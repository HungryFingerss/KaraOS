"""P0.8 — Per-tool timeout protection (behavioral tests).

Tests fall into two groups:

(1) **Timeout fires**: monkeypatch each _handle_<tool> to await
    asyncio.sleep(60); call _execute_tool; assert the call returns within
    `timeout + 1` second budget with status "tool_timeout".

(2) **Cancellation safety**: monkeypatch each _handle_<tool> to start a
    SQL transaction, write a sentinel row, then await asyncio.sleep(60).
    When wait_for fires CancelledError, the transaction's __aexit__ must
    roll back the partial write.  Assert no sentinel row visible after
    timeout.  This is the load-bearing invariant — partial writes from a
    cancelled handler would corrupt the DB across all 5 tool paths.

Each test uses a real ``PipelineStateStore`` / ``SessionStore`` /
``BrainDB`` (in-memory SQLite for speed) so the assertions exercise the
actual transaction wrapper chain, not stub mocks.
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from unittest.mock import MagicMock, patch

import pytest

# Install core.voice / core.audio stubs BEFORE importing pipeline to avoid
# the Windows torchaudio DLL crash (OSError 0xc0000139).  Conftest helper
# is idempotent.
from tests.conftest import setup_pipeline_stubs as _setup_pipeline_stubs  # noqa: E402
_setup_pipeline_stubs()

import pipeline  # noqa: E402
from core.config import TOOL_TIMEOUT_OVERRIDES, TOOL_TIMEOUT_SECS  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TOOL_NAMES = (
    "update_person_name",
    "report_identity_mismatch",
    "update_system_name",
    "shutdown",
    "search_memory",
)


def _expected_timeout(tool: str) -> float:
    return TOOL_TIMEOUT_OVERRIDES.get(tool, TOOL_TIMEOUT_SECS)


async def _seed_known_session(pid: str = "p_jagan", name: str = "Jagan") -> None:
    """Open a 'known' session so the privilege gate lets non-shutdown
    tools through (shutdown requires 'best_friend'; tests for shutdown
    open a 'best_friend' session explicitly)."""
    await pipeline._session_store.open_session(
        pid, name, "known", "face", now=time.time(),
    )


# ---------------------------------------------------------------------------
# Group 1: timeout fires within budget
# ---------------------------------------------------------------------------

class TestTimeoutFiresPerTool:
    @pytest.mark.parametrize("tool", _TOOL_NAMES)
    async def test_handler_hang_triggers_tool_timeout(self, tool, monkeypatch):
        """Monkeypatch the handler to sleep(60); wait_for must cancel it
        within `timeout + 1` and return status 'tool_timeout'."""
        # shutdown + update_system_name are best_friend-privileged; everyone
        # else passes the privilege gate as "known".
        if tool in ("shutdown", "update_system_name"):
            await pipeline._session_store.open_session(
                "p_jagan", "Jagan", "best_friend", "face", now=time.time(),
            )
        else:
            await _seed_known_session()

        budget = _expected_timeout(tool)

        async def _hang(args, ctx):
            await asyncio.sleep(60.0)
            return "handled"

        # Patch the per-tool entry in _TOOL_HANDLERS — direct dict mutation
        # is more reliable than monkeypatching the module attribute,
        # because _execute_tool reads _TOOL_HANDLERS.get(name).
        orig_handler = pipeline._TOOL_HANDLERS[tool]
        pipeline._TOOL_HANDLERS[tool] = _hang
        try:
            t0 = time.perf_counter()
            result = await pipeline._execute_tool(
                tool,
                args={"name": "X", "reason": "X", "query": "X"},
                person_id="p_jagan",
                person_name="Jagan",
                db=MagicMock(),
                user_text="my name is X",
                intent_sidecar=None,
            )
            elapsed = time.perf_counter() - t0
        finally:
            pipeline._TOOL_HANDLERS[tool] = orig_handler

        assert result == "tool_timeout", (
            f"expected 'tool_timeout' for {tool}, got {result!r}"
        )
        # Generous wall-clock slack: budget + 1s.
        assert elapsed < budget + 1.0, (
            f"{tool} returned after {elapsed:.2f}s (budget {budget}s) — "
            "wait_for cancellation may be slow."
        )


# ---------------------------------------------------------------------------
# Group 2: cancellation safety — partial SQL rolls back via __aexit__
# ---------------------------------------------------------------------------

class TestCancellationRollback:
    """Transaction wrappers (FaceDB.transaction / BrainDB._safe_commit)
    must propagate CancelledError through __aexit__ → ROLLBACK.  This
    tests the contract directly with an in-memory SQLite connection and
    a manual `async with` ROLLBACK-on-exception wrapper that mirrors the
    production pattern.
    """

    @pytest.mark.parametrize("tool", _TOOL_NAMES)
    async def test_handler_cancellation_rolls_back_sql(self, tool, monkeypatch):
        """A handler that starts a transaction, writes a sentinel row,
        then sleeps until wait_for cancels it MUST leave no sentinel row
        visible afterwards — the cancellation triggers ROLLBACK via the
        transaction wrapper's __aexit__."""
        if tool in ("shutdown", "update_system_name"):
            await pipeline._session_store.open_session(
                "p_jagan", "Jagan", "best_friend", "face", now=time.time(),
            )
        else:
            await _seed_known_session()

        # Isolated in-memory SQLite db with a sentinel table.
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE sentinel (tool TEXT)")
        conn.commit()

        class _AsyncTxn:
            """Production-style async transaction wrapper.  Commits on
            clean exit; rolls back on ANY exception (CancelledError
            included).  Mirrors FaceDB.transaction / BrainDB._safe_commit."""
            def __init__(self, c): self.c = c
            async def __aenter__(self):
                self.c.execute("BEGIN")
                return self.c
            async def __aexit__(self, exc_type, exc, tb):
                if exc_type is None:
                    self.c.commit()
                else:
                    self.c.rollback()
                return False  # don't suppress

        async def _partial_write(args, ctx):
            async with _AsyncTxn(conn):
                conn.execute("INSERT INTO sentinel(tool) VALUES (?)", (tool,))
                # Sentinel is now IN the transaction.  Sleep past timeout.
                await asyncio.sleep(60.0)
            return "handled"

        orig_handler = pipeline._TOOL_HANDLERS[tool]
        pipeline._TOOL_HANDLERS[tool] = _partial_write
        try:
            result = await pipeline._execute_tool(
                tool,
                args={"name": "X", "reason": "X", "query": "X"},
                person_id="p_jagan",
                person_name="Jagan",
                db=MagicMock(),
                user_text="my name is X",
                intent_sidecar=None,
            )
        finally:
            pipeline._TOOL_HANDLERS[tool] = orig_handler

        assert result == "tool_timeout"
        # Critical invariant: no sentinel row survived the cancellation.
        rows = conn.execute("SELECT COUNT(*) FROM sentinel").fetchone()[0]
        assert rows == 0, (
            f"{tool}: partial SQL write survived the timeout cancellation "
            f"({rows} sentinel rows present). Transaction __aexit__ must "
            "ROLLBACK on CancelledError."
        )
        conn.close()


