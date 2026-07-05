"""Covers PipelineStateStore's room-lifecycle atomics (mint/add/end) + the
heavy-worker-status setter + the sync cloud-state init helper (P0.6.6). Part of
the coverage-to-100 campaign (see COVERAGE.md)."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from core.pipeline_state_store import PipelineStateStore

async def test_mint_room_sets_session_and_empty_participants():
    s = PipelineStateStore()
    await s.mint_room("room_1", 100.0)
    assert s.peek_active_room_session() == "room_1"
    assert s.peek_active_room_started_at() == 100.0
    assert s.peek_active_room_participants() == set()

async def test_add_room_participant():
    s = PipelineStateStore()
    await s.mint_room("room_1", 100.0)
    await s.add_room_participant("p1")
    await s.add_room_participant("p2")
    assert s.peek_active_room_participants() == {"p1", "p2"}

async def test_end_room_returns_state_and_clears():
    s = PipelineStateStore()
    await s.mint_room("room_1", 100.0)
    await s.add_room_participant("p1")
    sid, started, parts = await s.end_room()
    assert sid == "room_1" and started == 100.0 and parts == {"p1"}
    assert s.peek_active_room_session() is None
    assert s.peek_active_room_started_at() is None
    assert s.peek_active_room_participants() == set()

async def test_set_heavy_worker_status():
    s = PipelineStateStore()
    await s.set_heavy_worker_status("adaface_embed", "degraded")
    assert s.peek_heavy_worker_status()["adaface_embed"] == "degraded"

def test_sync_set_cloud_state():
    s = PipelineStateStore()
    s._sync_set_cloud_state("ONLINE_SENTINEL")
    assert s.peek_cloud_state() == "ONLINE_SENTINEL"
