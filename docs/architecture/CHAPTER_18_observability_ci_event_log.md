> **CHAPTER 18 — Observability + Tiered CI + Event Log Foundation** | Sourced from `everything_about_system.md` §300-321 (verbatim mechanical extraction per Plan v2 §1.6 section-number stability invariant).

---

## 300. The Health-Pulse Cadence

`core/health.py` emits a one-line system pulse every `HEALTH_LOG_INTERVAL_SECS=300s` (5 minutes). The pulse is a passive observability signal — operators can grep `terminal_output.md` for `[Health]` lines and see the system's state over time without needing a dashboard.

`_emit_health()` runs the gather operation in an executor (`loop.run_in_executor(None, gather_health_snapshot)`) so the snapshot doesn't block the asyncio loop. The format helper (`format_health_line`) builds a single ≤200-character line; the alerts helper (`format_health_alerts`) emits zero or more `[Health-Alert]` lines for non-healthy conditions.

The first emission fires immediately at boot (not at the first 5-minute mark) so operators see the baseline state right away. Both functions are wrapped in `try/except` with logged errors so a health-log bug can never break the production pipeline.

## 301. `HealthSnapshot` and the One-Line Format

The dataclass:

```python
@dataclass
class HealthSnapshot:
    timestamp: float
    active_sessions: int
    sessions_by_type: dict[str, int]
    persons_count: int
    total_face_embeddings: int
    knowledge_active_rows: int
    shadow_persons_count: int
    classifier_scenarios_active: int
    classifier_scenarios_quarantined: int
    cloud_state: str
    active_disputes: int
    unresolved_watchdog_alerts: int
    last_dream_run_seconds_ago: Optional[float]
    thin_voice_galleries: int
    # P0.0.7 D8.1 additions:
    event_log_drops: int = 0
    event_log_emit_failures: int = 0
```

The one-line format prints time + the most-actionable fields:

```
[Health] 14:23 sessions=2(best_friend=1,known=1) persons=4 emb=120 knowledge=842 shadow=3 scenarios=2071/0 cloud=ONLINE disputes=0 watchdog=0 dream=8m_ago thin=0
```

Plus the event-log fields (event_log_drops + event_log_emit_failures) appended when either is non-zero (P0.0.7 D8.2 conditional surfacing, see §321).

The `format_health_alerts` function emits per-condition `[Health-Alert]` lines:
- Active disputes (one per disputed person, with the dispute timestamp)
- Unresolved watchdog alerts (one per unresolved alert, with severity)
- Thin voice galleries (one per person whose voice profile is under `VOICE_ACCUM_MATURE_SAMPLE_COUNT`)
- Event log drops + emit failures (P0.0.7 D8.3)

The alerts are designed to be greppable: `grep [Health-Alert] terminal_output.md` gives an operator a complete list of all active issues without needing to read the per-turn logs.

## 302. Three-Level Disk Alerts with Idempotent Transitions

`core/disk_monitor.py` watches three paths: `faces/`, `data/`, and the project root. Each is sampled via `shutil.disk_usage` plus a per-directory recursive walk for size aggregation. The three thresholds:

- `DISK_ALERT_WARNING_PCT = 80` — first alert level (warning)
- `DISK_ALERT_CRITICAL_PCT = 90` — second level (critical, escalated)
- `DISK_ALERT_BLOCKER_PCT = 95` — third level (blocker, system may stop accepting writes soon)

Threshold crossings are **idempotent**: a per-path module-level state dict `_last_disk_alert_level` tracks the most-recent alert level for each path. When the current usage moves to a higher level, the alert fires (one log line + one `WatchdogAgent.report_disk_threshold(...)` call). When usage stays at the same level, no re-fire. When usage drops (e.g. after a cleanup), the level is reset.

This is the same idempotent-transitions pattern P0.6.6's `transition_to_online` uses (§256). The WatchdogAgent receives at most one report per level transition; it persists to `brain.db.watchdog_alerts` (Session 42's table) with `severity ∈ {warning, critical, blocker}`.

The disk-monitor + health-monitor are emitted together every 5 minutes from `_emit_health()`. Operators see the full state in one block. The combined Wave 5 work (Items 19+20) added +14 tests (8 health + 6 disk) and provided passive observability for two failure surfaces that previously had no observability at all.

---

# Part XLVII — Conversation Hygiene and Memory Consolidation (Wave 6)

