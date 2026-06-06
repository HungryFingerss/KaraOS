"""test_pipeline_enrollment — enrollment tests (split from test_pipeline.py, P1.A1 SP-1).

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


def _fake_frame():
    return np.zeros((200, 200, 3), dtype=np.uint8)


def _fake_det():
    det = MagicMock()
    det.bbox = (10, 10, 90, 90)
    det.landmarks = None  # skip yaw branch
    return det


async def test_first_boot_flow_antispoof_blocks_all_frames():
    """All frames rejected by anti-spoof → person NOT enrolled, spoof message spoken."""
    import pipeline

    camera = MagicMock()
    camera.capture_frames_async = AsyncMock(return_value=[_fake_frame()] * 5)
    detector = MagicMock()
    detector.detect = MagicMock(return_value=[_fake_det()])
    embedder = MagicMock()
    db = MagicMock()

    spoof_checker = MagicMock()
    spoof_checker.is_live.return_value = False

    spoken = []

    with patch("pipeline._anti_spoof_checker", spoof_checker), \
         patch("pipeline.speak", new=AsyncMock(side_effect=lambda t, **kw: spoken.append(t))), \
         patch("pipeline.listen_and_transcribe", new=AsyncMock(side_effect=[
             ("yes", None, None),
             ("Jagan", None, None),
         ])), \
         patch("pipeline.face_quality_score", return_value=1.0), \
         patch("pipeline._set_state"), \
         patch("cv2.imwrite"):
        await pipeline.first_boot_flow(camera, detector, embedder, db)

    db.add_person.assert_not_called()
    assert any("real person" in t.lower() for t in spoken), \
        f"Expected spoof rejection message, got: {spoken}"


async def test_first_boot_flow_antispoof_none_enrolls_normally():
    """When _anti_spoof_checker is None (disabled), best friend is enrolled."""
    import pipeline

    camera = MagicMock()
    camera.capture_frames_async = AsyncMock(return_value=[_fake_frame()] * 5)
    detector = MagicMock()
    detector.detect = MagicMock(return_value=[_fake_det()])
    embedder = MagicMock()
    embedder.embed = MagicMock(return_value=np.zeros(512))
    db = MagicMock()
    db.add_embedding = MagicMock(return_value=True)

    spoken = []

    with patch("pipeline._anti_spoof_checker", None), \
         patch("pipeline.speak", new=AsyncMock(side_effect=lambda t, **kw: spoken.append(t))), \
         patch("pipeline.listen_and_transcribe", new=AsyncMock(side_effect=[
             ("yes", None, None),
             ("Jagan", None, None),
         ])), \
         patch("pipeline.face_quality_score", return_value=1.0), \
         patch("pipeline._set_state"), \
         patch("cv2.imwrite"):
        await pipeline.first_boot_flow(camera, detector, embedder, db)

    db.add_person.assert_called_once()
    assert db.add_person.call_args.kwargs.get("person_type") == "best_friend"


async def test_enrollment_flow_antispoof_blocks_all_frames():
    """All frames rejected by anti-spoof → person NOT enrolled, spoof message spoken."""
    import pipeline

    camera = MagicMock()
    camera.capture_frames_async = AsyncMock(return_value=[_fake_frame()] * 5)
    detector = MagicMock()
    detector.detect = MagicMock(return_value=[_fake_det()])
    embedder = MagicMock()
    db = MagicMock()

    spoof_checker = MagicMock()
    spoof_checker.is_live.return_value = False

    spoken = []

    with patch("pipeline._anti_spoof_checker", spoof_checker), \
         patch("pipeline.speak", new=AsyncMock(side_effect=lambda t, **kw: spoken.append(t))), \
         patch("pipeline.face_quality_score", return_value=1.0), \
         patch("pipeline._set_state"), \
         patch("cv2.imwrite"):
        await pipeline.enrollment_flow("Ajay", camera, detector, embedder, db)

    db.add_person.assert_not_called()
    assert any("real person" in t.lower() for t in spoken), \
        f"Expected spoof rejection message, got: {spoken}"


async def test_enrollment_flow_antispoof_none_enrolls_normally():
    """When _anti_spoof_checker is None (disabled), person is enrolled."""
    import pipeline

    camera = MagicMock()
    camera.capture_frames_async = AsyncMock(return_value=[_fake_frame()] * 5)
    detector = MagicMock()
    detector.detect = MagicMock(return_value=[_fake_det()])
    embedder = MagicMock()
    embedder.embed = MagicMock(return_value=np.zeros(512))
    db = MagicMock()
    db.add_embedding = MagicMock(return_value=True)

    spoken = []

    with patch("pipeline._anti_spoof_checker", None), \
         patch("pipeline.speak", new=AsyncMock(side_effect=lambda t, **kw: spoken.append(t))), \
         patch("pipeline.face_quality_score", return_value=1.0), \
         patch("pipeline._set_state"), \
         patch("cv2.imwrite"):
        await pipeline.enrollment_flow("Ajay", camera, detector, embedder, db)

    db.add_person.assert_called_once()


@pytest.mark.asyncio
async def test_first_boot_not_triggered_when_strangers_exist(tmp_path):
    """If strangers are in DB but no best_friend, first_boot must NOT re-fire."""
    import pipeline
    from core.db import FaceDB

    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))
    db.add_stranger("visitor")

    # list_people() returns ≥1 row → first_boot must not be triggered
    assert db.list_people()           # strangers present
    assert not db.is_best_friend_enrolled()  # but no best_friend yet

    # The new gate condition
    should_first_boot = not db.list_people()
    assert should_first_boot is False  # correctly skips first_boot
    db._conn.close()


@pytest.mark.asyncio
async def test_first_boot_triggered_on_truly_empty_db(tmp_path):
    """When DB has zero persons, first_boot condition must fire."""
    import pipeline
    from core.db import FaceDB

    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))

    assert not db.list_people()       # completely empty
    should_first_boot = not db.list_people()
    assert should_first_boot is True  # correctly triggers first_boot
    db._conn.close()


async def test_enrollment_mishear_widened_accepts_deny_identity_intent():
    """Session 101 Bug F.2 (CRITICAL): re-canary 2026-04-23 at turn 1
    had STT mangle "Jagan" → "Jawan" at enrollment. Jagan's natural
    correction "No, it's not Javan, it's Jagan, J-A-G-A-N." classified
    as `deny_identity` (linguistically correct — denial + correction)
    NOT `assign_own_name`. The original Session 100 Bug F escape hatch
    ran AFTER `_intent_allows`, which rejects `deny_identity` on
    `update_person_name` → rename never fired. This widened path must
    accept `deny_identity` during the fresh-enrollment window as long
    as the extracted value is grounded in user_text."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    await pipeline._session_store.open_session("jawan_abc", "Jawan", "best_friend", "face", now=_t.time() - 30)
    await pipeline._conversation_store.set_history("jawan_abc", [])
    mock_db = MagicMock()
    mock_db.voice_embedding_count.return_value = 0  # fresh enrollment

    orig_orch = pipeline._brain_orchestrator
    mock_orch = MagicMock()
    _wiring._brain_orchestrator = mock_orch
    try:
        result = await _execute_tool(
            "update_person_name", {"name": "Jagan"},
            "jawan_abc", "Jawan", db=mock_db,
            user_text="No, it's not Javan, it's Jagan, J-A-G-A-N.",
            intent_sidecar={
                "turn_intent": "deny_identity",
                "confidence": 0.95,
                "extracted_value": "Jagan",
            },
        )
    finally:
        _wiring._brain_orchestrator = orig_orch

    assert result == "handled"
    mock_db.update_person_name.assert_called_once_with("jawan_abc", "Jagan")
    await __import__("asyncio").sleep(0)  # flush _session_store.rename create_task
    snap = pipeline._session_store.peek_snapshot("jawan_abc")
    assert snap.person_name == "Jagan"
    assert snap.person_type == "best_friend", (
        "Bug F.2 must preserve person_type — it's a name correction, not "
        "a privilege change"
    )
    mock_orch.on_identity_confirmed.assert_called_once_with(
        "jawan_abc", "Jawan", "Jagan",
    )


