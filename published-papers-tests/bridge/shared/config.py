"""Bridge configuration constants. Single source of truth for paths,
prices, and the budget cap so the runner script + budget tracker see
exactly the same numbers.
"""
from __future__ import annotations

from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────
BRIDGE_DIR  = Path(__file__).resolve().parent.parent
ROOT_DIR    = BRIDGE_DIR.parent                          # published-papers-tests/
DATASET_DIR = ROOT_DIR / "dataset"
RESULTS_DIR = ROOT_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Budget ────────────────────────────────────────────────────────────────
# Hard $5 cap. Runner aborts when cumulative spend crosses this AND any
# projection from in-progress data also exceeds this. No override flag.
BUDGET_USD = 5.00

# Together.ai pricing for meta-llama/Llama-3.3-70B-Instruct-Turbo.
# Verify against Together.ai dashboard before run; update here if rates
# changed. Per the spec: input $0.88/M, output $0.88/M.
INPUT_PRICE_PER_M  = 0.88
OUTPUT_PRICE_PER_M = 0.88

# ── Datasets ──────────────────────────────────────────────────────────────
DATASETS = {
    "friends": DATASET_DIR / "friends" / "test" / "test_samples.jsonl",
    "ami":     DATASET_DIR / "ami"     / "test" / "test_samples.jsonl",
}

# ── Output paths ──────────────────────────────────────────────────────────
def predictions_path(domain: str) -> Path:
    return RESULTS_DIR / f"karaos_{domain}.json"


def partial_path(domain: str) -> Path:
    return RESULTS_DIR / f"karaos_{domain}.partial.json"
