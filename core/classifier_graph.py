"""
core/classifier_graph.py — Pure-graph intent classifier (Spec 2).

Replaces the LLM `_classify_intent` in production via a 3-stage rollout
(shadow → primary → retired). NO LLM call in the classification hot path,
correction-detection path, or outcome-supervision path.

Pipeline per turn:
  abstract -> embed (E5) -> k-NN over scenarios -> Wilson-weighted vote
  -> de-abstract -> intent sidecar dict (same shape as _classify_intent)

Online learning: when the classifier emits `correction_to_previous_response`
on turn N+1, `handle_correction` decrements the wrong-vote scenarios on
turn N's decision and (if regex extracts a target) inserts a new positive
scenario derived from N's user_text. Brain stays silent on corrections.

Module-level singletons (lazy-initialized):
  _classifier_db   — opens data/classifier_scenarios.db once
  _embedding_agent — re-uses the production E5 client
  _http_client     — single httpx.AsyncClient for embedding calls
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import asyncio
import os
import re
import time
import uuid
from collections import defaultdict, deque
from typing import Optional

import httpx
import numpy as np

from core.config import (
    CLASSIFIER_AUDIT_LOG_PATH,
    CLASSIFIER_DB_PATH,
    DEFAULT_SYSTEM_NAME,
    GRAPH_ABSTAIN_THRESHOLD,
    GRAPH_K_NEIGHBORS,
    GRAPH_LATENCY_BUDGET_MS,
    GRAPH_LOCAL_EMBEDDING_DEVICE,
    GRAPH_LOCAL_EMBEDDING_MODEL,
    GRAPH_OUTCOME_HOLDING_TURNS,
    GRAPH_USE_LOCAL_EMBEDDINGS,
    INTENT_LABELS,
)
from core.abstraction import abstract_text, deabstract
from core.classifier_db import ClassifierDB


# ── Module-level singletons ──────────────────────────────────────────────

_classifier_db: "ClassifierDB | None" = None
_embedding_agent = None
_http_client: "httpx.AsyncClient | None" = None

# 3-turn outcome supervision queue. Each entry: {decision_id, intent_label,
# scenarios_used, user_text, persons_in_room, system_name, ts, turns_aged}.
# Only populated for graph-driven decisions; LLM-only decisions in shadow
# mode never enter this queue.
_pending_outcomes: deque = deque(maxlen=10)

# ── Session-level event counters (S120 #6) ───────────────────────────────
# Incremented at event sites throughout this module; dumped at pipeline
# shutdown by get_session_summary(). Gives per-session visibility into
# classifier learning rate without relying on grep over logs.

_session_classifications: int = 0
_session_shadow_divergences: int = 0
_session_corrections: int = 0
_session_new_scenarios: int = 0
_session_confirmed: int = 0
_session_reverted: int = 0


def _get_db() -> "ClassifierDB | None":
    """Lazy ClassifierDB. Returns None if the DB file is missing — caller
    treats that as 'graph not bootstrapped, fall back'."""
    global _classifier_db
    if _classifier_db is not None:
        return _classifier_db
    try:
        override = os.environ.get("CLASSIFIER_DB_PATH_OVERRIDE")
        db_path = override if override else CLASSIFIER_DB_PATH
        if override:
            print(f"[classifier_graph] CLASSIFIER_DB_PATH_OVERRIDE active -> {db_path}")
        _classifier_db = ClassifierDB(
            db_path=db_path,
            audit_log_path=CLASSIFIER_AUDIT_LOG_PATH,
        )
        return _classifier_db
    except Exception as e:
        print(f"[classifier_graph] ClassifierDB open failed: {type(e).__name__}: {e!r}")
        return None


class LocalE5Embedder:
    """Local-only E5 embedder via HuggingFace Transformers.

    Lazy model load (first embed call), runs on CUDA if available,
    follows the E5 instruct prompt convention ("Instruction: represent
    the {purpose} for retrieval: {text}"), mean-pools last hidden states,
    L2-normalizes the output. Same interface as the network EmbeddingAgent
    so callers don't care which is in use.

    Closes the network-E5 latency gap (~400ms → ~30ms) for the graph
    classifier hot path.
    """

    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._device = None

    def _load(self):
        if self._model is not None:
            return
        import torch
        from transformers import AutoTokenizer, AutoModel
        if GRAPH_LOCAL_EMBEDDING_DEVICE == "cuda":
            device = "cuda"
        elif GRAPH_LOCAL_EMBEDDING_DEVICE == "cpu":
            device = "cpu"
        else:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[classifier_graph] loading local E5 ({GRAPH_LOCAL_EMBEDDING_MODEL}) on {device}...")
        t0 = time.perf_counter()
        self._tokenizer = AutoTokenizer.from_pretrained(GRAPH_LOCAL_EMBEDDING_MODEL)
        model = AutoModel.from_pretrained(GRAPH_LOCAL_EMBEDDING_MODEL)
        model.eval()
        if device == "cuda":
            model = model.cuda()
        self._model = model
        self._device = device
        elapsed = time.perf_counter() - t0
        print(f"[classifier_graph] local E5 loaded ({elapsed:.1f}s on {device})")

    def _encode_sync(self, text: str) -> "list[float] | None":
        import torch
        try:
            self._load()
        except Exception as e:
            print(f"[classifier_graph] local E5 load failed: {type(e).__name__}: {e!r}")
            return None
        try:
            tokens = self._tokenizer(
                text, padding=True, truncation=True, max_length=512,
                return_tensors="pt",
            )
            if self._device == "cuda":
                tokens = {k: v.cuda() for k, v in tokens.items()}
            with torch.no_grad():
                outputs = self._model(**tokens)
            # Average-pool the last hidden states (E5 docs)
            last_hidden = outputs.last_hidden_state
            mask = tokens["attention_mask"].unsqueeze(-1).float()
            pooled = (last_hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
            # L2 normalize (same as Together.ai E5 endpoint output)
            normalized = torch.nn.functional.normalize(pooled, p=2, dim=1)
            return normalized[0].cpu().tolist()
        except Exception as e:
            print(f"[classifier_graph] local E5 encode failed: {type(e).__name__}: {e!r}")
            return None

    async def embed(self, text: str, purpose: str = "knowledge fact") -> "list[float] | None":
        """Same signature as core.brain_agent.EmbeddingAgent.embed."""
        instruction = f"Instruction: represent the {purpose} for retrieval: {text}"
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._encode_sync, instruction)

    async def embed_batch(
        self, texts: list[str], purpose: str = "knowledge fact"
    ) -> "list[list[float] | None]":
        """Mirrors EmbeddingAgent.embed_batch but does so sequentially in
        the executor (one tokenize + one forward per text). For Spec 2's
        per-turn use case (1 text per call) the batch API is rarely hot."""
        return [await self.embed(t, purpose=purpose) for t in texts]


# Lazy singleton for the local embedder
_local_e5: "LocalE5Embedder | None" = None


def _get_embedding_agent():
    """Lazy embedder. Prefers local E5 when GRAPH_USE_LOCAL_EMBEDDINGS is
    enabled; falls back to the network EmbeddingAgent otherwise.

    Local mode is the production-recommended path (Spec 2 latency target)
    once the model is downloaded. Network mode kept as a fallback for
    environments without enough disk/memory for the ~2.3GB E5 model.
    """
    global _embedding_agent, _http_client, _local_e5

    if GRAPH_USE_LOCAL_EMBEDDINGS:
        if _local_e5 is None:
            _local_e5 = LocalE5Embedder()
        return _local_e5

    # Network fallback
    if _embedding_agent is not None:
        return _embedding_agent
    try:
        from core.brain_agent import EmbeddingAgent, EMBED_API_KEY
    except Exception as e:
        print(f"[classifier_graph] EmbeddingAgent import failed: {e!r}")
        return None
    if not EMBED_API_KEY:
        print("[classifier_graph] EMBED_API_KEY empty — graph classifier disabled")
        return None
    _http_client = httpx.AsyncClient(timeout=30.0)
    _embedding_agent = EmbeddingAgent(http=_http_client)
    return _embedding_agent


# ── Wilson lower-bound confidence ────────────────────────────────────────

def confidence_score(scenario: dict) -> float:
    """Map a scenario's outcome counts to a [0, 1] weight.

    Initial bias decays as outcome data accumulates. Wilson lower-bound
    (95% CI) on confirmation rate ensures a single confirmation doesn't
    get full credit — needs accumulating evidence to climb. Prevents
    single-correction events from over-skewing the graph.
    """
    confirmed = int(scenario.get("outcome_confirmed") or 0)
    reverted = int(scenario.get("outcome_reverted") or 0)
    initial = float(scenario.get("initial_confidence") or 0.5)
    n = confirmed + reverted
    if n == 0:
        return initial
    p = confirmed / n
    z = 1.96  # 95% confidence
    denom = 1.0 + z * z / n
    center = p + z * z / (2.0 * n)
    margin = z * ((p * (1.0 - p) + z * z / (4.0 * n)) / n) ** 0.5
    return max(0.0, (center - margin) / denom)


# ── Vote aggregation ─────────────────────────────────────────────────────

def _aggregate_votes(neighbors: list[dict]) -> tuple[str, float, dict, dict]:
    """Group neighbors by intent_label, sum (cosine_sim * Wilson weight).

    Returns (winning_label, confidence, per_label_weights, top_voters_per_label).
    `confidence` is winning_weight / total_weight (post-clamp); used as the
    abstain gate.
    """
    label_weights: dict[str, float] = defaultdict(float)
    label_voters: dict[str, list[dict]] = defaultdict(list)
    total_weight = 0.0
    for n in neighbors:
        label = n.get("intent_label") or "unclear"
        sim = float(n.get("similarity") or 0.0)
        w_score = confidence_score(n)
        # Clamp similarity to [0, 1] (cosine can be slightly negative on
        # near-orthogonal vectors; treat that as zero contribution).
        sim = max(0.0, sim)
        weight = sim * w_score
        if weight <= 0:
            continue
        label_weights[label] += weight
        label_voters[label].append(n)
        total_weight += weight

    if not label_weights or total_weight <= 0:
        return ("unclear", 0.0, {}, {})

    # Pick highest weight; on ties, prefer the label with highest mean
    # Wilson confidence among its voters (per spec test_aggregate_handles_tied_labels).
    sorted_labels = sorted(
        label_weights.items(),
        key=lambda kv: (
            kv[1],
            sum(confidence_score(n) for n in label_voters[kv[0]]) / max(1, len(label_voters[kv[0]])),
        ),
        reverse=True,
    )
    winning_label, winning_weight = sorted_labels[0]
    confidence = winning_weight / total_weight if total_weight > 0 else 0.0
    return winning_label, confidence, dict(label_weights), dict(label_voters)


# ── Public classifier API ────────────────────────────────────────────────

async def classify_intent_graph(
    user_text: str,
    *,
    conversation_history: "list[dict] | None" = None,
    persons_in_room: "list[str] | None" = None,
    system_name: str = DEFAULT_SYSTEM_NAME,
) -> "dict | None":
    """Pure-graph intent classifier. NO LLM call in this code path.

    Returns the same shape as core.brain._classify_intent, plus a
    `__usage` dict carrying graph-equivalent of LLM token usage so
    Phase 5 telemetry sees a uniform interface. Returns None when the
    graph is empty, embedding fails, or the winning weight falls below
    GRAPH_ABSTAIN_THRESHOLD (defensive abstain — caller falls back to
    LLM in primary mode, or to default-silent in retired mode).
    """
    if not user_text or not user_text.strip():
        return None

    db = _get_db()
    if db is None or db.count_scenarios(active_only=True) == 0:
        return None

    agent = _get_embedding_agent()
    if agent is None:
        return None

    # ── 1. Abstract ──────────────────────────────────────────────────────
    t_abs_start = time.perf_counter()
    abs_text, mapping = abstract_text(
        user_text,
        persons_in_room=persons_in_room,
        system_name=system_name,
    )
    abstraction_ms = int((time.perf_counter() - t_abs_start) * 1000)

    # ── 2. Embed ─────────────────────────────────────────────────────────
    t_emb_start = time.perf_counter()
    try:
        vec = await agent.embed(abs_text, purpose="classifier scenario")
    except Exception as e:
        print(f"[classifier_graph] embed failed: {type(e).__name__}: {e!r}")
        return None
    if vec is None:
        return None
    embedding_ms = int((time.perf_counter() - t_emb_start) * 1000)
    query = np.asarray(vec, dtype=np.float32)

    # ── 3. Query graph ───────────────────────────────────────────────────
    t_q_start = time.perf_counter()
    try:
        neighbors = db.query_nearest(query, k=GRAPH_K_NEIGHBORS, active_only=True)
    except Exception as e:
        print(f"[classifier_graph] query failed: {type(e).__name__}: {e!r}")
        return None
    graph_query_ms = int((time.perf_counter() - t_q_start) * 1000)

    if not neighbors:
        return None

    # ── 4. Aggregate ─────────────────────────────────────────────────────
    winning_label, confidence, label_weights, label_voters = _aggregate_votes(neighbors)
    if confidence < GRAPH_ABSTAIN_THRESHOLD:
        # Latency log even on abstain — we still spent the budget
        _maybe_warn_latency(abstraction_ms + embedding_ms + graph_query_ms, user_text)
        return None

    # Resolve through label_evolution (in case the seed has deprecated labels).
    winning_label = db.resolve_label(winning_label)
    if winning_label not in INTENT_LABELS:
        # Defensive — shouldn't happen unless graph carries labels we've
        # since removed without adding label_evolution rows.
        print(f"[classifier_graph] winning label {winning_label!r} not in INTENT_LABELS; abstaining")
        return None

    # ── 5. De-abstract extracted_value ───────────────────────────────────
    extracted_value: "str | None" = None
    voters = label_voters.get(winning_label, [])
    if voters:
        # Use the top-similarity voter's stored extracted_value
        top = max(voters, key=lambda n: float(n.get("similarity") or 0.0))
        raw_ev = top.get("extracted_value")
        if raw_ev:
            # Substitute placeholders back via mapping. If no mapping match,
            # leave as-is (defensive — production caller can decide).
            extracted_value = deabstract(raw_ev, mapping)

    # ── 6. Build sidecar ─────────────────────────────────────────────────
    total_ms = abstraction_ms + embedding_ms + graph_query_ms
    _maybe_warn_latency(total_ms, user_text)
    reasoning = _format_reasoning(winning_label, label_weights, voters[:3])
    winning_voter_ids = [
        int(v["scenario_id"])
        for v in voters
        if v.get("scenario_id") is not None
    ]
    global _session_classifications
    _session_classifications += 1
    return {
        "turn_intent":     winning_label,
        "extracted_value": extracted_value,
        "confidence":      float(confidence),
        "reasoning":       reasoning,
        "__usage": {
            "k_neighbors_queried": len(neighbors),
            "scenarios_voted":     sum(len(v) for v in label_voters.values()),
            "winning_voter_ids":   winning_voter_ids,
            "abstraction_ms":      abstraction_ms,
            "embedding_ms":        embedding_ms,
            "graph_query_ms":      graph_query_ms,
            "graph_decision":      True,  # marker so pipeline knows it can record outcome supervision
        },
    }


def _format_reasoning(label: str, weights: dict, top_voters: list[dict]) -> str:
    """Human-readable diagnostic for logs / debugging. Lists the top
    contributing scenarios and their similarities."""
    if not top_voters:
        return f"graph: {label} (no voters)"
    parts = [f"graph: {label} (label_weights={ {k: round(v, 3) for k, v in weights.items()} })"]
    for v in top_voters:
        sim = float(v.get("similarity") or 0.0)
        parts.append(
            f"  • sim={sim:.3f} '{(v.get('abstract_text') or '')[:60]}' "
            f"({v.get('intent_label')})"
        )
    return "\n".join(parts)


def _maybe_warn_latency(total_ms: int, user_text: str) -> None:
    """Log a warning if a single classify call exceeded the budget. Used
    by Phase 5 drift detection — climbing latency means embedding/spacy
    needs profiling."""
    if total_ms > GRAPH_LATENCY_BUDGET_MS:
        snip = (user_text or "")[:60]
        print(f"[classifier_graph] latency {total_ms}ms > {GRAPH_LATENCY_BUDGET_MS}ms budget on '{snip}'")


# ── Correction loop ──────────────────────────────────────────────────────

# Regex bank for extracting the corrected target from a user correction.
# `{system}` placeholder is filled at compile time when the patterns are
# rebuilt for a different system_name. v1: ~10 patterns covering the
# common phrasings.
_DEFAULT_CORRECTION_PATTERNS_TEMPLATE: list[str] = [
    r"no\s+{system},?\s+i\s+(?:was\s+)?talking\s+to\s+([\w]+)",
    r"no,?\s+i\s+(?:was\s+)?talking\s+to\s+([\w]+)",
    r"no,?\s+i\s+(?:was\s+)?telling\s+([\w]+)",
    r"i\s+(?:was\s+)?addressing\s+([\w]+),?\s+not\s+you",
    r"i\s+meant\s+([\w]+),?\s+not\s+you",
    r"shh,?\s+i'?m?\s+talking\s+to\s+([\w]+)",
    r"that\s+(?:was|wasn'?t)\s+for\s+([\w]+)",
    r"don'?t\s+answer\s+{system},?\s+i\s+(?:was\s+)?(?:telling|talking\s+to)\s+([\w]+)",
    r"{system},?\s+ignore\s+that\s+--?\s*it\s+was\s+for\s+([\w]+)",
    r"i'?m\s+asking\s+([\w]+),?\s+not\s+you",
    # Null-target patterns — correction without a target name. The handler
    # recognizes these as decrement-only signals.
    r"no\s+{system},?\s+i\s+wasn'?t\s+talking\s+to\s+you",
    r"stop\s+{system},?\s+that\s+wasn'?t\s+for\s+you",
    r"{system},?\s+that\s+wasn'?t\s+for\s+you",
    r"not\s+you,?\s+{system}",
]


def _compile_correction_patterns(system_name: str) -> list[re.Pattern]:
    """Compile correction regexes with {system} substituted to the
    actual system name. Always lives at module scope; do not instantiate
    per-call (re.compile is the slow step)."""
    sys_re = re.escape(system_name)
    return [
        re.compile(t.replace("{system}", sys_re), re.IGNORECASE)
        for t in _DEFAULT_CORRECTION_PATTERNS_TEMPLATE
    ]


# Cache compiled patterns by system_name so we don't recompile every call.
_compiled_patterns_cache: dict[str, list[re.Pattern]] = {}


def _get_correction_patterns(system_name: str) -> list[re.Pattern]:
    if system_name not in _compiled_patterns_cache:
        _compiled_patterns_cache[system_name] = _compile_correction_patterns(system_name)
    return _compiled_patterns_cache[system_name]


def extract_correction_target(text: str, system_name: str = DEFAULT_SYSTEM_NAME) -> "str | None":
    """Try each correction pattern. Return the first captured target name,
    or None if no pattern matches OR the matched pattern has no capture
    group (target-less correction — caller treats that as decrement-only).

    Captures of literal "you" are filtered out — they mean the correction
    was directed AT the AI ("that was for you" / "that wasn't for you")
    not at a third party. Caller treats that as decrement-only.
    """
    if not text:
        return None
    for pattern in _get_correction_patterns(system_name):
        m = pattern.search(text)
        if m is None:
            continue
        # Patterns without capture groups (target-less) intentionally return
        # None; the handler still decrements wrong-vote scenarios.
        if pattern.groups == 0:
            return None
        try:
            captured = m.group(1)
        except IndexError:
            return None
        if not captured or captured.lower() in {"you", "me", "myself"}:
            # Pronoun captured — not a real third-party target. Continue
            # scanning subsequent patterns in case a later one matches a
            # real name; if none do, fall through to None.
            continue
        return captured
    return None


# ── Outcome supervision queue (3-turn holding window) ───────────────────

def record_pending_outcome(
    sidecar: dict,
    user_text: str,
    *,
    persons_in_room: "list[str] | None" = None,
    system_name: str = DEFAULT_SYSTEM_NAME,
) -> str:
    """Push a graph-classifier decision onto the pending queue. Returns
    the minted `decision_id`. No-op + returns empty string if the sidecar
    isn't a graph decision (LLM sidecar from shadow mode)."""
    usage = (sidecar or {}).get("__usage") or {}
    if not usage.get("graph_decision"):
        return ""
    decision_id = uuid.uuid4().hex
    _pending_outcomes.append({
        "decision_id":     decision_id,
        "intent_label":    sidecar.get("turn_intent"),
        "scenarios_used":  list(usage.get("winning_voter_ids") or []),
        "user_text":       user_text,
        "persons_in_room": list(persons_in_room or []),
        "system_name":     system_name,
        "ts":              time.time(),
        "turns_aged":      0,
    })
    return decision_id


def _find_pending(decision_id: str) -> "tuple[int, dict] | None":
    """Locate a pending outcome by decision_id. Returns (index, entry) or
    None if not present."""
    for idx, entry in enumerate(_pending_outcomes):
        if entry.get("decision_id") == decision_id:
            return idx, entry
    return None


def confirm_pending(decision_id: str, reason: str = "") -> int:
    """Credit `outcome_confirmed` to every scenario that voted for the
    winning label of the matching pending entry. Returns count of
    scenarios credited. Pops the entry from the queue."""
    found = _find_pending(decision_id)
    if found is None:
        return 0
    idx, entry = found
    db = _get_db()
    if db is None:
        del _pending_outcomes[idx]
        return 0
    credited = 0
    for sid in entry.get("scenarios_used") or []:
        try:
            db.increment_outcome(sid, kind="confirmed",
                                 decision_id=decision_id,
                                 reason=reason or "tool_fire_or_silence")
            credited += 1
        except KeyError:
            pass
    global _session_confirmed
    _session_confirmed += credited
    del _pending_outcomes[idx]
    return credited


def revert_pending(decision_id: str, reason: str = "") -> int:
    """Increment `outcome_reverted` for the matching pending entry. Pops."""
    found = _find_pending(decision_id)
    if found is None:
        return 0
    idx, entry = found
    db = _get_db()
    if db is None:
        del _pending_outcomes[idx]
        return 0
    reverted = 0
    for sid in entry.get("scenarios_used") or []:
        try:
            db.increment_outcome(sid, kind="reverted",
                                 decision_id=decision_id,
                                 reason=reason or "gate_rejection_or_correction")
            reverted += 1
        except KeyError:
            pass
    global _session_reverted
    _session_reverted += reverted
    del _pending_outcomes[idx]
    return reverted


def age_pending_outcomes() -> int:
    """Bump `turns_aged` on every queue entry; entries reaching the
    holding-window threshold get auto-credited as confirmed (silence is
    consent). Returns count of auto-credited entries.

    Call once per conversation turn, BEFORE any new pending outcome is
    pushed onto the queue."""
    aged_out: list[str] = []
    for entry in _pending_outcomes:
        entry["turns_aged"] = int(entry.get("turns_aged") or 0) + 1
        if entry["turns_aged"] >= GRAPH_OUTCOME_HOLDING_TURNS:
            aged_out.append(entry["decision_id"])
    credited = 0
    for did in aged_out:
        credited += confirm_pending(did, reason="silence_is_consent")
    return credited


def latest_pending() -> "dict | None":
    """Return the most recently pushed pending entry (deepest in the deque),
    or None if empty. Used by the correction handler to find the previous
    turn's decision."""
    if not _pending_outcomes:
        return None
    return _pending_outcomes[-1]


def reset_pending_outcomes() -> None:
    """Clear the queue. Test-helper + factory-reset hook — not used in
    production hot path."""
    _pending_outcomes.clear()


# ── Correction loop ──────────────────────────────────────────────────────

async def handle_correction(
    correction_text: str,
    pending_outcome: "dict | None" = None,
    *,
    classifier_db: "ClassifierDB | None" = None,
    system_name: str = DEFAULT_SYSTEM_NAME,
) -> dict:
    """Apply outcome supervision on a user correction.

    `pending_outcome` is the previous turn's record (decision_id,
    scenarios_used, intent_label, user_text, persons_in_room, system_name).
    Returns a summary dict for logging:
        {
            "scenarios_decremented": int,
            "target_extracted": str | None,
            "new_scenario_id": int | None,
            "skipped_reason": str | None,   # populated when nothing happened
        }

    Hard rule: NO LLM call in this function.
    """
    out: dict = {
        "scenarios_decremented": 0,
        "target_extracted":      None,
        "new_scenario_id":       None,
        "skipped_reason":        None,
    }

    # Production callers pass `pending_outcome=None` and expect the
    # handler to look up the deepest pending entry from the queue.
    if pending_outcome is None:
        pending_outcome = latest_pending()
    if pending_outcome is None:
        out["skipped_reason"] = "no_pending_outcome"
        return out

    db = classifier_db if classifier_db is not None else _get_db()
    if db is None:
        out["skipped_reason"] = "classifier_db_unavailable"
        return out

    decision_id = pending_outcome.get("decision_id")
    wrong_label = pending_outcome.get("intent_label")

    # ── 1. Decrement wrong-vote scenarios ────────────────────────────────
    decremented = 0
    for sid in pending_outcome.get("scenarios_used") or []:
        scen = db.get_scenario(sid)
        if scen is None:
            continue
        # Only decrement scenarios that voted for the same wrong label;
        # other-label voters from the original k-NN pool aren't responsible.
        if scen.get("intent_label") == wrong_label:
            try:
                db.increment_outcome(
                    sid, kind="reverted",
                    decision_id=decision_id,
                    reason="user_correction",
                )
                decremented += 1
            except KeyError:
                pass
    out["scenarios_decremented"] = decremented
    # Pop the pending entry from the queue so subsequent corrections /
    # confirmations can't double-credit it. Safe even if pending_outcome
    # was passed explicitly by a test (it just wasn't in the queue).
    if decision_id:
        found = _find_pending(decision_id)
        if found is not None:
            del _pending_outcomes[found[0]]

    # ── 2. Extract corrected target (regex) ──────────────────────────────
    target = extract_correction_target(correction_text, system_name=system_name)
    out["target_extracted"] = target

    # ── 3. If target found, write a new positive scenario ────────────────
    if target:
        prev_text = pending_outcome.get("user_text") or ""
        prev_persons = pending_outcome.get("persons_in_room") or []
        prev_system = pending_outcome.get("system_name") or system_name
        # Re-abstract the previous turn so the new scenario is in graph form.
        # Include the corrected target in persons_in_room so it gets a
        # placeholder (target may not have been visible to the original
        # abstraction pass).
        if target not in prev_persons:
            prev_persons = list(prev_persons) + [target]
        abs_prev, mapping_prev = abstract_text(
            prev_text,
            persons_in_room=prev_persons,
            system_name=prev_system,
        )
        # Find the placeholder for the corrected target
        target_placeholder: "str | None" = next(
            (ph for ph, orig in mapping_prev.items() if orig == target),
            None,
        )
        # Embed the abstracted previous turn
        agent = _get_embedding_agent()
        if agent is None:
            out["skipped_reason"] = "embedding_agent_unavailable"
            return out
        try:
            vec = await agent.embed(abs_prev, purpose="classifier correction")
        except Exception as e:
            print(f"[classifier_graph] correction embed failed: {type(e).__name__}: {e!r}")
            out["skipped_reason"] = "embedding_failed"
            return out
        if vec is None:
            out["skipped_reason"] = "embedding_returned_none"
            return out
        try:
            new_sid = db.insert_scenario(
                abstract_text=abs_prev,
                intent_label="direct_address_to_person",
                embedding=np.asarray(vec, dtype=np.float32),
                source_tag="live_correction",
                source_version="v1",
                source_ref=decision_id,
                initial_confidence=0.85,  # high — explicit user signal
                extracted_value=target_placeholder or target,
                skip_if_duplicate=True,
            )
            out["new_scenario_id"] = new_sid
        except Exception as e:
            print(f"[classifier_graph] correction insert failed: {type(e).__name__}: {e!r}")
            out["skipped_reason"] = "insert_failed"

    global _session_corrections, _session_new_scenarios
    if out.get("scenarios_decremented", 0) > 0 or out.get("new_scenario_id") is not None:
        _session_corrections += 1
    if out.get("new_scenario_id") is not None:
        _session_new_scenarios += 1

    return out


# ── Session summary (S120 #6) ─────────────────────────────────────────────

def get_session_summary() -> str:
    """Return a one-line session summary string for shutdown logging.

    Format matches the spec from info.md:
      [classifier_graph] session summary: N classifications, M shadow divergences,
      K corrections logged, J new scenarios inserted, P confirmed, Q reverted
    """
    return (
        f"[classifier_graph] session summary: "
        f"{_session_classifications} classifications, "
        f"{_session_shadow_divergences} shadow divergences, "
        f"{_session_corrections} corrections logged, "
        f"{_session_new_scenarios} new scenarios inserted, "
        f"{_session_confirmed} confirmed, "
        f"{_session_reverted} reverted"
    )


# ── Lifecycle ────────────────────────────────────────────────────────────

def checkpoint_wal_singleton() -> None:
    """Flush the ClassifierDB singleton's WAL if it is open.

    Called from the pipeline's dream loop. No-op when the DB has never been
    opened (graph not bootstrapped) or has already been closed."""
    if _classifier_db is not None:
        _classifier_db.checkpoint_wal()


async def aclose() -> None:
    """Close module-level singletons. Call from the pipeline's shutdown
    handler so the httpx client doesn't leave a warning at exit."""
    global _classifier_db, _embedding_agent, _http_client
    if _http_client is not None:
        try:
            await _http_client.aclose()
        except Exception:
            pass  # CLEANUP: httpx client may already be closed or never opened
        _http_client = None
    _embedding_agent = None
    if _classifier_db is not None:
        _classifier_db.close()
        _classifier_db = None