## 303. Hard-Delete Pruning of Invalidated Knowledge

Pre-Wave-6, the `knowledge` table on `brain.db` accumulated rows indefinitely. The `invalidated_at` timestamp marked rows as no-longer-valid (set by `ContradictionAgent.check` when a new fact replaced an old one) but the rows themselves stayed in the table forever. After a year of use, the table could grow to 100k+ rows of historical invalidations — slow queries, large backup files, increasing index sizes.

`BrainDB.hard_delete_invalidated_knowledge(cutoff_days, now)` deletes rows where `invalidated_at < cutoff_ts` (`cutoff_ts = now - cutoff_days * 86400`). The retention default is `KNOWLEDGE_HARD_DELETE_DAYS = 90` — invalidated rows from the last 3 months stay in case retroactive analysis needs them; older ones are gone.

Wired into the dream loop (`_dream_loop` in `pipeline.py`) via `run_in_executor` so the bulk delete doesn't block the asyncio loop. The dream loop runs the hard-delete once per cycle (default every 5 minutes idle, or every 3 hours active). +3 tests in `tests/test_hard_delete_invalidated.py`.

## 304. SHA-256 Scene-Block Cache

`_build_scene_block(...)` (Part X §64) runs on every turn. Its inputs are 4 collections: `_active_sessions`, `_persons_in_frame`, `_unrecognized_tracks`, plus the `now` timestamp. Across turns these collections often don't change at all (a quiet room with one stable speaker stays stable for many turns). Rebuilding the scene block on every turn re-runs the dispute precedence logic, the visible-person enumeration, the voice-only-offscreen rendering, and the safety-flag aggregation. All wasted work when nothing has changed.

Wave 6 Item 23: the scene block now caches by **SHA-256 of all inputs**. The cache key is `sha256(json.dumps(canonical_inputs, sort_keys=True))`. On a cache hit, the previously-built block string is returned directly. On a miss, the block is built and cached under the new key.

The cache is owned by `pipeline.py` as a module-level dict; tested in `tests/test_scene_block_cache.py` via 4 source-inspection tests confirming the cache key contains the right input components, the cache hit path skips the build, the cache invalidates correctly on input change, and the cache survives across turn boundaries (cleared only on factory reset). Gated by `SCENE_BLOCK_CACHE_ENABLED = True` in `core/config.py`.

The empirical hit rate in normal use is ~60-80% (quiet room turns) and drops to ~10-20% in active multi-person rooms with changing visibility. The cumulative latency win is substantial; the cache cost is negligible (one SHA-256 + dict lookup per turn).

## 305. `conversation_log` Archival via ATTACH DATABASE

