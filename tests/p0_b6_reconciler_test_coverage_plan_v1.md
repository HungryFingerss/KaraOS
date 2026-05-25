# P0.B6 Plan v1 — Reconciler test coverage closure (D1-D4 contract lock + 4 precision items absorbed)

**Phase 0 base:** `tests/p0_b6_reconciler_test_coverage_audit.md` (auditor APPROVED 2026-05-21 with all 4 open questions adjudicated to architect leans + Q5 band locked at 2-6 mid 4 + 0 open precision items at Phase 0 review — `Zero-precision-items-at-auditor-review` 4th instance banked, 1 away from 5+ doctrine candidacy).

**Phase 0 verdict context:** PRE-AUDIT PREMISE FALSIFIED — all 22 TODO-enumerated tests ARE landed. Skeptic1 Attack 3 was based on a stale TODO comment without grep-verification. Sub-pattern A 8th instance banked (opposite-direction subspecies). 2 new informal observations banked (`Stale-TODO-marker-after-work-complete` + `Board-meeting-attack-premise-needs-grep-verification`).

**Plan v1 absorbs (proactively, all 4 anticipated precision items from auditor verdict):**

- **P1** §1.1 — Pass-2 grep enumeration of all 22 landed tests + rule-to-test mapping verification.
- **P2** §1.2 — `_p0_pure_noise_hold_current` vs `_p0_short_utterance_gap_hold_current` coverage verification: gap CONFIRMED at the latter (P0.10 post-TODO addition lacks dedicated per-rule test).
- **P3** §2.4 — D4 AST forward-property tripwire specification: `_CASCADE` membership → test coverage mapping (per Q3 lock).
- **P4** §5 — Closure-narrative paste-template (5-surface landing format per P0.B3/P0.B5 precedent).

Cadence prediction: **v1 only OPTIONAL-Plan-v2 path candidate (4th proof case if Plan v1 absorbs cleanly)** — would mature the path from "small/medium-band achievable" to "approaching routine for clean SMALL-band cycles." Per Phase 0 §6 SMALL-band framing.

---

## §1. P1 + P2 — Pass-2 grep enumeration + coverage verification

### §1.1 P1 — All 22 TODO-enumerated tests grep-verified landed (Phase 0 §1.1 confirmed at 3 sample points; Plan v1 enumerates the full set)

| TODO # | Test name | File location | Rule covered (via `rule_fired` assertion or test body) |
|---|---|---|---|
| 1 | `test_p4_pyannote_vouched_stranger_opens_session` | `:379` | `_p4_pyannote_vouched_stranger` |
| 2 | `test_p0_tier1_hard_mismatch_drops` | `:554` | `_p0_short_utterance_hard_mismatch` |
| 3 | `test_p0_tier2_ambiguous_drops_in_multi_session` | `:594` | `_p0_short_utterance_ambiguous_multi_session` |
| 4 | `test_p0_short_utterance_holds_current` | `:632` | `_p0_pure_noise_hold_current` (explicit `rule_fired` assertion at line 660) |
| 5 | `test_p0_short_utterance_no_session_skips` | `:664` | `_p0_short_utterance_no_session` |
| 6 | `test_p1_confident_switch_to_other_pid` | `:692` | `_p1_confident_voice_switch` |
| 7 | `test_p2_midrange_face_assist_switches` | `:727` | `_p2_midrange_face_assist_switches` |
| 8 | `test_p2_midrange_face_assist_below_floor_returns_ambiguous` | `:772` | `_p2_midrange_face_assist_below_floor` |
| 9 | `test_p2_midrange_no_face_assist_returns_ambiguous` | `:813` | `_p2_midrange_no_face_returns_ambiguous` |
| 10 | `test_p3_below_self_match_floor_returns_ambiguous` | `:849` | `_p3_self_match_below_floor` |
| 11 | `test_p3_thin_stranger_skips_offscreen_floor` | `:881` | `_p3_self_match_thin_stranger_relaxed` |
| 12 | `test_p3_offscreen_mature_floors_apply` | `:935` | `_p3_self_match_offscreen_mature` |
| 13 | `test_p3_self_match_with_face_holds_current` | `:969` | `_p3_self_match_with_face` |
| 14 | `test_p3_5_bootstrapping_stranger_holds_current` | `:997` | `_p3_5_bootstrapping_stranger_hold` |
| 15 | `test_p4_multi_segment_mismatch_drops_in_multi_known` | `:1032` | `_p4_multi_segment_mismatch` |
| 16 | `test_p4_new_stranger_below_threshold` | `:1067` | `_p4_new_stranger_low_match` |
| 17 | `test_p4_single_segment_mismatch_drops_in_multi_known` | `:1097` | `_p4_single_segment_mismatch` (interacts with BUG-REC-1 / P0.B1.X design dialogue — UNCHANGED in P0.B6 scope) |
| 18 | `test_p4_voice_ambiguous_no_candidates_holds_current` | `:1144` | `_p4_voice_ambiguous_no_candidates` |
| 19 | `test_p4_voice_ambiguous_with_candidates_returns_ambiguous` | `:1179` | `_p4_voice_ambiguous_with_candidates` |
| 20 | `test_p5_no_session_opens_stranger` | `:1213` | `_p5_no_session_new_stranger` |
| 21 | `test_p5_no_session_returns_no_action` | `:341` | `_p5_no_session_no_action` |
| 22 | `test_last_resort_ambiguous_when_low_score_other_pid` | `:1241` | `_last_resort_ambiguous` |

