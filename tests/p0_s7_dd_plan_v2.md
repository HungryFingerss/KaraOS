# P0.S7.D-D — RoomOrchestrator class extraction — Plan v2

**Date:** 2026-05-19
**Author:** architect
**Status:** Plan v2 — drafted against locked Phase 0 verdicts + Plan v1 L1-L3 + auditor's 3 precision items from Plan v1 review (1 MEDIUM + 2 LOW). Plan v1 retained at `tests/p0_s7_dd_plan_v1.md` for delta visibility. Standing by for auditor's Plan v2 verdict → joint sign-off → developer handoff.

**Phase 0 audit:** `tests/p0_s7_dd_audit.md` (premise reset; sub-pattern A 5th instance).
**Plan v1:** `tests/p0_s7_dd_plan_v1.md`.

**Disciplines applied at Plan v2 drafting:**
- **Two-pass grep-verification (Pass 1)**: autouse-fixture path + line numbers grep-verified 2026-05-19 (`conftest.py:34-83`). Pass 2 fires at closure.
- **AST + behavioral workhorse pair**: §6 test design preserved from Plan v1.

**Delta from Plan v1 (3 items):**
- **MEDIUM 1** — Test-init pattern for shim layer LOCKED at option (a): extend autouse fixture in `conftest.py` to re-init `_room_orchestrator` after stores reset. Verified viable via grep of existing fixture (lines 34-83 already pattern-match for store reset). §3.5 below.
- **LOW 1** — Doctrine-text-as-verbatim-quote banking. §5.4 below.
- **LOW 2** — Future sub-pattern A accumulation pattern explicit statement. §5.1 below.

Locked D-decisions + Plan v1 contract clauses unchanged except where explicit revision noted below.

---

## 1. Locked decision reference (Plan v1 unchanged unless noted)

| ID | Topic | Plan v2 delta |
|---|---|---|
| Q1-Q4 verdicts | All Phase 0 verdicts preserved | — |
| D1-D8 | All Plan v1 D-decisions preserved | — |
| **MED 1 (Plan v1)** | Test surface migration cost | §3.5 below — **option (a) autouse-fixture extension LOCKED** |
| **MED 2 (Plan v1)** | Order-of-instantiation + None handling | **REFINED in §4** — __init__ stores deps without asserting; per-method None checks; production assert in `_init_room_orchestrator()` only |
| **MED 1 (Plan v2)** | Test-init pattern for shim layer | §3.5 — autouse fixture re-inits `_room_orchestrator`; production __init__ relaxed |
| **LOW 1 (Plan v2)** | Doctrine-text-as-verbatim-quote banking | §5.4 |
| **LOW 2 (Plan v2)** | Future sub-pattern A accumulation pattern | §5.1 — one-sentence addition |

---

## 2. Architectural overview (Plan v1 §2 unchanged)

Two-stage class extraction. Stage 1 (this D-D) = class + shim layer; Stage 2 (post-bundled-canary) = shim removal + test migration. See Plan v1 §2 for diagram.

---

## 3. MEDIUM 1 (Plan v2) — Autouse-fixture extension (the 130-site reconciliation)

### 3.1 Grep-verified autouse-fixture viability (2026-05-19)

`conftest.py:34-83` already runs an autouse fixture that:
- Replaces `_session_store` with a fresh `SessionStore()` instance (line 64-65)
- Resets all P0.6 stores via `.reset()` (lines 60-69)
- Replaces `_pipeline_state_store` with a fresh production-shape instance (lines 74-80)
- Wraps everything in a try/except (lines 60, 81-82)

**Adding `_room_orchestrator` re-init slots into the existing pattern.** No architectural change needed; mechanical extension of the existing reset loop.

### 3.2 Why option (a) wins over (b) lazy / (c) explicit fixture

The 3 options from auditor's MED 1:

| Option | Cost | Behavior |
|---|---|---|
| (a) Extend autouse fixture | ~10 LOC in conftest.py | 130 test sites work unchanged; production behavior unaffected |
| (b) Lazy init in shims | ~5 LOC in pipeline.py per shim | Tests work unchanged; production gains an "initialized-on-first-call" branch |
| (c) Explicit `room_orchestrator` test fixture | New fixture + 130 test-site references to add fixture as parameter | 130 test sites edited (defeats the "no test changes" promise) |

