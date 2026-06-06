"""test_pipeline_speaker_routing — speaker routing tests (split from test_pipeline.py, P1.A1 SP-1).

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
import runtime.wiring as _wiring


async def test_stranger_session_waits_for_name_by_default():
    """Face-detected stranger session has waiting_for_name=True and person_type='stranger'."""
    import pipeline
    import time as _t

    await pipeline._session_store.open_session("stranger_abc", "visitor", "stranger", "face", now=_t.time())
    await pipeline._session_store.set_waiting_for_name("stranger_abc", True)

    snap = pipeline._session_store.peek_snapshot("stranger_abc")
    assert snap.person_type == "stranger"
    assert snap.waiting_for_name is True


async def test_stranger_name_gate_activates_on_system_name():
    """When text contains system name, waiting_for_name is cleared."""
    import pipeline
    import time as _t

    await pipeline._session_store.open_session("stranger_001", "visitor", "stranger", "face", now=_t.time())
    await pipeline._session_store.set_waiting_for_name("stranger_001", True)
    await pipeline._pipeline_state_store.set_active_system_name("Rex")

    text = "Hey Rex, are you awake?"
    pid = "stranger_001"

    # Simulate the name gate logic (mirrors production _session_store read path)
    _snap_gate = pipeline._session_store.peek_snapshot(pid)
    if _snap_gate and _snap_gate.waiting_for_name:
        if pipeline._pipeline_state_store.peek_active_system_name().lower() in text.lower():
            await pipeline._session_store.set_waiting_for_name(pid, False)

    _snap_after = pipeline._session_store.peek_snapshot(pid)
    assert _snap_after is not None and not _snap_after.waiting_for_name

    await pipeline._pipeline_state_store.set_active_system_name("Dog")


async def test_stranger_name_gate_stays_silent_without_name():
    """When text does NOT contain system name, waiting_for_name remains True."""
    import pipeline
    import re
    import time as _t

    await pipeline._session_store.open_session("stranger_002", "visitor", "stranger", "face", now=_t.time())
    await pipeline._session_store.set_waiting_for_name("stranger_002", True)
    await pipeline._pipeline_state_store.set_active_system_name("Rex")

    pid = "stranger_002"
    name_pattern = r'\b' + re.escape(pipeline._pipeline_state_store.peek_active_system_name().lower()) + r'\b'

    # Name absent → no fire; gate does not clear waiting_for_name
    gate_fired = False
    for text in ["hello there, how are you doing today?", "I see a reflex in the mirror"]:
        if re.search(name_pattern, text.lower()):
            gate_fired = True
    assert gate_fired is False
    _snap_check = pipeline._session_store.peek_snapshot(pid)
    assert _snap_check is not None and _snap_check.waiting_for_name is True

    # Word-boundary: "reflex" must NOT match "rex"
    await pipeline._pipeline_state_store.set_active_system_name("rex")
    name_pattern2 = r'\b' + re.escape("rex") + r'\b'
    assert not re.search(name_pattern2, "reflex is a thing")
    assert re.search(name_pattern2, "hey rex, wake up")

    await pipeline._pipeline_state_store.set_active_system_name("Dog")


def test_unrecognized_tracks_pruned_after_scene_stale_secs():
    """Stale entries (> SCENE_STALE_SECS old) are removed from _unrecognized_tracks by decay logic."""
    import pipeline
    import time
    from core.config import SCENE_STALE_SECS

    import asyncio
    stale_ts = time.time() - (SCENE_STALE_SECS + 1.0)
    asyncio.run(pipeline._track_store.mark_unrecognized(42, stale_ts))
    asyncio.run(pipeline._track_store.mark_unrecognized(99, time.time()))
    _bv_scan_now = time.time()
    asyncio.run(pipeline._track_store.prune_stale(_bv_scan_now - SCENE_STALE_SECS))
    assert 42 not in pipeline._track_store   # stale → pruned
    assert 99 in pipeline._track_store        # fresh → kept


def test_unrecognized_tracks_populated_with_track_id():
    """Secondary scan else-branch adds track_id to _track_store."""
    import asyncio, pipeline, time
    _bv_scan_now = time.time()
    # Simulate the else-branch logic for track_id=42
    _tid = 42
    asyncio.run(pipeline._track_store.mark_unrecognized(_tid, _bv_scan_now))
    assert 42 in pipeline._track_store
    assert abs(pipeline._track_store.peek_last_seen(42) - _bv_scan_now) < 0.01


def test_stranger_track_map_binds_single_track_to_new_session():
    """With exactly 1 unrecognized track, routing creates a session and maps track -> session."""
    import asyncio, pipeline, time
    orig_sys_name  = pipeline._pipeline_state_store.peek_active_system_name()

    asyncio.run(pipeline._session_store.open_session("p1", "Jagan", "known", "face", now=0.0))
    asyncio.run(pipeline._conversation_store.set_history("p1", []))
    asyncio.run(pipeline._track_store.mark_unrecognized(42, time.time()))  # one fresh track
    asyncio.run(pipeline._pipeline_state_store.set_active_system_name("Rex"))

    # Execute new_stranger routing logic (inline mirror of pipeline routing block)
    from core.config import VOICE_ROUTING_FACE_STALE_SECS, STRANGER_REQUIRE_SYSTEM_NAME
    import uuid as _uuid_mod

    _now_route   = time.time()
    _active_unrec = {
        tid: pipeline._track_store.peek_last_seen(tid)
        for tid in pipeline._track_store.peek_active_unrecognized()
        if _now_route - pipeline._track_store.peek_last_seen(tid) < VOICE_ROUTING_FACE_STALE_SECS
    }
    _speaker_track = next(iter(_active_unrec)) if len(_active_unrec) == 1 else None
    _target_sid    = pipeline._track_store.peek_stranger_pid(_speaker_track) if _speaker_track is not None else None

    assert _target_sid is None  # no existing mapping yet

    _sid = f"stranger_{_uuid_mod.uuid4().hex[:8]}"
    asyncio.run(pipeline._session_store.open_session(_sid, "visitor", "stranger", "voice", now=_now_route))
    asyncio.run(pipeline._conversation_store.set_history(_sid, []))
    if _speaker_track is not None:
        asyncio.run(pipeline._track_store.mint_stranger(_speaker_track, _sid))

    assert pipeline._track_store.peek_stranger_pid(_speaker_track) is not None
    assert pipeline._track_store.peek_stranger_pid(_speaker_track).startswith("stranger_")

    asyncio.run(pipeline._pipeline_state_store.set_active_system_name(orig_sys_name))


def test_stranger_track_map_resumes_existing_session():
    """Same SORT track speaks again → routing reuses the previously bound session."""
    import asyncio, pipeline, time
    from core.config import VOICE_ROUTING_FACE_STALE_SECS

    asyncio.run(pipeline._session_store.open_session("p1", "Jagan", "known", "face", now=0.0))
    asyncio.run(pipeline._session_store.open_session(
        "stranger_abc", "visitor", "stranger", "voice", now=time.time() - 5.0
    ))
    asyncio.run(pipeline._track_store.mark_unrecognized(42, time.time()))   # track 42 is active
    asyncio.run(pipeline._track_store.mint_stranger(42, "stranger_abc"))     # already bound

    _now_route    = time.time()
    _active_unrec = {
        tid: pipeline._track_store.peek_last_seen(tid)
        for tid in pipeline._track_store.peek_active_unrecognized()
        if _now_route - pipeline._track_store.peek_last_seen(tid) < VOICE_ROUTING_FACE_STALE_SECS
    }
    _speaker_track = next(iter(_active_unrec)) if len(_active_unrec) == 1 else None
    _target_sid    = pipeline._track_store.peek_stranger_pid(_speaker_track) if _speaker_track is not None else None

    assert _target_sid == "stranger_abc"
    assert pipeline._session_store.peek_snapshot(_target_sid) is not None


def test_two_unrecognized_tracks_routes_to_most_recent_stranger():
    """With 2 unrecognized tracks (ambiguous), routing reuses most recently active voice stranger."""
    import asyncio, pipeline, time
    from core.config import VOICE_ROUTING_FACE_STALE_SECS

    t_now = time.time()
    asyncio.run(pipeline._session_store.open_session(
        "stranger_abc", "visitor", "stranger", "voice", now=t_now - 3.0
    ))
    asyncio.run(pipeline._track_store.mark_unrecognized(1, t_now))  # 2 tracks — ambiguous
    asyncio.run(pipeline._track_store.mark_unrecognized(2, t_now))

    _now_route    = time.time()
    _active_unrec = {
        tid: pipeline._track_store.peek_last_seen(tid)
        for tid in pipeline._track_store.peek_active_unrecognized()
        if _now_route - pipeline._track_store.peek_last_seen(tid) < VOICE_ROUTING_FACE_STALE_SECS
    }
    _speaker_track = next(iter(_active_unrec)) if len(_active_unrec) == 1 else None
    assert _speaker_track is None  # 2 tracks → ambiguous → no definitive speaker

    _candidate = max(
        (s.person_id for s in pipeline._session_store.peek_all_snapshots()
         if s.person_id.startswith("stranger_") and s.session_type == "voice"),
        key=lambda pid: pipeline._session_store.peek_snapshot(pid).last_spoke_at,
        default=None,
    ) if len(_active_unrec) > 1 else None

    assert _candidate == "stranger_abc"


def test_two_unrecognized_tracks_creates_new_session_when_none_exist():
    """With 2 unrecognized tracks and no stranger sessions, routing creates a new one."""
    import asyncio, pipeline, time
    from core.config import VOICE_ROUTING_FACE_STALE_SECS

    t_now = time.time()
    # store is already empty via autouse _reset_pipeline_state_between_tests
    asyncio.run(pipeline._track_store.mark_unrecognized(1, t_now))
    asyncio.run(pipeline._track_store.mark_unrecognized(2, t_now))

    _now_route    = time.time()
    _active_unrec = {
        tid: pipeline._track_store.peek_last_seen(tid)
        for tid in pipeline._track_store.peek_active_unrecognized()
        if _now_route - pipeline._track_store.peek_last_seen(tid) < VOICE_ROUTING_FACE_STALE_SECS
    }
    _candidate = max(
        (s.person_id for s in pipeline._session_store.peek_all_snapshots()
         if s.person_id.startswith("stranger_") and s.session_type == "voice"),
        key=lambda pid: pipeline._session_store.peek_snapshot(pid).last_spoke_at,
        default=None,
    ) if len(_active_unrec) > 1 else None

    assert _candidate is None  # no existing stranger sessions → must create new


def test_primary_person_id_tie_breaks_by_pid():
    """BUG-5: When two sessions have identical last_spoke_at, the lexicographically
    larger pid must be returned (deterministic secondary sort key)."""
    import asyncio
    import pipeline
    from core.session_state import SessionStore

    orig = pipeline._session_store
    store = SessionStore()
    ts = 1000.0
    asyncio.run(store.open_session("alice", "Alice", "known", "face", now=ts))
    asyncio.run(store.open_session("bob", "Bob", "known", "face", now=ts))
    _wiring._session_store = store
    try:
        result = pipeline._primary_person_id()
    finally:
        _wiring._session_store = orig

    assert result == "bob"   # "bob" > "alice" lexicographically


def test_primary_person_id_no_tie_uses_recency():
    """BUG-5 regression: without a tie, the session with the highest last_spoke_at wins
    regardless of pid lexicographic order."""
    import asyncio
    import pipeline
    from core.session_state import SessionStore

    orig = pipeline._session_store
    store = SessionStore()
    asyncio.run(store.open_session("zzz", "Zzz", "known", "face", now=100.0))
    asyncio.run(store.open_session("aaa", "Aaa", "known", "face", now=200.0))
    _wiring._session_store = store
    try:
        result = pipeline._primary_person_id()
    finally:
        _wiring._session_store = orig

    assert result == "aaa"   # newer timestamp wins over lexicographic order


def test_last_raw_pruned_when_track_disappears():
    """BUG-8: When SORT stops reporting a track_id, _last_raw must evict that entry
    immediately so stale landmarks are never served on subsequent predict frames."""
    from unittest.mock import MagicMock, patch
    import numpy as np
    from core.vision import FaceDetector, Detection

    fd = FaceDetector.__new__(FaceDetector)
    fd._sort = MagicMock()
    fd._frame_count  = 0
    fd._detect_every = 5
    fd._last_raw = {
        42: Detection(bbox=(0,0,100,100), confidence=0.9, landmarks=None, track_id=42),
        99: Detection(bbox=(200,0,300,100), confidence=0.8, landmarks=None, track_id=99),
    }
    saved_det_99 = fd._last_raw[99]
    # SORT returns only track 99 — track 42 is dead
    fd._sort.update.return_value = np.array([[200, 0, 300, 100, 99]], dtype=np.float32)

    # Patch the output-building section to avoid frame/model dependency
    with patch.object(fd, "_run_detection", return_value=(np.empty((0,5)), [])), \
         patch.object(fd, "_match_tracks_to_raws", return_value={99: saved_det_99}):
        fd.detect(np.zeros((480,640,3), dtype=np.uint8))

    assert 42 not in fd._last_raw    # dead track evicted
    assert 99 in fd._last_raw        # active track preserved


def test_last_raw_keeps_active_tracks():
    """BUG-8 regression: track_ids still returned by SORT must remain in _last_raw."""
    from unittest.mock import MagicMock, patch
    import numpy as np
    from core.vision import FaceDetector, Detection

    fd = FaceDetector.__new__(FaceDetector)
    fd._sort = MagicMock()
    fd._frame_count  = 0
    fd._detect_every = 5
    original_det = Detection(bbox=(0,0,100,100), confidence=0.9, landmarks=None, track_id=7)
    fd._last_raw = {7: original_det}
    # SORT returns track 7 still active
    fd._sort.update.return_value = np.array([[0, 0, 100, 100, 7]], dtype=np.float32)

    with patch.object(fd, "_run_detection", return_value=(np.empty((0,5)), [])), \
         patch.object(fd, "_match_tracks_to_raws", return_value={7: original_det}):
        fd.detect(np.zeros((480,640,3), dtype=np.uint8))

    assert 7 in fd._last_raw         # still active — must not be evicted


def test_ambient_wake_pending_flag_set_on_first_wake():
    """Background loop sets ambient wake when it calls stop_audio."""
    import asyncio, pipeline, time
    from pipeline import GREET_COOLDOWN
    pipeline._per_person_agent_store.reset()
    last_greeted = {}

    stop_calls = []

    def fake_stop():
        stop_calls.append(1)
        # Simulate: after first call, flag is already set (no second fire)
        asyncio.run(pipeline._per_person_agent_store.add_ambient_wake("p1"))

    _pid = "p1"
    condition_met = (
        _pid
        and time.time() - last_greeted.get(_pid, 0) >= GREET_COOLDOWN
        and not pipeline._per_person_agent_store.is_ambient_wake_pending(_pid)
    )
    if condition_met:
        asyncio.run(pipeline._per_person_agent_store.add_ambient_wake(_pid))
        fake_stop()

    assert len(stop_calls) == 1
    assert pipeline._per_person_agent_store.is_ambient_wake_pending("p1")


def test_ambient_wake_pending_blocks_second_fire():
    """Once ambient wake contains a pid, a second wake for same pid is suppressed."""
    import asyncio, pipeline, time
    from pipeline import GREET_COOLDOWN
    pipeline._per_person_agent_store.reset()
    asyncio.run(pipeline._per_person_agent_store.add_ambient_wake("p1"))
    last_greeted = {}

    stop_calls = []
    _pid = "p1"
    condition_met = (
        _pid
        and time.time() - last_greeted.get(_pid, 0) >= GREET_COOLDOWN
        and not pipeline._per_person_agent_store.is_ambient_wake_pending(_pid)
    )
    if condition_met:
        stop_calls.append(1)

    assert len(stop_calls) == 0, "Second fire must be suppressed by ambient wake store"


def test_ambient_wake_pending_cleared_before_antispoof_blocked():
    """discard_ambient_wake() before anti-spoof check clears the flag even on block."""
    import asyncio, pipeline
    pipeline._per_person_agent_store.reset()
    asyncio.run(pipeline._per_person_agent_store.add_ambient_wake("p1"))

    person_id = "p1"
    asyncio.run(pipeline._per_person_agent_store.discard_ambient_wake(person_id))
    # Anti-spoof blocks (continue) — but flag is already cleared

    assert not pipeline._per_person_agent_store.is_ambient_wake_pending("p1")


def test_ambient_wake_pending_cleared_on_successful_greeting():
    """discard_ambient_wake() clears flag before successful greeting continues."""
    import asyncio, pipeline
    pipeline._per_person_agent_store.reset()
    asyncio.run(pipeline._per_person_agent_store.add_ambient_wake("p1"))

    person_id = "p1"
    asyncio.run(pipeline._per_person_agent_store.discard_ambient_wake(person_id))

    assert not pipeline._per_person_agent_store.is_ambient_wake_pending("p1")


def test_ambient_wake_pending_per_person_independent():
    """Flag for p1 does not suppress wake for a different person p2."""
    import asyncio, pipeline, time
    from pipeline import GREET_COOLDOWN
    pipeline._per_person_agent_store.reset()
    asyncio.run(pipeline._per_person_agent_store.add_ambient_wake("p1"))
    last_greeted = {}

    stop_calls = []
    _pid = "p2"   # different person
    condition_met = (
        _pid
        and time.time() - last_greeted.get(_pid, 0) >= GREET_COOLDOWN
        and not pipeline._per_person_agent_store.is_ambient_wake_pending(_pid)
    )
    if condition_met:
        asyncio.run(pipeline._per_person_agent_store.add_ambient_wake(_pid))
        stop_calls.append(1)

    assert len(stop_calls) == 1, "p2 wake must fire even when p1 is pending"
    assert pipeline._per_person_agent_store.is_ambient_wake_pending("p2")
    assert pipeline._per_person_agent_store.is_ambient_wake_pending("p1")  # p1 unchanged


def test_switch_enrolled_sets_person_type_known():
    """After switch_enrolled opens a new session, person_type is fetched from
    DB via get_person_type and passed as person_type=_switched_pt to _open_session."""
    import inspect, pipeline
    src = inspect.getsource(pipeline)
    # P0.7.4: dual-write _active_sessions[pid]["person_type"] = "known" deleted.
    # New pattern: db.get_person_type(_resolved_pid) + person_type=_switched_pt
    assert "get_person_type(_resolved_pid)" in src, \
        "switch_enrolled must call db.get_person_type(_resolved_pid) for person_type"
    assert "person_type=_switched_pt" in src, \
        "switch_enrolled must pass person_type=_switched_pt to _open_session"


def test_switch_enrolled_rebuilds_voice_state():
    """After switch_enrolled, voice_state must be rebuilt with matches_active=True."""
    import inspect, pipeline
    src = inspect.getsource(pipeline)
    # The fix: after switch, voice_state is rebuilt with "matches_active": True
    assert '"matches_active":' in src and 'True' in src, \
        "switch_enrolled must rebuild voice_state with matches_active=True"


def test_switch_enrolled_invalidates_query_embedding_cache():
    """After switch_enrolled, stale query embedding must be evicted from cache."""
    import inspect, pipeline
    src = inspect.getsource(pipeline)
    # The fix: _query_embedding_cache.pop(resolved_pid, None) after switch
    assert "_query_embedding_store.discard(_resolved_pid)" in src, \
        "switch_enrolled must evict stale query embedding cache for switched-to person"


def test_switch_enrolled_voice_state_has_correct_structure():
    """The rebuilt voice_state for switch_enrolled must have all required keys."""
    import inspect, pipeline
    src = inspect.getsource(pipeline)
    # Verify the rebuilt voice_state dict contains all expected keys
    # (matched_id, matched_name, voice_confidence, matches_active)
    assert '"matched_id":' in src and '"matched_name":' in src, \
        "Rebuilt voice_state must include matched_id and matched_name"


def test_track_identity_set_on_recognition():
    """#4: Successful recognition must store track_id → person_id in _track_identity."""
    import pipeline
    pipeline._track_identity = {}
    # Simulate: FAISS recognizes track 7 as "jagan_001"
    pipeline._track_identity[7] = "jagan_001"
    assert pipeline._track_identity.get(7) == "jagan_001"


