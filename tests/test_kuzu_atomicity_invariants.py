"""
P0.X structural invariants — ordering-enforcing, DLL-safe, PR-blocking.

Each Kuzu-writing method in BrainOrchestrator must follow one of three
P0.X-approved patterns:

  SCHEMA_MIGRATION (boot path, _ensure_graph_sync):
    sentinel written BEFORE destructive Kuzu op
    SQL version bump committed BEFORE drop/rebuild
    rebuild failure → _kuzu_degraded = True (no raise from __init__)
    success → _clear_kuzu_dirty()

  RAISE (on_identity_confirmed):
    with self._brain_db.transaction():   # 1. SQL transaction — NO Kuzu inside
        ...
    # after SQL commit:
    self._mark_kuzu_dirty()              # 2. Eager sentinel BEFORE Kuzu op
    try:
        self._graph_db.<write>(...)
        self._clear_kuzu_dirty()
    except Exception:
        raise                            # RAISE: sentinel preserved for next-boot

  SWALLOW (_persist_extraction_to_kuzu, _retroactive_scan):
    try:
        self._graph_db.<write>(...)
    except Exception:
        self._mark_kuzu_dirty()          # sentinel for next-boot heal
        # (no raise — brain.db is authoritative, Kuzu is derived state)

  DEGRADED guard (_persist_extraction_to_kuzu only):
    if self._kuzu_degraded:
        return                           # no-op when graph is known-bad

Also checks:
  - `__init__` writes sentinel BEFORE GraphDB construction when schema upgrade pending.
  - Boot reconciliation in `_ensure_graph_sync` checks sentinel OR count mismatch.
  - All Kuzu-writing methods are in one of the covered sets (inverse check).

DLL-safe: AST scan; no pipeline import.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BRAIN_AGENT_PATH = REPO_ROOT / "core" / "brain_agent.py"


# Methods that follow the RAISE pattern (sentinel + re-raise on failure).
RAISE_PATTERN_METHODS = (
    "on_identity_confirmed",
)

# Methods that follow the SWALLOW pattern (sentinel + swallow on failure).
# _process_turn: covers the ContradictionAgent invalidate_fact site; brain.db is
# authoritative and the Kuzu graph heals on next _ensure_graph_sync().
SWALLOW_PATTERN_METHODS = (
    "_persist_extraction_to_kuzu",
    "_retroactive_scan",
    "_process_turn",
)

# Methods excluded from the inverse scan.
# These are internal helpers or the boot reconciliation method itself.
_INVERSE_SCAN_EXCLUDE = frozenset({
    "_ensure_graph_sync",    # boot reconciliation — IS the reconciliation method
    "_kuzu_sentinel_path",   # sentinel path helper — no Kuzu write ops
    "_mark_kuzu_dirty",      # sentinel write helper — no Kuzu write ops
    "_clear_kuzu_dirty",     # sentinel clear helper — no Kuzu write ops
    "__init__",              # constructor — has its own pre-construction sentinel logic
})

# Kuzu write operation markers used in the inverse scan.
_KUZU_WRITE_MARKERS = (
    "self._graph_db.upsert_entity(",
    "self._graph_db.rebuild_entity_from_knowledge(",
    "self._graph_db.invalidate_fact(",
    "self._graph_db.rebuild(",
    "self._graph_db.drop_schema(",
    "self._graph_db._init_schema(",
)


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
    """Return the minimum lineno of any ast.Call whose unparse contains call_fragment.

    Robust against docstring false-positives: operates on Call AST nodes, not raw text.
    """
    linenos = []
    for node in ast.walk(method_node):
        if isinstance(node, ast.Call) and call_fragment in ast.unparse(node):
            ln = getattr(node, "lineno", None)
            if ln is not None:
                linenos.append(ln)
    return min(linenos) if linenos else None


def _first_if_test_lineno(method_node, identifier: str) -> "int | None":
    """Return the minimum lineno of any ast.If whose test references identifier.

    Robust against docstring/string-literal false-positives: operates on
    ast.If test expressions, not raw text.
    """
    linenos = []
    for node in ast.walk(method_node):
        if isinstance(node, ast.If) and identifier in ast.unparse(node.test):
            ln = getattr(node, "lineno", None)
            if ln is not None:
                linenos.append(ln)
    return min(linenos) if linenos else None


# ── sentinel helpers structural check ────────────────────────────────────────

def test_sentinel_helpers_defined_on_brain_orchestrator():
    """BrainOrchestrator must define all three sentinel helper methods."""
    source = _read_source(BRAIN_AGENT_PATH)
    tree = ast.parse(source)
    for method_name in ("_kuzu_sentinel_path", "_mark_kuzu_dirty", "_clear_kuzu_dirty"):
        method = _find_method_in_class(tree, "BrainOrchestrator", method_name)
        assert method is not None, (
            f"BrainOrchestrator.{method_name} not found — "
            "P0.X sentinel helpers must be defined on the class"
        )


def test_kuzu_degraded_flag_initialized_in_init():
    """BrainOrchestrator.__init__ must initialize _kuzu_degraded to False."""
    source = _read_source(BRAIN_AGENT_PATH)
    tree = ast.parse(source)
    method = _find_method_in_class(tree, "BrainOrchestrator", "__init__")
    assert method is not None, "BrainOrchestrator.__init__ not found"
    src = ast.unparse(method)
    assert "_kuzu_degraded" in src, (
        "BrainOrchestrator.__init__ must initialize self._kuzu_degraded"
    )
    assert "_kuzu_degraded: bool = False" in source or "self._kuzu_degraded = False" in src, (
        "BrainOrchestrator.__init__ must set _kuzu_degraded = False "
        "(or annotated as bool = False)"
    )


# ── __init__ pre-construction sentinel discipline ─────────────────────────────

def test_init_writes_sentinel_before_graphdb_construction():
    """BrainOrchestrator.__init__ must write sentinel BEFORE GraphDB construction.

    GraphDB.__init__ calls _init_schema() which may fail during a schema upgrade.
    The sentinel must be written before GraphDB() so any failure leaves the sentinel
    in place for next-boot reconciliation.
    """
    source = _read_source(BRAIN_AGENT_PATH)
    tree = ast.parse(source)
    method = _find_method_in_class(tree, "BrainOrchestrator", "__init__")
    assert method is not None, "BrainOrchestrator.__init__ not found"

    src = ast.unparse(method)
    assert "graph_schema_version" in src, (
        "BrainOrchestrator.__init__ must read graph_schema_version from brain_state "
        "to detect pending schema upgrades"
    )
    assert "_mark_kuzu_dirty()" in src, (
        "BrainOrchestrator.__init__ must call _mark_kuzu_dirty() when schema upgrade pending"
    )

    # Ordering: _mark_kuzu_dirty call must appear BEFORE GraphDB construction.
    mark_dirty_line = _first_call_lineno(method, "_mark_kuzu_dirty()")
    graphdb_construct_line = _first_call_lineno(method, "GraphDB(")
    assert mark_dirty_line is not None, "_mark_kuzu_dirty() not found in __init__"
    assert graphdb_construct_line is not None, "GraphDB(...) construction not found in __init__"
    assert mark_dirty_line < graphdb_construct_line, (
        "P0.X ordering violation in __init__: "
        "_mark_kuzu_dirty() must appear BEFORE GraphDB(self._graph_db_path)"
    )


# ── _ensure_graph_sync boot reconciliation ───────────────────────────────────

def test_ensure_graph_sync_checks_sentinel_and_count_mismatch():
    """_ensure_graph_sync must check sentinel file AND entity-count mismatch."""
    source = _read_source(BRAIN_AGENT_PATH)
    tree = ast.parse(source)
    method = _find_method_in_class(tree, "BrainOrchestrator", "_ensure_graph_sync")
    assert method is not None, "BrainOrchestrator._ensure_graph_sync not found"
    src = ast.unparse(method)
    assert "_kuzu_sentinel_path().exists()" in src, (
        "_ensure_graph_sync must check sentinel file existence"
    )
    assert "entity_count()" in src, (
        "_ensure_graph_sync must check entity-count mismatch via entity_count()"
    )


def test_ensure_graph_sync_sets_degraded_on_rebuild_failure():
    """_ensure_graph_sync must set _kuzu_degraded = True when rebuild fails at boot."""
    source = _read_source(BRAIN_AGENT_PATH)
    tree = ast.parse(source)
    method = _find_method_in_class(tree, "BrainOrchestrator", "_ensure_graph_sync")
    assert method is not None, "BrainOrchestrator._ensure_graph_sync not found"

    # Must have an except block that sets _kuzu_degraded = True.
    for node in ast.walk(method):
        if isinstance(node, ast.ExceptHandler):
            handler_src = ast.unparse(node)
            if "_kuzu_degraded" in handler_src and "True" in handler_src:
                return  # found
    pytest.fail(
        "_ensure_graph_sync must set self._kuzu_degraded = True in its except block"
    )


def test_ensure_graph_sync_clears_sentinel_on_success():
    """_ensure_graph_sync must call _clear_kuzu_dirty() after successful rebuild."""
    source = _read_source(BRAIN_AGENT_PATH)
    tree = ast.parse(source)
    method = _find_method_in_class(tree, "BrainOrchestrator", "_ensure_graph_sync")
    assert method is not None, "BrainOrchestrator._ensure_graph_sync not found"
    src = ast.unparse(method)
    assert "_clear_kuzu_dirty()" in src, (
        "_ensure_graph_sync must call _clear_kuzu_dirty() after successful rebuild"
    )


def test_ensure_graph_sync_sql_commit_after_kuzu_rebuild():
    """P0.B3 D1 (Finding 2 board-meeting 2026-05-21 fix; in-place rewrite of the
    P0.X-era `test_ensure_graph_sync_sql_first_before_kuzu_ops` test which encoded
    the bug):

    update_graph_schema_version() MUST commit AFTER Kuzu rebuild + sentinel clear,
    NOT before drop_schema.

    Pre-P0.B3 (BUG):
        SQL version bump happened BEFORE drop_schema + rebuild. On crash mid-Kuzu,
        SQL=NEW + Kuzu=PARTIAL → next boot's migration predicate FALSE → permanent
        _kuzu_degraded=True with no operator-visible recovery signal. The original
        test encoded the BUG ordering as the invariant; D1 inverts both the test
        name and the assertion direction.

    Post-P0.B3 D1:
        SQL commit moves to AFTER _clear_kuzu_dirty(), gated on _did_schema_upgrade
        captured at function entry. Any crash before the SQL commit leaves
        stored_version=OLD → next boot re-enters migration via the predicate at
        function entry → retries idempotently. Behavioral coverage for crash points
        lives in tests/test_p0_b3_kuzu_schema_health.py (D1 anchors 2+3).
    """
    source = _read_source(BRAIN_AGENT_PATH)
    tree = ast.parse(source)
    method = _find_method_in_class(tree, "BrainOrchestrator", "_ensure_graph_sync")
    assert method is not None, "BrainOrchestrator._ensure_graph_sync not found"

    commit_line = _first_call_lineno(method, "update_graph_schema_version(")
    clear_dirty_line = _first_call_lineno(method, "_clear_kuzu_dirty(")
    rebuild_line = _first_call_lineno(method, "self._graph_db.rebuild(")

    assert commit_line is not None, "must call update_graph_schema_version()"
    assert clear_dirty_line is not None, "must call _clear_kuzu_dirty()"
    assert rebuild_line is not None, "must call rebuild()"

    assert commit_line > clear_dirty_line, (
        f"P0.B3 D1 ordering violation: update_graph_schema_version (line {commit_line}) "
        f"must appear AFTER _clear_kuzu_dirty (line {clear_dirty_line}). "
        "Pre-P0.B3 the order was reversed — Finding 2 bug."
    )
    assert commit_line > rebuild_line, (
        f"P0.B3 D1 ordering violation: update_graph_schema_version (line {commit_line}) "
        f"must appear AFTER rebuild (line {rebuild_line})."
    )


# ── on_identity_confirmed RAISE pattern ──────────────────────────────────────

def _check_raise_pattern(source: str, method_name: str) -> list[str]:
    """Check that a method follows the RAISE pattern for Kuzu writes."""
    tree = ast.parse(source)
    method = _find_method_in_class(tree, "BrainOrchestrator", method_name)
    if method is None:
        return [f"BrainOrchestrator.{method_name}: method not found"]

    src = ast.unparse(method)
    issues = []

    if "_mark_kuzu_dirty()" not in src:
        issues.append(f"{method_name}: missing _mark_kuzu_dirty() call before Kuzu op")
    if "_clear_kuzu_dirty()" not in src:
        issues.append(f"{method_name}: missing _clear_kuzu_dirty() call after success")

    # The Kuzu-writing except handler specifically must raise.
    # Walk Try nodes, find the one whose body contains a Kuzu write call,
    # and check THAT handler for ast.Raise — not just any handler in the method.
    _KUZU_RAISE_MARKERS = (
        "self._graph_db.rebuild_entity_from_knowledge(",
        "self._graph_db.upsert_entity(",
        "self._graph_db.invalidate_fact(",
        "self._graph_db.rebuild(",
    )
    kuzu_try_found = False
    kuzu_except_raises = False
    for node in ast.walk(method):
        if not isinstance(node, ast.Try):
            continue
        try_body_src = "\n".join(ast.unparse(s) for s in node.body)
        if not any(marker in try_body_src for marker in _KUZU_RAISE_MARKERS):
            continue
        kuzu_try_found = True
        for handler in node.handlers:
            for h_node in ast.walk(handler):
                if isinstance(h_node, ast.Raise):
                    kuzu_except_raises = True
                    break
    if not kuzu_try_found:
        issues.append(f"{method_name}: no try/except wrapping Kuzu write call found")
    elif not kuzu_except_raises:
        issues.append(
            f"{method_name}: Kuzu except handler must re-raise "
            "(RAISE pattern — sentinel preserved for next-boot)"
        )

    # SQL transaction must appear before sentinel/Kuzu op.
    tx_line = _first_call_lineno(method, "transaction()")
    sentinel_line = _first_call_lineno(method, "_mark_kuzu_dirty()")
    if tx_line is None:
        issues.append(f"{method_name}: missing brain.db transaction context manager")
    elif sentinel_line is not None and tx_line > sentinel_line:
        issues.append(
            f"{method_name}: SQL transaction must appear BEFORE sentinel write "
            "(SQL-first ordering violated)"
        )

    return issues


@pytest.mark.parametrize("method_name", RAISE_PATTERN_METHODS)
def test_raise_pattern_method_follows_p0x_pattern(method_name):
    """Each RAISE-pattern method must follow: SQL transaction → sentinel → Kuzu try → raise."""
    source = _read_source(BRAIN_AGENT_PATH)
    issues = _check_raise_pattern(source, method_name)
    assert not issues, (
        f"P0.X RAISE structural invariant violated:\n"
        + "\n".join(f"  - {i}" for i in issues)
        + "\n\nExpected pattern:\n"
        "    with self._brain_db.transaction():\n"
        "        # SQL ops — NO Kuzu calls\n"
        "    self._mark_kuzu_dirty()   # eager sentinel BEFORE Kuzu op\n"
        "    try:\n"
        "        self._graph_db.<write>(...)\n"
        "        self._clear_kuzu_dirty()\n"
        "    except Exception:\n"
        "        raise                 # sentinel preserved for next-boot"
    )


# ── _persist_extraction_to_kuzu SWALLOW pattern ──────────────────────────────

def test_persist_extraction_to_kuzu_has_degraded_guard():
    """_persist_extraction_to_kuzu must short-circuit when _kuzu_degraded is True."""
    source = _read_source(BRAIN_AGENT_PATH)
    tree = ast.parse(source)
    method = _find_method_in_class(
        tree, "BrainOrchestrator", "_persist_extraction_to_kuzu"
    )
    assert method is not None, (
        "BrainOrchestrator._persist_extraction_to_kuzu not found"
    )
    src = ast.unparse(method)
    assert "_kuzu_degraded" in src, (
        "_persist_extraction_to_kuzu must check self._kuzu_degraded at top"
    )
    # The early-return on _kuzu_degraded must appear before any Kuzu call.
    degraded_check_line = _first_if_test_lineno(method, "_kuzu_degraded")
    upsert_call_line = _first_call_lineno(method, "upsert_entity(")
    assert degraded_check_line is not None, "_kuzu_degraded if-check not found"
    assert upsert_call_line is not None, "upsert_entity() call not found"
    assert degraded_check_line < upsert_call_line, (
        "P0.X degraded guard must appear BEFORE upsert_entity() call"
    )


def test_persist_extraction_to_kuzu_swallow_pattern():
    """_persist_extraction_to_kuzu must write sentinel on failure but NOT raise."""
    source = _read_source(BRAIN_AGENT_PATH)
    tree = ast.parse(source)
    method = _find_method_in_class(
        tree, "BrainOrchestrator", "_persist_extraction_to_kuzu"
    )
    assert method is not None, (
        "BrainOrchestrator._persist_extraction_to_kuzu not found"
    )

    # Find the except handler and check it has _mark_kuzu_dirty but NOT raise.
    for node in ast.walk(method):
        if isinstance(node, ast.ExceptHandler):
            handler_src = ast.unparse(node)
            assert "_mark_kuzu_dirty()" in handler_src, (
                "_persist_extraction_to_kuzu: except handler must call _mark_kuzu_dirty()"
            )
            assert "raise" not in handler_src.split("_mark_kuzu_dirty")[0] + \
                   handler_src.split("_mark_kuzu_dirty")[-1], (
                "_persist_extraction_to_kuzu: SWALLOW pattern — must NOT re-raise"
            )
            return

    pytest.fail(
        "_persist_extraction_to_kuzu: no except handler found — "
        "Kuzu writes must be guarded with try/except"
    )


# ── _retroactive_scan SWALLOW pattern ────────────────────────────────────────

def test_retroactive_scan_kuzu_handler_writes_sentinel():
    """_retroactive_scan's Kuzu exception handler must call _mark_kuzu_dirty."""
    source = _read_source(BRAIN_AGENT_PATH)
    tree = ast.parse(source)
    method = _find_method_in_class(
        tree, "BrainOrchestrator", "_retroactive_scan"
    )
    assert method is not None, "BrainOrchestrator._retroactive_scan not found"

    # Find an except handler that covers the invalidate_fact call.
    for node in ast.walk(method):
        if not isinstance(node, ast.Try):
            continue
        try_src = ast.unparse(node)
        if "invalidate_fact(" not in try_src:
            continue
        # This is the try/except around the Kuzu write.
        for handler in node.handlers:
            handler_src = ast.unparse(handler)
            if "_mark_kuzu_dirty()" in handler_src:
                return  # found — correct

    pytest.fail(
        "_retroactive_scan: the except block guarding invalidate_fact() "
        "must call _mark_kuzu_dirty() (SWALLOW pattern)"
    )


