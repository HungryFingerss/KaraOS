# Pre-P1 Bundle 3 — Critical Bugs (MF4 + MF5) Plan v2 (2026-05-28)

**Cycle**: Pre-P1 must-fix Bundle 3 (Critical Bugs)
**Predecessor**: `tests/pre_p1_bundle3_critical_bugs_plan_v1.md` (auditor verdict: BLOCKED by 3 PIs — PI #1 CRITICAL §1.14 overcount + PI #2 MEDIUM §1.8 arithmetic + PI #3 MEDIUM §1.9 enumeration mismatch)
**Discipline**: Strict-mode, 4-artifact cycle (OPTIONAL-Plan-v2 path NOT activated; 20th proof case STAYS at 19; 3rd consecutive blocked Pre-P1 bundle)
**Architect**: Claude
**Auditor**: External (Plan v1 verdict in `info.md` 2026-05-28)

---

## §0 Procedural commitments

All Plan v1 §0 commitments PRESERVED. NEW for Plan v2:

### §0 NEW absorption event — PI #1 absorbed (fabricated Pass-2 refinement event)

Plan v1 §1.14 claimed assert count refined 44 → 48 with "+4 sites from BUG-9 cluster expansion at architect Pass-2 grep". Auditor's independent Pass-2 grep verified pipeline.py has **14 assert sites total** (BUG-9 cluster = exactly 5 sites at lines 2020, 2023, 2026, 2029, 2032 — NOT "~9" as Plan v1 claimed). Total assert sites = 14 + 18 + 11 + 1 = **44** matching Phase 0 baseline. The "+4 site expansion" was a fabricated refinement event with no grep-evidence support.

**PI #1 CRITICAL absorption**: Plan v2 §1.14 LOCKS at 44 sites. All cascade sites corrected:
- §3.1 A1+A3 fan-out: 76 → **72 collections**
- §4.1 D3 file-impact: 48 → **44 line-level edits**
- §6 closure-narrative paste template: 4 instances of "48 sites" → **"44 sites"**
- §5.3 `Plan-v1-Pass-2-grep-undercount` 14 → 15 banking **WITHDRAWN** (stays at 14; no real undercount surfaced)

**NEW informal observation banked at architect-memory**: `Plan-v1-Pass-2-grep-OVERCOUNT` — opposite-direction failure mode of the locked `Plan-v1-Pass-2-grep-undercount` discipline. **1st instance** at Bundle 3 Plan v1 §1.14 (architect's Pass-2 grep on BUG-9 cluster inflated by +4 phantom sites). Distinct catching mechanism: undercount catches MISSING sites at later layers; overcount catches NONEXISTENT sites at AUDITOR Pass-2 verification. 3-instance threshold for sub-rule formalization under `Plan-v1-Pass-2-grep-undercount` parent doctrine.

### §0 NEW absorption event — PI #2 absorbed (footer arithmetic off-by-one)

Plan v1 §1.8 TOTAL row claimed "**231 production**" but bucket-cell arithmetic produces 230. Adjustment: `core/reconciler.py` row Notes correctly stated "Adjustment: bucket reduces from 1 to 0 production sites" but the TOTAL row didn't apply this adjustment.

**PI #2 MEDIUM absorption**: Plan v2 §1.8 corrects TOTAL row to **230 production** with explicit math note showing WALLCLOCK = 186 (was 187; reconciler.py adjustment applied to TOTAL). DEADLINE-MATH 28 + WALLCLOCK 186 + AMBIGUOUS 16 = 230.

### §0 NEW absorption event — PI #3 absorbed (§1.9 enumeration mismatch)

Plan v1 §1.9 header claimed "13 DEADLINE-MATH sites confirmed" but enumeration listed 12. The discrepancy: Phase 0 §1.2 listed 13 candidates total, including `core/brain_agent.py:6908` (Kuzu rebuild_secs); §1.9 section scope is pipeline.py-only (12 sites). The cross-file 13th candidate belongs in §1.10 (brain_agent.py).

**PI #3 MEDIUM absorption**: Plan v2 §1.9 header corrected to "**Initial Pass-1 12 pipeline.py DEADLINE-MATH sites + 1 core/brain_agent.py site (per §1.10) = 13 total DEADLINE-MATH candidates from Phase 0 §1.2**".

### §0 architect "HIGH with reservation" confidence framing VINDICATED

Per auditor §6: Plan v1 §0 framing acknowledged Bundle 1+2 prior-prediction-blocked history; framing predicted PIs were possible; prediction held. **NEW informal observation banked at architect-memory**: `Architect-PI-direction-prediction-reversed-by-mechanical-overcount` — Plan v1 §0 predicted the PI would surface on D1 semantic classification (most ambiguity-prone surface); actually surfaced on D3 mechanical assert-count overcount (intuitively the LEAST risky surface). 1st instance; 3-instance threshold for sub-rule formalization.

### §0 NEW operational rule extension candidacy

Per auditor §3 #6: Pass-2 grep at Plan v1 drafting MUST verify counts **ARITHMETICALLY** — not just enumerate sites; sum bucket cells + verify against TOTAL row. Bundle 3 Plan v1 surfaced this gap (3 of 3 PIs were arithmetic-class). Operational rule extension candidate to `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` discipline: 3-part Pass-2 grep rule extends to 4-part (1) symbol-name uniqueness + (2) behavioral-semantic + (3) symmetric verification + (4) **ARITHMETIC SUM-AGAINST-TOTAL verification**.

---

## §1 PI absorption + corrected scope

### §1.1 PI #1 absorbed — §1.14 assert count corrected 48 → 44

**Plan v2 §1.14 (corrected)**:

| Bucket | Sites | Exception class | Notes |
|---|---|---|---|
| `pipeline.py` line 1746 | 1 | RuntimeError | Skeptic-1 BUG-2 canonical site |
| `pipeline.py` lines 2020, 2023, 2026, 2029, 2032 | **5** (was "~9" in Plan v1 — fabricated) | RuntimeError | BUG-9 cluster (Q1 hybrid disposition; assert→raise + docstring reconciled per §1.1 below) |
| `pipeline.py` line 6615 | 1 | RuntimeError | Default |
| `pipeline.py` lines 6639, 6645, 6665, 6671, 6676, 6696, 6702 | 7 | RuntimeError | Default mechanical replacement |
| `core/brain_db_migrations.py` (18 sites) | 18 | RuntimeError | Q2 ratified |
| `core/faces_db_migrations.py` (11 sites) | 11 | RuntimeError | Q2 ratified |
| `core/db.py` (1 site) | 1 | RuntimeError | Default |
| **TOTAL** | **44 sites** (Phase 0 baseline preserved; no Pass-2 refinement event) | All `RuntimeError` | Mechanical-extraction discipline |

**Architect-side independent grep verification at Plan v2 drafting time** (per BIDIRECTIONAL-VALIDATION sub-rule active for Bundle 3+): `grep -n "^\s*assert " pipeline.py` returns 14 lines at 1746, 2020, 2023, 2026, 2029, 2032, 6615, 6639, 6645, 6665, 6671, 6676, 6696, 6702. Matches auditor's independent grep. PI #1 absorption confirmed by both actors' fresh Pass-2 grep.

### §1.2 PI #2 absorbed — §1.8 footer arithmetic corrected 231 → 230

**Plan v2 §1.8 (corrected math)**: production WALLCLOCK = 186 (was 187 in Plan v1; reconciler.py adjustment 1 → 0 applied per docstring-only false-positive). Production TOTAL = 28 (DEADLINE-MATH) + 186 (WALLCLOCK) + 16 (AMBIGUOUS) = **230 sites**.

Phase 0 grep-count = 233. Production-call count = 230. Difference = 3 docstring false-positives (1 in `core/reconciler.py` + 2 in `core/reconciler_state.py`).

### §1.3 PI #3 absorbed — §1.9 enumeration header corrected

**Plan v2 §1.9 (corrected header)**: "Initial Pass-1 **12 pipeline.py DEADLINE-MATH sites + 1 core/brain_agent.py site (per §1.10)** = 13 total DEADLINE-MATH candidates from Phase 0 §1.2".

Enumeration of 12 pipeline.py sites unchanged:
1. `pipeline.py:963` silence TTL check
2. `pipeline.py:2773` `_deadline = time.time() + VISION_WATCHDOG_RESTART_TIMEOUT_SECS`
3. `pipeline.py:2774` `while time.time() < _deadline:` (Skeptic-1's canonical example; same cluster as #2 but separate line/expression)
4. `pipeline.py:2915` GREET_COOLDOWN check
5. `pipeline.py:3313` cloud-state elapsed
6. `pipeline.py:3396` face-in-frame staleness
7. `pipeline.py:5636` YOLO throttle
8. `pipeline.py:5758` cloud-flap elapsed (BUG-10 race adjacent)
9. `pipeline.py:7454` face-loss grace_expired
10. `pipeline.py:7753` face-loss grace_expired (second site)
11. `pipeline.py:8419` presence recognized elapsed
12. `pipeline.py:8457` face-in-frame staleness (second site)

13th candidate (cross-file): `core/brain_agent.py:6908` `_rebuild_secs = time.time() - _rebuild_t0` (Kuzu graph rebuild duration). Per §1.10 detailed enumeration scope.

### §1.4 §3.1 A1+A3 fan-out corrected

Plan v1 §3.1 claimed "A1 + A3 parametrize fan-out estimate: ~28 + 48 = ~76 collections". Plan v2 corrects to **~28 + 44 = ~72 pytest collections**.

### §1.5 §4.1 D3 file-impact corrected

Plan v1 §4.1 D3 row claimed "48 line-level edits". Plan v2 corrects to **44 line-level edits**.

### §1.6 §6 closure-narrative paste template corrected

Plan v1 §6 paste template had 4 instances of "48 sites" / "48-site" / "48 assert sites". Plan v2 §6 (below) replaces all 4 with "44 sites" / "44-site" / "44 assert sites".

### §1.7 §5.3 doctrine banking revisions

Plan v1 §5.3 banked `Plan-v1-Pass-2-grep-undercount` 14 → 15 with rationale "Plan v1 §1.14 refined assert count 44 → 48 at Pass-2 grep". Plan v2 **WITHDRAWS** this banking — there was no real undercount; the "+4 refinement event" was fabricated.

**Final banking at Bundle 3 closure** (corrected):
- `Plan-v1-Pass-2-grep-undercount` STAYS at 14 (no Bundle 3 instance)
- NEW `Plan-v1-Pass-2-grep-OVERCOUNT` informal observation 1st instance banked at architect-memory (Bundle 3 Plan v1 §1.14 phantom +4 site claim)
- `Per-artifact-arithmetic-drift-survives-grep-baseline` 16 → **18 instances** (+2 from PI #2 §1.8 footer arithmetic + PI #3 §1.9 enumeration mismatch; same internal-to-artifact arithmetic class as Bundle 2 PI #1+#2)
- `Zero-precision-items-pre-closure-predictions-blocked` 5 → **6 instances** (Plan v1 §12 confidence framing "HIGH with reservation" blocked by 3 PIs — 6th instance STRENGTHENS sub-rule elevation candidacy beyond Bundle 2's 5-instance threshold)
- `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` 10 → **11 instances** — CAUGHT-REAL-GAP event (auditor Pass-2 grep on §1.14 BUG-9 cluster caught architect's overcount). Doctrine's PRESENCE-of-catching property validated; sustained dual-actor validation.

### §1.8 Plan v1 baseline counts grep-verified at Plan v2 drafting

Per `### Grep-baseline-before-drafting` + +1 per artifact convention (4-artifact cycle):
- Strict-industry-standard mode applications: 121 (Plan v1) → **122** (Plan v2) → 123 (closure)
- Spec-first review cycle: 130 → **131** → 132
- `### Grep-baseline-before-drafting`: 88 → **89** → 90
- Cross-cycle-handoff transparency: 91 → **92** → 93
- Spec-time grep-verification: 98 → **99** → 100

---

## §2 D-decisions UNCHANGED from Plan v1

D1-D5 + Cross-D shipping order + all Q1-Q8 ratifications PRESERVED verbatim from Plan v1 §2.

Only changes vs Plan v1:
- D3 scope: 48 → 44 assert sites (per §1.1 absorption)
- §3.1 A1+A3 fan-out: 76 → 72 (per §1.4 absorption)
- §4.1 D3 file-impact: 48 → 44 line-level edits (per §1.5 absorption)

---

## §3 Q5 LOCK at mid 5 + closure-projection band table UNCHANGED

Q5 LOCK at mid 5 anchors UNCHANGED. NARROW band [4.25, 5.75]. Falsification: ≤3 OR ≥8. Phase 4 strengthening caveat preserved.

### §3.1 Anchor breakdown finalized (A1+A3 fan-out corrected)

| # | Anchor | Type | Scope |
|---|---|---|---|
| A1 | D1 deadline-math migration | structural parametrize (~28 DEADLINE-MATH sites) + behavioral test for vision watchdog under simulated NTP-jump | source-inspection + 1 behavioral |
| A2 | D2 AST invariant (no `time.time()` in deadline contexts) | structural — AST walk + `# WALLCLOCK:` allowlist + self-test | 1 AST test + 2-3 self-test cases |
| A3 | D3 assert → raise replacement | structural parametrize (**44 assert sites**) + behavioral test that `python -O` doesn't bypass invariants | source-inspection + 1 behavioral |
| A4 | D4 AST invariant (no production `assert`) | structural — AST walk + path-based allowlist + self-test | 1 AST test + 2 self-test cases |
| A5 | D5 CI integration + closure-narrative | source-inspection | 1 on workflow + 1 on banner |

**Total = 5 logical anchors UNCHANGED. NARROW band [4.25, 5.75]. Q5 LOCK = 5.**

A1 + A3 parametrize fan-out: **~28 + 44 = ~72 pytest collections** (was 76 in Plan v1; corrected per PI #1 absorption).

---

## §4 Cross-spec impact (file-impact table corrected)

### §4.1 File-impact table (Plan v2 corrected per PI #1)

| D | New files | Modified files | Approx total |
|---|---|---|---|
| D1 | `tools/migrate_time_monotonic.py` | ~21 production files | ~28 deadline-math line-level edits + ~186 WALLCLOCK annotations (subset; many sites already have context comments) |
| D2 | `tests/test_no_walltime_deadline_math.py` (NEW) | None | 1 new test file |
| D3 | `tools/migrate_assert_raise.py` | 4 files (`pipeline.py` 14 + brain_db_migrations 18 + faces_db_migrations 11 + db.py 1) | **44 line-level edits** (was 48; PI #1 absorbed) + docstring updates at BUG-9 cluster (5 sites within the 14 pipeline.py count) |
| D4 | `tests/test_no_production_assert.py` (NEW) | None | 1 new test file |
| D5 | — | `CLAUDE.md` banner + Architectural Disciplines section | 1 banner + 1 doctrine note |

**Total scope (Plan v2 corrected)**: 4 new files (2 mechanical scripts + 2 test files) + ~72 line-level production-code edits (28 DEADLINE-MATH + **44 assert→raise**) + ~186 `# WALLCLOCK:` annotation candidates.

### §4.2 No further git ripple — UNCHANGED from Plan v1 §4.2

### §4.3 Bundle 3.X (BUG-15) deferred — UNCHANGED from Plan v1 §4.3

### §4.4 Bundle 4-5 unchanged dependencies — UNCHANGED from Plan v1 §4.4

---

## §5 Discipline counts (4-artifact cycle — Plan v2 absorbs)

### §5.1 Per-artifact-driven disciplines (UPDATED — 4-artifact, not 3)

| Discipline | Pre-Bundle-3 | Phase 0 | Plan v1 | **Plan v2** | Closure |
|---|---|---|---|---|---|
| Strict-industry-standard mode applications | 119 | 120 | 121 | **122** | 123 |
| Spec-first review cycle | 128 | 129 | 130 | **131** | 132 |
| `### Grep-baseline-before-drafting` | 86 | 87 | 88 | **89** | 90 |
| Cross-cycle-handoff transparency | 89 | 90 | 91 | **92** | 93 |
| Spec-time grep-verification | 96 | 97 | 98 | **99** | 100 |

### §5.2 Closure-event disciplines — PRESERVED from Plan v1 §5.2

### §5.3 NEW doctrine instances banked at Plan v2 + closure (CORRECTED)

| Discipline | Pre-Bundle-3 | After Plan v2 | After closure | Cycle event |
|---|---|---|---|---|
| `Plan-v1-Pass-2-grep-undercount` | 14 | **14 (STAYS)** | 14 | Plan v1's claimed 14 → 15 banking WITHDRAWN at Plan v2 absorption per PI #1 (no real undercount surfaced) |
| `Plan-v1-Pass-2-grep-OVERCOUNT` (NEW informal candidate; opposite-direction sibling) | 0 | **+1 instance** | 1 | Bundle 3 Plan v1 §1.14 fabricated +4 sites; auditor Pass-2 caught; 3-instance threshold for sub-rule under parent |
| `Per-artifact-arithmetic-drift-survives-grep-baseline` | 16 | **18** | 18 | +2 (PI #2 §1.8 footer 231 → 230 + PI #3 §1.9 13 → 12 enumeration mismatch); same internal-to-artifact arithmetic class as Bundle 2 PI #1+#2 |
| `Zero-precision-items-pre-closure-predictions-blocked` | 5 | **6** | 6 | Plan v1 §12 "HIGH with reservation" blocked by 3 PIs at Plan v1 review; 6th instance STRENGTHENS sub-rule elevation candidacy beyond Bundle 2's 5-instance threshold |
| `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` | 10 | **11** | 11 | CAUGHT-REAL-GAP event (auditor Pass-2 grep on §1.14 BUG-9 cluster caught architect's overcount); sustained dual-actor validation |
| OPTIONAL-Plan-v2 sub-rule track record | 19 | 19 (cycle escalated) | **STAYS at 19** | Bundle 3 ships 4-artifact; 3rd consecutive blocked Pre-P1 bundle confirms broader "Pre-P1 = multi-axis precision regardless of work category" pattern signal |
| `Doctrine-prediction-precision-improving-over-arc` 0%-streak | 11 | TBD | **12 IF closure-actual = 5 exact** | Conditional on closure-actual matching Q5 LOCK |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 32 supporting | TBD | **33 (if within NARROW band [4.25, 5.75])** | Conditional |
| `### Phase-0-catches-wrong-premise` | 13 | **STAYS 13** | 13 | Bundle 3 PIs were precision/arithmetic events NOT wrong-premise; premise was ON-TARGET |
| `Spec-scope-boundaries-consistent-across-bundles` (NEW informal candidate) | 0 | **+1 instance** | 1 | Bundle 2 D6 SPDX scope → Bundle 3 D2 AST invariant scope = same path enumeration; 3-instance threshold |
| `Docstring-mention-counted-in-grep-total` (NEW informal candidate) | 0 | **+1 instance** | 1 | Plan v1 §1.8 identified 3 docstring false-positives in reconciler.py + reconciler_state.py grep counts |
| `Architect-PI-direction-prediction-reversed-by-mechanical-overcount` (NEW informal candidate) | 0 | **+1 instance** | 1 | Architect's §0 prediction "PI on D1 semantic" REVERSED — PI on D3 mechanical-overcount instead; 3-instance threshold for sub-rule formalization |

### §5.4 Multi-discipline preventive convergence enumeration — UPDATED at Plan v2

Plan v1's 10 preventive disciplines PRESERVED.

**Plan v2 ADDS 1 NEW preventive application**:
11. **BIDIRECTIONAL architect+auditor Pass-2 grep verification at Plan v2 drafting** — architect ran fresh `grep -n "^\s*assert " pipeline.py` returning 14 lines (matching auditor's count); convergent reading locked the 44-site total. Same shape as Bundle 2 Plan v2 BIDIRECTIONAL Pass-3 file-count verification but at semantic-classification-correctness axis instead.

**11 preventives applied at Bundle 3 Plan v2** (was 10 at Plan v1; was 9 at Bundle 2 closure). **Multi-discipline preventive convergence trajectory CONTINUES STRENGTHENING**: Bundle 1 (7) → Bundle 2 Plan v3 (9) → Bundle 3 Plan v1 (10) → Bundle 3 Plan v2 (11).

### §5.5 NEW operational rule extension banked at Plan v2 §0

Per auditor §3 #6: Pass-2 grep at Plan v1 drafting MUST verify counts ARITHMETICALLY (not just enumerate sites). Bundle 3 surfaced this gap (3 of 3 PIs were arithmetic-class).

**Operational rule extension candidate** banked under `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine:
- 3-part Pass-2 grep rule extends to **4-part**:
  1. Symbol-name-uniqueness grep
  2. Behavioral-semantic verification
  3. Symmetric verification (reject + preserve classes)
  4. **ARITHMETIC SUM-AGAINST-TOTAL verification** (NEW; per Bundle 3 lesson)

3-part rule held for P0.S10 Plan v4 + Bundle 2 Plan v3. Bundle 3 surfaces the 4th part need. If 2 more instances of arithmetic-axis PIs surface at future cycles, formalize the 4-part rule.

---

## §6 Closure-narrative paste template (Plan v2-aware)

```markdown
| **Pre-P1 Bundle 3 (Critical bugs MF4 + MF5 — time.monotonic() deadline-math migration across ~28 sites + assert → if-not-raise mechanical replacement across 44 sites + 2 NEW AST invariant tests + 2 NEW mechanical scripts — 4-artifact cycle [Phase 0 + Plan v1 + Plan v2 absorbed PI #1+#2+#3 + closure] / 20th OPTIONAL-Plan-v2 proof case STAYS at 19 for 3rd consecutive blocked Pre-P1 bundle confirming multi-axis-precision pattern) CLOSED 2026-05-2X** — [SUMMARY: production `time.time()` deadline-math migrated to `time.monotonic()` at ~28 sites with `# WALLCLOCK:` annotation discipline preserving observability across ~186 wallclock sites; cross-process IPC sites in core/state.py EXPLICITLY excluded; production `assert` statements migrated to `if not...: raise RuntimeError(...)` at 44 sites across pipeline.py (14) + 2 migration files (29) + core/db.py (1); BUG-9 hybrid disposition replaced assert + reconciled docstring at pipeline.py:2020-2032 cluster (5 sites); 2 new AST invariant tests (test_no_walltime_deadline_math.py + test_no_production_assert.py) lock structural invariants in CI]. **N/N anchor tests A1-A5 GREEN** with A1+A3 parametrize fan-out covering ~72 pytest collections (was 76 estimate in Plan v1; corrected at Plan v2 PI #1 absorption from fabricated 48 → 44 assert count). **5/5 deliberate-regression confirmations passed cleanly** per `### Induction-surfaces-invariant-gaps`. **Doctrine bumps banked**: `Per-artifact-arithmetic-drift-survives-grep-baseline` 16 → 18 (+2: PI #2 §1.8 footer 231 → 230 + PI #3 §1.9 13 → 12 enumeration mismatch). `Zero-precision-items-pre-closure-predictions-blocked` 5 → 6 (Plan v1 confidence framing blocked by 3 PIs; sub-rule elevation candidacy STRENGTHENS beyond Bundle 2's 5-instance threshold). `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` 10 → 11 (CAUGHT-REAL-GAP event; auditor Pass-2 grep caught architect's BUG-9 cluster overcount). NEW `Plan-v1-Pass-2-grep-OVERCOUNT` informal observation 1st instance (opposite-direction sibling of undercount discipline). NEW `Spec-scope-boundaries-consistent-across-bundles` 1st instance + NEW `Docstring-mention-counted-in-grep-total` 1st instance + NEW `Architect-PI-direction-prediction-reversed-by-mechanical-overcount` 1st instance. OPTIONAL-Plan-v2 sub-rule **STAYS at 19** (3rd consecutive blocked Pre-P1 bundle confirms broader "Pre-P1 = multi-axis precision regardless of work category" pattern signal). `### Phase-0-granular-decomposition` 32 → 33 supporting (if closure-actual within NARROW band [4.25, 5.75]). `Doctrine-prediction-precision-improving-over-arc` 12th consecutive 0%-streak (if closure-actual = 5 exact). Strict-mode 119 → 123 applications + 34 → 35 closures (4-artifact cycle). **Multi-discipline preventive convergence 11 disciplines applied** at Bundle 3 Plan v2 (was 9 at Bundle 2 closure; trajectory STRENGTHENS strongly across 3 consecutive bundles). **NEW operational rule extension candidacy banked at Plan v2 §0** for `### Pass-2-grep-auditor-verified-before-Plan-v1-approval`: 3-part Pass-2 grep rule extends to 4-part with ARITHMETIC SUM-AGAINST-TOTAL verification (Bundle 3 surfaced gap; 3-of-3 PIs were arithmetic-class). Third Pre-P1 must-fix bundle CLOSED; 2 bundles remain per CEO synthesis. **No CI evidence event required** for governance-style work; new AST invariant tests run automatically in fast.yml default-include.
```

---

## §7 Honest-count commitment — STRENGTHENED at Plan v2

Per `Explicit-closure-honest-count-commitment` discipline:

- Plan v2 §7 MADE → closure §7 HONORED counts as 2 separate instances
- Bundle 3 total: Plan v1 + Plan v2 + closure = 3 commitment events (2 MADE + 1 HONORED) for 4-artifact cycle
- Architect commits to honest closure-actual reporting regardless of which band falls
- IF closure-actual = 5 exact: `Doctrine-prediction-precision-improving-over-arc` 12th-streak banks
- IF closure-actual ∈ {4, 6} → ON-TARGET via SLIGHT-DRIFT within ±15%; doctrine bumps; streak interrupted
- IF closure-actual ∈ {3, 7} → SLIGHT-DRIFT within ±30%; doctrine HOLDS; streak interrupted
- IF closure-actual ≤2 OR ≥8 → FALSIFICATION-WATCH activates

---

## §8 Plan v3 path adjudication (defensive)

Per `### Zero-precision-items-at-auditor-review` doctrine: if auditor returns Plan v2 review with NEW PIs (would be 2nd-tier absorption event), cycle escalates to 5-artifact (Plan v3 absorbs).

Plan v2 covers:
- ✓ PI #1 §1.14 assert count 48 → 44 (BUG-9 cluster corrected from "~9" → 5 actual sites)
- ✓ PI #2 §1.8 footer 231 → 230 (WALLCLOCK adjustment applied to TOTAL)
- ✓ PI #3 §1.9 header 13 → "12 pipeline.py + 1 brain_agent.py (per §1.10) = 13 total"
- ✓ §3.1 A1+A3 fan-out 76 → 72 cascade applied
- ✓ §4.1 D3 file-impact 48 → 44 cascade applied
- ✓ §6 closure-narrative paste template 4× "48 sites" → "44 sites" cascade applied
- ✓ §5.3 doctrine bumps revised (Plan-v1-Pass-2-grep-undercount banking WITHDRAWN; OVERCOUNT 1st instance banked)
- ✓ §0 architect "HIGH with reservation" framing VINDICATED + REVERSED-direction observation banked
- ✓ §5.4 11-discipline preventive convergence enumeration with BIDIRECTIONAL Pass-2 grep verification 11th preventive
- ✓ §5.5 4-part Pass-2 grep operational rule extension candidate banked

**Architect's Plan v2 confidence: HIGH (with strengthened reservation)**. Honest epistemic stance: Plan v1 confidence was "HIGH with reservation" + 3 PIs surfaced. Plan v2 confidence is "HIGH with STRENGTHENED reservation" — explicitly acknowledges that PI direction (D3 mechanical overcount, not D1 semantic) reversed the prediction; arithmetic-class PIs were not anticipated. If Plan v2 review surfaces NEW PIs on the corrected scope OR on a different axis (e.g., D1 classification semantic precision), cycle escalates to Plan v3. Bundle 3 has demonstrated that confidence stated unconditionally has been blocked.

---

## §9 Procedural commitments (closure-audit) — PRESERVED from Plan v1 §9

All 8 procedural commitments preserved verbatim. Plan v2 adds 0 NEW commitments — Phase 0 + Plan v1 framework sufficient.

---

## §10 Known Limitations — PRESERVED from Plan v1 §10 + extended

Plan v1 §10 limitations 1-7 PRESERVED verbatim.

8. **NEW (Plan v2)**: `Plan-v1-Pass-2-grep-OVERCOUNT` failure mode banked as opposite-direction sibling of undercount discipline. Architect's Pass-2 grep at Plan v1 §1.14 fabricated +4 site count without grep-evidence support. Future cycle drafting must apply 4-part Pass-2 grep operational rule extension (arithmetic sum-against-total verification) to prevent recurrence. Operational rule extension formal candidacy at 3-instance threshold.

9. **NEW (Plan v2)**: Architect PI-direction prediction reversed. Plan v1 §0 predicted PI would surface on D1 semantic classification (most ambiguity-prone surface). Actually surfaced on D3 mechanical assert-count overcount. NEW informal observation `Architect-PI-direction-prediction-reversed-by-mechanical-overcount` banked at architect-memory. 3-instance threshold for sub-rule formalization candidacy.

---

## §11 Architect Pass-3 grep clearance + arithmetic re-verification

Per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine + 4-part operational rule extension candidacy (per §5.5):

1. **Symbol-name-uniqueness grep** ✓ — UNCHANGED from Plan v1 §11.
2. **Behavioral semantic verification** ✓ — UNCHANGED.
3. **Symmetric verification** ✓ — UNCHANGED.
4. **ARITHMETIC SUM-AGAINST-TOTAL verification** ✓ NEW at Plan v2 §0: bucket cells sum to 230 (DEADLINE 28 + WALLCLOCK 186 + AMBIGUOUS 16) matching corrected TOTAL row; §1.14 sub-totals sum to 44 (1+5+1+7+18+11+1) matching corrected TOTAL.

### §11.1 Layer 3 None-check verification for BUG-9 hybrid — PRESERVED from Plan v1 §11.1

UNCHANGED. Plan v2 trusts existing Layer 3 None-handling per Skeptic-1's framing; Phase 4 developer verifies + adds explicit None-guards if any of the 3 RoomOrchestrator methods lacks one.

---

## §12 Standing by for auditor Plan v2 verdict

If CLEAN (0 PIs) → Plan v2 ships to developer for Phase 4 implementation resumption; cycle closes as 4-artifact.

If PIs surface → Plan v3 absorbs; cycle escalates to 5-artifact (matches P0.S5 / P0.B2 / Bundle 2 historical Plan v3 cycles).

**Architect's Plan v2 confidence: HIGH (with strengthened reservation)** per §8. Honest epistemic stance: PI direction was REVERSED at Plan v1 review; arithmetic-class PIs surfaced unexpectedly; Plan v2 has applied 4-part Pass-2 grep rule + arithmetic sum-against-total verification to absorb all 3 PIs cleanly. If Plan v2 absorption is itself incorrect OR new PI axis surfaces, Plan v3 absorbs.

---

**Filed**: 2026-05-28
**Architect**: Claude
**Forwarded to**: Auditor (external)
**Prior artifact**: `tests/pre_p1_bundle3_critical_bugs_plan_v1.md` (BLOCKED by 3 PIs: PI #1 §1.14 assert overcount 48 → 44 + PI #2 §1.8 footer 231 → 230 + PI #3 §1.9 header 13 vs 12 enumerated; absorbed at Plan v2 per auditor §3 absorption instructions)
