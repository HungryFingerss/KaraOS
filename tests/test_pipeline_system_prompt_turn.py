"""test_pipeline_system_prompt_turn — system prompt turn tests (split from test_pipeline.py, P1.A1 SP-1).

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


def test_conversation_turn_no_longer_resets_repeat_guard_per_turn():
    """Bug Q Part A: the per-turn pop of _tool_repeat_last/_tool_repeat_count
    at the top of conversation_turn defeated the guard's entire purpose.
    Source-inspection confirms those lines are gone. Regression guard — if
    someone re-adds them, the 2026-04-21 feedback loop comes back."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    # The specific pop pattern must NOT appear at the top of the function.
    # (Other pops inside _execute_tool are fine — those are the guard resetting
    # itself when the tool repeat limit has been reached.)
    assert '_active_sessions[person_id].pop("_tool_repeat_last"' not in src, (
        "Bug Q Part A regression: conversation_turn must NOT pop repeat-guard "
        "state on every user message — that defeats the cross-turn guard"
    )
    assert '_active_sessions[person_id].pop("_tool_repeat_count"' not in src, (
        "Same regression — both counter and key must persist across turns"
    )


def test_conversation_turn_canonical_ack_checks_handled_not_noop():
    """Bug Q: the canonical 'Got it, I'll go by X' ack must fire only for
    effective tool calls (handled), never for no-ops (handled_noop). Source-
    inspection confirms the gate is on _any_tool_effective, not the old
    _any_tool_handled."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    assert "_any_tool_effective" in src, (
        "the per-tool classification dict must distinguish 'handled' (effective) "
        "from 'handled_noop' so the ack only fires for real state changes"
    )
    # And the specific gate comparison must reference the handled status.
    assert '_tool_results.get(tc["name"]) == "handled"' in src, (
        "the HISTORY_OVERRIDE gate must require the specific result to be "
        "'handled' — not just truthy — or no-ops leak through to the ack"
    )


def test_conversation_turn_shutdown_rejected_override_still_applies():
    """Session 71 Issue A protection: even with unified 'rejected' status,
    the shutdown-specific history-poisoning override must remain — otherwise
    "Goodbye!" streamed alongside a rejected shutdown enters history and
    re-triggers shutdown next turn (infinite loop, Session 28 Issue A)."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    assert "_shutdown_was_rejected" in src, (
        "the shutdown-specific override must survive the unified-rejected "
        "refactor — it protects against Issue A history poisoning"
    )
    # The override must detect 'rejected' status specifically for the shutdown tool.
    assert '_tool_results.get(tc["name"]) == "rejected"' in src, (
        "override gate must recognize the new 'rejected' status"
    )


