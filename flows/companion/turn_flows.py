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