def test_retroactive_scan_kuzu_handler_does_not_raise():
    """_retroactive_scan's Kuzu handler must SWALLOW (not re-raise)."""
    source = _read_source(BRAIN_AGENT_PATH)
    tree = ast.parse(source)
    method = _find_method_in_class(
        tree, "BrainOrchestrator", "_retroactive_scan"
    )
    assert method is not None, "BrainOrchestrator._retroactive_scan not found"

    for node in ast.walk(method):
        if not isinstance(node, ast.Try):
            continue
        try_src = ast.unparse(node)
        if "invalidate_fact(" not in try_src:
            continue
        for handler in node.handlers:
            if "_mark_kuzu_dirty()" in ast.unparse(handler):
                # This is the Kuzu sentinel handler — it must NOT raise.
                for h_node in ast.walk(handler):
                    if isinstance(h_node, ast.Raise):
                        pytest.fail(
                            "_retroactive_scan: SWALLOW pattern requires NO raise "
                            "in the invalidate_fact except handler"
                        )
                return  # no raise found — correct

    pytest.fail(
        "_retroactive_scan: except block guarding invalidate_fact() not found"
    )


# ── _process_turn SWALLOW pattern (ContradictionAgent invalidate_fact site) ──

def test_process_turn_kuzu_handler_writes_sentinel():
    """_process_turn's Kuzu exception handler must call _mark_kuzu_dirty."""
    source = _read_source(BRAIN_AGENT_PATH)
    tree = ast.parse(source)
    method = _find_method_in_class(
        tree, "BrainOrchestrator", "_process_turn"
    )
    assert method is not None, "BrainOrchestrator._process_turn not found"

    for node in ast.walk(method):
        if not isinstance(node, ast.Try):
            continue
        try_src = ast.unparse(node)
        if "invalidate_fact(" not in try_src:
            continue
        for handler in node.handlers:
            handler_src = ast.unparse(handler)
            if "_mark_kuzu_dirty()" in handler_src:
                return  # found — correct

    pytest.fail(
        "_process_turn: the except block guarding invalidate_fact() "
        "must call _mark_kuzu_dirty() (SWALLOW pattern)"
    )


