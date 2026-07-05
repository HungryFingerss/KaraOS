# data/: system intelligence (survives factory reset)

**`classifier_scenarios_seed.jsonl`**, the committed seed for the pure-graph intent classifier (`core/classifier_graph.py`): ~1,600 abstracted conversation scenarios (Cornell Movie-Dialogs + DailyDialog + EmpatheticDialogues, names/places stripped via spaCy NER) plus ~100 hand-authored high-stakes scenarios, each with a 1024-dim multilingual-e5 embedding and a production intent label. Built once by the offline `bootstrap/classifier/` pipeline; ships with the repo.

## The load-bearing distinction
`data/` is **what the system has learned about language**, system intelligence. `faces/` (gitignored, runtime-created) is **who this deployment knows**, personal data. A factory reset wipes `faces/` and deliberately does NOT touch `data/` (CI-enforced: `test_factory_reset_does_not_touch_classifier_db`).

At first boot the runtime builds `data/classifier_scenarios.db` from this seed (gitignored, accumulates live outcome supervision + corrections); `data/classifier_audit_log.jsonl` and `data/classifier_snapshots/` (also gitignored) record every counter change and daily backups.

**Held out on purpose**: Friends, AMI, MELD, EmotionLines, they're benchmark sets used in `published-papers-tests/`; putting them in the seed would leak training into the published evaluation.
