# Pre-P1 Bundle 2 — Governance Plan v2 (2026-05-28)

**Cycle**: Pre-P1 must-fix Bundle 2 (Governance)
**Predecessor**: `tests/pre_p1_bundle2_governance_plan_v1.md` (RATIFIED CLEAN at auditor Plan v1 verdict; subsequent developer Pass-3 grep at Phase 4 pre-implementation triggered §0 NEW commitment catching-layer)
**Discipline**: Strict-mode, 4-artifact cycle (OPTIONAL-Plan-v2 path NOT TAKEN at this cycle — 20th proof case STAYS at 19)
**Architect**: Claude
**Auditor**: External (Plan v1 verdict in `info.md` 2026-05-28)

---

## §0 Procedural commitments

All 7 procedural commitments preserved from Plan v1 §9 verbatim. NEW for Plan v2:

**§0 NEW absorption event (catching-layer fired AS DESIGNED 2026-05-28)**: developer Pass-3 grep at Phase 4 pre-implementation returned **204 files actual** vs Plan v1 §1.1 / §2 D6 / §4.1 footer estimate of **~260 files** = **-21.5% drift**, exceeding the locked ±10% threshold from §0 NEW commitment. **Per-bucket breakdown** (developer Pass-3 grep, 2026-05-28):

| Bucket | Pass-3 actual | Plan v1 estimate | Delta |
|---|---|---|---|
| `core/*.py` | 49 | ~40 | +22% |
| Top-level production (`pipeline.py` + `enroll.py` + `delete_person.py` + `audit_person.py`) | 4 | 4 | 0% |
| `tools/*.py` | 6 | ~10 | -40% |
| `bootstrap/classifier/*.py` | 10 | ~6 | +67% |
| `tests/*.py` | 131 | ~200 | -34.5% (dominant gap) |
| `.github/workflows/*.yml` | 4 | 4 | 0% |
| **TOTAL** | **204** | **~260** | **-21.5%** |

Cross-bucket signal: 4 of 6 buckets (core/, tools/, bootstrap/, tests/) showed material drift; only the 2 explicitly-enumerated buckets (top-level + workflows) were precise. **Phase 0's globbed-pattern estimates were systematically imprecise; explicit-enumeration estimates were precise.** Cross-bundle pattern signal: Bundle 1 had architect Phase 0 PowerShell line-count tool error → Bundle 2 has architect Phase 0 glob-pattern count error → same SURFACE-CASCADE-AXIS sub-shape, different surface (line count vs file count).

**Plan v2 path TAKEN per §0 NEW commitment**: developer raised STOP back to architect at Phase 4 pre-implementation; architect adjudicated Plan v2 absorption (Path A); cycle escalates from 3-artifact (OPTIONAL-Plan-v2 path) to 4-artifact (Phase 0 + Plan v1 + Plan v2 + closure). 20th OPTIONAL-Plan-v2 sub-rule proof case STAYS at 19 per locked enumeration rule.

**Architect-side Pass-3 grep verification (BIDIRECTIONAL discipline)**: architect independently ran Pass-3 grep at Plan v2 drafting time, returned 216 files including 12 files outside Phase 0's locked enumeration (`conftest.py` + `sim_runner.py` + `repair_gallery.py` + `person_lifecycle.py` + 8 top-level `test_*.py`). **Developer's 204 is authoritative** because Phase 0 §2 D6 explicitly enumerated the in-scope buckets and developer's grep matched the enumeration exactly. The 12 architect-side extras are out of Phase 0 scope; if SPDX coverage for them is later judged useful, file Pre-P1 Bundle 2.Y follow-up. Plan v2 locks **204 files** as the scope.

---

## §1 PI absorption + Plan v1 §1.1 / §2 D6 / §4.1 footer corrections

### §1.1 File count corrected from ~260 to 204 (developer Pass-3 grep authoritative)

**Plan v1 §1.1 claimed**: `~260 files` based on Phase 0 globbed-pattern estimates.

**Pass-3 grep result (2026-05-28)**: **204 files** matching Phase 0 §2 D6 explicit enumeration exactly.

