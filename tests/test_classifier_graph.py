"""tests/test_classifier_graph.py — Spec 2 acceptance tests.

Covers the 20 tests from CLASSIFIER_GRAPH_SPEC_2.md acceptance table:
classifier shape, no-LLM invariants, abstention, Wilson confidence,
abstraction, correction loop, outcome supervision, mode routing,
latency budget.
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from core import classifier_graph as cg_mod
from core.classifier_db import ClassifierDB


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def fresh_paths(tmp_path: Path) -> tuple[Path, Path]:
    """Fresh DB + audit paths under tmp_path so tests don't share state."""
    return tmp_path / "graph.db", tmp_path / "audit.jsonl"


@pytest.fixture
def fresh_db(fresh_paths) -> ClassifierDB:
    db_path, audit_path = fresh_paths
    db = ClassifierDB(db_path=db_path, audit_log_path=audit_path)
    yield db
    db.close()


@pytest.fixture(autouse=True)
def _clear_module_state(monkeypatch):
    """Reset classifier_graph module singletons + the pending-outcomes
    queue between tests so cross-test bleed is impossible. Also include
    the Spec-2 local E5 singleton so the LocalE5Embedder cache doesn't
    leak across tests."""
    cg_mod._classifier_db = None
    cg_mod._embedding_agent = None
    cg_mod._local_e5 = None
    cg_mod._http_client = None
    cg_mod.reset_pending_outcomes()
    cg_mod._compiled_patterns_cache.clear()
    yield
    cg_mod.reset_pending_outcomes()


def _vec(seed: int = 0, dim: int = 1024) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim).astype(np.float32)
    return v / float(np.linalg.norm(v) + 1e-9)


def _seed_min_graph(db: ClassifierDB, target_text: str, target_label: str,
                    target_vec: np.ndarray, n_dist: int = 5) -> int:
    """Seed a minimal graph: one target scenario + N distractors. Returns
    the target's scenario_id."""
    target_id = db.insert_scenario(
        abstract_text=target_text,
        intent_label=target_label,
        embedding=target_vec,
        source_tag="test", source_version="v1",
        initial_confidence=0.85,
    )
    for i in range(n_dist):
        db.insert_scenario(
            abstract_text=f"distractor {i}",
            intent_label="casual_conversation",
            embedding=_vec(seed=100 + i),
            source_tag="test", source_version="v1",
            initial_confidence=0.5,
        )
    return target_id


def _install_fake_db(db: ClassifierDB):
    """Hook the test's fresh DB into the classifier_graph module so
    classify_intent_graph hits it instead of the real production DB."""
    cg_mod._classifier_db = db


def _install_fake_embedding(vec: np.ndarray):
    """Install a stub embedder that always returns ``vec``. Used by
    classify_intent_graph + handle_correction without hitting the
    network OR loading the local E5 model. Slots into both the local
    and network singletons so it works regardless of
    GRAPH_USE_LOCAL_EMBEDDINGS configuration."""
    fake_agent = MagicMock()
    fake_agent.embed = AsyncMock(return_value=vec.tolist())
    cg_mod._embedding_agent = fake_agent
    cg_mod._local_e5 = fake_agent
    return fake_agent


# ── 1. Output shape ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_classify_intent_graph_returns_correct_shape(fresh_db):
    target_vec = _vec(seed=1)
    _install_fake_db(fresh_db)
    _install_fake_embedding(target_vec)
    _seed_min_graph(fresh_db, "Hey {P1}, what's up?", "direct_address_to_person", target_vec)

    out = await cg_mod.classify_intent_graph("Hey friend, what's up?", persons_in_room=[], system_name="Kara")
    assert out is not None
    # Same keys as core.brain._classify_intent's sidecar shape
    for key in ("turn_intent", "extracted_value", "confidence", "reasoning", "__usage"):
        assert key in out, f"missing key {key}"
    assert out["turn_intent"] in {"direct_address_to_person", "casual_conversation"}
    assert isinstance(out["confidence"], float)
    assert 0.0 <= out["confidence"] <= 1.0


