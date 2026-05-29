"""A2 anchor — AST invariant: no `time.time()` in DEADLINE-MATH contexts in production code.

Per Plan v2 §2 D2. Rejects `time.time()` calls inside:
- `ast.While` test expressions
- `ast.Compare` with subtraction patterns (`time.time() - X` followed by comparison)
- `ast.Assign` targets ending in `_deadline`
- `ast.Call` `time.time()` followed by binary `+` operation (e.g., `_deadline = time.time() + TIMEOUT`)

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

    # Dedupe (multiple parents may flag same line)
    return sorted(set(violations))


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
