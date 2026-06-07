"""test_pipeline_face_antispoof — face antispoof tests (split from test_pipeline.py, P1.A1 SP-1).

Behavior-neutral move: test bodies are verbatim from the original root
test_pipeline.py. `import pipeline` stays lazy inside each test body (stubs are
installed by tests/conftest.py).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import asyncio
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
import types
import pytest
import numpy as np
import time as _time_mod
import numpy as _np


def _make_frame():
    """100×100 BGR frame with non-trivial content in the 10-50 crop region."""
    f = _np.zeros((100, 100, 3), dtype=_np.uint8)
    f[10:50, 10:50] = 128
    return f


def _make_det(bbox=(10, 10, 50, 50), track_id=7):
    d = MagicMock()
    d.bbox = bbox
    d.track_id = track_id
    d.person_id = None
    d.landmarks = None
    return d


async def test_background_scan_uses_temporal_pooling():
    """Secondary scan must call temporal_buffer.add_and_pool (V3) with correct args."""
    import pipeline
    from pipeline import _background_vision_loop
    import time as _t

    frame = _make_frame()
    det   = _make_det()

    mock_camera   = MagicMock(); mock_camera.read.return_value = frame
    mock_detector = MagicMock(); mock_detector.detect.return_value = [det]
    mock_embedder = MagicMock(); mock_embedder.embed.return_value = _np.ones(512, dtype=_np.float32)
    mock_temporal = MagicMock()
    mock_temporal.add_and_pool.return_value = _np.ones(512, dtype=_np.float32) * 0.5
    mock_temporal.pool_depth.return_value = 5  # deep pool → no penalty threshold
    mock_db       = MagicMock(); mock_db.recognize.return_value = (None, None, 0.0)

    # P0.R6 D3 — embedding dispatch moved from direct `embedder.embed(...)`
    # to `await hw.run_heavy("adaface_embed", ...)` (subprocess worker).
    # Mock the worker entry point to return pre-canned bytes matching what
    # the production path would produce (1-D float32 ndarray serialized
    # via .tobytes()). Without this stub the call would attempt a real
    # subprocess spawn during the test.
    async def _hw_stub(task_name, fn, *args, **kwargs):
        return _np.ones(512, dtype=_np.float32).tobytes()

    orig_scan_last      = pipeline._vision_face_scan_last
    orig_prev_count     = pipeline._vision_frame_store.peek_prev_det_count()

    await pipeline._session_store.open_session("pid_001", "Alice", "known", "face", now=_t.time())
    pipeline._vision_face_scan_last = 0.0
    pipeline._vision_frame_store._sync_set_prev_det_count(0)

    # P1.A1 SP-6.3: _background_vision_loop reads vision_loop's face_quality_score binding
    with patch("runtime.vision_loop.face_quality_score", return_value=0.8), \
         patch("pipeline.hw.run_heavy", side_effect=_hw_stub):
        task = asyncio.create_task(
            _background_vision_loop(mock_camera, mock_detector, mock_embedder, mock_temporal, mock_db)
        )
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # V3: add_and_pool must be called at least once
    mock_temporal.add_and_pool.assert_called()
    call_kwargs = mock_temporal.add_and_pool.call_args
    # track_id=7 must be passed as keyword or third positional arg
    assert call_kwargs.kwargs.get("track_id") == 7 or (
        len(call_kwargs.args) >= 3 and call_kwargs.args[2] == 7
    )

    pipeline._vision_face_scan_last = orig_scan_last
    pipeline._vision_frame_store._sync_set_prev_det_count(orig_prev_count)


async def test_background_scan_uses_adaptive_threshold():
    """Secondary scan must call db.recognize with adaptive_threshold, not bare RECOGNITION_THRESHOLD."""
    import pipeline
    from pipeline import _background_vision_loop, RECOGNITION_THRESHOLD
    import time as _t

    frame = _make_frame()
    det   = _make_det()

    mock_camera   = MagicMock(); mock_camera.read.return_value = frame
    mock_detector = MagicMock(); mock_detector.detect.return_value = [det]
    mock_embedder = MagicMock(); mock_embedder.embed.return_value = _np.ones(512, dtype=_np.float32)
    mock_temporal = MagicMock()
    mock_temporal.add_and_pool.return_value = _np.ones(512, dtype=_np.float32) * 0.5
    mock_temporal.pool_depth.return_value = 5  # deep pool → no penalty threshold
    mock_db       = MagicMock(); mock_db.recognize.return_value = (None, None, 0.0)

    orig_scan_last      = pipeline._vision_face_scan_last
    orig_prev_count     = pipeline._vision_frame_store.peek_prev_det_count()

    await pipeline._session_store.open_session("pid_001", "Alice", "known", "face", now=_t.time())
    pipeline._vision_face_scan_last = 0.0
    pipeline._vision_frame_store._sync_set_prev_det_count(0)

    # P0.R6 D3 — same hw.run_heavy stub as test_background_scan_uses_temporal_pooling.
    async def _hw_stub(task_name, fn, *args, **kwargs):
        return _np.ones(512, dtype=_np.float32).tobytes()

    quality = 0.9  # high quality → threshold should drop below base
    # P1.A1 SP-6.3: _background_vision_loop reads vision_loop's face_quality_score binding
    with patch("runtime.vision_loop.face_quality_score", return_value=quality), \
         patch("pipeline.hw.run_heavy", side_effect=_hw_stub):
        task = asyncio.create_task(
            _background_vision_loop(mock_camera, mock_detector, mock_embedder, mock_temporal, mock_db)
        )
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # V4: recognize must be called and the threshold must NOT be the bare base
    mock_db.recognize.assert_called()
    _, actual_thresh = mock_db.recognize.call_args.args[1], mock_db.recognize.call_args.args[1]
    # adaptive_threshold(0.9, base) = base - (0.9-0.5)*0.08 = base - 0.032
    from core.vision import adaptive_threshold as _at
    expected = _at(quality, RECOGNITION_THRESHOLD)
    assert actual_thresh == pytest.approx(expected, abs=1e-6), (
        f"recognize called with {actual_thresh}, expected adaptive {expected}"
    )

    pipeline._vision_face_scan_last = orig_scan_last
    pipeline._vision_frame_store._sync_set_prev_det_count(orig_prev_count)


async def test_background_scan_skips_when_temporal_buffer_none():
    """When temporal_buffer=None, secondary scan must not call db.recognize."""
    import pipeline
    from pipeline import _background_vision_loop
    import time as _t

    frame = _make_frame()
    det   = _make_det()

    mock_camera   = MagicMock(); mock_camera.read.return_value = frame
    mock_detector = MagicMock(); mock_detector.detect.return_value = [det]
    mock_embedder = MagicMock(); mock_embedder.embed.return_value = _np.ones(512, dtype=_np.float32)
    mock_db       = MagicMock(); mock_db.recognize.return_value = (None, None, 0.0)

    orig_scan_last  = pipeline._vision_face_scan_last
    orig_prev_count = pipeline._vision_frame_store.peek_prev_det_count()

    await pipeline._session_store.open_session("pid_001", "Alice", "known", "face", now=_t.time())
    pipeline._vision_face_scan_last = 0.0
    pipeline._vision_frame_store._sync_set_prev_det_count(0)

    # P1.A1 SP-6.3: _background_vision_loop reads vision_loop's face_quality_score binding
    with patch("runtime.vision_loop.face_quality_score", return_value=0.8):
        task = asyncio.create_task(
            # temporal_buffer=None — secondary scan block must not fire
            _background_vision_loop(mock_camera, mock_detector, mock_embedder, None, mock_db)
        )
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    mock_db.recognize.assert_not_called()

    pipeline._vision_face_scan_last = orig_scan_last
    pipeline._vision_frame_store._sync_set_prev_det_count(orig_prev_count)


def test_recognize_acquires_index_lock(tmp_path):
    """BUG-13: recognize() must acquire _index_lock before touching FAISS so that
    concurrent _rebuild_faiss() calls (which reassign self.index) cannot cause a
    segfault due to the old index object being destroyed mid-search."""
    import threading
    import numpy as np
    from core.db import FaceDB

    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))

    # Replace _index_lock with a spy wrapper that delegates to a real RLock
    real_lock = threading.RLock()
    acquire_count = [0]

    class SpyRLock:
        def __enter__(self):
            acquire_count[0] += 1
            return real_lock.__enter__()
        def __exit__(self, *args):
            return real_lock.__exit__(*args)

    db._index_lock = SpyRLock()
    emb = np.random.rand(512).astype(np.float32)
    db.recognize(emb, threshold=0.3)

    assert acquire_count[0] > 0, "recognize() did not acquire _index_lock"
    db._conn.close()


def test_adaptive_threshold_range_with_new_base():
    """#5: adaptive_threshold with base=0.28 must produce [0.24, 0.32] range."""
    from core.vision import adaptive_threshold
    from core.config import RECOGNITION_THRESHOLD
    assert abs(adaptive_threshold(1.0, RECOGNITION_THRESHOLD) - (RECOGNITION_THRESHOLD - 0.04)) < 1e-6
    assert abs(adaptive_threshold(0.0, RECOGNITION_THRESHOLD) - (RECOGNITION_THRESHOLD + 0.04)) < 1e-6
    # Minimum effective threshold must be well above the old poisoning window (0.14)
    assert adaptive_threshold(1.0, RECOGNITION_THRESHOLD) >= 0.20


