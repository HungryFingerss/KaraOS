"""Follow-up #129 golden tests — room-end on simultaneous multi-expiry.

The close-side mirror of Canary #4 B1. Before C4, `pipeline._close_session` removed the
session via a fire-and-forget `create_task(close_session(pid))`; on simultaneous multi-expiry
(≥2 sessions cross their timeout in one `_expire_stale_sessions` poll) every pop is still
pending when the room-end gate runs, so the gate's `_remaining` is non-empty and **room-end
never fires** — `_active_room_session` is left orphaned (the next arrival joins the dead room +
`conversation_log.room_session_id` is contaminated). C4 makes the close pop SYNCHRONOUS via
`SessionStore._sync_close_session`, so the last expiry sees an empty remainder and fires room-end
exactly once.

§3 async-drain rule (auditor PI — LOAD-BEARING): only the session POP is synchronous after C4.
`_on_room_end` is still fired via `asyncio.create_task` at pipeline.py:2236 (room-end synthesis
is heavyweight 3B work that must never block the close path), and the line-2379 full-cleanup fires
`create_task(_presence_store.clear())` + `create_task(set_detected_lang("en"))` — also async. So
any assertion that reads an ASYNC-fired effect (the `_on_room_end` spy, the `set_detected_lang`
cleanup) needs `await asyncio.sleep(0)` after `_expire_stale_sessions()`; the sync
`peek_active_room_session() → None` read does NOT. These tests are `@pytest.mark.asyncio` on a
running loop — in a no-loop sync context the :2230+ guard logs without scheduling `_on_room_end`,
so the spy would read zero regardless of the fix (a vacuity-class false-pass).

These are SessionStore / pipeline-state behavioral tests (no core.voice / core.audio hardware), so
they are not vacuity-prone against the conftest stub and run on any box.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest


def _backdate_face_session(pl, pid: str) -> None:
    """Push a 'face' session's last_face_seen far past FACE_LOSS_GRACE so the next
    _expire_stale_sessions() poll expires it. #5 Slice B (§0.1.3): last_face_seen is now a
    MONOTONIC staleness clock — _expire_stale_sessions reads `time.monotonic() - last_face_seen
    > FACE_LOSS_GRACE` — so a MONOTONIC backdate is the correct lever (a wallclock backdate would
    make mono_now − wall ≈ -1.78e9 < FACE_LOSS_GRACE → never expires)."""
    pl._session_store._sessions[pid].last_face_seen = time.monotonic() - pl.FACE_LOSS_GRACE - 100.0


@pytest.mark.asyncio
async def test_gt0_multi_expiry_fires_room_end_once_and_clears(monkeypatch):
    """GT0 (load-bearing) — two sessions expiring in one pass fire room-end EXACTLY once,
    carry both participants, and clear the room.

    RED before C4: both pops are pending create_tasks, so the last close's `_remaining` still
    contains the other person → room-end never fires (spy.call_count == 0) and the room id stays
    set. GREEN after C4: sync pop → last close sees `_remaining == []` → room-end fires once."""
    import pipeline as _pl

    # Spy the async-fired room-end hook (isolates from the real RoomOrchestrator + DB).
    spy = AsyncMock()
    # P1.A1 SP-6.1: _on_room_end + _close_session both relocated to runtime.session;
    # _close_session calls _on_room_end intra-module → patch the runtime.session binding,
    # not the pipeline re-export (which the intra-module bare call never consults).
    monkeypatch.setattr("runtime.session._on_room_end", spy)

    # Open A + B into ONE room (second open inherits the first's minted room id).
    _pl._open_session("a_1", "Alice", "face", "known", engagement_gate_passed=True)
    _pl._open_session("b_1", "Bob", "face", "known", engagement_gate_passed=True)
    room_id = _pl._pipeline_state_store.peek_active_room_session()
    assert room_id is not None, "sanity: first _open_session must mint a room"
    assert _pl._pipeline_state_store.peek_active_room_participants() == {"a_1", "b_1"}, (
        "sanity: both opens must join the same room"
    )

    # Backdate BOTH so they expire in a single poll → the simultaneous-multi-expiry case.
    _backdate_face_session(_pl, "a_1")
    _backdate_face_session(_pl, "b_1")

    # The production locus (the bug lives in this synchronous close loop).
    _pl._expire_stale_sessions()
    await asyncio.sleep(0)  # drain the async _on_room_end create_task (Q3 #1/#2 reads)

    # Q3 — all three (a bug could fire-without-clearing or clear-without-firing):
    # 1. room-end fired exactly once (0 = the current bug; 2 = broken _sync_clear_room idempotency).
    assert spy.call_count == 1, f"expected room-end fired once, got {spy.call_count}"
    # 2. the spy call carried BOTH participants (guards a truncated _ended_participants read).
    parts = spy.call_args.args[1]
    assert set(parts) == {"a_1", "b_1"}, f"room-end must carry both participants, got {parts!r}"
    # 3. the room id is cleared (the orphaned-room consequence; sync via _sync_clear_room, no drain).
    assert _pl._pipeline_state_store.peek_active_room_session() is None, (
        "room id must be cleared once the last session closes"
    )


@pytest.mark.asyncio
async def test_gt1_single_expiry_fires_room_end_once(monkeypatch):
    """GT1 — single-expiry regression guard. The single path already worked (the gate excludes
    the one closing person), so this must stay GREEN before AND after C4: the fix must not break
    it."""
    import pipeline as _pl

    spy = AsyncMock()
    # P1.A1 SP-6.1: _on_room_end + _close_session both relocated to runtime.session;
    # _close_session calls _on_room_end intra-module → patch the runtime.session binding,
    # not the pipeline re-export (which the intra-module bare call never consults).
    monkeypatch.setattr("runtime.session._on_room_end", spy)

    _pl._open_session("solo_1", "Solo", "face", "known", engagement_gate_passed=True)
    assert _pl._pipeline_state_store.peek_active_room_session() is not None

    _backdate_face_session(_pl, "solo_1")
    _pl._expire_stale_sessions()
    await asyncio.sleep(0)

    assert spy.call_count == 1, f"single-expiry must fire room-end once, got {spy.call_count}"
    assert _pl._pipeline_state_store.peek_active_room_session() is None


@pytest.mark.asyncio
async def test_gt2_full_cleanup_fires_on_full_close(monkeypatch):
    """GT2 — the line-2379 full-cleanup (`if _expired and not peek_all_snapshots()`) fires when
    every session closes. Locks the secondary fix.

    RED before C4: the pops are pending so `peek_all_snapshots()` is non-empty at :2379 → cleanup
    is skipped → set_detected_lang('en') never runs. GREEN after C4: sync pops → store empty →
    cleanup fires. This read is async-fired (create_task), so the drain is required."""
    import pipeline as _pl

    monkeypatch.setattr("runtime.session._on_room_end", AsyncMock())  # isolate (SP-6.1: intra-module binding)
    set_lang_spy = AsyncMock()
    monkeypatch.setattr(_pl._pipeline_state_store, "set_detected_lang", set_lang_spy)

    _pl._open_session("a_1", "Alice", "face", "known", engagement_gate_passed=True)
    _pl._open_session("b_1", "Bob", "face", "known", engagement_gate_passed=True)

    _backdate_face_session(_pl, "a_1")
    _backdate_face_session(_pl, "b_1")

    _pl._expire_stale_sessions()
    await asyncio.sleep(0)  # drain the async full-cleanup create_task (set_detected_lang)

    assert any(c.args == ("en",) for c in set_lang_spy.call_args_list), (
        "line-2379 full-cleanup must fire set_detected_lang('en') once all sessions close"
    )
    assert _pl._session_store.peek_all_snapshots() == (), "store must be fully drained after close"
