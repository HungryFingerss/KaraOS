"""core/track_store.py — P0.6.2: Store for track-keyed globals.

Unifies _unrecognized_tracks, _unrecognized_embeddings,
_stranger_track_map, and _track_identity into a single TrackEntry
per SORT track_id.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

from core.store_base import Store


@dataclass(slots=True)
class TrackEntry:
    last_seen: float = 0.0            # from _unrecognized_tracks
    embedding: Any = None             # np.ndarray | None — from _unrecognized_embeddings
    stranger_pid: Optional[str] = None   # from _stranger_track_map
    identity_pid: Optional[str] = None  # from _track_identity


@dataclass(frozen=True, slots=True)
class TrackSnapshot:
    track_id: Any  # int or str — SORT track_id
    last_seen: float
    embedding: Any
    stranger_pid: Optional[str]
    identity_pid: Optional[str]


class TrackStore(Store):
    """Single owner of all four track-keyed dicts."""

    def __init__(self) -> None:
        super().__init__()
        self._data: dict[Any, TrackEntry] = {}

    def reset(self) -> None:
        self._data.clear()

    # ------------------------------------------------------------------
    # Mutations (async — acquire lock)
    # ------------------------------------------------------------------

    async def mark_unrecognized(self, track_id: Any, now: float) -> None:
        async with self._lock:
            if track_id not in self._data:
                self._data[track_id] = TrackEntry()
            self._data[track_id].last_seen = now

    async def set_embedding(self, track_id: Any, embedding: Any) -> None:
        async with self._lock:
            if track_id not in self._data:
                self._data[track_id] = TrackEntry()
            self._data[track_id].embedding = embedding

    async def mint_stranger(self, track_id: Any, stranger_pid: str) -> None:
        async with self._lock:
            if track_id not in self._data:
                self._data[track_id] = TrackEntry()
            self._data[track_id].stranger_pid = stranger_pid

    async def bind_identity(self, track_id: Any, person_id: str) -> None:
        async with self._lock:
            if track_id not in self._data:
                self._data[track_id] = TrackEntry()
            self._data[track_id].identity_pid = person_id

    async def remove_track(self, track_id: Any) -> None:
        async with self._lock:
            self._data.pop(track_id, None)

    async def prune_stale(self, before_ts: float) -> list[Any]:
        """Remove entries where last_seen > 0 and last_seen < before_ts."""
        async with self._lock:
            stale = [
                tid
                for tid, e in self._data.items()
                if e.last_seen > 0 and e.last_seen < before_ts
            ]
            for tid in stale:
                del self._data[tid]
            return stale

    async def prune_to_active_tids(self, active_tids: set) -> list[Any]:
        """Remove entries whose track_id is not in active_tids."""
        async with self._lock:
            inactive = [tid for tid in self._data if tid not in active_tids]
            for tid in inactive:
                del self._data[tid]
            return inactive

    async def prune_for_session_close(self, person_id: str) -> list[Any]:
        """Remove entries where stranger_pid == person_id."""
        async with self._lock:
            to_remove = [
                tid
                for tid, e in self._data.items()
                if e.stranger_pid == person_id
            ]
            for tid in to_remove:
                del self._data[tid]
            return to_remove

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()

    # ------------------------------------------------------------------
    # Reads (sync — no lock; single-thread asyncio safe)
    # ------------------------------------------------------------------

    def __contains__(self, track_id: object) -> bool:
        return track_id in self._data

    def peek_snapshot(self, track_id: Any) -> Optional[TrackSnapshot]:
        e = self._data.get(track_id)
        if e is None:
            return None
        return TrackSnapshot(
            track_id=track_id,
            last_seen=e.last_seen,
            embedding=e.embedding,
            stranger_pid=e.stranger_pid,
            identity_pid=e.identity_pid,
        )

    def peek_all_track_ids(self) -> list[Any]:
        return list(self._data.keys())

    def peek_all_snapshots(self) -> list[TrackSnapshot]:
        return [
            TrackSnapshot(
                track_id=tid,
                last_seen=e.last_seen,
                embedding=e.embedding,
                stranger_pid=e.stranger_pid,
                identity_pid=e.identity_pid,
            )
            for tid, e in self._data.items()
        ]

    def peek_stranger_pid(self, track_id: Any, default: Optional[str] = None) -> Optional[str]:
        e = self._data.get(track_id)
        return e.stranger_pid if e is not None else default

    def peek_identity(self, track_id: Any, default: Optional[str] = None) -> Optional[str]:
        e = self._data.get(track_id)
        return e.identity_pid if e is not None else default

    def peek_embedding(self, track_id: Any, default: Any = None) -> Any:
        e = self._data.get(track_id)
        return e.embedding if e is not None else default

    def peek_last_seen(self, track_id: Any, default: float = 0.0) -> float:
        e = self._data.get(track_id)
        return e.last_seen if e is not None else default

    def peek_tracks_for_person(self, person_id: str) -> list[Any]:
        """Return track_ids where identity_pid == person_id."""
        return [tid for tid, e in self._data.items() if e.identity_pid == person_id]

    def peek_track_for_stranger_pid(self, stranger_pid: str) -> Optional[Any]:
        """Return first track_id whose stranger_pid matches."""
        for tid, e in self._data.items():
            if e.stranger_pid == stranger_pid:
                return tid
        return None

    def peek_active_unrecognized(self) -> list[Any]:
        """Return track_ids that have a last_seen timestamp (unrecognized tracks)."""
        return [tid for tid, e in self._data.items() if e.last_seen > 0]

    def peek_count(self) -> int:
        return len(self._data)
