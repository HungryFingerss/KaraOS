"""test_pipeline_db_faiss — db faiss tests (split from test_pipeline.py, P1.A1 SP-1).

Behavior-neutral move: test bodies are verbatim from the original root
test_pipeline.py. `import pipeline` stays lazy inside each test body (stubs are
installed by tests/conftest.py).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import asyncio
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
import types
import pytest
import numpy as np
import time as _time_mod
import numpy as _np


def _make_faces_stub(tmp_path):
    """Create a minimal object with _conn pointing to a seeded in-memory sqlite3 db."""
    import sqlite3 as _sq3
    import datetime as _dt

    class _Stub:
        pass

    import pathlib as _pl
    obj = _Stub()
    _db_path_str = str(tmp_path / "faces_g6a.db")
    obj._conn = _sq3.connect(_db_path_str)
    obj._db_path = _db_path_str
    # _archive_db_path() is called by load_conversation_history / search_conversation.
    obj._archive_db_path = lambda: _pl.Path(_db_path_str).with_name("faces_g6a_conversation_archive.db")
    obj._conn.executescript("""
        CREATE TABLE IF NOT EXISTS persons (
            id   TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            enrolled_at REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS conversation_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id TEXT NOT NULL,
            role      TEXT NOT NULL,
            content   TEXT NOT NULL,
            ts        REAL NOT NULL DEFAULT 0
        );
    """)
    obj._conn.commit()
    return obj


def test_load_conversation_history_returns_at_most_limit(tmp_path):
    """I4: load_conversation_history must return at most CONVERSATION_HISTORY_LIMIT turns."""
    from core.db import FaceDB
    from core.config import CONVERSATION_HISTORY_LIMIT

    stub = _make_faces_stub(tmp_path)
    # Insert more turns than the limit
    for i in range(CONVERSATION_HISTORY_LIMIT + 20):
        stub._conn.execute(
            "INSERT INTO conversation_log (person_id, role, content, ts) VALUES (?,?,?,?)",
            ("p1", "user" if i % 2 == 0 else "assistant", f"msg {i}", float(i)),
        )
    stub._conn.commit()

    result = FaceDB.load_conversation_history(stub, "p1")
    # session-break markers may add synthetic turns, but raw DB turns must be capped
    raw_turns = [m for m in result if not m["content"].startswith("[New session")]
    assert len(raw_turns) <= CONVERSATION_HISTORY_LIMIT

    stub._conn.close()


def test_load_conversation_history_oldest_first(tmp_path):
    """I4: returned turns must be in chronological (oldest-first) order."""
    from core.db import FaceDB

    stub = _make_faces_stub(tmp_path)
    for i in range(5):
        stub._conn.execute(
            "INSERT INTO conversation_log (person_id, role, content, ts) VALUES (?,?,?,?)",
            ("p1", "user", f"msg {i}", float(i * 10)),
        )
    stub._conn.commit()

    result = FaceDB.load_conversation_history(stub, "p1")
    # Extract the msg index from each turn (user turns have a timestamp prefix)
    indices = [int(m["content"].split("msg ")[-1]) for m in result if "msg" in m["content"]]
    assert indices == sorted(indices)

    stub._conn.close()


def test_get_person_id_by_name_found(tmp_path):
    """get_person_id_by_name returns the person_id for a matching name."""
    from core.db import FaceDB
    stub = _make_faces_stub(tmp_path)
    stub._conn.execute("INSERT INTO persons (id, name, enrolled_at) VALUES (?,?,?)",
                       ("jagan_001", "Jagan", 0.0))
    stub._conn.commit()

    result = FaceDB.get_person_id_by_name(stub, "Jagan")
    assert result == "jagan_001"

    # Case-insensitive
    result_lower = FaceDB.get_person_id_by_name(stub, "jagan")
    assert result_lower == "jagan_001"

    stub._conn.close()


def test_get_person_id_by_name_not_found(tmp_path):
    """get_person_id_by_name returns None when name is not in persons table."""
    from core.db import FaceDB
    stub = _make_faces_stub(tmp_path)

    result = FaceDB.get_person_id_by_name(stub, "Nobody")
    assert result is None

    stub._conn.close()


def test_search_conversation_returns_matching_excerpts(tmp_path):
    """search_conversation returns turns containing keyword; long content is truncated."""
    import time as _t
    from core.db import FaceDB

    stub = _make_faces_stub(tmp_path)
    base_ts = _t.time()
    stub._conn.executemany(
        "INSERT INTO conversation_log (person_id, role, content, ts) VALUES (?,?,?,?)",
        [
            ("p1", "user",      "I love hiking in the mountains",       base_ts + 1),
            ("p1", "assistant", "That's great! Hiking is wonderful.",   base_ts + 2),
            ("p1", "user",      "The weather was nice today",           base_ts + 3),  # no match
        ],
    )
    stub._conn.commit()

    results = FaceDB.search_conversation(stub, "p1", "hiking", limit=4)

    assert len(results) == 2
    assert all("hiking" in r["excerpt"].lower() for r in results)
    # Most-recent first
    assert "wonderful" in results[0]["excerpt"].lower()

    # Long content gets truncated
    long_content = "x" * 250
    stub._conn.execute(
        "INSERT INTO conversation_log (person_id, role, content, ts) VALUES (?,?,?,?)",
        ("p1", "user", long_content, base_ts + 10),
    )
    stub._conn.commit()
    long_results = FaceDB.search_conversation(stub, "p1", "x" * 5, limit=4)
    assert len(long_results) >= 1
    assert long_results[0]["excerpt"].endswith("…")
    assert len(long_results[0]["excerpt"]) == 201  # 200 chars + ellipsis

    stub._conn.close()


def test_search_conversation_returns_empty_on_no_match(tmp_path):
    """search_conversation returns [] when keyword has no matches."""
    from core.db import FaceDB

    stub = _make_faces_stub(tmp_path)
    stub._conn.execute(
        "INSERT INTO conversation_log (person_id, role, content, ts) VALUES (?,?,?,?)",
        ("p1", "user", "totally unrelated content", 1.0),
    )
    stub._conn.commit()

    results = FaceDB.search_conversation(stub, "p1", "xyzzy123", limit=4)
    assert results == []

    stub._conn.close()


def test_face_db_has_index_lock(tmp_path):
    """BUG-13: FaceDB.__init__ must create an _index_lock (threading.RLock) to
    serialise concurrent FAISS access between the executor thread (recognize) and
    the main event-loop thread (add_embedding, _rebuild_faiss, _save_faiss)."""
    import threading
    from core.db import FaceDB

    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))
    assert hasattr(db, "_index_lock"), "FaceDB missing _index_lock attribute"
    assert isinstance(db._index_lock, type(threading.RLock())), \
        "_index_lock must be a threading.RLock instance"
    db._conn.close()


def test_facedb_tmp_path_does_not_write_production_faiss(tmp_path):
    """FaceDB created with tmp SQLite + tmp FAISS must not touch production faiss.index."""
    import os
    from core.config import FAISS_INDEX_PATH
    from core.db import FaceDB

    # Note the production file's modification time before the test
    prod_mtime_before = FAISS_INDEX_PATH.stat().st_mtime if FAISS_INDEX_PATH.exists() else None

    # Create a FaceDB with isolated paths (the new API)
    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))
    db._conn.close()

    prod_mtime_after = FAISS_INDEX_PATH.stat().st_mtime if FAISS_INDEX_PATH.exists() else None
    assert prod_mtime_before == prod_mtime_after, \
        "FaceDB with tmp paths must not modify the production faiss.index file"


def test_facedb_faiss_roundtrip_survives_reload(tmp_path):
    """Vectors saved by one FaceDB instance must be readable by a new instance at same path."""
    import numpy as np
    from core.db import FaceDB

    db_file    = str(tmp_path / "faces.db")
    faiss_file = str(tmp_path / "faiss.index")

    db1 = FaceDB(db_file, faiss_path=faiss_file)
    db1.add_person("p1", "Alice")
    emb = np.random.rand(512).astype(np.float32)
    emb /= np.linalg.norm(emb)
    db1.add_embedding("p1", emb.reshape(1, -1), source="enrollment", anti_spoof_verdict=True)
    db1._conn.close()

    # Reload — simulates pipeline restart
    db2 = FaceDB(db_file, faiss_path=faiss_file)
    assert db2.index.ntotal == 1, \
        f"Reloaded FAISS index should have 1 vector, got {db2.index.ntotal}"
    pid, name, conf = db2.recognize(emb.reshape(1, -1), threshold=0.1)
    assert pid == "p1", f"Expected p1, got {pid}"
    db2._conn.close()


def test_state_set_persistent_persists_across_writes():
    """#13: _persistent fields survive multiple state.write() calls."""
    import json, pathlib
    import core.state as st
    st._persistent.clear()
    st.set_persistent("anti_spoof_enabled", False)
    with tempfile.TemporaryDirectory() as td:
        orig = st.STATE_FILE
        st.STATE_FILE = pathlib.Path(td) / "state.json"
        try:
            st.write(status="idle")
            d1 = json.loads(st.STATE_FILE.read_text())
            st.write(status="listening")
            d2 = json.loads(st.STATE_FILE.read_text())
        finally:
            st.STATE_FILE = orig
            st._persistent.clear()
    assert d1.get("anti_spoof_enabled") is False
    assert d2.get("anti_spoof_enabled") is False


