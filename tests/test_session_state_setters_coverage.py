"""Covers the SessionStore setters left uncovered by the main suite:
set_last_face_seen + record_voice_spoke (P0.7 typed session state). Uses a
fresh standalone SessionStore instance. Part of the coverage-to-100 campaign."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from core.session_state import SessionStore


async def _open(store):
    await store.open_session("p1", "Alice", "known", "voice", now=100.0)


async def test_set_last_face_seen_updates_snapshot():
    store = SessionStore()
    await _open(store)
    await store.set_last_face_seen("p1", 55.0)
    assert store.peek_snapshot("p1").last_face_seen == 55.0


async def test_set_last_face_seen_noop_on_unknown_pid():
    store = SessionStore()
    await store.set_last_face_seen("ghost", 55.0)  # no session -> no-op
    assert store.peek_snapshot("ghost") is None


async def test_record_voice_spoke_updates_spoke_at_and_confidence():
    store = SessionStore()
    await _open(store)
    await store.record_voice_spoke("p1", ts=60.0, voice_confidence=0.9)
    snap = store.peek_snapshot("p1")
    assert snap.last_spoke_at == 60.0 and snap.voice_confidence == 0.9


async def test_record_voice_spoke_noop_on_unknown_pid():
    store = SessionStore()
    await store.record_voice_spoke("ghost", ts=1.0, voice_confidence=0.1)
    assert store.peek_snapshot("ghost") is None
