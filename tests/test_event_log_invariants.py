"""P0.0.7 event_log structural invariants (Block E).

13 tests per Plan v2 R5 breakdown + 3 C-clarifications (C1 / C2 / C3):

  1. test_each_event_type_has_at_most_one_producer_location (D7)
  2. test_vision_frame_payload_includes_anti_spoof_fields (P0.S1 load-bearing)
  3. test_vision_frame_payload_does_not_embed_image_data (D2)
  4. test_parent_event_id_docstring_documents_immediate_upstream (D4)
  5. test_drop_counter_exposed_via_health_log_not_self_emit (D5)
  6. test_event_log_disabled_emit_is_noop (D8 plumbing)
  7. test_event_log_testing_mode_uses_in_memory_sqlite (D8)
  8. test_every_payload_round_trips_through_event_log_default (R2)
  9. test_recent_parent_cache_cleared_on_session_close (R1)
 10. test_migration_0012_creates_event_log_table (R3)
 11. test_recent_parent_only_mutated_by_writer_task (C1)
 12. test_every_payload_has_lossless_from_json_dict (C2)
 13. test_every_event_type_has_dispatch_entry_for_current_version (C3)

Plan: tests/p0_07_plan_v2.md.
"""
from __future__ import annotations

import ast
import asyncio
import dataclasses
import inspect
import json
import os
import re
import sqlite3
from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest

from core.event_log import producer as _producer
from core.event_log import types as _types
from core.event_log.types import (
    EVENT_TYPES,
    NATURAL_PARENT_PAIRS,
    SCHEMA_VERSIONS,
    _PAYLOAD_CLASSES,
    AudioInPayload,
    IdentityClaimPayload,
    IntentClassificationPayload,
    MemoryWritePayload,
    PresenceStatePayload,
    RoutingDecisionPayload,
    SessionLifecyclePayload,
    StateWritePayload,
    ToolCallPayload,
    ToolResultPayload,
    TtsOutPayload,
    VisionFramePayload,
)
from core.reconciler_state import RoutingDecision
from core.vision_channel import PresenceState
from core.voice_channel import IdentityClaim


_REPO_ROOT = Path(__file__).resolve().parent.parent
_PRODUCER_PY = _REPO_ROOT / "core" / "event_log" / "producer.py"
_TYPES_PY = _REPO_ROOT / "core" / "event_log" / "types.py"


# ──────────────────────────────────────────────────────────────────────────
# Sample payload fixtures — one of every type for round-trip + dispatch tests
# ──────────────────────────────────────────────────────────────────────────


def _sample_identity_claim() -> IdentityClaim:
    return IdentityClaim(
        pid="jagan_001", confidence=0.85, n_diarize_segments=1,
        utterance_duration=1.5, reasoning="sample",
        raw_segment_scores=(("jagan_001", 0.85), (None, -0.1)),
    )


def _sample_presence_state() -> PresenceState:
    return PresenceState(
        visible_pids=("jagan_001",),
        unrecognized_track_ids=(42,),
        per_pid_confidence={"jagan_001": 0.9},
        per_pid_quality={"jagan_001": 0.7},
        frame_ts=1779008461.0,
        reasoning="sample",
    )


def _sample_routing_decision() -> RoutingDecision:
    return RoutingDecision(
        pid="jagan_001", action="current",
        reasoning="sample", rule_fired="_p3_self_match_with_face",
    )


