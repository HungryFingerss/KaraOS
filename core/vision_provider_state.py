"""core/vision_provider_state.py — P0.R2 D4 provider state machine.

Global state tracking active inference provider (cuda vs cpu) across all
ONNX paths in core/vision.py. Counter + timer hybrid for switch-back semantics
per P0.R2 Q5 architect lean.

Trigger semantics:
- `record_cuda_failure()`: called by embed()/detect() RuntimeError catch;
  switches active to cpu + arms counter (N requests) and timer (M minutes).
- `record_success("cpu")`: called on successful CPU inference; decrements
  counter; restores cuda when counter reaches 0.
- `maybe_retry_cuda(now)`: called by `_health_log_loop`; restores cuda if
  timer (M minutes) elapsed since last failure.
- `set_cpu_only_permanent()`: called by D3 graceful degradation when CUDA
  is structurally unavailable at boot (no CUDAExecutionProvider in ORT).

Counter-OR-timer-restores-CUDA semantic (whichever fires first).
"""
from __future__ import annotations

import threading
import time
from typing import Literal

from core.config import VISION_CPU_SWITCH_N_REQUESTS, VISION_CUDA_RETRY_M_MINUTES

_lock = threading.Lock()
_active_provider: Literal["cuda", "cpu"] = "cuda"
_cpu_requests_remaining: int = 0
_cpu_switch_at: float | None = None
_cpu_only_permanent: bool = False  # D3 graceful degradation flag


def record_cuda_failure() -> None:
    """Called by embed()/detect() RuntimeError catch; switches active to cpu."""
    global _active_provider, _cpu_requests_remaining, _cpu_switch_at
    if _cpu_only_permanent:
        return
    with _lock:
        _active_provider = "cpu"
        _cpu_requests_remaining = VISION_CPU_SWITCH_N_REQUESTS
        _cpu_switch_at = time.time()
    print(f"[Vision] Active provider switched to CPU for next {VISION_CPU_SWITCH_N_REQUESTS} requests")


def record_success(provider: Literal["cuda", "cpu"]) -> None:
    """Called on successful inference; decrements counter; restores cuda on N exhausted."""
    global _active_provider, _cpu_requests_remaining
    if _cpu_only_permanent or _active_provider == "cuda":
        return
    with _lock:
        if provider == "cpu" and _cpu_requests_remaining > 0:
            _cpu_requests_remaining = max(0, _cpu_requests_remaining - 1)
            if _cpu_requests_remaining == 0:
                _active_provider = "cuda"
                print(f"[Vision] Active provider restored to CUDA after CPU request quota exhausted")


def get_active_provider() -> Literal["cuda", "cpu"]:
    """Read by FaceEmbedder/FaceDetector to route inference."""
    return _active_provider


def maybe_retry_cuda(now: float) -> None:
    """Called by _health_log_loop; attempts CUDA restoration if timer elapsed."""
    global _active_provider, _cpu_requests_remaining
    if _cpu_only_permanent or _active_provider == "cuda":
        return
    if _cpu_switch_at is None:
        return
    elapsed_minutes = (now - _cpu_switch_at) / 60.0
    if elapsed_minutes >= VISION_CUDA_RETRY_M_MINUTES:
        with _lock:
            _active_provider = "cuda"
            _cpu_requests_remaining = 0
            print(f"[Vision] CUDA-retry timer elapsed ({elapsed_minutes:.1f} min); active provider restored to CUDA")


def set_cpu_only_permanent() -> None:
    """Called by D3 graceful degradation when CUDA structurally unavailable."""
    global _cpu_only_permanent, _active_provider
    with _lock:
        _cpu_only_permanent = True
        _active_provider = "cpu"


def reset_for_tests() -> None:
    """Test helper — reset module state to defaults."""
    global _active_provider, _cpu_requests_remaining, _cpu_switch_at, _cpu_only_permanent
    with _lock:
        _active_provider = "cuda"
        _cpu_requests_remaining = 0
        _cpu_switch_at = None
        _cpu_only_permanent = False
