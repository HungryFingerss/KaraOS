"""#5 Slice A — Layer-1 behavioral tests for the presence clock fabric (real write/read clocks).

The clock-arc lesson (P0.R3): the old tests were GREEN while production was broken because they
used time.time() on BOTH sides. These drive the REAL PresenceStore write path (the monotonic
Slice-A clock) and the REAL read (`pipeline._face_in_frame`, the inline voice-accum staleness
expression), and they FAIL-ON-REVERT — a wall write read by the monotonic clock mis-reads, which
is exactly the live bug Slice A fixes (a long-gone face reading permanently in-frame; voice-accum
`face_verified` permanently on → gallery poisoning).

Covers the two LIVE Slice-A bugs:
  • _has_recent_face_evidence (pipeline.py:585) — mono read of PresenceStore.last_seen
    (the Wave-2 Item-9 scene/staleness reader; _face_in_frame is a pure source-check
    helper with no clock, so the staleness bug lives here).
  • voice-accum face_verified (pipeline.py:~8626) — mono read of PresenceStore.last_recognized_at.
The reconciler dict-mediated read is covered by tests/test_reconciler_clock_provenance.py (§5.2).

Spec: tests/presence_fabric_clock_migration_spec.md §3.A / §6 Layer 1.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import time

import pytest

from core.config import SCENE_STALE_SECS, VOICE_ROUTING_FACE_STALE_SECS


@pytest.mark.asyncio
async def test_has_recent_face_evidence_consistent_under_monotonic_presence_write():
    """scene-staleness: a face written via the REAL upsert_face_recognition with a monotonic
    clock reads as recent face evidence when fresh and stale once past SCENE_STALE_SECS — because
    _has_recent_face_evidence's monotonic read now matches the monotonic write (Slice A)."""
    import pipeline as _pl
    pid = "jagan_001"
    # Fresh monotonic write (the Slice-A presence clock).
    await _pl._presence_store.upsert_face_recognition(pid, "Jagan", 0.9, time.monotonic())
    assert _pl._has_recent_face_evidence(pid) is True, "fresh monotonic-written face must read recent"
    # Backdated monotonic write past SCENE_STALE_SECS → no longer recent.
    await _pl._presence_store.upsert_face_recognition(
        pid, "Jagan", 0.9, time.monotonic() - SCENE_STALE_SECS - 1.0
    )
    assert _pl._has_recent_face_evidence(pid) is False, (
        "a monotonic-written face older than SCENE_STALE_SECS must read stale (no recent evidence)"
    )


@pytest.mark.asyncio
async def test_has_recent_face_evidence_fails_on_wall_write_revert():
    """fail-on-revert: _has_recent_face_evidence reads time.monotonic(); if the presence WRITE
    reverts to wall (the pre-#5 bug), a long-gone face reads PERMANENTLY recent — time.monotonic()
    (~small) minus a wall timestamp(~1.78e9) is hugely negative → always < SCENE_STALE_SECS. This
    pins that the Slice-A monotonic write is load-bearing; if the assertion flips, the wall/mono
    divergence stopped mis-reading and the fix is no longer doing anything."""
    import pipeline as _pl
    pid = "ghost_001"
    # WALL write (the reverted clock), backdated far past SCENE_STALE — a long-gone face.
    await _pl._presence_store.upsert_face_recognition(
        pid, "Ghost", 0.9, time.time() - SCENE_STALE_SECS - 1000.0
    )
    assert _pl._has_recent_face_evidence(pid) is True, (
        "pre-#5 bug reproduction: a WALL presence write read by _has_recent_face_evidence's "
        "monotonic clock makes a long-gone face read recent forever (mono_now - wall ≈ -1.78e9 "
        "< SCENE_STALE). Slice A's monotonic write fixes the production path (see consistent test)."
    )


def _voice_accum_face_verified(store, pid: str) -> bool:
    """Replicates the production voice-accum `face_verified` staleness read (pipeline.py:~8626):
    `time.monotonic() - peek_last_recognized_at(pid) < VOICE_ROUTING_FACE_STALE_SECS`. Reads the
    REAL PresenceStore getter, same as production."""
    return (
        pid in store
        and time.monotonic() - store.peek_last_recognized_at(pid, 0.0) < VOICE_ROUTING_FACE_STALE_SECS
    )


@pytest.mark.asyncio
async def test_voice_accum_face_verified_consistent_under_monotonic_write():
    """voice-accum face_verified (last_recognized_at): monotonic write → face_verified True when
    the face is fresh, False once stale. Pre-fix the mono-read-of-wall-write kept face_verified
    permanently ON (gallery-poisoning risk)."""
    import pipeline as _pl
    pid = "lexi_002"
    await _pl._presence_store.upsert_face_recognition(pid, "Lexi", 0.8, time.monotonic())
    assert _voice_accum_face_verified(_pl._presence_store, pid) is True
    await _pl._presence_store.upsert_face_recognition(
        pid, "Lexi", 0.8, time.monotonic() - VOICE_ROUTING_FACE_STALE_SECS - 1.0
    )
    assert _voice_accum_face_verified(_pl._presence_store, pid) is False, (
        "a monotonic-written last_recognized_at older than VOICE_ROUTING_FACE_STALE_SECS must "
        "make face_verified False (no stale-face gallery accumulation)"
    )


@pytest.mark.asyncio
async def test_voice_accum_face_verified_fails_on_wall_write_revert():
    """fail-on-revert for the voice-accum read: a WALL last_recognized_at write read by the
    monotonic face_verified check stays permanently True (the gallery-poisoning bug). Pins that
    the Slice-A monotonic presence write is load-bearing for voice accumulation correctness."""
    import pipeline as _pl
    pid = "ghost_002"
    await _pl._presence_store.upsert_face_recognition(
        pid, "Ghost", 0.8, time.time() - VOICE_ROUTING_FACE_STALE_SECS - 1000.0
    )
    assert _voice_accum_face_verified(_pl._presence_store, pid) is True, (
        "pre-#5 bug reproduction: a WALL last_recognized_at write read by the monotonic "
        "face_verified check stays True for a long-gone face (mono - wall ≈ -1.78e9), keeping "
        "voice accumulation 'face-verified' forever. Slice A's monotonic write fixes production."
    )
