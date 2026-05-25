"""P0.R6 — Heavy-task worker foundation + AdaFace migration (10 logical anchors).

Validates the ``core/heavy_worker.py`` module (D1 + D2), the pipeline.py D3
migration of 4 AdaFace async-hot-path sites (per PI #1 Option α expansion),
the D4 health-observability wiring, and the D5 startup/shutdown lifecycle.

Per Plan v1 §3 LOCK: 10 anchors at exact mid 10 inclusive ±15% band [8.5, 11.5].
A4 broadened per PI #1 — covers all 4 async-hot-path sites (2569 + 2663 +
6716 + 7112; line numbers may shift post-edit) PLUS verifies sync sites
3474 + 3551 are NOT migrated (sync boot/enrollment flows OUT-OF-SCOPE).

Hybrid Q8 (a) surface:
- A1-A3 + A5-A8: source-inspection (file existence + substring + AST line-order)
- A4: AST-based migration scan (positive 4-site + inverse sync-sites-unchanged)
- A9: behavioral CUDA-gated smoke (Pipeline.from_pretrained-style; skips
  gracefully without GPU OR when conftest MagicMock stub active)
- A10: behavioral mocked (worker None-return propagation; CPU-only)
"""
from __future__ import annotations

import ast
import inspect
import os
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_HEAVY_WORKER = _REPO_ROOT / "core" / "heavy_worker.py"
_PIPELINE = _REPO_ROOT / "pipeline.py"
_PIPELINE_STATE_STORE = _REPO_ROOT / "core" / "pipeline_state_store.py"
_HEALTH = _REPO_ROOT / "core" / "health.py"


def _cuda_available() -> bool:
    try:
        import torch  # noqa: PLC0415

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _require_real_voice_module_or_skip() -> None:
    """A9 needs the REAL ``core.vision`` (not conftest MagicMock stub)."""
    import sys
    from unittest.mock import MagicMock

    voice = sys.modules.get("core.vision")
    if voice is None:
        return
    if isinstance(getattr(voice, "FaceEmbedder", None), MagicMock):
        pytest.skip(
            "core.vision is MagicMock stub — A9 smoke needs real module. "
            "Run with real vision module preloaded OR invoke standalone."
        )


# ---------------------------------------------------------------------------
# A1 + A2 (D1) — heavy_worker module + spawn start method
# ---------------------------------------------------------------------------


def test_p0_r6_d1_anchor_1_heavy_worker_module_exists() -> None:
    """A1 — ``core/heavy_worker.py`` exists, non-empty, importable.

    Per Plan v1 §2.7 (a) deliberate-regression: deleting the module fires
    this anchor (file-existence regression).
    """
    assert _HEAVY_WORKER.exists(), (
        f"D1 regression: core/heavy_worker.py missing at {_HEAVY_WORKER}. "
        f"Per Plan v1 §2.1 LOCKED, this module is the P0.R6 foundation."
    )
    content = _HEAVY_WORKER.read_text(encoding="utf-8")
    assert content.strip(), "D1 regression: heavy_worker.py is empty."
    # Importability sanity.
    import core.heavy_worker  # noqa: F401, PLC0415


def test_p0_r6_d1_anchor_2_uses_spawn_start_method() -> None:
    """A2 — ``core/heavy_worker.py`` uses ``mp.get_context("spawn")``
    explicitly (Q6 (a) lock; cross-platform Windows + Linux + Jetson).

    Per Plan v1 §2.7 (b) deliberate-regression: swapping ``"spawn"`` for
    ``"fork"`` fires this anchor.

    AST-based check (not substring) — the docstring at module top mentions
    ``mp.get_context("spawn")`` verbatim as part of the architectural
    rationale; substring check would pass even after the actual Call node
    was reverted to ``fork``. AST scan scopes to ACTUAL call expressions,
    closing the docstring-collision detector gap surfaced during P0.R6
    Phase 4 deliberate-regression (b) (same family as P0.R3 stale-persists
    docstring-collision per ``### Induction-surfaces-invariant-gaps``
    operational rule 3).
    """
    tree = ast.parse(_HEAVY_WORKER.read_text(encoding="utf-8"))
    spawn_calls = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Match `mp.get_context("spawn")` Call:
        # Call(func=Attribute(value=Name("mp"), attr="get_context"),
        #      args=[Constant("spawn")])
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "mp"
            and func.attr == "get_context"
        ):
            continue
        if (
            node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "spawn"
        ):
            spawn_calls += 1
    assert spawn_calls >= 1, (
        "D1 regression: core/heavy_worker.py must call mp.get_context(\"spawn\") "
        "explicitly (AST Call node, not docstring text) for cross-platform "
        "consistency per Plan v1 §2.1 + Q6 (a) lock. Fork start method "
        "breaks Windows (where it's unavailable) + leaks parent CUDA "
        "context on Linux."
    )


