# P0.B6 Phase 0 audit — Reconciler test coverage closure (skeptic1 Attack 3 / TODO #176)

**Spec ID:** P0.B6 — sixth cycle in the "Board-bug remediation" track. Per the original strategic plan, this was the LAST planned cycle (test-coverage parallel concern alongside the 10-bug scope). Per `### Twin-filename-pitfall-prevention` operational rule 4: bug-fix specs use `P0.B` prefix.

**Twin-filename pitfall check:** no existing `p0_b6_*` files in `tests/`. Clean disambiguation. **10th preventive instance** of the doctrine.

**Pre-audit premise (from `skeptic1-2026-05-20.md` Attack 3 + earlier session-plan):**

> Severity: MAJOR. The 22-rule reconciler cascade is the LIVE primary routing path (`ROUTING_USE_RECONCILER = True` since 2026-04-29). It is routing every turn in production WITHOUT complete per-rule behavioral test coverage. `tests/test_reconciler.py:1337`: `# TODO(#176): land 22 tests in lockstep with rule bodies.` 22 per-rule acceptance tests not landed.

Original P0.B6 scope (pre-Phase-0 framing): land the 22 per-rule acceptance tests, close the TODO marker, ship #176.

**Cadence prediction (initial, pre-Phase-0):** 22 logical anchors LOCKED by enumeration; MEDIUM-band single-subsystem; v1 → v2 floor likely.

---

## §1. Phase 0 grep verification — PRE-AUDIT PREMISE FALSIFIED

### §1.1 The 22 TODO-enumerated tests — grep-verify AGAINST `tests/test_reconciler.py`

| # | TODO test name | Current file location | Status |
|---|---|---|---|
| 1 | `test_p4_pyannote_vouched_stranger_opens_session` | `tests/test_reconciler.py:379` | **LANDED** ✓ |
| 2 | `test_p0_tier1_hard_mismatch_drops` | `tests/test_reconciler.py:554` | **LANDED** ✓ |
| 3 | `test_p0_tier2_ambiguous_drops_in_multi_session` | `tests/test_reconciler.py:594` | **LANDED** ✓ |
| 4 | `test_p0_short_utterance_holds_current` | `tests/test_reconciler.py:632` | **LANDED** ✓ |
| 5 | `test_p0_short_utterance_no_session_skips` | `tests/test_reconciler.py:664` | **LANDED** ✓ |
| 6 | `test_p1_confident_switch_to_other_pid` | `tests/test_reconciler.py:692` | **LANDED** ✓ |
| 7 | `test_p2_midrange_face_assist_switches` | `tests/test_reconciler.py:727` | **LANDED** ✓ |
| 8 | `test_p2_midrange_face_assist_below_floor_returns_ambiguous` | `tests/test_reconciler.py:772` | **LANDED** ✓ |
| 9 | `test_p2_midrange_no_face_assist_returns_ambiguous` | `tests/test_reconciler.py:813` | **LANDED** ✓ |
| 10 | `test_p3_below_self_match_floor_returns_ambiguous` | `tests/test_reconciler.py:849` | **LANDED** ✓ |
| 11 | `test_p3_thin_stranger_skips_offscreen_floor` | `tests/test_reconciler.py:881` | **LANDED** ✓ |
| 12 | `test_p3_offscreen_mature_floors_apply` | `tests/test_reconciler.py:935` | **LANDED** ✓ |
| 13 | `test_p3_self_match_with_face_holds_current` | `tests/test_reconciler.py:969` | **LANDED** ✓ |
| 14 | `test_p3_5_bootstrapping_stranger_holds_current` | `tests/test_reconciler.py:997` | **LANDED** ✓ |
| 15 | `test_p4_multi_segment_mismatch_drops_in_multi_known` | `tests/test_reconciler.py:1032` | **LANDED** ✓ |
| 16 | `test_p4_new_stranger_below_threshold` | `tests/test_reconciler.py:1067` | **LANDED** ✓ |
| 17 | `test_p4_single_segment_mismatch_drops_in_multi_known` | `tests/test_reconciler.py:1097` | **LANDED** ✓ |
| 18 | `test_p4_voice_ambiguous_no_candidates_holds_current` | `tests/test_reconciler.py:1144` | **LANDED** ✓ |
| 19 | `test_p4_voice_ambiguous_with_candidates_returns_ambiguous` | `tests/test_reconciler.py:1179` | **LANDED** ✓ |
| 20 | `test_p5_no_session_opens_stranger` | `tests/test_reconciler.py:1213` | **LANDED** ✓ |
| 21 | `test_p5_no_session_returns_no_action` | `tests/test_reconciler.py:341` | **LANDED** ✓ |
| 22 | `test_last_resort_ambiguous_when_low_score_other_pid` | `tests/test_reconciler.py:1241` | **LANDED** ✓ |

