"""tests/test_dashboard_launch_script.py — P0.S2 D5 launch wrapper tests.

D5 tests 17-20 plus the locked tripwire refactor (test 21 lives in
test_dashboard_bind_tripwire.py per Plan v1 §2). Behavioral tests use
`node scripts/launch.js --dry-run` so they exercise the actual launcher
logic without spawning Next.js. The `--dry-run` flag prints the resolved
argv to stdout and exits 0, giving the test harness a deterministic
assertion target.

Tests:
  - D5 test 17: default bind is 127.0.0.1 (AST/source scan + behavioral)
  - D5 test 18: DASHBOARD_BIND env var overrides default (behavioral dry-run)
  - D5 test 19: 0.0.0.0 without DASHBOARD_BIND_ALLOW_ANY → exit non-zero + stderr
  - D5 test 20: non-localhost bind → stderr WARNING block (≥3 of 6 lines)
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


_DASHBOARD = Path(__file__).resolve().parent.parent / "dog-ai-dashboard"
_LAUNCH_JS = _DASHBOARD / "scripts" / "launch.js"


def _node_available() -> bool:
    return shutil.which("node") is not None


pytestmark = pytest.mark.skipif(
    not _node_available(),
    reason="node not available — D5 launch-wrapper tests require Node.js",
)


def _run_launch(args, env_overrides=None, timeout=10.0):
    """Invoke `node scripts/launch.js <args>` from the dashboard cwd.

    Returns CompletedProcess with stdout/stderr captured. env_overrides
    layers on top of os.environ so the parent test process's env doesn't
    leak DASHBOARD_BIND values across tests.
    """
    env = os.environ.copy()
    # Clear any DASHBOARD_* envs so per-test overrides are deterministic
    for k in list(env.keys()):
        if k.startswith("DASHBOARD_"):
            del env[k]
    if env_overrides:
        env.update(env_overrides)

    cmd = ["node", str(_LAUNCH_JS)] + list(args)
    return subprocess.run(
        cmd,
        cwd=str(_DASHBOARD),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


# ───────────────────────────────────────────────────────────────────────
# D5 test 17 — default bind is localhost
# ───────────────────────────────────────────────────────────────────────


def test_launch_script_default_bind_is_localhost():
    """D5 test 17 — `node scripts/launch.js dev --dry-run` (no env)
    resolves to `next dev --hostname 127.0.0.1 --port 3000`.

    Combined AST/source + behavioral check: source must declare
    `DEFAULT_BIND = '127.0.0.1'` (or 'localhost'/'::1') AND dry-run must
    emit the resolved argv with the loopback value.
    """
    src = _LAUNCH_JS.read_text(encoding="utf-8")
    # Source-level: default bind constant in the locked loopback set
    assert (
        "DEFAULT_BIND = '127.0.0.1'" in src
        or "DEFAULT_BIND = 'localhost'" in src
        or "DEFAULT_BIND = '::1'" in src
    ), (
        "launch.js MUST declare DEFAULT_BIND in {127.0.0.1, localhost, ::1}; "
        "any other value defeats the locked-loopback invariant"
    )

    # Behavioral: dry-run resolves to the default
    res = _run_launch(["dev", "--dry-run"])
    assert res.returncode == 0, f"dry-run MUST exit 0; got {res.returncode}, stderr={res.stderr!r}"
    assert "--hostname 127.0.0.1" in res.stdout, (
        f"dry-run output MUST include '--hostname 127.0.0.1' default; "
        f"got stdout={res.stdout!r}"
    )
    assert "--port 3000" in res.stdout


# ───────────────────────────────────────────────────────────────────────
# D5 test 18 — DASHBOARD_BIND env var overrides
# ───────────────────────────────────────────────────────────────────────


def test_launch_script_dashboard_bind_env_overrides():
    """D5 test 18 — `DASHBOARD_BIND=192.168.1.5 node scripts/launch.js dev
    --dry-run` resolves to `--hostname 192.168.1.5`.
    """
    res = _run_launch(
        ["dev", "--dry-run"],
        env_overrides={"DASHBOARD_BIND": "192.168.1.5"},
    )
    assert res.returncode == 0, (
        f"non-localhost bind MUST still exit 0 in dry-run; got {res.returncode}; "
        f"stderr={res.stderr!r}"
    )
    assert "--hostname 192.168.1.5" in res.stdout, (
        f"env override MUST flow into resolved argv; got stdout={res.stdout!r}"
    )


# ───────────────────────────────────────────────────────────────────────
# D5 test 19 — 0.0.0.0 without double opt-in → hard error
# ───────────────────────────────────────────────────────────────────────


def test_launch_script_rejects_0_0_0_0_without_double_opt_in():
    """D5 test 19 — `DASHBOARD_BIND=0.0.0.0` without
    `DASHBOARD_BIND_ALLOW_ANY=1` exits non-zero + stderr names the
    locked second-opt-in env var.
    """
    res = _run_launch(
        ["dev", "--dry-run"],
        env_overrides={"DASHBOARD_BIND": "0.0.0.0"},
    )
    assert res.returncode != 0, (
        f"0.0.0.0 without double-opt-in MUST exit non-zero; got {res.returncode}; "
        f"stdout={res.stdout!r}, stderr={res.stderr!r}"
    )
    # The error message must explain what to do
    assert "DASHBOARD_BIND_ALLOW_ANY" in res.stderr, (
        "stderr MUST name DASHBOARD_BIND_ALLOW_ANY so the operator knows the "
        "second-opt-in env var; without naming it the error is unactionable"
    )
    assert "0.0.0.0" in res.stderr


def test_launch_script_accepts_0_0_0_0_with_double_opt_in():
    """D5 test 19b (defensive complement) — `DASHBOARD_BIND=0.0.0.0` +
    `DASHBOARD_BIND_ALLOW_ANY=1` succeeds (with stderr WARNING block).
    """
    res = _run_launch(
        ["dev", "--dry-run"],
        env_overrides={
            "DASHBOARD_BIND": "0.0.0.0",
            "DASHBOARD_BIND_ALLOW_ANY": "1",
        },
    )
    assert res.returncode == 0, (
        f"0.0.0.0 + double-opt-in MUST exit 0; got {res.returncode}; "
        f"stderr={res.stderr!r}"
    )
    assert "--hostname 0.0.0.0" in res.stdout


# ───────────────────────────────────────────────────────────────────────
# D5 test 20 — non-localhost bind → WARNING block
# ───────────────────────────────────────────────────────────────────────


def test_launch_script_prints_warning_on_non_localhost_bind():
    """D5 test 20 — `DASHBOARD_BIND=192.168.1.5` triggers a stderr
    WARNING block. Plan v1 §1.P3 / Phase 0 §2.D5 specifies a 6-line
    block; assert ≥3 of the lines are present (loose enough to allow
    minor wording adjustment, strict enough to catch absence).
    """
    res = _run_launch(
        ["dev", "--dry-run"],
        env_overrides={"DASHBOARD_BIND": "192.168.1.5"},
    )
    assert res.returncode == 0
    # WARNING signature
    assert "DASHBOARD WARNING" in res.stderr, (
        "stderr MUST contain 'DASHBOARD WARNING' literal banner so the "
        "operator can grep for non-localhost binds in launch logs"
    )
    # Count distinct WARNING lines
    warning_lines = [
        line for line in res.stderr.splitlines() if "WARNING" in line
    ]
    assert len(warning_lines) >= 3, (
        f"WARNING block MUST have ≥3 lines (Plan v1 §1.P3 locks 6); "
        f"got {len(warning_lines)}: {warning_lines!r}"
    )


# ───────────────────────────────────────────────────────────────────────
# D5 — argv-injection regex guard (defensive complement)
# ───────────────────────────────────────────────────────────────────────


def test_launch_script_rejects_unsafe_dashboard_bind_chars():
    """D5 (defensive) — DASHBOARD_BIND containing chars outside
    `[a-zA-Z0-9.:_-]` must be rejected BEFORE the 0.0.0.0 double-opt-in
    check fires. Prevents argv injection into next's --hostname flag.
    """
    # Space + flag-looking value: classic argv-injection vector
    res = _run_launch(
        ["dev", "--dry-run"],
        env_overrides={"DASHBOARD_BIND": "0.0.0.0 --foo bar"},
    )
    assert res.returncode != 0, (
        "unsafe DASHBOARD_BIND value MUST be rejected (argv-injection "
        "protection); got returncode=" + str(res.returncode)
    )
    assert "argv injection" in res.stderr.lower() or "characters outside" in res.stderr, (
        "stderr MUST explain WHY the bind value was rejected"
    )
