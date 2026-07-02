"""P0.10 reconciler contract — C1-C21 positive + N2-N6 negative.

Phase 1 deliverable per Plan v2 Step 5. C3 (Bug-W) and N1 (the same
forbidden behavior) live in tests/test_p10_routing_invariants.py since
they double as the auditor's R3 acceptance criterion.

N7 (no rule fired → hold current + WARN log) lives in Phase 2 Step 9
when the production fail-safe is added at pipeline.py:7417-7419.

Cross-references the audit at tests/p0_10_routing_audit.md deliverable 5.
Each test names its contract id + source branch in the legacy router.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import pytest

from core.reconciler import (
    reconcile,
    _p4_new_stranger_low_match,
    _p4_pyannote_vouched_stranger,
    _p5_no_session_new_stranger,
)
from core.reconciler_state import SessionState, VALID_ACTIONS
from core.voice_channel import IdentityClaim
from core.vision_channel import PresenceState

from tests.reconciler_golden import RECONCILER_GOLDEN_CASES, UNCHECKED

# PI-3 single source (2b): the contract C-cases now DERIVE their inputs + expected
# outcomes from the golden list rather than duplicating them inline. Each test keeps
# its name + docstring + assertion set; only the body changes to read from golden.
_GOLDEN = {c.case_id: c for c in RECONCILER_GOLDEN_CASES}


def _from_golden(case_id):
    """Build (claim, presence, session, case) for a golden case_id (2b derive)."""
    case = _GOLDEN[case_id]
    return (
        IdentityClaim(**case.claim),
        PresenceState(**case.presence),
        SessionState(**case.session),
        case,
    )


def _claim(
    pid=None,
    confidence=0.0,
    utterance_duration=1.5,
    n_diarize_segments=1,
    is_no_signal=False,
):
    return IdentityClaim(
        pid=pid,
        confidence=confidence,
        n_diarize_segments=n_diarize_segments,
        utterance_duration=utterance_duration,
        reasoning="",
        confidence_is_no_signal=is_no_signal,
    )


def _presence(
    visible_pids=(),
    unrecognized_track_ids=(),
):
    return PresenceState(
        visible_pids=visible_pids,
        unrecognized_track_ids=unrecognized_track_ids,
    )


def _session(
    cur_pid="jagan_001",
    cur_person_type="known",
    n_active_sessions=1,
    voice_gallery_sizes=None,
    cur_holder_voice_n=20,
):
    if voice_gallery_sizes is None:
        voice_gallery_sizes = {cur_pid: cur_holder_voice_n} if cur_pid else {}
    return SessionState(
        cur_pid=cur_pid,
        cur_person_type=cur_person_type,
        n_active_sessions=n_active_sessions,
        voice_gallery_sizes=voice_gallery_sizes,
        cur_holder_voice_n=cur_holder_voice_n,
        now=1000.0,
    )


# ══════════════════════════════════════════════════════════════════════════
# Positive contract — C1-C21 (C3 lives in test_p10_routing_invariants.py)
# ══════════════════════════════════════════════════════════════════════════


def test_c1_hard_mismatch_short_utterance_with_low_score_drops():
    """C1 (P0a): utt in [0.5, 1.0) AND v_score < SHORT_UTT_FLOOR (0.20)
    AND cur_pid set → short_utterance_voice_mismatch."""
    claim, presence, session, case = _from_golden("C1")
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_c2_ambiguous_zone_multi_session_drops():
    """C2 (P0b): utt in [0.5, 1.0) AND v_score in [FLOOR, AMBIGUOUS)
    AND n_active >= 2 → short_utterance_voice_mismatch."""
    claim, presence, session, case = _from_golden("C2")
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_c4_short_utterance_no_session_skips():
    """C4 (P0d): utt < NOISE_FLOOR (0.3) AND cur_pid is None → short_utterance_skip."""
    claim, presence, session, case = _from_golden("C4")
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_c5_confident_voice_switch_to_different_pid():
    """C5 (P1): v_pid != cur_pid AND v_score >= effective switch threshold
    → switch_enrolled (v_pid)."""
    claim, presence, session, case = _from_golden("C5")
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_c6_face_voice_agree_switches():
    """C6 (P2a): mid-range v_score + claim.pid visible + v_score >= FACE_ASSIST_MIN
    → switch_enrolled."""
    claim, presence, session, case = _from_golden("C6")
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_c7_face_but_weak_voice_returns_ambiguous():
    """C7 (P2b): mid-range v_score + face visible but v_score < FACE_ASSIST_MIN
    → ambiguous (S64 Bug O guard)."""
    claim, presence, session, case = _from_golden("C7")
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_c8_midrange_no_face_returns_ambiguous():
    """C8 (P2c): mid-range without face → ambiguous."""
    claim, presence, session, case = _from_golden("C8")
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_c9_self_match_below_floor_is_ambiguous():
    """C9 (P3a): v_pid == cur_pid AND v_score < SELF_MATCH_FLOOR (0.30)
    → ambiguous (S51 anti-poisoning)."""
    claim, presence, session, case = _from_golden("C9")
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_c10_thin_stranger_self_match_holds():
    """C10 (P3b): v_pid==cur_pid + offscreen + holder is thin stranger
    → current."""
    claim, presence, session, case = _from_golden("C10")
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_c11_offscreen_mature_self_match_is_ambiguous():
    """C11 (P3c): v_pid==cur_pid + offscreen + mature + v_score < OFFSCREEN
    → ambiguous (S64 poisoning protection)."""
    claim, presence, session, case = _from_golden("C11")
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_c12_self_match_with_face_holds():
    """C12 (P3d): v_pid==cur_pid + (face visible OR v_score >= OFFSCREEN)
    → current."""
    claim, presence, session, case = _from_golden("C12")
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_c13_bootstrapping_stranger_holds_on_unmatched_voice():
    """C13 (P3.5): v_pid is None + holder is stranger + gallery < N_INITIAL_VOICE
    → current (S49 NEW-1)."""
    claim, presence, session, case = _from_golden("C13")
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_c14_multi_segment_low_score_multi_session_drops():
    """C14 (P4a): n_diarize >= 2 + v_score < STRANGER_FLOOR + n_active >= 2
    → multi_segment_voice_mismatch (S118 / S121)."""
    claim, presence, session, case = _from_golden("C14")
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_c15_new_stranger_low_match_opens_stranger():
    """C15 (P4b): v_pid is None + 0 < v_score < VOICE_RECOGNITION_THRESHOLD
    → new_stranger.

    Note: gap rule fires for utt in [0.3, 0.5) with cur_pid set so we use
    utt = 2.0s (well above MIN_UTTERANCE_SECS) to deliberately exercise
    the P4 rule, not the new gap rule."""
    claim, presence, session, case = _from_golden("C15")
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_c16_single_segment_mature_low_score_drops():
    """C16 (P4c): n_diarize==1 + v_score < STRANGER_FLOOR + mature holder
    + audio >= 0.5 + n_active >= 2 → single_segment_voice_mismatch.

    Uses confidence=0.27 to land in [VOICE_RECOGNITION_THRESHOLD=0.25,
    STRANGER_FLOOR=0.30) — outside _p4_new_stranger_low_match's
    `confidence < 0.25` range so the cascade reaches P4c. For
    confidence in (0.0, 0.25) the new-stranger rule wins (audited
    behavior preserved from legacy P4b/P4c ordering)."""
    claim, presence, session, case = _from_golden("C16")
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_c17_voice_ambiguous_no_candidates_holds():
    """C17 (P4d): v_pid is None + v_score == 0 + no scene candidates
    → current."""
    claim, presence, session, case = _from_golden("C17")
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_c18_voice_ambiguous_with_candidates_is_ambiguous():
    """C18 (P4e): v_pid is None + v_score == 0 + scene_candidates >= 1
    → ambiguous."""
    claim, presence, session, case = _from_golden("C18")
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_c19_no_session_low_score_opens_stranger():
    """C19 (P5a): cur_pid is None + 0 < v_score < threshold OR unrec track
    → new_stranger."""
    claim, presence, session, case = _from_golden("C19")
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_c20_no_session_no_signal_returns_no_action():
    """C20 (P5b): cur_pid is None + no_signal + no unrec tracks + SUB-MIN_AUDIO
    utterance → no_action.

    NARROWED at Spec 1 D2 (2026-05-30): the utterance is now sub-0.5s (was 2.0s).
    A real-length no_signal utterance now opens a stranger via D2 — see c20b. A
    sub-0.5s no_signal utterance with no unrec tracks still correctly falls to
    _p5_no_session_no_action (new_stranger's three OR clauses all fail: no_signal,
    no unrec, utt 0.3 < 0.5)."""
    claim, presence, session, case = _from_golden("C20")
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_c20b_no_session_no_signal_real_length_opens_stranger():
    """Spec 1 D2 (the Lexi fix): cur_pid is None + no_signal (empty gallery) + a
    REAL-LENGTH utterance (>= MIN_AUDIO_FOR_SCORE 0.5s) → new_stranger.

    Deliberately reverses the pre-D2 C20 behavior: a 1.6s utterance from a speaker
    whose voice can't be matched (empty gallery → no_signal) now opens a GATED
    stranger session instead of dropping every turn. The session opens gated, so
    safety is unchanged; the speaker can finally be heard."""
    claim, presence, session, case = _from_golden("C20b")
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_c21_last_resort_ambiguous_catches_fallthrough():
    """C21: low-score voice ID against an unenrolled-direction pid
    when cur_pid is occupied → ambiguous (the last-resort rule).
    """
    claim, presence, session, case = _from_golden("C21")
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


# ══════════════════════════════════════════════════════════════════════════
# Negative contract — N2-N6 (N1 = Bug-W lives in routing_invariants.py)
# ══════════════════════════════════════════════════════════════════════════


def test_n2_gap_band_never_opens_stranger_in_session():
    """N2: across the entire 0.3-1.0s utterance band with cur_pid set,
    the cascade MUST NEVER return `new_stranger` when claim.pid is None
    and the rest of the Bug-W shape holds.

    Sweeps the band at multiple confidence + n_diarize combinations
    that previously fell through to _p4_new_stranger_low_match. The
    gap rule + the existing P0a/P0b protect this. If any combo opens
    a stranger, P0.10 cannot ship.
    """
    forbidden = "new_stranger"
    for utt in (0.30, 0.35, 0.45, 0.49, 0.6, 0.85):
        for conf in (0.0, 0.021, 0.15, 0.22):
            for n_seg in (0, 1):
                claim = _claim(
                    pid=None, confidence=conf,
                    utterance_duration=utt, n_diarize_segments=n_seg,
                )
                session = _session(
                    cur_pid="jagan_001",
                    cur_person_type="best_friend",
                    cur_holder_voice_n=20,
                    n_active_sessions=2,
                )
                decision = reconcile(claim, _presence(), session)
                assert decision.action != forbidden, (
                    f"N2 violation: utt={utt} conf={conf} n_seg={n_seg} "
                    f"→ action={decision.action!r} rule={decision.rule_fired!r}; "
                    "the 0.3-1.0s band with cur_pid set must not "
                    "open a stranger."
                )


def test_n3_confident_voice_switch_never_attributed_to_cur():
    """N3: if v_pid != cur_pid AND v_score >= effective switch threshold,
    the decision MUST switch (or at minimum NOT return 'current' bound
    to cur_pid). Silently mis-attributing the switched-in speaker's
    words to the previous holder is the contrapositive of C5.
    """
    claim = _claim(pid="lexi_002", confidence=0.95, utterance_duration=2.0)
    session = _session(
        cur_pid="jagan_001",
        voice_gallery_sizes={"jagan_001": 20, "lexi_002": 20},
    )
    decision = reconcile(claim, _presence(), session)
    assert not (decision.action == "current" and decision.pid == "jagan_001"), (
        f"N3 violation: confident switch attributed to cur_pid: {decision}"
    )


def test_n4_multi_segment_low_score_never_opens_stranger():
    """N4: n_diarize >= 2 + v_score < STRANGER_FLOOR + n_active >= 2
    must NEVER return new_stranger (would be cross-talk-between-knowns
    falsely promoted to a fresh stranger session)."""
    claim = _claim(
        pid=None, confidence=0.10, utterance_duration=2.0,
        n_diarize_segments=2,
    )
    session = _session(n_active_sessions=2)
    decision = reconcile(claim, _presence(), session)
    assert decision.action != "new_stranger", (
        f"N4 violation: multi-segment low-score multi-known room "
        f"opened a stranger: {decision}"
    )


# ── N4b (#128) — the pid-BEARING sibling of N2/N4 ───────────────────────────────
#
# N2 (gap-band sweep) + N4 (multi-segment) cover the pid=None axis: an UNIDENTIFIED
# claim must not over-open a stranger. N4b is the Canary #4 Q3 complement on the
# pid-BEARING axis: an IDENTIFIED claim (claim.pid set) must NEVER route to
# new_stranger, so a known speaker's turn can't be mis-created as a phantom stranger
# session (the Canary #3/#4 regression family). Runtime defense-in-depth complement to
# D1's structural tripwire (test_p10_routing_invariants.py): D1 checks the
# `claim.pid is None` guard is PRESENT; N4b checks it is EFFECTIVE (backstops the
# present-but-ineffective case D1 can't see — see #128 §2 caveat 3).


@pytest.mark.parametrize("rule_fn, case_id", [
    # _p4_pyannote_vouched_stranger: no_signal + 2 segments + cur_pid set + solo room
    (_p4_pyannote_vouched_stranger, "N4B_pyannote_vouched_pid_bearing_veto"),
    # _p4_new_stranger_low_match: low score below threshold + cur_pid set + real signal
    (_p4_new_stranger_low_match, "N4B_new_stranger_low_match_pid_bearing_veto"),
    # _p5_no_session_new_stranger: no session + real cosine signal
    (_p5_no_session_new_stranger, "N4B_no_session_new_stranger_pid_bearing_veto"),
], ids=["pyannote_vouched", "new_stranger_low_match", "no_session_new_stranger"])
def test_n4b_pid_bearing_claim_vetoed_by_each_new_stranger_rule(rule_fn, case_id):
    """N4b per-rule (#128 D2; golden-flattened 2026-07-02) — each golden row carries
    inputs that WOULD fire its new_stranger-emitting rule if pid were None (the rule's
    other conditions satisfied), with claim.pid set to an identified speaker. Two
    assertions: (1) the rule returns None — isolates the `claim.pid is None` guard's
    veto; (2) the cascade returns the row's PINNED vetoed-path action — strictly
    stronger than `action != "new_stranger"`: a veto regression surfaces as the
    action changing, not just as not-stranger. Pid-bearing sibling of N2/N4 (which
    cover the pid=None axis)."""
    claim, presence, session, case = _from_golden(case_id)
    assert rule_fn(claim, presence, session) is None, (
        f"N4b violation: {rule_fn.__name__} did NOT veto a pid-bearing claim "
        f"(pid='lexi_002') — the `claim.pid is None` guard is ineffective, so an "
        f"identified speaker could be mis-opened as a phantom stranger."
    )
    decision = reconcile(claim, presence, session)
    assert decision.action == case.expected_action, (
        f"N4b vetoed-path drift: cascade returned {decision.action!r} "
        f"(rule={decision.rule_fired!r}); golden pins {case.expected_action!r}."
    )
    if case.expected_rule_fired is not UNCHECKED:
        assert decision.rule_fired == case.expected_rule_fired
    if case.expected_pid is not UNCHECKED:
        assert decision.pid == case.expected_pid


def test_n4b_reconcile_never_opens_stranger_for_pid_bearing_claim():
    """N4b reconcile-level sweep (#128 D2) — the N2 sweep mirrored on the pid-BEARING axis:
    across confidence / segment / no-signal / session conditions, an IDENTIFIED claim
    (claim.pid set) NEVER routes to new_stranger at reconcile() level. The Q3 invariant
    end-to-end — a known speaker's turn cannot become a phantom stranger session."""
    for utt in (0.45, 0.6, 1.5, 2.0):
        for conf in (-0.2, 0.0, 0.10, 0.27, 0.95):
            for n_seg in (0, 1, 2):
                for no_sig in (False, True):
                    for cur in ("jagan_001", None):
                        claim = _claim(
                            pid="lexi_002", confidence=conf,
                            utterance_duration=utt, n_diarize_segments=n_seg,
                            is_no_signal=no_sig,
                        )
                        session = _session(
                            cur_pid=cur,
                            cur_person_type="best_friend" if cur else "",
                            n_active_sessions=2 if cur else 0,
                            cur_holder_voice_n=20 if cur else 0,
                        )
                        decision = reconcile(claim, _presence(), session)
                        assert decision.action != "new_stranger", (
                            f"N4b violation: pid-bearing claim (pid='lexi_002') routed to "
                            f"new_stranger — utt={utt} conf={conf} n_seg={n_seg} "
                            f"no_sig={no_sig} cur_pid={cur!r} → rule={decision.rule_fired!r}"
                        )


def test_n5_single_segment_mismatch_does_not_drop_bootstrapping_holder():
    """N5: drop on n_diarize==1 + low score must NOT fire when holder
    is bootstrapping (immature gallery). Drop is only safe for mature
    holders — bootstrapping strangers expect their own voice to score
    poorly against the thin profile.
    """
    claim = _claim(
        pid=None, confidence=0.10, utterance_duration=2.0,
        n_diarize_segments=1,
    )
    session = _session(
        cur_pid="stranger_x",
        cur_person_type="stranger",
        cur_holder_voice_n=2,  # bootstrapping (< MATURE)
        voice_gallery_sizes={"stranger_x": 2},
        n_active_sessions=2,
    )
    decision = reconcile(claim, _presence(), session)
    assert decision.action != "single_segment_voice_mismatch", (
        f"N5 violation: dropped a bootstrapping holder's turn: {decision}"
    )


def test_n6_reconciler_never_invents_pids():
    """N6: every decision pid is either None, cur_pid, or claim.pid
    (the voice channel's match). The reconciler must NEVER fabricate
    a person_id.

    Sweeps several decision-producing shapes and validates the pid
    contract by enumeration."""
    cur_pid = "jagan_001"
    voice_pid = "lexi_002"
    valid_pids = {None, cur_pid, voice_pid}

    scenarios = [
        # (claim, presence, session, label)
        (
            _claim(pid=voice_pid, confidence=0.95, utterance_duration=2.0),
            _presence(),
            _session(cur_pid=cur_pid, voice_gallery_sizes={cur_pid: 20, voice_pid: 20}),
            "P1 confident switch",
        ),
        (
            _claim(pid=None, confidence=0.0, utterance_duration=2.0),
            _presence(),
            _session(cur_pid=cur_pid),
            "P4d ambiguous-no-candidates hold",
        ),
        (
            _claim(pid=None, confidence=0.021, utterance_duration=0.45),
            _presence(),
            _session(cur_pid=cur_pid),
            "P0.10 gap rule hold",
        ),
        (
            _claim(pid=None, confidence=0.10, utterance_duration=2.0),
            _presence(),
            _session(
                cur_pid=None, cur_person_type="", n_active_sessions=0,
                voice_gallery_sizes={}, cur_holder_voice_n=0,
            ),
            "P5a no-session new stranger",
        ),
    ]
    for claim, presence, session, label in scenarios:
        decision = reconcile(claim, presence, session)
        assert decision.pid in valid_pids, (
            f"N6 violation in {label}: reconciler invented pid "
            f"{decision.pid!r}. Valid: {valid_pids}"
        )
        assert decision.action in VALID_ACTIONS, (
            f"N6 violation in {label}: action {decision.action!r} not in "
            f"VALID_ACTIONS"
        )