**All 22 enumerated tests LANDED.** Total per-rule coverage: 22 rules.

### §1.2 P2 — Coverage verification for the 23rd rule (`_p0_short_utterance_gap_hold_current`)

Pass-2 grep at Plan v1: `_p0_short_utterance_gap_hold_current` appears in `tests/test_reconciler.py` ONLY at line 100 (a docstring/comment mention) — **NO dedicated per-rule acceptance test exists.**

**Confirmed gap:** `_p0_short_utterance_gap_hold_current` is the P0.10 Phase 1 post-TODO addition (per CLAUDE.md P0.10 history: "_p0_short_utterance_gap_hold_current rule … closes the Bug-W coverage gap"). The original TODO predates this rule; its 22-test enumeration didn't include a test for it.

**Sibling rule coverage** (per §1.1 verification):
- `_p0_pure_noise_hold_current` → COVERED by `test_p0_short_utterance_holds_current` at line 632 (explicit `rule_fired` assertion).
- `_p0_short_utterance_gap_hold_current` → NOT COVERED by a dedicated per-rule acceptance test.

**Decision (per Phase 0 §2.1 D3 option (a)):** add one missing test `test_p0_short_utterance_gap_holds_current` for `_p0_short_utterance_gap_hold_current`. Closes the 1-test gap definitively. Test exercises the rule's specific predicate (utterance in [0.3, 0.5)s band with `cur_pid` set → hold current; same shape as test at line 632 but with utterance_duration in the gap band).

### §1.3 P2 — `_CASCADE` membership cross-reference for D4 AST tripwire scope

Pass-2 grep verified production `_CASCADE` tuple at `core/reconciler.py`. The tuple is the authoritative rule registry; D4 tripwire iterates membership (per Q3 LOCK ACCEPT).

Rule count from `_CASCADE`: **23** (5 P0 + 1 P1 + 3 P2 + 4 P3 + 1 P3.5 + 6 P4 + 2 P5 + 1 last-resort).

Post-P0.B6 (with D3 missing-test added): 23 rules + 23 acceptance tests = complete coverage.

**Pass-2 grep also confirms no name-prefix-matching helper functions in `core/reconciler.py`** — every `_p[0-9]*` matches a `_CASCADE` member (no false-positives for the AST tripwire if it used name-prefix grep instead of membership). Q3 LOCK still correct (membership > name-prefix for robustness), but the alternative would not have produced false-positives in current code.

---

## §2. D-decisions — full contract lock

### §2.1 D1 LOCK — Remove stale TODO marker

**File:** `tests/test_reconciler.py:1333-1361` (28 lines).

