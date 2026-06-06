"""test_pipeline_tool_dispatch — tool dispatch tests (split from test_pipeline.py, P1.A1 SP-1).

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


async def test_execute_tool_shutdown_returns_signal():
    """Shutdown tool returns 'shutdown' signal when the user's text contains
    an explicit shutdown command. Session 86 P1.7b: regex fallback path
    (classifier unavail since intent_sidecar not provided) decides. Empty
    user_text no longer auto-passes — the Session 86 shutdown gate is
    stricter than Session 28's."""
    import pipeline
    from pipeline import _execute_tool
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    result = await _execute_tool("shutdown", {}, "p1", "Jagan", db=None,
                                  user_text="shut down")
    assert result == "shutdown"


async def test_execute_tool_shutdown_with_explicit_phrase():
    """Shutdown proceeds when conversation contains an explicit shutdown phrase."""
    import pipeline
    from pipeline import _execute_tool
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    result = await _execute_tool("shutdown", {}, "p1", "Jagan", db=None,
                                  user_text="please shut down")
    assert result == "shutdown"


async def test_execute_tool_shutdown_rejected_on_mention():
    """Shutdown is rejected when the user merely mentions 'shutdown' in a question.
    Session 71 (unified 'rejected'): return value is now 'rejected' (was None)
    so the caller can route it through the Ollama-text retry alongside other
    user-text gate rejections (Bugs S, T). Requires best_friend session so
    privilege gate (shutdown = best_friend only) doesn't short-circuit to None."""
    import pipeline
    from pipeline import _execute_tool
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    result = await _execute_tool("shutdown", {}, "p1", "Jagan", db=None,
                                  user_text="why did you shut down last time?")
    assert result == "rejected"


async def test_execute_tool_shutdown_rejected_on_unrelated():
    """Shutdown is rejected when the user said something completely unrelated.
    Session 71: 'rejected' status (was None)."""
    import pipeline
    from pipeline import _execute_tool
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    result = await _execute_tool("shutdown", {}, "p1", "Jagan", db=None,
                                  user_text="You are my project that I am developing")
    assert result == "rejected"


async def test_execute_tool_set_language_no_op_when_same():
    import pipeline
    from pipeline import _execute_tool
    await pipeline._pipeline_state_store.set_detected_lang("en")
    await _execute_tool("set_language", {"language": "en"}, "p1", "Jagan", db=None)
    assert pipeline._pipeline_state_store.peek_detected_lang() == "en"


async def test_execute_tool_update_person_name_calls_db():
    """Rename on a stranger session flows through the legitimate rename path."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    await pipeline._session_store.open_session("p1", "OldName", "stranger", "face", now=__import__("time").time())
    await pipeline._conversation_store.set_history("p1", [])
    mock_db = MagicMock()
    await _execute_tool(
        "update_person_name", {"name": "Jagan"},
        "p1", "OldName", db=mock_db,
        user_text="my name is Jagan",
    )
    import asyncio as _asyncio
    await _asyncio.sleep(0)
    mock_db.update_person_name.assert_called_once_with("p1", "Jagan")
    snap = pipeline._session_store.peek_snapshot("p1")
    assert snap is not None and snap.person_name == "Jagan"


async def test_execute_tool_update_person_name_no_op_when_same():
    """No DB call if the new name matches the current name (case-insensitive)."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    await pipeline._session_store.open_session("p1", "Jagan", "known", "face", now=_t.time())
    await pipeline._conversation_store.set_history("p1", [])
    mock_db = MagicMock()
    await _execute_tool(
        "update_person_name", {"name": "jagan"},
        "p1", "Jagan", db=mock_db,
        user_text="my name is jagan",
    )
    mock_db.update_person_name.assert_not_called()


async def test_execute_tool_update_person_name_fixes_history():
    """Old name in in-memory history is replaced with the new name (stranger path)."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    await pipeline._session_store.open_session("p1", "Jaren", "stranger", "face", now=__import__("time").time())
    await pipeline._conversation_store.set_history("p1", [
        {"role": "assistant", "content": "Hello Jaren, how are you?"},
        {"role": "user",      "content": "Good thanks"},
        {"role": "assistant", "content": "Great, Jaren!"},
    ])
    mock_db = MagicMock()
    await _execute_tool(
        "update_person_name", {"name": "Jagan"},
        "p1", "Jaren", db=mock_db,
        user_text="my name is Jagan",
    )
    hist = pipeline._conversation_store.peek_history("p1")
    for msg in hist:
        assert "Jaren" not in msg["content"]
    assert hist[0]["content"] == "Hello Jagan, how are you?"
    assert hist[2]["content"] == "Great, Jagan!"


async def test_execute_tool_update_person_name_promotes_stranger():
    """When person_type is 'stranger', rename triggers db.update_person_type + on_identity_confirmed."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t

    await pipeline._session_store.open_session("stranger_001", "visitor", "stranger", "face", now=__import__("time").time())
    await pipeline._conversation_store.set_history("stranger_001", [])

    mock_db = MagicMock()
    mock_brain = MagicMock()
    _wiring._brain_orchestrator = mock_brain

    await _execute_tool(
        "update_person_name", {"name": "Ajay"},
        "stranger_001", "visitor", db=mock_db,
        user_text="my name is Ajay",
    )
    import asyncio as _asyncio
    await _asyncio.sleep(0)

    mock_db.update_person_name.assert_called_once_with("stranger_001", "Ajay")
    mock_db.update_person_type.assert_called_once_with("stranger_001", "known")
    mock_brain.on_identity_confirmed.assert_called_once_with("stranger_001", "visitor", "Ajay")
    snap = pipeline._session_store.peek_snapshot("stranger_001")
    assert snap is not None and snap.person_type == "known"
    assert snap.person_name == "Ajay"

    _wiring._brain_orchestrator = None


def _mk_divergence_capture_orch():
    """Build a minimal BrainOrchestrator stand-in whose _brain_db captures
    every log_intent_divergence call so tests can assert on the gate decision.
    P1.7a pattern: pipeline._brain_orchestrator._brain_db.log_intent_divergence
    is the write path; we replace the entire chain with MagicMocks so no SQLite
    state is touched at unit-test time."""
    mock_db = MagicMock()
    mock_db.log_intent_divergence = MagicMock(return_value=1)
    mock_orch = MagicMock()
    mock_orch._brain_db = mock_db
    return mock_orch, mock_db


