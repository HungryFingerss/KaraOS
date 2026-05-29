"""Stage 2 -- Filter relevant utterances from acquired corpora.

Reads the extracted corpora from Stage 1 and emits one record per kept
utterance to filtered_samples.jsonl.

Filter rules (per spec):
  - 3 ≤ word_count ≤ 50
  - drop pure stage directions / non-dialogue artifacts
  - prefer multi-character scenes (more multi-party signal)
  - stratify: ~1000 cornell + ~400 dailydialog + ~300 empathetic

Idempotent: skips if filtered_samples.jsonl already exists. Delete the
file to re-run.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "cache"
OUTPUT_PATH = CACHE_DIR / "filtered_samples.jsonl"

# Per-corpus sample budgets (per spec)
BUDGETS = {
    "cornell":     1000,
    "dailydialog":  400,
    "empathetic":   300,
}

MIN_WORDS = 3
MAX_WORDS = 50

# Stage-direction / artifact patterns. Conservative -- false-positives are
# fine here, we have plenty of utterances to choose from.
_STAGE_DIRECTION_RE = re.compile(r"^\s*[\(\[\<].*[\)\]\>]\s*$")
_ARTIFACT_RE = re.compile(r"^[A-Z\s]{3,}:\s*$")  # bare speaker label


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


# ── Cornell parser ───────────────────────────────────────────────────────

def _load_cornell() -> list[dict]:
    """Return list of {raw_text, source_ref} from Cornell movie lines."""
    base = CACHE_DIR / "cornell"
    # Cornell ZIP extracts to a nested dir; find the lines file.
    candidates = list(base.rglob("movie_lines.txt"))
    if not candidates:
        print(f"  [cornell] movie_lines.txt not found under {base}/ -- skipping")
        return []
    lines_file = candidates[0]
    out: list[dict] = []
    with lines_file.open("r", encoding="iso-8859-1", errors="ignore") as fh:
        for line in fh:
            parts = line.split(" +++$+++ ")
            if len(parts) < 5:
                continue
            line_id, _user, movie_id, _char, text = parts[0], parts[1], parts[2], parts[3], parts[4].strip()
            if not _is_dialogue(text):
                continue
            out.append({
                "raw_text":       text,
                "source_tag":     "cornell",
                "source_version": "cornell-v1.0-batch-001",
                "source_ref":     f"movie={movie_id}|line={line_id}",
            })
    return out


# ── DailyDialog parser ───────────────────────────────────────────────────

def _load_dailydialog() -> list[dict]:
    base = CACHE_DIR / "dailydialog"
    candidates = list(base.rglob("dialogues_text.txt"))
    if not candidates:
        print(f"  [dailydialog] dialogues_text.txt not found under {base}/ -- skipping")
        return []
    out: list[dict] = []
    with candidates[0].open("r", encoding="utf-8", errors="ignore") as fh:
        for dlg_id, line in enumerate(fh):
            # Each line is one full dialogue; turns separated by " __eou__ "
            for turn_id, raw_turn in enumerate(line.split("__eou__")):
                text = raw_turn.strip()
                if not _is_dialogue(text):
                    continue
                out.append({
                    "raw_text":       text,
                    "source_tag":     "dailydialog",
                    "source_version": "dailydialog-v1.0-batch-001",
                    "source_ref":     f"dialogue={dlg_id}|turn={turn_id}",
                })
    return out


# ── EmpatheticDialogues parser ───────────────────────────────────────────

def _load_empathetic() -> list[dict]:
    base = CACHE_DIR / "empathetic"
    # The CSV files are at base/empatheticdialogues/{train,valid,test}.csv
    candidates = list(base.rglob("train.csv")) + list(base.rglob("valid.csv"))
    if not candidates:
        print(f"  [empathetic] train.csv not found under {base}/ -- skipping")
        return []
    out: list[dict] = []
    for csv_path in candidates:
        with csv_path.open("r", encoding="utf-8", errors="ignore") as fh:
            header = fh.readline()
            cols = [c.strip() for c in header.split(",")]
            try:
                utt_idx = cols.index("utterance")
                conv_idx = cols.index("conv_id")
            except ValueError:
                continue
            for line in fh:
                # Empathetic CSV uses "_comma_" placeholder for embedded commas
                fields = line.rstrip("\n").split(",")
                if len(fields) < max(utt_idx, conv_idx) + 1:
                    continue
                text = fields[utt_idx].replace("_comma_", ",").strip()
                if not _is_dialogue(text):
                    continue
                out.append({
                    "raw_text":       text,
                    "source_tag":     "empathetic",
                    "source_version": "empathetic-v1.0-batch-001",
                    "source_ref":     f"conv={fields[conv_idx]}",
                })
    return out


# ── Sampling ─────────────────────────────────────────────────────────────

def _stratified_sample(rows_by_corpus: dict[str, list[dict]], seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    out: list[dict] = []
    for name, budget in BUDGETS.items():
        rows = rows_by_corpus.get(name, [])
        if not rows:
            continue
        if len(rows) <= budget:
            out.extend(rows)
            continue
        out.extend(rng.sample(rows, budget))
    return out


def main() -> int:
    if OUTPUT_PATH.exists() and OUTPUT_PATH.stat().st_size > 0:
        print(f"[skip] {OUTPUT_PATH} already exists")
        with OUTPUT_PATH.open("r", encoding="utf-8") as fh:
            n = sum(1 for _ in fh)
        print(f"  ({n} samples cached -- delete file to re-run)")
        return 0

    print("Loading + filtering corpora...")
    pools = {
        "cornell":     _load_cornell(),
        "dailydialog": _load_dailydialog(),
        "empathetic":  _load_empathetic(),
    }
    for name, pool in pools.items():
        print(f"  {name}: {len(pool)} candidates after filter")
    samples = _stratified_sample(pools)
    print(f"Stratified sample: {len(samples)} total")

    with OUTPUT_PATH.open("w", encoding="utf-8") as fh:
        for s in samples:
            fh.write(json.dumps(s) + "\n")
    print(f"[stage_2_filter] wrote {len(samples)} samples -> {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