def test_track_continuity_restores_identity_for_known_track():
    """#4: When recognition fails but track was previously identified, identity is restored."""
    import asyncio, pipeline, time as _t
    asyncio.run(pipeline._session_store.open_session("jagan_001", "Jagan", "best_friend", "face", now=_t.time()))
    pipeline._track_identity = {7: "jagan_001"}
    # Simulate: recognition returns None (below threshold) for track 7
    person_id = None
    tracked_pid = pipeline._track_identity.get(7)
    if tracked_pid and pipeline._session_store.peek_snapshot(tracked_pid) is not None:
        person_id = tracked_pid
    assert person_id == "jagan_001"


def test_track_continuity_does_not_fire_for_unknown_track():
    """#4: A new track with no prior identity must NOT inherit any person — no soft-match."""
    import pipeline
    pipeline._track_identity = {}  # empty — stranger's brand-new track
    # Simulate: recognition returns None for a new track (tid=99)
    person_id = None
    tracked_pid = pipeline._track_identity.get(99)
    if tracked_pid and pipeline._session_store.peek_snapshot(tracked_pid) is not None:
        person_id = tracked_pid
    # Stranger should NOT be assigned to Jagan's identity
    assert person_id is None


def test_self_update_skipped_for_track_continuity_restoration():
    """#4: Gallery write must NOT fire when identity came from track-continuity (below-threshold)."""
    # The directly_recognized flag must be False for track-continuity restorations.
    # We verify the logic: conf < threshold means directly_recognized=False → no self-update.
    import pipeline
    from core.config import RECOGNITION_THRESHOLD, SELF_UPDATE_THRESHOLD

    # Simulate: conf is 0.15 (below RECOGNITION_THRESHOLD) — track-continuity path
    conf = RECOGNITION_THRESHOLD - 0.05
    directly_recognized = conf >= RECOGNITION_THRESHOLD
    should_self_update = directly_recognized and conf >= SELF_UPDATE_THRESHOLD
    assert should_self_update is False  # gallery write must be blocked


