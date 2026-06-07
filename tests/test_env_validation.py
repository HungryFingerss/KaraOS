"""tests/test_env_validation.py — P0.S3 env-var validation tests.

9 tests per Plan v1 §2:
  - D1 (4): TOGETHER_API_KEY validation
  - D2 (3): HF_TOKEN banner
  - P1 (2): whitespace handling

Locked exact-substring assertions per Plan v1 §1.P2 (test concreteness):
  - RuntimeError body MUST contain: TOGETHER_API_KEY / export TOGETHER_API_KEY /
    $env:TOGETHER_API_KEY
  - HF_TOKEN banner MUST contain: HF_TOKEN / ECAPA-valley /
    huggingface.co/pyannote/speaker-diarization-3.1
  - Whitespace WARNING MUST contain: TOGETHER_API_KEY / whitespace /
    stripping for use

All tests monkeypatch config.* module attrs (NOT os.environ directly) so the
test stays consistent with the P0.S6 ``test_env_var_reads_centralized``
invariant — env_validation.py reads from config.*, so testing through
config.* validates the actual production path.

Spec: tests/p0_s3_plan_v1.md §2.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_PIPELINE_PY = _REPO_ROOT / "pipeline.py"
_ENV_VALIDATION_PY = _REPO_ROOT / "core" / "env_validation.py"


# ───────────────────────────────────────────────────────────────────────
# D1 — TOGETHER_API_KEY validation (4 tests)
# ───────────────────────────────────────────────────────────────────────


def test_validate_env_raises_on_empty_together_api_key(monkeypatch):
    """D1 test 1 — empty TOGETHER_API_KEY → RuntimeError with the 3
    locked exact substrings. The motivating-failure regression guard:
    without this, an empty key reaches httpx headers and surfaces as
    silent 401 at first API call instead of an actionable boot error.
    """
    from core import config, env_validation

    monkeypatch.setattr(config, "TOGETHER_API_KEY", "")
    monkeypatch.setattr(config, "_TOGETHER_API_KEY_RAW", "")
    # HF_TOKEN value doesn't matter for this test, but pin it so the
    # validate_required_env entry point doesn't emit a banner.
    monkeypatch.setattr(config, "HF_TOKEN", "fake-hf-token")

    with pytest.raises(RuntimeError) as excinfo:
        env_validation.validate_required_env()

    body = str(excinfo.value)
    assert "TOGETHER_API_KEY" in body, (
        "RuntimeError body MUST name the env var (operator searches the message "
        "for the var they forgot to set)"
    )
    assert "export TOGETHER_API_KEY" in body, (
        "RuntimeError body MUST include POSIX (bash/zsh) fix instruction"
    )
    assert "$env:TOGETHER_API_KEY" in body, (
        "RuntimeError body MUST include PowerShell fix instruction "
        "(Windows is a supported dev platform)"
    )


def test_validate_env_accepts_non_empty_together_api_key(monkeypatch, capsys):
    """D1 test 2 — clean non-empty key → no raise + no WARNING output.
    Happy-path regression guard: ensures the empty-check doesn't
    false-positive on valid keys.
    """
    from core import config, env_validation

    monkeypatch.setattr(config, "TOGETHER_API_KEY", "tgp_v1_validkey")
    monkeypatch.setattr(config, "_TOGETHER_API_KEY_RAW", "tgp_v1_validkey")
    monkeypatch.setattr(config, "HF_TOKEN", "fake-hf-token")

    # Should not raise
    env_validation._validate_together_api_key()

    out = capsys.readouterr().out
    assert "WARNING" not in out, (
        "clean key MUST NOT trigger any WARNING (whitespace-diagnostic should "
        "stay silent on the happy path); got: " + repr(out)
    )


def test_validate_env_reads_from_config_not_os_getenv():
    """D1 test 3 — AST source-inspection of
    ``core/env_validation.py::_validate_together_api_key`` asserts the
    function body reads ``config.TOGETHER_API_KEY`` (and/or
    ``config._TOGETHER_API_KEY_RAW``) and does NOT contain any
    ``os.getenv("TOGETHER_API_KEY", ...)`` call.

    P0.S6 ``test_env_var_reads_centralized`` invariant preservation —
    env reads stay in config.py only; consumers go through module attrs.
    """
    from core import env_validation

    fn_src = inspect.getsource(env_validation._validate_together_api_key)

    # Positive: must reference config.TOGETHER_API_KEY (the stripped value)
    assert "config.TOGETHER_API_KEY" in fn_src, (
        "_validate_together_api_key MUST read config.TOGETHER_API_KEY (the "
        "stripped value) for the empty-check — P0.S6 + Plan v1 §1.P1"
    )

    # Negative: must NOT contain os.getenv for TOGETHER_API_KEY
    # Parse the function and walk for any Call node matching os.getenv(...)
    tree = ast.parse(fn_src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == "getenv":
                # Could be config.os.getenv... we want to flag os.getenv calls
                if isinstance(f.value, ast.Name) and f.value.id == "os":
                    # Verify the first arg references TOGETHER_API_KEY
                    if node.args and isinstance(node.args[0], ast.Constant):
                        if "TOGETHER_API_KEY" in str(node.args[0].value):
                            pytest.fail(
                                "_validate_together_api_key contains "
                                "os.getenv('TOGETHER_API_KEY', ...) call — "
                                "MUST read through config.* per P0.S6 invariant"
                            )


def test_pipeline_run_calls_validate_env_after_dashboard_token():
    """D1 test 4 — AST/source-ordering check on ``pipeline.py::run``.
    Verifies the locked ordering: ``_ensure_dashboard_token`` →
    ``validate_required_env`` → privilege-table check. The whole point
    of Plan v1 §1.P3.
    """
    src = _PIPELINE_PY.read_text(encoding="utf-8")
    # Anchor on each of the 3 locked landmarks
    dash_idx = src.find("_ensure_dashboard_token(FACES_DIR)")
    env_idx = src.find("validate_required_env()")
    priv_idx = src.find("validate_tool_registries(")  # P1.A1 SP-7a: validation extracted to runtime/boot_checks.py; ordering now enforced at the run() call site

    assert dash_idx > 0, "pipeline.py::run MUST call _ensure_dashboard_token"
    assert env_idx > 0, "pipeline.py::run MUST call validate_required_env() (P0.S3)"
    assert priv_idx > 0, "pipeline.py::run MUST call validate_tool_registries (tool-registry validation)"

    assert dash_idx < env_idx, (
        "ORDERING INVARIANT (P0.S2 → P0.S3): _ensure_dashboard_token MUST "
        "run BEFORE validate_required_env so the dashboard token + auth URL "
        "files exist even when env validation raises. Without this ordering, "
        "an empty TOGETHER_API_KEY would create a chicken/egg recovery loop "
        "where the user cannot find the auth URL until they fix the env, but "
        "cannot start the pipeline to write the auth URL until they fix the env."
    )
    assert env_idx < priv_idx, (
        "ORDERING INVARIANT (P0.S3 → privilege-table): validate_required_env "
        "MUST run BEFORE the privilege-table check so an empty TOGETHER_API_KEY "
        "surfaces as an actionable RuntimeError BEFORE the brain tool loop "
        "can fail with a misleading network/privilege error. Plan v1 §1.P3."
    )

    # Belt-and-braces: ORDERING INVARIANT literal must be present at the
    # call site for future-grep coverage
    assert "ORDERING INVARIANT" in src[dash_idx:priv_idx], (
        "pipeline.py::run MUST contain the literal 'ORDERING INVARIANT' "
        "comment marker between _ensure_dashboard_token and the privilege "
        "check — future-grep target locked at Plan v1 §1.P3"
    )


# ───────────────────────────────────────────────────────────────────────
# D2 — HF_TOKEN banner (3 tests)
# ───────────────────────────────────────────────────────────────────────


def test_surface_hf_token_banner_when_missing(monkeypatch, capsys):
    """D2 test 5 — empty HF_TOKEN → banner with the 3 locked exact
    substrings. The banner is the operator-facing signal that multi-
    speaker scenes will use the ECAPA-valley fallback instead of the
    higher-quality pyannote diarization-3.1.
    """
    from core import config, env_validation

    monkeypatch.setattr(config, "HF_TOKEN", "")

    env_validation._surface_hf_token_banner()

    out = capsys.readouterr().out
    assert "HF_TOKEN" in out, "banner MUST name the env var"
    assert "ECAPA-valley" in out, (
        "banner MUST name the fallback backend so operator can grep voice.py "
        "for the trade-off"
    )
    assert "huggingface.co/pyannote/speaker-diarization-3.1" in out, (
        "banner MUST include the HF model URL (operator-actionable fix path; "
        "catches model-name drift if the URL slug changes)"
    )


def test_surface_hf_token_banner_silent_when_set(monkeypatch, capsys):
    """D2 test 6 — HF_TOKEN set → no banner output. Happy-path
    regression guard: ensures the banner doesn't false-fire on valid
    configs.
    """
    from core import config, env_validation

    monkeypatch.setattr(config, "HF_TOKEN", "fake-hf-token")

    env_validation._surface_hf_token_banner()

    out = capsys.readouterr().out
    assert out == "", (
        "HF_TOKEN set MUST NOT trigger the banner (silent happy path); "
        "got: " + repr(out)
    )


def test_validate_env_calls_hf_token_banner_after_together_check():
    """D2 test 7 — AST/source-inspection of
    ``validate_required_env``: assert
    ``_validate_together_api_key`` call appears BEFORE
    ``_surface_hf_token_banner`` call. Required-first, optional-second
    ordering — if required raises, optional doesn't run.
    """
    from core import env_validation

    fn_src = inspect.getsource(env_validation.validate_required_env)
    together_idx = fn_src.find("_validate_together_api_key()")
    hf_idx = fn_src.find("_surface_hf_token_banner()")

    assert together_idx > 0, (
        "validate_required_env MUST call _validate_together_api_key()"
    )
    assert hf_idx > 0, (
        "validate_required_env MUST call _surface_hf_token_banner()"
    )
    assert together_idx < hf_idx, (
        "validate_required_env MUST call _validate_together_api_key BEFORE "
        "_surface_hf_token_banner — if required-first raises, the optional "
        "banner is suppressed (the pipeline is on its way to refuse-to-start "
        "and further banners would just be noise). Plan v1 §1.P3."
    )


# ───────────────────────────────────────────────────────────────────────
# P1 — Whitespace handling (2 tests; NEW per Plan v1 §1.P1)
# ───────────────────────────────────────────────────────────────────────


def test_validate_env_warns_on_whitespace_in_together_api_key(monkeypatch, capsys):
    """P1 test 8 — RAW has leading/trailing whitespace + stripped is
    clean → WARNING with 3 locked exact substrings. The strip already
    happened at config.py module load; this WARNING tells the operator
    to fix the env var permanently.
    """
    from core import config, env_validation

    monkeypatch.setattr(config, "TOGETHER_API_KEY", "abc123")
    monkeypatch.setattr(config, "_TOGETHER_API_KEY_RAW", "  abc123  ")

    # Should NOT raise — the empty-check passes (stripped is non-empty);
    # the whitespace diagnostic just prints a WARNING.
    env_validation._validate_together_api_key()

    out = capsys.readouterr().out
    assert "TOGETHER_API_KEY" in out, (
        "WARNING MUST name the env var so operator can find it in their shell"
    )
    assert "whitespace" in out, (
        "WARNING MUST contain 'whitespace' for diagnostic substring matching"
    )
    assert "stripping for use" in out, (
        "WARNING MUST contain 'stripping for use' so operator knows the "
        "pipeline already applied the fix and the env var is the source"
    )


def test_validate_env_silent_when_no_whitespace(monkeypatch, capsys):
    """P1 test 9 — RAW == stripped (no whitespace in env) → NO WARNING.
    Negative regression guard against the whitespace diagnostic firing
    spuriously on clean keys.
    """
    from core import config, env_validation

    monkeypatch.setattr(config, "TOGETHER_API_KEY", "tgp_v1_clean")
    monkeypatch.setattr(config, "_TOGETHER_API_KEY_RAW", "tgp_v1_clean")

    env_validation._validate_together_api_key()

    out = capsys.readouterr().out
    assert "whitespace" not in out.lower(), (
        "clean key MUST NOT trigger the whitespace WARNING (silent happy path); "
        "got: " + repr(out)
    )
    assert out == "", (
        "_validate_together_api_key MUST produce zero output on the happy "
        "path; got: " + repr(out)
    )
