"""
test_faiss_delete.py — Tests for C2: FAISS deletion data-loss bug fix.

Scenario: enroll 2 persons, delete person 1, confirm person 2 still
recognized correctly. Uses isolated temp SQLite + FAISS files so it
never touches the production database.
"""
import os
import sys
import tempfile
import numpy as np
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))


def _make_db(db_path: Path, index_path: Path):
    """Return a FaceDB backed by isolated temp files (no reload needed)."""
    import core.db as _db_mod
    with patch.object(_db_mod, "DB_PATH",         db_path), \
         patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
        db = _db_mod.FaceDB()
    # Bind paths so callers can pass them to subsequent FaceDB() opens
    return db, _db_mod


def random_embedding(seed: int) -> np.ndarray:
    """Deterministic random unit vector (512-dim)."""
    rng = np.random.default_rng(seed)
    v = rng.random(512).astype(np.float32)
    v /= np.linalg.norm(v)
    return v


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_delete_person1_keeps_person2():
    """
    Core bug scenario:
    - Enroll person_1 (3 embeddings) and person_2 (3 embeddings)
    - Delete person_1
    - person_2 must still be recognized with correct ID and name
    """
    print("\nTEST 1: delete person_1 — person_2 must survive in FAISS")

    import core.db as _db_mod

    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"

        with patch.object(_db_mod, "DB_PATH",         db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()

            # Enroll person_1 (3 embeddings)
            db.add_person("p1", "Alice")
            emb1 = [random_embedding(seed=i) for i in range(1, 4)]
            for e in emb1:
                db.add_embedding("p1", e)

            # Enroll person_2 (3 embeddings)
            db.add_person("p2", "Bob")
            emb2 = [random_embedding(seed=i) for i in range(10, 13)]
            for e in emb2:
                db.add_embedding("p2", e)

            # Sanity: both recognized before delete
            pid, _, _ = db.recognize(emb1[0], threshold=0.01)
            assert pid == "p1", f"Expected p1 before delete, got {pid}"
            pid, _, _ = db.recognize(emb2[0], threshold=0.01)
            assert pid == "p2", f"Expected p2 before delete, got {pid}"
            print("  -> both persons recognized before delete OK")

            # THE BUG SCENARIO: delete person_1
            db.delete_person("p1")

            # FAISS must have exactly 3 vectors (person_2 only)
            assert db.index.ntotal == 3, \
                f"Expected 3 vectors after delete, got {db.index.ntotal}"
            print(f"  -> FAISS ntotal = {db.index.ntotal} after delete OK")

            # person_2 must still be recognized on all 3 embeddings
            for i, e in enumerate(emb2):
                pid, name, conf = db.recognize(e, threshold=0.01)
                assert pid == "p2", \
                    f"BUG: emb2[{i}] not recognized after deleting person_1! Got pid={pid}"
                assert name == "Bob"
            print("  -> person_2 (Bob) recognized on all 3 embeddings OK")

            # person_1 must NOT be found above threshold
            pid, _, conf = db.recognize(emb1[0], threshold=0.5)
            assert pid != "p1", \
                f"BUG: deleted person_1 still recognized! conf={conf:.4f}"
            print("  -> deleted person_1 not recognized OK")
            db._conn.close()  # release SQLite lock before temp dir cleanup


def test_faiss_index_file_deleted_triggers_rebuild():
    """
    Simulate the FAISS index file being deleted (git clean, disk wipe).
    On next FaceDB() startup, _load_faiss() must rebuild from SQLite vectors.
    """
    print("\nTEST 2: deleted FAISS index file — rebuild from SQLite on startup")

    import core.db as _db_mod

    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"
        emb = random_embedding(seed=42)

        # First instance: enroll one person, then close
        with patch.object(_db_mod, "DB_PATH",         db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            db.add_person("p1", "Charlie")
            db.add_embedding("p1", emb)
            assert index_path.exists(), "FAISS index file was not written"
            db._conn.close()

        # Simulate index file loss
        index_path.unlink()
        assert not index_path.exists(), "Failed to delete index file"

        # Second instance: must auto-rebuild from SQLite
        with patch.object(_db_mod, "DB_PATH",         db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db2 = _db_mod.FaceDB()
            assert db2.index.ntotal == 1, \
                f"Expected 1 vector after rebuild, got {db2.index.ntotal}"
            pid, name, conf = db2.recognize(emb, threshold=0.01)
            assert pid == "p1", f"Expected p1 after rebuild, got pid={pid}"
            assert name == "Charlie"
            print(f"  -> Charlie recognized after index rebuild, conf={conf:.4f} OK")
            db2._conn.close()


def test_empty_db_no_spurious_rebuild():
    """
    Empty DB: FAISS ntotal=0, DB count=0. Must NOT trigger rebuild.
    """
    print("\nTEST 3: empty DB — no spurious rebuild on startup")

    import core.db as _db_mod

    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"

        with patch.object(_db_mod, "DB_PATH",         db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()

        assert db.index.ntotal == 0
        assert db._idx_to_person == {}
        db._conn.close()
        print("  -> empty DB: ntotal=0, _idx_to_person={} OK")


def test_vectors_stored_as_normalized_blobs():
    """
    After add_embedding(), the stored BLOB must be a unit vector
    that matches what's in FAISS.
    """
    print("\nTEST 4: stored BLOB decodes to correct normalized vector")

    import core.db as _db_mod
    import faiss

    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"

        with patch.object(_db_mod, "DB_PATH",         db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            db.add_person("p1", "Dave")
            # Pass an unnormalized vector — add_embedding must normalize it
            raw = random_embedding(seed=99) * 5.0
            db.add_embedding("p1", raw)

            row = db._conn.execute(
                "SELECT vector FROM embeddings WHERE person_id = 'p1'"
            ).fetchone()
            stored = np.frombuffer(row[0], dtype=np.float32)

            # Stored vector must be unit length
            norm = float(np.linalg.norm(stored))
            assert abs(norm - 1.0) < 1e-5, \
                f"Stored vector not normalized: norm={norm:.6f}"
            print(f"  -> stored vector is unit length (norm={norm:.6f}) OK")

            # Self-search must return score ~1.0
            query = stored.copy().reshape(1, -1)
            faiss.normalize_L2(query)
            scores, _ = db.index.search(query, 1)
            assert float(scores[0][0]) > 0.999, \
                f"Self-search score too low: {scores[0][0]:.4f}"
            print(f"  -> self-search score={scores[0][0]:.6f} OK")
            db._conn.close()


# ── I2: load_voice_profile_for ────────────────────────────────────────────────

def test_load_voice_profile_for_returns_mean_embedding():
    """I2: load_voice_profile_for returns the mean normalized embedding for one person."""
    import core.db as _db_mod

    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"

        with patch.object(_db_mod, "DB_PATH",         db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            db.add_person("p1", "Alice")
            db.add_person("p2", "Bob")

            emb1 = random_embedding(seed=10)
            emb2 = random_embedding(seed=11)
            db.add_voice_embedding("p1", emb1)
            db.add_voice_embedding("p1", emb2)
            db.add_voice_embedding("p2", random_embedding(seed=20))

            profile = db.load_voice_profile_for("p1")
            assert profile is not None
            # Must be unit length
            import numpy as np
            assert abs(np.linalg.norm(profile) - 1.0) < 1e-5
            # Must not equal Bob's profile
            bob_profile = db.load_voice_profile_for("p2")
            assert not np.allclose(profile, bob_profile)
            db._conn.close()


def test_load_voice_profile_for_returns_none_when_no_data():
    """I2: load_voice_profile_for returns None for a person with no voice embeddings."""
    import core.db as _db_mod

    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"

        with patch.object(_db_mod, "DB_PATH",         db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            db.add_person("p1", "Alice")
            assert db.load_voice_profile_for("p1") is None
            assert db.load_voice_profile_for("nonexistent") is None
            db._conn.close()


# ── Stranger tests ─────────────────────────────────────────────────────────────

def test_add_stranger_creates_person_type_stranger():
    import core.db as _db_mod
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"
        with patch.object(_db_mod, "DB_PATH", db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            sid = db.add_stranger("Alice")
            assert sid.startswith("stranger_alice_")
            assert db.get_person_type(sid) == "stranger"
            db._conn.close()


def test_add_stranger_default_name():
    import core.db as _db_mod
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"
        with patch.object(_db_mod, "DB_PATH", db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            sid = db.add_stranger()
            assert sid.startswith("stranger_visitor_")
            assert db.get_person_type(sid) == "stranger"
            db._conn.close()


def test_get_person_type_known_person():
    import core.db as _db_mod
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"
        with patch.object(_db_mod, "DB_PATH", db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            db.add_person("p1", "Jagan")
            assert db.get_person_type("p1") == "known"
            db._conn.close()


def test_get_person_type_missing_returns_known():
    import core.db as _db_mod
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"
        with patch.object(_db_mod, "DB_PATH", db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            assert db.get_person_type("nonexistent_id") == "known"
            db._conn.close()


def test_get_stranger_visits_since():
    import core.db as _db_mod
    import time as _time
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"
        with patch.object(_db_mod, "DB_PATH", db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            before = _time.time()
            sid = db.add_stranger("Bob")
            db.update_last_seen(sid)  # stamp last_seen = now
            visits = db.get_stranger_visits_since(before)
            assert len(visits) == 1
            assert visits[0]["name"] == "Bob"
            assert visits[0]["id"] == sid
            db._conn.close()


def test_get_stranger_visits_since_excludes_old():
    import core.db as _db_mod
    import time as _time
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"
        with patch.object(_db_mod, "DB_PATH", db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            sid = db.add_stranger("Old visitor")
            db.update_last_seen(sid)
            future = _time.time() + 10
            visits = db.get_stranger_visits_since(future)
            assert visits == []
            db._conn.close()


def test_list_people_includes_person_type():
    import core.db as _db_mod
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"
        with patch.object(_db_mod, "DB_PATH", db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            db.add_person("p1", "Jagan")
            sid = db.add_stranger("Carol")
            people = {p["id"]: p for p in db.list_people()}
            assert people["p1"]["person_type"] == "known"
            assert people[sid]["person_type"] == "stranger"
            db._conn.close()


# ── WAL mode ──────────────────────────────────────────────────────────────────

def test_wal_mode_set_on_new_db():
    """M2: WAL journal mode must be set on every new FaceDB so the dashboard
    can read concurrently without locking the pipeline writer."""
    import core.db as _db_mod
    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"
        with patch.object(_db_mod, "DB_PATH", db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db   = _db_mod.FaceDB()
            mode = db._conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode == "wal", f"Expected WAL, got '{mode}'"
            db._conn.close()


# ── MAX_EMBEDDINGS cap ────────────────────────────────────────────────────────

def test_add_embedding_returns_false_at_cap():
    """M3: add_embedding() must return False once the gallery is full."""
    import core.db as _db_mod
    from core.config import MAX_EMBEDDINGS
    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"
        with patch.object(_db_mod, "DB_PATH", db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            db.add_person("p1", "Jagan")
            # Fill gallery to the cap using maximally diverse embeddings
            rng = np.random.default_rng(42)
            added = 0
            attempts = 0
            while added < MAX_EMBEDDINGS and attempts < MAX_EMBEDDINGS * 10:
                v = rng.random(512).astype(np.float32)
                v /= np.linalg.norm(v)
                if db.add_embedding("p1", v):
                    added += 1
                attempts += 1
            assert added == MAX_EMBEDDINGS, (
                f"Expected to fill gallery to {MAX_EMBEDDINGS}, only got {added}"
            )
            # One more must be rejected
            extra = rng.random(512).astype(np.float32)
            extra /= np.linalg.norm(extra)
            result = db.add_embedding("p1", extra)
            assert result is False, "add_embedding should return False when gallery is full"
            db._conn.close()


# ── system_identity table ─────────────────────────────────────────────────────

def test_system_identity_default_is_dog():
    """system_identity table must seed 'system_name' = 'Dog' at init."""
    import core.db as _db_mod
    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"
        with patch.object(_db_mod, "DB_PATH", db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db  = _db_mod.FaceDB()
            val = db.get_system_identity("system_name")
            assert val == "Dog"
            db._conn.close()


def test_system_identity_returns_none_for_unknown_key():
    import core.db as _db_mod
    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"
        with patch.object(_db_mod, "DB_PATH", db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            assert db.get_system_identity("nonexistent_key") is None
            db._conn.close()


def test_set_system_identity_upsert():
    """set_system_identity must insert on first call, update on second."""
    import core.db as _db_mod
    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"
        with patch.object(_db_mod, "DB_PATH", db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            db.set_system_identity("system_name", "Rex", set_by="jagan_abc", note="named in test")
            assert db.get_system_identity("system_name") == "Rex"
            # Update
            db.set_system_identity("system_name", "Max")
            assert db.get_system_identity("system_name") == "Max"
            # Only one row for this key
            count = db._conn.execute(
                "SELECT COUNT(*) FROM system_identity WHERE key = 'system_name'"
            ).fetchone()[0]
            assert count == 1
            db._conn.close()


def test_set_system_identity_new_key():
    import core.db as _db_mod
    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"
        with patch.object(_db_mod, "DB_PATH", db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            db.set_system_identity("owner_name", "Jagan")
            assert db.get_system_identity("owner_name") == "Jagan"
            db._conn.close()


# ── B1: add_person INSERT OR IGNORE ──────────────────────────────────────────

def test_add_person_ignore_preserves_existing_row():
    """B1: Re-calling add_person with an existing id must NOT reset enrolled_at,
    last_seen, or preferred_language."""
    import core.db as _db_mod

    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"

        with patch.object(_db_mod, "DB_PATH",         db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            db.add_person("p1", "Alice")

            # Manually set last_seen and preferred_language
            db._conn.execute(
                "UPDATE persons SET last_seen = 999.0, preferred_language = 'fr' WHERE id = 'p1'"
            )
            db._conn.commit()

            enrolled_before = db._conn.execute(
                "SELECT enrolled_at FROM persons WHERE id = 'p1'"
            ).fetchone()[0]

            # Re-call add_person with same id — should be a no-op
            db.add_person("p1", "Alice-renamed")

            row = db._conn.execute(
                "SELECT name, enrolled_at, last_seen, preferred_language FROM persons WHERE id = 'p1'"
            ).fetchone()
            assert row[0] == "Alice",   f"name changed to {row[0]!r}"
            assert row[1] == enrolled_before, "enrolled_at was reset"
            assert row[2] == 999.0,     f"last_seen was reset (got {row[2]})"
            assert row[3] == "fr",      f"preferred_language was reset (got {row[3]!r})"
            db._conn.close()


# ── B7: silent observation WHERE clause ───────────────────────────────────────

def test_update_silent_observation_matches_recent_row():
    """B7: A recent observation with high cosine sim must be updated, not re-inserted."""
    import core.db as _db_mod

    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"

        with patch.object(_db_mod, "DB_PATH",         db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            emb = random_embedding(seed=1)
            db.update_silent_observation(emb)
            # Call again with nearly identical embedding — should update, not insert
            db.update_silent_observation(emb * 0.9999)

            count = db._conn.execute("SELECT COUNT(*) FROM silent_observations").fetchone()[0]
            assert count == 1, f"Expected 1 row (update), got {count}"
            fc = db._conn.execute("SELECT frame_count FROM silent_observations").fetchone()[0]
            assert fc == 2, f"Expected frame_count=2, got {fc}"
            db._conn.close()


def test_update_silent_observation_skips_old_row():
    """B7: An observation older than SILENT_OBS_SCAN_DAYS must not be matched;
    a new row is inserted instead."""
    import core.db as _db_mod
    import time as _time

    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"

        with patch.object(_db_mod, "DB_PATH",         db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            emb = random_embedding(seed=2)

            # Insert an old observation directly (last_seen = 8 days ago)
            old_ts = _time.time() - 8 * 86400
            db._conn.execute(
                """INSERT INTO silent_observations
                   (id, first_seen, last_seen, duration_secs, frame_count,
                    embedding, photo_path, zone, created_at)
                   VALUES ('obs_old', ?, ?, 0, 1, ?, NULL, NULL, ?)""",
                (old_ts, old_ts, emb.tobytes(), old_ts),
            )
            db._conn.commit()

            # Same embedding — should NOT match the old row due to WHERE cutoff
            db.update_silent_observation(emb)

            count = db._conn.execute("SELECT COUNT(*) FROM silent_observations").fetchone()[0]
            assert count == 2, f"Expected 2 rows (old not matched), got {count}"
            old_fc = db._conn.execute(
                "SELECT frame_count FROM silent_observations WHERE id = 'obs_old'"
            ).fetchone()[0]
            assert old_fc == 1, f"Old row frame_count changed (got {old_fc})"
            db._conn.close()


# ── Wave 2 Item 12: vectorized silent-observation cosine ─────────────────────

def test_silent_observation_match_correctness_5_rows():
    """Item 12: among 5 inserted rows, the closest one must be returned."""
    import core.db as _db_mod
    import time as _time

    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"

        with patch.object(_db_mod, "DB_PATH",         db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()

            # Build 5 orthogonal-ish unit vectors.
            rng = np.random.default_rng(42)
            embs = []
            for _ in range(5):
                v = rng.standard_normal(512).astype(np.float32)
                v /= np.linalg.norm(v)
                embs.append(v)

            # Insert all 5 as silent observations with matched_person_id=NULL.
            now = _time.time()
            inserted_ids = []
            for i, v in enumerate(embs):
                oid = f"obs_test_{i}"
                db._conn.execute(
                    """INSERT INTO silent_observations
                       (id, first_seen, last_seen, duration_secs, frame_count,
                        embedding, photo_path, zone, created_at)
                       VALUES (?, ?, ?, 0, 1, ?, NULL, NULL, ?)""",
                    (oid, now, now, v.tobytes(), now),
                )
                inserted_ids.append(oid)
            db._conn.commit()

            # Query with a vector very close to embs[2].
            query = embs[2] * 0.9999 + rng.standard_normal(512).astype(np.float32) * 0.0001
            query /= np.linalg.norm(query)

            matched_id = db.update_silent_observation(query)

            assert matched_id == inserted_ids[2], (
                f"Expected '{inserted_ids[2]}' but got '{matched_id}'"
            )
            db._conn.close()


def test_silent_observation_match_returns_none_below_threshold():
    """Item 12: when best dot-product is below SILENT_OBS_SIMILARITY, return None."""
    import core.db as _db_mod
    from core.config import SILENT_OBS_SIMILARITY
    import time as _time

    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"

        with patch.object(_db_mod, "DB_PATH",         db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()

            # Insert a single row.
            now = _time.time()
            stored = np.zeros(512, dtype=np.float32)
            stored[0] = 1.0  # unit vector pointing along axis 0
            db._conn.execute(
                """INSERT INTO silent_observations
                   (id, first_seen, last_seen, duration_secs, frame_count,
                    embedding, photo_path, zone, created_at)
                   VALUES ('obs_low', ?, ?, 0, 1, ?, NULL, NULL, ?)""",
                (now, now, stored.tobytes(), now),
            )
            db._conn.commit()

            # Query with a vector orthogonal to stored → dot product ≈ 0.
            query = np.zeros(512, dtype=np.float32)
            query[1] = 1.0  # orthogonal axis

            result = db.update_silent_observation(query)

            # The stored dot product is 0.0 < SILENT_OBS_SIMILARITY → new row inserted → None.
            assert result is None, f"Expected None for low-similarity query, got {result!r}"
            # A new row should have been inserted.
            count = db._conn.execute("SELECT COUNT(*) FROM silent_observations").fetchone()[0]
            assert count == 2, f"Expected 2 rows (no match + new insert), got {count}"
            db._conn.close()


def test_silent_observation_match_handles_empty_window():
    """Item 12: when no rows exist in the recent window, return None without raising."""
    import core.db as _db_mod

    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"

        with patch.object(_db_mod, "DB_PATH",         db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()

            # Empty DB → no rows in window.
            query = np.zeros(512, dtype=np.float32)
            query[0] = 1.0

            result = db.update_silent_observation(query)

            assert result is None, f"Expected None on empty window, got {result!r}"
            # One new row should have been inserted.
            count = db._conn.execute("SELECT COUNT(*) FROM silent_observations").fetchone()[0]
            assert count == 1, f"Expected 1 inserted row, got {count}"
            db._conn.close()


# ── #3: Provenance schema migration ──────────────────────────────────────────

def test_add_embedding_stores_source_and_confidence():
    """#3: source and confidence_at_write must be stored in embeddings table."""
    import core.db as _db_mod

    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"

        with patch.object(_db_mod, "DB_PATH",         db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            db.add_person("p1", "Alice", None)
            emb = random_embedding(seed=10)

            db.add_embedding("p1", emb, source="enrollment", confidence=0.95)

            row = db._conn.execute(
                "SELECT source, confidence_at_write FROM embeddings WHERE person_id = 'p1'"
            ).fetchone()
            assert row is not None
            assert row[0] == "enrollment"
            assert abs(row[1] - 0.95) < 1e-5
            db._conn.close()


def test_add_embedding_default_source_is_legacy_unknown():
    """#3: Calling add_embedding() without source must default to 'legacy_unknown'."""
    import core.db as _db_mod

    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"

        with patch.object(_db_mod, "DB_PATH",         db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            db.add_person("p1", "Alice", None)
            db.add_embedding("p1", random_embedding(seed=11))

            row = db._conn.execute(
                "SELECT source FROM embeddings WHERE person_id = 'p1'"
            ).fetchone()
            assert row[0] == "legacy_unknown"
            db._conn.close()


def test_add_voice_embedding_stores_source_and_confidence():
    """#3: source and confidence_at_write must be stored in voice_embeddings table."""
    import core.db as _db_mod

    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"

        with patch.object(_db_mod, "DB_PATH",         db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            db.add_person("p1", "Alice", None)
            voice_emb = np.random.rand(192).astype(np.float32)
            voice_emb /= np.linalg.norm(voice_emb)

            db.add_voice_embedding("p1", voice_emb, source="voice_self_match", confidence=0.72)

            row = db._conn.execute(
                "SELECT source, confidence_at_write FROM voice_embeddings WHERE person_id = 'p1'"
            ).fetchone()
            assert row[0] == "voice_self_match"
            assert abs(row[1] - 0.72) < 1e-5
            db._conn.close()


def test_schema_migration_adds_columns_to_existing_db():
    """#3: Opening an old DB (without provenance columns) must add them automatically."""
    import core.db as _db_mod
    import sqlite3

    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"

        # Create a legacy DB without provenance columns
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE persons (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, enrolled_at REAL NOT NULL,
                photo_path TEXT, last_seen REAL, preferred_language TEXT NOT NULL DEFAULT 'en'
            );
            CREATE TABLE embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT, person_id TEXT NOT NULL,
                faiss_idx INTEGER NOT NULL, vector BLOB, captured_at REAL NOT NULL
            );
            CREATE TABLE voice_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT, person_id TEXT NOT NULL,
                vector BLOB NOT NULL, captured_at REAL NOT NULL
            );
        """)
        conn.commit()
        conn.close()

        # Opening via FaceDB must trigger migration
        with patch.object(_db_mod, "DB_PATH",         db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            db._conn.close()  # close before inspecting so file isn't locked

        # Verify columns now exist
        conn2 = sqlite3.connect(str(db_path))
        cols_emb   = {r[1] for r in conn2.execute("PRAGMA table_info(embeddings)").fetchall()}
        cols_voice = {r[1] for r in conn2.execute("PRAGMA table_info(voice_embeddings)").fetchall()}
        conn2.close()

        assert "source" in cols_emb
        assert "confidence_at_write" in cols_emb
        assert "source" in cols_voice
        assert "confidence_at_write" in cols_voice


# ── #7: Gallery audit / repair ────────────────────────────────────────────────

def test_gallery_audit_returns_source_counts():
    """#7: gallery_audit must report correct by_source breakdown."""
    import core.db as _db_mod

    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"

        with patch.object(_db_mod, "DB_PATH",         db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            db.add_person("p1", "Alice", None)
            db.add_embedding("p1", random_embedding(seed=1),  source="enrollment",        confidence=0.95)
            db.add_embedding("p1", random_embedding(seed=2),  source="enrollment",        confidence=0.93)
            db.add_embedding("p1", random_embedding(seed=3),  source="recognition_update", confidence=0.30)

            results = db.gallery_audit("p1")
            assert len(results) == 1
            r = results[0]
            assert r["total"] == 3
            assert r["by_source"]["enrollment"] == 2
            assert r["by_source"]["recognition_update"] == 1
            db._conn.close()


def test_gallery_audit_detects_outlier_embedding():
    """#7: An embedding that is very different from the cluster must appear in outlier_row_ids."""
    import core.db as _db_mod

    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"

        with patch.object(_db_mod, "DB_PATH",         db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            db.add_person("p1", "Alice", None)
            # 5 similar embeddings (same direction)
            base = random_embedding(seed=10)
            for i in range(5):
                db.add_embedding("p1", base + np.random.randn(512).astype(np.float32) * 0.01,
                                  source="enrollment", confidence=0.90)
            # 1 outlier embedding (completely different direction).
            # Use 'enrollment' source so the centroid-distance gate (which only
            # guards 'recognition_update' writes) doesn't reject it — the test's
            # intent is that audit detects bad rows regardless of how they got in.
            outlier = random_embedding(seed=99)
            db.add_embedding("p1", -outlier, source="enrollment", confidence=0.19)

            results = db.gallery_audit("p1", sigma=1.5)
            assert len(results) == 1
            assert len(results[0]["outlier_row_ids"]) >= 1
            db._conn.close()


def test_prune_outlier_embeddings_removes_rows_and_rebuilds():
    """#7: prune_outlier_embeddings must delete outlier rows and rebuild FAISS."""
    import core.db as _db_mod

    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"

        with patch.object(_db_mod, "DB_PATH",         db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            db.add_person("p1", "Alice", None)
            base = random_embedding(seed=10)
            for i in range(5):
                db.add_embedding("p1", base + np.random.randn(512).astype(np.float32) * 0.01,
                                  source="enrollment", confidence=0.90)
            # See test_gallery_audit_detects_outlier_embedding for why enrollment.
            db.add_embedding("p1", -random_embedding(seed=99),
                              source="enrollment", confidence=0.19)

            count_before = db._conn.execute(
                "SELECT COUNT(*) FROM embeddings WHERE person_id = 'p1'"
            ).fetchone()[0]
            removed = db.prune_outlier_embeddings("p1", sigma=1.5)
            count_after = db._conn.execute(
                "SELECT COUNT(*) FROM embeddings WHERE person_id = 'p1'"
            ).fetchone()[0]

            assert removed >= 1
            assert count_after == count_before - removed
            # FAISS index must still be in sync
            assert db.index.ntotal == count_after
            db._conn.close()


def test_gallery_audit_no_crash_with_few_embeddings():
    """#7: gallery_audit must not crash when a person has < 3 embeddings (skip outlier detection)."""
    import core.db as _db_mod

    with tempfile.TemporaryDirectory() as tmp:
        db_path    = Path(tmp) / "faces.db"
        index_path = Path(tmp) / "faces.index"

        with patch.object(_db_mod, "DB_PATH",         db_path), \
             patch.object(_db_mod, "FAISS_INDEX_PATH", index_path):
            db = _db_mod.FaceDB()
            db.add_person("p1", "Alice", None)
            db.add_embedding("p1", random_embedding(seed=1), source="enrollment", confidence=0.90)

            results = db.gallery_audit("p1")
            assert len(results) == 1
            assert results[0]["outlier_row_ids"] == []  # no stats possible with 1 embedding
            db._conn.close()


if __name__ == "__main__":
    test_delete_person1_keeps_person2()
    print()
    test_faiss_index_file_deleted_triggers_rebuild()
    print()
    test_empty_db_no_spurious_rebuild()
    print()
    test_vectors_stored_as_normalized_blobs()
    print()
    print("=" * 60)
    print("ALL TESTS PASSED OK")
    print("=" * 60)
