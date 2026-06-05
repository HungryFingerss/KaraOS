"""test_pipeline_intent_search — intent search tests (split from test_pipeline.py, P1.A1 SP-1).

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


def test_intent_allows_happy_path_rename():
    """P1.4 happy path: classifier says assign_system_name with conf 0.99,
    tool args match, extracted_value appears in user_text → ALLOW. Mirrors
    Session 80 Turn 21 ("I'd love to call you Atlas")."""
    from pipeline import _intent_allows
    ok, reason = _intent_allows(
        tool_name="update_system_name",
        turn_intent="assign_system_name",
        confidence=0.99,
        extracted_value="Atlas",
        user_text="I'd love to call you Atlas.",
        tool_args={"name": "Atlas"},
    )
    assert ok is True, f"expected ALLOW, got ({ok}, {reason!r})"
    assert "intent match" in reason


def test_intent_allows_rejects_intent_mismatch():
    """P1.4: classifier label disagrees with the tool's required intent →
    REJECT. Mirrors Session 80 Turn 23 ("Okay, goodnight" classified as
    casual_conversation; shutdown tool fired). Shutdown requires
    request_shutdown intent; casual_conversation must be rejected even at
    high confidence."""
    from pipeline import _intent_allows
    ok, reason = _intent_allows(
        tool_name="shutdown",
        turn_intent="casual_conversation",
        confidence=0.95,
        extracted_value=None,
        user_text="Okay, goodnight. I'm heading to bed.",
        tool_args={},
    )
    assert ok is False
    assert "expected=request_shutdown" in reason


def test_intent_allows_rejects_below_confidence_floor():
    """P1.4: classifier picks a wrong label at low confidence → REJECT
    via the confidence gate. Mirrors Session 80 Turn 19 (conf=0.20,
    wrong label — escape hatch leak). Dual-gate's second line of defense."""
    from pipeline import _intent_allows
    ok, reason = _intent_allows(
        tool_name="update_system_name",
        turn_intent="assign_system_name",  # label happens to match here
        confidence=0.20,                    # but confidence is way below floor
        extracted_value=None,
        user_text="Hey, what is your name?",
        tool_args={},
    )
    assert ok is False
    assert "0.20" in reason and "0.75" in reason


def test_intent_allows_shutdown_floor_strictly_higher():
    """P1.4: shutdown uses INTENT_SHUTDOWN_CONF_MIN (0.80), not the general
    0.75 floor. Test the gap: 0.77 passes the general floor but MUST fail
    the shutdown floor — bigger blast radius, stricter gate."""
    from pipeline import _intent_allows
    from core.config import INTENT_CONFIDENCE_MIN, INTENT_SHUTDOWN_CONF_MIN
    # Pick a conf value strictly between the two floors.
    assert INTENT_SHUTDOWN_CONF_MIN > INTENT_CONFIDENCE_MIN, "precondition"
    mid = (INTENT_CONFIDENCE_MIN + INTENT_SHUTDOWN_CONF_MIN) / 2  # e.g. 0.775
    # Non-shutdown tool at mid → ALLOW (above general floor).
    ok_general, _ = _intent_allows(
        tool_name="update_system_name",
        turn_intent="assign_system_name",
        confidence=mid,
        extracted_value="Atlas",
        user_text="Call you Atlas",
        tool_args={"name": "Atlas"},
    )
    assert ok_general is True, "general floor must admit mid-band confidence"
    # Shutdown tool at the SAME confidence → REJECT.
    ok_shutdown, reason = _intent_allows(
        tool_name="shutdown",
        turn_intent="request_shutdown",
        confidence=mid,
        extracted_value=None,
        user_text="shut down please",
        tool_args={},
    )
    assert ok_shutdown is False
    assert str(INTENT_SHUTDOWN_CONF_MIN) in reason


def test_intent_allows_rejects_ungrounded_extracted_value():
    """P1.4 grounding rule: extracted_value must appear in user_text. If
    the classifier hallucinates a name the user never said, REJECT even
    at high confidence + matching intent. Defense against classifier
    + LLM double-failure."""
    from pipeline import _intent_allows
    ok, reason = _intent_allows(
        tool_name="update_system_name",
        turn_intent="assign_system_name",
        confidence=0.99,
        extracted_value="Nova",  # classifier hallucinated this
        user_text="I want a new name for you",  # user never said Nova
        tool_args={"name": "Nova"},
    )
    assert ok is False
    assert "not grounded" in reason


def test_intent_allows_rejects_tool_arg_mismatch():
    """P1.4 arg cross-check: tool_args[arg_key] must equal extracted_value.
    Catches the case where the classifier correctly extracted what the user
    said, but the LLM's tool_call arg is a *different* name (a rename
    fabrication the user never authorized)."""
    from pipeline import _intent_allows
    ok, reason = _intent_allows(
        tool_name="update_system_name",
        turn_intent="assign_system_name",
        confidence=0.99,
        extracted_value="Atlas",
        user_text="I'd love to call you Atlas",
        tool_args={"name": "Nova"},  # LLM fabricated a different name
    )
    assert ok is False
    assert "'Nova'" in reason and "'Atlas'" in reason


