# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""runtime/vision_loop.py — the vision-loop engine surface (P1.A1 SP-6.3).

The background vision loop (_background_vision_loop) + the 3 watchdog loops
(_vision_watchdog_loop / _heavy_worker_watchdog_loop / _audio_device_watchdog_loop)
+ the lip-tracking loop (_lip_tracking_loop) + the supervised restart helper
(_restart_vision_task) + the 3 move-with helpers (_classify_anti_spoof_verdict /
_should_run_recognition / _maybe_record_silent_obs), relocated VERBATIM from pipeline.py
modulo the bare->_wiring._X rewiring of the 4 WIRE-d vision globals (_anti_spoof_checker /
_vision_task / _vision_last_heartbeat / _vision_last_heartbeat_state, now in runtime.wiring).

8 move-with globals co-locate here (5 boot-constructed deps _vision_*_ref + 3 loop-internal
_last_active_bbox / _last_vision_report_str / _last_vision_shadow_at). run() push-DIs the 5
refs + _last_active_bbox via _vl._X (cross-module-set; canary-validated). engine layer:
runtime -> core; imports runtime.wiring + core.*; never pipeline. pipeline.py re-exports the
8 stays/test-reached symbols so run() + the test suite stay byte-identical.
"""
from __future__ import annotations

import asyncio
import core.heavy_worker as hw
import numpy as np
import runtime.wiring as _wiring
import time
from core.audio import set_lip_active, stop_audio
from core.config import (
    ANTI_SPOOF_REASON_PASSED, ANTI_SPOOF_REASON_REJECTED, ANTI_SPOOF_REASON_UNAVAILABLE, FACE_QUALITY_RECOGNITION, GREET_COOLDOWN, RECOGNITION_THRESHOLD, SCENE_STALE_SECS, SHADOW_CHANNEL_LOGGING_ENABLED, VISION_SHADOW_INTERVAL_SECS, VOICE_ROUTING_FACE_STALE_SECS, VOICE_SESSION_TIMEOUT,
)
from core.log_utils import _now_log_ts
from core.vision import (
    Camera, adaptive_threshold, estimate_yaw_from_landmarks, face_quality_score, verify_live,
)
from runtime.context_blocks import _infer_zone
from runtime.state_enums import PipelineState
from runtime.wiring import (
    _anti_spoof_rejection_store, _conversation_store, _per_person_agent_store, _presence_store, _track_store, _vision_frame_store, lip_tracker,
)


# Phase 2 — Vision Channel shadow logging (Session 124, 2026-04-28).
# Throttled to VISION_SHADOW_INTERVAL_SECS so observe_scene's extra
# embed+recognize cost is bounded. 0.0 means "fire on first scan".
_last_vision_shadow_at:       float         = 0.0
async def _lip_tracking_loop(camera: Camera) -> None:
    """
    Background task active during LISTENING.
    Uses the latest frame captured by _background_vision_loop (no extra camera reads —
    avoids racing with the background loop on the same VideoCapture object).
    """
    while True:
        frame = _vision_frame_store.peek_frame()
        if frame is not None and _last_active_bbox is not None:
            moving = lip_tracker.update(frame, _last_active_bbox)
            set_lip_active(moving)
        await asyncio.sleep(0.05)
def _maybe_record_silent_obs(emb, bbox: tuple, frame_w: int, frame_h: int, db) -> None:
    if time.monotonic() - _wiring._pipeline_state_store.peek_last_silent_update() < 5.0:
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_wiring._pipeline_state_store.set_last_silent_update(time.monotonic()))
    except RuntimeError:
        pass  # OPTIONAL: no running loop in sync test contexts
    zone = _infer_zone(bbox, frame_w, frame_h)
    db.update_silent_observation(emb, zone=zone)
_last_active_bbox:   tuple | None          = None
_last_vision_report_str: str  = ""   # last emitted [Vision] line; suppresses duplicate emissions
def _should_run_recognition(
    track_id: "int | None",
    track_identity: dict,
    unrecognized_tracks: dict,
    persons_in_frame: dict,
    now: float,
) -> bool:
    """Event-driven cadence gate for the secondary recognition scan (#11).

    Returns True when this track genuinely needs a recognition pass:
    - Brand-new track (never seen before)
    - Known person: refresh after 5s
    - Unknown/unrecognized track: retry after 2s
    """
    if track_id is None:
        return True
    if track_id not in track_identity and track_id not in unrecognized_tracks:
        return True  # brand-new track — run immediately
    if track_id in track_identity:
        pid = track_identity[track_id]
        last = persons_in_frame.get(pid, {}).get("last_recognized_at", 0.0)
        return now - last > 5.0  # refresh known person every 5s
    last_seen = unrecognized_tracks.get(track_id, 0.0)
    return now - last_seen > 2.0  # retry unknown track every 2s
def _classify_anti_spoof_verdict(
    frame, bbox, checker: "AntiSpoofChecker | None"
) -> "tuple[bool | None, float | None, str]":
    """P0.S1 Phase 2 — single source of truth for (live, score, reason).

    Maps a verify_live invocation into the four-reason-code space (C1):
      - checker unavailable → (None, None, ANTI_SPOOF_REASON_UNAVAILABLE)
      - verify_live True    → (True,  score, ANTI_SPOOF_REASON_PASSED)
      - verify_live False   → (False, score, ANTI_SPOOF_REASON_REJECTED)

    Pure function — no module state, no I/O beyond verify_live's own model
    call. Both producer paths (ambient-listen + secondary-scan) consume this
    helper so the reason-code mapping never drifts between paths.

    C0 same-frame discipline is enforced by the caller — passing the SAME
    `frame` variable to this helper that was sliced to produce the embedding
    crop. The marker-comment `P0S1-C0` (in-code `#`-prefixed) flags the
    discipline at each call site for the structural test in
    tests/test_p0_s1_phase2.py.
    """
    if checker is None or not getattr(checker, "available", False):
        return (None, None, ANTI_SPOOF_REASON_UNAVAILABLE)
    live = verify_live(frame, bbox, checker)
    score = getattr(checker, "last_score", None)
    if live:
        return (True, score, ANTI_SPOOF_REASON_PASSED)
    return (False, score, ANTI_SPOOF_REASON_REJECTED)
_vision_camera_ref: "Camera | None" = None
_vision_detector_ref: "FaceDetector | None" = None
_vision_embedder_ref: "FaceEmbedder | None" = None
_vision_temporal_buffer_ref: "TemporalEmbeddingBuffer | None" = None
_vision_db_ref: "FaceDB | None" = None
async def _vision_watchdog_loop() -> None:
    """P0.R3 D2 — supervises _background_vision_loop liveness via heartbeat.

    Polls every VISION_WATCHDOG_INTERVAL_SECS; if heartbeat staleness exceeds
    VISION_WATCHDOG_STALE_THRESHOLD_SECS, invokes the restart helper.
    On restart failure → set vision_degraded; subsequent stale detections log
    [Vision] stale persists + no respawn (next successful heartbeat clears).
    """
    from core.config import VISION_WATCHDOG_INTERVAL_SECS, VISION_WATCHDOG_STALE_THRESHOLD_SECS
    while True:
        await asyncio.sleep(VISION_WATCHDOG_INTERVAL_SECS)
        # Canary #2 / latency D1: staleness is pure elapsed-duration math against the
        # heartbeat written at :2845 via set_vision_heartbeat(time.monotonic()). MUST be
        # monotonic — was time.time(), which subtracted a wall-clock now (~1.78e9) from a
        # monotonic heartbeat (~10²) → staleness ≈ 1.78e9 ≫ threshold on every poll →
        # the watchdog cancelled+respawned the vision task every 5s for the whole session
        # (GPU thrash). No cross-process/persisted reason for this `now` to be wall-clock.
        _now = time.monotonic()
        _heartbeat_at = _wiring._pipeline_state_store.peek_vision_heartbeat_at()
        _staleness = _now - _heartbeat_at
        if _staleness < VISION_WATCHDOG_STALE_THRESHOLD_SECS:
            continue
        # Staleness detected. Two branches per Q7 absorption.
        if _wiring._pipeline_state_store.peek_vision_degraded():
            # Subsequent stale-detection while degraded already set.
            # Log + no-op for restart. Next successful heartbeat naturally clears degraded.
            print(f"[Vision] stale persists (vision_degraded set; awaiting heartbeat recovery; staleness={_staleness:.1f}s)")
            continue
        # First stale detection (degraded not yet set). Invoke restart helper.
        print(f"[Vision] stale detected (staleness={_staleness:.1f}s; restarting vision task)")
        await _restart_vision_task()
async def _heavy_worker_watchdog_loop() -> None:
    """P0.R8 D3 — supervises the 4 heavy-worker pools (AdaFace + Whisper +
    ECAPA + Pyannote) for subprocess crash bursts.

    Polls every ``HEAVY_WORKER_WATCHDOG_INTERVAL_SECS``; for each pool,
    checks crash count within ``HEAVY_WORKER_RESTART_BURST_WINDOW_SECS``
    rolling window via ``hw.count_recent_crashes(task_name, window)``.
    When count >= ``HEAVY_WORKER_RESTART_BURST_THRESHOLD`` AND the per-pool
    ``_alert_armed`` flag is True: marks pool "degraded" via
    ``_pipeline_state_store.set_heavy_worker_status`` + dispatches
    ``WatchdogAgent.report_heavy_worker_burst`` alert + disarms the flag
    (one alert per burst event). Re-arms + clears "degraded" when crash
    count drops below threshold within the window (automatic recovery).

    Mirror of P0.R3 ``_vision_watchdog_loop`` pattern (pipeline.py:2412):
    bare ``while True:`` body + cancellation propagates via
    ``CancelledError`` through ``await asyncio.sleep(...)`` at the
    shutdown explicit ``.cancel()`` + ``asyncio.wait_for(..., timeout=1.0)``
    in the pipeline.run() finally block.

    ProcessPoolExecutor auto-respawns subprocesses on next submit() after
    BrokenProcessPool; no explicit restart helper needed (materially
    simpler than P0.R3 which needed ``_restart_vision_task`` for vision-
    task lifecycle management — pool restart is the executor's
    responsibility, not the watchdog's).
    """
    import core.heavy_worker as hw  # noqa: PLC0415
    from core.config import (  # noqa: PLC0415
        HEAVY_WORKER_WATCHDOG_INTERVAL_SECS,
        HEAVY_WORKER_RESTART_BURST_THRESHOLD,
        HEAVY_WORKER_RESTART_BURST_WINDOW_SECS,
    )
    # Per-pool alert-armed flag; re-arms when crash count drops below
    # threshold. Initialized lazily as we encounter each pool name (default
    # True so the first breach fires an alert).
    _alert_armed: "dict[str, bool]" = {}
    while True:
        await asyncio.sleep(HEAVY_WORKER_WATCHDOG_INTERVAL_SECS)
        # Snapshot pool names; the registry can grow at runtime as new
        # task_name values get minted via get_or_create_pool().
        for task_name in list(hw._HEAVY_WORKER_POOLS):
            crash_count = hw.count_recent_crashes(
                task_name, HEAVY_WORKER_RESTART_BURST_WINDOW_SECS
            )
            armed = _alert_armed.get(task_name, True)
            if crash_count >= HEAVY_WORKER_RESTART_BURST_THRESHOLD:
                if armed:
                    await _wiring._pipeline_state_store.set_heavy_worker_status(
                        task_name, "degraded"
                    )
                    if _wiring._brain_orchestrator is not None:
                        _wiring._brain_orchestrator.report_heavy_worker_burst(
                            task_name=task_name,
                            crash_count=crash_count,
                            window_secs=HEAVY_WORKER_RESTART_BURST_WINDOW_SECS,
                        )
                    print(
                        f"[HeavyWorker] WATCHDOG: pool '{task_name}' degraded — "
                        f"{crash_count} crashes in last "
                        f"{HEAVY_WORKER_RESTART_BURST_WINDOW_SECS:.0f}s"
                    )
                    _alert_armed[task_name] = False  # disarm until recovery
            else:
                # Crash count dropped below threshold → re-arm + clear degraded.
                if not armed:
                    await _wiring._pipeline_state_store.set_heavy_worker_status(
                        task_name, "healthy"
                    )
                    print(
                        f"[HeavyWorker] WATCHDOG: pool '{task_name}' recovered — "
                        f"crash count {crash_count} < threshold "
                        f"{HEAVY_WORKER_RESTART_BURST_THRESHOLD}"
                    )
                    _alert_armed[task_name] = True
async def _audio_device_watchdog_loop() -> None:
    """P0.R10 D3 — audio device watchdog. Polls per-channel failure burst
    counter; on threshold breach: dispatches WatchdogAgent.report_audio_device_burst
    alert + disarms re-arm flag (one alert per burst event); re-arms when
    failure rate drops below threshold.

    Q4 (b) RATIFIED: forensic capture via persist_crash_diagnostic ONLY on
    burst-threshold breach (NOT on every individual failure event — would
    spam crash_logs/ directory on flaky USB scenarios).
    """
    import core.audio as _audio_mod  # noqa: PLC0415
    from core.config import (  # noqa: PLC0415
        AUDIO_DEVICE_WATCHDOG_INTERVAL_SECS,
        AUDIO_DEVICE_BURST_THRESHOLD,
        AUDIO_DEVICE_BURST_WINDOW_SECS,
    )
    # Per-channel alert-armed flag; re-arms when failure rate drops below
    # threshold (default True so first breach fires an alert).
    _alert_armed: "dict[str, bool]" = {"mic": True, "speaker": True}
    while True:
        await asyncio.sleep(AUDIO_DEVICE_WATCHDOG_INTERVAL_SECS)
        for channel in ("mic", "speaker"):
            failure_count = _audio_mod.count_recent_audio_failures(
                channel, AUDIO_DEVICE_BURST_WINDOW_SECS
            )
            armed = _alert_armed.get(channel, True)
            if failure_count >= AUDIO_DEVICE_BURST_THRESHOLD:
                if armed:
                    if _wiring._brain_orchestrator is not None:
                        _wiring._brain_orchestrator.report_audio_device_burst(
                            channel=channel,
                            failure_count=failure_count,
                            window_secs=AUDIO_DEVICE_BURST_WINDOW_SECS,
                        )
                    # Q4 (b) — forensic capture on burst-threshold breach only.
                    try:
                        from core.crash_logs import persist_crash_diagnostic  # noqa: PLC0415
                        _exc = RuntimeError(
                            f"Audio device '{channel}' burst threshold breached: "
                            f"{failure_count} failures in "
                            f"{AUDIO_DEVICE_BURST_WINDOW_SECS:.0f}s"
                        )
                        persist_crash_diagnostic(
                            f"audio_{channel}_device",
                            _exc,
                            f"audio device burst (channel={channel}, count={failure_count})",
                            failure_count,
                        )
                    except Exception:  # OPTIONAL: forensic capture failure
                        pass
                    print(
                        f"[Audio-Watchdog] channel '{channel}' degraded — "
                        f"{failure_count} failures in last "
                        f"{AUDIO_DEVICE_BURST_WINDOW_SECS:.0f}s"
                    )
                    _alert_armed[channel] = False
            else:
                # Failure count dropped below threshold → re-arm.
                if not armed:
                    print(
                        f"[Audio-Watchdog] channel '{channel}' recovered — "
                        f"failure count {failure_count} < threshold "
                        f"{AUDIO_DEVICE_BURST_THRESHOLD}"
                    )
                    _alert_armed[channel] = True
async def _restart_vision_task() -> None:
    """P0.R3 D4 — supervised restart of _background_vision_loop.

    Cancels current task, spawns new task, waits for first heartbeat advance.
    On restart success (heartbeat advances past pre-restart value within
    VISION_WATCHDOG_RESTART_TIMEOUT_SECS) → clear vision_degraded.
    On restart fail (exception during spawn OR heartbeat unchanged after timeout)
    → set vision_degraded + log fail-loud line. Q4 (c) combined criterion.

    Critical invariant — "keep audio alive": this helper cancels ONLY the
    `_vision_task` global. Audio loop is a separate task; never touched.
    """
    from core.config import VISION_WATCHDOG_RESTART_TIMEOUT_SECS
    # P1.A1 SP-6.3: _vision_task is WIRE-d (runtime.wiring); all access is _wiring._vision_task.
    _prev_heartbeat = _wiring._pipeline_state_store.peek_vision_heartbeat_at()

    # Cancel current task gracefully.
    try:
        if _wiring._vision_task is not None and not _wiring._vision_task.done():
            _wiring._vision_task.cancel()
            await asyncio.gather(_wiring._vision_task, return_exceptions=True)
    except Exception as e:
        print(f"[Vision] watchdog: existing task cancellation error: {e!r}")

    # Respawn new task. Q4 (c): catch exception path explicitly.
    try:
        _wiring._vision_task = asyncio.get_running_loop().create_task(
            _background_vision_loop(
                _vision_camera_ref,
                _vision_detector_ref,
                _vision_embedder_ref,
                _vision_temporal_buffer_ref,
                _vision_db_ref,
            )
        )
    except Exception as e:
        print(f"[Vision] watchdog: respawn raised: {e!r}; marking vision_degraded")
        loop = asyncio.get_running_loop()
        loop.create_task(_wiring._pipeline_state_store.set_vision_degraded(True))
        return

    # Wait for heartbeat advance (Q4 (c) heartbeat-timeout criterion).
    _deadline = time.monotonic() + VISION_WATCHDOG_RESTART_TIMEOUT_SECS
    while time.monotonic() < _deadline:
        await asyncio.sleep(1.0)
        if _wiring._pipeline_state_store.peek_vision_heartbeat_at() > _prev_heartbeat:
            # Restart succeeded. Clear degraded if previously set.
            if _wiring._pipeline_state_store.peek_vision_degraded():
                loop = asyncio.get_running_loop()
                loop.create_task(_wiring._pipeline_state_store.set_vision_degraded(False))
                print(f"[Vision] watchdog: restart success; vision_degraded cleared")
            else:
                print(f"[Vision] watchdog: restart success")
            return

    # Heartbeat did not advance within timeout. Set degraded.
    print(f"[Vision] watchdog: restart timeout (heartbeat unchanged after {VISION_WATCHDOG_RESTART_TIMEOUT_SECS:.0f}s); marking vision_degraded")
    loop = asyncio.get_running_loop()
    loop.create_task(_wiring._pipeline_state_store.set_vision_degraded(True))
async def _background_vision_loop(
    camera: Camera,
    detector: "FaceDetector",
    embedder: "FaceEmbedder | None" = None,
    temporal_buffer: "TemporalEmbeddingBuffer | None" = None,
    db: "FaceDB | None" = None,
) -> None:
    """Keep vision alive during conversation (LISTENING / THINKING / SPEAKING).

    Runs as a background asyncio task while the inner conversation loop runs.
    Updates: face-loss timer, latest frame, active-person bbox, lip-tracker baseline.
    When embedder+temporal_buffer+db are provided (ambient listen path), also runs
    full recognition so a known face wakes the pipeline without waiting for speech.
    All FAISS writes stay on the main loop to avoid thread-safety issues.
    YOLO intentionally NOT run here — see comment at bottom of loop.
    """
    loop = asyncio.get_running_loop()
    while True:
        # P0.R3 D1 — heartbeat update at iteration start (BEFORE camera.read).
        # Fire-and-forget via loop.create_task per existing sync-mutator pattern.
        # Race-safe: write fires from main loop, never from executor thread.
        loop.create_task(_wiring._pipeline_state_store.set_vision_heartbeat(time.monotonic()))

        frame = await loop.run_in_executor(None, camera.read)
        if frame is None:
            await asyncio.sleep(0.05)
            continue
        global _last_active_bbox
        # P0.S1 Phase 2 — collect per-detection anti-spoof verdicts for this
        # scan iteration. Aggregated at H2 vision_frame emit time to surface
        # a single iteration-level liveness signal in the event log payload.
        _h2_iter_verdicts: "list[bool | None]" = []
        await _vision_frame_store.set_frame(frame.copy(), time.monotonic())
        detections = await loop.run_in_executor(None, detector.detect, frame)
        if detections:
            # During ambient listen (no active sessions), any face counts as "seen".
            # During active conversation, _last_face_seen is updated by the secondary
            # scan below (which runs recognition). detect() never sets person_id, so
            # we can't filter by active person here.
            if not _wiring._session_store.peek_all_snapshots():
                try:
                    asyncio.get_running_loop().create_task(_wiring._pipeline_state_store.set_last_face_seen(time.monotonic()))
                except RuntimeError:
                    asyncio.run(_wiring._pipeline_state_store.set_last_face_seen(time.monotonic()))
            # Keep bbox current and calibrate lip tracker.
            # Calibration runs during SPEAKING — the person is quiet and still,
            # making it the ideal resting-motion baseline window.
            if _wiring._session_store.peek_all_snapshots():
                for det in detections:
                    if _wiring._session_store.peek_snapshot(det.person_id) is not None:
                        _last_active_bbox = det.bbox
                        if _wiring._pipeline_state_store.peek_pipeline_state() == PipelineState.SPEAKING:
                            lip_tracker.update_baseline(frame, det.bbox)
                        break

        # ── Full recognition when no active sessions (ambient listen path) ────
        if (
            embedder is not None
            and temporal_buffer is not None
            and db is not None
            and not _wiring._session_store.peek_all_snapshots()
            and detections
        ):
            for _det in detections:
                _x1, _y1, _x2, _y2 = _det.bbox
                # P0S1-C0: same-frame discipline — `_crop` is sliced from `frame`;
                # `verify_live(frame, _det.bbox, ...)` below operates on the SAME
                # `frame` variable; `embedder.embed(_crop)` further below derives
                # from the same slice. All three share `frame` so the verdict
                # corresponds to the embedding captured. C0 contract.
                _crop = frame[_y1:_y2, _x1:_x2]
                if _crop.size == 0:
                    continue
                _q = face_quality_score(_crop)
                if _q < FACE_QUALITY_RECOGNITION:
                    continue
                if _det.landmarks is not None:
                    _yaw = estimate_yaw_from_landmarks(_det.landmarks, _det.bbox)
                    if abs(_yaw) > 60.0:
                        continue
                # P0.R6 D3 (Site 1, line 2569): AdaFace embed routed via
                # ProcessPoolExecutor worker pool (`hw.run_heavy(...)`) instead
                # of the default ThreadPoolExecutor (`loop.run_in_executor(None, ...)`)
                # so heavy C-extension inference runs in a separate subprocess
                # — non-blocking with respect to the asyncio loop's other
                # coroutines. P0.R1 D1 None-return fallback preserved.
                _raw_emb_bytes = await hw.run_heavy(
                    "adaface_embed",
                    hw.adaface_embed_worker,
                    _crop.tobytes(),
                    _crop.shape,
                )
                _raw_emb = (
                    np.frombuffer(_raw_emb_bytes, dtype=np.float32)
                    if _raw_emb_bytes is not None
                    else None
                )
                _emb = temporal_buffer.add_and_pool(_det.bbox, _raw_emb, track_id=_det.track_id)

                # P0.S1 Phase 2 — classify anti-spoof verdict against the SAME
                # `frame` the crop was sliced from (C0 same-frame discipline).
                # Atomic upsert ensures embedding + verdict are observable
                # together via peek_snapshot (no torn-state window).
                (_as_live, _as_score, _as_reason) = _classify_anti_spoof_verdict(
                    frame, _det.bbox, _wiring._anti_spoof_checker
                )
                if _det.track_id is not None:
                    loop.create_task(_track_store.upsert_embedding_with_verdict(
                        track_id=_det.track_id,
                        embedding=_emb,
                        anti_spoof_live=_as_live,
                        anti_spoof_score=_as_score,
                        anti_spoof_reason=_as_reason,
                        captured_at=time.monotonic(),   # #5 Slice B (§0.1.5): TrackStore.captured_at single-clock w/ the _bv_scan_now mono write (behavior-neutral; no elapsed reader)
                        bbox=_det.bbox,
                    ))
                _h2_iter_verdicts.append(_as_live)

                _thresh = adaptive_threshold(_q, RECOGNITION_THRESHOLD)
                if _det.track_id is not None and temporal_buffer.pool_depth(_det.track_id) < 3:
                    _thresh += 0.05
                _pid, _pname, _conf = await loop.run_in_executor(None, db.recognize, _emb, _thresh)
                if (_pid
                        and time.monotonic() - _conversation_store.peek_last_greeted(_pid) >= GREET_COOLDOWN
                        and not _per_person_agent_store.is_ambient_wake_pending(_pid)):
                    # Reuse the verdict captured above — same frame, same bbox.
                    if _as_live is not True:
                        print(f"[Pipeline] Anti-spoof: BLOCKED background wake for {_pname} — liveness failed")
                        continue
                    loop.create_task(_per_person_agent_store.add_ambient_wake(_pid))  # debounce: suppress re-fires until outer loop consumes
                    print(f"[Vision] Background: recognized {_pname} (score={_conf:.3f}) — waking pipeline")
                    stop_audio()  # interrupt ambient listen; outer loop handles greeting next iteration
                    break
                elif not _pid:
                    # Unrecognized face during ambient listen — accumulate silent observation.
                    await loop.run_in_executor(
                        None, _maybe_record_silent_obs, _emb, _det.bbox, frame.shape[1], frame.shape[0], db
                    )

        # ── Secondary face scan during active conversation ────────────────────
        # Recognises all faces in frame so brain knows when a new person appears.
        # Runs immediately when face count rises (new arrival), otherwise throttled
        # to 1/s to avoid hammering the GPU during normal conversation.
        global _last_vision_report_str  # P1.A1 SP-6.3: _vision_face_scan_last is dead (SB.1 YOLO removal residue)
        # #5 Slice A: monotonic. Grep-proof — every _bv_scan_now consumer is in-memory or
        # elapsed-math: track_store.prune_stale/captured_at (:3072/:3127, in-mem), session
        # set_last_face_seen/update_face_seen (:3149/:3165, in-mem), presence
        # upsert_face_recognition (:3154, in-mem), should_run_recognition cadence (:3086),
        # presence/track staleness reads (:3190/:3204/:3243/:3262), shadow-log cadence
        # (:3221). NO db.add_embedding created_at, NO display → straight monotonic.
        _bv_scan_now = time.monotonic()
        _det_count = len(detections) if detections else 0
        _new_arrival = _det_count > _vision_frame_store.peek_prev_det_count()
        await _vision_frame_store.set_prev_det_count(_det_count)
        if (
            embedder is not None
            and temporal_buffer is not None
            and db is not None
            and _wiring._session_store.peek_all_snapshots()
            and detections
        ):
            # Prune track store to currently-live SORT track_ids
            _active_tids = {_det.track_id for _det in detections if _det.track_id is not None}
            # P0.S1 Phase 3 — capture tracks BEFORE prune so we can pop the
            # rejection store for tracks that disappear. Returning to a fresh
            # SORT track means a new window — the prior rejection history is
            # tied to the OLD track id.
            _pre_prune_tracks = set(_track_store.peek_all_track_ids())
            loop.create_task(_track_store.prune_stale(_bv_scan_now - SCENE_STALE_SECS))
            loop.create_task(_track_store.prune_to_active_tids(_active_tids))
            for _stale_tid in _pre_prune_tracks - _active_tids:
                # Per-track scope cleanup (C2).
                loop.create_task(_anti_spoof_rejection_store.pop(str(_stale_tid)))
            _all_track_snaps = _track_store.peek_all_snapshots()
            _ti_view = {s.track_id: s.identity_pid for s in _all_track_snaps if s.identity_pid is not None}
            _ut_view = {s.track_id: s.last_seen for s in _all_track_snaps if s.last_seen > 0}
            _pif_recog_view = {s.person_id: {"last_recognized_at": s.last_recognized_at}
                               for s in _presence_store.peek_all_snapshots()}
            for _det in detections:
                # Event-driven cadence: skip if this track was recently recognized (#11)
                if not _should_run_recognition(
                    _det.track_id, _ti_view, _ut_view,
                    _pif_recog_view, _bv_scan_now,
                ):
                    continue
                _x1, _y1, _x2, _y2 = _det.bbox
                # P0S1-C0: same-frame discipline — `_crop` is sliced from `frame`;
                # `_classify_anti_spoof_verdict(frame, ...)` below operates on the
                # SAME `frame` variable; `embedder.embed(_crop)` derives from the
                # same slice. C0 contract for the secondary-scan path.
                _crop = frame[_y1:_y2, _x1:_x2]
                if _crop.size == 0:
                    continue
                _q2 = face_quality_score(_crop)
                if _q2 < FACE_QUALITY_RECOGNITION:
                    continue
                # P0.R6 D3 (Site 2, was line 2663): AdaFace embed via worker pool.
                _raw_emb2_bytes = await hw.run_heavy(
                    "adaface_embed",
                    hw.adaface_embed_worker,
                    _crop.tobytes(),
                    _crop.shape,
                )
                _raw_emb2 = (
                    np.frombuffer(_raw_emb2_bytes, dtype=np.float32)
                    if _raw_emb2_bytes is not None
                    else None
                )
                # V3: pool across frames for stability (same buffer as primary loop)
                _emb2 = temporal_buffer.add_and_pool(_det.bbox, _raw_emb2, track_id=_det.track_id)

                # P0.S1 Phase 2 — classify anti-spoof verdict against same `frame`.
                # Atomic upsert (verdict + embedding visible together via peek).
                (_as2_live, _as2_score, _as2_reason) = _classify_anti_spoof_verdict(
                    frame, _det.bbox, _wiring._anti_spoof_checker
                )
                if _det.track_id is not None:
                    loop.create_task(_track_store.upsert_embedding_with_verdict(
                        track_id=_det.track_id,
                        embedding=_emb2,
                        anti_spoof_live=_as2_live,
                        anti_spoof_score=_as2_score,
                        anti_spoof_reason=_as2_reason,
                        captured_at=_bv_scan_now,
                        bbox=_det.bbox,
                    ))
                _h2_iter_verdicts.append(_as2_live)

                # V4: adaptive threshold — stricter for low-quality crops
                _thresh2 = adaptive_threshold(_q2, RECOGNITION_THRESHOLD)
                if _det.track_id is not None and temporal_buffer.pool_depth(_det.track_id) < 3:
                    _thresh2 += 0.05
                _pid2, _pname2, _conf2 = await loop.run_in_executor(
                    None, db.recognize, _emb2, _thresh2
                )
                if _pid2:
                    # Record confirmed identity for this track (used by main-loop track-continuity)
                    if _det.track_id is not None:
                        loop.create_task(_track_store.bind_identity(_det.track_id, _pid2))
                    if _wiring._session_store.peek_snapshot(_pid2) is not None:
                        # Active person confirmed in frame — update their face-seen timestamp
                        # so brain knows they're visible. (detect() never sets person_id,
                        # so the primary loop can't do this; secondary scan is the only place.)
                        try:
                            _loop = asyncio.get_running_loop()
                            _loop.create_task(_wiring._session_store.set_last_face_seen(_pid2, _bv_scan_now))
                        except RuntimeError:
                            pass  # OPTIONAL: no running loop in test/early-boot context
                    _is_new_in_frame = _pid2 not in _presence_store
                    loop.create_task(_presence_store.upsert_face_recognition(
                        _pid2, _pname2, _conf2, _bv_scan_now))
                    if _is_new_in_frame:
                        if _wiring._session_store.peek_snapshot(_pid2) is None:
                            if verify_live(frame, _det.bbox, _wiring._anti_spoof_checker):
                                print(f"[Vision] New person in frame: {_pname2} (conf={_conf2:.2f})")
                    # Step 3: update identity_evidence with the fresh face match.
                    # anti_spoof_live isn't re-checked here (secondary scan is 1 Hz;
                    # liveness was verified at greeting). Session stays recent-witness.
                    try:
                        _loop = asyncio.get_running_loop()
                        _loop.create_task(_wiring._session_store.update_face_seen(
                            _pid2, conf=_conf2, ts=_bv_scan_now))
                    except RuntimeError:
                        pass  # OPTIONAL
                    # S120 #1/#2 — person stepped in front of camera; face
                    # witness now available so voice_only_origin is no longer
                    # the sole accumulation path.
                    _pid2_snap_voi = _wiring._session_store.peek_snapshot(_pid2)
                    if _pid2_snap_voi is not None and _pid2_snap_voi.voice_only_origin:
                        try:
                            _loop = asyncio.get_running_loop()
                            _loop.create_task(_wiring._session_store.set_voice_only_origin(_pid2, False))
                        except RuntimeError:
                            pass  # OPTIONAL: no running loop in test/early-boot context
                else:
                    # Unrecognized face — record by SORT track_id for per-person routing
                    _tid = _det.track_id if _det.track_id is not None else id(_det)
                    loop.create_task(_track_store.mark_unrecognized(_tid, _bv_scan_now))
                    loop.create_task(_track_store.set_embedding(_tid, _emb2))
                    # #20: pre-allocate a stranger pid for each stable (SORT-confirmed) track
                    if _det.track_id is not None and _track_store.peek_stranger_pid(_tid) is None:
                        import uuid as _uuid_pa
                        loop.create_task(_track_store.mint_stranger(
                            _tid, f"stranger_{_uuid_pa.uuid4().hex[:8]}"))

            # Prune recognized persons who left (not seen for >5s)
            _stale_cutoff = _bv_scan_now - SCENE_STALE_SECS
            _stale_snaps = [
                s for s in _presence_store.peek_all_snapshots()
                if s.last_seen > 0 and s.last_seen < _stale_cutoff
            ]
            for _lp_snap in _stale_snaps:
                # Bug B: suppress the "left frame" log for voice-only entries — they
                # were never ON-camera, so "left frame" is misleading.
                #
                # Obs 4 (2026-04-20): when a voice entry ages out but its session is
                # still alive, emit a [Voice] message so the transition is visible.
                if _lp_snap.source == "voice":
                    _snap_voice_lp = _wiring._session_store.peek_snapshot(_lp_snap.person_id)
                    if _snap_voice_lp is not None:
                        _remaining = VOICE_SESSION_TIMEOUT - (_bv_scan_now - _snap_voice_lp.last_spoke_at)
                        print(f"[Voice] {_lp_snap.name} no longer heard — session expires in {_remaining:.0f}s")
                    continue
                print(f"[Vision] Person left frame: {_lp_snap.name} (conf={_lp_snap.conf:.2f})")
            loop.create_task(_presence_store.prune_stale(_stale_cutoff))

            # ── Phase 2 / Session 124 — Vision Channel shadow logging ─────
            # Throttled comparison: once per VISION_SHADOW_INTERVAL_SECS,
            # call the new pure observe_scene() with the SAME detections we
            # just used (via a precomputed-detections shim — avoids running
            # the FaceDetector twice and avoids corrupting SORT state).
            # Compare its visible_pids against the production
            # _persons_in_frame face-source entries. Production behavior
            # unchanged — observation only. Wrapped in try/except so a bug
            # in the new code can't break the vision loop.
            global _last_vision_shadow_at
            if (db is not None and embedder is not None
                    and (_bv_scan_now - _last_vision_shadow_at) >= VISION_SHADOW_INTERVAL_SECS):
                _last_vision_shadow_at = _bv_scan_now
                try:
                    from core.vision_channel import observe_scene as _vc_observe

                    class _PrecomputedDetectionsShim:
                        """One-shot detector that returns the just-computed
                        `detections` instead of re-running RetinaFace + SORT.
                        Side-effect-free."""
                        def __init__(self, dets):
                            self._dets = dets
                        def detect(self, _frame):
                            return self._dets

                    _shadow_state = _vc_observe(
                        frame,
                        face_detector=_PrecomputedDetectionsShim(detections),
                        face_embedder=embedder,
                        face_db=db,
                        recognition_threshold=RECOGNITION_THRESHOLD,
                        quality_min=FACE_QUALITY_RECOGNITION,
                        yaw_max_deg=60.0,
                        now=_bv_scan_now,
                    )
                    # Note on transient single-frame divergence (verified
                    # against canary 2026-04-29 line 1068): production
                    # `_persons_in_frame` smooths face presence over
                    # SCENE_STALE_SECS (5s); vision_channel.observe_scene()
                    # is per-frame. When RetinaFace transiently misses
                    # a face for one frame (blink, turn, lighting flicker),
                    # _prod_visible still holds the pid (windowed), but
                    # _new_visible drops it (this frame's truth). That's
                    # an expected semantic difference, NOT a vision_channel
                    # bug. The reconciler routing path consumes
                    # _persons_in_frame via _build_routing_inputs (smoothed),
                    # so production behavior under the cutover is unaffected.
                    # Single-frame divergences on face flicker are noise;
                    # SUSTAINED multi-scan divergence would indicate a real
                    # gate or stale-window mismatch worth investigating.
                    _prod_visible = {
                        s.person_id for s in _presence_store.peek_all_snapshots()
                        if s.source == "face" and _bv_scan_now - s.last_seen < SCENE_STALE_SECS
                    }
                    _new_visible = set(_shadow_state.visible_pids)
                    # D6: comparison still runs (rollout data); only the print is gated.
                    if _prod_visible != _new_visible and SHADOW_CHANNEL_LOGGING_ENABLED:
                        _diff_added = _new_visible - _prod_visible
                        _diff_dropped = _prod_visible - _new_visible
                        print(
                            f"[VisionChannel-Shadow] {_now_log_ts()} divergence: "
                            f"new_only={sorted(_diff_added)} prod_only={sorted(_diff_dropped)} "
                            f"new_total={len(_new_visible)} prod_total={len(_prod_visible)}"
                        )
                except Exception as _vc_shadow_e:
                    print(f"[VisionChannel-Shadow] error: {type(_vc_shadow_e).__name__}: {_vc_shadow_e!r}")

        # ── Real-time vision state emit ───────────────────────────────────────
        # Emits [Vision] <names> whenever the visible-people set changes.
        # Uses raw det_count for instant "none" detection (~167 ms latency);
        # uses recognition data for named entries (1 s latency from scan).
        _det_count_bv = len(detections) if detections else 0
        if _det_count_bv == 0:
            _vis_report_now = "none"
        else:
            _now_vr  = time.monotonic()  # #5 Slice A: monotonic — only consumers are
            # presence last_seen (:3291) + track last_seen (:3296) staleness gates
            # (VOICE_ROUTING_FACE_STALE_SECS elapsed-math, in-memory). No persist/display.
            # Bug B: only count face-sourced entries in the visual-scene report.
            # Voice-only entries live in _persons_in_frame for routing purposes
            # but don't belong in the "who is ON CAMERA" line.
            _rnames  = sorted(
                s.name for s in _presence_store.peek_all_snapshots()
                if (_now_vr - s.last_seen < VOICE_ROUTING_FACE_STALE_SECS
                    and s.source != "voice")
            )
            _unrec_n = sum(
                1 for s in _track_store.peek_all_snapshots()
                if s.last_seen > 0 and _now_vr - s.last_seen < VOICE_ROUTING_FACE_STALE_SECS
            )
            _vr_parts = list(_rnames)
            if _unrec_n == 1:
                _vr_parts.append("unrecognized")
            elif _unrec_n > 1:
                _vr_parts.append(f"{_unrec_n}x unrecognized")
            _vis_report_now = ", ".join(_vr_parts) if _vr_parts else "none"

        if _vis_report_now != _last_vision_report_str:
            print(f"[Vision] {_vis_report_now}")
            _last_vision_report_str = _vis_report_now

        # ── Vision heartbeat during conversation ──────────────────────────────
        # P1.A1 SP-6.3: both heartbeats are WIRE-d; all access is _wiring._vision_last_heartbeat*.
        _bv_now = time.time()  # WALLCLOCK: frame_ts (:3389 below) feeds the PERSISTED
        # vision_frame event-log payload (safe_emit_sync — replay-ordered, cross-process);
        # an event-log persisted stamp is out of #5 scope (§7). Stays wall.
        _bv_now_mono = time.monotonic()  # #5 Slice A: elapsed-math companion for the
        # vision-loop heartbeat-log cadence below (in-memory cadence, not persisted/displayed).
        if _bv_now_mono - _wiring._vision_last_heartbeat >= 30.0:
            _wiring._vision_last_heartbeat = _bv_now_mono
            state_label = _wiring._pipeline_state_store.peek_pipeline_state().name if _wiring._pipeline_state_store.peek_pipeline_state() else "?"
            if _wiring._session_store.peek_all_snapshots():
                who = ", ".join(snap.person_name for snap in _wiring._session_store.peek_all_snapshots())
            elif detections:
                # Bug B: only face-sourced entries count as "known faces" here.
                _known_faces = [s.name for s in _presence_store.peek_all_snapshots()
                                if s.source != "voice"]
                who = ("recognized=" + ", ".join(_known_faces)) if _known_faces else "unrecognized"
            else:
                who = "no face"
            _hb_key = f"{state_label}|{who}"
            if _hb_key != _wiring._vision_last_heartbeat_state:
                _wiring._vision_last_heartbeat_state = _hb_key
                print(f"[Vision] Active ({state_label}) — {who}")

        # P0.0.7 H2 — emit vision_frame event per scan iteration.
        # Sidecar style: pipeline orchestrates the scan; emit ties into the
        # per-iteration tail. JPEG storage at faces/frames/<frame_id>.jpg
        # uses content-hash keying for free deduplication (D2 — no inline
        # image bytes in the event payload). anti_spoof_* fields are
        # placeholders here (the scan itself doesn't run anti-spoof);
        # P0.S1 will wire the real values when anti-spoof-on-every-match
        # lands. The schema's load-bearing fields are present from day 1
        # so post-P0.S1 replay logs can drive regression tests.
        # Single P0.4-annotated except lives inside safe_emit_sync; the
        # JPEG-storage sub-try remains because storage failure is a
        # legitimate distinct concern (handled with explicit fallback).
        import hashlib as _h2_hash
        import uuid as _h2_uuid
        import cv2 as _h2_cv2
        from pathlib import Path as _H2Path
        from core.event_log import safe_emit_sync, VisionFramePayload
        from core.event_log.producer import _ensure_frames_dir as _h2_frames_dir
        _h2_recognized: list[tuple[str, float, float]] = []
        for _s in _presence_store.peek_all_snapshots():
            if _s.source == "face" and _s.last_seen > 0:
                _h2_recognized.append((_s.person_id, float(_s.conf or 0.0), 0.0))
        _h2_unrec_ids = tuple(
            int(s.track_id) for s in _track_store.peek_all_snapshots()
            if s.last_seen > 0 and s.identity_pid is None
        )
        _h2_frame_id = _h2_uuid.uuid4().hex[:12]
        _h2_frame_path: "str | None" = None
        try:
            _h2_frames = _h2_frames_dir()
            _h2_path = _H2Path(_h2_frames) / f"{_h2_frame_id}.jpg"
            # Best-effort JPEG write — failures fall back to frame_path=None.
            _ok, _h2_buf = _h2_cv2.imencode(".jpg", frame)
            if _ok:
                _h2_path.write_bytes(_h2_buf.tobytes())
                _h2_frame_path = str(_h2_path)
        except Exception:
            # OPTIONAL: JPEG storage failure must not break the vision loop —
            # event still emits with frame_path=None and replay degrades
            # gracefully (text-only diagnostics, no image evidence).
            _h2_frame_path = None
        # P0.S1 Phase 2 — aggregate per-iteration verdict.
        # Semantic: any rejection in this scan iteration means "spoof signal
        # observed somewhere"; all-passed means clean; checker unavailable for
        # all → None. Default when no detections produced a verdict is True
        # (no anti-spoof signal to report — replay distinguishes via the
        # recognized/unrecognized lists being empty too).
        if any(v is False for v in _h2_iter_verdicts):
            _h2_iter_live: "bool | None" = False
        elif any(v is True for v in _h2_iter_verdicts):
            _h2_iter_live = True
        elif _h2_iter_verdicts and all(v is None for v in _h2_iter_verdicts):
            _h2_iter_live = None
        else:
            _h2_iter_live = True
        safe_emit_sync(
            "vision_frame",
            VisionFramePayload(
                frame_id=_h2_frame_id,
                frame_path=_h2_frame_path,
                frame_ts=_bv_now,
                n_detections=len(detections) if detections else 0,
                recognized=tuple(_h2_recognized),
                unrecognized_track_ids=_h2_unrec_ids,
                # P0.S1 Phase 2 — real per-iteration aggregate verdict.
                # Replay can drive regression tests off this field now that
                # producer wires real anti-spoof results into the payload.
                anti_spoof_live=_h2_iter_live,
                anti_spoof_score=None,
            ),
        )
