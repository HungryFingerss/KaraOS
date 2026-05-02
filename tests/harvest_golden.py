"""VISION_ROADMAP P1.5 — harvest script for the golden intent set.

Parses every ``terminal_output*.md`` in the project root, pairs each raw
``[STT]`` utterance with the nearest following ``[Intent]`` classifier log
(within HARVEST_LOOKAHEAD lines), dedups case-folded duplicates, and emits
a skeleton JSONL for manual labeling.

Output schema (one JSON object per line):

    {
      "user_text":       "Hey, what is your name?",
      "observed_intent": "question_about_shutdown",   # classifier's guess, or null
      "observed_value":  null,
      "observed_conf":   0.20,
      "source":          "real_observed",             # taxonomy slot
      "source_file":     "terminal_output_2026-04-22_233426.md:52",
      "expected_intent": null,                         # YOU fill this by hand
      "expected_value":  null                          # YOU fill this by hand
    }

Usage:
    python tests/harvest_golden.py

Output:
    tests/golden_intent_skeleton.jsonl   (overwritten each run)

Design notes:
  * Dedup keeps at most DEDUP_KEEP instances per exact-lowercase user_text.
    Reviewer's spec: "Free 60-80% reduction in labeling work without losing
    coverage" — two instances lets us catch classifier drift on repeated
    utterances without labeling the same phrase 20 times.
  * The raw ``[STT]`` form is used (not the attributed ``[STT] Name (voice=…):``
    form) because the raw form contains the single-quoted ground-truth
    transcript. The attributed form strips quotes and may include the name
    prefix which we don't want in user_text.
  * ``source`` defaults to "real_observed". Adversarial and synthetic rows
    come from separate files (tests/golden_intent_adversarial.jsonl etc.)
    and are merged at eval time by test_intent_structured.py (P1.6).
"""

from __future__ import annotations

import json
import pathlib
import re
from collections import defaultdict

HARVEST_LOOKAHEAD = 20       # lines to search after STT for its [Intent] peer
DEDUP_KEEP         = 2        # max rows per unique lowercase user_text

# Raw Whisper transcript: [STT] HH:MM:SS.mmm (Nms) 'text' or "text"
_STT_RAW_RE = re.compile(
    r"^\[STT\]\s+\d{2}:\d{2}:\d{2}\.\d+\s+\(\d+ms\)\s+(['\"])(.*?)\1\s*$"
)

# Classifier sidecar: [Intent] HH:MM:SS.mmm tools=[...] classified=X value=Y conf=Z reason=...
_INTENT_RE = re.compile(
    r"^\[Intent\]\s+\d{2}:\d{2}:\d{2}\.\d+\s+"
    r"tools=\[([^\]]*)\]\s+"
    r"classified=(\w+)\s+"
    r"value=(None|'[^']*'|\"[^\"]*\")\s+"
    r"conf=([\d.]+)"
)


def _parse_value(raw: str) -> "str | None":
    """Unwrap Python repr for the Intent line's value field."""
    if raw == "None":
        return None
    # Strip single or double quotes.
    if len(raw) >= 2 and raw[0] in "'\"" and raw[-1] == raw[0]:
        return raw[1:-1]
    return raw


def harvest(root: pathlib.Path) -> list[dict]:
    """Walk every terminal_output*.md under root, return observation dicts.

    Returned list is pre-dedup — callers apply `dedupe_rows`."""
    rows: list[dict] = []
    for path in sorted(root.glob("terminal_output*.md")):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines):
            m = _STT_RAW_RE.match(line)
            if not m:
                continue
            user_text = m.group(2).strip()
            if not user_text:
                continue
            # Look ahead for the paired [Intent] line (may not exist — only
            # gated-tool turns fire the classifier).
            observed_intent: "str | None" = None
            observed_value: "str | None"  = None
            observed_conf: "float | None" = None
            for j in range(i + 1, min(i + 1 + HARVEST_LOOKAHEAD, len(lines))):
                im = _INTENT_RE.match(lines[j])
                if im:
                    observed_intent = im.group(2)
                    observed_value  = _parse_value(im.group(3))
                    observed_conf   = float(im.group(4))
                    break
                # Stop early if we hit the NEXT STT — means the Intent
                # didn't fire for the current turn at all.
                if _STT_RAW_RE.match(lines[j]):
                    break
            rows.append({
                "user_text":       user_text,
                "observed_intent": observed_intent,
                "observed_value":  observed_value,
                "observed_conf":   observed_conf,
                "source":          "real_observed",
                "source_file":     f"{path.name}:{i + 1}",
                "expected_intent": None,
                "expected_value":  None,
            })
    return rows


def dedupe_rows(rows: list[dict], keep: int = DEDUP_KEEP) -> list[dict]:
    """Keep at most `keep` rows per exact-lowercase user_text, preserving
    harvest order (so the earliest occurrences survive — they're often the
    most representative of the original session context)."""
    counts: dict[str, int] = defaultdict(int)
    out: list[dict] = []
    for row in rows:
        key = row["user_text"].casefold()
        if counts[key] >= keep:
            continue
        counts[key] += 1
        out.append(row)
    return out


def main() -> None:
    root = pathlib.Path(__file__).resolve().parent.parent
    rows = harvest(root)
    before = len(rows)
    rows = dedupe_rows(rows)
    after = len(rows)

    out_path = root / "tests" / "golden_intent_skeleton.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    classified = sum(1 for r in rows if r["observed_intent"] is not None)
    print(
        f"Harvested {after} rows from {before} raw matches "
        f"({before - after} deduped); {classified} have classifier observations; "
        f"{after - classified} need hand-labeling without a hint."
    )
    print(f"Output: {out_path.relative_to(root)}")


if __name__ == "__main__":
    main()
