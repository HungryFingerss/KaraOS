"""test_pipeline_tts_clean — tts clean tests (split from test_pipeline.py, P1.A1 SP-1).

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
import runtime.wiring as _wiring


def test_clean_for_tts_plain_text_unchanged():
    """Issue 5: Plain conversational text must pass through _clean_for_tts unchanged."""
    from core.audio import _clean_for_tts
    text = "Hello, how are you?"
    assert _clean_for_tts(text) == text


def test_clean_for_tts_strips_bold():
    """Issue 5: **bold** markers must be removed, leaving just the word."""
    from core.audio import _clean_for_tts
    assert _clean_for_tts("That is **really** important.") == "That is really important."


def test_clean_for_tts_strips_italic():
    """Issue 5: *italic* markers must be removed."""
    from core.audio import _clean_for_tts
    assert _clean_for_tts("She said *hello*.") == "She said hello."


def test_clean_for_tts_strips_triple_bold_italic():
    """Issue 5: ***bold-italic*** markers must be removed."""
    from core.audio import _clean_for_tts
    result = _clean_for_tts("***bold italic*** text")
    assert "***" not in result
    assert "bold italic" in result


def test_clean_for_tts_strips_code_backtick():
    """Issue 5: `code` backtick markers must be removed."""
    from core.audio import _clean_for_tts
    assert _clean_for_tts("Run the `pipeline.py` file.") == "Run the pipeline.py file."


def test_clean_for_tts_strips_hash_header():
    """Issue 5: ## header markers at line start must be removed."""
    from core.audio import _clean_for_tts
    result = _clean_for_tts("## Summary")
    assert "##" not in result
    assert "Summary" in result


def test_clean_for_tts_strips_bullet_list():
    """Issue 5: - bullet / • bullet markers at line start must be removed."""
    from core.audio import _clean_for_tts
    result = _clean_for_tts("- First item")
    assert result == "First item"


def test_clean_for_tts_converts_em_dash():
    """Issue 5: em dash must be replaced with a comma so Kokoro pauses naturally."""
    from core.audio import _clean_for_tts
    result = _clean_for_tts("It was great — really great.")
    assert "—" not in result
    assert "great" in result


def test_tts_bold_re_does_not_eat_multiline():
    """BUG-1: Multi-line bullet content must not be eaten by the bold regex.

    Before fix: re.DOTALL caused '* speed\n* accuracy' to match as one bold span,
    eating 'accuracy'. After fix: each line is independent; both words survive.
    """
    from core.audio import _clean_for_tts
    text = "* speed is fast\n* accuracy is high"
    result = _clean_for_tts(text)
    assert "speed" in result
    assert "accuracy" in result


def test_tts_bold_re_still_cleans_singleline():
    """BUG-1 regression: single-line bold must still be stripped after DOTALL removal."""
    from core.audio import _clean_for_tts
    assert _clean_for_tts("**bold**") == "bold"
    assert _clean_for_tts("~~strike~~") == "strike"


def test_clean_for_tts_strips_markdown_link():
    """BUG-14: [text](url) must be reduced to 'text' so TTS never reads a URL aloud."""
    from core.audio import _clean_for_tts
    result = _clean_for_tts("Check out [this article](https://example.com) for more.")
    assert "this article" in result
    assert "https" not in result
    assert "example.com" not in result
    assert "[" not in result
    assert "(" not in result


def test_clean_for_tts_strips_nested_bold_in_link():
    """BUG-14: [**bold**](url) must become 'bold' — link stripped first, then bold."""
    from core.audio import _clean_for_tts
    result = _clean_for_tts("[**click here**](https://x.com)")
    assert result == "click here"


def test_meta_commentary_pattern_matches_known_leak():
    """Bug H: the exact phrase observed in the 2026-04-20 live run must be caught."""
    from core.audio import _is_meta_commentary
    assert _is_meta_commentary("No function call is needed for this prompt.") is True


def test_meta_commentary_matches_as_an_ai_variants():
    """Bug H: 'as an AI', 'as an AI language model' leak patterns must match —
    these are the second-most-common source of meta-commentary leaks."""
    from core.audio import _is_meta_commentary
    assert _is_meta_commentary("As an AI, I don't have feelings.") is True
    assert _is_meta_commentary("As an AI language model, I cannot.") is True


