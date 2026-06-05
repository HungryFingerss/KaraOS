"""test_pipeline_rooms_multiperson — rooms multiperson tests (split from test_pipeline.py, P1.A1 SP-1).

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
from tests._pipeline_helpers import (
    _s3b1_sess,
)


async def test_s112_room_session_minted_on_first_open_into_empty_room():
    """Session 112 Part 1: first _open_session into an empty store mints a new
    room_session_id of the shape `room_{timestamp}_{rand}`. Subsequent opens
    while the room is live inherit the same id (join, not mint)."""
    import pipeline
    orig_room = pipeline._pipeline_state_store.peek_active_room_session()
    orig_started = pipeline._pipeline_state_store.peek_active_room_started_at()
    orig_parts = pipeline._pipeline_state_store.peek_active_room_participants().copy()
    await pipeline._pipeline_state_store.set_active_room_session(None)
    await pipeline._pipeline_state_store.set_active_room_started_at(None)
    await pipeline._pipeline_state_store.set_active_room_participants(set())
    # Ensure these pids are not in the store (prior tests may have left them).
    await pipeline._session_store.close_session("jagan_001")
    await pipeline._session_store.close_session("lexi_xyz")
    try:
        pipeline._open_session("jagan_001", "Jagan", "face", "best_friend")
        assert pipeline._pipeline_state_store.peek_active_room_session() is not None, \
            "first open must mint a room_session_id"
        assert pipeline._pipeline_state_store.peek_active_room_session().startswith("room_"), \
            "room_session_id format must be `room_{ts}_{rand}`"
        minted_id = pipeline._pipeline_state_store.peek_active_room_session()

        await asyncio.sleep(0)  # let open_session create_task run
        _snap1 = pipeline._session_store.peek_snapshot("jagan_001")
        assert _snap1 is not None and _snap1.room_session_id == minted_id, \
            "session store must carry the active room_session_id"

        # Second open: joins the existing room, doesn't mint a new id.
        pipeline._open_session("lexi_xyz", "Lexi", "voice", "known")
        assert pipeline._pipeline_state_store.peek_active_room_session() == minted_id, \
            "second open must INHERIT the minted room_session_id, not mint again"
        await asyncio.sleep(0)
        _snap2 = pipeline._session_store.peek_snapshot("lexi_xyz")
        assert _snap2 is not None and _snap2.room_session_id == minted_id
    finally:
        await pipeline._pipeline_state_store.set_active_room_session(orig_room)
        await pipeline._pipeline_state_store.set_active_room_started_at(orig_started)
        await pipeline._pipeline_state_store.set_active_room_participants(orig_parts)
        await pipeline._session_store.close_session("jagan_001")
        await pipeline._session_store.close_session("lexi_xyz")


def test_s112_room_session_ends_when_last_person_leaves():
    """Session 112 Part 1: when `_close_session` empties the
    `_active_sessions` table, the module clears `_active_room_session`
    and fires the `_on_room_end` hook. A new _open_session after that
    mints a FRESH id (the next room, not a continuation)."""
    import pipeline
    asyncio.run(pipeline._pipeline_state_store.set_active_room_session(None))
    pipeline._per_person_agent_store.reset()
    pipeline._persons_in_frame = {}
    pipeline._session_store._sessions.clear()
    try:
        pipeline._open_session(
            "jagan_001", "Jagan", "face", "best_friend",
        )
        first_id = pipeline._pipeline_state_store.peek_active_room_session()
        assert first_id is not None

        # Last person leaves: room ends.
        pipeline._close_session("jagan_001")
        assert pipeline._pipeline_state_store.peek_active_room_session() is None, (
            "last _close_session must clear _active_room_session"
        )

        # Next fresh open mints a DIFFERENT room_session_id.
        pipeline._open_session(
            "lexi_xyz", "Lexi", "voice", "known",
        )
        assert pipeline._pipeline_state_store.peek_active_room_session() is not None
        assert pipeline._pipeline_state_store.peek_active_room_session() != first_id, (
            "next room must have a distinct room_session_id — a new "
            "room, not a resurrection of the last one"
        )
    finally:
        asyncio.run(pipeline._pipeline_state_store.set_active_room_session(None))
        pipeline._persons_in_frame = {}


async def test_s112_room_stays_live_when_one_of_many_leaves():
    """Session 112 Part 1: with 2+ people in the room, closing ONE session must NOT
    end the room — the remaining person's session keeps `_active_room_session` alive."""
    import pipeline
    orig_room = pipeline._pipeline_state_store.peek_active_room_session()
    orig_started = pipeline._pipeline_state_store.peek_active_room_started_at()
    orig_parts = pipeline._pipeline_state_store.peek_active_room_participants().copy()
    await pipeline._pipeline_state_store.set_active_room_session(None)
    await pipeline._pipeline_state_store.set_active_room_started_at(None)
    await pipeline._pipeline_state_store.set_active_room_participants(set())
    try:
        pipeline._open_session("jagan_001", "Jagan", "face", "best_friend")
        pipeline._open_session("lexi_xyz", "Lexi", "voice", "known")
        await asyncio.sleep(0)  # let both open_session tasks run
        room_id = pipeline._pipeline_state_store.peek_active_room_session()

        # Lexi leaves — Jagan still here.
        pipeline._close_session("lexi_xyz")
        await asyncio.sleep(0)  # let close_session task run

        assert pipeline._pipeline_state_store.peek_active_room_session() == room_id, \
            "room stays live while any person remains"
        assert pipeline._session_store.peek_snapshot("jagan_001") is not None
        assert pipeline._session_store.peek_snapshot("lexi_xyz") is None
    finally:
        await pipeline._pipeline_state_store.set_active_room_session(orig_room)
        await pipeline._pipeline_state_store.set_active_room_started_at(orig_started)
        await pipeline._pipeline_state_store.set_active_room_participants(orig_parts)


async def test_s112_persons_in_frame_pops_on_close_session():
    """Session 112 Part 3: `_close_session` must remove from
    `_presence_store` immediately instead of waiting for
    SCENE_STALE_SECS to age the entry out. The 30s lag window let
    scene blocks render people whose sessions had already closed."""
    import pipeline, time as _t
    await pipeline._pipeline_state_store.set_active_room_session(None)
    await pipeline._presence_store.upsert_face_recognition(
        "lexi_xyz", "Lexi", 0.9, _t.time()
    )
    try:
        assert "lexi_xyz" in pipeline._presence_store

        pipeline._close_session("lexi_xyz")
        await asyncio.sleep(0)  # flush create_task(_presence_store.remove)
        assert "lexi_xyz" not in pipeline._presence_store, (
            "Part 3: _presence_store must remove on session close, "
            "not wait for SCENE_STALE_SECS age-out"
        )
    finally:
        await pipeline._pipeline_state_store.set_active_room_session(None)


def test_s112_kairos_prefers_best_friend_in_multi_person_room():
    """Session 112 Part 2: room-aware speaker selection. When multiple
    sessions are active AND the best_friend is one of them, KAIROS
    fires for the best_friend — the natural engagement target — not
    the most-recent speaker. Most-recent-speaker logic was wrong in
    multi-person rooms where Jagan (owner) was the listener while a
    visitor spoke."""
    import pipeline, time as _t, asyncio as _aio
    now = _t.time()
    pipeline._session_store._sessions.clear()
    _aio.run(pipeline._session_store.open_session("jagan_001", "Jagan", "best_friend", "face", now=now))
    _aio.run(pipeline._session_store.open_session("lexi_xyz", "Lexi", "known", "voice", now=now))
    try:
        pid = pipeline._kairos_preferred_speaker("jagan_001")
        assert pid == "jagan_001", (
            "best_friend must win over most-recent speaker in room"
        )
    finally:
        pipeline._session_store._sessions.clear()


def test_s112_kairos_falls_back_to_longest_silence_without_best_friend():
    """Session 112 Part 2: when no best_friend is in the room, pick
    the pid with the LONGEST individual silence — not the most-recent
    speaker. The most-recent speaker just finished; they're least
    likely to welcome a proactive interrupt. Quietest person is most
    likely to engage."""
    import pipeline, time as _t, asyncio as _aio
    now = _t.time()
    pipeline._session_store._sessions.clear()
    _aio.run(pipeline._session_store.open_session("lexi_xyz", "Lexi", "known", "voice", now=now))
    _aio.run(pipeline._session_store.open_session("kara_def", "Kara", "known", "face", now=now - 180))
    _aio.run(pipeline._session_store.open_session("ravi_ghi", "Ravi", "known", "face", now=now - 90))
    try:
        # best_friend is 'jagan_001' but NOT in store — fallback path.
        pid = pipeline._kairos_preferred_speaker("jagan_001")
        assert pid == "kara_def", (
            "longest-silence (180s) must win over most-recent (0s) "
            "and medium (90s) in the absent-best_friend fallback"
        )
    finally:
        pipeline._session_store._sessions.clear()


def test_s112_kairos_preferred_speaker_single_session_returns_only_pid():
    """Session 112 Part 2: single-session room is a no-choice case —
    return the one active pid regardless of best_friend status or
    silence. Guards the trivial path so the multi-session logic doesn't
    accidentally break single-person behavior."""
    import pipeline, time as _t, asyncio as _aio
    now = _t.time()
    pipeline._session_store._sessions.clear()  # clear any leftover sessions from prior test
    _aio.run(pipeline._session_store.open_session("lexi_xyz", "Lexi", "known", "voice", now=now))
    try:
        assert pipeline._kairos_preferred_speaker("jagan_001") == "lexi_xyz"
        assert pipeline._kairos_preferred_speaker(None) == "lexi_xyz"
    finally:
        pipeline._session_store._sessions.clear()


