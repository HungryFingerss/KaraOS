# P0.S7.D-B — Kuzu v3 schema bump (privacy_level on graph edges) — Plan v2

**Date:** 2026-05-19
**Author:** architect
**Status:** Plan v2 — drafted against locked D1-D8 + L1-L3 (Plan v1) + auditor's 1 MEDIUM precision item + 2 LOW clarifications from Plan v1 review verdict. Plan v1 retained at `tests/p0_s7_db_plan_v1.md` for delta visibility. Standing by for auditor's Plan v2 verdict → joint sign-off → developer handoff.

**Phase 0 audit:** `tests/p0_s7_db_audit.md`.
**Plan v1:** `tests/p0_s7_db_plan_v1.md`.

**Disciplines applied at Plan v2 drafting:**
- Spec-time grep-verification: all function names + line numbers + test site counts grep-verified 2026-05-19
- AST-forward-property-tests-are-the-workhorse: §6 test design unchanged from Plan v1 (AST primary + 1 slow behavioral)

**Delta from Plan v1 (3 items):**
- **MEDIUM 1 (auditor precision item)** — test-surface disposition: 15 `get_graph_context` callers in test files (not the ~21 auditor estimated; grep-verified count below); per-site disposition LOCKED at **(a) pass `caller_pid` matching subject** for all 15. See §3.5.
- **LOW 1 (auditor clarification)** — D3 framing: defense-in-depth vs load-bearing distinction. D1 (`find_shared_entities` filter) closes the active leak that κ ship surfaced; D3 (`get_graph_context` filter) raises the floor against future code paths. Closure-narrative honesty preserved. See §3.4.
- **LOW 2 (auditor clarification)** — §4.1 schema-concept clarifier: one-line refresher distinguishing entity-name vs attribute-name vs privacy_level. Prevents future readers from conflating the concepts. See §4.

Locked D-decisions and Plan v1 contract clauses unchanged except where explicit revision noted below.

---

## 1. Locked decision reference (Plan v1 unchanged unless noted)

| ID | Locked at | Plan v2 delta |
|---|---|---|
| D1 | (a) Public only in `find_shared_entities` | — |
| D2 | (a) Edge-level placement | — |
| D3 | Plan v1 grep-verified + fail-closed default + caller_pid kwarg | **Plan v2 §3.4** adds the load-bearing vs defense-in-depth framing (LOW 1) |
| D4 | (a) `'personal'` default | — |
| D5 | NO CHANGE — P0.X atomicity covers | — |
| D6 | Hybrid AST + 1 slow behavioral | — |
| D7 | NO CHANGE — schema-version trigger automated | — |
| D8 | NO v2-edge backward compat needed | — |
| **P1** (Plan v1) | D3 fail-closed under uncertainty | — |
| **P2** (Plan v1) | D1 mixed-tier-per-entity semantic | **Plan v2 §4** adds schema-concept clarifier (LOW 2) |
| **MED 1** (Plan v2) | Test-surface disposition for 15 `get_graph_context` test sites | See §3.5 — disposition (a) for ALL 15 sites |

---

## 2. Architectural overview (unchanged from Plan v1 §2)

Three coordinated surface changes: schema definition extension → writer paths thread privacy_level → reader paths apply privacy filter. See Plan v1 §2 for the architectural-overview diagram. Plan v2 makes no architectural-surface changes.

---

## 3. D3 disposition with LOW 1 framing (defense-in-depth vs load-bearing)

### 3.1 Grep findings (unchanged from Plan v1 §3.1)

