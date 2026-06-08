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
