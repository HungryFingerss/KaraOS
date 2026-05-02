"""tests/test_voice_channel.py — Phase 1 of Voice/Vision Independence.

Tests the new pure `core.voice_channel.identify_speaker` function. Hard
rule under test: the function MUST NOT import from pipeline.py, MUST
NOT read vision state, MUST NOT call _face_in_frame or any presence
tracker. Each test reflects one boundary or behavioral contract from
VOICE_VISION_INDEPENDENCE_PLAN.md.
"""
from __future__ import annotations

import asyncio
import importlib
import sys
from typing import Optional

import numpy as np
import pytest

from core import voice_channel as vc_mod
from core.voice_channel import IdentityClaim, identify_speaker


# ── Test fixtures + helpers ───────────────────────────────────────────────


def _audio(duration_secs: float = 1.0, sample_rate: int = 16_000) -> np.ndarray:
    """Synthetic float32 mono audio. The voice_channel doesn't actually
    look at sample contents (it delegates to diarize/identify), so any
    deterministic noise pattern works."""
    rng = np.random.default_rng(42)
    n = int(duration_secs * sample_rate)
    return rng.standard_normal(n).astype(np.float32) * 0.01


def _gallery(*pids: str, dim: int = 192) -> dict[str, np.ndarray]:
    """Synthetic L2-normalized gallery vectors, one per pid."""
    out = {}
    for i, pid in enumerate(pids):
        rng = np.random.default_rng(i + 1000)
        v = rng.standard_normal(dim).astype(np.float32)
        out[pid] = v / float(np.linalg.norm(v) + 1e-9)
    return out


def _fake_diarize_factory(segments: list[dict]):
    """Returns a sync function that ignores its args and returns ``segments``."""
    def _f(*_a, **_kw):
        return segments
    return _f


def _fake_identify_factory(pid: Optional[str], score: float):
    """Returns a sync function that returns the given (pid, score) regardless of args."""
    def _f(*_a, **_kw):
        return (pid, score)
    return _f


# ── 1. Pure function — no global state reads ─────────────────────────────