def test_self_update_threshold_above_recognition_threshold():
    """#5: SELF_UPDATE_THRESHOLD must be > RECOGNITION_THRESHOLD to prevent poisoning."""
    from core.config import RECOGNITION_THRESHOLD, SELF_UPDATE_THRESHOLD
    assert SELF_UPDATE_THRESHOLD > RECOGNITION_THRESHOLD, (
        f"SELF_UPDATE_THRESHOLD={SELF_UPDATE_THRESHOLD} ≤ RECOGNITION_THRESHOLD={RECOGNITION_THRESHOLD} — "
        "gallery updates can fire on low-confidence matches and corrupt the gallery"
    )


def test_name_heard_in_exact_match():
    """#14: _name_heard_in returns True on exact word-boundary match."""
    from pipeline import _name_heard_in
    heard, method = _name_heard_in("Hey Kara can you help", "Kara")
    assert heard is True
    assert method == "exact"


def test_name_heard_in_phonetic_match():
    """#14: _name_heard_in returns True for a phonetic variant (Cara ≈ Kara via Metaphone)."""
    from pipeline import _name_heard_in
    heard, method = _name_heard_in("Hey Cara are you there", "Kara")
    assert heard is True
    assert method == "phonetic"


def test_name_heard_in_no_match():
    """#14: _name_heard_in returns False when neither exact nor phonetic match."""
    from pipeline import _name_heard_in
    heard, method = _name_heard_in("What time is it", "Kara")
    assert heard is False
    assert method == ""


