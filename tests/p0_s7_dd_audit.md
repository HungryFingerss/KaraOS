# P0.S7.D-D — RoomOrchestrator class extraction — Phase 0 Audit

**Date:** 2026-05-19
**Author:** architect
**Status:** Phase 0 — grep-verified findings, zero production-code changes. **MAJOR PREMISE-RESET FINDING — auditor adjudication needed before D-decision lock.** Standing by for auditor review.

**Companion document trail (forthcoming):**
- `tests/p0_s7_dd_plan_v1.md` — after Phase 0 sign-off + D-decision lock
- `tests/p0_s7_dd_plan_v2.md` — after Plan v1 review

**Disciplines applied at audit drafting (refined per P0.S7.D-B closure 2026-05-19):**
- **Two-pass grep-verification (Pass 1)**: all function/line references grep-verified 2026-05-19 against current production code. Pass 2 will fire at closure-narrative writing.
- **AST + behavioral workhorse pair**: §6 test design (when scope locks) will prioritize AST primary for static class-structure invariants + behavioral slow-marked for runtime semantics.

---

## 1. PREMISE RESET — D-D's scoping assumption is FALSIFIED

### 1.1 The original D-D scope (P0.S7 Phase 0 audit + `everything_about_system.md` §163.3)

P0.S7's Phase 0 audit (`tests/p0_s7_audit.md`) framed D-D as:

> **D-D — Extract `RoomOrchestrator` class (50+ access sites)** — 5-7 days, large refactor; deliberately deferred as its own project per `everything_about_system.md` §163.3.

`everything_about_system.md` §163.3 (the deferral rationale):

> "Existing `_active_sessions` is also module-level; Phase 3B.1–3B.6 deliberately stayed with that pattern rather than introducing a `RoomOrchestrator` class (as the roadmap originally proposed). Rationale: the roadmap's class would have required refactoring every `_active_sessions[pid]` access site (there are 50+). That refactor is its own project and risks landing bugs during a canary phase. Room state lives alongside session state until the refactor is a separate feature."

**This framing was written BEFORE the P0.7 + P0.6.6 migrations completed.** The 50+ access-site refactor that §163.3 warned about — has already happened, under different names.

### 1.2 Grep-verified current state (2026-05-19)

**The session-state access surface that D-D's scope assumed:**

```
pipeline.py — _active_sessions[pid] pattern:    0 occurrences
pipeline.py — _active_sessions symbol total:    2 occurrences (both in comments/variable names, NOT live dict accesses)
```

**Where the state actually lives now:**

| State | Class | Defined at | Pipeline.py access surface |
|---|---|---|---|
| Per-session data (person_id, voice_state, etc.) | `SessionStore` | `core/session_state.py:135` | **148** `_session_store.<method>()` call sites |
| Room-level state (room_session_id, started_at, participants) | `PipelineStateStore` | `core/pipeline_state_store.py:21` | **15** `_pipeline_state_store.peek_active_room_*` call sites |

**D-D's stated 50+ access-site refactor was already done by P0.7 (typed session state) + P0.6.6 (PipelineStateStore extraction).** The work is complete; it just went by different class names.

### 1.3 Sub-pattern A — 5th instance (auditor adjudication needed)

The architect's pre-Phase-0 mental model: *"D-D is the 5-7 day RoomOrchestrator class extraction. It refactors 50+ `_active_sessions[pid]` access sites."*

Grep-verified reality: *"P0.7 + P0.6.6 already extracted the classes. 0 `_active_sessions[pid]` access sites remain. The class extraction work is DONE under different names."*

**This is sub-pattern A wrong-premise pattern.** Compare against the 4 prior instances:

| Instance | Wrong premise | Actual gap |
|---|---|---|
| P0.10 | Legacy router was buggy path | NEW reconciler had the bug |
| P0.S1 | recognition_update was dangerous | progressive_enroll was THE gap |
| P0.S6 | Log-leak surface needed protection | Orphans + structural-invariant absence |
| P0.S7 | Phase 3B is one spec | 5-deferral decomposition |
| **P0.S7.D-D** (candidate) | **50+ `_active_sessions[pid]` access sites need refactoring** | **Already done in P0.7 under SessionStore name; D-D's actual remaining scope is much smaller** |

**Architect's lean: this IS sub-pattern A 5th instance.** The pattern matches exactly — natural framing pointed at the WRONG surface (assumed state still in module-level dict; actually in two classes already), grep-verified audit found the gap is elsewhere.

**Auditor adjudication needed**: if locked as 5th instance, **sub-pattern A crosses the 5+ elevation threshold** and graduates from informal-memory-note to a numbered `###` doctrine in CLAUDE.md Architectural Disciplines section.

---

## 2. What D-D actually IS now (grep-verified scope)

The session/room STATE is already in classes. What remains module-level: **7 room-related helper functions** in pipeline.py.

### 2.1 Module-level room-helper inventory

| Function | Line | Purpose | Composition |
|---|---|---|---|
| `_compute_room_audience` | 504 | Computes audience_ids for log_turn (P0.S7.2 κ) | Reads `PipelineStateStore.peek_active_room_participants()` |
| `_kairos_preferred_speaker` | 903 | Room-aware KAIROS speaker selection (S112 Part 2) | Reads `_session_store.peek_all_snapshots()` |
| `_build_cross_person_excerpts` | 1202 | Legacy multi-person block (D-C flag-gated, will be hard-deleted Stage 2) | Reads `_session_store` + `_conversation_store` |
| `_build_shared_context_block` | 1312 | `<<<SHARED CONTEXT>>>` block (P0.S7 D-A) | Reads `FaceDB.get_recent_room_conversation` + `_pipeline_state_store` |
| `_build_room_block` | 1457 | `<<<ROOM>>>` block (S113 P3B.1) | Reads `_session_store` + `_conversation_store` + `_emotion_agents` |
| `_fetch_recent_room_context` | 1660 | `<<<RECENT ROOMS>>>` block reader (S117) | Reads `BrainOrchestrator.brain_db.get_recent_room_context` |
| `_on_room_end` | 2192 | Last-person-leaves room hook (S112) | Reads `PipelineStateStore` + fires `synthesize_room` |

**7 helpers. ~580 LOC combined across the function bodies.** Plus the existing class-based state machinery (SessionStore + PipelineStateStore) that they compose over.

### 2.2 What "RoomOrchestrator class extraction" means under the revised scope

A `RoomOrchestrator` class would:
- Compose over `SessionStore` + `PipelineStateStore` + `FaceDB` + `BrainOrchestrator` (already-existing class instances)
- Own the 7 module-level room-helper functions as methods
- Provide a single composition point for "room-domain logic" (currently scattered across module scope)
- NOT change any state ownership — SessionStore and PipelineStateStore stay as they are; RoomOrchestrator is a thin composition layer

**This is fundamentally a "consolidate helpers into a class" refactor — not a "refactor 50+ access sites" refactor.** Much smaller scope than the P0.S7 Phase 0 audit estimated.

---

## 3. Two scope options for auditor adjudication

### 3.1 Option (α) — Consolidate helpers into thin RoomOrchestrator class

Scope:
- Create `core/room_orchestrator.py::RoomOrchestrator` class
- Move 7 module-level helpers into the class as methods
- Class composes over SessionStore + PipelineStateStore + FaceDB + BrainOrchestrator (passed at `__init__`)
- Module-level callers in pipeline.py + brain.py update to `_room_orchestrator.<method>(...)`
- ~7 module-level function-to-method conversions
- ~20 call-site updates (each helper has 1-3 call sites)
- No state-ownership changes; no signature changes beyond `self`

**Estimated effort: ~half-day to 1 day** (not 5-7 days). Mirrors D-C's "flag-gate + cleanup" scope size.

**Architectural value:**
- Cleaner module-level surface in pipeline.py (~580 LOC moved out → ~580 LOC in dedicated room_orchestrator.py)
- Single composition point for room-domain logic
- Future room-domain features land in `RoomOrchestrator` naturally rather than as more module-level helpers
- Tests become composable around a RoomOrchestrator fixture

**Tests:**
- AST forward-property: RoomOrchestrator class has expected method signatures + composition pattern
- Behavioral slow-marked: integration test exercises the class end-to-end through one of the helpers (e.g., `_build_room_block`)
- Inverse-check AST: every existing call site of the moved helpers is updated to the class-method shape
- Estimated ~6-8 tests, suite 2385 → ~2391-2393

### 3.2 Option (β) — Defer D-D entirely

Scope: **No code change.** Recognize that the 5-7 day refactor §163.3 warned about ALREADY HAPPENED under P0.7 + P0.6.6. Mark D-D as completed-under-different-names. Free up the 5-7 day budget.

