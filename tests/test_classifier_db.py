"""tests/test_classifier_db.py — Classifier scenarios DB (Spec 1).

Covers the 12 acceptance tests from CLASSIFIER_GRAPH_SPEC_1.md:
schema, migration idempotency, seed import, dedup, k-NN query,
quarantine exclusion, audit log, label evolution, factory-reset survival,
and abstraction PERSON/LOC/time-preserving rules.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from core import classifier_db as cdb_mod
from core.classifier_db import ClassifierDB


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def db_paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "classifier.db", tmp_path / "audit.jsonl"


@pytest.fixture
def db(db_paths) -> ClassifierDB:
    db_path, audit_path = db_paths
    inst = ClassifierDB(db_path=db_path, audit_log_path=audit_path)
    yield inst
    inst.close()


def _vec(seed: int = 0, dim: int = 1024) -> np.ndarray:
    """Deterministic test embedding (L2-normalized)."""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim).astype(np.float32)
    return v / float(np.linalg.norm(v) + 1e-9)


# ── 1. Schema creation ────────────────────────────────────────────────────

def test_classifier_db_creates_schema_on_first_open(db_paths):
    db_path, audit_path = db_paths
    assert not db_path.exists()
    db = ClassifierDB(db_path=db_path, audit_log_path=audit_path)
    try:
        # All four tables exist
        tables = {row[0] for row in db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        assert "scenarios" in tables
        assert "schema_migrations" in tables
        assert "label_evolution" in tables
        assert "audit_log" in tables
        assert "db_metadata" in tables

        # db_metadata seeded — schema_version tracks the latest applied
        # migration version (currently 2 after Spec 2's extracted_value column).
        assert db.get_metadata("schema_version") == "2"
        assert db.get_metadata("seed_version") == "1"
        assert db.get_metadata("embedding_model") == cdb_mod.CLASSIFIER_EMBEDDING_MODEL_ID
        assert db.get_metadata("created_at") is not None

        # schema_migrations row inserted
        rows = list(db._conn.execute("SELECT version FROM schema_migrations"))
        assert (1,) in [(r[0],) for r in rows]
    finally:
        db.close()


# ── 2. Migration idempotency ──────────────────────────────────────────────

def test_classifier_db_idempotent_on_reopen(db_paths):
    db_path, audit_path = db_paths
    # First open
    first = ClassifierDB(db_path=db_path, audit_log_path=audit_path)
    created_at_first = first.get_metadata("created_at")
    first.close()

    # Second open — must NOT re-run migrations or re-seed metadata
    second = ClassifierDB(db_path=db_path, audit_log_path=audit_path)
    try:
        # schema_migrations table has exactly one row per applied version
        n_v1 = second._conn.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version=1"
        ).fetchone()[0]
        assert n_v1 == 1, f"migration v1 was applied {n_v1} times — should be 1"
        n_v2 = second._conn.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version=2"
        ).fetchone()[0]
        assert n_v2 == 1, f"migration v2 was applied {n_v2} times — should be 1"

        # db_metadata.created_at preserved (INSERT OR IGNORE)
        assert second.get_metadata("created_at") == created_at_first

        # Single metadata row per key (no duplicates)
        n_keys = second._conn.execute(
            "SELECT COUNT(*) FROM db_metadata WHERE key='schema_version'"
        ).fetchone()[0]
        assert n_keys == 1
    finally:
        second.close()


# ── 3. Seed import ────────────────────────────────────────────────────────

def test_seed_from_jsonl_inserts_all_rows(db: ClassifierDB, tmp_path: Path):
    seed = tmp_path / "seed.jsonl"
    rows = []
    for i in range(5):
        vec = _vec(seed=i)
        rows.append({
            "abstract_text":      f"test scenario {i}",
            "intent_label":       "casual_conversation",
            "embedding_b64":      base64.b64encode(vec.tobytes()).decode("ascii"),
            "source_tag":         "test",
            "source_version":     "test-v1",
            "initial_confidence": 0.7,
        })
    with seed.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")

    inserted = db.seed_from_jsonl(seed)
    assert inserted == 5
    assert db.count_scenarios() == 5

    # Field round-trip check on one row
    s = db._conn.execute(
        "SELECT abstract_text, intent_label, source_tag, source_version, initial_confidence "
        "FROM scenarios WHERE abstract_text = 'test scenario 0'"
    ).fetchone()
    assert s["abstract_text"] == "test scenario 0"
    assert s["intent_label"] == "casual_conversation"
    assert s["source_tag"] == "test"
    assert s["source_version"] == "test-v1"
    assert abs(s["initial_confidence"] - 0.7) < 1e-6


# ── 4. Seed dedup ─────────────────────────────────────────────────────────

def test_seed_skips_duplicates(db: ClassifierDB, tmp_path: Path):
    seed = tmp_path / "seed.jsonl"
    vec = _vec(seed=42)
    row = {
        "abstract_text":   "duplicate scenario",
        "intent_label":    "casual_conversation",
        "embedding_b64":   base64.b64encode(vec.tobytes()).decode("ascii"),
        "source_tag":      "test",
        "source_version":  "test-v1",
    }
    # Same row twice in the file
    with seed.open("w", encoding="utf-8") as fh:
        for _ in range(3):
            fh.write(json.dumps(row) + "\n")

    inserted_first = db.seed_from_jsonl(seed)
    assert inserted_first == 1
    assert db.count_scenarios() == 1

    # Re-running the seed import is also a no-op
    inserted_second = db.seed_from_jsonl(seed)
    assert inserted_second == 0
    assert db.count_scenarios() == 1


# ── 5. k-NN query ─────────────────────────────────────────────────────────

def test_query_nearest_returns_k_results(db: ClassifierDB):
    # Insert 50 scenarios with random embeddings + one "target" close to query
    target = _vec(seed=7)
    for i in range(49):
        db.insert_scenario(
            abstract_text=f"random {i}",
            intent_label="casual_conversation",
            embedding=_vec(seed=100 + i),
            source_tag="test",
            source_version="v1",
        )
    target_id = db.insert_scenario(
        abstract_text="target — closest to query",
        intent_label="casual_conversation",
        embedding=target,
        source_tag="test",
        source_version="v1",
    )

    # Query with the same vector → target should be the top result
    results = db.query_nearest(target, k=10)
    assert len(results) == 10
    assert results[0]["scenario_id"] == target_id
    assert results[0]["similarity"] > 0.99  # essentially identical vector

    # Results are sorted by similarity DESC
    sims = [r["similarity"] for r in results]
    assert sims == sorted(sims, reverse=True)


# ── 6. Quarantine excluded from query ─────────────────────────────────────

def test_query_nearest_excludes_quarantined(db: ClassifierDB):
    target = _vec(seed=11)
    quarantined_id = db.insert_scenario(
        abstract_text="will be quarantined",
        intent_label="casual_conversation",
        embedding=target,
        source_tag="test",
        source_version="v1",
    )
    other_id = db.insert_scenario(
        abstract_text="active alternative",
        intent_label="casual_conversation",
        embedding=_vec(seed=12),
        source_tag="test",
        source_version="v1",
    )
    db.quarantine(quarantined_id, reason="bad data")

    # Default (active_only=True) excludes the quarantined row
    results = db.query_nearest(target, k=10)
    ids = [r["scenario_id"] for r in results]
    assert quarantined_id not in ids
    assert other_id in ids

    # active_only=False includes it
    results_all = db.query_nearest(target, k=10, active_only=False)
    ids_all = [r["scenario_id"] for r in results_all]
    assert quarantined_id in ids_all


# ── 7. Audit log on outcome change ────────────────────────────────────────

def test_increment_outcome_writes_audit_log(db: ClassifierDB, db_paths):
    _, audit_path = db_paths
    sid = db.insert_scenario(
        abstract_text="audit test",
        intent_label="casual_conversation",
        embedding=_vec(seed=1),
        source_tag="test",
        source_version="v1",
    )
    db.increment_outcome(sid, kind="confirmed", decision_id="dec-123", reason="gate validated")
    db.increment_outcome(sid, kind="reverted", decision_id="dec-456", reason="user corrected")

    # Counter values reflect both increments
    s = db.get_scenario(sid)
    assert s["outcome_confirmed"] == 1
    assert s["outcome_reverted"] == 1

    # SQL audit_log captures both events
    rows = list(db._conn.execute(
        "SELECT event_type, delta, decision_id, reason FROM audit_log "
        "WHERE scenario_id = ? ORDER BY id",
        (sid,),
    ))
    # First event = "created" from insert; then confirmed + reverted
    event_types = [r[0] for r in rows]
    assert "outcome_confirmed" in event_types
    assert "outcome_reverted" in event_types
    confirmed_row = next(r for r in rows if r[0] == "outcome_confirmed")
    assert confirmed_row[1] == 1
    assert confirmed_row[2] == "dec-123"
    assert confirmed_row[3] == "gate validated"

    # JSONL audit log mirrors the SQL events
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    parsed = [json.loads(l) for l in lines]
    confirmed_jsonl = [p for p in parsed if p["event_type"] == "outcome_confirmed"]
    assert len(confirmed_jsonl) == 1
    assert confirmed_jsonl[0]["decision_id"] == "dec-123"


# ── 8. Quarantine sets active=0 ───────────────────────────────────────────

def test_quarantine_sets_active_zero(db: ClassifierDB):
    sid = db.insert_scenario(
        abstract_text="quarantine target",
        intent_label="casual_conversation",
        embedding=_vec(seed=2),
        source_tag="test",
        source_version="v1",
    )
    assert db.get_scenario(sid)["active"] == 1

    db.quarantine(sid, reason="manual quarantine")
    assert db.get_scenario(sid)["active"] == 0

    # Audit log records the quarantine event
    events = [r[0] for r in db._conn.execute(
        "SELECT event_type FROM audit_log WHERE scenario_id = ?", (sid,)
    )]
    assert "quarantined" in events


# ── 9. Label evolution maps deprecated labels ─────────────────────────────

def test_label_evolution_resolves_old_labels(db: ClassifierDB):
    # Insert a scenario under an "old" label, then declare a label_evolution
    sid = db.insert_scenario(
        abstract_text="written under old label",
        intent_label="addressing_ai",  # hypothetically deprecated
        embedding=_vec(seed=3),
        source_tag="test",
        source_version="v1",
    )
    db.add_label_evolution(
        old_label="addressing_ai",
        new_label="casual_conversation",
        effective_version=2,
        reason="merged into casual_conversation",
    )

    # query_nearest / get_scenario should return the resolved (new) label
    s = db.get_scenario(sid)
    assert s["intent_label"] == "casual_conversation"

    results = db.query_nearest(_vec(seed=3), k=5)
    matching = [r for r in results if r["scenario_id"] == sid]
    assert len(matching) == 1
    assert matching[0]["intent_label"] == "casual_conversation"


# ── 10. Factory reset must NOT touch classifier_scenarios.db ──────────────

def test_factory_reset_does_not_touch_classifier_db(db_paths, tmp_path: Path, monkeypatch):
    """wipe_all() targets faces/ + sim_session_state.json. The classifier
    DB lives under data/ and must survive a factory reset.

    HISTORICAL FIX (2026-04-28): earlier versions of this test called
    `wipe_all()` directly with NO monkeypatch — the call operated on the
    REAL faces/ directory and silently wiped enrolled-face data,
    conversation history, brain.db facts, and Kuzu graph on every pytest
    run for several days. The test author noted the issue in a comment
    (`"can't redirect without monkey-patching"`) but never came back to
    fix it. This version monkey-patches the path constants on `core.db`
    so wipe_all only deletes files inside tmp_path. Test intent
    preserved (verifies classifier_scenarios.db survives) with zero
    side effects on production data.
    """
    db_path, audit_path = db_paths

    # Create the classifier DB and insert a row so we can verify survival
    db = ClassifierDB(db_path=db_path, audit_log_path=audit_path)
    sid = db.insert_scenario(
        abstract_text="survives factory reset",
        intent_label="casual_conversation",
        embedding=_vec(seed=4),
        source_tag="test",
        source_version="v1",
    )
    db.close()
    assert db_path.exists()

    # ── Redirect production paths to tmp_path BEFORE calling wipe_all ──
    # wipe_all() reads core.db's module-level path constants. Pointing
    # them at tmp_path/fake_faces/* means the destructive operation
    # only deletes files inside the test's temp dir, not real production
    # data.
    import core.db as _core_db

    fake_faces_dir = tmp_path / "fake_faces"
    fake_faces_dir.mkdir()
    fake_faces_db = fake_faces_dir / "faces.db"
    fake_brain_db = fake_faces_dir / "brain.db"
    fake_faiss = fake_faces_dir / "faiss.index"
    fake_graph = fake_faces_dir / "brain_graph"

    # Create dummy files so wipe_all has something to delete (verifies the
    # redirect actually took effect — we can sanity-check that wipe_all
    # ran by asserting the fakes are gone afterward).
    fake_faces_db.touch()
    fake_brain_db.touch()
    fake_faiss.touch()
    fake_graph.mkdir()

    monkeypatch.setattr(_core_db, "DB_PATH",          fake_faces_db)
    monkeypatch.setattr(_core_db, "BRAIN_DB_PATH",    fake_brain_db)
    monkeypatch.setattr(_core_db, "FAISS_INDEX_PATH", fake_faiss)
    monkeypatch.setattr(_core_db, "GRAPH_DB_PATH",    fake_graph)
    monkeypatch.setattr(_core_db, "FACES_DIR",        fake_faces_dir)

    # Run wipe_all — it now operates on the redirected fake paths.
    try:
        _core_db.wipe_all()
    except Exception:
        # Even if wipe_all hits something missing, our DB must remain.
        pass

    # Sanity check: the fake faces.db DID get deleted, proving the
    # redirect worked AND wipe_all is still functional. If the fake
    # file is still there, wipe_all wasn't reading our patched path.
    assert not fake_faces_db.exists(), (
        "wipe_all redirect failed — fake faces.db wasn't deleted; "
        "monkeypatch didn't take effect (CRITICAL: test would silently "
        "wipe real production data again)"
    )

    # The actual assertion: classifier DB outside tmp_path/fake_faces survives
    assert db_path.exists(), "classifier_scenarios.db was deleted by factory reset"
    db2 = ClassifierDB(db_path=db_path, audit_log_path=audit_path)
    try:
        survivor = db2.get_scenario(sid)
        assert survivor is not None
        assert survivor["abstract_text"] == "survives factory reset"
    finally:
        db2.close()


# ── 11. Abstraction strips PERSON + LOC entities ──────────────────────────

def test_abstract_strips_person_and_loc_entities():
    """spacy's NER replaces PERSON and GPE/LOC with placeholders."""
    from bootstrap.classifier.stage_4_abstract import abstract_text

    # Use a fake spacy doc instead of loading the real model — keeps the
    # test fast + free from `spacy download` setup.
    class FakeEnt:
        def __init__(self, text, label, start, end):
            self.text = text
            self.label_ = label
            self.start_char = start
            self.end_char = end

    class FakeDoc:
        def __init__(self, ents):
            self.ents = ents

    class FakeNlp:
        def __call__(self, text):
            ents = []
            # Locate "Alex" and "Boston" and "Sarah" by index
            for needle, label in [("Alex", "PERSON"), ("Sarah", "PERSON"),
                                  ("Boston", "GPE"), ("Paris", "GPE")]:
                idx = text.find(needle)
                if idx >= 0:
                    ents.append(FakeEnt(needle, label, idx, idx + len(needle)))
            return FakeDoc(ents)

    nlp = FakeNlp()

    # Single PERSON
    out, mapping = abstract_text("Hey Alex, can you grab the door?", nlp=nlp)
    assert "{P1}" in out
    assert "Alex" not in out
    assert mapping["Alex"] == "{P1}"

    # PERSON + LOC
    out2, mapping2 = abstract_text("Sarah went to Boston yesterday.", nlp=nlp)
    assert "{P1}" in out2 and "{LOC1}" in out2
    assert "Sarah" not in out2 and "Boston" not in out2

    # Multiple unique PERSONs get distinct placeholders
    out3, mapping3 = abstract_text("Alex told Sarah about the plan.", nlp=nlp)
    assert mapping3["Alex"] == "{P1}"
    assert mapping3["Sarah"] == "{P2}"
    assert "{P1}" in out3 and "{P2}" in out3


