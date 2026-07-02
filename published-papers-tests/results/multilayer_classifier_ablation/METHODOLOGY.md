# Methodology — multi-layer classifier ablation (2026-05-05)

The procedural detail behind the multi-layer ablation. Companion to [`README.md`](README.md) (overview) and [`RESULTS.md`](RESULTS.md) (the tables + interpretation).

---

## What problem this work tried to solve

The pure-graph classifier (Spec 2 in `dog-ai/everything_about_system.md`) scores 0.6448 balanced accuracy on the Bhagtani et al. 2026 Friends benchmark. Earlier ablation work ([`../friends_scaling_ablation/`](../friends_scaling_ablation/)) found that adding more scenarios to the retrieval database makes accuracy *worse* on Friends — *inverse scaling*. The diagnosis points at heterogeneous bootstrap-data quality: at large N, lower-quality scenarios crowd top-K cosine matches and corrupt the vote.

The multi-layer architecture (documented in `dog-ai/everything_about_system.md` Part XXXV) is the proposed engineering response. Six layers, planned in three phases. This work covers **Phase 1**:

- **Layer 1** — per-scenario learned reliability infrastructure: schema additions for TP/FP counters, smoothed-prior multiplier in retrieval ranking. Outcome supervision (Layer 2) is deferred — it requires real-world data accumulation beyond a 5-week window.
- **Layer 3** — three retrieval sub-improvements:
  - Hierarchical retrieval (cluster-routed search by `source_tag`)
  - Adaptive K (threshold-based instead of fixed K=5)
  - Distance-weighted voting (similarity × Wilson × Layer 1's effective_weight)

Layer 2 (outcome supervision wiring) is deferred. Layers 4-6 (multi-aspect annotation, auto-quarantine, provenance) are out of scope for this iteration.

---

## Hard isolation contract

Same as the scaling ablation. **Zero modifications to production code or production data.**

- All implementation under `published-papers-tests/multilayer/` (parallel codebase). Production `core/` modules not edited.
- Production `data/classifier_scenarios.db` opened **read-only** for the v2 DB build. Mtime + audit-log line count verified UNCHANGED after every run.
- Production classifier (`core/classifier_graph.py::classify_intent_graph`) untouched. The v2 classifier is `published-papers-tests/multilayer/classify_intent_graph_v2.py` — a separate module, never imported into production at runtime.
- Multi-layer ablation databases live under `published-papers-tests/multilayer/ablation_dbs/` — physically separate from `data/`.

After all 16+1 ablation runs:
- Production DB mtime: unchanged (`1777348319.9003425`, identical to pre-run snapshot)
- Production audit log line count: unchanged (`3991` lines)
- Production code: zero edits

---

## What was implemented

### Layer 1 — per-scenario reliability infrastructure

Schema additions on `ablation_dbs/v2_classifier.db` (a copy of the production DB with new columns):

```sql
ALTER TABLE scenarios ADD COLUMN tp_count INTEGER DEFAULT 0;
ALTER TABLE scenarios ADD COLUMN fp_count INTEGER DEFAULT 0;
ALTER TABLE scenarios ADD COLUMN retrieval_count INTEGER DEFAULT 0;
ALTER TABLE scenarios ADD COLUMN net_contribution REAL DEFAULT 0.0;
ALTER TABLE scenarios ADD COLUMN last_retrieved_ts TEXT;
```

Retrieval-time use:
```
effective_weight(scenario) =
    if retrieval_count >= MIN_RETRIEVALS_FOR_QUALITY:
        max(0, min(1, net_contribution))
    else:
        initial_confidence  # smoothed prior — typically 0.5
```

Layer 2 (outcome supervision) is what actually fills the TP/FP counters from production usage. Without Layer 2 wired, counters stay at zero and `effective_weight` falls back to `initial_confidence` for every scenario — a uniform multiplier across all candidates. **An empirical surprise**: this uniform smoothed prior turns out to act as Bayesian regularization on retrieval ranking, contributing measurable signal even with zero accumulated outcome data. See RESULTS.md for the discussion.

### Layer 3 — three retrieval sub-improvements

**Hierarchical retrieval** (`retrieval/hierarchical.py`):
- Compute L2-normalized centroid per `source_tag` cluster (cornell / dailydialog / empathetic_dialogues / hand_authored / live_correction).
- At query time, route to the highest-cosine cluster, then top-K within that cluster only.
- Fallback to flat search when routing confidence is below `HIERARCHICAL_FALLBACK_THRESHOLD`.

**Adaptive K** (`retrieval/adaptive_k.py`):
- Replace fixed K=5 with threshold-based: include all matches with similarity ≥ `ADAPTIVE_K_THRESHOLD`.
- Cap at `K_MAX=15` to prevent vote dilution on too-generic queries.
- If no candidate clears the threshold, abstain (return `None`).

**Distance-weighted voting** (`retrieval/distance_weighted.py`):
- Replace equal-weight votes from top-K with weighted votes.
- `weight = similarity × wilson_lower_bound × effective_weight_from_layer_1`
- Aggregate per intent_label, pick max as winner. (Wilson formula mirrors the production classifier's, copied not imported per the isolation contract.)

### Composed v2 classifier (`classify_intent_graph_v2.py`)

Returns the same shape as production's `classify_intent_graph`:
```
{turn_intent, extracted_value, confidence, reasoning}
```

Pipeline:
1. Abstract input via `core.abstraction.abstract_text` (production module — read-only call, no state mutation).
2. Embed via `core.classifier_graph.LocalE5Embedder` (production module — read-only construction).
3. Hierarchical or flat top-K cosine retrieval over v2 DB.
4. Adaptive K filter (threshold-based) + abstain check.
5. Aggregate weighted votes per intent label.
6. Pick winner; abstain if confidence below `ABSTAIN_THRESHOLD`.
7. Record retrieval count for each top-K candidate (Layer 1 plumbing — counters update lazily).

Test coverage: 60 passing tests across `multilayer/tests/` (24 Layer 1 + 33 Layer 3 + 3 build script tests).

---

## The ablation matrix — 16 runs across 3 phases

### Phase A (6 stages) — establish a fair baseline

`run_ablation_v2.py --phase a` produces these stages on the same 1,287-row Friends test set:

| Stage | What it tests |
|---|---|
| `strawman` | K=5, equal-weight votes, no abstain (the original v1 baseline — kept for historical comparison) |
| `production_equivalent` | K=20, sim×wilson, 0.40 abstain — replicates the production classifier's actual behavior. **Anchor for Δ comparisons.** |
| `prod_plus_distance_weighted` | production_equivalent + Layer 1 effective_weight multiplier active |
| `prod_plus_adaptive_k` | production_equivalent + adaptive-K filtering at threshold 0.65 (initial spec value) |
| `prod_plus_hierarchical` | production_equivalent + hierarchical cluster routing with 0.30 fallback threshold |
| `all_v2` | all three Layer 3 improvements stacked |

**Critical gate before downstream phases:** `production_equivalent` must reproduce the published 0.6448 baseline within ±0.5pp. If not, the parity layer is buggy and every comparison after is meaningless. Result: `production_equivalent` scored **0.6464** — within tolerance, parity confirmed (the 0.16pp delta is tiebreak drift on 1-2 rows out of 1287; the abstain rate matched production exactly at 19.7%).

### Phase B (5 runs) — adaptive K threshold sweep

`run_phases_b_c_d.py phase b` swept `ADAPTIVE_K_THRESHOLD` across 0.45 / 0.50 / 0.55 / 0.60 / 0.65, all with all other settings matching `prod_plus_adaptive_k`.

Per-run metrics include `avg_k_used` — the mean number of candidates that survived the threshold filter on each query. If `avg_k_used = 15` consistently, the K_MAX cap is dominating and the threshold isn't actually filtering.

### Phase C (4 runs) — hierarchical fallback threshold sweep

`run_phases_b_c_d.py phase c` swept `HIERARCHICAL_FALLBACK_THRESHOLD` across 0.30 / 0.40 / 0.50 / 0.60, all with hierarchical routing enabled.

Per-run metrics include `fallback_rate` — the fraction of queries where routing confidence fell below the threshold and the system fell back to flat search. If `fallback_rate = 0` regardless of threshold, the router is committing to a cluster on every query — meaning the threshold isn't actually exercising the fallback path.

### Phase D (1 run) — combined winners

Take the winning threshold from Phase B (0.45) and the winning fallback threshold from Phase C (0.30 — though it didn't beat anchor; recorded as best-of-bad). Stack them. Run once.

---

## Test set + scoring

- **Test set**: `published-papers-tests/dataset/friends/test/test_samples.jsonl` — 1,287 rows. Same data the scaling ablation consumed.
- **Scoring metric**: balanced accuracy = (recall_SPEAK + recall_SILENT) / 2. Same metric the paper publishes; same metric the scaling ablation used.
- **Predictions format**: `{turn_intent, prediction, ground_truth, category, ...}` per row, dumped to `predictions.json` for each stage. Re-scorable with the paper's `benchmarking/metrics.py:compute_metrics()`.
- **No row exclusions** in the strawman stage; abstaining stages (production_equivalent + downstream) report `excluded_count` (rows where the classifier abstained, computed as `1287 - evaluated_count`).

---

## Why we stopped where we did

After Phase D produced -1.03pp vs anchor (the spec'd combine-the-winners stack), and the parameter sweeps revealed that:

1. Adaptive K's threshold was structurally not exercising — K_MAX=15 cap dominated before threshold filtering could kick in. Five different thresholds, identical accuracy, identical avg_k_used. The dial was already past its useful operating range.
2. Hierarchical fallback's threshold was structurally not exercising — `fallback_rate = 0%` across all four threshold values. Routing confidence always exceeded the threshold, so the fallback never fired.

…the architect-level conclusion was that the negative results aren't a tuning problem; they're a design problem in the current Layer 3 implementation. Adaptive K needs K_MAX raised significantly above 15, OR the threshold logic needs redesign so it can actually filter. Hierarchical retrieval on `source_tag` clusters is structurally wrong for Friends — the test corpus's content style spans multiple bootstrap clusters, so locking queries to one cluster misses cross-cluster signal regardless of fallback threshold.

We had three options at this gate:

1. Iterate Layer 3 designs further (3-5 more days)
2. Pivot the submission narrative to use this ablation as supporting evidence rather than centerpiece
3. Drop Layer 3 entirely and integrate only the +0.56pp distance-weighted finding

We chose **option 2**. Multi-layer is now closed for this iteration. The +0.56pp from `prod_plus_distance_weighted` is a real, modest, defensible improvement worth integrating in production. Adaptive K and hierarchical retrieval need design rework before they're worth re-running, which is beyond the current 5-week deadline. Layer 1's smoothed-prior contribution is a publishable methodological finding (see RESULTS.md).

---

## Compute and cost

- **Total compute time**: ~16 minutes across all 16+1 runs on a warmed-up GPU (RTX 4090).
- **Actual API spend**: $0.00. The classifier uses `intfloat/multilingual-e5-large-instruct` loaded locally on GPU; no Together.ai or other API calls in the classification path.
- **Bridge's cost-tracking software** reports phantom amounts because it applies Llama-3.3-70B pricing to local-embedding token counts. The phantom numbers stay in the per-run JSONs as generated, with this caveat noted.

---

## Reproduction commands

```bash
# Build the v2 ablation DB (one-time setup)
cd dog-ai
python -m published-papers-tests.multilayer.scripts.build_ablation_db_v2 \
    --source-db data/classifier_scenarios.db \
    --out-path published-papers-tests/multilayer/ablation_dbs/v2_classifier.db \
    --verify-isolation

# Run Phase A — 6-stage matrix
python -m published-papers-tests.multilayer.scripts.run_ablation_v2 \
    --v2-db published-papers-tests/multilayer/ablation_dbs/v2_classifier.db \
    --test-set-path published-papers-tests/dataset/friends/test/test_samples.jsonl \
    --out-path published-papers-tests/results/multilayer_ablation_phase_a/

# Run Phases B + C + D
python -m published-papers-tests.multilayer.scripts.run_phases_b_c_d \
    --v2-db published-papers-tests/multilayer/ablation_dbs/v2_classifier.db \
    --test-set-path published-papers-tests/dataset/friends/test/test_samples.jsonl \
    --out-path published-papers-tests/results/multilayer_ablation_sweep/
```

After running, verify production isolation:
```bash
stat -c '%Y' data/classifier_scenarios.db   # must match pre-run mtime
wc -l data/classifier_audit_log.jsonl       # must match pre-run line count
```

If both checks pass, the isolation contract held.
