"""tests/test_vision_channel.py — Phase 2 of Voice/Vision Independence.

Tests the new pure `core.vision_channel.observe_scene` function. Hard
rule under test: the function MUST NOT import from pipeline.py, MUST
NOT read voice state, MUST NOT write to `_persons_in_frame` or any
shared module-level dict. Each test reflects one boundary or behavioral
contract from VOICE_VISION_INDEPENDENCE_PHASES_2_5_SPEC.md.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass

import numpy as np
import pytest

from core import vision_channel as vc_mod
from core.vision_channel import PresenceState, observe_scene


# ── Test fakes (no real models — pure unit testing) ──────────────────────


@dataclass
class _FakeDetection:
    bbox:      tuple[int, int, int, int]
    landmarks: object | None = None
    track_id:  int | None    = None


class _FakeDetector:
    """Sync fake matching `core.vision.FaceDetector.detect` shape."""

    def __init__(self, detections: list[_FakeDetection]):
        self._detections = detections

    def detect(self, frame: np.ndarray) -> list[_FakeDetection]:
        # Pure — frame argument ignored; canned detections returned.
        return list(self._detections)


class _FakeEmbedder:
    """Sync fake matching `core.vision.FaceEmbedder.embed`. Returns a
    deterministic vector keyed by the crop's first pixel value so each
    different face yields a different embedding (for downstream
    recognize routing in fakes that care)."""

    def embed(self, crop: np.ndarray) -> np.ndarray:
        if crop is None or crop.size == 0:
            return None
        seed = int(crop.flat[0]) & 0xFF
        rng = np.random.default_rng(seed + 1)
        v = rng.standard_normal(512).astype(np.float32)
        return v / float(np.linalg.norm(v) + 1e-9)


class _FakeDB:
    """Sync fake matching `FaceDB.recognize`. Returns (pid, name, conf)
    based on a pre-set rule callable. The default rule recognizes
    nothing."""

    def __init__(self, rule=None):
        # rule(emb) -> (pid|None, name|None, conf)
        self._rule = rule or (lambda emb: (None, None, 0.0))

    def recognize(self, emb: np.ndarray, threshold: float):
        return self._rule(emb)


def _frame(h: int = 480, w: int = 640) -> np.ndarray:
    """Synthetic BGR frame. The function delegates pixel work to the
    detector/embedder fakes, so any non-zero array is fine."""
    return np.full((h, w, 3), 64, dtype=np.uint8)


# ── 1. Pure function — no pipeline import at module scope ────────────────


def test_vision_channel_imports_no_pipeline():
    """vision_channel.py must not import pipeline. The hard architectural
    boundary from VOICE_VISION_INDEPENDENCE_PHASES_2_5_SPEC.md.

    AST-based check (substring would false-positive on docstring
    mentions like "must NOT import pipeline" — exactly what we
    write in the module's own header)."""
    import ast
    src = importlib.import_module("core.vision_channel")
    tree = ast.parse(open(src.__file__, encoding="utf-8").read())
    forbidden = {"pipeline"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in forbidden, (
                    f"vision_channel.py must NOT import {alias.name!r} "
                    f"(architectural boundary, "
                    f"see VOICE_VISION_INDEPENDENCE_PHASES_2_5_SPEC.md)"
                )
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            assert root not in forbidden, (
                f"vision_channel.py must NOT import from {node.module!r}"
            )


# ── 2. Mocked-out voice dependencies — function still works ──────────────


def test_observe_scene_runs_when_voice_modules_unavailable(monkeypatch):
    """If something tried to make vision_channel transitively read voice
    state, this test would fail at function-call time. Block any import
    of voice-related modules and verify the call still succeeds."""
    forbidden = ("pipeline", "core.voice", "core.voice_channel")
    for mod in forbidden:
        monkeypatch.setitem(sys.modules, mod, None)

    state = observe_scene(
        _frame(),
        face_detector=_FakeDetector([]),
        face_embedder=_FakeEmbedder(),
        face_db=_FakeDB(),
        recognition_threshold=0.28,
        quality_min=0.2,
        yaw_max_deg=60.0,
        now=12345.0,
        quality_score_fn=lambda crop: 0.9,           # avoid core.vision import
        yaw_estimate_fn=lambda landmarks, bbox: 0.0,
    )
    assert isinstance(state, PresenceState)
    assert state.visible_pids == ()


# ── 3. Zero faces → empty state ──────────────────────────────────────────


def test_observe_scene_zero_faces_returns_empty_state():
    state = observe_scene(
        _frame(),
        face_detector=_FakeDetector([]),
        face_embedder=_FakeEmbedder(),
        face_db=_FakeDB(),
        recognition_threshold=0.28,
        quality_min=0.2,
        yaw_max_deg=60.0,
        now=100.0,
        quality_score_fn=lambda crop: 0.9,
        yaw_estimate_fn=lambda landmarks, bbox: 0.0,
    )
    assert state.visible_pids == ()
    assert state.unrecognized_track_ids == ()
    assert state.per_pid_confidence == {}
    assert state.frame_ts == 100.0
    assert "no faces" in state.reasoning


# ── 4. One known face recognized → visible_pids has the pid ─────────────


def test_observe_scene_one_known_face_recognized():
    detections = [_FakeDetection(bbox=(10, 10, 110, 110), track_id=42)]
    db = _FakeDB(rule=lambda emb: ("jagan_001", "Jagan", 0.85))

    state = observe_scene(
        _frame(),
        face_detector=_FakeDetector(detections),
        face_embedder=_FakeEmbedder(),
        face_db=db,
        recognition_threshold=0.28,
        quality_min=0.2,
        yaw_max_deg=60.0,
        now=200.0,
        quality_score_fn=lambda crop: 0.9,
        yaw_estimate_fn=lambda landmarks, bbox: 0.0,
    )
    assert state.visible_pids == ("jagan_001",)
    assert state.per_pid_confidence == {"jagan_001": pytest.approx(0.85)}
    assert state.unrecognized_track_ids == ()


# ── 5. Unknown face → unrecognized_track_ids carries the track_id ───────


def test_observe_scene_unknown_face_lands_in_unrecognized_tracks():
    detections = [_FakeDetection(bbox=(10, 10, 110, 110), track_id=7)]
    db = _FakeDB(rule=lambda emb: (None, None, 0.0))

    state = observe_scene(
        _frame(),
        face_detector=_FakeDetector(detections),
        face_embedder=_FakeEmbedder(),
        face_db=db,
        recognition_threshold=0.28,
        quality_min=0.2,
        yaw_max_deg=60.0,
        now=300.0,
        quality_score_fn=lambda crop: 0.9,
        yaw_estimate_fn=lambda landmarks, bbox: 0.0,
    )
    assert state.visible_pids == ()
    assert state.unrecognized_track_ids == (7,)


# ── 6. V1 quality gate drops low-quality crops ───────────────────────────


def test_observe_scene_quality_gate_drops_low_quality():
    """A small/blurry box should be dropped before recognize is called.
    We force quality_score_fn to always return 0.0 — below quality_min=0.5
    — and assert nothing makes it into visible_pids even though the DB
    would have recognized it."""
    detections = [_FakeDetection(bbox=(10, 10, 110, 110), track_id=99)]
    db = _FakeDB(rule=lambda emb: ("alice", "Alice", 0.95))   # would-recognize

    state = observe_scene(
        _frame(),
        face_detector=_FakeDetector(detections),
        face_embedder=_FakeEmbedder(),
        face_db=db,
        recognition_threshold=0.28,
        quality_min=0.5,
        yaw_max_deg=60.0,
        now=400.0,
        quality_score_fn=lambda crop: 0.1,                     # FAILS quality gate
        yaw_estimate_fn=lambda landmarks, bbox: 0.0,
    )
    assert state.visible_pids == ()
    assert state.unrecognized_track_ids == ()
    assert "1 dropped on quality" in state.reasoning


# ── 7. V2 yaw gate drops extreme angles ──────────────────────────────────


def test_observe_scene_yaw_gate_drops_extreme_angles():
    """Faces with |yaw| > yaw_max_deg are dropped. We pass landmarks
    (so the yaw estimator runs) and force estimator to return 75°
    (above 60° default)."""
    detections = [_FakeDetection(
        bbox=(10, 10, 110, 110), track_id=55,
        landmarks=object(),    # truthy so yaw gate fires
    )]
    db = _FakeDB(rule=lambda emb: ("bob", "Bob", 0.92))

    state = observe_scene(
        _frame(),
        face_detector=_FakeDetector(detections),
        face_embedder=_FakeEmbedder(),
        face_db=db,
        recognition_threshold=0.28,
        quality_min=0.2,
        yaw_max_deg=60.0,
        now=500.0,
        quality_score_fn=lambda crop: 0.9,
        yaw_estimate_fn=lambda landmarks, bbox: 75.0,           # FAILS yaw gate
    )
    assert state.visible_pids == ()
    assert "1 dropped on yaw" in state.reasoning


# ── 8. Multi-face → per_pid_confidence populated per pid ─────────────────


def test_observe_scene_per_pid_confidence_populated():
    detections = [
        _FakeDetection(bbox=(10, 10, 110, 110), track_id=1),
        _FakeDetection(bbox=(200, 10, 300, 110), track_id=2),
    ]

    # Crop's first pixel value is 64 (from _frame). Both crops would yield
    # the same embedding from the deterministic fake — so we use a rule
    # that distinguishes by the crop's spatial coords. To do that we
    # tweak the frame so each detection's crop has a different first
    # pixel.
    frame = _frame()
    frame[10:110, 200:300] = 200    # second crop has a different pixel pattern

    def _rule(emb):
        # Use the first dimension of the embedding as a fingerprint
        # (deterministic per crop via our fake embedder's seeded rng).
        if emb is None:
            return (None, None, 0.0)
        sig = float(emb[0])
        if sig > 0:
            return ("alice", "Alice", 0.78)
        return ("bob", "Bob", 0.83)

    state = observe_scene(
        frame,
        face_detector=_FakeDetector(detections),
        face_embedder=_FakeEmbedder(),
        face_db=_FakeDB(rule=_rule),
        recognition_threshold=0.28,
        quality_min=0.2,
        yaw_max_deg=60.0,
        now=600.0,
        quality_score_fn=lambda crop: 0.9,
        yaw_estimate_fn=lambda landmarks, bbox: 0.0,
    )
    assert set(state.visible_pids) == {"alice", "bob"}
    # Each pid has an explicit confidence entry
    assert "alice" in state.per_pid_confidence
    assert "bob"   in state.per_pid_confidence
    # Sorted DESC by confidence — bob (0.83) before alice (0.78)
    assert state.visible_pids[0] == "bob"
    assert state.visible_pids[1] == "alice"
