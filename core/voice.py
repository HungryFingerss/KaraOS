"""
core/voice.py — Speaker verification using SpeechBrain ECAPA-TDNN.

Model: speechbrain/spkrec-ecapa-voxceleb
  - 192-dim L2-normalized embeddings, cosine similarity backend
  - 0.80% EER on VoxCeleb1-O (Cleaned) — production-grade accuracy
  - Same conceptual architecture as AdaFace: embeddings → cosine → threshold
  - ~80MB download on first use; cached in pretrained_models/

Verification threshold: 0.25 (EER operating point for cosine similarity).
Minimum reliable utterance length: ~1.5 seconds of actual speech.

Mirrors vision.py structure: lazy singleton load, thin wrapper, numpy I/O.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import asyncio
import time
import logging as _logging
import warnings as _warnings
import numpy as np
import torch
# P0.R6.Z D3.a RETIREMENT: from concurrent.futures import ThreadPoolExecutor
# was used exclusively by the retired _voice_diarize_executor pattern;
# subprocess isolation via core.heavy_worker replaces it.

from core.config import (
    MIC_SAMPLE_RATE, VOICE_EMBEDDING_DIM,
    DIARIZE_WINDOW_SECS, DIARIZE_HOP_SECS, DIARIZE_CHANGE_THRESH, DIARIZE_MIN_SECS,
    DIARIZATION_BACKEND, DIARIZATION_FALLBACK_ON_ERROR,
    DIARIZE_MIN_SEGMENT_SECS, DIARIZE_MIN_EMBED_SECS,
    VOICE_RECOGNITION_THRESHOLD,
)

# ── Apply SpeechBrain / torchaudio compat patches at IMPORT TIME ──────────────
# These must be in place before ANY speechbrain module is imported — even if
# some other module in the pipeline transitively imports SpeechBrain first.
_logging.getLogger("speechbrain").setLevel(_logging.ERROR)
_logging.getLogger("huggingface_hub").setLevel(_logging.ERROR)
_warnings.filterwarnings("ignore", category=FutureWarning, module="speechbrain")
_warnings.filterwarnings("ignore", category=UserWarning,   module="speechbrain")
_warnings.filterwarnings("ignore", message=".*unauthenticated.*")

_embedder = None   # SpeechBrain EncoderClassifier — lazy singleton

# P0.R6.Z D3.a RETIREMENT (2026-05-24): the dedicated diarization
# ThreadPoolExecutor pattern (_voice_diarize_executor + get_diarize_executor +
# shutdown_diarize_executor) was the Wave 3 Item 13 isolation mechanism for
# pyannote's sync C-extension call. Post-P0.R6.Z, pyannote inference runs in
# a ProcessPoolExecutor subprocess via `hw.run_heavy("pyannote_diarize", ...)`
# — the executor isolation moved one layer down into subprocess isolation.
# All 3 symbols hard-deleted per Q1 (a) lock. Pool shutdown is now handled
# by `hw.shutdown_all_pools(wait=True)` at process exit.


def _load_ecapa_patched(device: str = "cuda"):
    """Shared ECAPA loader — owns the FULL order-dependent hf_hub_download patch sequence.

    Canary #3 (2026-05-30): P0.R6.Y migrated ECAPA inference into a subprocess but left
    this compatibility patch behind in the main loader, so the subprocess `from_hparams`
    failed silently and `voice.embed` returned None on every call → empty voice gallery →
    the turn-55 Jagan→Lexi mis-rename. BOTH `load_speaker_embedder` (main) AND
    `heavy_worker._get_subprocess_ecapa` (subprocess) now call this single helper; each
    owns only its own singleton assignment. One source of truth for the patch.

    The two-phase ordering is LOAD-BEARING — do NOT flatten it:
      Phase 1 — patch the GLOBAL huggingface_hub.hf_hub_download (idempotent) BEFORE the
                speechbrain import (speechbrain binds the symbol at import time).
      Phase 2 — import EncoderClassifier (binds the now-patched global).
      Phase 3 — patch speechbrain.utils.fetching.hf_hub_download AFTER the import (that
                module captured its own reference to hf_hub_download at import time).
      Phase 4 — from_hparams.

    huggingface_hub 1.0+ vs SpeechBrain 1.x: (1) `use_auth_token` kwarg removed — strip it;
    (2) 404s raise RemoteEntryNotFoundError, not FileNotFoundError — convert to ValueError
    so SpeechBrain's existing `except` clause works.

    Returns the EncoderClassifier, or None (logged — A2: never silent) on failure. Lazy
    speechbrain/hf imports keep the subprocess import light (Q1 lock).
    """
    import functools
    import huggingface_hub as _hf

    # Phase 1 — GLOBAL patch, idempotent (sentinel so repeat calls don't wrap the wrapper).
    # huggingface_hub is always importable; the patch is the load-bearing pre-import step.
    if not getattr(_hf.hf_hub_download, "_dogai_patched", False):
        _orig_download = _hf.hf_hub_download

        @functools.wraps(_orig_download)
        def _patched_download(*args, **kwargs):
            kwargs.pop("use_auth_token", None)
            try:
                return _orig_download(*args, **kwargs)
            except Exception as _e:
                if type(_e).__name__ in ("RemoteEntryNotFoundError", "EntryNotFoundError") \
                        or "404" in str(_e):
                    raise ValueError(str(_e)) from _e
                raise

        _patched_download._dogai_patched = True
        _hf.hf_hub_download = _patched_download

    # Phases 2-4 — import + namespace patch + load, failure-guarded → None (logged).
    try:
        from speechbrain.inference.speaker import EncoderClassifier

        # Phase 3 — patch SpeechBrain's captured reference (after import).
        import speechbrain.utils.fetching as _sbfetch
        if hasattr(_sbfetch, "hf_hub_download") \
                and not getattr(_sbfetch.hf_hub_download, "_dogai_patched", False):
            _sbfetch.hf_hub_download = _hf.hf_hub_download

        return EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="pretrained_models/spkrec-ecapa-voxceleb",
            run_opts={"device": device},
        )
    except Exception as e:
        # A2: this swallow hid Canary #3 for a week — log type+message, never silent.
        print(f"[Voice] ECAPA load failed: {type(e).__name__}: {e}")
        return None


def load_speaker_embedder(device: str = "cuda") -> None:
    """Load ECAPA-TDNN model into the main-process singleton. Call once at startup."""
    global _embedder
    if _embedder is not None:
        return
    print("[Voice] Loading ECAPA-TDNN speaker embedder...")
    t0 = time.time()
    _embedder = _load_ecapa_patched(device)
    if _embedder is not None:
        print(f"[Voice] ECAPA-TDNN ready — {time.time() - t0:.1f}s")
    else:
        print("[Voice] WARNING: Could not load speaker embedder — voice ID disabled")


async def embed(audio: np.ndarray, sample_rate: int = MIC_SAMPLE_RATE) -> np.ndarray | None:
    """Extract L2-normalized 192-dim speaker embedding from a mono float32 audio array.

    P0.R6.Y migration: inference offloaded to ProcessPoolExecutor subprocess
    via ``hw.run_heavy("ecapa_embed", ...)``. The subprocess holds the
    persistent SpeechBrain EncoderClassifier singleton (loaded once on first
    call); the asyncio loop is not blocked during the ~50-200ms inference.
    Worker performs the L2-normalization subprocess-side per Q4 (b) lock;
    main process body just deserializes + detaches buffer for downstream
    mutation safety.

    Returns None if the utterance is too short OR the worker returns None
    (model load failure, inference crash). Minimum reliable length: 1.5
    seconds (~24 000 samples at 16 kHz) — gated subprocess-side.
    """
    if len(audio) == 0:
        return None
    import core.heavy_worker as hw  # noqa: PLC0415

    emb_bytes = await hw.run_heavy(
        "ecapa_embed",
        hw.ecapa_embed_worker,
        audio.tobytes(),
        audio.shape,
        audio.dtype.name,
        sample_rate,
    )
    if emb_bytes is None:
        return None
    emb = np.frombuffer(emb_bytes, dtype=np.float32)
    return emb.copy()  # detach from buffer (mutable downstream)


async def _diarize_ecapa_valley(
    audio:         np.ndarray,
    voice_gallery: dict[str, np.ndarray],
    threshold:     float = VOICE_RECOGNITION_THRESHOLD,
    sample_rate:   int   = MIC_SAMPLE_RATE,
) -> list[dict]:
    """Detect a speaker-change boundary using an ECAPA-TDNN sliding window.

    **Legacy backend (Phase 1 implementation).** P2.3 renamed this from
    ``diarize`` to ``_diarize_ecapa_valley`` so the new ``diarize`` at
    module scope can dispatch between pyannote (Phase 2 default) and this
    ECAPA-valley fallback based on ``DIARIZATION_BACKEND``. Kept for the
    fallback path and for the 2-speaker common case where pyannote's
    pipeline overhead isn't justified.

    Slides a 0.5-second window across ``audio`` in 0.25-second hops, computes
    L2-normalized embeddings for each window, and finds the deepest cosine-
    similarity valley between adjacent windows.  If the valley falls below
    DIARIZE_CHANGE_THRESH (0.70) the utterance is split there and each half is
    identified against ``voice_gallery``.

    Returns a list of segment dicts:
        [{"start_sample": int, "end_sample": int,
          "speaker_id": str|None, "speaker_score": float}, ...]
    Returns [] when audio is too short, the embedder is unavailable, or the
    utterance contains only one speaker. ``speaker_label`` is NOT present
    on the return from this function — only the pyannote backend produces
    pipeline-local SPEAKER_XX labels; the dispatch in ``diarize`` fills
    ``speaker_label=None`` on fallback-path returns for uniform shape.
    """
    if len(audio) < int(DIARIZE_MIN_SECS * sample_rate):
        return []

    window_samples = int(DIARIZE_WINDOW_SECS * sample_rate)
    hop_samples    = int(DIARIZE_HOP_SECS    * sample_rate)

    # ── Compute per-window embeddings ────────────────────────────────────────
    # P0.R6.Y D3 cascade: embed() is now async + dispatches to subprocess
    # via hw.run_heavy. Worker-side _get_subprocess_ecapa() returns None on
    # load failure (P0.R1 D1 contract preserved) — no main-process embedder
    # singleton check needed; embed() returns None on any failure path.
    embeddings:    list[np.ndarray] = []
    window_starts: list[int]        = []
    pos = 0
    while pos + window_samples <= len(audio):
        emb = await embed(audio[pos : pos + window_samples], sample_rate)
        if emb is not None:
            embeddings.append(emb)
            window_starts.append(pos)
        pos += hop_samples

    if len(embeddings) < 2:
        return []

    # ── Find the deepest cosine valley (most likely speaker-change point) ────
    sims = [
        float(np.dot(embeddings[i - 1], embeddings[i]))
        for i in range(1, len(embeddings))
    ]
    valley_idx = int(np.argmin(sims))
    valley_sim  = sims[valley_idx]

    if valley_sim >= DIARIZE_CHANGE_THRESH:
        return []   # no clear speaker change

    # ── Compute boundary sample (midpoint between the two valley windows) ────
    w_a      = window_starts[valley_idx]
    w_b      = window_starts[valley_idx + 1]
    boundary = (w_a + window_samples // 2 + w_b) // 2
    boundary = max(window_samples, min(boundary, len(audio) - window_samples))

    # ── Identify each segment against the voice gallery ──────────────────────
    segments = []
    for start_s, end_s in [(0, boundary), (boundary, len(audio))]:
        seg_audio            = audio[start_s:end_s]
        # Pre-P1 Bundle 5 MF7: identify() now returns 3-tuple; diarize only needs pid+score.
        pid, score, _        = await identify(seg_audio, voice_gallery, threshold, sample_rate)
        segments.append({
            "start_sample":  start_s,
            "end_sample":    end_s,
            "speaker_id":    pid,
            "speaker_score": score,
        })

    return segments


# ── VISION_ROADMAP Phase 2 — pyannote-backed diarization ────────────────────
# P0.R6.Z D3.a RETIREMENT (2026-05-24): the main-process `_pyannote_pipeline`
# singleton + `_load_pyannote_pipeline()` lazy loader retired in favor of
# subprocess-side singleton at `core/heavy_worker.py::_get_subprocess_pyannote()`.
# The pyannote Pipeline now lives entirely in the ProcessPoolExecutor worker
# subprocess; main process never imports `pyannote.audio` post-P0.R6.Z.
# `_diarize_pyannote()` body below dispatches to `hw.run_heavy("pyannote_diarize",
# ...)` which routes through the worker subprocess.

# Fallback counter — bumped every time a pyannote invocation degrades to
# _diarize_ecapa_valley (either because the pipeline failed to load, or
# because a runtime error fired during inference + DIARIZATION_FALLBACK_ON_ERROR
# is True). Reviewer's Session 88 observability ask: "Frequent fallback in
# production = pyannote has a runtime bug we haven't caught."
_diarize_fallback_count: int = 0


def get_diarize_stats() -> dict:
    """Snapshot of diarization counters. Used by future Phase 5 drift
    detection to flag a climbing fallback rate before it becomes a silent
    regression. Returns copies so callers can't mutate the internal state."""
    return {"fallback_count": _diarize_fallback_count}