**(a) wins because:**
- Lowest cost (~10 LOC in one file)
- Mirrors existing P0.6 store-reset pattern → discipline-consistency
- Production behavior strictly unchanged (no lazy-init branch to test/maintain)
- 130 sites continue working without modification

### 3.3 Plan v2 lock — autouse fixture extension code (locked)

`conftest.py:34-83` `_reset_pipeline_state_between_tests` fixture gains a new block AFTER the existing `_pipeline_state_store` reset:

```python
# P0.S7.D-D — re-init RoomOrchestrator with fresh stores. The class composes
# over the 6 dependencies; some (face_db, brain_orchestrator) may be None in
# test contexts that don't touch those subsystems. The class __init__ stores
# all deps without asserting; per-method None checks handle the gaps.
try:
    if hasattr(_pipeline, "RoomOrchestrator"):
        _pipeline._room_orchestrator = _pipeline.RoomOrchestrator(
            session_store=_pipeline._session_store,
            pipeline_state_store=_pipeline._pipeline_state_store,
            face_db=getattr(_pipeline, "_face_db_ref", None),
            brain_orchestrator=getattr(_pipeline, "_brain_orchestrator", None),
            conversation_store=_pipeline._conversation_store,
            emotion_agents=getattr(_pipeline, "_emotion_agents", {}),
        )
except Exception as _e:
    print(f"[conftest] _room_orchestrator init failed: {_e!r}")
```

Critical design: `getattr(_pipeline, "_face_db_ref", None)` and `getattr(_pipeline, "_brain_orchestrator", None)` PROVIDE None when those module-level attrs are absent (test contexts). RoomOrchestrator `__init__` accepts None for these per MED 2 refined (§4 below).

### 3.4 Dry-run verification gate (auditor MED 1 explicit ask)

Auditor's MED 1: *"Plan v2 must specify which option AND verify (preferably via dry-run on a single test file before full Phase 1) that the chosen pattern handles the 130 sites."*

**Plan v2 commits to dry-run at Phase 1 first-implementation step:**

1. Land RoomOrchestrator class + 7 methods + shim layer in pipeline.py.
2. Extend autouse fixture per §3.3.
3. **Dry-run gate**: run a single test file that exercises ALL 7 helpers (recommended: `tests/test_p0_s7_phase2.py` — uses `_build_shared_context_block` heavily, and that block reaches into multiple deps). Expected: green.
4. **If dry-run green**: proceed with full Phase 1+2+3 work.
5. **If dry-run red**: surface as Phase 1 in-flight calibration item; investigate which dep was needed at test time and adjust the fixture's None-providence or relax the class's __init__ further.

Dry-run is ~5 minutes at the start of Phase 1. Catches misalignment between the fixture and the 130-site assumption before full Phase 1 work commits.

### 3.5 130-site enumeration unchanged from Plan v1 §3.1

130 sites across 7 files. Per-file + per-helper breakdown preserved from Plan v1.

---

## 4. MEDIUM 2 (Plan v1) — REFINED: __init__ relaxes; production init asserts

### 4.1 The refinement

Plan v1 §4.2 said:
> *"In `_init_room_orchestrator()`: assert all 5 dependencies are non-None at call time. Fail loudly if any are missing."*

This needs Plan v2 refinement to handle MED 1 (autouse fixture) correctly.

**Refined disposition:**

- **`RoomOrchestrator.__init__`** — STORES all 6 dependency parameters as instance attributes. **Does NOT assert non-None.** Tolerates missing deps at construction time (test contexts where face_db/brain_orchestrator may be None).
- **`_init_room_orchestrator()` (in pipeline.py)** — **ASSERTS all 6 dependencies non-None** at production boot. Fails loudly if any are missing (catches production startup-order regressions).
- **RoomOrchestrator methods** — defensive per-method None-checks for deps they need. Methods that need face_db check `self._face_db is None`; methods that need brain_orchestrator do likewise. Methods that need only session/pipeline/conversation stores (which the autouse fixture ALWAYS provides) don't need None checks.

### 4.2 The 3-layer defense (refined)

| Layer | Where | Purpose |
|---|---|---|
| 1 | `_init_room_orchestrator()` production boot | Asserts all 6 deps non-None; production never proceeds with missing deps |
| 2 | Shim function in pipeline.py | `if _room_orchestrator is None: raise RuntimeError(...)` — catches callers that hit shim before init |
| 3 | RoomOrchestrator method body | Per-method `if self._face_db is None: raise ValueError(...)` for methods that need that specific dep |

