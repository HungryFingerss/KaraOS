# P0.S7 — Phase 3B (RoomOrchestrator follow-ups) — Phase 0 Audit

**Date:** 2026-05-18
**Author:** architect
**Status:** Phase 0 — grep-verified findings, zero production-code changes. Standing by for auditor review before D-decision lock and Plan v1.

**Companion document trail (forthcoming):**
- `tests/p0_s7_plan_v1.md` — after Phase 0 sign-off + D-decision lock
- `tests/p0_s7_plan_v2.md` — after Plan v1 review

---

## 1. Premise reset (sub-pattern A, 3rd consecutive instance candidate)

**Assumed premise (going into Phase 0):** "Phase 3B" is a single multi-day spec that introduces `RoomOrchestrator` as a class, refactors the 50+ `_active_sessions[pid]` access sites to go through it, wires room-scoped conversation-log retrieval, and ships the `<<<SHARED CONTEXT>>>` prompt block.

**Actual codebase state (grep-verified 2026-05-18):**

Phase 3B.1 through 3B.6 features are **already shipped** in Sessions 111-117:

| Sub-feature | Shipped in | Surface |
|---|---|---|
| 3B.1 — `<<<ROOM>>>` block | Session 113 | `_build_room_block` at `pipeline.py:1288` |
| 3B.2 — user-to-user silence (direct_address_to_person intent) | Session 113 | `_INTENT_CLASSIFIER_SYSTEM` + classifier label |
| 3B.3 — TURN ARBITRATION rules | Session 113 | `<<<TURN ARBITRATION>>>` prompt block |
| 3B.4 — N-speaker transcript | Session 113 | `_format_multispeaker_transcript` in pipeline.py |
| 3B.5 — `search_room_memory` tool | Session 113 | `FaceDB.search_room_turns` + brain tool registration |
| 3B.6 — room-end synthesis | Session 113 | `BrainOrchestrator.synthesize_room` + `room_summaries` table + `<<<RECENT ROOMS>>>` block |
| Room lifecycle (mint/add/end) | Session 112 | `_active_room_session` + `_active_room_started_at` + `_active_room_participants` + `_on_room_end` in pipeline.py |
| `conversation_log` schema columns | Session 107 + 111 | `room_session_id`, `audience_ids`, `addressed_to` columns + `idx_conv_log_room` index |

**What's actually deferred under the "Phase 3B" label** (verified by `everything_about_system.md` §145 + §163 + §338 + CLAUDE.md "Pending Work"):

1. **D-A — `<<<SHARED CONTEXT>>>` retrieval-side wiring.** Schema is in place (S107) but no retrieval consumer reads from it for the prompt-block path. `_build_cross_person_excerpts` (pipeline.py:1166) reads from in-memory `_conversation_store._history`, NOT from `conversation_log` with room/audience filters.
2. **D-B — Kuzu v3 schema bump.** Graph-side `privacy_level` propagation. Deferred at S107 audit (auditor: "SQL filter sufficient for current threat model").
3. **D-C — `_build_cross_person_excerpts` deletion.** Reviewer's plan: delete after live multi-person canary validates `<<<ROOM>>>` block sufficiency. Currently both blocks render in parallel (redundant).
4. **D-D — `RoomOrchestrator` class extraction.** The original roadmap proposed a class; Phase 3B.1-3B.6 deliberately stayed module-level. The class extraction would refactor 50+ `_active_sessions[pid]` access sites. Explicit non-goal of Phase 3B.1-3B.6 per `everything_about_system.md` §163.3.
5. **D-E — Multi-speaker `conversation_turn` signature redesign.** Remove `_cur_pid` singular primary model (72 occurrences in pipeline.py per grep), interleaved history with speaker tags. Listed under CLAUDE.md "Features pending" as "Part 2 Components 1-3 (deferred)."

**Implication:** there is no monolithic "Phase 3B" spec to write. There are 5 deferred items at different scope sizes, with different blocking dependencies. The architect's premise was wrong; the user's "let's start Phase 3B" phrasing inherits the wrong premise.

**Recommendation:** select ONE of the 5 deferrals as the first sub-PR. The audit recommends **D-A** (SHARED CONTEXT block) for reasons in §3 below.

---

## 2. Grep-verified surface map

### 2.1 Already-shipped room scaffolding

