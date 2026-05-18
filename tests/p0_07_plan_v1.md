# P0.0.7 Plan v1 — Event Log + Replay Harness

**Status:** v1 draft incorporating auditor's 5 clarifications on the
Phase 0 audit's D1-D8 + the promoted load-bearing prerequisite
(anti_spoof_* fields on vision_frame). Pure documentation;
implementation lands in the code phase after v2 sign-off.

**Date:** 2026-05-17.
**Phase 0 audit:** `tests/p0_07_event_boundary_audit.md` (locked D1-D8).
**Prerequisites:** P0.0 (CI scaffold) + P0.0.1 (S2 binding fix) +
P0.0.2 (xfail bundling) complete; P0.10 validation window open.

---

## Executive summary

Phase 0 audit closed with all 8 D-decisions signed off + 5 auditor
clarifications + 1 promoted prerequisite. Plan v1 turns those into
concrete deliverables.

**Scope:**

1. New module `core/event_log/` with 4 files (types.py, producer.py,
   migrations.py, __init__.py).
2. brain.db migration creating the `event_log` table (P0.9 5-tuple
   shape: apply + verify_post + verify_present).
3. ~11 producer-hook edits at module boundaries (8 boundary-wrap, 3
   sidecar — per D7 in the audit).
4. CLI replay tool at `tools/replay_session.py` (initial use: human
   inspection; future use: full pipeline replay).
5. Pytest fixture `replay_session_fixture` at
   `tests/fixtures/event_log_fixtures.py` for replay-based regression
   tests.
6. 4 new test files: contract tests, structural invariants, replay
   smoke tests, producer-hook coverage tests.

**Test count estimate:** +35 tests (rough breakdown in Block E below).
Suite target post-Plan v1: ~2214 passing (from current ~2179) + 9
xfailed (unchanged from P0.0.2).

**Load-bearing prerequisite folded in:** `vision_frame`'s payload
**MUST** include `anti_spoof_live: bool` + `anti_spoof_score: float | None`
from day one of P0.0.7. P0.S1's anti-spoof-on-every-match regression
test depends on these fields existing in captured replay logs;
backfilling later is not an option (existing replay logs would be
unreplayable for the anti-spoof tests).

---

## Auditor clarification → Plan v1 mapping

| Clarification | Plan v1 incorporation |
|---|---|
| **D2 (vision_frame no inline image data)** | `VisionFrameEvent` payload spec'd with `frame_id: str` + `frame_path: Optional[str]` reference (separate file, keyed by hash) — never embedded base64. Bytes live in `faces/frames/<frame_id>.jpg` written by the producer hook. Block A documents the constraint + the per-frame storage contract. |
| **D4 (parent_event_id immediate-upstream docstring)** | `EventEnvelope.parent_event_id` field docstring locked verbatim — "the IMMEDIATE upstream event in the natural-pair chain, NOT a full causal ancestor. Replay reconstruction queries all events within session_id, not just walks parent_event_id recursively." Block B documents the contract. Same shape as P0.9.2's "turn_count is per-session" disclosure. |
| **D5 (drop counter via health-log, not self-emitting)** | `core.event_log.producer.get_drop_count() -> int` exposed; integrated with `core.health.gather_health_snapshot` so health log line includes `event_log_drops=N` field. **No** `event_log_dropped` event in the queue (circular-dependency risk noted in audit). Tuning the 10000 cap deferred to post-P0.10-validation empirical measurement. |
| **D7 (N=1 producer-per-event_type structural test)** | `test_each_event_type_has_exactly_one_producer_location` AST scan over `core/event_log/producer.py` callers + `core/*` + `pipeline.py` asserting each `event_type` value appears as a `producer.emit(...)` argument in exactly one file:line. Same shape as P0.10's N=1 `_routing_action` source invariant. Architect's read: ~1-1.5h to implement. **Shipping with v1** (not deferred to P0.0.7.1). |
| **D8 (every producer hook has fast-CI test)** | New test file `tests/test_event_log_producer_coverage.py` — one fast-CI test per producer hook (11 tests). Each test sets `EVENT_LOG_TESTING=1` to get in-memory SQLite, calls the wrapped boundary function with minimal stub inputs, asserts exactly one event of the expected type is emitted. Catches null-input crashes + decorator placement bugs. |
| **Promoted prerequisite (anti_spoof_*)** | `VisionFrameEvent` payload locks `anti_spoof_live: bool` + `anti_spoof_score: float | None` as REQUIRED fields. Producer hook reads from the existing pipeline state (post-anti-spoof check) before emitting. Block A documents the field set with the explicit P0.S1 dependency note. |

