"""test_pipeline_session_lifecycle — session lifecycle tests (split from test_pipeline.py, P1.A1 SP-1).

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


async def test_voice_only_stranger_not_waiting():
    """Voice-only stranger (already said system name) has waiting_for_name=False."""
    import pipeline
    import time as _t

    await pipeline._session_store.open_session("stranger_xyz", "visitor", "stranger", "voice", now=_t.time())
    # waiting_for_name defaults to False in the Session dataclass

    snap = pipeline._session_store.peek_snapshot("stranger_xyz")
    assert snap.person_type == "stranger"
    assert snap.waiting_for_name is False


async def test_close_session_cleans_stranger_track_map():
    """_close_session() removes all track_map entries pointing to the closed session."""
    import pipeline
    await pipeline._session_store.open_session("stranger_abc", "visitor", "stranger", "voice", now=0.0)
    await pipeline._session_store.open_session("stranger_xyz", "visitor", "stranger", "voice", now=0.0)
    await pipeline._track_store.mark_unrecognized(42, 100.0)
    await pipeline._track_store.mark_unrecognized(99, 100.0)
    await pipeline._track_store.mint_stranger(42, "stranger_abc")
    await pipeline._track_store.mint_stranger(99, "stranger_xyz")

    pipeline._close_session("stranger_abc")
    # Yield so create_task'd close_session coroutine runs.
    await asyncio.sleep(0)

    assert 42 not in pipeline._track_store   # removed — session closed
    assert 99 in pipeline._track_store       # unrelated entry preserved
    assert pipeline._session_store.peek_snapshot("stranger_abc") is None


async def test_open_session_sets_kairos_clock_reset_flag():
    """Issue 4: A brand-new session must have kairos_clock_reset=True so the silence
    clock is reset exactly once when the conversation loop first enters."""
    import pipeline
    pipeline._open_session("kairos_p1", "Jagan", "face", person_type="known")
    # Yield so create_task'd open_session coroutine runs.
    await asyncio.sleep(0)
    _snap = pipeline._session_store.peek_snapshot("kairos_p1")
    assert _snap is not None and _snap.kairos_clock_reset is True
    assert _snap.person_type == "known"


async def test_open_session_existing_session_does_not_set_flag():
    """Issue 4: Updating an existing session (e.g. face re-detected) must NOT set
    kairos_clock_reset — re-entry after 'No speech detected' must not reset the clock."""
    import pipeline
    # Seed the store so _open_session takes the re-open path.
    await pipeline._session_store.open_session("p1", "Jagan", "known", "face", now=1000.0)
    # Simulate the first loop iteration consuming the flag (setting it to False).
    await pipeline._session_store.consume_kairos_reset("p1")
    # Re-open via pipeline (update_on_reopen does NOT touch kairos_clock_reset).
    pipeline._open_session("p1", "Jagan", "face", person_type="known")
    await asyncio.sleep(0)
    _snap = pipeline._session_store.peek_snapshot("p1")
    assert _snap is not None and not _snap.kairos_clock_reset


def test_progressive_enroll_db_entry_uses_session_id(tmp_path):
    """Progressive enroll: DB entry must be stored under the same ID as the in-memory session."""
    from core.db import FaceDB
    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))

    # Simulate: session opened with temp in-memory ID (no DB entry yet)
    session_id = "stranger_cafebabe"
    # System name heard → auto-enroll using session_id as person_id
    db.add_stranger("visitor", person_id=session_id)

    # DB entry must use session_id so voice embeddings and conversation log align
    row = db._conn.execute("SELECT id FROM persons WHERE id = ?", (session_id,)).fetchone()
    assert row is not None, "DB entry must exist under the in-memory session ID"
    db._conn.close()


@pytest.mark.asyncio
async def test_accumulate_voice_updates_gallery_for_enrolled_stranger(tmp_path):
    """_accumulate_voice must update _voice_gallery after storing the first embedding.
    Step 3: session needs identity_evidence with a witness path open (bootstrap credits
    from engagement-gate open is the canonical way to enable first-turn accumulation)."""
    import numpy as np
    from unittest.mock import patch, AsyncMock
    from core.db import FaceDB
    import time as _t

    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))
    stranger_id = "stranger_test99"
    db.add_stranger("visitor", person_id=stranger_id)

    audio = np.zeros(32000, dtype=np.float32)
    fake_emb = np.ones(192, dtype=np.float32)
    fake_emb /= np.linalg.norm(fake_emb)

    import asyncio as _asyncio, pipeline as _pl
    await _pl._voice_gallery_store.pop_gallery(stranger_id)
    # Open a session with engagement_gate_passed=True so bootstrap credits enable
    # first-turn accumulation via Path C.
    _pl._session_store._sessions.pop(stranger_id, None)
    _pl._open_session(stranger_id, "visitor", "voice",
                      person_type="stranger", engagement_gate_passed=True)
    await _pl._session_store.open_session(stranger_id, "visitor", "stranger", "voice",
                                          now=_t.time(),
                                          bootstrap_credits=_pl.N_INITIAL_VOICE_BOOTSTRAP)

    # P0.R6.Y D3: voice_mod.embed is async; patch with AsyncMock.
    with patch("pipeline.voice_mod.embed", new=AsyncMock(return_value=fake_emb)):
        await _pl._accumulate_voice(stranger_id, audio, db)

    assert _pl._voice_gallery_store.peek_gallery(stranger_id) is not None, \
        "_voice_gallery_store must contain the stranger after first accumulation"
    _pl._close_session(stranger_id)
    db._conn.close()


def test_progressive_enroll_auto_enroll_block_present():
    """Pipeline source must contain the auto-enroll block triggered after system-name gate."""
    import inspect, pipeline
    src = inspect.getsource(pipeline)
    assert "db.add_stranger(\"visitor\", person_id=_cur_pid)" in src, \
        "Auto-enroll DB call must be present in pipeline after system-name gate"
    assert "db_enrolled" in src, \
        "db_enrolled flag must be set on auto-enroll"
    assert 'mark_enrolled(' in src, \
        "_session_store.mark_enrolled must be called on auto-enroll"


async def test_voice_accumulation_refused_with_no_witness():
    """Step 3: _accumulate_voice must refuse when the session has no identity
    evidence (no face witness, no mature voice, no bootstrap credits)."""
    import numpy as np
    from unittest.mock import MagicMock
    import pipeline as _pl
    import time as _t
    # Session with empty evidence — all defaults: bootstrap=0, voice_n=0, conf=0.0
    await _pl._session_store.open_session("p1", "test", "stranger", "voice", now=_t.time())
    mock_db = MagicMock()
    audio = np.zeros(16000, dtype=np.float32)
    await _pl._accumulate_voice("p1", audio, mock_db)
    mock_db.add_voice_embedding.assert_not_called()


def test_gate_pass_stores_face_embedding_when_track_available(tmp_path):
    """When a stranger clears the gate and vision has an embedding cached, store it in faces.db."""
    import numpy as np
    import pipeline
    from core.db import FaceDB

    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))
    pid = "stranger_test_c3"
    db.add_stranger("visitor", person_id=pid)

    emb = np.random.rand(512).astype(np.float32)
    emb /= np.linalg.norm(emb)
    pipeline._unrecognized_embeddings = {42: emb}
    pipeline._stranger_track_map = {42: pid}

    _gate_track = next((tid for tid, p in pipeline._stranger_track_map.items() if p == pid), None)
    assert _gate_track == 42
    added = db.add_embedding(
        pid, pipeline._unrecognized_embeddings[_gate_track],
        source="progressive_enroll", anti_spoof_verdict=True,
    )
    assert added is True

    count = db._conn.execute(
        "SELECT COUNT(*) FROM embeddings WHERE person_id = ?", (pid,)
    ).fetchone()[0]
    assert count == 1
    db._conn.close()


def test_gate_pass_skips_face_embedding_when_no_track(tmp_path):
    """When no track is mapped to the stranger session, embedding storage is silently skipped."""
    import pipeline
    from core.db import FaceDB

    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))
    pid = "stranger_no_track"
    db.add_stranger("visitor", person_id=pid)

    pipeline._unrecognized_embeddings = {}
    pipeline._stranger_track_map = {}

    _gate_track = next((tid for tid, p in pipeline._stranger_track_map.items() if p == pid), None)
    assert _gate_track is None  # no crash, no embedding stored

    count = db._conn.execute(
        "SELECT COUNT(*) FROM embeddings WHERE person_id = ?", (pid,)
    ).fetchone()[0]
    assert count == 0
    db._conn.close()


async def test_close_session_prunes_track_identity():
    """#4: _close_session() must remove _track_identity entries for the closed person."""
    import pipeline
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    await pipeline._track_store.bind_identity(5, "p1")
    await pipeline._track_store.bind_identity(6, "p2")
    pipeline._close_session("p1")
    await asyncio.sleep(0)
    assert 5 not in pipeline._track_store
    assert pipeline._track_store.peek_identity(6) == "p2"  # unrelated entry preserved


