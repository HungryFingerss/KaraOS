"""test_pipeline_identity_tools — identity tools tests (split from test_pipeline.py, P1.A1 SP-1).

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


async def test_update_system_name_rejected_when_user_did_not_assign():
    """Bug S: LLM called update_system_name('Kara') after user asked 'Do you
    know Detroit?' — pattern-matched from training data (Kara = Detroit:
    Become Human character) without the user actually assigning a name.
    Server-side gate must reject. Uses best_friend session so privilege gate
    doesn't short-circuit; otherwise the test would pass trivially for the
    wrong reason."""
    import pipeline, time as _t
    from pipeline import _execute_tool
    await pipeline._pipeline_state_store.set_active_system_name("Dog")
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=_t.time())
    result = await _execute_tool(
        "update_system_name", {"name": "Kara"}, "p1", "Jagan", db=None,
        user_text="Do you know the game called Detroit?",
    )
    assert result == "rejected"
    assert pipeline._pipeline_state_store.peek_active_system_name() == "Dog", "name must NOT change on rejected call"


def test_identity_denial_patterns_cover_live_run_evidence():
    """Bug G3 regression guard: every denial shape that could plausibly appear
    from a frustrated user must match. The live-run question 'who are you
    talking to?' was legit (not denial) — must NOT match."""
    import re
    from core.config import IDENTITY_DENIAL_PATTERNS
    denials = [
        "I'm not Jagan",
        "that's not me",
        "you've got the wrong person",
        "you're confusing me with someone",
        "I'm not the person you think I am",
        "stop calling me Jagan",
    ]
    for d in denials:
        hits = [p for p in IDENTITY_DENIAL_PATTERNS if re.search(p, d, re.IGNORECASE)]
        assert hits, f"denial shape NOT matched by any pattern: {d!r}"
    benign = [
        "who are you talking to?",        # the exact live-run trigger
        "I'm not sure what you meant",    # "I'm not" followed by non-name
        "that's not a problem",
    ]
    # "I'm not sure" legitimately starts with the same prefix as "I'm not X"
    # — acceptable false-positive class if X=sure is treated as a name denial,
    # but "who are you talking to?" MUST remain benign.
    assert not any(
        re.search(p, "who are you talking to?", re.IGNORECASE)
        for p in IDENTITY_DENIAL_PATTERNS
    ), "the exact live-run benign question must not match any denial pattern"


async def test_update_system_name_accepted_when_name_in_turn():
    """Bug S: literal name in user turn satisfies the gate."""
    import pipeline
    import time as _t
    from pipeline import _execute_tool
    await pipeline._pipeline_state_store.set_active_system_name("Dog")
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=_t.time())
    result = await _execute_tool(
        "update_system_name", {"name": "Kara"}, "p1", "Jagan", db=None,
        user_text="I want to name you Kara.",
    )
    assert result == "handled"
    assert pipeline._pipeline_state_store.peek_active_system_name() == "Kara"


async def test_update_system_name_accepted_on_assign_intent_phrase():
    """Bug S: assignment-intent phrase with the name NOT literal-matched
    elsewhere still satisfies the gate (name can be new; the intent phrase
    is what matters). E.g. 'from now on you're X'."""
    import pipeline
    import time as _t
    from pipeline import _execute_tool
    await pipeline._pipeline_state_store.set_active_system_name("Dog")
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=_t.time())
    result = await _execute_tool(
        "update_system_name", {"name": "Kara"}, "p1", "Jagan", db=None,
        user_text="from now on you're Kara okay?",
    )
    assert result == "handled"


async def test_update_person_name_rejected_when_user_did_not_self_identify():
    """Bug S-parallel: LLM could fire update_person_name from context
    inference; server-side gate must require user to have literally said the
    name OR used a self-ID phrase. Uses stranger session — this is the main
    path where rename is a legitimate promotion (stranger → known)."""
    import pipeline
    from pipeline import _execute_tool
    await pipeline._session_store.open_session("stranger_x", "visitor", "stranger", "face", now=__import__("time").time())
    result = await _execute_tool(
        "update_person_name", {"name": "Sarah"}, "stranger_x", "visitor", db=None,
        user_text="okay, that's fine",
    )
    assert result == "rejected"


async def test_update_person_name_accepted_when_self_identifies():
    """Bug S-parallel: 'my name is Sarah' satisfies the gate."""
    import pipeline
    from pipeline import _execute_tool
    await pipeline._session_store.open_session("stranger_x", "visitor", "stranger", "face", now=__import__("time").time())
    # db=None so the rename doesn't hit real DB; we just verify gate passes.
    result = await _execute_tool(
        "update_person_name", {"name": "Sarah"}, "stranger_x", "visitor", db=None,
        user_text="my name is Sarah, by the way.",
    )
    assert result == "handled", (
        f"gate must accept a self-ID phrase; got {result!r}"
    )


async def test_update_system_name_rejected_on_detroit_cameo():
    """Bug G1: reproduces the exact 2026-04-22 live run failure. User said
    'do you know the GAME called Detroit?' — system renamed to 'Detroit'.
    Must now return 'rejected' via the capture-group gate."""
    import pipeline
    from pipeline import _execute_tool
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    await pipeline._pipeline_state_store.set_active_system_name("Dog")
    result = await _execute_tool(
        "update_system_name", {"name": "Detroit"}, "p1", "Jagan", db=None,
        user_text="Yeah, do you know the name called Detroit? I'm playing it",
    )
    assert result == "rejected", (
        f"Detroit rename must be blocked by capture-group gate, got {result!r}"
    )
    assert pipeline._pipeline_state_store.peek_active_system_name() == "Dog", (
        "system name must NOT change when gate rejects"
    )