def test_voice_channel_imports_no_pipeline():
    """voice_channel.py must not transitively import pipeline. The hard
    architectural boundary from VOICE_VISION_INDEPENDENCE_PLAN.md.

    AST-based check (substring would false-positive on natural docstring
    references to the module name)."""
    import ast
    src = importlib.import_module("core.voice_channel")
    tree = ast.parse(open(src.__file__, encoding="utf-8").read())
    forbidden = {"pipeline"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in forbidden, (
                    f"voice_channel.py must NOT import {alias.name!r} "
                    f"(architectural boundary)"
                )
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            assert root not in forbidden, (
                f"voice_channel.py must NOT import from {node.module!r}"
            )


# ── 2. Mocked-out vision dependencies — function still works ──────────────


@pytest.mark.asyncio
async def test_voice_channel_works_when_vision_modules_unavailable(monkeypatch):
    """If something tried to make voice_channel transitively read vision
    state, this test would fail at function-call time. Block any import
    of vision-related modules and verify the call still succeeds."""
    # Surface a clear error if someone tries to import any vision-state
    # module from inside identify_speaker. Tests are run in a fresh module
    # state so the function path can't have already cached references.
    forbidden = ("pipeline", "core.vision")
    for mod in forbidden:
        monkeypatch.setitem(sys.modules, mod, None)  # importing blocks → ImportError

    claim = await identify_speaker(
        _audio(1.0), _gallery("alice"),
        utterance_duration=1.0,
        diarize_fn=_fake_diarize_factory([{"speaker_id": "alice", "speaker_score": 0.7}]),
        identify_fn=_fake_identify_factory("alice", 0.7),
    )
    assert claim.pid == "alice"
    assert claim.confidence == pytest.approx(0.7)


# ── 3. Each diarize-segment count handled correctly ──────────────────────


@pytest.mark.asyncio
async def test_voice_channel_handles_each_segment_count():
    """Single, two, and three-segment diarize outputs all surface as
    `n_diarize_segments` on the claim, with `raw_segment_scores`
    matching the input."""
    for n in (1, 2, 3):
        segs = [{"speaker_id": f"p{i}", "speaker_score": 0.3 + 0.1 * i} for i in range(n)]
        claim = await identify_speaker(
            _audio(1.0), _gallery("p0", "p1", "p2"),
            utterance_duration=1.0,
            diarize_fn=_fake_diarize_factory(segs),
            identify_fn=_fake_identify_factory("p0", 0.45),
        )
        assert claim.n_diarize_segments == n, f"expected n_diarize_segments={n}, got {claim.n_diarize_segments}"
        assert len(claim.raw_segment_scores) == n
        for got, want in zip(claim.raw_segment_scores, segs):
            assert got[0] == want["speaker_id"]
            assert got[1] == pytest.approx(want["speaker_score"])


# ── 4. Low-score / no-match returns pid=None ─────────────────────────────


@pytest.mark.asyncio
async def test_voice_channel_low_score_returns_none_pid():
    """When identify can't clear the threshold it returns (None, score).
    The voice channel surfaces that as `pid=None` — never guesses."""
    claim = await identify_speaker(
        _audio(1.0), _gallery("alice"),
        utterance_duration=1.0,
        diarize_fn=_fake_diarize_factory([{"speaker_id": None, "speaker_score": 0.05}]),
        identify_fn=_fake_identify_factory(None, 0.05),  # below threshold
    )
    assert claim.pid is None
    assert claim.confidence == pytest.approx(0.05)
    assert "no gallery match" in claim.reasoning


# ── 5. High-score case returns matched pid ────────────────────────────────


@pytest.mark.asyncio
async def test_voice_channel_high_score_returns_matched_pid():
    """A strong match surfaces as `pid=<the matched id>` with the
    confidence score from identify."""
    claim = await identify_speaker(
        _audio(2.0), _gallery("alice", "bob"),
        utterance_duration=2.0,
        diarize_fn=_fake_diarize_factory([{"speaker_id": "alice", "speaker_score": 0.78}]),
        identify_fn=_fake_identify_factory("alice", 0.78),
    )
    assert claim.pid == "alice"
    assert claim.confidence == pytest.approx(0.78)
    assert "alice" in claim.reasoning


# ── 6. Utterance duration carried through unchanged ───────────────────────


@pytest.mark.asyncio
async def test_voice_channel_carries_utterance_duration():
    """The `utterance_duration` arg passes through to the claim verbatim
    (not recomputed from buffer length, which can include silence pad)."""
    for dur in (0.3, 0.5, 1.0, 2.5):
        claim = await identify_speaker(
            _audio(dur), _gallery("alice"),
            utterance_duration=dur,
            diarize_fn=_fake_diarize_factory([]),
            identify_fn=_fake_identify_factory(None, 0.0),
        )
        assert claim.utterance_duration == pytest.approx(dur)


# ── 7. Empty gallery returns pid=None without raising ─────────────────────


@pytest.mark.asyncio
async def test_voice_channel_empty_gallery_returns_none():
    """No enrolled voices to match against → honest `(None, 0.0)`. The
    function must NOT raise, must NOT try to fall back to vision."""
    claim = await identify_speaker(
        _audio(1.0), {},   # empty gallery
        utterance_duration=1.0,
    )
    assert claim.pid is None
    assert claim.confidence == 0.0
    assert claim.n_diarize_segments == 0
    assert "empty" in claim.reasoning.lower()


# ── 8. Multi-segment raw scores populated ─────────────────────────────────


@pytest.mark.asyncio
async def test_voice_channel_multi_segment_raw_scores_populated():
    """For multi-voice turns, `raw_segment_scores` carries per-segment
    (pid, score) tuples so the reconciler can reason about each speaker
    independently — not just the top-level identify result."""
    segs = [
        {"speaker_id": "alice", "speaker_score": 0.71},
        {"speaker_id": "bob",   "speaker_score": 0.65},
        {"speaker_id": None,    "speaker_score": 0.10},  # unrecognized voice in segment
    ]
    claim = await identify_speaker(
        _audio(3.0), _gallery("alice", "bob"),
        utterance_duration=3.0,
        diarize_fn=_fake_diarize_factory(segs),
        identify_fn=_fake_identify_factory("alice", 0.71),
    )
    assert claim.n_diarize_segments == 3
    assert claim.raw_segment_scores == (
        ("alice", pytest.approx(0.71)),
        ("bob",   pytest.approx(0.65)),
        (None,    pytest.approx(0.10)),
    )
