"""100% line coverage for runtime.log_capture — the terminal-output log harness.
Part of the coverage-to-100 campaign (see COVERAGE.md / CLAUDE.md).

Exercises every previously-uncovered line and both sides of every uncovered
branch: the archive rename-failure handler (58-65), the size-cap early returns
+ close-except + outer-except (90, 99-100, 110-112), the prune per-file /
glob failure swallows (141-144), the entire `_log_drain` daemon loop including
inner write-excepts, the outer-loop exception wrap, and the stderr-unavailable
fallback (170-194), and the `_Tee` proxy (199, 201-203) plus flush/__getattr__.

runtime.log_capture imports headless (time + datetime + pathlib + queue only,
no GPU/camera/network/model downloads) and starts no threads at import, so the
only mocking is at external boundaries: the filesystem via pytest ``tmp_path``,
``pathlib.Path`` fs methods + ``core.config`` constants + the module globals
(_log_q / _LOG_FILE / _LOG_PATH / counters) via monkeypatch, and stdout/stderr
via capsys + a fake ``sys.__stderr__``. The `while True` drain loop is broken
with a ``KeyboardInterrupt`` — a BaseException the loop's ``except Exception``
deliberately does not catch — which is the clean, deterministic way out.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import datetime
import os
import pathlib
import sys
import time
from unittest.mock import MagicMock

import pytest

from runtime import log_capture as lc


# ─────────────────────────────────────────────────────────────────────────────
# Test doubles
# ─────────────────────────────────────────────────────────────────────────────
class _ScriptedQueue:
    """Fake replacement for ``_log_q`` — ``.get()`` plays a scripted list.

    Each action is either a ``(stream, data)`` tuple to return or a
    ``BaseException`` instance to raise. When the script is exhausted, ``.get()``
    raises ``KeyboardInterrupt`` — a BaseException the drain's ``except
    Exception`` does NOT catch — to break the otherwise-infinite ``while True``.
    """

    def __init__(self, actions):
        self._actions = list(actions)
        self._i = 0

    def get(self):
        if self._i >= len(self._actions):
            raise KeyboardInterrupt  # break the daemon loop from the test
        action = self._actions[self._i]
        self._i += 1
        if isinstance(action, BaseException):
            raise action
        return action


class _CaptureQueue:
    """Fake ``_log_q`` that records ``.put()`` payloads for _Tee.write tests."""

    def __init__(self):
        self.items = []

    def put(self, item):
        self.items.append(item)


class _RecordingStderr:
    """Fake ``sys.__stderr__`` whose ``write`` succeeds and records output."""

    def __init__(self):
        self.buf = []

    def write(self, s):
        self.buf.append(s)
        return len(s)

    def flush(self):
        pass


class _FailingStderr:
    """Fake ``sys.__stderr__`` whose ``write`` raises (stderr unavailable)."""

    def write(self, s):
        raise OSError("stderr is closed")

    def flush(self):
        pass


# ─────────────────────────────────────────────────────────────────────────────
# _archive_terminal_output
# ─────────────────────────────────────────────────────────────────────────────
def test_archive_missing_file_returns_none(tmp_path):
    # Line 40-41: nothing to archive -> None (safe first-run no-op).
    missing = tmp_path / "terminal_output.md"
    assert lc._archive_terminal_output(missing) is None


def test_archive_renames_existing_file_to_timestamped_stem(tmp_path):
    # Lines 42-48, 56-57, 66: existing file -> mtime-stamped archive, returns it.
    log = tmp_path / "terminal_output.md"
    log.write_text("prior session output", encoding="utf-8")

    result = lc._archive_terminal_output(log)

    assert result is not None
    assert result.exists()
    assert result.name.startswith("terminal_output_")
    assert result.suffix == ".md"
    assert not log.exists(), "original renamed away"


def test_archive_zero_byte_file_still_archived(tmp_path):
    # Docstring contract: zero-byte files still archive so the harvest can audit.
    log = tmp_path / "terminal_output.md"
    log.write_bytes(b"")

    result = lc._archive_terminal_output(log)

    assert result is not None and result.exists()
    assert result.stat().st_size == 0


def test_archive_collision_appends_numeric_suffix(tmp_path):
    # Lines 46-48: candidate already exists -> `while candidate.exists()` fires
    # and a trailing `_1` is appended.
    log = tmp_path / "terminal_output.md"
    log.write_text("body", encoding="utf-8")
    fixed = datetime.datetime(2026, 1, 2, 3, 4, 5).timestamp()
    os.utime(log, (fixed, fixed))
    mtime = datetime.datetime.fromtimestamp(log.stat().st_mtime)
    stem = f"terminal_output_{mtime.strftime('%Y-%m-%d_%H%M%S')}"
    # Pre-create the first candidate so the collision arm of the loop runs.
    (tmp_path / f"{stem}.md").write_text("existing archive", encoding="utf-8")

    result = lc._archive_terminal_output(log)

    assert result == tmp_path / f"{stem}_1.md"
    assert result.exists()
    assert not log.exists()


def test_archive_rename_failure_logs_and_returns_none(tmp_path, monkeypatch, capsys):
    # Lines 58-65: rename raises (Windows WinError 32 / held handle) -> warn +
    # skip archive, returning None so import/session continuity is preserved.
    log = tmp_path / "terminal_output.md"
    log.write_text("held by another process", encoding="utf-8")

    def _boom_rename(self, *a, **k):
        raise OSError("WinError 32: file in use")

    monkeypatch.setattr(pathlib.Path, "rename", _boom_rename)

    result = lc._archive_terminal_output(log)

    assert result is None
    assert log.exists(), "file untouched when rename failed"
    out = capsys.readouterr().out
    assert "could not archive" in out
    assert "terminal_output.md" in out


# ─────────────────────────────────────────────────────────────────────────────
# _check_terminal_output_size_cap
# ─────────────────────────────────────────────────────────────────────────────
def test_size_cap_missing_file_returns_false(tmp_path):
    # Line 89-90: no file -> False before any config import.
    missing = tmp_path / "does_not_exist.md"
    assert lc._check_terminal_output_size_cap(missing) is False


def test_size_cap_under_threshold_returns_false(tmp_path, monkeypatch):
    # Lines 91-94: file under the configured cap -> no rotation, False.
    log = tmp_path / "terminal_output.md"
    log.write_text("small", encoding="utf-8")
    monkeypatch.setattr("core.config.TERMINAL_OUTPUT_SIZE_CAP_MB", 100)

    assert lc._check_terminal_output_size_cap(log) is False


def test_size_cap_over_threshold_rotates(tmp_path, monkeypatch):
    # Lines 96-98 (close succeeds), 102-109: over cap -> close, archive, reopen,
    # announce, return True.
    log = tmp_path / "terminal_output.md"
    log.write_text("X" * 4096, encoding="utf-8")
    monkeypatch.setattr("core.config.TERMINAL_OUTPUT_SIZE_CAP_MB", 0)  # any size fires
    logfile = MagicMock()
    monkeypatch.setattr(lc, "_LOG_FILE", logfile)

    result = lc._check_terminal_output_size_cap(log)

    # Line 103 reassigned the global to a real fresh handle — close it to avoid
    # leaking a file descriptor (monkeypatch restores the attr, not the handle).
    fresh = lc._LOG_FILE
    try:
        assert result is True
        logfile.flush.assert_called_once()  # line 97 try body
        logfile.close.assert_called_once()  # line 98 try body
        archives = list(tmp_path.glob("terminal_output_*.md"))
        assert len(archives) == 1, "old log archived under timestamped name"
        assert log.exists(), "fresh empty log recreated at line 103"
    finally:
        if hasattr(fresh, "close"):
            fresh.close()


def test_size_cap_outer_exception_returns_false(tmp_path, monkeypatch, capsys):
    # Lines 99-100 (close-except via None._LOG_FILE) AND 110-112 (outer except):
    # _LOG_FILE is None so flush raises + is swallowed, then the archive step
    # raises and the outer handler logs + returns False.
    log = tmp_path / "terminal_output.md"
    log.write_text("X" * 4096, encoding="utf-8")
    monkeypatch.setattr("core.config.TERMINAL_OUTPUT_SIZE_CAP_MB", 0)
    monkeypatch.setattr(lc, "_LOG_FILE", None)  # None.flush() -> AttributeError -> 99-100

    def _boom_archive(*a, **k):
        raise RuntimeError("archive exploded mid-rotation")

    monkeypatch.setattr(lc, "_archive_terminal_output", _boom_archive)

    result = lc._check_terminal_output_size_cap(log)

    assert result is False
    out = capsys.readouterr().out
    assert "terminal_output rotation failed" in out


# ─────────────────────────────────────────────────────────────────────────────
# _prune_old_terminal_archives
# ─────────────────────────────────────────────────────────────────────────────
def test_prune_deletes_old_keeps_recent(tmp_path):
    # Lines 133-140, 145: old archive deleted, recent one kept, count returned.
    now = time.time()
    old = tmp_path / "terminal_output_2026-01-01_000000.md"
    old.write_text("old", encoding="utf-8")
    recent = tmp_path / "terminal_output_2026-06-01_000000.md"
    recent.write_text("recent", encoding="utf-8")
    old_mtime = now - (40 * 86400)  # older than 30d retention -> eligible
    recent_mtime = now - (1 * 86400)  # within retention -> kept
    os.utime(old, (old_mtime, old_mtime))
    os.utime(recent, (recent_mtime, recent_mtime))

    deleted = lc._prune_old_terminal_archives(retention_days=30, log_dir=tmp_path)

    assert deleted == 1
    assert not old.exists()
    assert recent.exists()


def test_prune_uses_config_and_logpath_defaults(tmp_path, monkeypatch):
    # Lines 128-132: retention_days=None -> config import; log_dir=None ->
    # _LOG_PATH.parent. _LOG_PATH is redirected to tmp so the real repo dir is
    # never touched. Empty dir -> glob yields nothing -> 0.
    fake_log = tmp_path / "terminal_output.md"
    monkeypatch.setattr(lc, "_LOG_PATH", fake_log)
    monkeypatch.setattr("core.config.TERMINAL_OUTPUT_ARCHIVE_RETENTION_DAYS", 30)

    deleted = lc._prune_old_terminal_archives()  # both args omitted

    assert deleted == 0


def test_prune_survives_per_file_unlink_failure(tmp_path, monkeypatch):
    # Lines 141-142: an eligible file whose unlink raises -> swallowed, not
    # counted, file survives; the pass continues.
    now = time.time()
    old = tmp_path / "terminal_output_2026-01-01_000000.md"
    old.write_text("old", encoding="utf-8")
    old_mtime = now - (40 * 86400)
    os.utime(old, (old_mtime, old_mtime))

    def _boom_unlink(self, *a, **k):
        raise PermissionError(f"cannot unlink {self.name}")

    monkeypatch.setattr(pathlib.Path, "unlink", _boom_unlink)

    deleted = lc._prune_old_terminal_archives(retention_days=30, log_dir=tmp_path)

    assert deleted == 0
    assert old.exists(), "file survives when unlink raised"


def test_prune_survives_glob_failure(tmp_path, monkeypatch):
    # Lines 143-144: the glob itself raises -> outer except swallows -> 0.
    def _boom_glob(self, *a, **k):
        raise OSError("glob exploded")

    monkeypatch.setattr(pathlib.Path, "glob", _boom_glob)

    deleted = lc._prune_old_terminal_archives(retention_days=30, log_dir=tmp_path)

    assert deleted == 0


# ─────────────────────────────────────────────────────────────────────────────
# _log_drain
# ─────────────────────────────────────────────────────────────────────────────
def test_log_drain_happy_path_writes_and_increments(monkeypatch):
    # Lines 170-175, 178-180, 183-184: dequeue, write+flush to stream + logfile,
    # bump the success counter + last-drain timestamp.
    stream = MagicMock()
    logfile = MagicMock()
    monkeypatch.setattr(lc, "_log_q", _ScriptedQueue([(stream, "hello\n")]))
    monkeypatch.setattr(lc, "_LOG_FILE", logfile)
    monkeypatch.setattr(lc, "_log_drain_count", 0)
    monkeypatch.setattr(lc, "_log_drain_last_at", 0.0)
    monkeypatch.setattr(lc, "_log_drain_error_count", 0)

    with pytest.raises(KeyboardInterrupt):  # scripted exit after 1 iteration
        lc._log_drain()

    stream.write.assert_called_once_with("hello\n")
    stream.flush.assert_called_once()
    logfile.write.assert_called_once_with("hello\n")
    logfile.flush.assert_called_once()
    assert lc._log_drain_count == 1
    assert lc._log_drain_last_at > 0.0
    assert lc._log_drain_error_count == 0


def test_log_drain_swallows_stream_and_logfile_write_errors(monkeypatch):
    # Lines 176-177 + 181-182: both inner writes raise -> both swallowed
    # (raising kills the daemon); the iteration still completes + increments.
    stream = MagicMock()
    stream.write.side_effect = OSError("stream broken")
    logfile = MagicMock()
    logfile.write.side_effect = OSError("logfile broken")
    monkeypatch.setattr(lc, "_log_q", _ScriptedQueue([(stream, "x")]))
    monkeypatch.setattr(lc, "_LOG_FILE", logfile)
    monkeypatch.setattr(lc, "_log_drain_count", 0)
    monkeypatch.setattr(lc, "_log_drain_error_count", 0)

    with pytest.raises(KeyboardInterrupt):
        lc._log_drain()

    stream.write.assert_called_once_with("x")
    logfile.write.assert_called_once_with("x")
    assert lc._log_drain_count == 1, "iteration completed despite both writes failing"
    assert lc._log_drain_error_count == 0, "inner errors are NOT the outer error path"


def test_log_drain_outer_except_writes_to_stderr(monkeypatch):
    # Lines 185-192: _log_q.get() raises -> outer handler bumps the error
    # counter and reports to sys.__stderr__ (bypassing _Tee to avoid a loop).
    rec = _RecordingStderr()
    monkeypatch.setattr(sys, "__stderr__", rec)
    monkeypatch.setattr(lc, "_log_q", _ScriptedQueue([RuntimeError("get exploded")]))
    monkeypatch.setattr(lc, "_LOG_FILE", MagicMock())
    monkeypatch.setattr(lc, "_log_drain_error_count", 0)

    with pytest.raises(KeyboardInterrupt):  # 2nd get() ends the loop
        lc._log_drain()

    assert lc._log_drain_error_count == 1
    joined = "".join(rec.buf)
    assert "_log_drain exception" in joined
    assert "RuntimeError" in joined


def test_log_drain_outer_except_survives_stderr_failure(monkeypatch):
    # Lines 193-194: stderr write itself raises -> swallowed; error counter
    # still bumped, nothing more can be done.
    monkeypatch.setattr(sys, "__stderr__", _FailingStderr())
    monkeypatch.setattr(lc, "_log_q", _ScriptedQueue([RuntimeError("get exploded")]))
    monkeypatch.setattr(lc, "_LOG_FILE", MagicMock())
    monkeypatch.setattr(lc, "_log_drain_error_count", 0)

    with pytest.raises(KeyboardInterrupt):
        lc._log_drain()

    assert lc._log_drain_error_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# _Tee
# ─────────────────────────────────────────────────────────────────────────────
def test_tee_init_stores_stream():
    # Line 199.
    s = object()
    t = lc._Tee(s)
    assert t._s is s


def test_tee_write_nonempty_enqueues_and_returns_length(monkeypatch):
    # Lines 201-202 + 203 (len(data) arm): non-empty write enqueues (stream, data).
    cap = _CaptureQueue()
    monkeypatch.setattr(lc, "_log_q", cap)
    s = object()
    t = lc._Tee(s)

    n = t.write("abcde")

    assert n == 5
    assert cap.items == [(s, "abcde")]


def test_tee_write_empty_returns_zero_and_enqueues_nothing(monkeypatch):
    # Line 201 (falsy arm) + 203 (else 0): empty write is a no-op returning 0.
    cap = _CaptureQueue()
    monkeypatch.setattr(lc, "_log_q", cap)
    t = lc._Tee(object())

    n = t.write("")

    assert n == 0
    assert cap.items == []


def test_tee_flush_is_noop():
    # Line 205.
    t = lc._Tee(object())
    assert t.flush() is None


def test_tee_getattr_delegates_to_wrapped_stream():
    # Line 207: unknown attrs proxy through to the wrapped stream.
    class _Stream:
        encoding = "utf-8"

        def isatty(self):
            return True

    t = lc._Tee(_Stream())
    assert t.encoding == "utf-8"
    assert t.isatty() is True
