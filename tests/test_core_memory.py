"""
Wave 4 Item 18 — tests for tier memory: core vs archive.

Verifies:
1. _format_core_memory_block returns None on empty list
2. _format_core_memory_block annotates safety-critical attributes
3. get_core_memory_for returns [] when CORE_MEMORY_ENABLED is False
4. get_core_memory_for visibility: non-best-friend cannot see cross-person personal facts
5. get_core_memory_for visibility: best_friend (owner) can see personal facts about others
6. get_core_memory_for only returns attributes in CORE_MEMORY_ATTRIBUTES
7. get_core_memory_for filters out facts below CORE_MEMORY_MIN_CONFIDENCE
8. render_session_stable_prefix injects <<<CORE MEMORY>>> block when facts supplied
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import sqlite3
import tempfile
import os
import time

import pytest

import core.brain_agent as brain_agent
from core.brain import _format_core_memory_block, render_session_stable_prefix
from core.brain_agent import BrainDB


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def brain_db(tmp_path, monkeypatch):
    """BrainDB pointed at a throwaway in-memory-style temp file."""
    db_path = str(tmp_path / "brain_test.db")
    monkeypatch.setattr("core.brain_agent.BRAIN_DB_PATH", db_path)
    monkeypatch.setattr("core.brain_agent.GRAPH_DB_PATH", str(tmp_path / "graph"))
    db = BrainDB(db_path)
    yield db
    db._conn.close()


def _insert_fact(db: BrainDB, person_id: str, entity: str, attribute: str,
                 value: str, confidence: float, privacy_level: str):
    """Bypass store_knowledge's classifier — insert with explicit privacy_level."""
    now = time.time()
    db._conn.execute(
        "INSERT INTO knowledge "
        "(source_turn_id, person_id, entity, entity_type, attribute, value, confidence, "
        "is_temporal, valid_until, valid_at, agent, created_at, privacy_level) "
        "VALUES (0, ?, ?, 'person', ?, ?, ?, 0, NULL, ?, 'test', ?, ?)",
        (person_id, entity, attribute, value, confidence, now, now, privacy_level),
    )
    db._conn.commit()


# ── Test 1: _format_core_memory_block returns None on empty list ───────────────

def test_format_core_memory_block_none_on_empty():
    assert _format_core_memory_block([]) is None


# ── Test 2: safety-critical attributes get (SAFETY) annotation ────────────────

def test_format_core_memory_block_safety_annotation():
    facts = [
        {"attribute": "expressed_suicidal_thoughts", "value": "true", "confidence": 0.95},
        {"attribute": "lives_in", "value": "Tirupati", "confidence": 0.90},
    ]
    block = _format_core_memory_block(facts)
    assert block is not None
    assert "SAFETY" in block
    assert "expressed suicidal thoughts" in block
    assert "lives in: Tirupati" in block
    assert "<<<CORE MEMORY>>>" in block
    assert "<<<END CORE MEMORY>>>" in block


# ── Test 3: get_core_memory_for returns [] when flag disabled ─────────────────

def test_get_core_memory_for_disabled(brain_db, monkeypatch):
    monkeypatch.setattr("core.brain_agent.CORE_MEMORY_ENABLED", False)
    _insert_fact(brain_db, "jagan_abc", "Jagan", "lives_in", "Tirupati", 0.9, "personal")
    result = brain_db.get_core_memory_for("jagan_abc", None, "Jagan")
    assert result == []


# ── Test 4: non-best-friend cannot see cross-person personal facts ─────────────

@pytest.mark.privacy_critical
def test_get_core_memory_for_privacy_cross_person_blocked(brain_db, monkeypatch):
    monkeypatch.setattr("core.brain_agent.CORE_MEMORY_ENABLED", True)
    # Lexi's personal fact stored under Lexi's person_id
    _insert_fact(brain_db, "lexi_xyz", "Lexi", "lives_in", "Chennai", 0.9, "personal")
    # Requester is Jagan (non-best-friend, best_friend_id=None → non-owner)
    result = brain_db.get_core_memory_for("jagan_abc", None, "Lexi")
    # Non-owner cannot see personal facts belonging to another person
    assert all(r["person_id"] != "lexi_xyz" or r["privacy_level"] == "public"
               for r in result), "cross-person personal fact leaked to non-owner"