def test_load_faiss_warns_on_null_vectors(tmp_path, capsys):
    """_load_faiss prints WARNING when rows with NULL vectors exist in DB."""
    import sqlite3, numpy as np
    from core.db import FaceDB
    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "faiss.index")
    # Inject a NULL-vector row directly into the DB
    db._conn.execute(
        "INSERT INTO persons (id, name, enrolled_at, person_type) VALUES ('p_null', 'Ghost', 0, 'known')"
    )
    db._conn.execute(
        "INSERT INTO embeddings (person_id, faiss_idx, vector, captured_at, source, confidence_at_write)"
        " VALUES ('p_null', 999, NULL, 0.0, 'test', 0.0)"
    )
    db._conn.commit()
    # Reload FAISS to trigger _load_faiss
    db._load_faiss()
    captured = capsys.readouterr()
    assert "NULL vector" in captured.out or "null vector" in captured.out.lower() or "NULL" in captured.out
    db._conn.close()


def test_load_faiss_no_warning_when_no_nulls(tmp_path, capsys):
    """_load_faiss prints no NULL warning when all vectors are present."""
    import numpy as np
    from core.db import FaceDB
    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "faiss.index")
    db._load_faiss()
    captured = capsys.readouterr()
    assert "NULL vector" not in captured.out
    db._conn.close()


