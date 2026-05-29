"""core/conversation_store.py — P0.6.3: ConversationStore.

Owns four pipeline.py module globals:
  _conversation      dict[str, list]   — per-pid conversation history
  _last_greeted      dict[str, float]  — last-greeted timestamp per pid
  _last_self_update  dict[str, float]  — last self-update timestamp per pid
  _compact_pids      set[str]          — pids with a background compaction in flight

Contract (inherited from Store base):
  - All mutation methods are async and acquire self._lock.
  - peek_* and is_* methods are sync, no lock (single-thread asyncio safe).
  - reset() is sync — called by pytest autouse fixture outside the event loop.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

from typing import Callable, List, Optional

from core.store_base import Store

_PRUNE_MAX = 100  # evict oldest timestamp entry when dict exceeds this size


def _prune_timestamp_dict(d: dict, max_size: int = _PRUNE_MAX) -> None:
    if len(d) > max_size:
        del d[min(d, key=d.get)]


class ConversationStore(Store):
    """Single owner of _conversation, _last_greeted, _last_self_update, _compact_pids."""

    def __init__(self) -> None:
        super().__init__()
        self._history: dict[str, list] = {}
        self._last_greeted: dict[str, float] = {}
        self._last_self_update: dict[str, float] = {}
        self._compact_pids: set[str] = set()

    def reset(self) -> None:
        self._history.clear()
        self._last_greeted.clear()
        self._last_self_update.clear()
        self._compact_pids.clear()

    # ── History mutations ──────────────────────────────────────────────────────

    async def set_history(self, pid: str, history: list) -> None:
        async with self._lock:
            self._history[pid] = history

    async def append_turns(self, pid: str, msgs: list) -> None:
        """Atomic setdefault().extend() — creates empty list if pid absent."""
        async with self._lock:
            self._history.setdefault(pid, []).extend(msgs)

    async def pop_history(self, pid: str) -> Optional[list]:
        async with self._lock:
            return self._history.pop(pid, None)

    async def init_empty(self, pid: str) -> None:
        async with self._lock:
            self._history.setdefault(pid, [])

    async def ensure_history_loaded(
        self, pid: str, loader_fn: Callable[[], list]
    ) -> None:
        """Lazy hydration with double-checked locking.

        Only calls loader_fn when pid has no history entry.  loader_fn must be
        a zero-argument callable that returns the history list (e.g. a lambda
        wrapping db.load_conversation_history).
        """
        if pid in self._history:
            return
        async with self._lock:
            if pid not in self._history:
                self._history[pid] = loader_fn()

    async def clear_all_history(self) -> None:
        async with self._lock:
            self._history.clear()

    # ── Greeted mutations ──────────────────────────────────────────────────────

    async def touch_greeted(self, pid: str, ts: float) -> None:
        async with self._lock:
            self._last_greeted[pid] = ts
            _prune_timestamp_dict(self._last_greeted)

    async def clear_all_greeted(self) -> None:
        async with self._lock:
            self._last_greeted.clear()

    # ── Self-update mutations ──────────────────────────────────────────────────

    async def touch_self_update(self, pid: str, ts: float) -> None:
        async with self._lock:
            self._last_self_update[pid] = ts
            _prune_timestamp_dict(self._last_self_update)

    async def clear_all_self_update(self) -> None:
        async with self._lock:
            self._last_self_update.clear()

    # ── Compact-pid mutations ──────────────────────────────────────────────────

    async def add_compact(self, pid: str) -> None:
        async with self._lock:
            self._compact_pids.add(pid)

    async def release_compact(self, pid: str) -> None:
        """Discard pid from the compaction set.

        INVARIANT: callers MUST invoke this from inside a try/finally block so
        the pid is never permanently stuck in the set if the background task
        raises before reaching the normal completion point.
        """
        async with self._lock:
            self._compact_pids.discard(pid)

    async def clear_all_compact(self) -> None:
        async with self._lock:
            self._compact_pids.clear()

    # ── Factory reset (all four structures) ───────────────────────────────────

    async def clear_all(self) -> None:
        async with self._lock:
            self._history.clear()
            self._last_greeted.clear()
            self._last_self_update.clear()
            self._compact_pids.clear()

    # ── Sync peek / predicate methods (no lock) ───────────────────────────────

    def peek_history(self, pid: str) -> list:
        return self._history.get(pid, [])

    def peek_pids(self) -> List[str]:
        return list(self._history.keys())

    def peek_has_history(self, pid: str) -> bool:
        return pid in self._history

    def peek_last_greeted(self, pid: str) -> float:
        return self._last_greeted.get(pid, 0.0)

    def peek_last_self_update(self, pid: str) -> float:
        return self._last_self_update.get(pid, 0.0)

    def is_compacting(self, pid: str) -> bool:
        return pid in self._compact_pids
