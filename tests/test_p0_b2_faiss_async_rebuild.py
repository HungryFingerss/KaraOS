"""
P0.B2 D1+D2+D3+D4 logical anchors — async FAISS rebuild correctness invariants.

7 anchors covering the unit + source-inspection surfaces:
  - D1 (1): _fetch_all_embeddings_for_index returns 3-tuple with row_ids
  - D2 (1): _build_faiss_from_snapshot returns 3-tuple with snapshot_idx_updates
  - D3 (3): add_embedding 3-tuple pending append + Phase 3 combines snapshot+pending
            row_ids + DB UPDATE batch runs AFTER _index_lock release
  - D4 (2): _mark_faiss_dirty runs BEFORE Phase 3 swap (+ ORDERING INVARIANT
            comment present) + _clear_faiss_dirty runs AFTER Phase 4 _save_faiss

Behavioral D5 tests live in tests/test_faiss_async_rebuild.py (fast-tier Test 3)
and tests/test_faiss_sql_atomicity.py (slow-tier Tests 1+2).

Plan v3 §1 locked 10 logical anchors total. This file owns 7 (D1+D2+D3+D4).
"""
import ast
import inspect
import textwrap
import time

import numpy as np
import pytest
import faiss

from core.db import FaceDB
from core.config import EMBEDDING_DIM


# ── Fixture helpers (mirrors tests/test_faiss_async_rebuild.py) ───────────────

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


def _insert_embedding_direct(db: FaceDB, person_id: str) -> tuple[np.ndarray, int]:
    """Insert directly via DB+FAISS, returning the embedding and DB row id."""
    emb = _random_embedding()
    faiss_idx = db.index.ntotal
    db.index.add(emb.reshape(1, -1))
    db._idx_to_person[faiss_idx] = person_id
    cur = db._conn.execute(
        "INSERT INTO embeddings (person_id, faiss_idx, vector, captured_at, source, confidence_at_write) "
        "VALUES (?, ?, ?, ?, 'enrollment', 0.9)",
        (person_id, faiss_idx, emb.tobytes(), time.time()),
    )
    db._conn.commit()
    return emb, int(cur.lastrowid)


@pytest.fixture()
def db(tmp_path):
    faiss_file = tmp_path / "test.index"
    instance = FaceDB(
        db_path=str(tmp_path / "test.db"),
        faiss_path=str(faiss_file),
    )
    yield instance
    instance._conn.close()


# ── D1 — _fetch_all_embeddings_for_index returns 3-tuple ──────────────────────

def test_d1_fetch_all_embeddings_returns_3_tuple_with_row_ids(db):
    """D1 anchor: snapshot SELECT widens to (vecs, person_ids, row_ids).

    Pre-P0.B2 returned 2-tuple (vecs, person_ids); the async rebuild had no way
    to update the DB's faiss_idx column after the in-memory swap. row_ids gives
    Phase 3 the key it needs to write back.
    """
    _enroll(db, "p1")
    _enroll(db, "p2")
    emb_a, row_id_a = _insert_embedding_direct(db, "p1")
    emb_b, row_id_b = _insert_embedding_direct(db, "p1")
    emb_c, row_id_c = _insert_embedding_direct(db, "p2")

    result = db._fetch_all_embeddings_for_index()
    assert isinstance(result, tuple) and len(result) == 3, (
        f"expected 3-tuple, got {type(result).__name__} of length {len(result)}"
    )
    vecs, person_ids, row_ids = result
    assert isinstance(vecs, np.ndarray)
    assert vecs.shape == (3, EMBEDDING_DIM)
    assert person_ids == ["p1", "p1", "p2"]
    assert row_ids == [row_id_a, row_id_b, row_id_c]
    # Empty case: fresh db with no embeddings still returns 3-tuple shape.
    db._conn.execute("DELETE FROM embeddings")
    db._conn.commit()
    empty_vecs, empty_pids, empty_rids = db._fetch_all_embeddings_for_index()
    assert empty_vecs.shape == (0, EMBEDDING_DIM)
    assert empty_pids == []
    assert empty_rids == []


# ── D2 — _build_faiss_from_snapshot returns 3-tuple with snapshot_idx_updates ─