def test_is_meta_commentary_catches_silent_token():
    """Bug X: bare 'SILENT' was spoken to the user (line 179 of 2026-04-22
    log). The LLM emitted the KAIROS protocol token as a regular response
    after garbled STT + a blocked search. _is_meta_commentary must catch it."""
    from core.audio import _is_meta_commentary
    assert _is_meta_commentary("SILENT") is True
    assert _is_meta_commentary("silent") is True   # lowercase too


def test_is_meta_commentary_catches_silent_with_punctuation():
    """Bug X: trailing punctuation must not bypass the filter."""
    from core.audio import _is_meta_commentary
    assert _is_meta_commentary("SILENT.") is True
    assert _is_meta_commentary("SILENT!") is True
    assert _is_meta_commentary("  SILENT  ") is True


def test_is_meta_commentary_catches_no_response_variants():
    """Bug X: NO_RESPONSE / [SILENT] / <silent> are equivalent protocol
    tokens that some models emit. All must be caught."""
    from core.audio import _is_meta_commentary
    assert _is_meta_commentary("NO_RESPONSE") is True
    assert _is_meta_commentary("NO RESPONSE") is True
    assert _is_meta_commentary("NO-RESPONSE") is True
    assert _is_meta_commentary("[SILENT]") is True
    assert _is_meta_commentary("<silent>") is True


def test_is_meta_commentary_does_NOT_catch_silent_in_sentence():
    """Bug X regression guard: anchored full-string match means natural
    sentences containing 'silent' as a word still pass through."""
    from core.audio import _is_meta_commentary
    assert _is_meta_commentary("The room is silent.") is False
    assert _is_meta_commentary("She gave me the silent treatment.") is False
    assert _is_meta_commentary("Please be silent for a moment.") is False


def test_clean_for_tts_drops_bare_silent_token():
    """Bug X end-to-end: _clean_for_tts must return empty for bare SILENT,
    so the sentence-level loop never synthesizes it. Same code path as Bug H."""
    from core.audio import _clean_for_tts
    assert _clean_for_tts("SILENT") == ""
    assert _clean_for_tts("SILENT.") == ""
    # Normal text passes.
    assert _clean_for_tts("That's nice.") == "That's nice."


def test_meta_commentary_does_not_false_positive_on_normal_speech():
    """Bug H: normal conversational speech that happens to mention AI or tools
    in a non-meta way must NOT match. Regression guard against over-filtering."""
    from core.audio import _is_meta_commentary
    assert _is_meta_commentary("I will tell you about cars.") is False
    assert _is_meta_commentary("The AI on the other team won.") is False
    assert _is_meta_commentary("That's a good tool for woodworking.") is False
    assert _is_meta_commentary("Function over form, always.") is False


def test_clean_for_tts_drops_meta_commentary_entirely():
    """Bug H: when the whole sentence is meta-commentary, _clean_for_tts returns
    empty string so the caller's sentence-level loop never synthesizes it."""
    from core.audio import _clean_for_tts
    assert _clean_for_tts("No function call is needed for this prompt.") == ""
    # And normal text is still preserved.
    assert _clean_for_tts("Hello, how are you?") == "Hello, how are you?"


def test_echo_skip_clamped_when_exceeds_preroll():
    """BUG-15: When echo_clear_until extends beyond the entire pre_roll buffer's
    time span, echo_skip must be clamped to len(pre_roll) rather than exceeding
    it — pre_roll[n:] where n > len(pre_roll) silently returns [] (all audio lost)."""
    chunk_dur = 0.032          # 32ms chunks
    pre_roll  = [None] * 10   # 10-chunk buffer (0.32s history)

    stream_open_time = 0.0
    chunk_idx        = 15      # speech detected at chunk 15 (0.48s)
    # echo window extends 2.0s past stream open — well beyond pre_roll span
    echo_clear_until = stream_open_time + 2.0

    pre_roll_start = stream_open_time + (chunk_idx - len(pre_roll)) * chunk_dur
    # Clamped (fixed) formula
    echo_skip = min(max(0, int((echo_clear_until - pre_roll_start) / chunk_dur)), len(pre_roll))

    assert echo_skip <= len(pre_roll), \
        f"echo_skip ({echo_skip}) exceeds len(pre_roll) ({len(pre_roll)}) — pre-roll would be silently dropped"
    # Unclamped value would exceed len(pre_roll)
    unclamped = max(0, int((echo_clear_until - pre_roll_start) / chunk_dur))
    assert unclamped > len(pre_roll), "test setup error: unclamped should exceed buffer length"


