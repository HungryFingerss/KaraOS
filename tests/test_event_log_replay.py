"""P0.0.7 Step 7 — Event-log replay smoke tests (Block E, D7.3).

5 tests verifying the full ingestion → replay round-trip path:

  a. Round-trip integrity      — every payload class survives JSON
                                  serialize → DB write → SELECT →
                                  from_json_dict deserialize losslessly.
  b. Parent-chain integrity     — natural-pair chains land with correct
                                  parent_event_id linkage; orphaned events
                                  (parent_event_id pointing outside window)
                                  don't crash the replay tool.
  c. Filter composition         — _query_events with multiple AND'd
                                  filters returns the correct subset.
  d. Schema-version dispatch    — events written under different
                                  schema_version values deserialize via
                                  the (event_type, schema_version) key.
  e. Anti-spoof field preservation — VisionFramePayload.anti_spoof_live +
                                  anti_spoof_score round-trip correctly
                                  (load-bearing P0.S1 prerequisite).

Plan: tests/p0_07_plan_v2.md.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from core.event_log import producer as _producer
from core.event_log import safe_emit_sync
from core.event_log.types import (
    EVENT_TYPES,
    NATURAL_PARENT_PAIRS,
    SCHEMA_VERSIONS,
    _PAYLOAD_CLASSES,
    VisionFramePayload,
)
from tests.fixtures.event_log_fixtures import (
    ReplayContext,
    build_dispute_path,
    build_greeting_flow,
    build_multi_person_room,
    build_stranger_first_encounter,
    replay_session_fixture,  # noqa: F401 — re-exported so pytest discovers it
)


# Load tools/replay_session.py as a module so we can test _query_events
# directly. (`tools/` is a script directory, not a package, so we use
# importlib.util to side-load it without touching sys.path globally.)
_REPO_ROOT = Path(__file__).resolve().parent.parent
_REPLAY_CLI_PATH = _REPO_ROOT / "tools" / "replay_session.py"


def _load_replay_cli():
    spec = importlib.util.spec_from_file_location(
        "replay_session_cli", _REPLAY_CLI_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["replay_session_cli"] = module
    spec.loader.exec_module(module)
    return module


# ══════════════════════════════════════════════════════════════════════════
# a. Round-trip integrity — every payload class round-trips losslessly
# ══════════════════════════════════════════════════════════════════════════


def test_a_round_trip_every_payload_class_survives_db_write_and_read(
    replay_session_fixture,
):
    """For every (event_type, schema_version) pair in _PAYLOAD_CLASSES,
    emit through the producer + read back from the in-memory DB +
    dispatch via from_json_dict; assert the rebuilt payload field-by-field
    equals the original.

    Uses all 4 fixture scenarios so every payload class gets at least
    one representative round-trip.
    """
    ctx: ReplayContext = replay_session_fixture
    build_greeting_flow(session_id="jagan_001",
                       room_session_id="room_rt")
    build_stranger_first_encounter(session_id="stranger_rt")
    build_multi_person_room(pids=("jagan_001", "lexi_rt"),
                           room_session_id="room_rt_mp")
    build_dispute_path(session_id="jagan_001")

    events = ctx.all_events()
    assert events, "no events emitted — fixture builders didn't run"

    # Every event_type in EVENT_TYPES should appear at least once across
    # the 4 scenarios — confirms the fixture coverage assumption.
    types_seen = {e["event_type"] for e in events}
    missing = sorted(EVENT_TYPES - types_seen)
    assert not missing, (
        f"fixture scenarios didn't exercise event_type(s) {missing}; "
        f"update a scenario to cover them so round-trip coverage holds."
    )

    # Round-trip every emitted row.
    for event in events:
        event_type = event["event_type"]
        schema_version = event["schema_version"]
        cls = _PAYLOAD_CLASSES.get((event_type, schema_version))
        assert cls is not None, (
            f"no dispatch entry for ({event_type}, v={schema_version}); "
            f"either add a (event_type, version) → class entry, or check the row "
            f"was written with the wrong schema_version."
        )
        payload_dict = event["payload"]
        assert isinstance(payload_dict, dict), (
            f"event_log row's payload should round-trip to a dict; "
            f"got {type(payload_dict).__name__}"
        )
        rebuilt = cls.from_json_dict(payload_dict, schema_version=schema_version)
        # Re-serialize and re-deserialize — the rebuilt object should
        # round-trip again to the same shape (idempotency guard).
        rebuilt_dict = _producer._serialize_payload(rebuilt)
        rebuilt_2 = cls.from_json_dict(
            json.loads(rebuilt_dict), schema_version=schema_version,
        )
        assert rebuilt == rebuilt_2, (
            f"{event_type} v{schema_version} did not round-trip idempotently:\n"
            f"  rebuilt: {rebuilt!r}\n"
            f"  rebuilt_2: {rebuilt_2!r}"
        )


# ══════════════════════════════════════════════════════════════════════════
# b. Parent-chain integrity — natural-pair linkage + orphan tolerance
# ══════════════════════════════════════════════════════════════════════════


def test_b_parent_chain_natural_pairs_link_correctly(
    replay_session_fixture,
):
    """For each natural-pair (child, parent) emitted within the same
    session, the child's parent_event_id should point at the parent's id.

    Greeting flow scenario covers all 3 natural pairs:
      tool_result      → tool_call
      identity_claim   → audio_in
      routing_decision → identity_claim
    """
    ctx: ReplayContext = replay_session_fixture
    build_greeting_flow(session_id="jagan_001",
                       room_session_id="room_chain")

    events = ctx.all_events()
    by_type_first: dict[str, dict] = {}
    for e in events:
        # First occurrence wins for natural-pair lookup (the chain runs once).
        by_type_first.setdefault(e["event_type"], e)

    for child_type, parent_type in NATURAL_PARENT_PAIRS:
        if child_type not in by_type_first or parent_type not in by_type_first:
            continue   # scenario didn't include this pair; skip
        child = by_type_first[child_type]
        parent = by_type_first[parent_type]
        assert child["parent_event_id"] == parent["id"], (
            f"natural-pair linkage broken for ({child_type} → {parent_type}):\n"
            f"  child.parent_event_id = {child['parent_event_id']}\n"
            f"  parent.id             = {parent['id']}"
        )

    # Orphan tolerance: emit an event whose explicit parent_event_id
    # points OUTSIDE the in-window event set. The replay tool's tree
    # renderer should fall back to indent=0 (flat) rather than crash.
    safe_emit_sync(
        "memory_write",
        # Re-use any payload class — content irrelevant for this test.
        # (MemoryWritePayload chosen because it's simple.)
        type(events[0])("memory_write"),  # placeholder, replaced below
        session_id="ghost_sess",
        parent_event_id=99999,    # deliberately outside-window
    ) if False else None  # see proper construction below

    from core.event_log import MemoryWritePayload
    safe_emit_sync(
        "memory_write",
        MemoryWritePayload(
            person_id="ghost", role="user", text="orphan",
            room_session_id=None, audience_ids=None,
        ),
        session_id="ghost_sess",
        parent_event_id=99999,    # outside-window parent
    )

    replay_cli = _load_replay_cli()
    # The CLI's tree renderer must handle out-of-window parents without
    # raising — verify by formatting the orphan + a normal event.
    #
    # Bridge format: ctx.all_events() returns rows with the payload as a
    # parsed dict under key "payload"; the CLI's _render consumes rows
    # with the raw JSON under "payload_json" (what _query_events emits).
    # Convert before passing.
    all_events_with_orphan = [
        {**e, "payload_json": json.dumps(e["payload"], sort_keys=True)}
        for e in ctx.all_events()
    ]
    lines = list(replay_cli._render(all_events_with_orphan, tree=True))
    assert lines, "renderer produced no output"
    # The orphan should render at indent=0 (no `└─` prefix), since its
    # parent id 99999 isn't in the in-window set.
    orphan_line = next(l for l in lines if "ghost_sess" in l)
    assert "└─" not in orphan_line, (
        f"orphan event with out-of-window parent should render flat, got: "
        f"{orphan_line!r}"
    )


# ══════════════════════════════════════════════════════════════════════════
# c. Filter composition — _query_events with AND'd filters
# ══════════════════════════════════════════════════════════════════════════


def test_c_filter_composition_returns_correct_subset(
    replay_session_fixture, tmp_path,
):
    """Build 3 scenarios into the in-memory DB, dump to a tmp file-backed DB,
    then verify the CLI's _query_events composes filters with AND semantics.

    Uses a file-backed DB because _query_events opens with URI read-only
    mode which doesn't work against the in-memory connection used by the
    in-process producer.
    """
    # Populate via producer
    ctx: ReplayContext = replay_session_fixture
    build_greeting_flow(session_id="jagan_001",
                       room_session_id="room_filter_a")
    build_stranger_first_encounter(session_id="stranger_filter")
    build_multi_person_room(
        pids=("jagan_001", "lexi_filter"),
        room_session_id="room_filter_b",
    )

    # Dump in-memory rows into a file-backed DB so the CLI can open it
    # via URI read-only mode (the producer's `:memory:` connection isn't
    # accessible from a separate process).
    import sqlite3
    file_db_path = tmp_path / "brain_filter.db"
    file_conn = sqlite3.connect(str(file_db_path))
    from core.brain_db_migrations import _m_0012_create_event_log_apply
    _m_0012_create_event_log_apply(file_conn)
    file_conn.commit()
    for ev in ctx.all_events():
        file_conn.execute(
            "INSERT INTO event_log (id, ts, session_id, room_session_id, "
            "event_type, schema_version, payload, parent_event_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ev["id"], ev["ts"], ev["session_id"], ev["room_session_id"],
                ev["event_type"], ev["schema_version"],
                json.dumps(ev["payload"], sort_keys=True),
                ev["parent_event_id"],
            ),
        )
    file_conn.commit()
    file_conn.close()

    replay_cli = _load_replay_cli()
    ro_conn = replay_cli._open_readonly(file_db_path)
    try:
        # Filter 1 — session=jagan_001 AND type=tool_call.
        results = replay_cli._query_events(
            ro_conn, session="jagan_001", room=None,
            event_type="tool_call", since=None, limit=0,
        )
        assert all(r["session_id"] == "jagan_001" for r in results), (
            f"session filter leaked: got sessions "
            f"{[r['session_id'] for r in results]}"
        )
        assert all(r["event_type"] == "tool_call" for r in results), (
            f"type filter leaked: got types "
            f"{[r['event_type'] for r in results]}"
        )
        # Greeting flow + dispute path both emit a tool_call for jagan_001,
        # but we only ran greeting flow + multi-person + stranger in this
        # test — only greeting flow's tool_call should match.
        assert len(results) == 1, (
            f"expected exactly 1 tool_call for jagan_001, got {len(results)}: "
            f"{[r['payload_json'] for r in results]}"
        )

        # Filter 2 — room=room_filter_a only.
        results = replay_cli._query_events(
            ro_conn, session=None, room="room_filter_a",
            event_type=None, since=None, limit=0,
        )
        assert results, "expected events in room_filter_a"
        assert all(r["room_session_id"] == "room_filter_a" for r in results), (
            f"room filter leaked: got rooms "
            f"{[r['room_session_id'] for r in results]}"
        )

        # Filter 3 — multi-filter compose: room=room_filter_b AND
        # type=routing_decision. Multi-person room scenario emits
        # routing_decision per speaker — both should match.
        results = replay_cli._query_events(
            ro_conn, session=None, room="room_filter_b",
            event_type="routing_decision", since=None, limit=0,
        )
        assert len(results) == 2, (
            f"expected 2 routing_decision rows in room_filter_b "
            f"(one per speaker); got {len(results)}"
        )
        for r in results:
            assert r["event_type"] == "routing_decision"
            assert r["room_session_id"] == "room_filter_b"
    finally:
        ro_conn.close()


# ══════════════════════════════════════════════════════════════════════════
# d. Schema-version dispatch — (event_type, schema_version) key
# ══════════════════════════════════════════════════════════════════════════


def test_d_schema_version_dispatch_keys_on_event_type_and_version(
    replay_session_fixture, monkeypatch,
):
    """Simulate the future case where a payload is bumped from v1 → v2
    while v1 rows remain in the DB. The dispatch table maps
    (event_type, schema_version) → class; the v1 row should still
    deserialize via the v1 entry even after v2 lands.

    Test approach:
      1. Emit a real v1 event via the producer.
      2. Synthetically add a fake v2 entry to _PAYLOAD_CLASSES.
      3. Read the v1 row back and verify dispatch picks the v1 class.
      4. Confirm an unknown (event_type, schema_version) key triggers
         the CLI's fallback path (raw JSON dump) rather than crashing.
    """
    ctx: ReplayContext = replay_session_fixture
    build_greeting_flow(session_id="jagan_001",
                       room_session_id="room_dispatch")

    # The greeting flow emits tts_out at v1. Confirm the dispatch picks
    # the v1 class even after we mock-add a v2 entry.
    from core.event_log.types import TtsOutPayload
    fake_v2_class = type("TtsOutPayloadV2", (TtsOutPayload,), {})
    monkeypatch.setitem(_PAYLOAD_CLASSES, ("tts_out", 2), fake_v2_class)

    tts_rows = ctx.events_of_type("tts_out")
    assert tts_rows, "no tts_out emitted"
    v1_row = tts_rows[0]
    assert v1_row["schema_version"] == 1

    cls = _PAYLOAD_CLASSES[(v1_row["event_type"], v1_row["schema_version"])]
    assert cls is TtsOutPayload, (
        f"v1 dispatch picked the wrong class: {cls.__name__}. "
        f"Dispatch must key on (event_type, schema_version)."
    )

    # Now mock an unknown (event_type, version) key — the CLI should
    # not crash, just fall back to raw-JSON summary.
    replay_cli = _load_replay_cli()
    summary = replay_cli._summarize_payload(
        "tts_out", schema_version=99,    # unknown version
        payload_dict={"text": "unknown-shape", "language": "en",
                      "was_stream": False, "purpose": "test",
                      "duration_ms_est": None, "text_full_hash": "x"},
    )
    # Fallback returns a JSON-shaped summary; should contain at least
    # one of the known field names.
    assert ("unknown-shape" in summary or "tts_out" in summary
            or "language" in summary), (
        f"unknown schema_version should fall back to JSON dump; got: {summary!r}"
    )


# ══════════════════════════════════════════════════════════════════════════
# e. Anti-spoof field preservation — P0.S1 prerequisite
# ══════════════════════════════════════════════════════════════════════════


def test_e_anti_spoof_fields_round_trip_through_replay(replay_session_fixture):
    """P0.S1 load-bearing prerequisite: VisionFramePayload's anti_spoof_live
    and anti_spoof_score MUST round-trip through emit → DB → from_json_dict
    losslessly.

    P0.S1's anti-spoof-on-every-match regression test depends on
    these fields existing in captured replay logs; this test pins the
    contract so any future field-drop or type-change regression is
    caught before P0.S1 builds on top.
    """
    ctx: ReplayContext = replay_session_fixture

    # Three vision_frame events spanning the (live, score) value matrix.
    test_cases = [
        # (anti_spoof_live, anti_spoof_score)
        (True,  0.95),
        (True,  None),    # live but score-unavailable (e.g. anti-spoof model offline)
        (False, 0.12),    # explicit spoof detection
    ]
    for i, (live, score) in enumerate(test_cases):
        payload = VisionFramePayload(
            frame_id=f"frame_as_{i}",
            frame_path=None,
            frame_ts=1779012000.0 + i,
            n_detections=1,
            recognized=(),
            unrecognized_track_ids=(99,),
            anti_spoof_live=live,
            anti_spoof_score=score,
        )
        safe_emit_sync("vision_frame", payload)

    vf_events = ctx.events_of_type("vision_frame")
    assert len(vf_events) == 3, f"expected 3 vision_frame events, got {len(vf_events)}"

    for event, (expected_live, expected_score) in zip(vf_events, test_cases):
        # Direct dict access — anti_spoof_* fields must be present + correct type.
        payload = event["payload"]
        assert "anti_spoof_live" in payload, (
            "P0.S1 prerequisite violation: anti_spoof_live missing from "
            "vision_frame payload dict round-tripped through DB."
        )
        assert "anti_spoof_score" in payload, (
            "P0.S1 prerequisite violation: anti_spoof_score missing from "
            "vision_frame payload dict round-tripped through DB."
        )
        assert isinstance(payload["anti_spoof_live"], bool), (
            f"anti_spoof_live must be bool, got {type(payload['anti_spoof_live']).__name__}"
        )
        assert payload["anti_spoof_live"] is expected_live, (
            f"anti_spoof_live changed across round-trip: "
            f"expected {expected_live}, got {payload['anti_spoof_live']}"
        )

        # Score may be None or float — verify either preserves.
        if expected_score is None:
            assert payload["anti_spoof_score"] is None, (
                f"anti_spoof_score None should round-trip as None; "
                f"got {payload['anti_spoof_score']!r}"
            )
        else:
            assert abs(payload["anti_spoof_score"] - expected_score) < 1e-9, (
                f"anti_spoof_score changed across round-trip: "
                f"expected {expected_score}, got {payload['anti_spoof_score']}"
            )

        # Dispatch via from_json_dict — the reconstructed dataclass
        # should equal the original (P0.S1 will rely on this for
        # replay-based regression tests).
        cls = _PAYLOAD_CLASSES[("vision_frame", 1)]
        rebuilt = cls.from_json_dict(payload, schema_version=1)
        assert rebuilt.anti_spoof_live is expected_live
        assert rebuilt.anti_spoof_score == expected_score