`pipeline.py`:
- L1166 — `_build_cross_person_excerpts(person_id, all_snaps, conversation_store_history, bf_id)` — current redundant block reading from in-memory store
- L1288 — `_build_room_block(active_sessions, conversation, emotion_agents, room_start_ts, turn_cap, now)` — the Phase 3B.1 block (pure helper)
- L1497 — `get_recent_room_context` consumer for `<<<RECENT ROOMS>>>` block (Phase 3B.6 — reads from `room_summaries`, not `conversation_log`)
- L1803-1826 — `_open_session` lifecycle: mint room id + add participants
- L1921 — `_h11_room_open` — H11 session_lifecycle event emit
- L2009-2080 — `_on_room_end` — fires `synthesize_room` fire-and-forget on last-person-leaves
- L2158-2180 — close-session lifecycle: capture room_session_id + participants BEFORE prune
- L3123 — `_build_room_block` call site #1 (conversation_turn vision_state)
- L3165 — `search_room_memory` tool registration
- L4712-4777 — `search_room_memory` callback wiring + count failure handling
- L5216 — `_build_cross_person_excerpts` call site (still in production)
- L7776 — `_build_room_block` call site #2 (KAIROS path)

`core/db.py`:
- L191 — schema migration comment (room_session_id + audience_ids)
- L1154 — `RoomOrchestrator supplies them` (architectural intent comment in docstring; class doesn't exist)
- L1278 — `conversation_log rows tagged with the given room_session_id` (read helper docstring)

`core/faces_db_migrations.py`:
- L173-204 — v=7 migration adding `room_session_id`, `audience_ids`, `idx_conv_log_room`
- L217-250 — v=9 backfill for legacy rows

`core/brain_agent.py`:
- `synthesize_room` method on BrainOrchestrator
- `room_summaries` table writes
- `get_recent_room_context` reader

`core/event_log/types.py`:
- `room_session_id` field on session_lifecycle payload (H11)

### 2.2 NOT-YET-EXISTING surface (the gap)

Grep for "RoomOrchestrator" returns:
- 0 class definitions
- Multiple docstring/comment references treating it as an architectural intent (`core/db.py:1154`, `test_pipeline.py` Session 107 comments, `test_brain_agent.py` Session 107 comments)
- `everything_about_system.md` §163.3 explicit non-goal documentation

Grep for `<<<SHARED CONTEXT>>>` block returns:
- 0 occurrences in `pipeline.py` or `core/brain.py`
- Multiple `everything_about_system.md` references describing the deferred consumer (`§145 Q3 History Architecture Redesign`)
- This is the D-A gap.

Grep for "Kuzu v3" / `GRAPH_SCHEMA_VERSION = 3`:
- Currently `GRAPH_SCHEMA_VERSION = 2` per CLAUDE.md config table
- 0 v3-bump migration logic
- This is the D-B gap.

### 2.3 Redundancy evidence (D-C cleanup candidate)

Both `_build_room_block` AND `_build_cross_person_excerpts` are called every multi-person turn:
- `_build_room_block` at pipeline.py:3123 (vision_state) + pipeline.py:7776 (KAIROS)
- `_build_cross_person_excerpts` at pipeline.py:5216 (conversation_turn, after vision_state already includes ROOM block)

Both blocks render different views of the same underlying multi-person conversation. `<<<ROOM>>>` is the richer + newer block (4-section structure: speakers / duration / interleaved turns / per-person mood). The cross-person-excerpts block is the legacy from pre-3B.1 sessions.

**Reviewer's S113 plan (per CLAUDE.md "Features pending"):** delete `_build_cross_person_excerpts` after live multi-person canary validates ROOM block sufficiency. **Canary not yet run.** (User flagged in conversation 2026-05-18: "im not sure about the run book in the live session.")

### 2.4 `_cur_pid` singular-primary surface (D-E scope)

72 occurrences in `pipeline.py` (per grep count). This is the "primary speaker" model that Multi-speaker Part 2 Components 1-3 want to eliminate. Every turn currently has one `_cur_pid` that drives:
- Greeting selection
- Voice routing dispatch (Priority 1-5 in legacy + reconciler-replaced paths)
- KAIROS speaker selection (`_kairos_preferred_speaker`)
- session_lifecycle event audience targeting
- TTS gating
- Multiple session-dict reads

Migrating away from singular `_cur_pid` is a large refactor that touches the voice-routing surface, the conversation_turn signature, and history append semantics. This is structurally adjacent to D-D (RoomOrchestrator class extraction) since both touch the access-site surface.

---

## 3. D-decision surface

Below are the decisions the audit surfaces. Each carries an architect lean — auditor to lock or revise.

### D1 — Sub-PR slicing strategy

**Question:** Which of D-A through D-E ships first?

**Options:**
- **(a)** D-A alone (SHARED CONTEXT block, retrieval-side wiring) — schema already in place; smallest dependency surface; high immediate user-visible value.
- **(b)** D-A + D-B together (SHARED CONTEXT + Kuzu v3) — original roadmap intent ("Kuzu v3 lands alongside"). Larger scope.
- **(c)** D-D (RoomOrchestrator class extraction) — preserves the original "Phase 3B" framing but is the largest refactor + lowest immediate user value.
- **(d)** D-C (cross-person excerpts deletion) — smallest scope; canary-gated.

**Architect's lean: (a).** D-A is the most-blocked retrieval gap (brain currently can't pull room-scoped conversation history from `conversation_log` via the SQL visibility-filter path). Highest user-visible value per unit effort. D-B can ship as a separate sub-PR after D-A validates the SQL-side retrieval path; the S107 auditor explicitly ruled SQL filter sufficient for current threat model, so D-B isn't blocking D-A. D-C is gated on a live canary that hasn't run. D-D + D-E are large refactors that should be their own multi-day spec cycles after D-A demonstrates the retrieval contract is stable.