---

## Block A — Event types + payload contracts (verbatim spec)

**File:** `core/event_log/types.py` (new). Authoritative module for the
closed event-type set + the per-event payload dataclasses.

### Closed event-type set

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

**Adding a new event_type requires** (per D3 + D7 invariants):
1. Adding to `EVENT_TYPES` (this set).
2. Adding the dataclass below.
3. Adding the producer hook (one location, single source — D7 lock).
4. Updating `tests/test_event_log_producer_coverage.py` (one test per hook).
5. Updating `tests/p0_07_event_boundary_audit.md` Deliverable 1 table.

### Common envelope (every event)

```python
@dataclass(frozen=True)
class EventEnvelope:
    """Identity fields carried by every event in the log.

    Produced once at emission; never reused as a payload root.

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

### Natural-pair causality (D4 contract)

```python
# (child_event_type, parent_event_type) — when emitting `child`, the
# producer threads through the most recent `parent`'s assigned id.
NATURAL_PARENT_PAIRS: frozenset[tuple[str, str]] = frozenset({
    ("tool_result", "tool_call"),
    ("identity_claim", "audio_in"),
    ("routing_decision", "identity_claim"),
})
```

### Per-event payload dataclasses

Each dataclass is frozen + slots; JSON-serializable via dataclasses.asdict +
explicit handlers for tuple/None values.

```python
@dataclass(frozen=True)
class AudioInPayload:
    """audio_in: STT output + acoustic context. Buffer bytes are NOT
    embedded — `audio_hash` correlates to optional sidecar WAV files in
    faces/audio/<hash>.wav (storage contract separate from this spec)."""
    audio_hash:   str           # sha256 of buffer prefix
    speech_secs:  float
    stt_text:     str
    language:     str
    pre_roll_ms:  int


@dataclass(frozen=True)
class VisionFramePayload:
    """vision_frame: per-frame snapshot from the background scan.

    **P0.S1 prerequisite (locked by P0.0.7 Plan v1):** the
    `anti_spoof_live` + `anti_spoof_score` fields are LOAD-BEARING for
    P0.S1's anti-spoof-on-every-match regression test. Anti-spoof
    behavior is replay-tested by reading captured event_log entries
    and asserting `anti_spoof_live=False` correlates with rejected
    matches. Removing or making these fields optional in a future
    refactor breaks P0.S1's test surface — keep them required.

    **D2 lock (no inline images):** `frame_path` references
    faces/frames/<frame_id>.jpg written by the producer hook. The
    event payload itself NEVER embeds image bytes or base64-encoded
    pixel data — that would explode log volume (MB per frame × ~1Hz
    scan rate × hours = unmanageable).
    """
    frame_id:                 str                 # unique per-frame id (uuid7)
    frame_path:               Optional[str]       # faces/frames/<hash>.jpg, None if storage off
    frame_ts:                 float               # camera-timestamp for the frame
    n_detections:             int
    recognized:               tuple[tuple[str, float, float], ...]  # (pid, score, quality)
    unrecognized_track_ids:   tuple[int, ...]
    anti_spoof_live:          bool                # LOAD-BEARING (P0.S1 dependency)
    anti_spoof_score:         Optional[float]     # LOAD-BEARING (P0.S1 dependency)


@dataclass(frozen=True)
class IdentityClaimPayload:
    """identity_claim: voice channel output (wraps the existing IdentityClaim
    dataclass from core/voice_channel.py verbatim)."""
    claim:  "IdentityClaim"   # existing dataclass; serialized via dataclasses.asdict


@dataclass(frozen=True)
class PresenceStatePayload:
    """presence_state: vision channel output (wraps existing PresenceState
    dataclass from core/vision_channel.py verbatim)."""
    presence: "PresenceState"


@dataclass(frozen=True)
class RoutingDecisionPayload:
    """routing_decision: reconciler output + utt_band tag.

    The `utt_band` field is the P0.10 Block C tag (noise/gap/short_hard/normal)
    so the Reconciler-Shadow analysis can be reconstructed from event_log
    alone post-shadow-deletion.
    """
    decision: "RoutingDecision"
    utt_band: str   # noise / gap / short_hard / normal


