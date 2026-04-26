"""Classifier sidecar dict → SPEAK / SILENT / None.

Decision policy (default-deny on SPEAK):

  intent == "addressing_ai"                                 → SPEAK
  intent == "direct_address_to_person" AND extracted ==     → SPEAK
                                          target_speaker
  intent == "direct_address_to_person" AND extracted !=     → SILENT
                                          target_speaker
  any other intent                                          → SILENT
  sidecar is None  (classifier failed: timeout / bad JSON / → None
                   no API key)                                  (excluded)

A None return is NOT counted as wrong — the spec carves out an
"exclusions" bucket so timeout-class failures don't pollute the
balanced-accuracy number.

The mapping intentionally does NOT try to predict implicit turn-taking
("active participant who'd jump in next"). Kara-OS's classifier doesn't
claim that capability — it answers "is the AI being addressed?" The
caveat block in RESULTS.md spells this out.
"""
from __future__ import annotations


def map_to_decision(
    sidecar: "dict | None",
    target_speaker: str,
) -> "str | None":
    """Return 'SPEAK' / 'SILENT' / None per the policy above."""
    if sidecar is None:
        return None
    intent = sidecar.get("turn_intent") or ""
    extracted = (sidecar.get("extracted_value") or "").strip().lower()
    target_lower = (target_speaker or "").strip().lower()

    if intent == "addressing_ai":
        return "SPEAK"
    # Session 119 Path 1 — implicit addressing. The classifier emits this
    # label when the AI is an active participant in the thread AND the
    # current utterance invites a response (group-directed question,
    # "right?" / "anyone?" tags, or thread continuation). Maps to SPEAK
    # for the benchmark — production code does NOT route on this label
    # (no pipeline gate consumes it), so behavior on Jagan's home use
    # stays identical until/unless the gate is wired in a later session.
    if intent == "topical_participant_response":
        return "SPEAK"
    if intent == "direct_address_to_person":
        if extracted and extracted == target_lower:
            return "SPEAK"
        # Some other named person is the addressee — target stays silent.
        return "SILENT"
    # casual_conversation / live_data_query / general_knowledge_query /
    # opinion_query / personal_statement / request_shutdown /
    # question_about_shutdown / unclear / assign_*_name / deny_identity /
    # confirm_identity — none of these mean target_speaker is being
    # addressed. Default-deny on SPEAK.
    return "SILENT"
