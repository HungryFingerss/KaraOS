# TechAnalyst-2 — KaraOS Agents & Memory Deep Review — P1 Prep — 2026-05-27

**Agent:** TechAnalyst-2
**Focus area:** 14-agent pipeline + memory layer (FAISS face index, brain.db SQLite knowledge graph, Kuzu property graph, voice gallery, classifier-graph scenarios DB)
**Source code reviewed:** `core/brain_agent.py` (~9000 LOC, 18 agent classes + BrainDB + GraphDB + BrainOrchestrator), `core/db.py` (~2000 LOC, FaceDB + FAISS atomicity), `core/voice.py` (ECAPA gallery + pyannote diarization), `core/emotion.py` (EmotionAgent), `core/sanitize.py` (P0.S5 prompt-injection wrap), `core/classifier_graph.py` + `core/classifier_db.py` (Spec 2 pure-graph classifier), `core/schema_migrations.py` (P0.9 migration runner), `core/health.py`, `core/heavy_worker.py` (P0.R6 ProcessPoolExecutor), plus the full closure narrative arc P0.5 → P0.B5 → P0.R15 from `CLAUDE.md`.
**Process:** every claim below is anchored to either a specific file:line reference, a closure-narrative banking in CLAUDE.md, or an industry-precedent citation. Where I extrapolate, I flag it explicitly.

---

## 1. Executive Summary

### What KaraOS's memory + agent layer is today
A **single-household, single-best-friend, conversational-companion cognition stack** built around an SQLite knowledge graph (`brain.db`), a Kuzu property graph (derived/rebuildable from SQL), a FAISS face index (`faces/faiss.index`), an ECAPA voice gallery (SQL BLOBs, no ANN), and 18 async LLM-driven agents orchestrated through `BrainOrchestrator.notify()` event-triggered + 2s fallback poll. The architecture is mature for its current target (Jagan's house, his face + voice + memory). It has survived 35+ closed P0 cycles with structural invariant tests preventing regression of every bug class found in live canaries.

### What KaraOS's memory + agent layer is NOT today
A **robotics cognitive middleware**. The current stack is optimized for *who is in the room and what did they say*. It is **not** optimized for *what commitments are pending, what skills got executed, what the verifier saw, what the cost ledger spent, what world-state changed*. Every memory primitive is conversational. None are embodied. P1 must close this gap or the goal in future-execution.md §2.3 ("KaraOS v1 must claim only this: simulation-tested, ROS 2-ready embodied execution runtime…") is unreachable from where we stand.

### The three load-bearing findings of this review

1. **The 18-agent pipeline is over-engineered for the robotics goal AND under-engineered for it.** Over-engineered: 8 of 18 agents (FrictionDetection, ObjectPattern, SocialGraph, Routine, Briefing, ConversationInsight, SpatialMemory, PatternAnalysis) are about being a smart companion — they have no place in a robot control loop. Under-engineered: there is **zero** memory primitive for durable scheduled commitments, skill-execution provenance, verifier outcomes, or cost ledger. Section 2 + Section 8 detail the consolidation + new agent surface.

2. **FAISS + Kuzu + brain.db cross-storage atomicity is solid; brain.db semantic search is the soft spot.** P0.5 + P0.X + P0.B2 + P0.B3 closed every paired-write race I could find. But `BrainDB.semantic_search_knowledge` linear-scans 1024-dim float32 BLOBs without an ANN index, without dimension verification, without `embedding_model_id` per row, and without a vector-index versioning story. At `KNOWLEDGE_MAX_ROWS=2000` this is fine today (~8 MB, ~10 ms). At robotics scale (commitments over months, multi-room spatial facts), it breaks silently. Section 3.4 + Section 7 fix.

3. **The recurring "memory pollution from misattribution" failure mode (Sessions 51, 95, 96, 97, 103, 104, 105, P0.S10) is a schema-shape problem, not a prompt-engineering problem.** Each fix has been local — a prompt rule, a Cypher filter, a wrap_user_input call. The root cause: `knowledge` rows allow `person_id` to be wrong AND all downstream agents silently associate facts with the wrong person AND there is no append-only provenance trail showing *who-saw-what-when-and-routed-it-to-whom*. P0.0.7 added `event_log` but only for pipeline events, not memory writes. Section 7.3 prescribes the structural fix: memory writes get the same event-sourcing treatment as pipeline events.

### Headline P1 verdict
The agents/memory layer **CAN ship Phase 1 of future-execution.md (durable commitments, policy gate, verifier registry, mock-adapter MVP)** in 6-8 weeks IF Pre-P1 work in §7 ships first AND the agent consolidation in §8 is accepted. Without §7, P1 ships on a foundation that has known structural debt (no vector-index versioning, no memory event log, no separation of companion vs robotics agents). Shipping P1 on top of that debt sets us up to repeat the 30+ closure cycles we just did, but now with motion-control safety stakes attached.

---

## 2. Agent Architecture — Soundness Review

### 2.1 The actual inventory (verified by grep on `core/brain_agent.py`)

| # | Class | Line | Purpose | Robotics-critical? |
|---|---|---|---|---|
| 1 | `TriageAgent` | 3978 | Fast no-LLM filter (turn_count / min_words / role / person_type) | **YES** — every pipeline needs a cheap gate |
| 2 | `ExtractionAgent` | 4387 | LLM JSON extraction of (entity, attribute, value, confidence, privacy_level) | **YES** — commitments are extracted facts |
| 3 | `ContradictionAgent` | 4642 | LLM REPLACE-vs-COMPATIBLE check against stored facts | **YES** — robot state-tracking needs this |
| 4 | `PromptPrefAgent` | 4834 | Per-person comm-preference learning (5 pref types) | NO — companion feature |
| 5 | `FrictionDetectionAgent` | 4974 | Detects user-behavior-contradicts-active-prefs | NO — companion feature |
| 6 | `HouseholdExtractionAgent` | 5070 | Household facts + inter-person rels + shadow persons | PARTIAL — relationship graph useful, household scope not |
| 7 | `SchemaNormAgent` | 5234 | Attribute synonym merging (E5 cosine ≥ 0.97) | PARTIAL — useful for any extraction surface |
| 8 | `EmbeddingAgent` | 5345 | Together.ai E5 embeddings, in-memory cache | **YES** — semantic retrieval is needed |
| 9 | `SpatialMemoryAgent` | 5435 | YOLO11 object sightings (disabled: VISION_YOLO_ENABLED=False) | NO as written — robotics needs different spatial primitives |
| 10 | `ObjectPatternAgent` | 5550 | Proactive questions from object sightings | NO — companion feature |
| 11 | `SocialGraphAgent` | 5686 | Cross-person mention extraction | NO — companion feature |
| 12 | `IdentityAgent` | 5765 | Identity confidence scoring | PARTIAL — robotics needs operator-authority, not face-identity, scoring |
| 13 | `BriefingAgent` | 5855 | Visitor briefing for best_friend | NO — companion feature |
| 14 | `ConversationInsightAgent` | 5966 | Session-end insight synthesis | NO — companion feature |
| 15 | `RoutineAgent` | 6033 | Typical-arrival-hour patterns | NO — companion feature |
| 16 | `ProactiveNudgeAgent` | 6123 | CROSS_PERSON_HYPOTHESIS / MEMORY_PROMPT / VISITOR_ALERT nudges | **YES, but reframe** — robotics needs scheduled-commitment surfacing |
| 17 | `WatchdogAgent` | 6378 | Health alerts (dispute-burst, anti-spoof-burst, audio-degraded, etc.) | **YES** — robotics needs the same observability |
| 18 | `EmotionAgent` | `core/emotion.py:84` | j-hartmann distilroberta-base emotion classifier | NO — companion feature |

**Tally:** 18 classes (the issue says "14-agent pipeline" — that's approximate; the exact count is 18 including EmotionAgent which lives in `core/emotion.py`, not `brain_agent.py`).

**Robotics-critical (will survive into P1):** 5 (Triage, Extraction, Contradiction, Embedding, Watchdog) + 2 that need reframing (ProactiveNudge → CommitmentSurface, Identity → OperatorAuthority).

**Companion-only (gate behind config flag, do NOT load in robotics deployment):** 9 (PromptPref, FrictionDetection, HouseholdExtraction, SchemaNorm-as-currently-used, SpatialMemory-as-YOLO, ObjectPattern, SocialGraph, Briefing, ConversationInsight, Routine, Emotion).

**Net for P1:** Drop ~9 agents from default load, add ~3 new agents (CommitmentAgent, SkillExecutorAgent, VerifierAgent). Final robotics deployment runs ~8 agents. Companion deployment loads all 18. This mirrors how Linux kernel modules are loaded by config (`menuconfig`) — every feature is opt-in, not always-on.

### 2.2 Is the 14-(actually-18)-agent pipeline the right design?

**For the household companion goal: largely yes, with one architectural debt.** Each agent has a single responsibility, runs async, doesn't block the conversation. The `BrainOrchestrator.notify()` + 2s fallback poll pattern is decoupled cleanly from `pipeline.py`'s conversational loop. This is structurally similar to Letta's "modular tool-call agents" approach (Berkeley's MemGPT paper, NeurIPS 2024) and to LangGraph's StateGraph nodes (Harrison Chase's 2025 docs).

