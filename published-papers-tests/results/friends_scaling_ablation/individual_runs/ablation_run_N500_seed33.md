# KaraOS graph classifier — Friends ablation run: N500_seed33

Generated: 2026-04-30T22:04:10.093652+00:00

## Run parameters

| Parameter | Value |
|-----------|-------|
| Scenario-DB size (N) | 500 |
| Random seed | 33 |
| Source DB | `classifier_scenarios.db` |
| Ablation DB | `classifier_N500_seed33.db` |
| Elapsed time | 43.3s |
| Friends test rows | 1287 |
| API calls | 1287 |
| Cost (USD) | $0.00 |

## Results

| Metric | Value |
|--------|-------|
| **Balanced accuracy** | **0.6644** |
| F1 SPEAK | 0.2206 |
| F1 SILENT | 0.7014 |
| Macro F1 | 0.4610 |
| Precision SPEAK | 0.8333 |
| Recall SPEAK | 0.1271 |
| Precision SILENT | 0.5473 |
| Recall SILENT | 0.9765 |

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

Full predictions saved at: `karaos_friends_graph_N500_seed33.json`
