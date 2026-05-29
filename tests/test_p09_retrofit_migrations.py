"""P0.9.2 — per-migration tests for the retrofit MIGRATIONS lists.

Hybrid coverage per reviewer's spec:

  - **Trivial migrations (column-only adds)**: one representative test
    per DB exercises a baseline trivial migration end-to-end.  The
    structural Item 1 invariant test in
    tests/test_schema_migrations.py covers shape across all entries; no
    per-migration boilerplate is added.

  - **Non-trivial migrations (multi-artifact, conditional, data
    backfills)**: each gets explicit verify_post + verify_present
    positive AND negative tests.

The two data-backfill migrations (faces.db v=9 conversation_log
room_session_id backfill, brain.db v=10 privacy_level remediation) are
the canonical examples that motivated the 5-tuple split — verify_post is
stronger than verify_present, and the tests prove it.

Grep target: "P0.9 invariants" (same as test_schema_migrations.py).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import json
import sqlite3

import pytest

from core import faces_db_migrations as _fm
from core import brain_db_migrations as _bm


def _fresh_conn() -> sqlite3.Connection:
    return sqlite3.connect(":memory:", isolation_level="IMMEDIATE")


# ---------------------------------------------------------------------------
# Faces.db schema fixture (matches the baseline created by FaceDB._init_tables
# BEFORE any of the retrofitted ALTER migrations).  This is the pre-P0.9.2
# legacy shape — what every existing production DB looks like.
# ---------------------------------------------------------------------------

_FACES_BASELINE_SQL = """
    CREATE TABLE persons (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        enrolled_at REAL NOT NULL,
        photo_path  TEXT
    );
    CREATE TABLE embeddings (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id   TEXT NOT NULL,
        faiss_idx   INTEGER NOT NULL,
        captured_at REAL NOT NULL
    );
    CREATE TABLE voice_embeddings (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id   TEXT NOT NULL,
        vector      BLOB NOT NULL,
        captured_at REAL NOT NULL
    );
    CREATE TABLE conversation_log (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id TEXT NOT NULL,
        role      TEXT NOT NULL,
        content   TEXT NOT NULL,
        ts        REAL NOT NULL
    );
    CREATE TABLE conversation_memory (id INTEGER);  -- legacy, dropped at v=10