# ── Test 5: best_friend (owner) can see personal facts about others ────────────

@pytest.mark.privacy_critical
def test_get_core_memory_for_best_friend_sees_personal(brain_db, monkeypatch):
    monkeypatch.setattr("core.brain_agent.CORE_MEMORY_ENABLED", True)
    _insert_fact(brain_db, "lexi_xyz", "Lexi", "lives_in", "Chennai", 0.9, "personal")
    # Jagan is best_friend
    result = brain_db.get_core_memory_for("jagan_abc", "jagan_abc", "Lexi")
    values = [r["value"] for r in result]
    assert "Chennai" in values, "best_friend should see personal facts about others"


# ── Test 6: only returns attributes in CORE_MEMORY_ATTRIBUTES ─────────────────

@pytest.mark.privacy_critical
def test_get_core_memory_for_attribute_whitelist(brain_db, monkeypatch):
    monkeypatch.setattr("core.brain_agent.CORE_MEMORY_ENABLED", True)
    # Insert a whitelisted attribute and a non-whitelisted one
    _insert_fact(brain_db, "jagan_abc", "Jagan", "lives_in", "Tirupati", 0.9, "personal")
    _insert_fact(brain_db, "jagan_abc", "Jagan", "current_mood", "happy", 0.9, "personal")
    result = brain_db.get_core_memory_for("jagan_abc", "jagan_abc", "Jagan")
    attrs = {r["attribute"] for r in result}
    assert "lives_in" in attrs, "whitelisted attribute should be returned"
    assert "current_mood" not in attrs, "non-whitelisted attribute must not be returned"


# ── Test 7: filters out facts below CORE_MEMORY_MIN_CONFIDENCE ────────────────

def test_get_core_memory_for_confidence_floor(brain_db, monkeypatch):
    monkeypatch.setattr("core.brain_agent.CORE_MEMORY_ENABLED", True)
    monkeypatch.setattr("core.brain_agent.CORE_MEMORY_MIN_CONFIDENCE", 0.50)
    _insert_fact(brain_db, "jagan_abc", "Jagan", "lives_in", "Tirupati", 0.30, "personal")
    _insert_fact(brain_db, "jagan_abc", "Jagan", "works_at", "TCS", 0.80, "personal")
    result = brain_db.get_core_memory_for("jagan_abc", "jagan_abc", "Jagan")
    values = [r["value"] for r in result]
    assert "Tirupati" not in values, "fact below confidence floor must be excluded"
    assert "TCS" in values, "fact above confidence floor must be included"


# ── Test 8: render_session_stable_prefix injects <<<CORE MEMORY>>> ────────────

def test_render_session_stable_prefix_injects_core_memory():
    facts = [
        {"attribute": "lives_in", "value": "Tirupati", "confidence": 0.9},
    ]
    prefix = render_session_stable_prefix(
        system_name="Kara",
        session_person_type="known",
        session_user_turns=1,
        identity_disputed=False,
        person_name="Jagan",
        disputed_claimed_name=None,
        core_memory=facts,
    )
    assert "<<<CORE MEMORY>>>" in prefix
    assert "lives in: Tirupati" in prefix
    assert "<<<END CORE MEMORY>>>" in prefix


def test_render_session_stable_prefix_no_core_memory_block_when_empty():
    prefix = render_session_stable_prefix(
        system_name="Kara",
        session_person_type="known",
        session_user_turns=1,
        identity_disputed=False,
        person_name="Jagan",
        disputed_claimed_name=None,
        core_memory=[],
    )
    assert "<<<CORE MEMORY>>>" not in prefix
