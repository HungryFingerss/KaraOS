# P0.S9 Plan v2 — Helper scripts transactions (PI #1 absorption: §8 arithmetic correction)

**Plan v1 base:** `tests/p0_s9_helper_scripts_transactions_plan_v1.md` (auditor surfaced 1 precision item at Plan v1 review 2026-05-22 — §8 arithmetic drift on 5 artifact-increment disciplines; OPTIONAL-Plan-v2 path BLOCKED at this surface).

**Plan v2 scope (minimal correction per auditor lean Option (a)):**

- **§1** — PI #1 absorbed: 5 §8 cells corrected from "baseline + 1" to "baseline + 2" per locked +1-per-artifact convention (Phase 0 contributes +1, Plan v1 contributes +1).
- **§5.1** — Closure narrative paste-template counts updated for +1 (Plan v2 itself is now a 4th artifact in the cycle); 5 disciplines bump baseline + 4 at closure instead of baseline + 3.
- **§8** — Discipline counts table corrected at Plan v1 close column + extended with Plan v2 close column at +3.
- **No D-decision changes** — D1+D2+D3+D4 contract lock from Plan v1 §2 stays canonical.
- **No anchor count changes** — Plan v1 §3 LOCK at 7 anchors stays canonical (NARROW band [5.95, 8.05] mid 7).
- **No honest-count commitment changes** — Plan v1 §4 commitment (13th instance MADE) stays canonical; Plan v2 does NOT re-make the commitment.
- **2 informal observation bumps** — `Per-artifact-arithmetic-drift-survives-grep-baseline` 1 → 2 instances + `Auditor-adjudication-drift-clarified-by-architect` 2 → 3 instances.

---

## §1. PI #1 absorption — §8 arithmetic correction

### §1.1 Drift trace + corrective enumeration

Auditor's Plan v1 verdict identified 5 §8 cells showing "baseline + 1" at Plan v1 close, which undercounts Phase 0's +1 increment per the locked +1-per-artifact convention (CLAUDE.md P0.S8 closure text verbatim anchor: "P0.S8 Phase 0 + Plan v1 + closure = 3 artifacts × +1 each").

Drift propagation chain (honest reconstruction):

1. **Origin** — Auditor's Phase 0 verdict text wrote "Spec-first cycle 58-for-58 → 59-for-59 at Plan v1 sign-off per locked +1-per-artifact convention." This claim is incorrect under the convention: at Plan v1 sign-off, the cycle has 2 artifacts drafted (Phase 0 + Plan v1) → baseline + 2 = 60.
2. **Propagation** — Plan v1 §8 (architect-drafted) inherited the "→ 59" framing for spec-first cycle + applied the same -1 drift to 4 other artifact-increment disciplines (strict-mode, grep-baseline, cross-cycle-handoff, spec-time-grep-verification).
3. **Catching layer** — Auditor's Plan v1 review surfaced the drift by cross-checking §8 against §5.1 closure-narrative (which CORRECTLY showed "48 → 51 strict-mode applications" = 48 + 3 artifacts).

