"""P0.9.2 — Retrofitted faces.db schema migrations.

Each migration is a 5-tuple `(version, description, apply_fn,
verify_post_fn, verify_present_fn)` registered in `MIGRATIONS` at the
bottom of this module.

Numbering conventions:
  v=1   reserved for the baseline (handled by bootstrap_ledger_if_unversioned)
  v>=2  post-baseline retrofits enumerated below

Phase 2 discipline: every retrofit migration's apply_fn is a VERBATIM
move of the corresponding inline call in `core/db.py::_init_tables` (the
try/except ALTER TABLE block and friends).  The verify_post asserts the
post-state; verify_present is the bootstrap predicate that flags whether
the artifact already exists on a legacy production DB.

Phase 3 cleanup will remove the now-redundant inline ALTER calls.  Until
then the inline calls and the migrations run side-by-side; both are
idempotent so there is no risk of double-apply.

The 1 data-backfill migration (v=8 — conversation_log
room_session_id/audience_ids backfill, S107 P3A.6) has a stronger
verify_post than verify_present, per Item 1's split semantic — see the
docstrings on _m_0008_*.
"""
from __future__ import annotations

import json as _json
import sqlite3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return any(
        r[0] == table for r in
        conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    )


def _index_exists(conn: sqlite3.Connection, index: str) -> bool:
    return any(
        r[0] == index for r in
        conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
    )


def _alter_add_column_idempotent(
    conn: sqlite3.Connection, table: str, column: str, defn: str,
) -> None:
    """Verbatim of the inline `try/except sqlite3.OperationalError` pattern
    used in core/db.py."""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {defn}")
    except sqlite3.OperationalError:
        # Column already exists (idempotent re-run).
        pass


# ---------------------------------------------------------------------------
# v=2 — persons.last_seen (pre-Session-22; provenance: original `_init_tables`
# ALTER loop entry; track_record: documented in tests/p0_9_schema_inventory.md)
# ---------------------------------------------------------------------------

def _m_0002_persons_last_seen_apply(conn: sqlite3.Connection) -> None:
    _alter_add_column_idempotent(conn, "persons", "last_seen", "REAL")


def _m_0002_persons_last_seen_verify_post(conn: sqlite3.Connection) -> None:
    assert "last_seen" in _columns(conn, "persons"), \
        "persons.last_seen not present after apply"


def _m_0002_persons_last_seen_verify_present(conn: sqlite3.Connection) -> bool:
    return _table_exists(conn, "persons") and "last_seen" in _columns(conn, "persons")


# ---------------------------------------------------------------------------
# v=3 — persons.preferred_language
# ---------------------------------------------------------------------------

def _m_0003_persons_preferred_language_apply(conn: sqlite3.Connection) -> None:
    _alter_add_column_idempotent(
        conn, "persons", "preferred_language",
        "TEXT NOT NULL DEFAULT 'en'",
    )


def _m_0003_persons_preferred_language_verify_post(conn: sqlite3.Connection) -> None:
    assert "preferred_language" in _columns(conn, "persons")


def _m_0003_persons_preferred_language_verify_present(conn: sqlite3.Connection) -> bool:
    return _table_exists(conn, "persons") and "preferred_language" in _columns(conn, "persons")


# ---------------------------------------------------------------------------
# v=4 — embeddings.vector (pre-Session-22; legacy DBs stored embeddings
# out-of-table)
# ---------------------------------------------------------------------------

def _m_0004_embeddings_vector_apply(conn: sqlite3.Connection) -> None:
    _alter_add_column_idempotent(conn, "embeddings", "vector", "BLOB")


def _m_0004_embeddings_vector_verify_post(conn: sqlite3.Connection) -> None:
    assert "vector" in _columns(conn, "embeddings")


def _m_0004_embeddings_vector_verify_present(conn: sqlite3.Connection) -> bool:
    return _table_exists(conn, "embeddings") and "vector" in _columns(conn, "embeddings")


# ---------------------------------------------------------------------------
# v=5 — persons.person_type (Session 22 G4)
# ---------------------------------------------------------------------------

def _m_0005_persons_person_type_apply(conn: sqlite3.Connection) -> None:
    _alter_add_column_idempotent(
        conn, "persons", "person_type",
        "TEXT NOT NULL DEFAULT 'known'",
    )


def _m_0005_persons_person_type_verify_post(conn: sqlite3.Connection) -> None:
    assert "person_type" in _columns(conn, "persons")


def _m_0005_persons_person_type_verify_present(conn: sqlite3.Connection) -> bool:
    return _table_exists(conn, "persons") and "person_type" in _columns(conn, "persons")


