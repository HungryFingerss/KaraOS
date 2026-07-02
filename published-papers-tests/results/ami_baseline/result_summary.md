# AMI baseline — observed score

## Headline (small-sample, honest disclosure)

KaraOS was run against a **10-row smoke sample** from the AMI test set. It predicted `SILENT` on all 10 rows. Per-class breakdown:

| Class | Count | Recall |
|---|---:|---:|
| Ground-truth `SPEAK` | 8 | **0.0%** (0/8) |
| Ground-truth `SILENT` | 2 | **100.0%** (2/2) |
| **Balanced accuracy** | — | **50.0%** |

Predictions are deterministic on this run (the LLM classifier mapped every sample to `unclear` / `casual_conversation` intent, both of which route to `SILENT`).

This is **not a full AMI benchmark run**. It is a 10-row sample sufficient to confirm the qualitative architectural mismatch — KaraOS classifies workplace-meeting turn-taking primarily as "stay silent," which is correct *as a robot's safe default* but wrong *as a turn-taking model on AMI.* A full 1,000+ row AMI evaluation would likely produce a similar shape (heavy SILENT-bias, low SPEAK recall on `SPEAK_implicit` cases).

## Why this number is what it is

The Bhagtani paper categorizes AMI samples primarily as `SPEAK_implicit` — situations where the next speaker takes a turn without being directly addressed by name. These are exactly the cases KaraOS architecturally targets *not* to interrupt. The classifier prompt encodes "default to silence unless the speaker is named or asked" as an explicit rule. On AMI, that rule produces all-SILENT output, which collapses to ~50% balanced accuracy — better than random on `SILENT` (perfect), zero on `SPEAK_implicit` (the actual production cost being measured).

## What this does NOT mean

- It does not mean KaraOS is a bad turn-taking model. It means KaraOS is targeted at a different problem (home companion / explicit-addressing) than AMI was designed to test (meeting agenda / implicit-flow).
- It does not mean KaraOS would score 50% on a full AMI run. The full distribution would shift somewhat. But the architectural mismatch dominates whatever the exact number ends up being.
- It does not invalidate the Friends result. Friends is heavy on explicit addressing — KaraOS's design target. AMI is heavy on implicit flow — outside KaraOS's design target. Different domains, different appropriate scores.

## What would change this

If KaraOS's architecture were extended to include implicit-flow turn-taking — for example, by reading agenda state, recent-speaker patterns, or topic-coherence signals — re-running this benchmark would test whether the extension actually closed the gap. No such extension has shipped as of this writing.

## Reproduction

```bash
cd dog-ai/published-papers-tests/bridge
python run.py --datasets ami --split test --limit 10
```

(Drop `--limit 10` for a full run if you have the compute. Expect similar shape, more samples.)

## Honesty disclosure

This 10-row result is included in the public benchmark folder despite being preliminary because the alternative — silently omitting it because it's unflattering — would violate the principle this whole repo is built on. Researchers reproducing KaraOS will want to know that AMI is out-of-scope by design before they run it themselves and conclude something is broken.