def test_ambient_gate_uses_name_heard_in_for_phonetic():
    """#14: Ambient path gate (_name_heard_in) accepts phonetic variants, not just exact text."""
    from pipeline import _name_heard_in
    # "Rex" system name — "Recks" is phonetically identical (both map to RS metaphone)
    heard, _ = _name_heard_in("Hey Recks what is the time", "Rex")
    assert heard is True


def test_name_heard_in_no_substring_false_positive():
    """#14: _name_heard_in must not fire on substrings — 'Rex' must not match 'reflex'."""
    from pipeline import _name_heard_in
    heard, _ = _name_heard_in("this is a reflex action", "Rex")
    assert heard is False


def test_ambient_gate_blocks_camera_when_name_not_heard():
    """#15: If system name not spoken, camera fallback must NOT open a session."""
    import pipeline
    # _name_heard_in("hello there", "Kara") → (False, ...)
    heard, _ = pipeline._name_heard_in("hello there", "Kara")
    assert heard is False, "Precondition: system name not in text"


def test_ambient_gate_passes_when_name_heard():
    """#15: If system name is spoken, gate passes and session CAN be opened."""
    import pipeline
    heard, _ = pipeline._name_heard_in("hey Kara what time is it", "Kara")
    assert heard is True


def test_ambient_gate_phonetic_passes():
    """#15: Phonetic variant of system name passes the gate."""
    import pipeline
    heard, _ = pipeline._name_heard_in("cara can you help me", "Kara")
    assert heard is True


