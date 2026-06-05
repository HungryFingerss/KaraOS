"""test_pipeline_stranger_pruning — stranger pruning tests (split from test_pipeline.py, P1.A1 SP-1).

Behavior-neutral move: test bodies are verbatim from the original root
test_pipeline.py. `import pipeline` stays lazy inside each test body (stubs are
installed by tests/conftest.py).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import asyncio
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
import types
import pytest
import numpy as np
import time as _time_mod
import numpy as _np


def test_prune_old_strangers_deletes_old(tmp_path):
    """BUG-3: Strangers unseen longer than STRANGER_TTL_DAYS must be pruned and their
    person_id returned so the caller can clean brain.db orphans too."""
    import time
    from core.db import FaceDB

    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))
    old_ts = time.time() - 8 * 86400   # 8 days ago — beyond 7-day TTL
    db._conn.execute(
        "INSERT INTO persons (id, name, person_type, enrolled_at, last_seen) VALUES (?,?,?,?,?)",
        ("stranger_old", "visitor", "stranger", old_ts, old_ts)
    )
    db._conn.commit()

    deleted = db.prune_old_strangers(days=7)

    assert "stranger_old" in deleted
    row = db._conn.execute("SELECT id FROM persons WHERE id = 'stranger_old'").fetchone()
    assert row is None   # removed from DB
    db._conn.close()


def test_prune_old_strangers_keeps_recent(tmp_path):
    """BUG-3: Strangers seen within STRANGER_TTL_DAYS must NOT be pruned."""
    import time
    from core.db import FaceDB

    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))
    recent_ts = time.time() - 2 * 86400   # 2 days ago — within TTL
    db._conn.execute(
        "INSERT INTO persons (id, name, person_type, enrolled_at, last_seen) VALUES (?,?,?,?,?)",
        ("stranger_new", "visitor", "stranger", recent_ts, recent_ts)
    )
    db._conn.commit()

    deleted = db.prune_old_strangers(days=7)

    assert deleted == []
    row = db._conn.execute("SELECT id FROM persons WHERE id = 'stranger_new'").fetchone()
    assert row is not None   # still in DB
    db._conn.close()


def test_prune_old_strangers_keeps_known(tmp_path):
    """BUG-3: Known persons must never be touched by prune_old_strangers()."""
    import time
    from core.db import FaceDB

    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))
    old_ts = time.time() - 30 * 86400   # 30 days ago — way beyond TTL
    db._conn.execute(
        "INSERT INTO persons (id, name, person_type, enrolled_at, last_seen) VALUES (?,?,?,?,?)",
        ("jagan_001", "Jagan", "known", old_ts, old_ts)
    )
    db._conn.commit()

    deleted = db.prune_old_strangers(days=7)

    assert "jagan_001" not in deleted
    row = db._conn.execute("SELECT id FROM persons WHERE id = 'jagan_001'").fetchone()
    assert row is not None   # known person untouched
    db._conn.close()


def test_prune_zero_value_stranger_deletes_when_all_zero(tmp_path):
    """Fix 2 (a): stranger with zero voice embeddings AND zero
    conversation turns → deleted on first close. Guards the primary
    code path the feature exists to accelerate."""
    import time
    from core.db import FaceDB

    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))
    db._conn.execute(
        "INSERT INTO persons (id, name, person_type, enrolled_at, last_seen) VALUES (?,?,?,?,?)",
        ("stranger_ghost", "visitor", "stranger", time.time(), time.time()),
    )
    db._conn.commit()

    pruned = db.prune_zero_value_stranger("stranger_ghost")

    assert pruned is True
    row = db._conn.execute("SELECT id FROM persons WHERE id = 'stranger_ghost'").fetchone()
    assert row is None
    db._conn.close()


def test_prune_zero_value_stranger_preserves_voice_samples(tmp_path):
    """Fix 2 (b): a stranger with even ONE accumulated voice embedding
    must survive the immediate prune — that sample is data we want to
    keep on a re-visit. Only the 7-day TTL should eventually sweep it."""
    import time
    import numpy as np
    from core.db import FaceDB

    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))
    db._conn.execute(
        "INSERT INTO persons (id, name, person_type, enrolled_at, last_seen) VALUES (?,?,?,?,?)",
        ("stranger_with_voice", "visitor", "stranger", time.time(), time.time()),
    )
    vec = np.zeros(192, dtype=np.float32).tobytes()
    db._conn.execute(
        "INSERT INTO voice_embeddings (person_id, vector, captured_at, source) "
        "VALUES (?, ?, ?, 'voice_self_match')",
        ("stranger_with_voice", vec, time.time()),
    )
    db._conn.commit()

    pruned = db.prune_zero_value_stranger("stranger_with_voice")

    assert pruned is False
    row = db._conn.execute(
        "SELECT id FROM persons WHERE id = 'stranger_with_voice'"
    ).fetchone()
    assert row is not None
    db._conn.close()


def test_prune_zero_value_stranger_preserves_conversation_turns(tmp_path):
    """Fix 2 (c): a stranger with logged conversation turns must survive
    the immediate prune. Turns are a signal the stranger actually
    interacted — even without a voice sample, that history has value
    (visitor alert nudges, HouseholdAgent shadow facts)."""
    import time
    from core.db import FaceDB

    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))
    db._conn.execute(
        "INSERT INTO persons (id, name, person_type, enrolled_at, last_seen) VALUES (?,?,?,?,?)",
        ("stranger_with_turn", "visitor", "stranger", time.time(), time.time()),
    )
    db._conn.execute(
        "INSERT INTO conversation_log (person_id, role, content) VALUES (?,?,?)",
        ("stranger_with_turn", "user", "hello"),
    )
    db._conn.commit()

    pruned = db.prune_zero_value_stranger("stranger_with_turn")

    assert pruned is False
    row = db._conn.execute(
        "SELECT id FROM persons WHERE id = 'stranger_with_turn'"
    ).fetchone()
    assert row is not None
    db._conn.close()


def test_prune_zero_value_stranger_refuses_known_person(tmp_path):
    """Fix 2 (d) safety triple-check: even if called with a known or
    best_friend pid that happens to have no voice/turns (impossible in
    practice but defensive), the person_type gate must reject the
    delete. Catching this case here makes it impossible for a mistaken
    caller to nuke the owner's row."""
    import time
    from core.db import FaceDB

    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))
    db._conn.execute(
        "INSERT INTO persons (id, name, person_type, enrolled_at, last_seen) VALUES (?,?,?,?,?)",
        ("jagan_001", "Jagan", "best_friend", time.time(), time.time()),
    )
    db._conn.commit()

    pruned = db.prune_zero_value_stranger("jagan_001")

    assert pruned is False
    row = db._conn.execute("SELECT id FROM persons WHERE id = 'jagan_001'").fetchone()
    assert row is not None
    db._conn.close()


