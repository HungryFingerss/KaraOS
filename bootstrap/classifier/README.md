# Classifier bootstrap pipeline

One-time offline pipeline that produces `data/classifier_scenarios_seed.jsonl`
— the populated seed for the pure-graph classifier (Spec 2 consumes it).

**This pipeline runs OUTSIDE production.** It does not touch any
production code path. Production reads the committed seed file at
startup; it never re-runs the bootstrap.

## Quick start

```bash
# From dog-ai/ root:
export TOGETHER_API_KEY=...      # required for stages 3 + 5

# One-shot (~15-20 min, ~$1.05 cost):
python -m bootstrap.classifier.run_all

# Or run stages individually:
python -m bootstrap.classifier.stage_1_acquire    # Download Cornell + DailyDialog + EmpatheticDialogues
python -m bootstrap.classifier.stage_2_filter     # Filter to ~1700 utterances
python -m bootstrap.classifier.stage_3_classify   # 70B classify (~$1.05, hard cap $2)
python -m bootstrap.classifier.stage_4_abstract   # spacy NER → {P1}/{LOC1} placeholders
python -m bootstrap.classifier.stage_5_embed      # E5 embeddings
python -m bootstrap.classifier.stage_6_seed       # Combine corpus + hand-authored → seed JSONL
```

## Prerequisites

- `TOGETHER_API_KEY` environment variable set (for 70B classification + E5 embeddings).
- `spacy` installed: `pip install spacy && python -m spacy download en_core_web_sm` (~50 MB).
- `httpx`, `numpy` (already in dog-ai's requirements).
- Internet access for stages 1, 3, 5.

## Cost

| Stage | What | Cost |
|---|---|---|
| 1 acquire | Download corpora | Free |
| 2 filter  | In-memory filter | Free |
| 3 classify | Together.ai 70B over ~1700 samples | ~$1.05 (cap $2.00) |
| 4 abstract | Local spacy NER | Free |
| 5 embed   | Together.ai E5 over ~1800 samples | Free (E5 endpoint) |
| 6 seed    | Local JSONL writer | Free |
| **Total** | | **~$1.05** |

If `stage_3_classify` hits the $2.00 hard cap it stops cleanly; partial
output stays in `cache/classified_samples.jsonl` and the next run
resumes from where it stopped.

## Idempotency

Every stage is idempotent:
- Stage 1: skips already-downloaded archives.
- Stage 2: skips if `cache/filtered_samples.jsonl` exists (delete to re-run).
- Stage 3: tracks `source_ref` of already-classified samples; resumes after a crash.
- Stage 4 / 5 / 6: rewrite their output every run.

## Output

```
data/classifier_scenarios_seed.jsonl   ← committed to git, ships with KaraOS
data/classifier_scenarios.db           ← built from seed on first boot (gitignored)
data/classifier_audit_log.jsonl        ← per-deployment audit log (gitignored)
```

## Held out (DO NOT include as bootstrap data)

- **Friends** test set — used as held-out evaluation in `published-papers-tests/`. Including it as bootstrap data would be data leakage and would invalidate the benchmark.
- **AMI** corpus — same reason, plus same paper as Friends.
- **MELD / EmotionLines** — derived from Friends, same contamination risk.

The three approved corpora (Cornell, DailyDialog, EmpatheticDialogues)
have no overlap with the held-out test sets and are license-clean.

## Hand-authored scenarios

`hand_authored_scenarios.py` carries ~100 high-stakes scenarios drawn
from the lessons of Sessions 71-117 (rename traps, shutdown false-positives,
identity disputes, geographic-query pollution). These are the "teeth" —
they ensure the seed has good coverage of the rare/dangerous intents
that external corpora rarely contain.

## Re-running the pipeline

Bumping `SOURCE_VERSION` in `hand_authored_scenarios.py` is the cleanest
way to refresh hand-authored data. Old rows in the live DB can be
quarantined (their `source_version` won't match the new one) and the
seed re-imported.

For corpus refresh, delete `cache/` and re-run `run_all.py`.