def test_process_turn_kuzu_handler_does_not_raise():
    """_process_turn's Kuzu handler must SWALLOW (not re-raise)."""
    source = _read_source(BRAIN_AGENT_PATH)
    tree = ast.parse(source)
    method = _find_method_in_class(
        tree, "BrainOrchestrator", "_process_turn"
    )
    assert method is not None, "BrainOrchestrator._process_turn not found"

    for node in ast.walk(method):
        if not isinstance(node, ast.Try):
            continue
        try_src = ast.unparse(node)
        if "invalidate_fact(" not in try_src:
            continue
        for handler in node.handlers:
            if "_mark_kuzu_dirty()" in ast.unparse(handler):
                for h_node in ast.walk(handler):
                    if isinstance(h_node, ast.Raise):
                        pytest.fail(
                            "_process_turn: SWALLOW pattern requires NO raise "
                            "in the invalidate_fact except handler"
                        )
                return  # no raise found — correct

    pytest.fail(
        "_process_turn: except block guarding invalidate_fact() not found"
    )


# ── inverse check: all Kuzu-writing methods are covered ──────────────────────

def _find_kuzu_writing_methods(source: str) -> list[str]:
    """Return names of BrainOrchestrator methods that contain a Kuzu write call,
    excluding internal helpers and boot reconciliation listed in _INVERSE_SCAN_EXCLUDE."""
    tree = ast.parse(source)
    hits = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == "BrainOrchestrator"):
            continue
        for child in node.body:
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            name = child.name
            if name in _INVERSE_SCAN_EXCLUDE:
                continue
            src = ast.unparse(child)
            if any(marker in src for marker in _KUZU_WRITE_MARKERS):
                hits.append(name)
    return hits


