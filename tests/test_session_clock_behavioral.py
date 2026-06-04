"""#5 Slice B — Layer-1 behavioral tests for the session/dispute clock fabric (real write/read clocks).

Same clock-arc lesson (P0.R3) as Slice A's tests/test_presence_clock_behavioral.py: the old tests
were GREEN while production was broken because they used time.time() on BOTH sides. These drive the
REAL Slice-B monotonic write path (update_voice_heard / update_face_seen / transition_to_disputed /
the _build_and_insert now_mono seed) and the REAL read (_expire_stale_sessions' monotonic staleness
checks), and they FAIL-ON-REVERT — a wall write read by the monotonic _expire clock mis-reads, which
is exactly the live bug Slice B fixes.

Covers the two CRITICAL §0.1.2 bugs + FACE_LOSS_GRACE + the #22 DRIFT-1 revival:
  • VOICE_SESSION_TIMEOUT (last_spoke_at via update_voice_heard)            — CRITICAL
  • DISPUTE_MAX_DURATION (dispute_set_at_monotonic via transition_to_disputed) — CRITICAL
  • FACE_LOSS_GRACE     (last_face_seen via update_face_seen + now_mono seed)
  • #22 voice-session extension revival (DRIFT-1: _now_ext flip)

Direction note: _expire reads `time.monotonic() - <field>`. A WALL-written field makes
monotonic_now (~small) − wall (~1.78e9) hugely NEGATIVE → the staleness/timeout comparison never
trips → a session that SHOULD expire LINGERS forever (the spec §0.1.2 prose says "times out
instantly", but on a host where time.monotonic() < time.time() the divergence manifests as
never-expires; either way the wall/mono split breaks the timeout and the migration fixes it).

Spec: tests/presence_fabric_clock_migration_spec.md §3.B / §6 Layer 1 / §0.1.2 / §0.1.3.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import time

import pytest

from core.config import (
    VOICE_SESSION_TIMEOUT,
    FACE_LOSS_GRACE,
    DISPUTE_MAX_DURATION,
    VOICE_ROUTING_FACE_STALE_SECS,
)


# ── VOICE_SESSION_TIMEOUT (last_spoke_at) — CRITICAL ──────────────────────────

@pytest.mark.asyncio
async def test_voice_session_timeout_consistent_under_monotonic_write():
    """A voice session whose last_spoke_at was written via the REAL update_voice_heard with a
    monotonic clock stays alive within VOICE_SESSION_TIMEOUT and expires once past it — because
    _expire_stale_sessions' monotonic read now matches the monotonic write (Slice B)."""
    import pipeline as _pl
    pid = "voice_to_consistent"
    await _pl._session_store.open_session(
        pid, "Vee", "stranger", "voice", now=time.time(), now_mono=time.monotonic())
    # Fresh monotonic spoke time → within window → not expired.
    await _pl._session_store.update_voice_heard(pid, conf=0.9, ts=time.monotonic())
    _pl._expire_stale_sessions()
    await _async_drain()
    assert _pl._session_store.peek_snapshot(pid) is not None, "fresh voice session must stay alive"
    # Backdated monotonic spoke time past the timeout → expired.
    await _pl._session_store.update_voice_heard(
        pid, conf=0.9, ts=time.monotonic() - VOICE_SESSION_TIMEOUT - 5.0)
    _pl._expire_stale_sessions()
    await _async_drain()
    assert _pl._session_store.peek_snapshot(pid) is None, (
        "a monotonic-written last_spoke_at older than VOICE_SESSION_TIMEOUT must expire the session"
    )


