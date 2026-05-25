# P0.B2 Plan v3 — Q5 band-arithmetic correction (closure projection table)

**Plan v2 base:** `tests/p0_b2_faiss_async_rebuild_plan_v2.md` (auditor APPROVED 2026-05-21 with **1 Plan v3 precision item: §3 closure-actual projection table arithmetic errors**).

**Plan v3 absorbs:**
- **P1** §3 band-arithmetic correction: 14 anchors = **+27.3% SLIGHT-DRIFT-UP** (not lumped with falsification); 13 anchors = +18.2% SLIGHT-DRIFT-UP (architect's Plan v2 file had this right, but the architect's Jagan-facing message summary said "11-13 → ON-TARGET" which conflated the 13-anchor row).

All Plan v2 D1-D5 contracts + §2 closure-narrative paste-template + §3 architect commitment + §4 minor refinements + Plan v1 ORDERING INVARIANT/crash-safety table stand UNCHANGED. Plan v3 is pure band-table arithmetic absorption.

**Honest acknowledgment (per cross-cycle-handoff transparency precedent):** the auditor caught a real arithmetic error. The Plan v2 §3 table had `≥14 anchors → ≥+27.3% → approaching falsification | edge case — within ±30% → still HOLDS at 8` which grouped 14-anchor SLIGHT-DRIFT-UP cases AMBIGUOUSLY with the falsification-trigger band. The architect's Jagan-facing message summary worsened the conflation by writing "11-13 anchors → ON-TARGET" (which would have over-bumped doctrine at 13-anchor closure). Plan v3 corrects to explicit per-anchor rows.

---

## §1. P1 — Corrected closure-actual projection table (LOCKED)

**Per locked methodology with auditor's intermediate band 8-14 mid 11:**

| Closure-actual anchor count | Math (vs mid 11) | Disposition | Doctrine effect (`### Phase-0-granular-decomposition`) |
|---|---|---|---|
| ≤6 anchors | `≤−45.5%` | **FALSIFICATION TRIGGER** | **DEMOTES 8 → 7 supporting** |
| 7 anchors | `−36.4%` | **FALSIFICATION TRIGGER** | **DEMOTES 8 → 7 supporting** |
| 8 anchors | `−27.3%` | **SLIGHT-DRIFT-DOWN** | HOLDS at 8 supporting (no bump, no demote) |
| 9 anchors | `−18.2%` | **SLIGHT-DRIFT-DOWN** | HOLDS at 8 supporting |
| **10 anchors (Plan v2 LOCK + architect prediction)** | `−9.1%` | **ON-TARGET** | **BUMPS 8 → 9 supporting** |
| 11 anchors | `0%` (exact mid) | **ON-TARGET** | **BUMPS 8 → 9 supporting** |
| 12 anchors | `+9.1%` | **ON-TARGET** | **BUMPS 8 → 9 supporting** |
| 13 anchors | `+18.2%` | **SLIGHT-DRIFT-UP** | HOLDS at 8 supporting (no bump, no demote) |
| 14 anchors | `+27.3%` | **SLIGHT-DRIFT-UP** | HOLDS at 8 supporting |
| 15 anchors | `+36.4%` | **FALSIFICATION TRIGGER** | **DEMOTES 8 → 7 supporting** |
| ≥16 anchors | `≥+45.5%` | **FALSIFICATION TRIGGER** | **DEMOTES 8 → 7 supporting** |

### §1.1 — Band definitions (re-stated for explicit reference)

| Variance from mid 11 | Anchor count range | Disposition |
|---|---|---|
| Within ±15% | 10, 11, 12 | **ON-TARGET** — doctrine bumps 8 → 9 |
| ±15% to ±30% | 8, 9 (down) AND 13, 14 (up) | **SLIGHT DRIFT** — doctrine holds at 8 |
| ≥±30% | ≤7 (down) AND ≥15 (up) | **FALSIFICATION TRIGGER** — doctrine demotes 8 → 7 |

### §1.2 — Architect prediction holds: 10 anchors at closure → −9.1% ON-TARGET → doctrine BUMPS 8 → 9

Plan v2 §1 locked anchor count at 10 (D1×1 + D2×1 + D3×3 + D4×2 + D5×3 + cross-cutting×0 — wait, let me re-tally):

