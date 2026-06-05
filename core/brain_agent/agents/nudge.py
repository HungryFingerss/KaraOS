"""core/brain_agent/agents/nudge.py — ProactiveNudgeAgent.

Extracted VERBATIM from core/brain_agent.py (P1.A1 SP-2 Commit 4).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import sqlite3
import time
from rapidfuzz import fuzz as _rfuzz

from core.config import (
    CROSS_PERSON_MAX_NUDGES,
    DEFAULT_SYSTEM_NAME,
    EPISODE_TOPIC_MATCH_DAYS,
    NUDGE_EXPIRY_HOURS,
    NUDGE_FUZZY_MATCH_RATIO,
    NUDGE_MIN_CONFIDENCE,
)


class ProactiveNudgeAgent:
    """Generate proactive nudges for cross-person inference, intention follow-ups,
    and memory prompts. All computation is synchronous SQLite + Kuzu reads.

    Nudge types:
      CROSS_PERSON_HYPOTHESIS — "I think I met your cousin"
      INTENTION_FOLLOWUP      — person promised to do X, follow up
      MEMORY_PROMPT           — AI should ask about a high-significance topic
      ROUTINE_DEVIATION       — person is here at unusual time
    """

    def __init__(self, brain_db: "BrainDB", graph_db: "GraphDB"):
        self._db    = brain_db
        self._graph = graph_db

    # ── helpers ───────────────────────────────────────────────────────────────

    def _pending_count(self, person_id: str, nudge_type: str) -> int:
        now = time.time()
        row = self._db._conn.execute(
            """SELECT COUNT(*) FROM proactive_nudges
               WHERE target_person_id = ? AND nudge_type = ?
                 AND injected_at IS NULL AND dismissed_at IS NULL
                 AND (expires_at IS NULL OR expires_at > ?)""",
            (person_id, nudge_type, now),
        ).fetchone()
        return row[0] if row else 0

    def _expires(self) -> float:
        # WALLCLOCK: nudge expiry stored persistently in DB
        return time.time() + NUDGE_EXPIRY_HOURS * 3600

    # ── public interface ──────────────────────────────────────────────────────

    # Values that are never meaningful as cross-person entity names
    _GARBAGE_VALUES: frozenset = frozenset({
        "true", "false", "yes", "no", "1", "0", "none", "null", "unknown",
        "n/a", "na", "undefined", "empty", "other", "various", "multiple",
        "him", "her", "them", "it", "he", "she", "they", "we", "you", "i",
        "this", "that", "the", "a", "an", "and", "or", "but",
    })

    @staticmethod
    def _is_meaningful_entity(name: str, current_person_name: str, system_name: str) -> bool:
        """Return True if an entity name is worth generating a nudge for."""
        v = name.strip().lower()
        if len(v) < 3:
            return False
        if v in ProactiveNudgeAgent._GARBAGE_VALUES:
            return False
        if v == current_person_name.lower():
            return False   # self-reference
        if v == system_name.lower():
            return False   # AI system name
        return True

    def run_cross_person_inference(
        self,
        current_person_id:   str,
        current_person_name: str,
        faces_conn:          sqlite3.Connection,
        system_name:         str = DEFAULT_SYSTEM_NAME,
    ) -> None:
        """Match current person's known entities against other persons' social mentions.

        Algorithm:
        1. Load all other persons' social mentions.
        2. Load current person's knowledge entity values from brain_db.
        3. Fuzzy-match (rapidfuzz) + Kuzu shared-entity check.
        4. For each match above NUDGE_MIN_CONFIDENCE: store CROSS_PERSON_HYPOTHESIS nudge.
        """
        if self._pending_count(current_person_id, "CROSS_PERSON_HYPOTHESIS") >= CROSS_PERSON_MAX_NUDGES:
            return

        all_mentions = self._db.get_all_social_mentions()
        # Only consider mentions from OTHER persons
        other_mentions = [
            m for m in all_mentions
            if m["source_person_id"] != current_person_id
        ]
        if not other_mentions:
            return

        # Current person's known entity values (from brain.db knowledge).
        # Session 106 Phase 3A.5 — exclude system_only tier so embedding
        # hashes / bootstrap_credits / internal diagnostics can't leak
        # into cross-person inference. The raw SELECT here already
        # scopes by person_id (recipient's own rows) so no additional
        # visibility clause is needed for the 3 user-visible tiers —
        # rows are owner-scoped by construction. The system_only
        # exclusion is the one net-new protection this path gets.
        rows = self._db._conn.execute(
            "SELECT DISTINCT value FROM knowledge WHERE person_id = ? "
            "AND invalidated_at IS NULL AND confidence >= 0.50 "
            "AND privacy_level != 'system_only'",
            (current_person_id,),
        ).fetchall()
        current_values = {
            r[0].lower() for r in rows
            if r[0] and self._is_meaningful_entity(r[0], current_person_name, system_name)
        }

        # Also include Kuzu graph facts via find_shared_entities
        try:
            # Resolve source persons' names for Kuzu queries
            source_ids = {m["source_person_id"] for m in other_mentions}
            for src_id in source_ids:
                row = faces_conn.execute(
                    "SELECT name FROM persons WHERE id = ?", (src_id,)
                ).fetchone()
                if not row:
                    continue
                src_name = row[0]
                shared = self._graph.find_shared_entities(
                    current_person_name, src_name
                )
                for s in shared:
                    # Skip garbage entity names (booleans, short strings, self-refs, system name)
                    if not self._is_meaningful_entity(
                        s["entity_name"], current_person_name, system_name
                    ):
                        continue
                    conf = 0.70  # graph match = high confidence
                    rel_raw = next(
                        (m.get("relationship") for m in other_mentions
                         if m["source_person_id"] == src_id),
                        None,
                    )
                    # Bug 3 (2026-04-20): Kuzu can surface an unset relationship
                    # as the string "null" or "None" (from JSON-serialized Python None
                    # on the shadow_persons side). Both are truthy strings — the plain
                    # `if rel` check let "(possibly your null)" through.
                    rel = rel_raw if rel_raw and str(rel_raw).strip().lower() not in ("null", "none", "") else None
                    content = (
                        f"You and someone I've spoken with both mentioned "
                        f"'{s['entity_name']}' — they might be connected to you"
                        + (f" (possibly your {rel})" if rel else "")
                        + "."
                    )
                    if not self._db.nudge_exists(
                        current_person_id, "CROSS_PERSON_HYPOTHESIS", s["entity_name"]
                    ):
                        self._db.store_nudge(
                            target_person_id=current_person_id,
                            nudge_type="CROSS_PERSON_HYPOTHESIS",
                            content=content,
                            confidence=conf,
                            metadata={
                                "entity":           s["entity_name"],
                                "source_person_id": src_id,
                            },
                            expires_at=self._expires(),
                        )
                        print(f"[NudgeAgent] CROSS_PERSON_HYPOTHESIS for {current_person_name}: {content}")
        except Exception as e:
            print(f"[NudgeAgent] Kuzu cross-person error: {e}")

        # Fuzzy name match: other mention names vs current person's known values
        for mention in other_mentions:
            m_name = mention["name"].lower()
            if not m_name:
                continue
            # Skip garbage mention names
            if not self._is_meaningful_entity(m_name, current_person_name, system_name):
                continue
            best_ratio = 0
            matched_val = ""
            for val in current_values:
                ratio = _rfuzz.ratio(m_name, val)
                if ratio > best_ratio:
                    best_ratio, matched_val = ratio, val
            if best_ratio >= NUDGE_FUZZY_MATCH_RATIO:
                conf = (best_ratio / 100) * 0.75
                if conf < NUDGE_MIN_CONFIDENCE:
                    continue
                rel_raw = mention.get("relationship")
                # Bug 3: same null-string leak as the graph-match branch above.
                rel = rel_raw if rel_raw and str(rel_raw).strip().lower() not in ("null", "none", "") else None
                content = (
                    f"Someone I've spoken with mentioned someone called '{mention['name']}'"
                    + (f" ({rel})" if rel else "")
                    + f" — similar to '{matched_val}' you mentioned. Might be the same person."
                )
                if not self._db.nudge_exists(
                    current_person_id, "CROSS_PERSON_HYPOTHESIS", mention["name"]
                ):
                    self._db.store_nudge(
                        target_person_id=current_person_id,
                        nudge_type="CROSS_PERSON_HYPOTHESIS",
                        content=content,
                        confidence=conf,
                        metadata={
                            "mentioned_name":    mention["name"],
                            "matched_value":     matched_val,
                            "source_person_id":  mention["source_person_id"],
                            "fuzzy_ratio":       best_ratio,
                        },
                        expires_at=self._expires(),
                    )
                    print(f"[NudgeAgent] CROSS_PERSON_HYPOTHESIS for {current_person_name}: {content}")

    def run_intention_followup(self, person_id: str, person_name: str) -> None:
        """Surface old unfollowed promises from recent episodes."""
        cutoff = time.time() - EPISODE_TOPIC_MATCH_DAYS * 86400
        episodes = self._db.get_recent_episodes(person_id, limit=10)
        now = time.time()
        for ep in episodes:
            # Only follow up on sessions older than 24h but within retention window
            age_h = (now - ep["session_end_ts"]) / 3600
            if age_h < 24 or ep["session_end_ts"] < cutoff:
                continue
            for promise in ep.get("promises_made") or []:
                if not promise:
                    continue
                content = f"Last time, you mentioned: '{promise}' — worth checking in on."
                if not self._db.nudge_exists(person_id, "INTENTION_FOLLOWUP", promise[:40]):
                    self._db.store_nudge(
                        target_person_id=person_id,
                        nudge_type="INTENTION_FOLLOWUP",
                        content=content,
                        confidence=0.60,
                        metadata={"promise": promise, "session_end_ts": ep["session_end_ts"]},
                        expires_at=self._expires(),
                    )
                    print(f"[NudgeAgent] INTENTION_FOLLOWUP for {person_name}: {promise[:60]}")

    def run_memory_prompts(self, person_id: str, person_name: str) -> None:
        """Generate nudges for high-significance episode topics not discussed recently."""
        episodes = self._db.get_recent_episodes(person_id, limit=5)
        if not episodes:
            return
        # Find high-significance sessions with topics worth revisiting
        now = time.time()
        for ep in episodes:
            if ep["significance"] < 0.70:
                continue
            age_h = (now - ep["session_end_ts"]) / 3600
            if age_h < 48:  # too recent, not worth prompting yet
                continue
            topics = ep.get("key_topics") or []
            for topic in topics[:2]:
                content = f"You previously talked about '{topic}' in depth — worth revisiting if the moment fits."
                if not self._db.nudge_exists(person_id, "MEMORY_PROMPT", topic[:40]):
                    self._db.store_nudge(
                        target_person_id=person_id,
                        nudge_type="MEMORY_PROMPT",
                        content=content,
                        confidence=0.50,
                        metadata={"topic": topic, "significance": ep["significance"]},
                        expires_at=self._expires(),
                    )
                    print(f"[NudgeAgent] MEMORY_PROMPT for {person_name}: {topic}")
