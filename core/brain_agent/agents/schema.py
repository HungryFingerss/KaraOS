"""core/brain_agent/agents/schema.py — SchemaNormAgent + _distinct_schema_families.

Extracted VERBATIM from core/brain_agent.py (P1.A1 SP-2 Commit 4).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import time
from rapidfuzz import fuzz as _rfuzz
import numpy as np

from core.config import (
    SCHEMA_NORM_AMBIGUOUS,
    SCHEMA_NORM_DISTINCT_FAMILIES,
    SCHEMA_NORM_THRESHOLD,
    SCHEMA_NORM_TRIGGER,
)
from core.brain_agent.context import _cosine_similarity_matrix


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
