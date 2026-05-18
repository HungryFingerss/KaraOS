"""core/per_person_agent_store.py — P0.6.4: PerPersonAgentStore.

Owns three pipeline.py module globals:
  _emotion_agents       dict[str, EmotionAgent]  — per-pid emotion agent instances
  _sessions_started     set[str]                 — pids with at least one started session
  _ambient_wake_pending set[str]                 — pids whose background wake signal is in-flight

LIFECYCLE NOTE: `pop_emotion_agent` is the correct call on _close_session — NOT just
clearing state.  Re-opened sessions get a fresh EmotionAgent on first emotion-detection
call in conversation_turn.  This mirrors P0.6.2 PresenceStore.remove() semantics.

DEBOUNCE INVARIANT: `discard_ambient_wake(pid)` must precede every continue/return on the
greeting path in _background_vision_loop.  Source-inspection test in
test_pipeline_latency.py (TestReleaseCompactInFinallyBlock pattern) guards this.

Contract (inherited from Store base):
  - All mutation methods are async and acquire self._lock.
  - peek_* and is_* methods are sync, no lock (single-thread asyncio safe).
  - reset() is sync — called by pytest autouse fixture outside the event loop.
"""
from __future__ import annotations

from typing import Any, Optional

from core.store_base import Store


class PerPersonAgentStore(Store):
    """Single owner of _emotion_agents, _sessions_started, and _ambient_wake_pending."""

    def __init__(self) -> None:
        super().__init__()
        self._emotion_agents: dict[str, Any] = {}
        self._sessions_started: set[str] = set()
        self._ambient_wake_pending: set[str] = set()

    def reset(self) -> None:
        self._emotion_agents.clear()
        self._sessions_started.clear()
        self._ambient_wake_pending.clear()

    # ── Emotion agent mutations ───────────────────────────────────────────────

    async def set_emotion_agent(self, pid: str, agent: Any) -> None:
        async with self._lock:
            self._emotion_agents[pid] = agent

    async def pop_emotion_agent(self, pid: str) -> None:
        """Remove (not reset) the agent so re-entry creates a fresh one."""
        async with self._lock:
            self._emotion_agents.pop(pid, None)

    async def clear_emotion_agents(self) -> None:
        async with self._lock:
            self._emotion_agents.clear()

    # ── Sessions-started mutations ────────────────────────────────────────────

    async def add_session_started(self, pid: str) -> None:
        async with self._lock:
            self._sessions_started.add(pid)

    async def discard_session_started(self, pid: str) -> None:
        async with self._lock:
            self._sessions_started.discard(pid)

    async def clear_sessions_started(self) -> None:
        async with self._lock:
            self._sessions_started.clear()

    # ── Ambient-wake mutations ─────────────────────────────────────────────────

    async def add_ambient_wake(self, pid: str) -> None:
        async with self._lock:
            self._ambient_wake_pending.add(pid)

    async def discard_ambient_wake(self, pid: str) -> None:
        """Consume the debounce signal.  Must be called before every continue/return
        on the greeting path so the pid never stays stuck in the pending set."""
        async with self._lock:
            self._ambient_wake_pending.discard(pid)

    async def clear_ambient_wake(self) -> None:
        async with self._lock:
            self._ambient_wake_pending.clear()

    # ── Sync peek / predicate methods (no lock) ───────────────────────────────

    def peek_emotion_agent(self, pid: str) -> Optional[Any]:
        return self._emotion_agents.get(pid)

    def peek_all_emotion_agents(self) -> dict[str, Any]:
        """Return a reference to the internal dict — safe for iteration under single-thread asyncio."""
        return self._emotion_agents

    def peek_emotion_agent_pids(self) -> list[str]:
        return list(self._emotion_agents.keys())

    def is_session_started(self, pid: str) -> bool:
        return pid in self._sessions_started

    def peek_sessions_started(self) -> set[str]:
        return set(self._sessions_started)

    def is_ambient_wake_pending(self, pid: str) -> bool:
        return pid in self._ambient_wake_pending

    def peek_ambient_wake_pending(self) -> set[str]:
        return set(self._ambient_wake_pending)
