"""P0.10 routing invariants — RULES-ordering + Bug-W regression + boundaries
+ Phase 2 AST single-write-site + N7 fail-safe.

This file ships across both phases of P0.10:
  - Phase 1: Step 1 + Step 3 contracts.
  - Phase 2: AST single-write-site test (Step 1 leftover, post-legacy-delete)
             + 2 N7 tests for the Block B (B2) hold-current + WARN log fail-safe.

Coverage:
  - Step 1: RULES-ordering invariant (Block A structural lock; refined per
    auditor R1 to non-decreasing ordering allowing ties; R2 documents that
    gap-detection is human review's job, not this test's).
  - Step 3: Bug-W regression test (the exact 2026-05-17 boot-log shape) +
    boundary tests pinning the new _p0_short_utterance_gap_hold_current
    rule's gate semantics.
  - Phase 2: single-write-site invariant for `_routing_action` (no
    tuple-write to a deleted legacy function remains) +
    `_resolve_actual_speaker` does not appear in pipeline.py +
    N7 source-inspection on the B2 fail-safe + WARN log code shape.

Reference: tests/p0_10_plan_v2.md (Block A + Block B + auditor R1/R2 refinements).
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from core.reconciler import (
    _CASCADE,
    EXPECTED_RULES_BY_BAND,
    _p0_short_utterance_gap_hold_current,
    reconcile,
)
from core.reconciler_state import SessionState
from core.voice_channel import IdentityClaim
from core.vision_channel import PresenceState


_PIPELINE_PATH = Path(__file__).resolve().parent.parent / "pipeline.py"


# ══════════════════════════════════════════════════════════════════════════
# STEP 1 — RULES-ordering invariant (Block A + auditor R1 + R2)
# ══════════════════════════════════════════════════════════════════════════


def test_p0_cascade_ordered_by_ascending_utterance_band():
    """P0 rules must be in non-decreasing LOWER_BOUND order.

    Ties (multiple rules at same band) are allowed and indicate rules
    that fire under different non-overlapping conditions within the same
    utterance-duration band (e.g., the 0.5-1.0s hard-mismatch rule and
    ambiguous-multi-session rule both fire when utt_dur >=
    MIN_AUDIO_FOR_SCORE but on different v_score / n_active conditions;
    similarly the 0.0-0.3s pure-noise rule and no-session rule are
    mutually exclusive on cur_pid).

    Putting a rule LATER than its duration band would let an earlier
    rule fire on inputs the later rule was supposed to cover — exactly
    the failure shape Bug-W exhibited (gap-rule landing late wouldn't
    help; an earlier rule would already have fallen through to P4).

    This test catches misordering but NOT coverage gaps. Future P0 rule
    additions require manual gap-completeness review against the
    positive contract at tests/p0_10_routing_audit.md C1-C21. The
    validation window's zero-divergence-in-gap-band gate is the
    empirical safety net for coverage regressions (per auditor R2).

    Per auditor R1 — non-strict ordering: do not tighten this assertion
    to strict-ascending. Two P0 rules currently share LOWER_BOUND=0.5
    (`_p0_short_utterance_hard_mismatch` +
    `_p0_short_utterance_ambiguous_multi_session`) and two share
    LOWER_BOUND=0.0 (`_p0_pure_noise_hold_current` +
    `_p0_short_utterance_no_session`). Strict-ascending would either
    fail (because rules tie) or silently allow swapping their order;
    neither is right.
    """
    p0_rules = [r for r in _CASCADE if r.__name__.startswith("_p0_")]
    bounds = [r.LOWER_BOUND for r in p0_rules]
    assert bounds == sorted(bounds), (
        f"P0 cascade out of duration-band order.\n"
        f"  rule order: {[r.__name__ for r in p0_rules]}\n"
        f"  LOWER_BOUNDs: {bounds}\n"
        f"  expected sorted: {sorted(bounds)}\n"
        "Reorder per non-decreasing LOWER_BOUND — putting a rule out of "
        "band order lets an earlier rule fire on inputs the later rule "
        "was meant to cover. Ties allowed (multiple rules in same band)."
    )


def test_every_p0_rule_carries_lower_bound_attr():
    """Every P0 rule MUST carry an explicit LOWER_BOUND attribute.

    Per Plan v2 sign-off block A.1 — the choice was attribute-on-rule
    (more robust to refactors) over docstring parsing (fragile across
    edits). This test is the structural enforcement: a future P0 rule
    added without LOWER_BOUND breaks the ordering test's predicate
    AND breaks this test, surfacing the omission immediately.
    """
    p0_rules = [r for r in _CASCADE if r.__name__.startswith("_p0_")]
    missing = [r.__name__ for r in p0_rules if not hasattr(r, "LOWER_BOUND")]
    assert not missing, (
        f"P0 rules without LOWER_BOUND attr: {missing}. "
        "Add `<rule>.LOWER_BOUND = <value>` after the rule definition "
        "(see _p0_pure_noise_hold_current as template)."
    )


def test_expected_rules_by_band_references_existing_rules():
    """P0.10.1 F2 invariant: every rule name in `EXPECTED_RULES_BY_BAND`
    must correspond to a real callable in `_CASCADE`.

    Catches future refactors that rename a rule (or add/remove one) but
    forget to update the band-mapping co-located alongside the rules.
    Without this guard, the Reconciler-Shadow band-divergence trigger
    would silently emit false-positive divergence logs every time the
    "expected" rule fired under its new name — the validation window
    would fail on phantom divergences.

    Mapping lives at `core/reconciler.py::EXPECTED_RULES_BY_BAND`.
    """
    cascade_names = {r.__name__ for r in _CASCADE}
    for band, expected_rules in EXPECTED_RULES_BY_BAND.items():
        for rule_name in expected_rules:
            assert rule_name in cascade_names, (
                f"EXPECTED_RULES_BY_BAND[{band!r}] references "
                f"{rule_name!r} but no such rule exists in _CASCADE. "
                f"Existing rules: {sorted(cascade_names)}. Either the "
                f"rule was renamed (update the mapping) or the mapping "
                f"is stale (remove the dead entry)."
            )


def test_p0_10_gap_rule_present_in_cascade():
    """P0.10 Block A: `_p0_short_utterance_gap_hold_current` must be in
    the cascade and positioned between the noise-floor rule and the
    audio-gate rules so it actually fires on the Bug-W signature.

    Regression guard for "Plan v2 inserted the rule but a future refactor
    accidentally removed it" — without this rule, Bug-W's 0.45s utterance
    again falls through to `_p4_new_stranger_low_match`.
    """
    names = [r.__name__ for r in _CASCADE]
    assert "_p0_short_utterance_gap_hold_current" in names, (
        "P0.10 Bug-W coverage gone — gap rule missing from cascade"
    )
    gap_idx = names.index("_p0_short_utterance_gap_hold_current")
    noise_idx = names.index("_p0_pure_noise_hold_current")
    hard_idx = names.index("_p0_short_utterance_hard_mismatch")
    assert noise_idx < gap_idx < hard_idx, (
        f"Gap rule out of position: pure_noise at {noise_idx}, gap at "
        f"{gap_idx}, hard_mismatch at {hard_idx}. Required order: "
        "pure_noise < gap < hard_mismatch."
    )


# ══════════════════════════════════════════════════════════════════════════
# STEP 3 — Bug-W regression + boundary tests
# ══════════════════════════════════════════════════════════════════════════
#
# Auditor's R3 acceptance criterion: regression test pinning the EXACT
# 2026-05-17 boot-log signature. If P0.10 ships and Bug-W's input still
# produces `new_stranger`, the deletion isn't safe.
#
# Reproduces tests/p0_10_pre_audit_bug_w_evidence.md.


def _make_inputs(
    *,
    pid=None,
    confidence=0.0,
    utterance_duration=1.5,
    n_diarize_segments=0,
    cur_pid="jagan_001",
    cur_person_type="best_friend",
    n_active_sessions=2,
    cur_holder_voice_n=30,
    visible_pids=(),
):
    """Build (claim, presence, session) with sensible Bug-W-shaped defaults."""
    claim = IdentityClaim(
        pid=pid,
        confidence=confidence,
        n_diarize_segments=n_diarize_segments,
        utterance_duration=utterance_duration,
        reasoning="test",
    )
    presence = PresenceState(
        visible_pids=visible_pids,
        unrecognized_track_ids=(),
    )
    session = SessionState(
        cur_pid=cur_pid,
        cur_person_type=cur_person_type,
        n_active_sessions=n_active_sessions,
        voice_gallery_sizes={cur_pid: cur_holder_voice_n} if cur_pid else {},
        cur_holder_voice_n=cur_holder_voice_n,
        now=1779008461.0,
    )
    return claim, presence, session


def test_bug_w_short_utterance_gap_holds_current_session():
    """P0.10 acceptance gate — auditor R3.

    Reproduces the exact 2026-05-17 boot-log signature
    (terminal_output_2026-05-17_143659.md L685-696):
      - utterance_duration = 0.45s
      - voice confidence = 0.021 (gallery miss)
      - pyannote segments = 0
      - cur_pid = Jagan (mature gallery, n_active=2 with Lexi)
      - cur_person_type = best_friend

    Expected decision: action='current', pid=cur_pid, rule_fired=
    `_p0_short_utterance_gap_hold_current`.

    Without the gap rule, the cascade falls through every P0/P1/P2/P3
    rule and lands on `_p4_new_stranger_low_match` which opens a
    phantom stranger session. Locks P0.10's whole correctness story.
    """
    claim, presence, session = _make_inputs(
        pid=None,
        confidence=0.021,
        utterance_duration=0.45,
        n_diarize_segments=0,
        cur_pid="jagan_001",
        cur_person_type="best_friend",
        n_active_sessions=2,
        cur_holder_voice_n=30,
    )
    decision = reconcile(claim, presence, session)
    assert decision.action == "current", (
        f"Bug-W regression: 0.45s utterance with low voice score opened "
        f"action={decision.action!r} (rule={decision.rule_fired!r}); "
        "expected 'current' — the 0.3-0.5s band must hold the session "
        "to prevent phantom stranger sessions on short social closers."
    )
    assert decision.pid == "jagan_001", (
        f"Bug-W: expected pid=jagan_001, got {decision.pid!r}"
    )
    assert decision.rule_fired == "_p0_short_utterance_gap_hold_current", (
        f"Bug-W: wrong rule fired: {decision.rule_fired!r}. "
        "Expected _p0_short_utterance_gap_hold_current."
    )


def test_gap_rule_does_not_fire_at_audio_gate_boundary():
    """Boundary: at utt = 0.5s (MIN_AUDIO_FOR_SCORE) the gap rule must
    NOT fire — control passes to `_p0_short_utterance_hard_mismatch`
    (or the cascade beyond) so the voice score IS scored.

    Gap rule's upper bound is strict `<` per Block A spec — at exactly
    0.5s the audio-gate rules are responsible.
    """
    claim, presence, session = _make_inputs(
        confidence=0.021,
        utterance_duration=0.50,
        cur_pid="jagan_001",
        cur_person_type="best_friend",
        n_active_sessions=2,
    )
    decision = reconcile(claim, presence, session)
    assert decision.rule_fired != "_p0_short_utterance_gap_hold_current", (
        f"Gap rule fired at utt=0.50s but should not — at exactly "
        f"MIN_AUDIO_FOR_SCORE the audio-gate rules take over. "
        f"Got rule={decision.rule_fired!r} action={decision.action!r}."
    )


def test_gap_rule_does_not_fire_at_noise_floor_boundary():
    """Boundary: at utt = 0.29s (just below NOISE_FLOOR_SECS=0.3) the
    pure-noise rule fires first — gap rule must NOT fire.

    Gap rule's lower bound is `>=` 0.3 per Block A. At 0.29s,
    `_p0_pure_noise_hold_current` handles the turn (still returns
    'current' so behavior is preserved, but the rule_fired must
    reflect which rule actually fired).
    """
    claim, presence, session = _make_inputs(
        confidence=0.021,
        utterance_duration=0.29,
        cur_pid="jagan_001",
        cur_person_type="best_friend",
        n_active_sessions=2,
    )
    decision = reconcile(claim, presence, session)
    assert decision.rule_fired == "_p0_pure_noise_hold_current", (
        f"At utt=0.29s the pure-noise rule should fire, not the gap rule. "
        f"Got rule={decision.rule_fired!r}."
    )
    # Behavior still correct (action='current') but ensures the right
    # rule is taking ownership of the band.
    assert decision.action == "current"


def test_gap_rule_does_not_fire_when_no_cur_pid():
    """Boundary: when no session is active, gap rule must NOT fire
    (it requires cur_pid is not None per Block A spec). Without a
    session to hold, the turn falls through; in practice the cascade
    typically lands on `_p5_no_session_*` or the last-resort rule.

    Mirrors the contract C3-but-no-session edge: hold-current is
    meaningless without a current pid.
    """
    claim, presence, session = _make_inputs(
        confidence=0.021,
        utterance_duration=0.45,
        cur_pid=None,
        cur_person_type="",
        n_active_sessions=0,
        cur_holder_voice_n=0,
    )
    decision = reconcile(claim, presence, session)
    assert decision.rule_fired != "_p0_short_utterance_gap_hold_current", (
        f"Gap rule fired when cur_pid=None — must require cur_pid set. "
        f"Got rule={decision.rule_fired!r} action={decision.action!r}."
    )


def test_gap_rule_fires_at_top_of_range():
    """Top-of-range: at utt = 0.499s the gap rule must still fire.

    Verifies the upper boundary is exclusive on 0.5s — any value
    strictly less than MIN_AUDIO_FOR_SCORE is in the gap band.
    """
    claim, presence, session = _make_inputs(
        confidence=0.05,
        utterance_duration=0.499,
        cur_pid="jagan_001",
        cur_person_type="best_friend",
        n_active_sessions=1,
        cur_holder_voice_n=15,
    )
    decision = reconcile(claim, presence, session)
    assert decision.rule_fired == "_p0_short_utterance_gap_hold_current", (
        f"Gap rule must fire at top of range (utt=0.499s). "
        f"Got rule={decision.rule_fired!r} action={decision.action!r}."
    )
    assert decision.action == "current"
    assert decision.pid == "jagan_001"


def test_gap_rule_fires_at_bottom_of_range():
    """Bottom-of-range: at utt = 0.3s (exact NOISE_FLOOR_SECS) the gap
    rule must fire — its lower bound is inclusive (`>=`).

    This is a deliberate companion to the 0.29s noise-floor test:
    at 0.30s the pure-noise rule's `<` check fails so it returns
    None, and the gap rule's `>=` check succeeds. The boundary itself
    belongs to the gap rule.
    """
    claim, presence, session = _make_inputs(
        confidence=0.05,
        utterance_duration=0.30,
        cur_pid="jagan_001",
        cur_person_type="best_friend",
        n_active_sessions=1,
        cur_holder_voice_n=15,
    )
    decision = reconcile(claim, presence, session)
    assert decision.rule_fired == "_p0_short_utterance_gap_hold_current", (
        f"Gap rule must fire at bottom of range (utt=0.30s, inclusive). "
        f"Got rule={decision.rule_fired!r}."
    )


# ══════════════════════════════════════════════════════════════════════════
# Direct-rule test — _p0_short_utterance_gap_hold_current called in isolation
# ══════════════════════════════════════════════════════════════════════════


def test_gap_rule_isolated_returns_routing_decision():
    """Direct call to the rule helper (no dispatcher) — verifies the
    rule's signature + return shape match the cascade contract.

    Useful for debugging future failures: if the cascade-level Bug-W
    test fails AND this isolated test passes, the cascade's ORDERING
    is what's broken (some earlier rule swallowed the input). If both
    fail, the rule's GATE is broken.
    """
    claim, presence, session = _make_inputs(
        confidence=0.021,
        utterance_duration=0.45,
        cur_pid="jagan_001",
    )
    decision = _p0_short_utterance_gap_hold_current(claim, presence, session)
    assert decision is not None, "gap rule should fire on 0.45s gap-band input"
    assert decision.action == "current"
    assert decision.pid == "jagan_001"
    # rule_fired is set by the dispatcher, not the rule helper, so it
    # stays empty here (the helper returns RoutingDecision with default "").


# ══════════════════════════════════════════════════════════════════════════
# PHASE 2 — single-write-site invariant + legacy-name-removed guards
# ══════════════════════════════════════════════════════════════════════════
#
# After Step 6+7 the legacy function is gone and the override conditional
# (Step 9) is the single source of `_routing_action`. These tests pin the
# post-deletion structure so a future refactor can't accidentally re-introduce
# a parallel write site OR resurrect the deleted function.


def _pipeline_src() -> str:
    return _PIPELINE_PATH.read_text(encoding="utf-8")


def test_resolve_actual_speaker_function_removed_from_pipeline():
    """The legacy `_resolve_actual_speaker` function MUST NOT be defined
    anywhere in pipeline.py post-Phase-2. A future revert would surface here.

    Tolerance for the deletion marker comment: the function NAME appearing
    inside a `# ...` comment is acceptable (the deletion-marker block at the
    old call-site location names the deleted function for archaeology).
    The forbidden pattern is the `def _resolve_actual_speaker(` token.
    """
    src = _pipeline_src()
    assert "def _resolve_actual_speaker(" not in src, (
        "P0.10 Phase 2 regression: `_resolve_actual_speaker` function "
        "definition resurrected in pipeline.py. The reconciler is the sole "
        "routing source post-Phase-2. If a legitimate need to re-introduce "
        "a legacy decision path arises, surface it as a separate routing "
        "module — do not re-add the deleted function."
    )


def test_routing_action_has_single_logical_write_site():
    """Post-Phase-2 `_routing_action` is written by exactly one logical
    control-flow construct — the if/else override at the dispatch site.

    Asserts AST-level that:
      - Exactly 2 statement-level assignments target `_routing_action`
        (the True branch sets it from `_rc_decision.action`; the else
        branch sets it to "current" as the B2 fail-safe).
      - Both writes are simple `Name` targets (NOT tuple-unpacking from
        a function call — that's the legacy shape that was deleted).
      - Both writes share the same enclosing `If` node (i.e., they're the
        if/else of the same conditional, not two unrelated assignments).

    Without this lock, a future refactor could re-introduce a parallel
    `_routing_action = ...` assignment site (e.g., from a new legacy-shaped
    helper) and silently shadow the reconciler's decision.
    """
    src = _pipeline_src()
    tree = ast.parse(src)

    write_nodes: list[ast.Assign] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "_routing_action":
                    write_nodes.append(node)
                elif isinstance(tgt, ast.Tuple):
                    for el in tgt.elts:
                        if isinstance(el, ast.Name) and el.id == "_routing_action":
                            write_nodes.append(node)
                            break

    assert len(write_nodes) == 2, (
        f"Expected exactly 2 `_routing_action` write sites post-Phase-2, "
        f"got {len(write_nodes)} at lines {[n.lineno for n in write_nodes]}. "
        "The reconciler override + B2 fail-safe is the only write source; "
        "a third write means a parallel routing path was re-introduced."
    )

    # All writes must be simple Name targets (no tuple-unpacking from a
    # deleted legacy function).
    for n in write_nodes:
        for tgt in n.targets:
            assert isinstance(tgt, ast.Name), (
                f"Line {n.lineno}: `_routing_action` is being tuple-assigned "
                f"(target type={type(tgt).__name__!s}). The legacy router's "
                "`_resolved_pid, _routing_action = _resolve_actual_speaker(...)` "
                "shape is forbidden post-Phase-2."
            )

    # Both writes must share the same enclosing `If` node — i.e., they're
    # the if/else of the same conditional, not two independent assignments.
    parent_ifs: list[ast.If] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            for w in write_nodes:
                if w in node.body or w in node.orelse:
                    parent_ifs.append(node)
                    break

    # Dedup by id (Python's `in` uses ==; AST nodes use identity)
    unique_ifs = {id(n): n for n in parent_ifs}
    assert len(unique_ifs) == 1, (
        f"Expected both `_routing_action` writes to share one if/else "
        f"control-flow construct, got {len(unique_ifs)} distinct enclosing "
        "If nodes. The B2 fail-safe must live in the same if/else as the "
        "main `_rc_decision is not None` branch."
    )


# ══════════════════════════════════════════════════════════════════════════
# Block B — N7 fail-safe (B2 hold-current + WARN log on no-rule-fired)
# ══════════════════════════════════════════════════════════════════════════
#
# Behavioral testing of the N7 fail-safe via pipeline.run() requires the
# full async harness (camera, audio executor, session store seed) — out of
# proportion for what the production code is: a one-shot `else` clause.
#
# Source-inspection achieves the same invariant lock as P0.8.2 F1/F2 and
# P0.11 detectors: the structural code shape is the test, and a future
# revert (dropping the else clause or its WARN log) is the regression.
#
# The two N7 tests below cover both failure modes documented in Plan v2 / N7:
#   (1) reconcile returned None — covered by source-inspection on the
#       `else:` branch's hold-current + WARN log shape.
#   (2) reconcile raised — covered by the try/except wrapper around the
#       reconciler call, asserted by checking the WARN-log structure
#       depends ONLY on _rc_decision being None (regardless of cause).


def test_n7_no_rule_fired_holds_current_and_warns_structural():
    """N7: when `_rc_decision is None` (no rule fired OR reconciler raised
    and was caught), the override site MUST hold the current session AND
    emit a `[Reconciler] WARN: no rule fired` log line.

    Plan v2 Block B (B2): user-visible silence (drop turn with no_action)
    is a worse failure mode than a transient missed-routing-update —
    hold-current preserves the user's experience while making the gap
    loud in operator logs.

    This test source-inspects the structure:
      - The override at the dispatch site has an `else:` clause.
      - The else clause sets `_routing_action = "current"` (hold).
      - The else clause sets `_resolved_pid = _cur_pid` (current holder).
      - The else clause emits a print containing both `[Reconciler] WARN`
        AND `no rule fired` (operator grep targets per Block E gate).
    """
    src = _pipeline_src()
    tree = ast.parse(src)

    # Locate the `if _rc_decision is not None:` block (the override).
    target_if: ast.If | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            if (
                isinstance(test, ast.Compare)
                and len(test.ops) == 1
                and isinstance(test.ops[0], ast.IsNot)
                and isinstance(test.left, ast.Name)
                and test.left.id == "_rc_decision"
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value is None
            ):
                target_if = node
                break

    assert target_if is not None, (
        "Could not locate `if _rc_decision is not None:` override block in "
        "pipeline.py. Either it was renamed or removed; the B2 fail-safe "
        "invariant depends on this control-flow shape."
    )

    assert target_if.orelse, (
        "N7 violation: override has no `else:` clause. The B2 fail-safe "
        "(hold-current + WARN log) MUST run when _rc_decision is None — "
        "silent fall-through is forbidden."
    )

    # Inspect the else body for required statements.
    else_src = ast.unparse(ast.Module(body=target_if.orelse, type_ignores=[]))

    assert "_routing_action = 'current'" in else_src or '_routing_action = "current"' in else_src, (
        f"N7 violation: else clause does not set `_routing_action = 'current'`. "
        f"B2 fail-safe must hold current session.\nelse body:\n{else_src}"
    )
    assert "_resolved_pid = _cur_pid" in else_src, (
        f"N7 violation: else clause does not set `_resolved_pid = _cur_pid`. "
        f"B2 fail-safe must hold the current pid.\nelse body:\n{else_src}"
    )
    assert "[Reconciler] WARN" in else_src, (
        f"N7 violation: else clause does not emit `[Reconciler] WARN` log "
        f"line. Block E's gate criteria depend on grep'ing this marker.\n"
        f"else body:\n{else_src}"
    )
    assert "no rule fired" in else_src, (
        f"N7 violation: else clause does not emit `no rule fired` text. "
        f"This is the second half of the Block E grep target.\n"
        f"else body:\n{else_src}"
    )


def test_n7_reconciler_exception_path_falls_through_to_warn():
    """N7 companion: when `reconcile()` (inside the try block) raises,
    `_rc_decision` stays at its initial `None` value (set before the try)
    and the override's `else:` branch fires — same B2 fail-safe behavior.

    This test asserts the structural pre-conditions for that path:
      - `_rc_decision = None` initialization appears BEFORE the try block
        that calls reconcile.
      - The try block has an `except Exception` handler that does NOT
        re-raise (allowing fall-through to the override).
      - The reconcile call is INSIDE the try block (so its exceptions
        are caught).
    """
    src = _pipeline_src()
    tree = ast.parse(src)

    # Find `_rc_decision = None` assignments (the initial sentinel).
    init_nodes = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_rc_decision" for t in n.targets)
        and isinstance(n.value, ast.Constant)
        and n.value.value is None
    ]
    assert init_nodes, (
        "N7 companion: `_rc_decision = None` initialization not found in "
        "pipeline.py. The fail-safe relies on this sentinel — when the "
        "try block raises before reaching `_rc_decision = _rc_reconcile(...)`, "
        "the override's else branch fires."
    )

    # Find the try block that DIRECTLY wraps the `_rc_decision = _rc_reconcile(...)`
    # assignment. AST walk encounters outer try-finally blocks first whose nested
    # bodies happen to contain the call, so filter to try blocks whose immediate
    # body has the assignment as a direct child.
    target_try: ast.Try | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    targets_decision = any(
                        isinstance(t, ast.Name) and t.id == "_rc_decision"
                        for t in stmt.targets
                    )
                    is_reconcile_call = (
                        isinstance(stmt.value, ast.Call)
                        and isinstance(stmt.value.func, ast.Name)
                        and stmt.value.func.id == "_rc_reconcile"
                    )
                    if targets_decision and is_reconcile_call:
                        target_try = node
                        break
            if target_try is not None:
                break

    assert target_try is not None, (
        "N7 companion: try block wrapping `_rc_reconcile(...)` not found. "
        "The exception path of the fail-safe requires this wrapper."
    )

    # Assert the except handler does NOT re-raise (catches and logs).
    found_handler = False
    for h in target_try.handlers:
        found_handler = True
        handler_src = ast.unparse(ast.Module(body=h.body, type_ignores=[]))
        assert "raise" not in handler_src.split(), (
            f"N7 companion: try/except around _rc_reconcile re-raises — "
            f"that would propagate the exception past the fail-safe and "
            f"break the turn. Handler body:\n{handler_src}"
        )
    assert found_handler, (
        "N7 companion: try block has no except handler. The reconciler "
        "must not crash a turn — catching is mandatory."
    )