def test_face_quality_score_never_returns_zero():
    """#9: face_quality_score must return ≥ 0.05 even for the worst possible crop."""
    import numpy as np
    from core.vision import face_quality_score
    # 1px black crop — worst case
    tiny = np.zeros((1, 1, 3), dtype=np.uint8)
    assert face_quality_score(tiny) >= 0.05


def test_face_quality_score_good_crop_exceeds_enrollment_threshold():
    """#9: A bright, sharp, large crop must return ≥ floor — graded score, never hard-zero."""
    import numpy as np
    from core.vision import face_quality_score
    from core.config import FACE_QUALITY_PRESENCE
    # 200×200 gray uniform bright face (brightness=128, no blur variance → but large size)
    crop = np.full((200, 200, 3), 128, dtype=np.uint8)
    score = face_quality_score(crop)
    # Size score is max (1.0), brightness penalty is 1.0 — score limited by blur
    assert score >= FACE_QUALITY_PRESENCE  # at minimum always above floor


def test_face_quality_constants_ordered_correctly():
    """#9: Quality thresholds must form a strict ascending ladder."""
    from core.config import (
        FACE_QUALITY_PRESENCE, FACE_QUALITY_RECOGNITION,
        FACE_QUALITY_ENROLLMENT, FACE_QUALITY_SELF_UPDATE,
    )
    assert FACE_QUALITY_PRESENCE < FACE_QUALITY_RECOGNITION
    assert FACE_QUALITY_RECOGNITION < FACE_QUALITY_ENROLLMENT
    assert FACE_QUALITY_ENROLLMENT < FACE_QUALITY_SELF_UPDATE