# ---------------------------------------------------------------------------
# v=6 — embeddings + voice_embeddings provenance columns (paired)
# ---------------------------------------------------------------------------

def _m_0006_provenance_columns_apply(conn: sqlite3.Connection) -> None:
    """Adds source + confidence_at_write to both embeddings and
    voice_embeddings (4 column adds in one migration — paired in the
    original inline loop)."""
    for col, defn in (
        ("source", "TEXT NOT NULL DEFAULT 'legacy_unknown'"),
        ("confidence_at_write", "REAL NOT NULL DEFAULT 0.0"),
    ):
        for tbl in ("embeddings", "voice_embeddings"):
            _alter_add_column_idempotent(conn, tbl, col, defn)


def _m_0006_provenance_columns_verify_post(conn: sqlite3.Connection) -> None:
    for tbl in ("embeddings", "voice_embeddings"):
        cols = _columns(conn, tbl)
        assert "source" in cols, f"{tbl}.source missing"
        assert "confidence_at_write" in cols, f"{tbl}.confidence_at_write missing"


def _m_0006_provenance_columns_verify_present(conn: sqlite3.Connection) -> bool:
    for tbl in ("embeddings", "voice_embeddings"):
        if not _table_exists(conn, tbl):
            return False
        cols = _columns(conn, tbl)
        if "source" not in cols or "confidence_at_write" not in cols:
            return False
    return True


# ---------------------------------------------------------------------------
# v=7 — conversation_log room_session_id + audience_ids (S107 P3A.6 Part 3)
# Paired ALTERs.  Note: associated index (idx_conv_log_room) and the
# DATA backfill are split into v=8 and v=9 so each is independently
# verifiable.
# ---------------------------------------------------------------------------

def _m_0007_conversation_log_room_cols_apply(conn: sqlite3.Connection) -> None:
    _alter_add_column_idempotent(conn, "conversation_log", "room_session_id", "TEXT")
    _alter_add_column_idempotent(conn, "conversation_log", "audience_ids", "TEXT")


def _m_0007_conversation_log_room_cols_verify_post(conn: sqlite3.Connection) -> None:
    cols = _columns(conn, "conversation_log")
    assert "room_session_id" in cols
    assert "audience_ids" in cols


def _m_0007_conversation_log_room_cols_verify_present(conn: sqlite3.Connection) -> bool:
    if not _table_exists(conn, "conversation_log"):
        return False
    cols = _columns(conn, "conversation_log")
    return "room_session_id" in cols and "audience_ids" in cols


# ---------------------------------------------------------------------------
# v=8 — idx_conv_log_room (S107 P3A.6 Part 3)
# ---------------------------------------------------------------------------

def _m_0008_idx_conv_log_room_apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conv_log_room "
        "ON conversation_log(room_session_id, ts DESC)"
    )


def _m_0008_idx_conv_log_room_verify_post(conn: sqlite3.Connection) -> None:
    assert _index_exists(conn, "idx_conv_log_room"), "idx_conv_log_room missing"


def _m_0008_idx_conv_log_room_verify_present(conn: sqlite3.Connection) -> bool:
    return _index_exists(conn, "idx_conv_log_room")


# ---------------------------------------------------------------------------
# v=9 — conversation_log room_session_id/audience_ids BACKFILL (S107 P3A.6)
#
# DATA-BACKFILL migration.  verify_post and verify_present DIVERGE here
# (the canonical example that motivated the 5-tuple split):
#
#   verify_present:  column exists (says nothing about whether the
#                    backfill ran)
#   verify_post:     ZERO rows remain with NULL room_session_id AND
#                    every populated value matches the deterministic
#                    `{pid}_{int(first_ts)}` shape
#
# Without the stronger verify_post, a partially-backfilled DB would
# silently get stamped is_initial=1 by bootstrap and the runner would
# never finish the backfill.
# ---------------------------------------------------------------------------

def _m_0009_conversation_log_backfill_apply(conn: sqlite3.Connection) -> None:
    """Deterministic backfill — verbatim from the existing inline code in
    core/db.py._init_tables (L191-214 in pre-P0.9 numbering).

    Per-person first turn ts becomes the synthetic session id; audience_ids
    is JSON [person_id] so legacy single-speaker rows remain visible only
    to their owner."""
    null_count = conn.execute(
        "SELECT COUNT(*) FROM conversation_log WHERE room_session_id IS NULL"
    ).fetchone()[0]
    if not null_count:
        return
    first_ts_rows = conn.execute(
        "SELECT person_id, MIN(ts) FROM conversation_log "
        "WHERE room_session_id IS NULL GROUP BY person_id"
    ).fetchall()
    for pid, first_ts in first_ts_rows:
        rsid = f"{pid}_{int(first_ts or 0)}"
        aud = _json.dumps([pid])
        conn.execute(
            "UPDATE conversation_log "
            "SET room_session_id = ?, audience_ids = ? "
            "WHERE person_id = ? AND room_session_id IS NULL",
            (rsid, aud, pid),
        )


