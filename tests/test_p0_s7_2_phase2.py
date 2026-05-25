"""tests/test_p0_s7_2_phase2.py — P0.S7.2 Phase 2 (κ — extraction extension).

Plan v2 §6 Phase 2 = 4 logical tests / ~9 collected via parametrize:

  3. test_triage_admits_multi_person_assistant_turn (×3 participant counts)
  4. test_triage_skips_single_person_assistant_turn
  5. test_triage_skips_short_multi_person_assistant_turn
  6. test_extract_assistant_room_turn_fan_out_per_participant (×6 parametrize
     covering P1 + P2 + P3 + enum-validation coverage)

All 4 deliberate-regression confirmations from §8 are inducible against the
tests in this file: drop fan-out loop → 6a fails; drop disputed-skip → 6e
fails; drop counter-example from extract prompt → 6d fails (canary).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# P0.S7 D2 — module-level privacy_critical marker; all tests verify
# P0.S7.2 κ multi-person assistant-turn extraction (cross-session memory
# retrieval — the gap that motivated the Phase 3A arc).
pytestmark = pytest.mark.privacy_critical


# ────────────────────────────────────────────────────────────────────────────
# Test 3 — triage admits multi-person assistant turns
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("participant_count", [2, 3, 4])
def test_triage_admits_multi_person_assistant_turn(participant_count):
    """Plan v2 §4.1 + test 3 — TriageAgent.should_process must return
    (True, 'multi_person_assistant_turn') for an assistant turn in a
    multi-person room (count ≥ 2) with content ≥ 80 chars (D5)."""
    from core.brain_agent import TriageAgent

    long_content = (
        "To make cheese cookies, you'll need butter, sugar, eggs, flour, "
        "and cheese — I can walk you through the recipe if you'd like."
    )
    assert len(long_content) >= 80
    agent = TriageAgent()
    ok, reason = agent.should_process(
        role="assistant",
        content=long_content,
        room_participant_count=participant_count,
    )
    assert ok is True
    assert reason == "multi_person_assistant_turn", (
        f"Expected reason='multi_person_assistant_turn' for {participant_count}-"
        f"participant room; got {reason!r}"
    )


# ────────────────────────────────────────────────────────────────────────────
# Test 4 — triage preserves single-person assistant-turn skip
# ────────────────────────────────────────────────────────────────────────────


def test_triage_skips_single_person_assistant_turn():
    """Plan v2 D7 — single-person assistant turns continue to be skipped
    (default kwarg room_participant_count=1 preserves backward-compat for
    callers that don't supply the kwarg)."""
    from core.brain_agent import TriageAgent

    long_content = "x" * 200  # well over 80 chars; isolates the count gate.
    agent = TriageAgent()
    ok, reason = agent.should_process(
        role="assistant", content=long_content,
        room_participant_count=1,
    )
    assert ok is False
    assert reason == "assistant turn"

    # Default kwarg path (no room_participant_count supplied) — same outcome.
    ok2, reason2 = agent.should_process(role="assistant", content=long_content)
    assert ok2 is False
    assert reason2 == "assistant turn"


# ────────────────────────────────────────────────────────────────────────────
# Test 5 — D5 min-chars guard skips short multi-person assistant turns
# ────────────────────────────────────────────────────────────────────────────


def test_triage_skips_short_multi_person_assistant_turn():
    """Plan v2 D5 — content < ASSISTANT_TURN_EXTRACT_MIN_CHARS (80) skipped
    even when room is multi-person. Filters acknowledgments / KAIROS
    check-ins / filler."""
    from core.brain_agent import TriageAgent

    short_content = "Got it!"  # 7 chars
    agent = TriageAgent()
    ok, reason = agent.should_process(
        role="assistant",
        content=short_content,
        room_participant_count=3,
    )
    assert ok is False
    assert reason == "assistant turn"


# ────────────────────────────────────────────────────────────────────────────
# Test 6 — fan-out per participant + 6-parametrize for P1/P2/P3 coverage
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "case_id,llm_output,participant_names,participant_pids,disputed_pids,expected_facts",
    [
        # 6a — shared_information with addressee — primary `received_*` +
        #      witness `witnessed_*` to_<addressee>.
        (
            "6a_shared_info_with_addressee",
            {
                "topic": "cheese cookies recipe",
                "action_type": "shared_information",
                "primary_subject_name": "Lexi",
                "key_details": "butter, sugar, eggs, flour",
            },
            ["Jagan", "Lexi"], ["j_001", "l_002"], set(),
            [
                ("Jagan", "j_001", "witnessed_shared_information",
                 "cheese cookies recipe to_Lexi"),
                ("Lexi",  "l_002", "received_shared_information",
                 "cheese cookies recipe: butter, sugar, eggs, flour"),
            ],
        ),
        # 6b — asked_question (P1 new enum) — tests the 5th action_type lands
        #      as the attribute prefix correctly.
        (
            "6b_asked_question",
            {
                "topic": "thesis deadline",
                "action_type": "asked_question",
                "primary_subject_name": "Lexi",
                "key_details": None,
            },
            ["Jagan", "Lexi"], ["j_001", "l_002"], set(),
            [
                ("Jagan", "j_001", "witnessed_asked_question", "thesis deadline to_Lexi"),
                ("Lexi",  "l_002", "received_asked_question", "thesis deadline"),
            ],
        ),
        # 6c — primary_subject null → all participants get `witnessed_*`; no
        #      `received_*` fact emitted.
        (
            "6c_room_general_no_addressee",
            {
                "topic": "today's weather",
                "action_type": "engaged_general_discussion",
                "primary_subject_name": None,
                "key_details": None,
            },
            ["Jagan", "Lexi", "Kara_friend"],
            ["j_001", "l_002", "k_003"],
            set(),
            [
                ("Jagan",        "j_001", "witnessed_engaged_general_discussion", "today's weather"),
                ("Lexi",         "l_002", "witnessed_engaged_general_discussion", "today's weather"),
                ("Kara_friend",  "k_003", "witnessed_engaged_general_discussion", "today's weather"),
            ],
        ),
        # 6d — P2 addressee semantic: Jagan = ADDRESSEE; Lexi appears in topic
        #      but is the TOPIC-SUBJECT (not addressee). Jagan = received_*;
        #      Lexi (participant) = witnessed_* (her topic-subject role does
        #      NOT promote to received_*).
        (
            "6d_addressee_vs_topic_subject_disambiguation",
            {
                "topic": "Lexi's cooking",
                "action_type": "shared_information",
                "primary_subject_name": "Jagan",  # ADDRESSEE per P2
                "key_details": "she likes baking",
            },
            ["Jagan", "Lexi"], ["j_001", "l_002"], set(),
            [
                ("Jagan", "j_001", "received_shared_information",
                 "Lexi's cooking: she likes baking"),
                ("Lexi",  "l_002", "witnessed_shared_information",
                 "Lexi's cooking to_Jagan"),
            ],
        ),
        # 6e (NEW P3) — disputed pid in set → THAT pid's Extraction NOT emitted;
        #               other participants get their facts as normal.
        (
            "6e_disputed_pid_skipped",
            {
                "topic": "recipe steps",
                "action_type": "shared_information",
                "primary_subject_name": "Lexi",
                "key_details": "mix dry first",
            },
            ["Jagan", "Lexi", "Kara_friend"],
            ["j_001", "l_002", "k_003"],
            {"l_002"},  # Lexi is disputed
            [
                # Lexi (l_002) would have been the received_*; SKIPPED because disputed.
                ("Jagan",        "j_001", "witnessed_shared_information",
                 "recipe steps to_Lexi"),
                ("Kara_friend",  "k_003", "witnessed_shared_information",
                 "recipe steps to_Lexi"),
            ],
        ),
        # 6f (NEW P1 catch-all) — engaged_general_discussion + primary set →
        #     primary still receives; rest witness.
        (
            "6f_general_discussion_with_addressee",
            {
                "topic": "weekend plans",
                "action_type": "engaged_general_discussion",
                "primary_subject_name": "Jagan",
                "key_details": None,
            },
            ["Jagan", "Lexi"], ["j_001", "l_002"], set(),
            [
                ("Jagan", "j_001", "received_engaged_general_discussion", "weekend plans"),
                ("Lexi",  "l_002", "witnessed_engaged_general_discussion",
                 "weekend plans to_Jagan"),
            ],
        ),
    ],
)
def test_extract_assistant_room_turn_fan_out_per_participant(
    case_id, llm_output, participant_names, participant_pids,
    disputed_pids, expected_facts,
):
    """Plan v2 §6 test 6 (revised) — _fan_out_to_participants emits the
    correct Extraction objects across P1 enum + P2 addressee + P3
    disputed-skip + enum-validation coverage."""
    from core.brain_agent import _fan_out_to_participants

    facts = _fan_out_to_participants(
        extracted=llm_output,
        participant_names=participant_names,
        participant_pids=participant_pids,
        disputed_pids=disputed_pids,
    )
    actual = [
        (f.entity, f.person_id, f.attribute, f.value)
        for f in facts
    ]
    assert sorted(actual) == sorted(expected_facts), (
        f"Case {case_id} fan-out mismatch.\n"
        f"  Expected (sorted): {sorted(expected_facts)}\n"
        f"  Actual   (sorted): {sorted(actual)}"
    )
    # D6 — every emitted Extraction carries personal tier.
    for f in facts:
        assert f.privacy_level == "personal", (
            f"Case {case_id}: Extraction {f.entity}.{f.attribute} carries "
            f"privacy_level={f.privacy_level!r}; D6 requires 'personal' for "
            f"both subject-of-fact + witness-of-fact."
        )
    # Confidence pinned per Plan v2 §4.2 (0.85 fan-out default).
    for f in facts:
        assert f.confidence == 0.85, (
            f"Case {case_id}: Extraction {f.entity}.{f.attribute} confidence "
            f"is {f.confidence}; Plan v2 §4.2 pins fan-out confidence at 0.85."
        )


