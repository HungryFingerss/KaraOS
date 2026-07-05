"""100% coverage for runtime.boot_checks — tool-registry consistency validation
+ instance-mode declaration (P1.A1 SP-7a/7c). Pure logic: registries are passed
in / monkeypatched, so every raise branch is reachable. Part of the
coverage-to-100 campaign (see COVERAGE.md)."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import pytest

import core.config as config
import runtime.boot_checks as bc

def _tools(*names):
    return [{"function": {"name": n}} for n in names]

@pytest.fixture
def valid_registries(monkeypatch):
    """A fully-consistent registry set for one tool 't1'. Tests break one axis."""
    monkeypatch.setattr(bc, "TOOL_PRIVILEGES", {"t1": None})
    monkeypatch.setattr(config, "TOOL_INTENT_MAP", {"t1": "intent"})
    monkeypatch.setattr(config, "INTENT_OPTIONAL_TOOLS", frozenset())
    monkeypatch.setattr(config, "INLINE_DISPATCHED_TOOLS", frozenset())
    return {
        "brain": _tools("t1"),
        "fallbacks": {"t1": "here you go"},
        "handlers": {"t1": object()},
    }

def _run(reg):
    bc.validate_tool_registries(reg["brain"], reg["fallbacks"], reg["handlers"])

def test_consistent_registries_pass(valid_registries):
    _run(valid_registries)  # no raise (all happy-path branches)

def test_privilege_missing_raises(valid_registries, monkeypatch):
    monkeypatch.setattr(bc, "TOOL_PRIVILEGES", {})  # t1 missing
    with pytest.raises(RuntimeError, match="TOOL_PRIVILEGES missing"):
        _run(valid_registries)

def test_intent_missing_raises(valid_registries, monkeypatch):
    monkeypatch.setattr(config, "TOOL_INTENT_MAP", {})
    with pytest.raises(RuntimeError, match="missing from TOOL_INTENT_MAP"):
        _run(valid_registries)

def test_intent_orphan_raises(valid_registries, monkeypatch):
    monkeypatch.setattr(config, "TOOL_INTENT_MAP", {"t1": "i", "ghost": "i"})
    with pytest.raises(RuntimeError, match="intent registry but not in brain.TOOLS"):
        _run(valid_registries)

def test_fallback_missing_raises(valid_registries):
    valid_registries["fallbacks"] = {}
    with pytest.raises(RuntimeError, match="_TOOL_FALLBACKS missing"):
        _run(valid_registries)

def test_fallback_orphan_raises(valid_registries):
    valid_registries["fallbacks"] = {"t1": "ok", "ghost": "x"}
    with pytest.raises(RuntimeError, match="not in brain.TOOLS"):
        _run(valid_registries)

def test_fallback_degenerate_raises(valid_registries):
    valid_registries["fallbacks"] = {"t1": "   "}  # whitespace-only
    with pytest.raises(RuntimeError, match="empty/whitespace-only"):
        _run(valid_registries)

def test_handler_missing_raises(valid_registries):
    valid_registries["handlers"] = {}
    with pytest.raises(RuntimeError, match="missing from _TOOL_HANDLERS"):
        _run(valid_registries)

def test_handler_orphan_raises(valid_registries):
    valid_registries["handlers"] = {"t1": object(), "ghost": object()}
    with pytest.raises(RuntimeError, match="_TOOL_HANDLERS has entries for tools not in"):
        _run(valid_registries)

def test_instance_mode_valid(monkeypatch, capsys):
    monkeypatch.setattr(config, "KARAOS_INSTANCE_MODE", "base")
    bc.validate_instance_mode()
    out = capsys.readouterr().out
    assert "instance_mode=base" in out and "WARNING" not in out

def test_instance_mode_invalid_warns_and_defaults(monkeypatch, capsys):
    monkeypatch.setattr(config, "KARAOS_INSTANCE_MODE", "bogus_mode")
    bc.validate_instance_mode()
    out = capsys.readouterr().out
    assert "WARNING" in out and "instance_mode=base" in out
