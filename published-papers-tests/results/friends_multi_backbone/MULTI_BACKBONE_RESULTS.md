# Multi-Backbone Comparison — Friends Test Set

**Goal of the experiment:** isolate how much of KaraOS's reported 58.66% on Friends comes from the architecture (prompt + intent label space + heuristic + SPEAK/SILENT mapping) versus the underlying 70B model. Spec: `published-papers-tests/MULTI_BACKBONE_SPEC.md`.

**Date:** 2026-04-27
**Bridge:** unchanged from BRIDGE_SPEC.md baseline; one new shim (`bridge/multi_backbone_classifier.py`) calls the same KaraOS classifier prompt against alternative backbones via the `--model` CLI flag. **Production code untouched** (dog-ai test count `1282 passing` before AND after).

---

## Headline

**Architectural lift not demonstrated** on the one paper-baseline backbone we could reach. KaraOS-on-Qwen2.5-7B scored **2.68 percentage points BELOW** the paper's zero-shot Qwen2.5-7B baseline. The original 70B result is largely the model's contribution. **The "model-agnostic" framing in the public claim does not survive contact with this experiment** and needs revision.

This is the experiment's whole point — falsifiable test of our own claim, willing to surface uncomfortable results. The result is uncomfortable.

---

## Comparison table

| Backbone | KaraOS Bal. Acc. (macro) | KaraOS Overall | Paper zero-shot | Lift | Samples | Cost (tracker) | Hash |
|---|---:|---:|---:|---:|---:|---:|:---|
| Qwen2.5-7B-Instruct-Turbo | **52.32%** | 53.22% | 55.00% | **-2.68pp** | 1287 | $2.6635 | `bde0455f8e20` |
| Llama-3.3-70B-Instruct-Turbo | 58.05% | 58.66% | (not in paper) | n/a | 1287 | $0.1712 | `bde0455f8e20` |