def test_echo_skip_normal_case_unchanged():
    """BUG-15 regression: when echo_skip < len(pre_roll), the clamp must NOT alter the value."""
    chunk_dur = 0.032
    pre_roll  = [None] * 31   # standard 31-chunk buffer

    stream_open_time = 0.0
    chunk_idx        = 50      # speech detected at 1.6s
    echo_clear_until = stream_open_time + 0.45  # normal 450ms echo window

    pre_roll_start = stream_open_time + (chunk_idx - len(pre_roll)) * chunk_dur
    unclamped = max(0, int((echo_clear_until - pre_roll_start) / chunk_dur))
    clamped   = min(unclamped, len(pre_roll))

    # In the normal case the clamp must be a no-op
    assert clamped == unclamped, \
        f"clamp changed normal-case value: {unclamped} → {clamped}"
    assert clamped < len(pre_roll), "test setup error: normal case should not hit the clamp"


@pytest.mark.asyncio
async def test_speak_stream_tts_end_time_set_after_play():
    """BUG-9: _tts_end_time must be updated inside the loop after each sd.wait(),
    not after a guessed asyncio.sleep(0.15). Under event-loop load the sleep can
    fire before the hardware buffer is flushed, clipping speech and mis-timestamping
    the echo-suppression window."""
    import sys
    from unittest.mock import patch, MagicMock

    play_calls = []

    def fake_play(pcm, samplerate=None):
        play_calls.append(pcm)

    def fake_wait():
        pass

    async def fake_sentences():
        yield "hello world"

    # The module-level stub installed at the top of this file masks the real
    # core.audio so speak_stream is a no-op AsyncMock and _tts_end_time is
    # never written.  Temporarily swap in the real module for the duration of
    # this test, then restore everything so all subsequent tests are unaffected.
    #
    # sounddevice is not installed in the test venv, so inject a minimal stub
    # for it too (real core.audio does `import sounddevice as sd` at module level).
    import types as _types
    _sd_fake = _types.ModuleType("sounddevice")
    _sd_fake.play = MagicMock()
    _sd_fake.wait = MagicMock()
    _sd_fake.stop = MagicMock()

    _stub = sys.modules.pop("core.audio", None)
    _sd_prior = sys.modules.get("sounddevice")
    sys.modules["sounddevice"] = _sd_fake
    try:
        import core.audio as audio_mod  # loads real module from disk using _sd_fake

        with patch.object(audio_mod.sd, "play", side_effect=fake_play), \
             patch.object(audio_mod.sd, "wait", side_effect=fake_wait), \
             patch.object(audio_mod.sd, "stop"), \
             patch.object(audio_mod, "_tts_kokoro", return_value=(b"\x00\x01" * 100, 22050)), \
             patch.object(audio_mod, "_tts_piper_en", return_value=(None, 0)):
            audio_mod._tts_end_time = 0.0
            before = __import__("time").time()
            await audio_mod.speak_stream(fake_sentences())
            after = __import__("time").time()

        assert audio_mod._tts_end_time >= before, "_tts_end_time not set during playback"
        assert audio_mod._tts_end_time <= after + 0.1, "_tts_end_time set too late"
        assert len(play_calls) == 1, "sd.play should have been called once"
    finally:
        if _stub is not None:
            sys.modules["core.audio"] = _stub
        elif "core.audio" in sys.modules:
            del sys.modules["core.audio"]
        if _sd_prior is not None:
            sys.modules["sounddevice"] = _sd_prior
        elif "sounddevice" in sys.modules:
            del sys.modules["sounddevice"]


@pytest.mark.asyncio
async def test_speak_stream_no_sleep_after_sentinel():
    """BUG-9: asyncio.sleep must NOT be called after the sentinel is received.
    The old 0.15s sleep was a time-based guess that could clip the last word under load."""
    import core.audio as audio_mod
    from unittest.mock import patch, MagicMock

    sleep_calls = []
    original_sleep = __import__("asyncio").sleep

    async def tracking_sleep(delay):
        sleep_calls.append(delay)
        await original_sleep(0)  # yield but don't actually wait

    async def fake_sentences():
        yield "test sentence"

    with patch("asyncio.sleep", side_effect=tracking_sleep), \
         patch.object(audio_mod.sd, "play"), \
         patch.object(audio_mod.sd, "wait"), \
         patch.object(audio_mod.sd, "stop"), \
         patch("core.audio._tts_kokoro", return_value=(b"\x00\x01" * 100, 22050)), \
         patch("core.audio._tts_piper_en", return_value=(None, 0)):
        await audio_mod.speak_stream(fake_sentences())

    # asyncio.sleep may be called by other internals (e.g. run_in_executor plumbing)
    # but must NOT be called with 0.15 (the old tail sleep)
    assert 0.15 not in sleep_calls, "asyncio.sleep(0.15) tail still present in _play_worker"


