"""core/brain_agent/privacy.py — privacy-tier classification + visibility policy.

Extracted VERBATIM from core/brain_agent.py (P1.A1 SP-2 Commit 2). Behavior-
neutral; core/brain_agent/__init__.py re-exports these symbols so all importers
are unchanged. _privacy_classifier_cache stays MUTATE-ONLY (subscript writes;
never rebind) so the re-exported name shares one dict with this module.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import re

from core.brain_agent._llm import _call_llm_chat, _parse_json
from core.config import (
    SAFETY_CRITICAL_ATTRIBUTE_PATTERNS,
    PRIVACY_LEVELS,
    PRIVACY_LEVEL_DEFAULT,
    PRIVACY_LEVEL_STATIC_MAP,
    PRIVACY_CLASSIFIER_TIMEOUT_SECS,
    PRIVACY_CLASSIFIER_MAX_TOKENS,
)


_SAFETY_CRITICAL_ATTR_RES: tuple = tuple(
    re.compile(p) for p in SAFETY_CRITICAL_ATTRIBUTE_PATTERNS
)


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
