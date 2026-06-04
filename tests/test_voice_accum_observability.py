"""Spec 2 Phase A — voice-accumulation observability (A1-A4).

Phase A is observability ONLY — no behavior change to accumulation. It makes the
silent-failure paths LOG so the next instrumented canary shows exactly where the gallery
isn't filling; the actual accumulation fix is Phase B (separate handoff after the canary).

The two clock reads this deferral named were RESOLVED across #5
(presence_fabric_clock_migration_spec.md): the `time.monotonic() - peek_last_recognized_at`
read became single-clock once Slice A migrated the presence now-vars to monotonic
(PresenceSnapshot.last_recognized_at is monotonic-written, so mono - mono is consistent), and
the Path-A `face_age = now - ev.face_last_seen_ts` read was fixed in #5 Slice D — pipeline.py
`_voice_accum_allowed` now reads `time.monotonic()`, matching the now-monotonic
VoiceEvidence.face_last_seen_ts (§1.4/§3.D, the read-half of the deferred clock-fabric fix).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import asyncio
import contextlib
import inspect

import pytest


# ── A3 — fire-and-forget done-callback retrieves + LOGS the exception ─────────
# (previously a bare `add_done_callback(_voice_tasks.discard)` swallowed it silently)


def test_a3_callback_logs_exception_and_discards(capsys):
    """A3: a voice-accum task that RAISES must log `[Voice] accum task error` and be
    discarded from _voice_tasks — never silently swallowed, never crashing the caller."""
    import pipeline as _pl

    async def _boom():
        raise ValueError("accum boom")

    loop = asyncio.new_event_loop()
    try:
        t = loop.create_task(_boom())
        with contextlib.suppress(ValueError):
            loop.run_until_complete(t)
        _pl._voice_tasks.add(t)
        _pl._voice_accum_done_callback(t)  # must NOT raise
    finally:
        loop.close()

    out = capsys.readouterr().out
    assert "[Voice] accum task error: ValueError: accum boom" in out
    assert t not in _pl._voice_tasks


def test_a3_callback_clean_task_no_error_log_and_discards(capsys):
    """A3: a task that completes normally logs NO error and is still discarded."""
    import pipeline as _pl

    async def _ok():
        return 42

    loop = asyncio.new_event_loop()
    try:
        t = loop.create_task(_ok())
        loop.run_until_complete(t)
        _pl._voice_tasks.add(t)
        _pl._voice_accum_done_callback(t)
    finally:
        loop.close()

    out = capsys.readouterr().out
    assert "accum task error" not in out
    assert t not in _pl._voice_tasks


def test_a3_callback_cancelled_task_no_crash_and_discards(capsys):
    """A3: a cancelled task (task.exception() raises CancelledError) must not crash the
    callback and must be discarded — cancellation is not an error to log."""
    import pipeline as _pl

    async def _sleeper():
        await asyncio.sleep(60)

    loop = asyncio.new_event_loop()
    try:
        t = loop.create_task(_sleeper())
        loop.call_soon(t.cancel)
        with contextlib.suppress(asyncio.CancelledError):
            loop.run_until_complete(t)
        _pl._voice_tasks.add(t)
        _pl._voice_accum_done_callback(t)  # must NOT raise on CancelledError
    finally:
        loop.close()

    out = capsys.readouterr().out
    assert "accum task error" not in out
    assert t not in _pl._voice_tasks


def test_a3_call_site_uses_logging_callback_not_bare_discard():
    """A3 source: the fire-and-forget accumulation task (~pipeline.py:8519) must attach
    _voice_accum_done_callback (which retrieves the exception), NOT the legacy bare
    `add_done_callback(_voice_tasks.discard)` that swallowed exceptions silently."""
    import pipeline as _pl
    src = inspect.getsource(_pl)
    assert "_t.add_done_callback(_voice_accum_done_callback)" in src, (
        "accumulation task must use the logging done-callback"
    )
    assert "_t.add_done_callback(_voice_tasks.discard)" not in src, (
        "legacy bare-discard callback must be gone (it swallowed exceptions silently)"
    )


def test_a3_callback_retrieves_exception():
    """A3 AST: _voice_accum_done_callback must call `task.exception()` — retrieving the
    exception is the whole point of the change — and log it."""
    import pipeline as _pl
    fn_src = inspect.getsource(_pl._voice_accum_done_callback)
    tree = ast.parse(fn_src)
    calls_exception = any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "exception"
        for n in ast.walk(tree)
    )
    assert calls_exception, "_voice_accum_done_callback must call task.exception()"
    assert "accum task error" in fn_src, "callback must log the retrieved exception"


# ── A1 — embed→None logs a skip line (behavioral, real _accumulate_voice) ─────


@pytest.mark.asyncio
async def test_a1_embed_none_logs_skip(tmp_path, capsys):
    """A1: when voice_mod.embed returns None inside _accumulate_voice, the path must log
    `[Voice] accum skip {pid}: embed returned None` instead of returning silently — so the
    next canary shows the embed-failure as the reason the gallery didn't fill."""
    import numpy as np
    from unittest.mock import patch, AsyncMock
    from core.db import FaceDB
    import time as _t
    import pipeline as _pl

    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))
    pid = "stranger_a1none"
    db.add_stranger("visitor", person_id=pid)

    audio = np.zeros(32000, dtype=np.float32)  # 2.0s @ 16kHz — clears the duration gate
    await _pl._voice_gallery_store.pop_gallery(pid)
    # Engagement-gate open → bootstrap credits → Path C allows first-turn accumulation,
    # so execution reaches the embed call (mirrors test_accumulate_voice_updates_gallery_*).
    _pl._session_store._sessions.pop(pid, None)
    _pl._open_session(pid, "visitor", "voice",
                      person_type="stranger", engagement_gate_passed=True)
    await _pl._session_store.open_session(pid, "visitor", "stranger", "voice",
                                          now=_t.time(),
                                          bootstrap_credits=_pl.N_INITIAL_VOICE_BOOTSTRAP)
    try:
        with patch("pipeline.voice_mod.identify",
                   new=AsyncMock(return_value=(None, 0.0, True))), \
             patch("pipeline.voice_mod.embed", new=AsyncMock(return_value=None)):
            await _pl._accumulate_voice(pid, audio, db)
        out = capsys.readouterr().out
        assert f"[Voice] accum skip {pid}: embed returned None" in out, (
            f"embed→None must log a skip line; got stdout:\n{out}"
        )
        assert _pl._voice_gallery_store.peek_gallery(pid) is None, (
            "embed→None must NOT update the gallery"
        )
    finally:
        _pl._close_session(pid)
        db._conn.close()


# ── A2 + A4 — silent-path skip log + chosen-path log present (source guard) ────


def test_a2_logs_path_b_weak_self_match_skip():
    """A2: the Path-B `else: return` (self-match weak) must log a skip line, not return
    silently."""
    import pipeline as _pl
    src = inspect.getsource(_pl._accumulate_voice)
    assert "Path-B self-match weak" in src, (
        "_accumulate_voice must log the Path-B weak-self-match skip (A2)"
    )


def test_a4_logs_chosen_accumulation_path():
    """A4: _accumulate_voice must log the chosen accumulation path (face_witness /
    bootstrap) for the allowed case (refused is already logged separately)."""
    import pipeline as _pl
    src = inspect.getsource(_pl._accumulate_voice)
    assert "[Voice] accum path for" in src, (
        "_accumulate_voice must log the chosen accumulation path (A4)"
    )