# ── 2. No-LLM invariant (classifier hot path) ─────────────────────────────


@pytest.mark.asyncio
async def test_classify_intent_graph_no_llm_calls(fresh_db, monkeypatch):
    """Mock all LLM clients to fail. Classifier still works because the
    graph hot path uses ONLY the embedding model (E5) + cosine k-NN."""
    target_vec = _vec(seed=2)
    _install_fake_db(fresh_db)
    _install_fake_embedding(target_vec)
    _seed_min_graph(fresh_db, "{SYSTEM}, what time is it?", "live_data_query", target_vec)

    # Make any LLM call raise hard
    async def _boom(*a, **kw):
        raise AssertionError("LLM was called from classifier hot path")
    monkeypatch.setattr("core.brain._classify_intent", _boom)
    # Brain's chat http client should also not be called
    monkeypatch.setattr("core.brain._chat_http", MagicMock())

    out = await cg_mod.classify_intent_graph("Kara, what time is it?", system_name="Kara")
    assert out is not None
    assert out["turn_intent"] == "live_data_query"


# ── 3. Empty DB → defensive abstain ───────────────────────────────────────


@pytest.mark.asyncio
async def test_classify_intent_graph_returns_none_on_empty_db(fresh_db):
    _install_fake_db(fresh_db)
    # Even if embedding is available, an empty graph means abstain.
    _install_fake_embedding(_vec(seed=3))
    out = await cg_mod.classify_intent_graph("Anything at all", system_name="Kara")
    assert out is None


# ── 4. Abstention below threshold ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_classify_intent_graph_abstains_below_threshold(fresh_db, monkeypatch):
    """Graph with no clear winner → confidence below GRAPH_ABSTAIN_THRESHOLD → None.
    Setup: two scenarios with the SAME target embedding but DIFFERENT labels
    means the winning label can claim at most ~50% of the total weight.
    With abstain threshold above 0.5, the classifier must abstain."""
    monkeypatch.setattr("core.classifier_graph.GRAPH_ABSTAIN_THRESHOLD", 0.99)
    _install_fake_db(fresh_db)
    target_vec = _vec(seed=4)
    _install_fake_embedding(target_vec)
    # Two scenarios with identical embedding → identical cosine sim → tied
    # weights → winning label gets ≤ 50% of total weight
    fresh_db.insert_scenario(
        abstract_text="amb-A", intent_label="casual_conversation",
        embedding=target_vec, source_tag="test", source_version="v1",
        initial_confidence=0.5,
    )
    fresh_db.insert_scenario(
        abstract_text="amb-B", intent_label="general_knowledge_query",
        embedding=target_vec, source_tag="test", source_version="v1",
        initial_confidence=0.5,
    )
    out = await cg_mod.classify_intent_graph("hi", system_name="Kara")
    assert out is None


# ── 5. Tied labels → Wilson tiebreaker ────────────────────────────────────


def test_aggregate_handles_tied_labels():
    """When two labels carry equal weighted sums, the aggregator prefers
    the label whose voters have the higher mean Wilson confidence."""
    same_sim = 0.5
    a = {"intent_label": "casual_conversation", "similarity": same_sim,
         "outcome_confirmed": 100, "outcome_reverted": 0, "initial_confidence": 0.5}
    b = {"intent_label": "request_shutdown", "similarity": same_sim,
         "outcome_confirmed": 1, "outcome_reverted": 0, "initial_confidence": 0.5}
    label, conf, _w, _v = cg_mod._aggregate_votes([a, b])
    assert label == "casual_conversation"


# ── 6. Wilson confidence bounds single confirmation ───────────────────────