async def test_session_opens_with_recent_attributions_deque():
    """#21: Every new session must have a recent_attributions list."""
    import pipeline, tempfile, pathlib
    from core.db import FaceDB
    with tempfile.TemporaryDirectory() as td:
        db = FaceDB(pathlib.Path(td) / "faces.db")
        try:
            pid = db.add_person("Jagan", "jagan")
            pipeline._open_session(pid, "Jagan", "face", person_type="known")
            await asyncio.sleep(0)
            snap = pipeline._session_store.peek_snapshot(pid)
            assert snap is not None
            assert isinstance(snap.recent_attributions, tuple)
            pipeline._close_session(pid)
            await asyncio.sleep(0)
        finally:
            db._conn.close()


def test_voice_session_timeout_is_30():
    """#22: VOICE_SESSION_TIMEOUT must be 30s (reduced from 60s)."""
    from core.config import VOICE_SESSION_TIMEOUT
    assert VOICE_SESSION_TIMEOUT == 30


def test_voice_session_extends_when_face_visible():
    """#22: voice session last_spoke_at updated when holder is visible in _presence_store."""
    import asyncio, pipeline, time
    pid = "stranger_abc123"
    now = time.time()
    asyncio.run(pipeline._session_store.open_session(
        pid, "visitor", "stranger", "voice", now=now - 25.0,
    ))
    asyncio.run(pipeline._session_store.set_last_spoke_at(pid, now - 20.0))
    asyncio.run(pipeline._presence_store.upsert_face_recognition(pid, "visitor", 0.3, now))
    # Simulate the extension logic
    _now_ext = time.time()
    _holder_vis = (
        pid in pipeline._presence_store
        and _now_ext - pipeline._presence_store.peek_last_recognized_at(pid, 0.0) < 2.0
    )
    if _holder_vis:
        asyncio.run(pipeline._session_store.set_last_spoke_at(pid, _now_ext))
    snap = pipeline._session_store.peek_snapshot(pid)
    assert snap is not None
    assert snap.last_spoke_at >= now - 0.1


async def test_accumulate_voice_refused_when_session_has_no_evidence():
    """Step 3: session with empty identity_evidence dict → refused."""
    import numpy as np
    from unittest.mock import MagicMock
    import pipeline as _pl
    import time as _t
    await _pl._session_store.open_session("p1", "test", "stranger", "voice", now=_t.time())
    mock_db = MagicMock()
    audio = np.zeros(16000, dtype=np.float32)
    await _pl._accumulate_voice("p1", audio, mock_db)
    mock_db.add_voice_embedding.assert_not_called()


async def test_accumulate_voice_replenishes_bootstrap_for_engaged_stranger():
    """Session 94 Fix #5: an engaged stranger (waiting_for_name=False, gate
    passed on some earlier turn) whose bootstrap credits have burned to 0
    but whose voice profile hasn't reached MATURE_SAMPLE_COUNT must get
    +1 bootstrap credit at the top of ``_accumulate_voice``. Without this,
    sessions re-opened via voice match inherit bootstrap=0 from
    ``_open_session``'s default and every subsequent accumulation refuses
    — observed in the 2026-04-22 live run where a stranger was stuck at
    voice_n=2 across multiple visits. Replenishment fires BEFORE the
    ``_voice_accum_allowed`` check so Path C can then pass."""
    import numpy as np, time as _t
    from unittest.mock import MagicMock, patch
    import pipeline as _pl

    # Seed _session_store so _voice_accum_allowed can read evidence via peek_snapshot.
    await _pl._session_store.open_session("p1", "visitor", "stranger", "voice", now=_t.time())
    await _pl._session_store.set_voice_sample_count("p1", 2)
    await _pl._session_store.set_voice_only_origin("p1", True)
    # Replenishment uses loop.create_task (fire-and-forget), so the increment
    # isn't complete when _voice_accum_allowed reads peek_snapshot. Pre-seed
    # with 1 credit to simulate state after a prior replenishment cycle.
    await _pl._session_store.set_bootstrap_credits("p1", 1)
    mock_db = MagicMock()
    mock_db.add_voice_embedding = MagicMock(return_value=True)
    mock_db.load_voice_profile_for = MagicMock(return_value=np.ones(192, dtype=np.float32) / (192**0.5))
    mock_db.voice_embedding_count = MagicMock(return_value=3)
    # P0.S7.5.2 D3 — audio must be ≥ MIN_VOICE_ACCUM_DURATION_SECS=1.5s
    # (24000 samples at 16kHz) to pass the duration gate. Pre-D3 this test
    # used 1.0s (16000 samples) and was implicitly passing the gate that
    # didn't exist; D3 added the floor.
    audio = np.zeros(24000, dtype=np.float32)
    # Patch identify so the self-match branch doesn't attempt real ECAPA.
    # For bootstrap path, v_pid doesn't need to match person_id.
    # P0.R6.Y D3: voice_mod.identify + embed are async; use AsyncMock.
    from unittest.mock import AsyncMock as _AsyncMock  # noqa: PLC0415
    with patch("pipeline.voice_mod.identify", new=_AsyncMock(return_value=(None, 0.0, True))), \
         patch("pipeline.voice_mod.embed",
               new=_AsyncMock(return_value=np.ones(192, dtype=np.float32) / (192**0.5))):
        await _pl._accumulate_voice("p1", audio, mock_db)
    # The replenishment should have granted 1 credit, then Path C fired.
    # Accumulation fired → add_voice_embedding called.
    mock_db.add_voice_embedding.assert_called_once()