def test_conversation_turn_all_unreal_triggers_ollama_retry():
    """Bug P + Session 71 unified 'rejected': when ALL tool calls returned
    either 'unknown' (hallucinated name, Bug P) OR 'rejected' (user-text gate
    rejected, Bugs S/T) AND response text is empty, conversation_turn must
    route to Ollama for a text retry rather than fall through to the 'Sorry, I
    missed that' filler. The classifier is now named _all_unreal (was
    _all_unknown pre-Session 71)."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    assert "_all_unreal" in src, (
        "conversation_turn must classify the all-ungrounded case (unknown + rejected + tool_timeout)"
    )
    # P0.8: "tool_timeout" joined the ungrounded-outcomes set so the retry
    # path also fires when a handler hits its per-tool budget.
    assert '"unknown"' in src and '"rejected"' in src and '"tool_timeout"' in src, (
        "the _all_unreal classifier must accept ALL of 'unknown' (Bug P), "
        "'rejected' (Bugs S/T), and 'tool_timeout' (P0.8) as ungrounded outcomes"
    )
    assert "ungrounded" in src.lower(), (
        "the Ollama-retry log must distinctly describe this class so operators "
        "can see how often the LLM is firing calls without grounding"
    )


def test_system_prompt_contains_critical_tool_rule():
    """L2: SYSTEM_PROMPT must contain the CRITICAL TOOL RULE section."""
    from core.brain import SYSTEM_PROMPT
    assert "CRITICAL TOOL RULE" in SYSTEM_PROMPT


def test_system_prompt_tool_rule_mentions_action_tools():
    """L2: The CRITICAL TOOL RULE must name the action tools explicitly."""
    from core.brain import SYSTEM_PROMPT
    idx = SYSTEM_PROMPT.index("CRITICAL TOOL RULE")
    rule_section = SYSTEM_PROMPT[idx:]
    assert "update_person_name" in rule_section
    assert "update_system_name" in rule_section


def test_system_prompt_no_longer_instructs_bare_silent():
    """Bug X Layer 2: the system prompt previously told the LLM to 'respond
    with the literal single word SILENT' for regular turns. That instruction
    is the leak source. The KAIROS path has its own SILENT contract; regular
    conversation must produce real spoken content."""
    from core import brain
    sp = brain.SYSTEM_PROMPT
    # The old harmful instruction must be gone.
    assert "respond with the literal single word SILENT" not in sp, (
        "the global instruction telling the LLM to emit bare SILENT is the "
        "Bug X leak source — it must be removed from the regular-turn prompt"
    )
    # And the new explicit prohibition must be present.
    assert "NEVER emit bare protocol tokens" in sp, (
        "the system prompt must explicitly forbid bare protocol tokens (SILENT, "
        "NO_RESPONSE, etc.) as spoken response"
    )


def test_conversation_turn_suppresses_whole_response_meta_commentary():
    """Bug H Layer 3: if the ENTIRE streamed response is meta-commentary, the
    conversation_turn must suppress it (set response='') so it doesn't pollute
    history and get imitated on future turns. Source-inspection check."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    assert "_is_meta_commentary" in src, (
        "conversation_turn must call _is_meta_commentary on the whole response — "
        "Bug H Layer 3 is the backstop when the sentence-level filter missed a fragment"
    )
    assert "Meta-commentary suppressed" in src, (
        "The suppression must log what it dropped, for diagnostics"
    )


def test_system_prompt_has_anti_meta_instruction():
    """Bug H Layer 2: the system prompt must explicitly forbid meta-commentary
    and tell the model to respond with SILENT when it has nothing to say —
    this is the upstream defense, before the TTS filter even runs."""
    from core import brain
    sp = brain.SYSTEM_PROMPT
    assert "no function call is needed" in sp.lower(), (
        "the documented leak phrase must be called out by name in the prompt"
    )
    assert "SILENT" in sp, (
        "the model needs an explicit 'nothing to say' escape hatch that isn't meta-commentary"
    )


def test_system_prompt_surfaces_recognition_confidence_bucket():
    """High/medium/low confidence buckets must appear in SENSORS block based on score."""
    from core.brain import _build_system_prompt
    hi = _build_system_prompt(
        person_name="Jagan", system_name="Kara",
        vision_state={"face_in_frame": True, "person_name": "Jagan", "recognition_conf": 0.72},
        voice_state=None, memory_context=None,
    )
    mid = _build_system_prompt(
        person_name="Jagan", system_name="Kara",
        vision_state={"face_in_frame": True, "person_name": "Jagan", "recognition_conf": 0.48},
        voice_state=None, memory_context=None,
    )
    lo = _build_system_prompt(
        person_name="Jagan", system_name="Kara",
        vision_state={"face_in_frame": True, "person_name": "Jagan", "recognition_conf": 0.30},
        voice_state=None, memory_context=None,
    )
    assert "high confidence" in hi
    assert "medium confidence" in mid
    assert "low confidence" in lo


def test_system_prompt_injects_identity_disputed_block():
    """When vision_state.identity_disputed=True, prompt must include the IDENTITY DISPUTED block."""
    from core.brain import _build_system_prompt
    p = _build_system_prompt(
        person_name="Jagan", system_name="Kara",
        vision_state={
            "face_in_frame": True, "person_name": "Jagan",
            "recognition_conf": 0.40,
            "identity_disputed": True,
            "disputed_claimed_name": "Venkat",
        },
        voice_state=None, memory_context=None,
    )
    assert "IDENTITY DISPUTED" in p
    assert "Venkat" in p


