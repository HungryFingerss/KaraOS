"""Unit tests for core/track_store.py — P0.6.2."""
from __future__ import annotations

import asyncio
import inspect

import pytest

from core.track_store import TrackEntry, TrackSnapshot, TrackStore
from core.store_base import Store


# ---------------------------------------------------------------------------
# ABC / inheritance
# ---------------------------------------------------------------------------

class TestTrackStoreInheritance:
    def test_inherits_from_store(self) -> None:
        assert issubclass(TrackStore, Store)

    def test_instantiates_without_error(self) -> None:
        s = TrackStore()
        assert s is not None

    def test_has_asyncio_lock(self) -> None:
        import asyncio
        s = TrackStore()
        assert isinstance(s._lock, asyncio.Lock)

    def test_reset_is_sync(self) -> None:
        s = TrackStore()
        assert not inspect.iscoroutinefunction(s.reset)

    def test_reset_clears_state(self) -> None:
        s = TrackStore()
        asyncio.run(s.mark_unrecognized(42, 100.0))
        s.reset()
        assert s.peek_count() == 0


# ---------------------------------------------------------------------------
# Individual mutation methods
# ---------------------------------------------------------------------------

class TestMarkUnrecognized:
    def test_creates_entry_with_last_seen(self) -> None:
        s = TrackStore()
        asyncio.run(s.mark_unrecognized(42, 100.0))
        assert 42 in s
        assert s.peek_last_seen(42) == 100.0

    def test_updates_existing_last_seen(self) -> None:
        s = TrackStore()
        asyncio.run(s.mark_unrecognized(42, 100.0))
        asyncio.run(s.mark_unrecognized(42, 200.0))
        assert s.peek_last_seen(42) == 200.0


class TestSetEmbedding:
    def test_sets_embedding_on_existing_entry(self) -> None:
        s = TrackStore()
        asyncio.run(s.mark_unrecognized(1, 100.0))
        asyncio.run(s.set_embedding(1, b"fake_emb"))
        assert s.peek_embedding(1) == b"fake_emb"

    def test_creates_entry_if_needed(self) -> None:
        s = TrackStore()
        asyncio.run(s.set_embedding(99, b"emb"))
        assert 99 in s
        assert s.peek_embedding(99) == b"emb"


class TestMintStranger:
    def test_sets_stranger_pid(self) -> None:
        s = TrackStore()
        asyncio.run(s.mint_stranger(10, "stranger_abc"))
        assert s.peek_stranger_pid(10) == "stranger_abc"

    def test_creates_entry_if_needed(self) -> None:
        s = TrackStore()
        asyncio.run(s.mint_stranger(10, "stranger_xyz"))
        assert 10 in s


class TestBindIdentity:
    def test_sets_identity_pid(self) -> None:
        s = TrackStore()
        asyncio.run(s.bind_identity(5, "person_001"))
        assert s.peek_identity(5) == "person_001"

    def test_creates_entry_if_needed(self) -> None:
        s = TrackStore()
        asyncio.run(s.bind_identity(5, "person_001"))
        assert 5 in s


class TestRemoveTrack:
    def test_removes_existing(self) -> None:
        s = TrackStore()
        asyncio.run(s.mark_unrecognized(7, 100.0))
        asyncio.run(s.remove_track(7))
        assert 7 not in s

    def test_noop_on_missing(self) -> None:
        s = TrackStore()
        asyncio.run(s.remove_track(999))  # no raise


# ---------------------------------------------------------------------------
# Prune methods
# ---------------------------------------------------------------------------

class TestPruneMethods:
    def test_prune_stale_removes_old_tracks(self) -> None:
        s = TrackStore()
        asyncio.run(s.mark_unrecognized(1, 50.0))
        asyncio.run(s.mark_unrecognized(2, 150.0))
        pruned = asyncio.run(s.prune_stale(100.0))  # before_ts = 100
        assert 1 in pruned
        assert 2 not in pruned
        assert 1 not in s
        assert 2 in s

    def test_prune_stale_skips_zero_last_seen(self) -> None:
        """Tracks with last_seen=0 (e.g. identity-only entries) are not pruned."""
        s = TrackStore()
        asyncio.run(s.bind_identity(3, "person_1"))  # last_seen stays 0
        pruned = asyncio.run(s.prune_stale(100.0))
        assert 3 not in pruned
        assert 3 in s

    def test_prune_to_active_tids(self) -> None:
        s = TrackStore()
        asyncio.run(s.mark_unrecognized(1, 100.0))
        asyncio.run(s.mark_unrecognized(2, 100.0))
        asyncio.run(s.mark_unrecognized(3, 100.0))
        pruned = asyncio.run(s.prune_to_active_tids({1, 3}))
        assert 2 in pruned
        assert 1 in s
        assert 3 in s
        assert 2 not in s

    def test_prune_for_session_close(self) -> None:
        s = TrackStore()
        asyncio.run(s.mint_stranger(10, "stranger_abc"))
        asyncio.run(s.mint_stranger(11, "stranger_xyz"))
        asyncio.run(s.mark_unrecognized(12, 100.0))
        pruned = asyncio.run(s.prune_for_session_close("stranger_abc"))
        assert 10 in pruned
        assert 11 not in pruned  # different stranger_pid
        assert 10 not in s
        assert 11 in s
        assert 12 in s

    def test_clear_removes_all(self) -> None:
        s = TrackStore()
        asyncio.run(s.mark_unrecognized(1, 100.0))
        asyncio.run(s.mark_unrecognized(2, 100.0))
        asyncio.run(s.clear())
        assert s.peek_count() == 0


