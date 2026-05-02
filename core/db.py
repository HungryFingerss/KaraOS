"""
vision/db.py — SQLite + FAISS face database
Stores person metadata in SQLite, embeddings in FAISS index.
"""
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
)


VALID_EMBEDDING_SOURCES: frozenset[str] = frozenset({
    "enrollment",           # explicit human-supervised capture
    "recognition_update",   # self-update from live recognition
    "progressive_enroll",   # gate-pass during active session
    "legacy_unknown",       # one-time migration only — do not use in new code
})


class FaceDB:
    def __init__(self, db_path: str = None, faiss_path: "Path | str | None" = None):
        path = db_path if db_path is not None else str(DB_PATH)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._index_lock = threading.RLock()
        # Allow callers (tests, dashboard) to supply a separate FAISS path so they
        # never accidentally overwrite the production faces/faiss.index file.
        self._faiss_path: Path = Path(faiss_path) if faiss_path is not None else FAISS_INDEX_PATH
        self._init_tables()
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
        # Schema migration: add provenance columns to existing databases
        for _col, _defn in (
            ("source",             "TEXT NOT NULL DEFAULT 'legacy_unknown'"),
            ("confidence_at_write", "REAL NOT NULL DEFAULT 0.0"),
        ):
            for _tbl in ("embeddings", "voice_embeddings"):
                try:
                    self._conn.execute(f"ALTER TABLE {_tbl} ADD COLUMN {_col} {_defn}")
                except sqlite3.OperationalError:
                    pass  # column already exists
        self._conn.commit()

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
        # Drop legacy table that was replaced by brain.db (idempotent).
        self._conn.execute("DROP TABLE IF EXISTS conversation_memory")

        # Migrate existing DBs: add columns if they don't exist yet.
        # SQLite doesn't support ALTER TABLE ADD COLUMN IF NOT EXISTS,
        # so we attempt each and swallow the error if already present.
        for col_sql in (
            "ALTER TABLE persons ADD COLUMN last_seen REAL",
            "ALTER TABLE persons ADD COLUMN preferred_language TEXT NOT NULL DEFAULT 'en'",
            "ALTER TABLE embeddings ADD COLUMN vector BLOB",
            "ALTER TABLE persons ADD COLUMN person_type TEXT NOT NULL DEFAULT 'known'",
            # Session 107 Phase 3A.6 Part 3 — Q3 hybrid history columns.
            # room_session_id groups turns by room/group context (3B
            # RoomOrchestrator uses it to retrieve "what was discussed
            # in this room session"). audience_ids is a JSON array of
            # person_ids who can see the turn — consumed by 3B
            # visibility filtering at retrieval time. Additive, nullable;
            # not wired into any retrieval path yet.
            "ALTER TABLE conversation_log ADD COLUMN room_session_id TEXT",
            "ALTER TABLE conversation_log ADD COLUMN audience_ids TEXT",
        ):
            try:
                self._conn.execute(col_sql)
            except sqlite3.OperationalError:
                pass  # column already exists

        # Session 107 Phase 3A.6 Part 3 — index for room-history retrieval.
        # (room_session_id, ts DESC) covers the typical 3B query pattern
        # "most recent N turns in this room session." No effect until
        # room_session_id is populated; harmless to create now.
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conv_log_room "
            "ON conversation_log(room_session_id, ts DESC)"
        )

        # Session 107 Phase 3A.6 Part 3 — one-shot backfill for rows
        # that predate the schema addition. Deterministic defaults
        # preserve single-person semantics: each pre-migration turn
        # gets a synthetic room_session_id keyed by (person_id,
        # first-turn ts) and audience_ids = [person_id] so the turn is
        # visible only to that person. No-op after first run (WHERE
        # clause catches nothing once populated).
        _null_room = self._conn.execute(
            "SELECT COUNT(*) FROM conversation_log WHERE room_session_id IS NULL"
        ).fetchone()[0]
        if _null_room:
            import json as _json_bfill
            # Compute per-person first turn ts (used as session marker).
            _first_ts_rows = self._conn.execute(
                "SELECT person_id, MIN(ts) FROM conversation_log "
                "WHERE room_session_id IS NULL GROUP BY person_id"
            ).fetchall()
            for _pid, _first_ts in _first_ts_rows:
                _rsid = f"{_pid}_{int(_first_ts or 0)}"
                _aud  = _json_bfill.dumps([_pid])
                self._conn.execute(
                    "UPDATE conversation_log "
                    "SET room_session_id = ?, audience_ids = ? "
                    "WHERE person_id = ? AND room_session_id IS NULL",
                    (_rsid, _aud, _pid),
                )
            print(
                f"[FaceDB] Backfilled conversation_log for {len(_first_ts_rows)} "
                f"person(s) — added room_session_id + audience_ids to "
                f"{_null_room} legacy row(s)"
            )
        self._conn.commit()
        self._warn_missing_vectors()

    def _warn_missing_vectors(self):
        """One-time migration helper: warn if any enrolled persons lack vector BLOBs."""
        row = self._conn.execute(
            "SELECT COUNT(DISTINCT person_id) FROM embeddings WHERE vector IS NULL"
        ).fetchone()
        missing = row[0] if row else 0
        if missing > 0:
            print(f"[DB] WARNING: {missing} person(s) have no vector data and need re-enrollment")

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
        if self.index.ntotal != valid_count:
            print(
                f"[DB] FAISS out of sync: index={self.index.ntotal}, "
                f"valid_rows={valid_count}, null_rows={null_count} — rebuilding."
            )
            self._rebuild_faiss()
            return

        # Build idx → person_id map from DB
        rows = self._conn.execute(
            "SELECT faiss_idx, person_id FROM embeddings WHERE vector IS NOT NULL ORDER BY faiss_idx"
        ).fetchall()
        self._idx_to_person = {r[0]: r[1] for r in rows}

    def _save_faiss(self):
        with self._index_lock:
            faiss.write_index(self.index, str(self._faiss_path))

    # ── Enroll ────────────────────────────────────────────────────────────────
    def add_person(self, person_id: str, name: str, photo_path: str = None, person_type: str = 'known'):
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
        self._conn.execute(
            "INSERT OR IGNORE INTO persons (id, name, enrolled_at, last_seen, photo_path, person_type) "
            "VALUES (?, ?, ?, ?, ?, 'stranger')",
            (person_id, name, time.time(), time.time(), photo_path),
        )
        self._conn.commit()
        return person_id

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
    ) -> None:
        """Accumulate a silent-face sighting via online embedding mean.

        Compares the new embedding against all existing silent_observations using
        cosine similarity. If a match is found (sim > SILENT_OBS_SIMILARITY), updates
        that row's mean embedding, duration, and frame_count. Otherwise inserts a new row.
        Never creates a Person record.
        """
        emb = embedding.astype(np.float32)
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm

        now = time.time()
        cutoff = time.time() - SILENT_OBS_SCAN_DAYS * 86400
        rows = self._conn.execute(
            "SELECT id, embedding, frame_count FROM silent_observations WHERE last_seen >= ?",
            (cutoff,),
        ).fetchall()

        best_id:  str | None    = None
        best_emb: np.ndarray | None = None
        best_count: int         = 1
        best_sim: float         = -1.0

        for row_id, vec_bytes, frame_count in rows:
            existing = np.frombuffer(vec_bytes, dtype=np.float32).copy()
            sim = float(np.dot(emb, existing))
            if sim > best_sim:
                best_sim   = sim
                best_id    = row_id
                best_emb   = existing
                best_count = frame_count

        if best_id is not None and best_sim >= SILENT_OBS_SIMILARITY:
            # Online mean: new_mean = (old_mean * n + new) / (n + 1)
            # best_emb and best_count already fetched from the scan above — no second query.
            n        = best_count
            new_mean = (best_emb * n + emb) / (n + 1)
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
                      source: str = "legacy_unknown", confidence: float = 0.0) -> bool:
        """Add one face embedding for a person using diversity-based gallery management.

        Returns False if the gallery is full or the new embedding is too similar
        to an existing one (same angle/condition already covered).

        First N_INITIAL_FACE embeddings bypass diversity (enrollment baseline).
        Beyond that: only stored if cosine similarity to every existing embedding
        is below FACE_DIVERSITY_THRESHOLD — i.e. it covers a new angle or condition.
        """
        assert source in VALID_EMBEDDING_SOURCES, (
            f"add_embedding called with unknown source={source!r}. "
            f"Add it to VALID_EMBEDDING_SOURCES in db.py first."
        )
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

        with self._index_lock:
            faiss_idx = self.index.ntotal
            self.index.add(emb)
            self._idx_to_person[faiss_idx] = person_id

        self._conn.execute(
            "INSERT INTO embeddings (person_id, faiss_idx, vector, captured_at, source, confidence_at_write)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (person_id, faiss_idx, emb_1d.tobytes(), time.time(), source, confidence)
        )
        self._conn.commit()
        self._save_faiss()
        return True

    # ── Recognize ─────────────────────────────────────────────────────────────
    def recognize(self, embedding: np.ndarray, threshold: float) -> tuple[Optional[str], Optional[str], float]:
        """
        Returns (person_id, name, confidence) or (None, None, 0.0)
        """
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
        self._conn.execute("DELETE FROM embeddings WHERE person_id = ?", (person_id,))
        self._conn.execute("DELETE FROM voice_embeddings WHERE person_id = ?", (person_id,))
        self._conn.execute("DELETE FROM conversation_log WHERE person_id = ?", (person_id,))
        self._conn.execute("DELETE FROM persons WHERE id = ?", (person_id,))
        self._conn.execute(
            "UPDATE silent_observations SET matched_person_id = NULL WHERE matched_person_id = ?",
            (person_id,),
        )
        self._conn.commit()
        self._rebuild_faiss()

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
        for table in ("embeddings", "voice_embeddings", "conversation_log"):
            self._conn.execute(
                f"DELETE FROM {table} WHERE person_id IN ({placeholders})", ids
            )
        self._conn.execute(f"DELETE FROM persons WHERE id IN ({placeholders})", ids)
        self._conn.commit()
        self._rebuild_faiss()
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
        for table in ("embeddings", "voice_embeddings", "conversation_log"):
            self._conn.execute(
                f"DELETE FROM {table} WHERE person_id = ?", (person_id,)
            )
        self._conn.execute("DELETE FROM persons WHERE id = ?", (person_id,))
        self._conn.commit()
        self._rebuild_faiss()
        print(f"[FaceDB] Pruned zero-value stranger {person_id}")
        return True

    def _rebuild_faiss(self):
        """Rebuild FAISS index from SQLite vector BLOBs.

        Assigns new sequential faiss_idx values (0, 1, 2, …) and updates the DB
        to match, keeping _idx_to_person and the on-disk index in sync.
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
        """
        rows = self._conn.execute(
            """SELECT role, content, ts
               FROM conversation_log
               WHERE person_id = ? AND LOWER(content) LIKE LOWER(?)
               ORDER BY ts DESC LIMIT ?""",
            (person_id, f"%{keyword}%", limit),
        ).fetchall()
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
        """
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
        with self._index_lock:
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
        self._conn.execute(f"DELETE FROM embeddings WHERE id IN ({ph})", outlier_ids)
        self._conn.commit()
        self._rebuild_faiss()
        return len(outlier_ids)

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


def wipe_all() -> None:
    """
    Full factory reset — delete all runtime data files from disk.
    Caller must close any open FaceDB / BrainOrchestrator before calling this,
    then re-instantiate them after it returns.
    Each deletion is independent: a missing file is not an error.
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

    print("[Reset] All data files deleted.")