@pytest.mark.asyncio
async def test_synth_worker_sends_sentinel_on_exception():
    """BUG-10: If the sentences async generator raises mid-iteration, _synth_worker
    must still put None onto the queue so _play_worker can exit cleanly."""
    import asyncio
    import core.audio as audio_mod
    from unittest.mock import patch

    received = []

    async def raising_sentences():
        yield "first sentence"
        raise RuntimeError("stream dropped")

    # Capture what gets put on the queue
    original_speak_stream = audio_mod.speak_stream

    async def fake_sentences():
        async for s in raising_sentences():
            yield s

    with patch("core.audio._tts_kokoro", return_value=(b"\x00\x01" * 100, 22050)), \
         patch("core.audio._tts_piper_en", return_value=(None, 0)), \
         patch.object(audio_mod.sd, "play"), \
         patch.object(audio_mod.sd, "wait"), \
         patch.object(audio_mod.sd, "stop"):
        # speak_stream should complete (not hang) even when generator raises
        try:
            await asyncio.wait_for(audio_mod.speak_stream(raising_sentences()), timeout=5.0)
        except RuntimeError:
            pass  # exception from generator may propagate — that's OK
        except asyncio.TimeoutError:
            pytest.fail("speak_stream hung — sentinel was not sent after generator exception")


@pytest.mark.asyncio
async def test_synth_worker_normal_path_sentinel():
    """BUG-10 regression: sentinel must still be sent on normal loop completion
    after wrapping _synth_worker in try/finally."""
    import asyncio
    import core.audio as audio_mod
    from unittest.mock import patch

    async def normal_sentences():
        yield "sentence one"
        yield "sentence two"

    with patch("core.audio._tts_kokoro", return_value=(b"\x00\x01" * 100, 22050)), \
         patch("core.audio._tts_piper_en", return_value=(None, 0)), \
         patch.object(audio_mod.sd, "play"), \
         patch.object(audio_mod.sd, "wait"), \
         patch.object(audio_mod.sd, "stop"):
        # If sentinel is sent correctly, speak_stream will complete within timeout
        try:
            await asyncio.wait_for(audio_mod.speak_stream(normal_sentences()), timeout=5.0)
        except asyncio.TimeoutError:
            pytest.fail("speak_stream hung on normal path — sentinel not sent")


def test_stream_truncation_detection_in_source():
    """pipeline.py must contain stream truncation detection block.
    Session 68 (Bug D): the word-count split is now ≤ 2 (Case A full-replace)
    vs > 2 (Case B completion). Test updated from the original `<= 1` gate."""
    import inspect, pipeline
    src = inspect.getsource(pipeline)
    assert "Stream truncation" in src, \
        "pipeline must log stream truncation events"
    assert "len(_stream_words) <= 2" in src, \
        "pipeline must detect short streaming responses (≤2 words) as Case-A truncations"
    assert "_retry_resp" in src, \
        "pipeline must retry via Ollama when stream truncation is detected"