async def test_execute_tool_update_person_name_classifier_allows_fires_tool():
    """P1.7a scenario 1: classifier returns a positive sidecar (intent matches
    + conf ≥ 0.75 + extracted_value grounded) → tool fires, DB called,
    divergence row written with gate_decision='allow'. Matches Session 80
    Turn 21 'I'd love to call you Atlas' shape."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    await pipeline._session_store.open_session("p1", "OldName", "stranger", "face", now=__import__("time").time())
    await pipeline._conversation_store.set_history("p1", [])
    mock_db = MagicMock()
    mock_orch, mock_brain_db = _mk_divergence_capture_orch()
    _prev_orch = pipeline._brain_orchestrator
    _wiring._brain_orchestrator = mock_orch
    try:
        sidecar = {
            "turn_intent":     "assign_own_name",
            "extracted_value": "Jagan",
            "confidence":      0.95,
            "reasoning":       "User directly assigns own name",
        }
        result = await _execute_tool(
            "update_person_name", {"name": "Jagan"},
            "p1", "OldName", db=mock_db,
            user_text="my name is Jagan",
            intent_sidecar=sidecar,
        )
        # Tool fired — DB renamed, session updated, status is not "rejected".
        assert result != "rejected"
        mock_db.update_person_name.assert_called_once_with("p1", "Jagan")
        # Divergence row written with gate_decision='allow'.
        mock_brain_db.log_intent_divergence.assert_called()
        kwargs = mock_brain_db.log_intent_divergence.call_args.kwargs
        assert kwargs["tool_proposed"] == "update_person_name"
        assert kwargs["gate_decision"] == "allow"
        assert kwargs["structured_intent"] == "assign_own_name"
        assert kwargs["structured_confidence"] == pytest.approx(0.95)
    finally:
        _wiring._brain_orchestrator = _prev_orch


async def test_execute_tool_update_person_name_classifier_rejects_blocks_tool():
    """P1.7a scenario 2: classifier returns a sidecar whose confidence is
    below the floor (0.75 general) → _intent_allows rejects, tool does NOT
    fire, status='rejected', divergence row has gate_decision='reject: ...'.
    Matches Session 80 Turn 19: conf=0.20 escape-hatch leak; dual gate
    saves us at the confidence floor."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    await pipeline._session_store.open_session("p1", "OldName", "stranger", "face", now=__import__("time").time())
    await pipeline._conversation_store.set_history("p1", [])
    mock_db = MagicMock()
    mock_orch, mock_brain_db = _mk_divergence_capture_orch()
    _prev_orch = pipeline._brain_orchestrator
    _wiring._brain_orchestrator = mock_orch
    try:
        sidecar = {
            "turn_intent":     "assign_own_name",
            "extracted_value": None,
            "confidence":      0.20,    # way below 0.75 floor
            "reasoning":       "low confidence guess",
        }
        result = await _execute_tool(
            "update_person_name", {"name": "Jagan"},
            "p1", "OldName", db=mock_db,
            user_text="Hey, what is your name?",
            intent_sidecar=sidecar,
        )
        # Rejected — DB not touched, session not changed.
        assert result == "rejected"
        mock_db.update_person_name.assert_not_called()
        # Divergence row records the reject reason.
        mock_brain_db.log_intent_divergence.assert_called()
        kwargs = mock_brain_db.log_intent_divergence.call_args.kwargs
        assert kwargs["tool_proposed"] == "update_person_name"
        assert kwargs["gate_decision"].startswith("reject:")
        assert "0.20" in kwargs["gate_decision"]
    finally:
        _wiring._brain_orchestrator = _prev_orch


async def test_execute_tool_update_person_name_classifier_unavail_fallback_to_regex():
    """P1.7a scenario 3: classifier sidecar is None (timeout / shadow mode off
    / not-in-TOOL_INTENT_MAP). With ``INTENT_FALLBACK_TO_REGEX=True`` (default)
    the handler falls through to ``_user_text_gate_passes`` — legacy safety
    net. Divergence row gets gate_decision='regex_fallback_allow' or
    'regex_fallback_reject'. This test exercises the ALLOW branch (valid
    self-ID phrasing)."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    # INTENT_FALLBACK_TO_REGEX defaults to True. Sanity check — if someone
    # flips the default, this test's premise changes.
    from core.config import INTENT_FALLBACK_TO_REGEX
    assert INTENT_FALLBACK_TO_REGEX is True, "P1.17 flip invalidates this test"

    await pipeline._session_store.open_session("p1", "OldName", "stranger", "face", now=__import__("time").time())
    await pipeline._conversation_store.set_history("p1", [])
    mock_db = MagicMock()
    mock_orch, mock_brain_db = _mk_divergence_capture_orch()
    _prev_orch = pipeline._brain_orchestrator
    _wiring._brain_orchestrator = mock_orch
    try:
        result = await _execute_tool(
            "update_person_name", {"name": "Jagan"},
            "p1", "OldName", db=mock_db,
            user_text="my name is Jagan",
            intent_sidecar=None,   # classifier unavailable
        )
        assert result != "rejected"
        mock_db.update_person_name.assert_called_once_with("p1", "Jagan")
        mock_brain_db.log_intent_divergence.assert_called()
        kwargs = mock_brain_db.log_intent_divergence.call_args.kwargs
        assert kwargs["gate_decision"] == "regex_fallback_allow"
        assert kwargs["structured_intent"] is None  # classifier unavail
    finally:
        _wiring._brain_orchestrator = _prev_orch


async def test_execute_tool_update_person_name_classifier_unavail_fallback_disabled_allows_with_warning(monkeypatch):
    """P1.7a scenario 4: classifier unavailable AND
    ``INTENT_FALLBACK_TO_REGEX=False`` (post-P1.17 state) → handler allows
    with a warning rather than silently dropping the tool call. Divergence
    row gets gate_decision='both_unavailable_allow_with_warning'. Legit
    mutation tools must not be blackholed on classifier infrastructure
    blips."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    # Flip the flag for the duration of this test only.
    monkeypatch.setattr("core.config.INTENT_FALLBACK_TO_REGEX", False)

    await pipeline._session_store.open_session("p1", "OldName", "stranger", "face", now=__import__("time").time())
    await pipeline._conversation_store.set_history("p1", [])
    mock_db = MagicMock()
    mock_orch, mock_brain_db = _mk_divergence_capture_orch()
    _prev_orch = pipeline._brain_orchestrator
    _wiring._brain_orchestrator = mock_orch
    try:
        result = await _execute_tool(
            "update_person_name", {"name": "Jagan"},
            "p1", "OldName", db=mock_db,
            user_text="my name is Jagan",
            intent_sidecar=None,   # classifier unavailable
        )
        # Allowed-with-warning: DB called, result not rejected.
        assert result != "rejected"
        mock_db.update_person_name.assert_called_once_with("p1", "Jagan")
        mock_brain_db.log_intent_divergence.assert_called()
        kwargs = mock_brain_db.log_intent_divergence.call_args.kwargs
        assert kwargs["gate_decision"] == "both_unavailable_allow_with_warning"
    finally:
        _wiring._brain_orchestrator = _prev_orch


