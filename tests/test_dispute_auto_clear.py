"""
P0.2 — prior_person_type fail-closed default (behavior test).

When report_identity_mismatch fires for a session that has NO person_type key,
prior_person_type must be set to "stranger" (fail-closed), not "known".

After P0.7.5 migration: _active_sessions dict replaced by SessionStore.
prior_person_type is captured by transition_to_disputed() which stores
s.prior_person_type = s.person_type at the moment of dispute flip.

BEFORE fix (P0.2): setdefault("prior_person_type", ... "known") → test FAILS
AFTER fix:  transition_to_disputed captures actual person_type → test PASSES
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock

# Stub core.voice and core.audio before importing pipeline to avoid the
# Windows torchaudio DLL crash (OSError 0xc0000139).
# P0.R6.Y D3 cascade: identify + diarize are async; stubs use AsyncMock.
if "core.voice" not in sys.modules:
    _voice_stub = types.ModuleType("core.voice")
    _voice_stub.load_speaker_embedder = MagicMock(return_value=None)
    _voice_stub.identify = AsyncMock(return_value=(None, 0.0, True))
    _voice_stub.diarize = AsyncMock(return_value=[])
    _voice_stub.get_diarize_stats = MagicMock(return_value={})
    sys.modules["core.voice"] = _voice_stub

if "core.audio" not in sys.modules:
    _audio_stub = types.ModuleType("core.audio")
    for _fn in [
        "record_until_silence", "transcribe", "speak", "speak_stream",
        "listen_and_transcribe", "preload_models", "stop_audio",
        "play_filler", "set_lip_active",
    ]:
        setattr(_audio_stub, _fn, MagicMock())
    sys.modules["core.audio"] = _audio_stub

import pipeline
from pipeline import _execute_tool


async def test_report_identity_mismatch_prior_type_defaults_to_stranger():
    """
    Session opened with person_type='stranger' (simulates the "no person_type
    key" edge case that used to default to 'known').
    report_identity_mismatch must write prior_person_type = "stranger".
    """
    await pipeline._session_store.open_session(
        "p1", "TestPerson", "stranger", "voice", now=1000.0
    )

    mock_db = MagicMock()
    prev_orch = pipeline._brain_orchestrator
    pipeline._brain_orchestrator = None

    try:
        sidecar = {
            "turn_intent":     "deny_identity",
            "extracted_value": None,
            "confidence":      0.92,
            "reasoning":       "user denies identity",
        }
        await _execute_tool(
            "report_identity_mismatch",
            {"reason": "test dispute"},
            "p1",
            "TestPerson",
            db=mock_db,
            user_text="I am not TestPerson",
            intent_sidecar=sidecar,
        )
        # Yield so create_task'd coroutines (transition_to_disputed,
        # set_cached_prefix) scheduled via asyncio.get_running_loop() run.
        await asyncio.sleep(0)
    finally:
        pipeline._brain_orchestrator = prev_orch

    snap = pipeline._session_store.peek_snapshot("p1")
    captured = snap.prior_person_type if snap is not None else None
    assert captured == "stranger", (
        f"prior_person_type must default to 'stranger' (fail-closed) when "
        f"person_type is absent, but got {captured!r}."
    )


async def test_report_identity_mismatch_prior_type_preserves_existing_value():
    """
    When person_type IS present (e.g. "known"), prior_person_type captures it.
    This is the normal path — the field is set from actual session data.
    """
    await pipeline._session_store.open_session(
        "p2", "KnownPerson", "known", "voice", now=1000.0
    )

    mock_db = MagicMock()
    prev_orch = pipeline._brain_orchestrator
    pipeline._brain_orchestrator = None

    try:
        sidecar = {
            "turn_intent":     "deny_identity",
            "extracted_value": None,
            "confidence":      0.95,
            "reasoning":       "user denies identity",
        }
        await _execute_tool(
            "report_identity_mismatch",
            {"reason": "test dispute"},
            "p2",
            "KnownPerson",
            db=mock_db,
            user_text="I am not KnownPerson",
            intent_sidecar=sidecar,
        )
        # Yield so create_task'd coroutines run.
        await asyncio.sleep(0)
    finally:
        pipeline._brain_orchestrator = prev_orch

    snap = pipeline._session_store.peek_snapshot("p2")
    captured = snap.prior_person_type if snap is not None else None
    assert captured == "known", (
        f"prior_person_type should preserve the actual person_type 'known', "
        f"but got {captured!r}."
    )