async def test_accumulate_voice_no_replenish_when_gate_still_active():
    """Session 94 Fix #5 (negative case): a stranger whose engagement gate
    has NOT yet passed (``waiting_for_name=True``) must NOT get free
    credits — the gate itself grants N_INITIAL_VOICE_BOOTSTRAP on its
    pass-turn. Replenishing while the gate is still active would let
    strangers who never actually address the system accumulate samples
    silently (exactly what the gate exists to prevent)."""
    import numpy as np
    import time as _t
    from unittest.mock import MagicMock
    import pipeline as _pl

    await _pl._session_store.open_session("p1", "visitor", "stranger", "voice", now=_t.time(),
                                          voice_sample_count=2)
    await _pl._session_store.set_waiting_for_name("p1", True)
    mock_db = MagicMock()
    audio = np.zeros(16000, dtype=np.float32)
    await _pl._accumulate_voice("p1", audio, mock_db)
    # No replenishment → Path C still blocked → accumulation refused.
    mock_db.add_voice_embedding.assert_not_called()
    # Credits stayed at 0.
    assert _pl._session_store.peek_snapshot("p1").evidence.bootstrap_credits == 0


async def test_accumulate_voice_mature_profile_skipped_when_voice_weak():
    """Step 3: face witness and bootstrap both absent; mature profile gate-pass
    (path B) but the voice didn't self-match → skip this sample.

    P0.R6.Y D3: voice_mod.identify is async; use AsyncMock.
    """
    import numpy as np
    import time as _t
    from unittest.mock import MagicMock, patch, AsyncMock
    import pipeline as _pl

    await _pl._session_store.open_session("p1", "test", "stranger", "voice", now=_t.time(),
                                          voice_sample_count=7)
    await _pl._session_store.update_voice_heard("p1", conf=0.60, ts=_t.time())
    mock_db = MagicMock()
    audio = np.zeros(16000, dtype=np.float32)
    with patch("pipeline.voice_mod.identify", new=AsyncMock(return_value=(None, 0.0, True))):
        await _pl._accumulate_voice("p1", audio, mock_db)
    mock_db.add_voice_embedding.assert_not_called()


async def test_close_session_evicts_query_embedding_cache():
    import asyncio, pipeline, time as _t
    await pipeline._session_store.open_session("p1", "Alice", "known", "face", now=_t.time())
    await pipeline._query_embedding_store.set("p1", [0.1, 0.2])
    await pipeline._query_embedding_store.set("p2", [0.3, 0.4])
    pipeline._close_session("p1")
    await asyncio.sleep(0)
    assert pipeline._query_embedding_store.peek("p1") is None, "_close_session must evict _query_embedding_store"
    assert pipeline._query_embedding_store.peek("p2") is not None, "unrelated entry must not be removed"


async def test_close_session_evicts_identity_hints():
    import asyncio, pipeline, time as _t
    await pipeline._session_store.open_session("p1", "Alice", "known", "face", now=_t.time())
    await pipeline._identity_hints_store.set("p1", {"name": "Alice", "conf": 0.9})
    await pipeline._identity_hints_store.set("p2", {"name": "Bob", "conf": 0.7})
    pipeline._close_session("p1")
    await asyncio.sleep(0)
    assert pipeline._identity_hints_store.peek("p1") is None, "_close_session must evict _identity_hints_store"
    assert pipeline._identity_hints_store.peek("p2") is not None, "unrelated entry must not be removed"


def test_voice_embedding_stores_voice_self_match_source(tmp_path):
    import numpy as np, time
    from core.db import FaceDB
    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "faiss.index")
    db._conn.execute(
        "INSERT INTO persons (id, name, enrolled_at, person_type) VALUES ('p1', 'Alice', ?, 'known')",
        (time.time(),),
    )
    db._conn.commit()
    emb = np.random.randn(192).astype(np.float32)
    db.add_voice_embedding("p1", emb, source="voice_self_match", confidence=0.72)
    row = db._conn.execute(
        "SELECT source, confidence_at_write FROM voice_embeddings WHERE person_id = 'p1'"
    ).fetchone()
    assert row is not None
    assert row[0] == "voice_self_match"
    assert abs(row[1] - 0.72) < 1e-5
    db._conn.close()


def test_voice_embedding_stores_voice_face_verified_source(tmp_path):
    import numpy as np, time
    from core.db import FaceDB
    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "faiss.index")
    db._conn.execute(
        "INSERT INTO persons (id, name, enrolled_at, person_type) VALUES ('p1', 'Alice', ?, 'known')",
        (time.time(),),
    )
    db._conn.commit()
    emb = np.random.randn(192).astype(np.float32)
    db.add_voice_embedding("p1", emb, source="voice_face_verified", confidence=0.0)
    row = db._conn.execute(
        "SELECT source FROM voice_embeddings WHERE person_id = 'p1'"
    ).fetchone()
    assert row is not None
    assert row[0] == "voice_face_verified"
    db._conn.close()


def test_accumulate_voice_uses_correct_source_strings():
    import inspect, pipeline
    src = inspect.getsource(pipeline._accumulate_voice)
    assert '"voice_self_match"' in src, "_accumulate_voice must use 'voice_self_match' source"
    assert '"voice_face_verified"' in src, "_accumulate_voice must use 'voice_face_verified' source"


def test_expire_stale_sessions_exists_as_module_level_function():
    """_expire_stale_sessions must be a module-level callable (not nested inside run())."""
    import pipeline
    assert callable(getattr(pipeline, "_expire_stale_sessions", None)), \
        "_expire_stale_sessions must be a module-level function"


def test_expire_stale_sessions_called_in_inner_conversation_loop():
    """Inner conversation loop must call _expire_stale_sessions() every iteration."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.run)
    # The inner loop calls _expire_stale_sessions() — ensure it appears more than once
    # (outer WATCHING loop + inner conversation loop)
    count = src.count("_expire_stale_sessions()")
    assert count >= 2, (
        f"_expire_stale_sessions() appears {count} time(s) in run() — "
        "expected ≥ 2 (outer loop + inner conversation loop)"
    )


async def test_expire_stale_sessions_closes_timed_out_voice_session():
    """_expire_stale_sessions must close a voice session whose last_spoke_at is stale."""
    import time, pipeline
    from core.config import VOICE_SESSION_TIMEOUT

    stale_pid = "stranger_expire_test"
    stale_now = time.time() - (VOICE_SESSION_TIMEOUT + 10)
    # #5 Slice B (§0.1.3): VOICE_SESSION_TIMEOUT reads the MONOTONIC last_spoke_at now; seed the
    # staleness clock (now_mono) backdated so the elapsed-math expiry fires. A backdated WALL `now`
    # only stamps started_at (which is NOT the timeout clock — this test previously relied on wall).
    await pipeline._session_store.open_session(
        stale_pid, "ExpireTest", "stranger", "voice", now=stale_now,
        now_mono=time.monotonic() - (VOICE_SESSION_TIMEOUT + 10),
    )
    pipeline._expire_stale_sessions()
    await asyncio.sleep(0)
    assert pipeline._session_store.peek_snapshot(stale_pid) is None, \
        "Stale voice session should have been expired"


def test_voice_face_confirmed_flag_in_face_vis_acc_check():
    """_face_vis_acc must use voice_face_confirmed session flag (source inspection)."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.run)
    assert "voice_face_confirmed" in src, \
        "run() must check voice_face_confirmed flag in _face_vis_acc computation"


