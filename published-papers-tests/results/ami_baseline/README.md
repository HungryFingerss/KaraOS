# AMI benchmark — single baseline run

A single run of KaraOS's classifier on the AMI test set (workplace meetings — the second domain in the Bhagtani et al. 2026 benchmark). Kept here as honest evidence of *what KaraOS is not*, not as a result we're claiming.

---

## What this folder contains

- `predictions.json` — KaraOS classifier per-row predictions on the AMI test set. Re-scorable with the paper's `metrics.py`.
- `result_summary.md` — observed score and the diagnosis of why it's low.

---

## Why this folder exists

The Bhagtani et al. 2026 paper benchmarks turn-taking models across three domains: **Friends** (sitcom multi-party dialogue), **AMI** (workplace meeting transcripts), and **SPGI** (earnings calls). KaraOS's architecture targets one specific failure mode of voice AI — *interrupting on every pause when nobody addressed it* — and is built around explicit name-vocative addressing as the primary "should I speak?" signal.

That design works well for Friends (sitcom dialogue is heavy on direct address) and works poorly for AMI (meeting dialogue is heavy on implicit-flow turn-taking — the next speaker is determined by conversational drift, not by being named). KaraOS's score on AMI confirms this. It's not a defect; it's the architectural target hitting a domain it wasn't built for.

The honest thing is to publish the AMI score so anyone using KaraOS as a basis for comparison knows the limitation up front.

---

## What was tested

The same KaraOS classifier path (LLM-classifier — Run 1 architecture, before the graph-classifier rewrite) was run against the AMI test set via the same bridge that produced the Friends results. Predictions were captured per-row and saved to `predictions.json`.

---

## What was not tested

- The graph-classifier path (Run 3 architecture) on AMI. Plausibly KaraOS-on-AMI improves a bit with the graph classifier, but more likely it doesn't, because the architectural mismatch is between AMI's implicit-flow patterns and KaraOS's explicit-addressing target — a different classifier mechanism doesn't change that mismatch.
- SPGI (the third domain). Same mismatch. We did not run it.
- Multiple runs / variance estimation. AMI was a single confirmation pass, not a study.

---

## How to reproduce

```bash
cd dog-ai/published-papers-tests/bridge
python run.py --datasets ami --split test
```

Predictions land at `results/karaos_ami.json` (or the equivalent in the test directory).

---

## Honest read

KaraOS targeting explicit-addressing is a choice, not a limitation we're trying to hide. For a home companion robot, the production cost of barging into a private conversation between two friends is much higher than the production cost of staying quiet when someone gestures vaguely. AMI tests scenarios where the latter cost dominates (meeting facilitation, agenda-driven turn-taking). KaraOS is not built for that and shouldn't be deployed for that.

If a future version of KaraOS expands beyond explicit-addressing — for example, into agenda-aware turn detection — re-running this benchmark would be the right way to measure whether the expansion actually closed the gap. As of today, no such expansion has shipped, and the AMI score reflects that.
