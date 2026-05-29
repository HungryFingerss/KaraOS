"""tests/test_p0_r1_onnx_session_wrap.py — P0.R1 D1 source-inspection + behavioral anchors.

Plan v1 §3 LOCK at 4 logical anchors:
- Anchor 1 (source-inspection): `FaceEmbedder.embed()` wraps `session.run()` in
  try/except with lazy CPU-EP fallback construction.
- Anchor 2 (source-inspection): failure log substrings present (`[Vision] AdaFace
  inference failed`, `falling back to CPU`, `[Vision] AdaFace CPU fallback also failed`).
- Anchor 3 (behavioral): CUDA-OOM → CPU fallback returns L2-normalized 512-dim
  embedding; `_cpu_session` populated.
- Anchor 4 (behavioral): cascading CUDA+CPU failure → returns None gracefully
  (no exception propagation).

Source-inspection anchors run on any environment. Behavioral anchors (3+4) require
CUDA availability for `FaceEmbedder.__init__` to succeed — gated via skipif.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_VISION_PY = _REPO_ROOT / "core" / "vision.py"
_ADAFACE_MODEL = _REPO_ROOT / "models" / "adaface_ir101.onnx"


def _read(p: Path) -> str:
    assert p.exists(), f"P0.R1 anchor expects {p} to exist"
    return p.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def vision_src() -> str:
    """Read core/vision.py source once per module."""
    return _read(_VISION_PY)


def _cuda_available() -> bool:
    """Return True iff CUDAExecutionProvider is available (gates behavioral anchors).

    Called at TEST RUN TIME (not module-import time) so that monkeypatched
    onnxruntime state from earlier tests in the full-suite collection order
    doesn't permanently pin the marker to skip. Run-time evaluation re-queries
    real `ort.get_available_providers()` per test.
    """
    try:
        import onnxruntime as ort
        return "CUDAExecutionProvider" in ort.get_available_providers()
    except Exception:
        return False


def _require_cuda_or_skip() -> None:
    """Run-time guard — pytest.skip() if CUDA unavailable at this moment."""
    if not _cuda_available():
        pytest.skip("P0.R1 D1 behavioral anchors require CUDAExecutionProvider for FaceEmbedder.__init__")


# ───────────────────────────────────────────────────────────────────────
# D1 source-inspection anchors (2)
# ───────────────────────────────────────────────────────────────────────


def test_p0_r1_d1_anchor_1_embed_wraps_session_run_with_cpu_fallback(vision_src):
    """P0.R1 D1 (RETARGETED at P0.R2 D1 per Plan v1 §1.2): proactive CPU-EP
    session construction in `FaceEmbedder.__init__()`. P0.R1's original lazy
    build inside `embed()` body was retargeted by P0.R2 D1 to a proactive
    build at startup (eliminates the ~1s build cost on first failure).

    Anchor 1 assertion target shifted from `embed()` source to `__init__()`
    source: __init__() body must contain `providers=["CPUExecutionProvider"]`
    + `self._cpu_session = ort.InferenceSession(...)` proactive construction.
    Anchors 2/3/4 stay green (failure log substring + behavioral CUDA-fallback
    semantic + cascading-failure None return all preserved at embed() body).
    """
    import ast
    tree = ast.parse(vision_src)

    # Locate FaceEmbedder.__init__ body
    init_body_src = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "FaceEmbedder":
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == "__init__":
                    init_body_src = ast.unparse(child)
                    break
            break
    assert init_body_src is not None, "FaceEmbedder.__init__ method must exist"

    # P0.R2 D1: proactive CPU-EP construction in __init__ body. Note `ast.unparse`
    # normalizes string-literal quotes (double → single), so we check the symbolic
    # form `providers=` + `CPUExecutionProvider` separately rather than the exact
    # source quoting style.
    assert "providers=" in init_body_src and "CPUExecutionProvider" in init_body_src, (
        "P0.R1 D1 (retargeted): FaceEmbedder.__init__() body MUST contain "
        "`providers=[\"CPUExecutionProvider\"]` for proactive CPU session construction. "
        "P0.R1's lazy build inside embed() was retargeted by P0.R2 D1 to startup."
    )
    assert "self._cpu_session = ort.InferenceSession" in init_body_src, (
        "P0.R1 D1 (retargeted): __init__() MUST proactively build "
        "`self._cpu_session = ort.InferenceSession(...)` at startup. "
        "Lazy `self._cpu_session = None` slot was eliminated by P0.R2 D1."
    )
    # Embed() body should NO LONGER contain the lazy build pattern.
    # (Lazy `if self._cpu_session is None:` regression would re-introduce the
    # ~1s on-first-failure build cost.)
    embed_body_src = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "FaceEmbedder":
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == "embed":
                    embed_body_src = ast.unparse(child)
                    break
            break
    assert embed_body_src is not None, "FaceEmbedder.embed method must exist"
    assert "if self._cpu_session is None" not in embed_body_src, (
        "P0.R2 D1 invariant: embed() body MUST NOT contain `if self._cpu_session is None` "
        "lazy-build pattern. P0.R2 D1 retargeted to proactive __init__() construction."
    )


def test_p0_r1_d1_anchor_2_embed_logs_fallback_failure(vision_src):
    """P0.R1 D1 Q2: failure log mirrors core/audio.py Smart-Turn shape —
    `[Vision] AdaFace inference failed: {e}, falling back to CPU` + tier-2
    `[Vision] AdaFace CPU fallback also failed`.
    """
    assert "[Vision] AdaFace inference failed" in vision_src
    assert "falling back to CPU" in vision_src
    # Tier-2 cascading failure log.
    assert "[Vision] AdaFace CPU fallback also failed" in vision_src


# ───────────────────────────────────────────────────────────────────────
# D1 behavioral anchors (2) — require CUDA for FaceEmbedder.__init__
# ───────────────────────────────────────────────────────────────────────


def test_p0_r1_d1_anchor_3_cuda_failure_falls_back_to_cpu_embedding(monkeypatch):
    """P0.R1 D1 Q4: when CUDA session.run raises RuntimeError, embed() builds
    a CPU-EP session lazily, reruns the inference on CPU, and returns the
    embedding transparently. Verify L2-normalized 512-dim shape + _cpu_session populated.
    """
    _require_cuda_or_skip()
    from core.vision import FaceEmbedder
    fe = FaceEmbedder(model_path=str(_ADAFACE_MODEL))
    # Mock CUDA session.run to raise; first call should fall back to CPU.
    monkeypatch.setattr(
        fe._session, "run",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("CUDA OOM"))
    )
    face_crop = np.random.randint(0, 255, (112, 112, 3), dtype=np.uint8)
    embedding = fe.embed(face_crop)
    assert embedding is not None
    assert embedding.shape == (512,)
    assert embedding.dtype == np.float32
    # L2-normalized
    assert abs(np.linalg.norm(embedding) - 1.0) < 1e-5
    # CPU session got built
    assert fe._cpu_session is not None


def test_p0_r1_d1_anchor_4_cascading_failure_returns_none_gracefully(monkeypatch):
    """P0.R1 D1 Q4: when BOTH CUDA AND CPU sessions fail, embed() returns None
    gracefully (no exception propagation). Caller treats as recognize-miss
    via existing P0.5 None-handling paths.

    Post-P0.R2 D1 refactor: CPU session is now PROACTIVELY built at __init__()
    (no lazy build). To simulate cascading failure, monkeypatch BOTH
    `fe._session.run` AND `fe._cpu_session.run` to raise (the original
    `ort.InferenceSession` constructor monkeypatch is no longer load-bearing
    because no new sessions are constructed inside `embed()`). Semantic is
    preserved: cascading CUDA+CPU `.run()` failure → embed() returns None.
    """
    _require_cuda_or_skip()
    from core.vision import FaceEmbedder
    fe = FaceEmbedder(model_path=str(_ADAFACE_MODEL))
    # Mock CUDA session.run to raise.
    monkeypatch.setattr(
        fe._session, "run",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("CUDA OOM"))
    )
    # Mock CPU session.run to also raise (cascading failure).
    # P0.R2 D1: both sessions are pre-built at __init__; failure is at .run() time.
    monkeypatch.setattr(
        fe._cpu_session, "run",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("CPU inference failed"))
    )
    face_crop = np.random.randint(0, 255, (112, 112, 3), dtype=np.uint8)
    embedding = fe.embed(face_crop)
    assert embedding is None  # graceful degradation; NO exception