def test_gate_pass_sets_voice_face_confirmed_flag():
    """Progressive-enroll gate pass must call mark_voice_face_confirmed on session store."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.run)
    assert 'mark_voice_face_confirmed' in src, \
        "Gate pass must call _session_store.mark_voice_face_confirmed"


def test_greeting_path_uses_db_person_type_not_literal_known():
    """Problem B (Session 59) + Step 2 (session-type refactor): the greeting branch
    must fetch person_type from the DB and pass it into _open_session — seeded at
    dict creation, no post-hoc literal write that could downgrade best_friend."""
    import inspect, pipeline, re
    src = inspect.getsource(pipeline.run)
    assert "person_type = db.get_person_type(person_id)" in src, (
        "Greeting path must fetch person_type from DB before _open_session"
    )
    # Allow the call to span multiple lines; what matters is that face session
    # open passes person_type=person_type (not a literal).
    assert re.search(
        r'_open_session\(\s*person_id,\s*person_name,\s*"face",[^)]*person_type=person_type',
        src,
        flags=re.DOTALL,
    ), "Greeting path must pass person_type=person_type into _open_session"


def test_greeting_path_sets_voice_face_confirmed():
    """Problem C (Session 59 live run): known/best_friend greeting path must call
    mark_voice_face_confirmed so their voice profile can accumulate from turn 1."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.run)
    # Must appear in the greeting-path else-branch (known/best_friend open)
    assert 'mark_voice_face_confirmed' in src, (
        "Known/best_friend greeting path must call _session_store.mark_voice_face_confirmed"
    )


def test_notify_session_end_skips_synthesis_tasks_when_disputed():
    """When person_id is in _disputed_persons, notify_session_end must NOT schedule
    pref/insight/presence/nudge/household tasks (they'd pollute the sensor-matched
    person's long-term profile with turns that may belong to someone else)."""
    import asyncio, sqlite3
    from unittest.mock import AsyncMock, MagicMock
    from core.brain_agent import BrainOrchestrator

    orch = BrainOrchestrator.__new__(BrainOrchestrator)
    orch._trigger          = asyncio.Event()
    orch._disputed_persons = {"jagan_001"}
    orch._session_turn_counts = {"jagan_001": 5}
    orch._intra_pref_done  = set()
    orch._session_start_ts = {"jagan_001": 0.0}
    orch._faces_conn       = sqlite3.connect(":memory:")
    orch._faces_conn.executescript("""
        CREATE TABLE persons (id TEXT PRIMARY KEY, name TEXT NOT NULL);
        INSERT INTO persons VALUES ('jagan_001', 'Jagan');
    """)

    called = {"pref": 0, "insight": 0, "presence": 0, "nudge": 0, "visitor": 0, "household": 0}
    async def _fail_pref(*a, **k):     called["pref"] += 1
    async def _fail_insight(*a, **k):  called["insight"] += 1
    async def _fail_presence(*a, **k): called["presence"] += 1
    async def _fail_nudge(*a, **k):    called["nudge"] += 1
    async def _fail_visitor(*a, **k):  called["visitor"] += 1
    async def _fail_household(*a, **k):called["household"] += 1
    orch._run_pref_analysis        = _fail_pref
    orch._run_insight_analysis     = _fail_insight
    orch._run_presence_log         = _fail_presence
    orch._run_nudge_generation     = _fail_nudge
    orch._run_visitor_alert        = _fail_visitor
    orch._run_household_session_end = _fail_household

    async def run():
        orch.notify_session_end("jagan_001")
        await asyncio.sleep(0)
    asyncio.run(run())
    assert called == {"pref": 0, "insight": 0, "presence": 0, "nudge": 0, "visitor": 0, "household": 0}
    assert "jagan_001" not in orch._session_turn_counts


def test_notify_session_end_runs_synthesis_tasks_when_not_disputed():
    """Non-disputed sessions must still run all session-end synthesis helpers."""
    import asyncio, sqlite3
    from unittest.mock import AsyncMock, MagicMock
    from core.brain_agent import BrainOrchestrator

    orch = BrainOrchestrator.__new__(BrainOrchestrator)
    orch._trigger          = asyncio.Event()
    orch._disputed_persons = set()
    orch._session_turn_counts = {"jagan_001": 5}
    orch._intra_pref_done  = set()
    orch._session_start_ts = {"jagan_001": 1.0}
    orch._faces_conn       = sqlite3.connect(":memory:")
    orch._faces_conn.executescript("""
        CREATE TABLE persons (id TEXT PRIMARY KEY, name TEXT NOT NULL);
        INSERT INTO persons VALUES ('jagan_001', 'Jagan');
    """)

    called = {"pref": 0, "insight": 0}
    async def _count_pref(*a, **k):    called["pref"] += 1
    async def _count_insight(*a, **k): called["insight"] += 1
    orch._run_pref_analysis        = _count_pref
    orch._run_insight_analysis     = _count_insight
    orch._run_presence_log         = AsyncMock()
    orch._run_nudge_generation     = AsyncMock()
    orch._run_visitor_alert        = AsyncMock()
    orch._run_household_session_end = AsyncMock()

    async def run():
        orch.notify_session_end("jagan_001")
        await asyncio.sleep(0)
    asyncio.run(run())
    assert called["pref"] == 1
    assert called["insight"] == 1


async def test_open_session_with_engagement_gate_seeds_bootstrap_credits():
    """Step 3: engagement_gate_passed=True → session gets N_INITIAL_VOICE_BOOTSTRAP credits."""
    import pipeline
    from core.config import N_INITIAL_VOICE_BOOTSTRAP
    pipeline._open_session("os_egc_p1", "Jagan", "face",
                           person_type="best_friend", engagement_gate_passed=True)
    await asyncio.sleep(0)
    snap = pipeline._session_store.peek_snapshot("os_egc_p1")
    assert snap is not None
    assert snap.evidence.bootstrap_credits == N_INITIAL_VOICE_BOOTSTRAP


async def test_open_session_without_engagement_gate_no_credits():
    """Step 3: engagement_gate_passed=False (default) → zero bootstrap credits."""
    import pipeline
    pipeline._open_session("os_nogc_p2", "Jagan", "voice", person_type="known")
    await asyncio.sleep(0)
    snap = pipeline._session_store.peek_snapshot("os_nogc_p2")
    assert snap is not None
    assert snap.evidence.bootstrap_credits == 0


def test_voice_accum_allowed_path_a_face_witness():
    """Path A: recent confident face + anti-spoof live → allowed."""
    import pipeline, time, asyncio
    pid = "_test_path_a"
    now = time.time()
    asyncio.run(pipeline._session_store.open_session(pid, "Test", "known", "face", now=now))
    # #5 Slice D: _voice_accum_allowed reads time.monotonic() (was time.time()); face_last_seen_ts
    # must be seeded monotonic so a "fresh" face reads fresh under the now-monotonic reader.
    asyncio.run(pipeline._session_store.update_face_seen(pid, conf=0.80, ts=time.monotonic(), anti_spoof_live=True))
    allowed, reason, path = pipeline._voice_accum_allowed(pid)
    assert allowed
    assert path == "face_witness"


