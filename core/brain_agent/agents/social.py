"""core/brain_agent/agents/social.py — SocialGraphAgent + IdentityAgent.

Extracted VERBATIM from core/brain_agent.py (P1.A1 SP-2 Commit 4).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import httpx
import re

from core.sanitize import wrap_user_input
from core.brain_agent._llm import (
    _call_llm_chat,
    _parse_json,
    _parse_json_array,
)


class SocialGraphAgent:
    """Extracts third-party person mentions from best-friend conversation turns.

    Runs asynchronously after each best-friend user turn. Finds mentions like
    "my friend Ajay who works at TCS" and stores structured records in
    social_mentions so IdentityAgent can later recognise matching strangers.
    """

    _SYSTEM = (
        "Extract third-party person mentions from the conversation text.\n"
        "Return a JSON array (no other text). Each element:\n"
        '  {"name": "string or null", "relationship": "friend/brother/colleague/etc.", '
        '"attributes": ["specific fact 1", "specific fact 2"]}\n\n'
        "Rules:\n"
        "- Only named, real people (no celebrities, public figures, or generic 'someone')\n"
        "- Attributes must be explicitly stated facts, not inferences\n"
        "  Good: 'works at TCS', 'loves cricket', 'lives in Chennai'\n"
        "  Bad: 'seems happy', 'probably rich'\n"
        "- Skip the AI system itself\n"
        "- Return [] if no named people are mentioned"
    )

    def __init__(self, http: httpx.AsyncClient):
        self._http = http

    async def extract(self, turn_text: str) -> list[dict]:
        """Extract person mentions from one conversation turn. Returns [] on failure.

        Session 69 (Bug J): migrated to the shared ``_call_llm_chat`` helper.
        The previous open-coded access to the response's choices array raised
        KeyError on provider error-shaped responses and the bare ``except
        Exception: pass`` hid it — ``[SocialGraph] Extraction error``... was
        all the diagnosis the 2026-04-20 live run produced. The helper
        validates the response shape explicitly and logs with agent context.
        """
        if len(turn_text.split()) < 6:
            return []
        raw = await _call_llm_chat(
            self._http,
            [
                {"role": "system", "content": self._SYSTEM},
                {"role": "user",   "content": wrap_user_input(turn_text[:2000])},
            ],
            agent_name="SocialGraph",
            max_tokens=512,
            temperature=0.0,
            response_format={"type": "json_object"},
            timeout=12.0,
        )
        if raw is None:
            return []
        # P0.12.1 follow-up: P0.12 narrowed _parse_json to dict|None, which
        # silently dropped LLM responses that non-comply with json_object
        # response_format and return a raw top-level array.  Try the dict-
        # wrapper shape first (matches what response_format=json_object asks
        # for), then fall back to _parse_json_array for raw-array responses.
        data = _parse_json(raw)
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    return [m for m in v if isinstance(m, dict) and m.get("name")]
        arr = _parse_json_array(raw)
        if isinstance(arr, list):
            return [m for m in arr if isinstance(m, dict) and m.get("name")]
        return []


# ── IdentityAgent ──────────────────────────────────────────────────────────────

_IDENTITY_STOP = frozenset({
    "i", "me", "my", "we", "you", "your", "the", "a", "an", "is", "are",
    "was", "were", "be", "been", "have", "has", "had", "do", "did", "will",
    "would", "could", "should", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "it", "this", "that", "so", "yeah", "yes", "no", "ok",
    "okay", "hmm", "uh", "just", "like", "know", "think", "really", "well",
    "also", "then", "when", "with", "from", "they", "their", "there",
})


class IdentityAgent:
    """Scores a stranger's conversation against known social mentions.

    Fast and synchronous — keyword overlap only, no API calls.
    Uses a three-tier confidence model:
      IDENTITY_SOFT_THRESHOLD (0.35): inject soft hint into LLM context
      IDENTITY_ASK_THRESHOLD  (0.65): brain asks "are you X?" naturally
      IDENTITY_AUTO_THRESHOLD (0.85): auto-confirm without asking

    Confidence calculation:
    - Extract keywords from all user turns in the stranger's conversation
    - For each social mention, count attribute keywords present in the conversation
    - Require ≥2 distinct keyword matches to avoid trivial false positives
    - confidence = (matched / total_attr_keywords) × quality_factor
    """

    @staticmethod
    def _keywords(text: str) -> set[str]:
        words: set[str] = set()
        for w in re.split(r"[\s,\.!?;:'\"\-]+", text.lower()):
            w = re.sub(r"[^a-z0-9]", "", w)
            if w and len(w) > 2 and w not in _IDENTITY_STOP:
                words.add(w)
        return words

    def score(
        self,
        conversation: list[dict],
        mentions: list[dict],
    ) -> dict | None:
        """Return best identity match or None.

        Result dict: {name, relationship, confidence, matched_attrs, source_person_id}
        """
        if not mentions or not conversation:
            return None

        user_kw: set[str] = set()
        for msg in conversation:
            if msg.get("role") == "user":
                user_kw |= self._keywords(msg["content"])

        if not user_kw:
            return None

        best: dict | None = None
        best_conf = 0.0

        for mention in mentions:
            attrs = mention.get("attributes", [])
            if not attrs:
                continue

            attr_pool: list[str] = []
            for attr in attrs:
                attr_pool.extend(self._keywords(attr))

            if not attr_pool:
                continue

            matched       = [w for w in attr_pool if w in user_kw]
            distinct_count = len(set(matched))

            if distinct_count < 2:
                # Heavily dampened — one keyword match is likely noise
                raw_conf = len(matched) / max(len(attr_pool), 1) * 0.3
            else:
                raw_conf = len(matched) / max(len(attr_pool), 1)
                # Bonus for more distinct keyword hits (diminishing return)
                raw_conf = min(0.95, raw_conf * (1.0 + 0.1 * min(distinct_count, 5)))

            if raw_conf > best_conf:
                best_conf = raw_conf
                matched_attrs = [
                    a for a in attrs
                    if any(w in user_kw for w in self._keywords(a))
                ]
                best = {
                    "name":             mention["name"],
                    "relationship":     mention.get("relationship"),
                    "confidence":       raw_conf,
                    "matched_attrs":    matched_attrs,
                    "source_person_id": mention["source_person_id"],
                }

        return best if best_conf > 0 else None
