# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""SB.3 — the agent registry (PURE DATA; D4).

One entry per brain-agent: the agent-name → {class-name STRING, dep-source tags,
hook list}. The orchestrator resolves the class-name string → the class object
(it already imports all 15) and the dep tags → the live sources, so this module
imports NOTHING from ``core/`` — ``profiles/`` stays pure data, no
``profiles/ → core/`` coupling (the layering SB.2.1 locked via the loader's
no-``core.config`` rule). T7 enforces the no-import structurally.

- ``class``  — STRING; resolved by ``orchestrator._CLASS_BY_NAME``.
- ``deps``   — STRING dep-source tags (D4). ``"embed"`` is the one inter-agent
  dep (schema needs the embedding agent) → drives the topo-order (embed→schema).
- ``hooks``  — a LIST (D2): HouseholdExtractionAgent fires at 3 hooks day-one.
  Descriptive — they tell the dep-closure + completeness tests where to look;
  the actual gating is per-call-site (orchestrator §5), not hook-dispatched.

The deps were grep-verified 1:1 against the live constructor args at
``orchestrator.py:228-242`` (the SB.3 Plan v1 §0.1 enumeration).
"""

from __future__ import annotations

# Dep-source tags. The first four are external sources the orchestrator holds
# (self._http / self._brain_db / self._graph_db / self._faces_conn); "embed" is
# the inter-agent dep (the EmbeddingAgent instance) — it makes schema topo-after
# embed, and a profile registering schema without embed fails the dep-closure
# validation (SB.3 §6).
DEP_SOURCES = ("http", "brain_db", "graph_db", "faces_conn", "embed")

AGENT_REGISTRY = {
    "triage":        {"class": "TriageAgent",              "deps": [],                         "hooks": ["per_turn"]},
    "extraction":    {"class": "ExtractionAgent",          "deps": ["http"],                   "hooks": ["per_turn"]},
    "contradiction": {"class": "ContradictionAgent",       "deps": ["http"],                   "hooks": ["per_turn", "retroscan"]},
    "schema":        {"class": "SchemaNormAgent",          "deps": ["brain_db", "embed"],      "hooks": ["boot", "dream"]},
    "embed":         {"class": "EmbeddingAgent",           "deps": ["http"],                   "hooks": ["service"]},
    "social":        {"class": "SocialGraphAgent",         "deps": ["http"],                   "hooks": ["per_turn"]},
    "friction":      {"class": "FrictionDetectionAgent",   "deps": ["http"],                   "hooks": ["per_turn"]},
    "household":     {"class": "HouseholdExtractionAgent", "deps": ["http"],                   "hooks": ["config", "per_turn", "session_end"]},
    "prefs":         {"class": "PromptPrefAgent",          "deps": ["http"],                   "hooks": ["session_end"]},
    "insight":       {"class": "ConversationInsightAgent", "deps": ["http"],                   "hooks": ["session_end"]},
    "routine":       {"class": "RoutineAgent",             "deps": ["brain_db"],               "hooks": ["session_end"]},
    "nudge":         {"class": "ProactiveNudgeAgent",      "deps": ["brain_db", "graph_db"],   "hooks": ["session_end"]},
    "briefing":      {"class": "BriefingAgent",            "deps": ["http"],                   "hooks": ["on_demand"]},
    "identity":      {"class": "IdentityAgent",            "deps": [],                         "hooks": ["on_demand"]},
    "watchdog":      {"class": "WatchdogAgent",            "deps": ["brain_db", "faces_conn"], "hooks": ["event"]},
}

# Bundle shorthand (D3): `agents: companion` → the full 15. Mirrors SB.2.1's
# `provider: cloud` → leaf-expansion. SB.2.2+/clones add their own bundles.
AGENT_BUNDLES = {"companion": tuple(AGENT_REGISTRY)}
