# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""SB.4.1 — the prompt-block registry (PURE DATA; D4).

One entry per system-prompt block: the block-name → {enabled_key, render_fn
STRING, class, phase}. ``brain.py`` resolves the render_fn string → the bound
``_render_<name>`` callable (via ``_RENDER_BY_NAME``, like the orchestrator's
``_CLASS_BY_NAME`` in SB.3), so this module imports NOTHING from ``core/`` —
``profiles/`` stays pure data, no ``profiles/ → core/`` coupling (the layering
SB.2.1 locked via the loader's no-``core.config`` rule). T6 enforces the
no-import structurally.

- ``enabled_key`` — the ``core.config`` flag NAME (STRING) that gates the block,
  or ``None`` for blocks gated by a runtime condition (persona always-on;
  ``system_name_prose`` fires on ``system_name`` truthy; ``identity_disputed``
  fires when the session is disputed; etc.). NOT a config flag → ``None``.
- ``render_fn`` — STRING; resolved by ``brain._RENDER_BY_NAME`` (SB.4.1 step 2).
- ``class``   — ``PERSONA`` / ``SAFETY`` / ``OPTIONAL`` / ``STRUCTURAL``. The
  four SAFETY blocks are ``MANDATORY_BLOCKS`` (a clone can NEVER drop them).
- ``phase``   — ``stable`` (Section 1+2 → the Wave-4 cached prefix, rendered by
  ``render_session_stable_prefix``) vs ``dynamic`` (Section 3 → per-turn,
  rendered by ``_build_system_prompt``). The load-bearing PI-B rule: each
  builder iterates ONLY its phase-slice — if both iterate the full list, every
  block double-renders (T5/T10).

**Insertion order = assembly order.** The ``companion`` bundle is the ordered
full tuple; the prompt assembles top-to-bottom within each phase, so order is
load-bearing (T1 byte-identical golden + T4 order-preservation prove it). The
order was grep-confirmed against live ``core/brain.py`` 2275-3014 at SB.4.1
Phase-4 (FINDING A — ``system_name_prose`` :2336 between hedged_naming +
system_identity; FINDING B — ``scene`` :2913 at dynamic slot 6, BEFORE room).
"""

from __future__ import annotations

# 27 blocks = 12 stable (Section 1+2, cached prefix) + 15 dynamic (Section 3,
# per-turn). name: {enabled_key, render_fn, class, phase}.
BLOCK_REGISTRY = {
    # ── stable slice (12) — render_session_stable_prefix, Sections 1+2 ──────────
    "persona":             {"enabled_key": None,                                "render_fn": "render_persona",             "class": "PERSONA",    "phase": "stable"},
    "tool_contributions":  {"enabled_key": None,                                "render_fn": "render_tool_contributions", "class": "STRUCTURAL", "phase": "stable"},
    "hedged_naming":       {"enabled_key": "HEDGED_NAMING_CONTRACT_ENABLED",    "render_fn": "render_hedged_naming",       "class": "OPTIONAL",   "phase": "stable"},
    # FINDING A (dev Pass-3 + architect grep-confirmed :2336-2349): own-name STATE
    # prose, runtime-conditional on `system_name` truthy REGARDLESS of
    # SYSTEM_IDENTITY_BLOCK_ENABLED; two-branch body (!= DEFAULT_SYSTEM_NAME vs the
    # default-name else). DISTINCT from persona(:2301 pure-static) AND
    # system_identity(:2357). NOT a MANDATORY safety block (own-name plumbing).
    "system_name_prose":   {"enabled_key": None,                                "render_fn": "render_system_name_prose",  "class": "STRUCTURAL", "phase": "stable"},
    "system_identity":     {"enabled_key": "SYSTEM_IDENTITY_BLOCK_ENABLED",     "render_fn": "render_system_identity",     "class": "STRUCTURAL", "phase": "stable"},
    "known_speaker":       {"enabled_key": "KNOWN_SPEAKER_IDENTITY_BLOCK_ENABLED", "render_fn": "render_known_speaker",   "class": "OPTIONAL",   "phase": "stable"},
    "honesty_policy":      {"enabled_key": "HONESTY_POLICY_BLOCK_ENABLED",      "render_fn": "render_honesty_policy",      "class": "SAFETY",     "phase": "stable"},
    "cross_person_privacy":{"enabled_key": "CROSS_PERSON_PRIVACY_BLOCK_ENABLED","render_fn": "render_cross_person_privacy","class": "SAFETY",    "phase": "stable"},
    "tool_access":         {"enabled_key": None,                                "render_fn": "render_tool_access",         "class": "SAFETY",     "phase": "stable"},
    "stranger_identity":   {"enabled_key": "STRANGER_IDENTITY_BLOCK_ENABLED",   "render_fn": "render_stranger_identity",   "class": "OPTIONAL",   "phase": "stable"},
    "identity_disputed":   {"enabled_key": None,                                "render_fn": "render_identity_disputed",   "class": "SAFETY",     "phase": "stable"},
    "core_memory":         {"enabled_key": "CORE_MEMORY_ENABLED",               "render_fn": "render_core_memory",         "class": "OPTIONAL",   "phase": "stable"},
    # ── dynamic slice (15) — _build_system_prompt, Section 3, per-turn ──────────
    "datetime":            {"enabled_key": None,                                "render_fn": "render_datetime",            "class": "STRUCTURAL", "phase": "dynamic"},  # :2666 bare line
    "sensors":             {"enabled_key": None,                                "render_fn": "render_sensors",             "class": "STRUCTURAL", "phase": "dynamic"},  # :2707
    "identity_evidence":   {"enabled_key": "IDENTITY_EVIDENCE_BLOCK_ENABLED",   "render_fn": "render_identity_evidence",   "class": "OPTIONAL",   "phase": "dynamic"},  # :2742
    "visitor_context":     {"enabled_key": "VISITOR_CONTEXT_BLOCK_ENABLED",     "render_fn": "render_visitor_context",     "class": "OPTIONAL",   "phase": "dynamic"},  # :2845
    "address_decision":    {"enabled_key": "ADDRESS_DECISION_BLOCK_ENABLED",    "render_fn": "render_address_decision",    "class": "OPTIONAL",   "phase": "dynamic"},  # :2885
    # FINDING B (dev Pass-3 + architect grep-confirmed): scene injects at :2913-2914
    # BEFORE room/shared/recent — slot 6 of the dynamic slice. PI-C: render_fn reads
    # ctx.scene_block (built upstream in pipeline._build_scene_block; the :2647 param
    # is the RECEIPT, not the injection — §6 lock).
    "scene":               {"enabled_key": "SCENE_BLOCK_ENABLED",              "render_fn": "render_scene",               "class": "OPTIONAL",   "phase": "dynamic"},  # :2913
    "room":                {"enabled_key": "ROOM_BLOCK_ENABLED",              "render_fn": "render_room",                "class": "OPTIONAL",   "phase": "dynamic"},  # :2924
    "shared_context":      {"enabled_key": "SHARED_CONTEXT_BLOCK_ENABLED",     "render_fn": "render_shared_context",      "class": "OPTIONAL",   "phase": "dynamic"},  # :2935
    "recent_rooms":        {"enabled_key": None,                                "render_fn": "render_recent_rooms",        "class": "OPTIONAL",   "phase": "dynamic"},  # :2973 (gated by vision_state content)
    # ── PI-C generalization (auditor Plan-v1 gate): the 4 sibling param-contributions
    #    + person_name are the SAME registry-external class as SCENE (built upstream,
    #    injected as raw prose appends :2975-3005). RESOLVED into the registry — each
    #    is a phase=dynamic render_fn reading ctx.<param>; the prose wrapper moves
    #    verbatim. Now blocks:-axis-controlled + in T11's net.
    "memory_context":      {"enabled_key": None,                                "render_fn": "render_memory_context",      "class": "OPTIONAL",   "phase": "dynamic"},  # :2975
    "object_context":      {"enabled_key": None,                                "render_fn": "render_object_context",      "class": "OPTIONAL",   "phase": "dynamic"},  # :2984 (VESTIGIAL post-SB.1 YOLO-removal; always None until SB.6)
    "emotion_context":     {"enabled_key": None,                                "render_fn": "render_emotion_context",     "class": "OPTIONAL",   "phase": "dynamic"},  # :2991 (CONTENT gated upstream by EMOTION_ENABLED)
    "prompt_addendum":     {"enabled_key": None,                                "render_fn": "render_prompt_addendum",     "class": "OPTIONAL",   "phase": "dynamic"},  # :2997 (also read by render_visitor_context — both read ctx.prompt_addendum, no conflict)
    "person_name_line":    {"enabled_key": None,                                "render_fn": "render_person_name_line",    "class": "OPTIONAL",   "phase": "dynamic"},  # :3004
    "time_anchor":         {"enabled_key": None,                                "render_fn": "render_time_anchor",         "class": "STRUCTURAL", "phase": "dynamic"},  # :3012 near-END (recency); DISTINCT from "datetime" :2666
}

# Bundle shorthand (D3): `blocks: companion` → the full ordered 27. Mirrors SB.3's
# AGENT_BUNDLES + SB.2.1's `provider: cloud` leaf-expansion. Clones add reduced
# bundles in their own profile cycle. Ordered tuple — order is load-bearing.
BLOCK_BUNDLES = {"companion": tuple(BLOCK_REGISTRY)}

# PI-A — the mandatory SAFETY set. A clone's `blocks:` selection that drops ANY
# of these fails LOUD at load (_validate_block_closure). Companion has all → moot.
# Per-block reasoning is in SB4-1-plan-v1.md §4; the closure test (T3) enforces
# exactly this set and remains adjustable at the gate (safety-load-bearing).
MANDATORY_BLOCKS = ("honesty_policy", "cross_person_privacy", "tool_access", "identity_disputed")