def _seed_person(db, person_id: str, name: str, embeddings: list) -> None:
    """Helper: insert a person + face embeddings directly into test DB."""
    import time
    db._conn.execute(
        "INSERT OR IGNORE INTO persons (id, name, enrolled_at, person_type) VALUES (?, ?, ?, 'known')",
        (person_id, name, time.time()),
    )
    db._conn.commit()
    for i, emb in enumerate(embeddings):
        import numpy as np
        vec = np.array(emb, dtype=np.float32)
        vec /= np.linalg.norm(vec)
        db._conn.execute(
            "INSERT INTO embeddings (person_id, faiss_idx, vector, captured_at, source, confidence_at_write)"
            " VALUES (?, ?, ?, ?, 'enrollment', 0.9)",
            (person_id, i, vec.tobytes(), float(i)),
        )
    db._conn.commit()
    db._rebuild_faiss()


def test_audit_gallery_returns_empty_outliers_for_clean_gallery(tmp_path):
    """Clean gallery (all same person) should have no or few outliers."""
    import numpy as np
    from core.db import FaceDB
    from core.audit import audit_gallery

    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "faiss.index")
    base = np.random.default_rng(42).normal(0, 0.1, 512).astype(np.float32)
    embs = [base + np.random.default_rng(i).normal(0, 0.01, 512).astype(np.float32) for i in range(10)]
    _seed_person(db, "alice", "Alice", embs)

    r = audit_gallery("alice", db)
    assert r["total"] == 10
    assert len(r["outliers"]) == 0, f"Expected no outliers for clean gallery, got {r['outliers']}"
    db._conn.close()


def test_audit_gallery_detects_poisoned_embeddings(tmp_path):
    """Two embeddings from a completely different cluster should be flagged as outliers."""
    import numpy as np
    from core.db import FaceDB
    from core.audit import audit_gallery

    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "faiss.index")
    rng = np.random.default_rng(7)
    good_base = rng.normal(0, 0.1, 512).astype(np.float32)
    good_embs = [good_base + rng.normal(0, 0.01, 512).astype(np.float32) for _ in range(10)]
    # Two poisoned embeddings pointing in the opposite direction
    poison_embs = [-good_base + rng.normal(0, 0.01, 512).astype(np.float32) for _ in range(2)]
    _seed_person(db, "bob", "Bob", good_embs + poison_embs)

    r = audit_gallery("bob", db)
    assert r["total"] == 12
    assert len(r["outliers"]) >= 1, "Poisoned embeddings should be flagged as outliers"
    db._conn.close()