def test_conversation_turn_skips_log_turn_when_disputed():
    """During a disputed session, db.log_turn must not be called — turns live only
    in-memory until the dispute resolves."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    assert "_is_disputed_session" in src, \
        "conversation_turn must define _is_disputed_session guard"
    assert "not _is_disputed_session" in src, \
        "log_turn must be gated on `not _is_disputed_session`"


def _make_evidence(**overrides):
    """Shared test helper — build a default identity_evidence dict with any
    overrides. Keeps evidence-structured tests readable: one call, name the
    fields that matter, rest defaults to 'no witness'. Used across the Step 3
    regression suite."""
    ev = {
        "face_match_conf":     0.0,
        "face_last_seen_ts":   0.0,
        "anti_spoof_live":     False,
        "anti_spoof_score":    0.0,
        "anti_spoof_last_ts":  0.0,
        "voice_match_conf":    0.0,
        "voice_sample_count":  0,
        "voice_last_heard_ts": 0.0,
        "bootstrap_credits":   0,
    }
    ev.update(overrides)
    return ev


def test_ask_stream_yields_finish_event(monkeypatch):
    """Obs 3: ask_stream must emit a terminal ('finish', reason) event once per
    call, carrying the latest finish_reason seen on the SSE wire. Downstream
    consumers (pipeline's retry gate) depend on this being authoritative."""
    import asyncio
    from core import brain

    async def _fake_stream(messages, include_tools=True):
        yield ("text", "Hello!")
        yield ("finish", "stop")

    async def _collect():
        monkeypatch.setattr(brain, "_stream_together_raw", _fake_stream)
        monkeypatch.setattr(brain, "CHAT_API_KEY", "fake-key-for-test", raising=False)
        events = []
        async for ev in brain.ask_stream("hi", person_name="Alice"):
            events.append(ev)
        return events

    events = asyncio.run(_collect())
    # The terminal event must appear exactly once and be last.
    finish_events = [e for e in events if e[0] == "finish"]
    assert len(finish_events) == 1, f"expected exactly one finish event, got {finish_events}"
    assert events[-1][0] == "finish", "finish event must be the last yielded event"
    assert events[-1][1] == "stop"


def test_ask_stream_forwards_none_finish_reason_on_aborted_stream(monkeypatch):
    """Obs 3: when the SSE stream aborts before any finish_reason arrives
    (e.g. mid-token disconnect), ask_stream must forward ('finish', None) —
    downstream treats None as a real truncation and fires the Ollama retry."""
    import asyncio
    from core import brain

    async def _fake_stream(messages, include_tools=True):
        yield ("text", "Hmm")
        yield ("finish", None)   # aborted

    async def _collect():
        monkeypatch.setattr(brain, "_stream_together_raw", _fake_stream)
        monkeypatch.setattr(brain, "CHAT_API_KEY", "fake-key-for-test", raising=False)
        events = []
        async for ev in brain.ask_stream("hi", person_name="Alice"):
            events.append(ev)
        return events

    events = asyncio.run(_collect())
    assert events[-1] == ("finish", None)


def test_conversation_turn_retry_gate_rejects_stop_finish_reason():
    """Obs 3: source-inspection — the retry gate must AND-combine the
    word-count and punctuation heuristics with a truncation-class finish_reason
    check. Specifically, the guard must reject `finish_reason == 'stop'` even
    for single-word unterminated responses. This is the exact regression that
    motivated Obs 3 — a legit 'Hmm' from the model shouldn't trip Ollama."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.conversation_turn)
    # The guard expression must include the _truncated flag derived from finish_reason.
    assert "_truncated" in src, (
        "Retry gate must reference a _truncated flag derived from finish_reason"
    )
    # And the flag must evaluate True only for truncation-class reasons.
    assert 'in ("length", "content_filter", None)' in src, (
        "_truncated must be True only for ('length', 'content_filter', None) — "
        "any other finish_reason (notably 'stop') must short-circuit the retry"
    )


def test_brain_verdict_tracks_config_when_mature_threshold_changes(monkeypatch):
    """Step 3 follow-up (reviewer's finding): the brain's IDENTITY EVIDENCE verdict
    must read VOICE_ACCUM_* from config so raising e.g. MATURE_SAMPLE_COUNT moves
    BOTH the pipeline gate and the brain label in lockstep. No hardcoded 5/0.45/10.0
    literals in brain.py's heuristic. Patches the brain module's binding because
    `from X import Y` creates a local name — config edits don't auto-propagate."""
    from core.brain import _build_system_prompt
    import time

    # Raise the mature-count bar from 5 to 7. A session with 5 samples should now
    # be "medium" instead of "high" — voice_ok path is off, face_ok still holds.
    monkeypatch.setattr("core.brain.VOICE_ACCUM_MATURE_SAMPLE_COUNT", 7)
    p = _build_system_prompt(
        person_name="Jagan", system_name="Kara",
        vision_state={
            "face_in_frame": True, "person_name": "Jagan",
            "recognition_conf": 0.80,
            "session_person_type": "best_friend",
            "identity_evidence": _make_evidence(
                face_match_conf=0.85,
                face_last_seen_ts=time.time(),
                anti_spoof_live=True,
                voice_match_conf=0.60,
                voice_sample_count=5,                # below new threshold
                voice_last_heard_ts=time.time(),
            ),
        },
        voice_state=None, memory_context=None,
    )
    # At mature=7, n=5 is not enough → voice_ok=False → verdict shouldn't be "high".
    assert "verdict: high-confidence identity" not in p
    # Face path still holds, so verdict should be "medium".
    assert "verdict: medium-confidence identity" in p


def test_build_system_prompt_renders_identity_evidence_block():
    """Step 3: prompt contains <<<IDENTITY EVIDENCE>>> with a verdict line."""
    from core.brain import _build_system_prompt
    import time
    p = _build_system_prompt(
        person_name="Jagan", system_name="Kara",
        vision_state={
            "face_in_frame": True, "person_name": "Jagan",
            "recognition_conf": 0.80,
            "session_person_type": "best_friend",
            "identity_evidence": _make_evidence(
                face_match_conf=0.85,
                face_last_seen_ts=time.time(),
                anti_spoof_live=True,
                anti_spoof_score=0.98,
                voice_match_conf=0.60,
                voice_sample_count=7,
                voice_last_heard_ts=time.time(),
            ),
        },
        voice_state=None, memory_context=None,
    )
    assert "<<<IDENTITY EVIDENCE>>>" in p
    assert "verdict: high-confidence identity" in p


def test_build_system_prompt_contains_tool_access_block_for_best_friend():
    """Step 2: prompt must list each tool in TOOL_PRIVILEGES with availability
    for the current caller, so the brain knows upfront not to attempt blocked tools."""
    from core.brain import _build_system_prompt
    p = _build_system_prompt(
        person_name="Jagan", system_name="Kara",
        vision_state={
            "face_in_frame": True, "person_name": "Jagan",
            "recognition_conf": 0.8, "session_person_type": "best_friend",
        },
        voice_state=None, memory_context=None,
    )
    assert "<<<TOOL ACCESS FOR THIS SPEAKER (person_type='best_friend')>>>" in p
    # Owner must see shutdown + update_system_name as available
    assert "shutdown: available" in p
    assert "update_system_name: available" in p


def test_build_system_prompt_marks_tools_not_available_for_known():
    """A 'known' caller must see shutdown + update_system_name marked NOT AVAILABLE."""
    from core.brain import _build_system_prompt
    p = _build_system_prompt(
        person_name="Priya", system_name="Kara",
        vision_state={
            "face_in_frame": True, "person_name": "Priya",
            "recognition_conf": 0.8, "session_person_type": "known",
        },
        voice_state=None, memory_context=None,
    )
    assert "shutdown: NOT AVAILABLE" in p
    assert "update_system_name: NOT AVAILABLE" in p
    # But they retain access to generally-open tools
    assert "search_web: available" in p


def test_conversation_log_has_room_session_id_and_audience_ids_columns(tmp_path):
    """Session 107 Phase 3A.6 Part 3: additive schema migration must
    create room_session_id + audience_ids columns on conversation_log.
    Not wired into retrieval yet (3B territory) — this session just
    makes the columns available for 3B's RoomOrchestrator to populate."""
    from core.db import FaceDB
    db = FaceDB(
        str(tmp_path / "faces.db"),
        faiss_path=str(tmp_path / "faiss.index"),
    )
    try:
        cols = {
            r[1]: r[2]
            for r in db._conn.execute("PRAGMA table_info(conversation_log)").fetchall()
        }
        assert "room_session_id" in cols, (
            "room_session_id column must exist on conversation_log"
        )
        assert cols["room_session_id"] == "TEXT", (
            "room_session_id must be TEXT (holds opaque session identifiers)"
        )
        assert "audience_ids" in cols, (
            "audience_ids column must exist on conversation_log"
        )
        assert cols["audience_ids"] == "TEXT", (
            "audience_ids must be TEXT (JSON-encoded list of person_ids)"
        )
    finally:
        db._conn.close()


def test_conversation_log_has_room_index(tmp_path):
    """Session 107 Phase 3A.6 Part 3: index on (room_session_id, ts
    DESC) enables efficient 'most recent N turns in this room' queries
    that 3B RoomOrchestrator will run on every turn."""
    from core.db import FaceDB
    db = FaceDB(
        str(tmp_path / "faces.db"),
        faiss_path=str(tmp_path / "faiss.index"),
    )
    try:
        idx_names = {
            r[1] for r in db._conn.execute(
                "SELECT * FROM sqlite_master WHERE type='index' "
                "AND tbl_name='conversation_log'"
            ).fetchall()
        }
        assert "idx_conv_log_room" in idx_names, (
            "idx_conv_log_room must exist for 3B room-history retrieval"
        )
    finally:
        db._conn.close()


def test_conversation_log_backfill_populates_legacy_rows(tmp_path):
    """Session 107 Phase 3A.6 Part 3: pre-migration rows (room_session_id
    IS NULL) must be backfilled deterministically. Each legacy row
    gets `{person_id}_{first_ts}` as room_session_id + `[person_id]`
    as audience_ids, preserving single-speaker semantics."""
    import sqlite3 as _sqlite3, json as _json_t, time as _t
    # Simulate a pre-migration DB: open raw SQLite with the old
    # conversation_log schema (no room_session_id / audience_ids).
    raw_path = tmp_path / "faces_raw.db"
    raw = _sqlite3.connect(str(raw_path))
    raw.execute("PRAGMA journal_mode=WAL")
    raw.executescript("""
        CREATE TABLE persons (
            id TEXT PRIMARY KEY, name TEXT NOT NULL,
            person_type TEXT NOT NULL DEFAULT 'known',
            enrolled_at REAL, last_seen REAL,
            preferred_language TEXT NOT NULL DEFAULT 'en'
        );
        CREATE TABLE embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id TEXT NOT NULL, faiss_idx INTEGER, vector BLOB,
            created_at REAL NOT NULL
        );
        CREATE TABLE conversation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id TEXT NOT NULL, role TEXT NOT NULL,
            content TEXT NOT NULL, ts REAL NOT NULL
        );
    """)
    now = _t.time()
    raw.execute(
        "INSERT INTO conversation_log (person_id, role, content, ts) "
        "VALUES ('jagan_001', 'user', 'hello', ?)",
        (now,),
    )
    raw.execute(
        "INSERT INTO conversation_log (person_id, role, content, ts) "
        "VALUES ('jagan_001', 'assistant', 'hi', ?)",
        (now + 1,),
    )
    raw.commit()
    raw.close()

    from core.db import FaceDB
    db = FaceDB(
        str(raw_path),
        faiss_path=str(tmp_path / "faiss.index"),
    )
    try:
        rows = db._conn.execute(
            "SELECT room_session_id, audience_ids FROM conversation_log "
            "ORDER BY id"
        ).fetchall()
        assert len(rows) == 2
        for rsid, aud in rows:
            assert rsid is not None, (
                "backfill must populate room_session_id for legacy rows"
            )
            assert rsid.startswith("jagan_001_"), (
                f"room_session_id should be deterministic "
                f"`{{person_id}}_{{first_ts}}`, got {rsid!r}"
            )
            aud_list = _json_t.loads(aud)
            assert aud_list == ["jagan_001"], (
                "audience_ids backfill must be [person_id] to preserve "
                "single-speaker visibility"
            )
    finally:
        db._conn.close()