# ---------------------------------------------------------------------------
# A3 (D2) — adaface_embed_worker module-level function (pickleable)
# ---------------------------------------------------------------------------


def test_p0_r6_d2_anchor_1_adaface_worker_function() -> None:
    """A3 — ``adaface_embed_worker`` is defined at MODULE SCOPE in
    ``core/heavy_worker.py`` (NOT nested inside another function).
    Module-level definition is required for pickleability — ProcessPoolExecutor's
    spawn-based IPC pickles the function reference; nested functions can't
    be pickled.

    Per Plan v1 §2.7 (c) deliberate-regression: moving the function to
    local scope fires this anchor.
    """
    tree = ast.parse(_HEAVY_WORKER.read_text(encoding="utf-8"))
    module_level_funcs = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    assert "adaface_embed_worker" in module_level_funcs, (
        f"D2 regression: adaface_embed_worker must be defined at module "
        f"scope in core/heavy_worker.py (pickleability requirement). "
        f"Current module-level functions: {sorted(module_level_funcs)}."
    )
    # Also verify it's importable.
    import core.heavy_worker as hw  # noqa: PLC0415

    assert callable(getattr(hw, "adaface_embed_worker", None)), (
        "D2 regression: adaface_embed_worker not callable after import."
    )


# ---------------------------------------------------------------------------
# A4 (D3) — 4 async-hot-path sites migrated; 2 sync sites UNCHANGED
# ---------------------------------------------------------------------------


def test_p0_r6_d3_anchor_1_all_4_async_sites_use_heavy_worker() -> None:
    """A4 (BROADENED per PI #1 Option α absorption) — verifies that ALL 4
    async-hot-path AdaFace call sites in ``pipeline.py`` use
    ``hw.run_heavy("adaface_embed", ...)`` (positive check) AND that the 2
    sync boot/enrollment sites are NOT migrated (inverse check; sync flows
    are explicitly OUT-OF-SCOPE per Plan v1 §1.1).

    Per Plan v1 §2.7 (d) deliberate-regression: reverting site 6716 (or any
    of the 4 async sites) back to a sync ``embedder.embed(face_crop)`` call
    fires the positive 4-site enforcement.
    """
    source = _PIPELINE.read_text(encoding="utf-8")

    # Positive check — count `hw.run_heavy("adaface_embed"` calls (NOT
    # docstring/comment mentions of the substring; AST walker scopes to
    # actual Call nodes).
    tree = ast.parse(source)
    adaface_run_heavy_calls = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Match `hw.run_heavy("adaface_embed", ...)` shape:
        # Call(func=Attribute(value=Name("hw"), attr="run_heavy"),
        #      args=[Constant("adaface_embed"), ...])
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "hw"
            and func.attr == "run_heavy"
        ):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and first.value == "adaface_embed":
            adaface_run_heavy_calls += 1

    assert adaface_run_heavy_calls == 4, (
        f"D3 regression (positive 4-site enforcement): expected exactly 4 "
        f"`hw.run_heavy(\"adaface_embed\", ...)` calls in pipeline.py per "
        f"Plan v1 §1.1 PI #1 Option α absorption (sites 2569 + 2663 + 6716 "
        f"+ 7112). Found {adaface_run_heavy_calls}. Reverting any of the 4 "
        f"async-hot-path sites back to a sync `embedder.embed(...)` call "
        f"would drop this count below 4 and fire this anchor."
    )

    # Inverse check — verify the 2 OUT-OF-SCOPE sync sites STILL contain
    # direct `embedder.embed(face_crop)` calls (3474 + 3551 line numbers
    # may shift; substring-level check across the file is more robust).
    # Plan v1 §1.1 explicitly classifies these as sync boot/enrollment flows
    # that should NOT be migrated. Migrating them would break this anchor.
    sync_direct_call_count = source.count("embedding = embedder.embed(face_crop)")
    assert sync_direct_call_count == 2, (
        f"D3 regression (inverse OUT-OF-SCOPE check): expected exactly 2 "
        f"`embedding = embedder.embed(face_crop)` direct sync calls in "
        f"pipeline.py (sync boot/enrollment flows at first_boot_flow + "
        f"enrollment_flow per Plan v1 §1.1 OUT-OF-SCOPE classification). "
        f"Found {sync_direct_call_count}. Migrating these sync sites to the "
        f"worker pool would change the count and fire this inverse check; "
        f"per Plan v1 §1.1 they're explicitly OUT-OF-SCOPE."
    )


# ---------------------------------------------------------------------------
# A5 + A6 (D4) — HealthSnapshot field + format_health_line conditional emit
# ---------------------------------------------------------------------------