@pytest.mark.asyncio
async def test_voice_session_timeout_fails_on_wall_write_revert():
    """fail-on-revert: _expire reads time.monotonic(); if the update_voice_heard WRITE reverts to
    wall (the pre-#5 kwonly bug), a long-idle voice session reads PERMANENTLY fresh — monotonic now
    (~small) minus a wall timestamp (~1.78e9) is hugely negative → always < VOICE_SESSION_TIMEOUT →
    never expires. Pins that the Slice-B monotonic update_voice_heard write is load-bearing; if this
    assertion flips, the wall/mono divergence stopped mis-reading and the fix is doing nothing."""
    import pipeline as _pl
    pid = "voice_to_revert"
    await _pl._session_store.open_session(
        pid, "Vee", "stranger", "voice", now=time.time(), now_mono=time.monotonic())
    # WALL write (the reverted clock), backdated far past VOICE_SESSION_TIMEOUT.
    await _pl._session_store.update_voice_heard(
        pid, conf=0.9, ts=time.time() - VOICE_SESSION_TIMEOUT - 1000.0)
    _pl._expire_stale_sessions()
    await _async_drain()
    assert _pl._session_store.peek_snapshot(pid) is not None, (
        "pre-#5 bug reproduction: a WALL last_spoke_at write read by _expire's monotonic clock makes "
        "a long-idle voice session read fresh forever (mono - wall ≈ -1.78e9 < VOICE_SESSION_TIMEOUT). "
        "Slice B's monotonic update_voice_heard write fixes production (see consistent test)."
    )


# ── FACE_LOSS_GRACE (last_face_seen) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_face_loss_grace_consistent_under_monotonic_write():
    """A face session whose last_face_seen was seeded via the REAL _build_and_insert now_mono seed
    and refreshed via update_face_seen with a monotonic clock stays alive within FACE_LOSS_GRACE and
    expires once past it — the monotonic _expire read matches the monotonic write (Slice B)."""
    import pipeline as _pl
    pid = "face_consistent"
    await _pl._session_store.open_session(
        pid, "Jagan", "known", "face", now=time.time(), now_mono=time.monotonic())
    _pl._expire_stale_sessions()
    await _async_drain()
    assert _pl._session_store.peek_snapshot(pid) is not None, "fresh face session must stay alive"
    # Backdated monotonic face time past the grace → expired.
    await _pl._session_store.update_face_seen(
        pid, conf=0.9, ts=time.monotonic() - FACE_LOSS_GRACE - 5.0)
    _pl._expire_stale_sessions()
    await _async_drain()
    assert _pl._session_store.peek_snapshot(pid) is None, (
        "a monotonic-written last_face_seen older than FACE_LOSS_GRACE must expire the session"
    )


@pytest.mark.asyncio
async def test_face_loss_grace_fails_on_wall_write_revert():
    """fail-on-revert: a WALL last_face_seen write read by _expire's monotonic clock makes a
    long-gone face session read PERMANENTLY in-grace (mono - wall ≈ -1.78e9 < FACE_LOSS_GRACE) →
    never expires. Pins the Slice-B monotonic update_face_seen write is load-bearing."""
    import pipeline as _pl
    pid = "face_revert"
    await _pl._session_store.open_session(
        pid, "Jagan", "known", "face", now=time.time(), now_mono=time.monotonic())
    await _pl._session_store.update_face_seen(
        pid, conf=0.9, ts=time.time() - FACE_LOSS_GRACE - 1000.0)
    _pl._expire_stale_sessions()
    await _async_drain()
    assert _pl._session_store.peek_snapshot(pid) is not None, (
        "pre-#5 bug reproduction: a WALL last_face_seen write read by _expire's monotonic clock keeps "
        "a long-gone face session alive forever. Slice B's monotonic update_face_seen write fixes it."
    )


# ── DISPUTE_MAX_DURATION (dispute_set_at_monotonic) — CRITICAL ─────────────────

@pytest.mark.asyncio
async def test_dispute_max_duration_consistent_under_monotonic_companion():
    """A dispute whose dispute_set_at_monotonic companion was stamped via the REAL
    transition_to_disputed with a monotonic clock force-closes once past DISPUTE_MAX_DURATION (no
    voice/face auto-clear corroboration) — the monotonic _expire read matches the monotonic write."""
    import pipeline as _pl
    pid = "disp_consistent"
    await _pl._session_store.open_session(
        pid, "Jagan", "known", "face", now=time.time(), now_mono=time.monotonic())
    # Disputed with a monotonic companion already past DISPUTE_MAX_DURATION.
    await _pl._session_store.transition_to_disputed(
        pid, None, "test", now=time.time(),
        now_mono=time.monotonic() - DISPUTE_MAX_DURATION - 5.0)
    _pl._expire_stale_sessions()
    await _async_drain()
    assert _pl._session_store.peek_snapshot(pid) is None, (
        "a dispute older than DISPUTE_MAX_DURATION (monotonic companion) must force-close"
    )