async def test_execute_tool_update_system_name_classifier_allows_fires_tool():
    """P1.7b site 3: the direct fix for the 2026-04-22 Alexa-bug live-run.
    Classifier says assign_system_name/Alexa conf=0.95 (regex would reject
    'I want it to be changed to Alexa' for lacking the explicit 'call you X'
    shape). Under P1.7b the classifier is the authority → tool fires,
    _active_system_name flips, divergence row has gate_decision='allow'."""
    import pipeline
    from pipeline import _execute_tool
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    await pipeline._pipeline_state_store.set_active_system_name("Atlas")
    mock_db = MagicMock()
    mock_orch, mock_brain_db = _mk_divergence_capture_orch()
    _prev_orch = pipeline._brain_orchestrator
    _wiring._brain_orchestrator = mock_orch
    try:
        sidecar = {
            "turn_intent":     "assign_system_name",
            "extracted_value": "Alexa",
            "confidence":      0.95,
            "reasoning":       "User explicitly requests rename to Alexa",
        }
        result = await _execute_tool(
            "update_system_name", {"name": "Alexa"},
            "p1", "Jagan", db=mock_db,
            user_text="I want it to be changed to Alexa",
            intent_sidecar=sidecar,
        )
        assert result == "handled"
        assert pipeline._pipeline_state_store.peek_active_system_name() == "Alexa"
        kwargs = mock_brain_db.log_intent_divergence.call_args.kwargs
        assert kwargs["tool_proposed"] == "update_system_name"
        assert kwargs["gate_decision"] == "allow"
    finally:
        _wiring._brain_orchestrator = _prev_orch
        await pipeline._pipeline_state_store.set_active_system_name("Atlas")


async def test_execute_tool_update_system_name_classifier_rejects_on_grounding_fail():
    """P1.7b site 3: classifier label correct but extracted_value doesn't
    appear in user_text (homoglyph / hallucination). _intent_allows rejects
    on grounding — status='rejected', system name unchanged."""
    import pipeline
    from pipeline import _execute_tool
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    await pipeline._pipeline_state_store.set_active_system_name("Atlas")
    mock_db = MagicMock()
    mock_orch, mock_brain_db = _mk_divergence_capture_orch()
    _prev_orch = pipeline._brain_orchestrator
    _wiring._brain_orchestrator = mock_orch
    try:
        sidecar = {
            "turn_intent":     "assign_system_name",
            "extracted_value": "Nova",  # classifier hallucinated this
            "confidence":      0.99,
            "reasoning":       "fabricated",
        }
        result = await _execute_tool(
            "update_system_name", {"name": "Nova"},
            "p1", "Jagan", db=mock_db,
            user_text="tell me a joke",   # user never said Nova
            intent_sidecar=sidecar,
        )
        assert result == "rejected"
        assert pipeline._pipeline_state_store.peek_active_system_name() == "Atlas"
        kwargs = mock_brain_db.log_intent_divergence.call_args.kwargs
        assert kwargs["gate_decision"].startswith("reject:")
        assert "not grounded" in kwargs["gate_decision"]
    finally:
        _wiring._brain_orchestrator = _prev_orch


