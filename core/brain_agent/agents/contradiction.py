"""core/brain_agent/agents/contradiction.py — ContradictionAgent.

Extracted VERBATIM from core/brain_agent.py (P1.A1 SP-2 Commit 4).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import httpx

from core.sanitize import wrap_user_input
from core.config import (
    OLLAMA_MODEL,
    OLLAMA_URL,
    PREDICATE_VOLATILITY_THRESHOLD,
)
from core.brain_agent._llm import _call_llm_chat
from core.brain_agent.privacy import _is_safety_critical_attribute


_CONTRA_PROMPT = """\
Stored fact: {entity}.{attribute} = "{old_value}"
New fact:    {entity}.{attribute} = "{new_value}"
{volatility_note}
Does the NEW fact REPLACE the stored fact (the person changed or corrected it),
or are they COMPATIBLE (both can be true — different times, contexts, or details)?

Reply with exactly:
REPLACE   (if the new fact supersedes the old one)
COMPATIBLE (if both can coexist)

Then one sentence of rationale on the next line.\
"""

# A-MEM retroactive staleness check (Item 4):
# Used after a REPLACE event to re-evaluate related facts about the same entity.
_STALENESS_PROMPT = """\
A fact about {entity} was just updated:
  {changed_attribute}: "{old_value}" → "{new_value}"

Related stored fact: {entity}.{related_attribute} = "{related_value}"

Is the related fact now:
  STALE       — less certain, probably needs updating (reduce confidence)
  INVALIDATED — certainly no longer true (hard invalidate)
  UNCHANGED   — still valid regardless of the change

Reply with exactly one word (STALE, INVALIDATED, or UNCHANGED), then one sentence of rationale.\
"""


class ContradictionAgent:
    """LLM-powered contradiction detector.

    Called only when a new extraction shares an (entity, attribute) pair with
    a stored fact. Returns whether to replace or keep both.
    """

    def __init__(self, http: httpx.AsyncClient):
        self._http = http

    async def check(
        self,
        entity: str,
        attribute: str,
        old_value: str,
        new_value: str,
        contradiction_count: int = 0,
    ) -> tuple[bool, str]:
        """Returns (should_replace, rationale).

        contradiction_count: historical REPLACE events for this predicate.
        When ≥ PREDICATE_VOLATILITY_THRESHOLD the prompt notes the field is volatile.
        """
        if old_value.strip().lower() == new_value.strip().lower():
            return False, "identical values"

        # Session 105 Bug N — safety-critical attribute blacklist. Crisis
        # disclosures ("expressed_suicidal_thoughts", "mentioned_self_harm",
        # etc.) must be APPEND-ONLY — never overwritten by a later mood
        # update. 2026-04-23 canary had Lexi's suicidal-ideation fact get
        # REPLACED with current_mood='loving' four turns later, erasing a
        # safety-critical disclosure before best_friend could be alerted.
        # Extraction emits the historical flag alongside momentary mood;
        # this pre-check keeps the historical flag out of the contradiction
        # loop entirely so it accumulates as a timestamped history instead
        # of a single overwritable slot. Zero LLM cost on these checks.
        if _is_safety_critical_attribute(attribute):
            return False, "safety-critical — append, never replace"

        volatility_note = (
            f"[Note: '{attribute}' has been corrected {contradiction_count} times historically"
            f" — this is a volatile field; the new value likely supersedes the old one.]"
            if contradiction_count >= PREDICATE_VOLATILITY_THRESHOLD
            else ""
        )
        prompt = _CONTRA_PROMPT.format(
            entity=entity, attribute=attribute,
            old_value=old_value, new_value=new_value,
            volatility_note=volatility_note,
        )

        text = await self._call_together(prompt) or await self._call_ollama(prompt)
        if not text:
            return False, "check failed — keeping both"

        lines = text.strip().splitlines()
        verdict   = lines[0].strip().upper() if lines else ""
        rationale = lines[1].strip() if len(lines) > 1 else ""
        return verdict == "REPLACE", rationale

    async def _call_together(self, prompt: str) -> str | None:
        """Session 90 Bug 2: migrated to the shared ``_call_llm_chat`` helper.
        The previous inline ``try/except Exception`` wrapper produced the
        silent ``[ContradictionAgent] error: ReadTimeout:`` (empty message,
        no retry) observed in the 2026-04-22 multi-convo live run — exact
        same failure mode as Session 69 Bug M on PromptPrefAgent. Helper
        provides: retry-with-exponential-backoff on transient errors
        (ReadTimeout, ConnectTimeout, NetworkError, 5xx), no retry on
        4xx (except 429), explicit 'choices' shape validation, and the
        ``(no detail)`` fallback for empty-message exceptions. Covers BOTH
        ``check`` and ``check_staleness`` since they both delegate here."""
        return await _call_llm_chat(
            self._http,
            [{"role": "user", "content": wrap_user_input(prompt)}],
            agent_name="ContradictionAgent",
            max_tokens=80,
            temperature=0.0,
            timeout=10.0,
        )

    async def check_staleness(
        self,
        entity: str,
        related_attribute: str,
        related_value: str,
        changed_attribute: str,
        old_value: str,
        new_value: str,
    ) -> tuple[str, str]:
        """Re-evaluate a related fact after a REPLACE event (A-MEM Item 4).

        Returns (verdict, rationale) where verdict is STALE / INVALIDATED / UNCHANGED.
        Used by BrainOrchestrator._retroactive_scan().
        """
        prompt = _STALENESS_PROMPT.format(
            entity=entity,
            changed_attribute=changed_attribute,
            old_value=old_value,
            new_value=new_value,
            related_attribute=related_attribute,
            related_value=related_value,
        )
        text = await self._call_together(prompt) or await self._call_ollama(prompt)
        if not text:
            return "UNCHANGED", "check failed"
        lines   = text.strip().splitlines()
        verdict = lines[0].strip().upper() if lines else "UNCHANGED"
        rationale = lines[1].strip() if len(lines) > 1 else ""
        if verdict not in ("STALE", "INVALIDATED", "UNCHANGED"):
            return "UNCHANGED", rationale
        return verdict, rationale

    async def _call_ollama(self, prompt: str) -> str | None:
        try:
            resp = await self._http.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model":   OLLAMA_MODEL,
                    "messages":[{"role": "user", "content": wrap_user_input(prompt)}],
                    "stream":  False,
                    "options": {"temperature": 0.0},
                },
                timeout=20.0,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except Exception as e:
            print(f"[ContradictionAgent] Ollama error: {e}")
            return None
