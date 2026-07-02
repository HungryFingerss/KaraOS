"""Sanitize a Kara-OS prediction JSON for license-safe publishing.

Strips the copyrighted Friends dialogue (`current_turn`, `context_turns`)
while preserving everything needed to verify the reported score:
sample_id, ground_truth, prediction, category, output_text, latency,
target_speaker, all_speakers, context_turns_total, confidence.

A reader who downloads the source dataset from HuggingFace and joins
on sample_id can recompute the metrics with the paper's metrics.py and
reproduce our reported number — that's actually a stronger verification
path than shipping the raw text (the reader gets source from an
authoritative origin and can be sure we didn't doctor inputs).

Spec: published-papers-tests/SANITIZE_SPEC.md.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path


# ── Sanitization rules per SANITIZE_SPEC.md ────────────────────────────
DROP_FIELDS = ("current_turn", "context_turns")
LICENSE_NOTE = (
    "Source dialogue stripped to comply with Friends-MMC redistribution "
    "terms. To verify these predictions: download the source dataset from "
    "huggingface.co/datasets/ishiki-labs/multi-party-dialogue, join on "
    "sample_id, and recompute metrics with the paper's metrics.py. See "
    "RESULTS.md for full instructions."
)


def _word_tokens(text: str) -> list[str]:
    """Lowercase word-token list, alphanumeric only — used by the spot-
    check substring scan to compare LLM reasoning text against source
    dialogue. Keeps comparison robust against punctuation/case noise."""
    return re.findall(r"[A-Za-z0-9']+", (text or "").lower())


def _has_long_verbatim_quote(
    output_text: str,
    source_text: str,
    min_words: int = 6,
) -> bool:
    """Return True if `output_text` contains any ≥`min_words`-consecutive-
    word substring from `source_text`. Cheap rolling-window match."""
    if not output_text or not source_text:
        return False
    out_tokens = _word_tokens(output_text)
    src_tokens = _word_tokens(source_text)
    if len(src_tokens) < min_words or len(out_tokens) < min_words:
        return False
    # Build a set of every min_words-gram from source.
    src_grams = set()
    for i in range(len(src_tokens) - min_words + 1):
        src_grams.add(tuple(src_tokens[i : i + min_words]))
    if not src_grams:
        return False
    # Slide a window across output, check each min_words-gram.
    for i in range(len(out_tokens) - min_words + 1):
        if tuple(out_tokens[i : i + min_words]) in src_grams:
            return True
    return False


def sanitize_row(row: dict) -> dict:
    """Return a copy of `row` with copyrighted fields dropped."""
    return {k: v for k, v in row.items() if k not in DROP_FIELDS}


def spot_check(
    full_predictions: list[dict],
    n_samples: int = 20,
    seed: int = 42,
    min_words: int = 6,
) -> tuple[int, list[dict]]:
    """Run the SANITIZE_SPEC.md spot-check: sample N random rows + flag
    any whose `output_text` contains ≥`min_words`-consecutive-word
    quotes from `current_turn.text`.

    Returns (rows_checked, list_of_flagged_dicts).
    """
    rng = random.Random(seed)
    indices = sorted(rng.sample(range(len(full_predictions)),
                                k=min(n_samples, len(full_predictions))))
    flagged: list[dict] = []
    for idx in indices:
        row = full_predictions[idx]
        out  = row.get("output_text") or ""
        cur  = (row.get("current_turn") or {}).get("text") or ""
        if _has_long_verbatim_quote(out, cur, min_words=min_words):
            flagged.append({
                "row_index":     idx,
                "sample_id":     row.get("sample_id"),
                "current_text":  cur[:200],
                "output_text":   out[:300],
            })
    return len(indices), flagged


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Sanitize Kara-OS predictions for public release.")
    parser.add_argument("--input",  default="results/karaos_friends.json",
                        help="Path to full prediction JSON (default: %(default)s)")
    parser.add_argument("--output", default="results/karaos_friends_test.json",
                        help="Path to sanitized JSON (default: %(default)s)")
    parser.add_argument("--spot-check-samples", type=int, default=20,
                        help="Random rows to spot-check for verbatim quotes (default: 20)")
    parser.add_argument("--spot-check-min-words", type=int, default=6,
                        help="Minimum consecutive-word match to flag as verbatim quote (default: 6)")
    parser.add_argument("--abort-on-leaks", type=int, default=2,
                        help="Abort if N or more flagged rows found (default: 2)")
    args = parser.parse_args(argv)

    in_path  = Path(args.input)
    out_path = Path(args.output)
    if not in_path.exists():
        print(f"[sanitize] FATAL: input not found: {in_path}", file=sys.stderr)
        return 2

    raw_bytes = in_path.read_bytes()
    raw_size = len(raw_bytes)
    data = json.loads(raw_bytes)
    full_predictions = data.get("predictions") or []
    if not full_predictions:
        print(f"[sanitize] FATAL: no `predictions` array in {in_path}", file=sys.stderr)
        return 3

    # Spot-check on the FULL (unsanitized) data — that's where source
    # dialogue is still readable, so we can compare against output_text.
    print(f"[sanitize] Spot-checking {args.spot_check_samples} random rows for "
          f">={args.spot_check_min_words}-word verbatim quotes in output_text...")
    n_checked, flagged = spot_check(
        full_predictions,
        n_samples=args.spot_check_samples,
        min_words=args.spot_check_min_words,
    )
    print(f"[sanitize] Spot-check: {n_checked} rows checked, "
          f"{len(flagged)} flagged.")
    for f in flagged:
        print(f"  FLAG row={f['row_index']} sample_id={f['sample_id']!r}")
        print(f"    current_turn: {f['current_text']!r}")
        print(f"    output_text:  {f['output_text']!r}")
    if len(flagged) >= args.abort_on_leaks:
        print(
            f"[sanitize] ABORT: {len(flagged)} flagged rows >= "
            f"abort threshold {args.abort_on_leaks}. Don't ship until "
            f"resolved (regex scrub or escalate).",
            file=sys.stderr,
        )
        return 4

    # Build sanitized payload — preserve top-level run-metadata keys,
    # add _license_note as the FIRST key for visibility, drop
    # copyrighted fields from each prediction row.
    sanitized = {"_license_note": LICENSE_NOTE}
    for k, v in data.items():
        if k == "predictions":
            sanitized[k] = [sanitize_row(r) for r in v]
        else:
            sanitized[k] = v

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_bytes = json.dumps(sanitized, indent=2).encode("utf-8")
    out_path.write_bytes(out_bytes)

    avg_in  = raw_size / len(full_predictions)
    avg_out = len(out_bytes) / len(sanitized["predictions"])
    print()
    print(f"[sanitize] Rows: {len(sanitized['predictions'])}")
    print(f"[sanitize] File size: {raw_size:,} -> {len(out_bytes):,} bytes "
          f"({len(out_bytes)/raw_size:.1%} of original)")
    print(f"[sanitize] Avg row size: {avg_in:.0f} -> {avg_out:.0f} bytes "
          f"({avg_out/avg_in:.1%} of original)")
    print(f"[sanitize] Wrote sanitized predictions -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
