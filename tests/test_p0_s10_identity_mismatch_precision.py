"""P0.S10 — Brain + classifier identity-mismatch precision tightening.

8 anchors per Plan v4 §3 LOCK at exact mid 8 (inclusive ±15% band [6.8, 9.2]):

  A1 — D1 source-inspection: `_INTENT_CLASSIFIER_SYSTEM` contains
       `ASSERTION-DOMAIN RULE` block + canary date anchor + IDENTITY/TOPIC
       partition + DISTINGUISHING TEST + 5 verbatim counter-examples.
  A2 — D1 source-inspection: prompt contains ≥3 verbatim counter-examples
       (`"I don't have a job"`, `"I don't go to office"`, `"I'm not in school anymore"`).
  A3 — D2 source-inspection: `report_identity_mismatch` tool description
       contains `Topic corrections` bullet with canary phrasing `"I don't have any job"`
       AND `Session 10 canary 2026-05-27` reference + `update_person_name` redirect.
  A4 — D3 HYBRID source-inspection (character-presence) + behavioral verification.
       Character-presence: `IDENTITY_DENIAL_PATTERNS` tuple exists with 6 patterns;
       pattern #1 contains 4 lookahead categories with exact term lists from §2.2
       ("that" REMOVED + "into"/"interested" PRESENT). Behavioral: 3-5
       canary-derived counter-example assertions verify both reject + preserve
       classes via `re.search` calls against NFKC-casefolded inputs.
  A5 — D3 behavioral: `_intent_allows("report_identity_mismatch", "deny_identity",
       0.95, None, "I don't have any job and I don't go to office", {})` returns
       `(False, ...)` with reason containing `P0.S10 D3`; THE CANARY'S EXACT FAILURE MODE.
  A6 — D3 behavioral REGRESSION GUARD: `_intent_allows("report_identity_mismatch",
       "deny_identity", 0.95, None, "I'm not Jagan", {})` returns `(True, "intent match")`.
  A7 — D3 behavioral PARAMETRIZE fan-out: ~28 cases (9 preserve identity-denials
       MATCH + 10 reject topic-denials BLOCK + 6 existing test denials PASS +
       3 existing benign DON'T MATCH). Logical anchor = 1 per spec contract.
  A8 — golden_intent.jsonl regression row: canary's exact failure phrasing
       tagged `regression_session_canary_day1` with expected `personal_statement`.

Spec: tests/p0_s10_identity_mismatch_precision_plan_v4.md
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.config import IDENTITY_DENIAL_PATTERNS


def _nfkc_lower(s: str) -> str:
    """Mirror of pipeline.py::_nfkc_lower (NFKC normalize + casefold)."""
    return unicodedata.normalize("NFKC", s).casefold()


def _matches_any_denial(text: str) -> bool:
    """Apply NFKC-casefolded match against IDENTITY_DENIAL_PATTERNS with re.IGNORECASE."""
    lt = _nfkc_lower(text)
    return any(re.search(p, lt, re.IGNORECASE) for p in IDENTITY_DENIAL_PATTERNS)


# ───────────────────────────────────────────────────────────────────────
# A1 — D1 source-inspection: ASSERTION-DOMAIN RULE block presence
# ───────────────────────────────────────────────────────────────────────


def test_a1_assertion_domain_rule_block_present_in_classifier_prompt():
    """D1 — `_INTENT_CLASSIFIER_SYSTEM` MUST contain ASSERTION-DOMAIN RULE
    block + canary date anchor + IDENTITY/TOPIC partition + DISTINGUISHING TEST.
    """
    brain_src = (_REPO_ROOT / "core" / "brain.py").read_text(encoding="utf-8")
    # Anchor on the classifier system constant
    assert "_INTENT_CLASSIFIER_SYSTEM" in brain_src
    # Block header + canary date
    assert "ASSERTION-DOMAIN RULE" in brain_src, (
        "D1: ASSERTION-DOMAIN RULE block header missing from _INTENT_CLASSIFIER_SYSTEM"
    )
    assert "Session 10 canary fix" in brain_src and "2026-05-27" in brain_src, (
        "D1: canary date anchor missing"
    )
    # IDENTITY vs TOPIC partition
    assert "IDENTITY denial" in brain_src, "D1: IDENTITY domain partition missing"
    assert "TOPIC denial" in brain_src, "D1: TOPIC domain partition missing"
    # DISTINGUISHING TEST
    assert "DISTINGUISHING TEST" in brain_src, "D1: DISTINGUISHING TEST clause missing"
    # Prefer personal_statement bias on uncertainty
    assert "prefer" in brain_src and "personal_statement" in brain_src, (
        "D1: uncertainty-bias toward personal_statement missing"
    )


# ───────────────────────────────────────────────────────────────────────
# A2 — D1 source-inspection: ≥3 verbatim counter-examples
# ───────────────────────────────────────────────────────────────────────


def test_a2_classifier_prompt_contains_3_verbatim_counter_examples():
    """D1 — at least 3 canary-derived counter-examples MUST appear verbatim
    in the ASSERTION-DOMAIN RULE block to anchor LLM judgment.
    """
    brain_src = (_REPO_ROOT / "core" / "brain.py").read_text(encoding="utf-8")
    required_examples = [
        "I don't have a job",
        "I don't go to office",
        "I'm not in school anymore",
    ]
    for ex in required_examples:
        assert ex in brain_src, (
            f"D1: required counter-example {ex!r} missing from prompt"
        )


# ───────────────────────────────────────────────────────────────────────
# A3 — D2 source-inspection: topic-correction bullet in tool description
# ───────────────────────────────────────────────────────────────────────


def test_a3_tool_description_contains_topic_correction_bullet():
    """D2 — `report_identity_mismatch` tool description MUST contain a
    Topic-corrections bullet with the canary's exact failure phrasing AND
    a redirect to `update_person_name` for replacement-name cases.
    """
    brain_src = (_REPO_ROOT / "core" / "brain.py").read_text(encoding="utf-8")
    # Locate the tool definition block
    assert '"name": "report_identity_mismatch"' in brain_src, (
        "report_identity_mismatch tool name missing"
    )
    # Topic corrections bullet + canary anchor
    assert "Topic corrections" in brain_src, (
        "D2: 'Topic corrections' bullet missing from DO-NOT-call list"
    )
    assert "I don't have any job" in brain_src, (
        "D2: canary phrasing \"I don't have any job\" missing from tool description"
    )
    assert "Session 10 canary 2026-05-27" in brain_src, (
        "D2: canary date anchor missing from tool description"
    )
    # update_person_name redirect — already part of pre-existing DO-NOT-call
    # bullet for "I'm not Jagan, I'm Lexi" replacement-name case; verify it
    # still anchors the redirect path.
    assert "use update_person_name instead" in brain_src, (
        "D2: update_person_name redirect missing"
    )


# ───────────────────────────────────────────────────────────────────────
# A4 — D3 HYBRID source-inspection (character-presence) + behavioral
# ───────────────────────────────────────────────────────────────────────


def test_a4_identity_denial_patterns_hybrid_contract():
    """D3 HYBRID — character-presence ("that" REMOVED + "into"/"interested"
    PRESENT in lookaheads) + 3-5 behavioral counter-example assertions
    (canary "I don't have any job" + "I'm not in school anymore" +
    "I'm not sure" + identity-denial preserve cases).

    Plan v4 §11.2 strengthened contract: structural lookahead-category
    verification AND behavioral re.search outcome assertions, BOTH.
    """
    # Tuple exists with 6 patterns
    assert isinstance(IDENTITY_DENIAL_PATTERNS, tuple), (
        "D3: IDENTITY_DENIAL_PATTERNS must be tuple (immutable)"
    )
    assert len(IDENTITY_DENIAL_PATTERNS) == 6, (
        f"D3: expected 6 patterns, got {len(IDENTITY_DENIAL_PATTERNS)}"
    )

    # Character-presence: pattern #1 contains the 4 lookahead categories.
    pattern_1 = IDENTITY_DENIAL_PATTERNS[0]
    # Spatial prepositions lookahead — INCL. compound forms
    assert "into" in pattern_1, "D3: pattern #1 lookahead must INCLUDE 'into'"
    assert "onto" in pattern_1, "D3: pattern #1 lookahead must INCLUDE 'onto'"
    # Epistemic states lookahead — INCL. interested per Plan v3 §2.2
    assert "interested" in pattern_1, (
        "D3: pattern #1 lookahead must INCLUDE 'interested'"
    )
    assert "sure" in pattern_1, "D3: pattern #1 lookahead must INCLUDE 'sure'"
    # Progressive verbs lookahead
    assert "feeling" in pattern_1, "D3: pattern #1 lookahead must INCLUDE 'feeling'"
    # Adverb modifiers lookahead — "that" MUST BE ABSENT per PI #3 absorption
    # The CRITICAL character-presence test: "that\b" must NOT appear as a
    # negative-lookahead alternation atom (it WAS in Plan v3, REMOVED in Plan v4).
    # AST-precise check: split pattern #1 on lookahead boundaries and verify
    # none of the (?!(...)\b) groups contains "that" as an alternation atom.
    lookahead_groups = re.findall(r"\(\?!\(\?:([^)]+)\)\\b\)", pattern_1)
    for group in lookahead_groups:
        atoms = group.split("|")
        assert "that" not in atoms, (
            f"D3: pattern #1 lookahead {group!r} must NOT contain 'that' "
            f"(Plan v4 path A: 'that' REMOVED from lookahead #4 per PI #3 — "
            f"'that' is determiner/pronoun, not adverb; 'I'm not that person' "
            f"is identity-denial)"
        )

    # Behavioral: 3 canary-derived reject-class counter-examples MUST NOT match
    assert not _matches_any_denial("I don't have any job"), (
        "D3 behavioral: canary phrasing 'I don't have any job' MUST NOT match "
        "(topic-denial, would route through report_identity_mismatch incorrectly)"
    )
    assert not _matches_any_denial("I'm not in school anymore"), (
        "D3 behavioral: 'I'm not in school anymore' MUST NOT match (topic-denial)"
    )
    assert not _matches_any_denial("I'm not sure"), (
        "D3 behavioral: 'I'm not sure' MUST NOT match (epistemic-state lookahead)"
    )

    # Behavioral: 2 canary-derived preserve-class identity-denials MUST match
    assert _matches_any_denial("I'm not Jagan"), (
        "D3 behavioral: 'I'm not Jagan' MUST match (canonical identity-denial)"
    )
    assert _matches_any_denial("I'm not that person"), (
        "D3 behavioral: 'I'm not that person' MUST match — PI #3 fix verifies "
        "'that' was REMOVED from adverb lookahead so determiner-sense reaches pattern"
    )


# ───────────────────────────────────────────────────────────────────────
# A5 — D3 behavioral: canary's EXACT failure mode rejected
# ───────────────────────────────────────────────────────────────────────


def test_a5_intent_allows_rejects_canary_topic_denial(monkeypatch):
    """D3 — `_intent_allows("report_identity_mismatch", "deny_identity",
    0.95, None, "I don't have any job and I don't go to office", {})`
    MUST return (False, reason) with reason containing 'P0.S10 D3'.
    The canary's exact failure mode.
    """
    # Set up minimal pipeline import via conftest stub mechanism
    from tests.conftest import setup_pipeline_stubs
    setup_pipeline_stubs()

    import pipeline as _pl

    allowed, reason = _pl._intent_allows(
        tool_name="report_identity_mismatch",
        turn_intent="deny_identity",
        confidence=0.95,
        extracted_value=None,
        user_text="I don't have any job and I don't go to office",
        tool_args={"reason": "speaker insists they are not working"},
    )

    assert allowed is False, (
        "A5: canary topic-denial MUST be rejected by D3 gate "
        f"(got allowed={allowed!r}, reason={reason!r})"
    )
    assert "P0.S10 D3" in reason, (
        f"A5: rejection reason must reference P0.S10 D3 (got {reason!r})"
    )


# ───────────────────────────────────────────────────────────────────────
# A6 — D3 behavioral REGRESSION GUARD: real identity-denial still passes
# ───────────────────────────────────────────────────────────────────────


def test_a6_intent_allows_passes_canonical_identity_denial():
    """D3 regression guard — `_intent_allows("report_identity_mismatch",
    "deny_identity", 0.95, None, "I'm not Jagan", {})` MUST return
    (True, "intent match"). Real identity-denial must reach the tool.
    """
    from tests.conftest import setup_pipeline_stubs
    setup_pipeline_stubs()

    import pipeline as _pl

    allowed, reason = _pl._intent_allows(
        tool_name="report_identity_mismatch",
        turn_intent="deny_identity",
        confidence=0.95,
        extracted_value=None,
        user_text="I'm not Jagan",
        tool_args={"reason": "speaker says not Jagan"},
    )

    assert allowed is True, (
        "A6: canonical identity-denial 'I'm not Jagan' MUST pass D3 gate "
        f"(got allowed={allowed!r}, reason={reason!r})"
    )
    assert reason == "intent match", (
        f"A6: pass reason must be 'intent match' (got {reason!r})"
    )


# ───────────────────────────────────────────────────────────────────────
# A7 — D3 behavioral PARAMETRIZE fan-out (~28 cases)
# ───────────────────────────────────────────────────────────────────────


# 9 preserve cases — identity-denials MUST match
_PRESERVE_CASES = [
    ("i'm not jagan", "canonical name denial"),
    ("i'm not him", "pronoun denial — him"),
    ("i'm not her", "pronoun denial — her"),
    ("i'm not them", "pronoun denial — them"),
    ("i'm not the right person", "denial + replacement phrase"),
    ("i'm not who you think i am", "denial-of-knowledge phrase"),
    ("i'm not that person", "PI #3 fix — that-determiner identity-denial"),
    ("i'm not that guy", "PI #3 fix — that-guy variant"),
    ("i'm not that one", "PI #3 fix — that-one variant"),
]

# 10 reject cases — topic-denials MUST NOT match
_REJECT_CASES = [
    ("i'm not in school anymore", "spatial preposition — in"),
    ("i'm not at work today", "spatial preposition — at"),
    ("i'm not feeling well", "progressive verb — feeling"),
    ("i'm not sure what you meant", "epistemic state — sure"),
    ("i'm not in office", "canary's EXACT failure class"),
    ("i'm not into music", "spatial preposition — into compound"),
    ("i'm not interested", "epistemic state — interested"),
    ("i'm not really sure", "adverb modifier — really"),
    ("i'm not very happy", "adverb modifier — very"),
    ("i'm not quite ready", "adverb modifier — quite"),
]

# 6 existing test denials (`test_pipeline.py:2426-2433`) — STILL MATCH
_EXISTING_DENIAL_CASES = [
    ("i'm not jagan", "S73 Bug G3 existing — pattern #1"),
    ("that's not me", "S73 Bug G3 existing — pattern #2"),
    ("wrong person", "S73 Bug G3 existing — pattern #3"),
    ("you confused me with my brother", "S73 Bug G3 existing — pattern #4"),
    ("i'm not the person you think", "S73 Bug G3 existing — pattern #5"),
    ("stop calling me wrong", "S73 Bug G3 existing — pattern #6"),
]

# 3 existing benign — STILL DON'T match
_EXISTING_BENIGN_CASES = [
    ("who are you talking to?", "S73 Bug G3 benign — question"),
    ("can you tell me about jagan?", "S73 Bug G3 benign — query"),
    ("hello there", "S73 Bug G3 benign — greeting"),
]


@pytest.mark.parametrize("text,note", _PRESERVE_CASES)
def test_a7_preserve_identity_denials_match(text: str, note: str):
    """A7 preserve-class — 9 identity-denial phrasings MUST match the gate.
    Includes 3 PI #3 fix cases ("that person/guy/one") proving "that" was
    REMOVED from lookahead #4 per Plan v4 path A.
    """
    assert _matches_any_denial(text), (
        f"A7 preserve: {text!r} ({note}) MUST match IDENTITY_DENIAL_PATTERNS"
    )


@pytest.mark.parametrize("text,note", _REJECT_CASES)
def test_a7_reject_topic_denials_blocked(text: str, note: str):
    """A7 reject-class — 10 topic-denial phrasings MUST NOT match.
    Canary's exact failure class ("I'm not in office") + 9 lookahead-category
    variants verify all 4 lookahead categories work as designed.
    """
    assert not _matches_any_denial(text), (
        f"A7 reject: {text!r} ({note}) MUST NOT match IDENTITY_DENIAL_PATTERNS "
        f"(topic-denial would falsely trigger report_identity_mismatch)"
    )


@pytest.mark.parametrize("text,note", _EXISTING_DENIAL_CASES)
def test_a7_existing_denial_coverage_preserved(text: str, note: str):
    """A7 existing-denial regression guard — 6 Session 73 Bug G3 test
    denials MUST still match. P0.S10 path A re-pattern preserves S73
    coverage (Plan v4 §2.4 invariant).
    """
    assert _matches_any_denial(text), (
        f"A7 existing-denial: {text!r} ({note}) MUST still match "
        f"(Session 73 Bug G3 regression coverage)"
    )


@pytest.mark.parametrize("text,note", _EXISTING_BENIGN_CASES)
def test_a7_existing_benign_inputs_dont_false_match(text: str, note: str):
    """A7 existing-benign regression guard — 3 Session 73 Bug G3 benign
    inputs MUST NOT match. P0.S10 path A doesn't introduce false-positives
    on questions/queries/greetings.
    """
    assert not _matches_any_denial(text), (
        f"A7 existing-benign: {text!r} ({note}) MUST NOT match "
        f"(would false-positive identity-mismatch on benign turn)"
    )


# ───────────────────────────────────────────────────────────────────────
# A8 — golden_intent.jsonl regression row
# ───────────────────────────────────────────────────────────────────────


def test_a8_golden_intent_jsonl_canary_regression_row_present():
    """A8 — `tests/golden_intent.jsonl` MUST contain the canary's exact
    failure phrasing tagged `regression_session_canary_day1` with expected
    `personal_statement` label so future bench runs detect any regression.
    """
    golden_path = _REPO_ROOT / "tests" / "golden_intent.jsonl"
    assert golden_path.is_file(), "golden_intent.jsonl must exist"

    rows = []
    for line in golden_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))

    canary_rows = [
        r for r in rows
        if r.get("source") == "regression_session_canary_day1"
    ]
    assert canary_rows, (
        "A8: at least one golden_intent.jsonl row tagged "
        "`regression_session_canary_day1` MUST exist"
    )

    # The canary's exact phrasing must appear in user_text
    canary_phrase = "i don't have any job"
    matched = [
        r for r in canary_rows
        if canary_phrase in r.get("user_text", "").lower()
    ]
    assert matched, (
        f"A8: golden row containing canary phrasing {canary_phrase!r} "
        f"MUST exist (found {len(canary_rows)} canary-tagged rows, none matched)"
    )
    # Expected label is personal_statement (NOT deny_identity)
    for r in matched:
        assert r.get("expected_intent") == "personal_statement", (
            f"A8: canary regression row expected_intent must be "
            f"'personal_statement' (got {r.get('expected_intent')!r})"
        )
