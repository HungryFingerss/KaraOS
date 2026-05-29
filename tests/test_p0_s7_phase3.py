"""tests/test_p0_s7_phase3.py — P0.S7 Phase 3 (AST structural invariants).

Plan v2 §8 Phase 3 = 3 AST source-inspection tests (15-17):

  15. test_log_turn_callers_use_compute_room_audience_helper
      — every db.log_turn(...) call in pipeline.py passes audience_ids
        as a variable assigned from _compute_room_audience(...), NOT a
        literal [<single_pid>] list (MEDIUM 3 enforcement)

  16. test_shared_context_block_disputed_guard_present
      — within _build_shared_context_block body, is_disputed_fn(...)
        Call appears at a strictly LOWER line number than any
        db.get_recent_room_conversation(...) Call (T-A — disputed
        gate fires BEFORE DB read)

  17. test_facedb_get_recent_room_conversation_signature
      — FaceDB.get_recent_room_conversation has exactly Plan v2 §5
        signature (4 kwargs: room_session_id, requester_pid,
        best_friend_id, limit). `since_ts` MUST NOT be present
        (CRITICAL 2 regression guard).

Plan v2 §8.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import pathlib

import pytest

# P0.S7 D2 — module-level privacy_critical marker; all tests are AST
# structural invariants for the SHARED CONTEXT consumer + disputed gates.
pytestmark = pytest.mark.privacy_critical


_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PIPELINE_PY = _REPO_ROOT / "pipeline.py"
_DB_PY = _REPO_ROOT / "core" / "db.py"


# ────────────────────────────────────────────────────────────────────────────
# 15. log_turn callers use _compute_room_audience helper
# ────────────────────────────────────────────────────────────────────────────


def test_log_turn_callers_use_compute_room_audience_helper() -> None:
    """Plan v2 §4.1 / MEDIUM 3 — every production `db.log_turn(...)` call in
    pipeline.py must pass `audience_ids` as a variable whose nearest preceding
    assignment is `_compute_room_audience(...)`, NOT a literal
    `[<single_pid>]` list. Catches refactors that revert any of the 5 sites
    back to the single-speaker shape.
    """
    src = _PIPELINE_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)

    # Annotate parents so each Call can walk up to its enclosing function.
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child._parent = node  # type: ignore[attr-defined]

    def _enclosing_function(call: ast.Call):
        cur: ast.AST = call
        while cur is not None and not isinstance(
            cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)
        ):
            cur = getattr(cur, "_parent", None)
        return cur

    def _is_db_log_turn(call: ast.Call) -> bool:
        f = call.func
        return (
            isinstance(f, ast.Attribute)
            and f.attr == "log_turn"
            and isinstance(f.value, ast.Name)
            and f.value.id == "db"
        )

    log_turn_calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_db_log_turn(node):
            log_turn_calls.append(node)

    # Plan v2 §4.1 grep-verified exactly 5 sites — anchor the count so a
    # NEW log_turn caller doesn't slip through without explicit audit.
    assert len(log_turn_calls) == 5, (
        f"Plan v2 §4.1: expected exactly 5 db.log_turn(...) call sites in "
        f"pipeline.py (grep-verified at lines 3205/3208/5103/5996/5998). "
        f"Found {len(log_turn_calls)}. New caller? Update §4.1 + Plan v2 "
        f"§8 test 15 + the producer-side audience_ids upgrade pattern."
    )

    violations: list[str] = []
    for call in log_turn_calls:
        # Find audience_ids kwarg.
        audience_kw = None
        for kw in call.keywords:
            if kw.arg == "audience_ids":
                audience_kw = kw
                break
        if audience_kw is None:
            violations.append(
                f"pipeline.py:{call.lineno} — db.log_turn(...) missing "
                f"audience_ids kwarg (Plan v2 §4.3 wiring)"
            )
            continue

        value = audience_kw.value
        # FORBIDDEN: literal [<single_pid>] list — proves the producer-side
        # upgrade reverted.
        if isinstance(value, ast.List):
            violations.append(
                f"pipeline.py:{call.lineno} — db.log_turn(audience_ids=<List "
                f"literal>): the producer-side upgrade requires a variable "
                f"assigned from _compute_room_audience(...), not a literal "
                f"list. Revert?"
            )
            continue

        # ACCEPTED: Name referencing a variable assigned from
        # _compute_room_audience(...) somewhere in the same function.
        if not isinstance(value, ast.Name):
            violations.append(
                f"pipeline.py:{call.lineno} — db.log_turn(audience_ids=...) "
                f"value is {type(value).__name__}, expected ast.Name "
                f"(variable assigned from _compute_room_audience)"
            )
            continue

        var_name = value.id
        fn = _enclosing_function(call)
        assert isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)), (
            f"Module-level log_turn at line {call.lineno} unsupported"
        )
        # Scan the enclosing function for an assignment
        #   <var_name> = _compute_room_audience(...)
        helper_assigns: list[int] = []
        for inner in ast.walk(fn):
            if isinstance(inner, ast.Assign):
                # Single-target assignment to our var?
                if (len(inner.targets) == 1
                        and isinstance(inner.targets[0], ast.Name)
                        and inner.targets[0].id == var_name
                        and isinstance(inner.value, ast.Call)):
                    callee = inner.value.func
                    if isinstance(callee, ast.Name) and callee.id == "_compute_room_audience":
                        if inner.lineno < call.lineno:
                            helper_assigns.append(inner.lineno)
        if not helper_assigns:
            violations.append(
                f"pipeline.py:{call.lineno} — db.log_turn(audience_ids="
                f"{var_name!r}) but no preceding assignment of "
                f"{var_name!r} = _compute_room_audience(...) found in "
                f"enclosing function '{fn.name}'. Hidden bypass of the "
                f"audience-computation helper."
            )

    assert violations == [], (
        "P0.S7 MEDIUM 3 violations — log_turn callers must route through "
        "_compute_room_audience(...):\n"
        + "\n".join(violations)
    )


# ────────────────────────────────────────────────────────────────────────────
# 16. T-A — disputed-guard placement (line-order in _build_shared_context_block)
# ────────────────────────────────────────────────────────────────────────────


def test_shared_context_block_disputed_guard_present() -> None:
    """Plan v2 §6 / T-A — within `build_shared_context_block`'s body,
    the `is_disputed_fn(requester_pid)` Call MUST appear at a strictly
    lower line number than any `db.get_recent_room_conversation(...)`
    Call. Proves the disputed-caller gate fires BEFORE the DB read.

    P0.S7.D-D: body moved from pipeline.py:_build_shared_context_block
    to core/room_orchestrator.py::RoomOrchestrator.build_shared_context_block.
    """
    _ROOM_ORCH_PY = _PIPELINE_PY.parent / "core" / "room_orchestrator.py"
    src = _ROOM_ORCH_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)

    fn_node: "ast.FunctionDef | ast.AsyncFunctionDef | None" = None
    for node in ast.walk(tree):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "build_shared_context_block"):
            fn_node = node
            break
    assert fn_node is not None, "build_shared_context_block missing"

    # Find earliest is_disputed_fn(...) Call line.
    disputed_lines: list[int] = []
    db_call_lines: list[int] = []
    for inner in ast.walk(fn_node):
        if not isinstance(inner, ast.Call):
            continue
        f = inner.func
        # is_disputed_fn(...)
        if isinstance(f, ast.Name) and f.id == "is_disputed_fn":
            disputed_lines.append(inner.lineno)
        # db.get_recent_room_conversation(...)
        if (isinstance(f, ast.Attribute)
                and f.attr == "get_recent_room_conversation"
                and isinstance(f.value, ast.Name)
                and f.value.id == "db"):
            db_call_lines.append(inner.lineno)

    assert disputed_lines, (
        "T-A: _build_shared_context_block must call is_disputed_fn(...) "
        "to skip disputed callers (gate 4)"
    )
    assert db_call_lines, (
        "_build_shared_context_block must call db.get_recent_room_"
        "conversation(...) — the consumer side of D-A"
    )
    earliest_disputed = min(disputed_lines)
    earliest_db = min(db_call_lines)
    assert earliest_disputed < earliest_db, (
        f"T-A violation: is_disputed_fn(...) at line {earliest_disputed} "
        f"must fire BEFORE db.get_recent_room_conversation(...) at line "
        f"{earliest_db}. Disputed callers must never consume persisted "
        f"room context."
    )


# ────────────────────────────────────────────────────────────────────────────
# 17. CRITICAL 2 regression guard — FaceDB.get_recent_room_conversation signature
# ────────────────────────────────────────────────────────────────────────────


def test_facedb_get_recent_room_conversation_signature() -> None:
    """Plan v2 §5 — `FaceDB.get_recent_room_conversation` has exactly the
    locked 4-param signature: (self, room_session_id, requester_pid,
    best_friend_id, limit=10). `since_ts` MUST NOT be present (CRITICAL 2
    regression guard — Plan v1 designed since_ts dedup which was a no-op;
    Plan v2 dropped it entirely)."""
    src = _DB_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)

    # Locate the FaceDB class.
    facedb_cls: "ast.ClassDef | None" = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "FaceDB":
            facedb_cls = node
            break
    assert facedb_cls is not None, "core/db.py must define class FaceDB"

    # Locate the method.
    method: "ast.FunctionDef | ast.AsyncFunctionDef | None" = None
    for item in facedb_cls.body:
        if (isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == "get_recent_room_conversation"):
            method = item
            break
    assert method is not None, (
        "core/db.py::FaceDB must define get_recent_room_conversation "
        "(Plan v2 §5)"
    )

    # Collect param names (positional + kwonly).
    param_names: list[str] = []
    for a in method.args.args:
        param_names.append(a.arg)
    for a in method.args.kwonlyargs:
        param_names.append(a.arg)

    # Strip 'self'.
    if param_names and param_names[0] == "self":
        param_names = param_names[1:]

    expected = ["room_session_id", "requester_pid", "best_friend_id", "limit"]
    assert param_names == expected, (
        f"Plan v2 §5: FaceDB.get_recent_room_conversation must have exactly "
        f"params {expected!r}. Found {param_names!r}."
    )

    # CRITICAL 2 — `since_ts` must NOT be present anywhere in the param list.
    assert "since_ts" not in param_names, (
        "CRITICAL 2 regression guard: `since_ts` parameter was dropped in "
        "Plan v2 §3 — the dedup design was a no-op. Restoring it requires "
        "explicit architect re-approval + revised dedup semantic."
    )
