"""test_pipeline_dispute — dispute tests (split from test_pipeline.py, P1.A1 SP-1).

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


def test_dispute_auto_clear_on_three_consecutive_strong_voice_matches():
    """Bug D1: when a disputed session sees 3 consecutive voice_match_conf
    ≥ DISPUTE_AUTO_CLEAR_VOICE_SOLO_MIN (0.85 when no face), the dispute
    clears and person_type restores to prior_person_type. Without this fix,
    disputes lingered for the full 180s DISPUTE_MAX_DURATION.
    Session 73 post-review Medium C2: voice-only clear uses SOLO_MIN."""
    import asyncio, time, pipeline
    pid = "jagan_p1"
    now = time.time()
    asyncio.run(pipeline._session_store.open_session(pid, "Jagan", "known", "face", now=now))
    asyncio.run(pipeline._session_store.transition_to_disputed(pid, None, "test", now=now - 30))
    for conf in [0.87, 0.90, 0.88]:
        asyncio.run(pipeline._session_store.append_voice_conf(pid, conf=conf))
    pipeline._persons_in_frame = {}
    orig_orch = pipeline._brain_orchestrator
    pipeline._brain_orchestrator = None
    try:
        pipeline._expire_stale_sessions()
        snap = pipeline._session_store.peek_snapshot(pid)
        assert snap is not None, "session must NOT be force-closed; dispute cleared instead"
        assert snap.person_type == "known", "must restore to prior_person_type"
        assert snap.dispute_reason is None
        assert snap.dispute_set_at is None
        assert snap.prior_person_type is None
    finally:
        pipeline._persons_in_frame = {}
        pipeline._brain_orchestrator = orig_orch


def test_dispute_auto_clear_restores_best_friend_not_known():
    """Bug D1 critical safety: when the victim of a wrongly-fired dispute is
    a best_friend, auto-clear must restore best_friend — NOT demote to
    generic known. prior_person_type is the authoritative record.
    Uses ≥ SOLO_MIN (0.85) voice confs since no face corroboration here."""
    import asyncio, time, pipeline
    pid = "jagan_bf"
    now = time.time()
    asyncio.run(pipeline._session_store.open_session(pid, "Jagan", "best_friend", "face", now=now))
    asyncio.run(pipeline._session_store.transition_to_disputed(pid, None, "test", now=now - 30))
    for conf in [0.86, 0.89, 0.92]:
        asyncio.run(pipeline._session_store.append_voice_conf(pid, conf=conf))
    pipeline._persons_in_frame = {}
    orig_orch = pipeline._brain_orchestrator
    pipeline._brain_orchestrator = None
    try:
        pipeline._expire_stale_sessions()
        snap = pipeline._session_store.peek_snapshot(pid)
        assert snap is not None
        assert snap.person_type == "best_friend"
    finally:
        pipeline._persons_in_frame = {}
        pipeline._brain_orchestrator = orig_orch


def test_dispute_auto_clear_requires_three_consecutive_not_two():
    """Bug D1 safety: clearing after only 2 strong matches is too aggressive.
    Asymmetric blast radius — the test pinned at 3 consecutive prevents a
    pair of lucky-good matches from prematurely reopening the victim's facts."""
    import asyncio, time, pipeline
    pid = "p1"
    now = time.time()
    asyncio.run(pipeline._session_store.open_session(pid, "Jagan", "known", "face", now=now))
    asyncio.run(pipeline._session_store.transition_to_disputed(pid, None, "test", now=now - 10))
    for conf in [0.75, 0.80]:  # only 2 strong matches — must NOT clear
        asyncio.run(pipeline._session_store.append_voice_conf(pid, conf=conf))
    orig_orch = pipeline._brain_orchestrator
    pipeline._brain_orchestrator = None
    try:
        pipeline._expire_stale_sessions()
        snap = pipeline._session_store.peek_snapshot(pid)
        assert snap is not None
        assert snap.person_type == "disputed", (
            "only 2 strong matches must NOT clear dispute — need 3 consecutive"
        )
    finally:
        pipeline._brain_orchestrator = orig_orch


