# P0.10 Plan v1 — legacy routing deletion + Bug-W fix

**Status:** v1 draft for architect + auditor review. Pure documentation; zero production code changes during planning phase.
**Date:** 2026-05-17.
**Author:** developer; follows v1 → v2 → code discipline (P0.6 / P0.7 / P0.8 / P0.9 lineage).

**Prerequisites satisfied:**
- Phase 0 audit complete: `tests/p0_10_routing_audit.md` + `tests/p0_10_pre_audit_bug_w_evidence.md`
- D1-D8 architect+auditor-locked (see audit file)
- Suite at 2189 passing, 8 pre-existing infra failures

---

## Executive summary

P0.10 deletes the legacy `_resolve_actual_speaker` (270-line function in `pipeline.py`) plus its 4 supporting call sites, and simultaneously fixes Bug-W (the 0.3–0.5s utterance gap that surfaced during P0.9's validation gate). Same PR ships:

1. **Bug-W fix** — new `_p0_short_utterance_gap_hold_current` rule in `core/reconciler.py` covering the 0.3 ≤ utt < 0.5 band
2. **Bug-W regression test** — synthetic reproduction pinning the failure mode
3. **Contract test suite** — 27 tests mapped 1-to-1 against contract items C1-C21 + N1-N6 from the audit
4. **D7-watch telemetry** — instrumentation for the 0.5–1.0s utterance band during the 7-day validation window
5. **AST verification** — one-off Phase 0 check that `_routing_action` has structurally exactly one write site
6. **Deletion sequence** — 5 surgical edits in pipeline.py (~280 lines removed)
7. **Test-side cleanup** — retarget or remove test_pipeline.py:16590-16593 source-inspection refs

The `ROUTING_USE_RECONCILER` flag and Reconciler-Shadow infrastructure stay alive for the 7-day validation window. A follow-up PR (post-validation) deletes them together.

**Validation gate:** 100 routing decisions during the validation window **OR** 14 calendar days, **whichever comes later** (auditor's policy p2 — prevents thin-traffic green-lighting).

**Estimate:** 2–3 dev days for code + tests; 7+ days wall-clock for validation (traffic-dependent).

---

## Sequence of work (12 steps, exact order)

### Step 1 — AST verification (Phase 0 pre-deletion check)

**Purpose:** Confirm structurally (not just textually) that `_routing_action` has exactly one write site before the deletion lands. Catches a future refactor that adds a second writer.

**Location:** New test in `tests/test_p10_routing_invariants.py` (new file).

**Test shape:**
```python
def test_routing_action_has_exactly_one_write_site():
    """P0.10 pre-deletion invariant: structurally there is one and only
    one ast.Assign / ast.AugAssign targeting `_routing_action` in
    pipeline.py.  Audit confirmed N=1 textually; this is the structural
    enforcement so a future refactor can't add a second writer silently.
    """
    import ast, pathlib
    pipeline = pathlib.Path(__file__).resolve().parent.parent / "pipeline.py"
    tree = ast.parse(pipeline.read_text(encoding="utf-8"))
    write_sites = []
    for node in ast.walk(tree):
        targets = (
            node.targets if isinstance(node, ast.Assign) else
            [node.target] if isinstance(node, (ast.AugAssign, ast.AnnAssign)) else
            []
        )
        for tgt in targets:
            # _routing_action can be Name (single assign) or Tuple (unpacking
            # from _resolve_actual_speaker return).  Both count as writes.
            if isinstance(tgt, ast.Name) and tgt.id == "_routing_action":
                write_sites.append(node.lineno)
            elif isinstance(tgt, ast.Tuple):
                for elt in tgt.elts:
                    if isinstance(elt, ast.Name) and elt.id == "_routing_action":
                        write_sites.append(node.lineno)
    # During the deletion PR: count is 2 (the legacy unpacking at 7325 and
    # the override at 7419) pre-deletion, becomes 1 post-deletion.
    # The invariant gets tightened to assert == 1 in Step 9 as part of
    # the deletion commit.
    assert len(write_sites) <= 2, (
        f"Found {len(write_sites)} write sites at lines {write_sites} — "
        "P0.10 expects 2 pre-deletion (legacy + override), 1 post-deletion. "
        "More than 2 means a third writer landed and routing-source N is no "
        "longer 1 (audit assumption violated)."
    )
```

This test runs in CI before Step 6's deletion. Post-deletion it's tightened to `assert len(write_sites) == 1`.

**Rationale:** N=1 is the load-bearing assumption that makes the deletion structurally simple. AST verification proves it; future refactors that violate it fail CI immediately.

---

### Step 2 — Add `_p0_short_utterance_gap_hold_current` rule

**Purpose:** Fix Bug-W by covering the 0.3 ≤ utt < 0.5 utterance band that the new reconciler's existing P0 rules left exposed.

**Location:** `core/reconciler.py`, inserted between `_p0_short_utterance_ambiguous_multi_session` and `_p0_pure_noise_hold_current` (after the audio-gated rules, before the noise-floor rule).

**Rule design:**
```python
def _p0_short_utterance_gap_hold_current(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """Bug-W (2026-05-17 live validation): cover the 0.3-0.5s utterance gap.

    The existing P0 cascade leaves a coverage gap:
      - _p0_pure_noise_hold_current requires utt < 0.3s
      - _p0_short_utterance_hard_mismatch requires utt >= 0.5s (audio-gate)
      - _p0_short_utterance_ambiguous_multi_session requires utt >= 0.5s
    Utterances in [0.3, 0.5) fall through ALL P0 rules with no hold-current
    decision, then through P1/P2/P3 (which require v_pid), then land on
    _p4_new_stranger_low_match → phantom stranger session opened despite
    cur_pid being active.

    Legacy router pipeline.py:1233 had a catch-all `return cur_pid, 'current'`
    for any utt < MIN_UTTERANCE_SECS (1.0s) with cur_pid active.  Phase 4
    cutover (2026-04-29) intentionally removed the 1.0s blanket floor to
    score post-expiry voices instead of silently mis-attributing — that
    removal was correct for the 0.5-1.0s post-expiry case but accidentally
    exposed the 0.3-0.5s in-session gap.

    Narrow scope (auditor D7 (a1)): cover only 0.3-0.5s.  The 0.5-1.0s
    band is intentionally NOT held — Phase 4's design routes it through
    the audio-gated mismatch rules or normal P1-P5 cascade.
    """
    if (claim.utterance_duration is not None
            and VOICE_ROUTING_NOISE_FLOOR_SECS <= claim.utterance_duration < VOICE_ROUTING_MIN_AUDIO_FOR_SCORE
            and session.cur_pid is not None):
        return RoutingDecision(
            pid=session.cur_pid,
            action="current",
            reasoning=(
                f"short utterance gap ({claim.utterance_duration:.2f}s in "
                f"[{VOICE_ROUTING_NOISE_FLOOR_SECS}, "
                f"{VOICE_ROUTING_MIN_AUDIO_FOR_SCORE}) — below audio-gate, "
                f"above noise floor) — hold cur_pid={session.cur_pid!r}"
            ),
        )
    return None
```

**Position in RULES list** (between Tier 2 audio-gated mismatch and pure-noise floor):
```python
RULES: list = [
    _p0_short_utterance_hard_mismatch,         # 0.5 <= utt < 1.0 + score < FLOOR
    _p0_short_utterance_ambiguous_multi_session,  # 0.5 <= utt < 1.0 + ambiguous + multi-session
    _p0_short_utterance_gap_hold_current,      # ★ NEW: 0.3 <= utt < 0.5 + cur_pid → current
    _p0_pure_noise_hold_current,               # utt < 0.3 + cur_pid → current
    _p0_short_utterance_no_session,            # utt < 0.3 + no cur_pid → skip
    # ... P1-P5 unchanged ...
]
```

**Why this position:** The two audio-gated mismatch rules MUST fire first if their conditions match (they have stricter preconditions). The gap rule then catches the [0.3, 0.5) interval that neither mismatch rule nor the noise-floor rule covers. Order is load-bearing — testing per the table in Step 5 confirms it.

---

### Step 3 — Bug-W regression test

**Purpose:** Pin the exact Bug-W failure mode as a regression guard. Mirrors P0.6.7v2's deliberate-regression-check pattern and P0.11's hard-case test discipline.

**Location:** `tests/test_p10_routing_invariants.py` (same file as Step 1).

**Test shape:** verbatim from the proposed reproduction in `tests/p0_10_pre_audit_bug_w_evidence.md`:

```python
def test_bug_w_short_utterance_gap_holds_current_session():
    """Bug-W (2026-05-17 prod boot): 0.45s utterance + voice=0.021 +
    cur_pid active + mature gallery + n_diarize=0 must hold the current
    session — not open a phantom stranger.

    The reconciler's pre-P0.10 behavior fired _p4_new_stranger_low_match
    and opened stranger_c907181f despite the legacy router (shadow-logged)
    correctly returning 'current'.  Plan v1 adds _p0_short_utterance_gap_
    hold_current to fix the 0.3-0.5s coverage gap.
    """
    from core.reconciler import (
        reconcile, IdentityClaim, PresenceState, SessionState,
    )
    claim = IdentityClaim(
        pid=None, confidence=0.021,
        utterance_duration=0.45, n_diarize_segments=0,
        reasoning="ECAPA gallery miss on short utt",
    )
    presence = PresenceState(
        persons_in_frame={"jagan_001": {"source": "face", "last_seen": time.time()}},
        unrecognized_tracks={},
    )
    session = SessionState(
        cur_pid="jagan_001", cur_person_type="best_friend",
        n_active_sessions=2, voice_gallery_sizes={"jagan_001": 30},
        cur_holder_voice_n=30,
    )
    decision = reconcile(claim, presence, session)

    assert decision.action == "current", (
        f"Bug-W regression: 0.45s utterance produced "
        f"action={decision.action!r} (rule={decision.rule_fired!r}); "
        "expected 'current' from _p0_short_utterance_gap_hold_current"
    )
    assert decision.pid == "jagan_001"
    assert decision.rule_fired == "_p0_short_utterance_gap_hold_current", (
        f"Expected the gap-rule to fire; got {decision.rule_fired!r}.  "
        "If a different rule fires for this input, the cascade order is "
        "wrong or the gap-rule's gate condition is mis-specified."
    )
```

**Additional regression tests at the boundaries** (covers the gap rule's edges):
- `test_gap_rule_does_not_fire_at_audio_gate_boundary` — utt = 0.5s (exact boundary; audio-gated rules should fire instead)
- `test_gap_rule_does_not_fire_at_noise_floor_boundary` — utt = 0.3s (exact boundary; noise-floor rule should fire instead)
- `test_gap_rule_does_not_fire_when_no_cur_pid` — cur_pid=None (no session to hold; fall-through to short_utterance_skip)
- `test_gap_rule_fires_at_top_of_range` — utt = 0.499s (just below the 0.5 audio-gate)

5 tests total for Bug-W coverage.

---

### Step 4 — D7-watch telemetry for 0.5–1.0s band

**Purpose:** During the 7-day validation window, surface any divergences in the 0.5–1.0s utterance band so the auditor's D7 concern ("legacy's 1.0s floor was also papering over latent bugs in `_p0_short_utterance_hard_mismatch` / `_p0_short_utterance_ambiguous_multi_session` that haven't surfaced yet") is observable. If any divergence appears there, the gap rule's scope needs revisiting BEFORE legacy deletion.

**Location:** Augment the existing Reconciler-Shadow divergence log at pipeline.py:7400-7408 (NOT deleted in this PR — kept for the validation window per D5/D6).

**Telemetry shape:**
```python
if _rc_decision.action != _routing_action:
    # P0.10 D7 watch: surface divergences in the 0.5-1.0s band specifically,
    # so the auditor's concern about latent _p0_short_utterance_*_mismatch
    # bugs the legacy's 1.0s floor was silently guarding is observable.
    _band_label = ""
    if _utterance_secs is not None:
        if 0.5 <= _utterance_secs < 1.0:
            _band_label = " [BAND:0.5-1.0s — D7 watch]"
        elif 0.3 <= _utterance_secs < 0.5:
            _band_label = " [BAND:0.3-0.5s — Bug-W gap]"
        elif _utterance_secs < 0.3:
            _band_label = " [BAND:<0.3s — noise floor]"
        else:
            _band_label = f" [BAND:>=1.0s — {_utterance_secs:.2f}s]"
    # D4: rich logging by default — capture claim + both routing decisions
    # + state snapshot + audio ref + timestamp.
    print(
        f"[Reconciler-Shadow] {_now_log_ts()} divergence{_band_label}: "
        f"legacy={_routing_action!r} pid={_resolved_pid!r} "
        f"new={_rc_decision.action!r} rule={_rc_decision.rule_fired!r} "
        f"new_pid={_rc_decision.pid!r} "
        f"reason={_rc_decision.reasoning!r} "
        f"claim=(v_pid={_v_pid!r}, v_score={_v_score:.3f}, "
        f"utt={(_utterance_secs or 0.0):.2f}s, "
        f"n_diarize={_diar_seg_count}) "
        f"session=(cur_pid={_cur_pid!r}, cur_type={_cur_person_type!r}, "
        f"n_active={len(_session_store.peek_all_snapshots())}) "
        f"presence_keys={list(_rs_pif_view.keys())!r}"
    )
```

**Validation gate consumption:**
- Operator (Jagan) greps the boot logs for `[Reconciler-Shadow]` lines during the 7-day window
- Any line tagged `[BAND:0.5-1.0s — D7 watch]` triggers D7 reconsideration — the gap rule's scope may need to widen to 0.3-1.0s
- Any line tagged `[BAND:0.3-0.5s — Bug-W gap]` AFTER the gap rule lands is a regression — the gap rule isn't firing when it should
- Zero divergences in those two bands after 100 routing decisions OR 14 calendar days (whichever later) = validation passes

---

### Step 5 — C1-C21 + N1-N6 contract tests with explicit mapping table

**Purpose:** Per auditor's Item 3, every contract item from the audit's deliverable 5 MUST have a test companion. Mirrors P0.9's `verify_post`/`verify_present` discipline — every contract item is testable, and a violation surfaces as a CI failure.

**Location:** `tests/test_p10_reconciler_contract.py` (new file, separate from regression tests for grep-ability).

**Contract-to-test mapping table** (lands in Plan v1 for auditor review; the test file's docstring duplicates it):

| Contract | Test name | Notes |
|---|---|---|
| C1 (P0a Tier 1 hard mismatch) | `test_c1_tier1_hard_mismatch_returns_short_utterance_voice_mismatch` | utt=0.7s, score=0.10, cur_pid active → action=`short_utterance_voice_mismatch` |
| C2 (P0b Tier 2 ambiguous multi-session) | `test_c2_tier2_ambiguous_multi_session_returns_mismatch` | utt=0.7s, score=0.30, n_active=2 → `short_utterance_voice_mismatch` |
| C3 (Bug-W gap rule, P0c successor) | `test_c3_gap_rule_holds_current` | utt=0.45s, cur_pid → `current` (this is the Bug-W regression test from Step 3) |
| C4 (P0d no-session short-utt skip) | `test_c4_no_session_short_utt_skip` | utt=0.4s, cur_pid=None → `short_utterance_skip` |
| C5 (P1 confident voice switch) | `test_c5_confident_voice_switch` | v_pid!=cur_pid, score≥switch_threshold → `switch_enrolled` |
| C6 (P2a face+voice agree) | `test_c6_face_voice_agree_switch` | mid-range + face in frame + score≥FACE_ASSIST_MIN → `switch_enrolled` |
| C7 (P2b face + weak voice) | `test_c7_face_with_weak_voice_returns_ambiguous` | mid-range + face + score<FACE_ASSIST_MIN → `ambiguous` |
| C8 (P2c no face) | `test_c8_midrange_no_face_returns_ambiguous` | mid-range, no face → `ambiguous` |
| C9 (P3a self-match below floor) | `test_c9_self_match_below_floor_returns_ambiguous` | v_pid==cur_pid, score<SELF_MATCH_FLOOR → `ambiguous` |
| C10 (P3b thin stranger relaxed) | `test_c10_thin_stranger_offscreen_holds_current` | thin stranger holder, offscreen → `current` |
| C11 (P3c offscreen mature ambiguous) | `test_c11_offscreen_mature_returns_ambiguous` | mature holder, offscreen, score<OFFSCREEN_FLOOR → `ambiguous` |
| C12 (P3d self-match confirmed) | `test_c12_self_match_with_face_returns_current` | v_pid==cur_pid, face visible → `current` |
| C13 (P3.5 bootstrapping stranger hold) | `test_c13_bootstrapping_stranger_holds_current` | stranger holder, gallery<N_INITIAL_VOICE → `current` |
| C14 (P4a multi-segment mismatch) | `test_c14_multi_segment_low_score_drops` | n_diarize≥2, low score, n_active≥2 → `multi_segment_voice_mismatch` |
| C15 (P4b new stranger low match) | `test_c15_new_stranger_low_match_opens_session` | v_pid=None, 0<score<threshold, utt≥0.5s, cur_pid active → `new_stranger` |
| C16 (P4c single-segment mismatch) | `test_c16_single_segment_mature_drops` | n_diarize=1, mature, audio≥0.5s, n_active≥2 → `single_segment_voice_mismatch` |
| C17 (P4d voice ambiguous, no candidates) | `test_c17_voice_ambiguous_no_candidates_holds_current` | v_pid=None, score=0, no candidates → `current` |
| C18 (P4e voice ambiguous, with candidates) | `test_c18_voice_ambiguous_with_candidates_returns_ambiguous` | v_pid=None, scene candidates≥1 → `ambiguous` |
| C19 (P5a no session, low-score stranger) | `test_c19_no_session_low_score_opens_stranger` | cur_pid=None, 0<score<threshold → `new_stranger` |
| C20 (P5b no session, no signal) | `test_c20_no_session_no_signal_no_action` | cur_pid=None, score=0, no unrec → `no_action` |
| C21 (last resort ambiguous) | `test_c21_last_resort_ambiguous` | input doesn't match any rule → `ambiguous` |
| N1 (Bug-W exact failure mode) | (same as C3 regression) | covered by `test_c3_gap_rule_holds_current` |
| N2 (0.3-1.0s band stranger ban) | `test_n2_no_stranger_session_in_in_session_short_utt_band` | Parametrized: utt ∈ {0.31, 0.40, 0.49} with cur_pid → never `new_stranger` |
| N3 (no mis-attribution on switch) | `test_n3_no_misattribution_to_previous_holder_on_switch` | switch_enrolled case + previous holder pid check |
| N4 (no stranger on multi-segment cross-talk) | `test_n4_no_stranger_on_cross_talk_multi_session` | n_diarize≥2 + low score + n_active≥2 → never `new_stranger` |
| N5 (no drop on bootstrapping mismatch) | `test_n5_no_drop_when_holder_is_bootstrapping` | single-segment + low score + holder voice_n<MATURE → never `single_segment_voice_mismatch` |
| N6 (no invented pids) | `test_n6_decision_pid_in_known_set` | Property-style test: for any input, returned `decision.pid` is either `None`, `claim.pid`, or `session.cur_pid` — never a fabricated value |

**Total: 27 contract tests + 5 Bug-W boundary tests + 1 AST verification = 33 new tests in P0.10**. Plus parametrization on N2 (3 inputs) and N6 (Hypothesis-style) bumps the executed-test-count higher.

**File header docstring includes the mapping table** so future maintainers can grep `contract_id` to find the test.

---

### Step 6 — Delete `_resolve_actual_speaker` (270 lines)

**Location:** `pipeline.py:1147-1417`.

**Edit shape:** single contiguous range deletion. No code outside the function range moves. Mechanical extraction — no "while I'm here" cleanup of imports or helpers (the function's helpers `_face_in_frame`, `_count_scene_candidates`, `_effective_switch_threshold` may or may not have external callers — audit separately in a follow-up).

**Pre-delete confirmation:** Step 1's AST test must report `len(write_sites) == 2` (legacy + override). Post-delete it reports 1 (override only). The AST test gets tightened to `== 1` in the same commit.

---

### Step 7 — Delete legacy call site

**Location:** `pipeline.py:7325-7341` — the `_resolve_actual_speaker(...)` call producing `(_resolved_pid, _routing_action)`.

**Edit shape:** 17-line block deletion. The variables `_resolved_pid` and `_routing_action` get their initial assignment from Step 9's collapsed override (no gap in variable definition order).

---

### Step 8 — Delete Reconciler-Shadow divergence block

**Location:** `pipeline.py:7400-7408` — the `if _rc_decision.action != _routing_action: print(...)` block.

**Edit shape:** 9-line block deletion. Note: D4's rich logging (Step 4 enhancement) lives INSIDE this block — both go away together. Validation logging is OUT for the post-validation PR; for the legacy-deletion PR it stays (because the shadow infrastructure is still alive for the 7-day window).

**Actually — revised:** Step 8 only fires in the follow-up PR (post-validation), NOT the legacy-deletion PR. The Reconciler-Shadow block stays alive during the validation window. Updating sequence below to clarify.

---

### Step 9 — Collapse override conditional

**Location:** `pipeline.py:7415-7419` (current shape):
```python
if ROUTING_USE_RECONCILER and _rc_decision is not None:
    _resolved_pid = _rc_decision.pid
    _routing_action = _rc_decision.action
```

**Post-deletion shape:**
```python
# P0.10: reconciler is the only routing source.  Legacy router deleted;
# ROUTING_USE_RECONCILER flag kept alive for the 7-day validation window
# (follow-up PR deletes the flag once validation closes).
if _rc_decision is not None:
    _resolved_pid = _rc_decision.pid
    _routing_action = _rc_decision.action
else:
    # Reconciler error path: try/except caught a bug in reconciler.py.
    # Production-safe fallback — drop the turn (was: legacy_decision).
    # With legacy gone, the safest action is short_utterance_skip-style.
    _resolved_pid = None
    _routing_action = "no_action"
```

**Note on error path:** Pre-P0.10 the try/except at L7409-7413 caught reconciler bugs and fell back to the legacy decision. Post-P0.10 there IS no legacy fallback. The replacement is `_routing_action = "no_action"` (drop the turn). This is honest — if the reconciler crashes, we can't route the turn, so dropping is the only safe option.

This is a load-bearing behavior change that the audit didn't fully anticipate. Plan v1 surfaces it explicitly so auditor can review. **Architect+auditor decision needed:** is "drop on reconciler crash" the right fallback, or should it be `"current"` (hold)? Either choice is reviewable.

**Recommendation:** `"no_action"` for the legacy-deletion PR. Hold-current is plausible but the legacy's behavior in that branch was its full 270-line cascade, not just "hold." Without the legacy, "drop" is more honest than "hold." Re-evaluate in the follow-up PR if validation logs show reconciler crashes are common.

---

### Step 10 — Retarget or delete test-side source-inspection refs (D8.2)

**Location:** `test_pipeline.py:16590-16593`:
```python
idx = src.find('if _routing_action == "switch_enrolled":')
next_elif = src.find('elif _routing_action ==', idx + 1)
```

**Read the test's full context** before deciding retarget vs delete. The test purpose may be obsolete after the if/elif chain stays the same shape (the dispatch block at pipeline.py:7421-7618 is NOT deleted — only the routing source is). Likely the test stays valid as-is.

**Action plan:**
- Read the surrounding test function in Step 10's commit
- If test asserts properties of the dispatch chain (which still exists): keep as-is
- If test asserts properties of `_resolve_actual_speaker` (which is deleted): retarget to the reconciler equivalent OR delete with documented rationale
- Don't speculate now — read the test in v2 / implementation phase

---

### Step 11 — Keep `ROUTING_USE_RECONCILER` flag alive for validation window

**Location:** `core/config.py`.

**Edit:** none — the flag stays. Document in Step 12's CLAUDE.md milestone that the flag is intentionally not deleted in this PR.

**Validation procedure for Jagan** (to be documented separately when the deletion PR ships):
1. After deletion PR merges: monitor `[Reconciler-Shadow]` log lines for 7 days OR 100 routing decisions, whichever comes later
2. Specifically grep for `[BAND:0.5-1.0s — D7 watch]` and `[BAND:0.3-0.5s — Bug-W gap]` tags
3. Zero divergences in those bands = validation passes
4. Any divergence in 0.5-1.0s band = file a follow-up bug, do NOT proceed with shadow-infra deletion until the rule scope is revisited
5. Any divergence in 0.3-0.5s band after the gap rule lands = regression in the rule itself

After validation passes: separate follow-up PR deletes (a) `ROUTING_USE_RECONCILER` flag, (b) `_rc_decision is not None` conditional (becomes unconditional), (c) Reconciler-Shadow divergence block at L7400-7408, (d) the rich-logging telemetry added in Step 4.

---

### Step 12 — CLAUDE.md milestone with 3 explicit non-claims

**Location:** CLAUDE.md header line.

**Milestone entry shape:** documents what shipped, plus three explicit non-claims (per the P0.9 closure pattern):

1. **Gap rule preserves legacy semantic for 0.3-0.5s only** — NOT a full 0.3-1.0s blanket-hold restoration. Phase 4 cutover's design intent (score post-expiry voices at 0.5-1.0s) is preserved. If the auditor's D7 concern manifests during validation, the gap rule's scope widens in a follow-up PR.
2. **FK-style cross-DB invariants out of scope** — same non-claim as P0.9. Routing decisions affect SessionStore, PresenceStore, etc.; cross-store consistency is the existing P0.6 ratchet's responsibility, not P0.10's.
3. **Shadow infrastructure + flag deletion lives in follow-up PR** — per D5/D6. This PR removes the legacy ROUTING SOURCE but keeps the safety hatch alive for validation.

---

## Files touched by this PR

**New files:**
- `tests/test_p10_routing_invariants.py` — AST verification + Bug-W regression tests (Steps 1+3)
- `tests/test_p10_reconciler_contract.py` — C1-C21 + N1-N6 contract tests (Step 5)

**Modified files:**
- `core/reconciler.py` — add `_p0_short_utterance_gap_hold_current` rule + register in RULES list (Step 2)
- `pipeline.py` — Steps 6 + 7 + 9 (delete legacy function, delete call site, collapse override). Step 4 (telemetry enhancement) modifies the existing divergence-log block in place.
- `test_pipeline.py` — Step 10 (test-side source-inspection refs, inline decision)
- `CLAUDE.md` — Step 12 (milestone entry)

**Untouched files** (kept alive for validation window per D5/D6):
- `core/config.py::ROUTING_USE_RECONCILER` flag — deletion deferred
- `pipeline.py` Reconciler-Shadow divergence block at L7400-7408 — kept alive (modified by Step 4 enhancement, deleted in follow-up PR)

---

## Test count delta

| Item | Test count |
|---|---|
| Step 1: AST verification | 1 |
| Step 3: Bug-W regression + 4 boundary | 5 |
| Step 5: C1-C21 contract | 21 |
| Step 5: N1-N6 forbidden behaviors | 6 |
| **Total new tests** | **33** |

Plus parametrization on N2 (3 cases) and N6 (Hypothesis-style with `max_examples=200` for cheap property check on returned pid set).

**Estimated suite delta:** 2189 → ~2222+ passing after Plan v1's code lands. Infra debt stays at 8.

---

## Rollback plan (D6)

If P0.10 ships and a regression appears within 7 days of daily use resuming:

1. **Single-commit revert** of the Plan v1 PR. The `_resolve_actual_speaker` function, the legacy call site, and the override conditional all restore from git history.
2. **The `ROUTING_USE_RECONCILER=False` toggle** is still available as a hot-rollback even before the git revert — flipping the flag activates the legacy path... **except** the legacy path is deleted. So the toggle becomes dead.

**Revised:** during the 7-day validation window, the `ROUTING_USE_RECONCILER` flag is **observability-only**, not a rollback hatch. The actual rollback is git revert. Document this clearly in the CLAUDE.md milestone.

If validation passes and the follow-up PR ships: the flag goes away. Rollback path becomes: git revert + git revert (two-commit revert of the follow-up + the deletion).

---

## Validation gate (p2 policy)

**Gate:** 100 routing decisions during the validation window **OR** 14 calendar days, **whichever comes later** (auditor's p2 lock — prevents thin-traffic green-lighting).

**Operator procedure:**
1. After deletion PR merges, Jagan resumes daily use.
2. Boot logs accumulate `[Reconciler-Shadow]` divergence lines (rich-format per D4).
3. Wall-clock counter: 14 days from merge.
4. Traffic counter: count routing decisions in boot logs (any `[Voice] ... Routing:` line, or alternative — count distinct `_rc_decision` log emissions). Threshold: 100.
5. Gate closes when BOTH counters satisfied. **Whichever-later** means low-traffic operators don't green-light prematurely.
6. Gate close → follow-up PR ships (shadow infra + flag delete).

**Validation artifact:** `tests/p0_10_validation_window.md` (created during validation) captures the actual divergence count + band breakdown + traffic count. Same pattern as P0.9's `terminal_output.md` boot artifact.

---

## Out of scope (per audit + D8)

- **D8.1** — reconciler context preservation (`cur_person_type` not threaded into `_p4_new_stranger_low_match`). Deferred to post-P0.10 follow-up. NOT a Bug-W root cause.
- **Helper-function audit** — `_face_in_frame`, `_count_scene_candidates`, `_effective_switch_threshold` may have external callers beyond the deleted `_resolve_actual_speaker`. Plan v1 does not audit these; if they're unused after the deletion, a follow-up cleanup PR addresses them.
- **Validation artifact format** — `tests/p0_10_validation_window.md` shape is documented above but not produced during Plan v1 work.
- **Telemetry sampling** — D4's rich logging fires on EVERY divergence. If validation traffic produces too many lines, downstream sampling lands in a follow-up PR (not blocking).

---

## Plan v1 sign-off gates

Auditor/architect can hard-stop on any of:

- **Sign-off block A** (rule design): is `_p0_short_utterance_gap_hold_current`'s gate condition correct? Does the position in RULES list make sense? Reviewer can revise before implementation begins.
- **Sign-off block B** (Step 9 error path): is `"no_action"` the right fallback when `_rc_decision is None` post-deletion, or should it be `"current"`? Either reviewable.
- **Sign-off block C** (Step 4 telemetry verbosity): D4 says "rich by default." If reviewer prefers something narrower, surface here. The currently-proposed log line is ~12 fields wide.
- **Sign-off block D** (Step 5 contract test count): 27 contract tests = 21 C-tests + 6 N-tests. Plus boundary tests + AST verification + Bug-W regression = 33 total. Auditor can request more (e.g. N6 parametrization shape) or fewer (e.g. merge boundary tests into C3).
- **Sign-off block E** (validation procedure): is the operator procedure for the validation window clear enough? Should it be a separate runbook MD?

---

## Estimate

| Phase | Time |
|---|---|
| Plan v1 → v2 (architect+auditor review + revisions) | 1-2 days wall-clock |
| Implementation (Steps 1-12, code + tests) | 1-2 dev days |
| Validation window (7-day wall-clock + 100 routing decisions) | 7-14 days wall-clock |
| Follow-up PR (shadow + flag deletion) | 0.5 dev days |
| **Total P0.10 closure** | **~2-3 dev days + traffic-gated validation** |

Awaiting architect + auditor review of Plan v1.
