"""runtime/log_capture.py — Terminal-output log harness: _Tee + _log_drain (+ 3 drain counters) + archive/rotate + log-state globals.

Extracted VERBATIM from pipeline.py (P1.A1 SP-4.1).
_LOG_PATH carries the ONE behavior-preserving non-verbatim line: .parent -> .parent.parent so
__file__ (now runtime/log_capture.py) resolves back to the repo root, identical to the original.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import time
import datetime as _dt
import pathlib as _pathlib
import queue as _log_queue_mod


_LOG_PATH = _pathlib.Path(__file__).parent.parent / "terminal_output.md"


def _archive_terminal_output(log_path: _pathlib.Path = _LOG_PATH) -> "_pathlib.Path | None":
    """P1.5 data-accumulation hook: rename an existing terminal_output.md to a
    timestamped archive file so fresh sessions start clean AND historical logs
    are preserved for the golden-intent harvest script.

    Naming: ``terminal_output_YYYY-MM-DD_HHMMSS.md`` — timestamped from the
    file's mtime (when the PRIOR session wrote its last byte), not from now,
    so the archive name reflects the actual session boundary. Collision-safe:
    if the target already exists a trailing ``_1``, ``_2`` etc. is appended.

    Returns the archive path, or ``None`` if there was no file to archive.
    Safe to call on first run (no-op when log_path missing) and on zero-byte
    files (still archives so the harvest can audit 'prior session produced no
    output').

    Reverses Session 24's A6 (open mode "a" → "w") but preserves the same
    property (all prior logs retrievable) — just distributed across files
    rather than concatenated in one."""
    if not log_path.exists():
        return None
    mtime = _dt.datetime.fromtimestamp(log_path.stat().st_mtime)
    stem = f"terminal_output_{mtime.strftime('%Y-%m-%d_%H%M%S')}"
    candidate = log_path.parent / f"{stem}.md"
    suffix = 1
    while candidate.exists():
        candidate = log_path.parent / f"{stem}_{suffix}.md"
        suffix += 1
    # Windows holds the file when a prior pipeline.py process didn't fully
    # release the handle (orphaned hung process, IDE still tailing the file,
    # antivirus scan in progress). The rename then raises WinError 32 and
    # the bare exception kills module import. Catch + log + skip the
    # archive — preserving session continuity is more important than
    # archive hygiene; the user can rename the file manually after the
    # blocking process is killed.
    try:
        log_path.rename(candidate)
    except (OSError, PermissionError) as e:
        print(
            f"[Pipeline] WARN: could not archive {log_path.name} "
            f"({type(e).__name__}: {e!r}). Continuing without archive — "
            f"investigate which process is holding the file.",
            flush=True,
        )
        return None
    return candidate


_archived_log: "_pathlib.Path | None" = None


_LOG_FILE: "Any" = None  # opened by D1 main-only block; None in subprocess


def _check_terminal_output_size_cap(log_path: _pathlib.Path = _LOG_PATH) -> bool:
    """P0.R13 D2 — rotate terminal_output.md when size exceeds TERMINAL_OUTPUT_SIZE_CAP_MB.

    Q2 (a) RATIFIED 100MB default; Q4 (a) RATIFIED disk-monitor-poll cadence.

    Closes current log, renames to timestamped archive (matches startup
    archive shape via `_archive_terminal_output`), opens fresh log file.
    Returns True if rotation fired; False if under cap OR rotation failed.

    Called from dream-loop / disk-monitor poll cadence so size check is
    amortized over session (NOT per-print which would dominate hot path).
    """
    global _LOG_FILE
    try:
        if not log_path.exists():
            return False
        size_mb = log_path.stat().st_size / (1024 * 1024)
        from core.config import TERMINAL_OUTPUT_SIZE_CAP_MB  # noqa: PLC0415
        if size_mb < TERMINAL_OUTPUT_SIZE_CAP_MB:
            return False
        # Close current file before rename (Windows file-lock semantics).
        try:
            _LOG_FILE.flush()
            _LOG_FILE.close()
        except Exception:
            pass  # CLEANUP: best-effort flush before rotation
        # Rotate via same archive shape as startup.
        _archive_terminal_output(log_path)
        _LOG_FILE = open(log_path, "w", encoding="utf-8", buffering=1)
        print(
            f"[Pipeline] terminal_output.md rotated at {size_mb:.1f}MB "
            f"(cap={TERMINAL_OUTPUT_SIZE_CAP_MB}MB)",
            flush=True,
        )
        return True
    except Exception as e:
        print(f"[Pipeline] terminal_output rotation failed: {e!r}", flush=True)
        return False


def _prune_old_terminal_archives(
    retention_days: "int | None" = None,
    log_dir: "_pathlib.Path | None" = None,
) -> int:
    """P0.R13 D2 — delete terminal_output_*.md archive files older than retention_days.

    Q3 (a) RATIFIED 30-day archive retention default.

    Pattern: ``terminal_output_YYYY-MM-DD_HHMMSS*.md`` (matches
    ``_archive_terminal_output`` naming scheme). Returns count deleted.
    Per-file unlink failures swallowed (best-effort cleanup; single corrupt
    file shouldn't break the cleanup pass for the rest).
    """
    if retention_days is None:
        from core.config import TERMINAL_OUTPUT_ARCHIVE_RETENTION_DAYS  # noqa: PLC0415
        retention_days = TERMINAL_OUTPUT_ARCHIVE_RETENTION_DAYS
    if log_dir is None:
        log_dir = _LOG_PATH.parent
    cutoff_ts = time.time() - retention_days * 86400
    deleted = 0
    try:
        for path in log_dir.glob("terminal_output_*.md"):
            try:
                if path.stat().st_mtime < cutoff_ts:
                    path.unlink()
                    deleted += 1
            except Exception:
                pass  # CLEANUP: skip individual archive prune failures
    except Exception:
        pass  # CLEANUP: glob failure
    return deleted


_log_q: "_log_queue_mod.SimpleQueue[tuple[object, str]]" = _log_queue_mod.SimpleQueue()


_log_drain_count: int = 0  # observability counter — successful drains


_log_drain_last_at: float = 0.0  # WALLCLOCK: observability — last successful drain timestamp


_log_drain_error_count: int = 0  # observability counter — exception count


def _log_drain() -> None:
    """Daemon thread — writes queued log messages to terminal + log file.

    P0.B4 D1 (Bundle 4 observability) — outer-loop try/except catches:
      - _log_q.get() failures (the load-bearing silent-death failure mode per Skeptic-1 BUG-3)
      - _log_drain_count / _log_drain_last_at counter update failures (exotic)
      - any unforeseen exception sites
    Inner try/except blocks (stream.write + _LOG_FILE.write) preserved per P0.4 discipline.
    """
    global _log_drain_count, _log_drain_last_at, _log_drain_error_count
    while True:
        try:
            stream, data = _log_q.get()
            try:
                stream.write(data)
                stream.flush()
            except Exception:
                pass  # OPTIONAL: raising kills the daemon and silences all subsequent logging
            try:
                _LOG_FILE.write(data)
                _LOG_FILE.flush()
            except Exception:
                pass  # OPTIONAL: raising kills the daemon and silences all subsequent logging
            _log_drain_count += 1
            _log_drain_last_at = time.time()  # WALLCLOCK: observability timestamp
        except Exception as e:
            # P0.B4 D1 outer-loop wrap: DO NOT swallow silently. Emit to stderr directly
            # (bypassing _Tee which routes through _log_q — would create an infinite loop).
            _log_drain_error_count += 1
            import sys as _sys
            try:
                _sys.__stderr__.write(f"[Log] _log_drain exception: {type(e).__name__}: {e}\n")
                _sys.__stderr__.flush()
            except Exception:
                pass  # OPTIONAL: stderr unavailable; nothing more we can do


class _Tee:
    def __init__(self, stream):
        self._s = stream
    def write(self, data: str) -> int:
        if data:
            _log_q.put((self._s, data))
        return len(data) if data else 0
    def flush(self):
        pass  # background thread handles all flushing
    def __getattr__(self, name):
        return getattr(self._s, name)
