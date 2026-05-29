"""
Tests for core/disk_monitor.py — Wave 5 / Item 20.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import os
import pytest
from unittest.mock import MagicMock, patch

from core.disk_monitor import (
    DiskSnapshot,
    gather_disk_snapshot,
    check_disk_thresholds,
    reset_alert_level,
)


@pytest.fixture(autouse=True)
def reset_module_alert_level():
    reset_alert_level()
    yield
    reset_alert_level()


def _make_snapshot(pct: float, free: int = 5_000_000_000) -> DiskSnapshot:
    total = 100_000_000_000
    used = int(total * pct / 100)
    return DiskSnapshot(
        total_bytes=total,
        used_bytes=used,
        free_bytes=free,
        percent_used=pct,
        per_directory_bytes={},
    )


class TestGatherDiskSnapshot:
    def test_returns_total_used_free_percent(self, tmp_path):
        snap = gather_disk_snapshot(root_path=str(tmp_path), monitored_dirs=[])
        assert snap.total_bytes > 0
        assert snap.used_bytes >= 0
        assert snap.free_bytes >= 0
        assert 0.0 <= snap.percent_used <= 100.0

    def test_per_directory_size_correct_for_existing_dir(self, tmp_path):
        d = tmp_path / "testdir"
        d.mkdir()
        (d / "file.txt").write_bytes(b"x" * 1000)
        snap = gather_disk_snapshot(root_path=str(tmp_path), monitored_dirs=[str(d)])
        assert snap.per_directory_bytes[str(d)] == 1000

    def test_per_directory_size_returns_zero_for_missing_dir(self, tmp_path):
        missing = str(tmp_path / "nonexistent")
        snap = gather_disk_snapshot(root_path=str(tmp_path), monitored_dirs=[missing])
        assert snap.per_directory_bytes[missing] == 0


class TestCheckDiskThresholds:
    def test_fires_warning_at_80_percent(self):
        from core.config import DISK_ALERT_WARNING_PCT
        snap = _make_snapshot(float(DISK_ALERT_WARNING_PCT) + 0.5)
        fake_orch = MagicMock()
        result = check_disk_thresholds(snap, fake_orch)
        assert result is not None
        assert "warning" in result or "disk" in result
        fake_orch.watchdog.report_disk_threshold.assert_called_once()

    def test_does_not_re_fire_same_level(self):
        from core.config import DISK_ALERT_WARNING_PCT
        pct = float(DISK_ALERT_WARNING_PCT) + 0.5
        snap = _make_snapshot(pct)
        fake_orch = MagicMock()
        first = check_disk_thresholds(snap, fake_orch)
        second = check_disk_thresholds(snap, fake_orch)
        assert first is not None
        assert second is None
        assert fake_orch.watchdog.report_disk_threshold.call_count == 1

    def test_escalates_at_90_percent(self):
        from core.config import DISK_ALERT_WARNING_PCT, DISK_ALERT_CRITICAL_PCT
        # Fire warning first
        snap_warn = _make_snapshot(float(DISK_ALERT_WARNING_PCT) + 0.5)
        fake_orch = MagicMock()
        check_disk_thresholds(snap_warn, fake_orch)

        # Now escalate to critical
        snap_crit = _make_snapshot(float(DISK_ALERT_CRITICAL_PCT) + 0.5)
        result = check_disk_thresholds(snap_crit, fake_orch)
        assert result is not None
        assert fake_orch.watchdog.report_disk_threshold.call_count == 2