def test_d2_build_faiss_from_snapshot_returns_3_tuple_with_idx_updates(db):
    """D2 anchor: pure helper returns (new_index, new_idx_to_person, snapshot_idx_updates).

    snapshot_idx_updates is list[tuple[int, int]] of (new_idx, row_id) pairs
    parallel to the sync `_rebuild_faiss` idx_updates. Phase 3 of the async
    rebuild extends this list with pending-replay rows then writes the full
    batch to the DB.
    """
    _enroll(db, "p1")
    _enroll(db, "p2")
    emb_a, row_id_a = _insert_embedding_direct(db, "p1")
    emb_b, row_id_b = _insert_embedding_direct(db, "p2")
    emb_c, row_id_c = _insert_embedding_direct(db, "p2")

    snapshot = db._fetch_all_embeddings_for_index()
    out = db._build_faiss_from_snapshot(snapshot)
    assert isinstance(out, tuple) and len(out) == 3, (
        f"expected 3-tuple, got {type(out).__name__} of length {len(out)}"
    )
    new_index, new_idx_to_person, snapshot_idx_updates = out
    assert isinstance(new_index, faiss.IndexFlatIP)
    assert new_index.ntotal == 3
    assert new_idx_to_person == {0: "p1", 1: "p2", 2: "p2"}
    assert snapshot_idx_updates == [(0, row_id_a), (1, row_id_b), (2, row_id_c)]


# ── D3.1 — add_embedding captures cursor.lastrowid into 3-tuple ───────────────

def test_d3_add_embedding_appends_3_tuple_with_row_id_during_rebuild(db):
    """D3 anchor (1/3): pending-add tuple is (vec, person_id, row_id).

    `add_embedding` uses the explicit-cursor pattern (Plan v2 §4.1) to capture
    `cur.lastrowid` after the INSERT inside the transaction. When
    `_rebuild_in_progress` is True, the pending list appends 3-tuples so Phase 3
    can write back the new faiss_idx for every pending add too.
    """
    _enroll(db, "p1")
    # Open the rebuild window without actually running the rebuild.
    db._rebuild_in_progress = True
    db._pending_adds_during_rebuild = []

    emb = _random_embedding()
    ok = db.add_embedding(
        person_id="p1",
        embedding=emb,
        source="enrollment",
        anti_spoof_verdict=True,
    )
    assert ok is True
    assert len(db._pending_adds_during_rebuild) == 1
    entry = db._pending_adds_during_rebuild[0]
    assert isinstance(entry, tuple) and len(entry) == 3, (
        f"expected 3-tuple (vec, pid, row_id), got len={len(entry)}"
    )
    vec, pid, row_id = entry
    assert isinstance(vec, np.ndarray) and vec.shape == (EMBEDDING_DIM,)
    assert pid == "p1"
    # row_id must be the actual DB row id assigned by SQLite — the explicit
    # cursor lets us cross-check.
    db_row_id = db._conn.execute(
        "SELECT id FROM embeddings WHERE person_id = ? ORDER BY id DESC LIMIT 1",
        (pid,),
    ).fetchone()[0]
    assert row_id == db_row_id, (
        f"pending row_id {row_id} does not match DB row id {db_row_id}"
    )


# ── D3.2 — Phase 3 combines snapshot_idx_updates + pending_idx_updates ────────

def test_d3_rebuild_async_phase3_combines_snapshot_and_pending_idx_updates():
    """D3 anchor (2/3): Phase 3 builds combined idx_updates from both sources.

    Source-inspection — the combined batch is what makes the async path's DB
    write match the sync `_rebuild_faiss` precedent. Removing either side
    leaves rows whose `faiss_idx` column drifts from the in-memory mapping.
    """
    src = inspect.getsource(FaceDB.rebuild_faiss_async)
    # Both sources must show up in the combined batch expression.
    assert "snapshot_idx_updates + pending_idx_updates" in src, (
        "Phase 3 must combine snapshot + pending updates into a single batch"
    )
    # Pending replay loop must append (new_idx, row_id) so the row_id captured
    # in `add_embedding`'s explicit-cursor flows into the DB UPDATE.
    assert "pending_idx_updates.append((new_idx, row_id))" in src, (
        "Phase 3 must append (new_idx, row_id) into pending_idx_updates"
    )


# ── D3.3 — DB UPDATE batch runs AFTER _index_lock release ─────────────────────

