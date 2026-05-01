# Methodology — multi-backbone falsifying experiment

The procedural detail behind the falsifying test that disproved KaraOS's original "model-agnostic" claim. Companion to [`README.md`](README.md) and [`MULTI_BACKBONE_RESULTS.md`](MULTI_BACKBONE_RESULTS.md).

---

## What the test is for

The original public claim was: *"KaraOS is model-agnostic by design."* This was a falsifiable claim. The test of that claim is: take the KaraOS classifier prompt, swap in a different LLM as the classifier brain, and see if the score on the same benchmark stays comparable.

If the score stays comparable across LLM backbones, the "model-agnostic" claim is supported by data. If the score collapses on a smaller backbone, the original number was the model carrying the win, not the architecture.

---

## What was tested

The same KaraOS classifier prompt — verbatim, no changes — was passed to a different LLM backbone via the `--model` CLI flag of the bridge. Predictions were captured exactly the same way as the Run 1 baseline ([`../friends_baseline_full_db/`](../friends_baseline_full_db/)). The only difference between Run 1 and Run 2 is the LLM behind the prompt.

| Run | Classifier prompt | LLM backbone | Score |
|---|---|---|---:|
| Run 1 | KaraOS production prompt (Sessions 76-117 iterative) | Llama-3.3-70B-Instruct-Turbo | 58.66% |
| Run 2 | Same KaraOS production prompt (verbatim) | Qwen2.5-7B-Instruct-Turbo | **52.32%** |

The paper publishes a vanilla zero-shot Qwen2.5-7B baseline at 55.00%. KaraOS-on-Qwen-7B scored *2.68 percentage points below that vanilla baseline*. The "architectural lift" we had been claiming did not survive the model swap.

---

## Why Qwen-7B specifically

The original spec called for three smaller paper-baseline backbones to give a stronger statistical case (Qwen2.5-7B, Llama-3.1-8B, Mistral-7B-v0.3 — all three in the paper). The reality of provider access:

| Model attempted | Status | Why blocked |
|---|---|---|
| Qwen/Qwen2.5-7B-Instruct-Turbo | ✅ Worked | (paper baseline 55.00%) |
| meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo | ❌ HTTP 400 | "Unable to access non-serverless model" |
| meta-llama/Llama-3.1-8B-Instruct-Turbo | ❌ HTTP 404 | Model ID not in account catalog |
| meta-llama/Meta-Llama-3-8B-Instruct | ❌ HTTP 400 | "non-serverless" |
| meta-llama/Meta-Llama-3-8B-Instruct-Lite | ⚠️ 80% timeout | 4/5 ReadTimeout in 5-row smoke |
| meta-llama/Llama-3-8b-chat-hf | ❌ HTTP 400 | "non-serverless" |
| mistralai/Mistral-7B-Instruct-v0.3 | ❌ HTTP 400 | "non-serverless" (paper baseline 52.87%) |
| mistralai/Mistral-7B-Instruct-v0.1 | ❌ HTTP 400 | "non-serverless" |

Together.ai listed these models in `/v1/models` with non-zero pricing, but the account was not provisioned for serverless inference on most of them. The `/models` listing is necessary-but-not-sufficient evidence of access.

We did not switch to a different inference provider (OpenRouter, HuggingFace Inference) to fill in the missing models because (a) different providers run different quantizations and serving stacks, breaking apples-to-apples comparison, and (b) the architecture has since been replaced by the graph-classifier path, so additional multi-backbone runs against the old LLM-classifier architecture are of academic interest only.

The collapse of the planned 3-backbone study to a 1-backbone study is a real limitation of this experiment. We acknowledge it directly. The qualitative result — *the architecture's score depends on the model* — is well-supported by N=1 because the magnitude of the gap is large (collapse to *below* a paper baseline that was used as a low-end reference). It is not as strong as a full 3-backbone study would have been.

---

## What was held constant across runs

