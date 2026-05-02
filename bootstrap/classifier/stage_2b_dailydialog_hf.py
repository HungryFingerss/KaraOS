"""Stage 2b -- DailyDialog top-up via HuggingFace `OpenRL/daily_dialog`.

The original yanran.li URL is dead (returned a 1.1KB error page during the
2026-04-27 bootstrap run, costing us ~400 expected DailyDialog samples).
This stage fills the gap by pulling DailyDialog from the HuggingFace
parquet mirror `OpenRL/daily_dialog` (CC-BY-NC-SA-4.0, same license as
the original).

Reads:
  HuggingFace `OpenRL/daily_dialog` train split (11,118 dialogues,
  each with a list of turns in the `dialog` field)
Appends to:
  bootstrap/classifier/cache/filtered_samples.jsonl

Same filter rules as stage_2: 3-50 word utterances, drop stage directions.
Source tag: "dailydialog", source_version: "dailydialog-hf-openrl-batch-001".

Idempotent: skips utterances whose source_ref is already in the cache.

Run: python -m bootstrap.classifier.stage_2b_dailydialog_hf
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "cache"
OUTPUT_PATH = CACHE_DIR / "filtered_samples.jsonl"

HF_REPO = "OpenRL/daily_dialog"
SOURCE_TAG = "dailydialog"
SOURCE_VERSION = "dailydialog-hf-openrl-batch-001"
SAMPLE_BUDGET = 400
MIN_WORDS = 3
MAX_WORDS = 50

_STAGE_DIRECTION_RE = re.compile(r"^\s*[\(\[\<].*[\)\]\>]\s*$")
_ARTIFACT_RE = re.compile(r"^[A-Z\s]{3,}:\s*$")


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text))


def _is_dialogue(text: str) -> bool:
    if not text or not text.strip():
        return False
    if _STAGE_DIRECTION_RE.match(text):
        return False
    if _ARTIFACT_RE.match(text):
        return False
    n = _word_count(text)
    return MIN_WORDS <= n <= MAX_WORDS


def _existing_refs() -> set[str]:
    if not OUTPUT_PATH.exists():
        return set()
    refs: set[str] = set()
    with OUTPUT_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ref = rec.get("source_ref")
            if ref:
                refs.add(ref)
    return refs


def main() -> int:
    try:
        from datasets import load_dataset
    except ImportError:
        print("[stage_2b] HuggingFace `datasets` library not installed -- "
              "pip install datasets")
        return 2

    print(f"[stage_2b] loading {HF_REPO} (train split)...")
    try:
        ds = load_dataset(HF_REPO, split="train")
    except Exception as e:
        print(f"[stage_2b] HF load failed: {e!r}")
        return 1

    seen = _existing_refs()
    print(f"[stage_2b] {len(seen)} samples already in filtered_samples.jsonl")

    # Walk every dialogue/turn, build a candidate pool, then sample.
    candidates: list[dict] = []
    for dlg_id, row in enumerate(ds):
        turns = row.get("dialog") or []
        for turn_id, raw_turn in enumerate(turns):
            text = (raw_turn or "").strip()
            if not _is_dialogue(text):
                continue
            ref = f"hf={HF_REPO}|dialogue={dlg_id}|turn={turn_id}"
            if ref in seen:
                continue
            candidates.append({
                "raw_text":       text,
                "source_tag":     SOURCE_TAG,
                "source_version": SOURCE_VERSION,
                "source_ref":     ref,
            })
    print(f"[stage_2b] {len(candidates)} new candidates after filter")

    if not candidates:
        print("[stage_2b] nothing to add")
        return 0

    rng = random.Random(42)
    sample = candidates if len(candidates) <= SAMPLE_BUDGET else rng.sample(candidates, SAMPLE_BUDGET)
    with OUTPUT_PATH.open("a", encoding="utf-8") as fh:
        for s in sample:
            fh.write(json.dumps(s) + "\n")
    print(f"[stage_2b] appended {len(sample)} samples -> {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
