"""
pipeline.py — Main loop
See face → identify → greet → listen → respond → repeat
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import asyncio
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

# Terminal-output log harness (Tee + drain + archive/rotate + log-state globals) lives in
# runtime/log_capture.py as of P1.A1 SP-4.1. The boot-time side-effects (archive, open log
# file, start drain thread, install Tee) stay HERE in the __main__ guard because they must run
# only for `python pipeline.py`, never on subprocess re-import (Windows multiprocessing.spawn).
import threading as _log_thread_mod  # used only by the __main__ boot guard below

import runtime.log_capture as log_capture  # noqa: F401  — boot guard attribute-rebinds log_capture's rebound globals
from runtime.log_capture import (  # noqa: F401  — bare-name re-exports for callers (dream-loop _check/_prune, etc.)
    _LOG_PATH,
    _log_q,
    _archive_terminal_output,
    _check_terminal_output_size_cap,
    _prune_old_terminal_archives,
    _log_drain,
    _Tee,
)

# ───── P0.S12 — Module-level side-effect guard (Windows-spawn-mode safe boot block) ─────
#
# Canary 2026-05-27 (terminal_output_2026-05-27_115642.md) surfaced repeated PermissionError 13
# from _archive_terminal_output() firing in heavy-worker subprocess re-imports of this module:
# on Windows, multiprocessing uses `spawn` which RE-IMPORTS the main module in every child.
# This guard gates the 5 Tier-1 side-effects behind `__main__` so they never fire on re-import.
#
# P1.A1 SP-4.1: the harness symbols moved to runtime/log_capture.py. The REBOUND log-state
# (_LOG_FILE, _archived_log, _log_drain_thread, the 3 drain counters) is attribute-set on
# log_capture's namespace below — NOT pipeline-local — because _log_drain + _check (running in
# log_capture) and core.health (reading the drain counters) all resolve them in log_capture's
# namespace. A `from log_capture import _LOG_FILE; _LOG_FILE = ...` would snapshot a pipeline
# local and leave _log_drain staring at None. The boot-rebind is canary-gated: the suite asserts
# this guard does NOT run on import, so green can never prove the rebind works at runtime — only
# the P1.A1 hardware canary can.
#
# 5 Tier-1 sites, byte-for-byte ORDERING preserved (_LOG_FILE set BEFORE the thread + Tee read it):
#   - log_capture._archive_terminal_output() call (the original PermissionError surface)
#   - log_capture._LOG_FILE = open(...) (truncating-mode handle competition)
#   - log_capture._log_drain_thread.start() (orphan daemon in subprocess)
#   - sys.stdout = log_capture._Tee(sys.stdout) + sys.stderr = log_capture._Tee(sys.stderr)
#   - "Prior session log archived" success print (subprocess-duplicate)
#
# DO NOT move any Tier-1 site outside this guard without re-evaluating Windows spawn re-import.
# DO NOT convert the rebound attribute-sets to from-import + bare assignment. See test_p0_s12_*.py.
# ────────────────────────────────────────
if __name__ == "__main__":
    log_capture._archived_log = log_capture._archive_terminal_output()

    log_capture._LOG_FILE = open(
        log_capture._LOG_PATH,
        # P1.5: fresh per session now — prior session's content is preserved in
        # the timestamped archive returned by _archive_terminal_output above.
        "w", encoding="utf-8", buffering=1,
    )

    log_capture._log_drain_thread = _log_thread_mod.Thread(
        target=log_capture._log_drain, daemon=True, name="log-writer")
    log_capture._log_drain_thread.start()

    sys.stdout = log_capture._Tee(sys.stdout)
    sys.stderr = log_capture._Tee(sys.stderr)

    # P1.5: announce the archive AFTER the tee is wired so the message lands in
    # both terminal AND the new log file (harvest script correlates archives to sessions).
    if log_capture._archived_log is not None:
        print(f"[Pipeline] Prior session log archived → {log_capture._archived_log.name}")

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
import core.heavy_worker as hw  # P0.R6 D3: AdaFace embed routed via ProcessPoolExecutor worker pool
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
    DEFAULT_SYSTEM_NAME,
    EMOTION_FACT_VALIDITY_HOURS,
    IDENTITY_SOFT_THRESHOLD, IDENTITY_ASK_THRESHOLD, IDENTITY_AUTO_THRESHOLD,
    BRIEFING_MIN_ABSENCE,
    ANTISPOOFING_ENABLED, ANTISPOOFING_THRESHOLD,
    ANTI_SPOOF_REASON_PASSED, ANTI_SPOOF_REASON_REJECTED,
    ANTI_SPOOF_REASON_UNAVAILABLE, ANTI_SPOOF_REASON_NO_VERDICT,
    ANTI_SPOOF_BURST_THRESHOLD, ANTI_SPOOF_BURST_WINDOW_SECS,
    HISTORY_OVERRIDE_TOOLS, TOOL_REPEAT_MAX_CONSECUTIVE,
    TOOL_TIMEOUT_SECS, TOOL_TIMEOUT_OVERRIDES,
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
from core.config  import CLOUD_OFFLINE_TIMEOUT, CLOUD_RETRY_INTERVAL, DREAM_IDLE_MINUTES, DREAM_COOLDOWN, DREAM_MAX_INTERVAL, KAIROS_SILENCE_THRESHOLD_SECS, KAIROS_COOLDOWN, STRANGER_REQUIRE_SYSTEM_NAME, SCENE_STALE_SECS, SCENE_BLOCK_ENABLED, SCENE_VOICE_STALE, STRANGER_TTL_DAYS, STRANGER_VOICE_TTL_DAYS, DISPUTE_MAX_DURATION, DISPUTE_RENAME_BLOCK_THRESHOLD, VALID_PERSON_TYPES, TOOL_PRIVILEGES, N_INITIAL_VOICE_BOOTSTRAP, VOICE_ACCUM_FACE_WITNESS_MIN_CONF, VOICE_ACCUM_FACE_WITNESS_MAX_AGE_SEC, VOICE_ACCUM_VOICE_SELF_MATCH_MIN, VOICE_ACCUM_MATURE_SAMPLE_COUNT, VOICE_ROUTING_MIDRANGE_SWITCH_MIN, VOICE_ROUTING_FACE_ASSIST_MIN, VOICE_ROUTING_SELF_MATCH_FLOOR, VOICE_ROUTING_SELF_MATCH_OFFSCREEN, VOICE_ROUTING_MIN_UTTERANCE_SECS, VOICE_ROUTING_SHORT_UTT_MISMATCH_ENABLED, VOICE_ROUTING_SHORT_UTT_FLOOR, VOICE_ROUTING_MIN_AUDIO_FOR_SCORE, VOICE_ROUTING_SHORT_UTT_AMBIGUOUS, VOICE_ROUTING_NOISE_FLOOR_SECS, VOICE_ROUTING_STRANGER_FLOOR, VOICE_ROUTING_SINGLE_SEGMENT_MISMATCH_ENABLED, VISION_SHADOW_INTERVAL_SECS, MEMORY_SPARSE_THRESHOLD, SYSTEM_NAME_ASSIGN_PATTERNS, PERSON_NAME_ASSIGN_PATTERNS, IDENTITY_DENIAL_PATTERNS, DISPUTE_AUTO_CLEAR_VOICE_MIN, DISPUTE_AUTO_CLEAR_VOICE_SOLO_MIN, DISPUTE_AUTO_CLEAR_CONSECUTIVE_TURNS, ENROLLMENT_RENAME_GRACE_SECS, ENROLLMENT_RENAME_VOICE_THRESHOLD, ENROLLMENT_RENAME_MAX_TURNS, SCENE_VISITOR_RECENCY_SECS, KAIROS_PREFER_BEST_FRIEND, BATCH_GREETING_ENABLED, BATCH_GREETING_MIN_PEOPLE, BATCH_GREETING_LLM_TIMEOUT_SECS, ROOM_BLOCK_ENABLED, ROOM_BLOCK_TURN_CAP, SHARED_CONTEXT_BLOCK_ENABLED, SHARED_CONTEXT_BLOCK_TURN_CAP, STRANGER_IDENTITY_BLOCK_MIN_TURNS, SCENE_BLOCK_CACHE_ENABLED, SCENE_BLOCK_CACHE_MAX_ENTRIES, SHADOW_CHANNEL_LOGGING_ENABLED
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
from core.session_state       import SessionStore
from core.presence_store      import PresenceStore
from core.track_store         import TrackStore
from core.conversation_store  import ConversationStore
from core.voice_gallery_store import VoiceGalleryStore
from core.per_person_agent_store import PerPersonAgentStore
from core.cache_store import CacheStore, CACHE_MISS
from core.pipeline_state_store import PipelineStateStore
from core.vision_frame_store import VisionFrameStore
# P0.S7.D-D Stage 1 — class extraction. The 7 module-level room helpers
# below are flag-gated SHIMS dispatching to RoomOrchestrator methods.
# Stage 2 hard-deletes the shims + migrates 130 test sites; same bundled-
# queue canary trigger as D-C Stage 2 (combined PR candidate).
from core.room_orchestrator import RoomOrchestrator
from core.emotion        import EmotionAgent
from core import state
import jellyfish
# ── re-exported from runtime/ (P1.A1 SP-4 — pure leaves) ──────────────────────
from runtime.text import (  # noqa: F401
    _NAME_EXTRACT_RE, _PHRASE_PREFIXES, sanitize_name, _nfkc_lower,
    _strip_im_contraction, _intent_allows, _user_text_gate_passes, _detect_yes_no,
)
from runtime.state_enums import PipelineState, CloudState  # noqa: F401
from runtime.context_blocks import (  # noqa: F401
    _format_multispeaker_transcript, _count_scene_candidates, _infer_zone,
    _set_state, _get_scene_block_cached, get_scene_block_cache_stats, _build_scene_block,  # P1.A1 SP-6.5 re-export
)
from runtime.wiring import (  # noqa: F401  — P1.A1 SP-5: 11 reset-in-place stores
    # (from-import SAFE — conftest .reset()s the same shared object). The 5
    # rebound refs (_session_store/_pipeline_state_store/_brain_orchestrator/
    # _face_db_ref/_room_orchestrator) are NOT here — they forward via the
    # module-level __getattr__ installed at SP-5 step c.
    _identity_hints_store, _conversation_store, _query_embedding_store,
    _presence_store, _track_store, _anti_spoof_rejection_store,
    _voice_gallery_store, _per_person_agent_store, _vision_frame_store,
    _scene_block_store, _classifier_cache_store,
)
from runtime.session import (  # noqa: F401  — P1.A1 SP-6.1 re-export (engine bodies)
    _face_in_frame, _has_recent_face_evidence, _is_disputed, _emit_session_lifecycle_safe, _on_room_end,
    _open_session, _voice_accum_allowed, _close_session, _expire_stale_sessions, _accumulate_voice,
)
from flows.companion.tools import (  # noqa: F401  — P1.A1 SP-6.2 re-export (tool dispatch)
    _INVALID_SYSTEM_NAMES, _SHUTDOWN_QUESTION_RE, _tool_allowed, _is_enrollment_mishear_candidate, _log_intent_divergence,
    _ToolContext, _handle_update_person_name, _handle_report_identity_mismatch, _handle_update_system_name,
    _handle_shutdown, _handle_search_memory, _TOOL_HANDLERS, _execute_tool,
)
from flows.companion.turn_flows import shadow_classify, _compute_room_audience, session_end_notify, _resolve_addressed_to, history_persist  # noqa: F401  — P1.A1 SP-7b.1/7b.2/7b.3 re-export
from runtime.identity_cache import (  # noqa: F401  — P1.A1 SP-6.2 re-export (bf-cache funcs;
    _get_best_friend_cached, _invalidate_bf_cache,  # raw _cached_bf_* globals NOT re-exported — mutable, stale-snapshot trap)
)
import runtime.vision_loop as _vl  # P1.A1 SP-6.3: vision-loop engine home (run() push-DIs 5 refs via _vl._X)
from runtime.vision_loop import (  # noqa: F401  — P1.A1 SP-6.3 re-export (run() spawns 6; tests reach 2)
    _lip_tracking_loop, _vision_watchdog_loop, _heavy_worker_watchdog_loop,
    _audio_device_watchdog_loop, _background_vision_loop, _classify_anti_spoof_verdict,
    _should_run_recognition, _maybe_record_silent_obs,  # _restart_vision_task NOT re-exported (move-set-internal; tests use _vl)
)
from runtime.background_loops import (  # noqa: F401  — P1.A1 SP-6.4 re-export (run + conversation_turn spawn 3 loops;
    _cloud_retry_loop, _dream_loop, _health_log_loop,  # _emit_health NOT re-exported — move-set-internal, 0 test access)
)
from runtime.wiring import lip_tracker  # noqa: F401  — SP-6.1: relocated singleton (read by _lip_tracking_loop until 6.3)
import runtime.wiring as _wiring  # P1.A1 SP-5: rebound-global canonical home


# P1.A1 SP-5 — rebound-global READ facade (PEP 562). Forwards EXACTLY the 5
# rebound names to runtime.wiring (their canonical home) for EXTERNAL
# `pipeline._session_store` reads (tests/other modules) + getattr/hasattr.
# pipeline's OWN internal reads are rewired to _wiring._X (a bare LOAD_GLOBAL
# does NOT trigger module __getattr__). Strict whitelist — every other name
# raises AttributeError, so typos aren't masked and the conftest reset
# fixture's hasattr(pipeline, …) checks stay honest.
_WIRING_FORWARDED = frozenset({
    "_session_store", "_pipeline_state_store", "_brain_orchestrator",
    "_face_db_ref", "_room_orchestrator",
    "_anti_spoof_checker", "_vision_task",  # P1.A1 SP-6.3 WIRE (test-read)
})


def __getattr__(name):
    if name in _WIRING_FORWARDED:
        return getattr(_wiring, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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


def _voice_first_should_engage_stranger(
    voice_id_result, face_available: bool, ambient_text: str, system_name: str
) -> bool:
    """Canary #4 Q2 — pure decision for the camera-off voice-first path: must the stranger
    engagement gate open a voice-only stranger?

    Returns False when a known speaker was established — by voice (`voice_id_result` truthy,
    a known session opened) OR by camera-fallback face (`face_available`) — because that
    session is opened and the gate is skipped. Returns True ONLY when NO known identity was
    established AND the user addressed the system by name (the genuine voice-only-stranger
    engagement signal).

    Mechanical extraction (P0.8) of the boolean inlined in `run()`'s voice-first block — the
    camera-fallback face recognition + the actual `_open_session` calls stay in `run()`; this
    is the testable decision only (GT-A/GT-B). No behavior change: it is equivalent to the
    `not _session_store.peek_all_snapshots()` guard at the stranger-open site, because (post
    Canary #4 B1) the only sessions opened by then are the known-voice or known-face ones."""
    if voice_id_result:            # voice ID established a known speaker → session opened
        return False
    if face_available:             # camera fallback recognized a known face → session opened
        return False
    return bool(_name_heard_in(ambient_text, system_name)[0])






# Extracts a name from natural-language phrases like "People call me Jagan".
# Searches ANYWHERE in the string (not just at start) for name-introducing patterns.
# Legacy prefix strip for simple cases like "My name is Jagan" at start of string.






# Spoken fallback when LLM calls a tool but returns no text.
# Every tool MUST have a non-empty fallback to prevent silent turns.
# Coverage enforced at pipeline.run() entry by the P0.S6 D3 startup assertion
# (registry equality with brain.TOOLS + non-empty stripped value gate).
_TOOL_FALLBACKS: dict[str, str] = {
    "update_person_name":       "Got it.",
    "update_system_name":       "What name would you like to give me?",
    "shutdown":                 "Goodbye!",
    "search_web":               "One moment.",
    "search_memory":            "Let me think about that.",
    # P0.S6 D3 — dispute-handler tools acknowledge-then-stay-quiet (Session 28
    # Issue A precedent). The dispute state machine + UI surface the dispute
    # itself; the spoken fallback should not commit to a position the dispute
    # hasn't resolved yet.
    "report_identity_mismatch": "Got it.",
    # P0.S6 D3 — read-only query tool; mirrors search_memory's fallback for
    # UX symmetry (the user shouldn't be able to tell from the fallback
    # whether the brain called per-person search_memory or per-room
    # search_room_memory).
    "search_room_memory":       "Let me think about that.",
}















# ── VISION_ROADMAP P1.4 — structured intent validator ────────────────────────
# Paired with the shadow classifier in core.brain._classify_intent (P1.3).
# Gated behind INTENT_FALLBACK_TO_REGEX=True: these helpers produce the
# SHADOW verdict; the existing regex gates (Sessions 71-74) remain the
# source of truth for mutation tool dispatch until P1.17 flips the flag.










# ── Cloud health state ─────────────────────────────────────────────────────────

_health_log_task:     asyncio.Task | None = None  # background health log loop






_voice_tasks:           "set[asyncio.Task]"         = set() # pending fire-and-forget voice accumulation tasks


def _voice_accum_done_callback(task: "asyncio.Task") -> None:
    """Done-callback for fire-and-forget voice accumulation tasks (Spec 2 Phase A, A3).

    Retrieves + LOGS any exception the task raised — previously a bare
    `_voice_tasks.discard` swallowed it silently, so an accumulation failure left no
    trace and the next canary couldn't see why the gallery wasn't filling. Then discards
    from the pending set. Never re-raises (a background-task failure must not crash the
    turn) and never silently swallows again (the doctrine standard)."""
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        _voice_tasks.discard(task)
        return
    if exc is not None:
        print(f"[Voice] accum task error: {type(exc).__name__}: {exc}")
    _voice_tasks.discard(task)
_vision_face_scan_last: float                       = 0.0   # throttle: secondary face recognition in background vision loop





def _primary_person_id() -> str | None:
    """Return the most recently active person's ID, or None if no active sessions."""
    _snaps = _wiring._session_store.peek_all_snapshots()
    if not _snaps:
        return None
    return max(_snaps, key=lambda s: (s.last_spoke_at, s.person_id)).person_id


def _primary_person_name() -> str | None:
    pid = _primary_person_id()
    if not pid:
        return None
    snap = _wiring._session_store.peek_snapshot(pid)
    return snap.person_name if snap is not None else None


def _kairos_preferred_speaker(best_friend_id: "str | None") -> "str | None":
    """P0.S7.D-D Stage 1 shim → RoomOrchestrator.kairos_preferred_speaker."""
    if _wiring._room_orchestrator is None:
        raise RuntimeError(
            "RoomOrchestrator not initialized — _init_room_orchestrator() "
            "must run first (production: from run(); tests: autouse fixture)"
        )
    return _wiring._room_orchestrator.kairos_preferred_speaker(best_friend_id)







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




async def _classify_intent_cached(
    text: str,
    history: "list[dict]",
    active_session_pids: "frozenset[str]",
) -> "dict | None":
    """Session 115 Fix 1 Layer B — cached wrapper around _classify_intent.

    Cache key normalizes text (lowercase + stripped) plus the active
    session pid set so a turn classified under one room scope doesn't
    leak into a different room. TTL and LRU eviction managed by CacheStore.
    """
    key = (text.strip().lower() if text else "", active_session_pids)
    cached = _classifier_cache_store.peek(key, default=CACHE_MISS)
    if cached is not CACHE_MISS:
        return cached
    # Spec 2 wiring: route through `_classify_intent_smart` so the
    # graph classifier runs in parallel under shadow mode (default).
    # In shadow mode, smart returns the LLM result so behavior is
    # unchanged; in primary/retired modes, smart returns graph results.
    from core.brain import _classify_intent_smart
    sidecar = await _classify_intent_smart(text, conversation_history=history)
    await _classifier_cache_store.set(key, sidecar)
    return sidecar


def _append_per_speaker_history(
    spans_with_pids: "list[tuple[str | None, str, str]]",
    primary_pid: "str | None",
    now_ts: float,
) -> None:
    """P0.S7.D-E γ targeted fix — append each non-primary speaker's segment
    text to their own ``_conversation_store._history``.

    Primary speaker's history is appended by ``conversation_turn`` with the
    combined transcript (existing behavior unchanged). This helper covers
    SECONDARY speakers whose in-memory history would otherwise miss the
    overlapping-speech utterance — so when a secondary speaker takes the
    next primary turn, their per-person history already reflects what
    they said during the multi-speaker burst.

    Invariants (MANDATORY, helper-enforced per Plan v2 §1.4):
      - Skip rows where ``pid`` is None (voice ID failed).
      - Skip rows where ``content`` is empty/whitespace-only.
      - Skip rows where ``pid == primary_pid`` (conversation_turn covers
        primary; double-write would silently duplicate).
      - DEDUP same-pid spans within the call via ``seen_pids: set[str]``
        (each speaker gets at most ONE history append per multi-speaker
        turn — inverse-check on the upstream merger invariant per
        Plan v2 §1.3).

    Fire-and-forget via ``create_task`` — never blocks the caller. Catches
    ``RuntimeError`` (no running loop in sync test contexts) silently.
    Helper-level exceptions are caught at the call site (Plan v2 §2.3
    try/except wrapper).
    """
    seen_pids: "set[str]" = set()
    try:
        _loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # OPTIONAL: no running loop in sync test contexts
    for _pid, _name, _content in spans_with_pids:
        if _pid is None:
            continue
        if not _content or not _content.strip():
            continue
        if _pid == primary_pid:
            continue
        if _pid in seen_pids:
            continue
        seen_pids.add(_pid)
        _loop.create_task(_conversation_store.append_turns(
            _pid,
            [{"role": "user", "content": _content, "ts": now_ts}],
        ))




# _effective_switch_threshold moved to core/reconciler.py (#176, Phase 3) —
# routing logic belongs alongside the cascade. Re-exported here for any
# remaining legacy callers; Phase 5 deletes those along with
# `_resolve_actual_speaker`.
from core.reconciler import _effective_switch_threshold  # noqa: E402, F401




# P0.10 Phase 2: _resolve_actual_speaker function deleted (was 270 lines
# spanning the original L1147-L1417). The new reconciler (core/reconciler.py)
# is the sole routing source post-Phase 2. Legacy router preserved as shadow
# during the Phase 4 cutover validation window; this deletion closes that
# window. Bug-W (0.45s phantom-stranger) was THE divergence the shadow
# caught — fixed in Phase 1 by adding _p0_short_utterance_gap_hold_current
# (Block A) to the cascade. See tests/p0_10_routing_audit.md for the full
# branch-mapping and tests/p0_10_plan_v2.md for the Plan v2 execution.


# P0.S7.1 observability — track the most recent _build_shared_context_block
# row count so the caller's `[Brain] Context:` summary line can surface the
# value as `shared_context=<N>`. Set on EVERY code path (0 on any skip; N on
# render) by `_build_shared_context_block` itself; AST-asserted (Test 3).
_last_shared_context_row_count: int = 0


def _build_shared_context_block(
    room_session_id: "str | None",
    requester_pid: str,
    best_friend_id: "str | None",
    db: "FaceDB",
    is_disputed_fn,
    active_session_count: int,
    limit: int = 10,
    now: "float | None" = None,
) -> "str | None":
    """P0.S7.D-D Stage 1 shim → RoomOrchestrator.build_shared_context_block."""
    if _wiring._room_orchestrator is None:
        raise RuntimeError(
            "RoomOrchestrator not initialized — _init_room_orchestrator() "
            "must run first (production: from run(); tests: autouse fixture)"
        )
    return _wiring._room_orchestrator.build_shared_context_block(
        room_session_id=room_session_id,
        requester_pid=requester_pid,
        best_friend_id=best_friend_id,
        db=db,
        is_disputed_fn=is_disputed_fn,
        active_session_count=active_session_count,
        limit=limit,
        now=now,
    )


def _fetch_recent_visitors_for_scene(best_friend_id: "str | None") -> "list[dict] | None":
    """Session 108 Phase 3A.7 — helper for SCENE block recent-visitor /
    safety-concern sections. Returns a list of VISITOR_ALERT nudge
    dicts for the owner (from the past SCENE_VISITOR_RECENCY_SECS
    window). Safe when orchestrator/bf_id unavailable — returns None
    so the scene block skips those sections cleanly.
    """
    if not best_friend_id or _wiring._brain_orchestrator is None:
        return None
    try:
        hours_back = SCENE_VISITOR_RECENCY_SECS / 3600.0
        return _wiring._brain_orchestrator.brain_db.get_recent_visitor_alerts(
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
    best_friend_id: "str | None" = None,
) -> "str | None":
    """P0.S7.D-D Stage 1 shim → RoomOrchestrator.build_room_block."""
    if _wiring._room_orchestrator is None:
        raise RuntimeError(
            "RoomOrchestrator not initialized — _init_room_orchestrator() "
            "must run first (production: from run(); tests: autouse fixture)"
        )
    return _wiring._room_orchestrator.build_room_block(
        active_sessions=active_sessions,
        conversation=conversation,
        emotion_agents=emotion_agents,
        room_start_ts=room_start_ts,
        turn_cap=turn_cap,
        now=now,
        best_friend_id=best_friend_id,
    )


def _fetch_recent_room_context(person_id: "str | None") -> "dict | None":
    """P0.S7.D-D Stage 1 shim → RoomOrchestrator.fetch_recent_room_context."""
    if _wiring._room_orchestrator is None:
        raise RuntimeError(
            "RoomOrchestrator not initialized — _init_room_orchestrator() "
            "must run first (production: from run(); tests: autouse fixture)"
        )
    return _wiring._room_orchestrator.fetch_recent_room_context(person_id)


















def _init_room_orchestrator() -> None:
    """P0.S7.D-D Stage 1 — production boot init for RoomOrchestrator.

    Called from ``run()`` AFTER all 6 dependencies are populated
    (FaceDB, BrainOrchestrator, stores, emotion agents). Layer 1
    defensive guard: ``face_db`` / ``brain_orchestrator`` (and the 3
    Store deps) MUST be non-None at production boot per the runtime
    ``raise RuntimeError`` checks below (Pre-P1 Bundle 3 MF5 migration
    2026-05-28: replaced 5 ``assert`` statements with explicit
    ``if not ...: raise RuntimeError(...)`` so the checks survive
    ``python -O`` invocation which strips asserts).

    In test fixtures (per ``tests/conftest.py`` autouse fixture), None
    args are tolerated — the ``RoomOrchestrator`` class stores deps
    without asserting; per-method None checks on the 3 dep-requiring
    methods (``build_shared_context_block``, ``fetch_recent_room_context``,
    ``on_room_end``) handle test-context None gracefully.

    The runtime raise below + docstring contract + Layer 3 None-handling
    together form defense-in-depth per the P0.S1 §1.4 layered-defense
    precedent.
    """
    global _room_orchestrator
    if not (_wiring._session_store is not None):
        raise RuntimeError('_init_room_orchestrator: _session_store must be initialized')
    if not (_wiring._pipeline_state_store is not None):
        raise RuntimeError('_init_room_orchestrator: _pipeline_state_store must be initialized')
    if not (_wiring._face_db_ref is not None):
        raise RuntimeError('_init_room_orchestrator: _face_db_ref must be set in run()')
    if not (_wiring._brain_orchestrator is not None):
        raise RuntimeError('_init_room_orchestrator: _brain_orchestrator must be set in run()')
    if not (_conversation_store is not None):
        raise RuntimeError('_init_room_orchestrator: _conversation_store must be initialized')
    _wiring._room_orchestrator = RoomOrchestrator(
        session_store=_wiring._session_store,
        pipeline_state_store=_wiring._pipeline_state_store,
        face_db=_wiring._face_db_ref,
        brain_orchestrator=_wiring._brain_orchestrator,
        conversation_store=_conversation_store,
        emotion_agents=_per_person_agent_store.peek_all_emotion_agents(),
    )












_vision_watchdog_task: "asyncio.Task | None" = None

# P0.R8 D6 — heavy-worker watchdog supervises the 4 pools (AdaFace + Whisper
# + ECAPA + Pyannote) created by the P0.R6.* arc. Spawned in run() AFTER
# vision_watchdog; cancelled FIRST at shutdown per ORDERING INVARIANT so
# it doesn't observe pool shutdown as crash events. Loop body uses bare
# `while True:` per P0.R3 actual at pipeline.py:2421; cancellation
# propagates via CancelledError through `await asyncio.sleep(...)` and
# breaks the loop cleanly at the shutdown explicit `.cancel()` +
# `wait_for(timeout=1.0)` pattern.
_heavy_worker_watchdog_task: "asyncio.Task | None" = None






# P0.R10 D3 — audio device watchdog supervises mic + speaker channels for
# device failure bursts. Spawned in run() AFTER heavy_worker_watchdog per
# consistent ordering with P0.R8 + P0.R3 precedents. Cancelled BEFORE
# heavy_worker_watchdog at shutdown per reverse-order invariant. Loop body
# uses bare `while True:` per P0.R3 actual at pipeline.py:2421 + P0.R8
# mirror at :2475 (CODE-TEMPLATE-MISIDENTIFICATION sub-shape preventive
# application — verified canonical reference shape).
_audio_device_watchdog_task: "asyncio.Task | None" = None







        # YOLO is NOT run here during conversation — PyTorch CPU ops hold the Python
        # GIL, which blocks httpx's async I/O callbacks and stalls LLM token streaming.
        # Object detection runs in the outer watching loop instead (idle time only).




async def _kairos_tick(person_id: str, person_name: str, db: "FaceDB", memory_search_fn: "Callable | None" = None, best_friend_id: str | None = None) -> bool:
    """Brain-driven proactive conversation (KAIROS).

    Wakes every KAIROS_SILENCE_THRESHOLD_SECS seconds of user silence and asks the
    main brain whether it wants to say something.  The brain decides freely —
    a thought, a question, noticing something — or stays silent.

    Returns True if the brain spoke; False otherwise.
    """
    if person_id.startswith("stranger_"):
        return False
    # Finding H — don't initiate proactive speech during an identity-disputed
    # session. We don't know who the speaker actually is; asking the brain to
    # start a fresh turn toward them would produce confused phrasing.
    if _is_disputed(person_id):
        return False
    if not _wiring._brain_orchestrator:
        return False

    now = time.monotonic()  # Canary #2 clock spec #4 — KAIROS elapsed-math (cooldown + silence)
    # P0.S7.3 — silence baseline = max(last_user_speech_at, _tts_end_time).
    # Bug pre-fix: `_silence_elapsed` accumulated from BEFORE the brain
    # started speaking, so a long TTS response (3+ min) made KAIROS fire
    # immediately on TTS-end. Resetting the baseline to the LATER of "last
    # user utterance" and "last brain-TTS end" gives the user real silence
    # time after each brain response before KAIROS re-engages.
    import core.audio as _audio_mod
    # Canary #2 clock spec #4: read the MONOTONIC companion (the wall-clock `_tts_end_time`
    # is for the echo window). max() with monotonic last_user_speech_at compares like-for-like.
    _last_tts_end = float(getattr(_audio_mod, "_tts_end_time_monotonic", 0.0))
    _last_user = _wiring._pipeline_state_store.peek_last_user_speech_at()
    _silence_baseline = max(_last_user, _last_tts_end)
    _silence_elapsed  = now - _silence_baseline
    _cooldown_elapsed = now - _wiring._pipeline_state_store.peek_last_kairos_at()

    if _silence_elapsed < KAIROS_SILENCE_THRESHOLD_SECS:
        return False
    if _cooldown_elapsed < KAIROS_COOLDOWN:
        return False

    # Offer the brain a pending pattern question as a suggestion, but let it
    # decide freely whether to use it, rephrase it, or say something else.
    pending_q = _wiring._brain_orchestrator.get_pending_question() if _wiring._brain_orchestrator else None
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

    # P0.S7.3 — surface which baseline drove the firing (TTS end vs user speech).
    _baseline_source = "tts_end" if _last_tts_end >= _last_user else "user_speech"
    print(f"[KAIROS] Brain proactive wake — {_silence_elapsed:.0f}s silence (baseline={_baseline_source})")

    history = list(_conversation_store.peek_history(person_id))

    _k_pif_view = {
        s.person_id: {"last_seen": s.last_seen, "name": s.name, "conf": s.conf, "source": s.source}
        for s in _presence_store.peek_all_snapshots()
    }
    _k_ut_view = {
        s.track_id: s.last_seen
        for s in _track_store.peek_all_snapshots()
        if s.last_seen > 0 and s.identity_pid is None
    }
    kairos_scene_block = (
        await _get_scene_block_cached(
            person_id, time.time(), _wiring._session_store.peek_all_snapshots(), _k_pif_view,
            _k_ut_view, best_friend_id,
            recent_visitors=_fetch_recent_visitors_for_scene(best_friend_id),
        )
        if SCENE_BLOCK_ENABLED else None
    )
    _kairos_snap     = _wiring._session_store.peek_snapshot(person_id) if person_id else None
    _kairos_rec_conf = _presence_store.peek_conf(person_id, 0.0) if person_id else 0.0
    kairos_vision_state = {
        "face_in_frame":          time.monotonic() - _wiring._pipeline_state_store.peek_last_face_seen() < 2.0,
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
        "active_session_count":   len(_wiring._session_store.peek_all_snapshots()),
        # Phase 3B.1: unified room-state block. Returns None in
        # single-person sessions so this field is benign there.
        # P0.S7.D-C: best_friend_id threaded for Section 1 role hierarchy
        # (disputed → best_friend → person_type).
        "room_block":             _build_room_block(
            _wiring._session_store.peek_all_snapshots(), _conversation_store._history, _per_person_agent_store.peek_all_emotion_agents(),
            _wiring._pipeline_state_store.peek_active_room_started_at(), turn_cap=ROOM_BLOCK_TURN_CAP,
            best_friend_id=best_friend_id,
        ),
        # P0.S7 D-A: <<<SHARED CONTEXT>>> persisted history. Returns None on
        # flag-off / single-person / no room / disputed caller.
        "shared_context":         _build_shared_context_block(
            room_session_id=(_kairos_snap.room_session_id if _kairos_snap is not None else None),
            requester_pid=person_id,
            best_friend_id=best_friend_id,
            db=db,
            is_disputed_fn=_is_disputed,
            active_session_count=len(_wiring._session_store.peek_all_snapshots()),
            limit=SHARED_CONTEXT_BLOCK_TURN_CAP,
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
                    system_name=_wiring._pipeline_state_store.peek_active_system_name(),
                    session_person_type=_kairos_snap.person_type,
                    session_user_turns=_kairos_snap.user_turns,
                    identity_disputed=_is_disputed(person_id),
                    person_name=person_name,
                    disputed_claimed_name=_kairos_snap.disputed_claimed_name,
                    core_memory=_kairos_snap.core_memory,
                )
                try:
                    _loop = asyncio.get_running_loop()
                    _loop.create_task(_wiring._session_store.set_cached_prefix(person_id, _kp_value))
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
                language=_wiring._pipeline_state_store.peek_detected_lang(),
                system_name=_wiring._pipeline_state_store.peek_active_system_name(),
                memory_search_fn=memory_search_fn,
                room_search_fn=_make_room_search_fn(
                    _wiring._pipeline_state_store.peek_active_room_session(), person_id, db,
                ),
                vision_state=kairos_vision_state,
                scene_block=kairos_scene_block,
                cached_prefix=_kairos_cached_prefix,
            ):
                if ev_type == "text":
                    response_parts.append(payload)
                    yield payload

        _set_state(PipelineState.SPEAKING, person_name)
        await speak_stream(_sentence_stream(_kairos_token_gen()), language=_wiring._pipeline_state_store.peek_detected_lang())
        response = "".join(response_parts).strip()

        # Brain chose silence — don't log, don't reset cooldown aggressively
        if not response or response.upper() == "SILENT":
            print(f"[KAIROS] Brain chose silence")
            try:
                asyncio.get_running_loop().create_task(_wiring._pipeline_state_store.set_last_kairos_at(time.monotonic()))
            except RuntimeError:
                asyncio.run(_wiring._pipeline_state_store.set_last_kairos_at(time.monotonic()))
            _set_state(PipelineState.LISTENING, person_name)
            return False

        print(f"[KAIROS] Brain spoke: {response[:60]!r}")
        await _conversation_store.append_turns(person_id, [
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
            _k_snap = _wiring._session_store.peek_snapshot(person_id)
            _k_room_sid = _k_snap.room_session_id if _k_snap is not None else None
            # P0.S7 T-B + MEDIUM 4 — full-room-audience (sites 1+2 share one
            # call; same logical turn).
            _k_audience = _compute_room_audience(
                _wiring._pipeline_state_store.peek_active_room_participants(),
                person_id,
            )
            db.log_turn(person_id, "user",      "[silence]",
                        room_session_id=_k_room_sid,
                        audience_ids=_k_audience)
            db.log_turn(person_id, "assistant", response,
                        room_session_id=_k_room_sid,
                        audience_ids=_k_audience)
            if _wiring._brain_orchestrator:
                _wiring._brain_orchestrator.notify()

    except Exception as e:
        print(f"[KAIROS] Stream failed: {e}")
        return False

    if pending_q:
        _wiring._brain_orchestrator.mark_question_asked(pending_q["id"])
    try:
        asyncio.get_running_loop().create_task(_wiring._pipeline_state_store.set_last_kairos_at(time.monotonic()))
    except RuntimeError:
        asyncio.run(_wiring._pipeline_state_store.set_last_kairos_at(time.monotonic()))

    _set_state(PipelineState.LISTENING, person_name)
    return True










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
        _wiring._shutdown_event.set()
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
    frames     = await camera.capture_frames_async(n=20, interval=0.3, stop_event=_wiring._shutdown_event)
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
        # P0.S1 D1 — capture verdict for the catch-all in add_embedding below.
        _fb_verdict = verify_live(frame, det.bbox, _wiring._anti_spoof_checker)
        if not _fb_verdict:
            print("[Pipeline] Anti-spoof: first_boot enrollment frame rejected — possible photo attack")
            spoof_blocked = True
            continue
        embedding = embedder.embed(face_crop)
        # P0.R1 D1: embed() now returns None on cascading CUDA+CPU failure.
        if embedding is None:
            print("[Pipeline] first_boot_flow: face embedding failed, skipping this enrollment frame")
            continue
        pending_embeddings.append((embedding, _fb_verdict))
        if photo_frame is None:
            photo_frame = frame

    if pending_embeddings:
        photo_path = None
        if photo_frame is not None:
            photo_path = str(FACES_DIR / f"{person_id}.jpg")
            cv2.imwrite(photo_path, photo_frame)
        db.add_person(person_id, display_name, photo_path, person_type='best_friend')
        for emb, _verdict in pending_embeddings:
            db.add_embedding(person_id, emb, "enrollment", anti_spoof_verdict=_verdict)
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

    await speak(f"Hi {name}! Please look at the camera and stay still for 5 seconds.", language=_wiring._pipeline_state_store.peek_detected_lang())

    person_id  = f"{safe_id}_{uuid.uuid4().hex[:6]}"
    frames = await camera.capture_frames_async(n=20, interval=0.3, stop_event=_wiring._shutdown_event)
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

        # Anti-spoofing: reject photo/screen attacks during enrollment.
        # P0.S1 D1 — capture verdict for the catch-all in add_embedding below.
        _en_verdict = verify_live(frame, det.bbox, _wiring._anti_spoof_checker)
        if not _en_verdict:
            print(f"[Pipeline] Anti-spoof: enrollment frame rejected for '{name}' — possible photo attack")
            spoof_blocked = True
            continue

        embedding = embedder.embed(face_crop)
        # P0.R1 D1: embed() now returns None on cascading CUDA+CPU failure.
        if embedding is None:
            print("[Pipeline] enrollment_flow: face embedding failed, skipping this enrollment frame")
            continue
        pending_embeddings.append((embedding, _en_verdict))
        if photo_frame is None:
            photo_frame = frame  # save first good frame for photo

    if pending_embeddings:
        photo_path = None
        if photo_frame is not None:
            photo_path = str(FACES_DIR / f"{person_id}.jpg")
            cv2.imwrite(photo_path, photo_frame)

        # M11: add_person before add_embedding to satisfy FK constraint
        db.add_person(person_id, name, photo_path, person_type=person_type)
        for emb, _verdict in pending_embeddings:
            db.add_embedding(person_id, emb, "enrollment", anti_spoof_verdict=_verdict)

        await speak(f"Got it! I'll remember you as {name}. Nice to meet you!", language=_wiring._pipeline_state_store.peek_detected_lang())
        print(f"[Pipeline] Enrolled {name} ({person_id}) with {len(pending_embeddings)} embeddings")
    else:
        if spoof_blocked:
            await speak("I couldn't verify that you're a real person. Please try again without any photos or screens.", language=_wiring._pipeline_state_store.peek_detected_lang())
        else:
            await speak("I couldn't get a clear view of your face. Please try again in better lighting.", language=_wiring._pipeline_state_store.peek_detected_lang())


















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
    if not _wiring._brain_orchestrator:
        return
    try:
        emb = await _wiring._brain_orchestrator.embed_query(text)
        if emb is not None:
            await _query_embedding_store.set(person_id, emb)
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
                system_name=_wiring._pipeline_state_store.peek_active_system_name(),
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
        if _wiring._brain_orchestrator:
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
            facts = _wiring._brain_orchestrator.brain_db.query_knowledge_for(
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

    # P0.8 tool-timeout rejection — surface to the brain so the retry can
    # acknowledge the action didn't land rather than confabulate completion.
    timed_out = [
        tc["name"] for tc in tool_calls
        if tool_results.get(tc["name"]) == "tool_timeout"
    ]
    if timed_out:
        parts.append(
            "Your previous tool call(s) timed out before completing: "
            f"{', '.join(repr(t) for t in timed_out)}. Any partial database "
            "writes were rolled back. Acknowledge the action did not complete "
            "and ask the user to try again — do NOT pretend the action "
            "succeeded or stay silent. Keep it to one short sentence."
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
    _ct_snap = _wiring._session_store.peek_snapshot(person_id)
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
        and not _conversation_store.is_compacting(person_id)
    ):
        async def _compact_history_background(_pid: str, _pname: str):
            try:
                _compacted = await autocompact_history(
                    _conversation_store.peek_history(_pid), _pname,
                )
                await _conversation_store.set_history(_pid, _compacted)
            except Exception as _cex:
                print(f"[Pipeline] autocompact background failed for {_pid}: {_cex!r}")
            finally:
                await _conversation_store.release_compact(_pid)

        await _conversation_store.add_compact(person_id)
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

    history    = list(_conversation_store.peek_history(person_id))
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
    if _STAY_SILENT and len(_wiring._session_store.peek_all_snapshots()) >= 2:
        # Session 115 Fix 1 — heuristic pre-check eliminates ~80% of
        # classifier calls. Vocative-name regex against active session
        # names. When the heuristic is confident, skip the classifier
        # entirely; when inconclusive, fall through to the cached path.
        _u2u_sidecar: "dict | None" = None
        _heuristic_decision: "tuple[str, str] | None" = None
        if _U2U_HEURISTIC:
            _other_names = {
                snap.person_name for snap in _wiring._session_store.peek_all_snapshots()
                if snap.person_id != person_id and snap.person_name
            }
            _heuristic_decision = _user_to_user_heuristic(
                text, _wiring._pipeline_state_store.peek_active_system_name(), _other_names,
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
                frozenset(s.person_id for s in _wiring._session_store.peek_all_snapshots()),
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
                and _addressed.lower() == (_wiring._pipeline_state_store.peek_active_system_name() or "").lower()
            )
            if _addressed and not _is_system_name:
                print(
                    f"[Pipeline] User-to-user detected — "
                    f"addressed to {_addressed!r}, staying silent"
                )
                # Preserve history + extraction. No TTS, no tool execution.
                _now_ts_u2u = time.time()                 # WALLCLOCK: history "ts" age-suffix display (room-block render)
                _now_ts_u2u_mono = time.monotonic()       # #5 Slice B (§0.1.5 SPLIT): last_spoke_at (VOICE_SESSION_TIMEOUT elapsed-math)
                history.append({
                    "role":    "user",
                    "content": text,
                    "ts":      _now_ts_u2u,
                })
                await _conversation_store.set_history(person_id, history)
                _room_sid_u2u = _ct_snap.room_session_id if _ct_snap is not None else None
                if db and not _is_disputed(person_id):
                    # P0.S7 T-B + MEDIUM 4 — full-room-audience (site 3 U2U).
                    _u2u_audience = _compute_room_audience(
                        _wiring._pipeline_state_store.peek_active_room_participants(),
                        person_id,
                    )
                    db.log_turn(
                        person_id, "user", text,
                        room_session_id=_room_sid_u2u,
                        audience_ids=_u2u_audience,
                    )
                    if _wiring._brain_orchestrator:
                        _wiring._brain_orchestrator.notify()
                # Bump user turn counter to keep session lifecycle consistent
                # with turns where the brain DID respond — other state reads
                # (stranger promotion thresholds, address-decision gating)
                # assume this field reflects every user utterance.
                try:
                    _loop = asyncio.get_running_loop()
                    _loop.create_task(_wiring._session_store.increment_user_turns(person_id))
                    _loop.create_task(_wiring._session_store.set_last_spoke_at(person_id, _now_ts_u2u_mono))
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
    cached_embedding = _query_embedding_store.peek(person_id)
    if _wiring._brain_orchestrator and not is_stranger and person_name:
        asyncio.create_task(_refresh_query_embedding(person_id, person_name, text))

    _bf_row = _get_best_friend_cached(db) if db else None
    _bf_id  = _bf_row["id"] if _bf_row else None

    memory_context = (
        _wiring._brain_orchestrator.get_context(
            person_name,
            query_embedding=cached_embedding,
            requester_person_id=person_id,
            best_friend_id=_bf_id,
        )
        if _wiring._brain_orchestrator and not is_stranger and person_name
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
        if _per_person_agent_store.peek_emotion_agent(person_id) is None:
            await _per_person_agent_store.set_emotion_agent(person_id, EmotionAgent())
        _cur_agent = _per_person_agent_store.peek_emotion_agent(person_id)

        async def _emotion_process_background(_pid: str, _pname: str, _agent, _text: str):
            try:
                _loop = asyncio.get_running_loop()
                await _loop.run_in_executor(None, _agent.process_turn, _text)
                if _wiring._brain_orchestrator and _agent.should_store_as_fact() and _pid:
                    _fact_val = _agent.get_fact_value()
                    if _fact_val:
                        _wiring._brain_orchestrator.store_temporal_fact(
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
        for _emo_pid, _emo_ag in _per_person_agent_store.peek_all_emotion_agents().items():
            if _wiring._session_store.peek_snapshot(_emo_pid) is None:
                continue
            _emo_snap_em = _wiring._session_store.peek_snapshot(_emo_pid)
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

    # Multi-person detection — `room=yes/no` sources from len(active) >= 2.
    # The <<<ROOM>>> (S113 P3B.1) + <<<SHARED CONTEXT>>> (P0.S7 D-A) blocks
    # carry the multi-person context; the legacy cross-person-excerpts block
    # was removed in SB.1 D2.4.
    _all_snaps_ct = _wiring._session_store.peek_all_snapshots()
    _multi_person = len(_all_snaps_ct) >= 2
    print(f"[Brain] Context: history={len(history)} turns, memory={'yes' if memory_context else 'no'}, emotion={'yes' if emotion_context else 'no'}, room={'yes' if _multi_person else 'no'}, scene={'yes' if SCENE_BLOCK_ENABLED else 'no'}, shared_context={_last_shared_context_row_count}")

    object_context = None

    # prompt_addendum_override takes precedence (used for stranger mode and similar).
    # Otherwise fall back to brain agent's learned prefs for this person.
    if prompt_addendum_override is not None:
        prompt_addendum = prompt_addendum_override
    else:
        prompt_addendum = (
            _wiring._brain_orchestrator.get_prompt_addendum(person_id)
            if _wiring._brain_orchestrator and not is_stranger and person_id
            else None
        )

    # SCENE sensor block — always-on snapshot of who is visible / audible,
    # injected into the system prompt on every turn.
    _ct_pif_view = {
        s.person_id: {"last_seen": s.last_seen, "name": s.name, "conf": s.conf, "source": s.source}
        for s in _presence_store.peek_all_snapshots()
    }
    _ct_ut_view = {
        s.track_id: s.last_seen
        for s in _track_store.peek_all_snapshots()
        if s.last_seen > 0 and s.identity_pid is None
    }
    scene_block = (
        await _get_scene_block_cached(
            person_id, time.time(), _wiring._session_store.peek_all_snapshots(), _ct_pif_view,
            _ct_ut_view, _bf_id,
            recent_visitors=_fetch_recent_visitors_for_scene(_bf_id),
        )
        if SCENE_BLOCK_ENABLED else None
    )

    # Proactive curiosity — pattern-question consumer (KAIROS path). The
    # object-pattern queue is no longer populated after SB.1 D1, so
    # get_pending_question() returns None here (harmless no-op read; the
    # path is kept per the CEO ruling, separate later cleanup).
    if _wiring._brain_orchestrator and not is_stranger:
        pending_q = _wiring._brain_orchestrator.get_pending_question()
        if pending_q:
            q_hint = (
                "\n- PROACTIVE CURIOSITY (ask this naturally when the moment feels right — "
                "only if the conversation is relaxed, do not force it):\n"
                f"  \"{pending_q['text']}\""
            )
            prompt_addendum = (prompt_addendum or "") + q_hint
            _wiring._brain_orchestrator.mark_question_asked(pending_q["id"])

    # ── Identity hint injection for stranger sessions ─────────────────────────
    # Hint is built from the PREVIOUS turn's scoring — always one turn delayed,
    # which is correct: we need conversation content before we can score.
    _id_h = _identity_hints_store.peek(person_id, default=CACHE_MISS)
    if is_stranger and _id_h is not CACHE_MISS:
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
    _cs = _wiring._pipeline_state_store.peek_cloud_state()
    if _cs == CloudState.SICK:
        # Grace period: try Together.ai — it might have recovered
        try:
            response, tool_calls = await ask(
                text,
                person_name=person_name,
                conversation_history=history,
                language=_wiring._pipeline_state_store.peek_detected_lang(),
                vision_state=vision_state,
                voice_state=voice_state,
                memory_context=memory_context,
                object_context=object_context,
                emotion_context=emotion_context,
                prompt_addendum=prompt_addendum,
                system_name=_wiring._pipeline_state_store.peek_active_system_name(),
                scene_block=scene_block,
            )
            # Recovered!
            asyncio.create_task(_wiring._pipeline_state_store.recover_online_no_flag())
            print("[Cloud] State: SICK → ONLINE (recovered mid-conversation)")
            print("[Pipeline] Together.ai recovered (detected mid-conversation)")
        except Exception:
            elapsed = time.monotonic() - _wiring._pipeline_state_store.peek_cloud_failed_at()
            if elapsed >= CLOUD_OFFLINE_TIMEOUT:
                print(f"[Cloud] State: SICK → OFFLINE (timeout={elapsed:.0f}s >= {CLOUD_OFFLINE_TIMEOUT}s)")
                asyncio.create_task(_wiring._pipeline_state_store.transition_to_offline())
                _cmt = _wiring._pipeline_state_store.peek_cloud_monitor_task()
                if _cmt is None or _cmt.done():
                    asyncio.create_task(_wiring._pipeline_state_store.set_cloud_monitor_task(
                        asyncio.create_task(_cloud_retry_loop())
                    ))
                response = await _ask_offline_safe(
                    text,
                    "I'm having some real trouble with my brain right now. "
                    "I can still chat, but I won't be my full self for a bit — bear with me.",
                    timeout=15.0,
                    person_name=person_name,
                    conversation_history=history,
                    language=_wiring._pipeline_state_store.peek_detected_lang(),
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
                    language=_wiring._pipeline_state_store.peek_detected_lang(),
                    system_note=(
                        "Your cloud connection is unstable right now. "
                        "Briefly mention you're a bit under the weather, then do your best to answer."
                    ),
                )

    elif _cs == CloudState.OFFLINE:
        # Ollama stateless Q&A — no memory, no tools
        response = await _ask_offline_safe(
            text,
            "Sorry, I'm really struggling right now — give me a moment.",
            timeout=30.0,
            person_name=person_name,
            conversation_history=history,
            language=_wiring._pipeline_state_store.peek_detected_lang(),
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
            _snap_conv = _wiring._session_store.peek_snapshot(person_id)
            if _snap_conv is not None:
                if _snap_conv.cached_prefix is None:
                    _cp_value = render_session_stable_prefix(
                        system_name=_wiring._pipeline_state_store.peek_active_system_name(),
                        session_person_type=_snap_conv.person_type,
                        session_user_turns=_snap_conv.user_turns,
                        identity_disputed=_is_disputed(person_id),
                        person_name=person_name,
                        disputed_claimed_name=_snap_conv.disputed_claimed_name,
                        core_memory=_snap_conv.core_memory,
                    )
                    try:
                        _loop = asyncio.get_running_loop()
                        _loop.create_task(_wiring._session_store.set_cached_prefix(person_id, _cp_value))
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
                    language=_wiring._pipeline_state_store.peek_detected_lang(),
                    vision_state=vision_state,
                    voice_state=voice_state,
                    memory_context=memory_context,
                    object_context=object_context,
                    emotion_context=emotion_context,
                    prompt_addendum=prompt_addendum,
                    system_name=_wiring._pipeline_state_store.peek_active_system_name(),
                    memory_search_fn=_memory_search,
                    room_search_fn=_make_room_search_fn(
                        _wiring._pipeline_state_store.peek_active_room_session(), person_id, db,
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
            await speak_stream(_sentence_stream(_token_gen()), language=_wiring._pipeline_state_store.peek_detected_lang())
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
                    and not tool_calls and _wiring._pipeline_state_store.peek_cloud_state() == CloudState.ONLINE):
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
                    language=_wiring._pipeline_state_store.peek_detected_lang(),
                )
                if len(_retry_resp) > len(response):
                    # Cut the first-response tail so user doesn't hear overlap.
                    stop_audio()
                    await speak(_retry_resp, language=_wiring._pipeline_state_store.peek_detected_lang())
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
                    language=_wiring._pipeline_state_store.peek_detected_lang(),
                )
                if _continuation and _continuation.strip():
                    # Original audio already finished playing — just speak the
                    # tail. Feels like the model paused and thought a moment.
                    await speak(_continuation, language=_wiring._pipeline_state_store.peek_detected_lang())
                    response = response.rstrip() + " " + _continuation.strip()

        except Exception as e:
            print(f"[Brain] Together.ai stream failed: {e}")
            print(f"[Cloud] State: ONLINE → SICK ({type(e).__name__})")
            _ct_failed_at = time.monotonic()
            asyncio.create_task(_wiring._pipeline_state_store.transition_to_sick(_ct_failed_at))
            _cmt2 = _wiring._pipeline_state_store.peek_cloud_monitor_task()
            if _cmt2 is None or _cmt2.done():
                asyncio.create_task(_wiring._pipeline_state_store.set_cloud_monitor_task(
                    asyncio.create_task(_cloud_retry_loop())
                ))
            response = await _ask_offline_safe(
                text,
                "Oops, I'm feeling a bit sick right now... give me a moment to sort myself out.",
                timeout=15.0,
                person_name=person_name,
                conversation_history=history,
                language=_wiring._pipeline_state_store.peek_detected_lang(),
                system_note=(
                    "Your cloud connection just went down unexpectedly. "
                    "Briefly mention you're having a brain hiccup and may not be fully yourself, "
                    "then do your best to answer."
                ),
            )

    # Shadow intent classifier (lazy, gated-tool only) -> flows.companion.turn_flows  [P1.A1 SP-7b.1]
    _intent_sidecar = await shadow_classify(text, history, tool_calls)

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
                system_name=_wiring._pipeline_state_store.peek_active_system_name(),
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
            if _shadow_sidecar is not None and _wiring._brain_orchestrator is not None:
                try:
                    _wiring._brain_orchestrator.brain_db.log_intent_divergence(
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
            _wiring._shutdown_event.set()
            break

    _any_tool_effective = any(r == "handled"      for r in _tool_results.values())
    _any_tool_noop      = any(r == "handled_noop" for r in _tool_results.values())
    # Session 71 unified "rejected" (Bugs S/T): "unknown" (hallucinated name)
    # and "rejected" (user-text gate failure) both mean the LLM wanted to act
    # but had no real grounding in the user's actual utterance. Both classes
    # route through the same Ollama-retry path.
    # P0.8: "tool_timeout" (handler exceeded its per-tool budget; task
    # cancelled, transaction rolled back via __aexit__) joins the same
    # retry path so the brain can acknowledge the action didn't complete.
    _all_unreal         = bool(tool_calls) and all(
        _tool_results.get(tc["name"]) in ("unknown", "rejected", "tool_timeout")
        for tc in tool_calls
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
            brain_orchestrator=_wiring._brain_orchestrator,
        )
        if _wiring._pipeline_state_store.peek_cloud_state() == CloudState.ONLINE:
            print("[Pipeline] All tool calls ungrounded — Together.ai retry (tools disabled, full context)")
            # P0.8.1: retry chain is structurally one-shot — ask_retry_text
            # passes include_tools=False (Session 99 architecture), so the
            # retry stream CANNOT propose another tool call.  No recursive
            # tool dispatch is possible; the retry-loop denial-of-service
            # concern raised by the P0.8 audit does not apply here.
            try:
                response = await ask_retry_text(
                    text,
                    person_name=person_name,
                    conversation_history=history,
                    language=_wiring._pipeline_state_store.peek_detected_lang(),
                    vision_state=vision_state,
                    voice_state=voice_state,
                    memory_context=memory_context,
                    object_context=object_context,
                    emotion_context=emotion_context,
                    prompt_addendum=prompt_addendum,
                    system_name=_wiring._pipeline_state_store.peek_active_system_name(),
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
                    language=_wiring._pipeline_state_store.peek_detected_lang(),
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
                language=_wiring._pipeline_state_store.peek_detected_lang(),
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
            response          = f"Got it, I'll go by {_wiring._pipeline_state_store.peek_active_system_name()}."
            response_streamed = False  # stop_audio() cut the stream — must speak canonical ack
        elif _override_tool == "update_person_name":
            _post_tool_snap = _wiring._session_store.peek_snapshot(person_id)
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

    effective_name = await history_persist(text, response, person_id, person_name, _addr_override, history)
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
    session_end_notify(db, person_id, text, response, _is_disputed_session, _room_sid)
    # ── Identity scoring for stranger sessions ────────────────────────────────
    # Fast keyword-matching against social mentions — no API calls.
    # Accumulates confidence across turns; thresholds drive the next turn's hint.
    if is_stranger and _wiring._brain_orchestrator:
        _id_hit = _wiring._brain_orchestrator.score_stranger_identity(
            _conversation_store.peek_history(person_id)
        )
        if _id_hit and _id_hit["confidence"] >= IDENTITY_SOFT_THRESHOLD:
            await _identity_hints_store.set(person_id, _id_hit)
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
                    for _msg in _conversation_store.peek_history(person_id):
                        _msg["content"] = _old_pat.sub(_id_name, _msg["content"])
                    if _wiring._brain_orchestrator:
                        _wiring._brain_orchestrator.on_identity_confirmed(person_id, _old_name, _id_name)
                    if _wiring._session_store.peek_snapshot(person_id) is not None:
                        try:
                            _loop = asyncio.get_running_loop()
                            _loop.create_task(_wiring._session_store.rename(person_id, _id_name))
                            _loop.create_task(_wiring._session_store.promote_type(person_id, "known"))
                            _loop.create_task(_wiring._session_store.set_cached_prefix(person_id, None))
                            _loop.create_task(_wiring._session_store.set_waiting_for_name(person_id, False))
                        except RuntimeError:
                            pass  # OPTIONAL
                    await _identity_hints_store.discard(person_id)
                    print(f"[Identity] Auto-confirmed: {_id_name} (conf={_id_conf:.2f})")

    _set_state(PipelineState.SPEAKING, effective_name)
    if response and not response_streamed:
        await speak(response, language=_wiring._pipeline_state_store.peek_detected_lang())

    print(f"[Pipeline] Turn end {_now_log_ts()}: {effective_name} — {len(response)} chars")
    return ("continue", None)


# P0.R6.Z D3.c RETIREMENT (2026-05-24): `_warm_pyannote_via_dedicated_executor`
# retired. Pyannote pipeline now lives subprocess-side at
# `core/heavy_worker.py::_get_subprocess_pyannote()`; main-process warm-up
# happens via `hw.get_or_create_pool("pyannote_diarize")` in the run() startup
# 4-pool block (alongside AdaFace + Whisper + ECAPA).


async def _warmup_models(loop: asyncio.AbstractEventLoop) -> None:
    """Pre-load lazy models so the first user turn pays no cold-start cost.

    Already-eager models (RetinaFace, AdaFace, MiniFASNet, Whisper, Kokoro,
    Emotion) are not touched — they're loaded earlier in run().
    E5 has its own warmup block (S120); this covers ECAPA only post-P0.R6.Z
    (pyannote moved to subprocess pool warm-up in run()).
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
        # ECAPA speaker embedder — load_speaker_embedder is idempotent if
        # already loaded. P0.R6.Y migrated ECAPA inference to subprocess;
        # this main-process loader is now a no-op for the inference path
        # but kept for backward compat with the few remaining main-process
        # _embedder references in core/voice.py.
        _warm("ECAPA", voice_mod.load_speaker_embedder),
    ]

    await asyncio.gather(*tasks, return_exceptions=True)
    print(f"[Warmup] complete — {time.time() - overall_t0:.2f}s total")


async def _warm_heavy_worker_pools() -> None:
    """Canary #2 / latency D2 — force the lazy model-load in each heavy-worker
    subprocess at boot so the user's FIRST turn pays no cold-start cost.

    `get_or_create_pool` (and run_heavy's internal pool-resolve) only SPAWNS the
    subprocess; each model loads lazily on the FIRST real `run_heavy` call. Without
    this warm, the canary's first STT was ~20s (cold Whisper subprocess load) and the
    first diarize ~23s (cold pyannote). One dummy inference per pool forces the load
    NOW. Parallelized via `asyncio.gather` so boot cost ≈ the slowest single pool
    (~pyannote 23s), not the sum. Each warm is non-fatal (try/except) — a degraded pool
    (P0.R9 VRAM refusal → `run_heavy` returns None) must not block boot.

    MUST be awaited BEFORE '[Pipeline] All systems ready' — backgrounding it loses the
    race against a user who speaks ~3s after boot (the canary #2 failure mode).

    Dummy arg shapes cribbed VERBATIM from the real call sites so each matches its
    worker signature:
      adaface_embed     pipeline.py:2916  (crop.tobytes(), crop.shape)                  uint8 HxWx3
      whisper_transcribe core/audio.py:584 (.tobytes(), .shape, .dtype.name, language=)  float32
      ecapa_embed       core/voice.py:129  (.tobytes(), .shape, .dtype.name, sample_rate) float32
      pyannote_diarize  core/voice.py:297  (.tobytes(), .shape, .dtype.name, sample_rate) float32
    """
    import core.heavy_worker as hw  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    from core.config import MIC_SAMPLE_RATE, SPEAKER_LANGUAGES  # noqa: PLC0415

    _crop = np.zeros((112, 112, 3), dtype=np.uint8)   # dummy face crop (AdaFace)
    _wav1 = np.zeros(16000, dtype=np.float32)          # ~1.0s silence (Whisper)
    _wav15 = np.zeros(24000, dtype=np.float32)         # ~1.5s silence (ECAPA)
    _wav2 = np.zeros(32000, dtype=np.float32)          # ~2.0s silence (pyannote)

    async def _warm(label: str, make_coro) -> None:
        _t0 = time.perf_counter()  # perf_counter (not time.time) — elapsed timing, not a clock value
        try:
            await make_coro()
            print(f"[Warmup] {label} pool warm — {time.perf_counter() - _t0:.1f}s")
        except Exception as e:
            print(f"[Warmup] {label} pool warm skipped (non-fatal): {type(e).__name__}: {e!r}")

    print("[Warmup] warming heavy-worker subprocess pools (first-turn cold-start fix)...")
    await asyncio.gather(
        _warm("adaface_embed", lambda: hw.run_heavy(
            "adaface_embed", hw.adaface_embed_worker, _crop.tobytes(), _crop.shape)),
        _warm("whisper_transcribe", lambda: hw.run_heavy(
            "whisper_transcribe", hw.whisper_transcribe_worker,
            _wav1.tobytes(), _wav1.shape, _wav1.dtype.name, language=SPEAKER_LANGUAGES[0])),
        _warm("ecapa_embed", lambda: hw.run_heavy(
            "ecapa_embed", hw.ecapa_embed_worker,
            _wav15.tobytes(), _wav15.shape, _wav15.dtype.name, MIC_SAMPLE_RATE)),
        _warm("pyannote_diarize", lambda: hw.run_heavy(
            "pyannote_diarize", hw.pyannote_diarize_worker,
            _wav2.tobytes(), _wav2.shape, _wav2.dtype.name, MIC_SAMPLE_RATE)),
    )


async def run():
    """Main pipeline loop."""
    global _brain_orchestrator, _vision_face_scan_last  # P1.A1 SP-6.4: _shutdown_event WIRE-d (_wiring._X)

    # ── P0.S2 dashboard auth token (FIRST line — before any other boot work) ──
    # Generates or self-heals the single-user auth token used by the Next.js
    # dashboard's middleware + `/api/auth` route. On first launch, also writes
    # the one-shot `.dashboard_auth_url` file (mode 0600) — pipeline.run()
    # MUST surface the auth URL before any subsystem can fail, otherwise the
    # user has no recovery path. See `tests/p0_s2_plan_v2.md` for spec.
    from core.dashboard_token import _ensure_dashboard_token
    _ensure_dashboard_token(FACES_DIR)

    # ── P0.S3 env-var validation ──────────────────────────────────────────────
    # ORDERING INVARIANT: validate_required_env() MUST run BEFORE any cloud or
    # network probe. Future specs adding network reachability checks (e.g.,
    # Together.ai ping at startup, Tavily key liveness check) MUST land AFTER
    # this call so misleading network errors don't mask the actionable
    # "TOGETHER_API_KEY is empty" message.
    #
    # ORDERING vs P0.S2: validate_required_env() runs AFTER _ensure_dashboard_token
    # so that even if env validation raises, the dashboard token + auth URL
    # files are already on disk. User fixes env, restarts, dashboard auth
    # works (no chicken/egg recovery loop).
    #
    # Spec: tests/p0_s3_plan_v1.md §1.P3 (ordering convention locked at the
    # call site so future maintainers grepping for "ORDERING INVARIANT" find
    # both invariants at the surface they actually affect).
    from core.env_validation import validate_required_env
    validate_required_env()

    # ── Tool-registry integrity checks (P0.S2/S3/S6 ORDERING INVARIANTS) ──────
    # Validate brain.TOOLS is consistent with the privilege / intent / fallback /
    # handler registries. Runs AFTER validate_required_env() (env errors surface
    # first — the env-before-tool-registry ordering is enforced here at the call
    # site). Engine logic lives in runtime/boot_checks.py; companion registries
    # passed in.  [P1.A1 SP-7a]
    from core.brain import TOOLS as _BRAIN_TOOLS
    from runtime.boot_checks import validate_tool_registries
    validate_tool_registries(_BRAIN_TOOLS, _TOOL_FALLBACKS, _TOOL_HANDLERS)

    # ── Shutdown event (must be created inside the running loop) ──────────────
    _wiring._shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    # ── KAIROS silence/cooldown clocks — initialize to now so Kairos doesn't fire
    # immediately at startup before the user has said anything. Without this,
    # _last_user_speech_at=0.0 makes the silence gate pass on the very first tick.
    await _wiring._pipeline_state_store.set_last_user_speech_at(time.monotonic())
    await _wiring._pipeline_state_store.set_last_kairos_at(time.monotonic())

    _sigint_count = 0

    def _request_shutdown(signum=None, frame=None):
        """Sync-safe handler: schedules shutdown on first press, force-exits on second.
        The force-exit path handles the case where the loop is stuck in a long
        blocking await (e.g. listen_and_transcribe up to 30s) and won't respond."""
        nonlocal _sigint_count
        _sigint_count += 1
        if _sigint_count == 1:
            print("\n[Pipeline] Ctrl+C received — shutting down gracefully...")
            loop.call_soon_threadsafe(_wiring._shutdown_event.set)
        else:
            print("\n[Pipeline] Forced exit.")
            os._exit(1)

    signal.signal(signal.SIGINT, _request_shutdown)
    if sys.platform != "win32":
        # add_signal_handler is asyncio-native and safe on Linux/macOS (Jetson).
        # Not available on Windows ProactorEventLoop.
        loop.add_signal_handler(signal.SIGTERM, _wiring._shutdown_event.set)

    print("[Pipeline] Starting...")
    state.write(mode="starting")

    camera          = Camera(CAMERA_INDEX)
    detector        = FaceDetector()
    embedder        = FaceEmbedder()
    db              = FaceDB()
    temporal_buffer = TemporalEmbeddingBuffer(max_frames=5)
    global _face_db_ref
    _wiring._face_db_ref    = db  # Obs 1: module-level helpers (e.g. _open_session) read DB for voice count fallback
    _bf_row = _get_best_friend_cached(db)
    _bf_id  = _bf_row["id"] if _bf_row else None

    # Load system identity — name given by user persists across sessions.
    # Guard: reject any invalid/placeholder names that may have been stored by a misfiring tool.
    _loaded_name = db.get_system_identity("system_name") or DEFAULT_SYSTEM_NAME
    if _loaded_name.lower() in _INVALID_SYSTEM_NAMES:
        print(f"[Pipeline] System name '{_loaded_name}' is invalid — resetting to default.")
        db.set_system_identity("system_name", DEFAULT_SYSTEM_NAME, set_by="system", note="auto-reset invalid name")
        await _wiring._pipeline_state_store.set_active_system_name(DEFAULT_SYSTEM_NAME)
    else:
        await _wiring._pipeline_state_store.set_active_system_name(_loaded_name)
    if _wiring._pipeline_state_store.peek_active_system_name() != DEFAULT_SYSTEM_NAME:
        print(f"[Pipeline] System name: {_wiring._pipeline_state_store.peek_active_system_name()}")

    print("[Pipeline] Preloading audio models...")
    preload_models()

    # Load voice recognizer and build in-memory gallery from DB
    voice_mod.load_speaker_embedder()
    await _voice_gallery_store.load_bulk(db.load_voice_profiles(), db.load_voice_profile_sizes())
    print(f"[Voice] Gallery loaded — {_voice_gallery_store.peek_len()} person(s) with voice profiles")

    # Anti-spoofing — optional MiniFASNet liveness gate for enrollment + recognition
    # P1.A1 SP-6.3: _anti_spoof_checker is WIRE-d (runtime.wiring); set via _wiring._X below.
    if ANTISPOOFING_ENABLED:
        _wiring._anti_spoof_checker = AntiSpoofChecker(threshold=ANTISPOOFING_THRESHOLD)

    # Emotion agents — preload the shared HuggingFace pipeline so
    # the first conversation turn isn't blocked by the 15-25ms model-load.
    await _per_person_agent_store.clear_emotion_agents()
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
    _wiring._brain_orchestrator = BrainOrchestrator(_wiring._shutdown_event)
    _wiring._brain_orchestrator.set_system_name(_wiring._pipeline_state_store.peek_active_system_name())
    _brain_task = asyncio.create_task(_wiring._brain_orchestrator.run())

    # P0.S7.D-D Stage 1 — init RoomOrchestrator after all 6 deps are
    # populated. Production Layer 1 defense (assert all deps non-None).
    # Tests use the autouse fixture init path in conftest.py.
    _init_room_orchestrator()

    # Anti-spoof observability: stamp state.json and watchdog alert when disabled.
    _as_enabled = _wiring._anti_spoof_checker is not None and _wiring._anti_spoof_checker.available
    state.set_persistent("anti_spoof_enabled", _as_enabled)
    if ANTISPOOFING_ENABLED and not _as_enabled:
        print("[SECURITY] WARNING: Anti-spoofing DISABLED — photo / screen-replay attacks will "
              "succeed. Install silent-face-anti-spoofing to enable.")
        _wiring._brain_orchestrator.report_antispoof_disabled()
    elif not ANTISPOOFING_ENABLED:
        print("[Security] Anti-spoofing disabled by config (ANTISPOOFING_ENABLED=False)")
    asyncio.create_task(_dream_loop(db))
    global _health_log_task
    _health_log_task = asyncio.create_task(_health_log_loop(asyncio.get_event_loop()))

    # Canary #2 / latency D2 — warm the 4 heavy-worker subprocess pools (force lazy
    # model-load) BEFORE declaring ready, so the user's first turn is genuinely warm.
    # Awaited (NOT backgrounded): a backgrounded warm loses the race against a user who
    # speaks ~3s after boot. Boot takes ~20-25s longer here (parallel cold-loads,
    # pyannote-dominated) — the intended trade vs a 40s cold-start mid-first-turn.
    await _warm_heavy_worker_pools()

    # Canary #2 / latency D5a — boot health-check: warn LOUDLY if Ollama is unreachable
    # so the operator knows the OFFLINE fallback is dead BEFORE the cloud goes SICK (the
    # canary saw Ollama 500, silently dead-ending _ask_offline_safe + the greeting fallback).
    # Non-fatal — do not block boot.
    try:
        from core.brain import ping_ollama
        if not await ping_ollama():
            from core.config import OLLAMA_URL as _OLLAMA_URL, OLLAMA_MODEL as _OLLAMA_MODEL
            print(
                f"[Warmup] WARNING — Ollama unreachable at {_OLLAMA_URL}; offline fallback "
                f"DISABLED. Run 'ollama serve' + 'ollama pull {_OLLAMA_MODEL}'."
            )
    except Exception as _ollama_probe_err:
        print(f"[Warmup] Ollama health-check skipped (non-fatal): {_ollama_probe_err!r}")

    # ── SB.1 D4.2 — KaraOS instance-mode boot declaration ─────────────────────
    # Documents deployment intent (base = cloneable/publishable; personal =
    # Jagan's local instance). Lightweight: log only. Write-path enforcement
    # lands in SB.5. Flag a typo'd env override (not in VALID_INSTANCE_MODES)
    # without crashing — SB.1 is documentation-only.
    _instance_mode = config.KARAOS_INSTANCE_MODE
    if _instance_mode not in config.VALID_INSTANCE_MODES:
        print(
            f"[Config] WARNING — KARAOS_INSTANCE_MODE={_instance_mode!r} is not one of "
            f"{config.VALID_INSTANCE_MODES}; treating as 'base'. (SB.1 D4.2)"
        )
        _instance_mode = "base"
    print(f"[Config] instance_mode={_instance_mode}")

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
    # Main loop reads from _vision_frame_store.peek_frame (written by this task).
    # Eliminates thread-unsafe concurrent cv2.VideoCapture reads on Windows.
    #
    # P0.R3 D5 — capture refs at module scope BEFORE spawning the task, so D4
    # `_restart_vision_task()` can respawn `_background_vision_loop` with the
    # same arguments. `_vision_task` replaces the prior `_vis_bg_task` local
    # so the watchdog can mutate it on respawn.
    global _vision_watchdog_task  # P1.A1 SP-6.3: _vision_task WIRE-d (set via _wiring._vision_task)
    # P1.A1 SP-6.3: push boot-constructed vision deps into vision_loop's namespace;
    # _restart_vision_task reads them on respawn — canary-validated only (run()-set state,
    # constructed at live boot, suite-blind; the 5 refs are move-with globals in runtime.vision_loop).
    _vl._vision_camera_ref = camera
    _vl._vision_detector_ref = detector
    _vl._vision_embedder_ref = embedder
    _vl._vision_temporal_buffer_ref = temporal_buffer
    _vl._vision_db_ref = db
    # P0.R6 D5 — warm up the AdaFace heavy-worker pool BEFORE vision task
    # spawn. The vision loop's first iteration will call `hw.run_heavy(
    # "adaface_embed", ...)` (D3 migration sites 1+2); the worker subprocess
    # must be ready when that first call fires. Without this warm-up the
    # first inference call pays the subprocess + model-load latency
    # synchronously on the awaiting coroutine.
    hw.get_or_create_pool("adaface_embed")
    # Mark the pool as healthy in the observability surface (D4 health
    # snapshot). Subsequent crashes flip this to "degraded" via worker
    # lifecycle detection (future P0.R6.X follow-up may add per-call
    # health updates; foundation cycle just sets the initial state).
    asyncio.create_task(_wiring._pipeline_state_store.set_heavy_worker_status("adaface_embed", "healthy"))
    # P0.R6.X D4 — warm up the Whisper heavy-worker pool BEFORE vision task
    # spawn (same ordering invariant as adaface_embed above). Whisper does
    # NOT use a ProcessPoolExecutor initializer (worker lazy-loads the model
    # on first call via `_get_subprocess_whisper()`); minting the pool here
    # just creates the subprocess. The first `await transcribe(...)` call
    # from `listen_and_transcribe` pays the ~1-2s WhisperModel load on the
    # subprocess, NOT on the awaiting coroutine — the asyncio loop stays
    # responsive while the subprocess warms.
    hw.get_or_create_pool("whisper_transcribe")
    asyncio.create_task(_wiring._pipeline_state_store.set_heavy_worker_status("whisper_transcribe", "healthy"))
    # P0.R6.Y D4 — warm up the ECAPA heavy-worker pool BEFORE vision task
    # spawn (same ORDERING INVARIANT as AdaFace + Whisper above). The
    # subprocess lazy-loads the SpeechBrain EncoderClassifier on first
    # call via `_get_subprocess_ecapa()` — minting the pool here just
    # creates the subprocess. Voice ID is called from `_background_vision_
    # loop`'s downstream paths (per-turn voice ID at site 7414) AND from
    # the ambient-listen voice-first path (site 7148 LOAD-BEARING fix);
    # both must see the subprocess ready when their first `await
    # voice_mod.identify(...)` call fires.
    hw.get_or_create_pool("ecapa_embed")
    asyncio.create_task(_wiring._pipeline_state_store.set_heavy_worker_status("ecapa_embed", "healthy"))
    # P0.R6.Z D4 — warm up the Pyannote heavy-worker pool BEFORE vision task
    # spawn (4-pool ORDERING INVARIANT — AdaFace → Whisper → ECAPA →
    # Pyannote → vision_task). The subprocess lazy-loads the
    # `pyannote/speaker-diarization-3.1` Pipeline on first call via
    # `_get_subprocess_pyannote()`; minting the pool here creates the
    # subprocess. Pyannote inference is invoked from
    # `core/voice.py::_diarize_pyannote()` → `hw.run_heavy(
    # "pyannote_diarize", ...)` during multi-speaker scene segmentation
    # (per-turn diarize call in conversation_turn). Worker subprocess
    # serializes pyannote `Annotation` → `list[tuple[float, float, str]]`
    # subprocess-side per Q2 (a) lock so the main process stays free of
    # pyannote imports. 4-task heavy-worker migration arc COMPLETES with
    # this pool (P0.R6 AdaFace + P0.R6.X Whisper + P0.R6.Y ECAPA +
    # P0.R6.Z Pyannote = full cognitive runtime asyncio-loop-release).
    hw.get_or_create_pool("pyannote_diarize")
    asyncio.create_task(_wiring._pipeline_state_store.set_heavy_worker_status("pyannote_diarize", "healthy"))
    _wiring._vision_task = asyncio.create_task(
        _background_vision_loop(camera, detector, embedder, temporal_buffer, db)
    )
    # P0.R3 D5 — spawn watchdog AFTER vision task (D2 needs vision task to exist
    # before supervising). D5 ordering invariant: watchdog cancelled BEFORE
    # vision at shutdown (see finally block).
    _vision_watchdog_task = asyncio.create_task(_vision_watchdog_loop())
    # P0.R8 D6 — spawn heavy-worker watchdog AFTER vision_watchdog. Watches
    # the 4 pools (AdaFace/Whisper/ECAPA/Pyannote) for BrokenProcessPool
    # crash bursts via `hw.count_recent_crashes`; degrades pool + dispatches
    # WatchdogAgent alert when crash count exceeds threshold within the
    # rolling burst window. ORDERING INVARIANT at shutdown: this task
    # cancels FIRST (before vision_watchdog) so it doesn't observe pool
    # shutdown as crash events.
    global _heavy_worker_watchdog_task
    _heavy_worker_watchdog_task = asyncio.create_task(_heavy_worker_watchdog_loop())
    # P0.R10 D3 — spawn audio device watchdog AFTER heavy_worker_watchdog per
    # consistent ordering with P0.R8 + P0.R3 precedents. Watches mic + speaker
    # channels for device failure bursts via `count_recent_audio_failures`;
    # dispatches WatchdogAgent alert when failure count exceeds threshold
    # within the rolling burst window. ORDERING INVARIANT at shutdown: this
    # task cancels BEFORE heavy_worker_watchdog (reverse-order shutdown).
    global _audio_device_watchdog_task
    _audio_device_watchdog_task = asyncio.create_task(_audio_device_watchdog_loop())
    await asyncio.sleep(0.1)  # let background loop capture its first frame

    _null_frame_streak  = 0
    _reconnect_delay    = 2.0   # seconds; doubles each failed attempt, caps at 60


    # Prune stale silent observations at startup (runs once, fast)
    db.prune_silent_observations()

    try:
        while not _wiring._shutdown_event.is_set():
            # ── Dashboard enroll request ───────────────────────────────────────
            if _wiring._pipeline_state_store.peek_pipeline_state() == PipelineState.WATCHING and ENROLL_REQUEST_FILE.exists():
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
            if _wiring._pipeline_state_store.peek_pipeline_state() == PipelineState.WATCHING and RESET_REQUEST_FILE.exists():
                RESET_REQUEST_FILE.unlink(missing_ok=True)
                print("[Reset] Factory reset triggered — wiping all data...")
                state.write(mode="resetting")

                # Step 1: clear all in-memory state while connections are still valid
                _wiring._brain_orchestrator.wipe()

                # Step 2: close ALL file handles so wipe_all() can delete on Windows
                db.close()  # idempotent; CLEANUP swallow lives in FaceDB.close()
                _wiring._brain_orchestrator.close_connections()

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
                _wiring._face_db_ref    = db  # Obs 1: re-point module-level ref after factory reset
                # Session 115 Fix 2 — invalidate bf cache before next read; the
                # FaceDB instance just changed so the cached id() is stale.
                _invalidate_bf_cache()
                _bf_row = _get_best_friend_cached(db)
                _bf_id  = _bf_row["id"] if _bf_row else None

                # Step 5: re-open BrainOrchestrator connections to fresh DB files
                _wiring._brain_orchestrator.reopen_connections()

                # Clear all runtime state
                await _conversation_store.clear_all_greeted()
                await _conversation_store.clear_all_self_update()
                await _conversation_store.clear_all_history()
                await _voice_gallery_store.clear()
                await _per_person_agent_store.clear_sessions_started()
                for _snap_rst in _wiring._session_store.peek_all_snapshots():
                    try:
                        _loop = asyncio.get_running_loop()
                        _loop.create_task(_wiring._session_store.close_session(_snap_rst.person_id))
                    except RuntimeError:
                        pass  # OPTIONAL
                await _scene_block_store.clear()  # Wave 6 Item 23
                _wiring._pipeline_state_store.reset()      # P0.6.6

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

            frame = _vision_frame_store.peek_frame_if_fresh(0.5, time.monotonic())
            if frame is None:
                _null_frame_streak += 1
                if _null_frame_streak >= 30:
                    print(f"[Pipeline] Camera: {_null_frame_streak} consecutive null frames — reconnecting...")
                    state.write(mode="reconnecting")
                    if _wiring._brain_orchestrator:
                        _wiring._brain_orchestrator.report_camera_null_streak(_null_frame_streak)
                    if camera.reconnect():
                        print("[Pipeline] Camera reconnected.")
                        _null_frame_streak = 0
                        _reconnect_delay   = 2.0
                        state.write(mode="watching")
                        if _wiring._brain_orchestrator:
                            _wiring._brain_orchestrator.report_camera_recovered()
                    else:
                        print(f"[Pipeline] Camera reconnect failed — retrying in {_reconnect_delay:.0f}s")
                        try:
                            await asyncio.wait_for(_wiring._shutdown_event.wait(), timeout=_reconnect_delay)
                        except asyncio.TimeoutError:
                            pass
                        _reconnect_delay = min(_reconnect_delay * 2, 60.0)
                else:
                    await asyncio.sleep(0.1)
                continue

            _null_frame_streak = 0

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
                # P0.R6 D3 (Site 3, was line 6716): converted from SYNC direct
                # call (`embedder.embed(face_crop)` blocked the asyncio loop for
                # the duration of inference, ~50-100ms per call) to async via
                # ProcessPoolExecutor worker pool. Non-blocking improvement per
                # PI #1 absorption (Plan v1 §1.1 Option α expanded scope).
                raw_embedding_bytes = await hw.run_heavy(
                    "adaface_embed",
                    hw.adaface_embed_worker,
                    face_crop.tobytes(),
                    face_crop.shape,
                )
                raw_embedding = (
                    np.frombuffer(raw_embedding_bytes, dtype=np.float32)
                    if raw_embedding_bytes is not None
                    else None
                )
                # P0.R1 D1: embed() now returns None on cascading CUDA+CPU failure.
                if raw_embedding is None:
                    print("[Pipeline] background scan: face embedding failed, skipping frame")
                    continue
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
                        try:
                            asyncio.get_running_loop().create_task(
                                _track_store.bind_identity(det.track_id, person_id)
                            )
                        except RuntimeError:
                            pass  # OPTIONAL: no running loop in test context
                else:
                    print(f"[Vision] Face score={conf:.3f} (need ≥{threshold:.3f}) — unrecognized")
                    # Silent observation: accumulate face data without engagement.
                    if not _wiring._session_store.peek_all_snapshots():
                        _maybe_record_silent_obs(embedding, det.bbox, frame.shape[1], frame.shape[0], db)

                    # Track-continuity: if this SORT track was previously recognized as a
                    # specific person, maintain that identity across brief occlusion.
                    # Replaces soft-match (which mapped any unrecognized face to the current
                    # session holder — the gallery-poisoning root cause).
                    if det.track_id is not None:
                        _tracked_pid = _track_store.peek_identity(det.track_id)
                        if _tracked_pid and _wiring._session_store.peek_snapshot(_tracked_pid) is not None:
                            person_id   = _tracked_pid
                            _tc_snap = _wiring._session_store.peek_snapshot(_tracked_pid)
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
                        last = _conversation_store.peek_last_self_update(person_id)
                        if time.monotonic() - last >= SELF_UPDATE_COOLDOWN and conf >= SELF_UPDATE_THRESHOLD:
                            _anti_spoof_ok = (
                                _wiring._anti_spoof_checker is not None
                                and getattr(_wiring._anti_spoof_checker, "available", False)
                                and verify_live(frame, det.bbox, _wiring._anti_spoof_checker)
                            )
                            if not _anti_spoof_ok:
                                # Fail-closed: skip the write when liveness is unavailable or failed.
                                # Avoid log spam by throttling with the same cooldown.
                                await _conversation_store.touch_self_update(person_id, time.monotonic())
                            else:
                                # P0.S1 D1 — pass the verdict through to the catch-all.
                                # _anti_spoof_ok is True at this point (the else branch
                                # of `if not _anti_spoof_ok`); pass it as the verdict.
                                added = db.add_embedding(
                                    person_id, embedding, "recognition_update", conf,
                                    anti_spoof_verdict=_anti_spoof_ok,
                                )
                                if added:
                                    await _conversation_store.touch_self_update(person_id, time.monotonic())
                                    print(f"[Pipeline] {person_name} gallery updated — new angle stored ({db.embedding_count(person_id)}/{MAX_EMBEDDINGS} face embeddings)")

                    # ── Greet known person or returning stranger ──────────────
                    if _wiring._pipeline_state_store.peek_pipeline_state() == PipelineState.WATCHING:
                        last_greeted = _conversation_store.peek_last_greeted(person_id)
                        # _session_store.peek_snapshot(person_id) being non-None means their session is still
                        # live (e.g., returned to WATCHING after "no speech"). In that
                        # case never re-greet even if the cooldown has technically expired
                        # during a long conversation — the session never actually ended.
                        if (time.monotonic() - last_greeted >= GREET_COOLDOWN
                                and _wiring._session_store.peek_snapshot(person_id) is None):
                            # Consume the ambient wake signal unconditionally — whether
                            # anti-spoof blocks or passes, background loop must not re-fire.
                            await _per_person_agent_store.discard_ambient_wake(person_id)
                            # Anti-spoofing: check liveness before greeting to block
                            # photo/screen attacks. Only checked on the greeting frame.
                            if not verify_live(frame, det.bbox, _wiring._anti_spoof_checker):
                                print(f"[Pipeline] Anti-spoof: BLOCKED {person_name} — liveness check failed")
                                continue
                            if _wiring._anti_spoof_checker is not None and getattr(_wiring._anti_spoof_checker, "available", False):
                                print(f"[Pipeline] Anti-spoof: PASSED {person_name}")
                            else:
                                print(f"[Pipeline] Anti-spoof: DISABLED {person_name} (no liveness check performed)")
                            await _conversation_store.touch_greeted(person_id, time.monotonic())
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
                                await _per_person_agent_store.add_session_started(person_id)
                                # Per-person EmotionAgent: kept alive across sessions; 90-second TTL
                                # in get_dominant_emotion() handles stale entries automatically.
                                await _conversation_store.ensure_history_loaded(person_id, lambda: db.load_conversation_history(person_id))
                                # person_type was seeded by _open_session; just add the system-name gate.
                                if _wiring._session_store.peek_snapshot(person_id) is not None:
                                    try:
                                        _loop = asyncio.get_running_loop()
                                        _loop.create_task(_wiring._session_store.set_waiting_for_name(person_id, STRANGER_REQUIRE_SYSTEM_NAME))
                                    except RuntimeError:
                                        pass  # OPTIONAL
                                if STRANGER_REQUIRE_SYSTEM_NAME:
                                    print(f"[Pipeline] Stranger {person_id} detected — waiting for system name '{_wiring._pipeline_state_store.peek_active_system_name()}'")
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
                                if _wiring._session_store.peek_snapshot(person_id) is not None:
                                    try:
                                        _loop = asyncio.get_running_loop()
                                        _loop.create_task(_wiring._session_store.mark_voice_face_confirmed(person_id))
                                        _loop.create_task(_wiring._session_store.set_voice_only_origin(person_id, False))
                                    except RuntimeError:
                                        pass  # OPTIONAL
                                try:
                                    _loop = asyncio.get_running_loop()
                                    _loop.create_task(_wiring._session_store.update_face_seen(
                                        person_id, conf=conf, ts=time.monotonic(), anti_spoof_live=True))  # #5 Slice B: last_face_seen (FACE_LOSS_GRACE)
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
                                await _per_person_agent_store.add_session_started(person_id)
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
                                await _conversation_store.set_history(person_id, history_from_db)

                                # ── Briefing for best friend after long absence ─
                                _briefing_task = None
                                if (
                                    person_type == "best_friend"
                                    and _wiring._brain_orchestrator
                                    and last_seen_ts
                                    and (time.monotonic() - last_seen_ts) >= BRIEFING_MIN_ABSENCE
                                ):
                                    _briefing_task = asyncio.create_task(
                                        _wiring._brain_orchestrator.get_briefing(person_id, last_seen_ts)
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
            grace_expired = time.monotonic() - _wiring._pipeline_state_store.peek_last_face_seen() > FACE_LOSS_GRACE
            if _wiring._pipeline_state_store.peek_pipeline_state() == PipelineState.WATCHING and detections and not _wiring._session_store.peek_all_snapshots() and grace_expired:
                unknown_key = "unknown"
                last_sighted = _conversation_store.peek_last_greeted(unknown_key)
                if time.monotonic() - last_sighted >= GREET_COOLDOWN:
                    await _conversation_store.touch_greeted(unknown_key, time.monotonic())
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
                _now_face = time.monotonic()
                # Keep ambient timer current when no sessions are active.
                if not _wiring._session_store.peek_all_snapshots():
                    try:
                        _loop = asyncio.get_running_loop()
                        _loop.create_task(_wiring._pipeline_state_store.set_last_face_seen(_now_face))
                    except RuntimeError:
                        pass  # OPTIONAL
                else:
                    # Only update last_face_seen for faces that belong to active sessions.
                    # A stranger walking in during an active session should NOT reset the timer.
                    for _d in detections:
                        if _d.person_id and _wiring._session_store.peek_snapshot(_d.person_id) is not None:
                            try:
                                _loop = asyncio.get_running_loop()
                                _loop.create_task(_wiring._pipeline_state_store.set_last_face_seen(_now_face))
                                _loop.create_task(_wiring._session_store.set_last_face_seen(_d.person_id, _now_face))
                            except RuntimeError:
                                pass  # OPTIONAL

            # ── Session expiry — check each active session independently ──────
            if _wiring._pipeline_state_store.peek_pipeline_state() == PipelineState.WATCHING and _wiring._session_store.peek_all_snapshots():
                _expire_stale_sessions()

            # state.write removed here, handled by _set_state and final WATCHING state

            # ── Vision heartbeat — always-on confirmation every 30s ────────────
            # P1.A1 SP-6.3: _vision_last_heartbeat_state is WIRE-d; access via _wiring._X.
            _now = time.time()
            if _now - _wiring._vision_last_heartbeat >= 30.0:
                _wiring._vision_last_heartbeat = _now
                if visible_people:
                    _hb_who = ", ".join(set(visible_people))
                    _hb_key = f"WATCHING|{_hb_who}"
                elif detections:
                    _hb_who = "unrecognized face detected"
                    _hb_key = "WATCHING|unrecognized"
                else:
                    _hb_who = "no face"
                    _hb_key = "WATCHING|none"
                if _hb_key != _wiring._vision_last_heartbeat_state:
                    _wiring._vision_last_heartbeat_state = _hb_key
                    print(f"[Vision] Watching — {_hb_who}")

            # ── Listen for speech ─────────────────────────────────────────────
            # Lip tracker: keep bbox current and calibrate baseline while person is at rest.
            if _wiring._session_store.peek_all_snapshots() and detections:
                for _det in detections:
                    if _wiring._session_store.peek_snapshot(_det.person_id) is not None:
                        _last_active_bbox = _det.bbox
                        if _wiring._pipeline_state_store.peek_pipeline_state() not in (PipelineState.LISTENING, PipelineState.THINKING):
                            lip_tracker.update_baseline(frame, _det.bbox)
                        break

            # ── Listen for speech even without a face in frame ────────────────
            _ambient_text  = ""
            _ambient_audio = None
            if not _wiring._session_store.peek_all_snapshots() and _wiring._pipeline_state_store.peek_pipeline_state() == PipelineState.WATCHING:
                # Persistent background loop (_vis_bg_task) keeps vision alive — no
                # per-listen task needed here anymore.
                _ambient_text, _, _ambient_audio = await listen_and_transcribe()
                if _ambient_text:
                    print(f"[Pipeline] Voice-first: heard speech — identifying speaker...")
                    # Voice ID
                    v_pid, v_score, _ = await voice_mod.identify(
                        _ambient_audio, _voice_gallery_store.peek_all_gallery(), VOICE_RECOGNITION_THRESHOLD
                    )
                    _voice_known_opened = False  # Canary #4: did voice ID open a known session?
                    if v_pid:
                        row = db.get_person(v_pid)
                        if row:
                            _v_pt = db.get_person_type(v_pid) or "known"
                            _open_session(v_pid, row["name"], "voice", person_type=_v_pt, voice_confidence=v_score)
                            _voice_known_opened = True
                            print(f"[Voice] Identified {row['name']} by voice (score={v_score:.3f})")
                            await _conversation_store.ensure_history_loaded(v_pid, lambda: db.load_conversation_history(v_pid))
                    # #15 invariant: session-opening authority comes from (a) a known-voice
                    # match, (b) a known-face match at WATCHING entry, or (c) a stranger
                    # who said the system name. The gate runs first; camera is a
                    # disambiguator only after authority is established.
                    if not _wiring._session_store.peek_all_snapshots():
                        if not db.list_people():
                            await first_boot_flow(camera, detector, embedder, db)
                            _set_state(PipelineState.WATCHING)
                            _ambient_text = ""  # first_boot handled it
                        elif _name_heard_in(_ambient_text, _wiring._pipeline_state_store.peek_active_system_name())[0]:
                            # Gate PASSED — use camera to attach face identity if available.
                            _best_pid = None  # Canary #4: camera-fallback known-face result (None if no face / no fresh frame)
                            cam_f = _vision_frame_store.peek_frame_if_fresh(0.5, time.monotonic())
                            if cam_f is not None:
                                _best_pid, _best_pname, _best_conf = None, None, 0.0
                                for _d in detector.detect(cam_f):
                                    x1, y1, x2, y2 = _d.bbox
                                    crop = cam_f[y1:y2, x1:x2]
                                    if crop.size == 0:
                                        continue
                                    # P0.R6 D3 (Site 4, was line 7112): converted
                                    # from SYNC direct call to async via worker
                                    # pool. Non-blocking improvement per PI #1
                                    # absorption (Plan v1 §1.1 Option α scope).
                                    _emb_bytes = await hw.run_heavy(
                                        "adaface_embed",
                                        hw.adaface_embed_worker,
                                        crop.tobytes(),
                                        crop.shape,
                                    )
                                    _emb = (
                                        np.frombuffer(_emb_bytes, dtype=np.float32)
                                        if _emb_bytes is not None
                                        else None
                                    )
                                    # P0.R1 D1: embed() now returns None on cascading CUDA+CPU failure.
                                    if _emb is None:
                                        print("[Pipeline] camera fallback: face embedding failed, skipping")
                                        continue
                                    _pid, _pname, _conf = db.recognize(_emb, RECOGNITION_THRESHOLD)
                                    if _pid and _conf > _best_conf:
                                        if not verify_live(cam_f, _d.bbox, _wiring._anti_spoof_checker):
                                            print(f"[Pipeline] Anti-spoof: BLOCKED camera fallback for {_pname}")
                                            continue
                                        _best_pid, _best_pname, _best_conf = _pid, _pname, _conf
                                    elif not _pid:
                                        _maybe_record_silent_obs(_emb, _d.bbox, cam_f.shape[1], cam_f.shape[0], db)
                                if _best_pid:
                                    _best_pt = db.get_person_type(_best_pid) or "known"
                                    _open_session(_best_pid, _best_pname, "voice", person_type=_best_pt)
                                    await _conversation_store.ensure_history_loaded(_best_pid, lambda: db.load_conversation_history(_best_pid))
                            if _voice_first_should_engage_stranger(
                                _voice_known_opened, _best_pid is not None,
                                _ambient_text, _wiring._pipeline_state_store.peek_active_system_name(),
                            ):
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
                                await _conversation_store.init_empty(_sid)
                                if _wiring._session_store.peek_snapshot(_sid) is not None:
                                    try:
                                        _loop = asyncio.get_running_loop()
                                        _loop.create_task(_wiring._session_store.set_waiting_for_name(_sid, False))
                                        _loop.create_task(_wiring._session_store.set_voice_only_origin(_sid, True))
                                    except RuntimeError:
                                        pass  # OPTIONAL
                                print(f"[Pipeline] Stranger engaged (voice-only, system addressed) — {_sid}")
                        else:
                            # Gate FAILED — stay silent
                            _ambient_text = ""

            _primary_pid_conv = _primary_person_id()
            if _primary_pid_conv and _wiring._pipeline_state_store.peek_pipeline_state() == PipelineState.WATCHING:
                # Stay in a tight conversation loop — no camera rescan between turns.
                # Eliminates the SPEAKING → WATCHING → camera+detect+embed → LISTENING
                # round-trip (~150ms) that made each turn feel laggy.

                # Voice-ID / camera-fallback paths skip the face-recognition greeting block.
                # Only run once per session — greeting path already called update_last_seen.
                if not _per_person_agent_store.is_session_started(_primary_pid_conv):
                    db.update_last_seen(_primary_pid_conv)
                    await _per_person_agent_store.add_session_started(_primary_pid_conv)
                    await _conversation_store.touch_greeted(_primary_pid_conv, time.monotonic())  # prevent face-recog re-greet
                    _pp_snap = _wiring._session_store.peek_snapshot(_primary_pid_conv)
                    _ppname = _pp_snap.person_name if _pp_snap is not None else _primary_pid_conv
                    print(f"[Pipeline] Conversation started for {_ppname} (voice/camera-fallback path)")

                # Seed the voice session timeout for voice-started sessions
                if _wiring._session_store.peek_snapshot(_primary_pid_conv) is not None:
                    _conv_start_ts = time.monotonic()  # #5 Slice B (§0.1.5): last_spoke_at (VOICE_SESSION_TIMEOUT); only consumer is set_last_spoke_at
                    try:
                        _loop = asyncio.get_running_loop()
                        _loop.create_task(_wiring._session_store.set_last_spoke_at(_primary_pid_conv, _conv_start_ts))
                    except RuntimeError:
                        pass  # OPTIONAL

                _ppname_conv = _primary_person_name() or _primary_pid_conv
                _set_state(PipelineState.LISTENING, _ppname_conv)
                print(f"[Pipeline] Listening for {_ppname_conv}...")
                # Reset KAIROS silence clock only when a brand-new session just opened.
                # On re-entry after "No speech detected", preserve accumulated silence so
                # Kairos can fire if the person stays silent long enough.
                _kcr_snap = _wiring._session_store.peek_snapshot(_primary_pid_conv)
                if _kcr_snap is not None and _kcr_snap.kairos_clock_reset:
                    try:
                        _loop = asyncio.get_running_loop()
                        _loop.create_task(_wiring._pipeline_state_store.set_last_user_speech_at(time.monotonic()))
                        _loop.create_task(_wiring._session_store.consume_kairos_reset(_primary_pid_conv))
                    except RuntimeError:
                        pass  # OPTIONAL

                # Persistent _vis_bg_task (started at run() startup) keeps camera
                # running throughout — no separate per-conversation task needed.
                while not _wiring._shutdown_event.is_set():
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
                            (_wiring._session_store.peek_snapshot(_kairos_pid).person_name if _wiring._session_store.peek_snapshot(_kairos_pid) is not None else _kairos_pid)
                            if _kairos_pid and _wiring._session_store.peek_snapshot(_kairos_pid) is not None
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
                    if await _wiring._pipeline_state_store.consume_cloud_recovered():
                        print("[Cloud] Recovery TTS suppressed (Bug Y) — continuing silently")

                    # If ambient probe already captured speech, use it directly.
                    import core.audio as _audio_mod
                    if _ambient_text:
                        text, audio_buf = _ambient_text, _ambient_audio
                        _ambient_text  = ""
                        _ambient_audio = None
                        await _wiring._pipeline_state_store.set_last_user_speech_at(time.monotonic())
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
                    if _fl_pid and _wiring._session_store.peek_snapshot(_fl_pid) is not None:
                        _fl_snap = _wiring._session_store.peek_snapshot(_fl_pid)
                        _fl_face_gone = (
                            _fl_snap is not None
                            and _fl_snap.session_type == "face"
                            and time.monotonic() - _fl_snap.last_face_seen > FACE_LOSS_GRACE
                        )

                    if not text:
                        if _fl_face_gone or not _primary_person_id():
                            # Face gone or session expired — return to WATCHING scan.
                            print("[Pipeline] No speech detected, back to watching.")
                            break
                        # Face still visible but person silent — loop back so Kairos
                        # can fire when silence threshold is reached.
                        continue

                    await _wiring._pipeline_state_store.set_last_user_speech_at(time.monotonic())

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
                    _v_pid, _v_score, _v_is_no_signal = await voice_mod.identify(
                        audio_buf, _voice_gallery_store.peek_all_gallery(), VOICE_RECOGNITION_THRESHOLD
                    )

                    # Voice-identified speakers are added to _presence_store so
                    # session tracking knows they're present even without a face.
                    # source="voice" distinguishes them from camera-detected entries.
                    if _v_pid:
                        _v_row_pif = db.get_person(_v_pid)
                        _v_name_pif = _v_row_pif["name"] if _v_row_pif else _v_pid
                        try:
                            asyncio.get_running_loop().create_task(
                                _presence_store.upsert_voice_recognition(
                                    # #5 Slice A: monotonic — writes presence last_seen
                                    # (in-memory staleness, consumed by _face_in_frame :599 +
                                    # the routing reads, all elapsed-math). No persist/display.
                                    _v_pid, _v_name_pif, _v_score, time.monotonic()
                                )
                            )
                        except RuntimeError:
                            pass  # OPTIONAL: no running loop in test context

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
                        _diar = await voice_mod.diarize(
                            audio_buf, _voice_gallery_store.peek_all_gallery(), VOICE_RECOGNITION_THRESHOLD
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
                            # P0.S7.D-E γ: also collect (pid, name, text) into
                            # _spans_with_pids inline so the helper at the call
                            # site (~line 7830) can append per-speaker history
                            # rows for the SECONDARY speakers of this multi-
                            # speaker turn. Primary's history is appended by
                            # conversation_turn; secondaries would otherwise
                            # miss their own overlap utterance entirely.
                            _named_pairs: list[tuple[str | None, str]] = []
                            _spans_with_pids: list[tuple[str | None, str, str]] = []
                            for _span in _spans:
                                _a = audio_buf[_span["start_sample"]:_span["end_sample"]]
                                _t, _ = await transcribe(_a)
                                _t = _t.strip()
                                if not _t:
                                    continue
                                _pid_span = _span.get("speaker_id")
                                _span_name: "str | None" = None
                                if _pid_span is not None:
                                    _r = db.get_person(_pid_span)
                                    _span_name = _r["name"] if _r else _pid_span
                                _named_pairs.append((_span_name, _t))
                                # γ collection — helper at call site filters
                                # None pid + empty content + primary dedup.
                                _spans_with_pids.append(
                                    (_pid_span, _span_name or (_pid_span or ""), _t)
                                )

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
                    _matches_active = (_wiring._session_store.peek_snapshot(_v_pid) is not None) if _v_pid else False
                    _voice_state = {
                        "matched_id":              _v_pid,
                        "matched_name":            _v_name,
                        "voice_confidence":        _v_score,
                        "matches_active":          _matches_active,
                        "gallery_size":            _voice_gallery_store.peek_len(),
                        "multi_speaker":           _multi_speaker_detected,
                        "multi_speaker_speakers":  _multi_speaker_labels,
                    }
                    # Update the matching session's last_spoke_at — ONLY when
                    # voice confirms the session holder. When voice ID fails (unknown
                    # speaker), do NOT extend the session — a different person speaking
                    # should not keep the original person's session alive.
                    if _v_pid and _wiring._session_store.peek_snapshot(_v_pid) is not None:
                        _vs_ts = time.monotonic()  # #5 Slice B: last_spoke_at (VOICE_SESSION_TIMEOUT elapsed-math)
                        try:
                            _loop = asyncio.get_running_loop()
                            _loop.create_task(_wiring._session_store.record_voice_spoke(
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
                        _loop.create_task(_wiring._session_store.update_voice_heard(
                            _v_pid, conf=_v_score, ts=time.monotonic()))  # #5 Slice B: last_spoke_at (VOICE_SESSION_TIMEOUT)
                        # Bug D1 (2026-04-22 live run): feed the disputed-session
                        # auto-clear detector. Only disputed sessions need this
                        # deque; lazy-initialize on first append so non-disputed
                        # sessions don't pay the allocation cost.
                        if _is_disputed(_v_pid):
                            try:
                                _loop = asyncio.get_running_loop()
                                _loop.create_task(_wiring._session_store.append_voice_conf(_v_pid, conf=_v_score))
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
                    _pt_snap = _wiring._session_store.peek_snapshot(_cur_pid) if _cur_pid else None
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
                    _rs_pif_view = {
                        s.person_id: {
                            "last_seen": s.last_seen,
                            "last_recognized_at": s.last_recognized_at,  # P0.S7.5.2 D1 — mirror PresenceSnapshot schema; reconciler offscreen-floor reads this
                            "name": s.name,
                            "conf": s.conf,
                            "source": s.source,
                        }
                        for s in _presence_store.peek_all_snapshots()
                    }
                    _rs_ut_view = {
                        s.track_id: s.last_seen
                        for s in _track_store.peek_all_snapshots()
                        if s.last_seen > 0 and s.identity_pid is None
                    }
                    # P0.10 Phase 2: legacy `_resolve_actual_speaker` call site
                    # deleted (was at this site through Phase 4 cutover, retained
                    # as shadow-only since Phase 4, now fully removed). The
                    # reconciler is the sole routing source; `_routing_action`
                    # + `_resolved_pid` are assigned by the collapsed override
                    # conditional below (with B2 fail-safe per Block B).

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
                            audio_buf, _voice_gallery_store.peek_all_gallery(),
                            utterance_duration=_utterance_secs,
                        )
                        _vc_pid_diff = _vc_claim.pid != _v_pid
                        _vc_conf_diff = abs(float(_vc_claim.confidence) - float(_v_score)) > 0.05
                        # D6: comparison still runs; only the divergence print is gated.
                        if (_vc_pid_diff or _vc_conf_diff) and SHADOW_CHANNEL_LOGGING_ENABLED:
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
                    # turn. The reconciler is the primary router (Phase 4
                    # cutover, P0.10); the cutover flag was retired in SB.1 D2,
                    # rollback is a git revert.
                    _rc_decision = None
                    try:
                        from core.reconciler import (
                            _build_routing_inputs as _rc_build,
                            reconcile as _rc_reconcile,
                        )
                        # #5 Slice A keystone: monotonic. Reconciler (clock-disciplined,
                        # reconciler.py:12 "MUST NOT call time.time()") consumes this as `now`
                        # vs _rs_pif_view's last_recognized_at (sourced from PresenceSnapshot
                        # attrs, now monotonic-written). Single-clock by construction. Guarded
                        # by tests/test_reconciler_clock_provenance.py (the dict-mediated
                        # blind-spot closer the paired invariant can't see).
                        _rc_now = time.monotonic()
                        _rc_claim, _rc_presence, _rc_session = _rc_build(
                            v_pid=_v_pid,
                            v_score=_v_score,
                            n_diarize_segments=_diar_seg_count,
                            utterance_duration=_utterance_secs,
                            persons_in_frame=_rs_pif_view,
                            unrecognized_tracks=_rs_ut_view,
                            cur_pid=_cur_pid,
                            cur_person_type=(_cur_person_type or ""),
                            n_active_sessions=len(_wiring._session_store.peek_all_snapshots()),
                            voice_gallery_sizes=_voice_gallery_store.peek_all_sizes(),
                            now=_rc_now,
                            v_score_is_no_signal=_v_is_no_signal,
                        )
                        _rc_decision = _rc_reconcile(
                            _rc_claim, _rc_presence, _rc_session,
                        )
                        # P0.10 Phase 2 — Reconciler-Shadow as Bug-W-band watchdog.
                        # Pre-Phase-2 this block fired on "legacy != new" divergence.
                        # Legacy is gone now (Step 7); the trigger transforms to
                        # "did the rule that fired match the expected rule for
                        # the utterance band?" Bug-W class signal: gap-band turns
                        # MUST fire `_p0_short_utterance_gap_hold_current`;
                        # short_hard-band turns MUST fire one of the two
                        # short-utterance mismatch rules OR the pure-noise rule
                        # (boundary cases). Anything else is a regression worth
                        # an entry in the validation log. The whole shadow block
                        # is deleted in the P0.10 follow-up cleanup PR.
                        _utt = _utterance_secs or 0.0
                        if _utt < VOICE_ROUTING_NOISE_FLOOR_SECS:
                            _band = "noise"
                        elif _utt < VOICE_ROUTING_MIN_AUDIO_FOR_SCORE:
                            _band = "gap"        # 0.3 <= utt < 0.5 — Bug-W's signature
                        elif _utt < VOICE_ROUTING_MIN_UTTERANCE_SECS:
                            _band = "short_hard" # 0.5 <= utt < 1.0 — D7 watch
                        else:
                            _band = "normal"
                        _watch_bands = ("gap", "short_hard")
                        _rule_fired = _rc_decision.rule_fired
                        # P0.10.1 F2: band→expected-rule mapping co-located
                        # with the cascade in core/reconciler.py
                        # (EXPECTED_RULES_BY_BAND module-level constant).
                        # Pipeline.py imports it via the same `from
                        # core.reconciler import ...` line as `_rc_build`
                        # / `_rc_reconcile`.
                        from core.reconciler import EXPECTED_RULES_BY_BAND
                        _expected = EXPECTED_RULES_BY_BAND.get(_band, ())
                        # D6: reconcile() comparison already ran above; this gates only the
                        # divergence-logging diagnostic (computation + print).
                        if (_band in _watch_bands and _rule_fired not in _expected
                                and SHADOW_CHANNEL_LOGGING_ENABLED):
                            try:
                                _face_seens = [
                                    s.last_seen
                                    for s in _presence_store.peek_all_snapshots()
                                    if s.source == "face" and s.last_seen > 0
                                ]
                                _last_face_age = (
                                    _rc_now - max(_face_seens)
                                    if _face_seens else None
                                )
                            except Exception:
                                # OBSERVABILITY: logging path must never break a turn
                                _last_face_age = None
                            # P0.10.1 F1: per-session correlation axis
                            # distinct from ts. `user_turns` increments on
                            # each user message within the current session
                            # (Session 97 STRANGER_IDENTITY_BLOCK_MIN_TURNS
                            # plumbing). ts alone can't supply ordinal-
                            # within-session — correlation across multiple
                            # sessions uses ts; correlation within a single
                            # session uses turn_in_session.
                            _ts_snap = _wiring._session_store.peek_snapshot(_cur_pid) if _cur_pid else None
                            _turn_in_session = _ts_snap.user_turns if _ts_snap is not None else None
                            print(
                                f"[Reconciler-Shadow] {_now_log_ts()} divergence | "
                                f"turn_in_session={_turn_in_session if _turn_in_session is not None else 'n/a'} | "
                                f"expected_rules={_expected!r} | "
                                f"actual_rule={_rule_fired!r} | "
                                f"action={_rc_decision.action!r} | pid={_rc_decision.pid!r} | "
                                f"utt_dur={_utt:.2f}s | utt_band={_band} | v_score={_v_score:.3f} | "
                                f"pyannote_segments={_diar_seg_count} | cur_pid={_cur_pid!r} | "
                                f"cur_person_type={(_cur_person_type or '')!r} | "
                                f"persons_in_frame_count={len(_rs_pif_view)} | "
                                f"last_face_age_s={(f'{_last_face_age:.2f}' if _last_face_age is not None else 'n/a')} | "
                                f"reason={_rc_decision.reasoning!r}"
                            )
                    except Exception as _rc_e:
                        print(
                            f"[Reconciler-Shadow] error: "
                            f"{type(_rc_e).__name__}: {_rc_e!r}"
                        )

                    # P0.10 Block B (B2): reconciler is the sole routing
                    # source. The reconciler cutover flag was retired in SB.1
                    # D2 (it no longer gated dispatch); the remaining shadow
                    # block + this collapsed conditional go together in the
                    # P0.10 follow-up cleanup PR once Block E's gate
                    # criteria are met. Fail-safe (B2): on `_rc_decision is
                    # None` (cascade returned None — cannot happen with
                    # current 23-rule cascade per `_last_resort_ambiguous`,
                    # but a future refactor that re-introduces fall-through
                    # OR an exception in the try block above sets it back
                    # to None) hold the current session AND emit a loud
                    # WARN log so the coverage gap is INSTANTLY visible.
                    # This branch is a Bug-W-class regression signal —
                    # should NEVER fire in a fully-covered rule set.
                    if _rc_decision is not None:
                        _resolved_pid = _rc_decision.pid
                        _routing_action = _rc_decision.action
                    else:
                        _resolved_pid = _cur_pid
                        _routing_action = "current"
                        print(
                            f"[Reconciler] WARN {_now_log_ts()}: no rule fired — "
                            f"falling back to hold-current; claim=(v_pid={_v_pid!r}, "
                            f"v_score={_v_score:.3f}, utt={(_utterance_secs or 0.0):.2f}s, "
                            f"n_diarize={_diar_seg_count}) session=(cur_pid={_cur_pid!r}, "
                            f"cur_type={(_cur_person_type or '')!r})"
                        )

                    if _routing_action == "switch_enrolled":
                        # Different enrolled person is speaking — open/switch their session directly.
                        # No LLM confirmation needed: voice gallery is ground truth for enrolled persons.
                        if _wiring._session_store.peek_snapshot(_resolved_pid) is None:
                            # Fetch DB-sourced person_type BEFORE open so it's seeded at
                            # dict creation (closes the stranger-fallback race window).
                            _switched_pt = (db.get_person_type(_resolved_pid) if db else "known") or "known"
                            _open_session(_resolved_pid, _v_name, "voice",
                                          person_type=_switched_pt, voice_confidence=_v_score)
                            await _conversation_store.ensure_history_loaded(_resolved_pid, lambda: db.load_conversation_history(_resolved_pid))
                            # Invalidate stale query embedding cache so get_context() fetches
                            # fresh memory on this first turn rather than using a stale vector.
                            try:
                                _loop = asyncio.get_running_loop()
                                _loop.create_task(_query_embedding_store.discard(_resolved_pid))
                            except RuntimeError:
                                pass  # OPTIONAL
                        _sw_ts = time.monotonic()  # #5 Slice B: last_spoke_at (VOICE_SESSION_TIMEOUT elapsed-math)
                        try:
                            _loop = asyncio.get_running_loop()
                            _loop.create_task(_wiring._session_store.record_voice_spoke(
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
                        _loop.create_task(_wiring._session_store.update_voice_heard(
                            _resolved_pid, conf=_v_score, ts=time.monotonic()))  # #5 Slice B: last_spoke_at (VOICE_SESSION_TIMEOUT)
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
                            "gallery_size":            _voice_gallery_store.peek_len(),
                            "multi_speaker":           _multi_speaker_detected,
                            "multi_speaker_speakers":  _multi_speaker_labels,
                        }
                        print(f"[Voice] Speaker switch → {_v_name} (score={_v_score:.3f})")

                    elif _routing_action == "new_stranger":
                        # #20: 1:1 stranger-track-to-session binding.
                        # Every SORT track gets a pre-allocated pid; multi-track →
                        # pick the most-recently-seen track's session (not "most-recent voice session").
                        # #5 Slice A: monotonic — reads track last_seen staleness (:8426,
                        # elapsed) + writes last_spoke_at (:8447). The last_spoke_at write
                        # makes that field mixed-clock until Slice B flips its other writers
                        # (_now_ext/_now_ts_u2u/_conv_start_ts) → §3.0 TRANSIENT allowlist entry.
                        _now_route   = time.monotonic()
                        _active_unrec = {
                            s.track_id: s.last_seen
                            for s in _track_store.peek_all_snapshots()
                            if s.last_seen > 0 and s.identity_pid is None
                            and _now_route - s.last_seen < VOICE_ROUTING_FACE_STALE_SECS
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
                            _track_store.peek_stranger_pid(_speaker_track)
                            if _speaker_track is not None else None
                        )
                        if _target_sid and _wiring._session_store.peek_snapshot(_target_sid) is not None:
                            # Same physical face returned — resume their session
                            _cur_pid  = _target_sid
                            _ts_snap = _wiring._session_store.peek_snapshot(_target_sid)
                            _cur_name = _ts_snap.person_name if _ts_snap is not None else _target_sid
                            try:
                                _loop = asyncio.get_running_loop()
                                _loop.create_task(_wiring._session_store.set_last_spoke_at(_cur_pid, _now_route))
                            except RuntimeError:
                                pass  # OPTIONAL
                            print(f"[Voice] Track {_speaker_track} → resumed session {_cur_pid}")
                        else:
                            # Open session — use pre-allocated pid if available
                            _sid = _target_sid or f"stranger_{__import__('uuid').uuid4().hex[:8]}"
                            db.add_stranger("visitor", person_id=_sid)  # INSERT OR IGNORE

                            # P0.S7.5.2 D2 — voice-routing new_stranger MUST mirror
                            # the ambient-gate engagement semantics (pipeline.py:6846+)
                            # when the user said the system name in this turn's STT.
                            # Without this, the session opens stuck at
                            # waiting_for_name=True with bootstrap_credits=0; every
                            # subsequent _accumulate_voice call refuses with
                            # bootstrap=0 (canary 3 2026-05-20 Lexi failure: said
                            # "Hi Kara..." turn 1, session opened gate-blocked,
                            # never accumulated voice). NFKC-lowercased substring
                            # match (NOT word-boundary) — matches existing
                            # engagement-gate detection pattern; if word-boundary
                            # tightening proves load-bearing later, fix BOTH paths
                            # symmetrically in a follow-up spec.
                            _system_name = _wiring._pipeline_state_store.peek_active_system_name() or ""
                            _engagement_passed = bool(
                                _system_name
                                and text
                                and _nfkc_lower(_system_name) in _nfkc_lower(text)
                            )

                            _open_session(_sid, "visitor", "voice",
                                          person_type="stranger",
                                          engagement_gate_passed=_engagement_passed)
                            await _conversation_store.init_empty(_sid)
                            try:
                                _loop = asyncio.get_running_loop()
                                if _engagement_passed:
                                    _loop.create_task(_wiring._session_store.set_waiting_for_name(_sid, False))
                                    _loop.create_task(_wiring._session_store.set_voice_only_origin(_sid, True))
                                else:
                                    _loop.create_task(_wiring._session_store.set_waiting_for_name(_sid, STRANGER_REQUIRE_SYSTEM_NAME))
                            except RuntimeError:
                                pass  # OPTIONAL: no running loop in test/early-boot context
                            _cur_pid  = _sid
                            _cur_name = "visitor"
                            if _speaker_track is not None:
                                try:
                                    asyncio.get_running_loop().create_task(
                                        _track_store.mint_stranger(_speaker_track, _sid)
                                    )
                                except RuntimeError:
                                    pass  # OPTIONAL: no running loop in test context
                            if _engagement_passed:
                                print(f"[Pipeline] Stranger engaged (voice-only, system addressed) — {_sid}")
                            print(f"[Voice] Unrecognized speaker → new session {_cur_pid} (track={_speaker_track})")

                    elif _routing_action == "ambiguous":
                        # #21: record attribution; 3 consecutive ambiguous → close stale session
                        _drift_pid = _cur_pid
                        if _drift_pid and _wiring._session_store.peek_snapshot(_drift_pid) is not None:
                            try:
                                _loop = asyncio.get_running_loop()
                                _loop.create_task(_wiring._session_store.record_attribution(_drift_pid, "ambiguous"))
                            except RuntimeError:
                                pass  # OPTIONAL
                            _drift_snap = _wiring._session_store.peek_snapshot(_drift_pid)
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
                    _ext_snap = _wiring._session_store.peek_snapshot(_cur_pid) if _cur_pid else None
                    # #5 Slice B (DRIFT-1): flip to monotonic. The :8608 staleness read compares
                    # _now_ext against the MONOTONIC presence last_recognized_at (Slice A); while
                    # _now_ext was wall, wall−mono ≈ +1.78e9 ≥ VOICE_ROUTING_FACE_STALE_SECS so
                    # _holder_vis_ext was ALWAYS False → #22 voice-session extension was dead code.
                    # mono−mono revives it AND makes the :8614 last_spoke_at write monotonic.
                    _now_ext = time.monotonic()
                    if (_cur_pid and _wiring._session_store.peek_snapshot(_cur_pid) is not None
                            and (_ext_snap.session_type if _ext_snap is not None else None) == "voice"):
                        _holder_vis_ext = (
                            _cur_pid in _presence_store
                            and _now_ext - _presence_store.peek_last_recognized_at(_cur_pid, 0.0)
                            < VOICE_ROUTING_FACE_STALE_SECS
                        )
                        if _holder_vis_ext:
                            try:
                                _loop = asyncio.get_running_loop()
                                _loop.create_task(_wiring._session_store.set_last_spoke_at(_cur_pid, _now_ext))
                            except RuntimeError:
                                pass  # OPTIONAL

                    # #21: record non-ambiguous attribution (resets any drift streak)
                    if _cur_pid and _wiring._session_store.peek_snapshot(_cur_pid) is not None:
                        try:
                            _loop = asyncio.get_running_loop()
                            _loop.create_task(_wiring._session_store.record_attribution(_cur_pid, _routing_action))
                        except RuntimeError:
                            pass  # OPTIONAL

                    # Voice accumulation for current person (when verified or early phase)
                    if _cur_pid and _cur_pid != "unknown" and len(audio_buf) > 0:
                        # #23: single policy — face_verified when holder is visibly present
                        # OR when the progressive-enroll gate already confirmed their face
                        # (voice_face_confirmed flag set on gate-pass turn).
                        _face_vis_acc = (
                            (_cur_pid in _presence_store
                             and time.monotonic() - _presence_store.peek_last_recognized_at(_cur_pid, 0.0)
                             < VOICE_ROUTING_FACE_STALE_SECS)
                            or (_ext_snap.voice_face_confirmed if _ext_snap is not None else False)
                        )
                        _t = asyncio.create_task(
                            _accumulate_voice(_cur_pid, audio_buf, db, face_verified=_face_vis_acc)
                        )
                        # Spec 2 Phase A (A3): log task exceptions instead of swallowing them.
                        _voice_tasks.add(_t); _t.add_done_callback(_voice_accum_done_callback)

                    # Build live sensor state — vision + voice together give brain
                    # the complete picture: what it SEES and who it HEARS, every turn.
                    _cur_snap      = _wiring._session_store.peek_snapshot(_cur_pid) if _cur_pid else None
                    _cur_rec_conf  = _presence_store.peek_conf(_cur_pid, 0.0) if _cur_pid else 0.0
                    # Session 97 Fix 1: bump the user-turn counter BEFORE
                    # building vision_state so `session_user_turns` reflects
                    # "this turn's number" (1-indexed). Drives the
                    # <<<STRANGER IDENTITY>>> block's threshold gate.
                    if _cur_snap is not None:
                        _prev_turns = _cur_snap.user_turns
                        try:
                            _loop = asyncio.get_running_loop()
                            _loop.create_task(_wiring._session_store.increment_user_turns(_cur_pid))
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
                                _loop.create_task(_wiring._session_store.set_cached_prefix(_cur_pid, None))
                            except RuntimeError:
                                pass  # OPTIONAL
                    _vision_state = {
                        "face_in_frame":          time.monotonic() - _wiring._pipeline_state_store.peek_last_face_seen() < 2.0,
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
                        "active_session_count":   len(_wiring._session_store.peek_all_snapshots()),
                        # Phase 3B.1: unified room-state block (None in
                        # single-person sessions).
                        # P0.S7.D-C: best_friend_id threaded for Section 1
                        # role hierarchy (disputed → best_friend → person_type).
                        "room_block":             _build_room_block(
                            _wiring._session_store.peek_all_snapshots(), _conversation_store._history, _per_person_agent_store.peek_all_emotion_agents(),
                            _wiring._pipeline_state_store.peek_active_room_started_at(), turn_cap=ROOM_BLOCK_TURN_CAP,
                            best_friend_id=_bf_id,
                        ),
                        # P0.S7 D-A: <<<SHARED CONTEXT>>> persisted room
                        # history (None on flag-off / single-person / no
                        # room / disputed caller).
                        "shared_context":         _build_shared_context_block(
                            room_session_id=(_cur_snap.room_session_id if _cur_snap is not None else None),
                            requester_pid=_cur_pid,
                            best_friend_id=_bf_id,
                            db=db,
                            is_disputed_fn=_is_disputed,
                            active_session_count=len(_wiring._session_store.peek_all_snapshots()),
                            limit=SHARED_CONTEXT_BLOCK_TURN_CAP,
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
                        _name_heard, _name_match_method = _name_heard_in(text, _wiring._pipeline_state_store.peek_active_system_name())
                        if _name_heard:
                            # Name heard — unlock this stranger's session
                            try:
                                _loop = asyncio.get_running_loop()
                                _loop.create_task(_wiring._session_store.set_waiting_for_name(_cur_pid, False))
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
                                    _loop.create_task(_wiring._session_store.mark_enrolled(_cur_pid, "enrolled_1"))
                                except RuntimeError:
                                    pass  # OPTIONAL
                                print(f"[Pipeline] Progressive enroll: DB entry created for {_cur_pid}")
                                # Store face embedding if vision captured one for this track.
                                # Track whether a face was actually captured so we don't write
                                # false face-witness evidence for voice-only gate passes (Bug C).
                                _face_captured = False
                                _gate_track = _track_store.peek_track_for_stranger_pid(_cur_pid)
                                _gate_emb = _track_store.peek_embedding(_gate_track) if _gate_track is not None else None
                                if _gate_emb is not None:
                                    # P0.S1 D9 — close THE GAP. Read the anti-spoof
                                    # verdict captured atomically by the producer
                                    # (background vision loop) for this track, and
                                    # thread it through add_embedding's catch-all.
                                    # Verdict=True → write proceeds. Verdict=False
                                    # or None → catch-all blocks the face write but
                                    # voice-only fallthrough (the else branch below)
                                    # still grants bootstrap credits — session opens,
                                    # speaker just can't build a face gallery.
                                    _gate_live, _gate_score, _gate_reason = (
                                        _track_store.peek_anti_spoof_verdict(_gate_track)
                                    )
                                    if db.add_embedding(
                                        _cur_pid, _gate_emb, "progressive_enroll",
                                        anti_spoof_verdict=_gate_live,
                                    ):
                                        print(f"[Pipeline] Progressive enroll: face embedding stored for {_cur_pid}")
                                        _face_captured = True
                                    elif _gate_live is not True:
                                        # Catch-all blocked the face write because anti-spoof
                                        # rejected (or no verdict captured). D9 voice-only
                                        # fallthrough — session continues; face gallery doesn't
                                        # get poisoned.
                                        print(
                                            f"[Pipeline] Anti-spoof: BLOCKED progressive_enroll "
                                            f"face write for {_cur_pid} track={_gate_track} "
                                            f"reason={_gate_reason} score={_gate_score}"
                                        )
                                        try:
                                            _track_key = str(_gate_track) if _gate_track is not None else "<none>"
                                            _rej_now = time.time()
                                            _rej_count = await _anti_spoof_rejection_store.record_rejection(
                                                _track_key, _rej_now,
                                                ANTI_SPOOF_BURST_WINDOW_SECS,
                                            )
                                            # D10.c: dashboard-only signal (no TTS to the speaker).
                                            if _wiring._brain_orchestrator is not None:
                                                _wiring._brain_orchestrator.report_anti_spoof_rejection(
                                                    track_id=_track_key,
                                                    reason=_gate_reason or ANTI_SPOOF_REASON_NO_VERDICT,
                                                    score=_gate_score,
                                                    person_id=_cur_pid,
                                                )
                                                # §14b.1 EXACT-EQUALITY trigger — fires once
                                                # when the count crosses the threshold (NOT >=,
                                                # which would re-fire on every subsequent
                                                # rejection in the window).
                                                if _rej_count == ANTI_SPOOF_BURST_THRESHOLD:
                                                    _wiring._brain_orchestrator.report_anti_spoof_burst(
                                                        track_id=_track_key,
                                                        count=_rej_count,
                                                        window_secs=ANTI_SPOOF_BURST_WINDOW_SECS,
                                                        threshold=ANTI_SPOOF_BURST_THRESHOLD,
                                                        person_id=_cur_pid,
                                                    )
                                        except Exception as _rej_e:
                                            # OPTIONAL: rejection-logging failure must not
                                            # block the user's session-open path. Print so
                                            # operators can grep, but voice-only continues.
                                            print(
                                                f"[Pipeline] anti-spoof rejection bookkeeping "
                                                f"failed for {_cur_pid}: {_rej_e!r}"
                                            )
                                if len(audio_buf) > 0:
                                    if _face_captured:
                                        # Real face captured at gate pass — seed face-witness evidence
                                        # so post-routing accumulation trusts this person on turns 2..N.
                                        try:
                                            _loop = asyncio.get_running_loop()
                                            _loop.create_task(_wiring._session_store.mark_voice_face_confirmed(_cur_pid))
                                        except RuntimeError:
                                            pass  # OPTIONAL
                                        try:
                                            _loop = asyncio.get_running_loop()
                                            _loop.create_task(_wiring._session_store.update_face_seen(
                                                _cur_pid, conf=0.50, ts=time.monotonic(), anti_spoof_live=True))  # #5 Slice B: last_face_seen (FACE_LOSS_GRACE)
                                            _loop.create_task(_wiring._session_store.set_bootstrap_credits(
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
                                            _loop.create_task(_wiring._session_store.set_bootstrap_credits(
                                                _cur_pid, N_INITIAL_VOICE_BOOTSTRAP))
                                        except RuntimeError:
                                            pass  # OPTIONAL
                                        _t = asyncio.create_task(_accumulate_voice(_cur_pid, audio_buf, db, face_verified=False))
                                    # Spec 2 Phase A (A3): sibling _accumulate_voice task — log exceptions, don't swallow.
                                    _voice_tasks.add(_t); _t.add_done_callback(_voice_accum_done_callback)
                            # Fall through to conversation_turn() with original text.
                            # LLM responds naturally to whatever they said (which included the name).
                        else:
                            # Name not heard — stay silent, keep listening
                            print(f"[STT] STRANGER/{_cur_name} [gate blocked — '{_wiring._pipeline_state_store.peek_active_system_name()}' not heard]: {text}")
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

                    # P0.S7.D-E γ — append per-speaker history for SECONDARY
                    # speakers of a multi-speaker turn BEFORE conversation_turn.
                    # Helper failures are best-effort observability (Plan v2
                    # §2.3 try/except wrapper); never interrupt the user's
                    # dispatch path.
                    if _multi_speaker_detected:
                        try:
                            _append_per_speaker_history(
                                _spans_with_pids,
                                primary_pid=_cur_pid,
                                now_ts=time.time(),
                            )
                        except Exception as _aps_e:
                            print(
                                f"[Pipeline] _append_per_speaker_history failed: "
                                f"{type(_aps_e).__name__}: {_aps_e!r}"
                            )  # OPTIONAL: best-effort observability

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
                await asyncio.wait_for(_wiring._shutdown_event.wait(), timeout=0.05)
            except asyncio.TimeoutError:
                pass

    finally:
        print("[Pipeline] Shutting down...")

        # 1. Stop audio immediately — user shouldn't hear TTS continue during cleanup.
        print("[Pipeline] Stopping audio...")
        stop_audio()

        # 1.5. Stop persistent background vision loop (sole camera reader).
        # P0.R3 D5 + P0.R8 D6 + P0.R10 D3 ORDERING INVARIANT — reverse-order
        # shutdown: audio_device_watchdog cancels FIRST (so it doesn't fire
        # post-shutdown false-positives), then heavy_worker_watchdog (so it
        # doesn't observe pool shutdown as crash events), then vision_watchdog
        # (so it doesn't respawn vision task during shutdown), then vision
        # task itself, then hw.shutdown_all_pools below. Order:
        # audio_device_watchdog → heavy_worker_watchdog → vision_watchdog
        # → vision_task → hw.shutdown_all_pools.
        if _audio_device_watchdog_task and not _audio_device_watchdog_task.done():
            _audio_device_watchdog_task.cancel()
            try:
                await asyncio.wait_for(_audio_device_watchdog_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
        if _heavy_worker_watchdog_task and not _heavy_worker_watchdog_task.done():
            _heavy_worker_watchdog_task.cancel()
            try:
                await asyncio.wait_for(_heavy_worker_watchdog_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
        if _vision_watchdog_task and not _vision_watchdog_task.done():
            _vision_watchdog_task.cancel()
            try:
                await asyncio.wait_for(_vision_watchdog_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
        if _wiring._vision_task and not _wiring._vision_task.done():
            _wiring._vision_task.cancel()
            try:
                await asyncio.wait_for(_wiring._vision_task, timeout=1.0)
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
        _cmt = _wiring._pipeline_state_store.peek_cloud_monitor_task()
        if _cmt and not _cmt.done():
            _cmt.cancel()
            try:
                await asyncio.wait_for(_cmt, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass

        # 5.5b. Cancel health log loop (Wave 5 / Item 19).
        if _health_log_task and not _health_log_task.done():
            _health_log_task.cancel()
            try:
                await asyncio.wait_for(_health_log_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass

        # 5.6. P0.R6.Z D3.c RETIREMENT (2026-05-24): the dedicated
        # diarization executor shutdown call retired. Subprocess pool
        # cleanup is covered by `hw.shutdown_all_pools(wait=True)` below
        # (which terminates the pyannote_diarize subprocess alongside
        # AdaFace + Whisper + ECAPA).

        # 5.7. P0.R6 D5 — shut down heavy-worker pools cleanly (terminates
        # AdaFace + future P0.R6.X/Y/Z worker subprocesses). `wait=True`
        # blocks until pending futures resolve so in-flight inferences
        # finish before the process exits; this avoids zombie subprocesses
        # on Linux + matches the existing cleanup-discipline pattern.
        try:
            hw.shutdown_all_pools(wait=True)
        except Exception as e:
            print(f"[Pipeline] heavy worker pool shutdown failed: {e!r}")

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