def test_add_stranger_accepts_custom_person_id(tmp_path):
    """add_stranger(person_id=X) must store X as the DB primary key, not a generated ID."""
    from core.db import FaceDB
    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))

    custom_id = "stranger_abc12345"
    returned = db.add_stranger("visitor", person_id=custom_id)

    assert returned == custom_id, f"Expected {custom_id}, got {returned}"
    row = db._conn.execute(
        "SELECT id, person_type FROM persons WHERE id = ?", (custom_id,)
    ).fetchone()
    assert row is not None, "DB entry must exist after add_stranger with custom ID"
    assert row[0] == custom_id
    assert row[1] == "stranger"
    db._conn.close()


def test_add_stranger_custom_id_idempotent(tmp_path):
    """add_stranger called twice with the same person_id must not raise and must keep one row."""
    from core.db import FaceDB
    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))

    custom_id = "stranger_dup12345"
    db.add_stranger("visitor", person_id=custom_id)
    # Second call — must not raise (INSERT OR IGNORE)
    returned = db.add_stranger("visitor", person_id=custom_id)
    assert returned == custom_id

    count = db._conn.execute(
        "SELECT COUNT(*) FROM persons WHERE id = ?", (custom_id,)
    ).fetchone()[0]
    assert count == 1, "Idempotent call must not create a duplicate row"
    db._conn.close()


