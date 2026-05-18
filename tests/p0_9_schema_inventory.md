# P0.9 Schema Inventory — Phase 0 Audit

**Scope:** every schema mutation that has landed across the three production SQLite databases. Pure inventory — no plan, no implementation. Output of the audit-only cycle the reviewer authorized before any P0.9 design work begins.

**Date:** 2026-05-17
**Suite at audit time:** 2142 passing, 8 pre-existing infra failures.

**Databases audited:**
- `faces.db` (`core/db.py::FaceDB`)
- `faces/{stem}_conversation_archive.db` (sibling archive DB created by `FaceDB._init_conversation_archive`)
- `brain.db` (`core/brain_agent.py::BrainDB`)
- `data/classifier_scenarios.db` (`core/classifier_db.py::ClassifierDB`)

**Conventions:**
- *Idempotency* — whether the schema mutation can safely re-run on an already-migrated DB without error.
  - `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` are inherently idempotent.
  - `ALTER TABLE ADD COLUMN` is NOT idempotent in SQLite — wrapped in `try/except sqlite3.OperationalError: pass` OR `PRAGMA table_info(...)` check.
- *Reversibility* — whether a rollback would lose data.
  - All current mutations are **additive** (new tables, new indexes, new nullable columns with defaults). Zero column drops, renames, or type changes ever shipped.
- *Provenance* — Session # / Wave / P0.X / Phase per `CLAUDE.md` history. `unknown` = no provenance entry in CLAUDE.md (drift flag).

---

## faces.db — 8 tables, 5 indexes, 9 ALTER TABLE migrations

### Tables (CREATE TABLE IF NOT EXISTS — all idempotent)