**Layer 1 fires in production.** Layer 2 fires in production AND tests (autouse fixture init happens before any test runs). Layer 3 fires only when a method needs a None dep — production code never hits this because Layer 1 prevents it; test code hits this only if a test happens to call a method whose specific dep is None for that test's fixture state.

### 4.3 Per-helper dep audit (which methods need which deps)

To make Layer 3 precise, here's the dep-usage map (grep-verified at Plan v2 drafting):

| Helper | Uses session_store | pipeline_state_store | face_db | brain_orchestrator | conversation_store | emotion_agents |
|---|---|---|---|---|---|---|
| `_compute_room_audience` | ✓ via participants arg | ✓ via participants arg | — | — | — | — |
| `_kairos_preferred_speaker` | ✓ | — | — | — | — | — |
| `_build_cross_person_excerpts` | ✓ (via active_sessions arg) | — | — | — | ✓ (via conversation arg) | — |
| `_build_shared_context_block` | — (via active_session_count arg) | — | ✓ for `get_recent_room_conversation` | — | — | — |
| `_build_room_block` | ✓ (via active_sessions arg) | — | — | — | ✓ (via conversation arg) | ✓ |
| `_fetch_recent_room_context` | — | — | — | ✓ for `brain_db.get_recent_room_context` | — | — |
| `_on_room_end` | — | ✓ via peek_all | — | ✓ for `synthesize_room` dispatch | — | — |

**Methods that need face_db**: `build_shared_context_block` only.
**Methods that need brain_orchestrator**: `fetch_recent_room_context`, `on_room_end` (for `synthesize_room` dispatch).
**All other methods**: use session_store + pipeline_state_store + conversation_store + emotion_agents which the autouse fixture always provides.

Layer 3 None-checks therefore land on 3 specific methods, not all 7.

---

## 5. CLAUDE.md doctrine elevation (Plan v1 §5 + 2 LOW additions)

### 5.1 New numbered doctrine `### Phase-0-catches-wrong-premise` (Plan v1 §5.1 + LOW 2 addition)

The auditor's drop-in wording is adopted verbatim. **LOW 2 addition** — one-sentence statement about future sub-pattern A accumulation:

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

**Future instances** (Plan v2 LOW 2 addition): future sub-pattern A
instances continue to be banked under this doctrine's track record. The
doctrine's instance enumeration in CLAUDE.md grows as new examples
accumulate; no new memory-note creation needed. If discipline-stability
remains intact, the doctrine matures rather than requiring re-elevation
at higher thresholds (10+, 20+, etc.).
```

### 5.2 Sub-pattern A memory-note disposition (Plan v1 §5.2 unchanged)

The existing CLAUDE.md line 65 memory-note about sub-pattern A is REMOVED (or marked as historical/superseded). The numbered doctrine in §5.1 above replaces it.

### 5.3 Memory file disposition (Plan v1 §5.3 unchanged)

The 5 instances banked at architect-memory level (`feedback_*.md` family) remain unchanged — they're the historical evidence for the doctrine's elevation.

### 5.4 LOW 1 — Doctrine-text-as-verbatim-quote banking (NEW)

**Plan v2 explicit statement (banked in §5):**

> *"The `### Phase-0-catches-wrong-premise` doctrine text in CLAUDE.md is verbatim-sourced from Plan v2 §5.1. Any future edit should preserve: (a) the operational rules block (3 rules); (b) the '5 instances + discipline-stability evidence' framing as the canonical narrative anchors; (c) the 'future accumulation' clause. Future CLAUDE.md compactions or refactors must NOT drift these anchors. Same pattern as P0.S7.D-B §3.4 verbatim-closure-narrative-quote banking. Treat the doctrine text as a stable artifact, not as drift-prone prose."*

This protects against the same kind of drift the spec-time-grep-verification discipline was banked to prevent. The doctrine text is a high-stakes narrative anchor; its load-bearing content must survive future edits.

---

## 6. Test specification (Plan v1 §6 unchanged + 1 NEW test)

Plan v1 §6 tests 1-10 preserved. **Plan v2 adds 1 test** for the autouse-fixture extension:

11. **`test_autouse_fixture_initializes_room_orchestrator`** (behavioral) — after the autouse fixture fires, assert `pipeline._room_orchestrator` is a `RoomOrchestrator` instance (not None). Catches future autouse-fixture refactors that drop the init block. Pairs with Phase 3 test 6 (`_init_room_orchestrator` called in `run()` before first shim caller) — together they cover BOTH production and test init paths.

**Net new tests: 11 logical (8 AST + 3 behavioral, was 10 in Plan v1).** Suite delta forecast: 2385 → 2396 (+1 from Plan v1's 2395).

### 6.1 Phase 4 deliberate-regression confirmations (1 NEW addition)

5 confirmations from Plan v1 §6 Phase 4 preserved. **Plan v2 adds**:

- Drop the `_room_orchestrator` init block from `conftest.py` autouse fixture → test 11 fails (room_orchestrator stays None across tests) → revert.

Now 6 confirmations total.

---

## 7. Implementation phases (Plan v1 unchanged + 3.4 dry-run gate)

### Phase 1 — Class extraction + shim layer + autouse fixture extension (+4 tests, ~half-day)

Plan v2 deltas vs v1:
- Step 1: Create `core/room_orchestrator.py` (unchanged from Plan v1).
- Step 2: Add shim functions in pipeline.py (unchanged).
- Step 3: Add `_init_room_orchestrator()` + call from `run()` (unchanged).
- **Step 4 (NEW per Plan v2 MED 1)**: Extend `conftest.py:34-83` autouse fixture per §3.3.
- **Step 5 (NEW per §3.4 dry-run gate)**: Run `tests/test_p0_s7_phase2.py` (uses `_build_shared_context_block` heavily) — verify green BEFORE proceeding to full Phase 1 test additions.
- Step 6: Tests 1, 2, 3, 11 from §6 (4 tests instead of 3 — +1 from Plan v2 §6 addition).

**Suite checkpoint:** 2385 → 2389 (+4, was +3 in Plan v1).

### Phase 2 — Production wiring + behavioral integration (+4 tests, ~quarter-day)

Plan v1 §7 Phase 2 unchanged. Tests 4, 5, 6, 7.

**Suite checkpoint:** 2389 → 2393 (+4).

### Phase 3 — AST invariants (+3 tests, ~quarter-day)

Plan v1 §7 Phase 3 unchanged. Tests 8, 9, 10.

**Suite checkpoint:** 2393 → 2396 (+3).

### Phase 4 — Deliberate-regression confirmations + closure + doctrine elevation (+0 tests, ~quarter-day)

Plan v1 §7 Phase 4 preserved. **Plan v2 adds:**
- 6 deliberate-regression confirmations (was 5 in Plan v1; new one per §6.1).
- LOW 1 banking in closure narrative per §5.4.
- LOW 2 future-accumulation clause already in §5.1 doctrine wording.

**Total effort: ~1 to 1.5 days.** Net new tests: 11 logical. Suite delta: 2385 → 2396.

---

## 8. Validation gate (Plan v1 §8 + Plan v2 additions)

1. All 11 new tests green; full-suite green at 2396.
2. 6/6 deliberate-regression confirmations pass.
3. 130 existing test sites pass unchanged via shim layer + autouse fixture init.
4. **Phase 1 Step 5 dry-run gate**: `tests/test_p0_s7_phase2.py` green BEFORE full Phase 1 work proceeds.
5. CLAUDE.md doctrine elevation landed per §5.1 (verbatim wording + future-accumulation clause).
6. Sub-pattern A memory-note line 65 repurposed.
7. **§5.4 LOW 1 banking**: doctrine text marked as verbatim-source from Plan v2 §5.1; future edits preserve operational rules + 5-instances framing.
8. Stage 2 trigger banked in CLAUDE.md "Pending Work" alongside D-C Stage 2 (combined PR candidate).

---

## 9. Threats / risks (Plan v1 §9 + 1 NEW)

Plan v1 §9 risks 1-9 preserved. Plan v2 addition:

10. **Autouse-fixture extension may not handle ALL 130 sites cleanly.** If specific test files have non-standard setup (e.g., custom fixtures that override the autouse), the autouse extension may not fire for them. Mitigation: §3.4 dry-run gate at Phase 1 Step 5 catches this before full work commits. If dry-run reveals misalignment, scope-out specific tests AND surface as Plan v2 calibration item.

---

## 10. Discipline-count predictions (Plan v1 §10 unchanged)

| Discipline | Pre-D-D | On D-D closure |
|---|---|---|
| Spec-first review cycle | 12-for-12 | **13-for-13** ✓ |
| **Sub-pattern A (GRADUATING)** | 4 instances (memory-note) | **5 instances → ELEVATED to `### Phase-0-catches-wrong-premise` numbered doctrine** ✓ |
| Tripwires-must-match-deferral-surface | 4-for-4 | stays **4-for-4** ✓ |
| Developer-improves-on-spec | 6-for-6 | stays **6-for-6** unless code phase surfaces mechanism improvement |
| Induction-surfaces-invariant-gaps | 7-for-7 | stays **7-for-7** unless Phase 4 surfaces a real gap |
| Canary-finding tracker | 2 instances | stays at **2** |
| Canary-gate override (informal) | 1 instance | stays at **1** |
| Scope-expansion-via-Phase-0 (informal) | 1 instance | stays at **1** (per Q3 strict-read pushback) |
| Deferral-rationale-expires-when-downstream-ships (informal) | 1 instance | stays at **1** |

**Architect-memory disciplines:**
- Spec-time grep-verification (two-pass refinement): 4 instances; Pass 1 applied at Plan v2 drafting (autouse fixture lines + dep-usage map both grep-verified). Pass 2 fires at closure.
- AST-forward-property + behavioral pair: 2 instances; applied at §6 test design.

---

## 11. Closure-narrative banking (Phase 4 explicit)

Phase 4 closure report explicitly banks:

- **6/6 deliberate-regression confirmations** per §6 + §6.1
- **CLAUDE.md doctrine elevation** per §5.1 (verbatim wording + future-accumulation clause)
- **§5.2 sub-pattern A memory-note line 65 repurposed**
- **§5.4 LOW 1 doctrine-text-as-verbatim-quote banking** language explicit
- **Stage 2 trigger** = bundled-queue canary; combined PR candidate with D-C Stage 2
- **130 test sites preserved via autouse fixture + shim layer** — Stage 2 will migrate; documented as known follow-up
- **Discipline-stability narrative** as elevation-integrity evidence (5 strict-held cycles)
- **2 Plan v1 precision items + 3 Plan v2 items** resolution
- **NEW informal observation candidates** (toward future doctrine elevations):
  - Two-stage canary-gated cleanup pattern (now 2 instances: D-C + D-D) — toward potential `### Two-stage-canary-gated-cleanup` doctrine at 5+
  - Auditor-side Q5-estimates-trail-grep (now 2 instances: D-B 21 vs 15; D-D 40 vs 130) — toward potential `### Auditor-estimates-trail-grep` doctrine at 5+ (auditor's own informational note from Q5 verdict)

---

## 12. References

- `tests/p0_s7_dd_audit.md` — Phase 0 audit
- `tests/p0_s7_dd_plan_v1.md` — Plan v1 (retained for delta visibility)
- `conftest.py:34-83` — autouse fixture (Plan v2 §3.3 extension target; grep-verified Pass 1)
- `core/session_state.py:135` — SessionStore (composed dep)
- `core/pipeline_state_store.py:21` — PipelineStateStore (composed dep)
- `pipeline.py:504, 903, 1202, 1312, 1457, 1660, 2192` — 7 helpers to extract
- `tests/test_p0_s7_phase2.py` — Phase 1 dry-run gate target (uses `_build_shared_context_block` heavily)
- Memory: `feedback_spec_time_grep_verification.md` (two-pass refinement) — Pass 1 applied
- Memory: `feedback_ast_forward_property_tests.md` (AST + behavioral pair) — applied at §6

---

## 13. Next steps

1. **Auditor reviews Plan v2.** Specifically: (a) §3.3 autouse fixture code OK? (b) §3.4 dry-run gate at Phase 1 reasonable? (c) §4 refined 3-layer defense complete? (d) §5.4 doctrine-text-as-verbatim-quote banking explicit enough? (e) §11 NEW informal observation candidates worth tracking?
2. **Joint sign-off** on Plan v2 → user forwards to developer.
3. **Developer executes Phase 1-4** with full-suite verification between phases.
4. **Phase 4 closure** banks doctrine elevation per §11.
