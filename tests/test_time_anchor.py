"""Tests for _format_time_anchor() — Wave 4 follow-up F1."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from datetime import datetime
from unittest.mock import patch

import pytest

import core.brain as _brain


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call_anchor(fake_dt: datetime) -> str:
    """Call _format_time_anchor with datetime.now() patched to fake_dt."""
    # core.brain imports `from datetime import datetime` at module scope,
    # so we patch the name `datetime` inside the core.brain module.
    class _FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return fake_dt

    with patch("core.brain.datetime", _FakeDT):
        return _brain._format_time_anchor()


# ---------------------------------------------------------------------------
# Unit tests on _format_time_anchor
# ---------------------------------------------------------------------------

def test_time_anchor_block_markers_present():
    result = _call_anchor(datetime(2026, 5, 7, 14, 46, 0))
    assert "<<<TIME ANCHOR" in result
    assert "<<<END TIME ANCHOR>>>" in result


def test_time_anchor_rules_present():
    result = _call_anchor(datetime(2026, 5, 7, 14, 46, 0))
    assert "RULES:" in result
    assert "Do not contradict this clock" in result


def test_time_anchor_rounds_to_5_minutes():
    # 14:48 should round down to 14:45 → "2:45 PM"
    result = _call_anchor(datetime(2026, 5, 7, 14, 48, 0))
    assert "2:45 PM" in result


def test_time_anchor_morning_label():
    result = _call_anchor(datetime(2026, 5, 7, 9, 0, 0))
    assert "morning" in result


def test_time_anchor_afternoon_label():
    result = _call_anchor(datetime(2026, 5, 7, 14, 0, 0))
    assert "afternoon" in result


def test_time_anchor_evening_label():
    result = _call_anchor(datetime(2026, 5, 7, 19, 0, 0))
    assert "evening" in result


def test_time_anchor_night_label_late():
    # 23:00 is night
    result = _call_anchor(datetime(2026, 5, 7, 23, 0, 0))
    assert "night" in result


def test_time_anchor_night_label_early_hours():
    # 2:00 AM is still night (hour < 5)
    result = _call_anchor(datetime(2026, 5, 7, 2, 0, 0))
    assert "night" in result


# ---------------------------------------------------------------------------
# Integration: anchor appears in _build_system_prompt output
# ---------------------------------------------------------------------------

def test_time_anchor_injected_into_system_prompt():
    """TIME ANCHOR block must appear in the output of _build_system_prompt."""
    class _FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 5, 7, 14, 30, 0)

    with patch("core.brain.datetime", _FakeDT):
        prompt = _brain._build_system_prompt(person_name="Jagan")

    assert "<<<TIME ANCHOR" in prompt
    assert "<<<END TIME ANCHOR>>>" in prompt


def test_time_anchor_is_near_end_of_system_prompt():
    """TIME ANCHOR must appear in the final 20% of the system prompt.

    Recency-effect placement: brain attention peaks on content near the end
    of the prompt, immediately before conversation history.
    """
    class _FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 5, 7, 14, 30, 0)

    with patch("core.brain.datetime", _FakeDT):
        prompt = _brain._build_system_prompt(person_name="Jagan")

    anchor_pos = prompt.rfind("<<<TIME ANCHOR")
    assert anchor_pos != -1
    cutoff = int(len(prompt) * 0.80)
    assert anchor_pos >= cutoff, (
        f"TIME ANCHOR at pos {anchor_pos} but expected >= {cutoff} "
        f"(80% of {len(prompt)} chars). Block is not near the end of prompt."
    )
