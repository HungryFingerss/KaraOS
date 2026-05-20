# P0.S7.D-B — Kuzu v3 schema bump (privacy_level on graph edges) — Plan v1

**Date:** 2026-05-19
**Author:** architect
**Status:** Plan v1 — drafted against Phase 0 D-lock (2026-05-19) + auditor's 2 precision items + 3 minor observations from `tests/p0_s7_db_audit.md`'s Phase 0 review verdict. Standing by for auditor's Plan v1 review → Plan v2 (if precision items surface) → joint sign-off → developer handoff.

**Phase 0 audit:** `tests/p0_s7_db_audit.md` (premise reset; 8-surface map; deferral-rationale reversal).

**Disciplines applied at Plan v1 drafting:**
- Spec-time grep-verification: all function names + line numbers grep-verified 2026-05-19
- AST-forward-property-tests-are-the-workhorse: §7 test design prioritizes AST primary

---

## 1. Locked decision reference (Phase 0 D-lock 2026-05-19)

| ID | Topic | Locked at |
|---|---|---|
| D1 | Filter shape in `find_shared_entities` | **(a) Public only** — cross-person inference is meaningfully privacy-safe only at public tier |
| D2 | privacy_level placement | **(a) Edge** — same entity name can carry different tiers per fact |
| D3 | `get_graph_context` filter | **Plan v1 grep-verified + commits** (see §3 below) — fail-closed default per Precision Item 1 |
| D4 | Default for legacy edges | **(a) `'personal'`** — matches `PRIVACY_LEVEL_DEFAULT` (S106) |
| D5 | Rebuild-window safety | NO CHANGE — P0.X atomicity covers it |
| D6 | Test surface | Hybrid AST primary + 1-2 slow behavioral; AST forward-property is the workhorse |
| D7 | Schema-version trigger | NO CHANGE — existing infra (lines 6554-6570) automated |
| D8 | v2-edge backward compat | NOT NEEDED — v3 wipes + rebuilds |
| **P1** (precision item 1) | D3 fail-closed under uncertainty | **LOCKED** — see §3.3 below; if Plan v1 grep finds mixed caller patterns, filter is MANDATORY |
| **P2** (precision item 2) | D1 mixed-tier-per-entity semantic | **LOCKED** — see §4.2 below; explicit Plan v1 line + behavioral test 5 verifies |

---

## 2. Architectural overview