_ALL_COVERED_METHODS = frozenset(RAISE_PATTERN_METHODS) | frozenset(SWALLOW_PATTERN_METHODS)


def test_all_kuzu_write_sites_are_covered():
    """Every BrainOrchestrator method that calls a Kuzu write op must be in a
    covered set (RAISE_PATTERN_METHODS or SWALLOW_PATTERN_METHODS).

    This is the inverse of the pattern tests: forward tests verify listed methods
    follow the pattern; this test verifies no Kuzu-writing method was silently
    omitted from the lists.

    Without this check, adding a new Kuzu-writing method without the P0.X sentinel
    pattern would slip through undetected.
    """
    source = _read_source(BRAIN_AGENT_PATH)
    kuzu_writers = _find_kuzu_writing_methods(source)
    unlisted = [m for m in kuzu_writers if m not in _ALL_COVERED_METHODS]
    assert not unlisted, (
        f"Kuzu-writing BrainOrchestrator methods not in any covered set:\n"
        + "\n".join(f"  - {m}" for m in unlisted)
        + "\n\nAdd them to RAISE_PATTERN_METHODS (if Kuzu failure must propagate) "
        "or SWALLOW_PATTERN_METHODS (if brain.db is authoritative and Kuzu can lag), "
        "OR add them to _INVERSE_SCAN_EXCLUDE with a comment explaining why they are exempt."
    )


