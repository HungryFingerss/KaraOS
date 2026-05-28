> **CHAPTER 10 — Schemas + Tests + Dashboard** | Sourced from `everything_about_system.md` §119-140b (verbatim mechanical extraction per Plan v2 §1.6 section-number stability invariant).

---

## 119. `faces.db` Schema

> **Migration model (2026-05-16).** All schema changes to `faces.db` now flow through `core/faces_db_migrations.py` (P0.9, Part XLII). Every historical schema mutation is a 5-tuple entry in the `MIGRATIONS` list with `(version, description, apply_fn, verify_post_fn, verify_present_fn)`. The migration runner consumes the list under `BEGIN IMMEDIATE` with the tightened S65 rollback discipline (Part XLII §282). Inline `ALTER TABLE` calls inside `_init_tables` have been deleted in P0.9 Phase 3 — the structural invariant `TestNoAlterTableOutsideMigrationModules` (Part XLII §284) rejects any future regression. `_init_tables` only does `CREATE TABLE IF NOT EXISTS` for the canonical shape; the migration runner applies the historical evolution on top.

### 119.1 `persons`

```sql
CREATE TABLE persons (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    enrolled_at      REAL NOT NULL,
    last_seen        REAL,
    photo_path       TEXT,
    person_type      TEXT NOT NULL DEFAULT 'known',    -- stranger/known/best_friend/disputed
    preferred_language TEXT DEFAULT 'en'
);
```

### 119.2 `embeddings`

See §37.1. Cross-storage atomicity with FAISS handled by the P0.5 SQL-first ordering + sentinel + boot reconciliation pattern (Part XXXVIII §243-§244).

### 119.3 `voice_embeddings`

See §43.1.

### 119.4 `conversation_log` (with P0.0.7 and Phase 3B columns)

```sql
CREATE TABLE conversation_log (
    id                INTEGER PRIMARY KEY,
    person_id         TEXT NOT NULL,
    role              TEXT NOT NULL,    -- user / assistant
    content           TEXT NOT NULL,
    timestamp         REAL NOT NULL,
    -- Phase 3B (Session 107 / Q3 hybrid history):
    room_session_id   TEXT,              -- room/group context identifier
    audience_ids      TEXT,              -- JSON array of pids allowed to see this turn
    -- Phase 3B addressing (Session 111):
    addressed_to      TEXT,              -- pid the assistant turn was addressed to
    FOREIGN KEY (person_id) REFERENCES persons (id) ON DELETE CASCADE
);
CREATE INDEX conversation_log_person_id_idx ON conversation_log(person_id);
CREATE INDEX idx_conv_log_room ON conversation_log(room_session_id, timestamp DESC);
```

Append-only. Disputed-session turns are skipped (Session 53 Finding B, Part XV §105).

### 119.5 `system_identity`

Singleton table holding the system's name (given by best friend during first-boot).

```sql
CREATE TABLE system_identity (
    singleton INTEGER PRIMARY KEY DEFAULT 1,
    name      TEXT NOT NULL DEFAULT 'Dog',
    updated_at REAL
);
```

### 119.6 `silent_observations`

Faces seen but never engaged (never said the system name).

```sql
CREATE TABLE silent_observations (
    id                INTEGER PRIMARY KEY,
    face_embedding    BLOB NOT NULL,
    first_seen        REAL NOT NULL,
    last_seen         REAL NOT NULL,
    count             INTEGER DEFAULT 1,
    matched_person_id TEXT,              -- NULL unless the observation was later linked
    ...
);
CREATE INDEX idx_silent_obs_last_seen ON silent_observations(last_seen);
```

Retention: `SILENT_OBS_RETENTION_DAYS=45`. Scan window for matching: `SILENT_OBS_SCAN_DAYS=7`.

### 119.7 `visitor_log`

Records stranger sessions for dashboard display.

```sql
CREATE TABLE visitor_log (
    id                INTEGER PRIMARY KEY,
    stranger_id       TEXT,
    first_seen        REAL NOT NULL,
    last_seen         REAL NOT NULL,
    turn_count        INTEGER DEFAULT 0,
    resolved_name     TEXT               -- set if they were later named
);
```

