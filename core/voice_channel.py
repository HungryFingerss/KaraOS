"""
core/voice_channel.py — Phase 1 of the Voice/Vision Independence refactor.

A pure speaker-identification function. Reads audio + voice gallery,
outputs a structured `IdentityClaim`. Zero reads of vision state. Zero
imports from `pipeline.py`. Zero writes to shared mutable structures.

Architectural target (from VOICE_VISION_INDEPENDENCE_PLAN.md):

    audio buf + voice_gallery
            │
            ▼
    ┌─────────────────────┐
    │   VOICE CHANNEL     │  ── this module
    │  identify_speaker() │
    └─────────────────────┘
            │
            ▼
       IdentityClaim {
         pid: str|None,
         confidence: float,
         n_diarize_segments: int,
         utterance_duration: float,
         reasoning: str,
         raw_segment_scores: [(pid, score), ...]
       }

The reconciler (Phase 3) consumes this claim alongside a `PresenceState`
(Phase 2) to make routing decisions. This module never makes routing
decisions itself — it only describes what it heard.

Hard rule: if `identify_speaker` ever needs visual context to make a
decision, that's a bug. Return a low-confidence claim and let the
reconciler decide.

Phase 1 scope: extract the function + run in shadow mode alongside the
current coupled routing. No production change. After 1-2 weeks of
divergence-log review, graduate to Phase 2 (vision channel extraction).
"""
from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

import numpy as np

from core.config import MIC_SAMPLE_RATE, VOICE_RECOGNITION_THRESHOLD


@dataclass(frozen=True)
class IdentityClaim:
    """What the voice channel believes about the current utterance.

    Fields:
        pid: matched person_id from the voice gallery, or None if no match
            cleared the threshold. Never guesses — `None` is honest output.
        confidence: best ECAPA cosine similarity, 0.0-1.0 (typically; can be
            slightly negative on near-orthogonal vectors).
        n_diarize_segments: how many segments pyannote returned. 1 = single
            speaker; 2+ = multi-voice (often two speakers, sometimes audio
            quirks of one speaker — the reconciler decides what to do).
        utterance_duration: seconds of actual speech in the audio buffer.
            Caller passes this; we don't recompute it from the buffer
            because length includes pre-roll/silence padding.
        reasoning: human-readable diagnostic string for logging / debug.
        raw_segment_scores: per-segment (pid, score) tuples. Useful for
            multi-segment turns where the top-level pid + confidence is
            just the best across segments.
    """
    pid:                  Optional[str]
    confidence:           float
    n_diarize_segments:   int
    utterance_duration:   float
    reasoning:            str
    raw_segment_scores:   tuple[tuple[Optional[str], float], ...] = ()


# Type alias for the injectable diarize / identify functions. Tests can
# replace these with synchronous fakes; production passes the real
# `core.voice.diarize` and `core.voice.identify`.
_DiarizeFn = Callable[..., list[dict]]
_IdentifyFn = Callable[..., tuple[Optional[str], float]]


async def _maybe_run_in_executor(fn: Callable, *args, **kwargs):
    """Run a possibly-blocking function on the default executor when
    we're inside an event loop. Allows callers to pass either sync
    functions (real `core.voice.diarize` is sync) or async functions
    (test fakes can be `async def`)."""
    if inspect.iscoroutinefunction(fn):
        return await fn(*args, **kwargs)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


