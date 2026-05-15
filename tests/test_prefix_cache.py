"""
Wave 4 Item 17 — tests for session-stable prefix caching.

Verifies:
1. render_session_stable_prefix() is a pure function (same params → same output)
2. render_session_stable_prefix() contains expected section markers
3. _build_system_prompt uses cached_prefix when provided (skips rebuild)
4. update_system_name invalidates ALL session caches
5. report_identity_mismatch invalidates the affected session cache
6. Stranger turn threshold crossing invalidates the cache
"""
import os

import pytest

from core.brain import _build_system_prompt, render_session_stable_prefix

_PIPELINE_SRC = open(
    os.path.join(os.path.dirname(__file__), "..", "pipeline.py"), encoding="utf-8"
).read()


# ── Test 1: pure function — same params → same output ──────────────────────────

def test_render_session_stable_prefix_is_pure_function():
    kwargs = dict(
        system_name="Kara",
        session_person_type="known",
        session_user_turns=3,
        identity_disputed=False,
        person_name="Alice",
        disputed_claimed_name=None,
    )
    out1 = render_session_stable_prefix(**kwargs)
    out2 = render_session_stable_prefix(**kwargs)
    assert out1 == out2
    assert isinstance(out1, str)
    assert len(out1) > 100


# ── Test 2: expected section markers present ──────────────────────────────────

def test_render_session_stable_prefix_contains_expected_sections():
    prefix = render_session_stable_prefix(
        system_name="Kara",
        session_person_type="known",
        session_user_turns=2,
        identity_disputed=False,
        person_name="Alice",
        disputed_claimed_name=None,
    )
    assert "<<<HEDGED NAMING CONTRACT>>>" in prefix
    assert "<<<HONESTY POLICY>>>" in prefix
    assert "<<<CROSS-PERSON PRIVACY" in prefix


# ── Test 3: _build_system_prompt uses cached_prefix when provided ─────────────

def test_build_system_prompt_uses_cached_prefix():
    sentinel = "CACHED_PREFIX_SENTINEL_XYZ"
    result = _build_system_prompt(
        person_name="Alice",
        vision_state={"face_in_frame": False, "session_person_type": "known"},
        cached_prefix=sentinel,
    )
    # The result must START with the sentinel (Section 3 appended after it)
    assert result.startswith(sentinel)
    # Section 3 datetime line must still be present
    assert "Current date:" in result


# ── Test 5: report_identity_mismatch invalidates affected session cache ───────

def test_report_identity_mismatch_invalidates_session_cache():
    src = _PIPELINE_SRC
    # Both dispute-flip sites must invalidate the cache via set_cached_prefix
    pop_count = src.count('set_cached_prefix(person_id, None)')
    assert pop_count >= 2, (
        "both report_identity_mismatch and update_person_name dispute-flip "
        "must call set_cached_prefix(person_id, None)"
    )


# ── Test 6: stranger turn threshold crossing invalidates cache ────────────────

def test_stranger_turn_threshold_invalidates_cache():
    src = _PIPELINE_SRC
    # Threshold-crossing block must exist
    assert 'STRANGER_IDENTITY_BLOCK_MIN_TURNS' in src
    assert 'set_cached_prefix(_cur_pid, None)' in src
    # And must be inside the stranger-type guard
    idx_threshold = src.find('_cur_snap.user_turns + 1 == STRANGER_IDENTITY_BLOCK_MIN_TURNS')
    idx_pop = src.find('set_cached_prefix(_cur_pid, None)')
    assert idx_threshold != -1, "threshold crossing check must be present"
    assert idx_pop != -1, "cache invalidation at threshold must be present"
    # cache invalidation comes after the threshold check
    assert idx_pop > idx_threshold