### D2 — D-A scope: SHARED CONTEXT block contents

**Question:** What does `<<<SHARED CONTEXT>>>` actually inject?

**Options:**
- **(a)** Last N turns from `conversation_log` filtered by `room_session_id == current_room` AND audience-includes-current-speaker AND privacy via `_visibility_clause`. Simple recency window.
- **(b)** (a) + LLM-synthesized summary when the room has >K turns (avoid context-window bloat in long multi-person sessions). Adds latency.
- **(c)** (a) + per-speaker grouping (rendered as "Jagan said:" / "Lexi said:" sections instead of strict chronological).

**Architect's lean: (a).** Smallest delta, preserves the existing privacy contract (`_visibility_clause` already wired). Per-speaker grouping (c) duplicates what `<<<ROOM>>>` block already does in Section 3 (interleaved chronological turns with per-line speaker labels). LLM synthesis (b) is a separate optimization that can land later if context-bloat becomes load-bearing.

### D3 — D-A retrieval method placement

**Question:** Where does the SQL query live?

**Options:**
- **(a)** New method on `FaceDB` (the conversation_log owner): `get_recent_room_conversation(room_session_id, requester_pid, best_friend_id, limit)`. Mirrors the existing `search_room_turns` (S113) pattern.
- **(b)** New method on `BrainOrchestrator` that delegates to FaceDB. Adds an indirection layer.
- **(c)** Inline SQL in pipeline.py. Violates layering.

**Architect's lean: (a).** Layering invariant preserved (pipeline.py doesn't touch SQL); mirrors existing `search_room_turns` pattern; `_visibility_clause` already lives in brain_agent.py and is composable from both faces.db and brain.db query paths.

### D4 — D-A audience filtering shape

**Question:** Pre-S107 rows have `audience_ids = NULL` (backfilled to single-person via faces_db_migrations.py v=9). New shared turns get JSON audience arrays. How does the SELECT handle both?

**Options:**
- **(a)** `audience_ids IS NULL OR audience_ids LIKE '%"requester_pid"%'` — works for both legacy and new rows; JSON substring match is sqlite-portable.
- **(b)** SQLite JSON functions (`json_each`, `json_extract`) — proper JSON parsing but requires SQLite 3.45+ on Jetson. Need to verify the deployment SQLite version.
- **(c)** Two-step: SQL fetches candidates by `room_session_id`, Python filters by audience. Simple but bypasses index.

**Architect's lean: (a)** with explicit `audience_ids IS NULL` clause preserving legacy-row visibility per-speaker. Verify against SQLite version on Jetson before locking; if 3.45+ confirmed, (b) is cleaner and we can revise in Plan v2.

### D5 — D-A block gating

**Question:** When does the block render?

**Options:**
- **(a)** Same gate as `<<<ROOM>>>` block: `ROOM_BLOCK_ENABLED` AND `len(active_sessions) >= 2`. Block only fires in multi-person rooms.
- **(b)** Independent flag (`SHARED_CONTEXT_BLOCK_ENABLED`) + multi-person gate. Allows rolling back SHARED CONTEXT without disabling ROOM block.
- **(c)** Single-person rooms get the block too (pulls own prior turns from `conversation_log`). Larger blast radius.