def test_confidence_score_wilson_lower_bound():
    """A scenario with 1 confirmation and 0 reversions does NOT get full
    credit — Wilson lower bound keeps it well below 1.0."""
    score = cg_mod.confidence_score(
        {"outcome_confirmed": 1, "outcome_reverted": 0, "initial_confidence": 0.5}
    )
    assert 0.0 < score < 0.5, f"Wilson 1/0 should be bounded; got {score}"
    # 100/0 should approach 1.0 but stay below it
    high = cg_mod.confidence_score(
        {"outcome_confirmed": 100, "outcome_reverted": 0, "initial_confidence": 0.5}
    )
    assert 0.9 < high < 1.0
    # Initial bias used when no outcome data
    init = cg_mod.confidence_score(
        {"outcome_confirmed": 0, "outcome_reverted": 0, "initial_confidence": 0.7}
    )
    assert init == pytest.approx(0.7)


# ── 7. Abstraction strips PERSON + LOC ────────────────────────────────────


def test_abstract_text_strips_persons_and_places():
    """Coverage: registry replacement of known persons + system_name +
    NER fallback for unknown places."""
    from core.abstraction import abstract_text

    out, mapping = abstract_text(
        "Hey Lexi, what's the weather in Mumbai?",
        persons_in_room=["Lexi"], system_name="Kara",
    )
    assert "{P1}" in out
    assert "Lexi" not in out
    # NER should pick up Mumbai as GPE
    assert "{LOC1}" in out or "Mumbai" not in out
    assert mapping.get("{P1}") == "Lexi"


# ── 8. Times + numbers preserved ──────────────────────────────────────────


def test_abstract_text_preserves_times():
    """Times, dates, currency, numbers carry intent signal — must NOT be
    abstracted."""
    from core.abstraction import abstract_text

    out, _m = abstract_text(
        "Set a timer for 3pm tomorrow at $50.",
        persons_in_room=[], system_name="Kara",
    )
    assert "3pm" in out
    assert "tomorrow" in out
    assert "$50" in out


# ── 9. Correction decrements wrong-vote scenarios ─────────────────────────


@pytest.mark.asyncio
async def test_handle_correction_decrements_wrong_scenarios(fresh_db):
    """Pending outcome's scenarios all voted for label X. Correction
    fires → those scenarios' outcome_reverted goes up by 1."""
    _install_fake_db(fresh_db)
    sid = fresh_db.insert_scenario(
        abstract_text="Hey {P1}", intent_label="direct_address_to_person",
        embedding=_vec(seed=5),
        source_tag="test", source_version="v1",
        initial_confidence=0.7,
    )
    pending = {
        "decision_id":     "did-1",
        "intent_label":    "direct_address_to_person",
        "scenarios_used":  [sid],
        "user_text":       "Get me some chips",
        "persons_in_room": [],
        "system_name":     "Kara",
    }
    out = await cg_mod.handle_correction(
        "No Kara, that wasn't for you.",
        pending_outcome=pending,
        classifier_db=fresh_db,
        system_name="Kara",
    )
    assert out["scenarios_decremented"] == 1
    s = fresh_db.get_scenario(sid)
    assert s["outcome_reverted"] == 1


# ── 10. Correction with target writes new positive scenario ───────────────


@pytest.mark.asyncio
async def test_handle_correction_writes_new_positive_scenario(fresh_db):
    """When the regex extracts a target, a new direct_address_to_person
    scenario is inserted with source_tag='live_correction'."""
    _install_fake_db(fresh_db)
    _install_fake_embedding(_vec(seed=6))
    sid = fresh_db.insert_scenario(
        abstract_text="Hey {P1}", intent_label="addressing_ai_legacy",
        embedding=_vec(seed=7),
        source_tag="test", source_version="v1",
    )
    pending = {
        "decision_id":     "did-2",
        "intent_label":    "addressing_ai_legacy",
        "scenarios_used":  [sid],
        "user_text":       "Get me some chips",
        "persons_in_room": [],
        "system_name":     "Kara",
    }
    out = await cg_mod.handle_correction(
        "No Kara, I was talking to Lexi.",
        pending_outcome=pending,
        classifier_db=fresh_db,
        system_name="Kara",
    )
    assert out["target_extracted"] == "Lexi"
    assert out["new_scenario_id"] is not None
    new_scen = fresh_db.get_scenario(out["new_scenario_id"])
    assert new_scen["source_tag"] == "live_correction"
    assert new_scen["intent_label"] == "direct_address_to_person"


