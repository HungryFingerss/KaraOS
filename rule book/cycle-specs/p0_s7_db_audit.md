# P0.S7.D-B — Kuzu v3 schema bump (privacy_level on graph edges) — Phase 0 Audit

**Date:** 2026-05-19
**Author:** architect
**Status:** Phase 0 — grep-verified findings, zero production-code changes. Standing by for auditor review before D-decision lock and Plan v1.

**Companion document trail (forthcoming):**
- `tests/p0_s7_db_plan_v1.md` — after Phase 0 sign-off + D-decision lock
- `tests/p0_s7_db_plan_v2.md` — after Plan v1 review

**Disciplines applied at audit time** (per architect-memory banked at P0.S7.D-C closure 2026-05-19):
- Spec-time grep-verification: all function names + line numbers below grep-verified 2026-05-19
- AST-forward-property-tests-are-the-workhorse: §6 test design prefers AST over source-inspection

---

## 1. Premise (with explicit S112-deferral-rationale reversal)

P0.S7's Phase 0 audit (`tests/p0_s7_audit.md`) named D-B as the Kuzu v3 schema bump — graph-side `privacy_level` propagation. The S107 + S112 audits deferred it. **This audit reverses the deferral on grep-verified evidence that the deferral's premise no longer holds.**

### 1.1 The deferral rationale (from `find_shared_entities` docstring, pipeline.py:3662-3695)

> Session 112 Part 4 — session-isolation audit (DECISION: option (a) — skip v3 bump, SQL filter is sufficient): ... The sensitive-value leak concern (Session 107 wording) is already bounded by Session 106 Migration 2's SQL filter ... Full Kuzu v3 (privacy_level on Entity nodes + Cypher filter) is deferred to Phase 3B proper, when the audience_ids + room retrieval wiring for conversation_log arrives and the graph visibility model is re-visited end-to-end. **Shipping it now would add schema-version plumbing + a v2→v3 rebuild step without a concrete active leak to fix.**

### 1.2 Why the deferral premise no longer holds

The S112 deferral was on solid ground AT THE TIME: cross-person inference matched on entity NAMES (like "diabetes" / "cousin Ravi" / "cricket") that both persons happened to have in their graphs. Sensitive-value leaks were structurally bounded because (a) the SQL `privacy_level != 'system_only'` filter applied at the recipient's SELECT, (b) personal-tier facts about a visitor weren't being written to OTHER speakers' graphs.

**That second condition flipped 2026-05-19 when P0.S7.2 κ multi-person assistant-turn extraction shipped.** κ now writes per-participant `received_<action_type>` + `witnessed_<action_type>` facts to brain.db with `privacy_level='personal'`. The Kuzu graph rebuild (`rebuild_entity_from_knowledge`, line 3577) ingests every brain.db `knowledge` row into RELATES_TO edges. So:

- Lexi visits, brain shares cheese-cookies recipe with her while Jagan is present.
- κ extracts: `Lexi.received_shared_information='cheese cookies: butter, sugar, eggs, flour'` (personal-tier) + `Jagan.witnessed_shared_information='cheese cookies to_Lexi'` (personal-tier).
- Both rows land in brain.db; graph rebuild creates RELATES_TO edges WITHOUT privacy_level filter.
- A future cross-person inference query — e.g., a third visitor "Kara_friend" arrives, brain runs `find_shared_entities(Kara_friend, Lexi)` — would surface "cheese cookies" as a shared entity value across the two graphs (if it appears in both for any reason).
- The legacy SQL filter at the recipient's DISTINCT values SELECT (S106 Migration 2) only catches `system_only`. It does NOT catch personal-tier facts leaking via graph traversal.

**This is the concrete active leak the S112 deferral said didn't exist.** It exists now. D-B is load-bearing.

### 1.3 Premise reset summary

| Era | Cross-person Kuzu leak risk | S112 deferral status |
|---|---|---|
| Pre-P0.S7.2 | Only user-turn extractions in graph; cross-person room context not persisted as facts; low leak risk | Justified |
| Post-P0.S7.2 (NOW) | κ writes personal-tier room-context facts; graph rebuild ingests them; `find_shared_entities` returns them with no privacy filter | **Deferral rationale falsified** |