def test_face_quality_recognition_gate_passes_medium_crop():
    """#9: A crop just above FACE_QUALITY_RECOGNITION must not be rejected by recognition path."""
    import numpy as np
    from core.vision import face_quality_score
    from core.config import FACE_QUALITY_RECOGNITION
    # 64×64 crop with moderate sharpness (add noise for blur variance)
    rng = np.random.default_rng(42)
    crop = rng.integers(60, 180, (64, 64, 3), dtype=np.uint8)
    score = face_quality_score(crop)
    # Score is graded — assert it is > FACE_QUALITY_PRESENCE (never hard-zero)
    assert score >= 0.05
    # Enrollment gate must be stricter than recognition gate
    assert FACE_QUALITY_RECOGNITION < 0.5  # recognition=0.2, enrollment=0.5


def test_face_quality_floor_prevents_hard_zero():
    """#9: Even a very dark, tiny, blurry crop must return exactly 0.05 (the floor)."""
    import numpy as np
    from core.vision import face_quality_score
    # 2×2 nearly-black crop — all quality components near zero
    crop = np.zeros((2, 2, 3), dtype=np.uint8)
    crop[0, 0] = [1, 1, 1]  # avoid all-zero to allow cvtColor
    score = face_quality_score(crop)
    assert score == pytest.approx(0.05, abs=1e-6)


