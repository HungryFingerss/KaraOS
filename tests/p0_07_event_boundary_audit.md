# P0.0.7 Phase 0 Event-Boundary Audit

**Status:** Pre-Plan audit. Pure documentation, zero production code changes.
**Date:** 2026-05-17.
**Suite at audit time:** ~2179 passing, 8 marked `slow+models` (now excluded from fast CI per P0.0).

**Companion files (created during code phase, not this audit):**
- `core/event_log/types.py` — typed event dataclasses (Plan v1+).
- `core/event_log/producer.py` — async producer interface (Plan v1+).
- `tools/replay_session.py` — replay CLI (Plan v1+).
- `tests/test_event_log_invariants.py` — structural locks (Plan v1+).
- `tests/test_event_log_replay.py` — replay-fixture-based regression tests (Plan v1+).

---

## Executive summary

The pipeline today has **12 distinct event types** that cross the runtime
boundary in a way worth recording for replay. The event-source code is
spread across pipeline.py + `core/voice.py` + `core/vision.py` + `core/audio.py`
+ `core/reconciler.py` + `core/state.py` + `core/db.py` — wrapping at the
**module boundary** (rather than at each pipeline.py call site) minimises the
production-edit surface area to **~11 instrumentation hooks** that cover
**~50+ call sites in pipeline.py**.

**Storage placement (D1) finding:** `brain.db` is the right initial home.
`meta.db` (the P1.A8 split target) does not exist yet, and creating it
inside P0.0.7 would bundle a DB-split refactor with the event-log
introduction — two architectural changes in one PR violates the
spec-first discipline. P0.0.7 lands `event_log` in brain.db with the
existing P0.9 MIGRATIONS plumbing; the eventual P1.A8 split owns the
`brain.db → meta.db` migration for this table.

**Causal-chain finding (D4):** the `parent_event_id` column is **most
useful for a small natural-pair set** (`tool_call → tool_result`,
`identity_claim → routing_decision`, `audio_in → identity_claim`). For
everything else the column is NULL and events correlate via `(ts,
session_id, room_session_id)`. Forcing a strict DAG everywhere is
overengineering.

**Backpressure finding (D5):** lossy under backpressure per the spec.
Recommend a 10000-event bounded `asyncio.Queue` with a drop counter that
emits a nightly `[EventLog] WARN: dropped N events` if non-zero. Same
shape as P0.5's `_faiss_degraded` flag — degrade gracefully, log loudly,
never break the producer.

---

## Deliverable 1 — Producer-boundary enumeration

**Result: 12 event types.** Inputs that cross the runtime boundary in a
way worth recording for replay. Counted from grep + structural reading of
pipeline.py + core/. Outputs marked `→` indicate the event payload's
authoritative dataclass (where one exists today).

