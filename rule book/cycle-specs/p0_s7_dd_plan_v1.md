# P0.S7.D-D — RoomOrchestrator class extraction — Plan v1

**Date:** 2026-05-19
**Author:** architect
**Status:** Plan v1 — drafted against Phase 0 D-lock (2026-05-19, sub-pattern A 5th-instance elevation event) + auditor's 2 MEDIUM precision items + Q5 missed risks A & B from Phase 0 verdict. Standing by for auditor's Plan v1 review → Plan v2 (if precision items surface) → joint sign-off → developer handoff.

**Phase 0 audit:** `tests/p0_s7_dd_audit.md` (premise reset; sub-pattern A 5th instance; option α locked).

**Disciplines applied at Plan v1 drafting:**
- **Two-pass grep-verification (Pass 1)**: all file paths + line numbers + helper enumeration grep-verified 2026-05-19. Pass 2 fires at closure-narrative writing.
- **AST + behavioral workhorse pair**: §6 test design — AST primary for static class structure + 1-2 behavioral slow-marked tests for runtime semantics.

---

## 1. Locked decision reference (Phase 0 D-lock 2026-05-19)

| ID | Topic | Locked at |
|---|---|---|
| **Q1 verdict** | Sub-pattern A 5th instance | **ELEVATED to numbered doctrine** `### Phase-0-catches-wrong-premise` in CLAUDE.md on D-D closure. Auditor wording suggestion adopted. |
| **Q2 verdict** | Scope option (α) vs (β) | **LOCKED (α) consolidate** — thin RoomOrchestrator class composing over existing state stores |
| **Q3 verdict** | Inverse-direction scope correction | **Strict-read pushback ACCEPTED** — D-D banks under sub-pattern A only (surface-error is primary; estimate-error is downstream consequence). Scope-expansion-via-Phase-0 stays at 1 instance (D-C only). |
| **Q4 verdict** | Doctrine name | **ACCEPTED** `### Phase-0-catches-wrong-premise`. Auditor's drop-in wording adopted. |
| D1 | Class file location | `core/room_orchestrator.py` |
| D2 | `__init__` signature | Composes over `session_store, pipeline_state_store, face_db, brain_orchestrator, conversation_store, emotion_agents` — all already-existing class instances. Explicit dependency surface. |
| D3 | Method-vs-classmethod | All instance methods; `self` provides composed-dependency access |
| D4 | Helper name preservation | Drop `_` prefix on rename — methods become `compute_room_audience`, `build_room_block`, `on_room_end`, etc. (public API on the class) |
| D5 | Call-site update pattern | Module-level: `_room_orchestrator = RoomOrchestrator(...)`. Internal callers in pipeline.py update to `_room_orchestrator.<method>(...)`. **Module-level shim bindings preserved (see §3 below).** |
| D6 | Module-level function deprecation | **MEDIUM 1 disposition (see §3)**: Stage 1 keeps module-level helpers as SHIM BINDINGS to class methods (preserves 130 test sites without modification). Stage 2 (post-bundled-canary) hard-deletes shims + migrates tests. |
| D7 | Test surface (AST + behavioral pair) | Per refined discipline. AST: class structure, method signatures, shim-binding inverse-check. Behavioral: 1-2 slow-marked end-to-end tests. |
| D8 | `_build_cross_person_excerpts` D-C state preservation | Stays flag-gated (D-C Stage 1 semantic). MOVED into RoomOrchestrator as a method with the same flag gate. Stage 2 of D-C hard-deletes; same trigger as D-D Stage 2 (bundled-queue canary). |
| **MED 1** (auditor Q5 risk A) | Test surface migration cost | **130 sites enumerated (see §3)**. Plan v1 commits to two-stage: Stage 1 = shim-based (no test changes); Stage 2 = shim removal + test migration after bundled-queue canary. |
| **MED 2** (auditor Q5 risk B) | Order-of-instantiation + None handling | RoomOrchestrator instantiated AFTER all 6 dependencies; defensive None-handling in __init__ and methods. See §4. |

---

## 2. Architectural overview

