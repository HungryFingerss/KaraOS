"""ProcessPoolExecutor wrapper for heavy C-extension tasks (P0.R6 foundation).

Architecture per P0.R6 Phase 0 §2.1 + Plan v1 §2.1 LOCKED spec:

- 1 ProcessPoolExecutor per heavy-task type (one worker pool per task class)
- Workers persistent (warm; loaded model state preserved across calls)
- IPC via pickle (default) for foundation cycle (Q3 (a) lock)
- Restart-on-crash semantic via worker lifecycle management
- ``multiprocessing.set_start_method("spawn")`` for Windows + Linux cross-platform
  (Q6 (a) lock — explicit ``mp.get_context("spawn")`` rather than relying on the
  process-wide default which varies across host OS + parent process state)

P0.R6 foundation ships AdaFace migration only per Q1 (a) Q2 (a) decomposition.
Subsequent specs (P0.R6.X / P0.R6.Y / P0.R6.Z) add Whisper + ECAPA + pyannote
workers using the same pattern; this module is the shared scaffolding.

Subprocess model lifecycle:
- ``get_or_create_pool(task_name)`` mints a pool with ``max_workers=1`` (Q4 (a)
  persistent-worker lock; single worker per task class avoids GPU contention).
- ``run_heavy(task_name, fn, *args, **kwargs)`` is the async entry point;
  ``await`` returns once the subprocess completes the inference call.
- ``shutdown_all_pools(wait=True)`` cancels every pool cleanly at process exit
  (D5 shutdown wiring).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import multiprocessing as mp
import threading
import time
import traceback
from typing import Any, Callable

_HEAVY_WORKER_POOLS: dict[str, concurrent.futures.ProcessPoolExecutor] = {}

# ─────────────────────────────────────────────────────────────────────────────
# P0.R9 D2 — VRAM budget guard module state
# ─────────────────────────────────────────────────────────────────────────────
#
# `_REFUSED_POOLS` caches task_names that failed the cumulative VRAM budget
# check at first-call lazy invocation (Q6 (a) lock). Subsequent calls return
# False from cache without re-probing CUDA (Q4 (a) lock). `_VRAM_CHECK_LOCK`
# guards mutation under concurrent run_heavy callers (defense-in-depth — the
# asyncio loop is single-threaded, but loop.run_in_executor dispatch may
# trigger the check from worker threads under certain conditions).
_REFUSED_POOLS: "set[str]" = set()
_VRAM_CHECK_LOCK = threading.Lock()

# ─────────────────────────────────────────────────────────────────────────────
# P0.R8 D1 — heavy-worker pool crash history (main-process state)
# ─────────────────────────────────────────────────────────────────────────────
#
# Module-level crash event tracking for the watchdog's burst-detection logic.
# Each entry is a list of unix timestamps (one per BrokenProcessPool event)
# keyed by task_name. Subprocesses don't see this dict — it lives only in the
# main process where `run_heavy` catches BrokenProcessPool.
#
# Thread-safety: `run_heavy` is async (single-threaded asyncio loop), but
# `loop.run_in_executor` may dispatch the BrokenProcessPool catch from a
# worker thread under certain conditions. Lock-guarded mutation is
# defense-in-depth + matches the architectural pattern of "concurrent run_heavy
# calls from multiple coroutines may race on the same task_name's list".
_HEAVY_WORKER_CRASH_HISTORY: "dict[str, list[float]]" = {}
_HEAVY_WORKER_CRASH_LOCK = threading.Lock()


def _record_pool_crash(task_name: str, now: "float | None" = None) -> None:
    """Record a pool-crash event for burst detection. Called from
    ``run_heavy()``'s ``BrokenProcessPool`` catch block.

    Thread-safe via ``_HEAVY_WORKER_CRASH_LOCK`` — concurrent ``run_heavy()``
    calls from multiple coroutines can race on the same task_name's history
    list.

    Crash events stay in history indefinitely between calls;
    ``count_recent_crashes`` filters + prunes by the burst-window at
    watchdog poll time, bounding memory growth.
    """
    if now is None:
        now = time.time()
    with _HEAVY_WORKER_CRASH_LOCK:
        _HEAVY_WORKER_CRASH_HISTORY.setdefault(task_name, []).append(now)


def count_recent_crashes(
    task_name: str, window_secs: float, now: "float | None" = None
) -> int:
    """Return number of crashes for ``task_name`` within the rolling
    ``window_secs`` window ending at ``now``. Implicitly prunes events
    older than ``window_secs`` (writes back filtered list).
    """
    if now is None:
        now = time.time()
    cutoff = now - window_secs
    with _HEAVY_WORKER_CRASH_LOCK:
        events = _HEAVY_WORKER_CRASH_HISTORY.get(task_name, [])
        events = [t for t in events if t >= cutoff]
        _HEAVY_WORKER_CRASH_HISTORY[task_name] = events
        return len(events)


def peek_crash_history(task_name: str) -> "list[float]":
    """Return COPY of crash history for ``task_name``. Read-only accessor
    for tests + health observability."""
    with _HEAVY_WORKER_CRASH_LOCK:
        return list(_HEAVY_WORKER_CRASH_HISTORY.get(task_name, []))

# Subprocess-scoped FaceEmbedder singleton — populated on first call inside
# the worker subprocess (NOT shared with the parent process; each subprocess
# has its own instance, lazy-loaded). Matches the architect-intended
# "persistent worker, model loads ONCE per subprocess lifetime" contract
# from Plan v1 §2.2.
#
# NOTE (developer-improves-on-spec banking — Phase 4 closure-narrative item):
# Plan v1 §2.2 LOCKED D2 spec referenced ``vision_mod.FaceEmbedder.get_global()``
# but the actual ``core.vision.FaceEmbedder`` class doesn't expose a
# ``get_global`` classmethod. Per ``### Spec-contracts-not-implementations``
# discipline, implementing the equivalent contract (single embedder per
# subprocess, persistent across calls) via a module-level singleton inside
# the worker module preserves the spec's intent without requiring an API
# surface change to ``core/vision.py``.
_SUBPROCESS_EMBEDDER: "Any | None" = None


def _get_subprocess_embedder() -> "Any":
    """Get-or-create the subprocess-scoped FaceEmbedder singleton.

    Lazy-init: first call loads the model (proactive CPU-EP session per P0.R2
    D1 contract); subsequent calls re-use the loaded instance.
    """
    global _SUBPROCESS_EMBEDDER
    if _SUBPROCESS_EMBEDDER is None:
        import core.vision as vision_mod  # noqa: PLC0415
        try:
            _SUBPROCESS_EMBEDDER = vision_mod.FaceEmbedder()
        except Exception as _e:
            # Q5 sweep (Canary #3): log-only visibility. Unlike the ECAPA/whisper/pyannote
            # loaders this site has NO silent swallow — FaceEmbedder() failure already
            # propagates; we re-raise to preserve that (LOG ONLY, no behavior change) while
            # making a future load failure visible. (AdaFace ONNX — no SpeechBrain patch.)
            print(f"[HeavyWorker] _get_subprocess_embedder load failed: {type(_e).__name__}: {_e}")
            raise
    return _SUBPROCESS_EMBEDDER


def check_vram_budget(task_name: str) -> bool:
    """Return True if ``task_name`` can spawn within VRAM budget; False if refused.

    P0.R9 D2 RATIFIED Q3 (a) + Q4 (a) + Q5 (a) + Q6 (a) + Q7 (a) locks:

    - Q5 (a): skip enforcement on non-CUDA (``torch.cuda.is_available()`` False);
      returns True so non-CUDA dev/CI environments proceed as today.
    - Q4 (a): refused pools cached in ``_REFUSED_POOLS`` module set; subsequent
      calls return False without re-computing.
    - Q6 (a): first-call lazy check (called from ``get_or_create_pool`` BEFORE
      pool creation; matches existing pool warm-up ordering).
    - Q7 (a): ``torch.cuda.mem_get_info()`` — no subprocess overhead.

    Computes cumulative VRAM = sum(ESTIMATES_MB[p] for p in _HEAVY_WORKER_POOLS) +
    ESTIMATES_MB[task_name]; compares to (total_cuda_mb * VRAM_CEILING_PCT / 100).
    """
    with _VRAM_CHECK_LOCK:
        if task_name in _REFUSED_POOLS:
            return False
        try:
            import torch  # noqa: PLC0415
            if not torch.cuda.is_available():
                return True  # Q5 (a) — skip enforcement on non-CUDA
            free_mb, total_mb = (
                b // (1024 * 1024) for b in torch.cuda.mem_get_info()
            )
        except Exception:  # OPTIONAL: torch import / CUDA probe failure → skip
            return True
        from core.config import (  # noqa: PLC0415
            HEAVY_WORKER_VRAM_ESTIMATES_MB,
            VRAM_CEILING_PCT,
        )
        ceiling_mb = total_mb * (VRAM_CEILING_PCT / 100.0)
        cumulative_committed_mb = sum(
            HEAVY_WORKER_VRAM_ESTIMATES_MB.get(p, 0)
            for p in _HEAVY_WORKER_POOLS
        )
        this_pool_mb = HEAVY_WORKER_VRAM_ESTIMATES_MB.get(task_name, 0)
        if cumulative_committed_mb + this_pool_mb > ceiling_mb:
            _REFUSED_POOLS.add(task_name)
            return False
        return True


def peek_refused_pools() -> "set[str]":
    """Read-only accessor for refused pools (test + health observability)."""
    with _VRAM_CHECK_LOCK:
        return set(_REFUSED_POOLS)


def get_or_create_pool(
    task_name: str, max_workers: int = 1
) -> "concurrent.futures.ProcessPoolExecutor | None":
    """Get-or-create singleton ProcessPoolExecutor per task_name.

    P0.R9 D3 RATIFIED Q3 (a): budget check BEFORE pool creation. If
    ``check_vram_budget`` returns False (cumulative would exceed
    ``VRAM_CEILING_PCT``), returns None + dispatches
    ``WatchdogAgent.report_vram_budget_refusal`` alert per Q8 (a) lock
    (per-pool alert granularity). The None return propagates through
    ``run_heavy`` (D4) to caller's existing P0.R1 D1 None-return fallback
    contract uniformly across all 4 callers.

    Foundation cycle (P0.R6 Plan v1 §2.1 Q4 (a) lock): ``max_workers=1`` per
    task. Single worker per task class avoids GPU contention for GPU-bound
    inference + matches the persistent-worker invariant — model loads once per
    subprocess lifetime, then re-used across calls.

    ``mp.get_context("spawn")`` is explicit (Q6 (a) lock) for cross-platform
    consistency across Windows + Linux + Jetson. Default start method varies
    by host OS + parent state; explicit spawn eliminates that variability.
    """
    if task_name in _HEAVY_WORKER_POOLS:
        return _HEAVY_WORKER_POOLS[task_name]
    # P0.R9 D3 — VRAM budget check BEFORE pool creation (Q3 (a) RATIFIED).
    # On refusal: None return + WARN log + WatchdogAgent alert dispatch via
    # core.brain_agent (imported lazily to avoid module-init circular deps).
    if not check_vram_budget(task_name):
        print(
            f"[HeavyWorker] WARN VRAM budget refusal — pool '{task_name}' "
            f"not spawned (cumulative + estimate would exceed "
            f"VRAM_CEILING_PCT). Fallback path will fire via caller's "
            f"None-return handling."
        )
        try:
            import pipeline as _pipeline  # noqa: PLC0415
            from core.config import (  # noqa: PLC0415
                HEAVY_WORKER_VRAM_ESTIMATES_MB,
                VRAM_CEILING_PCT,
            )
            _orch = getattr(_pipeline, "_brain_orchestrator", None)
            if _orch is not None:
                _cum = sum(
                    HEAVY_WORKER_VRAM_ESTIMATES_MB.get(p, 0)
                    for p in _HEAVY_WORKER_POOLS
                )
                _est = HEAVY_WORKER_VRAM_ESTIMATES_MB.get(task_name, 0)
                # Re-probe ceiling for accurate alert metadata.
                import torch  # noqa: PLC0415
                _total_mb = int(torch.cuda.mem_get_info()[1] // (1024 * 1024))
                _ceiling = int(_total_mb * (VRAM_CEILING_PCT / 100.0))
                _orch.report_vram_budget_refusal(
                    task_name, _cum, _ceiling, _est
                )
        except Exception:  # OPTIONAL: pipeline unavailable OR torch probe failed
            pass
        return None
    ctx = mp.get_context("spawn")
    pool = concurrent.futures.ProcessPoolExecutor(
        max_workers=max_workers,
        mp_context=ctx,
        initializer=_adaface_worker_init if task_name == "adaface_embed" else None,
    )
    _HEAVY_WORKER_POOLS[task_name] = pool
    return pool


async def run_heavy(
    task_name: str, fn: Callable, *args: Any, **kwargs: Any
) -> Any:
    """Async wrapper for ProcessPoolExecutor.submit; preserves asyncio integration.

    Resolves the pool for ``task_name`` (creating on first call), then dispatches
    ``fn(*args, **kwargs)`` to a worker subprocess via the loop's
    ``run_in_executor`` glue. The await suspends the asyncio loop until the
    subprocess finishes — non-blocking with respect to the parent's other
    coroutines, unlike a sync ``embedder.embed(...)`` direct call which would
    block the loop for the duration of inference.

    P0.R8 D2 (2026-05-25): wraps dispatch in try/except to detect subprocess
    crashes via ``BrokenProcessPool``. On crash: records event via
    ``_record_pool_crash()`` for watchdog burst-detection + RE-RAISES via
    bare ``raise`` (preserves original traceback for caller debugging) so the
    caller's existing fallback semantic fires unchanged. LOAD-BEARING — the
    4 callers (AdaFace P0.R6 D3 / Whisper P0.R6.X D3 / ECAPA P0.R6.Y D3 /
    Pyannote P0.R6.Z D3.b) all rely on the exception propagating to trigger
    their respective fallback paths (None-return contracts + ECAPA-valley
    fallback). Swallowing the exception here would break every caller's
    fallback chain. The watchdog OBSERVES the crash via the side-effect
    `_record_pool_crash`; it does NOT swap in for the caller's fallback.
    """
    pool = get_or_create_pool(task_name)
    if pool is None:
        # P0.R9 D4 — VRAM budget refusal (Q3 (a) LOAD-BEARING + D3 interaction):
        # propagate None to caller's existing P0.R1 D1 None-return fallback
        # contract uniformly. Skips run_in_executor dispatch. The None flows
        # through `await hw.run_heavy(...)` to caller's None-handling path
        # (AdaFace recognize-miss / Whisper empty-STT / ECAPA identify-miss /
        # Pyannote ECAPA-valley fallback).
        return None
    loop = asyncio.get_running_loop()
    # ``functools.partial`` keeps args + kwargs pickleable across the IPC
    # boundary; lambdas would close over the parent's frame and fail.
    bound = functools.partial(fn, *args, **kwargs)
    try:
        return await loop.run_in_executor(pool, bound)
    except concurrent.futures.process.BrokenProcessPool as e:
        # P0.R8 D2: record + bare re-raise (preserves traceback + caller fallback).
        _record_pool_crash(task_name)
        # P0.R11: capture full forensic JSON for post-mortem. Persist failure
        # is silently logged (P0.4) — the original BrokenProcessPool MUST
        # propagate via the bare `raise` below regardless.
        try:
            from core.crash_logs import persist_crash_diagnostic
            crash_count = len(_HEAVY_WORKER_CRASH_HISTORY.get(task_name, []))
            persist_crash_diagnostic(
                task_name,
                e,
                traceback.format_exc(),
                crash_count,
            )
        except Exception:  # OPTIONAL: P0.R11 import/call failure
            pass
        raise  # bare — preserves traceback + caller fallback


def shutdown_all_pools(wait: bool = True) -> None:
    """Shutdown all heavy-worker pools cleanly at process exit.

    Called from ``pipeline.run()`` shutdown finally block (D5 wiring). With
    ``wait=True`` the call blocks until each pool's pending futures resolve;
    with ``wait=False`` it cancels immediately and lets the OS reap the
    subprocesses.
    """
    for _name, pool in list(_HEAVY_WORKER_POOLS.items()):
        pool.shutdown(wait=wait)
    _HEAVY_WORKER_POOLS.clear()


# ─────────────────────────────────────────────────────────────────────────────
# AdaFace worker (D2 LOCKED spec)
# ─────────────────────────────────────────────────────────────────────────────


def _adaface_worker_init() -> None:
    """Called once per subprocess at startup (ProcessPoolExecutor initializer).

    Loads the AdaFace ONNX session inside the subprocess. The subprocess
    inherits the parent's filesystem state but NOT its memory state; the
    model must be reloaded per subprocess. Lifecycle: persistent worker
    means the model loads ONCE per subprocess lifetime (typically: process
    lifetime), then is re-used across every ``adaface_embed_worker`` call.

    Inside the subprocess:
    - P0.R2 D1 proactive CPU-EP fallback contract is preserved (FaceEmbedder
      __init__ builds CPU session at startup regardless of CUDA availability)
    - P0.R2 D3 graceful boot contract preserved (CUDA-unavailable → CPU-only
      session without raising)
    """
    # Force the subprocess-scoped singleton to materialize via lazy init.
    _ = _get_subprocess_embedder()


def adaface_embed_worker(
    face_crop_bytes: bytes, shape: tuple[int, int, int]
) -> "bytes | None":
    """Worker entry point: deserialize ndarray, call embed, serialize result.

    IPC via pickle (default ProcessPoolExecutor mechanism) but ndarray
    serialization is explicit bytes+shape for predictable wire format —
    pickling a numpy array routes through ``__reduce__`` which inflates
    metadata; raw bytes + shape is leaner.

    Args:
        face_crop_bytes: face crop ndarray (uint8) serialized via ``.tobytes()``
        shape: 3-tuple ``(H, W, 3)`` for ``np.frombuffer`` reconstruction

    Returns:
        Serialized embedding bytes (1024-dim float32 = 4096 bytes) — caller
        reconstructs via ``np.frombuffer(result, dtype=np.float32)``. ``None``
        on cascading failure (P0.R1 D1 contract: GPU OOM + CPU EP fallback
        both fail → return None; caller treats as recognize-miss).
    """
    import numpy as np  # noqa: PLC0415

    face_crop = np.frombuffer(face_crop_bytes, dtype=np.uint8).reshape(shape)
    embedder = _get_subprocess_embedder()
    embedding = embedder.embed(face_crop)
    if embedding is None:
        return None
    return embedding.tobytes()


# ─────────────────────────────────────────────────────────────────────────────
# Whisper worker (P0.R6.X D1+D2 LOCKED spec)
# ─────────────────────────────────────────────────────────────────────────────

_SUBPROCESS_WHISPER_MODEL: "Any | None" = None


def _get_subprocess_whisper() -> "Any | None":
    """Get-or-create the subprocess-scoped WhisperModel singleton.

    Lazy-init: first call loads the model (cuda fp16); subsequent calls
    re-use the loaded instance. Returns None on any load failure so
    callers can apply the P0.R1 D1 None-fallback contract.
    """
    global _SUBPROCESS_WHISPER_MODEL
    if _SUBPROCESS_WHISPER_MODEL is None:
        try:
            from faster_whisper import WhisperModel  # noqa: PLC0415

            _SUBPROCESS_WHISPER_MODEL = WhisperModel(
                "large-v3-turbo",
                device="cuda",
                compute_type="float16",
            )
        except Exception as _e:
            # Q5 sweep (Canary #3): log-only — make a future load failure visible instead
            # of hiding it (different load mechanism than ECAPA; no SpeechBrain patch needed).
            print(f"[HeavyWorker] _get_subprocess_whisper load failed: {type(_e).__name__}: {_e}")
            return None
    return _SUBPROCESS_WHISPER_MODEL


def whisper_transcribe_worker(
    audio_bytes: bytes,
    shape: "tuple[int, ...]",
    dtype_name: str,
    language: str,
) -> "tuple[str, str]":
    """Worker entry point: deserialize audio ndarray, run Whisper, return (text, language).

    IPC via pickle (default ProcessPoolExecutor mechanism); ndarray serialization
    is explicit bytes+shape+dtype_name for predictable wire format.

    Args:
        audio_bytes: audio ndarray serialized via ``.tobytes()``
        shape: ndarray shape for ``np.frombuffer`` reconstruction
        dtype_name: dtype string (e.g. ``"float32"``) for reconstruction
        language: BCP-47 language tag passed through to Whisper + returned

    Returns:
        ``(raw_text, language)`` where ``raw_text`` is the filtered transcript
        (may be empty string on silence / all-filtered segments). ``language``
        is always the input language tag passed through.
    """
    import numpy as np  # noqa: PLC0415

    audio_array = np.frombuffer(audio_bytes, dtype=dtype_name).reshape(shape)
    model = _get_subprocess_whisper()
    if model is None:
        return ("", language)
    segments, _ = model.transcribe(
        audio_array,
        language=language,
        beam_size=5,
        vad_filter=False,
        vad_parameters={"min_silence_duration_ms": 200},
        condition_on_previous_text=False,
        no_speech_threshold=0.7,
        compression_ratio_threshold=2.4,
        log_prob_threshold=-1.5,
        temperature=0.0,
        task="transcribe",
    )
    segments_list = list(segments)
    good = [s for s in segments_list if s.no_speech_prob < 0.6 and s.avg_logprob > -1.5]
    if not good:
        candidates = [s for s in segments_list if s.no_speech_prob < 0.4]
        if candidates:
            good = [min(candidates, key=lambda s: s.no_speech_prob)]
        else:
            return ("", language)
    raw_text = " ".join(s.text for s in good).strip()
    return (raw_text, language)


# ─────────────────────────────────────────────────────────────────────────────
# ECAPA worker (P0.R6.Y D1+D2 LOCKED spec)
# ─────────────────────────────────────────────────────────────────────────────

_SUBPROCESS_ECAPA_EMBEDDER: "Any | None" = None


def _get_subprocess_ecapa() -> "Any | None":
    """Get-or-create the subprocess-scoped SpeechBrain ECAPA-TDNN
    EncoderClassifier singleton.

    Q5 (b) lock: lazy-load on first call matches main-process pattern
    (`core/voice.py::load_speaker_embedder`); first-call latency ~1-2s only
    affects first voice-ID after subprocess spawn (acceptable cost).

    P0.R1 D1 None-return fallback contract preserved: returns None on load
    failure → callers treat as identify-miss. Inherits P0.R5 vendored
    speechbrain fork via `requirements.txt` git URL — no special install
    steps needed.
    """
    global _SUBPROCESS_ECAPA_EMBEDDER
    if _SUBPROCESS_ECAPA_EMBEDDER is None:
        # Canary #3 (2026-05-30): route through the SHARED patch helper so the subprocess
        # applies the SAME hf_hub_download patch the main loader does. P0.R6.Y migrated the
        # inference here but left a bare from_hparams → silent load failure → embed
        # returned None → empty gallery → the Jagan→Lexi mis-rename. The helper owns the
        # order-dependent patch sequence and logs failures (A2 — no more silent swallow).
        import core.voice as voice_mod  # noqa: PLC0415
        _SUBPROCESS_ECAPA_EMBEDDER = voice_mod._load_ecapa_patched("cuda")
    return _SUBPROCESS_ECAPA_EMBEDDER


def ecapa_embed_worker(
    audio_bytes: bytes,
    shape: "tuple[int, ...]",
    dtype_name: str,
    sample_rate: int,
) -> "bytes | None":
    """Worker entry point: deserialize audio ndarray, run ECAPA-TDNN
    inference, return L2-normalized 192-dim float32 embedding as bytes.

    IPC via pickle (default ProcessPoolExecutor mechanism); ndarray
    serialization is explicit bytes+shape+dtype_name for predictable wire
    format (matches P0.R6 D2 adaface_embed_worker + P0.R6.X D2
    whisper_transcribe_worker pattern).

    Q3 (a) lock: explicit (bytes, shape, dtype_name, sample_rate) IPC payload.

    Q4 (b) lock: returns L2-normalized embedding bytes; main process
    consumers deserialize via `np.frombuffer(result, dtype=np.float32)`.
    Worker performs the L2-normalization subprocess-side so the main process
    body just deserializes + detaches buffer.

    Worker body preserves main-process embed() invariants verbatim (1.5s
    minimum reliable length, 16kHz resampling, torch.no_grad,
    L2-normalize) — keeps subprocess semantically identical to current
    main-process code at core/voice.py::embed.

    Returns:
        L2-normalized 192-dim float32 embedding serialized via .tobytes().
        ``None`` on cascading failure (P0.R1 D1 contract: too-short audio,
        model load failure, inference crash → return None; caller treats as
        identify-miss).
    """
    import numpy as np  # noqa: PLC0415

    audio_array = np.frombuffer(audio_bytes, dtype=dtype_name).reshape(shape)
    embedder = _get_subprocess_ecapa()
    if embedder is None:
        return None
    # Minimum reliable length: 1.5 seconds (matches main-process invariant).
    if len(audio_array) < sample_rate * 1.5:
        return None
    # Resample to 16 kHz if needed (matches main-process behavior).
    if sample_rate != 16000:
        import torchaudio  # noqa: PLC0415
        import torch  # noqa: PLC0415

        audio_t = torch.from_numpy(audio_array.astype(np.float32))
        audio_array = torchaudio.functional.resample(audio_t, sample_rate, 16000).numpy()
    import torch  # noqa: PLC0415

    signal = torch.from_numpy(audio_array.astype(np.float32)).unsqueeze(0)
    try:
        with torch.no_grad():
            emb = embedder.encode_batch(signal)
        emb_np = emb.squeeze().cpu().numpy()
        norm = np.linalg.norm(emb_np)
        if norm > 0:
            emb_np = emb_np / norm
        return emb_np.astype(np.float32).tobytes()
    except Exception as _e:
        # A2 (Canary #3): never silent — this inference swallow hid the break alongside
        # the load swallow. Log type+message before returning None.
        print(f"[HeavyWorker] ecapa_embed_worker inference failed: {type(_e).__name__}: {_e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Pyannote diarization worker (P0.R6.Z D1+D2 LOCKED spec)
# ─────────────────────────────────────────────────────────────────────────────

_SUBPROCESS_PYANNOTE_PIPELINE: "Any | None" = None


def _get_subprocess_pyannote() -> "Any | None":
    """Get-or-create the subprocess-scoped pyannote Pipeline singleton.

    Q5 (b) lock: lazy-load on first call. First-call latency ~30-60s if cold
    HF cache (model download); ~2-3s if cached (model load + CUDA context
    init). Acceptable for infrequent multi-speaker scenarios.

    Q6 (a) lock: HF_TOKEN env var inherits at subprocess spawn time per
    Python multiprocessing semantics. P0.R5 vendored fork
    (HungryFingerss/pyannote-audio @ 2cee8f3e) inherits via
    requirements.txt git URL — no special install steps needed.

    P0.R1 D1 None-return fallback contract preserved: returns None on load
    failure → worker returns None → main-process `_diarize_pyannote` falls
    through to ECAPA-valley fallback per existing
    `DIARIZATION_FALLBACK_ON_ERROR` logic.
    """
    global _SUBPROCESS_PYANNOTE_PIPELINE
    if _SUBPROCESS_PYANNOTE_PIPELINE is None:
        try:
            import os  # noqa: PLC0415
            import torch  # noqa: PLC0415
            from pyannote.audio import Pipeline  # noqa: PLC0415

            hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
            _SUBPROCESS_PYANNOTE_PIPELINE = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=hf_token,
            )
            if torch.cuda.is_available():
                _SUBPROCESS_PYANNOTE_PIPELINE.to(torch.device("cuda"))
        except Exception as _e:
            # Q5 sweep (Canary #3): log-only — make a future load failure visible instead
            # of hiding it (Pipeline.from_pretrained via the vendored fork; no SpeechBrain
            # patch needed — that missing-patch class is ECAPA/SpeechBrain-specific).
            print(f"[HeavyWorker] _get_subprocess_pyannote load failed: {type(_e).__name__}: {_e}")
            return None
    return _SUBPROCESS_PYANNOTE_PIPELINE


def pyannote_diarize_worker(
    audio_bytes: bytes,
    shape: "tuple[int, ...]",
    dtype_name: str,
    sample_rate: int,
) -> "list[tuple[float, float, str]] | None":
    """Worker entry point: deserialize audio buffer + call subprocess-
    singleton pyannote Pipeline + SERIALIZE returned Annotation to
    list[tuple[float, float, str]] subprocess-side + return serializable
    list of (start_secs, end_secs, label) triples.

    **Q2 (a) lock — LOAD-BEARING**: subprocess serializes pyannote
    `Annotation` → `list[tuple]` BEFORE returning. The pyannote.core
    Annotation class doesn't pickle reliably across processes (complex
    nested objects + version-skew risk between subprocess + main process
    pyannote versions). Returning simple tuples eliminates the pickle
    boundary AND keeps the main process free of pyannote imports.

    Q3 (a) lock: explicit (bytes, shape, dtype_name, sample_rate) IPC
    payload shape — matches P0.R6 D2 + P0.R6.X D1 + P0.R6.Y D1 precedent.

    Q5 (b) lock: lazy-load pyannote Pipeline on first call via
    `_get_subprocess_pyannote()` accessor.

    Args:
        audio_bytes: audio ndarray serialized via ``.tobytes()``
        shape: ndarray shape for ``np.frombuffer`` reconstruction
        dtype_name: dtype string (e.g. ``"float32"``) for reconstruction
        sample_rate: audio sample rate (Hz) passed to pyannote pipeline

    Returns:
        ``list[tuple[float, float, str]]`` where each tuple is
        ``(start_secs, end_secs, speaker_label)`` per
        ``Annotation.itertracks(yield_label=True)`` iteration. Returns
        empty list ``[]`` on (a) empty audio buffer, (b) empty Annotation
        (pyannote returned 0 segments), or (c) single-segment Annotation
        (single-tuple list). Returns ``None`` on cascading failure
        (pipeline load fails OR sync C-extension raises) — preserves
        P0.R1 D1 None-return fallback contract.

    Q9 (a) lock: subprocess crashes (BrokenProcessPool) surface to the
    main-process caller via the outer try/except in
    `core/voice.py::_diarize_pyannote()` — the pool auto-restarts on the
    next `hw.run_heavy("pyannote_diarize", ...)` call (new subprocess
    spawns). Main process falls through to `_diarize_ecapa_valley` per
    existing `DIARIZATION_FALLBACK_ON_ERROR` logic.
    """
    import numpy as np  # noqa: PLC0415

    audio_array = np.frombuffer(audio_bytes, dtype=dtype_name).reshape(shape)
    if len(audio_array) == 0:
        return []
    pipeline = _get_subprocess_pyannote()
    if pipeline is None:
        return None
    import torch  # noqa: PLC0415

    waveform = torch.from_numpy(audio_array.astype(np.float32)).unsqueeze(0)
    if torch.cuda.is_available():
        waveform = waveform.to(torch.device("cuda"))
    try:
        annotation = pipeline({"waveform": waveform, "sample_rate": sample_rate})
    except Exception as e:
        # #123 D3: LOG the subprocess inference failure — the Canary-#3-class silent-None
        # that hid the embed bug. Main process still falls through to _diarize_ecapa_valley
        # (DIARIZATION_FALLBACK_ON_ERROR), but the operator now sees WHY pyannote degraded.
        print(f"[Diarize] pyannote subprocess failed: {e!r}")
        return None
    # Q2 (a) lock: serialize Annotation → list[tuple] subprocess-side.
    result: "list[tuple[float, float, str]]" = []
    for segment, _, label in annotation.itertracks(yield_label=True):
        result.append((float(segment.start), float(segment.end), str(label)))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Florence-2 object-detection worker (SB.6 Step 2 — 5th pool, query-triggered)
# ─────────────────────────────────────────────────────────────────────────────
#
# Mirrors the Whisper/ECAPA/Pyannote LAZY-load pattern (NOT the AdaFace eager
# `initializer=` path): a query-triggered pool loads only on the first
# `run_heavy("florence_detect", ...)` call, and a load failure returns None
# (the P0.R1 D1 None-fallback contract → cloud-or-hedge in
# core/object_detection.py) rather than crashing the worker at spawn. Florence-2
# is VENDORED under review (SB.6 Step 1, core/_florence2/) + loaded via the
# vendored classes with `trust_remote_code=False` — NO remote code executes from
# the hub (the supply-chain lock; weights pinned by the recorded revision).
#
# Plan v1 §0/§7 inversion: this worker only runs on the GPU build with vendored
# weights — it is STUBBED in the dev-box suite (`hw.run_heavy` monkeypatch). The
# real capability is the §3.6 Jetson benchmark gate, NOT a dev-box assertion.

# Vendored Florence-2 repo + pinned revision (matches the SHA recorded in
# core/_florence2/__init__.py — the reviewed commit).
_FLORENCE_REPO = "microsoft/Florence-2-large"
_FLORENCE_REVISION = "21a599d414c4d928c9032694c424fb94458e3594"

# Subprocess-scoped (model, processor) singleton — loaded ONCE per subprocess.
_SUBPROCESS_FLORENCE: "tuple[Any, Any] | None" = None


def _get_subprocess_florence() -> "tuple[Any, Any] | None":
    """Get-or-create the subprocess-scoped Florence-2 (model, processor) pair.

    Loads the VENDORED Florence-2 (core/_florence2/) — NOT trust_remote_code
    against the hub. `from_pretrained` pulls config + weights from the HF cache
    (pinned by `_FLORENCE_REVISION`) but instantiates OUR reviewed classes, so
    the EXECUTED modeling code is under our control (the SB.6 D5 supply-chain
    fix). Returns None on any load failure → callers apply the P0.R1 D1
    None-fallback contract (object_detection cloud-or-hedge).
    """
    global _SUBPROCESS_FLORENCE
    if _SUBPROCESS_FLORENCE is None:
        try:
            import torch  # noqa: PLC0415
            from core._florence2 import (  # noqa: PLC0415
                Florence2ForConditionalGeneration,
                Florence2Processor,
            )

            device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype = torch.float16 if device == "cuda" else torch.float32
            model = (
                Florence2ForConditionalGeneration.from_pretrained(
                    _FLORENCE_REPO,
                    revision=_FLORENCE_REVISION,
                    torch_dtype=dtype,
                    trust_remote_code=False,
                )
                .to(device)
                .eval()
            )
            processor = Florence2Processor.from_pretrained(
                _FLORENCE_REPO,
                revision=_FLORENCE_REVISION,
                trust_remote_code=False,
            )
            _SUBPROCESS_FLORENCE = (model, processor)
        except Exception as _e:
            # Log-only (Q5 sweep discipline): make a future load failure visible.
            print(f"[HeavyWorker] _get_subprocess_florence load failed: {type(_e).__name__}: {_e}")
            return None
    return _SUBPROCESS_FLORENCE


def _florence_result_to_phrase(parsed: "Any", task_token: str) -> str:
    """Reduce Florence-2's post-processed output to a human phrase for
    `object_context`. Shape-defensive across the vendored processor's return
    forms: pure_text (caption/OCR) → the string; phrase_grounding/od →
    ``{'labels': [...], 'bboxes': [...]}`` → the joined unique labels.
    """
    ans = parsed.get(task_token, parsed) if isinstance(parsed, dict) else parsed
    if isinstance(ans, str):
        return ans.strip()
    if isinstance(ans, dict):
        labels = ans.get("labels") or []
        seen: "list[str]" = []
        for lab in labels:
            s = str(lab).strip()
            if s and s not in seen:
                seen.append(s)
        return ", ".join(seen)
    return str(ans).strip() if ans is not None else ""


def florence_detect_worker(
    frame_bytes: bytes,
    shape: "tuple[int, ...]",
    dtype_name: str,
    task_token: str,
    text_input: "str | None",
) -> "tuple[str, float] | None":
    """Worker entry point: deserialize a BGR frame, run vendored Florence-2 for
    the given task token, return ``(phrase, confidence)``.

    IPC via pickle (default ProcessPoolExecutor mechanism); frame serialization
    is explicit bytes+shape+dtype_name (matches the AdaFace/Whisper/ECAPA/Pyannote
    workers).

    Args:
        frame_bytes: BGR uint8 frame serialized via ``.tobytes()``
        shape: ndarray shape ``(H, W, 3)`` for ``np.frombuffer`` reconstruction
        dtype_name: dtype string (e.g. ``"uint8"``)
        task_token: a Florence-2 task token (e.g. ``"<MORE_DETAILED_CAPTION>"``,
            ``"<OCR>"``, ``"<CAPTION_TO_PHRASE_GROUNDING>"``)
        text_input: the grounding phrase for with-input tasks (appended to the
            token); ``None`` for no-input tasks

    Returns:
        ``(phrase, confidence)`` where ``phrase`` is the human-readable answer
        for ``object_context`` and ``confidence ∈ [0, 1]`` (the beam-averaged
        sequence probability — drives the caller's hedge). ``("", 0.0)`` when
        the model ran but produced no usable phrase. ``None`` on cascading
        failure (load fail / inference crash) → caller applies the P0.R1 D1
        None-fallback contract (cloud-or-hedge).
    """
    import numpy as np  # noqa: PLC0415

    loaded = _get_subprocess_florence()
    if loaded is None:
        return None
    model, processor = loaded
    try:
        import torch  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415

        frame = np.frombuffer(frame_bytes, dtype=dtype_name).reshape(shape)
        # BGR (OpenCV) → RGB → PIL (Florence-2's processor expects PIL/RGB).
        rgb = np.ascontiguousarray(frame[:, :, ::-1])
        pil = Image.fromarray(rgb)
        prompt = task_token if not text_input else f"{task_token}{text_input}"
        inputs = processor(text=prompt, images=pil, return_tensors="pt")
        device = next(model.parameters()).device
        m_dtype = next(model.parameters()).dtype
        input_ids = inputs["input_ids"].to(device)
        pixel_values = inputs["pixel_values"].to(device, m_dtype)
        with torch.no_grad():
            gen = model.generate(
                input_ids=input_ids,
                pixel_values=pixel_values,
                max_new_tokens=1024,
                num_beams=3,
                do_sample=False,
                output_scores=True,
                return_dict_in_generate=True,
            )
        confidence = 1.0
        seq_scores = getattr(gen, "sequences_scores", None)
        if seq_scores is not None and len(seq_scores) > 0:
            confidence = max(0.0, min(1.0, float(torch.exp(seq_scores[0]))))
        generated_text = processor.batch_decode(
            gen.sequences, skip_special_tokens=False
        )[0]
        height, width = int(shape[0]), int(shape[1])
        parsed = processor.post_process_generation(
            generated_text, task=task_token, image_size=(height, width)
        )
        phrase = _florence_result_to_phrase(parsed, task_token)
        if not phrase:
            return ("", 0.0)
        return (phrase, confidence)
    except Exception as _e:
        # Log-only (A2 discipline): inference failure is never silent. The
        # caller treats None as pool-unavailable → cloud-or-hedge.
        print(f"[HeavyWorker] florence_detect_worker inference failed: {type(_e).__name__}: {_e}")
        return None
