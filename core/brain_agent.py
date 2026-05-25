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


# ── Shared utilities ───────────────────────────────────────────────────────────

def _parse_json(raw: str) -> dict | None:
    """Parse JSON with automatic salvage of the first {…} block on failure.

    Returns a dict on success, or None on any failure.  P0.12: also returns
    None when `json.loads` succeeds but produces a non-dict JSON value
    (e.g. raw input `"0"`, `"[1,2,3]"`, `"true"`).  Type annotation said
    `dict | None` but the pre-P0.12 implementation returned whatever
    json.loads returned — Hypothesis surfaced the contract violation
    (falsifying input: `raw="0"` → returned `int(0)`).  Callers do
    `parsed.get(...)` assuming dict; a non-dict return would raise
    AttributeError at runtime.

    Also catches `RecursionError` from pathological deeply-nested JSON.
    """
    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, RecursionError, ValueError):
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                result = json.loads(raw[start:end])
            except (json.JSONDecodeError, RecursionError, ValueError):
                return None
        else:
            return None
    return result if isinstance(result, dict) else None


def _parse_json_array(raw: str) -> list | None:
    """Parse JSON expecting a top-level array.  Returns list OR None.

    Sibling to ``_parse_json`` (P0.12.1 follow-up): some agent prompts
    legitimately expect a top-level JSON array (e.g. SocialGraphAgent's
    "list of person mentions") even when ``response_format={"type":
    "json_object"}`` is set — practical LLMs occasionally ignore the
    object-only constraint and return a raw array.  Pre-P0.12, the
    permissive ``_parse_json`` returned the list and the caller's
    ``isinstance(data, list)`` branch caught it.  P0.12 narrowed
    ``_parse_json`` to ``dict | None`` for type-contract correctness;
    this sibling restores explicit list-shape parsing for the small set
    of call sites that need it WITHOUT re-broadening the main parser.

    Same brace-salvage discipline but with ``[``/``]`` markers.  Catches
    the same DoS exceptions as ``_parse_json``.
    """
    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, RecursionError, ValueError):
        start = raw.find("[")
        end   = raw.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                result = json.loads(raw[start:end])
            except (json.JSONDecodeError, RecursionError, ValueError):
                return None
        else:
            return None
    return result if isinstance(result, list) else None


def _valid_until(is_temporal: bool, valid_for_hours: float | None, now: float) -> float | None:
    """Compute expiry timestamp for a temporal fact, or None if permanent."""
    if is_temporal and valid_for_hours:
        return now + valid_for_hours * 3600
    return None


# ── Bugs J + M (2026-04-20 live run) — unified LLM retry helper ───────────────
async def _call_llm_chat(
    http:          "httpx.AsyncClient",
    messages:      list[dict],
    *,
    agent_name:    str,
    max_tokens:    int             = 400,
    temperature:   float           = 0.1,
    response_format: dict | None   = None,
    timeout:       float           = 15.0,
    max_retries:   int | None      = None,
    turn_id:       int | None      = None,
) -> str | None:
    """Shared LLM chat call with retry + diagnostic logging.

    Session 69 (Bugs J + M): several agents (PromptPref, SocialGraph,
    Household, Insight, FrictionDetection, Pattern) used ad-hoc
    ``try/except Exception:`` wrappers around ``http.post``. Two failure
    modes leaked through:

      * **Bug M** (silent ReadTimeout): ``str(httpx.ReadTimeout)`` is often
        empty, producing ``[AgentName] error: ReadTimeout:`` with no detail.
      * **Bug J** (KeyError on 'choices'): provider error-shaped JSON lacks
        ``choices``, the agent catches the KeyError silently, and the turn
        is dropped without anyone noticing.

    This helper unifies the pattern from ``ExtractionAgent`` (Session 65) and
    ``EmbeddingAgent`` (Session 24 A8): retry transient errors with
    exponential backoff, propagate 4xx without retry (masks real config bugs
    if we retry), validate the response shape explicitly, and always log with
    enough detail to diagnose.

    Returns the ``choices[0].message.content`` string on success, or ``None``
    on any failure (already logged). Callers decide whether ``None`` is
    recoverable for their domain.
    """
    if not EXTRACT_API_KEY:
        return None
    retries = EXTRACT_MAX_RETRIES if max_retries is None else max_retries
    body: dict = {
        "model":       EXTRACT_MODEL,
        "messages":    messages,
        "temperature": temperature,
        "max_tokens":  max_tokens,
    }
    if response_format is not None:
        body["response_format"] = response_format
    _ctx  = f" (turn {turn_id})" if turn_id is not None else ""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await http.post(
                f"{EXTRACT_BASE_URL}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {EXTRACT_API_KEY}"},
                timeout=timeout,
            )
            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                # 4xx (except 429): not transient, retrying wastes budget and
                # hides real config bugs. Log and propagate None.
                print(f"[{agent_name}] HTTP {resp.status_code}{_ctx}: {resp.text[:200]}")
                return None
            resp.raise_for_status()
            data = resp.json()
            # Bug J: provider error-shaped responses lack 'choices'. Don't let
            # the KeyError become a silent except — surface it.
            if "choices" not in data or not data["choices"]:
                print(f"[{agent_name}] LLM response missing 'choices'{_ctx}: {str(data)[:200]}")
                return None
            return data["choices"][0]["message"]["content"]
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.NetworkError) as e:
            last_exc = e
        except httpx.HTTPStatusError as e:
            # 5xx — transient on the provider side; retry.
            last_exc = e
        except Exception as e:
            # Non-HTTP / non-network (JSON parse, unexpected shape). Not
            # retryable — log with context and bail.
            detail = str(e) or "(no detail)"
            print(f"[{agent_name}] {type(e).__name__}{_ctx}: {detail}")
            return None
        if attempt < retries:
            await asyncio.sleep(2 ** attempt)
    # All retries exhausted — log with context since str(ReadTimeout) is often blank.
    detail = str(last_exc) if last_exc and str(last_exc) else "(no detail)"
    print(
        f"[{agent_name}] {type(last_exc).__name__ if last_exc else 'Unknown'} after "
        f"{retries + 1} attempts{_ctx}: {detail}"
    )
    return None


_SAFETY_CRITICAL_ATTR_RES: tuple = tuple(
    re.compile(p) for p in SAFETY_CRITICAL_ATTRIBUTE_PATTERNS
)


def _is_phantom_name(
    candidate: str,
    known_names: "list[str]",
    *,
    jw_threshold: float = 0.85,
) -> "str | None":
    """Session 114 Part 2 — phantom-person fuzzy match.

    Returns the matched ``known_name`` if ``candidate`` is plausibly a
    STT-mangled form of an existing name (phonetic via jellyfish
    Double-Metaphone OR Jaro-Winkler similarity ≥ ``jw_threshold``).
    Returns None when no match — caller should proceed with normal
    shadow insertion.

    Phonetic match uses metaphone codes (already a dep from
    Session 41 G4). Jaro-Winkler catches typo-class matches that share
    no phonetic code (e.g. "Lexie" vs "Lexi" — same Metaphone code, but
    short prefixes drift cheaply across vowel changes).
    """
    if not candidate or not known_names:
        return None
    try:
        import jellyfish as _jelly
    except Exception:
        return None
    cand = candidate.strip()
    if not cand:
        return None
    cand_lc = cand.lower()
    cand_meta = _jelly.metaphone(cand) or ""
    best_match = None
    for kn in known_names:
        if not kn:
            continue
        kn_lc = kn.strip().lower()
        if not kn_lc:
            continue
        # Exact / case-insensitive direct hit always wins.
        if kn_lc == cand_lc:
            return kn
        # Phonetic match.
        if cand_meta and _jelly.metaphone(kn) == cand_meta:
            return kn
        # Jaro-Winkler — captures typo-class drift even when phonetic
        # codes diverge slightly.
        try:
            jw = _jelly.jaro_winkler_similarity(cand_lc, kn_lc)
        except Exception:
            jw = 0.0
        if jw >= jw_threshold:
            best_match = kn
            # Don't break — exact / phonetic match further in the list
            # would still take precedence. But Jaro-Winkler is the
            # weakest signal; use only as fallback.
    return best_match


def _is_safety_critical_attribute(attribute: str) -> bool:
    """Session 105 Bug N — does the given attribute name match any
    safety-critical pattern? These attributes (expressed_suicidal_thoughts,
    mentioned_self_harm, etc.) must never be overwritten by the
    ContradictionAgent — they accumulate as timestamped history so a
    crisis disclosure stays on record even if the user's momentary mood
    shifts to something neutral afterwards.

    Compiled-regex cache (module-level) so each check is a constant-time
    precompiled match rather than re-parsing the pattern list per call.
    """
    if not attribute:
        return False
    return any(r.match(attribute) for r in _SAFETY_CRITICAL_ATTR_RES)


# ── P0.S4 D1 — privacy-level write-path validation ────────────────────────────
def _assert_valid_privacy_level(value: str, context: str) -> None:
    """Reject writes carrying a `privacy_level` outside `PRIVACY_LEVELS`.

    Called at every write-path boundary that persists a tier value: brain.db
    via `BrainDB.store_knowledge` (line ~1186) and Kuzu via
    `GraphDB._create_edge` (line ~3567). The empty/invalid case is
    programmer-error (Session 95 3A.4.5 legacy "private" reaching a writer
    means an extraction-agent path missed the migration; the visibility
    clause has no predicate matching it, so silently accepting it would
    write data that's structurally invisible to every retrieval site).

    Fail-loud disposition: raise `ValueError` naming the field, the
    constraint constant the operator must consult, and the offending value
    verbatim. Caller path is wrapped in `try/except Exception` at
    `BrainOrchestrator._poll_once` (lines ~7365-7379) and at
    `pipeline.py::_emotion_process_background`, so the raise logs the full
    traceback + continues the background task — does NOT crash the pipeline.

    Spec: tests/p0_s4_plan_v1.md §1.P4 (locked exact substrings).
    """
    if value not in PRIVACY_LEVELS:
        raise ValueError(
            f"Invalid privacy_level={value!r} at {context}. "
            f"Must be a member of PRIVACY_LEVELS (config.py): "
            f"{sorted(PRIVACY_LEVELS)}. If the legacy 2-tier name "
            f"'private' surfaced, this is a Session 95 3A.4.5 migration "
            f"regression — re-classify via _classify_privacy_level or "
            f"explicitly set privacy_level='personal' at the agent boundary."
        )


# ── VISION_ROADMAP P3.2 / Session 95 3A.2 — privacy-level classifier ──────────
# Session 95 3A.4.5 — the legacy `_privacy_level(attribute)` 2-tier helper
# was deleted in favor of `_classify_privacy_level` below. Its only caller
# was `BrainDB.store_knowledge`, which now reads `Extraction.privacy_level`
# directly — agents classify at construction time (Option B architecture).
# Tiered privacy classifier for facts heading into BrainDB. Callers use the
# result to populate a `privacy_level` column (3A.3 wire-in), which the
# retrieval site (P3.3 visibility clause) reads to suppress cross-person leaks.
#
# Layered lookup (fastest first):
#   1. Static map — O(1) dict check, zero I/O. Most facts hit this (reviewer's
#      S95 3A.1 pre-classified the common attributes).
#   2. Process-lifetime cache — LLM classifications persist until restart so
#      the same novel attribute never pays twice. Keyed by attribute alone
#      (not (entity, attribute)): the tier is a property of WHAT the fact is,
#      not WHOSE fact it is. "health_condition" is personal for everyone.
#   3. LLM fallback — bounded retry via `_call_llm_chat`, strict-schema JSON
#      response, fail-closed to PRIVACY_LEVEL_DEFAULT on any failure. Failed
#      classifications are NOT cached — a transient provider blip must not
#      permanently pin a novel attribute to "personal".
_privacy_classifier_cache: dict[str, str] = {}

_PRIVACY_CLASSIFIER_SYSTEM = (
    "You are a privacy-level classifier. Given one fact (entity, attribute, "
    "value), output its privacy tier as JSON.\n\n"
    "TIERS:\n"
    "  public      — anyone in the household can know (names, nationality,\n"
    "                public relationships like \"coworker\")\n"
    "  household   — best_friend (household owner) should know, but not\n"
    "                visitors (presence, visit topics, preferred_ai_name,\n"
    "                relationships revealing owner's social graph)\n"
    "  personal    — only the fact's owner should see (specific locations,\n"
    "                medical, moods, confidential concerns, dietary\n"
    "                preferences, private opinions)\n"
    "  system_only — internal/mechanical data, never surfaced to users\n"
    "                (embeddings, credits, diagnostics)\n\n"
    "RULES:\n"
    "  1. When in doubt, choose personal (fail-closed).\n"
    "  2. Facts revealing owner's social graph (relationships to others) "
    "→ household.\n"
    "  3. Facts that could embarrass or harm if shared → personal.\n"
    "  4. Mechanical/non-user-facing → system_only.\n"
    "  5. Name-level facts (the person IS X) → public; location/role "
    "granularity may be personal.\n\n"
    "EXAMPLES:\n"
    '  {entity: "Lexi", attribute: "name", value: "Lexi"}\n'
    '    → {"level": "public", "reasoning": "person\'s name is not sensitive"}\n'
    '  {entity: "Lexi", attribute: "relationship_to_jagan", value: "classmate"}\n'
    '    → {"level": "household", "reasoning": "social graph — owner sees, others don\'t"}\n'
    '  {entity: "Jagan", attribute: "confided_worry", value: "losing job"}\n'
    '    → {"level": "personal", "reasoning": "sensitive confidence — never share"}\n'
    '  {entity: "Lexi", attribute: "visited_household", value: "true"}\n'
    '    → {"level": "household", "reasoning": "presence fact — best_friend visibility"}\n'
    '  {entity: "stranger_abc", attribute: "voice_embedding_hash", value: "f4a8..."}\n'
    '    → {"level": "system_only", "reasoning": "mechanical data, not user-facing"}\n\n'
    "Output ONLY the JSON object, no other text."
)


async def _ask_privacy_llm(
    entity:    str,
    attribute: str,
    value:     str,
    *,
    http:      "httpx.AsyncClient",
    turn_id:   int | None = None,
) -> str | None:
    """Ask the LLM to classify a single (entity, attribute, value) fact.

    Returns a valid PRIVACY_LEVELS member on success, None on timeout,
    malformed JSON, invalid level, or any `_call_llm_chat` failure. The
    caller (`_classify_privacy_level`) interprets None as "fail-closed" —
    do NOT cache, return PRIVACY_LEVEL_DEFAULT.
    """
    user_msg = (
        f"Classify:\n"
        f"  entity: {entity}\n"
        f"  attribute: {attribute}\n"
        f"  value: {value}"
    )
    raw = await _call_llm_chat(
        http,
        messages=[
            {"role": "system", "content": _PRIVACY_CLASSIFIER_SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
        agent_name="PrivacyClassifier",
        max_tokens=PRIVACY_CLASSIFIER_MAX_TOKENS,
        temperature=0.1,
        response_format={"type": "json_object"},
        timeout=PRIVACY_CLASSIFIER_TIMEOUT_SECS,
        turn_id=turn_id,
    )
    if not raw:
        return None
    parsed = _parse_json(raw)
    if not parsed or not isinstance(parsed, dict):
        print(f"[PrivacyClassifier] malformed JSON for {attribute!r}: {raw[:120]!r}")
        return None
    level = parsed.get("level")
    if not isinstance(level, str) or level not in PRIVACY_LEVELS:
        print(f"[PrivacyClassifier] invalid level for {attribute!r}: {level!r}")
        return None
    return level


async def _classify_privacy_level(
    entity:    str,
    attribute: str,
    value:     str,
    *,
    http:      "httpx.AsyncClient | None" = None,
    turn_id:   int | None = None,
) -> str:
    """Return the privacy tier for a fact. Fails closed to PRIVACY_LEVEL_DEFAULT.

    Call order (fastest first): static map → process cache → LLM.
    On LLM failure (timeout, malformed JSON, invalid tier), return the
    default WITHOUT caching so a transient blip doesn't pin the attribute
    forever. On LLM success, cache the classification so subsequent facts
    with the same attribute skip the LLM entirely.
    """
    # Session 116 P1 #3 — auditability: log which path classified the
    # attribute (static map vs. cache vs. LLM vs. fail-closed default).
    # The path is the audit signal: an outside reviewer can see whether
    # a tier decision came from a hand-curated rule (static_map),
    # cheap reuse of a prior LLM call (cache), a fresh LLM judgment
    # (llm_<level>), or a safety-fallback when the LLM was unavailable
    # or returned malformed output (default_fallback).
    if attribute in PRIVACY_LEVEL_STATIC_MAP:
        level = PRIVACY_LEVEL_STATIC_MAP[attribute]
        print(f"[Privacy] _classify_privacy_level({attribute!r}) → {level} (static_map)")
        return level
    if attribute in _privacy_classifier_cache:
        level = _privacy_classifier_cache[attribute]
        print(f"[Privacy] _classify_privacy_level({attribute!r}) → {level} (cache)")
        return level
    if http is None:
        # No HTTP client supplied — caller didn't provide an LLM path; cannot
        # classify a novel attribute. Fail-closed without caching.
        print(
            f"[Privacy] _classify_privacy_level({attribute!r}) "
            f"→ {PRIVACY_LEVEL_DEFAULT} (default_fallback: no http client)"
        )
        return PRIVACY_LEVEL_DEFAULT
    level = await _ask_privacy_llm(entity, attribute, value, http=http, turn_id=turn_id)
    if level not in PRIVACY_LEVELS:
        print(
            f"[Privacy] _classify_privacy_level({attribute!r}) "
            f"→ {PRIVACY_LEVEL_DEFAULT} (default_fallback: invalid LLM response)"
        )
        return PRIVACY_LEVEL_DEFAULT
    _privacy_classifier_cache[attribute] = level
    print(f"[Privacy] _classify_privacy_level({attribute!r}) → {level} (llm)")
    return level


def _visibility_clause(
    requester_pid:  str,
    best_friend_id: "str | None" = None,
) -> tuple[str, list]:
    """Return (WHERE clause, params) for privacy-filtered knowledge SELECT.

    Single source of truth for the visibility policy. Callers compose it into
    their own SELECT with AND::

        base_where = "entity = ? AND invalidated_at IS NULL"
        vis_where, vis_params = _visibility_clause(requester_pid, best_friend_id)
        full_where = f"{base_where} AND ({vis_where})"
        full_params = [entity, *vis_params]

    **Session 95 3A.4.6 — simplified owner-access model (user's clarification):**
    best_friend (the household owner) has UNCONDITIONAL access to every fact
    the system stores, regardless of whose it is. The only tier they can't
    see is `system_only` (mechanical data — embeddings, credits — not useful
    in conversation anyway). This replaces the earlier three-tier-for-owner
    model because it's what the user actually wants: "owner sees everything
    in their home" is a simpler invariant than "owner sees public + household
    + their own personal." Household tier becomes meaningful only as "visitors
    can't see this" — it's everyone-else's exclusion tier, not the owner's
    special tier.

    Two branches:
      - best_friend: ``privacy_level != 'system_only'`` — sees all 3 visible
        tiers (public + personal for all persons + household) via a single
        exclusion predicate. Zero params.
      - non-best-friend: ``public`` OR (``personal`` owned by requester). Can't
        see other people's personal, can't see household, can't see system_only.
        One param: `requester_pid`.

    Clause is wrapped in parens so the whole expression composes safely under
    an outer AND — caller's ``f"AND ({clause})"`` produces double-paren nesting,
    which is correct.
    """
    # Best_friend (owner): unconditional access except system_only.
    if best_friend_id and requester_pid == best_friend_id:
        return ("(privacy_level != 'system_only')", [])

    # Non-best-friend: public + own personal. No household, no cross-person
    # personal, no system_only.
    clauses = [
        "privacy_level = 'public'",
        "privacy_level = 'personal' AND person_id = ?",
    ]
    return (" OR ".join(f"({c})" for c in clauses), [requester_pid])


def _decayed_confidence(
    stored_confidence: float,
    valid_at: float | None,
    last_confirmed_at: float | None,
    λ: float = DECAY_LAMBDA,
) -> float:
    """Non-destructive time-decayed confidence. Read-time only — never mutates storage.

    Decay anchor: last_confirmed_at if the fact was ever confirmed, else valid_at.
    λ=0.002 → half-life ≈347 days. At stored_conf=0.95, drops below 0.60 after ~235 days.
    A single user confirmation resets the anchor to today, giving the fact a full fresh window.
    """
    anchor = last_confirmed_at if last_confirmed_at else (valid_at if valid_at else time.time())
    days = max(0.0, (time.time() - anchor) / 86400)
    return stored_confidence * math.exp(-λ * days)


def _format_context_lines(entity_name: str, facts: list[dict]) -> str | None:
    """Format a list of fact dicts for LLM injection.

    Applies time-decay using valid_at + last_confirmed_at from each fact dict.
    Temporal facts show a human-readable expiry countdown.
    Returns None if every fact is filtered out after decay.
    """
    now = time.time()
    lines = []
    for f in facts:
        eff_conf = _decayed_confidence(
            f["confidence"],
            f.get("valid_at"),
            f.get("last_confirmed_at"),
        )
        if eff_conf < EMBED_MIN_CONFIDENCE:
            continue
        label  = f["attribute"].replace("_", " ")
        suffix = ""
        if f.get("is_temporal") and f.get("valid_until"):
            secs_left = f["valid_until"] - now
            if secs_left > 0:
                if secs_left < 3600:
                    suffix = f" (expires in {int(secs_left / 60)}m)"
                else:
                    suffix = f" (expires in {int(secs_left / 3600)}h)"
        if eff_conf < 0.7:
            suffix += " (uncertain)"
        lines.append(f"- {label}: {f['value']}{suffix}")
    if not lines:
        return None
    return f"What you know about {entity_name}:\n" + "\n".join(lines)


def _cosine_similarity(query: list[float], docs: list[list[float]]) -> list[float]:
    """Cosine similarity between a query vector and a list of doc vectors.

    Both query and docs must already be L2-normalized (multilingual-e5 returns
    normalized vectors). Returns a flat list of scores in the same order as docs.
    """
    q = np.array(query, dtype=np.float32)
    D = np.array(docs,  dtype=np.float32)
    return (D @ q).tolist()


def _cosine_similarity_matrix(vecs: list[list[float]]) -> np.ndarray:
    """Full n×n cosine similarity matrix for a list of L2-normalized vectors."""
    M = np.array(vecs, dtype=np.float32)
    return M @ M.T


# ── Prior AI claim detection ───────────────────────────────────────────────────

_RECALL_SIGNALS = (
    "i remember", "you mentioned", "you said", "last time",
    "you told me", "i recall", "as you said", "you've told",
)

_CONFIRM_SIGNALS = frozenset({
    "yes", "yeah", "yep", "correct", "exactly", "right",
    "true", "indeed", "absolutely", "that's right",
})

_DENY_SIGNALS = frozenset({
    "no", "nope", "wrong", "incorrect", "never",
    "false", "not really", "actually", "that's not",
})


def _get_prior_ai_claim(context: list[dict]) -> str | None:
    """Return the last assistant turn's content if it recalled a stored fact, else None."""
    if not context or context[-1]["role"] != "assistant":
        return None
    text_lower = context[-1]["content"].lower()
    if any(sig in text_lower for sig in _RECALL_SIGNALS):
        return context[-1]["content"]
    return None


def _get_prior_assistant_turn(context: list[dict]) -> str | None:
    """Return the immediately preceding assistant turn's content, or None."""
    if not context or context[-1]["role"] != "assistant":
        return None
    return context[-1]["content"]


def _classify_user_reaction(content: str) -> str:
    """Classify user turn as 'confirm', 'deny', or 'neutral' relative to prior AI claim."""
    words = set(content.lower().split())
    if words & _CONFIRM_SIGNALS:
        return "confirm"
    if words & _DENY_SIGNALS:
        return "deny"
    # Check for sentence-level deny patterns
    lower = content.lower()
    if any(p in lower for p in ("that's wrong", "not anymore", "i stopped", "never said")):
        return "deny"
    return "neutral"


# ── Spatial Memory helpers ─────────────────────────────────────────────────────

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


def _format_object_sightings(rows: list[dict]) -> str | None:
    """Format a list of object sighting dicts for LLM injection."""
    if not rows:
        return None
    now   = time.time()
    lines = []
    for r in rows:
        age = now - r["last_seen_at"]
        if age < 60:
            age_str = "just now"
        elif age < 3600:
            age_str = f"{int(age / 60)} minutes ago"
        elif age < 86400:
            age_str = f"{int(age / 3600)} hours ago"
        else:
            age_str = f"{int(age / 86400)} days ago"

        times_note   = f", seen {r['times_seen']}×" if r["times_seen"] > 1 else ""
        context_note = (
            f" (while {r['person_context']} was present)"
            if r.get("person_context") else ""
        )
        lines.append(
            f"- {r['object_class']} on {r['location_zone']},"
            f" last seen {age_str}{times_note}{context_note}"
        )
    return "Objects I have observed in the room:\n" + "\n".join(lines)


_VISION_STOPWORDS = frozenset({
    "what", "where", "when", "have", "seen", "last", "time",
    "that", "this", "there", "here", "with", "from", "your",
    "about", "some", "which", "does", "know", "think", "been",
    "could", "would", "should", "just", "still", "around",
})


def _escalate_pref(content: str, friction_count: int) -> str:
    """Apply escalating urgency language to a pref based on how many times friction was detected."""
    if friction_count == 0:
        return content
    if friction_count <= 2:
        return f"[important] {content}"
    return f"[STRICT — repeated friction] {content}"


_VALID_PREF_TYPES = frozenset({
    "communication_style",
    "topic_avoidance",
    "response_length",
    "greeting_style",
    "language_preference",
    "response_habit",
})


# ── Data types ─────────────────────────────────────────────────────────────────

@dataclass
class Extraction:
    entity:          str
    entity_type:     str   # person | place | topic | event | object
    attribute:       str   # LLM-decided snake_case name — this is the "schema freedom"
    value:           str
    confidence:      float
    is_temporal:     bool
    valid_for_hours: float | None
    # Session 95 3A.4.5 — agent-layer classification. Every Extraction carries
    # its tier; store_knowledge reads it verbatim (no DB-side fallback). Default
    # is fail-closed 'personal' so a caller that somehow forgets to classify
    # still produces an owner-only row instead of leaking as 'public'. Agents
    # producing novel attributes call `_classify_privacy_level(entity,
    # attribute, value, http=...)` before constructing each Extraction;
    # sync-path agents (RoutineAgent, store_temporal_fact) hard-code the tier
    # because they emit a small closed set of attributes.
    privacy_level:   str = PRIVACY_LEVEL_DEFAULT
    # P0.S7.2 Plan v2 §4.2 — per-participant scope for multi-person assistant-
    # turn fan-out. Single-person extraction paths leave this None and the
    # downstream storage path uses the turn-speaker's person_id (existing
    # behavior). The κ fan-out emits one Extraction per participant with the
    # participant's pid here so the storage layer routes each fact to the
    # right person_id row. Additive + optional — backward-compat for the
    # existing single-person extraction shape.
    person_id:       "str | None" = None


# ── BrainDB ────────────────────────────────────────────────────────────────────

class BrainDB:
    """Manages brain.db — the self-organized knowledge store.

    Separate from faces.db so it can be wiped independently and opened
    by the brain agent without touching the main pipeline's DB connection.
    """

    # P0.9.2 Phase 2: retrofit migrations live in core/brain_db_migrations.py.
    # Each entry is a 5-tuple (version, description, apply_fn,
    # verify_post_fn, verify_present_fn).
    from core.brain_db_migrations import MIGRATIONS as _M
    MIGRATIONS: list = _M
    del _M

    def __init__(self, path: Path = BRAIN_DB_PATH):
        # P0.9.1 Imp-1: IMMEDIATE isolation prevents Python auto-BEGIN
        # (DEFERRED by default) from clashing with explicit BEGIN IMMEDIATE
        # used by BrainDB.transaction() and core.schema_migrations runner.
        self._conn = sqlite3.connect(
            str(path), check_same_thread=False,
            isolation_level="IMMEDIATE",
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_tables()
        self._migrate()
        # P0.9.1 Phase 1: ledger + pending-migration runner.  The existing
        # _migrate() above handles the ad-hoc PRAGMA-guarded ALTERs (Phase 2
        # converts these to versioned MIGRATIONS entries).  This block adds
        # the schema_migrations ledger so future migrations land there.
        from core.schema_migrations import (
            init_ledger as _il, bootstrap_ledger_if_unversioned as _bl,
            apply_migrations as _am,
        )
        _il(self._conn)
        _bl(
            self._conn,
            baseline_description="brain.db initial baseline (pre-P0.9)",
            migrations=self.MIGRATIONS,
            db_label="brain.db",
        )
        _am(self._conn, self.MIGRATIONS, db_label="brain.db")

    def _safe_commit(self) -> None:
        """Commit only when a transaction is actually open.

        Bug 2 (2026-04-20 live run) + Obs 2 hardening (2026-04-20 post-review):
        Concurrent async session-end tasks race on ``commit()`` — when one task
        commits and the next arrives before any new write starts a fresh
        transaction, SQLite raises ``OperationalError: cannot commit - no
        transaction is active``. The error is harmless (first commit already
        persisted both tasks' intent) but aborts the brain loop.

        Using ``conn.in_transaction`` instead of string-matching the error
        message is deterministic and survives SQLite version/locale changes.
        A genuine ``OperationalError`` (disk full, constraint violation, locked
        DB) still propagates — we only skip the commit when there's nothing
        to commit.
        """
        if self._conn.in_transaction:
            self._conn.commit()
        # else: no-op — nothing to commit

    @contextmanager
    def transaction(self):
        """Wrap a multi-step write block in BEGIN IMMEDIATE / COMMIT with rollback on exception.

        Uses BEGIN IMMEDIATE to acquire the write lock upfront — prevents SQLITE_BUSY
        mid-transaction if a reader holds the connection.

        Callers must NOT call self._conn.commit() inside the with-block; the context
        manager owns commit/rollback. Helpers called from within this block detect
        they're inside an outer transaction via self._conn.in_transaction (True after
        BEGIN IMMEDIATE) and skip their own inner commits.
        """
        prev_isolation = self._conn.isolation_level
        self._conn.isolation_level = None  # autocommit — prevents Python auto-BEGIN clash
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield
                self._conn.execute("COMMIT")
            except Exception:
                # P0.9.1 Imp-2: tightened rollback — re-raise unexpected
                # OperationalErrors instead of swallowing every Exception.
                # Only the S65 "no transaction is active" race is suppressed.
                try:
                    self._conn.execute("ROLLBACK")
                except sqlite3.OperationalError as _rbe:
                    if "no transaction is active" not in str(_rbe).lower():
                        print(f"[BrainDB] rollback failed unexpectedly: {_rbe!r}")
                        raise
                    # else: # RACE: S65 — known race, suppress
                raise
        finally:
            self._conn.isolation_level = prev_isolation

    def _init_tables(self) -> None:
        self._conn.executescript("""
            -- Tracks which conversation_log turn the brain last processed.
            -- Single row, always present.
            CREATE TABLE IF NOT EXISTS brain_state (
                singleton    INTEGER PRIMARY KEY DEFAULT 1,
                last_turn_id INTEGER NOT NULL DEFAULT 0,
                updated_at   REAL    NOT NULL DEFAULT 0
            );
            INSERT OR IGNORE INTO brain_state (singleton, last_turn_id, updated_at)
            VALUES (1, 0, 0);

            -- Core knowledge store.
            -- The LLM decides entity/attribute names — that IS the schema freedom.
            -- invalidated_at IS NULL means the fact is currently valid.
            CREATE TABLE IF NOT EXISTS knowledge (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                source_turn_id INTEGER NOT NULL,
                person_id      TEXT,
                entity         TEXT    NOT NULL,
                entity_type    TEXT    NOT NULL,
                attribute      TEXT    NOT NULL,
                value          TEXT    NOT NULL,
                confidence     REAL    NOT NULL,
                is_temporal    INTEGER NOT NULL DEFAULT 0,
                valid_until    REAL,
                invalidated_at REAL,
                invalidated_by INTEGER,
                agent          TEXT    NOT NULL,
                created_at     REAL    NOT NULL,
                privacy_level  TEXT    NOT NULL DEFAULT 'public'
            );
            CREATE INDEX IF NOT EXISTS idx_knowledge_entity
                ON knowledge(entity, attribute)
                WHERE invalidated_at IS NULL;

            -- Meta-schema catalog: every attribute name the LLM has ever invented.
            -- Used later for schema normalization and retrieval routing.
            CREATE TABLE IF NOT EXISTS schema_catalog (
                attribute     TEXT PRIMARY KEY,
                entity_type   TEXT NOT NULL,
                example_value TEXT,
                use_count     INTEGER NOT NULL DEFAULT 1,
                first_seen_at REAL    NOT NULL,
                last_used_at  REAL    NOT NULL
            );

            -- Full audit trail of every agent decision.
            -- Critical for debuggability: when something is wrong, trace back here.
            CREATE TABLE IF NOT EXISTS agent_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                turn_id     INTEGER,
                agent       TEXT NOT NULL,
                decision    TEXT NOT NULL,
                rationale   TEXT,
                items       INTEGER DEFAULT 0,
                duration_ms REAL,
                ts          REAL NOT NULL
            );

            -- Per-person communication preferences learned over sessions.
            -- Staged by default (sessions_seen=1, confirmed=0).
            -- Auto-activates after sessions_seen >= PREF_AUTO_CONFIRM_THRESHOLD, or immediately
            -- when source='human'.
            CREATE TABLE IF NOT EXISTS prompt_prefs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id     TEXT NOT NULL,
                pref_type     TEXT NOT NULL,
                content       TEXT NOT NULL,
                source        TEXT NOT NULL DEFAULT 'prompt_agent',
                sessions_seen INTEGER NOT NULL DEFAULT 1,
                confirmed     INTEGER NOT NULL DEFAULT 0,
                created_at    REAL NOT NULL,
                expires_at    REAL
            );
            CREATE INDEX IF NOT EXISTS idx_prompt_prefs_person_id
                ON prompt_prefs(person_id);

            -- LLM-generated questions about object patterns, queued for proactive asking.
            -- pattern_key prevents the same pattern being asked twice.
            CREATE TABLE IF NOT EXISTS object_pattern_questions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                question    TEXT NOT NULL,
                pattern_key TEXT NOT NULL UNIQUE,
                asked       INTEGER NOT NULL DEFAULT 0,
                asked_at    REAL,
                created_at  REAL NOT NULL
            );

            -- Confirmed behavioral patterns learned from user answers.
            CREATE TABLE IF NOT EXISTS object_patterns (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_key TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                confidence  REAL NOT NULL DEFAULT 0.9,
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL
            );

            -- People mentioned by the best friend during conversations.
            -- Used by IdentityAgent to recognise strangers who match.
            CREATE TABLE IF NOT EXISTS social_mentions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                source_person_id TEXT NOT NULL,
                mentioned_name   TEXT NOT NULL,
                relationship     TEXT,
                attributes       TEXT NOT NULL DEFAULT '[]',
                created_at       REAL NOT NULL,
                updated_at       REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_social_mentions_source
                ON social_mentions(source_person_id);

            -- Per-session episode summaries — generated by ConversationInsightAgent.
            CREATE TABLE IF NOT EXISTS episodes (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id        TEXT NOT NULL,
                session_start_ts REAL NOT NULL,
                session_end_ts   REAL NOT NULL,
                mood             TEXT,
                key_topics       TEXT NOT NULL DEFAULT '[]',
                promises_made    TEXT NOT NULL DEFAULT '[]',
                questions_asked  TEXT NOT NULL DEFAULT '[]',
                emotional_arc    TEXT,
                significance     REAL NOT NULL DEFAULT 0.5,
                turn_count       INTEGER NOT NULL DEFAULT 0,
                created_at       REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_episodes_person
                ON episodes(person_id, session_end_ts DESC);

            -- Per-person visit windows — used by RoutineAgent for pattern detection.
            CREATE TABLE IF NOT EXISTS presence_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id    TEXT NOT NULL,
                arrived_at   REAL NOT NULL,
                left_at      REAL NOT NULL,
                duration_s   REAL NOT NULL,
                day_of_week  INTEGER NOT NULL,
                hour_of_day  INTEGER NOT NULL,
                created_at   REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_presence_log_person
                ON presence_log(person_id, arrived_at DESC);

            -- Pending proactive nudges — generated by ProactiveNudgeAgent.
            CREATE TABLE IF NOT EXISTS proactive_nudges (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                target_person_id TEXT NOT NULL,
                nudge_type       TEXT NOT NULL,
                content          TEXT NOT NULL,
                metadata         TEXT NOT NULL DEFAULT '{}',
                confidence       REAL NOT NULL DEFAULT 0.5,
                generated_at     REAL NOT NULL,
                injected_at      REAL,
                dismissed_at     REAL,
                expires_at       REAL
            );
            CREATE INDEX IF NOT EXISTS idx_nudges_person
                ON proactive_nudges(target_person_id, injected_at, dismissed_at, expires_at);

            -- System health and anomaly alerts — generated by WatchdogAgent.
            CREATE TABLE IF NOT EXISTS watchdog_alerts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_type   TEXT NOT NULL,
                severity     TEXT NOT NULL,
                message      TEXT NOT NULL,
                metadata     TEXT NOT NULL DEFAULT '{}',
                resolved     INTEGER NOT NULL DEFAULT 0,
                created_at   REAL NOT NULL,
                resolved_at  REAL
            );
            CREATE INDEX IF NOT EXISTS idx_watchdog_ts
                ON watchdog_alerts(created_at DESC, resolved);

            -- Persistent spatial object memory — every YOLO detection stored here.
            -- Enables "I saw your watch on the left side 7 days ago" recall.
            -- Deduplicated by (object_class, location_zone) within VISION_SIGHTING_GAP seconds.
            CREATE TABLE IF NOT EXISTS object_sightings (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                object_class   TEXT NOT NULL,
                confidence     REAL NOT NULL,
                location_zone  TEXT NOT NULL,
                bbox_cx        REAL NOT NULL,
                bbox_cy        REAL NOT NULL,
                first_seen_at  REAL NOT NULL,
                last_seen_at   REAL NOT NULL,
                times_seen     INTEGER NOT NULL DEFAULT 1,
                person_context TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_object_sightings_class
                ON object_sightings(object_class);
            CREATE INDEX IF NOT EXISTS idx_object_sightings_ts
                ON object_sightings(last_seen_at);

            -- Phase 5: per-predicate contradiction + extraction counters.
            -- High contradiction_count → volatile predicate → ContradictionAgent nudged
            -- to prefer REPLACE, and stored confidence capped at PREDICATE_CONFIDENCE_CAP.
            CREATE TABLE IF NOT EXISTS predicate_stats (
                predicate           TEXT PRIMARY KEY,
                contradiction_count INTEGER NOT NULL DEFAULT 0,
                total_extractions   INTEGER NOT NULL DEFAULT 0,
                updated_at          REAL    NOT NULL DEFAULT 0
            );

            -- Household-scoped facts learned from multi-person conversation.
            -- Scope "household" = shared asset/routine (we/our). Scope "per_person" = individual fact.
            CREATE TABLE IF NOT EXISTS household_facts (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                entity           TEXT    NOT NULL,   -- "household" or person_name
                attribute        TEXT    NOT NULL,
                value            TEXT    NOT NULL,
                scope            TEXT    NOT NULL DEFAULT 'household',
                source_speakers  TEXT    NOT NULL DEFAULT '[]',   -- JSON list of person_ids who stated/corroborated
                confidence       REAL    NOT NULL DEFAULT 0.7,
                conflict_status  TEXT    NOT NULL DEFAULT 'provisional',  -- "settled" | "disputed" | "provisional"
                disputed_values  TEXT,               -- JSON: {"jagan": "7pm", "priya": "8pm"} when disputed
                first_seen       REAL    NOT NULL,
                last_confirmed   REAL    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_household_facts_entity_attr
                ON household_facts(entity, attribute);

            -- Inter-person relationships inferred from conversation.
            CREATE TABLE IF NOT EXISTS inter_person_relationships (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                person_a       TEXT    NOT NULL,
                relationship   TEXT    NOT NULL,   -- "married_to", "parent_of", "colleague_of", etc.
                person_b       TEXT    NOT NULL,   -- may be a free-text name if not enrolled
                confidence     REAL    NOT NULL DEFAULT 0.8,
                source_speaker TEXT,               -- person_id who stated this
                created_at     REAL    NOT NULL,
                updated_at     REAL    NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_relationships_unique
                ON inter_person_relationships(person_a, relationship, person_b);

            -- Shadow nodes for non-enrolled persons mentioned in conversation.
            -- When Priya says "my colleague Anita", we create a shadow node for Anita.
            -- If Anita enrolls later, just add face/voice to the existing node.
            CREATE TABLE IF NOT EXISTS shadow_persons (
                shadow_id          TEXT PRIMARY KEY,
                known_name         TEXT NOT NULL UNIQUE,
                known_via          TEXT NOT NULL DEFAULT '[]',   -- JSON: [{"person_id": "...", "relationship": "..."}]
                face_id            TEXT,                         -- NULL until enrolled
                voice_id           TEXT,                         -- NULL until enrolled
                enrollment_status  TEXT NOT NULL DEFAULT 'pending',
                facts              TEXT NOT NULL DEFAULT '[]',   -- JSON: [{attribute, value, confidence}]
                first_mentioned    REAL NOT NULL,
                last_mentioned     REAL NOT NULL
            );

            -- VISION_ROADMAP P1.7a (Session 85): one row per gated-tool decision
            -- routed through _intent_allows(). Phase 5 drift detection queries
            -- this to compute divergence rate and inspect individual rejections
            -- before flipping INTENT_FALLBACK_TO_REGEX to False. Schema per
            -- VISION_ROADMAP section 5.2.2. Kept wide (nullable where reasonable)
            -- so both classifier-available and classifier-unavailable branches
            -- can record their decision without a second table.
            CREATE TABLE IF NOT EXISTS intent_divergences (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                turn_id                INTEGER,                      -- conversation_log.id reference, nullable when called outside a logged turn
                person_id              TEXT,                         -- the caller whose session made the tool call
                user_text              TEXT,                         -- what the user actually said (ground truth for the gate)
                structured_intent      TEXT,                         -- classifier's turn_intent (NULL when classifier unavail)
                structured_extracted   TEXT,                         -- classifier's extracted_value (NULL if empty or unavail)
                structured_confidence  REAL,                         -- classifier's confidence (NULL when classifier unavail)
                tool_proposed          TEXT NOT NULL,                -- e.g. 'update_person_name'
                gate_decision          TEXT NOT NULL,                -- 'allow' | 'reject: <reason>' | 'regex_fallback_allow' | 'regex_fallback_reject' | 'shadow_sample'
                reviewed               INTEGER NOT NULL DEFAULT 0,   -- 1 once human has audited this row
                ts                     REAL NOT NULL,                -- epoch seconds
                mode                   TEXT NOT NULL DEFAULT 'gate'  -- Phase 5 S119: 'gate' (production decision) | 'shadow' (1% canary sample)
            );
            CREATE INDEX IF NOT EXISTS idx_intent_divergences_ts
                ON intent_divergences(ts DESC);
            CREATE INDEX IF NOT EXISTS idx_intent_divergences_tool
                ON intent_divergences(tool_proposed, ts DESC);
            CREATE INDEX IF NOT EXISTS idx_intent_divergences_mode
                ON intent_divergences(mode, ts DESC);
            -- Phase 3B.6 — room-end synthesis target. One row per room
            -- session written when the last person leaves; drives
            -- greeting enrichment ("It's been 18 hours since you and
            -- Lexi last talked...") without re-running retrieval.
            CREATE TABLE IF NOT EXISTS room_summaries (
                room_session_id  TEXT PRIMARY KEY,
                started_at       REAL NOT NULL,
                ended_at         REAL NOT NULL,
                speaker_pids     TEXT NOT NULL,    -- JSON array
                summary          TEXT NOT NULL,    -- LLM narrative (1-2 sentences) or topic-only fallback
                topic_tags       TEXT,             -- JSON array of entity values
                safety_flags     TEXT,             -- JSON array of {pid,name,attribute} dicts
                created_at       REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_room_summaries_ended
                ON room_summaries(ended_at DESC);
        """)
        self._conn.commit()

    # ── State ──────────────────────────────────────────────────────────────────

    def get_last_turn_id(self) -> int:
        return self._conn.execute(
            "SELECT last_turn_id FROM brain_state WHERE singleton = 1"
        ).fetchone()[0]

    def set_last_turn_id(self, turn_id: int) -> None:
        self._conn.execute(
            "UPDATE brain_state SET last_turn_id = ?, updated_at = ? WHERE singleton = 1",
            (turn_id, time.time()),
        )
        self._conn.commit()

    # ── Knowledge ──────────────────────────────────────────────────────────────

    def store_knowledge(
        self,
        extractions: list[Extraction],
        turn_id: int,
        person_id: str | None,
        agent: str,
    ) -> int:
        now = time.time()
        count = 0
        for e in extractions:
            # P0.S4 D1 — fail-loud at the brain.db write boundary if a tier
            # value outside PRIVACY_LEVELS slipped through extraction. The
            # _visibility_clause has no predicate matching an invalid tier,
            # so silently writing one would produce a row that's structurally
            # invisible to every retrieval site. Caller is wrapped in
            # try/except at _poll_once + _emotion_process_background; the
            # raise propagates up, logs traceback, continues to next turn.
            _assert_valid_privacy_level(
                e.privacy_level,
                f"BrainDB.store_knowledge (agent={agent!r}, attribute={e.attribute!r})",
            )
            valid_until = _valid_until(e.is_temporal, e.valid_for_hours, now)
            self._conn.execute(
                """INSERT INTO knowledge
                       (source_turn_id, person_id, entity, entity_type, attribute,
                        value, confidence, is_temporal, valid_until, valid_at,
                        agent, created_at, privacy_level)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (turn_id, person_id, e.entity, e.entity_type, e.attribute,
                 e.value, e.confidence, int(e.is_temporal), valid_until, now,
                 agent, now, e.privacy_level),
            )
            # Keep the schema catalog: every attribute the LLM invents is recorded here.
            self._conn.execute(
                """INSERT INTO schema_catalog
                       (attribute, entity_type, example_value, first_seen_at, last_used_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(attribute) DO UPDATE SET
                       use_count     = use_count + 1,
                       last_used_at  = excluded.last_used_at,
                       example_value = COALESCE(excluded.example_value, example_value)""",
                (e.attribute, e.entity_type, e.value, now, now),
            )
            count += 1
        self._conn.commit()
        return count

    def get_active_knowledge(self, entity: str) -> list[dict]:
        """Return currently valid (non-invalidated, non-expired) facts for an entity."""
        now = time.time()
        rows = self._conn.execute(
            """SELECT attribute, value, confidence, is_temporal, valid_until,
                      valid_at, last_confirmed_at, privacy_level
               FROM knowledge
               WHERE entity = ?
                 AND invalidated_at IS NULL
                 AND (valid_until IS NULL OR valid_until > ?)
               ORDER BY created_at DESC""",
            (entity, now),
        ).fetchall()
        return [
            {
                "attribute":         r[0],
                "value":             r[1],
                "confidence":        r[2],
                "is_temporal":       bool(r[3]),
                "valid_until":       r[4],
                "valid_at":          r[5],
                "last_confirmed_at": r[6],
                "privacy_level":     r[7],
            }
            for r in rows
        ]

    def get_active_knowledge_for_entities(self, entity_list: list[str]) -> dict[str, list]:
        """Bulk fetch currently valid facts for all entities in entity_list.

        Single WHERE entity IN (?, ...) query — O(1) DB roundtrips instead of
        O(distinct entities) when the caller iterates over extracted facts.
        Returns dict mapping entity → list[dict] (same shape as get_active_knowledge).
        """
        if not entity_list:
            return {}
        now = time.time()
        placeholders = ",".join("?" * len(entity_list))
        rows = self._conn.execute(
            f"""SELECT entity, attribute, value, confidence, is_temporal, valid_until,
                      valid_at, last_confirmed_at, privacy_level
               FROM knowledge
               WHERE entity IN ({placeholders})
                 AND invalidated_at IS NULL
                 AND (valid_until IS NULL OR valid_until > ?)
               ORDER BY created_at DESC""",
            (*entity_list, now),
        ).fetchall()
        result: dict[str, list] = {ent: [] for ent in entity_list}
        for r in rows:
            result[r[0]].append({
                "attribute":         r[1],
                "value":             r[2],
                "confidence":        r[3],
                "is_temporal":       bool(r[4]),
                "valid_until":       r[5],
                "valid_at":          r[6],
                "last_confirmed_at": r[7],
                "privacy_level":     r[8],
            })
        return result

    def get_historical_knowledge(self, entity: str, attribute: str) -> list[dict]:
        """Return all rows for (entity, attribute) in chronological order, including invalidated.

        Used to answer "what was Jagan's job before?" type queries.
        """
        rows = self._conn.execute(
            """SELECT attribute, value, confidence, valid_at, invalidated_at, created_at
               FROM knowledge
               WHERE entity = ? AND attribute = ?
               ORDER BY valid_at ASC""",
            (entity, attribute),
        ).fetchall()
        return [
            {
                "attribute":      r[0], "value":        r[1],
                "confidence":     r[2], "valid_at":      r[3],
                "invalidated_at": r[4], "created_at":    r[5],
            }
            for r in rows
        ]

    def invalidate(self, entity: str, attribute: str, invalidated_by_turn: int) -> int:
        """Mark existing facts for (entity, attribute) as superseded."""
        cursor = self._conn.execute(
            """UPDATE knowledge
               SET invalidated_at = ?, invalidated_by = ?
               WHERE entity = ? AND attribute = ? AND invalidated_at IS NULL""",
            (time.time(), invalidated_by_turn, entity, attribute),
        )
        self._conn.commit()
        return cursor.rowcount

    # ── Agent log ──────────────────────────────────────────────────────────────

    def log_agent(
        self,
        turn_id: int | None,
        agent: str,
        decision: str,
        rationale: str | None = None,
        items: int = 0,
        duration_ms: float = 0.0,
    ) -> None:
        self._conn.execute(
            """INSERT INTO agent_log
                   (turn_id, agent, decision, rationale, items, duration_ms, ts)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (turn_id, agent, decision, rationale, items, duration_ms, time.time()),
        )
        self._conn.commit()

    # ── Prompt preferences ─────────────────────────────────────────────────────

    def store_pref(
        self,
        person_id: str,
        pref_type: str,
        content: str,
        source: str = "prompt_agent",
    ) -> bool:
        """Store a preference. Returns True if new, False if sessions_seen incremented.

        Near-duplicate detection: same person_id + pref_type + identical normalized
        content → increment sessions_seen and auto-confirm at 3.
        """
        norm = content.strip().lower()
        rows = self._conn.execute(
            "SELECT id, sessions_seen, content FROM prompt_prefs WHERE person_id=? AND pref_type=?",
            (person_id, pref_type),
        ).fetchall()
        for row_id, sessions, stored_content in rows:
            if stored_content.strip().lower() == norm:
                new_count = sessions + 1
                self._conn.execute(
                    "UPDATE prompt_prefs SET sessions_seen=?, confirmed=? WHERE id=?",
                    (new_count, 1 if new_count >= PREF_AUTO_CONFIRM_THRESHOLD else 0, row_id),
                )
                self._conn.commit()
                return False
        self._conn.execute(
            """INSERT INTO prompt_prefs
                   (person_id, pref_type, content, source, sessions_seen, confirmed, created_at)
               VALUES (?, ?, ?, ?, 1, ?, ?)""",
            (person_id, pref_type, content, source, 1 if source == "human" else 0, time.time()),
        )
        self._conn.commit()
        return True

    def get_active_prefs(self, person_id: str) -> list[dict]:
        """Return confirmed prefs: confirmed=1 or sessions_seen≥threshold, not expired."""
        now = time.time()
        rows = self._conn.execute(
            """SELECT pref_type, content, sessions_seen, confirmed, friction_count
               FROM prompt_prefs
               WHERE person_id = ?
                 AND (confirmed = 1 OR sessions_seen >= ?)
                 AND (expires_at IS NULL OR expires_at > ?)
               ORDER BY sessions_seen DESC, created_at DESC""",
            (person_id, PREF_AUTO_CONFIRM_THRESHOLD, now),
        ).fetchall()
        return [
            {
                "pref_type":     r[0], "content":      r[1],
                "sessions_seen": r[2], "confirmed":    bool(r[3]),
                "friction_count": r[4],
            }
            for r in rows
        ]

    # ── Bug L (Session 69) — semantic dedup support ──────────────────────────
    def get_prefs_by_type(self, person_id: str, pref_type: str) -> list[dict]:
        """Return ALL prefs for (person_id, pref_type), including staged ones.
        Used at activation time to check semantic similarity against prior prefs
        — staged rows (sessions_seen < threshold) must also count so repeated
        near-duplicates strengthen the existing row instead of fragmenting."""
        rows = self._conn.execute(
            """SELECT id, content, sessions_seen, confirmed, embedding
               FROM prompt_prefs
               WHERE person_id = ? AND pref_type = ?
               ORDER BY sessions_seen DESC, created_at DESC""",
            (person_id, pref_type),
        ).fetchall()
        return [
            {"id": r[0], "content": r[1], "sessions_seen": r[2],
             "confirmed": bool(r[3]), "embedding": r[4]}
            for r in rows
        ]

    def set_pref_embedding(self, pref_id: int, embedding: bytes) -> None:
        """Persist the 1024-dim float32 embedding bytes for a pref row."""
        self._conn.execute(
            "UPDATE prompt_prefs SET embedding = ? WHERE id = ?",
            (embedding, pref_id),
        )
        self._conn.commit()

    def bump_pref_seen(self, pref_id: int) -> None:
        """Strengthen an existing pref — increment sessions_seen, auto-confirm
        at PREF_AUTO_CONFIRM_THRESHOLD. Used when semantic dedup matches an
        existing row instead of inserting a near-duplicate."""
        row = self._conn.execute(
            "SELECT sessions_seen FROM prompt_prefs WHERE id = ?", (pref_id,),
        ).fetchone()
        if not row:
            return
        new_count = row[0] + 1
        self._conn.execute(
            "UPDATE prompt_prefs SET sessions_seen = ?, confirmed = ? WHERE id = ?",
            (new_count, 1 if new_count >= PREF_AUTO_CONFIRM_THRESHOLD else 0, pref_id),
        )
        self._conn.commit()

    def get_prompt_addendum(self, person_id: str) -> str | None:
        """Format active prefs as an injection-ready string with friction escalation.

        Returns None if empty. friction_count drives injection urgency:
          0   → plain content
          1-2 → [important] prefix
          3+  → [STRICT — repeated friction] prefix
        """
        prefs = self.get_active_prefs(person_id)
        if not prefs:
            return None
        return "\n".join(
            f"- {_escalate_pref(p['content'], p['friction_count'])}" for p in prefs
        )

    # ── Predicate reliability stats (Phase 5) ──────────────────────────────────

    def increment_predicate_contradiction(self, predicate: str) -> None:
        self._conn.execute(
            """INSERT INTO predicate_stats (predicate, contradiction_count, total_extractions, updated_at)
               VALUES (?, 1, 0, ?)
               ON CONFLICT(predicate) DO UPDATE SET
                   contradiction_count = contradiction_count + 1,
                   updated_at = excluded.updated_at""",
            (predicate, time.time()),
        )
        self._conn.commit()

    def increment_predicate_extraction(self, predicate: str) -> None:
        self.batch_increment_predicate_extraction([predicate])

    def batch_increment_predicate_extraction(self, predicates: list[str]) -> None:
        """Increment total_extractions for each predicate in a single transaction."""
        if not predicates:
            return
        now = time.time()
        for predicate in predicates:
            self._conn.execute(
                """INSERT INTO predicate_stats (predicate, contradiction_count, total_extractions, updated_at)
                   VALUES (?, 0, 1, ?)
                   ON CONFLICT(predicate) DO UPDATE SET
                       total_extractions = total_extractions + 1,
                       updated_at = excluded.updated_at""",
                (predicate, now),
            )
        self._conn.commit()

    def get_predicate_contradiction_count(self, predicate: str) -> int:
        row = self._conn.execute(
            "SELECT contradiction_count FROM predicate_stats WHERE predicate = ?",
            (predicate,),
        ).fetchone()
        return row[0] if row else 0

    def increment_pref_friction(self, person_id: str, pref_type: str) -> None:
        """Increment friction_count for the matching active pref. No-op if no match."""
        self._conn.execute(
            """UPDATE prompt_prefs
               SET friction_count = friction_count + 1
               WHERE person_id = ? AND pref_type = ?
                 AND (confirmed = 1 OR sessions_seen >= ?)
                 AND (expires_at IS NULL OR expires_at > ?)""",
            (person_id, pref_type, PREF_AUTO_CONFIRM_THRESHOLD, time.time()),
        )
        self._conn.commit()

    def get_all_knowledge_rows(self) -> list[dict]:
        """Return all knowledge rows (including invalidated) for graph rebuild.

        P0.S7.D-B: ``privacy_level`` added so the v3 graph rebuild can
        thread the tier onto every RELATES_TO edge. Pre-S106 rows that
        lack the column fall back at the caller via
        ``row.get("privacy_level") or PRIVACY_LEVEL_DEFAULT``.
        """
        rows = self._conn.execute(
            "SELECT entity, entity_type, attribute, value, confidence,"
            " is_temporal, valid_until, invalidated_at, source_turn_id, created_at, valid_at,"
            " privacy_level"
            " FROM knowledge"
        ).fetchall()
        return [
            {
                "entity": r[0], "entity_type": r[1], "attribute": r[2],
                "value": r[3], "confidence": r[4], "is_temporal": r[5],
                "valid_until": r[6], "invalidated_at": r[7],
                "source_turn_id": r[8], "created_at": r[9],
                "valid_at": r[10], "privacy_level": r[11],
            }
            for r in rows
        ]

    # ── Migration ──────────────────────────────────────────────────────────────
    # P0.9.3: the former `_migrate()` method body (10 PRAGMA-guarded ALTERs
    # spanning knowledge.embedding/valid_at/last_confirmed_at/privacy_level,
    # schema_catalog.embedding, prompt_prefs.friction_count/embedding,
    # brain_state.graph_schema_version, shadow_persons.mention_count,
    # intent_divergences.mode, plus the privacy_level NULL/legacy 'private'
    # remediation) has been retrofitted as MIGRATIONS entries v=2 through
    # v=11 in core.brain_db_migrations.  core.schema_migrations.apply_migrations
    # runs them (or bootstrap stamps them is_initial=1 on legacy DBs where
    # they already landed via the pre-P0.9 inline path).  The inline code
    # that used to live here is now redundant by construction — Phase 2's
    # validation against Jagan's prod DBs confirmed the bootstrap+runner
    # path handles legacy state.  _migrate() now exists only as a stub
    # so the __init__ call site stays trivially correct.

    def _migrate(self) -> None:
        """No-op stub — retrofitted into core.brain_db_migrations.MIGRATIONS.

        Kept as a stub (rather than removed entirely) so the existing
        __init__ call chain reads cleanly without conditional branches.
        The migration runner does the real work via apply_migrations.
        """
        return

    # ── Embedding storage ──────────────────────────────────────────────────────

    def store_knowledge_embedding(self, knowledge_id: int, embedding: list[float]) -> None:
        blob = np.array(embedding, dtype=np.float32).tobytes()
        self._conn.execute(
            "UPDATE knowledge SET embedding = ? WHERE id = ?", (blob, knowledge_id)
        )
        self._conn.commit()

    def get_unembedded_knowledge(self, person_id: str, limit: int = 20) -> list[dict]:
        """Return recently stored rows for a person that have no embedding yet."""
        rows = self._conn.execute(
            """SELECT id, entity, attribute, value
               FROM knowledge
               WHERE person_id = ? AND embedding IS NULL AND invalidated_at IS NULL
               ORDER BY created_at DESC LIMIT ?""",
            (person_id, limit),
        ).fetchall()
        return [{"id": r[0], "entity": r[1], "attribute": r[2], "value": r[3]} for r in rows]

    def get_all_unembedded_knowledge(self, limit: int = 50) -> list[dict]:
        """Return rows with embedding IS NULL across ALL persons, for startup backfill.

        Ordered oldest-first so the historical backlog is processed chronologically
        rather than re-processing the most recent rows that _embed_new_facts already handles.
        """
        rows = self._conn.execute(
            """SELECT id, entity, attribute, value, person_id
               FROM knowledge
               WHERE embedding IS NULL AND invalidated_at IS NULL
               ORDER BY created_at ASC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [
            {"id": r[0], "entity": r[1], "attribute": r[2], "value": r[3], "person_id": r[4]}
            for r in rows
        ]

    def store_schema_embedding(self, attribute: str, embedding: list[float]) -> None:
        blob = np.array(embedding, dtype=np.float32).tobytes()
        self._conn.execute(
            "UPDATE schema_catalog SET embedding = ? WHERE attribute = ?", (blob, attribute)
        )
        self._conn.commit()

    def get_unembedded_schema_attributes(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT attribute, use_count FROM schema_catalog"
            " WHERE embedding IS NULL ORDER BY use_count DESC"
        ).fetchall()
        return [{"attribute": r[0], "use_count": r[1]} for r in rows]

    def get_all_schema_embeddings(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT attribute, use_count, embedding FROM schema_catalog"
            " WHERE embedding IS NOT NULL"
        ).fetchall()
        return [{"attribute": r[0], "use_count": r[1], "embedding": r[2]} for r in rows]

    def merge_schema_attributes(self, canonical: str, synonyms: list[str]) -> None:
        """Rewrite knowledge rows and collapse schema_catalog for synonym → canonical."""
        for syn in synonyms:
            self._conn.execute(
                "UPDATE knowledge SET attribute = ? WHERE attribute = ?", (canonical, syn)
            )
            row = self._conn.execute(
                "SELECT use_count FROM schema_catalog WHERE attribute = ?", (syn,)
            ).fetchone()
            if row:
                self._conn.execute(
                    "UPDATE schema_catalog SET use_count = use_count + ? WHERE attribute = ?",
                    (row[0], canonical),
                )
            self._conn.execute(
                "DELETE FROM schema_catalog WHERE attribute = ?", (syn,)
            )
        self._conn.commit()

    def update_confidence(self, knowledge_id: int, delta: float) -> None:
        """Adjust a fact's confidence by delta, clamped to [0.0, 0.99]."""
        self._conn.execute(
            "UPDATE knowledge SET confidence = MIN(0.99, MAX(0.0, confidence + ?)) WHERE id = ?",
            (delta, knowledge_id),
        )
        self._conn.commit()

    def update_confirmation(self, knowledge_id: int) -> None:
        """Boost confidence AND reset the decay clock (SM-2 confirmation).

        Called when the user explicitly confirms an AI-recalled fact. The
        last_confirmed_at timestamp becomes the new anchor for decay, so the
        fact is treated as freshly valid starting from today.
        """
        now = time.time()
        self._conn.execute(
            """UPDATE knowledge
               SET confidence = MIN(0.99, MAX(0.0, confidence + ?)),
                   last_confirmed_at = ?
               WHERE id = ?""",
            (CONFIDENCE_BOOST, now, knowledge_id),
        )
        self._conn.commit()

    def decay_and_prune(
        self, prune_floor: float, decay_threshold: float
    ) -> tuple[int, int, int]:
        """Apply time-decay writes to all active knowledge rows.

        Facts whose effective confidence drops below prune_floor are soft-deleted
        (invalidated_at set). Facts that have decayed by more than decay_threshold
        have their stored confidence updated to the current effective value.

        Returns (pruned, decayed, stable) counts.
        """
        now = time.time()
        rows = self._conn.execute(
            """SELECT id, confidence, valid_at, last_confirmed_at
               FROM knowledge
               WHERE invalidated_at IS NULL""",
        ).fetchall()
        if not rows:
            return 0, 0, 0

        pruned = decayed = 0
        for row_id, stored_conf, valid_at, last_confirmed_at in rows:
            eff_conf = _decayed_confidence(stored_conf, valid_at, last_confirmed_at)
            if eff_conf < prune_floor:
                self._conn.execute(
                    "UPDATE knowledge SET invalidated_at = ? WHERE id = ?", (now, row_id)
                )
                pruned += 1
            elif eff_conf < stored_conf - decay_threshold:
                self._conn.execute(
                    "UPDATE knowledge SET confidence = ? WHERE id = ?",
                    (round(eff_conf, 4), row_id),
                )
                decayed += 1

        if pruned or decayed:
            self._conn.commit()

        return pruned, decayed, len(rows) - pruned - decayed

    def find_knowledge_id(self, entity: str, attribute: str, value: str) -> int | None:
        """Return the id of an active knowledge row, or None if not found."""
        row = self._conn.execute(
            "SELECT id FROM knowledge WHERE entity = ? AND attribute = ? AND value = ?"
            " AND invalidated_at IS NULL LIMIT 1",
            (entity, attribute, value),
        ).fetchone()
        return row[0] if row else None

    def semantic_search_knowledge(
        self,
        person_name: str,
        query_embedding: list[float],
        top_k: int = EMBED_TOP_K,
        *,
        requester_pid: "str | None" = None,
        best_friend_id: "str | None" = None,
    ) -> list[dict]:
        """Return top-K facts for a person ranked by cosine similarity to the query.

        Applies time-decay filtering (Item 6): a floor of 0.30 is used in SQL to
        avoid loading noise-level facts; actual EMBED_MIN_CONFIDENCE gate is applied
        in Python using _decayed_confidence() so old facts decay out naturally.

        Session 107 Phase 3A.6 — visibility is now composed into the
        SELECT WHERE clause when ``requester_pid`` is supplied. Same
        semantics as ``query_knowledge_for``: best_friend sees all
        non-system_only tiers, non-best_friend sees public + own
        personal. When ``requester_pid`` is None (internal callers with
        no identity context — dream loop synthesis, schema
        normalization), no visibility filter is added (pass-through
        behavior matching the legacy ``filter_facts_for_requester``'s
        None-guard path). Ranking + filtering now happen together in
        SQL; the Python-side filter step (``filter_facts_for_requester``)
        is deleted as part of this migration.
        """
        now = time.time()
        where_parts: list[str] = [
            "entity = ?",
            "invalidated_at IS NULL",
            "(valid_until IS NULL OR valid_until > ?)",
            "confidence >= 0.30",
            "embedding IS NOT NULL",
        ]
        params: list = [person_name, now]
        if requester_pid is not None:
            vis_clause, vis_params = _visibility_clause(requester_pid, best_friend_id)
            where_parts.append(f"({vis_clause})")
            params.extend(vis_params)
        sql = (
            "SELECT attribute, value, confidence, is_temporal, valid_until, "
            "embedding, valid_at, last_confirmed_at, privacy_level "
            "FROM knowledge WHERE " + " AND ".join(where_parts) +
            " ORDER BY created_at DESC"
        )
        rows = self._conn.execute(sql, params).fetchall()
        if not rows:
            return []

        doc_vecs   = []
        fact_dicts = []
        for r in rows:
            eff_conf = _decayed_confidence(r[2], r[6], r[7])
            if eff_conf < EMBED_MIN_CONFIDENCE:
                continue
            doc_vecs.append(np.frombuffer(r[5], dtype=np.float32).tolist())
            fact_dicts.append({
                "attribute":         r[0], "value":           r[1],
                "confidence":        r[2], "is_temporal":      bool(r[3]),
                "valid_until":       r[4], "valid_at":         r[6],
                "last_confirmed_at": r[7], "privacy_level":    r[8],
            })
        if not fact_dicts:
            return []

        scores = _cosine_similarity(query_embedding, doc_vecs)
        ranked = sorted(zip(scores, fact_dicts), key=lambda x: x[0], reverse=True)
        return [f for _, f in ranked[:top_k]]

    # ── Context ────────────────────────────────────────────────────────────────

    def get_context_for_person(self, person_name: str) -> str | None:
        """Return formatted knowledge for LLM system-prompt injection (recency order)."""
        facts = self.get_active_knowledge(person_name)
        return _format_context_lines(person_name, facts) if facts else None

    # Session 107 Phase 3A.6 — filter_facts_for_requester was deleted
    # after the semantic-search branch of BrainOrchestrator.get_context
    # migrated to pass requester_pid/best_friend_id into
    # semantic_search_knowledge (which composes _visibility_clause in
    # SQL). Zero remaining production callers. The 4-tier visibility
    # policy now lives in one place only: `_visibility_clause` at
    # module scope. Any future retrieval site that needs privacy
    # filtering goes through `query_knowledge_for` or passes
    # `requester_pid` into `semantic_search_knowledge`.

    def query_knowledge_for(
        self,
        requester_pid:  str,
        best_friend_id: "str | None",
        *,
        entity:    "str | None" = None,
        attribute: "str | None" = None,
        limit:     int           = 20,
    ) -> list[dict]:
        """Privacy-filtered knowledge retrieval — the 4-tier replacement for
        `get_active_knowledge` + `filter_facts_for_requester`.

        Internal callers touching the ``knowledge`` table MUST use this (or go
        through a site that does) once 3A.4 canary lands. Single source of
        truth for visibility policy: the SELECT's WHERE clause is composed
        from `_visibility_clause`, so adding a new tier or flipping policy
        happens in one place.

        The returned shape deliberately mirrors reviewer's 3A.4 spec
        (entity/attribute/value/confidence/person_id/privacy_level) rather
        than the richer `get_active_knowledge` shape — the canary site only
        consumes attribute/value/confidence, and keeping the surface narrow
        lets the schema grow (e.g. add `tier_reason` in 3A.6) without
        ballooning the read columns.

        Temporal and invalidation filters match the existing read paths:
        only currently-valid rows are returned (``invalidated_at IS NULL``
        and ``valid_until > now`` when present). Sort is confidence DESC
        followed by recency so the top-k slice is stable across calls.
        """
        now = time.time()
        vis_clause, vis_params = _visibility_clause(requester_pid, best_friend_id)

        where_parts:  list[str] = [f"({vis_clause})", "invalidated_at IS NULL",
                                   "(valid_until IS NULL OR valid_until > ?)"]
        sql_params:   list      = list(vis_params) + [now]
        if entity:
            where_parts.append("entity = ?")
            sql_params.append(entity)
        if attribute:
            where_parts.append("attribute = ?")
            sql_params.append(attribute)

        sql = (
            "SELECT entity, attribute, value, confidence, person_id, privacy_level "
            "FROM knowledge WHERE " + " AND ".join(where_parts) +
            " ORDER BY confidence DESC, created_at DESC LIMIT ?"
        )
        sql_params.append(limit)
        cur = self._conn.execute(sql, sql_params)
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        # Session 116 P1 #1+#2 — auditability: log every privacy-filtered
        # read with requester + tier scope + result shape so an outside
        # reviewer can verify cross-person isolation from terminal output
        # alone. Owner-mode (best_friend == requester) is the most
        # permissive scope and worth flagging in the line.
        _scope = (
            "owner-mode" if best_friend_id and requester_pid == best_friend_id
            else "non-owner"
        )
        _entity_str = f"entity={entity!r}" if entity else "all-entities"
        _attr_str = f", attribute={attribute!r}" if attribute else ""
        print(
            f"[Privacy] {_now_log_ts()} query_knowledge_for "
            f"requester={requester_pid!r} ({_scope}) {_entity_str}{_attr_str} "
            f"→ {len(rows)} row(s)"
        )
        return rows

    def get_core_memory_for(
        self,
        requester_pid:  str,
        best_friend_id: "str | None",
        entity:         str,
    ) -> list[dict]:
        """Return always-on stable facts for Section 2 prompt injection.

        Fetches rows whose attribute is in CORE_MEMORY_ATTRIBUTES and whose
        confidence meets CORE_MEMORY_MIN_CONFIDENCE.  Privacy filtering is
        applied via _visibility_clause — same policy as query_knowledge_for,
        so cross-person facts cannot leak.

        Returns up to CORE_MEMORY_MAX_FACTS rows ordered by confidence DESC.
        Returns [] when CORE_MEMORY_ENABLED is False.
        """
        if not CORE_MEMORY_ENABLED:
            return []

        now = time.time()
        vis_clause, vis_params = _visibility_clause(requester_pid, best_friend_id)

        # Build a SQL IN clause for the attribute whitelist
        placeholders = ",".join("?" * len(CORE_MEMORY_ATTRIBUTES))
        where = (
            f"({vis_clause})"
            " AND invalidated_at IS NULL"
            " AND (valid_until IS NULL OR valid_until > ?)"
            " AND entity = ?"
            f" AND attribute IN ({placeholders})"
            " AND confidence >= ?"
        )
        params: list = (
            list(vis_params)
            + [now, entity]
            + list(CORE_MEMORY_ATTRIBUTES)
            + [CORE_MEMORY_MIN_CONFIDENCE]
        )

        sql = (
            "SELECT entity, attribute, value, confidence, person_id, privacy_level "
            f"FROM knowledge WHERE {where} "
            "ORDER BY confidence DESC LIMIT ?"
        )
        params.append(CORE_MEMORY_MAX_FACTS)

        cur = self._conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        return rows

    # ── Object sightings (Spatial Memory) ─────────────────────────────────────

    def store_object_sighting(
        self,
        object_class:   str,
        confidence:     float,
        location_zone:  str,
        bbox_cx:        float,
        bbox_cy:        float,
        person_context: str | None,
        dedup_gap_secs: float = 60.0,
    ) -> bool:
        """Store a new sighting or bump an existing one within dedup_gap_secs.

        Returns True if a new row was inserted (new sighting), False if an
        existing row was updated (same object still in the same zone).
        """
        now      = time.time()
        existing = self._conn.execute(
            """SELECT id, times_seen FROM object_sightings
               WHERE  object_class = ? AND location_zone = ?
                 AND  last_seen_at > ?""",
            (object_class, location_zone, now - dedup_gap_secs),
        ).fetchone()
        if existing:
            self._conn.execute(
                """UPDATE object_sightings
                   SET last_seen_at = ?, times_seen = ?, confidence = ?
                   WHERE id = ?""",
                (now, existing[1] + 1, confidence, existing[0]),
            )
            self._conn.commit()
            return False
        self._conn.execute(
            """INSERT INTO object_sightings
               (object_class, confidence, location_zone, bbox_cx, bbox_cy,
                first_seen_at, last_seen_at, times_seen, person_context)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (object_class, confidence, location_zone, bbox_cx, bbox_cy,
             now, now, person_context),
        )
        self._conn.commit()
        return True

    def search_object_sightings(
        self, keywords: list[str], limit: int = 5
    ) -> list[dict]:
        """Return recent sightings whose class name matches any keyword (LIKE)."""
        if not keywords:
            return []
        conditions = " OR ".join("object_class LIKE ?" for _ in keywords)
        params: list = [f"%{kw}%" for kw in keywords]
        params.append(limit)
        rows = self._conn.execute(
            f"""SELECT object_class, confidence, location_zone,
                       first_seen_at, last_seen_at, times_seen, person_context
                FROM   object_sightings
                WHERE  ({conditions})
                ORDER  BY last_seen_at DESC
                LIMIT  ?""",
            params,
        ).fetchall()
        return [
            {
                "object_class":  r[0], "confidence":  r[1],
                "location_zone": r[2], "first_seen_at": r[3],
                "last_seen_at":  r[4], "times_seen": r[5],
                "person_context": r[6],
            }
            for r in rows
        ]

    def get_recent_object_sightings(self, limit: int = 20) -> list[dict]:
        """Return the most recently observed objects regardless of class."""
        rows = self._conn.execute(
            """SELECT object_class, confidence, location_zone,
                      first_seen_at, last_seen_at, times_seen, person_context
               FROM   object_sightings
               ORDER  BY last_seen_at DESC
               LIMIT  ?""",
            (limit,),
        ).fetchall()
        return [
            {
                "object_class":  r[0], "confidence":  r[1],
                "location_zone": r[2], "first_seen_at": r[3],
                "last_seen_at":  r[4], "times_seen": r[5],
                "person_context": r[6],
            }
            for r in rows
        ]

    def prune_object_sightings(self, max_rows: int) -> None:
        """Delete the oldest sightings when the table exceeds max_rows."""
        count = self._conn.execute(
            "SELECT COUNT(*) FROM object_sightings"
        ).fetchone()[0]
        if count > max_rows:
            self._conn.execute(
                """DELETE FROM object_sightings WHERE id IN (
                    SELECT id FROM object_sightings
                    ORDER  BY last_seen_at ASC
                    LIMIT  ?
                )""",
                (count - max_rows,),
            )
            self._conn.commit()

    # ── Table pruning (E) ─────────────────────────────────────────────────────

    def prune_knowledge_hard_cap(self, max_rows: int) -> int:
        """Soft-delete oldest active knowledge rows when count exceeds max_rows.

        Marks excess rows as invalidated (not hard-deleted) so the graph and
        embedding blobs remain queryable for rebuild. Returns rows invalidated.
        """
        count = self._conn.execute(
            "SELECT COUNT(*) FROM knowledge WHERE invalidated_at IS NULL"
        ).fetchone()[0]
        if count <= max_rows:
            return 0
        excess = count - max_rows
        self._conn.execute(
            "UPDATE knowledge SET invalidated_at = ? WHERE id IN ("
            "  SELECT id FROM knowledge WHERE invalidated_at IS NULL"
            "  ORDER BY created_at ASC LIMIT ?"
            ")",
            (time.time(), excess),
        )
        self._conn.commit()
        return excess

    def hard_delete_old_invalidated_knowledge(
        self,
        *,
        cutoff_days: int = KNOWLEDGE_HARD_DELETE_AFTER_DAYS,
        now: float | None = None,
    ) -> int:
        """Hard-delete knowledge rows soft-deleted longer than cutoff_days.

        Wave 6 / Item 22 — prevents unbounded soft-delete accumulation at year
        scale. Conservative 60-day cutoff: conversation log archives at 30 days,
        so a 30-day buffer remains where archived turns can still resolve their
        invalidated facts.
        """
        if now is None:
            now = time.time()
        cutoff_ts = now - (cutoff_days * 86400)
        cur = self._conn.execute(
            "DELETE FROM knowledge "
            "WHERE invalidated_at IS NOT NULL AND invalidated_at < ?",
            (cutoff_ts,),
        )
        n = cur.rowcount
        self._safe_commit()
        if n > 0:
            print(f"[Prune] Hard-deleted {n} invalidated knowledge row(s) older than {cutoff_days}d")
        return n

    def _prune_table(self, table: str, order_col: str, max_rows: int) -> int:
        """Hard-delete oldest rows from table when row count exceeds max_rows."""
        count = self._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if count <= max_rows:
            return 0
        excess = count - max_rows
        self._conn.execute(
            f"DELETE FROM {table} WHERE id IN ("
            f"  SELECT id FROM {table} ORDER BY {order_col} ASC LIMIT ?"
            f")",
            (excess,),
        )
        self._conn.commit()
        return excess

    def prune_presence_log(self, max_rows: int) -> int:
        return self._prune_table("presence_log", "arrived_at", max_rows)

    def prune_episodes(self, max_rows: int) -> int:
        return self._prune_table("episodes", "session_end_ts", max_rows)

    def prune_social_mentions(self, max_rows: int) -> int:
        return self._prune_table("social_mentions", "updated_at", max_rows)

    def prune_expired_nudges(self) -> int:
        """Delete proactive nudges whose expires_at has passed."""
        cur = self._conn.execute(
            "DELETE FROM proactive_nudges WHERE expires_at IS NOT NULL AND expires_at < ?",
            (time.time(),),
        )
        self._conn.commit()
        return cur.rowcount

    def prune_old_resolved_alerts(self, max_age_days: float) -> int:
        """Delete resolved watchdog alerts older than max_age_days."""
        cutoff = time.time() - max_age_days * 86400
        cur = self._conn.execute(
            "DELETE FROM watchdog_alerts WHERE resolved = 1 AND created_at < ?",
            (cutoff,),
        )
        self._conn.commit()
        return cur.rowcount

    def prune_agent_log(self, max_age_days: float = 30, max_rows: int = 50_000) -> int:
        """Delete old agent_log rows: first by age, then hard-cap remaining."""
        cutoff = time.time() - max_age_days * 86400
        cur = self._conn.execute(
            "DELETE FROM agent_log WHERE ts < ?", (cutoff,)
        )
        self._conn.commit()
        removed = cur.rowcount
        removed += self._prune_table("agent_log", "ts", max_rows)
        return removed

    def prune_expired_prefs(self) -> int:
        """Delete prompt_prefs rows whose expires_at has passed."""
        cur = self._conn.execute(
            "DELETE FROM prompt_prefs WHERE expires_at IS NOT NULL AND expires_at < ?",
            (time.time(),),
        )
        self._conn.commit()
        return cur.rowcount

    def prune_old_pattern_questions(self, max_age_days: float = 7) -> int:
        """Delete already-asked pattern questions older than max_age_days."""
        cutoff = time.time() - max_age_days * 86400
        cur = self._conn.execute(
            "DELETE FROM object_pattern_questions WHERE asked = 1 AND asked_at < ?",
            (cutoff,),
        )
        self._conn.commit()
        return cur.rowcount

    # ── Household context methods ───────────────────────────────────────────

    def store_household_fact(
        self,
        entity: str,
        attribute: str,
        value: str,
        scope: str,
        source_speaker: str,
        confidence: float,
    ) -> bool:
        """Store or update a household fact. Returns True if this created a dispute.

        Conflict logic:
        - Same speaker updates an existing fact → REPLACE (genuine update)
        - Different speaker corroborates → bump confidence + add to source_speakers
        - Different speaker contradicts a stable fact → mark disputed, store both values
        - Temporal/ephemeral facts (scope contains "temporal") → always REPLACE
        """
        now = time.time()
        row = self._conn.execute(
            "SELECT id, value, source_speakers, confidence, conflict_status FROM household_facts "
            "WHERE entity = ? AND attribute = ? AND conflict_status != 'invalidated'",
            (entity, attribute),
        ).fetchone()

        if row is None:
            self._conn.execute(
                "INSERT INTO household_facts "
                "(entity, attribute, value, scope, source_speakers, confidence, conflict_status, first_seen, last_confirmed) "
                "VALUES (?, ?, ?, ?, ?, ?, 'provisional', ?, ?)",
                (entity, attribute, value, scope, json.dumps([source_speaker]), confidence, now, now),
            )
            self._conn.commit()
            return False

        existing_id, existing_value, speakers_json, existing_conf, existing_status = row
        speakers: list = json.loads(speakers_json)

        # Same speaker → genuine update: REPLACE
        if source_speaker in speakers:
            self._conn.execute(
                "UPDATE household_facts SET value = ?, confidence = ?, last_confirmed = ? WHERE id = ?",
                (value, min(existing_conf + 0.05, 0.95), now, existing_id),
            )
            self._conn.commit()
            return False

        if value.lower() == existing_value.lower():
            # Different speaker corroborates — boost confidence
            if source_speaker not in speakers:
                speakers.append(source_speaker)
            new_conf = min(existing_conf + 0.10, 0.95)
            new_status = "settled" if new_conf >= 0.85 else existing_status
            self._conn.execute(
                "UPDATE household_facts SET source_speakers = ?, confidence = ?, "
                "conflict_status = ?, last_confirmed = ? WHERE id = ?",
                (json.dumps(speakers), new_conf, new_status, now, existing_id),
            )
            self._conn.commit()
            return False

        # Different speaker, different value → dispute
        disputed = {existing_value: speakers[0] if speakers else "unknown", value: source_speaker}
        self._conn.execute(
            "UPDATE household_facts SET conflict_status = 'disputed', "
            "disputed_values = ?, last_confirmed = ? WHERE id = ?",
            (json.dumps(disputed), now, existing_id),
        )
        self._conn.commit()
        return True

    def get_household_context(self) -> str | None:
        """Return formatted household facts + relationships for LLM injection."""
        now = time.time()
        rows = self._conn.execute(
            "SELECT entity, attribute, value, confidence, conflict_status, disputed_values, source_speakers "
            "FROM household_facts WHERE conflict_status != 'invalidated' "
            "ORDER BY confidence DESC, last_confirmed DESC LIMIT 30"
        ).fetchall()

        rels = self._conn.execute(
            "SELECT person_a, relationship, person_b, confidence FROM inter_person_relationships "
            "ORDER BY confidence DESC, updated_at DESC LIMIT 20"
        ).fetchall()

        if not rows and not rels:
            return None

        lines = []
        if rows:
            lines.append("Household & shared facts:")
            for entity, attr, value, conf, status, disputed_json, speakers_json in rows:
                label = attr.replace("_", " ")
                if status == "disputed" and disputed_json:  # knowledge-row status field, not person_type — disputed-row-status
                    disputed = json.loads(disputed_json)
                    parts = [f"{v} (per {k})" for k, v in disputed.items()]
                    lines.append(f"  - {label}: DISPUTED — {' vs '.join(parts)}")
                else:
                    suffix = ""
                    if conf < 0.70:
                        suffix = " (uncertain)"
                    elif status == "settled":
                        suffix = " (confirmed)"
                    scope_label = f"{entity}: " if entity != "household" else ""
                    lines.append(f"  - {scope_label}{label}: {value}{suffix}")

        if rels:
            lines.append("Known relationships:")
            for a, rel, b, conf in rels:
                suffix = " (uncertain)" if conf < 0.70 else ""
                lines.append(f"  - {a} → {rel.replace('_', ' ')} → {b}{suffix}")

        return "\n".join(lines) if lines else None

    def store_relationship(
        self,
        person_a: str,
        relationship: str,
        person_b: str,
        confidence: float,
        source_speaker: str,
    ) -> None:
        """Upsert an inter-person relationship."""
        now = time.time()
        self._conn.execute(
            """INSERT INTO inter_person_relationships
                   (person_a, relationship, person_b, confidence, source_speaker, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(person_a, relationship, person_b) DO UPDATE SET
                   confidence = MAX(confidence, excluded.confidence),
                   updated_at = excluded.updated_at""",
            (person_a, relationship, person_b, confidence, source_speaker, now, now),
        )
        self._conn.commit()

    def get_shadow_person(self, name: str) -> dict | None:
        """Return a shadow person record by known_name (case-insensitive)."""
        row = self._conn.execute(
            "SELECT shadow_id, known_name, known_via, face_id, voice_id, enrollment_status, facts "
            "FROM shadow_persons WHERE LOWER(known_name) = LOWER(?)",
            (name,),
        ).fetchone()
        if not row:
            return None
        return {
            "shadow_id": row[0], "known_name": row[1], "known_via": json.loads(row[2]),
            "face_id": row[3], "voice_id": row[4], "enrollment_status": row[5],
            "facts": json.loads(row[6]),
        }

    def upsert_shadow_person(
        self,
        name: str,
        via_person_id: str,
        relationship: "str | None",
    ) -> tuple[str, bool]:
        """Create or update a shadow node for a non-enrolled person.

        Session 105 Obs B — SHADOW_NAME_BLOCKLIST rejects pronouns and
        relationship roles ("him", "her", "boyfriend", "friend",
        "boss", etc.) at the write site. These aren't people names —
        they're referents that the LLM sometimes surfaces when the
        actual name isn't known. Writing them as shadow_persons
        pollutes the graph with unlinkable placeholders. When the
        brain later learns the actual name ("her name is Sarah"), the
        shadow can be created at that point with real semantic value.

        Returns ``(shadow_id="", was_new=False)`` for blocked names so
        callers can short-circuit without branching on a separate
        signal.

        Returns ``(shadow_id, was_new)`` — callers inspect ``was_new`` to
        decide whether to log "Shadow node: {name}" (Session 97 Fix 3 —
        2026-04-22 canary showed the log firing twice for the same name
        because the caller didn't know the second call was a no-op update).

        Session 97 Fix 3 refinements:
          - `mention_count` column (migrated via ALTER TABLE); bumped
            every UPDATE so retention/pruning can weight heavily-
            mentioned shadows over one-offs.
          - known_via merge prefers a non-null relationship over null:
            if `Priya said "Anita"` (relationship=None) comes first and
            `Sarah said "my colleague Anita"` (relationship="colleague")
            comes second, the second entry is kept rather than appended
            as a separate via row. Reduces redundant via entries in the
            UI dashboard and keeps Kuzu relationship edges meaningful.
          - Same-via-person mentions collapse into one entry, so repeated
            turns from the same speaker don't inflate the list.
        """
        # Session 105 Obs B — reject pronouns/roles at the write site.
        # Whitespace-normalize + lowercase for comparison against the
        # frozenset. Empty/whitespace-only names also blocked (defensive).
        _name_key = (name or "").strip().lower()
        if not _name_key or _name_key in SHADOW_NAME_BLOCKLIST:
            print(
                f"[BrainDB] upsert_shadow_person: blocked {name!r} "
                f"(pronoun/role — not a real name)"
            )
            return ("", False)
        now = time.time()
        existing = self._conn.execute(
            "SELECT shadow_id, known_via FROM shadow_persons WHERE LOWER(known_name) = LOWER(?)",
            (name,),
        ).fetchone()

        if existing is None:
            shadow_id = f"shadow_{uuid.uuid4().hex[:8]}"
            known_via_entry = json.dumps([
                {"person_id": via_person_id, "relationship": relationship}
            ])
            self._conn.execute(
                "INSERT INTO shadow_persons "
                "(shadow_id, known_name, known_via, first_mentioned, "
                " last_mentioned, mention_count) "
                "VALUES (?, ?, ?, ?, ?, 1)",
                (shadow_id, name, known_via_entry, now, now),
            )
            self._conn.commit()
            return (shadow_id, True)

        shadow_id = existing[0]
        via_list: list = json.loads(existing[1])
        # Merge: if an entry for this via_person_id already exists, prefer
        # the non-null relationship. Otherwise append as a new via entry.
        merged = False
        for entry in via_list:
            if entry.get("person_id") != via_person_id:
                continue
            merged = True
            existing_rel = entry.get("relationship")
            # Upgrade null → concrete; never downgrade concrete → null.
            if not existing_rel and relationship:
                entry["relationship"] = relationship
            break
        if not merged:
            via_list.append(
                {"person_id": via_person_id, "relationship": relationship}
            )
        self._conn.execute(
            "UPDATE shadow_persons SET known_via = ?, last_mentioned = ?, "
            "mention_count = mention_count + 1 WHERE shadow_id = ?",
            (json.dumps(via_list), now, shadow_id),
        )
        self._conn.commit()
        return (shadow_id, False)

    def add_shadow_person_fact(self, name: str, attribute: str, value: str, confidence: float) -> None:
        """Add a known fact about a shadow person (from what others said about them)."""
        now = time.time()
        existing = self._conn.execute(
            "SELECT shadow_id, facts FROM shadow_persons WHERE LOWER(known_name) = LOWER(?)",
            (name,),
        ).fetchone()
        if not existing:
            return
        shadow_id, facts_json = existing
        facts: list = json.loads(facts_json)
        # Update or append
        for f in facts:
            if f["attribute"] == attribute:
                f["value"] = value
                f["confidence"] = confidence
                break
        else:
            facts.append({"attribute": attribute, "value": value, "confidence": confidence})
        self._conn.execute(
            "UPDATE shadow_persons SET facts = ?, last_mentioned = ? WHERE shadow_id = ?",
            (json.dumps(facts), now, shadow_id),
        )
        self._conn.commit()

    def prune_shadow_persons(self, max_age_days: int = 90) -> int:
        """Remove stale shadow persons that were never enrolled and are very old."""
        cutoff = time.time() - max_age_days * 86400
        cur = self._conn.execute(
            "DELETE FROM shadow_persons WHERE enrollment_status = 'pending' AND last_mentioned < ?",
            (cutoff,),
        )
        self._conn.commit()
        return cur.rowcount

    def list_shadow_persons(self, status: str = "pending") -> list[dict]:
        """Return shadow persons by enrollment_status, newest-mentioned first."""
        rows = self._conn.execute(
            """SELECT shadow_id, known_name, known_via, face_id, enrollment_status, facts,
                      first_mentioned, last_mentioned
               FROM shadow_persons
               WHERE enrollment_status = ?
               ORDER BY last_mentioned DESC""",
            (status,),
        ).fetchall()
        return [
            {
                "shadow_id":         r[0],
                "known_name":        r[1],
                "known_via":         json.loads(r[2] or "[]"),
                "face_id":           r[3],
                "enrollment_status": r[4],
                "fact_count":        len(json.loads(r[5] or "[]")),
                "first_mentioned":   r[6],
                "last_mentioned":    r[7],
            }
            for r in rows
        ]

    def migrate_entity_name(self, old_name: str, new_name: str, person_id: str | None = None) -> int:
        """Rename entity in knowledge rows when a stranger's identity is confirmed.

        Uses person_id filter when provided — critical because multiple strangers
        share the default entity name 'visitor' and a plain entity-only UPDATE
        would corrupt all of them at once.

        Returns the number of rows updated.
        """
        # Capture BEFORE any write. When called inside transaction(), BEGIN IMMEDIATE
        # has already been issued so in_transaction=True → skip inner commit.
        # When called standalone, no BEGIN yet → in_transaction=False → commit at end.
        _in_outer_tx = self._conn.in_transaction
        if person_id:
            cur = self._conn.execute(
                "UPDATE knowledge SET entity = ? WHERE entity = ? AND person_id = ?",
                (new_name, old_name, person_id),
            )
        else:
            cur = self._conn.execute(
                "UPDATE knowledge SET entity = ? WHERE entity = ?",
                (new_name, old_name),
            )
        if not _in_outer_tx:
            self._conn.commit()
        n = cur.rowcount
        print(f"[BrainDB] migrate_entity_name: '{old_name}' → '{new_name}' ({n} rows updated)")
        return n

    def get_knowledge_rows_for_kuzu(self, person_id: str, entity: str) -> list[dict]:
        """Return all active knowledge rows for a person+entity pair.

        Used after migrate_entity_name to feed the Kuzu graph rebuild.
        """
        rows = self._conn.execute(
            """SELECT attribute, value, confidence, is_temporal, valid_until,
                      valid_at, source_turn_id, created_at
               FROM knowledge
               WHERE person_id = ? AND entity = ? AND invalidated_at IS NULL""",
            (person_id, entity),
        ).fetchall()
        return [
            {
                "attribute": r[0], "value": r[1], "confidence": r[2],
                "is_temporal": r[3], "valid_until": r[4], "valid_at": r[5],
                "source_turn_id": r[6], "created_at": r[7],
            }
            for r in rows
        ]

    def promote_shadow_to_confirmed(self, name: str, face_id: str) -> bool:
        """Link a shadow person to their confirmed face_id and copy their facts
        into the knowledge table.

        Returns True if a matching shadow node was found and promoted.
        """
        # Capture BEFORE any write — same inner-commit gate as migrate_entity_name.
        _in_outer_tx = self._conn.in_transaction
        now = time.time()
        row = self._conn.execute(
            "SELECT shadow_id, facts FROM shadow_persons WHERE LOWER(known_name) = LOWER(?)",
            (name,),
        ).fetchone()
        if not row:
            return False

        shadow_id, facts_json = row

        # Mark the shadow node as confirmed and record the face identity
        self._conn.execute(
            "UPDATE shadow_persons SET face_id = ?, enrollment_status = 'confirmed' WHERE shadow_id = ?",
            (face_id, shadow_id),
        )

        # Copy shadow facts (gathered from what others said) into the knowledge table
        # so they appear in get_context() alongside extracted conversation facts.
        facts: list = json.loads(facts_json)
        inserted = 0
        for f in facts:
            if not f.get("attribute") or not f.get("value"):
                continue
            # Session 95 3A.4.5: shadow facts are what OTHERS said about the
            # person before we met them. They're attributed to the person
            # (owner = the promoted face_id) so they belong in the 'personal'
            # tier — same reasoning as any other owner-scoped fact. Previously
            # this INSERT fell back to the column DEFAULT ('public') which
            # would have leaked on non-owner queries under the new
            # visibility_clause.
            self._conn.execute(
                """INSERT INTO knowledge
                       (source_turn_id, person_id, entity, entity_type, attribute,
                        value, confidence, is_temporal, valid_until, valid_at, agent,
                        created_at, privacy_level)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (0, face_id, name, "person", f["attribute"], f["value"],
                 f.get("confidence", 0.70), 0, None, now, "shadow_promotion", now,
                 PRIVACY_LEVEL_DEFAULT),
            )
            inserted += 1

        if not _in_outer_tx:
            self._conn.commit()
        print(f"[BrainDB] Shadow '{name}' promoted (face_id={face_id}, {inserted} facts copied)")
        return True

    # ── Object pattern questions ───────────────────────────────────────────────

    def get_sighting_stats(self, days: int = 7) -> list[dict]:
        """Aggregate object sighting statistics for the last N days.

        Returns per-class summary suitable for pattern analysis: total times seen,
        distinct zones, first/last seen timestamps, and associated person names.
        Objects seen only once are excluded (no pattern possible).
        """
        cutoff = time.time() - days * 86400
        rows = self._conn.execute(
            """SELECT
                   object_class,
                   SUM(times_seen)                          AS total_times,
                   COUNT(*)                                 AS distinct_sightings,
                   COUNT(DISTINCT location_zone)            AS distinct_zones,
                   GROUP_CONCAT(DISTINCT location_zone) AS zones,
                   MIN(first_seen_at)                  AS first_seen,
                   MAX(last_seen_at)                   AS last_seen,
                   GROUP_CONCAT(DISTINCT person_context) AS persons
               FROM object_sightings
               WHERE last_seen_at > ?
               GROUP BY object_class
               HAVING total_times > 2
               ORDER BY total_times DESC
               LIMIT 20""",
            (cutoff,),
        ).fetchall()
        return [
            {
                "object_class":       r[0], "total_times":      r[1],
                "distinct_sightings": r[2], "distinct_zones":    r[3],
                "zones":              r[4], "first_seen":        r[5],
                "last_seen":          r[6], "persons":           r[7],
            }
            for r in rows
        ]

    def store_pattern_question(self, question: str, pattern_key: str) -> bool:
        """Store a pending question, skipping if the same pattern_key already exists.

        Returns True if a new row was inserted.
        """
        existing = self._conn.execute(
            "SELECT id FROM object_pattern_questions WHERE pattern_key = ?",
            (pattern_key,),
        ).fetchone()
        if existing:
            return False
        self._conn.execute(
            """INSERT INTO object_pattern_questions (question, pattern_key, created_at)
               VALUES (?, ?, ?)""",
            (question, pattern_key, time.time()),
        )
        self._conn.commit()
        return True

    def get_next_pending_question(self) -> dict | None:
        """Return the oldest unasked pattern question, or None if none pending."""
        row = self._conn.execute(
            """SELECT id, question, pattern_key FROM object_pattern_questions
               WHERE asked = 0
               ORDER BY created_at ASC
               LIMIT 1""",
        ).fetchone()
        if not row:
            return None
        return {"id": row[0], "text": row[1], "pattern_key": row[2]}

    def mark_question_asked(self, qid: int) -> None:
        """Mark a question as asked so it is not served again."""
        self._conn.execute(
            "UPDATE object_pattern_questions SET asked = 1, asked_at = ? WHERE id = ?",
            (time.time(), qid),
        )
        self._conn.commit()

    def pending_question_count(self) -> int:
        """Number of questions still waiting to be asked."""
        return self._conn.execute(
            "SELECT COUNT(*) FROM object_pattern_questions WHERE asked = 0"
        ).fetchone()[0]

    # ── Social mentions ────────────────────────────────────────────────────────
    def upsert_social_mention(
        self,
        source_person_id: str,
        mentioned_name: str,
        relationship: str | None,
        new_attributes: list[str],
    ) -> None:
        """Store or update a person the best friend has mentioned.

        Merges new attributes with existing ones (case-insensitive dedup).
        Updates relationship if the existing row has none.
        """
        row = self._conn.execute(
            "SELECT id, attributes FROM social_mentions "
            "WHERE source_person_id=? AND LOWER(mentioned_name)=LOWER(?) LIMIT 1",
            (source_person_id, mentioned_name),
        ).fetchone()
        now = time.time()
        if row:
            existing = json.loads(row[1])
            seen = {a.lower() for a in existing}
            merged = existing + [a for a in new_attributes if a.lower() not in seen]
            self._conn.execute(
                "UPDATE social_mentions "
                "SET attributes=?, relationship=COALESCE(?,relationship), updated_at=? "
                "WHERE id=?",
                (json.dumps(merged), relationship, now, row[0]),
            )
        else:
            self._conn.execute(
                "INSERT INTO social_mentions "
                "(source_person_id, mentioned_name, relationship, attributes, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (source_person_id, mentioned_name, relationship, json.dumps(new_attributes), now, now),
            )
        self._conn.commit()

    def find_social_mention_overlaps(self, name_query: str) -> list[dict]:
        """Find social mentions matching name_query from any source_person_id.

        Case-insensitive LIKE search. Used by ProactiveNudgeAgent to find
        the same person mentioned by multiple different speakers.
        """
        rows = self._conn.execute(
            "SELECT id, source_person_id, mentioned_name, relationship, attributes "
            "FROM social_mentions WHERE LOWER(mentioned_name) LIKE LOWER(?) "
            "ORDER BY updated_at DESC",
            (f"%{name_query}%",),
        ).fetchall()
        return [
            {
                "id":               r[0],
                "source_person_id": r[1],
                "name":             r[2],
                "relationship":     r[3],
                "attributes":       json.loads(r[4]),
            }
            for r in rows
        ]

    def get_all_social_mentions(self, limit: int = 200) -> list[dict]:
        """Return social mentions, newest-updated first."""
        rows = self._conn.execute(
            "SELECT id, source_person_id, mentioned_name, relationship, attributes "
            "FROM social_mentions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "id":               r[0],
                "source_person_id": r[1],
                "name":             r[2],
                "relationship":     r[3],
                "attributes":       json.loads(r[4]),
            }
            for r in rows
        ]

    # ── Episodes ───────────────────────────────────────────────────────────────

    def store_episode(
        self,
        person_id:        str,
        episode:          dict,
        session_start_ts: float,
        session_end_ts:   float,
        turn_count:       int,
    ) -> int:
        now = time.time()
        cur = self._conn.execute(
            """INSERT INTO episodes
               (person_id, session_start_ts, session_end_ts, mood,
                key_topics, promises_made, questions_asked, emotional_arc,
                significance, turn_count, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                person_id, session_start_ts, session_end_ts,
                episode.get("mood"),
                json.dumps(episode.get("key_topics") or []),
                json.dumps(episode.get("promises_made") or []),
                json.dumps(episode.get("questions_asked") or []),
                episode.get("emotional_arc"),
                float(episode.get("significance_score") or 0.5),
                turn_count,
                now,
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_recent_episodes(self, person_id: str, limit: int = 5) -> list[dict]:
        rows = self._conn.execute(
            """SELECT mood, key_topics, promises_made, questions_asked,
                      emotional_arc, significance, turn_count, session_end_ts
               FROM episodes WHERE person_id = ?
               ORDER BY session_end_ts DESC LIMIT ?""",
            (person_id, limit),
        ).fetchall()
        return [
            {
                "mood":            r[0],
                "key_topics":      json.loads(r[1]),
                "promises_made":   json.loads(r[2]),
                "questions_asked": json.loads(r[3]),
                "emotional_arc":   r[4],
                "significance":    r[5],
                "turn_count":      r[6],
                "session_end_ts":  r[7],
            }
            for r in rows
        ]

    def get_episode_topics_since(self, since_ts: float) -> list[dict]:
        """All topics across all persons since since_ts — used for cross-person matching."""
        rows = self._conn.execute(
            "SELECT person_id, key_topics, session_end_ts FROM episodes "
            "WHERE session_end_ts > ? ORDER BY session_end_ts DESC",
            (since_ts,),
        ).fetchall()
        return [
            {
                "person_id":      r[0],
                "key_topics":     json.loads(r[1]),
                "session_end_ts": r[2],
            }
            for r in rows
        ]

    # ── Presence log ───────────────────────────────────────────────────────────

    # ── Phase 3B.6 — room synthesis storage ────────────────────────────────
    def store_room_summary(
        self,
        room_session_id: str,
        started_at: float,
        ended_at: float,
        speaker_pids: "list[str]",
        summary: str,
        topic_tags: "list[str] | None" = None,
        safety_flags: "list[dict] | None" = None,
    ) -> None:
        """Phase 3B.6 — persist room-end synthesis result.

        One row per room_session_id (PRIMARY KEY enforces that). If a
        retry hits the same id (e.g. the synthesis task was re-scheduled
        after a partial write), the INSERT OR REPLACE semantic keeps
        the freshest render.
        """
        import json as _json_rs
        self._conn.execute(
            "INSERT OR REPLACE INTO room_summaries "
            "(room_session_id, started_at, ended_at, speaker_pids, "
            " summary, topic_tags, safety_flags, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                room_session_id, started_at, ended_at,
                _json_rs.dumps(list(speaker_pids)),
                summary,
                _json_rs.dumps(list(topic_tags or [])),
                _json_rs.dumps(list(safety_flags or [])),
                time.time(),
            ),
        )
        self._conn.commit()

    def get_recent_room_context(
        self,
        person_id: str,
        hours: float = 24.0,
    ) -> "dict | None":
        """Phase 3B.6 — fetch the most recent room summary that included
        ``person_id`` within the last ``hours``.

        Returns a dict with the deserialized row (speaker_pids,
        topic_tags, safety_flags as lists) or ``None`` if no qualifying
        room. ``person_id in speaker_pids`` is the membership gate —
        prevents leaking other people's rooms to someone who wasn't
        there.
        """
        import json as _json_rr
        if not person_id:
            return None
        cutoff = time.time() - max(0.0, hours) * 3600.0
        rows = self._conn.execute(
            "SELECT room_session_id, started_at, ended_at, speaker_pids, "
            "summary, topic_tags, safety_flags "
            "FROM room_summaries WHERE ended_at > ? ORDER BY ended_at DESC",
            (cutoff,),
        ).fetchall()
        for row in rows:
            (room_id, started_at, ended_at, pids_json,
             summary, topics_json, flags_json) = row
            try:
                pids = _json_rr.loads(pids_json) or []
            except Exception:
                pids = []
            if person_id not in pids:
                continue
            def _safe_loads(raw):
                try:
                    return _json_rr.loads(raw) if raw else []
                except Exception:
                    return []
            return {
                "room_session_id": room_id,
                "started_at":      started_at,
                "ended_at":        ended_at,
                "speaker_pids":    pids,
                "summary":         summary,
                "topic_tags":      _safe_loads(topics_json),
                "safety_flags":    _safe_loads(flags_json),
            }
        return None

    def log_presence(self, person_id: str, arrived_at: float, left_at: float) -> None:
        dt = datetime.datetime.fromtimestamp(arrived_at)
        self._conn.execute(
            """INSERT INTO presence_log
               (person_id, arrived_at, left_at, duration_s,
                day_of_week, hour_of_day, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                person_id, arrived_at, left_at,
                left_at - arrived_at,
                dt.weekday(), dt.hour,
                time.time(),
            ),
        )
        self._conn.commit()

    def get_presence_history(self, person_id: str, limit: int = 30) -> list[dict]:
        rows = self._conn.execute(
            """SELECT arrived_at, left_at, duration_s, day_of_week, hour_of_day
               FROM presence_log WHERE person_id = ?
               ORDER BY arrived_at DESC LIMIT ?""",
            (person_id, limit),
        ).fetchall()
        return [
            {
                "arrived_at":  r[0], "left_at":     r[1],
                "duration_s":  r[2], "day_of_week": r[3],
                "hour_of_day": r[4],
            }
            for r in rows
        ]

    def get_presence_count(self, person_id: str) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM presence_log WHERE person_id = ?", (person_id,)
        ).fetchone()[0]

    # ── Proactive nudges ───────────────────────────────────────────────────────

    def store_nudge(
        self,
        target_person_id: str,
        nudge_type:       str,
        content:          str,
        confidence:       float,
        metadata:         dict,
        expires_at:       float | None = None,
    ) -> int:
        cur = self._conn.execute(
            """INSERT INTO proactive_nudges
               (target_person_id, nudge_type, content, metadata,
                confidence, generated_at, expires_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                target_person_id, nudge_type, content,
                json.dumps(metadata), confidence,
                time.time(), expires_at,
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_pending_nudges(self, target_person_id: str, limit: int = 3) -> list[dict]:
        now = time.time()
        rows = self._conn.execute(
            """SELECT id, nudge_type, content, confidence, metadata
               FROM proactive_nudges
               WHERE target_person_id = ?
                 AND injected_at IS NULL
                 AND dismissed_at IS NULL
                 AND (expires_at IS NULL OR expires_at > ?)
               ORDER BY confidence DESC, generated_at ASC
               LIMIT ?""",
            (target_person_id, now, limit),
        ).fetchall()
        return [
            {
                "id":         r[0], "nudge_type": r[1],
                "content":    r[2], "confidence": r[3],
                "metadata":   json.loads(r[4]),
            }
            for r in rows
        ]

    def get_recent_visitor_alerts(
        self,
        target_person_id: str,
        hours_back:       float = 24.0,
    ) -> list[dict]:
        """Return VISITOR_ALERT nudges for best_friend within a recent window,
        regardless of injection status.

        Used by the Ollama fallback path (pipeline.py) when the classifier
        gate rejects a `report_identity_mismatch` call on an owner query
        like "who were you talking to?". The rejected turn then routes
        through the offline retry — Ollama has zero context that a visitor
        even existed, so without this read it confabulates "there was no
        one else" (Session 96 Bug 2). Pulling recent VISITOR_ALERT nudges
        (injected OR pending) and injecting the visitor's name + turn count
        + topic hint into Ollama's system_note gives the offline path
        enough grounding to answer honestly.

        Injection status is intentionally ignored: if the alert was already
        shown to the user earlier, it's still relevant to a current owner
        query about the same window. Dismissed nudges and expired nudges
        ARE filtered — those represent explicit user closure.
        """
        cutoff = time.time() - (hours_back * 3600)
        rows = self._conn.execute(
            """SELECT id, content, metadata, generated_at
               FROM proactive_nudges
               WHERE target_person_id = ?
                 AND nudge_type = 'VISITOR_ALERT'
                 AND dismissed_at IS NULL
                 AND (expires_at IS NULL OR expires_at > ?)
                 AND generated_at >= ?
               ORDER BY generated_at DESC""",
            (target_person_id, time.time(), cutoff),
        ).fetchall()
        return [
            {
                "id":           r[0],
                "content":      r[1],
                "metadata":     json.loads(r[2]) if r[2] else {},
                "generated_at": r[3],
            }
            for r in rows
        ]

    def update_visitor_alert_for_promoted_person(
        self,
        person_id: str,
        new_name: str,
    ) -> int:
        """Session 114 Part 5 — when a stranger gets promoted to 'known'
        via update_person_name, sync any pre-promotion VISITOR_ALERT
        nudges so the post-promotion read returns one canonical row
        (correct name + visitor_type='known') rather than stacking two
        alerts about the same visitor.

        Updates `proactive_nudges` rows where ``nudge_type='VISITOR_ALERT'``
        AND ``metadata.visitor_id == person_id``. Read-modify-write on
        the JSON ``metadata`` column (SQLite portable — no JSON_SET
        dependency). Also rewrites the row's ``content`` to use the new
        name so the rendered visitor description stays consistent.

        Returns the number of rows updated.
        """
        # Capture BEFORE any write — same inner-commit gate as migrate_entity_name.
        _in_outer_tx = self._conn.in_transaction
        rows = self._conn.execute(
            "SELECT id, content, metadata FROM proactive_nudges "
            "WHERE nudge_type = 'VISITOR_ALERT' "
            "AND dismissed_at IS NULL",
        ).fetchall()
        updated = 0
        for nudge_id, content, meta_json in rows:
            try:
                meta = json.loads(meta_json) if meta_json else {}
            except Exception:
                meta = {}
            if meta.get("visitor_id") != person_id:
                continue
            old_name = meta.get("visitor_name") or ""
            meta["visitor_name"] = new_name
            meta["visitor_type"] = "known"
            # P0.S7.5.1 D1 — regex-replace the [visitor_name:...] marker
            # regardless of what placeholder is currently in content. The
            # previous literal-substring check (Session 114 Part 5) only
            # fired when the old_name from metadata matched the marker —
            # but _run_visitor_alert writes ASYMMETRIC content
            # (marker="[visitor_name:unknown]") and metadata
            # (visitor_name="visitor") for stranger sessions, so the old
            # check silently no-op'd on every stranger promotion.
            # Regex-replace is robust to the asymmetry (and to any future
            # placeholder drift).
            #
            # Use a LAMBDA replacement (callable) so the replacement
            # string is used verbatim — no interpretation of regex
            # backreferences (\1, \g<name>, \\). Defense-in-depth against
            # future visitor names containing regex special chars in
            # replacement-string context.
            #
            # Canary 2 evidence: 2026-05-19 terminal_output.md:857 + :1187.
            new_content = content
            if content:
                new_marker = f"[visitor_name:{new_name}]"
                new_content = re.sub(
                    r"\[visitor_name:[^\]]+\]",
                    lambda _m: new_marker,
                    content,
                )
            self._conn.execute(
                "UPDATE proactive_nudges SET content = ?, metadata = ? "
                "WHERE id = ?",
                (new_content, json.dumps(meta), nudge_id),
            )
            updated += 1
        if updated:
            if not _in_outer_tx:
                self._conn.commit()
            print(
                f"[BrainDB] update_visitor_alert_for_promoted_person: "
                f"updated {updated} alert(s) for {person_id} → {new_name!r}"
            )
        return updated

    def mark_nudge_injected(self, nudge_id: int) -> None:
        self._conn.execute(
            "UPDATE proactive_nudges SET injected_at = ? WHERE id = ?",
            (time.time(), nudge_id),
        )
        self._conn.commit()

    def dismiss_nudge(self, nudge_id: int) -> None:
        self._conn.execute(
            "UPDATE proactive_nudges SET dismissed_at = ? WHERE id = ?",
            (time.time(), nudge_id),
        )
        self._conn.commit()

    def nudge_exists(
        self,
        target_person_id: str,
        nudge_type:       str,
        content_key:      str,
    ) -> bool:
        """Dedup check — is an equivalent pending nudge already stored?"""
        now = time.time()
        row = self._conn.execute(
            """SELECT 1 FROM proactive_nudges
               WHERE target_person_id = ?
                 AND nudge_type = ?
                 AND content LIKE ?
                 AND injected_at IS NULL
                 AND dismissed_at IS NULL
                 AND (expires_at IS NULL OR expires_at > ?)
               LIMIT 1""",
            (target_person_id, nudge_type, f"%{content_key}%", now),
        ).fetchone()
        return row is not None

    # ── Watchdog alerts ────────────────────────────────────────────────────────

    def store_alert(
        self,
        alert_type: str,
        severity:   str,
        message:    str,
        metadata:   dict,
    ) -> int:
        cur = self._conn.execute(
            """INSERT INTO watchdog_alerts
               (alert_type, severity, message, metadata, created_at)
               VALUES (?,?,?,?,?)""",
            (alert_type, severity, message, json.dumps(metadata), time.time()),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_unresolved_alerts(self, limit: int = 10) -> list[dict]:
        rows = self._conn.execute(
            """SELECT id, alert_type, severity, message, metadata, created_at
               FROM watchdog_alerts WHERE resolved = 0
               ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [
            {
                "id":         r[0], "alert_type": r[1],
                "severity":   r[2], "message":    r[3],
                "metadata":   json.loads(r[4]), "created_at": r[5],
            }
            for r in rows
        ]

    def resolve_alert(self, alert_id: int) -> None:
        self._conn.execute(
            "UPDATE watchdog_alerts SET resolved = 1, resolved_at = ? WHERE id = ?",
            (time.time(), alert_id),
        )
        self._conn.commit()

    # ── VISION_ROADMAP P1.7a — intent divergence log ─────────────────────────
    def log_intent_divergence(
        self,
        *,
        tool_proposed:         str,
        gate_decision:         str,
        user_text:             "str | None"   = None,
        person_id:             "str | None"   = None,
        turn_id:               "int | None"   = None,
        structured_intent:     "str | None"   = None,
        structured_extracted:  "str | None"   = None,
        structured_confidence: "float | None" = None,
        mode:                  str            = "gate",
    ) -> int:
        """One row per gated-tool decision routed through _intent_allows
        (or one passive ``mode='shadow'`` sample from the Phase 5
        canary).

        Called from pipeline._execute_tool's gate-wiring sites. All classifier-
        sidecar fields are nullable — set them when the classifier fired, leave
        as None when the classifier was unavailable (timeout / parse fail /
        shadow-mode disabled) and the regex fallback handled the decision.
        ``gate_decision`` encodes what actually happened (e.g. ``'allow'``,
        ``'reject: intent=casual_conversation expected=assign_own_name'``,
        ``'regex_fallback_allow'``, ``'shadow_sample'``). Phase 5 drift
        detection queries this table to compute classifier-vs-regex
        divergence rates and inspect shadow samples for offline review.

        ``mode`` (Phase 5 / Session 119): defaults to ``'gate'`` so all
        existing call sites keep working unchanged. The 1% canary
        shadow sampler in pipeline.conversation_turn passes
        ``mode='shadow'`` for passive observability rows.

        Keyword-only signature to avoid accidental positional-argument
        misalignment as the schema evolves."""
        cur = self._conn.execute(
            """INSERT INTO intent_divergences
               (turn_id, person_id, user_text, structured_intent,
                structured_extracted, structured_confidence, tool_proposed,
                gate_decision, ts, mode)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                turn_id, person_id, user_text, structured_intent,
                structured_extracted, structured_confidence, tool_proposed,
                gate_decision, time.time(), mode,
            ),
        )
        self._safe_commit()
        return cur.lastrowid

    def get_recent_intent_divergences(self, limit: int = 50) -> list[dict]:
        """Phase 5 drift-detection query surface. Most-recent-first; oldest
        rows fall off once limit is hit. Returns dicts mirroring the schema."""
        rows = self._conn.execute(
            """SELECT id, turn_id, person_id, user_text, structured_intent,
                      structured_extracted, structured_confidence,
                      tool_proposed, gate_decision, reviewed, ts
               FROM intent_divergences
               ORDER BY ts DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [
            {
                "id": r[0], "turn_id": r[1], "person_id": r[2],
                "user_text": r[3], "structured_intent": r[4],
                "structured_extracted": r[5], "structured_confidence": r[6],
                "tool_proposed": r[7], "gate_decision": r[8],
                "reviewed": r[9], "ts": r[10],
            }
            for r in rows
        ]

    def resolve_alerts_by_type(self, alert_type: str) -> None:
        """Resolve all open alerts of a given type in one SQL UPDATE."""
        self._conn.execute(
            "UPDATE watchdog_alerts SET resolved = 1, resolved_at = ? "
            "WHERE alert_type = ? AND resolved = 0",
            (time.time(), alert_type),
        )
        self._conn.commit()

    def unresolved_alert_exists(self, alert_type: str) -> bool:
        """Dedup — prevents filing the same alert twice while it's still open."""
        row = self._conn.execute(
            "SELECT 1 FROM watchdog_alerts WHERE alert_type = ? AND resolved = 0 LIMIT 1",
            (alert_type,),
        ).fetchone()
        return row is not None

    def get_recent_alerts_summary(self) -> str | None:
        alerts = self.get_unresolved_alerts(limit=5)
        if not alerts:
            return None
        now = time.time()
        parts = []
        for a in alerts:
            age_m = int((now - a["created_at"]) / 60)
            parts.append(f"{a['alert_type']} ({a['severity']}, {age_m}m ago)")
        return f"{len(alerts)} unresolved alert(s): " + ", ".join(parts)

    def wipe(self) -> None:
        """Clear all brain.db tables (SQLite only).

        WARNING: Do NOT call this directly in production code.
        Always use BrainOrchestrator.wipe() which also clears the Kuzu graph.
        Calling this alone leaves the graph with stale entity nodes that no
        longer match the wiped SQLite knowledge rows.
        Direct calls are only safe in tests that don't use GraphDB.
        """
        self._conn.executescript("""
            DELETE FROM knowledge;
            DELETE FROM schema_catalog;
            DELETE FROM agent_log;
            DELETE FROM prompt_prefs;
            DELETE FROM object_sightings;
            DELETE FROM object_pattern_questions;
            DELETE FROM object_patterns;
            DELETE FROM social_mentions;
            DELETE FROM episodes;
            DELETE FROM presence_log;
            DELETE FROM proactive_nudges;
            DELETE FROM watchdog_alerts;
            DELETE FROM household_facts;
            DELETE FROM inter_person_relationships;
            DELETE FROM shadow_persons;
            DELETE FROM predicate_stats;
            UPDATE brain_state SET last_turn_id = 0, updated_at = 0 WHERE singleton = 1;
        """)
        self._conn.commit()

    def delete_person_data(self, person_ids: list) -> int:
        """Batch-delete all brain.db rows for a list of person_ids.

        Covers ALL tables that carry person-scoped data. Returns total rows removed.
        Called by BrainOrchestrator.prune_brain_data() after faces.db stranger pruning
        and by person_lifecycle.delete_person_everywhere() for explicit deletion.
        """
        if not person_ids:
            return 0
        ph = ",".join("?" * len(person_ids))
        total = 0
        # P0.S9 D2: explicit transaction wrap (was implicit single-commit pre-fix).
        # Atomicity equivalent (BEGIN IMMEDIATE / COMMIT contract owned by the
        # context manager); matches P0.9.1 ratchet for cross-DB destructive ops.
        with self.transaction():
            for table in ("knowledge", "presence_log", "episodes", "prompt_prefs"):
                cur = self._conn.execute(
                    f"DELETE FROM {table} WHERE person_id IN ({ph})", person_ids
                )
                total += cur.rowcount
            cur = self._conn.execute(
                f"DELETE FROM proactive_nudges WHERE target_person_id IN ({ph})", person_ids
            )
            total += cur.rowcount
            cur = self._conn.execute(
                f"DELETE FROM social_mentions WHERE source_person_id IN ({ph})", person_ids
            )
            total += cur.rowcount
            cur = self._conn.execute(
                f"DELETE FROM inter_person_relationships WHERE person_a IN ({ph}) OR source_speaker IN ({ph})",
                person_ids + person_ids,
            )
            total += cur.rowcount
            # household_facts.source_speakers is a JSON list of person_ids — remove each deleted id.
            for pid in person_ids:
                rows = self._conn.execute(
                    "SELECT id, source_speakers FROM household_facts WHERE source_speakers LIKE ?",
                    (f'%{pid}%',),
                ).fetchall()
                for row_id, ss_json in rows:
                    try:
                        speakers = json.loads(ss_json or "[]")
                    except (ValueError, TypeError):
                        speakers = []
                    updated = [s for s in speakers if s != pid]
                    if updated != speakers:
                        self._conn.execute(
                            "UPDATE household_facts SET source_speakers = ? WHERE id = ?",
                            (json.dumps(updated), row_id),
                        )
                        total += 1
        # NO trailing self._conn.commit() — transaction context manager owns commit.
        return total

    def prune_shadows_mentioning(self, person_id: str, person_name: str) -> int:
        """Remove references to person_id from shadow_persons.known_via JSON.

        Shadows whose known_via becomes empty after removal are deleted entirely.
        Returns the number of shadow rows modified or deleted.
        """
        rows = self._conn.execute(
            "SELECT shadow_id, known_via FROM shadow_persons"
        ).fetchall()
        affected = 0
        # P0.S9 D2: explicit transaction wrap (was implicit single-commit pre-fix).
        with self.transaction():
            for shadow_id, kv_json in rows:
                try:
                    known_via = json.loads(kv_json or "[]")
                except (ValueError, TypeError):
                    known_via = []
                new_via = [entry for entry in known_via if entry.get("person_id") != person_id]
                if len(new_via) == len(known_via):
                    continue
                affected += 1
                if new_via:
                    self._conn.execute(
                        "UPDATE shadow_persons SET known_via = ? WHERE shadow_id = ?",
                        (json.dumps(new_via), shadow_id),
                    )
                else:
                    self._conn.execute("DELETE FROM shadow_persons WHERE shadow_id = ?", (shadow_id,))
        # NO trailing self._conn.commit() — transaction context manager owns commit.
        return affected

    # ── P0.X graph-schema public API ─────────────────────────────────────────

    def get_graph_schema_version(self) -> int:
        """Return the currently stored graph schema version from brain_state."""
        return self._conn.execute(
            "SELECT graph_schema_version FROM brain_state WHERE singleton = 1"
        ).fetchone()[0]

    def update_graph_schema_version(self, version: int) -> None:
        """Commit a new graph schema version to brain_state.

        Commits immediately — caller (BrainOrchestrator._ensure_graph_sync)
        needs the version durable before touching Kuzu so a crash between the
        SQL commit and the Kuzu rebuild doesn't re-trigger the schema-upgrade
        path on next boot (sentinel handles the rebuild instead).
        """
        self._conn.execute(
            "UPDATE brain_state SET graph_schema_version = ? WHERE singleton = 1",
            (version,),
        )
        self._conn.commit()

    def count_active_knowledge_entities(self) -> int:
        """Return the count of distinct active entities in knowledge.

        Used by BrainOrchestrator._ensure_graph_sync for boot-time divergence
        detection: Kuzu has one Entity node per unique entity name, so
        COUNT(DISTINCT entity) (not COUNT(*)) is the correct comparand.
        """
        return self._conn.execute(
            "SELECT COUNT(DISTINCT entity) FROM knowledge "
            "WHERE invalidated_at IS NULL"
        ).fetchone()[0]

    # ── P0.X layering-cleanup wrappers ───────────────────────────────────────
    # Raw _conn accesses scattered across BrainOrchestrator and SchemaNormAgent
    # have been replaced with these public methods so test_layering_invariants
    # can enforce the boundary (Step 2.H).

    def count_schema_catalog_entries(self) -> int:
        """Return COUNT(*) of schema_catalog rows."""
        return self._conn.execute(
            "SELECT COUNT(*) FROM schema_catalog"
        ).fetchone()[0]

    def get_knowledge_topic_tags_for_persons(
        self, person_ids: list[str], since: float, until: float
    ) -> list[str]:
        """Return top-10 entity names by frequency for the given persons in [since, until]."""
        if not person_ids:
            return []
        placeholders = ",".join("?" for _ in person_ids)
        rows = self._conn.execute(
            f"SELECT entity, COUNT(*) AS n FROM knowledge "
            f"WHERE person_id IN ({placeholders}) "
            f"AND created_at >= ? AND created_at <= ? "
            f"GROUP BY entity ORDER BY n DESC LIMIT 10",
            (*person_ids, since, until),
        ).fetchall()
        return [entity for entity, _n in rows if entity]

    def get_knowledge_rows_for_persons(
        self, person_ids: list[str], since: float, until: float
    ) -> list[tuple[str, str, str, str]]:
        """Return (person_id, entity, attribute, value) tuples for the given persons in [since, until]."""
        if not person_ids:
            return []
        placeholders = ",".join("?" for _ in person_ids)
        rows = self._conn.execute(
            f"SELECT person_id, entity, attribute, value FROM knowledge "
            f"WHERE person_id IN ({placeholders}) "
            f"AND created_at >= ? AND created_at <= ? "
            f"AND invalidated_at IS NULL",
            (*person_ids, since, until),
        ).fetchall()
        return list(rows)

    def get_true_valued_attributes(self, person_id: str) -> list[str]:
        """Return distinct attributes whose value is 'true' or 'yes' for person."""
        rows = self._conn.execute(
            "SELECT DISTINCT attribute FROM knowledge "
            "WHERE person_id = ? AND invalidated_at IS NULL "
            "AND (value = 'true' OR value = 'yes')",
            (person_id,),
        ).fetchall()
        return [r[0] for r in rows if r[0]]

    def get_shadow_person_names_since(self, cutoff: float) -> list[str]:
        """Return known_name values from shadow_persons last_mentioned >= cutoff."""
        rows = self._conn.execute(
            "SELECT known_name FROM shadow_persons WHERE last_mentioned >= ?",
            (cutoff,),
        ).fetchall()
        return [r[0] for r in rows if r[0]]

    def get_latest_pref_id(
        self, person_id: str, pref_type: str, content: str
    ) -> int | None:
        """Return id of the most recently inserted matching prompt_prefs row, or None."""
        row = self._conn.execute(
            "SELECT id FROM prompt_prefs "
            "WHERE person_id=? AND pref_type=? AND content=? "
            "ORDER BY id DESC LIMIT 1",
            (person_id, pref_type, content),
        ).fetchone()
        return row[0] if row else None

    def checkpoint_wal(self) -> None:
        """Flush the WAL into the main DB file (TRUNCATE mode).

        Called at the end of each dream cycle so the -wal sidecar stays
        small and backup copies are self-contained."""
        try:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception as _e:
            print(f"[BrainDB] WAL checkpoint failed: {_e!r}")

    def close(self) -> None:
        self._conn.close()


# ── GraphDB ────────────────────────────────────────────────────────────────────

class GraphDB:
    """Kuzu property graph — entities linked by extracted facts.

    Sits alongside SQLite: SQLite = crash recovery source of truth,
    Kuzu = rich graph queries (1-hop traversal, relationship context).
    Rebuilt automatically from SQLite if empty at startup.

    Schema:
        Entity(name STRING PRIMARY KEY, entity_type STRING)
        RELATES_TO(attribute, value, confidence, is_temporal, valid_until,
                   invalidated, source_turn_id, created_at)
    """

    def __init__(self, path: Path) -> None:
        try:
            self._db = kuzu.Database(str(path))
        except Exception as e:
            # Kuzu's native init throws IndexError / RuntimeError / generic
            # Exception on corruption, version mismatch, or half-written files
            # (e.g. Ctrl+C during a graph edit). Since the graph is rebuildable
            # from SQLite via BrainOrchestrator._ensure_graph_sync(), we recover
            # by wiping the path and re-creating. Knowledge facts are preserved
            # in brain.db and rebuilt on next sync. If the retry also fails,
            # re-raise — that's a genuine environmental issue (disk-full, perms).
            import shutil
            print(
                f"[GraphDB] Kuzu open failed at {path} "
                f"({type(e).__name__}: {e}). Wiping + recreating — "
                f"facts will be rebuilt from SQLite on next sync."
            )
            p = Path(path)
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
            for suffix in (".wal", "-lock"):
                Path(str(path) + suffix).unlink(missing_ok=True)
            self._db = kuzu.Database(str(path))
        self._conn = kuzu.Connection(self._db)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            "CREATE NODE TABLE IF NOT EXISTS Entity("
            "name STRING, entity_type STRING, PRIMARY KEY (name))"
        )
        # valid_at added in GRAPH_SCHEMA_VERSION=1 (Item 3).
        # privacy_level added in GRAPH_SCHEMA_VERSION=3 (P0.S7.D-B). Edge-level
        # placement (D2): privacy is per-fact granularity, not per-entity. Same
        # target entity (e.g. 'diabetes') can appear in multiple edges with
        # different attribute names + different privacy_levels. Cross-person
        # `find_shared_entities` filters at `r.privacy_level = 'public'`.
        # Kuzu does not support ALTER TABLE on rel tables — schema changes require
        # BrainOrchestrator._ensure_graph_sync() to wipe + rebuild from SQLite.
        self._conn.execute(
            "CREATE REL TABLE IF NOT EXISTS RELATES_TO("
            "FROM Entity TO Entity,"
            "attribute STRING, value STRING, confidence DOUBLE,"
            "is_temporal BOOLEAN, valid_until DOUBLE, valid_at DOUBLE,"
            "invalidated BOOLEAN, source_turn_id INT64, created_at DOUBLE,"
            "privacy_level STRING)"
        )

    def upsert_entity(self, name: str, entity_type: str) -> None:
        # Single MERGE: ON CREATE initialises type; ON MATCH upgrades "value" placeholder to real type
        self._conn.execute(
            "MERGE (e:Entity {name: $name})"
            " ON CREATE SET e.entity_type = $etype"
            " ON MATCH SET e.entity_type ="
            " CASE WHEN e.entity_type = 'value' THEN $etype ELSE e.entity_type END",
            {"name": name, "etype": entity_type},
        )

    def _create_edge(
        self,
        src: str, tgt: str,
        attribute: str, value: str,
        confidence: float, is_temporal: bool,
        valid_until: float | None, valid_at: float | None,
        invalidated: bool, source_turn_id: int, created_at: float,
        privacy_level: str = "personal",
    ) -> None:
        # P0.S7.D-B D4: privacy_level defaults to 'personal' (matches
        # PRIVACY_LEVEL_DEFAULT from S106). Legacy callers OR forgotten
        # kwargs get the safest tier. Phase 3 inverse-check guards that
        # every production caller passes privacy_level= explicitly.
        # P0.S4 D1 — fail-loud at the Kuzu write boundary too. The graph
        # filter at find_shared_entities reads r.privacy_level; an invalid
        # tier slipping through would produce edges that are structurally
        # invisible to cross-person matching. Same caller-side try/except
        # wrapper protection as store_knowledge — raises propagate to the
        # background-task wrapper and log without crashing the pipeline.
        _assert_valid_privacy_level(
            privacy_level,
            f"GraphDB._create_edge (src={src!r}, attr={attribute!r})",
        )
        self._conn.execute(
            "MATCH (src:Entity {name: $src}), (tgt:Entity {name: $tgt})"
            " CREATE (src)-[:RELATES_TO {"
            "attribute: $attr, value: $val, confidence: $conf,"
            "is_temporal: $temporal, valid_until: $valid_until, valid_at: $valid_at,"
            "invalidated: $inv, source_turn_id: $turn_id, created_at: $now,"
            "privacy_level: $privacy"
            "}]->(tgt)",
            {
                "src": src, "tgt": tgt,
                "attr": attribute, "val": value,
                "conf": confidence, "temporal": is_temporal,
                "valid_until": valid_until, "valid_at": valid_at,
                "inv": invalidated,
                "turn_id": source_turn_id, "now": created_at,
                "privacy": privacy_level,
            },
        )

    def store_fact(self, ext: "Extraction", turn_id: int) -> None:
        now = time.time()
        self.upsert_entity(ext.entity, ext.entity_type)
        self.upsert_entity(ext.value, "value")
        # P0.S7.D-B: thread Extraction.privacy_level (set by S106
        # _classify_privacy_level) onto the edge so find_shared_entities
        # can filter cross-person traversal at Cypher level.
        self._create_edge(
            src=ext.entity, tgt=ext.value,
            attribute=ext.attribute, value=ext.value,
            confidence=ext.confidence, is_temporal=ext.is_temporal,
            valid_until=_valid_until(ext.is_temporal, ext.valid_for_hours, now),
            valid_at=now,
            invalidated=False, source_turn_id=turn_id, created_at=now,
            privacy_level=ext.privacy_level,
        )

    def invalidate_fact(self, entity: str, attribute: str) -> None:
        self._conn.execute(
            "MATCH (src:Entity {name: $entity})-[r:RELATES_TO]->()"
            " WHERE r.attribute = $attr AND r.invalidated = false"
            " SET r.invalidated = true",
            {"entity": entity, "attr": attribute},
        )

    def rebuild_entity_from_knowledge(self, entity_name: str, rows: list[dict]) -> None:
        """Create or refresh a Kuzu entity node from SQLite knowledge rows.

        Called after migrate_entity_name() to keep the graph in sync with the
        newly renamed entity. We do NOT rename the old node (Kuzu primary keys
        are immutable and the old name may be shared by other strangers), so we
        only ADD the new node and its edges.

        Each row must have: attribute, value, confidence, is_temporal,
        valid_until, valid_at, source_turn_id, created_at.
        """
        if not rows:
            return
        try:
            self.upsert_entity(entity_name, "person")
            for row in rows:
                self.upsert_entity(row["value"], "value")
                # P0.S7.D-B: thread privacy_level from brain.db row.
                # Fail-closed to PRIVACY_LEVEL_DEFAULT ('personal') for
                # pre-S106 rows that lack the column.
                self._create_edge(
                    src=entity_name,
                    tgt=row["value"],
                    attribute=row["attribute"],
                    value=row["value"],
                    confidence=row["confidence"],
                    is_temporal=bool(row["is_temporal"]),
                    valid_until=row.get("valid_until"),
                    valid_at=row.get("valid_at"),
                    invalidated=False,
                    source_turn_id=row.get("source_turn_id") or 0,
                    created_at=row.get("created_at") or time.time(),
                    privacy_level=row.get("privacy_level") or PRIVACY_LEVEL_DEFAULT,
                )
            print(f"[GraphDB] rebuild_entity_from_knowledge: '{entity_name}' ({len(rows)} edges)")
        except Exception as e:
            print(f"[GraphDB] rebuild_entity_from_knowledge error: {e}")

    def get_graph_context(
        self,
        entity_name: str,
        caller_pid: "str | None" = None,
        best_friend_id: "str | None" = None,
    ) -> str | None:
        """Return formatted 1-hop context for LLM injection. None if entity unknown.

        Confidence filter is applied in Python (not Kuzu Cypher) so that decay is
        respected: a 0.80-confidence fact from 2 years ago won't appear in context.

        P0.S7.D-B (DEFENSE-IN-DEPTH): Cypher WHERE adds a privacy filter
        mirroring the SQL `_visibility_clause` semantic:
          - ``caller_pid == entity_name`` (owner) → all tiers visible
            except 'system_only' (matches SQL best_friend / owner-of-fact)
          - ``caller_pid == best_friend_id`` (household owner) → all
            tiers visible except 'system_only'
          - ``caller_pid is None`` OR caller is neither owner nor
            best_friend → fail-closed public-only (Plan v1 P1, Plan v2
            §3.3)

        D3 framing (Plan v2 §3.4): this filter is **defense-in-depth**.
        The existing ``if not _filtering:`` skip at the single production
        caller (``BrainOrchestrator.get_context`` site) was already
        preventing the cross-person leak. The Cypher filter raises the
        floor against future code-path additions that bypass the
        defensive skip. D1's ``find_shared_entities`` filter is the
        load-bearing privacy fix; D3 is hardening, not active-leak
        closure.
        """
        now = time.time()
        # D3 fail-closed default — when caller identity is unknown,
        # filter to public-only. caller_pid == entity_name treated as
        # the "self-query" / owner-override branch (matches owner-check
        # arm of SQL _visibility_clause).
        if caller_pid is not None and (
            caller_pid == entity_name
            or (best_friend_id is not None and caller_pid == best_friend_id)
        ):
            _privacy_clause = "AND r.privacy_level <> 'system_only'"
        else:
            _privacy_clause = "AND r.privacy_level = 'public'"
        try:
            result = self._conn.execute(
                "MATCH (src:Entity {name: $name})-[r:RELATES_TO]->()"
                " WHERE r.invalidated = false"
                " AND (r.valid_until IS NULL OR r.valid_until > $now)"
                " AND r.confidence >= 0.30"
                f" {_privacy_clause}"
                " RETURN r.attribute, r.value, r.confidence, r.is_temporal, r.valid_until,"
                " r.valid_at, r.created_at"
                " ORDER BY r.created_at DESC",
                {"name": entity_name, "now": now},
            )
        except Exception as e:
            print(f"[GraphDB] get_graph_context error (schema mismatch?): {e}")
            return None
        rows = result.get_all()
        if not rows:
            return None
        facts = [
            {
                "attribute":         r[0], "value":       r[1],
                "confidence":        r[2], "is_temporal":  r[3],
                "valid_until":       r[4],
                "valid_at":          r[5] if r[5] else r[6],   # fall back to created_at
                "last_confirmed_at": None,  # graph doesn't store this; decay from valid_at
            }
            for r in rows
        ]
        return _format_context_lines(entity_name, facts)

    def find_shared_entities(
        self,
        person_a: str,
        person_b: str,
        min_confidence: float = 0.50,
    ) -> list[dict]:
        """Find entity nodes (values) that appear in both persons' 1-hop graphs.

        Queries each person's outgoing RELATES_TO edges in Python (two fast Kuzu
        calls), then intersects the value sets. Returns shared entities with the
        attribute context from each side.

        Used by ProactiveNudgeAgent to generate cross-person hypotheses:
        e.g. stranger said "cousin Ravi" + best_friend has "cousin Ravi" → match.

        Session 107 Phase 3A.6 Part 4 — Kuzu privacy audit finding:
        this traversal returns entity values directly from the graph, NOT
        from SQL. The graph's RELATES_TO edges currently carry no
        privacy_level property, so a sensitive value that happens to
        appear in both persons' graphs (e.g. a health_condition value
        like "diabetes") would surface as a shared entity without any
        tier filter.

        Session 112 Part 4 — session-isolation audit (DECISION at
        the time: option (a) skip v3 bump, SQL filter is sufficient
        because cross-person matches were entity-name-only and
        personal-tier room-context facts weren't being written to
        OTHER speakers' graphs). The decision was correct AT THE TIME
        — but was reversed by P0.S7.D-B below.

        P0.S7.D-B (2026-05-19) — Kuzu v3 schema bump SHIPPED. The
        S107 + S112 deferral premise was falsified by P0.S7.2 κ
        multi-person assistant-turn extraction (2026-05-19): κ writes
        personal-tier `received_*` / `witnessed_*` facts to brain.db;
        graph rebuild ingests them as RELATES_TO edges. Without the
        privacy_level filter, third-party visitors could surface
        another person's personal-tier facts through cross-person
        matching. The S112 deferral was load-bearing in light of κ;
        D-B is the active-leak fix.

        v3 fix (LOAD-BEARING):
          - RELATES_TO edges now carry `privacy_level STRING` (D2
            edge-level placement — same target entity name can appear
            in multiple edges with different attribute names AND
            different privacy_levels).
          - Cypher WHERE filter `r.privacy_level = 'public'` applied
            here: ONLY public-tier edges participate in cross-person
            traversal. Personal/household/system_only are filtered at
            Cypher level (Plan v2 §4 D1 lock).
          - Cross-person owner-override (P0.S7 P1 (ii)) does NOT apply
            to graph traversal — owner-override is for `query_knowledge_for`
            where the requester is identified; graph queries are
            recipient-agnostic by nature.

        Schema-concept clarifier (Plan v2 §4 LOW 2):
        each RELATES_TO edge has three relevant properties — `attribute`
        (the predicate, e.g. 'discussed_topic'), `value` (the target
        entity's name, mirrored from the target node), and `privacy_level`
        (the v3 property). The same target entity (same `value`) can
        appear in multiple edges with different attribute names AND
        different privacy_levels. The cross-person filter operates on
        `edge.privacy_level`, NOT on `entity.name`.
        """
        now = time.time()

        def _get_facts(name: str) -> dict[str, list[tuple[str, str]]]:
            """Return {value_lower: [(attribute, value), ...]} for a person.

            P0.S7.D-B: Cypher WHERE adds `r.privacy_level = 'public'`.
            ONLY public-tier edges participate in cross-person traversal.
            """
            try:
                result = self._conn.execute(
                    "MATCH (src:Entity {name: $name})-[r:RELATES_TO]->(tgt:Entity)"
                    " WHERE r.invalidated = false"
                    " AND (r.valid_until IS NULL OR r.valid_until > $now)"
                    " AND r.confidence >= $conf"
                    " AND r.privacy_level = 'public'"
                    " RETURN r.attribute, r.value, tgt.entity_type",
                    {"name": name, "now": now, "conf": min_confidence},
                )
                rows = result.get_all()
            except Exception:
                return {}
            out: dict[str, list[tuple[str, str, str]]] = {}
            for attr, val, etype in rows:
                key = val.lower()
                out.setdefault(key, []).append((attr, val, etype or "value"))
            return out

        facts_a = _get_facts(person_a)
        facts_b = _get_facts(person_b)
        shared_keys = set(facts_a) & set(facts_b)

        results = []
        for key in shared_keys:
            for attr_a, val_a, etype_a in facts_a[key]:
                for attr_b, val_b, etype_b in facts_b[key]:
                    results.append({
                        "entity_name":  val_a,
                        "entity_type":  etype_a if etype_a != "value" else etype_b,
                        "a_attribute":  attr_a,
                        "a_value":      val_a,
                        "b_attribute":  attr_b,
                        "b_value":      val_b,
                    })
        return results

    def is_empty(self) -> bool:
        rows = self._conn.execute("MATCH (e:Entity) RETURN count(e)").get_all()
        return not rows or rows[0][0] == 0

    def entity_count(self) -> int:
        rows = self._conn.execute("MATCH (n:Entity) RETURN count(n)").get_all()
        return rows[0][0] if rows else 0

    def rebuild(self, knowledge_rows: list[dict]) -> None:
        """Populate graph from SQLite knowledge rows (startup sync).

        P0.S7.D-B: each row's `privacy_level` is threaded through to the
        edge so cross-person `find_shared_entities` traversal can filter
        at Cypher level. Legacy rows without the column fall back to
        ``PRIVACY_LEVEL_DEFAULT`` ('personal').
        """
        for row in knowledge_rows:
            self.upsert_entity(row["entity"], row["entity_type"])
            self.upsert_entity(row["value"], "value")
            try:
                self._create_edge(
                    src=row["entity"], tgt=row["value"],
                    attribute=row["attribute"], value=row["value"],
                    confidence=row["confidence"], is_temporal=bool(row["is_temporal"]),
                    valid_until=row.get("valid_until"),
                    valid_at=row.get("valid_at") or row.get("created_at"),
                    invalidated=row["invalidated_at"] is not None,
                    source_turn_id=row["source_turn_id"],
                    created_at=row["created_at"],
                    privacy_level=row.get("privacy_level") or PRIVACY_LEVEL_DEFAULT,
                )
            except Exception as e:
                print(f"[GraphDB] Rebuild skipped edge {row['entity']}.{row['attribute']}: {e}")

    def drop_schema(self) -> None:
        """Drop all Kuzu tables (schema + data).

        Called before _init_schema() on schema-version upgrades so that
        CREATE REL/NODE TABLE is not a no-op on the old-schema table.
        `wipe()` only deletes rows (DETACH DELETE); it cannot alter column
        definitions — the only way to change a Kuzu rel table schema is to
        DROP + re-CREATE it.
        """
        for stmt in ("DROP TABLE IF EXISTS RELATES_TO", "DROP TABLE IF EXISTS Entity"):
            self._conn.execute(stmt)

    def delete_person_entity(self, person_name: str) -> bool:
        """Delete the Entity node for person_name and all its edges from the graph.

        Returns True if the DELETE executed without error (node may or may not have existed).
        """
        try:
            self._conn.execute(
                "MATCH (e:Entity {name: $name}) DETACH DELETE e",
                {"name": person_name},
            )
            return True
        except Exception as exc:
            print(f"[GraphDB] delete_person_entity failed for '{person_name}': {exc}")
            return False

    def wipe(self) -> None:
        self._conn.execute("MATCH (e:Entity) DETACH DELETE e")

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        if self._db is not None:
            self._db.close()
            self._db = None


# ── Agent 1: TriageAgent ───────────────────────────────────────────────────────

_NOISE_WORDS = frozenset({
    "ok", "okay", "yes", "no", "yeah", "nah", "sure", "right",
    "hmm", "uh", "um", "ah", "oh", "huh",
    "thanks", "thank", "you", "bye", "goodbye", "goodnight",
    "hi", "hello", "hey", "alright",
})


class TriageAgent:
    """Fast, LLM-free filter.

    Only user turns with meaningful content pass through — no LLM call,
    no async overhead. Designed to eliminate ~40% of turns before they
    ever reach the extraction LLM.
    """

    def should_process(
        self,
        role: str,
        content: str,
        prior_assistant_turn: str | None = None,
        *,
        room_participant_count: int = 1,
    ) -> tuple[bool, str]:
        # P0.S7.2 Phase 2 — multi-person assistant-turn extraction. Brain
        # responses in multi-person rooms carry topic-bearing content that
        # participants need in their knowledge graphs for cross-session
        # retrieval. D5 min-chars guard filters acknowledgments / KAIROS
        # check-ins / filler.
        if role == "assistant":
            if (
                room_participant_count >= 2
                and len(content or "") >= ASSISTANT_TURN_EXTRACT_MIN_CHARS
            ):
                return True, "multi_person_assistant_turn"
            return False, "assistant turn"
        # Non-user, non-assistant roles (defensive — schema enumerates
        # user/assistant only but guard against future role values).
        if role != "user":
            return False, "assistant turn"

        # Strip the timestamp prefix added by load_conversation_history
        text = content
        if text.startswith("[20"):
            end = text.find("]")
            if end != -1:
                text = text[end + 1:].strip()

        words = [w.strip(".,!?\"'").lower() for w in text.split() if w.strip(".,!?\"'")]

        if len(words) < BRAIN_AGENT_MIN_WORDS:
            # Short answers are meaningful when they're responding to an AI prompt
            if prior_assistant_turn is not None:
                return True, "short answer to ai"
            return False, f"too short ({len(words)} words)"

        if all(w in _NOISE_WORDS for w in words):
            return False, "noise only"

        return True, "ok"


# ──────────────────────────────────────────────────────────────────────────────
# P0.S7.2 Phase 2 — multi-person assistant-turn extraction helpers (κ)
# ──────────────────────────────────────────────────────────────────────────────

# Plan v2 P1 — locked 5-value action_type enum. Brain-asks-question turns are
# common; `asked_question` captures them with semantic precision instead of
# falling into the engaged_general_discussion catch-all.
_VALID_ACTION_TYPES: frozenset[str] = frozenset({
    "shared_information",
    "answered_question",
    "asked_question",
    "made_suggestion",
    "engaged_general_discussion",
})

_ASSISTANT_ROOM_EXTRACT_SYSTEM = """\
You analyze a single assistant turn that occurred during a multi-person
conversation. Extract structured information about what was discussed.

Output STRICT JSON:
{{
  "topic": "<concise topic phrase, =60 chars, e.g., 'cheese cookies recipe'>",
  "action_type": "<one of: shared_information | answered_question |
                   asked_question | made_suggestion |
                   engaged_general_discussion>",
  "primary_subject_name": "<participant name the assistant ADDRESSED (NOT
                            the topic-subject); see counter-example below>",
  "key_details": "<=80 chars of distinctive content; null if action_type is
                   engaged_general_discussion or content is non-substantive>"
}}

PRIMARY_SUBJECT_NAME SEMANTIC: the participant the assistant SPOKE TO, not
the participant they spoke ABOUT.

Counter-example: assistant says "Jagan, Lexi mentioned earlier she likes
cooking" -- primary_subject_name = "Jagan" (addressee), NOT "Lexi" (topic).
Lexi appears in topic content; she's covered separately by the system as
a witness in the room.

ACTION_TYPE GUIDANCE:
- shared_information: assistant offers facts/recipe/instructions/explanation
- answered_question: assistant directly responds to a participant's question
- asked_question: assistant probes for info (e.g., "Lexi, what's the deadline?")
- made_suggestion: assistant proposes an action/option
- engaged_general_discussion: catch-all for substantive turns that don't fit
  the 4 above; topic + key_details should still be extracted

If the assistant turn is non-substantive (acknowledgment, filler, KAIROS
check-in), output {{"topic": null}}. Do NOT extract anything.

Participants in the room: {participants}
"""


def _fan_out_to_participants(
    extracted: "dict | None",
    participant_names: "list[str]",
    participant_pids: "list[str]",
    disputed_pids: "set[str]",
) -> "list[Extraction]":
    """P0.S7.2 Plan v2 §4.2 — fan-out helper.

    Emits per-participant Extraction objects from the topic-level LLM
    extraction. Skips disputed pids (P3) — pollution into a disputed-id
    knowledge graph would be a correctness failure (S91 / S73).

    primary_subject_name semantic = ADDRESSEE (P2). Topic-subjects who happen
    to be participants get witnessed_* facts. Topic-subjects who are NOT
    participants do not appear in the fan-out at all (their data isn't being
    written to anyone's graph by this path).

    Enum-validation belt-and-braces (auditor Q1 follow-up): an LLM-emitted
    action_type outside the 5-enum collapses to engaged_general_discussion.
    """
    if not extracted or not extracted.get("topic"):
        return []  # non-substantive turn — no facts

    topic = str(extracted["topic"]).strip()
    if not topic:
        return []

    raw_action = extracted.get("action_type") or "engaged_general_discussion"
    action_type = (
        raw_action
        if raw_action in _VALID_ACTION_TYPES
        else "engaged_general_discussion"
    )

    primary_subject_name = extracted.get("primary_subject_name")
    if primary_subject_name is not None:
        primary_subject_name = str(primary_subject_name).strip() or None

    raw_details = extracted.get("key_details")
    key_details = str(raw_details).strip() if raw_details else ""

    # Compose value strings per Plan v2 §4.2.
    if primary_subject_name and primary_subject_name in participant_names:
        primary_value = topic if not key_details else f"{topic}: {key_details}"
        witness_value = f"{topic} to_{primary_subject_name}"
    else:
        # Primary subject not a participant (or null) — all participants are
        # witnesses; no `received_*` fact emitted.
        primary_subject_name = None
        primary_value = None
        witness_value = topic if not key_details else f"{topic}: {key_details}"

    facts: "list[Extraction]" = []
    for name, pid in zip(participant_names, participant_pids):
        # P3 — disputed-skip gate. Don't pollute disputed-id knowledge graph.
        if pid in disputed_pids:
            continue
        if name == primary_subject_name:
            attr  = f"received_{action_type}"
            value = primary_value
        else:
            attr  = f"witnessed_{action_type}"
            value = witness_value
        facts.append(Extraction(
            entity          = name,
            entity_type     = "person",
            attribute       = attr,
            value           = value or "",
            confidence      = 0.85,
            is_temporal     = False,
            valid_for_hours = None,
            privacy_level   = "personal",  # D6
            person_id       = pid,         # P0.S7.2 — per-participant scope
        ))
    return facts


# ── Agent 2: ExtractionAgent ───────────────────────────────────────────────────

_EXTRACT_SYSTEM = """\
You are a knowledge extraction agent for a personal AI companion.

Extract ALL factual knowledge from the conversation turn. The attribute names you
choose become the schema — pick descriptive snake_case names that will be
understood months later (e.g., dietary_preference, lives_in, works_at,
favorite_sport, sibling_name, current_mood, health_condition).

Return ONLY valid JSON:
{
  "worth_processing": true,
  "extractions": [
    {
      "entity":          "exact name of the person/place/thing this fact is about",
      "entity_type":     "person|place|topic|event|object",
      "attribute":       "snake_case_attribute_name",
      "value":           "fact value as plain string",
      "confidence":      0.9,
      "is_temporal":     false,
      "valid_for_hours": null
    }
  ]
}

Rules:
- Only extract facts explicitly stated or very strongly implied by what was said
- confidence: 0.9 = directly stated, 0.7 = strongly implied, 0.5 = weakly implied

Entity naming rules:
- entity must be an atomic name: a real person's name, a place, or a named thing
- NEVER use possessives as entity: NOT "Jagan's sister" — use entity="Divya", attribute="relationship_to_jagan", value="sister"
- NEVER invent names for entities not explicitly named in the conversation
- If the thing has no stated name (e.g., "my sister"), use the speaking person as entity:
  entity="{person_name}", attribute="has_sister", value="true"

Fact value rules:
- value must be a real-world fact, NOT a restatement of the attribute name
  BAD: entity="Jagan", attribute="brushing_teeth", value="brushing teeth"
  GOOD: entity="Jagan", attribute="current_activity", value="brushing teeth"
- Do NOT extract session-presence facts: "is_in_conversation", "is_talking_to_ai",
  "being_addressed", "participating_in_session" — these are noise, always true during a turn
- QUESTION vs STATEMENT discipline: if the user is ASKING about X, do NOT extract
  X as a property of the user. Only extract when the user STATES X about themselves.
  BAD: user asks "what is the temperature in Chennai?" → entity="Jagan", attribute="lives_in", value="Chennai"
  GOOD: user says "I moved to Chennai last month" → entity="Jagan", attribute="lives_in", value="Chennai"
  Questions about places, topics, or people ARE NOT statements of the user's
  relationship to those entities. Treat "Tell me about X" / "What is X?" / "How is
  X?" as information-seeking, NOT as location/preference reveals. Same applies to
  "Do you know X?" / "What did Y say about X?" / "Is X true?".
- SAFETY-CRITICAL CONTENT — momentary state AND historical event (Session 105
  Bug N, 2026-04-23 canary): when the user says something that expresses
  self-harm ideation, crisis, abuse, or other safety-critical content,
  emit TWO extractions — NOT one.
    (i)  Momentary state: `current_mood`, `current_feeling`, etc. —
         overwritten each turn as moods shift. Fine for moment-to-
         moment tracking.
    (ii) Historical event: `expressed_suicidal_thoughts='true'`,
         `mentioned_self_harm='true'`, `mentioned_abuse='true'`,
         `mentioned_substance_abuse='true'`, `mentioned_crisis='true'`,
         `mentioned_domestic_violence='true'`. These are APPEND-ONLY
         historical flags — once expressed, never erased by a later
         mood change. The ContradictionAgent safety blacklist
         protects them at the write layer.
  Concrete canary counter-example (2026-04-23 Lexi session):
    User: "I feel like committing suicide."
    BAD (canary behavior — only one extraction, overwritten 4 turns
      later by current_mood='loving'):
        { entity: "Lexi", attribute: "current_mood", value: "suicidal" }
    GOOD (emit BOTH):
        { entity: "Lexi", attribute: "current_mood",
          value: "suicidal", confidence: 0.9 }
        { entity: "Lexi", attribute: "expressed_suicidal_thoughts",
          value: "true", confidence: 0.95 }
  The historical flag is non-negotiable for a companion AI — erasing a
  crisis disclosure because the user later said "I like food" is a
  safety failure. Similar rule for any `mentioned_*` or `expressed_*_thoughts`
  shape.
- USER OPINION vs third-party FACT (Session 104 Bug M, 2026-04-23):
  when the user makes a CLAIM about a third-party entity — especially
  a factual-sounding one ("Mumbai Indians are at the bottom of the
  table", "Tesla stock is crashing", "the president said X") — that
  is the USER's opinion or belief, not a verified fact about the
  entity. Do NOT store as {entity:"Mumbai Indians", attribute:
  "current_standings", value:"bottom"} — that asserts the claim as
  truth about Mumbai Indians, polluting the knowledge graph with
  unverified user statements. Two correct alternatives:
    (1) SKIP the extraction entirely — safest, and appropriate when
        the claim is about current events / sports standings / news /
        stock prices / anything time-sensitive that a web-search tool
        would answer better.
    (2) Store as user's BELIEF instead of third-party fact:
        entity={person_name}, attribute="believes", value="Mumbai Indians
        are at the bottom of the table" — attributes the belief to
        the speaker, keeps the third-party entity untouched.
  When in doubt, prefer (1). A missed belief fact is fine; a wrong
  "fact" about Mumbai Indians poisons every future session that asks
  about the team. Same reasoning as the GEOGRAPHIC QUERY rule below —
  extraction is better off silent than wrong.
- SUPERLATIVE CLAIMS DISCIPLINE (Session 114 Obs 2, 2026-04-25):
  superlative claims ("most X", "biggest", "hottest", "best ever",
  "worst", "coldest", "fastest", "richest") about a person/place/thing
  are user opinion/belief, NOT verified fact ABOUT the subject — until
  corroborated by a search_web result. Same class as USER OPINION above
  but specifically the superlative shape, which the live canary showed
  slipping through with high confidence ("Tirupati was recorded as the
  most hottest city in India" → stored as a fact ABOUT Tirupati).
    BAD:  user: "Tirupati is the hottest city in India"
          → Tirupati.recorded_temperature_ranking="hottest in India"
    GOOD: user: "Tirupati is the hottest city in India"
          → SKIP the extraction entirely (preferred) — superlative
            without independent verification is not a load-bearing fact.
          OR Jagan.believes_about_tirupati="hottest city in India" if
            attributing the belief to the speaker is genuinely useful.
    GOOD: user: "Wikipedia says Tirupati is the hottest"
          → still SKIP — single user citation isn't strong enough
            corroboration. Only store as third-party fact if YOU called
            search_web AND the result independently confirms the claim.
  Treats superlatives the way the GEOGRAPHIC QUERY rule treats location
  questions: better to skip than to assert a wrong third-party fact.
- GEOGRAPHIC QUERY generalization (Session 103 Bug D.2, 2026-04-23): the
  QUESTION-vs-STATEMENT rule above applies to ALL geographic queries, not
  just Chennai. If the user asks "what is the {weather|temperature|price|
  time|rainfall|humidity|traffic|news|election|event|score|cricket match|
  ...} in {any city/state/country/location}?", you MUST NOT write
  user.lives_in=LOCATION, user.current_location=LOCATION, user.from=LOCATION,
  or any similar user-attribute. The user is asking a trivia/news query
  about that place, not revealing where they live. Concrete counter-
  examples that triggered memory pollution in canary runs:
    BAD: "What is the temperature in Chennai?" → Jagan.lives_in='Chennai'
    BAD: "What is the temperature in Bangalore?" → Jagan.current_location='Bangalore'
    BAD: "What is the weather in Mumbai today?" → Jagan.lives_in='Mumbai'
    BAD: "What are the election results in Delhi?" → Jagan.from='Delhi'
    BAD: "How is the traffic in Hyderabad?" → Jagan.current_city='Hyderabad'
  The presence of a city/state/country name in a question is NEVER
  evidence of the user's relationship to that place. Only explicit
  self-statements ("I live in Mumbai", "I'm from Hyderabad", "I moved
  to Delhi last month", "my home is Chennai") license a location fact.
  When in doubt: skip the extraction — a missed location fact is fine,
  a WRONG location fact poisons every future session.
- CORRECTION direction: when the user uses a "not X, Y" frame — "not X, my name is Y"
  / "not X, actually Y" / "No, it's not X, it's Y" / "I'm not X, I'm Y" — the
  CORRECT value is Y (the SECOND name, the one after "not"/"actually"/"my name is").
  X is what they are REJECTING, not the new value. Extract entity=Y, NOT X.
  BAD: user says "No, not Javan. My name is Jagan." → entity="Gevan", attribute="name_correction", value="not Jagan, actually Gevan"
  GOOD: user says "No, not Javan. My name is Jagan." → entity="Jagan", attribute="name", value="Jagan" (and the rename happens via the update_person_name tool, not extraction)
  When in doubt about correction direction, DO NOT extract a "name_correction"
  attribute at all — the update_person_name tool is the proper channel for name
  changes. Extraction should surface the FINAL asserted name, never invert it.
- RELATIONSHIP EXTRACTION DISCIPLINE (Session 114 Obs 3, 2026-04-25):
  relationships are extracted ONLY from EXPLICIT statements using
  relationship vocabulary. Tone-based inference (a stern instruction, a
  scolding, a paternal/maternal-sounding utterance) is NOT sufficient
  evidence to assert a kinship or guardianship relationship. The live
  canary surfaced this when "Lexi, do your homework" was inferred as
  Jagan.relationship_to_lexi='parent or guardian' at high confidence —
  could equally be older brother, mentor, friend, neighbor.
    BAD:  user A: "Lexi, do your homework"
          → infer A.relationship_to_lexi="parent or guardian"
    GOOD: user A: "Lexi is my daughter"
          → A.has_daughter="Lexi", Lexi.parent="A"
    GOOD: user A: "Lexi is my friend's kid"
          → Lexi.parent="A's friend" (note the indirection — preserves
            the actual relationship structure rather than collapsing
            "kid I'm watching" into "my kid").
  Relationship vocabulary that DOES license extraction: "my X" / "X is
  my Y" / "I'm X's Y" / "our X" / explicit kinship terms (mother,
  father, son, daughter, husband, wife, brother, sister, cousin,
  etc.). Tone, instructions, scolding, terms of endearment ("honey",
  "sweetie") on their own are NOT enough — skip the extraction. A
  missed relationship fact is fine; a wrong one ("Jagan is Lexi's
  parent" when he's actually her tutor) corrupts every future
  visitor-context block and proactive nudge.

Temporal validity windows (use these, not 12-168 for everything):
- Current activity (brushing teeth, at gym, eating):    is_temporal=true, valid_for_hours=1
- Emotion / mood (happy, stressed, tired):              is_temporal=true, valid_for_hours=4
- Short-term plan (going to gym later, meeting today):  is_temporal=true, valid_for_hours=24
- Multi-day plan / event (trip next week, project):     is_temporal=true, valid_for_hours=168
- Identity / preference / fact (lives_in, works_at):    is_temporal=false, valid_for_hours=null

Context grounding:
- Facts from dreams: prefix attribute with "dream_" (e.g., dream_location="forest")
- Facts about past events: prefix attribute with "former_" if no longer true
- Facts about stated plans: prefix attribute with "planned_" (e.g., planned_trip="Paris")

Redundancy:
- Do NOT emit a fact where value == entity name or value == attribute name
- Do NOT emit tautologies: entity="Jagan", attribute="name", value="Jagan"

Correction handling (when "Prior AI claim" is shown above):
- If the user's turn negates or corrects the AI's claim ("no", "actually", "wrong", "not anymore"),
  extract the corrected fact with confidence=0.95 so it supersedes the wrong stored belief.
- If the user confirms the AI's claim ("yes", "exactly", "correct"), you may still extract it
  as a fresh extraction — it will be handled as a compatible reinforcing fact.

- If nothing extractable: {"worth_processing": false, "extractions": []}
- Do NOT extract facts about the AI itself\
"""

_EXTRACT_USER = """\
Person speaking: {person_name}
Turn: \"{content}\"
{prior_claim_block}
Recent context:
{context}

Extract all factual knowledge from this turn.\
"""

_PRIOR_CLAIM_BLOCK = """\
Prior AI claim (the AI stated this just before the user's turn — the user may be correcting it):
\"{prior_ai_claim}\"

"""

_PRIOR_ASSISTANT_BLOCK = """\
Prior AI response (the AI said this immediately before the user's turn — use it to interpret the user's answer):
\"{prior_assistant_turn}\"

"""


class ExtractionAgent:
    """LLM-powered entity + fact extractor.

    Uses Together.ai with JSON mode for reliable structured output.
    Falls back to Ollama if Together.ai is unavailable.
    The LLM freely chooses attribute names — that's the "LLM owns the schema" principle.
    """

    def __init__(self, http: httpx.AsyncClient):
        self._http = http

    async def extract(
        self,
        content: str,
        person_name: str,
        context_turns: list[dict],
        prior_ai_claim: str | None = None,
        prior_assistant_turn: str | None = None,
        system_name: str = DEFAULT_SYSTEM_NAME,
    ) -> list[Extraction]:
        context_str = "\n".join(
            f"  [{t['role']}]: {t['content'][:200]}"
            for t in context_turns[-BRAIN_AGENT_CONTEXT_TURNS:]
        ) or "  (start of conversation)"

        # prior_ai_claim (recall signal) takes precedence; fall back to general prior turn
        if prior_ai_claim:
            prior_claim_block = _PRIOR_CLAIM_BLOCK.format(prior_ai_claim=prior_ai_claim[:300])
        elif prior_assistant_turn:
            prior_claim_block = _PRIOR_ASSISTANT_BLOCK.format(
                prior_assistant_turn=prior_assistant_turn[:300]
            )
        else:
            prior_claim_block = ""
        system_prompt = (
            _EXTRACT_SYSTEM
            + f'\n\nAI name rule: The AI assistant is named "{system_name}". '
            f"STRICT: you MUST NOT extract any fact where "
            f'entity == "{system_name}". The AI\'s own identity '
            f"(its name, spelling, voice, model, version, creator) "
            f"belongs to the system_identity table — NOT the knowledge "
            f"graph. Specifically, NEVER extract these attribute shapes "
            f"when the entity matches the AI's name: ai_name, "
            f"name_spelling, bot_identity, system_name, ai_model, "
            f"ai_version, ai_creator, ai_voice. Session 104 Bug L "
            f"(2026-04-23 canary): Jagan said 'your name is Kara' and "
            f"extraction wrote {{entity:'Kara', attribute:'ai_name', "
            f"value:'Kara'}} + {{entity:'Kara', attribute:"
            f"'name_spelling', value:'K-A-R-A'}} — both should have been "
            f"skipped. The LLM's rename tool (update_system_name) "
            f"handles the AI identity update; extraction must stay "
            f"silent on it."
        )
        user_msg = _EXTRACT_USER.format(
            person_name=person_name or "unknown",
            content=content[:500],
            prior_claim_block=prior_claim_block,
            context=context_str,
        )

        raw = await self._call_together(user_msg, system_prompt) or await self._call_ollama(user_msg, system_prompt)
        if not raw:
            return []

        data = _parse_json(raw)
        if data is None:
            return []

        if not data.get("worth_processing"):
            return []

        results: list[Extraction] = []
        for item in data.get("extractions", []):
            try:
                attr   = str(item["attribute"]).strip().lower().replace(" ", "_")
                entity = str(item["entity"]).strip()
                value  = str(item["value"]).strip()
            except (KeyError, ValueError, TypeError):
                continue
            # Session 95 3A.4.5: agent-layer privacy classification. Static-map
            # hits are free; novel attributes hit the LLM classifier exactly
            # once and cache for the process lifetime. Fail-closed default is
            # PRIVACY_LEVEL_DEFAULT='personal' on any classifier failure.
            try:
                privacy = await _classify_privacy_level(entity, attr, value, http=self._http)
            except Exception as ex:
                print(f"[ExtractionAgent] privacy classify failed for {attr!r}: {ex!r}")
                privacy = PRIVACY_LEVEL_DEFAULT
            try:
                results.append(Extraction(
                    entity          = entity,
                    entity_type     = str(item.get("entity_type", "unknown")).strip(),
                    attribute       = attr,
                    value           = value,
                    confidence      = float(item.get("confidence", 0.7)),
                    is_temporal     = bool(item.get("is_temporal", False)),
                    valid_for_hours = float(item["valid_for_hours"]) if item.get("valid_for_hours") else None,
                    privacy_level   = privacy,
                ))
            except (KeyError, ValueError, TypeError):
                continue
        return results

    async def extract_assistant_room_turn(
        self,
        assistant_content: str,
        participant_names: "list[str]",
        participant_pids: "list[str]",
        disputed_pids: "set[str] | None" = None,
    ) -> "list[Extraction]":
        """P0.S7.2 Plan v2 §4.2 — multi-person assistant-turn extraction.

        ONE LLM call (L1.c) returning topic-level structured data + mechanical
        fan-out per participant via `_fan_out_to_participants`.

        Returns a list of Extraction objects, one per non-disputed
        participant, all with `privacy_level='personal'` (D6).
        """
        if not assistant_content or not participant_names:
            return []
        system_prompt = _ASSISTANT_ROOM_EXTRACT_SYSTEM.format(
            participants=", ".join(participant_names),
        )
        response = await _call_llm_chat(
            self._http,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": assistant_content[:1500]},
            ],
            agent_name="ExtractAssistantRoomTurn",
            response_format={"type": "json_object"},
            timeout=5.0,
            max_tokens=250,
        )
        if response is None:
            return []  # LLM failure — fail safe; no extractions
        extracted = _parse_json(response) or {}

        return _fan_out_to_participants(
            extracted,
            participant_names,
            participant_pids,
            disputed_pids or set(),
        )

    async def _call_together(self, user_msg: str, system_prompt: str = _EXTRACT_SYSTEM) -> str | None:
        if not EXTRACT_API_KEY:
            return None
        # Bug 6 (2026-04-20 live run): transient network failures (ReadTimeout,
        # ConnectTimeout) silently produced `[ExtractionAgent] error: ReadTimeout:`
        # with empty message and dropped the turn. Match EmbeddingAgent's retry
        # pattern (Session 24 A8): retry EXTRACT_MAX_RETRIES times with exponential
        # backoff on transient errors; 4xx client errors propagate immediately
        # since retrying those is pointless.
        _last_exc: "Exception | None" = None
        for _attempt in range(EXTRACT_MAX_RETRIES + 1):
            try:
                resp = await self._http.post(
                    f"{EXTRACT_BASE_URL}/chat/completions",
                    json={
                        "model":           EXTRACT_MODEL,
                        "messages":        [
                            {"role": "system", "content": system_prompt},
                            {"role": "user",   "content": wrap_user_input(user_msg)},
                        ],
                        "temperature":     0.1,
                        "max_tokens":      800,
                        "response_format": {"type": "json_object"},
                    },
                    headers={"Authorization": f"Bearer {EXTRACT_API_KEY}"},
                    timeout=15.0,
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as e:
                # 4xx = client error (bad request, auth, model not found).
                # Retrying won't help and masks real config bugs.
                if 400 <= e.response.status_code < 500:
                    print(f"[ExtractionAgent] HTTP {e.response.status_code}: {e.response.text[:200]}")
                    return None
                _last_exc = e
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.NetworkError) as e:
                _last_exc = e
            except Exception as e:
                # Non-HTTP/non-network failures (JSON parse, KeyError, etc.) —
                # log and return without retry (not transient).
                _detail = str(e) or "(no detail)"
                print(f"[ExtractionAgent] error: {type(e).__name__}: {_detail}")
                return None
            # Backoff before retry (1s, 2s). Skip wait on last attempt.
            if _attempt < EXTRACT_MAX_RETRIES:
                await asyncio.sleep(2 ** _attempt)
        # All retries exhausted — log with context since str() is often empty on timeouts.
        _detail = str(_last_exc) if _last_exc and str(_last_exc) else "(no detail)"
        print(
            f"[ExtractionAgent] {type(_last_exc).__name__ if _last_exc else 'Unknown'} "
            f"after {EXTRACT_MAX_RETRIES + 1} attempts: {_detail}"
        )
        return None

    async def _call_ollama(self, user_msg: str, system_prompt: str = _EXTRACT_SYSTEM) -> str | None:
        try:
            resp = await self._http.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt + "\nIMPORTANT: output ONLY the JSON object, nothing else."},
                        {"role": "user",   "content": wrap_user_input(user_msg)},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.1},
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except Exception as e:
            print(f"[ExtractionAgent] Ollama error: {e}")
            return None


# ── Agent 3: ContradictionAgent ────────────────────────────────────────────────

_CONTRA_PROMPT = """\
Stored fact: {entity}.{attribute} = "{old_value}"
New fact:    {entity}.{attribute} = "{new_value}"
{volatility_note}
Does the NEW fact REPLACE the stored fact (the person changed or corrected it),
or are they COMPATIBLE (both can be true — different times, contexts, or details)?

Reply with exactly:
REPLACE   (if the new fact supersedes the old one)
COMPATIBLE (if both can coexist)

Then one sentence of rationale on the next line.\
"""

# A-MEM retroactive staleness check (Item 4):
# Used after a REPLACE event to re-evaluate related facts about the same entity.
_STALENESS_PROMPT = """\
A fact about {entity} was just updated:
  {changed_attribute}: "{old_value}" → "{new_value}"

Related stored fact: {entity}.{related_attribute} = "{related_value}"

Is the related fact now:
  STALE       — less certain, probably needs updating (reduce confidence)
  INVALIDATED — certainly no longer true (hard invalidate)
  UNCHANGED   — still valid regardless of the change

Reply with exactly one word (STALE, INVALIDATED, or UNCHANGED), then one sentence of rationale.\
"""


class ContradictionAgent:
    """LLM-powered contradiction detector.

    Called only when a new extraction shares an (entity, attribute) pair with
    a stored fact. Returns whether to replace or keep both.
    """

    def __init__(self, http: httpx.AsyncClient):
        self._http = http

    async def check(
        self,
        entity: str,
        attribute: str,
        old_value: str,
        new_value: str,
        contradiction_count: int = 0,
    ) -> tuple[bool, str]:
        """Returns (should_replace, rationale).

        contradiction_count: historical REPLACE events for this predicate.
        When ≥ PREDICATE_VOLATILITY_THRESHOLD the prompt notes the field is volatile.
        """
        if old_value.strip().lower() == new_value.strip().lower():
            return False, "identical values"

        # Session 105 Bug N — safety-critical attribute blacklist. Crisis
        # disclosures ("expressed_suicidal_thoughts", "mentioned_self_harm",
        # etc.) must be APPEND-ONLY — never overwritten by a later mood
        # update. 2026-04-23 canary had Lexi's suicidal-ideation fact get
        # REPLACED with current_mood='loving' four turns later, erasing a
        # safety-critical disclosure before best_friend could be alerted.
        # Extraction emits the historical flag alongside momentary mood;
        # this pre-check keeps the historical flag out of the contradiction
        # loop entirely so it accumulates as a timestamped history instead
        # of a single overwritable slot. Zero LLM cost on these checks.
        if _is_safety_critical_attribute(attribute):
            return False, "safety-critical — append, never replace"

        volatility_note = (
            f"[Note: '{attribute}' has been corrected {contradiction_count} times historically"
            f" — this is a volatile field; the new value likely supersedes the old one.]"
            if contradiction_count >= PREDICATE_VOLATILITY_THRESHOLD
            else ""
        )
        prompt = _CONTRA_PROMPT.format(
            entity=entity, attribute=attribute,
            old_value=old_value, new_value=new_value,
            volatility_note=volatility_note,
        )

        text = await self._call_together(prompt) or await self._call_ollama(prompt)
        if not text:
            return False, "check failed — keeping both"

        lines = text.strip().splitlines()
        verdict   = lines[0].strip().upper() if lines else ""
        rationale = lines[1].strip() if len(lines) > 1 else ""
        return verdict == "REPLACE", rationale

    async def _call_together(self, prompt: str) -> str | None:
        """Session 90 Bug 2: migrated to the shared ``_call_llm_chat`` helper.
        The previous inline ``try/except Exception`` wrapper produced the
        silent ``[ContradictionAgent] error: ReadTimeout:`` (empty message,
        no retry) observed in the 2026-04-22 multi-convo live run — exact
        same failure mode as Session 69 Bug M on PromptPrefAgent. Helper
        provides: retry-with-exponential-backoff on transient errors
        (ReadTimeout, ConnectTimeout, NetworkError, 5xx), no retry on
        4xx (except 429), explicit 'choices' shape validation, and the
        ``(no detail)`` fallback for empty-message exceptions. Covers BOTH
        ``check`` and ``check_staleness`` since they both delegate here."""
        return await _call_llm_chat(
            self._http,
            [{"role": "user", "content": wrap_user_input(prompt)}],
            agent_name="ContradictionAgent",
            max_tokens=80,
            temperature=0.0,
            timeout=10.0,
        )

    async def check_staleness(
        self,
        entity: str,
        related_attribute: str,
        related_value: str,
        changed_attribute: str,
        old_value: str,
        new_value: str,
    ) -> tuple[str, str]:
        """Re-evaluate a related fact after a REPLACE event (A-MEM Item 4).

        Returns (verdict, rationale) where verdict is STALE / INVALIDATED / UNCHANGED.
        Used by BrainOrchestrator._retroactive_scan().
        """
        prompt = _STALENESS_PROMPT.format(
            entity=entity,
            changed_attribute=changed_attribute,
            old_value=old_value,
            new_value=new_value,
            related_attribute=related_attribute,
            related_value=related_value,
        )
        text = await self._call_together(prompt) or await self._call_ollama(prompt)
        if not text:
            return "UNCHANGED", "check failed"
        lines   = text.strip().splitlines()
        verdict = lines[0].strip().upper() if lines else "UNCHANGED"
        rationale = lines[1].strip() if len(lines) > 1 else ""
        if verdict not in ("STALE", "INVALIDATED", "UNCHANGED"):
            return "UNCHANGED", rationale
        return verdict, rationale

    async def _call_ollama(self, prompt: str) -> str | None:
        try:
            resp = await self._http.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model":   OLLAMA_MODEL,
                    "messages":[{"role": "user", "content": wrap_user_input(prompt)}],
                    "stream":  False,
                    "options": {"temperature": 0.0},
                },
                timeout=20.0,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except Exception as e:
            print(f"[ContradictionAgent] Ollama error: {e}")
            return None


# ── Agent 4: PromptPrefAgent ───────────────────────────────────────────────────

_PREF_SYSTEM = """\
You are a communication preference detector for a personal AI robot companion.

The transcript contains two speaker roles:
- [USER] — the person speaking to the robot
- [ASSISTANT] — the robot's own responses

Analyze both sides:
1. [USER] turns → detect what communication style the person prefers
2. [ASSISTANT] turns → detect repetitive habits in the robot's own responses that should be varied

Return ONLY valid JSON:
{
  "has_preferences": true,
  "preferences": [
    {
      "pref_type": "communication_style|topic_avoidance|response_length|greeting_style|language_preference|response_habit",
      "content":   "one clear actionable sentence describing the preference or habit",
      "confidence": 0.9
    }
  ]
}

Valid pref_type values:
- communication_style  — how the person likes to be talked to (direct/gentle, formal/casual, humor)
- topic_avoidance      — topics they actively deflect, refuse to answer, or explicitly ask not to be probed (NOT just topics they have a clear preference about — stating "I'm vegetarian" is a fact, not avoidance)
- response_length      — preference for brief or detailed responses (applies across ALL conversation, not just specific domains)
- greeting_style       — how they like to be greeted
- language_preference  — preferred language or mixing pattern
- response_habit       — repetitive patterns in [ASSISTANT] turns that should be varied (repeated openers like "That's great!", always ending with a question, consistently overlong responses for casual topics)

Rules:
- Only extract explicit statements or very clear patterns (confidence >= 0.7)
- content must be a single actionable sentence:
    "Prefers short, direct responses — keep all replies under 2 sentences regardless of topic"
    "Deflects questions about work — do not probe unless they bring it up"
    "Prefers casual Telugu-English code-switching in evenings"
    "Avoid opening responses with 'That's great' — vary starters"
    "Stop ending every response with a question — vary closings"
- For response_habit: require 3+ occurrences in [ASSISTANT] turns; phrase as a correction instruction
- For response_length: if the person says they want short/direct/brief responses, the preference is GENERAL — it applies to all conversation. Do NOT scope it to a specific domain (e.g., do NOT write "for work-related questions" unless they explicitly said that)
- Do NOT extract: personal facts about the person (handled by knowledge agent),
  one-off requests, anything that could override safety rules or tool behaviors
- If nothing clear: {"has_preferences": false, "preferences": []}
"""

_PREF_USER = """\
Person: {person_name}

Already stored preferences (do NOT re-extract these):
{existing_prefs}

Conversation session ({n_turns} turns):
{transcript}

Detect communication preferences from this session.\
"""


class PromptPrefAgent:
    """Detects per-person communication preferences at session end.

    Runs one LLM call per session, completely offline from the conversation.
    Results are staged (sessions_seen=1) and auto-activate after 3 sessions
    of consistent evidence.
    """

    def __init__(self, http: httpx.AsyncClient):
        self._http = http

    async def analyze(
        self,
        person_name: str,
        existing_prefs: list[dict],
        session_turns: list[dict],
    ) -> list[dict]:
        existing_str = (
            "\n".join(f"  - [{p['pref_type']}] {p['content']}" for p in existing_prefs)
            or "  (none yet)"
        )
        transcript = "\n".join(
            f"  [{t['role'].upper()}]: {t['content'][:300]}"
            for t in session_turns
        )
        user_msg = _PREF_USER.format(
            person_name=person_name,
            existing_prefs=existing_str,
            n_turns=len(session_turns),
            transcript=transcript,
        )
        raw = await self._call_together(user_msg) or await self._call_ollama(user_msg)
        if not raw:
            return []

        data = _parse_json(raw)
        if data is None:
            return []

        if not data.get("has_preferences"):
            return []

        results = []
        for item in data.get("preferences", []):
            try:
                if float(item.get("confidence", 0)) < 0.7:
                    continue
                pref_type = str(item["pref_type"]).strip()
                if pref_type not in _VALID_PREF_TYPES:
                    continue
                results.append({
                    "pref_type": pref_type,
                    "content":   str(item["content"]).strip(),
                })
            except (KeyError, ValueError, TypeError):
                continue
        return results

    async def _call_together(self, user_msg: str) -> str | None:
        """Session 69 (Bug M): migrated to the shared ``_call_llm_chat`` helper.
        The previous `try/except Exception as e: print(...{e})` path produced
        ``[PromptPrefAgent] error: ReadTimeout:`` with no detail on transient
        network failures — the helper retries with exponential backoff and
        logs with actual context."""
        return await _call_llm_chat(
            self._http,
            [
                {"role": "system", "content": _PREF_SYSTEM},
                {"role": "user",   "content": wrap_user_input(user_msg)},
            ],
            agent_name="PromptPrefAgent",
            max_tokens=400,
            temperature=0.1,
            response_format={"type": "json_object"},
            timeout=15.0,
        )

    async def _call_ollama(self, user_msg: str) -> str | None:
        try:
            resp = await self._http.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model":   OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": _PREF_SYSTEM + "\nOutput ONLY the JSON object."},
                        {"role": "user",   "content": wrap_user_input(user_msg)},
                    ],
                    "stream":   False,
                    "options":  {"temperature": 0.1, "num_predict": 300},
                },
                # Explicit per-component timeout: 5s to connect + 20s to read.
                # A bare float (timeout=30.0) is read-only; adding connect=5.0
                # prevents the ~8s cold-start from pushing the total over 35s.
                timeout=httpx.Timeout(read=20.0, connect=5.0, write=5.0, pool=5.0),
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except Exception as e:
            # str(e) is empty for httpx timeout exceptions — always include the type.
            print(f"[PromptPrefAgent] Ollama error: {type(e).__name__}: {e or '(no message)'}")
            return None


# ── Agent 5: FrictionDetectionAgent ───────────────────────────────────────────

_FRICTION_SYSTEM = """\
You are analyzing whether a person's message expresses dissatisfaction with how an AI robot is \
responding — specifically, frustration that one of the robot's known communication preferences for \
this person is NOT being honored.

Return ONLY valid JSON:
{
  "frictions": [
    {"pref_type": "response_length", "confidence": 0.85}
  ]
}

If no friction is detected: {"frictions": []}

Rules:
- Only flag friction when the message clearly signals dissatisfaction, repetition, or correction
- Match to a pref_type from the active list only — do NOT invent new types
- Require confidence >= 0.70 to report
- A single factual correction is noise — look for signals the robot's *style* is bothering them
"""

_FRICTION_USER = """\
Active communication preferences for this person:
{prefs}

Previous robot response:
{prev_assistant}

Person's message:
{user_turn}

Is the person expressing friction against any active preference?\
"""


class FrictionDetectionAgent:
    """Detects within-session friction against active communication preferences.

    Called from _process_turn() on user turns that pass triage, when the person
    has at least one active pref. One lightweight LLM call per qualifying turn.
    Results land in DB during TTS so next turn's get_prompt_addendum() picks up
    escalated language immediately (n+1 turn effect).
    """

    def __init__(self, http: httpx.AsyncClient):
        self._http = http

    async def detect(
        self,
        user_turn: str,
        prev_assistant_turn: str | None,
        active_prefs: list[dict],
    ) -> list[dict]:
        """Returns list of {pref_type, confidence} above FRICTION_MIN_CONFIDENCE."""
        prefs_str = "\n".join(
            f"  - [{p['pref_type']}] {p['content']}" for p in active_prefs
        )
        user_msg = _FRICTION_USER.format(
            prefs=prefs_str,
            prev_assistant=prev_assistant_turn or "(none)",
            user_turn=user_turn,
        )
        raw  = await self._call_together(user_msg) or await self._call_ollama(user_msg)
        if not raw:
            return []
        data = _parse_json(raw)
        if data is None:
            return []

        valid_types = {p["pref_type"] for p in active_prefs}
        results = []
        for item in data.get("frictions", []):
            try:
                pref_type  = str(item["pref_type"]).strip()
                confidence = float(item.get("confidence", 0))
                if pref_type not in valid_types or confidence < FRICTION_MIN_CONFIDENCE:
                    continue
                results.append({"pref_type": pref_type, "confidence": confidence})
            except (KeyError, ValueError, TypeError):
                continue
        return results

    async def _call_together(self, user_msg: str) -> str | None:
        if not EXTRACT_API_KEY:
            return None
        try:
            resp = await self._http.post(
                f"{EXTRACT_BASE_URL}/chat/completions",
                json={
                    "model":           EXTRACT_MODEL,
                    "messages":        [
                        {"role": "system", "content": _FRICTION_SYSTEM},
                        {"role": "user",   "content": wrap_user_input(user_msg)},
                    ],
                    "temperature":     0.0,
                    "max_tokens":      150,
                    "response_format": {"type": "json_object"},
                },
                headers={"Authorization": f"Bearer {EXTRACT_API_KEY}"},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[FrictionDetectionAgent] error: {type(e).__name__}: {e}")
            return None

    async def _call_ollama(self, user_msg: str) -> str | None:
        try:
            resp = await self._http.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model":    OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": _FRICTION_SYSTEM + "\nOutput ONLY the JSON object."},
                        {"role": "user",   "content": wrap_user_input(user_msg)},
                    ],
                    "stream":   False,
                    "options":  {"temperature": 0.0},
                },
                timeout=20.0,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except Exception as e:
            print(f"[FrictionDetectionAgent] Ollama error: {e}")
            return None


# ── HouseholdExtractionAgent ───────────────────────────────────────────────────

class HouseholdExtractionAgent:
    """Extracts household-scoped facts and inter-person relationships from conversation turns.

    Dual-trigger (called from BrainOrchestrator):
    - Per-turn: fires on every user utterance to capture household facts + relationships
    - Session-end: deep analysis of full session for relationship consolidation

    Key design principles (from research):
    - Speaker attribution is explicit — "Jagan said 'my wife works nights'" → attributed to Priya
    - Household scope vs per-person scope classified at extraction time
    - Non-enrolled persons get shadow nodes, not full entity nodes
    - All decisions made by LLM — no hardcoded rules
    """

    _SYSTEM = (
        "You are a household context extractor for an AI robot. "
        "Your job is to extract HOUSEHOLD-LEVEL facts from a single conversation utterance. "
        "Focus only on:\n"
        "1. Facts about shared household assets/routines (we, our, the family, the house)\n"
        "2. Individual facts about SPECIFIC NAMED PEOPLE (not the current speaker unless explicitly stated)\n"
        "3. Relationships between people\n"
        "4. Non-enrolled persons mentioned by name (shadow nodes)\n\n"
        "DO NOT extract: conversational filler, opinions about the world, facts about public figures, "
        "single-word vague references, or facts already obvious from the question alone.\n\n"
        "CRITICAL relationship rule: Only use a relationship type that is explicitly stated or unmistakably implied in the utterance. "
        "If the speaker says 'my sister Kavya' → sibling_of. 'my wife Priya' → married_to. 'my colleague Ravi' → colleague_of. "
        "NEVER infer a spouse/married_to relationship unless the word 'wife', 'husband', 'spouse', or 'married' is present. "
        "When in doubt between sibling and spouse, always use sibling_of or family_member_of — never default to married_to.\n\n"
        "Respond with ONLY valid JSON matching this schema:\n"
        "{\n"
        '  "household_facts": [\n'
        '    {"entity": "household", "attribute": "dinner_time", "value": "around 8pm", '
        '"scope": "household", "confidence": 0.75}\n'
        "  ],\n"
        '  "per_person_facts": [\n'
        '    {"entity": "Priya", "attribute": "work_schedule", "value": "night shifts", '
        '"inferred_from": "speaker said \'my wife works nights\'", "confidence": 0.85}\n'
        "  ],\n"
        '  "relationships": [\n'
        '    {"person_a": "Jagan", "relationship": "married_to", "person_b": "Priya", "confidence": 0.95},\n'
        '    {"person_a": "Jagan", "relationship": "sibling_of", "person_b": "Kavya", "confidence": 0.90}\n'
        "  ],\n"
        '  "shadow_persons": [\n'
        '    {"name": "Anita", "mentioned_by": "Priya", "relationship": "colleague_of", '
        '"facts": [{"attribute": "works_at", "value": "same office", "confidence": 0.7}]}\n'
        "  ]\n"
        "}"
    )

    def __init__(self, http: httpx.AsyncClient):
        self._http        = http
        self._system_name = DEFAULT_SYSTEM_NAME

    def set_system_name(self, name: str) -> None:
        self._system_name = name

    async def _call_api(self, prompt: str, max_tokens: int, label: str) -> dict | None:
        """Session 69 (Bugs J + M): migrated to the shared ``_call_llm_chat``
        helper. Retries transient network errors; propagates 4xx; validates the
        response shape explicitly. The `label` is threaded into agent_name so
        per-turn vs session-end failures are distinguishable in logs."""
        raw = await _call_llm_chat(
            self._http,
            [
                {"role": "system", "content": self._SYSTEM},
                {"role": "user",   "content": wrap_user_input(prompt)},
            ],
            agent_name=f"HouseholdAgent:{label}",
            max_tokens=max_tokens,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        if raw is None:
            return None
        return _parse_json(raw)

    async def extract_per_turn(
        self,
        speaker_id: str,
        speaker_name: str,
        utterance: str,
        context_turns: list[dict],
        enrolled_persons: list[str],
    ) -> dict | None:
        """Extract household facts from a single utterance."""
        if len(utterance.split()) < 4:
            return None

        ctx_text = ""
        if context_turns:
            ctx_lines = [
                f"{t['role'].upper()}: {t['content'][:150]}"
                for t in context_turns[-3:]
            ]
            ctx_text = "\nRecent context:\n" + "\n".join(ctx_lines)

        enrolled_str = ", ".join(enrolled_persons) if enrolled_persons else "none yet"
        prompt = (
            f"Current speaker: {speaker_name} (id={speaker_id})\n"
            f"Known household members: {enrolled_str}\n"
            f"AI system name (NOT a person — never extract as shadow_person): {self._system_name}\n"
            f"{ctx_text}\n\n"
            f"Current utterance: {utterance}\n\n"
            "Extract household facts, relationships, and shadow persons from the utterance above. "
            "When the speaker says 'my wife/husband/kid/colleague', resolve to the known household member "
            "if the relationship matches. Attribute facts to the correct person, not the speaker. "
            f"IMPORTANT: '{self._system_name}' is the AI robot's name — never create a shadow_person for it. "
            "If nothing worth extracting, return empty arrays."
        )
        return await self._call_api(prompt, max_tokens=400, label="Per-turn extraction")

    async def extract_session_end(
        self,
        person_id: str,
        person_name: str,
        session_turns: list[dict],
        enrolled_persons: list[str],
    ) -> dict | None:
        """Deep relationship consolidation analysis of full session transcript."""
        if len(session_turns) < 4:
            return None

        transcript = "\n".join(
            f"[{t['role'].upper()}] {t['content'][:200]}"
            for t in session_turns[-30:]
        )
        enrolled_str = ", ".join(enrolled_persons) if enrolled_persons else "none yet"
        prompt = (
            f"Primary speaker this session: {person_name} (id={person_id})\n"
            f"All enrolled household members: {enrolled_str}\n"
            f"AI system name (NOT a person — never extract as shadow_person): {self._system_name}\n\n"
            f"Session transcript:\n{transcript}\n\n"
            "Analyze the full session above. Extract:\n"
            "1. Confirmed household facts (mentioned multiple times or with high certainty)\n"
            "2. Confirmed relationships between household members\n"
            "3. Any new shadow persons mentioned (non-enrolled people referenced by name)\n"
            "4. Behavioral patterns (recurring topics, routines confirmed across the session)\n"
            f"IMPORTANT: '{self._system_name}' is the AI robot's name — never create a shadow_person for it. "
            "Focus on STABLE, REPEATED, or HIGH-CONFIDENCE facts only. Ignore passing remarks."
        )
        return await self._call_api(prompt, max_tokens=600, label="Session-end extraction")


# ── SchemaNormAgent ────────────────────────────────────────────────────────────

def _distinct_schema_families(attr_a: str, attr_b: str) -> bool:
    """Return True iff two attributes belong to different protected semantic families.

    Used by SchemaNormAgent's clustering: embedding cosine can wrongly bridge
    "former_name" and "former_presence" because they share "former". A membership
    check on substring families prevents that. Config-driven via
    SCHEMA_NORM_DISTINCT_FAMILIES — extend when new confusions surface.
    """
    a, b = attr_a.lower(), attr_b.lower()
    fam_a = None
    fam_b = None
    for idx, family in enumerate(SCHEMA_NORM_DISTINCT_FAMILIES):
        if any(tok in a for tok in family):
            fam_a = idx
        if any(tok in b for tok in family):
            fam_b = idx
    return fam_a is not None and fam_b is not None and fam_a != fam_b


class SchemaNormAgent:
    """Normalizes synonymic schema attributes using embedding cosine similarity.

    The LLM freely invents attribute names (that's the schema freedom principle), so over
    time the same concept accumulates multiple spellings: dietary_preference, food_preference,
    eats_what. This agent clusters them by embedding similarity and rewrites all knowledge
    rows to use a single canonical name per concept cluster.

    Pipeline:
        1. Embed all unembedded schema_catalog attributes (reuses EmbeddingAgent batch infra)
        2. Build full cosine similarity matrix (numpy, O(n²) on <200 attributes ≈ microseconds)
        3. rapidfuzz pre-filter: skip pairs with string similarity < 30 before embedding compare
        4. Union-find clustering at SCHEMA_NORM_THRESHOLD (0.88)
        5. Within each cluster: canonical = highest use_count (tie-break: shortest name)
        6. Rewrite knowledge.attribute + collapse schema_catalog for synonyms

    Triggered at BrainOrchestrator startup when schema_catalog has >= SCHEMA_NORM_TRIGGER rows,
    and after each _process_turn that stores new facts.
    """

    def __init__(self, brain_db: "BrainDB", embed_agent: "EmbeddingAgent"):
        self._brain_db    = brain_db
        self._embed_agent = embed_agent

    async def maybe_run(self) -> None:
        count = self._brain_db.count_schema_catalog_entries()
        if count >= SCHEMA_NORM_TRIGGER:
            await self.run()

    async def run(self) -> None:
        t0 = time.time()
        await self._embed_attributes()
        rows = self._brain_db.get_all_schema_embeddings()
        if len(rows) < 2:
            return
        clusters = self._cluster(rows)
        if not clusters:
            return
        merged = 0
        for canonical, synonyms in clusters:
            self._brain_db.merge_schema_attributes(canonical, synonyms)
            merged += len(synonyms)
            print(f"[SchemaNorm] {canonical} ← {synonyms}")
        elapsed = (time.time() - t0) * 1000
        print(f"[SchemaNorm] Normalized {merged} attribute synonym(s) in {elapsed:.0f}ms")

    async def _embed_attributes(self) -> None:
        rows = self._brain_db.get_unembedded_schema_attributes()
        if not rows:
            return
        texts = [r["attribute"].replace("_", " ") for r in rows]
        embeddings = await self._embed_agent.embed_batch(texts, purpose="schema attribute")
        for row, emb in zip(rows, embeddings):
            if emb:
                self._brain_db.store_schema_embedding(row["attribute"], emb)

    def _cluster(self, rows: list[dict]) -> list[tuple[str, list[str]]]:
        """Return (canonical, [synonyms]) pairs using union-find over cosine similarity."""
        attrs      = [r["attribute"] for r in rows]
        use_counts = {r["attribute"]: r["use_count"] for r in rows}
        vecs       = [np.frombuffer(r["embedding"], dtype=np.float32).tolist() for r in rows]
        n          = len(attrs)
        sim        = _cosine_similarity_matrix(vecs)   # shape (n, n)

        # Union-find with path compression
        parent = list(range(n))
        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        def union(x: int, y: int) -> None:
            parent[find(x)] = find(y)

        ambiguous: list[tuple[str, str, float]] = []
        for i in range(n):
            for j in range(i + 1, n):
                # rapidfuzz pre-filter: skip pairs that are obviously unrelated strings
                if _rfuzz.token_sort_ratio(attrs[i], attrs[j]) < 60:
                    continue
                # Distinct-family guard: never merge attributes that belong to different
                # semantic families (e.g. "former_name" must not cluster with "former_presence").
                if _distinct_schema_families(attrs[i], attrs[j]):
                    continue
                score = float(sim[i, j])
                if score >= SCHEMA_NORM_THRESHOLD:
                    union(i, j)
                elif score >= SCHEMA_NORM_AMBIGUOUS:
                    ambiguous.append((attrs[i], attrs[j], score))

        # ambiguous pairs are informational only — no action required, suppress at startup

        # Group cluster members by root
        groups: dict[int, list[int]] = {}
        for i in range(n):
            groups.setdefault(find(i), []).append(i)

        result = []
        for members in groups.values():
            if len(members) < 2:
                continue
            member_attrs = [attrs[i] for i in members]
            # Canonical = highest use_count; tie-break = shortest name (more general)
            canonical = max(member_attrs, key=lambda a: (use_counts.get(a, 0), -len(a)))
            synonyms  = [a for a in member_attrs if a != canonical]
            result.append((canonical, synonyms))
        return result


# ── EmbeddingAgent ─────────────────────────────────────────────────────────────

class EmbeddingAgent:
    """Embeds text using Together.ai multilingual-e5-large-instruct (1024-dim).

    Instruction format: "Instruction: represent the {purpose} for retrieval: {text}"
    Common purposes: "knowledge fact", "user query", "schema attribute"

    In-memory cache avoids re-embedding identical strings within a session.
    No API key → returns None; callers fall back to non-semantic context gracefully.
    """

    _MAX_CACHE = 500  # LRU cap: ~2MB at 1024-dim float32

    def __init__(self, http: httpx.AsyncClient):
        self._http  = http
        self._cache: dict[str, list[float]] = {}  # bounded by _MAX_CACHE

    def _evict_cache(self) -> None:
        """Remove oldest entries when cache exceeds _MAX_CACHE."""
        while len(self._cache) > self._MAX_CACHE:
            # dict preserves insertion order (Python 3.7+); pop the oldest
            self._cache.pop(next(iter(self._cache)))

    async def embed(self, text: str, purpose: str = "knowledge fact") -> list[float] | None:
        instruction = f"Instruction: represent the {purpose} for retrieval: {text}"
        if instruction in self._cache:
            return self._cache[instruction]
        results = await self._call_together([instruction])
        if not results:
            return None
        self._cache[instruction] = results[0]
        self._evict_cache()
        return results[0]

    async def embed_batch(
        self, texts: list[str], purpose: str = "knowledge fact"
    ) -> list[list[float] | None]:
        instructions = [
            f"Instruction: represent the {purpose} for retrieval: {t}" for t in texts
        ]
        uncached = [i for i, inst in enumerate(instructions) if inst not in self._cache]
        if uncached:
            results = await self._call_together([instructions[i] for i in uncached])
            if results:
                for idx, vec in zip(uncached, results):
                    self._cache[instructions[idx]] = vec
                self._evict_cache()
        return [self._cache.get(inst) for inst in instructions]

    async def _call_together(self, inputs: list[str]) -> list[list[float]] | None:
        if not EMBED_API_KEY:
            return None
        last_exc: Exception | None = None
        for attempt in range(1 + EMBED_MAX_RETRIES):
            try:
                resp = await self._http.post(
                    f"{EMBED_BASE_URL}/embeddings",
                    json={"model": EMBED_MODEL, "input": inputs},
                    headers={"Authorization": f"Bearer {EMBED_API_KEY}"},
                    timeout=15.0,
                )
                # Don't retry on client errors (4xx except 429 rate-limit)
                if resp.status_code not in (429,) and 400 <= resp.status_code < 500:
                    print(f"[EmbeddingAgent] client error {resp.status_code} — not retrying")
                    return None
                resp.raise_for_status()
                data = resp.json()
                return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
            except Exception as e:
                last_exc = e
                if attempt < EMBED_MAX_RETRIES:
                    delay = 2 ** attempt  # 1s, 2s
                    print(f"[EmbeddingAgent] attempt {attempt + 1} failed ({type(e).__name__}), retrying in {delay}s…")
                    await asyncio.sleep(delay)
        print(f"[EmbeddingAgent] all {1 + EMBED_MAX_RETRIES} attempts failed: {type(last_exc).__name__}: {last_exc}")
        return None


# ── Agent 6: SpatialMemoryAgent ────────────────────────────────────────────────

from core.config import (
    VISION_SIGHTING_GAP,
    VISION_MAX_SIGHTINGS,
    PATTERN_MIN_SIGHTINGS,
    PATTERN_COOLDOWN,
    PATTERN_MAX_QUESTIONS,
    PATTERN_ANALYSIS_DAYS,
    PATTERN_MIN_CONF,
)


class SpatialMemoryAgent:
    """Stores YOLO object detections as persistent spatial memories in brain.db.

    Called synchronously from the pipeline's main vision loop (every Nth frame).
    Deduplicates within VISION_SIGHTING_GAP seconds so rapid re-detections of
    the same object in the same zone only update the existing row rather than
    flooding the table.

    Enables queries like "where did you last see my watch?" by doing a simple
    keyword search over stored sightings.
    """

    def __init__(self, brain_db: BrainDB) -> None:
        self._brain_db  = brain_db
        self._new_count = 0   # new rows inserted this session

    def record(
        self,
        detections:     list[dict],  # [{"class": str, "conf": float, "bbox": (x1,y1,x2,y2)}]
        frame_w:        int,
        frame_h:        int,
        person_context: str | None = None,
    ) -> None:
        """Process one frame's YOLO detections and persist new sightings."""
        if not detections or frame_w <= 0 or frame_h <= 0:
            return
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            cx   = ((x1 + x2) / 2) / frame_w
            cy   = ((y1 + y2) / 2) / frame_h
            zone = _infer_location_zone(cx, cy)
            is_new = self._brain_db.store_object_sighting(
                object_class   = det["class"],
                confidence     = float(det["conf"]),
                location_zone  = zone,
                bbox_cx        = cx,
                bbox_cy        = cy,
                person_context = person_context,
                dedup_gap_secs = VISION_SIGHTING_GAP,
            )
            if is_new:
                self._new_count += 1
                if self._new_count <= 3 or self._new_count % 50 == 0:
                    print(
                        f"[SpatialMemory] {det['class']} spotted at {zone}"
                        + (f" (n={self._new_count})" if self._new_count > 3 else "")
                    )

        # Prune every 100 new sightings to keep table bounded
        if self._new_count > 0 and self._new_count % 100 == 0:
            self._brain_db.prune_object_sightings(VISION_MAX_SIGHTINGS)

    def get_context(self, keywords: list[str]) -> str | None:
        """Formatted sighting context for objects matching any keyword."""
        rows = self._brain_db.search_object_sightings(keywords)
        return _format_object_sightings(rows)

    def get_recent_context(self, limit: int = 10) -> str | None:
        """Formatted context for the most recently seen objects (no filter)."""
        rows = self._brain_db.get_recent_object_sightings(limit)
        return _format_object_sightings(rows)


# ── Agent 7: ObjectPatternAgent ────────────────────────────────────────────────

_PATTERN_SYSTEM = """\
You are a behavioral pattern analyst for a personal AI robot companion.

The robot uses computer vision to detect objects in the person's environment.
You receive statistics about what objects it has observed recently.

Your job: identify genuinely interesting patterns that would help the robot
understand the person's habits, routines, and lifestyle — then generate
natural questions the robot can ask to learn more.

Good pattern examples:
- An object that appears only sometimes (suggesting different contexts or moods)
- Two objects that always appear together (co-occurrence → habit)
- An object that recently started appearing that wasn't there before (new activity?)
- An object that disappears and reappears (cyclical pattern)

Rules:
- Generate ZERO questions if nothing is genuinely interesting
- NEVER ask about obvious stationary furniture (chair, couch, dining table, bed)
- NEVER ask about things that are always present and never change
- Maximum 3 questions, minimum 0
- Questions must sound natural and curious, NOT like a data query
- Confidence >= 0.70 required

Return ONLY valid JSON:
{
  "has_patterns": true,
  "patterns": [
    {
      "pattern_key": "short_snake_case_key_max_50_chars",
      "question": "Natural question the robot should ask the person (max 200 chars)",
      "confidence": 0.85
    }
  ]
}
"""

_PATTERN_USER = """\
Object sighting statistics (last {days} days):
{stats}

Identify interesting patterns and generate questions. Return JSON.
"""

_STATIC_FURNITURE = frozenset({
    "chair", "couch", "sofa", "dining table", "bed", "toilet",
    "refrigerator", "microwave", "oven", "sink", "tv",
})


class ObjectPatternAgent:
    """Analyzes object sighting statistics and generates proactive curiosity questions.

    Triggered at session end and by the startup task scheduler. Cooldown prevents
    redundant runs. Generated questions are stored in object_pattern_questions and
    served one at a time via BrainOrchestrator.get_pending_question().
    """

    def __init__(self, brain_db: BrainDB, http: httpx.AsyncClient) -> None:
        self._brain_db    = brain_db
        self._http        = http
        self._last_run_at = 0.0

    async def maybe_run(self, total_sightings: int = 0) -> None:
        """Run pattern analysis if conditions are met (enough data + cooldown elapsed)."""
        now = time.time()
        if total_sightings > 0 and total_sightings < PATTERN_MIN_SIGHTINGS:
            return
        if now - self._last_run_at < PATTERN_COOLDOWN:
            return
        if self._brain_db.pending_question_count() >= PATTERN_MAX_QUESTIONS:
            return
        self._last_run_at = now
        await self.run()

    async def run(self) -> None:
        """Aggregate sighting stats → LLM → store new questions."""
        stats = self._brain_db.get_sighting_stats(days=PATTERN_ANALYSIS_DAYS)
        # Filter out static furniture — not worth asking about
        stats = [r for r in stats if r["object_class"] not in _STATIC_FURNITURE]
        if not stats:
            return

        patterns = await self._call_llm(stats)
        new_count = 0
        for p in patterns:
            is_new = self._brain_db.store_pattern_question(p["question"], p["pattern_key"])
            if is_new:
                new_count += 1
                print(f"[PatternAgent] Curiosity queued: {p['pattern_key']}")
        if new_count:
            print(f"[PatternAgent] {new_count} new question(s) from sighting analysis")

    def _format_stats(self, stats: list[dict]) -> str:
        """Format sighting stats as a readable summary for the LLM."""
        lines = []
        now = time.time()
        for r in stats:
            last_days  = int((now - r["last_seen"])  / 86400)
            first_days = int((now - r["first_seen"]) / 86400)
            age_note   = "new (appeared recently)" if first_days < 2 else f"first seen {first_days}d ago"
            zones      = r["zones"] or "unknown zone"
            persons    = r["persons"] or ""
            person_note = f", present with: {persons}" if persons and persons != "None" else ""
            lines.append(
                f"- {r['object_class']}: {r['total_times']}× in "
                f"{r['distinct_zones']} zone(s) [{zones}], "
                f"last seen {last_days}d ago, {age_note}{person_note}"
            )
        return "\n".join(lines)

    async def _call_llm(self, stats: list[dict]) -> list[dict]:
        stats_text = self._format_stats(stats)
        user_msg   = _PATTERN_USER.format(
            days=PATTERN_ANALYSIS_DAYS,
            stats=stats_text,
        )
        raw  = await self._call_together(user_msg) or await self._call_ollama(user_msg)
        if not raw:
            return []
        data = _parse_json(raw)
        if not data or not data.get("has_patterns"):
            return []
        results = []
        for p in data.get("patterns", []):
            try:
                conf = float(p.get("confidence", 0))
                if conf < PATTERN_MIN_CONF:
                    continue
                results.append({
                    "pattern_key": str(p["pattern_key"])[:100],
                    "question":    str(p["question"])[:300],
                })
            except (KeyError, ValueError, TypeError):
                continue
        return results

    async def _call_together(self, user_msg: str) -> str | None:
        if not EXTRACT_API_KEY:
            return None
        try:
            resp = await self._http.post(
                f"{EXTRACT_BASE_URL}/chat/completions",
                json={
                    "model":           EXTRACT_MODEL,
                    "messages":        [
                        {"role": "system", "content": _PATTERN_SYSTEM},
                        {"role": "user",   "content": user_msg},
                    ],
                    "temperature":     0.3,
                    "max_tokens":      400,
                    "response_format": {"type": "json_object"},
                },
                headers={"Authorization": f"Bearer {EXTRACT_API_KEY}"},
                timeout=15.0,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[PatternAgent] error: {type(e).__name__}: {e}")
            return None

    async def _call_ollama(self, user_msg: str) -> str | None:
        try:
            resp = await self._http.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": _PATTERN_SYSTEM + "\nOutput ONLY the JSON object."},
                        {"role": "user",   "content": user_msg},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.3},
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except Exception as e:
            print(f"[PatternAgent] Ollama error: {e}")
            return None


# ── SocialGraphAgent ───────────────────────────────────────────────────────────

class SocialGraphAgent:
    """Extracts third-party person mentions from best-friend conversation turns.

    Runs asynchronously after each best-friend user turn. Finds mentions like
    "my friend Ajay who works at TCS" and stores structured records in
    social_mentions so IdentityAgent can later recognise matching strangers.
    """

    _SYSTEM = (
        "Extract third-party person mentions from the conversation text.\n"
        "Return a JSON array (no other text). Each element:\n"
        '  {"name": "string or null", "relationship": "friend/brother/colleague/etc.", '
        '"attributes": ["specific fact 1", "specific fact 2"]}\n\n'
        "Rules:\n"
        "- Only named, real people (no celebrities, public figures, or generic 'someone')\n"
        "- Attributes must be explicitly stated facts, not inferences\n"
        "  Good: 'works at TCS', 'loves cricket', 'lives in Chennai'\n"
        "  Bad: 'seems happy', 'probably rich'\n"
        "- Skip the AI system itself\n"
        "- Return [] if no named people are mentioned"
    )

    def __init__(self, http: httpx.AsyncClient):
        self._http = http

    async def extract(self, turn_text: str) -> list[dict]:
        """Extract person mentions from one conversation turn. Returns [] on failure.

        Session 69 (Bug J): migrated to the shared ``_call_llm_chat`` helper.
        The previous open-coded access to the response's choices array raised
        KeyError on provider error-shaped responses and the bare ``except
        Exception: pass`` hid it — ``[SocialGraph] Extraction error``... was
        all the diagnosis the 2026-04-20 live run produced. The helper
        validates the response shape explicitly and logs with agent context.
        """
        if len(turn_text.split()) < 6:
            return []
        raw = await _call_llm_chat(
            self._http,
            [
                {"role": "system", "content": self._SYSTEM},
                {"role": "user",   "content": wrap_user_input(turn_text[:2000])},
            ],
            agent_name="SocialGraph",
            max_tokens=512,
            temperature=0.0,
            response_format={"type": "json_object"},
            timeout=12.0,
        )
        if raw is None:
            return []
        # P0.12.1 follow-up: P0.12 narrowed _parse_json to dict|None, which
        # silently dropped LLM responses that non-comply with json_object
        # response_format and return a raw top-level array.  Try the dict-
        # wrapper shape first (matches what response_format=json_object asks
        # for), then fall back to _parse_json_array for raw-array responses.
        data = _parse_json(raw)
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    return [m for m in v if isinstance(m, dict) and m.get("name")]
        arr = _parse_json_array(raw)
        if isinstance(arr, list):
            return [m for m in arr if isinstance(m, dict) and m.get("name")]
        return []


# ── IdentityAgent ──────────────────────────────────────────────────────────────

_IDENTITY_STOP = frozenset({
    "i", "me", "my", "we", "you", "your", "the", "a", "an", "is", "are",
    "was", "were", "be", "been", "have", "has", "had", "do", "did", "will",
    "would", "could", "should", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "it", "this", "that", "so", "yeah", "yes", "no", "ok",
    "okay", "hmm", "uh", "just", "like", "know", "think", "really", "well",
    "also", "then", "when", "with", "from", "they", "their", "there",
})


class IdentityAgent:
    """Scores a stranger's conversation against known social mentions.

    Fast and synchronous — keyword overlap only, no API calls.
    Uses a three-tier confidence model:
      IDENTITY_SOFT_THRESHOLD (0.35): inject soft hint into LLM context
      IDENTITY_ASK_THRESHOLD  (0.65): brain asks "are you X?" naturally
      IDENTITY_AUTO_THRESHOLD (0.85): auto-confirm without asking

    Confidence calculation:
    - Extract keywords from all user turns in the stranger's conversation
    - For each social mention, count attribute keywords present in the conversation
    - Require ≥2 distinct keyword matches to avoid trivial false positives
    - confidence = (matched / total_attr_keywords) × quality_factor
    """

    @staticmethod
    def _keywords(text: str) -> set[str]:
        words: set[str] = set()
        for w in re.split(r"[\s,\.!?;:'\"\-]+", text.lower()):
            w = re.sub(r"[^a-z0-9]", "", w)
            if w and len(w) > 2 and w not in _IDENTITY_STOP:
                words.add(w)
        return words

    def score(
        self,
        conversation: list[dict],
        mentions: list[dict],
    ) -> dict | None:
        """Return best identity match or None.

        Result dict: {name, relationship, confidence, matched_attrs, source_person_id}
        """
        if not mentions or not conversation:
            return None

        user_kw: set[str] = set()
        for msg in conversation:
            if msg.get("role") == "user":
                user_kw |= self._keywords(msg["content"])

        if not user_kw:
            return None

        best: dict | None = None
        best_conf = 0.0

        for mention in mentions:
            attrs = mention.get("attributes", [])
            if not attrs:
                continue

            attr_pool: list[str] = []
            for attr in attrs:
                attr_pool.extend(self._keywords(attr))

            if not attr_pool:
                continue

            matched       = [w for w in attr_pool if w in user_kw]
            distinct_count = len(set(matched))

            if distinct_count < 2:
                # Heavily dampened — one keyword match is likely noise
                raw_conf = len(matched) / max(len(attr_pool), 1) * 0.3
            else:
                raw_conf = len(matched) / max(len(attr_pool), 1)
                # Bonus for more distinct keyword hits (diminishing return)
                raw_conf = min(0.95, raw_conf * (1.0 + 0.1 * min(distinct_count, 5)))

            if raw_conf > best_conf:
                best_conf = raw_conf
                matched_attrs = [
                    a for a in attrs
                    if any(w in user_kw for w in self._keywords(a))
                ]
                best = {
                    "name":             mention["name"],
                    "relationship":     mention.get("relationship"),
                    "confidence":       raw_conf,
                    "matched_attrs":    matched_attrs,
                    "source_person_id": mention["source_person_id"],
                }

        return best if best_conf > 0 else None


# ── BriefingAgent ───────────────────────────────────────────────────────────────

class BriefingAgent:
    """Generate a warm spoken briefing for the best friend after a long absence.

    Scores stranger visits and silent observations by relevance
    (recency × relationship_match × significance), picks the top 3 most
    interesting events, and produces a 1–2 sentence spoken summary.
    """

    _SYSTEM = (
        "You are giving a brief, warm spoken update to someone who just got home. "
        "Keep it to 1–2 natural sentences. No bullet points, no headings. "
        "Only mention events that are worth saying out loud. "
        "If nothing interesting happened, return exactly the word: null"
    )
    _SCORE_THRESHOLD = 0.12

    def __init__(self, http: httpx.AsyncClient):
        self._http = http

    @staticmethod
    def _score(event: dict, social_names: set[str]) -> float:
        now = time.time()
        age_hours  = max(0.0, (now - event.get("last_seen", now)) / 3600)
        recency    = math.exp(-age_hours / 12)
        name       = (event.get("name") or "").lower()
        had_convo  = event.get("had_convo", False)
        frames     = event.get("frame_count", 1)
        matched    = name and name != "visitor" and name in social_names
        rel_weight = 1.5 if matched else (0.8 if had_convo else 0.4)
        significance = 1.0 if had_convo else min(1.0, frames / 50)
        return recency * rel_weight * significance

    async def generate(
        self,
        bf_name:         str,
        stranger_visits: list[dict],
        silent_obs:      list[dict],
        social_mentions: list[dict],
    ) -> str | None:
        social_names = {(m.get("name") or "").lower() for m in social_mentions}

        events: list[dict] = []
        for sv in stranger_visits:
            events.append({**sv, "had_convo": True})
        for obs in silent_obs:
            events.append({**obs, "had_convo": False})

        if not events:
            return None

        scored = [(self._score(e, social_names), e) for e in events]
        top = [
            e for _, e in sorted(scored, key=lambda x: x[0], reverse=True)
            if _ >= self._SCORE_THRESHOLD
        ][:3]

        if not top:
            return None

        now = time.time()
        lines: list[str] = []
        for e in top:
            age_h = max(0.0, (now - e.get("last_seen", now)) / 3600)
            if age_h < 0.1:
                age_str = "just now"
            elif age_h < 24:
                age_str = f"{int(age_h)}h ago"
            else:
                age_str = f"{int(age_h // 24)}d ago"

            if e["had_convo"]:
                name = e.get("name") or "an unnamed visitor"
                lines.append(f"- {name} visited and spoke with me ({age_str})")
            else:
                frames = e.get("frame_count", 1)
                zone   = e.get("zone") or "the area"
                lines.append(f"- An unidentified face was seen in {zone} ({frames} frames, {age_str})")

        prompt = (
            f"{bf_name} just got home after being away. "
            f"Here is what happened while they were away:\n"
            + "\n".join(lines)
            + "\n\nGenerate a warm 1–2 sentence spoken briefing. "
            "Return null if nothing is worth mentioning."
        )

        try:
            resp = await self._http.post(
                f"{EXTRACT_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {EXTRACT_API_KEY}"},
                json={
                    "model":       EXTRACT_MODEL,
                    "messages":    [
                        {"role": "system", "content": self._SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                    "max_tokens":  120,
                    "temperature": 0.7,
                },
            )
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            if raw.lower() in ("null", "none", ""):
                return None
            return raw
        except Exception as e:
            print(f"[BriefingAgent] generate error: {e}")
            return None


# ── ConversationInsightAgent ───────────────────────────────────────────────────

class ConversationInsightAgent:
    """Generate a structured episode summary at session end.

    One LLM call per session for any person (best_friend, known, stranger).
    Output feeds BriefingAgent, ProactiveNudgeAgent, and greeting context.
    Never blocks the conversation pipeline — runs as a fire-and-forget task.
    """

    _SYSTEM = (
        "You are analyzing a completed conversation session. "
        "Return ONLY valid JSON (no markdown, no extra text):\n"
        '{"mood":"one word: stressed/excited/neutral/happy/sad/anxious/tired",'
        '"key_topics":["topic1","topic2"],'
        '"promises_made":["I will call you back",...],'
        '"questions_asked":["What time is the meeting?",...],'
        '"emotional_arc":"one sentence describing emotional tone evolution",'
        '"significance_score":0.7}\n'
        "Rules: key_topics 1-5 concrete topics; significance_score 0.0=small talk "
        "1.0=major life event; null for absent fields."
    )

    def __init__(self, http: httpx.AsyncClient):
        self._http = http

    async def analyze(
        self,
        person_name:      str,
        turns:            list[dict],
        session_start_ts: float,
        session_end_ts:   float,
    ) -> dict | None:
        if not EXTRACT_API_KEY:
            return None
        transcript = "\n".join(
            f"{t['role'].upper()}: {t['content']}"
            for t in turns
        )[:3000]
        prompt = (
            f"Conversation with {person_name} "
            f"(duration: {int(session_end_ts - session_start_ts)}s):\n\n"
            + transcript
            + "\n\nGenerate the episode JSON."
        )
        try:
            resp = await self._http.post(
                f"{EXTRACT_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {EXTRACT_API_KEY}"},
                json={
                    "model":           EXTRACT_MODEL,
                    "messages":        [
                        {"role": "system", "content": self._SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                    "max_tokens":      INSIGHT_MAX_TOKENS,
                    "temperature":     0.2,
                    "response_format": {"type": "json_object"},
                },
            )
            raw = resp.json()["choices"][0]["message"]["content"]
            return _parse_json(raw)
        except Exception as e:
            print(f"[InsightAgent] analyze error: {e}")
            return None


# ── RoutineAgent ───────────────────────────────────────────────────────────────

class RoutineAgent:
    """Detect per-person visit patterns from presence_log.

    Runs synchronously at session end (in a thread executor so it never blocks
    the event loop). Works for ALL persons: best_friend, known, and strangers.

    When a stable pattern is found (std-dev of arrival hours < ROUTINE_STD_THRESHOLD),
    stores it as a fact in the knowledge table via store_knowledge() so the LLM
    context reflects it naturally.
    """

    def __init__(self, brain_db: "BrainDB"):
        self._db = brain_db

    def analyze(self, person_id: str, person_name: str) -> None:
        count = self._db.get_presence_count(person_id)
        if count < MIN_PRESENCE_SESSIONS:
            return
        history = self._db.get_presence_history(person_id, limit=20)
        if not history:
            return

        hours    = [h["hour_of_day"] for h in history]
        durations = [h["duration_s"] for h in history]

        try:
            std_h = statistics.stdev(hours) if len(hours) > 1 else 0.0
        except statistics.StatisticsError:
            return

        if std_h < ROUTINE_STD_THRESHOLD:
            typical_hour = round(statistics.mean(hours))
            avg_dur_min = round(statistics.mean(durations) / 60)
            # Invalidate previous routine facts before storing new ones
            self._db.invalidate(person_name, "typical_arrival_hour", 0)
            self._db.invalidate(person_name, "typical_visit_duration_min", 0)
            # Use store_knowledge() so facts get schema catalog, graph sync, embeddings
            # Session 95 3A.4.5: sync agent, closed attribute set. Both
            # facts describe a specific person's schedule — 'personal' by
            # definition (owner-only). No LLM classify needed.
            self._db.store_knowledge(
                [
                    Extraction(
                        entity=person_name, entity_type="person",
                        attribute="typical_arrival_hour", value=str(typical_hour),
                        confidence=0.80, is_temporal=False, valid_for_hours=None,
                        privacy_level="personal",
                    ),
                    Extraction(
                        entity=person_name, entity_type="person",
                        attribute="typical_visit_duration_min", value=str(avg_dur_min),
                        confidence=0.80, is_temporal=False, valid_for_hours=None,
                        privacy_level="personal",
                    ),
                ],
                turn_id=0,
                person_id=person_id,
                agent="routine_agent",
            )
            print(
                f"[RoutineAgent] {person_name}: typical arrival hour={typical_hour},"
                f" duration≈{avg_dur_min}min (std_h={std_h:.1f})"
            )

    def check_deviation(self, person_id: str, current_hour: int) -> str | None:
        """Return deviation description if current hour is unusual for this person.

        Synchronous SQLite read (<1ms). Called from ProactiveNudgeAgent.
        Returns None if no stable pattern or no deviation.
        """
        history = self._db.get_presence_history(person_id, limit=20)
        if len(history) < MIN_PRESENCE_SESSIONS:
            return None
        hours = [h["hour_of_day"] for h in history]
        try:
            mean_h = statistics.mean(hours)
            std_h  = statistics.stdev(hours) if len(hours) > 1 else 0.0
        except statistics.StatisticsError:
            return None
        if std_h >= ROUTINE_STD_THRESHOLD:
            return None  # pattern not stable enough
        deviation = abs(current_hour - mean_h)
        if deviation >= PRESENCE_DEVIATION_HOURS:
            typical = f"{int(mean_h):02d}:00"
            return f"usually here around {typical} but visiting at {current_hour:02d}:00"
        return None


# ── ProactiveNudgeAgent ────────────────────────────────────────────────────────

class ProactiveNudgeAgent:
    """Generate proactive nudges for cross-person inference, intention follow-ups,
    and memory prompts. All computation is synchronous SQLite + Kuzu reads.

    Nudge types:
      CROSS_PERSON_HYPOTHESIS — "I think I met your cousin"
      INTENTION_FOLLOWUP      — person promised to do X, follow up
      MEMORY_PROMPT           — AI should ask about a high-significance topic
      ROUTINE_DEVIATION       — person is here at unusual time
    """

    def __init__(self, brain_db: "BrainDB", graph_db: "GraphDB"):
        self._db    = brain_db
        self._graph = graph_db

    # ── helpers ───────────────────────────────────────────────────────────────

    def _pending_count(self, person_id: str, nudge_type: str) -> int:
        now = time.time()
        row = self._db._conn.execute(
            """SELECT COUNT(*) FROM proactive_nudges
               WHERE target_person_id = ? AND nudge_type = ?
                 AND injected_at IS NULL AND dismissed_at IS NULL
                 AND (expires_at IS NULL OR expires_at > ?)""",
            (person_id, nudge_type, now),
        ).fetchone()
        return row[0] if row else 0

    def _expires(self) -> float:
        return time.time() + NUDGE_EXPIRY_HOURS * 3600

    # ── public interface ──────────────────────────────────────────────────────

    # Values that are never meaningful as cross-person entity names
    _GARBAGE_VALUES: frozenset = frozenset({
        "true", "false", "yes", "no", "1", "0", "none", "null", "unknown",
        "n/a", "na", "undefined", "empty", "other", "various", "multiple",
        "him", "her", "them", "it", "he", "she", "they", "we", "you", "i",
        "this", "that", "the", "a", "an", "and", "or", "but",
    })

    @staticmethod
    def _is_meaningful_entity(name: str, current_person_name: str, system_name: str) -> bool:
        """Return True if an entity name is worth generating a nudge for."""
        v = name.strip().lower()
        if len(v) < 3:
            return False
        if v in ProactiveNudgeAgent._GARBAGE_VALUES:
            return False
        if v == current_person_name.lower():
            return False   # self-reference
        if v == system_name.lower():
            return False   # AI system name
        return True

    def run_cross_person_inference(
        self,
        current_person_id:   str,
        current_person_name: str,
        faces_conn:          sqlite3.Connection,
        system_name:         str = DEFAULT_SYSTEM_NAME,
    ) -> None:
        """Match current person's known entities against other persons' social mentions.

        Algorithm:
        1. Load all other persons' social mentions.
        2. Load current person's knowledge entity values from brain_db.
        3. Fuzzy-match (rapidfuzz) + Kuzu shared-entity check.
        4. For each match above NUDGE_MIN_CONFIDENCE: store CROSS_PERSON_HYPOTHESIS nudge.
        """
        if self._pending_count(current_person_id, "CROSS_PERSON_HYPOTHESIS") >= CROSS_PERSON_MAX_NUDGES:
            return

        all_mentions = self._db.get_all_social_mentions()
        # Only consider mentions from OTHER persons
        other_mentions = [
            m for m in all_mentions
            if m["source_person_id"] != current_person_id
        ]
        if not other_mentions:
            return

        # Current person's known entity values (from brain.db knowledge).
        # Session 106 Phase 3A.5 — exclude system_only tier so embedding
        # hashes / bootstrap_credits / internal diagnostics can't leak
        # into cross-person inference. The raw SELECT here already
        # scopes by person_id (recipient's own rows) so no additional
        # visibility clause is needed for the 3 user-visible tiers —
        # rows are owner-scoped by construction. The system_only
        # exclusion is the one net-new protection this path gets.
        rows = self._db._conn.execute(
            "SELECT DISTINCT value FROM knowledge WHERE person_id = ? "
            "AND invalidated_at IS NULL AND confidence >= 0.50 "
            "AND privacy_level != 'system_only'",
            (current_person_id,),
        ).fetchall()
        current_values = {
            r[0].lower() for r in rows
            if r[0] and self._is_meaningful_entity(r[0], current_person_name, system_name)
        }

        # Also include Kuzu graph facts via find_shared_entities
        try:
            # Resolve source persons' names for Kuzu queries
            source_ids = {m["source_person_id"] for m in other_mentions}
            for src_id in source_ids:
                row = faces_conn.execute(
                    "SELECT name FROM persons WHERE id = ?", (src_id,)
                ).fetchone()
                if not row:
                    continue
                src_name = row[0]
                shared = self._graph.find_shared_entities(
                    current_person_name, src_name
                )
                for s in shared:
                    # Skip garbage entity names (booleans, short strings, self-refs, system name)
                    if not self._is_meaningful_entity(
                        s["entity_name"], current_person_name, system_name
                    ):
                        continue
                    conf = 0.70  # graph match = high confidence
                    rel_raw = next(
                        (m.get("relationship") for m in other_mentions
                         if m["source_person_id"] == src_id),
                        None,
                    )
                    # Bug 3 (2026-04-20): Kuzu can surface an unset relationship
                    # as the string "null" or "None" (from JSON-serialized Python None
                    # on the shadow_persons side). Both are truthy strings — the plain
                    # `if rel` check let "(possibly your null)" through.
                    rel = rel_raw if rel_raw and str(rel_raw).strip().lower() not in ("null", "none", "") else None
                    content = (
                        f"You and someone I've spoken with both mentioned "
                        f"'{s['entity_name']}' — they might be connected to you"
                        + (f" (possibly your {rel})" if rel else "")
                        + "."
                    )
                    if not self._db.nudge_exists(
                        current_person_id, "CROSS_PERSON_HYPOTHESIS", s["entity_name"]
                    ):
                        self._db.store_nudge(
                            target_person_id=current_person_id,
                            nudge_type="CROSS_PERSON_HYPOTHESIS",
                            content=content,
                            confidence=conf,
                            metadata={
                                "entity":           s["entity_name"],
                                "source_person_id": src_id,
                            },
                            expires_at=self._expires(),
                        )
                        print(f"[NudgeAgent] CROSS_PERSON_HYPOTHESIS for {current_person_name}: {content}")
        except Exception as e:
            print(f"[NudgeAgent] Kuzu cross-person error: {e}")

        # Fuzzy name match: other mention names vs current person's known values
        for mention in other_mentions:
            m_name = mention["name"].lower()
            if not m_name:
                continue
            # Skip garbage mention names
            if not self._is_meaningful_entity(m_name, current_person_name, system_name):
                continue
            best_ratio = 0
            matched_val = ""
            for val in current_values:
                ratio = _rfuzz.ratio(m_name, val)
                if ratio > best_ratio:
                    best_ratio, matched_val = ratio, val
            if best_ratio >= NUDGE_FUZZY_MATCH_RATIO:
                conf = (best_ratio / 100) * 0.75
                if conf < NUDGE_MIN_CONFIDENCE:
                    continue
                rel_raw = mention.get("relationship")
                # Bug 3: same null-string leak as the graph-match branch above.
                rel = rel_raw if rel_raw and str(rel_raw).strip().lower() not in ("null", "none", "") else None
                content = (
                    f"Someone I've spoken with mentioned someone called '{mention['name']}'"
                    + (f" ({rel})" if rel else "")
                    + f" — similar to '{matched_val}' you mentioned. Might be the same person."
                )
                if not self._db.nudge_exists(
                    current_person_id, "CROSS_PERSON_HYPOTHESIS", mention["name"]
                ):
                    self._db.store_nudge(
                        target_person_id=current_person_id,
                        nudge_type="CROSS_PERSON_HYPOTHESIS",
                        content=content,
                        confidence=conf,
                        metadata={
                            "mentioned_name":    mention["name"],
                            "matched_value":     matched_val,
                            "source_person_id":  mention["source_person_id"],
                            "fuzzy_ratio":       best_ratio,
                        },
                        expires_at=self._expires(),
                    )
                    print(f"[NudgeAgent] CROSS_PERSON_HYPOTHESIS for {current_person_name}: {content}")

    def run_intention_followup(self, person_id: str, person_name: str) -> None:
        """Surface old unfollowed promises from recent episodes."""
        cutoff = time.time() - EPISODE_TOPIC_MATCH_DAYS * 86400
        episodes = self._db.get_recent_episodes(person_id, limit=10)
        now = time.time()
        for ep in episodes:
            # Only follow up on sessions older than 24h but within retention window
            age_h = (now - ep["session_end_ts"]) / 3600
            if age_h < 24 or ep["session_end_ts"] < cutoff:
                continue
            for promise in ep.get("promises_made") or []:
                if not promise:
                    continue
                content = f"Last time, you mentioned: '{promise}' — worth checking in on."
                if not self._db.nudge_exists(person_id, "INTENTION_FOLLOWUP", promise[:40]):
                    self._db.store_nudge(
                        target_person_id=person_id,
                        nudge_type="INTENTION_FOLLOWUP",
                        content=content,
                        confidence=0.60,
                        metadata={"promise": promise, "session_end_ts": ep["session_end_ts"]},
                        expires_at=self._expires(),
                    )
                    print(f"[NudgeAgent] INTENTION_FOLLOWUP for {person_name}: {promise[:60]}")

    def run_memory_prompts(self, person_id: str, person_name: str) -> None:
        """Generate nudges for high-significance episode topics not discussed recently."""
        episodes = self._db.get_recent_episodes(person_id, limit=5)
        if not episodes:
            return
        # Find high-significance sessions with topics worth revisiting
        now = time.time()
        for ep in episodes:
            if ep["significance"] < 0.70:
                continue
            age_h = (now - ep["session_end_ts"]) / 3600
            if age_h < 48:  # too recent, not worth prompting yet
                continue
            topics = ep.get("key_topics") or []
            for topic in topics[:2]:
                content = f"You previously talked about '{topic}' in depth — worth revisiting if the moment fits."
                if not self._db.nudge_exists(person_id, "MEMORY_PROMPT", topic[:40]):
                    self._db.store_nudge(
                        target_person_id=person_id,
                        nudge_type="MEMORY_PROMPT",
                        content=content,
                        confidence=0.50,
                        metadata={"topic": topic, "significance": ep["significance"]},
                        expires_at=self._expires(),
                    )
                    print(f"[NudgeAgent] MEMORY_PROMPT for {person_name}: {topic}")


# ── WatchdogAgent ──────────────────────────────────────────────────────────────

class WatchdogAgent:
    """Monitor system health and behavioural anomalies on a background loop.

    Checks every WATCHDOG_INTERVAL seconds:
    - Silent observation rate spikes
    - Repeated unknown faces at unusual hours
    Camera + API failures are reported via report_* methods called from pipeline.

    Alert types: CAMERA_FAILURE, API_FAILURE, UNUSUAL_FACE, SILENT_OBS_ANOMALY,
                 REPEATED_UNKNOWN
    """

    def __init__(self, brain_db: "BrainDB", faces_conn: sqlite3.Connection):
        self._db         = brain_db
        self._faces_conn = faces_conn

    async def run_loop(self, shutdown: asyncio.Event) -> None:
        while not shutdown.is_set():
            try:
                self._check_silent_obs_anomaly()
                self._check_unusual_repeated_faces()
            except Exception as e:
                print(f"[WatchdogAgent] Check error: {e}")
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=WATCHDOG_INTERVAL)
            except asyncio.TimeoutError:
                pass

    # ── called from pipeline ──────────────────────────────────────────────────

    def report_camera_null_streak(self, streak: int) -> None:
        if not self._db.unresolved_alert_exists("CAMERA_FAILURE"):
            self._db.store_alert(
                "CAMERA_FAILURE", "high",
                f"Camera returned {streak} consecutive null frames — reconnect attempted.",
                {"streak": streak},
            )
            print(f"[WatchdogAgent] CAMERA_FAILURE alert stored (streak={streak})")

    def report_api_failure(self, duration_s: float) -> None:
        if not self._db.unresolved_alert_exists("API_FAILURE"):
            self._db.store_alert(
                "API_FAILURE", "medium",
                f"Together.ai unreachable for {int(duration_s)}s — using offline fallback.",
                {"duration_s": duration_s},
            )
            print(f"[WatchdogAgent] API_FAILURE alert stored ({duration_s:.0f}s)")

    def report_dispute_rename_burst(
        self,
        victim_pid: str,
        victim_name: str,
        victim_person_type: str,
        claimed_name: str,
        block_count: int,
        dispute_started_at: "float | None",
    ) -> None:
        """Record a watchdog alert for a persistent disputed-rename attack.

        Fires when a single disputed session has blocked
        ``DISPUTE_RENAME_BLOCK_THRESHOLD`` rename attempts from the LLM — a strong
        signal that either the speaker really isn't the sensor-matched person
        (impersonation / gallery poisoning) or the tool-call loop is misbehaving.
        Severity escalates to ``"critical"`` when the victim's prior type was
        ``best_friend`` since owner-privilege transfer is the highest blast radius.

        Each burst fires its own alert (no cross-session dedup) — the per-session
        ``disputed_block_alerted`` flag in pipeline.py prevents re-firing within
        the same session.
        """
        severity = "critical" if victim_person_type == "best_friend" else "warning"
        message = (
            f"Session matched as {victim_name!r} (person_type={victim_person_type!r}) "
            f"blocked {block_count} rename attempts to {claimed_name!r}. "
            f"Suggests the current speaker may not be {victim_name}. "
            f"Run `python audit_person.py --id {victim_pid}` then "
            f"`python repair_gallery.py --id {victim_pid}` to inspect and clean "
            f"the gallery; factory-reset if drift is severe."
        )
        metadata = {
            "victim_pid":          victim_pid,
            "victim_name":         victim_name,
            "victim_person_type":  victim_person_type,
            "claimed_name":        claimed_name,
            "block_count":         block_count,
            "dispute_started_at":  dispute_started_at,
        }
        self._db.store_alert("DISPUTE_RENAME_BURST", severity, message, metadata)
        print(
            f"[WatchdogAgent] DISPUTE_RENAME_BURST ({severity}): "
            f"{victim_name} blocked {block_count} attempts → {claimed_name!r}"
        )

    def report_anti_spoof_rejection(
        self,
        track_id: str,
        reason: str,
        score: "float | None",
        person_id: "str | None" = None,
    ) -> None:
        """P0.S1 Phase 3 — record a per-instance anti-spoof rejection.

        Severity="info" because a single rejection is usually a transient
        false negative or one frame in a normal scan; the meaningful signal
        is the burst aggregator (`report_anti_spoof_burst`). Operators
        watching the dashboard see these as fine-grained activity entries.
        """
        self._db.store_alert(
            "ANTI_SPOOF_REJECTION",
            "info",
            f"Anti-spoof rejected face for track={track_id} "
            f"reason={reason} score={score!r} person={person_id!r}",
            {
                "track_id":  track_id,
                "reason":    reason,
                "score":     score,
                "person_id": person_id,
            },
        )

    def report_anti_spoof_burst(
        self,
        track_id: str,
        count: int,
        window_secs: float,
        threshold: int,
        person_id: "str | None" = None,
    ) -> None:
        """P0.S1 Phase 3 + §14b.1 — burst-threshold alert (fires once at the
        exact-equality trigger `count == THRESHOLD`).

        Severity="warning" because a sustained burst suggests an active
        attack — repeated photo/screen presentations against the same
        SORT track. The pipeline-side caller guarantees this fires at
        most once per burst window per track (exact-equality + state
        management on the rejection store).
        """
        message = (
            f"Anti-spoof burst threshold reached for track={track_id}: "
            f"{count} rejection(s) within {window_secs:.0f}s "
            f"(threshold={threshold}). "
            f"Likely active presentation attack — check camera view and "
            f"recent enrollment attempts."
        )
        self._db.store_alert(
            "ANTI_SPOOF_BURST",
            "warning",
            message,
            {
                "track_id":    track_id,
                "count":       count,
                "window_secs": window_secs,
                "threshold":   threshold,
                "person_id":   person_id,
            },
        )
        print(
            f"[WatchdogAgent] ANTI_SPOOF_BURST (warning): "
            f"track={track_id} count={count}/{threshold} in {window_secs:.0f}s"
        )

    def resolve_camera_failure(self) -> None:
        """Call from pipeline when camera reconnects successfully."""
        self._db.resolve_alerts_by_type("CAMERA_FAILURE")

    def resolve_api_failure(self) -> None:
        """Call from pipeline when Together.ai recovers."""
        self._db.resolve_alerts_by_type("API_FAILURE")

    def report_antispoof_disabled(self) -> None:
        """Record a persistent alert when MiniFASNet fails to load."""
        if not self._db.unresolved_alert_exists("ANTISPOOF_DISABLED"):
            self._db.store_alert(
                "ANTISPOOF_DISABLED", "high",
                "Anti-spoofing is DISABLED — photo/screen-replay attacks will succeed. "
                "Install silent-face-anti-spoofing to enable.",
                {},
            )
            print("[WatchdogAgent] ANTISPOOF_DISABLED alert stored")

    def report_disk_threshold(
        self,
        level: int,
        percent_used: float,
        free_bytes: int,
        severity: str,
    ) -> None:
        """Store a disk-space threshold crossing alert.

        alert_type encodes the exact threshold (disk_warning_80, disk_warning_90,
        disk_critical_95) so the dashboard can distinguish them.
        Called from core/disk_monitor.check_disk_thresholds; idempotency is
        managed there via _last_disk_alert_level module state.
        """
        alert_type = f"disk_critical_{level}" if level >= 95 else f"disk_warning_{level}"
        self._db.store_alert(
            alert_type,
            severity,
            f"Disk usage crossed {level}% threshold — {percent_used:.1f}% used, "
            f"{free_bytes // 1_000_000}MB free.",
            {"percent_used": percent_used, "free_bytes_at_alert": free_bytes, "level": level},
        )
        print(f"[WatchdogAgent] {alert_type} alert stored ({percent_used:.1f}% used)")

    def report_heavy_worker_burst(
        self,
        task_name: str,
        crash_count: int,
        window_secs: float,
    ) -> None:
        """Store a heavy-worker pool burst-crash alert (P0.R8 D4).

        Called from ``pipeline._heavy_worker_watchdog_loop`` when the rolling
        crash count for a pool within ``HEAVY_WORKER_RESTART_BURST_WINDOW_SECS``
        exceeds ``HEAVY_WORKER_RESTART_BURST_THRESHOLD``.

        Severity is ``warning`` — heavy-worker degraded is recoverable;
        operator-actionable but not session-blocking. ProcessPoolExecutor
        auto-respawns subprocesses on next submit; recovery happens
        implicitly when the crash rate drops below threshold within the
        rolling window.

        Idempotency: managed by the watchdog loop's per-pool ``_alert_armed``
        flag (one alert per pool per burst event; re-arms on recovery).
        """
        self._db.store_alert(
            f"heavy_worker_burst_{task_name}",
            "warning",
            f"Heavy-worker pool '{task_name}' crashed {crash_count} times in "
            f"the last {window_secs:.0f}s. Pool will auto-respawn but is marked "
            f"degraded. Check logs for crash root cause (CUDA OOM, model file "
            f"corruption, etc.).",
            {
                "task_name": task_name,
                "crash_count": crash_count,
                "window_secs": window_secs,
            },
        )
        print(
            f"[WatchdogAgent] heavy_worker_burst_{task_name} alert stored "
            f"({crash_count} crashes / {window_secs:.0f}s)"
        )

    def report_vram_budget_refusal(
        self,
        task_name: str,
        cumulative_mb: int,
        ceiling_mb: int,
        estimate_mb: int,
    ) -> None:
        """Store a VRAM budget refusal alert (P0.R9 D5).

        Called from ``core.heavy_worker.get_or_create_pool`` on first refusal
        per task_name. Severity ``warning`` — graceful degradation (caller's
        fallback fires; system continues running).

        Q8 (a) RATIFIED: per-pool alert granularity (operator wants to know
        WHICH pool degraded). Alert metadata captures pool name + cumulative
        MB + ceiling MB + estimate MB for operator triage.
        """
        self._db.store_alert(
            f"vram_budget_refusal_{task_name}",
            "warning",
            f"Pool '{task_name}' refused spawn (estimate {estimate_mb}MB + "
            f"cumulative {cumulative_mb}MB > ceiling {ceiling_mb}MB). "
            f"Fallback path active. Tune VRAM_POOL_PRIORITY / VRAM_CEILING_PCT / "
            f"HEAVY_WORKER_VRAM_ESTIMATES_MB at core/config.py + restart to recover.",
            {
                "task_name": task_name,
                "cumulative_mb": cumulative_mb,
                "ceiling_mb": ceiling_mb,
                "estimate_mb": estimate_mb,
            },
        )
        print(
            f"[WatchdogAgent] vram_budget_refusal_{task_name} alert stored "
            f"(estimate={estimate_mb}MB, cumulative={cumulative_mb}MB, "
            f"ceiling={ceiling_mb}MB)"
        )

    def report_audio_device_burst(
        self,
        channel: str,
        failure_count: int,
        window_secs: float,
    ) -> None:
        """Store an audio-device burst alert (P0.R10 D4).

        Called from ``pipeline._audio_device_watchdog_loop`` when the rolling
        failure count for a channel within ``AUDIO_DEVICE_BURST_WINDOW_SECS``
        exceeds ``AUDIO_DEVICE_BURST_THRESHOLD``.

        Q8 (a) RATIFIED severity ``warning``: graceful degradation (caller's
        fallback fires; system continues running). Mirrors P0.R8
        ``report_heavy_worker_burst`` shape.

        Q1 (a) RATIFIED per-channel granularity: channel in {'mic', 'speaker'};
        alert key includes channel name for operator triage clarity.

        Idempotency: managed by the watchdog loop's per-channel
        ``_alert_armed`` flag (one alert per channel per burst event; re-arms
        on recovery).
        """
        self._db.store_alert(
            f"audio_device_burst_{channel}",
            "warning",
            f"Audio device '{channel}' failure burst — {failure_count} failures in "
            f"{window_secs:.0f}s window. Check device connection / driver / "
            f"permissions. Clears when failure rate drops below "
            f"AUDIO_DEVICE_BURST_THRESHOLD.",
            {
                "channel": channel,
                "failure_count": failure_count,
                "window_secs": window_secs,
            },
        )
        print(
            f"[WatchdogAgent] audio_device_burst_{channel} alert stored "
            f"(count={failure_count}, window={window_secs:.0f}s)"
        )

    # ── periodic checks ───────────────────────────────────────────────────────

    def _check_silent_obs_anomaly(self) -> None:
        cutoff = time.time() - WATCHDOG_INTERVAL
        count = self._faces_conn.execute(
            "SELECT COUNT(*) FROM silent_observations WHERE last_seen > ?",
            (cutoff,),
        ).fetchone()[0]
        if count >= WATCHDOG_SILENT_OBS_SPIKE:
            self._db.store_alert(
                "SILENT_OBS_ANOMALY", "low",
                f"{count} new silent observations in the last {int(WATCHDOG_INTERVAL)}s.",
                {"count": count},
            )
            print(f"[WatchdogAgent] SILENT_OBS_ANOMALY: {count} observations in last interval")

    def _check_unusual_repeated_faces(self) -> None:
        now = time.time()
        hour = datetime.datetime.now().hour
        if not (WATCHDOG_UNUSUAL_HOUR_START <= hour <= WATCHDOG_UNUSUAL_HOUR_END):
            return
        cutoff = now - WATCHDOG_INTERVAL * 3   # seen in last 3 check intervals
        rows = self._faces_conn.execute(
            "SELECT id, first_seen, last_seen, frame_count FROM silent_observations "
            "WHERE last_seen > ? AND frame_count >= 10",
            (cutoff,),
        ).fetchall()
        if rows and not self._db.unresolved_alert_exists("UNUSUAL_FACE"):
            self._db.store_alert(
                "UNUSUAL_FACE", "medium",
                f"Unknown face seen at unusual hour ({hour:02d}:xx) with {rows[0][3]} frames.",
                {"hour": hour, "observation_id": rows[0][0]},
            )
            print(f"[WatchdogAgent] UNUSUAL_FACE at hour {hour}")


# ── BrainOrchestrator ──────────────────────────────────────────────────────────

class BrainOrchestrator:
    """Coordinates all brain agents. Runs as a background asyncio task.

    Polls conversation_log in faces.db for new turns (turn_id >
    brain_state.last_turn_id), runs each turn through the three-agent
    pipeline, and stores extracted knowledge to brain.db.

    Completely decoupled from the conversation pipeline — the conversation
    never waits for the brain. Memory extraction happens asynchronously
    and knowledge is available by the next turn at human conversation pace.

    Crash-safe: last_turn_id is written atomically after each turn, so a
    restart resumes exactly where it left off. All graph writes use
    REPLACE semantics to prevent duplicates on retry.
    """

    def __init__(self, shutdown_event: asyncio.Event, *,
                 brain_db_path=None, graph_db_path=None, faces_db_path=None):
        self._shutdown     = shutdown_event
        self._trigger      = asyncio.Event()   # fired by pipeline after log_turn
        # Store resolved paths so reopen_connections() uses the same locations.
        self._brain_db_path  = brain_db_path  if brain_db_path  is not None else BRAIN_DB_PATH
        self._graph_db_path  = graph_db_path  if graph_db_path  is not None else GRAPH_DB_PATH
        self._faces_db_path  = str(faces_db_path if faces_db_path is not None else DB_PATH)
        self._brain_db     = BrainDB(self._brain_db_path)
        # P0.X: if a schema upgrade is pending, write the sentinel BEFORE constructing
        # GraphDB — GraphDB.__init__ calls _init_schema() which may fail during upgrade.
        if self._brain_db.get_graph_schema_version() < GRAPH_SCHEMA_VERSION:
            self._mark_kuzu_dirty()
        self._graph_db     = GraphDB(self._graph_db_path)
        # Separate read-only connection to faces.db — WAL mode allows this
        # to coexist safely with pipeline writes.
        self._faces_conn   = sqlite3.connect(
            self._faces_db_path, check_same_thread=False,
            isolation_level="IMMEDIATE",  # P0.9.1 Imp-1
        )
        self._http         = httpx.AsyncClient(timeout=20.0)
        self._triage          = TriageAgent()
        self._extractor       = ExtractionAgent(self._http)
        self._contradictor    = ContradictionAgent(self._http)
        self._pref_agent      = PromptPrefAgent(self._http)
        self._friction_agent  = FrictionDetectionAgent(self._http)
        self._embed_agent  = EmbeddingAgent(self._http)
        self._schema_norm    = SchemaNormAgent(self._brain_db, self._embed_agent)
        self._spatial_memory = SpatialMemoryAgent(self._brain_db)
        self._pattern_agent  = ObjectPatternAgent(self._brain_db, self._http)
        self._social_graph   = SocialGraphAgent(self._http)
        self._identity_agent = IdentityAgent()
        self._briefing_agent = BriefingAgent(self._http)
        self._insight_agent  = ConversationInsightAgent(self._http)
        self._routine_agent  = RoutineAgent(self._brain_db)
        self._nudge_agent    = ProactiveNudgeAgent(self._brain_db, self._graph_db)
        self._watchdog       = WatchdogAgent(self._brain_db, self._faces_conn)
        self._household_agent = HouseholdExtractionAgent(self._http)
        self._system_name: str = DEFAULT_SYSTEM_NAME  # updated by pipeline when system_name tool fires
        # Per-session state (keyed by person_id)
        self._session_turn_counts: dict[str, int]   = {}
        self._intra_pref_done:     set[str]          = set()
        self._session_start_ts:    dict[str, float]  = {}   # first turn ts this session
        # Identity-dispute registry: person_ids whose current session has been flagged
        # as disputed (speaker contradicted the sensor). While listed, extraction is
        # paused so we don't pollute either person's knowledge with contradictory facts.
        self._disputed_persons:    set[str]          = set()
        self._kuzu_degraded: bool = False
        self._ensure_graph_sync()

    def _kuzu_sentinel_path(self) -> "Path":
        p = Path(self._graph_db_path)
        return p.parent / (p.name + ".dirty")

    def _mark_kuzu_dirty(self) -> None:
        try:
            self._kuzu_sentinel_path().touch()
        except Exception:
            pass  # CLEANUP: sentinel write failure is non-fatal

    def _clear_kuzu_dirty(self) -> None:
        try:
            self._kuzu_sentinel_path().unlink(missing_ok=True)
        except Exception:
            pass  # CLEANUP: sentinel clear failure is non-fatal

    def _ensure_graph_sync(self) -> None:
        """Rebuild graph from SQLite if needed.

        Handles two cases:
        1. Cold start / crash recovery: graph is empty but SQLite has rows.
        2. Schema upgrade: GRAPH_SCHEMA_VERSION bumped — Kuzu REL tables can't
           be ALTER TABLE'd, so we wipe the graph and rebuild with new schema.

        P0.B3 D1 ORDERING INVARIANT (Finding 2 board-meeting 2026-05-21 fix):
          1. Capture `_did_schema_upgrade = (stored_version < GRAPH_SCHEMA_VERSION)`
             at function entry — BEFORE any state mutation. This is the in-flight
             intent flag; tells the success path whether to commit the SQL version
             bump at the end.
          2. _mark_kuzu_dirty() FIRST — sentinel SET BEFORE any destructive op.
          3. IF schema upgrade pending: drop_schema() + _init_schema() (Kuzu ops).
             Crash here: kuzu_degraded=True, sentinel persists, stored_version=OLD
             → next boot re-enters via predicate at step 1.
          4. Compute need_rebuild via the migration-block-success OR boot-reconciliation
             (sentinel-exists OR entity-count-mismatch).
          5. IF need_rebuild AND NOT degraded: rebuild(knowledge_rows). Crash here:
             kuzu_degraded=True, sentinel persists, stored_version=OLD → next boot
             re-enters via predicate at step 1.
          6. _clear_kuzu_dirty() ONLY after rebuild() success.
          7. IF `_did_schema_upgrade` AND NOT degraded: update_graph_schema_version(NEW)
             — SQL commit ONLY at the end, AFTER Kuzu schema + data both at NEW + sentinel
             cleared. This is the LOAD-BEARING fix: pre-P0.B3 the SQL bump happened at step
             3-pre-Kuzu-ops, which left SQL=NEW + Kuzu=PARTIAL on crash; the migration
             predicate at step 1 became FALSE on next boot, silently trapping the system
             in permanent _kuzu_degraded=True with no operator-visible recovery signal.
             Post-P0.B3 the SQL bump lands ONLY at full success; any crash before this
             leaves stored_version=OLD → next boot retries idempotently.
          8. Sentinel-only rebuild paths (boot reconciliation, count mismatch) MUST NOT
             bump the SQL version — `_did_schema_upgrade=False` gates this correctly.
          9. degraded-mode caught-but-unfixable crashes leave sentinel + stored_version=OLD
             on disk → next process restart re-enters the migration block fresh + retries.
         10. Cross-spec invariant: P0.X SCHEMA_MIGRATION pattern's "SQL-first" framing
             applies to paired DATA writes (brain.db row + Kuzu edge). For the version
             BUMP itself, SQL-LAST is correct because SQL is the source-of-truth FOR
             which schema-state-is-canonical — committing it prematurely commits a
             lie. P0.X behavior for paired data writes is unchanged.
        """
        stored_version = self._brain_db.get_graph_schema_version()
        _did_schema_upgrade = stored_version < GRAPH_SCHEMA_VERSION  # P0.B3 D1 intent flag

        need_rebuild = False
        if _did_schema_upgrade:
            print(
                f"[BrainAgent] Graph schema v{stored_version}→v{GRAPH_SCHEMA_VERSION}: "
                "wiping Kuzu graph for rebuild with new schema"
            )
            # P0.B3 D1: SQL version bump REMOVED from this block per Finding 2 fix.
            # Sentinel + Kuzu ops only here; SQL commit deferred to the rebuild-success
            # branch below, gated on `_did_schema_upgrade`. See function docstring
            # ORDERING INVARIANT step 7 for rationale.
            self._mark_kuzu_dirty()
            try:
                self._graph_db.drop_schema()
                self._graph_db._init_schema()
                need_rebuild = True
            except Exception as e:
                self._kuzu_degraded = True
                print(f"[BrainAgent] Graph schema migration failed — degraded mode: {e!r}")

        # Boot reconciliation: sentinel OR entity-count mismatch.
        if not need_rebuild:
            if self._kuzu_sentinel_path().exists():
                need_rebuild = True
            else:
                sql_entity_count = self._brain_db.count_active_knowledge_entities()
                kuzu_entity_count = self._graph_db.entity_count()
                if sql_entity_count != kuzu_entity_count:
                    need_rebuild = True

        if need_rebuild and not self._kuzu_degraded:
            knowledge_rows = self._brain_db.get_all_knowledge_rows()
            try:
                if knowledge_rows:
                    # P0.S7.D-B observability — surface scale-of-pain in canary logs
                    # (auditor obs B). Measures wall-clock + emits entity_count +
                    # edge_count so production rebuilds (v2→v3 schema upgrade) can
                    # be reasoned about empirically. `stored_version` is the pre-bump
                    # version captured at function entry (the SQL bump lands AFTER
                    # `_clear_kuzu_dirty()` below per P0.B3 D1); report the jump
                    # against the pre-bump baseline explicitly.
                    _rebuild_t0 = time.time()
                    self._graph_db.rebuild(knowledge_rows)
                    _rebuild_secs = time.time() - _rebuild_t0
                    _ent_count = self._graph_db.entity_count()
                    print(
                        f"[BrainAgent] Graph rebuilt from {len(knowledge_rows)} SQLite rows"
                    )
                    print(
                        f"[Schema] Graph rebuild v{stored_version}\u2192v{GRAPH_SCHEMA_VERSION} "
                        f"completed in {_rebuild_secs:.2f}s "
                        f"({_ent_count} entities, {len(knowledge_rows)} edges)"
                    )
                self._clear_kuzu_dirty()
                # P0.B3 D1 (Finding 2 board-meeting 2026-05-21 fix): SQL version bump
                # ONLY here — after rebuild success + sentinel clear. Gated on
                # `_did_schema_upgrade` so sentinel-only rebuilds (boot reconciliation,
                # count mismatch) do NOT bump the version. See function docstring
                # ORDERING INVARIANT step 7 for the load-bearing rationale (pre-fix:
                # SQL=NEW + Kuzu=PARTIAL on crash trapped boot in permanent degraded).
                if _did_schema_upgrade:
                    self._brain_db.update_graph_schema_version(GRAPH_SCHEMA_VERSION)
            except Exception as e:
                self._kuzu_degraded = True
                print(f"[BrainAgent] Graph rebuild failed at boot — degraded mode: {e!r}")

    def _schedule_startup_tasks(self) -> None:
        """Schedule background tasks that should run once after startup."""
        asyncio.create_task(self._schema_norm.maybe_run())
        asyncio.create_task(self._pattern_agent.maybe_run())
        asyncio.create_task(self._backfill_embeddings())   # Item 5: embed pre-Phase-3 rows

    @property
    def brain_db(self) -> "BrainDB":
        """Public read access to the brain knowledge store.

        Pipeline query paths (visitor alerts, room context, core memory,
        knowledge search, intent logging) use this instead of reaching
        through the private _brain_db attribute. P1.A1-slice layering fix.
        """
        return self._brain_db

    def notify(self) -> None:
        """Wake the brain agent immediately to process new turns.

        Called by the pipeline after db.log_turn() so extraction starts
        during TTS playback rather than waiting for the next poll interval.
        Facts are then ready in brain.db by the time the user speaks again.
        """
        print(f"[BrainAgent] Notify — waking agent loop")
        self._trigger.set()

    def mark_disputed(self, person_id: str) -> None:
        """Mark a person's current session as identity-disputed (pauses extraction)."""
        self._disputed_persons.add(person_id)

    def clear_disputed(self, person_id: str) -> None:
        """Clear the dispute flag for a person (e.g. on resolution or session end)."""
        self._disputed_persons.discard(person_id)

    def on_identity_confirmed(self, person_id: str, old_name: str, new_name: str) -> None:
        """Atomic-within-brain.db identity promotion chain.

        Storage ordering (caller must have already committed faces.db):
            1. CALLER (before this fn): faces.db UPDATE persons SET name=?, type=?  (atomic)
            2. brain.db transaction (this fn) — all-or-nothing:
               - migrate_entity_name(old, new, person_id)
               - promote_shadow_to_confirmed(new, person_id)
               - update_visitor_alert_for_promoted_person(person_id, new)
               - get_knowledge_rows_for_kuzu (read-after-write, sees post-rename rows)
            3. brain_graph: rebuild_entity_from_knowledge (after brain.db commit)

        Crash recovery:
            - Crash between step 1 and 2: faces.db has new name; brain.db rolls back;
              old facts still under old name. Re-running promotion is idempotent.
            - Crash mid-step-2: brain.db rolls back atomically.
            - Crash between step 2 and 3: brain.db consistent; graph stale.
              rebuild_entity_from_knowledge self-heals on next graph access.
        """
        kuzu_rows = None
        try:
            with self._brain_db.transaction():
                self._brain_db.migrate_entity_name(old_name, new_name, person_id)
                self._brain_db.promote_shadow_to_confirmed(new_name, person_id)
                # Session 114 Part 5 — visitor alert dedup at promotion time.
                self._brain_db.update_visitor_alert_for_promoted_person(
                    person_id, new_name,
                )
                # Read-after-write within the transaction sees post-rename rows.
                kuzu_rows = self._brain_db.get_knowledge_rows_for_kuzu(person_id, new_name)
        except Exception as e:
            print(
                f"[BrainOrchestrator] on_identity_confirmed brain.db transaction failed: {e!r}"
            )
            raise  # RAISE: caller must know

        if self._graph_db and kuzu_rows is not None:
            self._mark_kuzu_dirty()  # Eager sentinel BEFORE Kuzu op.
            try:
                self._graph_db.rebuild_entity_from_knowledge(new_name, kuzu_rows)
                self._clear_kuzu_dirty()
            except Exception as e:
                print(
                    f"[BrainOrchestrator] on_identity_confirmed graph rebuild failed "
                    f"(brain.db OK, sentinel written for next-boot): {e!r}"
                )
                raise  # RAISE: sentinel preserved for next-boot

    def _persist_extraction_to_kuzu(self, facts, turn_id: int) -> None:
        """Write extracted facts to Kuzu graph. SWALLOW pattern — brain.db is authoritative.

        P0.X: degraded mode or Kuzu write failure → sentinel written, exception swallowed.
        """
        if self._kuzu_degraded:
            return
        try:
            for fact in facts:
                self._graph_db.upsert_entity(fact.entity, fact.entity_type)
        except Exception as e:
            self._mark_kuzu_dirty()  # SWALLOW: sentinel for next-boot heal
            print(
                f"[BrainAgent] Kuzu write failed in _persist_extraction_to_kuzu "
                f"(turn {turn_id}): {e!r}"
            )

    def notify_session_end(self, person_id: str) -> None:
        """Called on face-loss for any person with an active session.

        Flushes remaining unprocessed turns (via notify) then schedules all
        session-end background tasks: preference analysis, episode insight,
        presence logging, nudge generation, and spatial pattern analysis.
        Resets per-session state so the next session starts clean.

        Identity-disputed sessions skip every synthesis task — the turns may
        belong to someone other than the sensor-matched person, and running
        pref/insight/presence/nudge/household analysis would permanently
        attribute them to the wrong identity. Per-session state is still
        reset below so the next encounter starts clean.
        """
        row = self._faces_conn.execute("SELECT name FROM persons WHERE id = ?", (person_id,)).fetchone()
        pname_log = row[0] if row else person_id
        is_disputed = person_id in self._disputed_persons
        if is_disputed:
            print(
                f"[BrainAgent] Session end: {pname_log} ({person_id}) — "
                f"IDENTITY DISPUTED, skipping all synthesis tasks"
            )
        else:
            print(f"[BrainAgent] Session end: {pname_log} ({person_id}) — launching async tasks")
        self.notify()
        # Capture session start time BEFORE popping — async tasks need it.
        started = self._session_start_ts.pop(person_id, None)
        # SYNTHESIS TASKS — all gated on dispute flag. When adding a new session-end
        # helper, add it INSIDE this `if not is_disputed:` block so it also respects
        # the dispute gate by default.
        if not is_disputed:
            asyncio.create_task(self._run_pref_analysis(person_id))
            asyncio.create_task(self._run_insight_analysis(person_id, started))
            asyncio.create_task(self._run_presence_log(person_id, started))
            asyncio.create_task(self._run_nudge_generation(person_id))
            asyncio.create_task(self._run_visitor_alert(person_id))
            asyncio.create_task(self._pattern_agent.maybe_run(self._spatial_memory._new_count))
            if started:
                row = self._faces_conn.execute(
                    "SELECT name FROM persons WHERE id = ?", (person_id,)
                ).fetchone()
                pname = row[0] if row else person_id
                asyncio.create_task(self._run_household_session_end(person_id, pname, started))
        # Reset per-session state for next encounter
        self._session_turn_counts.pop(person_id, None)
        self._intra_pref_done.discard(person_id)

    async def _run_insight_analysis(self, person_id: str, started: float | None = None) -> None:
        """Generate a structured episode summary for the completed session."""
        if not started:
            return
        ended = time.time()

        row = self._faces_conn.execute(
            "SELECT name FROM persons WHERE id = ?", (person_id,)
        ).fetchone()
        person_name = row[0] if row else person_id

        turns_raw = self._faces_conn.execute(
            """SELECT role, content FROM conversation_log
               WHERE person_id = ? AND ts >= ?
               ORDER BY id ASC""",
            (person_id, started),
        ).fetchall()
        turns = [{"role": r[0], "content": r[1]} for r in turns_raw]
        if len(turns) < INSIGHT_MIN_TURNS:
            return

        episode = await self._insight_agent.analyze(
            person_name, turns, started, ended
        )
        if episode:
            self._brain_db.store_episode(
                person_id, episode, started, ended, len(turns)
            )
            print(
                f"[InsightAgent] Episode stored for {person_name}: "
                f"mood={episode.get('mood')} sig={episode.get('significance_score')}"
            )

    async def _run_presence_log(self, person_id: str, started: float | None = None) -> None:
        """Log the completed visit window and run routine pattern detection."""
        if not started:
            return
        self._brain_db.log_presence(person_id, started, time.time())

        row = self._faces_conn.execute(
            "SELECT name FROM persons WHERE id = ?", (person_id,)
        ).fetchone()
        if not row:
            return
        person_name = row[0]
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, self._routine_agent.analyze, person_id, person_name
        )

    async def _run_nudge_generation(self, person_id: str) -> None:
        """Run all ProactiveNudgeAgent passes for the completed session."""
        row = self._faces_conn.execute(
            "SELECT name FROM persons WHERE id = ?", (person_id,)
        ).fetchone()
        if not row:
            return
        person_name = row[0]
        loop = asyncio.get_event_loop()
        # Cross-person inference needs faces_conn for source-person name lookups
        await loop.run_in_executor(
            None,
            self._nudge_agent.run_cross_person_inference,
            person_id, person_name, self._faces_conn, self._system_name,
        )
        await loop.run_in_executor(
            None, self._nudge_agent.run_intention_followup, person_id, person_name
        )
        await loop.run_in_executor(
            None, self._nudge_agent.run_memory_prompts, person_id, person_name
        )

    async def synthesize_room(
        self,
        room_session_id: str,
        speaker_pids: "list[str]",
        started_at: "float | None" = None,
    ) -> None:
        """Phase 3B.6 — room-end synthesis. Called fire-and-forget from
        `_on_room_end`. Three parallel tasks:

          A. Topic aggregation — pure DB, cheap. Fetches knowledge rows
             (extraction-agent output) with ts in the room window and
             gathers distinct ``entity`` values for the top topic tags.
          B. Safety flag aggregation — pure DB. Filters knowledge rows
             matching ``SAFETY_CRITICAL_ATTRIBUTE_PATTERNS`` (Session
             105 Bug N) with per-speaker attribution — so a visitor
             who expressed suicidal thoughts while in the room shows
             up in the room's safety summary even if the attribute
             was logged under their own pid.
          C. Narrative summary — LLM call with bounded timeout. Renders
             1-2 sentences for greeting enrichment. On timeout or
             failure, falls back to a topic-tag-only string so the row
             still has a non-empty summary (never blocks room end).

        Gated on ``ROOM_END_SYNTHESIS_ENABLED`` — one-line rollback via
        flag if a live canary exposes a regression. Single-person room
        sessions skip synthesis (no rich multi-person context to
        summarize; the per-person session-end path already captures
        single-speaker insight).
        """
        import json as _json_sr
        import re as _re_sr
        from core.config import (
            ROOM_END_SYNTHESIS_ENABLED as _ENABLED,
            ROOM_SUMMARY_LLM_TIMEOUT_SECS as _LLM_TIMEOUT,
            SAFETY_CRITICAL_ATTRIBUTE_PATTERNS as _SAFETY_PAT,
        )
        if not _ENABLED:
            return
        if not room_session_id or not speaker_pids:
            return
        if len(speaker_pids) < 2:
            # Single-person room — per-person session-end synthesis
            # already handles this; no cross-speaker context to add.
            return

        # Determine time window from conversation_log rows that carry
        # this room_session_id (most authoritative — Session 107's
        # log_turn stamp drives everything downstream).
        row = self._faces_conn.execute(
            "SELECT MIN(ts), MAX(ts), COUNT(*) FROM conversation_log "
            "WHERE room_session_id = ?",
            (room_session_id,),
        ).fetchone()
        if not row or row[2] == 0:
            print(f"[Room] synthesize_room({room_session_id}) — no turns logged, skipping")
            return
        db_started, db_ended, turn_count = row
        # started_at kwarg wins if caller supplies it (matches room-mint
        # time, not first-turn ts). Ended_at comes from last turn.
        started_at = started_at if started_at is not None else db_started
        ended_at = time.time()

        # --- (A) Topic aggregation ----------------------------------------
        topic_tags: list[str] = []
        try:
            # Pull distinct entity values extracted from turns logged by
            # any speaker in this room during the window.
            topic_tags = self._brain_db.get_knowledge_topic_tags_for_persons(
                speaker_pids, started_at, ended_at
            )
        except Exception as _ex:
            print(f"[Room] synthesize_room topic aggregation failed: {_ex!r}")

        # --- (B) Safety flag aggregation ----------------------------------
        safety_flags: list[dict] = []
        try:
            safety_rows = self._brain_db.get_knowledge_rows_for_persons(
                speaker_pids, started_at, ended_at
            )
            for pid, entity, attr, value in safety_rows:
                is_safety = any(
                    _re_sr.match(pat, attr or "") for pat in _SAFETY_PAT
                )
                if not is_safety:
                    continue
                # Resolve human-readable name for attribution.
                r = self._faces_conn.execute(
                    "SELECT name FROM persons WHERE id = ?", (pid,),
                ).fetchone()
                speaker_name = r[0] if r else pid
                safety_flags.append({
                    "pid":       pid,
                    "name":      speaker_name,
                    "attribute": attr,
                    "entity":    entity,
                })
        except Exception as _ex:
            print(f"[Room] synthesize_room safety aggregation failed: {_ex!r}")

        # --- (C) Narrative summary via LLM --------------------------------
        summary = ""
        try:
            turns = self._faces_conn.execute(
                "SELECT role, content FROM conversation_log "
                "WHERE room_session_id = ? ORDER BY ts ASC LIMIT 20",
                (room_session_id,),
            ).fetchall()
            transcript = "\n".join(
                f"{role}: {content}" for role, content in turns if content
            )
            # Resolve speaker names for a cleaner prompt.
            name_rows = self._faces_conn.execute(
                f"SELECT id, name FROM persons WHERE id IN ({placeholders})",
                tuple(speaker_pids),
            ).fetchall()
            speaker_names = [n for _i, n in name_rows] or list(speaker_pids)
            user_prompt = (
                f"Summarize this conversation between {', '.join(speaker_names)} "
                f"in 1-2 sentences for future memory reference. Focus on what "
                f"was discussed and any significant moments. No preamble.\n\n"
                f"{transcript}"
            )
            # P0.S5 D1 + Plan v2 §1 RoomSynth disposition: single-wrap on
            # assembled transcript. Speaker labels stay inside the wrap as
            # documentation; multi-speaker self-close residual risk accepted
            # per Plan v2 §3.11 (file P0.S5.X if canary surfaces escape).
            llm_out = await _call_llm_chat(
                self._http,
                [{"role": "user", "content": wrap_user_input(user_prompt)}],
                agent_name="RoomSynth",
                max_tokens=120,
                temperature=0.3,
                timeout=_LLM_TIMEOUT,
            )
            if llm_out:
                summary = (llm_out or "").strip()
        except Exception as _ex:
            print(f"[Room] synthesize_room narrative LLM failed: {_ex!r}")
        if not summary:
            # Fallback: topic-only. Still informative, no LLM dependency.
            if topic_tags:
                summary = f"Topics discussed: {', '.join(topic_tags[:5])}."
            else:
                summary = f"Conversation with {', '.join(speaker_pids)}."

        # --- Persist ------------------------------------------------------
        try:
            self._brain_db.store_room_summary(
                room_session_id=room_session_id,
                started_at=started_at,
                ended_at=ended_at,
                speaker_pids=speaker_pids,
                summary=summary,
                topic_tags=topic_tags,
                safety_flags=safety_flags,
            )
            print(
                f"[Room] Synthesis complete for {room_session_id}: "
                f"{turn_count} turns, {len(topic_tags)} topics, "
                f"{len(safety_flags)} safety flag(s)"
            )
        except Exception as _ex:
            print(f"[Room] synthesize_room store failed: {_ex!r}")

    async def _run_visitor_alert(self, person_id: str) -> None:
        """Queue a VISITOR_ALERT nudge for the best friend when any
        non-owner session closes.

        Session 98 Bug A: the original gate only fired for sessions where
        the person was STILL 'stranger' at close. Session 97 Fix 1's
        promotion chain flipped the pid's ``person_type`` to ``'known'``
        during the session if the visitor said their name — which
        suppressed the alert for exactly the sessions we most want the
        owner to know about. 2026-04-23 canary showed this live: Lexi
        introduced herself, got promoted, her session-end fired NO alert,
        the owner's later "who were you talking to?" had no
        ``[visitor_id:`` marker in prompt_addendum, the Session 96
        VISITOR CONTEXT block didn't activate, and Ollama fallback
        confabulated "there wasn't anyone else here." The fix: fire the
        alert for any non-owner session close that produced user turns,
        regardless of promotion status.

        Gates (in order):
          - person row exists
          - person is NOT the best_friend themselves (owner shouldn't get
            visitor-alerts about their own activity)
          - person spoke at least once (turn_count > 0)
          - best_friend enrolled
          - no duplicate VISITOR_ALERT already pending for this pid

        Nudge expires in 24 hours.
        """
        row = self._faces_conn.execute(
            "SELECT person_type, name FROM persons WHERE id=?", (person_id,)
        ).fetchone()
        if not row:
            return
        person_type, person_name = row[0], row[1]

        # Scope gate — skip silent/accidental encounters.
        turn_count = self._faces_conn.execute(
            "SELECT COUNT(*) FROM conversation_log WHERE person_id=? AND role='user'",
            (person_id,)
        ).fetchone()[0]
        if turn_count == 0:
            return

        # Best_friend lookup + self-skip (owner shouldn't alert on themselves).
        bf = self._faces_conn.execute(
            "SELECT id, name FROM persons WHERE person_type='best_friend' LIMIT 1"
        ).fetchone()
        if not bf:
            return
        bf_id, bf_name = bf
        if bf_id == person_id:
            return

        # Dedup — don't queue a second alert for the same pid.
        if self._brain_db.nudge_exists(bf_id, "VISITOR_ALERT", person_id):
            return

        # Display name: real name if promoted ('known'), placeholder if still stranger.
        # Session 100 Bug G: surface the actual visitor_name as a parseable
        # marker so the VISITOR CONTEXT prompt block can name it as the
        # search_memory entity. Without this, the block instructed the brain
        # to "call search_memory" but the brain defaulted to the asker's
        # name (2026-04-23 canary: Jagan asked about Lexi, brain called
        # search_memory('Gevan', ...) → no results → lied "no one was here").
        if person_type == "stranger" and person_name.lower() == "visitor":
            display_name = "an unidentified visitor"
            name_marker  = "[visitor_name:unknown]"
        else:
            display_name = person_name
            name_marker  = f"[visitor_name:{person_name}]"
        turns_desc = "briefly" if turn_count <= 2 else "for a while"

        # Session 105 Bug N Part 3 — surface safety-flag concerns proactively.
        # Query the visitor's knowledge rows for any safety-critical
        # attribute (expressed_suicidal_thoughts, mentioned_self_harm,
        # etc. — append-only history from Bug N Part 2). When at least one
        # flag is present, embed a [safety_flags:...] marker alongside
        # the visitor_name marker so the VISITOR CONTEXT block can tell
        # the brain to surface the concern proactively. Canary 2026-04-23:
        # Lexi's suicidal disclosure was stored but never raised to Jagan
        # even when he asked about her state — the owner should hear the
        # safety-flag regardless of whether the specific query path hits.
        safety_flags: list[str] = []
        try:
            safety_rows = self._brain_db.get_true_valued_attributes(person_id)
            for _attr in safety_rows:
                if _is_safety_critical_attribute(_attr):
                    safety_flags.append(_attr)
        except Exception as _sfx:
            print(f"[Brain] safety-flag scan failed for {person_id}: {_sfx!r}")
        safety_marker = (
            f" [safety_flags:{','.join(sorted(safety_flags))}]"
            if safety_flags else ""
        )
        content = (
            f"{display_name.capitalize()} stopped by while you were away and we talked {turns_desc}. "
            f"{name_marker} [visitor_id:{person_id}]{safety_marker}"
        )

        self._brain_db.store_nudge(
            bf_id, "VISITOR_ALERT", content,
            confidence=0.9,
            metadata={
                "visitor_id":    person_id,
                "visitor_name":  person_name,
                "visitor_type":  person_type,  # Session 98 — surface promoted-vs-stranger
                "turn_count":    turn_count,
                "safety_flags":  safety_flags,  # Session 105 Bug N Part 3
            },
            expires_at=time.time() + 86400,
        )
        _safety_log = f", safety_flags={safety_flags}" if safety_flags else ""
        print(
            f"[Brain] Visitor alert queued for {bf_name} — {display_name} "
            f"stopped by ({turn_count} turns, type={person_type}{_safety_log})"
        )

    def set_system_name(self, name: str) -> None:
        """Called by pipeline when the AI's name is set or changed."""
        self._system_name = name
        self._household_agent.set_system_name(name)

    def report_camera_null_streak(self, streak: int) -> None:
        """Report a camera null-frame streak to the watchdog."""
        self._watchdog.report_camera_null_streak(streak)

    def report_camera_recovered(self) -> None:
        """Mark CAMERA_FAILURE alerts resolved after successful reconnect."""
        self._watchdog.resolve_camera_failure()

    def report_antispoof_disabled(self) -> None:
        """Record a persistent ANTISPOOF_DISABLED watchdog alert."""
        self._watchdog.report_antispoof_disabled()

    def report_api_failure(self, duration_s: float) -> None:
        """Report Together.ai being unreachable to the watchdog."""
        self._watchdog.report_api_failure(duration_s)

    def report_dispute_rename_burst(
        self,
        victim_pid: str,
        victim_name: str,
        victim_person_type: str,
        claimed_name: str,
        block_count: int,
        dispute_started_at: "float | None",
    ) -> None:
        """Surface a watchdog alert for persistent disputed-rename attempts."""
        self._watchdog.report_dispute_rename_burst(
            victim_pid=victim_pid,
            victim_name=victim_name,
            victim_person_type=victim_person_type,
            claimed_name=claimed_name,
            block_count=block_count,
            dispute_started_at=dispute_started_at,
        )

    def report_api_recovered(self) -> None:
        """Mark API_FAILURE alerts resolved after recovery."""
        self._watchdog.resolve_api_failure()

    def report_anti_spoof_rejection(
        self,
        track_id: str,
        reason: str,
        score: "float | None",
        person_id: "str | None" = None,
    ) -> None:
        """P0.S1 Phase 3 — surface a per-instance anti-spoof rejection."""
        self._watchdog.report_anti_spoof_rejection(
            track_id=track_id,
            reason=reason,
            score=score,
            person_id=person_id,
        )

    def report_anti_spoof_burst(
        self,
        track_id: str,
        count: int,
        window_secs: float,
        threshold: int,
        person_id: "str | None" = None,
    ) -> None:
        """P0.S1 Phase 3 + §14b.1 — surface burst-threshold alert (warning)."""
        self._watchdog.report_anti_spoof_burst(
            track_id=track_id,
            count=count,
            window_secs=window_secs,
            threshold=threshold,
            person_id=person_id,
        )

    def report_disk_threshold(
        self,
        level: int,
        percent_used: float,
        free_bytes: int,
        severity: str,
    ) -> None:
        """Surface a disk-space threshold crossing alert via the watchdog."""
        self._watchdog.report_disk_threshold(
            level=level,
            percent_used=percent_used,
            free_bytes=free_bytes,
            severity=severity,
        )

    def report_heavy_worker_burst(
        self,
        task_name: str,
        crash_count: int,
        window_secs: float,
    ) -> None:
        """Surface a heavy-worker pool burst-crash alert via the watchdog (P0.R8)."""
        self._watchdog.report_heavy_worker_burst(
            task_name=task_name,
            crash_count=crash_count,
            window_secs=window_secs,
        )

    def report_vram_budget_refusal(
        self,
        task_name: str,
        cumulative_mb: int,
        ceiling_mb: int,
        estimate_mb: int,
    ) -> None:
        """Surface a VRAM budget refusal alert via the watchdog (P0.R9 D5)."""
        self._watchdog.report_vram_budget_refusal(
            task_name=task_name,
            cumulative_mb=cumulative_mb,
            ceiling_mb=ceiling_mb,
            estimate_mb=estimate_mb,
        )

    def report_audio_device_burst(
        self,
        channel: str,
        failure_count: int,
        window_secs: float,
    ) -> None:
        """Surface an audio device burst alert via the watchdog (P0.R10 D4)."""
        self._watchdog.report_audio_device_burst(
            channel=channel,
            failure_count=failure_count,
            window_secs=window_secs,
        )

    def get_alerts_summary(self) -> str | None:
        """Return a formatted summary of unresolved watchdog alerts (for state.json)."""
        return self._brain_db.get_recent_alerts_summary()

    async def run(self) -> None:
        print("[BrainAgent] Started — watching conversation_log for new turns")
        self._schedule_startup_tasks()
        watchdog_task = asyncio.create_task(
            self._watchdog.run_loop(self._shutdown)
        )
        while not self._shutdown.is_set():
            # Clear trigger BEFORE poll so any notify() called during poll
            # re-arms the trigger and causes an immediate follow-up poll.
            self._trigger.clear()
            try:
                await self._poll_once()
            except Exception as e:
                print(f"[BrainAgent] Poll error: {e}")

            # Wait for trigger (new turn logged), shutdown, or poll interval.
            shutdown_task = asyncio.create_task(self._shutdown.wait())
            trigger_task  = asyncio.create_task(self._trigger.wait())
            try:
                await asyncio.wait(
                    {shutdown_task, trigger_task},
                    timeout=BRAIN_AGENT_POLL_INTERVAL,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                shutdown_task.cancel()
                trigger_task.cancel()
                await asyncio.gather(shutdown_task, trigger_task, return_exceptions=True)

        print("[BrainAgent] Shutting down...")
        await watchdog_task
        await self.close()

    async def _poll_once(self) -> None:
        last_id = self._brain_db.get_last_turn_id()

        # P0.S7.2 Phase 2 — select audience_ids alongside the turn so
        # _process_turn can route multi-person assistant turns to
        # extract_assistant_room_turn with the room snapshot at turn time.
        rows = self._faces_conn.execute(
            """SELECT cl.id, cl.person_id, cl.role, cl.content, cl.ts, p.name,
                      cl.audience_ids
               FROM   conversation_log cl
               LEFT JOIN persons p ON p.id = cl.person_id
               WHERE  cl.id > ?
               ORDER  BY cl.id ASC
               LIMIT  20""",
            (last_id,),
        ).fetchall()

        if not rows:
            return

        # Build a rolling context window of the turns just before our batch
        recent = self._faces_conn.execute(
            """SELECT role, content FROM conversation_log
               WHERE id <= ? ORDER BY id DESC LIMIT ?""",
            (last_id, BRAIN_AGENT_CONTEXT_TURNS * 2),
        ).fetchall()
        context: list[dict] = [{"role": r[0], "content": r[1]} for r in reversed(recent)]

        for turn_id, person_id, role, content, ts, person_name, audience_ids_json in rows:
            try:
                await self._process_turn(
                    turn_id     = turn_id,
                    person_id   = person_id,
                    person_name = person_name or person_id or "unknown",
                    role        = role,
                    content     = content,
                    context     = context,
                    ts          = ts,
                    audience_ids_json = audience_ids_json,
                )
            except Exception as e:
                import traceback
                print(f"[BrainAgent] Error on turn {turn_id}: {type(e).__name__}: {e}")
                traceback.print_exc()
            finally:
                # Always advance — even if processing failed, don't re-process
                self._brain_db.set_last_turn_id(turn_id)
                context.append({"role": role, "content": content})

    async def _process_turn(
        self,
        turn_id:     int,
        person_id:   str | None,
        person_name: str,
        role:        str,
        content:     str,
        context:     list[dict],
        ts:          float = 0.0,
        audience_ids_json: "str | None" = None,
    ) -> None:
        t0 = time.time()

        # ── Stage 0: Identity-dispute gate ─────────────────────────────────────
        # When the current speaker has contradicted the sensor, we don't know who
        # they actually are. Extracting facts under either name would pollute that
        # person's knowledge with contradictory data. Pause until the dispute
        # resolves (update_person_name gives a clean name or session ends).
        if person_id and person_id in self._disputed_persons:
            self._brain_db.log_agent(turn_id, "triage", "skip", "identity disputed")
            print(f"[BrainAgent] {_now_log_ts()} Triage: SKIP turn {turn_id} — identity disputed for {person_id}")
            return

        # ── Stage 1: Triage ────────────────────────────────────────────────────
        prior_assistant = _get_prior_assistant_turn(context)
        # P0.S7.2 Phase 2 — parse this turn's audience_ids so triage sees the
        # room-participant count. audience_ids JSON is the canonical room
        # snapshot at turn time (P0.S7 Phase 1 _compute_room_audience).
        _room_participant_pids: "list[str]" = []
        if audience_ids_json:
            try:
                _loaded = json.loads(audience_ids_json)
                if isinstance(_loaded, list):
                    _room_participant_pids = [str(p) for p in _loaded if p]
            except (json.JSONDecodeError, TypeError, ValueError):
                _room_participant_pids = []
        _room_count = len(_room_participant_pids)
        ok, reason = self._triage.should_process(
            role, content,
            prior_assistant_turn=prior_assistant,
            room_participant_count=_room_count if _room_count else 1,
        )
        self._brain_db.log_agent(turn_id, "triage", "process" if ok else "skip", reason)
        # Session 116 P1 #6 — triage rationale: surface the signals the
        # decision was based on (word_count, role, person_type) so an
        # outside reviewer can audit "why did we skip?" / "why did we
        # process?" from terminal output alone. Word count is the
        # dominant predictor in TriageAgent.
        _word_count = len((content or "").split())
        _ptype = "?"
        try:
            r = self._faces_conn.execute(
                "SELECT person_type FROM persons WHERE id = ?", (person_id,),
            ).fetchone()
            if r:
                _ptype = r[0] or "?"
        except Exception:
            pass  # OPTIONAL: enriches log rationale only — triage decision already made above
        _rationale = (
            f"role={role}, words={_word_count}, person_type={_ptype}"
        )
        if not ok:
            print(
                f"[BrainAgent] {_now_log_ts()} Triage: SKIP turn {turn_id} "
                f"— {reason} ({_rationale})"
            )
            return
        print(
            f"[BrainAgent] {_now_log_ts()} Triage: PASS turn {turn_id} "
            f"— processing ({_rationale})"
        )

        # ── Stage 1b: Confidence feedback — user confirming/denying AI recall ─
        # Run before extraction so the signal is logged even if extraction finds nothing.
        prior_ai_claim = _get_prior_ai_claim(context)
        if prior_ai_claim:
            reaction = _classify_user_reaction(content)
            if reaction == "confirm" and person_name:
                asyncio.create_task(
                    self._boost_recalled_fact_confidence(person_name, prior_ai_claim)
                )
                self._brain_db.log_agent(
                    turn_id, "feedback", "confirmed_recall", prior_ai_claim[:80]
                )
            elif reaction == "deny":
                self._brain_db.log_agent(
                    turn_id, "feedback", "denied_recall", prior_ai_claim[:80]
                )

        # ── Stage 2: Extract entities + facts ─────────────────────────────────
        t1 = time.time()
        if reason == "multi_person_assistant_turn":
            # P0.S7.2 Phase 2 — κ branch. ONE LLM call + mechanical fan-out.
            # Resolve participant pids → names via persons table.
            _names_by_pid: "dict[str, str]" = {}
            try:
                _placeholders = ",".join("?" * len(_room_participant_pids))
                if _placeholders:
                    _name_rows = self._faces_conn.execute(
                        f"SELECT id, name FROM persons WHERE id IN ({_placeholders})",
                        _room_participant_pids,
                    ).fetchall()
                    _names_by_pid = {pid: nm for pid, nm in _name_rows}
            except Exception as _name_ex:
                # OPTIONAL: name-lookup failure must not block the turn; we fall
                # back to using pids as names so the LLM still gets a participant
                # list (degraded but not dropped).
                print(f"[BrainAgent] room-participant name lookup failed: {_name_ex!r}")
            _names: "list[str]" = []
            _pids: "list[str]" = []
            for _pid in _room_participant_pids:
                _nm = _names_by_pid.get(_pid) or _pid
                _names.append(_nm)
                _pids.append(_pid)
            extractions = await self._extractor.extract_assistant_room_turn(
                assistant_content=content,
                participant_names=_names,
                participant_pids=_pids,
                disputed_pids=self._disputed_persons,
            )
        else:
            extractions = await self._extractor.extract(
                content, person_name, context,
                prior_ai_claim=prior_ai_claim,
                prior_assistant_turn=prior_assistant,
                system_name=self._system_name,
            )
        extract_ms  = (time.time() - t1) * 1000

        if not extractions:
            self._brain_db.log_agent(turn_id, "extraction", "no_facts", None, 0, extract_ms)
            print(f"[BrainAgent] Extraction: no facts found in turn {turn_id} ({extract_ms:.0f}ms)")
            self._advance_session_counter(person_id, person_name)
            return

        self._brain_db.log_agent(
            turn_id, "extraction", "extracted",
            f"{len(extractions)} fact(s)", len(extractions), extract_ms,
        )
        _ext_summary = ", ".join(
            f"{e.entity}.{e.attribute}={e.value[:20]!r}" for e in extractions[:3]
        )
        _ext_more = f" (+{len(extractions)-3} more)" if len(extractions) > 3 else ""
        print(f"[BrainAgent] {_now_log_ts()} Extracted {len(extractions)} fact(s) ({extract_ms:.0f}ms): {_ext_summary}{_ext_more}")

        # ── Stage 3: Contradiction check (parallel per fact) ──────────────────
        conflicts:    list[tuple["Extraction", str]] = []   # (ext, old_val)
        no_conflict:  list["Extraction"]             = []

        # Pre-fetch contradiction counts for conflicting predicates once — reused in
        # both Stage 3 (volatility hint) and Stage 4 (confidence cap) to avoid a
        # double SELECT for each REPLACE fact.
        conflict_counts: dict[str, int] = {}

        # Wave 2 Item 10: pre-fetch all distinct entities in one bulk query
        # instead of calling get_active_knowledge once per extraction fact.
        # O(facts) DB reads → O(1) DB reads per turn.
        _distinct_entities = list({ext.entity for ext in extractions})
        _existing_by_entity = self._brain_db.get_active_knowledge_for_entities(_distinct_entities)

        for ext in extractions:
            stored      = _existing_by_entity.get(ext.entity, [])
            conflicting = [s for s in stored if s["attribute"] == ext.attribute]
            if conflicting:
                conflicts.append((ext, conflicting[0]["value"]))
                if ext.attribute not in conflict_counts:
                    conflict_counts[ext.attribute] = (
                        self._brain_db.get_predicate_contradiction_count(ext.attribute)
                    )
            else:
                no_conflict.append(ext)

        t2 = time.time()
        check_results = await asyncio.gather(*[
            self._contradictor.check(
                ext.entity, ext.attribute, old_val, ext.value,
                conflict_counts[ext.attribute],
            )
            for ext, old_val in conflicts
        ])
        contra_ms = (time.time() - t2) * 1000

        final = list(no_conflict)
        for (ext, old_val), (should_replace, rationale) in zip(conflicts, check_results):
            if should_replace:
                self._brain_db.invalidate(ext.entity, ext.attribute, turn_id)
                try:
                    self._graph_db.invalidate_fact(ext.entity, ext.attribute)
                except Exception as e:
                    self._mark_kuzu_dirty()  # SWALLOW: sentinel for next-boot heal
                    print(f"[BrainAgent] Graph invalidate error: {e}")
                self._brain_db.increment_predicate_contradiction(ext.attribute)
                self._brain_db.log_agent(
                    turn_id, "contradiction",
                    f"replace: {ext.entity}.{ext.attribute} '{old_val}'→'{ext.value}'",
                    rationale, 1, contra_ms,
                )
                final.append(ext)
                # Item 4: A-MEM retroactive scan — re-evaluate related facts for staleness
                asyncio.create_task(
                    self._retroactive_scan(ext.entity, ext.attribute, old_val, ext.value, turn_id)
                )
            else:
                self._brain_db.log_agent(
                    turn_id, "contradiction",
                    f"compatible: {ext.entity}.{ext.attribute}",
                    rationale, 0, contra_ms,
                )

        _n_replace = sum(1 for _, (ok, _) in zip(conflicts, check_results) if ok)
        _n_compat  = len(conflicts) - _n_replace
        if conflicts:
            print(f"[BrainAgent] Contradiction check ({contra_ms:.0f}ms): {_n_replace} replaced, {_n_compat} compatible, {len(no_conflict)} new")

        # ── Stage 4: Store ─────────────────────────────────────────────────────
        if final:
            # Phase 5: cap confidence for volatile predicates before storing.
            # Reuse conflict_counts for REPLACE facts; fetch only for new (no-conflict) facts.
            for ext in final:
                count = conflict_counts.get(
                    ext.attribute,
                    self._brain_db.get_predicate_contradiction_count(ext.attribute),
                )
                if count >= PREDICATE_VOLATILITY_THRESHOLD:
                    ext.confidence = min(ext.confidence, PREDICATE_CONFIDENCE_CAP)

            n = self._brain_db.store_knowledge(final, turn_id, person_id, "extraction_agent")
            self._brain_db.batch_increment_predicate_extraction(
                [ext.attribute for ext in final]
            )
            for ext in final:
                try:
                    self._graph_db.store_fact(ext, turn_id)
                except Exception as e:
                    print(f"[BrainAgent] Graph write error: {e}")
            if person_id:
                asyncio.create_task(self._embed_new_facts(person_id))
            elapsed = (time.time() - t0) * 1000
            summary = ", ".join(
                f"{e.entity}.{e.attribute}={e.value!r}" for e in final
            )
            print(f"[BrainAgent] Turn {turn_id} → {n} fact(s) in {elapsed:.0f}ms: {summary}")

        self._advance_session_counter(person_id, person_name)

        # ── Social mention extraction — all persons ────────────────────────────
        # Run asynchronously so it never blocks the main extraction pipeline.
        # Only user turns are useful (assistant turns don't mention third parties).
        # Runs for best_friend, known, AND strangers — every person who mentions
        # a third party contributes to the cross-person social graph.
        if role == "user" and person_id:
            asyncio.create_task(self._extract_social_mentions(person_id, content))

            # ── Stage 5: Friction detection (Phase 5) ─────────────────────────
            # Only when person has active prefs. Runs async during TTS so n+1
            # turn's get_prompt_addendum() immediately picks up escalated level.
            active_prefs = self._brain_db.get_active_prefs(person_id)
            if active_prefs:
                prev_assistant = next(
                    (t["content"] for t in reversed(context) if t["role"] == "assistant"),
                    None,
                )
                asyncio.create_task(
                    self._detect_and_record_friction(
                        person_id, content, prev_assistant, active_prefs
                    )
                )

            # ── Household extraction — fire-and-forget per user turn ───────────
            context_recent = context[-3:] if context else []
            enrolled_rows = self._faces_conn.execute(
                "SELECT name FROM persons WHERE person_type != 'stranger' ORDER BY name"
            ).fetchall()
            enrolled = [r[0] for r in enrolled_rows]
            asyncio.create_task(self._run_household_per_turn(
                content, person_id, person_name, context_recent, enrolled
            ))

        # Track session start for RoutineAgent + InsightAgent (first turn = arrived)
        if person_id and person_id not in self._session_start_ts:
            self._session_start_ts[person_id] = ts

    async def _detect_and_record_friction(
        self,
        person_id: str,
        user_turn: str,
        prev_assistant_turn: str | None,
        active_prefs: list[dict],
    ) -> None:
        frictions = await self._friction_agent.detect(
            user_turn, prev_assistant_turn, active_prefs
        )
        for f in frictions:
            self._brain_db.increment_pref_friction(person_id, f["pref_type"])
            self._brain_db.log_agent(
                None, "friction",
                f"escalate: {f['pref_type']} (conf={f['confidence']:.2f})",
                user_turn[:80],
            )
            print(
                f"[FrictionAgent] {f['pref_type']} friction detected "
                f"(conf={f['confidence']:.2f}) — escalating pref injection"
            )

    def _collect_known_names_for_phantom_check(
        self,
        speaker_id: str,
        speaker_name: str,
    ) -> "list[str]":
        """Session 114 Part 2 — assemble the list of known names that a
        candidate shadow name should be fuzzy-matched against.

        Sources (in priority order):
          1. Current speaker's display name (catches STT mishears
             where the speaker accidentally referred to themselves).
          2. All enrolled person names from faces.db (catches
             cross-person mishears against any enrolled identity).
          3. Recent shadow_persons names within 24h (catches
             repeated-mishear shadows that would otherwise stack).

        Defensive on each query — a failure in one source still allows
        the others to contribute. Empty list is safe (no fuzzy match
        will fire, normal insert proceeds).
        """
        names: list[str] = []
        if speaker_name:
            names.append(speaker_name)
        try:
            rows = self._faces_conn.execute(
                "SELECT name FROM persons WHERE name IS NOT NULL"
            ).fetchall()
            for r in rows:
                if r[0]:
                    names.append(r[0])
        except Exception as _ex:
            print(f"[HouseholdAgent] phantom-check enrolled-name fetch failed: {_ex!r}")
        try:
            cutoff = time.time() - 86400.0
            names.extend(self._brain_db.get_shadow_person_names_since(cutoff))
        except Exception as _ex:
            print(f"[HouseholdAgent] phantom-check recent-shadows fetch failed: {_ex!r}")
        # Dedupe (case-insensitive) preserving first occurrence.
        seen: set[str] = set()
        out: list[str] = []
        for n in names:
            k = n.strip().lower()
            if k and k not in seen:
                seen.add(k)
                out.append(n)
        return out

    async def _apply_household_extraction(
        self,
        speaker_id: str,
        speaker_name: str,
        result: dict,
    ) -> None:
        """Persist household extraction results to BrainDB.

        Called async from both per-turn and session-end paths.
        """
        if not result:
            return

        # Household facts
        for hf in result.get("household_facts", []):
            entity    = hf.get("entity", "household")
            attribute = hf.get("attribute", "")
            value     = hf.get("value", "")
            scope     = hf.get("scope", "household")
            confidence = float(hf.get("confidence", 0.65))
            if not (entity and attribute and value):
                continue
            disputed = self._brain_db.store_household_fact(
                entity, attribute, value, scope, speaker_id, confidence
            )
            if disputed:
                print(f"[HouseholdAgent] Dispute detected: {entity}/{attribute}")

        # Per-person facts from cross-attribution
        for pf in result.get("per_person_facts", []):
            entity    = pf.get("entity", "")
            attribute = pf.get("attribute", "")
            value     = pf.get("value", "")
            confidence = float(pf.get("confidence", 0.65))
            if not (entity and attribute and value):
                continue
            # Store as per_person scope household fact
            self._brain_db.store_household_fact(
                entity, attribute, value, "per_person", speaker_id, confidence
            )

        # Relationships
        for rel in result.get("relationships", []):
            person_a     = rel.get("person_a", "")
            relationship = rel.get("relationship", "")
            person_b     = rel.get("person_b", "")
            confidence   = float(rel.get("confidence", 0.8))
            if not (person_a and relationship and person_b):
                continue
            self._brain_db.store_relationship(
                person_a, relationship, person_b, confidence, speaker_id
            )
            # Store inverse relationship too
            inverse_map = {
                "married_to": "married_to", "spouse_of": "spouse_of",
                "parent_of": "child_of", "child_of": "parent_of",
                "sibling_of": "sibling_of", "colleague_of": "colleague_of",
                "friend_of": "friend_of",
            }
            if relationship in inverse_map:
                self._brain_db.store_relationship(
                    person_b, inverse_map[relationship], person_a, confidence, speaker_id
                )

        # Shadow persons
        # Session 114 Part 2 — phantom-person prevention via phonetic
        # + Jaro-Winkler match. STT mishears (e.g. "Jagan" → "Jai Gun")
        # would otherwise spawn a shadow node parallel to the real
        # person's enrolled record. Pre-filter against (a) enrolled
        # person names in faces.db, (b) the current speaker's own
        # display name (self-reference via STT noise), (c) recent
        # shadow names within 24h.
        _phantom_known = self._collect_known_names_for_phantom_check(
            speaker_id, speaker_name,
        )
        for sp in result.get("shadow_persons", []):
            name         = sp.get("name", "")
            mentioned_by = sp.get("mentioned_by", speaker_name)
            relationship = sp.get("relationship", "mentioned_by")
            if not name:
                continue
            _matched = _is_phantom_name(name, _phantom_known)
            if _matched:
                print(
                    f"[HouseholdAgent] Shadow name {name!r} matched "
                    f"existing {_matched!r} phonetically — skipping "
                    f"(prevents phantom person)"
                )
                continue
            # Only create shadow nodes for non-enrolled persons
            # (Check won't be perfect here but speaker_id is available)
            _shadow_id, _was_new = self._brain_db.upsert_shadow_person(
                name, speaker_id, relationship
            )
            for fact in sp.get("facts", []):
                self._brain_db.add_shadow_person_fact(
                    name,
                    fact.get("attribute", ""),
                    fact.get("value", ""),
                    float(fact.get("confidence", 0.65)),
                )
            # Session 97 Fix 3: the "Shadow node: X" log fires only on
            # first create. Repeat mentions of the same name — which
            # would previously print an identical line giving the
            # impression of duplicate creates — now surface as a subtler
            # "Shadow mention" line so the information is still visible
            # without looking like new nodes were spawned.
            if _was_new:
                print(f"[HouseholdAgent] Shadow node: {name} (via {mentioned_by}, rel={relationship})")
            else:
                print(f"[HouseholdAgent] Shadow mention: {name} (via {mentioned_by}, rel={relationship})")

    async def _run_household_per_turn(
        self,
        utterance: str,
        speaker_id: str,
        speaker_name: str,
        context_turns: list[dict],
        enrolled_persons: list[str],
    ) -> None:
        """Async fire-and-forget household extraction for a single turn."""
        result = await self._household_agent.extract_per_turn(
            speaker_id, speaker_name, utterance, context_turns, enrolled_persons
        )
        if result:
            await self._apply_household_extraction(speaker_id, speaker_name, result)

    async def _run_household_session_end(
        self,
        person_id: str,
        person_name: str,
        started_at: float,
    ) -> None:
        """Deep household analysis at session close."""
        turns_raw = self._faces_conn.execute(
            """SELECT role, content FROM conversation_log
               WHERE person_id = ? AND ts >= ?
               ORDER BY id ASC""",
            (person_id, started_at),
        ).fetchall()
        turns = [{"role": r[0], "content": r[1]} for r in turns_raw]
        if len(turns) < 4:
            return

        # Get enrolled persons list
        enrolled_rows = self._faces_conn.execute(
            "SELECT name FROM persons WHERE person_type != 'stranger' ORDER BY name"
        ).fetchall()
        enrolled = [r[0] for r in enrolled_rows]

        result = await self._household_agent.extract_session_end(
            person_id, person_name, turns, enrolled
        )
        if result:
            await self._apply_household_extraction(person_id, person_name, result)
            print(f"[HouseholdAgent] Session-end extraction complete for {person_name}")

    def _is_best_friend(self, person_id: str) -> bool:
        row = self._faces_conn.execute(
            "SELECT 1 FROM persons WHERE id=? AND person_type='best_friend' LIMIT 1",
            (person_id,),
        ).fetchone()
        return row is not None

    async def _extract_social_mentions(self, source_person_id: str, text: str) -> None:
        mentions = await self._social_graph.extract(text)
        for m in mentions:
            name = (m.get("name") or "").strip()
            if not name:
                continue
            attrs = [a for a in (m.get("attributes") or []) if isinstance(a, str) and a.strip()]
            self._brain_db.upsert_social_mention(
                source_person_id=source_person_id,
                mentioned_name=name,
                relationship=m.get("relationship"),
                new_attributes=attrs,
            )
            print(f"[SocialGraph] Mention stored: {name} ({m.get('relationship', '?')}) — {attrs}")

    def score_stranger_identity(self, conversation: list[dict]) -> dict | None:
        """Score a stranger's conversation against all known social mentions.

        Synchronous — reads only pre-stored data from brain.db, no API calls.
        Called by pipeline after every stranger turn.

        Returns best match dict or None:
          {name, relationship, confidence, matched_attrs, source_person_id}
        """
        mentions = self._brain_db.get_all_social_mentions()
        return self._identity_agent.score(conversation, mentions)

    async def get_briefing(self, bf_person_id: str, since_ts: float) -> str | None:
        """Generate a spoken briefing for the best friend after a long absence.

        Queries stranger visits and silent observations from faces.db since
        since_ts (the best friend's last_seen timestamp), scores them for
        relevance, and generates a warm natural 1–2 sentence summary.

        Called from pipeline concurrently with the greeting TTS so the LLM
        call completes during the greeting with zero added latency.
        """
        try:
            row = self._faces_conn.execute(
                "SELECT name FROM persons WHERE id = ?", (bf_person_id,)
            ).fetchone()
            if not row:
                return None
            bf_name = row[0]

            # Bug N (2026-04-20 live run): strangers with turn_count=0 (gate-blocked,
            # phantom sessions from short-utterance misfires) must not surface in the
            # briefing — the downstream template phrasing "visited and spoke with me"
            # asserts a real exchange. Joining on the user-role rows in
            # conversation_log and filtering by BRIEFING_VISITOR_MIN_TURNS is the
            # authoritative guard.
            sv_rows = self._faces_conn.execute(
                """SELECT p.id, p.name, p.last_seen, p.enrolled_at,
                          (SELECT COUNT(*) FROM conversation_log cl
                           WHERE cl.person_id = p.id AND cl.role = 'user') AS user_turns
                     FROM persons p
                    WHERE p.person_type = 'stranger' AND p.last_seen > ?
                    ORDER BY p.last_seen DESC""",
                (since_ts,),
            ).fetchall()
            stranger_visits = [
                {"id": r[0], "name": r[1], "last_seen": r[2], "first_seen": r[3]}
                for r in sv_rows
                if (r[4] or 0) >= BRIEFING_VISITOR_MIN_TURNS
            ]

            obs_rows = self._faces_conn.execute(
                """SELECT id, first_seen, last_seen, duration_secs, frame_count,
                          photo_path, zone, matched_person_id
                   FROM silent_observations WHERE last_seen > ?
                   ORDER BY last_seen DESC""",
                (since_ts,),
            ).fetchall()
            silent_obs = [
                {
                    "id": r[0], "first_seen": r[1], "last_seen": r[2],
                    "duration_secs": r[3], "frame_count": r[4],
                    "photo_path": r[5], "zone": r[6], "matched_person_id": r[7],
                }
                for r in obs_rows
            ]

            mentions = self._brain_db.get_all_social_mentions()
            return await self._briefing_agent.generate(
                bf_name, stranger_visits, silent_obs, mentions
            )
        except Exception as e:
            print(f"[BriefingAgent] get_briefing error: {e}")
            return None

    def get_context(
        self,
        person_name: str,
        query_embedding: list[float] | None = None,
        requester_person_id: str | None = None,
        best_friend_id: str | None = None,
    ) -> str | None:
        """Return formatted knowledge about a person for LLM injection.

        When query_embedding is provided, uses cosine similarity to rank facts
        by relevance to the current user utterance (semantic retrieval). Falls
        back to graph context, then SQLite recency order when no embeddings exist.
        Synchronous — all reads are in-process (<1ms).
        Always appends household context (shared facts + relationships) when available.

        Session 106 Phase 3A.5 — privacy filtering now goes through
        ``query_knowledge_for`` (single source of truth via
        ``_visibility_clause``) instead of the legacy two-step
        ``get_active_knowledge`` + ``filter_facts_for_requester``. Same
        visibility semantics — 4-tier owner-access model — but the
        filter runs in SQL rather than Python so future retrieval sites
        can't accidentally skip it.

        The semantic-search branch (``query_embedding`` provided) still
        uses ``semantic_search_knowledge`` for cosine ranking and then
        filters the returned list in Python via
        ``filter_facts_for_requester`` — that method is kept for the
        semantic-rank path because the privacy clause doesn't affect
        embedding-similarity ranking. Migrating the cosine search to
        push the visibility predicate into SQL is 3A.6 scope.
        """
        household_ctx = self._brain_db.get_household_context()

        # Resolve subject person_id for the privacy filter (used by the
        # semantic-search branch's in-Python filter; the recency-fallback
        # branch composes visibility in SQL via query_knowledge_for).
        subject_person_id: str | None = None
        _fc = getattr(self, "_faces_conn", None)
        if _fc:
            row = _fc.execute(
                "SELECT id FROM persons WHERE LOWER(name) = LOWER(?) LIMIT 1",
                (person_name,),
            ).fetchone()
            subject_person_id = row[0] if row else None

        # Determine whether privacy filtering is active for this request
        _filtering = bool(
            requester_person_id
            and requester_person_id != best_friend_id
            and requester_person_id != subject_person_id
        )

        if query_embedding:
            # Session 107 Phase 3A.6 — visibility now composed into
            # semantic_search_knowledge's SELECT WHERE clause via
            # requester_pid/best_friend_id kwargs. filter_facts_for_requester
            # deleted. Same semantics as the recency-fallback branch
            # below: SQL is the single source of truth for "who can see
            # what." Backward compat: when requester_person_id is None
            # (internal synthesis paths), no filter is applied.
            facts = self._brain_db.semantic_search_knowledge(
                person_name, query_embedding,
                requester_pid=requester_person_id,
                best_friend_id=best_friend_id,
            )
            if facts:
                ctx = _format_context_lines(person_name, facts)
                if household_ctx:
                    ctx = (ctx + "\n\n" + household_ctx) if ctx else household_ctx
                return ctx

        # Graph path: P0.S7.D-B added `privacy_level` to Kuzu RELATES_TO
        # edges, so the graph can now filter at Cypher level. We thread
        # caller_pid + best_friend_id through; get_graph_context applies
        # the SQL `_visibility_clause`-equivalent semantic.
        # The existing `if not _filtering:` defensive skip is PRESERVED
        # as belt-and-braces (Plan v2 §3.4) — it remains correct even
        # though the Cypher filter now also enforces the same property.
        # Future cleanup PR may remove the skip once v3 is canary-validated.
        if not _filtering:
            ctx = self._graph_db.get_graph_context(
                person_name,
                caller_pid=requester_person_id,
                best_friend_id=best_friend_id,
            )
        else:
            ctx = None

        if not ctx:
            # Session 106 Phase 3A.5 canary-replicated site: recency
            # fallback retrieval now uses SQL-level visibility filter
            # via query_knowledge_for. When no requester_person_id is
            # supplied (internal callers), the query returns unfiltered
            # entity rows via the same helper — we use requester_pid =
            # subject as a sensible default so the owner-check branch
            # in _visibility_clause returns everything non-system.
            _eff_requester = requester_person_id or subject_person_id or (best_friend_id or "")
            if _eff_requester:
                facts = self._brain_db.query_knowledge_for(
                    requester_pid=_eff_requester,
                    best_friend_id=best_friend_id,
                    entity=person_name,
                )
            else:
                # No identity context anywhere — keep the legacy
                # unfiltered path (dream loop / internal synthesis).
                facts = self._brain_db.get_active_knowledge(person_name)
            ctx = _format_context_lines(person_name, facts) if facts else None

        if household_ctx:
            ctx = (ctx + "\n\n" + household_ctx) if ctx else household_ctx
        return ctx

    async def embed_query(self, text: str) -> list[float] | None:
        """Embed the current user utterance for semantic retrieval.

        Returns None when no API key is configured — callers fall back to
        graph/recency context automatically.
        """
        return await self._embed_agent.embed(text, purpose="user query")

    def record_object_sightings(
        self,
        detections:     list[dict],
        frame_w:        int,
        frame_h:        int,
        person_context: str | None = None,
    ) -> None:
        """Record YOLO object detections into persistent spatial memory.

        Called from the pipeline's main loop every VISION_DETECT_EVERY frames.
        Synchronous — no await needed; BrainDB writes are fast SQLite commits.
        Periodically fires pattern analysis as a background async task.
        """
        self._spatial_memory.record(detections, frame_w, frame_h, person_context)
        # Fire pattern analysis every 50 new sightings (avoids constant runs)
        n = self._spatial_memory._new_count
        if n > 0 and n % 50 == 0:
            asyncio.create_task(self._pattern_agent.maybe_run(n))

    def get_object_context(self, query: str) -> str | None:
        """Return spatial memory relevant to the current query for LLM injection.

        Extracts content words from the query and searches object_sightings.
        Falls back to recently seen objects when no keywords match.
        Synchronous — pure SQLite read (<1ms).
        """
        words    = [w.strip("?.,!").lower() for w in query.split()]
        keywords = [w for w in words if len(w) > 3 and w not in _VISION_STOPWORDS]
        if keywords:
            ctx = self._spatial_memory.get_context(keywords)
            if ctx:
                return ctx
        # Fall back to recent general scene context
        return self._spatial_memory.get_recent_context(5)

    def get_pending_question(self) -> dict | None:
        """Return the next unasked pattern question for proactive injection.

        Returns a dict with keys 'id', 'text', 'pattern_key', or None.
        Synchronous SQLite read (<1ms). Called every turn in conversation_turn().
        """
        return self._brain_db.get_next_pending_question()

    def mark_question_asked(self, qid: int) -> None:
        """Mark a question as served so it is not injected again.

        Called immediately after injecting the question into prompt_addendum,
        before the LLM responds — the injection is the commitment to ask.
        """
        self._brain_db.mark_question_asked(qid)

    def store_temporal_fact(
        self,
        person_id: str,
        person_name: str,
        attribute: str,
        value: str,
        valid_for_hours: float = 4.0,
    ) -> None:
        """Store a short-lived fact directly (bypassing extraction pipeline).

        Invalidates any existing active fact for the same (entity, attribute)
        before inserting — ensures at most one active value per attribute.

        Used by pipeline for sensor-derived facts (e.g. emotion agent)
        that don't need LLM extraction — they already have a structured value.
        """
        turn_id = self._brain_db.get_last_turn_id()
        # Replace previous value so the attribute stays deduplicated
        self._brain_db.invalidate(person_name, attribute, turn_id)
        # Session 95 3A.4.5: sync path. All sensor-derived temporal facts
        # (emotion agent's current_feeling, mood changes) are 'personal' —
        # they describe the speaker's internal state, owner-only by design.
        ext = Extraction(
            entity=person_name,
            entity_type="person",
            attribute=attribute,
            value=value,
            confidence=0.80,
            is_temporal=True,
            valid_for_hours=valid_for_hours,
            privacy_level="personal",
        )
        self._brain_db.store_knowledge([ext], turn_id, person_id, agent="emotion_agent")

    async def _embed_new_facts(self, person_id: str) -> None:
        """Embed unembedded knowledge rows for a person and persist the vectors.

        Fire-and-forget task — called after store_knowledge() so the pipeline
        never waits for it. Embeds up to 20 rows per call to keep latency low.
        """
        rows = self._brain_db.get_unembedded_knowledge(person_id)
        if not rows:
            return
        texts = [
            f"{r['entity']} {r['attribute'].replace('_', ' ')}: {r['value']}"
            for r in rows
        ]
        embeddings = await self._embed_agent.embed_batch(texts, purpose="knowledge fact")
        for row, emb in zip(rows, embeddings):
            if emb:
                self._brain_db.store_knowledge_embedding(row["id"], emb)

    async def _backfill_embeddings(self, batch_size: int = 50) -> None:
        """Item 5: Startup background job — embed all NULL-embedding knowledge rows.

        Processes rows from before EmbeddingAgent was introduced (Phase 3). Runs
        oldest-first, 50 rows per batch with 2s sleep for rate limiting. Exits
        immediately when all rows are embedded. Idempotent: safe to re-run.
        """
        total = 0
        while not self._shutdown.is_set():
            rows = self._brain_db.get_all_unembedded_knowledge(limit=batch_size)
            if not rows:
                if total > 0:
                    print(f"[BrainAgent] Embedding backfill complete — {total} rows embedded")
                return
            texts = [
                f"{r['entity']} {r['attribute'].replace('_', ' ')}: {r['value']}"
                for r in rows
            ]
            embeddings = await self._embed_agent.embed_batch(texts, purpose="knowledge fact")
            n_this = sum(1 for emb in embeddings if emb)
            for row, emb in zip(rows, embeddings):
                if emb:
                    self._brain_db.store_knowledge_embedding(row["id"], emb)
            total += n_this
            print(f"[BrainAgent] Backfill: {n_this}/{len(rows)} embedded ({total} total)")
            if n_this == 0:
                # API unavailable — stop trying; will retry on next restart
                print("[BrainAgent] Backfill: no embeddings returned (API unavailable?), aborting")
                return
            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass

    async def _retroactive_scan(
        self,
        entity: str,
        changed_attr: str,
        old_value: str,
        new_value: str,
        turn_id: int,
    ) -> None:
        """Item 4: A-MEM retroactive memory evolution.

        After a ContradictionAgent REPLACE, walk the entity's active facts and
        re-evaluate each for staleness relative to the change. Caps LLM calls at
        MAX_RETROACTIVE_FACTS to bound cost. Runs as a background task — never
        blocks the conversation.

        Safeguards:
        - Only checks facts with confidence >= EMBED_MIN_CONFIDENCE (already uncertain = skip)
        - No cascading: calls BrainDB.invalidate() directly, not _process_turn()
        - No cross-entity scan in v1 (only same-entity facts checked)
        """
        related = [
            f for f in self._brain_db.get_active_knowledge(entity)
            if f["attribute"] != changed_attr
            and f["confidence"] >= EMBED_MIN_CONFIDENCE
        ]
        if not related:
            return
        related = related[:MAX_RETROACTIVE_FACTS]

        results = await asyncio.gather(*[
            self._contradictor.check_staleness(
                entity, f["attribute"], f["value"],
                changed_attr, old_value, new_value,
            )
            for f in related
        ], return_exceptions=True)

        for f, result in zip(related, results):
            if isinstance(result, Exception):
                continue
            verdict, rationale = result
            if verdict == "INVALIDATED":
                self._brain_db.invalidate(entity, f["attribute"], turn_id)
                try:
                    self._graph_db.invalidate_fact(entity, f["attribute"])
                except Exception:
                    self._mark_kuzu_dirty()  # SWALLOW: brain.db is authoritative, sentinel for next-boot heal
                self._brain_db.log_agent(
                    turn_id, "retro_scan",
                    f"invalidated: {entity}.{f['attribute']}",
                    rationale,
                )
                print(f"[RetroScan] Invalidated {entity}.{f['attribute']} — {rationale}")
            elif verdict == "STALE":
                kid = self._brain_db.find_knowledge_id(entity, f["attribute"], f["value"])
                if kid is not None:
                    self._brain_db.update_confidence(kid, -RETRO_STALE_PENALTY)
                    self._brain_db.log_agent(
                        turn_id, "retro_scan",
                        f"stale: {entity}.{f['attribute']} (-{RETRO_STALE_PENALTY:.2f})",
                        rationale,
                    )
                    print(
                        f"[RetroScan] Stale: {entity}.{f['attribute']}"
                        f" (-{RETRO_STALE_PENALTY:.2f}) — {rationale}"
                    )

    async def _boost_recalled_fact_confidence(
        self, person_name: str, prior_ai_text: str
    ) -> None:
        """Boost the confidence of a stored fact the user just confirmed (SM-2 reset).

        Item 6: calls update_confirmation() which boosts stored confidence AND
        resets last_confirmed_at to now — resetting the decay clock.
        """
        emb = await self._embed_agent.embed(prior_ai_text[:200], purpose="user query")
        if not emb:
            return
        results = self._brain_db.semantic_search_knowledge(person_name, emb, top_k=1)
        if not results:
            return
        top = results[0]
        kid = self._brain_db.find_knowledge_id(person_name, top["attribute"], top["value"])
        if kid is not None:
            self._brain_db.update_confirmation(kid)
            print(
                f"[BrainAgent] Confirmation reset decay: {person_name}.{top['attribute']}"
                f" (+{CONFIDENCE_BOOST:.2f}, last_confirmed_at=now)"
            )

    def _advance_session_counter(
        self, person_id: str | None, person_name: str
    ) -> None:
        """Increment per-person turn counter; fire intra-session pref at INTRA_PREF_TURN."""
        if not person_id:
            return
        count = self._session_turn_counts.get(person_id, 0) + 1
        self._session_turn_counts[person_id] = count
        if count == INTRA_PREF_TURN and person_id not in self._intra_pref_done:
            self._intra_pref_done.add(person_id)
            asyncio.create_task(
                self._run_pref_analysis(
                    person_id,
                    turns_limit=INTRA_PREF_TURNS_LIMIT,
                    min_confidence=0.85,
                    source_override="human",
                )
            )
            print(f"[PromptPrefAgent] Intra-session lightweight pass fired for {person_name}")

    def get_prompt_addendum(self, person_id: str) -> str | None:
        """Return active communication prefs + proactive nudges for LLM injection.

        Synchronous SQLite reads (<2ms total). Returns None when nothing pending.
        Called every turn in conversation_turn() — same pattern as get_context().

        P0.S7.5 D1 — nudge consumption gates on `ONE_SHOT_NUDGE_TYPES`
        membership. One-shot proactive types (CROSS_PERSON_HYPOTHESIS,
        INTENTION_FOLLOWUP, MEMORY_PROMPT) get mark_nudge_injected on
        first delivery (legacy behavior). Persistent context types
        (VISITOR_ALERT) stay pending until naturally expired or
        dismissed — owner needs the visitor context whenever they
        ask, not just on the first re-engagement turn.

        Canary 2026-05-19 root cause: VISITOR_ALERT was being consumed
        on the first turn of Jagan's re-engagement; the next turn's
        addendum had nudge=no, the VISITOR CONTEXT block went dormant,
        and brain fabricated "No one was here, I was just waiting."
        """
        parts: list[str] = []
        pref_text = self._brain_db.get_prompt_addendum(person_id)
        if pref_text:
            parts.append(pref_text)
        nudges = self._brain_db.get_pending_nudges(person_id, limit=1)
        if nudges:
            nudge = nudges[0]
            parts.append(
                f"[Proactive — work naturally into conversation if the moment fits: "
                f"{nudge['content']}]"
            )
            # D1: only mark one-shot types as injected. Persistent
            # context types (VISITOR_ALERT) re-inject every turn.
            from core.config import ONE_SHOT_NUDGE_TYPES
            _nudge_type = nudge.get("nudge_type") or ""
            if _nudge_type in ONE_SHOT_NUDGE_TYPES:
                self._brain_db.mark_nudge_injected(nudge["id"])
            else:
                # LOW 2 (Plan v2 §3.2) — re-injection observability for
                # re-canary cost validation. Counts log lines per
                # session: bounded (~1-3 turns) = healthy; excessive
                # (~20+ turns) = signal to file follow-up for
                # auto-dismiss heuristic.
                print(
                    f"[PromptPrefAgent] persistent nudge re-injected "
                    f"(type={_nudge_type}, id={nudge['id']})"
                )
        if parts:
            print(f"[PromptPrefAgent] {len(parts)} addendum part(s) injected for {person_id} (prefs={'yes' if pref_text else 'no'}, nudge={'yes' if nudges else 'no'})")
        return "\n\n".join(parts) if parts else None

    async def _run_pref_analysis(
        self,
        person_id: str,
        turns_limit: int = PREF_ANALYSIS_TURNS,
        min_confidence: float = 0.7,
        source_override: str | None = None,
    ) -> None:
        """Analyze recent turns for communication preferences.

        Called at session end (full 40-turn pass, confidence >= 0.7) and optionally
        at INTRA_PREF_TURN mid-session (6-turn pass, confidence >= 0.85, source='human'
        so results activate immediately without the 3-session threshold).
        """
        try:
            row = self._faces_conn.execute(
                "SELECT name FROM persons WHERE id = ?", (person_id,)
            ).fetchone()
            if not row:
                return
            person_name = row[0]

            turns = self._faces_conn.execute(
                """SELECT role, content FROM conversation_log
                   WHERE person_id = ? ORDER BY id DESC LIMIT ?""",
                (person_id, turns_limit),
            ).fetchall()
            if not turns:
                return
            session_turns = [{"role": r[0], "content": r[1]} for r in reversed(turns)]

            existing   = self._brain_db.get_active_prefs(person_id)
            t0         = time.time()
            prefs      = await self._pref_agent.analyze(person_name, existing, session_turns)
            elapsed_ms = (time.time() - t0) * 1000

            # Filter by min_confidence (PromptPrefAgent already enforces 0.7; this allows
            # the intra-session pass to raise the bar to 0.85 for explicit-only signals)
            if min_confidence > 0.7:
                prefs = [p for p in prefs if p.get("confidence", 1.0) >= min_confidence]

            if not prefs:
                print(f"[PromptPrefAgent] {person_name}: no new preferences ({elapsed_ms:.0f}ms)")
                return

            for p in prefs:
                source = source_override or "prompt_agent"
                content = p["content"]
                ptype   = p["pref_type"]

                # Bug L Part 2 (Session 69): blacklist mistake-recovery patterns.
                # PromptPrefAgent was inferring "avoid apologizing" from the LLM's
                # own apology in a Bug-N confabulation recovery — that's training
                # on noise. Reject these shapes at the activation gate.
                import re as _re_l
                if any(_re_l.search(bl, content, _re_l.IGNORECASE) for bl in PREF_BLACKLIST_PATTERNS):
                    print(
                        f"[PromptPrefAgent] {person_name}: blacklisted pref rejected "
                        f"[{ptype}] {content}"
                    )
                    continue

                # Bug L Part 1 (Session 69): semantic dedup. If the new pref is
                # near-identical to one already recorded for this person+type,
                # bump the existing row's sessions_seen instead of inserting a
                # near-duplicate. The 2026-04-20 run produced 4 separate
                # "Prefers brief responses" rows with minor wording variations.
                import numpy as _np_l
                new_emb = await self._embed_agent.embed(content, purpose="user preference")
                dedup_handled = False
                if new_emb is not None:
                    new_vec = _np_l.asarray(new_emb, dtype=_np_l.float32)
                    existing_for_type = self._brain_db.get_prefs_by_type(person_id, ptype)
                    for existing in existing_for_type:
                        old_bytes = existing.get("embedding")
                        if old_bytes is None:
                            # Pre-migration row — embed now and backfill.
                            old_emb_list = await self._embed_agent.embed(
                                existing["content"], purpose="user preference"
                            )
                            if old_emb_list is None:
                                continue
                            old_vec = _np_l.asarray(old_emb_list, dtype=_np_l.float32)
                            self._brain_db.set_pref_embedding(existing["id"], old_vec.tobytes())
                        else:
                            old_vec = _np_l.frombuffer(old_bytes, dtype=_np_l.float32)
                        # E5 vectors are L2-normalized → dot product is cosine.
                        sim = float(_np_l.dot(new_vec, old_vec))
                        if sim >= PREF_DEDUP_THRESHOLD:
                            self._brain_db.bump_pref_seen(existing["id"])
                            print(
                                f"[PromptPrefAgent] {person_name}: strengthened "
                                f"(sim={sim:.2f}) [{ptype}] {existing['content']}"
                            )
                            dedup_handled = True
                            break
                if dedup_handled:
                    continue

                # No semantic match — fall through to the exact-string dedup +
                # insert path. Backfill the embedding on fresh rows so the next
                # activation can semantic-compare without re-embedding history.
                is_new = self._brain_db.store_pref(
                    person_id, ptype, content, source=source
                )
                if is_new and new_emb is not None:
                    _pref_id = self._brain_db.get_latest_pref_id(
                        person_id, ptype, content
                    )
                    if _pref_id is not None:
                        self._brain_db.set_pref_embedding(
                            _pref_id,
                            _np_l.asarray(new_emb, dtype=_np_l.float32).tobytes(),
                        )
                status = "activated (new)" if is_new else "seen again (+1 session)"
                print(
                    f"[PromptPrefAgent] {person_name}: {status} [{source}]"
                    f" — [{ptype}] {content}"
                )

        except Exception as e:
            print(f"[PromptPrefAgent] Error for {person_id}: {e}")
            import traceback
            traceback.print_exc()

    async def dream(self) -> None:
        """Pattern 4: autoDream — decay + hard-cap table pruning.

        Applies decay writes to all non-invalidated facts:
        - Below DREAM_PRUNE_FLOOR: soft-deleted (no longer appears in context).
        - Otherwise: stored confidence updated to current effective (decayed) value.
        Also prunes tables that grow unboundedly (presence_log, episodes,
        social_mentions, expired nudges, old resolved alerts).
        Runs schema normalization afterward to tidy attribute synonyms.
        Fully decoupled from the conversation — never blocks a turn.
        """
        all_persons = self._faces_conn.execute("SELECT id FROM persons").fetchall()
        print(f"[Dream] Consolidation started — {len(all_persons)} person(s) in DB")
        pruned, decayed, stable = self._brain_db.decay_and_prune(
            DREAM_PRUNE_FLOOR, DREAM_DECAY_WRITE_THRESHOLD
        )
        k_cap   = self._brain_db.prune_knowledge_hard_cap(KNOWLEDGE_MAX_ROWS)
        p_cap   = self._brain_db.prune_presence_log(PRESENCE_MAX_ROWS)
        ep_cap  = self._brain_db.prune_episodes(EPISODE_MAX_ROWS)
        sm_cap  = self._brain_db.prune_social_mentions(SOCIAL_MENTIONS_MAX_ROWS)
        n_exp   = self._brain_db.prune_expired_nudges()
        wa_old  = self._brain_db.prune_old_resolved_alerts(WATCHDOG_MAX_AGE_DAYS)
        al_old  = self._brain_db.prune_agent_log(AGENT_LOG_MAX_AGE_DAYS, AGENT_LOG_MAX_ROWS)
        prf_exp = self._brain_db.prune_expired_prefs()
        pq_old  = self._brain_db.prune_old_pattern_questions(PATTERN_Q_MAX_AGE_DAYS)
        removed = self._brain_db.prune_shadow_persons(max_age_days=90)
        await self._schema_norm.maybe_run()
        table_removed = k_cap + p_cap + ep_cap + sm_cap + n_exp + wa_old + al_old + prf_exp + pq_old + removed
        print(
            f"[Dream] Consolidated — {pruned} pruned, {decayed} decayed, {stable} stable"
            + (f" | tables: {table_removed} rows removed" if table_removed else "")
        )

    def wipe(self) -> None:
        """Wipe all brain data — SQLite knowledge + graph entities."""
        self._brain_db.wipe()
        self._graph_db.wipe()

    def close_connections(self) -> None:
        """Close all database file handles.

        Called before wipe_all() during factory reset so that Windows can
        delete the underlying files (open handles block deletion on Windows).
        Call wipe() first (while connections are still valid), then this,
        then wipe_all(), then reopen_connections().
        """
        try:
            self._brain_db.close()
        except Exception:
            pass  # CLEANUP: best-effort close before factory-reset file deletion
        try:
            self._faces_conn.close()
        except Exception:
            pass  # CLEANUP: best-effort close before factory-reset file deletion
        try:
            self._graph_db.close()
        except Exception:
            pass  # CLEANUP: best-effort close before factory-reset file deletion

    def reopen_connections(self) -> None:
        """Re-open all database connections after wipe_all() has deleted the files.

        Creates fresh connections to the newly created empty DB files and
        rebuilds all agent references that hold direct DB handles.

        Calls wipe() on the newly opened brain.db to guarantee clean state.
        On Windows, wipe_all() can fail to delete brain.db if the file is still
        locked by in-flight background tasks.  This second wipe() is the safety
        net that ensures any rows written after the first wipe() are also cleared.
        """
        self._brain_db   = BrainDB(self._brain_db_path)
        self._brain_db.wipe()          # safety net: clear any rows written during the race window
        self._graph_db   = GraphDB(self._graph_db_path)
        self._faces_conn = sqlite3.connect(
            self._faces_db_path, check_same_thread=False,
            isolation_level="IMMEDIATE",  # P0.9.1 Imp-1
        )
        # Patch all agents that hold direct DB references
        self._schema_norm    = SchemaNormAgent(self._brain_db, self._embed_agent)
        self._spatial_memory = SpatialMemoryAgent(self._brain_db)
        self._pattern_agent  = ObjectPatternAgent(self._brain_db, self._http)
        self._routine_agent  = RoutineAgent(self._brain_db)
        self._nudge_agent    = ProactiveNudgeAgent(self._brain_db, self._graph_db)
        self._watchdog       = WatchdogAgent(self._brain_db, self._faces_conn)
        self._ensure_graph_sync()

    def prune_brain_data(self, person_ids: list) -> int:
        """Delete all brain.db rows for the given person_ids.

        Called from pipeline._dream_loop() after faces.db stranger pruning to ensure
        no orphaned knowledge, nudges, or log rows remain for deleted stranger sessions.
        """
        return self._brain_db.delete_person_data(person_ids)

    async def close(self) -> None:
        await self._http.aclose()
        self._faces_conn.close()
        self._brain_db.close()
        self._graph_db.close()
