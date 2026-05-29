# Pre-P1 Bundle 3 — Developer Phase 4 Handoff (2026-05-28)

**Status**: Plan v2 RATIFIED CLEAN by auditor 2026-05-28. Phase 4 GREENLIT.
**Cycle shape**: 4-artifact (Phase 0 + Plan v1 + Plan v2 absorbed 3 PIs + closure)
**Scope**: ~28 DEADLINE-MATH migration sites + 44 assert→raise sites (NOT 48 per Plan v1 fabricated; corrected at Plan v2 PI #1 absorption)
**Carry-forward disciplines**: 4-part Pass-2 grep operational rule extension candidacy + Multi-axis-precision-pattern sub-rule candidacy + BIDIRECTIONAL Pass-2 grep cross-actor symmetric verification

---

## §1 Source-of-truth artifacts

Read in order:

1. **Plan v2** (`tests/pre_p1_bundle3_critical_bugs_plan_v2.md`) — authoritative; absorbs PI #1 (48 → 44) + PI #2 (231 → 230) + PI #3 (13 = 12 + 1 cross-file)
2. **Plan v1** (`tests/pre_p1_bundle3_critical_bugs_plan_v1.md`) — historical context; superseded on every numerical detail by Plan v2
3. **Phase 0 audit** (`tests/pre_p1_bundle3_critical_bugs_audit.md`) — Q1-Q8 ratifications + 3-way taxonomy

Plan v2 supersedes prior plans on every count + cascade detail. Earlier plans = historical context only.

---

## §2 Shipping order (Q6 RATIFIED at Phase 0)

**D1 → D2 → D3 → D4 → D5**

Each step lands as own commit. D3 + D4 (assert→raise + AST invariant) are mechanical surfaces; D1 + D2 (deadline-math migration + AST invariant) require per-site semantic judgment.

---

## §3 §0 NEW commitment EXTENSION dual-axis Pass-3 grep at Phase 4 pre-implementation

**MANDATORY BEFORE invoking any mechanical script**:

### §3.1 File-count verification axis (Bundle 1+2 carry-forward)

Run Pass-3 grep verifying:
- `time.time()` per-bucket counts match Plan v2 §1.8 expected: pipeline.py 84 + brain_agent.py 87 + audio.py 11 + db.py 18 + room_orchestrator.py 5 + brain.py 3 + cache_store.py 2 + emotion.py 2 + event_log/producer.py 2 + heavy_worker.py 2 + health.py 2 + state.py 2 + vision_channel.py 2 + voice.py 2 + crash_logs.py 2 + classifier_db.py 1 + classifier_graph.py 1 + dashboard_token.py 1 + reconciler.py 1 (docstring) + reconciler_state.py 2 (docstring) + vision_provider_state.py 1 = **233 grep total** / **230 production** (3 docstring false-positives)
- `assert ` per-bucket counts match Plan v2 §1.14: pipeline.py 14 + brain_db_migrations.py 18 + faces_db_migrations.py 11 + db.py 1 = **44 sites total**
- DEADLINE-MATH per Plan v2 §1.8 + §1.9 + §1.10: ~28 sites (12 pipeline.py from §1.9 + 1 brain_agent.py from §1.10 + ~15 from §1.11 audio + §1.12 room_orchestrator + cache_store + emotion + heavy_worker + state.py-staleness)

### §3.2 Semantic-correctness verification axis (Bundle 3 Plan v3 caveat carry-forward)

Per Plan v2 §0 + Q7 auditor caveat: each migrated `time.time()` site MUST be classified DEADLINE-MATH / WALLCLOCK-WRITE / AMBIGUOUS. Mechanical migration applies ONLY to DEADLINE-MATH sites; WALLCLOCK + AMBIGUOUS stay `time.time()` with `# WALLCLOCK:` annotation.

Each migrated assert site MUST preserve:
- Error message text verbatim
- Exception class = `RuntimeError` (Q2 RATIFIED uniform)
- Boolean condition logic semantic (note: `if not <cond>: raise` inverts `assert <cond>` — the body fires on falsy condition; verify each migration handles `not` correctly)

### §3.3 If file-count drift > ±10% OR semantic-correctness anomaly surfaces → STOP

Raise to architect for Plan v3 absorption. Same rollback discipline as Bundle 1 + Bundle 2 catching-layer events. Plan v2 §0 §11 4-part Pass-2 grep operational rule extension (arithmetic sum-against-total) applies — developer verifies bucket cells sum to TOTAL row.

If clean → proceed to Phase 4 implementation.

---

## §4 D-decisions (Plan v2-authoritative)

### D1 — MF4 deadline-math migration

**Scope (Plan v2 §1.8 locked)**: ~28 DEADLINE-MATH sites across 21 files (Pass-3 grep refines to exact count).

**Mechanical script** (NEW): `tools/migrate_time_monotonic.py`

```python
"""Migrate production deadline-math time.time() calls to time.monotonic().

Idempotent: re-runs report 0 modifications.

Excludes cross-process IPC sites per Plan v2 §1.13 (core/state.py:62 + state.py:108
require shared wallclock for dashboard online/offline detection — migrating to
monotonic would break the cross-process IPC contract).

Per Plan v2 §1.7 3-way taxonomy locked at Q7 ratification:
- DEADLINE-MATH (subtraction-with-stored-timestamp + while-loop guard + _deadline =
  assignment + comparison-to-elapsed) → migrate to time.monotonic()
- WALLCLOCK-WRITE → stays time.time() + # WALLCLOCK: annotation
- AMBIGUOUS → fail-safe to WALLCLOCK + annotation (preserves observability)

Store getter/setter pairs migrated together (e.g., set_last_face_seen() writer AND
peek_last_face_seen() reader both monotonic).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

EXCLUDED_PATHS = ("core/_minifasnet/",)
EXCLUDED_SITES_CROSS_PROCESS_IPC = (
    ("core/state.py", 62),  # # WALLCLOCK: cross-process IPC
    ("core/state.py", 108),  # # WALLCLOCK: cross-process IPC
)

# Per-site migration tagged by Plan v2 §1.8 + §1.9 + §1.10 + §1.11 + §1.12 classification
MIGRATION_TABLE = {
    # DEADLINE-MATH sites — migrate to time.monotonic() + update Store getter/setter pairs
    "pipeline.py": [963, 2773, 2774, 2915, 3313, 3396, 5636, 5758, 7454, 7753, 8419, 8457],
    "core/brain_agent.py": [6908],
    # ... per Plan v2 §1.11 + §1.12 (developer Pass-3 grep refines)
}

WALLCLOCK_ANNOTATION_TABLE = {
    # Sites with explicit # WALLCLOCK: annotation required (subset of WALLCLOCK-WRITE; some sites already have context comments)
    # ... developer enumerates at Pass-3
}
```

**Store getter/setter pairs migration** (Plan v2 §2 D1): when a deadline-math site reads `_pipeline_state_store.peek_last_face_seen()`, the Store's `set_last_face_seen()` writer must also write monotonic time. Plan v2 commits to enumerating these pairs at Phase 4 implementation. Subset of `core/pipeline_state_store.py` + similar Store classes.

**Annotation discipline (Q6 RATIFIED)**:
- Inline (`x = time.time()  # WALLCLOCK: DB write`) OR line-above (`# WALLCLOCK: DB write\nx = time.time()`)
- Categories: `# WALLCLOCK: DB write` / `# WALLCLOCK: log timestamp` / `# WALLCLOCK: event payload` / `# WALLCLOCK: cross-process IPC` / `# WALLCLOCK: archive filename`
- AMBIGUOUS sites default to `# WALLCLOCK: AMBIGUOUS-defaulted` annotation per Q7 fail-safe — flags for future re-classification audit

### D2 — MF4 AST invariant (production-code-only)

**New test file**: `tests/test_no_walltime_deadline_math.py`

**Detector logic** (per Plan v2 §2 D2 + Q3 STANDARD scope RATIFIED):
- AST-walks `pipeline.py` + `core/*.py` (excluding `core/_minifasnet/`) + `bootstrap/classifier/*.py` + `tools/*.py`
- Rejects `time.time()` calls inside:
  - `ast.While` test expressions
  - `ast.Compare` with subtraction patterns (`time.time() - X` followed by comparison)
  - `ast.Assign` targets ending in `_deadline`
  - `ast.Call` `time.time()` followed by binary `+` operation
- **Allowlist via `# WALLCLOCK:` inline OR line-above annotation** (Q6 BOTH placements ratified)
- Self-tests: forward (synthetic violation fires) + inverse (annotated site passes)

### D3 — MF5 assert → raise replacement at 44 sites

**Scope (Plan v2 §1.14 locked at 44)**:

```
pipeline.py (14 sites):
  Line 1746: BUG-2 canonical
  Lines 2020, 2023, 2026, 2029, 2032: BUG-9 cluster (5 sites — NOT "~9" as Plan v1 fabricated)
  Line 6615
  Lines 6639, 6645, 6665, 6671, 6676, 6696, 6702

core/brain_db_migrations.py (18 sites): schema-integrity post-checks
core/faces_db_migrations.py (11 sites): schema-integrity post-checks
core/db.py (1 site): DB invariant
```

**Mechanical replacement** (Q2 RATIFIED uniform, all `RuntimeError`):

```python
# BEFORE
assert <cond>, "<msg>"

# AFTER
if not <cond>:
    raise RuntimeError("<msg>")
```

**Mechanical script** (NEW): `tools/migrate_assert_raise.py` — idempotent; preserves error message text verbatim.

**BUG-9 hybrid disposition** (Q1 RATIFIED + Plan v2 §1.1 docstring update):

At `pipeline.py:2009-2013` (the function `_init_room_orchestrator()` docstring):

```python
"""Initialize RoomOrchestrator singleton.

face_db / brain_orchestrator MUST be non-None at production boot per the
_init_room_orchestrator() invariant runtime check below. In test fixtures
(per tests/conftest.py autouse fixture), None args are tolerated — the
RoomOrchestrator class stores deps without asserting; per-method None checks
on the 3 dep-requiring methods (build_shared_context_block, fetch_recent_room_context,
on_room_end) handle test-context None gracefully.

The runtime raise below + docstring contract + Layer 3 None-handling
together form defense-in-depth (P0.S1 §1.4 layered-defense precedent).
"""
```

**Layer 3 None-checks verification** (Plan v2 §11.1 commitment + Phase 4 developer task):
- `core/room_orchestrator.py::build_shared_context_block` — verify None guard on `db` arg; add if missing
- `core/room_orchestrator.py::fetch_recent_room_context` — verify None guard on `face_db` arg
- `core/room_orchestrator.py::on_room_end` — verify None guard on `brain_orchestrator` arg

If any of the 3 methods lacks an explicit None guard, add one in Phase 4 implementation. Document the None-handling semantic inline.

### D4 — MF5 AST invariant (production-code-only)

**New test file**: `tests/test_no_production_assert.py`

**Detector logic** (per Plan v2 §2 D4 + Q4 RATIFIED allowlist):
- AST-walks `pipeline.py` + `core/*.py` (excluding `core/_minifasnet/`) + `bootstrap/classifier/*.py` + `tools/*.py`
- Rejects `ast.Assert` nodes
- **Allowlist via path**:
  - `tests/*.py` (recursive — includes `tests/fixtures/*.py`)
  - 8 top-level `test_*.py` files (`test_brain_agent.py` + `test_brain_response.py` + `test_executor.py` + `test_faiss_delete.py` + `test_greetings.py` + `test_pipeline.py` + `test_shutdown.py` + `test_vision_v1v4.py`)
  - `conftest.py` (top-level)
- Self-tests: forward (synthetic production assert fires) + inverse (test-file assert passes)

### D5 — CI integration + closure-narrative + doctrine documentation

- New AST invariant tests wired into `fast.yml` workflow (default `pytest -m "not slow and not network and not models"` includes them — no marker changes needed)
- Closure-narrative banked at CLAUDE.md banner per Plan v2 §6 paste template
- CLAUDE.md Architectural Disciplines section — brief notes on MF4 + MF5 sibling structural invariants under `### Multi-discipline-preventive-convergence` parent doctrine context

---

## §5 A1-A5 anchor test files + 5/5 deliberate-regression confirmations

### §5.1 Test files

- `tests/test_no_walltime_deadline_math.py` (NEW; A2 + A1 source-inspection)
- `tests/test_no_production_assert.py` (NEW; A4 + A3 source-inspection)
- `tests/test_bundle3_anchors.py` (NEW; A1 + A3 behavioral + A5 source-inspection on CLAUDE.md + fast.yml)

### §5.2 5/5 deliberate-regression confirmations (per `### Induction-surfaces-invariant-gaps`)

After Phase 4 implementation:
1. **(a)** Insert synthetic `time.time()` in a `while` loop test in production code (no `# WALLCLOCK:` annotation) → A2 fires; revert
2. **(b)** Insert synthetic `assert <cond>` in production code → A4 fires; revert
3. **(c)** Strip `# WALLCLOCK:` annotation from a state.py:62 site → A2 fires with "cross-process IPC site missing annotation" message; revert
4. **(d)** Revert one deadline-math site to `time.time()` → A1 source-inspection fires; revert
5. **(e)** Revert one assert→raise migration to `assert` → A3 source-inspection fires; revert

Document each result in closure narrative under "5/5 deliberate-regression confirmations passed cleanly".

---

## §6 Closure narrative requirements

When Phase 4 complete + all 5 anchors green + 5/5 regressions passed:

1. **Append closure entry** to CLAUDE.md banner using Plan v2 §6 paste template (substitute actual closure date + closure-actual anchor count)
2. **Update test count** at top of CLAUDE.md banner (~3549 + ~72 new collections from A1+A3 parametrize + ~5-10 from A2+A4+A5 self-tests = ~3625-3631)
3. **Update `to_be_checked.md`** with Bundle 3 entry (deferred-canary strategy 37th application)
4. **Path C grep-verify** at closure-narrative drafting:
   - Production code surfaces (~28 deadline-math migrated + ~186 wallclock annotated + 44 assert→raise migrated)
   - 2 mechanical scripts landed (`tools/migrate_time_monotonic.py` + `tools/migrate_assert_raise.py`)
   - 2 NEW test files landed
   - CLAUDE.md banner Bundle 3 entry + doctrine section
   - `to_be_checked.md` Bundle 3 entry via Python `File.read_text` fresh-disk verify
5. **Forward closure-audit findings to auditor** for explicit ratification BEFORE declaring Bundle 3 CLOSED (8th-cycle routinization)
6. **Enumerate 11-discipline preventive convergence** for closure-audit ratification:
   1. LINE-REF-DRIFT preventive (Plan v1 §1.2 line numbers refreshed at Plan v2 §1.9)
   2. CROSS-PATH-SYNC-OMISSION preventive commitment (no new memory files this cycle expected)
   3. DEFERRED-CANARY-ENTRY-OMISSION grep-verify (`to_be_checked.md` Bundle 3 entry fresh-disk Python read)
   4. Closure-audit verdict forwarding commitment (8th-cycle routinization)
   5. CODE-TEMPLATE-MISIDENTIFICATION preventive (canonical examples: Linux kernel CLOCK_MONOTONIC + ROS 2 rclcpp::Clock RCL_STEADY_TIME + systemd Timer monotonic; mechanical scripts verified before run)
   6. Developer Pass-3 grep at Phase 4 pre-implementation (§3 above; Bundle 1+2 carry-forward)
   7. §0 NEW commitment EXTENSION dual-axis (file-count + semantic-correctness)
   8. BIDIRECTIONAL-VALIDATION sub-rule active (Bundle 2 elevation; Bundle 3+ carry-forward)
   9. Phase 0 explicit-per-bucket grep enumeration (no globbed-pattern approximation; Bundle 2 lesson)
   10. Cross-bundle architectural-coherence preventive (Q3 D2 AST invariant scope = Bundle 2 D6 SPDX scope)
   11. **BIDIRECTIONAL architect+auditor Pass-2 grep convergence at Plan v2** (NEW — Bundle 3 Plan v2 §5.4 RATIFIED by auditor)

### §6.1 Architect-side closure-audit verdict-forwarding template

Per 7th-cycle routinization (Bundle 1 + Bundle 2 precedent + 8th cycle at Bundle 3 closure):

```markdown
Bundle 3 Phase 4 implementation COMPLETE 2026-05-2X. Standing by for auditor closure-audit ratification BEFORE declaring CLOSED.

Phase 4 outcomes:
- 5/5 anchors A1-A5 GREEN; ~72 pytest collections via A1+A3 parametrize fan-out
- 5/5 deliberate-regression confirmations passed cleanly
- Suite: 3549 → ~XXXX passing (+72 collections)
- §0 NEW commitment Pass-3 grep dual-axis verification: file-count {clean/drift?} + semantic-correctness {clean/anomaly?}
- 2 mechanical scripts landed + 2 NEW test files
- 11-discipline preventive convergence preserved at closure

Doctrine bumps banked at Plan v2 verdict (locked):
- Per-artifact-arithmetic-drift-survives-grep-baseline 16 → 18
- Zero-precision-items-pre-closure-predictions-blocked 5 → 6
- ### Pass-2-grep-auditor-verified-before-Plan-v1-approval 10 → 11
- ### Zero-precision-items-at-auditor-review 40 → 41
- 3 NEW informal observation candidates
- OPTIONAL-Plan-v2 STAYS at 19

Closure-actual: {X} anchors; {ON-TARGET / SLIGHT-DRIFT / FALSIFICATION} per Q5 LOCK band.

Conditional bumps (closure-actual dependent):
- Doctrine-prediction-precision-improving-over-arc 11 → 12 IF closure-actual = 5
- ### Phase-0-granular-decomposition-enables-accurate-estimates 32 → 33 IF closure-actual ∈ [4.25, 5.75]
- Multi-axis-precision-pattern-confirmed-by-3-consecutive-blocked-bundles 1st instance preserved

Auditor ratification requested.
```

---

## §7 Closure-projection Q5 reading

Q5 LOCK at mid 5 anchors. NARROW band [4.25, 5.75]. Falsification: ≤3 OR ≥8.

Per `Explicit-closure-honest-count-commitment`:
- IF closure-actual = 5 exact → `Doctrine-prediction-precision-improving-over-arc` 12th-streak banks
- IF closure-actual ∈ {4, 6} → ON-TARGET via SLIGHT-DRIFT within ±15%; doctrine bumps; streak interrupted
- IF closure-actual ∈ {3, 7} → SLIGHT-DRIFT within ±30%; doctrine HOLDS at 32; streak interrupted
- IF closure-actual ≤2 OR ≥8 → FALSIFICATION-WATCH activates

Anchor enumeration: A1 (deadline-math) + A2 (no-walltime AST) + A3 (assert→raise) + A4 (no-production-assert AST) + A5 (CI integration + closure narrative). Total = 5 logical anchors UNCHANGED across Plan v1 + Plan v2.

**Phase 4 in-cycle strengthening caveat** (Bundle 1+2 pattern): if Phase 4 surfaces detector gap requiring same-cycle strengthening (e.g., A2 detector fails to catch edge-case deadline pattern), STRENGTHEN in same cycle + bank as `### Induction-surfaces-invariant-gaps` family event. Auditor ratifies via closure-audit verdict.

---

## §8 Standing by

Phase 4 ready to execute. Implementation order: §3 Pass-3 grep dual-axis → D1 deadline-math migration → D2 AST invariant → D3 assert→raise migration → D4 AST invariant → D5 closure → 5/5 regressions → closure-audit forwarding.

On Phase 4 completion: forward closure-audit findings + 11-discipline preventive convergence enumeration for explicit auditor ratification per 8th-cycle routinization discipline.

---

**Filed**: 2026-05-28
**Architect**: Claude
**For**: Developer Phase 4 implementation
**Prior artifact**: `tests/pre_p1_bundle3_critical_bugs_plan_v2.md` (RATIFIED CLEAN at auditor Plan v2 verdict 2026-05-28; 3 PIs absorbed; OPTIONAL-Plan-v2 STAYS at 19 for 3rd consecutive blocked Pre-P1 bundle confirming Multi-axis-precision-pattern)
