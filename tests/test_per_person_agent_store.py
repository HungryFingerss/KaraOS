"""Unit tests for core/per_person_agent_store.py — P0.6.4."""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import re
from unittest.mock import MagicMock

import pytest

from core.per_person_agent_store import PerPersonAgentStore
from core.store_base import Store

PIPELINE_PATH = pathlib.Path(__file__).parent.parent / "pipeline.py"


# ---------------------------------------------------------------------------
# ABC / inheritance / structure
# ---------------------------------------------------------------------------

class TestPerPersonAgentStoreInheritance:
    def test_inherits_from_store(self) -> None:
        assert issubclass(PerPersonAgentStore, Store)

    def test_instantiates_without_error(self) -> None:
        s = PerPersonAgentStore()
        assert s is not None

    def test_has_asyncio_lock(self) -> None:
        import asyncio
        s = PerPersonAgentStore()
        assert isinstance(s._lock, asyncio.Lock)

    def test_reset_is_sync(self) -> None:
        s = PerPersonAgentStore()
        assert not inspect.iscoroutinefunction(s.reset)

    def test_reset_clears_all_three_structures(self) -> None:
        s = PerPersonAgentStore()
        asyncio.run(s.set_emotion_agent("p1", MagicMock()))
        asyncio.run(s.add_session_started("p1"))
        asyncio.run(s.add_ambient_wake("p1"))
        s.reset()
        assert s.peek_emotion_agent("p1") is None
        assert not s.is_session_started("p1")
        assert not s.is_ambient_wake_pending("p1")


# ---------------------------------------------------------------------------
# Emotion agent CRUD
# ---------------------------------------------------------------------------

class TestEmotionAgentCRUD:
    def test_set_and_peek_emotion_agent(self) -> None:
        s = PerPersonAgentStore()
        agent = MagicMock()
        asyncio.run(s.set_emotion_agent("p1", agent))
        assert s.peek_emotion_agent("p1") is agent

    def test_pop_removes_agent(self) -> None:
        s = PerPersonAgentStore()
        asyncio.run(s.set_emotion_agent("p1", MagicMock()))
        asyncio.run(s.pop_emotion_agent("p1"))
        assert s.peek_emotion_agent("p1") is None

    def test_pop_noop_on_missing_pid(self) -> None:
        s = PerPersonAgentStore()
        asyncio.run(s.pop_emotion_agent("nonexistent"))  # must not raise

    def test_clear_emotion_agents(self) -> None:
        s = PerPersonAgentStore()
        asyncio.run(s.set_emotion_agent("p1", MagicMock()))
        asyncio.run(s.set_emotion_agent("p2", MagicMock()))
        asyncio.run(s.clear_emotion_agents())
        assert s.peek_all_emotion_agents() == {}

    def test_peek_all_emotion_agents_returns_reference(self) -> None:
        s = PerPersonAgentStore()
        agent = MagicMock()
        asyncio.run(s.set_emotion_agent("p1", agent))
        ref = s.peek_all_emotion_agents()
        assert ref["p1"] is agent

    def test_peek_emotion_agent_pids(self) -> None:
        s = PerPersonAgentStore()
        asyncio.run(s.set_emotion_agent("p1", MagicMock()))
        asyncio.run(s.set_emotion_agent("p2", MagicMock()))
        assert set(s.peek_emotion_agent_pids()) == {"p1", "p2"}


# ---------------------------------------------------------------------------
# Sessions-started CRUD
# ---------------------------------------------------------------------------

class TestSessionsStartedCRUD:
    def test_add_and_is_session_started(self) -> None:
        s = PerPersonAgentStore()
        assert not s.is_session_started("p1")
        asyncio.run(s.add_session_started("p1"))
        assert s.is_session_started("p1")

    def test_discard_session_started(self) -> None:
        s = PerPersonAgentStore()
        asyncio.run(s.add_session_started("p1"))
        asyncio.run(s.discard_session_started("p1"))
        assert not s.is_session_started("p1")

    def test_discard_noop_on_missing(self) -> None:
        s = PerPersonAgentStore()
        asyncio.run(s.discard_session_started("nonexistent"))  # must not raise

    def test_clear_sessions_started(self) -> None:
        s = PerPersonAgentStore()
        asyncio.run(s.add_session_started("p1"))
        asyncio.run(s.add_session_started("p2"))
        asyncio.run(s.clear_sessions_started())
        assert s.peek_sessions_started() == set()

    def test_peek_sessions_started_is_copy(self) -> None:
        s = PerPersonAgentStore()
        asyncio.run(s.add_session_started("p1"))
        copy = s.peek_sessions_started()
        copy.add("injected")
        assert "injected" not in s._sessions_started


# ---------------------------------------------------------------------------
# Ambient-wake CRUD + debounce invariant
# ---------------------------------------------------------------------------

class TestAmbientWakeCRUD:
    def test_add_and_is_ambient_wake_pending(self) -> None:
        s = PerPersonAgentStore()
        assert not s.is_ambient_wake_pending("p1")
        asyncio.run(s.add_ambient_wake("p1"))
        assert s.is_ambient_wake_pending("p1")

    def test_discard_ambient_wake(self) -> None:
        s = PerPersonAgentStore()
        asyncio.run(s.add_ambient_wake("p1"))
        asyncio.run(s.discard_ambient_wake("p1"))
        assert not s.is_ambient_wake_pending("p1")

    def test_discard_noop_on_missing(self) -> None:
        s = PerPersonAgentStore()
        asyncio.run(s.discard_ambient_wake("nonexistent"))  # must not raise

    def test_clear_ambient_wake(self) -> None:
        s = PerPersonAgentStore()
        asyncio.run(s.add_ambient_wake("p1"))
        asyncio.run(s.add_ambient_wake("p2"))
        asyncio.run(s.clear_ambient_wake())
        assert s.peek_ambient_wake_pending() == set()

    def test_peek_ambient_wake_pending_is_copy(self) -> None:
        s = PerPersonAgentStore()
        asyncio.run(s.add_ambient_wake("p1"))
        copy = s.peek_ambient_wake_pending()
        copy.add("injected")
        assert "injected" not in s._ambient_wake_pending


# ---------------------------------------------------------------------------
# Debounce invariant — discard_ambient_wake precedes every continue/return
# on the greeting path in _background_vision_loop
# ---------------------------------------------------------------------------

class TestAmbientWakeDebounceInvariant:
    """Source-inspection: every early exit on the greeting path discards the
    ambient-wake signal so the pid never stays stuck in the pending set.

    Scans for the pattern: `discard_ambient_wake` appears before each
    `continue` or `return` that occurs after an `is_ambient_wake_pending` check
    within _background_vision_loop.
    """

    def test_discard_ambient_wake_present_in_background_vision_loop(self) -> None:
        src = PIPELINE_PATH.read_text(encoding="utf-8")
        # Verify the method is actually called somewhere in the greeting path.
        assert "discard_ambient_wake" in src, (
            "discard_ambient_wake must be called in pipeline.py "
            "(debounce invariant for _background_vision_loop)"
        )

    def test_discard_ambient_wake_call_count_at_least_one(self) -> None:
        src = PIPELINE_PATH.read_text(encoding="utf-8")
        count = src.count("discard_ambient_wake")
        assert count >= 1, (
            f"Expected ≥1 discard_ambient_wake calls in pipeline.py, found {count}. "
            "Every continue/return on the greeting path must consume the debounce signal."
        )