def test_dispute_auto_clear_rejects_mixed_weak_matches():
    """Bug D1: one sub-threshold score in the last 3 blocks clearance.
    'all(c >= threshold)' enforces consecutive strength, not avg."""
    import asyncio, time, pipeline
    pid = "p1"
    now = time.time()
    asyncio.run(pipeline._session_store.open_session(pid, "Jagan", "known", "face", now=now))
    asyncio.run(pipeline._session_store.transition_to_disputed(pid, None, "test", now=now - 10))
    for conf in [0.80, 0.50, 0.80]:  # mid below floor
        asyncio.run(pipeline._session_store.append_voice_conf(pid, conf=conf))
    orig_orch = pipeline._brain_orchestrator
    pipeline._brain_orchestrator = None
    try:
        pipeline._expire_stale_sessions()
        snap = pipeline._session_store.peek_snapshot(pid)
        assert snap is not None
        assert snap.person_type == "disputed"
    finally:
        pipeline._brain_orchestrator = orig_orch


def test_dispute_auto_clear_on_face_in_frame_with_strong_conf():
    """Bug D1 second clear path: if holder's face is in frame AND
    face_match_conf ≥ 0.70, dispute clears (sensor has strong confirmation)."""
    import asyncio, time, pipeline
    pid = "p1"
    now = time.time()
    asyncio.run(pipeline._session_store.open_session(
        pid, "Jagan", "known", "face", now=now))
    asyncio.run(pipeline._session_store.transition_to_disputed(
        pid, None, "test", now=now - 10))
    asyncio.run(pipeline._session_store.update_face_seen(
        pid, conf=0.85, ts=now, anti_spoof_live=True, anti_spoof_score=0.9))
    asyncio.run(pipeline._presence_store.upsert_face_recognition(pid, "Jagan", 0.85, now))
    orig_orch = pipeline._brain_orchestrator
    pipeline._brain_orchestrator = None
    try:
        pipeline._expire_stale_sessions()
        snap = pipeline._session_store.peek_snapshot(pid)
        assert snap is not None, "session must not be force-closed"
        assert snap.person_type == "known", (
            f"face clear path must restore prior_person_type='known'; got {snap.person_type!r}"
        )
        assert snap.dispute_reason is None
        assert snap.dispute_set_at is None
    finally:
        asyncio.run(pipeline._presence_store.remove(pid))
        pipeline._brain_orchestrator = orig_orch


def test_dispute_auto_clear_voice_only_requires_higher_threshold():
    """Session 73 post-review Medium C2: voice auto-clear trusts the same
    sensor that triggered the dispute. Without face corroboration, voice
    scores of 0.70–0.85 must NOT clear the dispute (too close to the baseline
    biometric threshold — an attacker who scores 0.70 against the victim
    could silently reclaim authority). Raise the bar to SOLO_MIN (0.85) when
    face isn't co-present."""
    import asyncio, time, pipeline
    from core.config import (
        DISPUTE_AUTO_CLEAR_VOICE_MIN,
        DISPUTE_AUTO_CLEAR_VOICE_SOLO_MIN,
    )
    # Sanity: the two thresholds must differ, else the differentiation is moot.
    assert DISPUTE_AUTO_CLEAR_VOICE_SOLO_MIN > DISPUTE_AUTO_CLEAR_VOICE_MIN, (
        "SOLO_MIN must be strictly higher than the face-corroborated MIN"
    )
    pid = "p1"
    now = time.time()
    asyncio.run(pipeline._session_store.open_session(
        pid, "Jagan", "known", "voice", now=now))
    asyncio.run(pipeline._session_store.transition_to_disputed(
        pid, None, "test", now=now - 30))
    # 3 consecutive matches ≥ MIN (0.70) but below SOLO_MIN (0.85)
    for conf in [0.72, 0.78, 0.75]:
        asyncio.run(pipeline._session_store.append_voice_conf(pid, conf=conf))
    # NO face corroboration — presence store left empty
    orig_orch = pipeline._brain_orchestrator
    pipeline._brain_orchestrator = None
    try:
        pipeline._expire_stale_sessions()
        snap = pipeline._session_store.peek_snapshot(pid)
        assert snap is not None
        assert snap.person_type == "disputed", (
            "voice-only clear must require ≥ SOLO_MIN (0.85), not MIN (0.70); "
            "0.72/0.78/0.75 must stay disputed when no face is present"
        )
    finally:
        pipeline._brain_orchestrator = orig_orch


