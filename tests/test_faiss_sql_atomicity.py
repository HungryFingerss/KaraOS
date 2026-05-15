"""
P0.5 — FAISS + faces.db cross-storage atomicity (slow tier).

Architecture: SQLite = durable source of truth. FAISS = rebuildable
materialized view. Boot reconciliation closes any divergence. If
reconciliation itself fails, system comes up degraded rather than crashing.

Tests 1-4 inject crashes at specific points in the paired-write path and
verify the post-crash state is recoverable. Tests 5-6 verify boot
reconciliation fires when needed. Test 7 verifies degraded-mode semantics.

All use FaceDB with tmp_path so no production files are touched.

Proxy pattern for monkeypatching:
  sqlite3.Connection is a C-extension type — monkeypatch.setattr on its
  methods fails at runtime. _ConnProxy wraps the real connection and
  intercepts only the targeted SQL. faiss.IndexFlatIP is similar;
  _IndexProxy wraps it and overrides specific methods.
"""
import numpy as np
import pytest
from pathlib import Path

from core.db import FaceDB


# ── helpers ───────────────────────────────────────────────────────────────────

def fake_embedding(dim: int = 512) -> np.ndarray:
    """L2-normalized random embedding for tests."""
    raw = np.random.randn(dim).astype(np.float32)
    return raw / np.linalg.norm(raw)


def _sentinel_path(faiss_path: Path) -> Path:
    """
    Sentinel path is faiss_path.name + ".dirty" (appended), NOT
    .with_suffix(".dirty") (which replaces .index → faiss.dirty).
    """
    return faiss_path.with_name(faiss_path.name + ".dirty")


