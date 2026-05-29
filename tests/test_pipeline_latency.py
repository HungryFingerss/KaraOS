"""
tests/test_pipeline_latency.py — Wave 0 Item 2.

Guards the Session 110 invariant: autocompact_history and EmotionAgent.process_turn
are fire-and-forget background tasks (asyncio.create_task), NOT awaited in the
critical conversation path.

Design rules:
- time.perf_counter() for sub-ms resolution (Windows)
- asyncio_mode=auto (set in pytest.ini) — async tests run natively
- p95 threshold = 200ms for the latency regression test
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import asyncio
import time
import pytest
from unittest.mock import patch


# ─── Fast stubs ─────────────────────────────────────────────────────────────

async def _fast_ask_stream(*args, **kwargs):
    """Instant async generator — simulates LLM responding without delay."""
    yield "Hello"
    yield " world"


async def _slow_autocompact(history, person_name, **kwargs):
    """Simulates 300ms autocompact — must NOT block conversation_turn."""
    await asyncio.sleep(0.30)
    return history


def _slow_emotion_process_turn(text):
    """Simulates 500ms emotion processing — must NOT block conversation_turn."""
    time.sleep(0.50)


async def _noop_speak_stream(gen, **kwargs):
    """No-op speak_stream — causes empty-response fallback path in conversation_turn."""
    pass


async def _noop_speak(*args, **kwargs):
    pass


def _make_session(person_name: str = "Alice") -> dict:
    now = time.time()
    return {
        "person_name": person_name,
        "person_type": "known",
        "started_at": now,
        "last_face_seen": now,
        "last_spoke_at": now,
        "user_turns": 0,
        "engagement_gate_passed": True,
        "waiting_for_name": False,
        "voice_only_origin": False,
        "room_session_id": None,
    }


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def latency_pipeline_harness():
    import pipeline
    from pipeline import CloudState, PipelineState

    pid = "alice_001"
    session = _make_session("Alice")

    orig_brain_orchestrator = pipeline._brain_orchestrator
    orig_pss_snapshot = {
        "cloud_state": pipeline._pipeline_state_store.peek_cloud_state(),
        "pipeline_state": pipeline._pipeline_state_store.peek_pipeline_state(),
        "last_user_speech_at": pipeline._pipeline_state_store.peek_last_user_speech_at(),
        "active_room_session": pipeline._pipeline_state_store.peek_active_room_session(),
        "active_room_started_at": pipeline._pipeline_state_store.peek_active_room_started_at(),
        "active_room_participants": pipeline._pipeline_state_store.peek_active_room_participants(),
        "cloud_failed_at": pipeline._pipeline_state_store.peek_cloud_failed_at(),
        "cloud_monitor_task": pipeline._pipeline_state_store.peek_cloud_monitor_task(),
        "detected_lang": pipeline._pipeline_state_store.peek_detected_lang(),
        "active_system_name": pipeline._pipeline_state_store.peek_active_system_name(),
    }

    # Seed session via SessionStore (replaces legacy _active_sessions dict write)
    asyncio.run(pipeline._session_store.open_session(
        pid,
        session["person_name"],
        person_type=session["person_type"],
        session_type="face",
        now=time.time(),
    ))
    pipeline._conversation_store.reset()
    asyncio.run(pipeline._pipeline_state_store.recover_online_no_flag())
    asyncio.run(pipeline._pipeline_state_store.set_pipeline_state(PipelineState.WATCHING))
    pipeline._brain_orchestrator = None
    pipeline._per_person_agent_store.reset()
    asyncio.run(pipeline._pipeline_state_store.set_last_user_speech_at(time.time()))
    asyncio.run(pipeline._pipeline_state_store.set_active_room_session(None))
    asyncio.run(pipeline._pipeline_state_store.set_active_room_started_at(None))
    asyncio.run(pipeline._pipeline_state_store.set_active_room_participants(set()))
    asyncio.run(pipeline._pipeline_state_store.transition_to_sick(0.0))
    asyncio.run(pipeline._pipeline_state_store.recover_online_no_flag())
    asyncio.run(pipeline._pipeline_state_store.set_cloud_monitor_task(None))
    asyncio.run(pipeline._pipeline_state_store.set_detected_lang("en"))
    asyncio.run(pipeline._pipeline_state_store.set_active_system_name("Kara"))

    patches = [
        patch("pipeline.ask_stream", side_effect=_fast_ask_stream),
        patch("pipeline.autocompact_history", side_effect=_slow_autocompact),
        patch("pipeline.speak_stream", side_effect=_noop_speak_stream),
        patch("pipeline.speak", side_effect=_noop_speak),
        patch("pipeline.play_filler", return_value=None),
        patch("pipeline._set_state", return_value=None),
        patch("pipeline._get_best_friend_cached", return_value=None),
        patch("core.emotion.EmotionAgent.process_turn",
              side_effect=_slow_emotion_process_turn),
        patch("core.classifier_graph.LocalE5Embedder._load",
              side_effect=lambda self: pytest.fail(
                  "LocalE5Embedder._load was called — accidental model load in test")),
        patch("core.config.SHADOW_SAMPLE_ENABLED", False),
    ]

    for p in patches:
        p.start()

    yield pid, session

    for p in patches:
        p.stop()

    pipeline._session_store = __import__("core.session_state", fromlist=["SessionStore"]).SessionStore()  # fresh store
    pipeline._per_person_agent_store.reset()
    pipeline._brain_orchestrator = orig_brain_orchestrator

    asyncio.run(pipeline._pipeline_state_store.set_pipeline_state(orig_pss_snapshot["pipeline_state"]))
    asyncio.run(pipeline._pipeline_state_store.set_last_user_speech_at(orig_pss_snapshot["last_user_speech_at"]))
    asyncio.run(pipeline._pipeline_state_store.set_active_room_session(orig_pss_snapshot["active_room_session"]))
    asyncio.run(pipeline._pipeline_state_store.set_active_room_started_at(orig_pss_snapshot["active_room_started_at"]))
    asyncio.run(pipeline._pipeline_state_store.set_active_room_participants(orig_pss_snapshot["active_room_participants"]))
    asyncio.run(pipeline._pipeline_state_store.set_cloud_monitor_task(orig_pss_snapshot["cloud_monitor_task"]))
    asyncio.run(pipeline._pipeline_state_store.set_detected_lang(orig_pss_snapshot["detected_lang"]))
    asyncio.run(pipeline._pipeline_state_store.set_active_system_name(orig_pss_snapshot["active_system_name"]))


@pytest.fixture
def latency_pipeline_harness_with_long_history(latency_pipeline_harness):
    import pipeline

    pid, session = latency_pipeline_harness
    # 50 turns — enough to cross the compact gate threshold
    asyncio.run(pipeline._conversation_store.set_history(pid, [
        {"role": "user" if i % 2 == 0 else "assistant",
         "content": f"message {i}",
         "ts": time.time() - (50 - i)}
        for i in range(50)
    ]))
    yield pid, session


# ─── Tests ───────────────────────────────────────────────────────────────────

async def test_conversation_turn_latency_p95_no_serial_blocking(latency_pipeline_harness):
    """
    p95 over 20 turns must be < 200ms — guards against any new serial await
    being added to the critical path.
    """
    import pipeline

    pid, session = latency_pipeline_harness
    latencies = []

    for i in range(20):
        pipeline._emotion_agents = {}   # fresh EmotionAgent each turn
        t0 = time.perf_counter()
        await pipeline.conversation_turn(
            text=f"Hello turn {i}",
            person_id=pid,
            person_name=session["person_name"],
            db=None,
        )
        latencies.append(time.perf_counter() - t0)
        await asyncio.sleep(0)   # allow background tasks to schedule

    latencies.sort()
    p95_idx = int(len(latencies) * 0.95)
    p95 = latencies[p95_idx]

    assert p95 < 0.20, (
        f"p95 latency {p95 * 1000:.1f}ms exceeds 200ms threshold — "
        f"a serial blocking await may have been added to the critical path"
    )


async def test_conversation_turn_does_not_await_blocking_emotion(latency_pipeline_harness):
    """
    Single turn must complete < 250ms even though EmotionAgent.process_turn
    sleeps 500ms.  Proves emotion is backgrounded via asyncio.create_task.
    """
    import pipeline

    pid, session = latency_pipeline_harness
    pipeline._emotion_agents = {}   # ensure fresh EmotionAgent creation

    t0 = time.perf_counter()
    await pipeline.conversation_turn(
        text="Test emotion background",
        person_id=pid,
        person_name=session["person_name"],
        db=None,
    )
    elapsed = time.perf_counter() - t0

    assert elapsed < 0.25, (
        f"conversation_turn took {elapsed * 1000:.1f}ms — "
        f"EmotionAgent.process_turn (500ms) appears to be blocking the critical path"
    )


async def test_conversation_turn_does_not_await_autocompact(
        latency_pipeline_harness_with_long_history):
    """
    Single turn must complete < 200ms even though autocompact_history
    sleeps 300ms.  Proves autocompact is backgrounded via asyncio.create_task.
    """
    import pipeline

    pid, session = latency_pipeline_harness_with_long_history

    t0 = time.perf_counter()
    await pipeline.conversation_turn(
        text="Test autocompact background",
        person_id=pid,
        person_name=session["person_name"],
        db=None,
    )
    elapsed = time.perf_counter() - t0

    assert elapsed < 0.20, (
        f"conversation_turn took {elapsed * 1000:.1f}ms — "
        f"autocompact_history (300ms) appears to be blocking the critical path"
    )