# ────────────────────────────────────────────────────────────────────────────
# Bonus — enum-validation belt-and-braces (auditor Q1 follow-up)
# ────────────────────────────────────────────────────────────────────────────


def test_fan_out_collapses_invalid_action_type_to_general():
    """Auditor Q1 — LLM-hallucinated action_type outside the 5-enum collapses
    to engaged_general_discussion. Belt-and-braces defense; prevents
    invalid attribute names like `received_made_up_value` from polluting
    the knowledge graph."""
    from core.brain_agent import _fan_out_to_participants

    facts = _fan_out_to_participants(
        extracted={
            "topic": "topic",
            "action_type": "invented_action_type",  # outside the 5-enum
            "primary_subject_name": None,
            "key_details": None,
        },
        participant_names=["Jagan", "Lexi"],
        participant_pids=["j_001", "l_002"],
        disputed_pids=set(),
    )
    assert len(facts) == 2
    for f in facts:
        # Attribute prefix must be the canonical catch-all, not the invented name.
        assert f.attribute == "witnessed_engaged_general_discussion", (
            f"Invalid action_type 'invented_action_type' must collapse to "
            f"engaged_general_discussion; got attribute={f.attribute!r}"
        )


def test_fan_out_returns_empty_on_non_substantive_turn():
    """Plan v2 §4.2 — `topic` null or missing → return [] (non-substantive
    turn). Prevents empty facts from entering brain.db."""
    from core.brain_agent import _fan_out_to_participants

    for non_sub_payload in (
        None,
        {},
        {"topic": None},
        {"topic": ""},
        {"topic": "   "},  # whitespace-only
    ):
        result = _fan_out_to_participants(
            non_sub_payload,
            ["Jagan", "Lexi"],
            ["j_001", "l_002"],
            set(),
        )
        assert result == [], (
            f"Non-substantive payload {non_sub_payload!r} must return []; "
            f"got {result!r}"
        )