| # | event_type | Boundary description | Producer module / function | Payload dataclass |
|---|---|---|---|---|
| 1 | `audio_in` | Audio chunk arrives from microphone via `record_until_silence` → `transcribe` → STT result | `core/audio.py::listen_and_transcribe` (wraps `record_until_silence` + `transcribe`) | NEW — `AudioInEvent` (see Deliverable 2) |
| 2 | `vision_frame` | Camera frame snapshot → face detection → recognize | `core/vision.py::FaceDetector.detect_with_tracking` (called per ~5th frame in `_background_vision_loop`) | NEW — `VisionFrameEvent` |
| 3 | `identity_claim` | Voice-ID returns `IdentityClaim` for current utterance | `core/voice_channel.py::identify_speaker` (Phase 1 shadow at pipeline.py:7066+) → returns `IdentityClaim` | EXISTING — `IdentityClaim` (verbatim) |
| 4 | `presence_state` | Vision channel returns `PresenceState` for current frame | `core/vision_channel.py::observe_scene` → returns `PresenceState` | EXISTING — `PresenceState` (verbatim) |
| 5 | `routing_decision` | Reconciler returns `RoutingDecision` for `(claim, presence, session)` | `core/reconciler.py::reconcile` at pipeline.py:7123 | EXISTING — `RoutingDecision` (verbatim) |
| 6 | `intent_classification` | Classifier returns sidecar `{turn_intent, extracted_value, confidence, reasoning}` | `core/brain.py::_classify_intent_smart` at pipeline.py:5388; `_classify_intent_cached` at pipeline.py:1045 (multi-person heuristic path); shadow at pipeline.py:5444-5445 | NEW — `IntentClassificationEvent` (wraps sidecar dict + mode tag) |
| 7 | `tool_call` | LLM emits tool dispatch | `pipeline._execute_tool` entry at pipeline.py:5483 (gather), pipeline.py:5497 (serial loop) | NEW — `ToolCallEvent` |
| 8 | `tool_result` | Tool returns status (`handled` / `handled_noop` / `rejected` / `unknown` / `tool_timeout` / `shutdown`) | Same `_execute_tool` site — emit after handler returns | NEW — `ToolResultEvent` (carries `parent_event_id` linking to its tool_call) |
| 9 | `memory_write` | Persisted conversation turn via `db.log_turn` | `pipeline._kairos_tick` at pipeline.py:2968-2971; `conversation_turn` at pipeline.py:5718-5720, 4825 | NEW — `MemoryWriteEvent` |
| 10 | `state_write` | Dashboard IPC via `state.write` | 8 sites in pipeline.py (839, 5935, 6027, 6109, 6172, 6179, 6415, 7684) | NEW — `StateWriteEvent` |
| 11 | `tts_out` | TTS emission via `speak` / `speak_stream` | `core/audio.py::speak` (wraps Kokoro / Piper); 30+ pipeline.py call sites | NEW — `TtsOutEvent` |
| 12 | `session_lifecycle` | `_open_session` / `_close_session` | 6 open sites + 2 close sites in pipeline.py | NEW — `SessionLifecycleEvent` |

**Bookmarked but excluded from initial scope** (Spec mentioned `action_proposal` / `action_result` — the codebase does not yet have an "action" concept distinct from `tool_call`. Document this gap for future work; do NOT introduce a new layer in P0.0.7. May appear when P1.A4 service decomposition lands or when robotics actions ship in P0.S1+.)

---

## Deliverable 2 — Event payload shapes

Each event ships a typed dataclass under `core/event_log/types.py`
(created during the code phase). Where an existing dataclass already
captures the boundary's output (IdentityClaim, PresenceState,
RoutingDecision), the event payload embeds it verbatim — no
re-serialization.

### Common envelope (every event)

```python
@dataclass(frozen=True)
class EventEnvelope:
    """Identity fields carried by every event in the log.
    Authored once; never reused as a payload root."""
    ts:                float           # time.time() at producer
    session_id:        Optional[str]   # per-person session pid
    room_session_id:   Optional[str]   # per-room session id
    event_type:        str             # one of EVENT_TYPES (closed set)
    schema_version:    int             # bumped per event_type as payload evolves
    parent_event_id:   Optional[int]   # natural-pair causality (see D4)
    # `id` is DB-assigned via AUTOINCREMENT, not part of producer envelope.
```

### Per-event_type payloads

