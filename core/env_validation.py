"""core/env_validation.py — P0.S3 boot-time env-var validation.

Closes the deferral that the P0.0 tripwire kept honest since 2026-05-08:
required env vars (TOGETHER_API_KEY) MUST surface as actionable RuntimeError
at boot, NOT as silent 401 at first API call. Optional env vars (HF_TOKEN)
surface as a banner at boot so the operator knows which fallback path the
pipeline will follow.

Three helpers:

  - ``_validate_together_api_key()`` — required-first. Reads
    ``config.TOGETHER_API_KEY`` (stripped) for the empty-check + reads
    ``config._TOGETHER_API_KEY_RAW`` for the whitespace diagnostic. Raises
    ``RuntimeError`` with POSIX + PowerShell fix instructions on empty.
    Prints WARNING on whitespace (continues — strip already applied at
    config.py module load).

  - ``_surface_hf_token_banner()`` — optional-second. Reads
    ``config.HF_TOKEN``; prints a banner if empty (does NOT raise — the
    ECAPA-valley fallback backend is acceptable for single-speaker scenes;
    multi-speaker quality degrades to binary-split).

  - ``validate_required_env()`` — entry point. Required-first
    (``_validate_together_api_key`` may raise) → optional-second
    (``_surface_hf_token_banner`` informational only). If required raises,
    optional doesn't run. Pipeline cannot reach the privilege-table check
    or any cloud/network probe with an empty TOGETHER_API_KEY.

ORDERING INVARIANT (locked at pipeline.py::run): this module runs AFTER
``_ensure_dashboard_token(FACES_DIR)`` so even if env validation raises,
the dashboard token + auth URL files are already on disk. User fixes env,
restarts, dashboard auth works. AND this module runs BEFORE any cloud
probe so misleading network errors don't mask the actionable empty-key
message.

Spec: ``tests/p0_s3_plan_v1.md`` §1.P1, §1.P3, §1.P4.
"""
from __future__ import annotations

from core import config


def _validate_together_api_key() -> None:
    """TOGETHER_API_KEY is HARD-required. Empty → refuse to start.

    Reads from ``config.TOGETHER_API_KEY`` (stripped) for the empty-check,
    and from ``config._TOGETHER_API_KEY_RAW`` for the whitespace-detection
    diagnostic. Both reads stay through ``config.*`` — P0.S6
    ``test_env_var_reads_centralized`` invariant preserved.
    """
    if not config.TOGETHER_API_KEY:
        raise RuntimeError(
            "TOGETHER_API_KEY is not set or is empty. The pipeline cannot "
            "start without it — every brain/extraction/embedding/vision "
            "agent depends on Together.ai. Fix by setting the env var:\n"
            "  POSIX (bash/zsh):  export TOGETHER_API_KEY=tgp_v1_...\n"
            "  PowerShell:        $env:TOGETHER_API_KEY = 'tgp_v1_...'\n"
            "Get your key at https://api.together.xyz/settings/api-keys, "
            "then restart the pipeline."
        )

    # Whitespace diagnostic — strip is already applied at config.py module
    # load (P0.S3 §1.P1 dual-attr design). If RAW != stripped, the env var
    # had leading/trailing whitespace; we use the stripped value but emit
    # a WARNING so the operator can fix the env var permanently.
    if config._TOGETHER_API_KEY_RAW != config.TOGETHER_API_KEY:
        print(
            "[EnvCheck] WARNING: TOGETHER_API_KEY had leading/trailing "
            "whitespace; stripping for use. Set the env var without "
            "surrounding spaces to silence this WARNING.",
            flush=True,
        )


def _surface_hf_token_banner() -> None:
    """HF_TOKEN missing → log early banner.

    Reads from ``config.HF_TOKEN`` (P0.S3 §1.P4 — centralized via config.py
    for consistency with the TOGETHER_API_KEY pattern). No allowlist
    exception needed for this module.

    Does NOT raise — diarization fallback (ECAPA-valley) is acceptable for
    single-speaker sessions, and ``core/voice.py:302`` still handles the
    lazy-load fallback at first diarize call.
    """
    if not config.HF_TOKEN:
        print(
            "[EnvCheck] HF_TOKEN not set — pyannote speaker-diarization-3.1 "
            "(gated HF model) cannot load. Multi-speaker scenarios will use "
            "the ECAPA-valley fallback backend (binary-split only; less "
            "accurate on 3+ speakers). For diarization-3.1, register at "
            "https://huggingface.co/pyannote/speaker-diarization-3.1 + "
            "set HF_TOKEN.",
            flush=True,
        )


def validate_required_env() -> None:
    """Entry point — required-first, optional-second.

    Called from ``pipeline.py::run()`` AFTER ``_ensure_dashboard_token`` and
    BEFORE the privilege-table integrity check (per the ORDERING INVARIANT
    locked at the call site). If ``_validate_together_api_key`` raises, the
    HF_TOKEN banner does NOT fire — the pipeline is already on its way to
    refuse-to-start; further banners would just be noise.
    """
    _validate_together_api_key()       # required — may raise RuntimeError
    _surface_hf_token_banner()         # optional — banner only, never raises
