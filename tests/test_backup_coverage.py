"""100% coverage for core.backup — daily SQLite online-backup + retention prune
(Wave 0 / Item 1). Part of the coverage-to-100 campaign. Complements
tests/test_backup.py by exercising the remaining defensive/branch lines:
missing dir, non-file entries, invalid-date + iterdir failures in the prune
loop, the config-default db_paths branch, and the two error-collection
handlers in run_daily_backup_pass."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import core.backup as backup_mod
from core.backup import prune_old_snapshots, run_daily_backup_pass

def _make_db(path: Path) -> Path:
    """Create a minimal valid SQLite DB at path (real file, no mocks)."""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (42)")
    conn.commit()
    conn.close()
    return path

# ── prune_old_snapshots: directory does not exist (line 97) ────────────────────

def test_prune_returns_empty_when_dir_missing(tmp_path):
    missing = tmp_path / "no_such_dir"
    assert not missing.exists()

    # snap_dir.exists() is False -> early `return deleted` (empty).
    result = prune_old_snapshots(str(missing))

    assert result == []

# ── prune_old_snapshots: non-file entry skipped (line 102) ─────────────────────

def test_prune_skips_non_file_entries(tmp_path):
    snap_dir = tmp_path / "snaps"
    snap_dir.mkdir()
    # A sub-directory inside the snapshot dir: iterdir() yields it, but
    # `f.is_file()` is False -> `continue` at line 102 (never reaches the regex).
    sub = snap_dir / "a_subdir"
    sub.mkdir()

    result = prune_old_snapshots(str(snap_dir), now=datetime(2026, 5, 6, 12, 0, 0))

    assert result == []
    assert sub.exists(), "sub-directory must be left untouched"

# ── prune_old_snapshots: dated-name file with invalid calendar date (112-113) ──

def test_prune_logs_and_skips_file_with_invalid_date(tmp_path, caplog):
    snap_dir = tmp_path / "snaps"
    snap_dir.mkdir()
    # Matches _DATED_FILENAME_RE (4-2-2 digits) but is not a valid calendar
    # date, so datetime.strptime raises inside the inner try -> warning branch.
    bad = snap_dir / "faces_db_9999-99-99.db"
    bad.write_text("x")

    with caplog.at_level(logging.WARNING):
        result = prune_old_snapshots(str(snap_dir), now=datetime(2026, 5, 6, 12, 0, 0))

    assert result == []
    assert bad.exists(), "file must NOT be deleted when its date fails to parse"
    assert "prune_old_snapshots skipped" in caplog.text

# ── prune_old_snapshots: iterdir() itself raises -> outer except (114-115) ──────

def test_prune_logs_when_iterdir_raises(monkeypatch, caplog):
    # exists() True so we enter the try; iterdir() explodes -> outer except.
    fake_dir = MagicMock()
    fake_dir.exists.return_value = True
    fake_dir.iterdir.side_effect = OSError("iterdir exploded")

    monkeypatch.setattr(backup_mod, "Path", lambda p: fake_dir)

    with caplog.at_level(logging.ERROR):
        result = prune_old_snapshots("whatever", now=datetime(2026, 5, 6, 12, 0, 0))

    assert result == []
    assert "prune_old_snapshots failed" in caplog.text

# ── run_daily_backup_pass: default db_paths from config + created (140-141, 154) ─

def test_run_pass_defaults_to_config_db_paths_and_records_created(tmp_path, monkeypatch):
    db1 = _make_db(tmp_path / "faces.db")
    db2 = _make_db(tmp_path / "brain.db")

    # Point the config constants the function imports at real temp DBs so the
    # `db_paths is None` branch resolves to them (no real production DB touched).
    import core.config as cfg
    monkeypatch.setattr(cfg, "DB_PATH", db1)
    monkeypatch.setattr(cfg, "BRAIN_DB_PATH", db2)

    snap_dir = tmp_path / "snaps"
    result = run_daily_backup_pass(snapshot_dir=str(snap_dir))  # db_paths omitted

    # Both temp DBs snapshotted -> `snapshots_created.append(dest)` fires twice.
    assert len(result["snapshots_created"]) == 2
    assert result["snapshots_skipped"] == []
    assert result["errors"] == []
    for dest in result["snapshots_created"]:
        assert Path(dest).exists()

    # Second run over the same day is idempotent -> the skip branch (line 156).
    result2 = run_daily_backup_pass(snapshot_dir=str(snap_dir))
    assert result2["snapshots_created"] == []
    assert len(result2["snapshots_skipped"]) == 2

# ── run_daily_backup_pass: exception from daily_snapshot collected (159-160) ────

def test_run_pass_collects_exception_from_daily_snapshot(tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("snapshot exploded")

    # daily_snapshot normally never raises; force it to so the loop's own
    # try/except at 159-160 fires and appends "{path}: {exc!r}".
    monkeypatch.setattr(backup_mod, "daily_snapshot", boom)
    # Keep prune quiet so it can't contribute a second, confusing error.
    monkeypatch.setattr(backup_mod, "prune_old_snapshots", lambda *_a, **_k: [])

    result = run_daily_backup_pass(
        db_paths=["/x/y.db"], snapshot_dir=str(tmp_path)
    )

    assert result["snapshots_created"] == []
    assert any("/x/y.db" in e and "snapshot exploded" in e for e in result["errors"])

# ── run_daily_backup_pass: exception from prune collected (165-166) ────────────

def test_run_pass_collects_exception_from_prune(tmp_path, monkeypatch):
    def boom_prune(*_a, **_k):
        raise RuntimeError("prune exploded")

    monkeypatch.setattr(backup_mod, "prune_old_snapshots", boom_prune)

    # Nonexistent parent dir -> sqlite3.connect fails inside daily_snapshot,
    # which fails soft (False, "") without raising; the loop finishes, then
    # the prune call raises -> the second except at 165-166 fires.
    result = run_daily_backup_pass(
        db_paths=["/nonexistent_dir/z.db"], snapshot_dir=str(tmp_path)
    )

    assert result["pruned"] == []
    assert any("prune failed" in e and "prune exploded" in e for e in result["errors"])
