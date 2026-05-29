# Pre-P1 Bundle 2 — Governance Plan v1 (2026-05-28)

**Cycle**: Pre-P1 must-fix Bundle 2 (Governance)
**Predecessor**: `tests/pre_p1_bundle2_governance_audit.md` (Phase 0, ACCEPT WITH 2 PIs)
**Discipline**: Strict-mode, OPTIONAL-Plan-v2 path candidate (clean cycle expected)
**Architect**: Claude
**Auditor**: External (Phase 0 verdict in `info.md` 2026-05-28)

---

## §0 Procedural commitments

Carried from Phase 0 §0 verbatim. Plan v1 adds 1 NEW commitment:

**§0 NEW commitment (Bundle 2 — developer Pass-3 grep catching-layer applied preventively)**: per Bundle 1's banked discipline (developer Pass-3 grep at Phase 4 pre-implementation caught architect Phase 0 measurement error before code mutation), Bundle 2's developer Phase 4 MUST run a Pass-3 grep on the in-scope SPDX file list BEFORE running `tools/add_spdx_headers.py`. If actual file count diverges materially from the locked ~260 estimate, raise back to architect for Plan v2 absorption. Same rollback-discipline-preserved pattern as Bundle 1.

---

## §1 PI absorption + Pass-2 grep refresh

### §1.1 PI #1 absorption — §4.1 D6 row + footer updated to ~260

**Phase 0 §4.1 claimed**: D6 = "~60 files (core/ + pipeline.py + ... + bootstrap/classifier/)" and footer "5 new files + ~61 file edits = ~66 changes".

**Q4 ADJUDICATION (Phase 0 §1.2)**: SPDX scope expanded to production + tests + workflows = ~260 files. §4.1 row + footer were stale residue from pre-Q4 scope.

**Plan v1 correction**: §4.1 D6 row restated as ~260 (or breakdown: core+pipeline+tools+bootstrap = ~60, tests = ~200, workflows = 4). Footer "Total scope" recalibrated: 5 new files + ~261 file edits = **~266 changes**.

**Sub-shape banking**: 1st instance of `Per-artifact-arithmetic-drift-survives-grep-baseline` for Bundle 2 — same shape as P0.B3 / P0.S9 / P0.R5 prior catches. Not a new sub-shape; existing pattern. Banks at Bundle 2 closure under doctrine track record extension.

### §1.2 PI #2 absorption — closure-projection band table arithmetic corrected

**Phase 0 §3 claimed**: `≥11 anchors OR ≤6 anchors → ≥+37.5% / ≤-25% → FALSIFICATION TRIGGER`.

**Arithmetic error**: (6-8)/8 = -25.0%. Falsification threshold per locked precedent (P0.S5 + others) is ±30%, NOT ±25%. -25% is within ±30% → SLIGHT-DRIFT-DOWN, NOT falsification.

**Plan v1 correction** — corrected closure-projection band table at Q5 LOCK mid 8 (±30% falsification boundary):

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

