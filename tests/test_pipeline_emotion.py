"""test_pipeline_emotion — emotion tests (split from test_pipeline.py, P1.A1 SP-1).

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


def test_emotion_agent_shared_pipeline_is_singleton():
    """_get_pipeline() must return the same object on repeated calls (singleton)."""
    import core.emotion as _em

    p1 = _em._get_pipeline()
    p2 = _em._get_pipeline()
    # Both calls must return the identical object (same reference).
    # If model failed to load, both return None — still consistent.
    assert p1 is p2, \
        "_get_pipeline() must return the same object each call (singleton)"
    # Flag must be set after first call
    assert _em._shared_pipeline_ready is True, \
        "_shared_pipeline_ready must be True after first call"


def test_emotion_agent_window_stores_timestamps():
    """process_turn() must store (label, score, timestamp) triples in the window."""
    import time
    from unittest.mock import patch
    import core.emotion as _em

    agent = _em.EmotionAgent()
    fake_result = [[{"label": "sadness", "score": 0.75}]]
    t_before = time.time()
    with patch.object(_em, "_get_pipeline", return_value=lambda text: fake_result):
        agent.process_turn("I am really feeling terrible today right now")
    t_after = time.time()

    assert len(agent._window) == 1
    entry = agent._window[0]
    assert len(entry) == 3, "Each window entry must be (label, score, timestamp)"
    label, score, ts = entry
    assert label == "sadness"
    assert t_before <= ts <= t_after, "Timestamp must be captured at inference time"


def test_emotion_agent_ttl_excludes_stale_entries():
    """get_dominant_emotion() must ignore entries older than EMOTION_WINDOW_TTL_SECS."""
    import time
    from core.emotion import EmotionAgent
    from core.config  import EMOTION_WINDOW_TTL_SECS

    agent = EmotionAgent()
    # Inject a stale entry (older than TTL) directly into the window
    stale_ts = time.time() - EMOTION_WINDOW_TTL_SECS - 10
    agent._window.append(("sadness", 0.90, stale_ts))

    label, score = agent.get_dominant_emotion()
    assert label is None, "Stale entry must be excluded; expected no dominant emotion"


def test_emotion_agent_ttl_keeps_recent_entries():
    """get_dominant_emotion() must include entries within EMOTION_WINDOW_TTL_SECS."""
    import time
    from core.emotion import EmotionAgent

    agent = EmotionAgent()
    recent_ts = time.time() - 10   # 10 seconds ago — well within 90s TTL
    agent._window.append(("sadness", 0.90, recent_ts))

    label, score = agent.get_dominant_emotion()
    assert label == "sadness", "Recent entry must be included in dominant emotion"


def test_emotion_window_size_is_5():
    """EMOTION_WINDOW must be 5 (upgraded from 3)."""
    from core.config import EMOTION_WINDOW
    assert EMOTION_WINDOW == 5, f"Expected EMOTION_WINDOW=5, got {EMOTION_WINDOW}"


def test_emotion_ttl_config_exists():
    """EMOTION_WINDOW_TTL_SECS must be defined in config and be 90 seconds."""
    from core.config import EMOTION_WINDOW_TTL_SECS
    assert EMOTION_WINDOW_TTL_SECS == 90, \
        f"Expected EMOTION_WINDOW_TTL_SECS=90, got {EMOTION_WINDOW_TTL_SECS}"


def test_emotion_text_gate_is_5_words():
    """process_turn() must skip texts with fewer than 5 words."""
    import inspect
    from core.emotion import EmotionAgent
    src = inspect.getsource(EmotionAgent.process_turn)
    assert "< 5" in src, "Text gate must require at least 5 words (upgraded from 3)"


def test_emotion_agent_created_per_person(tmp_path):
    """conversation_turn() must create a separate EmotionAgent for each person_id."""
    import asyncio, pipeline
    from unittest.mock import patch, AsyncMock, MagicMock
    from core.db import FaceDB

    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))
    db.add_person("p_alice", "Alice")
    db.add_person("p_bob",   "Bob")

    orig_cloud        = pipeline._pipeline_state_store.peek_cloud_state()
    try:
        asyncio.run(pipeline._conversation_store.set_history("p_alice", []))
        asyncio.run(pipeline._conversation_store.set_history("p_bob", []))
        pipeline._per_person_agent_store.reset()
        asyncio.run(pipeline._pipeline_state_store.transition_to_sick(pipeline.time.time()))  # use simple ask() path

        # Session 119 Path 1 calibration — the prior text "hello there
        # {Name}" tripped the user-to-user heuristic + classifier
        # silent-skip path (Bob saying "Bob" looks like vocative
        # address). The test's intent is per-person EmotionAgent
        # creation, not user-to-user routing — using neutral text
        # exercises the intended path. Also patch _classify_intent to
        # None so the silent-skip gate never fires regardless of text.
        async def _run():
            await pipeline._session_store.open_session("p_alice", "Alice", "known", "face", now=__import__("time").time())
            await pipeline._session_store.open_session("p_bob", "Bob", "known", "face", now=__import__("time").time())
            with patch("pipeline.ask", new_callable=AsyncMock,
                       return_value=("hello", [])):
                with patch("pipeline.speak", new=AsyncMock()):
                    with patch("runtime.wiring._brain_orchestrator", None):
                        with patch("core.brain._classify_intent",
                                   new_callable=AsyncMock, return_value=None):
                            await pipeline.conversation_turn(
                                "the weather is really pleasant today everyone agrees",
                                "p_alice", "Alice", db,
                            )
                            await pipeline.conversation_turn(
                                "i finished my homework before dinner this evening",
                                "p_bob",   "Bob",   db,
                            )

        asyncio.run(_run())
        assert pipeline._per_person_agent_store.peek_emotion_agent("p_alice") is not None, \
            "Alice must have her own EmotionAgent"
        assert pipeline._per_person_agent_store.peek_emotion_agent("p_bob") is not None, \
            "Bob must have his own EmotionAgent"
        assert pipeline._per_person_agent_store.peek_emotion_agent("p_alice") is not \
               pipeline._per_person_agent_store.peek_emotion_agent("p_bob"), \
            "Alice and Bob must have separate EmotionAgent instances"
    finally:
        asyncio.run(pipeline._pipeline_state_store.set_cloud_state(orig_cloud))
        db._conn.close()


def test_s111_emotion_agent_pops_on_fresh_session_open():
    """Session 111 Critical #5: `_open_session` must pop the cached
    EmotionAgent for a pid on every FRESH session open so the 3-turn
    rolling window can't carry prior-session emotions into a new
    session. Re-opens (idempotent path) don't pop — they're the same
    session continuing."""
    import asyncio as _aio, pipeline
    from core.emotion import EmotionAgent
    # Seed agent as if a prior session populated it.
    _aio.run(pipeline._per_person_agent_store.set_emotion_agent("jagan_001", EmotionAgent()))
    old_agent = pipeline._per_person_agent_store.peek_emotion_agent("jagan_001")
    try:
        pipeline._open_session(
            "jagan_001", "Jagan", "face", "best_friend",
        )
        # After fresh open: agent was popped; conversation_turn will
        # lazily recreate one on first emotion-detection call.
        assert pipeline._per_person_agent_store.peek_emotion_agent("jagan_001") is None, (
            "fresh session open must clear stale EmotionAgent — "
            "reviewer's Critical #5 reset invariant"
        )
    finally:
        pipeline._per_person_agent_store.reset()


async def test_s111_emotion_agent_survives_session_reopen():
    """Session 111 Critical #5 safety: if _open_session hits the idempotent
    re-open path (session already active), the EmotionAgent must NOT be
    popped — that would reset the rolling window mid-conversation on
    every voice-routing re-enter call."""
    import pipeline, time as _t
    from core.emotion import EmotionAgent
    # Seed the store so _open_session detects an existing session (re-open path).
    await pipeline._session_store.open_session(
        "jagan_001", "Jagan", "known", "face", now=_t.time())
    await pipeline._per_person_agent_store.set_emotion_agent("jagan_001", EmotionAgent())
    sticky_agent = pipeline._per_person_agent_store.peek_emotion_agent("jagan_001")
    try:
        # Re-open (idempotent) — agent must persist.
        pipeline._open_session(
            "jagan_001", "Jagan", "face", "best_friend",
        )
        await asyncio.sleep(0)
        assert pipeline._per_person_agent_store.peek_emotion_agent("jagan_001") is sticky_agent, (
            "re-open path must NOT clear the agent — only fresh opens do"
        )
    finally:
        await pipeline._per_person_agent_store.pop_emotion_agent("jagan_001")


def test_emotion_process_turn_runs_in_background():
    """Session 110 Fix 2 (HIGH latency): emotion `process_turn` now
    runs inside an asyncio.create_task instead of blocking the
    critical path on a 15-25ms executor call per turn. Context for
    THIS turn reads cached state (one-turn lag acceptable — emotion
    changes slowly)."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    # The awaited executor call must be GONE from the main flow.
    assert "await _loop.run_in_executor(None, _cur_agent.process_turn" not in src, (
        "emotion process_turn must not be awaited on the critical path"
    )
    assert "_emotion_process_background" in src, (
        "Fix 2 must wrap emotion work in a background helper"
    )
    assert "asyncio.create_task(" in src
    # Helper body should still call run_in_executor internally (the
    # HuggingFace work is sync CPU).
    idx = src.find("async def _emotion_process_background")
    end = src.find("asyncio.create_task(\n            _emotion_process_background", idx)
    helper = src[idx:end]
    assert "run_in_executor(None, _agent.process_turn" in helper, (
        "background helper must still offload the sync HuggingFace call "
        "to a thread via run_in_executor — the whole helper can't block "
        "the event loop"
    )