# ── 12. Abstraction preserves times + numbers ─────────────────────────────

def test_abstract_preserves_times_and_numbers():
    """Times, dates, numbers carry intent signal — must NOT be abstracted."""
    from bootstrap.classifier.stage_4_abstract import abstract_text

    class FakeEnt:
        def __init__(self, text, label, start, end):
            self.text = text
            self.label_ = label
            self.start_char = start
            self.end_char = end

    class FakeDoc:
        def __init__(self, ents):
            self.ents = ents

    class FakeNlp:
        def __call__(self, text):
            # Real spacy would tag "tomorrow" as DATE, "3pm" as TIME, "5" as
            # CARDINAL. The abstractor's PERSON_TYPES + PLACE_TYPES sets
            # exclude all three, so they fall through unchanged.
            ents = []
            for needle, label in [("tomorrow", "DATE"), ("3pm", "TIME"),
                                  ("5", "CARDINAL"), ("$50", "MONEY")]:
                idx = text.find(needle)
                if idx >= 0:
                    ents.append(FakeEnt(needle, label, idx, idx + len(needle)))
            return FakeDoc(ents)

    nlp = FakeNlp()

    out, mapping = abstract_text("What's the weather tomorrow at 3pm?", nlp=nlp)
    assert "tomorrow" in out
    assert "3pm" in out
    assert mapping == {}  # nothing was abstracted

    out2, _ = abstract_text("I'll be there in 5 minutes for the $50 thing.", nlp=nlp)
    assert "5" in out2
    assert "$50" in out2
