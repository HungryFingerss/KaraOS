"""Phase 5 (Session 119) — quarterly golden-corpus drift check.

Two modes:
  --mode export   : sample 20 stratified golden rows; write a fillable
                    markdown checklist to tests/golden_set_drift_<date>.md
  --mode compare  : read the human-filled markdown and report any
                    disagreements with the stored expected_intent /
                    expected_value fields. Suggested action per row.

This is **explicitly not automated** — drift detection is a judgment
call. The script just makes the human review efficient.

Usage:
  python tests/golden_set_drift.py --mode export
  python tests/golden_set_drift.py --mode compare --filled tests/golden_set_drift_YYYY-MM-DD.md
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import random
import re
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

GOLDEN_PATH = _REPO_ROOT / "tests" / "golden_intent.jsonl"


# ── Loading ──────────────────────────────────────────────────────────────
def _load_rows() -> list[dict]:
    rows: list[dict] = []
    with GOLDEN_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _eligible(rows: list[dict]) -> list[dict]:
    """Drop legacy_synthetic — drift check is for live-eligible rows."""
    return [r for r in rows if r.get("source") != "legacy_synthetic"]


# ── Mode A — export ──────────────────────────────────────────────────────
def stratified_sample(
    rows: list[dict],
    n_total: int = 20,
    seed: int = 42,
    min_per_intent: int = 1,
    intent_floor: int = 3,
) -> list[dict]:
    """Return up to ``n_total`` rows, taking at least ``min_per_intent``
    from each intent label that has at least ``intent_floor`` rows
    in the corpus. Caller passes a fixed seed for reproducibility.

    Stratification is best-effort: if there are more well-populated
    intents than ``n_total`` quota allows, the remaining slots fill
    randomly across all eligible rows.
    """
    rng = random.Random(seed)
    by_intent: dict[str, list[dict]] = {}
    for r in rows:
        by_intent.setdefault(r.get("expected_intent", "?"), []).append(r)

    selected: list[dict] = []
    selected_ids: set[int] = set()

    for intent, bucket in sorted(by_intent.items()):
        if len(bucket) < intent_floor:
            continue
        # Pick min_per_intent from this bucket.
        for r in rng.sample(bucket, k=min(min_per_intent, len(bucket))):
            if id(r) in selected_ids:
                continue
            selected.append(r)
            selected_ids.add(id(r))
            if len(selected) >= n_total:
                return selected

    # Fill remaining quota randomly from all eligible rows.
    pool = [r for r in rows if id(r) not in selected_ids]
    rng.shuffle(pool)
    while len(selected) < n_total and pool:
        selected.append(pool.pop())
    return selected


def _export_markdown(sample: list[dict], out_path: pathlib.Path) -> None:
    parts: list[str] = []
    parts.append("# Golden Set Drift Check — Manual Review")
    parts.append("")
    parts.append(
        f"Generated: {_dt.datetime.now().isoformat(timespec='seconds')}  "
        f"Rows: {len(sample)}"
    )
    parts.append("")
    parts.append(
        "Instructions: for each row, decide whether the **stored expected_intent / "
        "expected_value** still match what a competent labeller would assign today. "
        "Mark `[x]` next to your verdict. If different, fill the new label below."
    )
    parts.append("")
    for i, row in enumerate(sample, 1):
        text = (row.get("user_text") or "").replace("\n", " ")
        parts.append(f"## Row {i}")
        parts.append(f"**user_text:** {text!r}")
        parts.append(f"**stored expected_intent:** {row.get('expected_intent')}")
        parts.append(f"**stored expected_value:** {row.get('expected_value')}")
        parts.append(f"**source:** {row.get('source')}")
        parts.append("")
        parts.append("- [ ] same  - [ ] different (fill below)")
        parts.append("")
        parts.append("Different label: ____________")
        parts.append("Different value: ____________")
        parts.append("Notes: ____________")
        parts.append("")
        parts.append("---")
        parts.append("")
    out_path.write_text("\n".join(parts), encoding="utf-8")


def export(out_path: "pathlib.Path | None" = None,
           n_total: int = 20,
           seed: int = 42) -> pathlib.Path:
    rows = _eligible(_load_rows())
    sample = stratified_sample(rows, n_total=n_total, seed=seed)
    if out_path is None:
        date_str = _dt.date.today().isoformat()
        out_path = _REPO_ROOT / "tests" / f"golden_set_drift_{date_str}.md"
    _export_markdown(sample, out_path)
    return out_path


# ── Mode B — compare ────────────────────────────────────────────────────
_ROW_HEADER_RE = re.compile(r"^##\s+Row\s+(\d+)", re.M)
_USER_RE       = re.compile(r"^\*\*user_text:\*\*\s+(.*)$", re.M)
_INTENT_RE     = re.compile(r"^\*\*stored expected_intent:\*\*\s+(.*)$", re.M)
_VALUE_RE      = re.compile(r"^\*\*stored expected_value:\*\*\s+(.*)$", re.M)
# Match either:
#   - [x] same  / - [x] different     (whitespace before checkbox)
_SAME_RE       = re.compile(r"-\s*\[\s*x\s*\]\s*same", re.I)
_DIFF_RE       = re.compile(r"-\s*\[\s*x\s*\]\s*different", re.I)
_DIFF_LABEL_RE = re.compile(r"^Different label:\s*(.+)$", re.M)
_DIFF_VALUE_RE = re.compile(r"^Different value:\s*(.+)$", re.M)


def parse_filled_markdown(text: str) -> list[dict]:
    """Parse a filled drift-check markdown into a list of verdicts.

    Each verdict: {row_index, user_text, stored_intent, stored_value,
                  verdict (same/different/none), new_intent, new_value}.
    Rows where neither checkbox is marked get verdict='none' (skipped).
    """
    # Split text by row headers; first section is the preamble.
    chunks: list[tuple[int, str]] = []
    matches = list(_ROW_HEADER_RE.finditer(text))
    for i, m in enumerate(matches):
        idx = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunks.append((idx, text[start:end]))

    verdicts: list[dict] = []
    for idx, body in chunks:
        u = _USER_RE.search(body)
        i = _INTENT_RE.search(body)
        v = _VALUE_RE.search(body)
        same = bool(_SAME_RE.search(body))
        diff = bool(_DIFF_RE.search(body))
        new_label_m = _DIFF_LABEL_RE.search(body)
        new_value_m = _DIFF_VALUE_RE.search(body)

        new_label = (new_label_m.group(1).strip() if new_label_m else "")
        new_value = (new_value_m.group(1).strip() if new_value_m else "")
        if new_label.startswith("___"):
            new_label = ""
        if new_value.startswith("___"):
            new_value = ""

        if diff:
            verdict = "different"
        elif same:
            verdict = "same"
        else:
            verdict = "none"

        verdicts.append({
            "row_index":     idx,
            "user_text":     (u.group(1).strip() if u else ""),
            "stored_intent": (i.group(1).strip() if i else ""),
            "stored_value":  (v.group(1).strip() if v else ""),
            "verdict":       verdict,
            "new_intent":    new_label,
            "new_value":     new_value,
        })
    return verdicts


def report_disagreements(verdicts: list[dict]) -> dict:
    """Return summary + flagged rows where verdict is 'different'."""
    same = sum(1 for v in verdicts if v["verdict"] == "same")
    diff = sum(1 for v in verdicts if v["verdict"] == "different")
    none = sum(1 for v in verdicts if v["verdict"] == "none")
    flagged = [v for v in verdicts if v["verdict"] == "different"]
    return {
        "total":   len(verdicts),
        "same":    same,
        "different": diff,
        "skipped": none,
        "flagged": flagged,
    }


def compare(filled_path: pathlib.Path) -> int:
    if not filled_path.exists():
        print(f"[golden_drift] FATAL: filled markdown not found: {filled_path}",
              file=sys.stderr)
        return 2
    text = filled_path.read_text(encoding="utf-8")
    verdicts = parse_filled_markdown(text)
    summary = report_disagreements(verdicts)
    print("# Golden-Set Drift Compare")
    print()
    print(f"- Total rows reviewed: {summary['total']}")
    print(f"- Agreed (same):       {summary['same']}")
    print(f"- Disagreed (drifted): {summary['different']}")
    print(f"- Unmarked (skipped):  {summary['skipped']}")
    print()
    if summary["flagged"]:
        print("## Drifted rows")
        for v in summary["flagged"]:
            print(f"### Row {v['row_index']}")
            print(f"- user_text:     {v['user_text']}")
            print(f"- stored intent: {v['stored_intent']}")
            print(f"- stored value:  {v['stored_value']}")
            print(f"- new intent:    {v['new_intent']!r}")
            print(f"- new value:     {v['new_value']!r}")
            print(f"- suggested action: relabel as `{v['new_intent']}` "
                  f"OR add a `regression_session_<n>_relabel` companion row "
                  f"(see tests/golden_intent.jsonl Session 81 taxonomy).")
            print()
    return 0


# ── Main ────────────────────────────────────────────────────────────────
def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--mode", choices=["export", "compare"], required=True,
        help="export: write a sampled markdown checklist. "
             "compare: read filled markdown + report disagreements.",
    )
    parser.add_argument(
        "--filled",
        help="Path to the filled markdown (compare mode only).",
    )
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--out",
        help="Output path for export mode. Defaults to "
             "tests/golden_set_drift_<date>.md.",
    )
    args = parser.parse_args(argv)

    if args.mode == "export":
        out_path = pathlib.Path(args.out).resolve() if args.out else None
        out_path = export(out_path=out_path, n_total=args.n, seed=args.seed)
        print(f"[golden_drift] Wrote {out_path}")
        return 0
    elif args.mode == "compare":
        if not args.filled:
            print("[golden_drift] FATAL: --filled required for compare mode",
                  file=sys.stderr)
            return 2
        return compare(pathlib.Path(args.filled).resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
