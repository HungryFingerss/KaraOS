"""
P0.X — brain.db ↔ Kuzu cross-write divergence (slow crash-injection tier).

Architecture:
  brain.db (BrainDB/SQLite) = durable source of truth.
  Kuzu graph               = rebuildable derived view.
  Sentinel file            = graph_db_path + ".dirty"
                             written BEFORE destructive Kuzu op,
                             cleared on success, preserved on failure.

Patterns exercised:
  SCHEMA_MIGRATION (_ensure_graph_sync):
    - sentinel written before drop_schema in _ensure_graph_sync
    - SQL version bump committed BEFORE drop_schema
    - rebuild failure at boot → _kuzu_degraded=True, no raise from __init__
    - sentinel OR count-mismatch triggers rebuild on next boot

  RAISE (on_identity_confirmed):
    - SQL transaction commits, then sentinel written, then Kuzu write
    - Kuzu crash → exception propagates, sentinel preserved

  SWALLOW (_persist_extraction_to_kuzu):
    - Kuzu crash → sentinel written, exception swallowed (no re-raise)

  SWALLOW (_process_turn ContradictionAgent loop):
    - _graph_db.invalidate_fact crash → sentinel written, exception swallowed
    - brain.db invalidation committed before Kuzu crash (SQL-first discipline)

All tests use BrainOrchestrator with tmp_path — no production files touched.
Kuzu write crashes are injected by monkeypatching GraphDB methods on the class;
Python method lookup is per-call so class patches propagate to existing instances.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import asyncio
import gc
import pytest
from pathlib import Path

from core.brain_agent import BrainDB, BrainOrchestrator, Extraction, GraphDB
from core.config import GRAPH_SCHEMA_VERSION


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_paths(tmp_path: Path) -> dict:
    return {
        "brain_db_path": tmp_path / "brain.db",
        "graph_db_path": str(tmp_path / "graph.db"),
        "faces_db_path": str(tmp_path / "faces.db"),
    }


def _sentinel_path(tmp_path: Path) -> Path:
    """Sentinel lives next to the Kuzu directory: graph.db.dirty"""
    return tmp_path / "graph.db.dirty"


def _add_knowledge_row(brain_db: BrainDB) -> None:
    """Insert one active knowledge row into an open BrainDB."""
    brain_db._conn.execute(
        "INSERT INTO knowledge "
        "(source_turn_id, person_id, entity, entity_type, attribute, value, "
        " confidence, is_temporal, agent, created_at, valid_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (1, "p1", "Alice", "person", "likes", "coffee", 0.9, 0, "test", 1.0, 1.0),
    )
    brain_db._conn.commit()


def _minimal_extraction() -> Extraction:
    return Extraction(
        entity="Alice", entity_type="person",
        attribute="likes", value="coffee",
        confidence=0.9, is_temporal=False, valid_for_hours=None,
    )


# ── SCHEMA_MIGRATION: drop_schema crash → degraded mode (not boot-crash) ─────

@pytest.mark.slow
def test_schema_migration_drop_schema_crash_comes_up_degraded(tmp_path, monkeypatch):
    """drop_schema() raises during schema upgrade → system comes up degraded, NOT boot-crash.

    P0.X architectural invariant: "Rebuild failure at boot → degraded mode
    (no raise from __init__)." This extends to drop_schema/init_schema during
    schema migration — the constructor must complete in degraded mode.

    Pre-P0.X: constructor raised RuntimeError — this test FAILED.
    P0.X post-fix: constructor completed with _kuzu_degraded=True, sentinel
                   preserved, brain.db at GRAPH_SCHEMA_VERSION (SQL-first).
    P0.B3 D1 (Finding 2 board-meeting 2026-05-21): SQL bump moved AFTER Kuzu
                   rebuild + sentinel clear. drop_schema crash now leaves
                   stored_version=OLD (not NEW) → next boot's migration
                   predicate (stored_version<GRAPH_SCHEMA_VERSION) re-triggers
                   the upgrade idempotently. This is the LOAD-BEARING fix.
                   (Plan v1 §1.1 Pass-2 grep undercounted this test file —
                   banked as P0.B3 Phase 4 in-flight observation.)
    """
    paths = _make_paths(tmp_path)

    def crashing_drop(self):
        raise RuntimeError("simulated drop_schema crash during schema upgrade")

    monkeypatch.setattr(GraphDB, "drop_schema", crashing_drop)

    # Constructor must complete — degraded mode instead of raising.
    orch = BrainOrchestrator(asyncio.Event(), **paths)
    try:
        assert orch._kuzu_degraded, (
            "_kuzu_degraded must be True when drop_schema crashes during schema upgrade"
        )
        assert _sentinel_path(tmp_path).exists(), (
            "sentinel must be preserved when drop_schema crashes — sentinel is "
            "written by _mark_kuzu_dirty() BEFORE drop_schema per ORDERING INVARIANT step 2"
        )
        assert orch._brain_db.get_graph_schema_version() < GRAPH_SCHEMA_VERSION, (
            "P0.B3 D1 LOAD-BEARING INVARIANT: brain.db version must stay OLD when "
            "drop_schema crashes — pre-fix the SQL bump happened BEFORE drop_schema "
            "(SQL=NEW + Kuzu=PARTIAL trap); post-fix the SQL bump is gated on "
            "_did_schema_upgrade AND lands AFTER _clear_kuzu_dirty (stored_version "
            "stays OLD on crash → next boot predicate re-triggers migration)"
        )
    finally:
        orch._brain_db._conn.close()
        orch._faces_conn.close()


@pytest.mark.slow
def test_schema_upgrade_drop_crash_leaves_old_version_and_sentinel(
    tmp_path, monkeypatch,
):
    """drop_schema raises before SQL version bump → degraded mode (no boot-crash).

    P0.X-era (Kuzu-first → SQL-first): update_graph_schema_version() was
    committed BEFORE drop_schema(). If drop_schema() crashed, the constructor
    completed in degraded mode with SQL version=GRAPH_SCHEMA_VERSION (durable).

    P0.B3 D1 (Finding 2 board-meeting 2026-05-21 fix): SQL bump moved AFTER
    Kuzu rebuild + _clear_kuzu_dirty, gated on _did_schema_upgrade captured
    at function entry. drop_schema crash now leaves stored_version=OLD
    (UPDATE never reached) — next boot's migration predicate retriggers
    the upgrade. This is the inverted assertion: SQL stays OLD on crash
    by design. The sentinel + degraded-mode invariants are unchanged.
    (Test renamed from `..._and_sql_committed` → `..._and_old_version` to
    reflect the new ordering. Plan v1 §1.1 Pass-2 grep undercounted this
    test file — banked as P0.B3 Phase 4 in-flight observation.)
    """
    paths = _make_paths(tmp_path)

    def crashing_drop(self):
        raise RuntimeError("simulated drop_schema crash")

    monkeypatch.setattr(GraphDB, "drop_schema", crashing_drop)

    orch = BrainOrchestrator(asyncio.Event(), **paths)
    try:
        assert orch._kuzu_degraded, (
            "_kuzu_degraded must be True when drop_schema crashes"
        )
        # Sentinel must exist — written by _mark_kuzu_dirty() before drop_schema.
        assert _sentinel_path(tmp_path).exists(), (
            "sentinel must be present after drop_schema crash"
        )
        # P0.B3 D1: SQL version bump must stay OLD — UPDATE never reached because
        # drop_schema raised before the rebuild block ran. Next boot's predicate
        # (stored_version < GRAPH_SCHEMA_VERSION) re-triggers migration.
        assert orch._brain_db.get_graph_schema_version() < GRAPH_SCHEMA_VERSION, (
            "P0.B3 D1 LOAD-BEARING INVARIANT: brain.db graph_schema_version must "
            "stay OLD when drop_schema crashes — the SQL bump moved AFTER Kuzu "
            "rebuild + sentinel clear, gated on _did_schema_upgrade, so any "
            "pre-rebuild crash leaves stored_version unchanged for predicate retry"
        )
    finally:
        orch._brain_db._conn.close()
        orch._faces_conn.close()


# ── SCHEMA_MIGRATION: recovery on second boot ─────────────────────────────────

@pytest.mark.slow
def test_schema_upgrade_crash_recovery_on_second_boot(tmp_path, monkeypatch):
    """Boot 2 recovers cleanly after Boot 1's drop_schema crash.

    Boot 1: drop_schema crashes → degraded mode (_kuzu_degraded=True), sentinel
            persists on disk, stored_version stays OLD (per P0.B3 D1 ordering —
            SQL bump moved AFTER Kuzu rebuild + _clear_kuzu_dirty), constructor
            completes degraded.
    Boot 2: stored_version < GRAPH_SCHEMA_VERSION → migration predicate TRUE
            → enter migration block → drop_schema (now unpatched) succeeds →
            _init_schema → rebuild path fires → empty DB → _clear_kuzu_dirty
            (sentinel cleared) → update_graph_schema_version (SQL bump lands
            at end-of-rebuild) → not degraded.

    Kuzu single-writer constraint: orch1 must be fully closed and gc'd before
    orch2 can open the same graph path.
    """
    paths = _make_paths(tmp_path)
    original_drop = GraphDB.drop_schema

    def crashing_drop(self):
        raise RuntimeError("simulated drop_schema crash")

    # ── Boot 1 ──
    monkeypatch.setattr(GraphDB, "drop_schema", crashing_drop)
    orch1 = BrainOrchestrator(asyncio.Event(), **paths)
    try:
        assert orch1._kuzu_degraded, "Boot 1 must be degraded after drop_schema crash"
    finally:
        orch1._brain_db._conn.close()
        orch1._faces_conn.close()
    del orch1
    gc.collect()

    assert _sentinel_path(tmp_path).exists(), "sentinel must survive Boot 1 crash"

    # Restore drop_schema for Boot 2.
    monkeypatch.setattr(GraphDB, "drop_schema", original_drop)

    # ── Boot 2 ──
    orch2 = BrainOrchestrator(asyncio.Event(), **paths)
    try:
        assert not orch2._kuzu_degraded, "Boot 2 should recover to non-degraded state"
        assert not _sentinel_path(tmp_path).exists(), (
            "sentinel must be cleared after successful Boot 2 recovery"
        )
    finally:
        orch2._brain_db._conn.close()
        orch2._faces_conn.close()


# ── SCHEMA_MIGRATION: rebuild failure → degraded mode ────────────────────────

@pytest.mark.slow
def test_rebuild_failure_at_boot_sets_degraded_mode(tmp_path, monkeypatch):
    """GraphDB.rebuild raises → _kuzu_degraded=True, sentinel preserved, no raise.

    P0.X boot invariant: rebuild failure must NEVER propagate from __init__.
    System comes up in degraded mode (reads return empty) rather than crashing.
    Sentinel preserved so the NEXT boot retries reconciliation.
    """
    paths = _make_paths(tmp_path)

    # Pre-populate brain.db with one knowledge row so get_all_knowledge_rows()
    # is non-empty, ensuring the 'if knowledge_rows:' branch is reached.
    setup_db = BrainDB(paths["brain_db_path"])
    _add_knowledge_row(setup_db)
    setup_db._conn.close()

    def crashing_rebuild(self, rows):
        raise RuntimeError("simulated Kuzu rebuild failure")

    monkeypatch.setattr(GraphDB, "rebuild", crashing_rebuild)

    # Constructor must complete — degraded mode instead of raising.
    orch = BrainOrchestrator(asyncio.Event(), **paths)
    try:
        assert orch._kuzu_degraded, (
            "_kuzu_degraded must be True after rebuild fails at boot"
        )
        # Sentinel preserved so next boot retries.
        assert _sentinel_path(tmp_path).exists(), (
            "sentinel must be preserved when rebuild fails (next-boot retry needed)"
        )
    finally:
        orch._brain_db._conn.close()
        orch._faces_conn.close()


# ── SCHEMA_MIGRATION: sentinel triggers rebuild ───────────────────────────────

@pytest.mark.slow
def test_sentinel_on_disk_triggers_rebuild_on_boot(tmp_path):
    """Sentinel left by a prior aborted write triggers rebuild on next boot.

    Pre-boot: set graph_schema_version=GRAPH_SCHEMA_VERSION (no upgrade needed),
              manually write sentinel (simulates a prior crashed Kuzu op).
    Boot: boot reconciliation sees sentinel → need_rebuild=True → empty DB
          → no actual graph writes → sentinel cleared → not degraded.
    """
    paths = _make_paths(tmp_path)

    # Set version to current so schema upgrade path is skipped.
    setup_db = BrainDB(paths["brain_db_path"])
    setup_db.update_graph_schema_version(GRAPH_SCHEMA_VERSION)
    setup_db._conn.close()

    # Simulate a sentinel left behind by a prior mid-write crash.
    _sentinel_path(tmp_path).touch()
    assert _sentinel_path(tmp_path).exists(), "pre-condition: sentinel on disk"

    orch = BrainOrchestrator(asyncio.Event(), **paths)
    try:
        assert not orch._kuzu_degraded, "rebuild should succeed (empty brain.db)"
        assert not _sentinel_path(tmp_path).exists(), (
            "sentinel must be cleared after successful rebuild triggered by sentinel"
        )
    finally:
        orch._brain_db._conn.close()
        orch._faces_conn.close()


# ── SCHEMA_MIGRATION: entity count mismatch triggers rebuild ─────────────────

@pytest.mark.slow
def test_entity_count_mismatch_triggers_rebuild(tmp_path):
    """Entity count divergence (brain.db > Kuzu) triggers rebuild without sentinel.

    Pre-boot: version=GRAPH_SCHEMA_VERSION, 1 active entity in brain.db,
              fresh Kuzu (0 entities) → mismatch → rebuild fires.
    Post-boot: graph populated, not degraded, no sentinel on disk.
    """
    paths = _make_paths(tmp_path)

    # Pre-populate brain.db: version=current + one knowledge row.
    setup_db = BrainDB(paths["brain_db_path"])
    setup_db.update_graph_schema_version(GRAPH_SCHEMA_VERSION)
    _add_knowledge_row(setup_db)
    setup_db._conn.close()

    # Sentinel must not exist before boot.
    assert not _sentinel_path(tmp_path).exists()

    # Boot: fresh Kuzu (0 entities) vs brain.db (1 entity "Alice") → mismatch.
    orch = BrainOrchestrator(asyncio.Event(), **paths)
    try:
        assert not orch._kuzu_degraded, "rebuild should succeed for count mismatch"
        # Count-mismatch path does not write the sentinel (only reads it).
        assert not _sentinel_path(tmp_path).exists(), (
            "no sentinel expected after count-mismatch rebuild (sentinel never written)"
        )
    finally:
        orch._brain_db._conn.close()
        orch._faces_conn.close()


# ── RAISE pattern ─────────────────────────────────────────────────────────────

@pytest.mark.slow
def test_on_identity_confirmed_kuzu_crash_raises_and_leaves_sentinel(
    tmp_path, monkeypatch,
):
    """on_identity_confirmed: brain.db succeeds, Kuzu crash → raises, sentinel kept.

    RAISE pattern:
      1. SQL transaction commits (migrate/promote/visitor-alert — no-ops on empty DB).
      2. Eager sentinel written BEFORE Kuzu op.
      3. GraphDB.rebuild_entity_from_knowledge raises.
      4. Exception propagates to caller.
      5. Sentinel preserved (not cleared) for next-boot reconciliation.
    """
    paths = _make_paths(tmp_path)
    orch = BrainOrchestrator(asyncio.Event(), **paths)

    # Confirm clean state before the test.
    assert not _sentinel_path(tmp_path).exists(), "no sentinel before RAISE test"

    def crashing_rebuild_entity(self, entity_name, rows):
        raise RuntimeError("simulated graph rebuild crash in on_identity_confirmed")

    monkeypatch.setattr(GraphDB, "rebuild_entity_from_knowledge", crashing_rebuild_entity)

    try:
        with pytest.raises(RuntimeError, match="simulated graph rebuild crash"):
            orch.on_identity_confirmed("p1", "OldName", "NewName")

        assert _sentinel_path(tmp_path).exists(), (
            "sentinel must be preserved after on_identity_confirmed Kuzu crash"
        )
    finally:
        orch._brain_db._conn.close()
        orch._faces_conn.close()


# ── SWALLOW pattern ───────────────────────────────────────────────────────────

@pytest.mark.slow
def test_persist_extraction_to_kuzu_crash_swallows_and_writes_sentinel(
    tmp_path, monkeypatch,
):
    """_persist_extraction_to_kuzu: Kuzu crash → sentinel written, no re-raise.

    SWALLOW pattern: brain.db is authoritative; Kuzu is derived state.
    A Kuzu write failure must NOT propagate — caller is never notified.
    Sentinel is written so next-boot reconciliation rebuilds the graph.
    """
    paths = _make_paths(tmp_path)
    orch = BrainOrchestrator(asyncio.Event(), **paths)

    assert not _sentinel_path(tmp_path).exists(), "no sentinel before SWALLOW test"

    def crashing_upsert_entity(self, entity_name, entity_type):
        raise RuntimeError("simulated Kuzu upsert failure")

    monkeypatch.setattr(GraphDB, "upsert_entity", crashing_upsert_entity)

    try:
        # Must not raise — SWALLOW pattern absorbs the Kuzu failure.
        orch._persist_extraction_to_kuzu([_minimal_extraction()], turn_id=1)

        assert _sentinel_path(tmp_path).exists(), (
            "sentinel must be written after _persist_extraction_to_kuzu Kuzu crash"
        )
    finally:
        orch._brain_db._conn.close()
        orch._faces_conn.close()


# ── SWALLOW pattern: _process_turn ContradictionAgent loop ───────────────────

@pytest.mark.slow
def test_process_turn_contradiction_agent_kuzu_crash_swallows_and_writes_sentinel(
    tmp_path, monkeypatch,
):
    """_process_turn ContradictionAgent invalidate_fact crash → sentinel written, no re-raise.

    SWALLOW pattern at _process_turn's ContradictionAgent loop — the hidden paired-write
    site found by the inverse check. brain.db state consistent (old fact invalidated via
    SQL before the Kuzu crash), Kuzu crash swallowed, sentinel written for next-boot
    reconciliation.
    """
    paths = _make_paths(tmp_path)
    orch = BrainOrchestrator(asyncio.Event(), **paths)

    # Initialize the minimal persons schema in faces.db so the household-extraction
    # query at line 7171 of brain_agent.py does not crash (that query is not inside
    # a try/except). BrainOrchestrator opens faces.db as a raw sqlite3 connection
    # without initialising FaceDB's schema, so we do it here.
    orch._faces_conn.execute(
        "CREATE TABLE IF NOT EXISTS persons "
        "(id TEXT PRIMARY KEY, name TEXT NOT NULL, enrolled_at REAL NOT NULL DEFAULT 0, "
        " person_type TEXT NOT NULL DEFAULT 'stranger')"
    )
    orch._faces_conn.commit()

    # Pre-populate brain.db with an existing fact that will be contradicted.
    _add_knowledge_row(orch._brain_db)  # Alice.likes=coffee

    assert not _sentinel_path(tmp_path).exists(), "no sentinel before SWALLOW test"

    # Triage: always pass so extraction is reached.
    monkeypatch.setattr(orch._triage, "should_process", lambda *a, **kw: (True, "test"))

    # ExtractionAgent: return a fact contradicting the existing Alice.likes=coffee.
    async def _mock_extract(*a, **kw):
        return [Extraction(
            entity="Alice", entity_type="person",
            attribute="likes", value="tea",
            confidence=0.9, is_temporal=False, valid_for_hours=None,
        )]
    monkeypatch.setattr(orch._extractor, "extract", _mock_extract)

    # ContradictionAgent: always return REPLACE.
    async def _mock_check(entity, attribute, old_val, new_val, count):
        return (True, "test replace reason")
    monkeypatch.setattr(orch._contradictor, "check", _mock_check)

    # GraphDB.invalidate_fact: crash — this is the site under test.
    monkeypatch.setattr(
        orch._graph_db,
        "invalidate_fact",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("simulated invalidate_fact crash")),
    )

    try:
        # (b) Must not raise — SWALLOW pattern absorbs the Kuzu failure.
        asyncio.run(orch._process_turn(
            turn_id=2,
            person_id="p1",
            person_name="Alice",
            role="user",
            content="I prefer tea now",
            context=[],
        ))

        # (a) Sentinel written by _mark_kuzu_dirty() in the except block.
        assert _sentinel_path(tmp_path).exists(), (
            "sentinel must be written after _process_turn ContradictionAgent Kuzu crash"
        )

        # (c) brain.db consistent — SQL invalidation ran BEFORE the Kuzu crash.
        row = orch._brain_db._conn.execute(
            "SELECT invalidated_at FROM knowledge "
            "WHERE person_id='p1' AND entity='Alice' AND attribute='likes' AND value='coffee'"
        ).fetchone()
        assert row is not None and row[0] is not None, (
            "brain.db must have invalidated the old 'coffee' fact (SQL-first discipline holds)"
        )

        # Close orch before booting orch2 (Kuzu single-writer constraint).
        orch._brain_db._conn.close()
        orch._faces_conn.close()
        for _attr in ("_conn", "_db"):
            _obj = getattr(orch._graph_db, _attr, None)
            if _obj is not None:
                _close_fn = getattr(_obj, "close", None)
                if _close_fn:
                    try:
                        _close_fn()
                    except Exception:
                        pass
        del orch
        gc.collect()

        # (d) Boot reconciliation fires on next construction — sentinel triggers rebuild.
        orch2 = BrainOrchestrator(asyncio.Event(), **paths)
        try:
            assert not orch2._kuzu_degraded, (
                "boot reconciliation should succeed (non-empty brain.db → rebuild succeeds)"
            )
            assert not _sentinel_path(tmp_path).exists(), (
                "sentinel must be cleared after successful boot reconciliation"
            )
        finally:
            orch2._brain_db._conn.close()
            orch2._faces_conn.close()
    except Exception:
        # Ensure connection cleanup if an unexpected exception leaks.
        try:
            orch._brain_db._conn.close()
        except Exception:
            pass
        try:
            orch._faces_conn.close()
        except Exception:
            pass
        raise