# ── 11. Correction loop hits no LLM ───────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_correction_no_llm_calls(fresh_db, monkeypatch):
    """Hard rule: correction-detection path NEVER calls the LLM."""
    _install_fake_db(fresh_db)
    _install_fake_embedding(_vec(seed=8))

    async def _boom(*a, **kw):
        raise AssertionError("LLM called from correction path")
    monkeypatch.setattr("core.brain._classify_intent", _boom)

    sid = fresh_db.insert_scenario(
        abstract_text="x", intent_label="direct_address_to_person",
        embedding=_vec(seed=9),
        source_tag="test", source_version="v1",
    )
    pending = {
        "decision_id": "did-3", "intent_label": "direct_address_to_person",
        "scenarios_used": [sid], "user_text": "x", "persons_in_room": [],
        "system_name": "Kara",
    }
    out = await cg_mod.handle_correction(
        "No Kara, I was talking to Sarah.",
        pending_outcome=pending, classifier_db=fresh_db, system_name="Kara",
    )
    assert out["scenarios_decremented"] == 1
    assert out["target_extracted"] == "Sarah"


# ── 12. Each correction pattern works ─────────────────────────────────────


def test_correction_pattern_extracts_target():
    """Spot-check a representative subset of the regex bank."""
    cases = [
        ("No Kara, I was talking to Lexi.",     "Lexi"),
        ("I meant Sarah, not you.",             "Sarah"),
        ("Shh, I'm talking to Priya.",          "Priya"),
        ("Stop Kara, that wasn't for you.",     None),  # null-target
        ("Not you, Kara.",                      None),  # null-target
        ("That was for John.",                  "John"),
    ]
    for text, expected in cases:
        got = cg_mod.extract_correction_target(text, system_name="Kara")
        assert got == expected, f"{text!r}: expected {expected!r}, got {got!r}"


# ── 13. Defensive: correction with no pending outcome ─────────────────────


@pytest.mark.asyncio
async def test_correction_skips_when_no_pending_outcome(fresh_db):
    """No pending decision → handle_correction is a no-op (no errors)."""
    _install_fake_db(fresh_db)
    out = await cg_mod.handle_correction(
        "No Kara, that wasn't for you.",
        pending_outcome=None,  # no pending
        classifier_db=fresh_db,
        system_name="Kara",
    )
    assert out["scenarios_decremented"] == 0
    assert out["skipped_reason"] == "no_pending_outcome"


# ── 14. 3-turn outcome supervision: silence is consent ────────────────────


def test_outcome_supervision_credits_after_3_turns(fresh_db, monkeypatch):
    """After GRAPH_OUTCOME_HOLDING_TURNS turns with no correction, pending
    outcome gets auto-credited as confirmed."""
    monkeypatch.setattr("core.classifier_graph.GRAPH_OUTCOME_HOLDING_TURNS", 3)
    _install_fake_db(fresh_db)
    sid = fresh_db.insert_scenario(
        abstract_text="x", intent_label="casual_conversation",
        embedding=_vec(seed=10),
        source_tag="test", source_version="v1",
    )
    sidecar = {
        "turn_intent": "casual_conversation",
        "extracted_value": None, "confidence": 0.9, "reasoning": "",
        "__usage": {"graph_decision": True, "winning_voter_ids": [sid]},
    }
    decision_id = cg_mod.record_pending_outcome(sidecar, "user said something",
                                                persons_in_room=[], system_name="Kara")
    assert decision_id != ""

    # Age twice — entry survives
    cg_mod.age_pending_outcomes()
    assert cg_mod._find_pending(decision_id) is not None
    cg_mod.age_pending_outcomes()
    assert cg_mod._find_pending(decision_id) is not None

    # Third aging: turns_aged hits 3 → auto-credited as confirmed + popped
    credited = cg_mod.age_pending_outcomes()
    assert credited == 1
    assert cg_mod._find_pending(decision_id) is None
    s = fresh_db.get_scenario(sid)
    assert s["outcome_confirmed"] == 1


