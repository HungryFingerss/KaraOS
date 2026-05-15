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
import time
import logging as _logging
import warnings as _warnings
import numpy as np
import torch
from concurrent.futures import ThreadPoolExecutor

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

import torchaudio as _ta
if not hasattr(_ta, "list_audio_backends"):
    # torchaudio 2.6+ removed list_audio_backends; SpeechBrain 1.x still calls it.
    # Session 89 fix: originally this returned ``[]`` on the theory that
    # SpeechBrain would skip file-backend setup. That broke pyannote.audio
    # (Session 88 Phase 2): pyannote's ``io.py:214`` does
    # ``backends[0]`` when "soundfile" isn't present → IndexError on an
    # empty list. Return ``['sox_io']`` instead — matches the sentinel our
    # file-level ``tests/patch_pyannote_io.py`` uses. SpeechBrain treats
    # any non-empty backend list as "something is available, proceed"
    # (only actually uses it when loading audio FROM FILES, which ECAPA-
    # TDNN in our pipeline never does — we pass in-memory tensors).
    _ta.list_audio_backends = lambda: ["sox_io"]

_embedder = None   # SpeechBrain EncoderClassifier — lazy singleton

# Wave 3 Item 13: dedicated single-threaded executor for diarization.
# Isolates 100-500ms pyannote budget from the default executor where TTS,
# embedder, FAISS, and SQLite all share 12 worker threads.
# max_workers=1: pyannote isn't safe for concurrent calls (one Pipeline
# instance, GPU contention). Lazy singleton — not created at import so
# test environments without pyannote don't pay construction cost.
_voice_diarize_executor: "ThreadPoolExecutor | None" = None


def get_diarize_executor() -> ThreadPoolExecutor:
    """Return the dedicated diarization executor, creating it on first call."""
    global _voice_diarize_executor
    if _voice_diarize_executor is None:
        _voice_diarize_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="voice-diarize",
        )
    return _voice_diarize_executor


def shutdown_diarize_executor() -> None:
    """Shut down the dedicated diarization executor. Call from pipeline shutdown."""
    global _voice_diarize_executor
    if _voice_diarize_executor is not None:
        _voice_diarize_executor.shutdown(wait=False)
        _voice_diarize_executor = None


def load_speaker_embedder(device: str = "cuda") -> None:
    """Load ECAPA-TDNN model. Call once at pipeline startup."""
    global _embedder
    if _embedder is not None:
        return
    try:
        # torchaudio 2.6+ removed list_audio_backends; SpeechBrain 1.x still calls it.
        # (Also patched at module scope above, but guard here in case voice.py is
        # imported after some other module already triggered a SpeechBrain import.)
        # Session 89: must return ``['sox_io']`` — see module-level comment above
        # for the Phase 2 / pyannote interaction that forced this.
        if not hasattr(_ta, "list_audio_backends"):
            _ta.list_audio_backends = lambda: ["sox_io"]

        # huggingface_hub 1.0+ has two breaking changes vs SpeechBrain 1.x:
        # 1. use_auth_token kwarg removed — strip it transparently.
        # 2. 404s now raise RemoteEntryNotFoundError instead of FileNotFoundError —
        #    SpeechBrain's try/except FileNotFoundError misses it and crashes.
        #    Patch both issues in a single wrapper.
        import huggingface_hub as _hf
        import functools
        _orig_download = _hf.hf_hub_download

        @functools.wraps(_orig_download)
        def _patched_download(*args, **kwargs):
            kwargs.pop("use_auth_token", None)
            try:
                return _orig_download(*args, **kwargs)
            except Exception as _e:
                # huggingface_hub 1.x raises RemoteEntryNotFoundError for 404s.
                # SpeechBrain 1.x catches ValueError for missing optional files
                # (e.g. custom.py). Convert so the existing except clause works.
                if type(_e).__name__ in ("RemoteEntryNotFoundError", "EntryNotFoundError") \
                        or "404" in str(_e):
                    raise ValueError(str(_e)) from _e
                raise

        _hf.hf_hub_download = _patched_download

        from speechbrain.inference.speaker import EncoderClassifier

        # Also patch the local reference inside SpeechBrain's fetching module,
        # which captured hf_hub_download at import time into its own namespace.
        import speechbrain.utils.fetching as _sbfetch
        if hasattr(_sbfetch, "hf_hub_download"):
            _sbfetch.hf_hub_download = _patched_download

        print("[Voice] Loading ECAPA-TDNN speaker embedder...")
        t0 = time.time()
        _embedder = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="pretrained_models/spkrec-ecapa-voxceleb",
            run_opts={"device": device},
        )
        print(f"[Voice] ECAPA-TDNN ready — {time.time() - t0:.1f}s")
    except Exception as e:
        print(f"[Voice] WARNING: Could not load speaker embedder ({e}) — voice ID disabled")
        _embedder = None