# ────────────────────────────────────────────────────────────────────────────
# Bonus — _ASSISTANT_ROOM_EXTRACT_SYSTEM prompt carries the P2 counter-example
# ────────────────────────────────────────────────────────────────────────────


def test_assistant_room_extract_system_prompt_has_p2_counter_example():
    """Plan v2 P2 — the addressee counter-example is verbatim in the
    extraction prompt. Catches refactors that strip the counter-example
    (Phase 4 deliberate-regression confirmation (e) inducible against this)."""
    from core.brain_agent import _ASSISTANT_ROOM_EXTRACT_SYSTEM

    # Counter-example anchor.
    assert "Jagan, Lexi mentioned earlier she likes" in _ASSISTANT_ROOM_EXTRACT_SYSTEM, (
        "P0.S7.2 P2: extraction prompt must include the verbatim addressee "
        "counter-example so brain understands primary_subject_name = "
        "addressee, NOT topic-subject."
    )
    assert "addressee" in _ASSISTANT_ROOM_EXTRACT_SYSTEM.lower(), (
        "P0.S7.2 P2: extraction prompt must use the label 'addressee' to "
        "anchor the semantic."
    )
    # 5-enum coverage in the prompt (P1).
    for action_type in (
        "shared_information",
        "answered_question",
        "asked_question",       # P1 new
        "made_suggestion",
        "engaged_general_discussion",
    ):
        assert action_type in _ASSISTANT_ROOM_EXTRACT_SYSTEM, (
            f"P0.S7.2 P1: extraction prompt must enumerate {action_type!r} "
            f"as one of the 5 action_type values."
        )
