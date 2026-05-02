"""Stage 3 -- Classify filtered samples with the production 70B classifier.

Calls the same `_classify_intent()` from core.brain that production uses
on every gated turn. Same prompt, same JSON output, same parser. The
70B is the *teacher* here -- once the seed is built, the pure-graph
classifier (Spec 2) replaces it in the hot path.

Reads:  bootstrap/classifier/cache/filtered_samples.jsonl
Writes: bootstrap/classifier/cache/classified_samples.jsonl

Cost cap: $2.00 hard. Expected ~$1.05 over ~1700 samples.

Idempotent: skips samples already classified (tracked by source_ref).
Re-runs resume from where the previous run left off.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Load TOGETHER_API_KEY from dog-ai/.env when run as a bootstrap script.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

CACHE_DIR = Path(__file__).parent / "cache"
INPUT_PATH = CACHE_DIR / "filtered_samples.jsonl"
OUTPUT_PATH = CACHE_DIR / "classified_samples.jsonl"

# Cost / quality
COST_CAP_USD = 2.00
TOGETHER_70B_PRICE_PER_M = 0.88  # Llama-3.3-70B-Instruct-Turbo input+output blended estimate
MIN_CONFIDENCE = 0.6  # drop ambiguous classifications


def _estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """Rough blended-price cost estimate."""
    return (prompt_tokens + completion_tokens) * TOGETHER_70B_PRICE_PER_M / 1_000_000


def _load_existing() -> set[str]:
    """Return source_refs of already-classified samples."""
    if not OUTPUT_PATH.exists():
        return set()
    refs: set[str] = set()
    with OUTPUT_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ref = rec.get("source_ref")
            if ref:
                refs.add(ref)
    return refs


async def _classify_one(sample: dict) -> "dict | None":
    """Wrap _classify_intent so we can capture token usage."""
    # Lazy import -- bootstrap only; core.brain pulls in heavy modules at import.
    from core.brain import _classify_intent

    sidecar = await _classify_intent(sample["raw_text"], conversation_history=None)
    if sidecar is None:
        return None
    usage = sidecar.pop("__usage", {}) if isinstance(sidecar, dict) else {}
    return {
        "raw_text":          sample["raw_text"],
        "source_tag":        sample["source_tag"],
        "source_version":    sample["source_version"],
        "source_ref":        sample["source_ref"],
        "intent_label":      sidecar.get("turn_intent"),
        "extracted_value":   sidecar.get("extracted_value"),
        "confidence":        float(sidecar.get("confidence", 0.0)),
        "reasoning":         sidecar.get("reasoning", ""),
        "model_id":          "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "classified_at":     time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "_prompt_tokens":    int(usage.get("prompt_tokens") or 0),
        "_completion_tokens": int(usage.get("completion_tokens") or 0),
    }


async def _run() -> int:
    if not INPUT_PATH.exists():
        print(f"[stage_3_classify] missing {INPUT_PATH}; run stage_2_filter first")
        return 2

    api_key = os.getenv("TOGETHER_API_KEY") or os.getenv("CHAT_API_KEY")
    if not api_key:
        print("[stage_3_classify] TOGETHER_API_KEY (or CHAT_API_KEY) not set")
        return 2

    seen = _load_existing()
    print(f"[stage_3_classify] {len(seen)} already classified")

    samples: list[dict] = []
    with INPUT_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("source_ref") in seen:
                continue
            samples.append(rec)
    total = len(samples)
    print(f"[stage_3_classify] {total} new samples to classify (cap ${COST_CAP_USD:.2f})")

    cost = 0.0
    in_tokens = 0
    out_tokens = 0
    written = 0
    dropped_low_conf = 0

    with OUTPUT_PATH.open("a", encoding="utf-8") as out_fh:
        for idx, sample in enumerate(samples):
            try:
                result = await _classify_one(sample)
            except Exception as e:
                print(f"  [error] sample {idx}: {e!r}")
                continue
            if result is None:
                continue

            in_tokens  += result["_prompt_tokens"]
            out_tokens += result["_completion_tokens"]
            cost = _estimate_cost(in_tokens, out_tokens)

            if result["confidence"] < MIN_CONFIDENCE:
                dropped_low_conf += 1
                continue

            out_fh.write(json.dumps(result) + "\n")
            written += 1

            if (idx + 1) % 50 == 0 or idx == total - 1:
                out_fh.flush()
                print(f"  [{idx+1}/{total}] written={written} dropped={dropped_low_conf} "
                      f"cost=${cost:.4f}")

            if cost >= COST_CAP_USD:
                print(f"[stage_3_classify] cost cap ${COST_CAP_USD:.2f} reached -- stopping")
                break

    print(f"\n[stage_3_classify] done")
    print(f"  written:        {written}")
    print(f"  dropped (conf): {dropped_low_conf}")
    print(f"  prompt tokens:  {in_tokens:,}")
    print(f"  output tokens:  {out_tokens:,}")
    print(f"  est. cost:      ${cost:.4f}")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
