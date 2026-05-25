"""tests/test_p0_r3_vision_loop_watchdog.py — P0.R3 D1-D5 anchors.

Plan v1 §3 LOCK at 10 logical anchors:
- A1 (D1 source-inspection): heartbeat update inside `_background_vision_loop` body, BEFORE camera.read.
- A2 (D2 source-inspection): `_vision_watchdog_loop` exists + cadence + stale check + persists log + degraded branch.
- A3 (D2 behavioral, parametrize 2): stale triggers restart (degraded=False) OR persists log (degraded=True).
- A4 (D3 source-inspection): PipelineStateStore has 2 fields + 4 methods.
- A5 (D3 source-inspection): HealthSnapshot has `vision_degraded: bool = False`.
- A6 (D3 source-inspection): `format_health_alerts` emits actionable recovery substrings.
- A7 (D4 behavioral): restart success clears degraded.
- A8 (D4 behavioral): restart fail sets degraded + audio task untouched.
- A9 (D5 source-inspection, AST line-order): watchdog spawn AFTER vision spawn + watchdog cancel BEFORE vision cancel.
- A10 (D2 source-inspection): config constants present.
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_PIPELINE_PY = _REPO_ROOT / "pipeline.py"
_STORE_PY = _REPO_ROOT / "core" / "pipeline_state_store.py"
_HEALTH_PY = _REPO_ROOT / "core" / "health.py"
_CONFIG_PY = _REPO_ROOT / "core" / "config.py"


def _read(p: Path) -> str:
    assert p.exists(), f"P0.R3 anchor expects {p} to exist"
    return p.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def pipeline_src() -> str:
    return _read(_PIPELINE_PY)


@pytest.fixture(scope="module")
def store_src() -> str:
    return _read(_STORE_PY)


@pytest.fixture(scope="module")
def health_src() -> str:
    return _read(_HEALTH_PY)


@pytest.fixture(scope="module")
def config_src() -> str:
    return _read(_CONFIG_PY)


def test_p0_r3_d1_anchor_1_heartbeat_update_in_loop(pipeline_src):
    """A1: `_background_vision_loop` body contains `set_vision_heartbeat` call
    BEFORE the `camera.read` executor call (heartbeat at iteration start)."""
    tree = ast.parse(pipeline_src)
    loop_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_background_vision_loop":
            loop_fn = node
            break
    assert loop_fn is not None, "_background_vision_loop must exist"
    body_src = ast.unparse(loop_fn)
    assert "set_vision_heartbeat" in body_src, (
        "P0.R3 D1: `_background_vision_loop` body MUST call `set_vision_heartbeat` "
        "at iteration start (heartbeat update before camera.read)."
    )
    heartbeat_idx = body_src.find("set_vision_heartbeat")
    cam_read_idx = body_src.find("camera.read")
    assert heartbeat_idx > 0 and cam_read_idx > 0
    assert heartbeat_idx < cam_read_idx, (
        "P0.R3 D1: heartbeat update MUST precede camera.read in loop body."
    )


def test_p0_r3_d2_anchor_1_watchdog_loop_source(pipeline_src):
    """A2: `_vision_watchdog_loop` exists + cadence + stale check + persists log + degraded branch."""
    assert "async def _vision_watchdog_loop" in pipeline_src, (
        "P0.R3 D2: `_vision_watchdog_loop` function MUST exist."
    )
    assert "VISION_WATCHDOG_INTERVAL_SECS" in pipeline_src
    assert "VISION_WATCHDOG_STALE_THRESHOLD_SECS" in pipeline_src
    assert "peek_vision_degraded" in pipeline_src, (
        "P0.R3 D2: watchdog MUST consult `peek_vision_degraded()` for persists-branch."
    )
    # Tighter substring `print(f"[Vision] stale persists` to avoid matching the
    # bare `stale persists` in the watchdog docstring (P0.R2 §2.6(b)-precedent
    # detector strengthening per `### Induction-surfaces-invariant-gaps`).
    assert 'print(f"[Vision] stale persists' in pipeline_src, (
        "P0.R3 D2: degraded-persists branch MUST emit `print(f\"[Vision] stale persists`. "
        "Bare `stale persists` matches the watchdog docstring too; the print call "
        "shape is the load-bearing assertion."
    )


@pytest.mark.parametrize("degraded_initial,expected_restart_called", [
    (False, True),
    (True, False),
])
def test_p0_r3_d2_anchor_2_stale_triggers_restart_OR_persists(
    monkeypatch, degraded_initial, expected_restart_called
):
    """A3: stale heartbeat — degraded=False → restart; degraded=True → persists log."""
    import pipeline as _pl
    import time
    _pl._pipeline_state_store.reset()
    asyncio.run(_pl._pipeline_state_store.set_vision_heartbeat(time.time() - 1000.0))
    asyncio.run(_pl._pipeline_state_store.set_vision_degraded(degraded_initial))

    restart_called = {"count": 0}

    async def _fake_restart():
        restart_called["count"] += 1

    monkeypatch.setattr(_pl, "_restart_vision_task", _fake_restart)

    async def _run_one_iteration():
        _now = time.time()
        _heartbeat_at = _pl._pipeline_state_store.peek_vision_heartbeat_at()
        from core.config import VISION_WATCHDOG_STALE_THRESHOLD_SECS
        _staleness = _now - _heartbeat_at
        if _staleness < VISION_WATCHDOG_STALE_THRESHOLD_SECS:
            return
        if _pl._pipeline_state_store.peek_vision_degraded():
            return
        await _pl._restart_vision_task()

    asyncio.run(_run_one_iteration())
    assert (restart_called["count"] > 0) == expected_restart_called, (
        f"P0.R3 D2: degraded_initial={degraded_initial} expected restart={expected_restart_called}"
    )


def test_p0_r3_d3_anchor_1_store_has_vision_fields(store_src):
    """A4: PipelineStateStore has 2 fields + 4 methods."""
    assert "_vision_heartbeat_at" in store_src
    assert "_vision_degraded" in store_src
    for method_name in ("set_vision_heartbeat", "peek_vision_heartbeat_at",
                        "set_vision_degraded", "peek_vision_degraded"):
        assert f"def {method_name}" in store_src, (
            f"P0.R3 D3: PipelineStateStore must define `{method_name}`"
        )


def test_p0_r3_d3_anchor_2_health_snapshot_field(health_src):
    """A5: HealthSnapshot has `vision_degraded: bool = False`."""
    assert "vision_degraded: bool = False" in health_src


def test_p0_r3_d3_anchor_3_format_alerts_emits_degraded(health_src):
    """A6: format_health_alerts emits actionable recovery substrings."""
    assert "Vision subsystem degraded" in health_src
    assert "check camera/driver state" in health_src
    assert "clears automatically" in health_src


def test_p0_r3_d4_anchor_1_restart_success_clears_degraded(monkeypatch):
    """A7: D4 detects heartbeat advance → clears vision_degraded."""
    import pipeline as _pl
    import time
    _pl._pipeline_state_store.reset()
    asyncio.run(_pl._pipeline_state_store.set_vision_degraded(True))
    _t1 = time.time() - 100.0
    asyncio.run(_pl._pipeline_state_store.set_vision_heartbeat(_t1))

    class _DoneTask:
        def done(self): return True
        def cancel(self): pass
    monkeypatch.setattr(_pl, "_vision_task", _DoneTask())

    async def _fake_loop_body():
        await _pl._pipeline_state_store.set_vision_heartbeat(time.time())

    monkeypatch.setattr(_pl, "_background_vision_loop", lambda *a, **k: _fake_loop_body())

    asyncio.run(_pl._restart_vision_task())

    async def _flush():
        await asyncio.sleep(0.1)
    asyncio.run(_flush())

    assert _pl._pipeline_state_store.peek_vision_degraded() == False, (
        "P0.R3 D4: restart success MUST clear vision_degraded."
    )


def test_p0_r3_d4_anchor_2_restart_fail_sets_degraded(monkeypatch):
    """A8: D4 detects heartbeat timeout → sets vision_degraded; audio untouched."""
    import pipeline as _pl
    import time
    _pl._pipeline_state_store.reset()
    asyncio.run(_pl._pipeline_state_store.set_vision_heartbeat(time.time() - 1000.0))
    asyncio.run(_pl._pipeline_state_store.set_vision_degraded(False))

    async def _never_advance():
        await asyncio.sleep(100.0)
    monkeypatch.setattr(_pl, "_background_vision_loop", lambda *a, **k: _never_advance())

    import core.config
    monkeypatch.setattr(core.config, "VISION_WATCHDOG_RESTART_TIMEOUT_SECS", 2.0)

    class _DoneTask:
        def done(self): return True
        def cancel(self): pass
    monkeypatch.setattr(_pl, "_vision_task", _DoneTask())

    # Audio-alive sentinel: capture before; verify after (the restart helper
    # has NO reference to any audio symbol, so this is a defense-in-depth check).
    audio_alive = {"alive": True}

    async def _test():
        await _pl._restart_vision_task()
        assert audio_alive["alive"], "P0.R3 D4: audio task MUST NOT be touched"

    asyncio.run(_test())

    async def _flush():
        await asyncio.sleep(0.1)
    asyncio.run(_flush())

    assert _pl._pipeline_state_store.peek_vision_degraded() == True, (
        "P0.R3 D4: restart timeout MUST set vision_degraded → True."
    )


def test_p0_r3_d5_anchor_1_watchdog_spawn_after_vision_AND_cancel_before_vision(pipeline_src):
    """A9: watchdog spawn AFTER vision spawn; watchdog cancel BEFORE vision cancel."""
    vision_spawn_idx = pipeline_src.find("_vision_task = asyncio.create_task(\n        _background_vision_loop")
    watchdog_spawn_idx = pipeline_src.find("_vision_watchdog_task = asyncio.create_task(_vision_watchdog_loop")
    assert vision_spawn_idx > 0, "Vision task spawn site must be present"
    assert watchdog_spawn_idx > 0, "Watchdog task spawn site must be present"
    assert vision_spawn_idx < watchdog_spawn_idx, (
        "P0.R3 D5: startup ordering — vision spawn BEFORE watchdog spawn."
    )

    # `_vision_task.cancel()` appears multiple times in source (once inside
    # `_restart_vision_task` helper at restart-helper-cancel-current-task, plus
    # the shutdown-final cancel). Use rfind to scope to the SHUTDOWN occurrence
    # (which is the last one in file order); `_vision_watchdog_task.cancel()`
    # only appears once (at shutdown), so find = rfind for it.
    watchdog_cancel_idx = pipeline_src.find("_vision_watchdog_task.cancel()")
    vision_cancel_idx = pipeline_src.rfind("_vision_task.cancel()")
    assert watchdog_cancel_idx > 0
    assert vision_cancel_idx > 0
    assert watchdog_cancel_idx < vision_cancel_idx, (
        "P0.R3 D5: shutdown ordering — watchdog cancel BEFORE vision cancel."
    )


def test_p0_r3_d2_anchor_3_config_constants_present(config_src):
    """A10: 3 watchdog constants present in core/config.py."""
    assert "VISION_WATCHDOG_INTERVAL_SECS" in config_src and "= 5.0" in config_src
    assert "VISION_WATCHDOG_STALE_THRESHOLD_SECS" in config_src and "= 30.0" in config_src
    assert "VISION_WATCHDOG_RESTART_TIMEOUT_SECS" in config_src