| event_type | Payload fields | Notes |
|---|---|---|
| `audio_in` | `audio_hash: str` (sha256 of buffer prefix), `speech_secs: float`, `stt_text: str`, `language: str`, `pre_roll_ms: int` | Do NOT log full audio buffer — bloats DB, defeats lossy-backpressure goal. `audio_hash` lets replay correlate against captured WAV files stored separately if needed. |
| `vision_frame` | `frame_ts: float`, `n_detections: int`, `recognized: list[{pid, score, quality}]`, `unrecognized_track_ids: tuple[int, ...]`, `anti_spoof_live: Optional[bool]`, `anti_spoof_score: Optional[float]` | Anti-spoof fields included so S1 regression tests can replay-and-assert. |
| `identity_claim` | `claim: IdentityClaim` (verbatim) | Existing dataclass from core/voice_channel.py. |
| `presence_state` | `presence: PresenceState` (verbatim) | Existing dataclass from core/vision_channel.py. Already frozen + JSON-serializable. |
| `routing_decision` | `decision: RoutingDecision` (verbatim), `utt_band: str` (gap/short_hard/normal/noise) | `utt_band` is the P0.10 Block C tag; emit it alongside the decision so the Reconciler-Shadow analysis can be reconstructed from event_log alone post-shadow-deletion. |
| `intent_classification` | `sidecar: dict` (existing shape — turn_intent/extracted_value/confidence/reasoning), `mode: str` (shadow/primary/retired), `text: str` (the user text classified), `from_cache: bool` | `from_cache` distinguishes `_classify_intent_cached` hits from fresh classifier calls. |
| `tool_call` | `name: str`, `args: dict`, `person_id: str`, `intent_sidecar: Optional[dict]` | `intent_sidecar` is the dual-gate input. |
| `tool_result` | `status: str` (handled/handled_noop/rejected/unknown/tool_timeout/shutdown), `response_text: Optional[str]`, `error: Optional[str]` | `parent_event_id` set to the corresponding `tool_call`. |
| `memory_write` | `person_id: str`, `role: str` (user/assistant), `text: str`, `room_session_id: Optional[str]`, `audience_ids: Optional[list[str]]` | Mirrors `db.log_turn`'s signature. |
| `state_write` | `mode: str`, `current_person: Optional[str]`, `current_person_id: Optional[str]`, `visible_people: list[str]`, `message: str` | Snapshot of what `state.write()` wrote (not the full state dict — just the changed fields per call). |
| `tts_out` | `text: str` (truncated to 500 chars), `text_full_hash: str` (sha256 for long-text correlation), `language: str`, `was_stream: bool`, `purpose: str` (greeting/conversation/kairos/enrollment), `duration_ms_est: Optional[int]` | Truncation prevents DB bloat on long responses. |
| `session_lifecycle` | `lifecycle: str` (open/close), `person_id: str`, `person_name: Optional[str]`, `source: str` (face/voice/voice-only), `person_type: str` (stranger/known/best_friend/disputed), `room_session_id: Optional[str]` | Both open and close share the shape; `lifecycle` discriminator distinguishes. |

---

## Deliverable 3 — Producer instrumentation hooks

**~11 hooks** wrap module boundaries instead of pipeline.py call sites.
The hook receives the boundary function's outputs and emits one event
via `core.event_log.producer.emit(event)`. Hooks are async-safe and
never block — `emit` queues to an `asyncio.Queue` that drains in a
background task.

| Hook # | Location | Wrapped function / call site | Event type emitted | # pipeline.py call sites covered |
|---|---|---|---|---|
| H1 | `core/audio.py::listen_and_transcribe` (wrap exit) | The function itself — emit after STT result returns | `audio_in` | 6 sites (pipeline.py:3187, 3198, 3205, 6617, 6792, 6836) |
| H2 | `pipeline._background_vision_loop` per-iteration (sidecar emit) | Inside the existing vision-loop scan body — emit one event per scan tick | `vision_frame` | 1 site (the loop itself) |
| H3 | `core/voice_channel.py::identify_speaker` (wrap exit) | Emit after the function returns its `IdentityClaim` | `identity_claim` | 1 site (pipeline.py:7068) |
| H4 | `core/vision_channel.py::observe_scene` (wrap exit) | Emit after PresenceState is computed | `presence_state` | 1 site (the scan loop) — emitted at the same cadence as `vision_frame` |
| H5 | `core/reconciler.py::reconcile` (wrap exit) | Emit after `_CASCADE` dispatch returns | `routing_decision` | 1 site (pipeline.py:7123) |
| H6 | `core/brain.py::_classify_intent_smart` (wrap exit) | Emit after sidecar returns | `intent_classification` | 3 sites (pipeline.py:1065, 5388, 5444-5445) |
| H7 | `pipeline._execute_tool` (wrap entry + exit) | Entry emits `tool_call`; exit emits `tool_result` with parent_event_id link | `tool_call` + `tool_result` | 2 sites (pipeline.py:5483 gather, 5497 serial) |
| H8 | `core/db.py::FaceDB.log_turn` (wrap exit) | Emit after row is inserted (best-effort — db is already synchronous) | `memory_write` | 5 sites (pipeline.py:2968, 2971, 4825, 5718, 5720) |
| H9 | `core/state.py::write` (wrap exit) | Emit after the atomic-replace dashboard write | `state_write` | 8 sites (pipeline.py:839, 5935, 6027, 6109, 6172, 6179, 6415, 7684) |
| H10 | `core/audio.py::speak` + `speak_stream` (wrap exit) | Emit after TTS playback finishes (or after stream-end for `speak_stream`) | `tts_out` | 30+ sites |
| H11 | `pipeline._open_session` + `_close_session` (wrap exit) | Emit lifecycle event after the store mutation completes | `session_lifecycle` | 6 open + 2 close = 8 sites |