async def test_enrollment_mishear_widened_accepts_confirm_identity():
    """Session 101 Bug F.2: re-canary turn 3 — after the correction
    attempt above failed, Jagan said "Yeah, correct" which classified
    as `confirm_identity`. Widened escape hatch accepts this intent
    too so recovery path from a prior failed correction works without
    user needing to restate 'my name is Jagan' in a specific phrasing."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    await pipeline._session_store.open_session("jawan_abc", "Jawan", "best_friend", "face", now=_t.time() - 30)
    await pipeline._conversation_store.set_history("jawan_abc", [])
    mock_db = MagicMock()
    mock_db.voice_embedding_count.return_value = 0

    orig_orch = pipeline._brain_orchestrator
    mock_orch = MagicMock()
    _wiring._brain_orchestrator = mock_orch
    try:
        result = await _execute_tool(
            "update_person_name", {"name": "Jagan"},
            "jawan_abc", "Jawan", db=mock_db,
            user_text="Yeah that's right, I'm Jagan.",
            intent_sidecar={
                "turn_intent": "confirm_identity",
                "confidence": 0.95,
                "extracted_value": "Jagan",
            },
        )
    finally:
        _wiring._brain_orchestrator = orig_orch

    assert result == "handled"
    mock_db.update_person_name.assert_called_once_with("jawan_abc", "Jagan")


async def test_enrollment_mishear_widened_rejects_ungrounded_extracted_value():
    """Session 101 Bug F.2 safety: even during the enrollment window,
    the widened escape hatch MUST reject if the classifier's
    extracted_value isn't actually present in user_text. Without the
    grounding check, any high-confidence classification on a fresh
    session would let the LLM hallucinate a name."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    await pipeline._session_store.open_session("jawan_abc", "Jawan", "best_friend", "face", now=_t.time() - 30)
    await pipeline._conversation_store.set_history("jawan_abc", [])
    mock_db = MagicMock()
    mock_db.voice_embedding_count.return_value = 0

    orig_orch = pipeline._brain_orchestrator
    _wiring._brain_orchestrator = MagicMock()
    try:
        # user_text does NOT contain "Attacker" → ungrounded
        await _execute_tool(
            "update_person_name", {"name": "Attacker"},
            "jawan_abc", "Jawan", db=mock_db,
            user_text="hello, how are you today?",
            intent_sidecar={
                "turn_intent": "deny_identity",
                "confidence": 0.95,
                "extracted_value": "Attacker",
            },
        )
    finally:
        _wiring._brain_orchestrator = orig_orch

    # Widened path did NOT fire; falls through to normal gate.
    mock_db.update_person_name.assert_not_called()