Two-stage class extraction (mirrors P0.S7.D-C's Stage 1 → Stage 2 pattern):

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Stage 1 (this D-D) — class extraction + module-level shims                │
│                                                                            │
│  1. core/room_orchestrator.py::RoomOrchestrator class                     │
│     - 7 methods (one per moved helper)                                     │
│     - __init__ composes over 6 dependencies (existing class instances)    │
│  2. pipeline.py — _room_orchestrator instance + shim bindings             │
│     _build_room_block = _room_orchestrator.build_room_block               │
│     _on_room_end      = _room_orchestrator.on_room_end                    │
│     ... etc for all 7 helpers                                              │
│  3. pipeline.py internal callers — updated to use class instance          │
│     (where convenient; shim bindings preserve existing call patterns)     │
│                                                                            │
│  Stage 1 result: class exists + 130 test sites work unchanged via shims.  │
└──────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼ (bundled-queue canary)
┌──────────────────────────────────────────────────────────────────────────┐
│  Stage 2 (post-bundled-canary follow-up)                                   │
│                                                                            │
│  1. Delete module-level shim bindings from pipeline.py                    │
│  2. Migrate 130 test sites to `_room_orchestrator.<method>()` shape       │
│     OR introduce a test fixture `room_orchestrator` that tests use        │
│  3. Delete 7 original module-level helper function bodies (already        │
│     redirected to class methods; this just removes the legacy locations)  │
│                                                                            │
│  Stage 2 trigger: bundled-queue canary validates D-A + D-C + D-B + D-D +  │
│  D-E + γ AS A SET. On canary PASS, file Stage 2 follow-up.                │
│  Mirrors D-C Stage 2 trigger pattern.                                      │
└──────────────────────────────────────────────────────────────────────────┘
```

**Why two-stage:**
- Stage 1 delivers the named artifact (RoomOrchestrator class) that the user's strategic direction expected.
- Stage 1 preserves 130 test sites without modification — minimizes blast radius during the canary window.
- Stage 2 finishes the cleanup post-canary, when the bundled-queue work has been validated end-to-end.
- Same shape as D-C two-stage. Discipline-consistency across the queue.

---

## 3. MEDIUM 1 — Test surface migration enumeration + disposition

### 3.1 Grep-verified test site count (2026-05-19)

Auditor estimated 20-40 test sites. **Actual count: 130 sites across 7 test files.**

| File | Total sites | Per-helper breakdown |
|---|---|---|
| `test_pipeline.py` | **69** | `_build_room_block`: 27 / `_on_room_end`: 19 / `_build_cross_person_excerpts`: 18 / `_kairos_preferred_speaker`: 5 |
| `tests/test_p0_s7_phase3.py` | 19 | `_compute_room_audience`: 12 / `_build_shared_context_block`: 7 |
| `tests/test_p0_s7_1_observability.py` | 17 | `_build_shared_context_block`: 17 |
| `tests/test_p0_s7_phase2.py` | 13 | `_build_shared_context_block`: 13 |
| `tests/test_p0_s7_phase1.py` | 8 | `_compute_room_audience`: 8 |
| `tests/test_multispeaker_integration.py` | 3 | `_build_room_block`: 3 |
| `tests/test_layering_invariants.py` | 1 | `_build_room_block`: 1 |
| **Total** | **130** | |

`_fetch_recent_room_context` has 0 direct test references — tested indirectly via `<<<RECENT ROOMS>>>` block integration paths. Plan v1 still moves it into RoomOrchestrator for consistency.

### 3.2 Plan v1 disposition — Stage 1 shim bindings (NO test changes)

The 130-site cost forces a strategic choice:

**Option (i) — migrate all 130 sites in Stage 1.** Cost: 1-2 days of test-edit work alone, on top of class extraction. Big blast radius during canary window.

**Option (ii) — Stage 1 shim bindings; Stage 2 migrates tests post-canary.** Cost: ~half-day for class + shims; test migration deferred. Mirrors D-C Stage 1 → Stage 2 pattern.

**LOCKED: option (ii).** Stage 1 ships module-level shim bindings; 130 test sites work unchanged; Stage 2 migrates tests after bundled-queue canary validates.

### 3.3 Stage 1 shim binding pattern (locked)

```python
# pipeline.py (after D-D Stage 1)

# Instantiate the class at module scope (after dependencies are ready).
_room_orchestrator: "RoomOrchestrator | None" = None

def _init_room_orchestrator(...) -> None:
    """Called from run() after SessionStore + PipelineStateStore + FaceDB +
    BrainOrchestrator + ConversationStore + emotion_agents are all initialized.
    Order-of-instantiation guard per MED 2."""
    global _room_orchestrator
    _room_orchestrator = RoomOrchestrator(
        session_store=_session_store,
        pipeline_state_store=_pipeline_state_store,
        face_db=_face_db_ref,
        brain_orchestrator=_brain_orchestrator,
        conversation_store=_conversation_store,
        emotion_agents=_emotion_agents,
    )

# Shim bindings — module-level helper names continue to work.
# Direct attribute access: when tests call _build_room_block(...), Python
# looks up the module attribute, finds the bound method, and dispatches
# to the class instance's method.
#
# NOTE: shims are populated AFTER _init_room_orchestrator() fires. Pre-init
# callers will hit the None guard (see MED 2).
def _build_room_block(*args, **kwargs):
    if _room_orchestrator is None:
        raise RuntimeError("RoomOrchestrator not initialized — _init_room_orchestrator() must run first")
    return _room_orchestrator.build_room_block(*args, **kwargs)

def _on_room_end(*args, **kwargs):
    if _room_orchestrator is None:
        raise RuntimeError("RoomOrchestrator not initialized — _init_room_orchestrator() must run first")
    return _room_orchestrator.on_room_end(*args, **kwargs)

# ... etc for all 7 helpers
```

**Why function shims (not attribute bindings):**

The auditor flagged Q5 risk B (order-of-instantiation). If we use `_build_room_block = _room_orchestrator.build_room_block` as a binding at module-level, the binding evaluates AT IMPORT TIME — which is BEFORE `_init_room_orchestrator()` runs. The binding would resolve to `None.build_room_block` → AttributeError.

Function shims defer the lookup to CALL TIME, after init has fired. The None-check fails loudly if a caller hits the shim before init.

**Trade-off:** function shims add ~one indirection per call (negligible overhead, ns-scale). The shim layer is dead-code-after-Stage 2.

### 3.4 Stage 2 trigger + scope (banked)

**Trigger:** bundled-queue canary validates D-A + D-C + D-B + D-D + D-E + γ AS A SET. Same trigger as D-C Stage 2. On canary PASS, file Stage 2 follow-up.

**Stage 2 scope:**
- Delete 7 module-level shim functions from pipeline.py (~70-100 LOC).
- Delete 7 original module-level helper bodies (the actual function definitions that the class now duplicates). Wait — these are MOVED, not duplicated. Let me clarify.

**Clarification:** in Stage 1, the helper bodies LIVE in `core/room_orchestrator.py` as methods. The module-level shims in pipeline.py dispatch to the methods. So pipeline.py loses ~580 LOC (the original helper bodies) in Stage 1, gains ~70-100 LOC (the shim layer). Net pipeline.py reduction: ~480-510 LOC.

In Stage 2, the 70-100 LOC shim layer is deleted; 130 test sites are migrated to use `_room_orchestrator.<method>()` directly.

**Stage 2 closure narrative will bank**: D-C Stage 2 + D-D Stage 2 BOTH triggered by the same bundled-queue canary. May ship as one combined follow-up PR.

---

## 4. MEDIUM 2 — Order-of-instantiation + None handling (auditor Q5 risk B)

### 4.1 Startup sequence

Pipeline.py current boot order:

1. `FaceDB` instantiated (line ~6300)
2. `BrainOrchestrator` instantiated (line ~6450; composes FaceDB)
3. `SessionStore`, `PipelineStateStore`, `ConversationStore` instantiated (existing module-level state)
4. `_emotion_agents: dict[str, EmotionAgent]` initialized as empty dict
5. **NEW:** `_init_room_orchestrator()` called — composes all 5 dependencies into `_room_orchestrator`

### 4.2 Defensive guards

Three layers of None-handling:

1. **In `_init_room_orchestrator()`**: assert all 5 dependencies are non-None at call time. Fail loudly if any are missing.

2. **In every shim function in pipeline.py**: `if _room_orchestrator is None: raise RuntimeError(...)` — catches callers that hit the shim before init.

3. **In RoomOrchestrator methods**: defensive None-handling for `best_friend_id` (some methods need it; pre-enrollment state has it = None). Methods accept `best_friend_id: str | None = None` parameter and degrade gracefully (default to non-owner-tier behavior, matches `_visibility_clause` semantic).

### 4.3 Init regression guard test

Phase 3 AST test asserts:
- `_init_room_orchestrator()` is called from `run()` BEFORE any caller of a shim.
- The call order in `run()` is: SessionStore → PipelineStateStore → FaceDB → BrainOrchestrator → ConversationStore → emotion_agents → `_init_room_orchestrator()` → first shim caller.

Catches future refactors that move RoomOrchestrator init earlier (which would hit None dependencies) or later (which would hit None on shim calls).

---

## 5. Doctrine elevation — CLAUDE.md narrative banking

On D-D closure, CLAUDE.md gets the following changes:

### 5.1 Architectural Disciplines section addition

A new `### Phase-0-catches-wrong-premise` heading is added to the Architectural Disciplines section in CLAUDE.md, alongside existing disciplines (`### Spec-first review cycle`, `### Induction-surfaces-invariant-gaps`, etc.).

**Auditor's drop-in wording** (Phase 0 audit Q4 verdict):

```markdown
### Phase-0-catches-wrong-premise

Every behavior-change P0/P1 cycle has a Phase 0 audit. The audit's job is
grep-verified findings BEFORE any code phase. 5 of 13 spec-first cycles
(P0.10, P0.S1, P0.S6, P0.S7, P0.S7.D-D) had their pre-audit mental model
falsified by Phase 0 grep — the architect's natural framing pointed at
the WRONG surface, and grep-verified evidence found the gap elsewhere.
At 5 instances, this pattern is now elevated to numbered doctrine:
expect Phase 0 to catch wrong-premise framing as a routine artifact, not
as a one-off discovery. When drafting a P0/P1 spec, treat the pre-audit
mental model as a hypothesis the audit will test — not as the locked scope.

**Discipline-stability evidence**: the architect held the strict-read
line across cycles that could have loose-counted to inflate the threshold
prematurely (P0.S7.2, P0.S7.D-C, P0.S7.D-B all explicitly NOT bumped despite
having borderline-elevation findings). That discipline-stability gives the
5th-instance lock its integrity.

**Operational rules:**
1. Phase 0 grep is the FIRST artifact, not the last. Frame the audit's job
   as "test my pre-audit hypothesis against grep evidence."
2. When Phase 0 falsifies the pre-audit premise, surface the reset
   explicitly — don't quietly proceed with the corrected scope.
3. Banking the falsification is the discipline working, not failing.
```

### 5.2 Sub-pattern A memory-note line repurposed

The existing CLAUDE.md line 65 memory-note about sub-pattern A is REMOVED (or marked as historical/superseded). The numbered doctrine in §5.1 above replaces it.

### 5.3 Memory file disposition

The 5 instances banked at architect-memory level (`feedback_*.md` family) remain unchanged — they're the historical evidence for the doctrine's elevation.

---

## 6. Test specification (Plan v1 — AST + behavioral workhorse pair)

### Phase 1 tests (class structure)

1. **`test_room_orchestrator_class_exists`** (AST forward-property) — assert `RoomOrchestrator` class is defined at `core/room_orchestrator.py`. Has 7 expected methods: `compute_room_audience`, `kairos_preferred_speaker`, `build_cross_person_excerpts`, `build_shared_context_block`, `build_room_block`, `fetch_recent_room_context`, `on_room_end`.

2. **`test_room_orchestrator_init_signature_composes_dependencies`** (AST forward-property) — assert `RoomOrchestrator.__init__` accepts the 6 expected dependency parameters. Type hints reference the correct classes (SessionStore, PipelineStateStore, FaceDB, BrainOrchestrator, ConversationStore, dict for emotion_agents).

3. **`test_room_orchestrator_init_asserts_all_dependencies_non_none`** (behavioral) — instantiate `RoomOrchestrator(session_store=None, ...)` → raises AssertionError or TypeError. Defensive None-check in __init__ verified.

### Phase 2 tests (shims + production wiring)

4. **`test_module_level_shims_exist_for_all_7_helpers`** (AST forward-property) — assert each of the 7 helper names exists at module scope in pipeline.py AND each is a function that dispatches to a `_room_orchestrator.<method>()` call.

5. **`test_shim_raises_if_room_orchestrator_uninitialized`** (behavioral) — set `pipeline._room_orchestrator = None`; call any shim; assert RuntimeError raised. Defensive guard verified.

6. **`test_init_room_orchestrator_called_in_run_before_first_shim_caller`** (AST forward-property) — walk `run()` AST in pipeline.py; find first call to any shim; assert `_init_room_orchestrator()` is called at strictly lower line number.

7. **`test_room_orchestrator_build_room_block_end_to_end`** (behavioral slow-marked) — instantiate RoomOrchestrator with real SessionStore + PipelineStateStore + ConversationStore fixtures; seed 2 sessions; call `build_room_block(...)`; assert output matches legacy `_build_room_block(...)` output. End-to-end integration verifies the class extraction preserves behavior.

### Phase 3 tests (invariants)

8. **`test_no_room_helper_body_remains_at_module_level`** (AST forward-property, inverse-check) — for each of the 7 helper names, assert pipeline.py either has a SHIM (function with single line dispatching to `_room_orchestrator.<method>(...)`) OR does not contain the function definition at all. Catches incomplete migration (e.g., developer accidentally leaves the original body in place alongside the shim).

9. **`test_room_orchestrator_methods_signatures_match_legacy_helpers`** (AST forward-property) — for each method on RoomOrchestrator, assert signature parameters (excluding `self`) match the corresponding module-level helper's original signature. Catches accidental signature drift during extraction.

10. **`test_d_c_flag_gate_preserved_in_room_orchestrator_method`** (AST forward-property) — `RoomOrchestrator.build_cross_person_excerpts` body contains `if not CROSS_PERSON_EXCERPTS_ENABLED:` guard. D-C Stage 1 flag-gate preserved through the move.

### Phase 4 (deliberate-regression confirmations — closure items)

- Delete the `_init_room_orchestrator()` call from `run()` → tests 5 + 6 fail (shims raise RuntimeError) → revert.
- Drop `_compute_room_audience` shim binding from pipeline.py → tests 4 + 8 fail → revert.
- Move `compute_room_audience` method body OUT of `RoomOrchestrator` (leave only the shim) → test 1 fails → revert.
- Drop one of the 6 dependencies from `RoomOrchestrator.__init__` → test 2 fails → revert.
- Strip the `if not CROSS_PERSON_EXCERPTS_ENABLED:` guard from the moved `build_cross_person_excerpts` method → test 10 fails → revert.

**Net new tests: 10 logical (8 AST + 2 behavioral).** Suite delta forecast: 2385 → ~2395.

---

## 7. Implementation phases

### Phase 1 — Class extraction + shim layer (+3 tests, ~half-day)

- Create `core/room_orchestrator.py` with `RoomOrchestrator` class + `__init__` + 7 methods (one per moved helper).
- Move helper bodies from pipeline.py to RoomOrchestrator methods.
- Add module-level shim functions in pipeline.py (7 shims, ~10 LOC each).
- Add `_init_room_orchestrator()` function + call from `run()`.
- Wire dependencies (SessionStore, PipelineStateStore, FaceDB, BrainOrchestrator, ConversationStore, emotion_agents).
- Tests 1, 2, 3 from §6.
- **Suite checkpoint:** 2385 → 2388 (+3).

### Phase 2 — Production wiring + behavioral integration (+4 tests, ~quarter-day)

- Update pipeline.py internal callers (where convenient) to use `_room_orchestrator.<method>(...)` directly. Where call-site convenience prefers the shim (e.g., short signature), keep the shim call.
- Verify all 130 test sites continue to work unchanged via the shim layer.
- Tests 4, 5, 6, 7 from §6.
- **Suite checkpoint:** 2388 → 2392 (+4).

### Phase 3 — AST invariants (+3 tests, ~quarter-day)

- Tests 8, 9, 10 from §6.
- **Suite checkpoint:** 2392 → 2395 (+3).

### Phase 4 — Deliberate-regression confirmations + closure + doctrine elevation (+0 tests, ~quarter-day)

- 5 deliberate-regression confirmations per §6 Phase 4 list.
- **CLAUDE.md updates per §5**:
  - Add `### Phase-0-catches-wrong-premise` doctrine section using auditor's drop-in wording.
  - Repurpose/remove the existing sub-pattern A memory-note line.
- **Closure-narrative banking**:
  - Sub-pattern A doctrine elevation banking (5 instances → numbered doctrine)
  - 130-site test-migration cost banked as Stage 2 dependency
  - Stage 2 trigger (bundled-queue canary) documented in CLAUDE.md "Pending Work"
  - 7 module-level helper deprecation banked alongside D-C Stage 2 cleanup

**Total effort: ~1 to 1.5 days.** Slightly larger than D-C due to 7 helpers vs 1. Net new tests: 10 logical. Suite delta: 2385 → 2395.

---

## 8. Validation gate

1. All 10 new tests green; full-suite green at 2395.
2. 5/5 deliberate-regression confirmations pass.
3. 130 existing test sites pass unchanged via shim layer (no test-edit work in D-D).
4. CLAUDE.md doctrine elevation landed: `### Phase-0-catches-wrong-premise` section present with auditor's wording.
5. Sub-pattern A memory-note repurposed (no longer informal at line 65; replaced by doctrine).
6. Stage 2 trigger banked in CLAUDE.md "Pending Work" alongside D-C Stage 2.

---

## 9. Threats / risks (Plan v1 — extends Phase 0 §9)

Phase 0 §9 risks 1-4 preserved. Plan v1 additions:

5. **130-site test-migration cost**: deferred to Stage 2 per shim approach. Risk: Stage 2 follow-up gets deprioritized and shims accumulate as dead code. Mitigation: banked in CLAUDE.md "Pending Work" with explicit trigger (bundled-queue canary).

6. **Shim layer overhead**: one indirection per call (~ns). Negligible for non-hot-path callers. `_compute_room_audience` is per-log_turn (potentially hot — runs on every multi-person assistant turn). Plan v1 estimate: at most ~10 calls/second on heavy multi-person sessions; ~100ns × 10 = 1μs overhead/sec. Non-issue.

7. **Order-of-instantiation regression risk**: future refactor that moves `_init_room_orchestrator()` earlier in `run()` would hit None dependencies. Mitigation: Phase 3 test 6 (AST line-number ordering check). Defensive RuntimeError guards in shims catch the runtime failure mode if test 6 ever gets bypassed.

8. **D-C interaction**: `_build_cross_person_excerpts` moves into RoomOrchestrator with its D-C flag-gate preserved. Phase 3 test 10 verifies the guard survives the move. D-C Stage 2 (post-canary) hard-deletes the method; D-D Stage 2 hard-deletes the shim. Two cleanups, one canary trigger.

9. **CLAUDE.md doctrine elevation has irreversible component**: once sub-pattern A graduates to `### Phase-0-catches-wrong-premise`, future "loose-counting" of sub-pattern A would inflate the doctrine's 5+ threshold for a different elevation (e.g., 10+ → elevation tier 2?). Plan v1 doesn't address tier-2 elevation; banked as "if instances continue accumulating, address at 10+ threshold."

---

## 10. Discipline-count predictions on closure

| Discipline | Pre-D-D | On D-D closure |
|---|---|---|
| Spec-first review cycle | 12-for-12 | **13-for-13** ✓ |
| **Sub-pattern A (GRADUATING)** | 4 instances (memory-note) | **5 instances → ELEVATED to `### Phase-0-catches-wrong-premise` numbered doctrine in CLAUDE.md** ✓ |
| Tripwires-must-match-deferral-surface | 4-for-4 | stays **4-for-4** |
| Developer-improves-on-spec | 6-for-6 | stays **6-for-6** unless code phase surfaces mechanism improvement |
| Induction-surfaces-invariant-gaps | 7-for-7 | stays **7-for-7** unless Phase 4 surfaces a real gap |
| Canary-finding tracker | 2 instances | stays at **2 instances** |
| Canary-gate override (informal) | 1 instance | stays at **1 instance** |
| Scope-expansion-via-Phase-0 (informal) | 1 instance | stays at **1 instance** (D-D's estimate-error is downstream of surface-error per strict-read; banked under sub-pattern A only) |
| Deferral-rationale-expires-when-downstream-ships (informal) | 1 instance | stays at **1 instance** |

**Architect-memory disciplines:**
- Spec-time grep-verification (two-pass refinement): 4 instances; Pass 1 applied at Plan v1 drafting. Pass 2 fires at closure-narrative writing.
- AST-forward-property + behavioral pair: 2 instances; applied at §6 test design.

---

## 11. Open items + risks summary

1. **130-site test migration** deferred to Stage 2 per shim approach (§3.2).
2. **Stage 2 trigger** = bundled-queue canary. Same trigger as D-C Stage 2. Combined follow-up possible.
3. **Doctrine elevation** is irreversible (no rollback once `### Phase-0-catches-wrong-premise` lands in CLAUDE.md). Discipline-stability evidence supports the elevation.
4. **Shim layer adds ~ns indirection** per call. Negligible for current hot-path callers.
5. **`_build_cross_person_excerpts` flag-gate preservation** verified by Phase 3 test 10.

---

## 12. References

- `tests/p0_s7_dd_audit.md` — Phase 0 audit (premise reset; sub-pattern A 5th instance; option α locked)
- `tests/p0_s7_dc_audit.md` + closure — preceding sibling spec (two-stage pattern reference)
- `tests/p0_s7_db_audit.md` + closure — preceding sibling spec (refined disciplines applied here)
- `core/session_state.py:135` — `SessionStore` class (already done; P0.7)
- `core/pipeline_state_store.py:21` — `PipelineStateStore` class (already done; P0.6.6)
- `pipeline.py:504` — `_compute_room_audience` (D-D scope target)
- `pipeline.py:903` — `_kairos_preferred_speaker` (D-D scope target)
- `pipeline.py:1202` — `_build_cross_person_excerpts` (D-C flag-gated; D-D moves into class with guard preserved)
- `pipeline.py:1312` — `_build_shared_context_block` (D-D scope target)
- `pipeline.py:1457` — `_build_room_block` (D-D scope target)
- `pipeline.py:1660` — `_fetch_recent_room_context` (D-D scope target)
- `pipeline.py:2192` — `_on_room_end` (D-D scope target)
- `everything_about_system.md` §163.3 — historical deferral rationale (bi-weekly refresh update target)
- Memory: `feedback_spec_time_grep_verification.md` (two-pass refinement) — Pass 1 applied
- Memory: `feedback_ast_forward_property_tests.md` (AST + behavioral pair) — applied at §6

---

## 13. Next steps

1. **Auditor reviews Plan v1.** Specifically: (a) §3.2 Stage 1 shim disposition for 130 sites OK? (b) §3.3 function-shim shape (vs attribute-binding) correct? (c) §4 order-of-instantiation guard structure complete? (d) §5 CLAUDE.md doctrine elevation wording and placement OK? (e) §9 risks — anything missed?
2. **Plan v2** if precision items surface (architect expects 1-2 items given the 130-site disposition + doctrine-elevation scope).
3. **Joint sign-off** → developer handoff for 4-phase implementation.
4. **Phase 4 closure** banks doctrine elevation + Stage 2 trigger + 130-site test migration.