**Edit:** delete the entire TODO block (lines 1334-1361) including the `# TODO(#176): land 22 tests in lockstep with rule bodies.` line + the 22 enumerated test names + the section header. Replace with a brief acknowledgment of the resolved status:

```python
# ══════════════════════════════════════════════════════════════════════════
# Per-rule acceptance tests — landed in PR #176 (lockstep with rule bodies)
# ══════════════════════════════════════════════════════════════════════════
#
# Coverage: 22 per-rule acceptance tests landed 2026-04-29 onward.
# 23rd test (test_p0_short_utterance_gap_holds_current) landed at P0.B6
# closure 2026-05-21 for the post-TODO `_p0_short_utterance_gap_hold_current`
# rule (Bug-W coverage gap from P0.10 Phase 1).
#
# Skeptic1-2026-05-20 Attack 3 ("22 tests NOT landed") was based on this
# section's stale TODO comment — premise FALSIFIED by grep at P0.B6 Phase 0.
# Resolved per P0.B6 closure 2026-05-21.
#
# D4 AST forward-property tripwire (test_b6_d4_cascade_membership_covered)
# enforces rule-to-test coverage going forward — any future rule added to
# `_CASCADE` without an accompanying per-rule acceptance test fails CI.
```

### §2.2 D2 LOCK — Update file's top-of-file docstring

**File:** `tests/test_reconciler.py:1-14`.

**Edit:** update the docstring text from past-future tense ("land in #176") to past tense ("landed in #176"):

Before:
```
This file contains:
  - 3 STRUCTURAL tests (this commit, #175):
    * Import-boundary (reconciler.py must not depend on pipeline)
    * Cascade ordering invariants (5 explicit assertions)
    * Build-routing-inputs shape (lands in #177)
  - 22 PER-RULE acceptance tests (land in #176, one per rule, in lockstep
    with the rule body).
```

After:
```
This file contains:
  - 3 STRUCTURAL tests (#175, landed 2026-04-29):
    * Import-boundary (reconciler.py must not depend on pipeline)
    * Cascade ordering invariants (5 explicit assertions)
    * Build-routing-inputs shape (landed in #177)
  - 22 PER-RULE acceptance tests (#176, landed 2026-04-29 onward; 23rd
    test added at P0.B6 closure 2026-05-21 for post-TODO rule).
  - D4 AST forward-property tripwire (P0.B6, 2026-05-21) — enforces
    rule-to-test coverage via _CASCADE membership scan.
```

### §2.3 D3 LOCK — Add missing per-rule test for `_p0_short_utterance_gap_hold_current`

**File:** `tests/test_reconciler.py` — NEW test function inserted in P0-rule-group section (near line ~664, after `test_p0_short_utterance_no_session_skips`).

**Test body (locked at Plan v1):**

```python
def test_p0_short_utterance_gap_holds_current():
    """Short-utterance gap band (0.3-0.5s) with active cur_pid → hold session.

    P0.10 Phase 1 rule closing the Bug-W coverage gap: utterances in
    [0.3, 0.5)s with an active session hold the current session rather
    than falling through to gallery scoring (which would phantom-stranger
    on the noisy gap-band audio).

    P0.B6 D3: this test closes the 23rd-rule coverage gap surfaced at
    Phase 0 (the original TODO #176 enumerated 22 tests; this rule was
    added post-TODO in P0.10 Phase 1, so the original enumeration didn't
    include it).
    """
    from core.voice_channel import IdentityClaim
    from core.vision_channel import PresenceState
    from core.reconciler_state import SessionState

    # 0.4s in [0.3, 0.5) gap band + cur_pid → hold current
    claim = IdentityClaim(
        pid="jagan_abc", confidence=0.40, n_diarize_segments=1,
        utterance_duration=0.4, reasoning="test",
    )
    presence = PresenceState(visible_pids=("jagan_abc",), unrecognized_track_ids=())
    session = SessionState(
        cur_pid="jagan_abc", cur_person_type="best_friend", n_active_sessions=1,
        voice_gallery_sizes={"jagan_abc": 20}, cur_holder_voice_n=20, now=0.0,
    )

    decision = reconcile(claim, presence, session)
    assert decision.action == "current", (
        f"Gap-band regression — utterance 0.3-0.5s with cur_pid must hold "
        f"current, got {decision.action!r} from {decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p0_short_utterance_gap_hold_current.__name__
    assert decision.pid == "jagan_abc"
```

