"""100% coverage for core.voice_channel — the pure speaker-ID function
identify_speaker() and its executor helper. Every branch is reachable with
injected sync/async fakes; no real ECAPA/pyannote needed. Part of the
coverage-to-100 campaign (see COVERAGE.md)."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import numpy as np
import pytest

import core.voice_channel as vc
from core.voice_channel import identify_speaker, IdentityClaim


_BUF = np.zeros(16000, dtype=np.float32)
_GALLERY = {"alice": np.ones(192, dtype=np.float32)}


def _diarize_ok(audio, gallery, threshold, sample_rate):
    return [{"speaker_id": "alice", "speaker_score": 0.8}]


def _identify_match(audio, gallery, threshold, sample_rate):
    return ("alice", 0.8, False)


async def test_matched_speaker_builds_claim():
    claim = await identify_speaker(
        _BUF, _GALLERY, utterance_duration=1.5,
        diarize_fn=_diarize_ok, identify_fn=_identify_match,
    )
    assert isinstance(claim, IdentityClaim)
    assert claim.pid == "alice" and claim.confidence == pytest.approx(0.8)
    assert claim.n_diarize_segments == 1 and not claim.confidence_is_no_signal
    assert "matched 'alice'" in claim.reasoning
    assert claim.raw_segment_scores == (("alice", 0.8),)


async def test_none_audio_returns_no_signal_claim():
    claim = await identify_speaker(
        None, _GALLERY, utterance_duration=0.0,
        diarize_fn=_diarize_ok, identify_fn=_identify_match,
    )
    assert claim.pid is None and claim.confidence_is_no_signal
    assert claim.reasoning == "audio_buf is None"


async def test_empty_gallery_returns_no_signal_claim():
    claim = await identify_speaker(
        _BUF, {}, utterance_duration=1.0,
        diarize_fn=_diarize_ok, identify_fn=_identify_match,
    )
    assert claim.pid is None and claim.confidence_is_no_signal
    assert claim.reasoning == "voice_gallery is empty"


async def test_diarize_exception_is_captured():
    def _boom(*a, **k):
        raise RuntimeError("pyannote down")
    claim = await identify_speaker(
        _BUF, _GALLERY, utterance_duration=1.0,
        diarize_fn=_boom, identify_fn=_identify_match,
    )
    assert claim.pid is None and claim.confidence_is_no_signal
    assert claim.reasoning.startswith("diarize failed: RuntimeError")


async def test_identify_exception_is_captured():
    def _boom(*a, **k):
        raise ValueError("ecapa down")
    claim = await identify_speaker(
        _BUF, _GALLERY, utterance_duration=1.0,
        diarize_fn=_diarize_ok, identify_fn=_boom,
    )
    assert claim.pid is None and claim.confidence_is_no_signal
    assert claim.reasoning.startswith("identify failed: ValueError")
    assert claim.n_diarize_segments == 1  # diarize ran before identify failed


async def test_no_match_with_positive_score_reports_threshold():
    def _miss(audio, gallery, threshold, sample_rate):
        return (None, 0.15, False)
    claim = await identify_speaker(
        _BUF, _GALLERY, utterance_duration=1.0,
        diarize_fn=_diarize_ok, identify_fn=_miss,
    )
    assert claim.pid is None
    assert "< threshold" in claim.reasoning


async def test_no_match_with_zero_score_reports_no_signal():
    def _zero(audio, gallery, threshold, sample_rate):
        return (None, 0.0, True)
    claim = await identify_speaker(
        _BUF, _GALLERY, utterance_duration=1.0,
        diarize_fn=_diarize_ok, identify_fn=_zero,
    )
    assert claim.pid is None
    assert claim.reasoning == "no gallery match (score 0.0)"
    assert claim.confidence_is_no_signal


async def test_async_diarize_fn_runs_via_coroutine_branch():
    async def _adiarize(audio, gallery, threshold, sample_rate):
        return [{"speaker_id": "alice", "speaker_score": 0.9}]
    claim = await identify_speaker(
        _BUF, _GALLERY, utterance_duration=1.0,
        diarize_fn=_adiarize, identify_fn=_identify_match,
    )
    assert claim.n_diarize_segments == 1


async def test_lazy_default_imports_from_core_voice(monkeypatch):
    # cover the diarize_fn/identify_fn None-default lazy-import path
    import core.voice as real_voice
    monkeypatch.setattr(real_voice, "diarize", _diarize_ok, raising=False)
    monkeypatch.setattr(real_voice, "identify", _identify_match, raising=False)
    claim = await identify_speaker(_BUF, _GALLERY, utterance_duration=1.0)
    assert claim.pid == "alice"


async def test_empty_segments_yields_zero_count():
    def _no_segments(audio, gallery, threshold, sample_rate):
        return []
    claim = await identify_speaker(
        _BUF, _GALLERY, utterance_duration=1.0,
        diarize_fn=_no_segments, identify_fn=_identify_match,
    )
    assert claim.n_diarize_segments == 0 and claim.raw_segment_scores == ()