async def test_enrollment_mishear_escape_hatch_renames_fresh_best_friend():
    """Session 100 Bug F (CRITICAL): STT mishear at first boot wrote
    "Gevan" instead of "Jagan" in 2026-04-23 canary. The corrective
    "No, my name is Jagan" landed on a best_friend session whose only
    corroboration was the face match — voice profile was empty, session
    was seconds old. The classic dispute-flip was wrong here; the rename
    must succeed via the stranger-promotion chain while preserving
    person_type='best_friend'."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    await pipeline._session_store.open_session("jagan_bf", "Gevan", "best_friend", "face", now=_t.time() - 30)
    # Canary #3 PI-1: pin the in-window turn count EXPLICITLY (was the incidental default 0).
    # user_turns=1 is within ENROLLMENT_RENAME_MAX_TURNS (3) — a genuine turn-1 enrollment
    # mishear correction MUST still rename through the escape hatch after B1.
    pipeline._session_store._sessions["jagan_bf"].user_turns = 1
    await pipeline._conversation_store.set_history("jagan_bf", [])
    mock_db = MagicMock()
    mock_db.voice_embedding_count.return_value = 0  # no voice samples yet

    orig_orch = pipeline._brain_orchestrator
    mock_orch = MagicMock()
    _wiring._brain_orchestrator = mock_orch
    try:
        result = await _execute_tool(
            "update_person_name", {"name": "Jagan"},
            "jagan_bf", "Gevan", db=mock_db,
            user_text="No, my name is Jagan",
        )
    finally:
        _wiring._brain_orchestrator = orig_orch

    assert result == "handled"
    # Rename fires on the real DB row.
    mock_db.update_person_name.assert_called_once_with("jagan_bf", "Jagan")
    # But person_type is NOT flipped to 'known' (it's a NAME correction,
    # not a privilege change — best_friend stays best_friend).
    mock_db.update_person_type.assert_not_called()
    await __import__("asyncio").sleep(0)  # flush _session_store.rename create_task
    snap = pipeline._session_store.peek_snapshot("jagan_bf")
    assert snap.person_type == "best_friend", (
        "escape hatch must preserve best_friend status on fresh enrollment"
    )
    assert snap.person_name == "Jagan"
    # Graph/knowledge migration runs via the existing promotion chain.
    mock_orch.on_identity_confirmed.assert_called_once_with(
        "jagan_bf", "Gevan", "Jagan"
    )


async def test_enrollment_mishear_escape_hatch_skips_when_voice_mature():
    """Session 100 Bug F safety: even on a fresh session, if the DB has
    voice samples corroborating the stored name, the escape hatch must
    NOT fire — someone who's been known for a while with an accumulated
    voice profile is NOT an enrollment-mishear candidate. Mid-session
    rename still disputes."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    await pipeline._session_store.open_session("jagan_bf", "Jagan", "best_friend", "face", now=_t.time() - 30)
    await pipeline._conversation_store.set_history("jagan_bf", [])
    mock_db = MagicMock()
    mock_db.voice_embedding_count.return_value = 20  # MATURE voice — not enrollment

    orig_orch = pipeline._brain_orchestrator
    _wiring._brain_orchestrator = MagicMock()
    try:
        await _execute_tool(
            "update_person_name", {"name": "Attacker"},
            "jagan_bf", "Jagan", db=mock_db,
            user_text="my name is Attacker",
        )
    finally:
        _wiring._brain_orchestrator = orig_orch

    # Voice mature → dispute path fires, DB row untouched.
    mock_db.update_person_name.assert_not_called()
    await __import__("asyncio").sleep(0)  # flush transition_to_disputed create_task
    assert pipeline._session_store.peek_snapshot("jagan_bf").person_type == "disputed"