@dataclass(frozen=True)
class IntentClassificationPayload:
    """intent_classification: classifier sidecar + mode tag."""
    sidecar:    dict[str, object]   # {turn_intent, extracted_value, confidence, reasoning}
    mode:       str                  # "shadow" / "primary" / "retired"
    text:       str                  # user text classified
    from_cache: bool                 # True if cached classifier path


@dataclass(frozen=True)
class ToolCallPayload:
    name:           str
    args:           dict[str, object]
    person_id:      str
    intent_sidecar: Optional[dict[str, object]]


@dataclass(frozen=True)
class ToolResultPayload:
    """tool_result: parent_event_id links to the tool_call."""
    status:        str                 # handled/handled_noop/rejected/unknown/tool_timeout/shutdown
    response_text: Optional[str]
    error:         Optional[str]


@dataclass(frozen=True)
class MemoryWritePayload:
    person_id:       str
    role:            str                # user / assistant
    text:            str
    room_session_id: Optional[str]
    audience_ids:    Optional[tuple[str, ...]]


@dataclass(frozen=True)
class StateWritePayload:
    """state_write: snapshot of what state.write() wrote (changed fields only)."""
    mode:              str
    current_person:    Optional[str]
    current_person_id: Optional[str]
    visible_people:    tuple[str, ...]
    message:           str


@dataclass(frozen=True)
class TtsOutPayload:
    """tts_out: text truncated to 500 chars + sha256 of full text for
    correlation. Truncation prevents DB bloat on long responses."""
    text:            str             # truncated to 500 chars
    text_full_hash:  str             # sha256 of un-truncated text
    language:        str
    was_stream:      bool
    purpose:         str             # greeting / conversation / kairos / enrollment / cloud_recovery
    duration_ms_est: Optional[int]


@dataclass(frozen=True)
class SessionLifecyclePayload:
    lifecycle:       str             # "open" / "close"
    person_id:       str
    person_name:     Optional[str]
    source:          str             # face / voice / voice-only
    person_type:     str             # stranger / known / best_friend / disputed
    room_session_id: Optional[str]
```

### Per-event_type schema versioning (D6)

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

Bumping per-event_type when a payload's shape changes. Replay tool
dispatches on `(event_type, schema_version)` to keep old logs replayable.

---

## Block B — Producer interface + storage contract

**File:** `core/event_log/producer.py` (new).

### Public API

```python
async def emit(
    event_type: str,
    payload: object,                         # one of the *Payload dataclasses
    *,
    session_id: Optional[str] = None,
    room_session_id: Optional[str] = None,
    parent_event_id: Optional[int] = None,
) -> Optional[int]:
    """Queue an event for async write. Returns the to-be-assigned id
    when EVENT_LOG_ENABLED=1, else None (no-op fast path)."""


def get_drop_count() -> int:
    """Return number of events dropped due to backpressure since last
    process start. Exposed to health.gather_health_snapshot per D5."""


async def start_writer(db_path: Optional[Path] = None) -> None:
    """Start the background-writer task. Called once during pipeline boot."""


async def stop_writer() -> None:
    """Drain the queue + shutdown. Called during graceful shutdown."""
```

### Storage contract (D1)

- DB: brain.db (existing).
- Table: `event_log` (schema below).
- Migration: P0.9 5-tuple in `core/brain_db_migrations.py`
  (next available version number).
- Frame storage (D2): `faces/frames/<frame_id>.jpg` JPEGs written
  alongside the `vision_frame` event by the producer hook. Hash-keyed
  so deduplication is free.

### Schema (per audit Deliverable A)

```sql
CREATE TABLE event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    session_id TEXT,
    room_session_id TEXT,
    event_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 0,
    payload BLOB NOT NULL,            -- JSON-serialized payload dataclass
    parent_event_id INTEGER REFERENCES event_log(id)
);
CREATE INDEX idx_event_log_ts ON event_log(ts DESC);
CREATE INDEX idx_event_log_session ON event_log(session_id, ts);
CREATE INDEX idx_event_log_room ON event_log(room_session_id, ts);
```

### Backpressure semantics (D5)

```python
_EVENT_QUEUE_MAX = 10000           # spec-locked v1; tune post-P0.10 validation
_drop_count = 0                    # exposed via get_drop_count()
_queue: asyncio.Queue              # maxsize=_EVENT_QUEUE_MAX
```

- `emit` writes via `queue.put_nowait(envelope_dict)` — never blocks.
- On `QueueFull`: `_drop_count += 1`, log `[EventLog] WARN: dropped — queue full` (max 1 line per 60s rate-limit), return None.
- Health-log integration: `core.health.gather_health_snapshot` reads
  `producer.get_drop_count()` and emits `event_log_drops=N` field. If
  N > 0 since last cycle → `format_health_alerts` adds a watch alert.
- **No `event_log_dropped` event emitted** (D5 circular-dependency guard).

### Test-mode toggle (D8)

```python
EVENT_LOG_ENABLED   = os.environ.get("EVENT_LOG_ENABLED", "0") == "1"   # default off
EVENT_LOG_TESTING   = os.environ.get("EVENT_LOG_TESTING", "0") == "1"   # in-memory SQLite

