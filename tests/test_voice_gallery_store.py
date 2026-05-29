"""Unit tests for core/voice_gallery_store.py — P0.6.4."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import asyncio
import inspect

import numpy as np
import pytest

from core.store_base import Store
from core.voice_gallery_store import VoiceGalleryStore


# ---------------------------------------------------------------------------
# ABC / inheritance / structure
# ---------------------------------------------------------------------------

class TestVoiceGalleryStoreInheritance:
    def test_inherits_from_store(self) -> None:
        assert issubclass(VoiceGalleryStore, Store)

    def test_instantiates_without_error(self) -> None:
        s = VoiceGalleryStore()
        assert s is not None

    def test_has_asyncio_lock(self) -> None:
        import asyncio
        s = VoiceGalleryStore()
        assert isinstance(s._lock, asyncio.Lock)

    def test_reset_is_sync(self) -> None:
        s = VoiceGalleryStore()
        assert not inspect.iscoroutinefunction(s.reset)

    def test_reset_clears_both_dicts(self) -> None:
        s = VoiceGalleryStore()
        emb = np.ones(192, dtype=np.float32)
        asyncio.run(s.set_gallery("p1", emb, 5))
        s.reset()
        assert s.peek_gallery("p1") is None
        assert s.peek_size("p1") == 0
        assert s.peek_len() == 0


# ---------------------------------------------------------------------------
# Atomicity invariant — set_gallery updates both dicts under one lock
# ---------------------------------------------------------------------------

class TestVoiceGalleryStoreAtomicity:
    def test_set_gallery_writes_both_dicts(self) -> None:
        s = VoiceGalleryStore()
        emb = np.ones(192, dtype=np.float32)
        asyncio.run(s.set_gallery("p1", emb, 7))
        assert s.peek_gallery("p1") is not None
        assert s.peek_size("p1") == 7

    def test_pop_gallery_removes_from_both_dicts(self) -> None:
        s = VoiceGalleryStore()
        emb = np.ones(192, dtype=np.float32)
        asyncio.run(s.set_gallery("p1", emb, 3))
        asyncio.run(s.pop_gallery("p1"))
        assert s.peek_gallery("p1") is None
        assert s.peek_size("p1") == 0

    def test_clear_empties_both_dicts(self) -> None:
        s = VoiceGalleryStore()
        emb = np.ones(192, dtype=np.float32)
        asyncio.run(s.set_gallery("p1", emb, 2))
        asyncio.run(s.set_gallery("p2", emb, 4))
        asyncio.run(s.clear())
        assert s.peek_len() == 0
        assert s.peek_all_gallery() == {}
        assert s.peek_all_sizes() == {}

    def test_pop_noop_on_missing_pid(self) -> None:
        s = VoiceGalleryStore()
        asyncio.run(s.pop_gallery("nonexistent"))  # must not raise


# ---------------------------------------------------------------------------
# load_bulk
# ---------------------------------------------------------------------------

class TestVoiceGalleryStoreBulkLoad:
    def test_load_bulk_populates_both_dicts(self) -> None:
        s = VoiceGalleryStore()
        emb1 = np.ones(192, dtype=np.float32)
        emb2 = np.zeros(192, dtype=np.float32)
        asyncio.run(s.load_bulk({"p1": emb1, "p2": emb2}, {"p1": 5, "p2": 3}))
        assert s.peek_size("p1") == 5
        assert s.peek_size("p2") == 3
        assert s.peek_len() == 2

    def test_load_bulk_is_additive(self) -> None:
        s = VoiceGalleryStore()
        emb = np.ones(192, dtype=np.float32)
        asyncio.run(s.set_gallery("p1", emb, 1))
        asyncio.run(s.load_bulk({"p2": emb}, {"p2": 2}))
        assert s.peek_len() == 2


# ---------------------------------------------------------------------------
# reconcile
# ---------------------------------------------------------------------------

class TestVoiceGalleryStoreReconcile:
    def test_reconcile_noop_when_sizes_match(self) -> None:
        s = VoiceGalleryStore()
        emb = np.ones(192, dtype=np.float32)
        asyncio.run(s.set_gallery("p1", emb, 5))
        count = asyncio.run(s.reconcile({"p1": 5}, lambda pid: emb))
        assert count == 0

    def test_reconcile_reloads_divergent_pid(self) -> None:
        s = VoiceGalleryStore()
        emb_old = np.ones(192, dtype=np.float32)
        emb_new = np.zeros(192, dtype=np.float32)
        asyncio.run(s.set_gallery("p1", emb_old, 3))
        count = asyncio.run(s.reconcile({"p1": 5}, lambda pid: emb_new))
        assert count == 1
        assert s.peek_size("p1") == 5

    def test_reconcile_removes_deleted_pid(self) -> None:
        s = VoiceGalleryStore()
        emb = np.ones(192, dtype=np.float32)
        asyncio.run(s.set_gallery("p1", emb, 5))
        # fresh_sizes has no p1 entry → load_profile_fn returns None → removed
        count = asyncio.run(s.reconcile({}, lambda pid: None))
        assert count == 1
        assert s.peek_gallery("p1") is None


# ---------------------------------------------------------------------------
# Peek methods
# ---------------------------------------------------------------------------

class TestVoiceGalleryStorePeeks:
    def test_peek_gallery_returns_none_for_missing(self) -> None:
        s = VoiceGalleryStore()
        assert s.peek_gallery("missing") is None

    def test_peek_size_returns_default_for_missing(self) -> None:
        s = VoiceGalleryStore()
        assert s.peek_size("missing") == 0
        assert s.peek_size("missing", default=99) == 99

    def test_peek_all_gallery_is_shallow_copy(self) -> None:
        s = VoiceGalleryStore()
        emb = np.ones(192, dtype=np.float32)
        asyncio.run(s.set_gallery("p1", emb, 3))
        copy = s.peek_all_gallery()
        copy["injected"] = emb
        assert "injected" not in s._voice_gallery

    def test_peek_all_sizes_is_shallow_copy(self) -> None:
        s = VoiceGalleryStore()
        emb = np.ones(192, dtype=np.float32)
        asyncio.run(s.set_gallery("p1", emb, 3))
        copy = s.peek_all_sizes()
        copy["injected"] = 99
        assert "injected" not in s._voice_gallery_sizes

    def test_peek_pids_returns_list(self) -> None:
        s = VoiceGalleryStore()
        emb = np.ones(192, dtype=np.float32)
        asyncio.run(s.set_gallery("p1", emb, 1))
        asyncio.run(s.set_gallery("p2", emb, 2))
        pids = s.peek_pids()
        assert set(pids) == {"p1", "p2"}
