# Pre-P1 Bundle 2 — Governance Phase 0 Audit (2026-05-28)

**Cycle**: Pre-P1 must-fix Bundle 2 (Governance)
**Item**: MF2 (Apache 2.0 LICENSE + GOVERNANCE.md + SPDX headers + supporting governance docs)
**Discipline**: Strict-mode, OPTIONAL-Plan-v2 path candidate
**Architect**: Claude
**Auditor**: External
**Predecessor**: Pre-P1 Bundle 1 CLOSED 2026-05-28 (CI gate GREEN, 2083/2095 tests passing)

---

## §0 Procedural commitments

Carried from Bundle 1 §0 verbatim:

1. **Path C grep-verify discipline applied at closure-narrative drafting time** (production code + memory file paths + MEMORY.md index entries + `to_be_checked.md` via PowerShell fresh-disk read).
2. **Cross-path memory-file discipline** applied to any new memory file landing this cycle (BOTH paths).
3. **Closure-audit verdict forwarding** to auditor for explicit ratification BEFORE declaring CLOSED.
4. **Multi-discipline preventive convergence sub-rule elevation candidacy** — Bundle 1 closure banked 7 preventives + STRONGLY WARRANTED. Bundle 2 closure-audit is the next elevation candidacy event if convergence pattern repeats.

---

## §1 Pass-1 grep-verified findings

### §1.1 Current state — zero governance artifacts

Verified via Glob + Grep 2026-05-28:

| Artifact | Status | Notes |
|---|---|---|
| `LICENSE` (or `LICENSE.md`, `LICENSE.txt`) | ✗ ABSENT | Glob returns only `venv/Lib/site-packages/*/LICENSE` (third-party deps) + `dog-ai-dashboard/node_modules/*/LICENSE`. No top-level. |
| `GOVERNANCE.md` | ✗ ABSENT | — |
| `CODE_OF_CONDUCT.md` | ✗ ABSENT | — |
| `CONTRIBUTING.md` | ✗ ABSENT | — |
| `NOTICE` | ✗ ABSENT | Apache 2.0 §4(d) requires distributing a NOTICE file when one exists in source distributions |
| `COPYING` | ✗ ABSENT | (GPL convention; we'd use LICENSE under Apache) |
| SPDX-License-Identifier in production source | ✗ ABSENT | 3 matches found, all in `karaos-org-discussions/00-CEO-FINAL-P1-PLAN-2026-05-27.md` (1) and `06-sundar-standard-playbook-2026-05-27.md` (2) — external audit docs only. Zero in core/, pipeline.py, tools/, tests/. |
| README.md license mention | ✗ ABSENT | Grep returns no matches |
| SETUP.md license mention | ✗ ABSENT | Grep returns no matches |

**Verdict**: full greenfield governance setup. Bundle 2 is purely additive — zero conflict with existing files.

### §1.2 Source-file inventory for SPDX scope

| Path | File count (approx) | SPDX scope (Q4 ADJUDICATED) |
|---|---|---|
| `core/*.py` | ~40 | ✅ IN SCOPE (production runtime) |
| `pipeline.py` | 1 | ✅ IN SCOPE |
| `enroll.py`, `delete_person.py`, `audit_person.py` | 3 | ✅ IN SCOPE |
| `tools/*.py` | ~10 | ✅ IN SCOPE |
| `bootstrap/classifier/*.py` | ~6 | ✅ IN SCOPE (production tooling) |
| `tests/*.py` | ~200 | ✅ IN SCOPE (REUSE compliance; people fork test code) |
| `.github/workflows/*.yml` | 4 | ✅ IN SCOPE (YAML `#` comments) |
| `pytest.ini`, `requirements.txt` | 2 | ❌ EXCLUDED (config; line-comment syntax inconsistent across these files) |
| `docs/architecture/CHAPTER_*.md` | 19 | ❌ EXCLUDED (markdown docs; LICENSE covers implicitly per standard convention) |
| `dog-ai-dashboard/*` (Next.js app) | ~100 | ❌ EXCLUDED — separate sub-component; deferred to Pre-P1 Bundle 2.X follow-up |

**Q4 ADJUDICATED at Phase 0**: Production + tests + workflows for the Python backend = **~260 files**. Markdown docs covered by LICENSE alone. Dashboard sub-component deferred. Rationale: REUSE compliance is a real OSS reputational signal; tests are part of the repo people read/fork, clear license helps them; mechanical cost is one script run; sets the convention permanently and avoids a future churn event.

### §1.3 Apache 2.0 specifics

Reference: https://www.apache.org/licenses/LICENSE-2.0

Standard requirements when shipping Apache 2.0:
- **LICENSE file**: full Apache 2.0 license text (~11 KB)
- **NOTICE file**: copyright holder line + any "required" third-party attributions
- **Per-file header** (RECOMMENDED, not required): boilerplate Apache header OR SPDX short-form (`SPDX-License-Identifier: LicenseRef-KaraOS-Proprietary`). Apache prefers the boilerplate; SPDX short-form is the modern compact alternative (REUSE Software spec) and is increasingly accepted.

**Architect lean**: SPDX short-form headers (more compact, machine-readable, REUSE-compliant). One-liner per file:
```python
# SPDX-License-Identifier: LicenseRef-KaraOS-Proprietary
# SPDX-FileCopyrightText: 2025-2026 <copyright_holder>
```

### §1.4 Copyright attribution — Q5 ADJUDICATED at Phase 0

**Q5 ADJUDICATED**: `SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors` (Kubernetes / Google-pattern collective attribution).

Rationale:
- Forward-compatible with multiple contributors (no rewrite when first external PR lands)
- Doesn't expose personal email in every source file (Jagan's email stays in commit metadata only)
- "The X Authors" is the widely-understood OSS convention for collective copyright (Kubernetes: "The Kubernetes Authors"; Go: "The Go Authors"; Rust: "The Rust Project Developers")
- Apache 2.0-compatible; doesn't require a Contributor Agreement (CLA) to function
- Git commit log preserves individual contributor attribution → personal trace is preserved