**Architectural value:**
- Honest disclosure: the work was done; the deferral was overtaken by adjacent migrations
- Pipeline.py keeps its current shape with 7 module-level helpers
- D-E (multi-speaker conversation_turn redesign) starts sooner
- Bundled-queue canary fires sooner

**Closure narrative would bank:**
- §163.3's deferral rationale, marking it as "the access-site refactor it warned about happened under SessionStore / PipelineStateStore migrations (P0.7 / P0.6.6); D-D is no longer a load-bearing item."
- Update CLAUDE.md "Pending Work" / `everything_about_system.md` reference to reflect the corrected state.

### 3.3 Architect's lean

**(α) consolidate helpers into thin RoomOrchestrator class — RECOMMENDED.**

Reasons:
1. The 7 module-level helpers are a real code-organization smell. Consolidating them into a class produces cleaner code at a reasonable cost (~half-day).
2. Future room-domain features (Phase 3B+ work, post-bundled-canary) land in RoomOrchestrator naturally.
3. Tests become easier to write — fixture creates one RoomOrchestrator instance instead of monkeypatching ~7 module-level functions.
4. Honors the user's strategic direction (move through D-D before bundled canary).

**(β) defer entirely** is also defensible — the §163.3-warned refactor IS done. But (α) has positive value beyond just "marking complete." User's call.

---

## 4. Pre-decision flags

### 4.1 Sub-pattern A 5th instance — elevation trigger

If auditor adjudicates this as sub-pattern A 5th instance:
- Sub-pattern A discipline graduates from informal-memory-note to `### Phase-0-catches-wrong-premise` numbered doctrine in CLAUDE.md Architectural Disciplines section.
- The pattern at 5 instances is well-established enough that future architect specs should expect Phase 0 to catch wrong-premise framing as a routine artifact, not as a one-off discovery.

If auditor adjudicates this as NOT sub-pattern A (e.g., "the wrong premise was the AUDIT'S, not the architect's pre-audit mental model"), it stays at 4 instances. Architect's strict-read lean is "this IS 5th instance" — the wrong premise was in the prior P0.S7 Phase 0 audit's framing of D-D, which is the architect's own work-product.

### 4.2 Scope-expansion-via-Phase-0 — INVERSE pattern

P0.S7.D-C surfaced "scope-expansion-via-Phase-0" (~3× larger than assumed). D-D is the INVERSE: ~10× SMALLER than assumed (estimated 5-7 days; actual ~half-day under option α).

This isn't a separate observation — it's the same "Phase 0 grep is more accurate than pre-audit estimate" pattern, just in the opposite direction. **Banking the inverse-direction sibling of scope-expansion-via-Phase-0 is worth surfacing.** If recurs 5+ times in either direction (over-estimate OR under-estimate), may warrant a `### Phase-0-corrects-pre-audit-estimates` umbrella doctrine.

### 4.3 Two-pass grep-verification (refined discipline) at audit drafting

Pass 1 applied. All 7 function line numbers + 2 class definitions grep-verified 2026-05-19. Pass 2 will fire at closure-narrative writing per refined discipline (line numbers may shift during option (α) implementation if chosen).

---

## 5. D-decisions surfaced (conditional on auditor's scope verdict)

**If auditor approves option (α):**

| ID | Topic | Architect's lean |
|---|---|---|
| D1 | Class file location | `core/room_orchestrator.py` (mirrors `core/session_state.py` + `core/pipeline_state_store.py` precedent) |
| D2 | `__init__` signature | Accept `session_store, pipeline_state_store, face_db, brain_orchestrator, conversation_store, emotion_agents` — all already-existing class instances. Document explicit dependency surface. |
| D3 | Method-vs-classmethod | All instance methods; `self` provides access to composed dependencies |
| D4 | Helper name preservation | Drop `_` prefix on rename — methods become `compute_room_audience`, `build_room_block`, etc. (public API on the class) |
| D5 | Call-site update pattern | Module-level: `_room_orchestrator = RoomOrchestrator(...)`. Call sites: `_room_orchestrator.build_room_block(...)`. Mirrors `_session_store` / `_pipeline_state_store` patterns. |
| D6 | Module-level function deprecation | The 7 module-level functions DELETED in their old location (no shim/alias). All callers updated to class-method shape. |
| D7 | Test surface — AST + behavioral pair | Per refined `AST-forward-property-tests-are-the-workhorse` discipline. AST: class structure, method signatures, inverse-check (no module-level helper of the same name remains). Behavioral: integration test exercises class end-to-end. |
| D8 | `_build_cross_person_excerpts` disposition under D-D | Stays flag-gated (D-C Stage 1 state). MOVED into RoomOrchestrator as a method (preserves Stage 1 semantics; Stage 2 hard-delete still post-bundled-canary). |