# ── detector self-tests ───────────────────────────────────────────────────────

@pytest.mark.parametrize("synthetic_method, expect_issues", [
    # 1. Correct RAISE shape — no issues.
    ("""
class BrainOrchestrator:
    def on_identity_confirmed(self, person_id, old_name, new_name):
        kuzu_rows = None
        try:
            with self._brain_db.transaction():
                self._brain_db.migrate_entity_name(old_name, new_name, person_id)
                kuzu_rows = self._brain_db.get_knowledge_rows_for_kuzu(person_id, new_name)
        except Exception as e:
            raise
        if self._graph_db and kuzu_rows is not None:
            self._mark_kuzu_dirty()
            try:
                self._graph_db.rebuild_entity_from_knowledge(new_name, kuzu_rows)
                self._clear_kuzu_dirty()
            except Exception as e:
                raise
""", False),

    # 2. Missing _mark_kuzu_dirty — should fail.
    ("""
class BrainOrchestrator:
    def on_identity_confirmed(self, person_id, old_name, new_name):
        kuzu_rows = None
        try:
            with self._brain_db.transaction():
                self._brain_db.migrate_entity_name(old_name, new_name, person_id)
        except Exception as e:
            raise
        if self._graph_db and kuzu_rows is not None:
            try:
                self._graph_db.rebuild_entity_from_knowledge(new_name, kuzu_rows)
                self._clear_kuzu_dirty()
            except Exception as e:
                raise
""", True),

    # 3. No re-raise in Kuzu except — should fail.
    ("""
class BrainOrchestrator:
    def on_identity_confirmed(self, person_id, old_name, new_name):
        kuzu_rows = None
        try:
            with self._brain_db.transaction():
                pass
        except Exception as e:
            raise
        self._mark_kuzu_dirty()
        try:
            self._graph_db.rebuild_entity_from_knowledge(new_name, kuzu_rows)
            self._clear_kuzu_dirty()
        except Exception as e:
            pass  # wrong — should re-raise
""", True),

    # 4. Missing _clear_kuzu_dirty — should fail.
    ("""
class BrainOrchestrator:
    def on_identity_confirmed(self, person_id, old_name, new_name):
        kuzu_rows = None
        try:
            with self._brain_db.transaction():
                pass
        except Exception as e:
            raise
        self._mark_kuzu_dirty()
        try:
            self._graph_db.rebuild_entity_from_knowledge(new_name, kuzu_rows)
            # forgot _clear_kuzu_dirty()
        except Exception as e:
            raise
""", True),
])
def test_raise_pattern_detector_against_synthetic_methods(synthetic_method, expect_issues):
    """Detector must catch missing components in RAISE-pattern methods."""
    issues = _check_raise_pattern(synthetic_method, "on_identity_confirmed")
    has_issues = len(issues) > 0
    assert has_issues == expect_issues, (
        f"RAISE detector mismatch:\n{synthetic_method}\nissues={issues}"
    )


