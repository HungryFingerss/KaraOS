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

from core.config import (
    N_INITIAL_VOICE,
    VOICE_ACCUM_MATURE_SAMPLE_COUNT,
    VOICE_RECOGNITION_THRESHOLD,
    VOICE_ROUTING_FACE_ASSIST_MIN,
    VOICE_ROUTING_MIDRANGE_SWITCH_MIN,
    VOICE_ROUTING_MIN_AUDIO_FOR_SCORE,
    VOICE_ROUTING_NOISE_FLOOR_SECS,
    VOICE_ROUTING_SELF_MATCH_FLOOR,
    VOICE_ROUTING_SELF_MATCH_OFFSCREEN,
    VOICE_ROUTING_SHORT_UTT_AMBIGUOUS,
    VOICE_ROUTING_SHORT_UTT_FLOOR,
    VOICE_ROUTING_STRANGER_FLOOR,
    VOICE_SWITCH_THRESHOLD_MATURE,
    VOICE_SWITCH_THRESHOLD_THIN,
)
from core.reconciler import reconcile
from core.reconciler_state import SessionState, VALID_ACTIONS
from core.voice_channel import IdentityClaim
from core.vision_channel import PresenceState


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
    claim = _claim(confidence=0.10, utterance_duration=0.7)
    session = _session(cur_pid="jagan_001", cur_holder_voice_n=20)
    decision = reconcile(claim, _presence(), session)
    assert decision.action == "short_utterance_voice_mismatch"


def test_c2_ambiguous_zone_multi_session_drops():
    """C2 (P0b): utt in [0.5, 1.0) AND v_score in [FLOOR, AMBIGUOUS)
    AND n_active >= 2 → short_utterance_voice_mismatch."""
    claim = _claim(confidence=0.30, utterance_duration=0.7)
    session = _session(n_active_sessions=2)
    decision = reconcile(claim, _presence(), session)
    assert decision.action == "short_utterance_voice_mismatch"


def test_c4_short_utterance_no_session_skips():
    """C4 (P0d): utt < NOISE_FLOOR (0.3) AND cur_pid is None → short_utterance_skip."""
    claim = _claim(confidence=0.0, utterance_duration=0.2)
    session = _session(cur_pid=None, cur_person_type="", n_active_sessions=0,
                       voice_gallery_sizes={}, cur_holder_voice_n=0)
    decision = reconcile(claim, _presence(), session)
    assert decision.action == "short_utterance_skip"


def test_c5_confident_voice_switch_to_different_pid():
    """C5 (P1): v_pid != cur_pid AND v_score >= effective switch threshold
    → switch_enrolled (v_pid)."""
    claim = _claim(pid="lexi_002", confidence=0.85, utterance_duration=2.0)
    session = _session(
        cur_pid="jagan_001",
        voice_gallery_sizes={"jagan_001": 20, "lexi_002": N_INITIAL_VOICE},
    )
    decision = reconcile(claim, _presence(), session)
    assert decision.action == "switch_enrolled"
    assert decision.pid == "lexi_002"


def test_c6_face_voice_agree_switches():
    """C6 (P2a): mid-range v_score + claim.pid visible + v_score >= FACE_ASSIST_MIN
    → switch_enrolled."""
    claim = _claim(pid="lexi_002", confidence=VOICE_ROUTING_FACE_ASSIST_MIN + 0.01,
                   utterance_duration=2.0)
    session = _session(
        cur_pid="jagan_001",
        voice_gallery_sizes={"jagan_001": 20, "lexi_002": 20},
    )
    presence = _presence(visible_pids=("lexi_002",))
    decision = reconcile(claim, presence, session)
    assert decision.action == "switch_enrolled"
    assert decision.pid == "lexi_002"


def test_c7_face_but_weak_voice_returns_ambiguous():
    """C7 (P2b): mid-range v_score + face visible but v_score < FACE_ASSIST_MIN
    → ambiguous (S64 Bug O guard)."""
    claim = _claim(pid="lexi_002", confidence=0.35, utterance_duration=2.0)
    # 0.35 is between MIDRANGE_SWITCH_MIN (0.30) and FACE_ASSIST_MIN (0.42)
    session = _session(
        cur_pid="jagan_001",
        voice_gallery_sizes={"jagan_001": 20, "lexi_002": 20},
    )
    presence = _presence(visible_pids=("lexi_002",))
    decision = reconcile(claim, presence, session)
    assert decision.action == "ambiguous"