**Plumbing summary:** ~11 module-boundary edits (most are 1-4 lines each
to call `emit(...)` after the existing return). Zero new logic in
pipeline.py — pipeline.py callers don't need to know event_log exists.

**Auditor note on H7:** the `tool_call → tool_result` pair is the
canonical use case for `parent_event_id` (D4). The wrapper captures the
DB-assigned id of the `tool_call` event and threads it through to the
`tool_result` emission. Implementation: producer.emit() returns the
assigned id; the wrapper stores it in a local before calling the handler.

---

## Deliverable 4 — D-decisions to surface BEFORE Plan v1

### D1 — Storage location: brain.db vs new meta.db vs per-session JSONL

| Option | Pros | Cons |
|---|---|---|
| (a) brain.db now, future-migrate to meta.db when P1.A8 lands | Zero new infra; P0.9 MIGRATIONS plumbing applies cleanly; events colocate with knowledge graph for cross-querying | Adds non-knowledge data to brain.db; migration cost later |
| (b) Create meta.db now | Architecturally clean; ready for P1.A8 split | Bundles two refactors (event log + DB split) in one PR — spec-first discipline violated |
| (c) Per-session JSONL files (no SQLite) | Replay-friendly file-per-session; trivially debuggable; no DB lock contention | Loses SQL queries (cross-session analysis, index lookups); separate file lifecycle to manage; rotation needed |

**Recommendation: (a).** Brain.db is the right initial home. Move to
meta.db when P1.A8 lands; that PR owns the migration. Same shape as P0.9
ledger-bootstrapping which already handles cross-DB schema evolution.

### D2 — Payload serialization: JSON vs MessagePack vs hybrid

| Option | Pros | Cons |
|---|---|---|
| (a) JSON | Human-readable; grep-friendly; debuggable from sqlite CLI; no new deps | ~3-5× larger payloads; ~2× slower serialize/deserialize |
| (b) MessagePack | Compact (~30-50% of JSON size); fast; supports binary blobs natively | New `msgpack` dep; opaque in CLI tools; needs base64 wrap or BLOB column |
| (c) JSON in dev, MessagePack in prod (toggle via env) | Speed when needed + readability when debugging | Two code paths; replay tool needs to handle both; cognitive overhead |

**Recommendation: (a) JSON for P0.0.7.** Readability beats speed at
foundation stage. The event_log replay tool's primary user is the
developer + auditor; both want grep-able payloads. Profile after
deployment; switch to MessagePack only if dimensional storage growth
becomes a real concern.

### D3 — event_type enum: open string vs closed set vs invariant-locked closed

| Option | Pros | Cons |
|---|---|---|
| (a) Open string set | Add types without code change | Typos silent; replay tool can't dispatch on unknown types |
| (b) Closed set (frozenset in types.py) | Typos caught at producer site | New event types require code change to register |
| (c) Closed set + structural invariant test (`test_every_producer_emits_known_event_type`) — same shape as P0.10 RULES-ordering or P0.11 atomic-replace | Same as (b) + CI-enforced that producers stay in sync with the registered set | One extra structural test |

**Recommendation: (c).** Closed set + invariant test. The set lives at
`core/event_log/types.py::EVENT_TYPES`. Structural test parses
`core/event_log/producer.py` and asserts every `emit(...)` call site
uses a literal `event_type` value from `EVENT_TYPES`. Same shape as
P0.10's `EXPECTED_RULES_BY_BAND` lock.

### D4 — parent_event_id semantics: full DAG vs flat sequence vs natural-pair

| Option | Pros | Cons |
|---|---|---|
| (a) Full causal DAG — every derived event links to its cause | Rich replay reconstruction; supports complex queries | Hard to define "cause" for many events; cognitive overhead; performance hit (extra producer cost per emission) |
| (b) Flat sequence — `parent_event_id` always NULL | Simplest model; rely on `(ts, session_id)` for ordering | Loses tool_call/tool_result correlation; replay must heuristic-match pairs |
| (c) Natural-pair chain — explicit linking only for pairs where causality is unambiguous (`tool_call → tool_result`, `audio_in → identity_claim`, `identity_claim → routing_decision`) | Captures the load-bearing causal edges; everything else is NULL | "Natural pairs" list needs explicit documentation; potential drift if new pairs land later |

