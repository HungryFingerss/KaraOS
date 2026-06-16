"""core/brain_agent/orchestrator.py — BrainOrchestrator — multi-agent coordination + Kuzu crash-atomicity (sentinel + _ensure_graph_sync) + conversation-reaction helpers.

Extracted VERBATIM from core/brain_agent.py (P1.A1 SP-2 SP-3).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import asyncio
import httpx
import json
import sqlite3
import time
from pathlib import Path

from core.config import (
    AGENT_LOG_MAX_AGE_DAYS,
    AGENT_LOG_MAX_ROWS,
    BRAIN_AGENT_CONTEXT_TURNS,
    BRAIN_AGENT_POLL_INTERVAL,
    BRAIN_DB_PATH,
    BRIEFING_VISITOR_MIN_TURNS,
    CONFIDENCE_BOOST,
    DB_PATH,
    DEFAULT_SYSTEM_NAME,
    DREAM_DECAY_WRITE_THRESHOLD,
    DREAM_PRUNE_FLOOR,
    EMBED_MIN_CONFIDENCE,
    EPISODE_MAX_ROWS,
    GRAPH_DB_PATH,
    GRAPH_SCHEMA_VERSION,
    INSIGHT_MIN_TURNS,
    INTRA_PREF_TURN,
    INTRA_PREF_TURNS_LIMIT,
    KNOWLEDGE_MAX_ROWS,
    MAX_RETROACTIVE_FACTS,
    PATTERN_Q_MAX_AGE_DAYS,
    PREDICATE_CONFIDENCE_CAP,
    PREDICATE_VOLATILITY_THRESHOLD,
    PREF_ANALYSIS_TURNS,
    PREF_BLACKLIST_PATTERNS,
    PREF_DEDUP_THRESHOLD,
    PRESENCE_MAX_ROWS,
    RETRO_STALE_PENALTY,
    SOCIAL_MENTIONS_MAX_ROWS,
    WATCHDOG_MAX_AGE_DAYS,
)
import core.config as config  # SB.3 — read config.ACTIVE_AGENTS by attribute (Lock 2; NEVER a from-import)
from core.sanitize import wrap_user_input
from core.log_utils import _now_log_ts
from core.brain_agent._llm import _call_llm_chat
from core.brain_agent.privacy import _is_safety_critical_attribute
from core.brain_agent.context import _format_context_lines
from core.brain_agent.memory.graph import GraphDB
from core.brain_agent.memory.store import BrainDB
from core.brain_agent.agents.triage import TriageAgent
from core.brain_agent.agents.extraction import (
    Extraction,
    ExtractionAgent,
)
from core.brain_agent.agents.contradiction import ContradictionAgent
from core.brain_agent.agents.prefs import (
    FrictionDetectionAgent,
    PromptPrefAgent,
)
from core.brain_agent.agents.household import HouseholdExtractionAgent
from core.brain_agent.agents.schema import SchemaNormAgent
from core.brain_agent.agents.embedding import EmbeddingAgent
from core.brain_agent.agents.social import (
    IdentityAgent,
    SocialGraphAgent,
)
from core.brain_agent.agents.briefing import (
    BriefingAgent,
    ConversationInsightAgent,
)
from core.brain_agent.agents.routine import RoutineAgent
from core.brain_agent.agents.nudge import ProactiveNudgeAgent
from core.brain_agent.agents.watchdog import WatchdogAgent

from profiles._registry import AGENT_REGISTRY  # SB.3 — agent-membership registry (pure data)

# SB.3 — registry class-name STRING → the class object. The orchestrator owns
# the resolution (it already imports all 15); profiles/_registry.py stays pure
# data with name strings → no profiles/→core/ coupling (D4).
_CLASS_BY_NAME = {
    "TriageAgent": TriageAgent,
    "ExtractionAgent": ExtractionAgent,
    "ContradictionAgent": ContradictionAgent,
    "SchemaNormAgent": SchemaNormAgent,
    "EmbeddingAgent": EmbeddingAgent,
    "SocialGraphAgent": SocialGraphAgent,
    "FrictionDetectionAgent": FrictionDetectionAgent,
    "HouseholdExtractionAgent": HouseholdExtractionAgent,
    "PromptPrefAgent": PromptPrefAgent,
    "ConversationInsightAgent": ConversationInsightAgent,
    "RoutineAgent": RoutineAgent,
    "ProactiveNudgeAgent": ProactiveNudgeAgent,
    "BriefingAgent": BriefingAgent,
    "IdentityAgent": IdentityAgent,
    "WatchdogAgent": WatchdogAgent,
}

# SB.3 — registry name → the existing self.<attr>. Keeps every call site's
# attribute name unchanged (the diff is "build from registry + presence guard",
# not a rename) — D-neutrality.
_ATTR = {
    "triage": "_triage",
    "extraction": "_extractor",
    "contradiction": "_contradictor",
    "schema": "_schema_norm",
    "embed": "_embed_agent",
    "social": "_social_graph",
    "friction": "_friction_agent",
    "household": "_household_agent",
    "prefs": "_pref_agent",
    "insight": "_insight_agent",
    "routine": "_routine_agent",
    "nudge": "_nudge_agent",
    "briefing": "_briefing_agent",
    "identity": "_identity_agent",
    "watchdog": "_watchdog",
}


def _topo_order(active) -> "list[str]":
    """SB.3 — order `active` agent names so any inter-agent dep builds first
    (the one edge today: schema deps on embed → embed before schema). Stable on
    the registry insertion order otherwise. DFS over deps that are registry keys."""
    active_set = set(active)
    placed: "set[str]" = set()
    ordered: "list[str]" = []

    def _place(name: str) -> None:
        if name in placed:
            return
        for dep in AGENT_REGISTRY[name]["deps"]:
            if dep in AGENT_REGISTRY and dep in active_set:
                _place(dep)
        placed.add(name)
        ordered.append(name)

    for name in AGENT_REGISTRY:  # registry order = stable base
        if name in active_set:
            _place(name)
    return ordered


def _is_phantom_name(
    candidate: str,
    known_names: "list[str]",
    *,
    jw_threshold: float = 0.85,
) -> "str | None":
    """Session 114 Part 2 — phantom-person fuzzy match.

    Returns the matched ``known_name`` if ``candidate`` is plausibly a
    STT-mangled form of an existing name (phonetic via jellyfish
    Double-Metaphone OR Jaro-Winkler similarity ≥ ``jw_threshold``).
    Returns None when no match — caller should proceed with normal
    shadow insertion.

    Phonetic match uses metaphone codes (already a dep from
    Session 41 G4). Jaro-Winkler catches typo-class matches that share
    no phonetic code (e.g. "Lexie" vs "Lexi" — same Metaphone code, but
    short prefixes drift cheaply across vowel changes).
    """
    if not candidate or not known_names:
        return None
    try:
        import jellyfish as _jelly
    except Exception:
        # OPTIONAL: (#123) jellyfish is an optional phonetic-match dependency — graceful
        # degradation to "no phonetic candidate" when it isn't installed.
        return None
    cand = candidate.strip()
    if not cand:
        return None
    cand_lc = cand.lower()
    cand_meta = _jelly.metaphone(cand) or ""
    best_match = None
    for kn in known_names:
        if not kn:
            continue
        kn_lc = kn.strip().lower()
        if not kn_lc:
            continue
        # Exact / case-insensitive direct hit always wins.
        if kn_lc == cand_lc:
            return kn
        # Phonetic match.
        if cand_meta and _jelly.metaphone(kn) == cand_meta:
            return kn
        # Jaro-Winkler — captures typo-class drift even when phonetic
        # codes diverge slightly.
        try:
            jw = _jelly.jaro_winkler_similarity(cand_lc, kn_lc)
        except Exception:
            jw = 0.0
        if jw >= jw_threshold:
            best_match = kn
            # Don't break — exact / phonetic match further in the list
            # would still take precedence. But Jaro-Winkler is the
            # weakest signal; use only as fallback.
    return best_match


_RECALL_SIGNALS = (
    "i remember", "you mentioned", "you said", "last time",
    "you told me", "i recall", "as you said", "you've told",
)


_CONFIRM_SIGNALS = frozenset({
    "yes", "yeah", "yep", "correct", "exactly", "right",
    "true", "indeed", "absolutely", "that's right",
})


_DENY_SIGNALS = frozenset({
    "no", "nope", "wrong", "incorrect", "never",
    "false", "not really", "actually", "that's not",
})


def _get_prior_ai_claim(context: list[dict]) -> str | None:
    """Return the last assistant turn's content if it recalled a stored fact, else None."""
    if not context or context[-1]["role"] != "assistant":
        return None
    text_lower = context[-1]["content"].lower()
    if any(sig in text_lower for sig in _RECALL_SIGNALS):
        return context[-1]["content"]
    return None


def _get_prior_assistant_turn(context: list[dict]) -> str | None:
    """Return the immediately preceding assistant turn's content, or None."""
    if not context or context[-1]["role"] != "assistant":
        return None
    return context[-1]["content"]


def _classify_user_reaction(content: str) -> str:
    """Classify user turn as 'confirm', 'deny', or 'neutral' relative to prior AI claim."""
    words = set(content.lower().split())
    if words & _CONFIRM_SIGNALS:
        return "confirm"
    if words & _DENY_SIGNALS:
        return "deny"
    # Check for sentence-level deny patterns
    lower = content.lower()
    if any(p in lower for p in ("that's wrong", "not anymore", "i stopped", "never said")):
        return "deny"
    return "neutral"