**Plan v2 correction**: every reference to "~260" updated to "204" across §2 D6 scope description + §3.1 A6 anchor parametrize fan-out + §4.1 D6 row + §4.1 footer total scope.

**Sub-shape banking**: 1st instance of `Per-artifact-arithmetic-drift-survives-grep-baseline` for Bundle 2 at Plan v2 (NEW — Plan v1 had 2 instances banked from PI #1 + PI #2 absorption; Plan v2 banks a 3rd instance for the file-count drift). Same locked-precedent rule (same-cycle multi-instance bumps count as separate instances per P0.S9 + P0.B3).

### §1.2 §2 D6 scope description corrected

**Plan v1 §2 D6**: "Scope locked at Q4 ADJUDICATION (Phase 0): ~260 files = `core/*.py` (~40) + `pipeline.py` + `enroll.py` + `delete_person.py` + `audit_person.py` + `tools/*.py` (~10) + `bootstrap/classifier/*.py` (~6) + `tests/*.py` (~200) + `.github/workflows/*.yml` (4)."

**Plan v2 correction**: "Scope locked at Q4 ADJUDICATION (Phase 0); developer Pass-3 grep verified 204 files = `core/*.py` (49) + 4 top-level production scripts (`pipeline.py` + `enroll.py` + `delete_person.py` + `audit_person.py`) + `tools/*.py` (6) + `bootstrap/classifier/*.py` (10) + `tests/*.py` (131) + `.github/workflows/*.yml` (4)."

### §1.3 §4.1 file-impact table corrected

**Plan v1 §4.1 D6 row**: "~260 files (core+pipeline+tools+bootstrap = ~60; tests = ~200; workflows = 4) + `.gitignore` (3 whitelist lines)" → "**~261 edits**"

**Plan v2 §4.1 D6 row corrected**:

| D | New files | Modified files | Approx total |
|---|---|---|---|
| D1 | LICENSE (project root) | — | 1 new |
| D2 | NOTICE (project root) | — | 1 new |
| D3 | GOVERNANCE.md (project root) | — | 1 new |
| D4 | CODE_OF_CONDUCT.md (project root) | — | 1 new |
| D5 | CONTRIBUTING.md (project root) | — | 1 new |
| D6 | — | 204 files (core 49 + top-level 4 + tools 6 + bootstrap 10 + tests 131 + workflows 4) + `.gitignore` (3 whitelist lines) | **205 edits** |
| D7 | — | README.md (one section appended) | 1 edit |

**Total scope (corrected)**: 5 new files + 206 file edits = **211 changes** (was ~267 in Plan v1).

### §1.4 §3.1 A6 anchor parametrize fan-out corrected

**Plan v1 §3.1 A6**: "structural parametrize across in-scope file list + `.gitignore` 3-whitelist-line check | ~260-file fan-out + 1 .gitignore check"

**Plan v2 §3.1 A6 corrected**: "structural parametrize across in-scope file list + `.gitignore` 3-whitelist-line check | 204-file fan-out + 3 .gitignore whitelist line checks"

**Total A6 collections**: 204 file checks + 3 whitelist line checks = **207 pytest collections** (was ~263 in Plan v1).

**Q5 LOCK at mid 8 anchors UNCHANGED** — file-count drift does NOT move anchor count. Anchors are logical (8), not file-count (204). A6 parametrize fan-out is a single logical anchor with structural parametrization; the collection count adjustment is bookkeeping, not anchor-count change.

### §1.5 PI #1 + PI #2 absorption from Plan v1 PRESERVED

Plan v1's two Plan v1 absorption events (PI #1 D6 row drift from Phase 0; PI #2 band table -25% vs -37.5% arithmetic) STAY banked under `Per-artifact-arithmetic-drift-survives-grep-baseline` as 2 separate instances. Plan v2's file-count correction adds a 3rd instance for the same locked precedent — **3 instances banked at Bundle 2 closure under this discipline**.

### §1.6 NEW informal observation candidate banked at Plan v2

`Phase-0-globbed-pattern-estimates-imprecise-explicit-enumeration-precise` — 1st instance candidate at Bundle 2 Phase 0. Phase 0's 4 globbed-pattern buckets (core/ tools/ bootstrap/ tests/) all drifted; 2 explicitly-enumerated buckets (top-level + workflows) were precise. If the same pattern recurs at Bundle 3-5 OR future P1.* cycles, may elevate to operational rule: "Phase 0 file-count enumeration MUST be explicit per-bucket grep at audit drafting time, never globbed-pattern approximation."

**Watch criteria**: 3+ instances for operational-rule formalization candidacy. Banked at architect-memory only this cycle.

---

## §2 D-decisions UNCHANGED from Plan v1

D1-D7 + Cross-D shipping order + all 5 RATIFIED Q-answers PRESERVED verbatim from Plan v1 §2.

Only changes vs Plan v1:
- §2 D6 scope description (count corrected per §1.2 above)
- §2 D6 mechanical-script SPDX scope list (loaded from verified file list)

---

## §3 Q5 LOCK (mid 8 unchanged) + corrected closure-projection band table

**Q5 LOCK at mid 8 anchors UNCHANGED** — file-count drift does NOT move anchor count (anchors are logical, fan-out is collection bookkeeping).

NARROW band [±15%]: **[6.8, 9.2]**. Falsification boundary at ±30% per locked precedent: **≤5 OR ≥11**.

### §3.1 Anchor breakdown finalized (A6 parametrize fan-out corrected)

| # | Anchor | Type | Scope |
|---|---|---|---|
| A1 | D1 LICENSE file | source-inspection: `LICENSE` exists at repo root + opens with "Apache License" + "Version 2.0" markers | One Glob + grep |
| A2 | D2 NOTICE file | source-inspection: `NOTICE` exists + contains "KaraOS" + "The KaraOS Authors" + 3 attribution lines (pyannote/speechbrain/MiniFASNet) | One Glob + grep |
| A3 | D3 GOVERNANCE.md | source-inspection: 5 required-content checkpoints (philosophy + BDFL + decision-process + contributor expectations + escalation) + Phase 1/2/3 evolution path mentioned | One file grep |
| A4 | D4 CODE_OF_CONDUCT.md | source-inspection: Contributor Covenant 2.1 marker (e.g., "Version 2.1") + maintainer contact line + project name | One file grep |
| A5 | D5 CONTRIBUTING.md | source-inspection: clone + install + test + PR sections + SETUP.md cross-ref + CLAUDE.md mention | One file grep |
| A6 | D6 SPDX headers across Python backend + .gitignore update | structural parametrize across in-scope file list + `.gitignore` 3-whitelist-line check | **204-file fan-out + 3 .gitignore checks** |
| A7 | D7 README license/governance section | source-inspection: 4 doc links + "Apache License 2.0" mention | One README grep |
| A8 | D6 mechanical-script idempotency | behavioral: run `tools/add_spdx_headers.py` twice; second run reports 0 files modified | One test invocation |

**Total = 8 logical anchors UNCHANGED. NARROW band [6.8, 9.2]. Q5 LOCK = 8 UNCHANGED.**

A6 parametrize fan-out: **207 pytest collections** (was ~263 in Plan v1).

### §3.2 Closure-projection band table PRESERVED from Plan v1 §1.2 + §3.2

| Closure-actual | % vs mid | Reading | Doctrine consequence |
|---|---|---|---|
| 5 anchors | -37.5% | FALSIFICATION TRIGGER | falsification clause activates IF wrong-premise root cause |
| 6 anchors | -25.0% | SLIGHT-DRIFT-DOWN (within ±30%; doctrine holds) | doctrine HOLDS at 31 supporting; streak interrupted |
| 7 anchors | -12.5% | ON-TARGET (within NARROW ±15%) | doctrine bumps 31 → 32 |
| **8 anchors (Q5 LOCK)** | **0%** | exact mid | doctrine bumps 31 → 32; **11th consecutive 0%-streak rebuild** under `Doctrine-prediction-precision-improving-over-arc` sub-observation (P0.S10 9th + Bundle 1 10th + Bundle 2 11th) |
| 9 anchors | +12.5% | ON-TARGET | doctrine bumps 31 → 32 |
| 10 anchors | +25.0% | SLIGHT-DRIFT-UP (within ±30%; doctrine holds) | doctrine HOLDS at 31 supporting; streak interrupted |
| 11 anchors | +37.5% | FALSIFICATION TRIGGER | falsification clause activates IF wrong-premise root cause |
| ≤4 OR ≥12 | ≥±50% | FALSIFICATION TRIGGER + emergency-review | falsification + same-cycle Plan v2 absorption |

---

## §4 Cross-spec impact (file count corrected)

### §4.1 File-impact table (D6 scope corrected to 204)

See §1.3 above. Total: 5 new files + 206 file edits = **211 changes**.

### §4.2 No further git ripple — UNCHANGED from Plan v1 §4.2

### §4.3 Bundle 3-5 unchanged dependencies — UNCHANGED from Plan v1 §4.3

### §4.4 Vendored MIT compliance check — UNCHANGED from Plan v1 §4.4 + §11

`core/_minifasnet/LICENSE` ABSENT (verified at Plan v1 §1.4-RESULT 2026-05-28). Pre-P1 Bundle 2.X follow-up FILED. Bundle 2 scope unchanged.

---

## §5 Discipline counts (4-artifact cycle — Plan v2 absorbs)

### §5.1 Per-artifact-driven disciplines (UPDATED — 4-artifact, not 3)

Locked +1-per-artifact convention applied. Plan v2 adds +1 to each:

| Discipline | Pre-Bundle-2 | Phase 0 | Plan v1 | **Plan v2** | Closure |
|---|---|---|---|---|---|
| Strict-industry-standard mode applications | 114 | 115 | 116 | **117** | 118 |
| Spec-first review cycle | 123 | 124 | 125 | **126** | 127 |
| `### Grep-baseline-before-drafting` | 81 | 82 | 83 | **84** | 85 |
| Cross-cycle-handoff transparency | 84 | 85 | 86 | **87** | 88 |
| Spec-time grep-verification | 91 | 92 | 93 | **94** | 95 |

### §5.2 Closure-event disciplines (single +1 at closure) — PRESERVED from Plan v1 §5.2

| Discipline | Pre-Bundle-2 | After closure |
|---|---|---|
| Strict-industry-standard mode closures | 33 | 34 |
| `### Twin-filename-pitfall-prevention` | 32 | 33 (preventive — `tests/pre_p1_bundle2_*.md` cleanly disambiguated against pre-existing pre_p1_bundle1 artifacts) |
| `### Architect-reads-production-code-before-sign-off` | 31 | 32 (closure-audit event with explicit X → Y per `Implicit-doctrine-firings-not-narrative-tracked` sub-rule) |
| Auditor-Q5-estimates-trail-grep | 37 | 38 banked closures |
| Deferred-canary strategy | 35 | 36 applications |

### §5.3 NEW doctrine instances banked at Plan v2 + closure (UPDATED)

| Discipline | Pre-Bundle-2 | After Plan v2 | After closure | Cycle event |
|---|---|---|---|---|
| `Per-artifact-arithmetic-drift-survives-grep-baseline` | TBD baseline | **+2 instances at Plan v1 (PI #1 + PI #2)** | **+3 instances total at closure** (Plan v2 §1.1 file-count drift = 3rd instance) | Same-cycle multi-instance bumps per locked precedent (P0.S9 + P0.B3) |
| `Plan-v1-Pass-2-grep-undercount` | 13 (Bundle 1 = 13th instance) | TBD | **14 (2nd consecutive bundle event)** | Developer Pass-3 grep at Phase 4 caught Plan v1 §1.1 file-count drift; same shape as Bundle 1's line-count drift |
| `Pre-audit-quantifier-precision-refined-by-grep` SURFACE-CASCADE-AXIS sub-shape | 10 (Bundle 1 = 10th instance) | TBD | **11 (2nd consecutive bundle event)** | Phase 0 globbed-pattern estimate cascaded through Plan v1 unrefined; developer Pass-3 grep refined at Phase 4 |
| `Zero-precision-items-pre-closure-predictions-blocked` | 3 (Bundle 1 = 3rd instance) | TBD | **4** | Architect's Plan v1 §12 confidence was HIGH ("0 PIs expected"); developer Pass-3 grep blocked the prediction; sub-rule formalization candidacy STRENGTHENS at 4th instance |
| `developer-Pass-3-at-Phase-4-pre-implementation` (NEW, banked at Bundle 1 closure) | 1 (Bundle 1) | TBD | **2** | Bundle 2 = 2nd instance; 3-instance threshold for sub-rule elevation under `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` parent doctrine APPROACHES |
| OPTIONAL-Plan-v2 sub-rule track record | 19 | 19 (cycle escalated) | **STAYS at 19** | Bundle 2 ships 4-artifact (Phase 0 + Plan v1 + Plan v2 + closure); 20th proof case BLOCKED for 2nd consecutive bundle |
| `Doctrine-prediction-precision-improving-over-arc` 0%-streak | 10 | TBD | **11 (if closure-actual = 8 exact)** | Conditional on Bundle 2 closure-actual = 8 exact |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 31 supporting | TBD | **32 (if within NARROW band [6.8, 9.2])** | Conditional on Bundle 2 within NARROW band |
| `### Phase-0-catches-wrong-premise` | 13 | TBD | **STAYS 13** | Bundle 2 Phase 0 premise was ON-TARGET (full-greenfield scope correctly identified); both PIs + Plan v2 file-count correction were precision/arithmetic events, NOT wrong-premise events |
| `Phase-0-globbed-pattern-estimates-imprecise-explicit-enumeration-precise` (NEW candidate) | 0 | **+1 instance** | 1 | Bundle 2 Phase 0 — 1st instance candidate banked at architect-memory; 3-instance threshold for operational-rule candidacy |

### §5.4 Multi-discipline preventive convergence — STRENGTHENED at Plan v2

Plan v1's 6 preventive disciplines (LINE-REF-DRIFT + CROSS-PATH-SYNC-OMISSION + DEFERRED-CANARY-ENTRY-OMISSION + closure-audit verdict forwarding + CODE-TEMPLATE-MISIDENTIFICATION + developer Pass-3 grep) PRESERVED.

**Plan v2 ADDS 2 NEW preventive applications**:
7. **§0 NEW catching-layer ACTIVATED as designed** — developer Pass-3 grep at Phase 4 pre-implementation caught file-count drift before code mutation. Catching-layer worked = preventive discipline VALIDATED in production for 2nd consecutive bundle.
8. **BIDIRECTIONAL Pass-3 verification at Plan v2 drafting** — architect independently ran Pass-3 grep + cross-checked developer's 204 against architect-side 216; reconciled 12-file delta as out-of-Phase-0-scope; locked 204 as authoritative per Phase 0 enumeration.

**8 preventives applied at Bundle 2 Plan v2** (was 7 at Bundle 1 closure). **Multi-discipline preventive convergence STRONGLY WARRANTED elevation candidacy CONTINUES STRENGTHENING**. If Bundle 2 closure preserves at least 7 of these preventives (likely), elevation event locks at Bundle 2 closure-audit per Bundle 1-banked elevation framework.

---

## §6 Closure-narrative paste template (Plan v2-aware)

```markdown
| **Pre-P1 Bundle 2 (Governance — Apache 2.0 LICENSE + NOTICE + GOVERNANCE.md + CODE_OF_CONDUCT.md + CONTRIBUTING.md + SPDX headers + README append — 4-artifact cycle [OPTIONAL-Plan-v2 path NOT TAKEN; 20th proof case STAYS at 19] / Plan v2 absorbed §0 NEW catching-layer file-count drift) CLOSED 2026-05-2X** — [SUMMARY: Apache 2.0 governance setup landed; LICENSE + NOTICE + 3 governance .md files at repo root; SPDX headers across 204-file Python backend (core 49 + top-level 4 + tools 6 + bootstrap 10 + tests 131 + workflows 4) via idempotent mechanical script; README appended with license/governance pointers; .gitignore updated with 3 new whitelist negations]. **N/N anchor tests A1-A8 GREEN** with A6 parametrize fan-out covering 207 file/line checks (was ~263 estimate in Plan v1; corrected at Plan v2 absorption). **5/5 deliberate-regression confirmations passed cleanly** per `### Induction-surfaces-invariant-gaps` discipline: [a-e regression list]. **Doctrine bumps banked**: `Per-artifact-arithmetic-drift-survives-grep-baseline` +3 instances (PI #1 + PI #2 at Plan v1 + file-count drift at Plan v2 — same-cycle multi-instance bumps per locked precedent). `Plan-v1-Pass-2-grep-undercount` 13 → 14 (2nd consecutive bundle event). `Pre-audit-quantifier-precision-refined-by-grep` SURFACE-CASCADE-AXIS 10 → 11 (2nd consecutive bundle event). `Zero-precision-items-pre-closure-predictions-blocked` 3 → 4 (sub-rule elevation candidacy STRENGTHENS). `developer-Pass-3-at-Phase-4-pre-implementation` 1 → 2 (3-instance threshold for sub-rule elevation approaches). OPTIONAL-Plan-v2 sub-rule 19 → STAYS at 19 (2 consecutive blocked bundles; pattern signals architect Phase 0 estimates need calibration discipline — confirms Plan v1's developer-Pass-3-commit was the right design). `### Phase-0-granular-decomposition` 31 → 32 supporting (if closure-actual within NARROW band [6.8, 9.2]). `Doctrine-prediction-precision-improving-over-arc` 11th consecutive 0%-streak (if closure-actual = 8 exact). `### Phase-0-catches-wrong-premise` STAYS at 13 (Bundle 2 file-count drift was precision item not wrong-premise). Strict-industry-standard mode 114 → 118 applications + 33 → 34 closures (4-artifact cycle). **Multi-discipline preventive convergence 8 disciplines applied** at Bundle 2 closure (2nd consecutive bundle event after Bundle 1's 7 — STRONGLY WARRANTED elevation candidacy STRENGTHENS). **§0 NEW commitment catching-layer VALIDATED IN PRODUCTION for 2nd consecutive bundle** — confirms the locked Plan v1 §0 NEW discipline is the right calibration mechanism for architect Phase 0 file-count estimate imprecision. **Vendored MIT compliance** (core/_minifasnet/LICENSE) ABSENT; Pre-P1 Bundle 2.X follow-up FILED. **No CI evidence event required** (governance docs don't change test behavior; next CI run on commit will fire automatically).
```

---

## §7 Honest-count commitment — PRESERVED from Plan v1 §7

Per `Explicit-closure-honest-count-commitment` discipline (LOCKED at P0.B3 closure 2026-05-21):

- Plan v2 §7 MADE → closure §7 HONORED counts as 2 separate instances per STRICT separation
- Plan v1 + Plan v2 → 2 MADE instances + closure 1 HONORED = 3 instances total for Bundle 2 (vs 2 for 3-artifact cycles)
- Architect commits to honest closure-actual reporting at Phase 7 closure-narrative drafting regardless of which band falls
- IF closure-actual = 8 exact: `Doctrine-prediction-precision-improving-over-arc` 11th-streak banks
- IF closure-actual ∈ {6, 10}: SLIGHT-DRIFT-DOWN/UP reading; doctrine HOLDS; streak interrupted
- IF closure-actual ≤5 OR ≥11: FALSIFICATION-WATCH activates; closure-audit names root cause

---

## §8 Plan v3 path adjudication (defensive)

Per `### Zero-precision-items-at-auditor-review` doctrine: if auditor returns Plan v2 review with NEW PIs (would be 2nd-tier absorption event in Bundle 2), cycle escalates to 5-artifact (Plan v3 absorbs).

Plan v2 covers:
- ✓ §0 NEW catching-layer absorption (file-count drift 204 actual vs ~260 estimate)
- ✓ §1.1 + §1.2 + §1.3 + §1.4 Plan v1 corrections applied
- ✓ §1.5 PI #1 + PI #2 absorptions PRESERVED from Plan v1
- ✓ §1.6 NEW informal observation candidate banked
- ✓ §2 D-decisions UNCHANGED (file-count drift doesn't affect D-content)
- ✓ §3 Q5 LOCK at 8 UNCHANGED (anchor count is logical, not file-count)
- ✓ §4 file-impact table corrected
- ✓ §5 discipline counts updated for 4-artifact cycle
- ✓ §6 closure-narrative paste template Plan v2-aware
- ✓ §7 honest-count commitment preserved

**Architect's Plan v2 confidence: HIGH**. The catching-layer fired as designed; Plan v2 absorbs cleanly with mechanical scope correction. No structural surprises expected at Plan v2 review.

---

## §9 Procedural commitments (closure-audit) — PRESERVED from Plan v1 §9

All 7 procedural commitments preserved verbatim. Plan v2 adds 0 NEW commitments — the §0 NEW commitment from Plan v1 ACTIVATED AS DESIGNED, no further commitment needed.

---

## §10 Known Limitations — PRESERVED from Plan v1 §10 + extended

1-5: PRESERVED verbatim from Plan v1 §10.

6. **NEW (Plan v2)**: Phase 0 globbed-pattern file-count estimates are imprecise (Bundle 1 evidence + Bundle 2 evidence). Future Pre-P1 Bundle 3-5 Phase 0 audits SHOULD use explicit per-bucket Pass-1 grep for file-count enumeration, not globbed-pattern approximation. If `Phase-0-globbed-pattern-estimates-imprecise-explicit-enumeration-precise` informal observation reaches 3+ instances, formalize as locked discipline. Until then, the §0 NEW commitment (developer Pass-3 grep at Phase 4 pre-implementation) is the locked calibration mechanism.

---

## §11 Architect Pass-3 grep clearance + scope reconciliation

Per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine + 3-part operational rule + bidirectional verification:

1. **Symbol-name-uniqueness grep** ✓ — UNCHANGED from Plan v1 §11.
2. **Behavioral semantic verification** ✓ — UNCHANGED from Plan v1 §11.
3. **Symmetric verification** ✓ — UNCHANGED from Plan v1 §11.
4. **Pass-3 BIDIRECTIONAL file-count verification** ✓ NEW: developer Pass-3 grep = 204; architect Pass-3 grep = 216 (architect-side; includes 12 out-of-Phase-0-scope files); reconciled — Phase 0 §2 D6 enumeration locked 204 as authoritative. Architect commits to filing Pre-P1 Bundle 2.Y if the 12 architect-side extras need SPDX coverage at a later audit.

### §11.1 Pre-P1 Bundle 2.Y candidate (architect-memory only)

12 files outside Phase 0 §2 D6 enumeration that could benefit from SPDX coverage:
- `conftest.py` (top-level test config)
- `sim_runner.py` (simulation runtime)
- `repair_gallery.py` (top-level utility)
- `person_lifecycle.py` (top-level utility)
- 8 top-level `test_*.py` files (`test_brain_agent.py`, `test_brain_response.py`, `test_executor.py`, `test_faiss_delete.py`, `test_greetings.py`, `test_pipeline.py`, `test_shutdown.py`, `test_vision_v1v4.py`)

**Filing criteria**: file Pre-P1 Bundle 2.Y IF REUSE-tooling later reports these as "missing license info" AND the dashboard isn't ready as a separate distribution (which would make these files clearly part of the main distribution). Until then, banked as architect-memory only.

---

## §12 Standing by for auditor Plan v2 verdict

If CLEAN (0 PIs) → Plan v2 ships to developer for Phase 4 implementation resumption; cycle closes as 4-artifact; OPTIONAL-Plan-v2 sub-rule track record STAYS at 19; multi-discipline preventive convergence 8 disciplines banked.

If PIs surface → Plan v3 absorbs; cycle escalates to 5-artifact (matches P0.S5 / P0.B2 historical Plan v3 cycles).

Architect's Plan v2 confidence: HIGH. The catching-layer fired AS DESIGNED at Plan v1 → developer Pass-3 path; Plan v2's absorption is mechanical scope correction with file-count locked at developer-verified 204. No structural surprises expected.

---

**Filed**: 2026-05-28
**Architect**: Claude
**Forwarded to**: Auditor (external)
**Prior artifact**: `tests/pre_p1_bundle2_governance_plan_v1.md` (RATIFIED CLEAN; subsequent developer Pass-3 grep triggered §0 NEW commitment catching-layer for file-count drift)