def test_s112_kuzu_audit_documented_not_v3_bumped():
    """Session 112 Part 4 audit + P0.S7.D-B reversal — historical trail
    must survive in-source so future readers see the full reasoning
    arc: S112 deferred v3, P0.S7.2 κ ship falsified the deferral
    premise, P0.S7.D-B shipped v3.

    Originally a no-v3-bump regression guard; after D-B (2026-05-19)
    repurposed to assert (a) the S112 audit reasoning STILL appears
    in-source (historical trail preserved) AND (b) the D-B reversal
    narrative is documented alongside it so the chain of decisions
    is legible. A future maintainer reading the find_shared_entities
    docstring sees BOTH the original deferral AND the reversal.
    """
    import inspect
    from core.brain_agent import GraphDB
    src = inspect.getsource(GraphDB.find_shared_entities)
    # Historical S112 reasoning preserved.
    assert "Session 112 Part 4" in src, (
        "S112 Part 4 audit reasoning must remain in-source so the "
        "deferral-then-reversal arc is legible to future readers"
    )
    # P0.S7.D-B reversal documented in the same docstring.
    assert "P0.S7.D-B" in src, (
        "P0.S7.D-B reversal narrative must be documented alongside "
        "the S112 deferral so the chain of decisions is legible"
    )
    assert "falsified" in src.lower() or "load-bearing" in src.lower(), (
        "D-B narrative must name the deferral-premise falsification "
        "(or the load-bearing framing) explicitly"
    )


def test_s113_address_decision_block_renders_when_multi_session_and_flag_on():
    """Session 113 Part 1 — `_build_system_prompt` emits the
    <<<ADDRESS DECISION>>> block only when BOTH the config flag is on
    AND there are ≥2 active sessions. Format instructions + positive
    "[addressing:current]" default + when-to-override examples must be
    present so the LLM learns the marker contract."""
    import inspect
    from core.brain import _build_system_prompt
    src = inspect.getsource(_build_system_prompt)
    assert "<<<ADDRESS DECISION>>>" in src, "block header missing"
    assert "ADDRESS_DECISION_BLOCK_ENABLED" in src, "flag-gate missing"
    assert "active_session_count" in src, (
        "multi-session gate must read active_session_count from vision_state"
    )
    # Format instructions: both variants must be documented.
    assert "[addressing:current]" in src, "current-speaker default format missing"
    assert "[addressing:" in src and "Name" in src, "named-speaker format missing"


def test_s113_resolve_addressed_to_matches_active_session_name():
    """Session 113 Part 1 — `_resolve_addressed_to` returns the active
    session's canonical person_name when the marker value matches
    (case-insensitively). Validates the happy-path lookup used when
    the LLM's [addressing:Lexi] marker should land Lexi as the
    history.addressed_to field."""
    import types
    from pipeline import _resolve_addressed_to
    active = [
        types.SimpleNamespace(person_name="Jagan"),
        types.SimpleNamespace(person_name="Lexi"),
    ]
    # Exact case match.
    assert _resolve_addressed_to("Lexi", active, "Jagan") == "Lexi"
    # Case-insensitive match — Whisper + LLM combine to produce varied
    # casing; resolution must tolerate "lexi" / "LEXI" / "Lexi ".
    assert _resolve_addressed_to("lexi", active, "Jagan") == "Lexi"
    assert _resolve_addressed_to("  LEXI  ", active, "Jagan") == "Lexi"


def test_s113_resolve_addressed_to_unknown_name_falls_back(capsys):
    """Session 113 Part 1 — if the marker names someone NOT in
    _active_sessions (hallucinated name, spelling drift, expired
    session), fall back to effective_name (current speaker) and emit a
    warning log. The safety property: marker never silently corrupts
    history with an unverifiable name."""
    import types
    from pipeline import _resolve_addressed_to
    active = [
        types.SimpleNamespace(person_name="Jagan"),
        types.SimpleNamespace(person_name="Lexi"),
    ]
    out = _resolve_addressed_to("Bogus", active, "Jagan")
    assert out == "Jagan", "unknown name must fall back to current speaker"
    captured = capsys.readouterr().out
    assert "ADDRESS DECISION" in captured and "Bogus" in captured, (
        "fallback must log a diagnostic line naming the bogus value"
    )


def test_s113_1_resolve_addressed_to_emits_observability_log(capsys):
    """Session 113.1 — every call to `_resolve_addressed_to` must emit
    a `[Pipeline] Turn addressed: X (...)` log line so canary analysis
    can distinguish LLM-driven address decisions from default fallback.
    Reviewer's post-canary observation: mis-addressed responses are
    ambiguous without ground-truth on whether the LLM emitted a marker
    at all. Tests all 3 branches:
      - LLM-driven (matched name): log shows "(LLM: '[addressing:Lexi]')"
      - Default (no marker / 'current'): log shows "(default)"
      - Fallback (unknown name): log shows "(fallback)"
    """
    import types
    from pipeline import _resolve_addressed_to
    active = [
        types.SimpleNamespace(person_name="Jagan"),
        types.SimpleNamespace(person_name="Lexi"),
    ]
    # Case 1: LLM decision, matched name.
    _resolve_addressed_to("Lexi", active, "Jagan")
    out1 = capsys.readouterr().out
    assert "Turn addressed: Lexi" in out1 and "LLM:" in out1, (
        f"LLM-driven path must log decision + marker; got {out1!r}"
    )
    # Case 2: default (None marker).
    _resolve_addressed_to(None, active, "Jagan")
    out2 = capsys.readouterr().out
    assert "Turn addressed: Jagan" in out2 and "default" in out2, (
        f"default path must log current speaker + 'default'; got {out2!r}"
    )
    # Case 3: unknown name → fallback.
    _resolve_addressed_to("Bogus", active, "Jagan")
    out3 = capsys.readouterr().out
    assert "Turn addressed: Jagan" in out3 and "fallback" in out3, (
        f"fallback path must log the resolved current speaker + 'fallback'; got {out3!r}"
    )


def test_s113_resolve_addressed_to_current_and_none_use_effective_name():
    """Session 113 Part 1 — 'current' and None / empty marker values
    are the no-override path: use effective_name. This preserves
    Session 111's behavior for every turn where the brain did NOT
    emit an override marker (default case)."""
    import types
    from pipeline import _resolve_addressed_to
    active = [
        types.SimpleNamespace(person_name="Jagan"),
        types.SimpleNamespace(person_name="Lexi"),
    ]
    assert _resolve_addressed_to(None,        active, "Jagan") == "Jagan"
    assert _resolve_addressed_to("",          active, "Jagan") == "Jagan"
    assert _resolve_addressed_to("current",   active, "Jagan") == "Jagan"
    assert _resolve_addressed_to("  Current", active, "Jagan") == "Jagan"


def test_s113_token_gen_marker_parse_source_guards_strip_and_capture():
    """Session 113 Part 1 — source-inspection guard on conversation_turn
    that the marker parser in _token_gen (a) uses a regex shaped
    `[addressing:...]` that captures the name between colons and `]`,
    (b) writes to `_addr_override[0]`, (c) flushes buffered content
    on fall-through, and (d) handles the end-of-stream flush edge case
    so unclosed markers can't swallow tokens."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    assert r"[addressing:" in src and "re.match" in src, (
        "regex-based marker parse expected in _token_gen"
    )
    assert "_addr_override[0] = _m.group(1)" in src, (
        "parser must capture the marker name into the closure slot"
    )
    # End-of-stream flush: buffer that wasn't classified must flush.
    assert "_prefix_buf" in src and "not _marker_done[0]" in src, (
        "end-of-stream flush path must read _marker_done + _prefix_buf"
    )
    # Resolution site must call the helper.
    assert "_resolve_addressed_to(" in src, (
        "conversation_turn must delegate resolution to the testable helper"
    )


def test_s113_address_decision_block_omitted_for_single_session():
    """Session 113 Part 1 — single-session contexts MUST NOT see the
    ADDRESS DECISION block in the rendered prompt (active_session_count
    is 1 → gate fails → block absent). Preserves legacy one-speaker
    behavior: brain just responds, no marker protocol. Rendered-prompt
    behavioral test over source-inspection since source-inspection can't
    distinguish 'present but gated off' from 'present and active'."""
    from core.brain import _build_system_prompt
    prompt = _build_system_prompt(
        person_name="Jagan",
        vision_state={"active_session_count": 1, "people_visible": ["Jagan"]},
    )
    assert "<<<ADDRESS DECISION>>>" not in prompt, (
        "single-session prompt must not carry the ADDRESS DECISION block"
    )
    # Sanity: block DOES render when count ≥ 2 (guards the negative above).
    prompt_multi = _build_system_prompt(
        person_name="Jagan",
        vision_state={"active_session_count": 2, "people_visible": ["Jagan", "Lexi"]},
    )
    assert "<<<ADDRESS DECISION>>>" in prompt_multi, (
        "multi-session prompt must carry the ADDRESS DECISION block (gate positive)"
    )


def test_s113_choose_greeting_order_single_name_skips_llm(monkeypatch):
    """Session 113 Part 2 — single-name input MUST return immediately
    without an LLM call. The LLM decision only matters when there are
    multiple people to order; a single-person greeting has no ordering
    to consider. Fast path must be zero-cost."""
    import asyncio
    from core import brain as brain_mod

    calls = {"count": 0}
    async def _boom(*args, **kwargs):
        calls["count"] += 1
        raise AssertionError("LLM must NOT be called for single-name input")

    monkeypatch.setattr(brain_mod._chat_http, "post", _boom)

    out = asyncio.run(brain_mod.choose_greeting_order(["Jagan"], timeout=1.0))
    assert out == ["Jagan"], "single-name input must pass through verbatim"
    assert calls["count"] == 0, "no LLM call expected for single-name input"
    # Empty input also short-circuits.
    out_empty = asyncio.run(brain_mod.choose_greeting_order([], timeout=1.0))
    assert out_empty == []
    assert calls["count"] == 0


def test_s113_choose_greeting_order_reorders_on_llm_success(monkeypatch):
    """Session 113 Part 2 — with ≥2 names, the LLM's comma-separated
    response drives the returned order. Parser is forgiving on case,
    whitespace, and trailing punctuation so a real model response
    ("Bob, alice.  CHARLIE!") still maps to the canonical casing."""
    import asyncio
    from core import brain as brain_mod

    class _Resp:
        status_code = 200
        def raise_for_status(self): return None
        def json(self):
            return {"choices": [{"message": {"content": "Bob, alice.  CHARLIE!"}}]}

    async def _fake_post(*args, **kwargs):
        return _Resp()

    monkeypatch.setattr(brain_mod, "CHAT_API_KEY", "test-key")
    monkeypatch.setattr(brain_mod._chat_http, "post", _fake_post)

    out = asyncio.run(brain_mod.choose_greeting_order(
        ["Alice", "Bob", "Charlie"], timeout=1.0,
    ))
    assert out == ["Bob", "Alice", "Charlie"], (
        f"LLM response must drive order; got {out!r}"
    )


def test_s113_choose_greeting_order_falls_back_on_llm_timeout(monkeypatch):
    """Session 113 Part 2 — any LLM failure (timeout / 5xx / malformed
    response) must return the INPUT order unchanged. Batched greeting
    is strictly-upgrade: same outcome as the pre-S113 detection-order
    path on failure, improved outcome on success. Callers never have
    to branch on error state."""
    import asyncio
    from core import brain as brain_mod

    async def _timeout_post(*args, **kwargs):
        raise TimeoutError("simulated LLM timeout")

    monkeypatch.setattr(brain_mod, "CHAT_API_KEY", "test-key")
    monkeypatch.setattr(brain_mod._chat_http, "post", _timeout_post)

    out = asyncio.run(brain_mod.choose_greeting_order(
        ["Alice", "Bob", "Charlie"], timeout=1.0,
    ))
    assert out == ["Alice", "Bob", "Charlie"], (
        "timeout must fall back to input order, not partial/empty result"
    )


def test_s113_choose_greeting_order_appends_missing_names_on_partial_llm(monkeypatch):
    """Session 113 Part 2 — if the LLM drops a name from its response
    (hallucinates a different name, returns only part of the list, etc.),
    the missing name must be appended in its original order so no one
    is silently skipped. Order-sorting is BEST EFFORT; completeness is
    the hard invariant."""
    import asyncio
    from core import brain as brain_mod

    class _Resp:
        status_code = 200
        def raise_for_status(self): return None
        def json(self):
            # LLM returned only 2 of 3 + a hallucinated name "Dave".
            return {"choices": [{"message": {"content": "Charlie, Dave, Alice"}}]}

    async def _fake_post(*args, **kwargs):
        return _Resp()

    monkeypatch.setattr(brain_mod, "CHAT_API_KEY", "test-key")
    monkeypatch.setattr(brain_mod._chat_http, "post", _fake_post)

    out = asyncio.run(brain_mod.choose_greeting_order(
        ["Alice", "Bob", "Charlie"], timeout=1.0,
    ))
    # LLM put Charlie first, Alice second; Dave is dropped (not in input);
    # Bob was dropped by LLM → must appear at the end in input order.
    assert out == ["Charlie", "Alice", "Bob"], (
        f"partial response must include every input name; got {out!r}"
    )


def test_s113_on_room_end_fires_exactly_once_when_last_person_leaves():
    """Session 113 Part 3 — Session 112 established `_on_room_end` as
    the room-level synthesis hook fired via `asyncio.create_task` when
    the last person leaves. Invariant: hook fires EXACTLY ONCE per room
    session. Part of a multi-person room's pids closing keeps the room
    alive; only the LAST close fires the hook. 3B wires real synthesis
    here — the count invariant is the contract 3B will build on."""
    import pipeline, time
    now = time.time()
    fires: list[str] = []
    original = pipeline._on_room_end

    async def _spy(room_session_id, *args, **kwargs):
        fires.append(room_session_id)

    pipeline._on_room_end = _spy
    try:
        asyncio.run(pipeline._pipeline_state_store.set_active_room_session("r_abc"))
        pipeline._face_db_ref = None

        import asyncio as _aio
        async def _drive():
            pipeline._close_session("a_1")         # store empty → fires room end
            pipeline._close_session("b_1")         # _active_room_session already None → no second fire
            # Let fire-and-forget task actually run.
            await _aio.sleep(0)
            await _aio.sleep(0)

        _aio.run(_drive())

        assert fires == ["r_abc"], (
            f"_on_room_end must fire exactly once on last-person close; got {fires!r}"
        )
        assert pipeline._pipeline_state_store.peek_active_room_session() is None, (
            "room session pointer must clear once the room empties"
        )
    finally:
        pipeline._on_room_end = original
        asyncio.run(pipeline._pipeline_state_store.set_active_room_session(None))


def test_s113_on_room_end_does_not_fire_while_other_sessions_live():
    """Session 113 Part 3 — complements the `fires_exactly_once` test:
    closing ONE of multiple sessions in a room must NOT fire the hook.
    The hook's job is room-lifecycle termination, not per-person close.
    Guards against a future refactor that accidentally fires per-close."""
    import pipeline, time
    now = time.time()
    fires: list[str] = []
    original = pipeline._on_room_end

    async def _spy(room_session_id, *args, **kwargs):
        fires.append(room_session_id)

    pipeline._on_room_end = _spy
    try:
        import asyncio as _aio
        pipeline._session_store._sessions.clear()
        _aio.run(pipeline._session_store.open_session("a_1", "Alice", "known", "face", now=now))
        _aio.run(pipeline._session_store.open_session("b_1", "Bob", "known", "face", now=now))
        asyncio.run(pipeline._pipeline_state_store.set_active_room_session("r_xyz"))
        pipeline._face_db_ref = None
        async def _drive():
            pipeline._close_session("a_1")   # Bob still in store → no hook
            await _aio.sleep(0)

        _aio.run(_drive())

        assert fires == [], (
            f"_on_room_end must NOT fire while other sessions live; got {fires!r}"
        )
        assert pipeline._pipeline_state_store.peek_active_room_session() == "r_xyz", (
            "room session stays alive while Bob is still present"
        )
    finally:
        pipeline._on_room_end = original
        asyncio.run(pipeline._pipeline_state_store.set_active_room_session(None))
        pipeline._session_store._sessions.clear()


def test_s113_pipeline_wires_batched_greeting_draining_after_for_det_loop():
    """Session 113 Part 2 — source-inspection guard that pipeline.run
    (a) collects greetable known-person entries into _pending_known_greets
    instead of speak()-ing inline, (b) drains via choose_greeting_order
    after the for-det loop exits, and (c) falls back to detection order
    when the pending list is shorter than BATCH_GREETING_MIN_PEOPLE. The
    structural guards let us iterate on the LLM prompt later without
    losing the wiring invariant."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.run)
    assert "_pending_known_greets" in src, (
        "collection list must exist so greetings can be reordered"
    )
    assert "choose_greeting_order(" in src, (
        "drain must call the brain-layer helper"
    )
    assert "BATCH_GREETING_ENABLED" in src and "BATCH_GREETING_MIN_PEOPLE" in src, (
        "gates must read both the master flag and the min-people threshold"
    )


def test_s3b1_room_block_returns_none_for_single_session():
    """Phase 3B.1 — single-active-session rooms MUST return None so the
    SCENE-only backward-compat path holds. The block's entire purpose
    is multi-person awareness; injecting it for solo sessions would be
    noise."""
    import pipeline, time
    out = pipeline._build_room_block(
        active_sessions=(_s3b1_sess("j", "Jagan", "best_friend"),),
        conversation={"j": []},
        emotion_agents={},
        room_start_ts=time.time() - 60,
        turn_cap=10,
    )
    assert out is None, f"single-session must return None; got {out!r}"


def test_s3b1_room_block_gated_off_returns_none(monkeypatch):
    """Phase 3B.1 — ROOM_BLOCK_ENABLED=False must produce None even in
    multi-person rooms. Master flag for a one-line rollback path if a
    live session exposes a regression."""
    import pipeline, time
    from core import config as _cfg
    monkeypatch.setattr(_cfg, "ROOM_BLOCK_ENABLED", False)
    out = pipeline._build_room_block(
        active_sessions=(
            _s3b1_sess("j", "Jagan", "best_friend"),
            _s3b1_sess("l", "Lexi",  "known"),
        ),
        conversation={"j": [], "l": []},
        emotion_agents={},
        room_start_ts=time.time() - 60,
        turn_cap=10,
    )
    assert out is None, "master flag off must return None"


def test_s3b1_room_block_interleaves_turns_chronologically():
    """Phase 3B.1 — turns across multiple speakers must be sorted by ts
    (oldest first, most recent last) so brain reads conversation flow
    as it actually happened. Seeds 3 turns per speaker with deliberate
    interleaving; asserts the rendered order matches chronology."""
    import pipeline, time
    now = time.time()
    start = now - 600  # 10min room
    convo = {
        "j": [
            {"role": "user",      "content": "Hi there",   "ts": start + 10},
            {"role": "assistant", "content": "Hey Jagan",  "ts": start + 12,
             "addressed_to": "Jagan"},
            {"role": "user",      "content": "what's new", "ts": start + 300},
        ],
        "l": [
            {"role": "user",      "content": "I'm Lexi",   "ts": start + 100},
            {"role": "assistant", "content": "Welcome Lexi", "ts": start + 102,
             "addressed_to": "Lexi"},
        ],
    }
    out = pipeline._build_room_block(
        active_sessions=(
            _s3b1_sess("j", "Jagan", "best_friend"),
            _s3b1_sess("l", "Lexi",  "known"),
        ),
        conversation=convo,
        emotion_agents={},
        room_start_ts=start,
        turn_cap=20,
        now=now,
    )
    assert out is not None
    # Assert chronological ordering: "Hi there" < "Hey Jagan" < "I'm Lexi"
    # < "Welcome Lexi" < "what's new".
    order = ["Hi there", "Hey Jagan", "I'm Lexi", "Welcome Lexi", "what's new"]
    positions = [out.find(s) for s in order]
    assert all(p >= 0 for p in positions), f"all turns must render: {positions}"
    assert positions == sorted(positions), (
        f"turns must appear in chronological order; got positions {positions}"
    )


def test_s3b1_room_block_renders_addressee_labels_on_assistant_messages():
    """Phase 3B.1 — assistant messages with addressed_to render as
    `Kara → Lexi: "..."` (brain sees WHO each response went to).
    Assistant messages WITHOUT addressed_to render as bare
    `Kara: "..."`. User turns render as `Speaker: "..."` since users
    don't carry an addressee."""
    import pipeline, time
    now = time.time()
    start = now - 120
    convo = {
        "j": [
            {"role": "user",      "content": "question 1", "ts": start + 10},
            {"role": "assistant", "content": "reply to J", "ts": start + 11,
             "addressed_to": "Jagan"},
        ],
        "l": [
            {"role": "assistant", "content": "pivoted reply", "ts": start + 20,
             "addressed_to": "Lexi"},
        ],
    }
    out = pipeline._build_room_block(
        active_sessions=(
            _s3b1_sess("j", "Jagan", "best_friend"),
            _s3b1_sess("l", "Lexi",  "known"),
        ),
        conversation=convo,
        emotion_agents={},
        room_start_ts=start,
        turn_cap=10,
        now=now,
    )
    assert "Kara → Jagan" in out, f"assistant-to-Jagan label missing; got:\n{out}"
    assert "Kara → Lexi" in out, f"assistant-to-Lexi label missing; got:\n{out}"
    assert "Jagan: \"question 1\"" in out, "user turn must render speaker + content"


def test_s3b1_room_block_filters_turns_before_room_start():
    """Phase 3B.1 — Session 111 Critical #2 invariant: messages with ts
    predating the current room session must be filtered out. Prevents
    yesterday's in-memory conversation bleeding into today's room
    context. Tests an old turn (before start) is EXCLUDED and a
    within-window turn IS included."""
    import pipeline, time
    now = time.time()
    start = now - 120   # room started 2 min ago
    convo = {
        "j": [
            {"role": "user", "content": "OLD TURN from yesterday",
             "ts": start - 3600},
            {"role": "user", "content": "in-room turn",
             "ts": start + 30},
        ],
        "l": [
            {"role": "user", "content": "lexi turn", "ts": start + 60},
        ],
    }
    out = pipeline._build_room_block(
        active_sessions=(
            _s3b1_sess("j", "Jagan", "best_friend"),
            _s3b1_sess("l", "Lexi",  "known"),
        ),
        conversation=convo,
        emotion_agents={},
        room_start_ts=start,
        turn_cap=10,
        now=now,
    )
    assert "OLD TURN" not in out, "pre-room-start turns must be filtered out"
    assert "in-room turn" in out
    assert "lexi turn" in out


def test_s3b1_room_block_honors_turn_cap():
    """Phase 3B.1 — when the session has more than turn_cap turns,
    only the MOST RECENT turn_cap must render. Keeps prompt tokens
    bounded; mirrors the design intent of a rolling window."""
    import pipeline, time
    now = time.time()
    start = now - 500
    convo = {
        "j": [
            {"role": "user", "content": f"j-turn-{i}", "ts": start + i}
            for i in range(20)
        ],
        "l": [
            {"role": "user", "content": f"l-turn-{i}", "ts": start + 100 + i}
            for i in range(5)
        ],
    }
    out = pipeline._build_room_block(
        active_sessions=(
            _s3b1_sess("j", "Jagan", "best_friend"),
            _s3b1_sess("l", "Lexi",  "known"),
        ),
        conversation=convo,
        emotion_agents={},
        room_start_ts=start,
        turn_cap=5,
        now=now,
    )
    # Count "turn-" occurrences in the turns section (5 is the cap).
    assert out.count("turn-") == 5, (
        f"cap must limit rendered turns; got {out.count('turn-')} occurrences"
    )
    # Most-recent ones are the ones from Lexi (ts=start+100+i) and the
    # last of Jagan's. Specifically: l-turn-0..l-turn-4 are the newest.
    for i in range(5):
        assert f"l-turn-{i}" in out


def test_s3b1_room_block_renders_per_person_mood():
    """Phase 3B.1 — per-person mood section pulls from EmotionAgent's
    get_dominant_emotion(). Missing agent renders 'unknown'; None
    emotion renders 'neutral'. Ensures stranger sessions don't crash
    the helper just because their agent wasn't created yet."""
    import pipeline, time
    class _FakeAgent:
        def __init__(self, label): self._label = label
        def get_dominant_emotion(self):
            return (self._label, 0.8) if self._label else (None, 0.0)
    now = time.time()
    start = now - 60
    out = pipeline._build_room_block(
        active_sessions=(
            _s3b1_sess("j", "Jagan", "best_friend"),
            _s3b1_sess("l", "Lexi",  "known"),
            _s3b1_sess("s", "Stranger", "stranger"),
        ),
        conversation={"j": [], "l": [], "s": []},
        emotion_agents={
            "j": _FakeAgent("neutral"),
            "l": _FakeAgent("anxious"),
            # "s" deliberately missing — simulates early stranger session.
        },
        room_start_ts=start,
        turn_cap=10,
        now=now,
    )
    assert "Jagan: neutral" in out
    assert "Lexi: anxious" in out
    assert "Stranger: unknown" in out, "missing agent must fall back to 'unknown'"


def test_s3b1_room_block_renders_room_duration():
    """Phase 3B.1 — room duration phrase drives the brain's sense of
    how long the current gathering has been active. Three branches:
    < 60s → "just started"; < 1h → "started Xm ago"; ≥ 1h → hours."""
    import pipeline, time
    now = time.time()
    cases = [
        (now - 30,    "just started"),
        (now - 300,   "started 5 min ago"),
        (now - 3700,  "started 1 hr ago"),
        (now - 7600,  "started 2 hrs ago"),
    ]
    for start, expected in cases:
        out = pipeline._build_room_block(
            active_sessions=(
                _s3b1_sess("j", "Jagan", "best_friend"),
                _s3b1_sess("l", "Lexi",  "known"),
            ),
            conversation={"j": [], "l": []},
            emotion_agents={},
            room_start_ts=start,
            turn_cap=10,
            now=now,
        )
        assert expected in out, (
            f"duration phrase {expected!r} missing for start={start}; got:\n{out}"
        )


def test_s3b1_build_system_prompt_injects_room_block():
    """Phase 3B.1 — `_build_system_prompt` must render the room_block
    when vision_state carries it. Uses a synthetic block string so the
    test is decoupled from _build_room_block's format."""
    from core.brain import _build_system_prompt
    marker = "<<<ROOM>>>\nActive in this room: A, B\n<<<END ROOM>>>"
    prompt = _build_system_prompt(
        person_name="Jagan",
        vision_state={"active_session_count": 2, "room_block": marker},
    )
    assert marker in prompt, "room_block must appear in the rendered prompt"


def test_s3b1_room_started_at_lifecycle(tmp_path):
    """Phase 3B.1 — module state `_active_room_started_at` must be set
    alongside `_active_room_session` on mint and cleared together on
    room end. Drives the "Room session started Xm ago" line — if this
    gets out of sync with the id, the block would render wrong
    durations or no duration at all."""
    import pipeline
    # Fresh state.
    asyncio.run(pipeline._pipeline_state_store.set_active_room_session(None))
    asyncio.run(pipeline._pipeline_state_store.set_active_room_started_at(None))
    pipeline._face_db_ref = None
    pipeline._per_person_agent_store.reset()

    pipeline._open_session("a_1", "Alice", "face", "known",
                           engagement_gate_passed=True)
    assert pipeline._pipeline_state_store.peek_active_room_session() is not None
    assert pipeline._pipeline_state_store.peek_active_room_started_at() is not None, (
        "mint must stamp started-at timestamp"
    )
    t_start = pipeline._pipeline_state_store.peek_active_room_started_at()

    # Second open into same room inherits — timestamp must NOT move.
    pipeline._open_session("b_1", "Bob", "face", "known",
                           engagement_gate_passed=True)
    assert pipeline._pipeline_state_store.peek_active_room_started_at() == t_start, (
        "second open into same room must inherit existing start time"
    )

    # Close everyone — stamp clears. Follow-up #129: _close_session now removes the session
    # SYNCHRONOUSLY via _sync_close_session, so back-to-back closes empty the store with no
    # drain — the last close sees _remaining == [] and fires room-end + _sync_clear_room()
    # synchronously, clearing the room id + start-time stamp (both sync reads below).
    # (Canary #4 needed an asyncio.run drain here only because close was still a fire-and-
    # forget create_task; #129 retired that close-pop scaffolding per spec §7 — the async
    # _on_room_end synthesis drain is NOT needed here since this test reads only sync state.)
    pipeline._close_session("a_1")
    pipeline._close_session("b_1")
    assert pipeline._pipeline_state_store.peek_active_room_session() is None
    assert pipeline._pipeline_state_store.peek_active_room_started_at() is None, (
        "room end must clear start-time stamp alongside the id"
    )


def test_s3b1_vision_state_wires_room_block():
    """Phase 3B.1 — source-inspection guard that both vision_state builds
    (pipeline.run's per-turn builder + _kairos_tick) populate "room_block"
    via _build_room_block. Lets us iterate on the helper without losing
    the wiring invariant. conversation_turn itself receives vision_state
    as a parameter — the build site is `run`."""
    import inspect, pipeline
    src_run    = inspect.getsource(pipeline.run)
    src_kairos = inspect.getsource(pipeline._kairos_tick)
    assert 'room_block' in src_run and '_build_room_block(' in src_run, (
        "pipeline.run vision_state must populate room_block via the helper"
    )
    assert 'room_block' in src_kairos and '_build_room_block(' in src_kairos, (
        "_kairos_tick vision_state must populate room_block via the helper"
    )


def test_s3b2_intent_labels_includes_direct_address_to_person():
    """Phase 3B.2 — new INTENT_LABELS entry must be present. INTENT_LABELS
    is the exhaustive set — missing or misspelled entries would cause the
    classifier's parsed sidecar to be rejected by the shape validator and
    the pipeline skip path would never fire. Structural guard."""
    from core.config import INTENT_LABELS
    assert "direct_address_to_person" in INTENT_LABELS, (
        "direct_address_to_person label missing from INTENT_LABELS frozenset"
    )


def test_s3b2_classifier_prompt_contains_direct_address_rule():
    """Phase 3B.2 — `_INTENT_CLASSIFIER_SYSTEM` must carry the
    DIRECT-ADDRESS RULE block AND the 5 counter-examples verbatim.
    Counter-examples are the teeth (the abstract rule without them drifts
    under STT noise); prompt-hash changes trigger a Phase 5 drift baseline
    reset so the five verbatim strings MUST stay."""
    from core.brain import _INTENT_CLASSIFIER_SYSTEM as src
    assert "DIRECT-ADDRESS RULE" in src, "rule block header missing"
    # 3 sub-rules (AI / PERSON / NOT EITHER).
    assert "direct_address_to_ai" in src, "AI-address sub-rule missing"
    assert "direct_address_to_person" in src, "PERSON-address sub-rule missing"
    # 5 verbatim counter-examples (reviewer's spec).
    ce = [
        'Kara, what\'s the weather?',
        'Jagan, what do you think?',
        'Lexi said the movie was good',
        'Kara, ask Jagan about the weather',
        'Hey Lexi, are you feeling better?',
    ]
    for phrase in ce:
        assert phrase in src, f"counter-example missing: {phrase!r}"