def test_dispute_auto_clear_voice_only_at_solo_threshold():
    """Medium C2: 3 consecutive ≥ SOLO_MIN (0.85) DOES clear even without face."""
    import asyncio, time, pipeline
    pid = "p1"
    now = time.time()
    asyncio.run(pipeline._session_store.open_session(
        pid, "Jagan", "known", "voice", now=now))
    asyncio.run(pipeline._session_store.transition_to_disputed(
        pid, None, "test", now=now - 30))
    for conf in [0.86, 0.88, 0.90]:
        asyncio.run(pipeline._session_store.append_voice_conf(pid, conf=conf))
    # NO face in frame — presence store left empty
    orig_orch = pipeline._brain_orchestrator
    pipeline._brain_orchestrator = None
    try:
        pipeline._expire_stale_sessions()
        snap = pipeline._session_store.peek_snapshot(pid)
        assert snap is not None
        assert snap.person_type == "known", (
            f"3 consecutive ≥ SOLO_MIN must clear dispute; got {snap.person_type!r}"
        )
    finally:
        pipeline._brain_orchestrator = orig_orch


def test_dispute_auto_clear_voice_with_face_uses_lower_min():
    """Medium C2: when face is co-present with face_match_conf ≥ MIN, the
    voice floor DROPS to MIN (0.70) — two independent sensors confirming
    is stronger than one sensor alone, so we don't need SOLO-level voice."""
    import asyncio, time, pipeline
    pid = "p1"
    now = time.time()
    asyncio.run(pipeline._session_store.open_session(
        pid, "Jagan", "known", "face", now=now))
    asyncio.run(pipeline._session_store.transition_to_disputed(
        pid, None, "test", now=now - 30))
    # voice confs below SOLO_MIN but ≥ MIN (0.70) — only enough with face
    for conf in [0.72, 0.78, 0.75]:
        asyncio.run(pipeline._session_store.append_voice_conf(pid, conf=conf))
    asyncio.run(pipeline._session_store.update_face_seen(
        pid, conf=0.80, ts=now, anti_spoof_live=True, anti_spoof_score=0.9))
    # Face IS in frame with confident face_match_conf
    asyncio.run(pipeline._presence_store.upsert_face_recognition(pid, "Jagan", 0.80, now))
    orig_orch = pipeline._brain_orchestrator
    pipeline._brain_orchestrator = None
    try:
        pipeline._expire_stale_sessions()
        snap = pipeline._session_store.peek_snapshot(pid)
        assert snap is not None
        # With face corroboration, voice-MIN (0.70) suffices; scores pass; clear.
        assert snap.person_type == "known", (
            f"face corroboration should lower voice floor to MIN; got {snap.person_type!r}"
        )
    finally:
        asyncio.run(pipeline._presence_store.remove(pid))
        pipeline._brain_orchestrator = orig_orch


