"""
Tests for FaceDB conversation log archival — Wave 6 / Item 21.

Source-inspection tests are avoided; all 6 tests are behavioural and use
a real FaceDB instance backed by a fresh tmp file so no production data is
touched.  The archive database is auto-created at
``<db_stem>_conversation_archive.db`` next to the main DB.
"""
import time
import pytest


def _make_db(tmp_path):
    from core.db import FaceDB
    return FaceDB(str(tmp_path / "faces.db"), faiss_path=tmp_path / "faiss.index")


def _insert_turn(db, person_id, role, content, ts):
    db._conn.execute(
        "INSERT INTO conversation_log (person_id, role, content, ts) VALUES (?, ?, ?, ?)",
        (person_id, role, content, ts),
    )
    db._conn.commit()


class TestConversationArchive:
    def test_archive_moves_old_rows_to_archive_db(self, tmp_path):
        """Rows older than cutoff are moved to the archive DB and removed from main."""
        db = _make_db(tmp_path)
        now = time.time()
        old_ts = now - 40 * 86400  # 40 days ago — past default 30d cutoff
        new_ts = now - 5 * 86400   # 5 days ago — recent

        _insert_turn(db, "pid1", "user", "old message", old_ts)
        _insert_turn(db, "pid1", "assistant", "old reply", old_ts + 1)
        _insert_turn(db, "pid1", "user", "recent message", new_ts)

        n = db.archive_old_conversation_log(cutoff_days=30, now=now)

        assert n == 2, f"expected 2 rows archived, got {n}"

        # Rows no longer in main DB
        main_rows = db._conn.execute(
            "SELECT content FROM conversation_log WHERE person_id = 'pid1' ORDER BY ts"
        ).fetchall()
        assert len(main_rows) == 1
        assert main_rows[0][0] == "recent message"

        # Rows present in archive DB
        import sqlite3
        archive_path = db._archive_db_path()
        _ac = sqlite3.connect(str(archive_path))
        arch_rows = _ac.execute(
            "SELECT content FROM conversation_log WHERE person_id = 'pid1' ORDER BY ts"
        ).fetchall()
        _ac.close()
        assert len(arch_rows) == 2
        assert {r[0] for r in arch_rows} == {"old message", "old reply"}

        db._conn.close()

    def test_archive_keeps_recent_rows_in_main_db(self, tmp_path):
        """Rows newer than the cutoff are not touched."""
        db = _make_db(tmp_path)
        now = time.time()
        recent_ts = now - 10 * 86400  # 10 days — within 30d cutoff

        for i in range(5):
            _insert_turn(db, "pid2", "user", f"msg {i}", recent_ts + i)

        n = db.archive_old_conversation_log(cutoff_days=30, now=now)

        assert n == 0
        count = db._conn.execute(
            "SELECT COUNT(*) FROM conversation_log WHERE person_id = 'pid2'"
        ).fetchone()[0]
        assert count == 5

        db._conn.close()

    def test_archive_idempotent(self, tmp_path):
        """Archiving twice does not duplicate rows; second call returns 0."""
        db = _make_db(tmp_path)
        now = time.time()
        old_ts = now - 60 * 86400  # 60 days ago

        _insert_turn(db, "pid3", "user", "stale turn", old_ts)

        first = db.archive_old_conversation_log(cutoff_days=30, now=now)
        second = db.archive_old_conversation_log(cutoff_days=30, now=now)

        assert first == 1
        assert second == 0

        import sqlite3
        archive_path = db._archive_db_path()
        _ac = sqlite3.connect(str(archive_path))
        count = _ac.execute(
            "SELECT COUNT(*) FROM conversation_log WHERE person_id = 'pid3'"
        ).fetchone()[0]
        _ac.close()
        assert count == 1, "archive should contain exactly 1 row, not 2"

        db._conn.close()

    def test_archive_returns_correct_count(self, tmp_path):
        """archive_old_conversation_log returns the exact number of rows moved."""
        db = _make_db(tmp_path)
        now = time.time()
        old_ts = now - 35 * 86400

        for i in range(7):
            _insert_turn(db, "pid4", "user", f"old {i}", old_ts + i)

        n = db.archive_old_conversation_log(cutoff_days=30, now=now)
        assert n == 7

        db._conn.close()

    def test_load_history_includes_archived_rows(self, tmp_path):
        """load_conversation_history returns rows from both main and archive."""
        db = _make_db(tmp_path)
        now = time.time()
        old_ts = now - 40 * 86400
        recent_ts = now - 2 * 86400

        _insert_turn(db, "pid5", "user", "archived content", old_ts)
        _insert_turn(db, "pid5", "user", "recent content", recent_ts)

        # Archive the old row
        db.archive_old_conversation_log(cutoff_days=30, now=now)

        # load_conversation_history should return both
        history = db.load_conversation_history("pid5")
        contents = [m["content"] for m in history if m["role"] == "user"]
        assert any("archived content" in c for c in contents), \
            "archived row should appear in load_conversation_history"
        assert any("recent content" in c for c in contents), \
            "recent row should still appear"

        db._conn.close()

    def test_search_conversation_includes_archive(self, tmp_path):
        """search_conversation finds keyword matches in the archive DB."""
        db = _make_db(tmp_path)
        now = time.time()
        old_ts = now - 50 * 86400
        recent_ts = now - 1 * 86400

        _insert_turn(db, "pid6", "user", "unique_keyword old", old_ts)
        _insert_turn(db, "pid6", "user", "unique_keyword recent", recent_ts)

        db.archive_old_conversation_log(cutoff_days=30, now=now)

        results = db.search_conversation("pid6", "unique_keyword", limit=10)
        excerpts = [r["excerpt"] for r in results]
        assert any("unique_keyword old" in e for e in excerpts), \
            "archived row should appear in search_conversation"
        assert any("unique_keyword recent" in e for e in excerpts), \
            "recent row should still appear in search"

        db._conn.close()