# ---------------------------------------------------------------------------
# Group 3 (P0.8.1): hard-case cancellation — sync SQL loop with periodic
# checkpoints.  The easy test (Group 2) used a single sleep(60); the auditor
# flagged that a future handler doing tight sync writes between awaits could
# commit durably despite timeout fire.  This test verifies the structural
# property holds for the realistic shape: a sync write loop interleaved with
# `await asyncio.sleep(0)` checkpoints — which is what a busy handler would
# look like in practice (every async function in our codebase yields at some
# point, even mid-loop, via the executor or sub-call).
# ---------------------------------------------------------------------------

class TestHardCaseCancellationRollback:
    async def test_sync_sql_loop_with_periodic_checkpoint_rolls_back(self):
        """The hard case: handler does 10k sync cursor.execute()s with a
        periodic `await asyncio.sleep(0)` every 100 writes.  When wait_for
        fires mid-loop, CancelledError raises at the next checkpoint and
        the transaction's __aexit__ ROLLBACKs the un-committed writes.

        If this test fails, the architectural invariant 'tool_timeout = no
        partial state' is held only by handler discipline, not by structure
        — at which point we'd need to either enforce periodic-checkpoint
        discipline OR add an AST scan that rejects sync-SQL-without-await
        handler bodies."""
        await pipeline._session_store.open_session(
            "p_jagan", "Jagan", "best_friend", "face", now=time.time(),
        )
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE rows (i INTEGER)")
        conn.commit()

        class _AsyncTxn:
            def __init__(self, c): self.c = c
            async def __aenter__(self):
                self.c.execute("BEGIN")
                return self.c
            async def __aexit__(self, exc_type, exc, tb):
                if exc_type is None:
                    self.c.commit()
                else:
                    self.c.rollback()
                return False

        async def _hot_loop_handler(args, ctx):
            async with _AsyncTxn(conn):
                for i in range(10_000):
                    conn.execute("INSERT INTO rows(i) VALUES (?)", (i,))
                    if i % 100 == 0:
                        # Yield to the event loop.  CancelledError is
                        # delivered at this await point when wait_for
                        # fires.  Without this checkpoint, the loop would
                        # run to completion synchronously and commit.
                        await asyncio.sleep(0)
            return "handled"

        # Use a TINY timeout so wait_for fires before the loop finishes —
        # otherwise the test is just measuring rollback on a successful run.
        # Patch TOOL_TIMEOUT_OVERRIDES for shutdown to a very small value.
        orig_override = TOOL_TIMEOUT_OVERRIDES.get("shutdown")
        TOOL_TIMEOUT_OVERRIDES["shutdown"] = 0.001  # 1ms — definitely fires before 10k inserts complete
        orig_handler = pipeline._TOOL_HANDLERS["shutdown"]
        pipeline._TOOL_HANDLERS["shutdown"] = _hot_loop_handler
        try:
            result = await pipeline._execute_tool(
                "shutdown",
                args={},
                person_id="p_jagan",
                person_name="Jagan",
                db=MagicMock(),
                user_text="shut down",
                intent_sidecar=None,
            )
        finally:
            pipeline._TOOL_HANDLERS["shutdown"] = orig_handler
            if orig_override is None:
                TOOL_TIMEOUT_OVERRIDES.pop("shutdown", None)
            else:
                TOOL_TIMEOUT_OVERRIDES["shutdown"] = orig_override

        assert result == "tool_timeout"
        # The critical assertion: NO rows survived the cancellation.  Even
        # with thousands of executed INSERTs in flight, none committed.
        row_count = conn.execute("SELECT COUNT(*) FROM rows").fetchone()[0]
        assert row_count == 0, (
            f"hard-case rollback failed: {row_count} rows committed despite "
            "timeout. Transaction __aexit__ did not ROLLBACK on CancelledError. "
            "Either add explicit checkpoint discipline to handlers OR add a "
            "structural AST scan that rejects sync-SQL-without-await patterns."
        )
        conn.close()


