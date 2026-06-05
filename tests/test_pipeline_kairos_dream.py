"""test_pipeline_kairos_dream — kairos dream tests (split from test_pipeline.py, P1.A1 SP-1).

Behavior-neutral move: test bodies are verbatim from the original root
test_pipeline.py. `import pipeline` stays lazy inside each test body (stubs are
installed by tests/conftest.py).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import asyncio
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
import types
import pytest
import numpy as np
import time as _time_mod
import numpy as _np


def test_kairos_tick_uses_is_disputed_helper():
    """Session 73 post-review Critical #1: _kairos_tick previously used
    raw `!= "disputed"` to gate db.log_turn, bypassing the single-source-of-
    truth helper AND slipping through the `==`-only grep invariant. Must now
    route through ``_is_disputed`` (positive form + `not`)."""
    import inspect, pipeline
    src = inspect.getsource(pipeline._kairos_tick)
    assert "_is_disputed(person_id)" in src, (
        "_kairos_tick must consult the shared helper — NOT a raw string comparison"
    )
    # Negative check: no raw != "disputed" anywhere in the function body.
    assert '!= "disputed"' not in src, (
        "_kairos_tick must NOT use raw `!= \"disputed\"` (Critical #1 regression)"
    )


async def test_kairos_tick_logs_turns_and_notifies_brain():
    """Successful KAIROS fires db.log_turn for both turns and calls brain notify()."""
    import pipeline

    mock_db           = MagicMock()
    mock_orchestrator = MagicMock()
    mock_orchestrator.get_pending_question.return_value = {
        "id": "q1", "text": "How are you feeling?"
    }

    orig_last_speech = pipeline._pipeline_state_store.peek_last_user_speech_at()
    orig_last_kairos = pipeline._pipeline_state_store.peek_last_kairos_at()
    # P0.S7.3 — threshold bumped 30s → 120s + baseline now = max(last_user_speech_at, _tts_end_time).
    # Canary #2 clock spec #4: KAIROS elapsed-math is MONOTONIC now — seed on time.monotonic().
    # Seed 150s past last_user_speech (clears 120s threshold via the user-speech baseline);
    # _tts_end_time_monotonic defaults to 0.0 module init, so the max resolves to the user-speech ts.
    await pipeline._pipeline_state_store.set_last_user_speech_at(_time_mod.monotonic() - 150)
    await pipeline._pipeline_state_store.set_last_kairos_at(_time_mod.monotonic() - 200)  # past 120s cooldown

    async def fake_ask_stream(*args, **kwargs):
        yield ("text", "Hey, how are you feeling today?")

    async def fake_speak_stream(sentences, **kw):
        async for _ in sentences:
            pass

    try:
        with patch("pipeline._brain_orchestrator", mock_orchestrator), \
             patch("pipeline.ask_stream",   new=fake_ask_stream), \
             patch("pipeline.speak_stream", new=fake_speak_stream), \
             patch("pipeline._set_state"):
            result = await pipeline._kairos_tick("jagan_abc123", "Jagan", mock_db)
    finally:
        await pipeline._pipeline_state_store.set_last_user_speech_at(orig_last_speech)
        await pipeline._pipeline_state_store.set_last_kairos_at(orig_last_kairos)

    assert result is True
    assert mock_db.log_turn.call_count == 2
    calls = mock_db.log_turn.call_args_list
    assert calls[0].args == ("jagan_abc123", "user", "[silence]")
    assert calls[1].args[0] == "jagan_abc123"
    assert calls[1].args[1] == "assistant"
    assert len(calls[1].args[2]) > 0
    mock_orchestrator.notify.assert_called_once()


async def test_kairos_tick_skips_stranger():
    """KAIROS must not fire for strangers — returns False immediately."""
    import pipeline
    mock_db = MagicMock()
    result = await pipeline._kairos_tick("stranger_abc123", "Stranger", mock_db)
    assert result is False
    mock_db.log_turn.assert_not_called()


async def test_kairos_tick_no_log_when_llm_returns_empty():
    """If the LLM returns an empty response, no db.log_turn should be called."""
    import pipeline

    mock_db           = MagicMock()
    mock_orchestrator = MagicMock()
    mock_orchestrator.get_pending_question.return_value = {
        "id": "q2", "text": "What did you eat today?"
    }

    orig_last_speech = pipeline._pipeline_state_store.peek_last_user_speech_at()
    orig_last_kairos = pipeline._pipeline_state_store.peek_last_kairos_at()
    await pipeline._pipeline_state_store.set_last_user_speech_at(_time_mod.time() - 60)
    await pipeline._pipeline_state_store.set_last_kairos_at(_time_mod.time() - 200)

    async def fake_ask_stream_empty(*args, **kwargs):
        return
        yield  # make it an async generator

    async def fake_speak_stream(sentences, **kw):
        async for _ in sentences:
            pass

    try:
        with patch("pipeline._brain_orchestrator", mock_orchestrator), \
             patch("pipeline.ask_stream",   new=fake_ask_stream_empty), \
             patch("pipeline.speak_stream", new=fake_speak_stream), \
             patch("pipeline._set_state"):
            result = await pipeline._kairos_tick("jagan_abc123", "Jagan", mock_db)
    finally:
        await pipeline._pipeline_state_store.set_last_user_speech_at(orig_last_speech)
        await pipeline._pipeline_state_store.set_last_kairos_at(orig_last_kairos)

    mock_db.log_turn.assert_not_called()
    mock_orchestrator.notify.assert_not_called()


async def test_kairos_tick_silent_before_threshold():
    """KAIROS must not fire when user has spoken within the silence threshold."""
    import pipeline
    mock_db = MagicMock()
    mock_orchestrator = MagicMock()

    orig_last_speech = pipeline._pipeline_state_store.peek_last_user_speech_at()
    await pipeline._pipeline_state_store.set_last_user_speech_at(_time_mod.time() - 5)   # only 5s ago, threshold is 30s

    try:
        with patch("pipeline._brain_orchestrator", mock_orchestrator):
            result = await pipeline._kairos_tick("jagan_abc123", "Jagan", mock_db)
    finally:
        await pipeline._pipeline_state_store.set_last_user_speech_at(orig_last_speech)

    assert result is False
    mock_db.log_turn.assert_not_called()


@pytest.mark.asyncio
async def test_dream_runs_when_idle():
    """I5: dream fires when no active sessions and cooldown has elapsed."""
    import pipeline
    from pipeline import _dream_loop

    from core.session_state import SessionStore
    pipeline._shutdown_event = asyncio.Event()
    pipeline._session_store = SessionStore()
    pipeline._brain_orchestrator = MagicMock()
    pipeline._brain_orchestrator.dream = AsyncMock()
    mock_db = MagicMock()
    mock_db.prune_old_strangers_async = AsyncMock(return_value=[])
    mock_db.find_stale_stranger_voice_ids.return_value = []

    try:
        # time.time returns a small value so cooldown/max_interval comparisons are predictable
        with patch("pipeline.time") as mock_time, \
             patch("pipeline.DREAM_IDLE_MINUTES", 0), \
             patch("pipeline.DREAM_COOLDOWN", 0), \
             patch("pipeline.DREAM_MAX_INTERVAL", 99999):
            mock_time.time.return_value = 1.0  # now=1, last=0 → cooldown elapsed, force not reached
            async def stop_after_dream():
                await asyncio.sleep(0.15)
                pipeline._shutdown_event.set()
            await asyncio.gather(_dream_loop(mock_db), stop_after_dream())
        pipeline._brain_orchestrator.dream.assert_called()
    finally:
        pipeline._shutdown_event = None


@pytest.mark.asyncio
async def test_dream_force_trigger_fires_during_active_session():
    """I5: dream fires via force trigger even when sessions are active."""
    import pipeline
    from pipeline import _dream_loop

    pipeline._shutdown_event = asyncio.Event()
    pipeline._brain_orchestrator = MagicMock()
    pipeline._brain_orchestrator.dream = AsyncMock()
    mock_db = MagicMock()
    mock_db.prune_old_strangers_async = AsyncMock(return_value=[])
    mock_db.find_stale_stranger_voice_ids.return_value = []

    try:
        with patch("pipeline.time") as mock_time, \
             patch("pipeline.DREAM_IDLE_MINUTES", 0), \
             patch("pipeline.DREAM_COOLDOWN", 99999), \
             patch("pipeline.DREAM_MAX_INTERVAL", 0):
            mock_time.time.return_value = 1.0  # now=1, last=0 → force_trigger (1 >= 0)
            async def stop_after_dream():
                await asyncio.sleep(0.15)
                pipeline._shutdown_event.set()
            await asyncio.gather(_dream_loop(mock_db), stop_after_dream())
        pipeline._brain_orchestrator.dream.assert_called()
    finally:
        pipeline._shutdown_event = None


@pytest.mark.asyncio
async def test_dream_skips_when_busy_and_not_forced():
    """I5: dream does NOT fire when sessions active and force threshold not reached."""
    import pipeline
    from pipeline import _dream_loop

    pipeline._shutdown_event = asyncio.Event()
    pipeline._brain_orchestrator = MagicMock()
    pipeline._brain_orchestrator.dream = AsyncMock()
    mock_db = MagicMock()
    mock_db.prune_old_strangers_async = AsyncMock(return_value=[])
    mock_db.find_stale_stranger_voice_ids.return_value = []
    # SessionStore must reflect the active session so idle_trigger is False.
    await pipeline._session_store.open_session("p1", "unknown", "stranger", "face", now=0.0)

    try:
        with patch("pipeline.time") as mock_time, \
             patch("pipeline.DREAM_IDLE_MINUTES", 0), \
             patch("pipeline.DREAM_COOLDOWN", 0), \
             patch("pipeline.DREAM_MAX_INTERVAL", 99999):
            mock_time.time.return_value = 1.0  # now=1, last=0 → force_trigger (1 >= 99999) = False
            async def stop_quickly():
                await asyncio.sleep(0.15)
                pipeline._shutdown_event.set()
            await asyncio.gather(_dream_loop(mock_db), stop_quickly())
        pipeline._brain_orchestrator.dream.assert_not_called()
    finally:
        pipeline._shutdown_event = None


def test_kairos_clock_not_reset_on_reentry_after_no_speech():
    """Issue 4: When the conversation loop re-enters after 'No speech detected',
    _last_user_speech_at must NOT be reset (kairos_clock_reset already consumed)."""
    import asyncio, pipeline, time
    orig_speech_at = pipeline._pipeline_state_store.peek_last_user_speech_at()
    try:
        past = time.time() - 50  # 50 seconds ago
        asyncio.run(pipeline._pipeline_state_store.set_last_user_speech_at(past))

        # Session with flag already consumed — simulates re-entry after "No speech detected"
        asyncio.run(pipeline._session_store.open_session("p1", "Jagan", "known", "face", now=time.time()))
        asyncio.run(pipeline._session_store.consume_kairos_reset("p1"))  # flag now False

        # Inline the conditional from pipeline.py (reads from session store)
        _snap = pipeline._session_store.peek_snapshot("p1")
        if _snap is not None and _snap.kairos_clock_reset:
            asyncio.run(pipeline._pipeline_state_store.set_last_user_speech_at(time.time()))

        # Clock must NOT have been reset — silence should still be ~50s
        assert time.time() - pipeline._pipeline_state_store.peek_last_user_speech_at() > 40, \
            "Kairos clock was incorrectly reset on re-entry without the flag"
    finally:
        asyncio.run(pipeline._pipeline_state_store.set_last_user_speech_at(orig_speech_at))


@pytest.mark.asyncio
async def test_kairos_does_not_fire_with_fresh_speech_at():
    """BUG-6: When _last_user_speech_at is current time, the KAIROS silence gate
    (now - _last_user_speech_at < KAIROS_SILENCE_THRESHOLD) must block firing."""
    import pipeline, time
    from unittest.mock import MagicMock

    orig_speech_at    = pipeline._pipeline_state_store.peek_last_user_speech_at()
    orig_kairos_at    = pipeline._pipeline_state_store.peek_last_kairos_at()
    orig_orchestrator = pipeline._brain_orchestrator

    await pipeline._session_store.open_session("p1", "Alice", "known", "face", now=time.time())
    await pipeline._pipeline_state_store.set_last_user_speech_at(pipeline.time.time())   # just spoke
    await pipeline._pipeline_state_store.set_last_kairos_at(0.0)                    # cooldown gate would pass
    pipeline._brain_orchestrator  = MagicMock()
    pipeline._brain_orchestrator.get_pending_question.return_value = {"id": "q1", "text": "Hi?"}

    try:
        result = await pipeline._kairos_tick("p1", "Alice", MagicMock())
    finally:
        await pipeline._pipeline_state_store.set_last_user_speech_at(orig_speech_at)
        await pipeline._pipeline_state_store.set_last_kairos_at(orig_kairos_at)
        pipeline._brain_orchestrator  = orig_orchestrator

    assert result is False   # silence gate blocked — user just spoke


@pytest.mark.asyncio
async def test_kairos_fires_after_silence_threshold():
    """BUG-6 regression: KAIROS must still fire (not return False early at silence gate)
    when the user has genuinely been silent longer than KAIROS_SILENCE_THRESHOLD."""
    import pipeline, time
    from unittest.mock import MagicMock, AsyncMock, patch

    orig_speech_at    = pipeline._pipeline_state_store.peek_last_user_speech_at()
    orig_kairos_at    = pipeline._pipeline_state_store.peek_last_kairos_at()
    orig_orchestrator = pipeline._brain_orchestrator

    await pipeline._session_store.open_session("p1", "Alice", "known", "face", now=time.time())
    await pipeline._pipeline_state_store.set_last_user_speech_at(0.0)   # long ago — silence gate opens
    await pipeline._pipeline_state_store.set_last_kairos_at(0.0)   # cooldown gate opens too
    mock_orch = MagicMock()
    mock_orch.get_pending_question.return_value = {"id": "q1", "text": "How are you?"}
    pipeline._brain_orchestrator = mock_orch

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
        await pipeline._pipeline_state_store.set_last_user_speech_at(orig_speech_at)
        await pipeline._pipeline_state_store.set_last_kairos_at(orig_kairos_at)
        pipeline._brain_orchestrator  = orig_orchestrator

    # The silence gate opened; KAIROS attempted to run (didn't return False early)
    mock_orch.get_pending_question.assert_called()


@pytest.mark.asyncio
async def test_kairos_tick_passes_memory_search_fn():
    """BUG-12: ask_stream inside _kairos_tick must receive memory_search_fn so that
    the search_memory tool is not silently skipped when the LLM calls it."""
    import pipeline, time
    from unittest.mock import MagicMock, AsyncMock, patch

    orig_speech_at    = pipeline._pipeline_state_store.peek_last_user_speech_at()
    orig_kairos_at    = pipeline._pipeline_state_store.peek_last_kairos_at()
    orig_orchestrator = pipeline._brain_orchestrator

    await pipeline._session_store.open_session("p1", "Alice", "known", "face", now=time.time())
    await pipeline._pipeline_state_store.set_last_user_speech_at(0.0)
    await pipeline._pipeline_state_store.set_last_kairos_at(0.0)
    mock_orch = MagicMock()
    mock_orch.get_pending_question.return_value = {"id": "q1", "text": "Do you exercise?"}
    pipeline._brain_orchestrator = mock_orch

    captured_kwargs = {}

    async def my_memory_search(query, pid):
        return "memory result"

    try:
        async def fake_speak_stream(gen, **kwargs):
            # drain the generator so _kairos_token_gen (and ask_stream) actually run
            async for _ in gen:
                pass

        with patch("pipeline.speak_stream", side_effect=fake_speak_stream), \
             patch("pipeline.ask_stream") as mock_ask, \
             patch("pipeline._set_state"):
            async def _fake_ask(*args, **kwargs):
                captured_kwargs.update(kwargs)
                return
                yield
            mock_ask.side_effect = _fake_ask

            await pipeline._kairos_tick("p1", "Alice", MagicMock(), memory_search_fn=my_memory_search)
    finally:
        await pipeline._pipeline_state_store.set_last_user_speech_at(orig_speech_at)
        await pipeline._pipeline_state_store.set_last_kairos_at(orig_kairos_at)
        pipeline._brain_orchestrator  = orig_orchestrator

    assert captured_kwargs.get("memory_search_fn") is my_memory_search, \
        "memory_search_fn not forwarded to ask_stream"


@pytest.mark.asyncio
async def test_kairos_tick_memory_search_fn_none_by_default():
    """BUG-12: _kairos_tick must still work when memory_search_fn is omitted (default None).
    Brain-driven KAIROS: when brain returns 'SILENT', tick returns False without error."""
    import pipeline, time
    from unittest.mock import MagicMock, AsyncMock, patch

    orig_speech_at    = pipeline._pipeline_state_store.peek_last_user_speech_at()
    orig_kairos_at    = pipeline._pipeline_state_store.peek_last_kairos_at()
    orig_orchestrator = pipeline._brain_orchestrator

    await pipeline._session_store.open_session("p1", "Alice", "known", "face", now=time.time())
    await pipeline._pipeline_state_store.set_last_user_speech_at(0.0)
    await pipeline._pipeline_state_store.set_last_kairos_at(0.0)
    mock_orch = MagicMock()
    mock_orch.get_pending_question.return_value = None
    pipeline._brain_orchestrator = mock_orch

    async def _silent_stream(*a, **kw):
        yield ("text", "SILENT")

    async def _noop_speak(sentences, **kw):
        async for _ in sentences:
            pass

    try:
        with patch("pipeline.ask_stream",   new=_silent_stream), \
             patch("pipeline.speak_stream", new=_noop_speak), \
             patch("pipeline._set_state"):
            # Must not raise even without memory_search_fn argument
            result = await pipeline._kairos_tick("p1", "Alice", MagicMock())
    finally:
        await pipeline._pipeline_state_store.set_last_user_speech_at(orig_speech_at)
        await pipeline._pipeline_state_store.set_last_kairos_at(orig_kairos_at)
        pipeline._brain_orchestrator  = orig_orchestrator

    assert result is False, "brain returning SILENT must cause tick to return False"


def test_silence_log_fires_once_per_streak(capsys):
    """'Silence detected' must log exactly once per continuous silence streak."""
    # Simulate the _in_silence flag logic directly — mirrors the production code path
    silent_streak  = 0
    _in_silence    = False
    log_count      = 0

    # Simulate 10 consecutive silent chunks after speech started
    for _ in range(10):
        if not _in_silence:
            _in_silence = True
            log_count += 1
            print("[Audio] Silence detected — waiting for end-of-turn...")
        silent_streak += 1

    assert log_count == 1, f"Expected 1 silence log, got {log_count}"


def test_silence_log_fires_once_per_separate_streak(capsys):
    """Two separate silence streaks (separated by speech) each log exactly once."""
    _in_silence = False
    log_lines   = []

    def _silence_chunk():
        nonlocal _in_silence
        if not _in_silence:
            _in_silence = True
            log_lines.append("silence")

    def _speech_chunk():
        nonlocal _in_silence
        _in_silence = False  # reset on resumed speech

    # First pause: 5 silent chunks
    for _ in range(5):
        _silence_chunk()

    # Speech resumes
    for _ in range(3):
        _speech_chunk()

    # Second pause: 8 silent chunks
    for _ in range(8):
        _silence_chunk()

    assert len(log_lines) == 2, \
        f"Expected 2 silence logs (one per streak), got {len(log_lines)}"


def test_kairos_tick_no_longer_guards_unknown():
    """kairos_tick's guard only checks stranger_, not 'unknown'."""
    import pathlib
    src = pathlib.Path("pipeline.py").read_text()
    # The old guard was: if person_id == "unknown" or person_id.startswith("stranger_")
    assert 'person_id == "unknown"' not in src, "person_id == 'unknown' guard must be removed"