def test_voice_accum_allowed_face_witness_too_old():
    """Path A refused when face is stale → falls through, no other path hits → refused."""
    import pipeline, time, asyncio
    pid = "_test_path_a_stale"
    now = time.time()
    asyncio.run(pipeline._session_store.open_session(pid, "Test", "known", "face", now=now))
    # #5 Slice D: _voice_accum_allowed reads time.monotonic(); a monotonic face 30s old is stale
    # (> VOICE_ACCUM_FACE_WITNESS_MAX_AGE_SEC) so Path A refuses. (Was ts=now-30.0 wall, which
    # under the now-monotonic reader gave a hugely-negative age that incorrectly read fresh.)
    asyncio.run(pipeline._session_store.update_face_seen(pid, conf=0.80, ts=time.monotonic() - 30.0, anti_spoof_live=True))
    allowed, reason, path = pipeline._voice_accum_allowed(pid)
    assert not allowed
    assert path == "refused"


def test_voice_accum_allowed_path_b_mature_voice():
    """Path B: no face, but mature voice profile self-matching → allowed."""
    import pipeline, time, asyncio
    pid = "_test_path_b"
    now = time.time()
    asyncio.run(pipeline._session_store.open_session(pid, "Test", "known", "voice", now=now))
    asyncio.run(pipeline._session_store.update_voice_heard(pid, conf=0.55, ts=now))
    asyncio.run(pipeline._session_store.set_voice_sample_count(pid, 7))
    allowed, reason, path = pipeline._voice_accum_allowed(pid)
    assert allowed
    assert path == "voice_self_match"


def test_voice_accum_allowed_path_c_bootstrap_credits():
    """Path C: no face, no mature voice, but bootstrap credits remaining → allowed."""
    import pipeline, time, asyncio
    pid = "_test_path_c"
    now = time.time()
    asyncio.run(pipeline._session_store.open_session(pid, "Test", "stranger", "voice", now=now))
    asyncio.run(pipeline._session_store.set_bootstrap_credits(pid, 2))
    allowed, reason, path = pipeline._voice_accum_allowed(pid)
    assert allowed
    assert path == "bootstrap"


def test_voice_accum_allowed_all_paths_exhausted():
    """All three paths fail → refused with informative reason."""
    import pipeline, time, asyncio
    pid = "_test_path_none"
    now = time.time()
    asyncio.run(pipeline._session_store.open_session(pid, "Test", "stranger", "voice", now=now))
    allowed, reason, path = pipeline._voice_accum_allowed(pid)
    assert not allowed
    assert path == "refused"
    assert "no witness" in reason


def test_refusal_log_includes_voice_match_conf():
    """Bug I diagnostic: the refusal log format must surface voice_match_conf so
    we can tell at a glance whether Path B failed because of low score (fixable
    by better acoustics) or low sample count (fixable by accumulation). Before
    Session 67 this was invisible and made Bug I diagnosis require a debugger."""
    import pipeline, time, asyncio
    pid = "_test_refusal_log"
    now = time.time()
    asyncio.run(pipeline._session_store.open_session(pid, "Test", "known", "voice", now=now))
    asyncio.run(pipeline._session_store.update_voice_heard(pid, conf=0.37, ts=now))
    asyncio.run(pipeline._session_store.set_voice_sample_count(pid, 20))
    _, reason, _ = pipeline._voice_accum_allowed(pid)
    assert "voice_conf=0.37" in reason, (
        f"refusal log must include voice_match_conf; got {reason!r}"
    )


def test_voice_accum_sees_current_turn_voice_match_conf():
    """Bug I fix: after the conversation_turn voice ID writes voice_match_conf to
    identity_evidence (line 3437+), Path B can fire on a re-opened mature session.
    Simulates the exact 2026-04-20 scenario: Jagan's session with voice_n=20 but
    voice_match_conf=0.0 (stale from _open_session seed). After the evidence write
    runs for the current turn's 0.55 voice match, Path B allows accumulation."""
    import pipeline, time, asyncio
    pid = "_test_current_turn"
    now = time.time()
    # Before write: stale (voice_n=20, conf=0.0) → refused
    asyncio.run(pipeline._session_store.open_session(pid, "Test", "known", "voice", now=now))
    asyncio.run(pipeline._session_store.set_voice_sample_count(pid, 20))
    allowed_before, _, path_before = pipeline._voice_accum_allowed(pid)
    assert not allowed_before and path_before == "refused"
    # After the conversation_turn write: voice_match_conf is set before the check
    asyncio.run(pipeline._session_store.update_voice_heard(pid, conf=0.55, ts=now))
    allowed, _, path = pipeline._voice_accum_allowed(pid)
    assert allowed is True and path == "voice_self_match", (
        "Path B must fire on a mature session once this turn's voice_match_conf "
        "is written to identity_evidence; Bug I was that this write happened "
        "inside _accumulate_voice AFTER the gate, so it never ran"
    )
    asyncio.run(pipeline._session_store.close_session(pid))


def test_face_in_frame_returns_false_for_voice_source():
    """Bug B: _persons_in_frame entries with source='voice' must NOT count as face-visible."""
    import pipeline
    pif = {"p1": {"name": "Chloe", "conf": 0.502, "source": "voice"}}
    assert pipeline._face_in_frame("p1", pif) is False


def test_face_in_frame_returns_true_for_face_source():
    """Bug B: entries with source='face' return True."""
    import pipeline
    pif = {"jagan": {"name": "Jagan", "conf": 0.8, "source": "face"}}
    assert pipeline._face_in_frame("jagan", pif) is True


def test_face_in_frame_returns_false_for_missing_pid():
    """Bug B: missing pid is not in frame at all."""
    import pipeline
    assert pipeline._face_in_frame("nobody", {}) is False


def test_bootstrap_budget_exceeds_mature_threshold():
    """Bug A Part 2: N_INITIAL_VOICE_BOOTSTRAP must exceed VOICE_ACCUM_MATURE_SAMPLE_COUNT
    so a voice-only stranger's first session can reach maturity within the budget.
    Invariant guard: if someone tunes MATURE up without also raising BOOTSTRAP, this fails."""
    from core.config import N_INITIAL_VOICE_BOOTSTRAP, VOICE_ACCUM_MATURE_SAMPLE_COUNT
    assert N_INITIAL_VOICE_BOOTSTRAP > VOICE_ACCUM_MATURE_SAMPLE_COUNT, (
        f"BOOTSTRAP ({N_INITIAL_VOICE_BOOTSTRAP}) must exceed MATURE "
        f"({VOICE_ACCUM_MATURE_SAMPLE_COUNT}) — otherwise voice-only strangers get "
        f"stuck at BOOTSTRAP samples and neither Path A nor B engages."
    )