### 119.8 `schema_migrations` (P0.9 — versioned ledger)

```sql
CREATE TABLE schema_migrations (
    version      INTEGER PRIMARY KEY,
    description  TEXT NOT NULL,
    applied_at   REAL NOT NULL,
    is_initial   INTEGER NOT NULL DEFAULT 0    -- 1 = stamped at bootstrap on legacy DB
);
```

The migration ledger. `init_ledger` (Part XLII §278) creates it on a fresh DB; on a legacy DB it self-evolves (idempotent ALTER adding `is_initial` column). `bootstrap_ledger_if_unversioned` walks the `MIGRATIONS` list at boot and stamps each entry whose `verify_present_fn` returns True as `is_initial=1`, then `apply_migrations` runs pending entries in version order.

Boot observability emits one of three lines per DB:
- `[Schema] faces: bootstrap stamped baseline v=1 + N pre-existing migration(s) as is_initial=1 (legacy DB)`
- `[Schema] faces: ledger already versioned`
- `[Schema] faces: apply_migrations ran K pending`

### 119.9 Cascading deletes

Every person-child table uses `ON DELETE CASCADE`. Deleting a person row auto-deletes their embeddings, voice_embeddings, conversation_log. `delete_person` also does knowledge cleanup via `BrainDB.delete_person_data`.

### 119.10 Companion archive DB (`faces_conversation_archive.db`)

Wave 6 Item 21 (Part XLVII §305). Old `conversation_log` rows (`timestamp < now - CONVERSATION_ARCHIVE_AFTER_DAYS * 86400`) are atomically moved to a companion DB at `faces/faces_conversation_archive.db` via `ATTACH DATABASE` + `BEGIN EXCLUSIVE` + cross-DB `INSERT INTO archive.conversation_log SELECT ... → DELETE FROM main.conversation_log WHERE ...`. The companion DB carries the same schema (incl. the room_session_id / audience_ids / addressed_to columns) and the same `idx_conv_log_room` index.

`load_conversation_history` and `search_conversation` open a short-lived connection to the archive DB (separate from the main FaceDB write connection, to avoid ATTACH conflict) and UNION-merge results with the primary DB. The default retention is 30 days; older turns live in the archive forever (or until manual cleanup).

## 120. `brain.db` Schema

> **Migration model (2026-05-16 + 2026-05-18).** Same versioned-ledger pattern as faces.db (§119.8). brain.db's `MIGRATIONS` list lives in `core/brain_db_migrations.py`. The current top version is **12** — P0.0.7's `_m_0012_create_event_log_*` (Part XLIX §318) added the `event_log` table.

### 120.1 `knowledge`

The core knowledge graph table.

```sql
CREATE TABLE knowledge (
    id              INTEGER PRIMARY KEY,
    person_id       TEXT NOT NULL,
    entity          TEXT NOT NULL,
    attribute       TEXT NOT NULL,
    value           TEXT NOT NULL,
    confidence      REAL NOT NULL,
    valid_at        REAL NOT NULL,
    valid_until     REAL,
    invalidated_at  REAL,
    privacy_level   TEXT NOT NULL DEFAULT 'public',    -- Phase 3A.4.5
    embedding       BLOB,                              -- for semantic search
    -- ... plus several Phase 3A / 3B columns: status, source, last_confirmed_at
);
CREATE INDEX idx_knowledge_person_entity ON knowledge(person_id, entity);
CREATE INDEX idx_knowledge_attribute ON knowledge(attribute);
```

The `privacy_level` column was added in Phase 3A.4.5 (Session 95.3-95.6, 4-tier privacy model with `public` / `personal` / `household` / `system_only`). All retrieval paths route through `_visibility_clause` (Part XXV §152).

### 120.2 `prompt_prefs` (PromptPrefAgent)

Per-person communication preferences with semantic dedup. Carries an `embedding` BLOB column (L2-normalised E5 vector) plus a `sessions_seen` counter for auto-confirmation at 3+ sessions.