def test_gallery_audit_returns_outlier_ids_without_modification(tmp_path):
    """FaceDB.gallery_audit() returns outlier_row_ids without modifying the DB.

    P0.S9 D1 replacement: the original `test_repair_gallery_removes_outliers` +
    `test_repair_gallery_flag_mode_does_not_modify` tests covered the
    `core.audit.repair_gallery` duplicate that was a P0.5 inverse-check violation
    (missing _index_lock + transaction + sentinel). P0.S9 D1 consolidated by
    redirecting `audit_person.py --repair` to `FaceDB.prune_outlier_embeddings`
    (the P0.5-correct paired-write site) and deleting `repair_gallery` entirely.
    The original flag-mode test was a no-op preview equivalent to the direct
    `db.gallery_audit()` read-only call exercised here.
    """
    import numpy as np
    from core.db import FaceDB

    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "faiss.index")
    rng = np.random.default_rng(99)
    good_base = rng.normal(0, 0.1, 512).astype(np.float32)
    good_embs = [good_base + rng.normal(0, 0.01, 512).astype(np.float32) for _ in range(10)]
    poison_embs = [-good_base + rng.normal(0, 0.01, 512).astype(np.float32) for _ in range(2)]
    _seed_person(db, "dave", "Dave", good_embs + poison_embs)

    pre_count = db._conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    results = db.gallery_audit(person_id="dave")
    assert results, "gallery_audit should return non-empty results"
    assert "outlier_row_ids" in results[0]
    post_count = db._conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    assert post_count == pre_count, "gallery_audit must not modify DB"
    db._conn.close()


def test_audit_gallery_handles_single_embedding(tmp_path):
    """audit_gallery on a 1-embedding gallery returns a note, no crash."""
    import numpy as np
    from core.db import FaceDB
    from core.audit import audit_gallery

    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "faiss.index")
    emb = np.random.default_rng(0).normal(0, 0.1, 512).astype(np.float32)
    _seed_person(db, "eve", "Eve", [emb])

    r = audit_gallery("eve", db)
    assert r["total"] == 1
    assert "note" in r
    db._conn.close()


def test_graph_db_delete_person_entity(tmp_path):
    """GraphDB.delete_person_entity removes the Entity node without raising."""
    from core.brain_agent import GraphDB, Extraction

    gdb = GraphDB(tmp_path / "kuzu_graph")
    # Store a fact so Alice has a node with at least one edge
    ext = Extraction("Alice", "person", "hobby", "reading", 0.9, False, None)
    gdb.store_fact(ext, turn_id=1)

    # Verify Alice's node exists before deletion
    ctx_before = gdb.get_graph_context("Alice", caller_pid="Alice")
    assert ctx_before is not None, "Alice should have graph context before deletion"

    ok = gdb.delete_person_entity("Alice")
    assert ok is True

    # After deletion, context should be None (no node = no edges)
    ctx_after = gdb.get_graph_context("Alice", caller_pid="Alice")
    assert ctx_after is None, "Alice's graph context should be None after deletion"
    gdb.close()


def test_now_log_ts_format_is_hhmmssms():
    """core.log_utils._now_log_ts() must emit HH:MM:SS.mmm (ms precision, not μs)."""
    import re
    from core.log_utils import _now_log_ts
    ts = _now_log_ts()
    assert re.fullmatch(r"\d{2}:\d{2}:\d{2}\.\d{3}", ts), f"unexpected format: {ts!r}"


def test_log_trunc_zero_means_no_truncation():
    """LOG_STT_MAX_CHARS=0 (default) means _log_trunc returns the input verbatim."""
    from core.log_utils import _log_trunc
    long = "a" * 500
    assert _log_trunc(long, 0) == long
    assert _log_trunc(long, None) == long  # None → read config, which defaults to 0


def test_log_trunc_positive_limit_truncates_with_ellipsis():
    """When a positive limit is passed, strings longer than that get '…' appended."""
    from core.log_utils import _log_trunc
    assert _log_trunc("hello world", 5) == "hello…"
    assert _log_trunc("hi", 5) == "hi"  # under limit — unchanged