async def test_ambient_known_voice_bypasses_gate():
    """#15: Known-voice match bypasses the gate entirely — session opens regardless."""
    import pipeline, tempfile, pathlib
    from core.db import FaceDB
    with tempfile.TemporaryDirectory() as td:
        db = FaceDB(pathlib.Path(td) / "faces.db")
        try:
            pid = db.add_person("Jagan", "jagan")
            pipeline._open_session(pid, "Jagan", "voice", person_type="known")
            await asyncio.sleep(0)
            assert pipeline._session_store.peek_snapshot(pid) is not None
            pipeline._close_session(pid)
            await asyncio.sleep(0)
        finally:
            db._conn.close()


def test_stranger_track_pre_allocated_on_unrecognized_scan():
    """#20: _track_store.mint_stranger must be called for each SORT-confirmed unrecognized track."""
    import pipeline, inspect
    src = inspect.getsource(pipeline._background_vision_loop)
    # The pre-allocation happens inside the background vision loop's else-branch
    assert "_track_store.mint_stranger(" in src, \
        "Background vision scan must pre-allocate stranger pid via _track_store.mint_stranger"


def test_new_stranger_multi_track_picks_most_recent():
    """#20: With 2+ unrecognized tracks, pick the most-recently-seen track (not arbitrary session)."""
    import pipeline, time, inspect
    src = inspect.getsource(pipeline)
    # The new multi-track logic uses max() on the timestamps
    assert "max(_active_unrec" in src, \
        "Multi-track new_stranger must use max(_active_unrec) to pick most-recently-seen track"