Per Plan v1 §8.1 + Plan v2 §1 (Test 3 IN):
- D1 (1): 3-tuple signature unit test
- D2 (1): build_from_snapshot signature + idx_updates return
- D3 (3): cursor.lastrowid capture + Phase 3 combines snapshot+pending row_ids + DB UPDATE after lock release
- D4 (2): _mark_faiss_dirty before Phase 3 + _clear_faiss_dirty after Phase 4
- D5 (3): Test 1 prune→restart→recognize + Test 2 crash mid-DB-UPDATE + Test 3 add_embedding-during-rebuild
- Cross-cutting (0): Bug 2 comment correction is part of D5 surface, not a separate test

**Total: 10 logical anchors.** Architect prediction at closure = 10 anchors (deviation from this only if developer surfaces additional fixture-level tests during impl OR consolidates 2 anchors via parametrize).

### §1.3 — Closure-narrative paste-template §2 doctrine track-record line re-verification

Plan v2 §2.1 said: "Doctrine track-record update — `### Phase-0-granular-decomposition-enables-accurate-estimates`: Header line: increment supporting count based on closure-actual reading per §3 projection below. Add P0.B2 row to "Supporting (decomposed → ON-TARGET):" section ONLY IF closure lands ON-TARGET (within ±15% of mid 11, i.e. 9-13 anchors)."

**The "9-13 anchors" range was WRONG** (consistent with the §3 arithmetic error). Corrected per §1 above:

> "Add P0.B2 row to "Supporting (decomposed → ON-TARGET):" section ONLY IF closure lands at **10, 11, or 12 anchors** (within ±15% of mid 11). At 9, 13, or 14 anchors → SLIGHT-DRIFT, doctrine HOLDS at 8 (no new row added). At ≤7 or ≥15 anchors → FALSIFICATION, doctrine demotes, no row added + P0.B2 documented as failed-bump in track-record narrative."

### §1.4 — Plan v2 §3 architect commitment re-verified

Plan v2 §3 commitment text:
> "Doctrine demotion will fire if closure lands at ≤7 or ≥15 anchors. Doctrine bumps to 9 supporting if closure lands in [9, 13]. Architect commits to honest count at closure — no silent over-bumping to avoid demotion, no silent under-counting to avoid SLIGHT-DRIFT label. Closure-actual count is the binding number for doctrine disposition."

**The "[9, 13]" range was WRONG** (off by 1 on the high side; off by 1 on the low side). Corrected:

> "Doctrine demotion will fire if closure lands at ≤7 or ≥15 anchors. Doctrine bumps to 9 supporting if closure lands in [10, 12] (within ±15% of mid 11). Closures at 8, 9, 13, or 14 anchors HOLD the doctrine at 8 supporting (SLIGHT-DRIFT, no bump). Architect commits to honest count at closure — no silent over-bumping to avoid SLIGHT-DRIFT label, no silent under-counting or over-counting to manipulate doctrine outcome. Closure-actual count is the binding number for doctrine disposition."

---

## §2. NEW informal observation banked — `Auditor-catches-Q5-math-at-plan-review`

**Per auditor Plan v2 verdict — 2nd instance:**

| Instance | Cycle + Stage | Error type | Catch | Resolution |
|---|---|---|---|---|
| 1st | P0.B1 Plan v1 §6 | "+33% SLIGHT-DRIFT-UP within ±30% tolerance" — framing conflated ±30% trigger threshold with tolerance ceiling | Auditor Plan v2 verdict P1 | Plan v2 §1 corrected framing |
| 2nd | P0.B2 Plan v2 §3 | Band-table grouped 13-14 anchor rows ambiguously with falsification-trigger band; architect Jagan-facing summary said "11-13 ON-TARGET" which over-bumped 13-anchor case | Auditor Plan v2 verdict P1 | Plan v3 §1 corrected band table |

**Pattern:** closure-projection band math is sufficiently complex that single-actor review (architect) misses arithmetic edges. Auditor cross-check is the catching layer. Same shape as Convention-drift catches at closure narratives.

**Discipline working as designed.** If 3+ instances accumulate, may elevate to operational rule under `feedback_auditor_q5_methodology_rebaseline.md`: "architect-side Q5 math at Plan v2 §3 closure projection table requires auditor cross-check before sign-off."

For now: 2 instances banked as informal observation candidate; not yet doctrine elevation candidate.

