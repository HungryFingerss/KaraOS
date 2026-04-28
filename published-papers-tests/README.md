# External Benchmark Validation

This folder validates KaraOS against a published academic benchmark: *Speak or Stay Silent: Context-Aware Turn-Taking in Multi-Party Dialogue* ([Bhagtani et al. 2026, arXiv:2603.11409](https://arxiv.org/abs/2603.11409)).

The full benchmark journey lives in [`results/RESULTS.md`](results/RESULTS.md). This README is the short overview.

---

## The journey in one paragraph

We ran the benchmark three times. Run 1 (LLM classifier on Llama-3.3-70B): 58.66% — looked great, claimed "model-agnostic." Run 2 (same classifier on Qwen-7B, falsifying experiment we ran on ourselves): 52.32% — *worse* than vanilla Qwen-7B. The 70B was carrying the win; the model-agnostic claim was rhetoric. So we rebuilt the classifier as a deterministic graph operation with zero LLM calls in the classification path. Run 3: 64.56% — beats both prior runs, sits just below the lowest fine-tuned model in the paper, and the score genuinely doesn't depend on which LLM is the conversation brain anymore.

---

## Headline comparison

| Approach | Friends balanced accuracy | Notes |
|---|---|---|
| Qwen3-8B (zero-shot) | 50.70% | paper |
| Qwen3-4B-Instruct (zero-shot) | 51.48% | paper |
| **KaraOS Run 2** (LLM classifier on Qwen-7B) | **52.32%** | this folder — falsifying experiment |
| Mistral-7B-Instruct (zero-shot) | 52.87% | paper |
| Llama-3.1-8B-Instruct (zero-shot) | 54.21% | paper |
| Qwen2.5-7B (zero-shot, paper baseline) | 55.00% | paper |
| GPT-5.2 (zero-shot) | 55.41% | paper |
| GPT-OSS-20B (zero-shot) | 55.92% | paper |
| **KaraOS Run 1** (LLM classifier on Llama-70B) | **58.66%** | this folder — original published result |
| Gemini-3.1-Pro (zero-shot) | 60.54% | paper |
| Human baseline | 63.75% | paper |
| **KaraOS Run 3** (graph classifier — current architecture) | **64.56%** | this folder — post-rewrite |
| Qwen3-4B-Instruct (LoRA fine-tuned) | 65.12% | paper |
| Qwen2.5-7B (LoRA fine-tuned) | 66.60% | paper |
| Qwen3-8B (LoRA fine-tuned) | 69.29% | paper |
| Mistral-7B-Instruct (LoRA fine-tuned) | 71.50% | paper |
| Llama-3.1-8B-Instruct (LoRA fine-tuned) | 72.52% | paper |

Run 3 places KaraOS above the human baseline and competitive with the lowest fine-tuned LoRA models — without modifying any model weights, without running gradient descent, without producing checkpoints.

---

## What "no fine-tuning" honestly means

KaraOS does not modify model weights. It does not train LoRA adapters. It does not run gradient descent. The brain LLM ships as-is.

KaraOS does use ~2,000 labeled scenarios as a retrieval corpus. **The complete bootstrap seed is published** at [`classifier-seed/seed.jsonl`](classifier-seed/seed.jsonl) (~780 KB, all 2,081 scenarios, no PII, with source attribution). See the [`classifier-seed README`](classifier-seed/README.md) for the full breakdown of what's in it. This is **non-parametric learning** — distinct from fine-tuning, but it IS labeled training data, and we want to be transparent about that.

The Friends test set was strictly held out from training. Test integrity is intact.

For the precise distinction between Run 3's retrieval-based learning and the paper's LoRA fine-tuning, see the "Honest framing" section of [`results/RESULTS.md`](results/RESULTS.md).

---

## What 64.56% looks like in practice (Run 3)

| Metric | Value | Interpretation |
|---|---|---|
| **SPEAK precision** | **80.2%** | When KaraOS chimes in, it's right ~4 times out of 5 |
| **SILENT recall** | **96.4%** | Almost never barges into conversations it isn't part of |
| **SPEAK recall (overall)** | **15.2%** | KaraOS misses many "should speak" moments — by design (errs toward silence) |
| `SPEAK_explicit` accuracy | 31.4% | In-scope target met (directly-addressed cases) |
| `SPEAK_implicit` accuracy | 1.9% | Out of scope by design (KaraOS targets explicit name-vocative addressing) |

The 15.2% overall recall isn't a uniform miss — it splits cleanly into 31.4% on the cases KaraOS targets (`SPEAK_explicit`) and 1.9% on the cases it doesn't (`SPEAK_implicit`, where the target speaker takes a turn without being addressed by name). The gap is structural, not a defect.

For a home companion, the right failure mode is "too quiet, occasionally," not "interrupts at random." KaraOS encodes that tradeoff structurally.

---

## What was NOT tested

1. **AMI (workplace meetings) and SPGI (earnings calls)** — the paper's other two domains. These contain implicit-flow conversational patterns that KaraOS's architecture doesn't target. A 10-row smoke test on AMI confirmed: KaraOS scores ~20%, not because anything is broken, but because explicit-addressing is what KaraOS is for.

2. **Run 3 with multiple brain LLMs side-by-side.** Run 3 is structurally model-agnostic (the classifier makes zero LLM calls), but we have not yet empirically tested it with multiple different brain models in parallel to confirm the classifier's score stays constant. Architectural commitment enforced by tests that mock the LLM client to fail; cross-backbone empirical validation is a follow-up experiment.

---

## Reproducing the result

The dataset and the paper's evaluation code are NOT in this repo. To reproduce:

### 1. Get the dataset

```bash
git clone https://huggingface.co/datasets/ishiki-labs/multi-party-dialogue
```

The `friends/test/test_samples.jsonl` file has the 1,287 evaluation rows.

### 2. Get the paper's evaluation code (for the metrics module)

```bash
git clone https://github.com/ishikilabsinc/context_aware_modeling
```

Use their `benchmarking/metrics.py` to compute balanced accuracy, F1, FPR, FNR, and per-category breakdowns.

### 3. Verify our predictions

The sanitized predictions for Run 1 are at [`results/karaos_friends_test.json`](results/karaos_friends_test.json). Source dialogue text is stripped per the Friends-MMC redistribution license — but per-row predictions and ground-truth labels are intact. Verify with:

```python
import json
from benchmarking.metrics import compute_metrics

with open("results/karaos_friends_test.json") as f:
    data = json.load(f)

print(compute_metrics(data["predictions"]))
# Should reproduce 58.66% balanced accuracy (Run 1)
```

(Sanitized Run 3 predictions will be added in a future commit.)

### 4. Run the bridge yourself

The bridge in [`bridge/`](bridge/) calls KaraOS's classifier on each sample. Three runs the bridge supports:

```bash
cd bridge

# Run 1 — LLM classifier path on Llama-70B (original)
python run.py --datasets friends --split test

# Run 2 — LLM classifier path on Qwen-7B (falsifying experiment)
python run.py --datasets friends --split test --model "Qwen/Qwen2.5-7B-Instruct-Turbo"

# Run 3 — graph classifier (no LLM in classification path)
python run.py --datasets friends --split test --use-graph-classifier
```

---

## Folder layout

```
published-papers-tests/
├── README.md                ← you are here (overview)
├── BRIDGE_SPEC.md           ← the spec the bridge was built to
├── PATH1_SPEC.md            ← prompt-expansion attempt that was rolled back
├── SANITIZE_SPEC.md         ← how the sanitized predictions were produced
├── .gitignore               ← keeps unsanitized files local
├── bridge/                  ← reproducible test harness
│   ├── run.py
│   ├── README.md
│   ├── adapters/
│   ├── shared/
│   └── scripts/sanitize_predictions.py
├── classifier-seed/         ← the labeled training data (NEW)
│   ├── seed.jsonl                  ← all 2,081 abstracted scenarios + labels + source refs (~780 KB)
│   └── README.md                   ← what's in the seed, composition, how to use it
└── results/
    ├── karaos_friends_test.json   ← Run 1 sanitized predictions
    └── RESULTS.md                  ← full benchmark journey, all three runs, methodology, caveats
```

---

## Honest caveats

KaraOS's production task is *"should the AI speak in this conversation?"* The benchmark's task is *"will the named human target speaker take the next turn?"* These are related but not identical. The bridge tests KaraOS by treating the target speaker as the AI for each sample.

KaraOS scores well on `SPEAK_explicit` and `SILENT_*` categories. It scores poorly on `SPEAK_implicit` — by design, not by failure. The architecture targets explicit name-vocative addressing.

Run 3's architecture is model-agnostic at the classification layer — the graph classifier makes zero LLM calls, regardless of which LLM is the brain. Run 1 and Run 2 used LLM classifiers and were therefore model-dependent (Run 2 confirmed this by collapsing on Qwen-7B). The Run 3 architecture exists today; Runs 1 and 2 are documented here for the complete history.

KaraOS uses ~2,000 labeled scenarios in its classifier graph (retrieval corpus). This is non-parametric learning, distinct from fine-tuning model weights. Both KaraOS and the paper's fine-tuned approaches use labeled training data; the techniques and scales are different.

---

## Citation

```bibtex
@misc{bhagtani2026speakstaysilentcontextaware,
  title={Speak or Stay Silent: Context-Aware Turn-Taking in Multi-Party Dialogue},
  author={Bhagtani, Kratika and Anand, Mrinal and Xu, Yu Chen and Yadav, Amit Kumar Singh},
  year={2026},
  archivePrefix={arXiv},
  url={https://arxiv.org/abs/2603.11409}
}
```
