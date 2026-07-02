# Methodology — Friends scaling ablation (2026-05-01)

The procedural detail behind the ablation study. Companion to [`README.md`](README.md) (which has the headline result) and [`ABLATION_RESULTS.md`](ABLATION_RESULTS.md) (which has the full narrative).

---

## The two questions being tested

From Amit Yadav's review on LinkedIn:

1. **Scaling curve.** "It might be worth to see if accuracy changes depending on number of abstracted scenarios."
2. **Variance.** "Standard deviation over multiple runs using random initialization of abstracted scenarios might be interesting."

We interpreted "random initialization" as random subsets of the production scenario DB (interpretation A) rather than re-running the bootstrap pipeline with a different seed (interpretation B). Either is a defensible read. Interpretation A tests retrieval-side sampling stability; interpretation B would test abstraction-pipeline stability. Interpretation B requires the bootstrap pipeline to be re-run end-to-end (~$5-15 in Together.ai cost), so we deferred it. The result here answers question A.

---

## The 10-run matrix

| Run | DB size (N) | Subset seed | What it tests |
|---|---:|---:|---|
| 1 | 500 | 11 | Variance at N=500 |
| 2 | 500 | 22 | Variance at N=500 |
| 3 | 500 | 33 | Variance at N=500 |
| 4 | 1000 | 11 | Variance at N=1000 |
| 5 | 1000 | 22 | Variance at N=1000 |
| 6 | 1000 | 33 | Variance at N=1000 |
| 7 | 1500 | 11 | Variance at N=1500 |
| 8 | 1500 | 22 | Variance at N=1500 |
| 9 | 1500 | 33 | Variance at N=1500 |
| 10 | 2071 (full) | n/a | Deterministic baseline |

3 random seeds × 3 sub-sizes + 1 deterministic full run = 10 runs. Per-row Friends predictions captured for each, allowing independent re-scoring.

---

## Building the ablation databases

Each ablation DB was constructed by:

1. Connecting **read-only** to the production classifier DB at `dog-ai/data/classifier_scenarios.db` (URI mode `file:...?mode=ro`, no write handle ever created).
2. Reading every active scenario along with its embedding, intent label, source tag, and metadata.
3. Grouping by `source_tag` (one of: `cornell`, `dailydialog`, `empathetic_dialogues`, `hand_authored`, `live_correction`).
4. **Stratified sampling** within each source group: for each source, take `int(N × group_ratio)` rows using Python's `random.Random(seed)` so seeds are reproducible.
5. Writing the sampled rows to a fresh SQLite file at `published-papers-tests/ablation_dbs/classifier_N{N}_seed{S}.db` via the standard `ClassifierDB.add_scenario()` API.
6. Verifying row counts match expected before declaring the DB ready.

Stratification is non-negotiable. Pure-uniform random sampling would let a 500-row subset accidentally over-represent or under-represent a single source corpus, contaminating the result with composition variance. The stratified approach preserves the production ratio (Cornell 46.8%, DailyDialog 19.0%, EmpatheticDialogues 14.4%, hand-authored 19.9%) at every N.

---

## Production isolation contract

Five safeguards combined to guarantee no production state was modified:

1. **Read-only DB handle** during scenario reads. A write attempt would fail at the SQLite level.
2. **Separate ablation DB directory** (`published-papers-tests/ablation_dbs/`) physically distinct from the production data directory (`dog-ai/data/`).
3. **`CLASSIFIER_DB_PATH_OVERRIDE` environment variable** — when set, the graph classifier consults the override path instead of `core.config.CLASSIFIER_DB_PATH`. Default unset, meaning production runtime always sees the production DB.
4. **Production code untouched.** No edits to `core/classifier_graph.py`, `core/classifier_db.py`, or any production module. The override mechanism was added behind the env var as a five-line read-time check that defaults to the production path.
5. **Post-run verification.** After all 10 runs:
   - `data/classifier_scenarios.db` mtime: unchanged
   - `data/classifier_audit_log.jsonl` line count: unchanged (no new audit events)
   - `core/` and `pipeline.py` source: unchanged

If any one of these checks had failed, the suite would have been treated as potentially-corrupting and the production DB restored from backup before any further work.

---

## Scoring rule

Every run produced 1,287 per-row predictions on the Friends test set. Each prediction was scored against the test set's ground-truth label using the paper's `benchmarking/metrics.py:compute_metrics()` function (from the published evaluation code at https://github.com/ishikilabsinc/context_aware_modeling).

The headline metric is **balanced accuracy** — `(SPEAK_recall + SILENT_recall) / 2`. This is the metric the paper reports and the metric KaraOS's prior runs were measured on, so it's the directly comparable number.

Per-class precision, recall, F1, and confusion matrices are also captured in each `ablation_summary_N{N}_seed{S}.json` for completeness.

---

## What's deterministic and what isn't

- **Within a single (N, seed) configuration**, the ablation DB is deterministic — same scenarios every time the build script runs with that seed.
- **The graph classifier itself** is fully deterministic for a given DB — same query, same DB, same result every call.
- **The full-DB run (N=2071)** has no seed; it uses every scenario, so there's only one possible result.
- **Cross-seed variance** is therefore entirely attributable to *which* scenarios got sampled into that subset. That is the variance the std-dev numbers measure.

---

## What this study does NOT measure

- **Abstraction-pipeline variance.** Re-running the bootstrap with a different random seed (different LLM-classifier outputs, different NER masking choices) would test whether the abstraction step itself contributes variance. That's a separate experiment.
- **Across-corpus generalization.** Running the same study on AMI or another test corpus would test whether the inverse scaling is Friends-specific or fundamental to the architecture. This experiment is queued; results not yet available at the time of this writing.
- **Embedding-model variance.** The classifier uses E5-large-instruct. Different embedding models (BGE, OpenAI text-embedding-3, Voyage) would likely shift the curve. Not tested.
- **Different aggregation strategies.** The current scoring uses Wilson lower-bound confirmation-rate aggregation over top-K cosine matches. Alternative aggregations (distance-weighted voting, adaptive-K, hierarchical retrieval) might change the scaling shape. Architectural follow-up work; not part of this study.

---

## Reproducing a single run

```bash
cd dog-ai/published-papers-tests
python -m bridge.scripts.run_one_ablation \
    --n 500 --seed 11 \
    --source-db "../dog-ai/data/classifier_scenarios.db"
```

The script builds the ablation DB if not present, sets the env-var override, runs the bridge against Friends, writes results to `results/karaos_friends_graph_N500_seed11.json`, and prints a summary.

The full 10-run suite was executed via `bridge/scripts/run_ablation_suite.py` which orchestrates the matrix sequentially (no parallel runs, easier to debug, easier to abort).

---

## Honest limitations of this study

- N=3 random seeds at each size is enough to estimate variance to ~1 decimal place on accuracy, but a more rigorous study would use 5 or 10 seeds. We chose 3 to keep total wall-clock under 30 minutes.
- The "production DB" used as the source for sampling was itself a snapshot at the time of the study (~2,071 scenarios). As the production DB grows from real-world correction events, this study's sample of source data ages.
- The result is specific to this combination of (Friends test set, E5 embeddings, the production classifier's aggregation logic, this scenario corpus mix). Generalizing to "non-parametric retrieval shows inverse scaling" would require replication on different test corpora, embeddings, and aggregation methods. The qualitative finding is suggestive; it is not yet a published claim.