**Recommendation: (c).** Document the natural-pair set explicitly in
`core/event_log/types.py` (NATURAL_PARENT_PAIRS frozenset). The H7 hook
already needs `parent_event_id` for tool_call/result. Other pairs land
in Plan v1's spec.

### D5 — Backpressure semantics: lossy / blocking / unbounded

| Option | Pros | Cons |
|---|---|---|
| (a) Lossy bounded queue (drop on full + counter) | Producer never blocks; bounded memory; observable degradation | Replay may have gaps under load |
| (b) Block producer if queue full | No data loss | Producer blocks → pipeline blocks → user-visible audio dropouts |
| (c) Unbounded queue | No drops, no blocks | Unbounded memory growth on writer failure |

**Recommendation: (a) — spec-locked.** 10000-event bounded
`asyncio.Queue`. Drop counter exposed via
`core.event_log.producer.get_drop_count()`. Health log emission (P0.0
Wave5 health log infra) extended to include event-log drop count; alert
if non-zero. Same observability shape as `_faiss_degraded` / P0.5
sentinel.

### D6 — Schema version evolution: per-event_type vs global vs none

| Option | Pros | Cons |
|---|---|---|
| (a) Per-event_type `schema_version`; replay dispatches on `(event_type, schema_version)` | Independent evolution; old logs replayable; clean upgrade path | Schema version registry needed; dispatch tables grow |
| (b) Global schema_version; bumping any type bumps all | Simple | All-or-nothing upgrade; old logs become unparseable after any change |
| (c) No version; assume forward-compat | Zero overhead | Breaks the first time any payload field is renamed |

**Recommendation: (a).** Per-event_type versioning. The
`schema_version` column starts at 0 for v1.0 payloads. Bumping happens
in the producer dataclass + a version-handler dict in the replay tool.
Same shape as the classifier_scenarios.db migration ledger (Spec 1).

### D7 — Producer wiring: per-call-site / boundary-function / decorator / sidecar

