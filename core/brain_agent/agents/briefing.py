"""core/brain_agent/agents/briefing.py — BriefingAgent + ConversationInsightAgent.

Extracted VERBATIM from core/brain_agent.py (P1.A1 SP-2 Commit 4).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import httpx
import math
import time

from core.config import (
    EXTRACT_API_KEY,
    EXTRACT_BASE_URL,
    EXTRACT_MODEL,
    INSIGHT_MAX_TOKENS,
)
from core.brain_agent._llm import _parse_json


class BriefingAgent:
    """Generate a warm spoken briefing for the best friend after a long absence.

    Scores stranger visits and silent observations by relevance
    (recency × relationship_match × significance), picks the top 3 most
    interesting events, and produces a 1–2 sentence spoken summary.
    """

    _SYSTEM = (
        "You are giving a brief, warm spoken update to someone who just got home. "
        "Keep it to 1–2 natural sentences. No bullet points, no headings. "
        "Only mention events that are worth saying out loud. "
        "If nothing interesting happened, return exactly the word: null"
    )
    _SCORE_THRESHOLD = 0.12

    def __init__(self, http: httpx.AsyncClient):
        self._http = http

    @staticmethod
    def _score(event: dict, social_names: set[str]) -> float:
        now = time.time()
        age_hours  = max(0.0, (now - event.get("last_seen", now)) / 3600)
        recency    = math.exp(-age_hours / 12)
        name       = (event.get("name") or "").lower()
        had_convo  = event.get("had_convo", False)
        frames     = event.get("frame_count", 1)
        matched    = name and name != "visitor" and name in social_names
        rel_weight = 1.5 if matched else (0.8 if had_convo else 0.4)
        significance = 1.0 if had_convo else min(1.0, frames / 50)
        return recency * rel_weight * significance

    async def generate(
        self,
        bf_name:         str,
        stranger_visits: list[dict],
        silent_obs:      list[dict],
        social_mentions: list[dict],
    ) -> str | None:
        social_names = {(m.get("name") or "").lower() for m in social_mentions}

        events: list[dict] = []
        for sv in stranger_visits:
            events.append({**sv, "had_convo": True})
        for obs in silent_obs:
            events.append({**obs, "had_convo": False})

        if not events:
            return None

        scored = [(self._score(e, social_names), e) for e in events]
        top = [
            e for _, e in sorted(scored, key=lambda x: x[0], reverse=True)
            if _ >= self._SCORE_THRESHOLD
        ][:3]

        if not top:
            return None

        now = time.time()
        lines: list[str] = []
        for e in top:
            age_h = max(0.0, (now - e.get("last_seen", now)) / 3600)
            if age_h < 0.1:
                age_str = "just now"
            elif age_h < 24:
                age_str = f"{int(age_h)}h ago"
            else:
                age_str = f"{int(age_h // 24)}d ago"

            if e["had_convo"]:
                name = e.get("name") or "an unnamed visitor"
                lines.append(f"- {name} visited and spoke with me ({age_str})")
            else:
                frames = e.get("frame_count", 1)
                zone   = e.get("zone") or "the area"
                lines.append(f"- An unidentified face was seen in {zone} ({frames} frames, {age_str})")

        prompt = (
            f"{bf_name} just got home after being away. "
            f"Here is what happened while they were away:\n"
            + "\n".join(lines)
            + "\n\nGenerate a warm 1–2 sentence spoken briefing. "
            "Return null if nothing is worth mentioning."
        )

        try:
            resp = await self._http.post(
                f"{EXTRACT_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {EXTRACT_API_KEY}"},
                json={
                    "model":       EXTRACT_MODEL,
                    "messages":    [
                        {"role": "system", "content": self._SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                    "max_tokens":  120,
                    "temperature": 0.7,
                },
            )
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            if raw.lower() in ("null", "none", ""):
                return None
            return raw
        except Exception as e:
            print(f"[BriefingAgent] generate error: {e}")
            return None


# ── ConversationInsightAgent ───────────────────────────────────────────────────

class ConversationInsightAgent:
    """Generate a structured episode summary at session end.

    One LLM call per session for any person (best_friend, known, stranger).
    Output feeds BriefingAgent, ProactiveNudgeAgent, and greeting context.
    Never blocks the conversation pipeline — runs as a fire-and-forget task.
    """

    _SYSTEM = (
        "You are analyzing a completed conversation session. "
        "Return ONLY valid JSON (no markdown, no extra text):\n"
        '{"mood":"one word: stressed/excited/neutral/happy/sad/anxious/tired",'
        '"key_topics":["topic1","topic2"],'
        '"promises_made":["I will call you back",...],'
        '"questions_asked":["What time is the meeting?",...],'
        '"emotional_arc":"one sentence describing emotional tone evolution",'
        '"significance_score":0.7}\n'
        "Rules: key_topics 1-5 concrete topics; significance_score 0.0=small talk "
        "1.0=major life event; null for absent fields."
    )

    def __init__(self, http: httpx.AsyncClient):
        self._http = http

    async def analyze(
        self,
        person_name:      str,
        turns:            list[dict],
        session_start_ts: float,
        session_end_ts:   float,
    ) -> dict | None:
        if not EXTRACT_API_KEY:
            return None
        transcript = "\n".join(
            f"{t['role'].upper()}: {t['content']}"
            for t in turns
        )[:3000]
        prompt = (
            f"Conversation with {person_name} "
            f"(duration: {int(session_end_ts - session_start_ts)}s):\n\n"
            + transcript
            + "\n\nGenerate the episode JSON."
        )
        try:
            resp = await self._http.post(
                f"{EXTRACT_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {EXTRACT_API_KEY}"},
                json={
                    "model":           EXTRACT_MODEL,
                    "messages":        [
                        {"role": "system", "content": self._SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                    "max_tokens":      INSIGHT_MAX_TOKENS,
                    "temperature":     0.2,
                    "response_format": {"type": "json_object"},
                },
            )
            raw = resp.json()["choices"][0]["message"]["content"]
            return _parse_json(raw)
        except Exception as e:
            print(f"[InsightAgent] analyze error: {e}")
            return None
