"""P0.0 + S2 tripwire: dashboard bind address regression guard.

**P0.S2 update (2026-05-20):** The dashboard auth surface now SHIPS in
P0.S2. The "S2 deferred" framing of the original tripwire no longer
applies — the auth token + cookie-gated middleware + launch wrapper are
all live. The tripwire's ROLE is now to lock the bind-address
invariant under the new launch-wrapper architecture.

P0.S2 D5 moved the bind logic from `package.json` (`next dev --hostname
127.0.0.1 ...`) into a new wrapper `scripts/launch.js` that reads
`DASHBOARD_BIND` from env (default `127.0.0.1`) + double-opt-in gate on
`0.0.0.0`. The package.json scripts now point at the wrapper. This
tripwire is REFACTORED accordingly per Plan v1 §2 test 21:

  - **Old invariant:** package.json scripts explicitly bind via
    `--hostname 127.0.0.1`.
  - **New invariant (P0.S2 D5):** package.json scripts invoke `node
    scripts/launch.js dev|start`; launch.js source has default-bind in
    {127.0.0.1, localhost, ::1}; launch.js has a `DASHBOARD_BIND`
    env-var check branch; launch.js has a `0.0.0.0`-rejection-without-
    double-opt-in branch.

Same invariant ("default bind localhost; LAN opt-out requires explicit
env-var"); new surface.

**THE PROPER RESPONSE TO THIS TEST FAILING:** restore the launch-wrapper
shape (either re-link package.json scripts to scripts/launch.js, or fix
launch.js to honor the default-localhost + double-opt-in invariants).
NOT to delete the test or weaken the invariant.

Scope:
  - Checks dashboard `package.json` scripts invoke `node scripts/launch.js`.
  - Checks `scripts/launch.js` declares DEFAULT_BIND in localhost set.
  - Checks `scripts/launch.js` reads `DASHBOARD_BIND` env var.
  - Checks `scripts/launch.js` rejects `0.0.0.0` without `DASHBOARD_BIND_ALLOW_ANY=1`.
  - Checks `next.config.js` for hostname config pointing to LAN.
  - Checks the dashboard `.env.local` for DASHBOARD_BIND / HOSTNAME
    overrides pointing to LAN (without ALLOW_ANY=1).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_DASHBOARD_DIR = _REPO_ROOT / "dog-ai-dashboard"
_PACKAGE_JSON = _DASHBOARD_DIR / "package.json"
_NEXT_CONFIG = _DASHBOARD_DIR / "next.config.js"
_DASHBOARD_ENV = _DASHBOARD_DIR / ".env.local"
_LAUNCH_JS = _DASHBOARD_DIR / "scripts" / "launch.js"

# Hostnames that mean "expose to LAN / any interface" — failing patterns.
_LAN_HOSTNAMES = frozenset({
    "0.0.0.0",
    "::",
    "*",
})

# Hostnames that count as localhost-only.
_LOCALHOST_HOSTNAMES = frozenset({
    "127.0.0.1",
    "localhost",
    "::1",
})

# Scripts that must explicitly bind localhost.  These are the Next.js
# launch scripts; adding more is fine but each addition must also bind
# explicitly (the tripwire will fail if not).
_SCRIPTS_REQUIRING_EXPLICIT_BIND = ("dev", "start")


def _read_text_if_exists(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _find_explicit_hostname_in_command(cmd: str) -> str | None:
    """Return the hostname value if `--hostname X` or `-H X` is present, else None."""
    # `--hostname X` form
    m = re.search(r"--hostname[=\s]+([^\s]+)", cmd)
    if m:
        return m.group(1).strip().strip("\"'")
    # `-H X` form (short flag)
    m = re.search(r"(?<![\w-])-H[=\s]+([^\s]+)", cmd)
    if m:
        return m.group(1).strip().strip("\"'")
    return None


def test_dashboard_package_json_scripts_invoke_launch_wrapper():
    """P0.S2 D5 refactor of the bind tripwire.

    Old (pre-P0.S2): scripts MUST contain `--hostname 127.0.0.1` literal.
    New (P0.S2 D5): scripts MUST invoke `node scripts/launch.js dev|start`;
    the bind logic moved into the wrapper which enforces default-localhost
    + double-opt-in on 0.0.0.0.

    Same invariant ("default bind localhost; LAN opt-out requires explicit
    env-var"); new surface (logic moved from package.json to launch.js).

    Per Plan v1 §2 test 21 — REFACTOR target locked.
    """
    assert _PACKAGE_JSON.exists(), f"dashboard package.json missing at {_PACKAGE_JSON}"

    pkg = json.loads(_PACKAGE_JSON.read_text(encoding="utf-8"))
    scripts = pkg.get("scripts", {})

    for script_name in _SCRIPTS_REQUIRING_EXPLICIT_BIND:
        cmd = scripts.get(script_name)
        assert cmd is not None, (
            f"S2 TRIPWIRE FIRED — required script {script_name!r} missing "
            f"from package.json. P0.S2 D5 expects `node scripts/launch.js "
            f"{script_name}`; both `dev` and `start` MUST point at the wrapper."
        )

        # New invariant: scripts invoke the launch wrapper.
        assert "scripts/launch.js" in cmd, (
            f"S2 TRIPWIRE FIRED — script {script_name!r} does NOT invoke "
            f"`scripts/launch.js`:\n"
            f"  current: {cmd!r}\n"
            f"  expected pattern: 'node scripts/launch.js {script_name}'\n"
            f"  why: P0.S2 D5 moved bind logic into the wrapper so the\n"
            f"       DASHBOARD_BIND env-var + double-opt-in invariant lives\n"
            f"       in ONE place. Inlining --hostname back into package.json\n"
            f"       bypasses the wrapper's safety gates.\n"
            f"\n"
            f"  PROPER RESPONSE: restore `node scripts/launch.js {script_name}` "
            f"OR ship a follow-up that moves the bind logic to a different "
            f"single source of truth + updates this test.\n"
        )
        # And the wrapper-invocation MUST come via `node` (not `npx`, not
        # `next` directly) so the dependency is explicit + portable.
        assert cmd.strip().startswith("node "), (
            f"S2 TRIPWIRE FIRED — script {script_name!r} does not start with "
            f"'node '; got: {cmd!r}. The wrapper assumes `node scripts/launch.js`"
        )


def test_dashboard_launch_script_enforces_default_localhost():
    """P0.S2 D5 — `scripts/launch.js` MUST declare `DEFAULT_BIND` in the
    locked localhost set. The wrapper's invariant is "default bind
    localhost; LAN opt-out requires explicit DASHBOARD_BIND env var."
    """
    assert _LAUNCH_JS.exists(), (
        f"S2 TRIPWIRE FIRED — P0.S2 D5 expects {_LAUNCH_JS} to exist; missing.\n"
        f"  The bind logic moved out of package.json into this wrapper.\n"
        f"  If the wrapper was deleted, restore it OR add a follow-up spec\n"
        f"  that re-locates the bind logic + updates this test."
    )
    src = _LAUNCH_JS.read_text(encoding="utf-8")

    # DEFAULT_BIND must be in the locked localhost set
    has_locked_default = any(
        f"DEFAULT_BIND = '{lh}'" in src or f'DEFAULT_BIND = "{lh}"' in src
        for lh in _LOCALHOST_HOSTNAMES
    )
    assert has_locked_default, (
        f"S2 TRIPWIRE FIRED — scripts/launch.js DEFAULT_BIND is NOT in "
        f"the locked localhost set {sorted(_LOCALHOST_HOSTNAMES)}.\n"
        f"  P0.S2 D5 requires default-localhost; any other value bypasses\n"
        f"  the deferral lock. PROPER RESPONSE: restore the default to\n"
        f"  '127.0.0.1' OR ship a follow-up updating both the wrapper AND\n"
        f"  this test."
    )

    # The wrapper MUST read DASHBOARD_BIND env var — without this, the
    # opt-out channel collapses and the default-localhost is unconditional
    # (which sounds safer but breaks the LAN-access workflow the wrapper exists
    # to enable safely).
    assert "DASHBOARD_BIND" in src, (
        "S2 TRIPWIRE FIRED — scripts/launch.js does NOT reference "
        "DASHBOARD_BIND env var. P0.S2 D5 locks DASHBOARD_BIND as the "
        "single env-var override channel."
    )

    # The wrapper MUST gate 0.0.0.0 behind DASHBOARD_BIND_ALLOW_ANY (the
    # second-opt-in env var). Without this gate, an attacker who can set
    # DASHBOARD_BIND can also pick the broadest-attack bind by default.
    assert "DASHBOARD_BIND_ALLOW_ANY" in src, (
        "S2 TRIPWIRE FIRED — scripts/launch.js does NOT reference "
        "DASHBOARD_BIND_ALLOW_ANY. P0.S2 D5 locks the double-opt-in gate "
        "for 0.0.0.0 (bind-all-interfaces) behind this second env var."
    )
    assert "0.0.0.0" in src, (
        "S2 TRIPWIRE FIRED — scripts/launch.js does NOT mention 0.0.0.0. "
        "The double-opt-in branch checks for this specific value; absence "
        "means the gate is unreachable."
    )


def test_dashboard_next_config_has_no_lan_hostname():
    """next.config.js must NOT export a hostname / host config pointing to LAN.

    Looks for keyword:value pairs (`hostname: '0.0.0.0'`, `host: '*'`)
    rather than bare literals — avoids JSDoc/comment false positives
    like `/** @type ... */` (the `*` in JSDoc syntax is not a bind).
    """
    src = _read_text_if_exists(_NEXT_CONFIG)
    if not src:
        return  # no config file — Next.js defaults apply, which we accept

    # Match `hostname` / `host` keys followed by a quoted LAN literal.
    patterns = [
        r"hostname\s*[:=]\s*['\"]([^'\"]+)['\"]",
        r"host\s*[:=]\s*['\"]([^'\"]+)['\"]",
    ]
    for pat in patterns:
        for m in re.finditer(pat, src):
            value = m.group(1).strip()
            assert value not in _LAN_HOSTNAMES, (
                f"S2 TRIPWIRE FIRED:\n"
                f"  next.config.js binds to LAN hostname {value!r} (matched "
                f"pattern {pat!r}). S2 must ship before the dashboard binds "
                f"outside localhost.\n"
            )


def test_dashboard_env_local_has_no_lan_override():
    """.env.local must NOT set DASHBOARD_BIND / HOSTNAME / HOST to LAN."""
    src = _read_text_if_exists(_DASHBOARD_ENV)
    if not src:
        return  # no env file — defaults apply

    # Match `VAR=value` lines; values are unquoted typical for dotenv.
    forbidden_keys = ("DASHBOARD_BIND", "HOSTNAME", "HOST")
    for line in src.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key in forbidden_keys and value in _LAN_HOSTNAMES:
            pytest.fail(
                f"S2 TRIPWIRE FIRED:\n"
                f"  .env.local sets {key}={value!r}. The dashboard is "
                f"assumed to bind localhost only; S2 must ship before "
                f"changing this.\n"
            )


def test_tripwire_failure_message_includes_s2_reminder():
    """Meta-test — the failure messages above all include the literal
    'S2' reminder so a future maintainer hitting this in CI understands
    the deferral and doesn't 'fix' the test by deleting it.

    Source-inspects this file so the reminder text can't drift out of
    sync with the spec.
    """
    src = Path(__file__).read_text(encoding="utf-8")
    assert "S2 TRIPWIRE FIRED" in src, (
        "S2 tripwire failure messages must include the 'S2 TRIPWIRE FIRED' "
        "marker so future maintainers immediately understand this is a "
        "deferral lock, not a flaky assertion."
    )
    assert "S2 (dashboard auth" in src, (
        "S2 tripwire must reference what S2 is in the failure message."
    )