This is NOT a sub-pattern A wrong-premise on the architect's side — the S112 architect correctly deferred at the time. **This is a "deferred-decision becomes load-bearing when downstream work ships" finding.** Worth banking as a separate observation.

---

## 2. Grep-verified surface map (2026-05-19)

`core/brain_agent.py` — all sites touching Kuzu schema or queries:

| Site | Function | Disposition under v3 |
|---|---|---|
| Line 3505-3519 | `GraphDB._init_schema` (schema definition) | EXTEND — add `privacy_level STRING` to RELATES_TO |
| Line 3531-3554 | `GraphDB._create_edge` (edge writer) | EXTEND — accept + write `privacy_level` param |
| Line 3556-3567 | `GraphDB.store_fact` (Extraction → edge) | EXTEND — pass `ext.privacy_level` to `_create_edge` |
| Line 3569-3575 | `GraphDB.invalidate_fact` | NO CHANGE — operates on attribute name only |
| Line 3577-3609 | `GraphDB.rebuild_entity_from_knowledge` | EXTEND — accept `privacy_level` from brain.db row; pass to `_create_edge` |
| Line 3611-3645 | `GraphDB.get_graph_context` (1-hop reader) | **DECISION NEEDED (D3 below)** — does this need a privacy filter too? |
| Line 3647-3760 | `GraphDB.find_shared_entities` (cross-person traversal) | EXTEND — Cypher filter on `privacy_level` |
| Line 3764-3775 | `GraphDB.drop_schema` | NO CHANGE — wipe is wipe |
| Line 6481-6485 | `BrainOrchestrator._ensure_graph_sync` schema-version check | NO CHANGE — already triggers rebuild on version bump |
| Line 6554-6570 | `BrainOrchestrator._ensure_graph_sync` schema-upgrade path | NO CHANGE — drop + init + rebuild already automated |
| Line 6675-6688 | `_persist_extraction_to_kuzu` (paired-write) | NO CHANGE — calls `store_fact` which gets privacy_level for free |

`core/config.py:1242` — `GRAPH_SCHEMA_VERSION = 2 → 3`. One-line bump.

`core/brain_agent.py:_visibility_clause` — SQL-side filter (P0.S7 P1). NO CHANGE — D-B is graph-side parity, not a replacement.

`tests/` — Kuzu test files (count TBD in Plan v1 grep; conservative estimate 2-4 test files: `test_kuzu_atomicity_invariants.py`, `test_kuzu_brain_atomicity.py`, possibly `test_brain_agent.py` slow-tier tests).

**Net surface count: 8 production sites (1 schema + 4 writers + 1 reader + 1 query + 1 config) + N test files. Materially smaller surface than P0.S7.D-C's 10 surfaces** — schema-version infrastructure (drop + init + rebuild + sentinel) already in place from prior v1→v2 work.

---

## 3. D-decisions surfaced

