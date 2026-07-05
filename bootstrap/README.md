# bootstrap/: one-shot offline build pipelines

Pipelines run ONCE, manually, to build committed artifacts, never at runtime, never in CI.

## `classifier/`: builds `data/classifier_scenarios_seed.jsonl`
The 6-stage pipeline that produced the graph classifier's seed (see `classifier/README.md` for the full run procedure):

1. `stage_1_acquire.py`, download the public dialog corpora (Cornell Movie-Dialogs, DailyDialog, EmpatheticDialogues)
2. `stage_2_filter.py` + `stage_2b_dailydialog_hf.py`, filter to usable scenario turns
3. `stage_3_classify.py`, label each scenario into the production intent space (Llama-3.3-70B via Together.ai)
4. `stage_4_abstract.py`, strip names/places via spaCy NER (scenarios must generalize, not memorize)
5. `stage_5_embed.py`, 1024-dim multilingual-e5 embeddings via Together.ai
6. `stage_6_seed.py`, assemble the JSONL seed
+ `hand_authored_scenarios.py`, ~100 hand-written high-stakes scenarios (shutdown/identity/name-assignment families) merged in
+ `run_all.py`, the orchestrator

Cost when it was run: ~$1.05 in API calls, ~15-20 min. Requires `TOGETHER_API_KEY` in the repo-root `.env`. Re-running is only needed to rebuild the seed from scratch (e.g., a new embedding model, the embedding model ID is locked in the DB metadata and a switch requires a full re-embed).