async def test_update_system_name_rejected_on_empty_user_text_by_default():
    """Option A (Session 73): proactive/KAIROS-triggered rename with no user
    utterance must be rejected, not silently allowed."""
    import pipeline
    from pipeline import _execute_tool
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    await pipeline._pipeline_state_store.set_active_system_name("Dog")
    result = await _execute_tool(
        "update_system_name", {"name": "Kara"}, "p1", "Jagan", db=None,
        user_text="",
    )
    assert result == "rejected"


async def test_report_identity_mismatch_rejected_on_benign_question():
    """Bug G3: the exact live-run trigger. User asked 'who are you talking to?'
    (legit multi-person-scene question), LLM called report_identity_mismatch
    → session flipped DISPUTED → 15 broken turns. Gate must reject."""
    import pipeline
    from pipeline import _execute_tool
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    result = await _execute_tool(
        "report_identity_mismatch", {"reason": "speaker asks who they are talking to"},
        "p1", "Jagan", db=None,
        user_text="Hey, who are you talking to?",
    )
    assert result == "rejected", (
        "legit multi-person-scene question must NOT trigger dispute"
    )
    snap = pipeline._session_store.peek_snapshot("p1")
    assert snap.person_type == "best_friend", (
        "session must stay best_friend — NOT flip to disputed"
    )


def test_update_person_name_tool_description_includes_stranger_promotion_trigger():
    """Session 97 Fix 1: the 2026-04-22 canary had Lexi say "my name is
    Lexi by the way" at turn ~41 and the brain replied "Nice to meet you,
    Lexi" WITHOUT calling update_person_name — so the stranger session
    stayed anonymous and her extracted facts orphaned into a dangling
    shadow node. The fix tightens the tool description with explicit
    language naming stranger-session name reveals as promotion triggers,
    plus verbatim counter-examples of the exact phrasing shapes ("my
    name is X", "my name is X by the way", "I'm X", "call me X")."""
    from core.brain import TOOLS
    desc = next(
        t["function"]["description"] for t in TOOLS
        if t["function"]["name"] == "update_person_name"
    )
    # Explicit promotion language — abstract rules drift, this phrasing sticks.
    assert "STRANGER PROMOTION" in desc or "stranger" in desc.lower(), (
        "Tool description must name the stranger-promotion path explicitly"
    )
    # Imperative — not optional.
    assert "MUST call" in desc or "must call" in desc.lower(), (
        "Description must use an imperative ('MUST call') so the LLM "
        "doesn't treat promotion as a nice-to-have"
    )
    # The exact phrasing that misfired in the canary.
    assert "my name is X by the way" in desc.lower() or (
        "by the way" in desc.lower() and "my name" in desc.lower()
    ), (
        "Description must include the 'my name is X by the way' shape — "
        "it's the exact form that the canary's Lexi reveal used and the "
        "one the LLM misread as casual sharing"
    )
    # Explicit "don't just acknowledge" directive.
    assert (
        "just acknowledge" in desc.lower()
        or "conversationally" in desc.lower()
    ), (
        "Description must explicitly forbid 'just acknowledging "
        "conversationally' without calling the tool — that's what the "
        "brain did in the canary"
    )


def test_report_identity_mismatch_description_hardens_against_prior_activity_queries():
    """Session 98 Bug B: the 2026-04-23 canary had the brain call
    `report_identity_mismatch` TWICE on Jagan's "who were you talking to?"
    questions — Session 96's tightening caught it at the classifier gate,
    but the Ollama fallback then confabulated. Reviewer: harden the tool
    description with explicit "who were you talking to" counter-examples
    AND an explicit TRIGGER CHECKLIST so the LLM has a structured test."""
    from core.brain import TOOLS
    desc = next(
        t["function"]["description"] for t in TOOLS
        if t["function"]["name"] == "report_identity_mismatch"
    )
    # Canary's exact question shapes are now named as DO-NOT-call cases.
    assert "who were you talking to when i was away" in desc.lower(), (
        "Canary's exact 'who were you talking to when I was away' shape "
        "must appear as a counter-example"
    )
    assert "who is that person" in desc.lower(), (
        "'Who is that person?' (the 2026-04-23 follow-up) must also be "
        "listed as NOT a mismatch trigger"
    )
    # Structured TRIGGER CHECKLIST with numbered items.
    assert "TRIGGER CHECKLIST" in desc, (
        "Must name a TRIGGER CHECKLIST — the ordered criteria give the "
        "LLM something to match against instead of gut-feeling"
    )
    # Question-phrasing shortcut.
    assert "questions are not" in desc.lower() or (
        "contains 'who', 'what'" in desc.lower() and "not" in desc.lower()
    ), (
        "Must include the question-phrasing shortcut — if the user's "
        "utterance contains question words, it's almost certainly not a "
        "denial"
    )


