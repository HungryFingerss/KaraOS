"""Latency D2 (Canary #2) — heavy-worker pool warm-up at boot, source-inspection.

The runtime proof is the Layer-4 canary (first-turn latency < ~2s). This unit layer
asserts the structural contract: run() fires a `hw.run_heavy(...)` warm for each of the
four heavy-worker pools, parallelized, and AWAITS it BEFORE '[Pipeline] All systems ready'
(a backgrounded warm loses the race against a user who speaks ~3s after boot).

Spec: tests/pipeline_latency_fix_spec.md §2 D2 + §3 Layer 1.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PIPELINE = REPO_ROOT / "pipeline.py"

_FOUR_POOLS = ("adaface_embed", "whisper_transcribe", "ecapa_embed", "pyannote_diarize")


@pytest.fixture(scope="module")
def pipeline_src() -> str:
    return PIPELINE.read_text(encoding="utf-8")


def _func_src(src: str, name: str) -> str:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"function {name} not found in pipeline.py")


def test_d2_warm_function_exists_and_warms_all_four_pools(pipeline_src):
    """`_warm_heavy_worker_pools` fires a run_heavy warm for each of the 4 pools."""
    body = _func_src(pipeline_src, "_warm_heavy_worker_pools")
    assert "hw.run_heavy(" in body, "warm function must call hw.run_heavy"
    for pool in _FOUR_POOLS:
        assert f'"{pool}"' in body, f"warm function must warm the {pool!r} pool"
    # Parallel, not serial — boot cost ≈ slowest pool, not the sum.
    assert "asyncio.gather(" in body, "the 4 warms must be gathered in parallel"


def test_d2_warm_is_non_fatal_per_pool(pipeline_src):
    """Each warm is try/except (a degraded/VRAM-refused pool must not block boot)."""
    body = _func_src(pipeline_src, "_warm_heavy_worker_pools")
    assert "try:" in body and "except" in body, (
        "warm must tolerate a degraded pool (run_heavy → None / raises) non-fatally"
    )


def test_d2_warm_awaited_before_all_systems_ready(pipeline_src):
    """run() awaits `_warm_heavy_worker_pools()` BEFORE the 'All systems ready' print.

    This is the load-bearing ordering: backgrounding the warm (or running it after the
    ready print) loses the race against a user who speaks ~3s after boot — the exact
    canary #2 failure mode.
    """
    run_src = _func_src(pipeline_src, "run")
    warm_idx = run_src.find("await _warm_heavy_worker_pools()")
    ready_idx = run_src.find("All systems ready")
    assert warm_idx >= 0, "run() must `await _warm_heavy_worker_pools()`"
    assert ready_idx >= 0, "run() must print 'All systems ready'"
    assert warm_idx < ready_idx, (
        "the heavy-worker warm MUST be awaited BEFORE 'All systems ready' — "
        "a warm that runs after (or is backgrounded) loses the race against an "
        "early speaker (canary #2 failure mode)."
    )
    # And it must be a direct `await`, not a fire-and-forget create_task.
    assert "create_task(_warm_heavy_worker_pools" not in run_src, (
        "the warm must be awaited, not backgrounded via create_task"
    )