def test_d3_rebuild_async_db_update_batch_runs_after_lock_release():
    """D3 anchor (3/3): DB UPDATE happens AFTER the _index_lock block ends.

    Matches the sync precedent at core/db.py:1067-1080 — holding the index
    lock across the DB batch would extend lock-hold time by the duration of
    every UPDATE+commit (potentially seconds on a large gallery), starving
    concurrent recognize() callers. Lock-then-release-then-update keeps the
    hold to the in-memory swap only.
    """
    src = textwrap.dedent(inspect.getsource(FaceDB.rebuild_faiss_async))
    tree = ast.parse(src)

    # Walk the entire function tree to find all `with self._index_lock:`
    # statements and all "UPDATE embeddings SET faiss_idx" string constants,
    # then compare by line number. The Phase 3 swap is the LAST lock block,
    # and the DB UPDATE must come AFTER its exit line.
    lock_blocks: list[ast.With] = []
    update_const_lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.With) and any(
            isinstance(item.context_expr, ast.Attribute)
            and item.context_expr.attr == "_index_lock"
            for item in node.items
        ):
            lock_blocks.append(node)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "UPDATE embeddings SET faiss_idx" in node.value:
                update_const_lines.append(node.lineno)

    assert lock_blocks, "rebuild_faiss_async must use self._index_lock"
    assert update_const_lines, "rebuild_faiss_async must emit a DB UPDATE batch"

    # Phase 3 swap is the lock block with the LATEST lineno. Its body extends
    # through end_lineno (Python 3.8+ has end_lineno on every node).
    phase3_lock = max(lock_blocks, key=lambda n: n.lineno)
    last_update_line = max(update_const_lines)
    assert last_update_line > phase3_lock.end_lineno, (
        f"DB UPDATE (line {last_update_line}) must run AFTER the Phase 3 "
        f"_index_lock block exit (line {phase3_lock.end_lineno})"
    )

    # Defense-in-depth: no UPDATE statement INSIDE any lock block (catches a
    # future refactor that drops the batch back into the lock).
    for lb in lock_blocks:
        for sub in ast.walk(lb):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                assert "UPDATE embeddings SET faiss_idx" not in sub.value, (
                    f"DB UPDATE must NOT run inside any _index_lock block "
                    f"(found at line {sub.lineno})"
                )


# ── D4.1 — _mark_faiss_dirty runs BEFORE Phase 3 swap + ORDERING INVARIANT cmt ─

def test_d4_rebuild_async_marks_faiss_dirty_before_phase3_swap():
    """D4 anchor (1/2): sentinel SET before Phase 3 + ORDERING INVARIANT comment.

    The sentinel marks the disk file + DB state as potentially-divergent
    during the rebuild window. A crash anywhere between this mark and the
    Phase-4 `_clear_faiss_dirty` triggers boot reconciliation via
    `_rebuild_faiss`.
    """
    src = inspect.getsource(FaceDB.rebuild_faiss_async)
    assert "self._mark_faiss_dirty()" in src, "sentinel mark must be present"
    mark_idx = src.index("self._mark_faiss_dirty()")

    # Phase 3 swap is the last `with self._index_lock:` block. Find its source
    # location via simple string search — it's the lock block AFTER the mark.
    phase3_idx = src.index("with self._index_lock:", mark_idx)
    assert mark_idx < phase3_idx, (
        "_mark_faiss_dirty() must run BEFORE Phase 3's _index_lock block"
    )

    # ORDERING INVARIANT comment block must name the sentinel discipline so
    # future maintainers see the rationale at the call site.
    assert "ORDERING INVARIANT" in src, (
        "rebuild_faiss_async must document the ORDERING INVARIANT at its body"
    )


# ── D4.2 — _clear_faiss_dirty runs AFTER Phase 4 _save_faiss ──────────────────

def test_d4_rebuild_async_clears_faiss_dirty_after_phase4_save():
    """D4 anchor (2/2): sentinel CLEAR runs only after both DB UPDATE commit
    AND `_save_faiss` succeed. Any earlier exception leaves the sentinel set.
    """
    src = inspect.getsource(FaceDB.rebuild_faiss_async)
    assert "self._clear_faiss_dirty()" in src, "sentinel clear must be present"
    clear_idx = src.index("self._clear_faiss_dirty()")
    save_idx = src.index("self._save_faiss")
    assert save_idx < clear_idx, (
        "_clear_faiss_dirty() must run AFTER the Phase 4 _save_faiss call"
    )
    # Defense-in-depth: also assert clear is AFTER the DB UPDATE batch.
    update_idx = src.index("UPDATE embeddings SET faiss_idx")
    assert update_idx < clear_idx, (
        "_clear_faiss_dirty() must run AFTER the DB UPDATE batch"
    )