Deferred: separate `AUTHORS.md` listing file is NOT created in Bundle 2. File can be added when the first external contributor lands; until then, "git log --format='%aN' | sort -u" is the authoritative attribution source.

---

## §2 D-decisions surfaced

### D1 — Apache 2.0 LICENSE file

Drop standard Apache 2.0 license text at repo root as `LICENSE` (no extension; matches convention for `apache/*` projects on GitHub).

Source: https://www.apache.org/licenses/LICENSE-2.0.txt

### D2 — NOTICE file

Apache 2.0 §4(d): "If the Work that You distribute or publish, that in whole or in part contains or is derived from the Work or its Derivative Works, and the Work that You distribute or publish has a NOTICE text file, You must include a copy of the NOTICE text file..."

Architect commits to including a NOTICE file from day 1 (forward-looking — once we use Apache-licensed derivative works, the NOTICE chain matters).

**Content shape**:
```
KaraOS
Copyright 2025-2026 KaraOS Contributors

This product includes software developed at HungryFingerss/Cognitive-System
(https://github.com/HungryFingerss/Cognitive-System).

Portions of this software are derived from:
- pyannote.audio (MIT License) — fork at HungryFingerss/pyannote-audio with dog-ai patches
- speechbrain (Apache License 2.0) — fork at HungryFingerss/speechbrain with dog-ai patches
- MiniFASNet (MIT License) — vendored at core/_minifasnet/ (model architecture from minivision-ai/Silent-Face-Anti-Spoofing)
```

### D3 — GOVERNANCE.md (Q2 ADJUDICATED at Phase 0)

**Q2 ADJUDICATED**: BDFL with documented 3-phase evolution path. Specifically:

- **Phase 1 (current — sole maintainer)**: Jagannivas is BDFL (Benevolent Dictator For Life). Sole final-decision authority on architecture, strategy, and merge approval. Fast decisions; clear authority chain; well-suited for early-stage one-person project.
- **Phase 2 (triggers when 3+ regular external contributors arrive)**: Maintainer + Committers model. Regular contributors get elevated to "committer" status (can merge PRs in their domain area without per-PR Jagan review). Jagan retains final authority on architecture decisions + strategic direction. Disputes between committers escalate to Jagan.
- **Phase 3 (triggers when 10+ committers, mature project)**: Steering committee, PEP-8016-style. Jagan steps back to "Emeritus" or rotating-member status; strategic decisions made by elected committee. Documented evolution path matters for OSS recruitment — contributors want to know they have a path to influence.

