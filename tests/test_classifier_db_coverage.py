"""100% line+branch coverage for core.classifier_db — part of the
coverage-to-100 campaign. Complements tests/test_classifier_db.py by
exercising the remaining defensive / edge / branch lines: the 2-D embedding
guard, the audit-JSONL write-failure fallback, empty-query early return, the
empty abstract_text / intent_label validators, increment_outcome bad-kind +
missing-row, quarantine/activate missing-row, the full activate() path, the
seed-file-missing + blank-line + invalid-JSON + all-embedding-shape seed
branches, snapshot() (default + custom dir), _prune_snapshots (old-file prune
+ unlink-OSError swallow), and the WAL-checkpoint / close() error swallows.
All tests run headless — real temp SQLite files, no GPU / camera / network."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import base64
import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import pytest

# core.classifier_db hard-imports numpy at module scope; skip gracefully (rather
# than error at collection) if a minimal env is missing it.
pytest.importorskip("numpy")
import numpy as np  # noqa: E402

from core import classifier_db as cdb_mod  # noqa: E402
from core.classifier_db import (  # noqa: E402
    ClassifierDB,
    EVENT_ACTIVATED,
    EVENT_CREATED,
    EVENT_QUARANTINED,
    VALID_OUTCOME_KINDS,
    _blob_to_embedding,
    _embedding_to_blob,
    _now_iso,
)


# ── Helpers / fixtures ─────────────────────────────────────────────────────

def _vec(*vals: float) -> np.ndarray:
    """Small deterministic float32 embedding (dim configurable by arg count)."""
    return np.asarray(vals, dtype=np.float32)


@pytest.fixture
def db(tmp_path: Path):
    """A fresh ClassifierDB backed by real temp files; closed on teardown."""
    inst = ClassifierDB(
        db_path=tmp_path / "classifier.db",
        audit_log_path=tmp_path / "audit.jsonl",
    )
    yield inst
    inst.close()


def _insert(db: ClassifierDB, text: str, label: str = "casual_conversation",
            embedding: "np.ndarray | None" = None, **kw) -> int:
    return db.insert_scenario(
        abstract_text=text,
        intent_label=label,
        embedding=embedding if embedding is not None else _vec(1.0, 0.0, 0.0, 0.0),
        source_tag="test",
        source_version="v1",
        **kw,
    )


# ── Module-level helpers (50-51, 54-58, 61-62) ─────────────────────────────

def test_now_iso_returns_parseable_utc():
    s = _now_iso()
    dt = datetime.fromisoformat(s)
    assert dt.tzinfo is not None            # UTC-aware
    assert "+00:00" in s


def test_embedding_to_blob_roundtrip():
    vec = _vec(0.5, -0.25, 1.0, 0.0)
    blob = _embedding_to_blob(vec)          # 54-56, 58
    assert isinstance(blob, bytes)
    back = _blob_to_embedding(blob)         # 61-62
    assert np.allclose(back, vec)


def test_embedding_to_blob_rejects_2d():
    # Line 57: ndim != 1 -> ValueError
    with pytest.raises(ValueError, match="embedding must be 1-D"):
        _embedding_to_blob(np.zeros((2, 3), dtype=np.float32))


# ── migration idempotency: reopen skips applied versions (216-217) ─────────

def test_reopen_skips_already_applied_migrations(tmp_path):
    # First open runs migrations v1 + v2 (216 False -> 218 fn). Reopening the
    # same DB finds both versions already in `applied` -> `continue` at 217.
    db_path = tmp_path / "reopen.db"
    audit_path = tmp_path / "reopen.jsonl"
    first = ClassifierDB(db_path=db_path, audit_log_path=audit_path)
    created_at = first.get_metadata("created_at")
    first.close()

    second = ClassifierDB(db_path=db_path, audit_log_path=audit_path)
    try:
        # Each version applied exactly once (no re-run) — proves the continue.
        for v in (1, 2):
            n = second._conn.execute(
                "SELECT COUNT(*) FROM schema_migrations WHERE version = ?", (v,)
            ).fetchone()[0]
            assert n == 1
        # created_at preserved (INSERT OR IGNORE metadata re-seed is a no-op).
        assert second.get_metadata("created_at") == created_at
    finally:
        second.close()


# ── query_nearest: empty DB early return (300-304) ─────────────────────────

def test_query_nearest_empty_db_active_only(db):
    # active_only=True (default) branch, no rows -> line 304 `return []`
    assert db.query_nearest(_vec(1.0, 0.0, 0.0, 0.0)) == []


def test_query_nearest_empty_db_active_false(db):
    # active_only=False branch (line 300 False) + empty -> line 304
    assert db.query_nearest(_vec(1.0, 0.0, 0.0, 0.0), active_only=False) == []


def test_query_nearest_populated_sorted_desc(db):
    exact = _vec(1.0, 0.0, 0.0, 0.0)
    top = _insert(db, "closest", embedding=exact)
    _insert(db, "orthogonal", embedding=_vec(0.0, 1.0, 0.0, 0.0))
    _insert(db, "opposite", embedding=_vec(-1.0, 0.0, 0.0, 0.0))

    # k larger than row count exercises top_k = min(k, len(rows))
    results = db.query_nearest(exact, k=50)
    assert len(results) == 3
    assert results[0]["scenario_id"] == top
    assert results[0]["similarity"] > 0.99
    sims = [r["similarity"] for r in results]
    assert sims == sorted(sims, reverse=True)
    # _row_to_dict similarity branch (361 True) + embedding decoded back
    assert isinstance(results[0]["embedding"], np.ndarray)


def test_query_nearest_tolerates_zero_vector_row(db):
    # A zero embedding makes denom == 0 -> the safe/where zero-division guards
    # (313-315) resolve to similarity 0.0 without raising.
    _insert(db, "zerovec", embedding=_vec(0.0, 0.0, 0.0, 0.0))
    _insert(db, "real", embedding=_vec(1.0, 0.0, 0.0, 0.0))
    results = db.query_nearest(_vec(1.0, 0.0, 0.0, 0.0), k=5)
    assert len(results) == 2
    sim_by_text = {r["abstract_text"]: r["similarity"] for r in results}
    assert sim_by_text["zerovec"] == 0.0


# ── get_scenario / get_metadata / count_scenarios / resolve_label ──────────

def test_get_scenario_found_and_missing(db):
    sid = _insert(db, "findme")
    got = db.get_scenario(sid)                     # 333 True branch
    assert got is not None and got["abstract_text"] == "findme"
    # _row_to_dict similarity=None branch (361 False) => no 'similarity' key
    assert "similarity" not in got
    assert db.get_scenario(999_999) is None        # 333 False branch


def test_get_metadata_found_and_missing(db):
    assert db.get_metadata("schema_version") == "2"    # 339 found
    assert db.get_metadata("no_such_key") is None      # 339 missing


def test_count_scenarios_active_and_all(db):
    a = _insert(db, "active-one")
    b = _insert(db, "to-quarantine")
    db.quarantine(b, reason="x")
    assert db.count_scenarios() == 1                # active_only True (343 True)
    assert db.count_scenarios(active_only=False) == 2  # 343 False branch
    assert db.get_scenario(a)["active"] == 1


def test_resolve_label_mapped_and_unmapped(db):
    # Unmapped: resolve_label returns as-is (355 else)
    assert db.resolve_label("casual_conversation") == "casual_conversation"
    # Mapped chain: latest effective_version wins (350-355 + ORDER BY DESC)
    db.add_label_evolution("legacy_a", "mid_b", effective_version=1)
    db.add_label_evolution("legacy_a", "final_c", effective_version=3, reason="merge")
    assert db.resolve_label("legacy_a") == "final_c"
    # And it flows through _row_to_dict on read
    sid = _insert(db, "under old label", label="legacy_a")
    assert db.get_scenario(sid)["intent_label"] == "final_c"


# ── insert_scenario validators + verb/rowcount branches ────────────────────

def test_insert_rejects_empty_abstract_text(db):
    # Line 390-391: falsy string (short-circuit on `not abstract_text`)
    with pytest.raises(ValueError, match="abstract_text must be non-empty"):
        _insert(db, "")
    # ...and whitespace-only exercises `not abstract_text.strip()`
    with pytest.raises(ValueError, match="abstract_text must be non-empty"):
        _insert(db, "   ")


def test_insert_rejects_empty_intent_label(db):
    # Line 392-393: empty + whitespace-only intent_label
    with pytest.raises(ValueError, match="intent_label must be non-empty"):
        _insert(db, "valid text", label="")
    with pytest.raises(ValueError, match="intent_label must be non-empty"):
        _insert(db, "valid text 2", label="  ")


def test_insert_skip_if_duplicate_false_then_dup_returns_none(db):
    # skip_if_duplicate=False -> plain INSERT verb (400 else) + rowcount>0 (423 False)
    sid = _insert(db, "dupkey", skip_if_duplicate=False)
    assert isinstance(sid, int)
    # Same (abstract_text, intent_label) with INSERT OR IGNORE -> rowcount 0 (423 True)
    dup = _insert(db, "dupkey", skip_if_duplicate=True)
    assert dup is None
    assert db.count_scenarios() == 1


def test_insert_with_explicit_model_and_rule_version(db):
    # Exercises the truthy side of `embedding_model_id or ...` (397) and
    # `abstract_rule_version or ...` (398).
    sid = _insert(
        db, "explicit-meta",
        embedding_model_id="custom-model-x",
        abstract_rule_version=7,
        extracted_value="{P1}",
        intent_label_version=4,
        initial_confidence=0.9,
        outcome_confirmed=2,
        outcome_reverted=1,
        active=False,
        source_ref="ref-42",
    )
    row = db.get_scenario(sid)
    assert row["embedding_model_id"] == "custom-model-x"
    assert row["abstract_rule_version"] == 7
    assert row["extracted_value"] == "{P1}"
    assert row["active"] == 0
    assert row["outcome_confirmed"] == 2 and row["outcome_reverted"] == 1


# ── increment_outcome (439-453) ────────────────────────────────────────────

def test_increment_outcome_confirmed_and_reverted(db):
    sid = _insert(db, "outcome")
    db.increment_outcome(sid, kind="confirmed", decision_id="d1", reason="ok")
    db.increment_outcome(sid, kind="reverted", decision_id="d2", reason="bad")
    row = db.get_scenario(sid)
    assert row["outcome_confirmed"] == 1     # col branch "confirmed" (443)
    assert row["outcome_reverted"] == 1      # col branch "reverted" (443 else)
    events = [r[0] for r in db._conn.execute(
        "SELECT event_type FROM audit_log WHERE scenario_id = ?", (sid,)
    )]
    assert "outcome_confirmed" in events and "outcome_reverted" in events


def test_increment_outcome_bad_kind_raises(db):
    sid = _insert(db, "badkind")
    # Line 439-440: kind not in VALID_OUTCOME_KINDS
    with pytest.raises(ValueError, match="increment_outcome kind must be one of"):
        db.increment_outcome(sid, kind="bogus")
    assert "bogus" not in VALID_OUTCOME_KINDS


def test_increment_outcome_missing_scenario_raises(db):
    # Line 449-450: rowcount 0 -> KeyError
    with pytest.raises(KeyError, match="scenario_id 424242 not found"):
        db.increment_outcome(424242, kind="confirmed")


# ── quarantine / activate ──────────────────────────────────────────────────

def test_quarantine_missing_scenario_raises(db):
    # Line 461-462: rowcount 0 -> KeyError
    with pytest.raises(KeyError, match="scenario_id 555 not found"):
        db.quarantine(555, reason="nope")


def test_activate_restores_quarantined(db):
    # Full activate() body (466-476), inverse of quarantine.
    sid = _insert(db, "toggle")
    db.quarantine(sid, reason="temp")
    assert db.get_scenario(sid)["active"] == 0
    db.activate(sid, reason="restored")
    row = db.get_scenario(sid)
    assert row["active"] == 1
    events = [r[0] for r in db._conn.execute(
        "SELECT event_type FROM audit_log WHERE scenario_id = ?", (sid,)
    )]
    assert EVENT_QUARANTINED in events
    assert EVENT_ACTIVATED in events


def test_activate_missing_scenario_raises(db):
    # Line 473: rowcount 0 -> KeyError
    with pytest.raises(KeyError, match="scenario_id 777 not found"):
        db.activate(777, reason="nope")


# ── audit JSONL write failure fallback (279-282) ───────────────────────────

def test_audit_jsonl_write_failure_falls_back_to_sql(tmp_path, capsys):
    # Point audit_log_path at an EXISTING DIRECTORY so `.open("a")` raises
    # OSError (IsADirectoryError on POSIX / PermissionError on Windows — both
    # subclasses of OSError). __init__ only mkdir's the parent, so it succeeds;
    # the failure surfaces on the first _audit() call from insert_scenario.
    audit_dir = tmp_path / "auditdir"
    audit_dir.mkdir()
    inst = ClassifierDB(db_path=tmp_path / "c.db", audit_log_path=audit_dir)
    try:
        sid = _insert(inst, "audit-fallback")   # triggers EVENT_CREATED audit
        assert isinstance(sid, int)             # no exception propagated
        out = capsys.readouterr().out
        assert "audit log write failed" in out
        # SQL row is the source of truth — it must still exist despite JSONL fail
        rows = list(inst._conn.execute(
            "SELECT event_type FROM audit_log WHERE scenario_id = ?", (sid,)
        ))
        assert [r[0] for r in rows] == [EVENT_CREATED]
    finally:
        inst.close()


# ── seed_from_jsonl ────────────────────────────────────────────────────────

def test_seed_missing_file_raises(db, tmp_path):
    # Line 515-516
    with pytest.raises(FileNotFoundError, match="seed file not found"):
        db.seed_from_jsonl(tmp_path / "does_not_exist.jsonl")


def test_seed_all_embedding_shapes_and_skips(db, tmp_path, capsys):
    """Single seed file exercising every seed branch:
    str-embedding (532), list-embedding (534), embedding_b64 key (536),
    missing-embedding else (538-540), invalid-JSON (526-528), blank line
    (522-523), duplicate skip (556 False), and normal insert (556 True)."""
    b64_a = base64.b64encode(_vec(0.1, 0.2, 0.3, 0.4).tobytes()).decode("ascii")
    b64_c = base64.b64encode(_vec(0.4, 0.3, 0.2, 0.1).tobytes()).decode("ascii")

    r_str = {"abstract_text": "seed a", "intent_label": "casual",
             "embedding": b64_a, "source_tag": "s", "source_version": "v"}
    r_list = {"abstract_text": "seed b", "intent_label": "casual",
              "embedding": [1.0, 0.0, 0.0, 0.0],
              "source_tag": "s", "source_version": "v",
              "extracted_value": "{P1}", "abstract_rule_version": 2,
              "intent_label_version": 3, "initial_confidence": 0.8}
    r_b64key = {"abstract_text": "seed c", "intent_label": "casual",
                "embedding_b64": b64_c, "source_tag": "s", "source_version": "v"}
    r_missing = {"abstract_text": "seed d", "intent_label": "casual",
                 "source_tag": "s", "source_version": "v"}
    r_dup = {"abstract_text": "seed a", "intent_label": "casual",
             "embedding": [9.0, 9.0, 9.0, 9.0],
             "source_tag": "s", "source_version": "v"}

    lines = [
        json.dumps(r_str),      # str emb -> insert
        "",                     # blank -> continue (522-523)
        json.dumps(r_list),     # list emb -> insert
        "garbage { not json",   # invalid JSON -> except (526-528) + continue
        json.dumps(r_b64key),   # embedding_b64 -> insert
        json.dumps(r_missing),  # no embedding -> else (538-540) + continue
        json.dumps(r_dup),      # dup of "seed a" -> sid None (556 False)
    ]
    seed = tmp_path / "seed.jsonl"
    seed.write_text("\n".join(lines) + "\n", encoding="utf-8")

    inserted = db.seed_from_jsonl(seed)
    assert inserted == 3                 # a, b, c
    assert db.count_scenarios() == 3

    out = capsys.readouterr().out
    assert "invalid JSON" in out
    assert "missing embedding" in out


# ── snapshot / _prune_snapshots ────────────────────────────────────────────

def test_snapshot_custom_dir_creates_file_and_prunes_old(db, tmp_path):
    snap_dir = tmp_path / "snaps_custom"
    snap_dir.mkdir()
    # Pre-existing OLD snapshot (matches glob, mtime 40 days ago) -> gets pruned
    # (inner-if True at 588-590). The fresh snapshot's mtime (~now) is > cutoff
    # -> kept (inner-if False).
    old = snap_dir / "classifier_scenarios_20200101_000000.db"
    old.write_bytes(b"stale")
    past = time.time() - 40 * 86400
    os.utime(old, (past, past))

    result = db.snapshot(snapshot_dir=snap_dir, retain_days=30)

    assert result.endswith(".db")
    assert Path(result).exists()               # fresh snapshot created
    assert not old.exists()                     # old snapshot pruned
    # The fresh one survived pruning
    survivors = list(snap_dir.glob("classifier_scenarios_*.db"))
    assert Path(result) in survivors


def test_snapshot_default_dir_uses_config(db, tmp_path, monkeypatch):
    # snapshot_dir=None -> Path(CLASSIFIER_SNAPSHOT_DIR) (570 else). Redirect the
    # module-level constant to tmp_path so no real production dir is touched.
    default_dir = tmp_path / "cfg_default_snaps"
    monkeypatch.setattr(cdb_mod, "CLASSIFIER_SNAPSHOT_DIR", str(default_dir))
    result = db.snapshot()                      # snapshot_dir omitted
    assert Path(result).exists()
    assert Path(result).parent == default_dir


def test_snapshot_wal_checkpoint_error_swallowed(tmp_path):
    # Closing the connection makes the PRAGMA wal_checkpoint raise
    # sqlite3.ProgrammingError (a sqlite3.Error) -> except at 575-576 swallows;
    # the file copy still proceeds and a path is returned.
    inst = ClassifierDB(db_path=tmp_path / "c.db", audit_log_path=tmp_path / "a.jsonl")
    _insert(inst, "before-close")
    snap_dir = tmp_path / "snaps_err"
    inst._conn.close()                          # subsequent PRAGMA will raise
    result = inst.snapshot(snapshot_dir=snap_dir, retain_days=30)
    assert Path(result).exists()
    # conn already closed; no further teardown needed.


def test_prune_snapshots_swallows_unlink_oserror(db, tmp_path, monkeypatch):
    # Line 591-592: p.unlink() raising OSError is caught, loop continues,
    # returns removed count (0). Patch Path.unlink to always raise.
    snap_dir = tmp_path / "snaps_unlinkfail"
    snap_dir.mkdir()
    stale = snap_dir / "classifier_scenarios_20200101_000000.db"
    stale.write_bytes(b"x")
    past = time.time() - 40 * 86400
    os.utime(stale, (past, past))

    def _raise_unlink(self, *a, **k):
        raise OSError("cannot unlink (simulated)")

    monkeypatch.setattr(Path, "unlink", _raise_unlink)
    removed = db._prune_snapshots(snap_dir, retain_days=30)
    assert removed == 0
    assert stale.exists()                       # unlink failed -> still present


# ── checkpoint_wal / close / context manager ───────────────────────────────

def test_checkpoint_wal_happy_path(db):
    # try succeeds (602-603) — no exception, no output.
    db.checkpoint_wal()
    assert db.count_scenarios() == 0


def test_checkpoint_wal_error_swallowed(tmp_path, capsys):
    # Line 604-605: closed conn -> PRAGMA raises -> broad except -> print.
    inst = ClassifierDB(db_path=tmp_path / "c.db", audit_log_path=tmp_path / "a.jsonl")
    inst._conn.close()
    inst.checkpoint_wal()                        # must not raise
    assert "WAL checkpoint failed" in capsys.readouterr().out


def test_close_swallows_sqlite_error(tmp_path):
    # Line 609-611: self._conn.close() raising sqlite3.Error is swallowed.
    inst = ClassifierDB(db_path=tmp_path / "c.db", audit_log_path=tmp_path / "a.jsonl")
    real_conn = inst._conn

    class _BadConn:
        def close(self_inner):
            raise sqlite3.ProgrammingError("close boom")

    inst._conn = _BadConn()
    inst.close()                                 # swallowed, no raise
    real_conn.close()                            # clean up the real connection


def test_context_manager_enters_and_closes(tmp_path):
    # __enter__ returns self (613-614); __exit__ calls close() (616-617).
    with ClassifierDB(db_path=tmp_path / "cm.db", audit_log_path=tmp_path / "cm.jsonl") as cm:
        assert isinstance(cm, ClassifierDB)
        sid = _insert(cm, "in-context")
        assert cm.get_scenario(sid) is not None
    # After the block the connection is closed -> operations raise.
    with pytest.raises(sqlite3.ProgrammingError):
        cm._conn.execute("SELECT 1")