# ── 15. Shadow mode logs divergences ──────────────────────────────────────


@pytest.mark.asyncio
async def test_shadow_mode_logs_divergences(fresh_db, monkeypatch, capsys):
    """Smart orchestrator in shadow mode runs both classifiers; mismatch
    surfaces in stdout via the [Intent] shadow divergence prefix."""
    monkeypatch.setattr("core.config.GRAPH_CLASSIFIER_MODE", "shadow")
    _install_fake_db(fresh_db)
    _install_fake_embedding(_vec(seed=11))
    fresh_db.insert_scenario(
        abstract_text="anything", intent_label="request_shutdown",
        embedding=_vec(seed=11),
        source_tag="test", source_version="v1",
        initial_confidence=0.9,
    )

    async def _fake_llm(text, conversation_history=None):
        return {"turn_intent": "casual_conversation", "extracted_value": None,
                "confidence": 0.85, "reasoning": "", "__usage": {}}
    monkeypatch.setattr("core.brain._classify_intent", _fake_llm)

    from core.brain import _classify_intent_smart
    out = await _classify_intent_smart("hi")
    # Production behavior unchanged: LLM result is returned
    assert out["turn_intent"] == "casual_conversation"
    captured = capsys.readouterr()
    assert "shadow divergence" in captured.out


# ── 16. Shadow mode returns LLM result (no behavior change) ───────────────


@pytest.mark.asyncio
async def test_shadow_mode_returns_llm_result(fresh_db, monkeypatch):
    monkeypatch.setattr("core.config.GRAPH_CLASSIFIER_MODE", "shadow")
    _install_fake_db(fresh_db)
    # Even when graph is empty, smart returns LLM result
    async def _fake_llm(text, conversation_history=None):
        return {"turn_intent": "general_knowledge_query", "extracted_value": None,
                "confidence": 0.92, "reasoning": "", "__usage": {}}
    monkeypatch.setattr("core.brain._classify_intent", _fake_llm)

    from core.brain import _classify_intent_smart
    out = await _classify_intent_smart("Who painted the Mona Lisa?")
    assert out["turn_intent"] == "general_knowledge_query"
    assert out["__usage"]["mode"] == "shadow"


# ── 17. Primary mode: graph wins when confident ───────────────────────────


@pytest.mark.asyncio
async def test_primary_mode_returns_graph_result_when_confident(fresh_db, monkeypatch):
    monkeypatch.setattr("core.config.GRAPH_CLASSIFIER_MODE", "primary")
    monkeypatch.setattr("core.config.GRAPH_PRIMARY_CONFIDENCE_FLOOR", 0.55)
    _install_fake_db(fresh_db)
    target_vec = _vec(seed=12)
    _install_fake_embedding(target_vec)
    fresh_db.insert_scenario(
        abstract_text="Shut down.", intent_label="request_shutdown",
        embedding=target_vec,
        source_tag="test", source_version="v1",
        initial_confidence=0.95,
    )

    async def _llm_should_not_fire(*a, **kw):
        raise AssertionError("LLM should not fire when graph is confident")
    monkeypatch.setattr("core.brain._classify_intent", _llm_should_not_fire)

    from core.brain import _classify_intent_smart
    out = await _classify_intent_smart("Shut down now.")
    assert out["turn_intent"] == "request_shutdown"
    assert out["__usage"]["mode"] == "primary"


# ── 18. Primary mode: LLM safety net on low graph confidence ──────────────


