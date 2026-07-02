# Pre-P1 Bundle 2 — Governance Plan v3 (2026-05-28)

**Cycle**: Pre-P1 must-fix Bundle 2 (Governance)
**Predecessor**: `tests/pre_p1_bundle2_governance_plan_v2.md` (auditor verdict: BLOCKED by PI #3 — vendored MIT code in D6 scope)
**Discipline**: Strict-mode, 5-artifact cycle (OPTIONAL-Plan-v2 path NOT TAKEN; 20th proof case STAYS at 19; 2nd consecutive blocked bundle)
**Architect**: Claude
**Auditor**: External (Plan v2 verdict in `info.md` 2026-05-28)
**Disposition**: Option (A) EXCLUDE — locked at user adjudication 2026-05-28

---

## §0 Procedural commitments

All Plan v2 §0 commitments PRESERVED. NEW for Plan v3:

### §0 NEW absorption event — PI #3 absorbed (vendored-MIT-licensing-precision)

Plan v2 §2 D6 mechanical-script applied uniform `SPDX-License-Identifier: Apache-2.0` to all 204 files. Auditor PI #3 identified this as a **licensing precision violation**: `core/_minifasnet/__init__.py` + `core/_minifasnet/model.py` are MIT-licensed (Copyright 2020 Minivision) per upstream `minivision-ai/Silent-Face-Anti-Spoofing`. Inline copyright notices preserve the MIT attribution; uniform Apache-2.0 SPDX header would either misrepresent the license, assert unauthorized sublicensing, or create ambiguous declaration (inline says MIT; header says Apache-2.0 → REUSE-tooling conflict).

**Plan v3 disposition (Option A — EXCLUDE)**: D6 mechanical-script in-scope file list explicitly excludes `core/_minifasnet/*.py`. File count drops 204 → 202. Pre-P1 Bundle 2.X (already filed at Plan v1 §1.4-RESULT 2026-05-28) handles comprehensive MIT compliance: (a) `core/_minifasnet/LICENSE` file with verbatim MIT permission notice text from upstream, (b) optional per-file `SPDX-License-Identifier: MIT` headers if REUSE-tooling later reports per-file SPDX coverage as missing.

**§0 NEW commitment EXTENSION** (Bundle 2 → Bundle 3+ discipline carry-forward): developer Pass-3 grep at Phase 4 pre-implementation MUST verify both (a) file-count consistency vs Plan estimate (Bundle 1 + Bundle 2 evidence; ±10% drift triggers Plan v2 absorption) AND (b) license-correctness per file/directory for SPDX-applicable paths (Plan v3 extension). Vendored code paths (`core/_minifasnet/*` + future in-tree vendoring) require per-path license verification, NOT uniform SPDX application.

**Cross-bundle pattern signal banked**: 2 consecutive bundles where Plan v2 review caught precision items across distinct axes — Bundle 1 (PowerShell tool error / line-count under-measure) → Bundle 2 (globbed-pattern file-count over-estimate + vendored-MIT-license-precision). Phase 0 globbed-pattern estimates and uniform-SPDX assumptions both need pre-implementation verification. The §0 NEW commitment extension is the locked calibration mechanism for both axes.

---

## §1 Plan v2 corrections — PI #3 absorbed

### §1.1 File count corrected from 204 to 202 (exclude vendored MIT files)

**Plan v2 §1.1 locked**: 204 files (developer Pass-3 grep authoritative; matched Phase 0 §2 D6 enumeration exactly).

**PI #3 correction**: D6 scope explicitly excludes the 2 vendored MIT files in `core/_minifasnet/`. File count drops to **202**.

**Updated bucket breakdown**:

| Bucket | Plan v2 count | Plan v3 count | Delta |
|---|---|---|---|
| `core/*.py` (EXCLUDING `_minifasnet/*.py`) | 49 | **47** | -2 (vendored MIT) |
| Top-level production (`pipeline.py` + `enroll.py` + `delete_person.py` + `audit_person.py`) | 4 | 4 | 0 |
| `tools/*.py` | 6 | 6 | 0 |
| `bootstrap/classifier/*.py` | 10 | 10 | 0 |
| `tests/*.py` | 131 | 131 | 0 |
| `.github/workflows/*.yml` | 4 | 4 | 0 |
| **TOTAL** | **204** | **202** | **-2** |

**Sub-shape banking**: 4th instance of `Per-artifact-arithmetic-drift-survives-grep-baseline` for Bundle 2 at Plan v3 (Plan v1 had 2 instances from PI #1 + PI #2; Plan v2 banked a 3rd from file-count drift; Plan v3 banks a 4th from PI #3 vendored-MIT-license-precision drift). Same locked-precedent rule (same-cycle multi-instance bumps count as separate instances per P0.S9 + P0.B3).

### §1.2 §2 D6 scope description corrected

**Plan v2 §2 D6**: "Scope locked at Q4 ADJUDICATION (Phase 0); developer Pass-3 grep verified 204 files = `core/*.py` (49) + 4 top-level production scripts + `tools/*.py` (6) + `bootstrap/classifier/*.py` (10) + `tests/*.py` (131) + `.github/workflows/*.yml` (4)."

**Plan v3 correction**: "Scope locked at Q4 ADJUDICATION (Phase 0) + Plan v3 PI #3 absorption (vendored MIT exclusion); architect Pass-3 grep verified 202 files = `core/*.py` (47, **EXCLUDING `_minifasnet/*.py` per Bundle 2.X vendored MIT compliance**) + 4 top-level production scripts (`pipeline.py` + `enroll.py` + `delete_person.py` + `audit_person.py`) + `tools/*.py` (6) + `bootstrap/classifier/*.py` (10) + `tests/*.py` (131) + `.github/workflows/*.yml` (4)."

**D6 mechanical-script** (`tools/add_spdx_headers.py`) MUST explicitly skip paths matching `core/_minifasnet/` — exclude pattern documented in script's in-scope list constant + inline rationale comment naming PI #3 + Bundle 2.X disposition.

### §1.3 §4.1 file-impact table corrected

**Updated D6 row**:

| D | New files | Modified files | Approx total |
|---|---|---|---|
| D1 | LICENSE (project root) | — | 1 new |
| D2 | NOTICE (project root) | — | 1 new |
| D3 | GOVERNANCE.md (project root) | — | 1 new |
| D4 | CODE_OF_CONDUCT.md (project root) | — | 1 new |
| D5 | CONTRIBUTING.md (project root) | — | 1 new |
| D6 | — | **202 files** (core 47 EXCLUDING `_minifasnet/*.py` + top-level 4 + tools 6 + bootstrap 10 + tests 131 + workflows 4) + `.gitignore` (3 whitelist lines) | **203 edits** |
| D7 | — | README.md (one section appended) | 1 edit |

**Total scope (Plan v3 corrected)**: 5 new files + 204 file edits = **209 changes** (was 211 in Plan v2).

### §1.4 §3.1 A6 anchor parametrize fan-out corrected

**Plan v3 §3.1 A6 corrected**: "structural parametrize across in-scope file list + `.gitignore` 3-whitelist-line check | **202-file fan-out + 3 .gitignore whitelist line checks**"

**Total A6 collections**: 202 file checks + 3 whitelist line checks = **205 pytest collections** (was 207 in Plan v2).

**Q5 LOCK at mid 8 anchors UNCHANGED** — vendored-MIT-exclusion does NOT move anchor count. Anchors are logical (8); file-count fan-out is bookkeeping. A6 parametrize-collection delta from 207 → 205 is bookkeeping.

### §1.5 PI #1 + PI #2 + Plan v2 file-count drift absorptions PRESERVED

Plan v1's 2 absorption events (PI #1 D6 row drift; PI #2 band table arithmetic) + Plan v2's 1 absorption event (file-count drift 204 vs ~260) STAY banked. Plan v3's PI #3 absorption is the 4th instance under `Per-artifact-arithmetic-drift-survives-grep-baseline` for Bundle 2 closure under the locked same-cycle-multi-instance precedent (P0.S9 + P0.B3).

### §1.6 NEW informal observation candidate at Plan v3 — `Vendored-license-precision-axis-under-D6-scope`

Plan v2's catching-layer (developer Pass-3 grep at Phase 4) caught the FILE-COUNT drift (204 actual vs ~260 estimate). It did NOT catch the LICENSE-CORRECTNESS drift (uniform Apache-2.0 SPDX applied to MIT-licensed vendored code). Different verification axis: file-count = quantifier-precision; license-correctness = semantic-precision.

**1st instance** banked at Bundle 2 Plan v3 absorption. Watch criteria: 3+ instances at future bundles touching vendored code OR cross-license-tier file mixes for operational-rule candidacy: "Phase 0 SPDX scope MUST verify license per file/directory for vendored paths, not just file count."

**Sub-shape distinct from prior `Per-artifact-arithmetic-drift-survives-grep-baseline` instances**: that family is about quantifier (count) drift. The new sub-shape is about semantic (license) drift. Both could land under `Per-artifact-precision-drift-survives-grep-baseline` parent if generalized, but maintaining the axis distinction makes the operational rules cleaner.

### §1.7 Carries from Plan v2 §1.6 informal observation

`Phase-0-globbed-pattern-estimates-imprecise-explicit-enumeration-precise` (1st instance candidate at Plan v2) — Plan v3 PRESERVES this banking. Bundle 2's Phase 0 had both globbed-pattern imprecision (caught at Plan v2) AND license-precision imprecision (caught at Plan v3). The two are distinct sub-shapes; Plan v3 doesn't escalate the globbed-pattern observation but does add the license-precision observation as a sibling.

---

## §2 D-decisions UNCHANGED from Plan v2 (except D6 scope correction)

D1-D5 + D7 + Cross-D shipping order + all 5 RATIFIED Q-answers PRESERVED verbatim from Plan v1 / Plan v2.

D6 scope correction per §1.2 above. D6 mechanical-script (`tools/add_spdx_headers.py`) gains:
1. **Exclude-path list** (load-bearing): `EXCLUDED_PATHS = ("core/_minifasnet/",)` — script skips any file matching these prefixes
2. **Inline rationale comment** naming PI #3 + Bundle 2.X disposition + REUSE Software spec licensing-precision concern
3. **Idempotent skip logging**: when the script encounters an excluded path, it logs "[SPDX] EXCLUDED (vendored MIT): {path}" with the count tallied at exit

---

## §3 Q5 LOCK (mid 8 unchanged) + closure-projection band table PRESERVED

**Q5 LOCK at mid 8 anchors UNCHANGED**. File-count drift + vendored-MIT-exclusion do NOT move anchor count (anchors are logical, not file-count).

NARROW band [±15%]: **[6.8, 9.2]**. Falsification boundary at ±30%: **≤5 OR ≥11**.

### §3.1 Anchor breakdown finalized (A6 parametrize fan-out corrected)

| # | Anchor | Type | Scope |
|---|---|---|---|
| A1 | D1 LICENSE file | source-inspection: `LICENSE` exists at repo root + opens with "Apache License" + "Version 2.0" markers | One Glob + grep |
| A2 | D2 NOTICE file | source-inspection: `NOTICE` exists + contains "KaraOS" + "The KaraOS Authors" + 3 attribution lines (pyannote/speechbrain/MiniFASNet) | One Glob + grep |
| A3 | D3 GOVERNANCE.md | source-inspection: 5 required-content checkpoints + Phase 1/2/3 evolution path | One file grep |
| A4 | D4 CODE_OF_CONDUCT.md | source-inspection: Contributor Covenant 2.1 marker + maintainer contact line + project name | One file grep |
| A5 | D5 CONTRIBUTING.md | source-inspection: clone + install + test + PR sections + SETUP.md cross-ref + CLAUDE.md mention | One file grep |
| A6 | D6 SPDX headers across Python backend + .gitignore update | structural parametrize across in-scope file list (EXCLUDING `core/_minifasnet/*.py`) + `.gitignore` 3-whitelist-line check | **202-file fan-out + 3 .gitignore checks** |
| A7 | D7 README license/governance section | source-inspection: 4 doc links + "Apache License 2.0" mention | One README grep |
| A8 | D6 mechanical-script idempotency | behavioral: run `tools/add_spdx_headers.py` twice; second run reports 0 files modified + EXCLUDED count remains 2 (vendored MIT skip preserved) | One test invocation |

**Total = 8 logical anchors UNCHANGED. NARROW band [6.8, 9.2]. Q5 LOCK = 8 UNCHANGED.**

A6 parametrize fan-out: **205 pytest collections** (was 207 in Plan v2).

**A8 STRENGTHENED at Plan v3**: idempotency check now also asserts that excluded-path count = 2 on both runs (PI #3 absorption invariant). Future refactor that drops the EXCLUDED_PATHS list would fail A8 with explicit diagnostic naming the vendored MIT exclusion contract.

### §3.2 Closure-projection band table PRESERVED from Plan v1 §1.2 + Plan v2 §3.2

UNCHANGED. Falsification: ≤5 OR ≥11. SLIGHT-DRIFT: 6 (down) OR 10 (up) within ±30%. ON-TARGET (NARROW): 7-9. Exact mid: 8.

---

## §4 Cross-spec impact (file count corrected)

### §4.1 File-impact table (D6 scope corrected to 202)

See §1.3 above. Total: 5 new files + 204 file edits = **209 changes** (was 211 in Plan v2).

### §4.2 No further git ripple — UNCHANGED from Plan v1 / Plan v2 §4.2

### §4.3 Bundle 3-5 unchanged dependencies — UNCHANGED from Plan v1 / Plan v2 §4.3

### §4.4 Vendored MIT compliance check — UPDATED at Plan v3

`core/_minifasnet/LICENSE` ABSENT (verified at Plan v1 §1.4-RESULT 2026-05-28). Pre-P1 Bundle 2.X FILED for:
1. `core/_minifasnet/LICENSE` file with verbatim MIT text from upstream `minivision-ai/Silent-Face-Anti-Spoofing/LICENSE`
2. **NEW at Plan v3**: optional per-file `SPDX-License-Identifier: MIT` + `SPDX-FileCopyrightText: 2020 Minivision` headers on `__init__.py` + `model.py` — flagged for REUSE-tooling compatibility audit at Bundle 2.X

Bundle 2 scope explicitly excludes `core/_minifasnet/*.py` per PI #3 absorption.

---

## §5 Discipline counts (5-artifact cycle — Plan v3 absorbs)

### §5.1 Per-artifact-driven disciplines (UPDATED — 5-artifact)

Locked +1-per-artifact convention applied. Plan v3 adds +1 to each:

| Discipline | Pre-Bundle-2 | Phase 0 | Plan v1 | Plan v2 | **Plan v3** | Closure |
|---|---|---|---|---|---|---|
| Strict-industry-standard mode applications | 114 | 115 | 116 | 117 | **118** | 119 |
| Spec-first review cycle | 123 | 124 | 125 | 126 | **127** | 128 |
| `### Grep-baseline-before-drafting` | 81 | 82 | 83 | 84 | **85** | 86 |
| Cross-cycle-handoff transparency | 84 | 85 | 86 | 87 | **88** | 89 |
| Spec-time grep-verification | 91 | 92 | 93 | 94 | **95** | 96 |

### §5.2 Closure-event disciplines (single +1 at closure) — PRESERVED from Plan v1 §5.2 / Plan v2 §5.2

| Discipline | Pre-Bundle-2 | After closure |
|---|---|---|
| Strict-industry-standard mode closures | 33 | 34 |
| `### Twin-filename-pitfall-prevention` | 32 | 33 (preventive — `tests/pre_p1_bundle2_*.md` cleanly disambiguated against pre-existing pre_p1_bundle1 artifacts) |
| `### Architect-reads-production-code-before-sign-off` | 31 | 32 (closure-audit event with explicit X → Y per `Implicit-doctrine-firings-not-narrative-tracked` sub-rule) |
| Auditor-Q5-estimates-trail-grep | 37 | 38 banked closures |
| Deferred-canary strategy | 35 | 36 applications |

### §5.3 NEW doctrine instances banked at Plan v3 + closure (UPDATED for 5-artifact)

| Discipline | Pre-Bundle-2 | After Plan v3 | After closure | Cycle event |
|---|---|---|---|---|
| `Per-artifact-arithmetic-drift-survives-grep-baseline` | TBD baseline | +3 instances at Plan v2 | **+4 instances total at closure** (Plan v3 PI #3 vendored-MIT-scope = 4th instance — same locked precedent of same-cycle multi-instance bumps) | Same-cycle multi-instance bumps per locked precedent (P0.S9 + P0.B3) |
| `Plan-v1-Pass-2-grep-undercount` | 13 | TBD | **14 (2nd consecutive bundle event)** | Developer Pass-3 grep at Phase 4 caught Plan v1 §1.1 file-count drift |
| `Pre-audit-quantifier-precision-refined-by-grep` SURFACE-CASCADE-AXIS sub-shape | 10 | TBD | **11 (2nd consecutive bundle event)** | Phase 0 globbed-pattern estimate cascaded through Plan v1 unrefined; developer Pass-3 refined at Phase 4 |
| `Zero-precision-items-pre-closure-predictions-blocked` | 3 | **5** | 5 | Plan v1 § confidence "HIGH" blocked by Plan v2 file-count drift (4th instance); Plan v2 §12 confidence "HIGH" blocked by Plan v3 PI #3 (5th instance) — sub-rule elevation candidacy STRENGTHENS STRONGLY at 5th instance |
| `developer-Pass-3-at-Phase-4-pre-implementation` (NEW, banked at Bundle 1 closure) | 1 | TBD | **2** | Bundle 2 = 2nd instance; 3-instance threshold for sub-rule elevation APPROACHES |
| OPTIONAL-Plan-v2 sub-rule track record | 19 | 19 (cycle escalated) | **STAYS at 19** | Bundle 2 ships 5-artifact (Phase 0 + Plan v1 + Plan v2 + Plan v3 + closure); 20th proof case BLOCKED for 2nd consecutive bundle; pattern STRENGTHENS architecture-cost-benefit lesson |
| `Doctrine-prediction-precision-improving-over-arc` 0%-streak | 10 | TBD | **11 (if closure-actual = 8 exact)** | Conditional on Bundle 2 closure-actual = 8 exact |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 31 supporting | TBD | **32 (if within NARROW band [6.8, 9.2])** | Conditional on Bundle 2 within NARROW band |
| `### Phase-0-catches-wrong-premise` | 13 | TBD | **STAYS 13** | Bundle 2 PI #3 was licensing-precision (semantic) NOT wrong-premise; premise (Apache 2.0 governance setup) was ON-TARGET |
| `Phase-0-globbed-pattern-estimates-imprecise-explicit-enumeration-precise` (NEW candidate from Plan v2 §1.6) | 0 | 1 (Plan v2 absorption) | **1 PRESERVED** | Plan v3 doesn't add new instance for this observation; PI #3 is licensing-precision axis, not file-count axis |
| `Vendored-license-precision-axis-under-D6-scope` (NEW candidate from Plan v3 §1.6) | 0 | **+1 instance** | 1 | Bundle 2 Plan v3 — 1st instance candidate banked at architect-memory; 3-instance threshold for operational-rule candidacy |

### §5.4 Multi-discipline preventive convergence — STRENGTHENED at Plan v3

Plan v2's 8 preventive disciplines PRESERVED.

**Plan v3 ADDS 1 NEW preventive application**:
9. **BIDIRECTIONAL license-precision audit at Plan v3** — auditor caught uniform-Apache-2.0-SPDX-on-MIT-files at Plan v2 review; Plan v3 absorbs via EXCLUDE disposition; mechanical-script in-scope list explicitly carries the exclusion; A8 anchor strengthened to assert exclusion count invariant. Same shape as Plan v2's BIDIRECTIONAL Pass-3 file-count verification but at semantic-precision axis instead of quantifier-precision axis.

**9 preventives applied at Bundle 2 Plan v3** (was 8 at Plan v2; was 7 at Bundle 1 closure). **Multi-discipline preventive convergence STRONGLY WARRANTED elevation candidacy STRENGTHENS STRONGLY** — 3-instance trajectory across Bundle 1 (7) → Plan v2 (8) → Plan v3 (9). If Bundle 2 closure preserves 9 preventives, elevation event WARRANTED at Bundle 2 closure-audit per Bundle 1-banked elevation framework.

---

## §6 Closure-narrative paste template (Plan v3-aware)

```markdown
| **Pre-P1 Bundle 2 (Governance — Apache 2.0 LICENSE + NOTICE + GOVERNANCE.md + CODE_OF_CONDUCT.md + CONTRIBUTING.md + SPDX headers + README append — 5-artifact cycle [OPTIONAL-Plan-v2 path NOT TAKEN; 20th proof case STAYS at 19; 2 consecutive blocked bundles] / Plan v2 absorbed file-count drift / Plan v3 absorbed PI #3 vendored-MIT-licensing-precision) CLOSED 2026-05-2X** — [SUMMARY: Apache 2.0 governance setup landed; LICENSE + NOTICE + 3 governance .md files at repo root; SPDX headers across 202-file Python backend (core 47 EXCLUDING _minifasnet + top-level 4 + tools 6 + bootstrap 10 + tests 131 + workflows 4) via idempotent mechanical script with vendored-MIT-exclusion logic; README appended with license/governance pointers; .gitignore updated with 3 new whitelist negations]. **N/N anchor tests A1-A8 GREEN** with A6 parametrize fan-out covering 205 file/line checks (was 207 in Plan v2; 263 in Plan v1; corrected at Plan v3 PI #3 absorption). A8 STRENGTHENED to assert EXCLUDED count = 2 invariant. **5/5 deliberate-regression confirmations passed cleanly** per `### Induction-surfaces-invariant-gaps` discipline: [a-e regression list]. **Doctrine bumps banked**: `Per-artifact-arithmetic-drift-survives-grep-baseline` +4 instances (PI #1 + PI #2 at Plan v1 + file-count drift at Plan v2 + PI #3 vendored-MIT at Plan v3 — same-cycle multi-instance bumps per locked precedent). `Plan-v1-Pass-2-grep-undercount` 13 → 14 (2nd consecutive bundle event). `Pre-audit-quantifier-precision-refined-by-grep` SURFACE-CASCADE-AXIS 10 → 11 (2nd consecutive bundle event). `Zero-precision-items-pre-closure-predictions-blocked` 3 → 5 (2 in-cycle Plan-confidence-blocks at Plan v2 + Plan v3; sub-rule elevation candidacy STRONGLY WARRANTED at 5th instance). `developer-Pass-3-at-Phase-4-pre-implementation` 1 → 2 (3-instance threshold approaches). NEW `Vendored-license-precision-axis-under-D6-scope` 1st instance banked. OPTIONAL-Plan-v2 sub-rule 19 → STAYS at 19 (2 consecutive blocked bundles — Pre-P1 doc/config work has measurement + licensing precision surfaces benefiting from staged absorption rather than racing through OPTIONAL-Plan-v2). `### Phase-0-granular-decomposition` 31 → 32 supporting (if closure-actual within NARROW band [6.8, 9.2]). `Doctrine-prediction-precision-improving-over-arc` 11th consecutive 0%-streak (if closure-actual = 8 exact). `### Phase-0-catches-wrong-premise` STAYS at 13. Strict-industry-standard mode 114 → 119 applications + 33 → 34 closures (5-artifact cycle). **Multi-discipline preventive convergence 9 disciplines applied** at Bundle 2 closure (3-instance Bundle-1-to-Plan-v3 trajectory 7 → 8 → 9 — STRONGLY WARRANTED elevation candidacy STRENGTHENS STRONGLY). **§0 NEW commitment EXTENSION** (developer Pass-3 grep verifies both file-count AND license-correctness for SPDX-applicable paths) banked for Bundle 3-5 carry-forward. **Vendored MIT compliance** (core/_minifasnet/) handled via Bundle 2.X follow-up at directory level + optional per-file MIT SPDX headers. **No CI evidence event required** (governance docs don't change test behavior).
```

---

## §7 Honest-count commitment — STRENGTHENED at Plan v3

Per `Explicit-closure-honest-count-commitment` discipline (LOCKED at P0.B3 closure 2026-05-21):

- Plan v3 §7 MADE → closure §7 HONORED counts as 2 separate instances per STRICT separation
- Bundle 2 total: Plan v1 + Plan v2 + Plan v3 + closure = 4 commitment events (3 MADE + 1 HONORED) for 5-artifact cycle
- Architect commits to honest closure-actual reporting at Phase 7 closure-narrative drafting regardless of which band falls
- IF closure-actual = 8 exact: `Doctrine-prediction-precision-improving-over-arc` 11th-streak banks
- IF closure-actual ∈ {6, 10}: SLIGHT-DRIFT-DOWN/UP reading; doctrine HOLDS; streak interrupted
- IF closure-actual ≤5 OR ≥11: FALSIFICATION-WATCH activates; closure-audit names root cause

---

## §8 Plan v4 path adjudication (defensive)

Per `### Zero-precision-items-at-auditor-review` doctrine: if auditor returns Plan v3 review with NEW PIs (would be 3rd-tier absorption event), cycle escalates to 6-artifact (Plan v4 absorbs — matches P0.S10 6-artifact OPTIONAL-Plan-v2-NOT-TAKEN historical depth).

Plan v3 covers:
- ✓ PI #3 absorption via Option A (EXCLUDE) — Auditor's recommended lean + user adjudication
- ✓ §1.1 + §1.2 + §1.3 + §1.4 file-count corrections (204 → 202; A6 fan-out 207 → 205; footer 211 → 209)
- ✓ §1.5 PI #1 + PI #2 + Plan v2 file-count drift absorptions PRESERVED
- ✓ §1.6 NEW informal observation candidate banked (Vendored-license-precision-axis-under-D6-scope)
- ✓ §2 D6 scope correction (explicit EXCLUDED_PATHS list + mechanical-script update)
- ✓ §3 Q5 LOCK at 8 UNCHANGED (anchor count is logical, not file-count or license-tier)
- ✓ §3.1 A8 STRENGTHENED (exclusion count invariant)
- ✓ §4 file-impact table corrected
- ✓ §5 discipline counts updated for 5-artifact cycle
- ✓ §5.3 doctrine bumps tracked: 4 instances `Per-artifact-arithmetic-drift` + Vendored-license-precision NEW 1st
- ✓ §5.4 multi-discipline preventive convergence 8 → 9
- ✓ §6 closure-narrative paste template Plan v3-aware
- ✓ §7 honest-count commitment preserved (4 events for 5-artifact cycle)
- ✓ §0 NEW commitment EXTENSION for Bundle 3+ carry-forward

**Architect's Plan v3 confidence: HIGH (with reservation)**. PI #3 absorbed via Option A; mechanical scope correction is straightforward. The "reservation" stems from the Plan v2 §12 confidence-also-was-HIGH-but-blocked-by-PI-3 lesson — Plan v3 confidence is HIGH but explicitly acknowledges the `Zero-precision-items-pre-closure-predictions-blocked` discipline's 5th instance possibility if any further licensing-precision OR scope-precision item surfaces. Stating this explicitly DOES NOT increase the prediction's precision (auditor will catch whatever it catches); it makes the architect's epistemic state honest.

---

## §9 Procedural commitments (closure-audit) — PRESERVED + EXTENDED

All 7 procedural commitments preserved from Plan v1 / Plan v2. Plan v3 ADDS 1 NEW:

8. **§0 NEW commitment EXTENSION** — developer Pass-3 grep at Phase 4 MUST verify both (a) file-count consistency vs Plan estimate AND (b) license-correctness per file/directory for SPDX-applicable paths. Bundle 3-5 carry-forward locked. Closure-narrative explicitly references this extension as a Bundle 2 → Bundle 3+ discipline-handoff anchor.

---

## §10 Known Limitations — EXTENDED at Plan v3

Plan v1 / Plan v2 §10 limitations 1-6 PRESERVED verbatim.

7. **NEW (Plan v3)**: `core/_minifasnet/*.py` EXCLUDED from D6 SPDX scope per PI #3 absorption. Bundle 2.X handles vendored MIT compliance at directory level (`core/_minifasnet/LICENSE` with verbatim MIT text from upstream `minivision-ai/Silent-Face-Anti-Spoofing`) AND optional per-file `SPDX-License-Identifier: MIT` + `SPDX-FileCopyrightText: 2020 Minivision` headers on `__init__.py` + `model.py` (REUSE-tooling compatibility audit). Bundle 2 mechanical-script's EXCLUDED_PATHS list contains `core/_minifasnet/` prefix. A8 idempotency anchor STRENGTHENED to assert EXCLUDED count = 2 invariant.

8. **NEW (Plan v3)**: Vendored-license-precision-axis informal observation banked. If future bundles touch cross-license-tier vendored code (in-tree pyannote/speechbrain in `core/_pyannote_fork/` or `core/_speechbrain_fork/` — hypothetical), the EXCLUDED_PATHS list mechanism extends naturally. Mechanical-script's path-detection logic stays simple (prefix match).

---

## §11 Architect Pass-3 grep clearance + scope reconciliation (Plan v3-aware)

Per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine + 3-part operational rule + bidirectional verification + Plan v3 license-precision extension:

1. **Symbol-name-uniqueness grep** ✓ — UNCHANGED from Plan v1 / Plan v2 §11.
2. **Behavioral semantic verification** ✓ — UNCHANGED.
3. **Symmetric verification** ✓ — UNCHANGED.
4. **Pass-3 BIDIRECTIONAL file-count verification** ✓ from Plan v2 — locked at 204 → corrected at Plan v3 PI #3 absorption to 202 (2 vendored MIT files excluded).
5. **NEW Plan v3 — Pass-3 BIDIRECTIONAL license-correctness verification** ✓: architect inspected `core/_minifasnet/__init__.py:3` + `core/_minifasnet/model.py:1-4` inline copyrights at Plan v2 §1.4-RESULT 2026-05-28; auditor cross-checked at Plan v2 review (PI #3) — convergent reading "MIT-licensed vendored code requires either MIT SPDX or exclusion from uniform Apache-2.0 D6 scope." EXCLUDE chosen.

### §11.1 Pre-P1 Bundle 2.Y candidate (architect-memory only) — PRESERVED from Plan v2 §11.1

12 files outside Phase 0 §2 D6 enumeration banked for Bundle 2.Y if REUSE-tooling later flags them. Plan v3 doesn't change this list — PI #3 absorption is about excluding the 2 _minifasnet files from D6, NOT about expanding scope to the 12 Bundle 2.Y candidates.

---

## §12 Standing by for auditor Plan v3 verdict

If CLEAN (0 PIs) → Plan v3 ships to developer for Phase 4 implementation resumption; cycle closes as 5-artifact; OPTIONAL-Plan-v2 sub-rule track record STAYS at 19; multi-discipline preventive convergence 9 disciplines banked.

If PIs surface → Plan v4 absorbs; cycle escalates to 6-artifact (matches P0.S10 historical 6-artifact depth).

**Architect's Plan v3 confidence: HIGH (with explicit acknowledgment of `Zero-precision-items-pre-closure-predictions-blocked` 5th-instance possibility)**. Honest epistemic stance: PI #3 absorbed mechanically via Option A; no remaining structural surprises anticipated, but Bundle 2 has demonstrated that confidence stated unconditionally has been twice-blocked. Plan v3 acknowledges the possibility while preserving the discipline.

---

**Filed**: 2026-05-28
**Architect**: Claude
**Forwarded to**: Auditor (external)
**Prior artifact**: `tests/pre_p1_bundle2_governance_plan_v2.md` (BLOCKED by PI #3 vendored MIT in D6 scope; absorbed at Plan v3 via Option A EXCLUDE disposition per auditor lean + user adjudication 2026-05-28)
