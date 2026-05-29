"""
P0.13 — repeat-tool-guard cross-turn discipline.

Session 70 Bug Q: an unconditional pop of REPEAT_GUARD_FIELDS at the top of
conversation_turn defeated the cross-turn guard, allowing the LLM to repeat
update_system_name('Kara') across turns 11/15/17/19 without detection.

S70 fix: moved the resets inside _execute_tool's different-(name, args)
detection branch. This test guards the invariant structurally — using AST
analysis with parent-walk, not text proximity heuristics.

DOES NOT IMPORT pipeline. Reads pipeline.py as raw text and ast.parse()s it.
Constants imported from core.pipeline_invariants (zero side effects).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import ast
from pathlib import Path

import pytest

from core.pipeline_invariants import (
    REPEAT_GUARD_FIELDS,
    ALLOWED_REPEAT_GUARD_FUNCS,
)

# Resolve pipeline.py path relative to this test file. No pipeline import.
PIPELINE_PATH = Path(__file__).resolve().parent.parent / "pipeline.py"


# ── AST helpers ───────────────────────────────────────────────────────────────

def _annotate_parents(tree: ast.AST) -> None:
    """Add .parent pointer to every node. ast.parse() doesn't do this natively."""
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node  # type: ignore[attr-defined]


def _enclosing_function_name(node: ast.AST) -> str | None:
    """
    Innermost enclosing function name. Used for diagnostic messages so the
    developer reads "in <closure_name>" not "in <outer_function>".
    """
    parent = getattr(node, "parent", None)
    while parent is not None:
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return parent.name
        parent = getattr(parent, "parent", None)
    return None


def _is_inside_allowlisted_function(node: ast.AST, allowlist: frozenset[str]) -> bool:
    """
    Walk ALL ancestor functions checking for allowlist membership.

    Why not just check the nearest enclosing function: P1.A3 decomposes
    _execute_tool into named helpers, including potentially nested closures.
    A clear-the-guard pattern inside a closure inside _execute_tool would
    have its NEAREST function be the closure (not in allowlist) and trigger
    a false positive. Walking all ancestors fixes this.
    """
    parent = getattr(node, "parent", None)
    while parent is not None:
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if parent.name in allowlist:
                return True
        parent = getattr(parent, "parent", None)
    return False


def _is_inside_repeat_key_conditional(node: ast.AST) -> bool:
    """
    Walk upward looking for an enclosing `If` whose test references either
    REPEAT_GUARD_FIELDS or _repeat_key. If found, the mutation is inside a
    legitimate "different key fired, reset state" branch (S70-correct shape).

    NOTE (auditor N1): only ast.If is checked. ast.IfExp (ternary),
    ast.Match/ast.match_case (Python 3.10+ pattern matching), and ast.While
    (gated loops) are intentionally treated as violations until a deliberate
    spec update broadens the conditional set. If a future legitimate use of
    any of those guards a guard-field clear, this test will fail — by design.

    NOTE (auditor N3): the "_repeat_key" in test_src check uses substring
    matching. A future variable named e.g. _repeat_key_disabled would
    accidentally satisfy the legitimacy check. Realistic? No. Acceptable risk.
    """
    parent = getattr(node, "parent", None)
    while parent is not None:
        if isinstance(parent, ast.If):
            try:
                test_src = ast.unparse(parent.test)
            except Exception:
                test_src = ""
            if any(field in test_src for field in REPEAT_GUARD_FIELDS):
                return True
            if "_repeat_key" in test_src:
                return True
        parent = getattr(parent, "parent", None)
    return False


# ── violation detectors ───────────────────────────────────────────────────────

