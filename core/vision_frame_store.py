"""core/vision_frame_store.py — P0.6.7v2: VisionFrameStore.

Owns three pipeline.py module globals:
  _latest_vision_frame    np.ndarray | None  — last good frame from the background vision loop
  _latest_frame_time      float              — monotonic timestamp of that frame
  _vision_prev_det_count  int                — face count from previous frame (spike-detect)

PRODUCER-COPY INVARIANT (load-bearing):
The frame is a mutable numpy ndarray.  cv2.VideoCapture.read() may return a
buffer that is overwritten on the next .read() — meaning a stored reference
would race against the next camera frame, with consumers seeing torn pixels
or partially-overwritten arrays under load.

Producers MUST `.copy()` the frame before storing.  AST source-inspection
test in tests/test_vision_frame_store_producer_copy.py scans every call site
of `set_frame(...)` in pipeline.py and asserts `.copy()` appears in the same
expression.

Contract (inherited from Store base):
  - All mutation methods are async and acquire self._lock.
  - peek_* methods are sync, no lock (single-thread asyncio safe).
  - reset() is sync — called by pytest autouse fixture outside the event loop.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

from typing import Any, Optional

from core.store_base import Store


class VisionFrameStore(Store):
    """Single owner of _latest_vision_frame, _latest_frame_time, _vision_prev_det_count."""

    def __init__(self) -> None:
        super().__init__()
        # Delegate field initialization to reset() so AST inverse-check tests
        # attribute init-time writes to a single source (reset), mirroring
        # PipelineStateStore's pattern.
        self.reset()

    def reset(self) -> None:
        self._frame: Any = None
        self._frame_time: float = 0.0
        self._prev_det_count: int = 0

    # ── Mutations (async — acquire lock) ─────────────────────────────────

    async def set_frame(self, frame: Any, ts: float) -> None:
        """Atomically store (frame, ts).  Producer MUST pass a copied ndarray
        — the AST source-inspection test enforces `.copy()` at every call
        site in pipeline.py."""
        async with self._lock:
            self._frame = frame
            self._frame_time = ts

    async def clear_frame(self) -> None:
        async with self._lock:
            self._frame = None
            self._frame_time = 0.0

    async def set_prev_det_count(self, n: int) -> None:
        async with self._lock:
            self._prev_det_count = n

    # ── Private sync mutator (pipeline.py internal use only) ─────────────
    # Used by _expire_stale_sessions which runs in a synchronous context
    # where create_task would defer the write past the point where
    # synchronous callers (the same function continuing past the call) read
    # it back.  Mirrors the PipelineStateStore._sync_* helper pattern.

    def _sync_set_prev_det_count(self, n: int) -> None:
        """Synchronously set _vision_prev_det_count. Only for sync call sites."""
        self._prev_det_count = n

    # ── Reads (sync — no lock; single-thread asyncio safe) ───────────────

    def peek_frame(self) -> Any:
        return self._frame

    def peek_frame_time(self) -> float:
        return self._frame_time

    def peek_frame_if_fresh(self, max_age_secs: float, now: float) -> Any:
        """Return the frame iff it is younger than max_age_secs.

        `now` is supplied by the caller (typically time.monotonic()) — keeps
        the store free of time-source coupling and matches the Snapshot
        pattern's caller-provided-now contract.
        """
        if (now - self._frame_time) < max_age_secs:
            return self._frame
        return None

    def peek_prev_det_count(self) -> int:
        return self._prev_det_count