def _sample_payloads() -> dict[str, object]:
    """One sample payload per event_type. Drives round-trip tests."""
    return {
        "audio_in": AudioInPayload(
            audio_hash="sha256:abcd", speech_secs=1.2, stt_text="hello",
            language="en", pre_roll_ms=200,
        ),
        "vision_frame": VisionFramePayload(
            frame_id="frame_0001", frame_path="faces/frames/frame_0001.jpg",
            frame_ts=1779008461.0, n_detections=1,
            recognized=(("jagan_001", 0.95, 0.85),),
            unrecognized_track_ids=(42, 43),
            anti_spoof_live=True, anti_spoof_score=0.92,
        ),
        "identity_claim": IdentityClaimPayload(claim=_sample_identity_claim()),
        "presence_state": PresenceStatePayload(presence=_sample_presence_state()),
        "routing_decision": RoutingDecisionPayload(
            decision=_sample_routing_decision(), utt_band="normal",
        ),
        "intent_classification": IntentClassificationPayload(
            sidecar={"turn_intent": "casual_conversation", "confidence": 0.88},
            mode="primary", text="hello there", from_cache=False,
        ),
        "tool_call": ToolCallPayload(
            name="search_memory", args={"query": "test"},
            person_id="jagan_001", intent_sidecar=None,
        ),
        "tool_result": ToolResultPayload(
            status="handled", response_text="ok", error=None,
        ),
        "memory_write": MemoryWritePayload(
            person_id="jagan_001", role="user", text="hello",
            room_session_id="room_xyz", audience_ids=("jagan_001",),
        ),
        "state_write": StateWritePayload(
            mode="watching", current_person="Jagan",
            current_person_id="jagan_001", visible_people=("Jagan",),
            message="",
        ),
        "tts_out": TtsOutPayload(
            text="Hello!", text_full_hash="sha256:efgh",
            language="en", was_stream=True, purpose="greeting",
            duration_ms_est=900,
        ),
        "session_lifecycle": SessionLifecyclePayload(
            lifecycle="open", person_id="jagan_001",
            person_name="Jagan", source="face", person_type="best_friend",
            room_session_id="room_xyz",
        ),
    }


# ══════════════════════════════════════════════════════════════════════════
# 1. D7 — N=1 producer-per-event_type (upper bound only at Step 2)
# ══════════════════════════════════════════════════════════════════════════
#
# At Step 2 closure (this state) hooks haven't landed yet — producer-side
# emits exist only in tests, not core/* or pipeline.py. The lower bound
# "every event_type has at least 1 producer" lands as a separate
# invariant when Step 5 (hooks H1-H11) closes.


_EMIT_CALL_NAMES = frozenset({"emit", "emit_sync", "safe_emit_sync"})


def _emit_callsite_event_types(src: str) -> list[str]:
    """AST-scan a source file for `emit("type", ...)`, `emit_sync("type", ...)`,
    `producer.emit(...)`, or `producer.emit_sync(...)` calls; return the
    event_type literals.

    Detects all four call shapes:
      - `from core.event_log import emit; emit("x", ...)`
      - `from core.event_log import emit_sync; emit_sync("x", ...)`
      - `from core.event_log import producer; producer.emit("x", ...)`
      - `from core.event_log import producer; producer.emit_sync("x", ...)`
    """
    types: list[str] = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return types
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_emit = (
            (isinstance(func, ast.Name) and func.id in _EMIT_CALL_NAMES)
            or (isinstance(func, ast.Attribute) and func.attr in _EMIT_CALL_NAMES)
        )
        if not is_emit:
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            types.append(first.value)
    return types


def test_each_event_type_has_exactly_one_producer_location():
    """D7 N=1 invariant — every event_type in EVENT_TYPES has exactly
    ONE producer location (boundary-wrap or sidecar) in pipeline.py +
    core/* (excluding core/event_log/ which owns the producer surface
    and is allowed to reference event_types in test/sample code).

    Catches BOTH failure modes in one assertion:
      - Upper bound (count > 1): dual-producer regression where two
        call sites accidentally emit the same event_type.
      - Lower bound (count < 1): coverage gap where an event_type is
        registered in EVENT_TYPES but no producer hook exists.

    Plan v2 R5 spec — same shape as P0.10's N=1 `_routing_action`
    source invariant. Was split into upper-bound-only at Step 2 closure
    (when hooks hadn't landed); Step 5 closure flips to exactly-one once
    H1-H11 wire all 12 producers.
    """
    # Files to scan: pipeline.py + everything in core/ EXCEPT core/event_log/.
    scan_targets: list[Path] = [_REPO_ROOT / "pipeline.py"]
    for p in (_REPO_ROOT / "core").rglob("*.py"):
        if "event_log" in p.parts:
            continue
        scan_targets.append(p)

    counts: dict[str, int] = {t: 0 for t in EVENT_TYPES}
    locations: dict[str, list[str]] = {t: [] for t in EVENT_TYPES}
    for path in scan_targets:
        try:
            src = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for event_type in _emit_callsite_event_types(src):
            if event_type in counts:
                counts[event_type] += 1
                locations[event_type].append(str(path.relative_to(_REPO_ROOT)))

    over_one = {t: locs for t, locs in locations.items() if len(locs) > 1}
    assert not over_one, (
        f"D7 N=1 violation (upper bound): event_type(s) emitted from "
        f"multiple producer locations: {over_one}. Each event_type must "
        f"have exactly one producer hook — consolidate to a single "
        f"boundary or sidecar (or extract a shared helper, the helper's "
        f"single emit_sync call satisfies N=1)."
    )

    missing = sorted(t for t, c in counts.items() if c == 0)
    assert not missing, (
        f"D7 N=1 violation (lower bound): event_type(s) registered in "
        f"EVENT_TYPES but have NO producer location: {missing}. Wire a "
        f"hook (boundary-wrap or sidecar) for each missing type."
    )


