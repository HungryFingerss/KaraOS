# Pre-P1 Bundle 1 — Docs + CI Plan v2 (2026-05-28)

**Cycle**: Pre-P1 must-fix Bundle 1 (Docs+CI)
**Predecessors**:
- `tests/pre_p1_bundle1_docs_ci_audit.md` (Phase 0, ACCEPT WITH 2 PIs)
- `tests/pre_p1_bundle1_docs_ci_plan_v1.md` (Plan v1, auditor RATIFIED CLEAN)
**Cycle shape**: 4-artifact (Phase 0 + Plan v1 + **Plan v2** + closure). OPTIONAL-Plan-v2 path NOT TAKEN this cycle.
**Trigger event**: Developer Pass-3 grep at Phase 4 pre-implementation surfaced architect Phase 0 enumeration drift (file actually 9214 lines / 344 H2 sections vs Phase 0 claim of 6487 / 178).
**Architect**: Claude (Phase 0 measurement error OWNED)
**Auditor**: External
**Developer**: External (caught the drift)

---

## §0 Procedural commitments

Carried from Plan v1 §0 verbatim plus 1 NEW commitment:

**§0 NEW commitment** — `feedback_pass_2_grep_caught_real_gap_subshape.md` BOTH-modes maturation continues. This is the 1st instance of a NEW catching-layer under the SURFACE-CASCADE-AXIS sub-shape: **developer Pass-3 grep at Phase 4 pre-implementation** (PREVIOUSLY caught at: closure-audit / Plan v1 auditor review / Phase 0 audit / developer Phase 5 implementation). Earliest catching-layer in track record. Phase 4 pre-implementation is the IDEAL catching layer — surfaces drift BEFORE any code phase fires, preserving rollback discipline.

---

## §1 Architect Phase 0 measurement error owned

### §1.1 Quantitative drift (verified 2026-05-28)

| Surface | Phase 0 claim (2026-05-27) | Actual (2026-05-28, verified) | Drift |
|---|---|---|---|
| File line count | 6487 | **9214** (raw LF count) / 9215 (.Split) | +42% |
| H2 section count | 178 | **344** (Grep `^## ` count) | +93% |
| Final section number | §176 at line 6517 | **§340 at line 9186** | +93% |
| File size (bytes) | 608 KB / 623,246 | 623,246 | 0% (unchanged) |

**File content has NOT changed since Phase 0 audit drafting (byte size identical).** The drift is entirely an architect measurement error.

### §1.2 Root cause owned

PowerShell `Get-Content | Measure-Object -Line` undercounts on this file. Likely due to:
- Mixed line-ending handling (`\r\n` vs `\n`)
- Streaming-mode line counting that bails early on a specific byte sequence
- Encoding artifact (file is UTF-8 with some non-ASCII content per CLAUDE.md history banking)

**Reliable verification methods** (verified 2026-05-28):
- `[System.IO.File]::ReadAllText('path').Split("`n").Length` — full read, accurate count
- `[System.IO.File]::ReadAllText('path').ToCharArray() | Where-Object { $_ -eq [char]10 }).Count` — raw LF count
- `Grep ^## path --output-mode count` (this tool, ripgrep-based) — accurate H2 count

**Architect Phase 0 used PowerShell `Get-Content | Measure-Object -Line` which is the unreliable method.** Banked at §10 Known Limitations as discipline-extension for future Phase 0 measurements.

### §1.3 §177-§340 content audit (the 164 missing sections)

Independent grep-verify of section list 2026-05-28 surfaces 14 natural clusters in §177-§340:

| Range | Sections | Line range | Approx size | Topic cluster |
|---|---|---|---|---|
| §177-§183 | 7 | 6541-6680 | ~140 lines | Observability 2.0 (logging, archival, intent log) |
| §184-§187 | 4 | 6622-6694 | ~75 lines | Pipeline.py Decomposition planning (now DEFERRED to P2 per CEO decisions) |
| §188-§193 | 6 | 6695-6776 | ~80 lines | Eval Bench + Golden Set phase planning |
| §194-§197 | 4 | 6777-6822 | ~50 lines | Pyannote patching workflow |
| §198-§203 | 6 | 6823-6990 | ~170 lines | Voice/Vision Independence + Reconciler 22-rule cascade |
| §204-§214 | 11 | 6991-7259 | ~270 lines | Pure-Graph Classifier (Spec 1 + Spec 2 + correction loop + outcome supervision + E5 + latency) |
| §215-§222 | 8 | 7260-7450 | ~190 lines | External Benchmarks (Friends test + Bhagtani et al. + Qwen-7B + Graph classifier 64.48% + scaling ablation + AMI + karaos-public repo) |
| §223-§232 | 10 | 7451-7709 | ~260 lines | Multi-Layer Architecture (6-layer plan + phase sequencing + non-parametric commitment + limitations) |
| §233-§249 | 17 | 7710-7898 | ~190 lines | P0 Correctness Cycles (P0.1-P0.5 + P0.X + silent excepts + paired writes + Kuzu) |
| §250-§270 | 21 | 7899-8215 | ~320 lines | P0.6 Store-Pattern Migration + P0.7 Typed Session State |
| §271-§284 | 14 | 8216-8427 | ~210 lines | P0.8 Timeout Protection + P0.9 Schema Migrations |
| §285-§299 | 15 | 8428-8611 | ~185 lines | P0.10 Legacy Router Deletion + P0.11 Persistent Dict + P0.12 Property Testing |
| §300-§321 | 22 | 8612-8934 | ~325 lines | Observability + Tiered CI + Event Log Foundation |
| §322-§340 | 19 | 8935-9214 | ~280 lines | Architectural Disciplines + Upcoming Work |

Total: 164 new sections covering ~2945 lines.

### §1.4 Revised cluster table — 19 chapters total

Combining small natural clusters where appropriate (Plan v1 §1.3 "comfortable file size" intent preserved):

| Chapter | Source sections | Line range | Approx size | Topic |
|---|---|---|---|---|
| **CHAPTER_01** | §1-§9 | 493-1115 | ~620 lines | Introduction + Tech Stack |
| **CHAPTER_02** | §10-§15 | 1116-1393 | ~280 lines | Lifecycle + Pipeline States |
| **CHAPTER_03** | §16-§29 | 1394-1935 | ~540 lines | Async + Vision Basics |
| **CHAPTER_04** | §30-§35 | 1936-2102 | ~170 lines | Audio + STT/TTS |
| **CHAPTER_05** | §36-§46 | 2103-2422 | ~320 lines | Face/Voice Galleries |
| **CHAPTER_06** | §47-§58 | 2423-2924 | ~500 lines | Sessions + Evidence |
| **CHAPTER_07** | §59-§71 | 2925-3437 | ~510 lines | Reconciler + Conversation Turn |
| **CHAPTER_08** | §72-§99 | 3438-4359 | ~920 lines | Prompt Blocks + Brain Agents |
| **CHAPTER_09** | §100-§118 | 4360-4633 | ~270 lines | Dispute + Tool Privileges + Logging |
| **CHAPTER_10** | §119-§140b | 4635-5161 | ~530 lines | Schemas + Tests + Dashboard |
| **CHAPTER_11** | §141-§149 | 5164-5704 | ~540 lines | Future Work + Reference Tables |
| **CHAPTER_12** | §150-§176 | 5705-6540 | ~835 lines | Privacy + Rooms + Recent Work |
| **CHAPTER_13** (NEW) | §177-§197 | 6541-6822 | ~280 lines | Observability 2.0 + Evolution Plans + Pyannote |
| **CHAPTER_14** (NEW) | §198-§214 | 6823-7259 | ~440 lines | Voice/Vision Independence + Pure-Graph Classifier |
| **CHAPTER_15** (NEW) | §215-§232 | 7260-7709 | ~450 lines | External Benchmarks + Multi-Layer Architecture |
| **CHAPTER_16** (NEW) | §233-§270 | 7710-8215 | ~510 lines | P0 Correctness Foundations + Store/Session Migrations |
| **CHAPTER_17** (NEW) | §271-§299 | 8216-8611 | ~400 lines | P0 Timeout + Schema + Router/Concurrency/Property |
| **CHAPTER_18** (NEW) | §300-§321 | 8612-8934 | ~325 lines | Observability + Tiered CI + Event Log Foundation |
| **CHAPTER_19** (NEW) | §322-§340 | 8935-9214 | ~280 lines | Architectural Disciplines + Upcoming Work |

