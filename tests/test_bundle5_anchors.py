"""A1-A5 anchor tests for Pre-P1 Bundle 5 (Contract Typing MF7 + MF8).

A1 = D1 IdentityClaim.confidence_is_no_signal field added + frozen preserved.
A2 = D2a voice.identify 3-tuple return (True/False/False) + _IdentifyFn alias.
A3 = D2b identify_speaker 5-site flag + success-path flag propagation (behavioral).
A4 = D2c+D2e reconciler construction kwarg + 6-predicate migration + Session-119
     negative-cosine canary (behavioral — the `< 0.0` half stays load-bearing).
A5 = D2d event-log round-trip (encode via asdict → decode → flag preserved).

A6 = D3 MF7 AST invariant (tests/test_no_exact_equality_against_claim_confidence.py).
A7 = D4+D5 MF8 tuple + AST invariant
     (tests/test_session_snapshot_collection_fields_are_immutable.py).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import dataclasses
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# --- A1: D1 field added + frozen preserved ---

def test_a1_identity_claim_has_confidence_is_no_signal_field() -> None:
    """A1 — IdentityClaim declares `confidence_is_no_signal: bool = False`, frozen preserved."""
    from core.voice_channel import IdentityClaim

    fields = {f.name: f for f in dataclasses.fields(IdentityClaim)}
    assert "confidence_is_no_signal" in fields, "IdentityClaim missing confidence_is_no_signal"
    assert fields["confidence_is_no_signal"].default is False, (
        "confidence_is_no_signal must default to False (positionally-safe trailing field)"
    )
    # Frozen preserved — mutation must raise.
    claim = IdentityClaim(
        pid=None, confidence=0.0, n_diarize_segments=0,
        utterance_duration=1.0, reasoning="x",
    )
    assert claim.confidence_is_no_signal is False
    with pytest.raises(dataclasses.FrozenInstanceError):
        claim.confidence_is_no_signal = True  # type: ignore[misc]


# --- A2: D2a 3-tuple return + alias ---

def test_a2_voice_identify_returns_3tuple_with_correct_flags() -> None:
    """A2 — core/voice.py identify() returns True/False/False at the 3 return sites."""
    text = (REPO_ROOT / "core" / "voice.py").read_text(encoding="utf-8")
    idx = text.find("async def identify(")
    assert idx >= 0
    body = text[idx:idx + 1500]
    assert "return None, 0.0, True" in body, "no-signal return must be (None, 0.0, True)"
    assert "return best_id, best_score, False" in body, "match return must be (..., False)"
    assert "return None, best_score, False" in body, "gallery-miss return must be (..., False)"
    assert "-> tuple[str | None, float, bool]:" in body, "return annotation must be 3-tuple"


def test_a2_identify_fn_alias_is_3tuple() -> None:
    """A2 — _IdentifyFn type alias is the 3-tuple callable."""
    text = (REPO_ROOT / "core" / "voice_channel.py").read_text(encoding="utf-8")
    assert "_IdentifyFn = Callable[..., tuple[Optional[str], float, bool]]" in text


# --- A3: D2b identify_speaker 5-site + success-path flag (behavioral) ---

@pytest.mark.asyncio
async def test_a3_identify_speaker_sets_flag_behaviorally() -> None:
    """A3 — identify_speaker sets confidence_is_no_signal correctly across paths."""
    import numpy as np
    from core.voice_channel import identify_speaker

    audio = np.ones(16000, dtype=np.float32) * 0.1
    gallery = {"alice": np.ones(192, dtype=np.float32) / np.sqrt(192)}

    def _diarize_empty(*_a, **_kw):
        return []

    def _identify_no_signal(*_a, **_kw):
        return (None, 0.0, True)

    def _identify_match(*_a, **_kw):
        return ("alice", 0.7, False)

    def _identify_gallery_miss(*_a, **_kw):
        return (None, 0.05, False)  # real (sub-threshold) cosine — has signal

    # By-construction no-signal: empty gallery → flag True.
    claim_empty = await identify_speaker(audio, {}, utterance_duration=1.0)
    assert claim_empty.confidence_is_no_signal is True

    # By-construction no-signal: audio None → flag True.
    claim_none = await identify_speaker(None, gallery, utterance_duration=1.0)
    assert claim_none.confidence_is_no_signal is True

    # Success path: backend reports no-signal → flag True (from the 3-tuple unpack).
    claim_ns = await identify_speaker(
        audio, gallery, utterance_duration=1.0,
        diarize_fn=_diarize_empty, identify_fn=_identify_no_signal,
    )
    assert claim_ns.confidence_is_no_signal is True

    # Success path: real match → flag False.
    claim_match = await identify_speaker(
        audio, gallery, utterance_duration=1.0,
        diarize_fn=_diarize_empty, identify_fn=_identify_match,
    )
    assert claim_match.confidence_is_no_signal is False
    assert claim_match.pid == "alice"

    # Success path: gallery miss with real cosine → flag False (has signal).
    claim_miss = await identify_speaker(
        audio, gallery, utterance_duration=1.0,
        diarize_fn=_diarize_empty, identify_fn=_identify_gallery_miss,
    )
    assert claim_miss.confidence_is_no_signal is False


# --- A4: D2c+D2e reconciler kwarg + 6-predicate migration + Session-119 canary ---

def _make_state(confidence: float, *, is_no_signal: bool, n_segments: int):
    from core.voice_channel import IdentityClaim
    from core.vision_channel import PresenceState
    from core.reconciler_state import SessionState

    claim = IdentityClaim(
        pid=None, confidence=confidence, n_diarize_segments=n_segments,
        utterance_duration=2.0, reasoning="canary",
        confidence_is_no_signal=is_no_signal,
    )
    presence = PresenceState(
        visible_pids=("jagan_992ed5",),
        unrecognized_track_ids=(),
        per_pid_confidence={"jagan_992ed5": 0.87},
    )
    session = SessionState(
        cur_pid="jagan_992ed5", cur_person_type="best_friend",
        n_active_sessions=1, voice_gallery_sizes={"jagan_992ed5": 3},
        cur_holder_voice_n=3, now=1714374585.0,
    )
    return claim, presence, session


def test_a4_build_routing_inputs_propagates_no_signal_kwarg() -> None:
    """A4 — _build_routing_inputs threads v_score_is_no_signal into the claim."""
    from core.reconciler import _build_routing_inputs

    claim, _, _ = _build_routing_inputs(
        v_pid=None, v_score=0.0, n_diarize_segments=0, utterance_duration=1.0,
        persons_in_frame={}, unrecognized_tracks={}, cur_pid=None,
        cur_person_type="", n_active_sessions=0, voice_gallery_sizes={},
        now=0.0, v_score_is_no_signal=True,
    )
    assert claim.confidence_is_no_signal is True

    claim2, _, _ = _build_routing_inputs(
        v_pid="p1", v_score=0.8, n_diarize_segments=1, utterance_duration=1.0,
        persons_in_frame={}, unrecognized_tracks={}, cur_pid=None,
        cur_person_type="", n_active_sessions=0, voice_gallery_sizes={},
        now=0.0,  # default False
    )
    assert claim2.confidence_is_no_signal is False


def test_a4_session_119_negative_cosine_canary_fires() -> None:
    """A4 — Session-119 canary: a NEGATIVE-cosine no-pid claim (flag False) in a solo
    multi-segment room still routes to new_stranger via _p4_pyannote_vouched_stranger.

    This is the load-bearing `or claim.confidence < 0.0` half of the 628 migration.
    A bare no-signal flag (False here) would miss it; the `< 0.0` catches it.
    """
    from core.reconciler import reconcile, _p4_pyannote_vouched_stranger

    claim, presence, session = _make_state(-0.05, is_no_signal=False, n_segments=2)
    decision = reconcile(claim, presence, session)
    assert decision.action == "new_stranger", (
        f"negative-cosine canary must route new_stranger, got {decision.action!r} "
        f"from {decision.rule_fired!r}"
    )
    assert decision.rule_fired == _p4_pyannote_vouched_stranger.__name__


def test_a4_no_signal_flag_also_fires_pyannote_vouched() -> None:
    """A4 — the flag half also fires: no-signal (flag True, score 0.0) solo multi-segment."""
    from core.reconciler import reconcile, _p4_pyannote_vouched_stranger

    claim, presence, session = _make_state(0.0, is_no_signal=True, n_segments=2)
    decision = reconcile(claim, presence, session)
    assert decision.rule_fired == _p4_pyannote_vouched_stranger.__name__
    assert decision.action == "new_stranger"


# --- A5: D2d event-log round-trip ---

def test_a5_event_log_round_trip_preserves_flag() -> None:
    """A5 — IdentityClaim(confidence_is_no_signal=True) survives asdict→JSON→decode."""
    from core.voice_channel import IdentityClaim
    from core.event_log.types import _identity_claim_from_dict

    claim = IdentityClaim(
        pid=None, confidence=0.0, n_diarize_segments=2,
        utterance_duration=2.0, reasoning="no signal",
        confidence_is_no_signal=True,
    )
    # Mirror the producer encoder (dataclasses.asdict) + JSON transport.
    encoded = json.loads(json.dumps(dataclasses.asdict(claim)))
    decoded = _identity_claim_from_dict(encoded)
    assert decoded.confidence_is_no_signal is True, "flag lost on round-trip"
    assert decoded.pid is None and decoded.confidence == 0.0

    # Round-trip with flag False (the common case).
    claim2 = IdentityClaim(
        pid="alice", confidence=0.72, n_diarize_segments=1,
        utterance_duration=1.5, reasoning="match",
    )
    decoded2 = _identity_claim_from_dict(json.loads(json.dumps(dataclasses.asdict(claim2))))
    assert decoded2.confidence_is_no_signal is False

    # Legacy payload (no key) defaults to False — backward compatible decode.
    legacy = {
        "pid": None, "confidence": 0.0, "n_diarize_segments": 0,
        "utterance_duration": 1.0, "reasoning": "legacy", "raw_segment_scores": [],
    }
    assert _identity_claim_from_dict(legacy).confidence_is_no_signal is False