### 120.3 Knowledge-system support tables

Each agent has its own table — `agent_log`, `object_sightings`, `object_pattern_questions`, `episodes`, `presence_log`, `proactive_nudges`, `watchdog_alerts`, `social_mentions`, `predicate_stats`, `household_facts`, `inter_person_relationships`, `shadow_persons`, `room_summaries`. See Part XIV §84 for the full enumeration.

### 120.4 `schema_migrations` (same shape as §119.8)

Versioned-ledger pattern, identical schema. brain.db's ledger tracks 10 retrofitted historical migrations (v=2 through v=11) plus the P0.0.7 v=12.

### 120.5 `event_log` (P0.0.7, Part XLIX §318)

```sql
CREATE TABLE event_log (
    id                INTEGER PRIMARY KEY,
    ts                REAL NOT NULL,
    session_id        TEXT,
    room_session_id   TEXT,
    event_type        TEXT NOT NULL,                   -- one of the 12 EVENT_TYPES
    schema_version    INTEGER NOT NULL DEFAULT 1,
    payload           TEXT NOT NULL,                   -- JSON-serialised dataclass
    parent_event_id   INTEGER                          -- natural-pair parent linkage
);
CREATE INDEX idx_event_log_ts ON event_log(ts);
CREATE INDEX idx_event_log_session ON event_log(session_id, ts);
CREATE INDEX idx_event_log_room ON event_log(room_session_id, ts);
```

The event-sourcing foundation. Every input crossing the runtime boundary (microphone audio, camera frame, identity claim, routing decision, tool call, tool result, ...) emits a typed event into this table. The 3 indexes are tuned for the replay CLI's most-common filter compositions (chronological / per-session / per-room).

Cross-write atomicity with Kuzu: the brain.db ↔ Kuzu paired-write hardening (P0.X, Part XXXVIII §246) treats brain.db as authoritative and Kuzu as derived state that heals on next `_ensure_graph_sync()`. `event_log` follows the same rule — it's a brain.db-only table, with no Kuzu shadow.

## 121. FAISS Index Layout

`faces/faiss.index` is a serialised `IndexFlatIP` over 512-d vectors. Each face embedding is added with its row index in memory mapped to pid via `self._idx_to_pid: dict[int, str]`.

Rebuilt from DB on:
- Startup.
- `FaceDB.delete_person(pid)` — cleans the mapping + index.
- Factory reset.

Session 38 Issue #2 added `faiss_path` param to `FaceDB` constructor so tests use isolated indexes instead of clobbering the production one.

## 122. Kuzu Graph Schema v2

Directory: `faces/brain_graph/`. Kuzu is embedded — no server. Schema bump triggers wipe + rebuild (§90.3).

Node types:
- `Person` — PK `name`, indexed `face_id`.
- `Entity` — PK `name`. Entities are things people mention (cars, games, objects, other people).

Relationship types:
- `MENTIONED` — `(Person)-[MENTIONED]->(Entity)` with count, last_mentioned, shared flag.
- `RELATES_TO` — `(Person)-[RELATES_TO]->(Person)` with type (friend, parent, sibling, ...).

## 123. `state.json` IPC Format

```json
{
    "status": "ready",
    "pipeline_state": "LISTENING",
    "current_person": {
        "id": "jagan_23ff85",
        "name": "Jagan",
        "type": "best_friend"
    },
    "persons_in_frame": [
        {"id": "jagan_23ff85", "name": "Jagan", "source": "face", "conf": 0.82}
    ],
    "active_sessions": [...],
    "system_name": "Kara",
    "cloud_state": "ONLINE",
    "last_update_ts": 1713600000.12
}
```

Written by `state.py::write_state(...)`. Dashboard polls at ~500ms.

## 124. Atomic Write Pattern

```python
def write_state(**fields):
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(fields))
    tmp.replace(STATE_FILE)   # atomic on POSIX; atomic on Windows if same volume
```

Rename is atomic on both platforms when source and dest are on the same volume. A reader can't see a partially-written file.

Same pattern for `enroll_request.json`, `enroll_result.json`, `reset_request.json`, `reset_result.json`.