**Sub-shape banking**: 2nd instance of `Per-artifact-arithmetic-drift-survives-grep-baseline` for Bundle 2 (same cycle as PI #1; same locked-precedent rule that same-cycle multi-instance bumps don't multiply — but they DO count as separate instances per locked precedent at P0.S9 + P0.B3).

### §1.3 .gitignore whitelist update enumeration (non-blocking obs absorbed)

**Auditor non-blocking observation #2**: Bundle 2 adds 5 new top-level files. `.gitignore` line 143 has `/*.md` ignore rule with whitelist negations. Three new `.md` files need whitelist entries:

```
!/GOVERNANCE.md
!/CODE_OF_CONDUCT.md
!/CONTRIBUTING.md
```

LICENSE + NOTICE without `.md` extension are NOT caught by the `/*.md` rule → no whitelist needed.

**Disposition**: folded into D6 scope (D6's mechanical-script pass also handles the .gitignore update; A6 structural-parametrize anchor extends to verify the 3 whitelist lines are present). This avoids inflating Q5 LOCK from mid 8 to mid 9. Banked as an additional check in §3 anchor breakdown (A6.3 below).

### §1.4 Vendored MIT compliance grep (non-blocking obs absorbed)

**Auditor non-blocking observation #1**: `core/_minifasnet/` contains vendored MIT-licensed code (MiniFASNet architecture from minivision-ai/Silent-Face-Anti-Spoofing). MIT compliance requires the copyright + permission notice be preserved in copies. Plan v1 commitment: grep-verify `core/_minifasnet/LICENSE` (or equivalent) exists in-tree.

**Pass-2 grep verified 2026-05-28** (via Glob `core/_minifasnet/*`):
- Need to check: is `core/_minifasnet/LICENSE` present?
- If ABSENT → file Pre-P1 Bundle 2.X (separate cycle, not blocking Bundle 2)
- If PRESENT → Bundle 2 closure-narrative confirms MIT compliance preserved

**Architect commits to running the grep at Plan v1 drafting time + reporting result**: result below.

```
[Architect Pass-2 grep result — embedded inline, run at Plan v1 drafting time]
```

→ See §1.4-RESULT block in §11 for the grep outcome.

### §1.5 Q1/Q3/Q6/Q7/Q8 ratifications (carried from auditor verdict)

All 5 open auditor questions returned RATIFIED with architect's leans. No further absorption needed:

- **Q1** (NOTICE attributions — all 3 vendored): RATIFIED. Plan v1 §2 D2 commits to including pyannote + speechbrain + MiniFASNet attribution lines.
- **Q3** (CODE_OF_CONDUCT — Contributor Covenant 2.1 verbatim): RATIFIED. Plan v1 §2 D4 commits to Contributor Covenant 2.1 with project-name + maintainer-contact customizations only.
- **Q6** (cross-D shipping order D1 → D2 → D3 → D4 → D5 → D7 → D6): RATIFIED. Plan v1 §2 cross-D order section preserves.
- **Q7** (OPTIONAL-Plan-v2 path): RATIFIED CONDITIONALLY. Plan v1 absorbs PI #1 + PI #2 cleanly → 3-artifact cycle (Phase 0 + Plan v1 + closure) ships; **20th OPTIONAL-Plan-v2 sub-rule proof case** locks at Bundle 2 closure.
- **Q8** (SPDX header position AFTER module docstring): RATIFIED. Plan v1 §2 D6 mechanical-script honors REUSE Software spec ordering.

---

## §2 D-decisions refined (PI absorption applied)

### D1 — Apache 2.0 LICENSE file — UNCHANGED from Phase 0 §2 D1

LICENSE file at repo root, Apache 2.0 verbatim text (~11 KB) from https://www.apache.org/licenses/LICENSE-2.0.txt.

### D2 — NOTICE file — UNCHANGED (Q1 RATIFIED, all 3 vendored attributions included)

Content shape preserved from Phase 0 §2 D2:
```
KaraOS
Copyright 2025-2026 The KaraOS Authors

This product includes software developed at HungryFingerss/Cognitive-System
(https://github.com/HungryFingerss/Cognitive-System).

Portions of this software are derived from:
- pyannote.audio (MIT License) — fork at HungryFingerss/pyannote-audio with dog-ai patches
- speechbrain (Apache License 2.0) — fork at HungryFingerss/speechbrain with dog-ai patches
- MiniFASNet (MIT License) — vendored at core/_minifasnet/ (model architecture from minivision-ai/Silent-Face-Anti-Spoofing)
```

Copyright line uses **The KaraOS Authors** per Q5 ADJUDICATION.

### D3 — GOVERNANCE.md — UNCHANGED (Q2 RATIFIED, BDFL 3-phase evolution)

Content sketch unchanged from Phase 0 §2 D3. Phase 1 BDFL → Phase 2 Maintainer+Committers (3+ regular contributors trigger) → Phase 3 Steering committee PEP-8016-style (10+ committers trigger).

### D4 — CODE_OF_CONDUCT.md — UNCHANGED (Q3 RATIFIED, Contributor Covenant 2.1 verbatim)

Source: https://www.contributor-covenant.org/version/2/1/code_of_conduct/ verbatim. Customizations: replace `[INSERT CONTACT METHOD]` with `jagannivas.001@gmail.com` + replace `[community]` with `KaraOS`.

### D5 — CONTRIBUTING.md — UNCHANGED

Lightweight contribution guide. ~50-100 lines. Sections: clone + install (link to SETUP.md) + run tests (`pytest`) + submit PR + strict-mode discipline reference + CLAUDE.md as project conventions source.

### D6 — SPDX-License-Identifier headers (EXPANDED per PI #1 + .gitignore absorption)

**Scope locked at Q4 ADJUDICATION (Phase 0)**: ~260 files = `core/*.py` (~40) + `pipeline.py` + `enroll.py` + `delete_person.py` + `audit_person.py` + `tools/*.py` (~10) + `bootstrap/classifier/*.py` (~6) + `tests/*.py` (~200) + `.github/workflows/*.yml` (4).

**Header format (Q5 ADJUDICATION + Q8 RATIFIED)** — placed AFTER module docstring:
```python
"""Module docstring."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
```

For `.yml` files (no docstring convention), placed at line 1 (after shebang if present, before name: directive).

**D6 mechanical-script** (`tools/add_spdx_headers.py`):
- Walks in-scope file list (configurable via constant)
- Detects existing SPDX header (idempotency check — re-runs are no-ops)
- Detects module docstring position (insert after closing `"""` if present)
- Inserts 2-line header
- **NEW per §1.3 absorption**: also updates `.gitignore` to add 3 whitelist negations for `!/GOVERNANCE.md`, `!/CODE_OF_CONDUCT.md`, `!/CONTRIBUTING.md` (idempotent — checks for existing lines before adding)
- Reports added/skipped counts at exit
- Has its own test in `tests/test_spdx_headers_invariant.py` (the A6 anchor; expanded scope per §1.3)

**Mechanical-extraction discipline** (per P0.8 / P0.9.2 precedent): verbatim header text, zero "while I'm here" content edits. Script idempotency is the load-bearing property.

### D7 — README.md license + governance mention — UNCHANGED from Phase 0 §2 D7

Append at README.md tail:
```markdown
## License & Governance

KaraOS is licensed under the **Apache License 2.0** (see [LICENSE](LICENSE) and [NOTICE](NOTICE)).

Governance model documented in [GOVERNANCE.md](GOVERNANCE.md). Contributor onboarding in [CONTRIBUTING.md](CONTRIBUTING.md). Community standards in [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
```

### Cross-D shipping order — UNCHANGED from Phase 0 (Q6 RATIFIED)

**D1 → D2 → D3 → D4 → D5 → D7 → D6**.

---

## §3 Q5 LOCK (mid 8 unchanged) + corrected closure-projection band table

**Q5 LOCK at mid 8 anchors UNCHANGED** (Phase 0 confirmed; .gitignore absorbed into A6 scope per §1.3 — no anchor count change).

NARROW band [±15%]: **[6.8, 9.2]**. Falsification boundary at ±30% per locked precedent: **≤5 OR ≥11**.

### §3.1 Anchor breakdown finalized

| # | Anchor | Type | Scope |
|---|---|---|---|
| A1 | D1 LICENSE file | source-inspection: `LICENSE` exists at repo root + opens with "Apache License" + "Version 2.0" markers | One Glob + grep |
| A2 | D2 NOTICE file | source-inspection: `NOTICE` exists + contains "KaraOS" + "The KaraOS Authors" + 3 attribution lines (pyannote/speechbrain/MiniFASNet) | One Glob + grep |
| A3 | D3 GOVERNANCE.md | source-inspection: 5 required-content checkpoints (philosophy + BDFL + decision-process + contributor expectations + escalation) + Phase 1/2/3 evolution path mentioned | One file grep |
| A4 | D4 CODE_OF_CONDUCT.md | source-inspection: Contributor Covenant 2.1 marker (e.g., "Version 2.1") + maintainer contact line + project name | One file grep |
| A5 | D5 CONTRIBUTING.md | source-inspection: clone + install + test + PR sections + SETUP.md cross-ref + CLAUDE.md mention | One file grep |
| A6 | D6 SPDX headers across Python backend + .gitignore update | structural parametrize across in-scope file list + `.gitignore` 3-whitelist-line check | ~260-file fan-out + 1 .gitignore check |
| A7 | D7 README license/governance section | source-inspection: 4 doc links + "Apache License 2.0" mention | One README grep |
| A8 | D6 mechanical-script idempotency | behavioral: run `tools/add_spdx_headers.py` twice; second run reports 0 files modified | One test invocation |

**Total = 8 logical anchors. NARROW band [6.8, 9.2]. Q5 LOCK = 8.**

A6 parametrize fan-out: ~260 file checks + 3 whitelist line checks = ~263 pytest collections.

### §3.2 Corrected closure-projection band table (PI #2 absorption)

See §1.2 above for the full table. Summary:
- Falsification: ≤5 OR ≥11
- SLIGHT-DRIFT: 6 (down) OR 10 (up) — within ±30%
- ON-TARGET (NARROW): 7-9 inclusive
- Exact mid: 8

### §3.3 Honest closure-projection per `Explicit-closure-honest-count-commitment`

- IF closure-actual = 8 exact: `### Phase-0-granular-decomposition` BUMPS 31 → 32 supporting + `Doctrine-prediction-precision-improving-over-arc` extends 11th consecutive 0%-streak (P0.S10 9th + Bundle 1 10th + Bundle 2 11th)
- IF closure-actual ∈ {7, 9}: doctrine still bumps 31 → 32 (within NARROW band); streak interrupted (not exact-mid)
- IF closure-actual ∈ {6, 10}: doctrine HOLDS at 31 supporting (SLIGHT-DRIFT, within ±30%); streak interrupted
- IF closure-actual ≤5 OR ≥11: FALSIFICATION-WATCH activates; closure-audit names root cause

---

## §4 Cross-spec impact (PI #1 absorbed)

### §4.1 File-impact table (D6 scope corrected to ~260)

| D | New files | Modified files | Approx total |
|---|---|---|---|
| D1 | LICENSE (project root) | — | 1 new |
| D2 | NOTICE (project root) | — | 1 new |
| D3 | GOVERNANCE.md (project root) | — | 1 new |
| D4 | CODE_OF_CONDUCT.md (project root) | — | 1 new |
| D5 | CONTRIBUTING.md (project root) | — | 1 new |
| D6 | — | ~260 files (core+pipeline+tools+bootstrap = ~60; tests = ~200; workflows = 4) + `.gitignore` (3 whitelist lines) | **~261 edits** |
| D7 | — | README.md (one section appended) | 1 edit |

**Total scope (PI #1 corrected)**: 5 new files + ~262 file edits = **~267 changes**.

### §4.2 No further git ripple

LICENSE + NOTICE without extensions are NOT caught by `/*.md` ignore rule (rule is glob-pattern, only matches `.md` files). LICENSE + NOTICE auto-tracked.

GOVERNANCE.md + CODE_OF_CONDUCT.md + CONTRIBUTING.md ARE caught by `/*.md` → need whitelist negations (folded into D6 script per §1.3).

### §4.3 Bundle 3-5 unchanged dependencies

Bundle 3 (Critical bugs MF4+MF5): code-only, no governance dep.
Bundle 4 (Observability+concurrency MF6+MF9): code-only.
Bundle 5 (Contract typing MF7+MF8): code-only.

**All 3 remaining bundles can start in parallel after Bundle 2 closes** — no cross-bundle dependencies. Or sequentially per Path A locked at CEO decisions doc.

### §4.4 Vendored MIT compliance check (§1.4 absorption)

Plan v1 grep-verify (run at §11 below):
- `core/_minifasnet/LICENSE` exists? → result in §11
- If absent → Pre-P1 Bundle 2.X follow-up filed

---

## §5 Discipline counts (3-artifact OPTIONAL-Plan-v2 cycle)

### §5.1 Per-artifact-driven disciplines

Locked +1-per-artifact convention applied:

| Discipline | Pre-Bundle-2 | Phase 0 | **Plan v1** | Closure |
|---|---|---|---|---|
| Strict-industry-standard mode applications | 114 | 115 | **116** | 117 |
| Spec-first review cycle | 123 | 124 | **125** | 126 |
| `### Grep-baseline-before-drafting` | 81 | 82 | **83** | 84 |
| Cross-cycle-handoff transparency | 84 | 85 | **86** | 87 |
| Spec-time grep-verification | 91 | 92 | **93** | 94 |

### §5.2 Closure-event disciplines (single +1 at closure)

| Discipline | Pre-Bundle-2 | After closure |
|---|---|---|
| Strict-industry-standard mode closures | 33 | 34 |
| `### Twin-filename-pitfall-prevention` | 32 | 33 (preventive — `tests/pre_p1_bundle2_*.md` cleanly disambiguated against pre-existing pre_p1_bundle1 artifacts) |
| `### Architect-reads-production-code-before-sign-off` | 31 | 32 (closure-audit event with explicit X → Y per `Implicit-doctrine-firings-not-narrative-tracked` sub-rule) |
| Auditor-Q5-estimates-trail-grep | 37 | 38 banked closures |
| Deferred-canary strategy | 35 | 36 applications |

### §5.3 NEW doctrine instances banked at closure

| Discipline | Pre-Bundle-2 | After closure | Cycle event |
|---|---|---|---|
| `Per-artifact-arithmetic-drift-survives-grep-baseline` | TBD baseline | **+2 instances** | PI #1 (D6 row drift 60→260) + PI #2 (band table -25% vs -37.5%) absorbed at Plan v1 — same-cycle multi-instance bumps per locked precedent (P0.S9 + P0.B3) |
| OPTIONAL-Plan-v2 sub-rule track record | 19 | **20** | Bundle 2 ships 3-artifact (Phase 0 + Plan v1 + closure) → 20th proof case LOCKS at closure |
| `Doctrine-prediction-precision-improving-over-arc` 0%-streak | 10 (Bundle 1 = 14 exact) | **11** | Conditional on Bundle 2 closure-actual = 8 exact |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 31 supporting | **32** | Conditional on Bundle 2 within NARROW band [6.8, 9.2] |
| `### Phase-0-catches-wrong-premise` | 13 | **STAYS 13** | Bundle 2 Phase 0 premise was ON-TARGET (full-greenfield scope correctly identified); both PIs were internal-consistency/arithmetic precision items, NOT wrong-premise events |

### §5.4 Multi-discipline preventive convergence (Bundle 2 — 2nd consecutive bundle event)

Per Bundle 1 closure banking (7 disciplines preventively applied → STRONGLY WARRANTED elevation candidacy), Bundle 2 closure is the 2nd consecutive opportunity for the sub-rule to advance.

**Bundle 2's commitment** (6 preventive disciplines applied at Plan v1, will preserve at closure):
1. **LINE-REF-DRIFT preventive** — Plan v1 §1.1 corrected the §4.1 row reference at Plan v1 absorption time
2. **CROSS-PATH-SYNC-OMISSION preventive commitment** — §0 carried; no new memory files this cycle so cross-path discipline applies as no-op
3. **DEFERRED-CANARY-ENTRY-OMISSION grep-verify commitment** — §9 carried; closure narrative will fresh-disk verify the Bundle 2 entry in `to_be_checked.md`
4. **Closure-audit verdict forwarding commitment** — §9 carried; 7th-cycle routinization (P0.R10 + P0.R12-R15 + P0.S11 + P0.S12 + P0.S10 + Bundle 1 + **Bundle 2**)
5. **CODE-TEMPLATE-MISIDENTIFICATION preventive** — D1 + D2 Apache LICENSE text verified verbatim against canonical apache.org source pre-implementation
6. **Developer Pass-3 grep at Phase 4 pre-implementation** — §0 NEW commitment (Bundle 1's banked catching-layer applied preventively to Bundle 2)

**6 preventives applied at Plan v1 → STRONGLY WARRANTED elevation candidacy CONTINUES**. If Bundle 2 closure also applies 5+ preventives (likely; same disciplines preserve at closure-audit), elevation event locks at Bundle 2 closure-audit per Bundle 1-banked elevation framework.

---

## §6 Closure-narrative paste template (Plan v1-aware)

```markdown
| **Pre-P1 Bundle 2 (Governance — Apache 2.0 LICENSE + NOTICE + GOVERNANCE.md + CODE_OF_CONDUCT.md + CONTRIBUTING.md + SPDX headers + README append — 3-artifact OPTIONAL-Plan-v2 cycle / 20th proof case) CLOSED 2026-05-2X** — [SUMMARY: Apache 2.0 governance setup landed; LICENSE + NOTICE + 3 governance .md files at repo root; SPDX headers across ~260-file Python backend (core/+pipeline.py+tools/+bootstrap/+tests/+workflows) via idempotent mechanical script; README appended with license/governance pointers; .gitignore updated with 3 new whitelist negations]. **N/N anchor tests A1-A8 GREEN** with A6 parametrize fan-out covering ~263 file/line checks. **5/5 deliberate-regression confirmations passed cleanly** per `### Induction-surfaces-invariant-gaps` discipline: [a-e regression list]. **Doctrine bumps banked**: `Per-artifact-arithmetic-drift-survives-grep-baseline` +2 instances (PI #1 + PI #2 absorbed at Plan v1; same-cycle multi-instance bumps per locked precedent). OPTIONAL-Plan-v2 sub-rule 19 → 20 proof cases LOCKED. `### Phase-0-granular-decomposition` 31 → 32 supporting (if closure-actual within NARROW band [6.8, 9.2]). `Doctrine-prediction-precision-improving-over-arc` 11th consecutive 0%-streak (if closure-actual = 8 exact). `### Phase-0-catches-wrong-premise` STAYS at 13 (Bundle 2 was internal-consistency PIs not wrong-premise). Strict-industry-standard mode 114 → 117 applications + 33 → 34 closures (3-artifact cycle). **Multi-discipline preventive convergence 6 disciplines applied** at Bundle 2 closure (2nd consecutive bundle event after Bundle 1's 7 — STRONGLY WARRANTED elevation candidacy advances). **Vendored MIT compliance** (core/_minifasnet/LICENSE) result: [PRESENT / ABSENT — if ABSENT, Pre-P1 Bundle 2.X filed]. **No CI evidence event required** (governance docs don't change test behavior; next CI run on commit will fire automatically).
```

---

## §7 Honest-count commitment

Per `Explicit-closure-honest-count-commitment` discipline (LOCKED at P0.B3 closure 2026-05-21):

- Plan v1 §7 MADE → closure §7 HONORED counts as 2 separate instances per STRICT separation
- Architect commits to honest closure-actual reporting at Phase 7 closure-narrative drafting regardless of which band falls
- IF closure-actual = 8 exact: `Doctrine-prediction-precision-improving-over-arc` 11th-streak banks
- IF closure-actual ∈ {6, 10}: SLIGHT-DRIFT-DOWN/UP reading; doctrine HOLDS; streak interrupted
- IF closure-actual ≤5 OR ≥11: FALSIFICATION-WATCH activates; closure-audit names root cause

---

## §8 Plan v2 path adjudication

Per Q7 RATIFIED CONDITIONALLY: OPTIONAL-Plan-v2 path conditional on Plan v1 cleanly absorbing PI #1 + PI #2.

Plan v1 covers:
- ✓ PI #1 absorption at §1.1 + §4.1 row + footer corrected to ~260 / ~267
- ✓ PI #2 absorption at §1.2 + §3.2 corrected band table (≤5 OR ≥11 falsification; ±30% boundary)
- ✓ Non-blocking observations absorbed: .gitignore enumeration (§1.3) + vendored MIT compliance grep (§1.4) + developer Pass-3 commitment (§0 NEW)
- ✓ Q5 LOCK at 8 unchanged (no anchor count change from absorption)
- ✓ Q1/Q3/Q6/Q7/Q8 ratifications documented
- ✓ §7 honest-count commitment preserved

If auditor returns Plan v1 review CLEAN (0 PIs) → ship Plan v1 to developer; cycle ships as 3-artifact (Phase 0 + Plan v1 + closure); **20th OPTIONAL-Plan-v2 proof case** locks at Bundle 2 closure.

If auditor returns Plan v1 with NEW PIs → cycle escalates to 4-artifact (Plan v2 absorbs).

---

## §9 Procedural commitments (closure-audit)

All 6 procedural commitments preserved from Bundle 1 §9:

1. **Path C grep-verify** at closure-narrative drafting (production code + memory files + index entries + `to_be_checked.md` via PowerShell fresh-disk read)
2. **Cross-path memory-file discipline** (no new memory files this cycle expected; carry forward as no-op)
3. **DEFERRED-CANARY-ENTRY-OMISSION preventive** via PowerShell fresh-disk read
4. **Closure-audit verdict forwarding** to auditor for EXPLICIT RATIFICATION before declaring CLOSED — 7th-cycle routinization
5. **Multi-discipline preventive convergence enumeration** at closure (5+ preventives required for STRONGLY WARRANTED candidacy advancement)
6. **No CI evidence event required** for Bundle 2 (governance docs don't change test behavior; differs from Bundle 1)

**NEW for Plan v1 (§0 carried)**:
7. **Developer Pass-3 grep at Phase 4 pre-implementation** — developer MUST run a Pass-3 grep on the in-scope SPDX file list (~260) BEFORE invoking `tools/add_spdx_headers.py`. If actual file count diverges materially (>±10% from 260), raise back to architect for Plan v2 absorption. Bundle 1's banked catching-layer applied preventively. Same rollback-discipline-preserved pattern.

---

## §10 Known Limitations

1. **Dashboard SPDX scope deferred** — `dog-ai-dashboard/` (Next.js app, ~100 source files) is a separate sub-component; Bundle 2 doesn't touch it. Pre-P1 Bundle 2.X follow-up will add LICENSE + SPDX headers if/when the dashboard ships as an independent distribution. For now, the dashboard inherits the top-level LICENSE via project association.

2. **Vendored MIT compliance — VERIFIED PARTIAL at §1.4-RESULT 2026-05-28** — `core/_minifasnet/` has inline copyright notices at `__init__.py:3` + `model.py:1-4` (partial MIT compliance), but NO `core/_minifasnet/LICENSE` file with the full ~10-line MIT permission notice text. **Pre-P1 Bundle 2.X follow-up FILED** to close the gap (trivial: 1 new file with verbatim MIT text from upstream). Bundle 2 scope explicitly excludes this — banked as a separate small cycle.

3. **SPDX script idempotency** — `tools/add_spdx_headers.py` is single-pass; running it twice should be a no-op. A8 anchor tests this property. If a future refactor breaks idempotency (e.g., changing the header text), A8 catches it.

4. **`pytest.ini` + `requirements.txt` excluded** — these config files don't get SPDX headers in Bundle 2. Their line-comment syntax varies (pytest.ini = INI format; requirements.txt = pip format). The LICENSE file at repo root covers their license implicitly. If REUSE-tooling reports them as "missing license info," the future cleanup PR can add `.reuse/dep5` file with explicit configuration; out of Bundle 2 scope.

5. **Old `# TODO-P0.4:` markers** (mentioned at CLAUDE.md `P0.4 Batch 7` history) — these were removed at P0.4 Batch 7 closure 2026-05-08 per `PERMITTED_ANNOTATIONS` discipline. No interaction with Bundle 2.

---

## §11 Architect Pass-2 grep clearance + §1.4 vendored MIT result

Per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine + 3-part operational rule:

1. **Symbol-name-uniqueness grep** ✓ — `LICENSE` / `NOTICE` / `GOVERNANCE.md` / `CODE_OF_CONDUCT.md` / `CONTRIBUTING.md` / `SPDX-License-Identifier` all unambiguously identify Bundle 2 artifacts.
2. **Behavioral semantic verification** ✓ — Phase 0 §1.1 verified that all 3 SPDX matches in `karaos-org-discussions/` are docstring/audit-narrative mentions, NOT actual source-file headers. Bundle 2 work is genuinely greenfield.
3. **Symmetric verification** ✓ — Bundle 2 is purely additive (5 new files + ~261 line-level edits). No delete/rename classes. Reject class N/A.

### §1.4-RESULT (Plan v1 grep-verify of vendored MIT compliance — EXECUTED 2026-05-28)

Glob `core/_minifasnet/*` returned 2 files:
- `core/_minifasnet/__init__.py`
- `core/_minifasnet/model.py`

**No `core/_minifasnet/LICENSE` file exists.**

Inline copyright notices PRESENT in both files (partial compliance):
- `__init__.py:3` — "Source: https://github.com/minivision-ai/Silent-Face-Anti-Spoofing (MIT License, Copyright (c) 2020 Minivision)"
- `model.py:1-4` — "MiniFASNet architecture — vendored from minivision-ai/Silent-Face-Anti-Spoofing / Original source: src/model_lib/MiniFASNet.py, Copyright (c) 2020 Minivision, MIT License."

**Disposition**: MIT strict compliance per upstream LICENSE text requires *"The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software."* The inline copyright is the "copyright notice" half; the missing full ~10-line MIT permission notice text is the "permission notice" half.

**Pre-P1 Bundle 2.X follow-up FILED**: add `core/_minifasnet/LICENSE` with verbatim MIT text from upstream `minivision-ai/Silent-Face-Anti-Spoofing/LICENSE`. Trivial fix (1 new file, ~10 lines). Architect commits to filing Bundle 2.X spec at next architect-side cycle slot — OR folding into Bundle 2 closure if scope-expansion is preferred. **Defer adjudication to user**: see closure-narrative TODO list.

**Bundle 2 scope unchanged**: Bundle 2 doesn't touch `core/_minifasnet/` paths. Plan v1 §10 known-limitation #2 updated to reflect verified state (not just hypothetical).

---

## §12 Standing by for auditor Plan v1 verdict

If CLEAN (0 PIs) → OPTIONAL-Plan-v2 path activates; Plan v1 ships to developer for Phase 4 implementation; cycle becomes 3-artifact; **20th OPTIONAL-Plan-v2 proof case** locks at closure.

If PIs surface → Plan v2 absorbs; cycle escalates to 4-artifact.

Architect's Plan v1 confidence: HIGH. Both PIs were internal-consistency arithmetic items absorbed verbatim. All 5 auditor-RATIFIED leans + 3 Phase-0-LOCKED decisions preserve. No structural surprises expected at Plan v1 review.

---

**Filed**: 2026-05-28
**Architect**: Claude
**Forwarded to**: Auditor (external)