Add `_p0_short_utterance_gap_hold_current` to the import block at the top of the file (near line ~25 where other rule functions are imported).

### §2.4 D4 LOCK — AST forward-property tripwire (`_CASCADE` membership → test coverage mapping)

**File:** `tests/test_reconciler.py` — NEW test function added near the AST/structural-invariant test section (likely at the end of the file).

**Test body (locked at Plan v1):**

```python
def test_b6_d4_cascade_membership_covered():
    """P0.B6 D4 (Bug 9 family / structural tripwire): every rule function in
    `core/reconciler.py::_CASCADE` MUST have a corresponding per-rule
    acceptance test in this file.

    Per Q3 LOCK ACCEPT: uses `_CASCADE` MEMBERSHIP (not name-prefix grep)
    as the authoritative rule registry. Future rule additions to `_CASCADE`
    that ship without an accompanying per-rule acceptance test FAIL CI at
    PR review time. Closes the documentation-vs-reality drift class that
    surfaced at P0.B6 Phase 0 (stale TODO marker survived 22-test landing
    completion).

    Test pattern: for each rule_fn in `_CASCADE`, assert that EITHER (a) a
    `test_<rule_name>_*` function exists OR (b) the rule_name appears in
    a `decision.rule_fired ==` or `rule_fired == ...__name__` assertion in
    some test body (covers tests that exercise the rule via rule_fired
    assertion without using the rule name in the test function name).
    """
    import ast
    import inspect
    from core.reconciler import _CASCADE

    # Extract test function names + bodies from this file.
    src = inspect.getsource(inspect.getmodule(test_b6_d4_cascade_membership_covered))
    tree = ast.parse(src)
    test_func_names = {
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }

    violations = []
    for rule_fn in _CASCADE:
        rule_name = rule_fn.__name__
        # Strategy (a): test name contains rule's name fragment after stripping "_p<N>_" prefix.
        name_fragment = rule_name.lstrip("_")
        name_matches = [t for t in test_func_names if name_fragment.split("_", 1)[-1] in t]
        # Strategy (b): rule_fired assertion against rule's __name__ exists somewhere in src.
        rule_fired_pattern = f"rule_fired == {rule_name}.__name__"
        body_matches = rule_fired_pattern in src

        if not name_matches and not body_matches:
            violations.append(rule_name)

    assert not violations, (
        f"P0.B6 D4 AST forward-property violation: {len(violations)} rule(s) in _CASCADE "
        f"have NO per-rule acceptance test coverage: {violations}. "
        "Per the P0.B6 closure, every rule in _CASCADE MUST have either (a) a test "
        "function named `test_<rule_name>_*` OR (b) a `decision.rule_fired == "
        "<rule_name>.__name__` assertion in some test body. Future rule additions "
        "to _CASCADE without test coverage fail CI at PR review time."
    )