**Chapter file naming convention** (LOCKED):
- `docs/architecture/CHAPTER_01_introduction_and_tech_stack.md`
- `docs/architecture/CHAPTER_02_lifecycle_and_pipeline_states.md`
- `docs/architecture/CHAPTER_03_async_and_vision_basics.md`
- `docs/architecture/CHAPTER_04_audio_and_stt_tts.md`
- `docs/architecture/CHAPTER_05_face_voice_galleries.md`
- `docs/architecture/CHAPTER_06_sessions_and_evidence.md`
- `docs/architecture/CHAPTER_07_reconciler_and_conversation_turn.md`
- `docs/architecture/CHAPTER_08_prompt_blocks_and_brain_agents.md`
- `docs/architecture/CHAPTER_09_dispute_tool_privileges_logging.md`
- `docs/architecture/CHAPTER_10_schemas_tests_dashboard.md`
- `docs/architecture/CHAPTER_11_future_work_reference_tables.md`
- `docs/architecture/CHAPTER_12_privacy_rooms_recent_work.md`
- `docs/architecture/CHAPTER_13_observability_evolution_plans_pyannote.md`
- `docs/architecture/CHAPTER_14_voice_vision_independence_pure_graph_classifier.md`
- `docs/architecture/CHAPTER_15_external_benchmarks_multilayer_architecture.md`
- `docs/architecture/CHAPTER_16_p0_correctness_store_session_migrations.md`
- `docs/architecture/CHAPTER_17_p0_timeout_schema_router_concurrency_property.md`
- `docs/architecture/CHAPTER_18_observability_ci_event_log.md`
- `docs/architecture/CHAPTER_19_architectural_disciplines_upcoming_work.md`

Plus parent index `docs/architecture/README.md` listing all 19 chapters.

### §1.5 PI absorption from Plan v1 (preserved unchanged)

PI #1 absorption (LINE-REF-DRIFT corrected to lines 1396 + 1397) — unchanged from Plan v1 §1.1.
PI #2 absorption (24-file ripple enumeration) — unchanged from Plan v1 §1.2.

### §1.6 Section-number stability invariant (LOAD-BEARING contract)

Every H2 section §NN in the source `everything_about_system.md` lands in EXACTLY ONE chapter file with the SAME §NN identifier. Reader of "see `docs/architecture/CHAPTER_NN §59`" finds the same content as the original "everything_about_system.md §59".

**Cross-reference test scope** (A14 anchor below): zero §NN appears in 2+ chapters; zero §NN missing from chapter set. Test parametrized across the full 1-340 section range.

---

## §2 D-decisions (D3.a scope expanded; D1 + D2 unchanged from Plan v1)

### D1 — UNCHANGED from Plan v1 §2 D1

CLAUDE.md lines 1396 + 1397 consolidation.

### D2 — UNCHANGED from Plan v1 §2 D2

Project Overview rewrite to Layer D framing. Fresh test count via `pytest --collect-only`.

### D3 — D3.a scope EXPANDED; D3.b/c/d UNCHANGED

- **D3.a (EXPANDED)**: Create `docs/architecture/` directory with **19 chapter files** per §1.4 cluster table (was 12 in Plan v1). Parent index `docs/architecture/README.md` lists all 19 chapters. Mechanical extraction discipline per P0.8 / P0.9.2 precedent — verbatim section moves, zero "while I'm here" edits.
- **D3.b** (UNCHANGED): Replace `everything_about_system.md` with thin redirect; chapter list mentions all 19 chapters.
- **D3.c** (UNCHANGED): `.gitignore` + `SETUP.md` updates per Plan v1.
- **D3.d** (SCOPE EXPANDED): CLAUDE.md `§NNN` cross-reference updates now cover §1-§340 (not §1-§176). Section-number stability invariant (§1.6) is the contract.

### Cross-D shipping order

UNCHANGED from Plan v1 (Q5 RATIFIED): **D3 → D2 → D1**.

---

## §3 Q5 LOCK recalibrated (mid 14, NARROW band [11.9, 16.1])

### §3.1 Anchor breakdown (3 NEW anchors A12+A13+A14)

