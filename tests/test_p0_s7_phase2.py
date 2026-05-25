"""tests/test_p0_s7_phase2.py — P0.S7 Phase 2 (D-A SHARED CONTEXT consumer).

Plan v2 §8 Phase 2 = 5 new tests (10-14):

  10. test_shared_context_block_renders_multi_person
  11. test_shared_context_block_single_person_returns_none
  12. test_shared_context_block_flag_off_returns_none
  13. test_shared_context_block_disputed_caller_returns_none (T-A — DB not called)
  14. test_shared_context_block_injected_in_build_system_prompt

Plan v2 §6 / §8.
"""
from __future__ import annotations

import pathlib
import re
from unittest.mock import MagicMock, patch

import pytest

# P0.S7 D2 — module-level privacy_critical marker; all tests verify the
# SHARED CONTEXT block (cross-person context construction + disputed gates).
pytestmark = pytest.mark.privacy_critical


_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


# ────────────────────────────────────────────────────────────────────────────
# 10. renders multi-person — happy path
# ────────────────────────────────────────────────────────────────────────────


def test_shared_context_block_renders_multi_person():
    """Mock db.get_recent_room_conversation to return 2 turns; assert the
    block contains the markers + 2 lines in the expected format."""
    import pipeline

    fake_rows = [
        {"person_id": "lexi_xyz", "role": "user",
         "text": "Hello room", "ts": 1779010000.0,
         "audience_ids": ["jagan_001", "lexi_xyz"], "addressed_to": None},
        {"person_id": "jagan_001", "role": "assistant",
         "text": "Hi everyone", "ts": 1779010001.0,
         "audience_ids": ["jagan_001", "lexi_xyz"], "addressed_to": "Lexi"},
    ]
    db = MagicMock()
    db.get_recent_room_conversation.return_value = fake_rows
    db.get_person.side_effect = lambda pid: (
        {"name": "Lexi"} if pid == "lexi_xyz" else
        {"name": "Jagan"} if pid == "jagan_001" else None
    )

    block = pipeline._build_shared_context_block(
        room_session_id="room_x",
        requester_pid="jagan_001",
        best_friend_id="jagan_001",
        db=db,
        is_disputed_fn=lambda pid: False,
        active_session_count=2,
        limit=10,
        now=1779010100.0,
    )
    assert block is not None
    assert "<<<SHARED CONTEXT" in block
    assert "<<<END SHARED CONTEXT>>>" in block
    # User line — "Lexi" name + content + age suffix.
    assert "Lexi" in block
    assert "Hello room" in block
    # Assistant line — "you [to Lexi]" because addressed_to is set.
    assert "you [to Lexi]" in block
    assert "Hi everyone" in block
    # db called with the correct params + best_friend override threaded through.
    db.get_recent_room_conversation.assert_called_once_with(
        room_session_id="room_x",
        requester_pid="jagan_001",
        best_friend_id="jagan_001",
        limit=10,
    )


def test_shared_context_block_renders_addressed_to_none_falls_back_to_plain_you():
    """Architect Phase 2 option (a) — graceful fallback when addressed_to is
    None (conversation_log schema lacks the column; field is reserved on the
    dict shape). Assistant line renders as plain `you: ...` not `you [to None]`."""
    import pipeline

    fake_rows = [
        {"person_id": "jagan_001", "role": "assistant",
         "text": "ack", "ts": 1779010000.0,
         "audience_ids": ["jagan_001", "lexi_xyz"], "addressed_to": None},
    ]
    db = MagicMock()
    db.get_recent_room_conversation.return_value = fake_rows
    db.get_person.return_value = {"name": "Jagan"}

    block = pipeline._build_shared_context_block(
        room_session_id="room_x",
        requester_pid="jagan_001",
        best_friend_id=None,
        db=db,
        is_disputed_fn=lambda pid: False,
        active_session_count=2,
        limit=10,
        now=1779010100.0,
    )
    assert block is not None
    # Plain `you` (no `[to ...]`).
    assert "you" in block
    assert "[to" not in block, (
        "addressed_to=None must NOT render as `[to None]`; architect option "
        "(a) requires graceful fallback to plain `you:` form."
    )


# ────────────────────────────────────────────────────────────────────────────
# 11. single-person returns None
# ────────────────────────────────────────────────────────────────────────────


def test_shared_context_block_single_person_returns_none():
    """active_session_count=1 → None (multi-person gate fires); DB never called."""
    import pipeline
    db = MagicMock()
    block = pipeline._build_shared_context_block(
        room_session_id="room_x",
        requester_pid="jagan_001",
        best_friend_id=None,
        db=db,
        is_disputed_fn=lambda pid: False,
        active_session_count=1,
        limit=10,
    )
    assert block is None
    db.get_recent_room_conversation.assert_not_called()


# ────────────────────────────────────────────────────────────────────────────
# 12. flag-off returns None
# ────────────────────────────────────────────────────────────────────────────