`get_graph_context` production callers: **1** (at `core/brain_agent.py:7943`).
`get_graph_context` test callers: **15 sites across 2 files** (Plan v2 grep-verified count; auditor's estimate of ~21 was high). See §3.5.

### 3.2 Current defensive behavior (unchanged from Plan v1 §3.2)

`core/brain_agent.py:7941-7945` — existing `if not _filtering:` defensive skip bypasses graph when cross-person query is active. Preserved during D-B.

### 3.3 D3 disposition signature (unchanged from Plan v1 §3.3)

```python
def get_graph_context(
    self,
    entity_name: str,
    caller_pid: "str | None" = None,
    best_friend_id: "str | None" = None,
) -> "str | None":
```

Default `caller_pid=None` → fail-closed public-only filter.

### 3.4 LOW 1 framing — defense-in-depth vs load-bearing (NEW)

Auditor verdict acknowledged: **D3's `get_graph_context` Cypher filter is defense-in-depth — the load-bearing leak vector D-B closes is D1's `find_shared_entities` filter, NOT D3.**

The honest distinction:

| Filter | Role | Threat closed |
|---|---|---|
| D1 `find_shared_entities` Cypher filter | **LOAD-BEARING** — closes the active cross-person leak that P0.S7.2 κ ship surfaced | Personal-tier edges (e.g., `Lexi.received_recipe`) appearing in cross-person inference results to third parties |
| D3 `get_graph_context` Cypher filter | **DEFENSE-IN-DEPTH** — raises floor against future code paths | Hypothetical future caller of `get_graph_context` that doesn't replicate the existing `if not _filtering:` defensive skip at line 7941 |

**Why D3 is defense-in-depth, not load-bearing:** the existing `_filtering` skip at line 7941 (set when `caller != best_friend AND caller != subject`) ALREADY prevents the cross-person leak via this path TODAY. The Cypher filter D3 adds doesn't close an active leak — it raises the floor so that if any future code-path addition bypasses or removes the defensive skip, the privacy semantic still holds at the Cypher level.

**Closure-narrative banking (Plan v2 §11 + Phase 4 closure):**

> *"D3's `get_graph_context` filter is defense-in-depth — the existing `_filtering` skip at `core/brain_agent.py:7941` was already preventing the cross-person leak via this path. D1's `find_shared_entities` filter is the load-bearing privacy fix; D3 raises the floor against future code-path additions. Both ship together in D-B; both are correct; only one closes an active leak."*

This framing prevents future readers from inferring that D3 was closing an active leak and reverting the `_filtering` skip on the assumption that "the Cypher filter has it covered." The skip remains correct belt-and-braces.

### 3.5 MEDIUM 1 — Test-surface enumeration + per-site disposition (NEW)

Grep-verified 2026-05-19. **15 test sites total across 2 files:**

| # | File | Line | Test name (or context) | Subject | Disposition |
|---|---|---|---|---|---|
| 1 | test_brain_agent.py | 1598 | `test_store_fact_creates_relationship` | Jagan | (a) `caller_pid="Jagan"` |
| 2 | test_brain_agent.py | 1604 | `test_get_graph_context_none_for_unknown_entity` | nobody | (a) `caller_pid="nobody"` |
| 3 | test_brain_agent.py | 1610 | `test_get_graph_context_excludes_invalidated` | Jagan | (a) `caller_pid="Jagan"` |
| 4 | test_brain_agent.py | 1630 | `test_get_graph_context_excludes_expired` | Jagan | (a) `caller_pid="Jagan"` |
| 5 | test_brain_agent.py | 1658 | rebuild + fact persistence test | Jagan | (a) `caller_pid="Jagan"` |
| 6 | test_brain_agent.py | 1672 | rebuild() test | Jagan | (a) `caller_pid="Jagan"` |
| 7 | test_brain_agent.py | 1681 | confidence threshold for uncertain label | Jagan | (a) `caller_pid="Jagan"` |
| 8 | test_brain_agent.py | 1741 | dietary_preference test via orchestrator | Jagan | (a) `caller_pid="Jagan"` |
| 9 | test_brain_agent.py | 1790 | Ajay entity creation test | Ajay | (a) `caller_pid="Ajay"` |
| 10 | test_brain_agent.py | 1806 | `rebuild_entity_from_knowledge` test | Ajay | (a) `caller_pid="Ajay"` |
| 11 | test_brain_agent.py | 1813 | `test_rebuild_entity_from_knowledge_noop_on_empty_rows` | Ajay | (a) `caller_pid="Ajay"` |
| 12 | test_brain_agent.py | 1829 | rebuild new entity test | Ajay | (a) `caller_pid="Ajay"` |
| 13 | test_brain_agent.py | 1831 | rebuild old entity preserved | visitor | (a) `caller_pid="visitor"` |
| 14 | test_pipeline.py | 9122 | `ctx_before` deletion test | Alice | (a) `caller_pid="Alice"` |
| 15 | test_pipeline.py | 9129 | `ctx_after` deletion test | Alice | (a) `caller_pid="Alice"` |

**Universal disposition: (a) — pass `caller_pid=` matching the subject entity name for owner-override.**

Why (a) wins for ALL 15 sites:

- Each test's focus is storage/retrieval mechanics (invalidation filter, valid_until filter, rebuild behavior, NULL handling), NOT privacy semantics.
- Passing `caller_pid=subject` exercises the owner-override branch (`caller_pid == subject_pid` → all tiers visible), so the test's existing edge-data + assertion logic continues to work unchanged.
- Owner-override is the BROADEST visibility — guaranteed to not strip any test-fixture edges regardless of their privacy_level.
- Alternative (b) "seed edges with explicit `privacy_level='public'`" would require updating 15 fixture-setup sites + would mask the actual production caller pattern (which uses owner-override).
- Alternative (c) "test-only `_unsafe_no_filter=True` escape hatch" — rejected by auditor; ships test-only code path that has no production analog.

**Implementation: minimal change per test site.** Each call goes from `graph.get_graph_context("Jagan")` to `graph.get_graph_context("Jagan", caller_pid="Jagan")`. ~15 one-line edits.

**No new tests added under MEDIUM 1.** The existing tests are reconfigured to maintain their original semantic under the new signature. The privacy-filter behavior is verified by the NEW Phase 2 test 5 (slow behavioral, real Kuzu) per Plan v1 §7.

---

## 4. LOW 2 — Schema-concept clarifier (NEW)

Plan v1 §4.1 listed examples like `Jagan.discussed_topic='diabetes' privacy_level='household'` that mix three concepts: entity-name (the graph node — `'diabetes'`), attribute-name (the edge property — `'discussed_topic'`), and privacy-level (the edge property — `'household'`).

**Plan v2 adds an upfront schema-concept refresher** in `find_shared_entities` post-D-B docstring + in §4.1 prose:

> *"In the v3 RELATES_TO schema: each edge has three relevant properties — `attribute` (the predicate name, e.g., `'discussed_topic'`), `value` (the target entity's name, mirrored from the target node, e.g., `'diabetes'`), and `privacy_level` (the new v3 property, e.g., `'household'`). The same target entity (same `value`) can appear in multiple edges with different attribute names AND different privacy_levels. The cross-person filter operates on `edge.privacy_level`, not on `entity.name`."*

This prevents future code-archaeology readers from inferring entity-level filtering by accident.

**Worked example added to §4.1:**

A person's graph may contain three edges all pointing to entity `'diabetes'`:
- Edge A: `attribute='discussed_topic', value='diabetes', privacy_level='household'`
- Edge B: `attribute='has_condition', value='diabetes', privacy_level='personal'`
- Edge C: `attribute='knows_about', value='diabetes', privacy_level='public'`

Under D1's "public only" filter for cross-person traversal, only Edge C participates in `find_shared_entities`. Edges A and B are filtered at Cypher WHERE-clause time. Test 5 (slow behavioral) explicitly seeds this case to verify.

---

## 5. Three minor observations (Plan v1 §5 — unchanged from auditor verdict)

| Obs | Topic | Status |
|---|---|---|
| A | Tier-mislabel correction | ✓ Plan v1 §5.1 — `lives_in='Bangalore'` (personal) → `from_country='India'` (public) swapped wherever §8 illustrates legitimate public-tier matches |
| B | Rebuild duration observability | ✓ Plan v1 §5.2 — entity_count + edge_count counters with graceful degradation; auditor's lean toward edge_count primacy acknowledged |
| C | Scope-expansion hypothesis forward-tracking | ✓ Plan v1 §5.3 — evaluate at D-D + D-E closure gates |

Plan v2 makes no changes to the three observations. All addressed in Plan v1 §5.

---

## 6. Implementation phases (Plan v2 — revised counts for MEDIUM 1)

### Phase 1 — Schema + writers + rebuild observability (+3 tests, ~quarter-day)

Unchanged from Plan v1 §6 Phase 1. Tests 1, 2, 3.

**Suite checkpoint:** 2377 → 2380 (+3).

### Phase 2 — Reader filters + 15 test-site updates (+2 NEW tests, ~half-day)

Plan v2 deltas vs v1:
- `get_graph_context` signature gains `caller_pid` + `best_friend_id` kwargs (Plan v1 §3.3).
- `find_shared_entities` Cypher gains `r.privacy_level = 'public'` filter (Plan v1 §3.3 + Plan v2 §4 docstring).
- Production caller at `core/brain_agent.py:7943` updated to pass `caller_pid=requester_person_id, best_friend_id=best_friend_id`.
- **NEW per MEDIUM 1**: 15 test sites updated to pass `caller_pid=<subject>` (per §3.5 enumeration).
- Tests 4, 5 (Plan v1 §7).

**Suite checkpoint:** 2380 → 2382 (+2 net new tests). The 15 test-site edits are FIXES, not new tests — they maintain the existing semantic under the new signature. No count delta from them.

### Phase 3 — AST invariants (+3 tests, ~quarter-day)

Unchanged from Plan v1 §6 Phase 3. Tests 6, 7, 8.

**Suite checkpoint:** 2382 → 2385 (+3).

### Phase 4 — Deliberate-regression confirmations + closure (+0 tests, ~quarter-day)

5 deliberate-regression confirmations per Plan v1 §7 Phase 4. Closure narrative banks:

- 2 Plan v1 precision items resolution (D3 fail-closed + D1 mixed-tier semantic)
- 3 Plan v2 items resolution (MED 1 test-site disposition + LOW 1 defense-in-depth framing + LOW 2 schema-concept clarifier)
- 3 minor observations resolution from Plan v1 §5 (tier-mislabel + rebuild observability + scope-expansion hypothesis forward-tracking)
- 1 NEW informal observation: **Deferral-rationale-expires-when-downstream-ships** (1 instance, P0.S7.D-B)
- Defensive `if not _filtering:` skip preserved as known dead-code-when-flag-on for future cleanup PR

**Total effort: ~1 day. Net new tests: 8 logical. Suite delta: 2377 → 2385.**

---

## 7. Test specification (Plan v2 — unchanged from Plan v1 §7)

Tests 1-8 from Plan v1 §7 unchanged. AST-forward-property primary + 1 slow behavioral remains the discipline. See Plan v1 §7 for full enumeration.

**Plus 15 test-site updates per §3.5** (not new tests; reconfiguration of existing tests to maintain semantic under new signature).

---

## 8. Validation gate (Plan v2 — extended)

1. All 8 new tests green; full-suite green at 2385.
2. All 15 reconfigured existing test sites pass (subject-owner-override path exercised correctly).
3. 5/5 deliberate-regression confirmations pass (induction protocol).
4. Rebuild observability log line fires on next-boot schema upgrade.
5. 2 Plan v1 precision items + 3 Plan v2 items resolved.
6. Closure narrative banks new informal observation: **Deferral-rationale-expires-when-downstream-ships**.

---

## 9. Threats / risks (Plan v1 §9 — unchanged; Plan v2 adds 1 banked observation)

Plan v1 risks 1-6 preserved. Plan v2 addition:

7. **Phase 0 test-surface estimation discrepancy (banked, non-blocking)**: Phase 0 audit §2 estimated "conservatively 2-4 test files." Plan v1 grep found 21 sites; Plan v2 grep refined to 15 sites across 2 files. Both files matched the "2-4 test files" estimate (2 files), so the FILE estimate held. The SITE count was deferred to Plan v1 grep per Phase 0 framing, and Plan v1 surfaced it. Plan v2 added per-site disposition per MEDIUM 1. **Not a scope-expansion-via-Phase-0 instance** — Phase 0 honestly deferred the count, both Plan v1 and Plan v2 cycles closed the loop with grep-verified data. Banked as informational discrepancy.

---

## 10. Discipline-count predictions (Plan v1 §10 — unchanged; auditor strict-read holds)

- Spec-first review cycle: 11-for-11 → **12-for-12** on closure
- Sub-pattern A: stays at **4 instances**
- Tripwires-must-match-deferral-surface: stays **4-for-4**
- Developer-improves-on-spec: stays **6-for-6** unless code phase surfaces a mechanism improvement
- Induction-surfaces-invariant-gaps: stays **7-for-7**
- Canary-finding tracker: stays at **2 instances**
- Canary-gate override (informal): stays at **1 instance**
- Scope-expansion-via-Phase-0 (informal): stays at **1 instance**
- **Deferral-rationale-expires-when-downstream-ships** (informal): **1 instance** (P0.S7.D-B) → toward potential 5+ doctrine elevation

---

## 11. Closure-narrative banking (Phase 4 explicit)

Phase 4 closure report explicitly banks:

- **5/5 deliberate-regression confirmations** per Plan v1 §7 Phase 4
- **D3 framing** per §3.4: *"D3's `get_graph_context` filter is defense-in-depth — the existing `_filtering` skip was already preventing the cross-person leak via this path. D1's `find_shared_entities` filter is the load-bearing privacy fix; D3 raises the floor against future code-path additions."*
- **Schema-concept clarifier** per §4 added to `find_shared_entities` docstring post-D-B
- **15 test-site disposition** per §3.5 — all sites updated to disposition (a) `caller_pid=<subject>`
- **2 Plan v1 precision items + 3 Plan v2 items** resolution
- **3 minor observations** from Plan v1 §5 resolution
- **NEW informal observation**: Deferral-rationale-expires-when-downstream-ships (1 instance)
- **Defensive `_filtering` skip** preserved; future cleanup PR scheduled in CLAUDE.md "Pending Work"
- **Phase 0 test-surface estimation discrepancy** noted (informational, non-blocking)

---

## 12. References (Plan v1 §12 — unchanged)

- `tests/p0_s7_db_audit.md` — Phase 0 audit
- `tests/p0_s7_db_plan_v1.md` — Plan v1 (retained for delta visibility)
- `core/brain_agent.py:3505` — `_init_schema`
- `core/brain_agent.py:3531` — `_create_edge`
- `core/brain_agent.py:3556` — `store_fact`
- `core/brain_agent.py:3577` — `rebuild_entity_from_knowledge`
- `core/brain_agent.py:3611` — `get_graph_context` (Plan v2 §3 + §3.5 site)
- `core/brain_agent.py:3647` — `find_shared_entities` (Plan v2 §4 docstring update site)
- `core/brain_agent.py:6554-6570` — `_ensure_graph_sync` schema-upgrade path
- `core/brain_agent.py:7943` — single production caller
- `core/brain_agent.py:7941` — defensive `_filtering` skip (Plan v2 §3.4 framing site)
- `core/config.py:1242` — `GRAPH_SCHEMA_VERSION`
- `test_brain_agent.py` lines 1598/1604/1610/1630/1658/1672/1681/1741/1790/1806/1813/1829/1831 — 13 test-site updates per §3.5
- `test_pipeline.py` lines 9122/9129 — 2 test-site updates per §3.5
- Memory: `feedback_spec_time_grep_verification.md` — applied at Plan v2 drafting
- Memory: `feedback_ast_forward_property_tests.md` — test design discipline

---

## 13. Next steps

1. **Auditor reviews Plan v2.** Specifically: (a) §3.5 universal disposition (a) for all 15 sites OK? (b) §3.4 defense-in-depth vs load-bearing framing precise enough? (c) §4 schema-concept clarifier complete?
2. **Joint sign-off** on Plan v2 → user forwards to developer.
3. **Developer executes Phase 1-4** with full-suite verification between phases.
4. **Phase 4 closure report** per §11 banking checklist.