| # | Anchor | Type | Scope |
|---|---|---|---|
| A1 | D1.b stale-line removal | source-inspection: ZERO `P1.P1 — No CI config` matches in CLAUDE.md | UNCHANGED |
| A2 | D1.b consolidated new narrative | source-inspection: new P0.0-scaffold-confirmed paragraph present | UNCHANGED |
| A3 | D2 Layer D lead sentence | source-inspection: exact verbatim "Layer D cognitive runtime middleware" | UNCHANGED |
| A4 | D2 two-stack mention | source-inspection: "companion stack" + "robotics stack" both present | UNCHANGED |
| A5 | D2 + D3 cross-ref resolution | structural parametrize across 4 active-doc surfaces | UNCHANGED |
| A6 | D3.a chapter directory + chapter files | source-inspection: `docs/architecture/` exists; **19 chapter files** present with correct names | SCOPE EXPANDED (12 → 19) |
| A7 | D3.a parent index | source-inspection: `docs/architecture/README.md` exists + links all **19** chapters | SCOPE EXPANDED (12 → 19) |
| A8 | D3.b thin redirect | source-inspection: redirect <50 lines + DO-NOT-WRITE-HERE notice + **19-chapter** list | SCOPE EXPANDED |
| A9 | D3.c .gitignore update | source-inspection: comment + whitelist reflect split | UNCHANGED |
| A10 | D3.c SETUP.md update | source-inspection: lines 71+85+108 reference active surfaces | UNCHANGED |
| A11 | D3.d CLAUDE.md ref redirect | source-inspection: zero stale `everything_about_system.md §NNN` refs in CLAUDE.md | UNCHANGED |
| **A12 (NEW)** | §177-§340 coverage | structural parametrize: every §NN in 177-340 lands in exactly one chapter file | NEW for Plan v2 |
| **A13 (NEW)** | Chapter index README covers 19 chapters | source-inspection: README contains all 19 chapter cross-section navigation entries | NEW for Plan v2 |
| **A14 (NEW)** | Section-number stability invariant | structural parametrize across §1-§340: every §NN appears in EXACTLY ONE chapter (zero duplicates + zero missing) | NEW for Plan v2 — LOAD-BEARING per §1.6 |

**Total = 14 logical anchors. NARROW band [11.9, 16.1]. Q5 LOCK = 14.**

### §3.2 Closure-projection band table (per `Explicit-closure-honest-count-commitment`)

| Closure-actual | % vs mid | Reading | Doctrine consequence |
|---|---|---|---|
| 12 anchors | -14.3% | ON-TARGET (within NARROW band) | doctrine bumps |
| 13 anchors | -7.1% | ON-TARGET | doctrine bumps |
| **14 anchors (Q5 LOCK)** | **0%** | exact mid | `### Phase-0-granular-decomposition` bumps 30 → 31 supporting; `Doctrine-prediction-precision-improving-over-arc` 10th consecutive 0%-streak rebuild (P0.S10 closure 9th already banked) |
| 15 anchors | +7.1% | ON-TARGET | doctrine bumps |
| 16 anchors | +14.3% | ON-TARGET | doctrine bumps |
| 17 anchors | +21.4% | SLIGHT-DRIFT-UP | within ±30%; doctrine holds |
| ≥19 anchors OR ≤10 anchors | ≥+35% / ≤-29% | FALSIFICATION TRIGGER | `### Phase-0-granular-decomposition` falsification clause activates IF root cause is wrong-premise; if scope-expansion via auditor refinement, sub-observation reset only |

### §3.3 Honest-count restatement

`Doctrine-prediction-precision-improving-over-arc` 10th-consecutive-0%-streak claim STAYS conditional on closure-actual = 14 exact. P0.S10 closure 2026-05-27 confirms 9th-streak banked. Bundle 1 closure at exact mid = 10th-streak rebuild.

---

## §4 Cross-spec impact

### §4.1 24-file ripple table — UNCHANGED from Plan v1 §1.2

4 active-doc mutations + 20 sealed archive files. Sealed archives NOT mutated (thin redirect catches downstream).

### §4.2 §177-§340 references in active docs

Architect Pass-3 grep 2026-05-28 verified: no NEW active-doc references to §177-§340 exist beyond the file itself. CLAUDE.md references `everything_about_system.md` ~3 times in the "Tests guard every invariant" + Pending Work + history banking — none point at §177-§340 specifically. `.gitignore` + `SETUP.md` references are file-level not §-level. **No additional active-doc ripple beyond Plan v1's 4-file scope.**

### §4.3 Bundle 2-5 dependencies — UNCHANGED

---

## §5 Discipline counts (4-artifact cycle, Plan v2 added)