# ── Gap A: _ensure_graph_sync structural predicates ───────────────────────────

def test_ensure_graph_sync_calls_init_schema():
    """_ensure_graph_sync must call _graph_db._init_schema() during schema upgrade."""
    source = _read_source(BRAIN_AGENT_PATH)
    tree = ast.parse(source)
    method = _find_method_in_class(tree, "BrainOrchestrator", "_ensure_graph_sync")
    assert method is not None, "BrainOrchestrator._ensure_graph_sync not found"
    src = ast.unparse(method)
    assert "_init_schema()" in src, (
        "_ensure_graph_sync must call self._graph_db._init_schema() during schema upgrade"
    )


def test_ensure_graph_sync_calls_rebuild():
    """_ensure_graph_sync must call _graph_db.rebuild() for graph reconciliation."""
    source = _read_source(BRAIN_AGENT_PATH)
    tree = ast.parse(source)
    method = _find_method_in_class(tree, "BrainOrchestrator", "_ensure_graph_sync")
    assert method is not None, "BrainOrchestrator._ensure_graph_sync not found"
    src = ast.unparse(method)
    assert "_graph_db.rebuild(" in src, (
        "_ensure_graph_sync must call self._graph_db.rebuild() for graph reconciliation"
    )


def test_ensure_graph_sync_destructive_ops_inside_try_except():
    """drop_schema and _init_schema must be inside try/except with _kuzu_degraded handler."""
    source = _read_source(BRAIN_AGENT_PATH)
    tree = ast.parse(source)
    method = _find_method_in_class(tree, "BrainOrchestrator", "_ensure_graph_sync")
    assert method is not None, "BrainOrchestrator._ensure_graph_sync not found"
    _DESTRUCTIVE_MARKERS = ("self._graph_db.drop_schema(", "self._graph_db._init_schema(")
    for node in ast.walk(method):
        if not isinstance(node, ast.Try):
            continue
        try_body_src = "\n".join(ast.unparse(s) for s in node.body)
        if not any(marker in try_body_src for marker in _DESTRUCTIVE_MARKERS):
            continue
        for handler in node.handlers:
            handler_src = ast.unparse(handler)
            if "_kuzu_degraded" in handler_src and "True" in handler_src:
                return  # correct
        pytest.fail(
            "_ensure_graph_sync: drop_schema/_init_schema try/except handler "
            "must set self._kuzu_degraded = True"
        )
    pytest.fail(
        "_ensure_graph_sync: drop_schema() and _init_schema() must be inside "
        "a try/except block (auditor Gap A third predicate)"
    )


