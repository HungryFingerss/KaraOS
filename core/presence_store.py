"""core/presence_store.py — P0.6.2: Store for _persons_in_frame."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from core.store_base import Store


@dataclass(slots=True)
class PresenceEntry:
    name: str
    last_seen: float
    last_recognized_at: float
    conf: float
    source: str  # "face" or "voice"


@dataclass(frozen=True, slots=True)
class PresenceSnapshot:
    person_id: str
    name: str
    last_seen: float
    last_recognized_at: float
    conf: float
    source: str


class PresenceStore(Store):
    """Single owner of _persons_in_frame state."""

    def __init__(self) -> None:
        super().__init__()
        self._data: dict[str, PresenceEntry] = {}

    def reset(self) -> None:
        self._data.clear()

    # ------------------------------------------------------------------
    # Mutations (async — acquire lock)
    # ------------------------------------------------------------------

    async def upsert_face_recognition(
        self,
        person_id: str,
        name: str,
        conf: float,
        now: float,
    ) -> None:
        async with self._lock:
            if person_id in self._data:
                e = self._data[person_id]
                e.last_seen = now
                e.last_recognized_at = now
                e.conf = conf
                e.source = "face"
                e.name = name
            else:
                self._data[person_id] = PresenceEntry(
                    name=name,
                    last_seen=now,
                    last_recognized_at=now,
                    conf=conf,
                    source="face",
                )

    async def upsert_voice_recognition(
        self,
        person_id: str,
        name: str,
        conf: float,
        now: float,
    ) -> None:
        async with self._lock:
            if person_id in self._data:
                e = self._data[person_id]
                e.last_seen = now
                e.conf = conf
                e.source = "voice"
                e.name = name
            else:
                self._data[person_id] = PresenceEntry(
                    name=name,
                    last_seen=now,
                    last_recognized_at=0.0,
                    conf=conf,
                    source="voice",
                )

    async def touch_last_seen(self, person_id: str, now: float) -> None:
        async with self._lock:
            if person_id in self._data:
                self._data[person_id].last_seen = now

    async def update_name(self, person_id: str, name: str) -> None:
        async with self._lock:
            if person_id in self._data:
                self._data[person_id].name = name

    async def remove(self, person_id: str) -> None:
        async with self._lock:
            self._data.pop(person_id, None)

    async def prune_stale(self, before_ts: float) -> list[str]:
        """Remove entries whose last_seen < before_ts. Returns pruned pids."""
        async with self._lock:
            stale = [
                pid
                for pid, e in self._data.items()
                if e.last_seen < before_ts
            ]
            for pid in stale:
                del self._data[pid]
            return stale

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()

    # ------------------------------------------------------------------
    # Reads (sync — no lock; single-thread asyncio safe)
    # ------------------------------------------------------------------

    def __contains__(self, person_id: object) -> bool:
        return person_id in self._data

    def peek_snapshot(self, person_id: str) -> Optional[PresenceSnapshot]:
        e = self._data.get(person_id)
        if e is None:
            return None
        return PresenceSnapshot(
            person_id=person_id,
            name=e.name,
            last_seen=e.last_seen,
            last_recognized_at=e.last_recognized_at,
            conf=e.conf,
            source=e.source,
        )

    def peek_all_snapshots(self) -> list[PresenceSnapshot]:
        return [
            PresenceSnapshot(
                person_id=pid,
                name=e.name,
                last_seen=e.last_seen,
                last_recognized_at=e.last_recognized_at,
                conf=e.conf,
                source=e.source,
            )
            for pid, e in self._data.items()
        ]

    def peek_pids(self) -> list[str]:
        return list(self._data.keys())

    def peek_name(self, person_id: str, default: str = "") -> str:
        e = self._data.get(person_id)
        return e.name if e is not None else default

    def peek_conf(self, person_id: str, default: float = 0.0) -> float:
        e = self._data.get(person_id)
        return e.conf if e is not None else default

    def peek_last_seen(self, person_id: str, default: float = 0.0) -> float:
        e = self._data.get(person_id)
        return e.last_seen if e is not None else default

    def peek_last_recognized_at(self, person_id: str, default: float = 0.0) -> float:
        e = self._data.get(person_id)
        return e.last_recognized_at if e is not None else default

    def peek_source(self, person_id: str, default: str = "") -> str:
        e = self._data.get(person_id)
        return e.source if e is not None else default

    def peek_count(self) -> int:
        return len(self._data)