**If auditor approves option (β):**

| ID | Topic | Architect's lean |
|---|---|---|
| D1' | Closure-narrative banking | Document explicitly: "§163.3's deferral rationale is overtaken by P0.7 + P0.6.6 migrations. The 50+ access-site refactor it warned about happened under SessionStore / PipelineStateStore names. D-D is no longer a load-bearing item." |
| D2' | CLAUDE.md "Pending Work" update | Remove D-D entry; replace with "D-D: completed-under-different-names; no code change needed" |
| D3' | `everything_about_system.md` update | Bi-weekly cadence — refine §163.3 in next consolidated refresh |

---

## 6. Test specification preview (if option α chosen)

Will apply refined `AST + behavioral workhorse pair` discipline per architect-memory.

### Phase 1 tests (class structure)

1. **AST forward-property**: `RoomOrchestrator` class exists at `core/room_orchestrator.py`; has 7 expected methods (or however many move under D-D scope).
2. **AST forward-property**: `__init__` signature accepts the expected dependency parameters.
3. **AST inverse-check**: no module-level helper with the original `_build_room_block` / `_on_room_end` / etc. names remains in `pipeline.py` (catch incomplete migration).

### Phase 2 tests (call sites + behavioral)

4. **AST forward-property**: every call site of the migrated helpers uses `_room_orchestrator.<method>(...)` shape, not the old `_build_room_block(...)` shape.
5. **Behavioral slow-marked**: integration test exercises `RoomOrchestrator.build_room_block` end-to-end with a 2-session fixture; asserts the rendered block matches the legacy `_build_room_block` output for the same input.

### Phase 3 tests (extra invariants)

6. **AST forward-property**: tests that previously imported module-level helpers from `pipeline` are updated to use the class (or skipped under explicit flag if test code organization prefers to mock the class as a whole).
7. **AST forward-property**: `_build_cross_person_excerpts` remains flag-gated under D-C semantics even after moving into RoomOrchestrator (Stage 2 hard-delete still post-canary).

### Phase 4 (deliberate-regression confirmations)

5 confirmations to be enumerated in Plan v1 once scope locks.

---

## 7. Effort estimate

**Option (α):** ~half-day to 1 day. 7 function-to-method moves + ~20 call-site updates + ~6-8 tests. Smaller than P0.S7.D-C (which was ~half-day flag-gate + tests).

**Option (β):** ~quarter-day. Documentation-only update to CLAUDE.md + bi-weekly refresh of `everything_about_system.md` §163.3. No code change.

Either option, the original P0.S7 estimate of 5-7 days is **invalidated** by the premise reset.

---

## 8. Discipline-count predictions (depends on auditor's verdict)

### 8.1 If auditor adjudicates sub-pattern A 5th instance + option (α) ships

- Spec-first review cycle: 12-for-12 → **13-for-13** on closure
- **Sub-pattern A: 4 → 5 instances → GRADUATES to `### Phase-0-catches-wrong-premise` doctrine in CLAUDE.md** (threshold-crossing event)
- Tripwires-must-match-deferral-surface: stays **4-for-4**
- Developer-improves-on-spec: stays **6-for-6** unless code phase surfaces mechanism improvement
- Induction-surfaces-invariant-gaps: stays **7-for-7** unless Phase 4 surfaces a real gap
- Canary-finding tracker: stays at **2 instances**
- Canary-gate override (informal): stays at **1 instance**
- Scope-expansion-via-Phase-0 (informal): stays at **1 instance** (D-D is INVERSE-direction; same pattern but documented separately for now, see §4.2)
- Deferral-rationale-expires-when-downstream-ships (informal): stays at **1 instance**
- **NEW informal observation candidate**: `Phase-0-corrects-pre-audit-estimates` (over-estimate direction) — 1 instance (P0.S7.D-D under option α). If recurs 5+ times either direction, may surface as umbrella doctrine.

### 8.2 If auditor adjudicates NOT sub-pattern A (loose-read)

- Sub-pattern A: stays at **4 instances**
- No doctrine-elevation event this cycle
- Other counts unchanged from §8.1 above