def test_c8_midrange_no_face_returns_ambiguous():
    """C8 (P2c): mid-range without face → ambiguous."""
    claim = _claim(pid="lexi_002", confidence=0.35, utterance_duration=2.0)
    session = _session(
        cur_pid="jagan_001",
        voice_gallery_sizes={"jagan_001": 20, "lexi_002": 20},
    )
    decision = reconcile(claim, _presence(), session)
    assert decision.action == "ambiguous"


def test_c9_self_match_below_floor_is_ambiguous():
    """C9 (P3a): v_pid == cur_pid AND v_score < SELF_MATCH_FLOOR (0.30)
    → ambiguous (S51 anti-poisoning)."""
    claim = _claim(pid="jagan_001", confidence=0.10, utterance_duration=2.0)
    session = _session(cur_pid="jagan_001")
    decision = reconcile(claim, _presence(), session)
    assert decision.action == "ambiguous"


def test_c10_thin_stranger_self_match_holds():
    """C10 (P3b): v_pid==cur_pid + offscreen + holder is thin stranger
    → current."""
    claim = _claim(pid="stranger_x", confidence=0.35, utterance_duration=2.0)
    # 0.35: above SELF_MATCH_FLOOR (0.30), below SELF_MATCH_OFFSCREEN (0.45)
    session = _session(
        cur_pid="stranger_x",
        cur_person_type="stranger",
        cur_holder_voice_n=3,  # below N_INITIAL_VOICE (5)
        voice_gallery_sizes={"stranger_x": 3},
    )
    # cur_pid NOT in visible_pids → offscreen
    decision = reconcile(claim, _presence(), session)
    assert decision.action == "current"
    assert decision.pid == "stranger_x"


def test_c11_offscreen_mature_self_match_is_ambiguous():
    """C11 (P3c): v_pid==cur_pid + offscreen + mature + v_score < OFFSCREEN
    → ambiguous (S64 poisoning protection)."""
    claim = _claim(pid="jagan_001", confidence=0.35, utterance_duration=2.0)
    session = _session(
        cur_pid="jagan_001",
        cur_person_type="known",
        cur_holder_voice_n=20,  # mature
    )
    decision = reconcile(claim, _presence(), session)
    assert decision.action == "ambiguous"


def test_c12_self_match_with_face_holds():
    """C12 (P3d): v_pid==cur_pid + (face visible OR v_score >= OFFSCREEN)
    → current."""
    claim = _claim(pid="jagan_001", confidence=0.80, utterance_duration=2.0)
    session = _session(cur_pid="jagan_001")
    presence = _presence(visible_pids=("jagan_001",))
    decision = reconcile(claim, presence, session)
    assert decision.action == "current"
    assert decision.pid == "jagan_001"


def test_c13_bootstrapping_stranger_holds_on_unmatched_voice():
    """C13 (P3.5): v_pid is None + holder is stranger + gallery < N_INITIAL_VOICE
    → current (S49 NEW-1)."""
    claim = _claim(pid=None, confidence=0.05, utterance_duration=2.0)
    session = _session(
        cur_pid="stranger_x",
        cur_person_type="stranger",
        cur_holder_voice_n=2,
        voice_gallery_sizes={"stranger_x": 2},
    )
    decision = reconcile(claim, _presence(), session)
    assert decision.action == "current"
    assert decision.pid == "stranger_x"


def test_c14_multi_segment_low_score_multi_session_drops():
    """C14 (P4a): n_diarize >= 2 + v_score < STRANGER_FLOOR + n_active >= 2
    → multi_segment_voice_mismatch (S118 / S121)."""
    claim = _claim(
        pid=None,
        confidence=0.10,
        utterance_duration=2.0,
        n_diarize_segments=2,
    )
    session = _session(n_active_sessions=2)
    decision = reconcile(claim, _presence(), session)
    assert decision.action == "multi_segment_voice_mismatch"