**All 22 enumerated tests are LANDED.** The TODO comment at `tests/test_reconciler.py:1337` is **STALE — documentation-vs-reality drift**.

### §1.2 Phase 0 verdict — PRE-AUDIT PREMISE FALSIFIED. `### Phase-0-catches-wrong-premise` 8th instance.

**Original pre-audit framing**: "22 per-rule acceptance tests are not landed."

**Grep-verified reality**: 22 per-rule tests ARE landed. File `tests/test_reconciler.py` has **34 total test functions** (24 of which are the per-rule acceptance tests visible at the grep above, plus 10 additional structural/contract/regression tests landed earlier).

**Root cause of wrong premise**: the skeptic1-2026-05-20 attack was based on reading the TODO comment text WITHOUT grep-verifying against the actual test functions in the same file. The TODO comment is stale — tests were landed (presumably in PR #176 itself, completing what the TODO predicted) but the TODO marker comment was never removed. Same documentation-vs-reality drift class as **P0.B2 Bug 2** (where `test_faiss_atomicity_invariants.py:29-32` claimed slow-tier crash-test coverage that didn't exist — drift in the OPPOSITE direction; P0.B6 here is "doc claims work pending, work actually done").

### §1.3 Sub-pattern A 8th instance — `### Phase-0-catches-wrong-premise` doctrine track record

Per the locked doctrine, sub-pattern A documents 7 prior instances at P0.B3 closure: P0.10, P0.S1, P0.S6, P0.S7, P0.S7.D-D, P0.B1, and (per architect closure-audit at P0.S7 closure) the rollback events at P0.S5/P0.S7. **P0.B6 Phase 0 is the 8th instance** — pre-audit premise "22 tests not landed" falsified by grep showing all 22 ARE landed. The discipline working as designed.

Distinctively, this 8th instance is OPPOSITE-DIRECTION drift from prior wrong-premise catches:
- Prior instances: pre-audit thought scope was X; grep revealed scope was Y (architect's mental model wrong about THE problem).
- P0.B6: pre-audit thought work was PENDING; grep revealed work was DONE (documentation drift, not scope drift).

Worth a sub-observation banking — see §3.

### §1.4 Reality check — verify the 22 landed tests cover the 22 rule bodies

`core/reconciler.py` has 23 rule functions (Pass-1 grep):

P0 group (5): `_p0_short_utterance_hard_mismatch`, `_p0_short_utterance_ambiguous_multi_session`, `_p0_pure_noise_hold_current`, `_p0_short_utterance_gap_hold_current`, `_p0_short_utterance_no_session`.

P1 (1): `_p1_confident_voice_switch`.

P2 (3): `_p2_midrange_face_assist_switches`, `_p2_midrange_face_assist_below_floor`, `_p2_midrange_no_face_returns_ambiguous`.

P3 (4): `_p3_self_match_below_floor`, `_p3_self_match_thin_stranger_relaxed`, `_p3_self_match_offscreen_mature`, `_p3_self_match_with_face`.

P3.5 (1): `_p3_5_bootstrapping_stranger_hold`.

P4 (6): `_p4_multi_segment_mismatch`, `_p4_pyannote_vouched_stranger`, `_p4_new_stranger_low_match`, `_p4_single_segment_mismatch`, `_p4_voice_ambiguous_no_candidates`, `_p4_voice_ambiguous_with_candidates`.

P5 (2): `_p5_no_session_new_stranger`, `_p5_no_session_no_action`.

Last-resort (1): `_last_resort_ambiguous`.

**Total: 23 rules.** TODO enumerated 22 named tests. The MISSING test is for one of the two "hold current" rules — `_p0_pure_noise_hold_current` OR `_p0_short_utterance_gap_hold_current` (the latter was added P0.10 era post-TODO per CLAUDE.md history: "P0.10 Phase 1 — `_p0_short_utterance_gap_hold_current` rule … closes the Bug-W coverage gap"). The TODO's test #4 `test_p0_short_utterance_holds_current` (landed at line 632) covers ONE of them; the other has no dedicated per-rule acceptance test.

**Hypothesized state**: `test_p0_short_utterance_holds_current` covers `_p0_short_utterance_gap_hold_current` (matches by name); `_p0_pure_noise_hold_current` may not have a dedicated per-rule acceptance test. **Plan v1 §1 Pass-2 grep verifies this** by reading `test_p0_short_utterance_holds_current` body + checking whether it exercises the noise rule too OR if it's gap-rule-specific.

If verified: one missing per-rule acceptance test (for `_p0_pure_noise_hold_current`). Otherwise: all 23 rules covered + the TODO's 22 enumeration was 1-short by an off-by-one count.

---

## §2. Revised P0.B6 scope — pivot from "land 22 tests" to "close documentation drift + verify coverage"

### §2.1 D-decisions to lock at Plan v1

**D1 (LOW — documentation correctness):** Remove the stale TODO marker comment at `tests/test_reconciler.py:1337-1361`. Replace with a brief "Per-rule acceptance test coverage" header pointing to the landed test functions + acknowledging skeptic1 Attack 3 as RESOLVED.

**D2 (LOW — documentation correctness):** Update the test file's top-of-file docstring at `tests/test_reconciler.py:1-14`:
- Original: "22 PER-RULE acceptance tests (land in #176, one per rule, in lockstep with the rule body)."
- Update to: "22 PER-RULE acceptance tests (landed in #176 2026-04-29; resolved at P0.B6 closure 2026-05-21)."

**D3 (verify coverage — Pass-2 grep at Plan v1):** Confirm whether `_p0_pure_noise_hold_current` has a dedicated per-rule acceptance test OR is covered by `test_p0_short_utterance_holds_current`. If a gap is found, EITHER (a) add the missing test, OR (b) document the rule's coverage via an existing test name in a comment block. Architect lean: option (a) — closes the 1-test gap definitively.

**D4 (AST forward-property tripwire — preventive):** add a test that scans `core/reconciler.py` for `^def _p[0-9]|^def _last_resort` rule definitions + asserts each has a `test_<rule_name>` or equivalent acceptance test in `tests/test_reconciler.py`. Same shape as P0.B3 D3 AST tripwire (lock-context discipline) — structural tripwire prevents future rule additions from shipping without per-rule acceptance test coverage. Closes the discipline-drift recurrence vector.

### §2.2 D-decisions DELIBERATELY NOT in scope

- **NOT in scope:** Refactoring the 22 existing tests or improving their per-rule assertions. They're landed + working.
- **NOT in scope:** BUG-REC-1 (P0.B1.X) design dialogue. Test 17 (`test_p4_single_segment_mismatch_drops_in_multi_known`) interacts with the BUG-REC-1 rule body but the test is LANDED + PASSING per current cascade ordering. If P0.B1.X resolves with a cascade reorder, the test asserts the post-reorder behavior; that's downstream of P0.B1.X scope, not P0.B6.
- **NOT in scope:** Other test-coverage concerns from board meeting (skeptic1 Attack 4 latency tests untested with real LLM, skeptic1 Attack 9 intent classifier accuracy on TV dialogue). Different surfaces, different specs.

---

## §3. Pre-mortem (5 failure modes — strict-mode floor 5-10, MINIMAL CYCLE)

### §3.1 — `_p0_pure_noise_hold_current` actually IS covered by `test_p0_short_utterance_holds_current`

**Risk:** Plan v1 §1 Pass-2 grep verifies that `test_p0_short_utterance_holds_current` body exercises BOTH the gap rule AND the noise rule. If so, D3 needs no new test; just documentation.

**Mitigation:** Plan v1 reads test body + classifies coverage. Either outcome is fine — adjust scope at Plan v1.

### §3.2 — D4 AST tripwire false-positives on internal helpers

**Risk:** `core/reconciler.py` may have helper functions matching `_p[0-9]_*` pattern that ARE NOT rules (e.g. `_p4_helper_check_voice`). AST scan that grabs all `^def _p[0-9]` matches would wrongly flag them.

**Mitigation:** Plan v1 grep-verifies `core/reconciler.py` for any helper functions matching the pattern. If found, D4 uses a `_CASCADE` membership check instead of name-prefix grep (the `_CASCADE` tuple is the authoritative rule list). Cleaner discipline.

### §3.3 — Documentation drift recurrence

**Risk:** The stale TODO has been there since 2026-04-29 — 22 days. Same drift class could recur in the future if another similar TODO comment is added without a cleanup gate.

**Mitigation:** D4 AST tripwire is the structural guard for future regressions. Plus closure-narrative banking under a new informal observation `Stale-TODO-marker-after-work-complete` (1 instance — P0.B6) to watch for recurrence. If 3+ instances accumulate, may elevate to operational rule.

### §3.4 — Test naming convention drift

**Risk:** Future rules added to `_CASCADE` may use test names that don't follow the `test_<rule_name>_*` convention. D4 tripwire's name-matching heuristic could miss them.

**Mitigation:** D4 uses a more robust mapping: for each rule function name in `_CASCADE`, scan `tests/test_reconciler.py` for any test whose docstring or function body references the rule's name. False-negative-resistant.

### §3.5 — Skeptic1 Attack 3 was FALSE — implications for board-meeting reliance

**Risk:** Skeptic1 Attack 3 from 2026-05-20 was based on a stale doc-comment read without grep-verification. The "severity MAJOR" framing was unfounded. This implies prior board-meeting findings may have similar stale-evidence quality.

**Mitigation:** P0.B6 closure narrative MUST honestly state that Attack 3's premise was FALSIFIED + the actual gap is documentation-only (stale TODO marker, not missing test coverage). Banked observation candidate: `Board-meeting-attack-premise-needs-grep-verification` — same family as `Plan-v1-Pass-2-grep-undercount` (grep-verify the source-of-truth claim before banking discipline events). 1 instance (P0.B6 Phase 0). Watch for recurrence.

---

## §4. Multi-direction invariant trace per D-decision

### §4.1 D1 + D2 (documentation cleanup)

- **Forward:** future readers of `tests/test_reconciler.py` see accurate state (no stale TODO, no stale docstring).
- **Backward:** no production callers; documentation-only changes.
- **Sideways:** other stale-TODO markers in the codebase. Grep `tests/` and `core/` for `TODO.*\#` patterns — if other similar stale markers exist, P0.B6.X follow-up.
- **Lifecycle:** stable; documentation changes don't affect runtime.

### §4.2 D3 (verify coverage + close 1-test gap if found)

- **Forward:** future maintainers see complete per-rule acceptance test coverage. The 23rd rule (`_p0_pure_noise_hold_current` if it lacks its own test) gains protection.
- **Backward:** `_CASCADE` tuple in `core/reconciler.py` is the rule registry; D3 traces from this registry forward to test coverage.
- **Sideways:** if the test for `_p0_pure_noise_hold_current` lands, it follows the same `test_p<N>_<rule>` naming convention as the existing 22.
- **Lifecycle:** stable; one new acceptance test if D3 finds a gap.

### §4.3 D4 (AST tripwire)

- **Forward:** future rule additions to `_CASCADE` cannot ship without an accompanying per-rule acceptance test (CI catches the absence at PR review time).
- **Backward:** `_CASCADE` tuple is the source-of-truth for rule registry.
- **Sideways:** parallel to P0.B3 D3 AST tripwire (locked-context discipline) + P0.B5 D3 AST tripwire (no `_save_faiss` inside `_index_lock` block). Same family: structural invariant prevents future regression.
- **Lifecycle:** lives in the test suite; runs on every PR.

---

## §5. Cross-spec impact analysis

- **P0.10 (legacy reconciler deletion + Block C band-divergence trigger):** P0.10 closed the cutover from legacy router to reconciler. The 22-per-rule acceptance test landing was originally PR #176 in the P0.10 follow-up sequence. P0.B6 closes the TODO marker that #176 left behind.
- **P0.B1.X (Bug 5 reconciler cascade design dialogue):** test 17 (`test_p4_single_segment_mismatch_drops_in_multi_known`) is the rule under design discussion. P0.B6 LEAVES this test as-is (asserting current cascade behavior). If P0.B1.X resolves with a reorder, the test gets updated at THAT spec's closure, not P0.B6.
- **P0.B5 (just-closed):** P0.B6's D4 AST tripwire is structurally analogous to P0.B5 D3's AST tripwire pattern. Reusable structural-invariant test discipline.
- **P1.A (pipeline.py decomposition, future):** no interaction. P0.B6 is contained within `tests/test_reconciler.py` + `core/reconciler.py`; pipeline.py decomp is orthogonal.

---

## §6. Cadence prediction

**SMALL-band (3-4 D-decisions / single subsystem / very LOW per-D fan-out / 2-4 logical anchors)** → **v1 only OPTIONAL-Plan-v2 path** (4th proof case candidate after P0.S3 + P0.B3 + P0.B5).

Rationale: P0.B6 is documentation-cleanup + verify-coverage + 1 AST tripwire (+ maybe 1 missing test if D3 surfaces a gap). VASTLY smaller scope than the pre-Phase-0 "land 22 tests" framing. The 22 tests are ALREADY landed.

If Plan v1 surfaces ≥1 unresolved precision item (e.g. D3 Pass-2 grep finds multiple coverage gaps, or D4 AST tripwire scope needs broadening) → escalate to Plan v2.

**Q5 estimate range: 2-5 logical anchors, mid 3-4.**

---

## §7. Q5 baseline estimation

Per `### Phase-0-granular-decomposition-enables-accurate-estimates` doctrine (10 supporting instances post-P0.B5):

Estimate range: **2-5 logical anchors**, mid-range **3-4**.

Breakdown:
- D1 (1 anchor): source-inspection that stale TODO marker is REMOVED.
- D2 (1 anchor): source-inspection that file docstring is updated.
- D3 (0-1 anchor): IF gap surfaced, the new `test_p0_pure_noise_holds_current` acceptance test. IF no gap, D3 is verification-only (no new anchor).
- D4 (1 anchor): AST forward-property tripwire (`_CASCADE` membership → test coverage mapping).

**Total: 3 anchors (no D3 gap) OR 4 anchors (with D3 test).**

Plan v1 will lock anchor count + auditor confirms / refines mid-range. ON-TARGET band per Plan v3 §1.1 corrected band table = ±15% of mid → ON-TARGET if closure lands at 3-4 anchors (mid 3.5 ±15%).

---

## §8. Open questions for auditor (4 items)

**Q1 — Should P0.B6 ALSO close the stale TODO markers elsewhere in the codebase (if any)?**

Architect lean: NO. Scope-bounded. Plan v1 §4.1 sideways trace grep-checks for analog stale TODOs but those are P0.B6.X follow-up scope, not P0.B6.

**Q2 — If D3 finds `_p0_pure_noise_hold_current` IS covered by existing test, should the test get a docstring update to make the coverage explicit?**

Architect lean: YES. Documentation-correctness fix — the test docstring should name BOTH rules if it covers both. Costs nothing and prevents future drift.

**Q3 — Should D4's AST tripwire ALSO scan `core/reconciler.py` for `_CASCADE` MEMBERSHIP vs name-prefix grep?**

Architect lean: YES per §3.2 — `_CASCADE` tuple is the authoritative registry; name-prefix grep could false-positive on internal helpers. Plan v1 locks this disposition.

**Q4 — Should the closure narrative explicitly bank the `### Phase-0-catches-wrong-premise` 8th instance + the new informal observation `Board-meeting-attack-premise-needs-grep-verification`?**

Architect lean: YES on both. The Phase 0 wrong-premise catch is significant (the entire P0.B6 scope pivoted from "land 22 tests" to "close documentation drift"). The new informal observation captures the meta-lesson that board-meeting attack claims warrant grep-verification before discipline-event banking. Cross-actor parallel to `Plan-v1-Pass-2-grep-undercount` + `Auditor-catches-Q5-math-at-plan-review`.

---

## §9. Discipline counts at Phase 0 close

**Per auditor's Post-P0.B5 ratified baseline + Phase 0 artifact (+1):**

| Discipline | Post-P0.B5 baseline | Post-P0.B6 Phase 0 |
|---|---|---|
| Spec-first review cycle | 52 | **53** ✓ (Phase 0 artifact +1) |
| Strict-industry-standard mode | 42 + 12 closures | **43 applications + 12 closures** ✓ |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 10 supporting | stays 10 (closure pending) |
| `### Phase-0-catches-wrong-premise` | 7 | **8** ✓ (P0.B6 Phase 0 falsified pre-audit premise; doctrine 8th instance per §1.3) |
| `### Twin-filename-pitfall-prevention` (elevated doctrine) | 7 + 4 op rules | stays 7 (preventive at audit drafting; 10th preventive event but not auto-counted) |
| `### Grep-baseline-before-drafting` (elevated doctrine) | 9 instances | **10 instances** ✓ (Phase 0 drafted from Post-P0.B5 ratified counts) |
| Deferred-canary | 13th application | stays 13 (closure event pending) |
| Auditor-Q5-estimates-trail-grep | 16 banked | stays 16 (closure pending) |
| Cross-cycle-handoff transparency precedent | 15 successful | **16 successful** ✓ (architect honored P0.B5 closure verdict's ratified counts at P0.B6 baseline grep) |
| Architect-reads-production-code-before-sign-off | 9 banked | stays 9 (closure-audit pending) |
| Sub-pattern A (Phase-0-catches-wrong-premise) | 7 | **8** (same event as the doctrine bump) |
| Spec-time grep-verification | 19 instances | **20** ✓ (Phase 0 §1 Pass-1 grep enumerated 22 named tests + 23 rule functions + cross-reference) |
| Discipline-count-bump-needs-explicit-justification | 10 preventive | stays 10 |
| Convention-drift-on-discipline-counts (parent) | 4 | stays 4 |
| Per-artifact-arithmetic-drift-survives-grep-baseline (child) | 1 | stays 1 |
| `Explicit-closure-honest-count-commitment` | 8 | stays 8 (commitment-making pending Plan v1) |
| `Auditor-catches-Q5-math-at-plan-review` | 2 | stays 2 |
| `Zero-precision-items-at-auditor-review` (renamed + broadened) | 3 + sub-rule threshold | stays 3 (Plan v1 audit pending; if 0 precision items → 4th instance) |
| `Plan-v1-Pass-2-grep-undercount` | 2 | stays 2 |
| `Bug-fix-cycles-surface-discipline-edges` | 1 | stays 1 |
| `Auditor-adjudication-drift-clarified-by-architect` | 2 | stays 2 |
| OPTIONAL-Plan-v2 proof case | 3 (P0.S3 + P0.B3 + P0.B5) | stays 3 (4th candidate if Plan v1 absorbs cleanly) |
| **NEW: `Board-meeting-attack-premise-needs-grep-verification` (informal)** | — | **1 instance** ✓ (P0.B6 Phase 0; skeptic1 Attack 3 falsified by grep) — see §3.5 |
| **NEW: `Stale-TODO-marker-after-work-complete` (informal, sub-observation)** | — | **1 instance** ✓ (P0.B6 Phase 0; opposite-direction documentation-vs-reality drift class) — see §3.3 |
| HEAVY-band cadence (working hypothesis) | 2 | stays 2 (P0.B6 is SMALL-band) |

**Phase 0 commitments banked for closure-audit:**

1. Spec-first review cycle expected at closure: 53 + 1 (Plan v1) + (+1 if Plan v2) + 1 (closure) per +1-per-artifact convention.
2. Q5 estimate range LOCKED at 2-5 anchors, mid 3-4. Closure-actual reading triggers band-table disposition.
3. `### Phase-0-catches-wrong-premise` ACTIVATED this cycle (8th instance) — discipline maturing.
4. 2 NEW informal observations banked.
5. Cadence: SMALL-band; v1 only OPTIONAL-Plan-v2 path (4th proof case candidate).

---

## §10. Open invariants for Plan v1 to enumerate

1. **D1 stale-TODO-removal invariant** — `tests/test_reconciler.py` does NOT contain `TODO(#176)` substring after closure.

2. **D2 docstring-update invariant** — `tests/test_reconciler.py` top-of-file docstring contains "landed in #176" (past tense) + P0.B6 closure reference.

3. **D3 coverage-completeness invariant** — every rule function in `core/reconciler.py::_CASCADE` has a corresponding per-rule acceptance test in `tests/test_reconciler.py` (verified by D4 AST tripwire below).

4. **D4 AST forward-property invariant** — AST scan of `core/reconciler.py` extracts `_CASCADE` membership; for each rule, asserts a `test_<rule>_*` function (or docstring-mentioning equivalent) exists in `tests/test_reconciler.py`.

5. **No-side-effect-in-Phase-0 invariant** — this Phase 0 audit landed with zero production code changes.

---

**End of Phase 0 audit.** Ready to forward to auditor.

**Architect's request to auditor:** confirm the wrong-premise catch is real (8th instance of `### Phase-0-catches-wrong-premise`) + revised P0.B6 scope (documentation cleanup + coverage verification + AST tripwire) is defensible + cadence (SMALL-band v1 only OPTIONAL-Plan-v2 path) is appropriate + 4 open questions adjudicable.

**Honest framing:** skeptic1 Attack 3 was based on a stale TODO comment, not on verified missing coverage. P0.B6 is a documentation-correctness + structural-invariant cycle, NOT a test-coverage gap closure. The original board-meeting "MAJOR severity" framing was unfounded; the actual severity is LOW (documentation drift). This is the FIRST time a board-meeting attack premise has been FALSIFIED by Phase 0 grep — banked as new informal observation `Board-meeting-attack-premise-needs-grep-verification`.
