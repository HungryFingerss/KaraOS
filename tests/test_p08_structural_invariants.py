"""P0.8.2 — structural invariants for the timeout architecture.

F1 (handler-checkpoint discipline):
    Every async handler in `_TOOL_HANDLERS` that contains a sync loop
    (`for`/`while`) with a raw SQL `.execute()` call inside MUST also
    contain `await asyncio.sleep(0)` inside the loop body.  Without the
    checkpoint, `wait_for` cancellation cannot fire until the loop exits,
    and the transaction wrapper's __aexit__ ROLLBACK never runs — partial
    writes commit durably despite the timeout firing.  P0.8.1's
    behavioral test (TestHardCaseCancellationRollback) proves the property
    structurally when checkpoints exist; this AST scan ENFORCES they
    continue to exist as the codebase grows.

F2 (retry-path one-shot guarantee):
    `ask_retry_text` (Session 99 architecture) MUST internally call
    `_stream_together_raw(..., include_tools=False)`.  That single line is
    the load-bearing reason the retry path is structurally non-recursive
    — without `include_tools=False`, the retry stream could propose
    another tool call and re-enter `conversation_turn`'s dispatch chain,
    opening a recursive-DoS surface.  AST scan over the function body
    locks this property as a CI invariant.

Same shape as P0.5's inverse-check, P0.6's Store-base ratchet, and
P0.6.7v2's inverse writer enumeration — turning a coding discipline into
a structurally enforced invariant.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

# Install core.voice / core.audio stubs before pipeline import.
from tests.conftest import setup_pipeline_stubs as _setup_pipeline_stubs  # noqa: E402
_setup_pipeline_stubs()

import pipeline as _pipeline  # noqa: E402
import core.brain as _brain  # noqa: E402


REPO = pathlib.Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _func_body_ast(fn) -> ast.AST:
    """Return the AST body of `fn` as a Module node so ast.walk descends."""
    src = inspect.getsource(fn)
    # Source may be indented (nested def); textwrap.dedent normalizes.
    import textwrap
    return ast.parse(textwrap.dedent(src))


def _call_targets_execute(node: ast.Call) -> bool:
    """True if `node` is a call to `*.execute(...)` — captures the SQL marker
    used by every raw-cursor write path in the codebase (FaceDB, BrainDB,
    GraphDB).  Any attribute named `execute` qualifies — narrower matching
    on cursor/db/_conn names would miss `self._conn.execute` and
    `connection.execute` shapes that also wrap raw SQL."""
    if not isinstance(node.func, ast.Attribute):
        return False
    return node.func.attr == "execute"


def _body_contains_execute_call(body: list[ast.AST]) -> bool:
    """True if any descendant ast.Call in `body` matches .execute(...)."""
    for stmt in body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call) and _call_targets_execute(node):
                return True
    return False


def _body_contains_sleep0_checkpoint(body: list[ast.AST]) -> bool:
    """True if `body` contains an `await asyncio.sleep(0)` checkpoint.

    Detection matches both forms the codebase uses:
      await asyncio.sleep(0)
      await sleep(0)              # if `from asyncio import sleep`
    The argument is asserted to be a literal 0 — a non-zero sleep is a
    rate-limit / pacing call, NOT a cancellation checkpoint.
    """
    for stmt in body:
        for node in ast.walk(stmt):
            if not isinstance(node, ast.Await):
                continue
            call = node.value
            if not isinstance(call, ast.Call):
                continue
            # Extract the function name without binding to the receiver chain.
            if isinstance(call.func, ast.Attribute):
                fname = call.func.attr
            elif isinstance(call.func, ast.Name):
                fname = call.func.id
            else:
                continue
            if fname != "sleep":
                continue
            # Arg must be literal 0.
            if call.args and isinstance(call.args[0], ast.Constant) \
                    and call.args[0].value == 0:
                return True
    return False


# ---------------------------------------------------------------------------
# F1 — handler-checkpoint discipline
# ---------------------------------------------------------------------------

class TestF1HandlerCheckpointDiscipline:
    def test_every_handler_loop_with_execute_has_checkpoint(self) -> None:
        """For every `_TOOL_HANDLERS` value, for every sync loop in its
        body that contains a `.execute(...)` call, the same loop body MUST
        also contain `await asyncio.sleep(0)`.

        Why this matters: P0.8.1 proves the property structurally when
        checkpoints are present.  Without this CI invariant, a future
        handler refactor that drops the checkpoint would silently break
        the "tool_timeout = no partial state" guarantee — cancellation
        cannot fire mid-loop, transaction commits durably despite the
        timeout having fired."""
        violations: list[str] = []
        for tool_name, handler_fn in _pipeline._TOOL_HANDLERS.items():
            tree = _func_body_ast(handler_fn)
            for node in ast.walk(tree):
                if not isinstance(node, (ast.For, ast.While, ast.AsyncFor)):
                    continue
                if not _body_contains_execute_call(node.body):
                    continue
                if not _body_contains_sleep0_checkpoint(node.body):
                    # Report file-relative line if available — handler
                    # bodies are at module scope so the lineno is
                    # accurate w.r.t. the dedented source.
                    violations.append(
                        f"_handle_{tool_name}: sync loop at line "
                        f"{node.lineno} contains a .execute() call but no "
                        "`await asyncio.sleep(0)` checkpoint — wait_for "
                        "cancellation cannot fire mid-loop, breaking the "
                        "P0.8 'tool_timeout = no partial state' invariant."
                    )
        assert not violations, (
            "F1 invariant violated — handlers with sync SQL loops MUST "
            "include `await asyncio.sleep(0)` checkpoints so wait_for "
            "cancellation can deliver CancelledError to __aexit__ for "
            "ROLLBACK.\n\nViolations:\n  " + "\n  ".join(violations)
        )


# ---------------------------------------------------------------------------
# F2 — retry-path one-shot guarantee
# ---------------------------------------------------------------------------

class TestF2RetryPathOneShot:
    def test_ask_retry_text_internally_disables_tools(self) -> None:
        """`ask_retry_text` MUST internally call
        `_stream_together_raw(..., include_tools=False)`.  This is the
        single point of structural enforcement that the retry path cannot
        propose another tool call — without it, the retry stream could
        emit a tool_call event and re-enter conversation_turn's dispatch
        chain (recursive-DoS surface).

        `ask_retry_text` does not accept `include_tools` as a parameter
        (deliberate — the contract is internal, not caller-trusted).  The
        AST scan walks the function body, finds every call to
        `_stream_together_raw`, and asserts every one of them passes
        `include_tools=False` (literal Constant).
        """
        tree = _func_body_ast(_brain.ask_retry_text)
        stream_calls: list[ast.Call] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # Match `_stream_together_raw(...)` — bare Name or attribute.
            if isinstance(func, ast.Name) and func.id == "_stream_together_raw":
                stream_calls.append(node)
            elif isinstance(func, ast.Attribute) and func.attr == "_stream_together_raw":
                stream_calls.append(node)

        assert stream_calls, (
            "ask_retry_text body must call _stream_together_raw — the "
            "function shape changed and F2 can no longer locate the "
            "enforcement site.  Update the test if the retry pathway "
            "moved to a different streaming entry point."
        )

        violations: list[str] = []
        for call in stream_calls:
            # Find the include_tools kwarg.
            kw = next(
                (k for k in call.keywords if k.arg == "include_tools"),
                None,
            )
            if kw is None:
                violations.append(
                    f"_stream_together_raw call at line {call.lineno} "
                    "missing include_tools= kwarg — defaults to True "
                    "(tools-enabled), which would let the retry stream "
                    "propose another tool call."
                )
                continue
            if not (isinstance(kw.value, ast.Constant) and kw.value.value is False):
                violations.append(
                    f"_stream_together_raw call at line {call.lineno} "
                    f"passes include_tools={ast.unparse(kw.value)} — must "
                    "be the literal False."
                )

        assert not violations, (
            "F2 invariant violated — ask_retry_text MUST pass "
            "include_tools=False on every internal _stream_together_raw "
            "call.\n\nViolations:\n  " + "\n  ".join(violations)
        )