def test_shared_context_block_flag_off_returns_none():
    """SHARED_CONTEXT_BLOCK_ENABLED=False → None even with multi-person room."""
    import pipeline
    db = MagicMock()
    with patch.object(pipeline, "SHARED_CONTEXT_BLOCK_ENABLED", False):
        block = pipeline._build_shared_context_block(
            room_session_id="room_x",
            requester_pid="jagan_001",
            best_friend_id=None,
            db=db,
            is_disputed_fn=lambda pid: False,
            active_session_count=3,
            limit=10,
        )
    assert block is None
    db.get_recent_room_conversation.assert_not_called()


# ────────────────────────────────────────────────────────────────────────────
# 13. T-A — disputed caller returns None AND DB not called
# ────────────────────────────────────────────────────────────────────────────


def test_shared_context_block_disputed_caller_returns_none():
    """T-A — disputed caller skip MUST fire BEFORE any DB read. Standard
    MagicMock.assert_not_called() verifies the structural ordering at
    behavior level (Phase 3 test 16 additionally proves it via AST)."""
    import pipeline
    db = MagicMock()
    block = pipeline._build_shared_context_block(
        room_session_id="room_x",
        requester_pid="jagan_001",
        best_friend_id=None,
        db=db,
        is_disputed_fn=lambda pid: pid == "jagan_001",
        active_session_count=3,
        limit=10,
    )
    assert block is None
    db.get_recent_room_conversation.assert_not_called(), (
        "T-A: disputed-caller gate MUST fire before any DB read so a "
        "disputed session never consumes persisted room context."
    )


def test_shared_context_block_empty_room_session_id_returns_none():
    """room_session_id None / empty → None (gate fires before DB read)."""
    import pipeline
    db = MagicMock()
    for empty in (None, ""):
        block = pipeline._build_shared_context_block(
            room_session_id=empty,
            requester_pid="jagan_001",
            best_friend_id=None,
            db=db,
            is_disputed_fn=lambda pid: False,
            active_session_count=2,
            limit=10,
        )
        assert block is None
    db.get_recent_room_conversation.assert_not_called()


# ────────────────────────────────────────────────────────────────────────────
# 14. injected in _build_system_prompt between ROOM and EMOTIONAL CONTEXT
# ────────────────────────────────────────────────────────────────────────────


def test_shared_context_block_injected_in_build_system_prompt():
    """Plan v2 §6 ordering — the prompt rendering reads
    `vision_state["shared_context"]` and injects between ROOM block and
    EMOTIONAL CONTEXT block. Source-inspection of `core/brain.py`."""
    brain_src = (_REPO_ROOT / "core" / "brain.py").read_text(encoding="utf-8")

    # The vision_state["shared_context"] read must exist.
    assert '(vision_state or {}).get("shared_context")' in brain_src or \
           '"shared_context"' in brain_src, (
        "core/brain.py must read vision_state['shared_context']"
    )

    # Ordering: must come AFTER `_room_block` injection AND BEFORE
    # `emotion_context` injection.
    room_idx = brain_src.find('vision_state or {}).get("room_block")')
    shared_idx = brain_src.find('vision_state or {}).get("shared_context")')
    emotion_idx = brain_src.find("if emotion_context:")

    assert room_idx > 0, "ROOM block read missing from _build_system_prompt"
    assert shared_idx > 0, "SHARED CONTEXT block read missing"
    assert emotion_idx > 0, "EMOTIONAL CONTEXT read missing"
    assert room_idx < shared_idx < emotion_idx, (
        f"Plan v2 §6 ordering violation: ROOM (at char {room_idx}) → "
        f"SHARED CONTEXT (at {shared_idx}) → EMOTIONAL CONTEXT (at "
        f"{emotion_idx}). Found: room={room_idx}, shared={shared_idx}, "
        f"emotion={emotion_idx}."
    )


def test_pipeline_call_sites_populate_shared_context():
    """Both vision_state builds in pipeline.py (conversation_turn +
    _kairos_tick) must populate `shared_context` via
    `_build_shared_context_block(...)`. Source-inspection."""
    pipeline_src = (_REPO_ROOT / "pipeline.py").read_text(encoding="utf-8")
    # At least 2 occurrences of the helper call in production code.
    helper_call_count = pipeline_src.count("_build_shared_context_block(")
    # 1 definition + 2 call sites = 3 occurrences. The definition's
    # `def _build_shared_context_block(` has the `def ` prefix; the calls
    # do not.
    call_only = pipeline_src.count("_build_shared_context_block(\n") + \
                pipeline_src.count("_build_shared_context_block(\nroom_session_id=")
    # More robust: count occurrences NOT preceded by `def `.
    pattern_call = re.compile(r"(?<!def )_build_shared_context_block\(")
    matches = pattern_call.findall(pipeline_src)
    assert len(matches) >= 2, (
        f"Expected ≥2 call sites of _build_shared_context_block in "
        f"pipeline.py (conversation_turn + _kairos_tick); found {len(matches)}."
    )