class _ConnProxy:
    """Wraps sqlite3.Connection; crashes execute() for matching SQL."""
    def __init__(self, real, crash_pred):
        self._real = real
        self._crash_pred = crash_pred

    def execute(self, sql, *args, **kwargs):
        if isinstance(sql, str) and self._crash_pred(sql):
            raise RuntimeError("simulated SQL failure mid-INSERT")
        return self._real.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _IndexProxy:
    """Wraps faiss index; overrides add() or remove_ids() to raise."""
    def __init__(self, real, crash_on_add=False, crash_on_remove=False):
        self._real = real
        self._crash_on_add = crash_on_add
        self._crash_on_remove = crash_on_remove

    def add(self, *args, **kwargs):
        if self._crash_on_add:
            raise RuntimeError("simulated FAISS add failure")
        return self._real.add(*args, **kwargs)

    def remove_ids(self, *args, **kwargs):
        if self._crash_on_remove:
            raise RuntimeError("simulated FAISS remove_ids failure")
        return self._real.remove_ids(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.slow
def test_crash_mid_sql_commit_does_not_corrupt_faiss(tmp_path, monkeypatch):
    """SQL INSERT raises BEFORE FAISS update fires.

    Post-fix ordering: SQL transaction is first (durable), FAISS is second
    (derived). A crash in the SQL phase must leave both stores clean:
    SQLite rolls back atomically; FAISS is never touched; sentinel NOT written
    (no divergence to mark — both stores consistent at zero embeddings).

    Pre-fix fingerprint: FAISS update fires BEFORE SQL, so this test will
    fail with db.index.ntotal == 1 (orphan from the pre-SQL-crash FAISS
    update) when run against the unfixed FaceDB.add_embedding.
    """
    db = FaceDB(db_path=str(tmp_path / "faces.db"),
                faiss_path=tmp_path / "faiss.index")
    db.add_person("test_pid", "Test Person")

    pre_faiss_size = db.index.ntotal
    pre_sql_count = db._conn.execute(
        "SELECT COUNT(*) FROM embeddings"
    ).fetchone()[0]

    monkeypatch.setattr(
        db, "_conn",
        _ConnProxy(db._conn, lambda s: "INSERT INTO embeddings" in s)
    )

    with pytest.raises(RuntimeError, match="simulated SQL failure"):
        db.add_embedding(person_id="test_pid", embedding=fake_embedding())

    assert db.index.ntotal == pre_faiss_size, (
        f"BUG: FAISS has {db.index.ntotal} entries after SQL crash — "
        f"expected {pre_faiss_size}. FAISS-first ordering bug: FAISS was "
        f"updated before SQL committed, leaving an orphan entry."
    )
    # Use real conn to check SQL state
    real_conn = db._conn._real
    post_sql_count = real_conn.execute(
        "SELECT COUNT(*) FROM embeddings"
    ).fetchone()[0]
    assert post_sql_count == pre_sql_count
    assert not _sentinel_path(tmp_path / "faiss.index").exists()


@pytest.mark.slow
def test_crash_post_sql_commit_pre_faiss_update_recovers_on_boot(tmp_path, monkeypatch):
    """SQL commits, then FAISS index.add() raises.

    Post-fix: SQL is durable (row in embeddings table). FAISS update failed.
    Sentinel must be written. On next boot: rebuild fires, FAISS reconciles
    with SQL, sentinel cleared.
    """
    faces_path = tmp_path / "faces.db"
    faiss_path = tmp_path / "faiss.index"
    sentinel = _sentinel_path(faiss_path)

    db1 = FaceDB(db_path=str(faces_path), faiss_path=faiss_path)
    db1.add_person("test_pid", "Test Person")

    monkeypatch.setattr(
        db1, "index",
        _IndexProxy(db1.index, crash_on_add=True)
    )

    with pytest.raises(RuntimeError, match="simulated FAISS add failure"):
        db1.add_embedding(person_id="test_pid", embedding=fake_embedding())

    assert sentinel.exists(), "Sentinel not written after FAISS failure"
    db1.close()

    # Invocation counter: verify rebuild fired on next boot.
    rebuild_count = []
    original_rebuild = FaceDB._rebuild_faiss
    def tracking_rebuild(self, *args, **kwargs):
        rebuild_count.append(1)
        return original_rebuild(self, *args, **kwargs)
    monkeypatch.setattr(FaceDB, "_rebuild_faiss", tracking_rebuild)

    db2 = FaceDB(db_path=str(faces_path), faiss_path=faiss_path)

    assert len(rebuild_count) == 1, "Boot did not invoke _rebuild_faiss"
    assert not sentinel.exists(), "Sentinel not cleared after successful rebuild"
    sql_count = db2._conn.execute(
        "SELECT COUNT(*) FROM embeddings"
    ).fetchone()[0]
    assert sql_count == 1
    assert db2.index.ntotal == sql_count


@pytest.mark.slow
def test_crash_post_faiss_inmemory_pre_disk_save_recovers_on_boot(tmp_path, monkeypatch):
    """FAISS in-memory updated, then _save_faiss() raises.

    SQL committed; FAISS in-memory updated; disk-save failed.
    Sentinel written. Next boot reconciles from SQL.
    """
    faces_path = tmp_path / "faces.db"
    faiss_path = tmp_path / "faiss.index"
    sentinel = _sentinel_path(faiss_path)

    db1 = FaceDB(db_path=str(faces_path), faiss_path=faiss_path)
    db1.add_person("test_pid", "Test Person")

    def crashing_save_faiss():
        raise RuntimeError("simulated disk save failure")
    monkeypatch.setattr(db1, "_save_faiss", crashing_save_faiss)

    with pytest.raises(RuntimeError, match="simulated disk save failure"):
        db1.add_embedding(person_id="test_pid", embedding=fake_embedding())

    assert sentinel.exists(), "Sentinel not written after disk-save failure"
    db1.close()

    rebuild_count = []
    original_rebuild = FaceDB._rebuild_faiss
    def tracking_rebuild(self, *args, **kwargs):
        rebuild_count.append(1)
        return original_rebuild(self, *args, **kwargs)
    monkeypatch.setattr(FaceDB, "_rebuild_faiss", tracking_rebuild)

    db2 = FaceDB(db_path=str(faces_path), faiss_path=faiss_path)
    assert len(rebuild_count) == 1
    sql_count = db2._conn.execute(
        "SELECT COUNT(*) FROM embeddings"
    ).fetchone()[0]
    assert db2.index.ntotal == sql_count


@pytest.mark.slow
def test_delete_person_crash_post_sql_recovers_on_boot(tmp_path, monkeypatch):
    """delete_person: SQL deletes committed, FAISS _rebuild_faiss raises.

    IndexFlatIP has no selective remove_ids; delete_person uses _rebuild_faiss.
    Five persons added. delete_person("pid_2") fires SQL delete (commits),
    then _rebuild_faiss raises. Sentinel written. Next boot rebuilds;
    FAISS and SQL agree on 4 persons.
    """
    faces_path = tmp_path / "faces.db"
    faiss_path = tmp_path / "faiss.index"
    sentinel = _sentinel_path(faiss_path)

    db1 = FaceDB(db_path=str(faces_path), faiss_path=faiss_path)
    for i in range(5):
        db1.add_person(f"pid_{i}", f"Person {i}")
        db1.add_embedding(person_id=f"pid_{i}", embedding=fake_embedding())
    assert db1.index.ntotal == 5

    original_rebuild = db1._rebuild_faiss
    call_count = []
    def crashing_rebuild():
        call_count.append(1)
        if len(call_count) == 1:
            raise RuntimeError("simulated FAISS rebuild failure post-SQL-commit")
        return original_rebuild()
    monkeypatch.setattr(db1, "_rebuild_faiss", crashing_rebuild)

    with pytest.raises(RuntimeError, match="simulated FAISS rebuild failure"):
        db1.delete_person(person_id="pid_2")

    assert sentinel.exists(), "Sentinel not written after FAISS rebuild failure"
    db1.close()

    rebuild_count = []
    original_rebuild = FaceDB._rebuild_faiss
    def tracking_rebuild(self, *args, **kwargs):
        rebuild_count.append(1)
        return original_rebuild(self, *args, **kwargs)
    monkeypatch.setattr(FaceDB, "_rebuild_faiss", tracking_rebuild)

    db2 = FaceDB(db_path=str(faces_path), faiss_path=faiss_path)
    assert len(rebuild_count) == 1
    sql_count = db2._conn.execute(
        "SELECT COUNT(*) FROM embeddings"
    ).fetchone()[0]
    assert sql_count == 4
    assert db2.index.ntotal == sql_count


@pytest.mark.slow
def test_artificial_divergence_reconciles_on_boot(tmp_path, monkeypatch):
    """Architectural-anchor: delete FAISS file, boot rebuilds from SQL.

    Five persons enrolled, FAISS file deleted manually. Boot must detect
    mismatch (index.ntotal=0 vs sql_count=5), invoke _rebuild_faiss, and
    restore recognition ability.
    """
    faces_path = tmp_path / "faces.db"
    faiss_path = tmp_path / "faiss.index"

    db1 = FaceDB(db_path=str(faces_path), faiss_path=faiss_path)
    embeddings_by_pid = {}
    for i in range(5):
        emb = fake_embedding()
        embeddings_by_pid[f"pid_{i}"] = emb
        db1.add_person(f"pid_{i}", f"Person {i}")
        db1.add_embedding(person_id=f"pid_{i}", embedding=emb)
    assert db1.index.ntotal == 5
    db1.close()

    faiss_path.unlink()

    rebuild_count = []
    original_rebuild = FaceDB._rebuild_faiss
    def tracking_rebuild(self, *args, **kwargs):
        rebuild_count.append(1)
        return original_rebuild(self, *args, **kwargs)
    monkeypatch.setattr(FaceDB, "_rebuild_faiss", tracking_rebuild)

    db2 = FaceDB(db_path=str(faces_path), faiss_path=faiss_path)

    assert len(rebuild_count) == 1, (
        f"Boot did not invoke _rebuild_faiss — expected 1, got {len(rebuild_count)}"
    )
    assert db2.index.ntotal == 5

    target = embeddings_by_pid["pid_2"]
    pid, name, score = db2.recognize(target, threshold=0.5)
    assert pid == "pid_2"


@pytest.mark.slow
def test_sentinel_file_triggers_reconciliation_when_counts_match(tmp_path, monkeypatch):
    """Belt-and-suspenders: row counts coincidentally match, but sentinel exists.

    Boot reconciliation must invoke _rebuild_faiss even when counts match —
    content may be diverged (wrong vectors in index despite same count).
    """
    faces_path = tmp_path / "faces.db"
    faiss_path = tmp_path / "faiss.index"
    sentinel = _sentinel_path(faiss_path)

    db1 = FaceDB(db_path=str(faces_path), faiss_path=faiss_path)
    for i in range(3):
        db1.add_person(f"pid_{i}", f"Person {i}")
        db1.add_embedding(person_id=f"pid_{i}", embedding=fake_embedding())
    db1.close()

    sentinel.touch()

    rebuild_count = []
    original_rebuild = FaceDB._rebuild_faiss
    def tracking_rebuild(self, *args, **kwargs):
        rebuild_count.append(1)
        return original_rebuild(self, *args, **kwargs)
    monkeypatch.setattr(FaceDB, "_rebuild_faiss", tracking_rebuild)

    db2 = FaceDB(db_path=str(faces_path), faiss_path=faiss_path)

    assert len(rebuild_count) == 1, (
        f"Sentinel did not trigger rebuild — expected 1, got {len(rebuild_count)}"
    )
    assert not sentinel.exists(), "Sentinel not cleared after successful rebuild"
    sql_count = db2._conn.execute(
        "SELECT COUNT(*) FROM embeddings"
    ).fetchone()[0]
    assert db2.index.ntotal == sql_count


@pytest.mark.slow
def test_rebuild_failure_at_boot_comes_up_degraded(tmp_path, monkeypatch):
    """If _rebuild_faiss raises at boot, FaceDB must NOT raise.

    Sentinel preserved for next-boot retry. _faiss_degraded flag set True.
    Recognition returns (None, None, <score>) — the documented no-match shape.
    """
    faces_path = tmp_path / "faces.db"
    faiss_path = tmp_path / "faiss.index"
    sentinel = _sentinel_path(faiss_path)

    db1 = FaceDB(db_path=str(faces_path), faiss_path=faiss_path)
    for i in range(3):
        db1.add_person(f"pid_{i}", f"Person {i}")
        db1.add_embedding(person_id=f"pid_{i}", embedding=fake_embedding())
    db1.close()
    sentinel.touch()
    faiss_path.unlink()

    def crashing_rebuild(self, *args, **kwargs):
        raise RuntimeError("simulated rebuild failure at boot")
    monkeypatch.setattr(FaceDB, "_rebuild_faiss", crashing_rebuild)

    # MUST NOT raise:
    db2 = FaceDB(db_path=str(faces_path), faiss_path=faiss_path)

    assert db2._faiss_degraded is True, "_faiss_degraded flag not set after rebuild failure"
    assert sentinel.exists(), "Sentinel cleared despite rebuild failure — must be preserved for retry"

    # Recognition runs and returns no-match (pid is None).
    target = fake_embedding()
    pid, name, score = db2.recognize(target, threshold=0.5)
    assert pid is None, f"Expected no match in degraded mode, got pid={pid!r}"