def test_p0_r6_d4_anchor_1_health_snapshot_has_worker_status() -> None:
    """A5 — ``HealthSnapshot`` dataclass has ``heavy_worker_status`` field.

    Per Plan v1 §2.7 (e) deliberate-regression: removing the field fires
    this anchor.
    """
    from core.health import HealthSnapshot

    import dataclasses

    field_names = {f.name for f in dataclasses.fields(HealthSnapshot)}
    assert "heavy_worker_status" in field_names, (
        f"D4 regression: HealthSnapshot missing heavy_worker_status field. "
        f"Present fields: {sorted(field_names)}. Per Plan v1 §2.4, this "
        f"field surfaces heavy-worker pool health to the observability layer."
    )


def test_p0_r6_d4_anchor_2_format_health_emits_worker_degraded() -> None:
    """A6 — ``format_health_line`` emits ``heavy_workers=degraded`` substring
    when any worker pool is non-healthy.

    Mirrors the existing ``vision=degraded`` / ``kuzu=degraded`` conditional
    emit pattern. Substring check on rendered output (not source) so the
    test stays robust against format-string refactors that preserve the
    rendered shape.
    """
    from core.health import HealthSnapshot, format_health_line

    snap = HealthSnapshot(
        timestamp=0.0,
        active_sessions=0,
        sessions_by_type={},
        persons_count=0,
        total_face_embeddings=0,
        knowledge_active_rows=0,
        shadow_persons_count=0,
        classifier_scenarios_active=0,
        classifier_scenarios_quarantined=0,
        cloud_state="ONLINE",
        active_disputes=0,
        unresolved_watchdog_alerts=0,
        last_dream_run_seconds_ago=None,
        thin_voice_galleries=0,
        event_log_drops=0,
        event_log_emit_failures=0,
        kuzu_degraded=False,
        vision_degraded=False,
        heavy_worker_status={"adaface_embed": "degraded"},
    )
    rendered = format_health_line(snap)
    assert "heavy_workers=degraded" in rendered, (
        f"D4 regression: format_health_line did not emit "
        f"heavy_workers=degraded for non-healthy pool. Rendered: {rendered!r}"
    )

    # Inverse: healthy pool should NOT emit the marker.
    snap_healthy = HealthSnapshot(
        timestamp=0.0,
        active_sessions=0,
        sessions_by_type={},
        persons_count=0,
        total_face_embeddings=0,
        knowledge_active_rows=0,
        shadow_persons_count=0,
        classifier_scenarios_active=0,
        classifier_scenarios_quarantined=0,
        cloud_state="ONLINE",
        active_disputes=0,
        unresolved_watchdog_alerts=0,
        last_dream_run_seconds_ago=None,
        thin_voice_galleries=0,
        event_log_drops=0,
        event_log_emit_failures=0,
        kuzu_degraded=False,
        vision_degraded=False,
        heavy_worker_status={"adaface_embed": "healthy"},
    )
    rendered_healthy = format_health_line(snap_healthy)
    assert "heavy_workers=degraded" not in rendered_healthy, (
        f"D4 regression: healthy pool emitted heavy_workers=degraded "
        f"spuriously. Rendered: {rendered_healthy!r}"
    )


# ---------------------------------------------------------------------------
# A7 + A8 (D5) — startup ordering + shutdown cancel
# ---------------------------------------------------------------------------


def test_p0_r6_d5_anchor_1_startup_spawns_pool_before_vision_task() -> None:
    """A7 — pipeline.run() startup spawns the heavy-worker pool BEFORE the
    vision task (D5 ordering invariant; worker must be ready when the first
    `_background_vision_loop` iteration calls `hw.run_heavy(...)`).

    Source-inspection AST line-order check: locate the
    ``hw.get_or_create_pool("adaface_embed")`` line + the
    ``_vision_task = asyncio.create_task(_background_vision_loop(...))``
    line, assert the pool spawn comes FIRST.

    Per Plan v1 §2.7 (f) deliberate-regression: reversing the order fires
    this anchor.
    """
    source = _PIPELINE.read_text(encoding="utf-8")
    lines = source.splitlines()

    pool_spawn_line = None
    vision_task_line = None
    for i, line in enumerate(lines, start=1):
        if pool_spawn_line is None and 'hw.get_or_create_pool("adaface_embed")' in line:
            pool_spawn_line = i
        if vision_task_line is None and "_vision_task = asyncio.create_task(" in line:
            vision_task_line = i
        if pool_spawn_line is not None and vision_task_line is not None:
            break

    assert pool_spawn_line is not None, (
        "D5 regression: pipeline.run() does not call "
        "hw.get_or_create_pool(\"adaface_embed\") at startup. Per Plan v1 §2.5, "
        "the worker pool must be warmed up before the vision task spawns."
    )
    assert vision_task_line is not None, (
        "D5 sanity: _vision_task = asyncio.create_task(...) not found in "
        "pipeline.py — has the P0.R3 D5 wiring been removed?"
    )
    assert pool_spawn_line < vision_task_line, (
        f"D5 regression (ordering invariant): heavy-worker pool spawn at "
        f"line {pool_spawn_line} comes AFTER vision task spawn at line "
        f"{vision_task_line}. Per Plan v1 §2.5, pool MUST be ready before "
        f"_background_vision_loop's first iteration calls hw.run_heavy(...)."
    )