def test_intent_allows_rejects_cyrillic_homoglyph():
    """P1.4 threat-model: the classifier may extract 'Kаra' (with Cyrillic а,
    U+0430) when the user said 'Kara' (Latin a) — or vice versa. NFKC-
    normalized grounding should NOT be fooled by visual equivalence when the
    code points differ AND the tool_args use the spoofed variant. Architect
    review called this out explicitly; cheap coverage now beats discovery
    under live adversarial conditions.

    The mismatch is between user_text (Latin) and both extracted_value +
    tool_args (Cyrillic) — grounding fails at the substring check."""
    from pipeline import _intent_allows
    ok, reason = _intent_allows(
        tool_name="update_system_name",
        turn_intent="assign_system_name",
        confidence=0.99,
        extracted_value="K\u0430ra",      # Cyrillic а in position 1
        user_text="I want to call you Kara",  # Latin a
        tool_args={"name": "K\u0430ra"},  # matches extracted_value
    )
    assert ok is False, (
        "Cyrillic homoglyph must fail the grounding substring check — "
        "NFKC normalizes compatibility variants but does NOT alias Cyrillic "
        "а (U+0430) to Latin a (U+0061). This is the correct behavior: "
        "if the code points differ in the *tool action*, reject."
    )
    assert "not grounded" in reason


def test_intent_allows_pass_through_for_unmapped_tool():
    """P1.4: tools not in TOOL_INTENT_MAP (e.g. search_memory) pass through
    the validator unconditionally. The validator is additive — it can only
    REJECT gated tools; it MUST NOT add new restrictions on tools that
    weren't previously gated. Safe-default preserves existing behavior."""
    from pipeline import _intent_allows
    ok, reason = _intent_allows(
        tool_name="search_memory",  # not in TOOL_INTENT_MAP
        turn_intent="casual_conversation",  # any value
        confidence=0.0,                      # even zero conf
        extracted_value=None,
        user_text="tell me about Jagan",
        tool_args={"person_name": "Jagan", "query": "hobbies"},
    )
    assert ok is True
    assert "not gated" in reason


def test_intent_allows_rejects_ungrounded_arg_when_extracted_value_none():
    """Session 87 regression (grounding-gap fix): classifier abstains
    (extracted_value=None) but LLM proposes an arg not present in user_text.
    Gate must reject.

    Was: `_intent_allows` skipped ALL grounding when extracted_value=None,
    letting hallucinated args through. The Session 86 live run caught this —
    divergence row showed 'Hey, it's not Jagan. I told you to rename my
    name.' classified as assign_own_name@0.80 with value=None, and the LLM
    proposed {'name': 'Kara'} which slipped through and renamed the person
    to Kara (user spent 3 turns correcting it). Fix: elif branch verifies
    `tool_args[arg_key]` appears in user_text when classifier didn't
    extract."""
    from pipeline import _intent_allows
    allowed, reason = _intent_allows(
        tool_name="update_person_name",
        turn_intent="assign_own_name",
        confidence=0.80,
        extracted_value=None,   # classifier abstained
        user_text="Hey, it's not Jagan. I told you to rename my name.",
        tool_args={"name": "Kara"},   # LLM hallucinated Kara from history
    )
    assert allowed is False
    assert "not grounded" in reason
    # The rejected arg name must appear in the reason so operators can
    # grep for the hallucination without decoding the structured_* cols.
    assert "Kara" in reason or "kara" in reason.lower()


def test_intent_allows_strips_im_contraction_from_extracted_value():
    """Session 94 Fix #2: Whisper sometimes mangles 'I'm Lexi' into
    'Imlexi' (no space). When the classifier lazily echoes the mangled
    form as ``extracted_value='Imlexi'`` but the user_text is the clean
    ``"I'm Lexi"``, the substring check ``'Imlexi' in "I'm Lexi"`` fails
    and the rename gets rejected spuriously. Fix: strip the Im/I'm
    contraction from ``extracted_value`` before grounding. After strip,
    ``'Lexi' in "I'm Lexi"`` matches — rename passes as intended."""
    from pipeline import _intent_allows
    ok, reason = _intent_allows(
        tool_name="update_person_name",
        turn_intent="assign_own_name",
        confidence=0.90,
        extracted_value="Imlexi",          # Whisper-mangled contraction
        user_text="Hi Kara, I'm Lexi",     # clean STT — contains "Lexi"
        tool_args={"name": "Imlexi"},
    )
    assert ok is True, f"expected allow after Im-strip, got reason: {reason!r}"
    assert "intent match" in reason


