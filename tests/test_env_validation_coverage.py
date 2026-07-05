"""100% coverage for core.env_validation — boot-time env-var validation (P0.S3).
Part of the coverage-to-100 campaign (see COVERAGE.md)."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import pytest

from core import config, env_validation

def test_validate_required_env_runs_banner_when_key_present(monkeypatch, capsys):
    # key present -> _validate_together_api_key passes -> banner runs (line 112)
    monkeypatch.setattr(config, "TOGETHER_API_KEY", "tgp_v1_test", raising=False)
    monkeypatch.setattr(config, "_TOGETHER_API_KEY_RAW", "tgp_v1_test", raising=False)
    monkeypatch.setattr(config, "HF_TOKEN", "", raising=False)  # empty -> banner fires
    env_validation.validate_required_env()  # must not raise
    assert "HF_TOKEN not set" in capsys.readouterr().out

def test_validate_required_env_raises_when_key_missing(monkeypatch):
    monkeypatch.setattr(config, "TOGETHER_API_KEY", "", raising=False)
    with pytest.raises(RuntimeError) as ei:
        env_validation.validate_required_env()
    assert "TOGETHER_API_KEY is not set" in str(ei.value)

def test_whitespace_key_warns_but_does_not_raise(monkeypatch, capsys):
    monkeypatch.setattr(config, "TOGETHER_API_KEY", "tgp_v1_x", raising=False)
    monkeypatch.setattr(config, "_TOGETHER_API_KEY_RAW", "  tgp_v1_x  ", raising=False)
    env_validation._validate_together_api_key()
    assert "WARNING" in capsys.readouterr().out

def test_hf_token_present_no_banner(monkeypatch, capsys):
    monkeypatch.setattr(config, "HF_TOKEN", "hf_realtoken", raising=False)
    env_validation._surface_hf_token_banner()
    assert "HF_TOKEN not set" not in capsys.readouterr().out