# ══════════════════════════════════════════════════════════════════════════
# 2-3. Vision-frame load-bearing fields + no inline image data (P0.S1 + D2)
# ══════════════════════════════════════════════════════════════════════════


def test_vision_frame_payload_includes_anti_spoof_fields():
    """P0.S1 prerequisite (locked by P0.0.7 Plan v2): VisionFramePayload
    MUST include anti_spoof_live + anti_spoof_score from day 1.

    P0.S1's anti-spoof-on-every-match regression test depends on these
    fields existing in replay logs. Removing/renaming/making-optional
    breaks the test surface.
    """
    field_names = {f.name for f in fields(VisionFramePayload)}
    assert "anti_spoof_live" in field_names, (
        "P0.S1 prerequisite violated: VisionFramePayload missing "
        "`anti_spoof_live` field. This is LOAD-BEARING per Plan v2 Block A."
    )
    assert "anti_spoof_score" in field_names, (
        "P0.S1 prerequisite violated: VisionFramePayload missing "
        "`anti_spoof_score` field. This is LOAD-BEARING per Plan v2 Block A."
    )
    # Type sanity — P0.S1 Phase 2 widened anti_spoof_live to Optional[bool]
    # to surface the ANTI_SPOOF_REASON_UNAVAILABLE case (3-state semantic):
    #   True  → at least one detection passed
    #   False → at least one detection rejected (active spoof signal)
    #   None  → all detections produced no verdict (checker unavailable)
    # Consumers MUST handle None (replay distinguishes hardware-down from
    # active attack). The P0.0.7 2-state contract was widened deliberately;
    # this is the new locked schema per P0.S1 closure.
    type_hints = {f.name: f.type for f in fields(VisionFramePayload)}
    live_type_str = str(type_hints["anti_spoof_live"])
    assert "Optional" in live_type_str or "None" in live_type_str, (
        f"P0.S1 Phase 2: anti_spoof_live MUST be Optional[bool] to support "
        f"the ANTI_SPOOF_REASON_UNAVAILABLE case (None). Found {live_type_str}. "
        f"Reverting to bare bool drops the unavailable-checker signal."
    )


def test_vision_frame_payload_does_not_embed_image_data():
    """D2 lock — VisionFramePayload MUST NOT embed inline image bytes.

    Pixel data lives at faces/frames/<frame_id>.jpg referenced via
    `frame_path`. The payload never carries the bytes — log volume
    would explode (MB per frame × ~1Hz × hours = unmanageable).
    """
    forbidden_field_substrings = (
        "image_bytes", "jpeg_data", "base64_image", "frame_bytes",
        "pixel_data", "raw_frame",
    )
    field_names = {f.name for f in fields(VisionFramePayload)}
    forbidden_present = [
        f for f in field_names
        if any(sub in f for sub in forbidden_field_substrings)
    ]
    assert not forbidden_present, (
        f"D2 violation: VisionFramePayload has fields suggesting inline "
        f"image data: {forbidden_present}. Use frame_path reference; "
        f"bytes live in faces/frames/<frame_id>.jpg keyed by hash."
    )