async def identify_speaker(
    audio_buf:           np.ndarray,
    voice_gallery:       dict[str, np.ndarray],
    *,
    utterance_duration:  float,
    threshold:           float = VOICE_RECOGNITION_THRESHOLD,
    sample_rate:         int = MIC_SAMPLE_RATE,
    diarize_fn:          "_DiarizeFn | None" = None,
    identify_fn:         "_IdentifyFn | None" = None,
) -> IdentityClaim:
    """Pure speaker identification — runs diarize + identify against the
    voice gallery, returns a structured `IdentityClaim`.

    Hard rule (Phase 1, VOICE_VISION_INDEPENDENCE_PLAN.md): this function
    MAY NOT import from `pipeline.py`, MAY NOT read `persons_in_frame`,
    MAY NOT call `_face_in_frame`, MAY NOT know about visual scene
    state. Routing decisions belong in the reconciler (Phase 3); this
    function only describes what it heard.

    Parameters
    ----------
    audio_buf:
        Float32 mono audio at `sample_rate`. Already silence-trimmed by
        the caller (pipeline's VAD path).
    voice_gallery:
        `{person_id: np.ndarray (192-dim L2-normalized ECAPA mean)}`. Empty
        dict is allowed — yields a `pid=None, confidence=0.0` claim.
    utterance_duration:
        Seconds of actual speech in `audio_buf`. Caller-provided because
        the buffer's length includes silence padding. Used for the
        claim's `utterance_duration` field; reconciler reads it for
        latency / quality gating.
    threshold:
        Min cosine sim for `identify` to claim a match. Defaults to
        production VOICE_RECOGNITION_THRESHOLD.
    sample_rate:
        Audio sample rate. Defaults to MIC_SAMPLE_RATE (16 kHz).
    diarize_fn / identify_fn:
        Injectable for tests. Default to `core.voice.diarize` /
        `core.voice.identify` lazily-imported on first call.

    Returns
    -------
    IdentityClaim
        Always returns a claim — never raises. On any internal error
        (bad audio, gallery problems, model unavailable), returns a
        `pid=None, confidence=0.0` claim with `reasoning` describing
        the failure.
    """
    # Lazy default imports. We import core.voice (the recognition layer)
    # but NEVER pipeline.py. core.voice itself imports nothing from
    # pipeline, so this transitive boundary is clean.
    if diarize_fn is None or identify_fn is None:
        from core import voice as _voice_mod
        if diarize_fn is None:
            diarize_fn = _voice_mod.diarize
        if identify_fn is None:
            identify_fn = _voice_mod.identify

    if audio_buf is None:
        return IdentityClaim(
            pid=None, confidence=0.0,
            n_diarize_segments=0, utterance_duration=float(utterance_duration),
            reasoning="audio_buf is None",
        )

    if not voice_gallery:
        # No gallery means there's nothing to match against. Return an
        # honest "I don't know" rather than guessing or raising.
        return IdentityClaim(
            pid=None, confidence=0.0,
            n_diarize_segments=0, utterance_duration=float(utterance_duration),
            reasoning="voice_gallery is empty",
        )

    # ── 1. Diarize: pyannote returns 1 / 2+ segments ───────────────────
    try:
        segments = await _maybe_run_in_executor(
            diarize_fn, audio_buf, voice_gallery, threshold, sample_rate
        )
    except Exception as e:
        return IdentityClaim(
            pid=None, confidence=0.0,
            n_diarize_segments=0, utterance_duration=float(utterance_duration),
            reasoning=f"diarize failed: {type(e).__name__}: {e!r}",
        )
    n_segments = len(segments) if segments else 0
    raw_scores: list[tuple[Optional[str], float]] = [
        (s.get("speaker_id"), float(s.get("speaker_score") or 0.0))
        for s in (segments or [])
    ]

    # ── 2. ECAPA top-level identify on the whole buffer ────────────────
    try:
        pid, score = await _maybe_run_in_executor(
            identify_fn, audio_buf, voice_gallery, threshold, sample_rate
        )
    except Exception as e:
        return IdentityClaim(
            pid=None, confidence=0.0,
            n_diarize_segments=n_segments,
            utterance_duration=float(utterance_duration),
            reasoning=f"identify failed: {type(e).__name__}: {e!r}",
            raw_segment_scores=tuple(raw_scores),
        )

    # ── 3. Build the claim ─────────────────────────────────────────────
    if pid is None:
        reason = (
            f"no gallery match (best score {float(score):.3f} < threshold {threshold:.2f})"
            if score
            else "no gallery match (score 0.0)"
        )
    else:
        reason = f"matched {pid!r} at score {float(score):.3f}"
    return IdentityClaim(
        pid=pid,
        confidence=float(score),
        n_diarize_segments=n_segments,
        utterance_duration=float(utterance_duration),
        reasoning=reason,
        raw_segment_scores=tuple(raw_scores),
    )