def test_add_stranger_generates_id_when_no_person_id(tmp_path):
    """add_stranger without person_id must still generate a unique stranger_*_* ID (no regression)."""
    from core.db import FaceDB
    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))

    sid = db.add_stranger("visitor")
    assert sid.startswith("stranger_visitor_"), f"Generated ID format changed: {sid}"
    db._conn.close()


def test_add_stranger_sets_last_seen(tmp_path):
    """add_stranger must set last_seen so TTL prune can find the row."""
    from core.db import FaceDB
    import time
    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))
    before = time.time()
    sid = db.add_stranger("visitor", person_id="stranger_test_001")
    row = db._conn.execute(
        "SELECT last_seen FROM persons WHERE id = ?", (sid,)
    ).fetchone()
    assert row is not None
    assert row[0] is not None, "last_seen must not be NULL after add_stranger()"
    assert row[0] >= before
    db._conn.close()


def test_prune_old_strangers_catches_null_last_seen(tmp_path):
    """prune_old_strangers must delete rows where last_seen IS NULL (legacy data)."""
    from core.db import FaceDB
    import time
    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))
    db._conn.execute(
        "INSERT INTO persons (id, name, enrolled_at, last_seen, person_type) "
        "VALUES (?, ?, ?, NULL, 'stranger')",
        ("stranger_null_001", "visitor", time.time()),
    )
    db._conn.commit()
    pruned = db.prune_old_strangers(days=0)
    assert "stranger_null_001" in pruned, "NULL last_seen stranger must be pruned"
    db._conn.close()


def test_delete_person_data_covers_inter_person_relationships(tmp_path):
    """delete_person_data removes inter_person_relationships rows for the deleted person."""
    import time
    from core.brain_agent import BrainDB

    brain_db = BrainDB(tmp_path / "brain.db")
    brain_db._conn.execute(
        "INSERT INTO inter_person_relationships "
        "(person_a, relationship, person_b, source_speaker, confidence, created_at, updated_at) "
        "VALUES ('alice', 'married_to', 'Bob', 'alice', 0.9, ?, ?)",
        (time.time(), time.time()),
    )
    brain_db._conn.commit()

    brain_db.delete_person_data(["alice"])
    count = brain_db._conn.execute(
        "SELECT COUNT(*) FROM inter_person_relationships WHERE person_a = 'alice'"
    ).fetchone()[0]
    assert count == 0
    brain_db.close()


def test_delete_person_data_cleans_household_facts_source_speakers(tmp_path):
    """delete_person_data removes deleted person's id from household_facts.source_speakers JSON."""
    import time, json
    from core.brain_agent import BrainDB

    brain_db = BrainDB(tmp_path / "brain.db")
    brain_db._conn.execute(
        "INSERT INTO household_facts "
        "(entity, attribute, value, scope, source_speakers, confidence, conflict_status, first_seen, last_confirmed) "
        "VALUES ('household', 'dinner_time', '7pm', 'household', ?, 0.8, 'settled', ?, ?)",
        (json.dumps(["alice", "bob"]), time.time(), time.time()),
    )
    brain_db._conn.commit()

    brain_db.delete_person_data(["alice"])
    row = brain_db._conn.execute(
        "SELECT source_speakers FROM household_facts WHERE attribute = 'dinner_time'"
    ).fetchone()
    assert row is not None
    speakers = json.loads(row[0])
    assert "alice" not in speakers
    assert "bob" in speakers
    brain_db.close()