# ---------------------------------------------------------------------------
# Peek methods
# ---------------------------------------------------------------------------

class TestPeekMethods:
    def test_peek_snapshot_returns_none_for_missing(self) -> None:
        s = TrackStore()
        assert s.peek_snapshot(999) is None

    def test_peek_snapshot_returns_full_data(self) -> None:
        s = TrackStore()
        asyncio.run(s.mark_unrecognized(5, 100.0))
        asyncio.run(s.set_embedding(5, b"emb"))
        asyncio.run(s.mint_stranger(5, "stranger_1"))
        asyncio.run(s.bind_identity(5, "person_x"))
        snap = s.peek_snapshot(5)
        assert snap.track_id == 5
        assert snap.last_seen == 100.0
        assert snap.embedding == b"emb"
        assert snap.stranger_pid == "stranger_1"
        assert snap.identity_pid == "person_x"

    def test_peek_snapshot_is_immutable(self) -> None:
        s = TrackStore()
        asyncio.run(s.mark_unrecognized(1, 100.0))
        snap = s.peek_snapshot(1)
        with pytest.raises((AttributeError, TypeError)):
            snap.last_seen = 999.0  # type: ignore[misc]

    def test_peek_all_track_ids(self) -> None:
        s = TrackStore()
        asyncio.run(s.mark_unrecognized(1, 100.0))
        asyncio.run(s.mark_unrecognized(2, 100.0))
        assert set(s.peek_all_track_ids()) == {1, 2}

    def test_peek_all_snapshots(self) -> None:
        s = TrackStore()
        asyncio.run(s.mark_unrecognized(1, 100.0))
        asyncio.run(s.mark_unrecognized(2, 200.0))
        snaps = s.peek_all_snapshots()
        tids = {snap.track_id for snap in snaps}
        assert tids == {1, 2}

    def test_peek_defaults_on_missing(self) -> None:
        s = TrackStore()
        assert s.peek_stranger_pid(99) is None
        assert s.peek_identity(99) is None
        assert s.peek_embedding(99) is None
        assert s.peek_last_seen(99, 0.0) == 0.0

    def test_peek_tracks_for_person(self) -> None:
        s = TrackStore()
        asyncio.run(s.bind_identity(1, "person_a"))
        asyncio.run(s.bind_identity(2, "person_b"))
        asyncio.run(s.bind_identity(3, "person_a"))
        tracks = s.peek_tracks_for_person("person_a")
        assert set(tracks) == {1, 3}

    def test_peek_track_for_stranger_pid(self) -> None:
        s = TrackStore()
        asyncio.run(s.mint_stranger(10, "stranger_xyz"))
        result = s.peek_track_for_stranger_pid("stranger_xyz")
        assert result == 10

    def test_peek_track_for_stranger_pid_returns_none_on_missing(self) -> None:
        s = TrackStore()
        assert s.peek_track_for_stranger_pid("nonexistent") is None

    def test_peek_active_unrecognized(self) -> None:
        s = TrackStore()
        asyncio.run(s.mark_unrecognized(1, 100.0))
        asyncio.run(s.bind_identity(2, "person"))  # last_seen=0, not unrecognized
        active = s.peek_active_unrecognized()
        assert 1 in active
        assert 2 not in active

    def test_contains_true_and_false(self) -> None:
        s = TrackStore()
        asyncio.run(s.mark_unrecognized(42, 100.0))
        assert 42 in s
        assert 99 not in s

    def test_peek_count(self) -> None:
        s = TrackStore()
        assert s.peek_count() == 0
        asyncio.run(s.mark_unrecognized(1, 100.0))
        assert s.peek_count() == 1


# ---------------------------------------------------------------------------
# Lock isolation
# ---------------------------------------------------------------------------

class TestLockIsolation:
    def test_two_instances_have_independent_locks(self) -> None:
        s1 = TrackStore()
        s2 = TrackStore()
        assert s1._lock is not s2._lock

    def test_two_instances_have_independent_state(self) -> None:
        s1 = TrackStore()
        s2 = TrackStore()
        asyncio.run(s1.mark_unrecognized(1, 100.0))
        assert 1 not in s2
