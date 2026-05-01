# Test results — index

Every benchmark and ablation run KaraOS has been put through, organized by test. Each folder is fully self-contained: a README explaining what the test was and why, a METHODOLOGY explaining how it was run, the result narrative, and the raw prediction files for re-scoring.

The narrative across all results lives in [`RESULTS.md`](RESULTS.md) at this level. The folders below are the audit trail behind that narrative.

---

## Folder index

| Folder | What it contains | Headline result |
|---|---|---|
| [`friends_baseline_full_db/`](friends_baseline_full_db/) | The two production runs of the Friends benchmark — the original LLM-classifier path on Llama-3.3-70B and the rewritten graph-classifier path on the full 2071-scenario DB. | **Llama-70B classifier: 58.66%** balanced accuracy. **Graph classifier (full DB): 64.48%** balanced accuracy. |
| [`friends_multi_backbone/`](friends_multi_backbone/) | The falsifying experiment — running the same LLM classifier on Qwen2.5-7B to see whether the original 58.66% was the architecture or the model. The result was uncomfortable and it's published as-is. | KaraOS-on-Qwen-7B: **52.32%** — *2.68pp BELOW* the paper's vanilla Qwen-7B baseline (55.00%). The 70B was carrying the original number; the architectural lift was not real for that approach. This finding is what motivated the graph-classifier rewrite. |
| [`friends_scaling_ablation/`](friends_scaling_ablation/) | 10-run ablation study (3 seeds × 3 sizes + 1 deterministic full run) prompted by Amit Yadav's review on LinkedIn. Tests whether more retrieval scenarios = better accuracy. | **Inverse scaling**: smaller scenario DBs score HIGHER. N=500 mean: 69.19% (±2.6pp). N=2071 full: 64.48%. Variance collapses as N grows. Findings discussed in detail in the folder's `ABLATION_RESULTS.md`. |
| [`ami_baseline/`](ami_baseline/) | A single run of KaraOS's classifier on the AMI (workplace-meetings) test set, kept here as honest evidence that KaraOS is NOT a general-purpose turn-taking system. | Performance on AMI is structurally low because KaraOS's architecture targets explicit name-vocative addressing, not the implicit-flow patterns AMI tests. Result file present so anyone can re-score; no claim attached. |

---

## How to audit any of these

Every test folder contains the per-row predictions used to compute the headline number. To re-score:

1. Get the paper's evaluation code and the test set:
   ```bash
   git clone https://github.com/ishikilabsinc/context_aware_modeling
   git clone https://huggingface.co/datasets/ishiki-labs/multi-party-dialogue
   ```
2. Open the predictions JSON in any folder. Each row has the original sample ID, the predicted label, and (for the original Run 1) the ground-truth label.
3. Pass the predictions through the paper's `benchmarking/metrics.py:compute_metrics()`. The number you get should match the headline in that folder's README to within rounding.

If the numbers don't match, that's a real finding — please open an issue on the public repo.

---

## What's NOT here (and why)

**Run 1 sanitized predictions** are at the parent level (`results/karaos_friends_test.json`) per the original Friends-MMC redistribution license requirement. The raw Run 1 dialogue text is stripped from the redistributable file; only the per-row predictions and ground-truth labels remain. The unsanitized file (with text) stays local in `dog-ai/published-papers-tests/results/` for development.

**The graph classifier's bootstrap seed** lives at [`../classifier-seed/seed.jsonl`](../classifier-seed/seed.jsonl). All 2,081 abstracted scenarios + labels + source attribution. ~780 KB. No PII. See [`../classifier-seed/README.md`](../classifier-seed/README.md) for what's in it.

**No fake or padded data.** Every number reported in this folder comes from a real run on real data. Where a result was uncomfortable (the multi-backbone collapse, the inverse scaling), it's published verbatim with the diagnosis attached.
