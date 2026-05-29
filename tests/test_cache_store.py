"""Unit tests for core/cache_store.py — P0.6.5."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import asyncio
import inspect
import time

import pytest

from core.cache_store import CACHE_MISS, CacheStore
from core.store_base import Store


# ---------------------------------------------------------------------------
# ABC / inheritance / structure
# ---------------------------------------------------------------------------

class TestCacheStoreInheritance:
    def test_inherits_from_store(self) -> None:
        assert issubclass(CacheStore, Store)

    def test_instantiates_without_error(self) -> None:
        s = CacheStore("test")
        assert s is not None

    def test_has_asyncio_lock(self) -> None:
        import asyncio
        s = CacheStore("test")
        assert isinstance(s._lock, asyncio.Lock)

    def test_reset_is_sync(self) -> None:
        s = CacheStore("test")
        assert not inspect.iscoroutinefunction(s.reset)

    def test_peek_is_sync(self) -> None:
        s = CacheStore("test")
        assert not inspect.iscoroutinefunction(s.peek)

    def test_set_is_async(self) -> None:
        s = CacheStore("test")
        assert inspect.iscoroutinefunction(s.set)

    def test_discard_is_async(self) -> None:
        s = CacheStore("test")
        assert inspect.iscoroutinefunction(s.discard)

    def test_clear_is_async(self) -> None:
        s = CacheStore("test")
        assert inspect.iscoroutinefunction(s.clear)


# ---------------------------------------------------------------------------
# CACHE_MISS sentinel
# ---------------------------------------------------------------------------

class TestCacheMissSentinel:
    def test_cache_miss_is_unique_object(self) -> None:
        assert CACHE_MISS is not None
        assert CACHE_MISS is not False
        assert CACHE_MISS is not 0  # noqa: E712

    def test_peek_returns_none_default_on_miss(self) -> None:
        s = CacheStore("test")
        assert s.peek("missing") is None

    def test_peek_returns_cache_miss_sentinel_on_miss(self) -> None:
        s = CacheStore("test")
        assert s.peek("missing", default=CACHE_MISS) is CACHE_MISS

    def test_stored_none_is_distinguishable_from_miss(self) -> None:
        s = CacheStore("test")
        asyncio.run(s.set("k", None))
        result = s.peek("k", default=CACHE_MISS)
        assert result is not CACHE_MISS
        assert result is None

    def test_stored_false_is_distinguishable_from_miss(self) -> None:
        s = CacheStore("test")
        asyncio.run(s.set("k", False))
        assert s.peek("k", default=CACHE_MISS) is not CACHE_MISS
        assert s.peek("k") is False


# ---------------------------------------------------------------------------
# Basic peek/set
# ---------------------------------------------------------------------------

class TestBasicPeekSet:
    def test_set_and_peek_value(self) -> None:
        s = CacheStore("test")
        asyncio.run(s.set("k", "v"))
        assert s.peek("k") == "v"

    def test_peek_missing_returns_custom_default(self) -> None:
        s = CacheStore("test")
        assert s.peek("nope", default="fallback") == "fallback"

    def test_set_overwrites_existing(self) -> None:
        s = CacheStore("test")
        asyncio.run(s.set("k", "v1"))
        asyncio.run(s.set("k", "v2"))
        assert s.peek("k") == "v2"

    def test_tuple_key_works(self) -> None:
        s = CacheStore("test")
        key = ("text", frozenset(["p1"]))
        asyncio.run(s.set(key, {"intent": "casual"}))
        assert s.peek(key) == {"intent": "casual"}


# ---------------------------------------------------------------------------
# TTL behavior
# ---------------------------------------------------------------------------

class TestTTLBehavior:
    def test_entry_valid_within_ttl(self) -> None:
        s = CacheStore("test", ttl=60.0)
        asyncio.run(s.set("k", "v"))
        assert s.peek("k") == "v"

    def test_entry_expired_after_ttl(self) -> None:
        s = CacheStore("test", ttl=0.01)
        asyncio.run(s.set("k", "v"))
        time.sleep(0.05)
        assert s.peek("k", default=CACHE_MISS) is CACHE_MISS

    def test_expired_entry_removed_lazily(self) -> None:
        s = CacheStore("test", ttl=0.01)
        asyncio.run(s.set("k", "v"))
        time.sleep(0.05)
        s.peek("k")
        assert "k" not in s._data

    def test_no_ttl_entry_never_expires(self) -> None:
        s = CacheStore("test")
        asyncio.run(s.set("k", "v"))
        assert s.peek("k") == "v"

    def test_ttl_miss_increments_miss_counter(self) -> None:
        s = CacheStore("test", ttl=0.01)
        asyncio.run(s.set("k", "v"))
        time.sleep(0.05)
        s.peek("k")
        assert s._misses == 1

    def test_ttl_hit_increments_hit_counter(self) -> None:
        s = CacheStore("test", ttl=60.0)
        asyncio.run(s.set("k", "v"))
        s.peek("k")
        assert s._hits == 1


# ---------------------------------------------------------------------------
# Oldest-by-cached-at eviction (write-driven; peek does NOT promote)
# ---------------------------------------------------------------------------

class TestOldestByCachedAtEviction:
    def test_evicts_oldest_by_cached_at_when_cap_reached(self) -> None:
        s = CacheStore("test", max_entries=2)
        asyncio.run(s.set("a", 1))
        asyncio.run(s.set("b", 2))
        asyncio.run(s.set("c", 3))  # evicts "a" (oldest cached_at)
        assert s.peek("a", default=CACHE_MISS) is CACHE_MISS
        assert s.peek("b") == 2
        assert s.peek("c") == 3

    def test_peek_does_not_promote_to_mru(self) -> None:
        """Locked spec: peek() is read-only.  A peek on 'a' does NOT save it
        from eviction — its cached_at is unchanged, so on the next set() it
        is still the oldest entry and is evicted first."""
        s = CacheStore("test", max_entries=2)
        asyncio.run(s.set("a", 1))
        asyncio.run(s.set("b", 2))
        s.peek("a")  # MUST NOT promote "a" — cached_at unchanged
        asyncio.run(s.set("c", 3))  # still evicts oldest by cached_at = "a"
        assert s.peek("a", default=CACHE_MISS) is CACHE_MISS
        assert s.peek("b") == 2
        assert s.peek("c") == 3

    def test_set_existing_key_does_not_trigger_eviction(self) -> None:
        """Updating an existing key keeps size constant — no eviction."""
        s = CacheStore("test", max_entries=2)
        asyncio.run(s.set("a", 1))
        asyncio.run(s.set("b", 2))
        asyncio.run(s.set("a", 99))  # update, not insert — size stays 2
        assert s.peek("a") == 99
        assert s.peek("b") == 2

    def test_size_stays_at_cap(self) -> None:
        s = CacheStore("test", max_entries=3)
        for i in range(10):
            asyncio.run(s.set(f"k{i}", i))
        assert len(s._data) == 3

    def test_no_cap_no_eviction(self) -> None:
        s = CacheStore("test")
        for i in range(100):
            asyncio.run(s.set(f"k{i}", i))
        assert len(s._data) == 100


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_clears_data(self) -> None:
        s = CacheStore("test")
        asyncio.run(s.set("k", "v"))
        s.reset()
        assert s.peek("k", default=CACHE_MISS) is CACHE_MISS
        assert len(s._data) == 0

    def test_reset_clears_hits_counter(self) -> None:
        s = CacheStore("test")
        asyncio.run(s.set("k", "v"))
        s.peek("k")
        s.reset()
        assert s._hits == 0

    def test_reset_clears_misses_counter(self) -> None:
        s = CacheStore("test")
        s.peek("missing")
        s.reset()
        assert s._misses == 0

    def test_reset_allows_reuse(self) -> None:
        s = CacheStore("test")
        asyncio.run(s.set("k", "v"))
        s.reset()
        asyncio.run(s.set("k2", "v2"))
        assert s.peek("k2") == "v2"


# ---------------------------------------------------------------------------
# Discard / clear
# ---------------------------------------------------------------------------

class TestDiscardAndClear:
    def test_discard_removes_entry(self) -> None:
        s = CacheStore("test")
        asyncio.run(s.set("k", "v"))
        asyncio.run(s.discard("k"))
        assert s.peek("k", default=CACHE_MISS) is CACHE_MISS

    def test_discard_noop_on_missing(self) -> None:
        s = CacheStore("test")
        asyncio.run(s.discard("nonexistent"))  # must not raise

    def test_discard_for_pid_removes_entry(self) -> None:
        s = CacheStore("test")
        asyncio.run(s.set("pid1", "data"))
        asyncio.run(s.discard_for_pid("pid1"))
        assert s.peek("pid1", default=CACHE_MISS) is CACHE_MISS

    def test_discard_for_pid_noop_on_missing(self) -> None:
        s = CacheStore("test")
        asyncio.run(s.discard_for_pid("nonexistent"))  # must not raise

    def test_clear_removes_all_entries(self) -> None:
        s = CacheStore("test")
        asyncio.run(s.set("a", 1))
        asyncio.run(s.set("b", 2))
        asyncio.run(s.clear())
        assert len(s._data) == 0

    def test_discard_leaves_other_entries_intact(self) -> None:
        s = CacheStore("test")
        asyncio.run(s.set("a", 1))
        asyncio.run(s.set("b", 2))
        asyncio.run(s.discard("a"))
        assert s.peek("b") == 2


# ---------------------------------------------------------------------------
# Peek methods
# ---------------------------------------------------------------------------

class TestPeekMethods:
    def test_peek_stats_returns_correct_fields(self) -> None:
        s = CacheStore("myname", max_entries=10)
        stats = s.peek_stats()
        assert stats["name"] == "myname"
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0
        assert stats["max_entries"] == 10

    def test_peek_stats_tracks_hits_and_misses(self) -> None:
        s = CacheStore("test")
        asyncio.run(s.set("k", "v"))
        s.peek("k")       # hit
        s.peek("missing") # miss
        stats = s.peek_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_peek_stats_size_reflects_data(self) -> None:
        s = CacheStore("test")
        asyncio.run(s.set("a", 1))
        asyncio.run(s.set("b", 2))
        assert s.peek_stats()["size"] == 2

    def test_peek_size_returns_count(self) -> None:
        s = CacheStore("test")
        asyncio.run(s.set("a", 1))
        asyncio.run(s.set("b", 2))
        assert s.peek_size() == 2

    def test_peek_size_empty_store_is_zero(self) -> None:
        s = CacheStore("test")
        assert s.peek_size() == 0

    def test_peek_all_returns_values_without_timestamps(self) -> None:
        s = CacheStore("test")
        asyncio.run(s.set("a", 1))
        asyncio.run(s.set("b", 2))
        all_data = s.peek_all()
        assert all_data == {"a": 1, "b": 2}

    def test_peek_all_is_shallow_copy(self) -> None:
        s = CacheStore("test")
        asyncio.run(s.set("a", 1))
        copy = s.peek_all()
        copy["injected"] = 99
        assert "injected" not in s._data
