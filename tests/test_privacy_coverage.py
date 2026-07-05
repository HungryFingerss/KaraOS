"""Covers core.brain_agent.privacy edge branches: the empty-attribute guard in
_is_safety_critical_attribute and the no-http-client fail-closed path in
_classify_privacy_level. Part of the coverage-to-100 campaign."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from core.brain_agent.privacy import (
    _is_safety_critical_attribute,
    _classify_privacy_level,
)
from core.config import PRIVACY_LEVEL_DEFAULT, PRIVACY_LEVEL_STATIC_MAP


def test_safety_critical_empty_attribute_is_false():
    assert _is_safety_critical_attribute("") is False
    assert _is_safety_critical_attribute(None) is False  # falsy -> line 44


def test_safety_critical_positive_match():
    assert _is_safety_critical_attribute("expressed_suicidal_thoughts") is True


async def test_classify_novel_attribute_without_http_fails_closed():
    # novel attr (not in static map / cache) + http None -> default_fallback
    lvl = await _classify_privacy_level(
        "Alice", "zz_novel_attr_for_coverage_9x7", "some value", http=None
    )
    assert lvl == PRIVACY_LEVEL_DEFAULT


async def test_classify_static_map_attribute_returns_mapped_tier():
    attr, expected = next(iter(PRIVACY_LEVEL_STATIC_MAP.items()))
    assert await _classify_privacy_level("Alice", attr, "v", http=None) == expected
