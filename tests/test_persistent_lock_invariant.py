"""Bundle 4 D5 — AST invariant: every _persistent access in core/state.py is either
(a) module-level declaration OR (b) under `with _persistent_lock:` block.

File-scoped to core/state.py production. Test files unrestricted per Q3 RATIFIED.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import ast
import pathlib


STATE_PATH = pathlib.Path(__file__).parent.parent / "core" / "state.py"


def _build_parent_map(tree: ast.Module) -> "dict[int, ast.AST]":
    """Map id(child_node) -> parent_node for the whole tree."""
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents


def _is_inside_persistent_lock_with(node: ast.AST, parents: "dict[int, ast.AST]") -> bool:
    """Return True iff node is enclosed in `with _persistent_lock:` block."""
    cur: ast.AST | None = parents.get(id(node))
    while cur is not None:
        if isinstance(cur, ast.With):
            for item in cur.items:
                ctx = item.context_expr
                if isinstance(ctx, ast.Name) and ctx.id == "_persistent_lock":
                    return True
        cur = parents.get(id(cur))
    return False


def _is_module_level_statement(node: ast.AST, tree: ast.Module, parents: "dict[int, ast.AST]") -> bool:
    """Return True iff node sits at module-level (not inside any FunctionDef / ClassDef / Lambda)."""
    cur: ast.AST | None = node
    while cur is not None:
        parent = parents.get(id(cur))
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            return False
        if parent is tree:
            return True
        cur = parent
    return False


def _is_inside_function_signature(node: ast.AST, parents: "dict[int, ast.AST]") -> bool:
    """Return True iff node sits in a FunctionDef args block (parameter default, annotation, etc.)."""
    cur: ast.AST | None = parents.get(id(node))
    while cur is not None:
        if isinstance(cur, ast.arguments):
            return True
        cur = parents.get(id(cur))
    return False


def test_all_persistent_loads_under_lock_or_module_level() -> None:
    """Every _persistent Name(Load) + DictUnpacking (**_persistent) spread must be
    either under `with _persistent_lock:` block OR a direct module-level statement.

    Note: `global _persistent` declarations are NOT ast.Name nodes — they're
    ast.Global with .names list; ast.walk doesn't visit those as Name. Safe.
    """
    source = STATE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    parents = _build_parent_map(tree)

    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        # Match `_persistent` Name nodes — both Load and Store
        if isinstance(node, ast.Name) and node.id == "_persistent":
            if _is_inside_function_signature(node, parents):
                continue
            if _is_inside_persistent_lock_with(node, parents):
                continue
            if _is_module_level_statement(node, tree, parents):
                continue
            ctx_kind = type(node.ctx).__name__
            violations.append((getattr(node, "lineno", -1), f"_persistent {ctx_kind}"))
        # Match `**_persistent` DictUnpacking spread (ast.keyword with arg=None,
        # value is ast.Name('_persistent'))
        if isinstance(node, ast.keyword) and node.arg is None:
            if isinstance(node.value, ast.Name) and node.value.id == "_persistent":
                if not _is_inside_persistent_lock_with(node, parents):
                    if not _is_module_level_statement(node, tree, parents):
                        violations.append(
                            (getattr(node, "lineno", -1), "_persistent SPREAD")
                        )

    assert not violations, (
        f"Bundle 4 D5 violations in core/state.py: {violations}. "
        "All _persistent access must be under `with _persistent_lock:` block "
        "OR module-level declaration."
    )


# --- Self-tests ---

def test_self_test_forward_unguarded_load_detection() -> None:
    """Self-test: synthetic unguarded _persistent Load fires the detector."""
    synthetic_source = """
import threading
_persistent = {}
_persistent_lock = threading.Lock()

def bad_read():
    return _persistent.get('foo')
"""
    tree = ast.parse(synthetic_source)
    parents = _build_parent_map(tree)
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "_persistent":
            if _is_inside_function_signature(node, parents):
                continue
            if _is_inside_persistent_lock_with(node, parents):
                continue
            if _is_module_level_statement(node, tree, parents):
                continue
            ctx_kind = type(node.ctx).__name__
            violations.append((getattr(node, "lineno", -1), f"_persistent {ctx_kind}"))
    assert violations, "Self-test forward: unguarded _persistent.get() should be flagged"


def test_self_test_inverse_under_lock_passes() -> None:
    """Self-test: synthetic _persistent under lock passes the detector."""
    synthetic_source = """
import threading
_persistent = {}
_persistent_lock = threading.Lock()

def good_read():
    with _persistent_lock:
        snap = dict(_persistent)
    return snap
"""
    tree = ast.parse(synthetic_source)
    parents = _build_parent_map(tree)
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "_persistent":
            if _is_inside_function_signature(node, parents):
                continue
            if _is_inside_persistent_lock_with(node, parents):
                continue
            if _is_module_level_statement(node, tree, parents):
                continue
            ctx_kind = type(node.ctx).__name__
            violations.append((getattr(node, "lineno", -1), f"_persistent {ctx_kind}"))
    assert not violations, f"Self-test inverse: under-lock access should be clean, got {violations}"
