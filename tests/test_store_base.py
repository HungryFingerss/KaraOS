"""Tests for core/store_base.py — P0.6.1 foundation.

Failing-test-first discipline: these tests were written before
core/store_base.py was implemented.
"""
from __future__ import annotations

import asyncio
import pytest
from core.store_base import Store


# ---------------------------------------------------------------------------
# Concrete test subclasses
# ---------------------------------------------------------------------------

class _CounterStore(Store):
    """Minimal concrete Store for unit tests."""

    def __init__(self) -> None:
        super().__init__()
        self._value: int = 0

    def reset(self) -> None:
        self._value = 0

    def peek_value(self) -> int:
        return self._value

    async def increment(self, by: int = 1) -> None:
        async with self._lock:
            self._value += by

    async def set_value(self, v: int) -> None:
        async with self._lock:
            self._value = v


class _NoResetStore(Store):
    """Store that intentionally omits reset() — must raise TypeError."""
    # reset() NOT defined — ABC enforcement check


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStoreBaseRequiresReset:
    def test_instantiating_store_without_reset_raises(self):
        """ABC @abstractmethod reset() must prevent instantiation."""
        with pytest.raises(TypeError):
            _NoResetStore()  # type: ignore[abstract]

    def test_instantiating_store_abc_itself_raises(self):
        """Store() itself is abstract — must raise TypeError."""
        with pytest.raises(TypeError):
            Store()  # type: ignore[abstract]


class TestStoreLockInitialized:
    def test_lock_is_asyncio_lock(self):
        store = _CounterStore()
        assert isinstance(store._lock, asyncio.Lock)

    def test_each_instance_has_its_own_lock(self):
        a = _CounterStore()
        b = _CounterStore()
        assert a._lock is not b._lock


class TestSubclassCanDefineTypedState:
    def test_initial_value(self):
        store = _CounterStore()
        assert store.peek_value() == 0

    def test_peek_is_sync(self):
        store = _CounterStore()
        # peek_value is NOT async — calling without await works
        result = store.peek_value()
        assert result == 0


class TestSubclassResetReturnsToInitial:
    async def test_reset_clears_state(self):
        store = _CounterStore()
        await store.increment(5)
        assert store.peek_value() == 5
        store.reset()
        assert store.peek_value() == 0

    async def test_reset_idempotent(self):
        store = _CounterStore()
        store.reset()
        store.reset()
        assert store.peek_value() == 0

    async def test_reset_after_multiple_mutations(self):
        store = _CounterStore()
        await store.increment(10)
        await store.increment(3)
        await store.set_value(99)
        store.reset()
        assert store.peek_value() == 0


class TestConcurrentMutationViaLockSerializes:
    async def test_concurrent_increments_are_serialized(self):
        """100 concurrent increments must sum to exactly 100."""
        store = _CounterStore()
        tasks = [asyncio.create_task(store.increment()) for _ in range(100)]
        await asyncio.gather(*tasks)
        assert store.peek_value() == 100

    async def test_lock_prevents_torn_reads(self):
        """Mutation under lock: no partial-write visible from peek."""
        store = _CounterStore()
        results: list[int] = []

        async def read_after_set(v: int) -> None:
            await store.set_value(v)
            # Immediately after set completes (lock released), peek sees new value.
            results.append(store.peek_value())

        # Run 20 writers sequentially and collect observed values.
        for i in range(20):
            await read_after_set(i)

        # Each writer saw its own written value immediately after release.
        assert results == list(range(20))
