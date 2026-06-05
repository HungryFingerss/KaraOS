"""core/brain_agent/agents/embedding.py — EmbeddingAgent.

Extracted VERBATIM from core/brain_agent.py (P1.A1 SP-2 Commit 4).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import asyncio
import httpx

from core.config import (
    EMBED_API_KEY,
    EMBED_BASE_URL,
    EMBED_MAX_RETRIES,
    EMBED_MODEL,
)


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