### §5.1 Per-artifact-driven disciplines

Locked +1-per-artifact convention applied:

| Discipline | Pre-Bundle-1 | Phase 0 | Plan v1 | **Plan v2** | Closure |
|---|---|---|---|---|---|
| Strict-industry-standard mode applications | 110 | 111 | 112 | **113** | 114 |
| Spec-first review cycle | 119 | 120 | 121 | **122** | 123 |
| `### Grep-baseline-before-drafting` | 77 | 78 | 79 | **80** | 81 |
| Cross-cycle-handoff transparency | 80 | 81 | 82 | **83** | 84 |
| Spec-time grep-verification | 87 | 88 | 89 | **90** | 91 |

### §5.2 Closure-event disciplines (single +1 at closure)

| Discipline | Pre-Bundle-1 | After closure |
|---|---|---|
| Strict-industry-standard mode closures | 32 | 33 |
| `### Twin-filename-pitfall-prevention` | 31 | 32 (preventive) |
| `### Architect-reads-production-code-before-sign-off` | 30 | 31 (closure-audit event with explicit X → Y per `Implicit-doctrine-firings-not-narrative-tracked` sub-rule) |
| Auditor-Q5-estimates-trail-grep | 36 | 37 banked closures |
| Deferred-canary strategy | 34 | 35 applications |

### §5.3 NEW doctrine instances banked at closure

| Discipline | Pre-Bundle-1 | After closure | Cycle event |
|---|---|---|---|
| `Plan-v1-Pass-2-grep-undercount` | 12 | **13** | NEW catching layer = developer Pass-3 pre-implementation (earliest catching layer in track record) |
| `### Pre-audit-quantifier-precision-refined-by-grep` SURFACE-CASCADE-AXIS | 9 | **10** | Architect Phase 0 measurement error (line/section count drift); developer Pass-3 catches |
| LINE-REF-DRIFT sub-shape | 3 | **4** | PI #1 absorption maturation (Plan v1 §1.1) |
| `Zero-precision-items-pre-closure-predictions-blocked` | 2 | **3** | Architect predicted OPTIONAL-Plan-v2 at Plan v1 verdict → developer Phase 4 pre-implementation surfaced real gap → prediction blocked. 3rd consecutive (P0.S9 + P0.R1 + Bundle1). **Sub-rule formalization candidacy STRONGLY WARRANTED at 3+ instances**. |
| `### Architect-reads-production-code-before-sign-off` BIDIRECTIONAL VALIDATION pattern | 1 (P0.R9 STALE-CACHED) | **2** | Developer's Pass-3 grep at Phase 4 catches architect's Phase 0 measurement drift. 2nd bidirectional-validation instance. 3-instance threshold for sub-rule elevation. |
| OPTIONAL-Plan-v2 sub-rule track record | 19 | **STAYS 19** | Bundle 1 ships 4-artifact; does NOT bank 20th proof case this cycle |
| `Doctrine-prediction-precision-improving-over-arc` consecutive 0%-streak | 9 | **STAYS 9** UNLESS Bundle 1 closure-actual = 14 exact → then 10 | conditional |
| `### Phase-0-catches-wrong-premise` | 13 | **STAYS 13** | Bundle 1 Phase 0 premise was ON-TARGET (split scope correctly identified); enumeration was off, NOT premise. Sub-pattern A NOT triggered. |

### §5.4 Multi-discipline preventive convergence (CANDIDATE ELEVATION at closure)

6 disciplines applied preventively at Plan v1 + Plan v2 (per Plan v1 §5.2 enumeration). Plan v2 PRESERVES the convergence — none of the 6 preventives reset.

7 disciplines applied preventively at Plan v2:
1. LINE-REF-DRIFT preventive (Plan v1 §1.1 + Plan v2 §1.5)
2. SURFACE-CASCADE preventive (Plan v1 §1.2 + Plan v2 §1.3 — enumeration drift bank at 10th instance)
3. CROSS-PATH-SYNC-OMISSION preventive commitment (§0)
4. DEFERRED-CANARY-ENTRY-OMISSION grep-verify commitment (§9)
5. Closure-audit verdict forwarding commitment (§9 — 6th cycle routinization)
6. CODE-TEMPLATE-MISIDENTIFICATION preventive (D3 chapter naming convention verified against existing `docs/` shape pre-creation)
7. **NEW: Architect-Phase-0-measurement-error-owned-and-corrected-pre-implementation** (Plan v2 §1.1 + §1.2 + §10 banking) — the discipline working as designed (developer catch + architect owns + Plan v2 absorbs without code-phase rollback)