---
---

# Part XIX — Config System

## 125. Single Source of Truth Invariant

### 125.1 The rule

Every tunable value in the system lives in `core/config.py`. No magic numbers in decision code.

### 125.2 Why enforced

Historical reason: during the uncle-false-match debug (Session 51), several thresholds were scattered across `pipeline.py`, `brain.py`, and `db.py`. Tuning one without tuning the others caused silent inconsistencies. Consolidating fixed the drift.

### 125.3 Current enforcement (structural, not convention-based)

The "single source of truth" rule used to be convention-only — relied on reviewer discipline + a grep-for-`0\.[0-9]` heuristic. The P0 work since 2026-05-08 made it structural. Every major drift class is now caught by a CI-enforced AST or behavioral invariant:

- **Hardcoded literals in routing thresholds** — Part X §61 — `_effective_switch_threshold` reads from config, not literals; the threshold values import as named constants.
- **`ALTER TABLE` outside the migration modules** — `TestNoAlterTableOutsideMigrationModules` (Part XLII §284) AST-rejects any inline ALTER outside `core/{faces,brain}_db_migrations.py`.
- **Magic numbers in store schemas** — `tests/test_p06_store_schemas.py` pins `EXPECTED_FIELDS` per Store (Part XXXIX §260). Schema drift fails CI.
- **Magic numbers in dispute-state predicates** — `_is_disputed()` is the canonical predicate; raw `"disputed"` comparisons outside the helper are AST-rejected (Part XXXVI §234).
- **Coupling tests** — e.g., `test_bootstrap_budget_exceeds_mature_threshold` fails if `N_INITIAL_VOICE_BOOTSTRAP` is tuned below `VOICE_ACCUM_MATURE_SAMPLE_COUNT`.

The convention layer (reviewer grep) is now backup, not primary. If you bypass `core/config.py` with an inline literal in production code, one of these structural invariants will catch you at PR time.

## 126. Startup Assertions

Run on `run()` entry:

1. **Tool privilege completeness** — every `brain.TOOLS` entry has a `TOOL_PRIVILEGES` row.
2. **Bootstrap arithmetic** — `N_INITIAL_VOICE_BOOTSTRAP > VOICE_ACCUM_MATURE_SAMPLE_COUNT`.
3. **Person type validity** — any `SessionStore.open_session` caller must pass a value in `VALID_PERSON_TYPES`.
4. **Schema migrations applied** — `apply_migrations` runs at boot for every DB; refuses to start if any migration's `verify_post_fn` raises (Part XLII).
5. **Pyannote patch idempotency** — the import-time monkeypatch in `core/voice.py` only fires if torchaudio still has the legacy API; otherwise no-op.

If any fires, the system refuses to start. Impossible to ship a broken config.

## 127. Tuning Workflow

1. Change one value in `core/config.py`.
2. Run `pytest --tb=no -q` (full suite, per the verification-before-completion lesson from Part L §324).
3. If tests pass, do a live test.
4. If the live test reveals the tune was too aggressive/conservative, revert.
5. Never touch a literal in a non-config file as a shortcut. The structural invariants will catch you, but more importantly, the next person editing the file will assume the literal is correct and tune the wrong thing.

---
---

# Part XX — Testing

## 128. ~2216 Tests — Breakdown by Category