# When TESTING: db_path is ":memory:" + queue drains synchronously after each emit.
# When PRODUCTION: db_path is faces/brain.db (or whatever BRAIN_DB_PATH points at).
```

`emit` is a no-op when both flags are off (fast CI path).

---

## Block C — Producer hooks (D7 — N=1 per event_type)

**11 hooks total** (8 boundary-wrap + 3 sidecar). Each hook is the
single, authoritative source of its event_type — the structural test
(Block F.3 below) enforces N=1.

| Hook # | event_type | Location | Hook style | Lines edited |
|---|---|---|---|---|
| H1 | `audio_in` | `core/audio.py::listen_and_transcribe` exit | boundary-wrap | ~6 |
| H2 | `vision_frame` | `pipeline._background_vision_loop` per-iteration | sidecar | ~10 (incl. JPEG storage) |
| H3 | `identity_claim` | `core/voice_channel.py::identify_speaker` exit | boundary-wrap | ~6 |
| H4 | `presence_state` | `core/vision_channel.py::observe_scene` exit | boundary-wrap | ~5 |
| H5 | `routing_decision` | `core/reconciler.py::reconcile` exit | boundary-wrap | ~7 (incl. utt_band tag) |
| H6 | `intent_classification` | `core/brain.py::_classify_intent_smart` exit | boundary-wrap | ~6 |
| H7 | `tool_call` + `tool_result` | `pipeline._execute_tool` entry + exit | sidecar | ~15 (incl. parent_event_id thread) |
| H8 | `memory_write` | `core/db.py::FaceDB.log_turn` exit | boundary-wrap | ~5 |
| H9 | `state_write` | `core/state.py::write` exit | boundary-wrap | ~5 |
| H10 | `tts_out` | `core/audio.py::speak` + `speak_stream` exit | boundary-wrap | ~8 |
| H11 | `session_lifecycle` | `pipeline._open_session` + `_close_session` exit | sidecar | ~10 |

Total edit budget: ~83 lines across 8 files. Most edits are
one-liner `await producer.emit(...)` calls after the function's
return point (or its computed-decision capture).

---

## Block D — Replay CLI + fixtures

### Replay CLI (`tools/replay_session.py`)

```bash
# Pretty-print a session's events
python tools/replay_session.py --session jagan_001 --since 1h

# Replay through pipeline (P0.S1+; v1 ships read-only)
python tools/replay_session.py --session jagan_001 --sink pipeline
```

V1 ships the read-only pretty-printer. Full pipeline replay is bookmarked
for the P0.S1 anti-spoof regression test work.

### Pytest fixture

```python
# tests/fixtures/event_log_fixtures.py
@pytest.fixture
def replay_session_fixture(tmp_path, monkeypatch):
    """Set EVENT_LOG_TESTING=1, point producer at in-memory SQLite.

    Yields a `ReplayContext` with helpers:
      - `ctx.emit(event_type, payload)` — synchronous test emit
      - `ctx.events_of_type(event_type)` — list[dict] of captured events
      - `ctx.all_events()` — full list ordered by ts

    Foundation for P0.S1's anti-spoof regression test and R3's
    vision-watchdog regression test.
    """