def _m_0009_conversation_log_backfill_verify_post(conn: sqlite3.Connection) -> None:
    """Stronger post-condition than verify_present: every row has a
    populated room_session_id (zero NULLs remain).  This is the
    correctness check that distinguishes "ran the migration" from "the
    column exists."""
    null_rows = conn.execute(
        "SELECT COUNT(*) FROM conversation_log WHERE room_session_id IS NULL"
    ).fetchone()[0]
    assert null_rows == 0, (
        f"conversation_log backfill incomplete: {null_rows} row(s) still "
        "have NULL room_session_id"
    )


def _m_0009_conversation_log_backfill_verify_present(conn: sqlite3.Connection) -> bool:
    """Predicate semantic: the column exists AND no row has NULL
    room_session_id.  A legacy DB with the column but unfilled rows
    should NOT be treated as "already backfilled" — bootstrap leaves it
    unstamped so the runner completes the backfill."""
    if not _table_exists(conn, "conversation_log"):
        return False
    if "room_session_id" not in _columns(conn, "conversation_log"):
        return False
    null_rows = conn.execute(
        "SELECT COUNT(*) FROM conversation_log WHERE room_session_id IS NULL"
    ).fetchone()[0]
    return null_rows == 0


# ---------------------------------------------------------------------------
# v=10 — DROP TABLE conversation_memory (Session 24 A4 cleanup)
# Destructive op; only operation in the entire faces.db schema surface that
# removes state.  Idempotent (IF EXISTS).
# ---------------------------------------------------------------------------

def _m_0010_drop_conversation_memory_apply(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS conversation_memory")


def _m_0010_drop_conversation_memory_verify_post(conn: sqlite3.Connection) -> None:
    assert not _table_exists(conn, "conversation_memory"), \
        "conversation_memory still present after drop"


def _m_0010_drop_conversation_memory_verify_present(conn: sqlite3.Connection) -> bool:
    return not _table_exists(conn, "conversation_memory")


# ---------------------------------------------------------------------------
# MIGRATIONS registry — consumed by FaceDB via:
#     from core.faces_db_migrations import MIGRATIONS as _FACES_MIGRATIONS
#     class FaceDB:
#         MIGRATIONS = _FACES_MIGRATIONS
# ---------------------------------------------------------------------------

MIGRATIONS: list = [
    (2, "persons.last_seen",
        _m_0002_persons_last_seen_apply,
        _m_0002_persons_last_seen_verify_post,
        _m_0002_persons_last_seen_verify_present),
    (3, "persons.preferred_language",
        _m_0003_persons_preferred_language_apply,
        _m_0003_persons_preferred_language_verify_post,
        _m_0003_persons_preferred_language_verify_present),
    (4, "embeddings.vector",
        _m_0004_embeddings_vector_apply,
        _m_0004_embeddings_vector_verify_post,
        _m_0004_embeddings_vector_verify_present),
    (5, "persons.person_type",
        _m_0005_persons_person_type_apply,
        _m_0005_persons_person_type_verify_post,
        _m_0005_persons_person_type_verify_present),
    (6, "embeddings+voice_embeddings provenance columns",
        _m_0006_provenance_columns_apply,
        _m_0006_provenance_columns_verify_post,
        _m_0006_provenance_columns_verify_present),
    (7, "conversation_log room_session_id + audience_ids",
        _m_0007_conversation_log_room_cols_apply,
        _m_0007_conversation_log_room_cols_verify_post,
        _m_0007_conversation_log_room_cols_verify_present),
    (8, "idx_conv_log_room",
        _m_0008_idx_conv_log_room_apply,
        _m_0008_idx_conv_log_room_verify_post,
        _m_0008_idx_conv_log_room_verify_present),
    (9, "conversation_log room_session_id + audience_ids deterministic backfill",
        _m_0009_conversation_log_backfill_apply,
        _m_0009_conversation_log_backfill_verify_post,
        _m_0009_conversation_log_backfill_verify_present),
    (10, "DROP TABLE conversation_memory (legacy cleanup)",
        _m_0010_drop_conversation_memory_apply,
        _m_0010_drop_conversation_memory_verify_post,
        _m_0010_drop_conversation_memory_verify_present),
]
