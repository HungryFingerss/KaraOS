"""Phase 5 (Session 119) — weekly drift report.

Runs the existing golden-set bench, persists the run, then compares
against the most recent prior persisted run to detect classifier
drift. Also queries `intent_divergences` for the last N days to
surface low-confidence decisions, recent rejections, and shadow
samples (Phase 5 mode='shadow' rows).

Outputs a markdown report on stdout. With `--alert`, returns
non-zero exit code when any per-intent precision drops by
``EVAL_WEEKLY_ALERT_PRECISION_DROP_PP`` percentage points or more —
suitable for CI / cron integration without baking in scheduling.

Usage:
  python tests/eval_weekly.py
  python tests/eval_weekly.py --alert
  python tests/eval_weekly.py --no-live   # skip live bench, use the most recent persisted run as "current"

Pure observability tool. Does not modify production code, schemas,
or behavior.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
import time

# Ensure project root on sys.path so `tests/` runs as a script work the
# same way as `python -m tests.eval_weekly`. Mirrors eval_intent_bench's
# Session 81 fix.
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tests.eval_intent_bench import (  # noqa: E402
    _BENCH_RUNS_DIR,
    _run_live_bench,
    collect_metadata,
    collect_mismatches,
    compute_metrics,
    load_golden,
    save_run,
)


# ── Config helpers ────────────────────────────────────────────────────────
def _config():
    """Resolve thresholds. Imported lazy so test monkeypatches stick."""
    from core.config import (
        EVAL_WEEKLY_ALERT_PRECISION_DROP_PP,
        EVAL_WEEKLY_DIVERGENCE_LOOKBACK_DAYS,
        EVAL_WEEKLY_TOP_N,
    )
    return (
        float(EVAL_WEEKLY_ALERT_PRECISION_DROP_PP),
        int(EVAL_WEEKLY_DIVERGENCE_LOOKBACK_DAYS),
        int(EVAL_WEEKLY_TOP_N),
    )


# ── Bench-run loaders ─────────────────────────────────────────────────────
def _list_runs(out_dir: pathlib.Path = _BENCH_RUNS_DIR) -> "list[pathlib.Path]":
    """Return persisted bench-run JSON paths, newest first."""
    if not out_dir.exists():
        return []
    return sorted(
        (p for p in out_dir.glob("*.json") if p.is_file()),
        key=lambda p: p.name,
        reverse=True,
    )


def load_run(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def find_prior_run(
    current_path: "pathlib.Path | None" = None,
    out_dir: pathlib.Path = _BENCH_RUNS_DIR,
) -> "pathlib.Path | None":
    """Return the most recent persisted run STRICTLY older than
    ``current_path``. If ``current_path`` is None, returns the
    most-recent run."""
    runs = _list_runs(out_dir)
    if current_path is None:
        return runs[0] if runs else None
    for p in runs:
        if p.resolve() != current_path.resolve():
            return p
    return None


# ── Drift detection ───────────────────────────────────────────────────────
def compute_drift(
    current_metrics: dict,
    prior_metrics:   dict,
) -> "dict[str, list[dict]]":
    """Compare per-intent precision/recall/accuracy in the ``hybrid``
    subset between two runs. Returns dict with `precision_drops`,
    `recall_drops`, `precision_gains`, `recall_gains` lists — each
    entry { intent, current, prior, delta_pp }.

    Drift is reported in percentage points (0.92 → 0.85 = 7.0pp drop).
    Threshold filtering happens in the caller.
    """
    cur_per_intent = (current_metrics.get("hybrid") or {}).get("per_intent") or {}
    pri_per_intent = (prior_metrics.get("hybrid") or {}).get("per_intent") or {}
    out: dict[str, list[dict]] = {
        "precision_drops": [],
        "recall_drops":    [],
        "precision_gains": [],
        "recall_gains":    [],
    }
    intents = sorted(set(cur_per_intent) | set(pri_per_intent))
    for intent in intents:
        cur = cur_per_intent.get(intent) or {}
        pri = pri_per_intent.get(intent) or {}
        for metric_key, drop_bucket, gain_bucket in (
            ("precision", "precision_drops", "precision_gains"),
            ("recall",    "recall_drops",    "recall_gains"),
        ):
            cur_val = cur.get(metric_key)
            pri_val = pri.get(metric_key)
            if cur_val is None or pri_val is None:
                continue
            delta_pp = (float(cur_val) - float(pri_val)) * 100.0
            entry = {
                "intent":   intent,
                "current":  float(cur_val),
                "prior":    float(pri_val),
                "delta_pp": round(delta_pp, 2),
            }
            if delta_pp < 0:
                out[drop_bucket].append(entry)
            elif delta_pp > 0:
                out[gain_bucket].append(entry)
    # Sort drops by largest drop first; gains by largest gain first.
    out["precision_drops"].sort(key=lambda e: e["delta_pp"])
    out["recall_drops"].sort(key=lambda e: e["delta_pp"])
    out["precision_gains"].sort(key=lambda e: -e["delta_pp"])
    out["recall_gains"].sort(key=lambda e: -e["delta_pp"])
    return out


def has_alert_drift(
    drift:           dict,
    threshold_pp:    float,
) -> bool:
    """Return True if any precision drop reaches the alert threshold."""
    return any(
        d["delta_pp"] <= -abs(threshold_pp)
        for d in drift.get("precision_drops", [])
    )


# ── Divergence query ──────────────────────────────────────────────────────
def query_divergences(
    brain_db_path:   "pathlib.Path | None" = None,
    *,
    lookback_days:   int = 7,
    top_n:           int = 20,
) -> dict:
    """Pull recent intent_divergences slices for the report.

    Returns dict with keys:
      - low_confidence_gates: top N gate decisions where structured_confidence < 0.80
      - rejections:           top N rows where gate_decision LIKE 'reject%'
      - shadow_samples:       top N rows where mode = 'shadow'
      - mode_counts:          {gate: N, shadow: N} totals over the window
      - missing:              True if brain_db unavailable / mode column absent
    """
    if brain_db_path is None:
        brain_db_path = _REPO_ROOT / "faces" / "brain.db"
    out: dict = {
        "low_confidence_gates": [],
        "rejections":           [],
        "shadow_samples":       [],
        "mode_counts":          {"gate": 0, "shadow": 0},
        "missing":              False,
        "lookback_days":        lookback_days,
    }
    if not brain_db_path.exists():
        out["missing"] = True
        return out
    import sqlite3
    cutoff = time.time() - (lookback_days * 86400)
    try:
        conn = sqlite3.connect(str(brain_db_path))
        # Verify mode column exists (post-Session-119 migration).
        cols = {r[1] for r in conn.execute(
            "PRAGMA table_info(intent_divergences)"
        ).fetchall()}
        has_mode = "mode" in cols
        # Mode counts.
        if has_mode:
            for mode_val, count in conn.execute(
                "SELECT mode, COUNT(*) FROM intent_divergences "
                "WHERE ts >= ? GROUP BY mode",
                (cutoff,),
            ).fetchall():
                out["mode_counts"][str(mode_val or "gate")] = int(count)
        else:
            count = conn.execute(
                "SELECT COUNT(*) FROM intent_divergences WHERE ts >= ?",
                (cutoff,),
            ).fetchone()[0]
            out["mode_counts"]["gate"] = int(count)

        # Low-confidence gate decisions.
        mode_filter = "AND mode = 'gate' " if has_mode else ""
        rows = conn.execute(
            "SELECT ts, person_id, user_text, structured_intent, "
            "structured_extracted, structured_confidence, tool_proposed, "
            "gate_decision FROM intent_divergences "
            f"WHERE ts >= ? {mode_filter}"
            "AND structured_confidence IS NOT NULL "
            "AND structured_confidence < 0.80 "
            "ORDER BY structured_confidence ASC LIMIT ?",
            (cutoff, top_n),
        ).fetchall()
        out["low_confidence_gates"] = [
            {
                "ts": r[0], "person_id": r[1], "user_text": r[2],
                "intent": r[3], "extracted": r[4], "confidence": r[5],
                "tool": r[6], "decision": r[7],
            }
            for r in rows
        ]

        # Rejections.
        rows = conn.execute(
            "SELECT ts, person_id, user_text, structured_intent, "
            "structured_confidence, tool_proposed, gate_decision "
            "FROM intent_divergences "
            f"WHERE ts >= ? {mode_filter}"
            "AND gate_decision LIKE 'reject%' "
            "ORDER BY ts DESC LIMIT ?",
            (cutoff, top_n),
        ).fetchall()
        out["rejections"] = [
            {
                "ts": r[0], "person_id": r[1], "user_text": r[2],
                "intent": r[3], "confidence": r[4],
                "tool": r[5], "decision": r[6],
            }
            for r in rows
        ]

        # Shadow samples.
        if has_mode:
            rows = conn.execute(
                "SELECT ts, person_id, user_text, structured_intent, "
                "structured_confidence FROM intent_divergences "
                "WHERE ts >= ? AND mode = 'shadow' "
                "ORDER BY ts DESC LIMIT ?",
                (cutoff, top_n),
            ).fetchall()
            out["shadow_samples"] = [
                {
                    "ts": r[0], "person_id": r[1], "user_text": r[2],
                    "intent": r[3], "confidence": r[4],
                }
                for r in rows
            ]
        conn.close()
    except Exception as ex:
        print(f"[eval_weekly] divergence query failed: {ex!r}", file=sys.stderr)
        out["missing"] = True
    return out


# ── Markdown formatter ────────────────────────────────────────────────────
def _fmt_pct(v: "float | None", digits: int = 2) -> str:
    if v is None:
        return "n/a"
    return f"{float(v) * 100.0:.{digits}f}%"


def _fmt_pp(v: "float | None") -> str:
    if v is None:
        return "n/a"
    return f"{float(v):+.2f}pp"


def render_report(
    *,
    current_metrics: dict,
    current_metadata: dict,
    prior_metrics:    "dict | None",
    prior_metadata:   "dict | None",
    drift:            dict,
    divergences:      dict,
    alert_threshold_pp: float,
    alert_active:     bool,
) -> str:
    """Compose the markdown report. Pure function — testable."""
    parts: list[str] = []
    parts.append("# Phase 5 — Weekly Eval Report")
    parts.append("")
    cur_hash = (current_metadata or {}).get("classifier_prompt_hash", "?")
    pri_hash = (prior_metadata or {}).get("classifier_prompt_hash") if prior_metadata else None
    cur_ts   = (current_metadata or {}).get("run_ts", "?")
    pri_ts   = (prior_metadata or {}).get("run_ts", "?") if prior_metadata else "(no prior run)"
    parts.append(f"- **Current run**: {cur_ts}  hash=`{cur_hash}`")
    parts.append(f"- **Prior run**: {pri_ts}  hash=`{pri_hash or '(none)'}`")
    parts.append(f"- **Hash baseline status**: "
                 f"{'UNCHANGED' if pri_hash == cur_hash else 'CHANGED — Phase 5 drift baseline reset'}")
    parts.append("")

    # Headline reflects actual drift state, independent of --alert flag.
    # --alert only controls exit code, not the report's substance.
    has_drift = bool([
        d for d in drift.get("precision_drops", [])
        if d["delta_pp"] <= -abs(alert_threshold_pp)
    ])
    if prior_metrics is None:
        parts.append("## Headline: first persisted run — no drift comparison possible")
    elif has_drift:
        parts.append(
            f"## Headline: ALERT — per-intent precision dropped >= {alert_threshold_pp:.1f}pp"
        )
    else:
        parts.append("## Headline: PASS — no alert-threshold drift detected")
    parts.append("")

    # Per-intent drift table.
    if prior_metrics is not None:
        parts.append("## Per-intent metrics drift (hybrid subset)")
        parts.append("")
        parts.append("| Intent | Precision (cur) | Precision (prior) | delta pp | Recall (cur) | Recall (prior) | delta pp |")
        parts.append("|---|---:|---:|---:|---:|---:|---:|")
        cur_pi = (current_metrics.get("hybrid") or {}).get("per_intent") or {}
        pri_pi = (prior_metrics.get("hybrid") or {}).get("per_intent") or {}
        intents = sorted(set(cur_pi) | set(pri_pi))
        for intent in intents:
            cur_p = cur_pi.get(intent, {}).get("precision")
            pri_p = pri_pi.get(intent, {}).get("precision")
            cur_r = cur_pi.get(intent, {}).get("recall")
            pri_r = pri_pi.get(intent, {}).get("recall")
            d_p   = (None if cur_p is None or pri_p is None
                     else round((cur_p - pri_p) * 100.0, 2))
            d_r   = (None if cur_r is None or pri_r is None
                     else round((cur_r - pri_r) * 100.0, 2))
            parts.append(
                f"| {intent} | {_fmt_pct(cur_p)} | {_fmt_pct(pri_p)} | {_fmt_pp(d_p)} "
                f"| {_fmt_pct(cur_r)} | {_fmt_pct(pri_r)} | {_fmt_pp(d_r)} |"
            )
        parts.append("")
        # Spotlight any drops at or beyond the alert threshold.
        flagged = [
            d for d in drift.get("precision_drops", [])
            if d["delta_pp"] <= -abs(alert_threshold_pp)
        ]
        if flagged:
            parts.append(f"### Precision drops >= {alert_threshold_pp:.1f}pp")
            for d in flagged:
                parts.append(
                    f"- **{d['intent']}**: {d['prior']:.4f} -> {d['current']:.4f} "
                    f"({d['delta_pp']:+.2f}pp)"
                )
            parts.append("")

    # Divergence summary.
    parts.append(f"## Divergences (last {divergences.get('lookback_days', 7)} days)")
    if divergences.get("missing"):
        parts.append("- (brain.db unavailable or `mode` column not migrated; skipping)")
    else:
        mc = divergences.get("mode_counts", {})
        parts.append(
            f"- Total rows: gate={mc.get('gate', 0)}, "
            f"shadow={mc.get('shadow', 0)}"
        )
    parts.append("")

    if divergences.get("low_confidence_gates"):
        parts.append("### Top low-confidence gate decisions")
        for d in divergences["low_confidence_gates"]:
            uxt = (d.get("user_text") or "")[:80]
            parts.append(
                f"- conf={d.get('confidence'):.2f} intent={d.get('intent')!r} "
                f"tool={d.get('tool')!r} decision={d.get('decision')!r}  user={uxt!r}"
            )
        parts.append("")

    if divergences.get("rejections"):
        parts.append("### Recent rejections (for false-reject review)")
        for d in divergences["rejections"]:
            uxt = (d.get("user_text") or "")[:80]
            parts.append(
                f"- decision={d.get('decision')!r} intent={d.get('intent')!r} "
                f"tool={d.get('tool')!r}  user={uxt!r}"
            )
        parts.append("")

    if divergences.get("shadow_samples"):
        parts.append("### Recent shadow samples (mode='shadow')")
        for d in divergences["shadow_samples"]:
            uxt = (d.get("user_text") or "")[:80]
            parts.append(
                f"- intent={d.get('intent')!r} conf="
                f"{(d.get('confidence') or 0):.2f}  user={uxt!r}"
            )
        parts.append("")

    return "\n".join(parts)


# ── Main ──────────────────────────────────────────────────────────────────
async def _do_live_bench():
    rows = load_golden()
    predictions, duration, _timeouts = await _run_live_bench(rows)
    return rows, predictions, duration


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--alert", action="store_true",
        help="Exit non-zero if any per-intent precision drops by "
             "EVAL_WEEKLY_ALERT_PRECISION_DROP_PP percentage points or more.",
    )
    parser.add_argument(
        "--no-live", action="store_true",
        help="Skip the live bench. Use the most recent persisted run as the "
             "'current' run instead. Faster for testing the report-generator path.",
    )
    args = parser.parse_args(argv)

    alert_pp, lookback_days, top_n = _config()

    if args.no_live:
        runs = _list_runs()
        if not runs:
            print("[eval_weekly] no persisted runs; cannot --no-live", file=sys.stderr)
            return 2
        current_path = runs[0]
        current_doc  = load_run(current_path)
    else:
        from core.brain import _INTENT_CLASSIFIER_SYSTEM
        rows, predictions, duration = asyncio.run(_do_live_bench())
        metrics = compute_metrics(rows, predictions)
        metadata = collect_metadata(
            row_count=len(rows),
            live_calls=len(rows),
            total_cost_usd=0.0,
            duration_secs=duration,
            classifier_system_prompt=_INTENT_CLASSIFIER_SYSTEM,
        )
        mismatches = collect_mismatches(rows, predictions)
        current_path = save_run(metrics, metadata, mismatches)
        current_doc  = {"metrics": metrics, "metadata": metadata}

    prior_path = find_prior_run(current_path)
    prior_doc  = load_run(prior_path) if prior_path else None

    drift = (
        compute_drift(current_doc["metrics"], prior_doc["metrics"])
        if prior_doc else
        {"precision_drops": [], "recall_drops": [],
         "precision_gains": [], "recall_gains": []}
    )

    divergences = query_divergences(
        lookback_days=lookback_days, top_n=top_n,
    )

    alert_active = args.alert and has_alert_drift(drift, alert_pp)

    report = render_report(
        current_metrics=current_doc["metrics"],
        current_metadata=current_doc["metadata"],
        prior_metrics=(prior_doc["metrics"] if prior_doc else None),
        prior_metadata=(prior_doc["metadata"] if prior_doc else None),
        drift=drift,
        divergences=divergences,
        alert_threshold_pp=alert_pp,
        alert_active=alert_active,
    )
    print(report)

    if args.alert and alert_active:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
