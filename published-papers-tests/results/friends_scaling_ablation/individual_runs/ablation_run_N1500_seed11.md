# KaraOS graph classifier — Friends ablation run: N1500_seed11

Generated: 2026-04-30T22:08:59.085210+00:00

## Run parameters

| Parameter | Value |
|-----------|-------|
| Scenario-DB size (N) | 1500 |
| Random seed | 11 |
| Source DB | `classifier_scenarios.db` |
| Ablation DB | `classifier_N1500_seed11.db` |
| Elapsed time | 59.8s |
| Friends test rows | 1287 |
| API calls | 1287 |
| Cost (USD) | $0.00 |

## Results

| Metric | Value |
|--------|-------|
| **Balanced accuracy** | **0.6646** |
| F1 SPEAK | 0.2613 |
| F1 SILENT | 0.6963 |
| Macro F1 | 0.4788 |
| Precision SPEAK | 0.8065 |
| Recall SPEAK | 0.1559 |
| Precision SILENT | 0.5448 |
| Recall SILENT | 0.9643 |

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

Full predictions saved at: `karaos_friends_graph_N1500_seed11.json`
