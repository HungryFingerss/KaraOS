"""VISION_ROADMAP P1.6 — intent classifier eval bench.

Two-layer design (Session 82):
  * PURE functions — deterministic metric math (precision/recall/ECE/low-sample
    flagging/per-source splitting). Unit-tested in CI via
    tests/test_eval_intent_bench.py. NO live API calls.
  * LIVE CLI (main) — iterates the golden corpus, calls the shadow classifier
    (core.brain._classify_intent) once per row, persists the full run JSON to
    tests/eval_bench_runs/, prints a human summary. Manual invocation only
    (not in CI — costs real API credits + takes ~10 min).

Reviewer-prescribed metadata per run (Phase 5 drift detection depends on it):
  * git SHA at run time
  * sha256(_INTENT_CLASSIFIER_SYSTEM)[:12] — prompt hash for change detection
  * CHAT_MODEL, INTENT_CONFIDENCE_MIN, INTENT_SHUTDOWN_CONF_MIN — thresholds
    in effect so future runs can flag apples-to-apples vs apples-to-oranges

Usage (run from project root):
    python tests/eval_intent_bench.py

Cost estimate (Llama-3.3-70B-Instruct-Turbo on Together.ai):
  ~$0.88 / 1M input tokens, ~$0.88 / 1M output tokens
  146 rows x (~600 input + ~150 output tokens) ~= $0.65-0.70 per full run

Wire-in gate (P1.6 -> P1.7-P1.11):
  (a) Hybrid-set per-intent precision >= 0.95, recall >= 0.85, ECE <= 0.05
  (b) real_observed subset (n >= REAL_OBSERVED_MIN) independently at same
      thresholds — anti-cheat against synthetic-engineered false green-light
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import hashlib
import json
import pathlib
import subprocess
import sys
import time
from collections import defaultdict

# Ensure project-root imports work when the bench is invoked as a script
# (``python tests/eval_intent_bench.py``). Python sets sys.path[0] to the
# script's parent directory in that case, which would make
# ``from core.brain import ...`` fail. Prepending the repo root is a no-op
# under pytest (rootdir already on path) and under ``python -m tests.eval_intent_bench``.
_REPO_ROOT       = pathlib.Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_BENCH_RUNS_DIR  = pathlib.Path(__file__).resolve().parent / "eval_bench_runs"
_GOLDEN_PATH     = pathlib.Path(__file__).resolve().parent / "golden_intent.jsonl"

# Per-intent sample count below which metrics get a "low_confidence_estimate"
# flag (wide error bars — one mislabel moves precision visibly). Reviewer's
# Session 82 threshold; intents that hit this get ⚠ low-sample in stdout.
LOW_SAMPLE_THRESHOLD = 15

# Real_observed sample count required before the P1.6 -> P1.7 wire-in gate
# opens. Matches Session 81 CLAUDE.md taxonomy spec.
REAL_OBSERVED_MIN    = 30

# ECE uses 10 equal-width confidence buckets [0.0, 0.1), ..., [0.9, 1.0].
# Standard choice for a 0.0-1.0 confidence range; 10 buckets is enough to
# detect calibration drift without being so fine-grained that each bucket
# has too few samples.
ECE_N_BUCKETS        = 10


# ── Loading ──────────────────────────────────────────────────────────────────


def load_golden(
    path: pathlib.Path = _GOLDEN_PATH,
    *,
    include_legacy: bool = False,
) -> list[dict]:
    """Load the golden corpus as a list of dicts. By default excludes
    ``source=legacy_synthetic`` rows per the Session 81 deprecation rule —
    they stay in the JSONL as historical record but must NOT contribute
    to metric computation."""
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if not include_legacy and row.get("source") == "legacy_synthetic":
            continue
        rows.append(row)
    return rows


# ── Pure metric computation (unit-tested in CI) ──────────────────────────────


def _compute_ece(pairs: list[tuple[dict, dict]]) -> float:
    """Expected Calibration Error across confidence buckets.

    Standard formula:
        ECE = Σ_b (|B_b| / N) * |acc(B_b) - conf(B_b)|

    where b iterates over equal-width confidence buckets. ECE measures how
    well the classifier's confidence matches its actual accuracy: a well-
    calibrated classifier has ECE near 0. `pairs` should already be filtered
    to a single intent's ground-truth rows so the accuracy signal is clean.

    Returns 0.0 on empty input (not a meaningful calibration error, but
    avoids division-by-zero blowing up the eval report)."""
    if not pairs:
        return 0.0
    N = len(pairs)
    buckets: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for r, p in pairs:
        conf = float(p.get("confidence") or 0.0)
        # Clamp to [0, ECE_N_BUCKETS-1] in case a classifier returns 1.0+
        # (shouldn't, but be defensive — don't crash the eval bench).
        bucket_idx = min(max(int(conf * ECE_N_BUCKETS), 0), ECE_N_BUCKETS - 1)
        correct = int(p.get("predicted_intent") == r["expected_intent"])
        buckets[bucket_idx].append((correct, conf))
    total = 0.0
    for _, items in buckets.items():
        acc      = sum(c for c, _ in items) / len(items)
        avg_conf = sum(cf for _, cf in items) / len(items)
        total += (len(items) / N) * abs(acc - avg_conf)
    return total


def _compute_subset_metrics(pairs: list[tuple[dict, "dict | None"]]) -> dict:
    """Per-subset metrics — overall accuracy + per-intent precision/recall/
    ECE + timeout count. A prediction of None means the classifier failed
    or timed out on that row; timeouts count as incorrect (they are)."""
    if not pairs:
        return {
            "overall":    {"n": 0, "correct": 0, "accuracy": 0.0},
            "per_intent": {},
            "timeouts":   0,
        }
    timeouts = sum(1 for _, p in pairs if p is None)
    # correct counts only rows that produced a prediction matching ground truth;
    # None predictions are counted as wrong (implicit — they can't match).
    correct = sum(
        1 for r, p in pairs
        if p is not None and p.get("predicted_intent") == r["expected_intent"]
    )
    per_intent: dict[str, dict] = {}
    valid = [(r, p) for r, p in pairs if p is not None]
    intents: set[str] = {r["expected_intent"] for r, _ in pairs}
    # Also include intents the classifier PREDICTED — so FP counts for classes
    # not in the ground truth are still surfaced (shouldn't happen if the
    # classifier stays on-schema, but don't silently drop).
    intents |= {
        p.get("predicted_intent") for _, p in valid
        if p.get("predicted_intent") is not None
    }
    for intent in intents:
        tp = sum(
            1 for r, p in valid
            if r["expected_intent"] == intent and p.get("predicted_intent") == intent
        )
        fp = sum(
            1 for r, p in valid
            if r["expected_intent"] != intent and p.get("predicted_intent") == intent
        )
        fn = sum(
            1 for r, p in valid
            if r["expected_intent"] == intent and p.get("predicted_intent") != intent
        )
        n_samples = sum(1 for r, _ in pairs if r["expected_intent"] == intent)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall    = tp / (tp + fn) if (tp + fn) else 0.0
        intent_pairs = [(r, p) for r, p in valid if r["expected_intent"] == intent]
        ece = _compute_ece(intent_pairs)
        per_intent[intent] = {
            "precision":  precision,
            "recall":     recall,
            "ece":        ece,
            "n_samples":  n_samples,
            "low_sample": n_samples < LOW_SAMPLE_THRESHOLD,
        }
    return {
        "overall": {
            "n":        len(pairs),
            "correct":  correct,
            "accuracy": correct / len(pairs),
        },
        "per_intent": per_intent,
        "timeouts":   timeouts,
    }


def compute_metrics(
    rows: list[dict],
    predictions: list["dict | None"],
) -> dict:
    """Top-level metric aggregator. Pure function — deterministic, no I/O.

    Inputs:
      rows:        golden-set entries (each must have ``expected_intent`` and
                   ``source`` keys; ``source_file`` optional).
      predictions: classifier outputs aligned with ``rows`` by index. Each
                   entry is either a dict with keys ``predicted_intent``,
                   ``confidence`` (and optionally ``extracted_value``,
                   ``reasoning``) OR ``None`` when the classifier
                   failed / timed out.

    Output — nested dict:
      {
        "hybrid":        {...},   # all non-legacy rows
        "real_observed": {...},   # filtered subset
        "per_source": {
           "adversarial":      {...},
           "synthetic_common": {...},
           "real_observed":    {...},   # also included here for per-source view
        },
      }

    Each subset contains ``overall``, ``per_intent``, ``timeouts`` — see
    ``_compute_subset_metrics``.
    """
    assert len(rows) == len(predictions), (
        f"rows ({len(rows)}) / predictions ({len(predictions)}) length mismatch"
    )
    pairs = list(zip(rows, predictions))

    def _subset(src: str) -> list[tuple[dict, "dict | None"]]:
        return [(r, p) for r, p in pairs if r.get("source") == src]

    out: dict = {
        "hybrid":        _compute_subset_metrics(pairs),
        "real_observed": _compute_subset_metrics(_subset("real_observed")),
        "per_source":    {},
    }
    for src in ("adversarial", "synthetic_common", "real_observed"):
        subset = _subset(src)
        if subset:
            out["per_source"][src] = _compute_subset_metrics(subset)
    return out


def collect_mismatches(
    rows: list[dict],
    predictions: list["dict | None"],
) -> list[dict]:
    """Row-level divergence list — one entry per ``expected != predicted``
    row (including classifier failures where prediction is None). Used for
    the stdout ``Mismatches:`` table AND persisted in the full run JSON so
    individual rows are inspectable after the fact."""
    out: list[dict] = []
    for r, p in zip(rows, predictions):
        if p is None:
            out.append({
                "user_text":        r["user_text"],
                "source":           r.get("source", "unknown"),
                "expected_intent":  r["expected_intent"],
                "predicted_intent": None,
                "confidence":       0.0,
                "source_file":      r.get("source_file"),
            })
            continue
        if p.get("predicted_intent") != r["expected_intent"]:
            out.append({
                "user_text":        r["user_text"],
                "source":           r.get("source", "unknown"),
                "expected_intent":  r["expected_intent"],
                "predicted_intent": p.get("predicted_intent"),
                "confidence":       float(p.get("confidence") or 0.0),
                "source_file":      r.get("source_file"),
            })
    return out


# ── Metadata for persisted runs (Phase 5 drift detection) ────────────────────


def _git_sha() -> str:
    """Return current git HEAD SHA, or 'no-git' if unavailable."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=2, cwd=str(_REPO_ROOT),
        )
        return r.stdout.strip() or "no-git"
    except Exception:
        return "no-git"