def test_prune_shadows_mentioning_removes_matching_entry(tmp_path):
    """prune_shadows_mentioning strips references to a deleted person from known_via."""
    import time, json
    from core.brain_agent import BrainDB

    brain_db = BrainDB(tmp_path / "brain.db")
    brain_db._conn.execute(
        "INSERT INTO shadow_persons "
        "(shadow_id, known_name, known_via, enrollment_status, facts, first_mentioned, last_mentioned) "
        "VALUES ('sh1', 'Anita', ?, 'pending', '[]', ?, ?)",
        (
            json.dumps([{"person_id": "alice", "relationship": "colleague"}]),
            time.time(), time.time(),
        ),
    )
    brain_db._conn.commit()

    affected = brain_db.prune_shadows_mentioning("alice", "Alice")
    assert affected == 1

    row = brain_db._conn.execute(
        "SELECT shadow_id FROM shadow_persons WHERE shadow_id = 'sh1'"
    ).fetchone()
    assert row is None, "Shadow with empty known_via should be deleted"
    brain_db.close()


def test_prune_shadows_mentioning_keeps_shadow_with_other_refs(tmp_path):
    """Shadow with references to multiple persons keeps remaining entries after deletion."""
    import time, json
    from core.brain_agent import BrainDB

    brain_db = BrainDB(tmp_path / "brain.db")
    brain_db._conn.execute(
        "INSERT INTO shadow_persons "
        "(shadow_id, known_name, known_via, enrollment_status, facts, first_mentioned, last_mentioned) "
        "VALUES ('sh2', 'Raj', ?, 'pending', '[]', ?, ?)",
        (
            json.dumps([
                {"person_id": "alice", "relationship": "colleague"},
                {"person_id": "bob", "relationship": "friend"},
            ]),
            time.time(), time.time(),
        ),
    )
    brain_db._conn.commit()

    brain_db.prune_shadows_mentioning("alice", "Alice")

    row = brain_db._conn.execute(
        "SELECT known_via FROM shadow_persons WHERE shadow_id = 'sh2'"
    ).fetchone()
    assert row is not None, "Shadow with remaining refs should NOT be deleted"
    remaining = json.loads(row[0])
    assert len(remaining) == 1
    assert remaining[0]["person_id"] == "bob"
    brain_db.close()


def test_delete_person_nulls_silent_observations(tmp_path):
    import time
    from core.db import FaceDB
    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "faiss.index")
    # Create person
    db._conn.execute(
        "INSERT INTO persons (id, name, enrolled_at, person_type) VALUES ('p1', 'Alice', ?, 'known')",
        (time.time(),),
    )
    import numpy as np
    dummy_emb = np.zeros(512, dtype=np.float32).tobytes()
    # Insert a silent_observations row matched to p1
    db._conn.execute(
        "INSERT INTO silent_observations (id, first_seen, last_seen, duration_secs, frame_count, embedding, created_at, matched_person_id)"
        " VALUES ('obs1', ?, ?, 1.0, 5, ?, ?, 'p1')",
        (time.time(), time.time(), dummy_emb, time.time()),
    )
    db._conn.commit()

    db.delete_person("p1")

    row = db._conn.execute("SELECT matched_person_id FROM silent_observations").fetchone()
    assert row is not None, "observation row should still exist"
    assert row[0] is None, "matched_person_id should be NULL after person deletion"
    db._conn.close()


def test_delete_person_everywhere_skips_graph_when_name_shared(tmp_path):
    """If two enrolled persons share a name, graph delete must be skipped
    (Kuzu Entity PK is name — deleting by name would wipe the other person)."""
    import time
    from unittest.mock import MagicMock
    from core.db import FaceDB
    from person_lifecycle import delete_person_everywhere

    faces_db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "f.index")
    # Two persons share the name "Sam"
    faces_db._conn.execute(
        "INSERT INTO persons (id, name, enrolled_at, person_type) VALUES ('p1', 'Sam', ?, 'known')",
        (time.time(),),
    )
    faces_db._conn.execute(
        "INSERT INTO persons (id, name, enrolled_at, person_type) VALUES ('p2', 'Sam', ?, 'known')",
        (time.time(),),
    )
    faces_db._conn.commit()

    brain_orch = MagicMock()
    brain_orch.brain_db.delete_person_data.return_value = 0
    brain_orch.brain_db.prune_shadows_mentioning.return_value = 0
    brain_orch.graph_db.delete_person_entity.return_value = True

    try:
        summary = delete_person_everywhere("p1", "Sam", faces_db, brain_orch)
    finally:
        faces_db._conn.close()

    # Graph delete must have been skipped — p2 still shares the name
    brain_orch.graph_db.delete_person_entity.assert_not_called()
    assert "skipped" in summary["graph"]


