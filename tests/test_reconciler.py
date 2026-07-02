"""Reconciler structural + per-rule acceptance tests.

Phase 3 of the Voice/Vision Independence refactor.

This file contains:
  - 3 STRUCTURAL tests (#175, landed 2026-04-29):
    * Import-boundary (reconciler.py must not depend on pipeline)
    * Cascade ordering invariants (5 explicit assertions)
    * Build-routing-inputs shape (landed in #177)
  - 22 PER-RULE acceptance tests (#176, landed 2026-04-29 onward; 23rd
    test added at P0.B6 closure 2026-05-21 for post-TODO rule).
  - D4 AST forward-property tripwire (P0.B6, 2026-05-21) — enforces
    rule-to-test coverage via _CASCADE membership scan.

Reference docs: RECONCILER_DESIGN.md (sections 1, 5).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import importlib

from core.reconciler import (
    _CASCADE,
    _build_routing_inputs,
    _last_resort_ambiguous,
    _p0_short_utterance_ambiguous_multi_session,
    _p0_short_utterance_hard_mismatch,
    _p0_pure_noise_hold_current,
    _p0_short_utterance_gap_hold_current,
    _p0_short_utterance_no_session,
    _p1_confident_voice_switch,
    _p2_midrange_face_assist_below_floor,
    _p2_midrange_face_assist_switches,
    _p2_midrange_no_face_returns_ambiguous,
    _p3_5_bootstrapping_stranger_hold,
    _p3_self_match_below_floor,
    _p3_self_match_offscreen_mature,
    _p3_self_match_thin_stranger_relaxed,
    _p3_self_match_with_face,
    _p4_multi_segment_mismatch,
    _p4_new_stranger_low_match,
    _p4_pyannote_vouched_stranger,
    _p4_single_segment_mismatch,
    _p4_voice_ambiguous_no_candidates,
    _p4_voice_ambiguous_with_candidates,
    _p5_no_session_new_stranger,
    _p5_no_session_no_action,
    reconcile,
)
from core.reconciler_state import SessionState, VALID_ACTIONS
from core.voice_channel import IdentityClaim
from core.vision_channel import PresenceState
from tests.reconciler_golden import RECONCILER_GOLDEN_CASES, UNCHECKED

# 2b deliverable — the 27 per-rule tests below DERIVE their inputs + expected
# outcomes from the golden registry instead of duplicating fixtures inline.
# Mirrors the precedent in test_p10_reconciler_contract.py (C1-C21).
_GOLDEN = {c.case_id: c for c in RECONCILER_GOLDEN_CASES}


def _from_golden(case_id):
    """Build (claim, presence, session, case) for a golden case_id.

    Splats the registry's plain-dict payloads into the channel/state
    dataclasses here (channel imports are allowed in the test driver, never
    in the golden module). ``_GOLDEN[case_id]`` raises KeyError on a typo —
    exact case_id strings are load-bearing.
    """
    case = _GOLDEN[case_id]
    return (
        IdentityClaim(**case.claim),
        PresenceState(**case.presence),
        SessionState(**case.session),
        case,
    )


# ══════════════════════════════════════════════════════════════════════════
# STRUCTURAL TEST 1 — import boundary
# ══════════════════════════════════════════════════════════════════════════


def test_reconciler_imports_no_pipeline():
    """core/reconciler.py must NOT import pipeline (architectural boundary).

    AST-based check. Substring match would false-positive on natural
    docstring references to "pipeline" (the module mentions it in its own
    module docstring).
    """
    src = importlib.import_module("core.reconciler")
    tree = ast.parse(open(src.__file__, encoding="utf-8").read())
    forbidden = {"pipeline"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in forbidden, (
                    f"reconciler.py must NOT import {alias.name!r} "
                    f"(architectural boundary)"
                )
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            assert root not in forbidden, (
                f"reconciler.py must NOT import from {node.module!r} "
                f"(architectural boundary)"
            )


# ══════════════════════════════════════════════════════════════════════════
# STRUCTURAL TEST 2 — cascade ordering invariants
# ══════════════════════════════════════════════════════════════════════════
#
# These assertions are the audit trail. Each ordering encodes a Sessions
# 60–122 calibration fix. Reordering rules in the source file is fine,
# but reordering the _CASCADE tuple regresses real bugs.


def _cascade_rule_names() -> list[str]:
    return [r.__name__ for r in _CASCADE]


def test_cascade_has_23_rules():
    """The cascade is exactly 23 rules. Adding/removing rules without
    spec review is a calibration drift risk; this test forces the
    addition or removal to be deliberate.

    Was 22 before P0.10 (2026-05-17) — bumped by Block A's
    `_p0_short_utterance_gap_hold_current` rule that closes the 0.3-0.5s
    coverage gap exposed when Phase 4 cutover removed the legacy router's
    1.0s blanket-hold floor (Bug-W).
    """
    assert len(_CASCADE) == 23, (
        f"Cascade must have exactly 23 rules; got {len(_CASCADE)}. "
        f"Adding or removing a rule changes calibration; update the "
        f"design doc + mapping table BEFORE editing _CASCADE."
    )


def test_cascade_ordering_live_bug_fix_invariant():
    """The 2026-04-29 live-bug fix is structural: _p4_pyannote_vouched_stranger
    MUST fire before _p4_voice_ambiguous_no_candidates. Any future refactor
    that swaps these returns the Lexi-via-ElevenLabs misattribution captured
    in canary_2026-04-29_lexi_misattribution.md (line 564).
    """
    rule_names = _cascade_rule_names()
    pyannote_idx = rule_names.index("_p4_pyannote_vouched_stranger")
    fallthrough_idx = rule_names.index("_p4_voice_ambiguous_no_candidates")
    assert pyannote_idx < fallthrough_idx, (
        "Cascade ordering broken: _p4_pyannote_vouched_stranger must fire "
        "BEFORE _p4_voice_ambiguous_no_candidates. Restoring this ordering "
        "bug would re-introduce the Lexi-via-ElevenLabs misattribution "
        "captured in tests/fixtures/canary_2026-04-29_lexi_misattribution.md "
        "(line 564)."
    )


def test_cascade_ordering_p0_before_p1_through_p5():
    """Priority 0 (short-utterance gate) is the highest priority — fires
    BEFORE all P1–P5 rules. Without this, a short utterance would route
    through the normal voice-ID cascade and fragment into stranger sessions
    on micropauses.
    """
    rule_names = _cascade_rule_names()
    p0_indices = [i for i, n in enumerate(rule_names) if n.startswith("_p0_")]
    later_indices = [
        i for i, n in enumerate(rule_names)
        if n.startswith(("_p1_", "_p2_", "_p3_", "_p3_5_", "_p4_", "_p5_"))
    ]
    assert p0_indices, "no _p0_ rules found"
    assert later_indices, "no later-priority rules found"
    assert max(p0_indices) < min(later_indices), (
        f"All _p0_ rules must fire before any _p1_/_p2_/_p3_/_p4_/_p5_ rule. "
        f"Last _p0_ index: {max(p0_indices)}, "
        f"first later-priority index: {min(later_indices)}."
    )


def test_cascade_ordering_p1_before_p2():
    """Priority 1 (confident voice match) fires BEFORE all Priority 2
    (mid-range) rules. Confident match wins over mid-range — without this
    ordering, a 0.85 voice match would get treated as mid-range when the
    Priority 2 rules examine it first.
    """
    rule_names = _cascade_rule_names()
    p1_indices = [i for i, n in enumerate(rule_names) if n.startswith("_p1_")]
    p2_indices = [i for i, n in enumerate(rule_names) if n.startswith("_p2_")]
    assert p1_indices and p2_indices, "missing _p1_ or _p2_ rules"
    assert max(p1_indices) < min(p2_indices), (
        "_p1_ rules must fire before _p2_ rules"
    )


def test_cascade_ordering_p4_inner_sequence():
    """Priority 4 inner ordering must be exact:
        _p4_multi_segment_mismatch
        _p4_pyannote_vouched_stranger
        _p4_voice_ambiguous_no_candidates

    The pyannote_vouched_stranger position between multi-segment-mismatch
    and voice-ambiguous-no-candidates encodes Sessions 118 / 121 / 2026-04-29
    fixes. Any reorder regresses one of three bugs.
    """
    rule_names = _cascade_rule_names()
    multi_idx = rule_names.index("_p4_multi_segment_mismatch")
    pyannote_idx = rule_names.index("_p4_pyannote_vouched_stranger")
    fallthrough_idx = rule_names.index("_p4_voice_ambiguous_no_candidates")
    assert multi_idx < pyannote_idx < fallthrough_idx, (
        f"P4 inner ordering broken — required: "
        f"_p4_multi_segment_mismatch < _p4_pyannote_vouched_stranger < "
        f"_p4_voice_ambiguous_no_candidates. "
        f"Got indices: {multi_idx} / {pyannote_idx} / {fallthrough_idx}."
    )


def test_cascade_last_rule_is_last_resort_ambiguous():
    """_last_resort_ambiguous (Q1) must be _CASCADE[-1]. It catches the
    final fallthrough where v_pid != cur_pid AND v_score is below the
    midrange-switch floor AND cur_pid is occupied — without it, that
    state would silently fall through to the dispatcher's no_action
    fallback, changing the legacy function's `ambiguous` return.
    """
    assert _CASCADE[-1].__name__ == "_last_resort_ambiguous", (
        f"_last_resort_ambiguous must be the LAST cascade entry; "
        f"got {_CASCADE[-1].__name__!r} as last."
    )


# ══════════════════════════════════════════════════════════════════════════
# STRUCTURAL TEST 3 — build-routing-inputs
# ══════════════════════════════════════════════════════════════════════════


def test_build_routing_inputs_produces_expected_dataclasses():
    """Snapshots a representative pipeline state (active sessions dict +
    voice_gallery_sizes + persons_in_frame + unrecognized_tracks + the
    routing args), calls _build_routing_inputs(), asserts the produced
    IdentityClaim + PresenceState + SessionState match expected shapes
    AND values.

    Catches pipeline-state-shape drift that fixture-based unit tests
    can't detect. If a future PR changes _active_sessions schema or
    renames a vision-channel field, every per-rule test will still pass
    against hand-built fixtures while the production wiring silently
    produces wrong reconciler inputs. This test fails loud at commit.

    Filtering policy mirrors legacy `_face_in_frame` / `_count_scene_candidates`:
      - visible_pids excludes voice-only entries AND stale entries (last_recognized_at
        beyond VOICE_ROUTING_FACE_STALE_SECS)
      - unrecognized_track_ids excludes stale tracks
      - cur_holder_voice_n derived from voice_gallery_sizes[cur_pid]
    """
    from core.config import VOICE_ROUTING_FACE_STALE_SECS
    from core.voice_channel import IdentityClaim
    from core.vision_channel import PresenceState
    from core.reconciler_state import SessionState

    now = 1000.0
    fresh_ts = now - 0.5  # within VOICE_ROUTING_FACE_STALE_SECS=2.0
    stale_ts = now - 10.0  # well past stale window

    # Representative pipeline state — mixed face/voice sources, fresh + stale
    persons_in_frame = {
        "jagan_abc": {  # face source, fresh — should appear in visible_pids
            "source": "face",
            "last_recognized_at": fresh_ts,
            "last_seen": fresh_ts,
            "conf": 0.87,
            "name": "Jagan",
        },
        "lexi_def": {  # face source but STALE — should be filtered out
            "source": "face",
            "last_recognized_at": stale_ts,
            "last_seen": stale_ts,
            "conf": 0.62,
            "name": "Lexi",
        },
        "voice_only_abc": {  # voice source — should be filtered out (Bug B)
            "source": "voice",
            "last_recognized_at": fresh_ts,
            "last_seen": fresh_ts,
            "conf": 0.55,
            "name": "Phantom",
        },
    }
    unrecognized_tracks = {
        42: fresh_ts,  # fresh — should be in unrecognized_track_ids
        7: stale_ts,   # stale — should be filtered out
    }
    voice_gallery_sizes = {"jagan_abc": 20, "lexi_def": 5, "kara_friend": 3}

    claim, presence, session = _build_routing_inputs(
        v_pid=None,
        v_score=0.0,
        n_diarize_segments=2,
        utterance_duration=2.0,
        persons_in_frame=persons_in_frame,
        unrecognized_tracks=unrecognized_tracks,
        cur_pid="jagan_abc",
        cur_person_type="best_friend",
        n_active_sessions=1,
        voice_gallery_sizes=voice_gallery_sizes,
        now=now,
        voice_reasoning="ECAPA: no enrolled match",
    )

    # IdentityClaim — direct field copy
    assert isinstance(claim, IdentityClaim)
    assert claim.pid is None
    assert claim.confidence == 0.0
    assert claim.n_diarize_segments == 2
    assert claim.utterance_duration == 2.0
    assert claim.reasoning == "ECAPA: no enrolled match"

    # PresenceState — visible_pids filtered for fresh + face-source only
    assert isinstance(presence, PresenceState)
    assert set(presence.visible_pids) == {"jagan_abc"}, (
        f"visible_pids must exclude voice-source AND stale entries; "
        f"got {presence.visible_pids!r}. "
        f"Stale 'lexi_def' (last_recognized_at={stale_ts}, threshold="
        f"{VOICE_ROUTING_FACE_STALE_SECS}s) and voice-only 'voice_only_abc' "
        f"must NOT appear."
    )
    assert set(presence.unrecognized_track_ids) == {42}, (
        f"unrecognized_track_ids must exclude stale tracks; got "
        f"{presence.unrecognized_track_ids!r}"
    )
    assert presence.per_pid_confidence == {"jagan_abc": 0.87}
    assert presence.frame_ts == now

    # SessionState — direct field copy + cur_holder_voice_n derivation
    assert isinstance(session, SessionState)
    assert session.cur_pid == "jagan_abc"
    assert session.cur_person_type == "best_friend"
    assert session.n_active_sessions == 1
    assert session.voice_gallery_sizes == voice_gallery_sizes
    assert session.cur_holder_voice_n == 20  # voice_gallery_sizes["jagan_abc"]
    assert session.now == now


def test_build_routing_inputs_handles_no_session_state():
    """When cur_pid is None (P5 entry path), cur_holder_voice_n MUST be 0
    (not raise KeyError, not pull a stale value). Guards against future
    refactors that forget to handle the empty-session case.
    """
    claim, presence, session = _build_routing_inputs(
        v_pid=None,
        v_score=0.0,
        n_diarize_segments=1,
        utterance_duration=1.5,
        persons_in_frame={},
        unrecognized_tracks={},
        cur_pid=None,
        cur_person_type="",
        n_active_sessions=0,
        voice_gallery_sizes={},
        now=0.0,
    )
    assert session.cur_pid is None
    assert session.cur_holder_voice_n == 0
    assert presence.visible_pids == ()
    assert presence.unrecognized_track_ids == ()


# ══════════════════════════════════════════════════════════════════════════
# Cascade dispatch sanity check (structural)
# ══════════════════════════════════════════════════════════════════════════


def test_p5_no_session_returns_no_action():
    """Rule 21: cur_pid is None AND no voice signal AND no unrecognized
    tracks → no_action. Truly empty turn — nothing to attribute, nothing
    to open.

    Pre-rule-21 (skeleton phase) this fell through to the dispatcher
    fallback returning no_action with rule_fired=""; with rule 21
    implemented it now returns via the rule itself.
    """
    # NARROWED at Spec 1 D2 (2026-05-30): golden fixture carries
    # utterance_duration sub-MIN_AUDIO (was 1.5s). Post-D2 a REAL-LENGTH
    # no_signal no-session turn opens a gated stranger; the "truly empty,
    # nothing to do" turn this test asserts is now the sub-0.5s case
    # (new_stranger's utt>=0.5 OR clause stays False, so it falls to no_action).
    claim, presence, session, case = _from_golden(
        "PR1_p5_no_session_returns_no_action"
    )

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    assert decision.action in VALID_ACTIONS
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid
    # With all 22 rules implemented, rule 21 (_p5_no_session_no_action)
    # catches this state — no longer the dispatcher fallback.
    assert decision.rule_fired == _p5_no_session_no_action.__name__ == case.expected_rule_fired


# ══════════════════════════════════════════════════════════════════════════
# PER-RULE TESTS — #176 (in lockstep with rule bodies)
# ══════════════════════════════════════════════════════════════════════════
#
# Order per reviewer 2026-04-29: live-bug rule first.


def test_p4_pyannote_vouched_stranger_opens_session():
    """2026-04-29 LIVE-BUG REGRESSION GUARD.

    Reproduces the misattribution captured in
    tests/fixtures/canary_2026-04-29_lexi_misattribution.md, lines 559-577.

    Scene: Lexi (via ElevenLabs from a phone) said "Hi Kara, can you tell
    me what is the escape velocity of earth?". Pyannote correctly returned
    2 segments (line 562). ECAPA found no enrolled match (v_score=0.0;
    log line 564 shows the score absent because it was 0). Only Jagan was
    in the active session (n_active_sessions=1). Jagan was visible.

    Legacy routing (line 564) fell through to "current — voice ambiguous,
    no other candidates in scene" and misattributed Lexi's question to
    Jagan (line 566). Brain answered Jagan's history (line 577).

    The reconciler MUST intercept this case via _p4_pyannote_vouched_stranger
    BEFORE _p4_voice_ambiguous_no_candidates (cascade-ordering invariant
    enforced separately). Action MUST be `new_stranger` so caller mints a
    fresh session for Lexi instead of attributing to Jagan.
    """
    # Inputs + expected outcome derive from the golden registry (2b).
    # Fixture-value provenance is in the docstring + canary md.
    claim, presence, session, case = _from_golden(
        "PR2_p4_pyannote_vouched_stranger_opens_session"
    )

    decision = reconcile(claim, presence, session)

    # Strong assertion: pin BOTH the action AND the specific rule fired.
    # `action == "new_stranger"` alone could match other rules; rule_fired
    # pin guards against future cascade reorders silently moving the match.
    assert decision.action == case.expected_action, (
        f"2026-04-29 live-bug regression: pyannote-vouched stranger in solo "
        f"room must route to `new_stranger`, got {decision.action!r}. "
        f"Rule fired: {decision.rule_fired!r}. "
        f"Reasoning: {decision.reasoning!r}"
    )
    assert decision.rule_fired == _p4_pyannote_vouched_stranger.__name__ == case.expected_rule_fired, (
        f"Wrong rule matched the live-bug fixture. Expected "
        f"_p4_pyannote_vouched_stranger; got {decision.rule_fired!r}. "
        f"This usually means cascade ordering broke (a P0/P1/P2/P3 rule "
        f"is now matching the fixture state) OR the live-bug rule's "
        f"predicate has drifted from the fixture's exact shape."
    )
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid, (
            "new_stranger action returns pid=None; caller mints fresh stranger pid"
        )


def test_p4_pyannote_vouched_stranger_negative_confidence():
    """Regression: ECAPA returns negative cosine score (not 0.0) on gallery miss.

    voice.identify() returns the actual best cosine similarity even when no match
    is found. When two speakers' L2-normalized embeddings are anti-correlated
    (different gender, accent, tone), the cosine can be negative (e.g., -0.05).
    The original _p4_pyannote_vouched_stranger checked == 0.0, missing negative
    scores entirely and causing the degenerate 'no rule matched' state.

    This is the exact Lexi scenario from the 2026-05-01 canary:
    pyannote returned 2 segments, ECAPA compared Lexi's voice against Jagan's
    gallery and got score -0.05 (anti-correlated). The fix changed == 0.0 to <= 0.0.
    """
    from core.reconciler import _p4_pyannote_vouched_stranger

    claim, presence, session, case = _from_golden(
        "PR3_p4_pyannote_vouched_stranger_negative_confidence"
    )

    decision = reconcile(claim, presence, session)

    assert decision.action == case.expected_action, (
        f"Negative ECAPA cosine (-0.05) must route to new_stranger, "
        f"got {decision.action!r}. Rule: {decision.rule_fired!r}. "
        f"Reasoning: {decision.reasoning!r}"
    )
    assert decision.rule_fired == _p4_pyannote_vouched_stranger.__name__ == case.expected_rule_fired, (
        f"Expected _p4_pyannote_vouched_stranger, got {decision.rule_fired!r}"
    )
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_p4_new_stranger_low_match_negative_confidence():
    """Regression: single-segment with negative ECAPA cosine routes to new_stranger.

    When pyannote returns 1 segment (single speaker) but ECAPA cosine is
    negative (stranger vs enrolled gallery), _p4_new_stranger_low_match must
    still open a new stranger session. The original 0.0 < confidence check
    excluded negative values.
    """
    from core.reconciler import _p4_new_stranger_low_match

    claim, presence, session, case = _from_golden(
        "PR4_p4_new_stranger_low_match_negative_confidence"
    )

    decision = reconcile(claim, presence, session)

    assert decision.action == case.expected_action, (
        f"Negative single-segment ECAPA (-0.08) must route to new_stranger, "
        f"got {decision.action!r}. Rule: {decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p4_new_stranger_low_match.__name__ == case.expected_rule_fired, (
        f"Expected _p4_new_stranger_low_match, got {decision.rule_fired!r}"
    )
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_p0_tier1_hard_mismatch_drops():
    """S92 P3.23 Tier 1: utt < MIN_UTTERANCE_SECS but >= MIN_AUDIO_FOR_SCORE,
    score < SHORT_UTT_FLOOR, cur_pid present → drop turn.

    Pre-S92 the blanket short-utterance floor held current; that broke the
    Lexi-joins-Jagan case (Lexi's brief 'Hi Kara' got attributed to Jagan).
    """
    from core.config import (
        VOICE_ROUTING_MIN_AUDIO_FOR_SCORE,
        VOICE_ROUTING_MIN_UTTERANCE_SECS,
        VOICE_ROUTING_SHORT_UTT_FLOOR,
    )
    claim, presence, session, case = _from_golden("PR5_p0_tier1_hard_mismatch_drops")
    # config-boundary self-checks against the golden fixture:
    # utt 0.7s in [MIN_AUDIO 0.5, MIN_UTTERANCE 1.0); score 0.10 < SHORT_UTT_FLOOR.
    assert claim.utterance_duration >= VOICE_ROUTING_MIN_AUDIO_FOR_SCORE
    assert claim.utterance_duration < VOICE_ROUTING_MIN_UTTERANCE_SECS
    assert claim.confidence < VOICE_ROUTING_SHORT_UTT_FLOOR

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"S92 P3.23 Tier 1 regression — expected drop, got {decision.action!r} "
        f"from rule {decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p0_short_utterance_hard_mismatch.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_p0_tier2_ambiguous_drops_in_multi_session():
    """S93 P3.23 Tier 2: same audio + utt constraints, score in
    [SHORT_UTT_FLOOR, SHORT_UTT_AMBIGUOUS) ambiguous zone, n_active >= 2 → drop.

    Solo session in same conditions (n_active == 1) holds current — guarded
    by separate test below to confirm the multi-session gate is the
    discriminator.
    """
    from core.config import (
        VOICE_ROUTING_SHORT_UTT_AMBIGUOUS,
        VOICE_ROUTING_SHORT_UTT_FLOOR,
    )
    claim, presence, session, case = _from_golden(
        "PR6_p0_tier2_ambiguous_drops_in_multi_session"
    )
    # score 0.30 in [SHORT_UTT_FLOOR 0.20, SHORT_UTT_AMBIGUOUS 0.40) ambiguous zone.
    assert VOICE_ROUTING_SHORT_UTT_FLOOR <= claim.confidence < VOICE_ROUTING_SHORT_UTT_AMBIGUOUS

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"S93 P3.23 Tier 2 regression — multi-session ambiguous-zone short "
        f"utterance must drop, got {decision.action!r} from {decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p0_short_utterance_ambiguous_multi_session.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_p0_short_utterance_holds_current():
    """Pure ECAPA noise floor (< 0.3s) + cur_pid → hold session.

    Below 0.3s ECAPA output is pure noise — the system holds the current
    session rather than attempting gallery scoring on unusable audio.
    This is the Phase 4 cutover floor (2026-04-29); utterances ≥ 0.3s
    now fall through to full gallery cascade instead of being held.
    """
    claim, presence, session, case = _from_golden("PR7_p0_short_utterance_holds_current")

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"Pure noise floor regression — utterance < 0.3s with cur_pid must "
        f"hold current, got {decision.action!r} from {decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p0_pure_noise_hold_current.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_p0_short_utterance_no_session_skips():
    """S67 Bug F variant: short utterance with cur_pid is None → drop.

    Nothing to hold and ECAPA on <1s is too noisy to seed a stranger profile.
    """
    claim, presence, session, case = _from_golden(
        "PR8_p0_short_utterance_no_session_skips"
    )

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"S67 Bug F variant regression — short utterance + no session must "
        f"skip, got {decision.action!r} from {decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p0_short_utterance_no_session.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


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
    claim, presence, session, case = _from_golden(
        "PR9_p0_short_utterance_gap_holds_current"
    )

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"Gap-band regression — utterance 0.3-0.5s with cur_pid must hold "
        f"current, got {decision.action!r} from {decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p0_short_utterance_gap_hold_current.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_p1_confident_switch_to_other_pid():
    """Confident voice match for a different enrolled person → switch_enrolled.

    Threshold scales with target's profile maturity via
    _effective_switch_threshold. Mature target (>= N_INITIAL_VOICE samples) =
    VOICE_SWITCH_THRESHOLD_MATURE; thin target = VOICE_SWITCH_THRESHOLD_THIN.
    Test uses mature target (gallery_n=20) so threshold=0.40; v_score=0.80
    clears it confidently.
    """
    from core.config import VOICE_SWITCH_THRESHOLD_MATURE

    claim, presence, session, case = _from_golden(
        "PR10_p1_confident_switch_to_other_pid"
    )
    assert claim.confidence >= VOICE_SWITCH_THRESHOLD_MATURE  # mature threshold

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"P1 confident match must switch to v_pid, got {decision.action!r} "
        f"from {decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p1_confident_voice_switch.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_p2_midrange_face_assist_switches():
    """S46 + S64 Bug O floor: mid-range voice [MIDRANGE, switch_threshold)
    AND target visible AND v_score >= FACE_ASSIST_MIN → switch_enrolled.

    Two-channel agreement licenses the switch. Thin gallery (n=3) gives
    switch_threshold = VOICE_SWITCH_THRESHOLD_THIN = 0.55; score 0.50
    fits in [MIDRANGE=0.30, 0.55) AND >= FACE_ASSIST_MIN=0.42.
    """
    from core.config import (
        VOICE_ROUTING_FACE_ASSIST_MIN,
        VOICE_ROUTING_MIDRANGE_SWITCH_MIN,
        VOICE_SWITCH_THRESHOLD_THIN,
    )

    claim, presence, session, case = _from_golden(
        "PR11_p2_midrange_face_assist_switches"
    )
    # Confirm score lands in P2 band, NOT P1
    assert claim.confidence >= VOICE_ROUTING_MIDRANGE_SWITCH_MIN
    assert claim.confidence >= VOICE_ROUTING_FACE_ASSIST_MIN
    assert claim.confidence < VOICE_SWITCH_THRESHOLD_THIN

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"P2 face-assisted switch must fire when target visible AND "
        f"score >= face-assist floor. Got {decision.action!r} from "
        f"{decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p2_midrange_face_assist_switches.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_p2_midrange_face_assist_below_floor_returns_ambiguous():
    """S64 Bug O: target visible BUT v_score < FACE_ASSIST_MIN → ambiguous.

    The 2026-04-20 phone-caller scenario: voice scored 0.314 against Jagan
    with Jagan's face visible (background bystander on the phone). Pre-S64
    routing treated this as confident switch and corrupted Jagan's pid.
    """
    from core.config import (
        VOICE_ROUTING_FACE_ASSIST_MIN,
        VOICE_ROUTING_MIDRANGE_SWITCH_MIN,
    )

    # score 0.35: in [MIDRANGE=0.30, FACE_ASSIST=0.42) — face visible but
    # voice too weak even with co-witness.
    claim, presence, session, case = _from_golden(
        "PR12_p2_midrange_face_assist_below_floor_returns_ambiguous"
    )
    assert VOICE_ROUTING_MIDRANGE_SWITCH_MIN <= claim.confidence < VOICE_ROUTING_FACE_ASSIST_MIN

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"S64 Bug O regression — weak voice + face visible must NOT switch, "
        f"got {decision.action!r} from {decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p2_midrange_face_assist_below_floor.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_p2_midrange_no_face_assist_returns_ambiguous():
    """Mid-range voice match, target NOT visible → ambiguous.

    Single-channel mid-range evidence isn't enough to switch sessions.
    Caller drops; if the next utterance brings face in frame OR confident
    voice, P1/P2 will fire on that turn instead.
    """
    # score 0.45: in [MIDRANGE=0.30, switch_threshold) for mature; target
    # not in visible_pids.
    claim, presence, session, case = _from_golden(
        "PR13_p2_midrange_no_face_assist_returns_ambiguous"
    )

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"P2 no-face mid-range must be ambiguous, got {decision.action!r} "
        f"from {decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p2_midrange_no_face_returns_ambiguous.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_p3_below_self_match_floor_returns_ambiguous():
    """S51 anti-poisoning: cur_pid's own profile matched but score below
    SELF_MATCH_FLOOR (0.30) → ambiguous, refuse to credit.

    Cross-talk or noise — crediting a 0.10 self-match would let any
    acoustically-similar stranger drift the holder's profile downward.
    """
    from core.config import VOICE_ROUTING_SELF_MATCH_FLOOR

    claim, presence, session, case = _from_golden(
        "PR14_p3_below_self_match_floor_returns_ambiguous"
    )
    assert claim.confidence < VOICE_ROUTING_SELF_MATCH_FLOOR

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"S51 anti-poisoning regression — sub-floor self-match must NOT "
        f"hold, got {decision.action!r} from {decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p3_self_match_below_floor.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_p3_thin_stranger_skips_offscreen_floor():
    """S71 Bug W: bootstrapping stranger's own voice scoring 0.30–0.45
    while offscreen is normal profile-warming, NOT a poisoning signal.

    Thin holder gets the offscreen floor RELAXED so the session continues
    accumulating samples. Mature poisoning protection (rule
    _p3_self_match_offscreen_mature) stays intact for grown profiles.

    The S71 canary: Chloe said 'My name is Chloe' at v=0.307 with 3/5
    samples; pre-fix dropped her turn, post-fix this rule fires →
    'current' so her session keeps accumulating.
    """
    from core.config import (
        N_INITIAL_VOICE,
        VOICE_ROUTING_SELF_MATCH_FLOOR,
        VOICE_ROUTING_SELF_MATCH_OFFSCREEN,
    )

    # Chloe's exact canary score, in [SELF_MATCH_FLOOR=0.30, OFFSCREEN=0.45)
    claim, presence, session, case = _from_golden(
        "PR15_p3_thin_stranger_skips_offscreen_floor"
    )
    assert VOICE_ROUTING_SELF_MATCH_FLOOR <= claim.confidence < VOICE_ROUTING_SELF_MATCH_OFFSCREEN
    assert session.cur_holder_voice_n < N_INITIAL_VOICE
    assert session.cur_pid not in presence.visible_pids
    assert session.cur_person_type == "stranger"

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"S71 Bug W regression — thin stranger holder must skip offscreen "
        f"floor, got {decision.action!r} from {decision.rule_fired!r}. "
        f"Pre-fix: dropped Chloe's session; post-fix: holds current so the "
        f"voice profile can mature."
    )
    assert decision.rule_fired == _p3_self_match_thin_stranger_relaxed.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_p3_offscreen_mature_floors_apply():
    """S64 mature poisoning protection: offscreen self-match for mature
    holder below SELF_MATCH_OFFSCREEN → ambiguous. Without this guard,
    a different speaker's mid-range match silently updates cur_pid's
    gallery and poisons the profile.
    """
    from core.config import (
        VOICE_ROUTING_SELF_MATCH_FLOOR,
        VOICE_ROUTING_SELF_MATCH_OFFSCREEN,
    )

    claim, presence, session, case = _from_golden(
        "PR16_p3_offscreen_mature_floors_apply"
    )
    assert VOICE_ROUTING_SELF_MATCH_FLOOR <= claim.confidence < VOICE_ROUTING_SELF_MATCH_OFFSCREEN

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"S64 mature-profile poisoning regression — got {decision.action!r} "
        f"from {decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p3_self_match_offscreen_mature.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_p3_self_match_with_face_holds_current():
    """Rule 12: self-match with co-witness OR above offscreen floor → hold.
    Standard happy-path — holder speaks again, face visible. Score 0.50
    is above SELF_MATCH_OFFSCREEN=0.45 so passes either branch.
    """
    claim, presence, session, case = _from_golden(
        "PR17_p3_self_match_with_face_holds_current"
    )

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"happy-path self-match must hold session, got {decision.action!r} "
        f"from {decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p3_self_match_with_face.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_p3_5_bootstrapping_stranger_holds_current():
    """S49 NEW-1: voice unmatched + cur_pid is bootstrapping stranger
    (< N_INITIAL_VOICE samples) → hold session. Without this, every
    early-stranger-session utterance fragments into a new stranger
    because thin profiles can't reliably self-match.
    """
    from core.config import N_INITIAL_VOICE

    claim, presence, session, case = _from_golden(
        "PR18_p3_5_bootstrapping_stranger_holds_current"
    )
    assert session.cur_holder_voice_n < N_INITIAL_VOICE

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"S49 NEW-1 regression — bootstrapping stranger session must hold, "
        f"got {decision.action!r} from {decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p3_5_bootstrapping_stranger_hold.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_p4_multi_segment_mismatch_drops_in_multi_known():
    """S118/S121: pyannote >= 2 segments + low score + multi-known room
    → drop. Cross-talk-between-knowns is the misattribution risk this
    guards. Solo (n_active=1) case lets rule 15 (live-bug fix) catch it
    instead — separate test covers that.
    """
    from core.config import VOICE_ROUTING_STRANGER_FLOOR

    claim, presence, session, case = _from_golden(
        "PR19_p4_multi_segment_mismatch_drops_in_multi_known"
    )
    assert claim.confidence < VOICE_ROUTING_STRANGER_FLOOR

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"S118/S121 regression — got {decision.action!r} from "
        f"{decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p4_multi_segment_mismatch.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_p4_new_stranger_below_threshold():
    """Rule 16: 0 < v_score < VOICE_RECOGNITION_THRESHOLD with cur_pid
    present → open new stranger session. Standard path for never-heard
    speakers entering an active session.
    """
    from core.config import VOICE_RECOGNITION_THRESHOLD

    claim, presence, session, case = _from_golden(
        "PR20_p4_new_stranger_below_threshold"
    )
    assert 0.0 < claim.confidence < VOICE_RECOGNITION_THRESHOLD

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"P4 normal-new-stranger path — got {decision.action!r} from "
        f"{decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p4_new_stranger_low_match.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_p4_single_segment_mismatch_drops_in_multi_known():
    """S120/S121: single-segment + low score + mature holder + multi-known.
    Stricter than rule 14 because single-segment with mature-holder mismatch
    in a multi-known room is the highest-confidence "this isn't anyone we
    know" signal.
    """
    from core.config import (
        VOICE_ACCUM_MATURE_SAMPLE_COUNT,
        VOICE_RECOGNITION_THRESHOLD,
        VOICE_ROUTING_MIN_AUDIO_FOR_SCORE,
        VOICE_ROUTING_STRANGER_FLOOR,
    )

    # Score must clear VOICE_RECOGNITION_THRESHOLD=0.25 (else rule 16 fires
    # first as new_stranger) AND stay below VOICE_ROUTING_STRANGER_FLOOR=0.30.
    # Narrow [0.25, 0.30) band by design — single-segment-mismatch is the
    # post-S121 carve-out for confident-non-match-of-mature-holder.
    claim, presence, session, case = _from_golden(
        "PR21_p4_single_segment_mismatch_drops_in_multi_known"
    )
    assert claim.confidence >= VOICE_RECOGNITION_THRESHOLD  # rule 16 won't fire
    assert claim.confidence < VOICE_ROUTING_STRANGER_FLOOR
    assert claim.utterance_duration >= VOICE_ROUTING_MIN_AUDIO_FOR_SCORE
    assert session.cur_holder_voice_n >= VOICE_ACCUM_MATURE_SAMPLE_COUNT

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"S120/S121 regression — got {decision.action!r} from "
        f"{decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p4_single_segment_mismatch.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_p4_voice_ambiguous_no_candidates_holds_current():
    """Rule 18: v_score==0 + scene has no other candidates → hold cur_pid.

    Most common ambient case: holder pauses, ambient noise, quiet syllable.
    Empty scene means no plausible alternative — trust the session.

    Rule 15 (live-bug) intercepts BEFORE this on multi-segment + n_active=1.
    Test forces n_diarize_segments=1 to skip rule 15.
    """
    claim, presence, session, case = _from_golden(
        "PR22_p4_voice_ambiguous_no_candidates_holds_current"
    )

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"P4 legacy fallback — empty room must hold current, got "
        f"{decision.action!r} from {decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p4_voice_ambiguous_no_candidates.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_p4_voice_ambiguous_with_candidates_returns_ambiguous():
    """Rule 19: v_score==0 + populated room → ambiguous.

    Other people are visible/heard; can't trust holding cur_pid when room
    genuinely has alternatives.
    """
    # Force scene_candidates > 0 via an unrecognized track (simpler than
    # adding non-cur visible_pids while keeping n_active_sessions=1)
    claim, presence, session, case = _from_golden(
        "PR23_p4_voice_ambiguous_with_candidates_returns_ambiguous"
    )

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"P4 populated-room must be ambiguous, got {decision.action!r} "
        f"from {decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p4_voice_ambiguous_with_candidates.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_p5_no_session_opens_stranger():
    """Rule 20: no session + voice signal OR unrecognized track → open
    fresh stranger session. First-entry path for ambient detection.
    """
    from core.config import VOICE_RECOGNITION_THRESHOLD

    claim, presence, session, case = _from_golden(
        "PR24_p5_no_session_opens_stranger"
    )
    assert 0.0 < claim.confidence < VOICE_RECOGNITION_THRESHOLD

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"P5 first-entry — got {decision.action!r} from {decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p5_no_session_new_stranger.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_last_resort_ambiguous_when_low_score_other_pid():
    """Q1 last-resort fallthrough: v_pid != cur_pid AND v_score below
    MIDRANGE_SWITCH_MIN AND cur_pid occupied → ambiguous (Q1 reviewer
    2026-04-28). ECAPA returned a name-match but score too weak for any
    P1/P2 rule, and cur_pid is occupied so P3/P4 don't apply. Without
    this rule, fallthrough would change return shape from `ambiguous` to
    `no_action` — a behavior change. Q1's exact reasoning string is pinned.
    """
    from core.config import VOICE_ROUTING_MIDRANGE_SWITCH_MIN

    # Q1's exact precondition: v_pid != cur_pid, v_score=0.10 (well below
    # MIDRANGE_SWITCH_MIN=0.30)
    claim, presence, session, case = _from_golden(
        "PR25_last_resort_ambiguous_when_low_score_other_pid"
    )
    assert claim.confidence < VOICE_ROUTING_MIDRANGE_SWITCH_MIN

    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"Q1 last-resort regression — got {decision.action!r} from "
        f"{decision.rule_fired!r}"
    )
    assert decision.rule_fired == _last_resort_ambiguous.__name__ == case.expected_rule_fired
    # Q1 reviewer 2026-04-28 pinned the exact reasoning string:
    assert decision.reasoning == case.expected_reasoning
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


# ══════════════════════════════════════════════════════════════════════════
# Cascade-walk integrity test — added at rule 22 per reviewer's
# 2026-04-29 closing recommendation. Confirms every rule body terminates
# correctly + only rule 21 fires on the empty-state input (i.e., no
# false-positive matches across the cascade).
# ══════════════════════════════════════════════════════════════════════════


def test_cascade_walks_all_22_rules_only_rule_21_matches_empty_state():
    """Walks every rule helper in _CASCADE against the no-signal /
    no-session / empty-scene state. Asserts:
      - Each rule terminates (returns either None or RoutingDecision)
      - 21 of 22 rules return None (don't false-positive on this state)
      - Only `_p5_no_session_no_action` matches and returns RoutingDecision

    This is the structural complement to per-rule tests: those verify
    each rule fires on its own positive case; this verifies they DON'T
    fire on the empty case. Catches future predicate regressions where
    an over-broad condition silently matches no-signal turns.
    """
    from core.voice_channel import IdentityClaim
    from core.vision_channel import PresenceState
    from core.reconciler_state import RoutingDecision, SessionState

    # NARROWED at Spec 1 D2 (2026-05-30): utterance_duration sub-MIN_AUDIO (was 1.5s).
    # The canonical "empty / nothing-to-do" turn that must match ONLY _p5_no_session_no_action
    # is now sub-0.5s — post-D2 a real-length (utt>=0.5) no_signal no-session turn legitimately
    # ALSO matches _p5_no_session_new_stranger (the Lexi fix), which is correct, not a
    # false-positive. Sub-0.5s keeps new_stranger's OR clauses all False so only no_action matches.
    claim = IdentityClaim(
        pid=None, confidence=0.0, n_diarize_segments=1,
        utterance_duration=0.3, reasoning="empty",
        confidence_is_no_signal=True,
    )
    presence = PresenceState(visible_pids=(), unrecognized_track_ids=())
    session = SessionState(
        cur_pid=None, cur_person_type="", n_active_sessions=0,
        voice_gallery_sizes={}, cur_holder_voice_n=0, now=0.0,
    )

    matches: dict[str, RoutingDecision] = {}
    for rule in _CASCADE:
        result = rule(claim, presence, session)
        assert result is None or isinstance(result, RoutingDecision), (
            f"{rule.__name__} returned {type(result).__name__!r} — "
            f"must be None or RoutingDecision"
        )
        if result is not None:
            matches[rule.__name__] = result

    assert set(matches.keys()) == {_p5_no_session_no_action.__name__}, (
        f"Empty-state input should match exactly one rule "
        f"(_p5_no_session_no_action). Got matches: {sorted(matches.keys())}. "
        f"Any other match indicates a predicate that's too broad."
    )
    assert matches[_p5_no_session_no_action.__name__].action == "no_action"


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


def test_b6_d1_stale_todo_marker_removed():
    """P0.B6 D1 source-inspection: the stale `TODO(#176): land 22 tests`
    marker comment must be gone from tests/test_reconciler.py.

    Skeptic1-2026-05-20 Attack 3 ("22 per-rule acceptance tests NOT landed")
    was based on this stale TODO comment. Phase 0 grep confirmed all 22 tests
    WERE landed; the TODO marker was documentation-vs-reality drift. D1 removes
    the marker; this test prevents regression to the stale-marker state.

    Assertion narrowed to the SPECIFIC stale marker phrase (`TODO(#176): land
    22 tests in lockstep with rule bodies`) so this test's own docstring and
    sibling test docstrings (which DO reference `TODO(#176)` as historical
    context) don't false-positive.
    """
    import inspect
    src = inspect.getsource(inspect.getmodule(test_b6_d1_stale_todo_marker_removed))
    # Stale-marker fingerprint: the original TODO comment's verbatim leading text.
    # Sibling docstrings may reference `TODO(#176)` for historical context — that's
    # intentional. The specific stale marker line is what D1 removed.
    # Self-reference dodge: assemble the forbidden marker from parts at runtime so
    # this test's own source bytes do NOT contain the literal forbidden string
    # (banked as Plan-v1-Pass-2-grep-undercount 3rd instance at P0.B6 closure —
    # the test's own literal was the missed surface in the original D1 anchor).
    _todo_tag = "TODO" + "(" + "#" + "176)"
    _stale_phrase = ": land 22 tests in lockstep with rule bodies"
    forbidden = _todo_tag + _stale_phrase
    assert forbidden not in src, (
        f"P0.B6 D1: stale TODO marker `{forbidden}` must be removed from "
        "tests/test_reconciler.py. The 22 enumerated tests landed 2026-04-29 "
        "onward; restoring the TODO would re-introduce the documentation drift "
        "that surfaced via skeptic1 Attack 3."
    )


def test_b6_d2_file_docstring_past_tense():
    """P0.B6 D2 source-inspection: the file's top-of-file docstring must
    narrate the work in past tense ("landed") with explicit P0.B6 closure
    reference + D4 tripwire mention.

    Pre-fix: docstring used past-future tense ("land in #176"), feeding the
    same drift class as the D1 stale TODO marker. Post-fix: past tense +
    explicit P0.B6 closure reference + D4 AST tripwire mention.
    """
    import inspect
    src = inspect.getsource(inspect.getmodule(test_b6_d2_file_docstring_past_tense))
    tree = ast.parse(src)
    module_doc = ast.get_docstring(tree) or ""

    # Past-tense markers per Plan v1 §2.2 verbatim "After" docstring text.
    assert "#176, landed" in module_doc, (
        "P0.B6 D2: docstring must use past-tense `#176, landed` "
        "(NOT past-future `(land in #176)` form which fed the original drift)"
    )
    assert "P0.B6 closure 2026-05-21" in module_doc, (
        "P0.B6 D2: docstring must reference the P0.B6 closure date explicitly"
    )
    assert "D4 AST forward-property tripwire" in module_doc, (
        "P0.B6 D2: docstring must mention the D4 AST tripwire so future readers "
        "see the structural-invariant maintenance contract"
    )
    # Defense-in-depth: the past-future tense form must NOT remain.
    assert "(land in #176" not in module_doc, (
        "P0.B6 D2: pre-fix past-future tense `(land in #176)` must be gone"
    )


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


# ══════════════════════════════════════════════════════════════════════════
# Spec 1 D1 — no_signal short utterance ABSTAINS from the P0 drop rules
# (canary 2026-05-30: empty voice gallery -> identify() returns no_signal every
#  turn -> the P0 short-utterance drop rules treated abstention as a mismatch
#  and dropped turns vision could route. Same shape as Session 119.)
# ══════════════════════════════════════════════════════════════════════════


def test_spec1_d1_no_signal_short_utterance_holds_current():
    """D1: a no_signal short_hard utterance (0.7s, empty gallery -> no_signal) with a
    holder ALONE must HOLD current, not drop. Pre-D1 the P0 hard-mismatch rule read the
    forced-0.0 no_signal score as a sub-floor mismatch and dropped (the 'Travel anywhere
    for free.' canary turn). Post-D1 it abstains -> _p4_voice_ambiguous_no_candidates."""
    claim, presence, session, case = _from_golden(
        "PR26_spec1_d1_no_signal_short_utterance_holds_current"
    )
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"D1: no_signal short utterance with holder alone must hold current, got "
        f"{decision.action!r} from {decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p4_voice_ambiguous_no_candidates.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_spec1_d1_no_signal_short_utterance_multi_candidate_returns_ambiguous():
    """D1 boundary: same no_signal short utterance but with a SECOND candidate in scene
    must return ambiguous (drop) - D1 did NOT over-relax. A genuinely-ambiguous
    multi-person short no_signal turn still drops, via _p4_voice_ambiguous_with_candidates."""
    # Force scene_candidates > 0 via an unrecognized track (a second candidate ->
    # scene genuinely ambiguous)
    claim, presence, session, case = _from_golden(
        "PR27_spec1_d1_no_signal_short_utterance_multi_candidate_returns_ambiguous"
    )
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"D1 boundary: no_signal short utterance with a second candidate must be "
        f"ambiguous, got {decision.action!r} from {decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p4_voice_ambiguous_with_candidates.__name__ == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid
