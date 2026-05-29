"""tests/test_p0_s7_phase1.py — P0.S7 Phase 1 (D-A: SHARED CONTEXT block).

Plan v2 §8 Phase 1 = 9 new tests:

  1. test_get_recent_room_conversation_returns_audience_visible_rows
  2. test_get_recent_room_conversation_legacy_null_audience_visible
  3. test_get_recent_room_conversation_best_friend_owner_override
  4. test_get_recent_room_conversation_room_session_id_filter
  5. test_get_recent_room_conversation_pid_collision_rejection
  6. test_get_recent_room_conversation_underscore_wildcard_rejection (CRITICAL 1)
  7. test_get_recent_room_conversation_empty_room_session_id_graceful
  8. test_compute_room_audience_speaker_always_present  (LOW 5 — helper unit)
  9. test_log_turn_persists_full_room_audience_to_db    (LOW 5 — DB persistence)

Plus latency budget test from Plan v2 §10 (median-of-10).

Plan v2 §8.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import json
import statistics
import time
from unittest.mock import patch

import pytest


# ────────────────────────────────────────────────────────────────────────────
# Shared fixture — temp FaceDB
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path):
    import core.db as _db_mod
    db_path = tmp_path / "faces.db"
    idx_path = tmp_path / "faiss.index"
    with patch.object(_db_mod, "DB_PATH", db_path), \
         patch.object(_db_mod, "FAISS_INDEX_PATH", idx_path):
        d = _db_mod.FaceDB()
        # Pre-create the personas we use across the suite.
        for pid, name in [
            ("jagan_001",  "Jagan"),
            ("jagan_0011", "Jagan-suffix-collision"),
            ("lexi_xyz",   "Lexi"),
            ("kara_friend","Kara_friend"),
            ("stranger_a", "Stranger A"),
            ("stranger_b", "Stranger B"),
        ]:
            try:
                d.add_person(pid, name)
            except Exception:
                pass
        yield d
        try:
            d._conn.close()
        except Exception:
            pass


def _seed_turn(db, *, person_id: str, role: str, content: str,
               room_session_id: str, audience_ids, ts: "float | None" = None):
    """Insert one conversation_log row at a controlled ts (sec-precision is
    fine for ordering; turns within the same second are ordered by rowid)."""
    if ts is None:
        ts = time.time()
    aud_json = json.dumps(audience_ids) if audience_ids is not None else None
    db._conn.execute(
        "INSERT INTO conversation_log "
        "(person_id, role, content, ts, room_session_id, audience_ids) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (person_id, role, content, ts, room_session_id, aud_json),
    )
    db._conn.commit()


# ────────────────────────────────────────────────────────────────────────────
# (1-5) Visibility + ordering
# ────────────────────────────────────────────────────────────────────────────


def test_get_recent_room_conversation_returns_audience_visible_rows(db):
    """Plan v2 test 1 — 3 turns with mixed audience_ids `[a]`, `[a,b]`, `[b]`;
    query as requester `a`; assert returns first 2 rows ordered by ts."""
    room = "room_visible"
    t0 = 1779010000.0
    _seed_turn(db, person_id="jagan_001",  role="user",      content="A only",
               room_session_id=room, audience_ids=["jagan_001"], ts=t0 + 1)
    _seed_turn(db, person_id="lexi_xyz",   role="user",      content="A and B",
               room_session_id=room, audience_ids=["jagan_001", "lexi_xyz"], ts=t0 + 2)
    _seed_turn(db, person_id="lexi_xyz",   role="assistant", content="B only",
               room_session_id=room, audience_ids=["lexi_xyz"], ts=t0 + 3)

    rows = db.get_recent_room_conversation(
        room_session_id=room, requester_pid="jagan_001",
        best_friend_id=None, limit=10,
    )
    assert len(rows) == 2
    assert [r["text"] for r in rows] == ["A only", "A and B"]
    # Ordered by ts ASC.
    assert rows[0]["ts"] <= rows[1]["ts"]


def test_get_recent_room_conversation_legacy_null_audience_visible(db):
    """Plan v2 test 2 — legacy backfill row (audience_ids=NULL) visible to all."""
    room = "room_legacy"
    _seed_turn(db, person_id="jagan_001", role="user", content="legacy turn",
               room_session_id=room, audience_ids=None)
    rows = db.get_recent_room_conversation(
        room_session_id=room, requester_pid="jagan_001",
        best_friend_id=None, limit=10,
    )
    assert len(rows) == 1
    assert rows[0]["text"] == "legacy turn"


def test_get_recent_room_conversation_best_friend_owner_override(db):
    """Plan v2 test 3 — owner override per P1 option (ii). Best_friend sees a
    turn whose audience_ids does NOT contain their pid."""
    room = "room_owner"
    _seed_turn(db, person_id="stranger_a", role="user", content="for stranger b only",
               room_session_id=room, audience_ids=["stranger_b"])
    rows = db.get_recent_room_conversation(
        room_session_id=room, requester_pid="jagan_001",
        best_friend_id="jagan_001", limit=10,
    )
    assert len(rows) == 1, "best_friend must override audience filter"
    # Without owner override, the same query returns 0 rows.
    rows_no_override = db.get_recent_room_conversation(
        room_session_id=room, requester_pid="jagan_001",
        best_friend_id=None, limit=10,
    )
    assert rows_no_override == []


def test_get_recent_room_conversation_room_session_id_filter(db):
    """Plan v2 test 4 — turns in different room_session_ids are scoped out."""
    _seed_turn(db, person_id="jagan_001", role="user", content="room R1",
               room_session_id="room_R1", audience_ids=["jagan_001"])
    _seed_turn(db, person_id="jagan_001", role="user", content="room R2",
               room_session_id="room_R2", audience_ids=["jagan_001"])
    rows = db.get_recent_room_conversation(
        room_session_id="room_R1", requester_pid="jagan_001",
        best_friend_id=None, limit=10,
    )
    assert len(rows) == 1
    assert rows[0]["text"] == "room R1"


def test_get_recent_room_conversation_pid_collision_rejection(db):
    """Plan v2 test 5 — quote-boundary safety against suffix collision.
    audience_ids=["jagan_0011"] must NOT match requester_pid="jagan_001"."""
    room = "room_collision"
    _seed_turn(db, person_id="jagan_0011", role="user", content="suffix collision",
               room_session_id=room, audience_ids=["jagan_0011"])
    rows = db.get_recent_room_conversation(
        room_session_id=room, requester_pid="jagan_001",
        best_friend_id=None, limit=10,
    )
    assert rows == [], (
        "suffix-collision pid must NOT match — quote boundary is part of the "
        "LIKE pattern '%\"<pid>\"%'"
    )


# ────────────────────────────────────────────────────────────────────────────
# (6) CRITICAL 1 — `_` wildcard collision rejection (Plan v2 §2)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("X", ["A", "Z", "/", "*"])
def test_get_recent_room_conversation_underscore_wildcard_rejection(db, X):
    """Plan v2 CRITICAL 1 — without ESCAPE clause, `jagan_001` LIKE pattern
    would match `jaganX001` for any single char X. ESCAPE '\\' makes `_` a
    literal underscore. Parametrize over 4 X positions; all must return 0 rows."""
    room = f"room_underscore_{X}"
    spoofed = f"jagan{X}001"
    _seed_turn(db, person_id=spoofed, role="user", content=f"wildcard X={X}",
               room_session_id=room, audience_ids=[spoofed])
    rows = db.get_recent_room_conversation(
        room_session_id=room, requester_pid="jagan_001",
        best_friend_id=None, limit=10,
    )
    assert rows == [], (
        f"CRITICAL 1: requester 'jagan_001' must NOT match audience "
        f"['{spoofed}'] (X={X!r}). ESCAPE clause is missing or broken."
    )


# ────────────────────────────────────────────────────────────────────────────
# (7) Graceful no-op on empty / None room_session_id
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("empty", [None, ""])
def test_get_recent_room_conversation_empty_room_session_id_graceful(db, empty):
    """Plan v2 test 7 — None / empty room_session_id returns []. No exception."""
    rows = db.get_recent_room_conversation(
        room_session_id=empty, requester_pid="jagan_001",
        best_friend_id=None, limit=10,
    )
    assert rows == []


# ────────────────────────────────────────────────────────────────────────────
# (8) LOW 5 — _compute_room_audience speaker-always-in-audience invariant
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "participants,person_id,expected",
    [
        # Case (a): empty participants set → speaker-only fallback.
        (set(),                          "jagan_001",
         ["jagan_001"]),
        # Case (b): speaker present in participants → sorted set.
        ({"jagan_001", "lexi_xyz"},      "jagan_001",
         ["jagan_001", "lexi_xyz"]),
        # Case (c): speaker missing from participants → union, sorted (MEDIUM 4).
        ({"lexi_xyz"},                   "jagan_001",
         ["jagan_001", "lexi_xyz"]),
    ],
)
def test_compute_room_audience_speaker_always_present(participants, person_id, expected):
    """Plan v2 test 8 (LOW 5 split — 8a). Pure helper test over 3 cases.

    Invariant: speaker is ALWAYS in the returned list. Removing case (c) would
    allow a race against _open_session to produce an audience list missing
    the speaker — D-A's audience filter would then drop the requester's own
    turn from their own retrieval (per the LIKE substring contract)."""
    import pipeline
    result = pipeline._compute_room_audience(participants, person_id)
    assert result == expected, (
        f"_compute_room_audience({participants!r}, {person_id!r}) "
        f"returned {result!r}; expected {expected!r}"
    )


# ────────────────────────────────────────────────────────────────────────────
# (9) LOW 5 — full-room-audience DB persistence
# ────────────────────────────────────────────────────────────────────────────


def test_log_turn_persists_full_room_audience_to_db(db):
    """Plan v2 test 9 (LOW 5 split — 8b). End-to-end: 3-person room →
    _compute_room_audience → log_turn → SELECT audience_ids → JSON is the
    sorted-list of all 3 pids, not [speaker_only]."""
    import pipeline

    participants = {"jagan_001", "lexi_xyz", "kara_friend"}
    audience = pipeline._compute_room_audience(participants, "jagan_001")
    assert audience == ["jagan_001", "kara_friend", "lexi_xyz"]

    db.log_turn(
        "jagan_001", "user", "hello room",
        room_session_id="room_audience_persist",
        audience_ids=audience,
    )

    row = db._conn.execute(
        "SELECT audience_ids FROM conversation_log "
        "WHERE room_session_id = 'room_audience_persist' AND role = 'user'"
    ).fetchone()
    assert row is not None
    persisted = json.loads(row[0])
    assert persisted == ["jagan_001", "kara_friend", "lexi_xyz"], (
        "Persisted audience_ids must be the FULL room (sorted), not "
        "[speaker_only]. Indicates _compute_room_audience was bypassed."
    )


# ────────────────────────────────────────────────────────────────────────────
# Latency budget — median-of-10 (Plan v2 §10, LOW 6)
# ────────────────────────────────────────────────────────────────────────────


def test_get_recent_room_conversation_latency_under_budget(db):
    """Plan v2 §10 LOW 6 — median-of-10 latency must stay under 50ms for a
    100-turn room. CI runner ceiling; production target is 10ms p99 on Jetson."""
    room = "room_latency"
    base_ts = 1779020000.0
    # Seed 100 turns mixing audience scopes so the SQL exercises the OR-chain.
    for i in range(100):
        if i % 3 == 0:
            aud = ["jagan_001"]
        elif i % 3 == 1:
            aud = ["jagan_001", "lexi_xyz"]
        else:
            aud = ["lexi_xyz"]
        _seed_turn(
            db, person_id="jagan_001" if i % 2 == 0 else "lexi_xyz",
            role="user", content=f"turn {i}",
            room_session_id=room, audience_ids=aud, ts=base_ts + i,
        )

    measurements_ms: list[float] = []
    for _ in range(10):
        t0 = time.perf_counter()
        rows = db.get_recent_room_conversation(
            room_session_id=room, requester_pid="jagan_001",
            best_friend_id="jagan_001", limit=10,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        measurements_ms.append(elapsed_ms)
        assert len(rows) == 10  # owner override returns all 10 most-recent

    median_ms = statistics.median(measurements_ms)
    assert median_ms < 50.0, (
        f"P0.S7 latency p50={median_ms:.1f}ms exceeds 50ms budget; "
        f"all measurements: {[round(m, 1) for m in measurements_ms]}"
    )
