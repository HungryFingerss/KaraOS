"""Tests for core/backup.py — Wave 0 Item 1."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import inspect
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pytest

import core.backup as backup_mod
from core.backup import (
    daily_snapshot,
    prune_old_snapshots,
    run_daily_backup_pass,
)


def _make_db(path: Path) -> Path:
    """Create a minimal valid SQLite DB at path."""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (42)")
    conn.commit()
    conn.close()
    return path


# ---------------------------------------------------------------------------
# 1. daily_snapshot creates file with dated name
# ---------------------------------------------------------------------------

def test_daily_snapshot_creates_file_with_dated_name(tmp_path):
    db = _make_db(tmp_path / "faces.db")
    snap_dir = tmp_path / "snaps"
    today = date(2026, 5, 6)

    created, dest = daily_snapshot(str(db), snapshot_dir=str(snap_dir), today=today)

    assert created is True
    assert dest != ""
    dest_path = Path(dest)
    assert dest_path.exists()
    assert dest_path.name == "faces_db_2026-05-06.db"

    # Verify it's a valid SQLite DB
    conn = sqlite3.connect(str(dest_path))
    row = conn.execute("SELECT x FROM t").fetchone()
    conn.close()
    assert row == (42,)


# ---------------------------------------------------------------------------
# 2. Idempotent same-day call
# ---------------------------------------------------------------------------

def test_daily_snapshot_idempotent_same_day(tmp_path):
    db = _make_db(tmp_path / "faces.db")
    snap_dir = tmp_path / "snaps"
    today = date(2026, 5, 6)

    created1, dest1 = daily_snapshot(str(db), snapshot_dir=str(snap_dir), today=today)
    assert created1 is True

    # Record mtime of the first snapshot
    mtime_before = Path(dest1).stat().st_mtime

    created2, dest2 = daily_snapshot(str(db), snapshot_dir=str(snap_dir), today=today)
    assert created2 is False
    assert dest2 == dest1

    # File should NOT have been overwritten
    mtime_after = Path(dest2).stat().st_mtime
    assert mtime_after == mtime_before


# ---------------------------------------------------------------------------
# 3. Uses sqlite3 online backup API, NOT shutil.copy
# ---------------------------------------------------------------------------

def test_daily_snapshot_uses_sqlite_online_backup_api():
    src = inspect.getsource(backup_mod)
    assert ".backup(" in src, "daily_snapshot must use sqlite3 Connection.backup()"
    assert "shutil.copy" not in src, "daily_snapshot must NOT use shutil.copy"


# ---------------------------------------------------------------------------
# 4. Fail-soft on unwritable directory
# ---------------------------------------------------------------------------

def test_daily_snapshot_fails_soft_on_unwritable_dir(tmp_path, monkeypatch):
    db = _make_db(tmp_path / "faces.db")

    # Pass a path inside a file (not a directory) — always unwritable
    fake_dir = tmp_path / "not_a_dir.txt"
    fake_dir.write_text("block")

    created, dest = daily_snapshot(str(db), snapshot_dir=str(fake_dir / "snaps"))
    assert created is False
    assert dest == ""


# ---------------------------------------------------------------------------
# 5. prune_old_snapshots deletes files past retention
# ---------------------------------------------------------------------------

def test_prune_old_snapshots_deletes_files_past_retention(tmp_path):
    snap_dir = tmp_path / "snaps"
    snap_dir.mkdir()
    now = datetime(2026, 5, 6, 12, 0, 0)

    # Files at various ages
    ages = {1: "faces_db_2026-05-05.db",
            15: "faces_db_2026-04-21.db",
            30: "faces_db_2026-04-06.db",
            31: "faces_db_2026-04-05.db",
            40: "faces_db_2026-03-27.db"}

    for days_ago, name in ages.items():
        file_date = (now - __import__("datetime").timedelta(days=days_ago)).strftime("%Y-%m-%d")
        # Reconstruct name deterministically from age
        f = snap_dir / name
        f.write_text("x")

    pruned = prune_old_snapshots(str(snap_dir), retention_days=30, now=now)

    pruned_names = {Path(p).name for p in pruned}
    assert "faces_db_2026-04-05.db" in pruned_names   # 31 days — should be pruned
    assert "faces_db_2026-03-27.db" in pruned_names   # 40 days — should be pruned

    # Files within retention should remain
    assert (snap_dir / "faces_db_2026-05-05.db").exists()   # 1 day
    assert (snap_dir / "faces_db_2026-04-21.db").exists()   # 15 days
    assert (snap_dir / "faces_db_2026-04-06.db").exists()   # 30 days — boundary, NOT pruned


# ---------------------------------------------------------------------------
# 6. prune_old_snapshots only matches dated filename pattern
# ---------------------------------------------------------------------------

def test_prune_old_snapshots_only_matches_dated_filename_pattern(tmp_path):
    snap_dir = tmp_path / "snaps"
    snap_dir.mkdir()
    now = datetime(2026, 5, 6, 12, 0, 0)

    # A very old dated snapshot (should be pruned)
    old_snap = snap_dir / "faces_db_2025-01-01.db"
    old_snap.write_text("x")

    # Unrelated files — must NOT be touched
    random_db = snap_dir / "random_file.db"
    notes = snap_dir / "notes.txt"
    random_db.write_text("keep me")
    notes.write_text("keep me")

    prune_old_snapshots(str(snap_dir), retention_days=30, now=now)

    assert random_db.exists(), "random_file.db must not be deleted"
    assert notes.exists(), "notes.txt must not be deleted"
    assert not old_snap.exists(), "old dated snapshot should have been pruned"


# ---------------------------------------------------------------------------
# 7. run_daily_backup_pass collects errors without raising
# ---------------------------------------------------------------------------

def test_run_daily_backup_pass_collects_errors_without_raising(tmp_path):
    snap_dir = tmp_path / "snaps"
    result = run_daily_backup_pass(
        db_paths=["/nonexistent/path/that/does/not/exist.db"],
        snapshot_dir=str(snap_dir),
    )

    assert isinstance(result, dict)
    assert "errors" in result
    assert len(result["errors"]) > 0
    # Must not raise — function returned normally


# ---------------------------------------------------------------------------
# 8. Pipeline dream loop invokes backup when enabled — source inspection
# ---------------------------------------------------------------------------

def test_pipeline_dream_loop_invokes_backup_when_enabled():
    import os
    # P1.A1 SP-6.4: _dream_loop relocated to runtime/background_loops.py.
    loops_path = os.path.join(
        os.path.dirname(__file__), "..", "runtime", "background_loops.py"
    )
    src = open(loops_path, encoding="utf-8").read()

    assert "run_daily_backup_pass" in src, (
        "background_loops.py must call run_daily_backup_pass in the dream loop"
    )
    assert "DAILY_BACKUP_ENABLED" in src, (
        "background_loops.py must gate backup on config.DAILY_BACKUP_ENABLED"
    )
