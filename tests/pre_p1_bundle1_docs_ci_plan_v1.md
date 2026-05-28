# Pre-P1 Bundle 1 — Docs + CI Plan v1 (2026-05-28)

**Cycle**: Pre-P1 must-fix Bundle 1 (Docs+CI)
**Predecessor**: `tests/pre_p1_bundle1_docs_ci_audit.md` (Phase 0, ACCEPT WITH 2 PIs)
**Discipline**: Strict-mode, OPTIONAL-Plan-v2 path candidate
**Architect**: Claude
**Auditor**: External (Phase 0 verdict in `info.md` 2026-05-27)

---

## §0 Procedural commitments

Carried from Phase 0 §0 verbatim. Adding 3rd Pass-2 grep operational rule application + LINE-REF-DRIFT preventive at Plan v1 §1.1.

PI #1 absorption + PI #2 absorption + Q1-Q7 all RATIFIED leans applied below.

---

## §1 PI absorption + Pass-2 grep refresh

### §1.1 PI #1 absorption — LINE-REF-DRIFT corrected

**Phase 0 §1.1 + §1.4 claimed**: stale `P1.P1 — No CI config` entry at **line 113**.
**Auditor's Pass-2 grep**: stale entries at **lines 1396 AND 1397** (TWO instances).
**Architect Pass-2 grep verified 2026-05-28**:

```
1396:- **P1.P1 — No CI config**: no `.github/workflows/` directory exists. (carried forward)
1397:- **P1.P1 — No CI config**: no `.github/workflows/` directory exists. `test_no_unannotated_silent_excepts_in_production_code` and `test_no_layering_violations_in_pipeline` are designed to be PR-blocking but have no CI runner to enforce it. Create a minimal GitHub Actions workflow that runs `pytest` on every PR.
```

Two stale facts both falsified by current state:
- Claim "no `.github/workflows/` directory exists" — DIRECTORY EXISTS (4 workflow files verified §1.1 Phase 0)
- Claim "have no CI runner to enforce it" — FAST.YML RUNS structural-invariant tests on every PR (verified §1.1 Phase 0)

Plan v1 PI #1 absorption applied at §2 (D1.b restated) and §3 (A2 anchor scope).

