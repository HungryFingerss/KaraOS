# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""100% coverage for core.classifier_graph — pure-graph intent classifier (coverage-to-100 campaign).

Complements tests/test_classifier_graph.py (the Spec-2 acceptance suite) by
exercising the lazy-singleton getters, the LocalE5Embedder model path (torch +
transformers mocked at the import boundary), every defensive abstain / error
branch in classify_intent_graph + handle_correction, the outcome-supervision
queue edge cases, and the lifecycle helpers. Fully headless — no GPU, camera,
model download, or network.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from core import classifier_graph as cg
from core.classifier_db import ClassifierDB


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_module_state():
    """Reset every classifier_graph module singleton + the session counters +
    the pending-outcomes queue between tests so cross-test bleed is impossible
    (mirrors the acceptance suite's autouse reset)."""
    cg._classifier_db = None
    cg._embedding_agent = None
    cg._local_e5 = None
    cg._http_client = None
    cg.reset_pending_outcomes()
    cg._compiled_patterns_cache.clear()
    cg._session_classifications = 0
    cg._session_shadow_divergences = 0
    cg._session_corrections = 0
    cg._session_new_scenarios = 0
    cg._session_confirmed = 0
    cg._session_reverted = 0
    yield
    cg.reset_pending_outcomes()


@pytest.fixture
def fresh_db(tmp_path):
    db = ClassifierDB(db_path=tmp_path / "graph.db", audit_log_path=tmp_path / "audit.jsonl")
    yield db
    db.close()


def _vec(seed: int = 0, dim: int = 1024) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim).astype(np.float32)
    return v / float(np.linalg.norm(v) + 1e-9)


def _seed_one(db, seed: int = 0) -> int:
    return db.insert_scenario(
        abstract_text=f"seed {seed}", intent_label="casual_conversation",
        embedding=_vec(seed), source_tag="test", source_version="v1",
        initial_confidence=0.6,
    )


def _install_agent(*, embed_result=None, embed_side_effect=None):
    """Install a stub embedder into BOTH singletons (local + network) so
    _get_embedding_agent returns it regardless of GRAPH_USE_LOCAL_EMBEDDINGS."""
    fake = MagicMock()
    if embed_side_effect is not None:
        fake.embed = AsyncMock(side_effect=embed_side_effect)
    else:
        fake.embed = AsyncMock(return_value=embed_result)
    cg._embedding_agent = fake
    cg._local_e5 = fake
    return fake


# ── Fake torch / transformers scaffolding for LocalE5Embedder ───────────────


def _make_fake_torch(cuda_available: bool = False, tolist_return=None):
    ft = types.ModuleType("torch")
    ft.cuda = types.SimpleNamespace(is_available=lambda: cuda_available)

    class _NoGrad:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    ft.no_grad = lambda: _NoGrad()
    norm_result = MagicMock()
    norm_result.__getitem__.return_value.cpu.return_value.tolist.return_value = (
        tolist_return if tolist_return is not None else [0.5, 0.5]
    )
    ft.nn = types.SimpleNamespace(
        functional=types.SimpleNamespace(normalize=MagicMock(return_value=norm_result))
    )
    return ft


def _make_fake_transformers(model=None):
    ftm = types.ModuleType("transformers")

    def _tok_call(text, **kw):
        # A real dict so both the cuda comprehension (.items()) and the
        # cpu path (subscript) work over MagicMock "tensors".
        return {"attention_mask": MagicMock(), "input_ids": MagicMock()}

    tokenizer = MagicMock(side_effect=_tok_call)
    the_model = model if model is not None else MagicMock()
    ftm.AutoTokenizer = MagicMock()
    ftm.AutoTokenizer.from_pretrained = MagicMock(return_value=tokenizer)
    ftm.AutoModel = MagicMock()
    ftm.AutoModel.from_pretrained = MagicMock(return_value=the_model)
    return ftm, the_model


# ── _get_db ─────────────────────────────────────────────────────────────────


def test_get_db_returns_cached_singleton():
    # lines 85-86: fast path returns the already-open singleton
    sentinel = object()
    cg._classifier_db = sentinel
    assert cg._get_db() is sentinel