def test_bootstrap_matches_max_voice_embeddings():
    """Session 67 (2026-04-21) voice-vision independence invariant: the bootstrap
    budget must equal MAX_VOICE_EMBEDDINGS so a voice-only speaker can fully mature
    their profile in a single engagement-gated session WITHOUT requiring any face
    evidence. Voice and vision are independent sensor channels — voice must not
    depend on vision for maturation. Guards against someone tuning BOOTSTRAP back
    down and reintroducing the channel coupling that caused Chloe's permanent-at-3
    problem in the 2026-04-20 live run."""
    from core.config import N_INITIAL_VOICE_BOOTSTRAP, MAX_VOICE_EMBEDDINGS
    assert N_INITIAL_VOICE_BOOTSTRAP == MAX_VOICE_EMBEDDINGS, (
        f"BOOTSTRAP ({N_INITIAL_VOICE_BOOTSTRAP}) must equal MAX_VOICE_EMBEDDINGS "
        f"({MAX_VOICE_EMBEDDINGS}) — voice-only speakers must be able to reach the "
        f"profile ceiling within one engagement session, regardless of face availability."
    )


async def test_open_session_hydrates_voice_sample_count_from_gallery():
    """Bug A Part 1: a re-opened session must hydrate voice_sample_count from the
    DB-backed _voice_gallery_sizes cache so prior samples carry forward."""
    import numpy as np, pipeline
    try:
        await pipeline._voice_gallery_store.set_gallery("chloe_001", np.ones(192, dtype=np.float32), 4)
        pipeline._open_session("chloe_001", "Chloe", "voice",
                               person_type="stranger", engagement_gate_passed=False)
        await asyncio.sleep(0)
        snap = pipeline._session_store.peek_snapshot("chloe_001")
        assert snap is not None
        assert snap.evidence.voice_sample_count == 4
    finally:
        await pipeline._voice_gallery_store.pop_gallery("chloe_001")


async def test_open_session_hydrates_zero_when_pid_unknown_to_gallery():
    """Fresh pid not in _voice_gallery_sizes → sample count is 0, no KeyError."""
    import pipeline
    from core.config import N_INITIAL_VOICE_BOOTSTRAP
    await pipeline._voice_gallery_store.pop_gallery("brand_new_stranger")
    pipeline._open_session("brand_new_stranger", "visitor", "voice",
                           person_type="stranger", engagement_gate_passed=True)
    await asyncio.sleep(0)
    snap = pipeline._session_store.peek_snapshot("brand_new_stranger")
    assert snap is not None
    assert snap.evidence.voice_sample_count == 0
    # Bootstrap credits still seeded from engagement_gate_passed.
    assert snap.evidence.bootstrap_credits == N_INITIAL_VOICE_BOOTSTRAP


def test_count_voice_embeddings_returns_db_count(tmp_path):
    """Obs 1: FaceDB.count_voice_embeddings returns the authoritative row count
    for a given person_id — used as the DB-backed fallback when the pipeline's
    in-memory cache may be stale (e.g. after out-of-process delete_person)."""
    import numpy as np, time
    from core.db import FaceDB
    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "faiss.index")
    db._conn.execute(
        "INSERT INTO persons (id, name, enrolled_at, person_type) VALUES ('p1', 'Alice', ?, 'known')",
        (time.time(),),
    )
    db._conn.commit()
    for _ in range(4):
        db.add_voice_embedding("p1", np.random.randn(192).astype(np.float32),
                               source="voice_self_match", confidence=0.7)
    assert db.count_voice_embeddings("p1") == 4
    db._conn.close()


def test_count_voice_embeddings_returns_zero_for_unknown_pid(tmp_path):
    """Obs 1: count_voice_embeddings must not raise on a pid with no voice rows."""
    from core.db import FaceDB
    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "faiss.index")
    assert db.count_voice_embeddings("nobody") == 0
    db._conn.close()


async def test_open_session_hydration_prefers_live_db_over_stale_cache(tmp_path):
    """Obs 1: when the in-memory cache disagrees with the DB (e.g. cache says 10
    but DB only has 4 rows because someone deleted the person out-of-process),
    _open_session must read the DB value and repair the cache so other consumers
    (profile-strength gating at _effective_switch_threshold) see reality too."""
    import numpy as np, time, pipeline
    from core.db import FaceDB
    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "faiss.index")
    db._conn.execute(
        "INSERT INTO persons (id, name, enrolled_at, person_type) VALUES ('hydrate_p1', 'Alice', ?, 'known')",
        (time.time(),),
    )
    db._conn.commit()
    for _ in range(4):
        db.add_voice_embedding("hydrate_p1", np.random.randn(192).astype(np.float32),
                               source="voice_self_match", confidence=0.7)
    prev_ref = pipeline._face_db_ref
    try:
        pipeline._face_db_ref = db
        await pipeline._voice_gallery_store.set_gallery("hydrate_p1", np.ones(192, dtype=np.float32), 10)  # STALE — out-of-process delete happened
        pipeline._open_session("hydrate_p1", "Alice", "voice", person_type="known")
        await asyncio.sleep(0)
        snap = pipeline._session_store.peek_snapshot("hydrate_p1")
        assert snap is not None
        assert snap.evidence.voice_sample_count == 4, (
            "_open_session must prefer the live DB count over the stale cache"
        )
        # Cache repaired so downstream consumers also see the correct number.
        assert pipeline._voice_gallery_store.peek_size("hydrate_p1") == 4, (
            "Stale cache entry must be repaired to match the DB"
        )
    finally:
        pipeline._face_db_ref = prev_ref
        await pipeline._voice_gallery_store.pop_gallery("hydrate_p1")
        db._conn.close()


def test_voice_entry_expiry_logs_when_session_still_active():
    """Obs 4: when a voice entry ages out of _persons_in_frame (SCENE_STALE_SECS)
    but its session is still alive (VOICE_SESSION_TIMEOUT is longer), emit a
    distinct [Voice] 'no longer heard' log so the 5–30s silent window is
    observable. Source-inspection confirms the log line + session lookup."""
    import inspect, pipeline
    src = inspect.getsource(pipeline._background_vision_loop)
    assert "no longer heard" in src, (
        "_background_vision_loop must log [Voice] 'no longer heard' when a voice "
        "entry ages out with a still-active session"
    )
    # And it must only fire when the session actually exists (avoids double-log
    # alongside _close_session once the session has already closed).
    assert "_session_store.peek_snapshot(_lp_snap.person_id)" in src, (
        "The log must be gated on a session-store snapshot lookup, not emitted unconditionally"
    )
    # And it must use VOICE_SESSION_TIMEOUT so the remaining-seconds value is meaningful.
    assert "VOICE_SESSION_TIMEOUT" in src, (
        "The log must reference VOICE_SESSION_TIMEOUT so the reported 'expires in Ns' "
        "is grounded in the actual timeout constant"
    )


