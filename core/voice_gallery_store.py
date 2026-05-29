"""core/voice_gallery_store.py — P0.6.4: VoiceGalleryStore.

Owns two pipeline.py module globals:
  _voice_gallery       dict[str, Any]   — per-pid mean L2-normalized voice embedding
  _voice_gallery_sizes dict[str, int]   — per-pid sample count (profile-strength gating)

ATOMICITY INVARIANT: `set_gallery` updates both dicts under a single lock acquisition.
Readers must never see a stale size paired with an old embedding.  All dict-dict paired
writes go through `set_gallery` — no direct access to the internal dicts outside this class.

Contract (inherited from Store base):
  - All mutation methods are async and acquire self._lock.
  - peek_* methods are sync, no lock (single-thread asyncio safe).
  - reset() is sync — called by pytest autouse fixture outside the event loop.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

from typing import Any, Callable, Optional

from core.store_base import Store


class VoiceGalleryStore(Store):
    """Single owner of _voice_gallery and _voice_gallery_sizes."""

    def __init__(self) -> None:
        super().__init__()
        self._voice_gallery: dict[str, Any] = {}
        self._voice_gallery_sizes: dict[str, int] = {}

    def reset(self) -> None:
        self._voice_gallery.clear()
        self._voice_gallery_sizes.clear()

    # ── Pair writes (atomicity invariant) ────────────────────────────────────

    async def set_gallery(self, pid: str, mean_emb: Any, count: int) -> None:
        """Atomic paired write — both dicts updated under one lock."""
        async with self._lock:
            self._voice_gallery[pid] = mean_emb
            self._voice_gallery_sizes[pid] = count

    async def pop_gallery(self, pid: str) -> None:
        """Remove a person's gallery entry from both dicts atomically."""
        async with self._lock:
            self._voice_gallery.pop(pid, None)
            self._voice_gallery_sizes.pop(pid, None)

    async def clear(self) -> None:
        """Factory-reset both dicts atomically."""
        async with self._lock:
            self._voice_gallery.clear()
            self._voice_gallery_sizes.clear()

    # ── Bulk load (boot-time) ────────────────────────────────────────────────

    async def load_bulk(
        self,
        gallery_dict: dict[str, Any],
        sizes_dict: dict[str, int],
    ) -> None:
        """Bulk-populate both dicts from DB at process startup."""
        async with self._lock:
            self._voice_gallery.update(gallery_dict)
            self._voice_gallery_sizes.update(sizes_dict)

    # ── Dream-loop reconciliation ────────────────────────────────────────────

    async def reconcile(
        self,
        fresh_sizes: dict[str, int],
        load_profile_fn: Callable[[str], Optional[Any]],
    ) -> int:
        """Rebuild divergent pids.  Returns the count of pids reconciled.

        Called from _dream_loop (Obs 1) to repair out-of-process deletes.
        `load_profile_fn` is typically db.load_voice_profile_for (callable, not coroutine).
        """
        async with self._lock:
            divergent = [
                pid
                for pid in set(self._voice_gallery_sizes) | set(fresh_sizes)
                if self._voice_gallery_sizes.get(pid) != fresh_sizes.get(pid)
            ]
            if not divergent:
                return 0
            self._voice_gallery_sizes.clear()
            self._voice_gallery_sizes.update(fresh_sizes)
            for pid in divergent:
                prof = load_profile_fn(pid)
                if prof is None:
                    self._voice_gallery.pop(pid, None)
                else:
                    self._voice_gallery[pid] = prof
            return len(divergent)

    # ── Sync peek / read methods (no lock) ───────────────────────────────────

    def peek_gallery(self, pid: str) -> Optional[Any]:
        return self._voice_gallery.get(pid)

    def peek_size(self, pid: str, default: int = 0) -> int:
        return self._voice_gallery_sizes.get(pid, default)

    def peek_all_gallery(self) -> dict[str, Any]:
        """Return a shallow copy — safe for passing as `voice_gallery` arg."""
        return dict(self._voice_gallery)

    def peek_all_sizes(self) -> dict[str, int]:
        return dict(self._voice_gallery_sizes)

    def peek_len(self) -> int:
        return len(self._voice_gallery)

    def peek_pids(self) -> list[str]:
        return list(self._voice_gallery.keys())