def test_intent_allows_strips_im_contraction_from_both_sides_of_arg_check():
    """Session 94 Fix #2: the cross-check (``tool_args[arg_key] ==
    extracted_value``) must also normalize Im-contraction on both sides
    so a smart-classifier extracted_value='Lexi' matches the lazy-LLM
    tool_args['name']='Imlexi' case. Without this, classifier + LLM
    disagreement on the contraction form would reject a legitimate
    rename.

    Also exercises the Fix #2 edge where the classifier is smart
    (extracted clean 'Lexi') but the LLM was less smart (echoed mangled
    'Imlexi' from STT into tool_args)."""
    from pipeline import _intent_allows
    ok, reason = _intent_allows(
        tool_name="update_person_name",
        turn_intent="assign_own_name",
        confidence=0.95,
        extracted_value="Lexi",                # classifier clean
        user_text="Hi Kara, Imlexi, nice to meet you",  # STT-mangled
        tool_args={"name": "Imlexi"},          # LLM echoed mangled form
    )
    assert ok is True, f"expected allow after Im-strip on arg cross-check, got reason: {reason!r}"


def test_intent_allows_allows_grounded_arg_when_extracted_value_none():
    """Session 87 complementary case: classifier abstains on extraction but
    the LLM's proposed arg DOES appear in user_text. This is a legit
    classifier-abstain case — extraction is optional; grounding is the real
    invariant — so the gate must ALLOW. Guards against the fix over-
    rejecting legit renames where the classifier just couldn't pull the
    name cleanly."""
    from pipeline import _intent_allows
    allowed, reason = _intent_allows(
        tool_name="update_person_name",
        turn_intent="assign_own_name",
        confidence=0.80,
        extracted_value=None,   # classifier abstained
        user_text="You know, just call me Sarah",
        tool_args={"name": "Sarah"},   # Sarah IS in user_text — legit
    )
    assert allowed is True
    assert "intent match" in reason.lower()


def test_search_web_tool_description_has_never_rules():
    """Issue 2: search_web description must contain explicit NEVER constraints."""
    from core.brain import TOOLS
    sw = next(t for t in TOOLS if t["function"]["name"] == "search_web")
    desc = sw["function"]["description"]
    assert "NEVER" in desc
    assert "person's name" in desc


def test_search_web_system_contribution_in_built_prompt():
    """Issue 2: search_web system_contribution must be injected into every built system prompt."""
    from core.brain import _build_system_prompt
    prompt = _build_system_prompt(person_name=None)
    assert "NEVER call search_web on conversational turns" in prompt


def test_search_lie_re_no_match_checking_that():
    """BUG-4: 'checking that' in everyday context must not trigger lie detection."""
    from core.brain import _SEARCH_LIE_RE
    assert not _SEARCH_LIE_RE.search("I'm checking that you got my message")
    assert not _SEARCH_LIE_RE.search("I was checking that with my notes")


def test_search_lie_re_no_match_let_me_look():
    """BUG-4: 'let me look' without online/web context must not trigger lie detection."""
    from core.brain import _SEARCH_LIE_RE
    assert not _SEARCH_LIE_RE.search("let me look at the picture")
    assert not _SEARCH_LIE_RE.search("let me look that over")


def test_search_lie_re_matches_genuine_search_claims():
    """BUG-4: Unambiguous 'check/search online' phrases must still trigger lie detection."""
    from core.brain import _SEARCH_LIE_RE
    assert _SEARCH_LIE_RE.search("let me check online")
    assert _SEARCH_LIE_RE.search("let me search online for that")
    assert _SEARCH_LIE_RE.search("searching the web for that")
    assert _SEARCH_LIE_RE.search("looking that up online")


async def test_web_search_rejects_empty_query():
    """Bug R: calling _web_search('') must short-circuit client-side with a
    structured error hint — never hit Tavily. The LLM's self-awareness
    question triggered a search_web('') call in the 2026-04-21 run; Tavily
    returned 400 and the tool dispatch cascaded into an error filler."""
    import core.brain as brain
    from unittest.mock import patch, MagicMock

    brain._tavily_http.post = MagicMock(side_effect=AssertionError("HTTP must not fire"))
    result = await brain._web_search("")
    assert isinstance(result, dict), f"expected dict error-shape, got {type(result).__name__}"
    assert result.get("error") == "empty_query"
    assert "hint" in result and "training knowledge" in result["hint"].lower()


async def test_web_search_rejects_whitespace_query():
    """Bug R: pure-whitespace queries are equivalent to empty — the strip()
    before length check must catch them."""
    import core.brain as brain
    from unittest.mock import MagicMock

    brain._tavily_http.post = MagicMock(side_effect=AssertionError("HTTP must not fire"))
    result = await brain._web_search("   ")
    assert isinstance(result, dict) and result.get("error") == "empty_query"


async def test_web_search_rejects_short_query_below_threshold(monkeypatch):
    """Bug R: the threshold is configurable. Raise it to 10 chars; a 5-char
    query that would normally pass must now be rejected with the same shape."""
    import core.brain as brain
    from unittest.mock import MagicMock

    monkeypatch.setattr(brain, "SEARCH_QUERY_MIN_CHARS", 10)
    brain._tavily_http.post = MagicMock(side_effect=AssertionError("HTTP must not fire"))
    result = await brain._web_search("apple")  # 5 chars
    assert isinstance(result, dict) and result.get("error") == "empty_query"


