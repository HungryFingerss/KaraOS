# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""Coverage completion for core/crash_logs.py — the P0.4 silent-except branches.

Targets the previously-uncovered exception paths in persist_crash_diagnostic
(79-84), prune_old_crash_logs (100-105 dir-fail, 111-115 unlink-fail), and
list_recent_crash_logs (128-133 dir-fail, 140-144 parse-fail), plus the
`now is None` default branches. External boundaries only are mocked: the
filesystem via tmp_path, and _crash_log_dir / Path.unlink via monkeypatch to
simulate unwritable-dir / unlink-denied failure modes.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import time

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# persist_crash_diagnostic: inner failure (79-84) → log warning + return None
# ─────────────────────────────────────────────────────────────────────────────
def test_persist_returns_none_when_crash_log_dir_raises(monkeypatch, caplog):
    from core import crash_logs

    def _boom_dir():
        raise OSError("FACES_DIR unwritable")

    monkeypatch.setattr(crash_logs, "_crash_log_dir", _boom_dir)

    with caplog.at_level(logging.WARNING):
        result = crash_logs.persist_crash_diagnostic(
            task_name="adaface_embed",
            exc=ValueError("boom"),
            traceback_str="Traceback...\n",
            crash_count=3,
            now=1717_000_000.5,
        )

    assert result is None, "persist must return None when the write path fails"
    assert "persist_crash_diagnostic failed" in caplog.text
    assert "adaface_embed" in caplog.text  # task_name interpolated into warning


# ─────────────────────────────────────────────────────────────────────────────
# persist_crash_diagnostic: now=None default branch (59-60) → uses time.time()
# ─────────────────────────────────────────────────────────────────────────────
def test_persist_defaults_now_to_time_time(tmp_path, monkeypatch):
    monkeypatch.setattr("core.config.FACES_DIR", tmp_path)
    from core import crash_logs

    before = time.time()
    path = crash_logs.persist_crash_diagnostic(
        task_name="ecapa_embed",
        exc=RuntimeError("x"),
        traceback_str="tb",
        crash_count=1,
        # now omitted → defaults to time.time()
    )
    after = time.time()

    assert path is not None and path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert before <= data["timestamp"] <= after


# ─────────────────────────────────────────────────────────────────────────────
# prune_old_crash_logs: dir-create failure (100-105) → log warning + return 0
# ─────────────────────────────────────────────────────────────────────────────
def test_prune_returns_zero_when_crash_log_dir_raises(monkeypatch, caplog):
    from core import crash_logs

    def _boom_dir():
        raise OSError("FACES_DIR unwritable")

    monkeypatch.setattr(crash_logs, "_crash_log_dir", _boom_dir)

    with caplog.at_level(logging.WARNING):
        removed = crash_logs.prune_old_crash_logs(retention_days=7, now=1717_000_000.0)

    assert removed == 0, "prune must return 0 when the dir cannot be accessed"
    assert "dir access failed" in caplog.text


# ─────────────────────────────────────────────────────────────────────────────
# prune_old_crash_logs: per-file unlink failure (111-115) → log warning + keep
# ─────────────────────────────────────────────────────────────────────────────
def test_prune_logs_and_survives_unlink_failure(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr("core.config.FACES_DIR", tmp_path)
    from core import crash_logs

    log_dir = tmp_path / "crash_logs"
    log_dir.mkdir()
    old = log_dir / "adaface_embed_2026-04-01T000000_000000.json"
    old.write_text("{}", encoding="utf-8")

    now = time.time()
    old_mtime = now - (10 * 86400)  # 10 days old vs retention_days=7 → eligible
    os.utime(old, (old_mtime, old_mtime))

    def _boom_unlink(self, *args, **kwargs):
        raise PermissionError(f"cannot unlink {self.name}")

    monkeypatch.setattr(pathlib.Path, "unlink", _boom_unlink)

    with caplog.at_level(logging.WARNING):
        removed = crash_logs.prune_old_crash_logs(retention_days=7, now=now)

    assert removed == 0, "unlink failure must not increment the removed count"
    assert old.exists(), "file must survive when unlink raised"
    assert "prune unlink failed" in caplog.text
    assert "adaface_embed_2026-04-01T000000_000000.json" in caplog.text


# ─────────────────────────────────────────────────────────────────────────────
# prune_old_crash_logs: now=None default branch (94-95) → empty dir returns 0
# ─────────────────────────────────────────────────────────────────────────────
def test_prune_defaults_now_and_returns_zero_on_empty_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("core.config.FACES_DIR", tmp_path)
    from core import crash_logs

    # No files created — dir auto-created, glob yields nothing, returns 0.
    removed = crash_logs.prune_old_crash_logs(retention_days=7)  # now omitted
    assert removed == 0


# ─────────────────────────────────────────────────────────────────────────────
# list_recent_crash_logs: dir-create failure (128-133) → log warning + return []
# ─────────────────────────────────────────────────────────────────────────────
def test_list_returns_empty_when_crash_log_dir_raises(monkeypatch, caplog):
    from core import crash_logs

    def _boom_dir():
        raise OSError("FACES_DIR unwritable")

    monkeypatch.setattr(crash_logs, "_crash_log_dir", _boom_dir)

    with caplog.at_level(logging.WARNING):
        results = crash_logs.list_recent_crash_logs(limit=5)

    assert results == [], "list must return [] when the dir cannot be accessed"
    assert "dir access failed" in caplog.text


# ─────────────────────────────────────────────────────────────────────────────
# list_recent_crash_logs: per-file parse failure (140-144) → skip corrupt + warn
# ─────────────────────────────────────────────────────────────────────────────
def test_list_skips_corrupt_json_and_warns(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr("core.config.FACES_DIR", tmp_path)
    from core import crash_logs

    log_dir = tmp_path / "crash_logs"
    log_dir.mkdir()

    good = log_dir / "adaface_embed_2026-05-25T000001_000000.json"
    good.write_text(json.dumps({"task_name": "adaface_embed", "id": 7}), encoding="utf-8")
    bad = log_dir / "adaface_embed_2026-05-25T000002_000000.json"
    bad.write_text("{ this is not valid json", encoding="utf-8")

    now = time.time()
    # Make the corrupt file the most-recent so it's definitely inside the limit
    # window and its parse-failure branch is exercised.
    os.utime(bad, (now, now))
    os.utime(good, (now - 10, now - 10))

    with caplog.at_level(logging.WARNING):
        results = crash_logs.list_recent_crash_logs(limit=10)

    assert len(results) == 1, "only the valid file should be returned"
    assert results[0]["id"] == 7
    assert "parse failed" in caplog.text
    assert "adaface_embed_2026-05-25T000002_000000.json" in caplog.text