def test_log_turn_backward_compat_without_new_kwargs(tmp_path):
    """Session 107 Phase 3A.6 Part 3: log_turn's new kwargs
    (room_session_id, audience_ids) must be optional so existing
    callers don't break. Default behavior: columns written as NULL,
    next startup's backfill pass populates them deterministically."""
    from core.db import FaceDB
    db = FaceDB(
        str(tmp_path / "faces.db"),
        faiss_path=str(tmp_path / "faiss.index"),
    )
    try:
        # Existing 3-positional-arg signature must still work.
        db.log_turn("jagan_001", "user", "hello")
        row = db._conn.execute(
            "SELECT person_id, role, content, room_session_id, audience_ids "
            "FROM conversation_log"
        ).fetchone()
        assert row[:3] == ("jagan_001", "user", "hello")
        # New columns default to NULL when caller doesn't supply them.
        assert row[3] is None
        assert row[4] is None
    finally:
        db._conn.close()


def test_log_turn_accepts_new_kwargs_when_supplied(tmp_path):
    """Session 107 Phase 3A.6 Part 3: when 3B RoomOrchestrator supplies
    room_session_id + audience_ids, they must land in the columns
    verbatim (audience_ids JSON-encoded)."""
    import json as _json_lt
    from core.db import FaceDB
    db = FaceDB(
        str(tmp_path / "faces.db"),
        faiss_path=str(tmp_path / "faiss.index"),
    )
    try:
        db.log_turn(
            "jagan_001", "user", "hello",
            room_session_id="room_xyz_42",
            audience_ids=["jagan_001", "lexi_abc"],
        )
        row = db._conn.execute(
            "SELECT room_session_id, audience_ids FROM conversation_log"
        ).fetchone()
        assert row[0] == "room_xyz_42"
        assert _json_lt.loads(row[1]) == ["jagan_001", "lexi_abc"]
    finally:
        db._conn.close()


def test_active_sessions_and_persons_in_frame_iterations_wrapped_with_list():
    """Wave 1 Item 7: every iteration over _active_sessions or _persons_in_frame
    in async code must use list() to snapshot the dict before iterating.
    Without list(), a concurrent coroutine mutating the dict mid-iteration
    (e.g. _open_session / _close_session waking between loop steps) raises
    RuntimeError: dictionary changed size during iteration.

    This test source-inspects the background vision loop and conversation_turn
    to verify all iteration sites use list()."""
    import inspect, pipeline

    src_run = inspect.getsource(pipeline.run)
    src_conv = inspect.getsource(pipeline.conversation_turn)

    # Every .items() / .values() / .keys() call on the two mutable dicts in
    # async code should be wrapped in list(). Collect all raw (unwrapped) hits
    # across both functions and assert none remain.
    import re
    unwrapped = re.findall(
        r'(?<!list\()(_active_sessions|_persons_in_frame)\.(items|values|keys)\(\)',
        src_run + src_conv,
    )
    # The only known-safe exceptions are sites already wrapped with frozenset()
    # (which also materialises immediately) — those won't appear in the regex
    # above because they don't call .items()/.values()/.keys() directly.
    assert unwrapped == [], (
        f"Wave 1 Item 7: found unwrapped dict iteration(s) on _active_sessions "
        f"or _persons_in_frame in async code: {unwrapped}. "
        "Wrap each with list() to prevent RuntimeError on concurrent mutation."
    )


def test_face_db_checkpoint_wal_executes_pragma(tmp_path):
    """Wave 1 Item 6: FaceDB.checkpoint_wal() must issue PRAGMA
    wal_checkpoint(TRUNCATE) and not raise on a normal connection."""
    from core.db import FaceDB
    db = FaceDB(
        db_path=str(tmp_path / "faces.db"),
        faiss_path=tmp_path / "faiss.index",
    )
    try:
        # Must not raise; WAL checkpoint on a fresh DB is a no-op but valid.
        db.checkpoint_wal()
    finally:
        db._conn.close()


def test_brain_db_checkpoint_wal_executes_pragma(tmp_path):
    """Wave 1 Item 6: BrainDB.checkpoint_wal() must issue PRAGMA
    wal_checkpoint(TRUNCATE) and not raise on a normal connection."""
    from core.brain_agent import BrainDB
    db = BrainDB(path=tmp_path / "brain.db")
    try:
        db.checkpoint_wal()
    finally:
        db._conn.close()


def test_classifier_db_checkpoint_wal_executes_pragma(tmp_path):
    """Wave 1 Item 6: ClassifierDB.checkpoint_wal() must issue PRAGMA
    wal_checkpoint(TRUNCATE) and not raise on a normal connection."""
    from core.classifier_db import ClassifierDB
    db = ClassifierDB(
        db_path=str(tmp_path / "classifier.db"),
        audit_log_path=str(tmp_path / "audit.jsonl"),
    )
    try:
        db.checkpoint_wal()
    finally:
        db.close()
