# Pre-P1 Bundle 5 — Contract Typing (MF7 + MF8) Plan v3 (2026-05-29)

**Cycle**: Pre-P1 must-fix Bundle 5 (Contract Typing) — FINAL Pre-P1 bundle — 5-artifact cycle (Phase 0 + Plan v1 + Plan v2 + Plan v3 + closure)
**Predecessor**: `tests/pre_p1_bundle5_contract_typing_plan_v2.md` (Plan v2 NOT CLEAN — 1 PI: §8's "15 test-fake sites, exhaustively grep-verified, complete, zero-deferral" falsified; true floor ≥17; auditor verdict in `info.md` 2026-05-29)
**Scope of this artifact**: A BOUNDED METHODOLOGY RE-SCOPE of the test-fake surface framing (Plan v2 §1.2 + §8). **NOT a re-grep chasing an exact count** — that is the recursion trap (auditor §3). Everything else in Plan v2 carries forward RATIFIED + unchanged.
**Architect**: Claude
**Auditor**: External

---

## §0 The PI + the lesson (auditor §2-§4 — absorbed)

### §0.1 What was falsified

Plan v2 §8 claimed "15 test-fake sites (grep-verified across 7 test files)... No deferred greps remain. Every count in this Plan v2 is grep-verified at drafting." The auditor's definitive unbounded grep found **≥17**, not 15. Two peers of sites I already listed:

| Missed site | Pattern | Peer I DID list |
|---|---|---|
| `test_brain_agent.py:6993` | `_vs.identify = MagicMock(return_value=(None, 0.0))` | `test_pipeline.py:35` (`_vs.identify`) — listed |
| `tests/test_user_text_gate_invariants.py:96` | `_voice_stub.identify = _AsyncMock(return_value=(None, 0.0))` | `test_user_text_gate_multiword.py:32` (identical pattern, sibling P0.3 file) — listed |

**Architect targeted confirmation (2026-05-29, BIDIRECTIONAL — NOT an exhaustive re-sweep)**: both cited sites grep-confirmed real (`test_brain_agent.py:6993` MagicMock ✓; `tests/test_user_text_gate_invariants.py:96` _AsyncMock ✓). The `_invariants` miss is the sharpest self-indictment: my Plan v2 grep found the `_multiword` sibling but not the `_invariants` one in the same pass — directly falsifying the "exhaustive/complete" claim.

### §0.2 The recursion IS the finding

**auditor ~8 → architect 15 → auditor 17.** Three independent careful greps, each undercounting the next. The auditor's call (which I fully accept): this is NOT a signal to demand "Plan v4, find the 18th" — that would risk a 19th in a file no one has opened, and the recursion would just continue. The recursion is **evidence of a surface-class distinction the discipline has been missing.**

### §0.3 The surface-class distinction (the bundle's deepest lesson — adopted)

| Surface class | This bundle's instance | Failure mode if a site is missed | Correct discipline |
|---|---|---|---|
| **HARD-BREAK** | the 3 production `voice.identify` callers (pipeline.py 2439/7539/7804) | **Silent ship-breakage** — `ValueError` in a live code path that may not be test-covered; blast radius = users | **MUST be exhaustively enumerated + verified at Plan stage.** This was the v1→v2 BLOCKING PI — correctly absorbed; genuinely exhaustive now (3, bounded, grep-verified). ✓ |
| **SELF-CORRECTING** | the ≥17 test-fakes (`*.identify =` / `patch(...identify` / `identify_fn=`) | **Loud failure at test time** — a missed 2-tuple stub that's actually exercised raises `ValueError` immediately in the test run; caught fast, fixed cheap, NEVER ships | **Delegate-with-mechanism to Phase 4 developer Pass-3 grep + the test-run `ValueError` backstop.** Exhaustive Plan-stage pre-enumeration of this scattered surface is precisely what produced the 8→15→17 recursion. |

### §0.4 Reconciliation with `feedback_pass_2_grep_deferral_pattern.md` (NOT a contradiction)

The deferral doctrine flags deferral as undercount risk **for surfaces that ship broken silently** — which is exactly why the Plan v1 hidden production-caller deferral was the right thing to escalate (HARD-BREAK + hidden behind a false-complete claim = the worst case). The doctrine does NOT forbid delegating a SELF-CORRECTING surface, provided the delegation is **OPEN and mechanism-backed**, not hidden behind a false "complete" claim. The honest move for the test-fakes is: name the detection mechanism + the known floor, delegate completion to Phase 4 — NOT claim an exhaustive Plan-stage count that keeps drifting. **Plan v1's sin was a hidden HARD-BREAK deferral; Plan v2's sin was a false-exhaustive SELF-CORRECTING claim. Plan v3 fixes the latter by being honest about the surface class.**

---

## §1 The re-scope (auditor §4 — the ONLY substantive change in this artifact)

### §1.1 Production-caller surface — UNCHANGED, genuinely exhaustive (HARD-BREAK)

The 3 `voice.identify` callers stay exactly as Plan v2 §1.1 / §2 D2c locked:
- `pipeline.py:2439` (`_accumulate_voice`) → `v_pid, v_score, _ = ...`
- `pipeline.py:7539` (voice-first ambient) → `v_pid, v_score, _ = ...`
- `pipeline.py:7804` (per-turn → reconciler) → `_v_pid, _v_score, _v_is_no_signal = ...` + `_build_routing_inputs(..., v_score_is_no_signal=_v_is_no_signal)`

**This surface IS claimed exhaustive-at-Plan-stage and grep-verified** (unbounded `identify\(` grep on pipeline.py; no hidden 4th; auditor §2 + §5 ✓). It is the load-bearing surface — a missed caller ships silent breakage. The "exhaustive/complete/verified" claim is preserved HERE because it is true here.

### §1.2 (REVISED) Test-fake surface — Phase-4-developer-Pass-3-grep-completed (SELF-CORRECTING)

The test-fake surface is **NOT claimed exhaustive at Plan stage.** It is a self-correcting surface (loud `ValueError` at test time on any invoked-but-unmigrated stub) delegated to the Phase 4 developer with an explicit detection mechanism:

**(a) Known floor: ≥17 sites** (the Plan v2 §1.2 list of 15 + the 2 auditor-found peers):

*test_pipeline.py (9)*: 35, 6500, 6604, 6640, 6683, 6722, 6763, 8246, 8295
*global `_voice_stub`/`_vs` stubs (6)*: conftest.py:57, test_dispute_auto_clear.py:29, test_multispeaker_integration.py:39, test_user_text_gate_multiword.py:32, **test_brain_agent.py:6993** (NEW), **tests/test_user_text_gate_invariants.py:96** (NEW)
*`identify_fn`-injected fakes (2)*: test_event_log_producer_coverage.py:160 (lambda), test_voice_channel.py:56 (`_fake_identify_factory`)

All return 2-tuples today; all must return 3-tuples (`(pid, score, is_no_signal)`) after D2a/D2b — `(None, 0.0, True)` for no-signal stubs, `(pid, score, False)` for match/gallery-miss stubs. The `_fake_identify_factory` gets an optional `is_no_signal: bool = False` param.

**(b) Phase-4 developer detection mechanism (the delegation contract)**:
1. **Grep sweep** at Phase 4 pre-implementation (developer Pass-3 — the numbered `### Developer-Pass-3-grep-at-Phase-4-pre-implementation` doctrine): `\.identify\s*=` + `patch\([^)]*identify` + `identify_fn=` across `test_pipeline.py` + `tests/` + any root-level `test_*.py`, inspect each match for a non-3-tuple return, convert.
2. **Test-run `ValueError` backstop**: run the full suite. Any invoked-but-unmigrated 2-tuple stub feeding a 3-target unpack raises `ValueError: too many values to unpack` immediately — a loud, located, cheap-to-fix failure. The green suite IS the completeness proof for this surface (stronger than any Plan-stage grep count, because it proves every *exercised* stub is correct, not merely every *enumerated* one).

**(c) Explicit non-claim**: this surface is **NOT** claimed exhaustive-at-Plan-stage. The 8→15→17 recursion proves exhaustive pre-enumeration is the wrong goal for a scattered self-correcting surface. The ≥17 is a KNOWN FLOOR to seed the developer's sweep, not a complete count. If the Phase-4 sweep + suite-run surface an 18th, that is the mechanism working as designed — not a Plan-stage miss.

### §1.3 (REVISED) §8 claim scope

Plan v2 §8's "exhaustive/complete/zero-deferral" claim is **DROPPED for the test-fake surface** and **PRESERVED for the production-caller surface** (where it is true and load-bearing). The decoder one-liner (D2d, event_log/types.py:124) + the MF8 break-set (exactly 5: test_pipeline.py:8138 + test_session_store.py:260/403/435/532) + the production-edit count (41 / 6 files) all stay exhaustive-claimed — those are bounded, verified, HARD-or-bounded surfaces. Only the scattered self-correcting test-fake surface moves to delegate-with-mechanism.

---

## §2 Everything else — RATIFIED, carries forward unchanged (auditor §5)

No change to any of the following (auditor explicitly cleared; do not re-litigate):
- **Q3 backend-sets architecture** ✓ · **3 production callers** (2439/7539/7804) ✓ · **D2a return points** 430/440/441 (True/False/False) ✓ · **D2d encoder** = `dataclasses.asdict`-automatic, decoder one-liner only ✓
- **D1** (IdentityClaim `confidence_is_no_signal: bool = False` field, frozen preserved) · **D2b** (identify_speaker 5-site + 3-tuple unpack) · **D2e** (6 reconciler predicate migrations: 3 `==`→flag, 2 `!=`→`not flag`, 1 `<=`→`flag or <0`) · **D3** (AST invariant bans Eq+NotEq, allows Lt/LtE) · **MF8 D4-D6** (SessionSnapshot 3 fields list→tuple + _to_snapshot + AST invariant + 5 test updates) ✓
- **§3 arithmetic**: 41 production line edits across 6 files ✓ · **Q5 = 7 HOLDS** ✓ · **MF8 break-set = exactly 5** ✓ · **no positional/field-count breaks** (7th trailing-default field safe) ✓

---

## §3 Q5 LOCK — 7 HOLDS (unchanged)

The re-scope adds NO anchor and changes NO production edit. Q5 = **7. NARROW band [5.95, 8.05].** A7 (MF8) + the test-fake fan-out are verified by the green suite at Phase 4, not by a Plan-stage count. Closure-projection: 7 exact = 0% ON-TARGET → `Doctrine-prediction-precision-improving-over-arc` 13→14 streak.

---

## §4 Discipline counts (5-artifact cycle)

| Discipline | Pre-B5 | P0 | v1 | v2 | **v3** | Closure |
|---|---|---|---|---|---|---|
| Strict-industry-standard mode applications | 126 | 127 | 128 | 129 | **130** | 131 |
| Spec-first review cycle | 135 | 136 | 137 | 138 | **139** | 140 |
| `### Grep-baseline-before-drafting` | 93 | 94 | 95 | 96 | **97** | 98 |
| Cross-cycle-handoff transparency | 96 | 97 | 98 | 99 | **100** | 101 |
| Spec-time grep-verification | 103 | 104 | 105 | 106 | **107** | 108 |

### §4.1 Doctrine adjudications (auditor §6 — ratified + new)

**Ratified (carry to closure):**
- `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` **12 → 13** CAUGHT-REAL-GAP (v1→v2 caller catch)
- `Plan-v1-Pass-2-grep-undercount` **16 → 17**
- `Multi-axis-precision-pattern-across-Pre-P1-bundles` **2 → 3 + RENAME** (architect adopted the methodology-honest name; rebaseline discipline ratified)
- `### Phase-0-catches-wrong-premise` STAYS 13 · `Pre-audit-quantifier-precision-refined-by-grep` STAYS 12 · OPTIONAL-Plan-v2 STAYS 20 · BIDIRECTIONAL STAYS 5 (mutual restraint)

**New from the Plan v2 verdict (auditor §6):**
- The Plan-v2 test-fake-count catch is a **2nd CAUGHT-REAL-GAP this bundle** (auditor catches architect's "exhaustive" Pass-2 grep still undercounting). Banked as a **reinforcing event WITHIN the 13th, NOT a bump to 14** (mutual restraint). **Density flag**: `### Pass-2-grep-auditor-verified` has now fired **three times in one bundle** (v1 caller catch + v2 test-fake-count catch + architect-catches-auditor test-fake direction). That density is strong validation of the doctrine's load-bearing claim — note for closure.
- **NEW informal observation candidate (architect-memory): `Self-correcting-surface-resists-exhaustive-pre-enumeration`** — the 8→15→17 recursion demonstrates that self-correcting surfaces (loud-failure-at-test-time) should be **delegated-with-mechanism**, not exhaustively pre-enumerated at Plan stage. The discipline should classify surfaces as **HARD-BREAK-pre-enumerate** vs **SELF-CORRECTING-delegate**. Reconciles with (does not contradict) `feedback_pass_2_grep_deferral_pattern.md`: deferral is forbidden for silent-ship surfaces, permitted-with-mechanism for loud-fail surfaces. **The bundle's most generalizable lesson.** Watch for recurrence; architect-memory candidate (banked at closure to BOTH memory paths per cross-path discipline).
- **Multi-axis reinforcement**: Bundle 5 exhibits **three precision axes in one bundle** — construction-surface @ Phase 0, caller-fanout @ Plan v1, test-fake-enumeration-recursion @ Plan v2 — strengthening (not weakening) the renamed `across-Pre-P1-bundles` pattern. Note for closure.

### §4.2 Multi-discipline preventive convergence (Bundle 5 — 11-floor preserved + 1 new)

Per `### Multi-discipline-preventive-convergence` (Bundle 3 [11] → Bundle 4 [11] → Bundle 5 [11+1]): the 11 from Plan v2 §5.4 + **NEW 12th candidate: surface-class-aware delegation** (HARD-BREAK-pre-enumerate vs SELF-CORRECTING-delegate — applied preventively at Plan v3 to stop the recursion). Architect notes the 12th but does NOT inflate the floor-claim — banks it as the `Self-correcting-surface-resists-exhaustive-pre-enumeration` observation; convergence count stays 11 at floor with the 12th flagged for closure adjudication (mirroring the BIDIRECTIONAL restraint).

---

## §5 Closure-narrative paste template (Plan v3-aware)

```markdown
| **Pre-P1 Bundle 5 (Contract Typing MF7+MF8 — FINAL Pre-P1 bundle — `IdentityClaim.confidence_is_no_signal` BACKEND-SETS decoupling [voice.identify 3-tuple → 3 production callers + identify_speaker 5-site + reconciler kwarg + event-log decoder + 6-predicate migration] + `SessionSnapshot` 3-field list→tuple — 5-artifact cycle [Phase 0 BLOCKING sole-construction-site PI → Plan v1 re-baseline → Plan v2 BLOCKING caller-fanout PI (1→3) → Plan v3 test-fake surface-class re-scope (≥17 floor, delegate-with-mechanism)]) CLOSED 2026-05-2X** — [SUMMARY: MF7 decouples reconciler from ECAPA exact-0.0 via `confidence_is_no_signal` SET AT THE BACKEND (voice.identify `(pid, score, is_no_signal)`; 3 production callers; identify_speaker 4 no-signal-by-construction + success-path unpack; reconciler.py:112 kwarg; event-log decoder; encoder asdict-auto); 6 reconciler predicates migrated (3 `==`→flag, 2 `!=`→`not flag`, 1 `<=`→`flag or <0` preserving Session-119); ≥17 test-fakes → 3-tuples via Phase-4 Pass-3 grep + ValueError backstop (self-correcting surface, NOT Plan-enumerated); MF8 SessionSnapshot 3 fields list→tuple + _to_snapshot]. **7/7 anchors A1-A7 GREEN**. **N/N deliberate-regression passed**. **Doctrine bumps**: `### Pass-2-grep-auditor-verified` 12→13 CAUGHT-REAL-GAP (fired 3× in-bundle: v1 caller + v2 test-fake-count + architect-catches-auditor). `Plan-v1-Pass-2-grep-undercount` 16→17. `Multi-axis-precision-pattern-across-Pre-P1-bundles` 2→3 ELEVATION + RENAME (dropped false "3-consecutive"; 4/5 bundles blocked; 3 precision axes in Bundle 5). NEW `Self-correcting-surface-resists-exhaustive-pre-enumeration` observation (HARD-BREAK-pre-enumerate vs SELF-CORRECTING-delegate — the bundle's deepest lesson). BIDIRECTIONAL STAYS 5. Phase-0-wrong-premise 13, Pre-audit-quantifier 12, OPTIONAL-Plan-v2 20 all STAY. `Doctrine-prediction-precision-improving-over-arc` 14th 0%-streak (if closure-actual=7). **FINAL Pre-P1 must-fix bundle CLOSED** — all 5 bundles (Docs+CI / Governance / Critical-bugs / Observability+Concurrency / Contract-typing) shipped. Next: P1 cycle (8-10 week clock, 5 parallel tracks). **No CI evidence event required**.
```

---

## §6 Honest-count commitment

Per `Explicit-closure-honest-count-commitment`: Plan v3 §6 MADE → closure §6 HONORED = 2 instances. IF closure-actual = 7 exact → `Doctrine-prediction-precision-improving-over-arc` 14th-streak. {6,8} → ON-TARGET, doctrine bumps, streak interrupted. {5,9} → SLIGHT-DRIFT, doctrine HOLDS, streak interrupted. ≤4 OR ≥10 → FALSIFICATION-WATCH.

---

## §7 Standing by for auditor Plan v3 verdict

This is a bounded methodology re-scope (auditor §4) — production surface ratified + unchanged; the ONLY substantive change is the test-fake surface re-framed as Phase-4-delegate-with-mechanism (≥17 known floor + grep sweep + ValueError backstop) with the false "exhaustive" claim dropped. No D-decision, no architecture, no production-edit count change (41 holds), no anchor change (Q5=7 holds).

If CLEAN → Plan v3 ships to developer for Phase 4 (5-artifact cycle). `Multi-axis-precision-pattern-across-Pre-P1-bundles` 3rd-instance elevation + rename + the NEW `Self-correcting-surface-resists-exhaustive-pre-enumeration` observation LOCK at closure.

**Architect's Plan v3 confidence: HIGH.** The re-scope adopts the auditor's surface-class insight exactly. The production surface (the one that ships breakage) is exhaustively verified; the test-fake surface (the one that fails loud at test time) is honestly delegated with a named mechanism + the ValueError backstop. The recursion stops here — not by finding the 18th, but by recognizing the surface didn't warrant exhaustive pre-enumeration.

---

**Filed**: 2026-05-29
**Architect**: Claude
**Forwarded to**: Auditor (external)
**Prior artifact**: `tests/pre_p1_bundle5_contract_typing_plan_v2.md` (Plan v2 NOT CLEAN — §8 "15 exhaustive" falsified at ≥17; re-scoped here to surface-class-aware delegation, NOT a re-grep)