def test_kairos_tick_signature_accepts_best_friend_id():
    import inspect, pipeline
    sig = inspect.signature(pipeline._kairos_tick)
    assert "best_friend_id" in sig.parameters, "_kairos_tick must accept best_friend_id"


def test_kairos_tick_passes_scene_block_and_vision_state_to_ask_stream():
    import inspect, pipeline
    src = inspect.getsource(pipeline._kairos_tick)
    assert "scene_block=kairos_scene_block" in src, "_kairos_tick must pass scene_block to ask_stream"
    assert "vision_state=kairos_vision_state" in src, "_kairos_tick must pass vision_state to ask_stream"


def test_kairos_call_site_passes_best_friend_id():
    import inspect, pipeline
    src = inspect.getsource(pipeline.run)
    assert "best_friend_id=_bf_id" in src, "call site must pass best_friend_id=_bf_id to _kairos_tick"


def test_silence_reset_threshold_is_9_chunks():
    """_speech_run reset threshold must be 9 (~288ms) to avoid micropause re-fires."""
    import pathlib
    src = (pathlib.Path(__file__).parent.parent / "core" / "audio.py").read_text()
    assert "_speech_run >= 9" in src, \
        "Silence log reset threshold must be _speech_run >= 9 (~288ms), not 3"


def test_kairos_tick_skipped_for_disputed_session():
    """Finding H — KAIROS must not initiate proactive speech during a disputed session.
    Session 73: guard now routes through ``_is_disputed()`` (the single-source-of-
    truth helper), not a raw string comparison."""
    import inspect, pipeline
    src = inspect.getsource(pipeline._kairos_tick)
    assert "_is_disputed(person_id)" in src, (
        "_kairos_tick must gate on _is_disputed(person_id) (Session 73 D4 invariant)"
    )
    # Structurally, the guard should return False (same pattern as the stranger guard)
    assert "return False" in src


