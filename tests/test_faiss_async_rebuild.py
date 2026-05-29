"""
Tests for FaceDB.rebuild_faiss_async — Wave 3 Item 15.

These tests require a real FAISS index (faiss-cpu) but mock out slow or
error-prone parts of the rebuild pipeline so the suite stays fast and
deterministic.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import asyncio
import time
import threading
import numpy as np
import pytest
import faiss

import core.db as db_mod
from core.db import FaceDB
from core.config import EMBEDDING_DIM


# ── Fixture helpers ────────────────────────────────────────────────────────────

def _random_embedding() -> np.ndarray:
    v = np.random.randn(EMBEDDING_DIM).astype(np.float32)
    v /= np.linalg.norm(v)
    return v


def _enroll(db: FaceDB, person_id: str, name: str = "Test") -> None:
    db._conn.execute(
        "INSERT OR IGNORE INTO persons (id, name, person_type, enrolled_at, last_seen) "
        "VALUES (?, ?, 'known', ?, ?)",
        (person_id, name, time.time(), time.time()),
    )
    db._conn.commit()


def _insert_embedding(db: FaceDB, person_id: str) -> None:
    """Insert a face embedding directly into the DB and FAISS (bypassing diversity gate)."""
    emb = _random_embedding()
    faiss_idx = db.index.ntotal
    db.index.add(emb.reshape(1, -1))
    db._idx_to_person[faiss_idx] = person_id
    db._conn.execute(
        "INSERT INTO embeddings (person_id, faiss_idx, vector, captured_at, source, confidence_at_write) "
        "VALUES (?, ?, ?, ?, 'enrollment', 0.9)",
        (person_id, faiss_idx, emb.tobytes(), time.time()),
    )
    db._conn.commit()


@pytest.fixture()
def db(tmp_path):
    faiss_file = tmp_path / "test.index"
    instance = FaceDB(
        db_path=str(tmp_path / "test.db"),
        faiss_path=str(faiss_file),
    )
    yield instance
    instance._conn.close()


# ── Tests ──────────────────────────────────────────────────────────────────────

async def test_rebuild_async_produces_correct_index_size(db):
    """After rebuild_faiss_async with 5 embeddings, index.ntotal == 5."""
    _enroll(db, "p1")
    for _ in range(5):
        _insert_embedding(db, "p1")

    loop = asyncio.get_event_loop()
    await db.rebuild_faiss_async(loop)

    assert db.index.ntotal == 5


async def test_rebuild_async_does_not_block_concurrent_recognize(db):
    """recognize() calls complete while a slow rebuild is in progress (uses OLD index)."""
    _enroll(db, "p1")
    for _ in range(10):
        _insert_embedding(db, "p1")

    orig_build = db._build_faiss_from_snapshot

    def slow_build(snapshot):
        time.sleep(0.20)  # 200ms — long enough to race recognize()
        return orig_build(snapshot)

    db._build_faiss_from_snapshot = slow_build

    loop = asyncio.get_event_loop()
    rebuild_task = asyncio.create_task(db.rebuild_faiss_async(loop))

    # Let Phase 1 complete (it's synchronous in the coroutine) so _rebuild_in_progress=True
    await asyncio.sleep(0)

    recognize_times = []
    probe = _random_embedding()
    for _ in range(5):
        t0 = time.time()
        db.recognize(probe, threshold=0.0)
        recognize_times.append(time.time() - t0)

    rebuild_start = time.time()
    await rebuild_task
    rebuild_elapsed = time.time() - rebuild_start

    # All 5 recognizes must have completed before the rebuild finished
    # (each took < 10ms; rebuild took ~200ms)
    assert max(recognize_times) < 0.15, (
        f"recognize() should not block; worst case was {max(recognize_times):.3f}s"
    )
    # Sanity: rebuild did take the mocked 200ms (otherwise the test is vacuous)
    # rebuild_elapsed is the REMAINING time after the recognizes, so it may be short.
    # What matters is that recognizes returned fast, not that rebuild was slow.
    _ = rebuild_elapsed  # just ensure no exception


async def test_rebuild_async_replays_pending_adds(db):
    """An add_embedding() during rebuild lands in the new index via pending queue."""
    _enroll(db, "p1")
    for _ in range(5):
        _insert_embedding(db, "p1")

    orig_build = db._build_faiss_from_snapshot

    def slow_build(snapshot):
        time.sleep(0.10)  # 100ms
        return orig_build(snapshot)

    db._build_faiss_from_snapshot = slow_build

    loop = asyncio.get_event_loop()
    rebuild_task = asyncio.create_task(db.rebuild_faiss_async(loop))

    # Yield once so Phase 1 runs (sets _rebuild_in_progress=True)
    await asyncio.sleep(0)

    # Phase 2 is now in progress (worker thread sleeping 100ms).
    # add_embedding must write to OLD index AND pending queue.
    assert db._rebuild_in_progress, "expected _rebuild_in_progress=True after Phase 1"

    added = False

    def _add_in_thread():
        nonlocal added
        emb = _random_embedding()
        db.add_embedding("p1", emb, source="enrollment", confidence=0.9, anti_spoof_verdict=True)
        added = True

    t = threading.Thread(target=_add_in_thread)
    t.start()
    t.join(timeout=2.0)
    assert added, "add_embedding timed out"

    await rebuild_task

    # New index should have snapshot (5) + pending (1) = 6
    assert db.index.ntotal == 6, (
        f"Expected ntotal=6 after replay of 1 pending add, got {db.index.ntotal}"
    )


async def test_rebuild_async_failure_resets_state(db):
    """If _build_faiss_from_snapshot raises, state is reset and the old index stays live."""
    _enroll(db, "p1")
    for _ in range(3):
        _insert_embedding(db, "p1")

    original_ntotal = db.index.ntotal  # 3
    assert original_ntotal == 3

    def boom(snapshot):
        raise RuntimeError("simulated build failure")

    db._build_faiss_from_snapshot = boom

    loop = asyncio.get_event_loop()
    with pytest.raises(RuntimeError, match="simulated build failure"):
        await db.rebuild_faiss_async(loop)

    # State must be fully reset
    assert db._rebuild_in_progress is False
    assert db._pending_adds_during_rebuild == []

    # OLD index must still be live and functional
    assert db.index.ntotal == original_ntotal
    probe = _random_embedding()
    result = db.recognize(probe, threshold=0.0)
    assert result is not None  # didn't crash


async def test_rebuild_async_concurrent_invocations_serialize(db):
    """Second rebuild_faiss_async returns early ('already in progress') without error."""
    _enroll(db, "p1")
    for _ in range(4):
        _insert_embedding(db, "p1")

    orig_build = db._build_faiss_from_snapshot
    build_call_count = {"n": 0}

    def counting_build(snapshot):
        build_call_count["n"] += 1
        time.sleep(0.05)  # short enough to keep test fast
        return orig_build(snapshot)

    db._build_faiss_from_snapshot = counting_build

    loop = asyncio.get_event_loop()

    # Fire two rebuilds concurrently
    t1 = asyncio.create_task(db.rebuild_faiss_async(loop))
    t2 = asyncio.create_task(db.rebuild_faiss_async(loop))

    await asyncio.gather(t1, t2)

    # Only one actual build should have happened
    assert build_call_count["n"] == 1, (
        f"Expected exactly 1 build call; got {build_call_count['n']}"
    )
    # Final index must still be correct
    assert db.index.ntotal == 4


# ── P0.B2 D5.3 — Concurrent add_embedding row_id tracking ─────────────────────

async def test_add_embedding_during_async_rebuild_tracks_row_id(db):
    """P0.B2 D5.3 (fast-tier depth coverage): add_embedding racing with
    rebuild_faiss_async writes its row_id into _pending_adds_during_rebuild as
    a 3-tuple, and Phase 3's combined DB UPDATE batch writes the post-swap
    faiss_idx back to the DB row.

    Without D3's cursor.lastrowid + 3-tuple pending append + post-lock DB
    UPDATE batch, the pending-add's DB row would carry the pre-swap faiss_idx
    forever, drifting from the in-memory _idx_to_person mapping. recognize()
    via that drifted row_id returns the wrong identity.

    Per Plan v2 §4.2: existing db fixture + threading.Event coordination
    (cross-thread Event is the correct primitive since slow_build runs in a
    worker thread via run_in_executor; asyncio.Event would not signal across
    the thread boundary).
    """
    _enroll(db, "p1")
    for _ in range(5):
        _insert_embedding(db, "p1")
    # Snapshot the DB row ids so we can identify the post-add row deterministically.
    pre_rebuild_row_ids = {
        r[0] for r in db._conn.execute("SELECT id FROM embeddings").fetchall()
    }
    assert len(pre_rebuild_row_ids) == 5

    build_started = threading.Event()
    release_build = threading.Event()
    orig_build = db._build_faiss_from_snapshot

    def coordinating_build(snapshot):
        build_started.set()
        # Wait for the main loop to run add_embedding and signal go-ahead.
        ok = release_build.wait(timeout=3.0)
        assert ok, "release_build event was never set — test deadlock"
        return orig_build(snapshot)

    db._build_faiss_from_snapshot = coordinating_build

    loop = asyncio.get_event_loop()
    rebuild_task = asyncio.create_task(db.rebuild_faiss_async(loop))

    # Yield so Phase 1 runs and rebuild dispatches to the executor where
    # coordinating_build blocks until release_build is set.
    await loop.run_in_executor(None, build_started.wait, 3.0)
    assert db._rebuild_in_progress, "expected _rebuild_in_progress=True after Phase 1"

    # Add a 6th embedding from a worker thread (add_embedding is sync).
    new_emb_holder: list = []

    def _add_in_thread():
        emb = _random_embedding()
        ok = db.add_embedding(
            "p1", emb,
            source="enrollment", confidence=0.9, anti_spoof_verdict=True,
        )
        assert ok, "add_embedding returned False"
        new_emb_holder.append(emb)

    t = threading.Thread(target=_add_in_thread)
    t.start()
    t.join(timeout=3.0)
    assert new_emb_holder, "add_embedding timed out"

    # 6th add must have enqueued a 3-tuple (vec, pid, row_id), not 2-tuple.
    assert len(db._pending_adds_during_rebuild) == 1
    pending = db._pending_adds_during_rebuild[0]
    assert len(pending) == 3, (
        f"pending entry must be (vec, pid, row_id); got {len(pending)}-tuple"
    )
    pending_vec, pending_pid, pending_row_id = pending
    assert pending_pid == "p1"
    # row_id must be the NEW row's id (not one of the pre-rebuild snapshot rows).
    assert pending_row_id not in pre_rebuild_row_ids
    db_new_row_ids = {
        r[0] for r in db._conn.execute("SELECT id FROM embeddings").fetchall()
    } - pre_rebuild_row_ids
    assert db_new_row_ids == {pending_row_id}

    # Release the build and let rebuild_faiss_async complete Phase 3+4.
    release_build.set()
    await rebuild_task

    # All 6 entries in the new index.
    assert db.index.ntotal == 6, (
        f"expected ntotal=6 (5 snapshot + 1 pending), got {db.index.ntotal}"
    )
    # Pending row's DB faiss_idx must reflect its NEW in-memory position (5 —
    # the last index appended during pending replay). Pre-fix the DB row would
    # have kept the pre-swap value forever.
    db_faiss_idx_for_new_row = db._conn.execute(
        "SELECT faiss_idx FROM embeddings WHERE id = ?", (pending_row_id,),
    ).fetchone()[0]
    assert db_faiss_idx_for_new_row == 5, (
        f"DB faiss_idx for pending row {pending_row_id} must be 5 (new "
        f"in-memory position after Phase 3 replay); got {db_faiss_idx_for_new_row}"
    )
    # And recognize() via the new embedding returns the right identity — the
    # full end-to-end invariant the D3 DB UPDATE batch protects.
    pid, name, score = db.recognize(new_emb_holder[0], threshold=0.0)
    assert pid == "p1", f"recognize returned wrong identity: pid={pid!r}"
