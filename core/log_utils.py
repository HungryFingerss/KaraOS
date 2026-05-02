"""Shared logging helpers.

Single source of truth for log formatting across the pipeline. Both audio.py
and pipeline.py (and any future timestamped log site) import from here so the
format stays consistent — grep for ``_now_log_ts`` to find every timestamped
log path; no ad-hoc ``datetime.now().strftime()`` anywhere else.

Depends only on core.config so it can't introduce circular imports.
"""
from __future__ import annotations

import datetime as _dt

from core.config import LOG_TIME_FORMAT, LOG_STT_MAX_CHARS


def _now_log_ts() -> str:
    """Wall-clock timestamp formatted per ``LOG_TIME_FORMAT``.

    Trims microseconds to milliseconds for readability
    (``%f`` in ``strftime`` is 6-digit microseconds; we cut to 3).
    """
    raw = _dt.datetime.now().strftime(LOG_TIME_FORMAT)
    if LOG_TIME_FORMAT.endswith("%f") and len(raw) >= 3:
        return raw[:-3]
    return raw


def _log_trunc(s: str, limit: int | None = None) -> str:
    """Truncate a log string when ``LOG_STT_MAX_CHARS`` (or explicit ``limit``) is positive.

    ``0`` means no truncation — the default. Callers can override per-site with
    the ``limit`` arg when they want stricter caps on a specific line.
    """
    effective = LOG_STT_MAX_CHARS if limit is None else limit
    if not effective or len(s) <= effective:
        return s
    return s[:effective] + "…"