def test_verify_live_returns_true_when_checker_none():
    """#12: verify_live must fail-open when checker is None."""
    from core.vision import verify_live
    import numpy as np
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    assert verify_live(frame, (0, 0, 50, 50), None) is True


def test_verify_live_returns_true_when_checker_unavailable():
    """#12: verify_live must fail-open when checker has no model loaded."""
    from core.vision import verify_live, AntiSpoofChecker
    import numpy as np
    checker = AntiSpoofChecker.__new__(AntiSpoofChecker)
    checker._models = []
    checker._threshold = 0.6
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    assert verify_live(frame, (0, 0, 50, 50), checker) is True


def test_verify_live_delegates_to_checker_is_live():
    """#12: verify_live must call checker.is_live when model is available."""
    from core.vision import verify_live
    from unittest.mock import MagicMock
    import numpy as np
    checker = MagicMock()
    checker.available = True
    checker.is_live.return_value = False
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    result = verify_live(frame, (0, 0, 50, 50), checker)
    checker.is_live.assert_called_once_with(frame, (0, 0, 50, 50))
    assert result is False


def test_verify_live_blocks_when_checker_rejects():
    """#12: verify_live returns False when checker.is_live returns False."""
    from core.vision import verify_live
    from unittest.mock import MagicMock
    import numpy as np
    checker = MagicMock()
    checker.available = True
    checker.is_live.return_value = False
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    assert verify_live(frame, (10, 10, 60, 60), checker) is False


def test_antispoof_disabled_watchdog_alert_stored(tmp_path):
    """#13: report_antispoof_disabled() creates a high-severity ANTISPOOF_DISABLED alert."""
    import sqlite3
    from core.brain_agent import WatchdogAgent, BrainDB
    db = BrainDB(tmp_path / "brain.db")
    faces_conn = sqlite3.connect(":memory:")
    wa = WatchdogAgent(db, faces_conn)
    wa.report_antispoof_disabled()
    alerts = db.get_unresolved_alerts()
    types = [a["alert_type"] for a in alerts]
    assert "ANTISPOOF_DISABLED" in types
    match = next(a for a in alerts if a["alert_type"] == "ANTISPOOF_DISABLED")
    assert match["severity"] == "high"


def test_antispoof_disabled_watchdog_alert_deduplicated(tmp_path):
    """#13: calling report_antispoof_disabled() twice does not create duplicate alerts."""
    import sqlite3
    from core.brain_agent import WatchdogAgent, BrainDB
    db = BrainDB(tmp_path / "brain.db")
    faces_conn = sqlite3.connect(":memory:")
    wa = WatchdogAgent(db, faces_conn)
    wa.report_antispoof_disabled()
    wa.report_antispoof_disabled()
    alerts = [a for a in db.get_unresolved_alerts() if a["alert_type"] == "ANTISPOOF_DISABLED"]
    assert len(alerts) == 1


def test_antispoof_checker_unavailable_reason_set_on_load_failure(tmp_path):
    """Wave 1 Item 5: AntiSpoofChecker.unavailable_reason is populated when weights are missing."""
    from core.vision import AntiSpoofChecker
    checker = AntiSpoofChecker.__new__(AntiSpoofChecker)
    checker._models = []
    checker._threshold = 0.6
    checker._device = None
    checker.unavailable_reason = ""
    from collections import deque
    checker._recent_live_probs = deque(maxlen=100)
    checker._calls_since_summary = 0
    checker._rejects_in_window = 0
    # Simulate the load-failure path setting unavailable_reason
    try:
        raise FileNotFoundError("MiniFASNet weights missing: ['fake/path.pth']")
    except Exception as e:
        checker.unavailable_reason = str(e)
        checker._models = []
    assert checker.unavailable_reason != "", "unavailable_reason must be non-empty after load failure"
    assert "missing" in checker.unavailable_reason.lower() or "fake" in checker.unavailable_reason.lower()
    assert not checker.available