def test_should_search_web_rejects_personal_statement():
    """Bug T: 'My favorite team is X' is a personal statement, not a request
    for live data. Server-side gate must reject — observed 3× in the
    2026-04-21 live run."""
    from core.brain import _should_search_web
    allowed, reason = _should_search_web(
        "Mumbai Indians", "My favorite team is Mumbai Indians",
    )
    assert allowed is False
    assert "personal statement" in reason.lower() or "opinion" in reason.lower()


def test_should_search_web_rejects_ai_opinion_query():
    """Bug T: 'do you have a favorite team?' asks the AI for ITS opinion —
    no web search can answer that. Observed in the 2026-04-21 run."""
    from core.brain import _should_search_web
    allowed, _ = _should_search_web(
        "favorite IPL team", "do you have a favorite team?",
    )
    assert allowed is False


def test_should_search_web_rejects_conversational_closer():
    """Bug T: 'okay okay I'll come back' is a closer. The LLM also fired
    shutdown on this turn (line 557 of 2026-04-21 run); a search would have
    been equally wrong."""
    from core.brain import _should_search_web
    allowed, _ = _should_search_web(
        "anything",  "okay okay I'll come back okay I'll come back in",
    )
    assert allowed is False


def test_should_search_web_accepts_live_data_query():
    """Bug T: 'what's the weather today?' contains both a time marker
    (today) and a domain keyword (weather). Allow."""
    from core.brain import _should_search_web
    allowed, reason = _should_search_web(
        "weather Mumbai today", "what's the weather in Mumbai today?",
    )
    assert allowed is True
    assert "live-data" in reason.lower()


def test_should_search_web_accepts_score_query():
    """Bug T: 'who won the IPL match today?' is a quintessential live-data
    query — match keyword + today + 'who won' question shape. Allow."""
    from core.brain import _should_search_web
    allowed, _ = _should_search_web(
        "IPL match result today", "who won the IPL match today?",
    )
    assert allowed is True


def test_should_search_web_default_denies_unmarked_queries():
    """Bug T: when neither block nor allow patterns match, default deny.
    Llama-3.3 should prefer training knowledge over speculative searches —
    the cost of a wasted search is higher than a slightly less-current answer."""
    from core.brain import _should_search_web
    allowed, reason = _should_search_web(
        "Detroit Become Human characters", "Tell me about the game Detroit",
    )
    assert allowed is False
    assert "no live-data marker" in reason.lower()


def test_should_search_web_does_not_block_know_have_for_live_data():
    """Bug T tightening (Session 71 design choice): unlike the reviewer's
    broader block list, we did NOT block 'do you know' / 'do you have' as
    blanket opinion verbs. Test that 'do you know today's weather?' still
    reaches the allow check (live-data keyword present) and is allowed."""
    from core.brain import _should_search_web
    allowed, _ = _should_search_web(
        "today weather", "do you know today's weather?",
    )
    assert allowed is True, (
        "block list must not catch 'do you know' / 'do you have' generically — "
        "would suppress legit live-data phrasings"
    )


def test_search_web_tool_description_forbids_empty_query():
    """Bug R Layer 2: the tool description tells the LLM not to call with
    an empty query. Source-inspection on the TOOLS entry."""
    from core import brain
    sw_entry = next(t for t in brain.TOOLS if t["function"]["name"] == "search_web")
    desc = sw_entry["function"]["description"]
    assert "empty" in desc.lower() and "whitespace" in desc.lower(), (
        "search_web description must explicitly forbid empty/whitespace queries"
    )


async def test_web_search_injects_date_for_time_sensitive_query():
    """Issue 3: Queries with time-sensitive keywords get today's date appended."""
    import core.brain as brain
    from datetime import datetime
    from unittest.mock import AsyncMock, patch, MagicMock

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"answer": "MI vs CSK today", "results": []}

    captured = {}

    async def fake_post(url, json=None, **kw):
        captured["json"] = json
        return mock_resp

    orig_cache = brain._search_cache.copy()
    brain._search_cache.clear()
    try:
        with patch.object(brain._tavily_http, "post", side_effect=fake_post):
            await brain._web_search("IPL match tonight")
        assert "query" in captured["json"]
        today_str_part = datetime.now().strftime("%B %Y")   # e.g. "April 2026"
        assert today_str_part in captured["json"]["query"], \
            f"Date not injected: {captured['json']['query']!r}"
    finally:
        brain._search_cache.clear()
        brain._search_cache.update(orig_cache)