def test_dispute_auto_clear_defaults_to_stranger_when_prior_missing():
    """Session 73 post-review Critical #2: if a future dispute-flip path
    forgets to capture prior_person_type, the auto-clear restore must
    default to 'stranger' (safer), NOT 'known' (privilege escalation).
    A stranger that loses auth can re-establish via engagement gate on the
    next turn; a stranger wrongly promoted to 'known' keeps those privileges
    silently until the next session close."""
    import asyncio, time, pipeline
    pid = "x1"
    now = time.time()
    # Open DIRECTLY as disputed WITHOUT transition_to_disputed so prior_person_type stays None.
    asyncio.run(pipeline._session_store.open_session(
        pid, "visitor", "disputed", "voice", now=now))
    # Manually set dispute_set_at so the auto-clear timer is satisfied.
    asyncio.run(pipeline._session_store.set_dispute_set_at(pid, now - 30))
    # ≥ SOLO_MIN (0.85) since no face corroboration here.
    for conf in [0.86, 0.90, 0.88]:
        asyncio.run(pipeline._session_store.append_voice_conf(pid, conf=conf))
    pipeline._persons_in_frame = {}
    orig_orch = pipeline._brain_orchestrator
    pipeline._brain_orchestrator = None
    try:
        pipeline._expire_stale_sessions()
        snap = pipeline._session_store.peek_snapshot(pid)
        assert snap is not None, "session should survive the clear"
        assert snap.person_type == "stranger", (
            "missing prior_person_type must default to 'stranger' (fail-closed); "
            f"got {snap.person_type!r} — this is the Critical #2 privilege escalation"
        )
    finally:
        pipeline._persons_in_frame = {}
        pipeline._brain_orchestrator = orig_orch


def test_dispute_auto_clear_thresholds_in_config():
    """Bug D1: thresholds must live in config, not as inline literals.
    Guards against someone hardcoding different values here and the
    auto-clear test file getting out of sync."""
    from core.config import DISPUTE_AUTO_CLEAR_VOICE_MIN, DISPUTE_AUTO_CLEAR_CONSECUTIVE_TURNS
    # Reviewer's D1 decision: 0.70 + 3 consecutive (asymmetric blast radius).
    assert 0.65 <= DISPUTE_AUTO_CLEAR_VOICE_MIN <= 0.80
    assert 2 <= DISPUTE_AUTO_CLEAR_CONSECUTIVE_TURNS <= 5


def test_expire_lazily_anchors_missing_dispute_set_at():
    """Finding K — if a future path flips person_type to 'disputed' without setting
    dispute_set_at, _expire_stale_sessions must lazily anchor it on first check
    so the timeout eventually fires (instead of permanently deferring)."""
    import time, pipeline, asyncio as _asl
    pid = "jagan_k_test"
    # open_session with person_type="disputed" creates session with dispute_set_at=None
    # (transition_to_disputed was never called) — this is the future-path-bug scenario.
    _asl.run(pipeline._session_store.open_session(
        pid, "Jagan", "disputed", "face", now=time.time()
    ))
    try:
        pipeline._expire_stale_sessions()
        # Session still open (timeout hasn't elapsed yet) but dispute_set_at is now anchored
        assert pipeline._session_store.peek_snapshot(pid) is not None
        assert pipeline._session_store.peek_snapshot(pid).dispute_set_at is not None
    finally:
        _asl.run(pipeline._session_store.close_session(pid))