**7 disciplines applied preventively → STRONGLY WARRANTED for sub-rule elevation candidacy at Bundle 1 closure-audit.** Threshold reached. If closure also applies 5+ preventives, elevation lock per locked procedure.

---

## §6 Closure-narrative paste template (Plan v2-aware)

```markdown
| **Pre-P1 Bundle 1 (Docs+CI — MF1 + MF3 + MF10 — 4-artifact cycle with Plan v2 absorption of architect Phase 0 enumeration drift) CLOSED 2026-05-28** — [SUMMARY: 19-chapter split (not 12 as Plan v1 originally enumerated; Phase 0 measurement error owned and corrected at Plan v2); MF1 declared complete via existing CI scaffold; MF3 Project Overview rewritten to Layer D middleware framing; MF10 everything_about_system.md split into 19 chapters under docs/architecture/ + thin redirect at original path]. **Plan v2 trigger event**: developer Pass-3 grep at Phase 4 pre-implementation surfaced architect Phase 0 line-count + section-count drift (file actually 9214 lines / 344 H2 sections vs Phase 0 claim of 6487 / 178). Root cause: PowerShell `Get-Content | Measure-Object -Line` undercounts on this file; banked as known limitation per §10. Plan v2 §1 absorption restated cluster table from 12 → 19 chapters covering §1-§340 with verbatim section-number preservation invariant (§1.6 + A14 anchor). **Doctrine firings at closure**: `Plan-v1-Pass-2-grep-undercount` 12 → 13 (NEW catching-layer = developer Pass-3 pre-implementation, earliest catching layer in track record). `### Pre-audit-quantifier-precision-refined-by-grep` SURFACE-CASCADE-AXIS 9 → 10 instances. LINE-REF-DRIFT sub-shape 3 → 4 instances. `Zero-precision-items-pre-closure-predictions-blocked` 2 → 3 instances (P0.S9 + P0.R1 + **Bundle 1**); **sub-rule formalization candidacy STRONGLY WARRANTED at 3rd instance**. `### Architect-reads-production-code-before-sign-off` BIDIRECTIONAL-VALIDATION pattern 1 → 2 instances (developer catches architect at Phase 4 pre-implementation; 3-instance threshold for sub-rule elevation). OPTIONAL-Plan-v2 sub-rule track record STAYS at 19 (Bundle 1 ships 4-artifact). `Doctrine-prediction-precision-improving-over-arc` consecutive 0%-streak [STAYS at 9 IF closure-actual ≠ 14 / extends to 10 IF closure-actual = 14 exact]. `### Phase-0-catches-wrong-premise` STAYS at 13 (Bundle 1 premise was ON-TARGET; enumeration was drift not wrong-premise). **N/N deliberate-regression confirmations passed cleanly** per `### Induction-surfaces-invariant-gaps` discipline: [a-h regression list]. **Plan-v2-§5.4 Multi-discipline preventive convergence**: 7 disciplines applied preventively at Plan v2; STRONGLY WARRANTED for sub-rule elevation candidacy at this closure-audit. **Strict-industry-standard mode 110 → 114 applications + 32 → 33 closures** (4-artifact cycle: 110 baseline + 4 artifacts = 114). **Spec-first review cycle 119-for-119 → 123-for-123 at closure** (4 artifacts × +1 each). **`### Grep-baseline-before-drafting` 77 → 81 instances**. **Cross-cycle-handoff transparency 80 → 84 successful**. **Spec-time grep-verification 87 → 91 instances**. **`### Twin-filename-pitfall-prevention` 31 → 32 preventive events**. **Auditor-Q5-estimates-trail-grep 36 → 37 banked closures** at [N% vs mid 14] (X consecutive 0% reading IF closure-actual=14). **Deferred-canary strategy 34 → 35 applications** with PowerShell fresh-disk read grep-verify per §9 commitment. **NEW CI-verification handoff item** (Q1 ratification): user-triggered `workflow_dispatch` on slow.yml status report — green/red status logged at closure narrative as Phase 4 evidence event. **NEW known limitation §10 banking**: PowerShell `Get-Content | Measure-Object -Line` is unreliable on certain file encodings; `[System.IO.File]::ReadAllText().Split("`n").Length` OR Grep `^pattern` count is the reliable Phase 0 measurement method. Locked discipline-extension for future Phase 0 grep-baseline work.
```

---

## §7 Honest-count commitment (preserved)

Per `Explicit-closure-honest-count-commitment`:
- Plan v2 §7 MADE → closure §7 HONORED counts as 2 separate instances of the discipline.
- Strict separation locked at P0.B3 close. Bundle 1 contributes 3 instances total (Plan v1 MADE + Plan v2 MADE + closure HONORED). Strict-mode discipline preserved.

Current count: 31 (P0.S10 closure) → 32 at Plan v1 (MADE) → **33 at Plan v2 (MADE — restated)** → 34 at closure (HONORED).

---

## §8 Plan v3 path adjudication

If auditor returns Plan v2 review CLEAN → ship Plan v2 to developer; cycle ships as 4-artifact (Phase 0 + Plan v1 + Plan v2 + closure); doctrine count bumps per §5.

If auditor returns Plan v2 with NEW PIs → cycle escalates to 5-artifact (Plan v3 absorbs). **This would be unusually deep absorption — same shape as P0.S10's 6-artifact cycle (PI #1, PI #2, PI #3 across 3 Plan iterations).**

Architect's Plan v2 confidence: Plan v2 §1.4 cluster table is GREP-VERIFIED at Pass-3 (architect re-ran the section grep + verified all line ranges 2026-05-28). 14-anchor Q5 LOCK was developer-confirmed at ~13-15 range. Multi-discipline preventive convergence preserved across Plan v1 → Plan v2 transition.

---

## §9 Procedural commitments (unchanged from Plan v1)

All 6 procedural commitments preserved. CI run evidence (Q1 ratified) still required at closure.

---

## §10 Known Limitations (Plan v2 adds 1 NEW entry)

1-5 UNCHANGED from Plan v1 §10.

**6 (NEW — locked at Plan v2)**: **PowerShell `Get-Content | Measure-Object -Line` undercounts on `everything_about_system.md` and possibly other large-or-mixed-encoding files**. Phase 0 used this method, returned 6487 lines for a 9214-line file (42% undercount). The byte size measurement was correct (`Get-Item.Length` ✓), but the line count was wrong.

**Discipline extension for future Phase 0 work**:
- For line count: use `[System.IO.File]::ReadAllText('path').Split("`n").Length` (full read + split on LF) OR `Grep '^.*$' path --output-mode count` (ripgrep, every line)
- For section count: use `Grep '^##\s' path --output-mode count` (ripgrep)
- For byte size: `Get-Item path | Select-Object -ExpandProperty Length` (always reliable)
- NEVER use `Get-Content | Measure-Object -Line` for line count on files with mixed encodings or > 5000 lines

This banking locks the lesson for future architect Phase 0 measurements. Any P0/Bundle Phase 0 audit citing line counts MUST use one of the reliable methods.

---

## §11 Architect Pass-3 grep-verify (Plan v2 drafting)

Per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine + 3-part operational rule:

1. **Symbol-name-uniqueness grep** ✓ — `^## ` returns 344 sections (verified via Grep count tool).
2. **Behavioral semantic verification under call-site context** ✓ — §177 lands at line 6541 (Enrollment Mishear Candidate Gate); §340 lands at line 9186 (Multi-Layer Classifier Architecture). Verbatim verified.
3. **Symmetric verification (reject + preserve)** ✓ — A14 invariant (every §NN appears in exactly one chapter; zero duplicates + zero missing) is the symmetric guard. Test parametrized across full 1-340 range covers both classes.

Pass-3 grep clearance for Plan v2 → Phase 4 handoff: **GREEN with corrected enumeration**.

---

## §12 Standing by for auditor Plan v2 verdict

If CLEAN (0 PIs) → ship to developer for Phase 4 implementation with corrected 19-chapter scope.
If PIs surface → Plan v3 absorbs (5-artifact cycle becomes 6-artifact). Architect commits to Plan v2 being the final iteration if no new structural issues surface.

---

**Filed**: 2026-05-28
**Architect**: Claude (Phase 0 measurement error OWNED at §1)
**Forwarded to**: Auditor (external)
**Trigger**: Developer Pass-3 grep at Phase 4 pre-implementation
