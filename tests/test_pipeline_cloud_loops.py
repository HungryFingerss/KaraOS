"""test_pipeline_cloud_loops — cloud loops tests (split from test_pipeline.py, P1.A1 SP-1).

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


async def test_cloud_retry_loop_continues_after_recovery():
    """Loop must NOT exit after first recovery — it stays alive for subsequent outages."""
    import pipeline
    from pipeline import CloudState, _cloud_retry_loop

    orig_state      = pipeline._pipeline_state_store.peek_cloud_state()
    orig_recovered  = pipeline._pipeline_state_store.peek_cloud_recovered()
    orig_failed_at  = pipeline._pipeline_state_store.peek_cloud_failed_at()

    # ping sequence: recover on first call, then fail, then recover again
    ping_results = [True, False, True]
    ping_call_count = 0

    async def fake_ping():
        nonlocal ping_call_count
        result = ping_results[ping_call_count % len(ping_results)]
        ping_call_count += 1
        return result

    shutdown = asyncio.Event()  # not set — loop should run freely

    await pipeline._pipeline_state_store.transition_to_sick(_time_mod.time() - 10)
    _wiring._brain_orchestrator = None

    with patch("pipeline.CLOUD_RETRY_INTERVAL", 0.05), \
         patch("pipeline.ping_together", side_effect=fake_ping), \
         patch("pipeline._shutdown_event", shutdown):

        task = asyncio.create_task(_cloud_retry_loop())

        # First ping recovers → ONLINE → loop continues (must not exit)
        await asyncio.sleep(0.12)
        assert pipeline._pipeline_state_store.peek_cloud_state() == CloudState.ONLINE
        assert pipeline._pipeline_state_store.peek_cloud_recovered() is True
        assert not task.done(), "Loop must still be running after first recovery"

        # Simulate second outage
        await pipeline._pipeline_state_store.transition_to_sick(pipeline.time.time())

        # Second ping fails, third ping recovers
        await asyncio.sleep(0.15)
        assert pipeline._pipeline_state_store.peek_cloud_state() == CloudState.ONLINE
        assert pipeline._pipeline_state_store.peek_cloud_recovered() is True
        assert not task.done(), "Loop must still be running after second recovery"

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    await pipeline._pipeline_state_store.set_cloud_state(orig_state)
    await pipeline._pipeline_state_store.set_cloud_recovered(orig_recovered)
    await pipeline._pipeline_state_store.set_cloud_failed_at(orig_failed_at)
    _wiring._brain_orchestrator = None


async def test_cloud_retry_loop_skips_ping_when_online():
    """When ONLINE, loop must skip ping_together() and keep running."""
    import pipeline
    from pipeline import CloudState, _cloud_retry_loop

    orig_state     = pipeline._pipeline_state_store.peek_cloud_state()
    orig_recovered = pipeline._pipeline_state_store.peek_cloud_recovered()

    shutdown = asyncio.Event()  # not set

    await pipeline._pipeline_state_store.recover_online_no_flag()
    _wiring._brain_orchestrator = None

    ping_called = False

    async def fake_ping():
        nonlocal ping_called
        ping_called = True
        return True

    with patch("pipeline.CLOUD_RETRY_INTERVAL", 0.05), \
         patch("pipeline.ping_together", side_effect=fake_ping), \
         patch("pipeline._shutdown_event", shutdown):

        task = asyncio.create_task(_cloud_retry_loop())

        # Allow two full iterations — loop must NOT call ping while ONLINE
        await asyncio.sleep(0.13)
        assert not ping_called, "ping_together must not be called when ONLINE"
        assert not task.done(), "Loop must still be running while ONLINE"

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    await pipeline._pipeline_state_store.set_cloud_state(orig_state)
    await pipeline._pipeline_state_store.set_cloud_recovered(orig_recovered)


@pytest.mark.asyncio
async def test_autocompact_retries_on_transient_error():
    """BUG-11: A transient network/5xx error must trigger one retry with 2s backoff.
    On retry success the old turns must NOT be dropped — summary path completes."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch
    from core.brain import autocompact_history

    # Build a history that exceeds TOKEN_COMPACT_THRESHOLD so autocompact runs
    from core.brain import TOKEN_COMPACT_THRESHOLD, AUTOCOMPACT_KEEP_TURNS
    # Each message ~50 tokens; need enough to exceed threshold
    n_old = max(10, TOKEN_COMPACT_THRESHOLD // 50 + 1)
    word = "word " * 48
    history = []
    for _ in range(n_old):
        history.append({"role": "user",      "content": word})
        history.append({"role": "assistant",  "content": word})

    call_count = 0

    async def fake_post(url, json=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Connection reset")  # transient error on first call
        # Second call succeeds
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "• Old talk summary"}}]
        }
        return mock_resp

    with patch("core.brain._extract_http") as mock_client, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_client.post = fake_post
        result = await autocompact_history(history, "Alice")

    assert call_count == 2, "should have retried once"
    # Result must contain the summary block, not just the recent slice
    assert any("compacted" in m.get("content", "").lower() for m in result), \
        "old turns were dropped instead of summarised"