def collect_metadata(
    *,
    row_count: int,
    live_calls: int,
    total_cost_usd: float,
    duration_secs: float,
    classifier_system_prompt: str,
) -> dict:
    """Snapshot the exact configuration that produced these metrics. Phase 5
    drift detection queries this to answer 'what changed?' when two runs
    diverge. Reviewer's Session 82 spec."""
    from core.config import (
        INTENT_CONFIDENCE_MIN, INTENT_SHUTDOWN_CONF_MIN, CHAT_MODEL,
    )
    prompt_hash = hashlib.sha256(
        classifier_system_prompt.encode("utf-8")
    ).hexdigest()[:12]
    return {
        "run_ts":                  _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha":                 _git_sha(),
        "classifier_prompt_hash":  prompt_hash,
        "intent_model":            CHAT_MODEL,
        "confidence_min":          INTENT_CONFIDENCE_MIN,
        "shutdown_conf_min":       INTENT_SHUTDOWN_CONF_MIN,
        "golden_row_count":        row_count,
        "live_calls":              live_calls,
        "total_cost_usd":          round(total_cost_usd, 4),
        "duration_secs":           round(duration_secs, 2),
    }


def save_run(
    metrics: dict,
    metadata: dict,
    mismatches: list[dict],
    *,
    out_dir: pathlib.Path = _BENCH_RUNS_DIR,
) -> pathlib.Path:
    """Persist one bench run to disk. File name derives from run_ts so
    chronological sorts work out-of-the-box."""
    out_dir.mkdir(parents=True, exist_ok=True)
    # Example: "2026-04-22T15:30:12Z" -> "20260422_153012"
    raw_ts = metadata["run_ts"].replace("-", "").replace("T", "_").replace(":", "").rstrip("Z")
    out_path = out_dir / f"{raw_ts}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump({
            "metadata":   metadata,
            "metrics":    metrics,
            "mismatches": mismatches,
        }, f, indent=2, ensure_ascii=False)
    return out_path


