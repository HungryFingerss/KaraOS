"""P0.R4 — Process supervisor structural invariants (9 logical anchors).

Validates the 4 deployment artifacts under deploy/ via configparser-based
structural tests (cross-platform; runs on Windows dev + Linux CI; no
systemd-analyze dependency). Systemd semantic verification happens at
deployment time per deploy/README.md §4 verification commands.

Per Plan v2 §3 LOCK: 9 anchors at exact mid 9 inclusive ±15% band [7.65, 10.35].
Plan v2 absorbs Plan v1 PI #1 by:
  - A8 REPLACED with programmatic enforcement (was hardcoded TOGETHER_API_KEY
    + HF_TOKEN check; now extracts every os.getenv(...) key from core/config.py
    and asserts each appears in deploy/karaos.env.example)
  - A9 EXPANDED to cover all 4 secret-class env vars (was 2: TOGETHER_API_KEY
    + HF_TOKEN; now 4: + GROQ_API_KEY + TAVILY_API_KEY)
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import configparser
import inspect
import re
from pathlib import Path

import pytest


# Repo-relative paths resolved from this test file's location.
# tests/test_p0_r4_process_supervisor.py -> parent.parent == repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SYSTEMD_UNIT = _REPO_ROOT / "deploy" / "systemd" / "karaos.service"
_SUPERVISORD_CONF = _REPO_ROOT / "deploy" / "supervisord" / "karaos.conf"
_README = _REPO_ROOT / "deploy" / "README.md"
_ENV_TEMPLATE = _REPO_ROOT / "deploy" / "karaos.env.example"


def _read_text(path: Path) -> str:
    assert path.exists(), f"Required P0.R4 artifact missing at {path}"
    return path.read_text(encoding="utf-8")


def _parse_ini(path: Path) -> configparser.ConfigParser:
    """Parse an INI-style file with interpolation disabled.

    Disabled because supervisord uses ``%(ENV_X)s`` literally as a
    supervisord-side env-interpolation marker, not as ConfigParser's
    own ``%(name)s`` substitution syntax. Standard ConfigParser would
    raise InterpolationSyntaxError on those values.
    """
    parser = configparser.ConfigParser(
        interpolation=None,
        strict=True,
        delimiters=("=",),
    )
    # Preserve case on option keys; default ``optionxform`` lowercases.
    parser.optionxform = str  # type: ignore[assignment]
    parser.read(path, encoding="utf-8")
    return parser


# ---------------------------------------------------------------------------
# D1 — systemd unit file anchors (A1 - A4)
# ---------------------------------------------------------------------------


def test_p0_r4_d1_anchor_1_systemd_unit_exists() -> None:
    """A1 — File exists at deploy/systemd/karaos.service, non-empty, parseable."""
    assert _SYSTEMD_UNIT.exists(), (
        f"D1 systemd unit missing at {_SYSTEMD_UNIT}. Required by Plan v1 §2.1."
    )
    content = _read_text(_SYSTEMD_UNIT)
    assert content.strip(), "D1 systemd unit is empty"
    # Parseability check — must not raise.
    parser = _parse_ini(_SYSTEMD_UNIT)
    assert parser.sections(), (
        "D1 systemd unit parsed but contains zero sections; expected [Unit] + "
        "[Service] + [Install] per Plan v1 §2.1 LOCKED spec."
    )


def test_p0_r4_d1_anchor_2_systemd_unit_has_required_sections() -> None:
    """A2 — [Unit] + [Service] + [Install] sections present."""
    parser = _parse_ini(_SYSTEMD_UNIT)
    required = {"Unit", "Service", "Install"}
    present = set(parser.sections())
    missing = required - present
    assert not missing, (
        f"D1 systemd unit missing required sections: {sorted(missing)}. "
        f"Present sections: {sorted(present)}. Per Plan v1 §2.1 LOCKED spec, "
        f"all three sections must be present for systemd to load the unit + "
        f"enable it via WantedBy=multi-user.target."
    )


def test_p0_r4_d1_anchor_3_systemd_restart_directives_present() -> None:
    """A3 — [Service] has Restart=on-failure + RestartSec= + StartLimitBurst= +
    StartLimitIntervalSec= directives (bounded burst limit auto-restart per Q3
    LOCK 2026-05-23).
    """
    content = _read_text(_SYSTEMD_UNIT)
    # Substring checks against the file content (preserves exact spec semantics
    # from Plan v1 §2.1; deliberate-regression (a) drops Restart=on-failure and
    # expects this anchor to fire).
    required_substrings = [
        "Restart=on-failure",
        "RestartSec=",
        "StartLimitBurst=",
        "StartLimitIntervalSec=",
    ]
    for needle in required_substrings:
        assert needle in content, (
            f"D1 systemd [Service] missing restart directive {needle!r}. "
            f"Per Plan v1 §2.1 + Q3 verdict 2026-05-23, the bounded burst "
            f"limit auto-restart contract requires all four directives. "
            f"Dropping any one breaks the spec's prevent-thrashing invariant."
        )


def test_p0_r4_d1_anchor_4_systemd_environment_file_reference() -> None:
    """A4 — [Service] has EnvironmentFile=... AND no inline Environment= with
    secret-looking values (P0.S6 compliance).
    """
    content = _read_text(_SYSTEMD_UNIT)
    # Positive check: EnvironmentFile= directive references external file
    assert "EnvironmentFile=" in content, (
        "D1 systemd [Service] missing EnvironmentFile= directive. Per Plan v1 "
        "§2.1 + P0.S6 secrets discipline, the unit MUST reference an external "
        "env file (chmod 0600, owned by karaos) rather than carry inline "
        "secret values."
    )
    # Negative check: no inline Environment= lines that look like secrets.
    # Pattern matches lines beginning with Environment=" (NOT EnvironmentFile=)
    # and carrying a *_API_KEY= assignment that looks populated.
    leak_pattern = re.compile(
        r'^Environment\s*=\s*"?[^=\n]*_API_KEY\s*=\s*["\']?(?:sk-|tvly-|gsk_|hf_)',
        re.MULTILINE | re.IGNORECASE,
    )
    leak_match = leak_pattern.search(content)
    assert leak_match is None, (
        f"D1 systemd [Service] contains inline Environment= line with "
        f"secret-looking value: {leak_match.group(0)!r}. P0.S6 discipline "
        f"forbids leaked secrets in committed configuration. Use "
        f"EnvironmentFile=/etc/karaos/karaos.env with chmod 0600 instead."
    )


# ---------------------------------------------------------------------------
# D2 — supervisord config anchors (A5 - A6)
# ---------------------------------------------------------------------------


def test_p0_r4_d2_anchor_1_supervisord_conf_exists() -> None:
    """A5 — File exists at deploy/supervisord/karaos.conf, configparser-parseable."""
    assert _SUPERVISORD_CONF.exists(), (
        f"D2 supervisord config missing at {_SUPERVISORD_CONF}. Required by "
        f"Plan v1 §2.2."
    )
    parser = _parse_ini(_SUPERVISORD_CONF)
    assert "program:karaos" in parser.sections(), (
        f"D2 supervisord config parsed but [program:karaos] section absent. "
        f"Present sections: {sorted(parser.sections())}. Per Plan v1 §2.2, "
        f"the single program section drives supervisord's program lifecycle."
    )


def test_p0_r4_d2_anchor_2_supervisord_program_section_has_autorestart() -> None:
    """A6 — [program:karaos] has autorestart=true + startretries= + startsecs=
    directives (native exponential backoff per Q3 LOCK 2026-05-23).
    """
    parser = _parse_ini(_SUPERVISORD_CONF)
    section = parser["program:karaos"]
    # autorestart contract — exact value match (Plan v2 §2.6 (c) deliberate-regression
    # drops autorestart=true and expects this anchor to fire).
    assert section.get("autorestart") == "true", (
        f"D2 [program:karaos] missing or mismatched autorestart=true. "
        f"Current value: {section.get('autorestart')!r}. Per Plan v1 §2.2 + "
        f"Q3 verdict, supervisord's native exponential backoff requires "
        f"autorestart=true."
    )
    # Companion directives — presence-only check (values are Plan v1 §2.2 LOCKED
    # but precision matching is reserved for the supervisor's own validator).
    assert "startretries" in section, (
        "D2 [program:karaos] missing startretries= directive. Per Plan v1 §2.2, "
        "the retry cap (10) bounds consecutive failures."
    )
    assert "startsecs" in section, (
        "D2 [program:karaos] missing startsecs= directive. Per Plan v1 §2.2, "
        "the boot stabilization window (5s) defines when a launch counts as "
        "successful for backoff reset."
    )


# ---------------------------------------------------------------------------
# D3 — installation README anchor (A7)
# ---------------------------------------------------------------------------


def test_p0_r4_d3_anchor_1_readme_exists_and_covers_both_supervisors() -> None:
    """A7 — File exists at deploy/README.md AND contains systemd + supervisord
    install section headers + systemctl + supervisorctl command examples.
    """
    content = _read_text(_README)
    # Per Plan v1 §2.3 + §2.6 (d) deliberate-regression — dropping supervisorctl
    # references from the README must fire this anchor.
    required_substrings = ["systemd", "supervisord", "systemctl", "supervisorctl"]
    missing = [s for s in required_substrings if s not in content]
    assert not missing, (
        f"D3 README at {_README} missing required substrings: {missing}. "
        f"Per Plan v1 §2.3 + §2.6 (d), both supervisors must be documented "
        f"with their respective control commands (systemctl + supervisorctl)."
    )


# ---------------------------------------------------------------------------
# D4 — env file template anchors (A8 PROGRAMMATIC + A9 EXPANDED per Plan v2)
# ---------------------------------------------------------------------------


def test_p0_r4_d4_anchor_1_env_template_documents_all_config_env_vars() -> None:
    """A8 (Plan v2 LOCKED) — programmatic enforcement: every os.getenv(...)
    key in core/config.py MUST appear in deploy/karaos.env.example.

    Replaces Plan v1's hardcoded TOGETHER_API_KEY + HF_TOKEN check with
    programmatic extraction. Future env vars automatically caught.

    Per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine
    (elevated at P0.R4 Plan v1 verdict 2026-05-23) — child enforcement at
    test surface backs the architect-side Pass-2 grep discipline.

    Plan v2 §2.6 deliberate-regression (e): dropping the TAVILY_API_KEY= line
    from the template must fire this anchor programmatically.
    """
    # Extract os.getenv(...) keys from core/config.py via regex over its source.
    # Regex matches uppercase-only identifiers (case-SENSITIVE [A-Z_][A-Z0-9_]*);
    # corrected from Plan v2 §2.5 source comment "case-insensitive" which mis-
    # described the actual regex behavior (non-blocking observation banked at
    # Phase 0 verdict 2026-05-23; correction applied at Phase 3 test-write time).
    import core.config as cfg
    config_source = inspect.getsource(cfg)
    env_keys = set(re.findall(
        r'''os\.getenv\(["']([A-Z_][A-Z0-9_]*)["']''',
        config_source,
    ))
    assert env_keys, (
        "A8 sanity: regex extracted zero os.getenv(...) keys from core/config.py. "
        "Either the regex is broken or config.py no longer uses os.getenv — "
        "investigate before silencing this assertion."
    )

    assert _ENV_TEMPLATE.exists(), (
        f"D4 env template missing at {_ENV_TEMPLATE}. Required by Plan v2 §2.4."
    )
    template_content = _ENV_TEMPLATE.read_text(encoding="utf-8")

    missing = set()
    for key in env_keys:
        # Accept either uncommented (`KEY=`) or commented (`# KEY=...`) form.
        # Commented form covers documented optional overrides like
        # ``# DASHBOARD_BIND=127.0.0.1``.
        if not re.search(
            rf"^(?:#\s*)?{re.escape(key)}=",
            template_content,
            re.MULTILINE,
        ):
            missing.add(key)

    assert not missing, (
        f"D4 env template at {_ENV_TEMPLATE} is missing keys from "
        f"core/config.py: {sorted(missing)}. Per Plan v2 §2.4 contract, every "
        f"os.getenv(...) key in core/config.py must appear in the template "
        f"(either as uncommented required entry or commented optional override). "
        f"Current config.py keys: {sorted(env_keys)}."
    )


def test_p0_r4_d4_anchor_2_env_template_values_are_empty_per_p0s6() -> None:
    """A9 (Plan v2 LOCKED) — P0.S6 compliance: secret-class env vars in
    deploy/karaos.env.example MUST have EMPTY values (no leaked secrets).

    Expanded from Plan v1's 2-key check to cover all 4 secret-class keys from
    core/config.py: TOGETHER_API_KEY + HF_TOKEN + GROQ_API_KEY + TAVILY_API_KEY.

    Plan v2 §2.6 deliberate-regression (f): adding ``TOGETHER_API_KEY=sk-real-secret``
    to the template must fire this anchor.
    """
    # Secret-class allowlist (extended at Plan v2 absorption). Future cycles
    # update this set when new secret-class env vars are added to core/config.py.
    _SECRET_CLASS_ENV_VARS = frozenset({
        "TOGETHER_API_KEY",
        "HF_TOKEN",
        "GROQ_API_KEY",
        "TAVILY_API_KEY",
    })

    template_content = _ENV_TEMPLATE.read_text(encoding="utf-8")

    violations = {}
    for key in _SECRET_CLASS_ENV_VARS:
        # Look for KEY=value (uncommented; non-empty value = violation).
        match = re.search(
            rf"^{re.escape(key)}=(.+)$",
            template_content,
            re.MULTILINE,
        )
        if match and match.group(1).strip():
            violations[key] = match.group(1).strip()

    assert not violations, (
        f"D4 env template at {_ENV_TEMPLATE} has non-empty values for "
        f"secret-class env vars (P0.S6 compliance violation): {violations}. "
        f"All secret-class keys ({sorted(_SECRET_CLASS_ENV_VARS)}) must have "
        f"EMPTY values in the template; operator fills in actual values when "
        f"deploying. Per P0.S6 discipline + Plan v2 §2.4 contract."
    )