def test_new_stranger_uses_preallocated_pid():
    """#20: When a pre-allocated pid exists in _track_store, the session uses it."""
    import asyncio, pipeline, time
    now = time.time()
    pre_pid = "stranger_prealloc12"
    asyncio.run(pipeline._track_store.mark_unrecognized(42, now))
    asyncio.run(pipeline._track_store.mint_stranger(42, pre_pid))
    # Verify that _target_sid lookup finds the pre-allocated pid
    _target = pipeline._track_store.peek_stranger_pid(42)
    assert _target == pre_pid


async def test_drift_detection_records_attribution():
    """#21: After routing, the attribution action must be appended to recent_attributions."""
    import pipeline, tempfile, pathlib
    from core.db import FaceDB
    with tempfile.TemporaryDirectory() as td:
        db = FaceDB(pathlib.Path(td) / "faces.db")
        try:
            pid = db.add_person("Jagan", "jagan")
            pipeline._open_session(pid, "Jagan", "face", person_type="known")
            await asyncio.sleep(0)
            await pipeline._session_store.record_attribution(pid, "current")
            snap = pipeline._session_store.peek_snapshot(pid)
            assert snap is not None
            assert list(snap.recent_attributions) == ["current"]
            pipeline._close_session(pid)
            await asyncio.sleep(0)
        finally:
            db._conn.close()


