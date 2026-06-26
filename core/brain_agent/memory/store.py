"""core/brain_agent/memory/store.py — BrainDB — brain.db knowledge store + schema-version tracking + pref-escalation helper.

Extracted VERBATIM from core/brain_agent.py (P1.A1 SP-2 SP-3).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import datetime
import json
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
import numpy as np

from core.config import (
    BRAIN_DB_PATH,
    CONFIDENCE_BOOST,
    CORE_MEMORY_ATTRIBUTES,
    CORE_MEMORY_ENABLED,
    CORE_MEMORY_MAX_FACTS,
    CORE_MEMORY_MIN_CONFIDENCE,
    EMBED_MIN_CONFIDENCE,
    EMBED_TOP_K,
    KNOWLEDGE_HARD_DELETE_AFTER_DAYS,
    PREF_AUTO_CONFIRM_THRESHOLD,
    PRIVACY_LEVEL_DEFAULT,
    SHADOW_NAME_BLOCKLIST,
)
from core.log_utils import _now_log_ts
from core.brain_agent._llm import _valid_until
from core.brain_agent.privacy import (
    _assert_valid_privacy_level,
    _visibility_clause,
)
from core.brain_agent.context import (
    _cosine_similarity,
    _decayed_confidence,
    _format_context_lines,
)
from core.brain_agent.agents.extraction import Extraction

from core import config  # SB.5 Step-2: live attribute access for RETENTION_MODE gate (from-import-trap)


def _escalate_pref(content: str, friction_count: int) -> str:
    """Apply escalating urgency language to a pref based on how many times friction was detected."""
    if friction_count == 0:
        return content
    if friction_count <= 2:
        return f"[important] {content}"
    return f"[STRICT — repeated friction] {content}"


class BrainDB:
    """Manages brain.db — the self-organized knowledge store.

    Separate from faces.db so it can be wiped independently and opened
    by the brain agent without touching the main pipeline's DB connection.
    """

    # P0.9.2 Phase 2: retrofit migrations live in core/brain_db_migrations.py.
    # Each entry is a 5-tuple (version, description, apply_fn,
    # verify_post_fn, verify_present_fn).
    from core.brain_db_migrations import MIGRATIONS as _M
    MIGRATIONS: list = _M
    del _M

    def __init__(self, path: Path = BRAIN_DB_PATH):
        # P0.9.1 Imp-1: IMMEDIATE isolation prevents Python auto-BEGIN
        # (DEFERRED by default) from clashing with explicit BEGIN IMMEDIATE
        # used by BrainDB.transaction() and core.schema_migrations runner.
        self._conn = sqlite3.connect(
            str(path), check_same_thread=False,
            isolation_level="IMMEDIATE",
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_tables()
        self._migrate()
        # P0.9.1 Phase 1: ledger + pending-migration runner.  The existing
        # _migrate() above handles the ad-hoc PRAGMA-guarded ALTERs (Phase 2
        # converts these to versioned MIGRATIONS entries).  This block adds
        # the schema_migrations ledger so future migrations land there.
        from core.schema_migrations import (
            init_ledger as _il, bootstrap_ledger_if_unversioned as _bl,
            apply_migrations as _am,
        )
        _il(self._conn)
        _bl(
            self._conn,
            baseline_description="brain.db initial baseline (pre-P0.9)",
            migrations=self.MIGRATIONS,
            db_label="brain.db",
        )
        _am(self._conn, self.MIGRATIONS, db_label="brain.db")

    def _safe_commit(self) -> None:
        """Commit only when a transaction is actually open.

        Bug 2 (2026-04-20 live run) + Obs 2 hardening (2026-04-20 post-review):
        Concurrent async session-end tasks race on ``commit()`` — when one task
        commits and the next arrives before any new write starts a fresh
        transaction, SQLite raises ``OperationalError: cannot commit - no
        transaction is active``. The error is harmless (first commit already
        persisted both tasks' intent) but aborts the brain loop.

        Using ``conn.in_transaction`` instead of string-matching the error
        message is deterministic and survives SQLite version/locale changes.
        A genuine ``OperationalError`` (disk full, constraint violation, locked
        DB) still propagates — we only skip the commit when there's nothing
        to commit.
        """
        if self._conn.in_transaction:
            self._conn.commit()
        # else: no-op — nothing to commit

    @contextmanager
    def transaction(self):
        """Wrap a multi-step write block in BEGIN IMMEDIATE / COMMIT with rollback on exception.

        Uses BEGIN IMMEDIATE to acquire the write lock upfront — prevents SQLITE_BUSY
        mid-transaction if a reader holds the connection.

        Callers must NOT call self._conn.commit() inside the with-block; the context
        manager owns commit/rollback. Helpers called from within this block detect
        they're inside an outer transaction via self._conn.in_transaction (True after
        BEGIN IMMEDIATE) and skip their own inner commits.
        """
        prev_isolation = self._conn.isolation_level
        self._conn.isolation_level = None  # autocommit — prevents Python auto-BEGIN clash
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield
                self._conn.execute("COMMIT")
            except Exception:
                # P0.9.1 Imp-2: tightened rollback — re-raise unexpected
                # OperationalErrors instead of swallowing every Exception.
                # Only the S65 "no transaction is active" race is suppressed.
                try:
                    self._conn.execute("ROLLBACK")
                except sqlite3.OperationalError as _rbe:
                    if "no transaction is active" not in str(_rbe).lower():
                        print(f"[BrainDB] rollback failed unexpectedly: {_rbe!r}")
                        raise
                    # else: # RACE: S65 — known race, suppress
                raise
        finally:
            self._conn.isolation_level = prev_isolation

    def _init_tables(self) -> None:
        self._conn.executescript("""
            -- Tracks which conversation_log turn the brain last processed.
            -- Single row, always present.
            CREATE TABLE IF NOT EXISTS brain_state (
                singleton    INTEGER PRIMARY KEY DEFAULT 1,
                last_turn_id INTEGER NOT NULL DEFAULT 0,
                updated_at   REAL    NOT NULL DEFAULT 0
            );
            INSERT OR IGNORE INTO brain_state (singleton, last_turn_id, updated_at)
            VALUES (1, 0, 0);

            -- Core knowledge store.
            -- The LLM decides entity/attribute names — that IS the schema freedom.
            -- invalidated_at IS NULL means the fact is currently valid.
            CREATE TABLE IF NOT EXISTS knowledge (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                source_turn_id INTEGER NOT NULL,
                person_id      TEXT,
                entity         TEXT    NOT NULL,
                entity_type    TEXT    NOT NULL,
                attribute      TEXT    NOT NULL,
                value          TEXT    NOT NULL,
                confidence     REAL    NOT NULL,
                is_temporal    INTEGER NOT NULL DEFAULT 0,
                valid_until    REAL,
                invalidated_at REAL,
                invalidated_by INTEGER,
                agent          TEXT    NOT NULL,
                created_at     REAL    NOT NULL,
                privacy_level  TEXT    NOT NULL DEFAULT 'public'
            );
            CREATE INDEX IF NOT EXISTS idx_knowledge_entity
                ON knowledge(entity, attribute)
                WHERE invalidated_at IS NULL;

            -- Meta-schema catalog: every attribute name the LLM has ever invented.
            -- Used later for schema normalization and retrieval routing.
            CREATE TABLE IF NOT EXISTS schema_catalog (
                attribute     TEXT PRIMARY KEY,
                entity_type   TEXT NOT NULL,
                example_value TEXT,
                use_count     INTEGER NOT NULL DEFAULT 1,
                first_seen_at REAL    NOT NULL,
                last_used_at  REAL    NOT NULL
            );

            -- Full audit trail of every agent decision.
            -- Critical for debuggability: when something is wrong, trace back here.
            CREATE TABLE IF NOT EXISTS agent_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                turn_id     INTEGER,
                agent       TEXT NOT NULL,
                decision    TEXT NOT NULL,
                rationale   TEXT,
                items       INTEGER DEFAULT 0,
                duration_ms REAL,
                ts          REAL NOT NULL
            );

            -- Per-person communication preferences learned over sessions.
            -- Staged by default (sessions_seen=1, confirmed=0).
            -- Auto-activates after sessions_seen >= PREF_AUTO_CONFIRM_THRESHOLD, or immediately
            -- when source='human'.
            CREATE TABLE IF NOT EXISTS prompt_prefs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id     TEXT NOT NULL,
                pref_type     TEXT NOT NULL,
                content       TEXT NOT NULL,
                source        TEXT NOT NULL DEFAULT 'prompt_agent',
                sessions_seen INTEGER NOT NULL DEFAULT 1,
                confirmed     INTEGER NOT NULL DEFAULT 0,
                created_at    REAL NOT NULL,
                expires_at    REAL
            );
            CREATE INDEX IF NOT EXISTS idx_prompt_prefs_person_id
                ON prompt_prefs(person_id);

            -- LLM-generated questions about object patterns, queued for proactive asking.
            -- pattern_key prevents the same pattern being asked twice.
            CREATE TABLE IF NOT EXISTS object_pattern_questions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                question    TEXT NOT NULL,
                pattern_key TEXT NOT NULL UNIQUE,
                asked       INTEGER NOT NULL DEFAULT 0,
                asked_at    REAL,
                created_at  REAL NOT NULL
            );

            -- Confirmed behavioral patterns learned from user answers.
            CREATE TABLE IF NOT EXISTS object_patterns (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_key TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                confidence  REAL NOT NULL DEFAULT 0.9,
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL
            );

            -- People mentioned by the best friend during conversations.
            -- Used by IdentityAgent to recognise strangers who match.
            CREATE TABLE IF NOT EXISTS social_mentions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                source_person_id TEXT NOT NULL,
                mentioned_name   TEXT NOT NULL,
                relationship     TEXT,
                attributes       TEXT NOT NULL DEFAULT '[]',
                created_at       REAL NOT NULL,
                updated_at       REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_social_mentions_source
                ON social_mentions(source_person_id);

            -- Per-session episode summaries — generated by ConversationInsightAgent.
            CREATE TABLE IF NOT EXISTS episodes (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id        TEXT NOT NULL,
                session_start_ts REAL NOT NULL,
                session_end_ts   REAL NOT NULL,
                mood             TEXT,
                key_topics       TEXT NOT NULL DEFAULT '[]',
                promises_made    TEXT NOT NULL DEFAULT '[]',
                questions_asked  TEXT NOT NULL DEFAULT '[]',
                emotional_arc    TEXT,
                significance     REAL NOT NULL DEFAULT 0.5,
                turn_count       INTEGER NOT NULL DEFAULT 0,
                created_at       REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_episodes_person
                ON episodes(person_id, session_end_ts DESC);

            -- Per-person visit windows — used by RoutineAgent for pattern detection.
            CREATE TABLE IF NOT EXISTS presence_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id    TEXT NOT NULL,
                arrived_at   REAL NOT NULL,
                left_at      REAL NOT NULL,
                duration_s   REAL NOT NULL,
                day_of_week  INTEGER NOT NULL,
                hour_of_day  INTEGER NOT NULL,
                created_at   REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_presence_log_person
                ON presence_log(person_id, arrived_at DESC);

            -- Pending proactive nudges — generated by ProactiveNudgeAgent.
            CREATE TABLE IF NOT EXISTS proactive_nudges (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                target_person_id TEXT NOT NULL,
                nudge_type       TEXT NOT NULL,
                content          TEXT NOT NULL,
                metadata         TEXT NOT NULL DEFAULT '{}',
                confidence       REAL NOT NULL DEFAULT 0.5,
                generated_at     REAL NOT NULL,
                injected_at      REAL,
                dismissed_at     REAL,
                expires_at       REAL
            );
            CREATE INDEX IF NOT EXISTS idx_nudges_person
                ON proactive_nudges(target_person_id, injected_at, dismissed_at, expires_at);

            -- System health and anomaly alerts — generated by WatchdogAgent.
            CREATE TABLE IF NOT EXISTS watchdog_alerts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_type   TEXT NOT NULL,
                severity     TEXT NOT NULL,
                message      TEXT NOT NULL,
                metadata     TEXT NOT NULL DEFAULT '{}',
                resolved     INTEGER NOT NULL DEFAULT 0,
                created_at   REAL NOT NULL,
                resolved_at  REAL
            );
            CREATE INDEX IF NOT EXISTS idx_watchdog_ts
                ON watchdog_alerts(created_at DESC, resolved);

            -- Persistent spatial object memory — every YOLO detection stored here.
            -- Enables "I saw your watch on the left side 7 days ago" recall.
            -- Deduplicated by (object_class, location_zone) within VISION_SIGHTING_GAP seconds.
            CREATE TABLE IF NOT EXISTS object_sightings (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                object_class   TEXT NOT NULL,
                confidence     REAL NOT NULL,
                location_zone  TEXT NOT NULL,
                bbox_cx        REAL NOT NULL,
                bbox_cy        REAL NOT NULL,
                first_seen_at  REAL NOT NULL,
                last_seen_at   REAL NOT NULL,
                times_seen     INTEGER NOT NULL DEFAULT 1,
                person_context TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_object_sightings_class
                ON object_sightings(object_class);
            CREATE INDEX IF NOT EXISTS idx_object_sightings_ts
                ON object_sightings(last_seen_at);

            -- Phase 5: per-predicate contradiction + extraction counters.
            -- High contradiction_count → volatile predicate → ContradictionAgent nudged
            -- to prefer REPLACE, and stored confidence capped at PREDICATE_CONFIDENCE_CAP.
            CREATE TABLE IF NOT EXISTS predicate_stats (
                predicate           TEXT PRIMARY KEY,
                contradiction_count INTEGER NOT NULL DEFAULT 0,
                total_extractions   INTEGER NOT NULL DEFAULT 0,
                updated_at          REAL    NOT NULL DEFAULT 0
            );

            -- Household-scoped facts learned from multi-person conversation.
            -- Scope "household" = shared asset/routine (we/our). Scope "per_person" = individual fact.
            CREATE TABLE IF NOT EXISTS household_facts (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                entity           TEXT    NOT NULL,   -- "household" or person_name
                attribute        TEXT    NOT NULL,
                value            TEXT    NOT NULL,
                scope            TEXT    NOT NULL DEFAULT 'household',
                source_speakers  TEXT    NOT NULL DEFAULT '[]',   -- JSON list of person_ids who stated/corroborated
                confidence       REAL    NOT NULL DEFAULT 0.7,
                conflict_status  TEXT    NOT NULL DEFAULT 'provisional',  -- "settled" | "disputed" | "provisional"
                disputed_values  TEXT,               -- JSON: {"jagan": "7pm", "priya": "8pm"} when disputed
                first_seen       REAL    NOT NULL,
                last_confirmed   REAL    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_household_facts_entity_attr
                ON household_facts(entity, attribute);

            -- Inter-person relationships inferred from conversation.
            CREATE TABLE IF NOT EXISTS inter_person_relationships (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                person_a       TEXT    NOT NULL,
                relationship   TEXT    NOT NULL,   -- "married_to", "parent_of", "colleague_of", etc.
                person_b       TEXT    NOT NULL,   -- may be a free-text name if not enrolled
                confidence     REAL    NOT NULL DEFAULT 0.8,
                source_speaker TEXT,               -- person_id who stated this
                created_at     REAL    NOT NULL,
                updated_at     REAL    NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_relationships_unique
                ON inter_person_relationships(person_a, relationship, person_b);

            -- Shadow nodes for non-enrolled persons mentioned in conversation.
            -- When Priya says "my colleague Anita", we create a shadow node for Anita.
            -- If Anita enrolls later, just add face/voice to the existing node.
            CREATE TABLE IF NOT EXISTS shadow_persons (
                shadow_id          TEXT PRIMARY KEY,
                known_name         TEXT NOT NULL UNIQUE,
                known_via          TEXT NOT NULL DEFAULT '[]',   -- JSON: [{"person_id": "...", "relationship": "..."}]
                face_id            TEXT,                         -- NULL until enrolled
                voice_id           TEXT,                         -- NULL until enrolled
                enrollment_status  TEXT NOT NULL DEFAULT 'pending',
                facts              TEXT NOT NULL DEFAULT '[]',   -- JSON: [{attribute, value, confidence}]
                first_mentioned    REAL NOT NULL,
                last_mentioned     REAL NOT NULL
            );

            -- VISION_ROADMAP P1.7a (Session 85): one row per gated-tool decision
            -- routed through _intent_allows(). Phase 5 drift detection queries
            -- this to compute divergence rate and inspect individual rejections
            -- before flipping INTENT_FALLBACK_TO_REGEX to False. Schema per
            -- VISION_ROADMAP section 5.2.2. Kept wide (nullable where reasonable)
            -- so both classifier-available and classifier-unavailable branches
            -- can record their decision without a second table.
            CREATE TABLE IF NOT EXISTS intent_divergences (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                turn_id                INTEGER,                      -- conversation_log.id reference, nullable when called outside a logged turn
                person_id              TEXT,                         -- the caller whose session made the tool call
                user_text              TEXT,                         -- what the user actually said (ground truth for the gate)
                structured_intent      TEXT,                         -- classifier's turn_intent (NULL when classifier unavail)
                structured_extracted   TEXT,                         -- classifier's extracted_value (NULL if empty or unavail)
                structured_confidence  REAL,                         -- classifier's confidence (NULL when classifier unavail)
                tool_proposed          TEXT NOT NULL,                -- e.g. 'update_person_name'
                gate_decision          TEXT NOT NULL,                -- 'allow' | 'reject: <reason>' | 'regex_fallback_allow' | 'regex_fallback_reject' | 'shadow_sample'
                reviewed               INTEGER NOT NULL DEFAULT 0,   -- 1 once human has audited this row
                ts                     REAL NOT NULL,                -- epoch seconds
                mode                   TEXT NOT NULL DEFAULT 'gate'  -- Phase 5 S119: 'gate' (production decision) | 'shadow' (1% canary sample)
            );
            CREATE INDEX IF NOT EXISTS idx_intent_divergences_ts
                ON intent_divergences(ts DESC);
            CREATE INDEX IF NOT EXISTS idx_intent_divergences_tool
                ON intent_divergences(tool_proposed, ts DESC);
            CREATE INDEX IF NOT EXISTS idx_intent_divergences_mode
                ON intent_divergences(mode, ts DESC);
            -- Phase 3B.6 — room-end synthesis target. One row per room
            -- session written when the last person leaves; drives
            -- greeting enrichment ("It's been 18 hours since you and
            -- Lexi last talked...") without re-running retrieval.
            CREATE TABLE IF NOT EXISTS room_summaries (
                room_session_id  TEXT PRIMARY KEY,
                started_at       REAL NOT NULL,
                ended_at         REAL NOT NULL,
                speaker_pids     TEXT NOT NULL,    -- JSON array
                summary          TEXT NOT NULL,    -- LLM narrative (1-2 sentences) or topic-only fallback
                topic_tags       TEXT,             -- JSON array of entity values
                safety_flags     TEXT,             -- JSON array of {pid,name,attribute} dicts
                created_at       REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_room_summaries_ended
                ON room_summaries(ended_at DESC);
        """)
        self._conn.commit()

    # ── State ──────────────────────────────────────────────────────────────────

    def get_last_turn_id(self) -> int:
        return self._conn.execute(
            "SELECT last_turn_id FROM brain_state WHERE singleton = 1"
        ).fetchone()[0]

    def set_last_turn_id(self, turn_id: int) -> None:
        self._conn.execute(
            "UPDATE brain_state SET last_turn_id = ?, updated_at = ? WHERE singleton = 1",
            (turn_id, time.time()),
        )
        self._conn.commit()

    # ── Knowledge ──────────────────────────────────────────────────────────────

    def store_knowledge(
        self,
        extractions: list[Extraction],
        turn_id: int,
        person_id: str | None,
        agent: str,
    ) -> int:
        if config.RETENTION_MODE == "ephemeral":
            return 0  # SB.5: retention-gated — no knowledge capture under ephemeral
        now = time.time()
        count = 0
        for e in extractions:
            # P0.S4 D1 — fail-loud at the brain.db write boundary if a tier
            # value outside PRIVACY_LEVELS slipped through extraction. The
            # _visibility_clause has no predicate matching an invalid tier,
            # so silently writing one would produce a row that's structurally
            # invisible to every retrieval site. Caller is wrapped in
            # try/except at _poll_once + _emotion_process_background; the
            # raise propagates up, logs traceback, continues to next turn.
            _assert_valid_privacy_level(
                e.privacy_level,
                f"BrainDB.store_knowledge (agent={agent!r}, attribute={e.attribute!r})",
            )
            valid_until = _valid_until(e.is_temporal, e.valid_for_hours, now)
            self._conn.execute(
                """INSERT INTO knowledge
                       (source_turn_id, person_id, entity, entity_type, attribute,
                        value, confidence, is_temporal, valid_until, valid_at,
                        agent, created_at, privacy_level)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (turn_id, person_id, e.entity, e.entity_type, e.attribute,
                 e.value, e.confidence, int(e.is_temporal), valid_until, now,
                 agent, now, e.privacy_level),
            )
            # Keep the schema catalog: every attribute the LLM invents is recorded here.
            self._conn.execute(
                """INSERT INTO schema_catalog
                       (attribute, entity_type, example_value, first_seen_at, last_used_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(attribute) DO UPDATE SET
                       use_count     = use_count + 1,
                       last_used_at  = excluded.last_used_at,
                       example_value = COALESCE(excluded.example_value, example_value)""",
                (e.attribute, e.entity_type, e.value, now, now),
            )
            count += 1
        self._conn.commit()
        return count

    def get_active_knowledge(self, entity: str) -> list[dict]:
        """Return currently valid (non-invalidated, non-expired) facts for an entity."""
        now = time.time()
        rows = self._conn.execute(
            """SELECT attribute, value, confidence, is_temporal, valid_until,
                      valid_at, last_confirmed_at, privacy_level
               FROM knowledge
               WHERE entity = ?
                 AND invalidated_at IS NULL
                 AND (valid_until IS NULL OR valid_until > ?)
               ORDER BY created_at DESC""",
            (entity, now),
        ).fetchall()
        return [
            {
                "attribute":         r[0],
                "value":             r[1],
                "confidence":        r[2],
                "is_temporal":       bool(r[3]),
                "valid_until":       r[4],
                "valid_at":          r[5],
                "last_confirmed_at": r[6],
                "privacy_level":     r[7],
            }
            for r in rows
        ]

    def get_active_knowledge_for_entities(self, entity_list: list[str]) -> dict[str, list]:
        """Bulk fetch currently valid facts for all entities in entity_list.

        Single WHERE entity IN (?, ...) query — O(1) DB roundtrips instead of
        O(distinct entities) when the caller iterates over extracted facts.
        Returns dict mapping entity → list[dict] (same shape as get_active_knowledge).
        """
        if not entity_list:
            return {}
        now = time.time()
        placeholders = ",".join("?" * len(entity_list))
        rows = self._conn.execute(
            f"""SELECT entity, attribute, value, confidence, is_temporal, valid_until,
                      valid_at, last_confirmed_at, privacy_level
               FROM knowledge
               WHERE entity IN ({placeholders})
                 AND invalidated_at IS NULL
                 AND (valid_until IS NULL OR valid_until > ?)
               ORDER BY created_at DESC""",
            (*entity_list, now),
        ).fetchall()
        result: dict[str, list] = {ent: [] for ent in entity_list}
        for r in rows:
            result[r[0]].append({
                "attribute":         r[1],
                "value":             r[2],
                "confidence":        r[3],
                "is_temporal":       bool(r[4]),
                "valid_until":       r[5],
                "valid_at":          r[6],
                "last_confirmed_at": r[7],
                "privacy_level":     r[8],
            })
        return result

    def get_historical_knowledge(self, entity: str, attribute: str) -> list[dict]:
        """Return all rows for (entity, attribute) in chronological order, including invalidated.

        Used to answer "what was Jagan's job before?" type queries.
        """
        rows = self._conn.execute(
            """SELECT attribute, value, confidence, valid_at, invalidated_at, created_at
               FROM knowledge
               WHERE entity = ? AND attribute = ?
               ORDER BY valid_at ASC""",
            (entity, attribute),
        ).fetchall()
        return [
            {
                "attribute":      r[0], "value":        r[1],
                "confidence":     r[2], "valid_at":      r[3],
                "invalidated_at": r[4], "created_at":    r[5],
            }
            for r in rows
        ]

    def invalidate(self, entity: str, attribute: str, invalidated_by_turn: int) -> int:
        """Mark existing facts for (entity, attribute) as superseded."""
        cursor = self._conn.execute(
            """UPDATE knowledge
               SET invalidated_at = ?, invalidated_by = ?
               WHERE entity = ? AND attribute = ? AND invalidated_at IS NULL""",
            (time.time(), invalidated_by_turn, entity, attribute),
        )
        self._conn.commit()
        return cursor.rowcount

    # ── Agent log ──────────────────────────────────────────────────────────────

    def log_agent(
        self,
        turn_id: int | None,
        agent: str,
        decision: str,
        rationale: str | None = None,
        items: int = 0,
        duration_ms: float = 0.0,
    ) -> None:
        self._conn.execute(
            """INSERT INTO agent_log
                   (turn_id, agent, decision, rationale, items, duration_ms, ts)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (turn_id, agent, decision, rationale, items, duration_ms, time.time()),
        )
        self._conn.commit()

    # ── Prompt preferences ─────────────────────────────────────────────────────

    def store_pref(
        self,
        person_id: str,
        pref_type: str,
        content: str,
        source: str = "prompt_agent",
    ) -> bool:
        """Store a preference. Returns True if new, False if sessions_seen incremented.

        Near-duplicate detection: same person_id + pref_type + identical normalized
        content → increment sessions_seen and auto-confirm at 3.
        """
        if config.RETENTION_MODE == "ephemeral":
            return False  # SB.5: retention-gated — no preference capture under ephemeral
        norm = content.strip().lower()
        rows = self._conn.execute(
            "SELECT id, sessions_seen, content FROM prompt_prefs WHERE person_id=? AND pref_type=?",
            (person_id, pref_type),
        ).fetchall()
        for row_id, sessions, stored_content in rows:
            if stored_content.strip().lower() == norm:
                new_count = sessions + 1
                self._conn.execute(
                    "UPDATE prompt_prefs SET sessions_seen=?, confirmed=? WHERE id=?",
                    (new_count, 1 if new_count >= PREF_AUTO_CONFIRM_THRESHOLD else 0, row_id),
                )
                self._conn.commit()
                return False
        self._conn.execute(
            """INSERT INTO prompt_prefs
                   (person_id, pref_type, content, source, sessions_seen, confirmed, created_at)
               VALUES (?, ?, ?, ?, 1, ?, ?)""",
            (person_id, pref_type, content, source, 1 if source == "human" else 0, time.time()),
        )
        self._conn.commit()
        return True

    def get_active_prefs(self, person_id: str) -> list[dict]:
        """Return confirmed prefs: confirmed=1 or sessions_seen≥threshold, not expired."""
        now = time.time()
        rows = self._conn.execute(
            """SELECT pref_type, content, sessions_seen, confirmed, friction_count
               FROM prompt_prefs
               WHERE person_id = ?
                 AND (confirmed = 1 OR sessions_seen >= ?)
                 AND (expires_at IS NULL OR expires_at > ?)
               ORDER BY sessions_seen DESC, created_at DESC""",
            (person_id, PREF_AUTO_CONFIRM_THRESHOLD, now),
        ).fetchall()
        return [
            {
                "pref_type":     r[0], "content":      r[1],
                "sessions_seen": r[2], "confirmed":    bool(r[3]),
                "friction_count": r[4],
            }
            for r in rows
        ]

    # ── Bug L (Session 69) — semantic dedup support ──────────────────────────
    def get_prefs_by_type(self, person_id: str, pref_type: str) -> list[dict]:
        """Return ALL prefs for (person_id, pref_type), including staged ones.
        Used at activation time to check semantic similarity against prior prefs
        — staged rows (sessions_seen < threshold) must also count so repeated
        near-duplicates strengthen the existing row instead of fragmenting."""
        rows = self._conn.execute(
            """SELECT id, content, sessions_seen, confirmed, embedding
               FROM prompt_prefs
               WHERE person_id = ? AND pref_type = ?
               ORDER BY sessions_seen DESC, created_at DESC""",
            (person_id, pref_type),
        ).fetchall()
        return [
            {"id": r[0], "content": r[1], "sessions_seen": r[2],
             "confirmed": bool(r[3]), "embedding": r[4]}
            for r in rows
        ]

    def set_pref_embedding(self, pref_id: int, embedding: bytes) -> None:
        """Persist the 1024-dim float32 embedding bytes for a pref row."""
        self._conn.execute(
            "UPDATE prompt_prefs SET embedding = ? WHERE id = ?",
            (embedding, pref_id),
        )
        self._conn.commit()

    def bump_pref_seen(self, pref_id: int) -> None:
        """Strengthen an existing pref — increment sessions_seen, auto-confirm
        at PREF_AUTO_CONFIRM_THRESHOLD. Used when semantic dedup matches an
        existing row instead of inserting a near-duplicate."""
        row = self._conn.execute(
            "SELECT sessions_seen FROM prompt_prefs WHERE id = ?", (pref_id,),
        ).fetchone()
        if not row:
            return
        new_count = row[0] + 1
        self._conn.execute(
            "UPDATE prompt_prefs SET sessions_seen = ?, confirmed = ? WHERE id = ?",
            (new_count, 1 if new_count >= PREF_AUTO_CONFIRM_THRESHOLD else 0, pref_id),
        )
        self._conn.commit()

    def get_prompt_addendum(self, person_id: str) -> str | None:
        """Format active prefs as an injection-ready string with friction escalation.

        Returns None if empty. friction_count drives injection urgency:
          0   → plain content
          1-2 → [important] prefix
          3+  → [STRICT — repeated friction] prefix
        """
        prefs = self.get_active_prefs(person_id)
        if not prefs:
            return None
        return "\n".join(
            f"- {_escalate_pref(p['content'], p['friction_count'])}" for p in prefs
        )

    # ── Predicate reliability stats (Phase 5) ──────────────────────────────────

    def increment_predicate_contradiction(self, predicate: str) -> None:
        self._conn.execute(
            """INSERT INTO predicate_stats (predicate, contradiction_count, total_extractions, updated_at)
               VALUES (?, 1, 0, ?)
               ON CONFLICT(predicate) DO UPDATE SET
                   contradiction_count = contradiction_count + 1,
                   updated_at = excluded.updated_at""",
            (predicate, time.time()),
        )
        self._conn.commit()

    def increment_predicate_extraction(self, predicate: str) -> None:
        self.batch_increment_predicate_extraction([predicate])

    def batch_increment_predicate_extraction(self, predicates: list[str]) -> None:
        """Increment total_extractions for each predicate in a single transaction."""
        if not predicates:
            return
        now = time.time()
        for predicate in predicates:
            self._conn.execute(
                """INSERT INTO predicate_stats (predicate, contradiction_count, total_extractions, updated_at)
                   VALUES (?, 0, 1, ?)
                   ON CONFLICT(predicate) DO UPDATE SET
                       total_extractions = total_extractions + 1,
                       updated_at = excluded.updated_at""",
                (predicate, now),
            )
        self._conn.commit()

    def get_predicate_contradiction_count(self, predicate: str) -> int:
        row = self._conn.execute(
            "SELECT contradiction_count FROM predicate_stats WHERE predicate = ?",
            (predicate,),
        ).fetchone()
        return row[0] if row else 0

    def increment_pref_friction(self, person_id: str, pref_type: str) -> None:
        """Increment friction_count for the matching active pref. No-op if no match."""
        self._conn.execute(
            """UPDATE prompt_prefs
               SET friction_count = friction_count + 1
               WHERE person_id = ? AND pref_type = ?
                 AND (confirmed = 1 OR sessions_seen >= ?)
                 AND (expires_at IS NULL OR expires_at > ?)""",
            (person_id, pref_type, PREF_AUTO_CONFIRM_THRESHOLD, time.time()),
        )
        self._conn.commit()

    def get_all_knowledge_rows(self) -> list[dict]:
        """Return all knowledge rows (including invalidated) for graph rebuild.

        P0.S7.D-B: ``privacy_level`` added so the v3 graph rebuild can
        thread the tier onto every RELATES_TO edge. Pre-S106 rows that
        lack the column fall back at the caller via
        ``row.get("privacy_level") or PRIVACY_LEVEL_DEFAULT``.
        """
        rows = self._conn.execute(
            "SELECT entity, entity_type, attribute, value, confidence,"
            " is_temporal, valid_until, invalidated_at, source_turn_id, created_at, valid_at,"
            " privacy_level"
            " FROM knowledge"
        ).fetchall()
        return [
            {
                "entity": r[0], "entity_type": r[1], "attribute": r[2],
                "value": r[3], "confidence": r[4], "is_temporal": r[5],
                "valid_until": r[6], "invalidated_at": r[7],
                "source_turn_id": r[8], "created_at": r[9],
                "valid_at": r[10], "privacy_level": r[11],
            }
            for r in rows
        ]

    # ── Migration ──────────────────────────────────────────────────────────────
    # P0.9.3: the former `_migrate()` method body (10 PRAGMA-guarded ALTERs
    # spanning knowledge.embedding/valid_at/last_confirmed_at/privacy_level,
    # schema_catalog.embedding, prompt_prefs.friction_count/embedding,
    # brain_state.graph_schema_version, shadow_persons.mention_count,
    # intent_divergences.mode, plus the privacy_level NULL/legacy 'private'
    # remediation) has been retrofitted as MIGRATIONS entries v=2 through
    # v=11 in core.brain_db_migrations.  core.schema_migrations.apply_migrations
    # runs them (or bootstrap stamps them is_initial=1 on legacy DBs where
    # they already landed via the pre-P0.9 inline path).  The inline code
    # that used to live here is now redundant by construction — Phase 2's
    # validation against Jagan's prod DBs confirmed the bootstrap+runner
    # path handles legacy state.  _migrate() now exists only as a stub
    # so the __init__ call site stays trivially correct.

    def _migrate(self) -> None:
        """No-op stub — retrofitted into core.brain_db_migrations.MIGRATIONS.

        Kept as a stub (rather than removed entirely) so the existing
        __init__ call chain reads cleanly without conditional branches.
        The migration runner does the real work via apply_migrations.
        """
        return

    # ── Embedding storage ──────────────────────────────────────────────────────

    def store_knowledge_embedding(self, knowledge_id: int, embedding: list[float]) -> None:
        blob = np.array(embedding, dtype=np.float32).tobytes()
        self._conn.execute(
            "UPDATE knowledge SET embedding = ? WHERE id = ?", (blob, knowledge_id)
        )
        self._conn.commit()

    def get_unembedded_knowledge(self, person_id: str, limit: int = 20) -> list[dict]:
        """Return recently stored rows for a person that have no embedding yet."""
        rows = self._conn.execute(
            """SELECT id, entity, attribute, value
               FROM knowledge
               WHERE person_id = ? AND embedding IS NULL AND invalidated_at IS NULL
               ORDER BY created_at DESC LIMIT ?""",
            (person_id, limit),
        ).fetchall()
        return [{"id": r[0], "entity": r[1], "attribute": r[2], "value": r[3]} for r in rows]

    def get_all_unembedded_knowledge(self, limit: int = 50) -> list[dict]:
        """Return rows with embedding IS NULL across ALL persons, for startup backfill.

        Ordered oldest-first so the historical backlog is processed chronologically
        rather than re-processing the most recent rows that _embed_new_facts already handles.
        """
        rows = self._conn.execute(
            """SELECT id, entity, attribute, value, person_id
               FROM knowledge
               WHERE embedding IS NULL AND invalidated_at IS NULL
               ORDER BY created_at ASC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [
            {"id": r[0], "entity": r[1], "attribute": r[2], "value": r[3], "person_id": r[4]}
            for r in rows
        ]

    def store_schema_embedding(self, attribute: str, embedding: list[float]) -> None:
        blob = np.array(embedding, dtype=np.float32).tobytes()
        self._conn.execute(
            "UPDATE schema_catalog SET embedding = ? WHERE attribute = ?", (blob, attribute)
        )
        self._conn.commit()

    def get_unembedded_schema_attributes(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT attribute, use_count FROM schema_catalog"
            " WHERE embedding IS NULL ORDER BY use_count DESC"
        ).fetchall()
        return [{"attribute": r[0], "use_count": r[1]} for r in rows]

    def get_all_schema_embeddings(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT attribute, use_count, embedding FROM schema_catalog"
            " WHERE embedding IS NOT NULL"
        ).fetchall()
        return [{"attribute": r[0], "use_count": r[1], "embedding": r[2]} for r in rows]

    def merge_schema_attributes(self, canonical: str, synonyms: list[str]) -> None:
        """Rewrite knowledge rows and collapse schema_catalog for synonym → canonical."""
        for syn in synonyms:
            self._conn.execute(
                "UPDATE knowledge SET attribute = ? WHERE attribute = ?", (canonical, syn)
            )
            row = self._conn.execute(
                "SELECT use_count FROM schema_catalog WHERE attribute = ?", (syn,)
            ).fetchone()
            if row:
                self._conn.execute(
                    "UPDATE schema_catalog SET use_count = use_count + ? WHERE attribute = ?",
                    (row[0], canonical),
                )
            self._conn.execute(
                "DELETE FROM schema_catalog WHERE attribute = ?", (syn,)
            )
        self._conn.commit()

    def update_confidence(self, knowledge_id: int, delta: float) -> None:
        """Adjust a fact's confidence by delta, clamped to [0.0, 0.99]."""
        self._conn.execute(
            "UPDATE knowledge SET confidence = MIN(0.99, MAX(0.0, confidence + ?)) WHERE id = ?",
            (delta, knowledge_id),
        )
        self._conn.commit()

    def update_confirmation(self, knowledge_id: int) -> None:
        """Boost confidence AND reset the decay clock (SM-2 confirmation).

        Called when the user explicitly confirms an AI-recalled fact. The
        last_confirmed_at timestamp becomes the new anchor for decay, so the
        fact is treated as freshly valid starting from today.
        """
        now = time.time()
        self._conn.execute(
            """UPDATE knowledge
               SET confidence = MIN(0.99, MAX(0.0, confidence + ?)),
                   last_confirmed_at = ?
               WHERE id = ?""",
            (CONFIDENCE_BOOST, now, knowledge_id),
        )
        self._conn.commit()

    def decay_and_prune(
        self, prune_floor: float, decay_threshold: float
    ) -> tuple[int, int, int]:
        """Apply time-decay writes to all active knowledge rows.

        Facts whose effective confidence drops below prune_floor are soft-deleted
        (invalidated_at set). Facts that have decayed by more than decay_threshold
        have their stored confidence updated to the current effective value.

        Returns (pruned, decayed, stable) counts.
        """
        now = time.time()
        rows = self._conn.execute(
            """SELECT id, confidence, valid_at, last_confirmed_at
               FROM knowledge
               WHERE invalidated_at IS NULL""",
        ).fetchall()
        if not rows:
            return 0, 0, 0

        pruned = decayed = 0
        for row_id, stored_conf, valid_at, last_confirmed_at in rows:
            eff_conf = _decayed_confidence(stored_conf, valid_at, last_confirmed_at)
            if eff_conf < prune_floor:
                self._conn.execute(
                    "UPDATE knowledge SET invalidated_at = ? WHERE id = ?", (now, row_id)
                )
                pruned += 1
            elif eff_conf < stored_conf - decay_threshold:
                self._conn.execute(
                    "UPDATE knowledge SET confidence = ? WHERE id = ?",
                    (round(eff_conf, 4), row_id),
                )
                decayed += 1

        if pruned or decayed:
            self._conn.commit()

        return pruned, decayed, len(rows) - pruned - decayed

    def find_knowledge_id(self, entity: str, attribute: str, value: str) -> int | None:
        """Return the id of an active knowledge row, or None if not found."""
        row = self._conn.execute(
            "SELECT id FROM knowledge WHERE entity = ? AND attribute = ? AND value = ?"
            " AND invalidated_at IS NULL LIMIT 1",
            (entity, attribute, value),
        ).fetchone()
        return row[0] if row else None

    def semantic_search_knowledge(
        self,
        person_name: str,
        query_embedding: list[float],
        top_k: int = EMBED_TOP_K,
        *,
        requester_pid: "str | None" = None,
        best_friend_id: "str | None" = None,
    ) -> list[dict]:
        """Return top-K facts for a person ranked by cosine similarity to the query.

        Applies time-decay filtering (Item 6): a floor of 0.30 is used in SQL to
        avoid loading noise-level facts; actual EMBED_MIN_CONFIDENCE gate is applied
        in Python using _decayed_confidence() so old facts decay out naturally.

        Session 107 Phase 3A.6 — visibility is now composed into the
        SELECT WHERE clause when ``requester_pid`` is supplied. Same
        semantics as ``query_knowledge_for``: best_friend sees all
        non-system_only tiers, non-best_friend sees public + own
        personal. When ``requester_pid`` is None (internal callers with
        no identity context — dream loop synthesis, schema
        normalization), no visibility filter is added (pass-through
        behavior matching the legacy ``filter_facts_for_requester``'s
        None-guard path). Ranking + filtering now happen together in
        SQL; the Python-side filter step (``filter_facts_for_requester``)
        is deleted as part of this migration.
        """
        now = time.time()
        where_parts: list[str] = [
            "entity = ?",
            "invalidated_at IS NULL",
            "(valid_until IS NULL OR valid_until > ?)",
            "confidence >= 0.30",
            "embedding IS NOT NULL",
        ]
        params: list = [person_name, now]
        if requester_pid is not None:
            vis_clause, vis_params = _visibility_clause(requester_pid, best_friend_id)
            where_parts.append(f"({vis_clause})")
            params.extend(vis_params)
        sql = (
            "SELECT attribute, value, confidence, is_temporal, valid_until, "
            "embedding, valid_at, last_confirmed_at, privacy_level "
            "FROM knowledge WHERE " + " AND ".join(where_parts) +
            " ORDER BY created_at DESC"
        )
        rows = self._conn.execute(sql, params).fetchall()
        if not rows:
            return []

        doc_vecs   = []
        fact_dicts = []
        for r in rows:
            eff_conf = _decayed_confidence(r[2], r[6], r[7])
            if eff_conf < EMBED_MIN_CONFIDENCE:
                continue
            doc_vecs.append(np.frombuffer(r[5], dtype=np.float32).tolist())
            fact_dicts.append({
                "attribute":         r[0], "value":           r[1],
                "confidence":        r[2], "is_temporal":      bool(r[3]),
                "valid_until":       r[4], "valid_at":         r[6],
                "last_confirmed_at": r[7], "privacy_level":    r[8],
            })
        if not fact_dicts:
            return []

        scores = _cosine_similarity(query_embedding, doc_vecs)
        ranked = sorted(zip(scores, fact_dicts), key=lambda x: x[0], reverse=True)
        return [f for _, f in ranked[:top_k]]

    # ── Context ────────────────────────────────────────────────────────────────

    def get_context_for_person(self, person_name: str) -> str | None:
        """Return formatted knowledge for LLM system-prompt injection (recency order)."""
        facts = self.get_active_knowledge(person_name)
        return _format_context_lines(person_name, facts) if facts else None

    # Session 107 Phase 3A.6 — filter_facts_for_requester was deleted
    # after the semantic-search branch of BrainOrchestrator.get_context
    # migrated to pass requester_pid/best_friend_id into
    # semantic_search_knowledge (which composes _visibility_clause in
    # SQL). Zero remaining production callers. The 4-tier visibility
    # policy now lives in one place only: `_visibility_clause` at
    # module scope. Any future retrieval site that needs privacy
    # filtering goes through `query_knowledge_for` or passes
    # `requester_pid` into `semantic_search_knowledge`.

    def query_knowledge_for(
        self,
        requester_pid:  str,
        best_friend_id: "str | None",
        *,
        entity:    "str | None" = None,
        attribute: "str | None" = None,
        limit:     int           = 20,
    ) -> list[dict]:
        """Privacy-filtered knowledge retrieval — the 4-tier replacement for
        `get_active_knowledge` + `filter_facts_for_requester`.

        Internal callers touching the ``knowledge`` table MUST use this (or go
        through a site that does) once 3A.4 canary lands. Single source of
        truth for visibility policy: the SELECT's WHERE clause is composed
        from `_visibility_clause`, so adding a new tier or flipping policy
        happens in one place.

        The returned shape deliberately mirrors reviewer's 3A.4 spec
        (entity/attribute/value/confidence/person_id/privacy_level) rather
        than the richer `get_active_knowledge` shape — the canary site only
        consumes attribute/value/confidence, and keeping the surface narrow
        lets the schema grow (e.g. add `tier_reason` in 3A.6) without
        ballooning the read columns.

        Temporal and invalidation filters match the existing read paths:
        only currently-valid rows are returned (``invalidated_at IS NULL``
        and ``valid_until > now`` when present). Sort is confidence DESC
        followed by recency so the top-k slice is stable across calls.
        """
        now = time.time()
        vis_clause, vis_params = _visibility_clause(requester_pid, best_friend_id)

        where_parts:  list[str] = [f"({vis_clause})", "invalidated_at IS NULL",
                                   "(valid_until IS NULL OR valid_until > ?)"]
        sql_params:   list      = list(vis_params) + [now]
        if entity:
            where_parts.append("entity = ?")
            sql_params.append(entity)
        if attribute:
            where_parts.append("attribute = ?")
            sql_params.append(attribute)

        sql = (
            "SELECT entity, attribute, value, confidence, person_id, privacy_level "
            "FROM knowledge WHERE " + " AND ".join(where_parts) +
            " ORDER BY confidence DESC, created_at DESC LIMIT ?"
        )
        sql_params.append(limit)
        cur = self._conn.execute(sql, sql_params)
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        # Session 116 P1 #1+#2 — auditability: log every privacy-filtered
        # read with requester + tier scope + result shape so an outside
        # reviewer can verify cross-person isolation from terminal output
        # alone. Owner-mode (best_friend == requester) is the most
        # permissive scope and worth flagging in the line.
        _scope = (
            "owner-mode" if best_friend_id and requester_pid == best_friend_id
            else "non-owner"
        )
        _entity_str = f"entity={entity!r}" if entity else "all-entities"
        _attr_str = f", attribute={attribute!r}" if attribute else ""
        print(
            f"[Privacy] {_now_log_ts()} query_knowledge_for "
            f"requester={requester_pid!r} ({_scope}) {_entity_str}{_attr_str} "
            f"→ {len(rows)} row(s)"
        )
        return rows

    def get_core_memory_for(
        self,
        requester_pid:  str,
        best_friend_id: "str | None",
        entity:         str,
    ) -> list[dict]:
        """Return always-on stable facts for Section 2 prompt injection.

        Fetches rows whose attribute is in CORE_MEMORY_ATTRIBUTES and whose
        confidence meets CORE_MEMORY_MIN_CONFIDENCE.  Privacy filtering is
        applied via _visibility_clause — same policy as query_knowledge_for,
        so cross-person facts cannot leak.

        Returns up to CORE_MEMORY_MAX_FACTS rows ordered by confidence DESC.
        Returns [] when CORE_MEMORY_ENABLED is False.
        """
        if not CORE_MEMORY_ENABLED:
            return []

        now = time.time()
        vis_clause, vis_params = _visibility_clause(requester_pid, best_friend_id)

        # Build a SQL IN clause for the attribute whitelist
        placeholders = ",".join("?" * len(CORE_MEMORY_ATTRIBUTES))
        where = (
            f"({vis_clause})"
            " AND invalidated_at IS NULL"
            " AND (valid_until IS NULL OR valid_until > ?)"
            " AND entity = ?"
            f" AND attribute IN ({placeholders})"
            " AND confidence >= ?"
        )
        params: list = (
            list(vis_params)
            + [now, entity]
            + list(CORE_MEMORY_ATTRIBUTES)
            + [CORE_MEMORY_MIN_CONFIDENCE]
        )

        sql = (
            "SELECT entity, attribute, value, confidence, person_id, privacy_level "
            f"FROM knowledge WHERE {where} "
            "ORDER BY confidence DESC LIMIT ?"
        )
        params.append(CORE_MEMORY_MAX_FACTS)

        cur = self._conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        return rows

    # ── SB.6 object memory (gated off by default) ─────────────────────────────

    def store_object_sighting(
        self,
        object_class:   str,
        confidence:     float,
        location_zone:  str,
        bbox_cx:        float,
        bbox_cy:        float,
        person_id:      str,
        person_context: "str | None" = None,
        now:            "float | None" = None,
    ) -> bool:
        """SB.6 Step 6 (D1) — retention-gated writer for persistent object memory.

        Two gates, both load-bearing:
          1. ``config.OBJECT_MEMORY_ENABLED`` — the SB.6 master feature flag
             (DEFAULT OFF; the §4.b concierge net flips it on). When off the
             call no-ops so the gated-off feature never touches the DB.
          2. ``config.RETENTION_MODE == "ephemeral"`` — the SB.5 retention gate.
             `object_sightings` is the 11th brain.db PERSONAL retention table:
             durable retention grows it, ephemeral purges it. (The §4.a
             partition scanner classifies the INSERT target PERSONAL via
             PERSONAL_TABLES, and `_func_consults_gate` is satisfied by the
             `config.RETENTION_MODE` reference below.)

        Rows are written with ``privacy_level = PRIVACY_LEVEL_DEFAULT`` (the
        owner-only 'personal' tier) and ``person_id`` = the visual-query
        session's person, so a visitor reading via `get_object_context` cannot
        see the owner's sightings (no-leak). Returns True on insert, False when
        a gate short-circuits.

        Live attribute access (``config.X``) is deliberate — the §4.b net
        monkeypatches ``core.config`` and both gates must observe the patch.
        """
        if not config.OBJECT_MEMORY_ENABLED:
            return False  # SB.6: object memory gated off by default
        if config.RETENTION_MODE == "ephemeral":
            return False  # SB.5: retention-gated — no object capture under ephemeral
        ts = time.time() if now is None else now
        self._conn.execute(
            "INSERT INTO object_sightings "
            "(object_class, confidence, location_zone, bbox_cx, bbox_cy, "
            " first_seen_at, last_seen_at, times_seen, person_context, "
            " person_id, privacy_level) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
            (object_class, confidence, location_zone, bbox_cx, bbox_cy,
             ts, ts, person_context, person_id, PRIVACY_LEVEL_DEFAULT),
        )
        self._conn.commit()
        return True

    def get_object_context(
        self,
        requester_pid:  str,
        best_friend_id: "str | None",
        *,
        object_class: "str | None" = None,
        limit:        int           = 20,
    ) -> list[dict]:
        """SB.6 Step 6 — privacy-scoped reader for persistent object memory.

        Single source of truth for visibility: the SELECT's WHERE clause is
        composed from `_visibility_clause` (the SB.5 four-tier policy), exactly
        as `query_knowledge_for` does. A best_friend sees every non-`system_only`
        sighting; a visitor (non-best-friend) sees only public OR
        personal-tier rows they own — so since the writer stamps
        ``privacy_level='personal'`` with ``person_id`` = the owner, a visitor
        reading another person's sightings gets NONE (the no-leak invariant).

        No gate on the reader — an empty `object_sightings` table (the
        gated-off default) simply returns []. Sorted by recency
        (``last_seen_at DESC``).
        """
        vis_clause, vis_params = _visibility_clause(requester_pid, best_friend_id)
        where_parts: list[str] = [f"({vis_clause})"]
        sql_params:  list      = list(vis_params)
        if object_class:
            where_parts.append("object_class = ?")
            sql_params.append(object_class)

        sql = (
            "SELECT object_class, confidence, location_zone, bbox_cx, bbox_cy, "
            "last_seen_at, times_seen, person_context, person_id, privacy_level "
            "FROM object_sightings WHERE " + " AND ".join(where_parts) +
            " ORDER BY last_seen_at DESC LIMIT ?"
        )
        sql_params.append(limit)
        cur = self._conn.execute(sql, sql_params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    # ── Table pruning (E) ─────────────────────────────────────────────────────

    def prune_knowledge_hard_cap(self, max_rows: int) -> int:
        """Soft-delete oldest active knowledge rows when count exceeds max_rows.

        Marks excess rows as invalidated (not hard-deleted) so the graph and
        embedding blobs remain queryable for rebuild. Returns rows invalidated.
        """
        count = self._conn.execute(
            "SELECT COUNT(*) FROM knowledge WHERE invalidated_at IS NULL"
        ).fetchone()[0]
        if count <= max_rows:
            return 0
        excess = count - max_rows
        self._conn.execute(
            "UPDATE knowledge SET invalidated_at = ? WHERE id IN ("
            "  SELECT id FROM knowledge WHERE invalidated_at IS NULL"
            "  ORDER BY created_at ASC LIMIT ?"
            ")",
            (time.time(), excess),
        )
        self._conn.commit()
        return excess

    def hard_delete_old_invalidated_knowledge(
        self,
        *,
        cutoff_days: int = KNOWLEDGE_HARD_DELETE_AFTER_DAYS,
        now: float | None = None,
    ) -> int:
        """Hard-delete knowledge rows soft-deleted longer than cutoff_days.

        Wave 6 / Item 22 — prevents unbounded soft-delete accumulation at year
        scale. Conservative 60-day cutoff: conversation log archives at 30 days,
        so a 30-day buffer remains where archived turns can still resolve their
        invalidated facts.
        """
        if now is None:
            now = time.time()
        cutoff_ts = now - (cutoff_days * 86400)
        cur = self._conn.execute(
            "DELETE FROM knowledge "
            "WHERE invalidated_at IS NOT NULL AND invalidated_at < ?",
            (cutoff_ts,),
        )
        n = cur.rowcount
        self._safe_commit()
        if n > 0:
            print(f"[Prune] Hard-deleted {n} invalidated knowledge row(s) older than {cutoff_days}d")
        return n

    def _prune_table(self, table: str, order_col: str, max_rows: int) -> int:
        """Hard-delete oldest rows from table when row count exceeds max_rows."""
        count = self._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if count <= max_rows:
            return 0
        excess = count - max_rows
        self._conn.execute(
            f"DELETE FROM {table} WHERE id IN ("
            f"  SELECT id FROM {table} ORDER BY {order_col} ASC LIMIT ?"
            f")",
            (excess,),
        )
        self._conn.commit()
        return excess

    def prune_presence_log(self, max_rows: int) -> int:
        return self._prune_table("presence_log", "arrived_at", max_rows)

    def prune_episodes(self, max_rows: int) -> int:
        return self._prune_table("episodes", "session_end_ts", max_rows)

    def prune_social_mentions(self, max_rows: int) -> int:
        return self._prune_table("social_mentions", "updated_at", max_rows)

    def prune_expired_nudges(self) -> int:
        """Delete proactive nudges whose expires_at has passed."""
        cur = self._conn.execute(
            "DELETE FROM proactive_nudges WHERE expires_at IS NOT NULL AND expires_at < ?",
            (time.time(),),
        )
        self._conn.commit()
        return cur.rowcount

    def prune_old_resolved_alerts(self, max_age_days: float) -> int:
        """Delete resolved watchdog alerts older than max_age_days."""
        cutoff = time.time() - max_age_days * 86400
        cur = self._conn.execute(
            "DELETE FROM watchdog_alerts WHERE resolved = 1 AND created_at < ?",
            (cutoff,),
        )
        self._conn.commit()
        return cur.rowcount

    def prune_agent_log(self, max_age_days: float = 30, max_rows: int = 50_000) -> int:
        """Delete old agent_log rows: first by age, then hard-cap remaining."""
        cutoff = time.time() - max_age_days * 86400
        cur = self._conn.execute(
            "DELETE FROM agent_log WHERE ts < ?", (cutoff,)
        )
        self._conn.commit()
        removed = cur.rowcount
        removed += self._prune_table("agent_log", "ts", max_rows)
        return removed

    def prune_expired_prefs(self) -> int:
        """Delete prompt_prefs rows whose expires_at has passed."""
        cur = self._conn.execute(
            "DELETE FROM prompt_prefs WHERE expires_at IS NOT NULL AND expires_at < ?",
            (time.time(),),
        )
        self._conn.commit()
        return cur.rowcount

    def prune_old_pattern_questions(self, max_age_days: float = 7) -> int:
        """Delete already-asked pattern questions older than max_age_days."""
        cutoff = time.time() - max_age_days * 86400
        cur = self._conn.execute(
            "DELETE FROM object_pattern_questions WHERE asked = 1 AND asked_at < ?",
            (cutoff,),
        )
        self._conn.commit()
        return cur.rowcount

    # ── Household context methods ───────────────────────────────────────────

    def store_household_fact(
        self,
        entity: str,
        attribute: str,
        value: str,
        scope: str,
        source_speaker: str,
        confidence: float,
    ) -> bool:
        """Store or update a household fact. Returns True if this created a dispute.

        Conflict logic:
        - Same speaker updates an existing fact → REPLACE (genuine update)
        - Different speaker corroborates → bump confidence + add to source_speakers
        - Different speaker contradicts a stable fact → mark disputed, store both values
        - Temporal/ephemeral facts (scope contains "temporal") → always REPLACE
        """
        if config.RETENTION_MODE == "ephemeral":
            return False  # SB.5: retention-gated — no household-fact capture under ephemeral
        now = time.time()
        row = self._conn.execute(
            "SELECT id, value, source_speakers, confidence, conflict_status FROM household_facts "
            "WHERE entity = ? AND attribute = ? AND conflict_status != 'invalidated'",
            (entity, attribute),
        ).fetchone()

        if row is None:
            self._conn.execute(
                "INSERT INTO household_facts "
                "(entity, attribute, value, scope, source_speakers, confidence, conflict_status, first_seen, last_confirmed) "
                "VALUES (?, ?, ?, ?, ?, ?, 'provisional', ?, ?)",
                (entity, attribute, value, scope, json.dumps([source_speaker]), confidence, now, now),
            )
            self._conn.commit()
            return False

        existing_id, existing_value, speakers_json, existing_conf, existing_status = row
        speakers: list = json.loads(speakers_json)

        # Same speaker → genuine update: REPLACE
        if source_speaker in speakers:
            self._conn.execute(
                "UPDATE household_facts SET value = ?, confidence = ?, last_confirmed = ? WHERE id = ?",
                (value, min(existing_conf + 0.05, 0.95), now, existing_id),
            )
            self._conn.commit()
            return False

        if value.lower() == existing_value.lower():
            # Different speaker corroborates — boost confidence
            if source_speaker not in speakers:
                speakers.append(source_speaker)
            new_conf = min(existing_conf + 0.10, 0.95)
            new_status = "settled" if new_conf >= 0.85 else existing_status
            self._conn.execute(
                "UPDATE household_facts SET source_speakers = ?, confidence = ?, "
                "conflict_status = ?, last_confirmed = ? WHERE id = ?",
                (json.dumps(speakers), new_conf, new_status, now, existing_id),
            )
            self._conn.commit()
            return False

        # Different speaker, different value → dispute
        disputed = {existing_value: speakers[0] if speakers else "unknown", value: source_speaker}
        self._conn.execute(
            "UPDATE household_facts SET conflict_status = 'disputed', "
            "disputed_values = ?, last_confirmed = ? WHERE id = ?",
            (json.dumps(disputed), now, existing_id),
        )
        self._conn.commit()
        return True

    def get_household_context(self) -> str | None:
        """Return formatted household facts + relationships for LLM injection."""
        now = time.time()
        rows = self._conn.execute(
            "SELECT entity, attribute, value, confidence, conflict_status, disputed_values, source_speakers "
            "FROM household_facts WHERE conflict_status != 'invalidated' "
            "ORDER BY confidence DESC, last_confirmed DESC LIMIT 30"
        ).fetchall()

        rels = self._conn.execute(
            "SELECT person_a, relationship, person_b, confidence FROM inter_person_relationships "
            "ORDER BY confidence DESC, updated_at DESC LIMIT 20"
        ).fetchall()

        if not rows and not rels:
            return None

        lines = []
        if rows:
            lines.append("Household & shared facts:")
            for entity, attr, value, conf, status, disputed_json, speakers_json in rows:
                label = attr.replace("_", " ")
                if status == "disputed" and disputed_json:  # knowledge-row status field, not person_type — disputed-row-status
                    disputed = json.loads(disputed_json)
                    parts = [f"{v} (per {k})" for k, v in disputed.items()]
                    lines.append(f"  - {label}: DISPUTED — {' vs '.join(parts)}")
                else:
                    suffix = ""
                    if conf < 0.70:
                        suffix = " (uncertain)"
                    elif status == "settled":
                        suffix = " (confirmed)"
                    scope_label = f"{entity}: " if entity != "household" else ""
                    lines.append(f"  - {scope_label}{label}: {value}{suffix}")

        if rels:
            lines.append("Known relationships:")
            for a, rel, b, conf in rels:
                suffix = " (uncertain)" if conf < 0.70 else ""
                lines.append(f"  - {a} → {rel.replace('_', ' ')} → {b}{suffix}")

        return "\n".join(lines) if lines else None

    def store_relationship(
        self,
        person_a: str,
        relationship: str,
        person_b: str,
        confidence: float,
        source_speaker: str,
    ) -> None:
        """Upsert an inter-person relationship."""
        if config.RETENTION_MODE == "ephemeral":
            return  # SB.5: retention-gated (Finding A — own method) — no relationship capture under ephemeral
        now = time.time()
        self._conn.execute(
            """INSERT INTO inter_person_relationships
                   (person_a, relationship, person_b, confidence, source_speaker, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(person_a, relationship, person_b) DO UPDATE SET
                   confidence = MAX(confidence, excluded.confidence),
                   updated_at = excluded.updated_at""",
            (person_a, relationship, person_b, confidence, source_speaker, now, now),
        )
        self._conn.commit()

    def get_shadow_person(self, name: str) -> dict | None:
        """Return a shadow person record by known_name (case-insensitive)."""
        row = self._conn.execute(
            "SELECT shadow_id, known_name, known_via, face_id, voice_id, enrollment_status, facts "
            "FROM shadow_persons WHERE LOWER(known_name) = LOWER(?)",
            (name,),
        ).fetchone()
        if not row:
            return None
        return {
            "shadow_id": row[0], "known_name": row[1], "known_via": json.loads(row[2]),
            "face_id": row[3], "voice_id": row[4], "enrollment_status": row[5],
            "facts": json.loads(row[6]),
        }

    def upsert_shadow_person(
        self,
        name: str,
        via_person_id: str,
        relationship: "str | None",
    ) -> tuple[str, bool]:
        """Create or update a shadow node for a non-enrolled person.

        Session 105 Obs B — SHADOW_NAME_BLOCKLIST rejects pronouns and
        relationship roles ("him", "her", "boyfriend", "friend",
        "boss", etc.) at the write site. These aren't people names —
        they're referents that the LLM sometimes surfaces when the
        actual name isn't known. Writing them as shadow_persons
        pollutes the graph with unlinkable placeholders. When the
        brain later learns the actual name ("her name is Sarah"), the
        shadow can be created at that point with real semantic value.

        Returns ``(shadow_id="", was_new=False)`` for blocked names so
        callers can short-circuit without branching on a separate
        signal.

        Returns ``(shadow_id, was_new)`` — callers inspect ``was_new`` to
        decide whether to log "Shadow node: {name}" (Session 97 Fix 3 —
        2026-04-22 canary showed the log firing twice for the same name
        because the caller didn't know the second call was a no-op update).

        Session 97 Fix 3 refinements:
          - `mention_count` column (migrated via ALTER TABLE); bumped
            every UPDATE so retention/pruning can weight heavily-
            mentioned shadows over one-offs.
          - known_via merge prefers a non-null relationship over null:
            if `Priya said "Anita"` (relationship=None) comes first and
            `Sarah said "my colleague Anita"` (relationship="colleague")
            comes second, the second entry is kept rather than appended
            as a separate via row. Reduces redundant via entries in the
            UI dashboard and keeps Kuzu relationship edges meaningful.
          - Same-via-person mentions collapse into one entry, so repeated
            turns from the same speaker don't inflate the list.
        """
        # Session 105 Obs B — reject pronouns/roles at the write site.
        # Whitespace-normalize + lowercase for comparison against the
        # frozenset. Empty/whitespace-only names also blocked (defensive).
        _name_key = (name or "").strip().lower()
        if not _name_key or _name_key in SHADOW_NAME_BLOCKLIST:
            print(
                f"[BrainDB] upsert_shadow_person: blocked {name!r} "
                f"(pronoun/role — not a real name)"
            )
            return ("", False)
        if config.RETENTION_MODE == "ephemeral":
            return ("", False)  # SB.5: retention-gated — no shadow-person capture under ephemeral
        now = time.time()
        existing = self._conn.execute(
            "SELECT shadow_id, known_via FROM shadow_persons WHERE LOWER(known_name) = LOWER(?)",
            (name,),
        ).fetchone()

        if existing is None:
            shadow_id = f"shadow_{uuid.uuid4().hex[:8]}"
            known_via_entry = json.dumps([
                {"person_id": via_person_id, "relationship": relationship}
            ])
            self._conn.execute(
                "INSERT INTO shadow_persons "
                "(shadow_id, known_name, known_via, first_mentioned, "
                " last_mentioned, mention_count) "
                "VALUES (?, ?, ?, ?, ?, 1)",
                (shadow_id, name, known_via_entry, now, now),
            )
            self._conn.commit()
            return (shadow_id, True)

        shadow_id = existing[0]
        via_list: list = json.loads(existing[1])
        # Merge: if an entry for this via_person_id already exists, prefer
        # the non-null relationship. Otherwise append as a new via entry.
        merged = False
        for entry in via_list:
            if entry.get("person_id") != via_person_id:
                continue
            merged = True
            existing_rel = entry.get("relationship")
            # Upgrade null → concrete; never downgrade concrete → null.
            if not existing_rel and relationship:
                entry["relationship"] = relationship
            break
        if not merged:
            via_list.append(
                {"person_id": via_person_id, "relationship": relationship}
            )
        self._conn.execute(
            "UPDATE shadow_persons SET known_via = ?, last_mentioned = ?, "
            "mention_count = mention_count + 1 WHERE shadow_id = ?",
            (json.dumps(via_list), now, shadow_id),
        )
        self._conn.commit()
        return (shadow_id, False)

    def add_shadow_person_fact(self, name: str, attribute: str, value: str, confidence: float) -> None:
        """Add a known fact about a shadow person (from what others said about them)."""
        now = time.time()
        existing = self._conn.execute(
            "SELECT shadow_id, facts FROM shadow_persons WHERE LOWER(known_name) = LOWER(?)",
            (name,),
        ).fetchone()
        if not existing:
            return
        shadow_id, facts_json = existing
        facts: list = json.loads(facts_json)
        # Update or append
        for f in facts:
            if f["attribute"] == attribute:
                f["value"] = value
                f["confidence"] = confidence
                break
        else:
            facts.append({"attribute": attribute, "value": value, "confidence": confidence})
        self._conn.execute(
            "UPDATE shadow_persons SET facts = ?, last_mentioned = ? WHERE shadow_id = ?",
            (json.dumps(facts), now, shadow_id),
        )
        self._conn.commit()

    def prune_shadow_persons(self, max_age_days: int = 90) -> int:
        """Remove stale shadow persons that were never enrolled and are very old."""
        cutoff = time.time() - max_age_days * 86400
        cur = self._conn.execute(
            "DELETE FROM shadow_persons WHERE enrollment_status = 'pending' AND last_mentioned < ?",
            (cutoff,),
        )
        self._conn.commit()
        return cur.rowcount

    def list_shadow_persons(self, status: str = "pending") -> list[dict]:
        """Return shadow persons by enrollment_status, newest-mentioned first."""
        rows = self._conn.execute(
            """SELECT shadow_id, known_name, known_via, face_id, enrollment_status, facts,
                      first_mentioned, last_mentioned
               FROM shadow_persons
               WHERE enrollment_status = ?
               ORDER BY last_mentioned DESC""",
            (status,),
        ).fetchall()
        return [
            {
                "shadow_id":         r[0],
                "known_name":        r[1],
                "known_via":         json.loads(r[2] or "[]"),
                "face_id":           r[3],
                "enrollment_status": r[4],
                "fact_count":        len(json.loads(r[5] or "[]")),
                "first_mentioned":   r[6],
                "last_mentioned":    r[7],
            }
            for r in rows
        ]

    def migrate_entity_name(self, old_name: str, new_name: str, person_id: str | None = None) -> int:
        """Rename entity in knowledge rows when a stranger's identity is confirmed.

        Uses person_id filter when provided — critical because multiple strangers
        share the default entity name 'visitor' and a plain entity-only UPDATE
        would corrupt all of them at once.

        Returns the number of rows updated.
        """
        # Capture BEFORE any write. When called inside transaction(), BEGIN IMMEDIATE
        # has already been issued so in_transaction=True → skip inner commit.
        # When called standalone, no BEGIN yet → in_transaction=False → commit at end.
        _in_outer_tx = self._conn.in_transaction
        if person_id:
            cur = self._conn.execute(
                "UPDATE knowledge SET entity = ? WHERE entity = ? AND person_id = ?",
                (new_name, old_name, person_id),
            )
        else:
            cur = self._conn.execute(
                "UPDATE knowledge SET entity = ? WHERE entity = ?",
                (new_name, old_name),
            )
        if not _in_outer_tx:
            self._conn.commit()
        n = cur.rowcount
        print(f"[BrainDB] migrate_entity_name: '{old_name}' → '{new_name}' ({n} rows updated)")
        return n

    def get_knowledge_rows_for_kuzu(self, person_id: str, entity: str) -> list[dict]:
        """Return all active knowledge rows for a person+entity pair.

        Used after migrate_entity_name to feed the Kuzu graph rebuild.
        """
        rows = self._conn.execute(
            """SELECT attribute, value, confidence, is_temporal, valid_until,
                      valid_at, source_turn_id, created_at
               FROM knowledge
               WHERE person_id = ? AND entity = ? AND invalidated_at IS NULL""",
            (person_id, entity),
        ).fetchall()
        return [
            {
                "attribute": r[0], "value": r[1], "confidence": r[2],
                "is_temporal": r[3], "valid_until": r[4], "valid_at": r[5],
                "source_turn_id": r[6], "created_at": r[7],
            }
            for r in rows
        ]

    def promote_shadow_to_confirmed(self, name: str, face_id: str) -> bool:
        """Link a shadow person to their confirmed face_id and copy their facts
        into the knowledge table.

        Returns True if a matching shadow node was found and promoted.
        """
        # Capture BEFORE any write — same inner-commit gate as migrate_entity_name.
        _in_outer_tx = self._conn.in_transaction
        now = time.time()
        row = self._conn.execute(
            "SELECT shadow_id, facts FROM shadow_persons WHERE LOWER(known_name) = LOWER(?)",
            (name,),
        ).fetchone()
        if not row:
            return False

        shadow_id, facts_json = row

        # Mark the shadow node as confirmed and record the face identity
        self._conn.execute(
            "UPDATE shadow_persons SET face_id = ?, enrollment_status = 'confirmed' WHERE shadow_id = ?",
            (face_id, shadow_id),
        )

        # Copy shadow facts (gathered from what others said) into the knowledge table
        # so they appear in get_context() alongside extracted conversation facts.
        # SB.5: retention-gated — under ephemeral, skip copying shadow facts into the
        # knowledge table (the promotion link above still applies; the shadow row itself
        # only exists under durable retention per the upsert_shadow_person gate).
        facts: list = [] if config.RETENTION_MODE == "ephemeral" else json.loads(facts_json)
        inserted = 0
        for f in facts:
            if not f.get("attribute") or not f.get("value"):
                continue
            # Session 95 3A.4.5: shadow facts are what OTHERS said about the
            # person before we met them. They're attributed to the person
            # (owner = the promoted face_id) so they belong in the 'personal'
            # tier — same reasoning as any other owner-scoped fact. Previously
            # this INSERT fell back to the column DEFAULT ('public') which
            # would have leaked on non-owner queries under the new
            # visibility_clause.
            self._conn.execute(
                """INSERT INTO knowledge
                       (source_turn_id, person_id, entity, entity_type, attribute,
                        value, confidence, is_temporal, valid_until, valid_at, agent,
                        created_at, privacy_level)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (0, face_id, name, "person", f["attribute"], f["value"],
                 f.get("confidence", 0.70), 0, None, now, "shadow_promotion", now,
                 PRIVACY_LEVEL_DEFAULT),
            )
            inserted += 1

        if not _in_outer_tx:
            self._conn.commit()
        print(f"[BrainDB] Shadow '{name}' promoted (face_id={face_id}, {inserted} facts copied)")
        return True

    # ── Object pattern questions ───────────────────────────────────────────────

    def get_next_pending_question(self) -> dict | None:
        """Return the oldest unasked pattern question, or None if none pending."""
        row = self._conn.execute(
            """SELECT id, question, pattern_key FROM object_pattern_questions
               WHERE asked = 0
               ORDER BY created_at ASC
               LIMIT 1""",
        ).fetchone()
        if not row:
            return None
        return {"id": row[0], "text": row[1], "pattern_key": row[2]}

    def mark_question_asked(self, qid: int) -> None:
        """Mark a question as asked so it is not served again."""
        self._conn.execute(
            "UPDATE object_pattern_questions SET asked = 1, asked_at = ? WHERE id = ?",
            (time.time(), qid),
        )
        self._conn.commit()

    # ── Social mentions ────────────────────────────────────────────────────────
    def upsert_social_mention(
        self,
        source_person_id: str,
        mentioned_name: str,
        relationship: str | None,
        new_attributes: list[str],
    ) -> None:
        """Store or update a person the best friend has mentioned.

        Merges new attributes with existing ones (case-insensitive dedup).
        Updates relationship if the existing row has none.
        """
        if config.RETENTION_MODE == "ephemeral":
            return  # SB.5: retention-gated — no social-mention capture under ephemeral
        row = self._conn.execute(
            "SELECT id, attributes FROM social_mentions "
            "WHERE source_person_id=? AND LOWER(mentioned_name)=LOWER(?) LIMIT 1",
            (source_person_id, mentioned_name),
        ).fetchone()
        now = time.time()
        if row:
            existing = json.loads(row[1])
            seen = {a.lower() for a in existing}
            merged = existing + [a for a in new_attributes if a.lower() not in seen]
            self._conn.execute(
                "UPDATE social_mentions "
                "SET attributes=?, relationship=COALESCE(?,relationship), updated_at=? "
                "WHERE id=?",
                (json.dumps(merged), relationship, now, row[0]),
            )
        else:
            self._conn.execute(
                "INSERT INTO social_mentions "
                "(source_person_id, mentioned_name, relationship, attributes, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (source_person_id, mentioned_name, relationship, json.dumps(new_attributes), now, now),
            )
        self._conn.commit()

    def find_social_mention_overlaps(self, name_query: str) -> list[dict]:
        """Find social mentions matching name_query from any source_person_id.

        Case-insensitive LIKE search. Used by ProactiveNudgeAgent to find
        the same person mentioned by multiple different speakers.
        """
        rows = self._conn.execute(
            "SELECT id, source_person_id, mentioned_name, relationship, attributes "
            "FROM social_mentions WHERE LOWER(mentioned_name) LIKE LOWER(?) "
            "ORDER BY updated_at DESC",
            (f"%{name_query}%",),
        ).fetchall()
        return [
            {
                "id":               r[0],
                "source_person_id": r[1],
                "name":             r[2],
                "relationship":     r[3],
                "attributes":       json.loads(r[4]),
            }
            for r in rows
        ]

    def get_all_social_mentions(self, limit: int = 200) -> list[dict]:
        """Return social mentions, newest-updated first."""
        rows = self._conn.execute(
            "SELECT id, source_person_id, mentioned_name, relationship, attributes "
            "FROM social_mentions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "id":               r[0],
                "source_person_id": r[1],
                "name":             r[2],
                "relationship":     r[3],
                "attributes":       json.loads(r[4]),
            }
            for r in rows
        ]

    # ── Episodes ───────────────────────────────────────────────────────────────

    def store_episode(
        self,
        person_id:        str,
        episode:          dict,
        session_start_ts: float,
        session_end_ts:   float,
        turn_count:       int,
    ) -> int:
        if config.RETENTION_MODE == "ephemeral":
            return -1  # SB.5: retention-gated — no episode capture under ephemeral
        now = time.time()
        cur = self._conn.execute(
            """INSERT INTO episodes
               (person_id, session_start_ts, session_end_ts, mood,
                key_topics, promises_made, questions_asked, emotional_arc,
                significance, turn_count, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                person_id, session_start_ts, session_end_ts,
                episode.get("mood"),
                json.dumps(episode.get("key_topics") or []),
                json.dumps(episode.get("promises_made") or []),
                json.dumps(episode.get("questions_asked") or []),
                episode.get("emotional_arc"),
                float(episode.get("significance_score") or 0.5),
                turn_count,
                now,
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_recent_episodes(self, person_id: str, limit: int = 5) -> list[dict]:
        rows = self._conn.execute(
            """SELECT mood, key_topics, promises_made, questions_asked,
                      emotional_arc, significance, turn_count, session_end_ts
               FROM episodes WHERE person_id = ?
               ORDER BY session_end_ts DESC LIMIT ?""",
            (person_id, limit),
        ).fetchall()
        return [
            {
                "mood":            r[0],
                "key_topics":      json.loads(r[1]),
                "promises_made":   json.loads(r[2]),
                "questions_asked": json.loads(r[3]),
                "emotional_arc":   r[4],
                "significance":    r[5],
                "turn_count":      r[6],
                "session_end_ts":  r[7],
            }
            for r in rows
        ]

    def get_episode_topics_since(self, since_ts: float) -> list[dict]:
        """All topics across all persons since since_ts — used for cross-person matching."""
        rows = self._conn.execute(
            "SELECT person_id, key_topics, session_end_ts FROM episodes "
            "WHERE session_end_ts > ? ORDER BY session_end_ts DESC",
            (since_ts,),
        ).fetchall()
        return [
            {
                "person_id":      r[0],
                "key_topics":     json.loads(r[1]),
                "session_end_ts": r[2],
            }
            for r in rows
        ]

    # ── Presence log ───────────────────────────────────────────────────────────

    # ── Phase 3B.6 — room synthesis storage ────────────────────────────────
    def store_room_summary(
        self,
        room_session_id: str,
        started_at: float,
        ended_at: float,
        speaker_pids: "list[str]",
        summary: str,
        topic_tags: "list[str] | None" = None,
        safety_flags: "list[dict] | None" = None,
    ) -> None:
        """Phase 3B.6 — persist room-end synthesis result.

        One row per room_session_id (PRIMARY KEY enforces that). If a
        retry hits the same id (e.g. the synthesis task was re-scheduled
        after a partial write), the INSERT OR REPLACE semantic keeps
        the freshest render.
        """
        if config.RETENTION_MODE == "ephemeral":
            return  # SB.5: retention-gated — no room-summary capture under ephemeral
        import json as _json_rs
        self._conn.execute(
            "INSERT OR REPLACE INTO room_summaries "
            "(room_session_id, started_at, ended_at, speaker_pids, "
            " summary, topic_tags, safety_flags, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                room_session_id, started_at, ended_at,
                _json_rs.dumps(list(speaker_pids)),
                summary,
                _json_rs.dumps(list(topic_tags or [])),
                _json_rs.dumps(list(safety_flags or [])),
                time.time(),
            ),
        )
        self._conn.commit()

    def get_recent_room_context(
        self,
        person_id: str,
        hours: float = 24.0,
    ) -> "dict | None":
        """Phase 3B.6 — fetch the most recent room summary that included
        ``person_id`` within the last ``hours``.

        Returns a dict with the deserialized row (speaker_pids,
        topic_tags, safety_flags as lists) or ``None`` if no qualifying
        room. ``person_id in speaker_pids`` is the membership gate —
        prevents leaking other people's rooms to someone who wasn't
        there.
        """
        import json as _json_rr
        if not person_id:
            return None
        cutoff = time.time() - max(0.0, hours) * 3600.0
        rows = self._conn.execute(
            "SELECT room_session_id, started_at, ended_at, speaker_pids, "
            "summary, topic_tags, safety_flags "
            "FROM room_summaries WHERE ended_at > ? ORDER BY ended_at DESC",
            (cutoff,),
        ).fetchall()
        for row in rows:
            (room_id, started_at, ended_at, pids_json,
             summary, topics_json, flags_json) = row
            try:
                pids = _json_rr.loads(pids_json) or []
            except Exception:
                pids = []
            if person_id not in pids:
                continue
            def _safe_loads(raw):
                try:
                    return _json_rr.loads(raw) if raw else []
                except Exception:
                    # OPTIONAL: (#123 PI-3) parses room_summaries.topic_tags / safety_flags —
                    # system-serialized JSON we wrote ourselves, NOT external/LLM input, so the
                    # P0.12 adversarial-input concern does not apply; [] == "no tags/flags".
                    return []
            return {
                "room_session_id": room_id,
                "started_at":      started_at,
                "ended_at":        ended_at,
                "speaker_pids":    pids,
                "summary":         summary,
                "topic_tags":      _safe_loads(topics_json),
                "safety_flags":    _safe_loads(flags_json),
            }
        return None

    def log_presence(self, person_id: str, arrived_at: float, left_at: float) -> None:
        if config.RETENTION_MODE == "ephemeral":
            return  # SB.5: retention-gated — no presence capture under ephemeral
        dt = datetime.datetime.fromtimestamp(arrived_at)
        self._conn.execute(
            """INSERT INTO presence_log
               (person_id, arrived_at, left_at, duration_s,
                day_of_week, hour_of_day, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                person_id, arrived_at, left_at,
                left_at - arrived_at,
                dt.weekday(), dt.hour,
                time.time(),
            ),
        )
        self._conn.commit()

    def get_presence_history(self, person_id: str, limit: int = 30) -> list[dict]:
        rows = self._conn.execute(
            """SELECT arrived_at, left_at, duration_s, day_of_week, hour_of_day
               FROM presence_log WHERE person_id = ?
               ORDER BY arrived_at DESC LIMIT ?""",
            (person_id, limit),
        ).fetchall()
        return [
            {
                "arrived_at":  r[0], "left_at":     r[1],
                "duration_s":  r[2], "day_of_week": r[3],
                "hour_of_day": r[4],
            }
            for r in rows
        ]

    def get_presence_count(self, person_id: str) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM presence_log WHERE person_id = ?", (person_id,)
        ).fetchone()[0]

    # ── Proactive nudges ───────────────────────────────────────────────────────

    def store_nudge(
        self,
        target_person_id: str,
        nudge_type:       str,
        content:          str,
        confidence:       float,
        metadata:         dict,
        expires_at:       float | None = None,
    ) -> int:
        if config.RETENTION_MODE == "ephemeral":
            return -1  # SB.5: retention-gated — no nudge capture under ephemeral
        cur = self._conn.execute(
            """INSERT INTO proactive_nudges
               (target_person_id, nudge_type, content, metadata,
                confidence, generated_at, expires_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                target_person_id, nudge_type, content,
                json.dumps(metadata), confidence,
                time.time(), expires_at,
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_pending_nudges(self, target_person_id: str, limit: int = 3) -> list[dict]:
        now = time.time()
        rows = self._conn.execute(
            """SELECT id, nudge_type, content, confidence, metadata
               FROM proactive_nudges
               WHERE target_person_id = ?
                 AND injected_at IS NULL
                 AND dismissed_at IS NULL
                 AND (expires_at IS NULL OR expires_at > ?)
               ORDER BY confidence DESC, generated_at ASC
               LIMIT ?""",
            (target_person_id, now, limit),
        ).fetchall()
        return [
            {
                "id":         r[0], "nudge_type": r[1],
                "content":    r[2], "confidence": r[3],
                "metadata":   json.loads(r[4]),
            }
            for r in rows
        ]

    def get_recent_visitor_alerts(
        self,
        target_person_id: str,
        hours_back:       float = 24.0,
    ) -> list[dict]:
        """Return VISITOR_ALERT nudges for best_friend within a recent window,
        regardless of injection status.

        Used by the Ollama fallback path (pipeline.py) when the classifier
        gate rejects a `report_identity_mismatch` call on an owner query
        like "who were you talking to?". The rejected turn then routes
        through the offline retry — Ollama has zero context that a visitor
        even existed, so without this read it confabulates "there was no
        one else" (Session 96 Bug 2). Pulling recent VISITOR_ALERT nudges
        (injected OR pending) and injecting the visitor's name + turn count
        + topic hint into Ollama's system_note gives the offline path
        enough grounding to answer honestly.

        Injection status is intentionally ignored: if the alert was already
        shown to the user earlier, it's still relevant to a current owner
        query about the same window. Dismissed nudges and expired nudges
        ARE filtered — those represent explicit user closure.
        """
        cutoff = time.time() - (hours_back * 3600)
        rows = self._conn.execute(
            """SELECT id, content, metadata, generated_at
               FROM proactive_nudges
               WHERE target_person_id = ?
                 AND nudge_type = 'VISITOR_ALERT'
                 AND dismissed_at IS NULL
                 AND (expires_at IS NULL OR expires_at > ?)
                 AND generated_at >= ?
               ORDER BY generated_at DESC""",
            (target_person_id, time.time(), cutoff),
        ).fetchall()
        return [
            {
                "id":           r[0],
                "content":      r[1],
                "metadata":     json.loads(r[2]) if r[2] else {},
                "generated_at": r[3],
            }
            for r in rows
        ]

    def update_visitor_alert_for_promoted_person(
        self,
        person_id: str,
        new_name: str,
    ) -> int:
        """Session 114 Part 5 — when a stranger gets promoted to 'known'
        via update_person_name, sync any pre-promotion VISITOR_ALERT
        nudges so the post-promotion read returns one canonical row
        (correct name + visitor_type='known') rather than stacking two
        alerts about the same visitor.

        Updates `proactive_nudges` rows where ``nudge_type='VISITOR_ALERT'``
        AND ``metadata.visitor_id == person_id``. Read-modify-write on
        the JSON ``metadata`` column (SQLite portable — no JSON_SET
        dependency). Also rewrites the row's ``content`` to use the new
        name so the rendered visitor description stays consistent.

        Returns the number of rows updated.
        """
        # Capture BEFORE any write — same inner-commit gate as migrate_entity_name.
        _in_outer_tx = self._conn.in_transaction
        rows = self._conn.execute(
            "SELECT id, content, metadata FROM proactive_nudges "
            "WHERE nudge_type = 'VISITOR_ALERT' "
            "AND dismissed_at IS NULL",
        ).fetchall()
        updated = 0
        for nudge_id, content, meta_json in rows:
            try:
                meta = json.loads(meta_json) if meta_json else {}
            except Exception:
                meta = {}
            if meta.get("visitor_id") != person_id:
                continue
            old_name = meta.get("visitor_name") or ""
            meta["visitor_name"] = new_name
            meta["visitor_type"] = "known"
            # P0.S7.5.1 D1 — regex-replace the [visitor_name:...] marker
            # regardless of what placeholder is currently in content. The
            # previous literal-substring check (Session 114 Part 5) only
            # fired when the old_name from metadata matched the marker —
            # but _run_visitor_alert writes ASYMMETRIC content
            # (marker="[visitor_name:unknown]") and metadata
            # (visitor_name="visitor") for stranger sessions, so the old
            # check silently no-op'd on every stranger promotion.
            # Regex-replace is robust to the asymmetry (and to any future
            # placeholder drift).
            #
            # Use a LAMBDA replacement (callable) so the replacement
            # string is used verbatim — no interpretation of regex
            # backreferences (\1, \g<name>, \\). Defense-in-depth against
            # future visitor names containing regex special chars in
            # replacement-string context.
            #
            # Canary 2 evidence: 2026-05-19 terminal_output.md:857 + :1187.
            new_content = content
            if content:
                new_marker = f"[visitor_name:{new_name}]"
                new_content = re.sub(
                    r"\[visitor_name:[^\]]+\]",
                    lambda _m: new_marker,
                    content,
                )
            self._conn.execute(
                "UPDATE proactive_nudges SET content = ?, metadata = ? "
                "WHERE id = ?",
                (new_content, json.dumps(meta), nudge_id),
            )
            updated += 1
        if updated:
            if not _in_outer_tx:
                self._conn.commit()
            print(
                f"[BrainDB] update_visitor_alert_for_promoted_person: "
                f"updated {updated} alert(s) for {person_id} → {new_name!r}"
            )
        return updated

    def mark_nudge_injected(self, nudge_id: int) -> None:
        self._conn.execute(
            "UPDATE proactive_nudges SET injected_at = ? WHERE id = ?",
            (time.time(), nudge_id),
        )
        self._conn.commit()

    def dismiss_nudge(self, nudge_id: int) -> None:
        self._conn.execute(
            "UPDATE proactive_nudges SET dismissed_at = ? WHERE id = ?",
            (time.time(), nudge_id),
        )
        self._conn.commit()

    def nudge_exists(
        self,
        target_person_id: str,
        nudge_type:       str,
        content_key:      str,
    ) -> bool:
        """Dedup check — is an equivalent pending nudge already stored?"""
        now = time.time()
        row = self._conn.execute(
            """SELECT 1 FROM proactive_nudges
               WHERE target_person_id = ?
                 AND nudge_type = ?
                 AND content LIKE ?
                 AND injected_at IS NULL
                 AND dismissed_at IS NULL
                 AND (expires_at IS NULL OR expires_at > ?)
               LIMIT 1""",
            (target_person_id, nudge_type, f"%{content_key}%", now),
        ).fetchone()
        return row is not None

    # ── Watchdog alerts ────────────────────────────────────────────────────────

    def store_alert(
        self,
        alert_type: str,
        severity:   str,
        message:    str,
        metadata:   dict,
    ) -> int:
        cur = self._conn.execute(
            """INSERT INTO watchdog_alerts
               (alert_type, severity, message, metadata, created_at)
               VALUES (?,?,?,?,?)""",
            (alert_type, severity, message, json.dumps(metadata), time.time()),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_unresolved_alerts(self, limit: int = 10) -> list[dict]:
        rows = self._conn.execute(
            """SELECT id, alert_type, severity, message, metadata, created_at
               FROM watchdog_alerts WHERE resolved = 0
               ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [
            {
                "id":         r[0], "alert_type": r[1],
                "severity":   r[2], "message":    r[3],
                "metadata":   json.loads(r[4]), "created_at": r[5],
            }
            for r in rows
        ]

    def resolve_alert(self, alert_id: int) -> None:
        self._conn.execute(
            "UPDATE watchdog_alerts SET resolved = 1, resolved_at = ? WHERE id = ?",
            (time.time(), alert_id),
        )
        self._conn.commit()

    # ── VISION_ROADMAP P1.7a — intent divergence log ─────────────────────────
    def log_intent_divergence(
        self,
        *,
        tool_proposed:         str,
        gate_decision:         str,
        user_text:             "str | None"   = None,
        person_id:             "str | None"   = None,
        turn_id:               "int | None"   = None,
        structured_intent:     "str | None"   = None,
        structured_extracted:  "str | None"   = None,
        structured_confidence: "float | None" = None,
        mode:                  str            = "gate",
    ) -> int:
        """One row per gated-tool decision routed through _intent_allows
        (or one passive ``mode='shadow'`` sample from the Phase 5
        canary).

        Called from pipeline._execute_tool's gate-wiring sites. All classifier-
        sidecar fields are nullable — set them when the classifier fired, leave
        as None when the classifier was unavailable (timeout / parse fail /
        shadow-mode disabled) and the regex fallback handled the decision.
        ``gate_decision`` encodes what actually happened (e.g. ``'allow'``,
        ``'reject: intent=casual_conversation expected=assign_own_name'``,
        ``'regex_fallback_allow'``, ``'shadow_sample'``). Phase 5 drift
        detection queries this table to compute classifier-vs-regex
        divergence rates and inspect shadow samples for offline review.

        ``mode`` (Phase 5 / Session 119): defaults to ``'gate'`` so all
        existing call sites keep working unchanged. The 1% canary
        shadow sampler in pipeline.conversation_turn passes
        ``mode='shadow'`` for passive observability rows.

        Keyword-only signature to avoid accidental positional-argument
        misalignment as the schema evolves."""
        cur = self._conn.execute(
            """INSERT INTO intent_divergences
               (turn_id, person_id, user_text, structured_intent,
                structured_extracted, structured_confidence, tool_proposed,
                gate_decision, ts, mode)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                turn_id, person_id, user_text, structured_intent,
                structured_extracted, structured_confidence, tool_proposed,
                gate_decision, time.time(), mode,
            ),
        )
        self._safe_commit()
        return cur.lastrowid

    def get_recent_intent_divergences(self, limit: int = 50) -> list[dict]:
        """Phase 5 drift-detection query surface. Most-recent-first; oldest
        rows fall off once limit is hit. Returns dicts mirroring the schema."""
        rows = self._conn.execute(
            """SELECT id, turn_id, person_id, user_text, structured_intent,
                      structured_extracted, structured_confidence,
                      tool_proposed, gate_decision, reviewed, ts
               FROM intent_divergences
               ORDER BY ts DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [
            {
                "id": r[0], "turn_id": r[1], "person_id": r[2],
                "user_text": r[3], "structured_intent": r[4],
                "structured_extracted": r[5], "structured_confidence": r[6],
                "tool_proposed": r[7], "gate_decision": r[8],
                "reviewed": r[9], "ts": r[10],
            }
            for r in rows
        ]

    def resolve_alerts_by_type(self, alert_type: str) -> None:
        """Resolve all open alerts of a given type in one SQL UPDATE."""
        self._conn.execute(
            "UPDATE watchdog_alerts SET resolved = 1, resolved_at = ? "
            "WHERE alert_type = ? AND resolved = 0",
            (time.time(), alert_type),
        )
        self._conn.commit()

    def unresolved_alert_exists(self, alert_type: str) -> bool:
        """Dedup — prevents filing the same alert twice while it's still open."""
        row = self._conn.execute(
            "SELECT 1 FROM watchdog_alerts WHERE alert_type = ? AND resolved = 0 LIMIT 1",
            (alert_type,),
        ).fetchone()
        return row is not None

    def get_recent_alerts_summary(self) -> str | None:
        alerts = self.get_unresolved_alerts(limit=5)
        if not alerts:
            return None
        now = time.time()
        parts = []
        for a in alerts:
            age_m = int((now - a["created_at"]) / 60)
            parts.append(f"{a['alert_type']} ({a['severity']}, {age_m}m ago)")
        return f"{len(alerts)} unresolved alert(s): " + ", ".join(parts)

    def wipe(self) -> None:
        """Clear all brain.db tables (SQLite only).

        WARNING: Do NOT call this directly in production code.
        Always use BrainOrchestrator.wipe() which also clears the Kuzu graph.
        Calling this alone leaves the graph with stale entity nodes that no
        longer match the wiped SQLite knowledge rows.
        Direct calls are only safe in tests that don't use GraphDB.
        """
        self._conn.executescript("""
            DELETE FROM knowledge;
            DELETE FROM schema_catalog;
            DELETE FROM agent_log;
            DELETE FROM prompt_prefs;
            DELETE FROM object_sightings;
            DELETE FROM object_pattern_questions;
            DELETE FROM object_patterns;
            DELETE FROM social_mentions;
            DELETE FROM episodes;
            DELETE FROM presence_log;
            DELETE FROM proactive_nudges;
            DELETE FROM watchdog_alerts;
            DELETE FROM household_facts;
            DELETE FROM inter_person_relationships;
            DELETE FROM shadow_persons;
            DELETE FROM predicate_stats;
            UPDATE brain_state SET last_turn_id = 0, updated_at = 0 WHERE singleton = 1;
        """)
        self._conn.commit()

    def delete_person_data(self, person_ids: list) -> int:
        """Batch-delete all brain.db rows for a list of person_ids.

        Covers ALL tables that carry person-scoped data. Returns total rows removed.
        Called by BrainOrchestrator.prune_brain_data() after faces.db stranger pruning
        and by person_lifecycle.delete_person_everywhere() for explicit deletion.
        """
        if not person_ids:
            return 0
        ph = ",".join("?" * len(person_ids))
        total = 0
        # P0.S9 D2: explicit transaction wrap (was implicit single-commit pre-fix).
        # Atomicity equivalent (BEGIN IMMEDIATE / COMMIT contract owned by the
        # context manager); matches P0.9.1 ratchet for cross-DB destructive ops.
        with self.transaction():
            for table in ("knowledge", "presence_log", "episodes", "prompt_prefs"):
                cur = self._conn.execute(
                    f"DELETE FROM {table} WHERE person_id IN ({ph})", person_ids
                )
                total += cur.rowcount
            cur = self._conn.execute(
                f"DELETE FROM proactive_nudges WHERE target_person_id IN ({ph})", person_ids
            )
            total += cur.rowcount
            cur = self._conn.execute(
                f"DELETE FROM social_mentions WHERE source_person_id IN ({ph})", person_ids
            )
            total += cur.rowcount
            cur = self._conn.execute(
                f"DELETE FROM inter_person_relationships WHERE person_a IN ({ph}) OR source_speaker IN ({ph})",
                person_ids + person_ids,
            )
            total += cur.rowcount
            # household_facts.source_speakers is a JSON list of person_ids — remove each deleted id.
            for pid in person_ids:
                rows = self._conn.execute(
                    "SELECT id, source_speakers FROM household_facts WHERE source_speakers LIKE ?",
                    (f'%{pid}%',),
                ).fetchall()
                for row_id, ss_json in rows:
                    try:
                        speakers = json.loads(ss_json or "[]")
                    except (ValueError, TypeError):
                        speakers = []
                    updated = [s for s in speakers if s != pid]
                    if updated != speakers:
                        self._conn.execute(
                            "UPDATE household_facts SET source_speakers = ? WHERE id = ?",
                            (json.dumps(updated), row_id),
                        )
                        total += 1
        # NO trailing self._conn.commit() — transaction context manager owns commit.
        return total

    def prune_shadows_mentioning(self, person_id: str, person_name: str) -> int:
        """Remove references to person_id from shadow_persons.known_via JSON.

        Shadows whose known_via becomes empty after removal are deleted entirely.
        Returns the number of shadow rows modified or deleted.
        """
        rows = self._conn.execute(
            "SELECT shadow_id, known_via FROM shadow_persons"
        ).fetchall()
        affected = 0
        # P0.S9 D2: explicit transaction wrap (was implicit single-commit pre-fix).
        with self.transaction():
            for shadow_id, kv_json in rows:
                try:
                    known_via = json.loads(kv_json or "[]")
                except (ValueError, TypeError):
                    known_via = []
                new_via = [entry for entry in known_via if entry.get("person_id") != person_id]
                if len(new_via) == len(known_via):
                    continue
                affected += 1
                if new_via:
                    self._conn.execute(
                        "UPDATE shadow_persons SET known_via = ? WHERE shadow_id = ?",
                        (json.dumps(new_via), shadow_id),
                    )
                else:
                    self._conn.execute("DELETE FROM shadow_persons WHERE shadow_id = ?", (shadow_id,))
        # NO trailing self._conn.commit() — transaction context manager owns commit.
        return affected

    # ── P0.X graph-schema public API ─────────────────────────────────────────

    def get_graph_schema_version(self) -> int:
        """Return the currently stored graph schema version from brain_state."""
        return self._conn.execute(
            "SELECT graph_schema_version FROM brain_state WHERE singleton = 1"
        ).fetchone()[0]

    def update_graph_schema_version(self, version: int) -> None:
        """Commit a new graph schema version to brain_state.

        Commits immediately — caller (BrainOrchestrator._ensure_graph_sync)
        needs the version durable before touching Kuzu so a crash between the
        SQL commit and the Kuzu rebuild doesn't re-trigger the schema-upgrade
        path on next boot (sentinel handles the rebuild instead).
        """
        self._conn.execute(
            "UPDATE brain_state SET graph_schema_version = ? WHERE singleton = 1",
            (version,),
        )
        self._conn.commit()

    def count_active_knowledge_entities(self) -> int:
        """Return the count of distinct active entities in knowledge.

        Used by BrainOrchestrator._ensure_graph_sync for boot-time divergence
        detection: Kuzu has one Entity node per unique entity name, so
        COUNT(DISTINCT entity) (not COUNT(*)) is the correct comparand.
        """
        return self._conn.execute(
            "SELECT COUNT(DISTINCT entity) FROM knowledge "
            "WHERE invalidated_at IS NULL"
        ).fetchone()[0]

    # ── P0.X layering-cleanup wrappers ───────────────────────────────────────
    # Raw _conn accesses scattered across BrainOrchestrator and SchemaNormAgent
    # have been replaced with these public methods so test_layering_invariants
    # can enforce the boundary (Step 2.H).

    def count_schema_catalog_entries(self) -> int:
        """Return COUNT(*) of schema_catalog rows."""
        return self._conn.execute(
            "SELECT COUNT(*) FROM schema_catalog"
        ).fetchone()[0]

    def get_knowledge_topic_tags_for_persons(
        self, person_ids: list[str], since: float, until: float
    ) -> list[str]:
        """Return top-10 entity names by frequency for the given persons in [since, until]."""
        if not person_ids:
            return []
        placeholders = ",".join("?" for _ in person_ids)
        rows = self._conn.execute(
            f"SELECT entity, COUNT(*) AS n FROM knowledge "
            f"WHERE person_id IN ({placeholders}) "
            f"AND created_at >= ? AND created_at <= ? "
            f"GROUP BY entity ORDER BY n DESC LIMIT 10",
            (*person_ids, since, until),
        ).fetchall()
        return [entity for entity, _n in rows if entity]

    def get_knowledge_rows_for_persons(
        self, person_ids: list[str], since: float, until: float
    ) -> list[tuple[str, str, str, str]]:
        """Return (person_id, entity, attribute, value) tuples for the given persons in [since, until]."""
        if not person_ids:
            return []
        placeholders = ",".join("?" for _ in person_ids)
        rows = self._conn.execute(
            f"SELECT person_id, entity, attribute, value FROM knowledge "
            f"WHERE person_id IN ({placeholders}) "
            f"AND created_at >= ? AND created_at <= ? "
            f"AND invalidated_at IS NULL",
            (*person_ids, since, until),
        ).fetchall()
        return list(rows)

    def get_true_valued_attributes(self, person_id: str) -> list[str]:
        """Return distinct attributes whose value is 'true' or 'yes' for person."""
        rows = self._conn.execute(
            "SELECT DISTINCT attribute FROM knowledge "
            "WHERE person_id = ? AND invalidated_at IS NULL "
            "AND (value = 'true' OR value = 'yes')",
            (person_id,),
        ).fetchall()
        return [r[0] for r in rows if r[0]]

    def get_shadow_person_names_since(self, cutoff: float) -> list[str]:
        """Return known_name values from shadow_persons last_mentioned >= cutoff."""
        rows = self._conn.execute(
            "SELECT known_name FROM shadow_persons WHERE last_mentioned >= ?",
            (cutoff,),
        ).fetchall()
        return [r[0] for r in rows if r[0]]

    def get_latest_pref_id(
        self, person_id: str, pref_type: str, content: str
    ) -> int | None:
        """Return id of the most recently inserted matching prompt_prefs row, or None."""
        row = self._conn.execute(
            "SELECT id FROM prompt_prefs "
            "WHERE person_id=? AND pref_type=? AND content=? "
            "ORDER BY id DESC LIMIT 1",
            (person_id, pref_type, content),
        ).fetchone()
        return row[0] if row else None

    def checkpoint_wal(self) -> None:
        """Flush the WAL into the main DB file (TRUNCATE mode).

        Called at the end of each dream cycle so the -wal sidecar stays
        small and backup copies are self-contained."""
        try:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception as _e:
            print(f"[BrainDB] WAL checkpoint failed: {_e!r}")

    def close(self) -> None:
        self._conn.close()