def test_c15_new_stranger_low_match_opens_stranger():
    """C15 (P4b): v_pid is None + 0 < v_score < VOICE_RECOGNITION_THRESHOLD
    → new_stranger.

    Note: gap rule fires for utt in [0.3, 0.5) with cur_pid set so we use
    utt = 2.0s (well above MIN_UTTERANCE_SECS) to deliberately exercise
    the P4 rule, not the new gap rule."""
    claim = _claim(
        pid=None,
        confidence=0.15,
        utterance_duration=2.0,
        n_diarize_segments=1,
    )
    session = _session()
    decision = reconcile(claim, _presence(), session)
    assert decision.action == "new_stranger"


def test_c16_single_segment_mature_low_score_drops():
    """C16 (P4c): n_diarize==1 + v_score < STRANGER_FLOOR + mature holder
    + audio >= 0.5 + n_active >= 2 → single_segment_voice_mismatch.

    Uses confidence=0.27 to land in [VOICE_RECOGNITION_THRESHOLD=0.25,
    STRANGER_FLOOR=0.30) — outside _p4_new_stranger_low_match's
    `confidence < 0.25` range so the cascade reaches P4c. For
    confidence in (0.0, 0.25) the new-stranger rule wins (audited
    behavior preserved from legacy P4b/P4c ordering)."""
    claim = _claim(
        pid=None,
        confidence=0.27,
        utterance_duration=2.0,
        n_diarize_segments=1,
    )
    session = _session(
        n_active_sessions=2,
        cur_holder_voice_n=VOICE_ACCUM_MATURE_SAMPLE_COUNT,
    )
    decision = reconcile(claim, _presence(), session)
    assert decision.action == "single_segment_voice_mismatch"


def test_c17_voice_ambiguous_no_candidates_holds():
    """C17 (P4d): v_pid is None + v_score == 0 + no scene candidates
    → current."""
    claim = _claim(pid=None, confidence=0.0, utterance_duration=2.0,
                   n_diarize_segments=1, is_no_signal=True)
    session = _session()
    decision = reconcile(claim, _presence(), session)
    assert decision.action == "current"
    assert decision.pid == "jagan_001"


def test_c18_voice_ambiguous_with_candidates_is_ambiguous():
    """C18 (P4e): v_pid is None + v_score == 0 + scene_candidates >= 1
    → ambiguous."""
    claim = _claim(pid=None, confidence=0.0, utterance_duration=2.0,
                   n_diarize_segments=1, is_no_signal=True)
    session = _session()
    presence = _presence(visible_pids=("other_002",))
    decision = reconcile(claim, presence, session)
    assert decision.action == "ambiguous"


def test_c19_no_session_low_score_opens_stranger():
    """C19 (P5a): cur_pid is None + 0 < v_score < threshold OR unrec track
    → new_stranger."""
    claim = _claim(pid=None, confidence=0.10, utterance_duration=2.0,
                   n_diarize_segments=1)
    session = _session(cur_pid=None, cur_person_type="", n_active_sessions=0,
                       voice_gallery_sizes={}, cur_holder_voice_n=0)
    decision = reconcile(claim, _presence(), session)
    assert decision.action == "new_stranger"


def test_c20_no_session_no_signal_returns_no_action():
    """C20 (P5b): cur_pid is None + v_score == 0 + no unrec tracks
    → no_action."""
    claim = _claim(pid=None, confidence=0.0, utterance_duration=2.0,
                   n_diarize_segments=1, is_no_signal=True)
    session = _session(cur_pid=None, cur_person_type="", n_active_sessions=0,
                       voice_gallery_sizes={}, cur_holder_voice_n=0)
    decision = reconcile(claim, _presence(), session)
    assert decision.action == "no_action"


def test_c21_last_resort_ambiguous_catches_fallthrough():
    """C21: low-score voice ID against an unenrolled-direction pid
    when cur_pid is occupied → ambiguous (the last-resort rule).
    """
    claim = _claim(
        pid="other_pid",
        confidence=0.15,  # below MIDRANGE_SWITCH_MIN (0.30) — no P1/P2 fire
        utterance_duration=2.0,
        n_diarize_segments=1,
    )
    session = _session(
        cur_pid="jagan_001",
        voice_gallery_sizes={"jagan_001": 20, "other_pid": 5},
    )
    decision = reconcile(claim, _presence(), session)
    assert decision.action == "ambiguous"


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