def _is_pop_of_guard_field(node: ast.AST) -> str | None:
    """X.pop("_tool_repeat_last", ...) → return field name; else None."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "pop"):
        return None
    if not node.args:
        return None
    arg0 = node.args[0]
    if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
        if arg0.value in REPEAT_GUARD_FIELDS:
            return arg0.value
    return None


def _is_del_of_guard_field(node: ast.AST) -> str | None:
    """del X["_tool_repeat_last"] → return field name; else None."""
    if not isinstance(node, ast.Delete):
        return None
    for target in node.targets:
        if isinstance(target, ast.Subscript):
            sl = target.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                if sl.value in REPEAT_GUARD_FIELDS:
                    return sl.value
    return None


def _is_assign_none_to_guard_field(node: ast.AST) -> str | None:
    """X["_tool_repeat_last"] = None → return field name; else None."""
    if not isinstance(node, ast.Assign):
        return None
    if not (isinstance(node.value, ast.Constant) and node.value.value is None):
        return None
    for target in node.targets:
        if isinstance(target, ast.Subscript):
            sl = target.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                if sl.value in REPEAT_GUARD_FIELDS:
                    return sl.value
    return None


def _is_update_with_guard_field(node: ast.AST) -> str | None:
    """X.update({"_tool_repeat_last": ...}) → return field name; else None."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "update"):
        return None
    if not node.args:
        return None
    arg0 = node.args[0]
    if not isinstance(arg0, ast.Dict):
        return None
    for key in arg0.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            if key.value in REPEAT_GUARD_FIELDS:
                return key.value
    return None


def _is_clear_on_session_target(node: ast.AST) -> bool:
    """
    X.clear() where X is a session-shaped name.

    NOTE (auditor N2): name-suffix heuristic only. Catches `_session.clear()`,
    `s_session.clear()`, `_active_sessions[pid].clear()`, etc. Does NOT
    catch `s = _active_sessions[pid]` followed by `s.clear()` two lines up
    (data-flow analysis would be required). Deliberate scope limit; the
    realistic bug shapes the detector self-tests cover all match the
    name-suffix heuristic. `startswith` check requires `_session_` (with
    trailing underscore) to avoid false-matching `_sessions_started` and
    similar set/counter variables whose names share the `_session` prefix
    but are not session dicts.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "clear"):
        return False
    target = func.value
    if isinstance(target, ast.Name):
        n = target.id
        return (n == "_session" or n.startswith("_session_")) or n.endswith("_session") or n == "session"
    if isinstance(target, ast.Subscript):
        if isinstance(target.value, ast.Name) and target.value.id == "_active_sessions":
            return True
    return False


# ── scanner ───────────────────────────────────────────────────────────────────

def _scan_source(source: str) -> list[str]:
    """
    Return list of human-readable violation strings.
    Empty list = no violations found.
    """
    tree = ast.parse(source)
    _annotate_parents(tree)

    failures: list[str] = []

    for node in ast.walk(tree):
        violation_field: str | None = None
        violation_kind: str = ""

        if (f := _is_pop_of_guard_field(node)) is not None:
            violation_field, violation_kind = f, "pop"
        elif (f := _is_del_of_guard_field(node)) is not None:
            violation_field, violation_kind = f, "del"
        elif (f := _is_assign_none_to_guard_field(node)) is not None:
            violation_field, violation_kind = f, "= None"
        elif (f := _is_update_with_guard_field(node)) is not None:
            violation_field, violation_kind = f, ".update({...})"
        elif _is_clear_on_session_target(node):
            violation_field, violation_kind = "(all)", ".clear()"
        else:
            continue

        # Allowlist: ANY ancestor function in the allowlist accepts the mutation.
        # Survives P1.A3 decomposition where _execute_tool may have nested helpers.
        if _is_inside_allowlisted_function(node, ALLOWED_REPEAT_GUARD_FUNCS):
            continue

        # AST parent-walk: inside If whose test mentions guard fields → legitimate.
        if _is_inside_repeat_key_conditional(node):
            continue

        line = getattr(node, "lineno", "?")
        innermost = _enclosing_function_name(node) or "<module>"
        failures.append(
            f"  - line {line} (in {innermost}): {violation_kind} on {violation_field}"
        )

    return failures


# ── the actual invariant test ─────────────────────────────────────────────────

def test_no_unconditional_repeat_guard_clears_in_pipeline():
    """
    Whole-file scan. Any clear of REPEAT_GUARD_FIELDS outside ANY ancestor
    in ALLOWED_REPEAT_GUARD_FUNCS AND outside an If conditional whose test
    mentions the guard fields = the S70 Bug Q regression.
    """
    source = PIPELINE_PATH.read_text(encoding="utf-8")
    failures = _scan_source(source)

    assert not failures, (
        "Repeat-guard fields cleared outside the safety boundary "
        f"(allowed in any ancestor of: {sorted(ALLOWED_REPEAT_GUARD_FUNCS)}):\n"
        + "\n".join(failures)
        + "\n\nReset the guard ONLY inside _execute_tool's "
        "different-(name, args) detection branch."
    )


# ── detector self-tests ───────────────────────────────────────────────────────

@pytest.mark.parametrize("violation_src", [
    # 1. Unconditional pop at top of conversation_turn (the S70 bug shape).
    """