# ── Gap B: SWALLOW + SCHEMA_MIGRATION detector helpers + self-tests ───────────

def _check_swallow_pattern(source: str, method_name: str) -> list[str]:
    """Check that a method follows the SWALLOW pattern for Kuzu writes."""
    tree = ast.parse(source)
    method = _find_method_in_class(tree, "BrainOrchestrator", method_name)
    if method is None:
        return [f"BrainOrchestrator.{method_name}: method not found"]
    _KUZU_SWALLOW_MARKERS = (
        "self._graph_db.upsert_entity(",
        "self._graph_db.rebuild_entity_from_knowledge(",
        "self._graph_db.invalidate_fact(",
        "self._graph_db.rebuild(",
    )
    for node in ast.walk(method):
        if not isinstance(node, ast.Try):
            continue
        try_body_src = "\n".join(ast.unparse(s) for s in node.body)
        if not any(marker in try_body_src for marker in _KUZU_SWALLOW_MARKERS):
            continue
        issues = []
        sentinel_handler_found = False
        for handler in node.handlers:
            handler_src = ast.unparse(handler)
            if "_mark_kuzu_dirty()" not in handler_src:
                continue
            sentinel_handler_found = True
            for h_node in ast.walk(handler):
                if isinstance(h_node, ast.Raise):
                    issues.append(
                        f"{method_name}: SWALLOW pattern — must NOT re-raise"
                    )
        if not sentinel_handler_found:
            issues.append(
                f"{method_name}: Kuzu except handler must call _mark_kuzu_dirty()"
            )
        return issues
    return [f"{method_name}: no try/except wrapping a Kuzu write call found"]


def _check_schema_migration_pattern(source: str, method_name: str) -> list[str]:
    """Check that a method follows the SCHEMA_MIGRATION pattern."""
    tree = ast.parse(source)
    method = _find_method_in_class(tree, "BrainOrchestrator", method_name)
    if method is None:
        return [f"BrainOrchestrator.{method_name}: method not found"]
    src = ast.unparse(method)
    issues = []
    if "_init_schema()" not in src:
        issues.append(f"{method_name}: missing _graph_db._init_schema() call")
    if "rebuild(" not in src:
        issues.append(f"{method_name}: missing _graph_db.rebuild() call")
    _DESTRUCTIVE_MARKERS = ("drop_schema(", "_init_schema(")
    found_try_with_destructive = False
    found_degraded_handler = False
    for node in ast.walk(method):
        if not isinstance(node, ast.Try):
            continue
        try_body_src = "\n".join(ast.unparse(s) for s in node.body)
        if not any(marker in try_body_src for marker in _DESTRUCTIVE_MARKERS):
            continue
        found_try_with_destructive = True
        for handler in node.handlers:
            handler_src = ast.unparse(handler)
            if "_kuzu_degraded" in handler_src and "True" in handler_src:
                found_degraded_handler = True
    if not found_try_with_destructive:
        issues.append(
            f"{method_name}: drop_schema/_init_schema must be inside a try/except block"
        )
    elif not found_degraded_handler:
        issues.append(
            f"{method_name}: try/except handler must set _kuzu_degraded = True"
        )
    return issues