def embed(audio: np.ndarray, sample_rate: int = MIC_SAMPLE_RATE) -> np.ndarray | None:
    """Extract L2-normalized 192-dim speaker embedding from a mono float32 audio array.

    Returns None if the embedder is unavailable or the utterance is too short.
    Minimum reliable length: 1.5 seconds (~24 000 samples at 16 kHz).
    """
    if _embedder is None:
        return None
    if len(audio) < sample_rate * 1.5:
        return None

    # Resample to 16 kHz if the mic sample rate differs
    if sample_rate != 16000:
        import torchaudio
        audio_t = torch.from_numpy(audio.astype(np.float32))
        audio   = torchaudio.functional.resample(audio_t, sample_rate, 16000).numpy()

    signal = torch.from_numpy(audio.astype(np.float32)).unsqueeze(0)  # [1, T]
    try:
        with torch.no_grad():
            emb = _embedder.encode_batch(signal)   # [1, 1, 192]
        emb  = emb.squeeze().cpu().numpy()          # [192]
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        return emb.astype(np.float32)
    except Exception as e:
        print(f"[Voice] Embedding failed: {e}")
        return None


def _diarize_ecapa_valley(
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
    if _embedder is None:
        return []
    if len(audio) < int(DIARIZE_MIN_SECS * sample_rate):
        return []

    window_samples = int(DIARIZE_WINDOW_SECS * sample_rate)
    hop_samples    = int(DIARIZE_HOP_SECS    * sample_rate)

    # ── Compute per-window embeddings ────────────────────────────────────────
    embeddings:    list[np.ndarray] = []
    window_starts: list[int]        = []
    pos = 0
    while pos + window_samples <= len(audio):
        emb = embed(audio[pos : pos + window_samples], sample_rate)
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
        pid, score           = identify(seg_audio, voice_gallery, threshold, sample_rate)
        segments.append({
            "start_sample":  start_s,
            "end_sample":    end_s,
            "speaker_id":    pid,
            "speaker_score": score,
        })

    return segments


# ── VISION_ROADMAP Phase 2 — pyannote-backed diarization ────────────────────
# Module-level singleton (matches load_speaker_embedder / MiniFASNet / Whisper
# lazy-loading pattern used everywhere else in core/*). First diarize() call
# with backend="pyannote" triggers load; subsequent calls reuse the cached
# pipeline. NOT loaded at module import — saves ~2-3s + ~500 MB of GPU
# allocation when pyannote isn't actually invoked.
_pyannote_pipeline = None

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


def _load_pyannote_pipeline():
    """Lazy loader for pyannote's speaker-diarization-3.1 pipeline.

    First call: imports pyannote.audio, loads the pipeline (downloads
    ~500 MB on first-ever run via HF_TOKEN, cached thereafter), transfers
    to CUDA if available. Subsequent calls return the cached singleton.

    Returns the Pipeline instance on success, or None on failure (missing
    HF_TOKEN, gated-repo access denied, or import error). Failure is
    logged; callers should treat None as "pyannote unavailable — fall back
    to ``_diarize_ecapa_valley``".

    Requires the torchaudio compat patches in
    ``tests/patch_pyannote_io.py`` to be applied before any pyannote
    import. The patches cover torchaudio 2.9+ API removals + torch 2.6+
    ``weights_only`` default change — see the patch file docstring and
    Session 88 CLAUDE.md entry."""
    global _pyannote_pipeline
    if _pyannote_pipeline is not None:
        return _pyannote_pipeline
    import os
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        print("[Voice] HF_TOKEN missing — pyannote pipeline cannot load "
              "(gated-model auth). Falling back to ECAPA-valley backend.")
        return None
    print("[Voice] Loading pyannote speaker-diarization-3.1...")
    t0 = time.time()
    try:
        from pyannote.audio import Pipeline
        _pyannote_pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token,
        )
    except Exception as e:
        # Session 89 fix: the original lazy loader logged only the exception
        # name + message, which made the in-pipeline "IndexError: list index
        # out of range" un-diagnosable. Log the full traceback so operators
        # can see which pyannote / torchaudio / speechbrain call actually
        # raised. Still returns None so the fallback chain in
        # _diarize_pyannote handles gracefully — logging, not raising.
        import traceback as _tb
        print(f"[Voice] pyannote load failed: {type(e).__name__}: {e}")
        print(f"[Voice] TRACEBACK:\n{_tb.format_exc()}")
        print(f"[Voice] Tip: run ``python tests/patch_pyannote_io.py`` if you "
              f"just reinstalled pyannote.audio.")
        return None
    if torch.cuda.is_available():
        _pyannote_pipeline.to(torch.device("cuda"))
    print(f"[Voice] pyannote ready — {time.time() - t0:.1f}s")
    return _pyannote_pipeline