def test_voice_entry_expiry_is_silent_when_session_already_closed():
    """Obs 4: when a voice entry ages out AND the session is already closed,
    stay silent — _close_session already logged the close and a second log
    would be redundant. Source-inspection: the log line must be inside an
    `if _snap_voice_lp is not None:` block (not emitted unconditionally)."""
    import inspect, pipeline
    src = inspect.getsource(pipeline._background_vision_loop)
    # Find the voice branch of the prune loop (now uses .source attribute on snapshot).
    idx = src.find('.source == "voice"')
    assert idx > -1, "voice-source branch missing from prune loop"
    snippet = src[idx:idx + 500]
    # The session lookup must precede the log, and the log must be inside
    # an `if _sess is not None:` guard.
    assert "_snap_voice_lp = _session_store.peek_snapshot" in snippet
    assert "if _snap_voice_lp is not None:" in snippet
    # The log line must come after the guard — confirm ordering by scanning.
    guard_idx = snippet.find("if _snap_voice_lp is not None:")
    log_idx   = snippet.find("no longer heard")
    assert guard_idx > -1 and log_idx > guard_idx, (
        "[Voice] 'no longer heard' log must be inside the `if _sess is not None:` "
        "guard so closed sessions don't double-log"
    )


def test_open_session_requires_person_type():
    """_open_session(person_type=...) is now required — calling without it is an error."""
    import pipeline
    import pytest as _pytest
    with _pytest.raises(TypeError):
        pipeline._open_session("p1", "Jagan", "face")


def test_open_session_rejects_invalid_person_type():
    """Invalid person_type → AssertionError — catches literal-string bugs at write time."""
    import pipeline, pytest as _pytest
    with _pytest.raises(RuntimeError):
        pipeline._open_session("p1", "Jagan", "face", person_type="bogus")


def test_voice_first_stranger_open_grants_bootstrap_credits():
    """Session 90 Bug 1 Fix A: the voice-first stranger-engagement path at
    pipeline.py (search for 'Stranger engaged (voice-only, system addressed)')
    must open the session with ``engagement_gate_passed=True`` so
    ``identity_evidence.bootstrap_credits`` gets seeded with
    ``N_INITIAL_VOICE_BOOTSTRAP``. Without this, every subsequent
    ``_accumulate_voice`` call on the stranger's turns refuses with
    ``bootstrap=0`` — observed in the 2026-04-22 multi-convo live run
    (``Refused accumulation for stranger_visitor_2b01a4: ..., bootstrap=0``
    on turns 1 AND 2)."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.run)
    idx = src.find("Stranger engaged (voice-only, system addressed)")
    assert idx > -1, "voice-first engagement log line must be present"
    # Search backward for the _open_session call preceding the log print.
    # The call must pass engagement_gate_passed=True to seed bootstrap credits.
    window = src[max(0, idx - 1500):idx]
    assert "_open_session(" in window, "voice-first path must call _open_session"
    assert "engagement_gate_passed=True" in window, (
        "Session 90 Bug 1 Fix A: the voice-first stranger open must pass "
        "engagement_gate_passed=True so bootstrap_credits get seeded. "
        "Missing this was the root cause of bootstrap=0 refusals in the "
        "2026-04-22 multi-convo run."
    )


def test_voice_only_origin_initialized_false_in_open_session():
    """S120 Fix #1/#2: _open_session must manage voice_only_origin via set_voice_only_origin().
    The Session dataclass default is False; _open_session sets it True only via
    the backfill heuristic when conditions are met."""
    import inspect, pipeline
    src = inspect.getsource(pipeline._open_session)
    assert 'set_voice_only_origin' in src, (
        "S120: _open_session must call set_voice_only_origin() — "
        "the dict-literal 'voice_only_origin' key is gone after P0.7.5.C migration"
    )
    assert "False" in src, (
        "S120: voice_only_origin heuristic must use 'else False' fallback (not True)"
    )


def test_voice_only_origin_set_true_at_voice_only_engagement_path():
    """S120 Fix #1/#2: when a stranger passes the engagement gate via voice
    only (no face), voice_only_origin must be set True. This is the Lexi
    scenario: she says the system name → gate passes → voice_only_origin=True
    so bootstrap replenishment continues even after she is promoted to known."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.run)
    assert 'voice_only_origin' in src, (
        "S120: voice_only_origin must be present in run()"
    )
    # P0.7.4: dual-write deleted. Now uses SessionStore.set_voice_only_origin().
    assert "set_voice_only_origin" in src, (
        "S120: voice_only_origin must be set via set_voice_only_origin() in run()"
    )


def test_bootstrap_replenishment_uses_voice_only_origin_not_person_type():
    """S120 Fix #1/#2 — the Lexi regression guard.

    Root cause of permanently-stunted voice galleries: S94's bootstrap
    replenishment condition checked person_type == 'stranger'. The moment
    update_person_name fires (stranger says her name), the promotion chain
    flips person_type to 'known'. From that point all three accumulation
    paths block:
      - Path A (face witness) — blocked, voice-only
      - Path B (mature voice) — blocked, voice_n < 5 threshold
      - Path C (bootstrap credits) — exhausted, refuses because person_type
        is no longer 'stranger'

    Fix: replenishment now checks voice_only_origin flag, not person_type.
    This test asserts the condition change is present in the source."""
    import inspect, pipeline
    # Replenishment lives in _accumulate_voice, not run().
    src_acc = inspect.getsource(pipeline._accumulate_voice)
    # The replenishment block must reference voice_only_origin, NOT person_type=="stranger"
    assert "voice_only_origin" in src_acc, (
        "S120: bootstrap replenishment condition must reference voice_only_origin"
    )
    # The old bug: person_type == 'stranger' as the replenishment gate.
    # Verify this pattern is NOT the sole condition for replenishment.
    # We check that the VOICE_BOOTSTRAP_REPLENISH_ENABLED block uses voice_only_origin.
    replenish_idx = src_acc.find("VOICE_BOOTSTRAP_REPLENISH_ENABLED")
    assert replenish_idx > -1, "VOICE_BOOTSTRAP_REPLENISH_ENABLED block must exist in _accumulate_voice"
    # Extract a reasonable window around the replenishment condition check.
    replenish_block = src_acc[replenish_idx:replenish_idx + 600]
    assert "voice_only_origin" in replenish_block, (
        "S120: the VOICE_BOOTSTRAP_REPLENISH_ENABLED block must gate on "
        "voice_only_origin, not person_type=='stranger'"
    )
    # The old person_type=='stranger' check must NOT be the gate inside this block.
    assert "person_type" not in replenish_block or "voice_only_origin" in replenish_block, (
        "S120: replenishment must use voice_only_origin flag (Option B fix)"
    )