@pytest.mark.parametrize("synthetic_method, expect_issues", [
    # 1. Correct SWALLOW shape — no issues.
    ("""
class BrainOrchestrator:
    def _persist_extraction_to_kuzu(self, person_id, extractions):
        if self._kuzu_degraded:
            return
        try:
            self._graph_db.upsert_entity(person_id, extractions)
            self._clear_kuzu_dirty()
        except Exception as e:
            self._mark_kuzu_dirty()
            print(f"[BrainAgent] Kuzu error: {e}")
""", False),

    # 2. Missing _mark_kuzu_dirty — should fail.
    ("""
class BrainOrchestrator:
    def _persist_extraction_to_kuzu(self, person_id, extractions):
        if self._kuzu_degraded:
            return
        try:
            self._graph_db.upsert_entity(person_id, extractions)
        except Exception as e:
            print(f"[BrainAgent] Kuzu error: {e}")
""", True),

    # 3. Has re-raise in Kuzu except — should fail.
    ("""
class BrainOrchestrator:
    def _persist_extraction_to_kuzu(self, person_id, extractions):
        if self._kuzu_degraded:
            return
        try:
            self._graph_db.upsert_entity(person_id, extractions)
        except Exception as e:
            self._mark_kuzu_dirty()
            raise
""", True),
])
def test_swallow_pattern_detector_against_synthetic_methods(synthetic_method, expect_issues):
    """Detector must catch missing components in SWALLOW-pattern methods."""
    issues = _check_swallow_pattern(synthetic_method, "_persist_extraction_to_kuzu")
    has_issues = len(issues) > 0
    assert has_issues == expect_issues, (
        f"SWALLOW detector mismatch:\n{synthetic_method}\nissues={issues}"
    )


@pytest.mark.parametrize("synthetic_method, expect_issues", [
    # 1. Correct SCHEMA_MIGRATION shape — no issues.
    ("""
class BrainOrchestrator:
    def _ensure_graph_sync(self):
        self._brain_db.update_graph_schema_version(2)
        try:
            self._graph_db.drop_schema()
            self._graph_db._init_schema()
        except Exception as e:
            self._kuzu_degraded = True
            print(f"[BrainAgent] Schema migration failed: {e!r}")
        try:
            self._graph_db.rebuild(self._brain_db)
            self._clear_kuzu_dirty()
        except Exception as e:
            self._kuzu_degraded = True
""", False),

    # 2. Destructive ops NOT in try/except — should fail.
    ("""
class BrainOrchestrator:
    def _ensure_graph_sync(self):
        self._brain_db.update_graph_schema_version(2)
        self._graph_db.drop_schema()
        self._graph_db._init_schema()
        try:
            self._graph_db.rebuild(self._brain_db)
            self._clear_kuzu_dirty()
        except Exception as e:
            self._kuzu_degraded = True
""", True),

    # 3. try/except present but handler missing _kuzu_degraded = True — should fail.
    ("""
class BrainOrchestrator:
    def _ensure_graph_sync(self):
        self._brain_db.update_graph_schema_version(2)
        try:
            self._graph_db.drop_schema()
            self._graph_db._init_schema()
        except Exception as e:
            print(f"[BrainAgent] Schema migration failed: {e!r}")
        try:
            self._graph_db.rebuild(self._brain_db)
            self._clear_kuzu_dirty()
        except Exception as e:
            self._kuzu_degraded = True
""", True),
])
def test_schema_migration_pattern_detector_against_synthetic_methods(
    synthetic_method, expect_issues
):
    """Detector must catch missing components in SCHEMA_MIGRATION-pattern methods."""
    issues = _check_schema_migration_pattern(synthetic_method, "_ensure_graph_sync")
    has_issues = len(issues) > 0
    assert has_issues == expect_issues, (
        f"SCHEMA_MIGRATION detector mismatch:\n{synthetic_method}\nissues={issues}"
    )