async def test_web_search_no_date_injection_for_general_query():
    """Issue 3: General (non-time-sensitive) queries are NOT modified."""
    import core.brain as brain
    from unittest.mock import MagicMock, patch

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"answer": "Paris", "results": []}

    captured = {}

    async def fake_post(url, json=None, **kw):
        captured["json"] = json
        return mock_resp

    orig_cache = brain._search_cache.copy()
    brain._search_cache.clear()
    try:
        with patch.object(brain._tavily_http, "post", side_effect=fake_post):
            await brain._web_search("capital of France")
        assert captured["json"]["query"] == "capital of France"
    finally:
        brain._search_cache.clear()
        brain._search_cache.update(orig_cache)


async def test_web_search_cache_hit_skips_api():
    """Issue 3: Second identical query returns cached result without calling Tavily."""
    import core.brain as brain
    import time
    from unittest.mock import MagicMock, patch

    orig_cache = brain._search_cache.copy()
    brain._search_cache.clear()
    brain._search_cache["capital of france"] = ("Paris is the capital.", time.time())

    mock_post = MagicMock()
    try:
        with patch.object(brain._tavily_http, "post", side_effect=mock_post):
            result = await brain._web_search("capital of France")
        mock_post.assert_not_called()
        assert result == "Paris is the capital."
    finally:
        brain._search_cache.clear()
        brain._search_cache.update(orig_cache)


async def test_web_search_cache_miss_after_ttl():
    """Issue 3: Expired cache entry (> TTL) triggers a fresh API call."""
    import core.brain as brain
    import time
    from unittest.mock import MagicMock, patch

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"answer": "Fresh result", "results": []}

    orig_cache = brain._search_cache.copy()
    brain._search_cache.clear()
    # Expire the cache entry (600 s > SEARCH_CACHE_TTL_SECS = 300)
    brain._search_cache["capital of france"] = ("Stale result.", time.time() - 600)

    called = []

    async def fake_post(url, json=None, **kw):
        called.append(json)
        return mock_resp

    try:
        with patch.object(brain._tavily_http, "post", side_effect=fake_post):
            await brain._web_search("capital of France")
        assert len(called) == 1, "Expired cache entry must trigger a fresh API call"
    finally:
        brain._search_cache.clear()
        brain._search_cache.update(orig_cache)


async def test_web_search_uses_advanced_depth_and_max_results():
    """Issue 3: Tavily request must use TAVILY_SEARCH_DEPTH and TAVILY_MAX_RESULTS from config."""
    import core.brain as brain
    from core.config import TAVILY_SEARCH_DEPTH, TAVILY_MAX_RESULTS
    from unittest.mock import MagicMock, patch

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"answer": "25°C", "results": []}

    captured = {}

    async def fake_post(url, json=None, **kw):
        captured["json"] = json
        return mock_resp

    orig_cache = brain._search_cache.copy()
    brain._search_cache.clear()
    try:
        with patch.object(brain._tavily_http, "post", side_effect=fake_post):
            await brain._web_search("current weather London")
        assert captured["json"]["search_depth"] == TAVILY_SEARCH_DEPTH
        assert captured["json"]["max_results"]   == TAVILY_MAX_RESULTS
    finally:
        brain._search_cache.clear()
        brain._search_cache.update(orig_cache)


def test_tavily_log_shows_answer_not_query(capsys):
    """The Tavily log line must show the result text, not the search query."""
    import asyncio
    from unittest.mock import patch, AsyncMock, MagicMock
    import core.brain as _brain_mod

    mock_resp = MagicMock()
    mock_resp.raise_for_status = lambda: None
    mock_resp.json.return_value = {
        "answer": "Punjab Kings won the match by 6 wickets.",
        "results": [],
    }

    async def _run():
        with patch.object(_brain_mod, "_tavily_http") as mock_http, \
             patch.object(_brain_mod, "TAVILY_API_KEY", "fake-key"), \
             patch.object(_brain_mod, "_search_cache", {}):
            mock_http.post = AsyncMock(return_value=mock_resp)
            return await _brain_mod._web_search("Who won the IPL match?")

    result = asyncio.run(_run())
    captured = capsys.readouterr()
    assert result is not None
    assert "Punjab Kings won" in captured.out, \
        f"Log should show answer text, not query. Got: {captured.out!r}"


def test_tavily_log_truncates_long_answer(capsys):
    """Long Tavily answers must be truncated to 80 chars + ellipsis in the log."""
    import asyncio
    from unittest.mock import patch, AsyncMock, MagicMock
    import core.brain as _brain_mod

    long_answer = "A" * 200

    mock_resp = MagicMock()
    mock_resp.raise_for_status = lambda: None
    mock_resp.json.return_value = {"answer": long_answer, "results": []}

    async def _run():
        with patch.object(_brain_mod, "_tavily_http") as mock_http, \
             patch.object(_brain_mod, "TAVILY_API_KEY", "fake-key"), \
             patch.object(_brain_mod, "_search_cache", {}):
            mock_http.post = AsyncMock(return_value=mock_resp)
            return await _brain_mod._web_search("test query")

    asyncio.run(_run())
    captured = capsys.readouterr()
    if "Tavily answer" in captured.out:
        log_line = [l for l in captured.out.splitlines() if "Tavily answer" in l][0]
        assert "..." in log_line, "Long answer must be truncated with '...'"
        assert "200 chars" in log_line, "Char count must show full length"


