"""core/brain_agent/context.py — context-assembly + cosine helpers.

Extracted VERBATIM from core/brain_agent.py (P1.A1 SP-2 Commit 2). Behavior-
neutral; core/brain_agent/__init__.py re-exports these symbols.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import math
import time

import numpy as np

from core.config import DECAY_LAMBDA, EMBED_MIN_CONFIDENCE


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
