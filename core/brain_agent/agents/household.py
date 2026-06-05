"""core/brain_agent/agents/household.py — HouseholdExtractionAgent.

Extracted VERBATIM from core/brain_agent.py (P1.A1 SP-2 Commit 4).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import httpx

from core.sanitize import wrap_user_input
from core.config import DEFAULT_SYSTEM_NAME
from core.brain_agent._llm import (
    _call_llm_chat,
    _parse_json,
)


class HouseholdExtractionAgent:
    """Extracts household-scoped facts and inter-person relationships from conversation turns.

    Dual-trigger (called from BrainOrchestrator):
    - Per-turn: fires on every user utterance to capture household facts + relationships
    - Session-end: deep analysis of full session for relationship consolidation

    Key design principles (from research):
    - Speaker attribution is explicit — "Jagan said 'my wife works nights'" → attributed to Priya
    - Household scope vs per-person scope classified at extraction time
    - Non-enrolled persons get shadow nodes, not full entity nodes
    - All decisions made by LLM — no hardcoded rules
    """

    _SYSTEM = (
        "You are a household context extractor for an AI robot. "
        "Your job is to extract HOUSEHOLD-LEVEL facts from a single conversation utterance. "
        "Focus only on:\n"
        "1. Facts about shared household assets/routines (we, our, the family, the house)\n"
        "2. Individual facts about SPECIFIC NAMED PEOPLE (not the current speaker unless explicitly stated)\n"
        "3. Relationships between people\n"
        "4. Non-enrolled persons mentioned by name (shadow nodes)\n\n"
        "DO NOT extract: conversational filler, opinions about the world, facts about public figures, "
        "single-word vague references, or facts already obvious from the question alone.\n\n"
        "CRITICAL relationship rule: Only use a relationship type that is explicitly stated or unmistakably implied in the utterance. "
        "If the speaker says 'my sister Kavya' → sibling_of. 'my wife Priya' → married_to. 'my colleague Ravi' → colleague_of. "
        "NEVER infer a spouse/married_to relationship unless the word 'wife', 'husband', 'spouse', or 'married' is present. "
        "When in doubt between sibling and spouse, always use sibling_of or family_member_of — never default to married_to.\n\n"
        "Respond with ONLY valid JSON matching this schema:\n"
        "{\n"
        '  "household_facts": [\n'
        '    {"entity": "household", "attribute": "dinner_time", "value": "around 8pm", '
        '"scope": "household", "confidence": 0.75}\n'
        "  ],\n"
        '  "per_person_facts": [\n'
        '    {"entity": "Priya", "attribute": "work_schedule", "value": "night shifts", '
        '"inferred_from": "speaker said \'my wife works nights\'", "confidence": 0.85}\n'
        "  ],\n"
        '  "relationships": [\n'
        '    {"person_a": "Jagan", "relationship": "married_to", "person_b": "Priya", "confidence": 0.95},\n'
        '    {"person_a": "Jagan", "relationship": "sibling_of", "person_b": "Kavya", "confidence": 0.90}\n'
        "  ],\n"
        '  "shadow_persons": [\n'
        '    {"name": "Anita", "mentioned_by": "Priya", "relationship": "colleague_of", '
        '"facts": [{"attribute": "works_at", "value": "same office", "confidence": 0.7}]}\n'
        "  ]\n"
        "}"
    )

    def __init__(self, http: httpx.AsyncClient):
        self._http        = http
        self._system_name = DEFAULT_SYSTEM_NAME

    def set_system_name(self, name: str) -> None:
        self._system_name = name

    async def _call_api(self, prompt: str, max_tokens: int, label: str) -> dict | None:
        """Session 69 (Bugs J + M): migrated to the shared ``_call_llm_chat``
        helper. Retries transient network errors; propagates 4xx; validates the
        response shape explicitly. The `label` is threaded into agent_name so
        per-turn vs session-end failures are distinguishable in logs."""
        raw = await _call_llm_chat(
            self._http,
            [
                {"role": "system", "content": self._SYSTEM},
                {"role": "user",   "content": wrap_user_input(prompt)},
            ],
            agent_name=f"HouseholdAgent:{label}",
            max_tokens=max_tokens,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        if raw is None:
            return None
        return _parse_json(raw)

    async def extract_per_turn(
        self,
        speaker_id: str,
        speaker_name: str,
        utterance: str,
        context_turns: list[dict],
        enrolled_persons: list[str],
    ) -> dict | None:
        """Extract household facts from a single utterance."""
        if len(utterance.split()) < 4:
            return None

        ctx_text = ""
        if context_turns:
            ctx_lines = [
                f"{t['role'].upper()}: {t['content'][:150]}"
                for t in context_turns[-3:]
            ]
            ctx_text = "\nRecent context:\n" + "\n".join(ctx_lines)

        enrolled_str = ", ".join(enrolled_persons) if enrolled_persons else "none yet"
        prompt = (
            f"Current speaker: {speaker_name} (id={speaker_id})\n"
            f"Known household members: {enrolled_str}\n"
            f"AI system name (NOT a person — never extract as shadow_person): {self._system_name}\n"
            f"{ctx_text}\n\n"
            f"Current utterance: {utterance}\n\n"
            "Extract household facts, relationships, and shadow persons from the utterance above. "
            "When the speaker says 'my wife/husband/kid/colleague', resolve to the known household member "
            "if the relationship matches. Attribute facts to the correct person, not the speaker. "
            f"IMPORTANT: '{self._system_name}' is the AI robot's name — never create a shadow_person for it. "
            "If nothing worth extracting, return empty arrays."
        )
        return await self._call_api(prompt, max_tokens=400, label="Per-turn extraction")

    async def extract_session_end(
        self,
        person_id: str,
        person_name: str,
        session_turns: list[dict],
        enrolled_persons: list[str],
    ) -> dict | None:
        """Deep relationship consolidation analysis of full session transcript."""
        if len(session_turns) < 4:
            return None

        transcript = "\n".join(
            f"[{t['role'].upper()}] {t['content'][:200]}"
            for t in session_turns[-30:]
        )
        enrolled_str = ", ".join(enrolled_persons) if enrolled_persons else "none yet"
        prompt = (
            f"Primary speaker this session: {person_name} (id={person_id})\n"
            f"All enrolled household members: {enrolled_str}\n"
            f"AI system name (NOT a person — never extract as shadow_person): {self._system_name}\n\n"
            f"Session transcript:\n{transcript}\n\n"
            "Analyze the full session above. Extract:\n"
            "1. Confirmed household facts (mentioned multiple times or with high certainty)\n"
            "2. Confirmed relationships between household members\n"
            "3. Any new shadow persons mentioned (non-enrolled people referenced by name)\n"
            "4. Behavioral patterns (recurring topics, routines confirmed across the session)\n"
            f"IMPORTANT: '{self._system_name}' is the AI robot's name — never create a shadow_person for it. "
            "Focus on STABLE, REPEATED, or HIGH-CONFIDENCE facts only. Ignore passing remarks."
        )
        return await self._call_api(prompt, max_tokens=600, label="Session-end extraction")