def test_s3b2_golden_corpus_has_new_regression_rows():
    """Phase 3B.2 — the 5 reviewer-specified golden rows tagged
    `regression_session_3b2` must land in tests/golden_intent.jsonl.
    These protect against classifier drift on this label through future
    prompt refactors — same pattern as regression_session_94 rows."""
    import json, pathlib
    path = pathlib.Path(__file__).parent.parent / "tests" / "golden_intent.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    s3b2 = [r for r in rows if r.get("source") == "regression_session_3b2"]
    assert len(s3b2) == 5, f"expected 5 regression_session_3b2 rows; got {len(s3b2)}"
    # One of each key variant must be present (quick sanity on coverage).
    texts = [r["user_text"] for r in s3b2]
    assert any("Kara, what's the weather" in t for t in texts)
    assert any("Jagan, what do you think" in t for t in texts)
    assert any("Lexi said the movie was good" in t for t in texts)


def test_s3b2_pipeline_has_silent_skip_branch():
    """Phase 3B.2 — source-inspection guard for the silent-skip branch
    in conversation_turn: (a) reads ROOM_STAY_SILENT_ON_USER_TO_USER,
    (b) calls _classify_intent early, (c) gates on active_sessions >= 2,
    (d) emits the documented log line, (e) returns early without calling
    ask_stream. These are the invariants that keep the behavioral path
    correct even if internal plumbing gets refactored."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    assert "ROOM_STAY_SILENT_ON_USER_TO_USER" in src, "config flag not read"
    assert "direct_address_to_person" in src, "intent label literal missing"
    assert "len(_session_store.peek_all_snapshots()) >= 2" in src, (
        "multi-person gate missing — single-person rooms MUST skip the classifier"
    )
    assert "User-to-user detected" in src, (
        "documented log signature missing — canary observability relies on it"
    )


async def test_s3b2_behavioral_silent_skip_fires_on_user_to_user(monkeypatch, tmp_path):
    """Phase 3B.2 — end-to-end behavioral test: when the classifier labels
    an utterance as `direct_address_to_person` with a name that is NOT
    the system_name, conversation_turn must (a) NOT call ask_stream /
    speak_stream, (b) log the user turn to _conversation + db.log_turn,
    (c) call _brain_orchestrator.notify, and (d) return ('continue', None).
    Heavy integration but gives ground-truth that the wire-in is correct."""
    import pipeline, time
    from core import db as _db_mod

    # Monkey-patch the classifier to return a direct_address_to_person sidecar.
    async def _fake_classifier(*args, **kwargs):
        return {
            "turn_intent":     "direct_address_to_person",
            "extracted_value": "Jagan",
            "confidence":      0.95,
            "reasoning":       "vocative = Jagan, not system name",
        }
    # Patch both points — pipeline imports it inline, brain exports it.
    monkeypatch.setattr("core.brain._classify_intent", _fake_classifier)

    ask_stream_fired = {"count": 0}
    async def _boom_ask_stream(*args, **kwargs):
        ask_stream_fired["count"] += 1
        if False:
            yield None  # never executes
    monkeypatch.setattr(pipeline, "ask_stream", _boom_ask_stream)

    speak_stream_fired = {"count": 0}
    async def _boom_speak_stream(*a, **k):
        speak_stream_fired["count"] += 1
    monkeypatch.setattr(pipeline, "speak_stream", _boom_speak_stream)
    monkeypatch.setattr(pipeline, "play_filler", lambda _t: None)
    monkeypatch.setattr(pipeline, "_set_state", lambda *a, **k: None)
    monkeypatch.setattr(pipeline, "stop_audio", lambda: None)

    # Lightweight in-memory DB stub that records log_turn calls.
    class _DBStub:
        def __init__(self):
            self.logged = []
        def get_best_friend(self): return None
        def load_conversation_history(self, pid): return []
        def log_turn(self, pid, role, content, **kw):
            self.logged.append((pid, role, content))
        def get_greeting_data(self, pid): return None
        def embedding_count(self, pid): return 0
    db_stub = _DBStub()

    class _OrchStub:
        def __init__(self):
            self.notified = 0
        def notify(self): self.notified += 1
        def get_pending_question(self): return None
        def get_prompt_addendum(self, pid): return None
        def get_context(self, *a, **k): return None
        def score_stranger_identity(self, *a, **k): return None
    orch_stub = _OrchStub()
    pipeline._brain_orchestrator = orch_stub

    now = time.time()
    pipeline._session_store._sessions.clear()
    await pipeline._session_store.open_session("jagan_001", "Jagan", "best_friend", "face", now=now)
    await pipeline._session_store.open_session("lexi_002", "Lexi", "known", "face", now=now)
    await pipeline._conversation_store.set_history("lexi_002", [])
    await pipeline._pipeline_state_store.recover_online_no_flag()
    await pipeline._pipeline_state_store.set_active_system_name("Kara")

    result = await pipeline.conversation_turn(
        text="Jagan, what do you think?",
        person_id="lexi_002",
        person_name="Lexi",
        db=db_stub,
    )

    assert result == ("continue", None), f"early return shape; got {result!r}"
    assert ask_stream_fired["count"] == 0, "ask_stream must NOT fire on user-to-user"
    assert speak_stream_fired["count"] == 0, "speak_stream must NOT fire"
    # User turn persisted (history + db + notify).
    assert any(msg.get("role") == "user" for msg in pipeline._conversation_store.peek_history("lexi_002"))
    assert any(log[1] == "user" for log in db_stub.logged)
    assert orch_stub.notified >= 1, "notify() must fire so extraction runs"
    # Cleanup.
    pipeline._conversation_store.reset()
    pipeline._brain_orchestrator = None
    pipeline._session_store._sessions.clear()


async def test_s3b2_behavioral_system_name_collision_falls_through(monkeypatch):
    """Phase 3B.2 — if the classifier extracts a name that matches the
    system's own name (someone in room named 'Kara' AND AI is 'Kara'),
    the silent-skip path MUST NOT fire. Ambiguous — safer to respond.
    Safety property: user-to-user skip is additive; collision edge
    cases never steal a legitimate response from the user."""
    import pipeline, time

    async def _fake_classifier(*args, **kwargs):
        return {
            "turn_intent":     "direct_address_to_person",
            "extracted_value": "Kara",  # system_name collision
            "confidence":      0.80,
            "reasoning":       "ambiguous",
        }
    monkeypatch.setattr("core.brain._classify_intent", _fake_classifier)

    # Spy whether we went past the skip point. Since we can't easily
    # simulate the rest of conversation_turn, we'll observe the fact
    # that conversation_turn did NOT return early — i.e. it reached
    # `_set_state(THINKING)`. Monkeypatch that to raise a sentinel and
    # catch. Caught → skip path was NOT taken (correct behavior).
    class _FellThrough(Exception):
        pass
    monkeypatch.setattr(pipeline, "_set_state",
                        lambda *a, **k: (_ for _ in ()).throw(_FellThrough()))
    monkeypatch.setattr(pipeline, "play_filler", lambda _t: None)

    now = time.time()
    pipeline._session_store._sessions.clear()
    await pipeline._session_store.open_session("a_1", "Alice", "known", "face", now=now)
    await pipeline._session_store.open_session("k_1", "Kara", "known", "face", now=now)
    await pipeline._conversation_store.set_history("a_1", [])
    await pipeline._pipeline_state_store.recover_online_no_flag()
    await pipeline._pipeline_state_store.set_active_system_name("Kara")  # AI is also Kara
    pipeline._brain_orchestrator = None

    class _DBStub:
        def get_best_friend(self): return None
        def load_conversation_history(self, pid): return []
        def log_turn(self, *a, **k): pass

    import pytest
    with pytest.raises(_FellThrough):
        await pipeline.conversation_turn(
            text="Kara, can you help me?",
            person_id="a_1",
            person_name="Alice",
            db=_DBStub(),
        )

    # Cleanup.
    pipeline._session_store._sessions.clear()
    pipeline._conversation_store.reset()


def test_s3b2_flag_off_falls_through(monkeypatch):
    """Phase 3B.2 — ROOM_STAY_SILENT_ON_USER_TO_USER=False must be a
    one-line rollback: classifier is not even consulted, conversation_turn
    falls through to the normal response path. Tests the master flag
    provides clean exit from the behavior if a live canary exposes a
    problem."""
    import inspect, pipeline
    # Structural guard: the config read happens on the gate line, so
    # monkey-patching the module-level constant flips the branch without
    # needing to re-execute the function.
    src = inspect.getsource(pipeline.conversation_turn)
    # Source should USE the flag's name and apply short-circuit logic.
    assert "if _STAY_SILENT and len(_session_store.peek_all_snapshots()) >= 2" in src or \
           "_STAY_SILENT and len(_session_store.peek_all_snapshots()) >= 2" in src, (
               "flag must short-circuit via 'and' before multi-person gate"
           )


def _s3b3_multi_room():
    """Shared 2-person room fixture for 3B.3 tests."""
    import time as _t
    now = _t.time()
    return dict(
        active_sessions=(
            _s3b1_sess("j", "Jagan", "best_friend"),
            _s3b1_sess("l", "Lexi",  "known"),
        ),
        conversation={"j": [], "l": []},
        emotion_agents={},
        room_start_ts=now - 60,
        turn_cap=10,
        now=now,
    )


def test_s3b3_turn_arbitration_section_present_in_room_block():
    """Phase 3B.3 — ROOM block must include a `<<<TURN ARBITRATION>>>`
    section when TURN_ARBITRATION_ENABLED is True (default) AND ROOM
    block itself renders (multi-person + ROOM_BLOCK_ENABLED)."""
    import pipeline
    out = pipeline._build_room_block(**_s3b3_multi_room())
    assert out is not None
    assert "<<<TURN ARBITRATION>>>" in out, "section header missing"
    assert "<<<END TURN ARBITRATION>>>" in out, "section closer missing"


def test_s3b3_arbitration_contains_all_four_rules_verbatim():
    """Phase 3B.3 — the 4 rules (reviewer-specified teeth of the
    mechanism) must be present by name. Counter-example removal would
    silently weaken the brain's reasoning — this test pins them."""
    import pipeline
    out = pipeline._build_room_block(**_s3b3_multi_room())
    required = [
        "MUMBLE CONTINUATION",
        "PENDING THREAD CIRCLE-BACK",
        "LONG-SILENCE RE-ENGAGEMENT",
        "DIRECT QUESTION ACROSS CONTEXT",
    ]
    for rule in required:
        assert rule in out, f"rule {rule!r} missing from arbitration section"


