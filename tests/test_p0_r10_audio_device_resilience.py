"""P0.R10 audio device failure resilience — 9 anchors per Plan v1 §3 LOCK.

Hybrid surface (per P0.R6/R8/R11 precedent):
- Source-inspection anchors (A1 AST + A2 AST + A5 + A7 + A8 source + A9): always work; file-based
- Behavioral anchors (A3 + A4 + A6 + A8 behavioral): require real sounddevice (skip when missing OR stubbed)

The stubbed-conftest env (Windows dev with core.audio MagicMock) returns a stub
that lacks our new symbols; we force-import via subprocess OR use file inspection.

Coverage map:
- A1: D1 record_until_silence return type Optional + try/except wrap (AST)
- A2: D1 sentinel semantic (file inspection — returns None NOT empty array)
- A3: D2.a speak wraps PortAudioError (file inspection — except clause present)
- A4: D2.b speak_stream abort-whole-stream + per-sentence count log (file inspection)
- A5: D2.d stop_audio preserves `# CLEANUP:` annotation (file inspection P0.4 LOAD-BEARING)
- A6: D3 per-channel burst counter independent (file inspection + AST)
- A7: D4 WatchdogAgent.report_audio_device_burst method (AST)
- A8: D5 HealthSnapshot.audio_degraded field + format_health_line emit + format_health_alerts 5 substrings (BEHAVIORAL via health module which is NOT stubbed)
- A9: D5 config constants present with sanity values (source)
"""
from __future__ import annotations

import ast
import pathlib
import re
import time

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_AUDIO_SRC = (REPO_ROOT / "core" / "audio.py").read_text(encoding="utf-8")
_AUDIO_AST = ast.parse(_AUDIO_SRC)
_BRAIN_AGENT_SRC = (REPO_ROOT / "core" / "brain_agent.py").read_text(encoding="utf-8")
_BRAIN_AGENT_AST = ast.parse(_BRAIN_AGENT_SRC)


def _find_fn(tree: ast.AST, name: str) -> "ast.FunctionDef | ast.AsyncFunctionDef | None":
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


# ─────────────────────────────────────────────────────────────────────────────
# A1: D1 record_until_silence return type Optional + try/except PortAudioError wrap (AST)
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r10_d1_record_until_silence_wraps_portaudio_error():
    fn = _find_fn(_AUDIO_AST, "record_until_silence")
    assert fn is not None, "record_until_silence not found"

    # Return type annotation must allow None (Optional)
    ret_str = ast.unparse(fn.returns) if fn.returns else ""
    assert "None" in ret_str, (
        f"D1 record_until_silence return type must be Optional[np.ndarray]; got: {ret_str!r}"
    )

    # AST scan: find try/except wrapping a `with sd.InputStream(...)` block
    found_wrap = False
    for sub in ast.walk(fn):
        if not isinstance(sub, ast.Try):
            continue
        has_input_stream = False
        for body_stmt in ast.walk(sub):
            if isinstance(body_stmt, ast.With):
                with_src = ast.unparse(body_stmt)
                if "sd.InputStream" in with_src:
                    has_input_stream = True
        has_portaudio_handler = False
        has_record_failure = False
        has_return_none = False
        for handler in sub.handlers:
            if handler.type is None:
                continue
            handler_src = ast.unparse(handler.type)
            if "PortAudioError" in handler_src and "OSError" in handler_src:
                has_portaudio_handler = True
                body_src = ast.unparse(handler.body)
                if "_record_audio_failure" in body_src and "'mic'" in body_src.replace('"', "'"):
                    has_record_failure = True
                if "return None" in body_src or any(
                    isinstance(s, ast.Return) and (s.value is None or (isinstance(s.value, ast.Constant) and s.value.value is None))
                    for s in handler.body
                ):
                    has_return_none = True
        if has_input_stream and has_portaudio_handler and has_record_failure and has_return_none:
            found_wrap = True
            break

    assert found_wrap, (
        "D1: record_until_silence must wrap `with sd.InputStream(...)` in try/except "
        "(sd.PortAudioError, OSError) that calls _record_audio_failure('mic') + returns None"
    )