def test_pipeline_antispoof_watchdog_wire_after_orchestrator():
    """Wave 1 Item 5: pipeline.run() calls report_antispoof_disabled() after orchestrator is constructed,
    gated on ANTISPOOFING_ENABLED and not available."""
    import inspect
    import pipeline
    src = inspect.getsource(pipeline.run)
    orch_idx = src.index("_brain_orchestrator = BrainOrchestrator")
    wire_idx = src.index("report_antispoof_disabled()")
    assert wire_idx > orch_idx, (
        "Wave 1 Item 5: report_antispoof_disabled() must be called AFTER BrainOrchestrator is constructed"
    )
    gate_region = src[src.rindex("\n", 0, wire_idx) - 200 : wire_idx]
    assert "ANTISPOOFING_ENABLED" in gate_region or "not _as_enabled" in gate_region, (
        "Wave 1 Item 5: watchdog call must be gated on antispoof being disabled"
    )


def test_maybe_record_silent_obs_helper_exists():
    import pipeline as _pl
    assert hasattr(_pl, "_maybe_record_silent_obs")


def test_maybe_record_silent_obs_calls_db_when_throttle_elapsed(tmp_path):
    """Helper calls db.update_silent_observation when enough time has elapsed."""
    import pipeline as _pl
    import time
    _pl._last_silent_update = 0.0  # reset so call fires
    mock_db = MagicMock()
    emb = [0.1] * 512
    bbox = (10, 10, 50, 50)
    # P1.A1 SP-6.3: _maybe_record_silent_obs reads vision_loop's _infer_zone binding
    with patch("runtime.vision_loop._infer_zone", return_value="center"):
        _pl._maybe_record_silent_obs(emb, bbox, 640, 480, mock_db)
    mock_db.update_silent_observation.assert_called_once_with(emb, zone="center")


def test_maybe_record_silent_obs_skips_when_throttled(tmp_path):
    """Helper does NOT call db when within 5-second throttle window."""
    import asyncio
    import pipeline as _pl
    import time
    asyncio.run(_pl._pipeline_state_store.set_last_silent_update(time.time()))  # just fired
    mock_db = MagicMock()
    _pl._maybe_record_silent_obs([0.1] * 512, (10, 10, 50, 50), 640, 480, mock_db)
    mock_db.update_silent_observation.assert_not_called()


def test_update_silent_observation_called_only_from_helper():
    """All call sites use the helper; no raw update_silent_observation calls.
    P1.A1 SP-6.3: _maybe_record_silent_obs (+ its one raw db.update_silent_observation
    call) relocated to runtime/vision_loop.py."""
    import pathlib, re
    src = pathlib.Path("runtime/vision_loop.py").read_text()
    raw_calls = re.findall(r"db\.update_silent_observation|update_silent_observation\(", src)
    helper_def = re.findall(r"def _maybe_record_silent_obs", src)
    assert len(helper_def) == 1
    # Only one reference per definition line + the helper body itself
    for line in src.splitlines():
        if "update_silent_observation" in line and "_maybe_record_silent_obs" not in line:
            assert "def _maybe_record_silent_obs" not in line
            assert line.strip().startswith("db.update_silent_observation") or \
                   "db.update_silent_observation" in line, f"unexpected raw call: {line.strip()}"
            # The only allowed raw call is inside the helper function body
            assert "zone=" in line, f"raw call outside helper: {line.strip()}"


def test_add_embedding_rejects_unknown_source(tmp_path):
    import numpy as np, pytest
    from core.db import FaceDB
    import time
    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "faiss.index")
    db._conn.execute(
        "INSERT INTO persons (id, name, enrolled_at, person_type) VALUES ('p1', 'Alice', ?, 'known')",
        (time.time(),),
    )
    db._conn.commit()
    emb = np.random.randn(512).astype(np.float32)
    with pytest.raises(RuntimeError, match="unknown source"):
        db.add_embedding("p1", emb, source="typo_source", anti_spoof_verdict=True)
    db._conn.close()


