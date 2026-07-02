"""
Shared test helpers for the KaraOS test suite.

setup_pipeline_stubs()
    Stubs core.voice and core.audio into sys.modules so pipeline.py can be
    imported on Windows without the torchaudio DLL crash (OSError 0xc0000139).

    CALL AT MODULE LEVEL BEFORE importing pipeline.py:

        from conftest import setup_pipeline_stubs
        setup_pipeline_stubs()
        from pipeline import _expire_stale_sessions

    P1.A1 SP-1: ALSO called once at module scope below (the test_pipeline.py
    split replaced the old root-file inline stub block with this conftest-import
    call), so every split test_pipeline_<concern>.py file gets the stub before it
    lazily imports pipeline. Tests that exercise the REAL core.voice (the
    retirement-surface tests test_voice.py / test_warmup.py pass against the stub;
    the real-voice golden tests) use the `real_voice` fixture below, which pops
    the stub for the duration of one test. test_voice_channel.py imports
    core.voice_channel (not stubbed by this helper), so it is unaffected.

_reset_session_state_between_tests (autouse=True)
    Resets SessionStore between every test so session state never leaks
    across tests. Also calls setup_pipeline_stubs() idempotently so
    test_session_store.py never needs to import pipeline directly.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest
import runtime.wiring as _wiring


def setup_pipeline_stubs() -> None:
    """Stub core.voice and core.audio into sys.modules if not already present.

    Idempotent — safe to call multiple times or from multiple test files.
    """
    if "core.voice" not in sys.modules:
        _voice_stub = types.ModuleType("core.voice")
        # P0.R6.Y D3 cascade: 4 voice fns become async (identify, diarize,
        # embed, _diarize_ecapa_valley). Stubs migrate to AsyncMock so
        # tests can `await` them directly. load_speaker_embedder +
        # _load_pyannote_pipeline stay MagicMock (boot-time loaders, sync).
        # _embedder stays MagicMock (model object, not callable function).
        # P0.R6.Y D3 cascade: 4 voice fns become async (identify, diarize,
        # embed, _diarize_ecapa_valley). Stubs migrate to AsyncMock so
        # tests can `await` them directly. load_speaker_embedder stays
        # MagicMock (boot-time loader, sync).
        # P0.R6.Z D3.a/D5 RETIREMENT (2026-05-24): _load_pyannote_pipeline
        # + _voice_diarize_executor + get_diarize_executor +
        # shutdown_diarize_executor stubs retired — those production
        # symbols no longer exist; pyannote pipeline lives subprocess-side
        # at core/heavy_worker.py::_get_subprocess_pyannote(). _embedder
        # stays MagicMock (model object, not callable function).
        _voice_stub.load_speaker_embedder = MagicMock(return_value=None)
        _voice_stub.identify = AsyncMock(return_value=(None, 0.0, True))
        _voice_stub.diarize = AsyncMock(return_value=[])
        _voice_stub.get_diarize_stats = MagicMock(return_value={})
        _voice_stub._embedder = MagicMock()
        _voice_stub.embed = AsyncMock(return_value=None)
        _voice_stub._diarize_ecapa_valley = AsyncMock(return_value=[])
        sys.modules["core.voice"] = _voice_stub

    if "core.audio" not in sys.modules:
        import re as _re_audio_stub
        _audio_stub = types.ModuleType("core.audio")
        for _fn in [
            "record_until_silence", "speak",
            "listen_and_transcribe", "preload_models", "stop_audio",
            "play_filler", "set_lip_active",
        ]:
            setattr(_audio_stub, _fn, MagicMock())
        _audio_stub.speak_stream = AsyncMock()
        _audio_stub._load_whisper = MagicMock()
        async def _transcribe_stub(audio):
            """P0.R6.X migration: production transcribe() is async + dispatches
            via hw.run_heavy("whisper_transcribe", ...). Stub mirrors that
            contract so tests can monkeypatch hw.run_heavy to inject text.
            Falls back to the legacy _load_whisper path when hw.run_heavy is
            unavailable (e.g. core.heavy_worker not yet imported) for
            backward-compat with tests that still monkeypatch _load_whisper.
            """
            import re as _re_tr
            import sys as _sys_tr
            import time as _time_tr
            if len(audio) == 0:
                return "", "en"
            _t0 = _time_tr.perf_counter()
            # New production path: dispatch through hw.run_heavy if available.
            _hw_mod = _sys_tr.modules.get("core.heavy_worker")
            text = None
            if _hw_mod is not None and hasattr(_hw_mod, "run_heavy"):
                try:
                    _result = await _hw_mod.run_heavy(
                        "whisper_transcribe",
                        getattr(_hw_mod, "whisper_transcribe_worker", lambda *a, **k: ("", "en")),
                        audio.tobytes() if hasattr(audio, "tobytes") else b"",
                        audio.shape if hasattr(audio, "shape") else (0,),
                        audio.dtype.name if hasattr(audio, "dtype") else "float32",
                        language="en",
                    )
                    text, _lang = _result
                except Exception:
                    text = None
            # Legacy fallback: use _load_whisper monkeypatch path. This keeps
            # any older tests that monkeypatch _load_whisper working.
            if text is None:
                model = _audio_stub._load_whisper()
                segments, _ = model.transcribe(audio)
                segments_list = list(segments)
                good = [s for s in segments_list if s.no_speech_prob < 0.6 and s.avg_logprob > -1.5]
                if not good:
                    candidates = [s for s in segments_list if s.no_speech_prob < 0.4]
                    if candidates:
                        good = [min(candidates, key=lambda s: s.no_speech_prob)]
                    else:
                        return "", "en"
                text = " ".join(s.text for s in good).strip()
            if not text:
                return "", "en"
            if _re_tr.search(r"(.)\1{15,}", text):
                print(f"[Audio] STT: (char-run hallucination filtered): '{text[:80]}'")
                return "", "en"
            _elapsed = (_time_tr.perf_counter() - _t0) * 1000.0
            _audio_stub._last_stt_elapsed_ms = _elapsed
            _now = _time_tr.localtime()
            _ms = int((_time_tr.perf_counter() % 1) * 1000)
            _ts = _time_tr.strftime(f"%H:%M:%S.{_ms:03d}", _now)
            print(f"[STT] {_ts} ({_elapsed:.0f}ms) {text!r}")
            return text, "en"
        _audio_stub.transcribe = _transcribe_stub
        _audio_stub._TTS_BOLD_RE    = _re_audio_stub.compile(r'\*{1,3}(.*?)\*{1,3}')
        _audio_stub._TTS_UNDER_RE   = _re_audio_stub.compile(r'_{1,2}(.*?)_{1,2}')
        _audio_stub._TTS_STRIKE_RE  = _re_audio_stub.compile(r'~~(.*?)~~')
        _audio_stub._TTS_CODE_RE    = _re_audio_stub.compile(r'`+([^`]*)`+')
        _audio_stub._TTS_HEADER_RE  = _re_audio_stub.compile(r'^\s*#{1,6}\s+', _re_audio_stub.MULTILINE)
        _audio_stub._TTS_BULLET_RE  = _re_audio_stub.compile(r'^\s*[-•*]\s+', _re_audio_stub.MULTILINE)
        _audio_stub._TTS_NUMLIST_RE = _re_audio_stub.compile(r'^\s*\d+[.)]\s+', _re_audio_stub.MULTILINE)
        _audio_stub._TTS_EMDASH_RE  = _re_audio_stub.compile(r'\s*—\s*|\s+--\s+')
        _audio_stub._TTS_SPACES_RE  = _re_audio_stub.compile(r'  +')
        _audio_stub._TTS_LINK_RE    = _re_audio_stub.compile(r'\[([^\]]+)\]\([^\)]+\)')
        _audio_stub._META_COMMENTARY_PATTERNS = [
            _re_audio_stub.compile(r'\bno\s+function\s+call[s]?\s+(?:is|are|were)?\s*(?:needed|required|necessary)', _re_audio_stub.IGNORECASE),
            _re_audio_stub.compile(r'\b(?:function|tool)\s+call[s]?\s+(?:is|was|are|were)\s+not\s+(?:needed|required|necessary)', _re_audio_stub.IGNORECASE),
            _re_audio_stub.compile(r"\bi\s+(?:should|will|would|won[\'`']t|do\s+not\s+need\s+to)\s+(?:call|invoke|use)\s+(?:the|a|any)\s+(?:function|tool)\b", _re_audio_stub.IGNORECASE),
            _re_audio_stub.compile(r"\bthe\s+user[\'`']s\s+(?:request|message|prompt)\s+does\s+not\s+(?:require|need)\b", _re_audio_stub.IGNORECASE),
            _re_audio_stub.compile(r"\bbased\s+on\s+(?:the|your)\s+(?:system\s+)?prompt\b", _re_audio_stub.IGNORECASE),
            _re_audio_stub.compile(r'\bas\s+an?\s+ai\b', _re_audio_stub.IGNORECASE),
            _re_audio_stub.compile(r'^\s*SILENT\s*[.!?]?\s*$', _re_audio_stub.IGNORECASE),
            _re_audio_stub.compile(r'^\s*(?:NO[\s_-]?RESPONSE|\[SILENT\]|<silent>)\s*$', _re_audio_stub.IGNORECASE),
        ]
        def _is_meta_commentary_impl(text):
            t = (text or "").strip()
            return bool(t) and any(p.search(t) for p in _audio_stub._META_COMMENTARY_PATTERNS)
        def _clean_for_tts_impl(text):
            if _is_meta_commentary_impl(text):
                return ""
            text = _audio_stub._TTS_LINK_RE.sub(r'\1', text)
            text = _audio_stub._TTS_HEADER_RE.sub('', text)
            text = _audio_stub._TTS_BOLD_RE.sub(r'\1', text)
            text = _audio_stub._TTS_UNDER_RE.sub(r'\1', text)
            text = _audio_stub._TTS_STRIKE_RE.sub(r'\1', text)
            text = _audio_stub._TTS_CODE_RE.sub(r'\1', text)
            text = _audio_stub._TTS_BULLET_RE.sub('', text)
            text = _audio_stub._TTS_NUMLIST_RE.sub('', text)
            text = _audio_stub._TTS_EMDASH_RE.sub(', ', text)
            text = _audio_stub._TTS_SPACES_RE.sub(' ', text)
            return text.strip()
        _audio_stub._is_meta_commentary = _is_meta_commentary_impl
        _audio_stub._clean_for_tts = _clean_for_tts_impl
        _audio_stub._tts_end_time = 0.0
        _audio_stub._last_speech_secs = 0.0
        _audio_stub._last_stt_elapsed_ms = 0.0
        _audio_stub._tts_kokoro = MagicMock(return_value=None)
        _audio_stub._tts_piper_en = MagicMock(return_value=(None, 0))
        _sd_stub = MagicMock()
        _sd_stub.play = MagicMock()
        _sd_stub.wait = MagicMock()
        _sd_stub.stop = MagicMock()
        _audio_stub.sd = _sd_stub
        sys.modules["core.audio"] = _audio_stub


# ── P1.A1 SP-1: install the stubs at conftest IMPORT (module scope) ──────────
# The split test_pipeline_<concern>.py files (and every other tests/ file that
# lazily `import pipeline`) need core.voice / core.audio stubbed before pipeline
# imports them. This call — replacing root test_pipeline.py's old inline
# collection-time stub block (deleted in the SP-1 split) — lands the stubs when
# pytest imports this conftest, before collecting any tests/ file. Idempotent;
# tests needing the REAL modules use the `real_voice` fixture (it pops the stub).
setup_pipeline_stubs()


@pytest.fixture(autouse=True)
def _reset_pipeline_state_between_tests():
    """Reset all Stores between every test — prevents session and pipeline state leakage.

    P0.7: resets _session_store (SessionStore).
    P0.6: resets every P0.6 Store via .reset(); hasattr guards make this
    forward-compatible as sub-PRs land new Stores.

    setup_pipeline_stubs() is idempotent; calling it here means tests
    never need to call it manually.

    _STORE_NAMES is the canonical list — tests/test_p06_store_invariants.py
    TestAutouseFixtureCoversEveryStore verifies this list stays in sync with
    core/*_store.py definitions (auditor M2 fix).
    """
    _STORE_NAMES = (
        "_presence_store",         # P0.6.2
        "_track_store",            # P0.6.2
        "_conversation_store",     # P0.6.3
        "_voice_gallery_store",    # P0.6.4
        "_per_person_agent_store", # P0.6.4
        "_identity_hints_store",   # P0.6.5
        "_query_embedding_store",  # P0.6.5
        "_scene_block_store",      # P0.6.5
        "_classifier_cache_store", # P0.6.5
        "_pipeline_state_store",   # P0.6.6
        "_vision_frame_store",     # P0.6.7v2
        "_anti_spoof_rejection_store",  # P0.S1 MED 5
    )
    setup_pipeline_stubs()
    from core.session_state import SessionStore  # noqa: PLC0415
    try:
        import pipeline as _pipeline
        # P0.7 store — replaced directly (not via .reset()) to ensure a fresh lock.
        if hasattr(_pipeline, "_session_store"):
            _wiring._session_store = SessionStore()
        # P0.6 stores — reset via .reset() (sync, no event loop needed).
        for _sname in _STORE_NAMES:
            if hasattr(_pipeline, _sname):
                getattr(_pipeline, _sname).reset()
        # P0.6.6: replace _pipeline_state_store with a fresh production-shape
        # instance — restores initial_pipeline_state=WATCHING + initial_cloud_state=ONLINE
        # defaults that reset() alone would wipe (reset() is sync arg-less).
        if (hasattr(_pipeline, "PipelineStateStore")
                and hasattr(_pipeline, "PipelineState")
                and hasattr(_pipeline, "CloudState")):
            _wiring._pipeline_state_store = _pipeline.PipelineStateStore(
                initial_pipeline_state=_pipeline.PipelineState.WATCHING,
                initial_cloud_state=_pipeline.CloudState.ONLINE,
            )
        # P0.S7.D-D — re-init RoomOrchestrator with fresh stores. The class
        # composes over the 6 dependencies; some (face_db, brain_orchestrator)
        # may be None in test contexts that don't touch those subsystems.
        # The class __init__ stores all deps without asserting; per-method
        # None checks handle the gaps (Plan v2 §4 refined 3-layer defense).
        if hasattr(_pipeline, "RoomOrchestrator"):
            _wiring._room_orchestrator = _pipeline.RoomOrchestrator(
                session_store=_pipeline._session_store,
                pipeline_state_store=_pipeline._pipeline_state_store,
                face_db=getattr(_pipeline, "_face_db_ref", None),
                brain_orchestrator=getattr(_pipeline, "_brain_orchestrator", None),
                conversation_store=_pipeline._conversation_store,
                emotion_agents=getattr(_pipeline, "_emotion_agents", {}),
            )
    except Exception as _e:
        print(f"[conftest] store reset failed: {_e!r}")
    yield


# ── P1.A1 SP-1: pipeline-globals save/restore (moved from root test_pipeline.py) ──
# Autouse save/restore of the pipeline_state_store's system_name + detected_lang
# around each test — prevents cross-test bleed of those two values. Distinct from
# the store-reset above (which replaces the Stores but does not preserve
# system_name/lang). Moved here so the SP-1 split files inherit it.
@pytest.fixture(autouse=True)
def reset_pipeline_globals():
    """Restore pipeline module globals after each test to avoid cross-test bleed."""
    import asyncio
    import pipeline
    orig_system_name   = pipeline._pipeline_state_store.peek_active_system_name()
    orig_detected_lang = pipeline._pipeline_state_store.peek_detected_lang()
    yield
    asyncio.run(pipeline._pipeline_state_store.set_active_system_name(orig_system_name))
    asyncio.run(pipeline._pipeline_state_store.set_detected_lang(orig_detected_lang))


# ── #126 D2: shared real_voice fixture + ECAPA skip gate (extracted from #125) ──────
#
# Moved verbatim from tests/test_canary3_ecapa_embed_and_rename_safety.py (#125) so EVERY
# real-voice-behavior golden test in tests/ uses ONE blessed path past the conftest stub.
# The Canary #3 lesson: a golden test that imports core.voice + asserts real behavior
# against the autouse STUB (embed → None) is vacuous (permanent false-RED). This fixture is
# the only sanctioned way to reach the real module; its `_load_ecapa_patched` assert is the
# vacuity guard. Mark such tests @pytest.mark.real_voice (registered in pytest.ini). The
# `importlib.import_module("core.voice")` below is the ONLY blessed force-import — the #126
# D4(a) tripwire excludes exactly this file (tests/conftest.py) and flags it anywhere else.


def _require_real_ecapa_or_skip():
    """Gate real-voice tests on the real SpeechBrain ECAPA model + CUDA (like the P0.R5
    anchors). A vacuous skip on GPU-less CI is the same blindness that hid the Canary #3
    bug for a week — so on the CUDA dev box / canary host this MUST actually run.

    #126 Q2 — ECAPA-SCOPED gate: it checks speechbrain + CUDA, which is what the ECAPA voice
    path needs. The `real_voice` fixture NAME is generic, but this availability gate is NOT a
    universal real-model gate — a future pyannote/whisper real-voice test must add its OWN
    model-availability gate; do not assume `real_voice` covers it."""
    pytest.importorskip("speechbrain")
    try:
        import torch
    except Exception:
        pytest.skip("torch unavailable")
    if not torch.cuda.is_available():
        pytest.skip("CUDA unavailable — real_voice tests run on the CUDA dev box / canary host")


@pytest.fixture
def real_voice():
    """Swap the conftest `core.voice` STUB for the REAL module for the duration of one test
    (function-scoped). The blessed path past the autouse stub — see the #126 D2 block above.

    Why this exists: the autouse `_reset_pipeline_state_between_tests` installs a `core.voice`
    stub whose `embed = AsyncMock(return_value=None)`. A real-voice-behavior test against that
    stub is vacuous (tests a mock hardcoded to None; permanent false-RED). This fixture pops
    the stub, imports the real `core.voice`, and — load-bearing — re-points the `voice_mod`
    alias to it on EVERY module that hosts one (tests reach embed through the
    `from core import voice as voice_mod` alias, a SEPARATE binding from sys.modules["core.voice"],
    so re-importing the module alone is NOT enough). P1.A1 SP-6.1 relocated the voice_mod-reading
    `_accumulate_voice` from pipeline.py to runtime/session.py, so BOTH modules' aliases must be
    re-pointed (see the _vm_hosts comment below).

    PI-1 hardening: try/finally restores the stub + every alias even if setup raises (so a
    setup-time assert can't leak the popped stub into sibling tests). The `_load_ecapa_patched`
    assert is MANDATORY + fail-loud — it guards against silently re-introducing the exact
    vacuity (real module never actually loaded)."""
    _require_real_ecapa_or_skip()  # the single call site for the ECAPA gate
    import importlib
    import pipeline
    import runtime.session as _rt_session  # already in sys.modules via pipeline's SP-6.1 re-export

    # P1.A1 SP-6.1: _accumulate_voice relocated pipeline.py → runtime/session.py. A function
    # reads its module-globals through its DEFINING module's __dict__, so the re-exported
    # pipeline._accumulate_voice reads `voice_mod` via runtime.session.__dict__ — the single
    # pipeline.voice_mod re-point no longer reaches it (the GT1b CUDA-only regression). Re-point
    # voice_mod on EVERY module hosting a `from core import voice as voice_mod` alias a test
    # exercises: pipeline keeps live readers in run()/_warmup_models (belt-and-braces); runtime
    # .session hosts the relocated _accumulate_voice. SP-6.2/6.3/6.4 append their modules below.
    # The hasattr filter keeps restore leak-free — only modules that actually carry voice_mod are
    # saved/set/restored (never setattr(m,'voice_mod',None) on a module that lacks the alias).
    _vm_hosts = tuple(m for m in (pipeline, _rt_session) if hasattr(m, "voice_mod"))

    _stub = sys.modules.get("core.voice")        # capture the stub BEFORE any mutation
    _saved_vm = [(m, m.voice_mod) for m in _vm_hosts]
    try:
        sys.modules.pop("core.voice", None)
        real = importlib.import_module("core.voice")
        assert hasattr(real, "_load_ecapa_patched"), \
            "real core.voice not loaded — stub still active (fixture vacuity guard)"
        for m in _vm_hosts:
            m.voice_mod = real                   # load-bearing: relocated + pipeline readers reach embed via this alias
        yield real
    finally:                                     # PI-1: always restores every alias, even on setup raise
        for m, _orig in _saved_vm:
            m.voice_mod = _orig
        if _stub is not None:
            sys.modules["core.voice"] = _stub
        else:
            sys.modules.pop("core.voice", None)
