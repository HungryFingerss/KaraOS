"""P0.R9 VRAM budget guard — 9 anchors per Plan v1 §3 LOCK.

Coverage map:
- A1: core/config.py D1 constants (HEAVY_WORKER_VRAM_ESTIMATES_MB + VRAM_CEILING_PCT + VRAM_POOL_PRIORITY) — source
- A2: core/heavy_worker.py D2 helper + state (check_vram_budget + peek_refused_pools + _REFUSED_POOLS + _VRAM_CHECK_LOCK) — source AST
- A3: D3 get_or_create_pool returns None when budget exceeded — BEHAVIORAL (monkeypatched torch)
- A4: D3 high-priority pool spawns when low-priority refused — BEHAVIORAL (monkeypatched torch)
- A5: D4 run_heavy returns None when pool is None — BEHAVIORAL
- A6: D2 _REFUSED_POOLS caches refusal — BEHAVIORAL (mem_get_info called once)
- A7: D5 WatchdogAgent.report_vram_budget_refusal method + store_alert call — source + behavioral
- A8: D6 HealthSnapshot.vram_budget field + format_health_line vram_refused=N + 5 verbatim substrings in alerts
- A9: Non-CUDA skip enforcement — BEHAVIORAL (torch.cuda.is_available False)
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import asyncio
import concurrent.futures
import concurrent.futures.process
import pathlib
import time

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


# ─────────────────────────────────────────────────────────────────────────────
# Shared CUDA monkeypatch helper for A3/A4/A5/A6/A9
# ─────────────────────────────────────────────────────────────────────────────
def _mock_cuda_with_total_mb(monkeypatch, total_mb: int, available: bool = True):
    """Stub torch.cuda.is_available + mem_get_info to a known total VRAM.

    `total_mb=100` means tiny GPU; budget will refuse Whisper (3000MB estimate).
    `total_mb=10000` means plenty; all 4 pools fit (~6300MB cumulative < 8000MB ceiling).
    `available=False` simulates a no-CUDA dev/CI environment.
    """
    import torch
    monkeypatch.setattr(torch.cuda, "is_available", lambda: available)
    if available:
        # mem_get_info returns (free_bytes, total_bytes)
        bytes_total = total_mb * 1024 * 1024
        monkeypatch.setattr(torch.cuda, "mem_get_info", lambda: (bytes_total, bytes_total))


# ─────────────────────────────────────────────────────────────────────────────
# A1: config constants present with sanity values
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r9_d1_config_constants_present():
    from core import config
    assert hasattr(config, "HEAVY_WORKER_VRAM_ESTIMATES_MB"), "constant missing"
    estimates = config.HEAVY_WORKER_VRAM_ESTIMATES_MB
    assert isinstance(estimates, dict)
    for pool in ("adaface_embed", "ecapa_embed", "whisper_transcribe", "pyannote_diarize"):
        assert pool in estimates, f"pool '{pool}' missing from HEAVY_WORKER_VRAM_ESTIMATES_MB"
        assert isinstance(estimates[pool], int) and estimates[pool] > 0

    assert hasattr(config, "VRAM_CEILING_PCT")
    assert config.VRAM_CEILING_PCT == 80.0

    assert hasattr(config, "VRAM_POOL_PRIORITY")
    priority = config.VRAM_POOL_PRIORITY
    assert isinstance(priority, list)
    assert len(priority) == 4
    assert set(priority) == {"adaface_embed", "ecapa_embed", "whisper_transcribe", "pyannote_diarize"}
    assert priority[0] == "adaface_embed"  # highest priority


# ─────────────────────────────────────────────────────────────────────────────
# A2: D2 helper + module state present (AST)
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r9_d2_check_vram_budget_helper_exists():
    src = (REPO_ROOT / "core" / "heavy_worker.py").read_text(encoding="utf-8")
    assert "def check_vram_budget(" in src, "check_vram_budget function missing"
    assert "def peek_refused_pools(" in src, "peek_refused_pools function missing"
    assert "_REFUSED_POOLS:" in src and "set()" in src, "_REFUSED_POOLS module state missing"
    assert "_VRAM_CHECK_LOCK = threading.Lock()" in src, "_VRAM_CHECK_LOCK missing"

    # AST verification: 2 functions at module scope
    mod = ast.parse(src)
    fn_names = {n.name for n in mod.body if isinstance(n, ast.FunctionDef)}
    assert "check_vram_budget" in fn_names
    assert "peek_refused_pools" in fn_names


# ─────────────────────────────────────────────────────────────────────────────
# A3: D3 get_or_create_pool returns None when budget exceeded
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r9_d3_get_or_create_pool_returns_none_when_budget_exceeded(monkeypatch):
    import core.heavy_worker as hw

    # Reset module state
    hw._HEAVY_WORKER_POOLS.clear()
    hw._REFUSED_POOLS.clear()

    # Tiny GPU: 100MB total, 80MB ceiling — Whisper (3000MB) WILL be refused
    _mock_cuda_with_total_mb(monkeypatch, total_mb=100, available=True)

    pool = hw.get_or_create_pool("whisper_transcribe")
    assert pool is None, "expected None on budget refusal; got %r" % pool
    assert "whisper_transcribe" in hw._REFUSED_POOLS
    # Pool registry should NOT have whisper key (we returned None before creation)
    assert "whisper_transcribe" not in hw._HEAVY_WORKER_POOLS


# ─────────────────────────────────────────────────────────────────────────────
# A4: D3 high-priority pool spawns when low-priority refused
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r9_d3_high_priority_pool_spawns_when_low_priority_refused(monkeypatch):
    import core.heavy_worker as hw

    hw._HEAVY_WORKER_POOLS.clear()
    hw._REFUSED_POOLS.clear()

    # Ceiling such that AdaFace (100MB) fits but Whisper (3000MB) doesn't
    # 1000MB total × 80% = 800MB ceiling. AdaFace 100MB fits. Whisper would push to 3100MB.
    _mock_cuda_with_total_mb(monkeypatch, total_mb=1000, available=True)

    pool_adaface = hw.get_or_create_pool("adaface_embed")
    assert pool_adaface is not None, "AdaFace should fit in budget"
    assert "adaface_embed" in hw._HEAVY_WORKER_POOLS

    pool_whisper = hw.get_or_create_pool("whisper_transcribe")
    assert pool_whisper is None, "Whisper should be refused"
    assert "whisper_transcribe" in hw._REFUSED_POOLS

    # Cleanup spawned pool
    if pool_adaface is not None:
        pool_adaface.shutdown(wait=False)
    hw._HEAVY_WORKER_POOLS.clear()


# ─────────────────────────────────────────────────────────────────────────────
# A5: D4 run_heavy returns None when pool is None
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_p0_r9_d4_run_heavy_returns_none_when_pool_none(monkeypatch):
    import core.heavy_worker as hw

    hw._HEAVY_WORKER_POOLS.clear()
    hw._REFUSED_POOLS.clear()

    # Monkeypatch get_or_create_pool to return None
    monkeypatch.setattr(hw, "get_or_create_pool", lambda task_name, max_workers=1: None)

    def _fn():
        return "should_not_run"

    result = await hw.run_heavy("p0_r9_a5_test", _fn)
    assert result is None, f"expected None on None pool; got {result!r}"


# ─────────────────────────────────────────────────────────────────────────────
# A6: D2 _REFUSED_POOLS caches refusal — second call from cache
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r9_d2_refused_pools_cached(monkeypatch):
    import core.heavy_worker as hw

    hw._HEAVY_WORKER_POOLS.clear()
    hw._REFUSED_POOLS.clear()

    # Set up a counter on torch.cuda.mem_get_info via lambda
    import torch
    call_count = {"n": 0}
    bytes_total = 100 * 1024 * 1024

    def _mem_get_info():
        call_count["n"] += 1
        return (bytes_total, bytes_total)

    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "mem_get_info", _mem_get_info)

    # First call — should refuse + cache + invoke mem_get_info ONCE
    result1 = hw.check_vram_budget("whisper_transcribe")
    assert result1 is False
    assert call_count["n"] == 1
    assert "whisper_transcribe" in hw._REFUSED_POOLS

    # Second call — should return False from cache (mem_get_info NOT called again)
    result2 = hw.check_vram_budget("whisper_transcribe")
    assert result2 is False
    assert call_count["n"] == 1, "mem_get_info called again — cache miss!"


# ─────────────────────────────────────────────────────────────────────────────
# A7: D5 WatchdogAgent.report_vram_budget_refusal method
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r9_d5_watchdog_report_vram_budget_refusal():
    src = (REPO_ROOT / "core" / "brain_agent.py").read_text(encoding="utf-8")
    assert "def report_vram_budget_refusal(" in src, "method missing"

    # AST verification: method exists on WatchdogAgent + calls store_alert with vram_budget_refusal_ prefix
    mod = ast.parse(src)
    found_method = False
    found_store_alert = False
    for cls in ast.walk(mod):
        if not (isinstance(cls, ast.ClassDef) and cls.name == "WatchdogAgent"):
            continue
        for fn in cls.body:
            if not (isinstance(fn, ast.FunctionDef) and fn.name == "report_vram_budget_refusal"):
                continue
            found_method = True
            for sub in ast.walk(fn):
                if not isinstance(sub, ast.Call):
                    continue
                src_str = ast.unparse(sub)
                if "store_alert" in src_str and "vram_budget_refusal_" in src_str:
                    found_store_alert = True

    assert found_method, "WatchdogAgent.report_vram_budget_refusal not found at AST scan"
    assert found_store_alert, "store_alert call with vram_budget_refusal_ prefix missing"


# ─────────────────────────────────────────────────────────────────────────────
# A8: D6 HealthSnapshot.vram_budget field + format_health_line + format_health_alerts
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r9_d6_health_snapshot_vram_budget_field_and_alerts():
    from core import health
    from dataclasses import fields

    field_names = {f.name for f in fields(health.HealthSnapshot)}
    assert "vram_budget" in field_names, f"vram_budget field missing; got: {field_names}"

    # Build snapshot with refused_pools non-empty
    now = time.time()
    snap = health.HealthSnapshot(
        timestamp=now,
        active_sessions=0,
        sessions_by_type={"best_friend": 0, "known": 0, "stranger": 0, "disputed": 0},
        persons_count=0,
        total_face_embeddings=0,
        knowledge_active_rows=0,
        shadow_persons_count=0,
        classifier_scenarios_active=0,
        classifier_scenarios_quarantined=0,
        cloud_state="OFFLINE",
        active_disputes=0,
        unresolved_watchdog_alerts=0,
        last_dream_run_seconds_ago=None,
        thin_voice_galleries=[],
        vram_budget={
            "refused_pools": ["whisper_transcribe", "pyannote_diarize"],
            "active_pools": ["adaface_embed", "ecapa_embed"],
        },
    )

    line = health.format_health_line(snap)
    assert "vram_refused=2" in line, f"Expected `vram_refused=2` in health line; got: {line}"

    class _StubBrain:
        class _stub:
            class _conn:
                @staticmethod
                def execute(*a, **kw):
                    return []
            _conn = _conn()
        _brain_db = _stub()
        _kuzu_degraded = False

    alerts = health.format_health_alerts(snap, _StubBrain())
    alerts_text = " ".join(alerts)
    for substring in (
        "VRAM budget refusal",
        "pools refused:",
        "VRAM_POOL_PRIORITY",
        "VRAM_CEILING_PCT",
        "HEAVY_WORKER_VRAM_ESTIMATES_MB",
    ):
        assert substring in alerts_text, f"Verbatim substring '{substring}' missing: {alerts_text}"


# ─────────────────────────────────────────────────────────────────────────────
# A9: Non-CUDA skip enforcement
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r9_non_cuda_skip_budget_enforcement(monkeypatch):
    import core.heavy_worker as hw
    import torch

    hw._HEAVY_WORKER_POOLS.clear()
    hw._REFUSED_POOLS.clear()

    mem_calls = {"n": 0}

    def _should_not_be_called():
        mem_calls["n"] += 1
        return (100 * 1024 * 1024, 100 * 1024 * 1024)

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(torch.cuda, "mem_get_info", _should_not_be_called)

    # Non-CUDA env → check_vram_budget returns True without probing mem
    result = hw.check_vram_budget("whisper_transcribe")
    assert result is True, "non-CUDA should skip enforcement"
    assert mem_calls["n"] == 0, "mem_get_info should NOT be called on non-CUDA"
    assert "whisper_transcribe" not in hw._REFUSED_POOLS, "non-CUDA should not refuse"
