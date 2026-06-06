"""
System health snapshot and log formatting.
Wave 5 / Item 19 — observability for production operations.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HealthSnapshot:
    timestamp: float
    active_sessions: int
    sessions_by_type: "dict[str, int]"
    persons_count: int
    total_face_embeddings: int
    knowledge_active_rows: int
    shadow_persons_count: int
    classifier_scenarios_active: int
    classifier_scenarios_quarantined: int
    cloud_state: str
    active_disputes: int
    unresolved_watchdog_alerts: int
    last_dream_run_seconds_ago: "float | None"
    thin_voice_galleries: "list[tuple[str, int]]"  # [(person_id, count)] for known persons with voice_n < 5
    # P0.0.7 D5 / D8.1 — event_log subsystem health.
    # `event_log_drops`: count of envelopes dropped due to bounded-queue
    #     backpressure since process start. Non-zero → consumer (writer
    #     task) falling behind; investigate writer-loop or DB lock.
    # `event_log_emit_failures`: count of exceptions swallowed by
    #     safe_emit_sync since process start. Non-zero → producer-hook
    #     bug (serialization failure / closed connection / etc.); check
    #     the [EventLog] WARN lines for the type+message of the first 3.
    # **No `event_log_dropped` event is emitted in the queue** (D5
    # circular-dependency guard) — these counters ARE the observability
    # signal; an event-about-a-dropped-event could itself be dropped.
    event_log_drops: int = 0
    event_log_emit_failures: int = 0
    # P0.B3 D2 — Kuzu graph degraded-mode observability.
    # `kuzu_degraded`: True iff BrainOrchestrator._kuzu_degraded is True in
    #     the current process. Set when graph schema upgrade fails (drop_schema
    #     or _init_schema raises) or when boot rebuild from knowledge rows
    #     raises. In degraded mode: graph queries silently return empty;
    #     cross-person privacy traversal (find_shared_entities) is broken;
    #     the P0.S7.D-B privacy-on-edges fix is bypassed. Recovery requires
    #     operator intervention: stop pipeline + delete the Kuzu directory
    #     + restart (brain.db facts will rebuild on next start). The
    #     format_health_alerts() output embeds the recovery procedure
    #     verbatim — operator never needs to grep logs or read source.
    # In-memory flag only — does not persist across process restarts.
    # Next boot's _ensure_graph_sync may set or clear it anew depending on
    # actual schema-state convergence (see P0.B3 audit §3.5).
    kuzu_degraded: bool = False
    # P0.R3 D3 — vision-loop watchdog observability.
    # `vision_degraded`: True iff the supervised vision-loop restart failed
    #     (cancel+respawn either raised an exception OR the new task didn't
    #     emit a heartbeat advance within VISION_WATCHDOG_RESTART_TIMEOUT_SECS).
    #     Cleared automatically when the next successful heartbeat advance
    #     fires (D4 restart-success path). Observability-only; pipeline
    #     continues running while degraded (audio + brain stay alive — the
    #     "keep audio alive" invariant under D4).
    vision_degraded: bool = False
    # P0.R6 D4 — heavy-worker pool health observability.
    # Mapping of task_name → status ∈ {"healthy", "degraded", "unknown"}.
    # Empty dict at boot before any pool spawn; populated by
    # `pipeline.run()` startup after `hw.get_or_create_pool("adaface_embed")`.
    # Conditional health-line emit fires when any pool has status != "healthy"
    # (see `format_health_line` below). Future P0.R6.X/Y/Z migrations add
    # entries for whisper + ecapa + pyannote pools using the same shape.
    heavy_worker_status: "dict[str, str]" = field(default_factory=dict)
    # P0.R8 D5 — per-pool crash count within HEAVY_WORKER_RESTART_BURST_WINDOW_SECS
    # rolling window. Empty dict at boot before any pool spawn; populated by
    # `gather_health_snapshot` via `hw.count_recent_crashes` per pool. Surfaces
    # the watchdog's burst-detection signal at the observability layer; when
    # any value > 0, `format_health_line` emits `heavy_worker_crashes=N`.
    heavy_worker_crash_counts: "dict[str, int]" = field(default_factory=dict)
    # P0.R11 D3 — recent persisted crash diagnostics (forensic JSON files in
    # faces/crash_logs/). Empty list at boot before any crash event; populated
    # by `gather_health_snapshot` via `crash_logs.list_recent_crash_logs(...)`
    # capped at HEALTH_CRASH_LOG_RECENT_LIMIT. When non-empty,
    # `format_health_line` emits `crash_logs=N` and `format_health_alerts`
    # emits an operator-actionable alert pointing at faces/crash_logs/ for
    # post-mortem analysis. Surfaces the persistence-side observability that
    # complements P0.R8's in-memory burst-detection signal.
    recent_crash_logs: "list[dict]" = field(default_factory=list)
    # P0.R9 D6 — VRAM budget guard observability.
    # `vram_budget` dict carries 2 keys: `refused_pools` (sorted list of
    # task_names refused by check_vram_budget) + `active_pools` (sorted list
    # of task_names currently spawned). Empty dict at boot before any pool
    # spawn / refusal. Populated by `gather_health_snapshot` via
    # `core.heavy_worker.peek_refused_pools()` + `_HEAVY_WORKER_POOLS` keys.
    # When `refused_pools` non-empty, `format_health_line` emits
    # `vram_refused=N` and `format_health_alerts` emits an operator-actionable
    # alert with config-tuning guidance.
    vram_budget: "dict[str, list[str]]" = field(default_factory=dict)
    # P0.R10 D5 — audio device failure resilience observability.
    # `audio_degraded` dict carries per-channel boolean keyed by 'mic' /
    # 'speaker' indicating whether the rolling failure count exceeds
    # AUDIO_DEVICE_BURST_THRESHOLD within AUDIO_DEVICE_BURST_WINDOW_SECS.
    # Empty dict at boot before any failure event. Populated by
    # `gather_health_snapshot` via `core.audio.count_recent_audio_failures`.
    # When any channel True, `format_health_line` emits
    # `audio_degraded=mic,speaker` and `format_health_alerts` emits an
    # operator-actionable alert.
    audio_degraded: "dict[str, bool]" = field(default_factory=dict)
    # P0.B4 D2 (Bundle 4 observability) — log drain liveness observability.
    # `log_drain_alive` trips False iff log_capture._log_drain_thread is dead OR
    # _log_drain_last_at hasn't advanced within LOG_DRAIN_STALENESS_SECS.
    # `log_drain_count` / `log_drain_error_count` mirror the runtime/log_capture.py module-
    # level counters so the dashboard can surface throughput + error rate.
    # Boot-time race tolerance: never-spawned thread + never-drained timestamp
    # both treated as alive (avoid false alerts before _log_drain spawns).
    log_drain_alive: bool = True
    log_drain_count: int = 0
    log_drain_error_count: int = 0


def gather_health_snapshot(
    db: Any,
    brain_orchestrator: Any,
    active_sessions: "list | tuple",
    cloud_state: Any,
    last_dream_run_at: "float | None",
) -> HealthSnapshot:
    """Gather all metrics in one pass. Each query is a fast SELECT COUNT(*).
    Total wall-clock budget: <100ms. Run in executor — never on the event loop.

    P0.7 adaptation: `active_sessions` is now a list/tuple of `SessionSnapshot`
    dataclasses (from `SessionStore.peek_all_snapshots()`), NOT the legacy
    `_active_sessions` dict.  Iterate directly + attribute-access for
    `person_type`.
    """
    now = time.time()

    # Sessions by type
    by_type: dict[str, int] = {"best_friend": 0, "known": 0, "stranger": 0, "disputed": 0}
    for s in active_sessions:
        pt = getattr(s, "person_type", "stranger")
        by_type[pt] = by_type.get(pt, 0) + 1

    # Active disputes are just disputed sessions
    disputes = by_type.get("disputed", 0)

    # faces.db counts
    try:
        persons_count = db._conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
        embed_count   = db._conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        thin = db._conn.execute("""
            SELECT p.id, COUNT(v.person_id)
            FROM persons p
            LEFT JOIN voice_embeddings v ON p.id = v.person_id
            WHERE p.type IN ('known', 'best_friend')
            GROUP BY p.id
            HAVING COUNT(v.person_id) < 5
        """).fetchall()
    except Exception:
        persons_count = -1
        embed_count   = -1
        thin          = []

    # brain.db counts
    try:
        bdb = brain_orchestrator._brain_db._conn
        knowledge_active = bdb.execute(
            "SELECT COUNT(*) FROM knowledge WHERE invalidated_at IS NULL"
        ).fetchone()[0]
        shadow_count = bdb.execute(
            "SELECT COUNT(*) FROM shadow_persons WHERE enrollment_status != 'confirmed'"
        ).fetchone()[0]
        watchdog_unresolved = bdb.execute(
            "SELECT COUNT(*) FROM watchdog_alerts WHERE resolved = 0"
        ).fetchone()[0]
    except Exception:
        knowledge_active    = -1
        shadow_count        = -1
        watchdog_unresolved = -1

    # classifier_scenarios.db counts — import the module-level singleton lazily
    try:
        from core import classifier_graph as _cg
        cdb_inst = _cg._classifier_db
        if cdb_inst is not None:
            cdb = cdb_inst._conn
            scen_active = cdb.execute(
                "SELECT COUNT(*) FROM scenarios WHERE active = 1"
            ).fetchone()[0]
            scen_quar = cdb.execute(
                "SELECT COUNT(*) FROM scenarios WHERE active = 0"
            ).fetchone()[0]
        else:
            scen_active, scen_quar = 0, 0
    except Exception:
        scen_active, scen_quar = -1, -1

    # P0.0.7 D8.1 — pull event_log degradation counters. Imported lazily
    # to keep gather_health_snapshot side-effect-free when event_log is
    # disabled (EVENT_LOG_ENABLED=0): the producer module is still
    # importable but its counters are zeros — no DB hit, no async work.
    try:
        from core.event_log.producer import (
            get_drop_count as _get_evlog_drops,
            get_safe_emit_failure_count as _get_evlog_emit_failures,
        )
        evlog_drops = int(_get_evlog_drops())
        evlog_emit_failures = int(_get_evlog_emit_failures())
    except Exception:
        # OPTIONAL: event_log module unavailable (early boot before producer
        # imported, or tests that mock out the package). Counters default
        # to 0 so the health line stays clean rather than emitting an alert.
        evlog_drops = 0
        evlog_emit_failures = 0

    # P0.B3 D2 — Kuzu degraded-mode observable. Defensive getattr so
    # brain_orchestrator may be partial during boot; missing attribute
    # defaults to False (not-degraded) so the health snapshot doesn't
    # false-alarm during early-boot windows.
    try:
        kuzu_degraded = bool(getattr(brain_orchestrator, "_kuzu_degraded", False))
    except Exception:
        # CLEANUP: defensive — see comment block above. Same fail-safe shape.
        kuzu_degraded = False

    # P0.R3 D3 — vision-loop watchdog degraded-mode observable. Same
    # defensive shape as kuzu_degraded above; reads from PipelineStateStore's
    # `_vision_degraded` flag (set/cleared by D4 restart helper).
    try:
        from pipeline import _pipeline_state_store as _pss
        vision_degraded = bool(_pss.peek_vision_degraded())
    except Exception:
        # OPTIONAL: pipeline module not yet importable (very early boot)
        # OR the store predates P0.R3 fields. Default False; the health
        # snapshot stays clean rather than emitting a false alert.
        vision_degraded = False

    # P0.R6 D4 — heavy-worker pool health. Defensive read mirroring the
    # vision_degraded pattern above: peeker returns a COPY so we don't
    # share-by-reference with the store's internal dict.
    try:
        from pipeline import _pipeline_state_store as _pss_hw
        heavy_worker_status = _pss_hw.peek_heavy_worker_status()
    except Exception:
        # OPTIONAL: store predates P0.R6 fields OR pipeline not yet
        # importable. Empty dict keeps the health line clean.
        heavy_worker_status = {}

    # P0.R8 D5 — per-pool crash count within rolling burst window.
    # Defensive read: if heavy_worker module isn't loaded yet (very early
    # boot) OR the config constants aren't available, return empty dict.
    heavy_worker_crash_counts: "dict[str, int]" = {}
    try:
        import core.heavy_worker as _hw_health  # noqa: PLC0415
        from core.config import HEAVY_WORKER_RESTART_BURST_WINDOW_SECS as _HW_WINDOW  # noqa: PLC0415

        for task_name in list(_hw_health._HEAVY_WORKER_POOLS):
            heavy_worker_crash_counts[task_name] = _hw_health.count_recent_crashes(
                task_name, _HW_WINDOW
            )
    except Exception:
        # OPTIONAL: heavy_worker not importable OR config not yet loaded.
        heavy_worker_crash_counts = {}

    # P0.R11 D3 — recent persisted crash diagnostics for HealthSnapshot.
    # Defensive read: crash_logs module is lazily imported (FACES_DIR mkdir
    # touches disk); if dir-create fails OR config constant unavailable, the
    # list defaults to empty so the health line stays clean.
    recent_crash_logs: "list[dict]" = []
    try:
        from core.crash_logs import list_recent_crash_logs as _list_crashes  # noqa: PLC0415
        from core.config import HEALTH_CRASH_LOG_RECENT_LIMIT as _CRASH_LIMIT  # noqa: PLC0415
        recent_crash_logs = _list_crashes(_CRASH_LIMIT)
    except Exception:
        # OPTIONAL: crash_logs module unavailable OR FACES_DIR access failure.
        recent_crash_logs = []

    # P0.R9 D6 — VRAM budget guard observability.
    # Defensive read mirroring heavy_worker_crash_counts above; if heavy_worker
    # module isn't loaded yet (very early boot), dict stays empty so the
    # health line stays clean.
    vram_budget: "dict[str, list[str]]" = {}
    try:
        import core.heavy_worker as _hw_vram  # noqa: PLC0415
        vram_budget = {
            "refused_pools": sorted(_hw_vram.peek_refused_pools()),
            "active_pools": sorted(_hw_vram._HEAVY_WORKER_POOLS.keys()),
        }
    except Exception:
        # OPTIONAL: heavy_worker not importable OR peek accessor unavailable.
        vram_budget = {}

    # P0.R10 D5 — audio device failure resilience observability.
    # Defensive read mirroring vram_budget above; if audio module isn't
    # loaded yet (very early boot) OR config constants unavailable, dict
    # stays empty so the health line stays clean.
    audio_degraded: "dict[str, bool]" = {}
    try:
        import core.audio as _audio_health  # noqa: PLC0415
        from core.config import (  # noqa: PLC0415
            AUDIO_DEVICE_BURST_THRESHOLD,
            AUDIO_DEVICE_BURST_WINDOW_SECS,
        )
        audio_degraded = {
            "mic": _audio_health.count_recent_audio_failures(
                "mic", AUDIO_DEVICE_BURST_WINDOW_SECS
            ) >= AUDIO_DEVICE_BURST_THRESHOLD,
            "speaker": _audio_health.count_recent_audio_failures(
                "speaker", AUDIO_DEVICE_BURST_WINDOW_SECS
            ) >= AUDIO_DEVICE_BURST_THRESHOLD,
        }
    except Exception:
        # OPTIONAL: audio module unavailable OR config not yet loaded.
        audio_degraded = {}

    # P0.B4 D2 — log drain liveness observability.
    # P1.A1 SP-4.1: the drain thread + counters live in runtime/log_capture.py now
    # (moved out of pipeline.py). Late import avoids any import-order surprise. The
    # rebound globals (_log_drain_thread / _log_drain_count / _last_at / _error_count)
    # are attribute-set on log_capture's namespace by pipeline.py's __main__ boot guard,
    # so they MUST be read from log_capture, not pipeline (a re-export would snapshot
    # stale zeros). Boot-time race tolerance: not-yet-spawned thread + never-drained
    # timestamp both treated as alive (avoids false alerts before the daemon spawns).
    log_drain_alive = True
    log_drain_count = 0
    log_drain_error_count = 0
    try:
        import runtime.log_capture as _log_capture_health  # noqa: PLC0415
        from core.config import LOG_DRAIN_STALENESS_SECS as _LOG_STALENESS  # noqa: PLC0415
        _thread = getattr(_log_capture_health, "_log_drain_thread", None)
        _last_at = getattr(_log_capture_health, "_log_drain_last_at", 0.0)
        log_drain_count = getattr(_log_capture_health, "_log_drain_count", 0)
        log_drain_error_count = getattr(_log_capture_health, "_log_drain_error_count", 0)
        _thread_alive = _thread.is_alive() if _thread is not None else True
        # WALLCLOCK: observability staleness check
        _fresh = (time.time() - _last_at) < _LOG_STALENESS if _last_at > 0 else True
        log_drain_alive = _thread_alive and _fresh
    except Exception:
        # OPTIONAL: pipeline not yet importable OR config unavailable. Boot-time
        # race tolerance: default alive so the health line stays clean.
        log_drain_alive = True

    return HealthSnapshot(
        timestamp=now,
        active_sessions=len(active_sessions),
        sessions_by_type=by_type,
        persons_count=persons_count,
        total_face_embeddings=embed_count,
        knowledge_active_rows=knowledge_active,
        shadow_persons_count=shadow_count,
        classifier_scenarios_active=scen_active,
        classifier_scenarios_quarantined=scen_quar,
        cloud_state=(str(cloud_state.name) if hasattr(cloud_state, "name") else str(cloud_state)),
        active_disputes=disputes,
        unresolved_watchdog_alerts=watchdog_unresolved,
        last_dream_run_seconds_ago=((now - last_dream_run_at) if last_dream_run_at is not None else None),
        thin_voice_galleries=thin,
        event_log_drops=evlog_drops,
        event_log_emit_failures=evlog_emit_failures,
        kuzu_degraded=kuzu_degraded,
        vision_degraded=vision_degraded,
        heavy_worker_status=heavy_worker_status,
        heavy_worker_crash_counts=heavy_worker_crash_counts,
        recent_crash_logs=recent_crash_logs,
        vram_budget=vram_budget,
        audio_degraded=audio_degraded,
        log_drain_alive=log_drain_alive,
        log_drain_count=log_drain_count,
        log_drain_error_count=log_drain_error_count,
    )


def format_health_line(s: HealthSnapshot) -> str:
    """One-line system pulse. Target: under 200 chars."""
    from datetime import datetime

    time_str = datetime.fromtimestamp(s.timestamp).strftime("%H:%M")

    parts: list[str] = []
    if s.sessions_by_type.get("best_friend", 0):
        parts.append(f"{s.sessions_by_type['best_friend']}bf")
    if s.sessions_by_type.get("known", 0):
        parts.append(f"{s.sessions_by_type['known']}known")
    if s.sessions_by_type.get("stranger", 0):
        parts.append(f"{s.sessions_by_type['stranger']}stranger")
    if s.sessions_by_type.get("disputed", 0):
        parts.append(f"{s.sessions_by_type['disputed']}disputed")
    sess_str = f"{s.active_sessions}({','.join(parts)})" if parts else str(s.active_sessions)

    if s.last_dream_run_seconds_ago is None:
        dream_str = "never"
    elif s.last_dream_run_seconds_ago < 60:
        dream_str = f"{int(s.last_dream_run_seconds_ago)}s_ago"
    elif s.last_dream_run_seconds_ago < 3600:
        dream_str = f"{int(s.last_dream_run_seconds_ago / 60)}m_ago"
    else:
        dream_str = f"{int(s.last_dream_run_seconds_ago / 3600)}h_ago"

    # P0.0.7 D8.2 — surface event_log degradation only when non-zero.
    # Steady-state runs (both counters 0) keep the health line clean;
    # any non-zero count tags the specific counter so operators can
    # grep for the right surface ("event_log_drops" vs
    # "event_log_emit_failures").
    evlog_parts: list[str] = []
    if s.event_log_drops > 0:
        evlog_parts.append(f"event_log_drops={s.event_log_drops}")
    if s.event_log_emit_failures > 0:
        evlog_parts.append(f"event_log_emit_failures={s.event_log_emit_failures}")
    evlog_str = (" | " + " ".join(evlog_parts)) if evlog_parts else ""

    # P0.B3 D2 — surface kuzu_degraded only when True. Mirrors the evlog_parts
    # conditional-emit pattern: clean health line in steady-state; non-zero
    # state tags the surface explicitly so operators grep for "kuzu=degraded"
    # without scanning the full alerts block.
    kuzu_parts: list[str] = []
    if s.kuzu_degraded:
        kuzu_parts.append("kuzu=degraded")
    kuzu_str = (" | " + " ".join(kuzu_parts)) if kuzu_parts else ""

    # P0.R3 D3 — surface vision=degraded only when True. Same conditional-emit
    # pattern as kuzu_parts above; clean steady-state line; degraded state
    # tags the surface explicitly so operators grep `vision=degraded`.
    vision_dgr_parts: list[str] = []
    if s.vision_degraded:
        vision_dgr_parts.append("vision=degraded")
    vision_dgr_str = (" | " + " ".join(vision_dgr_parts)) if vision_dgr_parts else ""

    # P0.R2 D5 — surface vision_provider=cpu only when active provider is CPU
    # (CUDA failure triggered state-machine switch OR D3 graceful CPU-only boot).
    # Mirrors evlog_parts/kuzu_parts conditional-emit pattern.
    from core import vision_provider_state as _vps
    vision_parts: list[str] = []
    if _vps.get_active_provider() == "cpu":
        vision_parts.append("vision_provider=cpu")
    vision_str = (" | " + " ".join(vision_parts)) if vision_parts else ""

    # P0.R6 D4 — surface heavy_workers=degraded only when any worker pool is
    # non-healthy. Same conditional-emit pattern as vision_provider above;
    # empty dict (no pools yet OR all healthy) keeps the line clean.
    hw_parts: list[str] = []
    if s.heavy_worker_status and any(
        v != "healthy" for v in s.heavy_worker_status.values()
    ):
        hw_parts.append("heavy_workers=degraded")
    hw_str = (" | " + " ".join(hw_parts)) if hw_parts else ""

    # P0.R8 D5 — surface heavy_worker_crashes=N only when any pool has crash
    # count > 0 in the rolling burst window. Aggregate total across all 4
    # pools; per-pool breakdown lives in format_health_alerts when degraded.
    hw_crash_parts: list[str] = []
    if s.heavy_worker_crash_counts:
        _hw_total = sum(s.heavy_worker_crash_counts.values())
        if _hw_total > 0:
            hw_crash_parts.append(f"heavy_worker_crashes={_hw_total}")
    hw_crash_str = (" | " + " ".join(hw_crash_parts)) if hw_crash_parts else ""

    # P0.R11 D3 — surface crash_logs=N only when persisted crash diagnostic
    # files are present. Same conditional-emit pattern as hw_crash above; clean
    # steady-state line until a crash event persists a JSON file.
    crash_logs_parts: list[str] = []
    if s.recent_crash_logs:
        crash_logs_parts.append(f"crash_logs={len(s.recent_crash_logs)}")
    crash_logs_str = (" | " + " ".join(crash_logs_parts)) if crash_logs_parts else ""

    # P0.R9 D6 — surface vram_refused=N only when any pool was refused by the
    # VRAM budget guard. Steady-state clean (no refusals); refusal state tags
    # the surface explicitly so operators grep `vram_refused`.
    vram_parts: list[str] = []
    refused = s.vram_budget.get("refused_pools", []) if s.vram_budget else []
    if refused:
        vram_parts.append(f"vram_refused={len(refused)}")
    vram_str = (" | " + " ".join(vram_parts)) if vram_parts else ""

    # P0.R10 D5 — surface audio_degraded=mic,speaker only when any channel
    # exceeds AUDIO_DEVICE_BURST_THRESHOLD within rolling window. Empty dict
    # OR all-False keeps the line clean; degraded channels listed explicitly.
    audio_parts: list[str] = []
    _degraded_channels = [
        c for c, deg in (s.audio_degraded or {}).items() if deg
    ]
    if _degraded_channels:
        audio_parts.append(f"audio_degraded={','.join(_degraded_channels)}")
    audio_str = (" | " + " ".join(audio_parts)) if audio_parts else ""

    # P0.B4 D2 — surface log_drain=DEAD only when liveness check trips OR
    # log_drain_errors=N only when outer-except handler has fired. Same
    # conditional-emit pattern as audio_degraded; clean steady-state line.
    log_drain_parts: list[str] = []
    if not s.log_drain_alive:
        log_drain_parts.append("log_drain=DEAD")
    if s.log_drain_error_count > 0:
        log_drain_parts.append(f"log_drain_errors={s.log_drain_error_count}")
    log_drain_str = (" | " + " ".join(log_drain_parts)) if log_drain_parts else ""

    return (
        f"[Health] {time_str} | sessions={sess_str} | "
        f"faces={s.persons_count}({s.total_face_embeddings}emb) | "
        f"knowledge={s.knowledge_active_rows}({s.shadow_persons_count}shadow) | "
        f"classifier={s.classifier_scenarios_active}act,{s.classifier_scenarios_quarantined}quar | "
        f"cloud={s.cloud_state} | disputes={s.active_disputes} | "
        f"alerts={s.unresolved_watchdog_alerts} | dream={dream_str}"
        f"{evlog_str}"
        f"{kuzu_str}"
        f"{vision_str}"
        f"{vision_dgr_str}"
        f"{hw_str}"
        f"{hw_crash_str}"
        f"{crash_logs_str}"
        f"{vram_str}"
        f"{audio_str}"
        f"{log_drain_str}"
    )


def format_health_alerts(s: HealthSnapshot, brain_orchestrator: Any) -> "list[str]":
    """Sub-lines for issues the operator should investigate. Empty list = healthy."""
    alerts: list[str] = []

    if s.active_disputes > 0:
        alerts.append(
            f"[Health-Alert] {s.active_disputes} dispute(s) active — investigate via dashboard"
        )

    if s.unresolved_watchdog_alerts > 0:
        try:
            recent = brain_orchestrator._brain_db._conn.execute(
                """SELECT alert_type, created_at FROM watchdog_alerts
                   WHERE resolved = 0
                   ORDER BY created_at DESC LIMIT 5"""
            ).fetchall()
            details = ", ".join(
                f"{t} ({_age_str(time.time() - ts)})" for t, ts in recent
            )
            alerts.append(
                f"[Health-Alert] {s.unresolved_watchdog_alerts} unresolved watchdog alerts: {details}"
            )
        except Exception:
            alerts.append(
                f"[Health-Alert] {s.unresolved_watchdog_alerts} unresolved watchdog alerts"
            )

    if s.thin_voice_galleries:
        from core.config import HEALTH_THIN_VOICE_MAX
        for pid, n in s.thin_voice_galleries[:HEALTH_THIN_VOICE_MAX]:
            alerts.append(f"[Health-Alert] Voice gallery thin: {pid} at {n}/5 samples")

    # P0.0.7 D8.3 — event_log subsystem degradation alerts. Either
    # counter being non-zero means the event-log producer is shedding
    # signal; the alert names the specific counter so operators
    # investigate the right surface. Drops = bounded-queue full
    # (consumer falling behind); emit_failures = exceptions swallowed by
    # safe_emit_sync (producer-hook bug — check the [EventLog] WARN
    # lines for type+message of the first 3).
    if s.event_log_drops > 0:
        alerts.append(
            f"[Health-Alert] event_log_drops={s.event_log_drops} — "
            f"writer task falling behind; bounded queue (10000) shedding "
            f"envelopes. Investigate writer-loop / DB lock / disk-full."
        )
    if s.event_log_emit_failures > 0:
        alerts.append(
            f"[Health-Alert] event_log_emit_failures={s.event_log_emit_failures} "
            f"— safe_emit_sync swallowed exception(s) from a producer hook. "
            f"Grep `[EventLog] WARN` in terminal_output for the type+message "
            f"of the first 3 (rate-limited)."
        )

    # P0.B3 D2 — Kuzu degraded-mode actionable recovery alert.
    # Per Plan v1 §3.3 substring lock: alert text MUST contain
    #   "Kuzu graph in degraded mode" + "Recovery: stop pipeline" +
    #   "rm -rf <path>" + "restart" + "brain.db facts will rebuild"
    # and MUST NOT contain any doc-URL form (no http:// / see-the-wiki /
    # consult-docs etc.) — recovery is HARDCODED inline so the operator
    # never has to grep logs or read source code.
    if s.kuzu_degraded:
        try:
            from pathlib import Path
            _gp = getattr(brain_orchestrator, "_graph_db_path", "<unknown>")
            _gp_resolved = str(Path(_gp).resolve()) if _gp != "<unknown>" else "<unknown>"
        except Exception:
            # CLEANUP: path resolution failure — emit alert with placeholder so
            # the recovery procedure stays visible even if path attr is missing.
            _gp_resolved = "<graph_db_path>"
        alerts.append(
            f"[Health-Alert] Kuzu graph in degraded mode — graph queries "
            f"returning empty (cross-person traversal broken; privacy "
            f"enforcement on RELATES_TO edges bypassed). "
            f"Recovery: stop pipeline, run `rm -rf {_gp_resolved}`, restart. "
            f"brain.db facts will rebuild from SQLite on next start."
        )

    # P0.R3 D3 — vision-loop degraded actionable alert.
    # Set when the supervised vision-loop restart (D4) failed: either the
    # respawn raised an exception OR the new task's first heartbeat didn't
    # advance within VISION_WATCHDOG_RESTART_TIMEOUT_SECS. Pipeline keeps
    # running (audio + brain alive — "keep audio alive" invariant); vision
    # subsystem is degraded until the next heartbeat advance auto-clears.
    if s.vision_degraded:
        alerts.append(
            "[Health-Alert] Vision subsystem degraded — restart attempts failing; "
            "check camera/driver state. "
            "Recovery: verify USB camera connection + driver; "
            "vision_degraded clears automatically on next successful heartbeat."
        )

    # P0.R6 D4 + P0.R8 D5 — heavy-worker pool degraded actionable alert.
    # Set when any pool transitions to a non-healthy state (subprocess crash
    # burst per P0.R8 watchdog; or future startup failure modes). Pipeline
    # keeps running (asyncio loop alive); the affected inference path returns
    # via P0.R1 D1 fallback semantic at each migrated call site.
    # Verbatim substrings per Plan v1 §2.5 substring lock:
    #   "Heavy-worker pool" (prefix) + "degraded" (state) + "auto-respawn"
    #   (recovery mechanism) + "check logs" (operator action) +
    #   "clears when crash rate drops" (recovery semantic).
    _degraded_pools = [
        name for name, status in s.heavy_worker_status.items()
        if status != "healthy"
    ]
    if _degraded_pools:
        # P0.R8 D5 — include per-pool crash counts in the alert when available
        # so operators see WHICH pools are crashing AND HOW OFTEN within the
        # rolling burst window.
        _crash_details = []
        for name in sorted(_degraded_pools):
            count = s.heavy_worker_crash_counts.get(name, 0) if s.heavy_worker_crash_counts else 0
            _crash_details.append(f"{name}={count} crashes")
        _crash_summary = ", ".join(_crash_details) if _crash_details else "no crash counts available"
        alerts.append(
            f"[Health-Alert] Heavy-worker pool(s) degraded — "
            f"{_crash_summary} in the recent burst window. "
            f"ProcessPoolExecutor will auto-respawn subprocesses on next "
            f"submit; check logs for crash root cause (CUDA OOM, model "
            f"file corruption, etc.). Pool status clears when crash rate "
            f"drops below the burst threshold within the rolling window."
        )

    # P0.R11 D3 — recent persisted crash diagnostics available alert.
    # Verbatim substrings per Plan v1 §2.3 substring lock:
    #   "Recent crash logs available" (prefix) +
    #   "check faces/crash_logs/" (operator action) +
    #   "CRASH_LOG_RETENTION_DAYS" (config knob naming).
    # Fires whenever recent_crash_logs is non-empty (steady-state empty since
    # crashes are rare; alert keeps surfaced until dream-loop prune clears
    # the directory).
    if s.recent_crash_logs:
        most_recent = s.recent_crash_logs[0]
        _task = most_recent.get("task_name", "<unknown>")
        _ts = most_recent.get("timestamp", 0)
        _ts_str = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(_ts))
        alerts.append(
            f"[Health-Alert] Recent crash logs available — "
            f"most recent: task_name={_task} at {_ts_str}. "
            f"check faces/crash_logs/ for forensic data; clears after "
            f"CRASH_LOG_RETENTION_DAYS via dream-loop cleanup."
        )

    # P0.R9 D6 — VRAM budget refusal alert.
    # Verbatim substrings per Plan v1 §2.6 substring lock (5 substrings):
    #   "VRAM budget refusal" + "pools refused:" + "VRAM_POOL_PRIORITY" +
    #   "VRAM_CEILING_PCT" + "HEAVY_WORKER_VRAM_ESTIMATES_MB"
    # Surfaces operator-actionable config tuning guidance. Refusal state is
    # immutable per process (cached in _REFUSED_POOLS; clears on restart);
    # alert persists for the lifetime of the refusal.
    _refused = s.vram_budget.get("refused_pools", []) if s.vram_budget else []
    if _refused:
        alerts.append(
            f"[Health-Alert] VRAM budget refusal — "
            f"pools refused: {', '.join(_refused)}. "
            f"Caller fallback active. Tune VRAM_POOL_PRIORITY / "
            f"VRAM_CEILING_PCT / HEAVY_WORKER_VRAM_ESTIMATES_MB at "
            f"core/config.py + restart to recover."
        )

    # P0.R10 D5 — audio device degraded actionable alert.
    # Verbatim substrings per Plan v1 §2.5 substring lock (5 substrings):
    #   "Audio device degraded" + "channels:" + "USB/audio device connection"
    #   + "driver" + "AUDIO_DEVICE_BURST_THRESHOLD"
    # Fires when any channel's rolling failure count exceeds threshold.
    _degraded_audio_channels = [
        c for c, deg in (s.audio_degraded or {}).items() if deg
    ]
    if _degraded_audio_channels:
        alerts.append(
            f"[Health-Alert] Audio device degraded — channels: "
            f"{', '.join(_degraded_audio_channels)}. Check USB/audio device "
            f"connection + driver + permissions. Clears when failure rate "
            f"drops below AUDIO_DEVICE_BURST_THRESHOLD."
        )

    # P0.B4 D2 — log drain liveness actionable alert.
    # Verbatim substrings per Plan v1 §2 D2 substring lock (5 substrings):
    #   "Log drain thread degraded" + "check pipeline restart" +
    #   "messages drained:" + "errors:" + "LOG_DRAIN_STALENESS_SECS"
    # Fires when log_drain_alive trips False — either the daemon thread died
    # OR _log_drain_last_at hasn't advanced within LOG_DRAIN_STALENESS_SECS.
    if not s.log_drain_alive:
        from core.config import LOG_DRAIN_STALENESS_SECS
        alerts.append(
            f"[Health-Alert] Log drain thread degraded — check pipeline restart "
            f"(messages drained: {s.log_drain_count}, "
            f"errors: {s.log_drain_error_count}, "
            f"LOG_DRAIN_STALENESS_SECS={LOG_DRAIN_STALENESS_SECS})"
        )

    return alerts


def _age_str(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds / 60)}m"
    if seconds < 86400:
        return f"{int(seconds / 3600)}h"
    return f"{int(seconds / 86400)}d"