@pytest.mark.asyncio
async def test_dispute_max_duration_fails_on_wall_companion_revert():
    """fail-on-revert: _expire reads the monotonic dispute companion; if that companion is stamped
    with a WALL clock (the pre-split bug where DISPUTE_MAX_DURATION read the wall dispute_set_at),
    monotonic now − wall ≈ -1.78e9 < DISPUTE_MAX_DURATION → the dispute never force-closes. Pins that
    the monotonic dispute_set_at_monotonic companion is load-bearing."""
    import pipeline as _pl
    pid = "disp_revert"
    await _pl._session_store.open_session(
        pid, "Jagan", "known", "face", now=time.time(), now_mono=time.monotonic())
    await _pl._session_store.transition_to_disputed(
        pid, None, "test", now=time.time(), now_mono=time.monotonic())
    # WALL companion, backdated far past DISPUTE_MAX_DURATION (the reverted clock). Non-None so the
    # Finding-K lazy-anchor does NOT re-stamp it.
    _wall_past = time.time() - DISPUTE_MAX_DURATION - 1000.0
    await _pl._session_store.set_dispute_set_at(pid, _wall_past, ts_monotonic=_wall_past)
    _pl._expire_stale_sessions()
    await _async_drain()
    assert _pl._session_store.peek_snapshot(pid) is not None, (
        "pre-split bug reproduction: a WALL dispute_set_at_monotonic read by _expire's monotonic "
        "clock never force-closes (mono - wall ≈ -1.78e9 < DISPUTE_MAX_DURATION). Slice B's monotonic "
        "companion fixes production (see consistent test)."
    )


# ── #22 voice-session extension revival (DRIFT-1: _now_ext flip) ──────────────

def _holder_visible_for_extension(presence_store, pid: str, now_ext: float) -> bool:
    """Replicates the #22 voice-session-extension visibility check (pipeline.py:~8606-8609):
    `pid in store and now_ext - peek_last_recognized_at(pid) < VOICE_ROUTING_FACE_STALE_SECS`.
    Reads the REAL PresenceStore getter, same as production."""
    return (
        pid in presence_store
        and now_ext - presence_store.peek_last_recognized_at(pid, 0.0) < VOICE_ROUTING_FACE_STALE_SECS
    )


@pytest.mark.asyncio
async def test_22_voice_session_extension_revived_under_monotonic_now_ext():
    """DRIFT-1 / #22: the voice-session extension fires when _now_ext is MONOTONIC (matching the
    monotonic-written PresenceStore.last_recognized_at). Pre-#5, _now_ext was wall → wall − mono ≈
    +1.78e9 ≥ VOICE_ROUTING_FACE_STALE_SECS → _holder_vis_ext was ALWAYS False → the #22 extension
    was dead code. Slice B's _now_ext→monotonic flip revives it AND makes the resulting
    set_last_spoke_at write monotonic. fail-on-revert: a wall _now_ext flips the assertion."""
    import pipeline as _pl
    pid = "ext_jagan"
    # REAL monotonic presence write (the Slice-A presence clock).
    await _pl._presence_store.upsert_face_recognition(pid, "Jagan", 0.9, time.monotonic())
    # Monotonic _now_ext (the Slice-B flip) → extension fires within the window.
    assert _holder_visible_for_extension(_pl._presence_store, pid, time.monotonic()) is True, (
        "#22 must fire: monotonic _now_ext against the monotonic-written last_recognized_at is "
        "within VOICE_ROUTING_FACE_STALE_SECS → voice session extends"
    )
    # fail-on-revert: WALL _now_ext (pre-#5) → wall − mono ≈ +1.78e9 ≥ FACE_STALE → never fires.
    assert _holder_visible_for_extension(_pl._presence_store, pid, time.time()) is False, (
        "DRIFT-1 reproduction: a WALL _now_ext against the monotonic-written last_recognized_at "
        "makes _holder_vis_ext always False → the #22 voice-session extension is dead code. "
        "Slice B's monotonic _now_ext flip revives it."
    )


async def _async_drain() -> None:
    """_expire_stale_sessions removes sessions synchronously via _sync_close_session (the pop is
    GIL-atomic), but fires _on_room_end via create_task. Yield once so any such task drains before
    the next assertion / test (mirrors the #129 room-end drain discipline)."""
    import asyncio
    await asyncio.sleep(0)