class BrainOrchestrator:
    """Coordinates all brain agents. Runs as a background asyncio task.

    Polls conversation_log in faces.db for new turns (turn_id >
    brain_state.last_turn_id), runs each turn through the three-agent
    pipeline, and stores extracted knowledge to brain.db.

    Completely decoupled from the conversation pipeline — the conversation
    never waits for the brain. Memory extraction happens asynchronously
    and knowledge is available by the next turn at human conversation pace.

    Crash-safe: last_turn_id is written atomically after each turn, so a
    restart resumes exactly where it left off. All graph writes use
    REPLACE semantics to prevent duplicates on retry.
    """

    def _build_agents(self, only=None) -> None:
        """SB.3 — construct the registered agents from ``config.ACTIVE_AGENTS``.

        Used by BOTH construction sites (PI-1): ``__init__`` (``only=None`` →
        build the full active set; an unregistered agent's attribute is set to
        ``None``) and ``reopen_connections`` (``only={dep-tags}`` → rebuild ONLY
        the active agents bound to a reopened source, i.e. the DB-handle agents).
        Topo-respects embed→schema. Companion registers all 15 → identical to the
        prior hardcoded blocks → behavior-neutral.
        """
        active = config.ACTIVE_AGENTS
        sources = {"http": self._http, "brain_db": self._brain_db,
                   "graph_db": self._graph_db, "faces_conn": self._faces_conn}
        if only is None:
            # __init__ path: an unregistered agent's attribute is None (set once up front).
            for name in AGENT_REGISTRY:
                if name not in active:
                    setattr(self, _ATTR[name], None)
        for name in _topo_order(active):
            spec = AGENT_REGISTRY[name]
            if only is not None and not (set(spec["deps"]) & only):
                continue  # reset path: only rebuild agents bound to a reopened source
            cls = _CLASS_BY_NAME[spec["class"]]
            args = [self._embed_agent if d == "embed" else sources[d] for d in spec["deps"]]
            setattr(self, _ATTR[name], cls(*args))

    def __init__(self, shutdown_event: asyncio.Event, *,
                 brain_db_path=None, graph_db_path=None, faces_db_path=None):
        self._shutdown     = shutdown_event
        self._trigger      = asyncio.Event()   # fired by pipeline after log_turn
        # Store resolved paths so reopen_connections() uses the same locations.
        self._brain_db_path  = brain_db_path  if brain_db_path  is not None else BRAIN_DB_PATH
        self._graph_db_path  = graph_db_path  if graph_db_path  is not None else GRAPH_DB_PATH
        self._faces_db_path  = str(faces_db_path if faces_db_path is not None else DB_PATH)
        self._brain_db     = BrainDB(self._brain_db_path)
        # P0.X: if a schema upgrade is pending, write the sentinel BEFORE constructing
        # GraphDB — GraphDB.__init__ calls _init_schema() which may fail during upgrade.
        if self._brain_db.get_graph_schema_version() < GRAPH_SCHEMA_VERSION:
            self._mark_kuzu_dirty()
        self._graph_db     = GraphDB(self._graph_db_path)
        # Separate read-only connection to faces.db — WAL mode allows this
        # to coexist safely with pipeline writes.
        self._faces_conn   = sqlite3.connect(
            self._faces_db_path, check_same_thread=False,
            isolation_level="IMMEDIATE",  # P0.9.1 Imp-1
        )
        self._http         = httpx.AsyncClient(timeout=20.0)
        self._build_agents()  # SB.3 — registry-driven construction (companion: all 15, byte-identical)
        self._system_name: str = DEFAULT_SYSTEM_NAME  # updated by pipeline when system_name tool fires
        # Per-session state (keyed by person_id)
        self._session_turn_counts: dict[str, int]   = {}
        self._intra_pref_done:     set[str]          = set()
        self._session_start_ts:    dict[str, float]  = {}   # first turn ts this session
        # Identity-dispute registry: person_ids whose current session has been flagged
        # as disputed (speaker contradicted the sensor). While listed, extraction is
        # paused so we don't pollute either person's knowledge with contradictory facts.
        self._disputed_persons:    set[str]          = set()
        self._kuzu_degraded: bool = False
        self._ensure_graph_sync()

    def _kuzu_sentinel_path(self) -> "Path":
        p = Path(self._graph_db_path)
        return p.parent / (p.name + ".dirty")

    def _mark_kuzu_dirty(self) -> None:
        try:
            self._kuzu_sentinel_path().touch()
        except Exception:
            pass  # CLEANUP: sentinel write failure is non-fatal

    def _clear_kuzu_dirty(self) -> None:
        try:
            self._kuzu_sentinel_path().unlink(missing_ok=True)
        except Exception:
            pass  # CLEANUP: sentinel clear failure is non-fatal

    def _ensure_graph_sync(self) -> None:
        """Rebuild graph from SQLite if needed.

        Handles two cases:
        1. Cold start / crash recovery: graph is empty but SQLite has rows.
        2. Schema upgrade: GRAPH_SCHEMA_VERSION bumped — Kuzu REL tables can't
           be ALTER TABLE'd, so we wipe the graph and rebuild with new schema.

        P0.B3 D1 ORDERING INVARIANT (Finding 2 board-meeting 2026-05-21 fix):
          1. Capture `_did_schema_upgrade = (stored_version < GRAPH_SCHEMA_VERSION)`
             at function entry — BEFORE any state mutation. This is the in-flight
             intent flag; tells the success path whether to commit the SQL version
             bump at the end.
          2. _mark_kuzu_dirty() FIRST — sentinel SET BEFORE any destructive op.
          3. IF schema upgrade pending: drop_schema() + _init_schema() (Kuzu ops).
             Crash here: kuzu_degraded=True, sentinel persists, stored_version=OLD
             → next boot re-enters via predicate at step 1.
          4. Compute need_rebuild via the migration-block-success OR boot-reconciliation
             (sentinel-exists OR entity-count-mismatch).
          5. IF need_rebuild AND NOT degraded: rebuild(knowledge_rows). Crash here:
             kuzu_degraded=True, sentinel persists, stored_version=OLD → next boot
             re-enters via predicate at step 1.
          6. _clear_kuzu_dirty() ONLY after rebuild() success.
          7. IF `_did_schema_upgrade` AND NOT degraded: update_graph_schema_version(NEW)
             — SQL commit ONLY at the end, AFTER Kuzu schema + data both at NEW + sentinel
             cleared. This is the LOAD-BEARING fix: pre-P0.B3 the SQL bump happened at step
             3-pre-Kuzu-ops, which left SQL=NEW + Kuzu=PARTIAL on crash; the migration
             predicate at step 1 became FALSE on next boot, silently trapping the system
             in permanent _kuzu_degraded=True with no operator-visible recovery signal.
             Post-P0.B3 the SQL bump lands ONLY at full success; any crash before this
             leaves stored_version=OLD → next boot retries idempotently.
          8. Sentinel-only rebuild paths (boot reconciliation, count mismatch) MUST NOT
             bump the SQL version — `_did_schema_upgrade=False` gates this correctly.
          9. degraded-mode caught-but-unfixable crashes leave sentinel + stored_version=OLD
             on disk → next process restart re-enters the migration block fresh + retries.
         10. Cross-spec invariant: P0.X SCHEMA_MIGRATION pattern's "SQL-first" framing
             applies to paired DATA writes (brain.db row + Kuzu edge). For the version
             BUMP itself, SQL-LAST is correct because SQL is the source-of-truth FOR
             which schema-state-is-canonical — committing it prematurely commits a
             lie. P0.X behavior for paired data writes is unchanged.
        """
        stored_version = self._brain_db.get_graph_schema_version()
        _did_schema_upgrade = stored_version < GRAPH_SCHEMA_VERSION  # P0.B3 D1 intent flag

        need_rebuild = False
        if _did_schema_upgrade:
            print(
                f"[BrainAgent] Graph schema v{stored_version}→v{GRAPH_SCHEMA_VERSION}: "
                "wiping Kuzu graph for rebuild with new schema"
            )
            # P0.B3 D1: SQL version bump REMOVED from this block per Finding 2 fix.
            # Sentinel + Kuzu ops only here; SQL commit deferred to the rebuild-success
            # branch below, gated on `_did_schema_upgrade`. See function docstring
            # ORDERING INVARIANT step 7 for rationale.
            self._mark_kuzu_dirty()
            try:
                self._graph_db.drop_schema()
                self._graph_db._init_schema()
                need_rebuild = True
            except Exception as e:
                self._kuzu_degraded = True
                print(f"[BrainAgent] Graph schema migration failed — degraded mode: {e!r}")

        # Boot reconciliation: sentinel OR entity-count mismatch.
        if not need_rebuild:
            if self._kuzu_sentinel_path().exists():
                need_rebuild = True
            else:
                sql_entity_count = self._brain_db.count_active_knowledge_entities()
                kuzu_entity_count = self._graph_db.entity_count()
                if sql_entity_count != kuzu_entity_count:
                    need_rebuild = True

        if need_rebuild and not self._kuzu_degraded:
            knowledge_rows = self._brain_db.get_all_knowledge_rows()
            try:
                if knowledge_rows:
                    # P0.S7.D-B observability — surface scale-of-pain in canary logs
                    # (auditor obs B). Measures wall-clock + emits entity_count +
                    # edge_count so production rebuilds (v2→v3 schema upgrade) can
                    # be reasoned about empirically. `stored_version` is the pre-bump
                    # version captured at function entry (the SQL bump lands AFTER
                    # `_clear_kuzu_dirty()` below per P0.B3 D1); report the jump
                    # against the pre-bump baseline explicitly.
                    _rebuild_t0 = time.time()
                    self._graph_db.rebuild(knowledge_rows)
                    _rebuild_secs = time.monotonic() - _rebuild_t0
                    _ent_count = self._graph_db.entity_count()
                    print(
                        f"[BrainAgent] Graph rebuilt from {len(knowledge_rows)} SQLite rows"
                    )
                    print(
                        f"[Schema] Graph rebuild v{stored_version}\u2192v{GRAPH_SCHEMA_VERSION} "
                        f"completed in {_rebuild_secs:.2f}s "
                        f"({_ent_count} entities, {len(knowledge_rows)} edges)"
                    )
                self._clear_kuzu_dirty()
                # P0.B3 D1 (Finding 2 board-meeting 2026-05-21 fix): SQL version bump
                # ONLY here — after rebuild success + sentinel clear. Gated on
                # `_did_schema_upgrade` so sentinel-only rebuilds (boot reconciliation,
                # count mismatch) do NOT bump the version. See function docstring
                # ORDERING INVARIANT step 7 for the load-bearing rationale (pre-fix:
                # SQL=NEW + Kuzu=PARTIAL on crash trapped boot in permanent degraded).
                if _did_schema_upgrade:
                    self._brain_db.update_graph_schema_version(GRAPH_SCHEMA_VERSION)
            except Exception as e:
                self._kuzu_degraded = True
                print(f"[BrainAgent] Graph rebuild failed at boot — degraded mode: {e!r}")

    def _schedule_startup_tasks(self) -> None:
        """Schedule background tasks that should run once after startup."""
        if self._schema_norm is not None:  # SB.3 presence guard
            asyncio.create_task(self._schema_norm.maybe_run())
        asyncio.create_task(self._backfill_embeddings())   # Item 5: embed pre-Phase-3 rows

    @property
    def brain_db(self) -> "BrainDB":
        """Public read access to the brain knowledge store.

        Pipeline query paths (visitor alerts, room context, core memory,
        knowledge search, intent logging) use this instead of reaching
        through the private _brain_db attribute. P1.A1-slice layering fix.
        """
        return self._brain_db

    def notify(self) -> None:
        """Wake the brain agent immediately to process new turns.

        Called by the pipeline after db.log_turn() so extraction starts
        during TTS playback rather than waiting for the next poll interval.
        Facts are then ready in brain.db by the time the user speaks again.
        """
        print(f"[BrainAgent] Notify — waking agent loop")
        self._trigger.set()

    def mark_disputed(self, person_id: str) -> None:
        """Mark a person's current session as identity-disputed (pauses extraction)."""
        self._disputed_persons.add(person_id)

    def clear_disputed(self, person_id: str) -> None:
        """Clear the dispute flag for a person (e.g. on resolution or session end)."""
        self._disputed_persons.discard(person_id)

    def on_identity_confirmed(self, person_id: str, old_name: str, new_name: str) -> None:
        """Atomic-within-brain.db identity promotion chain.

        Storage ordering (caller must have already committed faces.db):
            1. CALLER (before this fn): faces.db UPDATE persons SET name=?, type=?  (atomic)
            2. brain.db transaction (this fn) — all-or-nothing:
               - migrate_entity_name(old, new, person_id)
               - promote_shadow_to_confirmed(new, person_id)
               - update_visitor_alert_for_promoted_person(person_id, new)
               - get_knowledge_rows_for_kuzu (read-after-write, sees post-rename rows)
            3. brain_graph: rebuild_entity_from_knowledge (after brain.db commit)

        Crash recovery:
            - Crash between step 1 and 2: faces.db has new name; brain.db rolls back;
              old facts still under old name. Re-running promotion is idempotent.
            - Crash mid-step-2: brain.db rolls back atomically.
            - Crash between step 2 and 3: brain.db consistent; graph stale.
              rebuild_entity_from_knowledge self-heals on next graph access.
        """
        kuzu_rows = None
        try:
            with self._brain_db.transaction():
                self._brain_db.migrate_entity_name(old_name, new_name, person_id)
                self._brain_db.promote_shadow_to_confirmed(new_name, person_id)
                # Session 114 Part 5 — visitor alert dedup at promotion time.
                self._brain_db.update_visitor_alert_for_promoted_person(
                    person_id, new_name,
                )
                # Read-after-write within the transaction sees post-rename rows.
                kuzu_rows = self._brain_db.get_knowledge_rows_for_kuzu(person_id, new_name)
        except Exception as e:
            print(
                f"[BrainOrchestrator] on_identity_confirmed brain.db transaction failed: {e!r}"
            )
            raise  # RAISE: caller must know

        if self._graph_db and kuzu_rows is not None:
            self._mark_kuzu_dirty()  # Eager sentinel BEFORE Kuzu op.
            try:
                self._graph_db.rebuild_entity_from_knowledge(new_name, kuzu_rows)
                self._clear_kuzu_dirty()
            except Exception as e:
                print(
                    f"[BrainOrchestrator] on_identity_confirmed graph rebuild failed "
                    f"(brain.db OK, sentinel written for next-boot): {e!r}"
                )
                raise  # RAISE: sentinel preserved for next-boot

    def _persist_extraction_to_kuzu(self, facts, turn_id: int) -> None:
        """Write extracted facts to Kuzu graph. SWALLOW pattern — brain.db is authoritative.

        P0.X: degraded mode or Kuzu write failure → sentinel written, exception swallowed.
        """
        if self._kuzu_degraded:
            return
        try:
            for fact in facts:
                self._graph_db.upsert_entity(fact.entity, fact.entity_type)
        except Exception as e:
            self._mark_kuzu_dirty()  # SWALLOW: sentinel for next-boot heal
            print(
                f"[BrainAgent] Kuzu write failed in _persist_extraction_to_kuzu "
                f"(turn {turn_id}): {e!r}"
            )

    def notify_session_end(self, person_id: str) -> None:
        """Called on face-loss for any person with an active session.

        Flushes remaining unprocessed turns (via notify) then schedules all
        session-end background tasks: preference analysis, episode insight,
        presence logging, nudge generation, and spatial pattern analysis.
        Resets per-session state so the next session starts clean.

        Identity-disputed sessions skip every synthesis task — the turns may
        belong to someone other than the sensor-matched person, and running
        pref/insight/presence/nudge/household analysis would permanently
        attribute them to the wrong identity. Per-session state is still
        reset below so the next encounter starts clean.
        """
        row = self._faces_conn.execute("SELECT name FROM persons WHERE id = ?", (person_id,)).fetchone()
        pname_log = row[0] if row else person_id
        is_disputed = person_id in self._disputed_persons
        if is_disputed:
            print(
                f"[BrainAgent] Session end: {pname_log} ({person_id}) — "
                f"IDENTITY DISPUTED, skipping all synthesis tasks"
            )
        else:
            print(f"[BrainAgent] Session end: {pname_log} ({person_id}) — launching async tasks")
        self.notify()
        # Capture session start time BEFORE popping — async tasks need it.
        started = self._session_start_ts.pop(person_id, None)
        # SYNTHESIS TASKS — all gated on dispute flag. When adding a new session-end
        # helper, add it INSIDE this `if not is_disputed:` block so it also respects
        # the dispute gate by default.
        if not is_disputed:
            asyncio.create_task(self._run_pref_analysis(person_id))
            asyncio.create_task(self._run_insight_analysis(person_id, started))
            asyncio.create_task(self._run_presence_log(person_id, started))
            asyncio.create_task(self._run_nudge_generation(person_id))
            asyncio.create_task(self._run_visitor_alert(person_id))
            if started:
                row = self._faces_conn.execute(
                    "SELECT name FROM persons WHERE id = ?", (person_id,)
                ).fetchone()
                pname = row[0] if row else person_id
                asyncio.create_task(self._run_household_session_end(person_id, pname, started))
        # Reset per-session state for next encounter
        self._session_turn_counts.pop(person_id, None)
        self._intra_pref_done.discard(person_id)

    async def _run_insight_analysis(self, person_id: str, started: float | None = None) -> None:
        """Generate a structured episode summary for the completed session."""
        if not started:
            return
        ended = time.time()

        row = self._faces_conn.execute(
            "SELECT name FROM persons WHERE id = ?", (person_id,)
        ).fetchone()
        person_name = row[0] if row else person_id

        turns_raw = self._faces_conn.execute(
            """SELECT role, content FROM conversation_log
               WHERE person_id = ? AND ts >= ?
               ORDER BY id ASC""",
            (person_id, started),
        ).fetchall()
        turns = [{"role": r[0], "content": r[1]} for r in turns_raw]
        if len(turns) < INSIGHT_MIN_TURNS:
            return

        if self._insight_agent is None:  # SB.3 presence guard
            return
        episode = await self._insight_agent.analyze(
            person_name, turns, started, ended
        )
        if episode:
            self._brain_db.store_episode(
                person_id, episode, started, ended, len(turns)
            )
            print(
                f"[InsightAgent] Episode stored for {person_name}: "
                f"mood={episode.get('mood')} sig={episode.get('significance_score')}"
            )

    async def _run_presence_log(self, person_id: str, started: float | None = None) -> None:
        """Log the completed visit window and run routine pattern detection."""
        if not started:
            return
        self._brain_db.log_presence(person_id, started, time.time())

        row = self._faces_conn.execute(
            "SELECT name FROM persons WHERE id = ?", (person_id,)
        ).fetchone()
        if not row:
            return
        person_name = row[0]
        loop = asyncio.get_event_loop()
        if self._routine_agent is not None:  # SB.3 presence guard
            await loop.run_in_executor(
                None, self._routine_agent.analyze, person_id, person_name
            )

    async def _run_nudge_generation(self, person_id: str) -> None:
        """Run all ProactiveNudgeAgent passes for the completed session."""
        row = self._faces_conn.execute(
            "SELECT name FROM persons WHERE id = ?", (person_id,)
        ).fetchone()
        if not row:
            return
        person_name = row[0]
        if self._nudge_agent is None:  # SB.3 presence guard
            return
        loop = asyncio.get_event_loop()
        # Cross-person inference needs faces_conn for source-person name lookups
        await loop.run_in_executor(
            None,
            self._nudge_agent.run_cross_person_inference,
            person_id, person_name, self._faces_conn, self._system_name,
        )
        await loop.run_in_executor(
            None, self._nudge_agent.run_intention_followup, person_id, person_name
        )
        await loop.run_in_executor(
            None, self._nudge_agent.run_memory_prompts, person_id, person_name
        )

    async def synthesize_room(
        self,
        room_session_id: str,
        speaker_pids: "list[str]",
        started_at: "float | None" = None,
    ) -> None:
        """Phase 3B.6 — room-end synthesis. Called fire-and-forget from
        `_on_room_end`. Three parallel tasks:

          A. Topic aggregation — pure DB, cheap. Fetches knowledge rows
             (extraction-agent output) with ts in the room window and
             gathers distinct ``entity`` values for the top topic tags.
          B. Safety flag aggregation — pure DB. Filters knowledge rows
             matching ``SAFETY_CRITICAL_ATTRIBUTE_PATTERNS`` (Session
             105 Bug N) with per-speaker attribution — so a visitor
             who expressed suicidal thoughts while in the room shows
             up in the room's safety summary even if the attribute
             was logged under their own pid.
          C. Narrative summary — LLM call with bounded timeout. Renders
             1-2 sentences for greeting enrichment. On timeout or
             failure, falls back to a topic-tag-only string so the row
             still has a non-empty summary (never blocks room end).

        Gated on ``ROOM_END_SYNTHESIS_ENABLED`` — one-line rollback via
        flag if a live canary exposes a regression. Single-person room
        sessions skip synthesis (no rich multi-person context to
        summarize; the per-person session-end path already captures
        single-speaker insight).
        """
        import json as _json_sr
        import re as _re_sr
        from core.config import (
            ROOM_END_SYNTHESIS_ENABLED as _ENABLED,
            ROOM_SUMMARY_LLM_TIMEOUT_SECS as _LLM_TIMEOUT,
            SAFETY_CRITICAL_ATTRIBUTE_PATTERNS as _SAFETY_PAT,
        )
        if not _ENABLED:
            return
        if not room_session_id or not speaker_pids:
            return
        if len(speaker_pids) < 2:
            # Single-person room — per-person session-end synthesis
            # already handles this; no cross-speaker context to add.
            return

        # Determine time window from conversation_log rows that carry
        # this room_session_id (most authoritative — Session 107's
        # log_turn stamp drives everything downstream).
        row = self._faces_conn.execute(
            "SELECT MIN(ts), MAX(ts), COUNT(*) FROM conversation_log "
            "WHERE room_session_id = ?",
            (room_session_id,),
        ).fetchone()
        if not row or row[2] == 0:
            print(f"[Room] synthesize_room({room_session_id}) — no turns logged, skipping")
            return
        db_started, db_ended, turn_count = row
        # started_at kwarg wins if caller supplies it (matches room-mint
        # time, not first-turn ts). Ended_at comes from last turn.
        started_at = started_at if started_at is not None else db_started
        ended_at = time.time()

        # --- (A) Topic aggregation ----------------------------------------
        topic_tags: list[str] = []
        try:
            # Pull distinct entity values extracted from turns logged by
            # any speaker in this room during the window.
            topic_tags = self._brain_db.get_knowledge_topic_tags_for_persons(
                speaker_pids, started_at, ended_at
            )
        except Exception as _ex:
            print(f"[Room] synthesize_room topic aggregation failed: {_ex!r}")

        # --- (B) Safety flag aggregation ----------------------------------
        safety_flags: list[dict] = []
        try:
            safety_rows = self._brain_db.get_knowledge_rows_for_persons(
                speaker_pids, started_at, ended_at
            )
            for pid, entity, attr, value in safety_rows:
                is_safety = any(
                    _re_sr.match(pat, attr or "") for pat in _SAFETY_PAT
                )
                if not is_safety:
                    continue
                # Resolve human-readable name for attribution.
                r = self._faces_conn.execute(
                    "SELECT name FROM persons WHERE id = ?", (pid,),
                ).fetchone()
                speaker_name = r[0] if r else pid
                safety_flags.append({
                    "pid":       pid,
                    "name":      speaker_name,
                    "attribute": attr,
                    "entity":    entity,
                })
        except Exception as _ex:
            print(f"[Room] synthesize_room safety aggregation failed: {_ex!r}")

        # --- (C) Narrative summary via LLM --------------------------------
        summary = ""
        try:
            turns = self._faces_conn.execute(
                "SELECT role, content FROM conversation_log "
                "WHERE room_session_id = ? ORDER BY ts ASC LIMIT 20",
                (room_session_id,),
            ).fetchall()
            transcript = "\n".join(
                f"{role}: {content}" for role, content in turns if content
            )
            # Resolve speaker names for a cleaner prompt.
            name_rows = self._faces_conn.execute(
                f"SELECT id, name FROM persons WHERE id IN ({placeholders})",
                tuple(speaker_pids),
            ).fetchall()
            speaker_names = [n for _i, n in name_rows] or list(speaker_pids)
            user_prompt = (
                f"Summarize this conversation between {', '.join(speaker_names)} "
                f"in 1-2 sentences for future memory reference. Focus on what "
                f"was discussed and any significant moments. No preamble.\n\n"
                f"{transcript}"
            )
            # P0.S5 D1 + Plan v2 §1 RoomSynth disposition: single-wrap on
            # assembled transcript. Speaker labels stay inside the wrap as
            # documentation; multi-speaker self-close residual risk accepted
            # per Plan v2 §3.11 (file P0.S5.X if canary surfaces escape).
            llm_out = await _call_llm_chat(
                self._http,
                [{"role": "user", "content": wrap_user_input(user_prompt)}],
                agent_name="RoomSynth",
                max_tokens=120,
                temperature=0.3,
                timeout=_LLM_TIMEOUT,
            )
            if llm_out:
                summary = (llm_out or "").strip()
        except Exception as _ex:
            print(f"[Room] synthesize_room narrative LLM failed: {_ex!r}")
        if not summary:
            # Fallback: topic-only. Still informative, no LLM dependency.
            if topic_tags:
                summary = f"Topics discussed: {', '.join(topic_tags[:5])}."
            else:
                summary = f"Conversation with {', '.join(speaker_pids)}."

        # --- Persist ------------------------------------------------------
        try:
            self._brain_db.store_room_summary(
                room_session_id=room_session_id,
                started_at=started_at,
                ended_at=ended_at,
                speaker_pids=speaker_pids,
                summary=summary,
                topic_tags=topic_tags,
                safety_flags=safety_flags,
            )
            print(
                f"[Room] Synthesis complete for {room_session_id}: "
                f"{turn_count} turns, {len(topic_tags)} topics, "
                f"{len(safety_flags)} safety flag(s)"
            )
        except Exception as _ex:
            print(f"[Room] synthesize_room store failed: {_ex!r}")

    async def _run_visitor_alert(self, person_id: str) -> None:
        """Queue a VISITOR_ALERT nudge for the best friend when any
        non-owner session closes.

        Session 98 Bug A: the original gate only fired for sessions where
        the person was STILL 'stranger' at close. Session 97 Fix 1's
        promotion chain flipped the pid's ``person_type`` to ``'known'``
        during the session if the visitor said their name — which
        suppressed the alert for exactly the sessions we most want the
        owner to know about. 2026-04-23 canary showed this live: Lexi
        introduced herself, got promoted, her session-end fired NO alert,
        the owner's later "who were you talking to?" had no
        ``[visitor_id:`` marker in prompt_addendum, the Session 96
        VISITOR CONTEXT block didn't activate, and Ollama fallback
        confabulated "there wasn't anyone else here." The fix: fire the
        alert for any non-owner session close that produced user turns,
        regardless of promotion status.

        Gates (in order):
          - person row exists
          - person is NOT the best_friend themselves (owner shouldn't get
            visitor-alerts about their own activity)
          - person spoke at least once (turn_count > 0)
          - best_friend enrolled
          - no duplicate VISITOR_ALERT already pending for this pid

        Nudge expires in 24 hours.
        """
        row = self._faces_conn.execute(
            "SELECT person_type, name FROM persons WHERE id=?", (person_id,)
        ).fetchone()
        if not row:
            return
        person_type, person_name = row[0], row[1]

        # Scope gate — skip silent/accidental encounters.
        turn_count = self._faces_conn.execute(
            "SELECT COUNT(*) FROM conversation_log WHERE person_id=? AND role='user'",
            (person_id,)
        ).fetchone()[0]
        if turn_count == 0:
            return

        # Best_friend lookup + self-skip (owner shouldn't alert on themselves).
        bf = self._faces_conn.execute(
            "SELECT id, name FROM persons WHERE person_type='best_friend' LIMIT 1"
        ).fetchone()
        if not bf:
            return
        bf_id, bf_name = bf
        if bf_id == person_id:
            return

        # Dedup — don't queue a second alert for the same pid.
        if self._brain_db.nudge_exists(bf_id, "VISITOR_ALERT", person_id):
            return

        # Display name: real name if promoted ('known'), placeholder if still stranger.
        # Session 100 Bug G: surface the actual visitor_name as a parseable
        # marker so the VISITOR CONTEXT prompt block can name it as the
        # search_memory entity. Without this, the block instructed the brain
        # to "call search_memory" but the brain defaulted to the asker's
        # name (2026-04-23 canary: Jagan asked about Lexi, brain called
        # search_memory('Gevan', ...) → no results → lied "no one was here").
        if person_type == "stranger" and person_name.lower() == "visitor":
            display_name = "an unidentified visitor"
            name_marker  = "[visitor_name:unknown]"
        else:
            display_name = person_name
            name_marker  = f"[visitor_name:{person_name}]"
        turns_desc = "briefly" if turn_count <= 2 else "for a while"

        # Session 105 Bug N Part 3 — surface safety-flag concerns proactively.
        # Query the visitor's knowledge rows for any safety-critical
        # attribute (expressed_suicidal_thoughts, mentioned_self_harm,
        # etc. — append-only history from Bug N Part 2). When at least one
        # flag is present, embed a [safety_flags:...] marker alongside
        # the visitor_name marker so the VISITOR CONTEXT block can tell
        # the brain to surface the concern proactively. Canary 2026-04-23:
        # Lexi's suicidal disclosure was stored but never raised to Jagan
        # even when he asked about her state — the owner should hear the
        # safety-flag regardless of whether the specific query path hits.
        safety_flags: list[str] = []
        try:
            safety_rows = self._brain_db.get_true_valued_attributes(person_id)
            for _attr in safety_rows:
                if _is_safety_critical_attribute(_attr):
                    safety_flags.append(_attr)
        except Exception as _sfx:
            print(f"[Brain] safety-flag scan failed for {person_id}: {_sfx!r}")
        safety_marker = (
            f" [safety_flags:{','.join(sorted(safety_flags))}]"
            if safety_flags else ""
        )
        content = (
            f"{display_name.capitalize()} stopped by while you were away and we talked {turns_desc}. "
            f"{name_marker} [visitor_id:{person_id}]{safety_marker}"
        )

        self._brain_db.store_nudge(
            bf_id, "VISITOR_ALERT", content,
            confidence=0.9,
            metadata={
                "visitor_id":    person_id,
                "visitor_name":  person_name,
                "visitor_type":  person_type,  # Session 98 — surface promoted-vs-stranger
                "turn_count":    turn_count,
                "safety_flags":  safety_flags,  # Session 105 Bug N Part 3
            },
            # WALLCLOCK: visitor alert expires_at stored persistently in DB
            expires_at=time.time() + 86400,
        )
        _safety_log = f", safety_flags={safety_flags}" if safety_flags else ""
        print(
            f"[Brain] Visitor alert queued for {bf_name} — {display_name} "
            f"stopped by ({turn_count} turns, type={person_type}{_safety_log})"
        )

    def set_system_name(self, name: str) -> None:
        """Called by pipeline when the AI's name is set or changed."""
        self._system_name = name
        if self._household_agent is not None:  # SB.3 presence guard
            self._household_agent.set_system_name(name)

    def report_camera_null_streak(self, streak: int) -> None:
        """Report a camera null-frame streak to the watchdog."""
        if self._watchdog is None:  # SB.3 presence guard
            return
        self._watchdog.report_camera_null_streak(streak)

    def report_camera_recovered(self) -> None:
        """Mark CAMERA_FAILURE alerts resolved after successful reconnect."""
        if self._watchdog is None:  # SB.3 presence guard
            return
        self._watchdog.resolve_camera_failure()

    def report_antispoof_disabled(self) -> None:
        """Record a persistent ANTISPOOF_DISABLED watchdog alert."""
        if self._watchdog is None:  # SB.3 presence guard
            return
        self._watchdog.report_antispoof_disabled()

    def report_api_failure(self, duration_s: float) -> None:
        """Report Together.ai being unreachable to the watchdog."""
        if self._watchdog is None:  # SB.3 presence guard
            return
        self._watchdog.report_api_failure(duration_s)

    def report_dispute_rename_burst(
        self,
        victim_pid: str,
        victim_name: str,
        victim_person_type: str,
        claimed_name: str,
        block_count: int,
        dispute_started_at: "float | None",
    ) -> None:
        """Surface a watchdog alert for persistent disputed-rename attempts."""
        if self._watchdog is None:  # SB.3 presence guard
            return
        self._watchdog.report_dispute_rename_burst(
            victim_pid=victim_pid,
            victim_name=victim_name,
            victim_person_type=victim_person_type,
            claimed_name=claimed_name,
            block_count=block_count,
            dispute_started_at=dispute_started_at,
        )

    def report_api_recovered(self) -> None:
        """Mark API_FAILURE alerts resolved after recovery."""
        if self._watchdog is None:  # SB.3 presence guard
            return
        self._watchdog.resolve_api_failure()

    def report_anti_spoof_rejection(
        self,
        track_id: str,
        reason: str,
        score: "float | None",
        person_id: "str | None" = None,
    ) -> None:
        """P0.S1 Phase 3 — surface a per-instance anti-spoof rejection."""
        if self._watchdog is None:  # SB.3 presence guard
            return
        self._watchdog.report_anti_spoof_rejection(
            track_id=track_id,
            reason=reason,
            score=score,
            person_id=person_id,
        )

    def report_anti_spoof_burst(
        self,
        track_id: str,
        count: int,
        window_secs: float,
        threshold: int,
        person_id: "str | None" = None,
    ) -> None:
        """P0.S1 Phase 3 + §14b.1 — surface burst-threshold alert (warning)."""
        if self._watchdog is None:  # SB.3 presence guard
            return
        self._watchdog.report_anti_spoof_burst(
            track_id=track_id,
            count=count,
            window_secs=window_secs,
            threshold=threshold,
            person_id=person_id,
        )

    def report_disk_threshold(
        self,
        level: int,
        percent_used: float,
        free_bytes: int,
        severity: str,
    ) -> None:
        """Surface a disk-space threshold crossing alert via the watchdog."""
        if self._watchdog is None:  # SB.3 presence guard
            return
        self._watchdog.report_disk_threshold(
            level=level,
            percent_used=percent_used,
            free_bytes=free_bytes,
            severity=severity,
        )

    def report_heavy_worker_burst(
        self,
        task_name: str,
        crash_count: int,
        window_secs: float,
    ) -> None:
        """Surface a heavy-worker pool burst-crash alert via the watchdog (P0.R8)."""
        if self._watchdog is None:  # SB.3 presence guard
            return
        self._watchdog.report_heavy_worker_burst(
            task_name=task_name,
            crash_count=crash_count,
            window_secs=window_secs,
        )

    def report_vram_budget_refusal(
        self,
        task_name: str,
        cumulative_mb: int,
        ceiling_mb: int,
        estimate_mb: int,
    ) -> None:
        """Surface a VRAM budget refusal alert via the watchdog (P0.R9 D5)."""
        if self._watchdog is None:  # SB.3 presence guard
            return
        self._watchdog.report_vram_budget_refusal(
            task_name=task_name,
            cumulative_mb=cumulative_mb,
            ceiling_mb=ceiling_mb,
            estimate_mb=estimate_mb,
        )

    def report_audio_device_burst(
        self,
        channel: str,
        failure_count: int,
        window_secs: float,
    ) -> None:
        """Surface an audio device burst alert via the watchdog (P0.R10 D4)."""
        if self._watchdog is None:  # SB.3 presence guard
            return
        self._watchdog.report_audio_device_burst(
            channel=channel,
            failure_count=failure_count,
            window_secs=window_secs,
        )

    def get_alerts_summary(self) -> str | None:
        """Return a formatted summary of unresolved watchdog alerts (for state.json)."""
        return self._brain_db.get_recent_alerts_summary()

    async def run(self) -> None:
        print("[BrainAgent] Started — watching conversation_log for new turns")
        self._schedule_startup_tasks()
        watchdog_task = None
        if self._watchdog is not None:  # SB.3 presence guard
            watchdog_task = asyncio.create_task(
                self._watchdog.run_loop(self._shutdown)
            )
        while not self._shutdown.is_set():
            # Clear trigger BEFORE poll so any notify() called during poll
            # re-arms the trigger and causes an immediate follow-up poll.
            self._trigger.clear()
            try:
                await self._poll_once()
            except Exception as e:
                print(f"[BrainAgent] Poll error: {e}")

            # Wait for trigger (new turn logged), shutdown, or poll interval.
            shutdown_task = asyncio.create_task(self._shutdown.wait())
            trigger_task  = asyncio.create_task(self._trigger.wait())
            try:
                await asyncio.wait(
                    {shutdown_task, trigger_task},
                    timeout=BRAIN_AGENT_POLL_INTERVAL,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                shutdown_task.cancel()
                trigger_task.cancel()
                await asyncio.gather(shutdown_task, trigger_task, return_exceptions=True)

        print("[BrainAgent] Shutting down...")
        if watchdog_task is not None:  # SB.3 — None when watchdog is unregistered
            await watchdog_task
        await self.close()

    async def _poll_once(self) -> None:
        last_id = self._brain_db.get_last_turn_id()

        # P0.S7.2 Phase 2 — select audience_ids alongside the turn so
        # _process_turn can route multi-person assistant turns to
        # extract_assistant_room_turn with the room snapshot at turn time.
        rows = self._faces_conn.execute(
            """SELECT cl.id, cl.person_id, cl.role, cl.content, cl.ts, p.name,
                      cl.audience_ids
               FROM   conversation_log cl
               LEFT JOIN persons p ON p.id = cl.person_id
               WHERE  cl.id > ?
               ORDER  BY cl.id ASC
               LIMIT  20""",
            (last_id,),
        ).fetchall()

        if not rows:
            return

        # Build a rolling context window of the turns just before our batch
        recent = self._faces_conn.execute(
            """SELECT role, content FROM conversation_log
               WHERE id <= ? ORDER BY id DESC LIMIT ?""",
            (last_id, BRAIN_AGENT_CONTEXT_TURNS * 2),
        ).fetchall()
        context: list[dict] = [{"role": r[0], "content": r[1]} for r in reversed(recent)]

        for turn_id, person_id, role, content, ts, person_name, audience_ids_json in rows:
            try:
                await self._process_turn(
                    turn_id     = turn_id,
                    person_id   = person_id,
                    person_name = person_name or person_id or "unknown",
                    role        = role,
                    content     = content,
                    context     = context,
                    ts          = ts,
                    audience_ids_json = audience_ids_json,
                )
            except Exception as e:
                import traceback
                print(f"[BrainAgent] Error on turn {turn_id}: {type(e).__name__}: {e}")
                traceback.print_exc()
            finally:
                # Always advance — even if processing failed, don't re-process
                self._brain_db.set_last_turn_id(turn_id)
                context.append({"role": role, "content": content})

    async def _process_turn(
        self,
        turn_id:     int,
        person_id:   str | None,
        person_name: str,
        role:        str,
        content:     str,
        context:     list[dict],
        ts:          float = 0.0,
        audience_ids_json: "str | None" = None,
    ) -> None:
        t0 = time.time()

        # ── Stage 0: Identity-dispute gate ─────────────────────────────────────
        # When the current speaker has contradicted the sensor, we don't know who
        # they actually are. Extracting facts under either name would pollute that
        # person's knowledge with contradictory data. Pause until the dispute
        # resolves (update_person_name gives a clean name or session ends).
        if person_id and person_id in self._disputed_persons:
            self._brain_db.log_agent(turn_id, "triage", "skip", "identity disputed")
            print(f"[BrainAgent] {_now_log_ts()} Triage: SKIP turn {turn_id} — identity disputed for {person_id}")
            return

        # ── Stage 1: Triage ────────────────────────────────────────────────────
        prior_assistant = _get_prior_assistant_turn(context)
        # P0.S7.2 Phase 2 — parse this turn's audience_ids so triage sees the
        # room-participant count. audience_ids JSON is the canonical room
        # snapshot at turn time (P0.S7 Phase 1 _compute_room_audience).
        _room_participant_pids: "list[str]" = []
        if audience_ids_json:
            try:
                _loaded = json.loads(audience_ids_json)
                if isinstance(_loaded, list):
                    _room_participant_pids = [str(p) for p in _loaded if p]
            except (json.JSONDecodeError, TypeError, ValueError):
                _room_participant_pids = []
        _room_count = len(_room_participant_pids)
        if self._triage is None:  # SB.3 presence guard — no triage → no knowledge processing
            return
        ok, reason = self._triage.should_process(
            role, content,
            prior_assistant_turn=prior_assistant,
            room_participant_count=_room_count if _room_count else 1,
        )
        self._brain_db.log_agent(turn_id, "triage", "process" if ok else "skip", reason)
        # Session 116 P1 #6 — triage rationale: surface the signals the
        # decision was based on (word_count, role, person_type) so an
        # outside reviewer can audit "why did we skip?" / "why did we
        # process?" from terminal output alone. Word count is the
        # dominant predictor in TriageAgent.
        _word_count = len((content or "").split())
        _ptype = "?"
        try:
            r = self._faces_conn.execute(
                "SELECT person_type FROM persons WHERE id = ?", (person_id,),
            ).fetchone()
            if r:
                _ptype = r[0] or "?"
        except Exception:
            pass  # OPTIONAL: enriches log rationale only — triage decision already made above
        _rationale = (
            f"role={role}, words={_word_count}, person_type={_ptype}"
        )
        if not ok:
            print(
                f"[BrainAgent] {_now_log_ts()} Triage: SKIP turn {turn_id} "
                f"— {reason} ({_rationale})"
            )
            return
        print(
            f"[BrainAgent] {_now_log_ts()} Triage: PASS turn {turn_id} "
            f"— processing ({_rationale})"
        )

        # ── Stage 1b: Confidence feedback — user confirming/denying AI recall ─
        # Run before extraction so the signal is logged even if extraction finds nothing.
        prior_ai_claim = _get_prior_ai_claim(context)
        if prior_ai_claim:
            reaction = _classify_user_reaction(content)
            if reaction == "confirm" and person_name:
                asyncio.create_task(
                    self._boost_recalled_fact_confidence(person_name, prior_ai_claim)
                )
                self._brain_db.log_agent(
                    turn_id, "feedback", "confirmed_recall", prior_ai_claim[:80]
                )
            elif reaction == "deny":
                self._brain_db.log_agent(
                    turn_id, "feedback", "denied_recall", prior_ai_claim[:80]
                )

        # ── Stage 2: Extract entities + facts ─────────────────────────────────
        t1 = time.time()
        if self._extractor is None:  # SB.3 presence guard — no extractor → no facts → cascade skips
            extractions = []
        elif reason == "multi_person_assistant_turn":
            # P0.S7.2 Phase 2 — κ branch. ONE LLM call + mechanical fan-out.
            # Resolve participant pids → names via persons table.
            _names_by_pid: "dict[str, str]" = {}
            try:
                _placeholders = ",".join("?" * len(_room_participant_pids))
                if _placeholders:
                    _name_rows = self._faces_conn.execute(
                        f"SELECT id, name FROM persons WHERE id IN ({_placeholders})",
                        _room_participant_pids,
                    ).fetchall()
                    _names_by_pid = {pid: nm for pid, nm in _name_rows}
            except Exception as _name_ex:
                # OPTIONAL: name-lookup failure must not block the turn; we fall
                # back to using pids as names so the LLM still gets a participant
                # list (degraded but not dropped).
                print(f"[BrainAgent] room-participant name lookup failed: {_name_ex!r}")
            _names: "list[str]" = []
            _pids: "list[str]" = []
            for _pid in _room_participant_pids:
                _nm = _names_by_pid.get(_pid) or _pid
                _names.append(_nm)
                _pids.append(_pid)
            extractions = await self._extractor.extract_assistant_room_turn(
                assistant_content=content,
                participant_names=_names,
                participant_pids=_pids,
                disputed_pids=self._disputed_persons,
            )
        else:
            extractions = await self._extractor.extract(
                content, person_name, context,
                prior_ai_claim=prior_ai_claim,
                prior_assistant_turn=prior_assistant,
                system_name=self._system_name,
            )
        extract_ms  = (time.time() - t1) * 1000

        if not extractions:
            self._brain_db.log_agent(turn_id, "extraction", "no_facts", None, 0, extract_ms)
            print(f"[BrainAgent] Extraction: no facts found in turn {turn_id} ({extract_ms:.0f}ms)")
            self._advance_session_counter(person_id, person_name)
            return

        self._brain_db.log_agent(
            turn_id, "extraction", "extracted",
            f"{len(extractions)} fact(s)", len(extractions), extract_ms,
        )
        _ext_summary = ", ".join(
            f"{e.entity}.{e.attribute}={e.value[:20]!r}" for e in extractions[:3]
        )
        _ext_more = f" (+{len(extractions)-3} more)" if len(extractions) > 3 else ""
        print(f"[BrainAgent] {_now_log_ts()} Extracted {len(extractions)} fact(s) ({extract_ms:.0f}ms): {_ext_summary}{_ext_more}")

        # ── Stage 3: Contradiction check (parallel per fact) ──────────────────
        conflicts:    list[tuple["Extraction", str]] = []   # (ext, old_val)
        no_conflict:  list["Extraction"]             = []

        # Pre-fetch contradiction counts for conflicting predicates once — reused in
        # both Stage 3 (volatility hint) and Stage 4 (confidence cap) to avoid a
        # double SELECT for each REPLACE fact.
        conflict_counts: dict[str, int] = {}

        # Wave 2 Item 10: pre-fetch all distinct entities in one bulk query
        # instead of calling get_active_knowledge once per extraction fact.
        # O(facts) DB reads → O(1) DB reads per turn.
        _distinct_entities = list({ext.entity for ext in extractions})
        _existing_by_entity = self._brain_db.get_active_knowledge_for_entities(_distinct_entities)

        for ext in extractions:
            stored      = _existing_by_entity.get(ext.entity, [])
            conflicting = [s for s in stored if s["attribute"] == ext.attribute]
            if conflicting:
                conflicts.append((ext, conflicting[0]["value"]))
                if ext.attribute not in conflict_counts:
                    conflict_counts[ext.attribute] = (
                        self._brain_db.get_predicate_contradiction_count(ext.attribute)
                    )
            else:
                no_conflict.append(ext)

        t2 = time.time()
        if self._contradictor is not None:  # SB.3 presence guard
            check_results = await asyncio.gather(*[
                self._contradictor.check(
                    ext.entity, ext.attribute, old_val, ext.value,
                    conflict_counts[ext.attribute],
                )
                for ext, old_val in conflicts
            ])
        else:
            check_results = []
        contra_ms = (time.time() - t2) * 1000

        final = list(no_conflict)
        for (ext, old_val), (should_replace, rationale) in zip(conflicts, check_results):
            if should_replace:
                self._brain_db.invalidate(ext.entity, ext.attribute, turn_id)
                try:
                    self._graph_db.invalidate_fact(ext.entity, ext.attribute)
                except Exception as e:
                    self._mark_kuzu_dirty()  # SWALLOW: sentinel for next-boot heal
                    print(f"[BrainAgent] Graph invalidate error: {e}")
                self._brain_db.increment_predicate_contradiction(ext.attribute)
                self._brain_db.log_agent(
                    turn_id, "contradiction",
                    f"replace: {ext.entity}.{ext.attribute} '{old_val}'→'{ext.value}'",
                    rationale, 1, contra_ms,
                )
                final.append(ext)
                # Item 4: A-MEM retroactive scan — re-evaluate related facts for staleness
                asyncio.create_task(
                    self._retroactive_scan(ext.entity, ext.attribute, old_val, ext.value, turn_id)
                )
            else:
                self._brain_db.log_agent(
                    turn_id, "contradiction",
                    f"compatible: {ext.entity}.{ext.attribute}",
                    rationale, 0, contra_ms,
                )

        _n_replace = sum(1 for _, (ok, _) in zip(conflicts, check_results) if ok)
        _n_compat  = len(conflicts) - _n_replace
        if conflicts:
            print(f"[BrainAgent] Contradiction check ({contra_ms:.0f}ms): {_n_replace} replaced, {_n_compat} compatible, {len(no_conflict)} new")

        # ── Stage 4: Store ─────────────────────────────────────────────────────
        if final:
            # Phase 5: cap confidence for volatile predicates before storing.
            # Reuse conflict_counts for REPLACE facts; fetch only for new (no-conflict) facts.
            for ext in final:
                count = conflict_counts.get(
                    ext.attribute,
                    self._brain_db.get_predicate_contradiction_count(ext.attribute),
                )
                if count >= PREDICATE_VOLATILITY_THRESHOLD:
                    ext.confidence = min(ext.confidence, PREDICATE_CONFIDENCE_CAP)

            n = self._brain_db.store_knowledge(final, turn_id, person_id, "extraction_agent")
            self._brain_db.batch_increment_predicate_extraction(
                [ext.attribute for ext in final]
            )
            for ext in final:
                try:
                    self._graph_db.store_fact(ext, turn_id)
                except Exception as e:
                    print(f"[BrainAgent] Graph write error: {e}")
            if person_id:
                asyncio.create_task(self._embed_new_facts(person_id))
            elapsed = (time.time() - t0) * 1000
            summary = ", ".join(
                f"{e.entity}.{e.attribute}={e.value!r}" for e in final
            )
            print(f"[BrainAgent] Turn {turn_id} → {n} fact(s) in {elapsed:.0f}ms: {summary}")

        self._advance_session_counter(person_id, person_name)

        # ── Social mention extraction — all persons ────────────────────────────
        # Run asynchronously so it never blocks the main extraction pipeline.
        # Only user turns are useful (assistant turns don't mention third parties).
        # Runs for best_friend, known, AND strangers — every person who mentions
        # a third party contributes to the cross-person social graph.
        if role == "user" and person_id:
            asyncio.create_task(self._extract_social_mentions(person_id, content))

            # ── Stage 5: Friction detection (Phase 5) ─────────────────────────
            # Only when person has active prefs. Runs async during TTS so n+1
            # turn's get_prompt_addendum() immediately picks up escalated level.
            active_prefs = self._brain_db.get_active_prefs(person_id)
            if active_prefs:
                prev_assistant = next(
                    (t["content"] for t in reversed(context) if t["role"] == "assistant"),
                    None,
                )
                asyncio.create_task(
                    self._detect_and_record_friction(
                        person_id, content, prev_assistant, active_prefs
                    )
                )

            # ── Household extraction — fire-and-forget per user turn ───────────
            context_recent = context[-3:] if context else []
            enrolled_rows = self._faces_conn.execute(
                "SELECT name FROM persons WHERE person_type != 'stranger' ORDER BY name"
            ).fetchall()
            enrolled = [r[0] for r in enrolled_rows]
            asyncio.create_task(self._run_household_per_turn(
                content, person_id, person_name, context_recent, enrolled
            ))

        # Track session start for RoutineAgent + InsightAgent (first turn = arrived)
        if person_id and person_id not in self._session_start_ts:
            self._session_start_ts[person_id] = ts

    async def _detect_and_record_friction(
        self,
        person_id: str,
        user_turn: str,
        prev_assistant_turn: str | None,
        active_prefs: list[dict],
    ) -> None:
        if self._friction_agent is None:  # SB.3 presence guard
            return
        frictions = await self._friction_agent.detect(
            user_turn, prev_assistant_turn, active_prefs
        )
        for f in frictions:
            self._brain_db.increment_pref_friction(person_id, f["pref_type"])
            self._brain_db.log_agent(
                None, "friction",
                f"escalate: {f['pref_type']} (conf={f['confidence']:.2f})",
                user_turn[:80],
            )
            print(
                f"[FrictionAgent] {f['pref_type']} friction detected "
                f"(conf={f['confidence']:.2f}) — escalating pref injection"
            )

    def _collect_known_names_for_phantom_check(
        self,
        speaker_id: str,
        speaker_name: str,
    ) -> "list[str]":
        """Session 114 Part 2 — assemble the list of known names that a
        candidate shadow name should be fuzzy-matched against.

        Sources (in priority order):
          1. Current speaker's display name (catches STT mishears
             where the speaker accidentally referred to themselves).
          2. All enrolled person names from faces.db (catches
             cross-person mishears against any enrolled identity).
          3. Recent shadow_persons names within 24h (catches
             repeated-mishear shadows that would otherwise stack).

        Defensive on each query — a failure in one source still allows
        the others to contribute. Empty list is safe (no fuzzy match
        will fire, normal insert proceeds).
        """
        names: list[str] = []
        if speaker_name:
            names.append(speaker_name)
        try:
            rows = self._faces_conn.execute(
                "SELECT name FROM persons WHERE name IS NOT NULL"
            ).fetchall()
            for r in rows:
                if r[0]:
                    names.append(r[0])
        except Exception as _ex:
            print(f"[HouseholdAgent] phantom-check enrolled-name fetch failed: {_ex!r}")
        try:
            cutoff = time.time() - 86400.0
            names.extend(self._brain_db.get_shadow_person_names_since(cutoff))
        except Exception as _ex:
            print(f"[HouseholdAgent] phantom-check recent-shadows fetch failed: {_ex!r}")
        # Dedupe (case-insensitive) preserving first occurrence.
        seen: set[str] = set()
        out: list[str] = []
        for n in names:
            k = n.strip().lower()
            if k and k not in seen:
                seen.add(k)
                out.append(n)
        return out

    async def _apply_household_extraction(
        self,
        speaker_id: str,
        speaker_name: str,
        result: dict,
    ) -> None:
        """Persist household extraction results to BrainDB.

        Called async from both per-turn and session-end paths.
        """
        if not result:
            return

        # Household facts
        for hf in result.get("household_facts", []):
            entity    = hf.get("entity", "household")
            attribute = hf.get("attribute", "")
            value     = hf.get("value", "")
            scope     = hf.get("scope", "household")
            confidence = float(hf.get("confidence", 0.65))
            if not (entity and attribute and value):
                continue
            disputed = self._brain_db.store_household_fact(
                entity, attribute, value, scope, speaker_id, confidence
            )
            if disputed:
                print(f"[HouseholdAgent] Dispute detected: {entity}/{attribute}")

        # Per-person facts from cross-attribution
        for pf in result.get("per_person_facts", []):
            entity    = pf.get("entity", "")
            attribute = pf.get("attribute", "")
            value     = pf.get("value", "")
            confidence = float(pf.get("confidence", 0.65))
            if not (entity and attribute and value):
                continue
            # Store as per_person scope household fact
            self._brain_db.store_household_fact(
                entity, attribute, value, "per_person", speaker_id, confidence
            )

        # Relationships
        for rel in result.get("relationships", []):
            person_a     = rel.get("person_a", "")
            relationship = rel.get("relationship", "")
            person_b     = rel.get("person_b", "")
            confidence   = float(rel.get("confidence", 0.8))
            if not (person_a and relationship and person_b):
                continue
            self._brain_db.store_relationship(
                person_a, relationship, person_b, confidence, speaker_id
            )
            # Store inverse relationship too
            inverse_map = {
                "married_to": "married_to", "spouse_of": "spouse_of",
                "parent_of": "child_of", "child_of": "parent_of",
                "sibling_of": "sibling_of", "colleague_of": "colleague_of",
                "friend_of": "friend_of",
            }
            if relationship in inverse_map:
                self._brain_db.store_relationship(
                    person_b, inverse_map[relationship], person_a, confidence, speaker_id
                )

        # Shadow persons
        # Session 114 Part 2 — phantom-person prevention via phonetic
        # + Jaro-Winkler match. STT mishears (e.g. "Jagan" → "Jai Gun")
        # would otherwise spawn a shadow node parallel to the real
        # person's enrolled record. Pre-filter against (a) enrolled
        # person names in faces.db, (b) the current speaker's own
        # display name (self-reference via STT noise), (c) recent
        # shadow names within 24h.
        _phantom_known = self._collect_known_names_for_phantom_check(
            speaker_id, speaker_name,
        )
        for sp in result.get("shadow_persons", []):
            name         = sp.get("name", "")
            mentioned_by = sp.get("mentioned_by", speaker_name)
            relationship = sp.get("relationship", "mentioned_by")
            if not name:
                continue
            _matched = _is_phantom_name(name, _phantom_known)
            if _matched:
                print(
                    f"[HouseholdAgent] Shadow name {name!r} matched "
                    f"existing {_matched!r} phonetically — skipping "
                    f"(prevents phantom person)"
                )
                continue
            # Only create shadow nodes for non-enrolled persons
            # (Check won't be perfect here but speaker_id is available)
            _shadow_id, _was_new = self._brain_db.upsert_shadow_person(
                name, speaker_id, relationship
            )
            for fact in sp.get("facts", []):
                self._brain_db.add_shadow_person_fact(
                    name,
                    fact.get("attribute", ""),
                    fact.get("value", ""),
                    float(fact.get("confidence", 0.65)),
                )
            # Session 97 Fix 3: the "Shadow node: X" log fires only on
            # first create. Repeat mentions of the same name — which
            # would previously print an identical line giving the
            # impression of duplicate creates — now surface as a subtler
            # "Shadow mention" line so the information is still visible
            # without looking like new nodes were spawned.
            if _was_new:
                print(f"[HouseholdAgent] Shadow node: {name} (via {mentioned_by}, rel={relationship})")
            else:
                print(f"[HouseholdAgent] Shadow mention: {name} (via {mentioned_by}, rel={relationship})")

    async def _run_household_per_turn(
        self,
        utterance: str,
        speaker_id: str,
        speaker_name: str,
        context_turns: list[dict],
        enrolled_persons: list[str],
    ) -> None:
        """Async fire-and-forget household extraction for a single turn."""
        if self._household_agent is None:  # SB.3 presence guard
            return
        result = await self._household_agent.extract_per_turn(
            speaker_id, speaker_name, utterance, context_turns, enrolled_persons
        )
        if result:
            await self._apply_household_extraction(speaker_id, speaker_name, result)

    async def _run_household_session_end(
        self,
        person_id: str,
        person_name: str,
        started_at: float,
    ) -> None:
        """Deep household analysis at session close."""
        if self._household_agent is None:  # SB.3 presence guard
            return
        turns_raw = self._faces_conn.execute(
            """SELECT role, content FROM conversation_log
               WHERE person_id = ? AND ts >= ?
               ORDER BY id ASC""",
            (person_id, started_at),
        ).fetchall()
        turns = [{"role": r[0], "content": r[1]} for r in turns_raw]
        if len(turns) < 4:
            return

        # Get enrolled persons list
        enrolled_rows = self._faces_conn.execute(
            "SELECT name FROM persons WHERE person_type != 'stranger' ORDER BY name"
        ).fetchall()
        enrolled = [r[0] for r in enrolled_rows]

        result = await self._household_agent.extract_session_end(
            person_id, person_name, turns, enrolled
        )
        if result:
            await self._apply_household_extraction(person_id, person_name, result)
            print(f"[HouseholdAgent] Session-end extraction complete for {person_name}")

    def _is_best_friend(self, person_id: str) -> bool:
        row = self._faces_conn.execute(
            "SELECT 1 FROM persons WHERE id=? AND person_type='best_friend' LIMIT 1",
            (person_id,),
        ).fetchone()
        return row is not None

    async def _extract_social_mentions(self, source_person_id: str, text: str) -> None:
        if self._social_graph is None:  # SB.3 presence guard
            return
        mentions = await self._social_graph.extract(text)
        for m in mentions:
            name = (m.get("name") or "").strip()
            if not name:
                continue
            attrs = [a for a in (m.get("attributes") or []) if isinstance(a, str) and a.strip()]
            self._brain_db.upsert_social_mention(
                source_person_id=source_person_id,
                mentioned_name=name,
                relationship=m.get("relationship"),
                new_attributes=attrs,
            )
            print(f"[SocialGraph] Mention stored: {name} ({m.get('relationship', '?')}) — {attrs}")

    def score_stranger_identity(self, conversation: list[dict]) -> dict | None:
        """Score a stranger's conversation against all known social mentions.

        Synchronous — reads only pre-stored data from brain.db, no API calls.
        Called by pipeline after every stranger turn.

        Returns best match dict or None:
          {name, relationship, confidence, matched_attrs, source_person_id}
        """
        mentions = self._brain_db.get_all_social_mentions()
        if self._identity_agent is None:  # SB.3 presence guard
            return None
        return self._identity_agent.score(conversation, mentions)

    async def get_briefing(self, bf_person_id: str, since_ts: float) -> str | None:
        """Generate a spoken briefing for the best friend after a long absence.

        Queries stranger visits and silent observations from faces.db since
        since_ts (the best friend's last_seen timestamp), scores them for
        relevance, and generates a warm natural 1–2 sentence summary.

        Called from pipeline concurrently with the greeting TTS so the LLM
        call completes during the greeting with zero added latency.
        """
        try:
            row = self._faces_conn.execute(
                "SELECT name FROM persons WHERE id = ?", (bf_person_id,)
            ).fetchone()
            if not row:
                return None
            bf_name = row[0]

            # Bug N (2026-04-20 live run): strangers with turn_count=0 (gate-blocked,
            # phantom sessions from short-utterance misfires) must not surface in the
            # briefing — the downstream template phrasing "visited and spoke with me"
            # asserts a real exchange. Joining on the user-role rows in
            # conversation_log and filtering by BRIEFING_VISITOR_MIN_TURNS is the
            # authoritative guard.
            sv_rows = self._faces_conn.execute(
                """SELECT p.id, p.name, p.last_seen, p.enrolled_at,
                          (SELECT COUNT(*) FROM conversation_log cl
                           WHERE cl.person_id = p.id AND cl.role = 'user') AS user_turns
                     FROM persons p
                    WHERE p.person_type = 'stranger' AND p.last_seen > ?
                    ORDER BY p.last_seen DESC""",
                (since_ts,),
            ).fetchall()
            stranger_visits = [
                {"id": r[0], "name": r[1], "last_seen": r[2], "first_seen": r[3]}
                for r in sv_rows
                if (r[4] or 0) >= BRIEFING_VISITOR_MIN_TURNS
            ]

            obs_rows = self._faces_conn.execute(
                """SELECT id, first_seen, last_seen, duration_secs, frame_count,
                          photo_path, zone, matched_person_id
                   FROM silent_observations WHERE last_seen > ?
                   ORDER BY last_seen DESC""",
                (since_ts,),
            ).fetchall()
            silent_obs = [
                {
                    "id": r[0], "first_seen": r[1], "last_seen": r[2],
                    "duration_secs": r[3], "frame_count": r[4],
                    "photo_path": r[5], "zone": r[6], "matched_person_id": r[7],
                }
                for r in obs_rows
            ]

            mentions = self._brain_db.get_all_social_mentions()
            if self._briefing_agent is None:  # SB.3 presence guard
                return None
            return await self._briefing_agent.generate(
                bf_name, stranger_visits, silent_obs, mentions
            )
        except Exception as e:
            print(f"[BriefingAgent] get_briefing error: {e}")
            return None

    def get_context(
        self,
        person_name: str,
        query_embedding: list[float] | None = None,
        requester_person_id: str | None = None,
        best_friend_id: str | None = None,
    ) -> str | None:
        """Return formatted knowledge about a person for LLM injection.

        When query_embedding is provided, uses cosine similarity to rank facts
        by relevance to the current user utterance (semantic retrieval). Falls
        back to graph context, then SQLite recency order when no embeddings exist.
        Synchronous — all reads are in-process (<1ms).
        Always appends household context (shared facts + relationships) when available.

        Session 106 Phase 3A.5 — privacy filtering now goes through
        ``query_knowledge_for`` (single source of truth via
        ``_visibility_clause``) instead of the legacy two-step
        ``get_active_knowledge`` + ``filter_facts_for_requester``. Same
        visibility semantics — 4-tier owner-access model — but the
        filter runs in SQL rather than Python so future retrieval sites
        can't accidentally skip it.

        The semantic-search branch (``query_embedding`` provided) still
        uses ``semantic_search_knowledge`` for cosine ranking and then
        filters the returned list in Python via
        ``filter_facts_for_requester`` — that method is kept for the
        semantic-rank path because the privacy clause doesn't affect
        embedding-similarity ranking. Migrating the cosine search to
        push the visibility predicate into SQL is 3A.6 scope.
        """
        household_ctx = self._brain_db.get_household_context()

        # Resolve subject person_id for the privacy filter (used by the
        # semantic-search branch's in-Python filter; the recency-fallback
        # branch composes visibility in SQL via query_knowledge_for).
        subject_person_id: str | None = None
        _fc = getattr(self, "_faces_conn", None)
        if _fc:
            row = _fc.execute(
                "SELECT id FROM persons WHERE LOWER(name) = LOWER(?) LIMIT 1",
                (person_name,),
            ).fetchone()
            subject_person_id = row[0] if row else None

        # Determine whether privacy filtering is active for this request
        _filtering = bool(
            requester_person_id
            and requester_person_id != best_friend_id
            and requester_person_id != subject_person_id
        )

        if query_embedding:
            # Session 107 Phase 3A.6 — visibility now composed into
            # semantic_search_knowledge's SELECT WHERE clause via
            # requester_pid/best_friend_id kwargs. filter_facts_for_requester
            # deleted. Same semantics as the recency-fallback branch
            # below: SQL is the single source of truth for "who can see
            # what." Backward compat: when requester_person_id is None
            # (internal synthesis paths), no filter is applied.
            facts = self._brain_db.semantic_search_knowledge(
                person_name, query_embedding,
                requester_pid=requester_person_id,
                best_friend_id=best_friend_id,
            )
            if facts:
                ctx = _format_context_lines(person_name, facts)
                if household_ctx:
                    ctx = (ctx + "\n\n" + household_ctx) if ctx else household_ctx
                return ctx

        # Graph path: P0.S7.D-B added `privacy_level` to Kuzu RELATES_TO
        # edges, so the graph can now filter at Cypher level. We thread
        # caller_pid + best_friend_id through; get_graph_context applies
        # the SQL `_visibility_clause`-equivalent semantic.
        # The existing `if not _filtering:` defensive skip is PRESERVED
        # as belt-and-braces (Plan v2 §3.4) — it remains correct even
        # though the Cypher filter now also enforces the same property.
        # Future cleanup PR may remove the skip once v3 is canary-validated.
        if not _filtering:
            ctx = self._graph_db.get_graph_context(
                person_name,
                caller_pid=requester_person_id,
                best_friend_id=best_friend_id,
            )
        else:
            ctx = None

        if not ctx:
            # Session 106 Phase 3A.5 canary-replicated site: recency
            # fallback retrieval now uses SQL-level visibility filter
            # via query_knowledge_for. When no requester_person_id is
            # supplied (internal callers), the query returns unfiltered
            # entity rows via the same helper — we use requester_pid =
            # subject as a sensible default so the owner-check branch
            # in _visibility_clause returns everything non-system.
            _eff_requester = requester_person_id or subject_person_id or (best_friend_id or "")
            if _eff_requester:
                facts = self._brain_db.query_knowledge_for(
                    requester_pid=_eff_requester,
                    best_friend_id=best_friend_id,
                    entity=person_name,
                )
            else:
                # No identity context anywhere — keep the legacy
                # unfiltered path (dream loop / internal synthesis).
                facts = self._brain_db.get_active_knowledge(person_name)
            ctx = _format_context_lines(person_name, facts) if facts else None

        if household_ctx:
            ctx = (ctx + "\n\n" + household_ctx) if ctx else household_ctx
        return ctx

    async def embed_query(self, text: str) -> list[float] | None:
        """Embed the current user utterance for semantic retrieval.

        Returns None when no API key is configured — callers fall back to
        graph/recency context automatically.
        """
        if self._embed_agent is None:  # SB.3 presence guard
            return None
        return await self._embed_agent.embed(text, purpose="user query")

    def get_pending_question(self) -> dict | None:
        """Return the next unasked pattern question for proactive injection.

        Returns a dict with keys 'id', 'text', 'pattern_key', or None.
        Synchronous SQLite read (<1ms). Called every turn in conversation_turn().
        """
        return self._brain_db.get_next_pending_question()

    def mark_question_asked(self, qid: int) -> None:
        """Mark a question as served so it is not injected again.

        Called immediately after injecting the question into prompt_addendum,
        before the LLM responds — the injection is the commitment to ask.
        """
        self._brain_db.mark_question_asked(qid)

    def store_temporal_fact(
        self,
        person_id: str,
        person_name: str,
        attribute: str,
        value: str,
        valid_for_hours: float = 4.0,
    ) -> None:
        """Store a short-lived fact directly (bypassing extraction pipeline).

        Invalidates any existing active fact for the same (entity, attribute)
        before inserting — ensures at most one active value per attribute.

        Used by pipeline for sensor-derived facts (e.g. emotion agent)
        that don't need LLM extraction — they already have a structured value.
        """
        turn_id = self._brain_db.get_last_turn_id()
        # Replace previous value so the attribute stays deduplicated
        self._brain_db.invalidate(person_name, attribute, turn_id)
        # Session 95 3A.4.5: sync path. All sensor-derived temporal facts
        # (emotion agent's current_feeling, mood changes) are 'personal' —
        # they describe the speaker's internal state, owner-only by design.
        ext = Extraction(
            entity=person_name,
            entity_type="person",
            attribute=attribute,
            value=value,
            confidence=0.80,
            is_temporal=True,
            valid_for_hours=valid_for_hours,
            privacy_level="personal",
        )
        self._brain_db.store_knowledge([ext], turn_id, person_id, agent="emotion_agent")

    async def _embed_new_facts(self, person_id: str) -> None:
        """Embed unembedded knowledge rows for a person and persist the vectors.

        Fire-and-forget task — called after store_knowledge() so the pipeline
        never waits for it. Embeds up to 20 rows per call to keep latency low.
        """
        if self._embed_agent is None:  # SB.3 presence guard
            return
        rows = self._brain_db.get_unembedded_knowledge(person_id)
        if not rows:
            return
        texts = [
            f"{r['entity']} {r['attribute'].replace('_', ' ')}: {r['value']}"
            for r in rows
        ]
        embeddings = await self._embed_agent.embed_batch(texts, purpose="knowledge fact")
        for row, emb in zip(rows, embeddings):
            if emb:
                self._brain_db.store_knowledge_embedding(row["id"], emb)

    async def _backfill_embeddings(self, batch_size: int = 50) -> None:
        """Item 5: Startup background job — embed all NULL-embedding knowledge rows.

        Processes rows from before EmbeddingAgent was introduced (Phase 3). Runs
        oldest-first, 50 rows per batch with 2s sleep for rate limiting. Exits
        immediately when all rows are embedded. Idempotent: safe to re-run.
        """
        if self._embed_agent is None:  # SB.3 presence guard
            return
        total = 0
        while not self._shutdown.is_set():
            rows = self._brain_db.get_all_unembedded_knowledge(limit=batch_size)
            if not rows:
                if total > 0:
                    print(f"[BrainAgent] Embedding backfill complete — {total} rows embedded")
                return
            texts = [
                f"{r['entity']} {r['attribute'].replace('_', ' ')}: {r['value']}"
                for r in rows
            ]
            embeddings = await self._embed_agent.embed_batch(texts, purpose="knowledge fact")
            n_this = sum(1 for emb in embeddings if emb)
            for row, emb in zip(rows, embeddings):
                if emb:
                    self._brain_db.store_knowledge_embedding(row["id"], emb)
            total += n_this
            print(f"[BrainAgent] Backfill: {n_this}/{len(rows)} embedded ({total} total)")
            if n_this == 0:
                # API unavailable — stop trying; will retry on next restart
                print("[BrainAgent] Backfill: no embeddings returned (API unavailable?), aborting")
                return
            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass

    async def _retroactive_scan(
        self,
        entity: str,
        changed_attr: str,
        old_value: str,
        new_value: str,
        turn_id: int,
    ) -> None:
        """Item 4: A-MEM retroactive memory evolution.

        After a ContradictionAgent REPLACE, walk the entity's active facts and
        re-evaluate each for staleness relative to the change. Caps LLM calls at
        MAX_RETROACTIVE_FACTS to bound cost. Runs as a background task — never
        blocks the conversation.

        Safeguards:
        - Only checks facts with confidence >= EMBED_MIN_CONFIDENCE (already uncertain = skip)
        - No cascading: calls BrainDB.invalidate() directly, not _process_turn()
        - No cross-entity scan in v1 (only same-entity facts checked)
        """
        if self._contradictor is None:  # SB.3 presence guard
            return
        related = [
            f for f in self._brain_db.get_active_knowledge(entity)
            if f["attribute"] != changed_attr
            and f["confidence"] >= EMBED_MIN_CONFIDENCE
        ]
        if not related:
            return
        related = related[:MAX_RETROACTIVE_FACTS]

        results = await asyncio.gather(*[
            self._contradictor.check_staleness(
                entity, f["attribute"], f["value"],
                changed_attr, old_value, new_value,
            )
            for f in related
        ], return_exceptions=True)

        for f, result in zip(related, results):
            if isinstance(result, Exception):
                continue
            verdict, rationale = result
            if verdict == "INVALIDATED":
                self._brain_db.invalidate(entity, f["attribute"], turn_id)
                try:
                    self._graph_db.invalidate_fact(entity, f["attribute"])
                except Exception:
                    self._mark_kuzu_dirty()  # SWALLOW: brain.db is authoritative, sentinel for next-boot heal
                self._brain_db.log_agent(
                    turn_id, "retro_scan",
                    f"invalidated: {entity}.{f['attribute']}",
                    rationale,
                )
                print(f"[RetroScan] Invalidated {entity}.{f['attribute']} — {rationale}")
            elif verdict == "STALE":
                kid = self._brain_db.find_knowledge_id(entity, f["attribute"], f["value"])
                if kid is not None:
                    self._brain_db.update_confidence(kid, -RETRO_STALE_PENALTY)
                    self._brain_db.log_agent(
                        turn_id, "retro_scan",
                        f"stale: {entity}.{f['attribute']} (-{RETRO_STALE_PENALTY:.2f})",
                        rationale,
                    )
                    print(
                        f"[RetroScan] Stale: {entity}.{f['attribute']}"
                        f" (-{RETRO_STALE_PENALTY:.2f}) — {rationale}"
                    )

    async def _boost_recalled_fact_confidence(
        self, person_name: str, prior_ai_text: str
    ) -> None:
        """Boost the confidence of a stored fact the user just confirmed (SM-2 reset).

        Item 6: calls update_confirmation() which boosts stored confidence AND
        resets last_confirmed_at to now — resetting the decay clock.
        """
        if self._embed_agent is None:  # SB.3 presence guard
            return
        emb = await self._embed_agent.embed(prior_ai_text[:200], purpose="user query")
        if not emb:
            return
        results = self._brain_db.semantic_search_knowledge(person_name, emb, top_k=1)
        if not results:
            return
        top = results[0]
        kid = self._brain_db.find_knowledge_id(person_name, top["attribute"], top["value"])
        if kid is not None:
            self._brain_db.update_confirmation(kid)
            print(
                f"[BrainAgent] Confirmation reset decay: {person_name}.{top['attribute']}"
                f" (+{CONFIDENCE_BOOST:.2f}, last_confirmed_at=now)"
            )

    def _advance_session_counter(
        self, person_id: str | None, person_name: str
    ) -> None:
        """Increment per-person turn counter; fire intra-session pref at INTRA_PREF_TURN."""
        if not person_id:
            return
        count = self._session_turn_counts.get(person_id, 0) + 1
        self._session_turn_counts[person_id] = count
        if count == INTRA_PREF_TURN and person_id not in self._intra_pref_done:
            self._intra_pref_done.add(person_id)
            asyncio.create_task(
                self._run_pref_analysis(
                    person_id,
                    turns_limit=INTRA_PREF_TURNS_LIMIT,
                    min_confidence=0.85,
                    source_override="human",
                )
            )
            print(f"[PromptPrefAgent] Intra-session lightweight pass fired for {person_name}")

    def get_prompt_addendum(self, person_id: str) -> str | None:
        """Return active communication prefs + proactive nudges for LLM injection.

        Synchronous SQLite reads (<2ms total). Returns None when nothing pending.
        Called every turn in conversation_turn() — same pattern as get_context().

        P0.S7.5 D1 — nudge consumption gates on `ONE_SHOT_NUDGE_TYPES`
        membership. One-shot proactive types (CROSS_PERSON_HYPOTHESIS,
        INTENTION_FOLLOWUP, MEMORY_PROMPT) get mark_nudge_injected on
        first delivery (legacy behavior). Persistent context types
        (VISITOR_ALERT) stay pending until naturally expired or
        dismissed — owner needs the visitor context whenever they
        ask, not just on the first re-engagement turn.

        Canary 2026-05-19 root cause: VISITOR_ALERT was being consumed
        on the first turn of Jagan's re-engagement; the next turn's
        addendum had nudge=no, the VISITOR CONTEXT block went dormant,
        and brain fabricated "No one was here, I was just waiting."
        """
        parts: list[str] = []
        pref_text = self._brain_db.get_prompt_addendum(person_id)
        if pref_text:
            parts.append(pref_text)
        nudges = self._brain_db.get_pending_nudges(person_id, limit=1)
        if nudges:
            nudge = nudges[0]
            parts.append(
                f"[Proactive — work naturally into conversation if the moment fits: "
                f"{nudge['content']}]"
            )
            # D1: only mark one-shot types as injected. Persistent
            # context types (VISITOR_ALERT) re-inject every turn.
            from core.config import ONE_SHOT_NUDGE_TYPES
            _nudge_type = nudge.get("nudge_type") or ""
            if _nudge_type in ONE_SHOT_NUDGE_TYPES:
                self._brain_db.mark_nudge_injected(nudge["id"])
            else:
                # LOW 2 (Plan v2 §3.2) — re-injection observability for
                # re-canary cost validation. Counts log lines per
                # session: bounded (~1-3 turns) = healthy; excessive
                # (~20+ turns) = signal to file follow-up for
                # auto-dismiss heuristic.
                print(
                    f"[PromptPrefAgent] persistent nudge re-injected "
                    f"(type={_nudge_type}, id={nudge['id']})"
                )
        if parts:
            print(f"[PromptPrefAgent] {len(parts)} addendum part(s) injected for {person_id} (prefs={'yes' if pref_text else 'no'}, nudge={'yes' if nudges else 'no'})")
        return "\n\n".join(parts) if parts else None

    async def _run_pref_analysis(
        self,
        person_id: str,
        turns_limit: int = PREF_ANALYSIS_TURNS,
        min_confidence: float = 0.7,
        source_override: str | None = None,
    ) -> None:
        """Analyze recent turns for communication preferences.

        Called at session end (full 40-turn pass, confidence >= 0.7) and optionally
        at INTRA_PREF_TURN mid-session (6-turn pass, confidence >= 0.85, source='human'
        so results activate immediately without the 3-session threshold).
        """
        try:
            row = self._faces_conn.execute(
                "SELECT name FROM persons WHERE id = ?", (person_id,)
            ).fetchone()
            if not row:
                return
            person_name = row[0]

            turns = self._faces_conn.execute(
                """SELECT role, content FROM conversation_log
                   WHERE person_id = ? ORDER BY id DESC LIMIT ?""",
                (person_id, turns_limit),
            ).fetchall()
            if not turns:
                return
            session_turns = [{"role": r[0], "content": r[1]} for r in reversed(turns)]

            existing   = self._brain_db.get_active_prefs(person_id)
            t0         = time.time()
            if self._pref_agent is None:  # SB.3 presence guard
                return
            prefs      = await self._pref_agent.analyze(person_name, existing, session_turns)
            elapsed_ms = (time.time() - t0) * 1000

            # Filter by min_confidence (PromptPrefAgent already enforces 0.7; this allows
            # the intra-session pass to raise the bar to 0.85 for explicit-only signals)
            if min_confidence > 0.7:
                prefs = [p for p in prefs if p.get("confidence", 1.0) >= min_confidence]

            if not prefs:
                print(f"[PromptPrefAgent] {person_name}: no new preferences ({elapsed_ms:.0f}ms)")
                return

            for p in prefs:
                source = source_override or "prompt_agent"
                content = p["content"]
                ptype   = p["pref_type"]

                # Bug L Part 2 (Session 69): blacklist mistake-recovery patterns.
                # PromptPrefAgent was inferring "avoid apologizing" from the LLM's
                # own apology in a Bug-N confabulation recovery — that's training
                # on noise. Reject these shapes at the activation gate.
                import re as _re_l
                if any(_re_l.search(bl, content, _re_l.IGNORECASE) for bl in PREF_BLACKLIST_PATTERNS):
                    print(
                        f"[PromptPrefAgent] {person_name}: blacklisted pref rejected "
                        f"[{ptype}] {content}"
                    )
                    continue

                # Bug L Part 1 (Session 69): semantic dedup. If the new pref is
                # near-identical to one already recorded for this person+type,
                # bump the existing row's sessions_seen instead of inserting a
                # near-duplicate. The 2026-04-20 run produced 4 separate
                # "Prefers brief responses" rows with minor wording variations.
                import numpy as _np_l
                if self._embed_agent is not None:  # SB.3 presence guard
                    new_emb = await self._embed_agent.embed(content, purpose="user preference")
                else:
                    new_emb = None
                dedup_handled = False
                if new_emb is not None:
                    new_vec = _np_l.asarray(new_emb, dtype=_np_l.float32)
                    existing_for_type = self._brain_db.get_prefs_by_type(person_id, ptype)
                    for existing in existing_for_type:
                        old_bytes = existing.get("embedding")
                        if old_bytes is None:
                            # Pre-migration row — embed now and backfill.
                            if self._embed_agent is None:  # SB.3 presence guard
                                continue
                            old_emb_list = await self._embed_agent.embed(
                                existing["content"], purpose="user preference"
                            )
                            if old_emb_list is None:
                                continue
                            old_vec = _np_l.asarray(old_emb_list, dtype=_np_l.float32)
                            self._brain_db.set_pref_embedding(existing["id"], old_vec.tobytes())
                        else:
                            old_vec = _np_l.frombuffer(old_bytes, dtype=_np_l.float32)
                        # E5 vectors are L2-normalized → dot product is cosine.
                        sim = float(_np_l.dot(new_vec, old_vec))
                        if sim >= PREF_DEDUP_THRESHOLD:
                            self._brain_db.bump_pref_seen(existing["id"])
                            print(
                                f"[PromptPrefAgent] {person_name}: strengthened "
                                f"(sim={sim:.2f}) [{ptype}] {existing['content']}"
                            )
                            dedup_handled = True
                            break
                if dedup_handled:
                    continue

                # No semantic match — fall through to the exact-string dedup +
                # insert path. Backfill the embedding on fresh rows so the next
                # activation can semantic-compare without re-embedding history.
                is_new = self._brain_db.store_pref(
                    person_id, ptype, content, source=source
                )
                if is_new and new_emb is not None:
                    _pref_id = self._brain_db.get_latest_pref_id(
                        person_id, ptype, content
                    )
                    if _pref_id is not None:
                        self._brain_db.set_pref_embedding(
                            _pref_id,
                            _np_l.asarray(new_emb, dtype=_np_l.float32).tobytes(),
                        )
                status = "activated (new)" if is_new else "seen again (+1 session)"
                print(
                    f"[PromptPrefAgent] {person_name}: {status} [{source}]"
                    f" — [{ptype}] {content}"
                )

        except Exception as e:
            print(f"[PromptPrefAgent] Error for {person_id}: {e}")
            import traceback
            traceback.print_exc()

    async def dream(self) -> None:
        """Pattern 4: autoDream — decay + hard-cap table pruning.

        Applies decay writes to all non-invalidated facts:
        - Below DREAM_PRUNE_FLOOR: soft-deleted (no longer appears in context).
        - Otherwise: stored confidence updated to current effective (decayed) value.
        Also prunes tables that grow unboundedly (presence_log, episodes,
        social_mentions, expired nudges, old resolved alerts).
        Runs schema normalization afterward to tidy attribute synonyms.
        Fully decoupled from the conversation — never blocks a turn.
        """
        all_persons = self._faces_conn.execute("SELECT id FROM persons").fetchall()
        print(f"[Dream] Consolidation started — {len(all_persons)} person(s) in DB")
        pruned, decayed, stable = self._brain_db.decay_and_prune(
            DREAM_PRUNE_FLOOR, DREAM_DECAY_WRITE_THRESHOLD
        )
        k_cap   = self._brain_db.prune_knowledge_hard_cap(KNOWLEDGE_MAX_ROWS)
        p_cap   = self._brain_db.prune_presence_log(PRESENCE_MAX_ROWS)
        ep_cap  = self._brain_db.prune_episodes(EPISODE_MAX_ROWS)
        sm_cap  = self._brain_db.prune_social_mentions(SOCIAL_MENTIONS_MAX_ROWS)
        n_exp   = self._brain_db.prune_expired_nudges()
        wa_old  = self._brain_db.prune_old_resolved_alerts(WATCHDOG_MAX_AGE_DAYS)
        al_old  = self._brain_db.prune_agent_log(AGENT_LOG_MAX_AGE_DAYS, AGENT_LOG_MAX_ROWS)
        prf_exp = self._brain_db.prune_expired_prefs()
        pq_old  = self._brain_db.prune_old_pattern_questions(PATTERN_Q_MAX_AGE_DAYS)
        removed = self._brain_db.prune_shadow_persons(max_age_days=90)
        if self._schema_norm is not None:  # SB.3 presence guard
            await self._schema_norm.maybe_run()
        table_removed = k_cap + p_cap + ep_cap + sm_cap + n_exp + wa_old + al_old + prf_exp + pq_old + removed
        print(
            f"[Dream] Consolidated — {pruned} pruned, {decayed} decayed, {stable} stable"
            + (f" | tables: {table_removed} rows removed" if table_removed else "")
        )

    def wipe(self) -> None:
        """Wipe all brain data — SQLite knowledge + graph entities."""
        self._brain_db.wipe()
        self._graph_db.wipe()

    def close_connections(self) -> None:
        """Close all database file handles.

        Called before wipe_all() during factory reset so that Windows can
        delete the underlying files (open handles block deletion on Windows).
        Call wipe() first (while connections are still valid), then this,
        then wipe_all(), then reopen_connections().
        """
        try:
            self._brain_db.close()
        except Exception:
            pass  # CLEANUP: best-effort close before factory-reset file deletion
        try:
            self._faces_conn.close()
        except Exception:
            pass  # CLEANUP: best-effort close before factory-reset file deletion
        try:
            self._graph_db.close()
        except Exception:
            pass  # CLEANUP: best-effort close before factory-reset file deletion

    def reopen_connections(self) -> None:
        """Re-open all database connections after wipe_all() has deleted the files.

        Creates fresh connections to the newly created empty DB files and
        rebuilds all agent references that hold direct DB handles.

        Calls wipe() on the newly opened brain.db to guarantee clean state.
        On Windows, wipe_all() can fail to delete brain.db if the file is still
        locked by in-flight background tasks.  This second wipe() is the safety
        net that ensures any rows written after the first wipe() are also cleared.
        """
        self._brain_db   = BrainDB(self._brain_db_path)
        self._brain_db.wipe()          # safety net: clear any rows written during the race window
        self._graph_db   = GraphDB(self._graph_db_path)
        self._faces_conn = sqlite3.connect(
            self._faces_db_path, check_same_thread=False,
            isolation_level="IMMEDIATE",  # P0.9.1 Imp-1
        )
        # SB.3 (PI-1) — rebuild ONLY the registered DB-handle agents (deps touch a
        # reopened source). Companion: schema+routine+nudge+watchdog (the same 4).
        # A clone registering no knowledge agents rebuilds only what it has (e.g.
        # just watchdog) → the reset-bypass leak is closed by construction, not by
        # a guard the golden/canary is blind to.
        self._build_agents(only={"brain_db", "faces_conn", "graph_db"})
        self._ensure_graph_sync()

    def prune_brain_data(self, person_ids: list) -> int:
        """Delete all brain.db rows for the given person_ids.

        Called from pipeline._dream_loop() after faces.db stranger pruning to ensure
        no orphaned knowledge, nudges, or log rows remain for deleted stranger sessions.
        """
        return self._brain_db.delete_person_data(person_ids)

    async def close(self) -> None:
        await self._http.aclose()
        self._faces_conn.close()
        self._brain_db.close()
        self._graph_db.close()
