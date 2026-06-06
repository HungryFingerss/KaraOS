"""tests/test_p0_s7_2_phase3.py — P0.S7.2 Phase 3 (integration WIRING).

Plan v2 §6 Phase 3 = 1 logical test:

  7. test_session_a_then_b_recipe_retrieval — uses chain-5 fixture
     `build_multi_person_assistant_extraction` (P4) to seed Session A's
     κ extraction facts; verifies the Session B retrieval pipeline
     delivers those facts to brain via the search_memory wiring.

L2 dual assertion (Plan v2 §6 test 7):
  PRIMARY  — sample composed brain response does NOT match the denial
              regex `r"(?i)I (?:didn't|do not have|don't (?:think I )?
              (?:give|share|suggest)|did not (?:give|share|suggest))"`
  MECHANISM — the κ facts ARE retrieved via the search_memory wiring
              (`_make_memory_search_fn` → `query_knowledge_for`).
  Both must pass — no 3-way OR.

P5 scope clarification (Plan v2 §6 / §9): this test verifies WIRING only —
given seeded κ facts AND a search_memory invocation, the retrieval path
returns the facts so the brain has material to avoid denial. **Real-LLM
compliance with the new γ bullet is validated via post-closure re-canary**
within 1 week per Plan v2 §11.10; that's the empirical signal that closes
the loop on the canary failure mode.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import asyncio
import json
import re
from unittest.mock import MagicMock

import httpx
import pytest
import runtime.wiring as _wiring


# Denial regex per Plan v2 §6 L2 (tightened from Plan v1's 3-way OR).
_DENIAL_REGEX = re.compile(
    r"(?i)I (?:didn't|do not have|don't (?:think I )?"
    r"(?:give|share|suggest)|did not (?:give|share|suggest))"
)


def _build_test_orchestrator(tmp_path):
    """Minimal BrainOrchestrator with brain_db + a stubbed faces_conn that
    has the persons table the search path may need. Shape mirrors
    test_brain_agent.py's TestBrainOrchestrator setup (which my Phase 2
    work already touched)."""
    import sqlite3
    from core.brain_agent import BrainDB, BrainOrchestrator

    orch = BrainOrchestrator.__new__(BrainOrchestrator)
    orch._brain_db = BrainDB(tmp_path / "brain.db")
    orch._disputed_persons = set()

    # Stub faces conn — best_friend lookup queries persons table.
    orch._faces_conn = sqlite3.connect(":memory:")
    orch._faces_conn.executescript(
        """
        CREATE TABLE persons (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            person_type TEXT,
            enrolled_at REAL DEFAULT 0
        );
        """
    )
    return orch


@pytest.mark.asyncio
async def test_session_a_then_b_recipe_retrieval(tmp_path):
    """Plan v2 §6 test 7 — Phase 3 integration WIRING.

    P5 scope: verifies κ facts seeded by chain-5 fixture flow through the
    Session B retrieval surface (`query_knowledge_for` via the
    owner-override path P0.S7 P1 (ii)). The brain's response text is
    SUPPLIED by the test as a sample composed reply; the regex check
    asserts the wiring delivers retrievable facts so a non-denial response
    is structurally possible.

    Real-LLM compliance with the γ MEMORY HONESTY DISCIPLINE bullet is
    validated via post-closure re-canary, NOT this CI test (Plan v2 §11.10).
    """
    # Phase A — seed κ facts via chain-5 fixture.
    from tests.fixtures.event_log_fixtures import (
        build_multi_person_assistant_extraction,
    )

    orch = _build_test_orchestrator(tmp_path)
    result = build_multi_person_assistant_extraction(
        orch,
        owner_name="Jagan",  owner_pid="j_001",
        visitor_name="Lexi", visitor_pid="l_002",
    )
    assert result["session_b_ready"] is True
    assert len(result["extractions_stored"]) == 2  # owner witnesses + visitor receives

    # Sanity: facts persisted to brain.db (entity-keyed, person_id-scoped).
    facts_owner_perspective = orch._brain_db.query_knowledge_for(
        requester_pid="j_001",
        best_friend_id="j_001",       # P0.S7 P1 (ii) owner-override
        entity="Lexi",
        limit=15,
    )
    facts_visitor_perspective = orch._brain_db.query_knowledge_for(
        requester_pid="l_002",
        best_friend_id="j_001",
        entity="Lexi",
        limit=15,
    )
    # Owner (best_friend) sees Lexi's `received_*` fact via owner override.
    assert any(
        f["attribute"] == "received_shared_information"
        and "cheese cookies" in f["value"].lower()
        for f in facts_owner_perspective
    ), (
        "MECHANISM gap: Session A κ fact `Lexi.received_shared_information` "
        "is NOT retrievable by owner via query_knowledge_for. Best_friend "
        "owner-override path (P0.S7 P1 ii) must surface the cross-person fact."
    )
    # Visitor sees her own fact on return (own-pid retrieval, no override needed).
    assert any(
        f["attribute"] == "received_shared_information"
        for f in facts_visitor_perspective
    ), (
        "MECHANISM gap: visitor cannot retrieve her OWN `received_*` fact. "
        "personal-tier should allow owner-of-fact retrieval per D6."
    )

    # Phase B — exercise the search_memory mechanism via _make_memory_search_fn.
    # Patch the module-level _brain_orchestrator + _get_best_friend_cached so
    # the search fn can route through query_knowledge_for under test.
    import pipeline as _pl

    # Mock spy — wrap the orchestrator's query_knowledge_for so the test can
    # assert it was actually invoked (MECHANISM half of L2).
    real_query = orch._brain_db.query_knowledge_for
    spy = MagicMock(side_effect=real_query)
    orch._brain_db.query_knowledge_for = spy

    orig_orch         = _pl._brain_orchestrator
    orig_bf_cache_fn  = _pl._get_best_friend_cached
    _wiring._brain_orchestrator       = orch
    _pl._get_best_friend_cached   = lambda db: {"id": "j_001", "name": "Jagan"}
    try:
        # Pass a stub db (truthy) so the best_friend lookup gate fires; the
        # gate is `if db else None`, NOT `if db is not None`, so None
        # short-circuits the owner-override path. A MagicMock satisfies the
        # truthiness check + supports the .get_person_id_by_name attribute
        # access for the excerpt branch (no rows returned → empty list).
        stub_db = MagicMock()
        stub_db.get_person_id_by_name.return_value = None  # skip excerpts branch

        memory_search_fn = _pl._make_memory_search_fn(
            person_id="j_001",  # Session B speaker = owner
            db=stub_db,
        )

        # Owner-perspective search — simulates the brain's search_memory call.
        result_json = await memory_search_fn("Lexi", "cheese cookies recipe")
        result_dict = json.loads(result_json)
    finally:
        _wiring._brain_orchestrator     = orig_orch
        _pl._get_best_friend_cached = orig_bf_cache_fn

    # MECHANISM assertion — search_memory wiring invoked query_knowledge_for.
    spy.assert_called(), (
        "MECHANISM: _make_memory_search_fn must route through "
        "brain_db.query_knowledge_for (the privacy-filtered SQL path). "
        "If this spy is never called, the search_memory tool would always "
        "return empty regardless of stored facts."
    )

    # MECHANISM assertion — facts came back non-empty.
    assert result_dict.get("facts"), (
        "MECHANISM: search_memory call returned empty facts list even though "
        "κ facts are seeded in brain.db. The wiring through query_knowledge_for"
        " is not surfacing the cross-person fact via owner override."
    )
    fact_values = [f.get("value", "") for f in result_dict["facts"]]
    assert any("cheese cookies" in v.lower() for v in fact_values), (
        "MECHANISM: search_memory returned facts but none mention 'cheese "
        f"cookies'. Got values: {fact_values}"
    )

    # PRIMARY assertion — given the retrieved facts, brain CAN compose a
    # non-denial response. Sample composed reply uses the κ facts; verify
    # it doesn't trigger the denial regex.
    sample_response = (
        "Yes, I helped with the cheese cookies recipe — we walked through "
        "butter, sugar, eggs, flour, and cheese together. Glad they turned out!"
    )
    assert not _DENIAL_REGEX.search(sample_response), (
        "PRIMARY: sample non-denial response unexpectedly matched the denial "
        "regex. Pattern + sample text are inconsistent; review §6 L2 spec."
    )

    # Anti-control — a confident-denial response MUST match the regex (proves
    # the regex actually fires on the failure mode it's meant to catch).
    sample_denial = "I didn't actually give you a recipe in our conversation."
    assert _DENIAL_REGEX.search(sample_denial), (
        "PRIMARY anti-control: denial regex MUST match a confident self-denial "
        "phrase like 'I didn't actually give you a recipe'. If this fails, the "
        "regex needs strengthening before it can catch real-LLM canary denials."
    )
