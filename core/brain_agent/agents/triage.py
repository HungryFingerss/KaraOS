"""core/brain_agent/agents/triage.py — TriageAgent — fast LLM-free turn filter.

Extracted VERBATIM from core/brain_agent.py (P1.A1 SP-2 Commit 4).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

from core.config import (
    ASSISTANT_TURN_EXTRACT_MIN_CHARS,
    BRAIN_AGENT_MIN_WORDS,
)


_NOISE_WORDS = frozenset({
    "ok", "okay", "yes", "no", "yeah", "nah", "sure", "right",
    "hmm", "uh", "um", "ah", "oh", "huh",
    "thanks", "thank", "you", "bye", "goodbye", "goodnight",
    "hi", "hello", "hey", "alright",
})


class TriageAgent:
    """Fast, LLM-free filter.

    Only user turns with meaningful content pass through — no LLM call,
    no async overhead. Designed to eliminate ~40% of turns before they
    ever reach the extraction LLM.
    """

    def should_process(
        self,
        role: str,
        content: str,
        prior_assistant_turn: str | None = None,
        *,
        room_participant_count: int = 1,
    ) -> tuple[bool, str]:
        # P0.S7.2 Phase 2 — multi-person assistant-turn extraction. Brain
        # responses in multi-person rooms carry topic-bearing content that
        # participants need in their knowledge graphs for cross-session
        # retrieval. D5 min-chars guard filters acknowledgments / KAIROS
        # check-ins / filler.
        if role == "assistant":
            if (
                room_participant_count >= 2
                and len(content or "") >= ASSISTANT_TURN_EXTRACT_MIN_CHARS
            ):
                return True, "multi_person_assistant_turn"
            return False, "assistant turn"
        # Non-user, non-assistant roles (defensive — schema enumerates
        # user/assistant only but guard against future role values).
        if role != "user":
            return False, "assistant turn"

        # Strip the timestamp prefix added by load_conversation_history
        text = content
        if text.startswith("[20"):
            end = text.find("]")
            if end != -1:
                text = text[end + 1:].strip()

        words = [w.strip(".,!?\"'").lower() for w in text.split() if w.strip(".,!?\"'")]

        if len(words) < BRAIN_AGENT_MIN_WORDS:
            # Short answers are meaningful when they're responding to an AI prompt
            if prior_assistant_turn is not None:
                return True, "short answer to ai"
            return False, f"too short ({len(words)} words)"

        if all(w in _NOISE_WORDS for w in words):
            return False, "noise only"

        return True, "ok"