def test_should_run_recognition_brand_new_track():
    """#11: Brand-new track (not in track_identity or unrecognized_tracks) → True."""
    from pipeline import _should_run_recognition
    result = _should_run_recognition(42, {}, {}, {}, 1000.0)
    assert result is True


def test_should_run_recognition_known_track_within_5s():
    """#11: Known track recognized within last 5s → False (skip GPU work)."""
    from pipeline import _should_run_recognition
    import time as _t
    now = _t.monotonic()
    track_identity = {42: "jagan_001"}
    persons_in_frame = {"jagan_001": {"last_recognized_at": now - 2.0}}  # 2s ago
    result = _should_run_recognition(42, track_identity, {}, persons_in_frame, now)
    assert result is False


def test_should_run_recognition_known_track_stale_5s():
    """#11: Known track with last_recognized_at > 5s → True (refresh)."""
    from pipeline import _should_run_recognition
    import time as _t
    now = _t.monotonic()
    track_identity = {42: "jagan_001"}
    persons_in_frame = {"jagan_001": {"last_recognized_at": now - 6.0}}  # 6s ago
    result = _should_run_recognition(42, track_identity, {}, persons_in_frame, now)
    assert result is True


def test_should_run_recognition_unknown_track_within_2s():
    """#11: Unknown track seen within last 2s → False (retry throttled)."""
    from pipeline import _should_run_recognition
    import time as _t
    now = _t.monotonic()
    unrecognized_tracks = {99: now - 1.0}  # 1s ago
    result = _should_run_recognition(99, {}, unrecognized_tracks, {}, now)
    assert result is False


def test_should_run_recognition_unknown_track_stale_2s():
    """#11: Unknown track last seen > 2s ago → True (retry)."""
    from pipeline import _should_run_recognition
    import time as _t
    now = _t.monotonic()
    unrecognized_tracks = {99: now - 3.0}  # 3s ago
    result = _should_run_recognition(99, {}, unrecognized_tracks, {}, now)
    assert result is True


def test_should_run_recognition_none_track_id():
    """#11: None track_id (no SORT tracking) → always True."""
    from pipeline import _should_run_recognition
    result = _should_run_recognition(None, {}, {}, {}, 1000.0)
    assert result is True


def test_harvest_pairs_stt_with_following_intent(tmp_path):
    """P1.5: harvest must pair each raw STT line with the nearest following
    [Intent] log (within HARVEST_LOOKAHEAD lines). Mirrors the layout of
    Session 80 Turn 21 — STT on one line, Intent log a few lines later."""
    from tests.harvest_golden import harvest
    log = tmp_path / "terminal_output_2026-04-22_233426.md"
    log.write_text(
        "[Pipeline] Starting...\n"
        "[STT] 23:34:46.504 (329ms) \"I'd love to call you Atlas.\"\n"
        "[Audio] Listening...\n"
        "[Voice] 23:34:47.082 Routing: current — jagan (score=0.612)\n"
        "[Brain] 23:34:48.931 Tool: update_system_name({'name': 'Atlas'})\n"
        "[Intent] 23:34:54.650 tools=[update_system_name] classified=assign_system_name"
        " value='Atlas' conf=0.99 reason=\"The user explicitly\"\n",
        encoding="utf-8",
    )
    rows = harvest(tmp_path)
    assert len(rows) == 1
    r = rows[0]
    assert r["user_text"] == "I'd love to call you Atlas."
    assert r["observed_intent"] == "assign_system_name"
    assert r["observed_value"] == "Atlas"
    assert r["observed_conf"] == 0.99
    assert r["source"] == "real_observed"
    assert r["source_file"].startswith("terminal_output_2026-04-22_233426.md:")
    assert r["expected_intent"] is None
    assert r["expected_value"] is None


def test_harvest_stt_without_intent_still_captured(tmp_path):
    """P1.5: non-gated-tool turns don't fire the classifier. STT without
    a paired [Intent] must still enter the golden set with observed_*=null
    so it gets hand-labeled — those turns represent the majority of the
    calibration distribution (~95% are non-gated)."""
    from tests.harvest_golden import harvest
    log = tmp_path / "terminal_output_A.md"
    log.write_text(
        "[STT] 12:00:00.000 (100ms) 'hello there'\n"
        "[Audio] Listening...\n"
        "[Brain] Context: history=1 turns\n"
        # No [Intent] line anywhere — casual turn
        "[Pipeline] Turn end: 12:00:02.000\n",
        encoding="utf-8",
    )
    rows = harvest(tmp_path)
    assert len(rows) == 1
    r = rows[0]
    assert r["user_text"] == "hello there"
    assert r["observed_intent"] is None
    assert r["observed_value"] is None
    assert r["observed_conf"] is None