# ══════════════════════════════════════════════════════════════════════════
# 3b. P0.S6 D3.c — no secret-shaped field names on any event_log payload
# ══════════════════════════════════════════════════════════════════════════
# Colocated here per Plan v2 §9.3 / D7 (P0.S6 invariant placement decision).
# `_FORBIDDEN_FIELD_PATTERN` differs from the secret-in-prints regex in §2 by
# NOT requiring leading underscore — payload fields use snake_case without
# the `_API_KEY` convention. `auth_token` matches; `auth_flow_step` would also
# match (acceptable conservative false positive — payload field naming should
# avoid `auth` substring anyway).

_FORBIDDEN_FIELD_PATTERN = re.compile(
    r"(?i).*(api_key|token|secret|password|auth|credential).*"
)

# Payload-classes registry — every `@dataclass` defined in core/event_log/types.py
# that's listed in _PAYLOAD_CLASSES is in-scope. We use _PAYLOAD_CLASSES as the
# enumeration source so the test never drifts from the dispatch table.
_PAYLOAD_CLASS_NAMES_FOR_SECRET_FIELD_SCAN = {
    cls.__name__: cls
    for (_etype, _ver), cls in _PAYLOAD_CLASSES.items()
}


def test_payload_fields_no_secret_shaped_names():
    """P0.S6 D3.c — no event_log payload dataclass may declare a field whose
    name matches the secret-shape regex. Prevents accidental introduction of
    `api_key`, `auth_token`, etc. into the persisted event log via a future
    refactor that adds a "convenient" auth field to a payload.

    Scoped via `_PAYLOAD_CLASSES` — every registered payload class is checked.
    The dispatch table is the single source of truth for what counts as a
    payload (R3 + C3); this test piggybacks on that registry.
    """
    violations: list[str] = []
    for cls_name, cls in _PAYLOAD_CLASS_NAMES_FOR_SECRET_FIELD_SCAN.items():
        for f in fields(cls):
            if _FORBIDDEN_FIELD_PATTERN.match(f.name):
                violations.append(
                    f"{cls_name}.{f.name} — field name matches secret-shape "
                    f"regex; payload fields must not name credentials"
                )
    assert violations == [], (
        "P0.S6 D3.c violations (rename the field or pick a non-secret-shaped "
        "name; payloads persist to brain.db.event_log and must not log "
        "credentials):\n"
        + "\n".join(violations)
    )


# ══════════════════════════════════════════════════════════════════════════
# 4. D4 — parent_event_id docstring documents "immediate upstream"
# ══════════════════════════════════════════════════════════════════════════


def test_parent_event_id_docstring_documents_immediate_upstream():
    """D4 lock — `EventEnvelope.parent_event_id` docstring must explicitly
    state that it's the IMMEDIATE upstream event, NOT a full causal
    ancestor. Replay reconstruction queries all events within session_id;
    walking parent_event_id recursively would miss most events.
    """
    src = _TYPES_PY.read_text(encoding="utf-8")
    # The docstring lives in EventEnvelope's class body.
    # Look for the literal phrasing from the audit's locked spec.
    assert "IMMEDIATE UPSTREAM" in src or "IMMEDIATE upstream" in src, (
        "D4 docstring missing: `EventEnvelope.parent_event_id` must "
        "explicitly call out 'IMMEDIATE upstream' so a future maintainer "
        "doesn't treat parent_event_id as a full causal chain. See "
        "Plan v2 Block A."
    )
    assert "NOT a full causal ancestor" in src or "NOT a full causal" in src, (
        "D4 docstring missing: should explicitly say 'NOT a full causal "
        "ancestor' to prevent recursive-walk misuse."
    )


# ══════════════════════════════════════════════════════════════════════════
# 5. D5 — drop counter via health-log, not self-emit
# ══════════════════════════════════════════════════════════════════════════


def test_drop_counter_exposed_via_health_log_not_self_emit():
    """D5 lock — `get_drop_count()` exposes the counter; producer NEVER
    emits an `event_log_dropped` event (circular-dependency guard:
    the drop event itself can be dropped).
    """
    # Public API check.
    assert hasattr(_producer, "get_drop_count"), (
        "D5: producer must expose get_drop_count() for health-log integration."
    )
    assert callable(_producer.get_drop_count), (
        "D5: get_drop_count must be callable."
    )
    # No event_log_dropped self-emit in the producer source.
    src = _PRODUCER_PY.read_text(encoding="utf-8")
    assert 'emit("event_log_dropped"' not in src, (
        "D5 circular-dependency violation: producer.py emits an "
        "`event_log_dropped` event. The drop event itself can be dropped "
        "under backpressure — expose via get_drop_count() + health-log "
        "instead (per Plan v2 Block B)."
    )
    assert "'event_log_dropped'" not in src, (
        "D5 (alt quote form): same regression with single quotes."
    )