| ID | Topic | Architect's lean |
|---|---|---|
| D1 | Privacy filter shape in `find_shared_entities` Cypher | **(a) Block personal + household + system_only from cross-person traversal**; allow public only. Cross-person inference is ONLY meaningful when BOTH persons can independently see the matched entity, which is the public-tier definition. Cross-person owner-override (P0.S7 P1 (ii)) doesn't apply to graph traversal — owner-override is for `query_knowledge_for` where the requester is identified; graph queries are recipient-agnostic by nature. |
| D2 | `privacy_level` placement: edge vs node? | **(a) Edge** — `privacy_level` is a property of the FACT (the RELATES_TO edge), not the ENTITY (the value node). Same entity name "diabetes" can appear in a `health_condition` edge (personal) AND a `discussed_topic` edge (household) — different tiers per edge. Entity-level placement loses this granularity. |
| D3 | Does `get_graph_context` (1-hop reader) also need a privacy filter? | **NEEDS CLARIFICATION**: `get_graph_context` is called from `BrainOrchestrator.get_context` for the CURRENT speaker's own entity 1-hop graph. Per the P0.S7 P1 (ii) owner-override model, a person querying their OWN graph sees all tiers (including their own personal facts). But what about querying ANOTHER person's graph (caller has subject's name)? Plan v1 grep-verifies the callers + commits to disposition. Architect's lean: skip personal-tier when caller_pid != subject_pid AND caller_pid != best_friend_pid (matches SQL `_visibility_clause` semantic). |
| D4 | Default value for historical/legacy edges (where privacy_level isn't known) | **(a) `'personal'`** (matches `PRIVACY_LEVEL_DEFAULT` from S106 P0.S6 work). Fail-closed default; legacy edges treated as personal until explicitly classified. Since v3 rebuild always reads from brain.db (where privacy_level is backfilled), this only matters for transient races during the rebuild window. |
| D5 | Schema-rebuild discipline — does v3 bump risk dropping any in-flight extractions? | **NO** — P0.X atomicity discipline (lines 6545-6549) handles this: eager sentinel BEFORE destructive op, SQL-first commit, graceful degraded-mode fallback if Kuzu init fails. The existing rebuild path is robust. v3 bump rides on this established infrastructure. |
| D6 | Test surface — fast (AST) vs slow (live Kuzu) | **Hybrid**: AST tests for schema definition + Cypher-query text (fast, primary contract); 1-2 behavioral tests using real Kuzu in-memory DB to validate filter semantics end-to-end (slow-marked). Apply newly-banked AST-forward-property-tests-are-the-workhorse discipline: AST is primary, behavioral is belt-and-braces. |
| D7 | Schema-version trigger: anything special needed for v3? | **NO** — existing infrastructure (lines 6554-6570) already handles drop + init + rebuild on version mismatch. D-B just bumps the constant; the trigger fires automatically on next boot. |
| D8 | `valid_at` (currently NOT NULL per schema) interaction with v3 | NO CHANGE — v3 adds a new column; existing columns unchanged. Backward-compat for v2-shape reads not needed because v3 = wipe + rebuild (no v2 edges survive). |

---

## 4. Effort estimate + phase shape

D-B scope under D1-D8 locks:

| Phase | Scope | Tests | Time |
|---|---|---|---|
| 1 | `GRAPH_SCHEMA_VERSION 2 → 3` + schema definition extension (+5 cols becomes +6 cols with privacy_level) + `_create_edge` + `store_fact` + `rebuild_entity_from_knowledge` updated to thread privacy_level | +3 | ~quarter-day |
| 2 | `find_shared_entities` Cypher filter (D1) + `get_graph_context` filter if D3 (a) chosen | +2 | ~quarter-day |
| 3 | AST invariants (schema has privacy_level; Cypher queries filter on it; rebuild propagates from brain.db) + 1 slow-tier behavioral test | +3 | ~quarter-day |
| 4 | 5 deliberate-regression confirmations + closure | +0 | ~quarter-day |

**Total: ~6-8 tests, ~half-day to 1 day, suite 2377 → ~2384.**

S107 estimate was "~1 day" — Phase 0 audit confirms it. Schema-upgrade infrastructure is the bulk of the cost; that's already paid.

---

## 5. Pre-decision flags

### 5.1 Scope-expansion-via-Phase-0 instance count

P0.S7.D-C banked the first instance (10 surfaces vs assumed 3). D-B's grep finds 8 surfaces — slightly UNDER my pre-audit estimate of 10-12. So **D-B is NOT a scope-expansion instance**. The pre-audit mental model held within ~25%.

This is useful data: the scope-expansion observation may be specific to deletion/cleanup work (where dependency-fan-out is hard to predict) rather than additive work (where the change surface is more bounded by the new feature's scope).

### 5.2 Sub-pattern A check

Is the S112-deferral-falsification a sub-pattern A wrong-premise instance? **Architect's lean: NO.** The S112 deferral was correct at the time — the premise was "no concrete active leak EXISTS NOW given current code." It's not the architect making a wrong premise; it's a deferred decision becoming load-bearing because downstream work (κ extraction) changed the threat landscape.

The honest framing: this is a **"deferred-decision-becomes-load-bearing-when-downstream-ships"** observation. Distinct from sub-pattern A wrong-premise (where the architect's mental model was off) AND distinct from scope-expansion-via-Phase-0 (where the scope itself was bigger than expected).

If this pattern recurs (deferred decisions getting un-deferred by downstream work), it may surface as a separate observation. Currently 1 instance (P0.S7.D-B). Bank as informal observation alongside the other P0.S7-family observations.

### 5.3 Bundled-queue canary timing

Per user's 2026-05-19 direction: D-B ships into the bundled queue, validates with the bundled canary post-D-E. The privacy filter behavior (D1, D3) is best validated empirically in a real multi-person canary. D-B's CI tests prove the WIRING; the canary proves the actual privacy semantic holds.

---

## 6. Test specification preview (Plan v1 detailed)

Applying AST-forward-property-tests-are-the-workhorse discipline:

### Phase 1 tests (schema + writers)

1. **AST-forward-property**: `GraphDB._init_schema` source contains `privacy_level STRING` in the RELATES_TO CREATE statement.
2. **AST-forward-property**: `GraphDB._create_edge` signature includes `privacy_level: str` parameter; method body's Cypher INSERT includes the column.
3. **AST-forward-property**: `GraphDB.store_fact` body calls `_create_edge` with `privacy_level=ext.privacy_level`.

### Phase 2 tests (read paths)

4. **AST-forward-property**: `GraphDB.find_shared_entities` Cypher WHERE clause includes `r.privacy_level = 'public'` (D1 filter).
5. **Behavioral (slow-marked, real Kuzu)**: seed Kuzu with 3 edges (1 public, 1 personal, 1 system_only); call `find_shared_entities`; assert ONLY the public edge surfaces.

### Phase 3 tests (invariants)

6. **AST-forward-property**: `rebuild_entity_from_knowledge` reads `row.get("privacy_level", PRIVACY_LEVEL_DEFAULT)` and passes to `_create_edge`.
7. **AST-forward-property + invariant**: every site that calls `_create_edge` passes `privacy_level=` (scan all callers; assert kwarg present). Catches future code paths that forget the new field.
8. **AST-forward-property**: `GRAPH_SCHEMA_VERSION = 3` in `core/config.py`; documentation comment cross-references P0.S7.D-B.

### Phase 4 (deliberate-regression confirmations — closure items)

- Drop `privacy_level` from `_init_schema` → test 1 fails → revert.
- Drop the Cypher filter from `find_shared_entities` → test 5 (behavioral) returns personal/system_only edges → revert.
- Set v3 version constant back to 2 → test 8 fails → revert.
- Drop the kwarg from one `_create_edge` caller → test 7 fails → revert.
- Add a new helper that calls `_create_edge` without `privacy_level=` → test 7 fails → revert.

**Net new tests: 8 logical** (7 AST + 1 behavioral slow-marked). Suite delta forecast: 2377 → ~2385.

**Why AST-primary**: schema-definition + Cypher-query text invariants are perfectly expressible as AST forward-properties. Source-inspection ordering would catch text presence but not catch the case where `privacy_level` is declared but never written; AST catches both.

---

## 7. Discipline-count predictions

- **Spec-first review cycle**: 11-for-11 → **12-for-12** on closure (P0.S7.D-B added).
- **Sub-pattern A**: stays at **4 instances** (D-B is deferred-decision-becomes-load-bearing, NOT new wrong-premise — strict-read).
- **Tripwires-must-match-deferral-surface**: stays **4-for-4**. D-B's tests are forward-property (catch real failures: missing privacy_level in schema or query). NOT a tripwire-style deferral-guard.
- **Developer-improves-on-spec**: stays **6-for-6** unless code phase surfaces a mechanism improvement.
- **Induction-surfaces-invariant-gaps**: stays **7-for-7** unless Phase 4 surfaces a real gap.
- **Canary-finding tracker**: stays at **2 instances** (D-B is not canary-surfaced; surfaced from downstream-shipping analysis).
- **Canary-gate override (informal)**: stays at **1 instance**.
- **Scope-expansion-via-Phase-0 (informal)**: stays at **1 instance** (D-B is NOT scope-expansion; pre-audit estimate was accurate within ~25%).
- **NEW informal observation candidate**: **Deferred-decision-becomes-load-bearing-when-downstream-ships** — 1 instance (P0.S7.D-B). Distinct from sub-pattern A wrong-premise + scope-expansion. If 5+ accumulate, may surface as `### Deferred-decisions-need-re-evaluation-on-downstream-ship` doctrine.

---

## 8. Threats / risks

1. **Existing graph data wipe on v2 → v3 upgrade**. The schema-version trigger drops + rebuilds. ALL in-flight graph state is lost during the rebuild window. Mitigation: `_ensure_graph_sync` rebuilds from brain.db (the authoritative source). Rebuild includes `rebuild_entity_from_knowledge` for every entity in brain.db. Production impact: ~seconds-to-minutes rebuild time on first boot after deployment; brain.db rows preserved throughout. P0.X atomicity discipline (sentinel + SQL-first + degraded-mode fallback) protects against partial-rebuild data corruption.

2. **`find_shared_entities` filter strictness (D1)**. Locking at "public only" eliminates ALL personal/household/system_only edges from cross-person inference. This is the safest setting but may also eliminate LEGITIMATE cross-person matches (e.g., two visitors who both have "lives_in_Bangalore" — currently public-tier — that the brain could use for natural conversation hooks). Plan v1 verifies the legitimate-match surface against the cost of the privacy fix. If too restrictive in practice, Plan v2 may revise to (b) include household-tier with stricter joint-membership check.

3. **`get_graph_context` (D3) — caller analysis needed**. The function is called from `BrainOrchestrator.get_context`. Plan v1 grep-enumerates callers + commits to disposition. If callers always query the speaker's OWN graph, no filter needed (owner sees all). If callers query OTHER persons' graphs (cross-person paths), the privacy filter applies.

4. **Cypher syntax compatibility**. Kuzu's Cypher dialect may have edge-case behavior with the new `privacy_level` column in WHERE clauses. Plan v1 includes 1 explicit behavioral test running real Kuzu to catch any syntax incompatibility before developer hits it.

5. **Schema-upgrade rebuild time scaling**. Current production likely has hundreds-to-thousands of brain.db knowledge rows. Rebuild rebuilds every entity sequentially. If rebuild time exceeds ~30 seconds on first boot, user-experience impact (boot delay). Mitigation: parallelize rebuild OR accept the one-time delay. Worth measuring during Phase 4 or first deployment.

---

## 9. Next steps

1. **Auditor reviews this Phase 0 audit.** Specifically: (a) §1 deferral-rationale-reversal — solid framing, or push back? (b) D1 — "public only" filter strictness for `find_shared_entities`, or revise to include household with joint-membership check? (c) D3 — `get_graph_context` filter disposition? (d) §5.2 framing of "deferred-decision-becomes-load-bearing" as new informal observation distinct from sub-pattern A — accept or merge?
2. **D-decisions locked** at Phase 0 sign-off.
3. **Plan v1** drafted with locked D-decisions + Plan v1 grep-enumeration of `get_graph_context` callers.
4. **Plan v2** if precision items surface.
5. **Joint sign-off → developer handoff** for 4-phase implementation.

---

## 10. Reference documents

- `tests/p0_s7_audit.md` — P0.S7 Phase 0 audit (D-B bookmark; S107 deferral rationale)
- `tests/p0_s7_dc_audit.md` — P0.S7.D-C Phase 0 audit (scope-expansion-via-Phase-0 observation; sibling spec in queue)
- `tests/p0_s7_dc_plan_v1.md` — P0.S7.D-C Plan v1 (forward-property test-design pattern reference)
- `tests/p0_s7_2_plan_v2.md` — P0.S7.2 (κ multi-person assistant-turn extraction — the downstream ship that falsified S112's deferral premise)
- `core/brain_agent.py:3464-3776` — `GraphDB` class definition
- `core/brain_agent.py:3505` — `_init_schema` (D-B schema-change site)
- `core/brain_agent.py:3531` — `_create_edge` (D-B writer-extension site)
- `core/brain_agent.py:3556` — `store_fact` (D-B writer-extension site)
- `core/brain_agent.py:3577` — `rebuild_entity_from_knowledge` (D-B writer-extension site)
- `core/brain_agent.py:3611` — `get_graph_context` (D3 disposition target)
- `core/brain_agent.py:3647-3760` — `find_shared_entities` (D-B query-extension site + S107/S112 deferral docstring)
- `core/brain_agent.py:6541-6570` — `_ensure_graph_sync` schema-upgrade path (no change needed)
- `core/config.py:1242` — `GRAPH_SCHEMA_VERSION = 2` (D-B constant-bump site)
- `everything_about_system.md` §338 — Kuzu v3 deferral context (historical reference)
- Memory: `feedback_spec_time_grep_verification.md` — applied at audit drafting
- Memory: `feedback_ast_forward_property_tests.md` — applied at §6 test-design

---

**Standing by for auditor verdict on §1 framing + D-decision leans + §5.2 new-observation classification before drafting Plan v1.**