**Content sketch for GOVERNANCE.md**:
- Project philosophy (Layer D middleware positioning, 3-5 year horizon per CEO decisions doc)
- Current governance phase (Phase 1: BDFL — Jagannivas)
- Decision-making process (Issues + PRs; significant architecture/strategy changes require RFC-style discussion before implementation)
- Phase 2 + Phase 3 evolution triggers + criteria (so contributors see the trajectory)
- Contributor expectations (code review, tests, documentation, strict-mode discipline for spec-track work)
- Escalation path (open an issue tagged `governance`; direct contact via email/maintainer as last resort)
- Trademark/branding note (KaraOS name is owned by the project; downstream forks should rename)

### D4 — CODE_OF_CONDUCT.md

Standard Contributor Covenant v2.1 (industry-standard, https://www.contributor-covenant.org/). Architect lean: ship as-is from the template with minimal customization (project name + maintainer contact). Required for Apache Software Foundation-style positioning + de facto industry standard for any project taking outside contributions.

### D5 — CONTRIBUTING.md

Lightweight contribution guide. **Architect lean**: include but keep minimal — explain how to clone, install (link to SETUP.md), run tests (`pytest`), submit a PR. Reference the spec-first review cycle discipline + CLAUDE.md for project-side architectural conventions.

### D6 — SPDX-License-Identifier headers across Python backend (Q4 ADJUDICATED at Phase 0)

**Scope locked at Q4 ADJUDICATED**: `core/*.py` + `pipeline.py` + `enroll.py` + `delete_person.py` + `audit_person.py` + `tools/*.py` + `bootstrap/classifier/*.py` + `tests/*.py` + `.github/workflows/*.yml` ≈ **~260 files**.

Excluded: `pytest.ini`, `requirements.txt` (config files), `docs/architecture/CHAPTER_*.md` (markdown — LICENSE covers), `dog-ai-dashboard/` (separate Next.js sub-component → Pre-P1 Bundle 2.X follow-up).

Header format (2 lines, Q5 ADJUDICATED):
```python
# SPDX-License-Identifier: LicenseRef-KaraOS-Proprietary
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
```

For `.yml` workflow files, identical syntax (YAML `#` comments).

For `.py` files: place AFTER the module docstring if one exists, OR at line 1 if not. (Per REUSE Software spec + standard practice across `apache/airflow`, `kubernetes/kubernetes`, `golang/go`. Docstring stays the first thing the reader sees; SPDX is metadata for tooling.)

**Mechanical-extraction discipline locked** (mirrors P0.8 / P0.9.2 precedent): D6 is a script-driven mechanical pass. Architect commits to writing a single idempotent Python script (`tools/add_spdx_headers.py`) that:
- Walks the in-scope file list
- Detects existing header (idempotency check — re-runs are no-ops)
- Detects docstring position (insert after closing `"""` if present)
- Inserts 2-line header
- Reports added/skipped counts at exit
- Has its own test in `tests/test_spdx_headers_invariant.py` (the A6.x anchor)

### D7 — REMOVED (was: SPDX headers in test files)

Q4 ADJUDICATED merges D6 + D7 — test files are now IN SCOPE for D6. Old D7 dropped. Subsequent D-decisions renumber down by 1.

### D7 — README.md license + governance mention (was D8; renumbered after old D7 merged into D6)

Append a section at README.md tail:
```markdown
## License & Governance

KaraOS is licensed under the **Apache License 2.0** (see [LICENSE](LICENSE) and [NOTICE](NOTICE)).

Governance model documented in [GOVERNANCE.md](GOVERNANCE.md). Contributor onboarding in [CONTRIBUTING.md](CONTRIBUTING.md). Community standards in [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
```

### Cross-D shipping order

**Architect lean**: D1 → D2 → D3 → D4 → D5 → D7 → D6.

Rationale: D1 (LICENSE) is the structural anchor — everything else references it. D2 (NOTICE) lives next to LICENSE. D3-D5 are project-root .md files. D7 is the README pointer to them. D6 (SPDX headers across ~260 files via script-driven mechanical pass) is the heaviest mechanical work — last so the header text can verbatim-reference what's in LICENSE.

---

## §3 Anchor count estimate (Q5 MID-RANGE methodology)

**Per-D estimate**:

| D-decision | Anchor type | Mid count | NARROW band [±15%] |
|---|---|---|---|
| D1 — LICENSE file | source-inspection: file exists + opens with "Apache License" + version 2.0 marker | 1 | [0.85, 1.15] |
| D2 — NOTICE file | source-inspection: file exists + KaraOS + 3-attribution lines for pyannote/speechbrain/MiniFASNet | 1 | [0.85, 1.15] |
| D3 — GOVERNANCE.md | source-inspection: 5 required-content checkpoints (philosophy + BDFL + decision-process + contributor expectations + escalation) | 1 | [0.85, 1.15] |
| D4 — CODE_OF_CONDUCT.md | source-inspection: Contributor Covenant 2.1 marker + maintainer contact line | 1 | [0.85, 1.15] |
| D5 — CONTRIBUTING.md | source-inspection: clone+install+test+PR instructions present + SETUP.md cross-ref | 1 | [0.85, 1.15] |
| D6 — SPDX headers in production source | structural parametrize: every file in scope contains the 2-line header in expected position | 2 | [1.7, 2.3] |
| D7 — README license/governance section | source-inspection: 4 doc links + Apache 2.0 mention | 1 | [0.85, 1.15] |

**Total Q5 mid**: 8 logical anchors.
**NARROW band [±15%]**: [6.8, 9.2].
**Q5 LOCK at mid 8 with ±15% tolerance**.

D6 anchor breakdown (the heaviest):
- A6.1 (source-inspection): list-of-expected-files-vs-list-of-files-with-headers — zero unaccounted files in scope
- A6.2 (structural parametrize): each file's header lands in correct position (top-of-file OR after module docstring; not mid-file)

**Closure-projection band table** (per `Explicit-closure-honest-count-commitment` discipline):

| Closure-actual | % vs mid | Reading | Doctrine consequence |
|---|---|---|---|
| 7 anchors | -12.5% | ON-TARGET (within NARROW band) | doctrine bumps |
| **8 anchors (Q5 LOCK)** | **0%** | exact mid | `### Phase-0-granular-decomposition-enables-accurate-estimates` 31 → 32 supporting; **11th consecutive 0%-streak rebuild** under `Doctrine-prediction-precision-improving-over-arc` sub-observation |
| 9 anchors | +12.5% | ON-TARGET | doctrine bumps |
| 10 anchors | +25% | SLIGHT-DRIFT-UP | Within ±30%; doctrine holds |
| ≥11 anchors OR ≤6 anchors | ≥+37.5% / ≤-25% | FALSIFICATION TRIGGER | falsification clause activates IF wrong-premise root cause |

**Plan v1 §4 honest-count commitment**: closure narrative MUST report closure-actual against mid 8 explicitly with %-delta + doctrine consequence.

---

## §4 Cross-spec impact

### §4.1 Files affected (per D-decision)

| D | New files | Modified files | Approx total |
|---|---|---|---|
| D1 | LICENSE (project root) | — | 1 new |
| D2 | NOTICE (project root) | — | 1 new |
| D3 | GOVERNANCE.md (project root) | — | 1 new |
| D4 | CODE_OF_CONDUCT.md (project root) | — | 1 new |
| D5 | CONTRIBUTING.md (project root) | — | 1 new |
| D6 | — | ~60 files (core/ + pipeline.py + ... + bootstrap/classifier/) | 60 edits |
| D7 | — | README.md (one section appended) | 1 edit |

**Total scope**: 5 new files + ~61 file edits = ~66 changes.

### §4.2 No git ripple

Adding LICENSE and the .md files to project root doesn't conflict with `.gitignore` (the `/*.md` rule has a whitelist for top-level docs; LICENSE/NOTICE without extension are auto-tracked). Per-file SPDX headers are line-level edits, no path moves.

### §4.3 Bundle 3-5 dependencies

Bundle 3 (Critical bugs MF4+MF5) is code-only, no governance dependency.
Bundle 4 (Observability+concurrency MF6+MF9) is code-only.
Bundle 5 (Contract typing MF7+MF8) is code-only.

**All 3 remaining bundles can start in parallel after Bundle 2 closes — no cross-bundle dependencies.** Or sequentially per Path A locked at CEO decisions doc.

### §4.4 P1 strategic dependency

CEO decisions doc §5: "Apache 2.0 LICENSE + GOVERNANCE.md + SPDX headers land before any P1 spec references open-source positioning." Bundle 2 is the **governance prerequisite** for the P1 cycle's Layer D middleware framing. Without Bundle 2 landed, P1 specs would reference a "future open-source project" — vaporware framing. Bundle 2 makes the open-source positioning real.

---

## §5 Discipline counts to bump (per locked +1-per-artifact convention)

**Pre-Bundle-2 baselines** (verified at Bundle 1 closure 2026-05-28):

| Discipline | Pre-Bundle-2 | After Phase 0 | After Plan v1 | After closure |
|---|---|---|---|---|
| Strict-industry-standard mode applications | 114 | 115 | 116 | 117 (3-artifact OPTIONAL-Plan-v2 cycle) |
| Strict-industry-standard mode closures | 33 | 33 | 33 | 34 |
| Spec-first review cycle | 123 | 124 | 125 | 126 |
| `### Grep-baseline-before-drafting` | 81 | 82 | 83 | 84 |
| Cross-cycle-handoff transparency | 84 | 85 | 86 | 87 |
| Spec-time grep-verification | 91 | 92 | 93 | 94 |
| `### Twin-filename-pitfall-prevention` | 32 | — | — | 33 (preventive — `tests/pre_p1_bundle2_*.md` cleanly disambiguated) |
| `### Architect-reads-production-code-before-sign-off` | 31 | — | — | 32 (closure-audit event) |
| Auditor-Q5-estimates-trail-grep | 37 | — | — | 38 banked closures (at projected 0% ON-TARGET) |
| Deferred-canary strategy | 35 | — | — | 36 applications |

**Conditional doctrine firings at closure**:
- `### Phase-0-granular-decomposition-enables-accurate-estimates`: 31 → 32 supporting at closure IF Q5 lands within NARROW band [6.8, 9.2]
- `Doctrine-prediction-precision-improving-over-arc` sub-rule: 10-streak → 11-streak IF closure-actual = 8 exact
- `### Multi-discipline-preventive-convergence` sub-rule (CANDIDATE ELEVATION at Bundle 1 closure): if Bundle 2 also applies 5+ preventives, elevation candidacy strengthens to 2 consecutive instances

---

## §6 Open questions for auditor

**Q1** (D2 scope — NOTICE attributions): include all 3 vendored attributions (pyannote/speechbrain/MiniFASNet) in NOTICE on day 1, or only the Apache-licensed ones (speechbrain only)? Architect lean: ALL THREE — proactive transparency about derivative-work components even if their licenses (MIT) don't strictly require NOTICE attribution.

**Q2** (D3 GOVERNANCE model) — **ADJUDICATED at Phase 0**: BDFL with documented 3-phase evolution path. See §2 D3 for full rationale + content sketch. Phase 1 (current) = Jagannivas BDFL; Phase 2 (triggers at 3+ regular contributors) = Maintainer + Committers; Phase 3 (10+ committers) = Steering committee PEP-8016-style.

**Q3** (D4 CODE_OF_CONDUCT): Contributor Covenant v2.1 as-is, or custom? Architect lean: Contributor Covenant 2.1 verbatim (industry standard; minimal customization = just project name + maintainer contact).

**Q4** (D6 SPDX scope) — **ADJUDICATED at Phase 0**: production + tests + workflows for the Python backend ≈ 260 files. Excludes config files (pytest.ini, requirements.txt), markdown docs (LICENSE covers), and `dog-ai-dashboard/` (separate sub-component → Pre-P1 Bundle 2.X follow-up). See §1.2 for full scope table + rationale.

**Q5** (D6 copyright attribution) — **ADJUDICATED at Phase 0**: `SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors` (Kubernetes / Google-pattern collective attribution). See §1.4 for full rationale. Defers separate `AUTHORS.md` file to first-external-contributor trigger.

**Q6** (cross-D order): D1 → D2 → D3 → D4 → D5 → D7 → D6 shipping order? Architect lean: yes (LICENSE first as structural anchor; D7 README pointer; D6 SPDX-script-pass last as the heaviest mechanical work).

**Q7** (OPTIONAL-Plan-v2 path): if Plan v1 clears 0 PIs, ship to developer with no Plan v2? Architect lean: YES — Bundle 2 is governance-doc creation with no behavioral surface; same shape as Bundle 1 expected (but Bundle 1 escalated to 4-artifact due to Phase 0 measurement error caught at developer Pass-3). For Bundle 2: no measurement-prone work (LICENSE text is verbatim public-domain; file counts are grep-verifiable upfront; D6 mechanical pass via idempotent script removes the human-error class).

**Q8** (D6 hash-header position in `.py` files): top-of-file BEFORE module docstring, or AFTER module docstring? Architect lean: AFTER module docstring (REUSE Software spec recommends — docstring stays the first thing the reader sees; SPDX is metadata for tooling).

---

**Adjudication summary for auditor**:
- 3 questions LOCKED at Phase 0 (Q2 + Q4 + Q5) — see §1.2 / §1.4 / §2 D3+D6 for rationale
- 5 questions OPEN for auditor adjudication (Q1, Q3, Q6, Q7, Q8) with explicit architect leans

---

## §7 Architect closure-projection commitment

Per `Explicit-closure-honest-count-commitment` discipline:

- IF closure-actual = 8 exact: doctrine `### Phase-0-granular-decomposition` BUMPS 31 → 32 supporting + sub-observation `Doctrine-prediction-precision-improving-over-arc` extends 11th consecutive 0%-streak.
- IF closure-actual ∈ {7, 9, 10}: doctrine HOLDS at 31 supporting; sub-observation streak interrupted; honest closure-actual reading reported.
- IF closure-actual ≥ 11 OR ≤ 6: FALSIFICATION-WATCH activates.

Architect publicly commits to honest closure-actual reporting at Phase 7 closure-narrative drafting regardless of which band falls.

---

## §8 Architect Pass-1 grep clearance

Per `### Grep-baseline-before-drafting` doctrine + 3-part Pass-2 grep operational rule (locked at P0.S10 Plan v4):

Pass-1 baselines verified 2026-05-28 (this audit document):
1. **Symbol-name-uniqueness grep** ✓ — `LICENSE` / `GOVERNANCE.md` / `CODE_OF_CONDUCT.md` / `CONTRIBUTING.md` / `NOTICE` / `SPDX-License-Identifier` all unambiguously identify governance artifacts (zero collision with existing project content).
2. **Behavioral semantic verification** ✓ — verified 3 SPDX matches in `karaos-org-discussions/` are docstring/audit-narrative mentions only, NOT actual source-file headers. Production source surface is genuinely empty.
3. **Symmetric verification (additive class)** ✓ — Bundle 2 work is purely additive (new files + appended line-level headers). No "delete" or "rename" classes. Reject class N/A.

Plan v1 §1 Pass-2 grep will refresh against any new file landings between this audit and Plan v1 drafting.

---

## §9 Procedural commitments (closure-audit)

All 6 procedural commitments preserved from Bundle 1 §9.

**NEW for Bundle 2 — no CI evidence event required**: Bundle 2 is governance-doc creation. No code path changes. CI green from Bundle 1 closure already establishes the baseline. The next CI run will fire automatically on commit + pass (governance files don't change test behavior).

If user wants belt-and-braces CI re-run after Bundle 2, that's a closure-time judgment call. Default: skip the explicit `workflow_dispatch` since there's no functional change to validate.

---

## §10 Recommended auditor verdict shape

```
VERDICT: ACCEPT / ACCEPT WITH PI / BLOCKED

For ACCEPT or ACCEPT WITH PI:
  - Approve Q5 LOCK at mid 8 ± 15% NARROW band
  - Approve cross-D shipping order (D1 → ... → D6) or override
  - Adjudicate Q1-Q8 with explicit lean per question
  - Identify any §1 grep-verified findings architect missed
  - Decide OPTIONAL-Plan-v2 eligibility (likely; no measurement-prone work)

For BLOCKED:
  - List Precision Items (PIs) with exact §reference
  - Specify which D-decision needs absorption at Plan v1
```

---

Standing by for auditor verdict on Phase 0.

**Architect closure-audit commitment**: Plan v1 will absorb auditor PIs at §1 (revised state-table if scope shifts) + §2 (revised D-decisions per ratified leans) + §3 (Q5 re-lock with auditor-final mid value). Closure-narrative honest-count commitment honored regardless of which band Q5 lands in.

---

**Filed**: 2026-05-28
**Architect**: Claude
**Forwarded to**: Auditor (external)