def test_delete_person_everywhere_deletes_graph_when_name_unique(tmp_path):
    """With a unique name, graph delete proceeds normally."""
    import time
    from unittest.mock import MagicMock
    from core.db import FaceDB
    from person_lifecycle import delete_person_everywhere

    faces_db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "f.index")
    faces_db._conn.execute(
        "INSERT INTO persons (id, name, enrolled_at, person_type) VALUES ('p1', 'Alice', ?, 'known')",
        (time.time(),),
    )
    faces_db._conn.commit()

    brain_orch = MagicMock()
    brain_orch.brain_db.delete_person_data.return_value = 0
    brain_orch.brain_db.prune_shadows_mentioning.return_value = 0
    brain_orch.graph_db.delete_person_entity.return_value = True

    try:
        summary = delete_person_everywhere("p1", "Alice", faces_db, brain_orch)
    finally:
        faces_db._conn.close()

    brain_orch.graph_db.delete_person_entity.assert_called_once_with("Alice")
    assert summary["graph"] == "ok"


def test_find_stale_stranger_voice_ids_is_non_destructive(tmp_path):
    """Finding J — find_*_ids must return the same set as prune_* but leave rows intact,
    so callers can evict in-memory caches before the destructive prune runs."""
    import time, numpy as np
    from core.db import FaceDB
    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "f.index")
    db._conn.execute(
        "INSERT INTO persons (id, name, enrolled_at, person_type, last_seen) "
        "VALUES ('stranger_old', 'v', ?, 'stranger', ?)",
        (time.time(), time.time()),
    )
    old_ts = time.time() - 10 * 86400
    emb = np.random.randn(192).astype(np.float32)
    db._conn.execute(
        "INSERT INTO voice_embeddings (person_id, vector, captured_at, source, confidence_at_write) "
        "VALUES (?, ?, ?, 'voice_self_match', 0.5)",
        ("stranger_old", emb.tobytes(), old_ts),
    )
    db._conn.commit()
    try:
        found = db.find_stale_stranger_voice_ids(days=3)
        assert found == ["stranger_old"]
        # Non-destructive — row should still be there
        remaining = db._conn.execute(
            "SELECT COUNT(*) FROM voice_embeddings WHERE person_id='stranger_old'"
        ).fetchone()[0]
        assert remaining == 1
        # Now actually prune and confirm row is gone
        pruned = db.prune_stale_stranger_voice(days=3)
        assert pruned == ["stranger_old"]
        remaining = db._conn.execute(
            "SELECT COUNT(*) FROM voice_embeddings WHERE person_id='stranger_old'"
        ).fetchone()[0]
        assert remaining == 0
    finally:
        db._conn.close()


def test_prune_stale_stranger_voice_removes_thin_profiles(tmp_path):
    """Stranger voice rows should be pruned if profile never reached N_INITIAL_VOICE samples
    and hasn't been updated within the TTL window."""
    import time, numpy as np
    from core.db import FaceDB
    from core.config import N_INITIAL_VOICE

    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "f.index")
    # Stranger with 2 voice samples (< N_INITIAL_VOICE), last one 10 days old
    db._conn.execute(
        "INSERT INTO persons (id, name, enrolled_at, person_type, last_seen) "
        "VALUES ('stranger_1', 'visitor', ?, 'stranger', ?)",
        (time.time(), time.time()),
    )
    old_ts = time.time() - 10 * 86400
    emb = np.random.randn(192).astype(np.float32)
    for _ in range(2):
        db._conn.execute(
            "INSERT INTO voice_embeddings (person_id, vector, captured_at, source, confidence_at_write) "
            "VALUES (?, ?, ?, 'voice_self_match', 0.5)",
            ("stranger_1", emb.tobytes(), old_ts),
        )
    db._conn.commit()

    try:
        pruned_ids = db.prune_stale_stranger_voice(days=3)
        assert pruned_ids == ["stranger_1"]
        remaining = db._conn.execute(
            "SELECT COUNT(*) FROM voice_embeddings WHERE person_id='stranger_1'"
        ).fetchone()[0]
        assert remaining == 0
    finally:
        db._conn.close()


