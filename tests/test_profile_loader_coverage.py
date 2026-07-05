"""Covers core.profile_loader fail-loud raises + the generic top-level
scalar-section dispatch: missing file, bad YAML, non-mapping top level, bad
`profile` sentinel, non-mapping section body, and every malformed
leaf / cloud-timing / agent-select / block-select body. Part of the
coverage-to-100 campaign."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import pytest

import core.profile_loader as pl
from core.profile_loader import (
    ProfileError,
    load_profile,
    _validate,
    _check_leaf,
    _check_cloud_timing,
    _check_agent_select,
    _check_block_select,
)

# ── positive control — a valid synthetic profile validates clean ──────────────

def test_validate_valid_profile_no_raise():
    """Guards against every raise-test being a false positive: a well-formed
    profile passes _validate silently."""
    _validate({"profile": "companion", "features": {"emotion": True}}, "companion", "<x>")

# ── load_profile: file / format guards (lines 84, 91-92, 94) ──────────────────

def test_load_profile_missing_file_raises(tmp_path, monkeypatch):
    # name is valid (in VALID_PROFILES) but no <name>.yaml on disk -> line 84
    monkeypatch.setattr(pl, "_PROFILES_DIR", tmp_path)
    with pytest.raises(ProfileError, match="Profile file missing"):
        load_profile("companion")

def test_load_profile_invalid_yaml_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "_PROFILES_DIR", tmp_path)
    (tmp_path / "companion.yaml").write_text("foo: [1, 2, 3", encoding="utf-8")  # unclosed -> 91-92
    with pytest.raises(ProfileError, match="is not valid YAML"):
        load_profile("companion")

def test_load_profile_non_mapping_top_level_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "_PROFILES_DIR", tmp_path)
    (tmp_path / "companion.yaml").write_text("- a\n- b\n", encoding="utf-8")  # a YAML list -> 94
    with pytest.raises(ProfileError, match="must be a YAML mapping at top level"):
        load_profile("companion")

# ── _validate: `profile` sentinel (lines 127, 131) ────────────────────────────

def test_validate_profile_sentinel_not_string():
    with pytest.raises(ProfileError, match="'profile' must be a string"):
        _validate({"profile": 123}, "companion", "<x>")  # decl not str -> 127

def test_validate_profile_sentinel_mismatch():
    with pytest.raises(ProfileError, match="does not match the selected profile"):
        _validate({"profile": "robotics"}, "companion", "<x>")  # decl != name -> 131

# ── _validate: generic top-level scalar-section dispatch (lines 141-142) ───────

def test_validate_top_level_scalar_section(monkeypatch):
    """The real SCHEMA's only scalar section is `profile` (special-cased earlier),
    so the generic top-level scalar dispatch never fires against shipped data.
    Add a scalar section to the schema data and drive it with a valid value ->
    _check_scalar runs and `continue` executes (141-142), no raise."""
    patched = dict(pl.SCHEMA)
    patched["extra_scalar"] = {"kind": "scalar", "type": str}
    monkeypatch.setattr(pl, "SCHEMA", patched)
    _validate({"extra_scalar": "value"}, "companion", "<x>")  # no raise

# ── _validate: non-mapping section body (line 151) ────────────────────────────

def test_validate_section_body_not_mapping():
    with pytest.raises(ProfileError, match="must be a mapping; got"):
        _validate({"features": "not a dict"}, "companion", "<x>")  # section body str -> 151

# ── _check_leaf (lines 190, 196) ──────────────────────────────────────────────

def test_check_leaf_value_not_dict():
    with pytest.raises(ProfileError, match="must be a mapping of"):
        _check_leaf("llm", "chat", "not-a-dict", "<x>")  # -> 190

def test_check_leaf_unknown_leaf_key():
    with pytest.raises(ProfileError, match="unknown LLM leaf key"):
        _check_leaf("llm", "chat", {"badkey": "x"}, "<x>")  # -> 196

# ── _check_cloud_timing (lines 210, 216, 221) ─────────────────────────────────

def test_check_cloud_timing_value_not_dict():
    with pytest.raises(ProfileError, match="must be a mapping of"):
        _check_cloud_timing("llm", "cloud", "not-a-dict", "<x>")  # -> 210

def test_check_cloud_timing_unknown_key():
    with pytest.raises(ProfileError, match="unknown cloud-timing key"):
        _check_cloud_timing("llm", "cloud", {"badkey": 5}, "<x>")  # -> 216

def test_check_cloud_timing_value_not_int():
    with pytest.raises(ProfileError, match="must be an int"):
        _check_cloud_timing("llm", "cloud", {"offline_timeout": "5"}, "<x>")  # str -> 221

def test_check_cloud_timing_bool_value_rejected():
    # bool is an int subclass; `type(True) is not int` is True -> also 221 (guard intent).
    with pytest.raises(ProfileError, match="must be an int"):
        _check_cloud_timing("llm", "cloud", {"retry_interval": True}, "<x>")

# ── _check_agent_select (lines 233-250) ───────────────────────────────────────

def test_check_agent_select_valid_list():
    # str-bundle path is covered by the shipped profiles; exercise the list path.
    _check_agent_select("agents", ["triage", "extraction"], "<x>")  # 237-238 loop, no raise

def test_check_agent_select_unknown_bundle():
    with pytest.raises(ProfileError, match="is not a known agent bundle"):
        _check_agent_select("agents", "nope-bundle", "<x>")  # 233-236

def test_check_agent_select_list_entry_not_string():
    with pytest.raises(ProfileError, match="agents list entries must be agent-name strings"):
        _check_agent_select("agents", ["triage", 123], "<x>")  # 239-243

def test_check_agent_select_unknown_agent_name():
    with pytest.raises(ProfileError, match="is not a registered agent"):
        _check_agent_select("agents", ["not_an_agent"], "<x>")  # 244-248

def test_check_agent_select_wrong_type():
    with pytest.raises(ProfileError, match="agents must be a bundle-name string or a list"):
        _check_agent_select("agents", 42, "<x>")  # else -> 249-253

# ── _check_block_select (lines 262-279) ───────────────────────────────────────

def test_check_block_select_valid_list():
    _check_block_select("blocks", ["persona", "honesty_policy"], "<x>")  # 266-267 loop, no raise

def test_check_block_select_unknown_bundle():
    with pytest.raises(ProfileError, match="is not a known block bundle"):
        _check_block_select("blocks", "nope-bundle", "<x>")  # 262-265

def test_check_block_select_list_entry_not_string():
    with pytest.raises(ProfileError, match="blocks list entries must be block-name strings"):
        _check_block_select("blocks", ["persona", 123], "<x>")  # 268-272

def test_check_block_select_unknown_block_name():
    with pytest.raises(ProfileError, match="is not a registered block"):
        _check_block_select("blocks", ["not_a_block"], "<x>")  # 273-277

def test_check_block_select_wrong_type():
    with pytest.raises(ProfileError, match="blocks must be a bundle-name string or a list"):
        _check_block_select("blocks", 42, "<x>")  # else -> 278-282
