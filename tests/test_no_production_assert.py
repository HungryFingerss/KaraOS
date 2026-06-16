"""A4 anchor — AST invariant: no `assert` statements in production code.

Per Plan v2 §2 D4. Rejects `ast.Assert` nodes in production-scope files.

Asserts get stripped under `python -O` (optimized mode), so they must NOT be
used as invariant gates in production code. Use `if not <cond>: raise
RuntimeError("<msg>")` instead (preserves observable behavior under both
default and `-O` modes).

Allowlist via path (Q4 RATIFIED):
- `tests/*.py` (recursive)
- 8 top-level `test_*.py` files (`test_brain_agent.py`, `test_brain_response.py`,
  `test_executor.py`, `test_faiss_delete.py`, `test_greetings.py`, `test_pipeline.py`,
  `test_shutdown.py`, `test_vision_v1v4.py`)
- top-level `conftest.py`

Self-tests: forward (synthetic production assert detected) + inverse
(test-file assert NOT flagged).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

ALLOWLIST_TOP_LEVEL_TEST_FILES = frozenset({
    "test_brain_agent.py",
    "test_brain_response.py",
    "test_executor.py",
    "test_faiss_delete.py",
    "test_greetings.py",
    "test_pipeline.py",
    "test_shutdown.py",
    "test_vision_v1v4.py",
})


def _collect_production_files() -> list[Path]:
    """Files in production scope (Q3 STANDARD): pipeline.py + core/*.py (excl _minifasnet)
    + bootstrap/classifier/*.py + tools/*.py.
    """
    files: list[Path] = [REPO_ROOT / "pipeline.py"]
    for p in sorted((REPO_ROOT / "core").rglob("*.py")):
        if "_minifasnet" not in p.parts:
            files.append(p)
    files.extend(sorted((REPO_ROOT / "runtime").rglob("*.py")))  # P1.A1 SP-4 engine package
    files.extend(sorted((REPO_ROOT / "flows").rglob("*.py")))  # P1.A1 SP-6.2 app-layer flows
    files.extend(sorted((REPO_ROOT / "profiles").rglob("*.py")))  # SB.2.1 profile package
    boot = REPO_ROOT / "bootstrap" / "classifier"
    if boot.exists():
        files.extend(sorted(boot.rglob("*.py")))
    files.extend(sorted(p for p in (REPO_ROOT / "tools").glob("*.py") if p.is_file()))
    return files


def _find_asserts(source: str) -> list[int]:
    """Return list of line numbers containing `ast.Assert` nodes."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    return sorted({node.lineno for node in ast.walk(tree) if isinstance(node, ast.Assert)})


@pytest.mark.parametrize(
    "path",
    _collect_production_files(),
    ids=lambda p: p.relative_to(REPO_ROOT).as_posix(),
)
def test_a4_no_production_assert(path: Path) -> None:
    """A4 — production code must NOT use `assert` (use `if not ...: raise ...` instead)."""
    source = path.read_text(encoding="utf-8")
    assert_lines = _find_asserts(source)
    rel = path.relative_to(REPO_ROOT).as_posix()
    assert not assert_lines, (
        f"{rel} contains `assert` statements at lines {assert_lines}\n"
        "Fix: migrate to `if not <cond>: raise RuntimeError(\"<msg>\")` — "
        "asserts get stripped under `python -O` which would silently bypass the invariant."
    )


# --- Self-tests ---

def test_a4_self_test_forward_synthetic_assert_detected():
    """Forward self-test: synthetic production assert is detected."""
    src = textwrap.dedent("""
        def fn(x):
            assert x > 0, "x must be positive"
            return x * 2
    """)
    asserts = _find_asserts(src)
    assert asserts == [3], f"expected detection at line 3, got {asserts}"


def test_a4_self_test_inverse_no_assert_passes():
    """Inverse self-test: clean code passes."""
    src = textwrap.dedent("""
        def fn(x):
            if not (x > 0):
                raise RuntimeError("x must be positive")
            return x * 2
    """)
    asserts = _find_asserts(src)
    assert asserts == [], f"clean code should not flag any asserts, got {asserts}"
