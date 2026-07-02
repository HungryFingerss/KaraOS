# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""SB.2.1 — the profile override contract (the schema).

Declarative data: which keys a profile MAY override, their types/enums, the
named LLM provider bundles, and the ``features.*`` → ``config.*_ENABLED`` map.
Profiles are YAML *data*; this schema is *code* (Phase-0 §8.1 ruling).

Pure: stdlib only — imports NOTHING from ``core`` (the loader that consumes this
must stay config-free; this module is even stricter). PI-1: the LLM-provider
derivation ROOTS (``TOGETHER_API_KEY``/``TOGETHER_BASE_URL``) are NOT in the
schema — profiles override only at the per-role LEAF, so a root-override /
stale-leaf desync is impossible by construction.
"""

from __future__ import annotations

# ── LLM-provider axis (PI-1: leaf-level only) ─────────────────────────────────
# Per-role leaf = {model, base_url, api_key_env}. ``api_key_env`` is the NAME of
# the env var holding the secret (resolved at apply-time in config.py via
# ``os.getenv(name, "").strip()`` — PI-C); secrets NEVER live in the YAML.
LLM_ROLES: tuple[str, ...] = ("chat", "extract", "embed", "vision")
LLM_LEAF_KEYS: tuple[str, ...] = ("model", "base_url", "api_key_env")

# Named provider bundles (defined, not flipped). ``cloud`` == today's Together-70B
# leaves verbatim → companion selects it → byte-identical → behavior-neutral.
# ``local-orin`` / ``local-dev`` are the researched local rungs: present so the
# axis is real, but companion does NOT select them (the deferred local-first flip
# at the Orin move is a later one-line companion.yaml change + its own canary).
PROVIDER_BUNDLES: "dict[str, dict[str, dict[str, str]]]" = {
    # cloud — today's exact role-based config (core/config.py:334-356).
    "cloud": {
        "chat":    {"model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
                    "base_url": "https://api.together.xyz/v1",
                    "api_key_env": "TOGETHER_API_KEY"},
        "extract": {"model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
                    "base_url": "https://api.together.xyz/v1",
                    "api_key_env": "TOGETHER_API_KEY"},
        "embed":   {"model": "intfloat/multilingual-e5-large-instruct",
                    "base_url": "https://api.together.xyz/v1",
                    "api_key_env": "TOGETHER_API_KEY"},
        "vision":  {"model": "Qwen/Qwen3-VL-8B-Instruct",
                    "base_url": "https://api.together.xyz/v1",
                    "api_key_env": "TOGETHER_API_KEY"},
    },
    # local-orin — the researched production rung: Gemma-4-27B onboard via
    # Ollama's OpenAI-compatible endpoint (mirrors core/config.py OLLAMA_URL),
    # keyless. Defined; companion does NOT select it. (Flipped to companion's
    # default at the Orin move per Jagan — a later cycle.)
    "local-orin": {
        "chat":    {"model": "gemma-4-27b",
                    "base_url": "http://localhost:11434/v1", "api_key_env": ""},
        "extract": {"model": "gemma-4-27b",
                    "base_url": "http://localhost:11434/v1", "api_key_env": ""},
        "embed":   {"model": "intfloat/multilingual-e5-large-instruct",
                    "base_url": "http://localhost:11434/v1", "api_key_env": ""},
        "vision":  {"model": "gemma-4-27b",
                    "base_url": "http://localhost:11434/v1", "api_key_env": ""},
    },
    # local-dev — documented placeholder for the 8GB laptop rung (Qwen3-4B /
    # Gemma-4-E4B per §8.3). Companion uses cloud; this rung matters only for
    # local-on-laptop dev.
    "local-dev": {
        "chat":    {"model": "qwen3-4b",
                    "base_url": "http://localhost:11434/v1", "api_key_env": ""},
        "extract": {"model": "qwen3-4b",
                    "base_url": "http://localhost:11434/v1", "api_key_env": ""},
        "embed":   {"model": "intfloat/multilingual-e5-large-instruct",
                    "base_url": "http://localhost:11434/v1", "api_key_env": ""},
        "vision":  {"model": "qwen3-4b",
                    "base_url": "http://localhost:11434/v1", "api_key_env": ""},
    },
}
VALID_PROVIDERS: tuple[str, ...] = tuple(PROVIDER_BUNDLES)  # cloud / local-orin / local-dev

# Cloud-health timing axis — the CloudState-machine timings (optional override).
CLOUD_TIMING_MAP: "dict[str, str]" = {
    "offline_timeout": "CLOUD_OFFLINE_TIMEOUT",  # core/config.py:359
    "retry_interval":  "CLOUD_RETRY_INTERVAL",   # core/config.py:360
}

# ── Feature-toggle axis (§3.3) ────────────────────────────────────────────────
# Each ``features.*`` key MUST map 1:1 to an existing ``config.*_ENABLED`` flag
# (the T7 guardrail). SB.2.1 ships the 2 clean, semantically-exact mappings;
# the 6 flagless concepts (greeting/kairos/dream/household/social_graph/
# persona_companion) + the ~14 relationship BLOCK-flags arrive in SB.2.2 (they
# need new flags / deep wiring + the block-vs-generation decision). This map is
# the single source of truth for BOTH apply (which global to write) and T7.
FEATURE_FLAG_MAP: "dict[str, str]" = {
    "emotion":     "EMOTION_ENABLED",      # core/config.py:1413
    "tier_memory": "CORE_MEMORY_ENABLED",  # core/config.py:674 (core-vs-archive tier)
}

# ── Declared-only axes (hooks) ────────────────────────────────────────────────
# Present in the schema + the YAMLs so the files validate + differentiate
# (companion vs robotics), but NOT wired to config globals — applying them
# would break behavior-neutrality:
#   hardware → no config global today (whisper hardcoded in core/audio.py:249);
#              wired by a future hardware-tier cycle.
# persona LEFT this set at SB.8: `persona.persona_id` now selects a
# persona/<id>.yaml pack at apply-at-load (core/persona_loader.py). The old
# decorative `system_name` key was REMOVED from the persona section — the
# pack's `system_name_default` is the single source, and a stray profile-side
# name now fails loud instead of sitting as a latent Kara-clobber trap
# (SB.8 §0 catch + PI-A).
VALID_HARDWARE_TIERS: tuple[str, ...] = ("dev_laptop", "jetson_orin", "server")

# ── SB.5 — identity axis (ACTIVE, applied at config-load — NOT declared-only) ──
# Two-axis identity model:
#   enrollment_mode → config.ENROLLMENT_MODE (how long an identity stays enrolled)
#   retention_mode  → config.RETENTION_MODE  (how long that identity's data lives)
# Both tuples are ordered LONGEST-LIVED → SHORTEST-LIVED. That order is
# LOAD-BEARING: the loader's coherence validator derives the lifetime rank from
# the tuple index (rank = len - index), so reordering changes the 9-cell
# semantics. Coherence rule (SB.5 §3): a retention lifetime must not outlive the
# enrollment lifetime that grants it. Orthogonal to env KARAOS_INSTANCE_MODE
# (config.py:1347), which stays the separate base/personal instance axis.
VALID_ENROLLMENT_MODES: tuple[str, ...] = ("persistent", "transient", "none")
VALID_RETENTION_LIFETIMES: tuple[str, ...] = ("durable", "session_only", "ephemeral")
# Fail-closed defaults for an absent KEY *within* a declared `identity` section
# (SB.5 Q2 Reading B). An absent identity SECTION instead resolves to the config
# base defaults (persistent/durable) — the loader simply doesn't key it.
FAILCLOSED_ENROLLMENT_MODE: str = "transient"
FAILCLOSED_RETENTION_LIFETIME: str = "ephemeral"

# ── The schema (the override contract the loader validates against) ────────────
# A profile MAY declare any subset of these sections/keys; every key it declares
# is validated (unknown section / unknown key / bad type / bad enum → fail-loud).
SCHEMA: dict = {
    "profile":   {"kind": "scalar", "type": str},
    "llm": {"kind": "section", "keys": {
        "provider": {"kind": "scalar", "type": str, "enum": VALID_PROVIDERS},
        "chat":     {"kind": "leaf"},
        "extract":  {"kind": "leaf"},
        "embed":    {"kind": "leaf"},
        "vision":   {"kind": "leaf"},
        "cloud":    {"kind": "cloud_timing"},
    }},
    "features": {"kind": "section", "keys": {
        feat: {"kind": "scalar", "type": bool} for feat in FEATURE_FLAG_MAP
    }},
    "persona": {"kind": "section", "keys": {
        # SB.8: reference-only — the pack (persona/<persona_id>.yaml) is the
        # single source for name/voice/prompt-flavor. `system_name` was
        # deliberately REMOVED: a profile-side name would silently clobber
        # the pack's system_name_default; now it fails loud as unknown-key.
        "persona_id":  {"kind": "scalar", "type": str},
    }},
    "hardware": {"kind": "section", "keys": {
        "tier": {"kind": "scalar", "type": str, "enum": VALID_HARDWARE_TIERS},
    }},
    "identity": {"kind": "section", "keys": {
        "enrollment_mode": {"kind": "scalar", "type": str, "enum": VALID_ENROLLMENT_MODES},
        "retention_mode":  {"kind": "scalar", "type": str, "enum": VALID_RETENTION_LIFETIMES},
    }},
    # SB.3 — agent-membership axis. Value is a bundle-shorthand string
    # (∈ AGENT_BUNDLES, e.g. "companion") OR a list[str] of AGENT_REGISTRY keys.
    # Validated by the loader's _check_agent_select against profiles/_registry.py.
    "agents": {"kind": "agent_select"},
    # SB.4.1 — prompt-block-membership axis. Value is a bundle-shorthand string
    # (∈ BLOCK_BUNDLES, e.g. "companion") OR a list[str] of BLOCK_REGISTRY keys.
    # Validated by the loader's _check_block_select against profiles/_blocks.py;
    # closure (MANDATORY_BLOCKS ⊆ active) enforced by _validate_block_closure.
    "blocks": {"kind": "block_select"},
}
