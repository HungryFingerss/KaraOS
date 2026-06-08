# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""P1.A1 SP-7b.1 — conversation-turn sub-flows (companion app layer).

shadow_classify: VISION_ROADMAP P1.3 lazy shadow intent classifier. Fires only when
the main stream proposed a tool whose gate is in TOOL_INTENT_MAP; returns the intent
sidecar dict {turn_intent, extracted_value, confidence, reasoning} or None. Shadow-mode
only logs (the regex gate stays authoritative until P1.7+). Extracted verbatim from
pipeline.conversation_turn (SP-7b.1); companion app logic, reusable by other profiles.
"""

from __future__ import annotations

from core.log_utils import _now_log_ts
import runtime.wiring as _wiring  # P1.A1 SP-7b.2: shim dispatch + session_end_notify brain-notify
import time  # P1.A1 SP-7b.3: history_persist _now_ts wall-clock stamp
from core.config import CONVERSATION_HISTORY_LIMIT  # P1.A1 SP-7b.3
from runtime.wiring import _conversation_store  # P1.A1 SP-7b.3: from-import SAFE (reset-in-place shared object)


async def shadow_classify(text, history, tool_calls):
    """Gated shadow intent classification. Returns the intent_sidecar dict or None."""
    from core.config import INTENT_SHADOW_MODE_ENABLED, TOOL_INTENT_MAP
    _intent_sidecar: "dict | None" = None
    if (INTENT_SHADOW_MODE_ENABLED
            and tool_calls
            and any(tc["name"] in TOOL_INTENT_MAP for tc in tool_calls)):
        # Spec 2 wiring: route through `_classify_intent_smart` so graph
        # runs alongside LLM in shadow mode. Production behavior identical
        # in shadow (LLM result returned + divergences logged).
        from core.brain import _classify_intent_smart
        _intent_sidecar = await _classify_intent_smart(text, conversation_history=history)
        if _intent_sidecar is not None:
            _tool_names_str = ", ".join(tc["name"] for tc in tool_calls
                                        if tc["name"] in TOOL_INTENT_MAP)
            print(
                f"[Intent] {_now_log_ts()} "
                f"tools=[{_tool_names_str}] "
                f"classified={_intent_sidecar['turn_intent']} "
                f"value={_intent_sidecar['extracted_value']!r} "
                f"conf={_intent_sidecar['confidence']:.2f} "
                f"reason={_intent_sidecar.get('reasoning', '')[:80]!r}"
            )
    return _intent_sidecar


def _compute_room_audience(
    participants: "set[str] | list[str] | tuple[str, ...]",
    person_id: str,
) -> "list[str]":
    """P0.S7.D-D Stage 1 shim → RoomOrchestrator.compute_room_audience.

    Legacy module-level helper preserved as a function-shim (NOT attribute
    binding — defers lookup to call time so the shim works even if the
    underlying class instance is reassigned). 130 test sites call this
    name unchanged; Stage 2 hard-deletes the shim and migrates tests.
    """
    if _wiring._room_orchestrator is None:
        raise RuntimeError(
            "RoomOrchestrator not initialized — _init_room_orchestrator() "
            "must run first (production: from run(); tests: autouse fixture)"
        )
    return _wiring._room_orchestrator.compute_room_audience(participants, person_id)


def session_end_notify(db, person_id, text, response, _is_disputed_session, _room_sid):
    """P1.A1 SP-7b.2 — end-of-turn persist + brain-notify (output-free).

    Extracted verbatim from pipeline.conversation_turn (P10). Persists the user+
    assistant turns with full-room audience (via _compute_room_audience) unless the
    session is identity-disputed, then wakes the brain agent. Side-effect only —
    returns None. _is_disputed_session/_room_sid computed by the caller.
    """
    if db and not _is_disputed_session:
        # P0.S7 T-B + MEDIUM 4 — full-room-audience (sites 4+5 share one
        # call; same logical turn).
        _ct_audience = _compute_room_audience(
            _wiring._pipeline_state_store.peek_active_room_participants(),
            person_id,
        )
        db.log_turn(person_id, "user",      text, room_session_id=_room_sid,
                    audience_ids=_ct_audience)
        db.log_turn(person_id, "assistant", response, room_session_id=_room_sid,
                    audience_ids=_ct_audience)
        # Wake brain agent immediately — extraction runs during TTS so facts
        # are in brain.db before the user speaks their next turn.
        if _wiring._brain_orchestrator:
            _wiring._brain_orchestrator.notify()
    elif _is_disputed_session:
        print(f"[Pipeline] Skipping log_turn for disputed session {person_id} — "
              f"turns stay in-memory only until identity resolves.")


def _resolve_addressed_to(
    parsed_addr: "str | None",
    active_sessions: "tuple",
    effective_name: str,
) -> str:
    """Session 113 Part 1 — resolve the LLM's [addressing:X] marker into
    the history's addressed_to field. Policy:
      - marker absent / empty / "current" → default to current speaker
      - marker names a person in active_sessions (case-insensitive) → use
        that person's canonical name from the session dict
      - marker names someone not active → log warning + fall back to the
        current speaker (safety property: the marker never silently
        corrupts history with an unverifiable name).

    Pulled out of conversation_turn so unit tests can exercise the three
    branches without the full turn surface.

    Session 113.1: emit an observability log line on every call so canary
    debugging can tell apart (a) "LLM emitted a marker that routed to X"
    vs (b) "LLM emitted no marker; default to current speaker." Prior to
    the log, canary analysis had no ground truth on whether Part 1's
    parser actually fired — a mis-address could be a broken marker parse
    OR a legit LLM decision, and we couldn't distinguish.
    """
    # Session 116 P1 #8 — address decision reasoning: surface the room
    # candidate count so an outside reviewer can see WHY the default
    # path was taken (single-person room → no override possible vs.
    # multi-person room → LLM chose to default).
    _candidate_count = len(active_sessions)
    if not parsed_addr or parsed_addr.strip().lower() == "current":
        print(
            f"[Pipeline] Turn addressed: {effective_name} (default; "
            f"candidates={_candidate_count})"
        )
        return effective_name
    addr_lc = parsed_addr.strip().lower()
    matched = next(
        (s.person_name for s in active_sessions
         if s.person_name.strip().lower() == addr_lc),
        None,
    )
    if matched:
        print(
            f"[Pipeline] Turn addressed: {matched} "
            f"(LLM: '[addressing:{parsed_addr}]'; candidates={_candidate_count})"
        )
        return matched
    print(
        f"[Pipeline] ADDRESS DECISION: unknown name {parsed_addr!r} "
        f"not in active sessions, falling back to {effective_name!r}"
    )
    print(f"[Pipeline] Turn addressed: {effective_name} (fallback)")
    return effective_name


async def history_persist(text, response, person_id, person_name, _addr_override, history):
    """P1.A1 SP-7b.3 — end-of-turn history append + cap-trim + persist (non-empty
    bundle). Extracted verbatim from pipeline.conversation_turn (P9). Resolves the
    effective speaker name + the addressed_to marker, appends user+assistant turns
    to the in-memory history, trims to CONVERSATION_HISTORY_LIMIT, and persists.
    Returns effective_name (the only slice-defined local the caller reads after).
    """
    # ── Update in-memory conversation name if it changed ─────────────────────
    # session dict may have been updated by update_person_name tool
    _post_tool_snap = _wiring._session_store.peek_snapshot(person_id)
    effective_name = _post_tool_snap.person_name if _post_tool_snap is not None else person_name

    # Session 113 Part 1 — resolve the ADDRESS DECISION marker parsed by
    # _token_gen into the addressed_to field. TTS already played without
    # the marker (stripped in _token_gen); this only affects the history
    # field and, through it, Session 111's cross-person excerpt rendering.
    addressed_to = _resolve_addressed_to(
        _addr_override[0], _wiring._session_store.peek_all_snapshots(), effective_name,
    )

    # ── History + persistence ──────────────────────────────────────────────────
    # Session 111 Criticals #2 + #3 + HIGH timestamps — each message gets:
    #   - ts:           wall-clock write time (drives HIGH-timestamps excerpt
    #                   format + Critical #2 session-boundary filtering)
    #   - addressed_to: assistant-only; names the person the assistant was
    #                   replying to. Critical #3: 4-person rooms need
    #                   unambiguous "you [to Alice]: ..." format instead of
    #                   the previous "you: ..." where the target was implied
    #                   by the containing session dict. Session 113 Part 1
    #                   populates this from the LLM's [addressing:X] marker
    #                   when multi-person (falls back to effective_name).
    _now_ts = time.time()
    history.append({
        "role":    "user",
        "content": text,
        "ts":      _now_ts,
    })
    history.append({
        "role":         "assistant",
        "content":      response,
        "ts":           _now_ts,
        "addressed_to": addressed_to,
    })
    # Enforce in-session history cap: load_conversation_history() caps at
    # CONVERSATION_HISTORY_LIMIT turns on DB load, but in-session accumulation
    # is unbounded.  Trim here so the LLM never sees more than the limit.
    # Trim from the front (oldest turns) so recent context is preserved.
    _max_msgs = CONVERSATION_HISTORY_LIMIT * 2   # 2 messages per turn
    if len(history) > _max_msgs:
        history = history[-_max_msgs:]
    await _conversation_store.set_history(person_id, history)
    return effective_name