@pytest.mark.asyncio
async def test_stream_truncation_retry_replaces_fragment():
    """When streaming returns a name-only fragment, Ollama retry replaces it in history."""
    import pipeline
    from pipeline import conversation_turn, CloudState
    import time as _t

    await pipeline._session_store.open_session("p1", "Jagan", "known", "face", now=_t.time())

    orig_cloud    = pipeline._pipeline_state_store.peek_cloud_state()
    orig_brain    = pipeline._brain_orchestrator
    orig_lang     = pipeline._pipeline_state_store.peek_detected_lang()
    orig_sysname  = pipeline._pipeline_state_store.peek_active_system_name()
    orig_shutdown = _wiring._shutdown_event

    await pipeline._conversation_store.set_history("p1", [])
    await pipeline._pipeline_state_store.recover_online_no_flag()
    pipeline._per_person_agent_store.reset()
    _wiring._brain_orchestrator    = None
    await pipeline._pipeline_state_store.set_detected_lang("en")
    await pipeline._pipeline_state_store.set_active_system_name("Kara")
    _wiring._shutdown_event        = asyncio.Event()

    # Simulate stream that only yields "Jagan" (1 word — truncation scenario)
    async def fake_stream_truncated(*a, **kw):
        yield ("text", "Jagan")

    async def fake_speak_stream(sentences, **kw):
        async for _ in sentences:
            pass

    _ollama_response = "Photosynthesis is the process by which plants convert sunlight into energy."

    async def fake_speak(text, **kw):
        pass  # capture call without playing audio

    try:
        with patch("pipeline.ask_stream",      new=fake_stream_truncated), \
             patch("pipeline.speak_stream",    new=fake_speak_stream), \
             patch("pipeline.speak",           new=AsyncMock(side_effect=fake_speak)), \
             patch("pipeline._set_state"), \
             patch("pipeline.play_filler"), \
             patch("pipeline._ask_offline_safe", new=AsyncMock(return_value=_ollama_response)), \
             patch("pipeline.autocompact_history",
                   new=AsyncMock(side_effect=lambda h, *a, **kw: h)):
            await conversation_turn("explain photosynthesis", "p1", "Jagan", db=None)

        hist = pipeline._conversation_store.peek_history("p1")
        asst_msgs = [m for m in hist if m["role"] == "assistant"]
        assert len(asst_msgs) == 1
        # History must store the RETRY response, not the fragment "Jagan"
        assert asst_msgs[0]["content"] == _ollama_response, \
            f"Expected full retry response in history, got: {asst_msgs[0]['content']!r}"
    finally:
        await pipeline._pipeline_state_store.set_cloud_state(orig_cloud)
        _wiring._brain_orchestrator    = orig_brain
        await pipeline._pipeline_state_store.set_detected_lang(orig_lang)
        await pipeline._pipeline_state_store.set_active_system_name(orig_sysname)
        _wiring._shutdown_event        = orig_shutdown


@pytest.mark.asyncio
async def test_stream_truncation_skips_when_multi_word():
    """Multi-word streaming response must NOT trigger the truncation retry path."""
    import pipeline, time
    from pipeline import conversation_turn, CloudState

    await pipeline._session_store.open_session("p1", "Jagan", "known", "face", now=time.time())

    orig_cloud    = pipeline._pipeline_state_store.peek_cloud_state()
    orig_brain    = pipeline._brain_orchestrator
    orig_lang     = pipeline._pipeline_state_store.peek_detected_lang()
    orig_sysname  = pipeline._pipeline_state_store.peek_active_system_name()
    orig_shutdown = _wiring._shutdown_event

    await pipeline._conversation_store.set_history("p1", [])
    await pipeline._pipeline_state_store.recover_online_no_flag()
    pipeline._per_person_agent_store.reset()
    _wiring._brain_orchestrator    = None
    await pipeline._pipeline_state_store.set_detected_lang("en")
    await pipeline._pipeline_state_store.set_active_system_name("Kara")
    _wiring._shutdown_event        = asyncio.Event()

    _normal_response = "Photosynthesis is how plants make food from sunlight."
    _offline_called  = []

    async def fake_stream_full(*a, **kw):
        yield ("text", _normal_response)

    async def fake_speak_stream(sentences, **kw):
        async for _ in sentences:
            pass

    async def fake_offline(*a, **kw):
        _offline_called.append(True)
        return "fallback"

    try:
        with patch("pipeline.ask_stream",      new=fake_stream_full), \
             patch("pipeline.speak_stream",    new=fake_speak_stream), \
             patch("pipeline._set_state"), \
             patch("pipeline.play_filler"), \
             patch("pipeline._ask_offline_safe", new=AsyncMock(side_effect=fake_offline)), \
             patch("pipeline.autocompact_history",
                   new=AsyncMock(side_effect=lambda h, *a, **kw: h)):
            await conversation_turn("explain photosynthesis", "p1", "Jagan", db=None)

        # _ask_offline_safe should NOT have been called for truncation retry
        assert not _offline_called, "Truncation retry must not fire for normal multi-word response"
        hist = pipeline._conversation_store.peek_history("p1")
        asst = [m for m in hist if m["role"] == "assistant"]
        assert asst[0]["content"] == _normal_response
    finally:
        await pipeline._pipeline_state_store.set_cloud_state(orig_cloud)
        _wiring._brain_orchestrator    = orig_brain
        await pipeline._pipeline_state_store.set_detected_lang(orig_lang)
        await pipeline._pipeline_state_store.set_active_system_name(orig_sysname)
        _wiring._shutdown_event        = orig_shutdown


