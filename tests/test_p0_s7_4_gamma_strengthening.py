"""tests/test_p0_s7_4_gamma_strengthening.py — P0.S7.4 γ strengthening.

Surfaced by the 2026-05-19 partial-validation canary: the original
P0.S7.2 γ bullet shifted brain's behavior from "confident denial" →
"polite hedge until user permits retrieval" — better, but NOT the
locked γ target. The target is "autonomously call search_memory BEFORE
denying or hedging on first mention." See ``tests/p0_s7_4_spec.md``.

The strengthened bullet in ``core/brain.py::_build_system_prompt``'s
``<<<HONESTY POLICY>>>`` block demands autonomous retrieval on FIRST
mention, names the canary's exact hedge phrasings as forbidden, gates
the hedge fallback on AFTER-retrieval, and extends the failure-mode
definition to include "pre-retrieval hedging."

Real-LLM compliance with the strengthened bullet is validated via the
bundled-queue canary that fires after D-A + D-C + D-B + D-D + D-E +
γ all ship (per P0.S7.2 §11.10 re-canary discipline). This CI test
asserts the bullet text lands as specified.
"""
from __future__ import annotations


def test_honesty_policy_block_contains_strengthened_memory_discipline():
    """P0.S7.4 spec §3 — source-inspection guard on the strengthened bullet.

    Verifies that ``core/brain.py::render_session_stable_prefix`` carries
    the strengthened γ bullet text per ``tests/p0_s7_4_spec.md`` §2.2.
    (The spec's `core/brain.py:2283-2293` line range is correct; the
    enclosing function is ``render_session_stable_prefix`` — Wave 4
    cached-prefix optimization moved the HONESTY POLICY block out of
    ``_build_system_prompt`` so consecutive turns share a byte-identical
    Section 1+2 prefix. Same contract; different function name.)

    Six structural anchors checked:
      (1) Marker label + P0.S7.4 strengthening tag
      (2) Required phrasings — IMMEDIATELY / FIRST mention / BEFORE
          responding / Do NOT hedge first / call search_memory
      (3) Forbidden-first-response patterns — at least 3 of 5
      (4) Hedge-fallback gating language — AFTER retrieval +
          acknowledge the retrieval attempt
      (5) Failure-mode definition extended — False denial OR
          pre-retrieval hedging
      (6) Strengthening dated 2026-05-19
    """
    import inspect, re
    from core import brain

    raw_src = inspect.getsource(brain.render_session_stable_prefix)
    # Collapse adjacent string-literal splits so multi-line phrases match.
    # Python concatenates `"foo " "bar"` at parse time; `inspect.getsource`
    # returns the pre-parse source, so multi-line strings keep the
    # `"...\n            "..."` boundaries that hide contiguous phrases.
    # Strip the `"<whitespace>"` / `'<whitespace>'` boundaries (same shape
    # as the P0.S7.2 Phase 1 source/behavioral split rationale).
    src = re.sub(r'"\s+"', "", raw_src)
    src = re.sub(r"'\s+'", "", src)

    # (1) Marker label + strengthening tag.
    assert "MEMORY HONESTY DISCIPLINE" in src, (
        "MEMORY HONESTY DISCIPLINE marker label missing — strengthening "
        "MUST keep the bullet recognizable as the same γ contract"
    )
    assert "P0.S7.4 strengthening" in src, (
        "P0.S7.4 strengthening tag missing — provenance anchor for "
        "the strengthened bullet"
    )

    # (2) Required phrasings — single-line literal substrings.
    _required = [
        "IMMEDIATELY",          # autonomous-call keyword
        "FIRST mention",        # timing anchor
        "BEFORE responding",    # ordering anchor
        "Do NOT hedge first",   # negative-control on hedging
        "call search_memory",   # explicit tool name (multiple times)
    ]
    for _phrase in _required:
        assert _phrase in src, (
            f"required phrasing missing from strengthened bullet: {_phrase!r}"
        )

    # (3) Forbidden-first-response pattern list — at least 3 of 5
    # canary hedges named. The list teeth = naming the user's exact
    # observed failure phrasings; full-set match is the strict target,
    # 3-of-5 is the floor below which the strengthening lacks
    # discriminative power.
    _forbidden_patterns = [
        "I'm not sure what you're referring to",
        "I don't recall having a conversation",
        "I don't think I said",
        "I didn't actually",
        "Can you remind me what we discussed",
    ]
    _seen = sum(1 for _p in _forbidden_patterns if _p in src)
    assert _seen >= 3, (
        f"forbidden-first-response list must name at least 3 of 5 canary "
        f"hedges; found {_seen}. The patterns are the teeth — naming the "
        "exact user-observed phrasings makes the rule concrete"
    )

    # (4) Hedge-fallback gating language. Hedge is now allowed ONLY
    # after retrieval, and the response MUST acknowledge the
    # retrieval attempt.
    assert "AFTER retrieval" in src, (
        "hedge-fallback MUST be gated on 'AFTER retrieval' — "
        "without this, the LLM can still hedge before calling the tool"
    )
    assert "acknowledge the retrieval attempt" in src, (
        "post-retrieval hedge MUST acknowledge the retrieval — "
        "'I checked my notes and...' shape, not bare 'I don't recall...'"
    )

    # (5) Failure-mode definition extended to include hedging
    # pre-retrieval. The original P0.S7.2 bullet defined failure as
    # "false denial"; the strengthening adds "OR pre-retrieval
    # hedging" so the canary's exact failure mode is named explicitly.
    assert "False denial OR pre-retrieval hedging" in src, (
        "failure-mode definition MUST extend the original 'false denial' "
        "to include 'pre-retrieval hedging' — names the canary's exact "
        "failure mode so the LLM's training-time risk weighting matches "
        "the desired behavior"
    )

    # (6) Strengthening date — 2026-05-19, matches the canary date.
    assert "2026-05-19" in src, (
        "strengthening date 2026-05-19 missing — provenance anchor "
        "for the bullet revision"
    )