def test_harvest_stops_at_next_stt_before_intent(tmp_path):
    """P1.5: the lookahead must stop when it hits the NEXT STT — otherwise
    turn N's STT could be falsely paired with turn N+1's [Intent], yielding
    a catastrophically wrong observation label."""
    from tests.harvest_golden import harvest
    log = tmp_path / "terminal_output_B.md"
    log.write_text(
        # Turn 1: no Intent fires
        "[STT] 12:00:00.000 (100ms) 'first utterance'\n"
        "[Audio] Listening...\n"
        # Turn 2: gated tool + Intent
        "[STT] 12:00:05.000 (120ms) \"call you Atlas\"\n"
        "[Intent] 12:00:06.000 tools=[update_system_name] classified=assign_system_name"
        " value='Atlas' conf=0.99 reason=\"x\"\n",
        encoding="utf-8",
    )
    rows = harvest(tmp_path)
    assert len(rows) == 2
    # Turn 1 must NOT steal turn 2's Intent label.
    r1 = next(r for r in rows if r["user_text"] == "first utterance")
    assert r1["observed_intent"] is None
    # Turn 2 gets its own label.
    r2 = next(r for r in rows if r["user_text"] == "call you Atlas")
    assert r2["observed_intent"] == "assign_system_name"


def test_harvest_dedupe_keeps_up_to_two_per_lowercase(tmp_path):
    """P1.5: reviewer's rule — keep at most 2 instances per exact-lowercase
    user_text. Free 60-80% reduction in labeling work without losing drift
    signal (one instance catches the utterance; two instances confirm
    classifier stability across repetitions)."""
    from tests.harvest_golden import harvest, dedupe_rows
    log = tmp_path / "terminal_output_C.md"
    # Four "yeah"s (case variants) and one "hmm" — dedup should yield 2+1=3.
    log.write_text(
        "[STT] 12:00:00.000 (50ms) 'yeah'\n"
        "[STT] 12:00:01.000 (50ms) 'Yeah'\n"
        "[STT] 12:00:02.000 (50ms) 'YEAH'\n"
        "[STT] 12:00:03.000 (50ms) 'yeah'\n"
        "[STT] 12:00:04.000 (50ms) 'hmm'\n",
        encoding="utf-8",
    )
    rows = harvest(tmp_path)
    assert len(rows) == 5  # pre-dedup
    deduped = dedupe_rows(rows)
    assert len(deduped) == 3
    # Two "yeah"-family rows + one "hmm" row.
    yeah_rows = [r for r in deduped if r["user_text"].casefold() == "yeah"]
    assert len(yeah_rows) == 2
    hmm_rows = [r for r in deduped if r["user_text"].casefold() == "hmm"]
    assert len(hmm_rows) == 1


def test_golden_intent_jsonl_schema():
    """P1.5: every row of tests/golden_intent.jsonl must have the required
    keys, expected_intent must be a valid INTENT_LABEL, and source must be
    one of the fixed taxonomy values. Catches typos at CI time before they
    corrupt the eval bench's metrics."""
    import json, pathlib
    from core.config import INTENT_LABELS
    path = pathlib.Path(__file__).resolve().parent.parent / "tests" / "golden_intent.jsonl"
    assert path.exists(), "golden_intent.jsonl must exist after P1.5 Step 3"
    required_keys = {
        "user_text", "expected_intent", "expected_value", "source", "note",
    }
    valid_sources = {
        "real_observed",
        "adversarial",
        "synthetic_common",
        "legacy_synthetic",
    }
    # regression_<session> is also valid — test below handles the prefix case.
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) >= 60, f"adversarial alone should be ≥60 rows, got {len(rows)}"
    for i, row in enumerate(rows, 1):
        missing = required_keys - set(row.keys())
        assert not missing, f"row {i} missing keys: {missing}"
        assert row["expected_intent"] in INTENT_LABELS, (
            f"row {i} expected_intent={row['expected_intent']!r} not in INTENT_LABELS"
        )
        src = row["source"]
        is_valid_source = (
            src in valid_sources or src.startswith("regression_")
        )
        assert is_valid_source, (
            f"row {i} source={src!r} — must be one of {valid_sources} "
            f"or start with 'regression_'"
        )
        assert isinstance(row["user_text"], str), f"row {i} user_text must be str"
        assert row["expected_value"] is None or isinstance(row["expected_value"], str), (
            f"row {i} expected_value must be None or str"
        )