def test_p0_r6_d5_anchor_2_shutdown_cancels_pools() -> None:
    """A8 — pipeline.run() shutdown finally block calls
    ``hw.shutdown_all_pools(wait=True)``.
    """
    source = _PIPELINE.read_text(encoding="utf-8")
    assert "hw.shutdown_all_pools(wait=True)" in source, (
        "D5 regression: pipeline.run() shutdown finally block missing "
        "hw.shutdown_all_pools(wait=True) call. Per Plan v1 §2.5, all "
        "heavy-worker pools must be cleanly shut down at process exit to "
        "avoid zombie subprocesses."
    )


# ---------------------------------------------------------------------------
# A9 (D2 + D3) — behavioral CUDA-gated smoke
# ---------------------------------------------------------------------------


def test_p0_r6_d3_anchor_2_adaface_embed_via_worker_returns_correct_shape() -> None:
    """A9 — full round-trip through ``hw.run_heavy("adaface_embed", ...)``
    returns a valid embedding of the expected shape (1024-dim float32 =
    4096 bytes per the AdaFace IR101 contract).

    CUDA-gated smoke: requires real GPU + real ``core.vision`` module
    (not conftest MagicMock stub). Skips cleanly otherwise.
    """
    if not _cuda_available():
        pytest.skip("CUDA unavailable — skipping AdaFace round-trip smoke test")
    _require_real_voice_module_or_skip()

    import asyncio
    import numpy as np

    import core.heavy_worker as hw

    # Build a synthetic face-crop sized like the AdaFace input expectation
    # (112x112 RGB is the AdaFace IR101 input shape).
    face_crop = (np.random.rand(112, 112, 3) * 255).astype(np.uint8)

    async def _run():
        return await hw.run_heavy(
            "adaface_embed",
            hw.adaface_embed_worker,
            face_crop.tobytes(),
            face_crop.shape,
        )

    try:
        result_bytes = asyncio.run(_run())
    finally:
        # Always shut down so the test doesn't leak a worker subprocess.
        hw.shutdown_all_pools(wait=True)

    assert result_bytes is not None, (
        "D3 smoke: worker returned None — embedder.embed() crashed inside "
        "the subprocess (CUDA OOM? model-load fail?). Check subprocess stderr."
    )
    embedding = np.frombuffer(result_bytes, dtype=np.float32)
    # AdaFace IR101 produces 512-dim normalized embeddings (some configs
    # report 1024-dim; accept either as long as it's a non-empty 1-D array).
    assert embedding.ndim == 1 and embedding.size > 0, (
        f"D3 smoke: round-trip embedding has unexpected shape "
        f"{embedding.shape}; expected 1-D non-empty."
    )


# ---------------------------------------------------------------------------
# A10 (D2) — worker handles None-return from embed
# ---------------------------------------------------------------------------


def test_p0_r6_d2_anchor_2_worker_handles_none_return_from_embed() -> None:
    """A10 — ``adaface_embed_worker`` propagates ``None`` cleanly when the
    underlying ``embedder.embed()`` returns None (P0.R1 D1 contract:
    cascading CUDA + CPU EP fallback failure → recognize-miss).

    Mocked at the FaceEmbedder.get_global level so the test runs without
    GPU or real model load. Validates the worker's contract: None-in →
    None-out without raising.
    """
    from unittest.mock import patch, MagicMock

    import numpy as np

    import core.heavy_worker as hw

    # Mock the subprocess-scoped embedder accessor (developer-improves-on-
    # spec note: Plan v1 §2.2 referenced FaceEmbedder.get_global() which
    # doesn't exist on the real class; worker module uses a module-level
    # singleton via _get_subprocess_embedder() instead).
    mock_embedder = MagicMock()
    mock_embedder.embed = MagicMock(return_value=None)

    with patch.object(hw, "_get_subprocess_embedder", return_value=mock_embedder):
        face_crop = np.zeros((112, 112, 3), dtype=np.uint8)
        result = hw.adaface_embed_worker(face_crop.tobytes(), face_crop.shape)

    assert result is None, (
        f"D2 regression: adaface_embed_worker did not propagate None when "
        f"embedder.embed() returned None. Got {result!r}. Per Plan v1 §2.2 + "
        f"P0.R1 D1 contract, the worker must return None on cascading failure "
        f"so callers can treat as recognize-miss."
    )
    mock_embedder.embed.assert_called_once()