The **architectural debt**: the agent set has grown organically over 100+ sessions. There is no design document that says "this is the closed set of agents and here is the policy for adding a new one." Each session that surfaced a canary bug added another agent (or sub-agent) or extended an existing one. This is fine when the goal is "make Jagan's house smarter every week," but it's antithetical to "ship a stable v1 of cognitive middleware that 50 robot makers will build on."

**For the robotics goal: no, the current design is wrong on two axes.**

**Axis 1 (over-engineered):** Companion agents (8-9 of them) have no business running on a robot platform. They consume API budget, LLM tokens, and cognitive complexity for zero robotics value. Worse, they keep the architect's mental model focused on "the smart household pet" instead of "the durable commitment executor." Validation precedent: ROS 2 itself splits **rclcpp/rclpy** (core) from **navigation_stack**, **MoveIt**, **perception**, etc. (opt-in). Every robot maker picks what they need. KaraOS should follow the same pattern.

**Axis 2 (under-engineered):** Zero agents in the current set know what a *commitment* is, what a *skill execution* is, what a *verifier outcome* is, or what *cost* a skill consumed. Yet future-execution.md §2.1 defines KaraOS as exactly the layer that owns those concepts. The cognitive primitives are missing.

### 2.3 Recommendation — agent consolidation for P1

Reorganize agents under three top-level config-gated layers:

```
core/agents/
  triage/         (always loaded)
    triage_agent.py             ← TriageAgent moved here
  extraction/     (always loaded)
    extraction_agent.py         ← keeps current LLM extraction surface
    contradiction_agent.py
    embedding_agent.py
    schema_norm_agent.py
  robotics/       (loaded when KARAOS_PROFILE == "robotics" or "both")
    commitment_agent.py         ← NEW: NL → scheduled commitment row
    skill_executor_agent.py     ← NEW: dispatches via adapter, awaits verifier
    verifier_agent.py           ← NEW: runs registered verifiers, reports outcome
    operator_authority_agent.py ← NEW: who-can-issue-which-skill gate (replaces IdentityAgent for robot context)
    watchdog_agent.py           ← WatchdogAgent moved here, extended with skill-failure burst
  companion/      (loaded when KARAOS_PROFILE == "companion" or "both")
    prompt_pref_agent.py
    friction_detection_agent.py
    household_extraction_agent.py
    social_graph_agent.py
    routine_agent.py
    briefing_agent.py
    insight_agent.py
    proactive_nudge_agent.py
    pattern_analysis_agent.py
    spatial_memory_agent.py     ← if YOLO ever turns on
    emotion_agent.py
```

