# External Benchmark Validation

This folder validates KaraOS against a published academic benchmark: *Speak or Stay Silent: Context-Aware Turn-Taking in Multi-Party Dialogue* ([Bhagtani et al. 2026, arXiv:2603.11409](https://arxiv.org/abs/2603.11409)).

The result lives in [`results/RESULTS.md`](results/RESULTS.md). The reproducible test harness lives in [`bridge/`](bridge/). The sanitized predictions you can verify lives in [`results/karaos_friends_test.json`](results/karaos_friends_test.json).

---

## Headline finding

| Approach | Friends balanced accuracy | Notes |
|---|---|---|
| Qwen3-8B (zero-shot) | 50.70% | paper |
| Qwen3-4B-Instruct (zero-shot) | 51.48% | paper |
| Mistral-7B-Instruct (zero-shot) | 52.87% | paper |
| Llama-3.1-8B-Instruct (zero-shot) | 54.21% | paper |
| Qwen2.5-7B (zero-shot) | 55.00% | paper |
| GPT-5.2 (zero-shot) | 55.41% | paper |
| GPT-OSS-20B (zero-shot) | 55.92% | paper |
| **KaraOS (no fine-tuning)** | **58.66%** | **this folder** |
| Gemini-3.1-Pro (zero-shot) | 60.54% | paper |
| Human baseline | 63.75% | paper |
| Qwen2.5-7B (LoRA fine-tuned) | 66.60% | paper |
| Qwen3-8B (LoRA fine-tuned) | 69.29% | paper |
| Mistral-7B-Instruct (LoRA fine-tuned) | 71.50% | paper |
| Llama-3.1-8B-Instruct (LoRA fine-tuned) | 72.52% | paper |

KaraOS sits in the strong end of the no-fine-tuning cluster. Gemini-3.1-Pro is 1.88 points ahead. Fine-tuned models with 120,000 labeled training examples reach 65–72%.

KaraOS reaches 58.66% with prompt design alone — no fine-tuning, no LoRA, no training data.

---

## What "balanced accuracy" doesn't tell you

The 58.66% headline is composed of conservative tradeoffs that matter for a home companion robot:

| Metric | Value | What it means |
|---|---|---|
| **SPEAK precision** | **87.8%** | When KaraOS chimes in, it's right almost 9 times out of 10 |
| **SPEAK recall** | 18.3% | It misses some "should speak" moments — by design, errs toward silence |
| **False positive rate** | **2.4%** | Almost never interrupts when it shouldn't |
| **SILENT recall** | **97.6%** | Catches 98% of "stay quiet" moments |
| **SILENT_no_ref accuracy** | **100%** | Perfect bystander detection — never barges into conversations it isn't part of |
| **SILENT_ref accuracy** | 96.7% | Hears its name in passing without barging in |
| **SPEAK_explicit accuracy** | 46.4% | Some Friends "explicit" cases lack vocatives (sitcom-style implicit cues); KaraOS's classifier targets explicit name-vocative addressing |
| **SPEAK_implicit accuracy** | 3.2% | Out of design scope; documented honestly |

For a home companion, the right failure mode is "too quiet, occasionally," not "interrupts at random." That's the tradeoff KaraOS encodes.

---

## What was tested

The benchmark task: given a multi-party conversation snippet, decide whether the target speaker should `SPEAK` or `STAY SILENT` after a detected pause. The dataset has 1,287 such decision points from the *Friends* TV show corpus, each hand-labeled by the paper's authors.

KaraOS was tested by treating the target speaker as the AI in each sample and running the same `_classify_intent` function the production system uses. The classifier returns one of 13 intent labels; a small mapping layer turns those into SPEAK/SILENT.

The bridge that does this lives in [`bridge/`](bridge/). It's deliberately isolated from the rest of the KaraOS codebase: no DB access, no audio/vision, no orchestrator state. It calls one function per row, with one model. Anyone can audit the test harness in <30 minutes of reading.

---

## What was NOT tested

1. **AMI (workplace meetings) and SPGI (earnings calls)** — the paper's other two domains. These contain implicit-flow conversational patterns (group questions without vocatives, topical-thread continuations) that KaraOS's classifier doesn't claim to handle. A 10-row smoke test on AMI confirmed: KaraOS scores ~20%, not because anything is broken, but because explicit-addressing is what KaraOS targets. See [`PATH1_SPEC.md`](PATH1_SPEC.md) for the prompt-engineering attempt to lift the AMI score and [`results/RESULTS.md`](results/RESULTS.md) for the rollback narrative.

2. **Other backbones (GPT-5, Gemini, etc.)** — KaraOS is model-agnostic by design but was tested with Llama-3.3-70B-Instruct-Turbo as the backbone. Specific numbers may differ with other models; the conservative-bias and explicit-addressing-strength patterns should hold.

---

## Reproducing the result

The dataset and the paper's evaluation code are not in this repo (see "What's not in this folder" below). To reproduce:

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

The sanitized predictions are at [`results/karaos_friends_test.json`](results/karaos_friends_test.json). Source dialogue text is stripped per the Friends-MMC redistribution license — but our per-row predictions and ground-truth labels are intact. To verify our reported accuracy:

```python
import json
from benchmarking.metrics import compute_metrics

with open("results/karaos_friends_test.json") as f:
    data = json.load(f)

print(compute_metrics(data["predictions"]))
# Should reproduce 58.66% balanced accuracy / 58.05% macro accuracy
```

### 4. Run the bridge yourself

The bridge in [`bridge/`](bridge/) calls KaraOS's classifier on each sample. Requires:
- Together.ai API key (~$0.20 for the full Friends test set at current pricing)
- KaraOS source (this folder is in the KaraOS repo; the bridge imports `core.brain._classify_intent` read-only)
- Python 3.10+

```bash
cd bridge
python run.py --datasets friends --split test
```

Predictions are written to `results/karaos_friends.json` (full, with dialogue) and the sanitization script in `bridge/scripts/sanitize_predictions.py` produces the publishable `karaos_friends_test.json`.

---

## Folder layout

```
published-papers-tests/
├── README.md                ← you are here
├── BRIDGE_SPEC.md           ← the spec the bridge was built to
├── PATH1_SPEC.md            ← prompt-expansion attempt to lift AMI; rolled back honestly
├── SANITIZE_SPEC.md         ← how the sanitized predictions were produced
├── .gitignore               ← keeps unsanitized files local
├── bridge/                  ← reproducible test harness
│   ├── run.py
│   ├── README.md
│   ├── adapters/
│   ├── shared/
│   └── scripts/sanitize_predictions.py
└── results/
    ├── karaos_friends_test.json   ← per-row predictions, sanitized for publication
    └── RESULTS.md                  ← full findings, paper comparison, caveats
```

---

## What's NOT in this folder (and why)

- **The dataset itself** (~250MB of copyrighted Friends/AMI/SPGI dialogue). The HuggingFace source is the authoritative copy; we link to it rather than re-hosting it.
- **The paper's evaluation code.** It's available at the upstream GitHub repo; cloning it ourselves would just clutter this repo with code we didn't write.
- **The full unsanitized prediction file** (`karaos_friends.json`). It contains verbatim Friends dialogue from the 1,287 source samples. Kept locally in the developer's working tree; gitignored.

This makes the repo lean (~870KB total), focused on what KaraOS actually contributed, and easy to audit.

---

## Honest caveats

KaraOS's production task is *"should the AI speak in this conversation?"* The benchmark's task is *"will the named human target speaker take the next turn?"* These are related but not identical. The bridge tests KaraOS by treating the target speaker as the AI for each sample. The mapping from classifier intent labels to SPEAK/SILENT is documented in [`bridge/adapters/output_mapper.py`](bridge/adapters/output_mapper.py).

KaraOS scores well on cases where addressing is explicit (the `SPEAK_explicit` and `SILENT_*` categories — see metrics table above). It scores poorly on `SPEAK_implicit` (3.2%) — cases where the target takes a turn without being named. This is documented honestly. KaraOS's classifier is built to detect explicit name-vocative addressing, which is the dominant pattern in home-companion use; implicit conversational-flow detection is a separate task that wasn't claimed and isn't built.

KaraOS is model-agnostic. The current backbone is Llama-3.3-70B-Instruct-Turbo via Together.ai. The same classifier prompt, intent labels, and decision layer would plug into any frontier LLM (GPT-5, Gemini, Claude) with no changes. The score reported here is for KaraOS-the-system, not for the underlying model.

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