def test_prune_stale_stranger_voice_keeps_mature_profiles(tmp_path):
    """A stranger with a mature voice profile (>= N_INITIAL_VOICE samples) must not be pruned."""
    import time, numpy as np
    from core.db import FaceDB
    from core.config import N_INITIAL_VOICE

    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "f.index")
    db._conn.execute(
        "INSERT INTO persons (id, name, enrolled_at, person_type, last_seen) "
        "VALUES ('stranger_1', 'visitor', ?, 'stranger', ?)",
        (time.time(), time.time()),
    )
    old_ts = time.time() - 10 * 86400
    emb = np.random.randn(192).astype(np.float32)
    for _ in range(N_INITIAL_VOICE):
        db._conn.execute(
            "INSERT INTO voice_embeddings (person_id, vector, captured_at, source, confidence_at_write) "
            "VALUES (?, ?, ?, 'voice_self_match', 0.5)",
            ("stranger_1", emb.tobytes(), old_ts),
        )
    db._conn.commit()
    try:
        pruned_ids = db.prune_stale_stranger_voice(days=3)
        assert pruned_ids == []
    finally:
        db._conn.close()


def test_prune_stale_stranger_voice_keeps_known_persons(tmp_path):
    """Known persons must never be touched by stranger-voice pruning."""
    import time, numpy as np
    from core.db import FaceDB

    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "f.index")
    db._conn.execute(
        "INSERT INTO persons (id, name, enrolled_at, person_type) VALUES ('jagan', 'Jagan', ?, 'known')",
        (time.time(),),
    )
    old_ts = time.time() - 30 * 86400
    emb = np.random.randn(192).astype(np.float32)
    db._conn.execute(
        "INSERT INTO voice_embeddings (person_id, vector, captured_at, source, confidence_at_write) "
        "VALUES (?, ?, ?, 'voice_self_match', 0.5)",
        ("jagan", emb.tobytes(), old_ts),
    )
    db._conn.commit()
    try:
        pruned_ids = db.prune_stale_stranger_voice(days=3)
        assert pruned_ids == []
    finally:
        db._conn.close()


def test_prune_stale_stranger_voice_returns_list_of_ids(tmp_path):
    """Return value must be list[str] so pipeline can evict _voice_gallery entries."""
    import time, numpy as np
    from core.db import FaceDB

    db = FaceDB(db_path=tmp_path / "faces.db", faiss_path=tmp_path / "f.index")
    db._conn.execute(
        "INSERT INTO persons (id, name, enrolled_at, person_type, last_seen) "
        "VALUES ('stranger_a', 'v1', ?, 'stranger', ?)",
        (time.time(), time.time()),
    )
    db._conn.execute(
        "INSERT INTO persons (id, name, enrolled_at, person_type, last_seen) "
        "VALUES ('stranger_b', 'v2', ?, 'stranger', ?)",
        (time.time(), time.time()),
    )
    old_ts = time.time() - 10 * 86400
    emb = np.random.randn(192).astype(np.float32)
    for pid in ("stranger_a", "stranger_b"):
        db._conn.execute(
            "INSERT INTO voice_embeddings (person_id, vector, captured_at, source, confidence_at_write) "
            "VALUES (?, ?, ?, 'voice_self_match', 0.5)",
            (pid, emb.tobytes(), old_ts),
        )
    db._conn.commit()
    try:
        pruned = db.prune_stale_stranger_voice(days=3)
        assert isinstance(pruned, list)
        assert set(pruned) == {"stranger_a", "stranger_b"}
    finally:
        db._conn.close()