def test_kairos_tick_skips_log_turn_when_disputed():
    """KAIROS proactive path must also skip log_turn on disputed sessions.
    Session 73 Critical #1: gate now routes through ``_is_disputed()`` — the
    previous raw ``!= "disputed"`` bypassed the single-source-of-truth AND
    slipped through the ``==``-only grep invariant."""
    import inspect, pipeline
    src = inspect.getsource(pipeline._kairos_tick)
    # Two separate _is_disputed checks in the function: one for the proactive
    # speech guard (early return), one for the log_turn gate. Both must exist.
    assert src.count("_is_disputed(person_id)") >= 2, (
        "_kairos_tick must route BOTH the proactive-speech guard AND the "
        "log_turn gate through _is_disputed — not raw string comparisons"
    )


def test_dream_loop_reconciles_voice_gallery_cache_after_out_of_process_delete():
    """Obs 1: source-inspection test — _dream_loop must re-fetch voice gallery sizes
    each cycle and reconcile divergent pids, so an out-of-process delete_person
    can't leave the cache pointing at a vanished mean embedding indefinitely."""
    import inspect, pipeline
    src = inspect.getsource(pipeline._dream_loop)
    assert "load_voice_profile_sizes" in src, (
        "_dream_loop must call db.load_voice_profile_sizes() each cycle to detect divergence"
    )
    assert "_voice_gallery_store.reconcile" in src, (
        "_dream_loop must delegate reconciliation to _voice_gallery_store.reconcile()"
    )
    assert "load_voice_profile_for" in src, (
        "Divergent pids must have their embeddings reloaded via load_voice_profile_for "
        "so voice_mod.identify() can't keep matching against a vanished mean"
    )