async def test_execute_tool_report_identity_mismatch_classifier_allows():
    """P1.7b site 2: classifier labels deny_identity → tool fires, session
    flips to disputed. The decorated branch short-circuits the legacy
    IDENTITY_DENIAL_PATTERNS regex."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    await pipeline._session_store.open_session("p1", "Jagan", "known", "face", now=__import__("time").time())
    mock_db = MagicMock()
    mock_orch, mock_brain_db = _mk_divergence_capture_orch()
    _prev_orch = pipeline._brain_orchestrator
    _wiring._brain_orchestrator = mock_orch
    try:
        sidecar = {
            "turn_intent":     "deny_identity",
            "extracted_value": None,
            "confidence":      0.92,
            "reasoning":       "user denies claimed identity",
        }
        result = await _execute_tool(
            "report_identity_mismatch", {"reason": "user says they are not Jagan"},
            "p1", "Jagan", db=mock_db,
            user_text="no I'm not Jagan",
            intent_sidecar=sidecar,
        )
        await asyncio.sleep(0)
        assert result == "handled"
        _snap = pipeline._session_store.peek_snapshot("p1")
        assert _snap is not None and _snap.person_type == "disputed"
        kwargs = mock_brain_db.log_intent_divergence.call_args.kwargs
        assert kwargs["tool_proposed"] == "report_identity_mismatch"
        assert kwargs["gate_decision"] == "allow"
    finally:
        _wiring._brain_orchestrator = _prev_orch


async def test_execute_tool_report_identity_mismatch_classifier_rejects_question():
    """P1.7b site 2: the Bug G3 case — 'who are you talking to?' is a
    question, not a denial. Classifier labels casual_conversation →
    _intent_allows rejects on intent mismatch → session NOT flipped. This
    is the exact ~15-turn break the gate exists to prevent."""
    import pipeline
    from pipeline import _execute_tool
    import time as _t
    await pipeline._session_store.open_session("p1", "Jagan", "known", "face", now=__import__("time").time())
    mock_db = MagicMock()
    mock_orch, mock_brain_db = _mk_divergence_capture_orch()
    _prev_orch = pipeline._brain_orchestrator
    _wiring._brain_orchestrator = mock_orch
    try:
        sidecar = {
            "turn_intent":     "casual_conversation",
            "extracted_value": None,
            "confidence":      0.90,
            "reasoning":       "meta question about scene, not denial",
        }
        result = await _execute_tool(
            "report_identity_mismatch", {"reason": "speaker does not match"},
            "p1", "Jagan", db=mock_db,
            user_text="who are you talking to?",
            intent_sidecar=sidecar,
        )
        assert result == "rejected"
        # Session must NOT have been flipped to disputed.
        _snap = pipeline._session_store.peek_snapshot("p1")
        assert _snap is not None and _snap.person_type == "known"
        kwargs = mock_brain_db.log_intent_divergence.call_args.kwargs
        assert kwargs["gate_decision"].startswith("reject:")
        assert "expected=deny_identity" in kwargs["gate_decision"]
    finally:
        _wiring._brain_orchestrator = _prev_orch


async def test_execute_tool_shutdown_classifier_allows_fires():
    """P1.7b site 4: explicit shutdown command + classifier confirms →
    returns 'shutdown' signal. Cross-check: INTENT_SHUTDOWN_CONF_MIN (0.80)
    is strictly higher than the general floor, so conf=0.85 passes shutdown
    but would reject on a marginal case (tested elsewhere)."""
    import pipeline
    from pipeline import _execute_tool
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    mock_orch, mock_brain_db = _mk_divergence_capture_orch()
    _prev_orch = pipeline._brain_orchestrator
    _wiring._brain_orchestrator = mock_orch
    try:
        sidecar = {
            "turn_intent":     "request_shutdown",
            "extracted_value": None,
            "confidence":      0.95,
            "reasoning":       "explicit shutdown command",
        }
        result = await _execute_tool(
            "shutdown", {}, "p1", "Jagan", db=None,
            user_text="shut down",
            intent_sidecar=sidecar,
        )
        assert result == "shutdown"
        kwargs = mock_brain_db.log_intent_divergence.call_args.kwargs
        assert kwargs["tool_proposed"] == "shutdown"
        assert kwargs["gate_decision"] == "allow"
    finally:
        _wiring._brain_orchestrator = _prev_orch


async def test_execute_tool_shutdown_ambiguous_farewell_both_gates_reject():
    """P1.7b site 4 (reviewer's Session 86 refinement): the SAFETY-CRITICAL
    case from the 2026-04-22 live run — user says 'okay bye' / 'we'll
    discuss next session' (ambiguous farewells). Classifier labels
    casual_conversation; regex ALSO rejects (no explicit shutdown phrase).
    Dual-gate DENIES shutdown → status='rejected'. Confirmed behavior in
    both gates independently is the production-critical property for the
    highest-blast-radius tool."""
    import pipeline
    from pipeline import _execute_tool
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    mock_orch, mock_brain_db = _mk_divergence_capture_orch()
    _prev_orch = pipeline._brain_orchestrator
    _wiring._brain_orchestrator = mock_orch
    try:
        sidecar = {
            "turn_intent":     "casual_conversation",
            "extracted_value": None,
            "confidence":      0.95,
            "reasoning":       "farewell, not command",
        }
        result = await _execute_tool(
            "shutdown", {}, "p1", "Jagan", db=None,
            user_text="okay bye, we'll discuss next session",
            intent_sidecar=sidecar,
        )
        # Classifier gate rejects (intent mismatch) — returns before regex
        # ever fires. Test asserts the production-critical outcome: shutdown
        # does NOT fire on farewell.
        assert result == "rejected"
        kwargs = mock_brain_db.log_intent_divergence.call_args.kwargs
        assert kwargs["gate_decision"].startswith("reject:")
        assert "expected=request_shutdown" in kwargs["gate_decision"]
    finally:
        _wiring._brain_orchestrator = _prev_orch


async def test_execute_tool_shutdown_classifier_unavail_falls_through_to_3_regex_chain():
    """P1.7b site 4 (reviewer's Session 86 refinement): classifier sidecar
    is None → _regex_says_shutdown() fallback decides, using the 3-regex
    chain (STRICT + LENIENT + QUESTION exclusion). 'shut down' matches
    STRICT → allows; 'why did you shut down?' matches QUESTION exclusion
    → rejects. Exercises both the 'allow via regex fallback' path AND the
    'reject via question-exclusion' path."""
    import pipeline
    from pipeline import _execute_tool
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    mock_orch, mock_brain_db = _mk_divergence_capture_orch()
    _prev_orch = pipeline._brain_orchestrator
    _wiring._brain_orchestrator = mock_orch
    try:
        # Allow path: strict phrase, classifier unavail.
        result = await _execute_tool(
            "shutdown", {}, "p1", "Jagan", db=None,
            user_text="shut down",
            intent_sidecar=None,
        )
        assert result == "shutdown"
        kwargs = mock_brain_db.log_intent_divergence.call_args.kwargs
        assert kwargs["gate_decision"] == "regex_fallback_allow"
        mock_brain_db.log_intent_divergence.reset_mock()
        # Reset the Session 70 tool-repeat guard state — same (tool, args)
        # fired twice in a unit-test context would trip it before the new
        # regex-fallback code even runs.
        await pipeline._session_store.update_tool_repeat("p1", None, 0)
        # Reject path: the question-about-shutdown exclusion in the 3-regex
        # chain — "why did you shut down?" has the phrase but is wrapped
        # in a question.
        result2 = await _execute_tool(
            "shutdown", {}, "p1", "Jagan", db=None,
            user_text="why did you shut down earlier?",
            intent_sidecar=None,
        )
        assert result2 == "rejected"
        kwargs2 = mock_brain_db.log_intent_divergence.call_args.kwargs
        assert kwargs2["gate_decision"] == "regex_fallback_reject"
    finally:
        _wiring._brain_orchestrator = _prev_orch


async def test_execute_tool_auto_confirm_classifier_rejects_holds_promotion():
    """P1.7b site 5: auto-confirm is the only site where the
    both-unavailable policy is HOLD (not allow-with-warning) — runs every
    stranger turn, false-positive promotion is irreversible. Classifier
    labels casual_conversation (user didn't self-ID) → held. No DB write,
    no type flip. Test drives through ``conversation_turn`` path via the
    source-inspection version — behavior-level integration fixture for
    auto-confirm is prohibitively large."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    idx = src.find("IDENTITY_AUTO_THRESHOLD")
    assert idx > -1
    branch = src[idx:idx + 4000]
    # All three branches must be present after P1.7b.
    assert "_intent_sidecar is not None" in branch, "classifier branch missing"
    assert "INTENT_FALLBACK_TO_REGEX" in branch, "regex fallback branch missing"
    # Both-unavailable MUST be fail-closed (hold), NOT allow-with-warning
    # like the other mutation tools. Auto-confirm runs per-turn; false
    # promotions are irreversible.
    assert "both_unavailable_hold" in branch, (
        "auto-confirm must fail-closed (HOLD) when both gates unavailable — "
        "NOT allow-with-warning. Runs every stranger turn so a false-positive "
        "promotion is worse than a one-turn delay."
    )


async def test_execute_tool_update_system_name_updates_global():
    import pipeline
    from pipeline import _execute_tool
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    await pipeline._pipeline_state_store.set_active_system_name("Dog")
    _wiring._brain_orchestrator = None
    mock_db = MagicMock()
    await _execute_tool(
        "update_system_name", {"name": "Rex"},
        "p1", "Jagan", db=mock_db,
        user_text="I'll call you Rex",   # Session 73: gate requires assignment phrase
    )
    assert pipeline._pipeline_state_store.peek_active_system_name() == "Rex"
    mock_db.set_system_identity.assert_called_once()


async def test_execute_tool_update_system_name_no_op_when_same():
    import pipeline
    from pipeline import _execute_tool
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    await pipeline._pipeline_state_store.set_active_system_name("Rex")
    mock_db = MagicMock()
    await _execute_tool(
        "update_system_name", {"name": "rex"},
        "p1", "Jagan", db=mock_db,
        user_text="call you Rex",  # Session 73 gate
    )
    mock_db.set_system_identity.assert_not_called()


async def test_execute_tool_unknown_log_message_distinct_from_blocked(capsys):
    """Bug P: the 'unknown tool, discarded' log message must NOT use the
    'BLOCKED' phrasing — those are separate failure modes and the log is the
    signal that distinguishes model artifacts from security violations."""
    import pipeline
    from pipeline import _execute_tool
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    await _execute_tool("Buddy", {}, "p1", "Jagan", db=None)
    out = capsys.readouterr().out
    assert "unknown tool, discarded" in out
    assert "BLOCKED" not in out, (
        "unknown-tool path must NOT emit the BLOCKED log — that's the "
        "privilege-denied path and conflating them is the Bug P root cause"
    )


async def test_execute_tool_unknown_tool_does_not_fire_privilege_gate():
    """Bug P: the unknown filter runs BEFORE the privilege gate. Evidence:
    even for a best_friend (max privileges), an unknown tool must return
    'unknown' — not 'handled'. Without the Layer-0 filter, the flow hit
    the privilege gate's 'not in table' fallback and logged BLOCKED."""
    import pipeline
    from pipeline import _execute_tool
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    result = await _execute_tool("Buddy", {}, "p1", "Jagan", db=None)
    assert result == "unknown"


async def test_execute_tool_update_system_name_noop_returns_handled_noop():
    """Bug Q Part B: when update_system_name is called with the name already
    set, the handler returns 'handled_noop' (not 'handled'). This is the
    signal conversation_turn uses to suppress the canonical ack, breaking
    the feedback loop where the LLM re-issues the same call each turn."""
    import pipeline
    from pipeline import _execute_tool
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    await pipeline._pipeline_state_store.set_active_system_name("Kara")
    result = await _execute_tool(
        "update_system_name", {"name": "Kara"}, "p1", "Jagan", db=None,
        user_text="call you Kara",
    )
    assert result == "handled_noop", (
        f"no-op call must return 'handled_noop', got {result!r} — "
        f"without this the canonical ack fires and feeds the feedback loop"
    )


async def test_execute_tool_update_person_name_noop_returns_handled_noop():
    """Bug Q Part B: symmetric fix for update_person_name. Rename to the same
    name is a no-op and must not emit the canonical 'Got it, {name}' ack."""
    import pipeline
    from pipeline import _execute_tool
    await pipeline._session_store.open_session("p1", "Jagan", "known", "face", now=__import__("time").time())
    result = await _execute_tool(
        "update_person_name", {"name": "Jagan"}, "p1", "Jagan", db=None,
        user_text="my name is Jagan",
    )
    assert result == "handled_noop"


def test_retry_note_injects_hedge_for_rejected_rename():
    """Fix A (2026-04-22 live observation): when a rename tool is rejected,
    the retry system_note must instruct the model to use hedged phrasing
    ("I heard X — is that right?") instead of fabricating confirmation
    ("From now on you can call me X").

    Session 99 Fix E: system_note building now lives in the module-level
    `_build_tool_rejection_note` helper, shared between the Together.ai
    retry path (ONLINE) and the Ollama fallback path (SICK). Source-
    inspection the helper rather than conversation_turn."""
    import inspect, pipeline
    src = inspect.getsource(pipeline._build_tool_rejection_note)
    # The retry branch must detect rejected rename tools specifically.
    assert '"update_system_name", "update_person_name"' in src, (
        "retry path must detect rejected renames by tool name"
    )
    assert 'tool_results.get(tc["name"]) == "rejected"' in src, (
        "retry must check 'rejected' status (not 'handled' / 'unknown')"
    )
    assert "Do NOT say" in src, (
        "system_note must explicitly forbid confirmation phrasings"
    )
    assert "you can call me" in src, (
        "system_note must call out the exact fabrication pattern seen in the "
        "2026-04-22 log ('you can call me X') — abstract rules without the "
        "concrete forbidden phrase drift"
    )
    assert "is that right?" in src, (
        "system_note must give the retry path the hedged-question template"
    )


def test_retry_note_uses_classifier_value_when_available():
    """Fix A: prefer the shadow classifier's extracted_value over the LLM's
    proposed tool arg — classifier is the honest ground-truth for what the
    user actually said. If classifier returned None (timeout / failure),
    fall back to tool_args['name']."""
    import inspect, pipeline
    src = inspect.getsource(pipeline._build_tool_rejection_note)
    assert "intent_sidecar" in src, (
        "Fix A should consult the shadow classifier when building the system_note"
    )
    assert 'extracted_value' in src, (
        "classifier's extracted_value is the preferred rename-target source"
    )


def test_all_unreal_branch_routes_to_together_when_cloud_online():
    """Session 99 Fix E #1: when tool calls are ungrounded AND cloud is
    ONLINE, conversation_turn must call `ask_retry_text` (Together.ai
    with tools disabled), NOT `_ask_offline_safe` (Ollama). The main
    model has full conversation context, visitor history, SCENE block,
    and owner-access prompt — Ollama has none of that and confabulated
    in every prior canary."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    # The ONLINE branch must call ask_retry_text.
    assert "ask_retry_text(" in src, (
        "_all_unreal ONLINE branch must route to Together.ai retry, not Ollama"
    )
    # Branch must be gated on CloudState.ONLINE.
    assert "CloudState.ONLINE" in src, (
        "Fix E gating depends on cloud state — must explicitly check ONLINE"
    )


def test_all_unreal_branch_falls_back_to_ollama_when_cloud_sick():
    """Session 99 Fix E #2: when cloud is SICK/OFFLINE the existing
    Ollama fallback stays intact — that's its proper role as the
    genuine cloud-down backstop. Regression guard: confirms the SICK
    branch was NOT accidentally deleted in the refactor."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    # SICK branch must still invoke _ask_offline_safe with the same
    # system_note + history plumbing.
    assert "_ask_offline_safe(" in src, (
        "SICK branch must still call Ollama fallback"
    )
    # Must pass conversation_history and system_note (Session 77/96/98 hints).
    assert "system_note=_system_note_retry" in src, (
        "Ollama path must still receive the rejection system_note"
    )
    assert "conversation_history=history" in src, (
        "Ollama fallback must still receive full conversation history"
    )


def test_ask_retry_text_disables_tools_to_prevent_recursion():
    """Session 99 Fix E #3: the retry call MUST disable tools — otherwise
    the brain could emit another tool call that gets rejected, triggering
    another retry, ad infinitum. `_stream_together_raw(include_tools=False)`
    is the mechanism; source-inspect to confirm."""
    import inspect
    from core import brain
    src = inspect.getsource(brain.ask_retry_text)
    assert "include_tools=False" in src, (
        "ask_retry_text must call _stream_together_raw with include_tools=False "
        "to prevent tool-call recursion on the retry"
    )


def test_ask_retry_text_preserves_conversation_history_and_context():
    """Session 99 Fix E #6: the retry must pass full context — conversation
    history, vision_state, memory_context, prompt_addendum, scene_block —
    all the things Ollama lacks. That's the entire reason this fix
    exists."""
    import inspect
    from core import brain
    src = inspect.getsource(brain.ask_retry_text)
    # Signature must accept all the standard context params.
    for param in (
        "conversation_history", "vision_state", "memory_context",
        "prompt_addendum", "scene_block", "system_name",
    ):
        assert param in src, (
            f"ask_retry_text must accept {param!r} — the retry "
            f"contract requires full context parity with ask_stream"
        )
    # _build_system_prompt is how those params become prompt text.
    assert "_build_system_prompt" in src, (
        "retry must reuse the same prompt builder so context surfaces identically"
    )


def test_ask_retry_text_injects_system_note_as_separate_message():
    """Session 99 Fix E #4: the retry_system_note (explaining which
    tool was rejected and why) must reach the model. It's injected
    as its OWN system message after the main system prompt so it
    doesn't get drowned in the larger context."""
    import inspect
    from core import brain
    src = inspect.getsource(brain.ask_retry_text)
    assert "retry_system_note" in src, (
        "ask_retry_text must accept retry_system_note param"
    )
    # Added to messages list as a system-role entry.
    assert '{"role": "system", "content": retry_system_note}' in src, (
        "retry note must land as a system-role message, not user or assistant — "
        "system gives it authoritative weight"
    )


def test_shutdown_rejection_override_runs_before_retry_branch():
    """Session 99 Fix E #5 (preserves Session 28 Issue A): the shutdown
    rejection override sets `response = 'Okay.'` BEFORE the _all_unreal
    retry branch. Must stay in that order — otherwise a rejected shutdown
    would trigger a full retry round-trip instead of the terse canonical
    ack."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    shutdown_idx = src.find("_shutdown_was_rejected")
    retry_idx    = src.find("_all_unreal and not response")
    assert shutdown_idx >= 0 and retry_idx > 0, (
        "both branches must be present in conversation_turn"
    )
    assert shutdown_idx < retry_idx, (
        "Issue A shutdown override must run BEFORE the retry branch — "
        "otherwise 'Okay.' gets clobbered by the retry round-trip"
    )


def test_build_tool_rejection_note_returns_none_when_no_rejection_applies():
    """Session 99 Fix E #7: when the rejected-tool shape doesn't match
    any of the note-building rules (neither rename nor identity-mismatch
    on an owner query), the helper returns None. Retry path still fires
    — the brain just doesn't get explicit rejection context on that
    turn and generates a conversational response from history alone."""
    import pipeline
    # Tool call for a generic rejected tool (not rename, not mismatch).
    tool_calls = [{"name": "search_web", "args": {"query": "x"}}]
    tool_results = {"search_web": "rejected"}
    note = pipeline._build_tool_rejection_note(
        tool_calls=tool_calls,
        tool_results=tool_results,
        intent_sidecar=None,
        person_id="bf_001",
        bf_id="bf_001",
        brain_orchestrator=None,
    )
    assert note is None, (
        "helper must return None when no rejection shape matches — the "
        "retry path handles None gracefully by firing without explicit context"
    )

    # Sanity: rename rejection still yields a note.
    tool_calls_rename = [{"name": "update_system_name", "args": {"name": "Kara"}}]
    note2 = pipeline._build_tool_rejection_note(
        tool_calls=tool_calls_rename,
        tool_results={"update_system_name": "rejected"},
        intent_sidecar={"extracted_value": "Kara"},
        person_id="bf_001",
        bf_id="bf_001",
        brain_orchestrator=None,
    )
    assert note2 is not None
    assert "Kara" in note2


def test_retry_note_distinguishes_system_name_vs_person_name():
    """Fix A: the hedge message must correctly target 'yourself' vs 'the
    user' based on which rename tool was rejected (update_system_name
    renames the AI; update_person_name renames the speaker)."""
    import inspect, pipeline
    src = inspect.getsource(pipeline._build_tool_rejection_note)
    assert "yourself" in src and "the user" in src, (
        "system_note subject must correctly distinguish which party was the "
        "rename target; update_system_name → 'yourself', update_person_name → "
        "'the user'"
    )


async def test_execute_tool_unknown_tool_returns_unknown_status():
    """Bug P (2026-04-21 live run): names not in TOOL_PRIVILEGES are model
    hallucinations (LLM echoing a word from user input as a function name).
    Used to fall through all branches and return None — indistinguishable
    from privilege-denied. Now returns the dedicated "unknown" status so
    conversation_turn can retry for text rather than emit the error filler."""
    import pipeline
    from pipeline import _execute_tool
    result = await _execute_tool("nonexistent_tool", {}, "p1", "Jagan", db=None)
    assert result == "unknown", (
        f"unknown tool name must return 'unknown' status, got {result!r}"
    )


async def test_tool_repeat_guard_fires_on_second_consecutive_call():
    """L3: Same (tool, args) fired twice in a row — second call returns None."""
    import pipeline
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    await pipeline._pipeline_state_store.set_active_system_name("OldName")

    r1 = await pipeline._execute_tool(
        "update_system_name", {"name": "BotName"}, "p1", "Jagan", db=None,
        user_text="call you BotName",
    )
    assert r1 == "handled"
    # Drain the event loop so the create_task(update_tool_repeat) scheduled by r1
    # runs before r2 reads peek_snapshot — the repeat guard state is async.
    await asyncio.sleep(0)

    r2 = await pipeline._execute_tool(
        "update_system_name", {"name": "BotName"}, "p1", "Jagan", db=None,
        user_text="call you BotName",
    )
    assert r2 is None


async def test_tool_repeat_guard_resets_on_different_args():
    """L3: Different args hash — guard does not fire, second call proceeds."""
    import pipeline
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    await pipeline._pipeline_state_store.set_active_system_name("OldName")

    r1 = await pipeline._execute_tool(
        "update_system_name", {"name": "Alpha"}, "p1", "Jagan", db=None,
        user_text="call you Alpha",
    )
    assert r1 == "handled"

    r2 = await pipeline._execute_tool(
        "update_system_name", {"name": "Beta"}, "p1", "Jagan", db=None,
        user_text="call you Beta",
    )
    assert r2 == "handled"


async def test_tool_repeat_guard_resets_after_pop():
    """L3: After guard keys are popped (simulates new user message), same tool proceeds."""
    import pipeline
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    await pipeline._pipeline_state_store.set_active_system_name("OldName")

    await pipeline._execute_tool(
        "update_system_name", {"name": "Kara"}, "p1", "Jagan", db=None,
        user_text="call you Kara",
    )

    # Simulate new user message: reset tool repeat state in session store
    await pipeline._session_store.update_tool_repeat("p1", None, 0)
    await pipeline._pipeline_state_store.set_active_system_name("OldName")  # reset so tool has work to do

    r = await pipeline._execute_tool(
        "update_system_name", {"name": "Kara"}, "p1", "Jagan", db=None,
        user_text="call you Kara",
    )
    assert r == "handled"


async def test_tool_repeat_guard_different_tool_unaffected():
    """L3: Guard counter is per (tool+args) key — a different tool is not blocked."""
    import pipeline
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    await pipeline._pipeline_state_store.set_active_system_name("OldName")

    # Fire update_system_name once (count=1 for that key)
    await pipeline._execute_tool(
        "update_system_name", {"name": "Rex"}, "p1", "Jagan", db=None,
        user_text="call you Rex",
    )

    # set_language has a different key — must proceed normally
    await pipeline._execute_tool(
        "set_language", {"language": "en"}, "p1", "Jagan", db=None
    )
    assert pipeline._pipeline_state_store.peek_detected_lang() == "en"


async def test_shutdown_rejected_for_partial_phrase_in_longer_sentence():
    """B3: "i'm done" inside a longer sentence must NOT trigger shutdown."""
    from pipeline import _execute_tool
    result = await _execute_tool("shutdown", {}, "p1", "Jagan", db=None,
                                  user_text="i'm done thinking about it let's move on")
    assert result is None


async def test_shutdown_accepted_for_exact_good_night():
    """B3: standalone "good night" must still trigger shutdown."""
    import pipeline
    from pipeline import _execute_tool
    await pipeline._session_store.open_session("p1", "Jagan", "best_friend", "face", now=__import__("time").time())
    result = await _execute_tool("shutdown", {}, "p1", "Jagan", db=None,
                                  user_text="good night")
    assert result == "shutdown"


async def test_shutdown_rejected_for_good_night_in_context():
    """B3: "good night" embedded in a sentence must NOT trigger shutdown."""
    from pipeline import _execute_tool
    result = await _execute_tool("shutdown", {}, "p1", "Jagan", db=None,
                                  user_text="I had a good night last night")
    assert result is None


async def test_rejected_shutdown_response_overridden_to_neutral():
    """Issue A: When shutdown() is rejected, response written to history must be 'Okay.' not 'Goodbye!'."""
    import pipeline
    from pipeline import conversation_turn, CloudState

    orig_cloud     = pipeline._pipeline_state_store.peek_cloud_state()
    orig_brain     = pipeline._brain_orchestrator
    orig_lang      = pipeline._pipeline_state_store.peek_detected_lang()
    orig_sysname   = pipeline._pipeline_state_store.peek_active_system_name()
    orig_shutdown  = pipeline._shutdown_event

    await pipeline._session_store.open_session("p_sd", "Jagan", "best_friend", "face", now=__import__("time").time())
    await pipeline._conversation_store.set_history("p_sd", [])
    await pipeline._pipeline_state_store.recover_online_no_flag()
    pipeline._per_person_agent_store.reset()
    _wiring._brain_orchestrator    = None
    await pipeline._pipeline_state_store.set_detected_lang("en")
    await pipeline._pipeline_state_store.set_active_system_name("Kara")
    pipeline._shutdown_event        = asyncio.Event()   # fresh, not set

    async def fake_ask_stream(*args, **kwargs):
        yield ("text", "Goodbye!")
        yield ("tool_calls", [{"name": "shutdown", "args": {}}])

    async def fake_speak_stream(sentences, **kw):
        async for _ in sentences:
            pass

    try:
        with patch("pipeline.ask_stream",   new=fake_ask_stream), \
             patch("pipeline.speak_stream", new=fake_speak_stream), \
             patch("pipeline._set_state"), \
             patch("pipeline.play_filler"):
            await conversation_turn("hey", "p_sd", "Jagan", db=None)

        hist = pipeline._conversation_store.peek_history("p_sd")
        assert hist[-1]["role"] == "assistant"
        assert hist[-1]["content"] == "Okay.", \
            f"Expected 'Okay.' but got {hist[-1]['content']!r}"
    finally:
        await pipeline._pipeline_state_store.set_cloud_state(orig_cloud)
        _wiring._brain_orchestrator    = orig_brain
        await pipeline._pipeline_state_store.set_detected_lang(orig_lang)
        await pipeline._pipeline_state_store.set_active_system_name(orig_sysname)
        pipeline._shutdown_event        = orig_shutdown


async def test_rejected_shutdown_does_not_write_goodbye_to_history():
    """Issue A: 'Goodbye!' must never appear as the last assistant history entry after a rejected shutdown."""
    import pipeline
    from pipeline import conversation_turn, CloudState

    orig_cloud     = pipeline._pipeline_state_store.peek_cloud_state()
    orig_brain     = pipeline._brain_orchestrator
    orig_lang      = pipeline._pipeline_state_store.peek_detected_lang()
    orig_sysname   = pipeline._pipeline_state_store.peek_active_system_name()
    orig_shutdown  = pipeline._shutdown_event

    await pipeline._session_store.open_session("p_sd", "Jagan", "best_friend", "face", now=__import__("time").time())
    await pipeline._conversation_store.set_history("p_sd", [])
    await pipeline._pipeline_state_store.recover_online_no_flag()
    pipeline._per_person_agent_store.reset()
    _wiring._brain_orchestrator    = None
    await pipeline._pipeline_state_store.set_detected_lang("en")
    await pipeline._pipeline_state_store.set_active_system_name("Kara")
    pipeline._shutdown_event        = asyncio.Event()

    async def fake_ask_stream(*args, **kwargs):
        yield ("text", "Goodbye!")
        yield ("tool_calls", [{"name": "shutdown", "args": {}}])

    async def fake_speak_stream(sentences, **kw):
        async for _ in sentences:
            pass

    try:
        with patch("pipeline.ask_stream",   new=fake_ask_stream), \
             patch("pipeline.speak_stream", new=fake_speak_stream), \
             patch("pipeline._set_state"), \
             patch("pipeline.play_filler"):
            await conversation_turn("Don't look at that", "p_sd", "Jagan", db=None)

        hist = pipeline._conversation_store.peek_history("p_sd")
        assert hist[-1]["role"] == "assistant"
        assert "goodbye" not in hist[-1]["content"].lower(), \
            f"'Goodbye!' leaked into history: {hist[-1]['content']!r}"
    finally:
        await pipeline._pipeline_state_store.set_cloud_state(orig_cloud)
        _wiring._brain_orchestrator    = orig_brain
        await pipeline._pipeline_state_store.set_detected_lang(orig_lang)
        await pipeline._pipeline_state_store.set_active_system_name(orig_sysname)
        pipeline._shutdown_event        = orig_shutdown


async def test_approved_shutdown_override_does_not_fire():
    """Issue A: When shutdown() is approved (_shutdown_event set), response override must NOT fire."""
    import pipeline
    from pipeline import conversation_turn, CloudState

    orig_cloud     = pipeline._pipeline_state_store.peek_cloud_state()
    orig_brain     = pipeline._brain_orchestrator
    orig_lang      = pipeline._pipeline_state_store.peek_detected_lang()
    orig_sysname   = pipeline._pipeline_state_store.peek_active_system_name()
    orig_shutdown  = pipeline._shutdown_event

    await pipeline._session_store.open_session("p_sd", "Jagan", "best_friend", "face", now=__import__("time").time())
    await pipeline._conversation_store.set_history("p_sd", [])
    await pipeline._pipeline_state_store.recover_online_no_flag()
    pipeline._per_person_agent_store.reset()
    _wiring._brain_orchestrator    = None
    await pipeline._pipeline_state_store.set_detected_lang("en")
    await pipeline._pipeline_state_store.set_active_system_name("Kara")
    pipeline._shutdown_event        = asyncio.Event()

    async def fake_ask_stream(*args, **kwargs):
        yield ("text", "Goodbye!")
        yield ("tool_calls", [{"name": "shutdown", "args": {}}])

    async def fake_speak_stream(sentences, **kw):
        async for _ in sentences:
            pass

    try:
        with patch("pipeline.ask_stream",   new=fake_ask_stream), \
             patch("pipeline.speak_stream", new=fake_speak_stream), \
             patch("pipeline._set_state"), \
             patch("pipeline.play_filler"):
            await conversation_turn("shut down", "p_sd", "Jagan", db=None)

        hist = pipeline._conversation_store.peek_history("p_sd")
        assert hist[-1]["role"] == "assistant"
        # Approved path: override must NOT have replaced the LLM's text with "Okay."
        assert hist[-1]["content"] != "Okay.", \
            "Override fired on an approved shutdown — it should only fire on rejected calls"
    finally:
        await pipeline._pipeline_state_store.set_cloud_state(orig_cloud)
        _wiring._brain_orchestrator    = orig_brain
        await pipeline._pipeline_state_store.set_detected_lang(orig_lang)
        await pipeline._pipeline_state_store.set_active_system_name(orig_sysname)
        pipeline._shutdown_event        = orig_shutdown


@pytest.mark.asyncio
async def test_execute_tool_shutdown_blocked_for_stranger():
    """Stranger must not be able to trigger shutdown."""
    import pipeline, time as _t
    await pipeline._session_store.open_session("stranger_abc", "visitor", "stranger", "face", now=_t.time())
    result = await pipeline._execute_tool("shutdown", {}, "stranger_abc", "visitor", db=None, user_text="shut down")
    assert result is None


@pytest.mark.asyncio
async def test_execute_tool_update_system_name_blocked_for_stranger():
    """Stranger must not be able to rename the system."""
    import pipeline, time as _t
    await pipeline._session_store.open_session("stranger_abc", "visitor", "stranger", "face", now=_t.time())
    result = await pipeline._execute_tool("update_system_name", {"name": "Hacker"}, "stranger_abc", "visitor", db=None)
    assert result is None


@pytest.mark.asyncio
async def test_execute_tool_update_system_name_blocked_for_known():
    """Known (non-owner) person must not be able to rename the system."""
    import pipeline, time as _t
    await pipeline._session_store.open_session("known_p1", "Alice", "known", "face", now=_t.time())
    result = await pipeline._execute_tool("update_system_name", {"name": "NewBot"}, "known_p1", "Alice", db=None)
    assert result is None


@pytest.mark.asyncio
async def test_execute_tool_update_system_name_allowed_for_best_friend():
    """Best friend must be able to rename the system."""
    import pipeline
    import time as _t
    await pipeline._session_store.open_session("bf_p1", "Jagan", "best_friend", "face", now=_t.time())
    await pipeline._pipeline_state_store.set_active_system_name("Dog")
    _wiring._brain_orchestrator = None
    mock_db = MagicMock()
    result = await pipeline._execute_tool(
        "update_system_name", {"name": "Kara"}, "bf_p1", "Jagan", db=mock_db,
        user_text="call you Kara",
    )
    assert result == "handled"
    assert pipeline._pipeline_state_store.peek_active_system_name() == "Kara"


@pytest.mark.asyncio
async def test_execute_tool_shutdown_blocked_for_known():
    """Known (non-owner) person must not be able to trigger shutdown — only best_friend."""
    import pipeline, time as _t
    await pipeline._session_store.open_session("known_p1", "Alice", "known", "face", now=_t.time())
    result = await pipeline._execute_tool("shutdown", {}, "known_p1", "Alice", db=None, user_text="shut down please")
    assert result is None


@pytest.mark.asyncio
async def test_execute_tool_shutdown_allowed_for_best_friend():
    """Best friend must be able to trigger shutdown."""
    import pipeline
    import time as _t
    await pipeline._session_store.open_session("bf_p1", "Jagan", "best_friend", "face", now=_t.time())
    # Use an exact phrase from _SHUTDOWN_STRICT so the phrase-guard also passes
    result = await pipeline._execute_tool("shutdown", {}, "bf_p1", "Jagan", db=None,
                                          user_text="please shut down now")
    assert result == "shutdown"
