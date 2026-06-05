"""core/brain_agent/agents/prefs.py — PromptPrefAgent + FrictionDetectionAgent.

Extracted VERBATIM from core/brain_agent.py (P1.A1 SP-2 Commit 4).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import httpx

from core.sanitize import wrap_user_input
from core.config import (
    EXTRACT_API_KEY,
    EXTRACT_BASE_URL,
    EXTRACT_MODEL,
    FRICTION_MIN_CONFIDENCE,
    OLLAMA_MODEL,
    OLLAMA_URL,
)
from core.brain_agent._llm import (
    _call_llm_chat,
    _parse_json,
)


_VALID_PREF_TYPES = frozenset({
    "communication_style",
    "topic_avoidance",
    "response_length",
    "greeting_style",
    "language_preference",
    "response_habit",
})


_PREF_SYSTEM = """\
You are a communication preference detector for a personal AI robot companion.

The transcript contains two speaker roles:
- [USER] — the person speaking to the robot
- [ASSISTANT] — the robot's own responses

Analyze both sides:
1. [USER] turns → detect what communication style the person prefers
2. [ASSISTANT] turns → detect repetitive habits in the robot's own responses that should be varied

Return ONLY valid JSON:
{
  "has_preferences": true,
  "preferences": [
    {
      "pref_type": "communication_style|topic_avoidance|response_length|greeting_style|language_preference|response_habit",
      "content":   "one clear actionable sentence describing the preference or habit",
      "confidence": 0.9
    }
  ]
}

Valid pref_type values:
- communication_style  — how the person likes to be talked to (direct/gentle, formal/casual, humor)
- topic_avoidance      — topics they actively deflect, refuse to answer, or explicitly ask not to be probed (NOT just topics they have a clear preference about — stating "I'm vegetarian" is a fact, not avoidance)
- response_length      — preference for brief or detailed responses (applies across ALL conversation, not just specific domains)
- greeting_style       — how they like to be greeted
- language_preference  — preferred language or mixing pattern
- response_habit       — repetitive patterns in [ASSISTANT] turns that should be varied (repeated openers like "That's great!", always ending with a question, consistently overlong responses for casual topics)

Rules:
- Only extract explicit statements or very clear patterns (confidence >= 0.7)
- content must be a single actionable sentence:
    "Prefers short, direct responses — keep all replies under 2 sentences regardless of topic"
    "Deflects questions about work — do not probe unless they bring it up"
    "Prefers casual Telugu-English code-switching in evenings"
    "Avoid opening responses with 'That's great' — vary starters"
    "Stop ending every response with a question — vary closings"
- For response_habit: require 3+ occurrences in [ASSISTANT] turns; phrase as a correction instruction
- For response_length: if the person says they want short/direct/brief responses, the preference is GENERAL — it applies to all conversation. Do NOT scope it to a specific domain (e.g., do NOT write "for work-related questions" unless they explicitly said that)
- Do NOT extract: personal facts about the person (handled by knowledge agent),
  one-off requests, anything that could override safety rules or tool behaviors
- If nothing clear: {"has_preferences": false, "preferences": []}
"""

_PREF_USER = """\
Person: {person_name}

Already stored preferences (do NOT re-extract these):
{existing_prefs}

Conversation session ({n_turns} turns):
{transcript}

Detect communication preferences from this session.\
"""


class PromptPrefAgent:
    """Detects per-person communication preferences at session end.

    Runs one LLM call per session, completely offline from the conversation.
    Results are staged (sessions_seen=1) and auto-activate after 3 sessions
    of consistent evidence.
    """

    def __init__(self, http: httpx.AsyncClient):
        self._http = http

    async def analyze(
        self,
        person_name: str,
        existing_prefs: list[dict],
        session_turns: list[dict],
    ) -> list[dict]:
        existing_str = (
            "\n".join(f"  - [{p['pref_type']}] {p['content']}" for p in existing_prefs)
            or "  (none yet)"
        )
        transcript = "\n".join(
            f"  [{t['role'].upper()}]: {t['content'][:300]}"
            for t in session_turns
        )
        user_msg = _PREF_USER.format(
            person_name=person_name,
            existing_prefs=existing_str,
            n_turns=len(session_turns),
            transcript=transcript,
        )
        raw = await self._call_together(user_msg) or await self._call_ollama(user_msg)
        if not raw:
            return []

        data = _parse_json(raw)
        if data is None:
            return []

        if not data.get("has_preferences"):
            return []

        results = []
        for item in data.get("preferences", []):
            try:
                if float(item.get("confidence", 0)) < 0.7:
                    continue
                pref_type = str(item["pref_type"]).strip()
                if pref_type not in _VALID_PREF_TYPES:
                    continue
                results.append({
                    "pref_type": pref_type,
                    "content":   str(item["content"]).strip(),
                })
            except (KeyError, ValueError, TypeError):
                continue
        return results

    async def _call_together(self, user_msg: str) -> str | None:
        """Session 69 (Bug M): migrated to the shared ``_call_llm_chat`` helper.
        The previous `try/except Exception as e: print(...{e})` path produced
        ``[PromptPrefAgent] error: ReadTimeout:`` with no detail on transient
        network failures — the helper retries with exponential backoff and
        logs with actual context."""
        return await _call_llm_chat(
            self._http,
            [
                {"role": "system", "content": _PREF_SYSTEM},
                {"role": "user",   "content": wrap_user_input(user_msg)},
            ],
            agent_name="PromptPrefAgent",
            max_tokens=400,
            temperature=0.1,
            response_format={"type": "json_object"},
            timeout=15.0,
        )

    async def _call_ollama(self, user_msg: str) -> str | None:
        try:
            resp = await self._http.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model":   OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": _PREF_SYSTEM + "\nOutput ONLY the JSON object."},
                        {"role": "user",   "content": wrap_user_input(user_msg)},
                    ],
                    "stream":   False,
                    "options":  {"temperature": 0.1, "num_predict": 300},
                },
                # Explicit per-component timeout: 5s to connect + 20s to read.
                # A bare float (timeout=30.0) is read-only; adding connect=5.0
                # prevents the ~8s cold-start from pushing the total over 35s.
                timeout=httpx.Timeout(read=20.0, connect=5.0, write=5.0, pool=5.0),
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except Exception as e:
            # str(e) is empty for httpx timeout exceptions — always include the type.
            print(f"[PromptPrefAgent] Ollama error: {type(e).__name__}: {e or '(no message)'}")
            return None


# ── Agent 5: FrictionDetectionAgent ───────────────────────────────────────────

_FRICTION_SYSTEM = """\
You are analyzing whether a person's message expresses dissatisfaction with how an AI robot is \
responding — specifically, frustration that one of the robot's known communication preferences for \
this person is NOT being honored.