| Category | Files | Tests | Focus |
|---|---|---|---|
| Pipeline integration | `test_pipeline.py` and adjacents | ~750 | Session management (post-P0.7 via SessionStore API), routing dispatch, tool dispatch, ROOM block, TURN ARBITRATION, address marker, integration scenarios |
| Knowledge system | `test_brain_agent.py` | ~250 | Knowledge pipeline, each agent, Kuzu graph, visibility clause, privacy classifier, room summaries, safety-flag preservation |
| Reconciler (Part X) | `test_reconciler.py` + `test_p10_reconciler_contract.py` + `test_p10_routing_invariants.py` | ~60 | 22-rule cascade per-rule behavior, C1-C21 contracts, RULES-ordering invariant, EXPECTED_RULES_BY_BAND, Bug-W gap regression, negative-cosine regression |
| Voice/vision channels | `test_voice_channel.py` + `test_vision_channel.py` | ~40 | Pure-function channel contracts, import-boundary AST scans |
| Atomicity (Part XXXVIII) | `test_faiss_sql_atomicity.py` + `test_faiss_atomicity_invariants.py` + `test_kuzu_atomicity_invariants.py` + `test_kuzu_brain_atomicity.py` + `test_kuzu_crash_injection.py` | ~85 | Cross-storage paired-write contracts, sentinel + boot reconciliation, RAISE/SWALLOW/SCHEMA_MIGRATION detectors |
| Store pattern (Part XXXIX) | `test_p06_store_invariants.py` + `test_p06_store_schemas.py` + `test_p06_store_inverse_checks.py` + `test_p06_legacy_global_progress.py` + per-store unit tests | ~150 | Eight stores' contracts, schema pinning, paired-write inverse checks, legacy-global ratchet at cap=0 |
| Typed session state (Part XL) | `test_session_store.py` + `test_session_state_invariants.py` + `test_p072_read_migration_progress.py` | ~70 | Session/SessionSnapshot/VoiceEvidence shape, named transitions, single-writer invariant, no-dual-writes ratchet |
| Tool timeout (Part XLI) | `test_tool_timeout.py` + `test_p08_structural_invariants.py` | ~30 | Per-tool wait_for, cancellation rollback, F1 + F2 structural invariants |
| Schema migrations (Part XLII) | `test_schema_migrations.py` + `test_p09_retrofit_migrations.py` | ~45 | Versioned-ledger pattern, 5-tuple shape, bootstrap walks MIGRATIONS, no-ALTER-outside-modules, no-destructive-ops invariant |
| State race (Part XLIV) | `test_state_race.py` | 4 | Behavioural race + torn-state probe + AST subscript-assign ban + global decl invariant |
| JSON parser (Part XLV) | `test_brain_json_parser_hypothesis.py` | ~33 | Hypothesis property tests (1000 examples/each), regression tests pinned to the two production bugs |
| Health + disk (Part XLVI) | `test_health.py` + `test_disk_monitor.py` | ~20 | HealthSnapshot field coverage, format_health_line, format_health_alerts, idempotent threshold transitions |
| Conversation hygiene (Part XLVII) | `test_hard_delete_invalidated.py` + `test_scene_block_cache.py` + `test_conversation_archive.py` | ~13 | Dream-loop hard-delete, scene-block SHA-256 cache, ATTACH-based atomic archival |
| CI scaffold (Part XLVIII) | `test_dashboard_bind_tripwire.py` + `test_infra_debt_allowlist.py` | ~10 | Localhost binding tripwire, xfail-decorator alignment with allowlist |
| Event log (Part XLIX) | `test_event_log_contract.py` + `test_event_log_invariants.py` + `test_event_log_producer_coverage.py` + `test_event_log_replay.py` | ~80 | 15 contract + 35 parametrized invariant cases + 11 hook coverage + 5 replay smoke tests including anti-spoof field preservation |
| Privacy clause + classifier | privacy tests inside `test_brain_agent.py` and others | ~40 | Visibility clause for 4-tier model, classifier prompt, query_knowledge_for, owner-access (3A.4.6) |
| Layering invariants | `test_layering_invariants.py` + `test_silent_except_invariant.py` + `test_no_raw_disputed_comparisons.py` + `test_no_layering_violations.py` + `test_repeat_guard_invariant.py` + `test_prior_person_type_default.py` + `test_user_text_gate_*.py` | ~100 | AST-based structural invariants enforcing P0.1, P0.2, P0.3, P0.4, P0.13 |
| Vision / audio | `test_vision_v1v4.py` + various audio tests | ~70 | Quality gates V1-V4, anti-spoof, smart-turn, lip tracking, STT, TTS |
| Other | tool executor, shutdown, greetings, eval bench, classifier graph, time anchor, prompt blocks, etc. | ~250 | Miscellaneous unit + integration tests |