@pytest.mark.privacy_critical
def test_search_memory_description_covers_cross_person_recall():
    """Session 98 Bug B: complementary positive framing — the tool that
    SHOULD be called for 'who were you talking to?' must explicitly
    claim that query shape as its territory, so the LLM doesn't treat
    it as out-of-scope and fall through to the wrong tool."""
    from core.brain import TOOLS
    desc = next(
        t["function"]["description"] for t in TOOLS
        if t["function"]["name"] == "search_memory"
    )
    assert "cross-person" in desc.lower() or "someone else's prior activity" in desc.lower(), (
        "search_memory must advertise cross-person recall as a valid use "
        "case — otherwise the LLM defaults to report_identity_mismatch"
    )
    assert "who were you talking to" in desc.lower(), (
        "Must include the exact question shape as a concrete trigger"
    )
    assert "NEVER route them to" in desc or "never route" in desc.lower(), (
        "Must explicitly forbid routing these to report_identity_mismatch"
    )


def test_report_identity_mismatch_tool_description_tightened():
    """Session 96 Bug 1: the 2026-04-22 canary had the LLM call
    `report_identity_mismatch` in response to Jagan asking 'who were you
    talking to when I was away?' — a cross-person query, not a self-
    denial. The tool description was over-broad; reviewer's fix
    tightens it with explicit scope ("ONLY when speaker denies being
    themselves") and named counter-examples so the LLM has concrete
    negative anchors for the common question shapes. Source-inspection
    guards the specific phrases so a future edit that softens them
    breaks this test before it breaks production."""
    from core.brain import TOOLS
    desc = next(
        t["function"]["description"] for t in TOOLS
        if t["function"]["name"] == "report_identity_mismatch"
    )
    # Scope narrowing: the "ONLY" qualifier must be present.
    assert "ONLY" in desc, (
        "Tool description must lead with 'ONLY' to scope the tool's "
        "use to a single case — the canary's misroute happened because "
        "the old description was permissive"
    )
    # Concrete negative counter-examples for the question shapes the
    # LLM actually misrouted on. These are the teeth.
    assert "Who were you talking to" in desc or "who were you talking to" in desc.lower(), (
        "Must include the canary's exact question shape as a "
        "counter-example — abstract rules drift, concrete examples stick"
    )
    assert "search_memory" in desc, (
        "Must name search_memory as the CORRECT tool for cross-person "
        "queries so the LLM has a redirect target, not just a prohibition"
    )
    # Named exclusions — the LLM must know these aren't triggers.
    assert "DO NOT" in desc or "Do NOT" in desc, (
        "Must use an explicit DO NOT directive block — tool descriptions "
        "without negative framing leave edge cases ambiguous"
    )


async def test_report_identity_mismatch_accepted_on_explicit_denial():
    """Bug G3: 'I'm not Jagan, I told you' is a clear denial signal.
    Dispute must fire — protects known identities from impersonation."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    await pipeline._session_store.open_session("p1", "Jagan", "known", "face", now=_t.time())
    result = await _execute_tool(
        "report_identity_mismatch", {"reason": "speaker denies being Jagan"},
        "p1", "Jagan", db=None,
        user_text="No, I'm not Jagan, you've got the wrong person.",
    )
    await asyncio.sleep(0)
    assert result == "handled"
    _snap = pipeline._session_store.peek_snapshot("p1")
    assert _snap is not None and _snap.person_type == "disputed"
    # Session 73: prior_person_type must be captured for auto-clear restore.
    assert _snap.prior_person_type == "known"


def test_report_identity_mismatch_preserves_prior_person_type_for_best_friend():
    """Bug D1 (dispute auto-clear prep): when best_friend flips to disputed,
    prior_person_type must record 'best_friend' so auto-clear can restore the
    owner role, not demote to generic 'known'. After P0.7.3 migration,
    prior_person_type capture is done atomically inside
    transition_to_disputed() in SessionStore — not inline in the pipeline
    branch. Verify the branch calls transition_to_disputed (which guarantees
    prior_person_type is captured at the SessionStore layer)."""
    # P0.8: report_identity_mismatch logic was extracted to
    # _handle_report_identity_mismatch (mechanical handler extraction).
    # The branch in _execute_tool is now a delegation line; inspect the
    # extracted handler instead.
    import inspect, pipeline
    src = inspect.getsource(pipeline._handle_report_identity_mismatch)
    assert "transition_to_disputed" in src, (
        "_handle_report_identity_mismatch must call transition_to_disputed() "
        "which atomically captures prior_person_type so auto-clear can "
        "restore best_friend vs known correctly"
    )


def test_auto_confirm_gated_on_user_self_identification():
    """Bug G4 (Session 73) + Session 86 P1.7b: auto-confirm promotion (score
    ≥ IDENTITY_AUTO_THRESHOLD) must ALSO gate on user self-ID in current turn.
    Without this, a stranger whose conversation pattern-matches a known member
    could be auto-promoted to that identity — knowledge graph attack. After
    P1.7b the gate is classifier-first with regex fallback, so the source
    must contain BOTH _intent_allows (classifier branch) AND
    _user_text_gate_passes (regex fallback branch) — either path must
    enforce the grounding requirement."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    # Find the auto-confirm branch specifically. Bigger window after P1.7b
    # because the 3-branch decision takes ~60 lines.
    idx = src.find("IDENTITY_AUTO_THRESHOLD")
    assert idx > -1
    branch = src[idx:idx + 4000]
    assert "_intent_allows" in branch, (
        "P1.7b: auto-confirm classifier branch must call _intent_allows"
    )
    assert "_user_text_gate_passes" in branch, (
        "P1.7b: auto-confirm regex-fallback branch must still route through "
        "the shared gate primitive for classifier-unavailable cases"
    )
    assert "PERSON_NAME_ASSIGN_PATTERNS" in branch, (
        "regex fallback must use the self-ID pattern table (not SYSTEM_NAME_ASSIGN_PATTERNS)"
    )
    assert "Auto-confirm HELD" in branch, (
        "gate rejection must log a distinct diagnostic — operators need to see "
        "how often the auto-confirm scorer would have fired without user grounding"
    )