**Sub-shape banking commitment** (per `feedback_pass_2_grep_caught_real_gap_subshape.md`): 4th LINE-REF-DRIFT sub-shape instance (after P0.R9 caught + P0.R10 preventive + P0.R12-R15 preventive). Continues BOTH-modes maturation. Banks at Bundle 1 closure under `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine track record extension.

### §1.2 PI #2 absorption — Pass-2 grep exhaustive 24-file enumeration

**Phase 0 §4.1 claimed**: "~10-30 references across spec + plan files" with 6 enumeration categories.
**Auditor's Pass-2 grep**: 24 distinct files with .gitignore + SETUP.md categories missed.
**Architect Pass-2 grep verified 2026-05-28**: 24 files, full enumeration below.

#### Active-doc surfaces (REQUIRES MUTATION at D3 execution)

| # | File | Reference shape | Update action |
|---|---|---|---|
| 1 | `CLAUDE.md` | "Tests guard every invariant" narrative section + Architecture-doc-list references | Replace with `docs/architecture/` references; preserve historical context |
| 2 | `.gitignore` | Line 127: comment listing tracked docs; Line 144: `!/everything_about_system.md` whitelist | Add `docs/architecture/` to comment + new whitelist `!/docs/architecture/*.md` (or verify `docs/` is unaffected by `/*.md` ignore rule) |
| 3 | `SETUP.md` | Line 71: "see `everything_about_system.md` Part XXXI" (stale Roman numeral); Line 85: "Architecture docs (CLAUDE.md, everything_about_system.md, KARAOS guides)"; Line 108: "see `everything_about_system.md` §195" (section doesn't exist in current numbering) | Lines 71 + 108 redirected to actual chapter file + section number; Line 85 update to reference `docs/architecture/` |
| 4 | `everything_about_system.md` (itself) | TARGET of split | REPLACED with thin redirect (<50 lines + DO-NOT-WRITE-HERE notice) |

**SETUP.md pre-existing doc bugs** (Part XXXI + §195) noted but NOT a Bundle 1 fix obligation — these stale refs predate the split work. Plan v1 §2 D3 scope: redirect lines 71 + 108 to a SENSIBLE chapter (best-match for pyannote patches likely Chapter 5 covering §30-§35 sections incl. §33 diarization). Lines 71 + 108 get updated as part of the split-aware redirect pass; the underlying stale-section-reference issue stays a known doc-bug logged at §10 Known Limitations.

#### Spec/Plan archive surfaces (SEALED — no mutation)

Architect closure-audit discipline: closed plan/audit artifacts are sealed historical records. The thin redirect at `everything_about_system.md` catches any future reader of these files who follows the reference.

| Category | Count | Files |
|---|---|---|
| `karaos-org-discussions/` (CEO + 4 analyst, 2026-05-27 strategic) | 5 | 00-CEO-FINAL + 01-techanalyst1 + 03-skeptic1 + 05-elon + 06-sundar |
| `tests/` (P0.S1 plan v1+v2 + validation_runbook) | 3 | p0_s1_plan_v1.md + p0_s1_plan_v2.md + p0_s1_validation_runbook.md |
| `tests/` (P0.S7 family — audit + plans + spec) | 4 | p0_s7_audit.md + p0_s7_plan_v1.md + p0_s7_plan_v2.md + p0_s7_2_spec.md |
| `tests/` (P0.S7.D-B audit + plan) | 2 | p0_s7_db_audit.md + p0_s7_db_plan_v1.md |
| `tests/` (P0.S7.D-D audit + plan) | 2 | p0_s7_dd_audit.md + p0_s7_dd_plan_v1.md |
| `tests/` (P0.R4 audit + plan) | 2 | p0_r4_process_supervisor_audit.md + p0_r4_process_supervisor_plan_v1.md |
| `tests/` (canary_week runbook + Bundle 1 self-refs) | 2 | canary_week_2026-05-26.md + pre_p1_bundle1_docs_ci_audit.md (mine) |

**Total**: 5 (karaos) + 3 + 4 + 2 + 2 + 2 + 2 = 20 sealed archive files.

**Grand total**: 4 active-doc mutations + 20 sealed archive files = 24 files referencing `everything_about_system.md`. Matches auditor's grep count exactly.

**Sub-shape banking commitment**: 9th instance of `### Pre-audit-quantifier-precision-refined-by-grep` under SURFACE-CASCADE-AXIS sub-shape (caught-real-gap continuation, NOT elevation). Banks at Bundle 1 closure under doctrine track record extension.

### §1.3 §1.3 cluster table refined (no change from Phase 0)

12 natural clusters per Phase 0 §1.3 stand. Auditor Q3 RATIFIED fine-split (12 chapters).

Chapter file naming convention:
- `docs/architecture/CHAPTER_01_introduction_and_tech_stack.md` (§1-§9)
- `docs/architecture/CHAPTER_02_lifecycle_and_pipeline_states.md` (§10-§15)
- `docs/architecture/CHAPTER_03_async_and_vision_basics.md` (§16-§29)
- `docs/architecture/CHAPTER_04_audio_and_stt_tts.md` (§30-§35)
- `docs/architecture/CHAPTER_05_face_voice_galleries.md` (§36-§46)
- `docs/architecture/CHAPTER_06_sessions_and_evidence.md` (§47-§58)
- `docs/architecture/CHAPTER_07_reconciler_and_conversation_turn.md` (§59-§71)
- `docs/architecture/CHAPTER_08_prompt_blocks_and_brain_agents.md` (§72-§99)
- `docs/architecture/CHAPTER_09_dispute_tool_privileges_logging.md` (§100-§118)
- `docs/architecture/CHAPTER_10_schemas_tests_dashboard.md` (§119-§140b)
- `docs/architecture/CHAPTER_11_future_work_reference_tables.md` (§141-§149)
- `docs/architecture/CHAPTER_12_privacy_rooms_recent_work.md` (§150-§176)

Plus parent index: `docs/architecture/README.md` with one-line summary per chapter + cross-section navigation table.

### §1.4 Section-numbering preservation

Each chapter file preserves the original H2 section numbers (§1, §10, §59, etc.). Chapter file's TOC uses the same numbering as the source. A future reader following "see `docs/architecture/CHAPTER_07_*.md §59" lands at the same section content as the original "everything_about_system.md §59". Backward-compatible reference semantics.

---

## §2 D-decisions refined (PI absorption applied)

### D1 — MF1 — CI verification + CLAUDE.md remediation

**Sub-decisions revised**:

- **D1.a** (UNCHANGED): Architect declares MF1 verification complete per §1.1 Phase 0 grep evidence. **Plus**: user-triggered `workflow_dispatch` on `slow.yml` recommended (Q1 RATIFIED) — architect commits to confirming green/red status as Phase 4 evidence event before declaring Bundle 1 CLOSED.

- **D1.b** (REVISED per PI #1): Remove BOTH stale P1.P1 entries at CLAUDE.md lines 1396 + 1397. Consolidate into ONE new narrative paragraph confirming P0.0 CI scaffold is live + lists the 4 informational-mode gates as deferred-tightening candidates (NOT P1 scope; flagged for post-P1 follow-up). Net effect: 2 stale lines removed → 1 new narrative paragraph added.

- **D1.c** (SUBSUMED into D1.b): The "new narrative" sub-decision from Phase 0 §2 D1.c is now the body of the D1.b consolidation. No separate edit; one consolidated change.

### D2 — MF3 — CLAUDE.md Project Overview Layer D rewrite

**Scope UNCHANGED from Phase 0 §2 D2** (Q2 RATIFIED — only Project Overview, not Architecture section).

**New content shape** (verbatim phrases architect commits to including):

1. **Lead sentence**: "KaraOS is the Layer D cognitive runtime middleware for embodied AI — the layer above motor control and below natural-language orchestration."
2. **Two-stack architecture explicit**: "Two stacks ship in tandem: (1) the companion stack — today's behavior, AI robot dog reference application; (2) the robotics stack — embodied runtime landing in P1 with TurtleBot4 (Gazebo simulator) as reference."
3. **3-5 year horizon claim**: "The runtime targets a 3-5 year market-defining horizon as the standard middleware for any embodied AI agent."
4. **Companion description** (preserved from current): "Sees faces → identifies people → greets by name → holds voice conversations → remembers people across sessions."
5. **Robotics description**: "Commitment store + scheduler + policy engine + verifier registry + adapter SDK + MCP server. Robot-agnostic via the adapter SDK."
6. **Practical references PRESERVED VERBATIM**: dev machine + production target + project root + run + venv + tests lines unchanged.

Phase 0 file said "Tests: `pytest` (1273 passing, ...)" — at Plan v1 drafting time 2026-05-28, actual count is ~2810 passing per CLAUDE.md top-of-file banner. Architect commits to updating to the latest accurate count at D2 execution time (NOT today's date, but at Phase 4 closure when fresh count is verified via `pytest --collect-only`).

### D3 — MF10 — everything_about_system.md split (PI #2 expanded scope)

**Scope EXPANDED per PI #2**:

- **D3.a** (split files): create 12 chapter files under `docs/architecture/` per §1.3 cluster table + 1 parent index README.
- **D3.b** (redirect): replace `everything_about_system.md` content with thin redirect (~30 lines: redirect notice + chapter list with one-line summaries + DO-NOT-WRITE-HERE notice).
- **D3.c** (active-doc ripple — NEW per PI #2): update `.gitignore` (whitelist entries + comment block) + `SETUP.md` (3 reference sites at lines 71, 85, 108).
- **D3.d** (cross-references — UNCHANGED): CLAUDE.md `§NNN` references redirected to `docs/architecture/CHAPTER_NN §NNN`. Architect commits to maintaining section-number stability so the redirect is a simple file-path substitution.

**Sealed archive files** (20 listed at §1.2): NOT MUTATED. Thin redirect catches downstream readers.

### Cross-D shipping order

**UNCHANGED from Phase 0** (Q5 RATIFIED): **D3 → D2 → D1**.

Within D3: D3.a → D3.b → D3.c → D3.d (build chapters first; replace source with redirect; update active docs; verify cross-references).

---

## §3 Q5 LOCK (mid 11 unchanged, A5 scope expanded)

**Q5 LOCK at mid 11 anchors UNCHANGED** (Q6 RATIFIED with A5 parametrize fan-out expansion per Q5 review note).

**A5 scope expansion per PI #2**: "A5 (structural): zero broken cross-references — every `§NNN` reference in **CLAUDE.md + `.gitignore` + `SETUP.md` + the thin redirect in `everything_about_system.md`** resolves to a valid chapter+section pair." A5 becomes a parametrize fan-out across 4 active-doc surfaces (NOT 24 — sealed archive files excluded from mutation contract per §1.2). 4-file parametrize = ~4-6 pytest collections.

**Anchor breakdown finalized**:

| # | Anchor | Type | Scope |
|---|---|---|---|
| A1 | D1.b stale-line removal | source-inspection: ZERO `P1.P1 — No CI config` matches in CLAUDE.md | One CLAUDE.md grep |
| A2 | D1.b consolidated new narrative | source-inspection: new P0.0-scaffold-confirmed paragraph present | One CLAUDE.md grep |
| A3 | D2 Layer D lead sentence | source-inspection: exact verbatim "Layer D cognitive runtime middleware" | One CLAUDE.md grep |
| A4 | D2 two-stack mention | source-inspection: "companion stack" + "robotics stack" both present | One CLAUDE.md grep |
| A5 | D2 + D3 cross-ref resolution | structural parametrize (CLAUDE.md, .gitignore, SETUP.md, thin redirect): every `everything_about_system.md` reference resolves to a CURRENT valid file path | 4-file fan-out, ~4-6 pytest collections |
| A6 | D3.a chapter directory + 12 chapter files | source-inspection: `docs/architecture/` exists; 12 chapter files exist with correct names | Filesystem check |
| A7 | D3.a parent index | source-inspection: `docs/architecture/README.md` exists + links all 12 chapters | One README grep |
| A8 | D3.b thin redirect | source-inspection: `everything_about_system.md` <50 lines + contains DO-NOT-WRITE-HERE notice + chapter list | Source-inspection |
| A9 | D3.c .gitignore update | source-inspection: `.gitignore` allows new chapter paths + comment block reflects split | One .gitignore grep |
| A10 | D3.c SETUP.md update | source-inspection: SETUP.md lines 71+85+108 reference active surfaces (not stale) | SETUP.md grep |
| A11 | D3.d CLAUDE.md ref redirect | source-inspection: zero CLAUDE.md references to standalone `everything_about_system.md §NNN` (all become `docs/architecture/CHAPTER_NN §NNN` OR the redirect file ref) | CLAUDE.md grep |

**Total = 11 logical anchors. NARROW band [9.35, 12.65]. Q5 LOCK = 11.**

### Closure-projection band table (per `Explicit-closure-honest-count-commitment`)

| Closure-actual | % vs mid | Reading | Doctrine consequence |
|---|---|---|---|
| 9 anchors | -18.2% | SLIGHT-DRIFT-DOWN | Within ±30%; doctrine holds |
| 10 anchors | -9.1% | ON-TARGET (within NARROW band) | doctrine bumps |
| **11 anchors (Q5 LOCK)** | **0%** | exact mid | `### Phase-0-granular-decomposition` bumps 30 → 31 supporting; `Doctrine-prediction-precision-improving-over-arc` **10th consecutive 0%-streak (conditional on P0.S10 closing 0% — confirmed at P0.S10 closure 2026-05-27 per CLAUDE.md banner)** |
| 12 anchors | +9.1% | ON-TARGET (within NARROW band) | doctrine bumps |
| 13 anchors | +18.2% | SLIGHT-DRIFT-UP | Within ±30%; doctrine holds |
| ≥15 anchors | +36.4% | FALSIFICATION TRIGGER | falsification clause activates IF wrong-premise root cause; sub-observation streak reset only IF scope-expansion |

**Honest closure-projection note per auditor Q&A cross-doctrine sanity check** (info.md lines 64-66): the 10th consecutive 0%-streak claim was correctly CONDITIONAL at Phase 0 review time on P0.S10 closure outcome. P0.S10 has SINCE CLOSED 0% ON-TARGET at mid 8 anchors (CLAUDE.md banner line 5 confirms — 9th consecutive 0%-streak rebuild instance banked at P0.S10 closure). Bundle 1 at 11 anchors closure-actual would be 10th consecutive. Conditional resolved positively at Plan v1 drafting.

---

## §4 Cross-spec impact (PI #2 absorbed)

### §4.1 24-file ripple table (full enumeration per PI #2)

See §1.2 above for exhaustive breakdown.

**Active-doc mutations** (4 files): CLAUDE.md + .gitignore + SETUP.md + `everything_about_system.md` (becomes redirect)
**Sealed archive references** (20 files): NOT MUTATED; thin redirect catches downstream readers

### §4.2 Bundle 2-5 dependency review (no change from Phase 0)

Bundle 2 (Governance — MF2) independent of Bundle 1 docs. Bundles 3-5 code-only, no dependency. Bundle 1 + Bundle 2 can run sequentially OR parallel.

### §4.3 P0.S10/S11/S12 closure-narrative interactions

Bundle 1 closure-narrative will reference P0.S10 closure 2026-05-27 for the `Doctrine-prediction-precision-improving-over-arc` 9th → 10th streak transition. No retroactive narrative edits to P0.S10/S11/S12 closures.

---

## §5 Discipline counts (conditional restatement per auditor Q&A)

### §5.1 Baseline counts (verified at P0.S10 closure 2026-05-27 per CLAUDE.md banner)

| Discipline | P0.S10 close | After Bundle 1 Phase 0 | After Plan v1 | After closure |
|---|---|---|---|---|
| Strict-industry-standard mode applications | 110 | 111 | 112 | 113 (3-artifact cycle: Phase 0 + Plan v1 + closure = +3) |
| Strict-industry-standard mode closures | 32 | 32 | 32 | 33 |
| Spec-first review cycle | 119 | 120 | 121 | 122 |
| `### Grep-baseline-before-drafting` | 77 | 78 | 79 | 80 |
| Cross-cycle-handoff transparency | 80 | 81 | 82 | 83 |
| Spec-time grep-verification | 87 | 88 | 89 | 90 |
| `### Twin-filename-pitfall-prevention` | 31 | — | — | 32 (preventive at closure — `tests/pre_p1_bundle1_*.md` clean disambiguation) |
| `### Architect-reads-production-code-before-sign-off` | 30 | — | — | 31 (closure-audit event with explicit X → Y per `Implicit-doctrine-firings-not-narrative-tracked` sub-rule) |
| Auditor-Q5-estimates-trail-grep | 36 | — | — | 37 banked closures (0% ON-TARGET projected at mid 11) |
| Deferred-canary strategy | 34 | — | — | 35 applications (Bundle 1 entry banked in `to_be_checked.md` at closure) |

### §5.2 Conditional doctrine firings at closure

**`### Phase-0-granular-decomposition-enables-accurate-estimates`**: 30 → 31 supporting at closure IF Q5 lands within NARROW band [9.35, 12.65].

**`Doctrine-prediction-precision-improving-over-arc` sub-rule**: 9 consecutive 0%-streak (P0.S10 closure 2026-05-27) → 10 consecutive 0%-streak IF Bundle 1 Q5 closure-actual = 11 exact. Conditional on Bundle 1 closing at mid exact (NOT just within NARROW band).

**`### Pass-2-grep-auditor-verified-before-Plan-v1-approval`**: 14 → 15 applications (Bundle 1 Phase 0 auditor Pass-2 grep = 15th application). **3rd caught-real-gap mode** instance (after P0.R4 + P0.S10 Plan v1) — Bundle 1 Phase 0 caught PI #1 (LINE-REF-DRIFT) + PI #2 (SURFACE-CASCADE). Same-cycle multi-PI doesn't multiply per locked precedent (P0.S10 Plan v3 PI #3 didn't bank as 3rd).

**Sub-rule track record extensions**:
- `feedback_pass_2_grep_caught_real_gap_subshape.md` LINE-REF-DRIFT: 3 → 4 instances (preventive maturation)
- `### Pre-audit-quantifier-precision-refined-by-grep` SURFACE-CASCADE-AXIS: 8 → 9 instances (caught-real-gap continuation, no elevation)

**Multi-discipline preventive convergence sub-rule** (6 instances at P0.S10; STRONGLY WARRANTED for elevation): Bundle 1 candidate 7th instance IF 5+ disciplines apply preventively this cycle. Architect commits to enumeration at closure:
1. LINE-REF-DRIFT preventive (Plan v1 §1.1 absorption)
2. SURFACE-CASCADE preventive (Plan v1 §1.2 enumeration)
3. CROSS-PATH-SYNC-OMISSION preventive commitment (§0)
4. DEFERRED-CANARY-ENTRY-OMISSION grep-verify commitment (§9)
5. Closure-audit verdict forwarding commitment (§9)
6. CODE-TEMPLATE-MISIDENTIFICATION preventive (D3 chapter naming convention verified against existing `docs/` shape pre-creation)

If 6 disciplines apply preventively at closure → STRONGLY WARRANTED elevation candidacy locks; sub-rule promotes to numbered doctrine `### Multi-discipline-preventive-convergence` per locked elevation procedure.

---

## §6 Closure-narrative paste template

```markdown
| **Pre-P1 Bundle 1 (Docs+CI — MF1 + MF3 + MF10 — 3-artifact OPTIONAL-Plan-v2 cycle / 20th proof case) CLOSED 2026-05-28** — [SUMMARY: MF1 declared complete via existing CI scaffold + CLAUDE.md stale-entry consolidation; MF3 Project Overview rewritten to Layer D middleware framing; MF10 everything_about_system.md split into 12 chapters under docs/architecture/ + thin redirect at original path]. D1.b consolidates 2 stale P1.P1 entries (CLAUDE.md:1396+1397) into ONE new narrative paragraph confirming P0.0 scaffold live + 4 informational-mode gates flagged for post-P1 tightening. D2 Project Overview rewrite includes verbatim "Layer D cognitive runtime middleware" lead + "companion stack" + "robotics stack" explicit two-stack framing + 3-5 year horizon claim + practical references preserved. D3 split: 12 chapter files (`CHAPTER_01_*.md` through `CHAPTER_12_*.md`) + parent `README.md` index + `everything_about_system.md` replaced with <50-line thin redirect; .gitignore comment + whitelist updated; SETUP.md lines 71+85+108 redirected to active chapter surfaces. **N/N deliberate-regression confirmations passed cleanly** per `### Induction-surfaces-invariant-gaps` discipline: [(a) re-add stale P1.P1 line → A1 fires correctly + reverted; (b) drop "Layer D" lead from D2 rewrite → A3 fires + reverted; (c) drop one chapter file → A6 fires + reverted; (d) introduce broken cross-ref in CLAUDE.md (`§999` non-existent) → A5 fires + reverted; (e) leave .gitignore comment stale → A9 fires + reverted; (f) leave SETUP.md line 71 stale → A10 fires + reverted]. [Final cumulative-suite verification: passing count unchanged from P0.S10 closure baseline 2810; this is a docs-only cycle with zero production code surface.] **Plan-v1-Pass-2-grep-undercount STAYS at 12** OR **bumps to 13** depending on whether architect Pass-3 grep at closure-narrative drafting surfaces enumeration drift. **`### Pre-audit-quantifier-precision-refined-by-grep` 8 → 9 instances** (PI #2 SURFACE-CASCADE-AXIS continuation; caught-real-gap mode at auditor Phase 0 verdict). **`### Pass-2-grep-auditor-verified-before-Plan-v1-approval` 14 → 15 applications**; 3rd caught-real-gap mode (Bundle 1 Phase 0). **LINE-REF-DRIFT sub-shape 3 → 4 instances** (Bundle 1 PI #1 preventive maturation). **`### Architect-reads-production-code-before-sign-off` 30 → 31 at closure-audit** (per `Implicit-doctrine-firings-not-narrative-tracked` sub-rule; closure-narrative explicit X → Y line + Path C grep-verify across 4 active-doc surfaces + PowerShell fresh-disk verify on `to_be_checked.md` per §9 commitment). **`### Zero-precision-items-at-auditor-review` 38 → 39 instances** (Plan v1 surface CLEAN per auditor; OPTIONAL-Plan-v2 path TAKEN — **19th → 20th proof case** of the absorbed sub-rule track record). **`### Phase-0-catches-wrong-premise` STAYS at 13** (Bundle 1 premise was ON-TARGET — both PIs were verification-axis precision items inside Plan iterations, NOT wrong-premise events). **`### Phase-0-granular-decomposition-enables-accurate-estimates` BUMPS 30 → 31 SUPPORTING INSTANCES** per inclusive ±15% band table (closure-actual N anchors vs Plan v1 11-anchor LOCK = N%); **(if N=11) 10th consecutive 0%-streak rebuild instance** (P0.S10 closure 9th already banked); sub-rule `Doctrine-prediction-precision-improving-over-arc` 10th consecutive instance — sustained high-precision regime. **OPTIONAL-Plan-v2 sub-rule track record 19 → 20 proof cases** (... + P0.S10 + **Bundle 1**). **Strict-industry-standard mode 110 → 113 applications + 32 → 33 closures**. **Spec-first review cycle 119-for-119 → 122-for-122 at closure** (3 artifacts × +1 each). **`### Grep-baseline-before-drafting` 77 → 80 instances**. **Cross-cycle-handoff transparency 80 → 83 successful**. **Spec-time grep-verification 87 → 90 instances**. **`### Twin-filename-pitfall-prevention` 31 → 32 preventive events** (`tests/pre_p1_bundle1_*.md` cleanly disambiguated against zero pre-existing pre_p1 artifacts; new doctrinal genus established for pre-P1 sequence). **Auditor-Q5-estimates-trail-grep 36 → 37 banked closures** at 0% ON-TARGET exact-mid (22nd consecutive 0% reading IF N=11; `Doctrine-prediction-precision-improving-over-arc` 10th consecutive 0%-streak rebuild). **Deferred-canary strategy 34 → 35 applications** with PowerShell fresh-disk read grep-verify per §9 commitment. **NEW CI-verification handoff item**: user-triggered `workflow_dispatch` on slow.yml status report (per Q1 ratification) — green/red status logged at closure narrative as Phase 4 evidence event. **NEW elevation candidate**: `Multi-discipline preventive convergence` sub-rule (6 → 7 instances at Bundle 1 closure IF 5+ disciplines applied preventively per §5.2 enumeration) — STRONGLY WARRANTED for ###-doctrine elevation at next architect-side narrative work.
```

Above template is a placeholder shape; closure narrative will replace square-bracketed placeholders with closure-actual values.

---

## §7 Honest-count commitment (per `Explicit-closure-honest-count-commitment`)

Architect publicly commits at Plan v1 §7 (mirrors Phase 0 §7):

- Closure-actual count reported honestly at Phase 7 closure-narrative drafting regardless of which band falls
- `Doctrine-prediction-precision-improving-over-arc` 10th-consecutive-0%-streak claim ONLY banks if closure-actual = 11 exact (mid)
- If closure-actual ∈ {9, 10, 12, 13} → ON-TARGET within NARROW band BUT 10th-consecutive-streak NOT claimed (streak interrupts; 9th-streak stands as P0.S10 close — Bundle 1 falls in band-range but breaks exact-mid streak)
- If closure-actual ≥15 OR ≤7 → FALSIFICATION-WATCH activates; closure-audit names root cause

**Strict separation**: MADE (Plan v1 §7) and HONORED (closure §7) each count as one instance of `Explicit-closure-honest-count-commitment` per locked precedent. Bundle 1 contributes 2 instances total. Current count 31 (P0.S10 closure) → 32 at Plan v1 (MADE) → 33 at closure (HONORED).

---

## §8 Plan v2 path adjudication

Per Q7 RATIFIED: OPTIONAL-Plan-v2 path conditional on Plan v1 cleanly absorbing PI #1 + PI #2.

Plan v1 covers:
- ✓ PI #1 absorption at §1.1 + §2 D1.b restated
- ✓ PI #2 absorption at §1.2 24-file enumeration + §2 D3.c scope expansion
- ✓ Q5 LOCK at 11 with A5 scope-expanded (4-file parametrize per §3)
- ✓ §5 conditional restatement honoring auditor cross-doctrine sanity check
- ✓ §7 honest-count commitment preserved

If auditor returns Plan v1 review CLEAN (0 PIs) → ship Plan v1 to developer; cycle ships as 3-artifact (Phase 0 + Plan v1 + closure); **20th OPTIONAL-Plan-v2 proof case** locks at closure.

If auditor returns Plan v1 with new PIs → cycle escalates to 4-artifact (Plan v2 absorbs).

---

## §9 Procedural commitments (closure-audit)

Per locked precedent from P0.R8-P0.S10:

1. **Path C grep-verify discipline** applied at closure-narrative drafting: production active-doc files (CLAUDE.md + .gitignore + SETUP.md + thin redirect at `everything_about_system.md`) verified fresh post-implementation.
2. **Cross-path memory-file discipline**: NO new memory file landing this cycle (closure work touches CLAUDE.md narrative + `to_be_checked.md` entry only).
3. **DEFERRED-CANARY-ENTRY-OMISSION preventive**: PowerShell fresh-disk read on `to_be_checked.md` AFTER architect pastes Bundle 1 entry. Verify mtime + size + occurrence-count.
4. **Closure-audit verdict forwarding**: Bundle 1 closure findings + grep-verify results + 5+ preventive discipline enumeration → forwarded to auditor for EXPLICIT RATIFICATION verdict BEFORE declaring CLOSED. 6th cycle of routinization.
5. **Multi-discipline preventive convergence enumeration**: §5.2 list re-verified at closure with closure-actual count of preventive-applied disciplines. 7th instance lock requires ≥5 disciplines applied (per locked threshold).
6. **CI run evidence** (Q1 RATIFIED): user-triggered `workflow_dispatch` on slow.yml + green/red report logged in closure narrative as MF1 verification evidence.

---

## §10 Known Limitations

Per architect closure-discipline (locked at multiple prior closures):

1. **SETUP.md pre-existing doc bugs preserved**: Line 71 "Part XXXI" + Line 108 "§195" reference sections that don't exist in current `everything_about_system.md` H2 numbering (highest visible H2 is §176 with sub-sections §52b, §140a, §140b totaling 178 H2-prefixed sections). These stale refs predate Bundle 1's split work. Bundle 1 D3.c WILL redirect lines 71 + 108 to a SENSIBLE chapter (likely Chapter 4 audio_and_stt_tts for pyannote patches), but the underlying "ghost section number" issue stays. Future SETUP.md hygiene PR can correct the section refs separately.
2. **Sealed archive files** (20 listed at §1.2): not retroactively updated. Thin redirect at `everything_about_system.md` is the safety net for downstream readers of historical plan/audit files.
3. **CI informational-mode gates** (mypy, ruff format, pip-audit, Trivy `exit-code: 0`): remain non-blocking after Bundle 1. Tightening flagged as post-P1 follow-up.
4. **Plan v1 §1.2 enumeration count = 24 active grep matches**. If file system state changes between Plan v1 drafting and Phase 4 implementation (e.g., new spec file lands that references `everything_about_system.md`), Phase 4 §1 Pass-3 grep refresh will surface drift. Architect commits to Pass-3 grep at closure-narrative drafting per locked discipline.
5. **`docs/architecture/` directory does NOT yet exist**. Phase 4 implementation creates it. No CI/test workflow currently scans this directory — workflows scan `tests/` + `core/` + repo root. No CI updates required for Bundle 1.

---

## §11 Architect Pass-2 grep-verify summary

Per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine 3-part operational rule applied at Plan v1 drafting:

1. **Symbol-name-uniqueness grep** ✓ — verified `P1.P1 — No CI config` literal text returns exactly 2 matches in CLAUDE.md (lines 1396 + 1397); zero false-positive collisions with surrounding text.
2. **Behavioral semantic verification under call-site context** ✓ — verified by reading lines 1396-1400 context: both entries are top-level Pending Work bullets, NOT references inside other narrative blocks. Consolidating into one narrative paragraph at the same position is semantically clean.
3. **Symmetric verification (reject + preserve classes)** ✓ — verified ZERO stale `P1.P1` matches in CLAUDE.md post-removal would be the reject class (A1 anchor enforces); ANY non-P1.P1 PEND ING-Work entries near lines 1396+1397 preserve their position (regression guard at A1).

24-file enumeration ✓ verified via independent architect Pass-2 grep (matches auditor's grep result exactly).

`.gitignore` content ✓ verified: lines 127 (comment) + 144 (whitelist negation).
`SETUP.md` content ✓ verified: lines 71 + 85 + 108.

Path C grep-verify clearance for Plan v1 → Phase 4 handoff: GREEN.

---

## §12 Standing by for auditor Plan v1 verdict

If auditor returns CLEAN (0 PIs) → OPTIONAL-Plan-v2 path activates; Plan v1 ships to developer for Phase 4 implementation.

If auditor returns PIs → Plan v2 absorbs; cycle escalates to 4-artifact.

---

**Filed**: 2026-05-28
**Architect**: Claude
**Forwarded to**: Auditor (external)