The `conversation_log` table on `faces.db` grew indefinitely (Session 24's `CONVERSATION_HISTORY_LIMIT=100` only limits in-memory load, not on-disk storage). After 6 months of use, `faces.db` could be 500+ MB just from conversation history. Vacuum + index rebuilds get slow; backups get large; the working set for hot queries (recent turns) is degraded by all the cold storage.

Wave 6 Item 21: archive old rows into a companion DB. The pattern:

- `CONVERSATION_ARCHIVE_ENABLED = True` and `CONVERSATION_ARCHIVE_AFTER_DAYS = 30` in `core/config.py`. Rows older than 30 days are eligible for archival.
- The companion DB is `faces_conversation_archive.db` (same directory, same schema, same WAL, same index `idx_conv_log_room`). Built on first archival run.
- `FaceDB.archive_old_conversation_log(cutoff_days, now)` uses `ATTACH DATABASE` + `BEGIN EXCLUSIVE` for atomic `INSERT INTO archive.conversation_log SELECT ... → DELETE FROM main.conversation_log WHERE ...`. The atomicity guarantees no rows are lost on crash mid-archival.
- `load_conversation_history()` and `search_conversation()` each open a short-lived connection to the archive DB (separate from the main FaceDB connection, to avoid ATTACH conflict with the write path) and UNION-merge results with the primary DB.

Wired into the dream loop alongside the hard-delete (§303). The two run sequentially: hard-delete invalidated knowledge, then archive old conversation_log rows. +6 behavioural tests in `tests/test_conversation_archive.py`: moves old rows, keeps recent, idempotent, correct count, load_history includes archive, search includes archive.

The combined effect of P0.5/P0.X (atomicity) + P0.9 (versioning) + Wave 6 (archival) is that the persistence layer has become significantly more durable, observable, and bounded.

---

# Part XLVIII — Tiered CI Scaffold and S2 Deferral Tripwire (P0.0 + P0.0.1 + P0.0.2)

## 306. Three Workflows — Fast, Slow, Security

P0.0 shipped the project's first CI configuration. Three GitHub Actions workflows in `.github/workflows/`:

| Workflow | Trigger | Target | Scope |
|---|---|---|---|
| `fast.yml` | every push + PR | ≤5 min | `pytest -m "not slow and not network and not models"` + ruff + mypy permissive |
| `slow.yml` | nightly + manual via `workflow_dispatch` | unconstrained | full suite, HF model cache via `actions/cache`, `--run-network` when `TOGETHER_API_KEY` secret is set |
| `security.yml` | weekly + on `requirements.txt` change | quick | `pip-audit` + Trivy filesystem scan with SARIF upload to GitHub Security tab |

The split fixes the chicken-and-egg problem of CI for a project with heavy local-model dependencies. Fast CI runs on every PR and catches structural regressions in seconds. Slow CI runs nightly with model downloads + network access for full coverage. Security CI runs weekly to catch upstream vulnerabilities without paying the cost on every PR.

## 307. Pytest Markers and the Infra-Debt Allowlist

`pytest.ini` extended with the `models` marker (alongside the pre-existing `slow` and `network` markers). 15 tests now carry `@pytest.mark.slow @pytest.mark.models` so fast CI skips them — these are the SpeechBrain / pyannote / faster-whisper / torchaudio integration tests that need the heavyweight model assets.

The infra-debt allowlist lives in `tests/test_infra_debt_allowlist.py::INFRA_DEBT_FAILURES`. Currently 9 entries: 1 torchaudio DLL crash + 1 SpeechBrain logger suppression + 6 pyannote diarize tests + 1 pre-existing ECAPA-DLL diarize test. Each entry is a `(test_id, rationale)` tuple documenting why the test is on the allowlist.

The allowlist itself is a rationale-registry, not a behavior-control. The actual disposition on the tests is `@pytest.mark.xfail(strict=False, reason=...)` decorators applied in P0.0.2 (§309).

## 308. The S2 Tripwire and the Theater That P0.0.1 Closed

S2 is the "dashboard authentication" deferred item in the security backlog. The deferral premise: "the dashboard is bound to `127.0.0.1`, no LAN exposure today, ship auth (S2) later when the dashboard becomes LAN-accessible". A deferred item is safe IF AND ONLY IF the premise it deferred on continues to hold.

`tests/test_dashboard_bind_tripwire.py` is the structural tripwire that locks the precondition. The test scans `Kara-OS-dashboard/package.json` for the `dev` and `start` scripts and asserts they're explicitly bound to localhost.

**The theater P0.0 originally shipped:** the v1 tripwire asserted *absence* of `--hostname 0.0.0.0` (any explicit LAN bind), on the false premise that "no explicit LAN bind" meant "localhost". Next.js's actual behavior when `--hostname` is unspecified is to bind to `0.0.0.0` (LAN-accessible). The absence-of-flag check was theatrical — the dashboard was LAN-accessible whenever `npm run dev` was running, and the tripwire happily passed.

P0.0.1 closed the gap. The fix (2 lines in `Kara-OS-dashboard/package.json`): `dev` and `start` scripts now contain `--hostname 127.0.0.1 --port 3000` explicitly. The tripwire was tightened to REQUIRE the explicit flag rather than absence-of-LAN. The test was renamed from `test_dashboard_package_json_scripts_dont_bind_lan` to `test_dashboard_package_json_scripts_explicitly_bind_localhost`, asserting `_find_explicit_hostname_in_command` returns a value AND that the value is in `{127.0.0.1, localhost, ::1}`.

The empirical lesson banked in §328: **tripwires must catch the actual failure mode the deferral leaves unsafe, NOT just the symbolic version that pattern-matches the surface description**. P0.0.1 is one of the 3 instances on the track record.

## 309. P0.0.2 — V1 xfail Bundling for Infra-Debt Tests

The 8 infra-debt failures on the allowlist now carry `@pytest.mark.xfail(strict=False, reason=...)` decorators with explicit P0.0.2 reason strings cross-referencing the allowlist. `strict=False` means an unexpected PASS surfaces as XPASS (notable, doesn't break CI) — the signal that infra debt was resolved.

Slow CI now reports `715 passed, 9 xfailed, 0 failed` instead of `715 passed, 8 failed`. The 9th xfail is the pre-existing ECAPA-DLL diarize.

New structural lock `tests/test_infra_debt_allowlist.py::test_xfail_decorators_align_with_allowlist` AST-scans `test_pipeline.py` and asserts every name in `INFRA_DEBT_FAILURES` carries a `pytest.mark.xfail` decorator. The test catches half-fixes — removing the decorator without removing the allowlist entry, or vice versa.

The discipline this lock encodes: the allowlist and the xfail decorators are *dual artifacts of the same disposition*. When infra debt is genuinely fixed, both must be removed in the same commit. When new infra debt is added, both must be added in the same commit. The structural lock prevents either half from drifting.

Deliberate-regression check confirmed (induction-surfaces-invariant-gaps discipline): (a) forced one xfail test to trivially pass → XPASS surfaced cleanly + suite still green; (b) removed an xfail decorator → alignment test fired with full S2-style remediation message; (c) restored → alignment test passes.

---

# Part XLIX — Event Log and Replay Harness (P0.0.7)

## 310. Why Event-Sourcing the Boundary

P0.0.7 ships the system's first event-sourcing layer. Every input crossing the runtime boundary (microphone audio → audio_in event; camera frame → vision_frame event; identity claim → identity_claim event; routing decision → routing_decision event; ...) emits a typed event into a SQLite table that can be replayed later for debugging or regression testing.

The motivation is concrete: the next P0 work (P0.S1 — anti-spoof on every face match) needs regression tests that exercise the anti-spoof gate on a *captured* sequence of camera frames + voice signals + routing decisions. Without event-sourcing, those tests would need live camera input (expensive, flaky, non-deterministic). With event-sourcing, the test loads a captured event chain from a fixture, replays it through the system, and asserts the anti-spoof gate behaves correctly.

The architecture is plain: a `event_log` table on `brain.db` with rows `(id, ts, session_id, room_session_id, event_type, schema_version, payload, parent_event_id)`, an async producer that emits events, a read-only CLI for inspecting the log, scenario-builder fixtures for tests, and health-log integration so degradation is observable.

## 311. The 12 Payload Types

`core/event_log/types.py` defines 12 dataclasses, one per event type:

| Event type | Payload class | What it captures |
|---|---|---|
| `audio_in` | `AudioInPayload` | Microphone audio chunk + STT text + language + duration |
| `vision_frame` | `VisionFramePayload` | Camera frame metadata + frame_id + frame_path (NOT inline bytes) + **anti_spoof_live** + **anti_spoof_score** (the load-bearing P0.S1 fields) |
| `identity_claim` | `IdentityClaimPayload` | Voice-channel `IdentityClaim` (Part XXXII §199) flattened to JSON |
| `presence_state` | `PresenceStatePayload` | Vision-channel `PresenceState` (Part XXXII §200) flattened to JSON |
| `routing_decision` | `RoutingDecisionPayload` | Reconciler's `RoutingDecision` + `utt_band` tag |
| `intent_classification` | `IntentClassificationPayload` | Classifier output (graph or LLM mode) |
| `tool_call` | `ToolCallPayload` | LLM-proposed tool name + args + person_id |
| `tool_result` | `ToolResultPayload` | Tool handler's return status |
| `memory_write` | `MemoryWritePayload` | Conversation log write |
| `state_write` | `StateWritePayload` | `state.json` IPC write |
| `tts_out` | `TtsOutPayload` | TTS synthesis trigger + clean text |
| `session_lifecycle` | `SessionLifecyclePayload` | Open / close event + pid + name + person_type |

`EVENT_TYPES = frozenset(...)` enumerates the 12 names. `SCHEMA_VERSIONS = {(event_type, schema_version): payload_class}` — the dispatch table keyed on `(event_type, schema_version)` (§313).

Every payload class has a `from_json_dict(json_dict, schema_version)` classmethod that reconstructs the dataclass from the deserialised JSON. This is the C2 replay-deserialization contract — the CLI and the replay tests both consume events via this contract.

## 312. `NATURAL_PARENT_PAIRS` and Causal-Chain Auto-Resolution

Some event sequences have causal structure. A tool_result is caused by a tool_call. An identity_claim is caused by an audio_in. A routing_decision is caused by an identity_claim. Linking child events to their parents lets the replay tool render natural chains as trees.

`NATURAL_PARENT_PAIRS = frozenset({...})` is the registry of allowed (child_type, parent_type) edges:

```python
NATURAL_PARENT_PAIRS = frozenset({
    ("tool_result", "tool_call"),
    ("identity_claim", "audio_in"),
    ("routing_decision", "identity_claim"),
})
```

The producer auto-resolves parent_event_id when emitting a child event: it consults `_recent_parent[session_id]` (§315) for the most recent event of the matching parent_type, sets `parent_event_id` to that event's id, and falls back to NULL if no parent is in the cache. Manual override via the `parent_event_id` kwarg is supported but rare.

Only the natural-pair edges are auto-resolved. Other causal relationships (memory_write → routing_decision, tts_out → routing_decision, intent_classification → audio_in) are tracked elsewhere or simply unwired in the current schema. The natural-pair set is a conservative starting point; additional edges land when replay analysis surfaces concrete need (§339).

## 313. `_PAYLOAD_CLASSES` and the Deserialization Contract

`_PAYLOAD_CLASSES: dict[tuple[str, int], type] = {(event_type, schema_version): payload_class, ...}` is the dispatch table. The CLI and the replay tests look up `(event_type, schema_version)` in the table, call `cls.from_json_dict(payload_dict, schema_version=schema_version)` to reconstruct the typed dataclass, and use the typed object for assertions / rendering.

Schema versioning is per-event-type. A future change to `IdentityClaimPayload` (e.g. adding a new field) ships as `IdentityClaimPayloadV2` with `schema_version=2`. The dispatch table gains a `("identity_claim", 2)` entry pointing to the new class. Old rows in the DB (with `schema_version=1`) still deserialise correctly via the old class. The replay CLI handles both versions transparently.

`test_d_schema_version_dispatch_keys_on_event_type_and_version` in `tests/test_event_log_replay.py` verifies the dispatch behavior: a mock `("tts_out", 2)` → `TtsOutPayloadV2` entry added to the dispatch table; v1 rows still resolve to the original class. The CLI's fallback path handles unknown schema_versions by falling back to truncated JSON dump (no crash).

## 314. Producer Anatomy — `emit`, `emit_sync`, `safe_emit_sync`

Three producer functions in `core/event_log/producer.py`:

- **`async def emit(event_type, payload, *, session_id, room_session_id, parent_event_id)`** — primary async path. Builds the row dict, resolves parent_event_id via `_recent_parent` cache, JSON-serialises the payload, enqueues onto the bounded `asyncio.Queue`. Returns the event_id assigned by the writer task. Used in async contexts.
- **`def emit_sync(event_type, payload, ...) -> int`** — sync wrapper for callers in non-async contexts (database trigger callbacks, signal handlers). Submits the emit task to the running loop via `asyncio.run_coroutine_threadsafe` and awaits its result. Same contract as async `emit`.
- **`def safe_emit_sync(event_type, payload, ...) -> Optional[int]`** — swallowing wrapper around `emit_sync`. Catches every exception, increments `_safe_emit_failure_count`, logs a `[EventLog] WARN` line (rate-limited to first 3 failures), returns None. **The single annotated except block here satisfies P0.4's silent-except invariant for the entire 12-call-site hook surface.**

The `safe_emit_sync` consolidation is the **developer-improves-on-spec** 5th instance banked in §327. The auditor's original P0.4 remediation prescribed annotating the 12 per-call-site try/except blocks with `# OPTIONAL:`. The developer's response: consolidate to a single helper with one annotated except — 12 violations → 1 annotated except + 12 unannotated call sites; future hooks automatically inherit the swallow-discipline.

## 315. The `_recent_parent` Writer-Task-Scope Cache

`_recent_parent: dict[str, dict[str, int]]` — keyed by `session_id`, value is a dict from `event_type` to the most-recent event id of that type within the session. Mutated only in the writer task (not in the producer's async path) to keep the cache mutation single-threaded.

When a new event is written, the writer task updates `_recent_parent[session_id][event_type] = new_event_id`. The cache is cleared on `session_lifecycle=close` to prevent cross-session pollution (an audio_in from session A should never resolve to an identity_claim from session B).

The C1 invariant (`_recent_parent` writer-task-scope-only) is enforced by an AST scan in `tests/test_event_log_invariants.py` that asserts no production code outside the writer task mutates `_recent_parent`. The test catches future refactors that move parent resolution into the async path (which would introduce a race).

## 316. Bounded Queue and the D5 Lossy-Backpressure Decision

The producer's `asyncio.Queue` has `maxsize=10000`. Above 10000 unprocessed events, `queue.put_nowait()` raises `asyncio.QueueFull`. The producer catches this, increments `_drop_count`, and logs a `[EventLog] WARN: queue full, dropping event` line (rate-limited).

The design decision (D5 in the plan): **lossy backpressure under sustained overload**. The alternative (block on `queue.put`) would have made every producer-hook synchronous-with-DB-writes, which would break the "producer hooks never affect production behavior" contract.

The empirical assumption is that 10000 unprocessed events represents minutes of normal traffic. If the writer task falls behind by more than that, the issue is structural (DB lock, disk full) and dropping events is the safe choice — observability degrades gracefully, production behavior continues.

`get_drop_count()` exposes the cumulative drop count for health-log integration (§321). The drop counter is the observability channel; there is NO `event_log_dropped` event emitted in the queue (D5 circular-dependency guard — an "I dropped an event" event would itself be dropped under backpressure).

## 317. The 11 Producer Hooks at 12 Sites

| Hook | Site | Event type |
|---|---|---|
| H1 | `core/audio.py::listen_and_transcribe` | `audio_in` |
| H2 | `pipeline._background_vision_loop` (sidecar + JPEG storage) | `vision_frame` |
| H3 | `core/voice_channel.py::identify_speaker` | `identity_claim` |
| H4 | `core/vision_channel.py::observe_scene` | `presence_state` |
| H5 | `core/reconciler.py::reconcile` (+ utt_band tag) | `routing_decision` |
| H6 | `core/brain.py::_classify_intent_smart` (via `_emit_intent_classification_safe`) | `intent_classification` |
| H7 (×2) | `pipeline._execute_tool` (entry + exit) | `tool_call` + `tool_result` |
| H8 | `core/db.py::FaceDB.log_turn` | `memory_write` |
| H9 | `core/state.py::write` | `state_write` |
| H10 | `core/audio.py::speak` + `speak_stream` (via `_emit_tts_event_safe`) | `tts_out` |
| H11 | `pipeline._open_session` + `_close_session` (via `_emit_session_lifecycle_safe`) | `session_lifecycle` |

The D7 N=1 invariant (exactly-one-producer-per-event-type) is enforced by AST scan in `tests/test_event_log_invariants.py`. The scan walks all `safe_emit_sync(...)`, `emit_sync(...)`, and `emit(...)` calls in the codebase, groups them by the `event_type` literal argument, and asserts exactly one production location per type. The `_EMIT_CALL_NAMES = frozenset({"emit", "emit_sync", "safe_emit_sync"})` recognition set was extended to include `safe_emit_sync` at Step 5 polish.

## 318. `_m_0012_create_event_log_*` Migration

The schema migration that creates the `event_log` table is registered at version 12 in `core/brain_db_migrations.py`. P0.9 5-tuple shape:

```python
(12, "Create event_log table for P0.0.7 event-sourcing foundation",
 _m_0012_create_event_log_apply,
 _m_0012_create_event_log_verify_post,
 _m_0012_create_event_log_verify_present)
```

`apply_fn` creates the `event_log` table + 3 indexes: `idx_event_log_ts` (chronological queries), `idx_event_log_session` (per-session filter), `idx_event_log_room` (per-room filter). The indexes are tuned for the replay CLI's most-common filter compositions.

`verify_post_fn` asserts the table + all 3 indexes exist after `apply`. `verify_present_fn` returns True if the table already exists (used by bootstrap on legacy DBs that may have manually-applied earlier versions).

## 319. The Read-Only Replay CLI

`tools/replay_session.py` (~410 LOC) is the operator-facing CLI for inspecting the event log. Read-only by design: opens the DB via `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`, never writes, never initialises the producer. Safe to run against a live production DB.

Filter flags compose with AND semantics:
- `--session <id>` — per-session filter
- `--room <room_id>` — per-room filter
- `--type <event_type>` — filter to one event_type (closed-set choices via argparse)
- `--since <offset>` — Unix timestamp / ISO-like string / duration suffix (`1m`/`30m`/`1h`/`24h`/`7d`)
- `--limit N` — default 200, `0` = unbounded
- `--no-tree` — disable parent-chain tree rendering (flat output for grep/pipe use)
- `--raw-payload` — print full JSON payload below each line (debug mode)

Tree rendering: events with `parent_event_id IS NOT NULL` where the parent is in the rendered window get a `└─` indent prefix. Orphaned events (parent outside window) fall back to indent=0. Natural-pair chains (`tool_call → tool_result`, `audio_in → identity_claim → routing_decision`) render as causality trees.

UTF-8 stdout hygiene: `_ensure_utf8_stdout()` reconfigures stdout to UTF-8 at startup so the `→` and `└─` characters render on Windows cp1252 terminals. Fallback is wrapped in `# CLEANUP:` annotated except (P0.4 compliant).

Defensive UX: missing DB → clear error pointing at `--db <path>` flag; missing `event_log` table → clear error pointing at the P0.0.7 migration prerequisite; corrupt/unknown payload → fall back to truncated JSON dump (line still renders, no crash).

## 320. Reusable Scenario Fixtures for P0.S1+

`tests/fixtures/event_log_fixtures.py` (~520 LOC) ships 4 scenario builders that compose realistic event chains for use in tests:

- **`build_greeting_flow(session_id, pid, ...)`** — clean known-person turn: session_lifecycle=open → audio_in → identity_claim → routing_decision → intent_classification → tool_call → tool_result → memory_write×2 → state_write → tts_out → session_lifecycle=close. Exercises all 3 natural-pair links.
- **`build_stranger_first_encounter(session_id, pid, ...)`** — stranger says system-name: 3× vision_frame frames (anti_spoof_live=True) → presence_state → audio_in → identity_claim (no match) → routing_decision (new_stranger) → session_lifecycle=open → intent_classification (assign_own_name).
- **`build_multi_person_room(room_id, session_a, session_b, ...)`** — 2 sessions interleaved with shared room_session_id: 2× open → session A turn → session B turn (switch_enrolled) → 2× close. Verifies room_session_id threading + per-session parent cache isolation.
- **`build_dispute_path(session_id, ...)`** — dispute-trigger pattern: low-confidence identity_claim → ambiguous routing_decision → intent_classification (assign_own_name) → tool_call (update_person_name) → tool_result (status=rejected, user-text gate refused).

The fixtures use `safe_emit_sync` (the production hook surface) so the natural-pair parent_event_id resolution + `_recent_parent` cache lifecycle exercises exactly as on a live boot.

The fixtures are parameterised top-level callables. P0.S1's anti-spoof regression tests will import `build_greeting_flow` etc. directly, compose chains, and verify the anti-spoof gate behaves correctly — without needing live camera input. This is the **D7.4 reusability** contract.

## 321. Health-Log Integration via Drop and Emit-Failure Counters

`HealthSnapshot` (Part XLVI §301) gained two new fields:

- **`event_log_drops: int`** — from `get_drop_count()`. Bounded-queue full events shed by backpressure.
- **`event_log_emit_failures: int`** — from `get_safe_emit_failure_count()`. Exceptions swallowed by `safe_emit_sync`.

`format_health_line` conditionally surfaces both — clean steady-state line stays clean when both are 0; only surfaces during degradation. `format_health_alerts` emits two distinct alerts with remediation pointers:

- **drops** → "writer task falling behind; bounded queue (10000) shedding envelopes. Investigate writer-loop / DB lock / disk-full."
- **emit_failures** → "safe_emit_sync swallowed exception(s) from a producer hook. Grep `[EventLog] WARN` in terminal_output for the type+message of the first 3 (rate-limited)."

The two alerts capture genuinely different failure modes (consumer falling behind vs producer-hook exception). Collapsing them to a single "event_log degraded" alert would force operators to grep both surfaces every time.

The D5 circular-dependency guard is preserved: counters ARE the observability channel; no self-emitting `event_log_dropped` event exists in the queue. The lazy import + `# OPTIONAL:` annotated except in `gather_health_snapshot` handles legitimate cases where `core.event_log.producer` isn't loaded (early boot, tests that mock out the package).

---

# Part L — Architectural Disciplines (The Named Doctrines)