- **Same Friends test set** — 1,287 rows from the paper's `friends/test/test_samples.jsonl`.
- **Same prompt** — verbatim copy of KaraOS's production classifier prompt (Sessions 76-117 iterative state). No tuning, no shrinking, no per-model adaptation.
- **Same JSON-mode response format** — `response_format={"type": "json_object"}` on both runs.
- **Same temperature** — 0.1 with deterministic seed.
- **Same scoring code** — paper's `metrics.py:compute_metrics()` for both runs.
- **Same routing** — intent label → `SPEAK` / `SILENT` mapping unchanged.

The ONLY variable was the LLM backbone. That's what makes this a clean falsifying experiment.

---

## Diagnosis (where Qwen lost the points)

Per-category breakdown vs. Run 1 (Llama-70B):

| Category | Qwen-7B accuracy | Llama-70B accuracy | Δ |
|---|---:|---:|---:|
| `SILENT_no_ref` | 100.0% | 100.0% | 0.0pp |
| `SILENT_ref` | 98.8% | 96.7% | +2.1pp |
| `SPEAK_explicit` | **14.5%** | 46.4% | **-31.8pp** |
| `SPEAK_implicit` | 0.7% | 3.2% | -2.5pp |

The damage was concentrated in `SPEAK_explicit` — the category KaraOS was specifically designed to handle well. Qwen+KaraOS caught only 32 of 220 directly-addressed cases; Llama+KaraOS caught 102 of 220.

False-positive rate stayed low (0.91% — when Qwen says SPEAK it's still 85.4% precision), but recall collapsed to 5.5% vs. Llama's 18.3% on overall SPEAK.

Looking at Qwen's `reasoning` field on mismatched rows: under prompt load, the 7B model defaulted to `casual_conversation` even on samples that DO contain a vocative. That's not 7B being bad at language understanding — it's the prompt being **over-engineered for 70B**, with too much reasoning surface for a 7B to produce confident structured output. The KaraOS classifier prompt had been iteratively refined against 70B over 30+ live-canary sessions and accumulated complexity that the larger model could absorb. The complexity was hurting smaller backbones.

---

## What was NOT done in response

Things we deliberately did not do, all of which would have invalidated the experiment:

- **Did not retune the prompt for Qwen.** The test was *transferability of the existing prompt*, not "what's the smallest model we can make work after iterative tuning." Retuning would have produced a different prompt that's no longer KaraOS-on-Qwen — it would be KaraOS-Qwen-tuned, a different system.
- **Did not delete the Qwen result.** The data is the data. It's published as-is.
- **Did not retry with different inference providers** to find a friendlier number for Qwen-7B. See the paragraph above on quantization differences.
- **Did not run on AMI / SPGI** to pad numbers. Out-of-scope domains. The paper already characterized the implicit-flow failure mode.

---

## What this experiment caused

The collapse on Qwen-7B is what motivated the architectural rewrite. The graph-classifier path (Run 3, in [`../friends_baseline_full_db/predictions_graph_classifier.json`](../friends_baseline_full_db/predictions_graph_classifier.json)) makes zero LLM calls in the classification path, so it is structurally model-agnostic — the classifier behaves identically regardless of which (if any) LLM is the conversation brain. The architecture is empirically model-agnostic in a way the original LLM-classifier path was not.

This is the test working as intended. A falsifying experiment that doesn't change subsequent design is just performance theater. This one changed the design.

---

## Reproducing this experiment

```bash
cd dog-ai/published-papers-tests/bridge

# Reproduce the Llama-70B baseline (Run 1)
python run.py --datasets friends --split test

# Reproduce the Qwen-7B falsifying run (Run 2)
python run.py --datasets friends --split test --model "Qwen/Qwen2.5-7B-Instruct-Turbo"

# Re-score
python -m benchmarking.metrics results/karaos_friends_qwen-qwen2.5-7b-instruct-turbo.json
```

Predictions in this folder (`llama_70b_predictions.json`, `qwen_7b_predictions.json`) reproduce the headline numbers above when scored against the paper's ground-truth labels. If a researcher reproducing the test gets a different number, please open an issue.