def test_ambient_fallback_no_unconditional_break():
    """Ambient camera fallback must scan all faces for best match, not break on first."""
    import ast, pathlib
    src = pathlib.Path("pipeline.py").read_text()
    # The old pattern was: for _d in detector.detect(cam_f): ... break (unconditional)
    # New pattern: _best_pid, _best_conf = None, 0.0 loop, open after loop
    assert "_best_pid" in src and "_best_conf" in src, "best-match variables not found"


def test_ambient_fallback_selects_higher_confidence_face():
    """Ambient fallback opens session for the highest-confidence recognized face."""
    import pipeline as _pl
    from unittest.mock import MagicMock, patch
    import time

    # Two detections: first has lower conf, second has higher conf
    det_low = MagicMock(); det_low.bbox = (10, 10, 50, 50)
    det_high = MagicMock(); det_high.bbox = (60, 10, 100, 50)

    mock_cam = MagicMock()
    mock_cam.__bool__ = lambda s: True
    mock_cam.shape = (480, 640, 3)

    mock_detector = MagicMock()
    mock_detector.detect.return_value = [det_low, det_high]

    mock_embedder = MagicMock()
    mock_embedder.embed.side_effect = lambda crop: [0.1] * 512

    mock_db = MagicMock()
    # First call returns low conf, second returns high conf
    mock_db.recognize.side_effect = [
        ("pid_low", "Alice", 0.30),
        ("pid_high", "Bob", 0.55),
    ]

    opened = {}
    def fake_open(pid, name, stype, **kw):
        opened["pid"] = pid

    import numpy as np
    with patch.object(_pl, "verify_live", return_value=True), \
         patch.object(_pl, "_open_session", side_effect=fake_open):
        # Simulate the best-match logic directly
        best_pid, best_pname, best_conf = None, None, 0.0
        for _d in [det_low, det_high]:
            crop = np.zeros((40, 40, 3), dtype=np.uint8)
            emb = mock_embedder.embed(crop)
            pid, pname, conf = mock_db.recognize(emb, 0.28)
            if pid and conf > best_conf:
                best_pid, best_pname, best_conf = pid, pname, conf
        assert best_pid == "pid_high"
        assert best_conf == 0.55