The catching layer was earlier than P0.B2's 1st instance (which caught at closure-audit). P0.S9's catching layer at Plan v1 review prevents the drift from propagating into §5.1 closure-narrative paste-template (the place where P0.B2's drift was eventually caught + corrected).

### §1.2 Corrected §8 cells (5 disciplines × Plan v1 close column)

Per locked convention (Phase 0 contributes +1, Plan v1 contributes +1, total +2 at Plan v1 close):

| Discipline | Plan v1 §8 (drifted) | Plan v2 §8 corrected | Drift class |
|---|---|---|---|
| Spec-first review cycle | 58 → 59 | **58 → 60** | -1 |
| Strict-industry-standard mode (applications) | 48 → 49 | **48 → 50** | -1 |
| `### Grep-baseline-before-drafting` | 15 → 16 | **15 → 17** | -1 |
| Cross-cycle-handoff transparency precedent | 21 → 22 | **21 → 23** | -1 |
| Spec-time grep-verification | 25 → 26 | **25 → 27** | -1 |

Per-artifact convention semantic: each artifact in the cycle (Phase 0 audit, Plan v1, Plan v2 if any, closure narrative) is a distinct drafting event that contributes +1 to artifact-increment disciplines. The 5 disciplines above are artifact-increment disciplines (every drafting event = +1); the closure-narrative draft is itself an artifact (+1).

### §1.3 Internal consistency cross-check

Verified against §5.1 closure-narrative paste-template from Plan v1:

- Plan v1 §5.1 wrote: "Strict-industry-standard mode 48 → 51 applications + 14 → 15 closures."
- Under the convention with 3 artifacts (Phase 0 + Plan v1 + closure): 48 + 3 = 51 ✓ matches.
- Under the convention with 4 artifacts (Phase 0 + Plan v1 + Plan v2 + closure): 48 + 4 = 52.

Plan v2 §5.1 update (per addition of this Plan v2 artifact): correct closure narrative count from "48 → 51" to "48 → 52" + 4 other disciplines symmetric updates.

### §1.4 Informal observation bumps banked at Plan v2 surface

**Per-artifact-arithmetic-drift-survives-grep-baseline (1 → 2 instances):**

- **1st instance** — P0.B2 closure narrative pre-correction 2026-05-21: subdir narrative had "41 → 45 (5 artifacts × +1 each)" — baseline 41 grep-verified + artifact list 5 correct + math wrong (+4 applied, should be +5). Caught at architect closure-audit.
- **2nd instance (NEW, this banking)** — P0.S9 Plan v1 §8 2026-05-22: 5 artifact-increment discipline rows showed "baseline + 1" at Plan v1 close instead of "baseline + 2" per per-artifact convention. Caught at auditor Plan v1 review (earlier catching layer than 1st instance). Same arithmetic class; different surfaces (closure narrative vs Plan v1 §8 table). The parent doctrine `### Convention-drift-on-discipline-counts` preventive purpose is exactly to catch arithmetic drift before §5.1 inherits it; this instance validates the preventive purpose.

Memory file update: `feedback_per_artifact_arithmetic_drift_survives_grep_baseline.md` bumps 1 → 2 instances at Plan v2 §1.4 banking.

**Auditor-adjudication-drift-clarified-by-architect (2 → 3 instances — opposite-direction subspecies):**

- **1st instance** — P0.S7 closure 2026-05-21: architect surfaced auditor's prior Q5 SLIGHT-DRIFT supporting-count adjudication drift (architect-surfaced direction; auditor accepted rollback at closure adjudication).
- **2nd instance** — P0.B5 Plan v1 close 2026-05-21: auditor self-corrected scope-broadening of `Zero-precision-items-at-auditor-review` from Phase-0-only to Phase-0-OR-Plan-v1 (auditor-self-surfaced direction).
- **3rd instance (NEW, this banking)** — P0.S9 Plan v1 close 2026-05-22: auditor self-surfaced own prior Phase 0 verdict's arithmetic drift (auditor introduced "58 → 59 at Plan v1 sign-off" drift in Phase 0 text → architect inherited faithfully into Plan v1 §8 → auditor caught at Plan v1 review). Auditor-self-surfaced direction; same direction as 2nd instance (P0.B5 auditor self-correction) but at a different artifact-arithmetic surface. Confirms cross-actor symmetry — both actors (architect + auditor) voluntarily surface their own prior drift cleanly.

Memory file update: `feedback_auditor_adjudication_drift_clarified_by_architect.md` bumps 2 → 3 instances at Plan v2 §1.4 banking.

---

## §2. D-decisions — unchanged from Plan v1 §2

D1+D2+D3+D4 contract lock from `tests/p0_s9_helper_scripts_transactions_plan_v1.md` §2.1-§2.5 stays canonical. No edits.

---

## §3. Test surface — unchanged at 7 anchors

Plan v1 §3 LOCK at 7 anchors (D1=2 + D2=2 + D3=1 + D4=2) stays canonical. NARROW band [5.95, 8.05] mid 7 stays canonical. Q5 prediction: 0% ON-TARGET at closure-actual 7 anchors.

---

## §4. Closure-actual projection — unchanged from Plan v1 §4

Plan v1 §4 honest-count commitment (13th instance MADE) stays canonical. Plan v2 does NOT re-make the commitment — Plan v1 §4 is the canonical MADE event per the locked precedent (final-Plan-version-locks-the-band rule from P0.B2 STRICT precedent).

Closure projections per NARROW band [5.95, 8.05] mid 7 (unchanged from Plan v1 §4):

| Closure-actual | Math vs mid 7 | Disposition | Doctrine effect |
|---|---|---|---|
| ≤5 anchors | ≤−28.6% | FALSIFICATION TRIGGER | DEMOTES 12 → 11 supporting |
| 6 anchors | −14.3% | SLIGHT-DRIFT-DOWN | HOLDS at 12 |
| **7 anchors (Plan v1 LOCK)** | 0% | ON-TARGET (exact mid) | **BUMPS 12 → 13 supporting** |
| 8 anchors | +14.3% | SLIGHT-DRIFT-UP | HOLDS at 12 |
| ≥9 anchors | ≥+28.6% | FALSIFICATION TRIGGER | DEMOTES 12 → 11 |

---

## §5. Closure-narrative paste-template — UPDATED for Plan v2 +1 artifact

### §5.1 CLAUDE.md line ~3 (updated per Plan v2 4-artifact cycle)

When P0.S9 closes, prepend above P0.S8 entry (KEY DELTAS from Plan v1 §5.1 are marked with ← Plan v2 update):

```
| **P0.S9 (Helper scripts transactions + paired-write sibling correctness) CLOSED 2026-05-XX** — Closes the P0.5 sibling-pattern violation in `core/audit.py::repair_gallery` that the P0.5 inverse-check missed + 2 BrainDB explicit-transaction migrations + inverse-check coverage extension + `delete_person.py` safety flags. 4 D-decisions in a SMALL-band cycle. **D1 (CORRECTNESS — load-bearing)**: `audit_person.py:79` redirected from `repair_gallery(...)` to `db.prune_outlier_embeddings(...)`; `core/audit.py::repair_gallery` function DELETED entirely; 2 obsolete tests + 1 doc reference cleaned up. Consolidation-over-patch per `### Spec-contracts-not-implementations` discipline. **D2 (DISCIPLINE-SHAPE)**: `BrainDB.delete_person_data` + `prune_shadows_mentioning` migrated from implicit single-commit to explicit `with self.transaction():` wrapping. Atomicity equivalent; matches P0.9.1 ratchet. **D3 (INVARIANT-EXTENSION)**: P0.5 inverse-check `test_all_paired_write_sites_are_in_tuple` extended from `core/db.py`-only to `core/*.py` (top-level glob + `_SCAN_EXCLUDE` for vendored subdirs). Closes the coverage gap that originally hid the D1 violation. **D4 (SAFETY FLAGS)**: `delete_person.py` gains `--dry-run` (preview per-table row counts) + `--confirm` (default-deny gate); `compute_delete_preview()` helper added to `person_lifecycle.py`. **Total P0.S9 LOGICAL ANCHORS: 7** (Plan v1 §3 LOCK EXACT MATCH). **Q5 closure under MID-RANGE methodology**: auditor mid 7, Plan v1 lock 7, **closure actual 7** (exact mid; NARROW band [5.95, 8.05] only 7 anchors qualifies ON-TARGET). **Overage: 0% — ON-TARGET** (5th consecutive 0% exact-mid reading per `Doctrine-prediction-precision-improving-over-arc` sub-observation). Doctrine `### Phase-0-granular-decomposition-enables-accurate-estimates` **BUMPS 12 → 13 SUPPORTING INSTANCES**. Plan v1 §4 honest-count commitment HONORED — **14th instance of `Explicit-closure-honest-count-commitment` discipline** (13th MADE at Plan v1 §4, 14th HONORED at closure per STRICT separation). **5/5 deliberate-regression confirmations PASSED**. **Sub-pattern A 9th instance** banked — opposite-direction subspecies (pre-audit framing was flag-discipline-focused; grep revealed load-bearing P0.5 violation in `core/audit.py`). `### Phase-0-catches-wrong-premise` **8 → 9 instances**. **`### Induction-surfaces-invariant-gaps` 8 → 9 instances** — the P0.5 inverse-check coverage gap (only scanned `core/db.py`, missed `core/audit.py`) IS the inducted-invariant-gap; D3 closes it in same cycle. **`Plan-v1-Pass-2-grep-undercount` 3 → 4 instances** (Phase 0 conversational findings undercounted 4 affected surfaces; Plan v1 §1.1 absorbed corrective enumeration). **6th OPTIONAL-Plan-v2 proof case** stays at 5 — BLOCKED at this cycle (auditor Plan v1 review surfaced PI #1 arithmetic drift; cycle escalated to Plan v2). **`Per-artifact-arithmetic-drift-survives-grep-baseline` 1 → 2 instances** (auditor's Phase 0 verdict introduced -1 drift on 5 §8 cells → architect inherited into Plan v1 §8 → auditor caught at Plan v1 review). **`Auditor-adjudication-drift-clarified-by-architect` 2 → 3 instances** (auditor-self-surfaced direction at Plan v1 review). **`### Zero-precision-items-at-auditor-review` doctrine 7 → 8 instances** (Plan v2 8th instance IF auditor clears Plan v2 with 0 items; Phase 0 returned 4 items + Plan v1 returned 1 item — neither cleared at zero). **Strict-industry-standard mode 48 → 52 applications + 14 → 15 closures**  ← Plan v2 update (was 51; Plan v2 is 4th artifact). Spec-first review cycle 58 → 62-for-62 at closure  ← Plan v2 update (was 61-for-61; Plan v2 is 4th artifact). **`### Grep-baseline-before-drafting` 15 → 19 instances**  ← Plan v2 update (was 18). **Cross-cycle-handoff transparency precedent 21 → 25**  ← Plan v2 update (was 24). **Spec-time grep-verification 25 → 29 instances**  ← Plan v2 update (was 28). Twin-filename pitfall 10 → 11 preventive events (no pre-existing P0.S9 artifacts at audit drafting). **Cumulative suite**: 2607 → ~2607 (D1 deletes 2 obsolete tests + adds 7 new anchors; net delta -2+7 = +5).
```

Key Plan v2 corrections embedded in §5.1:
- "Strict-industry-standard mode 48 → 52" (was 51 in Plan v1 §5.1; Plan v2 is 4th artifact)
- "Spec-first review cycle 58 → 62" (was 61)
- "`### Grep-baseline-before-drafting` 15 → 19" (was 18)
- "Cross-cycle-handoff transparency precedent 21 → 25" (was 24)
- "Spec-time grep-verification 25 → 29" (was 28)
- "**6th OPTIONAL-Plan-v2 proof case** stays at 5 — BLOCKED at this cycle" (was "6th OPTIONAL-Plan-v2 proof case" — adjustment per honest reading; cycle escalated to Plan v2)
- NEW informal observation bumps banked: Per-artifact-arithmetic-drift 1→2, Auditor-adjudication-drift 2→3
- "`### Zero-precision-items-at-auditor-review` 7 → 8 instances" (Plan v2 surface; conditional on auditor clearing Plan v2 with 0 items)

### §5.2-§5.4 parent + subdir `complete-plan.md` + `to_be_checked.md`

Per P0.B3/P0.B5/P0.B6/P0.S8 precedents. Twin-filename pitfall discipline at status flip (parent + subdir). Counts mirror §5.1 corrections above.

### §5.5 Memory files

- `feedback_explicit_closure_honest_count_commitment.md`: bump 12 → 14 instances (Plan v1 §4 MADE 13th + closure HONORED 14th per STRICT).
- `feedback_phase_0_zero_precision_items_at_auditor_review.md`: bump 7 → 8 instances (Plan v2 surface only — Phase 0 + Plan v1 both returned items; if auditor clears Plan v2 with 0 items, instance fires at Plan v2 review).
- `feedback_plan_v1_pass2_grep_undercount.md`: bump 3 → 4 instances (Plan v1 §1.1 corrective enumeration of 4 affected `repair_gallery` surfaces).
- `feedback_doctrine_prediction_precision_improving_over_arc.md`: extend 4-cycle 0% streak to 5-cycle 0% streak (P0.S9 Plan v1 lock at exact mid + closure exact mid would extend, conditional on closure-actual = 7).
- **NEW** `feedback_per_artifact_arithmetic_drift_survives_grep_baseline.md`: bump 1 → 2 instances (P0.S9 Plan v1 §8 arithmetic drift caught at auditor Plan v1 review).
- **NEW** `feedback_auditor_adjudication_drift_clarified_by_architect.md`: bump 2 → 3 instances (auditor-self-surfaced direction at P0.S9 Plan v1 review).

---

## §6. Cross-spec impact analysis — unchanged from Plan v1 §6

---

## §7. Quality gate checklist — Plan v2 absorbs PI #1 cleanly (11/11)

Per strict-mode 11-gate floor (updated for Plan v2):

1. ✅ Phase 0 audit completed + auditor-approved with 4 precision items absorbed at Plan v1 (`### Zero-precision-items-at-auditor-review` did NOT fire at Phase 0; 4 PIs absorbed at Plan v1 §1).
2. ✅ Plan v1 absorbed all 4 Phase 0 precision items proactively (PI #1 enumerated 4 surfaces + 5th decoupled-by-execFile honestly banked; PI #2-#4 scope caps locked).
3. ✅ Plan v2 absorbs the 1 Plan v1 precision item proactively (§8 arithmetic correction + 2 informal observation bumps).
4. ✅ D-decisions have unambiguous contracts — D1 at §2.1 + D2 at §2.2 + D3 at §2.3 + D4 at §2.4 (unchanged from Plan v1).
5. ✅ Pre-mortem coverage — 10 failure modes documented at Phase 0 §6.
6. ✅ Multi-direction invariant trace per D-decision — Phase 0 §7.
7. ✅ Cross-spec impact analysis — Phase 0 §5.
8. ✅ Spec-time grep-verification (Pass-1 + Pass-2 + Pass-3 at Plan v2) — Phase 0 §1-§2 (Pass-1) + Plan v1 §1.1-§1.4 (Pass-2) + Plan v2 §1 (Pass-3 self-audit of §8 arithmetic).
9. ✅ Honest-closure-actual-count commitment made at Plan v1 §4 — 13th instance; Plan v2 inherits canonical commitment.
10. ✅ Deliberate-regression check protocol — Plan v1 §2.5 enumerates 5 induced reverts; Plan v2 inherits unchanged.
11. ✅ Closure-narrative paste-template ready — Plan v2 §5 5-surface template + §3 band-table (counts corrected for Plan v2 4th artifact).

---

## §8. Discipline counts at Plan v2 close (CORRECTED per PI #1 absorption)

| Discipline | Pre-P0.S9 baseline | Phase 0 close (+1) | Plan v1 close (+2) | Plan v2 close (+3) |
|---|---|---|---|---|
| Spec-first review cycle | 58 | 59 | **60** | **61** ✓ |
| Strict-industry-standard mode (applications) | 48 | 49 | **50** | **51** ✓ |
| Strict-industry-standard mode (closures) | 14 | 14 | 14 | 14 (closure event pending) |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 12 supporting | 12 | 12 | 12 (closure-actual event pending; ON-TARGET candidate at 7 anchors → bump 12 → 13 at closure) |
| `### Phase-0-catches-wrong-premise` | 8 | 8 | 8 | 8 (closure event pending; sub-pattern A 9th instance candidate → bump 8 → 9 at closure) |
| `### Twin-filename-pitfall-prevention` | 7 + 4 op rules | 7 | 7 | 7 (11th preventive event; doctrine count holds per locked enumeration rule) |
| `### Grep-baseline-before-drafting` | 15 | 16 | **17** | **18** ✓ |
| `### Zero-precision-items-at-auditor-review` | 7 | 7 (Phase 0 returned 4 PIs, NOT zero) | 7 (Plan v1 returned 1 PI, NOT zero) | 7 (Plan v2 audit pending; if 0 items → 8th instance at Plan v2 surface) |
| Deferred-canary | 16th in-flight | 16 | 16 | 16 (closure event pending) |
| Auditor-Q5-estimates-trail-grep | 18 banked | 18 | 18 | 18 (closure event pending) |
| Cross-cycle-handoff transparency precedent | 21 | 22 | **23** | **24** ✓ |
| Architect-reads-production-code-before-sign-off | 11 banked | 11 | 11 | 11 (closure-audit pending) |
| Sub-pattern A (in `### Phase-0-catches-wrong-premise`) | 8 | 8 | 8 | 8 (9th candidate pending closure) |
| Spec-time grep-verification | 25 instances | 26 | **27** | **28** ✓ |
| Discipline-count-bump-needs-explicit-justification | 11 preventive | 11 | 11 | 11 |
| Convention-drift-on-discipline-counts | 5 | 5 | 5 | 5 |
| `Per-artifact-arithmetic-drift-survives-grep-baseline` | 1 | 1 | 1 | **2** ✓ (Plan v2 §1.4 banking — auditor caught Plan v1 §8 arithmetic drift) |
| `Explicit-closure-honest-count-commitment` | 12 | 12 | **13** ✓ (Plan v1 §4 commitment MADE) | 13 (canonical commitment; Plan v2 does NOT re-make) |
| `Auditor-catches-Q5-math-at-plan-review` | 2 | 2 | 2 | 2 |
| `Plan-v1-Pass-2-grep-undercount` | 3 | 3 | **4** ✓ (Plan v1 §1.1 corrective enumeration) | 4 (canonical at Plan v1) |
| `Bug-fix-cycles-surface-discipline-edges` | 1 | 1 | 1 | 1 |
| `Auditor-adjudication-drift-clarified-by-architect` | 2 | 2 | 2 | **3** ✓ (Plan v2 §1.4 banking — auditor-self-surfaced direction) |
| `Stale-TODO-marker-after-work-complete` | 2 | 2 | 2 | 2 |
| `Board-meeting-attack-premise-needs-grep-verification` | 1 | 1 | 1 | 1 |
| `User-WONTFIX-after-design-dialogue` | 1 | 1 | 1 | 1 |
| `Doctrine-prediction-precision-improving-over-arc` | 4-cycle 0% streak | 4-cycle | 5-cycle (Plan v1 §3 LOCK at exact mid) | 5-cycle (Plan v2 inherits) |
| `Auditor-catches-doctrine-overlap-at-elevation-prep` | 1 (resolved at P0.S8 closure) | 1 | 1 | 1 |
| `Spec-internal-line-wrap-vs-substring-test-mismatch` | 1 (P0.S8) | 1 | 1 | 1 |
| OPTIONAL-Plan-v2 proof case (sub-rule) | 5 cases | 5 | 5 | 5 (closure-conditional 6th proof case BLOCKED — Plan v1 surfaced 1 PI; cycle escalated to Plan v2) |
| `### Induction-surfaces-invariant-gaps` | 8 | 8 | 8 | 8 (D3 fires at closure; bump 8 → 9) |

**Cells marked ✓ are bumped at this Plan version's surface per +1-per-artifact convention.**

Correction details for the 5 artifact-increment disciplines:
- **Pre-correction (Plan v1 §8)**: showed "baseline + 1" at Plan v1 close. Drifted by -1.
- **Post-correction (Plan v2 §8)**: shows "baseline + 2" at Plan v1 close + "baseline + 3" at Plan v2 close per locked convention.

---

## §9. Open questions for auditor — 0

Plan v2 absorbs PI #1 cleanly. No new open questions. Architect prediction: **APPROVED 0 items → ship to developer per OPTIONAL-Plan-v2 path** (8th instance of `### Zero-precision-items-at-auditor-review` at Plan v2 surface if cleared).

But honestly: cycle has already escalated to Plan v2, so the OPTIONAL-Plan-v2 path proof case sub-rule track record stays at 5 cases (cycle is NOT a Plan-v2-optional proof case; the 5-instance ratification at P0.S8 closure correctly stands).

---

## §10. Implementation handoff readiness — unchanged from Plan v1 §10

Developer contract from Plan v1 §10 stays canonical. Plan v2 changes nothing in the D-decision contracts or implementation phases. Plan v2 is documentation-correction only.

---

## §11. Open invariants — unchanged from Plan v1 §11

---

## §12. No doctrine elevation candidacy at P0.S9 — unchanged from Plan v1 §12

Sub-pattern A 9th instance + `### Induction-surfaces-invariant-gaps` 9th instance both are existing-doctrine count bumps, NOT new doctrine elevation candidates. OPTIONAL-Plan-v2 sub-rule already absorbed at P0.S8 closure.

---

**End of Plan v2.** Ready to forward to auditor.

**Architect prediction:** **APPROVED 0 items at Plan v2 review** → ship to developer with D1+D2+D3+D4 contracts from Plan v1 §2 + updated discipline counts at closure per Plan v2 §5.1 corrections. `### Zero-precision-items-at-auditor-review` doctrine fires at Plan v2 surface (8th instance) IF this prediction holds.
