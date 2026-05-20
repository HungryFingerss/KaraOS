"""tests/test_p0_s7_2_phase1.py — P0.S7.2 Phase 1 (γ — HONESTY POLICY extension).

Plan v2 §6 Phase 1 = 2 tests:

  1. test_honesty_policy_block_contains_memory_denial_bullet
     — source-inspection: the MEMORY HONESTY DISCIPLINE bullet text is present
       in core/brain.py with the locked phrasings (search_memory BEFORE
       denying / "self-denial phrasings" / "hard correctness failure" /
       hedge fallback).

  2. test_honesty_policy_block_present_for_known_speakers
     — behavioral: _build_system_prompt() output for a known-speaker context
       contains the MEMORY HONESTY DISCIPLINE marker.

Phase ordering note (L3): Phase 1 alone does NOT fix the canary failure. The
prompt-side discipline gets brain into the right behavioral mode but Phase 2
(κ — multi-person assistant-turn extraction) creates the facts that make
search_memory return useful results. Phase 3 integration test gates on BOTH.
"""
from __future__ import annotations

import pathlib

import pytest


_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_BRAIN_PY = _REPO_ROOT / "core" / "brain.py"


# ────────────────────────────────────────────────────────────────────────────
# Test 1 — source-inspection on HONESTY POLICY block
# ────────────────────────────────────────────────────────────────────────────


def test_honesty_policy_block_contains_memory_denial_bullet():
    """Plan v2 §3.2 — the MEMORY HONESTY DISCIPLINE bullet is present in
    core/brain.py source with marker + counter-example label. Catches a
    future refactor that strips the discipline label entirely. Semantic
    strings are verified in the rendered-prompt behavioral test (test 2)
    since Python concatenates adjacent string literals at parse time,
    making source-level substring matches across line-wraps unreliable."""
    src = _BRAIN_PY.read_text(encoding="utf-8")

    # Marker label.
    assert "MEMORY HONESTY DISCIPLINE" in src, (
        "P0.S7.2 γ: <<<HONESTY POLICY>>> block must include the "
        "MEMORY HONESTY DISCIPLINE bullet."
    )

    # Forbidden self-denial phrasings named (single short literal on one line).
    assert "I didn't actually" in src, (
        "P0.S7.2 γ: bullet must name 'I didn\\'t actually' as a forbidden "
        "self-denial phrasing the brain trips into without retrieval."
    )

    # Hedge fallback phrasing — what brain SHOULD do when retrieval is empty.
    assert "remind me" in src.lower(), (
        "P0.S7.2 γ: bullet must give brain the hedge fallback ('can you "
        "remind me?') for the search-empty path, not just forbid denial."
    )


# ────────────────────────────────────────────────────────────────────────────
# Test 2 — behavioral: _build_system_prompt renders the bullet for known speakers
# ────────────────────────────────────────────────────────────────────────────


def test_honesty_policy_block_present_for_known_speakers():
    """Plan v2 §3.3 — HONESTY POLICY block gated on HONESTY_POLICY_BLOCK_ENABLED
    (S68 Bug N existing flag). MEMORY HONESTY DISCIPLINE inherits this gating;
    the rendered prompt for a known-speaker context must contain the bullet."""
    import core.config as cfg
    from core.brain import _build_system_prompt

    # Sanity — the flag is on by default.
    assert cfg.HONESTY_POLICY_BLOCK_ENABLED is True, (
        "HONESTY_POLICY_BLOCK_ENABLED must default to True; the MEMORY "
        "HONESTY DISCIPLINE bullet inherits this gate."
    )

    vision_state = {
        "session_person_type": "known",
        "session_user_turns": 3,
        "identity_disputed": False,
        "person_name": "Jagan",
        "active_session_count": 1,
    }
    prompt = _build_system_prompt(
        person_name="Jagan",
        vision_state=vision_state,
        system_name="Kara",
    )

    # The bullet's marker must appear in the rendered prompt.
    assert "MEMORY HONESTY DISCIPLINE" in prompt, (
        "P0.S7.2 γ behavioral: rendered system prompt for a known speaker "
        "must include the MEMORY HONESTY DISCIPLINE marker. If the block is "
        "gated by a flag, that flag must default-on per Plan v2 §3.3."
    )
    # The imperative must reach the rendered prompt. P0.S7.4 strengthened
    # the phrasing from "search_memory BEFORE denying" to "search_memory
    # IMMEDIATELY — on the FIRST mention, BEFORE responding" per the
    # 2026-05-19 partial-validation canary finding (brain hedged before
    # retrieving). Either contract phrasing is acceptable here as long as
    # the rendered prompt carries the autonomous-retrieval imperative.
    assert (
        "search_memory IMMEDIATELY" in prompt
        or "search_memory BEFORE denying" in prompt
    ), (
        "P0.S7.2 γ behavioral: rendered prompt must carry the autonomous "
        "search_memory imperative (either the P0.S7.2 original 'BEFORE "
        "denying' phrasing OR the P0.S7.4 strengthened 'IMMEDIATELY' "
        "phrasing) — not just declare the marker label."
    )
    # Hard correctness failure framing — severity anchor in the rendered
    # prompt (source-level grep is unreliable across line-wraps because
    # Python concatenates adjacent string literals at parse time).
    assert "hard correctness failure" in prompt, (
        "P0.S7.2 γ behavioral: rendered prompt must frame false self-denial "
        "as a 'hard correctness failure' — preserves severity against a "
        "future 'soften the prompt' refactor."
    )