Three coordinated surface changes:

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Surface 1: Schema definition extension                                    │
│                                                                            │
│  core/config.py:1242 — GRAPH_SCHEMA_VERSION 2 → 3                          │
│  core/brain_agent.py:3505-3519 — RELATES_TO edge gains privacy_level       │
│    STRING column (per D2: edge-level placement)                            │
│                                                                            │
│  Existing schema-upgrade infrastructure (lines 6554-6570) AUTO-TRIGGERS    │
│    on next boot: drop_schema + _init_schema + rebuild from brain.db        │
│  P0.X atomicity discipline guarantees safe rebuild + degraded-mode fallback│
└──────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Surface 2: Writer paths thread privacy_level                              │
│                                                                            │
│  _create_edge: + privacy_level: str kwarg → Cypher CREATE includes col    │
│  store_fact: passes ext.privacy_level (already exists on Extraction)       │
│  rebuild_entity_from_knowledge: reads row.get("privacy_level",            │
│    PRIVACY_LEVEL_DEFAULT) → passes to _create_edge                          │
└──────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Surface 3: Reader paths apply privacy filter                              │
│                                                                            │
│  find_shared_entities Cypher WHERE: + r.privacy_level = 'public'           │
│    (per D1: public-only; cross-person traversal can't use owner-override)  │
│                                                                            │
│  get_graph_context: + caller_pid kwarg → Cypher WHERE mirrors              │
│    _visibility_clause semantic (owner-override + best_friend override +   │
│    public-default)                                                         │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 3. D3 grep-verification + disposition (Precision Item 1)

### 3.1 Grep findings

`get_graph_context` callers in the codebase (2026-05-19 grep):

| Site | Type | Caller pattern |
|---|---|---|
| `core/brain_agent.py:7943` | Production caller in `BrainOrchestrator.get_context` | **MIXED** — same-person OR cross-person depending on query context; existing defensive `if not _filtering:` skip at line 7941 guards against cross-person leak |
| `test_brain_agent.py` (~20 sites) | Test references | Test-only — exercise the function directly with various entity names |
| `test_pipeline.py:9122` | Test reference | Test-only — exercises `gdb.get_graph_context("Alice")` |

**Single production caller. The pattern is MIXED — same-person vs cross-person query depending on `_filtering` state.**

### 3.2 Current defensive behavior (pre-D-B)

`core/brain_agent.py:7941-7945`:

```python
# Graph path: skip when privacy filtering is active — Kuzu has no privacy_level field.
if not _filtering:
    ctx = self._graph_db.get_graph_context(person_name)
else:
    ctx = None
```

The caller bypasses the graph ENTIRELY when filtering is active. This is the existing belt-and-braces. **D-B makes this defensive skip obsolete-but-harmless** because the Cypher filter applies at the graph level.

### 3.3 D3 disposition (Precision Item 1: fail-closed under uncertainty)

Per auditor's Precision Item 1: *"If the caller pattern is mixed, the default disposition MUST be add the filter (fail-closed)."*

Caller pattern IS mixed (one production caller with both same-person + cross-person query modes). **Filter is MANDATORY.**

**Plan v1 lock for D3:**

```python
def get_graph_context(
    self,
    entity_name: str,
    caller_pid: "str | None" = None,
    best_friend_id: "str | None" = None,
) -> "str | None":
    """1-hop graph context for entity_name, filtered by caller's
    privacy access per the v3 schema's privacy_level column.

    Privacy filter semantic (mirrors _visibility_clause):
      - caller_pid == subject_pid (owner-of-graph) → all tiers visible
      - caller_pid == best_friend_id → all non-system_only tiers visible
      - caller_pid != subject_pid AND != best_friend_id → public only
      - caller_pid == None (legacy call) → public only (FAIL-CLOSED per P1)

    The subject_pid is resolved from entity_name via brain.db person-name lookup
    inside the method; caller doesn't need to pre-resolve.
    """
```

**Default behavior (caller_pid omitted) is fail-closed = public-only.** Legacy callers that don't pass `caller_pid` get the safest tier. Existing single production caller at line 7943 updated to pass `caller_pid=requester_person_id` and `best_friend_id=best_friend_id` from the surrounding scope.

### 3.4 Defensive `if not _filtering:` skip — Plan v1 disposition

**KEEP the existing defensive skip at line 7941** as-is during D-B. Reasoning:
- Post-D-B with v3 + privacy filter, the skip becomes REDUNDANT (filter handles it)
- But redundant-and-correct is fine; removing it adds risk without value
- Plan v2 or D-B follow-up can clean up the skip if Phase 4 deliberate-regression cycles validate the filter works correctly without the defensive guard

**Plan v1 commitment:** existing defensive skip preserved during D-B. Phase 4 closure narrative banks "redundant defensive skip" as known dead-code-when-flag-on for future cleanup PR.

---

## 4. D1 mixed-tier-per-entity semantic clarification (Precision Item 2)

### 4.1 The semantic

The same entity name (e.g., `'diabetes'`, `'cricket'`, `'Bangalore'`) can participate in MULTIPLE edges with DIFFERENT privacy_level values in one person's graph:

- `Jagan.discussed_topic='diabetes'` (privacy_level='household' — a topic discussed in the household)
- `Jagan.has_condition='diabetes'` (privacy_level='personal' — a health attribute about Jagan)
- `Jagan.knows_about='diabetes'` (privacy_level='public' — common knowledge)

After D-B, only the **public-tier edge** participates in cross-person matching. The personal-tier and household-tier edges are filtered at Cypher-WHERE-clause time.

### 4.2 Plan v1 lock (Precision Item 2 explicit statement)

> **When the same entity name participates in MULTIPLE RELATES_TO edges with different privacy_level values in one person's graph, only the public-tier edge participates in cross-person matching via `find_shared_entities`. Personal-tier and household-tier edges are filtered at the Cypher WHERE clause. The filter is per-edge, not per-entity. Test 5 (behavioral, slow-marked) seeds this mixed-tier case explicitly to verify.**

Documented in `find_shared_entities` docstring (post-D-B) so future readers don't infer entity-level filtering by accident.

---

## 5. Three minor observations from auditor verdict (banked)

### 5.1 Tier-mislabel correction (auditor obs A)

Phase 0 audit §8.2 cited `'lives_in='Bangalore''` as a public-tier facts example. Per `PRIVACY_LEVEL_STATIC_MAP` (S95 P0.S6 work), `lives_in` is **personal-tier**, not public. The auditor flagged this.

**Plan v1 corrected example**: `from_country='India'` (which IS public per static_map) replaces the Bangalore example wherever the threat-§8 discussion needs a public-tier illustration. Legitimate-match concern remains real — cross-person matching at public tier (`from_country='India'`) is the canonical use case for ProactiveNudgeAgent's *"you both mentioned X"* hook.

### 5.2 Rebuild duration observability (auditor obs B)

Per auditor's suggestion: add ~3 lines to Phase 1 implementation:

```python
# In BrainOrchestrator._ensure_graph_sync after rebuild completes
_rebuild_secs = time.time() - _rebuild_start
print(
    f"[Schema] Graph rebuild v{stored_version}→v{GRAPH_SCHEMA_VERSION} "
    f"completed in {_rebuild_secs:.1f}s "
    f"({_entity_count} entities, {_edge_count} edges)"
)
```

Production-scale-of-pain becomes measurable. If `>30s` threshold from threat §8.5 hits, surfaces in canary logs immediately rather than via user complaint.

**Caveat**: the existing rebuild code at line 6554-6570 doesn't currently capture `_entity_count` / `_edge_count` separately. Plan v1 commits to adding the counters during the rebuild loop (read from brain.db rows count + RELATES_TO edges created count). If implementation surfaces complexity in capturing the edge count cleanly (e.g., rebuild fans out across multiple entities), simplify to entity count only.

### 5.3 Scope-expansion hypothesis tracking (auditor obs C)

Phase 0 audit §5.1 surfaced the hypothesis: **scope-expansion-via-Phase-0 may be specific to deletion/cleanup work**. Currently 1 instance (P0.S7.D-C, which was cleanup) and 1 non-instance (P0.S7.D-B, which is additive, pre-audit estimate held within ~25%).

Plan v1 banking: when D-D (RoomOrchestrator class extraction — mixed refactor + cleanup) lands, evaluate scope-expansion against pre-audit estimate. If D-D shows scope-expansion AND D-E (multi-speaker conversation_turn redesign — refactor) doesn't, the deletion-specific hypothesis gains evidence. If both D-D + D-E show it, the hypothesis weakens.

**Not a discipline yet** (1 data point isn't a pattern). Banked for forward-tracking.

---

## 6. Implementation phases (Plan v1 — locked surface map)

### Phase 1 — Schema + writers + rebuild observability (+3 tests, ~quarter-day)

- `core/config.py:1242` — `GRAPH_SCHEMA_VERSION = 2 → 3` + cross-reference comment to P0.S7.D-B.
- `core/brain_agent.py:3505-3519` — `_init_schema` extends RELATES_TO with `privacy_level STRING` column.
- `core/brain_agent.py:3531-3554` — `_create_edge` signature gains `privacy_level: str = "personal"` kwarg (fail-closed default per D4); Cypher CREATE includes the column.
- `core/brain_agent.py:3556-3567` — `store_fact` passes `ext.privacy_level` (already on Extraction post-P0.S6).
- `core/brain_agent.py:3577-3609` — `rebuild_entity_from_knowledge` reads `row.get("privacy_level", PRIVACY_LEVEL_DEFAULT)`; passes to `_create_edge`.
- `core/brain_agent.py:6554-6570` — rebuild observability logging per §5.2.
- Tests 1, 2, 3 from §7.
- **Suite checkpoint:** 2377 → 2380 (+3).

### Phase 2 — Reader filters (+2 tests, ~quarter-day)

- `core/brain_agent.py:3611-3645` — `get_graph_context` signature gains `caller_pid: str | None = None` + `best_friend_id: str | None = None`; Cypher WHERE adds privacy filter mirroring `_visibility_clause` semantic; fail-closed default (caller_pid omitted → public only).
- `core/brain_agent.py:3647-3760` — `find_shared_entities` Cypher WHERE adds `r.privacy_level = 'public'` per D1; docstring updated with mixed-tier-per-entity semantic per §4.2.
- `core/brain_agent.py:7943` — production caller updated to pass `caller_pid=requester_person_id, best_friend_id=best_friend_id`.
- Tests 4, 5 from §7.
- **Suite checkpoint:** 2380 → 2382 (+2).

### Phase 3 — AST invariants (+3 tests, ~quarter-day)

- 3 AST forward-property tests per §7.
- **Suite checkpoint:** 2382 → 2385 (+3).

### Phase 4 — Deliberate-regression confirmations + closure (+0 tests, ~quarter-day)

- 5 deliberate-regression confirmations per §7 Phase 4 list.
- Closure-report banking:
  - 2 Plan v1 precision items resolution (D3 fail-closed + D1 mixed-tier semantic)
  - 3 minor observations resolution (tier-mislabel fixed + rebuild observability shipped + scope-expansion hypothesis forward-tracked)
  - Defensive `if not _filtering:` skip preserved as known dead-code-when-flag-on for future cleanup
  - NEW informal observation banked: **Deferral-rationale-expires-when-downstream-ships** — 1 instance (P0.S7.D-B; toward potential 5+ doctrine elevation)
  - Discipline-count updates (Plan v1 §10)

**Total effort: ~half-day to 1 day. Net new tests: 8 logical. Suite delta: 2377 → 2385.**

---

## 7. Test specification (Plan v1 — AST-forward-property primary)

### Phase 1 tests (schema + writers)

1. **`test_init_schema_relates_to_includes_privacy_level`** (AST forward-property) — Walk `GraphDB._init_schema` AST. Find the `_conn.execute` call whose argument string starts with `"CREATE REL TABLE IF NOT EXISTS RELATES_TO("`. Assert that string contains the substring `"privacy_level STRING"`. AST-based source extraction; resilient to formatting.
2. **`test_create_edge_signature_and_body_include_privacy_level`** (AST forward-property) — Walk `GraphDB._create_edge` AST. Assert (a) signature has `privacy_level` parameter; (b) method body's Cypher INSERT references `privacy_level: $...`.
3. **`test_rebuild_entity_from_knowledge_threads_privacy_level`** (AST forward-property) — Walk `rebuild_entity_from_knowledge` AST. Assert the call to `_create_edge` includes `privacy_level=row.get("privacy_level", PRIVACY_LEVEL_DEFAULT)` (or equivalent ast.keyword node).

### Phase 2 tests (reader filters)

4. **`test_find_shared_entities_cypher_filters_on_privacy_level_public`** (AST forward-property + Cypher-text inspection) — Walk `find_shared_entities` AST. Extract the Cypher query string. Assert WHERE clause contains `r.privacy_level = 'public'` (or equivalent quote-style).
5. **`test_find_shared_entities_filter_behavioral`** (slow-marked, real Kuzu in-memory DB) — Seed 5 edges across 2 persons:
   - Person A: 1 public edge to `'India'`, 1 personal edge to `'diabetes'`, 1 mixed entity (same name `'India'` with 2 edges: public + personal)
   - Person B: 1 public edge to `'India'`, 1 personal edge to `'diabetes'`, 1 personal edge to `'cricket'`
   - Call `find_shared_entities(A, B)`.
   - Assert ONLY `'India'` returned (public-tier match); `'diabetes'` NOT returned (personal); mixed-tier `'India'` only surfaces via the public edge.
   - This explicitly verifies the §4.2 mixed-tier-per-entity semantic.

### Phase 3 tests (AST invariants)

6. **`test_graph_schema_version_is_3`** (AST + source-inspection) — Read `core/config.py`. Assert `GRAPH_SCHEMA_VERSION = 3`. Cross-check that the line comment references P0.S7.D-B.
7. **`test_get_graph_context_signature_includes_caller_pid_and_filters`** (AST forward-property) — Walk `get_graph_context` AST. Assert (a) signature has `caller_pid` parameter; (b) method body's Cypher WHERE references `privacy_level` (filter clause present). Fail-closed default verified by signature inspection: `caller_pid: str | None = None` means default-skipped-tier behavior.
8. **`test_all_create_edge_callers_pass_privacy_level`** (AST forward-property, inverse-check) — Scan `core/brain_agent.py` for every `_create_edge` call site. Assert each call passes `privacy_level=` kwarg. Catches future code paths that add new graph-edge writers without threading privacy_level. (Inverse-check discipline per P0.5.)

### Phase 4 (deliberate-regression confirmations — closure items)

- Drop `privacy_level STRING` from `_init_schema` → test 1 fails → revert.
- Drop the Cypher filter from `find_shared_entities` → test 5 (behavioral) returns personal-tier edges → revert.
- Set `GRAPH_SCHEMA_VERSION` back to 2 → test 6 fails → revert.
- Drop `caller_pid` kwarg from `get_graph_context` → test 7 fails → revert.
- Add a new helper function that calls `_create_edge` without `privacy_level=` → test 8 fails → revert.

**Net new tests: 8 logical (7 AST + 1 behavioral slow-marked).** Suite delta forecast: 2377 → 2385.

---

## 8. Validation gate

1. All 8 new tests green; full-suite green at 2385.
2. 5/5 deliberate-regression confirmations pass (induction protocol).
3. Rebuild observability log line fires on next-boot schema upgrade (visible in terminal_output.md when D-B deploys).
4. 2 Plan v1 precision items resolved (D3 fail-closed default + D1 mixed-tier semantic locked in code + docstring).
5. 3 minor observations from auditor verdict resolved.
6. Closure narrative banks new informal observation: **Deferral-rationale-expires-when-downstream-ships** (1 instance, P0.S7.D-B).

---

## 9. Threats / risks

1. **Threat §8.1 from Phase 0 audit (rebuild wipes in-flight graph state)** — preserved as-is. P0.X atomicity discipline mitigates.

2. **Threat §8.2 — D1 strictness eliminates legitimate cross-person matches** — preserved. Tier-mislabel corrected per §5.1 (use `from_country='India'` as the public-tier example). If too restrictive in practice, Plan v2 may revise to include household-tier with joint-membership check.

3. **Threat §8.3 — `get_graph_context` cross-person leak (D3)** — RESOLVED by Plan v1 §3.3 disposition (filter is mandatory under mixed caller pattern).

4. **Threat §8.4 — Cypher syntax compatibility** — preserved. Test 5 (behavioral) catches before developer hits it.

5. **Threat §8.5 — rebuild time scaling** — addressed by §5.2 rebuild observability. Production-scale-of-pain measurable on first deployment.

6. **NEW — defensive `_filtering` skip becomes dead-code-when-flag-on**. Plan v1 §3.4 disposition: KEEP during D-B; future cleanup PR after Phase 4 validation. Not a blocker; documented.

---

## 10. Discipline-count predictions (strict-read locked per Phase 0 auditor verdict)

- **Spec-first review cycle**: 11-for-11 → **12-for-12** on closure.
- **Sub-pattern A**: stays at **4 instances** (D-B is Deferral-rationale-expires pattern, not new wrong-premise).
- **Tripwires-must-match-deferral-surface**: stays **4-for-4** (D-B tests are forward-property).
- **Developer-improves-on-spec**: stays **6-for-6** unless code phase surfaces a mechanism improvement.
- **Induction-surfaces-invariant-gaps**: stays **7-for-7** unless Phase 4 surfaces a real gap.
- **Canary-finding tracker**: stays at **2 instances**.
- **Canary-gate override (informal)**: stays at **1 instance**.
- **Scope-expansion-via-Phase-0 (informal)**: stays at **1 instance** (D-B pre-audit estimate held; not a scope-expansion case).
- **NEW informal observation banked**: **Deferral-rationale-expires-when-downstream-ships** — **1 instance** (P0.S7.D-B). Auditor's wording suggestion adopted (shorter than architect's original "Deferred-decision-becomes-load-bearing"). Toward potential future `### Deferral-rationale-expires-when-downstream-ships` doctrine at 5+ threshold.

---

## 11. Open items / risks summary

1. **D3 default behavior** locked at fail-closed (public-only when caller_pid omitted). Plan v1 §3.3 commits.
2. **Defensive `_filtering` skip** preserved as known redundant-after-D-B; future cleanup PR scheduled in Phase 4 closure bookmarks.
3. **Rebuild observability** logging added in Phase 1 per auditor obs B.
4. **Mixed-tier-per-entity semantic** explicitly stated in `find_shared_entities` docstring + tested behaviorally in test 5 per Precision Item 2.
5. **Scope-expansion hypothesis** forward-tracked: evaluate at D-D + D-E closures to test "deletion-specific" prediction.

---

## 12. References

- `tests/p0_s7_db_audit.md` — Phase 0 audit (premise-shift framing + 8-surface map)
- `tests/p0_s7_audit.md` — P0.S7 Phase 0 audit (D-B bookmark; S107 deferral context)
- `tests/p0_s7_dc_plan_v1.md` — P0.S7.D-C Plan v1 (forward-property test-design pattern reference)
- `tests/p0_s7_2_plan_v2.md` — P0.S7.2 κ multi-person extraction (the downstream ship that falsified S112 deferral)
- `core/brain_agent.py:3464-3776` — `GraphDB` class
- `core/brain_agent.py:3505` — `_init_schema` (Phase 1 schema-change site)
- `core/brain_agent.py:3531` — `_create_edge` (Phase 1 writer site)
- `core/brain_agent.py:3556` — `store_fact` (Phase 1 writer pass-through)
- `core/brain_agent.py:3577` — `rebuild_entity_from_knowledge` (Phase 1 writer site)
- `core/brain_agent.py:3611` — `get_graph_context` (Phase 2 reader-filter site)
- `core/brain_agent.py:3647` — `find_shared_entities` (Phase 2 reader-filter site)
- `core/brain_agent.py:6554-6570` — `_ensure_graph_sync` schema-upgrade path (Phase 1 observability addition)
- `core/brain_agent.py:7943` — single production caller of `get_graph_context` (Phase 2 caller update site)
- `core/brain_agent.py:7941` — defensive `_filtering` skip (preserved as redundant-after-D-B)
- `core/config.py:1242` — `GRAPH_SCHEMA_VERSION` constant (Phase 1 bump site)
- `everything_about_system.md` §338 — Kuzu v3 deferral historical context
- Memory: `feedback_spec_time_grep_verification.md` — applied at Plan v1 drafting
- Memory: `feedback_ast_forward_property_tests.md` — applied at §7 test design

---

## 13. Next steps

1. **Auditor reviews Plan v1.** Specifically: (a) §3.3 D3 disposition + caller-update pattern reasonable? (b) §5.2 rebuild observability shape — entity_count + edge_count both, or simplify to entity_count alone? (c) §4.2 mixed-tier-per-entity semantic statement complete enough? (d) §9 risk surface — anything missed?
2. **Plan v2** if precision items surface (architect expects 0-2 items; D-B's narrower surface than D-C reduces revision likelihood).
3. **Joint sign-off** → developer handoff for 4-phase implementation.
4. **Phase 4 closure narrative** banks new informal observation + scope-expansion hypothesis forward-tracking.
