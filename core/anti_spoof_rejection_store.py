"""core/anti_spoof_rejection_store.py — P0.S1 MED 5.

Per-track anti-spoof rejection log for the watchdog burst-alert path (C2
contract). Plan v1 sketched this as a module-level dict in pipeline.py; Plan v2
MED 5 promotes to a `Store` subclass per the P0.6 discipline so the
legacy-global-progress ratchet stays at cap=0.

Single-thread-asyncio safety contract:
- record_rejection / pop are async (acquire lock)
- peek_count / reset are sync (no lock — single-thread asyncio safe under the
  same contract as TrackStore.peek_snapshot)

Per-track scope (NOT per-pid) because at progressive_enroll gate time the pid
may not exist yet — the SORT track_id is the only stable correlation key.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

from typing import Optional

from core.store_base import Store


class AntiSpoofRejectionStore(Store[dict[str, list[float]]]):
    """Per-track anti-spoof rejection log for burst-threshold detection."""

    def __init__(self) -> None:
        super().__init__()
        self._log: dict[str, list[float]] = {}

    async def record_rejection(
        self, track_id: str, now: float, window_secs: float
    ) -> int:
        """Append a rejection at `now`; prune entries older than now-window_secs.

        Returns the post-prune count for this track. Plan v2 §14b.1 — the
        caller compares this return value against ANTI_SPOOF_BURST_THRESHOLD
        with EXACT EQUALITY (`count == THRESHOLD`, not `>=`) so the burst
        alert fires exactly once per burst.
        """
        async with self._lock:
            entries = self._log.setdefault(track_id, [])
            entries.append(now)
            cutoff = now - window_secs
            self._log[track_id] = [t for t in entries if t >= cutoff]
            return len(self._log[track_id])

    def peek_count(self, track_id: str, now: float, window_secs: float) -> int:
        """Sync read of current rejection count in window.

        No lock — single-thread asyncio safety per P0.6 contract. Used by the
        consumer side (watchdog dispatcher) to observe current burst state
        without taking a write lock.
        """
        entries = self._log.get(track_id, [])
        cutoff = now - window_secs
        return sum(1 for t in entries if t >= cutoff)

    async def pop(self, track_id: str) -> None:
        """Remove a track's rejection history.

        Called on track stale-prune (TrackStore.prune_stale fires) and on
        session close so a returning user starts with a fresh window.
        """
        async with self._lock:
            self._log.pop(track_id, None)

    def reset(self) -> None:
        """Required by Store ABC. Clear all rejection history.

        Called by autouse fixture between tests + factory reset.
        """
        self._log.clear()

    def peek_track_count(self) -> int:
        """Observability helper: number of tracks with any rejection history."""
        return len(self._log)