def test_voice_only_origin_cleared_on_face_witness():
    """S120 Fix #1/#2: when a real face is confirmed (background vision scan
    or greeting path), voice_only_origin must be cleared (set False). Once the
    person steps in front of the camera, the bootstrap replenishment path is no
    longer needed — Path A (face witness) becomes available."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.run)
    # P0.7.4: dual-write deleted. Now uses SessionStore.set_voice_only_origin(pid, False).
    assert "set_voice_only_origin" in src, (
        "S120: voice_only_origin must be cleared via set_voice_only_origin() in run()"
    )


async def test_voice_only_origin_inferred_on_open_for_thin_known_no_face():
    """Item 9: _open_session infers voice_only_origin=True for a known person
    whose gallery is thin and no face entry is in _presence_store."""
    import numpy as np, pipeline as _pl
    import inspect
    import asyncio

    src = inspect.getsource(_pl._open_session)
    assert "_has_recent_face_evidence" in src, (
        "Item 9: _open_session must call _has_recent_face_evidence in the heuristic"
    )
    assert "voice_only_origin" in src, (
        "Item 9: heuristic must set voice_only_origin in _open_session"
    )

    pid = "known_abc"
    saved = {}
    saved["active_room_session"] = _pl._pipeline_state_store.peek_active_room_session()

    try:
        await _pl._voice_gallery_store.set_gallery(pid, np.ones(192, dtype=np.float32), 2)  # thin gallery (< N_INITIAL_VOICE=5)
        # _presence_store is empty (autouse fixture) — no face evidence
        await _pl._pipeline_state_store.set_active_room_session("room_test")

        _pl._open_session(pid, "Lexi", "voice", "known", engagement_gate_passed=False)
        await asyncio.sleep(0)  # flush create_task(set_voice_only_origin) from _open_session

        snap = _pl._session_store.peek_snapshot(pid)
        assert snap is not None, "Session not opened"
        assert snap.voice_only_origin is True, (
            f"Expected voice_only_origin=True for thin known with no face, "
            f"got {snap.voice_only_origin!r}"
        )
    finally:
        await _pl._pipeline_state_store.set_active_room_session(saved["active_room_session"])


async def test_voice_only_origin_NOT_inferred_when_face_present_in_frame():
    """Item 9: heuristic does NOT fire when _presence_store has a recent
    face-sourced entry for the person — they have genuine face evidence."""
    import numpy as np, pipeline as _pl
    import time

    pid = "known_def"
    saved = {}
    saved["active_room_session"] = _pl._pipeline_state_store.peek_active_room_session()

    try:
        await _pl._voice_gallery_store.set_gallery(pid, np.ones(192, dtype=np.float32), 2)   # thin gallery
        # Face entry with recent timestamp via _presence_store
        await _pl._presence_store.upsert_face_recognition(pid, "Lexi", 0.5, time.time() - 1.0)
        await _pl._pipeline_state_store.set_active_room_session("room_test")

        _pl._open_session(pid, "Lexi", "face", "known", engagement_gate_passed=False)
        await asyncio.sleep(0)

        snap = _pl._session_store.peek_snapshot(pid)
        assert snap is not None
        assert snap.voice_only_origin is False, (
            "Heuristic must NOT infer voice_only_origin when face is present in frame"
        )
    finally:
        await _pl._pipeline_state_store.set_active_room_session(saved["active_room_session"])


async def test_voice_only_origin_NOT_inferred_when_gallery_mature():
    """Item 9: heuristic does NOT fire when the voice gallery is already at or
    above N_INITIAL_VOICE — no replenishment needed for a mature gallery."""
    import numpy as np, pipeline as _pl
    from core.config import N_INITIAL_VOICE

    pid = "known_ghi"
    saved = {}
    saved["active_room_session"] = _pl._pipeline_state_store.peek_active_room_session()

    try:
        await _pl._voice_gallery_store.set_gallery(pid, np.ones(192, dtype=np.float32), N_INITIAL_VOICE)  # mature gallery
        # _presence_store is empty (autouse fixture) — no face evidence
        await _pl._pipeline_state_store.set_active_room_session("room_test")

        _pl._open_session(pid, "Lexi", "voice", "known", engagement_gate_passed=False)
        await asyncio.sleep(0)

        snap = _pl._session_store.peek_snapshot(pid)
        assert snap is not None
        assert snap.voice_only_origin is False, (
            "Heuristic must NOT fire when gallery is already mature "
            f"(voice_n={N_INITIAL_VOICE} >= N_INITIAL_VOICE={N_INITIAL_VOICE})"
        )
    finally:
        await _pl._pipeline_state_store.set_active_room_session(saved["active_room_session"])


async def test_voice_only_origin_NOT_inferred_for_disputed_session():
    """Item 9: heuristic excludes disputed sessions — don't backfill someone
    whose identity we don't currently trust."""
    import numpy as np, pipeline as _pl

    pid = "disputed_jkl"
    saved = {}
    saved["active_room_session"] = _pl._pipeline_state_store.peek_active_room_session()

    try:
        await _pl._voice_gallery_store.set_gallery(pid, np.ones(192, dtype=np.float32), 2)   # thin gallery
        # _presence_store is empty (autouse fixture) — no face evidence
        await _pl._pipeline_state_store.set_active_room_session("room_test")

        _pl._open_session(pid, "Unknown", "voice", "disputed", engagement_gate_passed=False)
        await asyncio.sleep(0)

        snap = _pl._session_store.peek_snapshot(pid)
        assert snap is not None
        assert snap.voice_only_origin is False, (
            "Heuristic must NOT infer voice_only_origin for disputed sessions"
        )
    finally:
        await _pl._pipeline_state_store.set_active_room_session(saved["active_room_session"])


def test_voice_only_origin_explicit_true_preserved_over_heuristic():
    """Item 9: heuristic does NOT override an explicitly-set voice_only_origin=True.

    The S120 engagement-gate path sets it True before _open_session is ever called
    (via _active_sessions[pid]["voice_only_origin"] = True at line ~6395). This is
    defensive: the heuristic's 'not session_dict.get("voice_only_origin")' guard must
    ensure S120's explicit-True survives even when the heuristic conditions would
    otherwise trigger (thin gallery, no face). The heuristic should be idempotent —
    a second open with all conditions met should not toggle the flag.
    """
    import pipeline as _pl

    # Verify the guard is present in source
    import inspect
    src = inspect.getsource(_pl._open_session)
    assert "_session_store.peek_snapshot(person_id).voice_only_origin" in src, (
        "Item 9: heuristic must guard with "
        "'_session_store.peek_snapshot(person_id).voice_only_origin' "
        "so explicit True is preserved"
    )

    import numpy as np, time as _t, asyncio as _aio

    pid = "known_mno"
    now = _t.time()
    saved = {}
    saved["active_room_session"] = _pl._pipeline_state_store.peek_active_room_session()

    try:
        _aio.run(_pl._voice_gallery_store.set_gallery(pid, np.ones(192, dtype=np.float32), 1))   # very thin gallery — heuristic would fire
        # _presence_store is empty (autouse fixture) — no face — heuristic would fire
        _aio.run(_pl._pipeline_state_store.set_active_room_session("room_test"))

        # Simulate S120 explicitly setting voice_only_origin=True before _open_session
        _pl._session_store._sessions.pop(pid, None)
        _aio.run(_pl._session_store.open_session(pid, "Lexi", "known", "voice", now=now))
        _aio.run(_pl._session_store.set_voice_only_origin(pid, True))
        snap_before = _pl._session_store.peek_snapshot(pid)
        assert snap_before is not None and snap_before.voice_only_origin is True

        # Call _open_session — heuristic conditions are met (thin gallery, no face)
        # but the guard must prevent re-firing since voice_only_origin is already True
        _pl._open_session(pid, "Lexi", "voice", "known", engagement_gate_passed=False)
        snap_after = _pl._session_store.peek_snapshot(pid)
        assert snap_after is not None and snap_after.voice_only_origin is True, (
            "Explicit voice_only_origin=True must survive _open_session re-entry"
        )
    finally:
        _aio.run(_pl._pipeline_state_store.set_active_room_session(saved["active_room_session"]))
        _pl._session_store._sessions.pop(pid, None)