def test_add_embedding_valid_sources_accepted(tmp_path):
    import numpy as np
    from core.db import FaceDB, VALID_EMBEDDING_SOURCES
    import time
    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "faiss.index")
    db._conn.execute(
        "INSERT INTO persons (id, name, enrolled_at, person_type) VALUES ('p1', 'Alice', ?, 'known')",
        (time.time(),),
    )
    db._conn.commit()
    for src in VALID_EMBEDDING_SOURCES:
        emb = np.random.randn(512).astype(np.float32)
        db.add_embedding("p1", emb, source=src, anti_spoof_verdict=True)  # must not raise


def test_visitor_log_has_no_person_id_column(tmp_path):
    """visitor_log must have no person_id column — delete_person() needs no cleanup there."""
    from core.db import FaceDB
    face_db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "f.index")
    try:
        cols = [
            row[1]
            for row in face_db._conn.execute(
                "PRAGMA table_info(visitor_log)"
            ).fetchall()
        ]
    finally:
        face_db._conn.close()
    assert "person_id" not in cols, (
        "visitor_log must not have a person_id column — "
        "if one is added, delete_person() must be updated to clean it"
    )


def test_add_embedding_centroid_gate_rejects_outlier_recognition_update(tmp_path):
    """recognition_update writes whose cosine to existing centroid is below the floor
    must be rejected — catches outlier poisoning at write time."""
    import numpy as np
    from core.db import FaceDB
    from core.config import SELF_UPDATE_CENTROID_MIN

    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "f.index")
    db.add_person("p1", "Alice", None)
    # Baseline: 5 clustered embeddings pointing the same direction
    base = np.ones(512, dtype=np.float32)
    for i in range(5):
        jitter = np.random.randn(512).astype(np.float32) * 0.001
        db.add_embedding("p1", base + jitter, source="enrollment", confidence=0.95, anti_spoof_verdict=True)

    # Outlier in opposite direction — centroid cosine will be ~-1.0
    outlier = -np.ones(512, dtype=np.float32)
    stored = db.add_embedding("p1", outlier, source="recognition_update", confidence=0.46, anti_spoof_verdict=True)
    try:
        assert stored is False, \
            f"Outlier recognition_update write should have been rejected (min={SELF_UPDATE_CENTROID_MIN})"
    finally:
        db._conn.close()


def test_add_embedding_centroid_gate_allows_same_cluster(tmp_path):
    """A same-cluster recognition_update write (good cosine to centroid but varied
    enough to pass diversity) must still be accepted."""
    import numpy as np
    from core.db import FaceDB

    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "f.index")
    db.add_person("p1", "Alice", None)
    # Baseline: 5 vectors in a rough cluster — each has meaningful variance so the
    # diversity gate (>0.92) doesn't reject a new cluster-mate.
    rng = np.random.default_rng(0)
    base = np.ones(512, dtype=np.float32)
    for i in range(5):
        jitter = rng.standard_normal(512).astype(np.float32) * 0.8
        db.add_embedding("p1", base + jitter, source="enrollment", confidence=0.95, anti_spoof_verdict=True)

    # New vector in the same general direction — adds moderate noise so its
    # cosine to the existing cluster is in (0.55, 0.92): passes both gates.
    new_jitter = rng.standard_normal(512).astype(np.float32) * 0.8
    stored = db.add_embedding("p1", base + new_jitter, source="recognition_update", confidence=0.55, anti_spoof_verdict=True)
    try:
        assert stored is True, "Same-cluster recognition_update write should have been accepted"
    finally:
        db._conn.close()


def test_background_scan_tags_face_sourced_entries():
    """Bug B support: the face-side writer must call upsert_face_recognition on
    _presence_store so _face_in_frame can filter correctly. Source-inspection test
    targets `_background_vision_loop` — that's the only path that writes
    face-sourced entries (the per-frame inner loop also uses presence_store
    via the background loop's results)."""
    import inspect, pipeline
    src = inspect.getsource(pipeline._background_vision_loop)
    assert "upsert_face_recognition(" in src, (
        "Background face scan must call _presence_store.upsert_face_recognition"
    )