# ══════════════════════════════════════════════════════════════════════════
# 6-7. D8 — test-mode plumbing
# ══════════════════════════════════════════════════════════════════════════


def test_event_log_disabled_emit_is_noop(monkeypatch):
    """D8 plumbing — when EVENT_LOG_ENABLED=0 AND EVENT_LOG_TESTING=0,
    emit() returns None synchronously and never writes anything."""
    monkeypatch.setattr(_producer, "EVENT_LOG_ENABLED", False)
    monkeypatch.setattr(_producer, "EVENT_LOG_TESTING", False)

    async def _run():
        return await _producer.emit(
            "audio_in",
            _sample_payloads()["audio_in"],
            session_id="test",
        )

    result = asyncio.run(_run())
    assert result is None


def test_event_log_testing_mode_uses_in_memory_sqlite(monkeypatch):
    """D8 — EVENT_LOG_TESTING=1 routes to :memory: SQLite (no disk I/O)."""
    monkeypatch.setattr(_producer, "EVENT_LOG_ENABLED", False)
    monkeypatch.setattr(_producer, "EVENT_LOG_TESTING", True)
    _producer._reset_for_tests()
    _producer._open_testing_db_sync()
    try:
        # Verify the DB connection points at in-memory storage by checking
        # the database_list pragma — disk DBs report a file path; :memory:
        # reports "" or "main".
        conn = _producer._conn
        assert conn is not None
        rows = conn.execute("PRAGMA database_list").fetchall()
        # First entry's seq=0, name='main', file= should be "" or ":memory:".
        main_row = next(r for r in rows if r[1] == "main")
        file_path = main_row[2]
        assert file_path in ("", ":memory:"), (
            f"D8: test mode DB file is {file_path!r}; expected in-memory."
        )
    finally:
        _producer._reset_for_tests()


# ══════════════════════════════════════════════════════════════════════════
# 8. R2 — every payload round-trips through _event_log_default
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("event_type", sorted(_PAYLOAD_CLASSES.keys()))
def test_every_payload_serialize_round_trips_through_event_log_default(event_type):
    """R2 — every payload class serializes losslessly via
    json.dumps(asdict, default=_event_log_default) and the resulting JSON
    parses back to a dict whose shape matches dataclasses.asdict.

    Catches drift between dataclass field types and the encoder's handler
    set (e.g., a future field uses datetime, which has no handler).
    """
    payload = _sample_payloads()[event_type[0]]
    # Encode
    blob = _producer._serialize_payload(payload)
    assert isinstance(blob, bytes)
    # Decode JSON → dict
    decoded = json.loads(blob)
    assert isinstance(decoded, dict)
    # asdict produces the canonical reference form; the encoder + decoder
    # must round-trip to the same key set (values may have type drift —
    # tuples become lists; that's covered by R2 + C2 together — see #12).
    canonical = dataclasses.asdict(payload)
    assert set(decoded.keys()) == set(canonical.keys()), (
        f"{event_type}: round-trip key set drifted. "
        f"Original asdict keys: {sorted(canonical.keys())}; "
        f"Decoded keys: {sorted(decoded.keys())}."
    )


# ══════════════════════════════════════════════════════════════════════════
# 9. R1 — _recent_parent cache cleared on session_lifecycle=close
# ══════════════════════════════════════════════════════════════════════════