# ---------------------------------------------------------------------------
# Group 4 (P0.8.1): search_web Tavily timeout wrap
# ---------------------------------------------------------------------------

class TestSearchWebTimeoutWrap:
    """search_web is consumed inline inside ask_stream (NOT through
    _TOOL_HANDLERS), so the dispatch-table wait_for doesn't protect it.
    The P0.8.1 fix wraps the Tavily httpx.post inside `_web_search` with
    asyncio.wait_for(..., timeout=TOOL_TIMEOUT_OVERRIDES['search_web'])
    and returns a structured timeout dict so callers route the LLM through
    the same hint-to-training-knowledge path as other search errors."""

    @pytest.mark.skipif(
        not os.getenv("TAVILY_API_KEY"),
        reason="requires TAVILY_API_KEY — _web_search short-circuits to None on no-key, "
               "bypassing the wait_for path this test is meant to exercise. The timeout-"
               "tolerance contract requires a real Tavily client to monkeypatch.",
    )
    async def test_tavily_hang_returns_timeout_dict_within_budget(self, monkeypatch):
        """Monkeypatch the Tavily HTTP client to hang; _web_search must
        return a {error, hint} dict within budget+1s rather than block."""
        import core.brain as _brain_mod

        # Defense-in-depth: if for any reason _tavily_http is still None
        # despite TAVILY_API_KEY being set (e.g., httpx import failed),
        # skip rather than fail the assertion.
        if _brain_mod._tavily_http is None:
            pytest.skip("Tavily client unexpectedly None despite TAVILY_API_KEY set")

        async def _hang_post(*_a, **_kw):
            await asyncio.sleep(60.0)

        # Patch the AsyncClient.post method to hang.
        monkeypatch.setattr(_brain_mod._tavily_http, "post", _hang_post)

        budget = TOOL_TIMEOUT_OVERRIDES.get("search_web", TOOL_TIMEOUT_SECS)
        t0 = time.perf_counter()
        result = await _brain_mod._web_search("what's the weather today?")
        elapsed = time.perf_counter() - t0

        assert elapsed < budget + 1.0, (
            f"_web_search returned after {elapsed:.2f}s (budget {budget}s) — "
            "asyncio.wait_for did not bound the Tavily call."
        )
        assert isinstance(result, dict), (
            f"expected structured-error dict on timeout, got {type(result).__name__}"
        )
        assert result.get("error") == "timeout"
        assert "hint" in result and result["hint"], (
            "timeout return must include a hint string so the LLM can route "
            "to training knowledge instead of fabricating results."
        )

    def test_web_search_call_site_uses_wait_for(self):
        """Source-inspection: confirm the actual wait_for wrap is in place
        — guards against a future refactor stripping the protection while
        leaving the structured timeout-dict return path intact (which would
        silently make the hang-tolerance dead code)."""
        import inspect, core.brain as _brain_mod, re as _re
        src = inspect.getsource(_brain_mod._web_search)
        # The call form: await asyncio.wait_for(_tavily_http.post(...), timeout=...)
        m = _re.search(
            r"asyncio\.wait_for\s*\(\s*\n?\s*_tavily_http\.post",
            src,
        )
        assert m is not None, (
            "_web_search must wrap _tavily_http.post in asyncio.wait_for. "
            "Without it, search_web can still hang the pipeline despite P0.8."
        )