def test_update_system_name_description_forbids_redundant_calls():
    """Bug Q Layer: the tool description itself tells the LLM not to call
    with the current name. Alignment with the handler's 'handled_noop'
    behavior — belt-and-suspenders."""
    from core import brain
    usn_entry = next(t for t in brain.TOOLS if t["function"]["name"] == "update_system_name")
    desc = usn_entry["function"]["description"]
    assert "ALREADY have" in desc or "already have" in desc, (
        "update_system_name description must forbid calling with the current name"
    )


async def test_promotion_clears_waiting_for_name():
    """_execute_tool update_person_name promotion clears waiting_for_name from session."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t

    import time as _t2
    await pipeline._session_store.open_session("stranger_003", "visitor", "stranger", "face", now=_t2.time())
    await pipeline._session_store.set_waiting_for_name("stranger_003", True)
    await pipeline._conversation_store.set_history("stranger_003", [])

    mock_db = MagicMock()
    mock_brain = MagicMock()
    pipeline._brain_orchestrator = mock_brain

    await _execute_tool(
        "update_person_name", {"name": "Ajay"},
        "stranger_003", "visitor", db=mock_db,
        user_text="my name is Ajay",
    )
    # Yield so create_task'd coroutines (promote_type, set_waiting_for_name,
    # set_cached_prefix) scheduled via asyncio.get_running_loop() run.
    await asyncio.sleep(0)

    _snap = pipeline._session_store.peek_snapshot("stranger_003")
    assert _snap is not None and not _snap.waiting_for_name  # cleared by set_waiting_for_name
    # person_type promotion goes through _session_store.promote_type (async task)
    # and db.update_person_type; verify the DB write happened.
    mock_db.update_person_type.assert_called_once_with("stranger_003", "known")

    pipeline._brain_orchestrator = None


async def test_auto_confirm_promotion_runs_full_chain():
    """confidence >= IDENTITY_AUTO_THRESHOLD → db updated + on_identity_confirmed called."""
    import pipeline
    from pipeline import conversation_turn, CloudState
    import time as _t

    # ── Global state setup ─────────────────────────────────────────────────────
    orig_cloud_state    = pipeline._pipeline_state_store.peek_cloud_state()
    orig_brain_orch     = pipeline._brain_orchestrator
    orig_detected_lang  = pipeline._pipeline_state_store.peek_detected_lang()
    orig_system_name    = pipeline._pipeline_state_store.peek_active_system_name()

    await pipeline._conversation_store.set_history("stranger_001", [])
    await pipeline._pipeline_state_store.recover_online_no_flag()
    pipeline._per_person_agent_store.reset()
    await pipeline._pipeline_state_store.set_detected_lang("en")
    await pipeline._pipeline_state_store.set_active_system_name("Rex")

    # ── Mocks ─────────────────────────────────────────────────────────────────
    mock_brain = MagicMock()
    mock_brain.score_stranger_identity.return_value = {
        "name": "Priya",
        "confidence": 0.90,       # ≥ IDENTITY_AUTO_THRESHOLD (0.85)
        "matched_attrs": ["works_at"],
        "relationship": "colleague",
    }
    mock_brain.on_identity_confirmed = MagicMock()
    mock_brain.notify                = MagicMock()
    pipeline._brain_orchestrator = mock_brain

    mock_db = MagicMock()
    mock_db.log_turn = MagicMock()
    mock_db.update_person_name = MagicMock()
    mock_db.update_person_type = MagicMock()

    import time as _t2
    await pipeline._session_store.open_session("stranger_001", "visitor", "stranger", "face", now=_t2.time())

    async def fake_ask_stream(*args, **kwargs):
        yield ("text", "Hello Priya!")

    async def fake_speak_stream(sentences, **kw):
        async for _ in sentences:
            pass

    try:
        with patch("pipeline.ask_stream",   new=fake_ask_stream), \
             patch("pipeline.speak_stream", new=fake_speak_stream), \
             patch("pipeline._set_state"), \
             patch("pipeline.play_filler"):
            # Session 73 Bug G4: auto-confirm now requires user self-ID AND
            # score ≥ threshold. User's current turn must contain a name-assign
            # pattern capturing the proposed name ("Priya").
            result = await conversation_turn(
                "Hi, my name is Priya, I work at Google with Jagan",
                "stranger_001",
                "visitor",
                db=mock_db,
            )

        # ── Assertions ────────────────────────────────────────────────────────
        assert result == ("continue", None)

        mock_db.update_person_name.assert_called_once_with("stranger_001", "Priya")
        mock_db.update_person_type.assert_called_once_with("stranger_001", "known")
        mock_brain.on_identity_confirmed.assert_called_once_with(
            "stranger_001", "visitor", "Priya"
        )

        # waiting_for_name must be False after auto-confirm promotion
        _snap = pipeline._session_store.peek_snapshot("stranger_001")
        assert _snap is None or not _snap.waiting_for_name

        # identity_hints entry should be cleared after auto-confirm
        assert pipeline._identity_hints_store.peek("stranger_001") is None

    finally:
        # ── Restore globals ───────────────────────────────────────────────────
        await pipeline._pipeline_state_store.set_cloud_state(orig_cloud_state)
        pipeline._brain_orchestrator    = orig_brain_orch
        await pipeline._pipeline_state_store.set_detected_lang(orig_detected_lang)
        await pipeline._pipeline_state_store.set_active_system_name(orig_system_name)


async def test_history_override_update_system_name():
    """L1: Wrong LLM text alongside update_system_name must not appear in history."""
    import pipeline
    from pipeline import CloudState
    from unittest.mock import patch, AsyncMock

    await pipeline._session_store.open_session("p1", "Jagan", "known", "face", now=__import__("time").time())
    await pipeline._conversation_store.set_history("p1", [])
    await pipeline._pipeline_state_store.set_active_system_name("Kara")
    await pipeline._pipeline_state_store.recover_online_no_flag()

    async def fake_stream(*a, **kw):
        yield ("text", "Sorry, I missed that.")
        yield ("tool_calls", [{"name": "update_system_name", "args": {"name": "Kara"}}])

    async def fake_speak(sentences, **kw):
        async for _ in sentences:
            pass

    with patch("pipeline.ask_stream",   new=fake_stream), \
         patch("pipeline.speak_stream", new=fake_speak), \
         patch("pipeline.speak",        new=AsyncMock()), \
         patch("pipeline._set_state"), \
         patch("pipeline._execute_tool", new=AsyncMock(return_value="handled")), \
         patch("pipeline._brain_orchestrator", None), \
         patch("pipeline.autocompact_history",
               new=AsyncMock(side_effect=lambda h, *a, **kw: h)):
        await pipeline.conversation_turn("call yourself Kara", "p1", "Jagan", db=None)

    history   = pipeline._conversation_store.peek_history("p1")
    asst_msgs = [m for m in history if m["role"] == "assistant"]
    assert len(asst_msgs) == 1
    assert asst_msgs[0]["content"] == "Got it, I'll go by Kara."
    assert "Sorry" not in asst_msgs[0]["content"]


async def test_history_override_update_person_name():
    """L1: Wrong LLM text alongside update_person_name must not appear in history."""
    import pipeline
    from pipeline import CloudState
    from unittest.mock import patch, AsyncMock

    await pipeline._session_store.open_session("p1", "Jay", "known", "face", now=__import__("time").time())
    await pipeline._conversation_store.set_history("p1", [])
    await pipeline._pipeline_state_store.set_active_system_name("Rex")
    await pipeline._pipeline_state_store.recover_online_no_flag()

    async def fake_stream(*a, **kw):
        yield ("text", "No problem at all.")
        yield ("tool_calls", [{"name": "update_person_name", "args": {"name": "Jay"}}])

    async def fake_speak(sentences, **kw):
        async for _ in sentences:
            pass

    with patch("pipeline.ask_stream",   new=fake_stream), \
         patch("pipeline.speak_stream", new=fake_speak), \
         patch("pipeline.speak",        new=AsyncMock()), \
         patch("pipeline._set_state"), \
         patch("pipeline._execute_tool", new=AsyncMock(return_value="handled")), \
         patch("pipeline._brain_orchestrator", None), \
         patch("pipeline.autocompact_history",
               new=AsyncMock(side_effect=lambda h, *a, **kw: h)):
        await pipeline.conversation_turn("my name is Jay", "p1", "Jay", db=None)

    history   = pipeline._conversation_store.peek_history("p1")
    asst_msgs = [m for m in history if m["role"] == "assistant"]
    assert len(asst_msgs) == 1
    assert asst_msgs[0]["content"] == "Got it, Jay."
    assert "No problem" not in asst_msgs[0]["content"]


async def test_history_override_not_fired_for_set_language():
    """L1: set_language is not in HISTORY_OVERRIDE_TOOLS — LLM text kept in history."""
    import pipeline
    from pipeline import CloudState
    from unittest.mock import patch, AsyncMock

    await pipeline._session_store.open_session("p1", "Jagan", "known", "face", now=__import__("time").time())
    await pipeline._conversation_store.set_history("p1", [])
    await pipeline._pipeline_state_store.set_active_system_name("Rex")
    await pipeline._pipeline_state_store.recover_online_no_flag()

    async def fake_stream(*a, **kw):
        yield ("text", "I remember you mentioning that.")
        yield ("tool_calls", [{"name": "set_language", "args": {"language": "en"}}])

    async def fake_speak(sentences, **kw):
        async for _ in sentences:
            pass

    with patch("pipeline.ask_stream",   new=fake_stream), \
         patch("pipeline.speak_stream", new=fake_speak), \
         patch("pipeline._set_state"), \
         patch("pipeline._execute_tool", new=AsyncMock(return_value="handled")), \
         patch("pipeline._brain_orchestrator", None), \
         patch("pipeline.autocompact_history",
               new=AsyncMock(side_effect=lambda h, *a, **kw: h)):
        await pipeline.conversation_turn(
            "what do you know about me", "p1", "Jagan", db=None
        )

    history   = pipeline._conversation_store.peek_history("p1")
    asst_msgs = [m for m in history if m["role"] == "assistant"]
    assert len(asst_msgs) == 1
    # set_language not in HISTORY_OVERRIDE_TOOLS → original LLM text preserved
    assert asst_msgs[0]["content"] == "I remember you mentioning that."


async def test_layer4_stop_audio_called_for_action_tool():
    """L4: stop_audio() is called when an action tool arrives in _token_gen."""
    import time
    import pipeline
    from pipeline import CloudState
    from unittest.mock import patch, AsyncMock, MagicMock

    await pipeline._session_store.open_session("p1", "Jagan", "known", "face", now=time.time())
    await pipeline._conversation_store.set_history("p1", [])
    await pipeline._pipeline_state_store.set_active_system_name("Rex")
    await pipeline._pipeline_state_store.recover_online_no_flag()

    async def fake_stream(*a, **kw):
        yield ("text", "Wrong text.")
        yield ("tool_calls", [{"name": "update_system_name", "args": {"name": "Rex"}}])

    async def fake_speak(sentences, **kw):
        async for _ in sentences:
            pass

    stop_calls = []

    with patch("pipeline.ask_stream",   new=fake_stream), \
         patch("pipeline.speak_stream", new=fake_speak), \
         patch("pipeline.speak",        new=AsyncMock()), \
         patch("pipeline._set_state"), \
         patch("pipeline._execute_tool", new=AsyncMock(return_value="handled")), \
         patch("pipeline._brain_orchestrator", None), \
         patch("pipeline.autocompact_history",
               new=AsyncMock(side_effect=lambda h, *a, **kw: h)), \
         patch("pipeline.stop_audio", side_effect=lambda: stop_calls.append(1)) as mock_stop:
        await pipeline.conversation_turn("call yourself Rex", "p1", "Jagan", db=None)

    assert mock_stop.called, "stop_audio() must be called for action tool"


async def test_layer4_stop_audio_not_called_for_non_action_tool():
    """L4: stop_audio() is NOT called for set_language (not in HISTORY_OVERRIDE_TOOLS)."""
    import pipeline
    from pipeline import CloudState
    from unittest.mock import patch, AsyncMock

    await pipeline._session_store.open_session("p1", "Jagan", "known", "face", now=__import__("time").time())
    await pipeline._conversation_store.set_history("p1", [])
    await pipeline._pipeline_state_store.set_active_system_name("Rex")
    await pipeline._pipeline_state_store.recover_online_no_flag()

    async def fake_stream(*a, **kw):
        yield ("text", "Switching language.")
        yield ("tool_calls", [{"name": "set_language", "args": {"language": "en"}}])

    async def fake_speak(sentences, **kw):
        async for _ in sentences:
            pass

    with patch("pipeline.ask_stream",   new=fake_stream), \
         patch("pipeline.speak_stream", new=fake_speak), \
         patch("pipeline._set_state"), \
         patch("pipeline._execute_tool", new=AsyncMock(return_value="handled")), \
         patch("pipeline._brain_orchestrator", None), \
         patch("pipeline.autocompact_history",
               new=AsyncMock(side_effect=lambda h, *a, **kw: h)), \
         patch("pipeline.stop_audio") as mock_stop:
        await pipeline.conversation_turn("switch to english", "p1", "Jagan", db=None)

    mock_stop.assert_not_called()


async def test_layer4_stop_audio_not_called_when_no_tool_calls():
    """L4: stop_audio() is NOT called when the response has no tool calls at all."""
    import pipeline
    from pipeline import CloudState
    from unittest.mock import patch, AsyncMock

    await pipeline._session_store.open_session("p1", "Jagan", "known", "face", now=__import__("time").time())
    await pipeline._conversation_store.set_history("p1", [])
    await pipeline._pipeline_state_store.set_active_system_name("Rex")
    await pipeline._pipeline_state_store.recover_online_no_flag()

    async def fake_stream(*a, **kw):
        yield ("text", "That sounds great!")

    async def fake_speak(sentences, **kw):
        async for _ in sentences:
            pass

    with patch("pipeline.ask_stream",   new=fake_stream), \
         patch("pipeline.speak_stream", new=fake_speak), \
         patch("pipeline._set_state"), \
         patch("pipeline._brain_orchestrator", None), \
         patch("pipeline.autocompact_history",
               new=AsyncMock(side_effect=lambda h, *a, **kw: h)), \
         patch("pipeline.stop_audio") as mock_stop:
        await pipeline.conversation_turn("how are you", "p1", "Jagan", db=None)

    mock_stop.assert_not_called()


async def test_auto_confirm_retroactively_fixes_history():
    """B4: auto-confirm path replaces old name in in-memory history just like tool path."""
    import pipeline
    from pipeline import conversation_turn, CloudState
    import time as _t

    orig_cloud_state    = pipeline._pipeline_state_store.peek_cloud_state()
    orig_brain_orch     = pipeline._brain_orchestrator
    orig_detected_lang  = pipeline._pipeline_state_store.peek_detected_lang()
    orig_system_name    = pipeline._pipeline_state_store.peek_active_system_name()

    await pipeline._conversation_store.set_history("stranger_x", [
        {"role": "user",      "content": "visitor said hello"},
        {"role": "assistant", "content": "Nice to meet you, visitor!"},
    ])
    await pipeline._pipeline_state_store.recover_online_no_flag()
    pipeline._per_person_agent_store.reset()
    await pipeline._pipeline_state_store.set_detected_lang("en")
    await pipeline._pipeline_state_store.set_active_system_name("Rex")

    mock_brain = MagicMock()
    mock_brain.score_stranger_identity.return_value = {
        "name": "Priya",
        "confidence": 0.90,
        "matched_attrs": ["works_at"],
        "relationship": "colleague",
    }
    mock_brain.on_identity_confirmed = MagicMock()
    mock_brain.notify                = MagicMock()
    pipeline._brain_orchestrator = mock_brain

    mock_db = MagicMock()
    mock_db.log_turn           = MagicMock()
    mock_db.update_person_name = MagicMock()
    mock_db.update_person_type = MagicMock()

    import time as _t2
    await pipeline._session_store.open_session("stranger_x", "visitor", "stranger", "face", now=_t2.time())

    async def fake_ask_stream(*a, **kw):
        yield ("text", "Hello!")

    async def fake_speak_stream(sentences, **kw):
        async for _ in sentences:
            pass

    try:
        with patch("pipeline.ask_stream",   new=fake_ask_stream), \
             patch("pipeline.speak_stream", new=fake_speak_stream), \
             patch("pipeline._set_state"), \
             patch("pipeline.play_filler"):
            # Session 73 Bug G4: user_text needs self-ID for auto-confirm to fire.
            await conversation_turn("my name is Priya", "stranger_x", "visitor", db=mock_db)

        history = pipeline._conversation_store.peek_history("stranger_x")
        for msg in history:
            assert "visitor" not in msg["content"].lower(), (
                f"Old name 'visitor' still present in: {msg['content']!r}"
            )
        combined = " ".join(m["content"] for m in history)
        assert "priya" in combined.lower()

    finally:
        await pipeline._pipeline_state_store.set_cloud_state(orig_cloud_state)
        pipeline._brain_orchestrator    = orig_brain_orch
        await pipeline._pipeline_state_store.set_detected_lang(orig_detected_lang)
        await pipeline._pipeline_state_store.set_active_system_name(orig_system_name)


async def test_update_person_name_on_known_session_flips_to_disputed():
    """When a known-session rename happens on a MATURE session (past the
    Session 100 Bug F enrollment-mishear grace window OR with voice
    samples accumulated), DB must NOT be renamed — session flips to
    'disputed' and extraction is expected to pause. This protects the
    known person's identity from getting corrupted when the sensor was
    wrong mid-session. The enrollment-mishear escape hatch ONLY applies
    to fresh-enrollment sessions with no voice corroboration; this test
    pins the dispute path by using an old started_at."""
    import asyncio, pipeline
    from pipeline import _execute_tool
    import time as _t
    from core.config import ENROLLMENT_RENAME_GRACE_SECS
    pid = "jagan_001"
    await pipeline._session_store.open_session(
        pid, "Jagan", "known", "face",
        now=_t.time() - (ENROLLMENT_RENAME_GRACE_SECS + 60),
    )
    await pipeline._conversation_store.set_history(pid, [])
    mock_db = MagicMock()
    mock_db.voice_embedding_count.return_value = 20
    await _execute_tool(
        "update_person_name", {"name": "Venkat"},
        pid, "Jagan", db=mock_db,
        user_text="my name is Venkat",
    )
    mock_db.update_person_name.assert_not_called()
    await asyncio.sleep(0)
    snap = pipeline._session_store.peek_snapshot(pid)
    assert snap.person_type == "disputed"
    assert snap.disputed_claimed_name == "Venkat"
    assert snap.dispute_reason is not None


async def test_update_person_name_on_disputed_session_blocks_db_rename():
    """Finding G — CRITICAL: when update_person_name fires on a DISPUTED session, the
    DB row for the sensor-matched pid must NOT be renamed. The disputed pid belongs
    to a DIFFERENT person (the sensor-matched one); renaming them would permanently
    corrupt their identity record. The dispute stays active — force-closes via
    DISPUTE_MAX_DURATION; the user can factory-reset to clean the poisoned gallery.
    """
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    _now = _t.time()
    await pipeline._session_store.open_session(
        "jagan_001", "Jagan", "known", "face", now=_now,
    )
    await pipeline._session_store.transition_to_disputed(
        "jagan_001", "Venkat", "speaker claims not Jagan", now=_now,
    )
    await pipeline._conversation_store.set_history("jagan_001", [
        {"role": "user",      "content": "I am not Jagan, I am Venkat"},
        {"role": "assistant", "content": "I hear you, Jagan — let me sort this out."},
    ])
    mock_db = MagicMock()
    await _execute_tool(
        "update_person_name", {"name": "Venkat"},
        "jagan_001", "Jagan", db=mock_db,
        user_text="my name is Venkat",
    )
    # CRITICAL: the real Jagan's row must NOT have been renamed.
    mock_db.update_person_name.assert_not_called()
    mock_db.update_person_type.assert_not_called()
    # Session's person_name must NOT have been changed — still "Jagan".
    snap = pipeline._session_store.peek_snapshot("jagan_001")
    assert snap is not None
    assert snap.person_name == "Jagan"
    # Dispute must remain active so the timeout / session-end can close it cleanly.
    assert snap.person_type == "disputed"
    # In-memory history must NOT have been rewritten (stranger's turns are
    # still theirs; rewriting would confuse future debugging).
    msgs = pipeline._conversation_store.peek_history("jagan_001")
    assert msgs[1]["content"] == "I hear you, Jagan — let me sort this out."


async def test_update_person_name_on_best_friend_session_flips_to_disputed():
    """Finding L — CRITICAL: a rename on a best_friend session must flip to disputed,
    not corrupt the DB row. best_friend is the system owner — a mis-rename there
    would transfer owner privileges to the attacker. Same class of bug as Finding G
    but for a different session type.

    Session 100 Bug F adds an escape hatch for fresh enrollments (face only,
    no voice corroboration) — this test explicitly pins the MATURE-session
    path (past grace window + voice samples) to preserve the security
    invariant that mid-session best_friend renames never touch the DB row."""
    import asyncio
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    from core.config import ENROLLMENT_RENAME_GRACE_SECS
    _started_at = _t.time() - (ENROLLMENT_RENAME_GRACE_SECS + 60)
    # Past grace window so the Bug F escape hatch does NOT fire.
    await pipeline._session_store.open_session(
        "jagan_bf", "Jagan", "best_friend", "face", now=_started_at
    )
    await pipeline._conversation_store.set_history("jagan_bf", [])
    mock_db = MagicMock()
    mock_db.voice_embedding_count.return_value = 20  # mature voice profile

    # Mock the orchestrator so mark_disputed is observable
    orig_orch = pipeline._brain_orchestrator
    mock_orch = MagicMock()
    pipeline._brain_orchestrator = mock_orch
    try:
        await _execute_tool(
            "update_person_name", {"name": "Benkat"},
            "jagan_bf", "Jagan", db=mock_db,
            user_text="my name is Benkat",
        )
        # Drain the event loop so create_task(transition_to_disputed) runs.
        await asyncio.sleep(0)
    finally:
        pipeline._brain_orchestrator = orig_orch

    # CRITICAL: best_friend's DB row must NOT be renamed.
    mock_db.update_person_name.assert_not_called()
    mock_db.update_person_type.assert_not_called()

    # Post-P0.7.4: dispute state lives in _session_store, not _active_sessions dict.
    snap = pipeline._session_store.peek_snapshot("jagan_bf")
    assert snap is not None, "Session must still exist in store after dispute-flip"
    assert snap.person_type == "disputed"
    assert snap.prior_person_type == "best_friend"
    assert snap.disputed_claimed_name == "Benkat"
    assert snap.dispute_set_at is not None
    assert snap.person_name == "Jagan", "person_name must not change on dispute-flip"
    # Orchestrator flagged the pid as disputed so extraction pauses
    mock_orch.mark_disputed.assert_called_once_with("jagan_bf")


async def test_stranger_rename_still_works_after_g_fix():
    """Regression guard: Finding G's fix must NOT break the stranger promotion path —
    stranger_* pids are freshly minted for each stranger, so renaming them in DB
    is the intended promotion."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    import asyncio
    await pipeline._session_store.open_session(
        "stranger_xyz", "visitor", "stranger", "face", now=_t.time()
    )
    await pipeline._conversation_store.set_history("stranger_xyz", [])
    mock_db = MagicMock()
    await _execute_tool(
        "update_person_name", {"name": "Priya"},
        "stranger_xyz", "visitor", db=mock_db,
        user_text="my name is Priya",
    )
    # Stranger path still runs the DB rename + promotion
    mock_db.update_person_name.assert_called_once_with("stranger_xyz", "Priya")
    mock_db.update_person_type.assert_called_once_with("stranger_xyz", "known")
    # Allow async tasks (rename + promote_type) to execute
    await asyncio.sleep(0)
    _snap = pipeline._session_store.peek_snapshot("stranger_xyz")
    assert _snap.person_name == "Priya"
    assert _snap.person_type == "known"


