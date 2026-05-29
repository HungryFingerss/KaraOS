"""
Regression tests for Wave 6 Item 23 — scene_block string cache.

Source-inspection tests (not behavioural) — reads pipeline.py and config.py
as raw text to avoid the torchaudio DLL import crash on the Windows dev machine.

Four regression tests:
  1. test_cache_helpers_present
     _scene_fingerprint, _get_scene_block_cached, get_scene_block_cache_stats
     all exist in pipeline.py.

  2. test_call_sites_use_cached_wrapper
     Both _build_scene_block call sites (kairos + conversation_turn) have been
     replaced with _get_scene_block_cached — direct _build_scene_block( calls
     must only appear inside the function definitions themselves.

  3. test_module_state_vars_defined
     The three cache state variables (_scene_block_cache, _scene_block_cache_hits,
     _scene_block_cache_misses) are defined at module level.

  4. test_factory_reset_clears_cache
     The factory-reset "Clear all runtime state" block includes a
     _scene_block_cache.clear() call.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import pathlib
import re

# ---------------------------------------------------------------------------
# Read source files once — no import, no DLL issue.
# ---------------------------------------------------------------------------

_PIPELINE_PATH = pathlib.Path(__file__).parent.parent / "pipeline.py"
_CONFIG_PATH   = pathlib.Path(__file__).parent.parent / "core" / "config.py"

_PIPELINE_SRC  = _PIPELINE_PATH.read_text(encoding="utf-8")
_CONFIG_SRC    = _CONFIG_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 1: helper functions exist
# ---------------------------------------------------------------------------

def test_cache_helpers_present():
    """All three scene_block cache helpers must be defined in pipeline.py."""
    assert "def _scene_fingerprint(" in _PIPELINE_SRC, (
        "Wave 6 Item 23 regression: _scene_fingerprint not found in pipeline.py"
    )
    assert "def _get_scene_block_cached(" in _PIPELINE_SRC, (
        "Wave 6 Item 23 regression: _get_scene_block_cached not found in pipeline.py"
    )
    assert "def get_scene_block_cache_stats(" in _PIPELINE_SRC, (
        "Wave 6 Item 23 regression: get_scene_block_cache_stats not found in pipeline.py"
    )


# ---------------------------------------------------------------------------
# Test 2: call sites use the cached wrapper, not the raw builder
# ---------------------------------------------------------------------------

def test_call_sites_use_cached_wrapper():
    """Both production call sites must call _get_scene_block_cached, not _build_scene_block directly."""
    # Count direct _build_scene_block( occurrences outside its own def header
    # by looking at call-pattern lines (not 'def _build_scene_block').
    call_lines = [
        ln for ln in _PIPELINE_SRC.splitlines()
        if "_build_scene_block(" in ln and "def _build_scene_block(" not in ln
    ]
    # The only remaining occurrence must be the one inside _get_scene_block_cached
    # (and possibly _scene_fingerprint), i.e. the wrapper's own call.
    # Both former direct call sites must now use _get_scene_block_cached.
    wrapper_internal = [ln for ln in call_lines if "_get_scene_block_cached" not in ln]
    # wrapper_internal should have at most 1 entry: the call inside
    # _get_scene_block_cached itself (when SCENE_BLOCK_CACHE_ENABLED=False branch
    # and the normal miss branch both call _build_scene_block).
    # We accept ≤ 2 internal wrapper calls (disabled-path + miss-path).
    assert len(wrapper_internal) <= 2, (
        "Wave 6 Item 23 regression: found direct _build_scene_block( call sites "
        "outside the wrapper definition. They should use _get_scene_block_cached:\n"
        + "\n".join(wrapper_internal)
    )
    # Both KAIROS and conversation_turn sites must now call _get_scene_block_cached
    assert _PIPELINE_SRC.count("_get_scene_block_cached(") >= 2, (
        "Wave 6 Item 23 regression: expected at least 2 _get_scene_block_cached( "
        "call sites in pipeline.py (kairos + conversation_turn)"
    )


# ---------------------------------------------------------------------------
# Test 3: module-level state vars defined
# ---------------------------------------------------------------------------

def test_module_state_vars_defined():
    """The scene_block CacheStore must be declared at module level (P0.6.5)."""
    assert "_scene_block_store" in _PIPELINE_SRC, (
        "P0.6.5 regression: _scene_block_store not declared in pipeline.py"
    )
    # Config constants must be present
    assert "SCENE_BLOCK_CACHE_ENABLED" in _CONFIG_SRC, (
        "Wave 6 Item 23 regression: SCENE_BLOCK_CACHE_ENABLED missing from config.py"
    )
    assert "SCENE_BLOCK_CACHE_MAX_ENTRIES" in _CONFIG_SRC, (
        "Wave 6 Item 23 regression: SCENE_BLOCK_CACHE_MAX_ENTRIES missing from config.py"
    )


# ---------------------------------------------------------------------------
# Test 4: factory reset clears the cache
# ---------------------------------------------------------------------------

def test_factory_reset_clears_cache():
    """The factory-reset runtime-state clearing block must call _scene_block_cache.clear()."""
    # Find the factory-reset section by anchor text.
    # P0.6.6: _last_face_seen is now managed by _pipeline_state_store.reset()
    # so the old end-anchor pattern is gone. Use _pipeline_state_store.reset()
    # as the end anchor instead.
    reset_match = re.search(
        r"# Clear all runtime state.*?_pipeline_state_store\.reset\(\)",
        _PIPELINE_SRC,
        re.DOTALL,
    )
    assert reset_match is not None, (
        "Could not locate the factory-reset 'Clear all runtime state' block "
        "in pipeline.py — structure may have changed."
    )
    block = reset_match.group(0)
    assert "_scene_block_store.clear()" in block, (
        "P0.6.5 regression: factory-reset block does not call "
        "_scene_block_store.clear(). Scene block cache will accumulate stale "
        "entries after a factory reset."
    )
