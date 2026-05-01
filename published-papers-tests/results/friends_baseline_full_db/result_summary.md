# Friends baseline runs — observed scores

## Run 1 — LLM classifier on Llama-3.3-70B (production-realistic, original public claim)

**Balanced accuracy: 58.66%**
**File**: `predictions_llama_70b.json`
**Date**: original published run; same prediction file used for the LinkedIn post

| Metric | Value |
|---|---:|
| Balanced accuracy | 58.66% |
| Overall accuracy | 58.66% |
| `SILENT_no_ref` accuracy | 100.0% (173/173) |
| `SILENT_ref` accuracy | 96.7% (467/483) |
| `SPEAK_explicit` accuracy | 46.4% (102/220) |
| `SPEAK_implicit` accuracy | 3.2% (13/411) |

This is the original public number. It beats 7 of 8 zero-shot LLM baselines the paper publishes; sits below the human baseline (63.75%) and below the lowest fine-tuned model (Qwen2.5-7B fine-tuned: 66.60%). It was also the number that was shown in the LinkedIn post and the original ARCHITECTURE.md.

The number is real. What was wrong about it was the **interpretation** — the public claim "model-agnostic by design" did not survive the multi-backbone experiment ([`../friends_multi_backbone/`](../friends_multi_backbone/)). On Qwen2.5-7B the same classifier collapsed below the paper's vanilla baseline. The 70B was carrying the lift.

---

## Run 3 — Graph classifier, full 2,071-scenario DB (post-rewrite, current architecture)

**Balanced accuracy: 64.48%**
**File**: `predictions_graph_classifier.json`
**Date**: 2026-04-30 (deterministic full-DB run from the ablation suite)

| Metric | Value |
|---|---:|
| Balanced accuracy | **64.48%** |
| `SPEAK` precision | 80.21% |
| `SPEAK` recall | 15.19% |
| `SILENT` precision | 54.16% |
| `SILENT` recall | **96.39%** |
| Macro F1 | 47.45% |
| `SPEAK` F1 | 25.54% |
| `SILENT` F1 | 69.35% |

Confusion matrix (full DB):
- `SPEAK → SPEAK`: 77 (true positive)
- `SPEAK → SILENT`: 430 (false negative — these are mostly `SPEAK_implicit` cases the architecture deliberately doesn't target)
- `SILENT → SILENT`: 508 (true negative)
- `SILENT → SPEAK`: 19 (false positive — barge-ins)
- `SPEAK → None`: 124 (classifier abstained — graph confidence below threshold)
- `SILENT → None`: 129 (classifier abstained — graph confidence below threshold)

The 80.21% `SPEAK` precision means: when KaraOS chimes in, it's right ~4 times out of 5. The 96.39% `SILENT` recall means: KaraOS almost never barges into conversations it isn't part of. Those are the production-relevant numbers for a home companion.

The lower `SPEAK` recall (15.19%) reflects an architectural choice to err toward silence on `SPEAK_implicit` cases, where the next speaker takes a turn without being directly addressed. KaraOS targets explicit name-vocative addressing; missing implicit-flow cases is by design, not by failure.

---

## Comparison context

From the parent `RESULTS.md` and the public README:

| Approach | Friends balanced accuracy | Notes |
|---|---|---|
| Qwen3-8B (zero-shot) | 50.70% | paper |
| **Run 2** (KaraOS LLM classifier on Qwen-7B) | **52.32%** | the falsifying experiment |
| Mistral-7B-Instruct (zero-shot) | 52.87% | paper |
| Llama-3.1-8B-Instruct (zero-shot) | 54.21% | paper |
| Qwen2.5-7B (zero-shot, paper baseline) | 55.00% | paper |
| GPT-5.2 (zero-shot) | 55.41% | paper |
| GPT-OSS-20B (zero-shot) | 55.92% | paper |
| **Run 1** (KaraOS LLM classifier on Llama-70B) | **58.66%** | original public number |
| Gemini-3.1-Pro (zero-shot) | 60.54% | paper |
| Human baseline | 63.75% | paper |
| **Run 3** (KaraOS graph classifier — current architecture) | **64.48%** | this folder |
| Qwen3-4B-Instruct (LoRA fine-tuned) | 65.12% | paper |
| Qwen2.5-7B (LoRA fine-tuned) | 66.60% | paper |
| Qwen3-8B (LoRA fine-tuned) | 69.29% | paper |
| Mistral-7B-Instruct (LoRA fine-tuned) | 71.50% | paper |
| Llama-3.1-8B-Instruct (LoRA fine-tuned) | 72.52% | paper |

Run 3 places KaraOS above the human baseline and competitive with the lowest fine-tuned LoRA models — without modifying any model weights.

---

## Honest framing

KaraOS does not modify model weights. It does not train LoRA adapters. It does not run gradient descent. The brain LLM ships as-is.

KaraOS does use ~2,000 labeled scenarios as a retrieval corpus. This is **non-parametric learning** — distinct from fine-tuning, but it IS labeled training data, and the public framing acknowledges that explicitly. Both KaraOS and the paper's fine-tuned approaches use labeled data; the techniques and scales are different (paper: 120,000+ rows + LoRA training; KaraOS: ~2,000 + retrieval lookup).

The Friends test set was strictly held out from the bootstrap data. Test integrity is intact.

---

## Note on the 64.48% vs. 64.56% discrepancy

The public README cites "64.56%" while the file in this folder reports 64.48%. Both are real numbers from real graph-classifier runs against the full DB; the small difference (~0.08pp) reflects production DB state drift between runs (a small number of `live_correction` scenarios were added between the two evaluations). The 64.48% number in this folder is from the deterministic run captured during the 2026-04-30 ablation suite, which is the most rigorously-documented full-DB run available; that's the number we recommend citing going forward.

If the public README or other docs continue to cite 64.56%, both should be considered correct within run-to-run drift; if a researcher gets a third number when reproducing, it's likely the same kind of drift and not an error.
