"""A2 anchor — AST invariant: no `time.time()` in DEADLINE-MATH contexts in production code.

Per Plan v2 §2 D2. Rejects `time.time()` calls inside:
- `ast.While` test expressions
- `ast.Compare` with subtraction patterns (`time.time() - X` followed by comparison)
- `ast.Assign` targets ending in `_deadline`
- `ast.Call` `time.time()` followed by binary `+` operation (e.g., `_deadline = time.time() + TIMEOUT`)
- (Canary #2) Direction-A VARIABLE-HOP: `now = time.time()` on one line, then `now - X`
  on another — patterns 1-4 require `time.time()` *directly* in the subtraction, so they
  all missed the vision-watchdog bug (pipeline.py:2594). Tracked scope-locally.

Allowlist via `# WALLCLOCK:` annotation (inline OR on previous 3 lines).

Self-tests: forward (synthetic violation fires) + inverse (annotated site passes).

Production scope (Q3 STANDARD RATIFIED): `pipeline.py` + `core/*.py` (excluding
`core/_minifasnet/`) + `bootstrap/classifier/*.py` + `tools/*.py`.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _collect_in_scope() -> list[Path]:
    files: list[Path] = [REPO_ROOT / "pipeline.py"]
    for p in sorted((REPO_ROOT / "core").rglob("*.py")):
        if "_minifasnet" not in p.parts:
            files.append(p)
    boot = REPO_ROOT / "bootstrap" / "classifier"
    if boot.exists():
        files.extend(sorted(boot.rglob("*.py")))
    files.extend(sorted(p for p in (REPO_ROOT / "tools").glob("*.py") if p.is_file()))
    return files


def _is_time_time_call(node: ast.AST) -> bool:
    """True if node is `time.time()` Call expression."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "time"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "time"
        and not node.args
        and not node.keywords
    )


def _is_time_time_subtraction(node: ast.AST) -> bool:
    """True if node is `time.time() - X` BinOp Sub."""
    return (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Sub)
        and _is_time_time_call(node.left)
    )


def _is_time_time_addition(node: ast.AST) -> bool:
    """True if node is `time.time() + X` BinOp Add."""
    return (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Add)
        and _is_time_time_call(node.left)
    )


