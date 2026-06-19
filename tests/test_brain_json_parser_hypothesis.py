"""P0.12 — Brain LLM JSON parser hardening (Hypothesis property tests).

Two parsers handle every LLM-generated JSON response in the system:

  `core.brain_agent._parse_json(raw)`             — the salvage utility used
                                                    by every extraction agent
                                                    (7+ call sites).  Contract:
                                                    returns dict OR None,
                                                    never raises.

  `core.brain._parse_intent_sidecar(raw)`         — wraps the same salvage
                                                    pattern with intent-schema
                                                    validation.  Contract:
                                                    returns normalized dict
                                                    OR None, never raises.

Example-based tests (`test_brain_agent.py::TestParseJson`) cover the happy
path + a few hand-picked malformed strings.  P0.12 adds property-based
fuzz coverage for the long tail — the kinds of LLM-output pathologies that
example-based tests miss because no human thinks to write them down.

**Universal invariant**: for ANY input (bytes-decoded-to-str), the parser
returns a dict OR None, and NEVER raises.  This is the load-bearing
contract — production code does `parsed = _parse_json(raw); if parsed
is None: ...`.  A raise breaks every caller's branch.

**Failure-mode taxonomy** (Phase 0):

  1. Truncated stream (partial JSON, abrupt cutoff)
  2. Embedded code-block fences (```json ... ``` markdown wrapping)
  3. Doubled keys ({"a": 1, "a": 2} — Python's json.loads accepts, last wins)
  4. Nested unescaped quotes ({"text": "she said "hi""})
  5. Trailing commas ({"a": 1,})
  6. BOM / leading whitespace (\ufeff{...})
  7. Mixed encodings (surrogate code points, control chars)
  8. Empty / whitespace-only input
  9. Extremely large input (size DoS — must not OOM or hang)
 10. Deeply nested input (recursion DoS — must catch RecursionError if any)
 11. Arbitrary text (Hypothesis-generated random str — the catch-all)

Each test runs with `max_examples=1000` per the P0.12 spec.  Hypothesis's
shrinker finds the minimal falsifying input automatically if any invariant
breaks.  Total CI cost stays under ~30s on this machine.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import json
import sys

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

# Hypothesis settings shared across tests — 1000 examples per the spec.
# `deadline=None` because the recursion-depth / large-input tests can
# legitimately spend several ms on a single example.  HealthCheck.too_slow
# suppressed for the same reason.
_P012 = settings(
    max_examples=1000,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


# ---------------------------------------------------------------------------
# Parser imports — stub voice/audio BEFORE the brain import (torchaudio DLL).
# ---------------------------------------------------------------------------

from tests.conftest import setup_pipeline_stubs as _setup_pipeline_stubs  # noqa: E402
_setup_pipeline_stubs()

from core.brain_agent import _parse_json, _parse_json_array  # noqa: E402
from core.brain import _parse_intent_sidecar, INTENT_LABELS  # noqa: E402


# ---------------------------------------------------------------------------
# Universal invariant: never raise; return dict OR None
# ---------------------------------------------------------------------------

def _check_universal_invariant(raw: str, *, label: str) -> None:
    """For both parsers, assert the universal contract holds on `raw`."""
    try:
        r1 = _parse_json(raw)
    except BaseException as e:  # noqa: BLE001
        pytest.fail(
            f"{label}: _parse_json raised {type(e).__name__}: {e!r} on "
            f"input {raw[:120]!r}{'...' if len(raw) > 120 else ''}"
        )
    assert r1 is None or isinstance(r1, dict), (
        f"{label}: _parse_json returned {type(r1).__name__} (must be dict or None)"
    )

    try:
        r2 = _parse_intent_sidecar(raw)
    except BaseException as e:  # noqa: BLE001
        pytest.fail(
            f"{label}: _parse_intent_sidecar raised {type(e).__name__}: "
            f"{e!r} on input {raw[:120]!r}"
        )
    assert r2 is None or isinstance(r2, dict), (
        f"{label}: _parse_intent_sidecar returned {type(r2).__name__}"
    )
    # When the sidecar parser DOES return a dict, the contract demands a
    # fully-normalized shape — schema validation is the whole reason this
    # parser exists separately from the bare salvage utility.
    if isinstance(r2, dict):
        assert r2.get("turn_intent") in INTENT_LABELS, (
            f"{label}: sidecar returned dict but turn_intent="
            f"{r2.get('turn_intent')!r} not in INTENT_LABELS"
        )
        conf = r2.get("confidence")
        assert isinstance(conf, float) and 0.0 <= conf <= 1.0, (
            f"{label}: sidecar returned dict but confidence={conf!r}"
        )


# ---------------------------------------------------------------------------
# Test 1: arbitrary text — the catch-all
# ---------------------------------------------------------------------------

class TestArbitraryText:
    @_P012
    @given(st.text())
    def test_arbitrary_text_never_raises(self, raw: str) -> None:
        _check_universal_invariant(raw, label="arbitrary_text")


# ---------------------------------------------------------------------------
# Test 2: truncated streams (random JSON-shaped string cut at random offset)
# ---------------------------------------------------------------------------

class TestTruncatedStream:
    @_P012
    @given(
        prefix=st.sampled_from([
            "{",
            "{\"turn_intent\":",
            "{\"turn_intent\": \"casual_conversation\", \"confidence\":",
            "{\"a\": {\"b\": {\"c\":",
        ]),
        tail=st.text(max_size=200),
    )
    def test_truncated_json_prefix_with_random_tail(
        self, prefix: str, tail: str,
    ) -> None:
        _check_universal_invariant(prefix + tail, label="truncated_stream")

    @_P012
    @given(payload=st.text(min_size=1, max_size=500))
    def test_random_cutoff_position(self, payload: str) -> None:
        # Build a syntactically-plausible JSON envelope then truncate at
        # a random offset — the most realistic shape of an LLM stream that
        # was interrupted mid-output.
        full = '{"turn_intent": "casual_conversation", "extracted_value": ' \
               f'{json.dumps(payload)}, "confidence": 0.9}}'
        for cut in (0, len(full) // 4, len(full) // 2, 3 * len(full) // 4, len(full) - 1):
            _check_universal_invariant(full[:cut], label=f"truncate_at_{cut}")


# ---------------------------------------------------------------------------
# Test 3: code-block fences (```json ... ```)
# ---------------------------------------------------------------------------

class TestCodeBlockFences:
    @_P012
    @given(
        fence_lang=st.sampled_from(["", "json", "JSON", " json ", "javascript"]),
        body=st.text(max_size=300),
    )
    def test_fenced_block(self, fence_lang: str, body: str) -> None:
        wrapped = f"```{fence_lang}\n{body}\n```"
        _check_universal_invariant(wrapped, label="fenced_block")
        # Common LLM pattern: prose ABOVE the fence, JSON INSIDE.
        prosed = (
            "Sure, here's the result:\n"
            f"```{fence_lang}\n"
            '{"turn_intent": "casual_conversation", "confidence": 0.5}\n'
            "```\n"
            "Let me know if you need anything else."
        )
        # The salvaged dict should be recovered by the brace-find/rfind logic.
        r = _parse_json(prosed)
        assert r is None or isinstance(r, dict)


# ---------------------------------------------------------------------------
# Test 4: doubled keys (json.loads contract: last wins)
# ---------------------------------------------------------------------------

class TestDoubledKeys:
    @_P012
    @given(
        first=st.integers(min_value=-1000, max_value=1000),
        second=st.integers(min_value=-1000, max_value=1000),
    )
    def test_doubled_key_last_wins(self, first: int, second: int) -> None:
        raw = f'{{"x": {first}, "x": {second}}}'
        r = _parse_json(raw)
        assert r is None or isinstance(r, dict)
        # The Python json contract: duplicate keys → the LATER value wins.
        # Locking this behavior so a future parser swap doesn't silently
        # break callers that depend on it.
        if isinstance(r, dict):
            assert r.get("x") == second, (
                f"doubled-key contract violated: got x={r.get('x')!r}, "
                f"expected last value {second!r}"
            )


# ---------------------------------------------------------------------------
# Test 5: unescaped nested quotes (invalid → None)
# ---------------------------------------------------------------------------

class TestUnescapedNestedQuotes:
    @_P012
    @given(quoted=st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126), max_size=80))
    def test_unescaped_nested_quotes(self, quoted: str) -> None:
        raw = f'{{"text": "she said "{quoted}""}}'
        _check_universal_invariant(raw, label="unescaped_quotes")


# ---------------------------------------------------------------------------
# Test 6: trailing commas
# ---------------------------------------------------------------------------

class TestTrailingCommas:
    @_P012
    @given(payload=st.text(max_size=100))
    def test_trailing_comma_object(self, payload: str) -> None:
        raw = f'{{"key": {json.dumps(payload)},}}'
        _check_universal_invariant(raw, label="trailing_comma")


# ---------------------------------------------------------------------------
# Test 7: BOM + leading whitespace
# ---------------------------------------------------------------------------

class TestBomAndWhitespace:
    @_P012
    @given(
        prefix=st.sampled_from([
            "\ufeff", "  ", "\t", "\n\n", "\ufeff\n", "  \ufeff  ",
            "\u00a0", "\u200b", "",
        ]),
        suffix=st.sampled_from(["", "\n", "  ", "\n\n\t"]),
    )
    def test_bom_and_whitespace_padding(self, prefix: str, suffix: str) -> None:
        valid = '{"turn_intent": "casual_conversation", "confidence": 0.5}'
        raw = prefix + valid + suffix
        _check_universal_invariant(raw, label="bom_whitespace")


# ---------------------------------------------------------------------------
# Test 8: surrogate / control / weird Unicode
# ---------------------------------------------------------------------------

class TestWeirdUnicode:
    @_P012
    @given(
        # Include surrogate range (would be invalid UTF-8), control chars,
        # private-use, format chars — what an LLM might emit if its
        # tokenizer leaks raw code points.
        raw=st.text(
            alphabet=st.characters(
                blacklist_categories=(),  # allow everything including control
                min_codepoint=0,
                max_codepoint=0x10FFFF,
            ),
            max_size=200,
        ),
    )
    def test_weird_unicode_never_raises(self, raw: str) -> None:
        _check_universal_invariant(raw, label="weird_unicode")


# ---------------------------------------------------------------------------
# Test 9: empty / whitespace-only
# ---------------------------------------------------------------------------

class TestEmptyAndWhitespace:
    @_P012
    @given(
        raw=st.sampled_from([
            "", " ", "  ", "\n", "\t", "\r\n", "\n\n\t  ",
            "\ufeff", "\ufeff\n", "\u00a0\u200b",
        ]),
    )
    def test_empty_returns_none(self, raw: str) -> None:
        # All-whitespace input cannot contain a `{` → salvage finds nothing.
        assert _parse_json(raw) is None
        assert _parse_intent_sidecar(raw) is None


# ---------------------------------------------------------------------------
# Test 10: extremely large input (size DoS — must not OOM/hang)
# ---------------------------------------------------------------------------

class TestLargeInput:
    @_P012
    @given(payload=st.text(min_size=1, max_size=200))
    def test_very_large_repeated_payload(self, payload: str) -> None:
        # Build a multi-megabyte string by repetition.  Parser must return
        # within seconds — not seconds * size.
        big = (payload * 5_000)[:1_000_000]  # cap at ~1 MB to keep CI fast
        _check_universal_invariant(big, label="large_input")

    @_P012
    @given(n=st.integers(min_value=100, max_value=5000))
    def test_large_valid_json_object(self, n: int) -> None:
        # Programmatically build a large valid JSON object with N keys.
        # Parser must successfully parse it OR return None — never raise.
        obj = "{" + ", ".join(f'"k{i}": {i}' for i in range(n)) + "}"
        try:
            r = _parse_json(obj)
        except BaseException as e:  # noqa: BLE001
            pytest.fail(f"_parse_json raised on n={n}: {e!r}")
        assert r is None or isinstance(r, dict)


# ---------------------------------------------------------------------------
# Test 11: deeply nested input (recursion DoS — must catch RecursionError)
# ---------------------------------------------------------------------------

class TestDeeplyNested:
    @_P012
    @given(depth=st.integers(min_value=10, max_value=2000))
    def test_deep_nesting_does_not_raise(self, depth: int) -> None:
        # depth=2000 reliably exceeds Python's default recursion limit of
        # ~1000 (json.loads is iterative but uses C-stack frames).
        # Parser MUST catch RecursionError.  Without an explicit catch,
        # this is the most likely real bug Hypothesis surfaces.
        raw = ("[" * depth) + ("]" * depth)
        _check_universal_invariant(raw, label=f"deep_nest_{depth}")

    @_P012
    @given(depth=st.integers(min_value=10, max_value=2000))
    def test_deep_nested_object(self, depth: int) -> None:
        # Same but with objects.
        raw = ("{\"a\":" * depth) + "null" + ("}" * depth)
        _check_universal_invariant(raw, label=f"deep_obj_{depth}")


# ---------------------------------------------------------------------------
# Test 12: hypothesis-generated JSON values (round-trip soundness)
# ---------------------------------------------------------------------------

@st.composite
def _json_serializable(draw, max_depth: int = 4):
    """Recursive strategy for any JSON-serializable Python value."""
    if max_depth == 0:
        return draw(st.one_of(
            st.none(),
            st.booleans(),
            st.integers(min_value=-10**9, max_value=10**9),
            st.floats(allow_nan=False, allow_infinity=False, width=32),
            st.text(max_size=50),
        ))
    return draw(st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-10**9, max_value=10**9),
        st.floats(allow_nan=False, allow_infinity=False, width=32),
        st.text(max_size=50),
        st.lists(_json_serializable(max_depth=max_depth - 1), max_size=5),
        st.dictionaries(st.text(max_size=20), _json_serializable(max_depth=max_depth - 1), max_size=5),
    ))


class TestRoundTripValidJson:
    @settings(max_examples=500, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    @given(value=_json_serializable())
    def test_valid_json_round_trips_through_parser(self, value) -> None:
        """For any JSON-serializable Python value, json.dumps -> _parse_json
        must round-trip back to an equal value (when the outer type is a
        dict) OR return None (when the outer type is not a dict)."""
        raw = json.dumps(value)
        r = _parse_json(raw)
        if isinstance(value, dict):
            assert r == value, (
                f"round-trip failed: input={value!r}, parsed={r!r}"
            )
        else:
            # Non-dict top-level — _parse_json returns whatever json.loads
            # returns from the salvage path; non-dict top-levels won't have
            # a `{...}` to salvage, so result is None.  Anything is fine
            # AS LONG AS it doesn't raise.  We don't assert equality here.
            assert r is None or isinstance(r, dict)


# ---------------------------------------------------------------------------
# Targeted regression seeds — quick smoke that the corpus has explicit
# coverage for the named failure modes from the taxonomy.  These run with
# tiny max_examples just to anchor a positive count.
# ---------------------------------------------------------------------------

class TestExplicitFailureModeSeeds:
    @pytest.mark.parametrize("raw,desc", [
        ("",                                                "empty"),
        ("   ",                                             "whitespace-only"),
        ("\ufeff{}",                                        "bom-prefix"),
        ("not json",                                        "no-braces"),
        ("{",                                               "open-brace-only"),
        ("}",                                               "close-brace-only"),
        ('{"a": 1, "a": 2}',                                "doubled-key"),
        ('{"a": 1,}',                                       "trailing-comma"),
        ('{"text": "he said "hi""}',                        "nested-unescaped-quote"),
        ("```json\n{\"a\": 1}\n```",                        "fenced-json"),
        ("{\"deeply\": " + "{\"x\":" * 1500 + "null" + "}" * 1500 + "}", "deeply-nested-1500"),
        ("[" * 1500 + "]" * 1500,                           "deep-array-1500"),
        ("\x00\x01\x02",                                    "raw-control-chars"),
        ('{"x": NaN}',                                       "json-nan-extension"),
    ])
    def test_seed_does_not_raise(self, raw: str, desc: str) -> None:
        _check_universal_invariant(raw, label=f"seed:{desc}")


# ---------------------------------------------------------------------------
# P0.12 regression tests for the two production bugs Hypothesis surfaced
# ---------------------------------------------------------------------------

class TestP012RegressionFromHypothesis:
    """Hard regression tests pinned to the exact falsifying inputs that
    Hypothesis discovered.  Both inputs revealed real production bugs:

      Bug #1 (contract violation in core.brain_agent._parse_json):
          Input `"0"` returned `int(0)` instead of None.  Type annotation
          claimed `dict | None`, but the strict json.loads path returned
          whatever json.loads returned (int / list / str / bool / null).
          Callers do `parsed.get(...)` assuming dict → AttributeError at
          runtime on any non-dict valid JSON.

      Bug #2 (uncaught ValueError in core.brain._parse_intent_sidecar):
          Input with a long integer literal (5000 digits of '1') triggered
          Python 3.11+'s integer-string-conversion DoS limit, raising
          ValueError — not JSONDecodeError, which the except clause caught
          exclusively.  Adversarial LLM output could crash the parser.
    """

    def test_bug1_parse_json_returns_none_for_non_dict_top_level(self) -> None:
        """Falsifying input from TestArbitraryText: `raw='0'`."""
        # Pre-fix: returned int(0).  Post-fix: returns None.
        assert _parse_json("0") is None
        # Same for other non-dict JSON top-level types.
        assert _parse_json("[1, 2, 3]") is None
        assert _parse_json('"a string"') is None
        assert _parse_json("true") is None
        assert _parse_json("null") is None
        # Valid dict still returns the dict (positive regression guard).
        assert _parse_json('{"k": 1}') == {"k": 1}

    def test_bug2_parse_intent_sidecar_handles_oversized_int_string(self) -> None:
        """Falsifying input from TestLargeInput: payload='1' replicated to
        ~120 chars in the JSON envelope (Hypothesis simplified to a long
        run of '1's that exceeded the 4300-digit Python 3.11+ int-str
        conversion limit).  Pre-fix: raised ValueError mid-parse.
        Post-fix: returns None gracefully."""
        big_int_str = "1" * 5000
        raw = (
            '{"turn_intent": "casual_conversation", '
            '"extracted_value": ' + big_int_str + ', '
            '"confidence": 0.9}'
        )
        # MUST NOT raise.
        result = _parse_intent_sidecar(raw)
        # The result might be None (oversized int rejection) — what matters
        # is no exception leaks out.
        assert result is None or isinstance(result, dict)

    def test_bug2_parse_json_also_handles_oversized_int(self) -> None:
        """Same fix needs to apply to _parse_json (broader except)."""
        raw = '{"k": ' + ("1" * 5000) + "}"
        # Must not raise.
        result = _parse_json(raw)
        assert result is None or isinstance(result, dict)

    def test_p012_1_site_a_privacy_classifier_guards_none(self) -> None:
        """P0.12.1 Site A audit: PrivacyClassifier at brain_agent.py:404
        is FALSE-POSITIVE — L405's `if not parsed or not isinstance(parsed,
        dict): return None` already guards before the .get('level') access.
        Source-inspection regression guard to prevent removal of the
        existing safety net."""
        # NOTE: core.brain_agent was split into a package; the PrivacyClassifier
        # _parse_json call + dual-guard now live in core/brain_agent/privacy.py.
        import inspect, core.brain_agent.privacy as _privmod
        src = inspect.getsource(_privmod)
        # The PrivacyClassifier branch must keep the dual-guard pattern.
        idx_call = src.find("parsed = _parse_json(raw)")
        assert idx_call > -1, (
            "PrivacyClassifier _parse_json call site missing — audit context "
            "may have moved"
        )
        # Within the next 200 chars after the call, BOTH `not parsed` and
        # `isinstance(parsed, dict)` must appear (the guard).
        window = src[idx_call:idx_call + 300]
        assert "not parsed" in window and "isinstance(parsed, dict)" in window, (
            "PrivacyClassifier .get('level') access requires the dual-guard "
            "(`not parsed or not isinstance(parsed, dict)`) — the auditor's "
            "flagged Site A is safe iff this guard remains in place."
        )

    def test_p012_1_site_b_socialgraph_recovers_raw_array(self) -> None:
        """P0.12.1 Site B fix: SocialGraphAgent.extract must recover person
        mentions when the LLM returns a top-level JSON array (non-compliant
        with response_format=json_object).  Pre-P0.12, _parse_json returned
        the list and L5388's isinstance(data, list) caught it.  P0.12
        narrowed _parse_json to dict|None — that branch was DEAD and
        legitimate list responses were silently dropped.  P0.12.1 adds
        _parse_json_array fallback so raw-array responses parse correctly
        again.

        This is the falsifying-input-style regression: a known LLM output
        shape that the production code MUST handle but didn't post-Bug-#1."""
        from unittest.mock import AsyncMock
        from core.brain_agent import SocialGraphAgent
        import asyncio as _asyncio

        agent = SocialGraphAgent(http=AsyncMock())
        # Raw-array LLM response (response_format non-compliance):
        raw_array_response = (
            '[{"name": "Sarah", "attribute": "works at TCS"},'
            ' {"name": "Mike", "attribute": "loves cricket"}]'
        )
        # Monkey-patch _call_llm_chat inside the SocialGraphAgent module to
        # return our raw array response.  Use asyncio.run to drive the
        # async extract method.
        async def _fake_chat(*_args, **_kwargs):
            return raw_array_response
        # NOTE: SocialGraphAgent moved to core/brain_agent/agents/social.py,
        # which binds _call_llm_chat in its own namespace via
        # `from core.brain_agent._llm import _call_llm_chat`. Patch THAT binding
        # (not the package top level) so agent.extract sees the fake.
        import core.brain_agent.agents.social as _social
        orig = _social._call_llm_chat
        _social._call_llm_chat = _fake_chat
        try:
            result = _asyncio.run(
                agent.extract("Sarah works at TCS and Mike loves cricket.")
            )
        finally:
            _social._call_llm_chat = orig

        names = [m.get("name") for m in result]
        assert "Sarah" in names and "Mike" in names, (
            f"SocialGraphAgent must recover raw-array LLM responses post-"
            f"P0.12.  Got result={result!r} — _parse_json_array fallback may "
            "be missing or broken."
        )

    def test_p012_1_parse_json_array_returns_list_or_none(self) -> None:
        """_parse_json_array contract: returns list OR None, never raises.
        Mirrors the universal invariant for the sibling _parse_json."""
        # Valid list.
        assert _parse_json_array("[1, 2, 3]") == [1, 2, 3]
        # Top-level non-list returns None.
        assert _parse_json_array('{"x": 1}') is None
        assert _parse_json_array("42") is None
        assert _parse_json_array('"a string"') is None
        # Brace-salvage with surrounding prose.
        assert _parse_json_array('Sure! Here: [{"name": "Sarah"}]') == [{"name": "Sarah"}]
        # Empty / whitespace / completely invalid.
        assert _parse_json_array("") is None
        assert _parse_json_array("   ") is None
        assert _parse_json_array("not json") is None
        # DoS-class inputs must not raise.
        big_int_str = "1" * 5000
        assert _parse_json_array(f"[{big_int_str}]") is None  # ValueError caught
        deep = "[" * 1500 + "]" * 1500
        # Must not raise (RecursionError catch).
        try:
            result = _parse_json_array(deep)
        except BaseException as e:  # noqa: BLE001
            pytest.fail(f"_parse_json_array raised on deep nesting: {e!r}")
        assert result is None or isinstance(result, list)

    def test_bug1_fix_visible_in_source(self) -> None:
        """Source-inspection guard: a future revert of the isinstance(dict)
        gate would silently re-introduce Bug #1.  Lock the fix as a
        structural invariant.  Same shape as P0.11's AST detector."""
        import inspect, core.brain_agent as _ba
        src = inspect.getsource(_ba._parse_json)
        assert "isinstance(result, dict)" in src or "isinstance(data, dict)" in src, (
            "_parse_json must enforce its `dict | None` return contract via "
            "isinstance check — without it, non-dict JSON top-levels (int, "
            "list, str, bool, null) leak through as the wrong type and "
            "callers' .get(...) raises AttributeError."
        )
