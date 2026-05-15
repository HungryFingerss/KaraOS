"""
pipeline.py — Main loop
See face → identify → greet → listen → respond → repeat
"""
import asyncio
import concurrent.futures
import dataclasses
import datetime
from enum import Enum, auto
import json
import os
import re
import signal
import sys
import tempfile

# Force UTF-8 output so Telugu/Hindi/etc. and Unicode arrows don't crash on Windows cp1252
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Tee stdout+stderr to terminal_output.md so long sessions aren't lost to terminal scroll.
# P1.5: prior session's log is renamed to a timestamped archive before the new
# session starts; fresh per session, but all history preserved for the
# golden-intent harvest script (tests/harvest_golden.py). Line-buffered so
# nothing is lost on crash.
import datetime as _dt
import pathlib as _pathlib
import queue as _log_queue_mod
import threading as _log_thread_mod

_LOG_PATH = _pathlib.Path(__file__).parent / "terminal_output.md"


def _archive_terminal_output(log_path: _pathlib.Path = _LOG_PATH) -> "_pathlib.Path | None":
    """P1.5 data-accumulation hook: rename an existing terminal_output.md to a
    timestamped archive file so fresh sessions start clean AND historical logs
    are preserved for the golden-intent harvest script.

    Naming: ``terminal_output_YYYY-MM-DD_HHMMSS.md`` — timestamped from the
    file's mtime (when the PRIOR session wrote its last byte), not from now,
    so the archive name reflects the actual session boundary. Collision-safe:
    if the target already exists a trailing ``_1``, ``_2`` etc. is appended.

    Returns the archive path, or ``None`` if there was no file to archive.
    Safe to call on first run (no-op when log_path missing) and on zero-byte
    files (still archives so the harvest can audit 'prior session produced no
    output').

    Reverses Session 24's A6 (open mode "a" → "w") but preserves the same
    property (all prior logs retrievable) — just distributed across files
    rather than concatenated in one."""
    if not log_path.exists():
        return None
    mtime = _dt.datetime.fromtimestamp(log_path.stat().st_mtime)
    stem = f"terminal_output_{mtime.strftime('%Y-%m-%d_%H%M%S')}"
    candidate = log_path.parent / f"{stem}.md"
    suffix = 1
    while candidate.exists():
        candidate = log_path.parent / f"{stem}_{suffix}.md"
        suffix += 1
    # Windows holds the file when a prior pipeline.py process didn't fully
    # release the handle (orphaned hung process, IDE still tailing the file,
    # antivirus scan in progress). The rename then raises WinError 32 and
    # the bare exception kills module import. Catch + log + skip the
    # archive — preserving session continuity is more important than
    # archive hygiene; the user can rename the file manually after the
    # blocking process is killed.
    try:
        log_path.rename(candidate)
    except (OSError, PermissionError) as e:
        print(
            f"[Pipeline] WARN: could not archive {log_path.name} "
            f"({type(e).__name__}: {e!r}). Continuing without archive — "
            f"investigate which process is holding the file.",
            flush=True,
        )
        return None
    return candidate


_archived_log = _archive_terminal_output()

_LOG_FILE = open(
    _LOG_PATH,
    # P1.5: fresh per session now — prior session's content is preserved in
    # the timestamped archive returned by _archive_terminal_output above.
    "w", encoding="utf-8", buffering=1,
)

# Non-blocking log queue: print() puts messages here; a daemon thread drains them.
# This prevents terminal I/O from ever stalling the asyncio event loop.
_log_q: "_log_queue_mod.SimpleQueue[tuple[object, str]]" = _log_queue_mod.SimpleQueue()

def _log_drain() -> None:
    """Daemon thread — writes queued log messages to terminal + log file."""
    while True:
        stream, data = _log_q.get()
        try:
            stream.write(data)
            stream.flush()
        except Exception:
            pass  # OPTIONAL: raising kills the daemon and silences all subsequent logging
        try:
            _LOG_FILE.write(data)
            _LOG_FILE.flush()
        except Exception:
            pass  # OPTIONAL: raising kills the daemon and silences all subsequent logging

_log_drain_thread = _log_thread_mod.Thread(target=_log_drain, daemon=True, name="log-writer")
_log_drain_thread.start()

class _Tee:
    def __init__(self, stream):
        self._s = stream
    def write(self, data: str) -> int:
        if data:
            _log_q.put((self._s, data))
        return len(data) if data else 0
    def flush(self):
        pass  # background thread handles all flushing
    def __getattr__(self, name):
        return getattr(self._s, name)

sys.stdout = _Tee(sys.stdout)
sys.stderr = _Tee(sys.stderr)

# P1.5: announce the archive AFTER the tee is wired so the message lands in
# both terminal AND the new log file (harvest script can correlate archives
# to session boundaries).
if _archived_log is not None:
    print(f"[Pipeline] Prior session log archived → {_archived_log.name}")

import time
import uuid

# Session 114 Part 1 — startup warning suppression + TF32 enable.
# Must run BEFORE pyannote / speechbrain / torch are imported so the
# settings + filters are in place when those libraries init.
import warnings as _w114
# (1A) SpeechBrain 1.0 emits a deprecation warning when anything walks
# the speechbrain.pretrained alias (often via inspect.getmembers during
# pyannote setup). Our code uses speechbrain.inference; the warning is
# noise but routes through inspect.py so module-scoped filters miss it.
# Match by message pattern.
_w114.filterwarnings(
    "ignore",
    message=r".*speechbrain\.pretrained.*deprecated.*",
    category=UserWarning,
)
# (1C) Pyannote 3.3.2 numerical edge case during pooling — std() with 1
# sample logs a "degrees of freedom <= 0" warning. Pyannote handles the
# resulting NaN gracefully but the warning clutters every diarize call.
# Re-evaluate when pyannote upgrades.
_w114.filterwarnings(
    "ignore",
    message=r".*degrees of freedom.*",
    category=UserWarning,
)
# Session 118 Fix B — pyannote `ReproducibilityWarning` for TF32. Session
# 114's broad UserWarning filter doesn't catch this because pyannote uses
# a custom warning class (subclass of UserWarning, but Python's filter
# matches by class identity, not the inheritance chain when a specific
# class is named). Pyannote also re-disables TF32 internally on every
# module import — even though we set the flags True above, pyannote's
# init path flips them to False and emits the warning. Dual approach:
# (a) message-pattern filter matches before pyannote loads, (b) try
# class-import filter as defense-in-depth (works once pyannote is on
# the import path). Both run before any pyannote import.
_w114.filterwarnings(
    "ignore",
    message=r".*TensorFloat-32.*disabled.*",
)
_w114.filterwarnings(
    "ignore",
    message=r".*TF32.*",
)
try:
    from pyannote.audio.utils.reproducibility import ReproducibilityWarning as _ReproWarn
    _w114.filterwarnings("ignore", category=_ReproWarn)
except (ImportError, AttributeError):
    # Class isn't on the import path yet (pyannote not installed in
    # tests, or class moved in a future version). Message filters
    # above remain in place as fallback.
    pass
# (1B) TF32 — pyannote disables it for bit-exact reproducibility but our
# diarization runs are independent best-effort. Re-enabling gains a
# small perf win on Ampere/newer GPUs without affecting correctness.
try:
    import torch as _torch114
    _torch114.backends.cuda.matmul.allow_tf32 = True
    _torch114.backends.cudnn.allow_tf32 = True
except Exception:
    # No CUDA / no torch attribute path — silent. Suppression of the
    # warning still works because we set the flags before pyannote loads.
    pass  # OPTIONAL: no CUDA or no torch — TF32 performance opt skipped

import cv2
import numpy as np
from core.config import (
    CAMERA_INDEX, RECOGNITION_THRESHOLD,
    GREET_COOLDOWN, SELF_UPDATE_THRESHOLD, SELF_UPDATE_COOLDOWN,
    FACES_DIR, MAX_EMBEDDINGS, FACE_LOSS_GRACE, VOICE_SESSION_TIMEOUT,
    ENROLL_REQUEST_FILE, ENROLL_RESULT_FILE,
    RESET_REQUEST_FILE, RESET_RESULT_FILE,
    SMART_TURN_SILENCE, ADDENDUM_ONSET_WINDOW,
    VOICE_RECOGNITION_THRESHOLD, VOICE_SPEAKER_SWITCH_THRESHOLD, MAX_VOICE_EMBEDDINGS, N_INITIAL_VOICE,
    VOICE_ROUTING_FACE_STALE_SECS,
    DIARIZE_MIN_SECS, MIC_SAMPLE_RATE,
    VISION_YOLO_ENABLED, VISION_YOLO_MODEL, VISION_DETECT_EVERY, VISION_DETECT_CONF,
    DEFAULT_SYSTEM_NAME,
    EMOTION_FACT_VALIDITY_HOURS,
    IDENTITY_SOFT_THRESHOLD, IDENTITY_ASK_THRESHOLD, IDENTITY_AUTO_THRESHOLD,
    BRIEFING_MIN_ABSENCE,
    ANTISPOOFING_ENABLED, ANTISPOOFING_THRESHOLD,
    HISTORY_OVERRIDE_TOOLS, TOOL_REPEAT_MAX_CONSECUTIVE,
    CONVERSATION_HISTORY_LIMIT,
    FACE_QUALITY_PRESENCE, FACE_QUALITY_RECOGNITION, FACE_QUALITY_ENROLLMENT, FACE_QUALITY_SELF_UPDATE,
)
from core.vision  import (
    FaceDetector, FaceEmbedder, Camera,
    TemporalEmbeddingBuffer, face_quality_score,
    estimate_yaw_from_landmarks, adaptive_threshold, LipTracker,
    AntiSpoofChecker, verify_live,
)
from core.db      import FaceDB, wipe_all
from core.brain   import ask, ask_offline, ask_retry_text, ask_stream, ping_together, generate_greeting, autocompact_history, choose_greeting_order, render_session_stable_prefix
from core.config  import CLOUD_OFFLINE_TIMEOUT, CLOUD_RETRY_INTERVAL, DREAM_IDLE_MINUTES, DREAM_COOLDOWN, DREAM_MAX_INTERVAL, KAIROS_SILENCE_THRESHOLD, KAIROS_COOLDOWN, STRANGER_REQUIRE_SYSTEM_NAME, SCENE_STALE_SECS, SCENE_BLOCK_ENABLED, SCENE_VOICE_STALE, STRANGER_TTL_DAYS, STRANGER_VOICE_TTL_DAYS, DISPUTE_MAX_DURATION, DISPUTE_RENAME_BLOCK_THRESHOLD, VALID_PERSON_TYPES, TOOL_PRIVILEGES, N_INITIAL_VOICE_BOOTSTRAP, VOICE_ACCUM_FACE_WITNESS_MIN_CONF, VOICE_ACCUM_FACE_WITNESS_MAX_AGE_SEC, VOICE_ACCUM_VOICE_SELF_MATCH_MIN, VOICE_ACCUM_MATURE_SAMPLE_COUNT, VOICE_ROUTING_MIDRANGE_SWITCH_MIN, VOICE_ROUTING_FACE_ASSIST_MIN, VOICE_ROUTING_SELF_MATCH_FLOOR, VOICE_ROUTING_SELF_MATCH_OFFSCREEN, VOICE_ROUTING_MIN_UTTERANCE_SECS, VOICE_ROUTING_SHORT_UTT_MISMATCH_ENABLED, VOICE_ROUTING_SHORT_UTT_FLOOR, VOICE_ROUTING_MIN_AUDIO_FOR_SCORE, VOICE_ROUTING_SHORT_UTT_AMBIGUOUS, VOICE_ROUTING_STRANGER_FLOOR, VOICE_ROUTING_SINGLE_SEGMENT_MISMATCH_ENABLED, VISION_SHADOW_INTERVAL_SECS, MEMORY_SPARSE_THRESHOLD, SYSTEM_NAME_ASSIGN_PATTERNS, PERSON_NAME_ASSIGN_PATTERNS, IDENTITY_DENIAL_PATTERNS, DISPUTE_AUTO_CLEAR_VOICE_MIN, DISPUTE_AUTO_CLEAR_VOICE_SOLO_MIN, DISPUTE_AUTO_CLEAR_CONSECUTIVE_TURNS, ENROLLMENT_RENAME_GRACE_SECS, ENROLLMENT_RENAME_VOICE_THRESHOLD, SCENE_VISITOR_RECENCY_SECS, KAIROS_PREFER_BEST_FRIEND, BATCH_GREETING_ENABLED, BATCH_GREETING_MIN_PEOPLE, BATCH_GREETING_LLM_TIMEOUT_SECS, ROOM_BLOCK_ENABLED, ROOM_BLOCK_TURN_CAP, ROUTING_USE_RECONCILER, STRANGER_IDENTITY_BLOCK_MIN_TURNS, SCENE_BLOCK_CACHE_ENABLED, SCENE_BLOCK_CACHE_MAX_ENTRIES
import core.config as config
from core         import voice as voice_mod
from core.audio   import record_until_silence, transcribe, speak, speak_stream, listen_and_transcribe, preload_models, stop_audio, play_filler, set_lip_active
from core.log_utils import _now_log_ts
# P0.13 — invariant constants live in core.pipeline_invariants so they can
# be imported by structural tests without triggering pipeline.py's heavy
# top-level side effects.
from core.pipeline_invariants import (
    REPEAT_GUARD_FIELDS,
    ALLOWED_REPEAT_GUARD_FUNCS,
)
from core.brain_agent  import BrainOrchestrator, _infer_location_zone as _brain_infer_zone
from core.session_state import SessionStore
from core.emotion      import EmotionAgent
from core import state
import jellyfish

def _name_heard_in(text: str, system_name: str) -> tuple[bool, str]:
    """Return (heard, method) — exact word-boundary match first, Metaphone phonetic fallback."""
    pattern = r'\b' + re.escape(system_name.lower()) + r'\b'
    if re.search(pattern, text.lower()):
        return True, "exact"
    target_code = jellyfish.metaphone(system_name)
    if target_code:
        for word in re.findall(r'\b[a-zA-Z]+\b', text):
            if jellyfish.metaphone(word) == target_code:
                return True, "phonetic"
    return False, ""


# Optional YOLO object detection — spatial memory disabled if ultralytics missing
try:
    from ultralytics import YOLO as _YOLO
    _YOLO_AVAILABLE = True
except ImportError:
    _YOLO_AVAILABLE = False
    print("[Pipeline] WARNING: ultralytics not installed — spatial memory disabled. Run: pip install ultralytics>=8.3.0")

_yolo_model:              object | None = None
_yolo_frame_counter:      int           = 0
_latest_yolo_detections:  list[dict]    = []   # most recent YOLO frame (updated every detect cycle)
_yolo_last_ran:           float         = 0.0  # epoch time of last successful YOLO run
_vision_last_heartbeat:       float         = 0.0  # epoch time of last [Vision] status print
_vision_last_heartbeat_state: str           = ""   # last printed heartbeat content — skip if unchanged
# Phase 2 — Vision Channel shadow logging (Session 124, 2026-04-28).
# Throttled to VISION_SHADOW_INTERVAL_SECS so observe_scene's extra
# embed+recognize cost is bounded. 0.0 means "fire on first scan".
_last_vision_shadow_at:       float         = 0.0
# Dedicated single-thread executor for YOLO — isolates CPU-heavy PyTorch inference
# from the default executor used by face detection, voice ID, and emotion agent.
# This prevents GIL contention that would otherwise stall httpx LLM streaming.
_yolo_executor: "concurrent.futures.ThreadPoolExecutor | None" = None

# Identity hypothesis accumulator — updated each stranger turn by IdentityAgent.
# person_id → {name, relationship, confidence, matched_attrs, source_person_id}
_identity_hints: dict[str, dict] = {}

async def _lip_tracking_loop(camera: Camera) -> None:
    """
    Background task active during LISTENING.
    Uses the latest frame captured by _background_vision_loop (no extra camera reads —
    avoids racing with the background loop on the same VideoCapture object).
    """
    while True:
        frame = _latest_vision_frame
        if frame is not None and _last_active_bbox is not None:
            moving = lip_tracker.update(frame, _last_active_bbox)
            set_lip_active(moving)
        await asyncio.sleep(0.05)


# Extracts a name from natural-language phrases like "People call me Jagan".
# Searches ANYWHERE in the string (not just at start) for name-introducing patterns.
_NAME_EXTRACT_RE = re.compile(
    r'(?:call\s+me|calls?\s+me|my\s+name(?:\'?s)?\s+is|name(?:\'?s)?\s+is|i\'m|i\s+am|i\s+go\s+by)\s+(.+)',
    re.IGNORECASE,
)
# Legacy prefix strip for simple cases like "My name is Jagan" at start of string.
_PHRASE_PREFIXES = re.compile(
    r"^(?:my name(?:'?s)?(?:\s+is)?|call me|i(?:'m| am)|i go by|name(?:'?s)?(?:\s+is)?|it(?:'?s)?(?:\s+is)?)\s+",
    re.IGNORECASE,
)


def sanitize_name(raw: str) -> tuple[str, str]:
    """Return (display_name, safe_id_component) from raw user-supplied input.

    Extracts the actual name from natural-language phrases like
    "People call me Jagan", "My name is Jevin", "They call me Rex".
    Searches for name-introducing patterns ANYWHERE in the string,
    not just at the start.

    display_name     — extracted name, stripped to 50 chars, used in TTS greetings.
    safe_id_component — lowercase [a-z0-9_] only, max 50 chars, used as the
                        human-readable prefix of person_id filesystem paths.
    """
    text = raw.strip()
    # Try to extract name from phrases like "People call me Jagan" anywhere in string
    m = _NAME_EXTRACT_RE.search(text)
    if m:
        extracted = m.group(1).strip(" .,!?\"'")
        # Take the first word of the extracted part (the actual name)
        first = extracted.split()[0] if extracted else ""
        extracted = first if len(first) >= 2 else extracted
    else:
        # Fallback: strip known prefixes at start, take first word
        stripped = _PHRASE_PREFIXES.sub("", text).strip(" .,!?\"'")
        first    = stripped.split()[0] if stripped else ""
        extracted = first if len(first) >= 2 else stripped
    display = (extracted if len(extracted) >= 2 else text)[:50]
    safe = re.sub(r"[^a-z0-9_-]", "_", display.lower())
    safe = re.sub(r"_+", "_", safe).strip("_")[:50]
    if not safe:
        safe = "unknown"
    return display, safe


# Per-tool silent fallback spoken when the LLM calls a tool with no text.
# Names that are clearly placeholder/invalid and should never be stored.
_INVALID_SYSTEM_NAMES = frozenset({"none", "unknown", "unnamed", "noname", "null", "undefined", "n_a", "na"})

# Detects questions ABOUT shutdown (not commands to shutdown).
# "why did you shut down?" or "when did you turn off?" → question, not command.
_SHUTDOWN_QUESTION_RE = re.compile(
    r'\b(?:why|how|when|what|did|do|does|was|were|would|could)\b.{0,40}'
    r'\b(?:shut\s*down|shutdown|turn\s*off|goodbye|sleep|stop)\b',
    re.IGNORECASE,
)

# Spoken fallback when LLM calls a tool but returns no text.
# Every tool MUST have a non-empty fallback to prevent silent turns.
_TOOL_FALLBACKS: dict[str, str] = {
    "update_person_name":    "Got it.",
    "update_system_name":    "What name would you like to give me?",
    "shutdown":              "Goodbye!",
    "search_web":            "One moment.",
    "search_memory":         "Let me think about that.",
}


def _face_in_frame(pid: str, persons_in_frame: dict) -> bool:
    """Return True only if ``persons_in_frame[pid]`` has a face-sourced entry.

    Voice ID also writes into ``_persons_in_frame`` (to track "who just spoke")
    with ``source="voice"``. Routing, scene, and left-frame logs must not treat
    those as face presence — a voice-only speaker whose pid appears in the dict
    should NOT trigger the "face+voice agree" confident-switch shortcut, and
    should NOT be reported as visibly present in the scene block.

    Bug B (2026-04-20 live run): Chloe (voice-only) was routed through the
    face+voice-agree path and rendered as "[Vision] Chloe — speaking now" in
    the scene block despite never being on camera.
    """
    entry = persons_in_frame.get(pid)
    return entry is not None and entry.get("source") != "voice"


def _has_recent_face_evidence(person_id: str) -> bool:
    """True iff ``_persons_in_frame`` has a recent face-source entry for person_id.

    Voice-only entries (source='voice') do NOT count — distinguishing them is the
    entire point of the Bug B fix (Session 64). Used by the Wave 2 Item 9 heuristic
    to decide whether a thin-gallery known/best_friend session was originally
    voice-only.
    """
    entry = _persons_in_frame.get(person_id)
    if not entry:
        return False
    if entry.get("source") == "voice":
        return False
    last_seen = entry.get("last_seen", 0.0)
    return (time.time() - last_seen) < SCENE_STALE_SECS


def _tool_allowed(tool_name: str, caller_type: str) -> bool:
    """Return True iff ``caller_type`` is permitted to invoke ``tool_name``.

    Fail-closed: tools NOT in ``TOOL_PRIVILEGES`` are BLOCKED (treated as
    always-disallowed). Missing-table entries are a configuration bug — the
    startup assertion in run() ensures every tool in brain.TOOLS has a row
    here, so this path fires only for genuinely unregistered callers.
    """
    allowed = TOOL_PRIVILEGES.get(tool_name)
    if allowed is None:
        return False  # unregistered tool → blocked (fail-closed)
    return caller_type in allowed


def _is_enrollment_mishear_candidate(
    db: "FaceDB | None",
    person_id: str,
    session,
) -> bool:
    """Session 100 Bug F — is this a fresh-enrollment session whose stored
    name has no voice corroboration yet, so a speaker-grounded rename should
    flow through the stranger-promotion chain instead of flipping to
    disputed?

    2026-04-23 canary scenario: STT heard "My name is Jagan" as "My name
    is Gevan" at first-boot enrollment. Jagan's corrective "No, my name
    is Jagan" landed on a best_friend session whose ONLY corroboration
    was the face match — voice profile was empty, session was seconds old.
    The classic dispute-flip ('known'/'best_friend' rename-on-session =
    suspicious sensor) was designed for mid-session impersonation attempts,
    not for enrollment-mishear correction. This helper distinguishes the
    two cases by checking:

      1. Session started within ENROLLMENT_RENAME_GRACE_SECS. A week-old
         session with mature voice history has had plenty of opportunity
         for the user to correct a wrong name — the grace window is
         short enough that 'I've been called Gevan for a month and now
         I'd like to switch to Jagan' does NOT qualify.
      2. DB voice embedding count < ENROLLMENT_RENAME_VOICE_THRESHOLD.
         Below this floor, the system has not yet accumulated enough
         voice data to independently corroborate the stored name — the
         face match is the only evidence, and face + self-assertion is
         sufficient grounds to rename.

    Caller must have ALREADY validated the rename claim against the
    classifier (assign_own_name intent, grounded in user_text) — this
    helper only makes the routing decision between dispute-flip and
    promotion-chain rename; it is not itself a security gate.
    """
    started_at = float(session.started_at if session is not None else 0.0)
    if started_at <= 0 or time.time() - started_at > ENROLLMENT_RENAME_GRACE_SECS:
        return False
    if db is None:
        # No DB means we can't verify voice count — fail to the safer
        # dispute-flip path. In production the db arg is always set.
        return False
    try:
        voice_n = db.voice_embedding_count(person_id)
    except Exception:
        return False
    return voice_n < ENROLLMENT_RENAME_VOICE_THRESHOLD


def _is_disputed(pid_or_session) -> bool:
    """Single source of truth for "is this session in disputed state?".

    Session 73 (Bug D4, 2026-04-22 live run): before this helper, the dispute
    check was scattered across 9 sites in pipeline.py with raw ``==
    "disputed"`` comparisons. Each site independently decided what to do with
    the dispute signal (skip log_turn, skip extraction, refuse KAIROS, label
    the scene, gate privileges, etc.). A new disputed-check is easy to forget
    — the classic "distributed policy = missing policy" antipattern. Routing
    every check through this helper + the grep-invariant source-inspection
    test makes policy drift visible at CI time.

    Accepts either a ``person_id`` (str — looks up ``_session_store.peek_snapshot()``) or
    a pre-fetched session dict (dict — inspects directly). Returns False for
    missing / unknown sessions (fail-open for readers, fail-closed for
    writers: the LLM doesn't accidentally get "disputed" privileges just
    because the session vanished).
    """
    if isinstance(pid_or_session, dict):
        return pid_or_session.get("person_type") == "disputed"
    # Treat None / empty string as "no session" → not disputed.
    if not pid_or_session:
        return False
    _disp_snap = _session_store.peek_snapshot(pid_or_session)
    return _disp_snap is not None and _disp_snap.person_type == "disputed"


def _user_text_gate_passes(
    user_text: "str | None",
    new_value: "str | None",
    assign_patterns: tuple,
    *,
    reject_on_empty_user_text: bool = True,
) -> bool:
    """Server-side user-text gate — shared primitive for side-effect tools.

    Session 73 (Bugs G1-G4, 2026-04-22 live run): every side-effect tool must
    verify the LLM's action matches what the user actually said. The old
    Session 71 gate used OR-logic (name appeared in turn OR assignment phrase
    present) which let "do you know the GAME called Detroit?" pass as a valid
    name assignment. This primitive enforces a stricter contract: the
    assignment phrase itself must contain the name as a capture group.

    Three usage modes:
      1. Name-verify gate (``new_value`` is str): a pattern must match AND
         its first capture group (case-insensitively) must equal new_value.
         Used for update_system_name, update_person_name, auto-confirm.
      2. Denial-signal gate (``new_value`` is None): any pattern match
         suffices — no name-capture verification. Used for
         report_identity_mismatch where the gate just needs a clear denial.
      3. Empty user_text path: default REJECT (``reject_on_empty_user_text
         = True``). Mutation tools firing via KAIROS proactive prompts have
         no user utterance to verify against — the LLM is acting unilaterally,
         which is the exact risk class these gates exist to block.

    The existing shutdown handler has its own hand-rolled gate and is NOT
    migrated to this primitive.
    """
    import re as _re
    _lt = _nfkc_lower(user_text).strip()
    if not _lt:
        return not reject_on_empty_user_text
    _nv_lower = _nfkc_lower(new_value).strip() if new_value is not None else None
    for pat in assign_patterns:
        m = _re.search(pat, _lt, _re.IGNORECASE)
        if not m:
            continue
        if new_value is None:
            # Denial-signal gate — match alone is sufficient.
            return True
        if not m.groups():
            continue
        _captured = _nfkc_lower(m.group(1)).strip()
        # Exact match — the captured single-word name equals the proposal.
        if _captured == _nv_lower:
            return True
        # P0.3 fix (multi-word contiguous substring): (\w+) captures only the
        # first word — "call me Sarah Jane" → capture="sarah", proposal=
        # "sarah jane". Accept iff proposal STARTS with the captured word AND
        # the FULL proposal appears as a contiguous substring of user_text.
        # Contiguous check prevents the LLM from combining words from different
        # parts of the utterance ("call me sarah … is jane" ≠ "Sarah Jane").
        # NFKC applied above defeats homoglyph spoofing on all three inputs.
        if _captured and _nv_lower.startswith(_captured):
            if _nv_lower in _lt:
                return True
    return False


# ── VISION_ROADMAP P1.4 — structured intent validator ────────────────────────
# Paired with the shadow classifier in core.brain._classify_intent (P1.3).
# Gated behind INTENT_FALLBACK_TO_REGEX=True: these helpers produce the
# SHADOW verdict; the existing regex gates (Sessions 71-74) remain the
# source of truth for mutation tool dispatch until P1.17 flips the flag.
def _nfkc_lower(s: "str | None") -> str:
    """NFKC-normalized casefold — defeats Unicode homoglyph spoofing.

    Threat model (per architect review): the classifier may extract "Kаra"
    (Cyrillic а, U+0430) when the user actually said "Kara" (Latin a).
    Without normalization the grounding check would compare two different
    code points as if they were the same — a classic spoofing surface.
    NFKC collapses compatibility variants; casefold handles case-insensitive
    comparison more robustly than lower() for Unicode."""
    import unicodedata as _ud
    return _ud.normalize("NFKC", (s or "")).casefold()


def _strip_im_contraction(s: "str | None") -> str:
    """Session 94 Fix #2: strip leading ``Im`` / ``I'm`` / ``I\u2019m`` contraction.

    Whisper occasionally compresses ``I'm <Name>`` into ``Im<Name>`` (no
    space, no apostrophe) — observed in the 2026-04-22 live canary where
    "I'm Lexi" became "Imlexi" in the STT. Whisper also loses the capital
    on the following letter in the compression (so "Imlexi" has lowercase
    'l', not uppercase 'L'). When this lands in either the classifier's
    ``extracted_value`` or the LLM's ``tool_args[arg_key]``, grounding
    fails spuriously ("Imlexi" isn't a substring of "I'm Lexi", even
    though semantically they're the same name).

    Requires the INITIAL letter to be capital ``I`` (distinguishes the
    first-person pronoun start from mid-sentence words). Accepts either
    case for the letter after ``m``, since Whisper's compression
    occasionally drops the name's capital. False positive: "Important" at
    the start of an extracted_value/tool_arg would strip to "portant" —
    acceptable trade-off because those inputs should be names, not common
    words. Returns input unchanged when no match or input empty."""
    if not s:
        return s or ""
    import re as _re
    m = _re.match(r"^I['\u2019]?m([a-zA-Z].*)$", s)
    return m.group(1) if m else s


def _intent_allows(
    tool_name: str,
    turn_intent: str,
    confidence: float,
    extracted_value: "str | None",
    user_text: str,
    tool_args: dict,
) -> tuple[bool, str]:
    """P1.4 server-side validator consuming the shadow classifier's sidecar.

    Four rules, checked in order (short-circuit on first failure):
      1. Tool pass-through — not in TOOL_INTENT_MAP → (True, "tool not gated")
      2. Intent match — classifier's turn_intent must equal the tool's required
      3. Confidence floor — shutdown uses INTENT_SHUTDOWN_CONF_MIN (0.80),
         all others use INTENT_CONFIDENCE_MIN (0.75)
      4. Grounding + arg cross-check — when extracted_value is non-empty:
         - NFKC-casefolded extracted_value must be a substring of NFKC-casefolded
           user_text (defeats homoglyph spoofing + case/whitespace variance)
         - When the tool has arg_key, NFKC-casefolded tool_args[arg_key] must
           equal NFKC-casefolded extracted_value (catches the LLM fabricating
           a rename-target that differs from what the user actually said)

    Returns (allowed, reason). reason is a short diagnostic for the [Intent]
    log line. Session 80 observation: the dual gate (intent + confidence) is
    robust to both classifier failure modes seen in live data — wrong-label-
    low-conf (Turn 19) and conservative-label-high-conf (Turn 23). This
    validator relies on that robustness.

    Shadow mode: callers MUST continue using the regex gate for dispatch
    decisions until INTENT_FALLBACK_TO_REGEX flips to False at P1.17. The
    validator's verdict is logged side-by-side with the regex verdict so
    divergences are observable and the calibration corpus keeps growing."""
    from core.config import (
        TOOL_INTENT_MAP, INTENT_CONFIDENCE_MIN, INTENT_SHUTDOWN_CONF_MIN,
    )
    required, arg_key = TOOL_INTENT_MAP.get(tool_name, (None, None))
    if required is None:
        return (True, "tool not gated")
    if turn_intent != required:
        return (False, f"intent={turn_intent} expected={required}")
    min_conf = (
        INTENT_SHUTDOWN_CONF_MIN if tool_name == "shutdown"
        else INTENT_CONFIDENCE_MIN
    )
    if confidence < min_conf:
        return (False, f"confidence {confidence:.2f} < {min_conf}")
    if extracted_value:
        # Session 94 Fix #2: strip Whisper's "Im"/"I'm" contraction prefix
        # before grounding check. "Imlexi" vs user_text "I'm Lexi" (clean
        # STT) would fail substring match without this; after stripping
        # both sides to "Lexi", grounding succeeds as intended.
        _ev_stripped = _strip_im_contraction(extracted_value)
        _ev = _nfkc_lower(_ev_stripped)
        _ut = _nfkc_lower(user_text)
        if _ev not in _ut:
            return (False, "extracted_value not grounded in user_text")
        if arg_key:
            _arg_raw = tool_args.get(arg_key, "")
            # Apply the same contraction-strip to tool_args so the
            # cross-check treats "Lexi" and "Imlexi" as equivalent when
            # one came from a clean STT and the other from a mangled one.
            _arg_stripped = _strip_im_contraction(_arg_raw)
            _arg = _nfkc_lower(_arg_stripped)
            if _arg != _ev:
                return (
                    False,
                    f"tool arg {_arg_raw!r} != user said {extracted_value!r}",
                )
    elif arg_key and tool_args.get(arg_key):
        # Session 87 grounding-gap fix: the Session 86 live run had a case
        # where the classifier honestly abstained (extracted_value=None,
        # intent=assign_own_name, conf=0.80) but the LLM still proposed a
        # ``{"name": "Kara"}`` arg hallucinated from history. The original
        # code's ``if extracted_value:`` block skipped all grounding when
        # the classifier said "I see the intent but can't extract a value",
        # so the hallucinated arg slipped through and renamed the person to
        # Kara. This elif catches the case: if the classifier didn't
        # extract but the LLM proposed an arg, the arg itself must appear
        # in user_text. Closes the silent-hallucination path that
        # accumulated one false rename in just 10 divergence rows of
        # production observation — would have grown into a pattern.
        # Session 94: also strip Im-contraction from the proposed arg.
        _proposed = tool_args[arg_key]
        _proposed_stripped = _strip_im_contraction(_proposed)
        if _nfkc_lower(_proposed_stripped) not in _nfkc_lower(user_text):
            return (
                False,
                f"tool arg {_proposed!r} not grounded (classifier extracted no value)",
            )
    return (True, "intent match")


def _log_intent_divergence(
    *,
    tool_name:    str,
    sidecar:      "dict | None",
    gate_decision: str,
    user_text:    "str | None" = None,
    person_id:    "str | None" = None,
    turn_id:      "int | None" = None,
) -> None:
    """P1.7a helper — one row per gated-tool decision that routes through
    the intent gate. Wraps ``BrainDB.log_intent_divergence`` with safe
    access so unit tests (and the early-boot path before the orchestrator
    is up) don't need to stand up a full brain pipeline.

    Callers should pass the sidecar dict from ``_classify_intent`` (or
    ``None`` when the classifier wasn't consulted — shadow-mode disabled,
    timeout, parse failure); we unpack the structured_* columns from it.
    ``gate_decision`` is a short free-form string encoding what happened:
    ``'allow'`` / ``'reject: <reason>'`` / ``'regex_fallback_allow'`` /
    ``'regex_fallback_reject'`` / ``'both_unavailable_allow_with_warning'``.

    Any exception is swallowed with a warning log — the gate's primary job
    is dispatch, not bookkeeping, and a write failure must not block the
    user's turn."""
    orch = _brain_orchestrator
    if orch is None:
        # Early boot / test fixture — orchestrator not yet initialized. Not
        # an error; log debug and move on.
        return
    brain_db = getattr(orch, "_brain_db", None)
    if brain_db is None:
        return
    si  = sidecar.get("turn_intent") if sidecar else None
    sv  = sidecar.get("extracted_value") if sidecar else None
    sc  = sidecar.get("confidence") if sidecar else None
    try:
        brain_db.log_intent_divergence(
            tool_proposed         = tool_name,
            gate_decision         = gate_decision,
            user_text             = user_text,
            person_id             = person_id,
            turn_id               = turn_id,
            structured_intent     = si,
            structured_extracted  = sv,
            structured_confidence = float(sc) if sc is not None else None,
        )
    except Exception as e:
        print(f"[Intent] divergence log write failed: {type(e).__name__}: {e}")


class PipelineState(Enum):
    WATCHING     = auto()  # scanning for faces
    LISTENING    = auto()  # recording speech
    THINKING     = auto()  # LLM processing
    SPEAKING     = auto()  # TTS playing
    ENROLLING    = auto()  # enrollment flow

_last_greeted:          dict[str, float]      = {}
_last_self_update:      dict[str, float]      = {}
_ambient_wake_pending:  set[str]              = set()  # person_ids whose wake signal is in-flight (debounce)
_voice_gallery:         dict                  = {}   # person_id → mean L2-normalized voice embedding
_voice_gallery_sizes:   dict                  = {}   # person_id → sample count (for profile-strength gating)
_sessions_started:      set[str]             = set() # person_ids with an active session (guards one-time setup)
_face_db_ref:           "FaceDB | None"       = None # Obs 1: module-level reference to FaceDB instance, set in run() — gives module-level helpers (e.g. _open_session) authoritative DB access for voice count fallback when the in-memory cache may be stale.

# ── Cloud health state ─────────────────────────────────────────────────────────
class CloudState(Enum):
    ONLINE  = auto()   # Together.ai working normally
    SICK    = auto()   # First failure — grace period, trying to recover
    OFFLINE = auto()   # >2 min failure — Ollama Q&A mode active

_cloud_state:         CloudState        = CloudState.ONLINE
_cloud_failed_at:     float             = 0.0
_cloud_recovered:     bool              = False   # flag: announce recovery on next turn
_cloud_monitor_task:  asyncio.Task | None = None

_last_dream_run_at:   "float | None"    = None   # Wave 5 Item 19: timestamp of last dream() completion
_health_log_task:     asyncio.Task | None = None  # background health log loop

_active_system_name: str = DEFAULT_SYSTEM_NAME   # loaded from system_identity at startup


def _prune_dict(d: dict, max_size: int = 100) -> None:
    """Evict the oldest-timestamp entry when dict exceeds max_size."""
    if len(d) > max_size:
        del d[min(d, key=d.get)]


def _infer_zone(bbox: tuple, frame_w: int, frame_h: int) -> str:
    """Map a face bounding box to a zone label using the shared brain_agent helper."""
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) / 2 / max(frame_w, 1)
    cy = (y1 + y2) / 2 / max(frame_h, 1)
    return _brain_infer_zone(cx, cy)


def _maybe_record_silent_obs(emb, bbox: tuple, frame_w: int, frame_h: int, db) -> None:
    global _last_silent_update
    if time.time() - _last_silent_update < 5.0:
        return
    _last_silent_update = time.time()
    zone = _infer_zone(bbox, frame_w, frame_h)
    db.update_silent_observation(emb, zone=zone)

_conversation:       dict                  = {}
_pipeline_state:     PipelineState         = PipelineState.WATCHING
_compact_pids:       set[str]              = set() # pids with a background compaction in flight
_session_store: SessionStore = SessionStore()  # P0.7 — typed session state (single source of truth)

# Session 112 Part 1 — room-session lifecycle. `_active_room_session` holds a
# single room_{timestamp}_{rand} identifier for as long as ANY person has an
# active session. Minted by the first _open_session call when no room is
# live; cleared by _close_session when the last person leaves. Wired into
# conversation_log.room_session_id (Session 107 Phase 3A.6 Part 3 column)
# via log_turn plumbing, and consumed by downstream room-scoped retrieval
# that arrives in 3B. Explicitly module-level so _open_session/_close_session
# can read-modify-write as globals.
_active_room_session: "str | None" = None
# Phase 3B.1 — wall-clock timestamp when the current room session was minted.
# Paired with _active_room_session lifecycle: set on mint in _open_session,
# cleared on room end in _close_session. Drives the "Room session started
# Xm ago" line in the <<<ROOM>>> block. None when no room is live.
_active_room_started_at: "float | None" = None
# Phase 3B.6 — accumulated set of person_ids who have participated in the
# current room session. Every _open_session into the live room adds to
# this set; cleared when the room ends. Drives synthesize_room's
# speaker_pids arg so the orchestrator knows who was there WITHOUT
# reading back _session_store at room-end time.
_active_room_participants: "set[str]" = set()
# Session 115 Fix 2 — best_friend row cache. db.get_best_friend() returns
# the same row every call until update_person_name fires (rare). Cached
# value short-circuits ~10ms per turn × 5+ call sites. Invalidated on
# rename success and factory reset paths. id(db) tracked so a fresh
# DB instance (test fixture) can't pick up a stale row.
_cached_bf_row: "dict | None" = None
_cached_bf_db_id: "int | None" = None
_last_active_bbox:   tuple | None          = None
lip_tracker =        LipTracker()
_detected_lang:      str                   = "en"
_last_face_seen:     float                 = 0.0
_latest_vision_frame: "np.ndarray | None"  = None  # updated by background vision task
_latest_frame_time:   float                 = 0.0   # monotonic timestamp of last good frame
# Created inside run() once the event loop is running; stored here so
# signal handlers (which fire outside the loop) can reference it.
_shutdown_event:     asyncio.Event | None      = None
_brain_orchestrator:    "BrainOrchestrator | None" = None  # set in run() after event loop starts
_emotion_agents:        dict                       = {}    # person_id → EmotionAgent; kept alive across sessions
_anti_spoof_checker:    "AntiSpoofChecker | None"  = None  # set in run(); None when ANTISPOOFING_ENABLED=False
_query_embedding_cache: dict                       = {}    # person_id → embedding from previous turn
_voice_tasks:           "set[asyncio.Task]"         = set() # pending fire-and-forget voice accumulation tasks
_last_user_speech_at:   float                       = 0.0   # epoch time of user's most recent utterance (KAIROS)
_last_silent_update:    float                       = 0.0   # throttle: write silent obs at most every 5s
_persons_in_frame:      dict[str, dict]             = {}    # person_id → {name, conf, last_seen} — all faces currently visible
_vision_face_scan_last: float                       = 0.0   # throttle: secondary face recognition in background vision loop
_vision_prev_det_count: int                         = 0     # face count from previous frame — spike triggers immediate scan
_last_kairos_at:        float                       = 0.0   # epoch time of most recent KAIROS proactive tick
_unrecognized_tracks:      dict = {}   # SORT track_id -> last_seen epoch; one entry per unrecognized face in frame
_unrecognized_embeddings:  dict = {}   # SORT track_id -> latest face embedding (np.ndarray), for gate-pass enrollment
_stranger_track_map:       dict = {}   # SORT track_id -> stranger_pid; stable face->session binding across turns
_track_identity:           dict = {}   # SORT track_id -> person_id; confirmed identity per live track (replaces soft-match)
_last_vision_report_str: str  = ""   # last emitted [Vision] line; suppresses duplicate emissions
# Wave 6 Item 23: scene_block string cache.
_scene_block_cache:        "dict[tuple, str]" = {}
_scene_block_cache_hits:   int                = 0
_scene_block_cache_misses: int                = 0



def _set_state(new_state: PipelineState, person_name: str = None):
    global _pipeline_state
    if new_state == _pipeline_state:
        return
    print(f"[Pipeline] State: {_pipeline_state.name} -> {new_state.name}")
    _pipeline_state = new_state
    mode_map = {
        PipelineState.WATCHING:    "watching",
        PipelineState.LISTENING:   "listening",
        PipelineState.THINKING:    "thinking",
        PipelineState.SPEAKING:    "speaking",
        PipelineState.ENROLLING:   "enrolling",
    }
    state.write(mode=mode_map[new_state], current_person=person_name)


def _primary_person_id() -> str | None:
    """Return the most recently active person's ID, or None if no active sessions."""
    _snaps = _session_store.peek_all_snapshots()
    if not _snaps:
        return None
    return max(_snaps, key=lambda s: (s.last_spoke_at, s.person_id)).person_id


def _primary_person_name() -> str | None:
    pid = _primary_person_id()
    if not pid:
        return None
    snap = _session_store.peek_snapshot(pid)
    return snap.person_name if snap is not None else None


def _kairos_preferred_speaker(best_friend_id: "str | None") -> "str | None":
    """Session 112 Part 2 — room-aware KAIROS speaker selection.

    Policy (gated by KAIROS_PREFER_BEST_FRIEND config flag — set False to
    revert to legacy `_primary_person_id()` behavior):
      1. Single-session room → return the one active pid (no choice).
      2. Multi-session room WITH best_friend active → prefer best_friend
         (natural engagement target for proactive content — household
         context, cross-person insights, safety summaries all surface
         best here).
      3. Multi-session room WITHOUT best_friend active → pick the pid
         with the LONGEST silence (largest now - last_spoke_at). The
         most-recent speaker just finished — they're the least likely
         to welcome a proactive interrupt. Quietest person is most
         likely to want engagement.

    Returns None when no sessions are active. Feature-flag fallback
    ensures a one-line rollback if the policy ever regresses in a live
    session: flip KAIROS_PREFER_BEST_FRIEND to False and `_primary_person_id`
    takes over.
    """
    _snaps_ks = _session_store.peek_all_snapshots()
    if not _snaps_ks:
        return None
    if len(_snaps_ks) == 1:
        return _snaps_ks[0].person_id
    if not KAIROS_PREFER_BEST_FRIEND:
        return _primary_person_id()
    if best_friend_id and any(s.person_id == best_friend_id for s in _snaps_ks):
        return best_friend_id
    # Longest-silence fallback: pick the pid whose last_spoke_at is oldest.
    now_ks = time.time()
    return max(
        _snaps_ks,
        key=lambda s: (
            now_ks - s.last_spoke_at,
            s.person_id,
        ),
    ).person_id


def _get_best_friend_cached(db) -> "dict | None":
    """Session 115 Fix 2 — cached `db.get_best_friend()` lookup. Same row
    every session unless update_person_name fires; cache invalidated by
    `_invalidate_bf_cache()` from the rename + factory-reset paths.

    Multi-instance safety: cached row is keyed by ``id(db)`` so a fresh
    test fixture or a post-factory-reset DB instance won't match the
    stale id and will re-query. ``None`` db → ``None`` (pre-init paths).
    """
    global _cached_bf_row, _cached_bf_db_id
    if db is None:
        return None
    db_id = id(db)
    if _cached_bf_row is not None and _cached_bf_db_id == db_id:
        return _cached_bf_row
    _cached_bf_row = db.get_best_friend()
    _cached_bf_db_id = db_id
    return _cached_bf_row


def _invalidate_bf_cache() -> None:
    """Drop the cached best_friend row. Call after update_person_name
    succeeds, after factory reset, and after first_boot_flow completes."""
    global _cached_bf_row, _cached_bf_db_id
    _cached_bf_row = None
    _cached_bf_db_id = None


def _resolve_addressed_to(
    parsed_addr: "str | None",
    active_sessions: "tuple",
    effective_name: str,
) -> str:
    """Session 113 Part 1 — resolve the LLM's [addressing:X] marker into
    the history's addressed_to field. Policy:
      - marker absent / empty / "current" → default to current speaker
      - marker names a person in active_sessions (case-insensitive) → use
        that person's canonical name from the session dict
      - marker names someone not active → log warning + fall back to the
        current speaker (safety property: the marker never silently
        corrupts history with an unverifiable name).

    Pulled out of conversation_turn so unit tests can exercise the three
    branches without the full turn surface.

    Session 113.1: emit an observability log line on every call so canary
    debugging can tell apart (a) "LLM emitted a marker that routed to X"
    vs (b) "LLM emitted no marker; default to current speaker." Prior to
    the log, canary analysis had no ground truth on whether Part 1's
    parser actually fired — a mis-address could be a broken marker parse
    OR a legit LLM decision, and we couldn't distinguish.
    """
    # Session 116 P1 #8 — address decision reasoning: surface the room
    # candidate count so an outside reviewer can see WHY the default
    # path was taken (single-person room → no override possible vs.
    # multi-person room → LLM chose to default).
    _candidate_count = len(active_sessions)
    if not parsed_addr or parsed_addr.strip().lower() == "current":
        print(
            f"[Pipeline] Turn addressed: {effective_name} (default; "
            f"candidates={_candidate_count})"
        )
        return effective_name
    addr_lc = parsed_addr.strip().lower()
    matched = next(
        (s.person_name for s in active_sessions
         if s.person_name.strip().lower() == addr_lc),
        None,
    )
    if matched:
        print(
            f"[Pipeline] Turn addressed: {matched} "
            f"(LLM: '[addressing:{parsed_addr}]'; candidates={_candidate_count})"
        )
        return matched
    print(
        f"[Pipeline] ADDRESS DECISION: unknown name {parsed_addr!r} "
        f"not in active sessions, falling back to {effective_name!r}"
    )
    print(f"[Pipeline] Turn addressed: {effective_name} (fallback)")
    return effective_name


_U2U_VOCATIVE_PATTERNS = [
    # Name at start with comma: "Lexi, do your homework"
    re.compile(r"^\s*([A-Za-z][\w'\-]+),\s+", re.UNICODE),
    # Name at end: "What about you, Jagan?" / "What do you think, Lexi?"
    re.compile(r",\s*([A-Za-z][\w'\-]+)[?.!]?\s*$", re.UNICODE),
    # Greeting + name: "Hey Jagan, ..." / "Hi Lexi, ..."
    re.compile(r"^\s*(?:Hey|Hi|Hello)\s+([A-Za-z][\w'\-]+)[,!?]?\s+", re.UNICODE | re.IGNORECASE),
]


def _user_to_user_heuristic(
    text: str,
    system_name: "str | None",
    other_session_names: "set[str]",
) -> "tuple[str, str] | None":
    """Session 115 Fix 1 — vocative-pattern check before the classifier.

    Returns one of:
      - ``("user_to_person", canonical_name)`` — vocative matches an
        active session's display name (NOT the system name). Caller
        should silent-skip without invoking the classifier.
      - ``("addressing_ai", system_name)`` — vocative is the system
        name; classifier is redundant (would return same conclusion).
        Caller should fall through to normal response path.
      - ``None`` — no clear vocative pattern. Caller should consult
        the classifier with cache for the ambiguous case.

    Match is case-insensitive (STT often lowercases). Multi-name
    utterances ("Lexi, tell Jagan about X") return the FIRST vocative
    match (whichever pattern fires earliest in the regex list).
    """
    if not text:
        return None
    for pat in _U2U_VOCATIVE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        candidate = m.group(1).strip()
        if not candidate:
            continue
        cand_lc = candidate.lower()
        # System name match wins first — overrides any homonym in the
        # session list because addressing the AI is unambiguous.
        if system_name and cand_lc == system_name.strip().lower():
            return ("addressing_ai", system_name)
        # Match against active session display names (case-insensitive).
        for sess_name in other_session_names:
            if not sess_name:
                continue
            if sess_name.strip().lower() == cand_lc:
                return ("user_to_person", sess_name)
    return None


# Session 115 Fix 1 Layer B — short-TTL classifier cache. Key is
# (text_normalized, frozenset(active_session_pids)). Value is
# (sidecar_dict_or_None, timestamp). LRU-by-insertion-order with size
# limit. Cleared opportunistically on insert when size exceeds limit.
_CLASSIFIER_CACHE_TTL_SECS = 5.0
_CLASSIFIER_CACHE_MAX_SIZE = 64
_classifier_cache: "dict[tuple, tuple]" = {}


async def _classify_intent_cached(
    text: str,
    history: "list[dict]",
    active_session_pids: "frozenset[str]",
) -> "dict | None":
    """Session 115 Fix 1 Layer B — cached wrapper around _classify_intent.

    Cache key normalizes text (lowercase + stripped) plus the active
    session pid set so a turn classified under one room scope doesn't
    leak into a different room. 5-second TTL bounds staleness.
    """
    key = (text.strip().lower() if text else "", active_session_pids)
    now = time.time()
    cached = _classifier_cache.get(key)
    if cached is not None:
        sidecar, ts = cached
        if now - ts < _CLASSIFIER_CACHE_TTL_SECS:
            return sidecar
        # Expired — drop stale entry.
        _classifier_cache.pop(key, None)
    # Spec 2 wiring: route through `_classify_intent_smart` so the
    # graph classifier runs in parallel under shadow mode (default).
    # In shadow mode, smart returns the LLM result so behavior is
    # unchanged; in primary/retired modes, smart returns graph results.
    from core.brain import _classify_intent_smart
    sidecar = await _classify_intent_smart(text, conversation_history=history)
    # Insert + opportunistic LRU trim (drop oldest by insertion order).
    _classifier_cache[key] = (sidecar, now)
    if len(_classifier_cache) > _CLASSIFIER_CACHE_MAX_SIZE:
        # Evict the oldest 25% of entries to amortize the trim cost.
        _evict_n = max(1, len(_classifier_cache) // 4)
        for old_key in list(_classifier_cache.keys())[:_evict_n]:
            _classifier_cache.pop(old_key, None)
    return sidecar


def _format_multispeaker_transcript(
    named_pairs: "list[tuple[str | None, str]]",
) -> "tuple[str, str, list[str]]":
    """Phase 3B.4 — format a multi-speaker transcript for the brain.

    ``named_pairs`` is a list of ``(name_or_None, transcript)`` tuples in
    diarize order. ``name=None`` means the span didn't match the voice
    gallery — gets assigned ``unknown_1`` / ``unknown_2`` / ... in the
    order it appeared. Numbering is PER-UTTERANCE; no cross-turn state.

    Returns ``(brain_text, log_preview, labels)``:
      - ``brain_text``  — string injected into the user message.
          N=2 preserves legacy `[Name1]: text\\n[Name2]: text` format.
          N≥3 uses a `[N voices simultaneously]\\n{Name}: {text}\\n...`
          block — more readable with 3+ speakers than slash/newline
          mixing, and the header names exact count so brain sees the
          multi-speaker signal prominently.
      - ``log_preview`` — single-line slash-separated for ``[STT]`` log.
      - ``labels``      — list of resolved names (including ``unknown_N``)
          in order. Drives the voice_state "multi_speaker_speakers"
          field that downstream observability reads.

    Returns ``("", "", [])`` if fewer than 2 surviving transcripts —
    caller should treat single-speaker as the normal path.
    """
    if len(named_pairs) < 2:
        return "", "", []
    labels: list[str] = []
    unknown_i = 0
    for name, _ in named_pairs:
        if not name or name == "unknown":
            unknown_i += 1
            labels.append(f"unknown_{unknown_i}")
        else:
            labels.append(name)
    texts = [t for _, t in named_pairs]
    n = len(named_pairs)
    preview = " / ".join(
        f"{name}: \"{t[:60]}\"" for name, t in zip(labels, texts)
    )
    if n == 2:
        brain_text = "\n".join(
            f"[{name}]: {t}" for name, t in zip(labels, texts)
        )
    else:
        brain_text = (
            f"[{n} voices simultaneously]\n"
            + "\n".join(f"{name}: {t}" for name, t in zip(labels, texts))
        )
    return brain_text, preview, labels


# _effective_switch_threshold moved to core/reconciler.py (#176, Phase 3) —
# routing logic belongs alongside the cascade. Re-exported here for any
# remaining legacy callers; Phase 5 deletes those along with
# `_resolve_actual_speaker`.
from core.reconciler import _effective_switch_threshold  # noqa: E402, F401


def _count_scene_candidates(
    persons_in_frame: dict,
    unrecognized_tracks: dict,
    now: float,
    exclude: str | None = None,
) -> int:
    """Count how many distinct people are plausibly in the scene (excluding `exclude`)."""
    known = sum(
        1 for pid, info in persons_in_frame.items()
        if pid != exclude and now - info.get("last_recognized_at", 0) < VOICE_ROUTING_FACE_STALE_SECS
    )
    unrec = sum(
        1 for ts in unrecognized_tracks.values()
        if now - ts < VOICE_ROUTING_FACE_STALE_SECS
    )
    return known + unrec


def _resolve_actual_speaker(
    v_pid:              str | None,
    v_score:            float,
    cur_pid:            str | None,
    persons_in_frame:   dict,
    unrecognized_tracks: dict,
    voice_gallery_sizes: dict,
    now:                float,
    cur_person_type:    str | None = None,
    *,
    utterance_duration: float | None = None,
    n_active_sessions:  int = 1,
    n_diarize_segments: int = 1,
    cur_holder_voice_n: int = 0,
) -> tuple[str | None, str]:
    """Determine the actual speaker using voice + face signals.

    Returns (resolved_person_id, action) where action is one of:
      "switch_enrolled"                — switch to v_pid (confident different-person match)
      "current"                        — stay with cur_pid (confirmed)
      "new_stranger"                   — unrecognized speaker; caller opens stranger session
      "ambiguous"                      — cannot determine; caller logs and skips attribution
      "no_action"                      — nothing to do; caller drops the turn
      "short_utterance_skip"           — utterance too brief for reliable voice ID; drop
      "short_utterance_voice_mismatch" — utt < 1.0s BUT voice score says obviously
                                          not cur_pid (Session 92 P3.23) — drop
      "multi_segment_voice_mismatch"   — pyannote saw 2+ voices in the chunk BUT
                                          voice ID matched none of them confidently
                                          (Session 118 Fix A) — drop, prevents
                                          stranger's words being attributed to
                                          the visible owner.
      "single_segment_voice_mismatch"  — pyannote saw 1 voice, ECAPA confidently
                                          says it's NOT the holder (mature profile,
                                          adequate audio, score below stranger
                                          floor), but no other candidates in scene.
                                          Session 120 — drop instead of silently
                                          misattributing to current.

    ``utterance_duration`` (Bug F, 2026-04-20 live run): seconds of recorded
    audio the voice ID ran against. Below ``VOICE_ROUTING_MIN_UTTERANCE_SECS``
    (1.0s), ECAPA-TDNN embeddings are too noisy to drive session changes —
    stick with current session, or drop the turn if none. When ``None``, the
    check is skipped (for legacy tests; production callers must supply it).
    """
    # Priority 0 — Short-utterance floor. Below this, voice ID is noise; ignore
    # the score entirely and either hold the current session or drop the turn.
    # This prevents phantom stranger sessions from short social closers
    # ("Thank you", "Yes", "Hey") and the downstream visitor_log / Briefing
    # cascade that led to Bug N confabulation.
    #
    # Session 92 P3.23 refinement: the blanket "route to current" broke the
    # Lexi-joins-Jagan-session case — Lexi's "Hi Kara" at 0.67s (voice=0.08 vs
    # Jagan's mature gallery) was routed to Jagan, so a new stranger session
    # never formed. ECAPA on 0.5-1.0s audio is noisy BUT directional: "is this
    # obviously NOT cur_pid?" is answerable even when "is this definitely X?"
    # isn't. If v_score falls below SHORT_UTT_FLOOR when we have at least
    # MIN_AUDIO_FOR_SCORE of audio, treat as mismatch and drop — the caller
    # doesn't attribute, the user/other-speaker repeats with a longer utterance
    # which then routes correctly through the normal (non-floor) path.
    if utterance_duration is not None and utterance_duration < VOICE_ROUTING_MIN_UTTERANCE_SECS:
        if (VOICE_ROUTING_SHORT_UTT_MISMATCH_ENABLED
                and cur_pid is not None
                and utterance_duration >= VOICE_ROUTING_MIN_AUDIO_FOR_SCORE):
            # Tier 1 — hard mismatch (Session 92 P3.23 original).
            if v_score < VOICE_ROUTING_SHORT_UTT_FLOOR:
                print(
                    f"[Voice] {_now_log_ts()} Routing: short_utterance_voice_mismatch "
                    f"(utt={utterance_duration:.2f}s, score={v_score:.3f} < "
                    f"{VOICE_ROUTING_SHORT_UTT_FLOOR} hard floor vs cur_pid={cur_pid})"
                )
                return None, "short_utterance_voice_mismatch"
            # Tier 2 — ambiguous zone (Session 93 refinement). The 0.20-0.40 band
            # is too noisy to trust AND too noisy to reject outright. Drop only
            # when the room plausibly has another speaker (multiple active
            # sessions); solo case keeps Bug F's "hold current" to avoid false-
            # negative drops on the holder's own voice dipping briefly.
            if (v_score < VOICE_ROUTING_SHORT_UTT_AMBIGUOUS
                    and n_active_sessions >= 2):
                print(
                    f"[Voice] {_now_log_ts()} Routing: short_utterance_voice_mismatch "
                    f"(utt={utterance_duration:.2f}s, score={v_score:.3f} in ambiguous "
                    f"zone [{VOICE_ROUTING_SHORT_UTT_FLOOR}, {VOICE_ROUTING_SHORT_UTT_AMBIGUOUS}) "
                    f"with {n_active_sessions} active sessions — drop to prevent "
                    f"mis-attribution to cur_pid={cur_pid})"
                )
                return None, "short_utterance_voice_mismatch"
        if cur_pid is not None:
            print(f"[Voice] {_now_log_ts()} Routing: current (short utterance {utterance_duration:.2f}s < {VOICE_ROUTING_MIN_UTTERANCE_SECS}s floor)")
            return cur_pid, "current"
        print(f"[Voice] {_now_log_ts()} Routing: skip (short utterance {utterance_duration:.2f}s, no session)")
        return None, "short_utterance_skip"

    switch_threshold = _effective_switch_threshold(v_pid, voice_gallery_sizes)

    # Priority 1 — Confident voice match for a DIFFERENT person
    if v_pid and v_pid != cur_pid and v_score >= switch_threshold:
        print(f"[Voice] {_now_log_ts()} Routing: switch_enrolled → {v_pid} (score={v_score:.3f})")
        return v_pid, "switch_enrolled"

    # Priority 2 — Mid-range different-person match (VOICE_ROUTING_MIDRANGE_SWITCH_MIN–switch_threshold)
    if v_pid and v_pid != cur_pid and v_score >= VOICE_ROUTING_MIDRANGE_SWITCH_MIN:
        if _face_in_frame(v_pid, persons_in_frame) and v_score >= VOICE_ROUTING_FACE_ASSIST_MIN:
            # Voice AND face agree AND voice is strong enough to be credible on
            # its own — confident switch. Bug B: must use _face_in_frame so a
            # voice-only speaker doesn't falsely trigger this shortcut. Bug O
            # (2026-04-20): added the VOICE_ROUTING_FACE_ASSIST_MIN floor —
            # below 0.42, face-agreement isn't strong enough corroboration. The
            # visible face isn't necessarily the speaker (multi-person, phone
            # audio, background speaker) and a weak voice match shouldn't be
            # upgraded to "confident" just because a claimed face is in frame.
            print(f"[Voice] {_now_log_ts()} Routing: switch_enrolled (face+voice agree) → {v_pid} (score={v_score:.3f})")
            return v_pid, "switch_enrolled"
        if _face_in_frame(v_pid, persons_in_frame):
            # Face in frame but voice below VOICE_ROUTING_FACE_ASSIST_MIN — log
            # for diagnostics so Bug O regressions are visible.
            print(f"[Voice] {_now_log_ts()} Routing: ambiguous — weak voice {v_score:.3f} for {v_pid} despite face in frame (below {VOICE_ROUTING_FACE_ASSIST_MIN} floor)")
            return None, "ambiguous"
        print(f"[Voice] {_now_log_ts()} Routing: ambiguous — mid-range score {v_score:.3f} for {v_pid} not in frame")
        return None, "ambiguous"

    # Priority 3 — Voice matches current session holder (confirmation)
    if v_pid is not None and v_pid == cur_pid:
        # Unconditional floor: voice must clear a minimum even when face is co-visible.
        # Without this, a poisoned face match lets any acoustically-similar stranger
        # coast through on vision alone (fluctuating 0.3–0.6 scores were the smoking gun).
        if v_score < VOICE_ROUTING_SELF_MATCH_FLOOR:
            print(f"[Voice] {_now_log_ts()} Routing: ambiguous — voice self-match {v_score:.3f} below floor")
            return None, "ambiguous"

        # Bug W (2026-04-22 live run): the offscreen floor is a poisoning
        # protection calibrated for MATURE speakers — a stranger with a face
        # match where voice scored 0.30–0.45 was the smoking-gun pattern. But
        # a bootstrapping stranger's OWN voice routinely scores 0.30–0.45
        # against their unstable mean (3 samples isn't enough for a tight
        # cosine cluster) — that's normal profile-warming behavior, not a
        # poisoning signal. Applying the floor here silences thin strangers:
        # Chloe said "My name is Chloe" at v=0.307 with 3/5 samples and her
        # turn was dropped, then every subsequent attempt also dropped because
        # the gates prevented her from accumulating more samples. Profile-
        # maturity-aware gating mirrors what _effective_switch_threshold
        # already does for Priority 1.
        _is_stranger_holder = (
            cur_person_type == "stranger"
            if cur_person_type is not None
            else bool(cur_pid and cur_pid.startswith("stranger_"))
        )
        _holder_gallery_n = voice_gallery_sizes.get(cur_pid, 0)
        _thin_holder = _is_stranger_holder and _holder_gallery_n < N_INITIAL_VOICE

        if v_score < VOICE_ROUTING_SELF_MATCH_OFFSCREEN and not _face_in_frame(cur_pid, persons_in_frame):
            # Bug B: symmetric with Priority 2 — voice-sourced entries in
            # persons_in_frame don't count as "holder visible".
            if _thin_holder:
                # Skip the floor for thin strangers — log the relaxation so
                # debugging is visible.
                print(
                    f"[Voice] {_now_log_ts()} Routing: current "
                    f"(thin stranger {_holder_gallery_n}/{N_INITIAL_VOICE}, "
                    f"offscreen floor skipped, score={v_score:.3f})"
                )
                return cur_pid, "current"
            print(f"[Voice] {_now_log_ts()} Routing: ambiguous — low self-match {v_score:.3f} and holder not visible")
            return None, "ambiguous"
        print(f"[Voice] {_now_log_ts()} Routing: current — {cur_pid} (score={v_score:.3f})")
        return cur_pid, "current"

    # Priority 3.5 — Voice unrecognised but cur_pid is a bootstrapping stranger.
    # A thin profile (< N_INITIAL_VOICE samples) can't reliably self-match, so
    # identify() returns (None, low_score).  Don't fragment into a new session —
    # stay with the existing one so the profile can accumulate toward maturity.
    # NOTE: person_id keeps the "stranger_" prefix after promotion (only person_type
    # flips to "known"), so the prefix alone is not a reliable stranger signal.
    # We prefer the session's person_type when the caller supplied it.
    _is_stranger = (
        cur_person_type == "stranger"
        if cur_person_type is not None
        else bool(cur_pid and cur_pid.startswith("stranger_"))
    )
    if v_pid is None and cur_pid is not None and _is_stranger:
        gallery_count = voice_gallery_sizes.get(cur_pid, 0)
        if gallery_count < N_INITIAL_VOICE:
            print(f"[Voice] {_now_log_ts()} Routing: current (stranger bootstrapping — {gallery_count}/{N_INITIAL_VOICE} voice samples)")
            return cur_pid, "current"

    # Priority 4 — Voice unrecognized, active session exists
    if v_pid is None and cur_pid is not None:
        # Session 118 Fix A — multi-segment stranger guard. When pyannote
        # detected 2+ voices AND voice ID couldn't match any enrolled
        # speaker AND there are MULTIPLE active sessions, that's the
        # cross-talk-between-knowns case where misattribution is the real
        # risk. Drop the turn so the stranger doesn't get assigned to
        # whichever known speaker happens to be cur_pid.
        #
        # Session 121 (2026-04-28) refinement: only fires when
        # `n_active_sessions >= 2`. The original Session 118 author
        # assumed "the stranger / user repeats with cleaner audio, next
        # iteration routes through normal new_stranger logic" — that
        # turned out wrong: pyannote keeps returning 2 segments (audio
        # quirk, not a transient artifact), so the drop loop never
        # broke. With only the owner enrolled and no other candidates,
        # the unknown voice is unambiguously a stranger — fall through
        # to the new_stranger branch below instead of dropping forever.
        if (
            n_diarize_segments >= 2
            and v_score < VOICE_ROUTING_STRANGER_FLOOR
            and n_active_sessions >= 2
        ):
            print(
                f"[Voice] {_now_log_ts()} Routing: multi_segment_voice_mismatch "
                f"(pyannote={n_diarize_segments} segments, max v_score={v_score:.3f} < "
                f"{VOICE_ROUTING_STRANGER_FLOOR} stranger floor — likely a non-enrolled "
                f"speaker; dropping to prevent misattribution to cur_pid={cur_pid})"
            )
            return None, "multi_segment_voice_mismatch"
        if 0.0 < v_score < VOICE_RECOGNITION_THRESHOLD:
            print(f"[Voice] {_now_log_ts()} Routing: new_stranger — score {v_score:.3f} < threshold")
            return None, "new_stranger"
        # Session 120 — single-segment voice mismatch drop. Same shape as
        # Session 118's multi_segment_voice_mismatch but for single-segment
        # audio. Fires when pyannote saw ONE voice, ECAPA confidently fails
        # to match the enrolled holder (mature profile + adequate audio),
        # AND there are MULTIPLE active sessions (cross-talk-between-knowns
        # is the real risk).
        #
        # Session 121 (2026-04-28) inversion fix: original spec required
        # n_active_sessions == 1, which was backwards. With only the owner
        # enrolled, an unknown voice is a stranger — should fall through
        # to new_stranger. The drop only protects against misattribution
        # WHEN MULTIPLE knowns are around. Mature-profile + audio-duration
        # guards prevent false positives on bootstrapping voice profiles
        # and ECAPA-noise short utterances. Toggleable via config flag.
        if (
            VOICE_ROUTING_SINGLE_SEGMENT_MISMATCH_ENABLED
            and n_diarize_segments == 1
            and v_score < VOICE_ROUTING_STRANGER_FLOOR
            and utterance_duration is not None
            and utterance_duration >= VOICE_ROUTING_MIN_AUDIO_FOR_SCORE
            and cur_holder_voice_n >= VOICE_ACCUM_MATURE_SAMPLE_COUNT
            and n_active_sessions >= 2
        ):
            print(
                f"[Voice] {_now_log_ts()} Routing: single_segment_voice_mismatch — "
                f"v_score={v_score:.3f} < floor={VOICE_ROUTING_STRANGER_FLOOR}, "
                f"holder voice_n={cur_holder_voice_n} mature, "
                f"audio={utterance_duration:.2f}s, dropping turn to prevent "
                f"misattribution to cur_pid={cur_pid}"
            )
            return None, "single_segment_voice_mismatch"
        # v_score == 0: utterance too short to identify
        scene_candidates = _count_scene_candidates(
            persons_in_frame, unrecognized_tracks, now, exclude=cur_pid
        )
        if scene_candidates == 0:
            print(f"[Voice] {_now_log_ts()} Routing: current — voice ambiguous, no other candidates in scene")
            return cur_pid, "current"
        print(f"[Voice] {_now_log_ts()} Routing: ambiguous — {scene_candidates} other candidate(s) in scene")
        return None, "ambiguous"

    # Priority 5 — No active session, unrecognized voice
    if v_pid is None and cur_pid is None:
        unrec_active = any(
            now - ts < VOICE_ROUTING_FACE_STALE_SECS
            for ts in unrecognized_tracks.values()
        )
        if 0.0 < v_score < VOICE_RECOGNITION_THRESHOLD or unrec_active:
            print(f"[Voice] {_now_log_ts()} Routing: new_stranger — ambient, score={v_score:.3f}")
            return None, "new_stranger"
        return None, "no_action"

    print(f"[Voice] {_now_log_ts()} Routing: ambiguous — last resort (v_pid={v_pid}, cur={cur_pid})")
    return None, "ambiguous"


def _build_cross_person_excerpts(
    speaker_id: str,
    active_sessions: "tuple",
    conversation: dict,
    best_friend_id: str | None,
) -> str | None:
    """Build a room-state context block when multiple people are active.

    Gives the brain: who is present + their roles + recent exchanges from
    everyone else in the room.  Returns None for single-person sessions.

    Session 111 (Critical #2 + #3 + HIGH timestamps):
      - Excerpts filter by each other-person's session.started_at so
        yesterday's turns don't bleed into today's room context.
      - Assistant messages render with "you [to X]" when addressed_to
        is present — unambiguous in 4-person rooms where "you: ..."
        doesn't say who the AI was replying to.
      - Each line gets a "(Xm ago)" / "(just now)" suffix so the brain
        can judge freshness instead of treating all excerpts as equally
        recent.
    """
    if len(active_sessions) <= 1:
        return None

    present_parts = []
    for _cx_snap in active_sessions:
        pid = _cx_snap.person_id
        name = _cx_snap.person_name
        # Finding M — disputed sessions take the SCENE label "disputed identity"
        # regardless of the sensor-matched pid's usual role. The IDENTITY DISPUTED
        # block separately tells the brain to treat this person as unknown; the
        # SCENE role must agree rather than say "best friend is present."
        if _is_disputed(pid):
            role = "disputed identity"
        elif pid == best_friend_id:
            role = "best friend"
        elif _cx_snap.person_type == "stranger":
            role = "visitor"
        else:
            role = "known person"
        tag = " — speaking now" if pid == speaker_id else ""
        present_parts.append(f"{name} ({role}{tag})")

    now_ts = time.time()
    cross_lines: list[str] = []
    for _cx_snap2 in active_sessions:
        pid = _cx_snap2.person_id
        if pid == speaker_id:
            continue
        other_name = _cx_snap2.person_name
        # Critical #2 — only include messages written AFTER this session
        # opened; earlier turns (from a prior session days ago) would
        # confuse the brain about what's happening NOW.
        other_started = float(_cx_snap2.started_at)
        other_hist    = conversation.get(pid, [])
        in_session = [
            msg for msg in other_hist
            if float(msg.get("ts") or 0.0) >= other_started
        ]
        # Last 6 messages (~3 turns) from the other person
        recent = in_session[-6:] if len(in_session) > 6 else in_session
        for msg in recent:
            ts = float(msg.get("ts") or 0.0)
            age_secs = max(0.0, now_ts - ts) if ts else 0.0
            # HIGH — render freshness so brain weights recency properly.
            if not ts:
                age_label = ""
            elif age_secs < 60:
                age_label = "just now"
            else:
                age_label = f"{int(age_secs / 60)}m ago"
            age_suffix = f" ({age_label})" if age_label else ""
            if msg.get("role") == "user":
                role_label = other_name
            else:
                # Critical #3 — addressee label on assistant messages so
                # the brain sees who the AI was speaking to (vs. the
                # ambiguous bare "you:" that could refer to any listener).
                # Always include "[to X]" when addressed_to is recorded —
                # even if it's the session-owner name, the explicit label
                # helps the brain disambiguate multi-person rooms where a
                # bare "you:" could mean the AI addressed any listener.
                addressed = msg.get("addressed_to")
                role_label = (
                    f"you [to {addressed}]"
                    if addressed
                    else "you"
                )
            content = (msg.get("content") or "")[:120]
            cross_lines.append(f"  {role_label}{age_suffix}: {content}")

    lines = ["People in room: " + ", ".join(present_parts)]
    if cross_lines:
        lines.append("Recent context from others in the room:")
        lines.extend(cross_lines)

    return (
        "<<<ROOM STATE (internal — never quote these markers, treat as natural awareness)>>>\n"
        + "\n".join(lines)
        + "\n<<<END ROOM STATE>>>"
    )


def _fetch_recent_visitors_for_scene(best_friend_id: "str | None") -> "list[dict] | None":
    """Session 108 Phase 3A.7 — helper for SCENE block recent-visitor /
    safety-concern sections. Returns a list of VISITOR_ALERT nudge
    dicts for the owner (from the past SCENE_VISITOR_RECENCY_SECS
    window). Safe when orchestrator/bf_id unavailable — returns None
    so the scene block skips those sections cleanly.
    """
    if not best_friend_id or _brain_orchestrator is None:
        return None
    try:
        hours_back = SCENE_VISITOR_RECENCY_SECS / 3600.0
        return _brain_orchestrator.brain_db.get_recent_visitor_alerts(
            best_friend_id, hours_back=hours_back,
        )
    except Exception as _ex:
        print(f"[Pipeline] recent-visitor fetch for SCENE failed: {_ex!r}")
        return None


def _build_room_block(
    active_sessions: "tuple",
    conversation: dict,
    emotion_agents: dict,
    room_start_ts: "float | None",
    turn_cap: int = 10,
    now: "float | None" = None,
) -> "str | None":
    """Phase 3B.1 — unified multi-person room-state block.

    Returns a formatted `<<<ROOM>>>` block when ≥2 sessions are active;
    None otherwise (backward-compat — single-person sessions keep the
    SCENE-only path). Replaces the fragmented SCENE (in-room portion) +
    cross-person excerpts + per-person mood sections with a single
    coherent structure the brain reads end-to-end.

    Sections rendered (in order):
      1. Active speakers list with role labels (best_friend/known/stranger).
      2. Room duration ("Room session started Xm ago" — or omitted when
         room_start_ts is None, e.g. just-minted rooms without stamp).
      3. Interleaved recent turns across ALL active speakers, sorted
         chronologically (oldest first, most recent last), capped at
         turn_cap. Each line renders:
           [Xm ago] Speaker → Addressee: "content"
         for assistant messages with addressed_to, else [Xm ago]
         Speaker: "content" for user messages. Session 111's per-message
         `ts` + `addressed_to` fields drive the formatting.
      4. Per-person mood from EmotionAgent.get_dominant_emotion(); "neutral"
         when agent absent OR None returned. Strangers mid-bootstrap render
         as "unknown" gracefully so the block never crashes.

    Safety: messages older than `room_start_ts` are filtered out (prevents
    yesterday's turns bleeding into today's room context — Session 111
    Critical #2 invariant). Missing `ts` fields are treated as ts=0 and
    filtered out (pre-Session-111 history).

    The helper is pure over its inputs — callers pass `_conversation`,
    `_emotion_agents`, `_active_room_started_at` explicitly so unit tests
    can exercise it without the full module globals.
    """
    from core.config import ROOM_BLOCK_ENABLED
    if not ROOM_BLOCK_ENABLED:
        return None
    if len(active_sessions) < 2:
        return None
    if now is None:
        now = time.time()

    # ── Section 1: active speakers list ──────────────────────────────────
    _active_lines: list[str] = []
    for _rs in active_sessions:
        _active_lines.append(f"{_rs.person_name} ({_rs.person_type})")
    _active_str = ", ".join(_active_lines)

    # ── Section 2: room duration (optional) ──────────────────────────────
    _duration_line = ""
    if room_start_ts is not None:
        _elapsed_secs = max(0.0, now - room_start_ts)
        if _elapsed_secs < 60:
            _dur_phrase = "just started"
        elif _elapsed_secs < 3600:
            _dur_phrase = f"started {int(_elapsed_secs / 60)} min ago"
        else:
            _hrs = int(_elapsed_secs / 3600)
            _dur_phrase = f"started {_hrs} hr ago" if _hrs == 1 else f"started {_hrs} hrs ago"
        _duration_line = f"Room session {_dur_phrase}."

    # ── Section 3: interleaved recent turns ──────────────────────────────
    _boundary = room_start_ts if room_start_ts is not None else 0.0
    _all_msgs: list[tuple[float, str, dict]] = []
    for _rs in active_sessions:
        _pname = _rs.person_name
        _history = conversation.get(_rs.person_id, []) or []
        for _msg in _history:
            _ts = _msg.get("ts", 0.0)
            if _ts < _boundary:
                continue
            _all_msgs.append((_ts, _pname, _msg))
    _all_msgs.sort(key=lambda x: x[0])
    # Keep the most recent up to cap, preserving chronological order.
    if len(_all_msgs) > turn_cap:
        _all_msgs = _all_msgs[-turn_cap:]

    def _age_label(ts: float) -> str:
        _delta = max(0.0, now - ts)
        if _delta < 60:
            return "just now"
        if _delta < 3600:
            return f"{int(_delta / 60)}m ago"
        return f"{int(_delta / 3600)}h ago"

    _turn_lines: list[str] = []
    for _ts, _pname, _msg in _all_msgs:
        _role     = _msg.get("role", "user")
        _content  = (_msg.get("content") or "").strip()
        if not _content:
            continue
        _age      = _age_label(_ts)
        _addr     = _msg.get("addressed_to")
        if _role == "assistant":
            # Assistant: "Kara" (the system) → addressee
            _speaker = "Kara"
            if _addr:
                _turn_lines.append(f"  [{_age}] {_speaker} → {_addr}: \"{_content}\"")
            else:
                _turn_lines.append(f"  [{_age}] {_speaker}: \"{_content}\"")
        else:
            # User turn — speaker is the session's person_name.
            _turn_lines.append(f"  [{_age}] {_pname}: \"{_content}\"")

    # ── Section 4: per-person mood ───────────────────────────────────────
    _mood_lines: list[str] = []
    for _rs in active_sessions:
        _ag = emotion_agents.get(_rs.person_id)
        if _ag is None:
            _mood = "unknown"
        else:
            try:
                _label, _score = _ag.get_dominant_emotion()
                _mood = _label if _label else "neutral"
            except Exception:
                _mood = "neutral"
        _mood_lines.append(f"  {_rs.person_name}: {_mood}")

    # ── Assemble ─────────────────────────────────────────────────────────
    _parts: list[str] = ["<<<ROOM>>>"]
    _parts.append(f"Active in this room: {_active_str}")
    if _duration_line:
        _parts.append(_duration_line)
    if _turn_lines:
        _parts.append("")
        _parts.append("Recent turns (oldest first, most recent last):")
        _parts.extend(_turn_lines)
    _parts.append("")
    _parts.append("Current emotional state:")
    _parts.extend(_mood_lines)
    _parts.append("<<<END ROOM>>>")

    # Phase 3B.3 — TURN ARBITRATION rules. Appended AFTER the ROOM block
    # closer so the two sections render as siblings: ROOM gives the brain
    # context, ARBITRATION tells it when that context justifies overriding
    # the default addressee (current speaker). 4 rules with concrete
    # examples so the brain has sharp triggers, not abstract guidance.
    # Gated independently so canary rollback is a one-line flag flip.
    from core.config import TURN_ARBITRATION_ENABLED
    if TURN_ARBITRATION_ENABLED:
        _parts.append("")
        _parts.append("<<<TURN ARBITRATION>>>")
        _parts.append(
            "Default: respond to the current speaker (the one whose turn is being processed).\n"
            "No [addressing:X] marker needed.\n"
            "\n"
            "Emit [addressing:<name>] marker ONLY when one of these applies:\n"
            "\n"
            "1. MUMBLE CONTINUATION. Another speaker just gave a brief affirmation like\n"
            "   \"yeah\", \"uh-huh\", \"okay\", \"right\" — NOT a new turn demanding response.\n"
            "   Continue the thread with the PRIOR substantive speaker, not the mumbler.\n"
            "   Example: Jagan asks weather → Kara answers → Lexi: \"uh-huh\" → Kara should\n"
            "   continue with Jagan (not redirect to Lexi).\n"
            "\n"
            "2. PENDING THREAD CIRCLE-BACK. You helped speaker A earlier, the answer was\n"
            "   incomplete or promised follow-up, and speaker B took over the conversation.\n"
            "   After B's thread resolves naturally, you may circle back:\n"
            "   \"By the way, [addressing:A], about your earlier question...\"\n"
            "   ONLY do this when the current moment naturally allows it. Don't force.\n"
            "\n"
            "3. LONG-SILENCE RE-ENGAGEMENT. If a speaker (especially best_friend) has been\n"
            "   silent for 4+ turns while others dominated, a gentle check-in is fine.\n"
            "   \"[addressing:<quiet_speaker>], you've been quiet — what do you think?\"\n"
            "   ONLY if context naturally allows. Don't interrupt active thread.\n"
            "\n"
            "4. DIRECT QUESTION ACROSS CONTEXT. Speaker A asked a clear question to you\n"
            "   just now, but speaker B spoke last (even briefly). The question is still\n"
            "   unanswered. Emit [addressing:A] and respond to the question.\n"
            "\n"
            "DO NOT emit marker if:\n"
            "- None of the above apply\n"
            "- You're uncertain — default to current speaker is safer\n"
            "- The current speaker has clearly directed the conversation\n"
            "\n"
            "Marker format: `[addressing:Jagan]` on its own line at the START of your response.\n"
            "The marker will be stripped before TTS — the user won't hear it, only the\n"
            "pipeline uses it for attribution."
        )
        _parts.append("<<<END TURN ARBITRATION>>>")

    return "\n".join(_parts)


def _fetch_recent_room_context(person_id: "str | None") -> "dict | None":
    """Phase 3B.6 — fetch the most recent room_summaries row the person
    participated in, within the configured lookback window.

    Returns a dict with summary + topic_tags + safety_flags + ended_at,
    or None when no qualifying row exists / orchestrator unavailable /
    synthesis is disabled (defense-in-depth — the master flag may have
    been toggled off between synthesis time and retrieval time).
    Called per-turn from vision_state builds; query is indexed on
    ``ended_at DESC`` so cost is bounded.
    """
    from core.config import (
        ROOM_END_SYNTHESIS_ENABLED as _ENABLED,
        ROOM_RECENT_CONTEXT_HOURS as _HOURS,
    )
    if not _ENABLED or not person_id:
        return None
    if _brain_orchestrator is None:
        return None
    try:
        return _brain_orchestrator.brain_db.get_recent_room_context(
            person_id, hours=_HOURS,
        )
    except Exception as _ex:
        print(f"[Pipeline] recent-room-context fetch failed: {_ex!r}")
        return None


def _scene_fingerprint(
    speaker_id: "str | None",
    now: float,
    active_sessions: "tuple",
    persons_in_frame: dict,
    unrecognized_tracks: dict,
    best_friend_id: "str | None",
    recent_visitors: "list[dict] | None",
) -> tuple:
    """Hashable key summarising all inputs that affect _build_scene_block output."""
    now_sec = int(now)  # 1-second granularity — output is stable within a second
    _snap_by_pid = {s.person_id: s for s in active_sessions}

    vis_items = []
    for pid, info in persons_in_frame.items():
        if now - info.get("last_seen", 0) >= SCENE_STALE_SECS:
            continue
        name = info.get("name", pid)
        _snap = _snap_by_pid.get(pid)
        person_type = _snap.person_type if _snap is not None else "known"
        if _is_disputed(pid):
            role = "disputed"
        elif pid == best_friend_id:
            role = "best_friend"
        elif person_type == "stranger":
            role = "visitor"
        else:
            role = "known"
        secs_ago = int(now - info.get("last_seen", now))
        vis_items.append((pid, name, role, pid == speaker_id, secs_ago))

    unrec_count = sum(
        1 for t in unrecognized_tracks.values()
        if now - t.get("last_seen", 0) < SCENE_STALE_SECS
    )

    if recent_visitors is None:
        rv_key: "frozenset | None" = None
    else:
        rv_key = frozenset(
            (v.get("person_id", ""), v.get("visitor_name", ""), str(v.get("safety_flags", [])))
            for v in recent_visitors
        )

    return (speaker_id, now_sec, frozenset(vis_items), unrec_count, best_friend_id, rv_key)


def _get_scene_block_cached(
    speaker_id: "str | None",
    now: float,
    active_sessions: "tuple",
    persons_in_frame: dict,
    unrecognized_tracks: dict,
    best_friend_id: "str | None",
    recent_visitors: "list[dict] | None" = None,
) -> str:
    """Cache-backed wrapper for _build_scene_block (Wave 6 Item 23)."""
    global _scene_block_cache, _scene_block_cache_hits, _scene_block_cache_misses

    if not SCENE_BLOCK_CACHE_ENABLED:
        return _build_scene_block(
            speaker_id, now, active_sessions, persons_in_frame,
            unrecognized_tracks, best_friend_id, recent_visitors,
        )

    key = _scene_fingerprint(
        speaker_id, now, active_sessions, persons_in_frame,
        unrecognized_tracks, best_friend_id, recent_visitors,
    )

    cached = _scene_block_cache.get(key)
    if cached is not None:
        _scene_block_cache_hits += 1
        return cached

    _scene_block_cache_misses += 1
    result = _build_scene_block(
        speaker_id, now, active_sessions, persons_in_frame,
        unrecognized_tracks, best_friend_id, recent_visitors,
    )

    if len(_scene_block_cache) >= SCENE_BLOCK_CACHE_MAX_ENTRIES:
        oldest = next(iter(_scene_block_cache))
        del _scene_block_cache[oldest]

    _scene_block_cache[key] = result
    return result


def get_scene_block_cache_stats() -> dict:
    """Hit/miss/size stats for the scene_block cache."""
    return {
        "hits":        _scene_block_cache_hits,
        "misses":      _scene_block_cache_misses,
        "size":        len(_scene_block_cache),
        "max_entries": SCENE_BLOCK_CACHE_MAX_ENTRIES,
    }


def _build_scene_block(
    speaker_id: str | None,
    now: float,
    active_sessions: "tuple",
    persons_in_frame: dict,
    unrecognized_tracks: dict,
    best_friend_id: str | None,
    recent_visitors: "list[dict] | None" = None,
) -> str:
    """Always-on scene snapshot injected into the system prompt every turn.

    Session 108 Phase 3A.7 — restructured into 4 sections (Here now /
    Offscreen voice / Recent visitors / Safety concerns). Reviewer's
    lean-approach recommendation over LLM synthesis: structured
    descriptive block gets 80% of the value at 0% of the latency/cost,
    with proactive safety-flag surfacing baked in (Session 105 Bug N
    Part 3's per-visitor safety_flags metadata is now consumed here,
    not just in VISITOR CONTEXT).

    Sections render conditionally — each is omitted when empty so the
    block stays terse on single-person scenes. Safety concerns always
    render last so the brain reads them after the factual context.

    ``recent_visitors`` is pre-fetched by the caller from
    ``_brain_orchestrator.brain_db.get_recent_visitor_alerts(bf_id)``
    and filtered to nudges generated within SCENE_VISITOR_RECENCY_SECS.
    When None (caller unable to reach the orchestrator), those sections
    simply don't render — fallback-safe.
    """
    # ── Section 1: Who's here now (camera) ──────────────────────────
    _snap_by_pid_scene = {s.person_id: s for s in active_sessions}
    visible_lines: list[str] = []
    for pid, info in persons_in_frame.items():
        if now - info.get("last_seen", 0) >= SCENE_STALE_SECS:
            continue
        name = info.get("name", pid)
        _sc_snap = _snap_by_pid_scene.get(pid)
        person_type = _sc_snap.person_type if _sc_snap is not None else "known"
        # Finding M — disputed sessions take precedence over the sensor-matched
        # role so the SCENE block agrees with the IDENTITY DISPUTED block instead
        # of saying "best friend is present" for a contested identity.
        if _is_disputed(pid):
            role = "disputed identity"
        elif pid == best_friend_id:
            role = "best friend"
        elif person_type == "stranger":
            role = "visitor"
        else:
            role = "known"
        if pid == speaker_id:
            status = "speaking now"
        else:
            secs_ago = int(now - info.get("last_seen", now))
            status = "silent" if secs_ago < 2 else f"silent, last seen {secs_ago}s ago"
        visible_lines.append(f"- {name} ({role}) — {status}")

    unrec_count = sum(
        1 for ts in unrecognized_tracks.values()
        if now - ts < SCENE_STALE_SECS
    )
    if unrec_count:
        plural = "s" if unrec_count != 1 else ""
        visible_lines.append(f"- {unrec_count} unrecognized face{plural} (not greeted yet)")

    # ── Section 2: Offscreen voice ──────────────────────────────────
    offscreen_lines: list[str] = []
    for _off_snap in active_sessions:
        pid = _off_snap.person_id
        if pid in persons_in_frame:
            continue
        if _off_snap.session_type != "voice":
            continue
        last_spoke = _off_snap.last_spoke_at
        if now - last_spoke >= SCENE_VOICE_STALE:
            continue
        name = _off_snap.person_name
        person_type = _off_snap.person_type
        if pid == best_friend_id:
            role = "best friend"
        elif person_type == "stranger":
            role = "visitor"
        else:
            role = "known"
        secs_ago = int(now - last_spoke)
        status = "speaking now" if pid == speaker_id else f"heard {secs_ago}s ago"
        offscreen_lines.append(f"- {name} ({role}) — {status}")

    # ── Session 108 Phase 3A.7: Sections 3 & 4 — recent visitors + safety ──
    # `recent_visitors` is a list of nudge dicts (from
    # get_recent_visitor_alerts). Each has 'metadata' (visitor_name,
    # visitor_type, turn_count, safety_flags) + 'generated_at'. We
    # render two sections: human-readable visitor lines (Section 3)
    # AND an explicit Safety concerns rollup (Section 4) so the brain
    # can't miss them even if it skims.
    recent_visitor_lines: list[str] = []
    safety_concern_lines: list[str] = []
    if recent_visitors:
        for v in recent_visitors:
            if not isinstance(v, dict):
                continue
            gen_at = v.get("generated_at") or 0
            if gen_at and now - gen_at >= SCENE_VISITOR_RECENCY_SECS:
                continue
            meta = v.get("metadata") or {}
            vname  = meta.get("visitor_name") or "an unidentified visitor"
            vid    = meta.get("visitor_id")
            vturns = meta.get("turn_count") or 0
            vtype  = meta.get("visitor_type") or "stranger"
            # Don't surface the owner as their own visitor (defensive —
            # self-skip is enforced in get_recent_visitor_alerts too).
            if vid and vid == best_friend_id:
                continue
            mins_ago = int((now - gen_at) / 60) if gen_at else 0
            when = (
                "just now" if mins_ago < 1
                else f"{mins_ago} min ago"
            )
            role_label = "promoted visitor" if vtype == "known" else "visitor"
            turn_desc = "briefly" if vturns <= 2 else "for a while"
            recent_visitor_lines.append(
                f"- {vname} ({role_label}) visited {when} — spoke {turn_desc} ({vturns} turn(s))"
            )
            flags = meta.get("safety_flags") or []
            for flag in flags:
                # human-readable: expressed_suicidal_thoughts →
                # "expressed suicidal thoughts".
                human_flag = str(flag).replace("_", " ")
                safety_concern_lines.append(
                    f"- {vname}: {human_flag}"
                )

    # ── Assemble ────────────────────────────────────────────────────
    parts = ["<<<SCENE (internal — speak the meaning, never quote these tags)>>>"]
    if visible_lines:
        parts.append("Here now (camera):")
        parts.extend(visible_lines)
    else:
        parts.append("Nobody visible on camera.")
    if offscreen_lines:
        parts.append("Offscreen voice:")
        parts.extend(offscreen_lines)
    if recent_visitor_lines:
        parts.append("Recent visitors:")
        parts.extend(recent_visitor_lines)
    if safety_concern_lines:
        parts.append("Safety concerns (raised during recent visits):")
        parts.extend(safety_concern_lines)
    parts.append("<<<END SCENE>>>")
    return "\n".join(parts)


def _open_session(
    person_id: str,
    person_name: str,
    session_type: str,                # "face" | "voice"
    person_type: str,                 # "stranger" | "known" | "best_friend"
    voice_confidence: float = 1.0,
    engagement_gate_passed: bool = False,
) -> None:
    """Open a new session for a person. Idempotent — updates if already open.

    ``person_type`` is a REQUIRED keyword-or-positional arg: every caller must
    commit to which session kind they're opening. Seeding the dict at creation
    time closes the race window where ``_session_store.peek_snapshot(pid).person_type``
    might be absent before the SessionStore task completes after ``_open_session`` —
    with the Step 2 fail-safe "stranger" fallback, that window would mis-gate
    a best_friend as stranger for one iteration.

    ``engagement_gate_passed`` (Step 3): when True, the session was opened
    through a gate that establishes identity (face greeting after anti-spoof,
    or stranger who just cleared the system-name gate). Seeds the voice
    accumulation "bootstrap credits" budget (see _voice_accum_allowed path C)
    so the profile can grow on early turns before face/voice witnesses are
    strong enough. Each successful accumulation decrements the budget.
    """
    assert person_type in VALID_PERSON_TYPES, (
        f"_open_session called with invalid person_type={person_type!r}; "
        f"must be one of {sorted(VALID_PERSON_TYPES)}"
    )
    now = time.time()
    existing = _session_store.peek_snapshot(person_id)
    if existing is not None:
        # P0.7.3: named lifecycle call covers last_spoke_at, last_face_seen, voice_confidence
        try:
            _loop = asyncio.get_running_loop()
            _loop.create_task(_session_store.update_on_reopen(
                person_id, voice_confidence=voice_confidence, now=now))
        except RuntimeError:
            pass  # OPTIONAL: no running loop in test/early-boot context
        # Don't overwrite person_type on re-open — caller may have promoted
        # stranger→known via update_person_name since the last open.
    else:
        from collections import deque as _deque
        # Session 111 Critical #5 — reset the per-person EmotionAgent on
        # every fresh session so the 3-turn rolling window can't carry
        # yesterday's emotions into today. Agents were previously
        # persisted in `_emotion_agents` across session open/close
        # cycles, meaning a user whose last session ended on a
        # "sad/angry" detection still had that state seed their next
        # session's context block on turn 1. Pop is cheap (object
        # will be lazily recreated on first emotion-detection call in
        # conversation_turn) and avoids state invariants that'd be
        # needed for a more surgical reset.
        _emotion_agents.pop(person_id, None)
        # Session 112 Part 1 — room-session lifecycle. Mint a new
        # room_session_id on the FIRST open into an empty room; later
        # opens (another person joining) inherit the existing id. The
        # room stays alive until _close_session empties the session
        # table (see _close_session for the end-of-room hook).
        global _active_room_session, _active_room_started_at, _active_room_participants
        if _active_room_session is None:
            import uuid as _uuid_rs
            _active_room_session = f"room_{int(now)}_{_uuid_rs.uuid4().hex[:6]}"
            # Phase 3B.1 — stamp wall-clock start time so <<<ROOM>>> block
            # can render duration. Must be set in the SAME branch that
            # mints the id so the pair stays consistent.
            _active_room_started_at = now
            # Phase 3B.6 — fresh participants set for the new room.
            _active_room_participants = set()
            print(f"[Room] New room session: {_active_room_session}")
        _current_room_session = _active_room_session
        # Phase 3B.6 — accumulate every pid that joins this room so
        # synthesize_room has the participant list at room-end time
        # (when _session_store has no active sessions). Idempotent on re-open.
        # Session 116 P1 #9 — log room join events explicitly so an
        # outside reviewer can audit room membership transitions
        # without inferring from open/close lines.
        _was_new = person_id not in _active_room_participants
        _active_room_participants.add(person_id)
        if _was_new:
            print(
                f"[Room] Participant joined: {person_name} ({person_id}) "
                f"→ {_active_room_session} "
                f"(now {len(_active_room_participants)} participant(s))"
            )
        print(f"[Session] Open: {person_id} ({session_type}) — {person_name}")
        _bootstrap = N_INITIAL_VOICE_BOOTSTRAP if engagement_gate_passed else 0
        # Bug A Part 1: hydrate voice_sample_count from a DB-authoritative count
        # so a re-opened session carries forward its prior voice samples.
        # Without this, a voice-only stranger whose session expired (VOICE_SESSION_TIMEOUT)
        # would restart at sample 0 and never reach maturity (Path B needs 5+).
        #
        # Obs 1 (2026-04-20 post-review): prefer the live DB count over the
        # in-memory cache. The cache can go stale when a delete_person()
        # call from the dashboard/CLI removes voice_embeddings rows out of
        # process. If cache and DB disagree, repair the cache so other consumers
        # (e.g. _effective_switch_threshold gating) see the correct number too.
        # Face-side evidence stays ephemeral — it must be re-established each session.
        _db_voice_count = _voice_gallery_sizes.get(person_id, 0)
        if _face_db_ref is not None:
            try:
                _db_voice_count = _face_db_ref.count_voice_embeddings(person_id)
                if _voice_gallery_sizes.get(person_id, -1) != _db_voice_count:
                    _voice_gallery_sizes[person_id] = _db_voice_count
            except Exception:
                pass  # OPTIONAL: cache fallback already seeded above — stale count safe until next session open
        # P0.7.2-SHIM: canonical-first — populate SessionStore BEFORE legacy dict
        try:
            _loop = asyncio.get_running_loop()
            _loop.create_task(_session_store.open_session(
                person_id, person_name, person_type, session_type,
                now=now,
                bootstrap_credits=_bootstrap,
                room_session_id=_current_room_session,
                voice_sample_count=_db_voice_count,
            ))
        except RuntimeError:
            pass  # OPTIONAL: no running loop in test/early-boot context
        # Wave 4 Item 18 — fetch core memory at session open so render_session_stable_prefix
        # can inject it into Section 2 without a DB call on every turn.
        _core_mem_value: list = []
        if _brain_orchestrator is not None:
            try:
                _bf_row_open = _face_db_ref.get_best_friend() if _face_db_ref else None
                _bf_id_open  = _bf_row_open["id"] if _bf_row_open else None
                _core_mem_value = _brain_orchestrator.brain_db.get_core_memory_for(
                    requester_pid  = person_id,
                    best_friend_id = _bf_id_open,
                    entity         = person_name,
                )
            except Exception as _cm_err:
                print(f"[Session] core_memory fetch failed for {person_id}: {_cm_err!r}")
        # P0.7.3: named lifecycle call (uses local _core_mem_value — no dict read)
        try:
            _loop = asyncio.get_running_loop()
            _loop.create_task(_session_store.set_core_memory(
                person_id, _core_mem_value))
        except RuntimeError:
            pass  # OPTIONAL: no running loop in test/early-boot context
        # Wave 2 Item 9: backfill heuristic for pre-S120 promoted voice-only strangers.
        # S120 set voice_only_origin=True at the engagement-gate pass for new promotions.
        # Pre-S120 promoted persons have voice_only_origin=False and no way to grow their
        # gallery (bootstrap replenishment was gated on person_type=='stranger', which
        # becomes False the moment update_person_name fires). Infer the flag retroactively
        # when: not already True, person is known/best_friend (not disputed/stranger),
        # gallery is still thin (< N_INITIAL_VOICE), and no face evidence is currently
        # available (confirming this is a voice-only session). Idempotent across re-opens.
        if (
            not (_session_store.peek_snapshot(person_id).voice_only_origin if _session_store.peek_snapshot(person_id) is not None else False)
            and person_type in ("known", "best_friend")
            and _voice_gallery_sizes.get(person_id, 0) < N_INITIAL_VOICE
            and not _has_recent_face_evidence(person_id)
        ):
            print(
                f"[Backfill] {person_name} ({person_id}) — voice_only_origin=True inferred "
                f"(person_type={person_type}, "
                f"voice_n={_voice_gallery_sizes.get(person_id, 0)}, no face)"
            )
            try:
                _loop = asyncio.get_running_loop()
                _loop.create_task(_session_store.set_voice_only_origin(person_id, True))
            except RuntimeError:
                pass  # OPTIONAL: no running loop in test/early-boot context


def _voice_accum_allowed(pid: str) -> tuple[bool, str, str]:
    """Decide whether voice accumulation is allowed for a session.

    Returns (allowed, reason, path). ``path`` is one of ``"face_witness"``,
    ``"voice_self_match"``, ``"bootstrap"``, or ``"refused"``. Paths are tried
    in that order — first-match wins. No hardcoded thresholds; all values come
    from config so tuning is a single knob per concern.
    """
    snap = _session_store.peek_snapshot(pid)
    ev = snap.evidence if snap is not None else None
    now = time.time()

    if ev is None:
        return (False, "no session", "refused")

    # Path A — recent confident face witness
    face_age = now - ev.face_last_seen_ts
    if (ev.face_match_conf >= VOICE_ACCUM_FACE_WITNESS_MIN_CONF
            and ev.anti_spoof_live
            and face_age <= VOICE_ACCUM_FACE_WITNESS_MAX_AGE_SEC):
        return (True,
                f"face witness (conf={ev.face_match_conf:.2f}, age={face_age:.1f}s)",
                "face_witness")

    # Path B — mature voice profile self-matching
    if (ev.voice_match_conf >= VOICE_ACCUM_VOICE_SELF_MATCH_MIN
            and ev.voice_sample_count >= VOICE_ACCUM_MATURE_SAMPLE_COUNT):
        return (True,
                f"voice self-match (conf={ev.voice_match_conf:.2f}, "
                f"n={ev.voice_sample_count})",
                "voice_self_match")

    # Path C — bootstrap credits from engagement gate
    if ev.bootstrap_credits > 0:
        return (True,
                f"bootstrap ({ev.bootstrap_credits} credits remaining)",
                "bootstrap")

    return (False,
            f"no witness (face_conf={ev.face_match_conf:.2f}, "
            f"age={face_age:.1f}s, voice_n={ev.voice_sample_count}, "
            f"voice_conf={ev.voice_match_conf:.2f}, "
            f"bootstrap={ev.bootstrap_credits})",
            "refused")


async def _on_room_end(
    room_session_id: str,
    speaker_pids: "list[str] | None" = None,
    started_at: "float | None" = None,
) -> None:
    """Session 112 Part 1 — hook fired when the last person leaves,
    ending a room session. Phase 3B.6 wires the real synthesis:
    `BrainOrchestrator.synthesize_room` runs in the background, writes
    a summary row to `room_summaries` for future greeting enrichment.

    Back-compat: ``speaker_pids`` and ``started_at`` are optional so
    existing callers (sync test contexts, legacy call sites that only
    pass the id) continue to work — synthesis simply skips when the
    participant list is missing.
    """
    # Session 116 P1 #9 — surface participant count + session age in the
    # hook log so an outside reviewer can audit room duration + scope.
    _participant_count = len(speaker_pids or [])
    _age_str = ""
    if started_at:
        _age_secs = max(0.0, time.time() - started_at)
        _age_str = f", duration={int(_age_secs)}s"
    print(
        f"[Room] Room-end hook fired for {room_session_id} "
        f"(participants={_participant_count}{_age_str})"
    )
    # Phase 3B.6 — dispatch synthesis fire-and-forget. Room lifecycle
    # never blocks on synthesis latency; if synthesis fails, the room
    # is still "ended" from the pipeline's POV — the summary just
    # isn't written.
    if (
        _brain_orchestrator is not None
        and speaker_pids is not None
        and len(speaker_pids) >= 2
    ):
        try:
            asyncio.create_task(
                _brain_orchestrator.synthesize_room(
                    room_session_id=room_session_id,
                    speaker_pids=list(speaker_pids),
                    started_at=started_at,
                )
            )
            # Session 116 P1 #9 + #10 — synthesis trigger + background
            # spawn visibility. Reviewer wants the decoupling visible
            # in logs.
            print(
                f"[Room] Synthesis dispatched (background) for "
                f"{room_session_id} — speakers={list(speaker_pids)}"
            )
        except RuntimeError:
            # No running loop (sync-test contexts); matches _close_session
            # fallback shape so test harness doesn't fail on missing loop.
            print(
                f"[Room] Synthesis skipped for {room_session_id} — "
                f"no running loop"
            )
    elif _brain_orchestrator is None:
        print(f"[Room] Synthesis skipped for {room_session_id} — orchestrator unavailable")
    elif speaker_pids is None or len(speaker_pids) < 2:
        # Single-speaker rooms are a documented skip (per-person
        # synthesis already covers this); make the rationale visible.
        print(
            f"[Room] Synthesis skipped for {room_session_id} — "
            f"single-speaker (per-person session-end already handled it)"
        )


def _close_session(person_id: str) -> None:
    """Close and remove a person's session."""
    global _stranger_track_map, _unrecognized_embeddings, _track_identity
    global _active_room_session, _active_room_started_at, _active_room_participants
    _close_snap = _session_store.peek_snapshot(person_id)
    _pname_log = _close_snap.person_name if _close_snap is not None else person_id
    print(f"[Session] Close: {person_id} — {_pname_log}")
    # Session 97 Fix 2: if this is a stranger session that accumulated
    # no usable data (gate-blocked at open and never spoke to the
    # accumulator), prune the row immediately instead of waiting for
    # the 7-day TTL. The FaceDB method does its own triple-check —
    # person_type=='stranger', zero voice embeddings, zero conversation
    # turns — so a genuine short-interaction stranger with even ONE
    # preserved signal survives until the TTL.
    _sess_pt_close = _close_snap.person_type if _close_snap is not None else None
    if _sess_pt_close == "stranger" and _face_db_ref is not None:
        try:
            _face_db_ref.prune_zero_value_stranger(person_id)
        except Exception as _prune_ex:
            print(f"[Session] zero-value prune failed for {person_id}: {_prune_ex!r}")
    try:
        asyncio.get_running_loop().create_task(_session_store.close_session(person_id))
    except RuntimeError:
        pass  # OPTIONAL: no running loop in test/early-boot context
    _sessions_started.discard(person_id)
    # Clean up any face-track → session bindings pointing to this session
    _stranger_track_map = {
        tid: pid for tid, pid in _stranger_track_map.items()
        if pid != person_id
    }
    # Prune cached embeddings whose track no longer has an active session
    _unrecognized_embeddings = {
        tid: emb for tid, emb in _unrecognized_embeddings.items()
        if tid in _stranger_track_map
    }
    # Remove track-continuity entries for this session so re-entry goes through full recognition
    _track_identity = {
        tid: pid for tid, pid in _track_identity.items()
        if pid != person_id
    }
    # Evict per-person caches so re-entry never hits stale data
    _query_embedding_cache.pop(person_id, None)
    _identity_hints.pop(person_id, None)
    # Clear any identity-dispute flag with the orchestrator — the session is
    # gone, so next time this pid appears it's a fresh start.
    if _brain_orchestrator:
        _brain_orchestrator.clear_disputed(person_id)

    # Session 112 Part 3 — _persons_in_frame session-scoped cleanup.
    # Previously entries lingered until SCENE_STALE_SECS aged them out
    # (30s), producing a window where the scene block still rendered
    # people whose sessions had already closed. Pop immediately on
    # session close. If they're physically present, next background
    # face scan re-adds them (correct — they're visible). If they've
    # actually left the room, the lingering entry is removed right
    # away. Resolves the scene-contradicts-session-state class of bug.
    _persons_in_frame.pop(person_id, None)

    # Session 112 Part 1 — room-session end hook. When this close
    # empties the active_sessions table, the room is over. Fire
    # fire-and-forget synthesis tasks (current 3A scope: just log
    # the room end + clear the id; 3B will hook room-level insight,
    # relationship update, cross-person safety scan here).
    if not _session_store.peek_all_snapshots() and _active_room_session is not None:
        _ended_room = _active_room_session
        _ended_started_at = _active_room_started_at
        _ended_participants = list(_active_room_participants)
        _active_room_session = None
        # Phase 3B.1 — clear paired start-time timestamp. Next mint starts
        # a fresh duration clock from zero.
        _active_room_started_at = None
        # Phase 3B.6 — clear participants alongside the id. Set is
        # rebuilt on next mint.
        _active_room_participants = set()
        print(f"[Room] Room session ended: {_ended_room}")
        # Guard against sync-test contexts where no event loop is
        # running — `asyncio.create_task` would raise/warn outside
        # an active loop. If the hook can't be scheduled, log it
        # without blocking the close path.
        try:
            asyncio.get_running_loop()
            asyncio.create_task(
                _on_room_end(_ended_room, _ended_participants, _ended_started_at)
            )
        except RuntimeError:
            print(f"[Room] Room-end hook skipped for {_ended_room} — no running loop")


def _expire_stale_sessions() -> bool:
    """Expire timed-out sessions and clean up per-person state.

    Called from both the outer WATCHING loop AND the inner conversation loop
    so zombie sessions (e.g. abandoned voice-only strangers) are cleaned up
    within VOICE_SESSION_TIMEOUT even during active conversations.

    Returns True if any session was closed.
    """
    global _vision_prev_det_count, _detected_lang
    _now_fl = time.time()
    _expired: list[str] = []
    for _snap in _session_store.peek_all_snapshots():
        # Identity-disputed sessions get a hard cap — vision keeps matching the
        # wrong person so `last_face_seen` never stales out via FACE_LOSS_GRACE.
        # Force-close after DISPUTE_MAX_DURATION so pollution has a bounded tail.
        # Finding K — if a future path sets person_type="disputed" without also
        # setting dispute_set_at, lazily anchor it here on the first check so the
        # timeout still fires (instead of permanently resetting to now each pass).
        if _is_disputed(_snap.person_id):
            _dispute_start = _snap.dispute_set_at
            if _dispute_start is None:
                try:
                    _loop = asyncio.get_running_loop()
                    _loop.create_task(_session_store.set_dispute_set_at(_snap.person_id, _now_fl))
                except RuntimeError:
                    asyncio.run(_session_store.set_dispute_set_at(_snap.person_id, _now_fl))  # OPTIONAL: sync fallback
                _dispute_start = _now_fl

            # Bug D1 (2026-04-22 live run): signal-based dispute auto-clear.
            # Previously disputes only cleared via DISPUTE_MAX_DURATION=180s —
            # 60% of a 5-minute demo broken when the LLM wrongly triggered
            # report_identity_mismatch.
            #
            # Session 73 post-review Medium C2: voice auto-clear trusts the
            # same sensor that triggered the dispute. Without face
            # corroboration, raise the bar to DISPUTE_AUTO_CLEAR_VOICE_SOLO_MIN
            # (0.85 — near-confirmed biometric match) so a wrongly-cleared
            # dispute requires a very strong signal. When face is co-present
            # (stronger corroboration via separate modality), the lower
            # DISPUTE_AUTO_CLEAR_VOICE_MIN (0.70) is acceptable. Restore via
            # prior_person_type (captured at dispute-flip).
            _ev = _snap.evidence
            _face_confirmed = (
                _face_in_frame(_snap.person_id, _persons_in_frame)
                and _ev.face_match_conf >= DISPUTE_AUTO_CLEAR_VOICE_MIN
            )
            _voice_floor = (
                DISPUTE_AUTO_CLEAR_VOICE_MIN
                if _face_confirmed
                else DISPUTE_AUTO_CLEAR_VOICE_SOLO_MIN
            )
            _recent_vc = _snap.recent_voice_confs
            _voice_confirmed = (
                len(_recent_vc) >= DISPUTE_AUTO_CLEAR_CONSECUTIVE_TURNS
                and all(
                    _c >= _voice_floor
                    for _c in list(_recent_vc)[-DISPUTE_AUTO_CLEAR_CONSECUTIVE_TURNS:]
                )
            )
            if _voice_confirmed or _face_confirmed:
                _reason = (
                    f"{DISPUTE_AUTO_CLEAR_CONSECUTIVE_TURNS} consecutive strong "
                    f"voice matches (≥{_voice_floor})"
                    + (" [face-corroborated]" if _face_confirmed else " [voice-only]")
                    if _voice_confirmed else
                    f"face in frame with face_match_conf≥{DISPUTE_AUTO_CLEAR_VOICE_MIN}"
                )
                # Session 73 post-review Critical #2: fail-closed fallback.
                # If a future dispute-flip path forgets to capture
                # prior_person_type, defaulting to "known" here would
                # silently promote a stranger session — privilege escalation.
                # "stranger" is the safer fallback; worst case is the session
                # loses best_friend privileges but a user re-auth via
                # engagement gate restores them on the next turn.
                _restore_type = _snap.prior_person_type or "stranger"
                # P0.7.3: atomic named call (handles person_type restore + all dispute fields)
                try:
                    _loop = asyncio.get_running_loop()
                    _loop.create_task(_session_store.clear_dispute(_snap.person_id, now=_now_fl))
                except RuntimeError:
                    asyncio.run(_session_store.clear_dispute(_snap.person_id, now=_now_fl))  # OPTIONAL: sync fallback
                if _brain_orchestrator:
                    _brain_orchestrator.clear_disputed(_snap.person_id)
                print(
                    f"[Dispute] Auto-cleared for {_snap.person_name} — "
                    f"{_reason}; restored person_type={_restore_type!r}"
                )
                # Session no longer disputed — fall through to normal session
                # expiry checks below (not `continue`, so we don't skip them).
            elif _now_fl - _dispute_start > DISPUTE_MAX_DURATION:
                print(
                    f"[Pipeline] Dispute timeout for {_snap.person_name} — "
                    f"force-closing after {_now_fl - _dispute_start:.0f}s"
                )
                _expired.append(_snap.person_id)
                continue
        if _snap.session_type == "face":
            if _now_fl - _snap.last_face_seen > FACE_LOSS_GRACE:
                _expired.append(_snap.person_id)
        else:  # voice-started
            if _now_fl - _snap.last_spoke_at > VOICE_SESSION_TIMEOUT:
                _expired.append(_snap.person_id)

    for _pid in _expired:
        _snap_exp = _session_store.peek_snapshot(_pid)
        if _snap_exp is None:
            continue
        _pname = _snap_exp.person_name
        print(f"[Pipeline] Session expired: {_pname} ({_pid})")
        _conversation.pop(_pid, None)
        _last_greeted[_pid] = time.time()
        if _brain_orchestrator:
            _brain_orchestrator.notify_session_end(_pid)
        _close_session(_pid)
        _vision_prev_det_count = 0

    if _expired and not _session_store.peek_all_snapshots():
        # All sessions closed — full cleanup
        lip_tracker.reset()
        set_lip_active(False)
        _persons_in_frame.clear()
        _detected_lang = "en"

    return bool(_expired)


async def _accumulate_voice(
    person_id:     str,
    audio:         "np.ndarray",
    db:            "FaceDB",
    face_verified: bool  = False,   # kept for compat; evidence-dict is authoritative now
    min_self_match: float = 0.35,
) -> None:
    """Voice accumulation policy — gated by _voice_accum_allowed().

    Three allowed paths (config-tuned, not hardcoded here):
      A) face witness   — recent confident face + anti-spoof live
      B) voice match    — mature self-match on an already-grown profile
      C) bootstrap      — engagement-gate credits burning down on early turns

    When all three fail, accumulation is refused and the session won't grow
    its voice profile until better evidence arrives.
    """
    loop    = asyncio.get_running_loop()
    _acc_snap = _session_store.peek_snapshot(person_id)

    # Session 94 Fix #5 — bootstrap credit replenishment. When an engagement-
    # gated stranger (said the system name earlier, ``waiting_for_name=False``)
    # has burned all initial bootstrap credits but hasn't yet reached voice
    # profile maturity (Path B threshold), top up 1 credit per turn up to
    # VOICE_MAX_BOOTSTRAP_CREDITS. Without this, a stranger whose session
    # expires and re-opens via voice match inherits bootstrap=0 from the
    # ``_open_session`` default (no engagement_gate_passed=True on re-open
    # path), and every subsequent accumulation refuses — profile frozen.
    # Observed 2026-04-22 live run: stranger stuck at voice_n=2 across
    # multiple visits despite passing engagement gates each time.
    from core.config import (
        VOICE_BOOTSTRAP_REPLENISH_ENABLED, VOICE_MAX_BOOTSTRAP_CREDITS,
        VOICE_BOOTSTRAP_DEBUG,
    )
    # F2 diagnostic — log entry state before replenishment decision.
    if VOICE_BOOTSTRAP_DEBUG:
        _ev_pre = _acc_snap.evidence if _acc_snap is not None else None
        print(
            f"[Voice-Debug] _accumulate_voice entry: pid={person_id} "
            f"voice_only_origin={_acc_snap.voice_only_origin if _acc_snap is not None else False} "
            f"waiting_for_name={_acc_snap.waiting_for_name if _acc_snap is not None else False} "
            f"bootstrap_pre={_ev_pre.bootstrap_credits if _ev_pre is not None else 0} "
            f"voice_n={_ev_pre.voice_sample_count if _ev_pre is not None else 0}"
        )
    # S120 #1/#2 — condition widened from person_type=="stranger" to
    # voice_only_origin flag. A voice-only person promoted from stranger →
    # known loses person_type=="stranger" the moment update_person_name fires,
    # which previously froze their voice profile permanently at whatever
    # voice_n they had reached. The flag survives promotion and drives
    # replenishment until the profile matures or a face is witnessed.
    # F2 fix: default changed from True → False. known/best_friend sessions
    # don't carry waiting_for_name at all; defaulting to True caused
    # replenishment to always skip for every non-stranger voice-only session.
    if (VOICE_BOOTSTRAP_REPLENISH_ENABLED
            and (_acc_snap.voice_only_origin if _acc_snap is not None else False)
            and not (_acc_snap.waiting_for_name if _acc_snap is not None else False)):
        _snap_rep = _session_store.peek_snapshot(person_id)
        _ev_rep = _snap_rep.evidence if _snap_rep is not None else None
        voice_n = _ev_rep.voice_sample_count if _ev_rep is not None else 0
        current_credits = _ev_rep.bootstrap_credits if _ev_rep is not None else 0
        if (voice_n < VOICE_ACCUM_MATURE_SAMPLE_COUNT
                and current_credits < VOICE_MAX_BOOTSTRAP_CREDITS):
            loop.create_task(_session_store.increment_bootstrap_credits(
                person_id, cap=VOICE_MAX_BOOTSTRAP_CREDITS,
            ))
            if VOICE_BOOTSTRAP_DEBUG:
                print(
                    f"[Voice-Debug] Replenishment FIRED for {person_id} "
                    f"→ bootstrap≈{min(current_credits + 1, VOICE_MAX_BOOTSTRAP_CREDITS)}"
                )
        elif VOICE_BOOTSTRAP_DEBUG:
            # Log WHY replenishment was skipped.
            _reasons = []
            if not (_acc_snap.voice_only_origin if _acc_snap is not None else False):
                _reasons.append("voice_only_origin=False")
            if _ev_rep is not None and _ev_rep.voice_sample_count >= VOICE_ACCUM_MATURE_SAMPLE_COUNT:
                _reasons.append(f"already_mature(voice_n={_ev_rep.voice_sample_count})")
            if _ev_rep is not None and _ev_rep.bootstrap_credits >= VOICE_MAX_BOOTSTRAP_CREDITS:
                _reasons.append(f"at_cap(credits={_ev_rep.bootstrap_credits})")
            print(
                f"[Voice-Debug] Replenishment SKIPPED for {person_id}: "
                f"{', '.join(_reasons) if _reasons else 'condition_gate_false'}"
            )
    elif VOICE_BOOTSTRAP_DEBUG:
        print(
            f"[Voice-Debug] Replenishment gate skipped for {person_id}: "
            f"REPLENISH_ENABLED={VOICE_BOOTSTRAP_REPLENISH_ENABLED} "
            f"voice_only_origin={_acc_snap.voice_only_origin if _acc_snap is not None else False} "
            f"waiting_for_name={_acc_snap.waiting_for_name if _acc_snap is not None else False}"
        )

    allowed, reason, path = _voice_accum_allowed(person_id)
    if VOICE_BOOTSTRAP_DEBUG:
        print(f"[Voice-Debug] _voice_accum_allowed for {person_id}: {path} / allowed={allowed} ({reason})")
    if not allowed:
        print(f"[Voice] Refused accumulation for {person_id}: {reason}")
        if VOICE_BOOTSTRAP_DEBUG:
            _snap_exit = _session_store.peek_snapshot(person_id)
            _ev_exit = _snap_exit.evidence if _snap_exit is not None else None
            print(
                f"[Voice-Debug] _accumulate_voice exit (refused): pid={person_id} "
                f"bootstrap_post={_ev_exit.bootstrap_credits if _ev_exit is not None else 0}"
            )
        return

    v_pid, v_score = await loop.run_in_executor(
        None, voice_mod.identify, audio, _voice_gallery, VOICE_RECOGNITION_THRESHOLD
    )
    # Track the latest voice self-match in evidence regardless of accumulation outcome.
    if v_pid == person_id and v_score > 0.0:
        loop.create_task(_session_store.update_voice_heard(
            person_id, conf=v_score, ts=time.time(),
        ))

    if v_pid == person_id and v_score >= min_self_match:
        source = "voice_self_match"
    elif path in ("face_witness", "bootstrap"):
        source = "voice_face_verified"
    else:
        return  # Path B said OK but self-match weak — skip this sample

    emb = await loop.run_in_executor(None, voice_mod.embed, audio)
    if emb is None:
        return
    added = await loop.run_in_executor(
        None, db.add_voice_embedding, person_id, emb, source, v_score
    )
    if added:
        updated = await loop.run_in_executor(None, db.load_voice_profile_for, person_id)
        if updated is not None:
            _voice_gallery[person_id] = updated
        count = await loop.run_in_executor(None, db.voice_embedding_count, person_id)
        _voice_gallery_sizes[person_id] = count
        # Update evidence: sample count grew; if this was a bootstrap grant, burn a credit.
        loop.create_task(_session_store.set_voice_sample_count(person_id, count))
        if path == "bootstrap":
            loop.create_task(_session_store.decrement_bootstrap_credits(person_id))
        print(f"[Voice] Profile updated for {person_id} ({count}/{MAX_VOICE_EMBEDDINGS} voice samples) [via {path}]")
        if VOICE_BOOTSTRAP_DEBUG:
            _snap_added = _session_store.peek_snapshot(person_id)
            _ev_added = _snap_added.evidence if _snap_added is not None else None
            print(
                f"[Voice-Debug] _accumulate_voice exit (added): pid={person_id} "
                f"bootstrap_post={_ev_added.bootstrap_credits if _ev_added is not None else 0} "
                f"voice_n={_ev_added.voice_sample_count if _ev_added is not None else 0}"
            )


def _should_run_recognition(
    track_id: "int | None",
    track_identity: dict,
    unrecognized_tracks: dict,
    persons_in_frame: dict,
    now: float,
) -> bool:
    """Event-driven cadence gate for the secondary recognition scan (#11).

    Returns True when this track genuinely needs a recognition pass:
    - Brand-new track (never seen before)
    - Known person: refresh after 5s
    - Unknown/unrecognized track: retry after 2s
    """
    if track_id is None:
        return True
    if track_id not in track_identity and track_id not in unrecognized_tracks:
        return True  # brand-new track — run immediately
    if track_id in track_identity:
        pid = track_identity[track_id]
        last = persons_in_frame.get(pid, {}).get("last_recognized_at", 0.0)
        return now - last > 5.0  # refresh known person every 5s
    last_seen = unrecognized_tracks.get(track_id, 0.0)
    return now - last_seen > 2.0  # retry unknown track every 2s


async def _background_vision_loop(
    camera: Camera,
    detector: "FaceDetector",
    embedder: "FaceEmbedder | None" = None,
    temporal_buffer: "TemporalEmbeddingBuffer | None" = None,
    db: "FaceDB | None" = None,
) -> None:
    """Keep vision alive during conversation (LISTENING / THINKING / SPEAKING).

    Runs as a background asyncio task while the inner conversation loop runs.
    Updates: face-loss timer, latest frame, active-person bbox, lip-tracker baseline.
    When embedder+temporal_buffer+db are provided (ambient listen path), also runs
    full recognition so a known face wakes the pipeline without waiting for speech.
    All FAISS writes stay on the main loop to avoid thread-safety issues.
    YOLO intentionally NOT run here — see comment at bottom of loop.
    """
    loop = asyncio.get_running_loop()
    while True:
        frame = await loop.run_in_executor(None, camera.read)
        if frame is None:
            await asyncio.sleep(0.05)
            continue
        global _last_face_seen, _latest_vision_frame, _latest_frame_time, _latest_yolo_detections, _last_active_bbox, _last_silent_update, _ambient_wake_pending
        _latest_vision_frame = frame
        _latest_frame_time   = time.monotonic()
        detections = await loop.run_in_executor(None, detector.detect, frame)
        if detections:
            # During ambient listen (no active sessions), any face counts as "seen".
            # During active conversation, _last_face_seen is updated by the secondary
            # scan below (which runs recognition). detect() never sets person_id, so
            # we can't filter by active person here.
            if not _session_store.peek_all_snapshots():
                _last_face_seen = time.time()
            # Keep bbox current and calibrate lip tracker.
            # Calibration runs during SPEAKING — the person is quiet and still,
            # making it the ideal resting-motion baseline window.
            if _session_store.peek_all_snapshots():
                for det in detections:
                    if _session_store.peek_snapshot(det.person_id) is not None:
                        _last_active_bbox = det.bbox
                        if _pipeline_state == PipelineState.SPEAKING:
                            lip_tracker.update_baseline(frame, det.bbox)
                        break

        # ── Full recognition when no active sessions (ambient listen path) ────
        if (
            embedder is not None
            and temporal_buffer is not None
            and db is not None
            and not _session_store.peek_all_snapshots()
            and detections
        ):
            for _det in detections:
                _x1, _y1, _x2, _y2 = _det.bbox
                _crop = frame[_y1:_y2, _x1:_x2]
                if _crop.size == 0:
                    continue
                _q = face_quality_score(_crop)
                if _q < FACE_QUALITY_RECOGNITION:
                    continue
                if _det.landmarks is not None:
                    _yaw = estimate_yaw_from_landmarks(_det.landmarks, _det.bbox)
                    if abs(_yaw) > 60.0:
                        continue
                _raw_emb = await loop.run_in_executor(None, embedder.embed, _crop)
                _emb = temporal_buffer.add_and_pool(_det.bbox, _raw_emb, track_id=_det.track_id)
                _thresh = adaptive_threshold(_q, RECOGNITION_THRESHOLD)
                if _det.track_id is not None and temporal_buffer.pool_depth(_det.track_id) < 3:
                    _thresh += 0.05
                _pid, _pname, _conf = await loop.run_in_executor(None, db.recognize, _emb, _thresh)
                if (_pid
                        and time.time() - _last_greeted.get(_pid, 0) >= GREET_COOLDOWN
                        and _pid not in _ambient_wake_pending):
                    if not verify_live(frame, _det.bbox, _anti_spoof_checker):
                        print(f"[Pipeline] Anti-spoof: BLOCKED background wake for {_pname} — liveness failed")
                        continue
                    _ambient_wake_pending.add(_pid)   # debounce: suppress re-fires until outer loop consumes
                    print(f"[Vision] Background: recognized {_pname} (score={_conf:.3f}) — waking pipeline")
                    stop_audio()  # interrupt ambient listen; outer loop handles greeting next iteration
                    break
                elif not _pid:
                    # Unrecognized face during ambient listen — accumulate silent observation.
                    await loop.run_in_executor(
                        None, _maybe_record_silent_obs, _emb, _det.bbox, frame.shape[1], frame.shape[0], db
                    )

        # ── Secondary face scan during active conversation ────────────────────
        # Recognises all faces in frame so brain knows when a new person appears.
        # Runs immediately when face count rises (new arrival), otherwise throttled
        # to 1/s to avoid hammering the GPU during normal conversation.
        global _persons_in_frame, _vision_face_scan_last, _vision_prev_det_count, \
               _unrecognized_tracks, _unrecognized_embeddings, _stranger_track_map, _track_identity, \
               _last_vision_report_str
        _bv_scan_now = time.time()
        _det_count = len(detections) if detections else 0
        _new_arrival = _det_count > _vision_prev_det_count
        _vision_prev_det_count = _det_count
        if (
            embedder is not None
            and temporal_buffer is not None
            and db is not None
            and _session_store.peek_all_snapshots()
            and detections
        ):
            # Prune track dicts to currently-live SORT track_ids
            _active_tids = {_det.track_id for _det in detections if _det.track_id is not None}
            _unrecognized_tracks = {
                tid: ts for tid, ts in _unrecognized_tracks.items()
                if _bv_scan_now - ts < SCENE_STALE_SECS
            }
            _unrecognized_embeddings = {
                tid: emb for tid, emb in _unrecognized_embeddings.items()
                if tid in _unrecognized_tracks
            }
            _stranger_track_map = {
                tid: pid for tid, pid in _stranger_track_map.items()
                if tid in _unrecognized_tracks
            }
            # Track-continuity: prune identities for tracks that have left frame
            _track_identity = {
                tid: pid for tid, pid in _track_identity.items()
                if tid in _active_tids
            }
            for _det in detections:
                # Event-driven cadence: skip if this track was recently recognized (#11)
                if not _should_run_recognition(
                    _det.track_id, _track_identity, _unrecognized_tracks,
                    _persons_in_frame, _bv_scan_now,
                ):
                    continue
                _x1, _y1, _x2, _y2 = _det.bbox
                _crop = frame[_y1:_y2, _x1:_x2]
                if _crop.size == 0:
                    continue
                _q2 = face_quality_score(_crop)
                if _q2 < FACE_QUALITY_RECOGNITION:
                    continue
                _raw_emb2 = await loop.run_in_executor(None, embedder.embed, _crop)
                # V3: pool across frames for stability (same buffer as primary loop)
                _emb2 = temporal_buffer.add_and_pool(_det.bbox, _raw_emb2, track_id=_det.track_id)
                # V4: adaptive threshold — stricter for low-quality crops
                _thresh2 = adaptive_threshold(_q2, RECOGNITION_THRESHOLD)
                if _det.track_id is not None and temporal_buffer.pool_depth(_det.track_id) < 3:
                    _thresh2 += 0.05
                _pid2, _pname2, _conf2 = await loop.run_in_executor(
                    None, db.recognize, _emb2, _thresh2
                )
                if _pid2:
                    # Record confirmed identity for this track (used by main-loop track-continuity)
                    if _det.track_id is not None:
                        _track_identity[_det.track_id] = _pid2
                    if _session_store.peek_snapshot(_pid2) is not None:
                        # Active person confirmed in frame — update their face-seen timestamp
                        # so brain knows they're visible. (detect() never sets person_id,
                        # so the primary loop can't do this; secondary scan is the only place.)
                        try:
                            _loop = asyncio.get_running_loop()
                            _loop.create_task(_session_store.set_last_face_seen(_pid2, _bv_scan_now))
                        except RuntimeError:
                            pass  # OPTIONAL: no running loop in test/early-boot context
                    if _pid2 not in _persons_in_frame:
                        _persons_in_frame[_pid2] = {
                            "name": _pname2, "conf": _conf2,
                            "last_seen": _bv_scan_now, "last_recognized_at": _bv_scan_now,
                            "source": "face",   # Bug B: distinguish from voice-only entries
                        }
                        if _session_store.peek_snapshot(_pid2) is None:
                            if verify_live(frame, _det.bbox, _anti_spoof_checker):
                                print(f"[Vision] New person in frame: {_pname2} (conf={_conf2:.2f})")
                    else:
                        _persons_in_frame[_pid2]["last_seen"]          = _bv_scan_now
                        _persons_in_frame[_pid2]["last_recognized_at"] = _bv_scan_now
                        _persons_in_frame[_pid2]["conf"]               = _conf2
                        _persons_in_frame[_pid2]["source"]             = "face"
                        # Session 102 Bug F.3: refresh the cached display
                        # name every scan. Previously "name" was written
                        # once at pid-first-seen and never updated — so
                        # after a rename (Bug F.2 path or stranger
                        # promotion) the SCENE block and [Vision] logs
                        # kept rendering the STT-mangled original name
                        # for the remainder of the session. Re-reading
                        # from the fresh recognize() result is cheap
                        # (string assign, 1 Hz) and self-heals any
                        # rename within one scan.
                        _persons_in_frame[_pid2]["name"]               = _pname2
                    # Step 3: update identity_evidence with the fresh face match.
                    # anti_spoof_live isn't re-checked here (secondary scan is 1 Hz;
                    # liveness was verified at greeting). Session stays recent-witness.
                    try:
                        _loop = asyncio.get_running_loop()
                        _loop.create_task(_session_store.update_face_seen(
                            _pid2, conf=_conf2, ts=_bv_scan_now))
                    except RuntimeError:
                        pass  # OPTIONAL
                    # S120 #1/#2 — person stepped in front of camera; face
                    # witness now available so voice_only_origin is no longer
                    # the sole accumulation path.
                    _pid2_snap_voi = _session_store.peek_snapshot(_pid2)
                    if _pid2_snap_voi is not None and _pid2_snap_voi.voice_only_origin:
                        try:
                            _loop = asyncio.get_running_loop()
                            _loop.create_task(_session_store.set_voice_only_origin(_pid2, False))
                        except RuntimeError:
                            pass  # OPTIONAL: no running loop in test/early-boot context
                else:
                    # Unrecognized face — record by SORT track_id for per-person routing
                    _tid = _det.track_id if _det.track_id is not None else id(_det)
                    _unrecognized_tracks[_tid] = _bv_scan_now
                    _unrecognized_embeddings[_tid] = _emb2  # cache for gate-pass face enrollment
                    # #20: pre-allocate a stranger pid for each stable (SORT-confirmed) track
                    if _det.track_id is not None and _tid not in _stranger_track_map:
                        import uuid as _uuid_pa
                        _stranger_track_map[_tid] = f"stranger_{_uuid_pa.uuid4().hex[:8]}"
            # Prune recognized persons who left (not seen for >5s)
            _left_persons = {k: v for k, v in list(_persons_in_frame.items()) if _bv_scan_now - v["last_seen"] >= SCENE_STALE_SECS}
            for _lp_id, _lp_info in _left_persons.items():
                # Bug B: suppress the "left frame" log for voice-only entries — they
                # were never ON-camera, so "left frame" is misleading and the "conf"
                # field actually carries voice_score for those.
                #
                # Obs 4 (2026-04-20): when a voice entry ages out of _persons_in_frame
                # (at SCENE_STALE_SECS) but its session is still alive (expires at
                # VOICE_SESSION_TIMEOUT, 5–30s later), there's a silent window where
                # debugging "why did we stop tracking X's speech?" had no log. Emit a
                # distinct [Voice] message so the session-state transition is visible.
                # If no active session exists, stay silent — _close_session already
                # logged the close at VOICE_SESSION_TIMEOUT.
                if _lp_info.get("source") == "voice":
                    _snap_voice_lp = _session_store.peek_snapshot(_lp_id)
                    if _snap_voice_lp is not None:
                        _remaining = VOICE_SESSION_TIMEOUT - (_bv_scan_now - _snap_voice_lp.last_spoke_at)
                        print(f"[Voice] {_lp_info['name']} no longer heard — session expires in {_remaining:.0f}s")
                    continue
                print(f"[Vision] Person left frame: {_lp_info['name']} (conf={_lp_info['conf']:.2f})")
            for _stale_k in _left_persons:
                _persons_in_frame.pop(_stale_k, None)

            # ── Phase 2 / Session 124 — Vision Channel shadow logging ─────
            # Throttled comparison: once per VISION_SHADOW_INTERVAL_SECS,
            # call the new pure observe_scene() with the SAME detections we
            # just used (via a precomputed-detections shim — avoids running
            # the FaceDetector twice and avoids corrupting SORT state).
            # Compare its visible_pids against the production
            # _persons_in_frame face-source entries. Production behavior
            # unchanged — observation only. Wrapped in try/except so a bug
            # in the new code can't break the vision loop.
            global _last_vision_shadow_at
            if (db is not None and embedder is not None
                    and (_bv_scan_now - _last_vision_shadow_at) >= VISION_SHADOW_INTERVAL_SECS):
                _last_vision_shadow_at = _bv_scan_now
                try:
                    from core.vision_channel import observe_scene as _vc_observe

                    class _PrecomputedDetectionsShim:
                        """One-shot detector that returns the just-computed
                        `detections` instead of re-running RetinaFace + SORT.
                        Side-effect-free."""
                        def __init__(self, dets):
                            self._dets = dets
                        def detect(self, _frame):
                            return self._dets

                    _shadow_state = _vc_observe(
                        frame,
                        face_detector=_PrecomputedDetectionsShim(detections),
                        face_embedder=embedder,
                        face_db=db,
                        recognition_threshold=RECOGNITION_THRESHOLD,
                        quality_min=FACE_QUALITY_RECOGNITION,
                        yaw_max_deg=60.0,
                        now=_bv_scan_now,
                    )
                    # Note on transient single-frame divergence (verified
                    # against canary 2026-04-29 line 1068): production
                    # `_persons_in_frame` smooths face presence over
                    # SCENE_STALE_SECS (5s); vision_channel.observe_scene()
                    # is per-frame. When RetinaFace transiently misses
                    # a face for one frame (blink, turn, lighting flicker),
                    # _prod_visible still holds the pid (windowed), but
                    # _new_visible drops it (this frame's truth). That's
                    # an expected semantic difference, NOT a vision_channel
                    # bug. The reconciler routing path consumes
                    # _persons_in_frame via _build_routing_inputs (smoothed),
                    # so production behavior under the cutover is unaffected.
                    # Single-frame divergences on face flicker are noise;
                    # SUSTAINED multi-scan divergence would indicate a real
                    # gate or stale-window mismatch worth investigating.
                    _prod_visible = {
                        pid for pid, info in list(_persons_in_frame.items())
                        if info.get("source") == "face"
                        and _bv_scan_now - info.get("last_seen", 0) < SCENE_STALE_SECS
                    }
                    _new_visible = set(_shadow_state.visible_pids)
                    if _prod_visible != _new_visible:
                        _diff_added = _new_visible - _prod_visible
                        _diff_dropped = _prod_visible - _new_visible
                        print(
                            f"[VisionChannel-Shadow] {_now_log_ts()} divergence: "
                            f"new_only={sorted(_diff_added)} prod_only={sorted(_diff_dropped)} "
                            f"new_total={len(_new_visible)} prod_total={len(_prod_visible)}"
                        )
                except Exception as _vc_shadow_e:
                    print(f"[VisionChannel-Shadow] error: {type(_vc_shadow_e).__name__}: {_vc_shadow_e!r}")

        # ── Real-time vision state emit ───────────────────────────────────────
        # Emits [Vision] <names> whenever the visible-people set changes.
        # Uses raw det_count for instant "none" detection (~167 ms latency);
        # uses recognition data for named entries (1 s latency from scan).
        _det_count_bv = len(detections) if detections else 0
        if _det_count_bv == 0:
            _vis_report_now = "none"
        else:
            _now_vr  = time.time()
            # Bug B: only count face-sourced entries in the visual-scene report.
            # Voice-only entries live in _persons_in_frame for routing purposes
            # but don't belong in the "who is ON CAMERA" line.
            _rnames  = sorted(
                v["name"] for v in list(_persons_in_frame.values())
                if (_now_vr - v["last_seen"] < VOICE_ROUTING_FACE_STALE_SECS
                    and v.get("source") != "voice")
            )
            _unrec_n = sum(
                1 for ts in _unrecognized_tracks.values()
                if _now_vr - ts < VOICE_ROUTING_FACE_STALE_SECS
            )
            _vr_parts = list(_rnames)
            if _unrec_n == 1:
                _vr_parts.append("unrecognized")
            elif _unrec_n > 1:
                _vr_parts.append(f"{_unrec_n}x unrecognized")
            _vis_report_now = ", ".join(_vr_parts) if _vr_parts else "none"

        if _vis_report_now != _last_vision_report_str:
            print(f"[Vision] {_vis_report_now}")
            _last_vision_report_str = _vis_report_now

        # ── Vision heartbeat during conversation ──────────────────────────────
        global _vision_last_heartbeat, _vision_last_heartbeat_state
        _bv_now = time.time()
        if _bv_now - _vision_last_heartbeat >= 30.0:
            _vision_last_heartbeat = _bv_now
            state_label = _pipeline_state.name if _pipeline_state else "?"
            if _session_store.peek_all_snapshots():
                who = ", ".join(snap.person_name for snap in _session_store.peek_all_snapshots())
            elif detections:
                # Bug B: only face-sourced entries count as "known faces" here.
                _known_faces = [v["name"] for v in list(_persons_in_frame.values())
                                if v.get("source") != "voice"]
                who = ("recognized=" + ", ".join(_known_faces)) if _known_faces else "unrecognized"
            else:
                who = "no face"
            _hb_key = f"{state_label}|{who}"
            if _hb_key != _vision_last_heartbeat_state:
                _vision_last_heartbeat_state = _hb_key
                print(f"[Vision] Active ({state_label}) — {who}")

        # YOLO is NOT run here during conversation — PyTorch CPU ops hold the Python
        # GIL, which blocks httpx's async I/O callbacks and stalls LLM token streaming.
        # Object detection runs in the outer watching loop instead (idle time only).


async def _cloud_retry_loop() -> None:
    """
    Background task: runs for the full session lifetime once spawned.
    Pings Together.ai every CLOUD_RETRY_INTERVAL seconds while SICK or OFFLINE.
    Skips pinging when ONLINE — keeps the loop alive for any future outage.
    Sets _cloud_recovered flag on recovery.
    """
    global _cloud_state, _cloud_recovered
    while not _shutdown_event.is_set():
        try:
            await asyncio.wait_for(_shutdown_event.wait(), timeout=CLOUD_RETRY_INTERVAL)
            return  # shutdown requested
        except asyncio.TimeoutError:
            pass

        if _cloud_state == CloudState.ONLINE:
            continue  # ONLINE — skip ping, keep loop alive for next potential outage

        print("[Pipeline] Retrying Together.ai connection...")
        available = await ping_together()
        if available:
            print("[Pipeline] Together.ai reconnected!")
            _cloud_state    = CloudState.ONLINE
            _cloud_recovered = True
            if _brain_orchestrator:
                _brain_orchestrator.report_api_recovered()
        elif _cloud_failed_at and _brain_orchestrator:
            _brain_orchestrator.report_api_failure(time.time() - _cloud_failed_at)


async def _kairos_tick(person_id: str, person_name: str, db: "FaceDB", memory_search_fn: "Callable | None" = None, best_friend_id: str | None = None) -> bool:
    """Brain-driven proactive conversation (KAIROS).

    Wakes every KAIROS_SILENCE_THRESHOLD seconds of user silence and asks the
    main brain whether it wants to say something.  The brain decides freely —
    a thought, a question, noticing something — or stays silent.

    Returns True if the brain spoke; False otherwise.
    """
    global _last_kairos_at

    if person_id.startswith("stranger_"):
        return False
    # Finding H — don't initiate proactive speech during an identity-disputed
    # session. We don't know who the speaker actually is; asking the brain to
    # start a fresh turn toward them would produce confused phrasing.
    if _is_disputed(person_id):
        return False
    if not _brain_orchestrator:
        return False

    now = time.time()
    _silence_elapsed  = now - _last_user_speech_at
    _cooldown_elapsed = now - _last_kairos_at

    if _silence_elapsed < KAIROS_SILENCE_THRESHOLD:
        return False
    if _cooldown_elapsed < KAIROS_COOLDOWN:
        return False

    # Offer the brain a pending pattern question as a suggestion, but let it
    # decide freely whether to use it, rephrase it, or say something else.
    pending_q = _brain_orchestrator.get_pending_question() if _brain_orchestrator else None
    question_hint = (
        f"\nSuggested question (use it, rephrase it, or ignore it): \"{pending_q['text']}\""
        if pending_q else ""
    )

    kairos_prompt = (
        f"[PROACTIVE] It's been {_silence_elapsed:.0f} seconds since {person_name} last spoke. "
        f"You may say something natural — a question, a thought, noticing something, following up "
        f"on what you've been talking about. Or stay silent if nothing feels right. "
        f"If you choose to stay silent, reply with only the single word: SILENT.{question_hint}"
    )

    print(f"[KAIROS] Brain proactive wake — {_silence_elapsed:.0f}s silence")

    history = _conversation.get(person_id, [])

    kairos_scene_block = (
        _get_scene_block_cached(
            person_id, time.time(), _session_store.peek_all_snapshots(), _persons_in_frame,
            _unrecognized_tracks, best_friend_id,
            recent_visitors=_fetch_recent_visitors_for_scene(best_friend_id),
        )
        if SCENE_BLOCK_ENABLED else None
    )
    _kairos_snap     = _session_store.peek_snapshot(person_id) if person_id else None
    _kairos_rec_conf = _persons_in_frame.get(person_id, {}).get("conf", 0.0) if person_id else 0.0
    kairos_vision_state = {
        "face_in_frame":          time.time() - _last_face_seen < 2.0,
        "person_name":            person_name,
        "person_id":              person_id,
        "recognition_conf":       _kairos_rec_conf,
        "identity_disputed":      _is_disputed(person_id),
        "disputed_claimed_name":  _kairos_snap.disputed_claimed_name if _kairos_snap is not None else None,
        # Session person_type drives the brain's <<<TOOL ACCESS>>> block. Fallback
        # to stranger (most restricted) if session dict is missing the field.
        "session_person_type":    _kairos_snap.person_type if _kairos_snap is not None else "stranger",
        # Structured identity_evidence drives the brain's <<<IDENTITY EVIDENCE>>> block.
        # Kept as dict read: brain.py consumes via .get() which requires dict interface.
        "identity_evidence":      dataclasses.asdict(_kairos_snap.evidence) if _kairos_snap is not None else None,
        # Session 97 Fix 1: surface turn count for <<<STRANGER IDENTITY>>>
        # block. KAIROS does NOT bump — this is a brain-initiated silence
        # fill, not a user turn.
        "session_user_turns":     _kairos_snap.user_turns if _kairos_snap is not None else 0,
        # Session 113 Part 1: drives the <<<ADDRESS DECISION>>> block.
        # Block only fires in multi-person rooms; single-person keeps
        # current dispatch behavior unchanged.
        "active_session_count":   len(_session_store.peek_all_snapshots()),
        # Phase 3B.1: unified room-state block. Returns None in
        # single-person sessions so this field is benign there.
        "room_block":             _build_room_block(
            _session_store.peek_all_snapshots(), _conversation, _emotion_agents,
            _active_room_started_at, turn_cap=ROOM_BLOCK_TURN_CAP,
        ),
        # Phase 3B.6: recent room context for greeting/engagement
        # enrichment. None when no qualifying room within window.
        "recent_room_context":    _fetch_recent_room_context(person_id),
    }

    try:
        response_parts: list[str] = []

        # Wave 4 Item 17 — session-stable prefix cache for KAIROS path.
        if _kairos_snap is not None:
            if _kairos_snap.cached_prefix is None:
                _kp_value = render_session_stable_prefix(
                    system_name=_active_system_name,
                    session_person_type=_kairos_snap.person_type,
                    session_user_turns=_kairos_snap.user_turns,
                    identity_disputed=_is_disputed(person_id),
                    person_name=person_name,
                    disputed_claimed_name=_kairos_snap.disputed_claimed_name,
                    core_memory=_kairos_snap.core_memory,
                )
                try:
                    _loop = asyncio.get_running_loop()
                    _loop.create_task(_session_store.set_cached_prefix(person_id, _kp_value))
                except RuntimeError:
                    pass  # OPTIONAL: no running loop in test/early-boot context
            _kairos_cached_prefix = _kairos_snap.cached_prefix
        else:
            _kairos_cached_prefix = None

        async def _kairos_token_gen():
            async for ev_type, payload in ask_stream(
                kairos_prompt,
                person_name=person_name,
                conversation_history=history,
                language=_detected_lang,
                system_name=_active_system_name,
                memory_search_fn=memory_search_fn,
                room_search_fn=_make_room_search_fn(
                    _active_room_session, person_id, db,
                ),
                vision_state=kairos_vision_state,
                scene_block=kairos_scene_block,
                cached_prefix=_kairos_cached_prefix,
            ):
                if ev_type == "text":
                    response_parts.append(payload)
                    yield payload

        _set_state(PipelineState.SPEAKING, person_name)
        await speak_stream(_sentence_stream(_kairos_token_gen()), language=_detected_lang)
        response = "".join(response_parts).strip()

        # Brain chose silence — don't log, don't reset cooldown aggressively
        if not response or response.upper() == "SILENT":
            print(f"[KAIROS] Brain chose silence")
            _last_kairos_at = time.time()  # still advance cooldown to avoid spin
            _set_state(PipelineState.LISTENING, person_name)
            return False

        print(f"[KAIROS] Brain spoke: {response[:60]!r}")
        _conversation.setdefault(person_id, []).extend([
            {"role": "user",      "content": "[silence]"},
            {"role": "assistant", "content": response},
        ])
        # Skip persistent log_turn while session is identity-disputed (same rationale
        # as conversation_turn — don't persist turns under a sensor-match we no longer trust).
        # Session 73 post-review Critical #1: route through _is_disputed to keep the
        # single-source-of-truth invariant intact — the negation-form raw comparison
        # was a hole in the Step 3 grep check, which now covers both equality
        # polarities against the disputed literal.
        if not _is_disputed(person_id):
            # Session 112 Part 1 — tag KAIROS-generated turns with the
            # active room_session_id for 3B retrieval parity.
            _k_snap = _session_store.peek_snapshot(person_id)
            _k_room_sid = _k_snap.room_session_id if _k_snap is not None else None
            db.log_turn(person_id, "user",      "[silence]",
                        room_session_id=_k_room_sid,
                        audience_ids=[person_id])
            db.log_turn(person_id, "assistant", response,
                        room_session_id=_k_room_sid,
                        audience_ids=[person_id])
            if _brain_orchestrator:
                _brain_orchestrator.notify()

    except Exception as e:
        print(f"[KAIROS] Stream failed: {e}")
        return False

    if pending_q:
        _brain_orchestrator.mark_question_asked(pending_q["id"])
    _last_kairos_at = time.time()

    _set_state(PipelineState.LISTENING, person_name)
    return True


async def _dream_loop(db: "FaceDB") -> None:
    """Pattern 4: autoDream — consolidate memory during idle periods.

    Waits for DREAM_IDLE_MINUTES of idle (no active person), then calls
    brain_orchestrator.dream() to write decay back to stored knowledge and
    tidy schema synonyms. Runs at most once per DREAM_COOLDOWN seconds.
    Wakes immediately on shutdown.
    """
    global _last_dream_run_at
    # Initial delay: let the system settle after startup
    try:
        await asyncio.wait_for(_shutdown_event.wait(), timeout=DREAM_IDLE_MINUTES * 60)
        return  # shutdown during initial wait
    except asyncio.TimeoutError:
        pass

    _last_dream_at = 0.0
    while not _shutdown_event.is_set():
        now = time.time()
        cooldown_elapsed = (now - _last_dream_at) >= DREAM_COOLDOWN
        idle_trigger     = not _session_store.peek_all_snapshots() and cooldown_elapsed
        force_trigger    = (now - _last_dream_at) >= DREAM_MAX_INTERVAL
        if idle_trigger or force_trigger:
            if force_trigger and _session_store.peek_all_snapshots():
                print("[Dream] Force trigger — system has been busy, running dream during active session")
            idle_mins = (now - _last_dream_at) / 60 if _last_dream_at > 0 else 0
            print(f"[Dream] Starting consolidation cycle (idle={idle_mins:.1f}min, force={force_trigger})")
            await _brain_orchestrator.dream()
            # Stranger TTL cleanup — Wave 3 Item 15: rebuild_faiss_async keeps the index
            # swap off the critical path. recognize() continues on the OLD index while
            # the new one builds in a worker thread; no conversation latency spike.
            loop = asyncio.get_event_loop()
            pruned_ids = await db.prune_old_strangers_async(loop)
            if pruned_ids:
                _brain_orchestrator.prune_brain_data(pruned_ids)
                print(f"[Dream] Strangers pruned: {len(pruned_ids)}")
            # Voice-profile hygiene: strangers whose voice never matured become
            # false-positive sources; evict the in-memory cache FIRST so concurrent
            # voice_mod.identify() calls can't keep matching against the stale mean,
            # then delete the rows from SQLite. Finding J — ordering matters even
            # for microsecond windows.
            stale_ids = db.find_stale_stranger_voice_ids(STRANGER_VOICE_TTL_DAYS)
            if stale_ids:
                for _pid in stale_ids:
                    _voice_gallery.pop(_pid, None)
                    _voice_gallery_sizes.pop(_pid, None)
                # Pass the pre-computed ids so prune doesn't re-run the SELECT.
                voice_pruned_ids = db.prune_stale_stranger_voice(
                    STRANGER_VOICE_TTL_DAYS, ids=stale_ids,
                )
                print(f"[Dream] Stale stranger voice rows pruned: {len(voice_pruned_ids)}")
            # Obs 1 (2026-04-20): opportunistic voice-gallery reconciliation.
            # Defense-in-depth for out-of-process deletes (dashboard, CLI) that clear
            # ``voice_embeddings`` rows but can't invalidate the pipeline's in-memory
            # cache. Dream runs during idle windows so a full scan is effectively
            # free. Divergence → reload embeddings for the affected pids too, so
            # voice_mod.identify() can't keep matching against a vanished mean.
            _fresh_sizes = db.load_voice_profile_sizes()
            _divergent = [
                _pid for _pid in set(_voice_gallery_sizes) | set(_fresh_sizes)
                if _voice_gallery_sizes.get(_pid) != _fresh_sizes.get(_pid)
            ]
            if _divergent:
                print(f"[Dream] Voice gallery cache reconciled: {len(_divergent)} pid(s) out of sync")
                _voice_gallery_sizes.clear()
                _voice_gallery_sizes.update(_fresh_sizes)
                for _pid in _divergent:
                    _prof = db.load_voice_profile_for(_pid)
                    if _prof is None:
                        _voice_gallery.pop(_pid, None)
                    else:
                        _voice_gallery[_pid] = _prof
            # Silent observations retention (prune_silent_observations() is implemented in db.py
            # but was never called — enforce SILENT_OBS_RETENTION_DAYS from config)
            db.prune_silent_observations()
            if config.DAILY_BACKUP_ENABLED:
                try:
                    from core.backup import run_daily_backup_pass
                    _loop = asyncio.get_event_loop()
                    _backup_result = await _loop.run_in_executor(
                        None,
                        lambda: run_daily_backup_pass(
                            [str(config.DB_PATH), str(config.BRAIN_DB_PATH)],
                            snapshot_dir=config.SNAPSHOT_DIR,
                            retention_days=config.SNAPSHOT_RETENTION_DAYS,
                        )
                    )
                    if _backup_result["snapshots_created"]:
                        print(f"[Backup] {len(_backup_result['snapshots_created'])} snapshot(s) created, "
                              f"{len(_backup_result['pruned'])} old pruned")
                    if _backup_result["errors"]:
                        print(f"[Backup] errors: {_backup_result['errors']}")
                except Exception as _e:
                    print(f"[Backup] pass failed: {_e!r}")
            # Wave 6 Item 22: hard-delete old invalidated knowledge.
            if config.KNOWLEDGE_HARD_DELETE_ENABLED:
                try:
                    await loop.run_in_executor(
                        None,
                        _brain_orchestrator.brain_db.hard_delete_old_invalidated_knowledge,
                    )
                except Exception as _e:
                    print(f"[Dream] hard-delete prune failed: {_e!r}")
            # Wave 6 Item 21: archive old conversation_log turns
            if config.CONVERSATION_ARCHIVE_ENABLED:
                try:
                    n_archived = await loop.run_in_executor(
                        None,
                        db.archive_old_conversation_log,
                    )
                    if n_archived:
                        print(f"[Dream] Conversation archive: {n_archived} turn(s) moved to archive DB")
                except Exception as _e:
                    print(f"[Dream] conversation archive failed: {_e!r}")
            if config.WAL_CHECKPOINT_ENABLED:
                try:
                    db.checkpoint_wal()
                    _brain_orchestrator.brain_db.checkpoint_wal()
                    import core.classifier_graph as _cg_mod
                    _cg_mod.checkpoint_wal_singleton()
                    print("[Dream] WAL checkpoint complete (faces.db, brain.db, classifier.db)")
                except Exception as _wal_e:
                    print(f"[Dream] WAL checkpoint error: {_wal_e!r}")
            _last_dream_at = time.time()
            _last_dream_run_at = time.time()
        # Smart sleep: wait out remaining cooldown to avoid 60× useless wakeups per hour.
        # Falls back to 60s when cooldown is expired but no idle window yet.
        remaining = max(0.0, _last_dream_at + DREAM_COOLDOWN - time.time())
        sleep_secs = remaining if remaining > 60.0 else 60.0
        try:
            await asyncio.wait_for(_shutdown_event.wait(), timeout=sleep_secs)
            return
        except asyncio.TimeoutError:
            pass


async def _emit_health(loop: asyncio.AbstractEventLoop) -> None:
    """Gather health + disk snapshots in executor and print summary lines."""
    from core.config import HEALTH_LOG_ENABLED, DISK_MONITOR_ENABLED
    from core.health import gather_health_snapshot, format_health_line, format_health_alerts
    from core.disk_monitor import gather_disk_snapshot, format_disk_line, check_disk_thresholds

    # Health snapshot
    if HEALTH_LOG_ENABLED:
        try:
            snapshot = await loop.run_in_executor(
                None,
                lambda: gather_health_snapshot(
                    db=_face_db_ref,
                    brain_orchestrator=_brain_orchestrator,
                    active_sessions=_session_store.peek_all_snapshots(),
                    cloud_state=_cloud_state,
                    last_dream_run_at=_last_dream_run_at,
                ),
            )
            print(format_health_line(snapshot))
            for alert_line in format_health_alerts(snapshot, _brain_orchestrator):
                print(alert_line)
        except Exception as _e:
            print(f"[Health] emit failed: {_e!r}")

    # Disk snapshot
    if DISK_MONITOR_ENABLED:
        try:
            disk_snap = await loop.run_in_executor(None, gather_disk_snapshot)
            print(format_disk_line(disk_snap))
            check_disk_thresholds(disk_snap, _brain_orchestrator)
        except Exception as _e:
            print(f"[Disk] emit failed: {_e!r}")


async def _health_log_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Periodic health + disk log. First emission fires immediately at boot."""
    from core.config import HEALTH_LOG_INTERVAL_SECS
    await _emit_health(loop)
    while True:
        try:
            await asyncio.wait_for(_shutdown_event.wait(), timeout=HEALTH_LOG_INTERVAL_SECS)
            return
        except asyncio.TimeoutError:
            pass
        await _emit_health(loop)


def _detect_yes_no(text: str) -> str:
    """Returns 'yes', 'no', or 'unclear' from a short spoken response."""
    t = text.lower()
    if any(w in t for w in ("yes", "yeah", "yep", "yup", "sure", "absolutely",
                             "of course", "definitely", "correct", "right", "true",
                             "i am", "that's me", "thats me")):
        return "yes"
    if any(w in t for w in ("no", "nope", "nah", "never", "not", "negative", "i'm not")):
        return "no"
    return "unclear"


async def first_boot_flow(camera: Camera, detector: FaceDetector,
                           embedder: FaceEmbedder, db: FaceDB):
    """
    Runs when the DB is completely empty and a face is first detected.
    Asks if this is the owner; on yes → enroll with custom dialogue;
    on no or unclear → graceful shutdown.
    """
    _set_state(PipelineState.SPEAKING)
    await speak("Hey there... are you my best friend?")

    _set_state(PipelineState.LISTENING)
    response_text, _, _ = await listen_and_transcribe()
    verdict = _detect_yes_no(response_text) if response_text else "unclear"

    if verdict != "yes":
        await speak("Alright. I'll wait for my best friend then. Goodbye for now.")
        print("[Pipeline] First boot: not the owner — shutting down.")
        _shutdown_event.set()
        return

    await speak("Wow! What's your name?")
    _set_state(PipelineState.LISTENING)
    name_text, _, _ = await listen_and_transcribe()
    cleaned = name_text.strip() if name_text else None

    if not cleaned:
        # Ask once more before giving up
        await speak("I didn't catch that — could you say just your name?")
        _set_state(PipelineState.LISTENING)
        name_text, _, _ = await listen_and_transcribe()
        cleaned = name_text.strip() if name_text else None

    if not cleaned:
        await speak("No worries. Come back when you're ready and we'll try again.")
        return

    cleaned = cleaned.strip()[:50]
    display_name, safe_id = sanitize_name(cleaned)

    _set_state(PipelineState.ENROLLING, display_name)
    await speak(f"Wait, let me see you clearly, {display_name}... I want to remember you from now on.")
    person_id  = f"{safe_id}_{uuid.uuid4().hex[:6]}"
    frames     = await camera.capture_frames_async(n=20, interval=0.3, stop_event=_shutdown_event)
    pending_embeddings = []
    photo_frame = None
    spoof_blocked = False

    for frame in frames:
        dets = detector.detect(frame)
        if not dets:
            continue
        det = max(dets, key=lambda d: (d.bbox[2]-d.bbox[0]) * (d.bbox[3]-d.bbox[1]))
        x1, y1, x2, y2 = det.bbox
        face_crop = frame[y1:y2, x1:x2]
        if face_crop.size == 0:
            continue
        if face_quality_score(face_crop) < FACE_QUALITY_ENROLLMENT:
            continue
        if det.landmarks is not None:
            yaw = estimate_yaw_from_landmarks(det.landmarks, det.bbox)
            if abs(yaw) > 60.0:
                continue
        if not verify_live(frame, det.bbox, _anti_spoof_checker):
            print("[Pipeline] Anti-spoof: first_boot enrollment frame rejected — possible photo attack")
            spoof_blocked = True
            continue
        embedding = embedder.embed(face_crop)
        pending_embeddings.append(embedding)
        if photo_frame is None:
            photo_frame = frame

    if pending_embeddings:
        photo_path = None
        if photo_frame is not None:
            photo_path = str(FACES_DIR / f"{person_id}.jpg")
            cv2.imwrite(photo_path, photo_frame)
        db.add_person(person_id, display_name, photo_path, person_type='best_friend')
        for emb in pending_embeddings:
            db.add_embedding(person_id, emb, "enrollment")
        await speak(
            f"Got you, {display_name}! From now on, you're my best friend. "
            f"I'll never forget you."
        )
        print(f"[Pipeline] Best friend enrolled: {display_name} ({person_id}) with {len(pending_embeddings)} embeddings")
    else:
        if spoof_blocked:
            await speak("I couldn't verify that you're a real person. Please try again without any photos or screens.")
        else:
            await speak("I couldn't see you clearly. Please try again in better lighting.")


async def enrollment_flow(name: str, camera: Camera, detector: FaceDetector,
                           embedder: FaceEmbedder, db: FaceDB,
                           person_type: str = 'known'):
    """
    Voice enrollment — capture face for 5 seconds, save embeddings.
    Called from dashboard (best friend) or auto-enrollment paths.
    """
    # H7: sanitize before building filesystem path
    display_name, safe_id = sanitize_name(name)
    name = display_name  # keep display name for TTS

    await speak(f"Hi {name}! Please look at the camera and stay still for 5 seconds.", language=_detected_lang)

    person_id  = f"{safe_id}_{uuid.uuid4().hex[:6]}"
    frames = await camera.capture_frames_async(n=20, interval=0.3, stop_event=_shutdown_event)
    pending_embeddings = []
    photo_frame = None
    spoof_blocked = False

    for frame in frames:
        detections = detector.detect(frame)
        if not detections:
            continue
        # Take the largest face in frame
        det = max(detections, key=lambda d: (d.bbox[2]-d.bbox[0]) * (d.bbox[3]-d.bbox[1]))
        x1, y1, x2, y2 = det.bbox
        face_crop = frame[y1:y2, x1:x2]
        if face_crop.size == 0:
            continue

        # V1: skip insufficient-quality crops (enrollment requires clean frames)
        if face_quality_score(face_crop) < FACE_QUALITY_ENROLLMENT:
            continue

        # V2: skip side-on faces (unreliable embeddings)
        if det.landmarks is not None:
            yaw = estimate_yaw_from_landmarks(det.landmarks, det.bbox)
            if abs(yaw) > 60.0:
                continue

        # Anti-spoofing: reject photo/screen attacks during enrollment
        if not verify_live(frame, det.bbox, _anti_spoof_checker):
            print(f"[Pipeline] Anti-spoof: enrollment frame rejected for '{name}' — possible photo attack")
            spoof_blocked = True
            continue

        embedding = embedder.embed(face_crop)
        pending_embeddings.append(embedding)
        if photo_frame is None:
            photo_frame = frame  # save first good frame for photo

    if pending_embeddings:
        photo_path = None
        if photo_frame is not None:
            photo_path = str(FACES_DIR / f"{person_id}.jpg")
            cv2.imwrite(photo_path, photo_frame)

        # M11: add_person before add_embedding to satisfy FK constraint
        db.add_person(person_id, name, photo_path, person_type=person_type)
        for emb in pending_embeddings:
            db.add_embedding(person_id, emb, "enrollment")

        await speak(f"Got it! I'll remember you as {name}. Nice to meet you!", language=_detected_lang)
        print(f"[Pipeline] Enrolled {name} ({person_id}) with {len(pending_embeddings)} embeddings")
    else:
        if spoof_blocked:
            await speak("I couldn't verify that you're a real person. Please try again without any photos or screens.", language=_detected_lang)
        else:
            await speak("I couldn't get a clear view of your face. Please try again in better lighting.", language=_detected_lang)


async def _execute_tool(
    name: str,
    args: dict,
    person_id: str,
    person_name: str,
    db: "FaceDB",
    user_text: str = "",
    intent_sidecar: "dict | None" = None,
) -> str | None:
    """
    Execute a single tool call from the LLM.

    ``intent_sidecar`` (VISION_ROADMAP P1.7a): the shadow classifier's sidecar
    dict from ``_classify_intent`` if it ran this turn, or ``None`` when the
    classifier wasn't consulted (tool not in TOOL_INTENT_MAP, shadow mode
    disabled, timeout, parse failure). Gated-tool handlers consult the sidecar
    first via ``_intent_allows``; when the sidecar is ``None``,
    ``INTENT_FALLBACK_TO_REGEX=True`` routes through the legacy regex gate
    (safety net until ≥30 real_observed samples validate the classifier
    enough to flip fallback to False at P1.17). All gate decisions are
    persisted to ``brain.db.intent_divergences`` for Phase 5 drift detection.

    Return status classifies the result:
      "shutdown"      — shutdown was requested (caller triggers shutdown).
      "handled"       — tool ran AND changed state; caller may emit a canonical ack.
      "handled_noop"  — tool ran but was a no-op (state already matched); caller
                        must NOT emit a canonical ack to avoid the feedback loop
                        observed in Bug Q (LLM hears "Got it, I'll go by Kara" on
                        every redundant call and re-issues it next turn).
      "unknown"       — Bug P (2026-04-21): the LLM emitted a tool name that
                        isn't in our registry (typically echoing a user word,
                        e.g. ``Buddy({})``). Model artifact, NOT a security
                        violation. Caller treats it as "no tool effect".
      "rejected"      — Session 71 (Bugs S / T, 2026-04-21): server-side
                        user-text gate rejected the call. The LLM wanted to act
                        but the user's actual utterance didn't support it
                        (e.g. update_system_name('Kara') when user asked "do
                        you know Detroit?"). Distinct from "unknown" (tool
                        doesn't exist) and None (privilege denied / internal
                        error). Both "rejected" and "unknown" route through the
                        same Ollama-text retry path in conversation_turn.
      None            — blocked by privilege gate, repeat guard, or internal error.
    """
    global _active_system_name, _detected_lang

    # ── Layer 0: Unknown-tool filter (Bug P, 2026-04-21 live run) ────────────
    # TOOL_PRIVILEGES is the canonical registry — a startup assertion ties every
    # `brain.TOOLS` entry to a row here, so "not in table" means the LLM invented
    # a tool name (hallucination from prompt echo). These are model artifacts,
    # not security violations, and must NOT hit the BLOCKED logging path — the
    # user only sees the downstream "Sorry, I missed that" filler, which is worse
    # UX than silently discarding the phantom call and letting streamed text
    # (or an Ollama retry) flow through.
    if name not in TOOL_PRIVILEGES:
        print(f"[Pipeline] Tool: {name!r} — unknown tool, discarded (LLM hallucination)")
        return "unknown"

    # ── Layer 3: Tool repeat guard ────────────────────────────────────────────
    # Abort if the same (tool, args) fires TOOL_REPEAT_MAX_CONSECUTIVE times in
    # a row with no user message in between — prevents infinite loop scenarios.
    import hashlib as _hl, json as _j
    _args_hash  = _hl.md5(_j.dumps(args, sort_keys=True, default=str).encode()).hexdigest()[:8]
    _repeat_key = f"{name}:{_args_hash}"
    _session_snap_rg = _session_store.peek_snapshot(person_id)
    if _session_snap_rg is not None and _session_snap_rg.tool_repeat_last == _repeat_key:
        _new_count = _session_snap_rg.tool_repeat_count + 1
        if _new_count >= TOOL_REPEAT_MAX_CONSECUTIVE:
            print(
                f"[Pipeline] WARN: Tool repeat guard — '{name}' fired {_new_count}x "
                f"consecutively with same args. Aborting to prevent loop."
            )
            try:
                _loop = asyncio.get_running_loop()
                _loop.create_task(_session_store.update_tool_repeat(person_id, None, 0))
            except RuntimeError:
                pass  # OPTIONAL: no running loop in test/early-boot context
            return None
        try:
            _loop = asyncio.get_running_loop()
            _loop.create_task(_session_store.update_tool_repeat(person_id, _repeat_key, _new_count))
        except RuntimeError:
            pass  # OPTIONAL: no running loop in test/early-boot context
    else:
        if _session_snap_rg is not None:
            try:
                _loop = asyncio.get_running_loop()
                _loop.create_task(_session_store.update_tool_repeat(person_id, _repeat_key, 1))
            except RuntimeError:
                pass  # OPTIONAL: no running loop in test/early-boot context

    # ── Privilege gate ────────────────────────────────────────────────────────
    # Table-driven (see TOOL_PRIVILEGES in core/config.py). No hardcoded
    # `if name == "shutdown" ...` checks — privilege policy is data, changing
    # it is a config edit with no code change here or in brain.py.
    # Fallback is "stranger" (most restricted) if the session dict is somehow
    # missing person_type — fail-safe rather than fail-open.
    _exec_snap   = _session_store.peek_snapshot(person_id)
    _caller_type = _exec_snap.person_type if _exec_snap is not None else "stranger"
    if not _tool_allowed(name, _caller_type):
        allowed = TOOL_PRIVILEGES.get(name, frozenset())
        print(
            f"[Pipeline] Tool: {name!r} BLOCKED for {person_name} "
            f"(person_type={_caller_type!r}) — allowed: {sorted(allowed) or '<not in table — always blocked>'}"
        )
        return None

    if name == "update_person_name":
        new_name, _ = sanitize_name(args.get("name") or "")
        _sess_type  = _exec_snap.person_type if _exec_snap is not None else "known"

        # Session 101 Bug F.2 — enrollment-mishear escape hatch with
        # widened intent set. Runs BEFORE the normal `_intent_allows` gate
        # because natural correction phrasings ("No, it's not Javan, it's
        # Jagan") classify as `deny_identity` (linguistically correct —
        # denial + correction) rather than `assign_own_name`. The classic
        # `_intent_allows` check on `update_person_name` only accepts
        # `assign_own_name`, so the original Session 100 Bug F escape
        # hatch (which runs AFTER the gate) never activated for the exact
        # phrasing users actually produce. 2026-04-23 re-canary: rename
        # blocked → person_id stays at STT-mangled "Jawan" → all
        # downstream facts stored under wrong entity, PromptPrefAgent
        # encoded "use 'Jawan' as preferred form," dashboard frozen.
        #
        # Widening: during the fresh-enrollment window (face only, no
        # voice corroboration — same gate as Session 100's
        # _is_enrollment_mishear_candidate), accept 3 intents for
        # update_person_name: assign_own_name, deny_identity,
        # confirm_identity. Each MUST still satisfy the full grounding
        # contract (extracted_value present AND appears NFKC-casefolded
        # in user_text) so ungrounded hallucinations can't sneak through.
        # Mature-session security (mid-session rename → dispute) is
        # PRESERVED because `_is_enrollment_mishear_candidate` fails on
        # any session past the grace window or with voice samples.
        if (
            new_name
            and new_name.lower() != person_name.lower()
            and _sess_type in ("known", "best_friend")
            and _is_enrollment_mishear_candidate(db, person_id, _exec_snap)
            and intent_sidecar is not None
        ):
            from core.config import INTENT_CONFIDENCE_MIN as _ICM
            _mishear_intents = frozenset((
                "assign_own_name", "deny_identity", "confirm_identity",
            ))
            _mi_intent = intent_sidecar.get("turn_intent") or ""
            _mi_conf   = float(intent_sidecar.get("confidence") or 0.0)
            _mi_val    = intent_sidecar.get("extracted_value")
            _mi_val_s  = str(_mi_val).strip() if _mi_val else ""
            _grounded  = bool(_mi_val_s) and (
                _nfkc_lower(_mi_val_s) in _nfkc_lower(user_text or "")
            )
            if (
                _mi_intent in _mishear_intents
                and _mi_conf >= _ICM
                and _grounded
            ):
                if db:
                    db.update_person_name(person_id, new_name)
                    _invalidate_bf_cache()  # Session 115 Fix 2 — rename may target bf
                _old_pat_mh2 = re.compile(
                    r'\b' + re.escape(person_name) + r'\b', re.IGNORECASE,
                )
                for _msg_mh in _conversation.get(person_id, []):
                    _msg_mh["content"] = _old_pat_mh2.sub(
                        new_name, _msg_mh["content"],
                    )
                if _session_store.peek_snapshot(person_id) is not None:
                    try:
                        _loop = asyncio.get_running_loop()
                        _loop.create_task(_session_store.rename(person_id, new_name))
                    except RuntimeError:
                        pass  # OPTIONAL: no running loop in test/early-boot context
                # Session 102 Bug F.3: update the in-frame cache
                # immediately so the SCENE block and [Vision] logs don't
                # keep rendering the old name until the next background
                # scan lands (~1s). Belt-and-braces with the background-
                # scan refresh.
                if person_id in _persons_in_frame:
                    _persons_in_frame[person_id]["name"] = new_name
                if _brain_orchestrator:
                    _brain_orchestrator.on_identity_confirmed(
                        person_id, person_name, new_name,
                    )
                print(
                    f"[Pipeline] Enrollment-mishear rename (Bug F.2): "
                    f"{person_name!r} → {new_name!r} "
                    f"(intent={_mi_intent}, person_type={_sess_type!r}, "
                    f"conf={_mi_conf:.2f})"
                )
                _log_intent_divergence(
                    tool_name="update_person_name",
                    sidecar=intent_sidecar,
                    gate_decision=f"allow_mishear_{_mi_intent}",
                    user_text=user_text, person_id=person_id,
                )
                return "handled"

        # VISION_ROADMAP P1.7a (Session 85): classifier-first gate, regex
        # fallback. Order: (1) if _classify_intent fired this turn, use
        # _intent_allows — dual-gate (intent match + confidence floor +
        # grounding + arg cross-check) is the new authority. (2) If classifier
        # was unavailable AND INTENT_FALLBACK_TO_REGEX=True, fall through to
        # the legacy regex gate (Session 73's capture-group rule). (3) If
        # classifier was unavailable AND fallback is disabled (P1.17+), allow
        # with a warning — silently dropping mutation tools on classifier
        # failure would be worse UX than a logged wide-open path. All three
        # outcomes land a row in brain.db.intent_divergences for Phase 5.
        if new_name:
            from core.config import INTENT_FALLBACK_TO_REGEX
            _gate_allowed = True
            _gate_reason  = "no gate evaluated"
            if intent_sidecar is not None:
                _allowed, _reason = _intent_allows(
                    tool_name="update_person_name",
                    turn_intent=intent_sidecar.get("turn_intent") or "",
                    confidence=float(intent_sidecar.get("confidence") or 0.0),
                    extracted_value=intent_sidecar.get("extracted_value"),
                    user_text=user_text,
                    tool_args=args,
                )
                if not _allowed:
                    _last_msg_preview = ((user_text or "").strip())[:80]
                    print(
                        f"[Pipeline] Tool: update_person_name REJECTED (intent) "
                        f"— {_reason}; user_text: '{_last_msg_preview}'"
                    )
                    _log_intent_divergence(
                        tool_name="update_person_name",
                        sidecar=intent_sidecar,
                        gate_decision=f"reject: {_reason}",
                        user_text=user_text, person_id=person_id,
                    )
                    return "rejected"
                print(
                    f"[Pipeline] Tool: update_person_name allowed by intent "
                    f"gate — {_reason}"
                )
                _log_intent_divergence(
                    tool_name="update_person_name",
                    sidecar=intent_sidecar,
                    gate_decision="allow",
                    user_text=user_text, person_id=person_id,
                )
            elif INTENT_FALLBACK_TO_REGEX:
                if not _user_text_gate_passes(
                    user_text, new_name, PERSON_NAME_ASSIGN_PATTERNS
                ):
                    _last_msg_preview = ((user_text or "").strip())[:80]
                    print(
                        f"[Pipeline] Tool: update_person_name REJECTED "
                        f"(regex fallback) — user did not self-identify as "
                        f"'{new_name}' in: '{_last_msg_preview}'"
                    )
                    _log_intent_divergence(
                        tool_name="update_person_name",
                        sidecar=None,
                        gate_decision="regex_fallback_reject",
                        user_text=user_text, person_id=person_id,
                    )
                    return "rejected"
                _log_intent_divergence(
                    tool_name="update_person_name",
                    sidecar=None,
                    gate_decision="regex_fallback_allow",
                    user_text=user_text, person_id=person_id,
                )
            else:
                # Both classifier unavailable AND fallback disabled — this
                # state only happens after P1.17 flips the fallback off AND
                # the classifier genuinely failed (timeout / parse). Silent
                # drop would feel broken; log loudly and allow so legitimate
                # mutation tools aren't blackholed on infrastructure blips.
                print(
                    f"[Pipeline] WARN: update_person_name — classifier "
                    f"unavailable AND fallback disabled; allowing with warning"
                )
                _log_intent_divergence(
                    tool_name="update_person_name",
                    sidecar=None,
                    gate_decision="both_unavailable_allow_with_warning",
                    user_text=user_text, person_id=person_id,
                )

        if new_name and new_name.lower() != person_name.lower():
            # Session 100 Bug F — enrollment-mishear escape hatch. When a
            # fresh-enrollment session (face only, no voice corroboration) sees
            # a grounded rename claim, allow it through the stranger-promotion
            # chain instead of flipping to disputed. 2026-04-23 canary: STT
            # mishear at first boot wrote "Gevan" instead of "Jagan"; the
            # classic dispute-flip locked the wrong name in place for the
            # whole session + cascaded into all downstream facts. The classifier
            # gate above has already validated the rename is grounded
            # (assign_own_name intent + user_text match); this branch only
            # decides the ROUTING between dispute-flip and promotion-rename.
            if (
                _sess_type in ("known", "best_friend")
                and _is_enrollment_mishear_candidate(db, person_id, _exec_snap)
            ):
                if db:
                    db.update_person_name(person_id, new_name)
                    _invalidate_bf_cache()  # Session 115 Fix 2 — rename may target bf
                old_pat_mh = re.compile(r'\b' + re.escape(person_name) + r'\b', re.IGNORECASE)
                for msg in _conversation.get(person_id, []):
                    msg["content"] = old_pat_mh.sub(new_name, msg["content"])
                if _session_store.peek_snapshot(person_id) is not None:
                    try:
                        _loop = asyncio.get_running_loop()
                        _loop.create_task(_session_store.rename(person_id, new_name))
                    except RuntimeError:
                        pass  # OPTIONAL: no running loop in test/early-boot context
                # Session 102 Bug F.3: refresh in-frame cache immediately.
                if person_id in _persons_in_frame:
                    _persons_in_frame[person_id]["name"] = new_name
                # Migrate knowledge rows + rebuild graph. NOTE: person_type
                # stays as-is (best_friend keeps best_friend; known keeps
                # known) — this is a NAME correction, not a privilege change.
                if _brain_orchestrator:
                    _brain_orchestrator.on_identity_confirmed(person_id, person_name, new_name)
                print(
                    f"[Pipeline] Enrollment-mishear rename: {person_name!r} → "
                    f"{new_name!r} (person_type={_sess_type!r} preserved; "
                    f"session fresh + no voice corroboration)"
                )
                return "handled"

            # A rename on an already-KNOWN session is structurally suspicious —
            # the sensor may have misidentified the speaker. Do NOT rename the DB
            # row (that would corrupt the known person's identity). Flip to
            # "disputed": extraction pauses, next turn's SENSOR block surfaces
            # the mismatch, and the user can clarify before anything is persisted.
            # Any enrolled-identity session ("known" OR "best_friend") gets the
            # same dispute-flip treatment — a rename here is structurally suspicious
            # (sensor may be poisoned) and we MUST NOT touch the DB, since the pid
            # belongs to a real enrolled person whose identity the system has to
            # protect. best_friend is especially critical because they're the system
            # owner: a mis-rename would transfer their privileges to the attacker.
            if _sess_type in ("known", "best_friend"):
                if _session_store.peek_snapshot(person_id) is not None:
                    _dispute_ts = time.time()
                    try:
                        _loop = asyncio.get_running_loop()
                        _loop.create_task(_session_store.transition_to_disputed(
                            person_id, new_name,
                            f"speaker claims name '{new_name}', sensor says '{person_name}'",
                            now=_dispute_ts,
                        ))
                        _loop.create_task(_session_store.set_cached_prefix(person_id, None))
                    except RuntimeError:
                        pass  # OPTIONAL: no running loop in test/early-boot context
                if _brain_orchestrator:
                    _brain_orchestrator.mark_disputed(person_id)
                print(
                    f"[Pipeline] Tool: identity DISPUTED — speaker claims '{new_name}', "
                    f"sensor said '{person_name}' (session was {_sess_type!r}). "
                    f"Extraction paused for this session."
                )
                return "handled"

            # Finding G — CRITICAL: a rename on a DISPUTED session must NOT touch
            # the DB. The disputed pid belongs to the sensor-matched (real) person
            # whom vision wrongly matched; renaming their row would permanently
            # overwrite their identity. Block the rename and keep the dispute
            # active — it will force-close via DISPUTE_MAX_DURATION, and the user
            # can audit+repair the poisoned gallery (audit_person.py / repair_gallery.py)
            # or factory-reset if the drift is severe.
            if _is_disputed(person_id):
                # N3 — count persistent blocks and surface a watchdog alert once the
                # count crosses DISPUTE_RENAME_BLOCK_THRESHOLD. `disputed_block_alerted`
                # prevents re-firing within the same session; both fields evaporate
                # when _close_session pops the session dict.
                _block_count = (_exec_snap.disputed_block_count if _exec_snap is not None else 0) + 1
                try:
                    _loop = asyncio.get_running_loop()
                    _loop.create_task(_session_store.increment_block_count(person_id))
                except RuntimeError:
                    pass  # OPTIONAL: no running loop in test/early-boot context
                print(
                    f"[Pipeline] Tool: disputed-session rename to '{new_name}' BLOCKED "
                    f"(block #{_block_count}) — pid '{person_id}' belongs to '{person_name}' "
                    f"(sensor-matched), not the current speaker. Skipping DB rename; "
                    f"dispute stays active until timeout or session end."
                )
                if (_block_count >= DISPUTE_RENAME_BLOCK_THRESHOLD
                        and not (_exec_snap.disputed_block_alerted if _exec_snap is not None else False)
                        and _brain_orchestrator):
                    try:
                        _loop = asyncio.get_running_loop()
                        _loop.create_task(_session_store.mark_block_alerted(person_id))
                    except RuntimeError:
                        pass  # OPTIONAL: no running loop in test/early-boot context
                    # prior_person_type tells us whether this is a "best_friend"
                    # impersonation (critical) or a general "known" one (warning).
                    _victim_type = (_exec_snap.prior_person_type if _exec_snap is not None else None) or "stranger"
                    _brain_orchestrator.report_dispute_rename_burst(
                        victim_pid=person_id,
                        victim_name=person_name,
                        victim_person_type=_victim_type,
                        claimed_name=new_name,
                        block_count=_block_count,
                        dispute_started_at=_exec_snap.dispute_set_at if _exec_snap is not None else None,
                    )
                return "handled"

            # Stranger session: legitimate rename path (the pid was minted for this
            # stranger, so renaming it is the intended promotion to a real name).
            if db:
                db.update_person_name(person_id, new_name)
                _invalidate_bf_cache()  # Session 115 Fix 2 — defensive (stranger rename shouldn't touch bf, but cheap)
            # Retroactively fix old name in in-memory history
            old_pat = re.compile(r'\b' + re.escape(person_name) + r'\b', re.IGNORECASE)
            for msg in _conversation.get(person_id, []):
                msg["content"] = old_pat.sub(new_name, msg["content"])
            try:
                _loop = asyncio.get_running_loop()
                _loop.create_task(_session_store.rename(person_id, new_name))
            except RuntimeError:
                pass  # OPTIONAL: no running loop in test/early-boot context
            # Session 102 Bug F.3: refresh in-frame cache immediately.
            if person_id in _persons_in_frame:
                _persons_in_frame[person_id]["name"] = new_name
            # Stranger identity confirmed via LLM tool: run full promotion chain
            if _sess_type == "stranger":
                if db:
                    db.update_person_type(person_id, "known")
                if _brain_orchestrator:
                    _brain_orchestrator.on_identity_confirmed(person_id, person_name, new_name)
                try:
                    _loop = asyncio.get_running_loop()
                    _loop.create_task(_session_store.promote_type(person_id, "known"))
                    _loop.create_task(_session_store.set_cached_prefix(person_id, None))
                    _loop.create_task(_session_store.set_waiting_for_name(person_id, False))
                except RuntimeError:
                    pass  # OPTIONAL: no running loop in test/early-boot context
            print(f"[Pipeline] Tool: person name '{person_name}' → '{new_name}'")
            return "handled"
        # Same name — no-op. Bug Q (2026-04-21): return "handled_noop" so the
        # caller does NOT emit the canonical "Got it, {name}." ack. Writing
        # that ack to history when nothing actually changed was the feedback
        # loop that had the LLM re-issue the same tool call across turns.
        print(f"[Pipeline] Tool: update_person_name no-op (already '{person_name}')")
        return "handled_noop"

    elif name == "report_identity_mismatch":
        # Bug G3 (2026-04-22 live run): the second-biggest blast-radius tool
        # was the only Session 71+ side-effect tool without a user-text gate.
        # Jagan's legit multi-person scene question "who are you talking to?"
        # was interpreted as identity denial by the LLM → session flipped
        # DISPUTED → ~15 broken turns. Gate requires a denial-signal phrase.
        # Session 86 P1.7b: classifier-first; regex fallback on classifier
        # unavail. Same 3-branch pattern as update_person_name (P1.7a canary).
        from core.config import INTENT_FALLBACK_TO_REGEX
        if intent_sidecar is not None:
            _allowed, _reason = _intent_allows(
                tool_name="report_identity_mismatch",
                turn_intent=intent_sidecar.get("turn_intent") or "",
                confidence=float(intent_sidecar.get("confidence") or 0.0),
                extracted_value=intent_sidecar.get("extracted_value"),
                user_text=user_text,
                tool_args=args,
            )
            if not _allowed:
                _last_msg_preview = ((user_text or "").strip())[:80]
                print(
                    f"[Pipeline] Tool: report_identity_mismatch REJECTED (intent) "
                    f"— {_reason}; user_text: '{_last_msg_preview}'"
                )
                _log_intent_divergence(
                    tool_name="report_identity_mismatch",
                    sidecar=intent_sidecar,
                    gate_decision=f"reject: {_reason}",
                    user_text=user_text, person_id=person_id,
                )
                return "rejected"
            print(
                f"[Pipeline] Tool: report_identity_mismatch allowed by intent "
                f"gate — {_reason}"
            )
            _log_intent_divergence(
                tool_name="report_identity_mismatch",
                sidecar=intent_sidecar,
                gate_decision="allow",
                user_text=user_text, person_id=person_id,
            )
        elif INTENT_FALLBACK_TO_REGEX:
            if not _user_text_gate_passes(user_text, None, IDENTITY_DENIAL_PATTERNS):
                _last_msg_preview = ((user_text or "").strip())[:80]
                print(
                    f"[Pipeline] Tool: report_identity_mismatch REJECTED "
                    f"(regex fallback) — user did not deny identity in: "
                    f"'{_last_msg_preview}'"
                )
                _log_intent_divergence(
                    tool_name="report_identity_mismatch",
                    sidecar=None,
                    gate_decision="regex_fallback_reject",
                    user_text=user_text, person_id=person_id,
                )
                return "rejected"
            _log_intent_divergence(
                tool_name="report_identity_mismatch",
                sidecar=None,
                gate_decision="regex_fallback_allow",
                user_text=user_text, person_id=person_id,
            )
        else:
            print(
                f"[Pipeline] WARN: report_identity_mismatch — classifier "
                f"unavailable AND fallback disabled; allowing with warning"
            )
            _log_intent_divergence(
                tool_name="report_identity_mismatch",
                sidecar=None,
                gate_decision="both_unavailable_allow_with_warning",
                user_text=user_text, person_id=person_id,
            )

        reason = (args.get("reason") or "").strip() or "identity mismatch reported"
        if _session_store.peek_snapshot(person_id) is not None:
            _dispute_ts_ridm = time.time()
            try:
                _loop = asyncio.get_running_loop()
                _loop.create_task(_session_store.transition_to_disputed(
                    person_id, None, reason, now=_dispute_ts_ridm,
                ))
                _loop.create_task(_session_store.set_cached_prefix(person_id, None))
            except RuntimeError:
                pass  # OPTIONAL: no running loop in test/early-boot context
        if _brain_orchestrator:
            _brain_orchestrator.mark_disputed(person_id)
        print(f"[Pipeline] Tool: identity DISPUTED for {person_name} — {reason}")
        return "handled"

    elif name == "update_system_name":
        new_name, _ = sanitize_name(args.get("name") or "")
        if not new_name or new_name.lower() in _INVALID_SYSTEM_NAMES:
            print(f"[Pipeline] Tool: update_system_name rejected invalid name '{new_name}'")
            return None

        # Bug G1 (2026-04-22 live run): Session 71's OR-gate accepted
        # "do you know the GAME called Detroit?" because 'Detroit' appeared in
        # the turn — and the system renamed itself to "Detroit". Session 73
        # tightened to capture-group regex; Session 86 P1.7b layers the
        # classifier gate on top (this is the fix for the 2026-04-22 Alexa
        # bug: "I want it to be changed to Alexa" rejected by regex 3× even
        # though classifier got it right at 0.95 every time).
        from core.config import INTENT_FALLBACK_TO_REGEX
        if intent_sidecar is not None:
            _allowed, _reason = _intent_allows(
                tool_name="update_system_name",
                turn_intent=intent_sidecar.get("turn_intent") or "",
                confidence=float(intent_sidecar.get("confidence") or 0.0),
                extracted_value=intent_sidecar.get("extracted_value"),
                user_text=user_text,
                tool_args=args,
            )
            if not _allowed:
                _last_msg_preview = ((user_text or "").strip())[:80]
                print(
                    f"[Pipeline] Tool: update_system_name REJECTED (intent) "
                    f"— {_reason}; user_text: '{_last_msg_preview}'"
                )
                _log_intent_divergence(
                    tool_name="update_system_name",
                    sidecar=intent_sidecar,
                    gate_decision=f"reject: {_reason}",
                    user_text=user_text, person_id=person_id,
                )
                return "rejected"
            print(
                f"[Pipeline] Tool: update_system_name allowed by intent gate "
                f"— {_reason}"
            )
            _log_intent_divergence(
                tool_name="update_system_name",
                sidecar=intent_sidecar,
                gate_decision="allow",
                user_text=user_text, person_id=person_id,
            )
        elif INTENT_FALLBACK_TO_REGEX:
            if not _user_text_gate_passes(user_text, new_name, SYSTEM_NAME_ASSIGN_PATTERNS):
                _last_msg_preview = ((user_text or "").strip())[:80]
                print(
                    f"[Pipeline] Tool: update_system_name REJECTED "
                    f"(regex fallback) — user did not assign '{new_name}' in: "
                    f"'{_last_msg_preview}'"
                )
                _log_intent_divergence(
                    tool_name="update_system_name",
                    sidecar=None,
                    gate_decision="regex_fallback_reject",
                    user_text=user_text, person_id=person_id,
                )
                return "rejected"
            _log_intent_divergence(
                tool_name="update_system_name",
                sidecar=None,
                gate_decision="regex_fallback_allow",
                user_text=user_text, person_id=person_id,
            )
        else:
            print(
                f"[Pipeline] WARN: update_system_name — classifier unavailable "
                f"AND fallback disabled; allowing with warning"
            )
            _log_intent_divergence(
                tool_name="update_system_name",
                sidecar=None,
                gate_decision="both_unavailable_allow_with_warning",
                user_text=user_text, person_id=person_id,
            )

        if new_name.lower() != _active_system_name.lower():
            _active_system_name = new_name
            # Invalidate prefix cache for ALL sessions — system_name is in Section 2
            try:
                _loop = asyncio.get_running_loop()
                for _snap_inv in _session_store.peek_all_snapshots():
                    _loop.create_task(_session_store.set_cached_prefix(_snap_inv.person_id, None))
            except RuntimeError:
                pass  # OPTIONAL
            if _brain_orchestrator:
                _brain_orchestrator.set_system_name(new_name)
            if db:
                db.set_system_identity(
                    "system_name", new_name,
                    set_by=person_id,
                    note=f"named by {person_name}",
                )
            print(f"[Pipeline] Tool: system name → '{new_name}'")
            return "handled"
        # Same name — no-op. Bug Q: no canonical ack, no history write.
        # The redundant "Got it, I'll go by Kara." on turns 15/17/19 in the
        # 2026-04-21 run was the direct feedback-loop driver.
        print(f"[Pipeline] Tool: update_system_name no-op (already '{_active_system_name}')")
        return "handled_noop"

    elif name == "shutdown":
        # Session 86 P1.7b site 4: classifier-first; 3-regex fallback (strict
        # phrases + lenient goodnight + question-about-shutdown exclusion)
        # kept intact as the safety net. Shutdown is the highest-blast-radius
        # mutation tool so BOTH gates must agree for a shutdown to fire in the
        # dual-gate phase. ``request_shutdown`` requires INTENT_SHUTDOWN_CONF_MIN
        # (0.80), strictly higher than the general 0.75 floor — wired via the
        # tool_name branch in _intent_allows.
        from core.config import INTENT_FALLBACK_TO_REGEX
        _last_msg = (user_text or "").lower()
        _SHUTDOWN_STRICT = (
            "shut down", "shutdown", "turn off", "go to sleep", "stop listening",
            "bye i'm done", "power off", "switch off",
        )
        _SHUTDOWN_LENIENT_RE = re.compile(
            r"^\s*(?:good\s?night|i'?m\s+done|i\s+am\s+done)\s*[!.?]*\s*$"
        )

        def _regex_says_shutdown(msg: str) -> bool:
            """Legacy 3-regex chain — strict phrases + lenient goodnight
            minus question-about-shutdown exclusion. Extracted so the
            fallback branch reads cleanly and the shared logic is in one
            place."""
            has_phrase = (
                any(re.search(r'\b' + re.escape(p) + r'\b', msg) for p in _SHUTDOWN_STRICT)
                or bool(_SHUTDOWN_LENIENT_RE.match(msg))
            )
            is_question = has_phrase and _SHUTDOWN_QUESTION_RE.search(msg)
            return bool(msg and has_phrase and not is_question)

        if intent_sidecar is not None:
            _allowed, _reason = _intent_allows(
                tool_name="shutdown",
                turn_intent=intent_sidecar.get("turn_intent") or "",
                confidence=float(intent_sidecar.get("confidence") or 0.0),
                extracted_value=intent_sidecar.get("extracted_value"),
                user_text=user_text,
                tool_args=args,
            )
            if not _allowed:
                print(
                    f"[Pipeline] Tool: shutdown REJECTED (intent) — {_reason}; "
                    f"user_text: '{_last_msg[:80]}'"
                )
                _log_intent_divergence(
                    tool_name="shutdown",
                    sidecar=intent_sidecar,
                    gate_decision=f"reject: {_reason}",
                    user_text=user_text, person_id=person_id,
                )
                return "rejected"
            print(f"[Pipeline] Tool: shutdown allowed by intent gate — {_reason}")
            _log_intent_divergence(
                tool_name="shutdown",
                sidecar=intent_sidecar,
                gate_decision="allow",
                user_text=user_text, person_id=person_id,
            )
        elif INTENT_FALLBACK_TO_REGEX:
            if not _regex_says_shutdown(_last_msg):
                print(
                    f"[Pipeline] Tool: shutdown REJECTED (regex fallback) — "
                    f"no explicit command in: '{_last_msg[:80]}'"
                )
                _log_intent_divergence(
                    tool_name="shutdown",
                    sidecar=None,
                    gate_decision="regex_fallback_reject",
                    user_text=user_text, person_id=person_id,
                )
                return "rejected"
            _log_intent_divergence(
                tool_name="shutdown",
                sidecar=None,
                gate_decision="regex_fallback_allow",
                user_text=user_text, person_id=person_id,
            )
        else:
            # Shutdown's both-unavailable policy diverges from the other
            # mutation tools: allow-with-warning would risk an unintended
            # system shutdown if the classifier blips. For the biggest-
            # blast-radius tool we fail CLOSED — user can retry their
            # command in ~10s once the classifier recovers.
            print(
                f"[Pipeline] WARN: shutdown — classifier unavailable AND "
                f"fallback disabled; REJECTING (fail-closed for highest "
                f"blast radius)"
            )
            _log_intent_divergence(
                tool_name="shutdown",
                sidecar=None,
                gate_decision="both_unavailable_reject_failclosed",
                user_text=user_text, person_id=person_id,
            )
            return "rejected"
        print("[Pipeline] Tool: shutdown requested")
        return "shutdown"

    elif name == "search_memory":
        # Normally handled inside ask_stream (brain.py). This branch fires only in
        # degraded paths (SICK state non-streaming). Graceful no-op.
        print("[Pipeline] Tool: search_memory fallback — not executed in degraded mode")
        return None

    return None


# Tools that can safely run in parallel with each other (asyncio.gather).
# Criteria: (1) no control-flow signal (shutdown / enroll), (2) no shared-state
# mutation that other concurrent tools read, (3) idempotent on repeated calls.
# All other tools are serialized to avoid ordering hazards.
_CONCURRENT_SAFE_TOOLS: frozenset[str] = frozenset({"search_memory"})


# Matches terminal punctuation followed by whitespace or end-of-string, plus bare newlines.
# Used to split LLM token stream into TTS-ready sentences.
_SENT_END_RE = re.compile(r'[.!?…](?=\s|$)|\n')


async def _refresh_query_embedding(person_id: str, person_name: str, text: str) -> None:
    """Background task: embed query text and cache for the NEXT turn's context retrieval.

    Runs fire-and-forget so the current turn's LLM call starts immediately without
    waiting for the Together.ai embedding round-trip (200-500ms).
    """
    if not _brain_orchestrator:
        return
    try:
        emb = await _brain_orchestrator.embed_query(text)
        if emb is not None:
            _query_embedding_cache[person_id] = emb
    except Exception:
        pass  # OPTIONAL: embedding prefetch failed — next turn uses graph-context fallback


async def _sentence_stream(tokens):
    """Split an async token stream into TTS-ready sentences.

    Buffers until a sentence boundary is found past a minimum character threshold,
    then yields the sentence. The first sentence waits for MIN_FIRST chars so TTS
    gets enough context for natural prosody; subsequent sentences use MIN_REST.
    Remaining buffer is flushed as the final sentence when the token stream ends.
    """
    buf      = ""
    MIN_FIRST = 30   # chars before yielding the first sentence
    MIN_REST  = 15   # chars before yielding subsequent sentences
    first     = True

    async for token in tokens:
        buf += token
        min_len = MIN_FIRST if first else MIN_REST
        while len(buf) >= min_len:
            m = _SENT_END_RE.search(buf, min_len - 1)
            if not m:
                break
            sentence = buf[:m.end()].strip()
            buf = buf[m.end():].lstrip()
            if sentence and any(c.isalpha() for c in sentence):
                yield sentence
                first   = False
                min_len = MIN_REST

    if buf.strip() and any(c.isalpha() for c in buf):
        yield buf.strip()


async def _ask_offline_safe(
    message: str,
    fallback: str,
    *,
    timeout: float = 8.0,
    person_name: str | None = None,
    conversation_history: list[dict] | None = None,
    language: str = "en",
    system_note: str | None = None,
) -> str:
    """Call ask_offline() with a timeout and a hardcoded fallback string."""
    try:
        return await asyncio.wait_for(
            ask_offline(
                message,
                person_name=person_name,
                conversation_history=conversation_history,
                language=language,
                system_note=system_note,
                system_name=_active_system_name,
            ),
            timeout=timeout,
        )
    except Exception as e:
        print(f"[Pipeline] ask_offline failed ({e.__class__.__name__}): using fallback")
        return fallback


def _make_memory_search_fn(person_id: str, db: "FaceDB | None"):
    """Return a memory_search async callback for ask_stream / _kairos_tick.

    Extracted from conversation_turn so _kairos_tick (called from run()) can
    also pass a properly-scoped search function instead of hitting a NameError.
    """
    import json as _json_ms
    _bf_row_ms = _get_best_friend_cached(db) if db else None
    _bf_id_ms  = _bf_row_ms["id"] if _bf_row_ms else None

    async def _memory_search(person_name_q: str, query_q: str) -> str:
        # Bug D3 (2026-04-22 live run): during a disputed session, skip both
        # the knowledge lookup AND the conversation-excerpt search entirely.
        # The <<<IDENTITY DISPUTED>>> prompt block tells the LLM not to
        # reference the sensor-pid's facts, but prompts alone can't prevent
        # leaks — Llama-3.3 sometimes ignores NEVER clauses. Defense-in-
        # depth: if the session is disputed, the tool returns empty results
        # with an explicit hint. Same shape as the sparse path so the
        # LLM's HONESTY POLICY visible-turn exception still applies if it
        # has the answer from the current conversation.
        if _is_disputed(person_id):
            return _json_ms.dumps({
                "person": person_name_q,
                "facts": [],
                "conversation_excerpts": [],
                "status": "disputed",
                "note": f"memory access suspended (identity disputed for '{person_id}')",
                "hint": (
                    "Identity is currently disputed — do NOT reference any "
                    "stored facts for this session's pid. Answer only from "
                    "what the user has said in the visible conversation turns."
                ),
            })
        facts: list[dict] = []
        excerpts: list[dict] = []
        if _brain_orchestrator:
            # Session 95 3A.4 canary: route the knowledge read through the
            # privacy-filtered path. _visibility_clause composes the 4-tier
            # SELECT filter inside query_knowledge_for — so this site no
            # longer needs to know the requester's identity rules; it just
            # passes the session pid + best_friend pid through. Confidence
            # sort + top-5 cap is handled by the method itself.
            # Session 103 Bug I: raised fact limit from 5 → 15. The
            # 2026-04-23 canary showed Jagan ask about Lexi's feelings
            # after a suicidal-ideation conversation; brain got 5 top-
            # confidence facts (name, struggling_with, has_upcoming_test,
            # etc.) but the lower-confidence mood/feeling facts
            # (current_mood='desperate', has_suicidal_thoughts='true',
            # current_feeling='overwhelmed') didn't make the cut. Brain
            # mentally filtered the 5 returned facts against the query
            # word and found nothing relevant → said "I don't have
            # information about Lexi's feelings" despite those facts
            # being in brain.db. Raising the cap widens brain's material
            # so mentally-filter-for-relevance has more to chew on.
            facts = _brain_orchestrator.brain_db.query_knowledge_for(
                requester_pid=person_id,
                best_friend_id=_bf_id_ms,
                entity=person_name_q,
                limit=15,
            )
        if db:
            pid_q = db.get_person_id_by_name(person_name_q)
            if pid_q:
                keyword = next((w for w in query_q.split() if len(w) > 3), query_q)
                excerpts = db.search_conversation(pid_q, keyword, limit=4)
        # Bug N (2026-04-20 live run) — sparse-memory signal.
        # Count total evidence; below MEMORY_SPARSE_THRESHOLD we flag the
        # response as sparse / empty so the LLM knows not to pattern-complete
        # from adjacent memories. Paired with the <<<HONESTY POLICY>>> prompt
        # block, this anchors the model on actual memory state.
        _total = len(facts) + len(excerpts)
        if _total == 0:
            _status = "empty"
            _hint = (
                f"NO facts or conversation excerpts stored for '{person_name_q}'. "
                f"You MUST hedge (\"I don't have details about that\") — do NOT "
                f"invent traits, opinions, or past conversations."
            )
        elif _total < MEMORY_SPARSE_THRESHOLD:
            _status = "sparse"
            _hint = (
                f"Only {_total} fact(s)/excerpt(s) stored for '{person_name_q}'. "
                f"Say what's recorded and explicitly acknowledge you don't have "
                f"more details — do NOT pad with inferences from other people's memories."
            )
        else:
            _status = "ok"
            _hint = None
        result = {
            "person": person_name_q,
            "facts": [{"attribute": f["attribute"], "value": f["value"],
                       "confidence": round(f["confidence"], 2)} for f in facts],
            "conversation_excerpts": [
                f"{e['ts_label']} {e['role'].capitalize()}: {e['excerpt']}"
                for e in excerpts
            ],
            "status": _status,
            "note": f"{len(facts)} fact(s) + {len(excerpts)} excerpt(s) for '{person_name_q}'",
        }
        if _hint is not None:
            result["hint"] = _hint
        return _json_ms.dumps(result)

    return _memory_search


def _make_room_search_fn(
    room_session_id: "str | None",
    requester_pid: str,
    db: "FaceDB | None",
):
    """Phase 3B.5 — return a `room_search_fn` async callback for ask_stream.

    Closes over the current ``room_session_id`` + speaker pid so the brain's
    ``search_room_memory(query)`` tool doesn't need to pass room context
    explicitly. Callback returns a JSON string the follow-up LLM message
    can read directly.

    Gate behavior:
      - `SEARCH_ROOM_MEMORY_ENABLED=False` → return empty result + hint
        (master rollback flag; matches the search_memory empty-with-hint
        pattern so brain routes to direct recall).
      - No active room_session_id (single-session path or room just
        ended) → empty + hint.
      - Room turn count below ``SEARCH_ROOM_MEMORY_MIN_TURNS`` → empty +
        hint naming the threshold so brain knows why.
      - Otherwise → ``FaceDB.search_room_turns`` with requester audience
        filter, renders results with speaker names + relative ages for
        brain consumption.
    """
    import json as _json_rs
    from core.config import (
        SEARCH_ROOM_MEMORY_ENABLED as _ENABLED,
        SEARCH_ROOM_MEMORY_MIN_TURNS as _MIN_TURNS,
    )

    async def _room_search(query: str) -> str:
        if not _ENABLED:
            return _json_rs.dumps({
                "room_id":   room_session_id,
                "turns":     [],
                "status":    "disabled",
                "hint":      (
                    "Room memory search is disabled. Answer from what the "
                    "user just said or from general knowledge."
                ),
            })
        if not room_session_id or db is None:
            return _json_rs.dumps({
                "room_id":   None,
                "turns":     [],
                "status":    "no_room",
                "hint":      (
                    "No active room session to search. Recall directly "
                    "from the visible conversation turns."
                ),
            })
        try:
            _count = db.count_room_turns(room_session_id)
        except Exception as _ex:
            print(f"[Pipeline] search_room_memory count failed: {_ex!r}")
            _count = 0
        if _count < _MIN_TURNS:
            return _json_rs.dumps({
                "room_id":   room_session_id,
                "turns":     [],
                "status":    "too_young",
                "hint":      (
                    f"Room has only {_count} turn(s) logged — below the "
                    f"{_MIN_TURNS}-turn threshold for useful results. "
                    f"Recall directly from visible turns."
                ),
            })
        try:
            raw = db.search_room_turns(
                room_session_id, query,
                requester_pid=requester_pid, limit=20,
            )
        except Exception as _ex:
            print(f"[Pipeline] search_room_memory failed: {_ex!r}")
            raw = []

        # Render for brain: resolve speaker names, format age, trim content.
        now = time.time()
        rendered: list[dict] = []
        for row in raw:
            _pid   = row.get("person_id")
            _name  = None
            if _pid:
                try:
                    _row = db.get_person(_pid)
                    _name = _row["name"] if _row else _pid
                except Exception:
                    _name = _pid
            _delta = max(0.0, now - (row.get("ts") or 0))
            if _delta < 60:
                _age = "just now"
            elif _delta < 3600:
                _age = f"{int(_delta / 60)}m ago"
            else:
                _age = f"{int(_delta / 3600)}h ago"
            _content = (row.get("content") or "")[:200]
            rendered.append({
                "age":     _age,
                "speaker": _name or "unknown",
                "role":    row.get("role"),
                "content": _content,
            })

        if not rendered:
            return _json_rs.dumps({
                "room_id":   room_session_id,
                "turns":     [],
                "status":    "empty",
                "query":     query,
                "hint":      (
                    f"No turns in this room matched '{query}'. The room "
                    f"has {_count} turn(s) logged — try a different "
                    f"keyword or recall directly from visible turns."
                ),
            })

        return _json_rs.dumps({
            "room_id": room_session_id,
            "turns":   rendered,
            "status":  "ok",
            "query":   query,
        })

    return _room_search


def _build_tool_rejection_note(
    *,
    tool_calls:           list[dict],
    tool_results:         dict[str, str],
    intent_sidecar:       "dict | None",
    person_id:            str,
    bf_id:                "str | None",
    brain_orchestrator:   object | None,
) -> "str | None":
    """Session 99 Fix E helper — build the system_note consumed by the
    tool-rejection retry path.

    Facts are the same whether the retry goes to Together.ai (ONLINE,
    main model with full context) or Ollama (SICK fallback). Splitting
    the note-building out of the conditional makes the two retry
    branches share exactly one source of truth for what got rejected
    and why, and keeps the decision-point ``if _cloud_state == ONLINE``
    block uncluttered.

    Returns a newline-joined system_note string, or ``None`` if nothing
    was rejected in a way the brain needs to know about (in which case
    the retry still runs — just without explicit rejection context).

    Currently covers two rejection shapes:
      - Rename rejection (update_system_name / update_person_name) —
        inherited from Session 77's Ollama rename-hedge fix. Note
        instructs the retry to use hedged "I heard X — is that right?"
        phrasing and avoid "From now on…" confirmations.
      - Identity-mismatch rejection on owner queries about visitors —
        inherited from Session 96 Bug 2 + Session 98 expansions. Pulls
        recent VISITOR_ALERT nudges so the retry can speak honestly
        instead of confabulating "there was no one."
    """
    parts: list[str] = []

    # Rename rejection — matches Session 77 behavior verbatim.
    rejected_rename = next(
        (tc for tc in tool_calls
         if tc["name"] in ("update_system_name", "update_person_name")
         and tool_results.get(tc["name"]) == "rejected"),
        None,
    )
    if rejected_rename is not None:
        rename_target = (
            intent_sidecar.get("extracted_value")
            if (intent_sidecar and intent_sidecar.get("extracted_value"))
            else rejected_rename["args"].get("name", "")
        ) or "that name"
        subject = (
            "yourself"
            if rejected_rename["name"] == "update_system_name"
            else "the user"
        )
        parts.append(
            f"You attempted to rename {subject} to '{rename_target}' but "
            f"the rename could NOT be confirmed — the user's current "
            f"utterance did not ground the name assignment. Do NOT say "
            f"'you can call me {rename_target}', 'From now on…', or "
            f"'{rename_target} it is'. Instead, ask the user to confirm "
            f"using hedged phrasing like: \"I heard {rename_target} — "
            f"is that right?\". Keep it to one short sentence."
        )

    # Identity-mismatch rejection on owner query — inject visitor facts.
    rejected_mismatch = next(
        (tc for tc in tool_calls
         if tc["name"] == "report_identity_mismatch"
         and tool_results.get(tc["name"]) == "rejected"),
        None,
    )
    if (
        rejected_mismatch is not None
        and bf_id
        and person_id == bf_id
        and brain_orchestrator is not None
    ):
        try:
            recent_visits = brain_orchestrator._brain_db.get_recent_visitor_alerts(bf_id)
        except Exception as _vex:
            print(f"[Pipeline] visitor-alert fetch failed: {_vex!r}")
            recent_visits = []
        if recent_visits:
            visit_lines: list[str] = []
            for _v in recent_visits[:3]:
                _meta   = _v.get("metadata") or {}
                _vname  = _meta.get("visitor_name") or "a visitor"
                _vturns = _meta.get("turn_count") or 0
                visit_lines.append(
                    f"- {_vname} stopped by and spoke with you ({_vturns} turn(s))."
                )
            visit_summary = "\n".join(visit_lines)
            parts.append(
                "The user is the household owner asking about who visited "
                "while they were away. You DO have this information — "
                "share it honestly:\n"
                f"{visit_summary}\n"
                "Do NOT say 'there was no one', 'I was chatting with "
                "myself', or similar fabrications. The owner has full "
                "access to visitor history — mention the visitor(s) by "
                "name and give a brief natural answer. Keep it to one "
                "short sentence."
            )

    return "\n\n".join(parts) if parts else None


async def conversation_turn(
    text: str,
    person_id: str,
    person_name: str,
    db: "FaceDB" = None,
    vision_state: dict | None = None,
    voice_state: dict | None = None,
    prompt_addendum_override: str | None = None,
) -> tuple[str, str | None]:
    """Handle one turn of conversation. Returns ("continue", None) or ("enroll", name)."""
    global _conversation, _pipeline_state, \
           _cloud_state, _cloud_failed_at, _cloud_monitor_task, _active_system_name, \
           _emotion_agents, _query_embedding_cache, _last_user_speech_at, _identity_hints

    _ct_snap = _session_store.peek_snapshot(person_id)
    _sess_type_badge = _ct_snap.person_type if _ct_snap is not None else "known"
    _type_badge = " [STRANGER]" if _sess_type_badge == "stranger" else ""
    print(f"[Pipeline] Turn start {_now_log_ts()}: {person_name}{_type_badge} — '{text[:60]}{'...' if len(text) > 60 else ''}'")

    # ── Spec 2: graph-classifier outcome supervision ────────────────────
    # Age the pending-outcomes queue once per turn. Entries that have
    # survived GRAPH_OUTCOME_HOLDING_TURNS without correction get
    # auto-credited as confirmed (silence is consent). No-op when the
    # queue is empty (default state in shadow mode and during tests).
    try:
        from core.classifier_graph import age_pending_outcomes as _age_outcomes
        _age_outcomes()
    except Exception as _spec2_age_e:
        # Defensive: outcome supervision is observability-only — never
        # let it break a production turn.
        print(f"[classifier_graph] age_pending_outcomes failed: {_spec2_age_e!r}")

    # ── Session 110 Fix 1 (CRITICAL latency) — background AutoCompact ─────────
    # Was: `_conversation[pid] = await autocompact_history(...)` — blocked the
    # brain response 400-800ms on every turn past the token threshold (30+
    # history items), and up to 3s on retry (API hiccup + backoff). Now:
    # fire as asyncio.create_task; THIS turn uses current (possibly
    # uncompacted) history, NEXT turn reads the compacted version naturally
    # once the background task writes it back. Model context window (~128K)
    # is much larger than our compact threshold (~3-4K tokens), so one turn
    # of uncompacted-but-under-limit history is safe. The background task
    # catches its own exceptions so a failed compaction doesn't take the
    # session down — worst case history stays uncompacted for one more
    # turn.
    if (
        not person_id.startswith("stranger_")
        and person_id not in _compact_pids
    ):
        async def _compact_history_background(_pid: str, _pname: str):
            try:
                _compacted = await autocompact_history(
                    _conversation.get(_pid, []), _pname,
                )
                _conversation[_pid] = _compacted
            except Exception as _cex:
                print(f"[Pipeline] autocompact background failed for {_pid}: {_cex!r}")
            finally:
                _compact_pids.discard(_pid)

        _compact_pids.add(person_id)
        asyncio.create_task(_compact_history_background(person_id, person_name))
        # Session 116 P1 #10 — background spawn visibility. The
        # decoupling architecture is invisible from logs without these
        # markers; reviewers asking "why isn't this blocking?" need
        # ground truth that compaction was deliberately fire-and-forget.
        print(f"[BrainAgent] Spawn (background): autocompact for {person_name}")

    # Bug Q (2026-04-21 live run): the previous "reset on every new user
    # message" block was deleted here — it defeated the repeat guard's entire
    # purpose (which is precisely to stop cross-turn repeats). Evidence from
    # the 2026-04-21 run: LLM called `update_system_name('Kara')` on four
    # consecutive turns (11, 15, 17, 19) with no guard activation because the
    # reset wiped the counter each turn. The guard's `else` branch (in
    # _execute_tool) already handles natural reset: when a different
    # (name, args) tuple fires, the counter for the original tuple resets to 1
    # on the next match. So state persists exactly as long as the same call
    # pattern keeps firing — which is what the guard is for.

    history    = _conversation.get(person_id, [])
    # Use session dict person_type so that identity confirmation during a session
    # immediately lifts the stranger gates — no restart needed.
    is_stranger = (_ct_snap.person_type if _ct_snap is not None else None) == "stranger"

    # Phase 3B.2 — user-to-user silent-skip check. Fires BEFORE _set_state
    # and play_filler so the silent path is audibly silent (no THINKING
    # flash, no filler clip). Gated on ROOM_STAY_SILENT_ON_USER_TO_USER
    # AND multi-person room (single-person has no other user to address).
    # Classifier failure / ambiguous case falls through to the normal
    # response path — the silence is optional / additive, never blocking.
    from core.config import (
        ROOM_STAY_SILENT_ON_USER_TO_USER as _STAY_SILENT,
        USER_TO_USER_HEURISTIC_ENABLED as _U2U_HEURISTIC,
    )
    if _STAY_SILENT and len(_session_store.peek_all_snapshots()) >= 2:
        # Session 115 Fix 1 — heuristic pre-check eliminates ~80% of
        # classifier calls. Vocative-name regex against active session
        # names. When the heuristic is confident, skip the classifier
        # entirely; when inconclusive, fall through to the cached path.
        _u2u_sidecar: "dict | None" = None
        _heuristic_decision: "tuple[str, str] | None" = None
        if _U2U_HEURISTIC:
            _other_names = {
                snap.person_name for snap in _session_store.peek_all_snapshots()
                if snap.person_id != person_id and snap.person_name
            }
            _heuristic_decision = _user_to_user_heuristic(
                text, _active_system_name, _other_names,
            )
        if _heuristic_decision and _heuristic_decision[0] == "user_to_person":
            # Heuristic confident → synthesize a sidecar that drives the
            # existing silent-skip code below. Classifier never called.
            _u2u_sidecar = {
                "turn_intent":     "direct_address_to_person",
                "extracted_value": _heuristic_decision[1],
                "confidence":      1.0,
                "reasoning":       "heuristic vocative match",
            }
        elif _heuristic_decision and _heuristic_decision[0] == "addressing_ai":
            # Heuristic confident user IS addressing AI → classifier is
            # redundant. Leave _u2u_sidecar=None so silent-skip path
            # naturally exits and the normal response runs.
            _u2u_sidecar = None
        else:
            # Inconclusive — call classifier (cached) for the ambiguous case.
            _u2u_sidecar = await _classify_intent_cached(
                text, history,
                frozenset(s.person_id for s in _session_store.peek_all_snapshots()),
            )
        if (
            _u2u_sidecar
            and _u2u_sidecar.get("turn_intent") == "direct_address_to_person"
        ):
            _addressed = (_u2u_sidecar.get("extracted_value") or "").strip()
            # System-name collision edge: if the classifier extracted a name
            # that matches the AI's own name (e.g. someone in the room is
            # named "Kara" AND the AI is "Kara"), ambiguity wins — fall
            # through to the normal response path (safer to respond).
            _is_system_name = (
                _addressed
                and _addressed.lower() == (_active_system_name or "").lower()
            )
            if _addressed and not _is_system_name:
                print(
                    f"[Pipeline] User-to-user detected — "
                    f"addressed to {_addressed!r}, staying silent"
                )
                # Preserve history + extraction. No TTS, no tool execution.
                _now_ts_u2u = time.time()
                history.append({
                    "role":    "user",
                    "content": text,
                    "ts":      _now_ts_u2u,
                })
                _conversation[person_id] = history
                _room_sid_u2u = _ct_snap.room_session_id if _ct_snap is not None else None
                if db and not _is_disputed(person_id):
                    db.log_turn(
                        person_id, "user", text,
                        room_session_id=_room_sid_u2u,
                        audience_ids=[person_id],
                    )
                    if _brain_orchestrator:
                        _brain_orchestrator.notify()
                # Bump user turn counter to keep session lifecycle consistent
                # with turns where the brain DID respond — other state reads
                # (stranger promotion thresholds, address-decision gating)
                # assume this field reflects every user utterance.
                try:
                    _loop = asyncio.get_running_loop()
                    _loop.create_task(_session_store.increment_user_turns(person_id))
                    _loop.create_task(_session_store.set_last_spoke_at(person_id, _now_ts_u2u))
                except RuntimeError:
                    pass  # OPTIONAL
                return ("continue", None)

    # Signal THINKING and play filler immediately — no awaits have fired yet, so
    # the user hears the filler at the earliest possible moment.
    # (Previously delayed ~300ms by the embed_query await that came before this.)
    _set_state(PipelineState.THINKING, person_name)
    play_filler(text)

    # Context retrieval — use embedding cached from the PREVIOUS turn (instant dict
    # lookup) instead of a blocking 200-500ms Together.ai round-trip.
    # A background task refreshes the cache; the next turn benefits from it.
    cached_embedding = _query_embedding_cache.get(person_id)
    if _brain_orchestrator and not is_stranger and person_name:
        asyncio.create_task(_refresh_query_embedding(person_id, person_name, text))

    _bf_row = _get_best_friend_cached(db) if db else None
    _bf_id  = _bf_row["id"] if _bf_row else None

    memory_context = (
        _brain_orchestrator.get_context(
            person_name,
            query_embedding=cached_embedding,
            requester_person_id=person_id,
            best_friend_id=_bf_id,
        )
        if _brain_orchestrator and not is_stranger and person_name
        else None
    )

    # Emotion detection — per-person EmotionAgent, shared HuggingFace pipeline.
    # Agents are kept alive across sessions (90-second TTL handles stale data).
    #
    # Session 110 Fix 2 (HIGH latency) — emotion `process_turn` now fires as
    # asyncio.create_task instead of blocking the critical path on a
    # 15-25ms executor call. The `emotion_context` block injected into THIS
    # turn's prompt reflects the agent's PRIOR state (emotion from previous
    # turns); this turn's new emotion lands on the NEXT turn's context.
    # One-turn lag is acceptable for emotion (changes slowly, rolling
    # 3-turn window in EmotionAgent) and saves 15-25ms × every turn — free
    # win that scales with future multi-person emotion work. The fact-storage
    # side-effect (`store_temporal_fact` for `current_feeling`) runs inside
    # the background task so it doesn't block either; its sub-ms SQLite
    # write is unaffected by the move.
    emotion_context = None
    if not is_stranger:
        # Lazy-create agent for this person on first interaction
        if person_id not in _emotion_agents:
            _emotion_agents[person_id] = EmotionAgent()
        _cur_agent = _emotion_agents[person_id]

        async def _emotion_process_background(_pid: str, _pname: str, _agent, _text: str):
            try:
                _loop = asyncio.get_running_loop()
                await _loop.run_in_executor(None, _agent.process_turn, _text)
                if _brain_orchestrator and _agent.should_store_as_fact() and _pid:
                    _fact_val = _agent.get_fact_value()
                    if _fact_val:
                        _brain_orchestrator.store_temporal_fact(
                            _pid, _pname, "current_feeling", _fact_val,
                            valid_for_hours=EMOTION_FACT_VALIDITY_HOURS,
                        )
            except Exception as _eex:
                print(f"[Pipeline] emotion background failed for {_pid}: {_eex!r}")

        asyncio.create_task(
            _emotion_process_background(person_id, person_name, _cur_agent, text)
        )
        # Session 116 P1 #10 — background spawn visibility.
        print(f"[BrainAgent] Spawn (background): emotion process_turn for {person_name}")

        # Build emotion context — single-person or multi-person block.
        # Reads agents' CURRENT cached state (pre-this-turn). THIS turn's
        # fresh emotion update from the background task will be visible on
        # the NEXT turn's context build.
        _emo_lines: list[str] = []
        for _emo_pid, _emo_ag in _emotion_agents.items():
            if _session_store.peek_snapshot(_emo_pid) is None:
                continue
            _emo_snap_em = _session_store.peek_snapshot(_emo_pid)
            _emo_name = _emo_snap_em.person_name if _emo_snap_em is not None else _emo_pid
            _emo_ctx  = _emo_ag.get_context_string()
            if _emo_ctx:
                _emo_lines.append(f"{_emo_name}: {_emo_ctx.replace('CURRENT EMOTIONAL TONE: ', '')}")

        if _emo_lines:
            if len(_emo_lines) == 1:
                # Preserve existing single-person format for backward compatibility
                emotion_context = f"CURRENT EMOTIONAL TONE: {_emo_lines[0]}"
            else:
                # Multi-person format: one line per active person with emotion
                emotion_context = "<<<EMOTIONAL CONTEXT>>>\n" + "\n".join(_emo_lines)

    # Multi-person room context — injected when more than one person is active.
    # Gives the brain full awareness of who is present and recent cross-person
    # exchanges so it can make dynamic, human-like routing decisions.
    _all_snaps_ct = _session_store.peek_all_snapshots()
    room_context = _build_cross_person_excerpts(person_id, _all_snaps_ct, _conversation, _bf_id)
    if room_context:
        print(f"[Brain] Room context: {len(_all_snaps_ct)} people active")

    print(f"[Brain] Context: history={len(history)} turns, memory={'yes' if memory_context else 'no'}, emotion={'yes' if emotion_context else 'no'}, room={'yes' if room_context else 'no'}, scene={'yes' if SCENE_BLOCK_ENABLED else 'no'}")

    # Spatial memory — only active when YOLO is enabled
    object_context = None
    if VISION_YOLO_ENABLED and _brain_orchestrator and not is_stranger:
        object_context = _brain_orchestrator.get_object_context(text)
        if time.time() - _yolo_last_ran < 30.0:
            live_items = [d["class"] for d in _latest_yolo_detections if d["class"] != "person"]
            if live_items:
                live_str = "What I can see in the camera right now: " + ", ".join(live_items)
                object_context = (live_str + "\n\n" + object_context) if object_context else live_str

    # prompt_addendum_override takes precedence (used for stranger mode and similar).
    # Otherwise fall back to brain agent's learned prefs for this person.
    if prompt_addendum_override is not None:
        prompt_addendum = prompt_addendum_override
    else:
        prompt_addendum = (
            _brain_orchestrator.get_prompt_addendum(person_id)
            if _brain_orchestrator and not is_stranger and person_id
            else None
        )

    # Room context prepended to prompt_addendum so the brain sees it as part
    # of every multi-person turn and can make fully dynamic decisions.
    if room_context:
        prompt_addendum = room_context + ("\n\n" + prompt_addendum if prompt_addendum else "")

    # SCENE sensor block — always-on snapshot of who is visible / audible,
    # injected into the system prompt on every turn.
    scene_block = (
        _get_scene_block_cached(
            person_id, time.time(), _session_store.peek_all_snapshots(), _persons_in_frame,
            _unrecognized_tracks, _bf_id,
            recent_visitors=_fetch_recent_visitors_for_scene(_bf_id),
        )
        if SCENE_BLOCK_ENABLED else None
    )

    # Proactive curiosity — pattern question queued by ObjectPatternAgent.
    # Injected once per question; the LLM weaves it in when the moment feels right.
    if _brain_orchestrator and not is_stranger:
        pending_q = _brain_orchestrator.get_pending_question()
        if pending_q:
            q_hint = (
                "\n- PROACTIVE CURIOSITY (ask this naturally when the moment feels right — "
                "only if the conversation is relaxed, do not force it):\n"
                f"  \"{pending_q['text']}\""
            )
            prompt_addendum = (prompt_addendum or "") + q_hint
            _brain_orchestrator.mark_question_asked(pending_q["id"])

    # ── Identity hint injection for stranger sessions ─────────────────────────
    # Hint is built from the PREVIOUS turn's scoring — always one turn delayed,
    # which is correct: we need conversation content before we can score.
    if is_stranger and person_id in _identity_hints:
        _id_h    = _identity_hints[person_id]
        _id_conf = _id_h["confidence"]
        _id_name = _id_h["name"]
        _id_rel  = _id_h.get("relationship") or "acquaintance"
        _id_match = ", ".join(_id_h.get("matched_attrs", [])[:3])
        if _id_conf >= IDENTITY_ASK_THRESHOLD:
            _id_note = (
                f"\n- IDENTITY HYPOTHESIS (confidence {_id_conf:.0%}): "
                f"I believe this stranger may be '{_id_name}' "
                f"({_id_rel} of the best friend). "
                f"Matched signals: {_id_match or 'conversation overlap'}. "
                f"When the moment feels natural, ask gently: 'By any chance, are you {_id_name}?' "
                f"If they confirm, call update_person_name('{_id_name}') immediately."
            )
            prompt_addendum = (prompt_addendum or "") + _id_note
        elif _id_conf >= IDENTITY_SOFT_THRESHOLD:
            _id_note = (
                f"\n- IDENTITY HYPOTHESIS (soft, confidence {_id_conf:.0%}): "
                f"There is a weak signal that this stranger might be '{_id_name}' "
                f"({_id_rel} of the best friend). Do NOT mention this — "
                f"just be aware. More conversation will sharpen the signal."
            )
            prompt_addendum = (prompt_addendum or "") + _id_note

    response          = ""
    tool_calls        = []
    response_streamed = False

    # Session 113 Part 1 — ADDRESS DECISION marker state, hoisted to function
    # scope so SICK/OFFLINE paths can safely read _addr_override[0] (always
    # None on those paths → resolution falls back to effective_name). Only
    # the ONLINE branch's _token_gen writes through the closure.
    _addr_override: list["str | None"] = [None]
    _marker_done:   list[bool]         = [False]
    _prefix_buf:    list[str]          = []

    # ── Cloud state machine ────────────────────────────────────────────────────
    if _cloud_state == CloudState.SICK:
        # Grace period: try Together.ai — it might have recovered
        try:
            response, tool_calls = await ask(
                text,
                person_name=person_name,
                conversation_history=history,
                language=_detected_lang,
                vision_state=vision_state,
                voice_state=voice_state,
                memory_context=memory_context,
                object_context=object_context,
                emotion_context=emotion_context,
                prompt_addendum=prompt_addendum,
                system_name=_active_system_name,
                scene_block=scene_block,
            )
            # Recovered!
            _cloud_state = CloudState.ONLINE
            print("[Cloud] State: SICK → ONLINE (recovered mid-conversation)")
            print("[Pipeline] Together.ai recovered (detected mid-conversation)")
        except Exception:
            elapsed = time.time() - _cloud_failed_at
            if elapsed >= CLOUD_OFFLINE_TIMEOUT:
                print(f"[Cloud] State: SICK → OFFLINE (timeout={elapsed:.0f}s >= {CLOUD_OFFLINE_TIMEOUT}s)")
                _cloud_state = CloudState.OFFLINE
                if _cloud_monitor_task is None or _cloud_monitor_task.done():
                    _cloud_monitor_task = asyncio.create_task(_cloud_retry_loop())
                response = await _ask_offline_safe(
                    text,
                    "I'm having some real trouble with my brain right now. "
                    "I can still chat, but I won't be my full self for a bit — bear with me.",
                    timeout=15.0,
                    person_name=person_name,
                    conversation_history=history,
                    language=_detected_lang,
                    system_note=(
                        "Your cloud connection has gone down. "
                        "Briefly mention you're having some brain trouble and won't be fully yourself for a bit, "
                        "then do your best to answer."
                    ),
                )
            else:
                response = await _ask_offline_safe(
                    text,
                    "Still a little under the weather... give me just a bit more time.",
                    timeout=15.0,
                    person_name=person_name,
                    conversation_history=history,
                    language=_detected_lang,
                    system_note=(
                        "Your cloud connection is unstable right now. "
                        "Briefly mention you're a bit under the weather, then do your best to answer."
                    ),
                )

    elif _cloud_state == CloudState.OFFLINE:
        # Ollama stateless Q&A — no memory, no tools
        response = await _ask_offline_safe(
            text,
            "Sorry, I'm really struggling right now — give me a moment.",
            timeout=30.0,
            person_name=person_name,
            conversation_history=history,
            language=_detected_lang,
        )

    else:
        # ONLINE: stream Together.ai — first sentence plays as soon as LLM produces it
        try:
            response_parts: list[str] = []
            # Obs 3: authoritative truncation signal from the SSE stream.
            # "stop" = natural end; "length" / "content_filter" / None = truncated.
            # Mutable single-element list so the nested generator can write through it.
            _stream_finish_reason: list[str | None] = [None]
            # Session 113 Part 1 — ADDRESS DECISION marker state is hoisted to
            # conversation_turn() scope (see function top). _token_gen writes
            # through the closures; SICK/OFFLINE branches leave it None.

            # Memory search callback — executed inside ask_stream when LLM calls search_memory
            _memory_search = _make_memory_search_fn(person_id, db)

            # Wave 4 Item 17 — session-stable prefix cache for main conversation.
            _snap_conv = _session_store.peek_snapshot(person_id)
            if _snap_conv is not None:
                if _snap_conv.cached_prefix is None:
                    _cp_value = render_session_stable_prefix(
                        system_name=_active_system_name,
                        session_person_type=_snap_conv.person_type,
                        session_user_turns=_snap_conv.user_turns,
                        identity_disputed=_is_disputed(person_id),
                        person_name=person_name,
                        disputed_claimed_name=_snap_conv.disputed_claimed_name,
                        core_memory=_snap_conv.core_memory,
                    )
                    try:
                        _loop = asyncio.get_running_loop()
                        _loop.create_task(_session_store.set_cached_prefix(person_id, _cp_value))
                    except RuntimeError:
                        pass  # OPTIONAL
                _conv_cached_prefix = _snap_conv.cached_prefix
            else:
                _conv_cached_prefix = None

            async def _token_gen():
                async for ev_type, payload in ask_stream(
                    text,
                    person_name=person_name,
                    conversation_history=history,
                    language=_detected_lang,
                    vision_state=vision_state,
                    voice_state=voice_state,
                    memory_context=memory_context,
                    object_context=object_context,
                    emotion_context=emotion_context,
                    prompt_addendum=prompt_addendum,
                    system_name=_active_system_name,
                    memory_search_fn=_memory_search,
                    room_search_fn=_make_room_search_fn(
                        _active_room_session, person_id, db,
                    ),
                    scene_block=scene_block,
                    cached_prefix=_conv_cached_prefix,
                ):
                    if ev_type == "text":
                        # Session 113 Part 1 — intercept the very first
                        # tokens, hold back until we can confidently
                        # classify whether the response starts with an
                        # `[addressing:X]` marker. Once classified,
                        # either (a) strip the marker + yield the
                        # remainder, or (b) release the buffered prefix
                        # as-is. Subsequent tokens stream normally once
                        # `_marker_done[0]` is True. TTS never hears
                        # the marker.
                        if not _marker_done[0]:
                            _prefix_buf.append(payload)
                            _joined = "".join(_prefix_buf)
                            _stripped = _joined.lstrip()
                            if _stripped and not _stripped.startswith("["):
                                # First non-whitespace char isn't '[' —
                                # no marker possible. Flush buffered
                                # text as-is.
                                _marker_done[0] = True
                                response_parts.append(_joined)
                                yield _joined
                                _prefix_buf.clear()
                            elif "]" in _stripped:
                                # Closing bracket arrived — parse marker.
                                _m = re.match(
                                    r"^\s*\[addressing:([^\]]+)\]\s*\n?(.*)$",
                                    _joined,
                                    re.DOTALL,
                                )
                                if _m:
                                    _addr_override[0] = _m.group(1).strip()
                                    print(f"[Pipeline] ADDRESS DECISION parsed: addressing={_addr_override[0]!r}")
                                    _rest = _m.group(2)
                                    if _rest:
                                        response_parts.append(_rest)
                                        yield _rest
                                else:
                                    # Closing bracket but not an
                                    # addressing marker — content
                                    # coincidentally starts with '[',
                                    # yield as-is.
                                    response_parts.append(_joined)
                                    yield _joined
                                _marker_done[0] = True
                                _prefix_buf.clear()
                            elif len(_joined) > 60:
                                # Buffering too long — give up, flush.
                                _marker_done[0] = True
                                response_parts.append(_joined)
                                yield _joined
                                _prefix_buf.clear()
                            # else: keep buffering, waiting for ']'.
                        else:
                            response_parts.append(payload)
                            yield payload
                    elif ev_type == "tool_calls":
                        tool_calls.extend(payload)
                        # Layer 4: If action tools detected, interrupt any in-flight audio.
                        # speak_stream runs _synth_worker and _play_worker concurrently,
                        # so wrong text may already be mid-play when tool_calls arrives.
                        # stop_audio() cuts it off via sd.stop() — no-op if already done.
                        if any(tc["name"] in HISTORY_OVERRIDE_TOOLS for tc in payload):
                            stop_audio()
                    elif ev_type == "finish":
                        _stream_finish_reason[0] = payload
                # Session 113 Part 1 — flush edge case: stream ended while
                # marker buffer was still open (tokens starting with '[' but
                # no closing ']' ever arrived). Release the buffered prefix
                # as-is so TTS + history see the real content.
                if not _marker_done[0] and _prefix_buf:
                    _leftover = "".join(_prefix_buf)
                    response_parts.append(_leftover)
                    yield _leftover
                    _prefix_buf.clear()
                    _marker_done[0] = True

            _set_state(PipelineState.SPEAKING, person_name)
            await speak_stream(_sentence_stream(_token_gen()), language=_detected_lang)
            response          = "".join(response_parts)
            # Treat responses with no alphabetical content as empty (e.g. model returned "{}")
            if response and not any(c.isalpha() for c in response):
                response = ""
            # Bug H (2026-04-20 live run) — response-level meta-commentary suppression.
            # The TTS filter drops the *sentence* that leaked, but if the whole
            # response is meta-commentary ("No function call is needed for this
            # prompt.") we also must not log it as a real assistant turn in history
            # — otherwise future turns see the model pattern and imitate it. The
            # filter is narrow enough that this only fires on the documented leak
            # shapes, not on legit responses.
            from core.audio import _is_meta_commentary
            if response and _is_meta_commentary(response.strip()):
                print(f"[Brain] Meta-commentary suppressed: '{response}'")
                response = ""
            response_streamed = True

            # ── Stream truncation detection ───────────────────────────────────
            # Two retry paths, split by response shape:
            #   Case A — very short truncation (≤ 2 words, no terminator):
            #     the stream dropped early enough that starting fresh via Ollama
            #     is cleaner than trying to continue. stop_audio() cuts the
            #     fragment before speak() plays the full replacement.
            #   Case B — longer response truncated mid-sentence:
            #     original audio finished playing before we got here; asking
            #     Ollama to COMPLETE (not replace) the final sentence produces
            #     a natural pause-and-resume effect. The completion is appended
            #     to the response so history records the full utterance.
            #
            # Retries fire only when:
            #   - the response is non-empty
            #   - the stream did NOT end on terminal punctuation
            #   - SSE finish_reason indicates truncation ("length" /
            #     "content_filter" / None) — Obs 3 authoritative signal
            #   - no tool_calls (those are handled separately)
            #   - cloud is still ONLINE (offline would mean Ollama was already used)
            #
            # The word-count + punctuation gates remain as defense in depth:
            # a single-word finish_reason="stop" reply ("Hmm", "Wow") must not
            # accidentally trip Case A.
            _stream_words  = response.split() if response else []
            _tail          = response.strip()[-80:] if response else ""
            _ends_terminal = _tail.rstrip().endswith((".", "!", "?", "…")) if _tail else False
            _finish        = _stream_finish_reason[0]
            _truncated     = _finish in ("length", "content_filter", None)

            if not (response and not _ends_terminal and _truncated
                    and not tool_calls and _cloud_state == CloudState.ONLINE):
                pass  # nothing to retry
            elif len(_stream_words) <= 2:
                # Case A: very short truncation — full replacement via Ollama.
                # Bug 5 (2026-04-20): "Hello!" had the user hear both TTS clips
                # back-to-back before the terminal-punctuation gate landed.
                print(f"[Brain] Stream truncation (short): {len(response)} chars ('{response}') — full retry via Ollama")
                _retry_resp = await _ask_offline_safe(
                    text,
                    "Sorry, let me think on that again.",
                    timeout=15.0,
                    person_name=person_name,
                    conversation_history=history,
                    language=_detected_lang,
                )
                if len(_retry_resp) > len(response):
                    # Cut the first-response tail so user doesn't hear overlap.
                    stop_audio()
                    await speak(_retry_resp, language=_detected_lang)
                    response = _retry_resp
                    # response_streamed stays True — speak() above already played it;
                    # history will record the full retry response, not the fragment.
            else:
                # Case B: longer response truncated mid-sentence. Bug D
                # (2026-04-20 review): a 350-word answer with a chopped final
                # fragment ("His bravery and") passed the old "≤ 2 words" gate
                # and was never retried. Ask Ollama to COMPLETE the final
                # sentence naturally — original audio already played, so this
                # feels like a pause-and-resume rather than a retry.
                print(f"[Brain] Stream truncation (tail): tail='{_tail[-40:]}' finish={_finish} — requesting completion")
                _completion_prompt = (
                    "You were mid-sentence and got cut off. Here is what you "
                    "already said (do NOT repeat any of it):\n\n"
                    f"{response}\n\n"
                    "Complete ONLY the final sentence — one short sentence, "
                    "natural continuation, no preamble."
                )
                _continuation = await _ask_offline_safe(
                    _completion_prompt,
                    "",
                    timeout=10.0,
                    person_name=person_name,
                    conversation_history=[],
                    language=_detected_lang,
                )
                if _continuation and _continuation.strip():
                    # Original audio already finished playing — just speak the
                    # tail. Feels like the model paused and thought a moment.
                    await speak(_continuation, language=_detected_lang)
                    response = response.rstrip() + " " + _continuation.strip()

        except Exception as e:
            print(f"[Brain] Together.ai stream failed: {e}")
            print(f"[Cloud] State: ONLINE → SICK ({type(e).__name__})")
            _cloud_state     = CloudState.SICK
            _cloud_failed_at = time.time()
            if _cloud_monitor_task is None or _cloud_monitor_task.done():
                _cloud_monitor_task = asyncio.create_task(_cloud_retry_loop())
            response = await _ask_offline_safe(
                text,
                "Oops, I'm feeling a bit sick right now... give me a moment to sort myself out.",
                timeout=15.0,
                person_name=person_name,
                conversation_history=history,
                language=_detected_lang,
                system_note=(
                    "Your cloud connection just went down unexpectedly. "
                    "Briefly mention you're having a brain hiccup and may not be fully yourself, "
                    "then do your best to answer."
                ),
            )

    # ── VISION_ROADMAP P1.3 — shadow intent classifier (lazy, gated-tool only) ─
    # Only fire the classifier when the main stream proposed a tool whose
    # gate is in TOOL_INTENT_MAP. Non-gated turns (no tools, or only search_memory)
    # pay zero extra cost. The result is a dict {turn_intent, extracted_value,
    # confidence, reasoning} or None on classifier failure. For Phase 1.3 we
    # only LOG it — the regex gate remains authoritative until P1.7+ wires the
    # validator (gated behind INTENT_FALLBACK_TO_REGEX).
    from core.config import INTENT_SHADOW_MODE_ENABLED, TOOL_INTENT_MAP
    _intent_sidecar: "dict | None" = None
    if (INTENT_SHADOW_MODE_ENABLED
            and tool_calls
            and any(tc["name"] in TOOL_INTENT_MAP for tc in tool_calls)):
        # Spec 2 wiring: route through `_classify_intent_smart` so graph
        # runs alongside LLM in shadow mode. Production behavior identical
        # in shadow (LLM result returned + divergences logged).
        from core.brain import _classify_intent_smart
        _intent_sidecar = await _classify_intent_smart(text, conversation_history=history)
        if _intent_sidecar is not None:
            _tool_names_str = ", ".join(tc["name"] for tc in tool_calls
                                        if tc["name"] in TOOL_INTENT_MAP)
            print(
                f"[Intent] {_now_log_ts()} "
                f"tools=[{_tool_names_str}] "
                f"classified={_intent_sidecar['turn_intent']} "
                f"value={_intent_sidecar['extracted_value']!r} "
                f"conf={_intent_sidecar['confidence']:.2f} "
                f"reason={_intent_sidecar.get('reasoning', '')[:80]!r}"
            )

    # ── Spec 2: brain stays silent on user correction ───────────────────
    # When the graph classifier (or any future classifier) emits
    # `correction_to_previous_response`, the user is correcting the AI's
    # previous turn. The pipeline applies outcome supervision (decrement
    # wrong-vote scenarios + optionally insert a corrected positive
    # scenario) and SKIPS brain response generation entirely — replying
    # would be additional intrusion. NO LLM CALL in this code path.
    # In shadow mode the LLM classifier never emits this label so the
    # branch is dormant; in primary/retired mode it activates whenever
    # the graph fires the label.
    if _intent_sidecar and _intent_sidecar.get("turn_intent") == "correction_to_previous_response":
        try:
            from core.classifier_graph import handle_correction as _handle_correction
            _correction_summary = await _handle_correction(
                text,
                system_name=_active_system_name,
            )
            print(
                f"[classifier_graph] correction handled: "
                f"decremented={_correction_summary.get('scenarios_decremented')} "
                f"target={_correction_summary.get('target_extracted')!r} "
                f"new_scenario={_correction_summary.get('new_scenario_id')}"
            )
        except Exception as _spec2_corr_e:
            print(f"[classifier_graph] handle_correction failed: {_spec2_corr_e!r}")
        # Skip brain response generation. Return same tuple shape as the
        # normal path so the caller sees the turn completed cleanly.
        return ("continue", None)

    # Phase 5 (Session 119) — 1% canary shadow sample. Independent of
    # the gate-fired classifier above; this samples passively on EVERY
    # turn so the weekly review can spot drift in cases the gates never
    # see. Wrapped in try/except so a bug in sampling can't break the
    # turn — the existing `_intent_sidecar` path keeps producing real
    # gate decisions regardless. Disabled via SHADOW_SAMPLE_ENABLED kill
    # switch.
    try:
        from core.config import (
            SHADOW_SAMPLE_ENABLED as _SHADOW_ON,
            SHADOW_SAMPLE_RATE    as _SHADOW_RATE,
        )
        import random as _random_p5
        if _SHADOW_ON and _random_p5.random() < _SHADOW_RATE:
            from core.brain import _classify_intent as _classify_intent_shadow
            _shadow_sidecar = await _classify_intent_shadow(
                text, conversation_history=history,
            )
            if _shadow_sidecar is not None and _brain_orchestrator is not None:
                try:
                    _brain_orchestrator.brain_db.log_intent_divergence(
                        tool_proposed="",
                        gate_decision="shadow_sample",
                        user_text=text,
                        person_id=person_id,
                        structured_intent=_shadow_sidecar.get("turn_intent"),
                        structured_extracted=_shadow_sidecar.get("extracted_value"),
                        structured_confidence=_shadow_sidecar.get("confidence"),
                        mode="shadow",
                    )
                except Exception as _shadow_log_ex:
                    print(f"[Phase5] shadow log failed: {_shadow_log_ex!r}")
    except Exception as _shadow_ex:
        # Belt-and-braces — sampling path must never break a turn.
        print(f"[Phase5] shadow sampler failed: {_shadow_ex!r}")

    # ── Execute tool calls (ONLINE mode only) ──────────────────────────────────
    # Pattern 3 (isConcurrencySafe): safe tools run in parallel via asyncio.gather;
    # control-flow tools (shutdown) and state-mutating tools run serially.
    safe_calls   = [tc for tc in tool_calls if tc["name"] in _CONCURRENT_SAFE_TOOLS]
    serial_calls = [tc for tc in tool_calls if tc["name"] not in _CONCURRENT_SAFE_TOOLS]

    # Bugs P + Q (2026-04-21): per-tool result classification. The four
    # possible outcomes are:
    #   "handled"       → tool effective, emit canonical ack if applicable
    #   "handled_noop"  → tool ran but no state change; suppress canonical ack
    #                     (Bug Q feedback-loop driver)
    #   "unknown"       → LLM hallucinated the tool name; discard silently
    #                     (Bug P: separate from privilege-denied)
    #   None / shutdown → existing semantics (blocked / triggers shutdown)
    _tool_results: dict[str, object] = {}
    if safe_calls:
        safe_results = await asyncio.gather(
            *[_execute_tool(tc["name"], tc["args"], person_id, person_name, db,
                            user_text=text, intent_sidecar=_intent_sidecar)
              for tc in safe_calls],
            return_exceptions=True,
        )
        for tc, res in zip(safe_calls, safe_results):
            if isinstance(res, Exception):
                print(f"[Pipeline] Tool {tc['name']} error: {res}")
                _tool_results[tc["name"]] = None
            else:
                _tool_results[tc["name"]] = res

    for tc in serial_calls:
        try:
            result = await _execute_tool(tc["name"], tc["args"], person_id, person_name, db,
                                          user_text=text, intent_sidecar=_intent_sidecar)
        except Exception as e:
            print(f"[Pipeline] Tool {tc['name']} error: {e}")
            result = None
        _tool_results[tc["name"]] = result
        if result == "shutdown":
            _shutdown_event.set()
            break

    _any_tool_effective = any(r == "handled"      for r in _tool_results.values())
    _any_tool_noop      = any(r == "handled_noop" for r in _tool_results.values())
    # Session 71 unified "rejected" (Bugs S/T): "unknown" (hallucinated name)
    # and "rejected" (user-text gate failure) both mean the LLM wanted to act
    # but had no real grounding in the user's actual utterance. Both classes
    # route through the same Ollama-retry path.
    _all_unreal         = bool(tool_calls) and all(
        _tool_results.get(tc["name"]) in ("unknown", "rejected") for tc in tool_calls
    )

    # ── Shutdown rejection: prevent history poisoning (Issue A, Session 28) ──
    # When the LLM calls shutdown() but _execute_tool's user-text gate rejects
    # it (returns "rejected"), the LLM may have ALSO streamed "Goodbye!" text
    # alongside the tool call. If that text enters history, the next turn's
    # context contains "Goodbye!" and the LLM re-triggers shutdown → infinite
    # loop. Override to "Okay." so history records something neutral, and
    # keep response_streamed=True so we don't re-speak (user already heard
    # whatever the LLM actually streamed over TTS). This remains narrow and
    # shutdown-specific — other "rejected" outcomes flow through the unified
    # _all_unreal Ollama-retry path below.
    _shutdown_was_rejected = any(
        tc["name"] == "shutdown" and _tool_results.get(tc["name"]) == "rejected"
        for tc in tool_calls
    )
    if _shutdown_was_rejected:
        response          = "Okay."
        response_streamed = True

    # ── Bugs P + S + T: all tool calls were ungrounded ───────────────────────
    # Either the LLM invented a tool name (Bug P) or the user-text gate rejected
    # the call because the user's turn didn't actually support the action
    # (Bugs S, T). If the streamed response is also empty (LLM spent its text
    # budget on the phantom/rejected call), retry for clean conversational
    # text instead of the "Sorry, I missed that" filler.
    #
    # Session 99 Fix E: retry target depends on cloud state.
    #   ONLINE  → Together.ai (tools disabled). Preserves full context +
    #             visitor history + SCENE block + owner-access model.
    #   SICK    → Ollama. Stateless fallback — keeps inherited Session 77
    #             rename-hedge and Session 96/98 visitor-hint plumbing.
    # Both branches receive the same system_note built from the rejection
    # facts. Ollama was the confabulation source for every whack-a-mole
    # bug debugged Sessions 77 / 96 / 98 precisely because it was firing
    # while cloud was healthy. Routing to Together.ai eliminates that
    # failure mode for the common case.
    if _all_unreal and not response:
        _system_note_retry = _build_tool_rejection_note(
            tool_calls=tool_calls,
            tool_results=_tool_results,
            intent_sidecar=_intent_sidecar,
            person_id=person_id,
            bf_id=_bf_id,
            brain_orchestrator=_brain_orchestrator,
        )
        if _cloud_state == CloudState.ONLINE:
            print("[Pipeline] All tool calls ungrounded — Together.ai retry (tools disabled, full context)")
            try:
                response = await ask_retry_text(
                    text,
                    person_name=person_name,
                    conversation_history=history,
                    language=_detected_lang,
                    vision_state=vision_state,
                    voice_state=voice_state,
                    memory_context=memory_context,
                    object_context=object_context,
                    emotion_context=emotion_context,
                    prompt_addendum=prompt_addendum,
                    system_name=_active_system_name,
                    scene_block=scene_block,
                    retry_system_note=_system_note_retry,
                )
            except Exception as _retry_exc:
                # Retry failed too — fall back to the offline safety net so
                # the user still gets some audible reply. Cloud-state
                # machinery elsewhere will flip us to SICK on sustained
                # errors; here we just need a best-effort text for THIS turn.
                print(f"[Pipeline] Together.ai retry failed ({type(_retry_exc).__name__}); using Ollama safety net")
                response = await _ask_offline_safe(
                    text,
                    "I didn't quite follow — could you say that again?",
                    timeout=10.0,
                    person_name=person_name,
                    conversation_history=history,
                    language=_detected_lang,
                    system_note=_system_note_retry,
                )
        else:
            # SICK/OFFLINE — original Ollama fallback stays intact.
            print("[Pipeline] All tool calls ungrounded — Ollama retry (cloud SICK)")
            response = await _ask_offline_safe(
                text,
                "I didn't quite follow — could you say that again?",
                timeout=10.0,
                person_name=person_name,
                conversation_history=history,
                language=_detected_lang,
                system_note=_system_note_retry,
            )
        response_streamed = False

    # ── Layer 1: History override for action tools ────────────────────────────
    # When an action tool executed successfully (not a no-op), the LLM's
    # streamed text may be wrong filler. Replace `response` with a canonical
    # acknowledgment BEFORE writing to history to prevent history poisoning and
    # infinite repeat loops on subsequent turns.
    # Bug Q: canonical ack fires ONLY for effective tool calls, never for
    # no-ops — writing "Got it, I'll go by Kara" to history on a redundant
    # call had the LLM re-issue the tool on the next turn (feedback loop).
    # Do NOT re-speak — response_streamed stays True so speak() is skipped.
    if _any_tool_effective:
        _override_tool = next(
            (tc["name"] for tc in tool_calls
             if tc["name"] in HISTORY_OVERRIDE_TOOLS
             and _tool_results.get(tc["name"]) == "handled"),
            None,
        )
        if _override_tool == "update_system_name":
            response          = f"Got it, I'll go by {_active_system_name}."
            response_streamed = False  # stop_audio() cut the stream — must speak canonical ack
        elif _override_tool == "update_person_name":
            _post_tool_snap = _session_store.peek_snapshot(person_id)
            _ack_name = _post_tool_snap.person_name if _post_tool_snap is not None else person_name
            response          = f"Got it, {_ack_name}."
            response_streamed = False  # stop_audio() cut the stream — must speak canonical ack

    # ── Tool-only fallback: LLM called a tool but returned no text ───────────
    # If tools returned "handled" / "handled_noop", skip the tool-specific
    # fallback. But still fall through to the generic empty-response fallback
    # below — silence is NEVER OK.
    if not response and tool_calls and not (_any_tool_effective or _any_tool_noop):
        for tc in tool_calls:
            fb = _TOOL_FALLBACKS.get(tc["name"], "")
            if fb:
                response          = fb
                response_streamed = False
                break

    # ── Empty response fallback ───────────────────────────────────────────────
    # ABSOLUTE LAST RESORT: if response is STILL empty after all tool handling,
    # speak something. Silence is never acceptable — the user is waiting.
    if not response:
        response          = "Sorry, I missed that. Could you say it again?"
        response_streamed = False

    # ── Update in-memory conversation name if it changed ─────────────────────
    # session dict may have been updated by update_person_name tool
    _post_tool_snap = _session_store.peek_snapshot(person_id)
    effective_name = _post_tool_snap.person_name if _post_tool_snap is not None else person_name

    # Session 113 Part 1 — resolve the ADDRESS DECISION marker parsed by
    # _token_gen into the addressed_to field. TTS already played without
    # the marker (stripped in _token_gen); this only affects the history
    # field and, through it, Session 111's cross-person excerpt rendering.
    addressed_to = _resolve_addressed_to(
        _addr_override[0], _session_store.peek_all_snapshots(), effective_name,
    )

    # ── History + persistence ──────────────────────────────────────────────────
    # Session 111 Criticals #2 + #3 + HIGH timestamps — each message gets:
    #   - ts:           wall-clock write time (drives HIGH-timestamps excerpt
    #                   format + Critical #2 session-boundary filtering)
    #   - addressed_to: assistant-only; names the person the assistant was
    #                   replying to. Critical #3: 4-person rooms need
    #                   unambiguous "you [to Alice]: ..." format instead of
    #                   the previous "you: ..." where the target was implied
    #                   by the containing session dict. Session 113 Part 1
    #                   populates this from the LLM's [addressing:X] marker
    #                   when multi-person (falls back to effective_name).
    _now_ts = time.time()
    history.append({
        "role":    "user",
        "content": text,
        "ts":      _now_ts,
    })
    history.append({
        "role":         "assistant",
        "content":      response,
        "ts":           _now_ts,
        "addressed_to": addressed_to,
    })
    # Enforce in-session history cap: load_conversation_history() caps at
    # CONVERSATION_HISTORY_LIMIT turns on DB load, but in-session accumulation
    # is unbounded.  Trim here so the LLM never sees more than the limit.
    # Trim from the front (oldest turns) so recent context is preserved.
    _max_msgs = CONVERSATION_HISTORY_LIMIT * 2   # 2 messages per turn
    if len(history) > _max_msgs:
        history = history[-_max_msgs:]
    _conversation[person_id] = history

    # During an identity-disputed session, skip persistent logging — the turns
    # may belong to someone who is NOT the sensor-matched person, and persisting
    # them under the sensor's pid would permanently poison their conversation
    # history. In-memory `_conversation[pid]` keeps the turns for the current
    # session only; they evaporate on session close.
    _is_disputed_session = _is_disputed(person_id)
    # Session 112 Part 1 — pass room_session_id into log_turn so persisted
    # rows carry the Session 107 Phase 3A.6 column that 3B retrieval will
    # group on. None is acceptable (backward-compat); room_session_id is
    # stamped on session dict at _open_session time.
    _room_sid = _ct_snap.room_session_id if _ct_snap is not None else None
    if db and not _is_disputed_session:
        db.log_turn(person_id, "user",      text, room_session_id=_room_sid,
                    audience_ids=[person_id])
        db.log_turn(person_id, "assistant", response, room_session_id=_room_sid,
                    audience_ids=[person_id])
        # Wake brain agent immediately — extraction runs during TTS so facts
        # are in brain.db before the user speaks their next turn.
        if _brain_orchestrator:
            _brain_orchestrator.notify()
    elif _is_disputed_session:
        print(f"[Pipeline] Skipping log_turn for disputed session {person_id} — "
              f"turns stay in-memory only until identity resolves.")

    # ── Identity scoring for stranger sessions ────────────────────────────────
    # Fast keyword-matching against social mentions — no API calls.
    # Accumulates confidence across turns; thresholds drive the next turn's hint.
    if is_stranger and _brain_orchestrator:
        _id_hit = _brain_orchestrator.score_stranger_identity(
            _conversation.get(person_id, [])
        )
        if _id_hit and _id_hit["confidence"] >= IDENTITY_SOFT_THRESHOLD:
            _identity_hints[person_id] = _id_hit
            _id_conf = _id_hit["confidence"]
            _id_name = _id_hit["name"]
            if _id_conf >= IDENTITY_AUTO_THRESHOLD:
                # Bug G4 (2026-04-22 live run): auto-confirm promotion must
                # also require user-text self-identification, not just a
                # high score. A stranger whose conversation pattern-matches
                # a household member (e.g. mentions the best friend's name
                # often) could otherwise be promoted to that member's
                # identity — knowledge graph corruption attack vector.
                # AND-gate: score ≥ threshold AND user-text matches. False
                # negative costs one extra turn ("my name is X"); false
                # positive leaks a different person's facts.
                # Session 86 P1.7b: classifier-first; regex fallback on
                # classifier unavail. Auto-confirm treats the promotion as
                # an implicit assign_own_name so we can reuse the same gate.
                from core.config import INTENT_FALLBACK_TO_REGEX
                _ac_allowed: bool
                if _intent_sidecar is not None:
                    _ac_allow, _ac_reason = _intent_allows(
                        tool_name="update_person_name",
                        turn_intent=_intent_sidecar.get("turn_intent") or "",
                        confidence=float(_intent_sidecar.get("confidence") or 0.0),
                        extracted_value=_intent_sidecar.get("extracted_value"),
                        user_text=text,
                        tool_args={"name": _id_name},
                    )
                    _ac_allowed = _ac_allow
                    _log_intent_divergence(
                        tool_name="auto_confirm_promotion",
                        sidecar=_intent_sidecar,
                        gate_decision=("allow" if _ac_allow else f"reject: {_ac_reason}"),
                        user_text=text, person_id=person_id,
                    )
                    if not _ac_allow:
                        print(
                            f"[Identity] Auto-confirm HELD — classifier reject: "
                            f"{_ac_reason}; score={_id_conf:.2f}"
                        )
                elif INTENT_FALLBACK_TO_REGEX:
                    _ac_allowed = _user_text_gate_passes(text, _id_name, PERSON_NAME_ASSIGN_PATTERNS)
                    _log_intent_divergence(
                        tool_name="auto_confirm_promotion",
                        sidecar=None,
                        gate_decision=("regex_fallback_allow" if _ac_allowed else "regex_fallback_reject"),
                        user_text=text, person_id=person_id,
                    )
                    if not _ac_allowed:
                        print(
                            f"[Identity] Auto-confirm HELD — score {_id_conf:.2f} but user "
                            f"did not self-ID as '{_id_name}'; waiting for explicit confirmation"
                        )
                else:
                    # Both unavailable — HOLD is safer than auto-promote. This
                    # diverges from the mutation-tool both_unavailable policy
                    # (allow-with-warning) because auto-confirm runs on every
                    # stranger turn, so a false-positive promotion is worse
                    # than a one-turn delay.
                    _ac_allowed = False
                    print(
                        f"[Identity] Auto-confirm HELD — classifier unavailable "
                        f"AND fallback disabled; safer to hold for explicit confirm"
                    )
                    _log_intent_divergence(
                        tool_name="auto_confirm_promotion",
                        sidecar=None,
                        gate_decision="both_unavailable_hold",
                        user_text=text, person_id=person_id,
                    )
                if _ac_allowed:
                    # Auto-confirm: update faces.db, run full brain promotion chain
                    _old_name = person_name  # capture before any update
                    db.update_person_name(person_id, _id_name)
                    _invalidate_bf_cache()  # Session 115 Fix 2 — auto-confirm rename
                    db.update_person_type(person_id, "known")
                    # Retroactively fix old name in in-memory history (mirrors tool path)
                    _old_pat = re.compile(r'\b' + re.escape(_old_name) + r'\b', re.IGNORECASE)
                    for _msg in _conversation.get(person_id, []):
                        _msg["content"] = _old_pat.sub(_id_name, _msg["content"])
                    if _brain_orchestrator:
                        _brain_orchestrator.on_identity_confirmed(person_id, _old_name, _id_name)
                    if _session_store.peek_snapshot(person_id) is not None:
                        try:
                            _loop = asyncio.get_running_loop()
                            _loop.create_task(_session_store.rename(person_id, _id_name))
                            _loop.create_task(_session_store.promote_type(person_id, "known"))
                            _loop.create_task(_session_store.set_cached_prefix(person_id, None))
                            _loop.create_task(_session_store.set_waiting_for_name(person_id, False))
                        except RuntimeError:
                            pass  # OPTIONAL
                    _identity_hints.pop(person_id, None)
                    print(f"[Identity] Auto-confirmed: {_id_name} (conf={_id_conf:.2f})")

    _set_state(PipelineState.SPEAKING, effective_name)
    if response and not response_streamed:
        await speak(response, language=_detected_lang)

    print(f"[Pipeline] Turn end {_now_log_ts()}: {effective_name} — {len(response)} chars")
    return ("continue", None)


async def _warm_pyannote_via_dedicated_executor(
    loop: asyncio.AbstractEventLoop, loader
) -> None:
    """Warm pyannote on Item 13's dedicated executor thread.

    Loading on the same thread that serves diarize() calls means any
    thread-local CUDA context is set up before the first real call.
    """
    try:
        t = time.time()
        await loop.run_in_executor(voice_mod.get_diarize_executor(), loader)
        print(f"[Warmup] pyannote ready — {time.time() - t:.2f}s")
    except Exception as e:
        print(f"[Warmup] pyannote failed (non-fatal): {e!r}")


async def _warmup_models(loop: asyncio.AbstractEventLoop) -> None:
    """Pre-load lazy models so the first user turn pays no cold-start cost.

    Already-eager models (RetinaFace, AdaFace, MiniFASNet, Whisper, Kokoro,
    Emotion) are not touched — they're loaded earlier in run().
    E5 has its own warmup block (S120); this covers pyannote + ECAPA.
    """
    print("[Warmup] starting model warmup pass...")
    overall_t0 = time.time()

    async def _warm(label: str, loader) -> None:
        try:
            t = time.time()
            await loop.run_in_executor(None, loader)
            print(f"[Warmup] {label} ready — {time.time() - t:.2f}s")
        except Exception as e:
            print(f"[Warmup] {label} failed (non-fatal): {e!r}")

    tasks = [
        # Pyannote diarization — lazy per S88; uses Item 13's dedicated executor
        _warm_pyannote_via_dedicated_executor(loop, voice_mod._load_pyannote_pipeline),
        # ECAPA speaker embedder — load_speaker_embedder is idempotent if already loaded
        _warm("ECAPA", voice_mod.load_speaker_embedder),
    ]

    await asyncio.gather(*tasks, return_exceptions=True)
    print(f"[Warmup] complete — {time.time() - overall_t0:.2f}s total")


async def run():
    """Main pipeline loop."""
    global _pipeline_state, \
           _detected_lang, _last_face_seen, _shutdown_event, _active_system_name, \
           _cloud_recovered, _brain_orchestrator, _yolo_frame_counter, \
           _latest_yolo_detections, _yolo_last_ran, _vision_last_heartbeat, \
           _last_user_speech_at, _last_silent_update, \
           _persons_in_frame, _vision_face_scan_last, \
           _vision_prev_det_count, _ambient_wake_pending

    # ── Privilege-table integrity check ───────────────────────────────────────
    # Fail-closed: every tool the brain can see in its TOOLS list MUST have a
    # TOOL_PRIVILEGES entry, else callers get silently blocked at runtime. This
    # assertion fires at launch so missing entries are impossible to miss.
    from core.brain import TOOLS as _BRAIN_TOOLS
    _tool_names = {t["function"]["name"] for t in _BRAIN_TOOLS}
    _missing = _tool_names - set(TOOL_PRIVILEGES)
    assert not _missing, (
        f"TOOL_PRIVILEGES missing entries for: {sorted(_missing)}. "
        f"Every tool in brain.TOOLS must have a privilege row in core/config.py — "
        f"add them before launch."
    )

    # ── Shutdown event (must be created inside the running loop) ──────────────
    _shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    # ── KAIROS silence/cooldown clocks — initialize to now so Kairos doesn't fire
    # immediately at startup before the user has said anything. Without this,
    # _last_user_speech_at=0.0 makes the silence gate pass on the very first tick.
    global _last_user_speech_at, _last_kairos_at
    _last_user_speech_at = time.time()
    _last_kairos_at      = time.time()

    _sigint_count = 0

    def _request_shutdown(signum=None, frame=None):
        """Sync-safe handler: schedules shutdown on first press, force-exits on second.
        The force-exit path handles the case where the loop is stuck in a long
        blocking await (e.g. listen_and_transcribe up to 30s) and won't respond."""
        nonlocal _sigint_count
        _sigint_count += 1
        if _sigint_count == 1:
            print("\n[Pipeline] Ctrl+C received — shutting down gracefully...")
            loop.call_soon_threadsafe(_shutdown_event.set)
        else:
            print("\n[Pipeline] Forced exit.")
            os._exit(1)

    signal.signal(signal.SIGINT, _request_shutdown)
    if sys.platform != "win32":
        # add_signal_handler is asyncio-native and safe on Linux/macOS (Jetson).
        # Not available on Windows ProactorEventLoop.
        loop.add_signal_handler(signal.SIGTERM, _shutdown_event.set)

    print("[Pipeline] Starting...")
    state.write(mode="starting")

    camera          = Camera(CAMERA_INDEX)
    detector        = FaceDetector()
    embedder        = FaceEmbedder()
    db              = FaceDB()
    temporal_buffer = TemporalEmbeddingBuffer(max_frames=5)
    global _face_db_ref
    _face_db_ref    = db  # Obs 1: module-level helpers (e.g. _open_session) read DB for voice count fallback
    _bf_row = _get_best_friend_cached(db)
    _bf_id  = _bf_row["id"] if _bf_row else None

    # Load system identity — name given by user persists across sessions.
    # Guard: reject any invalid/placeholder names that may have been stored by a misfiring tool.
    _loaded_name = db.get_system_identity("system_name") or DEFAULT_SYSTEM_NAME
    if _loaded_name.lower() in _INVALID_SYSTEM_NAMES:
        print(f"[Pipeline] System name '{_loaded_name}' is invalid — resetting to default.")
        db.set_system_identity("system_name", DEFAULT_SYSTEM_NAME, set_by="system", note="auto-reset invalid name")
        _active_system_name = DEFAULT_SYSTEM_NAME
    else:
        _active_system_name = _loaded_name
    if _active_system_name != DEFAULT_SYSTEM_NAME:
        print(f"[Pipeline] System name: {_active_system_name}")

    print("[Pipeline] Preloading audio models...")
    preload_models()

    # Load voice recognizer and build in-memory gallery from DB
    voice_mod.load_speaker_embedder()
    _voice_gallery.update(db.load_voice_profiles())
    _voice_gallery_sizes.update(db.load_voice_profile_sizes())
    print(f"[Voice] Gallery loaded — {len(_voice_gallery)} person(s) with voice profiles")

    # Anti-spoofing — optional MiniFASNet liveness gate for enrollment + recognition
    global _anti_spoof_checker
    if ANTISPOOFING_ENABLED:
        _anti_spoof_checker = AntiSpoofChecker(threshold=ANTISPOOFING_THRESHOLD)

    # Emotion agents — per-person dict; preload the shared HuggingFace pipeline so
    # the first conversation turn isn't blocked by the 15-25ms model-load.
    global _emotion_agents
    _emotion_agents = {}
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, EmotionAgent()._ensure_loaded)

    # Spec 2 — warm up the local E5 embedder so the first classifier call
    # returns in ~30ms instead of ~4600ms (cold model-load latency).
    try:
        from core.classifier_graph import _get_embedding_agent as _cg_get_agent
        _e5_agent = _cg_get_agent()
        if _e5_agent is not None and hasattr(_e5_agent, "_load"):
            _t0_e5 = time.perf_counter()
            await loop.run_in_executor(None, _e5_agent._load)
            print(f"[classifier_graph] E5 ready — {time.perf_counter() - _t0_e5:.1f}s")
    except Exception as _e5_warmup_err:
        print(f"[classifier_graph] E5 warmup skipped: {_e5_warmup_err!r}")

    # Wave 3 Item 14 — warm pyannote + ECAPA in parallel so first-turn pays no
    # cold-start cost. Camera/audio init overlaps with this (~1-2s absorption).
    await _warmup_models(loop)

    # Brain agent — async, decoupled, never blocks the conversation
    _brain_orchestrator = BrainOrchestrator(_shutdown_event)
    _brain_orchestrator.set_system_name(_active_system_name)
    _brain_task = asyncio.create_task(_brain_orchestrator.run())

    # Anti-spoof observability: stamp state.json and watchdog alert when disabled.
    _as_enabled = _anti_spoof_checker is not None and _anti_spoof_checker.available
    state.set_persistent("anti_spoof_enabled", _as_enabled)
    if ANTISPOOFING_ENABLED and not _as_enabled:
        print("[SECURITY] WARNING: Anti-spoofing DISABLED — photo / screen-replay attacks will "
              "succeed. Install silent-face-anti-spoofing to enable.")
        _brain_orchestrator.report_antispoof_disabled()
    elif not ANTISPOOFING_ENABLED:
        print("[Security] Anti-spoofing disabled by config (ANTISPOOFING_ENABLED=False)")
    asyncio.create_task(_dream_loop(db))
    global _health_log_task
    _health_log_task = asyncio.create_task(_health_log_loop(asyncio.get_event_loop()))

    # YOLO spatial memory — disabled via VISION_YOLO_ENABLED flag
    global _yolo_model, _yolo_executor
    if VISION_YOLO_ENABLED and _YOLO_AVAILABLE:
        try:
            _yolo_model = _YOLO(VISION_YOLO_MODEL, verbose=False)
            # Isolated single-thread pool — prevents PyTorch GIL from stalling
            # httpx async I/O during LLM streaming in the conversation loop.
            _yolo_executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="yolo"
            )
            print(f"[Pipeline] YOLO object detection ready ({VISION_YOLO_MODEL})")
        except Exception as e:
            print(f"[Pipeline] YOLO load failed — spatial memory disabled: {e}")

    print("[Pipeline] All systems ready. Watching...")
    state.write(mode="watching")

    # Camera warmup — intentional one-time exception to the single-reader invariant.
    # Windows DirectShow produces black/garbage frames for the first ~200ms after
    # open(). We discard them here BEFORE starting the background loop so the loop's
    # first captured frame is real. The bg loop hasn't started yet — no race condition.
    for _ in range(5):
        camera.read()
        await asyncio.sleep(0.05)

    # Single-reader design: from this point on, background loop is the ONLY camera reader.
    # Main loop reads from _latest_vision_frame (written by this task).
    # Eliminates thread-unsafe concurrent cv2.VideoCapture reads on Windows.
    _vis_bg_task = asyncio.create_task(
        _background_vision_loop(camera, detector, embedder, temporal_buffer, db)
    )
    await asyncio.sleep(0.1)  # let background loop capture its first frame

    _null_frame_streak  = 0
    _reconnect_delay    = 2.0   # seconds; doubles each failed attempt, caps at 60
    _last_silent_update = 0.0   # throttle: write silent obs at most every 5s

    # Prune stale silent observations at startup (runs once, fast)
    db.prune_silent_observations()

    try:
        while not _shutdown_event.is_set():
            # ── Dashboard enroll request ───────────────────────────────────────
            if _pipeline_state == PipelineState.WATCHING and ENROLL_REQUEST_FILE.exists():
                try:
                    req  = json.loads(ENROLL_REQUEST_FILE.read_text())
                    name = req.get("name", "").strip()
                    ENROLL_REQUEST_FILE.unlink(missing_ok=True)
                except Exception as e:
                    print(f"[Pipeline] Bad enroll request: {e}")
                    ENROLL_REQUEST_FILE.unlink(missing_ok=True)
                    name = ""

                if name:
                    bf = _get_best_friend_cached(db)
                    if bf:
                        print(f"[Pipeline] Enroll blocked — best friend already enrolled: {bf['name']}")
                        result: dict = {"success": False, "error": f"Best friend already enrolled: {bf['name']}"}
                        fd, tmp = tempfile.mkstemp(dir=FACES_DIR, suffix=".tmp")
                        try:
                            with os.fdopen(fd, "w") as f:
                                json.dump(result, f)
                            os.replace(tmp, ENROLL_RESULT_FILE)
                        except Exception as e:
                            print(f"[Pipeline] Failed to write enroll result: {e}")
                            try:
                                os.unlink(tmp)
                            except Exception as _cleanup_e:
                                # Session 111 HIGH fix — was silent `except: pass`;
                                # log so tmp-file leaks become visible to operators.
                                print(f"[Pipeline] enroll tmp cleanup failed: {_cleanup_e!r}")
                    else:
                        _set_state(PipelineState.ENROLLING, name)
                        try:
                            await enrollment_flow(name, camera, detector, embedder, db, person_type='best_friend')
                            result = {"success": True, "name": name}
                        except Exception as e:
                            print(f"[Pipeline] Enrollment error: {e}")
                            result = {"success": False, "error": str(e)}
                        fd, tmp = tempfile.mkstemp(dir=FACES_DIR, suffix=".tmp")
                        try:
                            with os.fdopen(fd, "w") as f:
                                json.dump(result, f)
                            os.replace(tmp, ENROLL_RESULT_FILE)
                        except Exception as e:
                            print(f"[Pipeline] Failed to write enroll result: {e}")
                            try:
                                os.unlink(tmp)
                            except Exception as _cleanup_e:
                                # Session 111 HIGH fix — parallel site, same reasoning.
                                print(f"[Pipeline] enroll tmp cleanup failed: {_cleanup_e!r}")
                        _set_state(PipelineState.WATCHING)

            # ── Dashboard factory reset request ───────────────────────────────
            if _pipeline_state == PipelineState.WATCHING and RESET_REQUEST_FILE.exists():
                RESET_REQUEST_FILE.unlink(missing_ok=True)
                print("[Reset] Factory reset triggered — wiping all data...")
                state.write(mode="resetting")

                # Step 1: clear all in-memory state while connections are still valid
                _brain_orchestrator.wipe()

                # Step 2: close ALL file handles so wipe_all() can delete on Windows
                db.close()  # idempotent; CLEANUP swallow lives in FaceDB.close()
                _brain_orchestrator.close_connections()

                # Step 3: delete all files from disk
                try:
                    wipe_all()
                    reset_ok = True
                except Exception as e:
                    print(f"[Reset] wipe_all error: {e}")
                    reset_ok = False

                # Step 4: re-initialize FaceDB and temporal buffer (creates fresh faces.db)
                db              = FaceDB()
                temporal_buffer = TemporalEmbeddingBuffer(max_frames=5)
                _face_db_ref    = db  # Obs 1: re-point module-level ref after factory reset
                # Session 115 Fix 2 — invalidate bf cache before next read; the
                # FaceDB instance just changed so the cached id() is stale.
                _invalidate_bf_cache()
                _bf_row = _get_best_friend_cached(db)
                _bf_id  = _bf_row["id"] if _bf_row else None

                # Step 5: re-open BrainOrchestrator connections to fresh DB files
                _brain_orchestrator.reopen_connections()

                # Clear all runtime state
                _last_greeted.clear()
                _last_self_update.clear()
                _conversation.clear()
                _voice_gallery.clear()
                _voice_gallery_sizes.clear()
                _sessions_started.clear()
                for _snap_rst in _session_store.peek_all_snapshots():
                    try:
                        _loop = asyncio.get_running_loop()
                        _loop.create_task(_session_store.close_session(_snap_rst.person_id))
                    except RuntimeError:
                        pass  # OPTIONAL
                _scene_block_cache.clear()  # Wave 6 Item 23
                _active_system_name = DEFAULT_SYSTEM_NAME
                _detected_lang      = "en"
                _last_face_seen     = 0.0

                # Write result for the API to read
                result = {"success": reset_ok}
                try:
                    fd, tmp = tempfile.mkstemp(dir=FACES_DIR, suffix=".tmp")
                    with os.fdopen(fd, "w") as f:
                        json.dump(result, f)
                    os.replace(tmp, str(RESET_RESULT_FILE))
                except Exception as e:
                    print(f"[Reset] Failed to write reset result: {e}")

                _set_state(PipelineState.WATCHING)
                print("[Reset] Factory reset complete." if reset_ok else "[Reset] Reset partially failed.")

            frame = _latest_vision_frame if time.monotonic() - _latest_frame_time < 0.5 else None
            if frame is None:
                _null_frame_streak += 1
                if _null_frame_streak >= 30:
                    print(f"[Pipeline] Camera: {_null_frame_streak} consecutive null frames — reconnecting...")
                    state.write(mode="reconnecting")
                    if _brain_orchestrator:
                        _brain_orchestrator.report_camera_null_streak(_null_frame_streak)
                    if camera.reconnect():
                        print("[Pipeline] Camera reconnected.")
                        _null_frame_streak = 0
                        _reconnect_delay   = 2.0
                        state.write(mode="watching")
                        if _brain_orchestrator:
                            _brain_orchestrator.report_camera_recovered()
                    else:
                        print(f"[Pipeline] Camera reconnect failed — retrying in {_reconnect_delay:.0f}s")
                        try:
                            await asyncio.wait_for(_shutdown_event.wait(), timeout=_reconnect_delay)
                        except asyncio.TimeoutError:
                            pass
                        _reconnect_delay = min(_reconnect_delay * 2, 60.0)
                else:
                    await asyncio.sleep(0.1)
                continue

            _null_frame_streak = 0

            # ── YOLO object detection (spatial memory) — disabled when VISION_YOLO_ENABLED=False
            _yolo_frame_counter += 1
            if VISION_YOLO_ENABLED and _yolo_model and _yolo_frame_counter % VISION_DETECT_EVERY == 0:
                _yolo_frame_counter = 0
                try:
                    _yolo_frame = frame
                    yolo_results = await loop.run_in_executor(
                        _yolo_executor, lambda: _yolo_model(_yolo_frame, verbose=False, device="cpu")[0]
                    )
                    all_boxes = yolo_results.boxes
                    yolo_dets = [
                        {
                            "class": yolo_results.names[int(box.cls[0])],
                            "conf":  float(box.conf[0]),
                            "bbox":  tuple(int(v) for v in box.xyxy[0].tolist()),
                        }
                        for box in all_boxes
                        if float(box.conf[0]) >= VISION_DETECT_CONF
                    ]
                    if yolo_dets:
                        _latest_yolo_detections = yolo_dets
                        _yolo_last_ran = time.time()
                        det_summary = ", ".join(
                            f"{d['class']}({d['conf']:.2f})" for d in yolo_dets
                        )
                        print(f"[YOLO] Detected: {det_summary}")
                    elif all_boxes is not None and len(all_boxes) > 0:
                        top = max(all_boxes, key=lambda b: float(b.conf[0]))
                        print(f"[YOLO] Scan: best={yolo_results.names[int(top.cls[0])]}({float(top.conf[0]):.2f}), total={len(all_boxes)} raw — all below conf={VISION_DETECT_CONF}")
                    else:
                        print(f"[YOLO] Scan: 0 raw detections")
                    if yolo_dets and _brain_orchestrator:
                        h, w = frame.shape[:2]
                        _brain_orchestrator.record_object_sightings(
                            yolo_dets,
                            frame_w=w,
                            frame_h=h,
                            person_context=_primary_person_name(),
                        )
                except Exception as _yolo_err:
                    print(f"[Pipeline] YOLO error: {_yolo_err}")

            # ── Detect faces ──────────────────────────────────────────────────
            detections = detector.detect(frame)
            visible_people = []
            # Session 113 Part 2 — collect known-person greetings for this
            # scan cycle. Drained after the for-det loop so LLM ordering
            # can run across all simultaneous arrivals. Each entry carries
            # everything needed to actually speak the greeting + briefing.
            _pending_known_greets: list[dict] = []

            for det in detections:
                x1, y1, x2, y2 = det.bbox
                face_crop = frame[y1:y2, x1:x2]
                if face_crop.size == 0:
                    continue

                # V1: quality gate — skip blurry/tiny/dark crops
                quality = face_quality_score(face_crop)
                if quality < FACE_QUALITY_RECOGNITION:
                    continue

                # V2: yaw gate — skip side-on faces (unreliable embeddings)
                if det.landmarks is not None:
                    yaw = estimate_yaw_from_landmarks(det.landmarks, det.bbox)
                    if abs(yaw) > 60.0:
                        continue

                # V3: pool embedding across frames for stability
                raw_embedding = embedder.embed(face_crop)
                embedding     = temporal_buffer.add_and_pool(det.bbox, raw_embedding, track_id=det.track_id)

                # V4: adaptive threshold — stricter for low-quality crops
                threshold = adaptive_threshold(quality, RECOGNITION_THRESHOLD)
                # Pool-size gate: shallow pool (< 3 frames) → noisy embedding → demand stronger match
                if det.track_id is not None and temporal_buffer.pool_depth(det.track_id) < 3:
                    threshold += 0.05
                person_id, person_name, conf = db.recognize(embedding, threshold)
                directly_recognized = person_id is not None

                if directly_recognized:
                    # Record identity for this SORT track so brief occlusion doesn't lose it
                    if det.track_id is not None:
                        _track_identity[det.track_id] = person_id
                else:
                    print(f"[Vision] Face score={conf:.3f} (need ≥{threshold:.3f}) — unrecognized")
                    # Silent observation: accumulate face data without engagement.
                    if not _session_store.peek_all_snapshots():
                        _maybe_record_silent_obs(embedding, det.bbox, frame.shape[1], frame.shape[0], db)

                    # Track-continuity: if this SORT track was previously recognized as a
                    # specific person, maintain that identity across brief occlusion.
                    # Replaces soft-match (which mapped any unrecognized face to the current
                    # session holder — the gallery-poisoning root cause).
                    if det.track_id is not None:
                        _tracked_pid = _track_identity.get(det.track_id)
                        if _tracked_pid and _session_store.peek_snapshot(_tracked_pid) is not None:
                            person_id   = _tracked_pid
                            _tc_snap = _session_store.peek_snapshot(_tracked_pid)
                            person_name = _tc_snap.person_name if _tc_snap is not None else _tracked_pid
                            print(f"[Vision] Track-continuity: {person_name} (track={det.track_id}, score={conf:.3f})")

                det.embedding        = embedding
                det.person_id        = person_id
                det.person_name      = person_name
                det.recognition_conf = conf

                if person_id:
                    visible_people.append(person_name)

                    # ── Self-update gallery (direct recognition only) ─────────
                    # Only fire when FAISS directly matched (conf ≥ threshold).
                    # Track-continuity restorations are excluded — their score is
                    # below threshold and writing them would re-introduce gallery drift.
                    # Anti-spoof LIVE is required — refusing when unavailable (fail-closed)
                    # since a poisoned frame can lock in permanently via gallery drift.
                    if directly_recognized and quality >= FACE_QUALITY_SELF_UPDATE:
                        last = _last_self_update.get(person_id, 0)
                        if time.time() - last >= SELF_UPDATE_COOLDOWN and conf >= SELF_UPDATE_THRESHOLD:
                            _anti_spoof_ok = (
                                _anti_spoof_checker is not None
                                and getattr(_anti_spoof_checker, "available", False)
                                and verify_live(frame, det.bbox, _anti_spoof_checker)
                            )
                            if not _anti_spoof_ok:
                                # Fail-closed: skip the write when liveness is unavailable or failed.
                                # Avoid log spam by throttling with the same cooldown.
                                _last_self_update[person_id] = time.time()
                                _prune_dict(_last_self_update)
                            else:
                                added = db.add_embedding(person_id, embedding, "recognition_update", conf)
                                if added:
                                    _last_self_update[person_id] = time.time()
                                    _prune_dict(_last_self_update)
                                    print(f"[Pipeline] {person_name} gallery updated — new angle stored ({db.embedding_count(person_id)}/{MAX_EMBEDDINGS} face embeddings)")

                    # ── Greet known person or returning stranger ──────────────
                    if _pipeline_state == PipelineState.WATCHING:
                        last_greeted = _last_greeted.get(person_id, 0)
                        # _session_store.peek_snapshot(person_id) being non-None means their session is still
                        # live (e.g., returned to WATCHING after "no speech"). In that
                        # case never re-greet even if the cooldown has technically expired
                        # during a long conversation — the session never actually ended.
                        if (time.time() - last_greeted >= GREET_COOLDOWN
                                and _session_store.peek_snapshot(person_id) is None):
                            # Consume the ambient wake signal unconditionally — whether
                            # anti-spoof blocks or passes, background loop must not re-fire.
                            _ambient_wake_pending.discard(person_id)
                            # Anti-spoofing: check liveness before greeting to block
                            # photo/screen attacks. Only checked on the greeting frame.
                            if not verify_live(frame, det.bbox, _anti_spoof_checker):
                                print(f"[Pipeline] Anti-spoof: BLOCKED {person_name} — liveness check failed")
                                continue
                            if _anti_spoof_checker is not None and getattr(_anti_spoof_checker, "available", False):
                                print(f"[Pipeline] Anti-spoof: PASSED {person_name}")
                            else:
                                print(f"[Pipeline] Anti-spoof: DISABLED {person_name} (no liveness check performed)")
                            _last_greeted[person_id] = time.time()
                            _prune_dict(_last_greeted)
                            # Fetch DB-sourced person_type BEFORE opening the session so it
                            # lands in the dict at creation — closes the race window where
                            # a best_friend could be mis-gated as stranger via the fail-safe
                            # fallback in the privilege gate.
                            person_type = db.get_person_type(person_id) or "known"
                            # engagement_gate_passed=True — face recognition just
                            # succeeded AND anti-spoof was live. Seeds bootstrap
                            # credits so the voice profile can grow on turn 1.
                            _open_session(
                                person_id, person_name, "face",
                                person_type=person_type,
                                engagement_gate_passed=True,
                            )

                            gdata        = db.get_greeting_data(person_id)
                            last_seen_ts = gdata["last_seen"] if gdata else None
                            lang         = gdata["preferred_language"] if gdata else "en"

                            if person_type == "stranger":
                                # ── Returning stranger ────────────────────────
                                db.update_last_seen(person_id)
                                _sessions_started.add(person_id)
                                # Per-person EmotionAgent: kept alive across sessions; 90-second TTL
                                # in get_dominant_emotion() handles stale entries automatically.
                                _conversation[person_id] = db.load_conversation_history(person_id)
                                # person_type was seeded by _open_session; just add the system-name gate.
                                if _session_store.peek_snapshot(person_id) is not None:
                                    try:
                                        _loop = asyncio.get_running_loop()
                                        _loop.create_task(_session_store.set_waiting_for_name(person_id, STRANGER_REQUIRE_SYSTEM_NAME))
                                    except RuntimeError:
                                        pass  # OPTIONAL
                                if STRANGER_REQUIRE_SYSTEM_NAME:
                                    print(f"[Pipeline] Stranger {person_id} detected — waiting for system name '{_active_system_name}'")
                                else:
                                    greeting = await generate_greeting(person_name, last_seen_ts, lang)
                                    await speak(greeting, language=lang)
                            else:
                                # ── Known enrolled person OR best_friend ──────
                                # person_type was seeded by _open_session from the
                                # DB value. Seed identity_evidence (Step 3) with the
                                # recognition we just passed + live anti-spoof so the
                                # voice accumulation gate sees a real witness on turn 1.
                                # Dual-write voice_face_confirmed=True as a compat shim
                                # for any code still reading the old boolean — remove in
                                # a follow-up once all readers migrate to identity_evidence.
                                if _session_store.peek_snapshot(person_id) is not None:
                                    try:
                                        _loop = asyncio.get_running_loop()
                                        _loop.create_task(_session_store.mark_voice_face_confirmed(person_id))
                                        _loop.create_task(_session_store.set_voice_only_origin(person_id, False))
                                    except RuntimeError:
                                        pass  # OPTIONAL
                                try:
                                    _loop = asyncio.get_running_loop()
                                    _loop.create_task(_session_store.update_face_seen(
                                        person_id, conf=conf, ts=time.time(), anti_spoof_live=True))
                                except RuntimeError:
                                    pass  # OPTIONAL
                                state.write(
                                    mode="speaking",
                                    current_person=person_name,
                                    current_person_id=person_id,
                                    visible_people=visible_people
                                )
                                greeting = await generate_greeting(person_name, last_seen_ts, lang)
                                db.update_last_seen(person_id)
                                _sessions_started.add(person_id)
                                history_from_db = db.load_conversation_history(person_id)
                                # Prepend anonymous visitor sightings
                                sightings = db.get_recent_visitor_sightings()
                                if sightings:
                                    lines = []
                                    for s in sightings:
                                        dt = datetime.datetime.fromtimestamp(s["ts"])
                                        label = dt.strftime("%Y-%m-%d %A %H:%M")
                                        note = f" ({s['note']})" if s["note"] else ""
                                        lines.append(f"- {label}{note}")
                                    sighting_note = (
                                        "Visitor log — unfamiliar faces I have seen (not enrolled):\n"
                                        + "\n".join(lines)
                                    )
                                    history_from_db = [
                                        {"role": "user",      "content": f"[Visitor log]\n{sighting_note}"},
                                        {"role": "assistant", "content": "Noted."},
                                    ] + history_from_db
                                # Prepend named stranger visits since owner was last here
                                if last_seen_ts:
                                    stranger_visits = db.get_stranger_visits_since(last_seen_ts)
                                    if stranger_visits:
                                        sv_lines = []
                                        for sv in stranger_visits:
                                            dt = datetime.datetime.fromtimestamp(sv["last_seen"])
                                            label = dt.strftime("%Y-%m-%d %H:%M")
                                            name_str = (
                                                sv["name"]
                                                if sv["name"] != "visitor"
                                                else f"an unnamed visitor (code: {sv['id'][-6:]})"
                                            )
                                            sv_lines.append(f"- {label}: {name_str}")
                                        stranger_note = (
                                            "People who spoke with me while you were away:\n"
                                            + "\n".join(sv_lines)
                                        )
                                        history_from_db = [
                                            {"role": "user",      "content": f"[Visitor conversations]\n{stranger_note}"},
                                            {"role": "assistant", "content": "Noted. I'll mention it when you ask."},
                                        ] + history_from_db
                                _conversation[person_id] = history_from_db

                                # ── Briefing for best friend after long absence ─
                                _briefing_task = None
                                if (
                                    person_type == "best_friend"
                                    and _brain_orchestrator
                                    and last_seen_ts
                                    and (time.time() - last_seen_ts) >= BRIEFING_MIN_ABSENCE
                                ):
                                    _briefing_task = asyncio.create_task(
                                        _brain_orchestrator.get_briefing(person_id, last_seen_ts)
                                    )

                                # Session 113 Part 2 — defer the speak()
                                # into the pending queue so we can reorder
                                # across multiple simultaneous known-person
                                # arrivals via LLM. Single-person case is
                                # untouched behaviorally: pending list of
                                # length 1 drains in detection order (which
                                # is the only order possible).
                                _pending_known_greets.append({
                                    "person_name":   person_name,
                                    "person_id":     person_id,
                                    "greeting":      greeting,
                                    "lang":          lang,
                                    "briefing_task": _briefing_task,
                                })

            # Session 113 Part 2 — drain pending known-person greetings.
            # When 2+ entries and BATCH_GREETING_ENABLED, ask the LLM for
            # ordering; otherwise (or on LLM failure) the original append
            # order wins, which is detection order — the pre-S113 behavior.
            if _pending_known_greets:
                if (
                    BATCH_GREETING_ENABLED
                    and len(_pending_known_greets) >= BATCH_GREETING_MIN_PEOPLE
                ):
                    _greet_names = [g["person_name"] for g in _pending_known_greets]
                    _ordered_names = await choose_greeting_order(
                        _greet_names,
                        timeout=BATCH_GREETING_LLM_TIMEOUT_SECS,
                    )
                    _by_name = {g["person_name"]: g for g in _pending_known_greets}
                    _ordered_greets = [
                        _by_name[n] for n in _ordered_names if n in _by_name
                    ]
                    # Safety net: if reordering somehow lost entries, fall
                    # back to the detection order so no one is skipped.
                    if len(_ordered_greets) != len(_pending_known_greets):
                        _ordered_greets = list(_pending_known_greets)
                else:
                    _ordered_greets = list(_pending_known_greets)
                for _g in _ordered_greets:
                    await speak(_g["greeting"], language=_g["lang"])
                    _g_briefing_task = _g.get("briefing_task")
                    if _g_briefing_task is not None:
                        try:
                            briefing = await _g_briefing_task
                            if briefing:
                                print(f"[Pipeline] Briefing: {briefing}")
                                await speak(briefing, language=_g["lang"])
                        except Exception as be:
                            print(f"[Pipeline] Briefing error: {be}")

            # V3: evict stale slots for faces no longer in frame
            active_track_ids = {d.track_id for d in detections if d.track_id is not None}
            temporal_buffer.clear_stale([d.bbox for d in detections], active_track_ids=active_track_ids)

            # ── Unknown face — silent sighting (no greeting) ──────────────────
            # Strangers are not greeted on sight. They engage by addressing
            # the system by name. Only log the sighting once per cooldown.
            grace_expired = time.time() - _last_face_seen > FACE_LOSS_GRACE
            if _pipeline_state == PipelineState.WATCHING and detections and not _session_store.peek_all_snapshots() and grace_expired:
                unknown_key = "unknown"
                last_sighted = _last_greeted.get(unknown_key, 0)
                if time.time() - last_sighted >= GREET_COOLDOWN:
                    _last_greeted[unknown_key] = time.time()
                    _prune_dict(_last_greeted)
                    if not db.list_people():
                        # Empty DB — first time anyone has stood in front of this system
                        await first_boot_flow(camera, detector, embedder, db)
                        # Session 115 Fix 2 — bf was just enrolled by first_boot_flow;
                        # invalidate cache so next read fetches the new row.
                        _invalidate_bf_cache()
                        _bf_row = _get_best_friend_cached(db)
                        _bf_id  = _bf_row["id"] if _bf_row else None
                        _set_state(PipelineState.WATCHING)
                    else:
                        db.log_visitor_sighting()
                        print("[Pipeline] Unknown face detected — logged sighting, waiting for name mention.")

            # ── Update face-seen timestamps for visible sessions ──────────────
            if detections:
                # Keep ambient timer current when no sessions are active.
                if not _session_store.peek_all_snapshots():
                    _last_face_seen = time.time()
                else:
                    # Only update _last_face_seen for faces that belong to active sessions.
                    # A stranger walking in during an active session should NOT reset the timer.
                    for _d in detections:
                        if _d.person_id and _session_store.peek_snapshot(_d.person_id) is not None:
                            _last_face_seen = time.time()
                            try:
                                _loop = asyncio.get_running_loop()
                                _loop.create_task(_session_store.set_last_face_seen(_d.person_id, _last_face_seen))
                            except RuntimeError:
                                pass  # OPTIONAL

            # ── Session expiry — check each active session independently ──────
            if _pipeline_state == PipelineState.WATCHING and _session_store.peek_all_snapshots():
                _expire_stale_sessions()

            # state.write removed here, handled by _set_state and final WATCHING state

            # ── Vision heartbeat — always-on confirmation every 30s ────────────
            global _vision_last_heartbeat_state
            _now = time.time()
            if _now - _vision_last_heartbeat >= 30.0:
                _vision_last_heartbeat = _now
                if visible_people:
                    _hb_who = ", ".join(set(visible_people))
                    _hb_key = f"WATCHING|{_hb_who}"
                elif detections:
                    _hb_who = "unrecognized face detected"
                    _hb_key = "WATCHING|unrecognized"
                else:
                    _hb_who = "no face"
                    _hb_key = "WATCHING|none"
                if _hb_key != _vision_last_heartbeat_state:
                    _vision_last_heartbeat_state = _hb_key
                    print(f"[Vision] Watching — {_hb_who}")

            # ── Listen for speech ─────────────────────────────────────────────
            # Lip tracker: keep bbox current and calibrate baseline while person is at rest.
            if _session_store.peek_all_snapshots() and detections:
                for _det in detections:
                    if _session_store.peek_snapshot(_det.person_id) is not None:
                        _last_active_bbox = _det.bbox
                        if _pipeline_state not in (PipelineState.LISTENING, PipelineState.THINKING):
                            lip_tracker.update_baseline(frame, _det.bbox)
                        break

            # ── Listen for speech even without a face in frame ────────────────
            _ambient_text  = ""
            _ambient_audio = None
            if not _session_store.peek_all_snapshots() and _pipeline_state == PipelineState.WATCHING:
                # Persistent background loop (_vis_bg_task) keeps vision alive — no
                # per-listen task needed here anymore.
                _ambient_text, _, _ambient_audio = await listen_and_transcribe()
                if _ambient_text:
                    print(f"[Pipeline] Voice-first: heard speech — identifying speaker...")
                    # Voice ID
                    v_pid, v_score = voice_mod.identify(
                        _ambient_audio, _voice_gallery, VOICE_RECOGNITION_THRESHOLD
                    )
                    if v_pid:
                        row = db.get_person(v_pid)
                        if row:
                            _v_pt = db.get_person_type(v_pid) or "known"
                            _open_session(v_pid, row["name"], "voice", person_type=_v_pt, voice_confidence=v_score)
                            print(f"[Voice] Identified {row['name']} by voice (score={v_score:.3f})")
                            if v_pid not in _conversation:
                                _conversation[v_pid] = db.load_conversation_history(v_pid)
                    # #15 invariant: session-opening authority comes from (a) a known-voice
                    # match, (b) a known-face match at WATCHING entry, or (c) a stranger
                    # who said the system name. The gate runs first; camera is a
                    # disambiguator only after authority is established.
                    if not _session_store.peek_all_snapshots():
                        if not db.list_people():
                            await first_boot_flow(camera, detector, embedder, db)
                            _set_state(PipelineState.WATCHING)
                            _ambient_text = ""  # first_boot handled it
                        elif _name_heard_in(_ambient_text, _active_system_name)[0]:
                            # Gate PASSED — use camera to attach face identity if available.
                            cam_f = _latest_vision_frame if time.monotonic() - _latest_frame_time < 0.5 else None
                            if cam_f is not None:
                                _best_pid, _best_pname, _best_conf = None, None, 0.0
                                for _d in detector.detect(cam_f):
                                    x1, y1, x2, y2 = _d.bbox
                                    crop = cam_f[y1:y2, x1:x2]
                                    if crop.size == 0:
                                        continue
                                    _emb = embedder.embed(crop)
                                    _pid, _pname, _conf = db.recognize(_emb, RECOGNITION_THRESHOLD)
                                    if _pid and _conf > _best_conf:
                                        if not verify_live(cam_f, _d.bbox, _anti_spoof_checker):
                                            print(f"[Pipeline] Anti-spoof: BLOCKED camera fallback for {_pname}")
                                            continue
                                        _best_pid, _best_pname, _best_conf = _pid, _pname, _conf
                                    elif not _pid:
                                        _maybe_record_silent_obs(_emb, _d.bbox, cam_f.shape[1], cam_f.shape[0], db)
                                if _best_pid:
                                    _best_pt = db.get_person_type(_best_pid) or "known"
                                    _open_session(_best_pid, _best_pname, "voice", person_type=_best_pt)
                                    if _best_pid not in _conversation:
                                        _conversation[_best_pid] = db.load_conversation_history(_best_pid)
                            if not _session_store.peek_all_snapshots():
                                # No face visible or face unrecognized — voice-only stranger
                                _sid = db.add_stranger("visitor")
                                # Session 90 Bug 1 Fix A: this branch OPENS a stranger
                                # session ONLY after the ambient gate confirmed the
                                # user addressed the system by name (``_gate_ok`` path
                                # upstream). That IS an engagement-gate pass — the
                                # same semantics as the in-loop G4 path at line 4783
                                # that grants bootstrap credits after hearing "Kara".
                                # Without ``engagement_gate_passed=True`` here, the
                                # newly-opened session's ``identity_evidence.bootstrap_credits``
                                # stays at 0 (the ``_open_session`` non-gate default),
                                # and every subsequent ``_accumulate_voice`` call
                                # refuses with ``bootstrap=0`` — observed in the
                                # 2026-04-22 multi-convo live run for John's entire
                                # session (turns 1 AND 2 both refused).
                                _open_session(_sid, "visitor", "voice",
                                              person_type="stranger",
                                              engagement_gate_passed=True)
                                _conversation[_sid] = []
                                if _session_store.peek_snapshot(_sid) is not None:
                                    try:
                                        _loop = asyncio.get_running_loop()
                                        _loop.create_task(_session_store.set_waiting_for_name(_sid, False))
                                        _loop.create_task(_session_store.set_voice_only_origin(_sid, True))
                                    except RuntimeError:
                                        pass  # OPTIONAL
                                print(f"[Pipeline] Stranger engaged (voice-only, system addressed) — {_sid}")
                        else:
                            # Gate FAILED — stay silent
                            _ambient_text = ""

            _primary_pid_conv = _primary_person_id()
            if _primary_pid_conv and _pipeline_state == PipelineState.WATCHING:
                # Stay in a tight conversation loop — no camera rescan between turns.
                # Eliminates the SPEAKING → WATCHING → camera+detect+embed → LISTENING
                # round-trip (~150ms) that made each turn feel laggy.

                # Voice-ID / camera-fallback paths skip the face-recognition greeting block.
                # Only run once per session — greeting path already called update_last_seen.
                if _primary_pid_conv not in _sessions_started:
                    db.update_last_seen(_primary_pid_conv)
                    _sessions_started.add(_primary_pid_conv)
                    _last_greeted[_primary_pid_conv] = time.time()  # prevent face-recog re-greet
                    _pp_snap = _session_store.peek_snapshot(_primary_pid_conv)
                    _ppname = _pp_snap.person_name if _pp_snap is not None else _primary_pid_conv
                    print(f"[Pipeline] Conversation started for {_ppname} (voice/camera-fallback path)")

                # Seed the voice session timeout for voice-started sessions
                if _session_store.peek_snapshot(_primary_pid_conv) is not None:
                    _conv_start_ts = time.time()
                    try:
                        _loop = asyncio.get_running_loop()
                        _loop.create_task(_session_store.set_last_spoke_at(_primary_pid_conv, _conv_start_ts))
                    except RuntimeError:
                        pass  # OPTIONAL

                _ppname_conv = _primary_person_name() or _primary_pid_conv
                _set_state(PipelineState.LISTENING, _ppname_conv)
                print(f"[Pipeline] Listening for {_ppname_conv}...")
                # Reset KAIROS silence clock only when a brand-new session just opened.
                # On re-entry after "No speech detected", preserve accumulated silence so
                # Kairos can fire if the person stays silent long enough.
                _kcr_snap = _session_store.peek_snapshot(_primary_pid_conv)
                if _kcr_snap is not None and _kcr_snap.kairos_clock_reset:
                    _last_user_speech_at = time.time()
                    try:
                        _loop = asyncio.get_running_loop()
                        _loop.create_task(_session_store.consume_kairos_reset(_primary_pid_conv))
                    except RuntimeError:
                        pass  # OPTIONAL

                # Persistent _vis_bg_task (started at run() startup) keeps camera
                # running throughout — no separate per-conversation task needed.
                while not _shutdown_event.is_set():
                    # Expire abandoned voice/face sessions (zombies from stranger
                    # fragmentation or face-loss) so room-context stays accurate
                    # even during long active conversations.
                    _expire_stale_sessions()

                    # Resolve current primary person at the top of each inner loop iteration
                    _cur_pid  = _primary_person_id()
                    _cur_name = _primary_person_name() if _cur_pid else None

                    # Pattern 7 — KAIROS: break silence proactively if person is quiet.
                    # Session 112 Part 2: use room-aware selector (prefers
                    # best_friend in multi-person rooms, falls back to
                    # longest-silence speaker). The legacy
                    # `_primary_person_id()` was wrong in rooms where the
                    # most recent speaker wasn't the natural engagement
                    # target (e.g. Jagan listening to Lexi → KAIROS
                    # should engage Jagan, not Lexi).
                    if not _ambient_text:
                        _kairos_pid = _kairos_preferred_speaker(_bf_id)
                        _kairos_name = (
                            (_session_store.peek_snapshot(_kairos_pid).person_name if _session_store.peek_snapshot(_kairos_pid) is not None else _kairos_pid)
                            if _kairos_pid and _session_store.peek_snapshot(_kairos_pid) is not None
                            else None
                        )
                        if _kairos_pid and _kairos_name and await _kairos_tick(_kairos_pid, _kairos_name, db, memory_search_fn=_make_memory_search_fn(_kairos_pid, db), best_friend_id=_bf_id):
                            continue  # re-enter loop to listen for their response

                    # Bug Y (2026-04-22 live run): cloud-recovery TTS narration
                    # was suppressed. The previous Ollama-generated "I'm feeling
                    # much better now" message leaked internal infrastructure
                    # terminology to the user ("My cloud connection just came
                    # back online, so everything should be smooth sailing now"
                    # — line 415 of the 2026-04-22 log). The user has no need
                    # to know about cloud-state transitions: they didn't hear
                    # when we went SICK (we silently used Ollama for that turn),
                    # so they don't need to hear when we recover. Just clear
                    # the flag and continue. The next turn flows on Together.ai
                    # as normal.
                    if _cloud_recovered:
                        _cloud_recovered = False
                        print("[Cloud] Recovery TTS suppressed (Bug Y) — continuing silently")

                    # If ambient probe already captured speech, use it directly.
                    import core.audio as _audio_mod
                    if _ambient_text:
                        text, audio_buf = _ambient_text, _ambient_audio
                        _ambient_text  = ""
                        _ambient_audio = None
                        _last_user_speech_at = time.time()  # KAIROS: reset silence clock
                        # Ambient probe published its own speech duration when
                        # it ran; read the latest snapshot as the main-turn value.
                        _main_speech_secs = float(getattr(_audio_mod, "_last_speech_secs", 0.0))
                    else:
                        _lip_task = asyncio.create_task(_lip_tracking_loop(camera))
                        try:
                            text, _, audio_buf = await listen_and_transcribe()
                        finally:
                            _lip_task.cancel()
                        try:
                            await _lip_task
                        except asyncio.CancelledError:
                            pass
                        set_lip_active(False)
                        # Stash main turn's speech duration IMMEDIATELY — the
                        # addendum probe below runs another listen and (if
                        # speech is detected) will publish its own duration
                        # over this global. We accumulate both in routing.
                        _main_speech_secs = float(getattr(_audio_mod, "_last_speech_secs", 0.0))

                    # Face-loss early exit: check BEFORE processing speech.
                    # If face is gone AND no speech detected → break immediately.
                    # If face is gone BUT speech WAS detected → respond first, THEN
                    # exit after this turn (the user deserves a response to what they said).
                    _fl_pid = _primary_person_id()
                    _fl_face_gone = False
                    if _fl_pid and _session_store.peek_snapshot(_fl_pid) is not None:
                        _fl_snap = _session_store.peek_snapshot(_fl_pid)
                        _fl_face_gone = (
                            _fl_snap is not None
                            and _fl_snap.session_type == "face"
                            and time.time() - _fl_snap.last_face_seen > FACE_LOSS_GRACE
                        )

                    if not text:
                        if _fl_face_gone or not _primary_person_id():
                            # Face gone or session expired — return to WATCHING scan.
                            print("[Pipeline] No speech detected, back to watching.")
                            break
                        # Face still visible but person silent — loop back so Kairos
                        # can fire when silence threshold is reached.
                        continue

                    _last_user_speech_at = time.time()  # KAIROS: reset silence clock

                    # Addendum window: user may have paused mid-thought (Smart-Turn fired
                    # at 0.85s) but still has more to say. Re-listen for up to
                    # ADDENDUM_ONSET_WINDOW seconds; if speech starts, record the addendum
                    # and combine it with the original utterance before calling the LLM.
                    # Adds ≤ADDENDUM_ONSET_WINDOW latency on normal turns (no addendum).
                    addendum_text, _, addendum_audio = await listen_and_transcribe(
                        silence_duration=SMART_TURN_SILENCE,
                        max_duration=3.0,
                        speech_onset_timeout=ADDENDUM_ONSET_WINDOW,
                    )
                    # Capture addendum's speech duration (0.0 if empty — thanks
                    # to the Session 79 fix, empty recordings no longer clobber
                    # the global, but we still need to know whether the addendum
                    # had speech to sum correctly).
                    _addendum_speech_secs = (
                        float(getattr(_audio_mod, "_last_speech_secs", 0.0))
                        if addendum_text else 0.0
                    )
                    if addendum_text:
                        combined = text.rstrip(' .,?!') + " " + addendum_text
                        print(f"[Pipeline] Addendum: '{addendum_text}' → '{combined}'")
                        text      = combined
                        # Merge audio for a richer voice embedding sample
                        if len(addendum_audio) > 0:
                            import numpy as _np
                            audio_buf = _np.concatenate([audio_buf, addendum_audio])

                    # Re-resolve primary person after listen (may have changed)
                    _cur_pid  = _primary_person_id()
                    _cur_name = _primary_person_name() if _cur_pid else None
                    _set_state(PipelineState.THINKING, _cur_name)

                    # ── Per-turn voice ID (all sessions) ─────────────────────────
                    # Always run voice ID on every utterance — not just for unknowns.
                    # Result tells brain exactly who spoke and whether it matches the
                    # active session person. Runs in executor (ECAPA-TDNN, 80-150ms).
                    _ev_loop = asyncio.get_running_loop()
                    _v_pid, _v_score = await _ev_loop.run_in_executor(
                        None, voice_mod.identify, audio_buf, _voice_gallery, VOICE_RECOGNITION_THRESHOLD
                    )

                    # Voice-identified speakers are added to _persons_in_frame so
                    # session tracking knows they're present even without a face.
                    # source="voice" distinguishes them from camera-detected entries.
                    if _v_pid:
                        _v_row_pif = db.get_person(_v_pid)
                        _v_name_pif = _v_row_pif["name"] if _v_row_pif else _v_pid
                        if _v_pid in _persons_in_frame:
                            _persons_in_frame[_v_pid]["last_seen"] = time.time()
                            _persons_in_frame[_v_pid]["conf"]      = _v_score
                            # Session 102 Bug F.3: refresh name on
                            # voice-only updates too — parallel to the
                            # face-scan fix. A voice-routed re-entry
                            # after a rename would have kept the stale
                            # name otherwise.
                            _persons_in_frame[_v_pid]["name"]      = _v_name_pif
                        else:
                            _persons_in_frame[_v_pid] = {
                                "name":              _v_name_pif,
                                "conf":              _v_score,
                                "last_seen":         time.time(),
                                "last_recognized_at": time.time(),
                                "source": "voice",
                            }

                    # ── Within-utterance diarization ─────────────────────────────
                    # Detect multiple speakers in a single VAD window and attribute
                    # each span to a person_id via the ECAPA voice gallery.
                    #
                    # Session 88 P2 refactor (Part B): generalized from the legacy
                    # exactly-2-speaker hardcode (``len(_diar) == 2``) to N-segment
                    # consumption. Pyannote's backend can return 1, 2, 3, or more
                    # segments per utterance; we group consecutive same-
                    # ``speaker_label`` segments into spans (pyannote often emits
                    # multiple adjacent fragments for one speaker's turn after a
                    # pause), transcribe each span independently, and build a
                    # ``[Name]: text`` block per span. The ``>= 2`` threshold is
                    # what distinguishes multi-speaker from single-speaker —
                    # anything less falls through to normal single-speaker flow.
                    _multi_speaker_detected = False
                    _multi_speaker_labels: list[str] = []
                    if len(audio_buf) >= DIARIZE_MIN_SECS * MIC_SAMPLE_RATE:
                        _diar = await _ev_loop.run_in_executor(
                            voice_mod.get_diarize_executor(), voice_mod.diarize,
                            audio_buf, _voice_gallery, VOICE_RECOGNITION_THRESHOLD
                        )
                        if len(_diar) >= 2:
                            # Collapse adjacent same-``speaker_label`` segments
                            # into spans. Pyannote SPEAKER_XX labels are stable
                            # WITHIN a single diarize() call (but NOT across
                            # calls — see voice.diarize docstring). Consecutive
                            # segments with the same label are the same speaker's
                            # continuation; merge to reduce transcription work
                            # and keep the brain's [Name]: block clean.
                            _spans: list[dict] = []
                            for _seg in _diar:
                                _this_label = _seg.get("speaker_label")
                                _last_label = _spans[-1].get("speaker_label") if _spans else None
                                if _spans and _this_label is not None and _this_label == _last_label:
                                    _spans[-1]["end_sample"] = _seg["end_sample"]
                                    # Prefer the first non-None speaker_id across merged
                                    # segments — ECAPA on a longer span is more reliable
                                    # than on the short fragments it was computed from.
                                    if _spans[-1].get("speaker_id") is None and _seg.get("speaker_id"):
                                        _spans[-1]["speaker_id"]    = _seg["speaker_id"]
                                        _spans[-1]["speaker_score"] = _seg["speaker_score"]
                                else:
                                    _spans.append({**_seg})

                            # Transcribe each span; drop ones that produce
                            # empty text (silence misdiarized into a segment).
                            # Session 3B.4: name resolution pushed into the
                            # _format_multispeaker_transcript helper (carries
                            # unknown_N numbering + N=2 vs N≥3 layout).
                            _named_pairs: list[tuple[str | None, str]] = []
                            for _span in _spans:
                                _a = audio_buf[_span["start_sample"]:_span["end_sample"]]
                                _t, _ = await _ev_loop.run_in_executor(None, transcribe, _a)
                                _t = _t.strip()
                                if not _t:
                                    continue
                                _pid_span = _span.get("speaker_id")
                                _span_name: "str | None" = None
                                if _pid_span is not None:
                                    _r = db.get_person(_pid_span)
                                    _span_name = _r["name"] if _r else _pid_span
                                _named_pairs.append((_span_name, _t))

                            # Only emit multi-speaker text block when ≥2 non-empty
                            # transcripts survive. Single-span or single-survivor
                            # cases stay on the normal single-speaker path.
                            if len(_named_pairs) >= 2:
                                text, _preview, _labels = _format_multispeaker_transcript(_named_pairs)
                                _multi_speaker_detected = True
                                _multi_speaker_labels   = _labels
                                print(f"[STT] [{len(_named_pairs)} voices] {_preview}")
                                # Phase 3B.4 — N≥3 guardrail log makes
                                # primary-attribution visible in canary logs
                                # alongside [STT]. Non-primary speakers are
                                # NOT auto-promoted to active sessions —
                                # prevents a 3-speaker burst from fragmenting
                                # into 3 new stranger sessions.
                                if len(_named_pairs) >= 3:
                                    _primary_name = None
                                    if _v_pid:
                                        _pr_row = db.get_person(_v_pid)
                                        _primary_name = (
                                            _pr_row["name"] if _pr_row else _v_pid
                                        )
                                    _others = [n for n in _labels if n != _primary_name]
                                    print(
                                        f"[Pipeline] N-speaker turn — "
                                        f"primary: {_primary_name or 'unknown'}, "
                                        f"others: {_others!r}"
                                    )
                    _v_name = None
                    if _v_pid:
                        _v_row = db.get_person(_v_pid)
                        _v_name = _v_row["name"] if _v_row else _v_pid

                    # Build voice state for brain injection
                    _matches_active = (_session_store.peek_snapshot(_v_pid) is not None) if _v_pid else False
                    _voice_state = {
                        "matched_id":              _v_pid,
                        "matched_name":            _v_name,
                        "voice_confidence":        _v_score,
                        "matches_active":          _matches_active,
                        "gallery_size":            len(_voice_gallery),
                        "multi_speaker":           _multi_speaker_detected,
                        "multi_speaker_speakers":  _multi_speaker_labels,
                    }
                    # Update the matching session's last_spoke_at — ONLY when
                    # voice confirms the session holder. When voice ID fails (unknown
                    # speaker), do NOT extend the session — a different person speaking
                    # should not keep the original person's session alive.
                    if _v_pid and _session_store.peek_snapshot(_v_pid) is not None:
                        _vs_ts = time.time()
                        try:
                            _loop = asyncio.get_running_loop()
                            _loop.create_task(_session_store.record_voice_spoke(
                                _v_pid, ts=_vs_ts, voice_confidence=_v_score))
                        except RuntimeError:
                            pass  # OPTIONAL
                        # Bug I (2026-04-20 live run): persist the voice match to the
                        # session's identity_evidence BEFORE routing or accumulation
                        # decisions. Without this, a freshly-reopened session's Path B
                        # sees voice_match_conf=0.0 (the _open_session seed value) even
                        # when this turn's voice ID scored ≥ 0.45 — and refuses to
                        # accumulate despite a mature profile. Every Jagan turn in the
                        # second half of the 2026-04-20 run hit this refusal at voice_n=20.
                        _loop.create_task(_session_store.update_voice_heard(
                            _v_pid, conf=_v_score, ts=time.time()))
                        # Bug D1 (2026-04-22 live run): feed the disputed-session
                        # auto-clear detector. Only disputed sessions need this
                        # deque; lazy-initialize on first append so non-disputed
                        # sessions don't pay the allocation cost.
                        if _is_disputed(_v_pid):
                            try:
                                _loop = asyncio.get_running_loop()
                                _loop.create_task(_session_store.append_voice_conf(_v_pid, conf=_v_score))
                            except RuntimeError:
                                pass  # OPTIONAL

                    # ── Per-turn speaker routing ──────────────────────────────
                    # Resolve the ACTUAL speaker using voice + face signals.
                    # Five outcomes:
                    #   switch_enrolled — different enrolled person (confident)
                    #   current         — stay with cur_pid (confirmed)
                    #   new_stranger    — unrecognized speaker; open stranger session
                    #   ambiguous       — unknown; log and skip attribution
                    #   no_action       — nothing to do; drop turn
                    _pt_snap = _session_store.peek_snapshot(_cur_pid) if _cur_pid else None
                    _cur_person_type = _pt_snap.person_type if _pt_snap is not None else None
                    # Bug F: pass utterance duration so the short-utterance floor
                    # can drop noisy voice IDs from short social closers.
                    # Session 78: switched from BUFFER length (pre-roll + speech
                    # + trailing silence, always >1s) to speech-only duration
                    # published by record_until_silence via module-level state.
                    # Session 79: the 2026-04-22 live session caught this reading
                    # 0.00s every turn — the addendum probe's empty recording
                    # was clobbering the main turn's published value before we
                    # could read it. Fix has two parts: (1) audio.py only
                    # publishes on non-empty recordings, (2) pipeline stashes
                    # main and addendum durations immediately after each listen
                    # and sums them here so the routing floor sees the full
                    # speech duration on combined-audio turns.
                    _utterance_secs = _main_speech_secs + _addendum_speech_secs
                    # Session 118 Fix A — pass diarize segment count so the
                    # resolver can detect "stranger present, voice ID failed"
                    # and drop the turn instead of misattributing to current.
                    _diar_seg_count = len(_diar) if isinstance(_diar, list) else 1
                    _resolved_pid, _routing_action = _resolve_actual_speaker(
                        _v_pid, _v_score, _cur_pid,
                        _persons_in_frame, _unrecognized_tracks,
                        _voice_gallery_sizes, time.time(),
                        cur_person_type=_cur_person_type,
                        utterance_duration=_utterance_secs,
                        # Session 93 P3.23 tiered threshold: ambiguous-zone drop
                        # (0.20-0.40 score) only fires when the room plausibly
                        # contains another speaker. Pass the active session count
                        # so the resolver can tell solo from multi-session context.
                        n_active_sessions=len(_session_store.peek_all_snapshots()),
                        n_diarize_segments=_diar_seg_count,
                        # Session 120: pass holder's voice profile maturity so
                        # the single-segment-voice-mismatch gate can decide
                        # whether ECAPA's "no match" verdict is trustworthy.
                        cur_holder_voice_n=(_pt_snap.evidence.voice_sample_count if _pt_snap is not None else 0) if _cur_pid else 0,
                    )

                    # ── Session 123 / Phase 1 — Voice Channel shadow logging ──
                    # Run the new pure voice_channel.identify_speaker AFTER the
                    # existing routing call. Compare its IdentityClaim against
                    # the current routing's (v_pid, v_score). Production
                    # behavior unchanged — this is observation only. After 1-2
                    # weeks of divergence-log review, graduate to Phase 2.
                    # Wrapped in try/except so a bug in the new code can never
                    # break a production turn.
                    try:
                        from core.voice_channel import identify_speaker as _vc_identify
                        _vc_claim = await _vc_identify(
                            audio_buf, _voice_gallery,
                            utterance_duration=_utterance_secs,
                        )
                        _vc_pid_diff = _vc_claim.pid != _v_pid
                        _vc_conf_diff = abs(float(_vc_claim.confidence) - float(_v_score)) > 0.05
                        if _vc_pid_diff or _vc_conf_diff:
                            print(
                                f"[VoiceChannel-Shadow] {_now_log_ts()} divergence: "
                                f"new=(pid={_vc_claim.pid!r}, conf={_vc_claim.confidence:.3f}, "
                                f"n_seg={_vc_claim.n_diarize_segments}) "
                                f"vs current=(pid={_v_pid!r}, score={_v_score:.3f}, "
                                f"n_seg={_diar_seg_count}) "
                                f"reason={_vc_claim.reasoning!r}"
                            )
                    except Exception as _vc_e:
                        print(f"[VoiceChannel-Shadow] error: {type(_vc_e).__name__}: {_vc_e!r}")

                    # ── Phase 3/4 — Reconciler (shadow → primary) ────────
                    # Wrapped in try/except so a bug here can't break a
                    # turn. ROUTING_USE_RECONCILER=True makes the
                    # reconciler the primary router (Phase 4 cutover).
                    # Rollback: flip ROUTING_USE_RECONCILER=False in
                    # core/config.py.
                    _rc_decision = None
                    try:
                        from core.reconciler import (
                            _build_routing_inputs as _rc_build,
                            reconcile as _rc_reconcile,
                        )
                        _rc_now = time.time()
                        _rc_claim, _rc_presence, _rc_session = _rc_build(
                            v_pid=_v_pid,
                            v_score=_v_score,
                            n_diarize_segments=_diar_seg_count,
                            utterance_duration=_utterance_secs,
                            persons_in_frame=_persons_in_frame,
                            unrecognized_tracks=_unrecognized_tracks,
                            cur_pid=_cur_pid,
                            cur_person_type=(_cur_person_type or ""),
                            n_active_sessions=len(_session_store.peek_all_snapshots()),
                            voice_gallery_sizes=_voice_gallery_sizes,
                            now=_rc_now,
                        )
                        _rc_decision = _rc_reconcile(
                            _rc_claim, _rc_presence, _rc_session,
                        )
                        if _rc_decision.action != _routing_action:
                            print(
                                f"[Reconciler-Shadow] {_now_log_ts()} divergence: "
                                f"legacy={_routing_action!r} "
                                f"new={_rc_decision.action!r} "
                                f"rule={_rc_decision.rule_fired!r} "
                                f"pid={_rc_decision.pid!r} "
                                f"reason={_rc_decision.reasoning!r}"
                            )
                    except Exception as _rc_e:
                        print(
                            f"[Reconciler-Shadow] error: "
                            f"{type(_rc_e).__name__}: {_rc_e!r}"
                        )

                    # Phase 4 cutover: reconciler is now the primary router.
                    # Rollback: flip ROUTING_USE_RECONCILER = False in core/config.py.
                    if ROUTING_USE_RECONCILER and _rc_decision is not None:
                        _resolved_pid = _rc_decision.pid
                        _routing_action = _rc_decision.action

                    if _routing_action == "switch_enrolled":
                        # Different enrolled person is speaking — open/switch their session directly.
                        # No LLM confirmation needed: voice gallery is ground truth for enrolled persons.
                        if _session_store.peek_snapshot(_resolved_pid) is None:
                            # Fetch DB-sourced person_type BEFORE open so it's seeded at
                            # dict creation (closes the stranger-fallback race window).
                            _switched_pt = (db.get_person_type(_resolved_pid) if db else "known") or "known"
                            _open_session(_resolved_pid, _v_name, "voice",
                                          person_type=_switched_pt, voice_confidence=_v_score)
                            if _resolved_pid not in _conversation:
                                _conversation[_resolved_pid] = db.load_conversation_history(_resolved_pid)
                            # Invalidate stale query embedding cache so get_context() fetches
                            # fresh memory on this first turn rather than using a stale vector.
                            _query_embedding_cache.pop(_resolved_pid, None)
                        _sw_ts = time.time()
                        try:
                            _loop = asyncio.get_running_loop()
                            _loop.create_task(_session_store.record_voice_spoke(
                                _resolved_pid, ts=_sw_ts, voice_confidence=_v_score))
                        except RuntimeError:
                            pass  # OPTIONAL
                        # Session 90 Bug 1 Fix B: persist the voice match score to the
                        # switched-in session's ``identity_evidence`` so ``_voice_accum_allowed``
                        # Path B (mature-voice-match) can fire on this turn. The earlier
                        # write at the ``_v_pid in _active_sessions`` block (≈ line 4561)
                        # was skipped BECAUSE the session didn't exist yet — we just
                        # opened it. Without this write, a mature speaker (voice_n=20)
                        # re-entering after session expiry saw ``voice_match_conf=0.0``
                        # in evidence and every accumulation refused despite a real
                        # routing score of 0.617. Reviewer's 2026-04-22 Jagan re-entry
                        # case after John's session expired.
                        _loop.create_task(_session_store.update_voice_heard(
                            _resolved_pid, conf=_v_score, ts=time.time()))
                        _cur_pid  = _resolved_pid
                        _cur_name = _v_name
                        # Rebuild voice_state for the switched speaker so conversation_turn()
                        # receives consistent sensor data — critically matches_active=True.
                        # (voice_state was built before routing at line 2669, so it may
                        # reflect the OLD session holder, not the newly-switched-to person.)
                        _voice_state = {
                            "matched_id":              _cur_pid,
                            "matched_name":            _cur_name,
                            "voice_confidence":        _v_score,
                            "matches_active":          True,
                            "gallery_size":            len(_voice_gallery),
                            "multi_speaker":           _multi_speaker_detected,
                            "multi_speaker_speakers":  _multi_speaker_labels,
                        }
                        print(f"[Voice] Speaker switch → {_v_name} (score={_v_score:.3f})")

                    elif _routing_action == "new_stranger":
                        # #20: 1:1 stranger-track-to-session binding.
                        # Every SORT track gets a pre-allocated pid; multi-track →
                        # pick the most-recently-seen track's session (not "most-recent voice session").
                        _now_route   = time.time()
                        _active_unrec = {
                            tid: ts for tid, ts in _unrecognized_tracks.items()
                            if _now_route - ts < VOICE_ROUTING_FACE_STALE_SECS
                        }
                        # Identify which track is most likely the speaker
                        if len(_active_unrec) == 1:
                            _speaker_track = next(iter(_active_unrec))
                        elif len(_active_unrec) > 1:
                            # Pick the most-recently-seen face track as the likely speaker
                            _speaker_track = max(_active_unrec, key=lambda tid: _active_unrec[tid])
                        else:
                            _speaker_track = None
                        _target_sid = (
                            _stranger_track_map.get(_speaker_track)
                            if _speaker_track is not None else None
                        )
                        if _target_sid and _session_store.peek_snapshot(_target_sid) is not None:
                            # Same physical face returned — resume their session
                            _cur_pid  = _target_sid
                            _ts_snap = _session_store.peek_snapshot(_target_sid)
                            _cur_name = _ts_snap.person_name if _ts_snap is not None else _target_sid
                            try:
                                _loop = asyncio.get_running_loop()
                                _loop.create_task(_session_store.set_last_spoke_at(_cur_pid, _now_route))
                            except RuntimeError:
                                pass  # OPTIONAL
                            print(f"[Voice] Track {_speaker_track} → resumed session {_cur_pid}")
                        else:
                            # Open session — use pre-allocated pid if available
                            _sid = _target_sid or f"stranger_{__import__('uuid').uuid4().hex[:8]}"
                            db.add_stranger("visitor", person_id=_sid)  # INSERT OR IGNORE
                            _open_session(_sid, "visitor", "voice", person_type="stranger")
                            try:
                                _loop = asyncio.get_running_loop()
                                _loop.create_task(_session_store.set_waiting_for_name(_sid, STRANGER_REQUIRE_SYSTEM_NAME))
                            except RuntimeError:
                                pass  # OPTIONAL
                            _conversation[_sid] = []
                            _cur_pid  = _sid
                            _cur_name = "visitor"
                            if _speaker_track is not None:
                                _stranger_track_map[_speaker_track] = _sid
                            print(f"[Voice] Unrecognized speaker → new session {_cur_pid} (track={_speaker_track})")

                    elif _routing_action == "ambiguous":
                        # #21: record attribution; 3 consecutive ambiguous → close stale session
                        _drift_pid = _cur_pid
                        if _drift_pid and _session_store.peek_snapshot(_drift_pid) is not None:
                            try:
                                _loop = asyncio.get_running_loop()
                                _loop.create_task(_session_store.record_attribution(_drift_pid, "ambiguous"))
                            except RuntimeError:
                                pass  # OPTIONAL
                            _drift_snap = _session_store.peek_snapshot(_drift_pid)
                            if _drift_snap is not None:
                                _drift_attrs = list(_drift_snap.recent_attributions)
                                if len(_drift_attrs) == 3 and all(a == "ambiguous" for a in _drift_attrs):
                                    print(f"[Session] Drift: 3 consecutive ambiguous turns for {_drift_pid} — closing stale session")
                                    _close_session(_drift_pid)
                                    _cur_pid  = None
                                    _cur_name = None
                        print(f"[Voice] {_now_log_ts()} Routing: ambiguous — dropping turn (cur={_cur_pid})")
                        continue

                    elif _routing_action == "no_action":
                        # Short/silent utterance, nothing to attribute.
                        continue

                    elif _routing_action == "short_utterance_skip":
                        # Bug F (2026-04-20): utterance below VOICE_ROUTING_MIN_UTTERANCE_SECS
                        # and no session open — drop silently. User will repeat if meaningful.
                        continue

                    elif _routing_action == "short_utterance_voice_mismatch":
                        # Session 92 P3.23: utterance below VOICE_ROUTING_MIN_UTTERANCE_SECS
                        # but voice score against the gallery was clearly below
                        # VOICE_ROUTING_SHORT_UTT_FLOOR — the short-utterance floor
                        # said "noisy, hold current" but the mismatch check vetoed:
                        # this is obviously NOT cur_pid. Drop the turn without
                        # attribution; the speaker (probably a non-enrolled person
                        # starting with a short "hi") will naturally repeat with
                        # a longer utterance that routes correctly through the
                        # normal new_stranger path. No accumulation, no session
                        # state advance, no conversation_turn fires.
                        continue

                    elif _routing_action == "multi_segment_voice_mismatch":
                        # Session 118 Fix A: pyannote saw 2+ voices in this audio
                        # chunk but voice ID couldn't match any of them above
                        # VOICE_ROUTING_STRANGER_FLOOR. Without this drop, the
                        # canary 2026-04-25 23:21 misattribution would have
                        # routed a stranger's words to the visible owner. The
                        # speaker (the unrecognized one) will repeat with a
                        # cleaner longer utterance that routes through the
                        # normal new_stranger path. Same drop-and-let-repeat
                        # pattern as short_utterance_voice_mismatch.
                        continue

                    elif _routing_action == "single_segment_voice_mismatch":
                        # Session 120: pyannote heard ONE voice, ECAPA confidently
                        # said it's NOT the holder (mature voice profile +
                        # adequate audio + score below stranger floor), and
                        # there's no other candidate session. Without this
                        # drop, the silent fallback ("current — no other
                        # candidates in scene") misattributes the stranger's
                        # voice to the holder. Same drop-and-let-repeat
                        # pattern as multi_segment_voice_mismatch.
                        continue

                    # "current" — keep existing cur_pid (no speaker switch needed).

                    # #22: extend voice session when face confirms holder is present
                    _ext_snap = _session_store.peek_snapshot(_cur_pid) if _cur_pid else None
                    _now_ext = time.time()
                    if (_cur_pid and _session_store.peek_snapshot(_cur_pid) is not None
                            and (_ext_snap.session_type if _ext_snap is not None else None) == "voice"):
                        _holder_vis_ext = (
                            _cur_pid in _persons_in_frame
                            and _now_ext - _persons_in_frame[_cur_pid].get("last_recognized_at", 0)
                            < VOICE_ROUTING_FACE_STALE_SECS
                        )
                        if _holder_vis_ext:
                            try:
                                _loop = asyncio.get_running_loop()
                                _loop.create_task(_session_store.set_last_spoke_at(_cur_pid, _now_ext))
                            except RuntimeError:
                                pass  # OPTIONAL

                    # #21: record non-ambiguous attribution (resets any drift streak)
                    if _cur_pid and _session_store.peek_snapshot(_cur_pid) is not None:
                        try:
                            _loop = asyncio.get_running_loop()
                            _loop.create_task(_session_store.record_attribution(_cur_pid, _routing_action))
                        except RuntimeError:
                            pass  # OPTIONAL

                    # Voice accumulation for current person (when verified or early phase)
                    if _cur_pid and _cur_pid != "unknown" and len(audio_buf) > 0:
                        # #23: single policy — face_verified when holder is visibly present
                        # OR when the progressive-enroll gate already confirmed their face
                        # (voice_face_confirmed flag set on gate-pass turn).
                        _face_vis_acc = (
                            (_cur_pid in _persons_in_frame
                             and time.time() - _persons_in_frame[_cur_pid].get("last_recognized_at", 0)
                             < VOICE_ROUTING_FACE_STALE_SECS)
                            or (_ext_snap.voice_face_confirmed if _ext_snap is not None else False)
                        )
                        _t = asyncio.create_task(
                            _accumulate_voice(_cur_pid, audio_buf, db, face_verified=_face_vis_acc)
                        )
                        _voice_tasks.add(_t); _t.add_done_callback(_voice_tasks.discard)

                    # Build live sensor state — vision + voice together give brain
                    # the complete picture: what it SEES and who it HEARS, every turn.
                    _cur_snap      = _session_store.peek_snapshot(_cur_pid) if _cur_pid else None
                    _cur_rec_conf  = _persons_in_frame.get(_cur_pid, {}).get("conf", 0.0) if _cur_pid else 0.0
                    # Session 97 Fix 1: bump the user-turn counter BEFORE
                    # building vision_state so `session_user_turns` reflects
                    # "this turn's number" (1-indexed). Drives the
                    # <<<STRANGER IDENTITY>>> block's threshold gate.
                    if _cur_snap is not None:
                        _prev_turns = _cur_snap.user_turns
                        try:
                            _loop = asyncio.get_running_loop()
                            _loop.create_task(_session_store.increment_user_turns(_cur_pid))
                        except RuntimeError:
                            pass  # OPTIONAL
                        # Item 17: invalidate prefix cache when stranger turn threshold
                        # is crossed — <<<STRANGER IDENTITY>>> block enters Section 2.
                        # +1 because create_task(increment_user_turns) hasn't run yet;
                        # _cur_snap.user_turns still holds the pre-increment value.
                        if (
                            _cur_snap.person_type == "stranger"
                            and _cur_snap.user_turns + 1 == STRANGER_IDENTITY_BLOCK_MIN_TURNS
                        ):
                            try:
                                _loop = asyncio.get_running_loop()
                                _loop.create_task(_session_store.set_cached_prefix(_cur_pid, None))
                            except RuntimeError:
                                pass  # OPTIONAL
                    _vision_state = {
                        "face_in_frame":          time.time() - _last_face_seen < 2.0,
                        "person_name":            _cur_name,
                        "person_id":              _cur_pid,
                        "recognition_conf":       _cur_rec_conf,
                        "identity_disputed":      _is_disputed(_cur_pid),
                        "disputed_claimed_name":  _cur_snap.disputed_claimed_name if _cur_snap is not None else None,
                        # Session person_type drives the <<<TOOL ACCESS>>> block.
                        "session_person_type":    _cur_snap.person_type if _cur_snap is not None else "stranger",
                        # Structured identity_evidence drives <<<IDENTITY EVIDENCE>>>.
                        # Kept as dict read — brain.py requires the dict interface.
                        "identity_evidence":      dataclasses.asdict(_cur_snap.evidence) if _cur_snap is not None else None,
                        # Session 97 Fix 1: this turn's 1-indexed number (post-increment).
                        # +1 because create_task(increment_user_turns) hasn't run yet.
                        "session_user_turns":     (_cur_snap.user_turns + 1) if _cur_snap is not None else 0,
                        # Session 113 Part 1: gates the ADDRESS DECISION block.
                        "active_session_count":   len(_session_store.peek_all_snapshots()),
                        # Phase 3B.1: unified room-state block (None in
                        # single-person sessions).
                        "room_block":             _build_room_block(
                            _session_store.peek_all_snapshots(), _conversation, _emotion_agents,
                            _active_room_started_at, turn_cap=ROOM_BLOCK_TURN_CAP,
                        ),
                        # Phase 3B.6: recent room context for greeting
                        # enrichment (None when no qualifying summary).
                        "recent_room_context":    _fetch_recent_room_context(_cur_pid),
                    }

                    # ── STT attribution log ───────────────────────────────────────────────
                    _is_stranger_turn = (_cur_pid or "").startswith("stranger_")
                    _gate_active_turn = (_cur_snap.waiting_for_name if _cur_snap is not None else False) if _cur_pid else False
                    _spk_badge = f"STRANGER/{_cur_name}" if _is_stranger_turn else _cur_name
                    _voice_badge = f" (voice={_v_score:.2f})" if _v_score and _v_score > 0.01 else ""
                    _gate_badge = " [gate active]" if _gate_active_turn else ""
                    print(f"[STT] {_spk_badge}{_voice_badge}{_gate_badge}: {text}")

                    # G4: System-name gate — strangers must address system by name first.
                    # Word-boundary match (not substring) — "Rex" must not fire on "reflex".
                    if _cur_pid and (_cur_snap.waiting_for_name if _cur_snap is not None else False):
                        _name_heard, _name_match_method = _name_heard_in(text, _active_system_name)
                        if _name_heard:
                            # Name heard — unlock this stranger's session
                            try:
                                _loop = asyncio.get_running_loop()
                                _loop.create_task(_session_store.set_waiting_for_name(_cur_pid, False))
                            except RuntimeError:
                                pass  # OPTIONAL
                            _match_note = f" (phonetic)" if _name_match_method == "phonetic" else ""
                            print(f"[Pipeline] Stranger {_cur_pid} addressed system by name{_match_note} — engaging")
                            # Progressive enrollment: create DB entry on first system-name
                            # utterance and seed the voice profile with this audio so the
                            # stranger can be recognised by voice from the second turn onward.
                            if not (_cur_snap.db_enrolled if _cur_snap is not None else False):
                                db.add_stranger("visitor", person_id=_cur_pid)
                                try:
                                    _loop = asyncio.get_running_loop()
                                    _loop.create_task(_session_store.mark_enrolled(_cur_pid, "enrolled_1"))
                                except RuntimeError:
                                    pass  # OPTIONAL
                                print(f"[Pipeline] Progressive enroll: DB entry created for {_cur_pid}")
                                # Store face embedding if vision captured one for this track.
                                # Track whether a face was actually captured so we don't write
                                # false face-witness evidence for voice-only gate passes (Bug C).
                                _face_captured = False
                                _gate_track = next(
                                    (tid for tid, pid in _stranger_track_map.items() if pid == _cur_pid), None
                                )
                                if _gate_track is not None and _gate_track in _unrecognized_embeddings:
                                    _gate_emb = _unrecognized_embeddings[_gate_track]
                                    if db.add_embedding(_cur_pid, _gate_emb, "progressive_enroll"):
                                        print(f"[Pipeline] Progressive enroll: face embedding stored for {_cur_pid}")
                                        _face_captured = True
                                if len(audio_buf) > 0:
                                    if _face_captured:
                                        # Real face captured at gate pass — seed face-witness evidence
                                        # so post-routing accumulation trusts this person on turns 2..N.
                                        try:
                                            _loop = asyncio.get_running_loop()
                                            _loop.create_task(_session_store.mark_voice_face_confirmed(_cur_pid))
                                        except RuntimeError:
                                            pass  # OPTIONAL
                                        try:
                                            _loop = asyncio.get_running_loop()
                                            _loop.create_task(_session_store.update_face_seen(
                                                _cur_pid, conf=0.50, ts=time.time(), anti_spoof_live=True))
                                            _loop.create_task(_session_store.set_bootstrap_credits(
                                                _cur_pid, N_INITIAL_VOICE_BOOTSTRAP))
                                        except RuntimeError:
                                            pass  # OPTIONAL
                                        _t = asyncio.create_task(_accumulate_voice(_cur_pid, audio_buf, db, face_verified=True))
                                    else:
                                        # Voice-only engagement — NO face was captured. Only grant
                                        # bootstrap credits so the voice profile can grow; don't
                                        # fabricate face evidence that would mislead the brain's
                                        # <<<IDENTITY EVIDENCE>>> verdict or the accumulation gate.
                                        try:
                                            _loop = asyncio.get_running_loop()
                                            _loop.create_task(_session_store.set_bootstrap_credits(
                                                _cur_pid, N_INITIAL_VOICE_BOOTSTRAP))
                                        except RuntimeError:
                                            pass  # OPTIONAL
                                        _t = asyncio.create_task(_accumulate_voice(_cur_pid, audio_buf, db, face_verified=False))
                                    _voice_tasks.add(_t); _t.add_done_callback(_voice_tasks.discard)
                            # Fall through to conversation_turn() with original text.
                            # LLM responds naturally to whatever they said (which included the name).
                        else:
                            # Name not heard — stay silent, keep listening
                            print(f"[STT] STRANGER/{_cur_name} [gate blocked — '{_active_system_name}' not heard]: {text}")
                            continue

                    # For stranger sessions, give the LLM context about the visitor
                    # so it can naturally ask their name and probe the owner connection.
                    _addendum_override = None
                    if _cur_pid and _cur_pid.startswith("stranger_"):
                        _known = [p for p in db.list_people() if p.get("person_type", "known") == "known"]
                        _owner = sorted(_known, key=lambda p: p["enrolled_at"])[0]["name"] if _known else None
                        _addendum_override = (
                            "You are speaking with an unknown visitor — respond warmly and naturally. "
                            "Learn their name organically; ask when the moment feels right. "
                        )
                        if _owner:
                            _addendum_override += (
                                f"If it feels natural, ask if they know {_owner}. "
                                f"If yes, explore how they know them and the relationship. "
                            )
                        _addendum_override += "Do not share private information about enrolled persons."

                    result, extra = await conversation_turn(
                        text, _cur_pid, _cur_name, db,
                        vision_state=_vision_state,
                        voice_state=_voice_state,
                        prompt_addendum_override=_addendum_override,
                    )

                    # Deferred face-loss exit: we responded to the user's last words,
                    # now exit if their face has been gone longer than grace period.
                    # Guard: skip if _cur_pid changed mid-turn (speaker switch or new stranger).
                    if _fl_face_gone and _cur_pid == _fl_pid:
                        print(f"[Pipeline] Face lost for {_cur_name} — ending conversation after final response.")
                        break

                    # Stay in conversation — immediately re-listen without camera rescan
                    _cur_name = _primary_person_name() or _cur_name
                    _set_state(PipelineState.LISTENING, _cur_name)
                    print(f"[Pipeline] Listening for {_cur_name}...")

                _set_state(PipelineState.WATCHING, _primary_person_name())

            # Tick at ~20 FPS but wake immediately if shutdown is requested.
            try:
                await asyncio.wait_for(_shutdown_event.wait(), timeout=0.05)
            except asyncio.TimeoutError:
                pass

    finally:
        print("[Pipeline] Shutting down...")

        # 1. Stop audio immediately — user shouldn't hear TTS continue during cleanup.
        print("[Pipeline] Stopping audio...")
        stop_audio()

        # 1.5. Stop persistent background vision loop (sole camera reader).
        if _vis_bg_task and not _vis_bg_task.done():
            _vis_bg_task.cancel()
            try:
                await asyncio.wait_for(_vis_bg_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # 2. Release camera.
        print("[Pipeline] Releasing camera...")
        camera.release()

        # 3. Cancel pending voice accumulation tasks — they hold DB references.
        for _vt in list(_voice_tasks):
            _vt.cancel()
        if _voice_tasks:
            await asyncio.gather(*list(_voice_tasks), return_exceptions=True)
        _voice_tasks.clear()

        # 4. Close database (flushes WAL, releases file locks).
        db.close()  # idempotent; CLEANUP swallow lives in FaceDB.close()

        # 5. Shutdown brain agent (waits for in-flight extraction to finish).
        try:
            await asyncio.wait_for(_brain_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
            pass

        # 5.5. Cancel cloud retry loop (runs for session lifetime — must be cancelled).
        if _cloud_monitor_task and not _cloud_monitor_task.done():
            _cloud_monitor_task.cancel()
            try:
                await asyncio.wait_for(_cloud_monitor_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass

        # 5.5b. Cancel health log loop (Wave 5 / Item 19).
        if _health_log_task and not _health_log_task.done():
            _health_log_task.cancel()
            try:
                await asyncio.wait_for(_health_log_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass

        # 5.6. Shut down dedicated diarization executor (Item 13, Wave 3).
        try:
            voice_mod.shutdown_diarize_executor()
        except Exception as e:
            print(f"[Pipeline] diarize executor shutdown failed: {e!r}")

        # 6. Mark dashboard offline.
        state.write(mode="offline")

        # S120 #6 — emit classifier learning-rate summary for this session.
        try:
            from core.classifier_graph import get_session_summary as _cg_summary
            print(_cg_summary())
        except Exception:
            pass  # OPTIONAL: classifier session summary at shutdown — non-critical telemetry

        print("[Pipeline] Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(run())