async def conversation_turn(person_id):
    _active_sessions[person_id].pop("_tool_repeat_last", None)
""",
    # 2. del statement
    """
async def conversation_turn(person_id):
    del _active_sessions[person_id]["_tool_repeat_count"]
""",
    # 3. Assign None.
    """
async def conversation_turn(person_id):
    _active_sessions[person_id]["_tool_repeat_last"] = None
""",
    # 4. update() with guard field key.
    """
async def conversation_turn(person_id):
    _active_sessions[person_id].update({"_tool_repeat_last": None})
""",
    # 5. Wholesale .clear() on session.
    """
async def conversation_turn(person_id):
    _session = _active_sessions[person_id]
    _session.clear()
""",
    # 6. Inside an If, but the If test doesn't mention guard fields.
    """
async def conversation_turn(person_id):
    if some_unrelated_condition:
        _active_sessions[person_id].pop("_tool_repeat_last", None)
""",
    # 7. Inside a closure that's NOT inside any allowlisted ancestor.
    """
async def conversation_turn(person_id):
    def _reset_helper(session):
        session.pop("_tool_repeat_last", None)
    _reset_helper(_active_sessions[person_id])
""",
])
def test_detector_catches_all_violation_shapes(violation_src):
    """Each synthetic violation MUST trigger at least one detector."""
    failures = _scan_source(violation_src)
    assert len(failures) >= 1, (
        f"Detector missed a violation shape:\n{violation_src}"
    )


@pytest.mark.parametrize("legitimate_src", [
    # 1. Conditional reset inside _execute_tool — the S70-correct pattern.
    """
async def _execute_tool(name, args, ctx):
    _session = ctx.session
    _repeat_key = (name, args)
    if _session.get("_tool_repeat_last") != _repeat_key:
        _session.pop("_tool_repeat_last", None)
        _session.pop("_tool_repeat_count", None)
""",
    # 2. Conditional reset in another function, gated on the field itself.
    """
def some_helper(session):
    if session.get("_tool_repeat_last") is not None:
        session.pop("_tool_repeat_last", None)
""",
    # 3. Set inside _execute_tool — write, not clear.
    """
async def _execute_tool(name, args, ctx):
    ctx.session["_tool_repeat_last"] = (name, args)
""",
    # 4. Clear inside a closure inside _execute_tool (P1.A3 decomposition shape).
    #    The upward-walk allowlist check accepts this because _execute_tool is
    #    an ANCESTOR. A nearest-only check would false-positive here.
    """
async def _execute_tool(name, args, ctx):
    def _check_repeat_guard(session, repeat_key):
        if session.get("_tool_repeat_last") != repeat_key:
            session.pop("_tool_repeat_last", None)
    _check_repeat_guard(ctx.session, (name, args))
""",
])
def test_detector_allows_legitimate_patterns(legitimate_src):
    """Each synthetic legitimate pattern MUST NOT trigger a false positive."""
    failures = _scan_source(legitimate_src)
    assert failures == [], (
        f"False positive on legitimate pattern:\n{legitimate_src}\n"
        f"Failures: {failures}"
    )
