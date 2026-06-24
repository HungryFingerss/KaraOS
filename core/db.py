"""
vision/db.py — SQLite + FAISS face database
Stores person metadata in SQLite, embeddings in FAISS index.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import asyncio
import contextlib
import datetime
import re
import shutil
import sqlite3
import threading
import time
from uuid import uuid4
import numpy as np
from pathlib import Path
from typing import Optional
import faiss
from core.config import (
    DB_PATH, FAISS_INDEX_PATH, EMBEDDING_DIM, MAX_EMBEDDINGS,
    FACE_DIVERSITY_THRESHOLD, N_INITIAL_FACE,
    SELF_UPDATE_CENTROID_MIN,
    MAX_VOICE_EMBEDDINGS, VOICE_DIVERSITY_THRESHOLD, N_INITIAL_VOICE,
    BRAIN_DB_PATH, GRAPH_DB_PATH,
    ENROLL_REQUEST_FILE, ENROLL_RESULT_FILE,
    RESET_REQUEST_FILE, RESET_RESULT_FILE,
    FACES_DIR, DEFAULT_SYSTEM_NAME,
    SILENT_OBS_SIMILARITY, SILENT_OBS_RETENTION_DAYS, SILENT_OBS_SCAN_DAYS,
    CONVERSATION_HISTORY_LIMIT,
    CONVERSATION_ARCHIVE_ENABLED, CONVERSATION_ARCHIVE_AFTER_DAYS,
    CONVERSATION_ARCHIVE_RETENTION_DAYS,
    STRANGER_TTL_DAYS,
)
from core import config  # SB.5 Step-2: live attribute access for ENROLLMENT_MODE/RETENTION_MODE gates (from-import-trap)


# P0.S1 D4 — `legacy_unknown` DELETED 2026-05-18 (no production callers; doc-grep
# clean per Plan v2 §1). Every add_embedding call must now declare `source`
# explicitly and pass anti_spoof_verdict=True. Restoring legacy_unknown requires
# explicit architect approval — it's the only backdoor that bypasses the gate.
VALID_EMBEDDING_SOURCES: frozenset[str] = frozenset({
    "enrollment",           # explicit human-supervised capture
    "recognition_update",   # self-update from live recognition
    "progressive_enroll",   # gate-pass during active session
})


def _escape_like_pid(pid: str) -> str:
    """P0.S7 D-A — escape pid for safe substring use in a SQLite LIKE pattern.

    SQLite LIKE treats ``_`` as a single-character wildcard and ``%`` as a
    multi-char wildcard. Every pid in this codebase contains ``_`` (e.g.
    ``jagan_001``, ``stranger_a0d44122``), so a naked pid in a LIKE pattern
    collides with any string of the same length sharing the surrounding
    context (``"jaganX001"``, ``"jaganA001"``, etc.).

    Escape order is LOAD-BEARING:
      1. Backslash first (otherwise steps 2+3 produce double-escaped sequences)
      2. Underscore  → ``\\_``
      3. Percent     → ``\\%``

    The consuming query MUST include the ``ESCAPE '\\'`` clause so SQLite
    recognises backslash as the escape character. Plan v2 §2 CRITICAL 1.
    """
    return (
        pid
        .replace("\\", "\\\\")
        .replace("_", "\\_")
        .replace("%", "\\%")
    )


# P0.S1 D1 — sources whose writes require an explicit anti-spoof verdict.
# Every production call site for these sources MUST pass `anti_spoof_verdict=True`
# to `add_embedding` (the catch-all rejects False/None). Equals
# VALID_EMBEDDING_SOURCES after the D4 deletion — every valid source is gated.
#
# AST invariant `test_every_protected_source_call_site_has_upstream_verify_live`
# scans pipeline.py + enroll.py and asserts every literal-source add_embedding
# call with source ∈ this set has an upstream verify_live(...) in the same
# function body (Plan v2 §3.1).
ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF: frozenset[str] = VALID_EMBEDDING_SOURCES


class FaceDB:
    # P0.9.2 Phase 2: retrofit migrations live in core/faces_db_migrations.py
    # to keep this file focused on FaceDB behavior.  Each entry is a 5-tuple
    # (version, description, apply_fn, verify_post_fn, verify_present_fn) —
    # every migration carries BOTH verify companions (Item 1 invariant).
    from core.faces_db_migrations import MIGRATIONS as _M
    MIGRATIONS: list = _M
    del _M

    def __init__(self, db_path: str = None, faiss_path: "Path | str | None" = None):
        path = db_path if db_path is not None else str(DB_PATH)
        self._db_path = path
        # P0.9.1 Imp-1: isolation_level="IMMEDIATE" makes Python's implicit
        # auto-BEGIN take an IMMEDIATE write lock (instead of DEFERRED),
        # which prevents conflict with the explicit BEGIN IMMEDIATE used
        # by FaceDB.transaction() and core.schema_migrations.apply_migrations.
        self._conn = sqlite3.connect(
            path, check_same_thread=False, isolation_level="IMMEDIATE",
        )
        self._index_lock = threading.RLock()
        # Wave 3 Item 15 — async rebuild state
        self._rebuild_in_progress: bool = False
        self._pending_adds_during_rebuild: list = []  # list of (vec: np.ndarray 1-D, person_id: str, row_id: int) — P0.B2 D3 3-tuple
        self._rebuild_lock = threading.Lock()  # serialize rebuilds; separate from _index_lock
        # Allow callers (tests, dashboard) to supply a separate FAISS path so they
        # never accidentally overwrite the production faces/faiss.index file.
        self._faiss_path: Path = Path(faiss_path) if faiss_path is not None else FAISS_INDEX_PATH
        self._faiss_degraded: bool = False
        self._init_tables()
        # P0.9.1 Phase 1: ledger + pending-migration runner.  Order matters:
        # (1) init_ledger creates schema_migrations table if absent (and
        #     adds is_initial column to pre-P0.9 ledgers in place).
        # (2) bootstrap_ledger_if_unversioned stamps v=1 on legacy DBs.
        # (3) apply_migrations runs any v>=2 entries in MIGRATIONS (empty
        #     in Phase 1; Phase 2 populates).
        from core.schema_migrations import (
            init_ledger as _il, bootstrap_ledger_if_unversioned as _bl,
            apply_migrations as _am,
        )
        _il(self._conn)
        _bl(
            self._conn,
            baseline_description="faces.db initial baseline (pre-P0.9)",
            migrations=self.MIGRATIONS,
            db_label="faces.db",
        )
        _am(self._conn, self.MIGRATIONS, db_label="faces.db")
        self._load_faiss()

    def _init_tables(self):
        # M2: WAL mode — allows dashboard reads to proceed concurrently with
        # pipeline writes without locking either side.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS persons (
                id                 TEXT PRIMARY KEY,
                name               TEXT NOT NULL,
                enrolled_at        REAL NOT NULL,
                photo_path         TEXT,
                last_seen          REAL,
                preferred_language TEXT NOT NULL DEFAULT 'en'
            );
            CREATE TABLE IF NOT EXISTS embeddings (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id         TEXT NOT NULL,
                faiss_idx         INTEGER NOT NULL,
                vector            BLOB,
                captured_at       REAL NOT NULL,
                source            TEXT NOT NULL DEFAULT 'legacy_unknown',
                confidence_at_write REAL NOT NULL DEFAULT 0.0,
                FOREIGN KEY (person_id) REFERENCES persons(id)
            );
            CREATE TABLE IF NOT EXISTS conversation_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id TEXT NOT NULL,
                role      TEXT NOT NULL,
                content   TEXT NOT NULL,
                ts        REAL NOT NULL DEFAULT (unixepoch('now', 'subsec'))
            );
            CREATE TABLE IF NOT EXISTS visitor_log (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                ts   REAL NOT NULL DEFAULT (unixepoch('now', 'subsec')),
                note TEXT   -- free-form text only; no person_id column — delete_person() needs no cleanup here
            );
            CREATE TABLE IF NOT EXISTS voice_embeddings (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id         TEXT NOT NULL,
                vector            BLOB NOT NULL,
                captured_at       REAL NOT NULL,
                source            TEXT NOT NULL DEFAULT 'legacy_unknown',
                confidence_at_write REAL NOT NULL DEFAULT 0.0,
                FOREIGN KEY (person_id) REFERENCES persons(id)
            );
        """)
        self._conn.commit()
        # P0.9.3: provenance-column legacy ALTERs (embeddings/voice_embeddings
        # source + confidence_at_write) retrofitted as migration v=6 — handled
        # by core.schema_migrations.apply_migrations now.  Inline ALTER loop
        # removed (defense-in-depth no longer needed post-validation).

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS system_identity (
                key     TEXT PRIMARY KEY,
                value   TEXT NOT NULL,
                set_by  TEXT,
                set_at  REAL NOT NULL,
                note    TEXT
            )
        """)
        self._conn.execute(
            "INSERT OR IGNORE INTO system_identity (key, value, set_at, note) VALUES (?, ?, ?, ?)",
            ("system_name", DEFAULT_SYSTEM_NAME, time.time(), "default"),
        )
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS silent_observations (
                id               TEXT PRIMARY KEY,
                first_seen       REAL NOT NULL,
                last_seen        REAL NOT NULL,
                duration_secs    REAL NOT NULL DEFAULT 0,
                frame_count      INTEGER NOT NULL DEFAULT 1,
                embedding        BLOB NOT NULL,
                photo_path       TEXT,
                zone             TEXT,
                matched_person_id TEXT,
                created_at       REAL NOT NULL
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_silent_obs_last_seen ON silent_observations(last_seen)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_log_person ON conversation_log(person_id, ts)"
        )
        # P0.9.3: all post-baseline legacy ALTERs (persons.last_seen /
        # preferred_language / person_type, embeddings.vector,
        # conversation_log room_session_id + audience_ids), idx_conv_log_room,
        # the room_session_id deterministic backfill, AND the
        # DROP TABLE IF EXISTS conversation_memory legacy cleanup have all
        # been retrofitted as MIGRATIONS entries v=2 through v=10 in
        # core.faces_db_migrations.  core.schema_migrations.apply_migrations
        # runs them (or bootstrap stamps them is_initial=1 on legacy DBs
        # where they already landed via the pre-P0.9 inline path).  The
        # inline calls that used to live here are now redundant by
        # construction — Phase 2's validation against Jagan's prod DBs
        # confirmed the bootstrap+runner path handles legacy state.
        self._conn.commit()
        if CONVERSATION_ARCHIVE_ENABLED:
            self._init_conversation_archive()
        self._warn_missing_vectors()

    @contextlib.contextmanager
    def transaction(self):
        """BEGIN IMMEDIATE / COMMIT with S65 ROLLBACK race handled.

        Uses BEGIN IMMEDIATE to acquire the write lock upfront. The inner
        try/except around ROLLBACK prevents masking the original exception
        when COMMIT auto-rolls back (constraint violation, lock contention).

        P0.5: used by paired-write methods to make SQL writes durable before
        attempting FAISS updates. Callers must NOT commit inside the with-block.
        """
        prev_isolation = self._conn.isolation_level
        self._conn.isolation_level = None  # autocommit — prevents Python auto-BEGIN clash
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield
                self._conn.execute("COMMIT")
            except Exception:
                # P0.9.1 Imp-2: tightened rollback — re-raise unexpected
                # OperationalErrors instead of swallowing every Exception.
                # Only the S65 "no transaction is active" race is suppressed
                # (SQLite auto-rolled the failed COMMIT before our explicit
                # ROLLBACK could run).
                try:
                    self._conn.execute("ROLLBACK")
                except sqlite3.OperationalError as _rbe:
                    if "no transaction is active" not in str(_rbe).lower():
                        print(f"[FaceDB] rollback failed unexpectedly: {_rbe!r}")
                        raise
                    # else: # RACE: S65 — known race, suppress
                raise
        finally:
            self._conn.isolation_level = prev_isolation

    def _archive_db_path(self) -> "Path":
        """Return the path to the companion conversation archive database."""
        p = Path(self._db_path)
        return p.with_name(p.stem + "_conversation_archive.db")

    def _init_conversation_archive(self) -> None:
        """Create (or migrate) the conversation archive database (Wave 6 Item 21)."""
        archive_path = self._archive_db_path()
        # P0.9.1 Imp-1: IMMEDIATE isolation for all SQLite connections in core.
        _ac = sqlite3.connect(
            str(archive_path), check_same_thread=False,
            isolation_level="IMMEDIATE",
        )
        try:
            _ac.execute("PRAGMA journal_mode=WAL")
            _ac.execute("""
                CREATE TABLE IF NOT EXISTS conversation_log (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    person_id       TEXT NOT NULL,
                    role            TEXT NOT NULL,
                    content         TEXT NOT NULL,
                    ts              REAL NOT NULL DEFAULT (unixepoch('now', 'subsec')),
                    room_session_id TEXT,
                    audience_ids    TEXT
                )
            """)
            _ac.execute(
                "CREATE INDEX IF NOT EXISTS idx_archive_log_person "
                "ON conversation_log(person_id, ts)"
            )
            _ac.commit()
        finally:
            _ac.close()

    def archive_old_conversation_log(
        self, cutoff_days: "int | None" = None, now: "float | None" = None
    ) -> int:
        """Move conversation_log turns older than cutoff_days to the archive DB.

        Uses ATTACH DATABASE so the INSERT and DELETE happen in a single
        transaction — if anything fails, no rows are lost from main and
        none are duplicated in the archive.  Returns the number of rows moved.
        """
        if config.RETENTION_MODE == "ephemeral":
            return 0  # SB.5: retention-gated — no archive move under ephemeral (data purges; nothing to archive)
        if cutoff_days is None:
            cutoff_days = CONVERSATION_ARCHIVE_AFTER_DAYS
        if now is None:
            now = time.time()
        cutoff_ts = now - cutoff_days * 86400

        n = self._conn.execute(
            "SELECT COUNT(*) FROM conversation_log WHERE ts < ?",
            (cutoff_ts,),
        ).fetchone()[0]
        if n == 0:
            return 0

        archive_path = self._archive_db_path()
        self._conn.execute("ATTACH DATABASE ? AS archive", (str(archive_path),))
        try:
            self._conn.execute("BEGIN EXCLUSIVE")
            self._conn.execute(
                "INSERT INTO archive.conversation_log "
                "(person_id, role, content, ts, room_session_id, audience_ids) "
                "SELECT person_id, role, content, ts, room_session_id, audience_ids "
                "FROM main.conversation_log WHERE ts < ?",
                (cutoff_ts,),
            )
            self._conn.execute(
                "DELETE FROM main.conversation_log WHERE ts < ?",
                (cutoff_ts,),
            )
            self._conn.execute("COMMIT")
        except Exception:
            # P0.9.1 Imp-2: tightened rollback — re-raise unexpected
            # OperationalErrors instead of swallowing every Exception.
            # Only the S65 "no transaction is active" race is suppressed
            # (ROLLBACK raises if BEGIN EXCLUSIVE failed before).
            try:
                self._conn.execute("ROLLBACK")
            except sqlite3.OperationalError as _rbe:
                if "no transaction is active" not in str(_rbe).lower():
                    print(f"[FaceDB] archive rollback failed unexpectedly: {_rbe!r}")
                    raise
                # else: # RACE: S65 — known race, suppress
            raise
        finally:
            try:
                self._conn.execute("DETACH DATABASE archive")
            except Exception:
                pass  # CLEANUP: DETACH raises if ATTACH failed earlier — no archive DB to release
        return n

    def prune_old_archive_conversation_log(
        self, retention_days: "int | None" = None, now: "float | None" = None
    ) -> int:
        """P0.R12 D1 — delete rows from archive.conversation_log older than retention_days.

        Mirrors archive_old_conversation_log's ATTACH DATABASE + BEGIN EXCLUSIVE +
        P0.9.1 Imp-2 rollback discipline. Different polarity: archive_old_*
        MOVES from main → archive; this method DELETES from archive (bounds
        archive growth at ~1 year of history by default).

        Operator-tunable via CONVERSATION_ARCHIVE_RETENTION_DAYS config (Q1 (a)
        RATIFIED). Returns count of rows deleted.
        """
        if retention_days is None:
            retention_days = CONVERSATION_ARCHIVE_RETENTION_DAYS
        if now is None:
            now = time.time()
        cutoff_ts = now - retention_days * 86400

        archive_path = self._archive_db_path()
        if not archive_path.exists():
            return 0

        self._conn.execute("ATTACH DATABASE ? AS archive", (str(archive_path),))
        try:
            n = self._conn.execute(
                "SELECT COUNT(*) FROM archive.conversation_log WHERE ts < ?",
                (cutoff_ts,),
            ).fetchone()[0]
            if n == 0:
                return 0
            self._conn.execute("BEGIN EXCLUSIVE")
            self._conn.execute(
                "DELETE FROM archive.conversation_log WHERE ts < ?",
                (cutoff_ts,),
            )
            self._conn.execute("COMMIT")
        except Exception:
            # P0.9.1 Imp-2 tightened rollback discipline — re-raise unexpected
            # OperationalErrors; only S65 "no transaction is active" race
            # suppressed (ROLLBACK raises if BEGIN EXCLUSIVE failed before).
            try:
                self._conn.execute("ROLLBACK")
            except sqlite3.OperationalError as _rbe:
                if "no transaction is active" not in str(_rbe).lower():
                    print(f"[FaceDB] archive-prune rollback failed unexpectedly: {_rbe!r}")
                    raise
                # else: # RACE: S65 — known race, suppress per P0.9.1 Imp-2
            raise
        finally:
            try:
                self._conn.execute("DETACH DATABASE archive")
            except Exception:
                pass  # CLEANUP: DETACH raises if ATTACH failed earlier — no archive DB to release
        return n

    def _warn_missing_vectors(self):
        """One-time migration helper: warn if any enrolled persons lack vector BLOBs."""
        row = self._conn.execute(
            "SELECT COUNT(DISTINCT person_id) FROM embeddings WHERE vector IS NULL"
        ).fetchone()
        missing = row[0] if row else 0
        if missing > 0:
            print(f"[DB] WARNING: {missing} person(s) have no vector data and need re-enrollment")

    def _sentinel_path(self) -> Path:
        """P0.5 dirty sentinel — name + '.dirty' (appended, not suffix-replaced)."""
        return self._faiss_path.with_name(self._faiss_path.name + ".dirty")

    def _mark_faiss_dirty(self) -> None:
        """Write the dirty sentinel; best-effort (row-count check still catches mismatches)."""
        try:
            self._sentinel_path().touch()
        except Exception as e:
            print(f"[FaceDB] failed to write FAISS dirty sentinel: {e!r}")  # CLEANUP: best-effort

    def _clear_faiss_dirty(self) -> None:
        """Remove the dirty sentinel after a successful FAISS rebuild."""
        try:
            self._sentinel_path().unlink(missing_ok=True)
        except Exception as e:
            print(f"[FaceDB] failed to clear FAISS dirty sentinel: {e!r}")  # CLEANUP: best-effort

    def _load_faiss(self):
        if self._faiss_path.exists():
            self.index = faiss.read_index(str(self._faiss_path))
        else:
            self.index = faiss.IndexFlatIP(EMBEDDING_DIM)

        null_count = self._conn.execute(
            "SELECT COUNT(*) FROM embeddings WHERE vector IS NULL"
        ).fetchone()[0]
        if null_count > 0:
            print(
                f"[DB] WARNING: {null_count} embedding row(s) with NULL vectors — "
                f"orphaned gallery entries. Re-enrol those persons or run delete_person."
            )

        valid_count = self._conn.execute(
            "SELECT COUNT(*) FROM embeddings WHERE vector IS NOT NULL"
        ).fetchone()[0]

        sentinel = self._sentinel_path()
        needs_rebuild = sentinel.exists() or self.index.ntotal != valid_count
        if needs_rebuild:
            if self.index.ntotal != valid_count:
                print(
                    f"[DB] FAISS out of sync: index={self.index.ntotal}, "
                    f"valid_rows={valid_count}, null_rows={null_count} — rebuilding."
                )
            else:
                print("[DB] FAISS dirty sentinel found — rebuilding to reconcile.")
            try:
                self._rebuild_faiss()
                self._clear_faiss_dirty()
            except Exception as e:
                print(f"[FaceDB] Boot reconciliation failed; starting in degraded mode: {e!r}")
                self._faiss_degraded = True
            return

        # Build idx → person_id map from DB
        rows = self._conn.execute(
            "SELECT faiss_idx, person_id FROM embeddings WHERE vector IS NOT NULL ORDER BY faiss_idx"
        ).fetchall()
        self._idx_to_person = {r[0]: r[1] for r in rows}

    def _save_faiss_unlocked(self) -> None:
        """Write FAISS index to disk. MUST be called WITH _index_lock already held.

        Extracted from _save_faiss() to make the lock-held precondition explicit
        at every internal call site (P0.B5 D3 / ceo-morning Finding 3 — was
        implicitly relying on RLock re-entrancy; explicit naming prevents future
        refactor from breaking the contract if _index_lock is ever changed from
        threading.RLock to threading.Lock).
        """
        faiss.write_index(self.index, str(self._faiss_path))

    def _save_faiss(self) -> None:
        """Public-facing save. Acquires _index_lock + calls _save_faiss_unlocked.

        External callers (callers that do NOT already hold _index_lock) use this
        method. Internal callers that already hold _index_lock (inside a
        `with self._index_lock:` block) MUST use _save_faiss_unlocked() directly
        to make the lock-held precondition visible at the call site.
        """
        with self._index_lock:
            self._save_faiss_unlocked()

    # ── Enroll ────────────────────────────────────────────────────────────────
    def add_person(self, person_id: str, name: str, photo_path: str = None, person_type: str = 'known'):
        if config.ENROLLMENT_MODE != "persistent":
            return  # SB.5: enrollment-gated — transient/none skip the disk INSERT; caller's in-session pid carries
        self._conn.execute(
            "INSERT OR IGNORE INTO persons (id, name, enrolled_at, photo_path, person_type) "
            "VALUES (?, ?, ?, ?, ?)",
            (person_id, name, time.time(), photo_path, person_type)
        )
        self._conn.commit()

    def get_best_friend(self) -> dict | None:
        row = self._conn.execute(
            "SELECT id, name, enrolled_at FROM persons WHERE person_type = 'best_friend' LIMIT 1"
        ).fetchone()
        return {"id": row[0], "name": row[1], "enrolled_at": row[2]} if row else None

    def is_best_friend_enrolled(self) -> bool:
        return self.get_best_friend() is not None

    def add_stranger(self, name: str = "visitor", photo_path: str = "",
                     person_id: str | None = None) -> str:
        """Create a stranger person record and return their person_id.

        Pass person_id to pin the DB entry to an existing in-memory session ID
        (progressive enrollment: session opened before system name was heard).
        If omitted, a new UUID-based ID is generated.
        Uses INSERT OR IGNORE so calling twice for the same person_id is safe.
        """
        if person_id is None:
            safe = re.sub(r"[^a-z0-9]", "", name.lower())[:12] or "visitor"
            person_id = f"stranger_{safe}_{uuid4().hex[:6]}"
        if config.ENROLLMENT_MODE == "persistent":
            self._conn.execute(
                "INSERT OR IGNORE INTO persons (id, name, enrolled_at, last_seen, photo_path, person_type) "
                "VALUES (?, ?, ?, ?, ?, 'stranger')",
                (person_id, name, time.time(), time.time(), photo_path),
            )
            self._conn.commit()
        return person_id  # SB.5: enrollment-gated — always return pid (transient mints+returns, skips only the INSERT)

    def get_person_type(self, person_id: str) -> str:
        """Return 'known' or 'stranger' for a person. Defaults to 'known' if not found."""
        row = self._conn.execute(
            "SELECT person_type FROM persons WHERE id = ?", (person_id,)
        ).fetchone()
        return row[0] if row else "known"

    def get_stranger_visits_since(self, since_ts: float) -> list[dict]:
        """Return strangers seen after since_ts, ordered by most recent. For owner briefing."""
        rows = self._conn.execute(
            """SELECT id, name, last_seen, enrolled_at FROM persons
               WHERE person_type = 'stranger' AND last_seen > ?
               ORDER BY last_seen DESC""",
            (since_ts,),
        ).fetchall()
        return [
            {"id": r[0], "name": r[1], "last_seen": r[2], "first_seen": r[3]}
            for r in rows
        ]

    # ── Silent observations ────────────────────────────────────────────────────
    def update_silent_observation(
        self, embedding: np.ndarray,
        photo_path: str | None = None,
        zone: str | None = None,
    ) -> str | None:
        """Accumulate a silent-face sighting via online embedding mean.

        Compares the new embedding against unmatched recent silent_observations using
        vectorized cosine similarity (single matmul). If a match is found
        (sim >= SILENT_OBS_SIMILARITY), updates that row's mean embedding and
        frame_count and returns its id. Otherwise inserts a new row and returns None.
        Never creates a Person record.

        Wave 2 Item 12: vectorized — single matmul instead of per-row Python loop.
        """
        if config.RETENTION_MODE == "ephemeral":
            return None  # SB.5: retention-gated — no silent-observation capture under ephemeral
        emb = embedding.astype(np.float32)
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm

        now = time.time()
        cutoff = time.time() - SILENT_OBS_SCAN_DAYS * 86400
        rows = self._conn.execute(
            """SELECT id, embedding, frame_count FROM silent_observations
               WHERE matched_person_id IS NULL AND last_seen >= ?""",
            (cutoff,),
        ).fetchall()

        if not rows:
            obs_id = f"obs_{uuid4().hex[:10]}"
            self._conn.execute(
                """INSERT INTO silent_observations
                   (id, first_seen, last_seen, duration_secs, frame_count,
                    embedding, photo_path, zone, created_at)
                   VALUES (?, ?, ?, 0, 1, ?, ?, ?, ?)""",
                (obs_id, now, now, emb.tobytes(), photo_path, zone, now),
            )
            self._conn.commit()
            return None

        # Decode all embeddings into an (N, D) matrix — single allocation.
        n = len(rows)
        dim = emb.shape[0]
        mat = np.empty((n, dim), dtype=np.float32)
        ids: list[str] = []
        counts: list[int] = []
        for i, (row_id, vec_bytes, frame_count) in enumerate(rows):
            mat[i] = np.frombuffer(vec_bytes, dtype=np.float32)
            ids.append(row_id)
            counts.append(frame_count)

        # Cosine == dot product since both query and stored embeddings are L2-normalized.
        scores = mat @ emb  # shape (N,)
        best_idx = int(np.argmax(scores))
        best_sim = float(scores[best_idx])

        if best_sim >= SILENT_OBS_SIMILARITY:
            best_id = ids[best_idx]
            n_frames = counts[best_idx]
            best_emb = mat[best_idx]
            # Online mean: new_mean = (old_mean * n + new) / (n + 1)
            new_mean = (best_emb * n_frames + emb) / (n_frames + 1)
            norm2 = np.linalg.norm(new_mean)
            if norm2 > 0:
                new_mean /= norm2
            self._conn.execute(
                """UPDATE silent_observations
                   SET embedding    = ?,
                       last_seen    = ?,
                       frame_count  = frame_count + 1,
                       zone         = COALESCE(?, zone),
                       photo_path   = COALESCE(?, photo_path)
                   WHERE id = ?""",
                (new_mean.tobytes(), now, zone, photo_path, best_id),
            )
            self._conn.commit()
            return best_id
        else:
            obs_id = f"obs_{uuid4().hex[:10]}"
            self._conn.execute(
                """INSERT INTO silent_observations
                   (id, first_seen, last_seen, duration_secs, frame_count,
                    embedding, photo_path, zone, created_at)
                   VALUES (?, ?, ?, 0, 1, ?, ?, ?, ?)""",
                (obs_id, now, now, emb.tobytes(), photo_path, zone, now),
            )
            self._conn.commit()
            return None

    def prune_silent_observations(self, days: int = SILENT_OBS_RETENTION_DAYS) -> int:
        """Delete observations older than `days` days. Returns rows deleted."""
        cutoff = time.time() - days * 86400
        cur = self._conn.execute(
            "DELETE FROM silent_observations WHERE last_seen < ?", (cutoff,)
        )
        self._conn.commit()
        return cur.rowcount

    def get_recent_silent_observations(self, since_ts: float = 0.0) -> list[dict]:
        """Return silent observations last seen after since_ts, newest first."""
        rows = self._conn.execute(
            """SELECT id, first_seen, last_seen, duration_secs, frame_count,
                      photo_path, zone, matched_person_id
               FROM silent_observations
               WHERE last_seen > ?
               ORDER BY last_seen DESC""",
            (since_ts,),
        ).fetchall()
        return [
            {
                "id":               r[0],
                "first_seen":       r[1],
                "last_seen":        r[2],
                "duration_secs":    r[3],
                "frame_count":      r[4],
                "photo_path":       r[5],
                "zone":             r[6],
                "matched_person_id": r[7],
            }
            for r in rows
        ]

    def add_embedding(self, person_id: str, embedding: np.ndarray,
                      source: str, confidence: float = 0.0,
                      anti_spoof_verdict: "bool | None" = None) -> bool:
        """Add one face embedding for a person using diversity-based gallery management.

        Returns False if the gallery is full, the new embedding is too similar
        to an existing one (same angle/condition already covered), or the
        anti-spoof catch-all rejects the write (P0.S1 D1).

        First N_INITIAL_FACE embeddings bypass diversity (enrollment baseline).
        Beyond that: only stored if cosine similarity to every existing embedding
        is below FACE_DIVERSITY_THRESHOLD — i.e. it covers a new angle or condition.

        P0.S1 D1 — anti-spoof catch-all: every source in
        ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF (currently all valid
        sources) requires `anti_spoof_verdict=True`. False or None blocks the
        write with a `[FaceDB]` log line. Callers MUST compute the verdict
        upstream via `verify_live(...)` (or `_anti_spoof_ok`) and pass it
        through. Plan v2 §1 / §3.1.
        """
        if config.ENROLLMENT_MODE != "persistent":
            return False  # SB.5: enrollment-gated — face recognition template not persisted under transient/none (before the P0.5 FAISS+SQL transaction)
        if not (source in VALID_EMBEDDING_SOURCES):
            raise RuntimeError(f'add_embedding called with unknown source={source!r}. Add it to VALID_EMBEDDING_SOURCES in db.py first.')

        # P0.S1 D1 catch-all — structural backstop for the per-call-site
        # upstream gates. Sites 1-4 already gate at their call point via
        # verify_live; site 5 (progressive_enroll, Phase 3) closes the gap.
        # The catch-all ensures that *any* future caller using a protected
        # source is blocked at the DB layer if they forget the upstream gate.
        if source in ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF:
            if anti_spoof_verdict is not True:
                print(
                    f"[FaceDB] add_embedding rejected for {person_id} "
                    f"source={source} verdict={anti_spoof_verdict!r} — "
                    f"anti-spoof gate blocks write (P0.S1 D1 catch-all)"
                )
                return False
        # Normalize first — all stored vectors are L2-normalized for cosine via inner product
        emb = embedding.astype(np.float32).reshape(1, -1)
        faiss.normalize_L2(emb)
        emb_1d = emb[0]  # (512,)

        # Load existing embeddings for cap + diversity check
        rows = self._conn.execute(
            "SELECT vector FROM embeddings WHERE person_id = ?", (person_id,)
        ).fetchall()
        count = len(rows)

        if count >= MAX_EMBEDDINGS:
            return False

        # Diversity check: skip if this angle/condition is already well-represented
        if count >= N_INITIAL_FACE:
            for (vec_bytes,) in rows:
                existing = np.frombuffer(vec_bytes, dtype=np.float32)
                if float(np.dot(emb_1d, existing)) > FACE_DIVERSITY_THRESHOLD:
                    return False  # too similar to an existing embedding — skip

        # Centroid-distance gate for recognition_update writes (anti-poisoning).
        # If the proposed embedding is too far from the existing gallery centroid,
        # reject it — a genuine same-person frame sits in the same neighbourhood.
        # Only enforced for "recognition_update" and only once baseline is seeded.
        if source == "recognition_update" and count >= N_INITIAL_FACE:
            centroid = np.mean(
                np.vstack([np.frombuffer(v, dtype=np.float32) for (v,) in rows]),
                axis=0,
            )
            cn = float(np.linalg.norm(centroid))
            if cn > 0.0:
                centroid = centroid / cn
                centroid_sim = float(np.dot(emb_1d, centroid))
                if centroid_sim < SELF_UPDATE_CENTROID_MIN:
                    print(
                        f"[FaceDB] recognition_update rejected for {person_id}: "
                        f"centroid cosine {centroid_sim:.3f} < {SELF_UPDATE_CENTROID_MIN}"
                    )
                    return False

        # P0.5: SQL durable, FAISS derived; boot reconciliation handles divergence.
        with self._index_lock:
            faiss_idx = self.index.ntotal
            # P0.B2 D3 (closed 2026-05-21): capture `cur.lastrowid` via
            # explicit-cursor pattern (Plan v2 §4.1). Required because Phase 3
            # of `rebuild_faiss_async` needs the row_id to write the new
            # `faiss_idx` back to the DB after the async swap.
            with self.transaction():
                cur = self._conn.execute(
                    "INSERT INTO embeddings (person_id, faiss_idx, vector, captured_at, source, confidence_at_write)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (person_id, faiss_idx, emb_1d.tobytes(), time.time(), source, confidence)
                )
                _row_id = cur.lastrowid
            try:
                self.index.add(emb)
                self._idx_to_person[faiss_idx] = person_id
                if self._rebuild_in_progress:
                    # Enqueue so the async rebuild can replay this addition onto the new index.
                    # P0.B2 D3: 3-tuple `(vec, person_id, row_id)` enables Phase 3 to write
                    # the post-replay `faiss_idx` back to the DB row for this pending add.
                    self._pending_adds_during_rebuild.append((emb[0].copy(), person_id, _row_id))
                self._save_faiss_unlocked()  # P0.B5 D3 — lock already held at line 694
            except Exception as e:
                print(f"[FaceDB] FAISS update failed; will reconcile on next boot: {e!r}")
                self._mark_faiss_dirty()
                raise
        return True

    # ── Recognize ─────────────────────────────────────────────────────────────
    def recognize(self, embedding: np.ndarray, threshold: float) -> tuple[Optional[str], Optional[str], float]:
        """
        Returns (person_id, name, confidence) or (None, None, 0.0)
        """
        if self._faiss_degraded:
            return None, None, 0.0

        with self._index_lock:
            if self.index.ntotal == 0:
                return None, None, 0.0

            emb = embedding.astype(np.float32).reshape(1, -1)
            faiss.normalize_L2(emb)

            scores, indices = self.index.search(emb, 1)
            score = float(scores[0][0])
            idx   = int(indices[0][0])

            if score < threshold or idx not in self._idx_to_person:
                return None, None, score

            person_id = self._idx_to_person[idx]

        row = self._conn.execute(
            "SELECT name FROM persons WHERE id = ?", (person_id,)
        ).fetchone()

        if not row:
            return None, None, score

        return person_id, row[0], score

    # ── People list ───────────────────────────────────────────────────────────
    def list_people(self) -> list[dict]:
        rows = self._conn.execute("""
            SELECT p.id, p.name, p.enrolled_at, p.photo_path,
                   COUNT(e.id) as embedding_count, p.person_type
            FROM persons p
            LEFT JOIN embeddings e ON e.person_id = p.id
            GROUP BY p.id
            ORDER BY p.enrolled_at DESC
        """).fetchall()
        return [
            {
                "id":              r[0],
                "name":            r[1],
                "enrolled_at":     r[2],
                "photo_path":      r[3],
                "embedding_count": r[4],
                "person_type":     r[5],
            }
            for r in rows
        ]

    def get_person(self, person_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT id, name, enrolled_at, photo_path FROM persons WHERE id = ?",
            (person_id,)
        ).fetchone()
        if not row:
            return None
        return {"id": row[0], "name": row[1], "enrolled_at": row[2], "photo_path": row[3]}

    def delete_person(self, person_id: str):
        """Delete person, their embeddings, and their full conversation history."""
        # P0.5: SQL durable, FAISS derived; boot reconciliation handles divergence.
        with self._index_lock:
            with self.transaction():
                self._conn.execute("DELETE FROM embeddings WHERE person_id = ?", (person_id,))
                self._conn.execute("DELETE FROM voice_embeddings WHERE person_id = ?", (person_id,))
                self._conn.execute("DELETE FROM conversation_log WHERE person_id = ?", (person_id,))
                self._conn.execute("DELETE FROM persons WHERE id = ?", (person_id,))
                self._conn.execute(
                    "UPDATE silent_observations SET matched_person_id = NULL WHERE matched_person_id = ?",
                    (person_id,),
                )
            try:
                self._rebuild_faiss()
            except Exception as e:
                print(f"[FaceDB] FAISS rebuild failed after delete_person; will reconcile on next boot: {e!r}")
                self._mark_faiss_dirty()
                raise

    def find_stale_stranger_voice_ids(self, days: int) -> list[str]:
        """Return (without deleting) the list of stranger person_ids whose voice profile
        is both immature (< N_INITIAL_VOICE samples) and stale (> `days` since last update).

        Used by callers that want to evict in-memory voice caches BEFORE issuing the
        destructive prune, so concurrent readers can't briefly see a pid that will be
        deleted in a moment. See pipeline dream-loop for the two-step pattern.
        """
        cutoff = time.time() - days * 86400
        rows = self._conn.execute(
            f"""
            SELECT v.person_id
            FROM voice_embeddings v
            JOIN persons p ON p.id = v.person_id
            WHERE p.person_type = 'stranger'
            GROUP BY v.person_id
            HAVING COUNT(*) < {N_INITIAL_VOICE} AND MAX(v.captured_at) < ?
            """,
            (cutoff,),
        ).fetchall()
        return [r[0] for r in rows]

    def prune_stale_stranger_voice(self, days: int,
                                    ids: "list[str] | None" = None) -> list[str]:
        """Prune voice_embeddings for stranger persons whose voice profile never reached
        maturity (< N_INITIAL_VOICE samples) and hasn't been updated in `days` days.

        A thin voice profile on a stranger is more false-positive prone than absent, so
        we'd rather force rebuild-from-scratch on next encounter. The person row is left
        alone — only their voice rows are deleted. Returns the list of pruned person_ids
        so the caller can also evict them from any in-memory voice gallery caches
        (pipeline.py:_voice_gallery, _voice_gallery_sizes).

        `ids` may be pre-computed by the caller (e.g. from find_stale_stranger_voice_ids)
        to avoid running the query twice in the evict-then-prune pattern.
        """
        if ids is None:
            ids = self.find_stale_stranger_voice_ids(days)
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        self._conn.execute(
            f"DELETE FROM voice_embeddings WHERE person_id IN ({placeholders})", ids,
        )
        self._conn.commit()
        return ids

    def prune_old_strangers(self, days: int) -> list:
        """Delete stranger persons unseen for `days` days from all faces.db tables.

        Returns a list of deleted person_ids. Rebuilds FAISS once at the end —
        never once per deletion — so N-stranger cleanup costs one FAISS rebuild total.
        """
        cutoff = time.time() - days * 86400
        rows = self._conn.execute(
            "SELECT id FROM persons WHERE person_type = 'stranger' "
            "AND (last_seen IS NULL OR last_seen < ?)",
            (cutoff,)
        ).fetchall()
        if not rows:
            return []
        ids = [r[0] for r in rows]
        placeholders = ",".join("?" * len(ids))
        # P0.5: SQL durable, FAISS derived; boot reconciliation handles divergence.
        with self._index_lock:
            with self.transaction():
                for table in ("embeddings", "voice_embeddings", "conversation_log"):
                    self._conn.execute(
                        f"DELETE FROM {table} WHERE person_id IN ({placeholders})", ids
                    )
                self._conn.execute(f"DELETE FROM persons WHERE id IN ({placeholders})", ids)
            try:
                self._rebuild_faiss()
            except Exception as e:
                print(f"[FaceDB] FAISS rebuild failed after prune_old_strangers; will reconcile on next boot: {e!r}")
                self._mark_faiss_dirty()
                raise
        return ids

    def prune_zero_value_stranger(self, person_id: str) -> bool:
        """Session 97 Fix 2: delete a stranger row that accumulated zero
        useful data — no voice embeddings, no conversation turns. These
        appear when a stranger session opens, hits the engagement gate
        (didn't say the system name), and closes at expiry with nothing
        to preserve. The existing STRANGER_TTL_DAYS=7 backstop catches
        them eventually but that window leaves ghost sessions visible in
        the UI/graph for a week.

        SAFETY TRIPLE-CHECK before any DELETE fires:
          1. person_type MUST be 'stranger' (never touch known/best_friend)
          2. zero voice_embeddings rows
          3. zero conversation_log rows

        Any missing condition → no-op, return False. Returns True only
        when the row was actually deleted. Deletion cascades through
        ``embeddings`` + ``voice_embeddings`` + ``conversation_log`` +
        ``persons`` and triggers a FAISS rebuild — same pattern as
        :py:meth:`prune_old_strangers`.
        """
        row = self._conn.execute(
            "SELECT person_type FROM persons WHERE id = ?", (person_id,)
        ).fetchone()
        if not row or row[0] != "stranger":
            return False
        voice_n = self._conn.execute(
            "SELECT COUNT(*) FROM voice_embeddings WHERE person_id = ?", (person_id,)
        ).fetchone()[0]
        if voice_n > 0:
            return False
        turn_n = self._conn.execute(
            "SELECT COUNT(*) FROM conversation_log WHERE person_id = ?", (person_id,)
        ).fetchone()[0]
        if turn_n > 0:
            return False
        # P0.5: SQL durable, FAISS derived; boot reconciliation handles divergence.
        with self._index_lock:
            with self.transaction():
                for table in ("embeddings", "voice_embeddings", "conversation_log"):
                    self._conn.execute(
                        f"DELETE FROM {table} WHERE person_id = ?", (person_id,)
                    )
                self._conn.execute("DELETE FROM persons WHERE id = ?", (person_id,))
            try:
                self._rebuild_faiss()
            except Exception as e:
                print(f"[FaceDB] FAISS rebuild failed after prune_zero_value_stranger; will reconcile on next boot: {e!r}")
                self._mark_faiss_dirty()
                raise
        print(f"[FaceDB] Pruned zero-value stranger {person_id}")
        return True

    # ── Wave 3 Item 15 — async FAISS rebuild ──────────────────────────────────

    def _fetch_all_embeddings_for_index(self) -> tuple:
        """Snapshot all embeddings for index rebuild. Must be called under _index_lock.

        P0.B2 D1 (closed 2026-05-21): returns 3-tuple `(vecs, person_ids, row_ids)`.
        `row_ids` enables Phase 3 of `rebuild_faiss_async` to write the new
        `faiss_idx` values back to the `embeddings` table — the Bug 1 fix
        (sync `_rebuild_faiss` already does this DB UPDATE; async path was
        missing it pre-P0.B2).
        """
        rows = self._conn.execute(
            "SELECT id, person_id, vector FROM embeddings WHERE vector IS NOT NULL ORDER BY id"
        ).fetchall()
        if not rows:
            return np.empty((0, EMBEDDING_DIM), dtype=np.float32), [], []
        row_ids = [r[0] for r in rows]
        person_ids = [r[1] for r in rows]
        vecs = np.vstack([
            np.frombuffer(r[2], dtype=np.float32).copy().reshape(1, -1)
            for r in rows
        ]).astype(np.float32)
        return vecs, person_ids, row_ids

    def _build_faiss_from_snapshot(self, snapshot: tuple) -> tuple:
        """Build a new IndexFlatIP from snapshot data. Pure — no DB access, no lock.

        P0.B2 D2 (closed 2026-05-21): returns 4-tuple `(new_index,
        new_idx_to_person, snapshot_idx_updates)` where `snapshot_idx_updates`
        is `list[tuple[int, int]]` of `(new_idx, row_id)` pairs. Caller
        (`rebuild_faiss_async` Phase 3) uses this list to write the new
        `faiss_idx` values back to the `embeddings` table after the swap.

        Safe to run in a worker thread (no DB access, no lock).
        """
        vecs, person_ids, row_ids = snapshot
        new_index = faiss.IndexFlatIP(EMBEDDING_DIM)
        new_idx_to_person: dict = {}
        snapshot_idx_updates: list = []
        for i, (pid, row_id) in enumerate(zip(person_ids, row_ids)):
            new_index.add(vecs[i].reshape(1, -1))
            new_idx_to_person[i] = pid
            snapshot_idx_updates.append((i, row_id))
        return new_index, new_idx_to_person, snapshot_idx_updates

    async def rebuild_faiss_async(self, loop: asyncio.AbstractEventLoop) -> None:
        """Rebuild FAISS index without blocking concurrent recognize/add_embedding.

        Snapshot under lock (~ms), build outside lock (~50ms-3s), swap under lock (~ms).
        Concurrent add_embedding calls during the build phase are queued and replayed
        onto the new index before swap, so no additions are lost.

        P0.B2 D3+D4 (closed 2026-05-21) — ORDERING INVARIANT:
            sentinel SET → Phase 3 in-memory swap → DB UPDATE batch + commit
            → Phase 4 _save_faiss → sentinel CLEAR

        Each crash point has an explicit recovery path:
            - Crash before sentinel set: in-memory swap not yet applied; OLD
              state still on disk. Boot loads OLD state cleanly; no rebuild.
            - Crash after sentinel set, before DB UPDATE commit: sentinel
              triggers `_rebuild_faiss` on next boot (which uses the sync
              path's SELECT + UPDATE + commit + save discipline).
            - Crash mid-DB-UPDATE batch: SQLite transaction atomicity rolls
              back partial commits; sentinel still set; boot rebuilds.
            - Crash after DB UPDATE commit, before _save_faiss: DB is fresh;
              disk faiss.index is stale; sentinel still set; boot rebuilds
              the in-memory index from the fresh DB.
            - Crash after _save_faiss, before sentinel clear: DB + disk both
              fresh; sentinel triggers redundant-but-safe rebuild on boot.
        """
        if not self._rebuild_lock.acquire(blocking=False):
            print("[FaceDB] rebuild already in progress, skipping")
            return

        try:
            # Phase 1: snapshot under lock, mark rebuild-in-progress
            with self._index_lock:
                snapshot = self._fetch_all_embeddings_for_index()
                self._pending_adds_during_rebuild = []
                self._rebuild_in_progress = True

            # Phase 2: build new index in worker thread (slow, no lock held)
            try:
                new_index, new_idx_to_person, snapshot_idx_updates = await loop.run_in_executor(
                    None,
                    self._build_faiss_from_snapshot,
                    snapshot,
                )
            except Exception:
                with self._index_lock:
                    self._rebuild_in_progress = False
                    self._pending_adds_during_rebuild = []
                raise

            # P0.B2 D4: sentinel SET BEFORE Phase 3 swap (ORDERING INVARIANT
            # step 1). If the in-memory swap completes but the DB UPDATE
            # batch crashes or _save_faiss fails, boot reconciliation reads
            # the sentinel and re-runs the sync `_rebuild_faiss` to repair.
            self._mark_faiss_dirty()

            # Phase 3: replay pending adds onto new index, swap atomically (under lock, fast)
            # Replay BEFORE setting self.index so that an add_embedding racing between the
            # assignment and _rebuild_in_progress=False doesn't double-add. All three
            # mutations happen inside one lock acquisition — correct by construction.
            #
            # P0.B2 D3: pending-add row_ids are captured via add_embedding's
            # explicit-cursor pattern (line ~706); replay positions are
            # captured into `pending_idx_updates` for the post-lock DB UPDATE
            # batch. Combined with `snapshot_idx_updates` from Phase 2 to
            # cover all rows whose `faiss_idx` changed during the rebuild.
            pending_idx_updates: list = []
            with self._index_lock:
                for vec, person_id, row_id in self._pending_adds_during_rebuild:
                    new_idx = new_index.ntotal
                    new_index.add(vec.reshape(1, -1))
                    new_idx_to_person[new_idx] = person_id
                    pending_idx_updates.append((new_idx, row_id))
                self.index = new_index
                self._idx_to_person = new_idx_to_person
                self._rebuild_in_progress = False
                self._pending_adds_during_rebuild = []

            # P0.B2 D3: DB UPDATE batch AFTER releasing _index_lock (matches
            # sync `_rebuild_faiss` precedent at lines 1075-1080). Combined
            # updates cover BOTH snapshot rows AND pending-add rows so the
            # DB `embeddings.faiss_idx` column reflects the new in-memory
            # positions. ORDERING INVARIANT step 2.
            try:
                all_idx_updates = snapshot_idx_updates + pending_idx_updates
                if all_idx_updates:
                    for new_idx, row_id in all_idx_updates:
                        self._conn.execute(
                            "UPDATE embeddings SET faiss_idx = ? WHERE id = ?",
                            (new_idx, row_id),
                        )
                    self._conn.commit()
            except Exception as e:
                # Sentinel stays set; next boot rebuilds via _rebuild_faiss.
                print(f"[FaceDB] async DB UPDATE batch failed; sentinel set for boot rebuild: {e!r}")
                raise

            # Phase 4: persist to disk (lock-free; no readers depend on file content)
            # ORDERING INVARIANT step 3.
            try:
                await loop.run_in_executor(None, self._save_faiss)
            except Exception as e:
                print(f"[FaceDB] async save_faiss failed (index in memory OK): {e!r}")
                return  # leave sentinel set so boot rebuilds from fresh DB

            # P0.B2 D4: sentinel CLEAR after BOTH DB UPDATE commit AND
            # _save_faiss succeed (ORDERING INVARIANT step 4). Any earlier
            # exception leaves the sentinel set — boot reconciliation handles.
            self._clear_faiss_dirty()
        finally:
            self._rebuild_lock.release()

    def prune_old_strangers_sql_only(self, days: int) -> list:
        """SQL-only part of prune_old_strangers: SELECT + DELETE rows, no FAISS rebuild.

        Returns the list of deleted person_ids. Used by prune_old_strangers_async so
        that the FAISS rebuild can happen in the background while conversation continues.
        The sync prune_old_strangers() is kept for CLI paths that still want sync semantics.
        """
        cutoff = time.time() - days * 86400
        rows = self._conn.execute(
            "SELECT id FROM persons WHERE person_type = 'stranger' "
            "AND (last_seen IS NULL OR last_seen < ?)",
            (cutoff,)
        ).fetchall()
        if not rows:
            return []
        ids = [r[0] for r in rows]
        placeholders = ",".join("?" * len(ids))
        for table in ("embeddings", "voice_embeddings", "conversation_log"):
            self._conn.execute(
                f"DELETE FROM {table} WHERE person_id IN ({placeholders})", ids
            )
        self._conn.execute(f"DELETE FROM persons WHERE id IN ({placeholders})", ids)
        self._conn.commit()
        return ids

    async def prune_old_strangers_async(
        self, loop: asyncio.AbstractEventLoop, days: int = None
    ) -> list:
        """Async version of prune_old_strangers for the dream loop.

        Deletes stale stranger rows synchronously (fast), then rebuilds FAISS in the
        background so the conversation pipeline is never blocked for 500ms-3s.
        Returns the list of deleted person_ids so the caller can prune brain data.
        """
        effective_days = days if days is not None else STRANGER_TTL_DAYS
        ids = self.prune_old_strangers_sql_only(effective_days)
        if ids:
            await self.rebuild_faiss_async(loop)
        return ids

    def _rebuild_faiss(self):
        """Rebuild FAISS index from SQLite vector BLOBs.

        Assigns new sequential faiss_idx values (0, 1, 2, …) and updates the DB
        to match, keeping _idx_to_person and the on-disk index in sync.

        delete_person() uses this sync path deliberately — it is an operator-facing,
        low-frequency action invoked via subprocess (dashboard/CLI), so the caller is
        exiting anyway and blocking is acceptable. Do NOT migrate delete_person() to
        the async path; the subprocess exit makes async overhead pointless here.
        """
        rows = self._conn.execute(
            "SELECT id, person_id, vector FROM embeddings WHERE vector IS NOT NULL ORDER BY id"
        ).fetchall()

        idx_updates = []
        with self._index_lock:
            self.index = faiss.IndexFlatIP(EMBEDDING_DIM)
            self._idx_to_person = {}
            for new_idx, (row_id, person_id, vector_bytes) in enumerate(rows):
                emb = np.frombuffer(vector_bytes, dtype=np.float32).copy().reshape(1, -1)
                self.index.add(emb)
                self._idx_to_person[new_idx] = person_id
                idx_updates.append((new_idx, row_id))

        for new_idx, row_id in idx_updates:
            self._conn.execute(
                "UPDATE embeddings SET faiss_idx = ? WHERE id = ?",
                (new_idx, row_id)
            )

        self._conn.commit()
        self._save_faiss()

    def embedding_count(self, person_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM embeddings WHERE person_id = ?", (person_id,)
        ).fetchone()
        return row[0] if row else 0

    def voice_embedding_count(self, person_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM voice_embeddings WHERE person_id = ?", (person_id,)
        ).fetchone()
        return row[0] if row else 0

    # ── Greeting data ─────────────────────────────────────────────────────────
    def update_last_seen(self, person_id: str):
        """Stamp the current time as last_seen for a person."""
        self._conn.execute(
            "UPDATE persons SET last_seen = ? WHERE id = ?",
            (time.time(), person_id)
        )
        self._conn.commit()

    def update_language(self, person_id: str, language: str):
        """Persist the detected preferred language for a person."""
        self._conn.execute(
            "UPDATE persons SET preferred_language = ? WHERE id = ?",
            (language, person_id)
        )
        self._conn.commit()

    def update_person_name(self, person_id: str, new_name: str):
        """Correct the display name for a person."""
        self._conn.execute(
            "UPDATE persons SET name = ? WHERE id = ?",
            (new_name, person_id)
        )
        self._conn.commit()

    def update_person_type(self, person_id: str, new_type: str) -> None:
        """Update the person_type for a person (e.g. 'stranger' → 'known')."""
        self._conn.execute(
            "UPDATE persons SET person_type = ? WHERE id = ?",
            (new_type, person_id),
        )
        self._conn.commit()

    def get_system_identity(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM system_identity WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def set_system_identity(
        self, key: str, value: str,
        set_by: str | None = None,
        note: str | None = None,
    ) -> None:
        self._conn.execute(
            """INSERT INTO system_identity (key, value, set_by, set_at, note)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET
                   value  = excluded.value,
                   set_by = excluded.set_by,
                   set_at = excluded.set_at,
                   note   = excluded.note""",
            (key, value, set_by, time.time(), note),
        )
        self._conn.commit()

    def get_greeting_data(self, person_id: str) -> Optional[dict]:
        """Return (name, last_seen, preferred_language) for greeting generation."""
        row = self._conn.execute(
            "SELECT name, last_seen, preferred_language FROM persons WHERE id = ?",
            (person_id,)
        ).fetchone()
        if not row:
            return None
        return {"name": row[0], "last_seen": row[1], "preferred_language": row[2]}


    # ── Full conversation log ─────────────────────────────────────────────────
    def log_turn(
        self,
        person_id: str,
        role: str,
        content: str,
        *,
        room_session_id: "str | None" = None,
        audience_ids:    "list[str] | None" = None,
    ) -> None:
        """Append one message to the permanent conversation log.

        Session 107 Phase 3A.6 Part 3 — optional kwargs for Q3 hybrid
        history. ``room_session_id`` identifies the room/group context
        this turn belongs to; ``audience_ids`` is the list of
        person_ids who can see the turn. Both default to None so every
        existing caller's signature is preserved — only the future 3B
        RoomOrchestrator supplies them. When caller omits them,
        legacy single-speaker rows are created (visible to person_id
        only, untagged room_session_id — the backfill pass at
        __init__ fills these on next startup).
        """
        if config.RETENTION_MODE == "ephemeral":
            return  # SB.5: retention-gated — no transcript capture under ephemeral
        _aud_json = None
        if audience_ids is not None:
            import json as _json_lt
            _aud_json = _json_lt.dumps(list(audience_ids))
        self._conn.execute(
            "INSERT INTO conversation_log "
            "(person_id, role, content, room_session_id, audience_ids) "
            "VALUES (?, ?, ?, ?, ?)",
            (person_id, role, content, room_session_id, _aud_json),
        )
        self._conn.commit()
        # P0.0.7 H8 — emit memory_write event after successful INSERT via
        # safe_emit_sync (single P0.4-annotated except lives inside helper).
        from core.event_log import safe_emit_sync, MemoryWritePayload
        safe_emit_sync(
            "memory_write",
            MemoryWritePayload(
                person_id=person_id,
                role=role,
                text=content,
                room_session_id=room_session_id,
                audience_ids=tuple(audience_ids) if audience_ids is not None else None,
            ),
            session_id=person_id,
            room_session_id=room_session_id,
        )

    def load_conversation_history(self, person_id: str) -> list[dict]:
        """Load the most recent CONVERSATION_HISTORY_LIMIT turns, oldest first.

        Older turns remain in the DB and are retrievable on demand via search_conversation()
        (used by the LLM's search_memory tool). User messages are prefixed with a
        human-readable timestamp so the LLM can answer "when did we talk about X?" questions.
        A session-break marker is inserted between turns separated by > 4 hours
        so the LLM understands conversation boundaries.
        """
        rows = self._conn.execute(
            "SELECT role, content, ts FROM conversation_log WHERE person_id = ? "
            "ORDER BY ts DESC LIMIT ?",
            (person_id, CONVERSATION_HISTORY_LIMIT),
        ).fetchall()

        # Wave 6 Item 21: supplement with archived turns when the archive exists.
        archive_path = self._archive_db_path()
        if CONVERSATION_ARCHIVE_ENABLED and archive_path.exists():
            try:
                _ac = sqlite3.connect(
                    str(archive_path), check_same_thread=False,
                    isolation_level="IMMEDIATE",  # P0.9.1 Imp-1
                )
                arch_rows = _ac.execute(
                    "SELECT role, content, ts FROM conversation_log WHERE person_id = ? "
                    "ORDER BY ts DESC LIMIT ?",
                    (person_id, CONVERSATION_HISTORY_LIMIT),
                ).fetchall()
                _ac.close()
                combined = sorted(list(rows) + list(arch_rows), key=lambda r: r[2], reverse=True)
                rows = combined[:CONVERSATION_HISTORY_LIMIT]
            except Exception as _e:
                print(f"[FaceDB] archive load failed: {_e!r}")

        rows = list(reversed(rows))  # restore chronological order

        _SESSION_GAP = 4 * 3600  # 4 hours = new session

        messages: list[dict] = []
        prev_ts: float | None = None

        for role, content, ts in rows:
            # Insert a session break marker when there is a large gap between turns
            if prev_ts is not None and (ts - prev_ts) > _SESSION_GAP:
                dt = datetime.datetime.fromtimestamp(ts)
                label = dt.strftime("%Y-%m-%d %A %H:%M")
                messages.append({"role": "user",      "content": f"[New session — {label}]"})
                messages.append({"role": "assistant", "content": "Got it."})

            if role == "user":
                dt = datetime.datetime.fromtimestamp(ts)
                ts_label = dt.strftime("[%Y-%m-%d %a %H:%M]")
                content = f"{ts_label} {content}"

            messages.append({"role": role, "content": content})
            prev_ts = ts

        return messages

    def get_person_id_by_name(self, name: str) -> str | None:
        """Return person_id for the first person whose name matches case-insensitively."""
        row = self._conn.execute(
            "SELECT id FROM persons WHERE LOWER(name) = LOWER(?) LIMIT 1",
            (name,),
        ).fetchone()
        return row[0] if row else None

    def count_room_turns(self, room_session_id: str) -> int:
        """Phase 3B.5 — count non-NULL rows tagged with this room_session_id.

        Drives the SEARCH_ROOM_MEMORY_MIN_TURNS gate — brain's room-search
        tool returns empty + hint when the room is still too young for
        useful results. Queryable independently so pipeline can also use
        it for tool-description hints ("room has N turns so far").
        """
        if not room_session_id:
            return 0
        row = self._conn.execute(
            "SELECT COUNT(*) FROM conversation_log "
            "WHERE room_session_id = ?",
            (room_session_id,),
        ).fetchone()
        return int(row[0]) if row else 0

    def get_recent_room_conversation(
        self,
        room_session_id: str,
        requester_pid: str,
        best_friend_id: "str | None",
        limit: int = 10,
    ) -> "list[dict]":
        """P0.S7 D-A — return last ``limit`` turns from ``conversation_log``
        scoped to ``room_session_id``, filtered by audience visibility (T-B
        option β) with best_friend owner override (P1 option ii), with safe
        SQLite LIKE-escape on requester_pid (CRITICAL 1).

        Visibility rules (composed in SQL for one round-trip):
          - ``best_friend_id == requester_pid`` → owner override; sees ALL
            rows under the room_session_id regardless of audience_ids.
          - ``audience_ids IS NULL`` → legacy backfill row, default-visible.
          - ``audience_ids`` LIKE-substring contains the requester pid
            (quote-bounded + ESCAPE '\\' for safe `_` handling).

        Returns ordered list (oldest-first via ``ORDER BY ts ASC``) of
        ``{person_id, role, text, ts, audience_ids, addressed_to}`` dicts.

        Returns ``[]`` on:
          - ``room_session_id`` None / empty (no exception)
          - ``sqlite3.OperationalError`` (logged)
          - no matching rows

        Plan v2 §5.
        """
        if not room_session_id:
            return []
        escaped_pid = _escape_like_pid(requester_pid)
        try:
            rows = self._conn.execute(
                # CRITICAL 1 — ESCAPE '\\' clause activates backslash as
                # the escape character; the Python-side _escape_like_pid
                # has already double-escaped \\, _, %.  Two binds for the
                # same conceptual pid: equality vs LIKE-substring.
                "SELECT person_id, role, content, ts, audience_ids "
                "FROM conversation_log "
                "WHERE room_session_id = :room_session_id "
                "  AND ( "
                "    (:best_friend_id IS NOT NULL "
                "       AND :requester_pid = :best_friend_id) "
                "    OR audience_ids IS NULL "
                "    OR audience_ids LIKE '%\"' || :escaped_pid || '\"%' "
                "       ESCAPE '\\' "
                "  ) "
                "ORDER BY ts ASC LIMIT :limit",
                {
                    "room_session_id": room_session_id,
                    "best_friend_id":  best_friend_id,
                    "requester_pid":   requester_pid,
                    "escaped_pid":     escaped_pid,
                    "limit":           limit,
                },
            ).fetchall()
        except sqlite3.OperationalError as e:
            print(f"[FaceDB] get_recent_room_conversation OperationalError: {e!r}")
            return []
        results: list[dict] = []
        import json as _json_grc
        for pid, role, content, ts, aud_json in rows:
            try:
                audience = _json_grc.loads(aud_json) if aud_json else None
            except Exception:
                audience = None
            results.append({
                "person_id":    pid,
                "role":         role,
                "text":         content,
                "ts":           ts,
                "audience_ids": audience,
                "addressed_to": None,  # field reserved; future room_log JOIN
            })
        return results

    def get_recent_audience_rooms(
        self,
        requester_pid: str,
        best_friend_id: "str | None" = None,
        hours_back: float = 24.0,
        limit: int = 5,
    ) -> "list[str]":
        """P0.S7.5 D2 — return distinct ``room_session_id``s from the past
        ``hours_back`` window where ``requester_pid`` appears in
        ``audience_ids`` OR requester IS ``best_friend`` (owner override
        per 3A.4.6). Most-recent first; capped at ``limit``.

        Used by ``RoomOrchestrator.build_shared_context_block`` when the
        current scene is single-person but the owner returns and asks
        about prior multi-person rooms. Without this widening, the
        SHARED CONTEXT block gate fires "single_person → skip" and the
        persisted room history is invisible (canary 2026-05-19 root
        cause #2).

        Visibility composition mirrors ``get_recent_room_conversation``:
          - ``best_friend_id == requester_pid`` (owner override) → all
            rooms regardless of audience
          - ``audience_ids`` LIKE-substring contains requester pid
            (CRITICAL 1 ESCAPE clause for safe ``_`` handling)
          - ``audience_ids IS NULL`` (legacy backfill) → default-visible

        Returns ``[]`` on empty result OR ``sqlite3.OperationalError``.
        """
        if not requester_pid:
            return []
        _cutoff_ts = time.time() - (hours_back * 3600.0)
        escaped_pid = _escape_like_pid(requester_pid)
        try:
            rows = self._conn.execute(
                "SELECT room_session_id, MAX(ts) AS max_ts "
                "FROM conversation_log "
                "WHERE ts >= :cutoff_ts "
                "  AND room_session_id IS NOT NULL "
                "  AND ( "
                "    (:best_friend_id IS NOT NULL "
                "       AND :requester_pid = :best_friend_id) "
                "    OR audience_ids IS NULL "
                "    OR audience_ids LIKE '%\"' || :escaped_pid || '\"%' "
                "       ESCAPE '\\' "
                "  ) "
                "GROUP BY room_session_id "
                "ORDER BY max_ts DESC LIMIT :limit",
                {
                    "cutoff_ts":       _cutoff_ts,
                    "best_friend_id":  best_friend_id,
                    "requester_pid":   requester_pid,
                    "escaped_pid":     escaped_pid,
                    "limit":           limit,
                },
            ).fetchall()
        except sqlite3.OperationalError as e:
            print(f"[FaceDB] get_recent_audience_rooms OperationalError: {e!r}")
            return []
        return [row[0] for row in rows if row[0]]


    def search_room_turns(
        self,
        room_session_id: str,
        keyword: str,
        requester_pid: "str | None" = None,
        limit: int = 20,
    ) -> list[dict]:
        """Phase 3B.5 — audience-filtered keyword search across all
        conversation_log rows tagged with the given ``room_session_id``.

        Unlike ``search_conversation`` (per-person), this scopes the
        search to a ROOM — interleaving turns from all speakers who
        participated. ``requester_pid`` scopes visibility via the
        Session 107 Phase 3A.6 ``audience_ids`` column:

          - ``audience_ids IS NULL`` → default-visible to everyone (legacy
            pre-Session-107 rows + any row logged without the kwarg).
          - ``audience_ids`` contains ``requester_pid`` (JSON array) →
            visible to that speaker.
          - ``audience_ids`` is a non-empty JSON array that does NOT
            contain ``requester_pid`` → hidden.
          - ``requester_pid`` None → pass-through (internal synthesis
            paths that don't need the filter).

        Returns list of dicts with ``ts`` (unix), ``role``, ``content``,
        ``person_id`` (speaker). Caller is responsible for name lookup
        + human-readable rendering (keeps this method pure over the
        log schema).

        Keyword match is case-insensitive substring (``LOWER(content)
        LIKE ?``). Matches most-recent-first for readable rendering.
        """
        if not room_session_id or not keyword:
            return []
        rows = self._conn.execute(
            "SELECT ts, role, content, person_id, audience_ids "
            "FROM conversation_log "
            "WHERE room_session_id = ? AND LOWER(content) LIKE LOWER(?) "
            "ORDER BY ts DESC LIMIT ?",
            (room_session_id, f"%{keyword}%", limit),
        ).fetchall()
        results: list[dict] = []
        import json as _json_srt
        for ts, role, content, person_id, aud_json in rows:
            # Audience filter (Python-side because SQLite JSON1 may not
            # be available on every SQLite build). `aud_json IS NULL`
            # means default-visible; non-null is a JSON array that
            # requester must appear in.
            if requester_pid is not None and aud_json is not None:
                try:
                    audience = _json_srt.loads(aud_json) or []
                except Exception:
                    audience = []
                if audience and requester_pid not in audience:
                    continue
            results.append({
                "ts":         ts,
                "role":       role,
                "content":    content,
                "person_id":  person_id,
            })
        return results

    def search_conversation(self, person_id: str, keyword: str, limit: int = 4) -> list[dict]:
        """Search conversation_log for turns containing keyword (case-insensitive).

        Returns most-recent matching turns first, each excerpt truncated to 200 chars.
        Also searches the conversation archive when CONVERSATION_ARCHIVE_ENABLED (Wave 6 Item 21).
        """
        rows = self._conn.execute(
            """SELECT role, content, ts
               FROM conversation_log
               WHERE person_id = ? AND LOWER(content) LIKE LOWER(?)
               ORDER BY ts DESC LIMIT ?""",
            (person_id, f"%{keyword}%", limit),
        ).fetchall()

        archive_path = self._archive_db_path()
        if CONVERSATION_ARCHIVE_ENABLED and archive_path.exists():
            try:
                _ac = sqlite3.connect(
                    str(archive_path), check_same_thread=False,
                    isolation_level="IMMEDIATE",  # P0.9.1 Imp-1
                )
                arch_rows = _ac.execute(
                    "SELECT role, content, ts FROM conversation_log "
                    "WHERE person_id = ? AND LOWER(content) LIKE LOWER(?) "
                    "ORDER BY ts DESC LIMIT ?",
                    (person_id, f"%{keyword}%", limit),
                ).fetchall()
                _ac.close()
                combined = sorted(list(rows) + list(arch_rows), key=lambda r: r[2], reverse=True)
                rows = combined[:limit]
            except Exception as _e:
                print(f"[FaceDB] archive search failed: {_e!r}")

        results = []
        for role, content, ts in rows:
            dt = datetime.datetime.fromtimestamp(ts)
            ts_label = dt.strftime("[%Y-%m-%d %a %H:%M]")
            excerpt = content[:200] + ("…" if len(content) > 200 else "")
            results.append({"role": role, "ts_label": ts_label, "excerpt": excerpt})
        return results

    # ── Visitor log ───────────────────────────────────────────────────────────
    def log_visitor_sighting(self, note: str = None) -> None:
        """Record an unknown-person sighting in the visitor log."""
        if config.RETENTION_MODE == "ephemeral":
            return  # SB.5: retention-gated — no visitor-sighting capture under ephemeral
        self._conn.execute("INSERT INTO visitor_log (note) VALUES (?)", (note,))
        self._conn.commit()

    def get_recent_visitor_sightings(self, days: int = 90) -> list[dict]:
        """Return visitor sightings from the last `days` days, newest first."""
        cutoff = time.time() - days * 86400
        rows = self._conn.execute(
            "SELECT ts, note FROM visitor_log WHERE ts > ? ORDER BY ts DESC",
            (cutoff,),
        ).fetchall()
        return [{"ts": r[0], "note": r[1]} for r in rows]

    # ── Voice embeddings ──────────────────────────────────────────────────────
    def add_voice_embedding(self, person_id: str, embedding,
                            source: str = "legacy_unknown", confidence: float = 0.0) -> bool:
        """Add one voice embedding using diversity-based gallery management.

        Returns False if the gallery is full or the sample is too similar to an
        existing one (same mic distance/condition already covered).

        First N_INITIAL_VOICE embeddings bypass diversity (enrollment baseline).
        Beyond that: only stored if cosine similarity to every existing embedding
        is below VOICE_DIVERSITY_THRESHOLD — i.e. it covers a new condition.

        P0.S7.5.2 D3: also enforces centroid-distance gate once the gallery
        has ≥ VOICE_CENTROID_GATE_MIN_SAMPLES — proposed embedding must cosine
        ≥ VOICE_SELF_UPDATE_CENTROID_MIN to the current gallery centroid.
        Mirrors face-gallery's Session 51 SELF_UPDATE_CENTROID_MIN discipline;
        prevents the slow centroid drift that produced canary 3's Jagan
        v_score 0.3-0.4 against his own mature profile.
        """
        if config.ENROLLMENT_MODE != "persistent":
            return False  # SB.5: enrollment-gated — voice recognition template not persisted under transient/none
        emb = np.asarray(embedding, dtype=np.float32)

        rows = self._conn.execute(
            "SELECT vector FROM voice_embeddings WHERE person_id = ?", (person_id,)
        ).fetchall()
        count = len(rows)

        if count >= MAX_VOICE_EMBEDDINGS:
            return False

        # Diversity check: skip if this voice condition is already represented
        if count >= N_INITIAL_VOICE:
            for (vec_bytes,) in rows:
                existing = np.frombuffer(vec_bytes, dtype=np.float32).copy()
                if float(np.dot(emb, existing)) > VOICE_DIVERSITY_THRESHOLD:
                    return False  # too similar to an existing sample — skip

        # P0.S7.5.2 D3 — centroid-distance gate. Recomputes the centroid per
        # add via np.mean(embeddings, axis=0) + L2-normalize. O(N≤50) at <5ms
        # on dev CPU; negligible relative to upstream ECAPA embed (~50ms).
        # Plan v2 §3.1 LOCKED recompute (NOT cache): cache-invalidation would
        # require enumerating 6+ gallery-write sites (this method, delete_person,
        # prune_old_strangers, prune_zero_value_stranger, prune_stale_stranger_voice,
        # factory reset paths) and AST-asserting every site invalidates — same
        # inverse-check discipline as P0.5's PAIRED_WRITE_METHODS. Not worth
        # it for ~5ms saved on a rare event. If profiling later shows centroid-
        # recompute as a hot spot, revisit with bench numbers. Bootstrap-safe:
        # gate only fires once the gallery has ≥ VOICE_CENTROID_GATE_MIN_SAMPLES
        # so early enrollment isn't blocked by an unstable centroid.
        from core.config import (
            VOICE_SELF_UPDATE_CENTROID_MIN,
            VOICE_CENTROID_GATE_MIN_SAMPLES,
        )
        if count >= VOICE_CENTROID_GATE_MIN_SAMPLES:
            existing_embeddings = [
                np.frombuffer(r[0], dtype=np.float32).copy() for r in rows
            ]
            centroid = np.mean(existing_embeddings, axis=0).astype(np.float32)
            norm = float(np.linalg.norm(centroid))
            if norm > 0:
                centroid = centroid / norm
                cosine_to_centroid = float(np.dot(emb, centroid))
                if cosine_to_centroid < VOICE_SELF_UPDATE_CENTROID_MIN:
                    print(
                        f"[Voice] Skipped accum for {person_id}: "
                        f"centroid-distance {cosine_to_centroid:.3f} < "
                        f"{VOICE_SELF_UPDATE_CENTROID_MIN}"
                    )
                    return False

        self._conn.execute(
            "INSERT INTO voice_embeddings (person_id, vector, captured_at, source, confidence_at_write)"
            " VALUES (?, ?, ?, ?, ?)",
            (person_id, emb.tobytes(), time.time(), source, confidence),
        )
        self._conn.commit()
        return True

    def load_voice_profile_for(self, person_id: str) -> "np.ndarray | None":
        """Return the mean L2-normalized voice embedding for one person, or None if no data."""
        import numpy as np
        rows = self._conn.execute(
            "SELECT vector FROM voice_embeddings WHERE person_id = ?", (person_id,)
        ).fetchall()
        if not rows:
            return None
        embeddings = [np.frombuffer(r[0], dtype=np.float32).copy() for r in rows]
        mean_emb = np.mean(embeddings, axis=0).astype(np.float32)
        norm = np.linalg.norm(mean_emb)
        if norm > 0:
            mean_emb /= norm
        return mean_emb

    def load_voice_profiles(self) -> dict:
        """Return {person_id: mean_L2_normalized_embedding} for all persons with voice data."""
        import numpy as np
        rows = self._conn.execute(
            "SELECT person_id, vector FROM voice_embeddings"
        ).fetchall()
        by_person: dict[str, list] = {}
        for person_id, vector_bytes in rows:
            emb = np.frombuffer(vector_bytes, dtype=np.float32).copy()
            by_person.setdefault(person_id, []).append(emb)
        profiles: dict = {}
        for person_id, embeddings in by_person.items():
            mean_emb = np.mean(embeddings, axis=0).astype(np.float32)
            norm = np.linalg.norm(mean_emb)
            if norm > 0:
                mean_emb /= norm
            profiles[person_id] = mean_emb
        return profiles

    def load_voice_profile_sizes(self) -> dict:
        """Return {person_id: sample_count} for all persons with voice data."""
        rows = self._conn.execute(
            "SELECT person_id, COUNT(*) FROM voice_embeddings GROUP BY person_id"
        ).fetchall()
        return {pid: cnt for pid, cnt in rows}

    def count_voice_embeddings(self, person_id: str) -> int:
        """Authoritative count of voice samples for a given person.

        Obs 1 (2026-04-20 post-review): used as DB-backed fallback when the
        in-memory cache (pipeline._voice_gallery_sizes) might be stale — e.g.,
        after an out-of-process delete_person() call from the dashboard or CLI
        that clears ``voice_embeddings`` rows but not the pipeline's cache.
        Uses the existing ``voice_embeddings_person_id_idx`` → O(log n).
        """
        row = self._conn.execute(
            "SELECT COUNT(*) FROM voice_embeddings WHERE person_id = ?",
            (person_id,),
        ).fetchone()
        return row[0] if row else 0

    # ── Gallery audit / repair ────────────────────────────────────────────────

    def gallery_audit(self, person_id: str = None, sigma: float = 2.0) -> list:
        """Return per-person gallery health stats.

        If person_id is provided, audits only that person.  Otherwise audits all.
        Each result dict contains:
          total          — total embedding count
          by_source      — {source: count} breakdown
          confidences    — {min, mean, max} of confidence_at_write values
          outlier_row_ids — row IDs of embeddings whose cosine distance to the
                            person centroid exceeds mean_distance + sigma * std_distance
        """
        if person_id:
            pids = [(person_id,)]
        else:
            pids = self._conn.execute("SELECT DISTINCT person_id FROM embeddings").fetchall()

        results = []
        for (pid,) in pids:
            rows = self._conn.execute(
                "SELECT id, vector, source, confidence_at_write FROM embeddings WHERE person_id = ?",
                (pid,)
            ).fetchall()
            if not rows:
                continue

            # Per-source counts
            by_source: dict = {}
            confs: list[float] = []
            embeddings: list[np.ndarray] = []
            row_ids: list[int] = []

            for row_id, vec_bytes, src, conf in rows:
                by_source[src] = by_source.get(src, 0) + 1
                confs.append(conf)
                if vec_bytes is not None:
                    emb = np.frombuffer(vec_bytes, dtype=np.float32).copy()
                    embeddings.append(emb)
                    row_ids.append(row_id)

            # Outlier detection via cosine distance to centroid
            outlier_ids: list[int] = []
            if len(embeddings) >= 3:
                mat = np.stack(embeddings, axis=0)  # (N, 512)
                centroid = mat.mean(axis=0)
                norm = np.linalg.norm(centroid)
                if norm > 0:
                    centroid /= norm
                similarities = mat @ centroid  # cosine similarity (already L2-normalized)
                distances = 1.0 - similarities
                mean_d = float(distances.mean())
                std_d  = float(distances.std())
                cutoff = mean_d + sigma * std_d
                outlier_ids = [row_ids[i] for i, d in enumerate(distances) if d > cutoff]

            name_row = self._conn.execute("SELECT name FROM persons WHERE id = ?", (pid,)).fetchone()
            results.append({
                "person_id":      pid,
                "name":           name_row[0] if name_row else pid,
                "total":          len(rows),
                "by_source":      by_source,
                "confidences":    {
                    "min":  min(confs),
                    "mean": sum(confs) / len(confs),
                    "max":  max(confs),
                } if confs else {},
                "outlier_row_ids": outlier_ids,
            })
        return results

    def prune_outlier_embeddings(self, person_id: str, sigma: float = 2.0) -> int:
        """Remove face embeddings that are geometric outliers (> sigma from centroid).

        Returns the number of rows deleted.  Rebuilds FAISS index afterward.
        Safe no-op when the person has < 3 embeddings (not enough for statistics).
        """
        audit = self.gallery_audit(person_id, sigma=sigma)
        if not audit:
            return 0
        outlier_ids = audit[0]["outlier_row_ids"]
        if not outlier_ids:
            return 0
        ph = ",".join("?" * len(outlier_ids))
        # P0.5: SQL durable, FAISS derived; boot reconciliation handles divergence.
        with self._index_lock:
            with self.transaction():
                self._conn.execute(f"DELETE FROM embeddings WHERE id IN ({ph})", outlier_ids)
            try:
                self._rebuild_faiss()
            except Exception as e:
                print(f"[FaceDB] FAISS rebuild failed after prune_outlier_embeddings; will reconcile on next boot: {e!r}")
                self._mark_faiss_dirty()
                raise
        return len(outlier_ids)

    def checkpoint_wal(self) -> None:
        """Flush the WAL into the main DB file (TRUNCATE mode).

        Called at the end of each dream cycle so the -wal sidecar stays
        small and backup copies are self-contained."""
        try:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception as _e:
            print(f"[FaceDB] WAL checkpoint failed: {_e!r}")

    def wipe(self):
        """Factory reset — clear everything including system identity."""
        self._conn.executescript("""
            DELETE FROM embeddings;
            DELETE FROM voice_embeddings;
            DELETE FROM persons;
            DELETE FROM conversation_log;
            DELETE FROM visitor_log;
            DELETE FROM system_identity;
            DELETE FROM silent_observations;
        """)
        # Re-insert the default system_name row so the key always exists
        self._conn.execute(
            "INSERT OR IGNORE INTO system_identity (key, value, set_at, note) VALUES (?, ?, ?, ?)",
            ("system_name", DEFAULT_SYSTEM_NAME, time.time(), "default"),
        )
        self._conn.commit()
        self.index      = faiss.IndexFlatIP(EMBEDDING_DIM)
        self._idx_to_person = {}
        self._save_faiss()

    def close(self) -> None:
        """Close the SQLite connection.

        Idempotent wrapper — call sites (pipeline factory-reset, shutdown)
        need no try/except. The CLEANUP swallow lives here so the boundary
        is one place.
        """
        try:
            self._conn.close()
        except Exception:
            pass  # CLEANUP: connection may already be closed (double-shutdown or wipe_all race)


def wipe_all() -> None:
    """
    Full factory reset — delete all runtime data files from disk.
    Caller must close any open FaceDB / BrainOrchestrator before calling this,
    then re-instantiate them after it returns.
    Each deletion is independent: a missing file is not an error.

    P0.S2 preservation invariant: `.dashboard_token` is INTENTIONALLY NOT
    deleted by this function. The dashboard's authentication token survives
    factory reset because re-issuing the auth URL on every reset is hostile
    UX and the token is single-user-scoped (one machine, one user — no
    cross-tenant risk). The .dashboard_auth_url file (one-shot) is also
    preserved here; it auto-deletes on first /api/auth success. If a future
    spec needs token rotation, add it as an explicit
    `rotate_dashboard_token()` function, not via this catch-all.
    """
    # faces.db (+ WAL siblings)
    for suffix in ("", "-shm", "-wal"):
        p = Path(str(DB_PATH) + suffix)
        try:
            p.unlink(missing_ok=True)
        except Exception as e:
            print(f"[Reset] Could not delete {p.name}: {e}")

    # faiss index
    try:
        FAISS_INDEX_PATH.unlink(missing_ok=True)
    except Exception as e:
        print(f"[Reset] Could not delete faiss.index: {e}")

    # brain.db (+ WAL siblings)
    for suffix in ("", "-shm", "-wal"):
        p = Path(str(BRAIN_DB_PATH) + suffix)
        try:
            p.unlink(missing_ok=True)
        except Exception as e:
            print(f"[Reset] Could not delete {p.name}: {e}")

    # Kuzu graph — single file on Windows, directory on Linux
    gp = Path(GRAPH_DB_PATH)
    if gp.is_dir():
        try:
            shutil.rmtree(gp, ignore_errors=True)
        except Exception as e:
            print(f"[Reset] Could not delete brain_graph/: {e}")
    else:
        try:
            gp.unlink(missing_ok=True)
        except Exception as e:
            print(f"[Reset] Could not delete brain_graph: {e}")
    # Kuzu WAL companion file
    for suffix in (".wal", "-lock"):
        gw = Path(str(GRAPH_DB_PATH) + suffix)
        try:
            gw.unlink(missing_ok=True)
        except Exception as e:
            print(f"[Reset] Could not delete brain_graph{suffix}: {e}")

    # All face photos in faces/
    for photo in FACES_DIR.glob("*.jpg"):
        try:
            photo.unlink(missing_ok=True)
        except Exception as e:
            print(f"[Reset] Could not delete {photo.name}: {e}")

    # Transient request/result files
    for f in (ENROLL_REQUEST_FILE, ENROLL_RESULT_FILE,
              RESET_REQUEST_FILE, RESET_RESULT_FILE):
        try:
            f.unlink(missing_ok=True)
        except Exception as e:
            print(f"[Reset] Could not delete {f.name}: {e}")

    # sim_runner.py session state (stores turn counter for batch simulation)
    # Must be deleted so sim_runner.py starts fresh from turn 1 after reset.
    sim_state = FACES_DIR.parent / "sim_session_state.json"
    try:
        sim_state.unlink(missing_ok=True)
    except Exception as e:
        print(f"[Reset] Could not delete sim_session_state.json: {e}")

    # P0.S11 D2 — Post-wipe summary so callers (CLI, dashboard, pipeline IPC)
    # see a clear log of what was deleted vs preserved. Without this, wipe_all
    # is silent on success — the 2026-05-27 canary surfaced exactly this
    # diagnostic gap (Jagan thought factory reset had run; no log proved it).
    # Probe Path.exists() post-call (NOT pre-call enumeration) so the count
    # reflects ACTUAL deletions — files that failed to delete (per-line WARN
    # logged above) will show up as "still present" in the summary.
    _DELETED_PROBE_TARGETS = (
        (str(DB_PATH), "faces.db"),
        (str(DB_PATH) + "-shm", "faces.db-shm"),
        (str(DB_PATH) + "-wal", "faces.db-wal"),
        (str(FAISS_INDEX_PATH), "faiss.index"),
        (str(BRAIN_DB_PATH), "brain.db"),
        (str(BRAIN_DB_PATH) + "-shm", "brain.db-shm"),
        (str(BRAIN_DB_PATH) + "-wal", "brain.db-wal"),
        (str(GRAPH_DB_PATH), "brain_graph"),
        (str(FACES_DIR.parent / "sim_session_state.json"), "sim_session_state.json"),
    )
    _PRESERVED_PROBE_TARGETS = (
        (str(FACES_DIR / ".dashboard_token"), ".dashboard_token"),
        (str(FACES_DIR / ".dashboard_auth_url"), ".dashboard_auth_url"),
    )
    _deleted_count = sum(1 for path, _ in _DELETED_PROBE_TARGETS if not Path(path).exists())
    _total_targets = len(_DELETED_PROBE_TARGETS)
    _photos_remaining = sum(1 for _ in FACES_DIR.glob("*.jpg"))
    _preserved_count = sum(1 for path, _ in _PRESERVED_PROBE_TARGETS if Path(path).exists())
    print(
        f"[Reset] Summary: deleted {_deleted_count}/{_total_targets} target(s) + "
        f"{_photos_remaining} photo(s) remaining (expected 0); "
        f"preserved {_preserved_count}/{len(_PRESERVED_PROBE_TARGETS)} (P0.S2 invariant)"
    )
    # Verbose enumeration for diagnostic clarity
    print("[Reset] Deleted targets:")
    for path, name in _DELETED_PROBE_TARGETS:
        status = "  \u2713 gone" if not Path(path).exists() else "  \u2717 STILL PRESENT (delete failed)"
        print(f"  {status}: {name}")
    print("[Reset] Preserved targets (per P0.S2 invariant):")
    for path, name in _PRESERVED_PROBE_TARGETS:
        status = "  \u2713 kept" if Path(path).exists() else "  \u00b7 absent (not present at start)"
        print(f"  {status}: {name}")

    print("[Reset] All data files deleted.")
