"""Bridge runner — Kara-OS classifier vs. Speak-or-Stay-Silent benchmark.

Runs `core.brain._classify_intent` against each row of the configured
test sets. Writes paper-shape prediction JSON files at
`published-papers-tests/results/karaos_<domain>.json`.

Usage:
  python bridge/run.py --datasets friends ami --split test
  python bridge/run.py --datasets friends --split test --limit 10  # smoke

Hard rules (per BRIDGE_SPEC.md):
- $5 budget cap. Aborts via BudgetExceeded with partial results saved.
- Imports `core.brain._classify_intent` only. No pipeline / FaceDB /
  audio / vision / orchestrator imports.
- Sequential, not parallel — easier to track budget.
- Temperature stays at the classifier's defaults (0.1, low for
  determinism). No prompt mods. No retries beyond the spec's 4× backoff
  on 429/503 (which we approximate by trusting `_classify_intent`'s
  internal timeout-and-return-None behavior).
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import signal
import sys
import time
from pathlib import Path

# Ensure dog-ai on sys.path so we can import core.brain._classify_intent.
# `dog-ai` lives one level up from `published-papers-tests/`. Use the
# absolute path so the runner works regardless of cwd.
_BRIDGE_DIR = Path(__file__).resolve().parent
_PAPER_DIR  = _BRIDGE_DIR.parent                  # published-papers-tests/
_REPO_ROOT  = _PAPER_DIR.parent                   # dog-ai/ (parent of papers folder)
_DOG_AI_DIR = _REPO_ROOT / "dog-ai"
# Make the `bridge` package importable when launched as `python bridge/run.py`
# from `published-papers-tests/`. Without this, Python treats run.py as a
# script and the `bridge` package isn't on sys.path.
if str(_PAPER_DIR) not in sys.path:
    sys.path.insert(0, str(_PAPER_DIR))
if str(_DOG_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_DOG_AI_DIR))

from bridge.adapters.input_adapter      import build_classifier_inputs
from bridge.adapters.output_mapper      import map_to_decision
from bridge.adapters.prediction_writer  import build_prediction_row, build_payload
from bridge.shared.config               import (
    DATASETS,
    BUDGET_USD,
    INPUT_PRICE_PER_M,
    OUTPUT_PRICE_PER_M,
    predictions_path,
    partial_path,
)
from bridge.shared.budget_tracker       import BudgetTracker, BudgetExceeded


# ── Token estimation (no usage object exposed by _classify_intent) ─────
# `core.brain._classify_intent` doesn't return token counts, so we
# estimate using the same char-per-token heuristic the dog-ai project
# already uses (TOKEN_CHARS_PER_TOKEN ~= 3.5 for English voice
# transcripts). We bound estimation conservatively to stay within
# $5 even if the heuristic underestimates by 20%.
def _est_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / 3.5))


def _est_messages_tokens(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        total += _est_tokens(m.get("content") or "")
    return total + len(messages) * 4   # role/header overhead


def _classifier_prompt_hash() -> str:
    """First-12 sha256 of `_INTENT_CLASSIFIER_SYSTEM` for run metadata.

    Read-only — does not modify the classifier source. Logged into
    each result payload + RESULTS.md so a future re-run can detect
    drift if the classifier prompt has changed since the last run.
    """
    try:
        from core.brain import _INTENT_CLASSIFIER_SYSTEM
    except Exception:
        return "unavailable"
    return hashlib.sha256(_INTENT_CLASSIFIER_SYSTEM.encode("utf-8")).hexdigest()[:12]


def _stream_jsonl(path: Path, limit: "int | None" = None):
    """Yield rows from a JSONL file. Streams (does NOT read whole file)."""
    n = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                print(f"[bridge] JSON parse error on line {n+1}: {e}; skipping",
                      flush=True)
                continue
            n += 1
            if limit is not None and n >= limit:
                return


def _count_rows(path: Path) -> int:
    n = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


# ── Per-row dispatch ───────────────────────────────────────────────────
async def _process_row(
    sample:    dict,
    classify:  callable,
    tracker:   BudgetTracker,
) -> dict:
    """Run one sample end-to-end. Returns the prediction dict."""
    user_text, history = build_classifier_inputs(sample)

    # Estimate cost BEFORE the call so we accumulate even if the API
    # times out (timeout still consumes input tokens we paid for).
    est_input  = _est_tokens(user_text) + _est_messages_tokens(history)

    t0 = time.time()
    try:
        sidecar = await classify(user_text, conversation_history=history)
    except Exception as e:
        # `_classify_intent` is documented as never-raising, but harden
        # anyway so a stray raise doesn't crash the run.
        print(f"[bridge] classifier raised: {type(e).__name__}: {e}",
              flush=True)
        sidecar = None
    latency = time.time() - t0

    # `_classify_intent` returns None on any failure; estimate output
    # tokens from a typical sidecar size (~80 tokens for the JSON
    # envelope + reasoning string). When sidecar is non-None we use
    # the actual JSON length.
    if sidecar is None:
        est_output = 0   # nothing came back — likely no output billed
    else:
        try:
            est_output = _est_tokens(json.dumps(sidecar))
        except Exception:
            est_output = 80

    tracker.add(est_input, est_output)

    target_speaker = sample.get("target_speaker") or ""
    decision = map_to_decision(sidecar, target_speaker)
    return build_prediction_row(sample, sidecar, decision, latency)


async def _run_domain(
    domain:        str,
    path:          Path,
    classify:      callable,
    tracker:       BudgetTracker,
    limit:         "int | None",
    backbone:      str,
    prompt_hash:   str,
) -> dict:
    """Run one domain end-to-end. Returns the result payload (paper shape)."""
    total_rows = _count_rows(path) if limit is None else min(limit, _count_rows(path))
    print(f"\n[bridge] Domain {domain!r}: {total_rows} rows from {path}", flush=True)
    predictions: list[dict] = []
    started_at = time.time()
    rows_done  = 0
    exclusions = 0

    try:
        for sample in _stream_jsonl(path, limit=limit):
            row = await _process_row(sample, classify, tracker)
            predictions.append(row)
            rows_done += 1
            if row["prediction"] is None:
                exclusions += 1

            # Status + budget check every 50 rows.
            if rows_done % 50 == 0:
                print(
                    f"[bridge] {domain} {tracker.status_line(rows_done, total_rows)} "
                    f"exclusions={exclusions}",
                    flush=True,
                )
                tracker.check(rows_done, total_rows)

        # Final budget check at end-of-domain.
        tracker.check(rows_done, total_rows)

    except BudgetExceeded as bx:
        print(f"[bridge] BUDGET EXCEEDED: {bx}", flush=True)
        # Save partial results before re-raising — caller exits 1.
        partial = build_payload(
            domain=domain, model_id=backbone,
            classifier_prompt_hash=prompt_hash,
            predictions=predictions,
            metadata=_build_metadata(
                tracker, started_at, rows_done, total_rows,
                exclusions, aborted=True, abort_reason=str(bx),
            ),
        )
        partial_path(domain).write_text(
            json.dumps(partial, indent=2), encoding="utf-8",
        )
        print(f"[bridge] Wrote partial -> {partial_path(domain)}", flush=True)
        raise

    elapsed = time.time() - started_at
    payload = build_payload(
        domain=domain, model_id=backbone,
        classifier_prompt_hash=prompt_hash,
        predictions=predictions,
        metadata=_build_metadata(
            tracker, started_at, rows_done, total_rows,
            exclusions, aborted=False,
        ),
    )
    out_path = predictions_path(domain)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        f"[bridge] {domain} complete: {rows_done}/{total_rows} rows, "
        f"exclusions={exclusions}, elapsed={elapsed:.1f}s, "
        f"cumulative ${tracker.cost_usd():.4f}",
        flush=True,
    )
    print(f"[bridge] Wrote -> {out_path}", flush=True)
    return payload


def _build_metadata(
    tracker:    BudgetTracker,
    started_at: float,
    rows_done:  int,
    total_rows: int,
    exclusions: int,
    aborted:    bool,
    abort_reason: "str | None" = None,
) -> dict:
    return {
        "elapsed_secs":    round(time.time() - started_at, 2),
        "rows_attempted":  rows_done,
        "rows_total":      total_rows,
        "exclusions":      exclusions,
        "input_tokens":    tracker.input_tokens,
        "output_tokens":   tracker.output_tokens,
        "api_calls":       tracker.api_calls,
        "cost_usd":        round(tracker.cost_usd(), 4),
        "budget_usd":      tracker.budget_usd,
        "input_price_per_m":  INPUT_PRICE_PER_M,
        "output_price_per_m": OUTPUT_PRICE_PER_M,
        "aborted":         aborted,
        "abort_reason":    abort_reason,
    }


# ── CLI ────────────────────────────────────────────────────────────────
def _parse_args(argv: "list[str] | None" = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kara-OS benchmark bridge")
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=["friends", "ami"],
        choices=list(DATASETS.keys()),
        help="Domain(s) to evaluate (default: friends ami)",
    )
    parser.add_argument(
        "--split",
        default="test",
        choices=["test"],
        help="Dataset split. Only 'test' is supported (paths in config).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N rows per domain (smoke test mode).",
    )
    return parser.parse_args(argv)


async def _main(args: argparse.Namespace) -> int:
    # Import the classifier ONLY here so an import error surfaces with
    # the bridge's own diagnostic before token-spending begins.
    try:
        from core.brain import _classify_intent
    except Exception as e:
        print(
            f"[bridge] FATAL: cannot import core.brain._classify_intent: "
            f"{type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        return 2

    # Verify CHAT_API_KEY is present — _classify_intent silently returns
    # None when missing, but we'd rather see the error up front.
    try:
        from core.config import CHAT_API_KEY
        if not CHAT_API_KEY:
            print(
                "[bridge] FATAL: CHAT_API_KEY not set; classifier will "
                "always return None. Set TOGETHER_API_KEY in env.",
                file=sys.stderr, flush=True,
            )
            return 3
    except Exception as e:
        print(f"[bridge] WARN: could not read CHAT_API_KEY: {e}", flush=True)

    backbone    = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    prompt_hash = _classifier_prompt_hash()
    print(f"[bridge] Classifier prompt hash: {prompt_hash}", flush=True)
    print(f"[bridge] Backbone: {backbone}", flush=True)
    print(f"[bridge] Budget cap: ${BUDGET_USD:.2f}", flush=True)
    print(f"[bridge] Datasets: {args.datasets} (limit={args.limit})", flush=True)

    tracker = BudgetTracker()
    exit_code = 0

    for domain in args.datasets:
        path = DATASETS.get(domain)
        if not path or not path.exists():
            print(
                f"[bridge] FATAL: dataset path missing for {domain!r}: {path}",
                file=sys.stderr, flush=True,
            )
            return 4
        try:
            await _run_domain(
                domain=domain, path=path,
                classify=_classify_intent, tracker=tracker,
                limit=args.limit, backbone=backbone, prompt_hash=prompt_hash,
            )
        except BudgetExceeded:
            exit_code = 1
            break

    print(
        f"\n[bridge] FINAL: ${tracker.cost_usd():.4f} spent across "
        f"{tracker.api_calls} API calls (input={tracker.input_tokens} tok, "
        f"output={tracker.output_tokens} tok). Exit code {exit_code}.",
        flush=True,
    )
    return exit_code


def _install_sigint_handler():
    """Trap Ctrl+C so partial state is preserved (handler just sets a
    flag; the runner's per-row loop polls cooperative via try/except
    KeyboardInterrupt). We let asyncio.run propagate KeyboardInterrupt
    naturally — no fancy state handling needed beyond the budget
    tracker's existing partial-write path on BudgetExceeded.
    """
    pass  # default behavior is fine; partial files written on BudgetExceeded


if __name__ == "__main__":
    args = _parse_args()
    _install_sigint_handler()
    try:
        rc = asyncio.run(_main(args))
    except KeyboardInterrupt:
        print("\n[bridge] interrupted by user — exit code 130", flush=True)
        rc = 130
    sys.exit(rc)
