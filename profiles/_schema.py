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
# (companion vs robotics), but NOT wired to config globals in SB.2.1 — applying
# them would break behavior-neutrality:
#   persona  → SB.8 (persona pack). companion system_name='Kara' would clobber
#              config.DEFAULT_SYSTEM_NAME='Dog' (config.py:1166) → NOT neutral.
#   hardware → no config global today (whisper hardcoded in core/audio.py:249);
#              wired by a future hardware-tier cycle.
#   retention→ KARAOS_INSTANCE_MODE stays env-authoritative (config.py:1347);
#              the profile default_mode is documented intent SB.5 consumes.
VALID_HARDWARE_TIERS: tuple[str, ...] = ("dev_laptop", "jetson_orin", "server")
VALID_RETENTION_MODES: tuple[str, ...] = ("base", "personal")

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
        "system_name": {"kind": "scalar", "type": str},
        "persona_id":  {"kind": "scalar", "type": str},
    }},
    "hardware": {"kind": "section", "keys": {
        "tier": {"kind": "scalar", "type": str, "enum": VALID_HARDWARE_TIERS},
    }},
    "retention": {"kind": "section", "keys": {
        "default_mode": {"kind": "scalar", "type": str, "enum": VALID_RETENTION_MODES},
    }},
}
