"""
P0.B3 — Kuzu schema migration ordering (D1) + Kuzu health observable (D2).

6 logical anchors:
  D1 (3): AST line-order ORDERING INVARIANT + 2 slow-tier crash-injection tests
          (drop_schema crash mid-migration, rebuild crash mid-data-population)
  D2 (3): HealthSnapshot.kuzu_degraded field shape + format_health_line
          conditional emit + format_health_alerts actionable recovery alert
          with substring lock (per Plan v1 §3.3) AND forbidden-doc-URL absence.

The 7th P0.B3 anchor is an IN-PLACE REWRITE at
`tests/test_kuzu_atomicity_invariants.py:240-260` (rename + invert assertion;
see Plan v1 §4.3). Plus `tests/test_kuzu_brain_atomicity.py:198-229` gets a
docstring update narrating the post-D1 ordering (per Plan v1 §1.1).

DLL-safe for D1 anchor 1 (AST scan; no pipeline import).
D1 anchors 2+3 are slow-tier behavioral (use real BrainOrchestrator + tmp_path).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import ast
import asyncio
import gc
import time
from dataclasses import fields
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import core.brain_agent as brain_agent_mod
from core.brain_agent import BrainOrchestrator, GraphDB

REPO_ROOT = Path(__file__).resolve().parent.parent
BRAIN_AGENT_PATH = REPO_ROOT / "core" / "brain_agent" / "__init__.py"


# ── Shared helpers (mirror tests/test_kuzu_atomicity_invariants.py shape) ─────

def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _find_method_in_class(tree, class_name: str, method_name: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if child.name == method_name:
                        return child
    return None


def _first_call_lineno(method_node, call_fragment: str) -> "int | None":
    """Min lineno of any ast.Call whose unparse contains call_fragment.

    Robust against docstring false-positives — operates on Call nodes only.
    """
    linenos = []
    for node in ast.walk(method_node):
        if isinstance(node, ast.Call) and call_fragment in ast.unparse(node):
            ln = getattr(node, "lineno", None)
            if ln is not None:
                linenos.append(ln)
    return min(linenos) if linenos else None


# ── Helpers for slow-tier D1 crash tests (mirror tests/test_kuzu_brain_atomicity.py) ─

def _make_orch(tmp_path) -> BrainOrchestrator:
    return BrainOrchestrator(
        asyncio.Event(),
        brain_db_path=str(tmp_path / "brain.db"),
        graph_db_path=str(tmp_path / "brain_graph"),
        faces_db_path=str(tmp_path / "faces.db"),
    )


def _close_orch(orch) -> None:
    try:
        orch._brain_db._conn.close()
    except Exception:
        pass
    try:
        orch._graph_db._conn.close()
    except Exception:
        pass


def _get_schema_version(brain_db) -> int:
    return brain_db._conn.execute(
        "SELECT graph_schema_version FROM brain_state WHERE singleton = 1"
    ).fetchone()[0]


def _kuzu_sentinel(graph_db_path) -> Path:
    p = Path(graph_db_path)
    return p.parent / (p.name + ".dirty")


# ────────────────────────────────────────────────────────────────────────────────
# D1 anchors (3) — _ensure_graph_sync ORDERING INVARIANT + crash recovery
# ────────────────────────────────────────────────────────────────────────────────


def test_d1_ensure_graph_sync_sql_commit_after_kuzu_rebuild():
    """P0.B3 D1 ORDERING INVARIANT (Finding 2 board-meeting 2026-05-21 fix):

    mark_kuzu_dirty → drop_schema → rebuild → _clear_kuzu_dirty → update_graph_schema_version

    Pre-fix: update_graph_schema_version() committed BEFORE drop_schema/rebuild.
    Any crash mid-Kuzu left SQL=NEW + Kuzu=PARTIAL → next boot migration
    predicate FALSE → permanent _kuzu_degraded trap.
    Post-fix: SQL commit is the LAST mutation; gated on `_did_schema_upgrade`
    so sentinel-only rebuild paths don't bump the version.
    """
    source = _read_source(BRAIN_AGENT_PATH)
    tree = ast.parse(source)
    method = _find_method_in_class(tree, "BrainOrchestrator", "_ensure_graph_sync")
    assert method is not None, "BrainOrchestrator._ensure_graph_sync not found"

    commit_line = _first_call_lineno(method, "update_graph_schema_version(")
    rebuild_line = _first_call_lineno(method, "self._graph_db.rebuild(")
    clear_dirty_line = _first_call_lineno(method, "_clear_kuzu_dirty(")
    drop_line = _first_call_lineno(method, "drop_schema(")
    mark_dirty_line = _first_call_lineno(method, "_mark_kuzu_dirty(")

    assert mark_dirty_line is not None, "must call _mark_kuzu_dirty()"
    assert drop_line is not None, "must call drop_schema()"
    assert rebuild_line is not None, "must call rebuild()"
    assert clear_dirty_line is not None, "must call _clear_kuzu_dirty()"
    assert commit_line is not None, "must call update_graph_schema_version()"

    assert mark_dirty_line < drop_line, (
        "P0.B3 D1: _mark_kuzu_dirty() must precede drop_schema() — sentinel "
        "SET before any destructive op (ORDERING INVARIANT step 2)"
    )
    assert drop_line < rebuild_line, (
        "P0.B3 D1: drop_schema() must precede rebuild() — schema upgrade "
        "completes before data repopulation (ORDERING INVARIANT step 3-5)"
    )
    assert rebuild_line < clear_dirty_line, (
        "P0.B3 D1: rebuild() must precede _clear_kuzu_dirty() — sentinel "
        "clears only after rebuild success (ORDERING INVARIANT step 6)"
    )
    assert clear_dirty_line < commit_line, (
        "P0.B3 D1 (Finding 2 board-meeting 2026-05-21 fix): "
        "update_graph_schema_version() MUST appear AFTER _clear_kuzu_dirty(). "
        "Pre-fix the SQL commit happened BEFORE Kuzu rebuild — crash-window left "
        "SQL=NEW + Kuzu=PARTIAL, trapping next boot in permanent _kuzu_degraded."
    )


@pytest.mark.slow
def test_d1_crash_mid_drop_schema_leaves_sql_version_old(tmp_path, monkeypatch):
    """P0.B3 D1: drop_schema raises → SQL version UNCHANGED → next boot retries.

    Pre-fix: SQL commit happened BEFORE drop_schema → stored_version=NEW on
    next boot → predicate FALSE → permanent _kuzu_degraded trap (no recovery).
    Post-fix: SQL commit moved AFTER rebuild + sentinel clear → drop_schema
    failure leaves stored_version=OLD → next boot predicate TRUE → retries.
    """
    orch1 = _make_orch(tmp_path)
    current_version = _get_schema_version(orch1._brain_db)
    _close_orch(orch1)
    del orch1
    gc.collect()

    monkeypatch.setattr(brain_agent_mod, "GRAPH_SCHEMA_VERSION", current_version + 1)
    monkeypatch.setattr(
        GraphDB, "drop_schema",
        lambda self: (_ for _ in ()).throw(RuntimeError("simulated drop_schema crash")),
    )

    orch2 = _make_orch(tmp_path)
    try:
        assert orch2._kuzu_degraded, (
            "constructor must complete in degraded mode after drop_schema crash"
        )
        stored = _get_schema_version(orch2._brain_db)
        assert stored == current_version, (
            f"P0.B3 D1: stored_version advanced to {stored} despite drop crash "
            f"(expected {current_version}). SQL commit must NOT happen pre-rebuild."
        )
    finally:
        _close_orch(orch2)
        del orch2
        gc.collect()

    # Recovery: revert the drop_schema patch, restart, verify stored_version advances cleanly.
    monkeypatch.undo()
    monkeypatch.setattr(brain_agent_mod, "GRAPH_SCHEMA_VERSION", current_version + 1)
    orch3 = _make_orch(tmp_path)
    try:
        assert not orch3._kuzu_degraded, "recovery boot should clear degraded state"
        stored2 = _get_schema_version(orch3._brain_db)
        assert stored2 == current_version + 1, (
            f"P0.B3 D1 recovery: stored_version should advance to {current_version + 1} "
            f"after clean retry; got {stored2}"
        )
    finally:
        _close_orch(orch3)


@pytest.mark.slow
def test_d1_crash_mid_rebuild_leaves_sql_version_old(tmp_path, monkeypatch):
    """P0.B3 D1: rebuild() raises → SQL version UNCHANGED → next boot retries.

    Same shape as test_d1_crash_mid_drop_schema but exercises a later crash
    point — after drop_schema + _init_schema succeed, rebuild() raises during
    data repopulation. Pre-fix this also left SQL=NEW on crash; post-fix the
    SQL commit lands AFTER _clear_kuzu_dirty, so this crash leaves SQL=OLD.
    """
    orch1 = _make_orch(tmp_path)
    # Seed one knowledge row so rebuild has work to do (the row is non-empty
    # → rebuild() runs the populate loop instead of short-circuiting).
    orch1._brain_db._conn.execute(
        "INSERT INTO knowledge "
        "(source_turn_id, person_id, entity, entity_type, attribute, value, "
        "confidence, is_temporal, agent, created_at, privacy_level) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (1, "pid_seed", "Alice", "person", "attr", "value",
         0.9, 0, "test", time.time(), "personal"),
    )
    orch1._brain_db._conn.commit()
    current_version = _get_schema_version(orch1._brain_db)
    _close_orch(orch1)
    del orch1
    gc.collect()

    monkeypatch.setattr(brain_agent_mod, "GRAPH_SCHEMA_VERSION", current_version + 1)
    monkeypatch.setattr(
        GraphDB, "rebuild",
        lambda self, rows: (_ for _ in ()).throw(RuntimeError("simulated rebuild crash")),
    )

    orch2 = _make_orch(tmp_path)
    try:
        assert orch2._kuzu_degraded, "must be in degraded mode after rebuild crash"
        stored = _get_schema_version(orch2._brain_db)
        assert stored == current_version, (
            f"P0.B3 D1: stored_version advanced to {stored} despite rebuild crash "
            f"(expected {current_version}). SQL commit must NOT happen pre-_clear_kuzu_dirty."
        )
    finally:
        _close_orch(orch2)
        del orch2
        gc.collect()

    # Recovery — same shape as D1 Anchor 2.
    monkeypatch.undo()
    monkeypatch.setattr(brain_agent_mod, "GRAPH_SCHEMA_VERSION", current_version + 1)
    orch3 = _make_orch(tmp_path)
    try:
        assert not orch3._kuzu_degraded, "recovery boot should clear degraded state"
        stored2 = _get_schema_version(orch3._brain_db)
        assert stored2 == current_version + 1, (
            f"P0.B3 D1 recovery: stored_version should advance to {current_version + 1} "
            f"after clean retry; got {stored2}"
        )
    finally:
        _close_orch(orch3)


# ────────────────────────────────────────────────────────────────────────────────
# D2 anchors (3) — HealthSnapshot.kuzu_degraded observability
# ────────────────────────────────────────────────────────────────────────────────


def _health_kwargs() -> dict:
    """Minimal base kwargs for HealthSnapshot construction in D2 tests."""
    return dict(
        timestamp=0.0,
        active_sessions=0,
        sessions_by_type={},
        persons_count=0,
        total_face_embeddings=0,
        knowledge_active_rows=0,
        shadow_persons_count=0,
        classifier_scenarios_active=0,
        classifier_scenarios_quarantined=0,
        cloud_state="ONLINE",
        active_disputes=0,
        unresolved_watchdog_alerts=0,
        last_dream_run_seconds_ago=None,
        thin_voice_galleries=[],
    )


def test_d2_health_snapshot_has_kuzu_degraded_field():
    """P0.B3 D2: HealthSnapshot.kuzu_degraded: bool = False (default not-degraded).

    Field MUST exist so the format_health_line conditional emit and
    format_health_alerts actionable recovery alert can consume it.
    """
    from core.health import HealthSnapshot

    field_names = {f.name for f in fields(HealthSnapshot)}
    assert "kuzu_degraded" in field_names, (
        "P0.B3 D2: HealthSnapshot.kuzu_degraded field missing"
    )

    snap = HealthSnapshot(**_health_kwargs())
    assert snap.kuzu_degraded is False, (
        "P0.B3 D2: default must be False (not-degraded) so health snapshot "
        "doesn't false-alarm during early-boot windows or unit tests"
    )


def test_d2_format_health_line_emits_kuzu_degraded_only_when_true():
    """P0.B3 D2: 'kuzu=degraded' appears in health line iff snap.kuzu_degraded.

    Mirrors the event_log_drops conditional-emit pattern — steady-state runs
    keep the health line clean; non-zero state tags the surface explicitly.
    """
    from core.health import HealthSnapshot, format_health_line

    line_clean = format_health_line(HealthSnapshot(**_health_kwargs(), kuzu_degraded=False))
    line_degraded = format_health_line(HealthSnapshot(**_health_kwargs(), kuzu_degraded=True))

    assert "kuzu=degraded" not in line_clean, (
        "P0.B3 D2: 'kuzu=degraded' must NOT appear when kuzu_degraded=False"
    )
    assert "kuzu=degraded" in line_degraded, (
        "P0.B3 D2: 'kuzu=degraded' MUST appear when kuzu_degraded=True"
    )


def test_d2_format_health_alerts_includes_recovery_procedure_when_degraded():
    """P0.B3 D2: format_health_alerts emits VERBATIM actionable recovery
    procedure when kuzu_degraded=True.

    Per Plan v1 §3.3 substring lock:
      MUST contain: 'Kuzu graph in degraded mode', 'Recovery: stop pipeline',
                    'rm -rf', 'restart', 'brain.db facts will rebuild'
      MUST NOT contain: any doc-URL form (http:// / see-the-wiki / consult-docs)

    The recovery procedure is HARDCODED inline so operators never have to
    grep logs or read source code.
    """
    from core.health import HealthSnapshot, format_health_alerts

    snap_clean = HealthSnapshot(**_health_kwargs(), kuzu_degraded=False)
    snap_degraded = HealthSnapshot(**_health_kwargs(), kuzu_degraded=True)

    mock_orch = MagicMock()
    mock_orch._brain_db._conn.execute.return_value.fetchall.return_value = []
    mock_orch._graph_db_path = "/fake/faces/brain_graph"

    alerts_clean = format_health_alerts(snap_clean, mock_orch)
    alerts_degraded = format_health_alerts(snap_degraded, mock_orch)

    # MUST be absent when not degraded
    for line in alerts_clean:
        assert "kuzu" not in line.lower(), (
            f"P0.B3 D2: no Kuzu alert when not degraded; found: {line!r}"
        )

    # MUST be present + actionable when degraded
    kuzu_alert = "\n".join(alerts_degraded)
    assert "Kuzu graph in degraded mode" in kuzu_alert, (
        "P0.B3 D2 §3.3 substring lock: 'Kuzu graph in degraded mode' missing"
    )
    assert "Recovery: stop pipeline" in kuzu_alert, (
        "P0.B3 D2 §3.3 substring lock: 'Recovery: stop pipeline' missing"
    )
    assert "rm -rf" in kuzu_alert, (
        "P0.B3 D2 §3.3 substring lock: 'rm -rf' command missing"
    )
    assert "restart" in kuzu_alert, (
        "P0.B3 D2 §3.3 substring lock: 'restart' missing"
    )
    assert "brain.db facts will rebuild" in kuzu_alert, (
        "P0.B3 D2 §3.3 substring lock: 'brain.db facts will rebuild' missing"
    )

    # MUST NOT contain doc-URL form (Q3 LOCK per Plan v1 §3.3 forbidden list)
    kuzu_alert_lower = kuzu_alert.lower()
    for forbidden in ("http://", "https://", "see the wiki", "consult docs", "consult the docs"):
        assert forbidden not in kuzu_alert_lower, (
            f"P0.B3 D2 §3.3 Q3 LOCK violation: alert contains '{forbidden}' — "
            "recovery procedure must be HARDCODED inline, not deferred to docs."
        )
