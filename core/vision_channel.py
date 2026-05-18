"""
core/vision_channel.py — Phase 2 of the Voice/Vision Independence refactor.

A pure scene-observation function. Reads a video frame + injected face
recognition dependencies, outputs a structured `PresenceState`. Zero
voice reads. Zero imports from `pipeline.py`. Zero writes to shared
mutable structures.

Architectural target (from VOICE_VISION_INDEPENDENCE_PHASES_2_5_SPEC.md):

    frame + face_detector + face_embedder + face_db
            │
            ▼
    ┌─────────────────────┐
    │  VISION CHANNEL     │  ── this module
    │  observe_scene()    │
    └─────────────────────┘
            │
            ▼
       PresenceState {
         visible_pids: tuple[str, ...],
         unrecognized_track_ids: tuple[int, ...],
         per_pid_confidence: dict[str, float],
         per_pid_quality: dict[str, float],
         frame_ts: float,
         reasoning: str,
       }

The reconciler (Phase 3) consumes this state alongside `IdentityClaim`
(Phase 1) to make routing decisions. This module never makes routing
decisions itself — it only reports what the camera sees.

Hard rule: if `observe_scene` ever needs voice context to make a
decision, that's a bug. Return a low-confidence state and let the
reconciler decide.

Phase 2 scope: extract the function + run in shadow alongside the
existing background vision loop. No production change. After 1-2 weeks
of divergence-log review, graduate to Phase 3 (reconciler).

Design note on production shadow: production callers should allocate a
SEPARATE detector / embedder for the shadow path so calling
`observe_scene` doesn't mutate the existing SORT state. The function
itself is stateless w.r.t. shared globals — any state lives on the
injected dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np


@dataclass(frozen=True)
class PresenceState:
    """What the vision channel sees right now.

    Fields:
        visible_pids: tuple of person_ids whose face passed quality + yaw
            gates AND was recognized above threshold this frame. Sorted by
            descending confidence so callers can read the strongest match
            first.
        unrecognized_track_ids: SORT track IDs for faces that passed gates
            but did NOT match the gallery. Empty tuple when no
            unrecognized faces present (or when the caller passed no
            sort tracker that yields track_ids).
        per_pid_confidence: pid -> best face cosine match for this frame.
            Populated only for `visible_pids`.
        per_pid_quality: pid -> V1 quality_score (size/blur/brightness).
            Populated only for `visible_pids`. Useful for the reconciler's
            face-assist gates which sometimes condition on quality.
        frame_ts: caller-provided wall-clock timestamp for this frame
            (we never call `time.time()` internally — the reconciler
            wants a reproducible "now" reference across calls).
        reasoning: human-readable diagnostic for logging / debug.
    """
    visible_pids:           tuple[str, ...]
    unrecognized_track_ids: tuple[int, ...]
    per_pid_confidence:     dict[str, float] = field(default_factory=dict)
    per_pid_quality:        dict[str, float] = field(default_factory=dict)
    frame_ts:               float = 0.0
    reasoning:              str = ""


# Type aliases for the injectable callables. `face_detector` exposes
# `.detect(frame) -> list[Detection]` (Detection has `bbox`,
# `landmarks`, `track_id` attributes). `face_embedder` exposes
# `.embed(face_crop) -> np.ndarray`. `face_db` exposes
# `.recognize(emb, threshold) -> (pid, name, conf)`. Tests inject fakes
# matching these duck types.


def observe_scene(
    frame:                np.ndarray,
    *,
    face_detector:        Any,
    face_embedder:        Any,
    face_db:              Any,
    recognition_threshold: float,
    quality_min:          float,
    yaw_max_deg:          float,
    now:                  float,
    quality_score_fn:     "Callable[[np.ndarray], float] | None" = None,
    yaw_estimate_fn:      "Callable[..., float] | None"          = None,
) -> PresenceState:
    """Pure scene-observation — runs detect → quality gate → yaw gate →
    embed → FAISS recognize for each face in the frame, returns a
    structured `PresenceState`.

    Hard rule (Phase 2, VOICE_VISION_INDEPENDENCE_PHASES_2_5_SPEC.md):
    this function MAY NOT import from `pipeline.py`, MAY NOT read voice
    state (`_voice_gallery`, `_active_sessions`), MAY NOT write to
    `_persons_in_frame` or any shared module-level dict. If it needs
    voice context to make a decision, that's a bug. The reconciler
    decides; this function only reports.

    Parameters
    ----------
    frame:
        BGR `np.ndarray` from the camera (DirectShow / V4L2 path). The
        function does not modify the frame.
    face_detector:
        Object exposing `.detect(frame)` returning a list of Detection
        objects with `bbox`, `landmarks`, `track_id` attributes.
        Production injects the existing `core.vision.FaceDetector`;
        tests inject fakes.
    face_embedder:
        Object exposing `.embed(face_crop)` returning a 1-D numpy array
        (AdaFace embedding shape).
    face_db:
        Object exposing `.recognize(emb, threshold)` returning
        `(person_id, name, conf)`. The threshold parameter is the
        FAISS lookup floor.
    recognition_threshold:
        Cosine threshold for `face_db.recognize`. Caller passes
        production `RECOGNITION_THRESHOLD`. Tests pass whatever they
        want.
    quality_min:
        V1 quality_score floor. Below this, the face is dropped. Caller
        passes `FACE_QUALITY_RECOGNITION` from config.
    yaw_max_deg:
        Maximum |yaw| (degrees) for V2 yaw gate. Faces beyond this are
        dropped (side-on / profile views are unreliable). Caller passes
        ~60.0.
    now:
        Wall-clock timestamp the caller wants attached to this state.
        We never call `time.time()` internally — caller controls "now"
        for reproducibility across observation windows.
    quality_score_fn / yaw_estimate_fn:
        Optional injectable helpers for tests. Default to
        `core.vision.face_quality_score` /
        `core.vision.estimate_yaw_from_landmarks`.

    Returns
    -------
    PresenceState
        Always returns a state — never raises. On any internal error
        (bad frame, model unavailable), returns an empty state with
        `reasoning` describing the failure.
    """
    # Lazy default imports for the helpers. core.vision is the recognition
    # layer; it imports nothing from pipeline.
    if quality_score_fn is None or yaw_estimate_fn is None:
        from core import vision as _vision_mod
        if quality_score_fn is None:
            quality_score_fn = _vision_mod.face_quality_score
        if yaw_estimate_fn is None:
            yaw_estimate_fn = _vision_mod.estimate_yaw_from_landmarks

    if frame is None or not isinstance(frame, np.ndarray):
        return PresenceState(
            visible_pids=(), unrecognized_track_ids=(),
            per_pid_confidence={}, per_pid_quality={},
            frame_ts=float(now),
            reasoning="frame is None or wrong type",
        )

    # ── 1. Detect ────────────────────────────────────────────────────────
    try:
        detections = face_detector.detect(frame)
    except Exception as e:
        return PresenceState(
            visible_pids=(), unrecognized_track_ids=(),
            per_pid_confidence={}, per_pid_quality={},
            frame_ts=float(now),
            reasoning=f"detect failed: {type(e).__name__}: {e!r}",
        )

    if not detections:
        return PresenceState(
            visible_pids=(), unrecognized_track_ids=(),
            per_pid_confidence={}, per_pid_quality={},
            frame_ts=float(now),
            reasoning="no faces detected",
        )

    # ── 2. Per-face: quality gate → yaw gate → embed → recognize ─────────
    # Visible pids (above threshold) live in `visible` keyed by pid;
    # we keep the BEST score per pid in case the same person is detected
    # multiple times in one frame (rare but possible — mirror, photo).
    visible: dict[str, dict] = {}     # pid -> {"conf": float, "quality": float}
    unrecognized_track_ids: list[int] = []
    n_dropped_quality = 0
    n_dropped_yaw     = 0
    n_recognized      = 0
    n_unrecognized    = 0

    for det in detections:
        bbox = getattr(det, "bbox", None)
        if bbox is None or len(bbox) != 4:
            continue
        x1, y1, x2, y2 = bbox
        # Bounds check — frame slicing with bad coords can yield empty crops
        try:
            crop = frame[int(y1):int(y2), int(x1):int(x2)]
        except Exception:
            continue
        if crop.size == 0:
            continue

        # V1 quality gate
        try:
            q = quality_score_fn(crop)
        except Exception:
            q = 0.0
        if q < quality_min:
            n_dropped_quality += 1
            continue

        # V2 yaw gate (skip when no landmarks available — predict-only
        # frames don't carry landmarks; we keep them in the loop because
        # they still have track_ids worth recording).
        landmarks = getattr(det, "landmarks", None)
        if landmarks is not None:
            try:
                yaw = yaw_estimate_fn(landmarks, bbox)
            except Exception:
                yaw = 0.0
            if abs(yaw) > yaw_max_deg:
                n_dropped_yaw += 1
                continue

        # Embed + recognize
        track_id = getattr(det, "track_id", None)
        try:
            emb = face_embedder.embed(crop)
        except Exception:
            # Embedding failed — skip this face, continue with others
            continue
        if emb is None:
            continue
        try:
            pid, _name, conf = face_db.recognize(emb, recognition_threshold)
        except Exception:
            pid, conf = None, 0.0

        if pid:
            n_recognized += 1
            existing = visible.get(pid)
            if existing is None or float(conf) > existing["conf"]:
                visible[pid] = {"conf": float(conf), "quality": float(q)}
        else:
            n_unrecognized += 1
            if track_id is not None:
                # Only record once per track_id (a face detected in
                # multiple boxes — rare — shouldn't list the track twice).
                if int(track_id) not in unrecognized_track_ids:
                    unrecognized_track_ids.append(int(track_id))

    # ── 3. Sort visible_pids by confidence descending ────────────────────
    # Callers (the reconciler in Phase 3) often only care about the top
    # match; sorting puts it first.
    sorted_pids = sorted(
        visible.keys(), key=lambda p: visible[p]["conf"], reverse=True
    )
    per_conf = {p: visible[p]["conf"] for p in sorted_pids}
    per_qual = {p: visible[p]["quality"] for p in sorted_pids}

    reasoning = (
        f"{n_recognized} recognized, "
        f"{n_unrecognized} unrecognized, "
        f"{n_dropped_quality} dropped on quality, "
        f"{n_dropped_yaw} dropped on yaw"
    )
    _presence = PresenceState(
        visible_pids=tuple(sorted_pids),
        unrecognized_track_ids=tuple(unrecognized_track_ids),
        per_pid_confidence=per_conf,
        per_pid_quality=per_qual,
        frame_ts=float(now),
        reasoning=reasoning,
    )
    # P0.0.7 H4 — emit presence_state via safe_emit_sync (single
    # P0.4-annotated except lives inside the helper). Early-return paths
    # (no detections / no embedder / no db) skip the emission; replay
    # infers their absence from vision_frame events.
    from core.event_log import safe_emit_sync, PresenceStatePayload
    safe_emit_sync(
        "presence_state",
        PresenceStatePayload(presence=_presence),
    )
    return _presence