async def _diarize_pyannote(
    audio:         np.ndarray,
    voice_gallery: dict[str, np.ndarray],
    threshold:     float = VOICE_RECOGNITION_THRESHOLD,
    sample_rate:   int   = MIC_SAMPLE_RATE,
) -> list[dict]:
    """Pyannote-backed diarization. See ``diarize()`` for the public
    contract; this is the backend implementation.

    Reviewer's Session 88 per-segment edge-case policy:
      * segment < DIARIZE_MIN_SEGMENT_SECS → drop (too short for ECAPA)
      * segment 0.5s–1.0s → keep with ``speaker_id=None`` (kept in output
        so pyannote's segmentation is preserved; attribution skipped
        because ECAPA needs ≥1.0s for a reliable embedding)
      * segment ≥1.0s → run ECAPA ``identify()`` against ``voice_gallery``
      * empty voice_gallery → all segments get ``speaker_id=None``
        (still useful — segmentation info drives multi-speaker transcribe)
      * pure silence (no pyannote segments) → return []
      * pyannote runtime error → log + fall back to ``_diarize_ecapa_valley``
        when ``DIARIZATION_FALLBACK_ON_ERROR=True`` (default), else []

    CRITICAL caveat: pyannote's ``SPEAKER_XX`` labels are
    PIPELINE-LOCAL. ``SPEAKER_00`` in one call is NOT the same person as
    ``SPEAKER_00`` in the next call. Labels only differentiate speakers
    WITHIN a single ``diarize()`` invocation. Cross-chunk speaker
    identity comes from ``speaker_id`` (ECAPA gallery match), never from
    ``speaker_label``."""
    global _diarize_fallback_count
    if len(audio) == 0:
        return []

    # P0.R6.Z D3.b body migration: pyannote inference dispatches to the
    # heavy-worker ProcessPoolExecutor pool via `hw.run_heavy(
    # "pyannote_diarize", ...)`. Worker subprocess holds the persistent
    # Pipeline singleton (loaded once per subprocess lifetime via
    # `_get_subprocess_pyannote()`) AND serializes Annotation →
    # list[tuple[float, float, str]] BEFORE returning per Q2 (a) lock.
    # Main process iterates simple tuples; no pyannote imports in main.
    # Q9 (a) lock: BrokenProcessPool from subprocess crash lands in the
    # outer except Exception below; pool auto-restarts on next call.
    import core.heavy_worker as hw  # noqa: PLC0415

    try:
        segments_raw = await hw.run_heavy(
            "pyannote_diarize",
            hw.pyannote_diarize_worker,
            audio.tobytes(),
            audio.shape,
            audio.dtype.name,
            sample_rate,
        )
    except Exception as e:
        print(f"[Voice] pyannote diarize runtime error: {type(e).__name__}: {e}")
        if DIARIZATION_FALLBACK_ON_ERROR:
            _diarize_fallback_count += 1
            print(f"[Voice] WARN diarize fallback (runtime) — ecapa_valley "
                  f"for this call (fallback #{_diarize_fallback_count})")
            return await _diarize_ecapa_valley(audio, voice_gallery, threshold, sample_rate)
        return []

    if segments_raw is None:
        # Worker returned None — pyannote pipeline load failure in
        # subprocess (cold HF cache fail OR vendored fork import broken).
        # Preserves P0.R1 D1 None-return fallback contract.
        if DIARIZATION_FALLBACK_ON_ERROR:
            _diarize_fallback_count += 1
            print(f"[Voice] WARN diarize fallback (load-fail) — "
                  f"pyannote unavailable, using ecapa_valley "
                  f"(fallback #{_diarize_fallback_count})")
            return await _diarize_ecapa_valley(audio, voice_gallery, threshold, sample_rate)
        return []

    segments: list[dict] = []
    for start_secs, end_secs, label in segments_raw:
        dur = end_secs - start_secs
        if dur < DIARIZE_MIN_SEGMENT_SECS:
            # Below the ECAPA-noise floor — pyannote's own confidence is
            # usually already low here, and our downstream needs ≥0.5s to
            # produce any useful signal. Drop.
            continue
        start_s = int(start_secs * sample_rate)
        end_s   = min(int(end_secs * sample_rate), len(audio))
        if dur < DIARIZE_MIN_EMBED_SECS:
            # Pyannote saw a valid segment but it's too short for a
            # reliable ECAPA embedding. Keep the segment (the calling
            # pipeline may still transcribe it and route via other
            # signals) but mark speaker_id=None so downstream doesn't
            # trust a noisy voice-gallery match.
            segments.append({
                "start_sample":  start_s,
                "end_sample":    end_s,
                "speaker_id":    None,
                "speaker_score": 0.0,
                "speaker_label": label,
            })
            continue
        seg_audio  = audio[start_s:end_s]
        # Pre-P1 Bundle 5 MF7: identify() now returns 3-tuple; diarize only needs pid+score.
        pid, score, _ = await identify(seg_audio, voice_gallery, threshold, sample_rate)
        segments.append({
            "start_sample":  start_s,
            "end_sample":    end_s,
            "speaker_id":    pid,
            "speaker_score": score,
            "speaker_label": label,
        })
    return segments


