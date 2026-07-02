# Friends benchmark — multi-backbone falsifying experiment

The experiment that disproved KaraOS's original "model-agnostic" claim, kept here as evidence and not hidden.

---

## What this folder contains

- `MULTI_BACKBONE_RESULTS.md` — the full diagnostic report written immediately after the run. Every honest detail: which model failed, by how much, why we think it failed, what we tried but couldn't run, and the recommended public-claim revision.
- `llama_70b_predictions.json` — KaraOS LLM-classifier predictions on Llama-3.3-70B-Instruct-Turbo. Balanced accuracy: **58.66%**.
- `qwen_7b_predictions.json` — KaraOS LLM-classifier predictions on Qwen2.5-7B-Instruct-Turbo. Balanced accuracy: **52.32%**.

---

## What the test was for

The original public claim was: *"KaraOS is model-agnostic by design."* That claim deserved a falsifying test. If KaraOS's architecture genuinely contributes the lift over zero-shot baselines, swapping in a smaller LLM should still produce above-baseline results. If the 70B was carrying the win, swapping models would expose that.

We ran the same KaraOS classifier prompt on Qwen2.5-7B (a model the paper benchmarks at 55.00% zero-shot) via the same Together.ai inference path. KaraOS-on-Qwen-7B scored **52.32%** — *2.68 percentage points below* the paper's vanilla-Qwen-7B baseline.

---

## What this means

The 70B was carrying it. The classifier prompt had been iteratively refined over 30+ live-canary sessions on Llama-3.3-70B and accumulated complexity (taxonomy rules, counter-examples, injection defense, structured-output contracts) that 70B handled fluently but 7B got distracted by. Damage was concentrated in the `SPEAK_explicit` category, where Qwen's recall collapsed to 14.5% versus 70B's 46.4%.

This is uncomfortable. The experiment's whole point was to be uncomfortable if the data was uncomfortable. Read [`MULTI_BACKBONE_RESULTS.md`](MULTI_BACKBONE_RESULTS.md) for the full diagnosis.

This finding is what motivated the graph-classifier rewrite. The current architecture (`friends_baseline_full_db/predictions_graph_classifier.json`) makes zero LLM calls in the classification path, so it is structurally model-agnostic — the classifier behaves identically regardless of which LLM is the conversation brain. That's the architecture made empirically real, in response to this experiment showing that the original architecture was not.

---

## What was attempted but couldn't run

The original spec called for three smaller paper-baseline backbones to give a stronger statistical case. Reality: only one of the three was accessible on the Together.ai serverless inventory we had at the time. Every model we tried, with HTTP error if applicable, is documented in section "What we tried but couldn't run" of `MULTI_BACKBONE_RESULTS.md`.

This collapses the comparison to N=1, which we acknowledge is weaker than N=3. We did not pad the result with retries on different inference providers because (a) different providers have different quantizations and serving stacks, breaking the apples-to-apples comparison; (b) the architecture has since been replaced by the graph classifier, so additional multi-backbone runs against the old architecture are of academic interest only.

---

## Honest framing recommendation (from the diagnostic report)

The recommendation, kept verbatim because it shaped the public posture going forward:

> "On Llama-3.3-70B-Instruct-Turbo via Together.ai, KaraOS scores 58.66% balanced accuracy on the Friends test set — competitive with frontier zero-shot baselines that the paper publishes. We have not yet demonstrated that the architecture transfers to smaller backbones; an attempt on Qwen2.5-7B (the only paper-baseline model accessible on the inference provider used) scored 2.68pp below the paper's zero-shot baseline for that model. The architecture is currently best characterized as competitive on 70B-class backbones; broader transferability requires further validation."

The current public KaraOS README and ARCHITECTURE.md were updated in line with this recommendation. The phrase "model-agnostic" now appears only attached to the graph-classifier path (Run 3), where it is structurally true (zero LLM calls).

---

## Reproduction

```bash
cd dog-ai/published-papers-tests/bridge

# Re-run on Llama-70B (the default model)
python run.py --datasets friends --split test

# Re-run on Qwen-7B
python run.py --datasets friends --split test --model "Qwen/Qwen2.5-7B-Instruct-Turbo"
```

Both write predictions JSONs that should reproduce the headline numbers above when scored with the paper's `metrics.py`.
