"""
Wave 4 Item 16 — tests for the three-section prompt caching architecture.

Verifies:
1. PURE-STATIC section precedes SESSION-STABLE section
2. SESSION-STABLE section precedes TURN-DYNAMIC section
3. Content-set (all blocks) is unchanged after the reorder
4. _format_datetime_line() rounds to 5-minute boundaries
"""
import inspect
from datetime import datetime
from unittest.mock import patch

import pytest

import core.brain as brain_mod
from core.brain import _build_system_prompt, _format_datetime_line


# ── helpers ───────────────────────────────────────────────────────────────────

def _minimal_prompt(system_name="TestBot", **kwargs):
    """Call _build_system_prompt with minimal required args."""
    defaults = dict(
        person_name="Alice",
        vision_state={"face_in_frame": False, "session_person_type": "known"},
        voice_state=None,
        memory_context=None,
        object_context=None,
        emotion_context=None,
        prompt_addendum=None,
        system_name=system_name,
        scene_block=None,
    )
    defaults.update(kwargs)
    return _build_system_prompt(**defaults)


# ── Test 1: PURE-STATIC precedes SESSION-STABLE ───────────────────────────────

def test_system_prompt_pure_static_section_precedes_session_stable():
    """
    HEDGED NAMING CONTRACT (pure-static, Section 1) must appear BEFORE
    HONESTY POLICY (session-stable, Section 2) in the prompt.
    """
    prompt = _minimal_prompt(system_name="Kara")
    pos_static = prompt.find("<<<HEDGED NAMING CONTRACT>>>")
    pos_session = prompt.find("<<<HONESTY POLICY>>>")
    assert pos_static != -1, "<<<HEDGED NAMING CONTRACT>>> not found in prompt"
    assert pos_session != -1, "<<<HONESTY POLICY>>> not found in prompt"
    assert pos_static < pos_session, (
        f"PURE-STATIC block (pos={pos_static}) must precede SESSION-STABLE block "
        f"(pos={pos_session})"
    )


# ── Test 2: SESSION-STABLE precedes TURN-DYNAMIC ─────────────────────────────

def test_system_prompt_session_stable_precedes_turn_dynamic():
    """
    HONESTY POLICY (session-stable) must appear BEFORE SENSORS (turn-dynamic).
    """
    prompt = _minimal_prompt(
        system_name="Kara",
        vision_state={
            "face_in_frame": True,
            "person_name": "Alice",
            "recognition_conf": 0.75,
            "session_person_type": "known",
        },
        voice_state={"gallery_size": 0},
    )
    pos_session = prompt.find("<<<HONESTY POLICY>>>")
    pos_dynamic = prompt.find("<<<SENSORS")
    assert pos_session != -1, "<<<HONESTY POLICY>>> not found"
    assert pos_dynamic != -1, "<<<SENSORS>>> not found"
    assert pos_session < pos_dynamic, (
        f"SESSION-STABLE (pos={pos_session}) must precede TURN-DYNAMIC "
        f"(pos={pos_dynamic})"
    )


# ── Test 3: Content set unchanged after reorder ───────────────────────────────

def test_system_prompt_content_set_unchanged_after_reorder():
    """
    All expected blocks are present in the prompt regardless of order.
    Ensures the reorder didn't accidentally drop any block.
    """
    prompt = _minimal_prompt(
        system_name="Kara",
        vision_state={
            "face_in_frame": True,
            "person_name": "Alice",
            "recognition_conf": 0.70,
            "session_person_type": "known",
        },
        voice_state={"gallery_size": 1, "matched_id": None, "voice_confidence": 0.0,
                     "matches_active": False, "multi_speaker": False},
    )
    expected_blocks = [
        "<<<HEDGED NAMING CONTRACT>>>",   # Section 1 (pure-static)
        "<<<HONESTY POLICY>>>",            # Section 2 (session-stable)
        "<<<CROSS-PERSON PRIVACY",         # Section 2
        "<<<SENSORS",                      # Section 3 (turn-dynamic)
        "Current date:",                   # Section 3 datetime line
    ]
    for block in expected_blocks:
        assert block in prompt, f"Expected block '{block}' not found in prompt"


# ── Test 4: _format_datetime_line rounds to 5-minute boundary ────────────────

def test_datetime_line_rounded_to_5_minute_boundary():
    """
    _format_datetime_line() should round minutes down to the nearest 5.
    E.g. 13:47 → 13:45, 09:00 → 09:00, 23:59 → 23:55.
    No seconds in output.
    """
    test_cases = [
        (2026, 5, 7, 13, 47, 33),   # 13:47:33 → 13:45
        (2026, 5, 7,  9,  0,  0),   # 09:00:00 → 09:00
        (2026, 5, 7, 23, 59, 59),   # 23:59:59 → 23:55
        (2026, 5, 7,  8, 33,  1),   # 08:33:01 → 08:30
        (2026, 5, 7, 12,  5,  0),   # 12:05:00 → 12:05
    ]
    expected_minutes = [45, 0, 55, 30, 5]

    for (yr, mo, dy, hr, mn, sc), exp_min in zip(test_cases, expected_minutes):
        fake_now = datetime(yr, mo, dy, hr, mn, sc)
        with patch("core.brain.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            line = _format_datetime_line()

        # Must not contain seconds
        assert ":00 " not in line or exp_min == 0, "seconds must not appear in output"

        # Minutes must be rounded down to nearest 5
        exp_time_str = fake_now.replace(
            minute=(mn // 5) * 5, second=0, microsecond=0
        ).strftime("%I:%M %p")
        assert exp_time_str in line, (
            f"Expected '{exp_time_str}' in datetime line, got: {line!r}"
        )
