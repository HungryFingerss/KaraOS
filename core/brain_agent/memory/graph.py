"""core/brain_agent/memory/graph.py — GraphDB (Kuzu property graph).

Extracted VERBATIM from core/brain_agent.py (P1.A1 SP-2 Commit 3). Behavior-
neutral; core/brain_agent/__init__.py re-exports GraphDB. The Kuzu sentinel
machinery (_mark_kuzu_dirty / _clear_kuzu_dirty / _is_kuzu_dirty /
_kuzu_dirty_path) and _ensure_graph_sync's SQL-last ordering stay on
BrainOrchestrator (move at SP-3, not here).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import shutil
import time
from pathlib import Path

import kuzu

from core.config import PRIVACY_LEVEL_DEFAULT
from core.brain_agent._llm import _valid_until
from core.brain_agent.privacy import _assert_valid_privacy_level
from core.brain_agent.context import _format_context_lines


class GraphDB:
    """Kuzu property graph — entities linked by extracted facts.

    Sits alongside SQLite: SQLite = crash recovery source of truth,
    Kuzu = rich graph queries (1-hop traversal, relationship context).
    Rebuilt automatically from SQLite if empty at startup.

    Schema:
        Entity(name STRING PRIMARY KEY, entity_type STRING)
        RELATES_TO(attribute, value, confidence, is_temporal, valid_until,
                   invalidated, source_turn_id, created_at)
    """

    def __init__(self, path: Path) -> None:
        try:
            self._db = kuzu.Database(str(path))
        except Exception as e:
            # Kuzu's native init throws IndexError / RuntimeError / generic
            # Exception on corruption, version mismatch, or half-written files
            # (e.g. Ctrl+C during a graph edit). Since the graph is rebuildable
            # from SQLite via BrainOrchestrator._ensure_graph_sync(), we recover
            # by wiping the path and re-creating. Knowledge facts are preserved
            # in brain.db and rebuilt on next sync. If the retry also fails,
            # re-raise — that's a genuine environmental issue (disk-full, perms).
            import shutil
            print(
                f"[GraphDB] Kuzu open failed at {path} "
                f"({type(e).__name__}: {e}). Wiping + recreating — "
                f"facts will be rebuilt from SQLite on next sync."
            )
            p = Path(path)
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
            for suffix in (".wal", "-lock"):
                Path(str(path) + suffix).unlink(missing_ok=True)
            self._db = kuzu.Database(str(path))
        self._conn = kuzu.Connection(self._db)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            "CREATE NODE TABLE IF NOT EXISTS Entity("
            "name STRING, entity_type STRING, PRIMARY KEY (name))"
        )
        # valid_at added in GRAPH_SCHEMA_VERSION=1 (Item 3).
        # privacy_level added in GRAPH_SCHEMA_VERSION=3 (P0.S7.D-B). Edge-level
        # placement (D2): privacy is per-fact granularity, not per-entity. Same
        # target entity (e.g. 'diabetes') can appear in multiple edges with
        # different attribute names + different privacy_levels. Cross-person
        # `find_shared_entities` filters at `r.privacy_level = 'public'`.
        # Kuzu does not support ALTER TABLE on rel tables — schema changes require
        # BrainOrchestrator._ensure_graph_sync() to wipe + rebuild from SQLite.
        self._conn.execute(
            "CREATE REL TABLE IF NOT EXISTS RELATES_TO("
            "FROM Entity TO Entity,"
            "attribute STRING, value STRING, confidence DOUBLE,"
            "is_temporal BOOLEAN, valid_until DOUBLE, valid_at DOUBLE,"
            "invalidated BOOLEAN, source_turn_id INT64, created_at DOUBLE,"
            "privacy_level STRING)"
        )

    def upsert_entity(self, name: str, entity_type: str) -> None:
        # Single MERGE: ON CREATE initialises type; ON MATCH upgrades "value" placeholder to real type
        self._conn.execute(
            "MERGE (e:Entity {name: $name})"
            " ON CREATE SET e.entity_type = $etype"
            " ON MATCH SET e.entity_type ="
            " CASE WHEN e.entity_type = 'value' THEN $etype ELSE e.entity_type END",
            {"name": name, "etype": entity_type},
        )

    def _create_edge(
        self,
        src: str, tgt: str,
        attribute: str, value: str,
        confidence: float, is_temporal: bool,
        valid_until: float | None, valid_at: float | None,
        invalidated: bool, source_turn_id: int, created_at: float,
        privacy_level: str = "personal",
    ) -> None:
        # P0.S7.D-B D4: privacy_level defaults to 'personal' (matches
        # PRIVACY_LEVEL_DEFAULT from S106). Legacy callers OR forgotten
        # kwargs get the safest tier. Phase 3 inverse-check guards that
        # every production caller passes privacy_level= explicitly.
        # P0.S4 D1 — fail-loud at the Kuzu write boundary too. The graph
        # filter at find_shared_entities reads r.privacy_level; an invalid
        # tier slipping through would produce edges that are structurally
        # invisible to cross-person matching. Same caller-side try/except
        # wrapper protection as store_knowledge — raises propagate to the
        # background-task wrapper and log without crashing the pipeline.
        _assert_valid_privacy_level(
            privacy_level,
            f"GraphDB._create_edge (src={src!r}, attr={attribute!r})",
        )
        self._conn.execute(
            "MATCH (src:Entity {name: $src}), (tgt:Entity {name: $tgt})"
            " CREATE (src)-[:RELATES_TO {"
            "attribute: $attr, value: $val, confidence: $conf,"
            "is_temporal: $temporal, valid_until: $valid_until, valid_at: $valid_at,"
            "invalidated: $inv, source_turn_id: $turn_id, created_at: $now,"
            "privacy_level: $privacy"
            "}]->(tgt)",
            {
                "src": src, "tgt": tgt,
                "attr": attribute, "val": value,
                "conf": confidence, "temporal": is_temporal,
                "valid_until": valid_until, "valid_at": valid_at,
                "inv": invalidated,
                "turn_id": source_turn_id, "now": created_at,
                "privacy": privacy_level,
            },
        )

    def store_fact(self, ext: "Extraction", turn_id: int) -> None:
        now = time.time()
        self.upsert_entity(ext.entity, ext.entity_type)
        self.upsert_entity(ext.value, "value")
        # P0.S7.D-B: thread Extraction.privacy_level (set by S106
        # _classify_privacy_level) onto the edge so find_shared_entities
        # can filter cross-person traversal at Cypher level.
        self._create_edge(
            src=ext.entity, tgt=ext.value,
            attribute=ext.attribute, value=ext.value,
            confidence=ext.confidence, is_temporal=ext.is_temporal,
            valid_until=_valid_until(ext.is_temporal, ext.valid_for_hours, now),
            valid_at=now,
            invalidated=False, source_turn_id=turn_id, created_at=now,
            privacy_level=ext.privacy_level,
        )

    def invalidate_fact(self, entity: str, attribute: str) -> None:
        self._conn.execute(
            "MATCH (src:Entity {name: $entity})-[r:RELATES_TO]->()"
            " WHERE r.attribute = $attr AND r.invalidated = false"
            " SET r.invalidated = true",
            {"entity": entity, "attr": attribute},
        )

    def rebuild_entity_from_knowledge(self, entity_name: str, rows: list[dict]) -> None:
        """Create or refresh a Kuzu entity node from SQLite knowledge rows.

        Called after migrate_entity_name() to keep the graph in sync with the
        newly renamed entity. We do NOT rename the old node (Kuzu primary keys
        are immutable and the old name may be shared by other strangers), so we
        only ADD the new node and its edges.

        Each row must have: attribute, value, confidence, is_temporal,
        valid_until, valid_at, source_turn_id, created_at.
        """
        if not rows:
            return
        try:
            self.upsert_entity(entity_name, "person")
            for row in rows:
                self.upsert_entity(row["value"], "value")
                # P0.S7.D-B: thread privacy_level from brain.db row.
                # Fail-closed to PRIVACY_LEVEL_DEFAULT ('personal') for
                # pre-S106 rows that lack the column.
                self._create_edge(
                    src=entity_name,
                    tgt=row["value"],
                    attribute=row["attribute"],
                    value=row["value"],
                    confidence=row["confidence"],
                    is_temporal=bool(row["is_temporal"]),
                    valid_until=row.get("valid_until"),
                    valid_at=row.get("valid_at"),
                    invalidated=False,
                    source_turn_id=row.get("source_turn_id") or 0,
                    created_at=row.get("created_at") or time.time(),
                    privacy_level=row.get("privacy_level") or PRIVACY_LEVEL_DEFAULT,
                )
            print(f"[GraphDB] rebuild_entity_from_knowledge: '{entity_name}' ({len(rows)} edges)")
        except Exception as e:
            print(f"[GraphDB] rebuild_entity_from_knowledge error: {e}")

    def get_graph_context(
        self,
        entity_name: str,
        caller_pid: "str | None" = None,
        best_friend_id: "str | None" = None,
    ) -> str | None:
        """Return formatted 1-hop context for LLM injection. None if entity unknown.

        Confidence filter is applied in Python (not Kuzu Cypher) so that decay is
        respected: a 0.80-confidence fact from 2 years ago won't appear in context.

        P0.S7.D-B (DEFENSE-IN-DEPTH): Cypher WHERE adds a privacy filter
        mirroring the SQL `_visibility_clause` semantic:
          - ``caller_pid == entity_name`` (owner) → all tiers visible
            except 'system_only' (matches SQL best_friend / owner-of-fact)
          - ``caller_pid == best_friend_id`` (household owner) → all
            tiers visible except 'system_only'
          - ``caller_pid is None`` OR caller is neither owner nor
            best_friend → fail-closed public-only (Plan v1 P1, Plan v2
            §3.3)

        D3 framing (Plan v2 §3.4): this filter is **defense-in-depth**.
        The existing ``if not _filtering:`` skip at the single production
        caller (``BrainOrchestrator.get_context`` site) was already
        preventing the cross-person leak. The Cypher filter raises the
        floor against future code-path additions that bypass the
        defensive skip. D1's ``find_shared_entities`` filter is the
        load-bearing privacy fix; D3 is hardening, not active-leak
        closure.
        """
        now = time.time()
        # D3 fail-closed default — when caller identity is unknown,
        # filter to public-only. caller_pid == entity_name treated as
        # the "self-query" / owner-override branch (matches owner-check
        # arm of SQL _visibility_clause).
        if caller_pid is not None and (
            caller_pid == entity_name
            or (best_friend_id is not None and caller_pid == best_friend_id)
        ):
            _privacy_clause = "AND r.privacy_level <> 'system_only'"
        else:
            _privacy_clause = "AND r.privacy_level = 'public'"
        try:
            result = self._conn.execute(
                "MATCH (src:Entity {name: $name})-[r:RELATES_TO]->()"
                " WHERE r.invalidated = false"
                " AND (r.valid_until IS NULL OR r.valid_until > $now)"
                " AND r.confidence >= 0.30"
                f" {_privacy_clause}"
                " RETURN r.attribute, r.value, r.confidence, r.is_temporal, r.valid_until,"
                " r.valid_at, r.created_at"
                " ORDER BY r.created_at DESC",
                {"name": entity_name, "now": now},
            )
        except Exception as e:
            print(f"[GraphDB] get_graph_context error (schema mismatch?): {e}")
            return None
        rows = result.get_all()
        if not rows:
            return None
        facts = [
            {
                "attribute":         r[0], "value":       r[1],
                "confidence":        r[2], "is_temporal":  r[3],
                "valid_until":       r[4],
                "valid_at":          r[5] if r[5] else r[6],   # fall back to created_at
                "last_confirmed_at": None,  # graph doesn't store this; decay from valid_at
            }
            for r in rows
        ]
        return _format_context_lines(entity_name, facts)

    def find_shared_entities(
        self,
        person_a: str,
        person_b: str,
        min_confidence: float = 0.50,
    ) -> list[dict]:
        """Find entity nodes (values) that appear in both persons' 1-hop graphs.

        Queries each person's outgoing RELATES_TO edges in Python (two fast Kuzu
        calls), then intersects the value sets. Returns shared entities with the
        attribute context from each side.

        Used by ProactiveNudgeAgent to generate cross-person hypotheses:
        e.g. stranger said "cousin Ravi" + best_friend has "cousin Ravi" → match.

        Session 107 Phase 3A.6 Part 4 — Kuzu privacy audit finding:
        this traversal returns entity values directly from the graph, NOT
        from SQL. The graph's RELATES_TO edges currently carry no
        privacy_level property, so a sensitive value that happens to
        appear in both persons' graphs (e.g. a health_condition value
        like "diabetes") would surface as a shared entity without any
        tier filter.

        Session 112 Part 4 — session-isolation audit (DECISION at
        the time: option (a) skip v3 bump, SQL filter is sufficient
        because cross-person matches were entity-name-only and
        personal-tier room-context facts weren't being written to
        OTHER speakers' graphs). The decision was correct AT THE TIME
        — but was reversed by P0.S7.D-B below.

        P0.S7.D-B (2026-05-19) — Kuzu v3 schema bump SHIPPED. The
        S107 + S112 deferral premise was falsified by P0.S7.2 κ
        multi-person assistant-turn extraction (2026-05-19): κ writes
        personal-tier `received_*` / `witnessed_*` facts to brain.db;
        graph rebuild ingests them as RELATES_TO edges. Without the
        privacy_level filter, third-party visitors could surface
        another person's personal-tier facts through cross-person
        matching. The S112 deferral was load-bearing in light of κ;
        D-B is the active-leak fix.

        v3 fix (LOAD-BEARING):
          - RELATES_TO edges now carry `privacy_level STRING` (D2
            edge-level placement — same target entity name can appear
            in multiple edges with different attribute names AND
            different privacy_levels).
          - Cypher WHERE filter `r.privacy_level = 'public'` applied
            here: ONLY public-tier edges participate in cross-person
            traversal. Personal/household/system_only are filtered at
            Cypher level (Plan v2 §4 D1 lock).
          - Cross-person owner-override (P0.S7 P1 (ii)) does NOT apply
            to graph traversal — owner-override is for `query_knowledge_for`
            where the requester is identified; graph queries are
            recipient-agnostic by nature.

        Schema-concept clarifier (Plan v2 §4 LOW 2):
        each RELATES_TO edge has three relevant properties — `attribute`
        (the predicate, e.g. 'discussed_topic'), `value` (the target
        entity's name, mirrored from the target node), and `privacy_level`
        (the v3 property). The same target entity (same `value`) can
        appear in multiple edges with different attribute names AND
        different privacy_levels. The cross-person filter operates on
        `edge.privacy_level`, NOT on `entity.name`.
        """
        now = time.time()

        def _get_facts(name: str) -> dict[str, list[tuple[str, str]]]:
            """Return {value_lower: [(attribute, value), ...]} for a person.

            P0.S7.D-B: Cypher WHERE adds `r.privacy_level = 'public'`.
            ONLY public-tier edges participate in cross-person traversal.
            """
            try:
                result = self._conn.execute(
                    "MATCH (src:Entity {name: $name})-[r:RELATES_TO]->(tgt:Entity)"
                    " WHERE r.invalidated = false"
                    " AND (r.valid_until IS NULL OR r.valid_until > $now)"
                    " AND r.confidence >= $conf"
                    " AND r.privacy_level = 'public'"
                    " RETURN r.attribute, r.value, tgt.entity_type",
                    {"name": name, "now": now, "conf": min_confidence},
                )
                rows = result.get_all()
            except Exception as _e:
                # #123 D3: LOG the graph-read failure. A silent {} degrades cross-person
                # inference to "no graph knowledge" with no diagnostic (the _kuzu_degraded /
                # P0.X class). Keep returning {} (callers tolerate it), but surface why.
                print(f"[Graph] cross-person RELATES_TO read failed for {name!r}: {_e!r} "
                      f"— degrading to no-graph-knowledge")
                return {}
            out: dict[str, list[tuple[str, str, str]]] = {}
            for attr, val, etype in rows:
                key = val.lower()
                out.setdefault(key, []).append((attr, val, etype or "value"))
            return out

        facts_a = _get_facts(person_a)
        facts_b = _get_facts(person_b)
        shared_keys = set(facts_a) & set(facts_b)

        results = []
        for key in shared_keys:
            for attr_a, val_a, etype_a in facts_a[key]:
                for attr_b, val_b, etype_b in facts_b[key]:
                    results.append({
                        "entity_name":  val_a,
                        "entity_type":  etype_a if etype_a != "value" else etype_b,
                        "a_attribute":  attr_a,
                        "a_value":      val_a,
                        "b_attribute":  attr_b,
                        "b_value":      val_b,
                    })
        return results

    def is_empty(self) -> bool:
        rows = self._conn.execute("MATCH (e:Entity) RETURN count(e)").get_all()
        return not rows or rows[0][0] == 0

    def entity_count(self) -> int:
        rows = self._conn.execute("MATCH (n:Entity) RETURN count(n)").get_all()
        return rows[0][0] if rows else 0

    def rebuild(self, knowledge_rows: list[dict]) -> None:
        """Populate graph from SQLite knowledge rows (startup sync).

        P0.S7.D-B: each row's `privacy_level` is threaded through to the
        edge so cross-person `find_shared_entities` traversal can filter
        at Cypher level. Legacy rows without the column fall back to
        ``PRIVACY_LEVEL_DEFAULT`` ('personal').
        """
        for row in knowledge_rows:
            self.upsert_entity(row["entity"], row["entity_type"])
            self.upsert_entity(row["value"], "value")
            try:
                self._create_edge(
                    src=row["entity"], tgt=row["value"],
                    attribute=row["attribute"], value=row["value"],
                    confidence=row["confidence"], is_temporal=bool(row["is_temporal"]),
                    valid_until=row.get("valid_until"),
                    valid_at=row.get("valid_at") or row.get("created_at"),
                    invalidated=row["invalidated_at"] is not None,
                    source_turn_id=row["source_turn_id"],
                    created_at=row["created_at"],
                    privacy_level=row.get("privacy_level") or PRIVACY_LEVEL_DEFAULT,
                )
            except Exception as e:
                print(f"[GraphDB] Rebuild skipped edge {row['entity']}.{row['attribute']}: {e}")

    def drop_schema(self) -> None:
        """Drop all Kuzu tables (schema + data).

        Called before _init_schema() on schema-version upgrades so that
        CREATE REL/NODE TABLE is not a no-op on the old-schema table.
        `wipe()` only deletes rows (DETACH DELETE); it cannot alter column
        definitions — the only way to change a Kuzu rel table schema is to
        DROP + re-CREATE it.
        """
        for stmt in ("DROP TABLE IF EXISTS RELATES_TO", "DROP TABLE IF EXISTS Entity"):
            self._conn.execute(stmt)

    def delete_person_entity(self, person_name: str) -> bool:
        """Delete the Entity node for person_name and all its edges from the graph.

        Returns True if the DELETE executed without error (node may or may not have existed).
        """
        try:
            self._conn.execute(
                "MATCH (e:Entity {name: $name}) DETACH DELETE e",
                {"name": person_name},
            )
            return True
        except Exception as exc:
            print(f"[GraphDB] delete_person_entity failed for '{person_name}': {exc}")
            return False

    def wipe(self) -> None:
        self._conn.execute("MATCH (e:Entity) DETACH DELETE e")

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        if self._db is not None:
            self._db.close()
            self._db = None
