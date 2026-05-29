"""Crash diagnostic capture (P0.R11). Extends P0.R8's in-memory crash
history with persistent JSON-per-crash forensic data for post-mortem
analysis. Used by core.heavy_worker.run_heavy's BrokenProcessPool catch
block; designed for broader unhandled-exception capture in follow-up cycle.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import json
import logging
import time
import traceback as _traceback  # NOTE: only used if caller doesn't pass traceback_str
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CRASH_LOG_SCHEMA_VERSION = 1


def _crash_log_dir() -> Path:
    """Return crash_logs/ subdir under FACES_DIR; auto-create on first call.

    Per P0.4 silent-except policy: if FACES_DIR is unwritable (extreme
    failure mode), this raises at mkdir — persist_crash_diagnostic's outer
    try/except catches + logs, returning None.
    """
    from core.config import FACES_DIR
    d = FACES_DIR / "crash_logs"
    d.mkdir(exist_ok=True, parents=True)
    return d


def persist_crash_diagnostic(
    task_name: str,
    exc: "BaseException",
    traceback_str: str,
    crash_count: int,
    now: "float | None" = None,
) -> "Path | None":
    """Write structured JSON crash diagnostic to faces/crash_logs/.

    Q4 (a) lock: schema_version=1 + task_name + timestamp + exception_type +
    exception_message + stack_trace + crash_count fields.

    Q5 (a) lock: filename {task_name}_{YYYY-MM-DDTHHMMSS}_{micros}.json for
    sortable + collision-resistant naming.

    Per P0.4 silent-except policy: write failure (disk full, permission
    denied, unwritable FACES_DIR) is logged + swallowed; returns None on
    failure. The original crash propagation via run_heavy's bare `raise`
    is UNAFFECTED.

    Returns the path to the written file on success, None on failure.
    """
    if now is None:
        now = time.time()
    try:
        log_dir = _crash_log_dir()
        ts_struct = time.gmtime(now)
        ts_str = time.strftime("%Y-%m-%dT%H%M%S", ts_struct)
        micros = int((now - int(now)) * 1_000_000)
        filename = f"{task_name}_{ts_str}_{micros:06d}.json"
        log_path = log_dir / filename
        payload = {
            "schema_version": _CRASH_LOG_SCHEMA_VERSION,
            "task_name": task_name,
            "timestamp": now,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "stack_trace": traceback_str,
            "crash_count": crash_count,
        }
        log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return log_path
    except Exception as e:  # OPTIONAL: persist failure → log + swallow per P0.4
        logger.warning(
            "[CrashLogs] persist_crash_diagnostic failed for task_name=%s: %s: %s",
            task_name, type(e).__name__, e,
        )
        return None


def prune_old_crash_logs(retention_days: int, now: "float | None" = None) -> int:
    """Remove crash log files older than retention_days. Returns count
    of files removed. Called periodically from pipeline._dream_loop.

    Per P0.4: file-level unlink failures are logged + swallowed (a single
    corrupt file shouldn't break the cleanup pass for the rest).
    """
    if now is None:
        now = time.time()
    cutoff = now - (retention_days * 86_400)
    removed = 0
    try:
        log_dir = _crash_log_dir()
    except Exception as e:  # OPTIONAL: dir-create failure
        logger.warning(
            "[CrashLogs] prune_old_crash_logs: dir access failed: %s: %s",
            type(e).__name__, e,
        )
        return 0
    for path in log_dir.glob("*.json"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except Exception as e:  # OPTIONAL: per-file unlink failure
            logger.warning(
                "[CrashLogs] prune unlink failed for %s: %s: %s",
                path.name, type(e).__name__, e,
            )
    return removed


def list_recent_crash_logs(limit: int = 10) -> "list[dict[str, Any]]":
    """Return parsed JSON contents of the most recent crash logs (by mtime),
    up to `limit` entries. Read accessor for HealthSnapshot + dashboard.

    Each entry: dict matching persist_crash_diagnostic's payload shape.
    Corrupt files (malformed JSON) are skipped with warning.
    """
    try:
        log_dir = _crash_log_dir()
    except Exception as e:  # OPTIONAL: dir-create failure
        logger.warning(
            "[CrashLogs] list_recent_crash_logs: dir access failed: %s: %s",
            type(e).__name__, e,
        )
        return []
    paths = sorted(log_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    results: "list[dict[str, Any]]" = []
    for path in paths[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            results.append(data)
        except Exception as e:  # OPTIONAL: parse failure → skip + warn
            logger.warning(
                "[CrashLogs] parse failed for %s: %s: %s",
                path.name, type(e).__name__, e,
            )
    return results
