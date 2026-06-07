"""Behavioral test for the vision-watchdog clock-consistency fix (Canary #2 / latency D1).

Drives the REAL `_vision_watchdog_loop` with a heartbeat written via the REAL write path
using the production monotonic clock, then asserts the watchdog does NOT spuriously detect
staleness. This MUST fail on the pre-fix `_now = time.time()` code (staleness ≈ 1.78e9 →
restart loop every poll) and pass on the fixed `_now = time.monotonic()` code.

Why a NEW test is mandatory (spec §3 Layer 1 D1 item 1): the existing
`test_p0_r3_vision_loop_watchdog.py::...anchor_2_stale_triggers_restart_OR_persists` seeds
the heartbeat with `time.time()` AND re-implements the staleness check with a test-local
clock — internally consistent, so it was GREEN while production was broken. It is blind to
the clock-mismatch by construction. This test uses the real production write/read clocks.

Spec: tests/pipeline_latency_fix_spec.md §2 D1.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import asyncio
import time

import pytest


def test_vision_watchdog_no_spurious_stale_with_monotonic_heartbeat(monkeypatch):
    """Fresh monotonic heartbeat → the real watchdog loop must NOT trigger a restart.

    Fail-on-revert: with `:2594 _now = time.time()`, staleness = time.time() − monotonic
    ≈ 1.78e9 ≫ VISION_WATCHDOG_STALE_THRESHOLD_SECS on every poll → restart fires → assert fails.
    """
    import pipeline as _pl
    import runtime.vision_loop as _vl  # P1.A1 SP-6.3: _vision_watchdog_loop + _restart_vision_task relocated here
    import core.config as _cfg

    _pl._pipeline_state_store.reset()
    # REAL write path, production clock (monotonic) — exactly what :2845 writes.
    asyncio.run(_pl._pipeline_state_store.set_vision_heartbeat(time.monotonic()))

    restart_called = {"count": 0}

    async def _fake_restart():
        restart_called["count"] += 1

    monkeypatch.setattr(_vl, "_restart_vision_task", _fake_restart)
    # Poll fast so multiple real iterations run inside the short drive window.
    monkeypatch.setattr(_cfg, "VISION_WATCHDOG_INTERVAL_SECS", 0.02, raising=False)

    async def _drive():
        # _vision_watchdog_loop is `while True:` — drive it briefly, then cancel.
        try:
            await asyncio.wait_for(_vl._vision_watchdog_loop(), timeout=0.3)
        except asyncio.TimeoutError:
            pass

    asyncio.run(_drive())

    assert restart_called["count"] == 0, (
        f"Vision watchdog spuriously detected staleness {restart_called['count']}x against a "
        "FRESH monotonic heartbeat. The :2594 read clock is wall-clock — "
        "time.time() − time.monotonic() ≈ 1.78e9 ≫ threshold on every poll, the Canary #2 "
        "GPU-thrash bug. The staleness `now` MUST be time.monotonic()."
    )


def test_vision_watchdog_detects_genuinely_stale_monotonic_heartbeat(monkeypatch):
    """Sanity (the watchdog still WORKS): a genuinely-stale monotonic heartbeat
    (older than the threshold) DOES trigger exactly one restart. Guards against a
    'fix' that simply disables the watchdog.
    """
    import pipeline as _pl
    import runtime.vision_loop as _vl  # P1.A1 SP-6.3: _vision_watchdog_loop + _restart_vision_task relocated here
    import core.config as _cfg

    _pl._pipeline_state_store.reset()
    threshold = _cfg.VISION_WATCHDOG_STALE_THRESHOLD_SECS
    # A monotonic heartbeat older than the threshold (still on the monotonic scale).
    asyncio.run(_pl._pipeline_state_store.set_vision_heartbeat(time.monotonic() - threshold - 100.0))

    restart_called = {"count": 0}

    async def _fake_restart():
        restart_called["count"] += 1
        # Advance the heartbeat so the next poll sees it fresh (mirror real restart success).
        await _pl._pipeline_state_store.set_vision_heartbeat(time.monotonic())

    monkeypatch.setattr(_vl, "_restart_vision_task", _fake_restart)
    monkeypatch.setattr(_cfg, "VISION_WATCHDOG_INTERVAL_SECS", 0.02, raising=False)

    async def _drive():
        try:
            await asyncio.wait_for(_vl._vision_watchdog_loop(), timeout=0.3)
        except asyncio.TimeoutError:
            pass

    asyncio.run(_drive())

    assert restart_called["count"] >= 1, (
        "Vision watchdog failed to detect a genuinely-stale (monotonic) heartbeat — "
        "the fix must keep the watchdog functional, not disable it."
    )


def test_vision_watchdog_loop_uses_monotonic_read(monkeypatch):
    """Source belt-and-braces: the watchdog staleness `now` is time.monotonic(), not
    time.time() (fail-on-revert at the source layer too)."""
    from pathlib import Path
    import ast

    # P1.A1 SP-6.3: _vision_watchdog_loop relocated to runtime/vision_loop.py.
    src = (Path(__file__).resolve().parent.parent / "runtime" / "vision_loop.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_vision_watchdog_loop"
    )
    # Find `_now = <call>` and assert the call is time.monotonic(), not time.time().
    now_assigns = [
        node for node in ast.walk(fn)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_now" for t in node.targets)
    ]
    assert now_assigns, "_vision_watchdog_loop must assign `_now`"
    for a in now_assigns:
        call = a.value
        assert (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "monotonic"
        ), "watchdog `_now` must be time.monotonic() (staleness is elapsed-duration math)"
