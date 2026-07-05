"""100% coverage for core.vision_provider_state — the CUDA/CPU provider state
machine (P0.R2 D4). Global state, so each test resets first. Part of the
coverage-to-100 campaign (see COVERAGE.md)."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import pytest

import core.vision_provider_state as vps


@pytest.fixture(autouse=True)
def _reset():
    vps.reset_for_tests()
    yield
    vps.reset_for_tests()


def test_default_provider_is_cuda():
    assert vps.get_active_provider() == "cuda"


def test_record_failure_switches_to_cpu_and_arms_counter(monkeypatch):
    monkeypatch.setattr(vps, "VISION_CPU_SWITCH_N_REQUESTS", 3)
    vps.record_cuda_failure()
    assert vps.get_active_provider() == "cpu"
    assert vps._cpu_requests_remaining == 3


def test_success_counter_restores_cuda_when_exhausted(monkeypatch):
    monkeypatch.setattr(vps, "VISION_CPU_SWITCH_N_REQUESTS", 2)
    vps.record_cuda_failure()
    vps.record_success("cpu")
    assert vps.get_active_provider() == "cpu"  # 1 remaining
    vps.record_success("cpu")
    assert vps.get_active_provider() == "cuda"  # exhausted -> restored


def test_success_noop_when_already_cuda():
    vps.record_success("cpu")  # active is cuda -> early return
    assert vps.get_active_provider() == "cuda"


def test_failure_noop_when_cpu_only_permanent():
    vps.set_cpu_only_permanent()
    vps.record_cuda_failure()  # early return, stays cpu-only
    assert vps.get_active_provider() == "cpu" and vps._cpu_only_permanent


def test_success_noop_when_cpu_only_permanent():
    vps.set_cpu_only_permanent()
    vps.record_success("cpu")  # early return
    assert vps._cpu_requests_remaining == 0


def test_retry_timer_restores_cuda_after_m_minutes(monkeypatch):
    monkeypatch.setattr(vps, "VISION_CUDA_RETRY_M_MINUTES", 5.0)
    vps.record_cuda_failure()
    switched = vps._cpu_switch_at
    vps.maybe_retry_cuda(switched + 6 * 60)  # 6 min > 5 -> restore
    assert vps.get_active_provider() == "cuda"


def test_retry_timer_holds_before_m_minutes(monkeypatch):
    monkeypatch.setattr(vps, "VISION_CUDA_RETRY_M_MINUTES", 5.0)
    vps.record_cuda_failure()
    vps.maybe_retry_cuda(vps._cpu_switch_at + 60)  # 1 min < 5 -> stay cpu
    assert vps.get_active_provider() == "cpu"


def test_retry_noop_when_no_switch_recorded():
    vps._active_provider = "cpu"  # force cpu without a switch timestamp
    vps._cpu_switch_at = None
    vps.maybe_retry_cuda(1_000_000.0)  # _cpu_switch_at is None -> return
    assert vps.get_active_provider() == "cpu"


def test_retry_noop_when_already_cuda():
    vps.maybe_retry_cuda(1_000_000.0)  # active cuda -> early return
    assert vps.get_active_provider() == "cuda"


def test_reset_restores_defaults():
    vps.set_cpu_only_permanent()
    vps.reset_for_tests()
    assert vps.get_active_provider() == "cuda" and not vps._cpu_only_permanent