def test_self_update_threshold_raised_to_045():
    """Gallery write gate must be at least 0.45 so only clearly-confident matches update."""
    from core.config import SELF_UPDATE_THRESHOLD, RECOGNITION_THRESHOLD
    assert SELF_UPDATE_THRESHOLD >= 0.45, \
        f"SELF_UPDATE_THRESHOLD {SELF_UPDATE_THRESHOLD} too low — marginal matches will poison gallery"
    assert SELF_UPDATE_THRESHOLD > RECOGNITION_THRESHOLD, \
        "SELF_UPDATE_THRESHOLD must exceed RECOGNITION_THRESHOLD (the invariant must hold)"


async def test_switch_enrolled_uses_db_person_type():
    """Problem B (switch_enrolled path, pipeline.py ~3170): when a voice match
    opens a session for an enrolled person, the person_type must be fetched from
    the DB — not hardcoded 'known' — so best_friend doesn't silently downgrade
    when they speak offscreen. Uses a mock db so the test doesn't need real faces.db."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.run)
    # Old bug: `_active_sessions[_resolved_pid]["person_type"] = "known"`
    # Fixed: uses `db.get_person_type(_resolved_pid)`.
    assert "db.get_person_type(_resolved_pid)" in src, (
        "switch_enrolled branch must fetch person_type from DB, not hardcode 'known'"
    )


def test_face_assist_floor_invariant():
    """Bug O invariant: the face-assist floor sits strictly between the
    mid-range switch minimum and the full switch threshold. If someone tunes
    one without the others, this test fails and flags the inconsistency."""
    from core.config import (
        VOICE_ROUTING_MIDRANGE_SWITCH_MIN,
        VOICE_ROUTING_FACE_ASSIST_MIN,
        VOICE_SPEAKER_SWITCH_THRESHOLD,
    )
    assert VOICE_ROUTING_MIDRANGE_SWITCH_MIN < VOICE_ROUTING_FACE_ASSIST_MIN, (
        f"FACE_ASSIST_MIN ({VOICE_ROUTING_FACE_ASSIST_MIN}) must exceed "
        f"MIDRANGE_SWITCH_MIN ({VOICE_ROUTING_MIDRANGE_SWITCH_MIN}) — otherwise "
        f"the face-assist gate is equal to or weaker than the raw mid-range floor"
    )
    assert VOICE_ROUTING_FACE_ASSIST_MIN < VOICE_SPEAKER_SWITCH_THRESHOLD, (
        f"FACE_ASSIST_MIN ({VOICE_ROUTING_FACE_ASSIST_MIN}) must be below the "
        f"full switch threshold ({VOICE_SPEAKER_SWITCH_THRESHOLD}) — if "
        f"face-assist is already at-or-above the switch threshold, Priority 1 "
        f"fires first and Priority 2 never matters"
    )


def test_switch_enrolled_writes_voice_match_conf_to_fresh_session():
    """Session 90 Bug 1 Fix B: when routing returns ``switch_enrolled`` and
    the resolved pid's prior session had expired (so the upstream
    ``_v_pid in _active_sessions`` guard skipped the
    ``voice_match_conf`` write), the switch_enrolled branch must write
    ``voice_match_conf=_v_score`` to the newly-opened session's
    ``identity_evidence`` BEFORE ``_accumulate_voice`` reads it at
    ~line 4752. Without this, a mature speaker (voice_n=20) sees
    ``voice_conf=0.00`` in Path B and accumulation refuses despite a real
    routing score — observed for Jagan re-entering after John's session
    expired in the 2026-04-22 multi-convo run."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.run)
    idx = src.find('if _routing_action == "switch_enrolled":')
    assert idx > -1, "switch_enrolled branch must exist"
    # Scan the branch body (up to the next elif) for the evidence write.
    next_elif = src.find('elif _routing_action ==', idx + 1)
    assert next_elif > idx, "branch bounded by the next elif"
    body = src[idx:next_elif]
    assert "update_voice_heard(" in body, (
        "Session 90 Bug 1 Fix B: switch_enrolled must call "
        "update_voice_heard on the resolved pid"
    )
    # Specifically the conf field — the exact column read by
    # _voice_accum_allowed Path B.
    assert "conf=_v_score" in body, (
        "Session 90 Bug 1 Fix B: switch_enrolled must write conf=_v_score "
        "from the routing score so Path B can fire on the re-entry turn"
    )
    # And ts — drives Path B's staleness check AND the
    # dispute auto-clear Bug D1 deque.
    assert "ts=time.monotonic()" in body, (
        "switch_enrolled must also bump ts (monotonic per #5 Slice B — last_spoke_at is the "
        "VOICE_SESSION_TIMEOUT staleness clock) so staleness checks don't immediately "
        "disqualify the fresh session"
    )