def test_recent_parent_cache_cleared_on_session_lifecycle_close(monkeypatch):
    """R1 — when a session_lifecycle event with lifecycle='close' is
    flushed, the per-session entry in `_recent_parent` is removed."""
    monkeypatch.setattr(_producer, "EVENT_LOG_TESTING", True)
    _producer._reset_for_tests()
    _producer._open_testing_db_sync()
    try:
        sid = "test_session_close"
        # Seed cache directly (writer-task scope; legal in test).
        _producer._record_parent(sid, "audio_in", 99)
        assert sid in _producer._recent_parent
        # Emit a close event — writer-task should clear the cache.
        close_payload = SessionLifecyclePayload(
            lifecycle="close", person_id=sid, person_name=None,
            source="face", person_type="best_friend",
            room_session_id=None,
        )

        async def _run():
            return await _producer.emit(
                "session_lifecycle", close_payload, session_id=sid,
            )

        asyncio.run(_run())
        assert sid not in _producer._recent_parent, (
            f"R1: _recent_parent[{sid!r}] should be cleared after "
            f"session_lifecycle=close; still present."
        )
    finally:
        _producer._reset_for_tests()


# ══════════════════════════════════════════════════════════════════════════
# 10. R3 — migration 0012 creates event_log table + 3 indexes
# ══════════════════════════════════════════════════════════════════════════


def test_migration_0012_creates_event_log_table():
    """R3 — `_m_0012_create_event_log_*` 5-tuple shape verified end-to-end.

    Applies to a fresh in-memory DB; asserts table + 3 indexes exist
    with the documented column shape; asserts verify_post + verify_present
    behave per P0.9 contract.
    """
    from core.brain_db_migrations import (
        _m_0012_create_event_log_apply,
        _m_0012_create_event_log_verify_post,
        _m_0012_create_event_log_verify_present,
        MIGRATIONS,
    )

    # Sanity — registered in MIGRATIONS at version 12 with the expected name.
    versions = [m[0] for m in MIGRATIONS]
    assert 12 in versions, "Migration v=12 not registered in MIGRATIONS."

    conn = sqlite3.connect(":memory:")
    try:
        # verify_present on fresh DB → False (table doesn't exist yet).
        assert _m_0012_create_event_log_verify_present(conn) is False, (
            "verify_present on fresh DB should return False."
        )
        # Apply
        _m_0012_create_event_log_apply(conn)
        # verify_post must succeed
        _m_0012_create_event_log_verify_post(conn)
        # verify_present now True
        assert _m_0012_create_event_log_verify_present(conn) is True, (
            "verify_present after apply should return True."
        )
        # Idempotent re-apply must not raise (IF NOT EXISTS guards)
        _m_0012_create_event_log_apply(conn)
        _m_0012_create_event_log_verify_post(conn)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════
# 11. C1 — _recent_parent only mutated by writer-task functions
# ══════════════════════════════════════════════════════════════════════════


def test_recent_parent_only_mutated_by_writer_task():
    """C1 lock — `_recent_parent` is mutated ONLY by writer-task scope
    functions (`_flush_one`, `_record_parent`, `_clear_session_parents`).

    Producer's `emit()` and any public API MUST NOT touch `_recent_parent`.
    AST-scans producer.py for assignment / subscript-assign / del /
    pop / setdefault / clear operations on the name `_recent_parent` and
    asserts each appears only inside an allowlisted function.

    Catches the race-prone pattern where emit() (running on the producer's
    asyncio event loop) tries to mutate the cache concurrently with the
    writer task — the SQLite single-writer ordering guarantee depends on
    cache mutations happening exclusively inside the writer task.
    """
    src = _PRODUCER_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)

    # Functions allowed to mutate _recent_parent — all writer-task-scope.
    ALLOWED_MUTATORS = frozenset({
        "_flush_one",                # consumes from queue; cursor.lastrowid
        "_record_parent",            # called only by _flush_one
        "_clear_session_parents",    # called only by _flush_one
        "stop_writer",               # final reset on shutdown
        "_reset_for_tests",          # test-only helper
    })

    # Walk every function definition; for each, find any reference to
    # _recent_parent that's part of a mutation expression.
    violations: list[tuple[str, int]] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            # Subscript assign: _recent_parent[...] = ...
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if (isinstance(tgt, ast.Subscript)
                            and isinstance(tgt.value, ast.Name)
                            and tgt.value.id == "_recent_parent"):
                        if fn.name not in ALLOWED_MUTATORS:
                            violations.append((fn.name, node.lineno))
                # Rebind: _recent_parent = ...
                for tgt in node.targets:
                    if (isinstance(tgt, ast.Name)
                            and tgt.id == "_recent_parent"):
                        if fn.name not in ALLOWED_MUTATORS:
                            violations.append((fn.name, node.lineno))
            # Call: _recent_parent.pop / .setdefault / .clear etc.
            if isinstance(node, ast.Call):
                func = node.func
                if (isinstance(func, ast.Attribute)
                        and isinstance(func.value, ast.Name)
                        and func.value.id == "_recent_parent"
                        and func.attr in {"pop", "setdefault", "clear", "update", "popitem"}):
                    if fn.name not in ALLOWED_MUTATORS:
                        violations.append((fn.name, node.lineno))
            # Delete: del _recent_parent[...]
            if isinstance(node, ast.Delete):
                for tgt in node.targets:
                    if (isinstance(tgt, ast.Subscript)
                            and isinstance(tgt.value, ast.Name)
                            and tgt.value.id == "_recent_parent"):
                        if fn.name not in ALLOWED_MUTATORS:
                            violations.append((fn.name, node.lineno))

    assert not violations, (
        f"C1 violation: `_recent_parent` mutated outside writer-task scope: "
        f"{violations}. Allowed mutators: {sorted(ALLOWED_MUTATORS)}. "
        "Move the mutation inside `_flush_one` (or a helper called only by "
        "it). Producer's emit() must never touch _recent_parent — race-prone "
        "with the writer task."
    )