def _iter_scope_local(scope: ast.AST):
    """Yield every descendant of `scope` in its OWN lexical scope, NOT descending
    into nested function / class / lambda scopes (so a name assigned in one function
    cannot match a subtraction in a sibling function)."""
    stack: list[ast.AST] = list(getattr(scope, "body", []) or [])
    _NESTED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
    while stack:
        node = stack.pop()
        yield node
        # Do NOT descend into a nested scope's body — it is processed as its own scope.
        # (Check on the popped node, because scope.body can seed nested defs directly.)
        if isinstance(node, _NESTED):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _find_variable_hop_violations(tree: ast.Module, is_allowlisted) -> list[tuple[int, str]]:
    """Direction-A variable-hop (Canary #2 / clock-consistency): a name assigned from a
    bare `time.time()` call, then used as the LEFT operand of a `-` subtraction. This is
    the `now = time.time(); elapsed = now - X` shape the original patterns (1)-(4) all
    miss — they require `time.time()` to appear *directly* in the subtraction. The vision
    watchdog bug (pipeline.py:2594) was exactly this shape and evaded all four patterns.

    Scoped per-function (+ module) so a wall-clock name in one function does not match a
    subtraction in another. Allowlisted if either the subtraction line OR the assignment
    line carries `# WALLCLOCK:`.
    """
    violations: list[tuple[int, str]] = []
    scopes: list[ast.AST] = [tree]
    scopes.extend(
        n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    for scope in scopes:
        local = list(_iter_scope_local(scope))
        wall_names: dict[str, int] = {}  # name -> lineno of its `= time.time()` assign
        for node in local:
            if isinstance(node, ast.Assign) and _is_time_time_call(node.value):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        wall_names[tgt.id] = node.value.lineno
            elif (
                isinstance(node, ast.AnnAssign)
                and node.value is not None
                and _is_time_time_call(node.value)
                and isinstance(node.target, ast.Name)
            ):
                wall_names[node.target.id] = node.value.lineno
        if not wall_names:
            continue
        for node in local:
            if (
                isinstance(node, ast.BinOp)
                and isinstance(node.op, ast.Sub)
                and isinstance(node.left, ast.Name)
                and node.left.id in wall_names
            ):
                ln = node.lineno
                if not is_allowlisted(ln) and not is_allowlisted(wall_names[node.left.id]):
                    violations.append((
                        ln,
                        f"`{node.left.id} = time.time()` then `{node.left.id} - X` "
                        "(variable-hop DEADLINE-MATH; use time.monotonic())",
                    ))
    return violations


def _find_violations(source: str) -> list[tuple[int, str]]:
    """Return list of (line_number, reason) for DEADLINE-MATH patterns lacking `# WALLCLOCK:` annotation."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    source_lines = source.splitlines()
    violations: list[tuple[int, str]] = []

    def is_allowlisted(line_num: int) -> bool:
        # Inline annotation on the target line OR within the 3 lines above.
        for j in range(max(0, line_num - 4), line_num):
            if 0 <= j < len(source_lines) and "# WALLCLOCK:" in source_lines[j]:
                return True
        return False

    for parent in ast.walk(tree):
        # (1) while time.time() ...
        if isinstance(parent, ast.While):
            for sub in ast.walk(parent.test):
                if _is_time_time_call(sub):
                    ln = sub.lineno
                    if not is_allowlisted(ln):
                        violations.append((ln, "While loop test uses time.time()"))
        # (2) Compare with time.time() - X
        if isinstance(parent, ast.Compare):
            operands = [parent.left] + list(parent.comparators)
            for op in operands:
                if _is_time_time_subtraction(op):
                    ln = op.left.lineno
                    if not is_allowlisted(ln):
                        violations.append((ln, "Compare with `time.time() - X` subtraction"))
                elif _is_time_time_call(op):
                    ln = op.lineno
                    if not is_allowlisted(ln):
                        violations.append((ln, "Compare operand is bare `time.time()`"))
        # (3) Assign to _deadline-suffixed target with time.time() in value
        if isinstance(parent, ast.Assign):
            for tgt in parent.targets:
                if isinstance(tgt, ast.Name) and tgt.id.endswith("_deadline"):
                    for sub in ast.walk(parent.value):
                        if _is_time_time_call(sub):
                            ln = sub.lineno
                            if not is_allowlisted(ln):
                                violations.append((ln, "_deadline assigned from `time.time()`"))
        # (4) BinOp time.time() + X (deadline computation)
        if _is_time_time_addition(parent):
            ln = parent.left.lineno
            if not is_allowlisted(ln):
                violations.append((ln, "`time.time() + X` (deadline computation)"))

    # NOTE: Direction-A variable-hop (pattern 5) is intentionally NOT folded into this
    # hard-gate function during the latency spec — it surfaces ~30 pre-existing sites that
    # the companion clock_consistency_audit_spec.md owns. The latency spec ships the
    # DETECTOR (`_find_variable_hop`) + self-tests + a non-gating discovery xfail; the
    # clock spec migrates/annotates every site then promotes variable-hop into THIS gate.
    # Dedupe (multiple parents may flag same line)
    return sorted(set(violations))


def _find_variable_hop(source: str) -> list[tuple[int, str]]:
    """Standalone runner for the Direction-A variable-hop detector (pattern 5).

    Kept separate from `_find_violations` so the latency spec can DISCOVER + DOCUMENT
    repo-wide without turning the hard gate red (clock spec owns the fixes)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    source_lines = source.splitlines()

    def is_allowlisted(line_num: int) -> bool:
        for j in range(max(0, line_num - 4), line_num):
            if 0 <= j < len(source_lines) and "# WALLCLOCK:" in source_lines[j]:
                return True
        return False

    return sorted(set(_find_variable_hop_violations(tree, is_allowlisted)))


@pytest.mark.parametrize(
    "path",
    _collect_in_scope(),
    ids=lambda p: p.relative_to(REPO_ROOT).as_posix(),
)
def test_a2_no_deadline_math_walltime(path: Path) -> None:
    """A2 — no `time.time()` in DEADLINE-MATH contexts in production code."""
    source = path.read_text(encoding="utf-8")
    violations = _find_violations(source)
    rel = path.relative_to(REPO_ROOT).as_posix()
    assert not violations, (
        f"{rel} has DEADLINE-MATH `time.time()` usage without `# WALLCLOCK:` annotation:\n"
        + "\n".join(f"  line {ln}: {reason}" for ln, reason in violations)
        + "\n\nFix: either migrate to `time.monotonic()` (preferred for DEADLINE-MATH) or "
        "add `# WALLCLOCK: <reason>` annotation if the site genuinely needs wallclock semantic."
    )


# --- Self-tests: forward (synthetic violation fires) + inverse (annotated passes) ---

def test_a2_self_test_forward_synthetic_violation_fires():
    """Forward self-test: synthetic violation must be detected by `_find_violations`."""
    src = textwrap.dedent("""
        import time
        def watchdog():
            _deadline = time.time() + 30
            while time.time() < _deadline:
                pass
            if time.time() - last > 5:
                print('elapsed')
    """)
    violations = _find_violations(src)
    assert len(violations) >= 3, (
        f"forward self-test failed: expected >=3 violations on synthetic, got {len(violations)}: {violations}"
    )


def test_a2_self_test_inverse_annotated_passes():
    """Inverse self-test: annotated site must NOT be flagged."""
    src = textwrap.dedent("""
        import time
        def check():
            # WALLCLOCK: cross-process IPC
            if time.time() - last > 5:
                print('elapsed')
    """)
    violations = _find_violations(src)
    assert not violations, (
        f"inverse self-test failed: annotated site should not be flagged, got {violations}"
    )


def test_a2_self_test_state_py_annotations_allowlist_cross_process_ipc():
    """state.py:62 + :108 must pass via `# WALLCLOCK: cross-process IPC` allowlist."""
    state_py = REPO_ROOT / "core" / "state.py"
    violations = _find_violations(state_py.read_text(encoding="utf-8"))
    assert not violations, (
        f"state.py cross-process IPC sites should be allowlisted via # WALLCLOCK: annotation: {violations}"
    )


# --- Direction-A variable-hop self-tests (Canary #2) ---

def test_a2_self_test_variable_hop_fires():
    """Forward: `now = time.time()` then `now - X` (the vision-watchdog shape) fires.

    This is the EXACT bug pattern that evaded patterns (1)-(4) — it must be caught now.
    """
    src = textwrap.dedent("""
        import time
        def watchdog():
            _now = time.time()
            _heartbeat = peek_heartbeat()
            _staleness = _now - _heartbeat
            if _staleness < 30.0:
                return
    """)
    violations = _find_variable_hop(src)
    assert any("variable-hop" in reason for _, reason in violations), (
        f"variable-hop forward self-test failed: expected a variable-hop violation, got {violations}"
    )


def test_a2_self_test_variable_hop_monotonic_passes():
    """Inverse: the fixed `now = time.monotonic()` shape must NOT fire."""
    src = textwrap.dedent("""
        import time
        def watchdog():
            _now = time.monotonic()
            _heartbeat = peek_heartbeat()
            _staleness = _now - _heartbeat
            if _staleness < 30.0:
                return
    """)
    violations = _find_variable_hop(src)
    assert not violations, (
        f"variable-hop monotonic inverse failed: monotonic now should be clean, got {violations}"
    )


def test_a2_self_test_variable_hop_annotated_passes():
    """Inverse: an annotated wall-clock variable-hop (legit display/IPC) must NOT fire."""
    src = textwrap.dedent("""
        import time
        def report():
            # WALLCLOCK: displayed age, not a cooldown gate
            _now = time.time()
            _age = _now - _created_at
            print(_age)
    """)
    violations = _find_variable_hop(src)
    assert not violations, (
        f"variable-hop annotated inverse failed: annotated site should pass, got {violations}"
    )


def test_a2_self_test_variable_hop_scoped_no_cross_function_false_positive():
    """A wall-clock name in one function must NOT match a subtraction in another."""
    src = textwrap.dedent("""
        import time
        def writer():
            _now = time.time()
            return _now
        def reader(_now):
            return _now - other  # different scope; _now here is a param, not time.time()
    """)
    violations = _find_variable_hop(src)
    assert not violations, (
        f"variable-hop scoping failed: cross-function name reuse should not flag, got {violations}"
    )


@pytest.mark.xfail(
    reason="Direction-A variable-hop clock debt discovered by latency-spec D1; "
    "migrated/annotated by clock_consistency_audit_spec.md, which then removes this "
    "xfail and promotes variable-hop into the hard gate (_find_violations).",
    strict=False,
)
def test_a2_variable_hop_repo_wide_discovery():
    """DISCOVER + DOCUMENT (latency spec §3 D1 item 3): run the strengthened
    variable-hop detector across the whole in-scope set. This is EXPECTED to xfail
    until the clock-consistency audit migrates each site to time.monotonic() or
    annotates the legitimate wall-clock ones. The vision-watchdog site (:2594) is
    already fixed and must NOT appear; every remaining site is the clock spec's surface.
    """
    findings: list[str] = []
    for path in _collect_in_scope():
        rel = path.relative_to(REPO_ROOT).as_posix()
        for ln, reason in _find_variable_hop(path.read_text(encoding="utf-8")):
            findings.append(f"  {rel}:{ln}  {reason}")
    # Surface the count + sites for the clock spec's hand-off (printed on xfail).
    print(f"\n[variable-hop discovery] {len(findings)} site(s) for clock_consistency_audit_spec.md:")
    print("\n".join(findings))
    assert not findings, (
        f"{len(findings)} Direction-A variable-hop site(s) remain — owned by "
        "clock_consistency_audit_spec.md (expected xfail in the latency spec)."
    )
