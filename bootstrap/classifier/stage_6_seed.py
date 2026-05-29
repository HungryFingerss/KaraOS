"""Stage 6 -- Combine corpus-derived + hand-authored scenarios into seed JSONL.

Reads:
  - bootstrap/classifier/cache/embedded_samples.jsonl (from stage_5)
  - HAND_AUTHORED_SCENARIOS from hand_authored_scenarios.py
Writes:
  - data/classifier_scenarios_seed.jsonl

Hand-authored scenarios get embedded inline (re-uses the same E5 batch
embedder used in stage_5). Source tags stamped:
  source_tag = "hand_authored"
  source_version = SOURCE_VERSION (from hand_authored_scenarios.py)
  initial_confidence = each scenario's hard-coded value (0.85-0.95)

Corpus-derived scenarios pass through with:
  initial_confidence = 0.6 (medium -- they came from 70B classification, not human)
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import asyncio
import base64
import json
import sys
from pathlib import Path

from core.config import CLASSIFIER_SEED_PATH

CACHE_DIR = Path(__file__).parent / "cache"
EMBEDDED_PATH = CACHE_DIR / "embedded_samples.jsonl"

CORPUS_DEFAULT_CONFIDENCE = 0.6


async def _embed_hand_authored() -> list[dict]:
    """Embed each HAND_AUTHORED_SCENARIO and return rows ready for the seed."""
    from bootstrap.classifier.hand_authored_scenarios import (
        HAND_AUTHORED_SCENARIOS, SOURCE_VERSION,
    )
    from bootstrap.classifier.stage_5_embed import _embed_batch, _b64_encode, EMBEDDING_MODEL_ID

    texts = [s["abstract_text"] for s in HAND_AUTHORED_SCENARIOS]
    print(f"[stage_6_seed] embedding {len(texts)} hand-authored scenarios...")
    vecs = await _embed_batch(texts)
    if vecs is None:
        raise RuntimeError("hand-authored embedding failed -- check TOGETHER_API_KEY")
    out: list[dict] = []
    for scenario, vec in zip(HAND_AUTHORED_SCENARIOS, vecs):
        out.append({
            "abstract_text":         scenario["abstract_text"],
            "intent_label":          scenario["intent_label"],
            "extracted_value":       scenario.get("extracted_value"),
            "confidence":            scenario.get("initial_confidence", 0.9),
            "initial_confidence":    scenario.get("initial_confidence", 0.9),
            "embedding_b64":         _b64_encode(vec),
            "embedding_model_id":    EMBEDDING_MODEL_ID,
            "abstract_rule_version": 1,
            "source_tag":            "hand_authored",
            "source_version":        SOURCE_VERSION,
            "source_ref":            None,
        })
    return out


def _load_corpus_rows() -> list[dict]:
    if not EMBEDDED_PATH.exists():
        print(f"[stage_6_seed] {EMBEDDED_PATH} missing -- corpus path skipped")
        return []
    rows: list[dict] = []
    with EMBEDDED_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            # Default confidence for corpus rows
            rec.setdefault("initial_confidence", CORPUS_DEFAULT_CONFIDENCE)
            rows.append(rec)
    return rows


async def _run() -> int:
    corpus_rows = _load_corpus_rows()
    print(f"[stage_6_seed] corpus rows: {len(corpus_rows)}")

    try:
        hand_rows = await _embed_hand_authored()
    except Exception as e:
        print(f"[stage_6_seed] hand-authored embedding failed: {e!r}")
        return 1

    all_rows = corpus_rows + hand_rows
    if not all_rows:
        print("[stage_6_seed] no rows produced -- aborting")
        return 1

    out_path = Path(CLASSIFIER_SEED_PATH)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for row in all_rows:
            fh.write(json.dumps(row) + "\n")

    # Distribution check
    from collections import Counter
    by_source = Counter(r["source_tag"] for r in all_rows)
    by_intent = Counter(r["intent_label"] for r in all_rows)
    print(f"\n[stage_6_seed] wrote {len(all_rows)} rows -> {out_path}")
    print(f"  by source: {dict(by_source)}")
    print(f"  by intent: {dict(by_intent)}")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