def test_s3b3_arbitration_contains_marker_format_instruction():
    """Phase 3B.3 — the section must explicitly tell the brain how to
    format the marker (single line, at response start, will be stripped
    before TTS). Session 113 Part 1's parser depends on this exact
    format; drift in the instruction text could produce unparseable
    markers."""
    import pipeline
    out = pipeline._build_room_block(**_s3b3_multi_room())
    assert "[addressing:" in out, "marker format sample missing"
    assert "on its own line at the START" in out, (
        "placement instruction missing — parser expects single-line marker"
    )
    assert "stripped before TTS" in out, (
        "stripping behavior must be documented so brain doesn't speak the marker"
    )


def test_s3b3_arbitration_gated_off_omits_section(monkeypatch):
    """Phase 3B.3 — TURN_ARBITRATION_ENABLED=False must drop the section
    without affecting the rest of the ROOM block. One-line rollback path
    if live canary shows the arbitration rules are triggering badly."""
    import pipeline
    from core import config as _cfg
    monkeypatch.setattr(_cfg, "TURN_ARBITRATION_ENABLED", False)
    out = pipeline._build_room_block(**_s3b3_multi_room())
    assert out is not None, (
        "ROOM block itself must still render; only arbitration section drops"
    )
    assert "<<<TURN ARBITRATION>>>" not in out
    # Rest of ROOM block still present.
    assert "<<<ROOM>>>" in out and "<<<END ROOM>>>" in out
    assert "Active in this room" in out
    assert "Current emotional state" in out


def test_s3b3_arbitration_absent_for_single_person_rooms():
    """Phase 3B.3 — single-person rooms have no ROOM block → no
    arbitration section. `_build_room_block` returns None in
    single-person; arbitration never renders."""
    import pipeline, time
    out = pipeline._build_room_block(
        active_sessions=(_s3b1_sess("j", "Jagan", "best_friend"),),
        conversation={"j": []},
        emotion_agents={},
        room_start_ts=time.time() - 30,
        turn_cap=10,
    )
    assert out is None, "single-person block must still return None"


def test_s3b3_arbitration_absent_when_room_block_gated_off(monkeypatch):
    """Phase 3B.3 — ROOM_BLOCK_ENABLED=False drops the entire ROOM
    block (including arbitration section). Tests that arbitration is
    gated transitively, not independently — can't have arbitration
    rules with no ROOM context."""
    import pipeline
    from core import config as _cfg
    monkeypatch.setattr(_cfg, "ROOM_BLOCK_ENABLED", False)
    out = pipeline._build_room_block(**_s3b3_multi_room())
    assert out is None, (
        "ROOM_BLOCK_ENABLED=False must suppress the entire block, "
        "arbitration included"
    )


def test_s3b3_arbitration_does_not_bloat_block_beyond_budget():
    """Phase 3B.3 — reviewer's non-regression: the arbitration section
    adds ~50-80 tokens; rough-count via character length (1 token ≈ 4
    chars) to catch accidental bloat if a future edit dumps the entire
    spec into the prompt. Soft upper bound of 1500 tokens total ROOM
    block keeps the per-turn prompt budget sane."""
    import pipeline
    out = pipeline._build_room_block(**_s3b3_multi_room())
    assert out is not None
    approx_tokens = len(out) / 4
    assert approx_tokens < 1500, (
        f"ROOM block too large: ~{approx_tokens:.0f} tokens "
        f"(raw length {len(out)} chars)"
    )


def test_s3b3_classifier_prompt_unchanged_by_arbitration():
    """Phase 3B.3 — arbitration lives in the MAIN chat prompt (via
    `_build_room_block` → `_build_system_prompt`), NOT in the intent
    classifier's system prompt. Phase 5 drift detection relies on the
    classifier hash staying stable; test asserts the TURN ARBITRATION
    header never leaked into `_INTENT_CLASSIFIER_SYSTEM`."""
    from core.brain import _INTENT_CLASSIFIER_SYSTEM
    assert "TURN ARBITRATION" not in _INTENT_CLASSIFIER_SYSTEM, (
        "arbitration must NOT appear in classifier prompt — that would "
        "reset the Phase 5 drift baseline unnecessarily"
    )


def test_s3b5_search_room_turns_scopes_to_room_session_id(tmp_path):
    """Phase 3B.5 — `FaceDB.search_room_turns` must return ONLY rows
    tagged with the given room_session_id. Seeds 2 rooms with turns
    containing the same keyword; asserts query against room_A returns
    only room_A's rows."""
    from core.db import FaceDB
    db = FaceDB(db_path=str(tmp_path / "faces.db"),
                faiss_path=str(tmp_path / "faiss.index"))
    try:
        # Add person rows so log_turn doesn't trip FK.
        db._conn.execute(
            "INSERT INTO persons (id, name, person_type, enrolled_at) "
            "VALUES (?,?,?,?)",
            ("j_1", "Jagan", "best_friend", _time_mod.time()),
        )
        db._conn.commit()
        db.log_turn("j_1", "user", "let's talk about cricket",
                    room_session_id="room_A", audience_ids=["j_1"])
        db.log_turn("j_1", "user", "cricket again in room B",
                    room_session_id="room_B", audience_ids=["j_1"])
        out_a = db.search_room_turns("room_A", "cricket", requester_pid="j_1")
        out_b = db.search_room_turns("room_B", "cricket", requester_pid="j_1")
        assert len(out_a) == 1
        assert "room_A" not in out_a[0]["content"] and "cricket" in out_a[0]["content"]
        assert len(out_b) == 1
        assert "room B" in out_b[0]["content"]
    finally:
        db._conn.close()


def test_s3b5_search_room_turns_audience_filter_blocks_non_audience(tmp_path):
    """Phase 3B.5 — audience_ids column holds a JSON array of pids who
    can see the row. Rows where requester is NOT in the list must be
    filtered out. Test seeds a row visible only to Jagan, queries as
    Kara, asserts empty result (Kara is a stranger visitor, not in
    Jagan's audience)."""
    from core.db import FaceDB
    db = FaceDB(db_path=str(tmp_path / "faces.db"),
                faiss_path=str(tmp_path / "faiss.index"))
    try:
        db._conn.execute(
            "INSERT INTO persons (id, name, person_type, enrolled_at) "
            "VALUES (?,?,?,?)",
            ("j_1", "Jagan", "best_friend", _time_mod.time()),
        )
        db._conn.execute(
            "INSERT INTO persons (id, name, person_type, enrolled_at) "
            "VALUES (?,?,?,?)",
            ("k_1", "Kara", "known", _time_mod.time()),
        )
        db._conn.commit()
        db.log_turn("j_1", "user", "jagan secret health data",
                    room_session_id="room_X", audience_ids=["j_1"])
        visible = db.search_room_turns("room_X", "secret", requester_pid="j_1")
        hidden  = db.search_room_turns("room_X", "secret", requester_pid="k_1")
        assert len(visible) == 1, "owner must see their own audience row"
        assert hidden == [], (
            f"non-audience requester must NOT see the row; got {hidden!r}"
        )
    finally:
        db._conn.close()


def test_s3b5_search_room_turns_null_audience_is_default_visible(tmp_path):
    """Phase 3B.5 — legacy rows (pre-Session-107) have NULL audience_ids;
    the column semantic is "default visible to any requester". Tests
    that a row with audience_ids=NULL (written via the raw SQL path that
    predates the kwarg) is returned to any requester."""
    from core.db import FaceDB
    db = FaceDB(db_path=str(tmp_path / "faces.db"),
                faiss_path=str(tmp_path / "faiss.index"))
    try:
        db._conn.execute(
            "INSERT INTO persons (id, name, person_type, enrolled_at) "
            "VALUES (?,?,?,?)",
            ("j_1", "Jagan", "best_friend", _time_mod.time()),
        )
        db._conn.commit()
        # Legacy-shape INSERT: audience_ids left NULL explicitly.
        db._conn.execute(
            "INSERT INTO conversation_log (person_id, role, content, "
            "room_session_id, audience_ids) VALUES (?,?,?,?,?)",
            ("j_1", "user", "legacy room turn with keyword", "room_L", None),
        )
        db._conn.commit()
        out = db.search_room_turns(
            "room_L", "keyword", requester_pid="any_pid",
        )
        assert len(out) == 1, "NULL audience must be default-visible"


    finally:
        db._conn.close()


def test_s3b5_count_room_turns_returns_accurate_count(tmp_path):
    """Phase 3B.5 — `count_room_turns` drives the SEARCH_ROOM_MEMORY_MIN_TURNS
    gate. Confirms it counts only the target room's rows (not other
    rooms, not NULL rooms)."""
    from core.db import FaceDB
    db = FaceDB(db_path=str(tmp_path / "faces.db"),
                faiss_path=str(tmp_path / "faiss.index"))
    try:
        db._conn.execute(
            "INSERT INTO persons (id, name, person_type, enrolled_at) "
            "VALUES (?,?,?,?)",
            ("j_1", "Jagan", "best_friend", _time_mod.time()),
        )
        db._conn.commit()
        for i in range(3):
            db.log_turn("j_1", "user", f"turn {i}",
                        room_session_id="room_C", audience_ids=["j_1"])
        db.log_turn("j_1", "user", "other-room turn",
                    room_session_id="room_D", audience_ids=["j_1"])
        assert db.count_room_turns("room_C") == 3
        assert db.count_room_turns("room_D") == 1
        assert db.count_room_turns("nonexistent") == 0
        assert db.count_room_turns("") == 0
    finally:
        db._conn.close()


async def test_s3b5_room_search_fn_returns_too_young_below_threshold(tmp_path, monkeypatch):
    """Phase 3B.5 — when room turn count < SEARCH_ROOM_MEMORY_MIN_TURNS,
    the callback MUST return status='too_young' + hint and no turns.
    Prevents noisy empty results on 1-3 turn rooms."""
    import json, pipeline
    from core.db import FaceDB
    from core import config as _cfg
    monkeypatch.setattr(_cfg, "SEARCH_ROOM_MEMORY_MIN_TURNS", 5)
    db = FaceDB(db_path=str(tmp_path / "faces.db"),
                faiss_path=str(tmp_path / "faiss.index"))
    try:
        db._conn.execute(
            "INSERT INTO persons (id, name, person_type, enrolled_at) "
            "VALUES (?,?,?,?)",
            ("j_1", "Jagan", "best_friend", _time_mod.time()),
        )
        db._conn.commit()
        # Only 2 turns → below threshold.
        for i in range(2):
            db.log_turn("j_1", "user", f"turn {i}",
                        room_session_id="room_Y", audience_ids=["j_1"])
        fn = pipeline._make_room_search_fn("room_Y", "j_1", db)
        result = json.loads(await fn("cricket"))
        assert result["status"] == "too_young"
        assert result["turns"] == []
        assert "below" in result.get("hint", "").lower() or \
               "threshold" in result.get("hint", "").lower()
    finally:
        db._conn.close()


