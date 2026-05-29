"""Routing reconciler — pure cascade of speaker-attribution rules.

Phase 3 of the Voice/Vision Independence refactor. This module replaces
`pipeline._resolve_actual_speaker`'s tangled if-elif chain with a flat,
ordered cascade of 22 named rule helpers. Each helper is a pure function
on `(IdentityClaim, PresenceState, SessionState)` returning either a
`RoutingDecision` (this rule matches; cascade stops) or `None` (try the
next rule).

Architectural rules (enforced by `test_reconciler_imports_no_pipeline`):
  - This module MUST NOT import from `pipeline`.
  - This module MUST NOT call `time.time()` (callers supply `session.now`).
  - Rule helpers are stateless and side-effect free; the cascade dispatcher
    is the only place that loops.

Cascade ordering (enforced by `test_cascade_ordering_*` tests):
  - Priority 0 (short-utterance) fires before all P1–P5.
  - Priority 1 (confident match) fires before P2 (mid-range).
  - Priority 4 inner ordering: multi_segment_mismatch < pyannote_vouched_stranger
    < voice_ambiguous_no_candidates. The middle-vs-third ordering IS the
    2026-04-29 live-bug fix; restoring the original ordering re-introduces
    the Lexi-via-ElevenLabs misattribution.
  - `_last_resort_ambiguous` is always `_CASCADE[-1]`.

Design reference: RECONCILER_DESIGN.md.
Mapping reference: DRAFT_RECONCILER_MAPPING.md (22-row cascade with
                   code-line citations to the legacy function).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import dataclasses
from typing import Optional

from core.config import (
    N_INITIAL_VOICE,
    VOICE_ACCUM_MATURE_SAMPLE_COUNT,
    VOICE_RECOGNITION_THRESHOLD,
    VOICE_ROUTING_FACE_ASSIST_MIN,
    VOICE_ROUTING_FACE_STALE_SECS,
    VOICE_ROUTING_MIDRANGE_SWITCH_MIN,
    VOICE_ROUTING_MIN_AUDIO_FOR_SCORE,
    VOICE_ROUTING_MIN_UTTERANCE_SECS,
    VOICE_ROUTING_NOISE_FLOOR_SECS,
    VOICE_ROUTING_SELF_MATCH_FLOOR,
    VOICE_ROUTING_SELF_MATCH_OFFSCREEN,
    VOICE_ROUTING_SHORT_UTT_AMBIGUOUS,
    VOICE_ROUTING_SHORT_UTT_FLOOR,
    VOICE_ROUTING_SHORT_UTT_MISMATCH_ENABLED,
    VOICE_ROUTING_SINGLE_SEGMENT_MISMATCH_ENABLED,
    VOICE_ROUTING_STRANGER_FLOOR,
    VOICE_SWITCH_THRESHOLD_MATURE,
    VOICE_SWITCH_THRESHOLD_THIN,
)
from core.reconciler_state import RoutingDecision, SessionState, VALID_ACTIONS
from core.voice_channel import IdentityClaim
from core.vision_channel import PresenceState


def _effective_switch_threshold(v_pid: Optional[str], gallery_sizes: dict) -> float:
    """Return the voice switch threshold adjusted for target profile maturity.

    Mature profile (>= N_INITIAL_VOICE samples): VOICE_SWITCH_THRESHOLD_MATURE.
    Thin profile (< N_INITIAL_VOICE): VOICE_SWITCH_THRESHOLD_THIN — higher bar
    because under-trained means have unstable cosine clusters and a new speaker
    can fluke a 0.40 match against a 2-sample profile.

    Moved here from pipeline.py:1125 in #176 (Phase 3): the function is
    routing logic, not voice identification, so its home is core/reconciler.py.
    Pipeline.py imports this for any remaining legacy call sites; Phase 5
    deletes those along with `_resolve_actual_speaker`.
    """
    if v_pid and gallery_sizes.get(v_pid, 0) >= N_INITIAL_VOICE:
        return VOICE_SWITCH_THRESHOLD_MATURE
    return VOICE_SWITCH_THRESHOLD_THIN


def _build_routing_inputs(
    *,
    v_pid: Optional[str],
    v_score: float,
    n_diarize_segments: int,
    utterance_duration: float,
    persons_in_frame: dict,
    unrecognized_tracks: dict,
    cur_pid: Optional[str],
    cur_person_type: str,
    n_active_sessions: int,
    voice_gallery_sizes: dict,
    now: float,
    voice_reasoning: str = "",
    voice_raw_segment_scores: tuple = (),
    v_score_is_no_signal: bool = False,
) -> tuple["IdentityClaim", "PresenceState", SessionState]:
    """Assemble (IdentityClaim, PresenceState, SessionState) from pipeline state.

    Pure function — reads only its arguments, never pipeline globals. Phase 3
    uses it for shadow comparison (build inputs once, dispatch through both
    legacy `_resolve_actual_speaker` and reconciler.reconcile() for divergence
    logging). Phase 4 reuses the same signature when the cutover flag flips.

    Filtering policy mirrors legacy `_face_in_frame` / `_count_scene_candidates`:
      - visible_pids: face-source entries with last_recognized_at within
                      VOICE_ROUTING_FACE_STALE_SECS (voice-only entries excluded;
                      Bug B from S64).
      - unrecognized_track_ids: tracks whose last-seen ts is within the same
                                window.
      - cur_holder_voice_n: derived from voice_gallery_sizes[cur_pid] when set.
    """
    claim = IdentityClaim(
        pid=v_pid,
        confidence=v_score,
        n_diarize_segments=n_diarize_segments,
        utterance_duration=utterance_duration,
        reasoning=voice_reasoning,
        raw_segment_scores=voice_raw_segment_scores,
        confidence_is_no_signal=v_score_is_no_signal,
    )

    visible_pids = tuple(
        pid for pid, info in persons_in_frame.items()
        if info.get("source") != "voice"
        and now - info.get("last_recognized_at", 0) < VOICE_ROUTING_FACE_STALE_SECS
    )
    unrec_track_ids = tuple(
        tid for tid, ts in unrecognized_tracks.items()
        if now - ts < VOICE_ROUTING_FACE_STALE_SECS
    )
    per_pid_confidence = {
        pid: float(info.get("conf", 0.0))
        for pid, info in persons_in_frame.items()
        if info.get("source") != "voice"
        and now - info.get("last_recognized_at", 0) < VOICE_ROUTING_FACE_STALE_SECS
    }
    presence = PresenceState(
        visible_pids=visible_pids,
        unrecognized_track_ids=unrec_track_ids,
        per_pid_confidence=per_pid_confidence,
        per_pid_quality={},  # not surfaced by legacy persons_in_frame; Q2: kept-not-used
        frame_ts=now,
        reasoning="",
    )

    session = SessionState(
        cur_pid=cur_pid,
        cur_person_type=cur_person_type,
        n_active_sessions=n_active_sessions,
        voice_gallery_sizes=dict(voice_gallery_sizes),  # defensive shallow copy
        cur_holder_voice_n=voice_gallery_sizes.get(cur_pid, 0) if cur_pid else 0,
        now=now,
    )

    return claim, presence, session


# ──────────────────────────────────────────────────────────────────────────
# Priority 0 — short-utterance handling (utt < MIN_UTTERANCE_SECS)
# ──────────────────────────────────────────────────────────────────────────


def _p0_short_utterance_hard_mismatch(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """S92 P3.23 Tier 1: hard mismatch on short utterance with sound voice signal.

    Audio cleared MIN_AUDIO_FOR_SCORE so v_score is meaningful, but utterance
    is still under MIN_UTTERANCE_SECS and score is well below SHORT_UTT_FLOOR
    vs holder. Drop turn rather than fragment; user repeats with longer audio.
    """
    if (claim.utterance_duration < VOICE_ROUTING_MIN_UTTERANCE_SECS
            and VOICE_ROUTING_SHORT_UTT_MISMATCH_ENABLED
            and session.cur_pid is not None
            and claim.utterance_duration >= VOICE_ROUTING_MIN_AUDIO_FOR_SCORE
            and claim.confidence < VOICE_ROUTING_SHORT_UTT_FLOOR):
        return RoutingDecision(
            pid=None,
            action="short_utterance_voice_mismatch",
            reasoning=(
                f"short utterance {claim.utterance_duration:.2f}s, score "
                f"{claim.confidence:.3f} < {VOICE_ROUTING_SHORT_UTT_FLOOR} "
                f"hard floor vs cur_pid={session.cur_pid!r}"
            ),
        )
    return None


_p0_short_utterance_hard_mismatch.LOWER_BOUND = VOICE_ROUTING_MIN_AUDIO_FOR_SCORE


def _p0_short_utterance_ambiguous_multi_session(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """S93 P3.23 Tier 2: ambiguous-zone drop in multi-session room.

    Same audio + utterance constraints as Tier 1 but with v_score in the
    [SHORT_UTT_FLOOR, SHORT_UTT_AMBIGUOUS) ambiguous zone. Only drops when
    n_active_sessions >= 2 (solo sessions trust the score regardless).
    """
    if (claim.utterance_duration < VOICE_ROUTING_MIN_UTTERANCE_SECS
            and VOICE_ROUTING_SHORT_UTT_MISMATCH_ENABLED
            and session.cur_pid is not None
            and claim.utterance_duration >= VOICE_ROUTING_MIN_AUDIO_FOR_SCORE
            and claim.confidence < VOICE_ROUTING_SHORT_UTT_AMBIGUOUS
            and session.n_active_sessions >= 2):
        return RoutingDecision(
            pid=None,
            action="short_utterance_voice_mismatch",
            reasoning=(
                f"short utterance {claim.utterance_duration:.2f}s, score "
                f"{claim.confidence:.3f} in ambiguous zone "
                f"[{VOICE_ROUTING_SHORT_UTT_FLOOR}, "
                f"{VOICE_ROUTING_SHORT_UTT_AMBIGUOUS}) with "
                f"{session.n_active_sessions} active sessions — drop to prevent "
                f"mis-attribution to cur_pid={session.cur_pid!r}"
            ),
        )
    return None


_p0_short_utterance_ambiguous_multi_session.LOWER_BOUND = VOICE_ROUTING_MIN_AUDIO_FOR_SCORE


def _p0_pure_noise_hold_current(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """Pure ECAPA noise floor: utterances below 0.3s hold current session.

    Below VOICE_ROUTING_NOISE_FLOOR_SECS (0.3s) the embedding window is too
    small to extract any meaningful signal — hold current as last resort.
    Above 0.3s the full cascade applies and the gallery is always scored
    (Phase 4 cutover, 2026-04-29: removes the old 1.0s blanket-hold floor
    so post-expiry voices are scored rather than silently mis-attributed).
    """
    if (claim.utterance_duration < VOICE_ROUTING_NOISE_FLOOR_SECS
            and session.cur_pid is not None):
        return RoutingDecision(
            pid=session.cur_pid,
            action="current",
            reasoning=(
                f"short utterance {claim.utterance_duration:.2f}s < "
                f"{VOICE_ROUTING_NOISE_FLOOR_SECS}s pure noise floor — hold session"
            ),
        )
    return None


_p0_pure_noise_hold_current.LOWER_BOUND = 0.0


def _p0_short_utterance_gap_hold_current(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """P0.10 Bug-W fix: hold current for utterance in the 0.3-0.5s gap band.

    Gap-fill rule covering the 0.3-0.5s utterance band where neither
    _p0_pure_noise_hold_current (< 0.3s) nor _p0_short_utterance_*_mismatch
    (>= 0.5s) fires.  Without this, Bug-W falls through every P0/P1/P2/P3
    rule and lands on _p4_new_stranger_low_match → phantom stranger.

    Same shape as legacy router's P0c catch-all (pipeline.py:1233) but
    narrowed to the actual coverage gap (not legacy's 1.0s blanket floor —
    existing P0 rules at >= 0.5s were designed correctly per Phase 4 cutover).
    """
    if (claim.utterance_duration >= VOICE_ROUTING_NOISE_FLOOR_SECS
            and claim.utterance_duration < VOICE_ROUTING_MIN_AUDIO_FOR_SCORE
            and session.cur_pid is not None):
        return RoutingDecision(
            pid=session.cur_pid,
            action="current",
            reasoning=(
                f"utterance {claim.utterance_duration:.2f}s in 0.3-0.5s gap band — "
                f"hold current session ({session.cur_pid}); audio too short for "
                f"voice-ID decision but above pure-noise floor"
            ),
        )
    return None


_p0_short_utterance_gap_hold_current.LOWER_BOUND = VOICE_ROUTING_NOISE_FLOOR_SECS


def _p0_short_utterance_no_session(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """Pure noise floor variant: sub-0.3s utterance with no active session.

    No cur_pid to hold and the embedding is too short to reliably seed a new
    profile. Drop the turn — the user naturally speaks again longer.
    Above 0.3s the cascade continues and P4 rules can open a session.
    """
    if (claim.utterance_duration < VOICE_ROUTING_NOISE_FLOOR_SECS
            and session.cur_pid is None):
        return RoutingDecision(
            pid=None,
            action="short_utterance_skip",
            reasoning=(
                f"short utterance {claim.utterance_duration:.2f}s < "
                f"{VOICE_ROUTING_NOISE_FLOOR_SECS}s pure noise floor, "
                f"no session to attach to — drop"
            ),
        )
    return None


_p0_short_utterance_no_session.LOWER_BOUND = 0.0


# ──────────────────────────────────────────────────────────────────────────
# Priority 1 — confident voice switch (v_score above effective threshold)
# ──────────────────────────────────────────────────────────────────────────


def _p1_confident_voice_switch(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """Confident voice match against a different enrolled person.

    Threshold is _effective_switch_threshold(v_pid, voice_gallery_sizes) —
    target's profile maturity calibrates the bar (thin profiles need higher
    confidence to switch into them). Voice gallery is ground truth for
    enrolled persons; no LLM confirmation needed.
    """
    if claim.pid is not None and claim.pid != session.cur_pid:
        threshold = _effective_switch_threshold(claim.pid, session.voice_gallery_sizes)
        if claim.confidence >= threshold:
            return RoutingDecision(
                pid=claim.pid,
                action="switch_enrolled",
                reasoning=(
                    f"confident voice match → {claim.pid!r} "
                    f"(score={claim.confidence:.3f} >= threshold={threshold:.3f})"
                ),
            )
    return None


# ──────────────────────────────────────────────────────────────────────────
# Priority 2 — mid-range different-person match
# ──────────────────────────────────────────────────────────────────────────


def _p2_midrange_face_assist_switches(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """Mid-range voice + face co-witness allows switch (S46 + S64 Bug O floor).

    v_score in [MIDRANGE_SWITCH_MIN, SWITCH_THRESHOLD) for a non-cur target
    AND that target is currently visible AND v_score >= FACE_ASSIST_MIN.
    Two-channel agreement licenses the switch where voice alone wouldn't.
    """
    if (claim.pid is not None
            and claim.pid != session.cur_pid
            and claim.confidence >= VOICE_ROUTING_MIDRANGE_SWITCH_MIN
            and claim.pid in presence.visible_pids
            and claim.confidence >= VOICE_ROUTING_FACE_ASSIST_MIN):
        return RoutingDecision(
            pid=claim.pid,
            action="switch_enrolled",
            reasoning=(
                f"face+voice agree → {claim.pid!r} "
                f"(score={claim.confidence:.3f} >= face-assist floor "
                f"{VOICE_ROUTING_FACE_ASSIST_MIN}, target visible)"
            ),
        )
    return None


def _p2_midrange_face_assist_below_floor(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """S64 Bug O: mid-range + face but voice below FACE_ASSIST_MIN → ambiguous.

    Visible face isn't necessarily the speaker (multi-person, phone audio).
    A 0.30 voice score with the face in frame is too weak to license switch
    even with co-witness. Returns ambiguous so caller drops/rejects the turn.
    """
    if (claim.pid is not None
            and claim.pid != session.cur_pid
            and claim.confidence >= VOICE_ROUTING_MIDRANGE_SWITCH_MIN
            and claim.pid in presence.visible_pids
            and claim.confidence < VOICE_ROUTING_FACE_ASSIST_MIN):
        return RoutingDecision(
            pid=None,
            action="ambiguous",
            reasoning=(
                f"weak voice {claim.confidence:.3f} for {claim.pid!r} despite "
                f"face in frame (below {VOICE_ROUTING_FACE_ASSIST_MIN} floor) "
                f"— S64 Bug O guard"
            ),
        )
    return None


def _p2_midrange_no_face_returns_ambiguous(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """Mid-range voice match but target NOT visible → ambiguous.

    Single-channel mid-range evidence isn't enough to switch sessions.
    Caller defers; if next utterance brings face in frame OR confident voice,
    rules #5/#6 will fire then.
    """
    if (claim.pid is not None
            and claim.pid != session.cur_pid
            and claim.confidence >= VOICE_ROUTING_MIDRANGE_SWITCH_MIN
            and claim.pid not in presence.visible_pids):
        return RoutingDecision(
            pid=None,
            action="ambiguous",
            reasoning=(
                f"mid-range score {claim.confidence:.3f} for {claim.pid!r} "
                f"not in frame — single-channel evidence insufficient"
            ),
        )
    return None


# ──────────────────────────────────────────────────────────────────────────
# Priority 3 — voice matches current session holder
# ──────────────────────────────────────────────────────────────────────────


def _p3_self_match_below_floor(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """S51 anti-poisoning: self-match below SELF_MATCH_FLOOR → ambiguous.

    cur_pid's own profile matched the utterance but at a score so low it's
    likely cross-talk or noise. Refusing to credit prevents a poisoned
    profile from drifting further on this match.
    """
    if (claim.pid is not None
            and claim.pid == session.cur_pid
            and claim.confidence < VOICE_ROUTING_SELF_MATCH_FLOOR):
        return RoutingDecision(
            pid=None,
            action="ambiguous",
            reasoning=(
                f"self-match {claim.confidence:.3f} below "
                f"{VOICE_ROUTING_SELF_MATCH_FLOOR} floor — S51 anti-poisoning"
            ),
        )
    return None


def _p3_self_match_thin_stranger_relaxed(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """S71 Bug W: thin-stranger holder skips offscreen poisoning floor.

    Bootstrapping stranger's own voice routinely scores 0.30–0.45 against
    the unstable mean — that's normal profile-warming, not a poisoning
    signal. Mature poisoning protection (rule #11) stays intact for grown
    profiles.
    """
    if (claim.pid is not None
            and claim.pid == session.cur_pid
            and claim.confidence >= VOICE_ROUTING_SELF_MATCH_FLOOR
            and claim.confidence < VOICE_ROUTING_SELF_MATCH_OFFSCREEN
            and session.cur_pid not in presence.visible_pids
            and session.cur_person_type == "stranger"
            and session.cur_holder_voice_n < N_INITIAL_VOICE):
        return RoutingDecision(
            pid=session.cur_pid,
            action="current",
            reasoning=(
                f"thin stranger {session.cur_holder_voice_n}/{N_INITIAL_VOICE} "
                f"samples — S71 Bug W relaxation, offscreen floor skipped "
                f"(score={claim.confidence:.3f})"
            ),
        )
    return None


def _p3_self_match_offscreen_mature(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """S64 poisoning protection: offscreen self-match for mature holder.

    cur_pid's profile is mature (>= MATURE_SAMPLE_COUNT), they're not in
    frame, and v_score is below SELF_MATCH_OFFSCREEN. Without this guard,
    a mid-range match from a different speaker would silently update
    cur_pid's gallery, poisoning the profile.
    """
    if (claim.pid is not None
            and claim.pid == session.cur_pid
            and claim.confidence >= VOICE_ROUTING_SELF_MATCH_FLOOR
            and claim.confidence < VOICE_ROUTING_SELF_MATCH_OFFSCREEN
            and session.cur_pid not in presence.visible_pids
            and not (session.cur_person_type == "stranger"
                     and session.cur_holder_voice_n < N_INITIAL_VOICE)):
        return RoutingDecision(
            pid=None,
            action="ambiguous",
            reasoning=(
                f"low self-match {claim.confidence:.3f} and holder not visible "
                f"— S64 mature-profile poisoning protection"
            ),
        )
    return None


def _p3_self_match_with_face(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """Self-match with co-witness OR above offscreen floor → hold session.

    Either cur_pid's face is in frame (two-channel agreement) OR voice
    score cleared SELF_MATCH_OFFSCREEN (single-channel high enough).
    Standard happy path for routine holder-speaks-again turns.
    """
    if (claim.pid is not None
            and claim.pid == session.cur_pid
            and claim.confidence >= VOICE_ROUTING_SELF_MATCH_FLOOR
            and (session.cur_pid in presence.visible_pids
                 or claim.confidence >= VOICE_ROUTING_SELF_MATCH_OFFSCREEN)):
        return RoutingDecision(
            pid=session.cur_pid,
            action="current",
            reasoning=(
                f"self-match {claim.confidence:.3f} confirmed "
                f"(face in frame OR score >= offscreen floor)"
            ),
        )
    return None


# ──────────────────────────────────────────────────────────────────────────
# Priority 3.5 — bootstrapping stranger holder, voice unmatched
# ──────────────────────────────────────────────────────────────────────────


def _p3_5_bootstrapping_stranger_hold(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """S49 NEW-1: voice unmatched + cur is bootstrapping stranger → hold.

    Stranger sessions with < N_INITIAL_VOICE samples expect their own voice
    to score poorly against the thin profile. Hold session so subsequent
    samples can mature the profile. Without this, every early-session
    utterance fragments into a new stranger.
    """
    if (claim.pid is None
            and session.cur_pid is not None
            and session.cur_person_type == "stranger"
            and session.cur_holder_voice_n < N_INITIAL_VOICE):
        return RoutingDecision(
            pid=session.cur_pid,
            action="current",
            reasoning=(
                f"stranger bootstrapping — {session.cur_holder_voice_n}/"
                f"{N_INITIAL_VOICE} voice samples; hold session to allow "
                f"profile maturity"
            ),
        )
    return None


# ──────────────────────────────────────────────────────────────────────────
# Priority 4 — voice unrecognized, active session exists
# ──────────────────────────────────────────────────────────────────────────
#
# ⚠ Inner ordering is load-bearing:
#   _p4_multi_segment_mismatch
#   _p4_pyannote_vouched_stranger     ← MUST fire before _p4_voice_ambiguous_no_candidates
#   _p4_new_stranger_low_match
#   _p4_single_segment_mismatch
#   _p4_voice_ambiguous_no_candidates
#   _p4_voice_ambiguous_with_candidates
# Reordering re-introduces the 2026-04-28 Lexi misattribution.


def _p4_multi_segment_mismatch(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """S118/S121: multi-segment + low score + multi-known room → drop.

    Pyannote heard >= 2 voices, none matched the gallery confidently, and
    multiple known persons are in active session. Could be background talk,
    an unenrolled visitor, or genuine cross-talk — all wrongly attributed
    if held. Drop and let the user repeat.
    """
    if (claim.pid is None
            and session.cur_pid is not None
            and claim.n_diarize_segments >= 2
            and claim.confidence < VOICE_ROUTING_STRANGER_FLOOR
            and session.n_active_sessions >= 2):
        return RoutingDecision(
            pid=None,
            action="multi_segment_voice_mismatch",
            reasoning=(
                f"pyannote={claim.n_diarize_segments} segments, max "
                f"v_score={claim.confidence:.3f} < "
                f"{VOICE_ROUTING_STRANGER_FLOOR} stranger floor with "
                f"{session.n_active_sessions} active sessions — likely "
                f"non-enrolled speaker; drop to prevent misattribution"
            ),
        )
    return None


def _p4_pyannote_vouched_stranger(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """2026-04-29 live-bug fix: pyannote vouches for a stranger in solo room.

    pid=None + confidence <= 0.0 + n_diarize_segments >= 2 + cur_pid is not None
    + n_active_sessions == 1. Pyannote witnessed multiple voices but ECAPA
    couldn't match (gallery doesn't contain the new speaker). Solo
    n_active_sessions distinguishes from rule _p4_multi_segment_mismatch's
    multi-known case.

    `confidence_is_no_signal or confidence < 0.0` (Pre-P1 Bundle 5 MF7 — was
    `confidence <= 0.0`): ECAPA cosine similarity between two very different
    speakers' L2-normalized embeddings is often NEGATIVE (anti-correlated
    vectors). voice.identify() returns the actual best cosine score even on
    gallery miss — it sets `confidence_is_no_signal=True` (score forced to 0.0)
    ONLY when the embedding computation itself failed or the gallery was empty.
    The `or confidence < 0.0` half catches the common negative-score case
    (e.g., Lexi at -0.05 vs Jagan's gallery) that a bare no-signal flag would
    miss; dropping it regresses to the degenerate state. The flag half replaces
    the old `== 0.0` exact-convention coupling.

    Reference reproduction: tests/fixtures/canary_2026-04-29_lexi_misattribution.md
    line 564. Without this rule, falls through to _p4_voice_ambiguous_no_candidates
    and misattributes the new speaker's turn to cur_pid.

    MUST FIRE BEFORE _p4_voice_ambiguous_no_candidates — that ordering IS the bug fix.
    """
    if (claim.pid is None
            and (claim.confidence_is_no_signal or claim.confidence < 0.0)
            and claim.n_diarize_segments >= 2
            and session.cur_pid is not None
            and session.n_active_sessions == 1):
        return RoutingDecision(
            pid=None,  # caller mints the new stranger pid
            action="new_stranger",
            reasoning=(
                f"pyannote witnessed {claim.n_diarize_segments} voices in solo "
                f"room (cur_pid={session.cur_pid!r}, n_active=1) but voice ID "
                f"found no enrolled match — open new stranger session"
            ),
        )
    return None


def _p4_new_stranger_low_match(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """Normal new-stranger entry: v_score < VOICE_RECOGNITION_THRESHOLD and heard something.

    Voice ID returned a score below the enrollment threshold. Covers two cases:
    - 0 < score < threshold: weak positive match (classic path)
    - score < 0: negative cosine similarity — ECAPA vectors are anti-correlated,
      meaning this is definitively NOT any enrolled speaker (even stronger signal
      than a weak positive). voice.identify() returns the actual cosine score on
      gallery miss; only returns exactly 0.0 when embedding computation failed
      (no signal at all). Negative scores belong here, not in the ambiguous rules.
    """
    if (claim.pid is None
            and session.cur_pid is not None
            and claim.confidence < VOICE_RECOGNITION_THRESHOLD
            and not claim.confidence_is_no_signal):
        return RoutingDecision(
            pid=None,
            action="new_stranger",
            reasoning=(
                f"new stranger — score {claim.confidence:.3f} < threshold "
                f"{VOICE_RECOGNITION_THRESHOLD}"
            ),
        )
    return None


def _p4_single_segment_mismatch(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """S120/S121: single-segment + low score + mature holder + multi-known.

    Stricter conditions than _p4_multi_segment_mismatch (n_segments == 1)
    because a single segment with low score against a mature holder in a
    multi-known room is the highest-confidence "this isn't anyone we know"
    signal we have. Gated on SINGLE_SEGMENT_MISMATCH_ENABLED for canary
    rollback.
    """
    if (claim.pid is None
            and session.cur_pid is not None
            and VOICE_ROUTING_SINGLE_SEGMENT_MISMATCH_ENABLED
            and claim.n_diarize_segments == 1
            and claim.confidence < VOICE_ROUTING_STRANGER_FLOOR
            and claim.utterance_duration >= VOICE_ROUTING_MIN_AUDIO_FOR_SCORE
            and session.cur_holder_voice_n >= VOICE_ACCUM_MATURE_SAMPLE_COUNT
            and session.n_active_sessions >= 2):
        return RoutingDecision(
            pid=None,
            action="single_segment_voice_mismatch",
            reasoning=(
                f"v_score={claim.confidence:.3f} < floor="
                f"{VOICE_ROUTING_STRANGER_FLOOR}, holder voice_n="
                f"{session.cur_holder_voice_n} mature, audio="
                f"{claim.utterance_duration:.2f}s — drop to prevent "
                f"misattribution"
            ),
        )
    return None


def _p4_voice_ambiguous_no_candidates(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """Legacy fallback: v_score==0 in empty room → hold current.

    Most common case: holder pauses, ambient noise, or a quiet syllable
    pyannote couldn't bin. Empty scene means no plausible alternative
    speaker, so trust the session over the noise.

    _p4_pyannote_vouched_stranger fires BEFORE this on multi-segment +
    n_active==1 cases, intercepting the live-bug class.
    """
    if (claim.pid is None
            and session.cur_pid is not None
            and claim.confidence_is_no_signal):
        scene_candidates = (
            sum(1 for p in presence.visible_pids if p != session.cur_pid)
            + len(presence.unrecognized_track_ids)
        )
        if scene_candidates == 0:
            return RoutingDecision(
                pid=session.cur_pid,
                action="current",
                reasoning="voice ambiguous, no other candidates in scene",
            )
    return None


def _p4_voice_ambiguous_with_candidates(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """v_score==0 in populated room → ambiguous.

    Other people are visible/heard; we can't trust holding cur_pid when
    the room genuinely has alternatives. Caller drops the turn.
    """
    if (claim.pid is None
            and session.cur_pid is not None
            and claim.confidence_is_no_signal):
        scene_candidates = (
            sum(1 for p in presence.visible_pids if p != session.cur_pid)
            + len(presence.unrecognized_track_ids)
        )
        if scene_candidates > 0:
            return RoutingDecision(
                pid=None,
                action="ambiguous",
                reasoning=(
                    f"voice ambiguous, {scene_candidates} other candidate(s) "
                    f"in scene"
                ),
            )
    return None


# ──────────────────────────────────────────────────────────────────────────
# Priority 5 — no active session
# ──────────────────────────────────────────────────────────────────────────


def _p5_no_session_new_stranger(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """No session + voice OR unrecognized track → open stranger.

    First entry path: either voice ID returned a low-but-nonzero match
    (some acoustic content) OR an unrecognized face track is active.
    Either signal is enough to seed a new stranger session.
    """
    if (claim.pid is None
            and session.cur_pid is None
            and (not claim.confidence_is_no_signal  # any real cosine signal (positive or negative)
                 or len(presence.unrecognized_track_ids) > 0)):
        return RoutingDecision(
            pid=None,
            action="new_stranger",
            reasoning=(
                f"ambient first entry — score={claim.confidence:.3f}, "
                f"unrec_tracks={len(presence.unrecognized_track_ids)}"
            ),
        )
    return None


def _p5_no_session_no_action(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """No session + nothing detectable → no action.

    Truly empty turn — nothing to attribute, nothing to open. Caller skips.
    """
    if (claim.pid is None
            and session.cur_pid is None
            and claim.confidence_is_no_signal
            and len(presence.unrecognized_track_ids) == 0):
        return RoutingDecision(
            pid=None,
            action="no_action",
            reasoning="no session, no voice signal, no unrecognized tracks",
        )
    return None


# ──────────────────────────────────────────────────────────────────────────
# Last-resort fallback (Q1: kept; LAST entry in cascade)
# ──────────────────────────────────────────────────────────────────────────


def _last_resort_ambiguous(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """Q1: low-score voice ID against unenrolled speaker (fallthrough catch).

    v_pid is not None AND v_pid != cur_pid AND v_score < MIDRANGE_SWITCH_MIN
    AND cur_pid is not None. ECAPA returned a name-match but score is too
    weak for P1 (_p1_*) or P2 (_p2_*), and cur_pid is occupied so P3/P4
    didn't apply. Without this rule, fallthrough returns no_action — a
    behavior change. Returns ambiguous to preserve caller dispatch.
    """
    if (claim.pid is not None
            and claim.pid != session.cur_pid
            and claim.confidence < VOICE_ROUTING_MIDRANGE_SWITCH_MIN
            and session.cur_pid is not None):
        return RoutingDecision(
            pid=None,
            action="ambiguous",
            reasoning="voice match below switch threshold, ambiguous attribution",
        )
    return None


# ──────────────────────────────────────────────────────────────────────────
# Cascade — ordering IS the audit trail.
# ──────────────────────────────────────────────────────────────────────────
#
# DO NOT REORDER without understanding which Sessions 60–122 fix each
# position encodes. Test `test_cascade_ordering_*` enforces the critical
# invariants.

_CASCADE = (
    _p0_pure_noise_hold_current,                  # band: utt < 0.3, requires cur_pid
    _p0_short_utterance_no_session,               # band: utt < 0.3, requires no cur_pid
    _p0_short_utterance_gap_hold_current,         # ★ P0.10 Bug-W: 0.3 ≤ utt < 0.5
    _p0_short_utterance_hard_mismatch,            # band: 0.5 ≤ utt < 1.0
    _p0_short_utterance_ambiguous_multi_session,  # band: 0.5 ≤ utt < 1.0
    _p1_confident_voice_switch,
    _p2_midrange_face_assist_switches,
    _p2_midrange_face_assist_below_floor,
    _p2_midrange_no_face_returns_ambiguous,
    _p3_self_match_below_floor,
    _p3_self_match_thin_stranger_relaxed,
    _p3_self_match_offscreen_mature,
    _p3_self_match_with_face,
    _p3_5_bootstrapping_stranger_hold,
    _p4_multi_segment_mismatch,
    _p4_pyannote_vouched_stranger,        # MUST stay before _p4_voice_ambiguous_no_candidates
    _p4_new_stranger_low_match,
    _p4_single_segment_mismatch,
    _p4_voice_ambiguous_no_candidates,
    _p4_voice_ambiguous_with_candidates,
    _p5_no_session_new_stranger,
    _p5_no_session_no_action,
    _last_resort_ambiguous,
)


def reconcile(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> RoutingDecision:
    """Run the cascade in order; return the first matching rule's decision.

    The dispatcher injects `rule_fired = matched_rule.__name__` so
    callers and tests get a single machine-readable rule identifier
    without each rule body having to set it manually (DRY + typo-proof).

    Falls through to a `no_action` decision if all 22 rules return None
    (degenerate state — `_last_resort_ambiguous` should normally catch
    cur_pid-occupied fallthroughs and `_p5_no_session_no_action` catches
    the empty-state case, so this final fallback only fires when both
    return None — currently impossible once #176 lands rule bodies, but
    kept here for correctness during the skeleton phase).
    """
    _final_decision: Optional[RoutingDecision] = None
    for rule in _CASCADE:
        decision = rule(claim, presence, session)
        if decision is not None:
            _final_decision = dataclasses.replace(decision, rule_fired=rule.__name__)
            break
    if _final_decision is None:
        _final_decision = RoutingDecision(
            pid=None,
            action="no_action",
            reasoning="no rule matched (degenerate state)",
            rule_fired="",
        )

    # P0.0.7 H5 — emit routing_decision event via safe_emit_sync.
    # utt_band tag (Block C of P0.10) drives replay reconstruction of the
    # gap-band watch. Single P0.4-annotated except lives in safe_emit_sync.
    _utt = float(claim.utterance_duration or 0.0)
    if _utt < VOICE_ROUTING_NOISE_FLOOR_SECS:
        _band = "noise"
    elif _utt < VOICE_ROUTING_MIN_AUDIO_FOR_SCORE:
        _band = "gap"
    elif _utt < VOICE_ROUTING_MIN_UTTERANCE_SECS:
        _band = "short_hard"
    else:
        _band = "normal"
    from core.event_log import safe_emit_sync, RoutingDecisionPayload
    safe_emit_sync(
        "routing_decision",
        RoutingDecisionPayload(decision=_final_decision, utt_band=_band),
        session_id=session.cur_pid,
    )
    return _final_decision


# ──────────────────────────────────────────────────────────────────────────
# Band → expected rule mapping (P0.10.1 F2 — moved here from pipeline.py)
# ──────────────────────────────────────────────────────────────────────────
#
# Co-located with the rules so the mapping evolves alongside the cascade.
# Consumed by the Reconciler-Shadow band-divergence trigger in pipeline.py:
#   if utt_band ∈ {gap, short_hard} and rule_fired not in EXPECTED_RULES_BY_BAND[band]:
#       emit divergence log
#
# Boundary semantics (short_hard): rules from the adjacent bands (gap and
# pure-noise) are accepted because utterance_duration measurements can
# round across MIN_AUDIO_FOR_SCORE (0.5s) or NOISE_FLOOR_SECS (0.3s) — a
# turn that nominally lands in short_hard might fire a gap-rule due to
# precision loss in the float comparison. Treating both as legitimate
# prevents false-positive divergence noise during the validation window.
#
# Structural invariant: every rule name in this mapping must exist in
# _CASCADE — guarded by `test_expected_rules_by_band_references_existing_rules`.

EXPECTED_RULES_BY_BAND: dict[str, tuple[str, ...]] = {
    "gap": ("_p0_short_utterance_gap_hold_current",),
    "short_hard": (
        "_p0_short_utterance_hard_mismatch",
        "_p0_short_utterance_ambiguous_multi_session",
        # Boundary cases — see comment above.
        "_p0_short_utterance_gap_hold_current",
        "_p0_pure_noise_hold_current",
    ),
}


__all__ = [
    "reconcile",
    "_CASCADE",
    "EXPECTED_RULES_BY_BAND",
    "VALID_ACTIONS",
    "_build_routing_inputs",
    "_effective_switch_threshold",
]