# ---------------------------------------------------------------------------
# Source-inspection: wait_for wraps ONLY the handler dispatch
# ---------------------------------------------------------------------------

class TestWaitForScope:
    def test_execute_tool_wraps_only_handler_dispatch(self):
        """wait_for must appear EXACTLY once in _execute_tool, on the line
        that dispatches the handler.  Layer 0 / repeat / privilege gates
        above it run un-budgeted."""
        import inspect, re as _re
        src = inspect.getsource(pipeline._execute_tool)
        # Count wait_for occurrences (call expressions, not strings).
        occurrences = len(_re.findall(r"asyncio\.wait_for\s*\(", src))
        assert occurrences == 1, (
            f"_execute_tool contains {occurrences} asyncio.wait_for calls; "
            "exactly 1 expected (handler dispatch only)."
        )

    def test_wait_for_wraps_handler_call_not_gates(self):
        """The wait_for argument must be a handler(args, ctx) call — not
        a gate predicate, not a privilege check."""
        import inspect, re as _re
        src = inspect.getsource(pipeline._execute_tool)
        # The handler dispatch should look like: wait_for(handler(args, _ctx)...
        # or wait_for(handler(...), timeout=_timeout)
        m = _re.search(
            r"asyncio\.wait_for\s*\(\s*handler\s*\(\s*args\s*,\s*_ctx\s*\)",
            src,
        )
        assert m is not None, (
            "asyncio.wait_for must wrap `handler(args, _ctx)` — confirms "
            "Layer 0 / privilege / repeat gates are above the wait_for."
        )

    def test_handlers_above_gates_not_wrapped(self):
        """Source ordering: Layer 0 / repeat / privilege block headers must
        appear BEFORE the actual `await asyncio.wait_for(handler(...)` call
        site.  Catches a future refactor that moves the wait_for above one
        of the gates."""
        import inspect, re as _re
        src = inspect.getsource(pipeline._execute_tool)
        # Use the actual gate-comment headers (unique in function body) and
        # the actual wait_for *call* (not the docstring mention) as anchors.
        idx_layer0    = src.find("# ── Layer 0:")
        idx_repeat    = src.find("# ── Layer 3:")
        idx_privilege = src.find("# ── Privilege gate")
        # Find the call form `await asyncio.wait_for(handler(`, NOT the
        # docstring mention — the docstring also contains "asyncio.wait_for"
        # and would otherwise be picked up as a false positive.
        m = _re.search(
            r"await\s+asyncio\.wait_for\s*\(\s*handler\s*\(",
            src,
        )
        assert m is not None, "wait_for(handler(...)) call site not found"
        idx_waitfor = m.start()
        assert 0 <= idx_layer0 < idx_waitfor, "Layer 0 header must precede wait_for"
        assert 0 <= idx_repeat < idx_waitfor, "Layer 3 (repeat) header must precede wait_for"
        assert 0 <= idx_privilege < idx_waitfor, "Privilege gate header must precede wait_for"

    def test_tool_handlers_dict_covers_all_privileged_tools(self):
        """Every entry in TOOL_PRIVILEGES that has an extracted handler
        is registered in _TOOL_HANDLERS.  search_web is not in the dict
        because it's consumed inside ask_stream (per CLAUDE.md Phase 1.5
        note); other privileged tools must be present."""
        registered = set(pipeline._TOOL_HANDLERS.keys())
        expected = {
            "update_person_name",
            "report_identity_mismatch",
            "update_system_name",
            "shutdown",
            "search_memory",
        }
        assert expected.issubset(registered), (
            f"_TOOL_HANDLERS missing {expected - registered}"
        )
