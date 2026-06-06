"""
P0.X slow-tier crash-injection tests — brain.db (SQLite) ↔ Kuzu cross-write divergence.

Architecture: brain.db = durable source of truth. Kuzu = rebuildable derived
property graph. Boot reconciliation closes divergence. Three write patterns:

  SCHEMA_MIGRATION: _ensure_graph_sync — eager sentinel, SQL-first, Kuzu after.
  RAISE:           on_identity_confirmed — sentinel + re-raise on any failure.
  SWALLOW:         _persist_extraction_to_kuzu / _retroactive_scan — sentinel + swallow.

Boot reconciliation: sentinel OR entity-count mismatch → Kuzu rebuild. If rebuild
fails at boot → _kuzu_degraded = True, sentinel preserved, no raise.

Pre-fix failure fingerprints:
  Tests 1-2: sentinel NOT written before Kuzu schema ops (eager write absent).
  Test 3:    sentinel NOT written; Kuzu mutated before SQL fails (Kuzu-first order).
  Test 4:    SQL exception swallowed by 'except Exception: return'.
  Test 5:    Kuzu exception swallowed, no sentinel, no re-raise.
  Tests 6,11: AttributeError — _persist_extraction_to_kuzu does not exist pre-fix.
  Test 7:    'except Exception: pass' with no sentinel in retroscan.
  Tests 8-9: boot reconciliation ignores sentinel / entity-count mismatch.
  Test 10:   no _kuzu_degraded attribute; __init__ raises on rebuild failure.

DLL-safe: imports core.brain_agent; no pipeline import.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import asyncio
import gc
import time
from pathlib import Path

import pytest

import core.brain_agent.orchestrator as brain_agent_mod  # SP-3: _ensure_graph_sync + GRAPH_SCHEMA_VERSION live here
from core.brain_agent import BrainOrchestrator, GraphDB


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_orch(tmp_path) -> BrainOrchestrator:
    return BrainOrchestrator(
        asyncio.Event(),
        brain_db_path=str(tmp_path / "brain.db"),
        graph_db_path=str(tmp_path / "brain_graph"),
        faces_db_path=str(tmp_path / "faces.db"),
    )


def _kuzu_sentinel(graph_db_path) -> Path:
    p = Path(graph_db_path)
    return p.parent / (p.name + ".dirty")


def _get_schema_version(brain_db) -> int:
    return brain_db._conn.execute(
        "SELECT graph_schema_version FROM brain_state WHERE singleton = 1"
    ).fetchone()[0]


def _count_graph_entities(graph_db) -> int:
    rows = graph_db._conn.execute("MATCH (e:Entity) RETURN count(e)").get_all()
    return rows[0][0] if rows else 0


def _seed_brain_db(brain_db, entity: str = "Alice", n: int = 5) -> None:
    """Insert n knowledge rows for entity — high confidence to pass EMBED_MIN_CONFIDENCE."""
    now = time.time()
    for i in range(n):
        brain_db._conn.execute(
            "INSERT INTO knowledge "
            "(source_turn_id, person_id, entity, entity_type, attribute, value, "
            "confidence, is_temporal, agent, created_at, privacy_level) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (i + 1, "pid_test", entity, "person", f"attr_{i}", f"value_{i}",
             0.9, 0, "test", now, "personal"),
        )
    brain_db._conn.commit()


class _BrainConnProxy:
    """Wraps sqlite3.Connection; raises for matching SQL to simulate crash."""
    def __init__(self, real, crash_pred):
        self._real = real
        self._crash_pred = crash_pred

    def execute(self, sql, *args, **kwargs):
        if isinstance(sql, str) and self._crash_pred(sql):
            raise RuntimeError("simulated SQL failure")
        return self._real.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _FakeExtraction:
    """Minimal stand-in for Extraction dataclass for _persist_extraction_to_kuzu calls."""
    def __init__(self, entity, attribute, value):
        self.entity = entity
        self.entity_type = "person"
        self.attribute = attribute
        self.value = value
        self.confidence = 0.9
        self.is_temporal = False
        self.agent = "test"
        self.privacy_level = "personal"
        self.source_turn_id = 1
        self.person_id = "pid_test"


def _close_orch(orch: BrainOrchestrator) -> None:
    """Best-effort close of brain_db and Kuzu connections."""
    try:
        orch.close_connections()
    except Exception:
        pass
    # Best-effort Kuzu close (connection and database)
    for attr in ("_conn", "_db"):
        obj = getattr(orch._graph_db, attr, None)
        if obj is not None:
            close_fn = getattr(obj, "close", None)
            if close_fn is not None:
                try:
                    close_fn()
                except Exception:
                    pass


# ── SCHEMA_MIGRATION pattern ──────────────────────────────────────────────────

@pytest.mark.slow
def test_schema_upgrade_drop_schema_failure_writes_sentinel(tmp_path, monkeypatch):
    """Kuzu drop_schema raises during upgrade — constructor completes in degraded mode,
    sentinel preserved.

    Pre-fix: constructor raised RuntimeError (stale test expectation).
    Post-fix (P0.X Round 2): constructor swallows, sets _kuzu_degraded=True, sentinel
    remains on disk so next boot's reconciliation can rebuild.
    """
    orch1 = _make_orch(tmp_path)
    current_version = _get_schema_version(orch1._brain_db)
    _close_orch(orch1)
    del orch1
    gc.collect()

    sentinel = _kuzu_sentinel(tmp_path / "brain_graph")

    monkeypatch.setattr(brain_agent_mod, "GRAPH_SCHEMA_VERSION", current_version + 1)
    monkeypatch.setattr(
        GraphDB, "drop_schema",
        lambda self: (_ for _ in ()).throw(
            RuntimeError("simulated drop_schema failure")
        ),
    )

    orch = _make_orch(tmp_path)
    try:
        assert orch._kuzu_degraded, (
            "constructor must complete in degraded mode when drop_schema crashes"
        )
        assert sentinel.exists(), (
            "P0.X: sentinel must be preserved when drop_schema crashes — "
            "boot reconciliation on next start depends on it"
        )
    finally:
        _close_orch(orch)


@pytest.mark.slow
def test_schema_upgrade_init_schema_failure_writes_sentinel(tmp_path, monkeypatch):
    """drop_schema succeeds, _init_schema raises — sentinel must persist through failure.

    Pre-fix: no sentinel before Kuzu ops → Kuzu schema partially rebuilt, no recovery marker.
    Post-fix: sentinel written BEFORE drop_schema → persists through _init_schema failure.
    """
    orch1 = _make_orch(tmp_path)
    current_version = _get_schema_version(orch1._brain_db)
    _close_orch(orch1)
    del orch1
    gc.collect()

    sentinel = _kuzu_sentinel(tmp_path / "brain_graph")

    monkeypatch.setattr(brain_agent_mod, "GRAPH_SCHEMA_VERSION", current_version + 1)
    monkeypatch.setattr(
        GraphDB, "_init_schema",
        lambda self: (_ for _ in ()).throw(
            RuntimeError("simulated _init_schema failure")
        ),
    )

    with pytest.raises(RuntimeError, match="simulated _init_schema failure"):
        _make_orch(tmp_path)

    assert sentinel.exists(), (
        "P0.X: sentinel not written before Kuzu schema ops"
    )


@pytest.mark.slow
def test_schema_upgrade_sql_commit_failure_leaves_version_old(tmp_path, monkeypatch):
    """SQL UPDATE brain_state fails post-Kuzu-rebuild — version unchanged; degraded mode set.

    P0.X-era pre-fix (Kuzu-first): drop+reinit ran before SQL fails → Kuzu mutated,
    SQL stale, no sentinel — silent divergence.

    P0.X-era post-fix (SQL-first): sentinel written eagerly; SQL UPDATE happened
    BEFORE drop_schema/rebuild — failure left Kuzu untouched + sentinel preserved
    + stored_version unchanged. This was the locked invariant from P0.X close.

    P0.B3 D1 (Finding 2 board-meeting 2026-05-21 fix): the SQL UPDATE moved AFTER
    rebuild + _clear_kuzu_dirty, gated on `_did_schema_upgrade`. Crash semantics
    change:
      - rebuild block's `except Exception` swallows the SQL UPDATE failure +
        sets `_kuzu_degraded=True` (no re-raise) → the old `pytest.raises`
        wrapper no longer applies.
      - `_clear_kuzu_dirty()` runs BEFORE the failing UPDATE → sentinel is
        cleared. Recovery on next boot is driven by the migration PREDICATE
        (stored_version < GRAPH_SCHEMA_VERSION), NOT the sentinel.

    What still holds (the core invariant): stored_version=OLD after the failed
    UPDATE → predicate at function entry on next boot returns TRUE → migration
    retries idempotently. This is the LOAD-BEARING property D1 protects.

    (Plan v1 §1.1 disposition for this test was "docstring update only" but
    the actual D1 semantics required broader adjustment — banked as P0.B3
    Phase 4 in-flight observation.)
    """
    orch1 = _make_orch(tmp_path)
    current_version = _get_schema_version(orch1._brain_db)

    monkeypatch.setattr(brain_agent_mod, "GRAPH_SCHEMA_VERSION", current_version + 1)
    orch1._brain_db._conn = _BrainConnProxy(
        orch1._brain_db._conn,
        lambda s: "UPDATE brain_state SET graph_schema_version" in s,
    )

    # Under P0.B3 D1, the SQL UPDATE failure is swallowed by the rebuild
    # block's `except Exception` clause + sets _kuzu_degraded=True. No
    # exception propagates to the caller. (Pre-D1 the same proxy would
    # have raised RuntimeError; the pytest.raises wrapper has been dropped
    # for the new ordering.)
    orch1._ensure_graph_sync()

    assert orch1._kuzu_degraded is True, (
        "P0.B3 D1: SQL UPDATE failure inside the rebuild try-block must set "
        "_kuzu_degraded=True (caught by rebuild-block except Exception)"
    )
    real_conn = orch1._brain_db._conn._real
    stored = real_conn.execute(
        "SELECT graph_schema_version FROM brain_state WHERE singleton = 1"
    ).fetchone()[0]
    assert stored == current_version, (
        f"P0.B3 D1 LOAD-BEARING INVARIANT: schema version advanced to {stored} "
        f"despite SQL UPDATE failure (expected {current_version}). The migration "
        f"predicate at function entry depends on stored_version<NEW for recovery."
    )


# ── RAISE pattern ─────────────────────────────────────────────────────────────

@pytest.mark.slow
def test_on_identity_confirmed_sql_failure_reraises(tmp_path, monkeypatch):
    """SQL transaction in on_identity_confirmed fails — exception must propagate.

    Pre-fix: 'except Exception: return' swallows the error silently.
    Post-fix: exception re-raised → caller is notified of the failure.
    """
    orch = _make_orch(tmp_path)
    monkeypatch.setattr(
        orch._brain_db, "migrate_entity_name",
        lambda *a, **kw: (_ for _ in ()).throw(
            RuntimeError("simulated migrate_entity_name failure")
        ),
    )

    with pytest.raises(RuntimeError, match="simulated migrate_entity_name failure"):
        orch.on_identity_confirmed(
            person_id="pid_test",
            old_name="OldName",
            new_name="NewName",
        )


@pytest.mark.slow
def test_on_identity_confirmed_kuzu_failure_writes_sentinel_and_reraises(
    tmp_path, monkeypatch
):
    """SQL succeeds; Kuzu graph rebuild fails — sentinel written + exception re-raised.

    Pre-fix: Kuzu exception swallowed (no sentinel, no re-raise) → divergence invisible.
    Post-fix: sentinel written before Kuzu op + exception re-raised.
    """
    orch = _make_orch(tmp_path)
    sentinel = _kuzu_sentinel(tmp_path / "brain_graph")

    monkeypatch.setattr(orch._brain_db, "migrate_entity_name", lambda *a, **kw: None)
    monkeypatch.setattr(
        orch._brain_db, "promote_shadow_to_confirmed", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        orch._brain_db,
        "update_visitor_alert_for_promoted_person",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        orch._brain_db,
        "get_knowledge_rows_for_kuzu",
        lambda *a, **kw: [{"entity": "NewName", "attribute": "test", "value": "v"}],
    )
    monkeypatch.setattr(
        orch._graph_db,
        "rebuild_entity_from_knowledge",
        lambda *a, **kw: (_ for _ in ()).throw(
            RuntimeError("simulated Kuzu rebuild failure")
        ),
    )

    with pytest.raises(RuntimeError, match="simulated Kuzu rebuild failure"):
        orch.on_identity_confirmed(
            person_id="pid_test",
            old_name="OldName",
            new_name="NewName",
        )

    assert sentinel.exists(), (
        "P0.X: sentinel not written before Kuzu rebuild in on_identity_confirmed"
    )


# ── SWALLOW pattern ───────────────────────────────────────────────────────────

@pytest.mark.slow
def test_persist_extraction_to_kuzu_failure_writes_sentinel(tmp_path, monkeypatch):
    """Kuzu write fails in _persist_extraction_to_kuzu — sentinel written, exception swallowed.

    Pre-fix: method does not exist → AttributeError on any call.
    Post-fix: Kuzu fails → sentinel written, no exception raised to caller.
    """
    orch = _make_orch(tmp_path)
    sentinel = _kuzu_sentinel(tmp_path / "brain_graph")

    monkeypatch.setattr(
        orch._graph_db,
        "upsert_entity",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("simulated upsert failure")),
    )

    facts = [_FakeExtraction("Alice", "age", "30")]
    # Pre-fix: AttributeError — method doesn't exist → test fails
    # Post-fix: Kuzu fails → sentinel written → no exception raised (swallow pattern)
    orch._persist_extraction_to_kuzu(facts, turn_id=1)

    assert sentinel.exists(), (
        "P0.X: sentinel not written on Kuzu failure in _persist_extraction_to_kuzu"
    )


@pytest.mark.slow
def test_retroactive_scan_kuzu_failure_writes_sentinel(tmp_path, monkeypatch):
    """Kuzu invalidate_fact fails during _retroactive_scan — sentinel written.

    Pre-fix: 'except Exception: pass' with no sentinel → FAISS-style silent divergence.
    Post-fix: _mark_kuzu_dirty() called in except block → sentinel exists after loop.
    """
    orch = _make_orch(tmp_path)
    _seed_brain_db(orch._brain_db, entity="Alice", n=3)
    sentinel = _kuzu_sentinel(tmp_path / "brain_graph")

    async def _mock_check_staleness(entity, attribute, value, changed_attr, old_val, new_val):
        return ("INVALIDATED", "test retroscan reason")

    monkeypatch.setattr(orch._contradictor, "check_staleness", _mock_check_staleness)
    monkeypatch.setattr(
        orch._graph_db,
        "invalidate_fact",
        lambda *a, **kw: (_ for _ in ()).throw(
            RuntimeError("simulated invalidate_fact failure")
        ),
    )

    asyncio.run(
        orch._retroactive_scan(
            entity="Alice",
            changed_attr="nonexistent_attr",
            old_value="old_val",
            new_value="new_val",
            turn_id=99,
        )
    )

    assert sentinel.exists(), (
        "P0.X: sentinel not written on Kuzu failure in _retroactive_scan invalidate site"
    )


# ── boot reconciliation ───────────────────────────────────────────────────────

@pytest.mark.slow
def test_sentinel_at_boot_triggers_rebuild(tmp_path, monkeypatch):
    """Sentinel present at boot — Kuzu rebuild must fire regardless of count match.

    Pre-fix: _ensure_graph_sync only checks is_empty(); sentinel is ignored.
    Post-fix: sentinel → rebuild always fires → sentinel cleared on success.
    """
    orch1 = _make_orch(tmp_path)
    _seed_brain_db(orch1._brain_db, entity="Alice", n=3)
    orch1._ensure_graph_sync()
    _close_orch(orch1)
    del orch1
    gc.collect()

    sentinel = _kuzu_sentinel(tmp_path / "brain_graph")
    sentinel.touch()

    rebuild_count = []
    original_rebuild = GraphDB.rebuild

    def tracking_rebuild(self, *args, **kwargs):
        rebuild_count.append(1)
        return original_rebuild(self, *args, **kwargs)

    monkeypatch.setattr(GraphDB, "rebuild", tracking_rebuild)

    _make_orch(tmp_path)

    assert len(rebuild_count) >= 1, (
        f"P0.X: sentinel at boot did not trigger rebuild — "
        f"expected >= 1, got {len(rebuild_count)}"
    )
    assert not sentinel.exists(), "P0.X: sentinel not cleared after successful rebuild"


@pytest.mark.slow
def test_count_mismatch_at_boot_triggers_rebuild(tmp_path, monkeypatch):
    """brain.db has more entities than Kuzu — count mismatch must trigger rebuild at boot.

    Pre-fix: only is_empty() check — Kuzu non-empty → no rebuild even with divergence.
    Post-fix: entity count compared; mismatch → rebuild fires.
    """
    orch1 = _make_orch(tmp_path)
    _seed_brain_db(orch1._brain_db, entity="Alice", n=3)
    orch1._ensure_graph_sync()

    # Add Bob directly to brain.db without Kuzu sync — creates entity count mismatch
    _seed_brain_db(orch1._brain_db, entity="Bob", n=2)
    _close_orch(orch1)
    del orch1
    gc.collect()

    rebuild_count = []
    original_rebuild = GraphDB.rebuild

    def tracking_rebuild(self, *args, **kwargs):
        rebuild_count.append(1)
        return original_rebuild(self, *args, **kwargs)

    monkeypatch.setattr(GraphDB, "rebuild", tracking_rebuild)

    _make_orch(tmp_path)

    assert len(rebuild_count) >= 1, (
        f"P0.X: count mismatch at boot did not trigger rebuild — "
        f"expected >= 1, got {len(rebuild_count)}"
    )


@pytest.mark.slow
def test_rebuild_failure_at_boot_sets_degraded_flag(tmp_path, monkeypatch):
    """Kuzu rebuild fails at boot — BrainOrchestrator must NOT raise.

    _kuzu_degraded = True; sentinel preserved for next-boot retry.
    Pre-fix: no _kuzu_degraded attr → AttributeError or unhandled exception during __init__.
    Post-fix: degraded mode — init completes, _kuzu_degraded = True, sentinel preserved.
    """
    orch1 = _make_orch(tmp_path)
    _seed_brain_db(orch1._brain_db, entity="Alice", n=3)
    orch1._ensure_graph_sync()
    _close_orch(orch1)
    del orch1
    gc.collect()

    sentinel = _kuzu_sentinel(tmp_path / "brain_graph")
    sentinel.touch()

    def crashing_rebuild(self, *args, **kwargs):
        raise RuntimeError("simulated Kuzu rebuild failure at boot")

    monkeypatch.setattr(GraphDB, "rebuild", crashing_rebuild)

    orch2 = _make_orch(tmp_path)  # MUST NOT raise

    assert orch2._kuzu_degraded is True, (
        "P0.X: _kuzu_degraded flag not set after boot rebuild failure"
    )
    assert sentinel.exists(), (
        "P0.X: sentinel cleared despite rebuild failure — "
        "must be preserved for next-boot retry"
    )


@pytest.mark.slow
def test_degraded_mode_kuzu_writes_are_noop(tmp_path, monkeypatch):
    """In degraded mode, _persist_extraction_to_kuzu skips all Kuzu writes.

    Pre-fix: _persist_extraction_to_kuzu does not exist → AttributeError.
    Post-fix: _kuzu_degraded=True → Kuzu writes suppressed → upsert_entity not called.
    """
    orch1 = _make_orch(tmp_path)
    _seed_brain_db(orch1._brain_db, entity="Alice", n=3)
    orch1._ensure_graph_sync()
    _close_orch(orch1)
    del orch1
    gc.collect()

    sentinel = _kuzu_sentinel(tmp_path / "brain_graph")
    sentinel.touch()

    def crashing_rebuild(self, *args, **kwargs):
        raise RuntimeError("simulated Kuzu rebuild failure at boot")

    monkeypatch.setattr(GraphDB, "rebuild", crashing_rebuild)

    orch2 = _make_orch(tmp_path)  # comes up degraded
    assert orch2._kuzu_degraded is True

    upsert_calls = []
    monkeypatch.setattr(
        orch2._graph_db,
        "upsert_entity",
        lambda *a, **kw: upsert_calls.append((a, kw)),
    )

    facts = [_FakeExtraction("Alice", "age", "30")]
    # Pre-fix: AttributeError — method doesn't exist → test fails
    # Post-fix: degraded mode → Kuzu writes suppressed → no upsert_entity call
    orch2._persist_extraction_to_kuzu(facts, turn_id=1)

    assert len(upsert_calls) == 0, (
        f"P0.X: Kuzu writes not suppressed in degraded mode — "
        f"got {len(upsert_calls)} upsert_entity call(s)"
    )
