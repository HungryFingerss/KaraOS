# Methodology — Friends baseline runs

The procedural detail behind the two production runs in this folder. Companion to [`README.md`](README.md) (which has the headline numbers) and the parent [`RESULTS.md`](../RESULTS.md) (which narrates the full benchmark journey).

---

## What the test is

The Friends test set comes from the Bhagtani et al. 2026 paper *"Speak or Stay Silent: Context-Aware Turn-Taking in Multi-Party Dialogue"* ([arXiv:2603.11409](https://arxiv.org/abs/2603.11409)). It contains 1,287 dialogue snippets drawn from the Friends sitcom corpus. For each snippet, a "target speaker" is named, and the question is: does the target speaker take the next turn (`SPEAK`), or does someone else speak (`SILENT`)?

KaraOS's production task is *"should the AI speak in this moment?"* — slightly different but related. The bridge tests KaraOS by treating the target speaker as if it were KaraOS for that moment. The classifier output (`SPEAK` / `SILENT`) is compared to the paper's ground-truth label.

---

## What "balanced accuracy" means here

For an imbalanced-class problem (Friends is roughly 50/50 SPEAK/SILENT but each subcategory is unbalanced), the relevant metric is:

```
balanced_accuracy = (recall_SPEAK + recall_SILENT) / 2
```

This is the metric the paper reports and the metric every comparison table in this repo uses. Other metrics (precision, F1, per-category breakdowns) are computed too but the headline number is balanced accuracy.

The paper's `benchmarking/metrics.py:compute_metrics()` function is the canonical scorer. Predictions are passed through it; no custom scoring rule is used by KaraOS.

---

## Run 1 — LLM-classifier path (Llama-3.3-70B)

**File**: `predictions_llama_70b.json`
**Score**: 58.66% balanced accuracy

For each Friends row, the bridge:

1. Builds a system prompt for KaraOS's intent classifier — the same prompt KaraOS uses in production at the time of this run. Includes the IMPLICIT-ADDRESSING taxonomy, DIRECT-ADDRESS rule, INJECTION DEFENSE, GREETING-vs-ASSIGN rule, and 8+ few-shot examples.
2. Wraps the row's last utterance and conversational context into the prompt's user message.
3. Calls Llama-3.3-70B-Instruct-Turbo on Together.ai with `response_format={"type": "json_object"}`, temperature 0.1, deterministic seed.
4. Parses the JSON response — extracts `turn_intent` and `confidence` fields.
5. Maps the intent label to `SPEAK` or `SILENT` using KaraOS's production routing rule (intents `direct_address_to_person` and a few siblings → `SPEAK`; others → `SILENT`).
6. Records the prediction.

This is the original KaraOS classification mechanism — model-dependent (relies on 70B's fluency), production-realistic (this is the same code path that runs on real conversations).

---

## Run 3 — Graph-classifier path (no LLM in classification)

**File**: `predictions_graph_classifier.json`
**Score**: 64.48% balanced accuracy (full 2,071-scenario DB, deterministic)

For each Friends row, the bridge:

1. Calls KaraOS's `core.classifier_graph.classify_intent_graph()` directly.
2. The function abstracts the input (replaces person names with `{P1}`, `{P2}`, places with `{LOC}`, etc. — registry-first then spaCy NER fallback) so the test query is in the same abstraction space as the stored scenarios.
3. Embeds the abstracted text via `intfloat/multilingual-e5-large-instruct` loaded locally on GPU.
4. Performs k-NN cosine similarity search against all 2,071 scenarios in the production DB (`dog-ai/data/classifier_scenarios.db`) — top-K with K=5.
5. Aggregates the K matches' intent labels using Wilson lower-bound confirmation-rate scoring (each scenario carries a confirmation count from prior live corrections + an initial confidence; Wilson score reflects how well-validated each scenario's label is).
6. Returns the highest-scoring label as the prediction.
7. Maps the intent to `SPEAK` / `SILENT` via the same routing rule as Run 1.

**Critical**: there is no LLM call anywhere in steps 1–6. The embedding is local. The k-NN is brute-force cosine. The aggregation is arithmetic. The classifier is structurally model-agnostic — the same code produces the same prediction regardless of which (if any) LLM is the conversation brain.

---

## Why two runs in one folder

The two represent the architectural shift KaraOS underwent. Run 1 is what was originally claimed in the LinkedIn post and the Bhagtani-paper comparison. Run 3 is what the architecture became after the multi-backbone experiment ([`../friends_multi_backbone/`](../friends_multi_backbone/)) revealed that Run 1's score was 70B-dependent.

Both runs scored on the same 1,287 Friends test rows with the same scoring function. Both predictions JSONs are loadable by the paper's metrics code and reproduce the headline numbers exactly. Anyone replicating either should get within rounding of these numbers.

---

## What is and isn't held out

- The Friends test set is **strictly held out** from the bootstrap data used to build the production classifier DB. The bootstrap pipeline draws scenarios from Cornell Movie-Dialogs, DailyDialog, and EmpatheticDialogues. Friends is not in the bootstrap. There is no train-test contamination.
- Hand-authored scenarios in the production DB (~412 of the 2,071) are *based on* KaraOS's own production failure modes (sessions 71–117 in the development log) — they were written to address bugs in the classifier prompt. They are not Friends-derived. They are KaraOS-specific.
- `live_correction` scenarios (added when production users explicitly correct the classifier) are also not Friends-derived. They originate from the development team's own canary sessions.

Every scenario in the production DB carries a `source_tag` indicating its origin. The bootstrap seed is published at [`../../classifier-seed/seed.jsonl`](../../classifier-seed/seed.jsonl) for full inspection.

---

## Reproduction guarantees

Each prediction file in this folder is reproducible to the row level. Differences from the published numbers, if any, would arise from:

- **Together.ai inference variability** — the LLM classifier (Run 1) is deterministic at temperature 0.1 with a fixed seed but Together.ai may serve from different replicas with slightly different floating-point behavior. Differences should be <0.5pp.
- **Production DB drift** — if the live KaraOS system has accumulated `live_correction` scenarios since this run, the classifier DB has more entries than the snapshot used for this score. The graph classifier's score is sensitive to DB state. The exact reported score (64.48%) is from the DB state as of 2026-04-30 with 2,071 active scenarios.
- **E5 model version** — the embedding model is locked at `intfloat/multilingual-e5-large-instruct` with a specific HuggingFace SHA pinned in `core/config.py`. Switching versions would shift the result.

If a researcher reproducing the score lands more than 1pp away, please open an issue. We'll reconcile.