"""


def _faces_legacy_conn() -> sqlite3.Connection:
    conn = _fresh_conn()
    conn.executescript(_FACES_BASELINE_SQL)
    return conn


# ---------------------------------------------------------------------------
# Trivial-migration representative tests (one per DB)
# ---------------------------------------------------------------------------

class TestTrivialMigrationsRepresentative:
    def test_faces_v2_persons_last_seen_end_to_end(self):
        """Representative trivial migration: column add + verify_post +
        verify_present round-trip on a legacy faces.db shape."""
        conn = _faces_legacy_conn()
        # Pre-state: column not present → verify_present must be False.
        v2 = next(m for m in _fm.MIGRATIONS if m[0] == 2)
        _, _, apply_fn, verify_post, verify_present = v2
        assert verify_present(conn) is False, "pre-apply: last_seen not yet present"
        apply_fn(conn)
        verify_post(conn)  # raises if post-state wrong
        assert verify_present(conn) is True, "post-apply: last_seen must be present"
        # Re-apply is idempotent.
        apply_fn(conn)
        verify_post(conn)
        assert verify_present(conn) is True

    def test_brain_v4_knowledge_last_confirmed_at_end_to_end(self):
        """Representative trivial migration on brain.db."""
        conn = _fresh_conn()
        conn.executescript("""
            CREATE TABLE knowledge (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                entity     TEXT NOT NULL,
                value      TEXT NOT NULL,
                created_at REAL NOT NULL
            );
        """)
        v4 = next(m for m in _bm.MIGRATIONS if m[0] == 4)
        _, _, apply_fn, verify_post, verify_present = v4
        assert verify_present(conn) is False
        apply_fn(conn)
        verify_post(conn)
        assert verify_present(conn) is True


# ---------------------------------------------------------------------------
# Non-trivial faces.db migrations
# ---------------------------------------------------------------------------

class TestFacesV7PairedColumnAdd:
    """v=7: conversation_log room_session_id + audience_ids — paired
    column adds, both must be present for the migration to be considered
    applied."""

    def test_verify_present_false_when_neither_column_exists(self):
        conn = _faces_legacy_conn()
        v7 = next(m for m in _fm.MIGRATIONS if m[0] == 7)
        assert v7[4](conn) is False

    def test_verify_present_false_when_only_one_column_exists(self):
        """Partial-apply detection: if one column landed but not the
        other (e.g. operator manually ran the first ALTER), verify_present
        MUST return False so the runner finishes the job."""
        conn = _faces_legacy_conn()
        conn.execute("ALTER TABLE conversation_log ADD COLUMN room_session_id TEXT")
        # audience_ids still missing → not yet "applied".
        v7 = next(m for m in _fm.MIGRATIONS if m[0] == 7)
        assert v7[4](conn) is False

    def test_apply_then_verify_post_succeeds(self):
        conn = _faces_legacy_conn()
        v7 = next(m for m in _fm.MIGRATIONS if m[0] == 7)
        _, _, apply_fn, verify_post, verify_present = v7
        apply_fn(conn)
        verify_post(conn)
        assert verify_present(conn) is True


class TestFacesV9ConversationLogBackfill:
    """v=9: DATA BACKFILL — conversation_log room_session_id/audience_ids
    deterministic backfill from per-person MIN(ts).  This is the
    canonical example of verify_post being STRONGER than verify_present."""

    def _conn_with_unbackfilled_rows(self) -> sqlite3.Connection:
        conn = _faces_legacy_conn()
        # Apply v=7 first (column add) so the backfill has something to do.
        v7 = next(m for m in _fm.MIGRATIONS if m[0] == 7)
        v7[2](conn)
        # Insert legacy rows (no room_session_id yet).
        conn.execute(
            "INSERT INTO conversation_log(person_id, role, content, ts) "
            "VALUES ('alice', 'user', 'hi', 1000.0)"
        )
        conn.execute(
            "INSERT INTO conversation_log(person_id, role, content, ts) "
            "VALUES ('alice', 'assistant', 'hello', 1001.0)"
        )
        conn.execute(
            "INSERT INTO conversation_log(person_id, role, content, ts) "
            "VALUES ('bob', 'user', 'hey', 2000.0)"
        )
        conn.commit()
        return conn

    def test_verify_present_false_when_backfill_incomplete(self):
        """Column EXISTS but rows are unbackfilled → verify_present must
        return False.  This is the load-bearing semantic: bootstrap MUST
        leave this migration unstamped so the runner finishes the
        backfill."""
        conn = self._conn_with_unbackfilled_rows()
        v9 = next(m for m in _fm.MIGRATIONS if m[0] == 9)
        # Column exists (v=7 applied) but rows are NULL — NOT yet present.
        assert v9[4](conn) is False, (
            "verify_present must return False when column exists but "
            "rows are unbackfilled — otherwise bootstrap stamps "
            "is_initial=1 and the backfill never runs"
        )

    def test_verify_post_raises_when_backfill_incomplete(self):
        """verify_post is STRONGER than verify_present: it asserts every
        row has been backfilled, not just that the column exists."""
        conn = self._conn_with_unbackfilled_rows()
        v9 = next(m for m in _fm.MIGRATIONS if m[0] == 9)
        with pytest.raises(RuntimeError, match="backfill incomplete"):
            v9[3](conn)

    def test_apply_then_verify_post_and_present_both_pass(self):
        conn = self._conn_with_unbackfilled_rows()
        v9 = next(m for m in _fm.MIGRATIONS if m[0] == 9)
        _, _, apply_fn, verify_post, verify_present = v9
        apply_fn(conn)
        verify_post(conn)  # no AssertionError
        assert verify_present(conn) is True
        # Deterministic shape check on the backfilled values.
        rows = list(conn.execute(
            "SELECT person_id, room_session_id, audience_ids "
            "FROM conversation_log ORDER BY id"
        ))
        for pid, rsid, aud_json in rows:
            assert rsid is not None
            assert rsid.startswith(f"{pid}_"), (
                f"deterministic rsid shape violated: {rsid!r} for pid={pid}"
            )
            assert json.loads(aud_json) == [pid]


class TestFacesV10DropConversationMemory:
    """v=10: destructive op — DROP TABLE conversation_memory.  Only
    destructive migration in the entire faces.db surface."""

    def test_verify_present_true_when_legacy_table_already_gone(self):
        """A DB that never had conversation_memory (post-S24 fresh)
        returns verify_present=True without running anything."""
        conn = _fresh_conn()
        # No conversation_memory table — fresh shape.
        v10 = next(m for m in _fm.MIGRATIONS if m[0] == 10)
        assert v10[4](conn) is True

    def test_verify_present_false_when_legacy_table_present(self):
        conn = _faces_legacy_conn()  # creates conversation_memory
        v10 = next(m for m in _fm.MIGRATIONS if m[0] == 10)
        assert v10[4](conn) is False

    def test_apply_drops_and_verify_post_passes(self):
        conn = _faces_legacy_conn()
        v10 = next(m for m in _fm.MIGRATIONS if m[0] == 10)
        _, _, apply_fn, verify_post, verify_present = v10
        apply_fn(conn)
        verify_post(conn)
        assert verify_present(conn) is True


# ---------------------------------------------------------------------------
# Non-trivial brain.db migrations
# ---------------------------------------------------------------------------

class TestBrainV3KnowledgeValidAtBackfill:
    """v=3: ALTER + UPDATE backfill.  Adds knowledge.valid_at and
    populates from created_at for legacy rows."""

    def _legacy_conn(self) -> sqlite3.Connection:
        conn = _fresh_conn()
        conn.executescript("""
            CREATE TABLE knowledge (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                entity     TEXT NOT NULL,
                value      TEXT NOT NULL,
                created_at REAL NOT NULL
            );
        """)
        conn.execute(
            "INSERT INTO knowledge(entity, value, created_at) "
            "VALUES ('alice', 'lives_in_x', 1000.0)"
        )
        conn.execute(
            "INSERT INTO knowledge(entity, value, created_at) "
            "VALUES ('bob', 'works_at_y', 1100.0)"
        )
        conn.commit()
        return conn

    def test_verify_present_false_pre_apply(self):
        conn = self._legacy_conn()
        v3 = next(m for m in _bm.MIGRATIONS if m[0] == 3)
        assert v3[4](conn) is False

    def test_verify_post_fails_when_only_column_added_no_backfill(self):
        """Operator manually ran ALTER but forgot UPDATE — verify_post
        must detect the incomplete state."""
        conn = self._legacy_conn()
        conn.execute("ALTER TABLE knowledge ADD COLUMN valid_at REAL")
        v3 = next(m for m in _bm.MIGRATIONS if m[0] == 3)
        with pytest.raises(RuntimeError, match="backfill incomplete"):
            v3[3](conn)

    def test_apply_then_verify_post_succeeds_and_backfill_lands(self):
        conn = self._legacy_conn()
        v3 = next(m for m in _bm.MIGRATIONS if m[0] == 3)
        _, _, apply_fn, verify_post, verify_present = v3
        apply_fn(conn)
        verify_post(conn)
        assert verify_present(conn) is True
        # Spot-check: valid_at populated from created_at.
        rows = list(conn.execute("SELECT created_at, valid_at FROM knowledge"))
        for created_at, valid_at in rows:
            assert valid_at == created_at, (
                f"backfill failed: valid_at={valid_at!r} != created_at={created_at!r}"
            )


class TestBrainV9PrivacyLevelMultiArtifact:
    """v=9: multi-artifact migration — column + index.  Both must be
    present for verify_present to return True."""

    def _conn(self) -> sqlite3.Connection:
        conn = _fresh_conn()
        conn.executescript("""
            CREATE TABLE knowledge (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                entity    TEXT NOT NULL,
                value     TEXT NOT NULL,
                person_id TEXT
            );
        """)
        return conn

    def test_verify_present_false_when_only_column_exists(self):
        """Column landed but index missing → not yet 'applied'."""
        conn = self._conn()
        conn.execute(
            "ALTER TABLE knowledge ADD COLUMN privacy_level TEXT NOT NULL DEFAULT 'public'"
        )
        v9 = next(m for m in _bm.MIGRATIONS if m[0] == 9)
        assert v9[4](conn) is False

    def test_verify_present_true_after_apply(self):
        conn = self._conn()
        v9 = next(m for m in _bm.MIGRATIONS if m[0] == 9)
        v9[2](conn)
        v9[3](conn)
        assert v9[4](conn) is True


class TestBrainV10PrivacyLevelRemediation:
    """v=10: DATA BACKFILL — privacy_level NULL→personal + legacy
    'private'→personal remediation.  The other canonical example of
    verify_post stronger than verify_present."""

    def _conn_with_legacy_rows(self) -> sqlite3.Connection:
        conn = _fresh_conn()
        conn.executescript("""
            CREATE TABLE knowledge (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                entity        TEXT NOT NULL,
                value         TEXT NOT NULL,
                privacy_level TEXT
            );
        """)
        conn.execute(
            "INSERT INTO knowledge(entity, value, privacy_level) "
            "VALUES ('alice', 'name', 'public')"
        )
        conn.execute(
            "INSERT INTO knowledge(entity, value, privacy_level) "
            "VALUES ('bob', 'health_condition', 'private')"
        )
        conn.execute(
            "INSERT INTO knowledge(entity, value, privacy_level) "
            "VALUES ('carol', 'mood', NULL)"
        )
        conn.commit()
        return conn

    def test_verify_present_false_when_legacy_values_remain(self):
        """Column exists but legacy 'private' / NULL values present →
        verify_present must return False so runner finishes remediation."""
        conn = self._conn_with_legacy_rows()
        v10 = next(m for m in _bm.MIGRATIONS if m[0] == 10)
        assert v10[4](conn) is False

    def test_verify_post_fails_when_remediation_incomplete(self):
        conn = self._conn_with_legacy_rows()
        v10 = next(m for m in _bm.MIGRATIONS if m[0] == 10)
        with pytest.raises(RuntimeError, match="remediation incomplete"):
            v10[3](conn)

    def test_apply_remediates_both_legacy_states(self):
        conn = self._conn_with_legacy_rows()
        v10 = next(m for m in _bm.MIGRATIONS if m[0] == 10)
        _, _, apply_fn, verify_post, verify_present = v10
        apply_fn(conn)
        verify_post(conn)
        assert verify_present(conn) is True
        # Spot-check: 'private' and NULL both → 'personal'.
        rows = dict(conn.execute("SELECT entity, privacy_level FROM knowledge"))
        assert rows["alice"] == "public", "public must be untouched"
        assert rows["bob"] == "personal", "legacy 'private' must migrate to 'personal'"
        assert rows["carol"] == "personal", "NULL must migrate to 'personal'"