def test_stream_truncation_retry_checks_terminal_punctuation():
    """Bug 5 (2026-04-20 live run) + Obs 3 (post-review) + Bug D (split-retry):
    retry must only fire when the streamed response has no terminal punctuation
    AND the SSE stream reported a truncation-class finish_reason. 'Hello!' /
    'Hmm' with finish_reason='stop' must NOT trigger retry; only finish_reason
    in ('length', 'content_filter', None) does. Source-inspection test — the
    behavioral contract lives in the guard expression in conversation_turn."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    assert "_ends_terminal" in src, (
        "Stream truncation retry must check terminal punctuation to avoid "
        "retrying on legitimate short replies like 'Hello!'"
    )
    # And stop_audio() must fire before the Case-A retry speak() to cut the fragment's tail.
    assert "stop_audio()" in src, (
        "Short-retry path must stop_audio() before speak() to avoid double-speak"
    )
    # Obs 3: finish_reason is the primary authoritative signal.
    assert "_stream_finish_reason" in src, (
        "Retry gate must consult the SSE finish_reason captured from ask_stream"
    )
    assert '"length"' in src and '"content_filter"' in src, (
        "Truncation-class finish_reason values ('length', 'content_filter', None) "
        "must gate the retry; 'stop' must not trigger it"
    )


def test_stream_truncation_has_two_retry_paths():
    """Bug D: the retry logic must split on response shape — very short (≤2 words)
    uses full replacement, longer truncated responses use sentence completion.
    Source-inspection on conversation_turn."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    assert "Stream truncation (short)" in src, (
        "Case A (full-replace for ≤2-word truncation) marker missing"
    )
    assert "Stream truncation (tail)" in src, (
        "Case B (completion for mid-sentence truncation) marker missing — "
        "Bug D was that long responses truncated mid-sentence went unretried"
    )


def test_completion_prompt_forbids_repetition():
    """Bug D: the Case-B completion prompt must explicitly tell Ollama NOT to
    repeat what was already said. Without this, the user hears the original
    stream's tail spoken again on top of the completion — worse than silence."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    # Find the completion prompt text.
    idx = src.find("Complete ONLY the final sentence")
    assert idx > -1, "Case-B completion instruction missing"
    snippet = src[max(0, idx - 300):idx + 300]
    assert "do NOT repeat" in snippet or "do not repeat" in snippet.lower(), (
        "completion prompt must forbid repetition so the user doesn't hear "
        "the original fragment's tail spoken twice"
    )


def test_case_a_gate_requires_two_or_fewer_words():
    """Bug D: Case A (full-replace) fires only when len(_stream_words) ≤ 2.
    Three-word responses are long enough to attempt completion, not replacement."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    assert "len(_stream_words) <= 2" in src, (
        "Case A must use ≤ 2 words as the split — 1-word (previous gate) missed "
        "'It is' / 'I think' truncations that Bug D surfaced"
    )


def test_case_b_only_speaks_continuation_not_full_response():
    """Bug D: Case B must NOT call stop_audio() or re-speak the original text.
    The original audio already played; only the continuation is spoken.
    Anti-regression guard: if someone copies the Case-A shape into Case B,
    the user hears a double-speak disaster."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    idx_b = src.find("Stream truncation (tail)")
    assert idx_b > -1
    # Slice from the tail marker to the end of the except block.
    tail_block = src[idx_b:idx_b + 1500]
    # stop_audio() must NOT appear in the tail-retry branch (it's only for Case A).
    assert "stop_audio()" not in tail_block, (
        "Case B must not stop_audio() — original audio already played; calling "
        "stop_audio() here would be a no-op at best and a timing hazard if "
        "refactored. Keep the branch audio-passive."
    )
    # And the response must be EXTENDED, not replaced.
    assert "response.rstrip() + " in tail_block or "response.rstrip() +" in tail_block, (
        "Case B must append the continuation to response (not assign), so "
        "history records the full utterance"
    )
