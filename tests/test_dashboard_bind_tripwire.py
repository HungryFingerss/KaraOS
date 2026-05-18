"""P0.0 + S2 tripwire: dashboard bind address regression guard.

S2 (dashboard auth + per-install token + cookie-gated routes) is deferred
under the assumption that the dashboard binds to localhost only. If anyone
changes the bind for legitimate reasons (LAN access from phone, tablet,
etc.) without first shipping S2, this test fails and surfaces "are you
sure?" before the change ships.

Same pattern as P0.11's atomic-replace structural test — preventive
hardening that locks the precondition justifying the deferral.

**THE PROPER RESPONSE TO THIS TEST FAILING IS TO SHIP S2** — auth,
per-install token, cookie-gated routes. NOT to update the test.

P0.0.1 tightening (post-auditor known-gap review):
  The original tripwire passed when `--hostname` was ABSENT from
  package.json scripts. Next.js defaults to `0.0.0.0` when --hostname is
  unspecified, so the absence of an explicit flag = LAN exposure today.
  The original tripwire was theater under that default.
  P0.0.1 fixes the package.json scripts to explicitly bind 127.0.0.1
  AND tightens this tripwire to REQUIRE the explicit flag (not just
  absence of 0.0.0.0).

Scope:
  - Checks dashboard `package.json` scripts REQUIRE explicit
    `--hostname 127.0.0.1` flag.
  - Checks `next.config.js` for hostname config pointing to LAN.
  - Checks the dashboard `.env.local` for DASHBOARD_BIND / HOSTNAME
    overrides pointing to LAN.
"""
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


def test_dashboard_package_json_scripts_explicitly_bind_localhost():
    """P0.0.1 tightening of the S2 tripwire: package.json scripts MUST
    explicitly bind to 127.0.0.1 via the --hostname flag. Next.js's
    default of 0.0.0.0 is the failure mode the tripwire catches.

    A MISSING --hostname flag is NOT acceptable — Next.js's default
    binding is 0.0.0.0 (LAN-exposed). Explicit --hostname 127.0.0.1
    (or `localhost` / `::1`) is required.

    Originally (pre-P0.0.1) this tripwire allowed absent --hostname
    flags, on the false premise that "no explicit LAN bind" meant
    "localhost." Auditor's known-gap review surfaced the real Next.js
    default; P0.0.1 fixed both the package.json scripts and this test.

    S2 (dashboard auth + per-install token + cookie-gated routes) is
    the proper fix when LAN exposure becomes legitimate. Until then,
    this tripwire keeps the deferral honest.
    """
    assert _PACKAGE_JSON.exists(), f"dashboard package.json missing at {_PACKAGE_JSON}"

    pkg = json.loads(_PACKAGE_JSON.read_text(encoding="utf-8"))
    scripts = pkg.get("scripts", {})

    for script_name in _SCRIPTS_REQUIRING_EXPLICIT_BIND:
        cmd = scripts.get(script_name)
        assert cmd is not None, (
            f"S2 TRIPWIRE FIRED — required script {script_name!r} missing "
            f"from package.json. The tripwire's invariant assumes both "
            f"`dev` and `start` exist and bind explicitly to localhost; "
            f"a missing script is either a rename (update "
            f"_SCRIPTS_REQUIRING_EXPLICIT_BIND) or accidental deletion."
        )

        hostname = _find_explicit_hostname_in_command(cmd)
        assert hostname is not None, (
            f"S2 TRIPWIRE FIRED — script {script_name!r} has no --hostname "
            f"flag:\n"
            f"  current: {cmd!r}\n"
            f"  fix:     add `--hostname 127.0.0.1` to the command\n"
            f"  why:     Next.js defaults to 0.0.0.0 when --hostname is "
            f"unset → LAN-exposed dashboard\n"
            f"\n"
            f"  S2 (dashboard auth + per-install token + cookie-gated "
            f"routes) MUST ship before exposing to LAN. PROPER RESPONSE: "
            f"either restore the localhost flag, or ship S2 first and "
            f"then update _SCRIPTS_REQUIRING_EXPLICIT_BIND.\n"
        )

        assert hostname in _LOCALHOST_HOSTNAMES, (
            f"S2 TRIPWIRE FIRED — script {script_name!r} binds to "
            f"non-localhost hostname {hostname!r}:\n"
            f"  current: {cmd!r}\n"
            f"  S2 MUST ship before exposing the dashboard to LAN.\n"
            f"\n"
            f"  Accepted localhost values: {sorted(_LOCALHOST_HOSTNAMES)}.\n"
            f"  Anything else (including {hostname!r}) is treated as LAN "
            f"exposure and must wait for S2.\n"
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