@pytest.mark.asyncio
async def test_primary_mode_falls_back_to_llm_when_low_confidence(fresh_db, monkeypatch):
    """Two-label tied graph keeps winning ratio at 0.5; primary floor 0.7
    triggers fallback to the LLM safety net."""
    monkeypatch.setattr("core.config.GRAPH_CLASSIFIER_MODE", "primary")
    monkeypatch.setattr("core.config.GRAPH_PRIMARY_CONFIDENCE_FLOOR", 0.7)
    _install_fake_db(fresh_db)
    target_vec = _vec(seed=13)
    _install_fake_embedding(target_vec)
    # Two scenarios with identical embeddings + different labels →
    # winning ratio capped at ~0.5 → below the 0.7 floor → fallback
    fresh_db.insert_scenario(
        abstract_text="x-A", intent_label="casual_conversation",
        embedding=target_vec, source_tag="test", source_version="v1",
        initial_confidence=0.5,
    )
    fresh_db.insert_scenario(
        abstract_text="x-B", intent_label="opinion_query",
        embedding=target_vec, source_tag="test", source_version="v1",
        initial_confidence=0.5,
    )

    async def _fake_llm(text, conversation_history=None):
        return {"turn_intent": "general_knowledge_query", "extracted_value": None,
                "confidence": 0.85, "reasoning": "llm-fallback", "__usage": {}}
    monkeypatch.setattr("core.brain._classify_intent", _fake_llm)

    from core.brain import _classify_intent_smart
    out = await _classify_intent_smart("ambiguous")
    assert out["turn_intent"] == "general_knowledge_query"
    assert out["__usage"]["mode"] == "primary_fallback_llm"


# ── 19. Retired mode never calls LLM ──────────────────────────────────────


@pytest.mark.asyncio
async def test_retired_mode_never_calls_llm(fresh_db, monkeypatch):
    monkeypatch.setattr("core.config.GRAPH_CLASSIFIER_MODE", "retired")
    _install_fake_db(fresh_db)
    target_vec = _vec(seed=14)
    _install_fake_embedding(target_vec)
    fresh_db.insert_scenario(
        abstract_text="Power off.", intent_label="request_shutdown",
        embedding=target_vec,
        source_tag="test", source_version="v1",
        initial_confidence=0.9,
    )

    async def _llm_should_not_fire(*a, **kw):
        raise AssertionError("LLM must not fire in retired mode")
    monkeypatch.setattr("core.brain._classify_intent", _llm_should_not_fire)

    from core.brain import _classify_intent_smart
    out = await _classify_intent_smart("Power off.")
    assert out is not None
    assert out["turn_intent"] == "request_shutdown"
    assert out["__usage"]["mode"] == "retired"


# ── 20. Latency budget on the local-only path ─────────────────────────────


@pytest.mark.asyncio
async def test_classifier_graph_latency_under_budget(fresh_db):
    """Latency check: with a stubbed embedding (no network) + small graph,
    p95 of 50 calls under GRAPH_LATENCY_BUDGET_MS. Validates that the
    abstraction + cosine k-NN + aggregation portion is genuinely fast.
    Real production latency depends on the embedding service; this tests
    the local-only portion of the budget."""
    target_vec = _vec(seed=15)
    _install_fake_db(fresh_db)
    _install_fake_embedding(target_vec)
    for i in range(25):
        fresh_db.insert_scenario(
            abstract_text=f"row {i}", intent_label="casual_conversation",
            embedding=_vec(seed=200 + i),
            source_tag="test", source_version="v1",
            initial_confidence=0.6,
        )
    fresh_db.insert_scenario(
        abstract_text="target", intent_label="casual_conversation",
        embedding=target_vec, source_tag="test", source_version="v1",
        initial_confidence=0.85,
    )
    # Warm-up: first call may pay one-time init (numpy stack, etc.)
    await cg_mod.classify_intent_graph("hi", system_name="Kara")
    times_ms: list[float] = []
    for _ in range(50):
        t0 = time.perf_counter()
        await cg_mod.classify_intent_graph("hi", system_name="Kara")
        times_ms.append((time.perf_counter() - t0) * 1000.0)
    times_ms.sort()
    p95 = times_ms[int(len(times_ms) * 0.95)]
    # 100ms budget per spec; allow 2x headroom for CI variance.
    from core.config import GRAPH_LATENCY_BUDGET_MS
    assert p95 < GRAPH_LATENCY_BUDGET_MS * 2, (
        f"p95 latency {p95:.1f}ms (budget {GRAPH_LATENCY_BUDGET_MS}ms)"
    )