### 8.3 If auditor approves option (β) defer

- Spec-first review cycle: stays **12-for-12** (D-D closes as no-code; no spec-first cycle counted)
- Other counts same as §8.1 / §8.2 depending on sub-pattern A adjudication

---

## 9. Threats / risks

1. **Sub-pattern A elevation threshold-crossing event (potential)**: if auditor locks 5th instance, sub-pattern A graduates to numbered doctrine. Worth surfacing explicitly so the elevation is deliberate, not implicit.

2. **D-D's "RoomOrchestrator" name conflicts with user's mental model**: the user has been told D-D is "RoomOrchestrator class extraction." Option (β) defer would land as "D-D was already done under different names." Worth verifying with user that defer-with-banking is acceptable vs (α) which delivers the named class.

3. **Option (α) creates a thin composition layer with no state-ownership change**: pure code organization win, not a load-bearing privacy/correctness fix. Lower-stakes than D-A / D-C / D-B. The cost-benefit is "cleaner pipeline.py module surface" — real value, but smaller than the user may expect from "5-7 day refactor."

4. **The 7 module-level helpers have shared assumptions about module-level state**: they reach into `_session_store`, `_pipeline_state_store`, `_conversation_store._history`, etc. Class extraction needs to thread these as constructor dependencies, not module-globals. Plan v1 grep-verifies the dependency surface.

---

## 10. Auditor verdict requested

1. **§1.3 sub-pattern A 5th instance adjudication** — accept as 5th instance (graduates discipline to numbered doctrine) OR reject as "not strict-read sub-pattern A" (stays at 4)?
2. **§3 scope option** — (α) consolidate helpers into thin RoomOrchestrator class, OR (β) defer entirely with banking?
3. **§4.2 "inverse direction" scope-expansion** — bank as same observation, or carve as separate `Phase-0-under-estimates` observation? Architect's lean: same pattern, both directions; bank as `Phase-0-corrects-pre-audit-estimates` umbrella.
4. **§4.1 sub-pattern A doctrine name** — if 5th instance locks: propose name `### Phase-0-catches-wrong-premise` for the new CLAUDE.md doctrine. Acceptable, or revise?
5. **§9 risks** — anything missed?

---

## 11. Next steps

1. **Auditor reviews this Phase 0 audit.** Specifically: sub-pattern A 5th-instance adjudication + scope option (α vs β) + doctrine name if elevation triggers.
2. **D-decisions locked** at Phase 0 sign-off (different D-decision sets for α vs β paths).
3. **Plan v1** drafted with locked D-decisions. Plan v1 grep-verifies the 7-helper dependency surface for option (α).
4. **Plan v2** if precision items surface.
5. **Joint sign-off** → developer handoff for 4-phase implementation (option α) OR documentation-only close (option β).

---

## 12. Reference documents

- `tests/p0_s7_audit.md` — P0.S7 Phase 0 audit (original D-D scope reference)
- `tests/p0_s7_dc_audit.md` + closure — preceding sibling spec
- `tests/p0_s7_db_audit.md` + closure — preceding sibling spec (banked refined disciplines)
- `core/session_state.py:135` — `SessionStore` class (already done; P0.7)
- `core/pipeline_state_store.py:21` — `PipelineStateStore` class (already done; P0.6.6)
- `pipeline.py:504` — `_compute_room_audience` (D-D scope target)
- `pipeline.py:903` — `_kairos_preferred_speaker` (D-D scope target)
- `pipeline.py:1202` — `_build_cross_person_excerpts` (D-C flag-gated; D-D scope target with Stage 1 preservation)
- `pipeline.py:1312` — `_build_shared_context_block` (D-D scope target)
- `pipeline.py:1457` — `_build_room_block` (D-D scope target)
- `pipeline.py:1660` — `_fetch_recent_room_context` (D-D scope target)
- `pipeline.py:2192` — `_on_room_end` (D-D scope target)
- `everything_about_system.md` §163.3 — historical deferral rationale (now overtaken; bi-weekly refresh update target)
- Memory: `feedback_spec_time_grep_verification.md` (two-pass refinement) — Pass 1 applied at this audit
- Memory: `feedback_ast_forward_property_tests.md` (AST + behavioral pair) — applied at §6 test design preview

---

**Standing by for auditor verdict on §1.3 + §3 + §4 before drafting Plan v1.**