def test_get_db_with_override(tmp_path, monkeypatch, capsys):
    # lines 87-96 + 90-91: CLASSIFIER_DB_PATH_OVERRIDE active -> print + open
    ov = str(tmp_path / "override.db")
    monkeypatch.setenv("CLASSIFIER_DB_PATH_OVERRIDE", ov)
    monkeypatch.setattr(cg, "CLASSIFIER_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    cg._classifier_db = None
    db = cg._get_db()
    try:
        assert db is not None
        assert cg._classifier_db is db
        assert "OVERRIDE active" in capsys.readouterr().out
    finally:
        db.close()


def test_get_db_without_override(tmp_path, monkeypatch, capsys):
    # lines 88-96 with override falsy -> db_path = CLASSIFIER_DB_PATH, no print
    monkeypatch.delenv("CLASSIFIER_DB_PATH_OVERRIDE", raising=False)
    monkeypatch.setattr(cg, "CLASSIFIER_DB_PATH", str(tmp_path / "plain.db"))
    monkeypatch.setattr(cg, "CLASSIFIER_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    cg._classifier_db = None
    db = cg._get_db()
    try:
        assert db is not None
        assert "OVERRIDE active" not in capsys.readouterr().out
    finally:
        db.close()


def test_get_db_open_failure_returns_none(monkeypatch, capsys):
    # lines 97-99: ClassifierDB construction raises -> logged, None returned
    monkeypatch.delenv("CLASSIFIER_DB_PATH_OVERRIDE", raising=False)
    monkeypatch.setattr(cg, "ClassifierDB", MagicMock(side_effect=RuntimeError("disk full")))
    cg._classifier_db = None
    assert cg._get_db() is None
    assert "ClassifierDB open failed" in capsys.readouterr().out


# ── LocalE5Embedder._load ───────────────────────────────────────────────────


def test_local_e5_load_early_return_when_loaded():
    # lines 121-122: model already loaded -> return without importing torch
    emb = cg.LocalE5Embedder()
    sentinel = MagicMock()
    emb._model = sentinel
    emb._load()
    assert emb._model is sentinel


def test_local_e5_load_explicit_cuda_device(monkeypatch, capsys):
    # lines 125-126 + 131-141 (device == "cuda" branch + model.cuda())
    monkeypatch.setattr(cg, "GRAPH_LOCAL_EMBEDDING_DEVICE", "cuda")
    monkeypatch.setitem(sys.modules, "torch", _make_fake_torch())
    ftm, model = _make_fake_transformers()
    monkeypatch.setitem(sys.modules, "transformers", ftm)
    emb = cg.LocalE5Embedder()
    emb._load()
    assert emb._device == "cuda"
    assert emb._model is not None
    model.cuda.assert_called_once()
    assert "local E5 loaded" in capsys.readouterr().out


def test_local_e5_load_explicit_cpu_device(monkeypatch):
    # lines 127-128 (device == "cpu" branch -> no .cuda())
    monkeypatch.setattr(cg, "GRAPH_LOCAL_EMBEDDING_DEVICE", "cpu")
    monkeypatch.setitem(sys.modules, "torch", _make_fake_torch())
    ftm, model = _make_fake_transformers()
    monkeypatch.setitem(sys.modules, "transformers", ftm)
    emb = cg.LocalE5Embedder()
    emb._load()
    assert emb._device == "cpu"
    model.cuda.assert_not_called()
    assert emb._model is model


def test_local_e5_load_auto_device_no_cuda(monkeypatch):
    # lines 129-130 (auto -> torch.cuda.is_available() False -> cpu)
    monkeypatch.setattr(cg, "GRAPH_LOCAL_EMBEDDING_DEVICE", "auto")
    monkeypatch.setitem(sys.modules, "torch", _make_fake_torch(cuda_available=False))
    ftm, model = _make_fake_transformers()
    monkeypatch.setitem(sys.modules, "transformers", ftm)
    emb = cg.LocalE5Embedder()
    emb._load()
    assert emb._device == "cpu"
    model.cuda.assert_not_called()


def test_local_e5_load_auto_device_with_cuda(monkeypatch):
    # line 130 (auto -> is_available() True -> cuda) + 136-137
    monkeypatch.setattr(cg, "GRAPH_LOCAL_EMBEDDING_DEVICE", "auto")
    monkeypatch.setitem(sys.modules, "torch", _make_fake_torch(cuda_available=True))
    ftm, model = _make_fake_transformers()
    monkeypatch.setitem(sys.modules, "transformers", ftm)
    emb = cg.LocalE5Embedder()
    emb._load()
    assert emb._device == "cuda"
    model.cuda.assert_called_once()


# ── LocalE5Embedder._encode_sync ────────────────────────────────────────────


def test_local_e5_encode_sync_success_cpu(monkeypatch):
    # lines 143-165 (cpu path: skip the cuda token move at 155-156)
    monkeypatch.setattr(cg, "GRAPH_LOCAL_EMBEDDING_DEVICE", "cpu")
    monkeypatch.setitem(sys.modules, "torch", _make_fake_torch(tolist_return=[0.1, 0.2, 0.3]))
    ftm, _model = _make_fake_transformers()
    monkeypatch.setitem(sys.modules, "transformers", ftm)
    emb = cg.LocalE5Embedder()
    assert emb._encode_sync("hello") == [0.1, 0.2, 0.3]


def test_local_e5_encode_sync_success_cuda(monkeypatch):
    # lines 155-156 (device == cuda -> tokens moved to .cuda())
    monkeypatch.setattr(cg, "GRAPH_LOCAL_EMBEDDING_DEVICE", "cuda")
    monkeypatch.setitem(sys.modules, "torch", _make_fake_torch(tolist_return=[0.9]))
    ftm, _model = _make_fake_transformers()
    monkeypatch.setitem(sys.modules, "transformers", ftm)
    emb = cg.LocalE5Embedder()
    assert emb._encode_sync("hello") == [0.9]


def test_local_e5_encode_sync_load_failure_returns_none(monkeypatch, capsys):
    # lines 147-149: _load raises -> logged, None returned
    monkeypatch.setitem(sys.modules, "torch", _make_fake_torch())
    emb = cg.LocalE5Embedder()
    emb._load = MagicMock(side_effect=RuntimeError("no model on disk"))
    assert emb._encode_sync("hi") is None
    assert "local E5 load failed" in capsys.readouterr().out


def test_local_e5_encode_sync_encode_failure_returns_none(monkeypatch, capsys):
    # lines 166-168: the forward pass raises -> logged, None returned
    monkeypatch.setattr(cg, "GRAPH_LOCAL_EMBEDDING_DEVICE", "cpu")
    raising_model = MagicMock(side_effect=RuntimeError("cuda oom"))
    monkeypatch.setitem(sys.modules, "torch", _make_fake_torch())
    ftm, _model = _make_fake_transformers(model=raising_model)
    monkeypatch.setitem(sys.modules, "transformers", ftm)
    emb = cg.LocalE5Embedder()
    assert emb._encode_sync("hi") is None
    assert "local E5 encode failed" in capsys.readouterr().out


# ── LocalE5Embedder.embed / embed_batch ─────────────────────────────────────


async def test_local_e5_embed_runs_encode_in_executor():
    # lines 172-174: embed builds the instruction + runs _encode_sync off-loop
    emb = cg.LocalE5Embedder()
    captured = {}

    def _fake_encode(instruction):
        captured["instruction"] = instruction
        return [1.0, 2.0]

    emb._encode_sync = _fake_encode
    out = await emb.embed("hi there", purpose="unit test")
    assert out == [1.0, 2.0]
    assert captured["instruction"] == "Instruction: represent the unit test for retrieval: hi there"


async def test_local_e5_embed_batch_sequential():
    # line 182: batch API embeds each text sequentially
    emb = cg.LocalE5Embedder()
    emb._encode_sync = lambda instruction: [3.0]
    out = await emb.embed_batch(["a", "b"], purpose="unit test")
    assert out == [[3.0], [3.0]]


# ── _get_embedding_agent ────────────────────────────────────────────────────


def test_get_embedding_agent_local_creates_singleton(monkeypatch):
    # line 201: local mode, singleton not yet built -> construct LocalE5Embedder
    monkeypatch.setattr(cg, "GRAPH_USE_LOCAL_EMBEDDINGS", True)
    cg._local_e5 = None
    agent = cg._get_embedding_agent()
    assert isinstance(agent, cg.LocalE5Embedder)
    assert cg._local_e5 is agent


def test_get_embedding_agent_network_cached(monkeypatch):
    # lines 205-206: network mode with an existing agent -> return cached
    monkeypatch.setattr(cg, "GRAPH_USE_LOCAL_EMBEDDINGS", False)
    sentinel = object()
    cg._embedding_agent = sentinel
    assert cg._get_embedding_agent() is sentinel


def test_get_embedding_agent_network_import_failure(monkeypatch, capsys):
    # lines 207-211: import of EmbeddingAgent/EMBED_API_KEY fails -> None
    monkeypatch.setattr(cg, "GRAPH_USE_LOCAL_EMBEDDINGS", False)
    cg._embedding_agent = None
    # A bare module missing both names -> AttributeError on `from ... import`.
    fake_ba = types.ModuleType("core.brain_agent")
    monkeypatch.setitem(sys.modules, "core.brain_agent", fake_ba)
    assert cg._get_embedding_agent() is None
    assert "EmbeddingAgent import failed" in capsys.readouterr().out


def test_get_embedding_agent_network_empty_key(monkeypatch, capsys):
    # lines 212-214: EMBED_API_KEY empty -> classifier disabled, None
    monkeypatch.setattr(cg, "GRAPH_USE_LOCAL_EMBEDDINGS", False)
    cg._embedding_agent = None
    fake_ba = types.ModuleType("core.brain_agent")
    fake_ba.EmbeddingAgent = MagicMock()
    fake_ba.EMBED_API_KEY = ""
    monkeypatch.setitem(sys.modules, "core.brain_agent", fake_ba)
    assert cg._get_embedding_agent() is None
    assert "EMBED_API_KEY empty" in capsys.readouterr().out


async def test_get_embedding_agent_network_success(monkeypatch):
    # lines 215-217: build the httpx client + network EmbeddingAgent
    monkeypatch.setattr(cg, "GRAPH_USE_LOCAL_EMBEDDINGS", False)
    cg._embedding_agent = None

    class _FakeAgent:
        def __init__(self, http=None):
            self.http = http

    fake_ba = types.ModuleType("core.brain_agent")
    fake_ba.EmbeddingAgent = _FakeAgent
    fake_ba.EMBED_API_KEY = "fake-key"
    monkeypatch.setitem(sys.modules, "core.brain_agent", fake_ba)
    agent = cg._get_embedding_agent()
    try:
        assert isinstance(agent, _FakeAgent)
        assert cg._http_client is not None
        assert agent.http is cg._http_client
    finally:
        await cg._http_client.aclose()
        cg._http_client = None


# ── _aggregate_votes ────────────────────────────────────────────────────────


def test_aggregate_votes_all_zero_weight_returns_unclear():
    # lines 264-265 (weight <= 0 continue) + 271 (no labels -> unclear)
    neighbors = [
        {"intent_label": "casual_conversation", "similarity": 0.0, "initial_confidence": 0.5},
        {"intent_label": "request_shutdown", "similarity": -0.3, "initial_confidence": 0.5},
    ]
    label, conf, weights, voters = cg._aggregate_votes(neighbors)
    assert label == "unclear"
    assert conf == 0.0
    assert weights == {}
    assert voters == {}


# ── classify_intent_graph — defensive branches ──────────────────────────────


async def test_classify_empty_text_returns_none():
    # lines 306-307: empty / whitespace user_text short-circuits
    assert await cg.classify_intent_graph("") is None
    assert await cg.classify_intent_graph("   ") is None


async def test_classify_returns_none_when_db_none(monkeypatch):
    # lines 309-311: _get_db() None -> abstain (graph not bootstrapped)
    monkeypatch.setattr(cg, "_get_db", lambda: None)
    assert await cg.classify_intent_graph("hi", system_name="Kara") is None


async def test_classify_returns_none_when_agent_none(fresh_db, monkeypatch):
    # lines 313-315: embedding agent unavailable -> abstain
    _seed_one(fresh_db)
    cg._classifier_db = fresh_db
    monkeypatch.setattr(cg, "_get_embedding_agent", lambda: None)
    assert await cg.classify_intent_graph("hi", system_name="Kara") is None


async def test_classify_returns_none_when_embed_raises(fresh_db, capsys):
    # lines 330-332: embed raises -> logged, abstain
    _seed_one(fresh_db)
    cg._classifier_db = fresh_db
    _install_agent(embed_side_effect=RuntimeError("embed boom"))
    assert await cg.classify_intent_graph("hi", system_name="Kara") is None
    assert "embed failed" in capsys.readouterr().out


async def test_classify_returns_none_when_embed_returns_none(fresh_db):
    # lines 333-334: embedder returns None -> abstain
    _seed_one(fresh_db)
    cg._classifier_db = fresh_db
    _install_agent(embed_result=None)
    assert await cg.classify_intent_graph("hi", system_name="Kara") is None


async def test_classify_returns_none_when_query_raises(fresh_db, monkeypatch, capsys):
    # lines 342-344: db.query_nearest raises -> logged, abstain
    _seed_one(fresh_db)
    cg._classifier_db = fresh_db
    _install_agent(embed_result=_vec(1).tolist())
    monkeypatch.setattr(fresh_db, "query_nearest", MagicMock(side_effect=RuntimeError("q boom")))
    assert await cg.classify_intent_graph("hi", system_name="Kara") is None
    assert "query failed" in capsys.readouterr().out


async def test_classify_returns_none_on_empty_neighbors(fresh_db, monkeypatch):
    # lines 347-348: no neighbors -> abstain
    _seed_one(fresh_db)
    cg._classifier_db = fresh_db
    _install_agent(embed_result=_vec(1).tolist())
    monkeypatch.setattr(fresh_db, "query_nearest", MagicMock(return_value=[]))
    assert await cg.classify_intent_graph("hi", system_name="Kara") is None


async def test_classify_abstains_when_winning_label_unknown(fresh_db, capsys):
    # lines 358-363: resolve -> label not in INTENT_LABELS -> abstain
    tv = _vec(20)
    fresh_db.insert_scenario(
        abstract_text="odd row", intent_label="bogus_not_a_real_label",
        embedding=tv, source_tag="test", source_version="v1",
        initial_confidence=0.9,
    )
    cg._classifier_db = fresh_db
    _install_agent(embed_result=tv.tolist())
    assert await cg.classify_intent_graph("hi", system_name="Kara") is None
    assert "not in INTENT_LABELS" in capsys.readouterr().out


async def test_classify_deabstracts_extracted_value(fresh_db):
    # lines 366-375: winning voter carries a placeholder -> de-abstract to name
    tv = _vec(21)
    fresh_db.insert_scenario(
        abstract_text="Hey {P1}", intent_label="direct_address_to_person",
        embedding=tv, source_tag="test", source_version="v1",
        initial_confidence=0.9, extracted_value="{P1}",
    )
    cg._classifier_db = fresh_db
    _install_agent(embed_result=tv.tolist())
    out = await cg.classify_intent_graph(
        "Hey friend", persons_in_room=["Lexi"], system_name="Kara"
    )
    assert out is not None
    assert out["turn_intent"] == "direct_address_to_person"
    assert out["extracted_value"] == "Lexi"


# ── _format_reasoning / _maybe_warn_latency ─────────────────────────────────


def test_format_reasoning_no_voters():
    # lines 408-409: empty voter list -> no-voters diagnostic
    assert cg._format_reasoning("casual_conversation", {"a": 1.0}, []) == (
        "graph: casual_conversation (no voters)"
    )


def test_maybe_warn_latency_over_budget(capsys):
    # lines 424-426: total_ms over budget -> warning printed
    cg._maybe_warn_latency(10 ** 9, "some long user utterance to snip")
    assert "latency" in capsys.readouterr().out


# ── extract_correction_target — edge branches ───────────────────────────────


def test_extract_correction_target_empty_text():
    # lines 485-486: falsy text -> None
    assert cg.extract_correction_target("", system_name="Kara") is None


def test_extract_correction_target_no_match():
    # line 505: no pattern matches -> None (loop exhausted)
    assert cg.extract_correction_target("The weather is lovely today", system_name="Kara") is None


def test_extract_correction_target_index_error(monkeypatch):
    # lines 496-498: pattern claims a group but m.group(1) raises IndexError
    fake_match = MagicMock()
    fake_match.group.side_effect = IndexError("no such group")
    fake_pat = MagicMock()
    fake_pat.groups = 1
    fake_pat.search.return_value = fake_match
    monkeypatch.setattr(cg, "_get_correction_patterns", lambda sn: [fake_pat])
    assert cg.extract_correction_target("anything", system_name="Kara") is None


# ── record_pending_outcome ──────────────────────────────────────────────────


def test_record_pending_outcome_non_graph_returns_empty():
    # lines 520-522: non-graph sidecar (or None) -> no-op empty string
    assert cg.record_pending_outcome({"turn_intent": "x", "__usage": {}}, "text") == ""
    assert cg.record_pending_outcome({}, "text") == ""
    assert cg.record_pending_outcome(None, "text") == ""


# ── confirm_pending ─────────────────────────────────────────────────────────


def test_confirm_pending_not_found_returns_zero():
    # lines 550-551: unknown decision_id -> 0
    assert cg.confirm_pending("nope") == 0


def test_confirm_pending_db_none_pops_and_returns_zero(monkeypatch):
    # lines 554-557: db unavailable -> pop entry, credit nothing
    did = cg.record_pending_outcome(
        {"turn_intent": "casual_conversation",
         "__usage": {"graph_decision": True, "winning_voter_ids": [1]}}, "x")
    monkeypatch.setattr(cg, "_get_db", lambda: None)
    assert cg.confirm_pending(did) == 0
    assert cg._find_pending(did) is None


def test_confirm_pending_key_error_skips(fresh_db):
    # lines 565-566: increment_outcome raises KeyError (missing sid) -> skipped
    cg._classifier_db = fresh_db
    did = cg.record_pending_outcome(
        {"turn_intent": "casual_conversation",
         "__usage": {"graph_decision": True, "winning_voter_ids": [99999]}}, "x")
    assert cg.confirm_pending(did) == 0
    assert cg._find_pending(did) is None


# ── revert_pending ──────────────────────────────────────────────────────────


def test_revert_pending_not_found_returns_zero():
    # line 577: unknown decision_id -> 0
    assert cg.revert_pending("nope") == 0


def test_revert_pending_db_none_pops_and_returns_zero(monkeypatch):
    # lines 580-582: db unavailable -> pop entry, revert nothing
    did = cg.record_pending_outcome(
        {"turn_intent": "casual_conversation",
         "__usage": {"graph_decision": True, "winning_voter_ids": [1]}}, "x")
    monkeypatch.setattr(cg, "_get_db", lambda: None)
    assert cg.revert_pending(did) == 0
    assert cg._find_pending(did) is None


def test_revert_pending_increments_reverted(fresh_db):
    # lines 583-595: happy path -> outcome_reverted bumped, entry popped
    sid = fresh_db.insert_scenario(
        abstract_text="x", intent_label="casual_conversation",
        embedding=_vec(30), source_tag="test", source_version="v1",
    )
    cg._classifier_db = fresh_db
    did = cg.record_pending_outcome(
        {"turn_intent": "casual_conversation",
         "__usage": {"graph_decision": True, "winning_voter_ids": [sid]}}, "x")
    assert cg.revert_pending(did) == 1
    assert fresh_db.get_scenario(sid)["outcome_reverted"] == 1
    assert cg._find_pending(did) is None


def test_revert_pending_key_error_skips(fresh_db):
    # lines 590-591: increment_outcome raises KeyError -> skipped
    cg._classifier_db = fresh_db
    did = cg.record_pending_outcome(
        {"turn_intent": "casual_conversation",
         "__usage": {"graph_decision": True, "winning_voter_ids": [99999]}}, "x")
    assert cg.revert_pending(did) == 0


# ── latest_pending ──────────────────────────────────────────────────────────


def test_latest_pending_returns_deepest_entry():
    # lines 620-622: non-empty queue -> newest (rightmost) entry
    cg.record_pending_outcome(
        {"turn_intent": "a", "__usage": {"graph_decision": True, "winning_voter_ids": []}}, "first")
    did2 = cg.record_pending_outcome(
        {"turn_intent": "b", "__usage": {"graph_decision": True, "winning_voter_ids": []}}, "second")
    latest = cg.latest_pending()
    assert latest is not None
    assert latest["decision_id"] == did2


# ── handle_correction — additional branches ─────────────────────────────────


async def test_handle_correction_db_unavailable(monkeypatch):
    # lines 669-672: classifier_db None + _get_db() None -> skipped
    monkeypatch.setattr(cg, "_get_db", lambda: None)
    pending = {"decision_id": "d", "intent_label": "casual_conversation",
               "scenarios_used": [1], "user_text": "x",
               "persons_in_room": [], "system_name": "Kara"}
    out = await cg.handle_correction(
        "No Kara, that wasn't for you.", pending_outcome=pending,
        classifier_db=None, system_name="Kara")
    assert out["skipped_reason"] == "classifier_db_unavailable"


async def test_handle_correction_skips_missing_scenario(fresh_db):
    # lines 681-682: get_scenario returns None -> continue (not decremented)
    pending = {"decision_id": "d", "intent_label": "direct_address_to_person",
               "scenarios_used": [99999], "user_text": "x",
               "persons_in_room": [], "system_name": "Kara"}
    out = await cg.handle_correction(
        "hmm ok", pending_outcome=pending, classifier_db=fresh_db, system_name="Kara")
    assert out["scenarios_decremented"] == 0


async def test_handle_correction_skips_other_label_voter(fresh_db):
    # line 685 (False side): voter voted for a different label -> not decremented
    sid = fresh_db.insert_scenario(
        abstract_text="x", intent_label="casual_conversation",
        embedding=_vec(40), source_tag="test", source_version="v1",
    )
    pending = {"decision_id": "d", "intent_label": "direct_address_to_person",
               "scenarios_used": [sid], "user_text": "x",
               "persons_in_room": [], "system_name": "Kara"}
    out = await cg.handle_correction(
        "hmm ok", pending_outcome=pending, classifier_db=fresh_db, system_name="Kara")
    assert out["scenarios_decremented"] == 0
    assert fresh_db.get_scenario(sid)["outcome_reverted"] == 0


async def test_handle_correction_decrement_key_error():
    # lines 693-694: get_scenario returns a matching-label row but
    # increment_outcome races to a KeyError -> swallowed
    fake_db = MagicMock()
    fake_db.get_scenario.return_value = {"intent_label": "direct_address_to_person"}
    fake_db.increment_outcome.side_effect = KeyError("scenario vanished")
    pending = {"decision_id": "d", "intent_label": "direct_address_to_person",
               "scenarios_used": [1], "user_text": "x",
               "persons_in_room": [], "system_name": "Kara"}
    out = await cg.handle_correction(
        "hmm ok", pending_outcome=pending, classifier_db=fake_db, system_name="Kara")
    assert out["scenarios_decremented"] == 0


async def test_handle_correction_pops_pending_from_queue(fresh_db):
    # lines 663-664 (latest_pending lookup) + 699-702 (pop matching entry)
    sid = fresh_db.insert_scenario(
        abstract_text="x", intent_label="direct_address_to_person",
        embedding=_vec(41), source_tag="test", source_version="v1",
    )
    cg._classifier_db = fresh_db
    did = cg.record_pending_outcome(
        {"turn_intent": "direct_address_to_person",
         "__usage": {"graph_decision": True, "winning_voter_ids": [sid]}}, "x")
    out = await cg.handle_correction(
        "hmm ok", pending_outcome=None, classifier_db=fresh_db, system_name="Kara")
    assert out["scenarios_decremented"] == 1
    assert cg._find_pending(did) is None


async def test_handle_correction_embed_agent_unavailable(fresh_db, monkeypatch):
    # lines 730-732: target extracted but no embedder -> skipped
    monkeypatch.setattr(cg, "_get_embedding_agent", lambda: None)
    pending = {"decision_id": "d", "intent_label": "x", "scenarios_used": [],
               "user_text": "Get me chips", "persons_in_room": [], "system_name": "Kara"}
    out = await cg.handle_correction(
        "No Kara, I was talking to Lexi.", pending_outcome=pending,
        classifier_db=fresh_db, system_name="Kara")
    assert out["target_extracted"] == "Lexi"
    assert out["skipped_reason"] == "embedding_agent_unavailable"


async def test_handle_correction_embed_raises(fresh_db, capsys):
    # lines 734-739: correction embed raises -> skipped
    _install_agent(embed_side_effect=RuntimeError("embed boom"))
    pending = {"decision_id": "d", "intent_label": "x", "scenarios_used": [],
               "user_text": "Get me chips", "persons_in_room": [], "system_name": "Kara"}
    out = await cg.handle_correction(
        "No Kara, I was talking to Lexi.", pending_outcome=pending,
        classifier_db=fresh_db, system_name="Kara")
    assert out["skipped_reason"] == "embedding_failed"
    assert "correction embed failed" in capsys.readouterr().out


async def test_handle_correction_embed_returns_none(fresh_db):
    # lines 740-742: correction embed returns None -> skipped
    _install_agent(embed_result=None)
    pending = {"decision_id": "d", "intent_label": "x", "scenarios_used": [],
               "user_text": "Get me chips", "persons_in_room": [], "system_name": "Kara"}
    out = await cg.handle_correction(
        "No Kara, I was talking to Lexi.", pending_outcome=pending,
        classifier_db=fresh_db, system_name="Kara")
    assert out["skipped_reason"] == "embedding_returned_none"


async def test_handle_correction_insert_raises(fresh_db, monkeypatch, capsys):
    # lines 756-758: insert_scenario raises -> skipped, logged
    _install_agent(embed_result=_vec(42).tolist())
    monkeypatch.setattr(fresh_db, "insert_scenario",
                        MagicMock(side_effect=RuntimeError("insert boom")))
    pending = {"decision_id": "d", "intent_label": "x", "scenarios_used": [],
               "user_text": "Get me chips", "persons_in_room": [], "system_name": "Kara"}
    out = await cg.handle_correction(
        "No Kara, I was talking to Lexi.", pending_outcome=pending,
        classifier_db=fresh_db, system_name="Kara")
    assert out["skipped_reason"] == "insert_failed"
    assert "correction insert failed" in capsys.readouterr().out


# ── get_session_summary ─────────────────────────────────────────────────────


def test_get_session_summary_formats_counts():
    # lines 778-786: one-line summary carrying every counter
    cg._session_classifications = 7
    cg._session_shadow_divergences = 2
    cg._session_corrections = 3
    cg._session_new_scenarios = 1
    cg._session_confirmed = 5
    cg._session_reverted = 4
    s = cg.get_session_summary()
    assert "7 classifications" in s
    assert "2 shadow divergences" in s
    assert "3 corrections logged" in s
    assert "1 new scenarios inserted" in s
    assert "5 confirmed" in s
    assert "4 reverted" in s


# ── checkpoint_wal_singleton ────────────────────────────────────────────────


def test_checkpoint_wal_singleton_with_db():
    # lines 796-797: db open -> delegate to checkpoint_wal
    fake = MagicMock()
    cg._classifier_db = fake
    cg.checkpoint_wal_singleton()
    fake.checkpoint_wal.assert_called_once()


def test_checkpoint_wal_singleton_no_db():
    # line 796 (False side): db never opened -> no-op, no error
    cg._classifier_db = None
    cg.checkpoint_wal_singleton()


# ── aclose ──────────────────────────────────────────────────────────────────


async def test_aclose_closes_http_and_db():
    # lines 804-806, 809-813: close http client + db, reset all singletons
    http = AsyncMock()
    cg._http_client = http
    cg._embedding_agent = MagicMock()
    db = MagicMock()
    cg._classifier_db = db
    await cg.aclose()
    http.aclose.assert_awaited_once()
    db.close.assert_called_once()
    assert cg._http_client is None
    assert cg._embedding_agent is None
    assert cg._classifier_db is None


async def test_aclose_swallows_http_close_error():
    # lines 807-808: http aclose raises -> swallowed, still reset to None
    http = AsyncMock()
    http.aclose = AsyncMock(side_effect=RuntimeError("already closed"))
    cg._http_client = http
    await cg.aclose()
    assert cg._http_client is None


async def test_aclose_noop_when_nothing_open():
    # line 804 (False) + 811 (False): nothing open -> clean no-op
    cg._http_client = None
    cg._embedding_agent = None
    cg._classifier_db = None
    await cg.aclose()