```

---

## Block E — Test plan

### New tests (~35 tests across 4 new files)

**File 1: `tests/test_event_log_contract.py`** (~15 tests)
- One contract test per event_type asserting:
  - The payload dataclass exists in `core/event_log/types.py`.
  - All required fields are present.
  - `schema_version` matches `SCHEMA_VERSIONS[event_type]`.
- `test_event_types_set_matches_payload_dataclasses` — every type
  in `EVENT_TYPES` has a corresponding `*Payload` dataclass.

**File 2: `tests/test_event_log_invariants.py`** (~10 tests)
- `test_each_event_type_has_exactly_one_producer_location` (D7).
  AST scan over `core/event_log/producer.py` callers + `core/*` +
  `pipeline.py` asserting each `event_type` value appears in exactly
  one `producer.emit(...)` argument.
- `test_natural_parent_pairs_reference_known_types` — every
  `(child, parent)` in `NATURAL_PARENT_PAIRS` is in `EVENT_TYPES`.
- `test_vision_frame_payload_includes_anti_spoof_fields` —
  load-bearing P0.S1 prerequisite; verifies `anti_spoof_live` +
  `anti_spoof_score` are required fields on `VisionFramePayload`.
- `test_vision_frame_payload_does_not_embed_image_data` (D2) —
  asserts `VisionFramePayload` fields don't include `image_bytes` /
  `jpeg_data` / `base64_image` substrings.
- `test_parent_event_id_docstring_documents_immediate_upstream` (D4) —
  source-inspects `EventEnvelope.parent_event_id`'s comment/docstring
  for the "IMMEDIATE upstream, NOT full causal ancestor" guidance.
- `test_drop_counter_exposed_via_health_log_not_self_emit` (D5) —
  asserts `producer.get_drop_count()` exists AND no `emit("event_log_dropped"`
  pattern exists in producer source.
- `test_event_log_disabled_emit_is_noop` — `EVENT_LOG_ENABLED=0`
  emit returns None + writes nothing.
- `test_event_log_testing_mode_uses_in_memory_sqlite` (D8 plumbing) —
  fixture sets `EVENT_LOG_TESTING=1` + asserts producer connection
  is `:memory:`.
- `test_schema_versions_dict_covers_every_event_type` — every type in
  `EVENT_TYPES` has a `SCHEMA_VERSIONS` entry.
- `test_migration_creates_event_log_table` — apply migration to
  fresh in-memory DB; assert `event_log` table + 3 indexes exist.

**File 3: `tests/test_event_log_producer_coverage.py`** (~11 tests, D8)
- One fast-CI test per producer hook. Each test:
  - Sets `EVENT_LOG_TESTING=1`.
  - Calls the wrapped boundary function with minimal stub inputs.
  - Asserts exactly one event of the expected type is emitted.
  - Asserts payload structure conforms to the dataclass.
- Names: `test_h1_audio_in_emits_one_event`, ..., `test_h11_session_lifecycle_emits_one_event`.

**File 4: `tests/test_event_log_replay.py`** (~5 tests)
- `test_replay_fixture_yields_replay_context` — fixture-level smoke.
- `test_replay_emit_and_retrieve_roundtrip` — emit one event, query
  back via `events_of_type` + `all_events`.
- `test_replay_natural_pair_chain_linked` — emit `tool_call`, then
  `tool_result` with `parent_event_id` set; assert query reconstructs
  the link.
- `test_replay_drop_counter_bumps_on_queue_full` — fill queue,
  assert `get_drop_count()` increments.
- `test_replay_anti_spoof_fields_round_trip` — emit `vision_frame`
  with anti_spoof fields, replay back, assert fields preserved
  (load-bearing for P0.S1 regression test prerequisite).

**Existing tests:** none deleted; no surface overlap with P0.10 / P0.0.

**Test count delta:**
- New tests: ~41
- Pre-existing test updates: 0
- Suite target: ~2179 (current) → ~2220 (post-Plan v1 land)

---

## Block F — Step sequence

1. **Step 1** (`core/event_log/types.py`): EVENT_TYPES + NATURAL_PARENT_PAIRS + all 12 Payload dataclasses + SCHEMA_VERSIONS. **Test file 1** (contract tests, ~15 tests).
2. **Step 2** (`core/event_log/producer.py`): emit + get_drop_count + start_writer + stop_writer + queue plumbing + test-mode toggles. **Test file 2** (invariants, 10 tests).
3. **Step 3** (`core/event_log/migrations.py` + wire into `core/brain_db_migrations.py`): 5-tuple migration creating event_log table + 3 indexes. Verify_post + verify_present per P0.9 contract.
4. **Step 4** (H1-H6 boundary-wrap hooks): audio_in, identity_claim, presence_state, routing_decision, intent_classification, memory_write. ~30 lines across 5 files. **Test file 3** producer-coverage tests for H1-H6.
5. **Step 5** (H7-H11 sidecar + remaining boundary hooks): tool_call/tool_result, state_write, tts_out, session_lifecycle, vision_frame. ~50 lines across 4 files (pipeline.py + state.py + audio.py + plus the vision_frame JPEG storage in pipeline._background_vision_loop). **Test file 3** producer-coverage tests for H7-H11.
6. **Step 6** (`tools/replay_session.py`): read-only pretty-printer CLI; ~80 lines.
7. **Step 7** (`tests/fixtures/event_log_fixtures.py` + **Test file 4** replay smoke tests): fixture + 5 replay tests.
8. **Step 8** (health-log integration — `core/health.py`): wire `producer.get_drop_count()` into `gather_health_snapshot`. Update `format_health_line` to include `event_log_drops=N` field. ~10 lines.
9. **Step 9** (CLAUDE.md milestone + complete-plan.md update + P0.S1 prerequisite note pointing at `VisionFramePayload`'s anti_spoof fields as load-bearing).

---

## D-decisions — locked summary

| # | Decision | Locked value | Source |
|---|---|---|---|
| **D1** | Storage location | brain.db now; migrate to meta.db when P1.A8 lands | Audit Deliverable 4 |
| **D2** | Serialization + no inline image data | JSON v1.0; vision_frame uses frame_path reference, NEVER embeds bytes | Audit + auditor clarification |
| **D3** | event_type enum | Closed set in EVENT_TYPES frozenset + structural invariant test | Audit Deliverable 4 |
| **D4** | parent_event_id semantics | Natural-pair chain (3 pairs); IMMEDIATE upstream only (docstring locked) | Audit + auditor clarification |
| **D5** | Backpressure + drop counter | 10000-event bounded asyncio.Queue; get_drop_count() exposed via health-log (NOT self-emit) | Audit + auditor clarification |
| **D6** | Schema versioning | Per-event_type SCHEMA_VERSIONS dict | Audit Deliverable 4 |
| **D7** | Producer wiring + N=1 invariant | Boundary-wrap (8) + sidecar (3); structural test asserts N=1 producer per event_type | Audit + auditor clarification |
| **D8** | Test-mode default | EVENT_LOG_ENABLED=0 default; EVENT_LOG_TESTING=1 for fixture; every producer hook has fast-CI test | Audit + auditor clarification |

**Bookmarked follow-ups** (not Plan v1 scope; flagged for future PRs):
- post-P0.10-validation queue-depth measurement → potential 10000 cap tuning.
- MessagePack serialization candidate for P1.A16.
- Full pipeline replay sink for `tools/replay_session.py` (currently read-only).
- Audio waveform sidecar storage (separate from event_log).

---

## Estimate

| Phase | Time |
|---|---|
| Plan v1 → architect+auditor sign-off | ~0.5-1 day (this draft + revisions) |
| Step 1 (types + contract tests) | ~2-3 hours |
| Step 2 (producer + invariant tests, incl. D7 N=1 AST scan) | ~3-4 hours |
| Step 3 (migration + verify) | ~1-2 hours |
| Step 4 (H1-H6 boundary hooks + coverage tests) | ~3-4 hours |
| Step 5 (H7-H11 sidecar hooks + coverage tests + JPEG storage) | ~4-5 hours |
| Step 6 (replay CLI) | ~1-2 hours |
| Step 7 (replay fixture + smoke tests) | ~2-3 hours |
| Step 8 (health-log integration) | ~1 hour |
| Step 9 (CLAUDE.md + complete-plan.md updates) | ~30 min |
| **Total P0.0.7 closure** | **~2-3 dev days** (matches complete-plan.md estimate) |

---

## Sign-off requests carried forward to v2

None currently. All 8 D-decisions locked with the 5 auditor clarifications
absorbed. Plan v1 is comprehensive enough to land verbatim; if reviewer
flags polish during v1 review the revisions become Plan v2.

Awaiting architect + auditor Plan v1 sign-off.