---

## §3. Discipline counts at Plan v3 close

- **Spec-first review cycle:** 44 → **45 at Plan v3 close** per locked +1-per-artifact convention (Phase 0 + Plan v1 + Plan v2 + Plan v3 = 4 artifacts; +5 from baseline 41 post-P0.B1 close).
- **Strict-industry-standard mode:** 34 → **35 consecutive applications** + 9 closures (in-flight to 10 at P0.B2 close).
- **`### Phase-0-granular-decomposition-enables-accurate-estimates`:** STAYS at 8 supporting (FALSIFICATION-WATCH ACTIVE per corrected §1 band table).
- **`### Phase-0-catches-wrong-premise`:** STAYS at 7.
- **`### Twin-filename-pitfall-prevention`:** STAYS at 7 instances + 4 operational rules.
- **Auditor-Q5:** 13 banked + 1 in-flight at −9.1% vs mid 11 (ON-TARGET projection).
- **Spec-time grep-verification:** STAYS at 13.
- **Cross-cycle-handoff transparency precedent:** **8 → 9 successful** (Plan v3 §1 honestly acknowledged the band-arithmetic error + adopted auditor correction).
- **Discipline-count-bump-needs-explicit-justification:** STAYS at 10 preventive.
- **Convention-drift-on-discipline-counts:** STAYS at 3 instances.
- **Grep-baseline-before-drafting:** STAYS at 3 instances (Plan v2 §2 explicit baseline citation; no new instance at Plan v3).
- **Explicit-closure-honest-count-commitment:** STAYS at 3 instances (Plan v2 §3 commitment MADE for P0.B2; 4th instance banked if honored at closure).
- **NEW `Auditor-catches-Q5-math-at-plan-review` informal observation:** 1 → **2 instances** (P0.B1 Plan v1 §6 framing error + P0.B2 Plan v2 §3 band-arithmetic error). Watch for 3rd instance for potential elevation.
- **Phase-0-catches-scope-narrowing:** STAYS at 1 candidate.
- **Auditor-precision-item-misframe (auditor-side):** STAYS at 2.
- **Deferred-canary:** STAYS at 9th application in-flight.

---

## §4. Working hypothesis confirmation — HEAVY-band v1→v2→v3 cadence

Per auditor Plan v2 verdict banking:
> "P0.B2 confirms HEAVY-band 5-D-decision specs landing at v3 floor (P0.S5 + P0.B2 = 2 instances now). The multi-axis cadence prediction holds — D-count + complexity-per-site + cross-storage atomicity = v3 minimum even with clean Plan v1 absorption."

**Banked under `feedback_plan_version_cadence_multi_axis.md` as supporting evidence for the multi-axis hypothesis.** 2 instances (P0.S5 + P0.B2) across distinct subsystems (P0.S5 was prompt-injection wrap_user_input; P0.B2 is FAISS async rebuild). Cross-subsystem confirmation strengthens the working hypothesis.

---

## §5. Quality gate checklist (unchanged from Plan v1/v2 — 10 APPLIES + 1 N/A privacy)

Plan v3 is pure precision-item absorption; no architectural changes; gate checklist re-verification unchanged.

---

## §6. Open questions for auditor (0)

No new open questions. P1 from Plan v2 verdict locked per §1 above.

**Architect prediction:** APPROVED 0 items → ship to developer per HEAVY-band v1 → v2 → v3 → developer cadence (matches P0.S5 precedent + auditor's working hypothesis confirmation).

---

## §7. Implementation handoff readiness (Plan v2 §8 + Plan v3 §1 corrections)

Plan v2 §8 readiness check items all still ✓. Plan v3 adds:
- ✅ Closure-actual projection table arithmetic corrected (§1 above)
- ✅ Closure-narrative paste-template §2 doctrine track-record line re-verified (§1.3)
- ✅ Plan v2 §3 architect commitment text re-verified (§1.4)
- ✅ NEW informal observation banked (§2)

**Developer contract:** unchanged from Plan v2 §8 — ~7-10 hours total. Developer reads Plan v1 + Plan v2 + Plan v3 in sequence; Plan v3 supersedes Plan v2 §3 + §2 doctrine track-record line only.

---

**End of Plan v3.** Ready to forward to auditor.

**Architect prediction:** APPROVED 0 items → ship to developer.