**Total: ~2302 passing, 9 xfailed, 4 skipped, 0 failed, 0 errors as of 2026-05-18 post-P0.0.7.X closure.**

**Growth since Session 113.1 (~1083 tests, 2026-04-24).** +1133 tests across ~6 weeks of disciplined P0 hardening + Wave 5/6 + P0.0/P0.0.7. Most growth concentrated in:

- **P0.4** silent-except audit (+14 invariant tests catching the 22 sites + the 4 detector self-tests).
- **P0.5 + P0.X** cross-storage atomicity (+85 across the 5 atomicity test files).
- **P0.6** Store-pattern migration (+150 store unit tests + schema/inverse-check ratchets).
- **P0.7** typed session state migration (+70 SessionStore + invariant tests across the 5 sub-PRs).
- **P0.8** per-tool timeout protection (+30 including F1 + F2 structural invariants).
- **P0.9** schema migrations versioning (+45 retrofit + ratchet tests).
- **P0.10** legacy router deletion + Bug-W (+40 contract + invariant tests; –54 deleted legacy tests; net –15 raw / +40 architectural coverage — see Part XLIII §290 for the math).
- **P0.11** state race (+4 race + AST tests).
- **P0.12** Hypothesis property-based JSON parser hardening (+33).
- **Wave 5 + Wave 6** observability + memory consolidation (+33 across health, disk, hard-delete, scene-cache, archival).
- **P0.0 + P0.0.1 + P0.0.2** tiered CI + S2 tripwire (+10).
- **P0.0.7** event log + replay harness (+80, the largest single sub-PR's test surface).

The growth pattern is dominated by structural invariants rather than feature behaviour. Of the ~1133 new tests since 2026-04-24, roughly two-thirds are AST-based or source-inspection-based — they verify that the production code *continues to satisfy* an architectural property over time, not that a specific feature works on one happy path. This is the empirical realisation of the Part XXII §139 "tests guard every invariant" principle.

## 129. TDD Approach

New features land via TDD when practical:
1. Write a failing test for the behaviour.
2. Implement the minimal code to pass.
3. Refactor as needed; test stays green.

For bug fixes (which are the majority of recent sessions), the pattern is:
1. Write a regression test that reproduces the bug.
2. Fix the code.
3. Verify the test now passes and no others regress.

## 130. Source-Inspection Tests

For behaviours that are hard to test in isolation (because they live inside a 3761-line function or depend on async streaming), we use source-inspection:

```python
def test_stream_truncation_detection_in_source():
    src = Path("pipeline.py").read_text()
    assert "_stream_finish_reason" in src, (
        "Obs 3: pipeline must capture finish_reason from ask_stream"
    )
    assert '_finish in ("length", "content_filter", None)' in src, (
        "Obs 3: pipeline must gate retry on truncation finish_reason"
    )
```

Brittle-looking but surprisingly effective. The test fails if someone silently reverts the post-review Obs 3 fix. Tradeoff: we accept some test-as-documentation rigidity in exchange for catching regressions in code we can't easily call directly.

## 131. Async Test Pattern

`pytest-asyncio` with `asyncio_mode=auto`. Tests are just `async def test_...` functions; pytest awaits them automatically.

```python
@pytest.mark.asyncio  # optional in auto mode, but some tests use it for clarity
async def test_conversation_turn_logs_turns():
    ...
```

Mock patterns:
- `mock_db = MagicMock(spec=FaceDB)` — type-checked mock.
- `monkeypatch.setattr("core.brain.VOICE_ACCUM_MATURE_SAMPLE_COUNT", 7)` — patches the module-local binding (not the config), so `from X import Y` consumers see the patched value.

---
---

# Part XXI — Dashboard

## 132. Next.js Architecture

`Kara-OS-dashboard/` is a Next.js 14 app (App Router). It runs independently of the pipeline process on localhost:3000 (or wherever you configure). Communicates with the pipeline via the JSON file interface in `faces/`.

### 132.1 Routes

- `/` — main dashboard with live state, active sessions, vision heartbeat.
- `/persons` — enrolled people list; per-person drill-down.
- `/persons/[id]` — shows knowledge, conversation history, gallery with audit flags.
- `/visitors` — visitor log.
- `/shadow-persons` — mentioned but not enrolled.
- `/nudges` — pending proactive nudges.

### 132.2 API routes

- `POST /api/enroll` — writes `enroll_request.json`; pipeline picks up and enrolls.
- `POST /api/delete` — runs `delete_person.py` via `execFile` (NOT `exec`; Session 41 H1 security fix) with ID regex validation.
- `GET /api/gallery-audit?person_id=...` — returns audit report JSON.
- `POST /api/reset` — writes `reset_request.json`.

## 133. Real-Time State Read

Polls `faces/state.json` every 500ms via server-side fetch. Data flows to client components via React state.

We don't use WebSockets — polling a local file is fast enough and much simpler.

## 134. Enrollment Flow

The dashboard enrollment route is currently not-yet-integrated with the pipeline's camera — the request is accepted but the pipeline doesn't yet route it. This is on the roadmap.

---
---

# Part XXII — Design Philosophy and Invariants

> **Cross-reference (2026-05-18).** The principles in this Part are the *product-side* design philosophy — how the system relates to the user and how subsystems relate to each other. The *engineering-side* discipline that produces and maintains this code lives in **Part L — Architectural Disciplines (The Named Doctrines)**. The two complement each other: Part XXII describes what we build; Part L describes how we build it well. Each named discipline in Part L (induction-surfaces-invariant-gaps, spec-first review cycle, developer-improves-on-spec, etc.) has a track record of N-for-N instances backing it; the principles in this Part are stated as rules without track records because they're architectural primitives, not validated patterns.

## 135. Brain Decides, Pipeline Enforces

The most important architectural rule. The pipeline is the brain's sensors and actuators — it tells the brain what's happening and carries out what the brain decides. The brain is the one that says "respond", "call this tool", "stay silent."

The pipeline enforces:
- Privilege checks (via TOOL_PRIVILEGES).
- Accumulation gates (Path A/B/C, see §55).
- Anti-spoof gating (§24).
- Session expiry (§51).
- Dispute state transitions (Part XV §102, all via `transition_to_disputed` named transition).
- Per-tool timeout (Part XLI §273).
- Cross-storage atomicity (Part XXXVIII §242).

The brain owns:
- What to say.
- When to invoke tools.
- How to interpret the sensor data.
- Whether to call `report_identity_mismatch`.

This split prevents the pipeline from growing a competing "brain" — every temptation to encode a conversation decision at the pipeline level becomes instead an enhancement to the system prompt.

## 136. No Hardcoded Magic Numbers (Now Structurally Enforced)

Every threshold, every count, every duration lives in `core/config.py`. The exceptions (0, 1, -1, None) are intentionally not called out.

The principle used to be convention-only. As of 2026-05-16 it is structurally enforced via the AST/regex invariants enumerated in §125.3 above. The relevant Parts: Part XLII §284 (no ALTER outside migration modules), Part XXXIX §260 (store schema pinning), Part XXXVI §234 (no raw `"disputed"` comparisons).

## 137. Fail-Closed on Security

Anything resembling a security surface defaults to denial:
- Unknown tool → blocked (Part XVI §109).
- Unknown person_type → handled as stranger (Part XXXVI §235 — `prior_person_type` defaults to `"stranger"` per P0.2).
- Missing anti-spoof model → recognition_update blocked.
- Dispute without clean resolution → force-close.
- Multi-word names not contiguously appearing in user_text → rejected (Part XXXVI §236 — P0.3 contiguous-substring fix).
- Tool execution exceeding budget → cancellation + transaction rollback (Part XLI §274).
- Cross-storage half-writes → degraded mode, no silent divergence (Part XXXVIII §249).

The system errs on "do nothing" rather than "do the risky thing."

## 138. Single Source of Truth for Shared Helpers

- `log_utils._now_log_ts` — one formatter.
- `TOOL_PRIVILEGES` — one privilege table.
- `VOICE_ACCUM_*` — one set of constants used by pipeline gate AND brain verdict.
- `VALID_PERSON_TYPES` — one frozenset asserted everywhere.
- `_is_disputed()` — canonical predicate (Part XV §105; Part XXXVI §234).
- `SessionStore` — only writer of session state (Part XL §263).
- `safe_emit_sync` — only producer-hook swallow path (Part XLIX §314).
- `_visibility_clause` — only privacy-filter SQL composer (Part XXV §152).
- `core/event_log/types.py::_PAYLOAD_CLASSES` — only deserialization dispatch table (Part XLIX §313).

When there are two places something could live, there must be one. The pattern repeats across the codebase because every cycle of consolidation pays back in the next maintenance pass.

## 139. Tests Guard Every Invariant

An invariant that isn't tested is an invariant that will silently break. Every major architectural claim in this document is backed by at least one test. Source-inspection tests (§130) cover the cases that are hard to invoke directly.

The empirical realisation: ~2/3 of the ~1133 tests added between 2026-04-24 and 2026-05-18 are structural invariants (AST scans, source-inspection, paired-write inverse checks). The Part L disciplines that produce these — **induction-surfaces-invariant-gaps** (§322, 7-for-7), **structured-audit-vs-reactive-patching** (§329) — are the meta-rules that ensure every new invariant ships with a corresponding test.

## 140. Privacy at the Data Layer, Phrasing at the Prompt Layer

Two layers enforce cross-person privacy, and neither alone is sufficient:

- **Data layer** — `_visibility_clause` + `query_knowledge_for` decide what rows the brain SEES.
- **Prompt layer** — `<<<CROSS-PERSON PRIVACY>>>` / `<<<CROSS-PERSON PRIVACY (OWNER MODE)>>>` / `<<<VISITOR CONTEXT>>>` / `<<<HONESTY POLICY>>>` decide what the brain SAYS about what it sees.

A brain with restricted context can still phrase its refusal badly ("No one" instead of "Someone I can't share specifics about"). A brain with owner-full-access can still over-share inappropriately. A brain with neither flies blind. Every cross-person retrieval path routes through both layers.

The invariant: **no prompt block tries to enforce row-level privacy, and no SQL clause tries to enforce phrasing.** Each layer does one job.

## 140a. Safety-Flag Preservation — Non-Destructive Plus Append-Only

Non-destructive invalidation is sufficient for most facts. Safety-critical attributes require a stricter rule: append-only, never REPLACE.

Pattern regex lives in `core/config.py::SAFETY_CRITICAL_ATTRIBUTE_PATTERNS`:

```
^expressed_.*_thoughts$
^mentioned_.*$
^reported_.*_abuse$
^has_experienced_crisis$
```

ContradictionAgent's pre-check short-circuits on any match. New disclosures always produce a new row with a new `captured_at`. The matching momentary attribute (e.g. `current_mood`) keeps normal overwrite semantics — the system captures "right now" AND "this ever happened" as separate rows.

The naming of the config (SAFETY_CRITICAL, not APPEND_ONLY or IMMUTABLE) signals intent to future maintainers: removing a regex pattern removes a safety guarantee, not an optimisation.

## 140b. Observability at Every Latency-Critical Boundary

- STT elapsed_ms
- LLM tokens streamed
- Voice routing decision
- Tool dispatch
- Turn-end latency

These are the places where the system can mysteriously feel slow. Having timestamps and durations on each means "why is it laggy today" can be answered from logs alone.

---
---

# Part XXIII — Roadmap and Open Items (Hardware + Long-Range Product)

> **Cross-reference (2026-05-18).** The **engineering** roadmap — the upcoming P0 security / P0 robustness / eval gates / P1.A pipeline decomposition sequence — lives in **Part LI — Upcoming Work and Roadmap** (§331-§340). That's the actively-managed queue and the place to check for "what's next". This Part XXIII covers the hardware-and-long-range items: physical actuators, Jetson deployment, wake-word power management, the Q3 history redesign — items that depend on either physical-world milestones or on broader architectural decisions that aren't blocking the current sprint.