def test_report_identity_mismatch_tool_registered():
    """report_identity_mismatch must be registered in TOOLS."""
    from core.brain import TOOLS
    names = [t["function"]["name"] for t in TOOLS]
    assert "report_identity_mismatch" in names


async def test_report_identity_mismatch_flips_session_to_disputed():
    """Tool handler flips person_type to 'disputed' and stores the reason."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    await pipeline._session_store.open_session(
        "jagan_001", "Jagan", "known", "face", now=_t.time()
    )
    await _execute_tool(
        "report_identity_mismatch", {"reason": "speaker insists they are not Jagan"},
        "jagan_001", "Jagan", db=None,
        user_text="I'm not Jagan",   # Session 73: denial-pattern gate
    )
    await asyncio.sleep(0)
    _snap = pipeline._session_store.peek_snapshot("jagan_001")
    assert _snap is not None and _snap.person_type == "disputed"
    assert "insists" in (_snap.dispute_reason or "")


async def test_mark_disputed_records_timestamp():
    """update_person_name on KNOWN session must set dispute_set_at so the timeout works."""
    import asyncio, pipeline
    from pipeline import _execute_tool
    import time as _t
    pid = "jagan_001"
    await pipeline._session_store.open_session(pid, "Jagan", "known", "face", now=_t.time())
    await pipeline._conversation_store.set_history(pid, [])
    await _execute_tool(
        "update_person_name", {"name": "Venkat"},
        pid, "Jagan", db=None,
        user_text="my name is Venkat",
    )
    await asyncio.sleep(0)
    snap = pipeline._session_store.peek_snapshot(pid)
    assert snap.dispute_set_at is not None
    assert snap.dispute_set_at > 0