def _diarize_pyannote(
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
    pipeline = _load_pyannote_pipeline()
    if pipeline is None:
        if DIARIZATION_FALLBACK_ON_ERROR:
            _diarize_fallback_count += 1
            print(f"[Voice] WARN diarize fallback (load-fail) — "
                  f"pyannote unavailable, using ecapa_valley "
                  f"(fallback #{_diarize_fallback_count})")
            return _diarize_ecapa_valley(audio, voice_gallery, threshold, sample_rate)
        return []
    if len(audio) == 0:
        return []

    # Pyannote accepts an in-memory waveform dict. Avoids torchcodec /
    # FFmpeg entirely — the exact path documented as supported when
    # torchcodec's built-in audio decoding fails.
    waveform = torch.from_numpy(audio.astype(np.float32)).unsqueeze(0)
    if torch.cuda.is_available():
        waveform = waveform.to(torch.device("cuda"))

    try:
        annotation = pipeline({"waveform": waveform, "sample_rate": sample_rate})
    except Exception as e:
        print(f"[Voice] pyannote diarize runtime error: {type(e).__name__}: {e}")
        if DIARIZATION_FALLBACK_ON_ERROR:
            _diarize_fallback_count += 1
            print(f"[Voice] WARN diarize fallback (runtime) — ecapa_valley "
                  f"for this call (fallback #{_diarize_fallback_count})")
            return _diarize_ecapa_valley(audio, voice_gallery, threshold, sample_rate)
        return []

    segments: list[dict] = []
    for segment, _, label in annotation.itertracks(yield_label=True):
        dur = segment.end - segment.start
        if dur < DIARIZE_MIN_SEGMENT_SECS:
            # Below the ECAPA-noise floor — pyannote's own confidence is
            # usually already low here, and our downstream needs ≥0.5s to
            # produce any useful signal. Drop.
            continue
        start_s = int(segment.start * sample_rate)
        end_s   = min(int(segment.end * sample_rate), len(audio))
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
        pid, score = identify(seg_audio, voice_gallery, threshold, sample_rate)
        segments.append({
            "start_sample":  start_s,
            "end_sample":    end_s,
            "speaker_id":    pid,
            "speaker_score": score,
            "speaker_label": label,
        })
    return segments


def diarize(
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
        segments = _diarize_pyannote(audio, voice_gallery, threshold, sample_rate)
        _backend_used = "pyannote"
    elif DIARIZATION_BACKEND == "ecapa_valley":
        segments = _diarize_ecapa_valley(audio, voice_gallery, threshold, sample_rate)
        _backend_used = "ecapa_valley"
    else:
        print(f"[Voice] Unknown DIARIZATION_BACKEND {DIARIZATION_BACKEND!r} — "
              f"falling back to ecapa_valley")
        segments = _diarize_ecapa_valley(audio, voice_gallery, threshold, sample_rate)
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


def identify(
    audio:         np.ndarray,
    voice_gallery: dict[str, np.ndarray],
    threshold:     float,
    sample_rate:   int = MIC_SAMPLE_RATE,
) -> tuple[str | None, float]:
    """1:N speaker identification against the in-memory voice gallery.

    Returns (person_id, cosine_score) if the best match exceeds `threshold`,
    otherwise (None, best_score).
    """
    emb = embed(audio, sample_rate)
    if emb is None or not voice_gallery:
        return None, 0.0

    best_id, best_score = None, -1.0
    for person_id, profile_emb in voice_gallery.items():
        sim = float(np.dot(emb, profile_emb))   # cosine sim on L2-normalized vectors
        if sim > best_score:
            best_score = sim
            best_id    = person_id

    if best_score >= threshold:
        return best_id, best_score
    return None, best_score
