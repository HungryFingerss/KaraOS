"""
Shared test helpers for the dog-ai test suite.

setup_pipeline_stubs()
    Stubs core.voice and core.audio into sys.modules so pipeline.py can be
    imported on Windows without the torchaudio DLL crash (OSError 0xc0000139).

    CALL AT MODULE LEVEL BEFORE importing pipeline.py:

        from conftest import setup_pipeline_stubs
        setup_pipeline_stubs()
        from pipeline import _expire_stale_sessions

    NOT applied automatically at conftest module scope — that would shadow
    core.voice / core.audio for tests that exercise the real modules
    (e.g. tests/test_voice.py, tests/test_voice_channel.py).

_reset_session_state_between_tests (autouse=True)
    Resets SessionStore between every test so session state never leaks
    across tests. Also calls setup_pipeline_stubs() idempotently so
    test_session_store.py never needs to import pipeline directly.
"""
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest


def setup_pipeline_stubs() -> None:
    """Stub core.voice and core.audio into sys.modules if not already present.

    Idempotent — safe to call multiple times or from multiple test files.
    """
    if "core.voice" not in sys.modules:
        _voice_stub = types.ModuleType("core.voice")
        _voice_stub.load_speaker_embedder = MagicMock(return_value=None)
        _voice_stub.identify = MagicMock(return_value=(None, 0.0))
        _voice_stub.diarize = MagicMock(return_value=[])
        _voice_stub.get_diarize_stats = MagicMock(return_value={})
        _voice_stub._embedder = MagicMock()
        _voice_stub._load_pyannote_pipeline = MagicMock(return_value=None)
        _voice_stub.embed = MagicMock(return_value=None)
        _voice_stub._voice_diarize_executor = None
        _voice_stub._diarize_ecapa_valley = MagicMock(return_value=[])
        def _get_diarize_executor_cf():
            from concurrent.futures import ThreadPoolExecutor
            _vsm = sys.modules["core.voice"]
            if _vsm._voice_diarize_executor is None:
                _vsm._voice_diarize_executor = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="voice-diarize"
                )
            return _vsm._voice_diarize_executor
        def _shutdown_diarize_executor_cf():
            _vsm = sys.modules["core.voice"]
            if _vsm._voice_diarize_executor is not None:
                _vsm._voice_diarize_executor.shutdown(wait=False)
                _vsm._voice_diarize_executor = None
        _voice_stub.get_diarize_executor = _get_diarize_executor_cf
        _voice_stub.shutdown_diarize_executor = _shutdown_diarize_executor_cf
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
        def _transcribe_stub(audio):
            import re as _re_tr
            import time as _time_tr
            if len(audio) == 0:
                return "", "en"
            _t0 = _time_tr.perf_counter()
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
        "_cache_store",            # P0.6.5
        "_pipeline_state_store",   # P0.6.6
    )
    setup_pipeline_stubs()
    from core.session_state import SessionStore  # noqa: PLC0415
    try:
        import pipeline as _pipeline
        # P0.7 store — replaced directly (not via .reset()) to ensure a fresh lock.
        if hasattr(_pipeline, "_session_store"):
            _pipeline._session_store = SessionStore()
        # P0.6 stores — reset via .reset() (sync, no event loop needed).
        for _sname in _STORE_NAMES:
            if hasattr(_pipeline, _sname):
                getattr(_pipeline, _sname).reset()
    except Exception as _e:
        print(f"[conftest] store reset failed: {_e!r}")
    yield
