"""P0.9.2 — Retrofitted brain.db schema migrations.

Each migration is a 5-tuple `(version, description, apply_fn,
verify_post_fn, verify_present_fn)` registered in `MIGRATIONS` at the
bottom of this module.

Phase 2 discipline: every retrofit migration's apply_fn is a VERBATIM
move of the corresponding `_migrate()` body in `core/brain_agent.py`.
Phase 3 cleanup removes the now-redundant inline calls.

The 1 data-backfill migration (v=10 — privacy_level NULL→personal +
legacy 'private'→personal remediation, S95 P3A.4) has a stronger
verify_post than verify_present — see the docstrings on _m_0010_*.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import sqlite3


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


# ---------------------------------------------------------------------------
# v=2 — knowledge.embedding + schema_catalog.embedding (Phase 3 / S15)
# ---------------------------------------------------------------------------

def _m_0002_embedding_columns_apply(conn: sqlite3.Connection) -> None:
    for table in ("knowledge", "schema_catalog"):
        cols = _columns(conn, table)
        if "embedding" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN embedding BLOB")


def _m_0002_embedding_columns_verify_post(conn: sqlite3.Connection) -> None:
    for table in ("knowledge", "schema_catalog"):
        if not ('embedding' in _columns(conn, table)):
            raise RuntimeError(f'{table}.embedding missing')


def _m_0002_embedding_columns_verify_present(conn: sqlite3.Connection) -> bool:
    for table in ("knowledge", "schema_catalog"):
        if not _table_exists(conn, table):
            return False
        if "embedding" not in _columns(conn, table):
            return False
    return True


# ---------------------------------------------------------------------------
# v=3 — knowledge.valid_at + UPDATE backfill from created_at (Phase 5)
# Mini data-backfill: apply ALSO updates legacy rows so valid_at is
# never NULL when the column exists.
# ---------------------------------------------------------------------------

def _m_0003_knowledge_valid_at_apply(conn: sqlite3.Connection) -> None:
    cols = _columns(conn, "knowledge")
    if "valid_at" not in cols:
        conn.execute("ALTER TABLE knowledge ADD COLUMN valid_at REAL")
        conn.execute("UPDATE knowledge SET valid_at = created_at WHERE valid_at IS NULL")


def _m_0003_knowledge_valid_at_verify_post(conn: sqlite3.Connection) -> None:
    if not ('valid_at' in _columns(conn, 'knowledge')):
        raise RuntimeError("assertion failed: 'valid_at' in _columns(conn, 'knowledge')")
    # Stronger post-condition: backfill must have landed on legacy rows.
    null_legacy = conn.execute(
        "SELECT COUNT(*) FROM knowledge WHERE valid_at IS NULL AND created_at IS NOT NULL"
    ).fetchone()[0]
    if not (null_legacy == 0):
        raise RuntimeError(f'valid_at backfill incomplete: {null_legacy} legacy row(s) still NULL')


def _m_0003_knowledge_valid_at_verify_present(conn: sqlite3.Connection) -> bool:
    if not _table_exists(conn, "knowledge"):
        return False
    if "valid_at" not in _columns(conn, "knowledge"):
        return False
    null_legacy = conn.execute(
        "SELECT COUNT(*) FROM knowledge WHERE valid_at IS NULL AND created_at IS NOT NULL"
    ).fetchone()[0]
    return null_legacy == 0


# ---------------------------------------------------------------------------
# v=4 — knowledge.last_confirmed_at (Phase 5 Item 6 SM-2 anchor)
# ---------------------------------------------------------------------------

def _m_0004_knowledge_last_confirmed_at_apply(conn: sqlite3.Connection) -> None:
    if "last_confirmed_at" not in _columns(conn, "knowledge"):
        conn.execute("ALTER TABLE knowledge ADD COLUMN last_confirmed_at REAL")


def _m_0004_knowledge_last_confirmed_at_verify_post(conn: sqlite3.Connection) -> None:
    if not ('last_confirmed_at' in _columns(conn, 'knowledge')):
        raise RuntimeError("assertion failed: 'last_confirmed_at' in _columns(conn, 'knowledge')")


def _m_0004_knowledge_last_confirmed_at_verify_present(conn: sqlite3.Connection) -> bool:
    return _table_exists(conn, "knowledge") and "last_confirmed_at" in _columns(conn, "knowledge")


# ---------------------------------------------------------------------------
# v=5 — prompt_prefs.friction_count (Phase 5 / S20)
# ---------------------------------------------------------------------------

def _m_0005_prompt_prefs_friction_count_apply(conn: sqlite3.Connection) -> None:
    if "friction_count" not in _columns(conn, "prompt_prefs"):
        conn.execute(
            "ALTER TABLE prompt_prefs ADD COLUMN friction_count INTEGER NOT NULL DEFAULT 0"
        )


def _m_0005_prompt_prefs_friction_count_verify_post(conn: sqlite3.Connection) -> None:
    if not ('friction_count' in _columns(conn, 'prompt_prefs')):
        raise RuntimeError("assertion failed: 'friction_count' in _columns(conn, 'prompt_prefs')")


def _m_0005_prompt_prefs_friction_count_verify_present(conn: sqlite3.Connection) -> bool:
    return _table_exists(conn, "prompt_prefs") and "friction_count" in _columns(conn, "prompt_prefs")


# ---------------------------------------------------------------------------
# v=6 — prompt_prefs.embedding (Session 69 Bug L)
# ---------------------------------------------------------------------------

def _m_0006_prompt_prefs_embedding_apply(conn: sqlite3.Connection) -> None:
    if "embedding" not in _columns(conn, "prompt_prefs"):
        conn.execute("ALTER TABLE prompt_prefs ADD COLUMN embedding BLOB")


def _m_0006_prompt_prefs_embedding_verify_post(conn: sqlite3.Connection) -> None:
    if not ('embedding' in _columns(conn, 'prompt_prefs')):
        raise RuntimeError("assertion failed: 'embedding' in _columns(conn, 'prompt_prefs')")


def _m_0006_prompt_prefs_embedding_verify_present(conn: sqlite3.Connection) -> bool:
    return _table_exists(conn, "prompt_prefs") and "embedding" in _columns(conn, "prompt_prefs")


# ---------------------------------------------------------------------------
# v=7 — brain_state.graph_schema_version
# ---------------------------------------------------------------------------

def _m_0007_graph_schema_version_apply(conn: sqlite3.Connection) -> None:
    if "graph_schema_version" not in _columns(conn, "brain_state"):
        conn.execute(
            "ALTER TABLE brain_state ADD COLUMN "
            "graph_schema_version INTEGER NOT NULL DEFAULT 0"
        )


def _m_0007_graph_schema_version_verify_post(conn: sqlite3.Connection) -> None:
    if not ('graph_schema_version' in _columns(conn, 'brain_state')):
        raise RuntimeError("assertion failed: 'graph_schema_version' in _columns(conn, 'brain_state')")


def _m_0007_graph_schema_version_verify_present(conn: sqlite3.Connection) -> bool:
    return _table_exists(conn, "brain_state") and "graph_schema_version" in _columns(conn, "brain_state")


# ---------------------------------------------------------------------------
# v=8 — shadow_persons.mention_count (Session 97 Fix 3 / canary S114)
# ---------------------------------------------------------------------------

def _m_0008_shadow_mention_count_apply(conn: sqlite3.Connection) -> None:
    if "mention_count" not in _columns(conn, "shadow_persons"):
        conn.execute(
            "ALTER TABLE shadow_persons ADD COLUMN mention_count INTEGER NOT NULL DEFAULT 1"
        )


def _m_0008_shadow_mention_count_verify_post(conn: sqlite3.Connection) -> None:
    if not ('mention_count' in _columns(conn, 'shadow_persons')):
        raise RuntimeError("assertion failed: 'mention_count' in _columns(conn, 'shadow_persons')")


def _m_0008_shadow_mention_count_verify_present(conn: sqlite3.Connection) -> bool:
    return _table_exists(conn, "shadow_persons") and "mention_count" in _columns(conn, "shadow_persons")


# ---------------------------------------------------------------------------
# v=9 — knowledge.privacy_level + idx_knowledge_privacy_person (S95 P3A.1)
# Multi-artifact migration: column add + index create.  Both must succeed
# for the migration to be considered applied.
# ---------------------------------------------------------------------------

def _m_0009_knowledge_privacy_level_apply(conn: sqlite3.Connection) -> None:
    if "privacy_level" not in _columns(conn, "knowledge"):
        conn.execute(
            "ALTER TABLE knowledge ADD COLUMN privacy_level TEXT NOT NULL DEFAULT 'public'"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_knowledge_privacy_person "
        "ON knowledge(privacy_level, person_id)"
    )


def _m_0009_knowledge_privacy_level_verify_post(conn: sqlite3.Connection) -> None:
    if not ('privacy_level' in _columns(conn, 'knowledge')):
        raise RuntimeError('privacy_level column missing')
    if not (_index_exists(conn, 'idx_knowledge_privacy_person')):
        raise RuntimeError('idx_knowledge_privacy_person missing')


def _m_0009_knowledge_privacy_level_verify_present(conn: sqlite3.Connection) -> bool:
    if not _table_exists(conn, "knowledge"):
        return False
    if "privacy_level" not in _columns(conn, "knowledge"):
        return False
    return _index_exists(conn, "idx_knowledge_privacy_person")


# ---------------------------------------------------------------------------
# v=10 — privacy_level remediation backfill (S95 P3A.4)
#
# DATA-BACKFILL migration.  Two disjoint legacy states need remediation:
#   (1) NULL rows — defensive belt-and-braces (column has DEFAULT 'public'
#       so NULL shouldn't appear, but hand-edits or older schema edges
#       could produce them)
#   (2) legacy 'private' rows (pre-4-tier 2-tier owner-only semantics)
#       → map 1:1 to new 4-tier 'personal'.  Critical: 'private' would
#       be INVISIBLE under the new _visibility_clause and hide rows
#       from their own owners.
#
# verify_post: zero NULL rows AND zero legacy 'private' rows remain.
# verify_present: column exists AND zero legacy 'private' / NULL rows.
# These genuinely differ — pre-remediation DB might have the column but
# unremediated rows; bootstrap MUST leave it unstamped so the runner
# completes the backfill.
# ---------------------------------------------------------------------------

def _m_0010_privacy_level_remediation_apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        "UPDATE knowledge SET privacy_level = 'personal' WHERE privacy_level IS NULL"
    )
    conn.execute(
        "UPDATE knowledge SET privacy_level = 'personal' WHERE privacy_level = 'private'"
    )


def _m_0010_privacy_level_remediation_verify_post(conn: sqlite3.Connection) -> None:
    null_rows = conn.execute(
        "SELECT COUNT(*) FROM knowledge WHERE privacy_level IS NULL"
    ).fetchone()[0]
    legacy_private = conn.execute(
        "SELECT COUNT(*) FROM knowledge WHERE privacy_level = 'private'"
    ).fetchone()[0]
    if not (null_rows == 0):
        raise RuntimeError(f'privacy_level remediation incomplete: {null_rows} NULL row(s) remain')
    if not (legacy_private == 0):
        raise RuntimeError(f"privacy_level remediation incomplete: {legacy_private} legacy 'private' row(s) remain (must be migrated to 'personal')")


def _m_0010_privacy_level_remediation_verify_present(conn: sqlite3.Connection) -> bool:
    if not _table_exists(conn, "knowledge"):
        return False
    if "privacy_level" not in _columns(conn, "knowledge"):
        return False
    null_rows = conn.execute(
        "SELECT COUNT(*) FROM knowledge WHERE privacy_level IS NULL"
    ).fetchone()[0]
    legacy_private = conn.execute(
        "SELECT COUNT(*) FROM knowledge WHERE privacy_level = 'private'"
    ).fetchone()[0]
    return null_rows == 0 and legacy_private == 0


# ---------------------------------------------------------------------------
# v=11 — intent_divergences.mode (Session 119 Phase 5)
# ---------------------------------------------------------------------------

def _m_0011_intent_divergences_mode_apply(conn: sqlite3.Connection) -> None:
    if "mode" not in _columns(conn, "intent_divergences"):
        conn.execute(
            "ALTER TABLE intent_divergences ADD COLUMN mode TEXT NOT NULL DEFAULT 'gate'"
        )


def _m_0011_intent_divergences_mode_verify_post(conn: sqlite3.Connection) -> None:
    if not ('mode' in _columns(conn, 'intent_divergences')):
        raise RuntimeError("assertion failed: 'mode' in _columns(conn, 'intent_divergences')")


def _m_0011_intent_divergences_mode_verify_present(conn: sqlite3.Connection) -> bool:
    return _table_exists(conn, "intent_divergences") and "mode" in _columns(conn, "intent_divergences")


# ---------------------------------------------------------------------------
# v=12 — P0.0.7 event_log table for event-sourcing + replay harness
# ---------------------------------------------------------------------------

def _m_0012_create_event_log_apply(conn: sqlite3.Connection) -> None:
    """P0.0.7 — CREATE TABLE event_log + 3 indexes.

    Schema per Phase 0 audit Deliverable A. Plan v2 R3 locks this as
    version 12 (verified against the existing v=2 through v=11 chain).
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            session_id TEXT,
            room_session_id TEXT,
            event_type TEXT NOT NULL,
            schema_version INTEGER NOT NULL DEFAULT 0,
            payload BLOB NOT NULL,
            parent_event_id INTEGER REFERENCES event_log(id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_log_ts ON event_log(ts DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_log_session ON event_log(session_id, ts)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_log_room ON event_log(room_session_id, ts)"
    )


def _m_0012_create_event_log_verify_post(conn: sqlite3.Connection) -> None:
    """Assert event_log table + 3 indexes exist with expected columns."""
    if not (_table_exists(conn, 'event_log')):
        raise RuntimeError('event_log table missing post-apply')
    cols = _columns(conn, "event_log")
    expected = {
        "id", "ts", "session_id", "room_session_id", "event_type",
        "schema_version", "payload", "parent_event_id",
    }
    missing = expected - cols
    if not (not missing):
        raise RuntimeError(f'event_log missing columns: {sorted(missing)}')
    if not (_index_exists(conn, 'idx_event_log_ts')):
        raise RuntimeError('idx_event_log_ts missing')
    if not (_index_exists(conn, 'idx_event_log_session')):
        raise RuntimeError('idx_event_log_session missing')
    if not (_index_exists(conn, 'idx_event_log_room')):
        raise RuntimeError('idx_event_log_room missing')


def _m_0012_create_event_log_verify_present(conn: sqlite3.Connection) -> bool:
    """Bootstrap predicate: True if event_log already exists on a legacy DB."""
    return _table_exists(conn, "event_log")


# ---------------------------------------------------------------------------
# MIGRATIONS registry
# ---------------------------------------------------------------------------

MIGRATIONS: list = [
    (2, "knowledge + schema_catalog .embedding",
        _m_0002_embedding_columns_apply,
        _m_0002_embedding_columns_verify_post,
        _m_0002_embedding_columns_verify_present),
    (3, "knowledge.valid_at + backfill from created_at",
        _m_0003_knowledge_valid_at_apply,
        _m_0003_knowledge_valid_at_verify_post,
        _m_0003_knowledge_valid_at_verify_present),
    (4, "knowledge.last_confirmed_at",
        _m_0004_knowledge_last_confirmed_at_apply,
        _m_0004_knowledge_last_confirmed_at_verify_post,
        _m_0004_knowledge_last_confirmed_at_verify_present),
    (5, "prompt_prefs.friction_count",
        _m_0005_prompt_prefs_friction_count_apply,
        _m_0005_prompt_prefs_friction_count_verify_post,
        _m_0005_prompt_prefs_friction_count_verify_present),
    (6, "prompt_prefs.embedding",
        _m_0006_prompt_prefs_embedding_apply,
        _m_0006_prompt_prefs_embedding_verify_post,
        _m_0006_prompt_prefs_embedding_verify_present),
    (7, "brain_state.graph_schema_version",
        _m_0007_graph_schema_version_apply,
        _m_0007_graph_schema_version_verify_post,
        _m_0007_graph_schema_version_verify_present),
    (8, "shadow_persons.mention_count",
        _m_0008_shadow_mention_count_apply,
        _m_0008_shadow_mention_count_verify_post,
        _m_0008_shadow_mention_count_verify_present),
    (9, "knowledge.privacy_level + idx_knowledge_privacy_person",
        _m_0009_knowledge_privacy_level_apply,
        _m_0009_knowledge_privacy_level_verify_post,
        _m_0009_knowledge_privacy_level_verify_present),
    (10, "privacy_level NULL→personal + legacy 'private'→personal remediation",
        _m_0010_privacy_level_remediation_apply,
        _m_0010_privacy_level_remediation_verify_post,
        _m_0010_privacy_level_remediation_verify_present),
    (11, "intent_divergences.mode",
        _m_0011_intent_divergences_mode_apply,
        _m_0011_intent_divergences_mode_verify_post,
        _m_0011_intent_divergences_mode_verify_present),
    (12, "event_log table + 3 indexes (P0.0.7 event sourcing + replay)",
        _m_0012_create_event_log_apply,
        _m_0012_create_event_log_verify_post,
        _m_0012_create_event_log_verify_present),
]
