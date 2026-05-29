"""Bundle 4 D3 — AST invariant: pipeline.py:_log_drain body has outer-loop try/except
that does NOT swallow silently. Catches the silent-death failure mode per Skeptic-1 BUG-3.

Single-function scope (NOT file-wide). Distinct from Bundle 3 D2/D4 STANDARD-scope.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import ast
import pathlib


PIPELINE_PATH = pathlib.Path(__file__).parent.parent / "pipeline.py"


def _find_log_drain_function(source: str) -> ast.FunctionDef:
    """Locate _log_drain FunctionDef in pipeline.py."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_log_drain":
            return node
    raise AssertionError("_log_drain function not found in pipeline.py")


def test_log_drain_has_outer_loop_try_except() -> None:
    """Outer-loop try/except wraps the while True body — catches _log_q.get() silent-death."""
    source = PIPELINE_PATH.read_text(encoding="utf-8")
    func = _find_log_drain_function(source)
    while_node = next(
        n for n in ast.walk(func) if isinstance(n, ast.While)
    )
    assert len(while_node.body) >= 1, "_log_drain while body is empty"
    first_stmt = while_node.body[0]
    assert isinstance(first_stmt, ast.Try), (
        f"_log_drain outer-loop body must start with try/except; got {type(first_stmt).__name__}"
    )
    assert len(first_stmt.handlers) >= 1, "_log_drain outer try has no except handlers"


def test_log_drain_except_handler_does_not_swallow() -> None:
    """Outer except handler body MUST NOT be just `pass` — must emit observability signal."""
    source = PIPELINE_PATH.read_text(encoding="utf-8")
    func = _find_log_drain_function(source)
    while_node = next(n for n in ast.walk(func) if isinstance(n, ast.While))
    outer_try = while_node.body[0]
    for handler in outer_try.handlers:
        non_pass_statements = [s for s in handler.body if not isinstance(s, ast.Pass)]
        assert len(non_pass_statements) >= 1, (
            "_log_drain outer except handler is pure pass — violates non-swallow contract"
        )


def test_log_drain_except_handler_emits_to_stderr() -> None:
    """Outer except handler MUST contain _sys.__stderr__ substring (stderr bypass)."""
    source = PIPELINE_PATH.read_text(encoding="utf-8")
    func = _find_log_drain_function(source)
    while_node = next(n for n in ast.walk(func) if isinstance(n, ast.While))
    outer_try = while_node.body[0]
    handler_source_chunks = []
    for handler in outer_try.handlers:
        handler_source_chunks.append(ast.unparse(handler))
    handler_source = " ".join(handler_source_chunks)
    assert "_sys.__stderr__" in handler_source or "sys.__stderr__" in handler_source, (
        "_log_drain outer except handler must emit to sys.__stderr__ "
        "(direct bypass; not via _Tee/_log_q infinite loop)"
    )


# --- Self-tests ---

def test_self_test_forward_pure_pass_detection() -> None:
    """Self-test: synthetic FunctionDef with except: pass body fails the non-swallow check."""
    synthetic_source = """
def _log_drain():
    while True:
        try:
            x = 1
        except Exception:
            pass
"""
    tree = ast.parse(synthetic_source)
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    while_node = next(n for n in ast.walk(func) if isinstance(n, ast.While))
    outer_try = while_node.body[0]
    for handler in outer_try.handlers:
        non_pass_statements = [s for s in handler.body if not isinstance(s, ast.Pass)]
        assert len(non_pass_statements) == 0


def test_self_test_inverse_correct_shape_passes() -> None:
    """Self-test: synthetic FunctionDef with proper non-swallow + stderr emit passes."""
    synthetic_source = """
def _log_drain():
    while True:
        try:
            x = 1
        except Exception as e:
            import sys as _sys
            _sys.__stderr__.write('error\\n')
"""
    tree = ast.parse(synthetic_source)
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    while_node = next(n for n in ast.walk(func) if isinstance(n, ast.While))
    outer_try = while_node.body[0]
    handler = outer_try.handlers[0]
    non_pass = [s for s in handler.body if not isinstance(s, ast.Pass)]
    assert len(non_pass) >= 1
    assert "_sys.__stderr__" in ast.unparse(handler)
