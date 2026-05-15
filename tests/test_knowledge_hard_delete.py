"""
Tests for BrainDB.hard_delete_old_invalidated_knowledge — Wave 6 / Item 22.
"""
import sqlite3
import time
import pytest


def _make_brain_db(tmp_path):
    """Return a BrainDB instance backed by a fresh tmp file."""
    from core.brain_agent import BrainDB
    return BrainDB(str(tmp_path / "brain.db"))


def _insert_knowledge(db, invalidated_at=None, *, entity="test", attribute="attr", value="val"):
    """Insert one knowledge row directly; return its id."""
    now = time.time()
    cur = db._conn.execute(
        "INSERT INTO knowledge "
        "(source_turn_id, person_id, entity, entity_type, attribute, value, "
        " confidence, agent, created_at, invalidated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (1, "pid_test", entity, "person", attribute, value, 0.9, "test", now, invalidated_at),
    )
    db._conn.commit()
    return cur.lastrowid


class TestHardDeleteOldInvalidatedKnowledge:
    def test_removes_invalidated_rows_older_than_cutoff(self, tmp_path):
        """Only the 90d-old invalidated row is removed; active + 30d rows stay."""
        db = _make_brain_db(tmp_path)
        now = time.time()

        active_id       = _insert_knowledge(db, invalidated_at=None)
        recent_inv_id   = _insert_knowledge(db, invalidated_at=now - 30 * 86400, attribute="a2")
        old_inv_id      = _insert_knowledge(db, invalidated_at=now - 90 * 86400, attribute="a3")

        n = db.hard_delete_old_invalidated_knowledge(cutoff_days=60, now=now)

        assert n == 1

        ids_left = {r[0] for r in db._conn.execute("SELECT id FROM knowledge").fetchall()}
        assert old_inv_id not in ids_left
        assert active_id in ids_left
        assert recent_inv_id in ids_left

        db._conn.close()

    def test_skips_active_rows(self, tmp_path):
        """Active rows (invalidated_at IS NULL) are never touched, even with cutoff_days=1."""
        db = _make_brain_db(tmp_path)
        now = time.time()

        for i in range(5):
            _insert_knowledge(db, invalidated_at=None, attribute=f"attr_{i}")

        n = db.hard_delete_old_invalidated_knowledge(cutoff_days=1, now=now)

        assert n == 0
        count = db._conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
        assert count == 5

        db._conn.close()

    def test_idempotent_same_day(self, tmp_path):
        """Running twice on the same DB produces 1 deletion then 0."""
        db = _make_brain_db(tmp_path)
        now = time.time()
        _insert_knowledge(db, invalidated_at=now - 90 * 86400)

        first  = db.hard_delete_old_invalidated_knowledge(cutoff_days=60, now=now)
        second = db.hard_delete_old_invalidated_knowledge(cutoff_days=60, now=now)

        assert first == 1
        assert second == 0

        db._conn.close()
