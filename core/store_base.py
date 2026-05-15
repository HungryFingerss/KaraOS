"""core/store_base.py — P0.6.1: Abstract base for module-global state Stores.

Pattern banked from P0.7 SessionStore — generalized for P0.6's 7 Stores.

Contract every subclass MUST honour:
- _lock: asyncio.Lock           held for every mutation method
- reset() -> None               sync; called by autouse fixture between tests
- peek_* methods                sync, no lock (single-thread asyncio safe)
- all mutation methods          async, acquire self._lock
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")


class Store(ABC, Generic[T]):
    """Abstract base for module-global state Stores.

    Subclasses MUST:
    1. Define typed state (dataclass / dict / set / scalar) on self.
    2. Implement reset() — called by the autouse fixture between tests.
       The @abstractmethod decorator causes TypeError at instantiation if
       reset() is missing (auditor M5 fix: structural enforcement).
    3. Implement mutation methods as async, each acquiring self._lock.
    4. Implement peek_* read methods as sync (no lock — single-thread
       asyncio safe under the same contract as SessionStore.peek_snapshot).
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    @abstractmethod
    def reset(self) -> None:
        """Reset to initial state.

        Sync because pytest fixtures run outside the event loop.
        Called by _reset_pipeline_state_between_tests autouse fixture.
        """