# ══════════════════════════════════════════════════════════════════════════
# 12. C2 — every payload has lossless from_json_dict round-trip
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("event_type", sorted(_PAYLOAD_CLASSES.keys()))
def test_every_payload_has_lossless_from_json_dict(event_type):
    """C2 — every payload class round-trips through
    json.dumps(asdict, default=_event_log_default) → json.loads →
    cls.from_json_dict losslessly.

    Verifies the deserialization side of the encoder/decoder pair.
    """
    payload = _sample_payloads()[event_type[0]]
    cls = type(payload)
    assert hasattr(cls, "from_json_dict"), (
        f"C2: {cls.__name__} missing `from_json_dict` classmethod. "
        "Required per Plan v2 Block A."
    )

    blob = _producer._serialize_payload(payload)
    decoded = json.loads(blob)
    rebuilt = cls.from_json_dict(decoded, schema_version=1)

    # Compare field-by-field. Direct dataclass equality works because all
    # payloads are frozen + slots-friendly + use comparable field types.
    assert rebuilt == payload, (
        f"C2 round-trip failure for {event_type}:\n"
        f"  original: {payload!r}\n"
        f"  rebuilt:  {rebuilt!r}\n"
        f"  decoded dict: {decoded!r}"
    )


# ══════════════════════════════════════════════════════════════════════════
# 13. C3 — every event_type has a _PAYLOAD_CLASSES entry for current version
# ══════════════════════════════════════════════════════════════════════════


def test_every_event_type_has_dispatch_entry_for_current_version():
    """C3 — for every event_type in EVENT_TYPES, the dispatch table
    `_PAYLOAD_CLASSES` has an entry for the current SCHEMA_VERSIONS[type].

    Replay logic does `cls = _PAYLOAD_CLASSES[(event_type, schema_version)]`.
    A missing dispatch entry would crash replay on first encounter of
    that event type.
    """
    missing: list[tuple[str, int]] = []
    for event_type in EVENT_TYPES:
        current_version = SCHEMA_VERSIONS[event_type]
        key = (event_type, current_version)
        if key not in _PAYLOAD_CLASSES:
            missing.append(key)

    assert not missing, (
        f"C3 violation: _PAYLOAD_CLASSES missing dispatch entries for "
        f"{missing}. Every (event_type, current_version) must map to a "
        f"payload class so replay can deserialize."
    )

    # The mapped class must have a `from_json_dict` classmethod (C2 + C3 cross-link).
    for (event_type, version), cls in _PAYLOAD_CLASSES.items():
        assert hasattr(cls, "from_json_dict"), (
            f"C3 + C2: dispatch table maps ({event_type!r}, {version}) → "
            f"{cls.__name__}, but the class lacks `from_json_dict`. "
            f"Add the classmethod (see C2 contract)."
        )