async def test_enrollment_mishear_escape_hatch_skips_when_session_stale():
    """Session 100 Bug F safety: even with zero voice samples, a session
    that's been going for longer than the grace window does NOT qualify
    as an enrollment-mishear candidate. A stranger with years of thin
    data shouldn't get their name rewritten just because voice
    accumulation stalled."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    from core.config import ENROLLMENT_RENAME_GRACE_SECS
    await pipeline._session_store.open_session("jagan_bf", "Jagan", "best_friend", "face", now=_t.time() - (ENROLLMENT_RENAME_GRACE_SECS + 60))
    await pipeline._conversation_store.set_history("jagan_bf", [])
    mock_db = MagicMock()
    mock_db.voice_embedding_count.return_value = 0

    orig_orch = pipeline._brain_orchestrator
    _wiring._brain_orchestrator = MagicMock()
    try:
        await _execute_tool(
            "update_person_name", {"name": "Attacker"},
            "jagan_bf", "Jagan", db=mock_db,
            user_text="my name is Attacker",
        )
    finally:
        _wiring._brain_orchestrator = orig_orch

    # Stale session → dispute path, not rename.
    mock_db.update_person_name.assert_not_called()
    await __import__("asyncio").sleep(0)  # flush transition_to_disputed create_task
    assert pipeline._session_store.peek_snapshot("jagan_bf").person_type == "disputed"
