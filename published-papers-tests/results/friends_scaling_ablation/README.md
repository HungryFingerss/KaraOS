# Friends benchmark — scaling ablation (2026-05-01)

A 10-run ablation study testing how the graph classifier's accuracy on Friends changes as the size of its retrieval scenario database changes. Prompted by Amit Yadav's review on LinkedIn, where he asked two specific methodology questions:

1. Does accuracy change with the number of abstracted scenarios?
2. What is the standard deviation across multiple runs with random subsets?

This folder is the answer.

---

## What this folder contains

- `ABLATION_RESULTS.md` — the full result narrative: scaling table, variance analysis, source-DB composition, findings, reproduction. **Read this first.**
- `METHODOLOGY.md` — the procedural detail: how subsets were built (stratified sampling), the isolation contract that protected the production DB during testing, run order, what counted as an ablation DB vs. a production DB.
- `ablation_summary.json` — machine-readable aggregate statistics (mean ± std per N, full-DB baseline).
- `individual_runs/` — every individual run's outputs:
  - `ablation_run_N{N}_seed{S}.md` — per-run narrative with that run's stats and confusion matrix
  - `ablation_summary_N{N}_seed{S}.json` — machine-readable per-run stats
  - `karaos_friends_graph_N{N}_seed{S}.json` — raw per-row predictions for that run (re-scorable)
  - `ablation_run_full.md`, `ablation_summary_full.json`, `karaos_friends_graph_full.json` — the deterministic full-DB run (no seed; identical inputs every time)

---

## Headline result

**Inverse scaling.** Smaller scenario DBs score *higher* on the Friends benchmark — the opposite of what was expected.

| N (scenarios) | Balanced accuracy (mean) | Std dev | Range |
|---|---:|---:|---|
| 500 | **0.6919** | ±0.0261 | [0.6644, 0.7270] |
| 1000 | 0.6835 | ±0.0075 | [0.6731, 0.6907] |
| 1500 | 0.6677 | ±0.0026 | [0.6646, 0.6709] |
| 2071 (full) | 0.6448 | — | (deterministic) |

Two findings come out of this:

1. **The curve is monotonically decreasing.** Adding more scenarios hurts rather than helps accuracy on Friends specifically. The full 2,071-scenario DB scores ~6.5 percentage points below the best 500-scenario subset. Diagnosis: in k-NN cosine retrieval, larger DBs introduce more confusable near-neighbors from heterogeneous-quality bootstrap corpora. A compact DB has a higher density of high-signal scenarios per query.

2. **Variance collapses as N grows.** At N=500, standard deviation is ±2.6pp across 3 random seeds (one seed scored 0.7270, another 0.6644 — a 6.3pp gap from sampling alone). By N=1500, std dev is ±0.26pp. At N=2071 (full), variance is zero by construction — same inputs every run.

---

## What the result is NOT saying

- **It is not saying KaraOS should ship at N=500.** Friends is a benchmark, not the production target distribution. The full DB has broader intent coverage and is better calibrated for live traffic.
- **It is not a problem with the graph classifier architecture per se.** The diagnosis points at bootstrap-corpus quality heterogeneity (Cornell + DailyDialog + Empathetic + hand-authored mix) — different corpora contribute scenarios of different relevance to Friends-style sitcom dialogue. The same architecture might show flat or upward scaling on a test corpus closer to one of the bootstrap sources.
- **It is not yet replicated on a different test corpus.** A planned next experiment will run the same ablation against AMI to disentangle "is this Friends-specific or fundamental." That experiment is queued but not yet run.

---

## Isolation guarantee

Production safety was a hard constraint. The ablation suite never wrote to or modified the production classifier DB at `dog-ai/data/classifier_scenarios.db`. Reads were performed via a read-only handle. All ablation databases were built into a separate `published-papers-tests/ablation_dbs/` directory. The graph classifier was routed at runtime via a `CLASSIFIER_DB_PATH_OVERRIDE` environment variable so the production code path could remain untouched.

After all 10 runs:
- Production DB mtime: unchanged
- Production audit log: zero new entries
- Production code: zero edits

Full isolation contract details in [`METHODOLOGY.md`](METHODOLOGY.md).

---

## Honest cost note

Each of the 10 runs cost **$0.00** in actual API spend. The graph classifier uses `intfloat/multilingual-e5-large-instruct` loaded locally on GPU — there are no API calls in the classification hot path. The bridge's cost-tracking software reported approximately $0.099 per run by mistakenly applying Llama-3.3-70B pricing to local-embedding token counts; this is a phantom figure that does not reflect actual spend. The cost field is left in the per-run JSONs as it was generated, with this caveat noted here so any researcher reproducing the test isn't misled.

Total compute time across all 10 runs: ~12 minutes.
