# Classifier Seed Data

The complete training data for KaraOS's graph classifier, published as `seed.jsonl`. 2,081 abstracted dialogue scenarios drawn from external corpora plus hand-authored high-stakes cases, labeled into our 13-intent space by a one-time Llama-3.3-70B labeling pass during bootstrap.

We are publishing this in full because the architectural claim ("KaraOS is a model-agnostic classifier built from labeled scenarios") is only honest if you can see the labeled scenarios.

---

## What's in the file

Each line is a JSON object representing one scenario. Example:

```json
{
  "abstract_text": "{P1}, how's a kid?",
  "intent_label": "direct_address_to_person",
  "extracted_value": "{P1}",
  "confidence": 0.95,
  "source_tag": "cornell",
  "source_version": "cornell-v1.0-batch-001",
  "source_ref": "movie=m386|line=L278029",
  "model_id": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
  "abstract_rule_version": 1,
  "initial_confidence": 0.6
}
```

| Field | Meaning |
|---|---|
| `abstract_text` | The scenario text with PII placeholders. Names → `{P1}`, `{P2}`. System name → `{SYSTEM}`. Places → `{LOC1}`, `{LOC2}`. Times preserved (they carry intent signal). |
| `intent_label` | One of 13 KaraOS intent labels (see below) |
| `extracted_value` | Placeholder reference for the target of the intent (if applicable) |
| `confidence` | The labeling LLM's confidence when it assigned this label |
| `source_tag` | Which corpus the row came from |
| `source_version` | Batch identifier (for reproducibility / rollback granularity) |
| `source_ref` | Original record locator within the source corpus (so anyone can trace a row back to its origin) |
| `model_id` | The LLM that did the labeling pass — `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| `abstract_rule_version` | Version of the abstraction rules applied (so future schema changes can migrate) |
| `initial_confidence` | Bootstrap confidence weight: 0.6 for corpus-derived rows, 0.9 for hand-authored |

**Embeddings are not included.** Each scenario also has a 1024-dim float32 embedding (computed via `intfloat/multilingual-e5-large-instruct`), but those are deterministic outputs — anyone with the abstract_text and the same embedding model can regenerate them. Including them would 8× the file size with no auditability gain.

---

## Composition

### By source

| Source | Count | License | Notes |
|---|---|---|---|
| Cornell Movie-Dialogs Corpus | 971 | Free, academic | 220K-conversation movie corpus, sampled for multi-party scenes |
| Hand-authored | 419 | Original | High-stakes intents (shutdown, identity rename, correction detection) — written from scratch covering cases external corpora have too few of |
| DailyDialog (HuggingFace `OpenRL/daily_dialog`) | 393 | Free, academic | 13K-dialogue daily-life corpus |
| EmpatheticDialogues | 298 | CC-BY 4.0 | 25K emotion-grounded conversations |

**Total: 2,081 scenarios.**

### By intent label (the 13-label space)

| Label | Count | Description |
|---|---|---|
| `casual_conversation` | 725 | Open conversation between humans, not addressing the AI |
| `personal_statement` | 576 | User stating something about themselves |
| `direct_address_to_person` | 280 | One human addressing another by name (AI stays silent) |
| `general_knowledge_query` | 205 | Question the AI can answer from training |
| `opinion_query` | 38 | Asking the AI's opinion |
| `assign_own_name` | 36 | "Call me X" — speaker telling AI their own name |
| `request_shutdown` | 36 | "Shut down" / "Power off" |
| `live_data_query` | 35 | Question requiring live web search |
| `deny_identity` | 30 | "I'm not who you think" |
| `confirm_identity` | 30 | "Yes, that's me" |
| `question_about_shutdown` | 30 | Asking about shutdown (NOT the same as requesting it) |
| `assign_system_name` | 30 | "Your name is X" — user naming the AI |
| `correction_to_previous_response` | 30 | "No, I was talking to {P1}" — user correcting addressing |

The bottom 7 labels are hand-authored — high-stakes intents where misclassification has the worst consequences (accidental shutdowns, accidental renames, etc.). The top 4 are from external corpora because casual dialogue dominates real conversation.

**`unclear` is intentionally absent** — it's a runtime escape hatch for low-confidence cases, not something to bootstrap with examples.

---

## What is NOT in this seed

- **The Friends test set** — strictly held out from training. The benchmark integrity depends on this. The graph has never seen Friends data.
- **The AMI corpus** — also held out (it's part of the same paper's evaluation set).
- **Any production conversation data** — production turns enrich the graph through online learning, but those scenarios contain personal information from specific deployments and are not published. **Only this bootstrap seed is public.**
- **Embeddings** — see above; deterministic, regenerable from `abstract_text`.

---

## How to use this seed

### To audit our claim

Open the file. Read scenarios. The architecture's behavior is determined by the data + the retrieval logic. The retrieval logic is deterministic (k-NN cosine similarity + outcome-weighted vote). The data is here. There's no hidden corpus.

### To reproduce

1. Get the abstraction step (spacy NER + person registry; see `bridge/` and `core/abstraction.py` in the codebase if available)
2. Generate embeddings: `intfloat/multilingual-e5-large-instruct` over `abstract_text`
3. Build a vector index (FAISS, Annoy, or any cosine-similarity retrieval engine)
4. At inference: embed the query, retrieve top-K, aggregate labels by Wilson lower-bound confidence weighting
5. Map intent label → SPEAK/SILENT decision (see `bridge/adapters/output_mapper.py`)

You should be able to reproduce KaraOS's classifier behavior given just this seed file plus the published bridge code.

### To extend or audit individual scenarios

Each row carries `source_ref` so you can trace it back to the origin corpus. For Cornell rows, `source_ref` looks like `movie=m386|line=L278029`. For EmpatheticDialogues, it's a different format. For hand-authored rows, `source_ref` is null and `source_tag` is `hand_authored`.

---

## What we deliberately NOT shipping

The full classifier database (`classifier_scenarios.db`) is an SQLite file that includes:
- This bootstrap seed
- All production-time additions from live KaraOS deployments
- Outcome supervision counters (which scenarios got confirmed / reverted by gates and corrections)
- Audit log of every change

We ship the bootstrap seed (this file) because it's the architectural foundation. We don't ship production accumulations because:
1. They contain personally-identifying interaction patterns from specific deployments
2. They reflect each deployment's particular conversational quirks
3. The privacy-preserving abstraction step makes them safer than raw conversation logs, but they're still per-deployment data

Each KaraOS deployment grows its own private classifier database from this public seed.

---

## License

This seed file is derived from open, freely-licensed corpora plus original hand-authored content. The combination is published under the same license as the KaraOS repository for benchmark verification and academic use.

Source corpora:
- Cornell Movie-Dialogs Corpus: free for non-commercial research
- DailyDialog: CC-BY-NC-SA 4.0 (research use)
- EmpatheticDialogues: CC-BY 4.0
- Hand-authored content: original, KaraOS-licensed

---

## Statistics summary

| Metric | Value |
|---|---|
| Total scenarios | 2,081 |
| Distinct intent labels | 13 |
| Distinct source corpora | 4 |
| File size | ~780 KB (without embeddings) |
| Labeling model | meta-llama/Llama-3.3-70B-Instruct-Turbo |
| Bootstrap labeling cost | ~$0.91 (one-time, see `results/RESULTS.md`) |
| Test set held out | Yes (Friends from arXiv:2603.11409) |