| Line | Table | Columns | Provenance | Notes |
|---|---|---|---|---|
| 64 | `persons` | `id`(PK), `name`, `enrolled_at`, `photo_path` + 3 ALTER-added cols | Original | Core persons table. AUTOINCREMENT-free, `id` is TEXT pid like `stranger_abc123`. |
| 72 | `embeddings` | `id`, `person_id`(FK), `faiss_idx`, + 3 ALTER-added cols | Original | Face embedding rows. `vector` BLOB added via ALTER (legacy schema didn't store it). |
| 82 | `conversation_log` | `id`, `person_id`, `role`, `content`, `ts` + 2 ALTER-added cols | Original | Audit log of every turn. Two cols added later (S107 Phase 3A.6 Part 3). |
| 89 | `visitor_log` | `id`, `ts`, `note` (free-form) | Original | Comment explicitly notes: "no person_id column — delete_person() needs no cleanup here". |
| 94 | `voice_embeddings` | `id`, `person_id`(FK), `vector`, `captured_at` + 2 ALTER-added cols | Original | Per-person ECAPA voice profile rows. |
| 117 | `system_identity` | `key`(PK), `value`, `set_by`, `set_at`, `note` | Session 70-area | Seeds row `('system_name', DEFAULT_SYSTEM_NAME, ...)` via `INSERT OR IGNORE` at init. |
| 130 | `silent_observations` | `id`(PK), `first_seen`, `last_seen`, `duration_secs`, `frame_count`, `embedding`, `photo_path`, `zone`, `matched_person_id`, `created_at` | Session 22 area | Background-scan unrecognized-face accumulator. |
| 259 (archive) | `conversation_log` (in *_conversation_archive.db*) | `id`, `person_id`, `role`, `content`, `ts`, `room_session_id`, `audience_ids` | Wave 6 Item 21 | Companion DB for >30-day-old turns. Created via `_init_conversation_archive` when `CONVERSATION_ARCHIVE_ENABLED=True`. |

### Indexes (CREATE INDEX IF NOT EXISTS — all idempotent)

| Line | Index | Table | Columns | Provenance |
|---|---|---|---|---|
| 144 | `idx_silent_obs_last_seen` | silent_observations | `(last_seen)` | Session 24 B7 — bounded scan |
| 147 | `idx_log_person` | conversation_log | `(person_id, ts)` | Original |
| 180 | `idx_conv_log_room` | conversation_log | `(room_session_id, ts DESC)` | Session 107 Phase 3A.6 Part 3 |
| 270 (archive) | `idx_archive_log_person` | conversation_log (archive) | `(person_id, ts)` | Wave 6 Item 21 |

### ALTER TABLE ADD COLUMN migrations (try/except sqlite3.OperationalError)

| Line | Table | Column | Provenance | Idempotency | Reversibility | Notes |
|---|---|---|---|---|---|---|
| 111 | `embeddings` | `source TEXT NOT NULL DEFAULT 'legacy_unknown'` | (loop block) | try/except | Additive nullable-with-default | Provenance metadata for embedding source. |
| 111 | `voice_embeddings` | `source TEXT NOT NULL DEFAULT 'legacy_unknown'` | (loop block) | try/except | Additive | Same. |
| 111 | `embeddings` | `confidence_at_write REAL NOT NULL DEFAULT 0.0` | (loop block) | try/except | Additive | Same. |
| 111 | `voice_embeddings` | `confidence_at_write REAL NOT NULL DEFAULT 0.0` | (loop block) | try/except | Additive | Same. |
| 156 | `persons` | `last_seen REAL` | Original-area | try/except | Additive nullable | |
| 157 | `persons` | `preferred_language TEXT NOT NULL DEFAULT 'en'` | Pre-Session-22 | try/except | Additive | English-only env, but column kept for future per-person language. |
| 158 | `embeddings` | `vector BLOB` | Pre-Session-22 | try/except | Additive nullable | Legacy DBs stored embeddings out-of-table. |
| 159 | `persons` | `person_type TEXT NOT NULL DEFAULT 'known'` | Session 22 G4 | try/except | Additive | Drives privilege model (best_friend / known / stranger / disputed). |
| 167 | `conversation_log` | `room_session_id TEXT` | Session 107 Phase 3A.6 Part 3 | try/except | Additive nullable | Group/room context grouping for 3B retrieval. |
| 168 | `conversation_log` | `audience_ids TEXT` (JSON) | Session 107 Phase 3A.6 Part 3 | try/except | Additive nullable | JSON list of person_ids who can see the turn. |

### One-shot data backfill (faces.db, L191-214)

When the L167-168 ALTERs land on an existing DB, the L191-214 block performs a deterministic backfill:
- `SELECT COUNT(*) FROM conversation_log WHERE room_session_id IS NULL` — gate.
- For each person_id, compute `MIN(ts)` and set `room_session_id = f"{pid}_{int(first_ts)}"` + `audience_ids = json.dumps([pid])`.
- Idempotent — `WHERE room_session_id IS NULL` matches zero rows on second run.
- **Reversibility:** would lose the synthetic session grouping on rollback. Not currently versioned.

### Destructive operation (faces.db, L150)

| Line | Operation | Target | Provenance | Reversibility |
|---|---|---|---|---|
| 150 | `DROP TABLE IF EXISTS conversation_memory` | legacy table | Session 24 A4 | Data lost. Pre-Session-24 DBs had this table; cleanup runs at every `_init_tables()`. |

---

## brain.db — 18 tables, 12 indexes, 8 ALTER TABLE migrations + 1 one-shot backfill

### Tables (CREATE TABLE IF NOT EXISTS — all idempotent)

| Line | Table | Provenance | Notes |
|---|---|---|---|
| 832 | `brain_state` | Original Phase 1 | Singleton row tracking `last_turn_id` + `updated_at` + (later) `graph_schema_version`. |
| 843 | `knowledge` | Original Phase 1 | The LLM-decided entity/attribute/value store. `privacy_level` column part of CREATE since S95 3A.1 hardcoded; older DBs need ALTER (L1533). |
| 866 | `schema_catalog` | Original Phase 1 | Tracks every attribute name the LLM has invented. |
| 877 | `agent_log` | Original Phase 1 | Audit trail for every agent decision. |
| 892 | `prompt_prefs` | Session 13 | Per-person communication preferences. |
| 908 | `object_pattern_questions` | Session 17 | Queued proactive questions about object patterns. |
| 918 | `object_patterns` | Session 17 | Confirmed behavioral patterns. |
| 929 | `social_mentions` | Session 18-area | People mentioned by best_friend during conversation. |
| 942 | `episodes` | Session 18 | Per-session episode summaries (ConversationInsightAgent). |
| 960 | `presence_log` | Session 41 | Per-person visit windows (RoutineAgent). |
| 974 | `proactive_nudges` | Session 23 G5a | Pending proactive nudges (visitor alerts, friction nudges, cross-person hypothesis). |
| 990 | `watchdog_alerts` | Session 42 | System health + anomaly alerts (anti-spoof, dispute-rename burst, disk threshold). |
| 1006 | `object_sightings` | Session 17 / Wave-5 | YOLO detection log (currently disabled via `VISION_YOLO_ENABLED=False`). |
| 1026 | `predicate_stats` | Phase 5 / Session 20 | Per-predicate contradiction + extraction counters → ContradictionAgent confidence cap. |
| 1035 | `household_facts` | Session 39 Part 4 | Household-scoped facts ("we have 2 cats" / "our backup is Friday"). |
| 1052 | `inter_person_relationships` | Session 39 Part 4 | Inferred relationships between persons. |
| 1068 | `shadow_persons` | Session 22 G3 / Session 39 | Non-enrolled persons mentioned in conversation; promoted on enrollment. |
| 1087 | `intent_divergences` | Session 85 P1.7a | Every gated-tool decision (allow/reject/regex_fallback_*/shadow_sample) for Phase 5 drift detection. |
| 1111 | `room_summaries` | Phase 3B.6 / Session 105-area | Room-end synthesis target. One row per multi-person room session. |

### Indexes (CREATE INDEX IF NOT EXISTS — all idempotent)

| Line | Index | Table | Columns | Provenance |
|---|---|---|---|---|
| 860 | `idx_knowledge_entity` | knowledge | `(entity, attribute) WHERE invalidated_at IS NULL` | Original Phase 1 |
| 903 | `idx_prompt_prefs_person_id` | prompt_prefs | `(person_id)` | Session 13 |
| 938 | `idx_social_mentions_source` | social_mentions | `(source_person_id)` | Session 18 |
| 956 | `idx_episodes_person` | episodes | `(person_id, session_end_ts DESC)` | Session 18 |
| 970 | `idx_presence_log_person` | presence_log | `(person_id, arrived_at DESC)` | Session 41 |
| 986 | `idx_nudges_person` | proactive_nudges | `(target_person_id, injected_at, dismissed_at, expires_at)` | Session 23 |
| 1000 | `idx_watchdog_ts` | watchdog_alerts | `(created_at DESC, resolved)` | Session 42 |
| 1018 | `idx_object_sightings_class` | object_sightings | `(object_class)` | Session 17 |
| 1020 | `idx_object_sightings_ts` | object_sightings | `(last_seen_at)` | Session 17 |
| 1048 | `idx_household_facts_entity_attr` | household_facts | `(entity, attribute)` | Session 39 Part 4 |
| 1062 | `idx_relationships_unique` (UNIQUE) | inter_person_relationships | `(person_a, relationship, person_b)` | Session 39 Part 4 |
| 1101 | `idx_intent_divergences_ts` | intent_divergences | `(ts DESC)` | Session 85 |
| 1103 | `idx_intent_divergences_tool` | intent_divergences | `(tool_proposed, ts DESC)` | Session 85 |
| 1105 | `idx_intent_divergences_mode` | intent_divergences | `(mode, ts DESC)` | Session 119 Phase 5 |
| 1121 | `idx_room_summaries_ended` | room_summaries | `(ended_at DESC)` | Phase 3B.6 |
| 1536 | `idx_knowledge_privacy_person` | knowledge | `(privacy_level, person_id)` | Session 95 3A.1 |

### ALTER TABLE ADD COLUMN migrations (PRAGMA-guarded — proper idempotency check, NOT try/except)

`_migrate()` at L1478 explicitly states "ALTER TABLE ADD COLUMN only (never destructive)." Each block reads `PRAGMA table_info` to check column presence before adding.

| Line | Table | Column | Provenance | Idempotency | Reversibility | Notes |
|---|---|---|---|---|---|---|
| 1483 | `knowledge` | `embedding BLOB` | Phase 3 / Session 15 | PRAGMA-guarded loop | Additive nullable | Embedding semantic-search payload. |
| 1483 | `schema_catalog` | `embedding BLOB` | Phase 3 / Session 15 | PRAGMA-guarded loop | Additive nullable | Same loop covers both tables. |
| 1490 | `knowledge` | `valid_at REAL` | Phase 5-area "Item 3" | PRAGMA-guarded | Additive nullable + UPDATE backfill | Backfills `valid_at = created_at` for legacy rows. |
| 1495 | `knowledge` | `last_confirmed_at REAL` | Phase 5-area "Item 6" | PRAGMA-guarded | Additive nullable | SM-2 confirmation anchor. |
| 1501 | `prompt_prefs` | `friction_count INTEGER NOT NULL DEFAULT 0` | Phase 5 / Session 20 | PRAGMA-guarded | Additive | FrictionDetectionAgent counter. |
| 1508 | `prompt_prefs` | `embedding BLOB` | Session 69 Bug L | PRAGMA-guarded | Additive nullable | Semantic dedup at pref activation. |
| 1515 | `brain_state` | `graph_schema_version INTEGER NOT NULL DEFAULT 0` | Session 42-area | PRAGMA-guarded | Additive | Detects Kuzu RELATES_TO schema changes → forced wipe+rebuild. |
| 1526 | `shadow_persons` | `mention_count INTEGER NOT NULL DEFAULT 1` | Session 97 Fix 3 (Session 114-area canary) | PRAGMA-guarded | Additive | Bumped on every `upsert_shadow_person` update. |
| 1533 | `knowledge` | `privacy_level TEXT NOT NULL DEFAULT 'public'` | G7b / Session 95 3A.1 | PRAGMA-guarded | Additive | 4-tier privacy classifier feed; superseded by 4-tier `public/personal/household/system_only`. |
| 1548 | `intent_divergences` | `mode TEXT NOT NULL DEFAULT 'gate'` | Session 119 Phase 5 | PRAGMA-guarded | Additive | Splits 'gate' production decisions from 'shadow' canary samples. |

### One-shot data backfill (brain.db, L1564+ region — `_migrate` continues)

VISION_ROADMAP Phase 3A.4 — legacy privacy_level remediation:
- **(1)** NULL rows → set `privacy_level = PRIVACY_LEVEL_DEFAULT='personal'` (defensive belt-and-braces; CREATE TABLE has DEFAULT 'public' so NULL shouldn't appear, but legacy hand-edits could produce them).
- **(2)** `'private'` rows (legacy 2-tier owner-only) → migrate to `'personal'` (new 4-tier semantic equivalent). `'private'` would be invisible under the new `_visibility_clause` (which has no predicate matching `'private'`).
- Idempotent — `WHERE privacy_level IS NULL` / `WHERE privacy_level = 'private'` match zero rows on second run.
- **Reversibility:** data semantic preserved (owner-only → owner-only); no row-loss; only the label changes.

---

## classifier_scenarios.db — 5 tables, 4 indexes, 1 versioned migration (Spec 2 v2)

### Tables (CREATE TABLE IF NOT EXISTS — all idempotent)

| Line | Table | Provenance | Notes |
|---|---|---|---|
| 93 | `scenarios` | Spec 1 / Session 122 | Core graph classifier data. `extracted_value` column is part of CREATE since v2; older v1 DBs add via migration #2 (L162). |
| 119 | `schema_migrations` | Spec 1 / Session 122 | **Versioned migration ledger.** `version INTEGER PRIMARY KEY` + `description` + `applied_at`. This is the gold-standard pattern P0.9 should generalize. |
| 125 | `label_evolution` | Spec 1 / Session 122 | Maps deprecated intent labels at query time. `PRIMARY KEY (old_label, effective_version)`. |
| 133 | `audit_log` | Spec 1 / Session 122 | Append-only log of every counter change / quarantine. `FOREIGN KEY (scenario_id) REFERENCES scenarios(scenario_id)`. |
| 146 | `db_metadata` | Spec 1 / Session 122 | Key-value pairs (embedding_model_id, etc.). Seeded by `_seed_metadata()`. |

### Indexes (CREATE INDEX IF NOT EXISTS — all idempotent)

| Line | Index | Table | Columns | Provenance |
|---|---|---|---|---|
| 114 | `idx_scenarios_intent` | scenarios | `(intent_label, active)` | Spec 1 |
| 115 | `idx_scenarios_source` | scenarios | `(source_tag, source_version)` | Spec 1 |
| 116 | `idx_scenarios_dedup` (UNIQUE) | scenarios | `(abstract_text, intent_label)` | Spec 1 |
| 143 | `idx_audit_log_scenario` | audit_log | `(scenario_id)` | Spec 1 |
| 144 | `idx_audit_log_ts` | audit_log | `(ts DESC)` | Spec 1 |

### Versioned migrations (via `schema_migrations` ledger — proper versioning)

`_run_migrations()` at L154 iterates a `migrations: list[tuple[int, str, Callable]]` and writes `INSERT INTO schema_migrations (version, description, applied_at)` after each `fn(conn)`.

| Version | Description | Callable | Idempotency | Reversibility |
|---|---|---|---|---|
| 1 | "initial schema (Spec 1)" | `lambda _conn: None` | Baseline — recorded but no-op | n/a |
| 2 | "Spec 2: extracted_value column" | `_migration_v2_add_extracted_value` (try/except sqlite3.OperationalError) | Idempotent via `WHERE version NOT IN applied` set comprehension | Additive nullable |

---

## Cross-database summary

| Property | faces.db | faces/_conversation_archive.db | brain.db | classifier_scenarios.db |
|---|---|---|---|---|
| Tables | 8 | 1 | 18 | 5 |
| Indexes | 5 | 1 | 16 | 5 |
| ALTER TABLE ADD COLUMN migrations | 9 | 0 | 10 | 1 |
| Versioned migration ledger | ❌ | ❌ | ❌ | ✅ (`schema_migrations`) |
| Idempotency mechanism | `try/except OperationalError` | n/a | `PRAGMA table_info(...)` check | Version-set check |
| One-shot data backfills | 1 (S107 P3A.6 room_session_id) | 0 | 1 (S95 3A.4 privacy_level migration) | 0 |
| Destructive operations | 1 (`DROP TABLE IF EXISTS conversation_memory` legacy cleanup) | 0 | 0 | 0 |
| Foreign keys | Yes (embeddings→persons, voice_embeddings→persons) | No | No (intentional — denormalized for write throughput) | Yes (audit_log→scenarios) |
| PRAGMA `foreign_keys=ON` set? | No | No | No | **Yes** (L83) |

---

## Drift flags (mutations without explicit CLAUDE.md provenance)

Most CLAUDE.md milestone entries name specific tables/columns when they land, but a few cases are uncertain or implicit:

1. **`embeddings.vector` ALTER (faces.db L158)** — `"ALTER TABLE embeddings ADD COLUMN vector BLOB"`. Provenance is "pre-Session-22" (the BLOB column is part of the CREATE TABLE statement now, so this ALTER only fires on legacy DBs). No CLAUDE.md entry explicitly documents this migration; it's implicit in pre-history. **Risk: low** — purely additive, default NULL, callers handle missing vector.

2. **`embeddings.source` + `embeddings.confidence_at_write` + parallel voice_embeddings ALTERs (faces.db L106-113)** — no CLAUDE.md milestone entry directly says "added source / confidence_at_write columns." Likely landed alongside Session 22 G3 area but undocumented in the milestone text. **Risk: low** — additive, defaults to `'legacy_unknown'` / `0.0`.

3. **`persons.last_seen` + `persons.preferred_language` ALTERs (faces.db L156-157)** — `last_seen` is mentioned in P0.4 Batch comment context (`prune_old_strangers` uses it), `preferred_language` mentioned in CLAUDE.md ("English only — column kept for future per-person language") but no explicit "when added" milestone. **Risk: low** — additive.

4. **`persons.person_type` ALTER (faces.db L159)** — Session 22 G4 documented the GATE behavior (stranger system-name gate) but the underlying schema migration that introduced the column is implicit. **Risk: low** — additive with default `'known'`.

5. **`system_identity` CREATE + seed (faces.db L117)** — drives `DEFAULT_SYSTEM_NAME` initialization. No explicit milestone entry name. **Risk: low**.

6. **`silent_observations` CREATE (faces.db L130)** — Session 22 B3-area but no direct "schema landed at S22" entry. **Risk: low** — full provenance via Session 22 work.

7. **`brain.db` initial Phase 1 tables (L832-1078 — 16 of the 18 tables)** — listed individually in CLAUDE.md's "Module Roles" section but no per-table "added in Session N" entries. Their provenance is "Phase 1 / Session 12+" (the brain_agent.py multi-agent pipeline rollout). **Risk: low** — well-documented in aggregate.

8. **`brain_state.graph_schema_version` ALTER (brain.db L1515)** — comment says "detect Kuzu RELATES_TO schema changes" — relates to the GRAPH_SCHEMA_VERSION config constant. No specific CLAUDE.md entry naming this migration. **Risk: low** — additive default 0.

9. **`intent_divergences.mode` ALTER (brain.db L1548)** — Session 119 Phase 5 documented as "shadow sample = 1% canary" but the schema ALTER is implicit in the milestone. **Risk: low** — additive default 'gate'.

**No drift flags raise correctness concerns.** All flagged mutations are additive and have defensive idempotency. The drift is documentation-completeness, not behavior-correctness.

---

## Observations relevant to P0.9 design (NOT a plan — observations only)

1. **classifier_scenarios.db is the only DB with proper versioned migrations.** `schema_migrations` ledger + `MIGRATIONS: list[tuple[int, str, Callable]]` in `_run_migrations` (L174-189). This is the gold-standard pattern the auditor previously called out as Spec 1's contribution to the codebase's migration discipline. P0.9 design should generalize this pattern, not invent a new one.

2. **faces.db uses `try/except sqlite3.OperationalError` for column-add idempotency.** Works in practice but conflates "column already exists" with other operational errors (e.g. disk full mid-ALTER). The classifier_scenarios.db migration also uses this pattern at the per-migration callable level. P0.9 should pick one of: (a) PRAGMA-guarded check (brain.db pattern), (b) try/except OperationalError (faces.db / classifier_scenarios.db migration #2 pattern). brain.db's pattern is stricter.

3. **All schema mutations to date are additive.** Zero column drops, renames, or type changes. P0.9 plan can punt on reversible-migration support for now — but should note that the moment a non-additive change is required, the current ad-hoc patterns break.

4. **One-shot data backfills are inline in `_init_tables` / `_migrate`.** Two exist today: S107 P3A.6 conversation_log backfill (faces.db) and S95 3A.4 privacy_level remediation (brain.db). Both are correctness-critical (without them, the new column's semantic-default doesn't apply to legacy rows). Neither is versioned. P0.9 needs to decide: (a) keep backfills inside migration callables and version them, or (b) separate "schema migration" from "data migration" with two ledgers.

5. **`DROP TABLE IF EXISTS conversation_memory` (faces.db L150)** is the only destructive operation in the entire schema surface. It runs at every `_init_tables()` (idempotent). Pre-Session-24 DBs had this table; post-S24 it never gets recreated. P0.9 could legitimately delete this line now that any user upgrading from pre-S24 has long since had it dropped — or version it explicitly as migration #0.

6. **No `PRAGMA foreign_keys=ON` on faces.db or brain.db.** Only classifier_scenarios.db sets it (L83). FaceDB's `embeddings.person_id` / `voice_embeddings.person_id` FOREIGN KEY declarations are therefore advisory only — SQLite parses them but does not enforce. Production `delete_person()` cleanup is implemented in app code, not schema. **Not a P0.9 issue per se**, but adjacent.

7. **archive DB is a sibling, not embedded.** The `faces/{stem}_conversation_archive.db` is created lazily via `_init_conversation_archive` when `CONVERSATION_ARCHIVE_ENABLED=True` and accessed via `ATTACH DATABASE` for atomic INSERT→DELETE in `archive_old_conversation_log`. P0.9 needs to decide whether the archive DB participates in the same migration ledger or has its own (currently neither — schema is duplicated inline in `_init_conversation_archive`).

8. **`graph_schema_version` ALTER on brain_state interacts with Kuzu**, not with the brain.db schema. It's a SQLite-side counter for the Kuzu graph schema. Mixing in here is the only cross-DB schema dependency.

---

## What this audit does NOT do (per reviewer's authorization)

- Does not propose retroactive migration numbers
- Does not pick one-way-vs-reversible per migration
- Does not spec P0.9 implementation
- Does not modify any production code
- Does not modify any test code

Next step per reviewer's directive: architect + auditor review this inventory together to assign retroactive migration numbers, decide reversibility per migration, and spec the P0.9 implementation against real inventory. Hold P0.9 plan until that review lands.