# ── Stdout summary ───────────────────────────────────────────────────────────


def format_summary(
    metrics: dict,
    metadata: dict,
    mismatches: list[dict],
    *,
    real_observed_min: int = REAL_OBSERVED_MIN,
) -> str:
    """Human-readable summary table. Matches reviewer's Session 82 mock
    format. Low-sample intents flagged visibly; wire-in gate state
    explicit."""
    lines: list[str] = []
    lines.append(f"Intent Classifier Eval — {metadata['run_ts']}")
    lines.append(
        f"{metadata['golden_row_count']} rows processed | "
        f"{metadata['live_calls']} live calls | "
        f"${metadata['total_cost_usd']:.2f} | "
        f"{metadata['duration_secs'] / 60:.1f} min"
    )
    lines.append("")
    lines.append("HYBRID SET (all sources)")
    hb_header = f"  {'Intent':25s} {'Prec':>5s} {'Rec':>5s} {'ECE':>5s} {'N':>4s}  Flag"
    lines.append(hb_header)
    for intent, m in sorted(metrics["hybrid"]["per_intent"].items()):
        flag = "low-sample" if m["low_sample"] else ""
        lines.append(
            f"  {intent:25s} {m['precision']:5.2f} {m['recall']:5.2f} "
            f"{m['ece']:5.2f} {m['n_samples']:4d}  {flag}"
        )
    ov = metrics["hybrid"]["overall"]
    lines.append(
        f"  Overall: {ov['accuracy']:.2%} ({ov['correct']}/{ov['n']}) "
        f"| timeouts: {metrics['hybrid']['timeouts']}"
    )
    lines.append("")
    real   = metrics["real_observed"]
    real_n = real["overall"]["n"]
    lines.append(f"REAL_OBSERVED SUBSET (n={real_n})")
    if real_n < real_observed_min:
        lines.append(
            f"  sample too small ({real_n} < {real_observed_min}) — "
            f"skip per-intent breakdown"
        )
        lines.append(
            f"  Overall accuracy: {real['overall']['correct']}/{real['overall']['n']}"
        )
    else:
        lines.append(hb_header)
        for intent, m in sorted(real["per_intent"].items()):
            flag = "low-sample" if m["low_sample"] else ""
            lines.append(
                f"  {intent:25s} {m['precision']:5.2f} {m['recall']:5.2f} "
                f"{m['ece']:5.2f} {m['n_samples']:4d}  {flag}"
            )
    lines.append("")
    ready = real_n >= real_observed_min
    lines.append(
        f"Wire-in gate: {'READY' if ready else 'NOT READY'} "
        f"(real_observed {real_n}/{real_observed_min})"
    )
    if mismatches:
        lines.append("")
        lines.append(f"Mismatches ({len(mismatches)}) — first 20:")
        for m in mismatches[:20]:
            ut = m["user_text"][:50] if len(m["user_text"]) <= 50 else m["user_text"][:47] + "..."
            pi = m["predicted_intent"] or "TIMEOUT"
            lines.append(
                f"  [{m['source']:17s}] {ut!r:52s} "
                f"expected={m['expected_intent']} got={pi}@{m['confidence']:.2f}"
            )
        if len(mismatches) > 20:
            lines.append(f"  ... ({len(mismatches) - 20} more in run JSON)")
    return "\n".join(lines)


