# P0.0.7 Plan v2 — Event Log + Replay Harness

**Status:** v2 draft incorporating architect's R1-R5 precision refinements
on Plan v1. Pure documentation; implementation lands in the code phase
after v2 sign-off.

**Date:** 2026-05-17.
**Supersedes:** `tests/p0_07_plan_v1.md` (kept for delta visibility).
**Phase 0 audit:** `tests/p0_07_event_boundary_audit.md` (locked D1-D8).

---

## Delta from v1

| R# | v1 stance | v2 resolution |
|---|---|---|
| **R1** | "Producer threads through most recent parent's assigned id" — mechanism unspecified | Locked: producer maintains `_recent_parent: dict[str, dict[str, int]]` keyed by session_id → event_type → most-recent-id; emit() generates id internally; child events resolve parent via NATURAL_PARENT_PAIRS at emit time; cache cleared on `session_lifecycle=close` |
| **R2** | "JSON-serializable via dataclasses.asdict + explicit handlers" — encoder unnamed | Locked: `_event_log_default(obj)` encoder named explicitly with handlers for frozenset/set/Path/Enum; new contract test `test_every_payload_round_trips_through_event_log_default` verifies lossless round-trip per dataclass |
| **R3** | "Next available version number" for migration | Locked: `_m_0012_create_event_log_*` (verified — brain.db's latest is `_m_0011_intent_divergences_mode_*` per `core/brain_db_migrations.py`) |
| **R4** | NATURAL_PARENT_PAIRS = 3 pairs without scope rationale | One-sentence rationale added in Block B explaining why these 3 (strongest causal links + v1's replay use cases — Bug-W class debugging + P0.S1 anti-spoof regression) and what's deliberately deferred (intent_classification→audio_in, memory_write→routing_decision, tts_out→routing_decision; add when replay analysis surfaces gaps) |
| **R5** | "+41 tests" total without per-file breakdown | Block E gains an explicit test-count breakdown table (P0.10 Block D shape): 15 contract + 10 producer invariants + 11 hook coverage + 5 replay smoke = 41; cross-checked against the 4 new test files' contents |

---

## Block A — Event types + payload contracts (unchanged from v1 except R2 + R4 callouts)

**File:** `core/event_log/types.py` (new). Authoritative module.

### Closed event-type set (D3 — unchanged)

```python
EVENT_TYPES: frozenset[str] = frozenset({
    "audio_in",
    "vision_frame",
    "identity_claim",
    "presence_state",
    "routing_decision",
    "intent_classification",
    "tool_call",
    "tool_result",
    "memory_write",
    "state_write",
    "tts_out",
    "session_lifecycle",
})
```

### Common envelope (D4 — docstring locked verbatim)

```python
@dataclass(frozen=True)
class EventEnvelope:
    """Identity fields carried by every event in the log.

    `parent_event_id` is the IMMEDIATE UPSTREAM event in the natural-pair
    chain — NOT a full causal ancestor. Replay reconstruction queries all
    events within `session_id`, not just walks `parent_event_id`
    recursively. See `NATURAL_PARENT_PAIRS` in this module for the
    enumerated set of (child_event_type, parent_event_type) pairs where
    parent_event_id is populated. For all other event types it is None
    and (ts, session_id, room_session_id) drive ordering.
    """
    ts:              float
    session_id:      Optional[str]
    room_session_id: Optional[str]
    event_type:      str
    schema_version:  int
    parent_event_id: Optional[int]
```

### Natural-pair causality (R4 — scope rationale added)

```python
# (child_event_type, parent_event_type) — when emitting `child`, the
# producer looks up the most recent `parent` for the same session via
# _recent_parent and threads its assigned id through as parent_event_id.
#
# v1 scope is intentionally conservative — only the strongest causal
# links that v1's replay use cases require:
#   - tool_call → tool_result          : verify tool-execution shape
#   - audio_in → identity_claim         : trace voice ID back to source audio
#   - identity_claim → routing_decision : trace dispatch back to claim
#
# Deferred candidates (add when replay analysis surfaces gaps):
#   - intent_classification → audio_in     (classifier input correlation)
#   - memory_write → routing_decision      (turn → log entry causality)
#   - tts_out → routing_decision           (response → routing causality)
# Same shape as P0.10's "validation window catches gaps post-ship"
# framing — add edges as the replay tool finds them load-bearing.
NATURAL_PARENT_PAIRS: frozenset[tuple[str, str]] = frozenset({
    ("tool_result", "tool_call"),
    ("identity_claim", "audio_in"),
    ("routing_decision", "identity_claim"),
})
```

### Per-event payload dataclasses (unchanged from v1)

Same 12 payload dataclasses as Plan v1 Block A (omitted here to keep delta
tight; see v1 for full text). Key load-bearing field on VisionFramePayload
preserved:

```python
@dataclass(frozen=True)
class VisionFramePayload:
    """vision_frame: per-frame snapshot from the background scan.

    **P0.S1 prerequisite (locked by P0.0.7 Plan v1+v2):** the
    `anti_spoof_live` + `anti_spoof_score` fields are LOAD-BEARING for
    P0.S1's anti-spoof-on-every-match regression test. ...

    **D2 lock (no inline images):** `frame_path` references
    faces/frames/<frame_id>.jpg written by the producer hook. The
    event payload itself NEVER embeds image bytes or base64-encoded
    pixel data ...
    """
    frame_id:                 str
    frame_path:               Optional[str]
    frame_ts:                 float
    n_detections:             int
    recognized:               tuple[tuple[str, float, float], ...]
    unrecognized_track_ids:   tuple[int, ...]
    anti_spoof_live:          bool                # LOAD-BEARING (P0.S1)
    anti_spoof_score:         Optional[float]     # LOAD-BEARING (P0.S1)
```

### Schema versioning (D6 — unchanged)

```python
SCHEMA_VERSIONS: dict[str, int] = {
    "audio_in":               1,
    "vision_frame":           1,
    "identity_claim":         1,
    "presence_state":         1,
    "routing_decision":       1,
    "intent_classification":  1,
    "tool_call":              1,
    "tool_result":            1,
    "memory_write":           1,
    "state_write":            1,
    "tts_out":                1,
    "session_lifecycle":      1,
}
```

---

## Block B — Producer interface + R1 parent threading + R2 JSON encoder

**File:** `core/event_log/producer.py` (new).

### R1 — `parent_event_id` threading mechanism (locked)

```python
# Per-session cache of the most recent emitted event id keyed by event_type.
# Resolution lookup at emit() time when (child_type, parent_type) in
# NATURAL_PARENT_PAIRS — producer looks up
# _recent_parent[session_id][parent_type] and threads that id through
# as parent_event_id.
#
# Cache lifetime: per-session. Cleared when session_lifecycle event with
# lifecycle="close" is emitted for the same session_id. A child event
# without a corresponding parent in the cache (parent never emitted, OR
# parent dropped under backpressure, OR session opened mid-replay) sets
# parent_event_id=None — replay tool handles missing parents gracefully.
_recent_parent: dict[str, dict[str, int]] = {}


def _resolve_parent_event_id(
    session_id: Optional[str],
    event_type: str,
) -> Optional[int]:
    """Look up the most-recent parent event id for this (session, child)
    pair via the NATURAL_PARENT_PAIRS table. Returns None when no parent
    has been emitted in this session yet."""
    if session_id is None:
        return None
    session_cache = _recent_parent.get(session_id, {})
    for child, parent_type in NATURAL_PARENT_PAIRS:
        if child == event_type:
            return session_cache.get(parent_type)
    return None


def _record_parent(
    session_id: Optional[str],
    event_type: str,
    event_id: int,
) -> None:
    """Update the per-session cache with the just-assigned id, so
    downstream children in NATURAL_PARENT_PAIRS can resolve to it."""
    if session_id is None:
        return
    _recent_parent.setdefault(session_id, {})[event_type] = event_id


def _clear_session_parents(session_id: str) -> None:
    """Drop the per-session parent cache on session_lifecycle=close.
    Called by emit() after writing the close event."""
    _recent_parent.pop(session_id, None)
```

**Why per-session cache vs global LRU:** session-scoped parents naturally
expire when the session closes; LRU would let cross-session linkage
leak (a routing_decision in session B finding an identity_claim from
session A as its "parent"). Per-session scoping prevents that.

**Why client-side id vs DB-assigned id:** spec'd as DB-assigned via
SQLite AUTOINCREMENT. Producer awaits the queue-drain task which performs
the INSERT + reads `cursor.lastrowid`, then updates `_recent_parent`
**before** any child event referencing this parent can be processed.
Since the writer task is single-threaded, this ordering is structurally
preserved without locks. Synthetic uuid7 (option (a)) was considered
but rejected: collision-resistant ids add complexity without buying
anything — the SQLite AUTOINCREMENT id is unique per row and the writer
task serializes id assignment naturally.

### R2 — JSON encoder named explicitly

```python
# core/event_log/producer.py module-level

import dataclasses
import json
from enum import Enum
from pathlib import Path


def _event_log_default(obj):
    """JSON encoder default-handler for event_log payloads.

    Handles types that json.dumps doesn't serialize natively but appear
    in payload fields:
      - dataclass instances → dataclasses.asdict (recursive)
      - frozenset / set → sorted list (deterministic ordering for replay
        diffs to stay stable across runs)
      - Path → str
      - Enum → .value (the primitive)

    Raises TypeError on unhandled types — replay round-trip contract test
    catches any type that slipped into a payload without an entry here.
    """
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    if isinstance(obj, (frozenset, set)):
        return sorted(obj)
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value
    raise TypeError(
        f"event_log: cannot serialize {type(obj).__name__}; "
        f"add a handler in `_event_log_default` or simplify the field."
    )


def _serialize_payload(payload: object) -> bytes:
    """Single canonical serialization path for event_log payloads.
    Used by `emit` and exercised by the round-trip contract test."""
    return json.dumps(
        dataclasses.asdict(payload),
        default=_event_log_default,
        sort_keys=True,    # deterministic byte-for-byte replay diffs
    ).encode("utf-8")
```

### Public API (unchanged from v1 except internal `_resolve_parent_event_id` call)

```python
async def emit(
    event_type: str,
    payload: object,
    *,
    session_id: Optional[str] = None,
    room_session_id: Optional[str] = None,
    parent_event_id: Optional[int] = None,   # caller override; None → auto-resolve
) -> Optional[int]:
    """Queue an event for async write.

    If `parent_event_id` is None AND `(event_type, ?)` matches a child
    role in NATURAL_PARENT_PAIRS, the producer auto-resolves via
    `_resolve_parent_event_id(session_id, event_type)`. Callers can
    explicitly pass `parent_event_id` to override (e.g., to break the
    natural-pair link in a specific replay scenario).

    Returns the to-be-assigned id when EVENT_LOG_ENABLED=1, else None.
    """


def get_drop_count() -> int:
    """Number of events dropped due to backpressure since process start.
    Exposed via `core.health.gather_health_snapshot` per D5."""


async def start_writer(db_path: Optional[Path] = None) -> None: ...
async def stop_writer() -> None: ...
```

### Storage contract (D1 + R3) — migration version locked

- DB: brain.db (existing, P0.9 plumbing).
- Migration version: **`_m_0012_create_event_log_*`** (R3 lock — verified
  against `core/brain_db_migrations.py` where the latest is
  `_m_0011_intent_divergences_mode_*`).
- 5-tuple per P0.9 contract:
  - `_m_0012_create_event_log_apply(conn)`: CREATE TABLE + 3 indexes.
  - `_m_0012_create_event_log_verify_post(conn)`: assert table + all 3
    indexes exist with the documented column shape.
  - `_m_0012_create_event_log_verify_present(conn)`: return True if
    `event_log` table exists on disk (bootstrap predicate).
- Frame storage (D2): JPEG files written by H2 producer hook alongside
  the `vision_frame` event. Path: `faces/frames/<frame_id>.jpg`.

### Backpressure semantics (D5 — unchanged)

- 10000-event bounded `asyncio.Queue`.
- `_drop_count: int` module-level; `get_drop_count()` exposes it.
- `core.health.gather_health_snapshot` reads `get_drop_count()` and adds
  `event_log_drops=N` field; alert if non-zero since last cycle.
- No `event_log_dropped` self-emitting event (circular-dependency guard).

### Test-mode toggle (D8 — unchanged)

```python
EVENT_LOG_ENABLED = os.environ.get("EVENT_LOG_ENABLED", "0") == "1"
EVENT_LOG_TESTING = os.environ.get("EVENT_LOG_TESTING", "0") == "1"
```

---

## Block C — Producer hooks (D7 — N=1 per event_type, unchanged from v1)

**11 hooks total** (8 boundary-wrap + 3 sidecar). Plan v1 Block C table
verbatim; not duplicated here. Structural N=1 invariant test enforces
each event_type appears as exactly one `producer.emit(...)` argument in
the codebase.

---

## Block D — Replay CLI + fixtures (unchanged from v1)

Plan v1 Block D verbatim. CLI ships read-only pretty-printer; full
pipeline replay deferred to P0.S1 dependency work.

---

## Block E — Test plan + R5 explicit breakdown

### R5 — Test count breakdown (P0.10 Block D shape)

| Source | Test file | Count |
|---|---|---|
| Contract tests (one per event_type + payload-set invariants) | `tests/test_event_log_contract.py` | **15** |
| Structural invariants (incl. D7 N=1 producer-per-type + R2 round-trip + R4 NATURAL_PARENT_PAIRS validation + R1 cache lifetime) | `tests/test_event_log_invariants.py` | **10** |
| Producer-hook coverage (D8 — one fast-CI test per hook with EVENT_LOG_TESTING=1) | `tests/test_event_log_producer_coverage.py` | **11** |
| Replay smoke tests (fixture + roundtrip + natural-pair + drop-counter + anti-spoof) | `tests/test_event_log_replay.py` | **5** |
| **Total new tests** | | **41** |

**v1 → v2 delta:**
- Plan v1 said "+41 tests" with the per-file estimates folded informally
  (15 + 10 + ~11 + 5).
- Plan v2 codifies the breakdown into the table above so the auditor
  can verify against the claim cleanly. Math reconciled: contract 15 +
  invariants 10 + coverage 11 + replay 5 = **41 exactly**.
- No behavioral changes from v1's test plan — same files, same coverage
  intent.

### Contract tests (15 — `tests/test_event_log_contract.py`)

One contract test per event_type (12) + 3 module-level invariants:

| # | Test name | Purpose |
|---|---|---|
| 1-12 | `test_<event_type>_payload_dataclass_present_and_valid` | Each EVENT_TYPES member has a matching *Payload dataclass with required fields documented per Block A |
| 13 | `test_event_types_set_matches_payload_dataclasses` | Every type in EVENT_TYPES has a corresponding *Payload class; no orphan types |
| 14 | `test_schema_versions_dict_covers_every_event_type` | Every type in EVENT_TYPES has a SCHEMA_VERSIONS entry |
| 15 | `test_natural_parent_pairs_reference_known_types` | Every (child, parent) in NATURAL_PARENT_PAIRS is in EVENT_TYPES |

### Structural invariants (10 — `tests/test_event_log_invariants.py`)

| # | Test name | R-refinement |
|---|---|---|
| 1 | `test_each_event_type_has_exactly_one_producer_location` | D7 (N=1 AST scan) |
| 2 | `test_vision_frame_payload_includes_anti_spoof_fields` | Load-bearing P0.S1 prerequisite |
| 3 | `test_vision_frame_payload_does_not_embed_image_data` | D2 |
| 4 | `test_parent_event_id_docstring_documents_immediate_upstream` | D4 |
| 5 | `test_drop_counter_exposed_via_health_log_not_self_emit` | D5 |
| 6 | `test_event_log_disabled_emit_is_noop` | D8 plumbing |
| 7 | `test_event_log_testing_mode_uses_in_memory_sqlite` | D8 |
| 8 | `test_every_payload_round_trips_through_event_log_default` | **R2** — every payload → json.dumps(asdict, default=_event_log_default) → json.loads → asdict comparison lossless |
| 9 | `test_recent_parent_cache_cleared_on_session_close` | **R1** — cache lifetime invariant; emit a session_lifecycle=close → assert `_recent_parent[session_id]` is gone |
| 10 | `test_migration_0012_creates_event_log_table` | **R3** — migration version + 5-tuple shape; apply to fresh in-memory DB; assert table + 3 indexes exist with correct column types |

### Producer-hook coverage (11 — `tests/test_event_log_producer_coverage.py`)

One fast-CI test per producer hook (D8). Each sets `EVENT_LOG_TESTING=1`,
calls the wrapped boundary function with minimal stub inputs, asserts
exactly one event of the expected type is emitted with the right payload
shape.

| # | Hook | Test name |
|---|---|---|
| 1 | H1 | `test_h1_audio_in_emits_one_event` |
| 2 | H2 | `test_h2_vision_frame_emits_one_event_and_writes_jpeg` |
| 3 | H3 | `test_h3_identity_claim_emits_one_event` |
| 4 | H4 | `test_h4_presence_state_emits_one_event` |
| 5 | H5 | `test_h5_routing_decision_emits_one_event_with_utt_band` |
| 6 | H6 | `test_h6_intent_classification_emits_one_event` |
| 7 | H7 | `test_h7_tool_call_then_tool_result_links_via_parent_event_id` (R1 dependency) |
| 8 | H8 | `test_h8_memory_write_emits_one_event` |
| 9 | H9 | `test_h9_state_write_emits_one_event` |
| 10 | H10 | `test_h10_tts_out_emits_one_event_with_text_truncation` |
| 11 | H11 | `test_h11_session_lifecycle_open_close_clears_parent_cache` (R1 dependency) |

### Replay smoke tests (5 — `tests/test_event_log_replay.py`)

| # | Test name | Purpose |
|---|---|---|
| 1 | `test_replay_fixture_yields_replay_context` | Fixture-level smoke |
| 2 | `test_replay_emit_and_retrieve_roundtrip` | Emit/query single event |
| 3 | `test_replay_natural_pair_chain_linked` | tool_call → tool_result via parent_event_id (R1 end-to-end) |
| 4 | `test_replay_drop_counter_bumps_on_queue_full` | Backpressure (D5) |
| 5 | `test_replay_anti_spoof_fields_round_trip` | Load-bearing P0.S1 prerequisite — vision_frame anti_spoof fields preserved across emit→write→read cycle |

**Suite count projection:** ~2179 (current post-P0.0.2) → ~2220 after
all 41 tests land. Pre-existing 9 xfailed unchanged.

---

## Block F — Step sequence (R3 version-locked)

1. **Step 1** (`core/event_log/types.py`): EVENT_TYPES + NATURAL_PARENT_PAIRS + 12 Payload dataclasses + SCHEMA_VERSIONS + EventEnvelope docstring (R4 + D4). **Test file 1** (15 contract tests).
2. **Step 2** (`core/event_log/producer.py`): emit / get_drop_count / start_writer / stop_writer + `_recent_parent` cache (R1) + `_event_log_default` encoder (R2) + queue plumbing + test-mode toggles. **Test file 2** (10 invariants, incl. R1 cache + R2 round-trip + D7 N=1 + R3 migration test).
3. **Step 3** (`core/event_log/migrations.py` + wire `_m_0012_create_event_log_*` into `core/brain_db_migrations.py`): 5-tuple migration. R3 version-locked.
4. **Step 4** (H1-H6 boundary-wrap hooks): audio_in, identity_claim, presence_state, routing_decision, intent_classification, memory_write. **Test file 3** coverage tests 1-6.
5. **Step 5** (H7-H11 sidecar hooks + remaining): tool_call/tool_result (R1 parent threading end-to-end), state_write, tts_out, session_lifecycle (R1 cache-clear trigger), vision_frame (D2 JPEG storage). **Test file 3** coverage tests 7-11.
6. **Step 6** (`tools/replay_session.py`): read-only pretty-printer CLI.
7. **Step 7** (`tests/fixtures/event_log_fixtures.py`): `replay_session_fixture` + ReplayContext helpers. **Test file 4** (5 replay smoke tests).
8. **Step 8** (`core/health.py` integration): wire `producer.get_drop_count()` into `gather_health_snapshot`; update `format_health_line` for `event_log_drops=N` field.
9. **Step 9** (CLAUDE.md milestone + complete-plan.md update + P0.S1 prerequisite cross-reference at `VisionFramePayload`).

---

## D-decisions + R-refinements — locked summary

| # | Decision | Locked value | Source |
|---|---|---|---|
| **D1** | Storage location | brain.db now; migrate to meta.db when P1.A8 lands | Audit |
| **D2** | Serialization + no inline image data | JSON v1.0; vision_frame uses frame_path reference, NEVER embeds bytes | Audit + clarification |
| **D3** | event_type enum | Closed set in EVENT_TYPES frozenset + structural invariant test | Audit |
| **D4** | parent_event_id semantics | Natural-pair chain (3 pairs); IMMEDIATE upstream only (docstring locked) | Audit + clarification |
| **D5** | Backpressure + drop counter | 10000-event bounded asyncio.Queue; get_drop_count() exposed via health-log (NOT self-emit) | Audit + clarification |
| **D6** | Schema versioning | Per-event_type SCHEMA_VERSIONS dict | Audit |
| **D7** | Producer wiring + N=1 invariant | Boundary-wrap (8) + sidecar (3); structural test asserts N=1 producer per event_type | Audit + clarification |
| **D8** | Test-mode default | EVENT_LOG_ENABLED=0 default; EVENT_LOG_TESTING=1 for fixture; every producer hook has fast-CI test | Audit + clarification |
| **R1** | parent_event_id threading | `_recent_parent: dict[session_id, dict[event_type, id]]`; auto-resolve at emit() time via NATURAL_PARENT_PAIRS; cache cleared on session_lifecycle=close | **v2 NEW** |
| **R2** | JSON encoder | `_event_log_default(obj)` handles dataclass / frozenset / set / Path / Enum; round-trip contract test enforces lossless serialization | **v2 NEW** |
| **R3** | Migration version | `_m_0012_create_event_log_*` (verified: brain.db latest is `_m_0011_intent_divergences_mode_*`) | **v2 NEW** |
| **R4** | NATURAL_PARENT_PAIRS scope | 3 pairs (strongest causal + v1 use cases); deferred candidates documented; add on replay-analysis-surfaced gaps | **v2 NEW** |
| **R5** | Test count breakdown | 15 contract + 10 invariants + 11 hook coverage + 5 replay = 41 (table in Block E) | **v2 NEW** |

**Bookmarked follow-ups** (carried forward from v1; not v2 scope):
- post-P0.10-validation queue-depth measurement → potential 10000 cap tuning.
- MessagePack serialization candidate for P1.A16.
- Full pipeline replay sink (currently read-only).
- Audio waveform sidecar storage.
- Additional NATURAL_PARENT_PAIRS edges (intent_classification→audio_in,
  memory_write→routing_decision, tts_out→routing_decision) — add when
  replay analysis surfaces concrete need.

---

## Files touched (v2)

**New files (created during code phase):**
- `core/event_log/__init__.py` (~5 lines — re-exports `emit`, `start_writer`, `stop_writer`, `get_drop_count`)
- `core/event_log/types.py` (~200 lines — EVENT_TYPES + 12 Payload dataclasses + NATURAL_PARENT_PAIRS + SCHEMA_VERSIONS + EventEnvelope)
- `core/event_log/producer.py` (~250 lines — emit + queue + writer task + `_recent_parent` cache + `_event_log_default` + `_serialize_payload` + EVENT_LOG_ENABLED/TESTING toggles)
- `core/event_log/migrations.py` (~80 lines — `_m_0012_create_event_log_*` 5-tuple)
- `tools/replay_session.py` (~80 lines — read-only pretty-printer CLI)
- `tests/fixtures/event_log_fixtures.py` (~60 lines — `replay_session_fixture` + ReplayContext helpers)
- `tests/test_event_log_contract.py` (~250 lines — 15 tests)
- `tests/test_event_log_invariants.py` (~350 lines — 10 tests incl. R1 / R2 / R3 / D7)
- `tests/test_event_log_producer_coverage.py` (~300 lines — 11 tests)
- `tests/test_event_log_replay.py` (~150 lines — 5 tests)

**Modified files:**
- `core/audio.py`: H1 (listen_and_transcribe), H10 (speak / speak_stream) — ~12 lines
- `core/voice_channel.py`: H3 (identify_speaker) — ~6 lines
- `core/vision_channel.py`: H4 (observe_scene) — ~5 lines
- `core/reconciler.py`: H5 (reconcile + utt_band tag) — ~7 lines
- `core/brain.py`: H6 (_classify_intent_smart) — ~6 lines
- `core/db.py`: H8 (FaceDB.log_turn) — ~5 lines
- `core/state.py`: H9 (write) — ~5 lines
- `core/brain_db_migrations.py`: add `_m_0012_*` migration entry — ~50 lines (R3)
- `core/health.py`: wire `producer.get_drop_count()` into `gather_health_snapshot` + format_health_line — ~10 lines
- `pipeline.py`: H2 (vision-loop sidecar + JPEG storage), H7 (`_execute_tool` entry/exit + parent_event_id), H11 (`_open_session` / `_close_session` sidecar) — ~30 lines
- `CLAUDE.md`: P0.0.7 milestone entry — ~10 lines
- `complete-plan.md`: P0.0.7 status update — ~5 lines

**Untouched (per Plan v2 scope):**
- `core/config.py` (no new constants; env-var-driven toggles instead)
- All test files for other P0/P1 work
- Any production code outside the 10 modified files above

---

## Estimate (v2, unchanged from v1)

| Phase | Time |
|---|---|
| Plan v2 → architect+auditor sign-off | ~0.5 day |
| Step 1 (types + 15 contract tests) | ~2-3 hours |
| Step 2 (producer + 10 invariants incl. R1 cache + R2 encoder + D7 N=1 + R3 migration test) | ~3-4 hours |
| Step 3 (migration 0012 + verify_post + verify_present) | ~1-2 hours |
| Step 4 (H1-H6 boundary hooks + 6 coverage tests) | ~3-4 hours |
| Step 5 (H7-H11 sidecar hooks + 5 coverage tests + JPEG storage) | ~4-5 hours |
| Step 6 (replay CLI) | ~1-2 hours |
| Step 7 (replay fixture + 5 smoke tests) | ~2-3 hours |
| Step 8 (health-log integration) | ~1 hour |
| Step 9 (CLAUDE.md + complete-plan.md updates) | ~30 min |
| **Total P0.0.7 closure** | **~2-3 dev days** |

---

## Sign-off blocks carried forward to v2

All R1-R5 absorbed into v2; D1-D8 unchanged from audit. Plan v2 has no
open sign-off questions; if the auditor flags polish during review, the
revisions become a v2.1 amendment rather than a v3.

Awaiting joint architect + auditor v2 sign-off → code phase starts on
the 9-step sequence.