async def test_dispute_rename_block_increments_counter():
    """N3 — each disputed-rename block increments the session's counter so
    persistent bursts can be detected."""
    import asyncio, pipeline
    from pipeline import _execute_tool
    import time as _t
    pid = "jagan_n3a"
    now = _t.time()
    orig_orch = pipeline._brain_orchestrator
    pipeline._brain_orchestrator = MagicMock()
    try:
        await pipeline._session_store.open_session(pid, "Jagan", "known", "face", now=now)
        await pipeline._session_store.transition_to_disputed(pid, None, "speaker claims not Jagan", now=now)
        await pipeline._conversation_store.set_history(pid, [])
        mock_db = MagicMock()
        await _execute_tool("update_person_name", {"name": "Venkat"},
                            pid, "Jagan", db=mock_db,
                            user_text="my name is Venkat")
        await asyncio.sleep(0)
        assert pipeline._session_store.peek_snapshot(pid).disputed_block_count == 1
        await pipeline._session_store.update_tool_repeat(pid, None, 0)
        await _execute_tool("update_person_name", {"name": "Venkat"},
                            pid, "Jagan", db=mock_db,
                            user_text="my name is Venkat")
        await asyncio.sleep(0)
        assert pipeline._session_store.peek_snapshot(pid).disputed_block_count == 2
    finally:
        pipeline._brain_orchestrator = orig_orch


async def test_dispute_rename_burst_fires_watchdog_at_threshold():
    """N3 — on the 3rd blocked attempt (threshold), watchdog fires once; the
    4th attempt keeps counting but does not re-fire."""
    import pipeline
    from pipeline import _execute_tool
    from core.config import DISPUTE_RENAME_BLOCK_THRESHOLD
    import time as _t
    pid = "jagan_n3b"
    now = _t.time()
    await pipeline._session_store.open_session(pid, "Jagan", "known", "face", now=now)
    await pipeline._session_store.transition_to_disputed(pid, None, "speaker claims not Jagan", now=now)
    await pipeline._conversation_store.set_history(pid, [])
    orig_orch = pipeline._brain_orchestrator
    mock_orch = MagicMock()
    pipeline._brain_orchestrator = mock_orch
    try:
        import asyncio as _asyncio
        mock_db = MagicMock()
        # 1st and 2nd blocks — below threshold. Reset the tool-repeat guard
        # between calls to simulate a per-turn boundary. asyncio.sleep(0) lets
        # the create_task(increment_block_count) coroutines actually execute.
        for _ in range(DISPUTE_RENAME_BLOCK_THRESHOLD - 1):
            await _execute_tool("update_person_name", {"name": "Venkat"},
                                pid, "Jagan", db=mock_db,
                                user_text="my name is Venkat")
            await _asyncio.sleep(0)
            await pipeline._session_store.update_tool_repeat(pid, None, 0)
        mock_orch.report_dispute_rename_burst.assert_not_called()
        # 3rd block — hits threshold, alert fires
        await _execute_tool("update_person_name", {"name": "Venkat"},
                            pid, "Jagan", db=mock_db,
                            user_text="my name is Venkat")
        await _asyncio.sleep(0)
        await pipeline._session_store.update_tool_repeat(pid, None, 0)
        assert mock_orch.report_dispute_rename_burst.call_count == 1
        call_kwargs = mock_orch.report_dispute_rename_burst.call_args.kwargs
        assert call_kwargs["victim_pid"]         == pid
        assert call_kwargs["victim_name"]        == "Jagan"
        assert call_kwargs["victim_person_type"] == "known"
        assert call_kwargs["claimed_name"]       == "Venkat"
        assert call_kwargs["block_count"]        == DISPUTE_RENAME_BLOCK_THRESHOLD
        # 4th block — counter increments but no re-fire
        await _execute_tool("update_person_name", {"name": "Venkat"},
                            pid, "Jagan", db=mock_db,
                            user_text="my name is Venkat")
        await _asyncio.sleep(0)
        assert pipeline._session_store.peek_snapshot(pid).disputed_block_count == DISPUTE_RENAME_BLOCK_THRESHOLD + 1
        assert mock_orch.report_dispute_rename_burst.call_count == 1
    finally:
        pipeline._brain_orchestrator = orig_orch