**Architect's lean: (b).** Independent flag preserves rollback discipline (P0.10 lesson — flag-gated rollouts make canary cleanup trivial). Single-person rooms (option c) is wider scope than the deferred contract envisioned.

### D6 — D-A coexistence with `_build_cross_person_excerpts`

**Question:** During D-A's validation window, both blocks render?

**Options:**
- **(a)** Both render in parallel; D-C (cross-person excerpts deletion) is its own follow-up after multi-person canary validates D-A sufficiency.
- **(b)** D-A ships with `_build_cross_person_excerpts` deletion bundled — single sub-PR, single canary.
- **(c)** D-A ships disabled by default (`SHARED_CONTEXT_BLOCK_ENABLED=False`); enable after canary; delete cross-person-excerpts in a third PR.

**Architect's lean: (a).** Single-flag rollback path; D-A and D-C are independent decisions. Bundling (b) widens canary scope. Default-off (c) defers the actual value until a second enabling PR — adds friction for canary observers.

### D7 — D-A block format

**Question:** What does the block text look like?

**Options:**
- **(a)** Identical to `_build_cross_person_excerpts`'s existing render shape (line per turn with `[name] (age suffix):` prefix). Trains the brain on existing patterns.
- **(b)** Richer format (e.g., `(turn N) [age] [name → addressee]: "text"`) — closer to what `<<<ROOM>>>` block section 3 already does.
- **(c)** Plain text, no per-turn metadata.

**Architect's lean: (a).** Reusing existing format keeps the brain's pattern-recognition surface stable. `<<<ROOM>>>` block already covers the rich-format case (interleaved chronological with addressee labels) for the IN-MEMORY in-progress turns; `<<<SHARED CONTEXT>>>` is the persistent-DB-backed complement. Same render shape, different source.

### D8 — D-A test coverage

**Question:** What tests ship with D-A?

**Options:**
- **(a)** Unit tests for `FaceDB.get_recent_room_conversation` (room filter, audience filter NULL + non-NULL, privacy_level filter, ordering, limit), + `_build_shared_context_block` (single-person gate, multi-person rendering, empty-query graceful, flag-off) + 1 pipeline-level integration test asserting `_build_system_prompt` injects the block at the right offset. ~8-10 tests.
- **(b)** (a) + AST source-inspection tests guarding the query method signature + the visibility-clause composition. Same shape as P0.S6's structural tests.
- **(c)** (b) + a 5-row deliberate-regression confirmation set (inject cross-room turn leak / inject privacy_level=system_only row / inject audience mismatch / etc.) at Phase 4.

**Architect's lean: (c).** Same discipline as P0.S6 — induction protocol with explicit injection-confirms-fires-and-reverts. Total target ~10-12 tests, suite delta 2310 → ~2322.

---

## 4. Estimated effort + phase shape (architect's prediction)

D-A alone, with the recommended D-decisions locked at architect's leans:

| Phase | Scope | Tests | Time |
|---|---|---|---|
| 1 | `FaceDB.get_recent_room_conversation` + unit tests | +4 | ~half-day |
| 2 | `_build_shared_context_block` helper + pipeline integration + flag + 2 call sites (conversation_turn + KAIROS) | +3 | ~half-day |
| 3 | Source-inspection invariants (query method signature, visibility-clause composition, block placement) | +3 | ~quarter-day |
| 4 | Deliberate-regression confirmations + closure | +0 | ~quarter-day |

**Total: ~10 tests, ~1.5 dev-days, suite 2310 → ~2320.**

For comparison: D-D (RoomOrchestrator class extraction) would be **5-7 dev-days** (50+ access sites + comprehensive regression testing). D-E (multi-speaker conversation_turn redesign) would be **3-5 dev-days**. The user's "let's start Phase 3B" instinct probably envisioned the class extraction; the audit recommends starting with D-A first because it's the user-visible-value delta, and the class extraction is structural cleanup that doesn't itself unlock new behavior.

---

## 5. Discipline-count predictions

If the audit's recommended path (D-A first) is approved:

- **Spec-first review cycle**: 8-for-8 → **9-for-9** on closure (P0.S7 added; another Phase 0 audit caught the wrong-premise correctly).
- **Sub-pattern A (memory-note, 3rd → 4th instance)**: Phase 3B Phase 0 audit catches wrong premise — "Phase 3B is one spec" → actual is "5 distinct deferrals." Bank as 4th instance at closure. Still below 5+ threshold for CLAUDE.md doctrine elevation, but trending toward it.
- **Tripwires-must-match-deferral-surface**: stays 4-for-4 unless D-A introduces a deferral with a guarding tripwire.
- **Developer-improves-on-spec**: stays 6-for-6 unless code phase surfaces a mechanism improvement.
- **Induction-surfaces-invariant-gaps**: stays 7-for-7 unless Phase 4 surfaces a real gap.

---

## 6. Threats / risks / non-claims

### Threats to D-A as the first slice

1. **Latency budget.** `<<<SHARED CONTEXT>>>` adds one SQL query per multi-person turn. The existing `_build_room_block` does NOT touch SQL (reads from in-memory `_conversation_store`). The query's cost depends on `conversation_log` size + index health; on Jetson this should be sub-10ms but unverified. Phase 1 should include a latency assertion.

2. **Brain context-window competition.** `<<<ROOM>>>` already renders interleaved turns from the current session's in-memory history. `<<<SHARED CONTEXT>>>` renders persistent room-scoped turns from `conversation_log`. There's content overlap on long multi-person sessions. D7's "reuse existing render shape" mitigates this somewhat, but if both blocks render the SAME turn twice (in-memory + DB), the brain may double-count facts. Plan v1 should either dedupe or scope `<<<SHARED CONTEXT>>>` to "older than current session start."

3. **Cross-person excerpts cleanup gate.** D-C (delete `_build_cross_person_excerpts`) is the canary-gated cleanup. If D-A ships with both blocks rendering, the prompt token budget grows. The architect's recommendation (D6.a) accepts this temporarily; Plan v1 should quantify the token-budget impact.

### Non-claims for D-A

- D-A does NOT replace `<<<ROOM>>>` block. The two blocks serve different sources (in-memory vs persistent).
- D-A does NOT introduce `RoomOrchestrator` class. D-D remains deferred.
- D-A does NOT change the singular `_cur_pid` model. D-E remains deferred.
- D-A does NOT touch Kuzu. D-B remains deferred (S107 auditor ruled SQL filter sufficient).
- D-A does NOT delete `_build_cross_person_excerpts`. D-C remains deferred until canary validates.

### Wrong-premise non-claim (sub-pattern A explicit banking)

The architect's pre-Phase-0 mental model treated "Phase 3B" as one spec. Grep-verified evidence shows the label spans 5 independent deferrals. This audit explicitly disclaims the monolithic framing and recommends a per-item slicing approach. Same shape as P0.10 (legacy router was thought to be the baseline), P0.S1 (recognition_update was thought to be the dangerous path), P0.S6 (log-leak surface was assumed).

---

## 7. Next steps

1. **Auditor reviews this Phase 0 audit.** Specifically: (a) the sub-pattern A premise-reset framing — is D-A the right first slice? (b) the D1-D8 architect leans — any to revise? (c) the threats in §6 — anything missed?
2. **D-decisions locked** at Phase 0 sign-off (mirrors P0.S1 / P0.S6 pattern).
3. **Plan v1** drafted with locked D-decisions.
4. **Plan v1 review** by auditor → 5-7 precision items.
5. **Plan v2** drafted incorporating precision items → joint sign-off.
6. **Developer handoff** for 4-phase implementation.

Standing by for auditor verdict.

---

## 8. Reference documents

- `everything_about_system.md` §145 (Q3 History Architecture Redesign — D-A deferral rationale), §163 (Room session lifecycle — already-shipped state), §163.3 (RoomOrchestrator class non-goal), §338 (Kuzu v3 deferral)
- `CLAUDE.md` "Pending Work" + "Features pending" sections — D-C / D-D / D-E enumeration
- `core/db.py:1154` — `RoomOrchestrator supplies them` docstring (architectural intent placeholder)
- `pipeline.py:1166` (`_build_cross_person_excerpts`), `pipeline.py:1288` (`_build_room_block`), `pipeline.py:2009` (`_on_room_end`), `pipeline.py:5216` (D-C cleanup target call site)
- `core/faces_db_migrations.py:173-204` (v=7 room schema landing), `:217-250` (v=9 backfill)
- `tests/p0_s1_audit.md` + `tests/p0_s6_audit.md` — reference Phase 0 audit shape
