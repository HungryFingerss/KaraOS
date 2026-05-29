"""A1 + A2 + A4 anchor tests for Pre-P1 Bundle 4 (Observability + Concurrency MF6+MF9).

A1 = D1 _log_drain outer-loop wrap + 3 observability state vars source-inspection
     (pipeline.py:_log_drain body has outer try/except + 3 module-level counters
     present).

A2 = D2 HealthSnapshot.log_drain_alive + format_health_alerts source-inspection
     (5 verbatim substrings; LOG_DRAIN_STALENESS_SECS=60.0 in core/config.py).

A4 = D4 core/state.py lock-snapshot block source-inspection
     (`with _persistent_lock:` followed by `_persistent_snapshot = dict(_persistent)`
     before the state dict construction; spread uses _persistent_snapshot not
     _persistent).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# --- A1: D1 _log_drain outer-loop wrap + 3 observability vars ---


def test_a1_log_drain_function_has_outer_loop_try_wrap() -> None:
    """A1 — `_log_drain` function body has outer-loop try/except wrapping while True."""
    text = (REPO_ROOT / "pipeline.py").read_text(encoding="utf-8")
    idx = text.find("def _log_drain")
    assert idx >= 0, "_log_drain not found in pipeline.py"
    body = text[idx:idx + 2500]
    assert "P0.B4 D1" in body, "_log_drain missing P0.B4 D1 annotation"
    assert "while True:" in body, "_log_drain missing while True loop"
    assert re.search(r"while True:\s*\n\s*try:", body), (
        "_log_drain outer-loop body must start with try/except (not bare _log_q.get())"
    )
    assert "_sys.__stderr__" in body or "sys.__stderr__" in body, (
        "_log_drain outer except must emit to sys.__stderr__ direct bypass"
    )


def test_a1_three_observability_module_level_vars_landed() -> None:
    """A1 — 3 module-level observability vars present in pipeline.py."""
    text = (REPO_ROOT / "pipeline.py").read_text(encoding="utf-8")
    assert "_log_drain_count: int = 0" in text, "missing _log_drain_count: int = 0"
    assert "_log_drain_last_at: float = 0.0" in text, "missing _log_drain_last_at: float = 0.0"
    assert "_log_drain_error_count: int = 0" in text, "missing _log_drain_error_count: int = 0"


# --- A2: D2 HealthSnapshot + format_health_alerts + config constant ---


def test_a2_config_log_drain_staleness_secs_constant() -> None:
    """A2 — core/config.py defines LOG_DRAIN_STALENESS_SECS = 60.0."""
    text = (REPO_ROOT / "core" / "config.py").read_text(encoding="utf-8")
    assert "LOG_DRAIN_STALENESS_SECS" in text, "LOG_DRAIN_STALENESS_SECS not declared"
    assert re.search(r"LOG_DRAIN_STALENESS_SECS\s*:\s*float\s*=\s*60\.0", text), (
        "LOG_DRAIN_STALENESS_SECS must be `float = 60.0`"
    )


def test_a2_health_snapshot_log_drain_fields_landed() -> None:
    """A2 — HealthSnapshot dataclass has log_drain_alive + log_drain_count + log_drain_error_count."""
    text = (REPO_ROOT / "core" / "health.py").read_text(encoding="utf-8")
    assert "log_drain_alive: bool = True" in text, "HealthSnapshot.log_drain_alive missing"
    assert "log_drain_count: int = 0" in text, "HealthSnapshot.log_drain_count missing"
    assert "log_drain_error_count: int = 0" in text, (
        "HealthSnapshot.log_drain_error_count missing"
    )


def test_a2_gather_health_snapshot_populates_log_drain_fields() -> None:
    """A2 — gather_health_snapshot populates log_drain_alive via late `import pipeline`."""
    text = (REPO_ROOT / "core" / "health.py").read_text(encoding="utf-8")
    idx = text.find("def gather_health_snapshot")
    assert idx >= 0
    body = text[idx:]
    assert "import pipeline" in body, "gather_health_snapshot must late-import pipeline"
    assert "_log_drain_last_at" in body, "gather_health_snapshot must read _log_drain_last_at"
    assert "_log_drain_count" in body, "gather_health_snapshot must read _log_drain_count"
    assert "_log_drain_error_count" in body, (
        "gather_health_snapshot must read _log_drain_error_count"
    )
    assert "LOG_DRAIN_STALENESS_SECS" in body, (
        "gather_health_snapshot must reference LOG_DRAIN_STALENESS_SECS"
    )


def test_a2_format_health_line_emits_log_drain_dead_conditional() -> None:
    """A2 — format_health_line conditional emit on log_drain_alive False / errors > 0."""
    text = (REPO_ROOT / "core" / "health.py").read_text(encoding="utf-8")
    idx = text.find("def format_health_line")
    assert idx >= 0
    body = text[idx:text.find("def format_health_alerts", idx)]
    assert "log_drain=DEAD" in body, "format_health_line must emit log_drain=DEAD when not alive"
    assert "log_drain_errors=" in body, "format_health_line must emit log_drain_errors=N"


# A2 — format_health_alerts 5 verbatim substring lock per Plan v1 §2 D2

A2_VERBATIM_SUBSTRINGS: tuple[str, ...] = (
    "Log drain thread degraded",
    "check pipeline restart",
    "messages drained:",
    "errors:",
    "LOG_DRAIN_STALENESS_SECS",
)


@pytest.mark.parametrize("substring", A2_VERBATIM_SUBSTRINGS)
def test_a2_format_health_alerts_contains_verbatim_substring(substring: str) -> None:
    """A2 — format_health_alerts contains all 5 locked verbatim substrings."""
    text = (REPO_ROOT / "core" / "health.py").read_text(encoding="utf-8")
    idx = text.find("def format_health_alerts")
    assert idx >= 0
    body = text[idx:]
    assert substring in body, (
        f"format_health_alerts missing verbatim substring {substring!r} per Plan v1 §2 D2 lock"
    )


# --- A4: D4 core/state.py lock-snapshot block ---


def test_a4_state_write_uses_persistent_lock_snapshot() -> None:
    """A4 — core/state.py write() acquires _persistent_lock for shallow dict copy."""
    text = (REPO_ROOT / "core" / "state.py").read_text(encoding="utf-8")
    idx = text.find("def write(")
    assert idx >= 0
    body = text[idx:idx + 2500]
    assert "P0.B4 D4" in body, "state.write missing P0.B4 D4 annotation"
    assert "with _persistent_lock:" in body, (
        "state.write must acquire _persistent_lock for shallow copy"
    )
    assert "_persistent_snapshot = dict(_persistent)" in body, (
        "state.write must take shallow dict() copy under lock"
    )
    assert "**_persistent_snapshot" in body, (
        "state dict must spread _persistent_snapshot, not _persistent"
    )


def test_a4_state_write_lock_released_before_file_io() -> None:
    """A4 — lock is acquired ONLY for shallow copy; file I/O happens outside the with block."""
    text = (REPO_ROOT / "core" / "state.py").read_text(encoding="utf-8")
    idx = text.find("def write(")
    body = text[idx:idx + 3000]
    lock_open = body.find("with _persistent_lock:")
    snapshot_line = body.find("_persistent_snapshot = dict(_persistent)")
    file_write_idx = body.find("tempfile.mkstemp")
    assert lock_open >= 0 and snapshot_line > lock_open
    assert file_write_idx > snapshot_line, (
        "tempfile.mkstemp must occur AFTER the with-block; lock granularity = shallow-copy-only"
    )
    # Crude indentation check: snapshot must be indented inside the with; mkstemp must NOT.
    state_dict_start = body.find('state = {')
    assert state_dict_start > snapshot_line, "state dict must construct after snapshot taken"
