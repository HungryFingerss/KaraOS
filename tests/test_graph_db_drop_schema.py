"""
P0.4 Batch 5 — GraphDB.drop_schema() must propagate Kuzu errors (Bucket C fix).

Bug: drop_schema() swallowed exceptions from `DROP TABLE IF EXISTS`. Caller
_ensure_graph_sync() would then:
  1. call _init_schema() — a NO-OP because old tables still exist (IF NOT EXISTS)
  2. commit graph_schema_version = GRAPH_SCHEMA_VERSION to brain_state

Result: SQLite believes schema upgrade succeeded; Kuzu still has the old schema.
Writes using new-schema columns would silently fail or corrupt the graph.

Fix: removed the try/except so Kuzu errors propagate. _ensure_graph_sync() will
unwind before reaching UPDATE brain_state, leaving graph_schema_version unchanged
and preventing the schema mismatch.

Mock-based tests: DOES NOT IMPORT pipeline. Does not open real Kuzu or SQLite files.
Integration test (test_drop_schema_on_fresh_db_does_not_raise): opens a real Kuzu DB
in a tmp_path to validate that IF EXISTS is a genuine no-op on missing tables.
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.brain_agent import GraphDB


def test_drop_schema_propagates_kuzu_errors():
    """
    drop_schema() must not swallow Kuzu errors.

    A silent swallow lets _ensure_graph_sync() proceed to _init_schema()
    (a no-op on still-existing tables) and commit an updated
    graph_schema_version — leaving Kuzu on the old schema while SQLite
    believes the upgrade succeeded.
    """
    mock_conn = MagicMock()
    mock_conn.execute.side_effect = RuntimeError(
        "Kuzu: cannot drop table — active connection"
    )

    gdb = object.__new__(GraphDB)
    gdb._conn = mock_conn

    with pytest.raises(RuntimeError, match="Kuzu: cannot drop table"):
        gdb.drop_schema()


def test_drop_schema_executes_both_statements_in_order():
    """
    drop_schema() must attempt DROP RELATES_TO before DROP Entity.
    Rel tables must be dropped before their node tables (referential order).
    """
    executed: list[str] = []
    mock_conn = MagicMock()
    mock_conn.execute.side_effect = lambda stmt: executed.append(stmt)

    gdb = object.__new__(GraphDB)
    gdb._conn = mock_conn

    gdb.drop_schema()

    assert len(executed) == 2
    assert "RELATES_TO" in executed[0]
    assert "Entity" in executed[1]


def test_drop_schema_on_fresh_db_does_not_raise(tmp_path: Path):
    """
    Integration test: drop_schema() against a real Kuzu DB must never raise,
    whether the tables exist or not.

    The Bucket C fix removed all exception handling from drop_schema(), relying
    entirely on Kuzu's DROP TABLE IF EXISTS being a genuine no-op on missing
    tables.  This test validates that assumption:

      Phase 1 — tables exist (created by GraphDB.__init__ → _init_schema()):
        drop_schema() must succeed.

      Phase 2 — tables are now absent (dropped in Phase 1):
        drop_schema() must still succeed (IF EXISTS is a real no-op, not a lie).

    If Phase 2 raises, Kuzu's IF EXISTS does NOT suppress errors on missing
    tables and drop_schema() needs hardening to catch only the specific
    "table does not exist" exception class.
    """
    gdb = GraphDB(tmp_path / "fresh_brain_graph")  # creates DB + tables

    gdb.drop_schema()  # Phase 1: tables exist → must not raise

    gdb.drop_schema()  # Phase 2: tables absent → IF EXISTS must be genuine no-op