Return ONLY valid JSON:
{
  "frictions": [
    {"pref_type": "response_length", "confidence": 0.85}
  ]
}

If no friction is detected: {"frictions": []}

Rules:
- Only flag friction when the message clearly signals dissatisfaction, repetition, or correction
- Match to a pref_type from the active list only — do NOT invent new types
- Require confidence >= 0.70 to report
- A single factual correction is noise — look for signals the robot's *style* is bothering them
"""

_FRICTION_USER = """\
Active communication preferences for this person:
{prefs}

Previous robot response:
{prev_assistant}

Person's message:
{user_turn}

Is the person expressing friction against any active preference?\
"""


class FrictionDetectionAgent:
    """Detects within-session friction against active communication preferences.

    Called from _process_turn() on user turns that pass triage, when the person
    has at least one active pref. One lightweight LLM call per qualifying turn.
    Results land in DB during TTS so next turn's get_prompt_addendum() picks up
    escalated language immediately (n+1 turn effect).
    """

    def __init__(self, http: httpx.AsyncClient):
        self._http = http

    async def detect(
        self,
        user_turn: str,
        prev_assistant_turn: str | None,
        active_prefs: list[dict],
    ) -> list[dict]:
        """Returns list of {pref_type, confidence} above FRICTION_MIN_CONFIDENCE."""
        prefs_str = "\n".join(
            f"  - [{p['pref_type']}] {p['content']}" for p in active_prefs
        )
        user_msg = _FRICTION_USER.format(
            prefs=prefs_str,
            prev_assistant=prev_assistant_turn or "(none)",
            user_turn=user_turn,
        )
        raw  = await self._call_together(user_msg) or await self._call_ollama(user_msg)
        if not raw:
            return []
        data = _parse_json(raw)
        if data is None:
            return []

        valid_types = {p["pref_type"] for p in active_prefs}
        results = []
        for item in data.get("frictions", []):
            try:
                pref_type  = str(item["pref_type"]).strip()
                confidence = float(item.get("confidence", 0))
                if pref_type not in valid_types or confidence < FRICTION_MIN_CONFIDENCE:
                    continue
                results.append({"pref_type": pref_type, "confidence": confidence})
            except (KeyError, ValueError, TypeError):
                continue
        return results

    async def _call_together(self, user_msg: str) -> str | None:
        if not EXTRACT_API_KEY:
            return None
        try:
            resp = await self._http.post(
                f"{EXTRACT_BASE_URL}/chat/completions",
                json={
                    "model":           EXTRACT_MODEL,
                    "messages":        [
                        {"role": "system", "content": _FRICTION_SYSTEM},
                        {"role": "user",   "content": wrap_user_input(user_msg)},
                    ],
                    "temperature":     0.0,
                    "max_tokens":      150,
                    "response_format": {"type": "json_object"},
                },
                headers={"Authorization": f"Bearer {EXTRACT_API_KEY}"},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[FrictionDetectionAgent] error: {type(e).__name__}: {e}")
            return None

    async def _call_ollama(self, user_msg: str) -> str | None:
        try:
            resp = await self._http.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model":    OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": _FRICTION_SYSTEM + "\nOutput ONLY the JSON object."},
                        {"role": "user",   "content": wrap_user_input(user_msg)},
                    ],
                    "stream":   False,
                    "options":  {"temperature": 0.0},
                },
                timeout=20.0,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except Exception as e:
            print(f"[FrictionDetectionAgent] Ollama error: {e}")
            return None
