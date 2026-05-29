"""Unit tests for core/presence_store.py — P0.6.2."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import asyncio
import inspect

import pytest

from core.presence_store import PresenceEntry, PresenceSnapshot, PresenceStore
from core.store_base import Store


# ---------------------------------------------------------------------------
# ABC / inheritance
# ---------------------------------------------------------------------------

class TestPresenceStoreInheritance:
    def test_inherits_from_store(self) -> None:
        assert issubclass(PresenceStore, Store)

    def test_instantiates_without_error(self) -> None:
        s = PresenceStore()
        assert s is not None

    def test_has_asyncio_lock(self) -> None:
        import asyncio
        s = PresenceStore()
        assert isinstance(s._lock, asyncio.Lock)

    def test_reset_is_sync(self) -> None:
        s = PresenceStore()
        assert not inspect.iscoroutinefunction(s.reset)

    def test_reset_clears_state(self) -> None:
        s = PresenceStore()
        asyncio.run(s.upsert_face_recognition("p1", "Alice", 0.8, 100.0))
        s.reset()
        assert s.peek_count() == 0


# ---------------------------------------------------------------------------
# Face recognition mutations
# ---------------------------------------------------------------------------

class TestUpsertFaceRecognition:
    def test_inserts_new_entry(self) -> None:
        s = PresenceStore()
        asyncio.run(s.upsert_face_recognition("p1", "Alice", 0.85, 100.0))
        assert "p1" in s
        snap = s.peek_snapshot("p1")
        assert snap.name == "Alice"
        assert snap.conf == 0.85
        assert snap.source == "face"
        assert snap.last_seen == 100.0
        assert snap.last_recognized_at == 100.0

    def test_updates_existing_entry(self) -> None:
        s = PresenceStore()
        asyncio.run(s.upsert_face_recognition("p1", "Alice", 0.7, 100.0))
        asyncio.run(s.upsert_face_recognition("p1", "Alice2", 0.9, 200.0))
        snap = s.peek_snapshot("p1")
        assert snap.name == "Alice2"
        assert snap.conf == 0.9
        assert snap.last_seen == 200.0
        assert snap.last_recognized_at == 200.0

    def test_source_is_face(self) -> None:
        s = PresenceStore()
        asyncio.run(s.upsert_face_recognition("p1", "Alice", 0.8, 100.0))
        assert s.peek_source("p1") == "face"


# ---------------------------------------------------------------------------
# Voice recognition mutations
# ---------------------------------------------------------------------------

class TestUpsertVoiceRecognition:
    def test_inserts_new_voice_entry(self) -> None:
        s = PresenceStore()
        asyncio.run(s.upsert_voice_recognition("p1", "Bob", 0.6, 100.0))
        snap = s.peek_snapshot("p1")
        assert snap.source == "voice"
        assert snap.last_recognized_at == 0.0  # not set for voice

    def test_updates_existing_with_voice(self) -> None:
        s = PresenceStore()
        asyncio.run(s.upsert_face_recognition("p1", "Bob", 0.8, 50.0))
        asyncio.run(s.upsert_voice_recognition("p1", "Bob", 0.65, 100.0))
        snap = s.peek_snapshot("p1")
        assert snap.source == "voice"
        assert snap.last_seen == 100.0
        # last_recognized_at preserved from face upsert
        assert snap.last_recognized_at == 50.0


# ---------------------------------------------------------------------------
# Other mutations
# ---------------------------------------------------------------------------

class TestOtherMutations:
    def test_touch_last_seen(self) -> None:
        s = PresenceStore()
        asyncio.run(s.upsert_face_recognition("p1", "Alice", 0.8, 100.0))
        asyncio.run(s.touch_last_seen("p1", 200.0))
        assert s.peek_last_seen("p1") == 200.0

    def test_touch_last_seen_noop_on_missing(self) -> None:
        s = PresenceStore()
        asyncio.run(s.touch_last_seen("unknown", 200.0))  # should not raise

    def test_update_name(self) -> None:
        s = PresenceStore()
        asyncio.run(s.upsert_face_recognition("p1", "Old", 0.8, 100.0))
        asyncio.run(s.update_name("p1", "New"))
        assert s.peek_name("p1") == "New"

    def test_remove(self) -> None:
        s = PresenceStore()
        asyncio.run(s.upsert_face_recognition("p1", "Alice", 0.8, 100.0))
        asyncio.run(s.remove("p1"))
        assert "p1" not in s

    def test_remove_missing_noop(self) -> None:
        s = PresenceStore()
        asyncio.run(s.remove("nonexistent"))  # should not raise


# ---------------------------------------------------------------------------
# Prune methods
# ---------------------------------------------------------------------------

class TestPruneMethods:
    def test_prune_stale_removes_old_entries(self) -> None:
        s = PresenceStore()
        asyncio.run(s.upsert_face_recognition("p1", "A", 0.8, 50.0))
        asyncio.run(s.upsert_face_recognition("p2", "B", 0.8, 150.0))
        pruned = asyncio.run(s.prune_stale(100.0))  # before_ts=100
        assert "p1" in pruned
        assert "p2" not in pruned
        assert "p1" not in s
        assert "p2" in s

    def test_prune_stale_returns_empty_when_nothing_stale(self) -> None:
        s = PresenceStore()
        asyncio.run(s.upsert_face_recognition("p1", "A", 0.8, 200.0))
        pruned = asyncio.run(s.prune_stale(100.0))
        assert pruned == []

    def test_clear_removes_all(self) -> None:
        s = PresenceStore()
        asyncio.run(s.upsert_face_recognition("p1", "A", 0.8, 100.0))
        asyncio.run(s.upsert_face_recognition("p2", "B", 0.8, 100.0))
        asyncio.run(s.clear())
        assert s.peek_count() == 0


# ---------------------------------------------------------------------------
# Peek methods
# ---------------------------------------------------------------------------

class TestPeekMethods:
    def test_peek_snapshot_returns_none_for_missing(self) -> None:
        s = PresenceStore()
        assert s.peek_snapshot("unknown") is None

    def test_peek_all_snapshots(self) -> None:
        s = PresenceStore()
        asyncio.run(s.upsert_face_recognition("p1", "Alice", 0.8, 100.0))
        asyncio.run(s.upsert_face_recognition("p2", "Bob", 0.7, 200.0))
        snaps = s.peek_all_snapshots()
        pids = {snap.person_id for snap in snaps}
        assert pids == {"p1", "p2"}

    def test_peek_pids(self) -> None:
        s = PresenceStore()
        asyncio.run(s.upsert_face_recognition("p1", "A", 0.8, 100.0))
        asyncio.run(s.upsert_face_recognition("p2", "B", 0.7, 100.0))
        assert set(s.peek_pids()) == {"p1", "p2"}

    def test_peek_defaults_on_missing(self) -> None:
        s = PresenceStore()
        assert s.peek_name("x", "default") == "default"
        assert s.peek_conf("x", 0.0) == 0.0
        assert s.peek_last_seen("x", 0.0) == 0.0
        assert s.peek_last_recognized_at("x", 0.0) == 0.0
        assert s.peek_source("x", "none") == "none"

    def test_snapshot_is_immutable(self) -> None:
        s = PresenceStore()
        asyncio.run(s.upsert_face_recognition("p1", "Alice", 0.8, 100.0))
        snap = s.peek_snapshot("p1")
        with pytest.raises((AttributeError, TypeError)):
            snap.name = "Mutated"  # type: ignore[misc]

    def test_contains_true_and_false(self) -> None:
        s = PresenceStore()
        asyncio.run(s.upsert_face_recognition("p1", "Alice", 0.8, 100.0))
        assert "p1" in s
        assert "p2" not in s

    def test_peek_count(self) -> None:
        s = PresenceStore()
        assert s.peek_count() == 0
        asyncio.run(s.upsert_face_recognition("p1", "A", 0.8, 100.0))
        assert s.peek_count() == 1


# ---------------------------------------------------------------------------
# Lock isolation
# ---------------------------------------------------------------------------

class TestLockIsolation:
    def test_two_instances_have_independent_locks(self) -> None:
        s1 = PresenceStore()
        s2 = PresenceStore()
        assert s1._lock is not s2._lock

    def test_two_instances_have_independent_state(self) -> None:
        s1 = PresenceStore()
        s2 = PresenceStore()
        asyncio.run(s1.upsert_face_recognition("p1", "Alice", 0.8, 100.0))
        assert "p1" not in s2