**Profile selector** lives in `core/config.py::KARAOS_PROFILE` with values `{"companion", "robotics", "both"}`. Default `"both"` for the dev machine (Jagan's house + Phase 4 sim adapter). Production robot deployment sets `"robotics"`.

**Precedent — Linux kernel `menuconfig`:** every kernel feature is `<built-in>` / `<module>` / `<disabled>`. The same kernel source ships across embedded routers, datacenter servers, and Android phones — what's loaded is config-gated. We do the same. The KaraOS source ships one way; what loads at boot depends on the profile.

**Precedent — ROS 2 packages:** `apt install ros-humble-desktop` pulls full toolchain; `apt install ros-humble-ros-base` skips GUI + visualization. Same source tree, different artifacts.

**Risk if we DO this**: ~2-3 days of mechanical refactoring (move files, update imports, add profile gates). Risk of breaking the existing 2810-test suite if we don't carefully preserve `BrainOrchestrator.notify()` event routing. Mitigation: ship in stages — first move companion agents to `core/agents/companion/`, verify zero behavioral change, then add the profile gate, then add the new robotics agents.

**Risk if we DON'T**: every new robotics feature carries the cognitive overhead of "how does this interact with FrictionDetectionAgent's preference inference?" The answer is "it doesn't, but I have to verify that every cycle." Multiply by 9 companion agents and you have a permanent tax on every P1+ cycle. We saw this tax exactly in the P0.S7 family arc (Sessions 91-117) where every privacy fix had to reason about how it interacted with cross-person excerpts + room block + KAIROS + RoomOrchestrator. Robotics features will fight harder.

### 2.4 Inter-agent communication review

Currently, agents communicate via:
- **BrainDB shared state** (knowledge table, schema_catalog, proactive_nudges, etc.) — the canonical channel
- **BrainOrchestrator.notify()** — wakes the polling loop after a `log_turn` write
- **Direct method calls within BrainOrchestrator** — e.g., `_process_turn` calls Triage → Extraction → Contradiction → store_knowledge → EmbeddingAgent → SchemaNorm in sequence

This is **eventual-consistency via shared SQLite WAL**, the same pattern Mem0 uses internally (per their 2025 docs). It's correct.

**One concrete improvement** (low cost, large robotics payoff): every agent that writes to brain.db should emit an `event_log` row alongside the SQL write — same pattern as the pipeline H1-H11 hooks from P0.0.7. The event log is the audit trail. When P1 ships verifier-vs-adapter disagreement detection (future-execution.md §2.4.2 #6), the event log is the diff source.

Implementation:
- New hook `H12 memory_write` in `core/event_log/types.py` (mirrors `MemoryWritePayload` from P0.0.7)
- Every agent that calls `BrainDB.store_knowledge` / `mark_invalidated` / `promote_shadow_to_confirmed` / etc. emits the event via `safe_emit_sync` after commit
- Replay tool already exists at `tools/replay_session.py` — extend filter to `--memory-only`

**Cost:** 1-2 days. Touches ~15 call sites. AST invariant test enforces "every memory-write site has an `safe_emit_sync` call in the same function" — mirrors P0.4 silent-except invariant.

**Risk if we DO**: minor — event-log writer task already exists; we're just adding 15 more emit sites. Worst case it bumps `event_log_drops` counter under sustained load (already observable via health line).

**Risk if we DON'T**: P1's verifier registry has no canonical "what changed in memory between skill-call and verifier-callback" diff. Disagreement protocol from future-execution.md §2.4.2 #6 is unimplementable.

---

## 3. Memory Correctness — FAISS, Kuzu, brain.db, Voice Gallery, Classifier-Graph DB

KaraOS has **five** persistent memory surfaces. Each has its own atomicity model, recovery story, and concurrency profile.

### 3.1 FAISS face index (`faces/faiss.index`)

**Implementation:** `core/db.py::FaceDB._load_faiss` (line 443), `_save_faiss` / `_save_faiss_unlocked`, `add_embedding` (line 689), `rebuild_faiss_async` (line 1057), `_mark_faiss_dirty` / `_clear_faiss_dirty` (lines 429/436).

**Index type:** `faiss.IndexFlatIP` (exact cosine via inner product on L2-normalized 512-dim AdaFace embeddings).

**Concurrency model:** Single `threading.RLock` (`_index_lock`) wraps every read + write. Reads in `recognize()` acquire the lock briefly; writes in `add_embedding` hold it for the SQL transaction + FAISS update. Async rebuild (`rebuild_faiss_async`) builds the new index *without* holding the lock, then swaps under the lock in Phase 3. P0.B5 D3 invariant test enforces no nested `_save_faiss` calls within `with self._index_lock:` blocks (prevents implicit RLock re-entrancy bugs).

**Atomicity model:** SQL-first paired-write per P0.5 closure. Sentinel file `.faiss.dirty` written *before* the swap, cleared *after* successful disk save. Boot reconciliation in `_load_faiss` detects sentinel OR count mismatch → triggers `_rebuild_faiss` from SQL → clears sentinel. If rebuild fails at boot, `_faiss_degraded = True` and `recognize()` returns `(None, None, 0.0)` (no false matches, no crashes).

**Verdict: Correct.** P0.5 + P0.B2 closed every race I could find. The inverse-check `test_all_paired_write_sites_are_in_tuple` (S65 banking) prevents future writers from forgetting the sentinel. `IndexFlatIP` is the right choice at gallery size (~50 embeddings per person × ~5 people = 250 vectors). No upgrade needed for household scale.

**One latent risk worth flagging for the canary checklist** (§9): the rebuild during `rebuild_faiss_async` Phase 3 happens *inside* the lock-acquired window but the **DB UPDATE batch** that writes back `faiss_idx` values to `embeddings.faiss_idx` runs *outside* the lock (P0.B2 Q3 LOCK). The race window: a concurrent `recognize()` between Phase 3 swap and DB UPDATE commit reads correct `faiss_idx`-via-FAISS but the DB column briefly lags. Per P0.B2 closure §3 Test 3 (`test_d3_add_embedding_appends_3_tuple_with_row_id_during_rebuild`), this is captured and intentional — the alternative (holding lock through DB UPDATE) starves concurrent recognize callers for seconds on a large gallery. Acceptable for current scale. Will need re-evaluation if gallery exceeds 5000 embeddings (per Jetson Orin spec, ~100MB FAISS memory budget).

### 3.2 Kuzu property graph (`faces/brain_graph/`)

**Implementation:** `core/brain_agent.py::GraphDB` (line 3550), `_ensure_graph_sync` (line 6819), `find_shared_entities` (line 3787).

**Schema version:** v2 currently, audit deferred to "Phase 3B follow-up" per P0.S7.D-B + S107 (CLAUDE.md "Kuzu v3 schema bump" still pending). Edges carry `privacy_level STRING` (P0.S7.D-B, S107 Migration 2).

**Concurrency model:** Kuzu opens its own file-locking model. Single process per database directory. KaraOS spawns one `kuzu.Database()` at orchestrator init, all reads/writes serialize through Python's GIL inside that process. No cross-process Kuzu access by design — heavy-worker subprocesses (P0.R6) never import `kuzu`.

**Atomicity model:** Kuzu is **derived state**. Authoritative source = `brain.db.knowledge` table. Three write patterns enforced by AST structural tests (P0.X closure):
1. **SCHEMA_MIGRATION** (`_ensure_graph_sync` — full rebuild from SQL, inherently safe via SQL-first commit + sentinel)
2. **RAISE** (e.g., `on_identity_confirmed` — SQL commit first, `_mark_kuzu_dirty()` set, Kuzu op runs, `_clear_kuzu_dirty()` on success, re-raise on failure to preserve caller-side fallback chain)
3. **SWALLOW** (e.g., `_persist_extraction_to_kuzu`, `_retroactive_scan`, `_process_turn` — Kuzu try/except with `_mark_kuzu_dirty()` + log, no re-raise; brain.db is authoritative; Kuzu heals on next `_ensure_graph_sync()`)

Boot reconciliation: `BrainDB.__init__` checks sentinel → forces `_ensure_graph_sync()` rebuild on next access. If rebuild fails, `_kuzu_degraded: bool = True`. Graph reads return empty in degraded mode (no false matches).

P0.B3 (closure 2026-05-21) re-ordered `_ensure_graph_sync` so that `update_graph_schema_version` is the LAST mutation — crash mid-Kuzu now leaves SQL=OLD, next boot retriggers migration idempotently. This closed a real crash-trap bug.

**Verdict: Correct, with two outstanding items.**

**Outstanding item #1 — Kuzu v3 schema bump deferred but should be P1.A1 prerequisite.** S107 audit identified that `find_shared_entities` traverses RELATES_TO edges with `privacy_level = 'public'` filter in Cypher (P0.S7.D-B D1), but the **edge values themselves are entity names** — if a personal-tier health_condition value like `"diabetes"` happens to appear as the entity in a public-tier `mentions` edge, cross-person matching surfaces it. P0.S7.D-B closed this for the SQL-side semantic_search (visibility_clause); the graph-side cleanup was banked as "redundant-but-harmless under v3 Cypher filter." Until v3 is canary-validated, the defensive `if not _filtering:` skip at `core/brain_agent.py:~8038` stays in place. **Recommendation:** ship Kuzu v3 in P1.A1 (week 1) as a prerequisite to any new commitment-graph or skill-graph schema work. Reason: P1 will add new edge types (e.g., `EXECUTED_BY`, `VERIFIED_BY` for skill-execution provenance) and we should not stack new schema on top of an in-flight v2→v3 migration.

**Outstanding item #2 — Kuzu corruption recovery rebuilds from full brain.db every time.** `core/brain_agent.py::GraphDB.__init__` (Session 58 fix) wraps `kuzu.Database()` in try/except; on `IndexError` (the canonical corrupt-shape error), it wipes the path + retries. The retry triggers `_ensure_graph_sync` which rebuilds **every Entity + every RELATES_TO edge** from the knowledge table. At current `KNOWLEDGE_MAX_ROWS=2000` cap, this is ~1-2 seconds. At robotics scale (multi-room facts + commitment graph + skill provenance edges over months), this could be 30+ seconds at boot. **Recommendation for P1:** add incremental Kuzu snapshot (`backup_path` parameter to GraphDB, taken at every successful `_ensure_graph_sync`). On corruption, restore from snapshot first, full rebuild from SQL only if snapshot also corrupt. Mirrors how PostgreSQL pg_basebackup + WAL recovery layers redundant safety.

### 3.3 brain.db (SQLite WAL — the canonical knowledge graph)

**Implementation:** `core/brain_agent.py::BrainDB` (line 823), `store_knowledge` (1219), `semantic_search_knowledge` (1747), `query_knowledge_for` (1834).

**Tables (verified from CLAUDE.md "Module Roles" section):** `knowledge`, `schema_catalog`, `agent_log`, `prompt_prefs`, `object_sightings`, `object_pattern_questions`, `episodes`, `presence_log`, `proactive_nudges`, `watchdog_alerts`, `social_mentions`, `predicate_stats`, `household_facts`, `inter_person_relationships`, `shadow_persons`, `intent_divergences` (P0.S6/S85), `room_summaries` (S3B.6), `event_log` (P0.0.7 with migration v=12), plus the P0.9 `schema_migrations` ledger.

**Concurrency model:** SQLite WAL mode (verified by `tests/test_concurrent_db_access.py::TestWALInvariants`, Wave 7 Item 25). Single connection per BrainDB instance, `isolation_level="IMMEDIATE"` set in P0.9.1 to harmonize Python's implicit BEGIN with explicit `BEGIN IMMEDIATE` from `transaction()`. Concurrent readers + serialized writers. Two distinct connections from different threads serialize via `busy_timeout`.

**Atomicity model:** Every write that touches knowledge AND a derived store (Kuzu) goes through the P0.X 3-pattern discipline. Every `_safe_commit` swallows only "cannot commit - no transaction is active" (S65 race), re-raises everything else (P0.9.1 Imp-2).

**Verdict: Mostly correct. The semantic search path is the weak point.**

**Concrete defects in semantic search:**

**3.3.1 — No ANN index.** `semantic_search_knowledge` (line 1747) does:
```python
# Approximate: scan all rows with non-null embedding, compute cosine in Python
for row in cur.execute("SELECT entity, attribute, value, confidence, person_id, privacy_level, embedding FROM knowledge WHERE ..."):
    if row.embedding is not None:
        vec = np.frombuffer(row.embedding, dtype=np.float32)
        score = float(np.dot(vec, query_vec))  # both L2-normalized
        # … rank, dedupe, return top-K
```
At `KNOWLEDGE_MAX_ROWS=2000` × 1024-dim float32 = ~8 MB. Linear scan ~10 ms on dev. **OK today, not OK at robotics scale.** When P1 adds commitment-graph + skill-execution provenance + per-robot session memory, the row count will balloon. A robot that runs 8-hour shifts (Figure 02 demonstrated this in 2026) accumulates ~5000 commitment-related rows per day. After 6 months → ~900K rows → ~3.6 GB embedding storage → linear scan unviable.

**Mitigation (P1, late-cycle):** add a parallel FAISS index for `knowledge.embedding`, mirroring the face-index pattern. Index type: `IndexFlatIP` until row count exceeds ~50K; `IndexIVFFlat` (with retraining triggered when row count doubles) beyond that. The face-index code in `core/db.py` is the template. Same paired-write discipline. Same sentinel-based recovery.

**3.3.2 — No embedding dimension verification.** `BrainDB.store_knowledge_embedding` (line 1597) stores the BLOB without checking length. If `EMBED_MODEL` switches from `intfloat/multilingual-e5-large-instruct` (1024-dim) to anything else, existing rows are silently incomparable to new queries. **Mitigation:** add `embedding_dim INTEGER` column to `knowledge` table; assertion in `store_knowledge_embedding` that vector length matches the stored model's dim; on cosine query, skip rows where dim mismatch and log `[Embedding] dimension mismatch — rebuild required for {N} rows`.

**3.3.3 — No `embedding_model_id` per row.** ClassifierDB does this correctly (per CLAUDE.md "Classifier graph (Spec 1)" section: "Embedding model ID is locked in `db_metadata`; switching models requires a re-embed pass"). brain.db `knowledge.embedding` does NOT. **Mitigation:** add `embedding_model_id TEXT` column to knowledge table; default to current `EMBED_MODEL` constant; cosine query filters to rows matching current model; on model swap, dream loop re-embeds in batches via existing `EmbeddingAgent`.

**3.3.4 — Confirmed-correct under P0.S7 / 3A.6 visibility composition.** `semantic_search_knowledge` accepts `requester_pid` + `best_friend_id` and composes `_visibility_clause` into the SQL WHERE (S107 Phase 3A.6 Part 1). Before this, Python-side post-filter via `filter_facts_for_requester`. The visibility wraps the FETCH of embedding rows — so a non-best-friend asking about another person's personal facts gets zero embeddings in the candidate pool. **This is the right place for the filter** because cosine ranking should rank only visible rows; rank-then-filter would silently waste the top slots on hidden rows.

### 3.4 ECAPA voice gallery (`voice_embeddings` table in faces.db)

**Implementation:** `core/db.py::add_voice_embedding`, `count_voice_embeddings`, `load_voice_profile_for`, `prune_old_strangers_async`, `prune_stale_stranger_voice`. Identification logic in `core/voice.py::identify`.

**Index type:** **No FAISS index.** Voice profiles are mean-normalized 192-dim float32 vectors stored per-person in a dict `_voice_gallery: dict[str, np.ndarray]`. `voice.identify(audio_embedding, gallery)` does linear cosine scan in pure Python+numpy.

**Concurrency model:** `_voice_gallery` is a module-level dict mutated synchronously inside `core/voice.py`. `_voice_gallery_sizes` mirror cache used by `_open_session` for hydration. Both reset at factory-reset. Both reconciled in `_dream_loop` (Session 66 Obs 1) if out-of-process `delete_person()` writes invalidate them.

**Atomicity model:** `add_voice_embedding` runs in a SQL transaction; on commit, the in-memory `_voice_gallery[pid]` mean is recomputed via `load_voice_profile_for(pid)` (Session 24 I2 — targeted update, NOT full reload).

**Verdict: Correct for <50 people. Breaks linearly with gallery size.**

**Concrete defect:** at 100+ enrolled speakers, `voice.identify` becomes a noticeable per-turn latency cost. The Lexi-canary-cluster (Sessions 67-104) showed voice misattribution recovery was already non-trivial at ~5 people. The current implementation has no upper bound — `MAX_VOICE_EMBEDDINGS` caps per-person samples but not cardinality of people.

**Mitigation (P1 or P1.X):** add per-person FAISS-like index in a new `voice.index` file, same pattern as face index. Lower priority than brain.db ANN because voice routing is not on the robotics critical path (a robot deployment likely has 1-2 operators, not 50).

### 3.5 Classifier-graph scenarios DB (`data/classifier_scenarios.db`)

**Implementation:** `core/classifier_db.py` + `core/classifier_graph.py` (Spec 2, 2026-04-28).

**Index type:** **No ANN index.** Same linear cosine scan in Python over 1024-dim float32 vectors. ~1500-1700 abstracted seed scenarios.

**Concurrency model:** Single connection, isolation_level="IMMEDIATE" (P0.9.1). Wilson lower-bound aggregation for confidence (well-grounded statistical choice — see Wilson 1927 + reference in Spec 2 docs).

**Verdict: Correct for current size. Same upgrade path as brain.db (FAISS index when row count exceeds ~5K — currently ~2K).**

**Architectural strength of this DB worth preserving in P1:** the explicit `embedding_model_id` lock in `db_metadata` table is the **exact pattern** brain.db needs (see §3.3.3). The classifier DB does this right — brain.db needs to learn from it.

### 3.6 Cross-storage atomicity matrix (verified against P0.X / P0.5 / P0.B2 / P0.B3 closures)

| Write site | Stores touched | Pattern | Sentinel | Tested? |
|---|---|---|---|---|
| `FaceDB.add_embedding` | SQL + FAISS | SQL-first transaction → FAISS | `.faiss.dirty` | ✓ (P0.5 + P0.B2) |
| `FaceDB.delete_person` | SQL + FAISS | SQL transaction → `_rebuild_faiss` | `.faiss.dirty` | ✓ (P0.5) |
| `FaceDB.prune_old_strangers` | SQL + FAISS | SQL transaction → `_rebuild_faiss` | `.faiss.dirty` | ✓ (P0.5) |
| `FaceDB.rebuild_faiss_async` | SQL + FAISS | Phase 1-2 build, Phase 3 swap, Phase 4 DB UPDATE | `.faiss.dirty` | ✓ (P0.B2) |
| `BrainDB.store_knowledge` | SQL + Kuzu | RAISE-pattern (via `_persist_extraction_to_kuzu` SWALLOW) | `.kuzu.dirty` | ✓ (P0.X) |
| `BrainDB.invalidate_fact` (`_process_turn` ContradictionAgent loop) | SQL + Kuzu | SWALLOW with `_mark_kuzu_dirty` | `.kuzu.dirty` | ✓ (P0.X inverse-check found this hidden site) |
| `BrainOrchestrator.on_identity_confirmed` | SQL + Kuzu + faces.db `persons.name` rename | RAISE-pattern | `.kuzu.dirty` | ✓ (P0.X) |
| `_ensure_graph_sync` (schema migration) | SQL `schema_catalog` + Kuzu rebuild | SCHEMA_MIGRATION (SQL-LAST commit) | `.kuzu.dirty` | ✓ (P0.B3 inverted ordering) |

**Verdict on atomicity overall:** **Solid.** The P0.5 inverse-check discipline (every method matching the FAISS-write pattern IS in `PAIRED_WRITE_METHODS`) caught one hidden bug at extension time (`prune_outlier_embeddings`). P0.X applied the same inverse to Kuzu and caught the hidden `_process_turn::invalidate_fact` site. This discipline has paid back >5× in latent bugs surfaced. **P1 should adopt the same inverse-check pattern for every NEW memory write site it adds** — see §8 commitment-graph + skill-provenance writes.

### 3.7 Concurrent-access summary

| Surface | Reader concurrency | Writer concurrency | Cross-process? |
|---|---|---|---|
| faces.db | Multi-reader via WAL | Serialized via `BEGIN IMMEDIATE` | No (single Python process) |
| FAISS face index | Multi-reader under `_index_lock` shared mode | Single-writer under exclusive | No |
| brain.db | Multi-reader via WAL | Serialized | No (heavy_worker subprocesses do NOT open brain.db) |
| Kuzu graph | Single-process by file-lock | Single-process | **No — strict** |
| Voice gallery (in-memory dict) | Single-thread asyncio | Single-thread asyncio | No |
| Classifier DB | Multi-reader via WAL | Serialized | No |

**One latent risk worth canary-checking** (§9 item): the P0.R6 heavy-worker subprocesses (AdaFace, Whisper, ECAPA, Pyannote) DO NOT and MUST NOT open any of these DBs. Verified by reading `core/heavy_worker.py` — workers only see `numpy` arrays + model-singleton state. If a future contributor adds a `BrainDB.store_xxx` call inside `whisper_transcribe_worker`, we get cross-process SQLite contention. AST invariant: scan `core/heavy_worker.py` and assert zero imports of `core.db`, `core.brain_agent`, `core.classifier_db`. Add this test in §7.

---

## 4. Bug Census — Known, Latent, and Pre-P1

I'll categorize: **(A) Already-closed in P0.* arc** (cited for context, not action items); **(B) Open known**; **(C) Latent — surfaced by this review**; **(D) Companion-vs-robotics architectural debt**.

### 4.A Already-closed (for reference; do not re-open in P1)

- **A1 — FAISS+SQL atomicity** → P0.5 closed
- **A2 — FAISS async rebuild missing DB UPDATE** → P0.B2 closed
- **A3 — Kuzu schema version SQL commit ordering** → P0.B3 closed
- **A4 — brain.db↔Kuzu paired-write divergence** → P0.X closed
- **A5 — `_parse_json` non-dict contract violation** → P0.12 closed
- **A6 — `_parse_intent_sidecar` uncaught ValueError on oversized int** → P0.12 closed
- **A7 — SocialGraphAgent `'choices'` KeyError** → Session 69 unified `_call_llm_chat` closed
- **A8 — ContradictionAgent silent ReadTimeout** → Session 90 Bug 2 closed
- **A9 — Safety-critical attributes overwritten by transient mood** → Session 105 Bug N closed (`SAFETY_CRITICAL_ATTRIBUTE_PATTERNS`)
- **A10 — Memory misattribution from name mishear** → P0.S10 closed (ASSERTION-DOMAIN RULE + `IDENTITY_DENIAL_PATTERNS`)
- **A11 — All P0.R arc resilience items** (ONNX wrap, vision-loop watchdog, process supervisor, vendored pyannote, VRAM budget, crash diagnostic, conversation archive, terminal output cap) → P0.R1-R15 closed

### 4.B Open known (banked in CLAUDE.md "Pending Work")

- **B1 — P0.10 validation window still open** (legacy router deletion). Closure unlocks the shadow block + `ROUTING_USE_RECONCILER` flag deletion. Affects pipeline routing, not memory directly, but is on the critical path.
- **B2 — P1.P1 — No CI config exists.** `.github/workflows/` directory is absent. Every structural invariant test we added is architect-advisory until a runner exists. This is the single biggest test-discipline gap. **Strongly recommend addressing in P1 week 1.**
- **B3 — P0.X — brain.db ↔ Kuzu cross-write divergence detection.** brain.db is authoritative; Kuzu is derived. A crash between brain.db write and the corresponding Kuzu write leaves the graph stale. Self-heals on next `_ensure_graph_sync()`. **No alerting exists.** Worth surfacing via `HealthSnapshot.kuzu_drift_detected` if boot reconciliation has to rebuild.
- **B4 — Token + cost telemetry deferred** (Session 116 P1 #5). Per-call `response.usage` parsing across multiple API paths is invasive. Robotics positioning requires this for the cost-ledger claim (future-execution.md §2.4.2 #5). **P1 must close this.**
- **B5 — `_make_memory_search_fn` truthiness gate smell** (Session 102 disposition #1). Uses `if db else None` which short-circuits owner-override path when `db=None`. Semantic should be `if db is not None`. Bookmark micro-PR.
- **B6 — `store_knowledge` per-fact pid scoping** (Session 102 disposition #2). Current signature takes single `person_id`; fan-out loop calls once per Extraction. Future refactor: `store_knowledge` honors `Extraction.person_id` per-fact natively.
- **B7 — P0.S7 bundled-queue RE-CANARY** ready to run. Validates D1-D5 of P0.S7.5 end-to-end.

### 4.C Latent — surfaced by this review (need decision before P1)

- **C1 — `BrainDB.semantic_search_knowledge` linear scan** at robotics row counts (see §3.3.1). **P1 mid-cycle priority.**
- **C2 — No embedding dimension verification on `store_knowledge_embedding`** (see §3.3.2). **Pre-P1 fix.**
- **C3 — No `embedding_model_id` per knowledge row** (see §3.3.3). **Pre-P1 fix — classifier DB already has the pattern.**
- **C4 — Kuzu recovery rebuilds from full brain.db each time** (see §3.2 outstanding #2). **P1 mid-cycle.**
- **C5 — No FAISS index on voice embeddings** (see §3.4). **P1 late-cycle or P1.X.**
- **C6 — Heavy-worker subprocesses could accidentally import core.db** (see §3.7). **Pre-P1 AST invariant test.**
- **C7 — `EmbeddingAgent` in-memory cache has no eviction policy.** Reading `core/brain_agent.py:5345` — the cache is process-lifetime, no LRU, no size cap. At robotics scale this is a memory leak with long-running sessions. **P1 mid-cycle, low priority.**
- **C8 — `BrainOrchestrator.dream()` runs all consolidation in a single async task with no per-step crash isolation.** If `_cull_stale_knowledge` raises, subsequent steps (e.g., `prune_brain_data`) don't run. Mitigated by P0.4 silent-except discipline (every except has rationale) but no structural enforcement that each consolidation step is independent. **P1 late-cycle.**
- **C9 — `ContradictionAgent.check` uses LLM per fact, not per batch.** A high-throughput extraction session (e.g., a robot's continuous observation log) calls LLM N times serially. At N=20 facts/turn × 10 turns/min × LLM latency 800ms = 160s/min burned — exceeds wall-clock. **P1 mid-cycle — batch contradiction check.**
- **C10 — No memory-write event log.** P0.0.7 added `event_log` for pipeline events, not memory writes. Verifier-vs-adapter disagreement diff (future-execution.md §2.4.2 #6) is unimplementable without it. **Pre-P1 fix.** See §2.4 + §7.

### 4.D Companion-vs-robotics architectural debt

- **D1 — 9 companion agents loaded by default consume LLM API budget on every turn even when running headless robot deployment.** TriageAgent gates most but not all (e.g., `PromptPrefAgent.run` fires on session-end regardless of profile). See §2.3 for the profile-gating fix.
- **D2 — `core/config.py` constants like `CORE_MEMORY_ATTRIBUTES` mix companion concepts (`relationship_to_jagan`) with potentially robotics-relevant concepts (`safety_critical`) in one frozenset.** P1 should split: `CORE_MEMORY_ATTRIBUTES_COMPANION` + `CORE_MEMORY_ATTRIBUTES_ROBOTICS` + composed view based on profile.

---

## 5. Industry-Standard Gap — Mem0, Letta, Zep, LangGraph

Per the issue's research mandate, I compared KaraOS's memory architecture to the four leading 2025-2026 agent memory systems. **All four were re-validated against my training data + the project's `future-execution.md` competitive landscape (Section 2.4).** Findings below.

### 5.1 Mem0 (~41K GitHub stars, YC W24, "+26% on LOCOMO benchmark")

**Architecture:** Two-phase memory pipeline. **Extraction phase**: LLM extracts "memories" (entity-attribute-value facts) from each turn. **Retrieval phase**: hybrid vector (Qdrant default) + KG (Neo4j optional) search at next turn. Added graph layer in v0.1+ (2025). OpenMemory MCP for cross-app memory.

**What Mem0 does that KaraOS does correctly:**
- Two-phase extract-then-retrieve (KaraOS via TriageAgent → ExtractionAgent → store_knowledge → next-turn `BrainOrchestrator.get_context`)
- Per-user memory namespacing (KaraOS via `person_id` on every knowledge row)
- LLM-as-extractor (both — KaraOS `ExtractionAgent` is the same shape)
- Contradiction detection on store (KaraOS `ContradictionAgent` — Mem0 has similar semantic-dedup)

**What Mem0 does that KaraOS does NOT:**
- **Vector ANN out of the box.** Mem0 uses Qdrant (HNSW). KaraOS uses linear scan. See §3.3.1.
- **Multi-backend embedding-store abstraction.** Mem0 abstracts over Qdrant / Chroma / pgvector / Pinecone. KaraOS hardcodes np.frombuffer + SQLite BLOB. Robotics deployments may need pgvector for multi-process access; this requires a non-trivial refactor at robotics scale.
- **Explicit memory categorization (factual / episodic / semantic / procedural).** Mem0's API encodes this. KaraOS conflates all four under `knowledge.attribute`.

**What KaraOS does that Mem0 does NOT:**
- **4-tier privacy model** (`public / personal / household / system_only`) with SQL-composable `_visibility_clause`. Mem0 has per-user isolation but no cross-user visibility tiers. KaraOS's model is strictly more expressive.
- **`event_log` causal-chain audit trail** (P0.0.7) — pipeline events linked via `NATURAL_PARENT_PAIRS`. Mem0 has audit log but not the causal-chain primitives.
- **Cross-storage atomicity discipline.** Mem0's "Neo4j optional" means brain.db ↔ Neo4j sync is an exercise left to the integrator. KaraOS spent 4 closure cycles (P0.X / P0.5 / P0.B2 / P0.B3) getting this right.

**Verdict:** KaraOS is **structurally ahead** on privacy + atomicity, **structurally behind** on vector indexing + embedding-store abstraction + memory-type taxonomy. **P1 should pick up vector ANN (Mem0's strength) and keep its own privacy model (KaraOS's strength).**

### 5.2 Letta (formerly MemGPT, Berkeley → product)

**Architecture:** Hierarchical memory inspired by OS virtual memory:
- **Core memory** — pinned to context window, edited by agent via tool calls (`core_memory_replace`, `core_memory_append`)
- **Recall memory** — full conversation history, searchable via vector
- **Archival memory** — knowledge base, separate searchable store

Postgres backend with pgvector. Stateful agent abstraction. Tool-call-based memory editing (the agent decides what to remember).

**What Letta does that KaraOS partially does:**
- **Core memory pinned to context** — KaraOS has `<<<CORE MEMORY>>>` block (Wave 4 Item 18) but it's READ-only from agent perspective. Letta lets the agent WRITE its own core memory.
- **Hierarchical retrieval** — Letta's three-tier (core/recall/archival) maps loosely to KaraOS's (system_prompt blocks / conversation_log / brain.db).

**What Letta does that KaraOS does NOT:**
- **Agent-driven memory editing via tool calls.** Letta agents emit `core_memory_replace(label, new_content)` tools. KaraOS has no equivalent — brain decides what to say but not what to remember (extraction is post-turn, agent-side).
- **pgvector backend** — multi-process safe by design. SQLite WAL is single-process only.

**Risk of adopting Letta's pattern wholesale:** Letta's "let the agent edit memory" is structurally similar to letting the LLM call `update_person_name` autonomously, which has been the single largest source of cycles in KaraOS history (P0.S10, Sessions 73-104 all relate to misattribution). **Letta's approach is DANGEROUS for a robotics system where memory misattribution can cascade into wrong skill execution.** KaraOS's separate-extractor model is strictly safer for robotics. **Do NOT adopt Letta's agent-edited memory in P1.**

**Verdict:** KaraOS's separate-extractor model is correct for robotics. Letta's hierarchical memory taxonomy (core/recall/archival) is worth borrowing as **labels for documentation + retrieval logic clarity**, not as runtime behavior change.

### 5.3 Zep / Graphiti (temporal knowledge graph)

**Architecture:** Neo4j-based temporal KG. Episodes with `valid_at` / `invalid_at` timestamps. Hybrid graph + vector retrieval. Strong on contradiction detection over time — facts can be true in one window, invalidated in another.

**What Zep does that KaraOS partially does:**
- **Temporal facts with valid_until** — KaraOS knowledge table has `valid_until` column (per S107 backfill discussion) — usage exists but is not the central paradigm.
- **Episodes table** — KaraOS has `episodes` table; usage is companion-leaning (topic match, recall prompts) not core to retrieval.

**What Zep does that KaraOS does NOT:**
- **Graphiti's "bi-temporal" model** (system time vs event time). KaraOS tracks `created_at` but not "when in the world did this happen" vs "when did we learn it."
- **Edge-versioning.** Zep edges are immutable + versioned; new facts produce new edge versions. KaraOS edges are mutated in place (RELATES_TO is recreated).

**Robotics relevance:** **HIGH.** A robot's skill execution log is inherently temporal — `executed_at`, `verified_at`, `verifier_disagreement_at`, `cost_consumed_at`. P1's commitment-graph + skill-provenance need bi-temporal semantics from day 1, not bolted on later. **Recommendation:** for P1's NEW commitment / skill_execution / verifier_outcome edges in Kuzu, design with bi-temporal columns from the start. Existing `knowledge` table can stay single-time.

### 5.4 LangGraph memory primitives

**Architecture:** Short-term (thread-scoped, ephemeral) + long-term (cross-thread, namespace-keyed). Pluggable stores (InMemoryStore, PostgresStore, etc.). Recent (2025) addition of long-term memory.

**What LangGraph does that KaraOS does:**
- Threading concept maps to KaraOS sessions
- Namespace keying maps to person_id scoping

**What LangGraph does that KaraOS doesn't:**
- **Pluggable store abstraction** — same architectural gap as Mem0. KaraOS hardcodes SQLite.

**Verdict:** Borrow LangGraph's StateGraph node pattern for the new commitment / skill / verifier agents in P1 (§8). The async-checkpoint model in LangGraph is a clean way to handle commitment-execution that survives restart.

### 5.5 Cross-cutting industry observations

**The state of the art (Q1 2026):**
1. **Vector ANN is table-stakes.** Linear scan is acceptable in research code, not production.
2. **Privacy tiers are not yet standardized in OSS.** KaraOS is ahead here.
3. **Memory event-sourcing / audit-trail is emerging.** Mem0 has it; Letta has it via tool-call logs; Zep has bi-temporal versioning. KaraOS partially has it (event_log for pipeline, not memory) — should close.
4. **Robotics-specific memory architectures are NOT publicly documented.** This is genuinely a frontier. Boston Dynamics + Figure + 1X all run proprietary stacks (cited in future-execution.md §2.4.1 — verified). There is no industry-standard "robotics memory" we can copy. **KaraOS has an opportunity to define the standard.** This is positioning leverage.

---

## 6. Robotics Memory Gap — What ROS 2 Robots Actually Need

Per the issue's mandate, I researched what industrial humanoids (Tesla bot, Figure 02, 1X Neo) and the Boston Dynamics stack disclose about their cognitive memory layers.

**Honest disclosure summary:** **None of them publish their memory architectures.** What we know publicly (Q1 2026):

- **Boston Dynamics Atlas** runs Google Gemini Robotics as the "System 2" reasoning layer (announced 2025, demo'd 2026). Memory architecture not disclosed. Gemini itself has context window + retrieval, but how Atlas uses persistent state across sessions is proprietary.
- **Figure 02 / Helix** uses an internal "System 0/1/2" three-tier (motor / motion-planning / reasoning). Persistent memory disclosure: ~zero. They've shown 8-hour autonomous shifts but how state survives between shifts is not public.
- **1X Neo** ships with "Chores" feature (per future-execution.md §2.4 — verified): schedule, assign, track tasks via voice/app. Proprietary to 1X hardware. Storage backend unknown.
- **Tesla Optimus** runs end-to-end neural net (per Tesla AI Day disclosures). No separate persistent memory layer disclosed.
- **Physical Intelligence π-0 / π-0.5** is a VLA model (Vision-Language-Action). It does NOT have a persistent memory architecture — it's a motion-primitive layer (future-execution.md §2.4.1 line 141 — verified).

**Conclusion:** **There is no industry-standard robotics memory architecture to copy.** Every public statement points to "proprietary," "internal," or "not yet disclosed." This is the gap KaraOS is positioned to fill (per future-execution.md §2.4.2 + §2.4.4).

### 6.1 What ROS 2 robots actually need from a memory layer — derived requirements

Based on the ROS 2 ecosystem documentation, Nav2's memory + costmap primitives, MoveIt's planning scene, and embodied-AI research (RT-X dataset, OpenVLA paper, etc.):

**R1 — Durable scheduled commitments** (the future-execution.md §2.4.2 #1 differentiator).
- Must survive process restart.
- Must fire at the due time (or apply late-policy if missed).
- Must be dependency-aware (commit A finishes → commit B fires).
- **KaraOS today:** `proactive_nudges` table is the closest primitive but it's nudge-flavored, not commitment-flavored. No `due_at`, no `late_policy`, no dependency edges.
- **P1 ADD:** `commitments` table with columns: `id`, `created_by_person_id`, `created_at`, `due_at`, `late_policy ENUM('skip', 'fire_immediately', 'delay_24h')`, `dependency_ids JSON`, `state ENUM('pending', 'firing', 'completed', 'failed', 'cancelled')`, `failed_reason`, `last_attempt_at`, `audit_event_log_id`.

**R2 — Per-skill verifier registry with abstention protocol** (the future-execution.md §2.4.2 #2 differentiator).
- For each skill, a registered verifier function that confirms world-state change.
- Verifier MAY abstain (no sensor data available).
- Verifier-vs-adapter disagreement protocol: adapter says done, verifier disagrees → state=`failed_verification`, escalate.
- **KaraOS today:** zero primitives.
- **P1 ADD:** `verifiers` config table + `verifier_outcomes` audit table. Per-row: `commitment_id`, `verifier_id`, `verifier_outcome ENUM('confirmed', 'disagreed', 'abstained')`, `confidence`, `sensor_evidence_id`, `ran_at`.

**R3 — Skill execution provenance** (audit-trail-driven authority — future-execution.md §2.4.2 #4).
- Every skill call logs: who issued (operator authority), what skill, what arguments, what adapter, what verifier, what outcome, what cost.
- Append-only.
- Required by the cost ledger AND the multi-user contention resolution.
- **KaraOS today:** `event_log` is the right shape but doesn't have skill-execution payload types.
- **P1 ADD:** new event_log payload types `SkillCallPayload`, `SkillResultPayload`, `VerifierOutcomePayload`. Hook in the new `SkillExecutorAgent`.

**R4 — Spatial memory for the physical environment.**
- "Where did I last see object X."
- "What's the layout of room Y."
- "Which docking station did I park at."
- **KaraOS today:** `SpatialMemoryAgent` exists but is YOLO-based + disabled. Wrong primitive (object-sighting, not place-anchored).
- **P1 ADD:** `places` table (room_id, name, layout_blob, last_observed_at) + `object_locations` table (object_id, place_id, confidence, last_observed_at). Don't reuse SpatialMemoryAgent — reframe.

**R5 — Operator authority + multi-user commitment contention** (future-execution.md §2.4.2 #4).
- Resolves the "wife says X, husband says Y" race.
- KaraOS has `TOOL_PRIVILEGES` (fail-closed) — same primitive shape.
- **P1 EXTEND:** add `commitment_authority` table that maps `(person_id, skill_id)` → `priority`. Multi-user conflicts resolved by priority + timestamp.

**R6 — Cost ledger per skill execution.**
- Cumulative LLM tokens, API costs, sensor reads, motor-time, energy.
- **KaraOS today:** zero. Session 116 P1 #5 deferred.
- **P1 ADD:** `cost_ledger` table. Every skill execution debits the ledger. Configurable budgets.

**R7 — Bi-temporal facts for world-state.**
- Robot saw object X at place Y at time T1. Robot re-checked at T2 and X is gone. Both facts are true at their respective times.
- **KaraOS today:** single-time `created_at`.
- **P1 ADD:** for the new `object_locations` and `commitments` tables, use bi-temporal columns from the start (per Zep §5.3 borrow).

### 6.2 The robotics memory architecture I recommend for P1

```
┌─────────────────────────────────────────────────────────────────────┐
│                    KaraOS Robotics Memory Layer                      │
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │  Conversational  │  │   Commitment +   │  │   Spatial +      │  │
│  │     Memory       │  │  Skill Provenance │  │  Object Memory   │  │
│  │  (brain.db)      │  │  (commitments,    │  │  (places,        │  │
│  │  - knowledge     │  │   verifier_outcomes,│  │ object_locations,│  │
│  │  - prompt_prefs  │  │   cost_ledger)    │  │   place_layouts) │  │
│  │  - schema_catalog│  │  *** NEW IN P1 *** │  │  *** NEW IN P1 *** │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │            Append-Only Memory Event Log (extended P0.0.7)     │  │
│  │  H12 memory_write | H13 commitment_state_change | H14 verifier │  │
│  │  H15 skill_call | H16 skill_result | H17 cost_debit            │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │   Derived: Kuzu graph (v3 schema)                              │  │
│  │   New edges: ISSUED_BY, EXECUTED_VIA, VERIFIED_BY,             │  │
│  │              FOLLOWED_BY (commitment chains),                  │  │
│  │              OBSERVED_AT (object → place)                      │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  Vector indexes (deferred FAISS P1 mid-cycle):                      │
│    - faces.index    (existing, 512-dim AdaFace)                     │
│    - voice.index    (P1.X — 192-dim ECAPA)                          │
│    - brain.index    (P1 mid — 1024-dim E5 over knowledge.embedding) │
│    - place.index    (P1 mid — 1024-dim E5 over places.description)  │
└─────────────────────────────────────────────────────────────────────┘
```

This is a strict superset of today's architecture. **Nothing existing is removed; new tables + new event types are added.** Existing companion-mode behavior is preserved when `KARAOS_PROFILE in ('companion', 'both')`.

---

## 7. Pre-P1 Fix List — MUST land before P1 starts

These items address §4.C latent defects + §6 prerequisites for robotics memory. Each is small enough to land in 1-3 days. Order is by criticality.

### 7.1 (BLOCKER) Add CI runner — P1.P1 closure

**Why first:** every structural invariant test in the project is architect-advisory until a CI runner enforces it. P1 will add ~15 new invariants (commitment-graph paired-writes, verifier-outcome event-log emission, profile-gate respect). Without CI, they're decorative.

**Action:** add minimal `.github/workflows/fast.yml` running `pytest -m "not slow and not network and not models"` on every PR. Mirror P0.0 design (already specified in CLAUDE.md "P0.0 COMPLETE — tiered CI scaffold" — the YAML was authored but not committed because no `.github/` exists). Add `slow.yml` + `security.yml` per the same spec.

**Validation:** push a deliberate regression on a structural invariant; verify the action fails. Restore; verify green.

**Risk if we DON'T:** every P1 invariant we add is a future-architect-trust violation. P0 closures repeatedly note "structural invariant now CI-enforced on every PR" — that's currently a lie. Fix it.

### 7.2 (HIGH) `embedding_model_id` + `embedding_dim` columns on `brain.db.knowledge`

**Why:** §3.3.2 + §3.3.3. Silent corruption on embedding model swap.

**Action:**
1. P0.9 migration `_m_0013_add_embedding_model_id_and_dim` adds two columns with defaults (`embedding_model_id = current EMBED_MODEL constant`, `embedding_dim = 1024`).
2. `BrainDB.store_knowledge_embedding` writes both on insert.
3. `BrainDB.semantic_search_knowledge` filters cosine candidates to rows matching the current model+dim.
4. Dream loop checks for embedding-model-id divergence and queues re-embedding batches.

**Validation:** `tests/test_brain_db_embedding_lifecycle.py` (new) — happy path, mismatch-row filter, dream-loop re-embed trigger.

**Risk if we DON'T:** P1 will inevitably swap embeddings (multilingual-e5-large-instruct → newer model OR move to local model for cost). The swap silently breaks every existing cosine query. We discover this in canary — too late.

### 7.3 (HIGH) Memory-write event log — H12 hook

**Why:** §2.4 + §4.C C10 + §6.1 R3. Verifier-disagreement diff requires it. Future-execution.md §2.4.2 #6 is unimplementable without it.

**Action:**
1. Add `MemoryWritePayload` dataclass in `core/event_log/types.py` (mirrors `MemoryWritePayload` already named in CLAUDE.md P0.0.7 §3 — verify it exists; if not, add).
2. Add `safe_emit_sync` calls at every `BrainDB.store_knowledge` / `mark_invalidated` / `promote_shadow_to_confirmed` / `store_room_summary` / `update_visitor_alert_for_promoted_person` site.
3. AST invariant: scan `core/brain_agent.py` for `store_knowledge(` and `_safe_commit()`; assert each is followed within 10 lines by a `safe_emit_sync(` call.

**Validation:** `tests/test_event_log_memory_hooks.py` (new) — replay 10 extraction turns, assert event_log has H12 rows for every knowledge write.

**Risk if we DON'T:** P1's audit trail is incomplete. Verifier disagreement protocol cannot be built on it.

### 7.4 (HIGH) Heavy-worker isolation AST invariant

**Why:** §3.7 + §4.C C6.

**Action:** new `tests/test_heavy_worker_isolation.py` AST scan asserts `core/heavy_worker.py` imports zero of `core.db`, `core.brain_agent`, `core.classifier_db`, `core.voice` (except where currently necessary — explicit allowlist).

**Validation:** trivial — invariant passes on current code.

**Risk if we DON'T:** future contributor adds a `BrainDB.store_xxx(...)` call inside a subprocess worker; cross-process SQLite contention; data loss.

### 7.5 (MEDIUM) Kuzu v3 schema bump

**Why:** §3.2 outstanding #1. P1 will add edges; stacking new schema on in-flight v2→v3 migration is sketchy.

**Action:** existing CLAUDE.md flag "Kuzu v3 schema bump: graph-side `privacy_level` (deferred from S107 audit)" → ship as Pre-P1. Mirrors P0.S7.D-B D1 work but for the v3 column itself.

**Validation:** existing test_kuzu_atomicity_invariants suite + new test_kuzu_v3_schema_invariant.

**Risk if we DON'T:** every P1 schema change has to reason about "what state am I in for v2→v3."

### 7.6 (MEDIUM) Profile-gate companion agents

**Why:** §2.3 + §4.D D1.

**Action:**
1. Add `KARAOS_PROFILE` constant to `core/config.py` with default `"both"`.
2. Move companion agents to `core/agents/companion/` (mechanical refactor).
3. `BrainOrchestrator.__init__` skips companion-agent instantiation when `KARAOS_PROFILE == "robotics"`.

**Validation:** boot pipeline with `KARAOS_PROFILE=robotics`, assert `len(orchestrator._agents)` is 5-6 (Triage, Extraction, Contradiction, Embedding, Watchdog) instead of 18.

**Risk if we DON'T:** P1 cycles have to reason about how new robotics features interact with 9 companion agents. Permanent cognitive tax.

### 7.7 (LOW) Update CLAUDE.md test count + verify CLAUDE.md "Module Roles" matches actual code

**Why:** CLAUDE.md self-states test count = 1273 in "Tests" line, but the actual P0.S10 closure says ~2810 passing. The internal consistency drift means future architects can't trust the file. Quick fix.

**Action:** read current pytest count, update CLAUDE.md test line + verify each constant in "Key Config Values" section matches `core/config.py`.

**Validation:** `pytest --collect-only` count vs CLAUDE.md line should match.

**Risk if we DON'T:** trust erosion. The doctrine "never leave stale values in this file" (CLAUDE.md "Rules for Claude" line 1) is itself stale. Self-defeating.

---

## 8. P1 Cycle Plan — Agent + Memory Layer

This is the 8-12 week P1 plan for the agents/memory surface. It assumes Pre-P1 items §7 have shipped first.

### 8.1 Phase 1A — Foundation week (Week 1)

**Deliverables:**
- Profile-gating shipped (§7.6)
- Memory-write event log shipped (§7.3)
- Embedding model+dim columns shipped (§7.2)
- CI runner shipped (§7.1)
- Kuzu v3 shipped (§7.5)

**Exit gate:** all of §7 deliverables green-CI, no regression on existing 2810 tests, profile-gating verified by manual boot of `KARAOS_PROFILE=robotics`.

### 8.2 Phase 1B — Commitment primitive (Weeks 2-4)

**Deliverables:**
1. `commitments` table (P0.9 migration `_m_0014_create_commitments`). Schema per §6.1 R1.
2. `CommitmentAgent` (new) under `core/agents/robotics/`. Subscribes to `ExtractionAgent` output via `BrainOrchestrator.notify()`. When extraction surfaces `intent='request_commitment'` (new TriageAgent intent class), CommitmentAgent constructs the row.
3. `CommitmentScheduler` async task in pipeline.py (mirrors `_dream_loop`). Fires at `due_at`, dispatches to `SkillExecutorAgent`.
4. Late-policy enforcement.
5. Persistence test: 100 commitments queued, kill -9 the pipeline, restart, verify all 100 still pending + due_at timestamps preserved.

**Validation:**
- `tests/test_commitment_lifecycle.py` — queue/fire/complete/fail/cancel state machine
- `tests/test_commitment_persistence.py` — restart survival
- `tests/test_commitment_late_policy.py` — three policies validated

**Exit gate:** demo — Jagan says "remind me to feed the dog in 2 minutes." Pipeline crashes mid-window. Restart. Commitment still fires at correct time.

**Architectural precedent:** PostgreSQL's `pg_cron` extension does exactly this. Cloudflare Durable Objects pattern. Airflow scheduler. All well-validated.

**Risk if we ship this badly:** commitments fail silently. Mitigation: every state transition emits H13 event_log row. Health alert if any commitment is `state='firing'` for > 60s.

### 8.3 Phase 1C — Skill executor + verifier registry (Weeks 4-7)

**Deliverables:**
1. `skill_call` + `skill_result` event types (P0.0.7 extension).
2. `verifiers` config registry — YAML at `config/verifiers/`. Each verifier is a Python callable with input `(commitment_id, skill_args)` and output `('confirmed', 'disagreed', 'abstained')`.
3. `SkillExecutorAgent` (new): receives commitment from scheduler, dispatches via adapter API (mock for Phase 1), receives adapter response, calls verifier, logs outcome.
4. `verifier_outcomes` table.
5. Disagreement protocol: adapter says `done`, verifier says `disagreed` → state=`failed_verification` + escalate to `WatchdogAgent`.

**Validation:**
- `tests/test_skill_executor.py` — mock adapter + mock verifier, happy path + disagreement path
- `tests/test_verifier_abstention.py` — verifier returns `abstained`, state stays `pending_verification`
- End-to-end: NL → commitment → fire → mock skill → mock verifier confirm → state=`completed` → audit event-chain replay shows full causal chain via H13/H14/H15/H16

**Exit gate:** demo — `mock_adapter` simulates a "turn off oven" skill. `mock_verifier` reads a fake sensor. Disagreement case fires the watchdog alert.

### 8.4 Phase 1D — Cost ledger (Week 7-8)

**Deliverables:**
1. `cost_ledger` table per §6.1 R6.
2. Token/$ tracking in every LLM call (Session 116 P1 #5 — finally close).
3. Per-skill cost tracking via `skill_result.cost_estimate`.
4. Budget threshold alerts via `WatchdogAgent`.

**Validation:** queue 100 commitments, run them, verify cost ledger sum matches Together.ai dashboard within 5%.

### 8.5 Phase 1E — Adapter SDK + conformance suite (Weeks 8-10)

This is the deliverable per future-execution.md §2.4.2 #3. Out of scope for this review (TechAnalyst-1 owns it), but the agents/memory layer's coupling to it is: `SkillExecutorAgent.dispatch(skill_name, args, adapter_endpoint)`.

### 8.6 Phase 1F — Brain.db FAISS index (Week 10-11)

**Why now (not Pre-P1):** the row count today is fine. Becomes a problem only after commitments + skill provenance + verifier outcomes start filling the knowledge table at robotics scale.

**Deliverables:**
1. Parallel FAISS index at `faces/brain.faiss` (and matching sentinel `.brain.faiss.dirty`).
2. `BrainDB.semantic_search_knowledge_faiss` (new method, preserves linear-scan as fallback).
3. Rebuild-on-boot if sentinel set or count mismatch (mirror face-index pattern from `core/db.py`).
4. AST inverse-check: every `store_knowledge_embedding` site has a FAISS-update sibling.

**Validation:** scale-test — insert 100K knowledge rows, query, assert <50ms p95 latency.

### 8.7 Phase 1G — Pre-canary integration tests (Week 11-12)

End-to-end scenario coverage:
- Multi-user commitment contention (operator A queues X, operator B queues conflicting Y → resolved by authority priority).
- Restart resilience over a 24h window.
- Adapter outage → commitments stay `pending`, retry policy fires when adapter back.
- Verifier abstention chain — 3 consecutive verifiers abstain → state=`pending_human_review`.
- Cost ledger drift — kill mid-execution, restart, verify no double-billing.

---

## 9. Canary Checklist — for `to_be_checked.md`

Per Jagan's mandate: every item below must be verified in CANARY (post-P1, before declaring P1 done).

### 9.1 Atomicity invariants (regression guards)

- [ ] FAISS face index — power-cycle the box mid-`add_embedding`. On boot, recognize() returns correct identities for all previously-enrolled faces. Sentinel auto-clears.
- [ ] Kuzu graph — corrupt `faces/brain_graph/data.kz` manually. Restart pipeline. Verify `_ensure_graph_sync` rebuilds without crash + `_kuzu_degraded` flag does NOT stick.
- [ ] brain.db ↔ Kuzu — kill -9 pipeline immediately after a `store_knowledge` that should propagate to Kuzu. Restart. Verify `_kuzu_dirty` sentinel detected + graph self-heals on next access.
- [ ] async FAISS rebuild — fire 50 `add_embedding` calls during a `rebuild_faiss_async`. Verify no orphan embeddings, no FAISS↔SQL row-count divergence, `embeddings.faiss_idx` column post-state matches `_idx_to_person`.

### 9.2 Memory correctness (P1 NEW invariants)

- [ ] Embedding dimension verification — manually insert a 768-dim BLOB into `knowledge.embedding`. Trigger semantic_search. Verify the row is skipped + dream loop logs re-embed-required.
- [ ] Embedding model_id filter — change `EMBED_MODEL` in config (without re-embedding). Restart. Verify semantic_search returns zero stale-model rows + dream-loop queues re-embedding.
- [ ] Memory write event log — extract 10 facts. Replay via `tools/replay_session.py --memory-only`. Verify 10 H12 rows + matching `knowledge` table state.
- [ ] Heavy-worker isolation — inject an `import core.brain_agent` into `core/heavy_worker.py`. Run AST invariant. Verify failure.

### 9.3 Robotics primitives (P1 NEW)

- [ ] Commitment persistence — queue 50 commitments with `due_at` spread over 24h. Kill -9 pipeline. Restart. Verify all 50 still `state='pending'` + correct `due_at`.
- [ ] Commitment scheduling — set `due_at = now + 30s` on a test commitment. Verify it fires at correct wall-clock time + state transitions to `firing`.
- [ ] Late policy — kill pipeline. Wait for commitment to be overdue. Restart. Verify late-policy enforcement per `late_policy` column.
- [ ] Verifier disagreement — mock adapter returns `done`, mock verifier returns `disagreed`. Verify state=`failed_verification` + WatchdogAgent fires.
- [ ] Cost ledger — run 100 commitments. Compare ledger total to provider API dashboard. Drift < 5%.
- [ ] Profile gate — boot with `KARAOS_PROFILE=robotics`. Verify only 5-6 agents loaded (Triage, Extraction, Contradiction, Embedding, Watchdog + new robotics agents). Companion agents NOT loaded.
- [ ] Adapter outage resilience — commitment with due_at in 30s. Take mock adapter offline. Verify commitment stays `pending` + retries when adapter recovers.

### 9.4 Privacy + safety (regression — must hold post-P1)

- [ ] Cross-person leak — visitor session ends with personal-tier safety-flag fact. Best_friend asks "what did X say." Verify owner-mode visibility returns the fact (3A.4.6 simplified model). Non-owner asking same question returns nothing.
- [ ] Safety-critical preservation — extract a `expressed_suicidal_thoughts='true'` fact. Subsequently extract `current_mood='happy'`. Verify safety-flag fact is NOT invalidated (Session 105 Bug N).
- [ ] Misattribution defense — STT mishears "Jagan" as "Jaman" during enrollment. Verify Session 100 Bug F escape hatch fires + person promoted correctly.

### 9.5 Performance + cost SLOs (proposed for P1)

- [ ] p95 turn latency in robotics profile ≤ 1.2s end-to-end (STT + classification + skill dispatch).
- [ ] p99 memory event log emit latency ≤ 50ms.
- [ ] Knowledge semantic search p95 < 50ms (validates §8.6 FAISS adoption).
- [ ] Commitment scheduler tick latency < 100ms.

### 9.6 Industry-comparison check

After P1 ships, run a smoke comparison vs Mem0 + Letta + Zep on a fixed scenario set (10 commitments, 5 multi-user conflicts, 3 verifier-disagreement cases). Document where KaraOS lands. This is **positioning evidence** — it doesn't have to win every benchmark, but the comparison must exist for the partner pitch.

---

## Appendix A — Files I read deeply for this review (auditable list)

- `C:\Users\jagan\dog-ai\dog-ai\CLAUDE.md` — entire history (~2200 lines of closure narratives)
- `C:\Users\jagan\dog-ai\future-execution.md` — §0-2.4 verified, §3-7 spot-checked
- `C:\Users\jagan\dog-ai\complete-plan.md` — referenced indirectly via CLAUDE.md
- `core/brain_agent.py` — grep-verified 18 agent class definitions + line offsets + BrainDB/GraphDB/BrainOrchestrator entry points
- `core/db.py` — grep-verified FAISS atomicity surface (add_embedding, _save_faiss, _mark_faiss_dirty, rebuild_faiss_async, _load_faiss)
- `core/health.py` — referenced via CLAUDE.md "Module Roles"
- `core/heavy_worker.py` — referenced via P0.R6 closure narrative

## Appendix B — Where my evidence is direct vs derived

- **Direct file/line citations** (verified by grep this session): §2.1 agent inventory table, §3.1 FAISS atomicity, §3.3 brain.db tables, §3.4 voice gallery code paths.
- **Derived from CLAUDE.md closure narratives** (high confidence — those are the architect's own banked observations): P0.5 / P0.X / P0.B2 / P0.B3 / P0.S10 / P0.R6 architectural commitments, the existence of `event_log` payload types in P0.0.7.
- **External (industry comparison)**: Mem0 / Letta / Zep / LangGraph architectures cited from my training data (cutoff Jan 2026). Robotics industry section cites future-execution.md §2.4 which the architect has independently authored.
- **Flagged extrapolations**: §6 robotics requirements R1-R7 are derived from future-execution.md §2.1-2.4 + general ROS 2 ecosystem knowledge. Where I extrapolated (e.g., bi-temporal model from Zep), I flagged it.

---

## Closing note

This review puts heart and blood into what Jagan asked for. The honest answer is: KaraOS today is a well-engineered conversational companion stack with structurally sound atomicity, mature privacy, and 35+ closure cycles of regression discipline behind it. It is **not yet** the cognitive middleware that the strategic goal demands. The gap is closeable in 8-12 weeks of P1 if Pre-P1 §7 ships first and the agent consolidation §8 is accepted.

The single most important architectural decision pending: **commit to profile-gating now.** Every week without it, more companion-leaning logic gets entangled with robotics-leaning logic, and the eventual separation becomes more expensive. ROS 2 + Linux kernel both made this decision early and well; KaraOS should too.

— TechAnalyst-2
