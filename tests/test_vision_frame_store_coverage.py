"""100% coverage for core.vision_frame_store — VisionFrameStore (P0.6.7v2).
Behavioral companion to the AST producer-copy test. Part of the
coverage-to-100 campaign (see COVERAGE.md)."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from core.vision_frame_store import VisionFrameStore

def test_defaults_after_construction():
    s = VisionFrameStore()
    assert s.peek_frame() is None
    assert s.peek_frame_time() == 0.0
    assert s.peek_prev_det_count() == 0

async def test_set_and_peek_frame():
    s = VisionFrameStore()
    await s.set_frame("FRAME", 12.5)
    assert s.peek_frame() == "FRAME" and s.peek_frame_time() == 12.5

async def test_clear_frame_resets_frame_and_time():
    s = VisionFrameStore()
    await s.set_frame("FRAME", 12.5)
    await s.clear_frame()
    assert s.peek_frame() is None and s.peek_frame_time() == 0.0

async def test_set_prev_det_count_async():
    s = VisionFrameStore()
    await s.set_prev_det_count(4)
    assert s.peek_prev_det_count() == 4

def test_sync_set_prev_det_count():
    s = VisionFrameStore()
    s._sync_set_prev_det_count(7)
    assert s.peek_prev_det_count() == 7

async def test_peek_frame_if_fresh_returns_frame_when_young():
    s = VisionFrameStore()
    await s.set_frame("FRESH", 100.0)
    assert s.peek_frame_if_fresh(max_age_secs=5.0, now=102.0) == "FRESH"

async def test_peek_frame_if_fresh_returns_none_when_stale():
    s = VisionFrameStore()
    await s.set_frame("OLD", 100.0)
    assert s.peek_frame_if_fresh(max_age_secs=5.0, now=200.0) is None

async def test_reset_clears_all_fields():
    s = VisionFrameStore()
    await s.set_frame("X", 9.0)
    await s.set_prev_det_count(3)
    s.reset()
    assert s.peek_frame() is None and s.peek_frame_time() == 0.0
    assert s.peek_prev_det_count() == 0
