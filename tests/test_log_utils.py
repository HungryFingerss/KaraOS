"""100% coverage for core.log_utils — timestamp + truncation helpers.
Part of the coverage-to-100 campaign (see COVERAGE.md)."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import re

import core.log_utils as lu

def test_now_log_ts_returns_nonempty_string():
    assert isinstance(lu._now_log_ts(), str) and lu._now_log_ts()

def test_now_log_ts_trims_microseconds_to_milliseconds(monkeypatch):
    # %f is 6-digit microseconds; the helper trims the trailing 3 -> ms
    monkeypatch.setattr(lu, "LOG_TIME_FORMAT", "%H:%M:%S.%f")
    frac = lu._now_log_ts().split(".")[-1]
    assert len(frac) == 3 and frac.isdigit()

def test_now_log_ts_returns_raw_when_format_has_no_microseconds(monkeypatch):
    monkeypatch.setattr(lu, "LOG_TIME_FORMAT", "%H:%M:%S")  # no %f -> raw branch
    assert re.fullmatch(r"\d{2}:\d{2}:\d{2}", lu._now_log_ts())

def test_log_trunc_no_truncation_when_effective_zero(monkeypatch):
    monkeypatch.setattr(lu, "LOG_STT_MAX_CHARS", 0)  # falsy -> return s
    s = "x" * 500
    assert lu._log_trunc(s) == s

def test_log_trunc_returns_string_at_or_under_limit():
    assert lu._log_trunc("short", limit=100) == "short"

def test_log_trunc_truncates_and_appends_ellipsis():
    assert lu._log_trunc("abcdefghij", limit=4) == "abcd…"

def test_log_trunc_uses_config_default_when_limit_none(monkeypatch):
    monkeypatch.setattr(lu, "LOG_STT_MAX_CHARS", 3)
    assert lu._log_trunc("abcdef") == "abc…"
