"""
core/brain_agent.py — Autonomous multi-agent knowledge pipeline

Architecture:
  Raw transcript (conversation_log) → always-on, never modified
        ↓  event-triggered (notify after log_turn) + 2s fallback poll
  TriageAgent        — fast, no LLM, filters noise
        ↓  only processable turns pass
  ExtractionAgent    — LLM, extracts entities + facts (LLM decides attribute names)
        ↓  per-entity
  ContradictionAgent — LLM, checks new facts against stored facts
        ↓
  BrainDB (brain.db) — knowledge, schema_catalog, agent_log

All agents run async and are completely decoupled from the conversation pipeline.
The conversation never waits for the brain.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import asyncio
import datetime
import json
import math
import re
import sqlite3
import statistics
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx
import kuzu
import numpy as np
from rapidfuzz import fuzz as _rfuzz

from core.config import (
    BRAIN_DB_PATH,
    GRAPH_DB_PATH,
    DB_PATH,
    BRAIN_AGENT_POLL_INTERVAL,
    BRAIN_AGENT_CONTEXT_TURNS,
    BRAIN_AGENT_MIN_WORDS,
    ASSISTANT_TURN_EXTRACT_MIN_CHARS,
    PREF_AUTO_CONFIRM_THRESHOLD,
    PREF_ANALYSIS_TURNS,
    EXTRACT_MODEL, EXTRACT_BASE_URL, EXTRACT_API_KEY,
    EMBED_MODEL, EMBED_BASE_URL, EMBED_API_KEY, EMBED_MAX_RETRIES,
    EXTRACT_MAX_RETRIES,
    OLLAMA_URL,
    OLLAMA_MODEL,
    EMBED_TOP_K,
    EMBED_MIN_CONFIDENCE,
    SCHEMA_NORM_TRIGGER,
    SCHEMA_NORM_THRESHOLD,
    SCHEMA_NORM_AMBIGUOUS,
    SCHEMA_NORM_DISTINCT_FAMILIES,
    CONFIDENCE_BOOST,
    INTRA_PREF_TURN,
    INTRA_PREF_TURNS_LIMIT,
    DEFAULT_SYSTEM_NAME,
    DECAY_LAMBDA,
    MAX_RETROACTIVE_FACTS,
    RETRO_STALE_PENALTY,
    GRAPH_SCHEMA_VERSION,
    DREAM_PRUNE_FLOOR,
    DREAM_DECAY_WRITE_THRESHOLD,
    IDENTITY_SOFT_THRESHOLD,
    IDENTITY_ASK_THRESHOLD,
    IDENTITY_AUTO_THRESHOLD,
    BRIEFING_MIN_ABSENCE,
    BRIEFING_VISITOR_MIN_TURNS,
    MEMORY_SPARSE_THRESHOLD,
    PREF_DEDUP_THRESHOLD,
    PREF_BLACKLIST_PATTERNS,
    INSIGHT_MIN_TURNS, INSIGHT_MAX_TOKENS, EPISODE_TOPIC_MATCH_DAYS,
    MIN_PRESENCE_SESSIONS, ROUTINE_STD_THRESHOLD, PRESENCE_DEVIATION_HOURS,
    NUDGE_MIN_CONFIDENCE, NUDGE_FUZZY_MATCH_RATIO, NUDGE_EXPIRY_HOURS,
    CROSS_PERSON_MAX_NUDGES,
    WATCHDOG_INTERVAL, WATCHDOG_SILENT_OBS_SPIKE,
    WATCHDOG_UNUSUAL_HOUR_START, WATCHDOG_UNUSUAL_HOUR_END,
    KNOWLEDGE_MAX_ROWS, KNOWLEDGE_HARD_DELETE_AFTER_DAYS, PRESENCE_MAX_ROWS, EPISODE_MAX_ROWS,
    SOCIAL_MENTIONS_MAX_ROWS, WATCHDOG_MAX_AGE_DAYS,
    AGENT_LOG_MAX_AGE_DAYS, AGENT_LOG_MAX_ROWS, PATTERN_Q_MAX_AGE_DAYS,
    FRICTION_MIN_CONFIDENCE, PREDICATE_VOLATILITY_THRESHOLD, PREDICATE_CONFIDENCE_CAP,
    SAFETY_CRITICAL_ATTRIBUTE_PATTERNS, SHADOW_NAME_BLOCKLIST,
    PRIVACY_LEVELS,
    PRIVACY_LEVEL_DEFAULT,
    PRIVACY_LEVEL_STATIC_MAP,
    PRIVACY_CLASSIFIER_TIMEOUT_SECS,
    PRIVACY_CLASSIFIER_MAX_TOKENS,
    CORE_MEMORY_ENABLED,
    CORE_MEMORY_MAX_FACTS,
    CORE_MEMORY_MIN_CONFIDENCE,
    CORE_MEMORY_ATTRIBUTES,
)
from core.log_utils import _now_log_ts
from core.sanitize import wrap_user_input


# ── re-exported from core/brain_agent/_llm.py (P1.A1 SP-2) ───────────────────
from core.brain_agent._llm import (  # noqa: F401
    _parse_json,
    _parse_json_array,
    _valid_until,
    _call_llm_chat,
)


# ── re-exported from core/brain_agent/privacy.py (P1.A1 SP-2) ───────────────
from core.brain_agent.privacy import (  # noqa: F401
    _SAFETY_CRITICAL_ATTR_RES,
    _is_safety_critical_attribute,
    _assert_valid_privacy_level,
    _privacy_classifier_cache,
    _PRIVACY_CLASSIFIER_SYSTEM,
    _ask_privacy_llm,
    _classify_privacy_level,
    _visibility_clause,
)


# ── re-exported from core/brain_agent/context.py (P1.A1 SP-2) ───────────────
from core.brain_agent.context import (  # noqa: F401
    _decayed_confidence,
    _format_context_lines,
    _cosine_similarity,
    _cosine_similarity_matrix,
)




# ── Prior AI claim detection ───────────────────────────────────────────────────











# Shared geometry helper — maps a normalized bbox center to a zone label.
# Consumed by pipeline's silent-observation path (the YOLO spatial-memory
# consumer was removed in SB.1 D1; this helper is NOT YOLO-specific).
def _infer_location_zone(bbox_cx: float, bbox_cy: float) -> str:
    """Map normalized center coordinates to a human-readable location zone.

    bbox_cx, bbox_cy are in [0, 1] (0 = left/top, 1 = right/bottom).
    Combines horizontal position with a vertical qualifier for top/bottom thirds.
    """
    if bbox_cx < 0.33:
        h = "left side"
    elif bbox_cx < 0.67:
        h = "center"
    else:
        h = "right side"

    if bbox_cy < 0.30:
        return f"{h} (upper area)"
    if bbox_cy > 0.70:
        return f"{h} (floor level)"
    return h




# ── re-exported from core/brain_agent/agents/triage.py (P1.A1 SP-2) ──
from core.brain_agent.agents.triage import (  # noqa: F401
    _NOISE_WORDS,
    TriageAgent,
)


# ── re-exported from core/brain_agent/agents/extraction.py (P1.A1 SP-2) ──
from core.brain_agent.agents.extraction import (  # noqa: F401
    Extraction,
    _VALID_ACTION_TYPES,
    _ASSISTANT_ROOM_EXTRACT_SYSTEM,
    _fan_out_to_participants,
    _EXTRACT_SYSTEM,
    _EXTRACT_USER,
    _PRIOR_CLAIM_BLOCK,
    _PRIOR_ASSISTANT_BLOCK,
    ExtractionAgent,
)


# ── re-exported from core/brain_agent/agents/contradiction.py (P1.A1 SP-2) ──
from core.brain_agent.agents.contradiction import (  # noqa: F401
    _CONTRA_PROMPT,
    _STALENESS_PROMPT,
    ContradictionAgent,
)


# ── re-exported from core/brain_agent/agents/prefs.py (P1.A1 SP-2) ──
from core.brain_agent.agents.prefs import (  # noqa: F401
    _VALID_PREF_TYPES,
    _PREF_SYSTEM,
    _PREF_USER,
    PromptPrefAgent,
    _FRICTION_SYSTEM,
    _FRICTION_USER,
    FrictionDetectionAgent,
)


# ── re-exported from core/brain_agent/agents/household.py (P1.A1 SP-2) ──
from core.brain_agent.agents.household import (  # noqa: F401
    HouseholdExtractionAgent,
)


# ── re-exported from core/brain_agent/agents/schema.py (P1.A1 SP-2) ──
from core.brain_agent.agents.schema import (  # noqa: F401
    _distinct_schema_families,
    SchemaNormAgent,
)


# ── re-exported from core/brain_agent/agents/embedding.py (P1.A1 SP-2) ──
from core.brain_agent.agents.embedding import (  # noqa: F401
    EmbeddingAgent,
)


# ── re-exported from core/brain_agent/agents/social.py (P1.A1 SP-2) ──
from core.brain_agent.agents.social import (  # noqa: F401
    SocialGraphAgent,
    _IDENTITY_STOP,
    IdentityAgent,
)


# ── re-exported from core/brain_agent/agents/briefing.py (P1.A1 SP-2) ──
from core.brain_agent.agents.briefing import (  # noqa: F401
    BriefingAgent,
    ConversationInsightAgent,
)


# ── re-exported from core/brain_agent/agents/routine.py (P1.A1 SP-2) ──
from core.brain_agent.agents.routine import (  # noqa: F401
    RoutineAgent,
)


# ── re-exported from core/brain_agent/agents/nudge.py (P1.A1 SP-2) ──
from core.brain_agent.agents.nudge import (  # noqa: F401
    ProactiveNudgeAgent,
)


# ── re-exported from core/brain_agent/agents/watchdog.py (P1.A1 SP-2) ──
from core.brain_agent.agents.watchdog import (  # noqa: F401
    WatchdogAgent,
)


# ── BrainDB ────────────────────────────────────────────────────────────────────

# ── re-exported from core/brain_agent/memory/store.py (P1.A1 SP-2 SP-3) ──
from core.brain_agent.memory.store import (  # noqa: F401
    BrainDB,
    _escalate_pref,
)


# ── re-exported from core/brain_agent/memory/graph.py (P1.A1 SP-2) ──────────
from core.brain_agent.memory.graph import GraphDB  # noqa: F401


# ── BrainOrchestrator ──────────────────────────────────────────────────────────

# ── re-exported from core/brain_agent/orchestrator.py (P1.A1 SP-2 SP-3) ──
from core.brain_agent.orchestrator import (  # noqa: F401
    BrainOrchestrator,
    _is_phantom_name,
    _get_prior_ai_claim,
    _get_prior_assistant_turn,
    _classify_user_reaction,
    _RECALL_SIGNALS,
    _CONFIRM_SIGNALS,
    _DENY_SIGNALS,
)