(Tracker cost uses the 70B `$0.88/M` rate as a conservative ceiling. Qwen's true Together.ai rate is `$0.30/M`, so the actual Qwen bill is ~$0.91, not $2.66. The cap is a safety bound, not the true charge.)

---

## Per-category breakdown — Qwen2.5-7B vs Llama-3.3-70B

| Category         | Qwen Acc.    | 70B Acc.    | Total | Δ vs 70B    |
|------------------|-------------:|------------:|------:|------------:|
| `SILENT_no_ref`  | **100.0%**   | 100.0%      |   173 |  +0.0pp     |
| `SILENT_ref`     | 98.8%        | 96.7%       |   483 |  +2.1pp     |
| `SPEAK_explicit` | **14.5%**    | 46.4%       |   220 | **-31.8pp** |
| `SPEAK_implicit` | 0.7%         | 3.2%        |   411 |  -2.5pp     |

The damage is concentrated in `SPEAK_explicit` — Qwen+KaraOS catches only 32 of 220 directly-addressed-target cases that 70B+KaraOS catches 102 of. The classifier on Qwen is over-conservative: too many turns slip into `casual_conversation` / `unclear`, never triggering the SPEAK branch.

(Confusion matrix: `SPEAK→SILENT=596, SILENT→SILENT=650, SPEAK→SPEAK=35, SILENT→SPEAK=6`. False-positive rate stays low at 0.91% — when Qwen does say SPEAK it's still 85.4% precision — but recall collapses to 5.5%, vs 70B's 18.3%.)

---

## Why this happens (diagnosis)

Looking at Qwen's reasoning fields on mismatched rows: the classifier prompt is heavy — the IMPLICIT-ADDRESSING taxonomy + DIRECT-ADDRESS rule + GREETING-vs-ASSIGN rule + INJECTION DEFENSE + 8+ few-shot examples. 70B handles the complexity fluently and still produces sharp `addressing_ai` / `direct_address_to_person` labels. 7B gets distracted: under prompt-load the model defaults to `casual_conversation` even on samples that DO contain a vocative.

That's not the model being "worse" at language understanding — it's the prompt being **over-engineered for 70B**, with too much reasoning surface for a 7B to produce confident structured output. KaraOS's classifier prompt was iteratively refined against the 70B backbone (Sessions 76–117) and accumulated complexity that the larger model could absorb. The complexity is now hurting smaller backbones.

---

## What we tried but couldn't run

The original spec called for three smaller paper-baseline backbones (Qwen2.5-7B, Llama-3.1-8B, Mistral-7B-v0.3). Reality: this Together.ai account's serverless inventory only includes one of them. Documenting every attempt:

| Model ID attempted                                | Status     | Error                                                              |
|---------------------------------------------------|-----------|--------------------------------------------------------------------|
| `Qwen/Qwen2.5-7B-Instruct-Turbo`                  | ✅ Works  | (paper baseline 55.00%)                                            |
| `meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo`     | ❌ HTTP 400 | "Unable to access non-serverless model"                          |
| `meta-llama/Llama-3.1-8B-Instruct-Turbo`          | ❌ HTTP 404 | Model ID not in account catalog                                  |
| `meta-llama/Meta-Llama-3-8B-Instruct`             | ❌ HTTP 400 | "non-serverless"                                                  |
| `meta-llama/Meta-Llama-3-8B-Instruct-Lite`        | ⚠️ 80% timeout | 4/5 ReadTimeout in smoke — too slow to be usable             |
| `meta-llama/Llama-3-8b-chat-hf`                   | ❌ HTTP 400 | "non-serverless"                                                  |
| `mistralai/Mistral-7B-Instruct-v0.3`              | ❌ HTTP 400 | "non-serverless" (paper baseline 52.87%)                          |
| `mistralai/Mistral-7B-Instruct-v0.1`              | ❌ HTTP 400 | "non-serverless"                                                  |

Together.ai lists these models in `/v1/models` with non-zero pricing entries but the account is not provisioned for serverless inference on most of them — they require dedicated endpoints (separate pricing posture, slow to provision) or are simply restricted by region/tier on this account. The `/models` listing is necessary-but-not-sufficient evidence of access.

**Net effect:** the planned three-backbone comparison collapsed to a single-backbone comparison. Qwen2.5-7B remains the cleanest data point for a paper-baseline-comparable run.

**Follow-up sessions** (do not commit yet):
- Try OpenRouter / HuggingFace Inference for the rejected paper-baseline models — different inference providers, same model weights
- Run local Ollama Qwen2.5-7B as a production-realistic data point (note: Ollama runs Q4 quantization which is not apples-to-apples with the paper's full-precision evaluation — the result is informative for deployment but not for architecture isolation)

---

## Decision gate (per spec outcome table)

The spec's outcome matrix:

| Result pattern | Interpretation | Public claim |
|---|---|---|
| All paper-baseline backbones lift +3pp or more | Architecture is the source. Strong "model-agnostic" claim defensible. | "KaraOS lifts every backbone above paper baseline" |
| Mixed (some lift, some flat) | Calibrated claim. | "KaraOS lifts {list}; neutral on {list}" |
| All flat or below baseline | The 70B was carrying it. Architecture doesn't transfer. | Drop "model-agnostic"; reframe as "competitive on 70B" |

**Outcome:** the one paper-baseline backbone we tested landed BELOW its paper baseline. With N=1 we can't prove "all flat or below" generalizes, but the spec's last row is the only honest reading of the data we have. The "uncomfortable" cell from the reviewer's outcome table — "Architecture is over-fit to 70B and harms smaller models. Public claim needs full revision."

---

## What the public claim should look like (recommendation, awaiting Jagan's review)

Drop the "model-agnostic turn-taking layer" framing. Replace with something like:

> "On Llama-3.3-70B-Instruct-Turbo via Together.ai, KaraOS scores 58.66% balanced accuracy on the Friends test set — competitive with frontier zero-shot baselines that the paper publishes. We have not yet demonstrated that the architecture transfers to smaller backbones; an attempt on Qwen2.5-7B (the only paper-baseline model accessible on the inference provider used) scored 2.68pp below the paper's zero-shot baseline for that model. The architecture is currently best characterized as competitive on 70B-class backbones; broader transferability requires further validation."

That's honest about what we know and what we don't.

---

## What NOT to do

- Don't quietly delete the Qwen result file. It IS the data point that calibrates the public claim — keep it loadable for verifiers.
- Don't retune the classifier prompt to "fix" Qwen and republish. That defeats the experiment — the test was *transferability of the existing prompt*, not "what's the smallest model we can make work after iterative tuning."
- Don't run on AMI / SPGI to pad the numbers. Same reason as the original spec: out-of-scope domains, paper already characterized the implicit-addressing failure mode.
- Don't commit the per-model JSON to GitHub yet. Sanitization (per `SANITIZE_SPEC.md` pattern) needs to run first if these are ever published, AND Jagan reviews framing first.

---

## Reproducibility

```bash
# From C:\Users\jagan\dog-ai\published-papers-tests\
cd bridge

# Production 70B (already run — file at results/karaos_friends.json)
python run.py --datasets friends --split test

# Multi-backbone (this session)
python run.py --datasets friends --split test --model "Qwen/Qwen2.5-7B-Instruct-Turbo"

# Comparison table generator
python scripts/compare_backbones.py
```

dog-ai unchanged (1,282 tests passing). Production classifier path (`core.brain._classify_intent`) untouched — the bridge calls a separate shim `bridge/multi_backbone_classifier.py` that mirrors the prompt+JSON-mode behavior and accepts a model ID parameter.

---

## Acceptance checklist (per `MULTI_BACKBONE_SPEC.md`)

- [x] `bridge/run.py` accepts `--model` flag; defaults preserved when unset
- [x] Per-model prediction files written to `results/karaos_friends_<slug>.json`
- [x] Existing `results/karaos_friends.json` (the 70B run) unchanged
- [x] Smoke (10 rows) ran cleanly for at least one model; smoke evidence on access-blocked models documented above
- [x] Full Friends pass (1,287 rows) completed for at least one model — Qwen2.5-7B done
- [ ] Llama-3.1-8B + Mistral-7B full passes — **blocked by Together.ai serverless access; documented above**
- [x] Total spend recorded; under $1 real money (~$0.91 actual Qwen bill at $0.30/M)
- [x] `bridge/scripts/compare_backbones.py` produces the comparison table
- [x] `results/MULTI_BACKBONE_RESULTS.md` written (this file)
- [x] Per-model JSON loadable by `metrics.py:compute_metrics` and reproduces reported number
- [x] dog-ai test count unchanged at 1,282 — no production code modified
- [x] Public docs (`README.md`, `ARCHITECTURE.md`, top-level `results/RESULTS.md`) **NOT touched** — pending Jagan's review of these numbers