| Option | Pros | Cons |
|---|---|---|
| (a) Inline emit at every call site (~50+ edits to pipeline.py) | Maximum explicitness; pipeline.py owns the instrumentation | Huge edit surface; cognitive cost; concentration risk if a site is missed |
| (b) Boundary-function wrap (~11 edits to core/*) | Minimal pipeline.py churn; per-module ownership stays intact | Mixes concerns inside core modules slightly |
| (c) Decorator pattern (`@instrument("audio_in")`) | Declarative; one-line at each boundary fn | Decorator stacking with `@asyncio.coroutine` + existing patterns gets hairy |
| (d) Sidecar — pipeline.py orchestrates emissions after each major block | Centralized control; no core/* edits | Reintroduces the per-call-site problem; defeats the modular pre-extraction goal |

**Recommendation: (b) boundary-function wrap** for module-owned events
(audio_in, identity_claim, presence_state, routing_decision,
intent_classification, memory_write, state_write, tts_out) +
**(d) sidecar** for pipeline-orchestrated events
(tool_call/tool_result via H7, session_lifecycle via H11,
vision_frame via H2 inside `_background_vision_loop`). Total ~11
edits, distributed sensibly.

### D8 — Test/dev mode: always-on / opt-in / in-memory

| Option | Pros | Cons |
|---|---|---|
| (a) Always on in tests; same code path as prod | Matches prod behavior; replay tested by production code | Slow test suite; disk I/O on every test |
| (b) Off by default in tests; opt-in via env var (EVENT_LOG_ENABLED=1) | Fast tests; explicit opt-in for replay-fixture tests | Production code path under-tested |
| (c) In-memory SQLite when EVENT_LOG_TESTING=1; off otherwise; on in prod | Speed + production fidelity at the cost of some path-coverage divergence | Two code paths to maintain |

**Recommendation: (b) for fast CI + (c) for replay-harness fixtures.**
Fast CI runs with EVENT_LOG_ENABLED=0 (producer is a no-op); replay-
fixture tests set EVENT_LOG_TESTING=1 to get in-memory SQLite +
event_log writing. The replay-fixture pytest fixture handles the env
var lifecycle and provides a captured-session sample.

---

## Decisions surfaced for Plan v1 review

Before code, architect + auditor lock D1-D8 above. Plan v1 then enumerates:

- **DB choice (D1):** brain.db now, P1.A8 migrates to meta.db
- **Serialization (D2):** JSON v1.0, MessagePack candidate for P1.A16
- **event_type enum (D3):** closed set + structural test
- **Causality (D4):** natural-pair chain; document `NATURAL_PARENT_PAIRS`
- **Backpressure (D5):** lossy bounded queue, drop counter, health-log integration
- **Versioning (D6):** per-event_type schema_version
- **Wiring (D7):** boundary-wrap (8 hooks) + sidecar (3 hooks); ~11 total
- **Test mode (D8):** opt-in via env var; in-memory SQLite for replay fixtures

Migration plumbing follows P0.9's 5-tuple pattern:

```python
# core/brain_db_migrations.py (or core/meta_db_migrations.py at P1.A8)
def _m_NNNN_create_event_log_apply(conn): ...
def _m_NNNN_create_event_log_verify_post(conn): ...
def _m_NNNN_create_event_log_verify_present(conn): ...
MIGRATIONS.append((NNNN, "create event_log table", _m_NNNN_..._apply,
                   _m_NNNN_..._verify_post, _m_NNNN_..._verify_present))
```

---

## Acceptance gate check

| Item | Status |
|---|---|
| `tests/p0_07_event_boundary_audit.md` exists with all deliverable sections populated | ✅ |
| Producer-boundary enumeration (Deliverable 1) covers every input crossing the runtime boundary, count = 12 distinct event types | ✅ |
| Event payload shapes (Deliverable 2) specified per event type; existing dataclasses (IdentityClaim/PresenceState/RoutingDecision) re-used verbatim, 3 sites | ✅ |
| Producer call sites (Deliverable 3) enumerated with ~11 instrumentation hooks covering ~50+ pipeline.py call sites | ✅ |
| D-decisions (Deliverable 4) — D1-D8 surfaced with 2-4 options each + recommendation | ✅ |
| `git status core/` shows zero modifications (Phase 0 discipline — same as P0.9 + P0.10 audits) | ✅ |

---

## What this audit does NOT do

- Does not implement `core/event_log/producer.py` or `core/event_log/types.py`
- Does not modify any production code (zero edits to pipeline.py / core/*)
- Does not write the migration (5-tuple lands in Plan v1's code phase)
- Does not write the replay CLI (`tools/replay_session.py`)
- Does not write the pytest fixture for replay-based regression tests
- Does not lock D1-D8 — that's architect + auditor's call after reviewing this audit

All implementation lands in Plan v1 after the D-decisions are locked.

---

## Bookmarked follow-ups discovered during audit

These surfaced while grep'ing — not P0.0.7 scope but worth flagging:

1. **`action_proposal` / `action_result` (spec list)** — no concept in
   the codebase today distinct from `tool_call`. May appear when P0.S1
   ships robotics actions OR when P1.A4 service decomposition introduces
   an action layer. Document as TBD in Plan v1; don't introduce
   speculatively.
2. **TTS truncation policy (event 11)** — `speak()` paths log full TTS
   text today via the existing `[Audio] TTS:` log line. The event_log
   should truncate to 500 chars + sha256 the full text to prevent DB
   bloat on long greetings. Truncation policy spec'd in Plan v1.
3. **`anti_spoof_*` fields on `vision_frame` event** — captured per
   reviewer's note that "anti-spoof regression fixtures (record a
   session, replay with photo-replay attempts, assert anti-spoof fires)
   are trivial when replay infrastructure exists." Including these
   fields in `VisionFrameEvent`'s payload makes P0.S1 a pure replay-test
   exercise.
4. **`raw_segment_scores` on `identity_claim`** — already in the existing
   dataclass; verify it serializes cleanly to JSON (tuples + None values).
5. **Audio waveform storage** — we deliberately do NOT log full audio
   buffers (DB bloat + privacy). Replay relying on identity-claim
   re-derivation from audio needs the producer to ALSO write WAV files
   keyed by `audio_hash`. Separate concern from event_log; spec'd
   separately if/when P0.S1 needs it.
