# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""SB.8 — the persona-pack schema (PURE DATA; D2).

The closed contract a pack YAML validates against. Plan v2 §1 schema delta:
the single ``persona_prompt`` key is superseded by the two SLOT keys
(``persona_identity`` + ``persona_character``) matching the engine's two-slot
template (PI-B). The key set is CLOSED — unknown keys fail loud, which is the
schema half of the D1 durable principle: a pack key that is not a
schema-defined slot filler can never reach the rendered prompt (the renderer
consumes exactly the slot keys; A4 locks the other half).

This module imports NOTHING from ``core/`` — ``persona/`` stays pure data,
same layering rule as ``profiles/`` (no ``persona/ → core/`` coupling).
"""

from __future__ import annotations

# The 4 greeting time-of-day buckets — mirrors core/brain.py's _time_of_day()
# output domain. Every pack must carry all 4, each with ≥1 template.
TIME_OF_DAY_KEYS: tuple[str, ...] = ("morning", "afternoon", "evening", "night")

# The closed pack key set (Plan v2 §1). Scalar strings unless noted:
#   persona_id            — must equal the pack's file stem AND the selected id
#   system_name_default   — the PRE-ASSIGNMENT default name (config.DEFAULT_SYSTEM_NAME;
#                           the user-assigned runtime name in system_identity is UNTOUCHED)
#   voice_id              — Kokoro voice name (config.TTS_VOICE_ID)
#   persona_identity      — slot 1 text ({persona_identity} in the engine template)
#   persona_character     — slot 2 text ({persona_character})
#   greeting_persona_line — the one greeting-prompt slot ({greeting_persona_line})
#   greeting_fallbacks    — mapping: EXACTLY the 4 TIME_OF_DAY_KEYS, each a
#                           non-empty list of str templates ({name} runtime key)
REQUIRED_KEYS: tuple[str, ...] = (
    "persona_id",
    "system_name_default",
    "voice_id",
    "persona_identity",
    "persona_character",
    "greeting_persona_line",
    "greeting_fallbacks",
)

# The pack keys that fill prompt slots — the renderer may consume EXACTLY these
# (A4 structural half of the D1 durable principle).
SLOT_KEYS: tuple[str, ...] = ("persona_identity", "persona_character", "greeting_persona_line")
