# Bridge — Kara-OS vs. Speak-or-Stay-Silent Benchmark

Runs Kara-OS's classifier (`core.brain._classify_intent`) against the
paper's test set without touching any of the dog-ai system. Predictions
land in `published-papers-tests/results/karaos_<domain>.json` in the
paper's exact JSON shape so downstream metric code can compute
balanced-accuracy / F1 / per-category numbers.

## Architecture

```
bridge/
├── __init__.py
├── run.py                       # main runner — handles Friends + AMI
├── adapters/
│   ├── __init__.py
│   ├── input_adapter.py         # source row → classifier inputs (4 ALLOWED fields only)
│   ├── output_mapper.py         # classifier sidecar → SPEAK / SILENT
│   └── prediction_writer.py     # build prediction-JSON shape (paper-compatible)
├── shared/
│   ├── __init__.py
│   ├── budget_tracker.py        # $5 cumulative cost cap with abort
│   └── config.py                # paths, prices, BUDGET_USD = 5.00
└── README.md                    # you are here
```

## Hard rules

1. **Bridge does not modify dog-ai.** Read-only import of
   `core.brain._classify_intent`. No edits to any file in `dog-ai/`.
2. **6 forbidden fields never reach the classifier.** `decision`,
   `category`, `target_is_addressed`, `addressees_in_current`, `reason`,
   `confidence` are read ONLY by `prediction_writer.py` to fill the
   ground-truth columns of the output JSON.
3. **No pipeline / FaceDB / audio / vision imports.** The bridge calls
   one function per row. That's it.
4. **$5 budget cap, hard enforced.** No `--force` override.

## Running

```bash
# from C:\Users\jagan\dog-ai\published-papers-tests\
cd bridge

# Smoke test FIRST — mandatory, 10 rows from each domain.
python run.py --datasets friends ami --split test --limit 10

# Full run (after smoke is clean)
python run.py --datasets friends ami --split test
```

`CHAT_API_KEY` (Together.ai) must be set in env. The runner aborts up
front if it's missing.

## Cost projections

| Run                          | Rows  | Estimated cost |
|------------------------------|-------|----------------|
| Smoke (10 rows × 2 domains)  |    20 |          ~$0.04 |
| Friends test                 | 1,287 |          ~$1.50 |
| AMI test                     | 1,410 |          ~$1.65 |
| **Total expected**           | **2,697** |      **~$3.20** |

Cap is `$5.00` with ~$1.80 buffer. SPGI (9,929 rows ≈ $11.50) is
explicitly out of scope for this session per BRIDGE_SPEC.md.

## Cost tracking

The runner accumulates input + output token counts after every API call
and prints a status line every 50 rows:

```
[bridge] friends [$0.42 spent / $5.00 cap | 234/1287 rows | proj total ~$2.31] exclusions=12
```

If cumulative spend reaches `$5.00` OR a linear projection from
`rows_done >= 50` exceeds `$5.00`, the runner raises `BudgetExceeded`,
writes partial results to `karaos_<domain>.partial.json`, and exits 1.

## Failure modes

| Situation                            | Behavior                                                              |
|--------------------------------------|-----------------------------------------------------------------------|
| `_classify_intent` returns `None`     | Mark prediction as `null`. Counted in `exclusions`, NOT counted wrong. |
| Together.ai 429 / 503                 | `_classify_intent` already retries with backoff; we trust its return. |
| Cumulative cost crosses `$5.00`       | Abort, write `*.partial.json`, exit 1.                                |
| Ctrl+C                                | KeyboardInterrupt propagates; partial state intact on disk. Exit 130. |

## Output shape

Paper-compatible JSON wrapper:

```json
{
  "dataset": "friends",
  "model_key": "karaos",
  "model_id": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
  "system_prompt_repeat": 1,
  "predictions": [
    {
      "sample_id": "...",
      "ground_truth": "SPEAK",
      "prediction": "SPEAK | SILENT | null",
      "category": "SPEAK_explicit",
      "output_text": "<JSON-stringified classifier dict, or 'NULL'>",
      "latency": 0.42,
      "target_speaker": "ross",
      "all_speakers": ["rachel", "ross"],
      "context_turns": [...],
      "context_turns_total": 0,
      "current_turn": {...},
      "confidence": "high"
    }
  ],
  "bridge_metadata": {
    "elapsed_secs": 487.3,
    "rows_attempted": 1287,
    "rows_total": 1287,
    "exclusions": 12,
    "input_tokens": 412345,
    "output_tokens": 102233,
    "api_calls": 1287,
    "cost_usd": 0.4523,
    "budget_usd": 5.0,
    "input_price_per_m": 0.88,
    "output_price_per_m": 0.88,
    "aborted": false,
    "abort_reason": null,
    "classifier_prompt_hash": "df9ae2a1cdde"
  }
}
```

## Computing metrics

After the run completes, hand the result file to the paper's metric
module:

```bash
cd ../code
python -c "
from benchmarking.metrics import compute_metrics
import json
for domain in ['friends', 'ami']:
    data = json.load(open(f'../results/karaos_{domain}.json'))
    print(f'{domain.upper()}:', compute_metrics(data['predictions']))
"
```