def test_golden_intent_jsonl_adversarial_coverage():
    """P1.5: the adversarial subset must cover every high-risk failure
    pattern documented in prior sessions — Detroit/Kara false-accepts,
    identity denials, implicit-shutdown cases, prompt injection, homoglyph.
    A missing pattern means we're not testing the threat model."""
    import json, pathlib
    path = pathlib.Path(__file__).resolve().parent.parent / "tests" / "golden_intent.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    adversarial = [r for r in rows if r["source"] == "adversarial"]
    all_texts = " || ".join(r["user_text"] for r in adversarial)
    # Pattern classes that MUST have at least one adversarial row.
    required_patterns = [
        "Detroit",           # Session 71 Bug S regression
        "Cara",              # Session 77 Kara variant regex-miss
        "call me",           # generic nickname assign
        "Mary Ann",          # multi-word name
        "not Javan",         # identity denial phrasing
        "shut down",         # shutdown command (lowercase — normalized match)
        "Goodnight",         # implicit-shutdown case
        "favorite team",     # Session 71 Bug T personal-statement / opinion-query
        "<user_said>",       # prompt-injection attempt
        "K\u0430ra",        # Cyrillic homoglyph (U+0430)
    ]
    lowered = all_texts.casefold()
    for pat in required_patterns:
        assert pat.casefold() in lowered, (
            f"adversarial coverage MISSING pattern {pat!r} — every documented "
            f"failure class must have ≥1 adversarial row"
        )


def test_golden_intent_jsonl_high_blast_radius_min_coverage():
    """P1.5 (reviewer's spec): the golden set must have ≥25 rows per
    high-blast-radius intent (shutdown-family + deny_identity). Rationale:
    authorization bugs in these tools have the largest blast radius (DB
    corruption, wrongful shutdown), so precision/recall statistics on them
    need a strong sample size. Hybrid of adversarial + synthetic_common +
    real_observed is fine — the test counts across ALL sources."""
    import json, pathlib
    path = pathlib.Path(__file__).resolve().parent.parent / "tests" / "golden_intent.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    shutdown_family = sum(
        1 for r in rows
        if r["expected_intent"] in ("request_shutdown", "question_about_shutdown")
    )
    deny = sum(1 for r in rows if r["expected_intent"] == "deny_identity")
    assert shutdown_family >= 25, (
        f"shutdown-family has {shutdown_family} rows; spec requires ≥25 "
        f"(authorization-bug blast radius = wrongful shutdown of the system)"
    )
    assert deny >= 25, (
        f"deny_identity has {deny} rows; spec requires ≥25 "
        f"(authorization-bug blast radius = rewriting the wrong person's identity)"
    )


def test_golden_intent_jsonl_all_labels_represented():
    """P1.5: every one of the 12 INTENT_LABELS must have ≥1 row in the
    golden set, otherwise precision/recall is undefined for that class and
    the eval bench has a blind spot."""
    import json, pathlib
    from core.config import INTENT_LABELS
    path = pathlib.Path(__file__).resolve().parent.parent / "tests" / "golden_intent.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    present = {r["expected_intent"] for r in rows}
    missing = INTENT_LABELS - present
    assert not missing, (
        f"INTENT_LABELS not represented in golden set: {missing}. "
        f"Every label needs ≥1 row for eval bench precision/recall."
    )


def test_golden_intent_jsonl_session_82_relabels_present():
    """Session 83: bench run 20260421_192323 surfaced 6 rows whose expected
    labels disagreed with a CONSISTENT classifier reading — 5 out-of-context
    confirm_identity affirmations + 1 correction phrasing. Relabeled to
    align with the classifier's (correct) reading, and tagged with
    source=regression_session_82_relabel so the permanent taxonomy slot
    preserves the provenance (this is a CALIBRATION relabel, distinct from
    production-bug regressions).

    Test asserts: (a) the regression tier exists with exactly 6 rows,
    (b) the 5 affirmation variants moved from confirm_identity to
    casual_conversation, (c) the 'Actually I'm Jagan, not Javan' row moved
    from assign_own_name to deny_identity with expected_value='Jagan'.
    Guards against a silent revert of the relabel."""
    import json, pathlib
    path = pathlib.Path(__file__).resolve().parent.parent / "tests" / "golden_intent.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    relabels = [r for r in rows if r["source"] == "regression_session_82_relabel"]
    assert len(relabels) == 6, (
        f"Session 83 relabel tier must have exactly 6 rows (5 affirmations + "
        f"1 correction); found {len(relabels)}"
    )
    affirmations = {"Yeah that's right", "Yes you're right", "That's correct",
                    "You got it", "Yep, you got it"}
    for r in relabels:
        ut = r["user_text"]
        if ut in affirmations:
            assert r["expected_intent"] == "casual_conversation", (
                f"affirmation {ut!r} must be relabeled to casual_conversation, "
                f"got {r['expected_intent']}"
            )
            assert r["expected_value"] is None
        elif ut == "Actually I'm Jagan, not Javan":
            assert r["expected_intent"] == "deny_identity", (
                f"'Actually I'm Jagan, not Javan' must be relabeled to "
                f"deny_identity; got {r['expected_intent']}"
            )
            assert r["expected_value"] == "Jagan", (
                f"deny_identity row should carry expected_value='Jagan' "
                f"(the correction target); got {r['expected_value']!r}"
            )
        else:
            raise AssertionError(
                f"unexpected user_text in relabel tier: {ut!r}. "
                f"Either update this test or investigate the new row."
            )
