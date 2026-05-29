"""P0.6.5 — parameterized cache store: peek-not-mutate read, oldest-by-cached-at
eviction on write, per-pid lifecycle.

Design contract (locked by spec at P0.6.7v2):

  peek() is genuinely read-only.  It does NOT touch the cached_at timestamp,
  does NOT reorder entries, does NOT trigger any data-state mutation.  The
  ONLY read-side mutation is the _hits / _misses observability counter (see
  OBSERVABILITY note below).

  This is NOT an LRU cache.  Touch-on-read LRU would mutate cached_at on
  every read, making `peek` ambiguous about whether it's a query or a
  promote.  Instead, eviction picks the oldest entry by cached_at (the
  insertion timestamp) when set() overflows the cap.  An entry's eviction
  eligibility is determined purely by when it was written, not when it was
  last read.

  OBSERVABILITY exception: _hits / _misses are documented read-side mutations
  with semantic distinction from the cache's data-state.  They are
  observability counters about the cache, not part of the cached data.
  Moving the increments to set() would change "actual hits" to
  "writes-after-a-hit" — wrong by construction for base-rate accuracy.  See
  the # OBSERVABILITY: annotations on the increment lines below.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import time
from typing import Any

from core.store_base import Store

CACHE_MISS = object()  # sentinel: peek(key, default=CACHE_MISS) → CACHE_MISS means miss


class CacheStore(Store):
    """Generic parameterized cache with optional TTL and write-only eviction.

    Four instances used in pipeline.py:
      _identity_hints_store     — no TTL, no cap
      _query_embedding_store    — no TTL, no cap
      _scene_block_store        — no TTL, max_entries=SCENE_BLOCK_CACHE_MAX_ENTRIES
      _classifier_cache_store   — ttl=5.0, max_entries=64
    """

    def __init__(
        self,
        name: str,
        *,
        ttl: float | None = None,
        max_entries: int | None = None,
    ) -> None:
        super().__init__()
        self._name = name
        self._ttl = ttl
        self._max_entries = max_entries
        # Plain dict — touch-on-read LRU is intentionally NOT supported, so
        # there is no need for OrderedDict's insertion-order-preserving
        # move_to_end semantics.
        self._data: dict[Any, tuple[Any, float]] = {}
        self._hits = 0
        self._misses = 0

    # ------------------------------------------------------------------
    # Store ABC
    # ------------------------------------------------------------------

    def reset(self) -> None:
        self._data.clear()
        self._hits = 0
        self._misses = 0

    # ------------------------------------------------------------------
    # Sync read (peek): no data mutation; counter increment is documented
    # observability-only (see module docstring).
    # ------------------------------------------------------------------

    def peek(self, key: Any, *, default: Any = None) -> Any:
        entry = self._data.get(key)
        if entry is None:
            self._misses += 1  # OBSERVABILITY: counter, not part of cached state
            return default
        value, ts = entry
        if self._ttl is not None and (time.monotonic() - ts) >= self._ttl:
            # TTL eviction on read is a write — but it removes ONE expired
            # entry that the caller just learned is stale.  Acceptable because
            # the alternative (return stale value or scan on every set) is
            # worse.  No reordering, no cached_at update on surviving entries.
            del self._data[key]
            self._misses += 1  # OBSERVABILITY: counter, not part of cached state
            return default
        self._hits += 1  # OBSERVABILITY: counter, not part of cached state
        return value

    def peek_stats(self) -> dict[str, Any]:
        return {
            "name": self._name,
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._data),
            "max_entries": self._max_entries,
        }

    def peek_size(self) -> int:
        return len(self._data)

    def peek_all(self) -> dict[Any, Any]:
        return {k: v for k, (v, _ts) in self._data.items()}

    # ------------------------------------------------------------------
    # Async mutators (all acquire lock)
    # ------------------------------------------------------------------

    async def set(self, key: Any, value: Any) -> None:
        async with self._lock:
            # Pre-P1 Bundle 5 (Bundle 3 paired-writer fix): cached_at is consumed
            # ONLY by duration math (peek() TTL `time.monotonic() - ts`) + relative
            # eviction ordering — never displayed, persisted, or sent cross-process.
            # Bundle 3 migrated the reader to time.monotonic() but left this paired
            # writer on time.time(), so monotonic()-wallclock made entries never
            # expire. Both clocks must match → store monotonic here too.
            self._data[key] = (value, time.monotonic())
            if self._max_entries is not None and len(self._data) > self._max_entries:
                # Oldest-by-cached-at eviction — purely write-driven.
                # min() over the dict by stored timestamp finds the entry
                # that was written longest ago and removes it.  An entry's
                # eviction eligibility never depends on read activity.
                oldest_key = min(self._data, key=lambda k: self._data[k][1])
                del self._data[oldest_key]

    async def discard(self, key: Any) -> None:
        async with self._lock:
            self._data.pop(key, None)

    async def discard_for_pid(self, pid: str) -> None:
        await self.discard(pid)

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()