async def test_s3b5_room_search_fn_disabled_flag_short_circuits(monkeypatch):
    """Phase 3B.5 — SEARCH_ROOM_MEMORY_ENABLED=False must make the
    callback return status='disabled' without touching the DB. Master
    rollback flag for canary regressions."""
    import json, pipeline
    from core import config as _cfg
    monkeypatch.setattr(_cfg, "SEARCH_ROOM_MEMORY_ENABLED", False)
    # db stub that would blow up if touched.
    class _BoomDB:
        def count_room_turns(self, *a, **k): raise AssertionError("DB not allowed")
        def search_room_turns(self, *a, **k): raise AssertionError("DB not allowed")
    fn = pipeline._make_room_search_fn("room_X", "j_1", _BoomDB())
    result = json.loads(await fn("query"))
    assert result["status"] == "disabled"


async def test_s3b5_room_search_fn_renders_speaker_names_and_ages(tmp_path, monkeypatch):
    """Phase 3B.5 — the rendered response dict must carry human-readable
    speaker names (resolved via FaceDB.get_person) + relative age
    labels. Brain uses these to frame "Lexi said 5m ago..." responses.
    Also sanity-checks room-turn rows are the bodies, not just ids."""
    import json, pipeline, time as _t
    from core.db import FaceDB
    from core import config as _cfg
    monkeypatch.setattr(_cfg, "SEARCH_ROOM_MEMORY_MIN_TURNS", 1)
    db = FaceDB(db_path=str(tmp_path / "faces.db"),
                faiss_path=str(tmp_path / "faiss.index"))
    try:
        db._conn.execute(
            "INSERT INTO persons (id, name, person_type, enrolled_at) "
            "VALUES (?,?,?,?)",
            ("j_1", "Jagan", "best_friend", _time_mod.time()),
        )
        db._conn.execute(
            "INSERT INTO persons (id, name, person_type, enrolled_at) "
            "VALUES (?,?,?,?)",
            ("l_1", "Lexi", "known", _time_mod.time()),
        )
        db._conn.commit()
        # Use explicit ts values so age labels are predictable.
        now = _t.time()
        db._conn.execute(
            "INSERT INTO conversation_log (person_id, role, content, ts, "
            "room_session_id, audience_ids) VALUES (?,?,?,?,?,?)",
            ("l_1", "user", "I have an interview tomorrow", now - 300,
             "room_Z", '["l_1","j_1"]'),
        )
        db._conn.commit()
        fn = pipeline._make_room_search_fn("room_Z", "j_1", db)
        result = json.loads(await fn("interview"))
        assert result["status"] == "ok"
        assert len(result["turns"]) == 1
        t = result["turns"][0]
        assert t["speaker"] == "Lexi", f"name not resolved; got {t!r}"
        # 300s ≈ 5m
        assert "m ago" in t["age"] or "just now" == t["age"]
        assert "interview" in t["content"]
    finally:
        db._conn.close()


def test_s3b5_tool_registered_in_brain_tools():
    """Phase 3B.5 — `search_room_memory` must be registered in brain.TOOLS
    so Together.ai exposes it to the model. Also asserts the tool's
    minimum-turn hint is present in the description so brain knows the
    threshold semantic before calling."""
    from core.brain import TOOLS
    names = [t["function"]["name"] for t in TOOLS]
    assert "search_room_memory" in names, (
        "search_room_memory missing from brain.TOOLS"
    )
    # Arg shape: query only (pipeline auto-injects room_id).
    tool = next(t for t in TOOLS if t["function"]["name"] == "search_room_memory")
    params = tool["function"]["parameters"]
    assert params["required"] == ["query"], (
        "tool must take only 'query' — room_id is pipeline-injected"
    )
    assert "room_id" not in params["properties"], (
        "tool MUST NOT expose room_id parameter (pipeline-scoped)"
    )


def test_s3b5_tool_privileges_entry_present():
    """Phase 3B.5 — TOOL_PRIVILEGES must list search_room_memory so the
    fail-closed privilege gate (Session 61 Step 2) doesn't block legit
    calls. Strangers are out of scope — room-search requires engaged
    session context."""
    from core.config import TOOL_PRIVILEGES
    assert "search_room_memory" in TOOL_PRIVILEGES, (
        "missing from TOOL_PRIVILEGES — fail-closed gate would block the tool"
    )
    assert TOOL_PRIVILEGES["search_room_memory"] == frozenset(
        {"known", "best_friend"}
    )


def test_s3b5_ask_stream_wires_room_search_fn():
    """Phase 3B.5 — source-inspection guard that `ask_stream` accepts
    `room_search_fn` and dispatches `search_room_memory` tool calls
    through it. Follows the same pattern as `memory_search_fn`."""
    import inspect
    from core import brain as brain_mod
    src = inspect.getsource(brain_mod.ask_stream)
    assert "room_search_fn" in src, "ask_stream signature must take room_search_fn"
    assert "search_room_memory" in src, (
        "ask_stream must parse search_room_memory tool calls"
    )
    # Follow-up stream pattern (like memory_call): builds tool response
    # then streams follow-up via _stream_together_raw with tools disabled.
    assert "room_call" in src, "ask_stream must have a room_call variable"


def test_s3b6_store_and_get_recent_room_context_roundtrip(tmp_path):
    """Phase 3B.6 — `store_room_summary` persists the row, and
    `get_recent_room_context(person_id)` retrieves it ONLY when the
    requester was in the speaker list."""
    from core.brain_agent import BrainDB
    bdb = BrainDB(tmp_path / "brain.db")
    try:
        now = _time_mod.time()
        bdb.store_room_summary(
            room_session_id="room_T",
            started_at=now - 600,
            ended_at=now - 60,
            speaker_pids=["j_1", "l_1"],
            summary="Jagan and Lexi discussed the thesis deadline.",
            topic_tags=["thesis", "deadline"],
            safety_flags=[{"pid": "l_1", "name": "Lexi",
                           "attribute": "expressed_suicidal_thoughts",
                           "entity": "Lexi"}],
        )
        rc_jagan = bdb.get_recent_room_context("j_1", hours=24)
        assert rc_jagan is not None, "Jagan participated; must retrieve"
        assert rc_jagan["summary"] == "Jagan and Lexi discussed the thesis deadline."
        assert "thesis" in rc_jagan["topic_tags"]
        assert rc_jagan["safety_flags"][0]["attribute"] == "expressed_suicidal_thoughts"
        rc_kara = bdb.get_recent_room_context("kara_1", hours=24)
        assert rc_kara is None, "Kara wasn't in the room; must NOT retrieve"
    finally:
        bdb._conn.close()


def test_s3b6_get_recent_room_context_respects_hours_window(tmp_path):
    """Phase 3B.6 — rooms older than the ``hours`` lookback must NOT be
    returned. Guards the ROOM_RECENT_CONTEXT_HOURS invariant — stale
    summaries silently polluting greeting context would be invisible."""
    from core.brain_agent import BrainDB
    bdb = BrainDB(tmp_path / "brain.db")
    try:
        now = _time_mod.time()
        # Ended 3 days ago — outside 24h window.
        bdb.store_room_summary(
            room_session_id="room_old",
            started_at=now - 3 * 86400 - 600,
            ended_at=now - 3 * 86400,
            speaker_pids=["j_1"],
            summary="old room",
        )
        assert bdb.get_recent_room_context("j_1", hours=24) is None
        # Widened window returns it.
        assert bdb.get_recent_room_context("j_1", hours=96) is not None
    finally:
        bdb._conn.close()


def test_s3b6_get_recent_room_context_returns_most_recent(tmp_path):
    """Phase 3B.6 — when multiple qualifying rooms exist, the newest
    (by ended_at) wins. Drives the greeting enrichment to reference
    the MOST recent interaction, not a stale earlier one."""
    from core.brain_agent import BrainDB
    bdb = BrainDB(tmp_path / "brain.db")
    try:
        now = _time_mod.time()
        bdb.store_room_summary(
            room_session_id="room_earlier",
            started_at=now - 7200, ended_at=now - 7000,
            speaker_pids=["j_1", "l_1"],
            summary="earlier room — thesis talk",
        )
        bdb.store_room_summary(
            room_session_id="room_later",
            started_at=now - 300, ended_at=now - 120,
            speaker_pids=["j_1", "l_1"],
            summary="later room — dinner plans",
        )
        rc = bdb.get_recent_room_context("j_1", hours=24)
        assert rc is not None
        assert rc["room_session_id"] == "room_later"
        assert "dinner" in rc["summary"]
    finally:
        bdb._conn.close()