@pytest.mark.asyncio
async def test_autocompact_no_retry_on_4xx():
    """BUG-11: A non-retryable 4xx error (e.g. 401 Unauthorized) must NOT be retried —
    drop old turns immediately without a second API call."""
    from unittest.mock import MagicMock, patch, AsyncMock
    from core.brain import autocompact_history, TOKEN_COMPACT_THRESHOLD

    word = "word " * 48
    n_old = max(10, TOKEN_COMPACT_THRESHOLD // 50 + 1)
    history = []
    for _ in range(n_old):
        history.append({"role": "user",      "content": word})
        history.append({"role": "assistant",  "content": word})

    call_count = 0

    async def fake_post_401(url, json=None, **kwargs):
        nonlocal call_count
        call_count += 1
        exc = Exception("401 Unauthorized")
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        exc.response = mock_resp
        raise exc

    with patch("core.brain._extract_http") as mock_client, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_client.post = fake_post_401
        result = await autocompact_history(history, "Alice")

    assert call_count == 1, "should not have retried on 401"
    mock_sleep.assert_not_called()
    # Old turns dropped — result is just the recent slice (no summary block)
    assert not any("compacted" in m.get("content", "").lower() for m in result)


def test_pref_agent_ollama_error_log_includes_type():
    """PromptPrefAgent._call_ollama must log exception type in error message."""
    import inspect
    from core.brain_agent import PromptPrefAgent
    src = inspect.getsource(PromptPrefAgent._call_ollama)
    assert "type(e).__name__" in src, \
        "_call_ollama error log must include exception type"
    assert "no message" in src, \
        "_call_ollama error log must handle empty exception message"


def test_pref_agent_ollama_uses_explicit_timeout():
    """PromptPrefAgent._call_ollama must use explicit per-component httpx.Timeout."""
    import inspect
    from core.brain_agent import PromptPrefAgent
    src = inspect.getsource(PromptPrefAgent._call_ollama)
    assert "httpx.Timeout" in src, \
        "_call_ollama must use httpx.Timeout for explicit connect+read timeouts"
    assert "connect=" in src, \
        "_call_ollama must set explicit connect timeout to prevent cold-start overrun"


def test_pref_agent_ollama_has_num_predict():
    """PromptPrefAgent._call_ollama must set num_predict to cap response length."""
    import inspect
    from core.brain_agent import PromptPrefAgent
    src = inspect.getsource(PromptPrefAgent._call_ollama)
    assert "num_predict" in src, \
        "_call_ollama must set num_predict to limit Ollama response length and latency"


def test_cloud_recovery_does_not_trigger_tts():
    """Bug Y: when CloudState transitions SICK → ONLINE, the pipeline must
    NOT narrate it to the user. The previous behavior generated TTS like
    'My cloud connection just came back online, so everything should be smooth
    sailing now' (line 415 of 2026-04-22 log) — leaked internal infrastructure
    terminology. Source-inspection confirms the Ollama recovery-message
    generation was removed."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.run)
    # The flag still exists and gets cleared atomically via consume_cloud_recovered(),
    # but no Ollama call / speak() happens for it.
    assert "consume_cloud_recovered" in src, (
        "the flag-clear must remain so we don't re-trigger on next turn"
    )
    # The old recovery-generation pattern must be GONE.
    assert "I'm feeling much better now" not in src, (
        "Bug Y regression: old recovery TTS template still present"
    )
    assert "cloud connection just recovered" not in src, (
        "Bug Y regression: the system_note that leaked 'cloud connection' "
        "phrasing into LLM output is back"
    )
    # And a marker comment should explain WHY there's no announcement.
    assert "Bug Y" in src, (
        "the suppression rationale must be commented inline so future "
        "developers don't 'helpfully' add it back"
    )


def test_autocompact_runs_as_background_task_not_awaited():
    """Session 110 Fix 1 (CRITICAL latency): autocompact_history must
    fire as `asyncio.create_task(_compact_history_background(...))` —
    NOT be awaited in the critical path. The 2026-04-24 canary showed
    400-800ms blocking on every post-threshold turn, up to 3s on
    retry. Moving to background saves that latency on every turn at
    the cost of one-turn staleness (cloud's 128K context window
    easily handles uncompacted history in the meantime)."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    # The specific blocking pattern must be GONE. The old code was
    # `_conversation[person_id] = await autocompact_history(...)` — an
    # inline await that blocked the critical path. The new background
    # helper does call `await autocompact_history(...)` internally, but
    # NOT in the main conversation_turn flow — it's wrapped in
    # asyncio.create_task.
    assert "_conversation[person_id] = await autocompact_history(" not in src, (
        "the blocking assignment pattern must be gone — that was the "
        "exact call that blocked the brain response 400-800ms on every "
        "post-threshold turn"
    )
    # The background dispatch must be present.
    assert "_compact_history_background" in src, (
        "Fix 1 must wrap autocompact in _compact_history_background "
        "helper and fire it as asyncio.create_task"
    )
    assert "asyncio.create_task(_compact_history_background(" in src, (
        "background helper must be dispatched via asyncio.create_task "
        "(not awaited, not scheduled later)"
    )


def test_autocompact_stranger_guard_preserved_in_background_dispatch():
    """Session 110 Fix 1 guard: stranger sessions don't compact (the
    stranger path doesn't accumulate mature history). Refactor must
    preserve that guard so the background task isn't fired for
    stranger_* pids — would fail cleanly but it's pointless work."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    # The stranger-skip guard must still be present near the compact dispatch.
    idx = src.find("_compact_history_background")
    assert idx > 0
    # Back up to find the surrounding gate.
    window = src[max(0, idx - 1000):idx]
    assert "startswith(\"stranger_\")" in window, (
        "stranger guard must still gate autocompact dispatch — compaction "
        "on stranger sessions is pointless work"
    )


def test_autocompact_background_task_catches_exceptions():
    """Session 110 Fix 1 safety: _compact_history_background must
    wrap its body in try/except so a failed API call doesn't take
    down the session. Failures just leave history uncompacted for
    one more turn — NEXT turn retries."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    idx = src.find("_compact_history_background")
    end = src.find("asyncio.create_task", idx)
    helper_body = src[idx:end]
    assert "try:" in helper_body and "except Exception" in helper_body, (
        "background compaction must catch exceptions — unhandled errors "
        "in create_task's coroutine crash silently and can leak "
        "'Task exception was never retrieved' warnings"
    )
