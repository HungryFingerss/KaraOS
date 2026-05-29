"""
core/audio.py — STT (faster-whisper) + TTS (Kokoro primary, Piper English fallback)
VAD: Silero | Playback: sounddevice only | English only
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import asyncio
import os
import sys
import time
import threading
import numpy as np
import sounddevice as sd
from core.config import (
    MIC_SAMPLE_RATE, SILENCE_DURATION, VAD_THRESHOLD, RMS_THRESHOLD,
    VAD_SWITCH, PIPER_MODELS_DIR, FILLER_ENABLED,
    SMART_TURN_MODEL_PATH, SMART_TURN_SILENCE, SMART_TURN_THRESHOLD, SMART_TURN_ADDENDUM,
    LIP_MAX_EXTENSION, SPEAKER_LANGUAGES, LOG_LATENCY_ENABLED,
)
from core.log_utils import _now_log_ts

# Latest STT elapsed (ms), populated by transcribe() before it returns. Pipeline
# reads this to decorate the attributed [STT] line with latency, without us
# having to churn transcribe()'s 2-tuple return signature through every caller.
_last_stt_elapsed_ms: float = 0.0

# Latest SPEECH duration (seconds), populated by record_until_silence before it
# returns the audio buffer. Distinct from `len(audio_buf) / MIC_SAMPLE_RATE`
# — the buffer includes pre-roll + speech + trailing silence (typically
# 1.5–2s total), so buffer-based duration bypasses the Bug F short-utterance
# floor entirely. Pipeline reads this to drive the real speech-duration
# check at the routing gate. Same module-level pattern as _last_stt_elapsed_ms
# to avoid churning record_until_silence's 1-tuple return signature.
_last_speech_secs: float = 0.0

# ─────────────────────────────────────────────────────────────────────────────
# P0.R10 D3 — audio device failure tracking (mirror P0.R8 D1)
# ─────────────────────────────────────────────────────────────────────────────
#
# Module-level per-channel failure event tracking for the audio-device
# watchdog's burst-detection logic. Q1 (a) RATIFIED: per-channel keys ('mic',
# 'speaker') tracked independently — USB mic disconnect != speaker driver
# crash; per-channel granularity meaningful operationally.
#
# Thread-safety: callers may be async (speak/speak_stream) OR sync (play_filler,
# stop_audio). threading.Lock guards mutation under concurrent access.
_AUDIO_FAILURE_HISTORY: "dict[str, list[float]]" = {}
_AUDIO_FAILURE_LOCK = threading.Lock()


def _record_audio_failure(channel: str, now: "float | None" = None) -> None:
    """Record an audio-device-failure event for burst detection. Mirrors
    P0.R8's _record_pool_crash shape. channel in {'mic', 'speaker'}.
    """
    if now is None:
        now = time.time()
    with _AUDIO_FAILURE_LOCK:
        _AUDIO_FAILURE_HISTORY.setdefault(channel, []).append(now)


def count_recent_audio_failures(
    channel: str, window_secs: float, now: "float | None" = None
) -> int:
    """Count audio-device failures within rolling window. Mirrors P0.R8's
    count_recent_crashes shape; auto-prunes events older than window.
    """
    if now is None:
        now = time.time()
    cutoff = now - window_secs
    with _AUDIO_FAILURE_LOCK:
        events = _AUDIO_FAILURE_HISTORY.get(channel, [])
        events = [t for t in events if t >= cutoff]
        _AUDIO_FAILURE_HISTORY[channel] = events
        return len(events)


def peek_audio_failure_history(channel: str) -> "list[float]":
    """Read-only accessor for audio-failure history. Tests + observability."""
    with _AUDIO_FAILURE_LOCK:
        return list(_AUDIO_FAILURE_HISTORY.get(channel, []))


# ── TTS text cleaning — strip LLM formatting artifacts before synthesis ───────
import re as _re
_TTS_BOLD_RE    = _re.compile(r'\*{1,3}(.*?)\*{1,3}')                # **bold**, *italic*, ***both***
_TTS_UNDER_RE   = _re.compile(r'_{1,2}(.*?)_{1,2}')                  # _italic_, __bold__
_TTS_STRIKE_RE  = _re.compile(r'~~(.*?)~~')                           # ~~strikethrough~~
_TTS_CODE_RE    = _re.compile(r'`+([^`]*)`+')                        # `code`, ``code``
_TTS_HEADER_RE  = _re.compile(r'^\s*#{1,6}\s+', _re.MULTILINE)       # # Header lines
_TTS_BULLET_RE  = _re.compile(r'^\s*[-•*]\s+', _re.MULTILINE)        # - bullet / • bullet
_TTS_NUMLIST_RE = _re.compile(r'^\s*\d+[.)]\s+', _re.MULTILINE)      # 1. item / 2) item
_TTS_EMDASH_RE  = _re.compile(r'\s*—\s*|\s+--\s+')                   # em dash / spaced --
_TTS_SPACES_RE  = _re.compile(r'  +')                                 # double+ spaces
_TTS_LINK_RE    = _re.compile(r'\[([^\]]+)\]\([^\)]+\)')              # [text](url) → text

# Bug H (2026-04-20 live run) — meta-commentary detection.
# The LLM occasionally leaks its own function-calling reasoning or "as an AI"
# boilerplate into the spoken response channel instead of keeping it internal.
# Observed in the live run: "No function call is needed for this prompt." was
# spoken aloud to the user. Patterns deliberately narrow — "I will tell you
# about cars" must not match, only metacommentary about tools / reasoning /
# AI self-identification.
_META_COMMENTARY_PATTERNS = [
    _re.compile(r'\bno\s+function\s+call[s]?\s+(?:is|are|were)?\s*(?:needed|required|necessary)', _re.IGNORECASE),
    _re.compile(r'\b(?:function|tool)\s+call[s]?\s+(?:is|was|are|were)\s+not\s+(?:needed|required|necessary)', _re.IGNORECASE),
    _re.compile(r"\bi\s+(?:should|will|would|won[\'`’]t|do\s+not\s+need\s+to)\s+(?:call|invoke|use)\s+(?:the|a|any)\s+(?:function|tool)\b", _re.IGNORECASE),
    _re.compile(r"\bthe\s+user[\'`’]s\s+(?:request|message|prompt)\s+does\s+not\s+(?:require|need)\b", _re.IGNORECASE),
    _re.compile(r"\bbased\s+on\s+(?:the|your)\s+(?:system\s+)?prompt\b", _re.IGNORECASE),
    _re.compile(r'\bas\s+an?\s+ai\b', _re.IGNORECASE),
    # Bug X (2026-04-22 live run): the LLM emitted the bare SILENT protocol
    # token (used by KAIROS to indicate "no proactive utterance") as a regular
    # response after garbled STT + a blocked search_web. TTS spoke "SILENT"
    # literally to the user. Anchored full-string match so "the room is
    # silent" / "silent treatment" don't false-positive.
    _re.compile(r'^\s*SILENT\s*[.!?]?\s*$', _re.IGNORECASE),
    _re.compile(r'^\s*(?:NO[\s_-]?RESPONSE|\[SILENT\]|<silent>)\s*$', _re.IGNORECASE),
]


def _is_meta_commentary(text: str) -> bool:
    """True iff `text` is purely meta-commentary that should never be spoken.

    Used by `_clean_for_tts` to drop leaked function-calling / reasoning /
    'as an AI' utterances before they reach Kokoro/Piper.
    """
    t = (text or "").strip()
    return bool(t) and any(p.search(t) for p in _META_COMMENTARY_PATTERNS)


def _clean_for_tts(text: str) -> str:
    """Strip LLM formatting artifacts that cause TTS mispronunciation.

    Called before every Kokoro / Piper synthesis. Safe no-op on plain text.
    Order matters: inline patterns before whitespace collapse.

    Bug H (2026-04-20 live run): pure meta-commentary ("No function call is
    needed for this prompt.") is dropped entirely — returning "" causes the
    caller's sentence-level logic to skip TTS for that fragment.
    """
    if _is_meta_commentary(text):
        return ""
    text = _TTS_LINK_RE.sub(r'\1',   text)   # [text](url) → text (before inline patterns)
    text = _TTS_HEADER_RE.sub('',    text)   # # Headers → remove marker
    text = _TTS_BOLD_RE.sub(r'\1',   text)   # **bold** → bold
    text = _TTS_UNDER_RE.sub(r'\1',  text)   # _italic_ → italic
    text = _TTS_STRIKE_RE.sub(r'\1', text)   # ~~strike~~ → strike
    text = _TTS_CODE_RE.sub(r'\1',   text)   # `code` → code
    text = _TTS_BULLET_RE.sub('',    text)   # - item → item
    text = _TTS_NUMLIST_RE.sub('',   text)   # 1. item → item
    text = _TTS_EMDASH_RE.sub(', ',  text)   # — → ,
    text = _TTS_SPACES_RE.sub(' ',   text)   # collapse spaces
    return text.strip()


# ── Shutdown flag — set by stop_audio() to unblock record_until_silence() ────
_interrupt_flag = threading.Event()

# ── Lip activity — set by pipeline lip tracking task, read by record_until_silence ──
_lip_active = threading.Event()


def set_lip_active(moving: bool) -> None:
    """Called by pipeline.py's background lip tracking task."""
    if moving:
        _lip_active.set()
    else:
        _lip_active.clear()


# ── TTS echo-window — set by speak() so record_until_silence() can skip ──────
# pre_roll audio that contains room echo of the system's own TTS output.
_tts_end_time:        float = 0.0
_POST_TTS_ECHO_WINDOW: float = 0.45   # seconds of echo after TTS ends

# ── Piper TTS (English fallback when Kokoro unavailable) ─────────────────────
# Downloaded from: https://github.com/rhasspy/piper/releases
# Place en_US-lessac-medium.onnx + .json in models/piper/
_PIPER_EN_MODEL = "en_US-lessac-medium.onnx"
_piper_en_voice = None  # loaded lazily on first fallback use


# ── Smart-Turn — neural end-of-turn detection ────────────────────────────────
_st_extractor = None   # WhisperFeatureExtractor (audio → mel spectrogram)
_st_session   = None   # onnxruntime.InferenceSession (~8MB ONNX model)


def _load_smart_turn():
    """Load Smart-Turn ONNX model. Gracefully skipped if model file absent."""
    global _st_extractor, _st_session
    if not SMART_TURN_MODEL_PATH.exists():
        print(
            f"[Audio] Smart-Turn model not found — silence-only end-of-turn.\n"
            f"        Download smart-turn-v3.1.onnx from github.com/pipecat-ai/smart-turn\n"
            f"        and place it at: {SMART_TURN_MODEL_PATH}"
        )
        return
    try:
        import onnxruntime as ort
        from transformers import WhisperFeatureExtractor
        _st_extractor = WhisperFeatureExtractor(chunk_length=8)
        so = ort.SessionOptions()
        so.execution_mode             = ort.ExecutionMode.ORT_SEQUENTIAL
        so.inter_op_num_threads       = 1
        so.graph_optimization_level   = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _st_session = ort.InferenceSession(str(SMART_TURN_MODEL_PATH), sess_options=so)
        print("[Audio] Smart-Turn loaded — neural end-of-turn active")
    except Exception as e:
        print(f"[Audio] Smart-Turn unavailable ({e}) — silence-only end-of-turn")


def _smart_turn_predict(audio: np.ndarray) -> float:
    """
    Return P(turn complete) ∈ [0, 1].
    Runs in a thread (record_until_silence is already in an executor).
    Returns 0.0 (= incomplete) on any failure so the hard silence fallback fires.
    """
    if _st_session is None:
        return 0.0
    try:
        target = 8 * MIC_SAMPLE_RATE
        padded = audio[-target:] if len(audio) >= target else np.concatenate(
            [np.zeros(target - len(audio), dtype=np.float32), audio]
        )
        features = _st_extractor(padded, sampling_rate=MIC_SAMPLE_RATE,
                                  return_tensors="np").input_features
        return float(_st_session.run(None, {"input_features": features})[0][0][0])
    except Exception as e:
        print(f"[Audio] Smart-Turn predict failed: {e}")
        return 0.0


# ── Whisper model (lazy load) ─────────────────────────────────────────────────
_whisper_model = None

def _load_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        print("[Audio] Loading Whisper large-v3-turbo on GPU...")
        t0 = time.time()
        _whisper_model = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16")
        print(f"[Audio] Whisper ready — {time.time()-t0:.1f}s")
    return _whisper_model


# ── Kokoro TTS (lazy load) ────────────────────────────────────────────────────
_kokoro_model = None

def _load_kokoro():
    global _kokoro_model
    if _kokoro_model is None:
        from kokoro_onnx import Kokoro
        print("[Audio] Loading Kokoro TTS...")
        t0 = time.time()
        model_dir = os.path.join(os.path.dirname(__file__), "..", "models")
        _kokoro_model = Kokoro(
            os.path.join(model_dir, "kokoro-v1.0.onnx"),
            os.path.join(model_dir, "voices-v1.0.bin")
        )
        print(f"[Audio] Kokoro ready — {time.time()-t0:.1f}s")
    return _kokoro_model


# ── VAD model (lazy load) ─────────────────────────────────────────────────────
_vad_model = None

def _load_vad():
    global _vad_model
    if _vad_model is None:
        from silero_vad import load_silero_vad
        print("[Audio] Loading Silero VAD...")
        t0 = time.time()
        _vad_model = load_silero_vad()
        print(f"[Audio] VAD ready — {time.time()-t0:.1f}s")
    return _vad_model


# ── Filler audio (pre-rendered, plays non-blocking while LLM thinks) ─────────
# Organized by topic so the filler sounds relevant to what was asked.
_FILLER_PHRASES: dict[str, list[str]] = {
    "sports": [
        "Let me check those sports details.",
        "Looking up that score for you.",
        "Checking the sports news.",
    ],
    "web": [
        "Let me look that up online.",
        "Checking the latest on that.",
        "One moment, fetching that.",
    ],
    "weather": [
        "Checking the weather for you.",
        "Let me look up the forecast.",
    ],
    "searching": [
        "Let me search the web for that.",
        "Fetching that from the web.",
        "Checking online for you.",
    ],
    "thinking": [
        "Hmm, let me think.",
        "One moment.",
        "Let me see.",
        "Sure, one second.",
        "Let me work on that.",
        "On it.",
    ],
}

# Keywords for picking a category — checked in order
_FILLER_KEYWORDS: list[tuple[list[str], str]] = [
    (["ipl", "cricket", "match", "score", "team", "player", "football", "f1", "race", "sport", "league", "season", "tournament", "cup"], "sports"),
    (["weather", "rain", "temperature", "forecast", "sunny", "humidity", "wind"], "weather"),
    (["news", "latest", "today", "current", "now", "happening", "internet", "website", "search", "online", "check"], "web"),
]

# Flat cache: {category: [(pcm, sr), ...]}
_filler_cache: dict[str, list[tuple[np.ndarray, int]]] = {}


def preload_fillers():
    """Pre-render all filler phrases via Kokoro at startup."""
    global _filler_cache
    cache: dict[str, list[tuple[np.ndarray, int]]] = {}
    total = 0
    for category, phrases in _FILLER_PHRASES.items():
        rendered = []
        for phrase in phrases:
            try:
                pcm, sr = _tts_kokoro(phrase)
                if pcm is not None and len(pcm) > 0:
                    rendered.append((pcm, sr))
                    total += 1
            except Exception as e:
                print(f"[Audio] Filler pre-render failed '{phrase}': {e}")
        if rendered:
            cache[category] = rendered
    _filler_cache = cache
    print(f"[Audio] Filler cache: {total} phrases ready")


def play_filler(message: str = ""):
    """Play a contextually appropriate pre-rendered filler phrase non-blocking.
    No-op when FILLER_ENABLED=False.
    """
    if not FILLER_ENABLED:
        return
    if not _filler_cache:
        return

    # Detect category from message keywords
    category = "thinking"
    msg_lower = message.lower()
    for keywords, cat in _FILLER_KEYWORDS:
        if any(kw in msg_lower for kw in keywords):
            category = cat
            break

    pool = _filler_cache.get(category) or _filler_cache.get("thinking") or []
    if not pool:
        # Flatten all categories as last resort
        pool = [item for items in _filler_cache.values() for item in items]
    if not pool:
        return

    import random as _random
    pcm, sr = _random.choice(pool)
    try:
        sd.play(pcm, samplerate=sr)
    except (sd.PortAudioError, OSError) as e:
        # P0.R10 D2.c — speaker device failure: log + record for burst detection;
        # fall through naturally (low-stakes filler, caller's contract preserved).
        print(f"[Audio] WARN speaker device failure in play_filler: {e!r}")
        _record_audio_failure("speaker")
    except Exception as e:
        print(f"[Audio] Filler play error: {e}")


def preload_models():
    """Eagerly load all heavy models at startup to avoid first-use delays."""
    _load_whisper()
    _load_kokoro()
    if VAD_SWITCH:
        _load_vad()
    _load_smart_turn()
    if FILLER_ENABLED:
        preload_fillers()


# ── Recording ─────────────────────────────────────────────────────────────────
def record_until_silence(
    sample_rate: int = MIC_SAMPLE_RATE,
    silence_duration: float = SILENCE_DURATION,
    max_duration: float = 30.0,
    speech_onset_timeout: float = 0.0,
) -> "np.ndarray | None":
    """Record from mic until speech then silence is detected.

    VAD_SWITCH=True:  Silero VAD (accurate, GPU-backed on Jetson/PCB)
    VAD_SWITCH=False: RMS energy threshold (no model needed, works on laptop)

    Runs in a thread via run_in_executor — checks _interrupt_flag each chunk
    so stop_audio() (called on shutdown) exits the loop within ~32ms.
    """
    # Clear any leftover flag from a previous TTS.
    _interrupt_flag.clear()

    print("[Audio] Listening...")

    chunk_size             = 512
    chunk_dur              = chunk_size / sample_rate
    max_chunks             = int(max_duration / chunk_dur)
    original_silence_count = int(silence_duration / chunk_dur)
    onset_chunks           = int(speech_onset_timeout / chunk_dur) if speech_onset_timeout > 0 else 0
    silence_count          = original_silence_count
    smart_turn_count       = int(SMART_TURN_SILENCE / chunk_dur)   # 0.5s — Smart-Turn trigger
    addendum_count         = int(SMART_TURN_ADDENDUM / chunk_dur)  # 0.35s — grace window
    max_lip_chunks         = int(LIP_MAX_EXTENSION / chunk_dur)    # 2s — max lip extension
    min_speech             = int(0.10 / chunk_dur)  # 100ms min speech — allows single words

    audio_chunks      = []
    pre_roll          = []
    pre_roll_size     = int(1.0 / chunk_dur)   # 1s pre-roll
    silent_streak     = 0
    speech_chunks     = 0
    started           = False
    smart_turn_fired  = False  # one check per silence window, reset on resumed speech
    lip_extensions    = 0     # chunks extended due to lip activity
    _in_silence       = False  # rate-limit: only log FIRST chunk of each silence streak
    _speech_run       = 0     # consecutive speech chunks — prevents noise spikes resetting _in_silence

    if VAD_SWITCH:
        import torch
        vad_model = _load_vad()

    # P0.R10 D1 Q3 (a) RATIFIED LOAD-BEARING: wrap sd.InputStream context
    # manager in try/except for (sd.PortAudioError, OSError). On failure:
    # record event via _record_audio_failure('mic') + return None (distinct
    # sentinel — empty audio means 'user was silent', None means 'device
    # failed'). Caller (listen_and_transcribe + pipeline.py callers) inspects
    # None vs empty-array to route differently (silence vs device-error).
    try:
        with sd.InputStream(samplerate=sample_rate, channels=1, dtype='float32') as stream:
            stream_open_time = time.time()
            echo_clear_until = _tts_end_time + _POST_TTS_ECHO_WINDOW

            for chunk_idx in range(max_chunks):
                if _interrupt_flag.is_set():
                    break
                if onset_chunks > 0 and not started and chunk_idx >= onset_chunks:
                    break  # no speech onset detected within timeout — exit early
                chunk, _ = stream.read(chunk_size)
                chunk_1d  = chunk.flatten()

                if VAD_SWITCH:
                    tensor     = torch.from_numpy(chunk_1d)
                    is_speech  = vad_model(tensor, sample_rate).item() > VAD_THRESHOLD
                else:
                    is_speech  = float(np.sqrt(np.mean(chunk_1d ** 2))) > RMS_THRESHOLD

                if is_speech:
                    if not started:
                        started = True
                        print(f"[Audio] Speech started (chunk #{chunk_idx}, {_now_log_ts()})")
                        chunk_time = stream_open_time + chunk_idx * chunk_dur
                        if chunk_time > echo_clear_until:
                            # Pre_roll may still contain echo chunks from its earliest portion
                            # (captured right after the stream opened, before the echo cleared).
                            # Trim those leading chunks so Whisper only sees clean audio.
                            pre_roll_start = stream_open_time + (chunk_idx - len(pre_roll)) * chunk_dur
                            echo_skip = min(max(0, int((echo_clear_until - pre_roll_start) / chunk_dur)), len(pre_roll))
                            if echo_skip > 0:
                                print(f"[Audio] Echo skip: {echo_skip}/{len(pre_roll)} pre-roll chunks trimmed")
                            audio_chunks.extend(pre_roll[echo_skip:])
                    silent_streak    = 0
                    _speech_run     += 1
                    if _speech_run >= 9:             # ~288ms sustained speech resets silence flag
                        _in_silence  = False         # prevents micropause within utterance re-firing log
                    smart_turn_fired = False        # allow another Smart-Turn check on next pause
                    silence_count    = original_silence_count  # restore if Smart-Turn had shrunk it
                    lip_extensions   = 0            # reset lip extension budget
                    speech_chunks   += 1
                    audio_chunks.append(chunk_1d)
                elif started:
                    audio_chunks.append(chunk_1d)
                    _speech_run = 0                  # reset sustained-speech counter
                    if not _in_silence:
                        _in_silence = True
                        print(f"[Audio] Silence detected — waiting for end-of-turn...")
                    silent_streak += 1

                    # Smart-Turn: at the first 0.5s of silence, ask the neural model
                    # whether the turn is complete. No wordlists — it reads audio patterns.
                    # On a confident completion, shrink the remaining silence window to
                    # addendum_count (0.35s). If the person resumes speaking within that
                    # grace window, smart_turn_fired resets and recording continues.
                    # If they stay silent for 0.35s more, the hard-stop below fires.
                    #
                    # P0.S7.5.2 D4 — broaden the silent_streak guard from `==` to `>=`
                    # so a missed boundary chunk doesn't skip Smart-Turn for the
                    # whole streak; the `not smart_turn_fired` flag (reset on resumed
                    # speech, line 418) is the debounce — invariant "fires at most
                    # once per silence streak" preserved.
                    if (not smart_turn_fired
                            and silent_streak >= smart_turn_count
                            and speech_chunks >= min_speech):
                        smart_turn_fired = True
                        prob = _smart_turn_predict(np.concatenate(audio_chunks))
                        if prob > SMART_TURN_THRESHOLD:
                            # Adaptive grace: very high confidence → shorter window (saves ~300ms).
                            # Moderate confidence → full window in case of genuine mid-thought pause.
                            used_addendum = int(addendum_count * 0.4) if prob >= 0.95 else addendum_count
                            print(f"[Audio] Smart-Turn: turn complete (p={prob:.2f}, grace={used_addendum * chunk_dur:.2f}s)")
                            silence_count = smart_turn_count + used_addendum

                    # Hard stop: fires when silence_count is reached.
                    # Lip tracking gets a final veto: if lips are still moving, extend
                    # one chunk (~32ms) at a time up to LIP_MAX_EXTENSION total.
                    if silent_streak >= silence_count and speech_chunks >= min_speech:
                        if _lip_active.is_set() and lip_extensions < max_lip_chunks:
                            lip_extensions += 1
                            if lip_extensions == 1:
                                print(f"[Audio] Lip extension: holding turn (lips still moving)")
                        else:
                            print(f"[Audio] Turn end — {speech_chunks} speech chunks, {lip_extensions} lip extension(s)")
                            break
                else:
                    pre_roll.append(chunk_1d)
                    if len(pre_roll) > pre_roll_size:
                        pre_roll.pop(0)
    except (sd.PortAudioError, OSError) as e:
        # P0.R10 D1 Q3 (a) — mic device failure: log + record for burst
        # detection + return None (distinct sentinel — see docstring above).
        print(f"[Audio] WARN mic device failure during record_until_silence: {e!r}")
        _record_audio_failure("mic")
        return None

    if not audio_chunks or speech_chunks < min_speech:
        # Empty / sub-threshold recording — DO NOT publish. Session 78 learned
        # the hard way that the pipeline's addendum window (a 3s post-turn
        # probe that usually yields NO speech) was clobbering the main turn's
        # _last_speech_secs with 0.0 before the routing gate could read it.
        # Publish is now conditional: only recordings that produced usable
        # audio update the global; the routing gate always sees the latest
        # *recorded* speech duration, not the latest *attempted* one.
        return np.array([], dtype=np.float32)

    # Publish observed speech duration for the pipeline's short-utterance
    # floor. ECAPA-TDNN embeddings below ~1s of actual speech are too noisy
    # for reliable routing decisions; buffer duration (pre-roll + silence)
    # is not the right signal (always >1s).
    global _last_speech_secs
    _last_speech_secs = speech_chunks * chunk_dur

    return np.concatenate(audio_chunks, axis=0)


# ── STT ───────────────────────────────────────────────────────────────────────

async def transcribe(audio: np.ndarray) -> tuple[str, str]:
    """Transcribe audio using faster-whisper. English only.

    P0.R6.X migration: inference offloaded to ProcessPoolExecutor subprocess
    via ``hw.run_heavy("whisper_transcribe", ...)``. The subprocess holds the
    persistent WhisperModel singleton (loaded once at startup); the asyncio
    loop is not blocked during the ~100-300ms inference call. Segment
    filtering (no_speech_prob / avg_logprob gates) happens in the subprocess
    (per Plan v1 §2.1); the local text filter chain at lines below stays in
    the main process per Q2(b) LOCK.

    Observability: the elapsed ms is exposed via the module-level
    ``_last_stt_elapsed_ms`` global and also printed alongside the transcript.
    Return signature stays 2-tuple to avoid churning every caller's unpacking.
    """
    global _last_stt_elapsed_ms
    if len(audio) == 0:
        return "", "en"

    import time as _time
    import core.heavy_worker as hw  # noqa: PLC0415
    _t0 = _time.perf_counter()
    text, _ = await hw.run_heavy(
        "whisper_transcribe",
        hw.whisper_transcribe_worker,
        audio.tobytes(),
        audio.shape,
        audio.dtype.name,
        language=SPEAKER_LANGUAGES[0],
    )
    if not text:
        print("[Audio] STT: (filtered)")
        return "", "en"

    # Discard if transcript is mostly non-ASCII (Whisper hallucination on noise)
    non_ascii = sum(1 for c in text if not c.isascii())
    if text and non_ascii / len(text) > 0.2:
        print("[Audio] STT: (non-ASCII hallucination — discarded)")
        return "", "en"

    # Session 105 Obs A — character-level repetition filter. 2026-04-23
    # canary line 444: Whisper emitted `Mmmmm... × 500` chars on
    # ambient noise. Word-level filter below doesn't catch single-char
    # runs (it's all one "word" token). Regex `(.)\1{15,}` matches any
    # 16+ char run of the same character — zero false-positive risk
    # because no natural human utterance produces that pattern in STT
    # output (laughter, "mmm", "ohh" max out around 5-6 chars before
    # Whisper segments). Runs BEFORE the word-level filter since the
    # character run would usually pass word-level filtering (single
    # token).
    import re as _re_stt
    if _re_stt.search(r"(.)\1{15,}", text):
        print(f"[Audio] STT: (char-run hallucination filtered): '{text[:80]}'")
        return "", "en"

    # Repetition hallucination filter — word level
    words = [w.strip('.,!?;:"\'-').lower() for w in text.split()]
    words = [w for w in words if w]
    if len(words) >= 4 and len(set(words)) / len(words) <= 0.5:
        print(f"[Audio] STT: (repetition filtered): '{text[:80]}'")
        return "", "en"

    # Phrase-level repetition
    for sep in (', ', '. ', ' - ', '; '):
        idx = text.find(sep)
        if idx > 3:
            first = text[:idx].strip().lower()
            rest  = text[idx + len(sep):].strip().rstrip('.').lower()
            if first == rest:
                print(f"[Audio] STT: (phrase repetition filtered): '{text[:80]}'")
                return "", "en"

    # P0.S7.5.2 D4 — 1-word artifact filter. Canary 3 (2026-05-20) surfaced
    # multiple turns where Whisper emitted bare "You", "Yeah", "Thank" with
    # no terminal punctuation — phantom acknowledgments that triggered
    # phantom routing/extraction work. Accept 1-word transcripts ONLY when
    # EITHER (a) terminated with .!? — "Stop.", "Help!" — OR (b) lowercase
    # word matches the known-imperative allowlist. Otherwise reject as
    # Whisper noise. Allowlist expansion procedure documented in
    # core/config.py STT_KNOWN_IMPERATIVES docstring.
    from core.config import MIN_STT_WORD_COUNT, STT_KNOWN_IMPERATIVES
    _t_stripped = text.strip()
    _raw_words = _t_stripped.split()
    if len(_raw_words) < MIN_STT_WORD_COUNT:
        _terminated = _t_stripped.endswith(('.', '!', '?'))
        _word_lower = _t_stripped.lower().rstrip('.!?,;:')
        _allowed = _word_lower in STT_KNOWN_IMPERATIVES
        if not (_terminated or _allowed):
            print(f"[Audio] STT: (1-word artifact filtered): {_t_stripped!r}")
            return "", "en"

    # Raw STT log — pipeline.py attaches speaker attribution in its own [STT] line;
    # this ensures paths that don't go through the inner conversation loop
    # (first_boot_flow, ambient, addendum) still show what Whisper heard.
    # Records elapsed ms on the module-level _last_stt_elapsed_ms global so
    # pipeline.py can surface it in the attributed log line without changing
    # transcribe()'s return signature.
    _last_stt_elapsed_ms = (_time.perf_counter() - _t0) * 1000.0
    _lat_tag = f" ({_last_stt_elapsed_ms:.0f}ms)" if LOG_LATENCY_ENABLED else ""
    print(f"[STT] {_now_log_ts()}{_lat_tag} {text!r}")
    return text, "en"


async def listen_and_transcribe(
    sample_rate: int = MIC_SAMPLE_RATE,
    silence_duration: float = SILENCE_DURATION,
    max_duration: float = 30.0,
    speech_onset_timeout: float = 0.0,
) -> tuple[str, str, np.ndarray]:
    """Record then transcribe. Returns (text, language, audio_array).

    audio_array is the raw float32 mono PCM — callers may use it for voice
    speaker recognition. It is always a numpy array (empty if no speech).
    Both operations run in executor so the event loop stays free.
    """
    loop  = asyncio.get_running_loop()
    audio = await loop.run_in_executor(
        None, record_until_silence, sample_rate, silence_duration, max_duration, speech_onset_timeout
    )
    if len(audio) == 0:
        return "", "en", audio
    text, lang = await transcribe(audio)
    # P0.0.7 H1 — emit audio_in event via safe_emit_sync. session_id=None
    # at this boundary (audio capture is session-agnostic; identity_claim
    # downstream threads session via the natural-pair chain). The
    # safe_emit_sync helper carries the single P0.4-annotated except block;
    # this call site does not need its own try/except.
    import hashlib as _h1_hash
    from core.event_log import safe_emit_sync, AudioInPayload
    _audio_hash = "sha256:" + _h1_hash.sha256(audio.tobytes()[:16384]).hexdigest()[:16]
    safe_emit_sync(
        "audio_in",
        AudioInPayload(
            audio_hash=_audio_hash,
            speech_secs=float(getattr(sys.modules[__name__], "_last_speech_secs", 0.0)),
            stt_text=text,
            language=lang,
            pre_roll_ms=int(silence_duration * 1000),
        ),
    )
    return text, lang, audio


# ── TTS ───────────────────────────────────────────────────────────────────────
async def speak(text: str, language: str = "en"):
    """TTS: Kokoro (primary, local) → Piper English (fallback, local)."""
    if not text or not text.strip():
        return

    text = _clean_for_tts(text)
    if not text:
        return

    print(f"[Audio] TTS {_now_log_ts()}: '{text}'")

    try:
        loop = asyncio.get_running_loop()
        pcm, sample_rate = await loop.run_in_executor(None, _tts_kokoro, text)
        if pcm is None or len(pcm) == 0:
            print(f"[Audio] Piper fallback: Kokoro returned empty — using Piper")
            pcm, sample_rate = await loop.run_in_executor(None, _tts_piper_en, text)

        if pcm is None or len(pcm) == 0:
            return

        sd.stop()  # stop any filler or previous audio before starting response
        sd.play(pcm, samplerate=sample_rate)
        # sd.wait() blocks until the buffer is truly drained — more reliable than
        # asyncio.sleep(duration) which can fire early when the event loop is busy.
        await loop.run_in_executor(None, sd.wait)
        sd.stop()
        global _tts_end_time
        _tts_end_time = time.time()

        # P0.0.7 H10 — emit tts_out event after successful playback.
        _emit_tts_event_safe(
            text=text, language=language, was_stream=False,
            pcm_len=len(pcm) if pcm is not None else 0,
            sample_rate=sample_rate,
        )

    except (sd.PortAudioError, OSError) as e:
        # P0.R10 D2.a — speaker device failure: log + record for burst
        # detection + return silently (caller's contract preserved).
        print(f"[Audio] WARN speaker device failure in speak: {e!r}")
        _record_audio_failure("speaker")
        return
    except Exception as e:
        print(f"[Audio] TTS error: {e}")


def _emit_tts_event_safe(*, text: str, language: str, was_stream: bool,
                        pcm_len: int, sample_rate: int) -> None:
    """P0.0.7 H10 single producer location for tts_out events.

    Called by both speak() and speak_stream() so D7 N=1 holds. Delegates
    to `safe_emit_sync` so any event_log failure never breaks TTS playback
    (the single P0.4-annotated except block lives inside safe_emit_sync).
    """
    import hashlib as _h10_hash
    from core.event_log import safe_emit_sync, TtsOutPayload
    _full_hash = "sha256:" + _h10_hash.sha256(text.encode("utf-8")).hexdigest()[:16]
    _truncated = text if len(text) <= 500 else (text[:497] + "...")
    _duration_ms = (int(pcm_len / max(1, sample_rate) * 1000)
                   if pcm_len > 0 else None)
    safe_emit_sync(
        "tts_out",
        TtsOutPayload(
            text=_truncated,
            text_full_hash=_full_hash,
            language=language,
            was_stream=was_stream,
            purpose="conversation",  # generic; specific purpose threading is a follow-up
            duration_ms_est=_duration_ms,
        ),
    )


def _tts_piper_en(text: str) -> tuple[np.ndarray | None, int]:
    """Generate speech with Piper TTS English fallback (local, offline).

    Returns (pcm_float32, sample_rate) or (None, 0) if model is not available.
    """
    global _piper_en_voice
    if _piper_en_voice is None:
        model_path = PIPER_MODELS_DIR / _PIPER_EN_MODEL
        if not model_path.exists():
            return None, 0
        from piper import PiperVoice
        print("[Audio] Loading Piper English voice...")
        _piper_en_voice = PiperVoice.load(str(model_path))

    raw = b"".join(_piper_en_voice.synthesize_stream_raw(text))
    if not raw:
        return None, 0

    # Piper outputs int16 PCM — convert to float32 for sounddevice
    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return pcm, _piper_en_voice.config.sample_rate


def _tts_kokoro(text: str) -> tuple[np.ndarray, int]:
    """Generate speech with Kokoro (local, English)."""
    kokoro = _load_kokoro()
    samples, sample_rate = kokoro.create(
        text, voice="af_heart", speed=1.0, lang="en-us"
    )
    return samples.astype(np.float32), sample_rate


async def speak_stream(sentences, language: str = "en"):
    """
    Speak an async iterable of sentences with synthesis-playback pipelining.
    Sentence N+1 is synthesized (in executor) while sentence N is playing,
    so there is no idle gap waiting for TTS between sentences.
    """
    loop = asyncio.get_running_loop()
    # maxsize=2: synthesizer stays at most one sentence ahead of playback
    audio_q: asyncio.Queue = asyncio.Queue(maxsize=2)
    # P0.0.7 H10 — accumulate the streamed text for the tts_out event
    # emitted at stream-end. Per-sentence emission would N>1 violate D7.
    _streamed_text_parts: list[str] = []
    _streamed_total_pcm_len: int = 0
    _streamed_sample_rate: int = 0

    async def _synth_worker():
        nonlocal _streamed_total_pcm_len, _streamed_sample_rate
        try:
            async for sentence in sentences:
                if not sentence.strip():
                    continue
                sentence = _clean_for_tts(sentence)
                if not sentence:
                    continue
                print(f"[Audio] TTS stream {_now_log_ts()}: '{sentence}'")
                _streamed_text_parts.append(sentence)
                try:
                    pcm, sr = await loop.run_in_executor(None, _tts_kokoro, sentence)
                    if pcm is None or len(pcm) == 0:
                        print(f"[Audio] Piper fallback: Kokoro returned empty — using Piper for '{sentence[:40]}'")
                        pcm, sr = await loop.run_in_executor(None, _tts_piper_en, sentence)
                    if pcm is not None and len(pcm) > 0:
                        _streamed_total_pcm_len += len(pcm)
                        _streamed_sample_rate = sr or _streamed_sample_rate
                        await audio_q.put((pcm, sr))
                except Exception as e:
                    print(f"[Audio] Synthesis error for sentence: {e}")
        finally:
            await audio_q.put(None)  # sentinel — guaranteed even on exception/cancellation

    async def _play_worker():
        global _tts_end_time
        first = True
        # P0.R10 D2.b Q2 (b) RATIFIED — per-sentence count tracking for
        # diagnostic context on mid-stream device failures. _sentence_total
        # bumps when each item is dequeued; _sentence_count bumps after
        # each successful playback.
        _sentence_count = 0
        _sentence_total = 0
        while True:
            try:
                item = await audio_q.get()
                if item is None:
                    break
                _sentence_total += 1
                pcm, sr = item
                if first:
                    sd.stop()  # stop any pre-rendered filler
                    first = False
                sd.play(pcm, samplerate=sr)
                # sd.wait() blocks until playback is truly done — more reliable than
                # asyncio.sleep(duration) which can fire early when the event loop
                # is busy (BrainAgent tasks, network callbacks), clipping the last word.
                await loop.run_in_executor(None, sd.wait)
                _tts_end_time = time.time()  # set after actual hardware completion
                _sentence_count += 1
                print(f"[Audio] Playback complete — echo window reset ({_now_log_ts()})")
            except (sd.PortAudioError, OSError) as e:
                # P0.R10 D2.b Q2 (b) RATIFIED — speaker device failure mid-stream:
                # abort whole stream + record once + log per-sentence count for
                # diagnostic context. Caller's contract preserved (no exception
                # propagates); synth_worker drains naturally on cancellation.
                print(
                    f"[Audio] WARN speaker device failure in speak_stream "
                    f"(sentence {_sentence_count}/{_sentence_total}): {e!r}"
                )
                _record_audio_failure("speaker")
                break
            except Exception as e:
                print(f"[Audio] Playback error: {e}")
                break

    await asyncio.gather(_synth_worker(), _play_worker())

    # P0.0.7 H10 — emit one tts_out event for the whole stream at exit.
    # Accumulated text + total PCM length give the replay tool the same
    # shape as a non-stream tts_out event with was_stream=True.
    if _streamed_text_parts:
        _emit_tts_event_safe(
            text=" ".join(_streamed_text_parts),
            language=language,
            was_stream=True,
            pcm_len=_streamed_total_pcm_len,
            sample_rate=_streamed_sample_rate or 24000,
        )


def speak_sync(text: str):
    asyncio.run(speak(text))


def stop_audio():
    """Stop all active audio playback and unblock record_until_silence().
    Safe to call at any time, including during shutdown."""
    try:
        sd.stop()
    except (sd.PortAudioError, OSError):
        pass  # CLEANUP: sd.stop() raises if no active stream or device gone — interrupt flag still set
    except Exception:
        pass  # CLEANUP: defensive — preserves P0.4 silent-except policy
    _interrupt_flag.set()