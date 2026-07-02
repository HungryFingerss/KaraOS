"""Stage 5 -- Embed abstracted scenarios via E5.

Uses the production embedding agent (`EmbeddingAgent` from
core.brain_agent -- same model: intfloat/multilingual-e5-large-instruct,
1024-dim float32, L2-normalized).

Reads:  bootstrap/classifier/cache/abstracted_samples.jsonl (or
        bootstrap/classifier/cache/hand_authored_with_metadata.jsonl
        if invoked via stage_6_seed)
Writes: bootstrap/classifier/cache/embedded_samples.jsonl
        (corpus-derived) AND embeds the hand-authored list in-memory
        when called via API.

Output JSONL row:
  {... existing fields ..., "embedding_b64": "<base64-encoded float32>",
   "embedding_model_id": "multilingual-e5-large-instruct-v1"}
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
from pathlib import Path

import httpx
import numpy as np

# Load TOGETHER_API_KEY from the repo-root .env when run as a bootstrap script.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

CACHE_DIR = Path(__file__).parent / "cache"
INPUT_PATH = CACHE_DIR / "abstracted_samples.jsonl"
OUTPUT_PATH = CACHE_DIR / "embedded_samples.jsonl"

EMBED_BATCH_SIZE = 32
EMBEDDING_MODEL_ID = "multilingual-e5-large-instruct-v1"


async def _embed_batch(texts: list[str]) -> "list[np.ndarray] | None":
    """Embed a batch via the production EmbeddingAgent. Returns a list
    of np.ndarray (float32, 1024-dim) parallel to `texts`, or None on
    failure. EmbeddingAgent reads its API key from core.brain_agent's
    EMBED_API_KEY module constant (sourced from TOGETHER_API_KEY env)."""
    from core.brain_agent import EmbeddingAgent, EMBED_API_KEY

    if not EMBED_API_KEY:
        print("[stage_5_embed] core.brain_agent.EMBED_API_KEY empty -- "
              "set TOGETHER_API_KEY in the repo-root .env")
        return None

    async with httpx.AsyncClient(timeout=60.0) as http:
        agent = EmbeddingAgent(http=http)
        vecs = await agent.embed_batch(texts, purpose="classifier scenario")
        if vecs is None:
            return None
        # embed_batch returns parallel list of list[float] | None — fail-fast
        # if any individual embed missed.
        out: list[np.ndarray] = []
        for vec in vecs:
            if vec is None:
                return None
            out.append(np.asarray(vec, dtype=np.float32))
        return out


def _b64_encode(vec: np.ndarray) -> str:
    return base64.b64encode(np.asarray(vec, dtype=np.float32).tobytes()).decode("ascii")


async def _run() -> int:
    if not INPUT_PATH.exists():
        print(f"[stage_5_embed] missing {INPUT_PATH}; run stage_4_abstract first")
        return 2

    rows: list[dict] = []
    with INPUT_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    print(f"[stage_5_embed] {len(rows)} rows to embed")

    written = 0
    with OUTPUT_PATH.open("w", encoding="utf-8") as out_fh:
        for i in range(0, len(rows), EMBED_BATCH_SIZE):
            batch = rows[i : i + EMBED_BATCH_SIZE]
            texts = [r["abstract_text"] for r in batch]
            vecs = await _embed_batch(texts)
            if vecs is None:
                print(f"  [error] embedding batch {i // EMBED_BATCH_SIZE} failed; aborting")
                return 1
            for rec, vec in zip(batch, vecs):
                rec["embedding_b64"] = _b64_encode(vec)
                rec["embedding_model_id"] = EMBEDDING_MODEL_ID
                out_fh.write(json.dumps(rec) + "\n")
                written += 1
            out_fh.flush()
            print(f"  [{i + len(batch)}/{len(rows)}] written={written}")

    print(f"[stage_5_embed] done -- wrote {written} -> {OUTPUT_PATH}")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