# ─────────────────────────────────────────────────────────────────────────────
# A2: D1 sentinel semantic — None NOT empty np.array (Q3 (a) LOAD-BEARING)
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r10_d1_mic_failure_returns_none_not_empty_array():
    # Q3 (a) load-bearing: empty np.ndarray means user silence; None means device failure.
    # Verify the D1 handler's return is None (not np.array([]), np.zeros(0), etc.)
    fn = _find_fn(_AUDIO_AST, "record_until_silence")
    assert fn is not None
    for sub in ast.walk(fn):
        if not isinstance(sub, ast.Try):
            continue
        for handler in sub.handlers:
            if handler.type is None:
                continue
            handler_src = ast.unparse(handler.type)
            if "PortAudioError" not in handler_src:
                continue
            body_src = ast.unparse(handler.body)
            # Must contain `return None` and NOT `np.zeros` / `np.array([])` / `np.ndarray`
            assert "return None" in body_src or any(
                isinstance(s, ast.Return) and isinstance(s.value, ast.Constant) and s.value.value is None
                for s in handler.body
            ), f"D1 PortAudio handler must `return None`; body: {body_src!r}"
            assert "np.zeros" not in body_src and "np.array(" not in body_src, (
                f"D1 PortAudio handler must NOT return empty np.array (Q3 (a) sentinel semantic broken); body: {body_src!r}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# A3: D2.a speak wraps PortAudioError (file inspection)
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r10_d2_speak_wraps_portaudio_error():
    fn = _find_fn(_AUDIO_AST, "speak")
    assert fn is not None and isinstance(fn, ast.AsyncFunctionDef), "speak must be async"

    found_speaker_handler = False
    for sub in ast.walk(fn):
        if not isinstance(sub, ast.Try):
            continue
        for handler in sub.handlers:
            if handler.type is None:
                continue
            handler_src = ast.unparse(handler.type)
            if "PortAudioError" in handler_src and "OSError" in handler_src:
                body_src = ast.unparse(handler.body)
                if "_record_audio_failure" in body_src and "'speaker'" in body_src.replace('"', "'"):
                    found_speaker_handler = True

    assert found_speaker_handler, (
        "D2.a: speak must catch (sd.PortAudioError, OSError) and call _record_audio_failure('speaker')"
    )


# ─────────────────────────────────────────────────────────────────────────────
# A4: D2.b speak_stream abort-whole-stream + per-sentence count log (Q2 (b))
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r10_d2_speak_stream_aborts_whole_stream_on_mid_stream_failure():
    fn = _find_fn(_AUDIO_AST, "speak_stream")
    assert fn is not None and isinstance(fn, ast.AsyncFunctionDef), "speak_stream must be async"

    # Q2 (b) RATIFIED — verify per-sentence count variables present + abort semantic
    fn_src = ast.unparse(fn)
    assert "_sentence_count" in fn_src, "speak_stream must track _sentence_count"
    assert "_sentence_total" in fn_src, "speak_stream must track _sentence_total"

    # Verify PortAudioError handler within play_worker has break (abort) + per-sentence log
    found_abort = False
    for sub in ast.walk(fn):
        if not isinstance(sub, ast.Try):
            continue
        for handler in sub.handlers:
            if handler.type is None:
                continue
            handler_src = ast.unparse(handler.type)
            if "PortAudioError" not in handler_src or "OSError" not in handler_src:
                continue
            handler_body_src = ast.unparse(handler.body)
            if (
                "_record_audio_failure" in handler_body_src
                and "'speaker'" in handler_body_src.replace('"', "'")
                and "_sentence_count" in handler_body_src
                and "_sentence_total" in handler_body_src
                and any(isinstance(s, ast.Break) for s in ast.walk(handler))
            ):
                found_abort = True

    assert found_abort, (
        "D2.b: speak_stream must catch (sd.PortAudioError, OSError) inside play_worker; "
        "log per-sentence count + record failure + break (abort whole stream)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# A5: D2.d stop_audio preserves `# CLEANUP:` annotation (P0.4 LOAD-BEARING)
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r10_d2_stop_audio_preserves_cleanup_annotation():
    # P0.4 silent-except policy LOAD-BEARING: the # CLEANUP: annotation must be
    # present at the pass line so test_no_unannotated_silent_excepts_in_production_code
    # remains green.
    fn = _find_fn(_AUDIO_AST, "stop_audio")
    assert fn is not None, "stop_audio not found"

    # File-text scan: stop_audio body must contain # CLEANUP: annotation +
    # explicit (sd.PortAudioError, OSError) handler + defensive Exception handler
    # Locate the function source as raw text (preserves comments)
    fn_start_line = fn.lineno
    fn_end_line = fn.end_lineno or fn_start_line + 20
    fn_text = "\n".join(_AUDIO_SRC.splitlines()[fn_start_line - 1:fn_end_line])

    assert "# CLEANUP:" in fn_text, (
        f"D2.d regression: `# CLEANUP:` annotation comment removed from stop_audio. "
        f"P0.4 silent-except policy LOAD-BEARING. Function body:\n{fn_text}"
    )
    assert "except (sd.PortAudioError, OSError):" in fn_text, (
        f"stop_audio must catch (sd.PortAudioError, OSError) explicitly per D2.d spec"
    )
    assert "except Exception:" in fn_text, (
        f"stop_audio must retain defensive `except Exception:` per D2.d spec"
    )


# ─────────────────────────────────────────────────────────────────────────────
# A6: D3 per-channel burst counter independent (file + AST)
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r10_d3_per_channel_burst_counter_independent():
    # AST verification: 3 functions + module-level state present
    assert "_AUDIO_FAILURE_HISTORY" in _AUDIO_SRC
    assert "_AUDIO_FAILURE_LOCK" in _AUDIO_SRC and "threading.Lock()" in _AUDIO_SRC
    assert "def _record_audio_failure(" in _AUDIO_SRC
    assert "def count_recent_audio_failures(" in _AUDIO_SRC
    assert "def peek_audio_failure_history(" in _AUDIO_SRC

    fn_record = _find_fn(_AUDIO_AST, "_record_audio_failure")
    fn_count = _find_fn(_AUDIO_AST, "count_recent_audio_failures")
    assert fn_record is not None and fn_count is not None

    # AST-strict: setdefault MUST be called with `channel` Name as first arg
    # (NOT a string literal like "_shared" — that breaks per-channel granularity).
    # Defense against shared-counter regression (Plan v1 §4 scenario f).
    found_keyed_setdefault = False
    for sub in ast.walk(fn_record):
        if not isinstance(sub, ast.Call):
            continue
        if not (isinstance(sub.func, ast.Attribute) and sub.func.attr == "setdefault"):
            continue
        if not sub.args:
            continue
        first_arg = sub.args[0]
        # First arg must be `channel` Name reference, NOT a Constant string
        if isinstance(first_arg, ast.Name) and first_arg.id == "channel":
            found_keyed_setdefault = True
    assert found_keyed_setdefault, (
        f"D3 _record_audio_failure must call setdefault(channel, ...) with the channel "
        f"parameter Name (NOT a string literal like '_shared'). Per-channel granularity "
        f"Q1 (a) LOAD-BEARING."
    )

    # Verify count_recent_audio_failures filters by channel + window via Name refs
    count_src = ast.unparse(fn_count)
    assert "channel" in count_src and "cutoff" in count_src, (
        f"D3 count_recent_audio_failures must filter by channel + rolling window"
    )


# ─────────────────────────────────────────────────────────────────────────────
# A7: D4 WatchdogAgent.report_audio_device_burst (AST + behavioral)
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r10_d4_watchdog_report_audio_device_burst_method():
    assert "def report_audio_device_burst(" in _BRAIN_AGENT_SRC

    found_method = False
    found_store_alert = False
    for cls in ast.walk(_BRAIN_AGENT_AST):
        if not (isinstance(cls, ast.ClassDef) and cls.name == "WatchdogAgent"):
            continue
        for fn in cls.body:
            if not (isinstance(fn, ast.FunctionDef) and fn.name == "report_audio_device_burst"):
                continue
            found_method = True
            for sub in ast.walk(fn):
                if not isinstance(sub, ast.Call):
                    continue
                src_str = ast.unparse(sub)
                if "store_alert" in src_str and "audio_device_burst_" in src_str:
                    found_store_alert = True

    assert found_method, "WatchdogAgent.report_audio_device_burst not found"
    assert found_store_alert, "store_alert call with audio_device_burst_ prefix missing"


# ─────────────────────────────────────────────────────────────────────────────
# A8: D5 HealthSnapshot.audio_degraded field + format_health_line + format_health_alerts
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r10_d5_health_snapshot_audio_degraded_field_and_alerts():
    from core import health
    from dataclasses import fields

    field_names = {f.name for f in fields(health.HealthSnapshot)}
    assert "audio_degraded" in field_names, (
        f"HealthSnapshot.audio_degraded field missing; got: {field_names}"
    )

    # Build snapshot with audio_degraded non-empty
    now = time.time()
    snap = health.HealthSnapshot(
        timestamp=now,
        active_sessions=0,
        sessions_by_type={"best_friend": 0, "known": 0, "stranger": 0, "disputed": 0},
        persons_count=0,
        total_face_embeddings=0,
        knowledge_active_rows=0,
        shadow_persons_count=0,
        classifier_scenarios_active=0,
        classifier_scenarios_quarantined=0,
        cloud_state="OFFLINE",
        active_disputes=0,
        unresolved_watchdog_alerts=0,
        last_dream_run_seconds_ago=None,
        thin_voice_galleries=[],
        audio_degraded={"mic": True, "speaker": False},
    )

    line = health.format_health_line(snap)
    assert "audio_degraded=mic" in line, (
        f"Expected `audio_degraded=mic` in health line; got: {line}"
    )

    class _StubBrain:
        class _stub:
            class _conn:
                @staticmethod
                def execute(*a, **kw):
                    return []
            _conn = _conn()
        _brain_db = _stub()
        _kuzu_degraded = False

    alerts = health.format_health_alerts(snap, _StubBrain())
    alerts_text = " ".join(alerts)
    for substring in (
        "Audio device degraded",
        "channels:",
        "USB/audio device connection",
        "driver",
        "AUDIO_DEVICE_BURST_THRESHOLD",
    ):
        assert substring in alerts_text, (
            f"Verbatim substring '{substring}' missing: {alerts_text}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# A9: D5 config constants present with sanity values
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r10_d5_config_constants_present():
    from core import config
    assert hasattr(config, "AUDIO_DEVICE_WATCHDOG_INTERVAL_SECS")
    assert hasattr(config, "AUDIO_DEVICE_BURST_THRESHOLD")
    assert hasattr(config, "AUDIO_DEVICE_BURST_WINDOW_SECS")
    assert config.AUDIO_DEVICE_WATCHDOG_INTERVAL_SECS == 10.0
    assert config.AUDIO_DEVICE_BURST_THRESHOLD == 3
    assert config.AUDIO_DEVICE_BURST_WINDOW_SECS == 60.0