async def test_dispute_rename_burst_severity_critical_for_best_friend(tmp_path):
    """N3 — when victim is best_friend, stored watchdog_alerts row has severity='critical'.
    Regular known persons get severity='warning'."""
    import pipeline
    from pipeline import _execute_tool
    from core.config import DISPUTE_RENAME_BLOCK_THRESHOLD
    from core.brain_agent import BrainOrchestrator, WatchdogAgent, BrainDB
    import asyncio as _asyncio
    import time as _t

    # Minimal orchestrator with a real BrainDB + WatchdogAgent so store_alert lands in SQLite
    brain_db = BrainDB(tmp_path / "brain.db")
    orch = BrainOrchestrator.__new__(BrainOrchestrator)
    orch._brain_db        = brain_db
    orch._shutdown        = _asyncio.Event()
    orch._trigger         = _asyncio.Event()
    orch._disputed_persons = set()
    orch._watchdog        = WatchdogAgent(brain_db, None)

    pid_bf = "jagan_bf_n3c"
    now_bf = _t.time()
    await pipeline._session_store.open_session(pid_bf, "Jagan", "best_friend", "face", now=now_bf)
    await pipeline._session_store.transition_to_disputed(pid_bf, None, "speaker claims not Jagan", now=now_bf)
    await pipeline._conversation_store.set_history(pid_bf, [])
    orig_orch = pipeline._brain_orchestrator
    pipeline._brain_orchestrator = orch
    try:
        mock_db = MagicMock()
        for _ in range(DISPUTE_RENAME_BLOCK_THRESHOLD):
            await _execute_tool("update_person_name", {"name": "Attacker"},
                                pid_bf, "Jagan", db=mock_db,
                                user_text="my name is Attacker")
            await _asyncio.sleep(0)
            await pipeline._session_store.update_tool_repeat(pid_bf, None, 0)
        # Inspect stored alerts
        row = brain_db._conn.execute(
            "SELECT alert_type, severity, message FROM watchdog_alerts ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        assert row[0] == "DISPUTE_RENAME_BURST"
        assert row[1] == "critical"
        assert "Jagan" in row[2]
        assert "Attacker" in row[2]
    finally:
        pipeline._brain_orchestrator = orig_orch
        brain_db.close()


async def test_dispute_timeout_forces_session_close():
    """A disputed session older than DISPUTE_MAX_DURATION must be expired even if
    vision is still (wrongly) refreshing last_face_seen."""
    import time, pipeline
    from core.config import DISPUTE_MAX_DURATION

    pid = "jagan_dispute_timeout_test"
    now = time.time()
    await pipeline._session_store.open_session(pid, "Jagan", "known", "face", now=now)
    await pipeline._session_store.transition_to_disputed(pid, None, "test", now=now)
    # #5 Slice B (§0.1.3): DISPUTE_MAX_DURATION reads the MONOTONIC companion now (the wall
    # dispute_set_at is retained only for the persisted watchdog display). Backdate the mono
    # companion so the elapsed-math timeout fires (a past WALL dispute_set_at no longer drives
    # the timer — this test previously encoded the wall clock).
    await pipeline._session_store.set_dispute_set_at(
        pid, now - (DISPUTE_MAX_DURATION + 10),
        ts_monotonic=time.monotonic() - (DISPUTE_MAX_DURATION + 10))
    pipeline._expire_stale_sessions()
    await asyncio.sleep(0)
    assert pipeline._session_store.peek_snapshot(pid) is None, \
        "Disputed session should have been force-closed after DISPUTE_MAX_DURATION"


def test_dispute_within_timeout_not_force_closed():
    """A disputed session still within DISPUTE_MAX_DURATION must not be force-closed."""
    import asyncio, time, pipeline

    pid = "jagan_dispute_fresh_test"
    now = time.time()
    asyncio.run(pipeline._session_store.open_session(pid, "Jagan", "known", "face", now=now))
    asyncio.run(pipeline._session_store.transition_to_disputed(pid, None, "test", now=now))
    pipeline._expire_stale_sessions()
    assert pipeline._session_store.peek_snapshot(pid) is not None, \
        "Fresh disputed session should not be force-closed"
