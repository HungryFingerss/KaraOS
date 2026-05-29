"""tests/test_p0_s7_3_kairos_baseline.py — P0.S7.3 KAIROS silence baseline fix.

Spec: tests/p0_s7_3_spec.md (direct-to-developer micro-fix).

Bug: pre-fix `_silence_elapsed = now - _last_user_speech_at` accumulated
silence from BEFORE the brain started speaking. During a 3-min TTS, by the
time TTS ends `_silence_elapsed > KAIROS_SILENCE_THRESHOLD_SECS` so KAIROS
fires immediately — feels intrusive, no breathing room.

Fix: silence baseline = max(last_user_speech_at, _tts_end_time). Brain-
speaking time no longer counts as "silence."

3 tests:
  1. baseline_uses_max_of_user_speech_and_tts_end — recent TTS suppresses KAIROS
  2. fires_after_threshold_from_tts_end — TTS old enough → KAIROS fires
  3. threshold_constant_is_configurable_float — config shape (rename + bump)
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import pathlib
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_CONFIG_PY = _REPO_ROOT / "core" / "config.py"


# ────────────────────────────────────────────────────────────────────────────
# Shared async fixture — restore pipeline/audio state between tests
# ────────────────────────────────────────────────────────────────────────────


async def _seed_state(speech_secs_ago: float, tts_secs_ago: float, *,
                      cooldown_clear: bool = True):
    """Set both silence-baseline sources + open a session so the helper
    returns past the early gates. Returns (orig_speech_at, orig_kairos_at,
    orig_tts_end_time, orig_orchestrator) for caller to restore."""
    import pipeline
    import core.audio as _audio_mod

    orig_speech_at = pipeline._pipeline_state_store.peek_last_user_speech_at()
    orig_kairos_at = pipeline._pipeline_state_store.peek_last_kairos_at()
    orig_tts_end   = float(getattr(_audio_mod, "_tts_end_time", 0.0))
    orig_orch      = pipeline._brain_orchestrator

    now = time.time()
    await pipeline._session_store.open_session(
        "p1", "Alice", "known", "face", now=now,
    )
    await pipeline._pipeline_state_store.set_last_user_speech_at(now - speech_secs_ago)
    if cooldown_clear:
        await pipeline._pipeline_state_store.set_last_kairos_at(0.0)
    _audio_mod._tts_end_time = now - tts_secs_ago

    mock_orch = MagicMock()
    mock_orch.get_pending_question.return_value = {"id": "q1", "text": "How are you?"}
    pipeline._brain_orchestrator = mock_orch

    return orig_speech_at, orig_kairos_at, orig_tts_end, orig_orch, mock_orch


async def _restore_state(orig_speech_at, orig_kairos_at, orig_tts_end, orig_orch):
    import pipeline
    import core.audio as _audio_mod
    await pipeline._pipeline_state_store.set_last_user_speech_at(orig_speech_at)
    await pipeline._pipeline_state_store.set_last_kairos_at(orig_kairos_at)
    _audio_mod._tts_end_time = orig_tts_end
    pipeline._brain_orchestrator = orig_orch


# ────────────────────────────────────────────────────────────────────────────
# Test 1 — recent TTS suppresses KAIROS (new behavior)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_kairos_silence_baseline_uses_max_of_user_speech_and_tts_end():
    """TTS ended 10s ago, user spoke 200s ago. silence_baseline = max(...) =
    10s ago (TTS more recent). silence_elapsed = 10s < 120s threshold → KAIROS
    must NOT fire. Pre-fix: silence_elapsed = 200s > 30s old threshold → would
    fire. Catches the regression."""
    import pipeline

    state = await _seed_state(speech_secs_ago=200.0, tts_secs_ago=10.0)
    orig_speech_at, orig_kairos_at, orig_tts_end, orig_orch, mock_orch = state

    try:
        result = await pipeline._kairos_tick("p1", "Alice", MagicMock())
    finally:
        await _restore_state(orig_speech_at, orig_kairos_at, orig_tts_end, orig_orch)

    assert result is False, (
        "P0.S7.3 regression: KAIROS fired despite TTS having ended only 10s "
        "ago. The silence baseline must be max(last_user_speech_at, "
        "_tts_end_time) — brain-speaking time does NOT count as silence."
    )
    # Pre-fix code would have passed the silence gate and called
    # get_pending_question(); post-fix it returns before that point.
    mock_orch.get_pending_question.assert_not_called()


# ────────────────────────────────────────────────────────────────────────────
# Test 2 — TTS old enough → KAIROS still fires (no regression on intended path)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_kairos_fires_after_threshold_from_tts_end():
    """TTS ended 121s ago, user spoke 200s ago. silence_baseline = max(...) =
    121s ago. silence_elapsed = 121s > 120s threshold → KAIROS DOES fire.
    Proves the fix doesn't over-suppress — only suppresses while the brain is
    still recently speaking."""
    import pipeline

    state = await _seed_state(speech_secs_ago=200.0, tts_secs_ago=121.0)
    orig_speech_at, orig_kairos_at, orig_tts_end, orig_orch, mock_orch = state

    try:
        with patch("pipeline.speak_stream", new_callable=AsyncMock), \
             patch("pipeline._sentence_stream", return_value=None), \
             patch("pipeline.ask_stream") as mock_ask, \
             patch("pipeline._set_state"):
            async def _fake_ask(*args, **kwargs):
                return
                yield  # make it an async generator
            mock_ask.return_value = _fake_ask()
            await pipeline._kairos_tick("p1", "Alice", MagicMock())
    finally:
        await _restore_state(orig_speech_at, orig_kairos_at, orig_tts_end, orig_orch)

    # Silence gate opened (121s > 120s); KAIROS attempted to run.
    mock_orch.get_pending_question.assert_called(), (
        "P0.S7.3 over-suppression: KAIROS did NOT fire despite TTS having "
        "ended 121s ago (> 120s threshold). The baseline change must not "
        "over-suppress legitimate firings."
    )


# ────────────────────────────────────────────────────────────────────────────
# Test 3 — config constant shape (renamed + bumped + float type + lower bound)
# ────────────────────────────────────────────────────────────────────────────


def test_kairos_threshold_constant_is_configurable_float():
    """Plan v2 §2.2 — KAIROS_SILENCE_THRESHOLD_SECS exists in core/config.py,
    is a float, value ≥ 60 (lower-bound safety: under 60s starts to feel
    intrusive again; user can tune within the safe range)."""
    import core.config as cfg

    # 1. Renamed constant exists.
    assert hasattr(cfg, "KAIROS_SILENCE_THRESHOLD_SECS"), (
        "P0.S7.3 §2.2: core/config.py must expose "
        "`KAIROS_SILENCE_THRESHOLD_SECS` (renamed from KAIROS_SILENCE_THRESHOLD)"
    )
    # 2. Old name removed.
    assert not hasattr(cfg, "KAIROS_SILENCE_THRESHOLD"), (
        "P0.S7.3 §2.2: legacy `KAIROS_SILENCE_THRESHOLD` must be removed "
        "(no aliasing). The rename forces explicit caller migration."
    )
    # 3. Float type.
    val = cfg.KAIROS_SILENCE_THRESHOLD_SECS
    assert isinstance(val, float), (
        f"KAIROS_SILENCE_THRESHOLD_SECS must be a float; got {type(val).__name__}"
    )
    # 4. Lower-bound safety — values below 60s start to feel intrusive again.
    assert val >= 60.0, (
        f"KAIROS_SILENCE_THRESHOLD_SECS={val!r} is below the 60s safety floor. "
        f"P0.S7.3 default is 120s; tuning is allowed but below 60s reintroduces "
        f"the intrusiveness Bug 2 documented."
    )


def test_kairos_silence_baseline_source_logged():
    """P0.S7.3 §2.3 — the [KAIROS] firing log line includes
    `baseline=tts_end|user_speech` so canary log surfaces which baseline
    drove each firing. Source-inspection (the log path runs deep inside
    _kairos_tick; structural check is the cleanest way to lock the
    format)."""
    src = (_REPO_ROOT / "pipeline.py").read_text(encoding="utf-8")
    # The firing log line must include the baseline field.
    assert "baseline=" in src, (
        "P0.S7.3 §2.3: [KAIROS] log must include baseline=<source> field"
    )
    # The source-deciding ternary uses _last_tts_end vs _last_user.
    assert "_baseline_source" in src, (
        "P0.S7.3 §2.3: a `_baseline_source` local must compute "
        "'tts_end' vs 'user_speech' label for the log"
    )