# ── Live CLI (manual invocation — NOT run in CI) ─────────────────────────────


async def _run_live_bench(rows: list[dict]) -> tuple[list["dict | None"], float, int]:
    """Drive the shadow classifier against every golden row. Prints per-row
    progress so a 10-min run isn't a silent void. Returns
    (predictions, duration_secs, timeouts_during_run)."""
    from core.brain import _classify_intent, get_intent_classifier_stats
    stats0 = get_intent_classifier_stats()
    t0 = time.time()
    predictions: list["dict | None"] = []
    for i, row in enumerate(rows, 1):
        user_text = row["user_text"]
        short     = user_text[:60] + ("..." if len(user_text) > 60 else "")
        short_safe = short.encode("ascii", errors="replace").decode("ascii")
        print(f"[Bench] {i:3d}/{len(rows)} — {short_safe!r}", flush=True)
        try:
            sidecar = await _classify_intent(user_text, conversation_history=[])
        except Exception as e:
            print(f"[Bench]   ERROR row {i}: {type(e).__name__}: {e}")
            sidecar = None
        if sidecar is None:
            predictions.append(None)
            continue
        predictions.append({
            "predicted_intent": sidecar.get("turn_intent"),
            "confidence":       float(sidecar.get("confidence") or 0.0),
            "extracted_value":  sidecar.get("extracted_value"),
            "reasoning":        sidecar.get("reasoning", ""),
        })
    duration = time.time() - t0
    stats1   = get_intent_classifier_stats()
    timeouts = stats1["timeouts"] - stats0["timeouts"]
    return predictions, duration, timeouts


def main() -> None:
    from core.brain import _INTENT_CLASSIFIER_SYSTEM
    rows = load_golden()
    print(f"[Bench] Loaded {len(rows)} non-legacy rows from {_GOLDEN_PATH}")
    predictions, duration, _ = asyncio.run(_run_live_bench(rows))
    # Rough cost estimate — Llama-3.3-70B-Instruct-Turbo is $0.88 per 1M tokens
    # (input + output combined on Together.ai's pricing as of Session 82).
    # Classifier prompts are ~600 input + ~150 output per row.
    total_cost = 0.88 * ((600 + 150) * len(rows) / 1_000_000)
    metrics    = compute_metrics(rows, predictions)
    metadata   = collect_metadata(
        row_count=len(rows),
        live_calls=len(rows),
        total_cost_usd=total_cost,
        duration_secs=duration,
        classifier_system_prompt=_INTENT_CLASSIFIER_SYSTEM,
    )
    mismatches = collect_mismatches(rows, predictions)
    save_path  = save_run(metrics, metadata, mismatches)
    summary = format_summary(metrics, metadata, mismatches)
    print("")
    sys.stdout.buffer.write((summary + f"\nFull run JSON saved: {save_path}\n").encode("utf-8", errors="replace"))


if __name__ == "__main__":
    main()