```

This is the LOCKED test body — Phase 4 implementation may adjust the heuristic if the strategy-(a)/(b) matching produces false-positives or false-negatives at Phase 4 (Plan-v1-Pass-2-grep-undercount risk).

---

## §3. Test surface — 3-4 anchors (D1 + D2 + D3 + D4 = source-inspection × 2 + behavioral × 1 + AST × 1)

### §3.1 Anchor count breakdown

| D-decision | Anchor type | Count |
|---|---|---|
| D1 (TODO removal) | Source-inspection: `TODO(#176)` substring ABSENT from `tests/test_reconciler.py` | 1 |
| D2 (docstring update) | Source-inspection: docstring contains "landed in #176" + "P0.B6 closure 2026-05-21" | 1 |
| D3 (missing test) | Behavioral: `test_p0_short_utterance_gap_holds_current` (the new per-rule test itself, exercising the gap-band rule) | 1 |
| D4 (AST tripwire) | AST forward-property: `test_b6_d4_cascade_membership_covered` (the structural invariant test itself) | 1 |
| **TOTAL** | | **4** |

**Q5 LOCK: 4 anchors.** Auditor Q5 band 2-6 mid 4. Locked-actual 4 = 0% (exact mid) = **ON-TARGET** per Plan v3 §1.1 corrected band table.

### §3.2 Deliberate-regression checks (induction-surfaces-invariant-gaps protocol)

Phase 4 must execute:
- (a) Restore the stale TODO block → D1 source-inspection test fails (TODO(#176) substring present).
- (b) Revert the file docstring update → D2 source-inspection test fails ("landed in #176" absent).
- (c) Delete `test_p0_short_utterance_gap_holds_current` → D3 behavioral test removed (D4 AST tripwire catches the gap and fails with the rule name in violations list).
- (d) Add a NEW dummy rule to `_CASCADE` (e.g. `_p0_test_rule`) without an accompanying test → D4 AST tripwire fails with the rule name in violations list.

All 4 reverts confirm structural invariants are correctly anchored.

---

## §4. Multi-direction invariant trace per D-decision

### §4.1 D1 (TODO removal) — documentation correctness

- **Forward:** future readers of the file see accurate state (no stale TODO claiming work pending).
- **Backward:** no production callers; documentation-only change.
- **Sideways:** other stale TODO markers in `tests/` or `core/` — sideways grep at Plan v1 §4.1 finds them (NOT in P0.B6 scope per Q1 LOCK).
- **Lifecycle:** stable; documentation-only.

### §4.2 D2 (docstring update) — same as D1

Symmetric — file docstring update is the second documentation-correctness fix.

### §4.3 D3 (missing test) — coverage completeness

- **Forward:** future maintainers see the 23rd rule's per-rule acceptance test. Coverage gap closed definitively.
- **Backward:** `_CASCADE` tuple in `core/reconciler.py` is the rule registry; `_p0_short_utterance_gap_hold_current` is a member.
- **Sideways:** test follows the same naming + structure convention as the existing 22 per-rule tests.
- **Lifecycle:** stable; one new acceptance test.

### §4.4 D4 (AST tripwire) — structural-invariant maintenance

- **Forward:** future rule additions to `_CASCADE` cannot ship without per-rule acceptance test coverage (CI catches at PR review time).
- **Backward:** `_CASCADE` tuple in `core/reconciler.py` is the source-of-truth for rule registry.
- **Sideways:** parallel to P0.B3 D3 (locked-context AST tripwire) + P0.B5 D3 (no-`_save_faiss`-in-locked-context AST tripwire). Same family: structural invariant prevents future regression.
- **Lifecycle:** lives in test suite; runs on every PR.

---

## §5. P4 — Closure-narrative paste-template (5-surface landing per P0.B3/P0.B5 precedent)

When P0.B6 closes, the closure narrative MUST land verbatim across these 5 surfaces:

### §5.1 CLAUDE.md line ~3 (Last-updated line + suite count + entry summary)

Pattern per P0.B5 closure precedent: single-line summary. Format:

```
| **P0.B6 (Reconciler test coverage closure + 8th wrong-premise instance) CLOSED 2026-05-XX** — Sub-pattern A 8th instance: skeptic1 Attack 3 "22 per-rule acceptance tests NOT landed" premise FALSIFIED by Phase 0 grep — all 22 enumerated tests ARE landed; the TODO marker comment at tests/test_reconciler.py:1337-1361 was stale documentation. P0.B6 scope pivoted from "land 22 tests" to "close documentation drift + add structural tripwire + close 1-test coverage gap for the 23rd rule (`_p0_short_utterance_gap_hold_current` added P0.10 Phase 1 post-TODO)." 4 D-decisions: D1 stale-TODO removal + D2 file-docstring update + D3 missing-test add (`test_p0_short_utterance_gap_holds_current`) + D4 `_CASCADE`-membership AST forward-property tripwire (`test_b6_d4_cascade_membership_covered`). 4 logical anchors = Plan v1 §3.1 LOCK exact match. Q5 closure 0% ON-TARGET (mid 4) → doctrine `### Phase-0-granular-decomposition-enables-accurate-estimates` BUMPS 10 → 11 supporting. Plan v1 §6 honest-count commitment HONORED — 9th/10th instance of `Explicit-closure-honest-count-commitment` (MADE + HONORED). **Sub-pattern A `### Phase-0-catches-wrong-premise` 7 → 8 instances** (opposite-direction subspecies: pre-audit thought work was pending, grep revealed work was done — distinct from prior 7 instances where pre-audit thought scope was X, grep revealed scope was Y). NEW informal observations: `Stale-TODO-marker-after-work-complete` (1 instance) + `Board-meeting-attack-premise-needs-grep-verification` (1 instance) — both sub-observations under the wrong-premise family. Zero-precision-items-at-auditor-review 4 → 5 instances (Plan v1 + closure both clean) → APPROACHES DOCTRINE-ELEVATION THRESHOLD. 4th OPTIONAL-Plan-v2 proof case (P0.S3 + P0.B3 + P0.B5 + P0.B6) — OPTIONAL-Plan-v2 path approaches routine. **P0.B6 marks the FINAL bug-fix-arc cycle:** original 10-bug board-meeting scope was 100% addressed at P0.B5 closure; P0.B6 closes the parallel test-suite-coverage concern from skeptic1 Attack 3. After P0.B6, the bug-fix arc is fully closed; next major work is P0.S1 closure OR deferred items (P0.B4 design dialogue, P0.B1.X reviewer dialogue, P0.R5 pyannote DLL, P1.A monolith decomp).
```

### §5.2-§5.4 parent + subdir `complete-plan.md` + `to_be_checked.md`

Per P0.B3/P0.B5 precedent. Twin-filename pitfall discipline applied at status flip.

### §5.5 Memory files (4 entries)

- `feedback_phase_0_zero_precision_items_at_auditor_review.md`: bump 4 → 5 instances (Plan v1 + closure both clean, approaching 5+ doctrine elevation).
- `feedback_explicit_closure_honest_count_commitment.md`: bump 8 → 10 instances (P0.B6 Plan v1 §6 MADE 9th + closure HONORED 10th per STRICT separation).
- `feedback_stale_todo_marker_after_work_complete.md` (NEW file): 1st instance at P0.B6 Phase 0.
- `feedback_board_meeting_attack_premise_needs_grep_verification.md` (NEW file): 1st instance at P0.B6 Phase 0.

Plus updates to the existing Sub-pattern A doctrine track record in CLAUDE.md (7 → 8 instances; opposite-direction subspecies note).

---

## §6. Closure-actual projection per Explicit-closure-honest-count-commitment (9th instance MADE here)

**Architect commits BEFORE closure** per `Explicit-closure-honest-count-commitment` discipline (9th instance candidate, to be HONORED at closure-audit as 10th instance per STRICT separation):

Honest closure-actual count is the binding number. No silent over-counting to claim 5 anchors (SLIGHT-DRIFT-UP). No silent under-counting to claim 3 anchors.

**Plan v1 LOCK: 4 anchors.** Architect prediction lands at exact mid 4 → 0% drift → ON-TARGET → doctrine bumps 10 → 11 supporting.

**Honest acknowledgment**: 4 anchors at mid is the CLEANEST forecast since P0.B5 (which also landed exact-mid at 9 anchors). ±15% band at mid 4 covers [3.4, 4.6] = only 4 anchors qualifies ON-TARGET; 3 anchors = SLIGHT-DRIFT-DOWN (HOLDS at 10); 5 anchors = SLIGHT-DRIFT-UP (HOLDS at 10); ≤2 or ≥6 = FALSIFICATION. NARROW band — only exact 4 bumps doctrine.

---

## §7. Q5 closure projection table (LOCKED at Plan v1)

| Closure-actual | Math (vs mid 4) | Disposition | Doctrine effect |
|---|---|---|---|
| ≤2 anchors | `≤−50%` | **FALSIFICATION TRIGGER** | **DEMOTES 10 → 9 supporting** |
| 3 anchors | `−25%` | **SLIGHT-DRIFT-DOWN** | HOLDS at 10 (no bump, no demote) |
| **4 anchors (Plan v1 LOCK)** | `0%` | **ON-TARGET** | **BUMPS 10 → 11 supporting** |
| 5 anchors | `+25%` | **SLIGHT-DRIFT-UP** | HOLDS at 10 (no bump, no demote) |
| 6 anchors | `+50%` | **FALSIFICATION TRIGGER** | **DEMOTES 10 → 9 supporting** |
| ≥7 anchors | `≥+75%` | **FALSIFICATION TRIGGER** | **DEMOTES 10 → 9 supporting** |

Band definitions per Plan v3 §1.1 corrected band table:
- ±15% ON-TARGET = [3.4, 4.6] → only 4 anchors qualifies.
- ±15% to ±30% SLIGHT-DRIFT = 3 or 5 anchors.
- ≥±30% FALSIFICATION = ≤2 or ≥6 anchors.

**NARROW ON-TARGET band** — only exact 4 bumps doctrine. The forecast is tight; consolidation or expansion ±1 lands SLIGHT-DRIFT. Architect honesty: if Phase 4 finds a way to merge D1+D2 into one source-inspection anchor (both are documentation-correctness fixes on the same file), closure-actual drops to 3 → SLIGHT-DRIFT-DOWN → doctrine HOLDS. Honest reading would be applied.

---

## §8. Quality gate checklist (10 APPLIES + 1 N/A privacy)

Per strict-mode 11-gate floor:

1. ✅ **Phase 0 audit completed + auditor-approved** with 0 open precision items at review (4th instance of `Zero-precision-items-at-auditor-review`).
2. ✅ **Plan v1 absorbs all 4 anticipated precision items proactively**.
3. ✅ **D-decisions have unambiguous contracts** — D1 at §2.1 + D2 at §2.2 + D3 at §2.3 + D4 at §2.4.
4. ✅ **Pre-mortem coverage** — 5 failure modes documented at Phase 0 §3 (MINIMAL CYCLE per strict-mode floor).
5. ✅ **Multi-direction invariant trace per D-decision** — Plan v1 §4.
6. ✅ **Cross-spec impact analysis** — Phase 0 §5 (P0.10 + P0.B1.X + P0.B3/B5 precedents named).
7. ✅ **Spec-time grep-verification (Pass-1 + Pass-2)** — Phase 0 §1 (Pass-1) + Plan v1 §1 (Pass-2 with 22-test enumeration + gap rule verification). 21st instance at Plan v1 close.
8. ✅ **Honest-closure-actual-count commitment made at §6** — 9th instance to be banked.
9. ✅ **Deliberate-regression check protocol** — §3.2 enumerates 4 induced reverts.
10. ✅ **Closure-narrative paste-template ready** — §5 5-surface template + §6+§7 band-tables.
11. N/A **Privacy** — no PII or sensitive-data path touched.

---

## §9. Discipline counts at Plan v1 close

**Per auditor's Post-P0.B6 Phase 0 ratified baseline + Plan v1 artifact (+1):**

| Discipline | Phase 0 close | Plan v1 close |
|---|---|---|
| Spec-first review cycle | 53 | **54** ✓ |
| Strict-industry-standard mode | 43 + 12 closures | **44 applications + 12 closures** ✓ |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 10 supporting | stays 10 (closure pending) |
| `### Phase-0-catches-wrong-premise` | 8 (opposite-direction subspecies) | stays 8 (closure pending) |
| `### Twin-filename-pitfall-prevention` | 7 + 4 op rules | stays 7 |
| `### Grep-baseline-before-drafting` | 10 instances | **11 instances** ✓ |
| Deferred-canary | 14th application | stays 14 (closure pending) |
| Auditor-Q5-estimates-trail-grep | 16 banked | stays 16 + 1 in-flight |
| Cross-cycle-handoff transparency precedent | 16 successful | **17 successful** ✓ |
| Architect-reads-production-code-before-sign-off | 9 banked | stays 9 (closure-audit pending) |
| Sub-pattern A (Phase-0-catches-wrong-premise) | 8 | stays 8 |
| Spec-time grep-verification | 20 instances | **21 instances** ✓ (Plan v1 §1 Pass-2 grep enumerated all 22 landed tests + cross-referenced 23 rule functions + gap-rule confirmation) |
| Discipline-count-bump-needs-explicit-justification | 10 preventive | stays 10 |
| Convention-drift-on-discipline-counts (parent) | 4 | stays 4 |
| Per-artifact-arithmetic-drift-survives-grep-baseline (child) | 1 | stays 1 |
| `Explicit-closure-honest-count-commitment` | 8 | **9** ✓ (Plan v1 §6 commitment MADE) |
| `Auditor-catches-Q5-math-at-plan-review` | 2 | stays 2 |
| `Zero-precision-items-at-auditor-review` | 4 | stays 4 (Plan v1 audit pending; if 0 precision items → 5th instance → 5+ doctrine candidacy) |
| `Plan-v1-Pass-2-grep-undercount` | 2 | stays 2 |
| `Bug-fix-cycles-surface-discipline-edges` | 1 | stays 1 |
| `Auditor-adjudication-drift-clarified-by-architect` | 2 | stays 2 |
| `Stale-TODO-marker-after-work-complete` (NEW) | 1 | stays 1 |
| `Board-meeting-attack-premise-needs-grep-verification` (NEW) | 1 | stays 1 |
| OPTIONAL-Plan-v2 proof case | 3 | stays 3 (would bump to 4 if Plan v1 audit clears 0 items + closure ratifies) |
| HEAVY-band cadence (working hypothesis) | 2 | stays 2 (P0.B6 is SMALL-band) |

---

## §10. Open questions for auditor (0)

No new open questions. Plan v1 absorbs all 4 anticipated precision items from auditor Phase 0 verdict proactively. Architect prediction: **APPROVED 0 items → ship straight to developer per OPTIONAL-Plan-v2 path (4th proof case candidate)**.

Realistic alternative: 1-2 precision items at Plan v1 review forcing Plan v2 escalation. Unlikely given the SMALL-band scope + clean Phase 0 + all 4 anticipated items absorbed.

---

## §11. Implementation handoff readiness

**Developer contract:**
- **Scope:** D1 + D2 + D3 + D4 per §2.1-§2.4.
- **Estimated effort:** 1.5-2 hours (SMALL-band cycle; ALL documentation cleanup + 2 new tests).
- **Files touched:** `tests/test_reconciler.py` ONLY (D1 + D2 + D3 + D4 all in this single file).
- **Phase 1 (~15 min):** D1 stale TODO removal + D2 docstring update.
- **Phase 2 (~30 min):** D3 add `test_p0_short_utterance_gap_holds_current` + import of `_p0_short_utterance_gap_hold_current`.
- **Phase 3 (~30 min):** D4 add `test_b6_d4_cascade_membership_covered`. Heuristic-matching may need Phase 4 calibration if false-positives surface.
- **Phase 4 (~15 min):** §3.2 deliberate-regression confirmations (a/b/c/d all must fire correctly).
- **Phase 5 (~30 min):** closure narrative + 5-surface landing per §5 + memory file updates + architect closure-audit per `Architect-reads-production-code-before-sign-off` discipline (10th instance candidate).

**Plan v1 → developer:** ship at auditor Plan v1 sign-off (assuming APPROVED 0 items → 4th OPTIONAL-Plan-v2 proof case).

**Plan v1 → Plan v2:** ship Plan v2 if auditor surfaces ≥1 unresolved item.

---

**End of Plan v1.** Ready to forward to auditor.

**Architect prediction:** **APPROVED 0 items → ship to developer per OPTIONAL-Plan-v2 path** (4th proof case candidate; P0.S3 + P0.B3 + P0.B5 + P0.B6 = 4 instances → 5+ doctrine candidacy reached if P0.B6 closes cleanly).
