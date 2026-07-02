"""Golden source for reconciler routing tests — single list of 51 cases.

2a deliverable. ``RECONCILER_GOLDEN_CASES`` is the single source of truth for
both the contract tests (``test_p10_reconciler_contract.py``, C1-C21) and the
per-rule acceptance tests (``test_reconciler.py``, the 27 ``reconcile``-calling
rule tests) once 2b re-points them to derive from here.

Each case stores plain *dict* payloads (NOT constructed dataclasses) so this
module imports nothing beyond ``core.config`` at load time. The channel/state
dataclasses (``IdentityClaim`` / ``PresenceState`` / ``SessionState``) are
constructed in the bench driver (``compute_attribution_accuracy``) via
``IdentityClaim(**case.claim)`` etc. — channel imports are allowed there, never
here at golden-module load.

- 21 cases transcribed verbatim from ``test_p10_reconciler_contract.py`` (C1-C21).
- 27 cases transcribed verbatim from the per-rule ``reconcile``-calling tests in
  ``test_reconciler.py``.
- 3 N4b vetoed-path rows (one per new_stranger emitter, pid-bearing inputs;
  ``expected_action`` pins the action the cascade ACTUALLY returns when the
  ``claim.pid is None`` guard vetoes — strictly stronger than asserting
  ``!= "new_stranger"``. Flattened per architect ruling 2026-07-02; the
  reconcile-level N4b sweep in ``test_p10_reconciler_contract.py`` stays as an
  invariant on top).
- ``EXPECTED_CASE_COUNT = 51``.

Boundary-sensitive values (C5 lexi gallery = ``N_INITIAL_VOICE``, C6 confidence
= ``VOICE_ROUTING_FACE_ASSIST_MIN + 0.01``, C16 holder_n =
``VOICE_ACCUM_MATURE_SAMPLE_COUNT``) and the band boundaries are authored
config-relative so the golden source tracks ``core.config`` rather than drifting
from it. A module-level self-check asserts every stored ``expected_band`` matches
the config-relative band derivation, and that the list holds exactly
``EXPECTED_CASE_COUNT`` cases.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.config import (
    N_INITIAL_VOICE,
    VOICE_ACCUM_MATURE_SAMPLE_COUNT,
    VOICE_ROUTING_FACE_ASSIST_MIN,
    VOICE_ROUTING_MIN_AUDIO_FOR_SCORE,
    VOICE_ROUTING_MIN_UTTERANCE_SECS,
    VOICE_ROUTING_NOISE_FLOOR_SECS,
)

EXPECTED_CASE_COUNT = 51


# Sentinel: "this case does not assert this field". Distinct from ``None``,
# which is a real expected pid / rule for many cases (e.g. "the cascade must
# emit pid=None"). Compare with ``is UNCHECKED`` to skip the assertion.
UNCHECKED: Any = object()


def band_for(utterance_duration: float) -> str:
    """Derive the utterance band from duration, config-relative.

    Strict ``<`` boundaries (mirror ``core.reconciler``):

        utt <  NOISE_FLOOR_SECS (0.30)        -> "noise"
        utt <  MIN_AUDIO_FOR_SCORE (0.5)      -> "gap"
        utt <  MIN_UTTERANCE_SECS (1.0)       -> "short_hard"
        else                                  -> "normal"
    """
    if utterance_duration < VOICE_ROUTING_NOISE_FLOOR_SECS:
        return "noise"
    if utterance_duration < VOICE_ROUTING_MIN_AUDIO_FOR_SCORE:
        return "gap"
    if utterance_duration < VOICE_ROUTING_MIN_UTTERANCE_SECS:
        return "short_hard"
    return "normal"


@dataclass(frozen=True)
class ReconcilerGoldenCase:
    """One golden routing case: dict payloads + expected outcome.

    ``claim`` / ``presence`` / ``session`` are plain dicts. The bench driver
    builds ``IdentityClaim(**claim)`` / ``PresenceState(**presence)`` /
    ``SessionState(**session)`` (channel imports allowed there, never here at
    golden-module load) and runs ``reconcile`` to compare the resulting
    ``decision.action`` against ``expected_action``.

    ``expected_rule_fired`` / ``expected_pid`` / ``expected_reasoning`` are
    ``UNCHECKED`` for cases that do not assert them (e.g. the contract tests
    assert action only, 6 of them also assert pid). They become load-bearing
    when 2b re-points the per-rule behavioral tests to derive from this source.
    """

    case_id: str
    claim: dict
    presence: dict
    session: dict
    expected_action: str
    expected_band: str
    expected_rule_fired: Any = UNCHECKED
    expected_pid: Any = UNCHECKED
    expected_reasoning: Any = UNCHECKED


# ──────────────────────────────────────────────────────────────────────────
# Dict builders — mirror the ``_claim`` / ``_presence`` / ``_session`` helpers
# in test_p10_reconciler_contract.py so the contract cases transcribe 1:1, and
# keep the per-rule cases concise. They produce DICTS, not dataclasses.
# ──────────────────────────────────────────────────────────────────────────


def _c(
    pid=None,
    confidence=0.0,
    utterance_duration=1.5,
    n_diarize_segments=1,
    reasoning="",
    is_no_signal=False,
):
    return {
        "pid": pid,
        "confidence": confidence,
        "n_diarize_segments": n_diarize_segments,
        "utterance_duration": utterance_duration,
        "reasoning": reasoning,
        "confidence_is_no_signal": is_no_signal,
    }


def _p(visible_pids=(), unrecognized_track_ids=(), per_pid_confidence=None):
    d: dict = {
        "visible_pids": visible_pids,
        "unrecognized_track_ids": unrecognized_track_ids,
    }
    if per_pid_confidence is not None:
        d["per_pid_confidence"] = per_pid_confidence
    return d


def _s(
    cur_pid="jagan_001",
    cur_person_type="known",
    n_active_sessions=1,
    voice_gallery_sizes=None,
    cur_holder_voice_n=20,
    now=1000.0,
):
    if voice_gallery_sizes is None:
        voice_gallery_sizes = {cur_pid: cur_holder_voice_n} if cur_pid else {}
    return {
        "cur_pid": cur_pid,
        "cur_person_type": cur_person_type,
        "n_active_sessions": n_active_sessions,
        "voice_gallery_sizes": voice_gallery_sizes,
        "cur_holder_voice_n": cur_holder_voice_n,
        "now": now,
    }


# ──────────────────────────────────────────────────────────────────────────
# Contract cases C1-C21 (from test_p10_reconciler_contract.py; now=1000.0)
# ──────────────────────────────────────────────────────────────────────────

_CONTRACT_CASES = [
    ReconcilerGoldenCase(
        case_id="C1",
        claim=_c(confidence=0.10, utterance_duration=0.7),
        presence=_p(),
        session=_s(cur_pid="jagan_001", cur_holder_voice_n=20),
        expected_action="short_utterance_voice_mismatch",
        expected_band="short_hard",
    ),
    ReconcilerGoldenCase(
        case_id="C2",
        claim=_c(confidence=0.30, utterance_duration=0.7),
        presence=_p(),
        session=_s(n_active_sessions=2),
        expected_action="short_utterance_voice_mismatch",
        expected_band="short_hard",
    ),
    ReconcilerGoldenCase(
        case_id="C4",
        claim=_c(confidence=0.0, utterance_duration=0.2),
        presence=_p(),
        session=_s(cur_pid=None, cur_person_type="", n_active_sessions=0,
                   voice_gallery_sizes={}, cur_holder_voice_n=0),
        expected_action="short_utterance_skip",
        expected_band="noise",
    ),
    ReconcilerGoldenCase(
        case_id="C5",
        claim=_c(pid="lexi_002", confidence=0.85, utterance_duration=2.0),
        presence=_p(),
        session=_s(cur_pid="jagan_001",
                   voice_gallery_sizes={"jagan_001": 20, "lexi_002": N_INITIAL_VOICE}),
        expected_action="switch_enrolled",
        expected_band="normal",
        expected_pid="lexi_002",
    ),
    ReconcilerGoldenCase(
        case_id="C6",
        claim=_c(pid="lexi_002", confidence=VOICE_ROUTING_FACE_ASSIST_MIN + 0.01,
                 utterance_duration=2.0),
        presence=_p(visible_pids=("lexi_002",)),
        session=_s(cur_pid="jagan_001",
                   voice_gallery_sizes={"jagan_001": 20, "lexi_002": 20}),
        expected_action="switch_enrolled",
        expected_band="normal",
        expected_pid="lexi_002",
    ),
    ReconcilerGoldenCase(
        case_id="C7",
        claim=_c(pid="lexi_002", confidence=0.35, utterance_duration=2.0),
        presence=_p(visible_pids=("lexi_002",)),
        session=_s(cur_pid="jagan_001",
                   voice_gallery_sizes={"jagan_001": 20, "lexi_002": 20}),
        expected_action="ambiguous",
        expected_band="normal",
    ),
    ReconcilerGoldenCase(
        case_id="C8",
        claim=_c(pid="lexi_002", confidence=0.35, utterance_duration=2.0),
        presence=_p(),
        session=_s(cur_pid="jagan_001",
                   voice_gallery_sizes={"jagan_001": 20, "lexi_002": 20}),
        expected_action="ambiguous",
        expected_band="normal",
    ),
    ReconcilerGoldenCase(
        case_id="C9",
        claim=_c(pid="jagan_001", confidence=0.10, utterance_duration=2.0),
        presence=_p(),
        session=_s(cur_pid="jagan_001"),
        expected_action="ambiguous",
        expected_band="normal",
    ),
    ReconcilerGoldenCase(
        case_id="C10",
        claim=_c(pid="stranger_x", confidence=0.35, utterance_duration=2.0),
        presence=_p(),
        session=_s(cur_pid="stranger_x", cur_person_type="stranger",
                   cur_holder_voice_n=3, voice_gallery_sizes={"stranger_x": 3}),
        expected_action="current",
        expected_band="normal",
        expected_pid="stranger_x",
    ),
    ReconcilerGoldenCase(
        case_id="C11",
        claim=_c(pid="jagan_001", confidence=0.35, utterance_duration=2.0),
        presence=_p(),
        session=_s(cur_pid="jagan_001", cur_person_type="known",
                   cur_holder_voice_n=20),
        expected_action="ambiguous",
        expected_band="normal",
    ),
    ReconcilerGoldenCase(
        case_id="C12",
        claim=_c(pid="jagan_001", confidence=0.80, utterance_duration=2.0),
        presence=_p(visible_pids=("jagan_001",)),
        session=_s(cur_pid="jagan_001"),
        expected_action="current",
        expected_band="normal",
        expected_pid="jagan_001",
    ),
    ReconcilerGoldenCase(
        case_id="C13",
        claim=_c(pid=None, confidence=0.05, utterance_duration=2.0),
        presence=_p(),
        session=_s(cur_pid="stranger_x", cur_person_type="stranger",
                   cur_holder_voice_n=2, voice_gallery_sizes={"stranger_x": 2}),
        expected_action="current",
        expected_band="normal",
        expected_pid="stranger_x",
    ),
    ReconcilerGoldenCase(
        case_id="C14",
        claim=_c(pid=None, confidence=0.10, utterance_duration=2.0,
                 n_diarize_segments=2),
        presence=_p(),
        session=_s(n_active_sessions=2),
        expected_action="multi_segment_voice_mismatch",
        expected_band="normal",
    ),
    ReconcilerGoldenCase(
        case_id="C15",
        claim=_c(pid=None, confidence=0.15, utterance_duration=2.0,
                 n_diarize_segments=1),
        presence=_p(),
        session=_s(),
        expected_action="new_stranger",
        expected_band="normal",
    ),
    ReconcilerGoldenCase(
        case_id="C16",
        claim=_c(pid=None, confidence=0.27, utterance_duration=2.0,
                 n_diarize_segments=1),
        presence=_p(),
        session=_s(n_active_sessions=2,
                   cur_holder_voice_n=VOICE_ACCUM_MATURE_SAMPLE_COUNT),
        expected_action="single_segment_voice_mismatch",
        expected_band="normal",
    ),
    ReconcilerGoldenCase(
        case_id="C17",
        claim=_c(pid=None, confidence=0.0, utterance_duration=2.0,
                 n_diarize_segments=1, is_no_signal=True),
        presence=_p(),
        session=_s(),
        expected_action="current",
        expected_band="normal",
        expected_pid="jagan_001",
    ),
    ReconcilerGoldenCase(
        case_id="C18",
        claim=_c(pid=None, confidence=0.0, utterance_duration=2.0,
                 n_diarize_segments=1, is_no_signal=True),
        presence=_p(visible_pids=("other_002",)),
        session=_s(),
        expected_action="ambiguous",
        expected_band="normal",
    ),
    ReconcilerGoldenCase(
        case_id="C19",
        claim=_c(pid=None, confidence=0.10, utterance_duration=2.0,
                 n_diarize_segments=1),
        presence=_p(),
        session=_s(cur_pid=None, cur_person_type="", n_active_sessions=0,
                   voice_gallery_sizes={}, cur_holder_voice_n=0),
        expected_action="new_stranger",
        expected_band="normal",
    ),
    ReconcilerGoldenCase(
        case_id="C20",
        claim=_c(pid=None, confidence=0.0, utterance_duration=0.3,
                 n_diarize_segments=1, is_no_signal=True),
        presence=_p(),
        session=_s(cur_pid=None, cur_person_type="", n_active_sessions=0,
                   voice_gallery_sizes={}, cur_holder_voice_n=0),
        expected_action="no_action",
        expected_band="gap",
    ),
    ReconcilerGoldenCase(
        case_id="C20b",
        claim=_c(pid=None, confidence=0.0, utterance_duration=1.6,
                 n_diarize_segments=1, is_no_signal=True),
        presence=_p(),
        session=_s(cur_pid=None, cur_person_type="", n_active_sessions=0,
                   voice_gallery_sizes={}, cur_holder_voice_n=0),
        expected_action="new_stranger",
        expected_band="normal",
    ),
    ReconcilerGoldenCase(
        case_id="C21",
        claim=_c(pid="other_pid", confidence=0.15, utterance_duration=2.0,
                 n_diarize_segments=1),
        presence=_p(),
        session=_s(cur_pid="jagan_001",
                   voice_gallery_sizes={"jagan_001": 20, "other_pid": 5}),
        expected_action="ambiguous",
        expected_band="normal",
    ),
]


# ──────────────────────────────────────────────────────────────────────────
# Per-rule cases (the 27 reconcile-calling tests in test_reconciler.py).
# Each asserts action + rule_fired; pid where the test asserts it. now varies.
# ──────────────────────────────────────────────────────────────────────────

_PER_RULE_CASES = [
    ReconcilerGoldenCase(
        case_id="PR1_p5_no_session_returns_no_action",
        claim=_c(pid=None, confidence=0.0, n_diarize_segments=1,
                 utterance_duration=0.3, reasoning="test", is_no_signal=True),
        presence=_p(),
        session=_s(cur_pid=None, cur_person_type="", n_active_sessions=0,
                   voice_gallery_sizes={}, cur_holder_voice_n=0, now=0.0),
        expected_action="no_action",
        expected_band="gap",
        expected_rule_fired="_p5_no_session_no_action",
        expected_pid=None,
    ),
    ReconcilerGoldenCase(
        case_id="PR2_p4_pyannote_vouched_stranger_opens_session",
        claim=_c(pid=None, confidence=0.0, n_diarize_segments=2,
                 utterance_duration=2.0, reasoning="ECAPA: no enrolled match",
                 is_no_signal=True),
        presence=_p(visible_pids=("jagan_992ed5",),
                    per_pid_confidence={"jagan_992ed5": 0.87}),
        session=_s(cur_pid="jagan_992ed5", cur_person_type="best_friend",
                   n_active_sessions=1, voice_gallery_sizes={"jagan_992ed5": 3},
                   cur_holder_voice_n=3, now=1714374585.223),
        expected_action="new_stranger",
        expected_band="normal",
        expected_rule_fired="_p4_pyannote_vouched_stranger",
        expected_pid=None,
    ),
    ReconcilerGoldenCase(
        case_id="PR3_p4_pyannote_vouched_stranger_negative_confidence",
        claim=_c(pid=None, confidence=-0.05, n_diarize_segments=2,
                 utterance_duration=2.0,
                 reasoning="ECAPA: no enrolled match (best_score=-0.05)"),
        presence=_p(visible_pids=("jagan_992ed5",),
                    per_pid_confidence={"jagan_992ed5": 0.87}),
        session=_s(cur_pid="jagan_992ed5", cur_person_type="best_friend",
                   n_active_sessions=1, voice_gallery_sizes={"jagan_992ed5": 3},
                   cur_holder_voice_n=3, now=1714374585.223),
        expected_action="new_stranger",
        expected_band="normal",
        expected_rule_fired="_p4_pyannote_vouched_stranger",
        expected_pid=None,
    ),
    ReconcilerGoldenCase(
        case_id="PR4_p4_new_stranger_low_match_negative_confidence",
        claim=_c(pid=None, confidence=-0.08, n_diarize_segments=1,
                 utterance_duration=1.5,
                 reasoning="ECAPA: no enrolled match (best_score=-0.08)"),
        presence=_p(visible_pids=("jagan_abc",)),
        session=_s(cur_pid="jagan_abc", cur_person_type="best_friend",
                   n_active_sessions=1, voice_gallery_sizes={"jagan_abc": 10},
                   cur_holder_voice_n=10, now=1714374600.0),
        expected_action="new_stranger",
        expected_band="normal",
        expected_rule_fired="_p4_new_stranger_low_match",
        expected_pid=None,
    ),
    ReconcilerGoldenCase(
        case_id="PR5_p0_tier1_hard_mismatch_drops",
        claim=_c(pid="jagan_abc", confidence=0.10, n_diarize_segments=1,
                 utterance_duration=0.7, reasoning="test"),
        presence=_p(visible_pids=("jagan_abc",)),
        session=_s(cur_pid="jagan_abc", cur_person_type="best_friend",
                   n_active_sessions=1, voice_gallery_sizes={"jagan_abc": 20},
                   cur_holder_voice_n=20, now=0.0),
        expected_action="short_utterance_voice_mismatch",
        expected_band="short_hard",
        expected_rule_fired="_p0_short_utterance_hard_mismatch",
        expected_pid=None,
    ),
    ReconcilerGoldenCase(
        case_id="PR6_p0_tier2_ambiguous_drops_in_multi_session",
        claim=_c(pid="jagan_abc", confidence=0.30, n_diarize_segments=1,
                 utterance_duration=0.7, reasoning="test"),
        presence=_p(visible_pids=("jagan_abc", "lexi_def")),
        session=_s(cur_pid="jagan_abc", cur_person_type="best_friend",
                   n_active_sessions=2,
                   voice_gallery_sizes={"jagan_abc": 20, "lexi_def": 5},
                   cur_holder_voice_n=20, now=0.0),
        expected_action="short_utterance_voice_mismatch",
        expected_band="short_hard",
        expected_rule_fired="_p0_short_utterance_ambiguous_multi_session",
    ),
    ReconcilerGoldenCase(
        case_id="PR7_p0_short_utterance_holds_current",
        claim=_c(pid="jagan_abc", confidence=0.30, n_diarize_segments=1,
                 utterance_duration=0.2, reasoning="test"),
        presence=_p(visible_pids=("jagan_abc",)),
        session=_s(cur_pid="jagan_abc", cur_person_type="best_friend",
                   n_active_sessions=1, voice_gallery_sizes={"jagan_abc": 20},
                   cur_holder_voice_n=20, now=0.0),
        expected_action="current",
        expected_band="noise",
        expected_rule_fired="_p0_pure_noise_hold_current",
        expected_pid="jagan_abc",
    ),
    ReconcilerGoldenCase(
        case_id="PR8_p0_short_utterance_no_session_skips",
        claim=_c(pid=None, confidence=0.0, n_diarize_segments=1,
                 utterance_duration=0.2, reasoning="test"),
        presence=_p(),
        session=_s(cur_pid=None, cur_person_type="", n_active_sessions=0,
                   voice_gallery_sizes={}, cur_holder_voice_n=0, now=0.0),
        expected_action="short_utterance_skip",
        expected_band="noise",
        expected_rule_fired="_p0_short_utterance_no_session",
        expected_pid=None,
    ),
    ReconcilerGoldenCase(
        case_id="PR9_p0_short_utterance_gap_holds_current",
        claim=_c(pid="jagan_abc", confidence=0.40, n_diarize_segments=1,
                 utterance_duration=0.4, reasoning="test"),
        presence=_p(visible_pids=("jagan_abc",)),
        session=_s(cur_pid="jagan_abc", cur_person_type="best_friend",
                   n_active_sessions=1, voice_gallery_sizes={"jagan_abc": 20},
                   cur_holder_voice_n=20, now=0.0),
        expected_action="current",
        expected_band="gap",
        expected_rule_fired="_p0_short_utterance_gap_hold_current",
        expected_pid="jagan_abc",
    ),
    ReconcilerGoldenCase(
        case_id="PR10_p1_confident_switch_to_other_pid",
        claim=_c(pid="lexi_def", confidence=0.80, n_diarize_segments=1,
                 utterance_duration=2.0, reasoning="test"),
        presence=_p(visible_pids=("jagan_abc",)),
        session=_s(cur_pid="jagan_abc", cur_person_type="best_friend",
                   n_active_sessions=2,
                   voice_gallery_sizes={"jagan_abc": 20, "lexi_def": 20},
                   cur_holder_voice_n=20, now=0.0),
        expected_action="switch_enrolled",
        expected_band="normal",
        expected_rule_fired="_p1_confident_voice_switch",
        expected_pid="lexi_def",
    ),
    ReconcilerGoldenCase(
        case_id="PR11_p2_midrange_face_assist_switches",
        claim=_c(pid="lexi_def", confidence=0.50, n_diarize_segments=1,
                 utterance_duration=2.0, reasoning="test"),
        presence=_p(visible_pids=("jagan_abc", "lexi_def")),
        session=_s(cur_pid="jagan_abc", cur_person_type="best_friend",
                   n_active_sessions=2,
                   voice_gallery_sizes={"jagan_abc": 20, "lexi_def": 3},
                   cur_holder_voice_n=20, now=0.0),
        expected_action="switch_enrolled",
        expected_band="normal",
        expected_rule_fired="_p2_midrange_face_assist_switches",
        expected_pid="lexi_def",
    ),
    ReconcilerGoldenCase(
        case_id="PR12_p2_midrange_face_assist_below_floor_returns_ambiguous",
        claim=_c(pid="lexi_def", confidence=0.35, n_diarize_segments=1,
                 utterance_duration=2.0, reasoning="test"),
        presence=_p(visible_pids=("jagan_abc", "lexi_def")),
        session=_s(cur_pid="jagan_abc", cur_person_type="best_friend",
                   n_active_sessions=2,
                   voice_gallery_sizes={"jagan_abc": 20, "lexi_def": 20},
                   cur_holder_voice_n=20, now=0.0),
        expected_action="ambiguous",
        expected_band="normal",
        expected_rule_fired="_p2_midrange_face_assist_below_floor",
        expected_pid=None,
    ),
    ReconcilerGoldenCase(
        case_id="PR13_p2_midrange_no_face_assist_returns_ambiguous",
        claim=_c(pid="lexi_def", confidence=0.45, n_diarize_segments=1,
                 utterance_duration=2.0, reasoning="test"),
        presence=_p(visible_pids=("jagan_abc",)),
        session=_s(cur_pid="jagan_abc", cur_person_type="best_friend",
                   n_active_sessions=2,
                   voice_gallery_sizes={"jagan_abc": 20, "lexi_def": 3},
                   cur_holder_voice_n=20, now=0.0),
        expected_action="ambiguous",
        expected_band="normal",
        expected_rule_fired="_p2_midrange_no_face_returns_ambiguous",
        expected_pid=None,
    ),
    ReconcilerGoldenCase(
        case_id="PR14_p3_below_self_match_floor_returns_ambiguous",
        claim=_c(pid="jagan_abc", confidence=0.10, n_diarize_segments=1,
                 utterance_duration=2.0, reasoning="test"),
        presence=_p(visible_pids=("jagan_abc",)),
        session=_s(cur_pid="jagan_abc", cur_person_type="best_friend",
                   n_active_sessions=1, voice_gallery_sizes={"jagan_abc": 20},
                   cur_holder_voice_n=20, now=0.0),
        expected_action="ambiguous",
        expected_band="normal",
        expected_rule_fired="_p3_self_match_below_floor",
        expected_pid=None,
    ),
    ReconcilerGoldenCase(
        case_id="PR15_p3_thin_stranger_skips_offscreen_floor",
        claim=_c(pid="stranger_chloe", confidence=0.307, n_diarize_segments=1,
                 utterance_duration=2.0, reasoning="test"),
        presence=_p(),
        session=_s(cur_pid="stranger_chloe", cur_person_type="stranger",
                   n_active_sessions=1,
                   voice_gallery_sizes={"stranger_chloe": 3},
                   cur_holder_voice_n=3, now=0.0),
        expected_action="current",
        expected_band="normal",
        expected_rule_fired="_p3_self_match_thin_stranger_relaxed",
        expected_pid="stranger_chloe",
    ),
    ReconcilerGoldenCase(
        case_id="PR16_p3_offscreen_mature_floors_apply",
        claim=_c(pid="jagan_abc", confidence=0.35, n_diarize_segments=1,
                 utterance_duration=2.0, reasoning="test"),
        presence=_p(),
        session=_s(cur_pid="jagan_abc", cur_person_type="best_friend",
                   n_active_sessions=1, voice_gallery_sizes={"jagan_abc": 20},
                   cur_holder_voice_n=20, now=0.0),
        expected_action="ambiguous",
        expected_band="normal",
        expected_rule_fired="_p3_self_match_offscreen_mature",
        expected_pid=None,
    ),
    ReconcilerGoldenCase(
        case_id="PR17_p3_self_match_with_face_holds_current",
        claim=_c(pid="jagan_abc", confidence=0.50, n_diarize_segments=1,
                 utterance_duration=2.0, reasoning="test"),
        presence=_p(visible_pids=("jagan_abc",)),
        session=_s(cur_pid="jagan_abc", cur_person_type="best_friend",
                   n_active_sessions=1, voice_gallery_sizes={"jagan_abc": 20},
                   cur_holder_voice_n=20, now=0.0),
        expected_action="current",
        expected_band="normal",
        expected_rule_fired="_p3_self_match_with_face",
        expected_pid="jagan_abc",
    ),
    ReconcilerGoldenCase(
        case_id="PR18_p3_5_bootstrapping_stranger_holds_current",
        claim=_c(pid=None, confidence=0.05, n_diarize_segments=1,
                 utterance_duration=2.0, reasoning="test"),
        presence=_p(),
        session=_s(cur_pid="stranger_chloe", cur_person_type="stranger",
                   n_active_sessions=1,
                   voice_gallery_sizes={"stranger_chloe": 2},
                   cur_holder_voice_n=2, now=0.0),
        expected_action="current",
        expected_band="normal",
        expected_rule_fired="_p3_5_bootstrapping_stranger_hold",
        expected_pid="stranger_chloe",
    ),
    ReconcilerGoldenCase(
        case_id="PR19_p4_multi_segment_mismatch_drops_in_multi_known",
        claim=_c(pid=None, confidence=0.20, n_diarize_segments=3,
                 utterance_duration=2.0, reasoning="test"),
        presence=_p(visible_pids=("jagan_abc", "lexi_def")),
        session=_s(cur_pid="jagan_abc", cur_person_type="best_friend",
                   n_active_sessions=2,
                   voice_gallery_sizes={"jagan_abc": 20, "lexi_def": 20},
                   cur_holder_voice_n=20, now=0.0),
        expected_action="multi_segment_voice_mismatch",
        expected_band="normal",
        expected_rule_fired="_p4_multi_segment_mismatch",
        expected_pid=None,
    ),
    ReconcilerGoldenCase(
        case_id="PR20_p4_new_stranger_below_threshold",
        claim=_c(pid=None, confidence=0.15, n_diarize_segments=1,
                 utterance_duration=2.0, reasoning="test"),
        presence=_p(visible_pids=("jagan_abc",)),
        session=_s(cur_pid="jagan_abc", cur_person_type="best_friend",
                   n_active_sessions=1, voice_gallery_sizes={"jagan_abc": 20},
                   cur_holder_voice_n=20, now=0.0),
        expected_action="new_stranger",
        expected_band="normal",
        expected_rule_fired="_p4_new_stranger_low_match",
        expected_pid=None,
    ),
    ReconcilerGoldenCase(
        case_id="PR21_p4_single_segment_mismatch_drops_in_multi_known",
        claim=_c(pid=None, confidence=0.27, n_diarize_segments=1,
                 utterance_duration=1.5, reasoning="test"),
        presence=_p(visible_pids=("jagan_abc", "lexi_def")),
        session=_s(cur_pid="jagan_abc", cur_person_type="best_friend",
                   n_active_sessions=2,
                   voice_gallery_sizes={"jagan_abc": 20, "lexi_def": 20},
                   cur_holder_voice_n=20, now=0.0),
        expected_action="single_segment_voice_mismatch",
        expected_band="normal",
        expected_rule_fired="_p4_single_segment_mismatch",
        expected_pid=None,
    ),
    ReconcilerGoldenCase(
        case_id="PR22_p4_voice_ambiguous_no_candidates_holds_current",
        claim=_c(pid=None, confidence=0.0, n_diarize_segments=1,
                 utterance_duration=2.0, reasoning="test", is_no_signal=True),
        presence=_p(visible_pids=("jagan_abc",)),
        session=_s(cur_pid="jagan_abc", cur_person_type="best_friend",
                   n_active_sessions=1, voice_gallery_sizes={"jagan_abc": 20},
                   cur_holder_voice_n=20, now=0.0),
        expected_action="current",
        expected_band="normal",
        expected_rule_fired="_p4_voice_ambiguous_no_candidates",
        expected_pid="jagan_abc",
    ),
    ReconcilerGoldenCase(
        case_id="PR23_p4_voice_ambiguous_with_candidates_returns_ambiguous",
        claim=_c(pid=None, confidence=0.0, n_diarize_segments=1,
                 utterance_duration=2.0, reasoning="test", is_no_signal=True),
        presence=_p(visible_pids=("jagan_abc",), unrecognized_track_ids=(42,)),
        session=_s(cur_pid="jagan_abc", cur_person_type="best_friend",
                   n_active_sessions=1, voice_gallery_sizes={"jagan_abc": 20},
                   cur_holder_voice_n=20, now=0.0),
        expected_action="ambiguous",
        expected_band="normal",
        expected_rule_fired="_p4_voice_ambiguous_with_candidates",
        expected_pid=None,
    ),
    ReconcilerGoldenCase(
        case_id="PR24_p5_no_session_opens_stranger",
        claim=_c(pid=None, confidence=0.10, n_diarize_segments=1,
                 utterance_duration=2.0, reasoning="test"),
        presence=_p(),
        session=_s(cur_pid=None, cur_person_type="", n_active_sessions=0,
                   voice_gallery_sizes={}, cur_holder_voice_n=0, now=0.0),
        expected_action="new_stranger",
        expected_band="normal",
        expected_rule_fired="_p5_no_session_new_stranger",
        expected_pid=None,
    ),
    ReconcilerGoldenCase(
        case_id="PR25_last_resort_ambiguous_when_low_score_other_pid",
        claim=_c(pid="lexi_def", confidence=0.10, n_diarize_segments=1,
                 utterance_duration=2.0, reasoning="test"),
        presence=_p(visible_pids=("jagan_abc",)),
        session=_s(cur_pid="jagan_abc", cur_person_type="best_friend",
                   n_active_sessions=1,
                   voice_gallery_sizes={"jagan_abc": 20, "lexi_def": 20},
                   cur_holder_voice_n=20, now=0.0),
        expected_action="ambiguous",
        expected_band="normal",
        expected_rule_fired="_last_resort_ambiguous",
        expected_pid=None,
        expected_reasoning=(
            "voice match below switch threshold, ambiguous attribution"
        ),
    ),
    ReconcilerGoldenCase(
        case_id="PR26_spec1_d1_no_signal_short_utterance_holds_current",
        claim=_c(pid=None, confidence=0.0, n_diarize_segments=1,
                 utterance_duration=0.7, reasoning="test", is_no_signal=True),
        presence=_p(visible_pids=("jagan_abc",)),
        session=_s(cur_pid="jagan_abc", cur_person_type="best_friend",
                   n_active_sessions=1, voice_gallery_sizes={"jagan_abc": 20},
                   cur_holder_voice_n=20, now=0.0),
        expected_action="current",
        expected_band="short_hard",
        expected_rule_fired="_p4_voice_ambiguous_no_candidates",
        expected_pid="jagan_abc",
    ),
    ReconcilerGoldenCase(
        case_id="PR27_spec1_d1_no_signal_short_utterance_multi_candidate_returns_ambiguous",
        claim=_c(pid=None, confidence=0.0, n_diarize_segments=1,
                 utterance_duration=0.7, reasoning="test", is_no_signal=True),
        presence=_p(visible_pids=("jagan_abc",), unrecognized_track_ids=(42,)),
        session=_s(cur_pid="jagan_abc", cur_person_type="best_friend",
                   n_active_sessions=1, voice_gallery_sizes={"jagan_abc": 20},
                   cur_holder_voice_n=20, now=0.0),
        expected_action="ambiguous",
        expected_band="short_hard",
        expected_rule_fired="_p4_voice_ambiguous_with_candidates",
        expected_pid=None,
    ),
]


# ──────────────────────────────────────────────────────────────────────────
# N4b vetoed-path rows (#128 D2 per-rule veto, flattened per architect ruling
# 2026-07-02). One row per new_stranger emitter, with inputs that WOULD fire
# that rule if claim.pid were None — but pid="lexi_002" is set, so the
# `claim.pid is None` guard vetoes. expected_action pins the action the
# cascade ACTUALLY returns on the vetoed path (empirically determined by
# running reconcile; deterministic across 3 processes + 50 repeated calls) —
# strictly stronger than `!= "new_stranger"`: a veto regression surfaces as
# the action changing, not just as not-stranger. The reconcile-level N4b
# sweep in test_p10_reconciler_contract.py stays as an invariant on top.
# ──────────────────────────────────────────────────────────────────────────

_N4B_VETO_CASES = [
    ReconcilerGoldenCase(
        # Would fire _p4_pyannote_vouched_stranger if pid were None
        # (no-signal confidence + 2 diarize segments). Vetoed path falls
        # through to _last_resort_ambiguous.
        case_id="N4B_pyannote_vouched_pid_bearing_veto",
        claim=_c(pid="lexi_002", confidence=0.0, n_diarize_segments=2,
                 is_no_signal=True),
        presence=_p(),
        session=_s(cur_pid="jagan_001", n_active_sessions=1),
        expected_action="ambiguous",
        expected_band="normal",
        expected_rule_fired="_last_resort_ambiguous",
        expected_pid=None,
    ),
    ReconcilerGoldenCase(
        # Would fire _p4_new_stranger_low_match if pid were None (genuine
        # low cosine, single segment). Vetoed path falls through to
        # _last_resort_ambiguous.
        case_id="N4B_new_stranger_low_match_pid_bearing_veto",
        claim=_c(pid="lexi_002", confidence=0.10, n_diarize_segments=1),
        presence=_p(),
        session=_s(cur_pid="jagan_001"),
        expected_action="ambiguous",
        expected_band="normal",
        expected_rule_fired="_last_resort_ambiguous",
        expected_pid=None,
    ),
    ReconcilerGoldenCase(
        # Would fire _p5_no_session_new_stranger if pid were None (no active
        # session, low cosine). Vetoed path exhausts the cascade — reconcile
        # returns the degenerate no_action decision (rule_fired="").
        case_id="N4B_no_session_new_stranger_pid_bearing_veto",
        claim=_c(pid="lexi_002", confidence=0.10, n_diarize_segments=1),
        presence=_p(),
        session=_s(cur_pid=None, cur_person_type="", n_active_sessions=0,
                   cur_holder_voice_n=0),
        expected_action="no_action",
        expected_band="normal",
        expected_rule_fired="",
        expected_pid=None,
    ),
]


RECONCILER_GOLDEN_CASES = [*_CONTRACT_CASES, *_PER_RULE_CASES, *_N4B_VETO_CASES]


# ──────────────────────────────────────────────────────────────────────────
# Module-level self-checks (run at import; cheap, no channel imports).
#   (1) the list holds exactly EXPECTED_CASE_COUNT cases.
#   (2) every stored expected_band matches the config-relative derivation —
#       catches transcription drift in the band field against the actual utt.
#   (3) case_ids are unique (no copy-paste collision).
# ──────────────────────────────────────────────────────────────────────────

assert len(RECONCILER_GOLDEN_CASES) == EXPECTED_CASE_COUNT, (
    f"RECONCILER_GOLDEN_CASES holds {len(RECONCILER_GOLDEN_CASES)} cases; "
    f"expected {EXPECTED_CASE_COUNT}"
)

for _case in RECONCILER_GOLDEN_CASES:
    _derived = band_for(_case.claim["utterance_duration"])
    assert _case.expected_band == _derived, (
        f"{_case.case_id}: stored band {_case.expected_band!r} != derived "
        f"{_derived!r} for utt={_case.claim['utterance_duration']}"
    )

assert len({c.case_id for c in RECONCILER_GOLDEN_CASES}) == EXPECTED_CASE_COUNT, (
    "duplicate case_id in RECONCILER_GOLDEN_CASES"
)

del _case, _derived