async def diarize(
    audio:         np.ndarray,
    voice_gallery: dict[str, np.ndarray],
    threshold:     float = VOICE_RECOGNITION_THRESHOLD,
    sample_rate:   int   = MIC_SAMPLE_RATE,
) -> list[dict]:
    """Public dispatcher — selects the diarization backend based on
    ``DIARIZATION_BACKEND`` config (``"pyannote"`` default as of Session 88;
    ``"ecapa_valley"`` is the legacy 2-speaker binary-split backend kept for
    emergencies and no-token environments).

    Returns a list of segment dicts:
        [{"start_sample":  int,
          "end_sample":    int,
          "speaker_id":    str | None,   # ECAPA gallery match, None if unmatched
          "speaker_score": float,        # cosine vs best gallery entry (0.0 if none)
          "speaker_label": str | None},  # pyannote SPEAKER_XX or None on ECAPA fallback
         ...]

    ``speaker_label`` is ADDITIVE vs the legacy contract — existing
    callers that only read ``start_sample`` / ``end_sample`` /
    ``speaker_id`` / ``speaker_score`` work unchanged.

    WARNING: ``speaker_label`` values are pipeline-local per call. Do NOT
    use them for cross-call speaker identity. Use ``speaker_id`` (ECAPA
    gallery match) for that. See ``_diarize_pyannote`` for the full
    caveat.

    Backend dispatch is lazy: with ``backend="pyannote"``, the pyannote
    pipeline loads on first invocation (~2-3s + 500 MB one-time download).
    Subsequent calls reuse the cached singleton."""
    if DIARIZATION_BACKEND == "pyannote":
        segments = await _diarize_pyannote(audio, voice_gallery, threshold, sample_rate)
        _backend_used = "pyannote"
    elif DIARIZATION_BACKEND == "ecapa_valley":
        segments = await _diarize_ecapa_valley(audio, voice_gallery, threshold, sample_rate)
        _backend_used = "ecapa_valley"
    else:
        print(f"[Voice] Unknown DIARIZATION_BACKEND {DIARIZATION_BACKEND!r} — "
              f"falling back to ecapa_valley")
        segments = await _diarize_ecapa_valley(audio, voice_gallery, threshold, sample_rate)
        _backend_used = "ecapa_valley(unknown-backend-fallback)"
    # Normalize shape: fallback/legacy paths don't produce ``speaker_label``,
    # but callers should see a uniform dict regardless of which backend ran.
    for s in segments:
        s.setdefault("speaker_label", None)
    # Observability: one line per call so operators can eyeball that
    # pyannote is actually firing in prod (vs silently falling back every
    # turn). Reviewer's Session 88 ask.
    print(f"[Voice] diarize: {_backend_used} returned {len(segments)} segment(s)")
    return segments


async def identify(
    audio:         np.ndarray,
    voice_gallery: dict[str, np.ndarray],
    threshold:     float,
    sample_rate:   int = MIC_SAMPLE_RATE,
) -> tuple[str | None, float, bool]:
    """1:N speaker identification against the in-memory voice gallery.

    P0.R6.Y D3 cascade: embed() is now async (offloads to ProcessPoolExecutor
    subprocess); identify() becomes async to await it.

    Returns `(person_id, cosine_score, is_no_signal)`. `is_no_signal=True`
    ONLY when the embedding failed or the gallery was empty (score forced to
    0.0); `False` for both real matches and gallery-misses (score is a genuine
    cosine, possibly negative).
    """
    emb = await embed(audio, sample_rate)
    if emb is None or not voice_gallery:
        return None, 0.0, True

    best_id, best_score = None, -1.0
    for person_id, profile_emb in voice_gallery.items():
        sim = float(np.dot(emb, profile_emb))   # cosine sim on L2-normalized vectors
        if sim > best_score:
            best_score = sim
            best_id    = person_id

    if best_score >= threshold:
        return best_id, best_score, False
    return None, best_score, False
