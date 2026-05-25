"""tests/test_p0_r2_proactive_cpu_fallback.py — P0.R2 D1-D5 anchors.

Plan v1 §3 LOCK at 9 logical anchors total (1 RETARGETED P0.R1 Anchor 1 lives
in `tests/test_p0_r1_onnx_session_wrap.py` per §1.2 retargeting disposition;
the 8 NEW anchors below cover D1 #2 + D2 #1+#2 + D3 #1 + D4 #1+#2+#3 + D5 #1).

- D1 Anchor 2 (behavioral): proactive build verification (`_cpu_session is not None` post-`__init__()`).
- D2 Anchor 1 (source-inspection): both `_app_cuda` + `_app_cpu` FaceAnalysis instances built.
- D2 Anchor 2 (behavioral): CUDA-fail → CPU fallback returns detection.
- D3 Anchor 1 (behavioral): CUDA-unavailable → graceful CPU-only degradation (no RuntimeError).
- D4 Anchor 1 (source-inspection): `core/vision_provider_state.py` module shape (state + 5 public functions).
- D4 Anchor 2 (behavioral): counter trigger — `record_cuda_failure()` → switch; N×`record_success("cpu")` → restore.
- D4 Anchor 3 (behavioral): timer trigger — `record_cuda_failure()` → `maybe_retry_cuda(now)` after M minutes → restore.
- D5 Anchor 1 (source-inspection): conditional `vision_provider=cpu` emit in `format_health_line`.

Behavioral anchors that require CUDA at FaceEmbedder/FaceDetector `__init__` are gated via
`_require_cuda_or_skip()` run-time check (same pattern as `tests/test_p0_r1_onnx_session_wrap.py`).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_VISION_PY = _REPO_ROOT / "core" / "vision.py"
_VISION_PROVIDER_STATE_PY = _REPO_ROOT / "core" / "vision_provider_state.py"
_HEALTH_PY = _REPO_ROOT / "core" / "health.py"
_ADAFACE_MODEL = _REPO_ROOT / "models" / "adaface_ir101.onnx"


def _read(p: Path) -> str:
    assert p.exists(), f"P0.R2 anchor expects {p} to exist"
    return p.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def vision_src() -> str:
    return _read(_VISION_PY)


@pytest.fixture(scope="module")
def vps_src() -> str:
    return _read(_VISION_PROVIDER_STATE_PY)


@pytest.fixture(scope="module")
def health_src() -> str:
    return _read(_HEALTH_PY)


def _cuda_available() -> bool:
    try:
        import onnxruntime as ort
        return "CUDAExecutionProvider" in ort.get_available_providers()
    except Exception:
        return False


def _require_cuda_or_skip() -> None:
    if not _cuda_available():
        pytest.skip("P0.R2 behavioral anchors require CUDAExecutionProvider for vision instantiation")


def _require_real_ort_or_skip() -> None:
    """Defensive guard — earlier full-suite tests sometimes leave `ort.InferenceSession`
    monkeypatched to a `MagicMock`. P0.R2 D3 Anchor 1 needs a REAL ORT session for
    `get_providers()` to return a real provider list. Skip if polluted.
    """
    import onnxruntime as ort
    if not callable(ort.InferenceSession) or type(ort.InferenceSession).__name__ in ("MagicMock", "Mock"):
        pytest.skip("P0.R2 D3 Anchor 1 requires real `ort.InferenceSession` (full-suite pollution detected)")


@pytest.fixture(autouse=True)
def _reset_vps_state():
    """Reset module-level state in core.vision_provider_state between tests."""
    from core import vision_provider_state as _vps
    _vps.reset_for_tests()
    yield
    _vps.reset_for_tests()


# ───────────────────────────────────────────────────────────────────────
# D1 Anchor 2 (behavioral) — proactive CPU session build at __init__
# ───────────────────────────────────────────────────────────────────────


def test_p0_r2_d1_anchor_2_proactive_cpu_session_built_at_init():
    """D1 Anchor 2: `FaceEmbedder.__init__()` proactively builds `self._cpu_session`
    at startup (no lazy `= None` slot). Verified by inspecting post-init state.
    """
    _require_cuda_or_skip()
    from core.vision import FaceEmbedder
    fe = FaceEmbedder(model_path=str(_ADAFACE_MODEL))
    assert fe._cpu_session is not None, (
        "P0.R2 D1: `self._cpu_session` MUST be proactively built at __init__(); "
        "P0.R1's lazy-`None`-slot pattern was retargeted by P0.R2 D1."
    )
    # The pre-built session must be a real ORT InferenceSession with CPU provider active.
    providers = fe._cpu_session.get_providers()
    assert "CPUExecutionProvider" in providers, (
        f"P0.R2 D1: `_cpu_session` MUST use CPUExecutionProvider; got {providers}"
    )


# ───────────────────────────────────────────────────────────────────────
# D2 Anchor 1 (source-inspection) — both FaceAnalysis instances built
# ───────────────────────────────────────────────────────────────────────


def test_p0_r2_d2_anchor_1_both_face_analysis_instances_built(vision_src):
    """D2 Anchor 1: `FaceDetector.__init__()` builds BOTH `_app_cuda` AND `_app_cpu`
    FaceAnalysis instances with their respective provider lists.
    """
    assert "self._app_cuda" in vision_src and "self._app_cpu" in vision_src, (
        "P0.R2 D2: FaceDetector MUST have both `self._app_cuda` AND `self._app_cpu` attributes."
    )
    assert "CUDAExecutionProvider" in vision_src and "CPUExecutionProvider" in vision_src, (
        "P0.R2 D2: __init__() MUST configure both CUDAExecutionProvider AND CPUExecutionProvider."
    )
    # Both instances should be prepared (ctx_id=0 for CUDA + ctx_id=-1 for CPU).
    # Use tighter substring `prepare(ctx_id=X, det_size=` to avoid matching
    # bare `ctx_id=-1` literals in comments (P0.S9-precedent prefix-collision
    # detector strengthening per `### Induction-surfaces-invariant-gaps`).
    assert "prepare(ctx_id=0, det_size=" in vision_src, (
        "P0.R2 D2: __init__() MUST call `_app_cuda.prepare(ctx_id=0, det_size=...)` for CUDA."
    )
    assert "prepare(ctx_id=-1, det_size=" in vision_src, (
        "P0.R2 D2: __init__() MUST call `_app_cpu.prepare(ctx_id=-1, det_size=...)` for CPU."
    )


# ───────────────────────────────────────────────────────────────────────
# D2 Anchor 2 (behavioral) — CUDA-fail → CPU fallback returns detection
# ───────────────────────────────────────────────────────────────────────


def test_p0_r2_d2_anchor_2_cuda_fail_falls_back_to_cpu_detection(monkeypatch):
    """D2 Anchor 2: when `_app_cuda.get` raises, `_run_detection()` falls back
    to `_app_cpu.get` via state machine. Verify via mocked CUDA + CPU apps.
    """
    _require_cuda_or_skip()
    from core.vision import FaceDetector
    fd = FaceDetector()
    # Mock CUDA app.get to raise; CPU app.get to return a fake face object.
    class _FakeFace:
        det_score = 0.99
        bbox = np.array([10, 10, 100, 100], dtype=np.float32)
        kps = np.array([[20, 30], [40, 30], [30, 50], [25, 70], [35, 70]], dtype=np.float32)
    monkeypatch.setattr(
        fd._app_cuda, "get",
        lambda frame: (_ for _ in ()).throw(RuntimeError("CUDA OOM"))
    )
    monkeypatch.setattr(fd._app_cpu, "get", lambda frame: [_FakeFace()])
    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    dets_np, raw_list = fd._run_detection(frame, 480, 640)
    # CPU fallback should return non-empty result
    assert len(raw_list) >= 1, (
        "P0.R2 D2: CUDA failure MUST fall back to CPU app.get; got empty result. "
        "Verify `_run_detection()` routes via `_vision_provider_state` + has CPU fallback try/except."
    )


# ───────────────────────────────────────────────────────────────────────
# D3 Anchor 1 (behavioral) — CUDA-unavailable graceful CPU-only boot
# ───────────────────────────────────────────────────────────────────────


def test_p0_r2_d3_anchor_1_cuda_unavailable_graceful_cpu_only(monkeypatch):
    """D3 Anchor 1: when `ort.get_available_providers()` returns only CPU,
    `FaceEmbedder.__init__()` does NOT raise RuntimeError; instead builds
    CPU-only session + calls `_vision_provider_state.set_cpu_only_permanent()`.
    """
    _require_real_ort_or_skip()
    import onnxruntime as ort
    monkeypatch.setattr(
        ort, "get_available_providers",
        lambda: ["CPUExecutionProvider"]
    )
    from core.vision import FaceEmbedder
    # MUST NOT raise — graceful CPU-only degradation per D3.
    fe = FaceEmbedder(model_path=str(_ADAFACE_MODEL))
    assert fe._session is not None
    # _session must use CPU provider since CUDA was unavailable.
    providers = fe._session.get_providers()
    assert "CPUExecutionProvider" in providers, (
        f"P0.R2 D3: with CUDA unavailable, _session MUST use CPU; got {providers}"
    )
    # State machine should be set to cpu_only_permanent.
    from core import vision_provider_state as _vps
    assert _vps.get_active_provider() == "cpu", (
        "P0.R2 D3: CUDA-unavailable boot MUST call `set_cpu_only_permanent()` "
        "→ active provider stays 'cpu'."
    )


# ───────────────────────────────────────────────────────────────────────
# D4 Anchor 1 (source-inspection) — module shape: state + 5 public functions
# ───────────────────────────────────────────────────────────────────────


def test_p0_r2_d4_anchor_1_provider_state_module_shape(vps_src):
    """D4 Anchor 1: `core/vision_provider_state.py` has module-level state
    (`_active_provider`, `_cpu_requests_remaining`, `_cpu_switch_at`) +
    5 public functions (`record_cuda_failure`, `record_success`,
    `get_active_provider`, `maybe_retry_cuda`, `set_cpu_only_permanent`).
    """
    # Module-level state
    assert "_active_provider" in vps_src, "P0.R2 D4: module must define `_active_provider`"
    assert "_cpu_requests_remaining" in vps_src, "P0.R2 D4: module must define `_cpu_requests_remaining`"
    assert "_cpu_switch_at" in vps_src, "P0.R2 D4: module must define `_cpu_switch_at`"
    # 5 public functions
    for fn_name in ("record_cuda_failure", "record_success", "get_active_provider",
                    "maybe_retry_cuda", "set_cpu_only_permanent"):
        assert f"def {fn_name}(" in vps_src, (
            f"P0.R2 D4: module must define public function `{fn_name}`"
        )


# ───────────────────────────────────────────────────────────────────────
# D4 Anchor 2 (behavioral) — counter trigger
# ───────────────────────────────────────────────────────────────────────


def test_p0_r2_d4_anchor_2_counter_trigger_restores_cuda():
    """D4 Anchor 2: `record_cuda_failure()` → active='cpu'; N×`record_success('cpu')`
    decrements counter; final success restores active='cuda'.
    """
    from core import vision_provider_state as _vps
    from core.config import VISION_CPU_SWITCH_N_REQUESTS
    # Start in default state (active='cuda').
    assert _vps.get_active_provider() == "cuda"
    # Trigger CUDA failure → switch to CPU.
    _vps.record_cuda_failure()
    assert _vps.get_active_provider() == "cpu", (
        "P0.R2 D4: `record_cuda_failure()` MUST switch active provider to 'cpu'."
    )
    # Decrement counter via N successful CPU inferences.
    for _ in range(VISION_CPU_SWITCH_N_REQUESTS):
        _vps.record_success("cpu")
    # Counter exhausted → restore CUDA.
    assert _vps.get_active_provider() == "cuda", (
        f"P0.R2 D4: after {VISION_CPU_SWITCH_N_REQUESTS} CPU successes, "
        "active provider MUST restore to 'cuda'."
    )


# ───────────────────────────────────────────────────────────────────────
# D4 Anchor 3 (behavioral) — timer trigger
# ───────────────────────────────────────────────────────────────────────


def test_p0_r2_d4_anchor_3_timer_trigger_restores_cuda():
    """D4 Anchor 3: `record_cuda_failure()` → active='cpu'; after
    VISION_CUDA_RETRY_M_MINUTES + epsilon, `maybe_retry_cuda(now)` restores
    active='cuda' (timer-based trigger; counter is NOT exhausted in this test).
    """
    import time as _time
    from core import vision_provider_state as _vps
    from core.config import VISION_CUDA_RETRY_M_MINUTES
    # Trigger CUDA failure.
    _vps.record_cuda_failure()
    assert _vps.get_active_provider() == "cpu"
    # Simulate enough time passing — pass `now` parameter explicitly.
    fake_now = _time.time() + (VISION_CUDA_RETRY_M_MINUTES + 1) * 60.0
    _vps.maybe_retry_cuda(fake_now)
    assert _vps.get_active_provider() == "cuda", (
        f"P0.R2 D4: `maybe_retry_cuda()` with elapsed >{VISION_CUDA_RETRY_M_MINUTES} min "
        "MUST restore active provider to 'cuda' (timer trigger)."
    )


# ───────────────────────────────────────────────────────────────────────
# D5 Anchor 1 (source-inspection) — conditional vision_provider=cpu emit
# ───────────────────────────────────────────────────────────────────────


def test_p0_r2_d5_anchor_1_conditional_vision_provider_emit(health_src):
    """D5 Anchor 1: `core/health.py::format_health_line` imports
    `vision_provider_state` and conditionally emits `vision_provider=cpu`
    when active provider is CPU (mirrors evlog_parts/kuzu_parts pattern).
    """
    assert "from core import vision_provider_state" in health_src, (
        "P0.R2 D5: `core/health.py` MUST import `vision_provider_state`."
    )
    assert "vision_provider=cpu" in health_src, (
        "P0.R2 D5: `format_health_line` MUST emit literal `vision_provider=cpu` "
        "(conditional on `get_active_provider() == 'cpu'`)."
    )
    assert "get_active_provider()" in health_src, (
        "P0.R2 D5: `format_health_line` MUST call `get_active_provider()` "
        "to gate the conditional emit."
    )
