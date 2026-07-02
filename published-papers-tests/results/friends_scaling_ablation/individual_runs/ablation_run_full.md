# KaraOS graph classifier — Friends ablation run: full

Generated: 2026-04-30T22:13:04.219129+00:00

## Run parameters

| Parameter | Value |
|-----------|-------|
| Scenario-DB size (N) | 2081 (full) |
| Random seed | n/a (deterministic) |
| Source DB | `classifier_scenarios.db` |
| Ablation DB | `classifier_scenarios.db` |
| Elapsed time | 70.5s |
| Friends test rows | 1287 |
| API calls | 1287 |
| Cost (USD) | $0.00 |

## Results

| Metric | Value |
|--------|-------|
| **Balanced accuracy** | **0.6448** |
| F1 SPEAK | 0.2554 |
| F1 SILENT | 0.6935 |
| Macro F1 | 0.4745 |
| Precision SPEAK | 0.8021 |
| Recall SPEAK | 0.1519 |
| Precision SILENT | 0.5416 |
| Recall SILENT | 0.9639 |

## Confusion matrix

| | Predicted SPEAK | Predicted SILENT |
|---|---|---|
| Actual SPEAK | ? (TP) | ? (FN) |
| Actual SILENT | ? (FP) | ? (TN) |

## Source-DB composition

The production DB has 2071 active scenarios:

| Source corpus | Rows | Share |
|---------------|------|-------|
| Cornell Movie-Dialogs | 968 | 46.8% |
| DailyDialog | 393 | 19.0% |
| EmpatheticDialogues | 298 | 14.4% |
| hand_authored | 412 | 19.9% |

Stratified random sampling preserves these ratios in every subset.

## Raw output

Full predictions saved at: `karaos_friends_graph_full.json`
