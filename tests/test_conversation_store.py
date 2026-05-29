"""Unit tests for core/conversation_store.py — P0.6.3."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import asyncio
import inspect
import pathlib

import pytest

from core.conversation_store import ConversationStore
from core.store_base import Store

PIPELINE_PATH = pathlib.Path(__file__).parent.parent / "pipeline.py"


# ---------------------------------------------------------------------------
# ABC / inheritance / structure
# ---------------------------------------------------------------------------

class TestConversationStoreInheritance:
    def test_inherits_from_store(self) -> None:
        assert issubclass(ConversationStore, Store)

    def test_instantiates_without_error(self) -> None:
        s = ConversationStore()
        assert s is not None

    def test_has_asyncio_lock(self) -> None:
        import asyncio
        s = ConversationStore()
        assert isinstance(s._lock, asyncio.Lock)

    def test_reset_is_sync(self) -> None:
        s = ConversationStore()
        assert not inspect.iscoroutinefunction(s.reset)

    def test_reset_clears_all_four_structures(self) -> None:
        s = ConversationStore()
        asyncio.run(s.set_history("p1", [{"role": "user", "content": "hi"}]))
        asyncio.run(s.touch_greeted("p1", 1000.0))
        asyncio.run(s.touch_self_update("p1", 2000.0))
        asyncio.run(s.add_compact("p1"))
        s.reset()
        assert s.peek_history("p1") == []
        assert s.peek_last_greeted("p1") == 0.0
        assert s.peek_last_self_update("p1") == 0.0
        assert not s.is_compacting("p1")


# ---------------------------------------------------------------------------
# EXPECTED_FIELDS schema invariant (P0.6.3 Phase 5)
#
# Guards that the four internal dict/set attributes that ConversationStore
# owns are named exactly as expected.  Any rename must update this test.
# ---------------------------------------------------------------------------

class TestConversationStoreExpectedFields:
    _EXPECTED_FIELDS = {"_history", "_last_greeted", "_last_self_update", "_compact_pids"}

    def test_all_expected_fields_present_on_instance(self) -> None:
        s = ConversationStore()
        missing = self._EXPECTED_FIELDS - set(vars(s))
        assert not missing, (
            f"ConversationStore is missing expected internal fields: {missing}. "
            "Update core/conversation_store.py to add them."
        )

    def test_no_unexpected_extra_data_fields(self) -> None:
        """The four known fields plus _lock (from Store base) cover all instance attrs."""
        s = ConversationStore()
        instance_attrs = set(vars(s))
        # _lock comes from Store.__init__
        allowed = self._EXPECTED_FIELDS | {"_lock"}
        unexpected = instance_attrs - allowed
        assert not unexpected, (
            f"ConversationStore has unexpected instance attributes: {unexpected}. "
            "If you added a new field, register it in EXPECTED_FIELDS."
        )

    def test_history_is_dict(self) -> None:
        s = ConversationStore()
        assert isinstance(s._history, dict)

    def test_last_greeted_is_dict(self) -> None:
        s = ConversationStore()
        assert isinstance(s._last_greeted, dict)

    def test_last_self_update_is_dict(self) -> None:
        s = ConversationStore()
        assert isinstance(s._last_self_update, dict)

    def test_compact_pids_is_set(self) -> None:
        s = ConversationStore()
        assert isinstance(s._compact_pids, set)


# ---------------------------------------------------------------------------
# History mutations
# ---------------------------------------------------------------------------

class TestHistoryMutations:
    def test_set_history_stores_list(self) -> None:
        s = ConversationStore()
        msgs = [{"role": "user", "content": "hello"}]
        asyncio.run(s.set_history("p1", msgs))
        assert s.peek_history("p1") == msgs

    def test_append_turns_creates_and_extends(self) -> None:
        s = ConversationStore()
        asyncio.run(s.append_turns("p1", [{"role": "user", "content": "a"}]))
        asyncio.run(s.append_turns("p1", [{"role": "assistant", "content": "b"}]))
        assert len(s.peek_history("p1")) == 2

    def test_pop_history_removes_and_returns(self) -> None:
        s = ConversationStore()
        msgs = [{"role": "user", "content": "hi"}]
        asyncio.run(s.set_history("p1", msgs))
        result = asyncio.run(s.pop_history("p1"))
        assert result == msgs
        assert s.peek_history("p1") == []

    def test_pop_history_returns_none_when_absent(self) -> None:
        s = ConversationStore()
        result = asyncio.run(s.pop_history("noone"))
        assert result is None

    def test_init_empty_creates_empty_list(self) -> None:
        s = ConversationStore()
        asyncio.run(s.init_empty("p1"))
        assert s.peek_history("p1") == []

    def test_init_empty_does_not_overwrite(self) -> None:
        s = ConversationStore()
        msgs = [{"role": "user", "content": "existing"}]
        asyncio.run(s.set_history("p1", msgs))
        asyncio.run(s.init_empty("p1"))
        assert s.peek_history("p1") == msgs

    def test_ensure_history_loaded_calls_loader_when_absent(self) -> None:
        s = ConversationStore()
        called = []
        def loader():
            called.append(True)
            return [{"role": "user", "content": "loaded"}]
        asyncio.run(s.ensure_history_loaded("p1", loader))
        assert len(called) == 1
        assert len(s.peek_history("p1")) == 1

    def test_ensure_history_loaded_skips_loader_when_present(self) -> None:
        s = ConversationStore()
        asyncio.run(s.set_history("p1", [{"role": "user", "content": "existing"}]))
        called = []
        asyncio.run(s.ensure_history_loaded("p1", lambda: called.append(True) or []))
        assert not called

    def test_peek_has_history(self) -> None:
        s = ConversationStore()
        assert not s.peek_has_history("p1")
        asyncio.run(s.set_history("p1", []))
        assert s.peek_has_history("p1")

    def test_peek_pids(self) -> None:
        s = ConversationStore()
        asyncio.run(s.set_history("p1", []))
        asyncio.run(s.set_history("p2", []))
        pids = s.peek_pids()
        assert "p1" in pids and "p2" in pids


# ---------------------------------------------------------------------------
# Greeted / self-update timestamp mutations
# ---------------------------------------------------------------------------

class TestTimestampMutations:
    def test_touch_greeted_stores_timestamp(self) -> None:
        s = ConversationStore()
        asyncio.run(s.touch_greeted("p1", 1234.5))
        assert s.peek_last_greeted("p1") == 1234.5

    def test_peek_last_greeted_default_zero(self) -> None:
        s = ConversationStore()
        assert s.peek_last_greeted("unknown") == 0.0

    def test_touch_self_update_stores_timestamp(self) -> None:
        s = ConversationStore()
        asyncio.run(s.touch_self_update("p1", 9999.0))
        assert s.peek_last_self_update("p1") == 9999.0

    def test_peek_last_self_update_default_zero(self) -> None:
        s = ConversationStore()
        assert s.peek_last_self_update("unknown") == 0.0


# ---------------------------------------------------------------------------
# Compact-pid mutations
# ---------------------------------------------------------------------------

class TestCompactPidMutations:
    def test_add_compact_marks_pid(self) -> None:
        s = ConversationStore()
        asyncio.run(s.add_compact("p1"))
        assert s.is_compacting("p1")

    def test_release_compact_unmarks_pid(self) -> None:
        s = ConversationStore()
        asyncio.run(s.add_compact("p1"))
        asyncio.run(s.release_compact("p1"))
        assert not s.is_compacting("p1")

    def test_release_compact_idempotent(self) -> None:
        s = ConversationStore()
        asyncio.run(s.release_compact("neveradded"))  # must not raise

    def test_is_compacting_default_false(self) -> None:
        s = ConversationStore()
        assert not s.is_compacting("nobody")


# ---------------------------------------------------------------------------
# P0.6.3 Phase 4 — source-inspection: release_compact inside finally:
#
# Guards the Session 110 invariant that _compact_history_background's
# release_compact call lives inside a finally: block — so it fires even
# when autocompact_history raises, preventing pids from getting stuck in
# the compacting set permanently.
# ---------------------------------------------------------------------------

class TestReleaseCompactInFinallyBlock:
    def test_release_compact_is_inside_finally_in_compact_history_background(self) -> None:
        """
        AST-verify that within _compact_history_background, every call to
        release_compact appears only inside a Try node's finalbody.
        """
        src = PIPELINE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(src)

        # Walk the entire AST to find all AsyncFunctionDef named
        # _compact_history_background (it's a nested function inside conversation_turn).
        compact_fn_bodies: list[list[ast.stmt]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_compact_history_background":
                compact_fn_bodies.append(node.body)

        assert compact_fn_bodies, (
            "_compact_history_background not found in pipeline.py — "
            "was it renamed or deleted?"
        )

        # For each function body, verify release_compact is in a finally block.
        def _calls_release_compact(stmts: list[ast.stmt]) -> bool:
            """Return True if any statement is an await of release_compact."""
            for stmt in stmts:
                for node in ast.walk(stmt):
                    if (
                        isinstance(node, ast.Await)
                        and isinstance(node.value, ast.Call)
                        and isinstance(node.value.func, ast.Attribute)
                        and node.value.func.attr == "release_compact"
                    ):
                        return True
            return False

        for body in compact_fn_bodies:
            # Find Try nodes in the function body.
            try_nodes: list[ast.Try] = [
                node for stmt in body for node in ast.walk(stmt)
                if isinstance(node, ast.Try)
            ]
            assert try_nodes, (
                "_compact_history_background has no try block — "
                "release_compact must be inside a finally: block."
            )
            # At least one Try node must have release_compact in its finalbody.
            found_in_finally = any(
                _calls_release_compact(t.finalbody) for t in try_nodes
            )
            assert found_in_finally, (
                "release_compact is not called inside a finally: block in "
                "_compact_history_background. "
                "This means a pid can get stuck in _compact_pids if autocompact raises."
            )

    def test_pipeline_path_exists(self) -> None:
        assert PIPELINE_PATH.exists(), f"pipeline.py not found at {PIPELINE_PATH}"
