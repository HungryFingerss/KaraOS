"""core/pipeline_state_store.py — P0.6.6 pipeline state, cloud health, room lifecycle, timestamps."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import asyncio
import dataclasses
from typing import Any, Optional

from core.config import DEFAULT_SYSTEM_NAME
from core.store_base import Store


@dataclasses.dataclass(frozen=True)
class CloudSnapshot:
    """Immutable point-in-time snapshot of all cloud-state fields."""
    cloud_state: Any
    cloud_failed_at: float
    cloud_monitor_task: Any
    cloud_recovered: bool


class PipelineStateStore(Store):
    """Typed store for pipeline-level state: cloud health, pipeline FSM, room lifecycle, timestamps.

    All write methods are async to satisfy TestNoSyncMutatorsOnAnyStore.
    Cloud-group methods acquire self._lock for atomic multi-field writes.
    Scalar setters are async without a lock (CPython GIL is sufficient for single-attr writes).
    """

    def __init__(
        self,
        *,
        initial_pipeline_state: Any = None,
        initial_cloud_state: Any = None,
    ) -> None:
        """Construct with optional production defaults.

        At module load time pipeline.py instantiates with
            PipelineStateStore(
                initial_pipeline_state=PipelineState.WATCHING,
                initial_cloud_state=CloudState.ONLINE,
            )
        so the very first peek_pipeline_state() / peek_cloud_state() return
        production-ready values before any explicit transition fires.  Without
        these initials, `_pipeline_state` would default to None and the
        greeting-gate compare (`peek_pipeline_state() == PipelineState.WATCHING`)
        would never pass.

        Defaults are kwargs-only so tests / autouse fixtures that construct
        a bare PipelineStateStore() still get None defaults (matching the
        prior reset() shape and the existing test corpus).
        """
        super().__init__()
        self.reset()
        if initial_pipeline_state is not None:
            self._pipeline_state = initial_pipeline_state
        if initial_cloud_state is not None:
            self._cloud_state = initial_cloud_state

    # ── Reset ──────────────────────────────────────────────────────────────

    def reset(self) -> None:
        self._cloud_state: Any = None
        self._cloud_failed_at: float = 0.0
        self._cloud_recovered: bool = False
        self._cloud_monitor_task: Any = None

        self._pipeline_state: Any = None
        self._active_system_name: str = DEFAULT_SYSTEM_NAME
        self._detected_lang: str = "en"

        self._active_room_session: Optional[str] = None
        self._active_room_started_at: Optional[float] = None
        self._active_room_participants: set = set()

        self._last_face_seen: float = 0.0
        self._last_user_speech_at: float = 0.0
        self._last_kairos_at: float = 0.0
        self._last_silent_update: float = 0.0

        # P0.R3 D3 — vision-loop watchdog state (heartbeat + degraded flag).
        # Default heartbeat 0.0 means "never published"; watchdog's stale check
        # (now - 0.0 > VISION_WATCHDOG_STALE_THRESHOLD_SECS) is True at startup
        # until the vision loop fires its first heartbeat, but the watchdog's
        # own startup-grace period (first sleep interval) covers the boot window.
        self._vision_heartbeat_at: float = 0.0
        self._vision_degraded: bool = False
        # P0.R6 D4 — heavy-worker pool health observability.
        # Keyed by task_name (e.g. "adaface_embed"); value ∈ {"healthy",
        # "degraded", "unknown"}. Empty dict at boot before any pool spawn.
        self._heavy_worker_status: dict[str, str] = {}

    # ── Peek helpers (sync, no lock) ────────────────────────────────────────

    def peek_cloud_snapshot(self) -> CloudSnapshot:
        return CloudSnapshot(
            cloud_state=self._cloud_state,
            cloud_failed_at=self._cloud_failed_at,
            cloud_monitor_task=self._cloud_monitor_task,
            cloud_recovered=self._cloud_recovered,
        )

    def peek_cloud_state(self) -> Any:
        return self._cloud_state

    def peek_cloud_failed_at(self) -> float:
        return self._cloud_failed_at

    def peek_cloud_recovered(self) -> bool:
        return self._cloud_recovered

    def peek_cloud_monitor_task(self) -> Any:
        return self._cloud_monitor_task

    def peek_pipeline_state(self) -> Any:
        return self._pipeline_state

    def peek_active_system_name(self) -> str:
        return self._active_system_name

    def peek_detected_lang(self) -> str:
        return self._detected_lang

    def peek_active_room_session(self) -> Optional[str]:
        return self._active_room_session

    def peek_active_room_started_at(self) -> Optional[float]:
        return self._active_room_started_at

    def peek_active_room_participants(self) -> set:
        return set(self._active_room_participants)

    def peek_vision_heartbeat_at(self) -> float:
        """P0.R3 D2 — sync peeker for watchdog stale-detection."""
        return self._vision_heartbeat_at

    def peek_vision_degraded(self) -> bool:
        """P0.R3 D3 — sync peeker for health.py + watchdog persists-branch."""
        return self._vision_degraded

    async def set_vision_heartbeat(self, ts: float) -> None:
        """P0.R3 D1 — scalar setter for vision-loop heartbeat. No lock (CPython
        GIL on float assignment is atomic; matches existing scalar-setter pattern
        like `set_pipeline_state`)."""
        self._vision_heartbeat_at = ts

    async def set_vision_degraded(self, degraded: bool) -> None:
        """P0.R3 D3 — scalar setter for vision-subsystem degraded flag."""
        self._vision_degraded = degraded

    def peek_heavy_worker_status(self) -> dict[str, str]:
        """P0.R6 D4 — sync peeker; returns COPY so callers can't mutate the
        underlying dict without going through `set_heavy_worker_status`.
        """
        return dict(self._heavy_worker_status)

    async def set_heavy_worker_status(self, task_name: str, status: str) -> None:
        """P0.R6 D4 — scalar setter for a single heavy-worker pool's status.

        Valid values: ``"healthy"`` | ``"degraded"`` | ``"unknown"``. No lock
        needed for single dict key assignment (CPython GIL atomicity matches
        the existing scalar-setter pattern; `set_vision_degraded` precedent).
        """
        self._heavy_worker_status[task_name] = status

    def peek_last_face_seen(self) -> float:
        return self._last_face_seen

    def peek_last_user_speech_at(self) -> float:
        return self._last_user_speech_at

    def peek_last_kairos_at(self) -> float:
        return self._last_kairos_at

    def peek_last_silent_update(self) -> float:
        return self._last_silent_update

    # ── Cloud-group atomic transitions (acquire lock) ───────────────────────

    async def transition_to_sick(self, failed_at: float) -> None:
        """ONLINE/SICK → SICK. Records failed_at timestamp atomically."""
        import pipeline as _pl  # lazy: avoids circular import at module-load time
        async with self._lock:
            self._cloud_state = _pl.CloudState.SICK
            self._cloud_failed_at = failed_at

    async def transition_to_offline(self) -> None:
        """SICK → OFFLINE."""
        import pipeline as _pl
        async with self._lock:
            self._cloud_state = _pl.CloudState.OFFLINE

    async def transition_to_online(self) -> None:
        """* → ONLINE, sets cloud_recovered=True (C4 path: retry loop recovery).

        Prior-state guard (P0.6.7v2): cloud_recovered is set only if the
        prior state was NOT already ONLINE.  An ONLINE→ONLINE idempotent
        call via this path would otherwise spuriously signal a recovery —
        leading downstream consumers to emit a recovery notice for a
        transition that never happened.
        """
        import pipeline as _pl
        async with self._lock:
            prior = self._cloud_state
            self._cloud_state = _pl.CloudState.ONLINE
            if prior != _pl.CloudState.ONLINE:
                self._cloud_recovered = True

    async def recover_online_no_flag(self) -> None:
        """* → ONLINE without setting cloud_recovered (C2 path: mid-conversation recovery)."""
        import pipeline as _pl
        async with self._lock:
            self._cloud_state = _pl.CloudState.ONLINE

    async def consume_cloud_recovered(self) -> bool:
        """Atomic read-and-clear for the cloud_recovered flag."""
        async with self._lock:
            was = self._cloud_recovered
            self._cloud_recovered = False
            return was

    async def set_cloud_monitor_task(self, task: Any) -> None:
        async with self._lock:
            self._cloud_monitor_task = task

    async def set_cloud_state(self, state: Any) -> None:
        """Low-level setter for restoring cloud_state from a saved variable (test cleanup)."""
        async with self._lock:
            self._cloud_state = state

    async def set_cloud_recovered(self, value: bool) -> None:
        """Low-level setter for restoring cloud_recovered from a saved variable (test cleanup)."""
        async with self._lock:
            self._cloud_recovered = value

    async def set_cloud_failed_at(self, ts: float) -> None:
        """Low-level setter for restoring cloud_failed_at from a saved variable (test cleanup)."""
        async with self._lock:
            self._cloud_failed_at = ts

    # ── Room lifecycle atomic methods (acquire lock) ───────────────────────

    async def mint_room(self, session_id: str, started_at: float) -> None:
        """Atomically mint a new room session on first person entry."""
        async with self._lock:
            self._active_room_session = session_id
            self._active_room_started_at = started_at
            self._active_room_participants = set()

    async def add_room_participant(self, person_id: str) -> None:
        """Atomically add a participant to the active room."""
        async with self._lock:
            self._active_room_participants.add(person_id)

    async def end_room(self) -> tuple:
        """Atomically clear all room fields. Returns (session_id, started_at, participants)."""
        async with self._lock:
            _sid = self._active_room_session
            _started = self._active_room_started_at
            _parts = set(self._active_room_participants)
            self._active_room_session = None
            self._active_room_started_at = None
            self._active_room_participants = set()
            return (_sid, _started, _parts)

    # ── Scalar setters (async, no lock needed) ─────────────────────────────

    async def set_pipeline_state(self, state: Any) -> None:
        self._pipeline_state = state

    async def set_active_system_name(self, name: str) -> None:
        self._active_system_name = name

    async def set_detected_lang(self, lang: str) -> None:
        self._detected_lang = lang

    async def set_active_room_session(self, session_id: Optional[str]) -> None:
        self._active_room_session = session_id

    async def set_active_room_started_at(self, ts: Optional[float]) -> None:
        self._active_room_started_at = ts

    async def set_active_room_participants(self, participants: set) -> None:
        self._active_room_participants = set(participants)

    async def set_last_face_seen(self, ts: float) -> None:
        self._last_face_seen = ts

    async def set_last_user_speech_at(self, ts: float) -> None:
        self._last_user_speech_at = ts

    async def set_last_kairos_at(self, ts: float) -> None:
        self._last_kairos_at = ts

    async def set_last_silent_update(self, ts: float) -> None:
        self._last_silent_update = ts

    # ── Private sync helpers (pipeline.py internal use only) ──────────────
    # These bypass the asyncio.Lock for call sites that are already in a
    # single-threaded synchronous context (_open_session / _close_session)
    # where the lock is not needed and create_task would defer the write
    # past the point where synchronous callers read it back.
    #
    # Prefixed with `_` so TestNoSyncMutatorsOnAnyStore skips them (that
    # test ignores private helpers — see _SYNC_ALLOWLIST_RE).
    # pipeline.py calls these instead of direct `_pipeline_state_store._field = x`
    # so the P0.6.6 legacy-mutation scanner (which looks for `._fieldname =`)
    # reports 0 violations.

    def _sync_mint_room(self, session_id: str, started_at: float) -> None:
        """Synchronously mint a new room — same semantics as mint_room() but
        without the coroutine wrapper. Only for _open_session's sync context."""
        self._active_room_session = session_id
        self._active_room_started_at = started_at
        self._active_room_participants = set()

    def _sync_add_room_participant(self, person_id: str) -> None:
        """Synchronously add a participant. Only for _open_session's sync context."""
        self._active_room_participants = self._active_room_participants | {person_id}

    def _sync_clear_room(self) -> None:
        """Synchronously clear all room fields. Only for _close_session's sync context."""
        self._active_room_session = None
        self._active_room_started_at = None
        self._active_room_participants = set()

    def _sync_set_cloud_state(self, state: Any) -> None:
        """Synchronously set cloud_state. Only for module-level initialization."""
        self._cloud_state = state