async def test_s3b6_synthesize_room_writes_summary_row(tmp_path, monkeypatch):
    """Phase 3B.6 — `BrainOrchestrator.synthesize_room` must persist a
    row to room_summaries with topic_tags + safety_flags populated from
    the room's knowledge rows. LLM call is monkey-patched to return a
    canned summary so the test is deterministic."""
    import sqlite3 as _sq3, json as _json_t
    from core.brain_agent import BrainDB, BrainOrchestrator
    import core.brain_agent as _ba

    orch = BrainOrchestrator.__new__(BrainOrchestrator)
    orch._brain_db   = BrainDB(tmp_path / "brain.db")
    orch._faces_conn = _sq3.connect(str(tmp_path / "faces.db"))
    orch._faces_conn.executescript("""
        CREATE TABLE persons (id TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE conversation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id TEXT, role TEXT, content TEXT,
            ts REAL NOT NULL DEFAULT 0,
            room_session_id TEXT, audience_ids TEXT
        );
    """)
    orch._faces_conn.executemany(
        "INSERT INTO persons (id, name) VALUES (?, ?)",
        [("j_1", "Jagan"), ("l_1", "Lexi")],
    )
    now = _time_mod.time()
    for i, (pid, content) in enumerate([
        ("j_1", "I'm worried about Lexi"),
        ("l_1", "I have an interview tomorrow"),
        ("j_1", "Let me help you prep"),
        ("l_1", "I don't want to live anymore"),
    ]):
        orch._faces_conn.execute(
            "INSERT INTO conversation_log (person_id, role, content, ts, "
            "room_session_id) VALUES (?,?,?,?,?)",
            (pid, "user", content, now - 300 + i, "room_S3B6"),
        )
    orch._faces_conn.commit()
    # Seed some knowledge rows so topic + safety aggregation pull them.
    orch._brain_db._conn.execute(
        "INSERT INTO knowledge (entity, entity_type, attribute, value, "
        "confidence, person_id, created_at, source_turn_id, agent) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ("interview", "event", "tomorrow", "true", 0.9, "l_1",
         now - 200, 1, "ExtractionAgent"),
    )
    orch._brain_db._conn.execute(
        "INSERT INTO knowledge (entity, entity_type, attribute, value, "
        "confidence, person_id, created_at, source_turn_id, agent) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ("Lexi", "person", "expressed_suicidal_thoughts", "true", 0.95,
         "l_1", now - 150, 2, "ExtractionAgent"),
    )
    orch._brain_db._conn.commit()

    # Stub the LLM helper (module-level _call_llm_chat in brain_agent).
    async def _fake_llm(*args, **kwargs):
        return "Jagan helped Lexi prep for an interview; Lexi expressed distress."
    monkeypatch.setattr(_ba, "_call_llm_chat", _fake_llm)

    import httpx
    orch._http = httpx.AsyncClient()
    try:
        await orch.synthesize_room(
            room_session_id="room_S3B6",
            speaker_pids=["j_1", "l_1"],
            started_at=now - 400,
        )
        row = orch._brain_db._conn.execute(
            "SELECT summary, topic_tags, safety_flags FROM room_summaries "
            "WHERE room_session_id = ?", ("room_S3B6",),
        ).fetchone()
        assert row is not None, "room_summaries row must be written"
        summary, topic_json, safety_json = row
        assert "interview" in summary.lower() or "prep" in summary.lower()
        topics = _json_t.loads(topic_json)
        assert "interview" in topics or "Lexi" in topics, (
            f"topic aggregation missing key entities; got {topics!r}"
        )
        flags = _json_t.loads(safety_json)
        assert any(
            f.get("attribute") == "expressed_suicidal_thoughts" for f in flags
        ), f"safety flag missing; got {flags!r}"
    finally:
        await orch._http.aclose()
        orch._brain_db._conn.close()
        orch._faces_conn.close()


async def test_s3b6_synthesize_room_llm_failure_falls_back_to_topics(tmp_path, monkeypatch):
    """Phase 3B.6 — if the LLM call fails/times out, `synthesize_room`
    MUST still persist a row with a non-empty summary. Falls back to
    topic-tag-only string. Preserves the invariant: room-end synthesis
    is best-effort; a row is always written so greeting enrichment
    can later reference something."""
    import sqlite3 as _sq3
    from core.brain_agent import BrainDB, BrainOrchestrator
    import core.brain_agent as _ba

    orch = BrainOrchestrator.__new__(BrainOrchestrator)
    orch._brain_db   = BrainDB(tmp_path / "brain.db")
    orch._faces_conn = _sq3.connect(str(tmp_path / "faces.db"))
    orch._faces_conn.executescript("""
        CREATE TABLE persons (id TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE conversation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id TEXT, role TEXT, content TEXT,
            ts REAL NOT NULL DEFAULT 0,
            room_session_id TEXT, audience_ids TEXT
        );
    """)
    orch._faces_conn.executemany(
        "INSERT INTO persons (id, name) VALUES (?, ?)",
        [("j_1", "Jagan"), ("l_1", "Lexi")],
    )
    now = _time_mod.time()
    orch._faces_conn.execute(
        "INSERT INTO conversation_log (person_id, role, content, ts, "
        "room_session_id) VALUES (?,?,?,?,?)",
        ("j_1", "user", "hello", now - 60, "room_T"),
    )
    orch._faces_conn.commit()
    orch._brain_db._conn.execute(
        "INSERT INTO knowledge (entity, entity_type, attribute, value, "
        "confidence, person_id, created_at, source_turn_id, agent) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ("cooking", "activity", "likes", "true", 0.9, "j_1",
         now - 30, 1, "ExtractionAgent"),
    )
    orch._brain_db._conn.commit()

    # Stub LLM to return None (timeout / error).
    async def _boom_llm(*args, **kwargs):
        return None
    monkeypatch.setattr(_ba, "_call_llm_chat", _boom_llm)

    import httpx
    orch._http = httpx.AsyncClient()
    try:
        await orch.synthesize_room(
            room_session_id="room_T",
            speaker_pids=["j_1", "l_1"],
            started_at=now - 100,
        )
        row = orch._brain_db._conn.execute(
            "SELECT summary FROM room_summaries WHERE room_session_id = ?",
            ("room_T",),
        ).fetchone()
        assert row is not None, "row must still be written on LLM failure"
        assert row[0], "fallback summary must be non-empty"
        assert "Topics" in row[0] or "cooking" in row[0], (
            f"fallback must reference topic tags; got {row[0]!r}"
        )
    finally:
        await orch._http.aclose()
        orch._brain_db._conn.close()
        orch._faces_conn.close()


async def test_s3b6_synthesize_room_single_speaker_skipped(tmp_path, monkeypatch):
    """Phase 3B.6 — single-person room sessions skip synthesis entirely
    (no cross-speaker context to summarize; per-person session-end
    already handles single-speaker insight). No row written."""
    import sqlite3 as _sq3
    from core.brain_agent import BrainDB, BrainOrchestrator

    orch = BrainOrchestrator.__new__(BrainOrchestrator)
    orch._brain_db   = BrainDB(tmp_path / "brain.db")
    orch._faces_conn = _sq3.connect(str(tmp_path / "faces.db"))
    orch._faces_conn.executescript("""
        CREATE TABLE persons (id TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE conversation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id TEXT, role TEXT, content TEXT,
            ts REAL NOT NULL DEFAULT 0,
            room_session_id TEXT, audience_ids TEXT
        );
    """)
    orch._faces_conn.commit()
    import httpx
    orch._http = httpx.AsyncClient()
    try:
        await orch.synthesize_room(
            room_session_id="room_solo",
            speaker_pids=["j_1"],        # single-person → skip
        )
        row = orch._brain_db._conn.execute(
            "SELECT room_session_id FROM room_summaries"
        ).fetchone()
        assert row is None, (
            "single-person room must not write a row"
        )
    finally:
        await orch._http.aclose()
        orch._brain_db._conn.close()
        orch._faces_conn.close()


def test_s3b6_build_system_prompt_injects_recent_rooms_block():
    """Phase 3B.6 — `_build_system_prompt` renders a <<<RECENT ROOMS>>>
    block when vision_state carries recent_room_context; block includes
    summary + topic + safety hints + human-readable age."""
    from core.brain import _build_system_prompt
    rc = {
        "room_session_id": "room_X",
        "ended_at":        _time_mod.time() - 3600,  # 1 hour ago
        "speaker_pids":    ["j_1", "l_1"],
        "summary":         "Jagan helped Lexi with her interview prep.",
        "topic_tags":      ["interview", "career"],
        "safety_flags":    [{"pid": "l_1", "name": "Lexi",
                             "attribute": "expressed_suicidal_thoughts"}],
    }
    prompt = _build_system_prompt(
        person_name="Jagan",
        vision_state={"recent_room_context": rc, "active_session_count": 1},
    )
    assert "<<<RECENT ROOMS>>>" in prompt
    assert "interview" in prompt.lower()
    assert "Lexi" in prompt
    assert "expressed suicidal thoughts" in prompt or \
           "expressed_suicidal_thoughts" in prompt


def test_s3b6_build_system_prompt_omits_block_when_no_context():
    """Phase 3B.6 — no recent_room_context means no block (backward
    compat with pre-3B.6 prompts + with windows where synthesis was
    disabled)."""
    from core.brain import _build_system_prompt
    prompt = _build_system_prompt(
        person_name="Jagan",
        vision_state={"active_session_count": 1},
    )
    assert "<<<RECENT ROOMS>>>" not in prompt


def test_s3b6_on_room_end_dispatches_synthesize_room(monkeypatch):
    """Phase 3B.6 — `_on_room_end` must schedule
    `_brain_orchestrator.synthesize_room` as a fire-and-forget task
    when speaker_pids has ≥2 participants. Guards the wiring contract:
    synthesis runs background, doesn't block room lifecycle."""
    import asyncio as _aio, pipeline
    captured = {"called": False, "args": None}

    class _OrchStub:
        async def synthesize_room(self, *, room_session_id,
                                  speaker_pids, started_at):
            captured["called"] = True
            captured["args"] = (room_session_id, speaker_pids, started_at)

    pipeline._brain_orchestrator = _OrchStub()
    try:
        async def _drive():
            await pipeline._on_room_end(
                "room_W", speaker_pids=["j_1", "l_1"],
                started_at=_time_mod.time() - 100,
            )
            # Let create_task run.
            await _aio.sleep(0)
        _aio.run(_drive())
        assert captured["called"], (
            "_on_room_end must dispatch synthesize_room when 2+ speakers"
        )
        room_id, pids, _ = captured["args"]
        assert room_id == "room_W"
        assert list(pids) == ["j_1", "l_1"]
    finally:
        pipeline._brain_orchestrator = None


def test_s3b6_on_room_end_skips_synthesize_for_single_speaker(monkeypatch):
    """Phase 3B.6 — single-speaker room: _on_room_end logs the end but
    does NOT schedule synthesize_room. Prevents wasted work on the
    most common case (Jagan alone)."""
    import asyncio as _aio, pipeline
    captured = {"called": False}

    class _OrchStub:
        async def synthesize_room(self, **kwargs):
            captured["called"] = True

    pipeline._brain_orchestrator = _OrchStub()
    try:
        async def _drive():
            await pipeline._on_room_end(
                "room_Single", speaker_pids=["j_1"],
            )
            await _aio.sleep(0)
        _aio.run(_drive())
        assert not captured["called"], (
            "single-speaker room must not fire synthesize_room"
        )
    finally:
        pipeline._brain_orchestrator = None
