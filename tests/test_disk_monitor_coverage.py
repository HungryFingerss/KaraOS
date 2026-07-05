# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""100% coverage for core.disk_monitor — disk usage snapshot + idempotent
threshold alerts (Wave 5 / Item 20). Part of the coverage-to-100 campaign
(see COVERAGE.md). Global alert state, so each test resets first."""

import logging

import pytest
from unittest.mock import MagicMock

import core.disk_monitor as disk_monitor
from core.disk_monitor import (
    DiskSnapshot,
    format_disk_line,
    gather_disk_snapshot,
    check_disk_thresholds,
    reset_alert_level,
    _human_bytes,
    _dir_size,
)


@pytest.fixture(autouse=True)
def _reset_alert_level():
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


# ── gather_disk_snapshot: default monitored_dirs branch (lines 47-48) ──────────


def test_gather_defaults_to_config_monitored_dirs(tmp_path, monkeypatch):
    # Stub _dir_size so we don't walk the real faces/ + data/ dirs (fast + deterministic).
    monkeypatch.setattr(disk_monitor, "_dir_size", lambda p: 0)
    from core.config import DISK_MONITORED_DIRS

    snap = gather_disk_snapshot(root_path=str(tmp_path))  # monitored_dirs omitted

    assert set(snap.per_directory_bytes.keys()) == set(DISK_MONITORED_DIRS)
    assert all(v == 0 for v in snap.per_directory_bytes.values())
    assert snap.total_bytes > 0


# ── _dir_size: exception paths (lines 76-79) ───────────────────────────────────


def test_dir_size_skips_file_that_vanished_mid_walk(monkeypatch):
    # is_file() True, but the explicit .stat() raises OSError -> inner except: pass.
    vanished = MagicMock()
    vanished.is_file.return_value = True
    vanished.stat.side_effect = OSError("file vanished mid-walk")

    fake_root = MagicMock()
    fake_root.exists.return_value = True
    fake_root.rglob.return_value = [vanished]

    monkeypatch.setattr(disk_monitor, "Path", lambda p: fake_root)

    assert _dir_size("whatever") == 0


def test_dir_size_logs_and_returns_zero_when_walk_raises(monkeypatch, caplog):
    # rglob() itself raises -> outer except Exception logs a warning.
    fake_root = MagicMock()
    fake_root.exists.return_value = True
    fake_root.rglob.side_effect = RuntimeError("walk exploded")

    monkeypatch.setattr(disk_monitor, "Path", lambda p: fake_root)

    with caplog.at_level(logging.WARNING):
        result = _dir_size("blocked_dir")

    assert result == 0
    assert "_dir_size(blocked_dir) failed" in caplog.text


def test_dir_size_sums_real_files(tmp_path):
    # Positive path: two real files summed correctly (guards the happy path).
    (tmp_path / "a.bin").write_bytes(b"x" * 300)
    (tmp_path / "b.bin").write_bytes(b"y" * 700)
    assert _dir_size(str(tmp_path)) == 1000


# ── format_disk_line: full line + zero-dir skip (lines 84-93) ──────────────────


def test_format_disk_line_renders_nonzero_dirs_and_skips_zero():
    snap = DiskSnapshot(
        total_bytes=100_000_000_000,
        used_bytes=50_000_000_000,
        free_bytes=50_000_000_000,
        percent_used=50.0,
        per_directory_bytes={"faces/": 124_000_000, "empty/": 0},
    )

    line = format_disk_line(snap)

    assert line.startswith("[Disk] ")
    assert "used=50.0GB/100GB (50.0%)" in line
    assert "faces=124MB" in line  # non-zero dir rendered (rstrip('/') + _human_bytes)
    assert "empty" not in line    # zero-byte dir skipped by `if b == 0: continue`


# ── _human_bytes: KB and MB branches (lines 98, 100) ───────────────────────────


def test_human_bytes_kb_branch():
    assert _human_bytes(500_000) == "500KB"


def test_human_bytes_mb_branch():
    assert _human_bytes(124_000_000) == "124MB"


def test_human_bytes_gb_branch():
    assert _human_bytes(2_500_000_000) == "2.5GB"


# ── check_disk_thresholds: blocker level (line 120) ────────────────────────────


def test_check_thresholds_fires_blocker_at_95():
    snap = _make_snapshot(96.0)
    fake_orch = MagicMock()

    result = check_disk_thresholds(snap, fake_orch)

    assert result == "disk_critical_95"
    fake_orch.watchdog.report_disk_threshold.assert_called_once()
    _, kwargs = fake_orch.watchdog.report_disk_threshold.call_args
    assert kwargs["level"] == 95
    assert kwargs["severity"] == "critical"


# ── check_disk_thresholds: report failure logged (lines 146-147) ───────────────


def test_check_thresholds_logs_when_report_raises(caplog):
    snap = _make_snapshot(85.0)  # warning level
    fake_orch = MagicMock()
    fake_orch.watchdog.report_disk_threshold.side_effect = RuntimeError("boom")

    with caplog.at_level(logging.ERROR):
        result = check_disk_thresholds(snap, fake_orch)

    assert result is None  # exception swallowed, falls through to return None
    assert "alert fire failed" in caplog.text
    # Alert level was NOT advanced (the fire failed before the assignment).
    assert disk_monitor._last_disk_alert_level == 0


# ── check_disk_thresholds: reset when usage drops (line 150) ───────────────────


def test_check_thresholds_resets_level_when_usage_drops():
    fake_orch = MagicMock()

    # Fire critical (level -> 90).
    first = check_disk_thresholds(_make_snapshot(91.0), fake_orch)
    assert first is not None
    assert disk_monitor._last_disk_alert_level == 90

    # Usage drops well below warning -> new_level 0 < 90 -> reset branch, returns None.
    dropped = check_disk_thresholds(_make_snapshot(50.0), fake_orch)
    assert dropped is None
    assert disk_monitor._last_disk_alert_level == 0

    # Because the level reset, crossing warning again re-alerts.
    reagain = check_disk_thresholds(_make_snapshot(85.0), fake_orch)
    assert reagain is not None
    assert fake_orch.watchdog.report_disk_threshold.call_count == 2
