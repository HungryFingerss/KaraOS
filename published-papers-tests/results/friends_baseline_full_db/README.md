# Friends benchmark — full-DB baseline runs

The two "current architecture" runs on the Friends test set, on the full unsubsampled scenario database. Both predictions live here for independent re-scoring.

---

## What this folder contains

- `predictions_llama_70b.json` — Run 1: KaraOS's original LLM-classifier path on Llama-3.3-70B-Instruct-Turbo (via Together.ai). 1,287 Friends test rows. **Balanced accuracy: 58.66%.**
- `predictions_graph_classifier.json` — Run 3: KaraOS's current graph-classifier path on the full 2,071-scenario DB. Same 1,287 Friends test rows. **Balanced accuracy: 64.48%.**

Run 2 (LLM classifier on Qwen-7B — the falsifying experiment that scored *below* baseline) lives in the sibling folder [`../friends_multi_backbone/`](../friends_multi_backbone/) because that test had a separate purpose.

---

## Why two runs in one folder

These are the two "production-realistic" runs against the full scenario DB. They use different classification mechanisms (LLM vs. graph) but the same test set, same scoring rule, and same input distribution. Keeping them together makes the architectural comparison readable in one place.

The full benchmark journey across all three runs is narrated in [`../RESULTS.md`](../RESULTS.md).

---

## Headline numbers

| Run | Classifier mechanism | Balanced acc. | SPEAK precision | SPEAK recall | SILENT recall |
|---|---|---:|---:|---:|---:|
| Run 1 (LLM on Llama-70B) | LLM classification, 70B reasoning | 58.66% | (see file) | (see file) | (see file) |
| Run 3 (graph classifier, full DB) | k-NN cosine retrieval over 2,071 scenarios; zero LLM in classification path | 64.48% | 80.21% | 15.19% | 96.39% |

The Run 3 numbers above are reproduced from `../friends_scaling_ablation/individual_runs/ablation_summary_full.json` — the deterministic full-DB result from the 2026-05-01 ablation suite. (An earlier graph-classifier run reported 64.56% — within run-to-run drift due to slight DB state differences; both numbers are real.)

---

## How to reproduce

```bash
# From dog-ai/published-papers-tests/
cd bridge

# Run 1 — LLM classifier on Llama-70B (default model)
python run.py --datasets friends --split test

# Run 3 — graph classifier (no LLM in classification)
python run.py --datasets friends --split test --use-graph-classifier
```

Both write predictions to `results/karaos_friends*.json`. Re-score with the paper's `benchmarking/metrics.py:compute_metrics()`.

---

## Honest notes

- Run 1's prediction file is the unsanitized version (raw text included) — for the redistributable sanitized version with text stripped, see `../karaos_friends_test.json`.
- Run 3 uses the production-state classifier DB. The DB grows over time as users explicitly correct the classifier (currently ~2,071 scenarios); the run captured here is the state on the date generated.
- Neither run involved any modification of model weights. Run 3 uses ~2,000 labeled scenarios as a retrieval corpus — non-parametric learning, distinct from fine-tuning. See the parent README's "Honest framing" section for the precise distinction.
- The Friends test set was strictly held out from the bootstrap data used to populate the classifier DB. Test-train integrity is intact.
