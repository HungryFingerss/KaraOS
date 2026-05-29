"""
Tests for Wave 7 Item 25 — concurrent DB access / WAL invariants.

All tests use tmp_path for isolation; no production data is touched.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import sqlite3
import threading
import time

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_facedb(tmp_path):
    from core.db import FaceDB
    return FaceDB(str(tmp_path / "faces.db"), faiss_path=tmp_path / "faiss.index")


def _make_braindb(tmp_path):
    from core.brain_agent import BrainDB
    return BrainDB(path=tmp_path / "brain.db")


def _make_classifierdb(tmp_path):
    from core.classifier_db import ClassifierDB
    return ClassifierDB(
        db_path=tmp_path / "classifier.db",
        audit_log_path=tmp_path / "audit.jsonl",
    )


# ── WAL invariant tests ───────────────────────────────────────────────────────

class TestWALInvariants:
    def test_facedb_uses_wal_mode(self, tmp_path):
        db = _make_facedb(tmp_path)
        mode = db._conn.execute("PRAGMA journal_mode").fetchone()[0]
        db._conn.close()
        assert mode == "wal", f"FaceDB journal_mode={mode!r}, expected 'wal'"

    def test_braindb_uses_wal_mode(self, tmp_path):
        db = _make_braindb(tmp_path)
        mode = db._conn.execute("PRAGMA journal_mode").fetchone()[0]
        db._conn.close()
        assert mode == "wal", f"BrainDB journal_mode={mode!r}, expected 'wal'"

    def test_classifierdb_uses_wal_mode(self, tmp_path):
        db = _make_classifierdb(tmp_path)
        mode = db._conn.execute("PRAGMA journal_mode").fetchone()[0]
        db._conn.close()
        assert mode == "wal", f"ClassifierDB journal_mode={mode!r}, expected 'wal'"


# ── threading tests ───────────────────────────────────────────────────────────

class TestConcurrentAccess:
    def test_concurrent_reader_not_starved_during_writer(self, tmp_path):
        """
        WAL allows concurrent readers even while a writer is active.
        Writer thread: 100 log_turn inserts spread over 1s.
        Reader thread: SELECT COUNT(*) every 10ms.
        Asserts: ≥50 successful reads and max per-read latency < 100ms.
        """
        db = _make_facedb(tmp_path)
        # Insert directly — no FK enforcement in FaceDB, so no persons row needed.
        db._conn.execute(
            "INSERT INTO persons (id, name, enrolled_at) "
            "VALUES ('p_reader_test', 'Tester', 0.0)"
        )
        db._conn.commit()

        read_latencies = []
        read_errors = []
        stop_event = threading.Event()

        def reader():
            # Open a separate connection — proves WAL reader/writer independence.
            conn = sqlite3.connect(str(tmp_path / "faces.db"), timeout=5.0)
            try:
                while not stop_event.is_set():
                    t0 = time.perf_counter()
                    try:
                        conn.execute("SELECT COUNT(*) FROM conversation_log").fetchone()
                        read_latencies.append(time.perf_counter() - t0)
                    except sqlite3.OperationalError as exc:
                        read_errors.append(str(exc))
                    time.sleep(0.01)
            finally:
                conn.close()

        reader_thread = threading.Thread(target=reader, daemon=True)
        reader_thread.start()

        # Writer: 100 inserts over ~1s
        for i in range(100):
            db.log_turn("p_reader_test", "user", f"msg {i}")
            time.sleep(0.01)

        stop_event.set()
        reader_thread.join(timeout=5.0)
        db._conn.close()

        assert len(read_errors) == 0, f"reader saw errors: {read_errors[:5]}"
        assert len(read_latencies) >= 50, (
            f"expected ≥50 successful reads, got {len(read_latencies)}"
        )
        max_latency_ms = max(read_latencies) * 1000
        assert max_latency_ms < 100, (
            f"max read latency {max_latency_ms:.1f}ms exceeds 100ms (WAL starvation?)"
        )

    def test_concurrent_writers_serialize_via_busy_timeout(self, tmp_path):
        """
        Two writers against the same WAL DB must not raise SQLITE_BUSY.
        Python sqlite3 default timeout=5s serializes them transparently.
        """
        db_path = str(tmp_path / "faces.db")
        # Bootstrap schema via FaceDB, then close the helper object.
        bootstrapper = _make_facedb(tmp_path)
        bootstrapper._conn.execute(
            "INSERT INTO persons (id, name, enrolled_at) VALUES ('p_write_a', 'Alice', 0.0)"
        )
        bootstrapper._conn.execute(
            "INSERT INTO persons (id, name, enrolled_at) VALUES ('p_write_b', 'Bob', 0.0)"
        )
        bootstrapper._conn.commit()
        bootstrapper._conn.close()

        errors = []

        def writer_a():
            conn = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            try:
                for i in range(20):
                    conn.execute(
                        "INSERT INTO conversation_log (person_id, role, content, ts) "
                        "VALUES (?, ?, ?, ?)",
                        ("p_write_a", "user", f"a{i}", time.time()),
                    )
                    conn.commit()
            except sqlite3.OperationalError as exc:
                errors.append(f"writer_a: {exc}")
            finally:
                conn.close()

        def writer_b():
            conn = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            try:
                for i in range(20):
                    conn.execute(
                        "INSERT INTO conversation_log (person_id, role, content, ts) "
                        "VALUES (?, ?, ?, ?)",
                        ("p_write_b", "user", f"b{i}", time.time()),
                    )
                    conn.commit()
            except sqlite3.OperationalError as exc:
                errors.append(f"writer_b: {exc}")
            finally:
                conn.close()

        t_a = threading.Thread(target=writer_a)
        t_b = threading.Thread(target=writer_b)
        t_a.start()
        t_b.start()
        t_a.join(timeout=15.0)
        t_b.join(timeout=15.0)

        assert errors == [], f"SQLITE_BUSY or other error: {errors}"

        # Verify both writers completed all 20 rows each.
        verify = sqlite3.connect(db_path)
        count_a = verify.execute(
            "SELECT COUNT(*) FROM conversation_log WHERE person_id='p_write_a'"
        ).fetchone()[0]
        count_b = verify.execute(
            "SELECT COUNT(*) FROM conversation_log WHERE person_id='p_write_b'"
        ).fetchone()[0]
        verify.close()
        assert count_a == 20, f"writer_a only wrote {count_a}/20 rows"
        assert count_b == 20, f"writer_b only wrote {count_b}/20 rows"
