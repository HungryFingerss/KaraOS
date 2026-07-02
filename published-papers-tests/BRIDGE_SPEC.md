# Bridge Spec — Kara-OS vs Speak-or-Stay-Silent Benchmark

**Goal:** validate that **Kara-OS's turn-taking layer** correctly handles multi-party conversation, on the published 1,287-row Friends test set + the 1,410-row AMI test set.

**Folder:** all bridge code lives under `published-papers-tests/bridge/`. Zero changes to anything outside that folder.

---

## What we're actually testing

Kara-OS is **model-agnostic.** Today the backbone is Llama-3.3-70B-Instruct-Turbo. Tomorrow it could be GPT-5, Gemini, or anything else. The value Kara-OS adds is:

- The classifier prompt design (`core/brain.py:_INTENT_CLASSIFIER_SYSTEM`)
- The intent label space (12 labels including `addressing_ai`, `direct_address_to_person`)
- The vocative heuristic shortcut (`pipeline.py:_user_to_user_heuristic`)
- The mapping from intent → speak/stay-silent decision

None of those depend on which LLM is doing the inference. **That's the durable claim.**

The benchmark does NOT test "is Llama-3.3-70B good at turn-taking" — the paper already answered that (no, ~50-60%). The benchmark tests "**does Kara-OS as a layer add value, regardless of the backbone underneath.**"

---

## Hard budget — $5 absolute cap

**Hard limit: $5 USD total Together.ai spend across all runs in this session.**

The runner script MUST track cumulative cost in real time and **abort cleanly** the moment cumulative spend crosses $5. Save partial results, write what was completed, exit non-zero.

**Cost tracking:**
- After every API call, accumulate `total_input_tokens` and `total_output_tokens`
- Estimated cost = `(input_tokens × INPUT_PRICE_PER_M + output_tokens × OUTPUT_PRICE_PER_M) / 1_000_000`
- For Llama-3.3-70B-Instruct-Turbo on Together.ai: input $0.88/M, output $0.88/M (verify against Together.ai dashboard before run; update `bridge/shared/config.py` if rates differ)
- Print running cost every 50 rows: `[$0.42 spent / $5.00 cap | 234/2697 rows]`
- Project final cost (`current_spend × total_rows / rows_done`) every 50 rows. If projection > $5, abort.

**Expected actual spend:**
- Smoke test on Friends (10 rows): ~$0.02
- Smoke test on AMI (10 rows): ~$0.02
- Friends full (1,287 rows): ~$1.50
- AMI full (1,410 rows): ~$1.65
- **Total expected: ~$3.20**
- Buffer for retries / re-runs / token over-estimates: ~$1.80

**SPGI is OUT of scope.** Its 9,929 rows would cost ~$11.50 alone. Run it in a separate session if the Friends + AMI numbers warrant going further.

---

## Hard rules (read these first)

1. **Do not modify any file in `dog-ai/`** outside this `published-papers-tests/` folder. The bridge imports `core.brain._classify_intent` read-only — no edits, no monkeypatching, no new dependencies in `core/`.

2. **Do not pass any of these dataset fields to Kara-OS.** These are the answer:
   - `decision`
   - `category`
   - `target_is_addressed`
   - `addressees_in_current`
   - `reason`
   - `confidence`

   Passing any one of these is cheating. The test becomes meaningless. Bridge code must explicitly NOT read these fields when constructing classifier inputs (only the prediction-writer reads `decision` + `category` to write the output JSON, and only into the `ground_truth` and `category` fields of the prediction shape — never back into the classifier).

3. **Never start a real Kara-OS pipeline session.** No FaceDB, no audio, no vision, no orchestrator, no Whisper, no Kokoro. The bridge calls one function (`_classify_intent`) per row — that's it. If you find yourself importing `pipeline.py` or `core.brain_agent`, stop and re-read this rule.

4. **Match the paper's prediction JSON shape exactly.** Lets us reuse `code/benchmarking/metrics.py` to compute scores without writing our own metric code. Schema reference: `code/benchmarking/evaluate_baseline.py:115-139`.

5. **Honor the $5 budget cap.** See above.

---

## Reference points in the dog-ai codebase

These are the only files in `dog-ai/` you read from. You do not edit any of them.

| File | Why |
|---|---|
| `core/brain.py:977` | Definition of `_classify_intent(user_text, conversation_history) -> dict \| None` |
| `pipeline.py:4968` | Production call site — copy this calling pattern |
| `tests/eval_intent_bench.py:434` | Existing async test invocation — borrow the `asyncio.run` setup |

`_classify_intent` returns a dict like `{"turn_intent": "...", "extracted_value": "...", "confidence": 0.92, "reasoning": "..."}`, or `None` on any failure (timeout, bad JSON, missing API key). It never raises.

---

## The run — one pass, two domains

For each domain in [`friends`, `ami`], stream `dataset/<domain>/test/test_samples.jsonl` row by row. For each row:

### Step 1 — Read these fields ONLY
`decision_point_id`, `target_speaker`, `all_speakers`, `context_turns`, `current_turn`, `decision` (ground truth — only used in the prediction-writer, never passed to the classifier), `category` (only used for per-category reporting).

### Step 2 — Build classifier inputs (Pass B style)

```python
user_text = current_turn["text"]  # the most recent utterance — what the classifier judges

others = [s for s in all_speakers if s.lower() != target_speaker.lower()]
conversation_history = [
    {
        "role": "system",
        "content": (
            f"You are {target_speaker}. "
            f"The other people in this room are: {', '.join(others) if others else '(none)'}."
        ),
    }
]
for turn in context_turns:
    conversation_history.append({
        "role": "user",
        "content": f"{turn['speaker']}: {turn['text']}",
    })
# current_turn is NOT appended to history — it's passed as user_text
```

**Why the rebrand:** Kara-OS's classifier asks "is the AI being addressed?" By making the AI's identity = target_speaker for each sample, the classifier's answer naturally maps to "should target_speaker take the turn?".

### Step 3 — Call the classifier

```python
import asyncio
from core.brain import _classify_intent
sidecar = asyncio.run(_classify_intent(user_text, conversation_history=conversation_history))
```

### Step 4 — Map sidecar to SPEAK / SILENT

```python
def map_to_decision(sidecar: dict | None, target_speaker: str) -> str | None:
    """Return 'SPEAK', 'SILENT', or None (None = excluded, NOT counted as wrong)."""
    if sidecar is None:
        return None  # classifier failed (timeout, bad JSON, no API key)
    intent = sidecar.get("turn_intent")
    extracted = (sidecar.get("extracted_value") or "").strip().lower()
    target_lower = target_speaker.strip().lower()

    if intent == "addressing_ai":
        return "SPEAK"
    if intent == "direct_address_to_person" and extracted == target_lower:
        return "SPEAK"
    if intent == "direct_address_to_person":
        # someone else is being addressed
        return "SILENT"
    # casual_conversation, live_data_query, request_shutdown, unclear, etc.
    return "SILENT"
```

This mapping is **default-deny on SPEAK**. Kara-OS's classifier is trained on explicit-addressing patterns; it will likely score well on `SPEAK_explicit` and `SILENT_no_ref` categories, weaker on `SPEAK_implicit`. That's honest signal — we don't claim to predict implicit turn-taking.

### Step 5 — Write prediction row

Per row:

```json
{
  "sample_id": "<decision_point_id from source>",
  "ground_truth": "<source.decision: 'SPEAK' or 'SILENT'>",
  "prediction": "SPEAK | SILENT | null",
  "category": "<source.category: 'SPEAK_explicit' | 'SPEAK_implicit' | 'SILENT_no_ref' | 'SILENT_ref'>",
  "output_text": "<JSON-stringified classifier dict, or 'NULL' if sidecar is None>",
  "latency": <seconds, float>,
  "target_speaker": "<from source>",
  "all_speakers": [<from source>],
  "context_turns": [<truncate to last 20 from source>],
  "context_turns_total": <int, original length>,
  "current_turn": {<from source>},
  "confidence": "<source.confidence — annotation confidence, NOT ours>"
}
```

Wrap rows in the run-metadata envelope used by `code/benchmarking/evaluate_baseline.py` (read lines 215-260 for the exact wrapper structure).

**Output paths:**
- `published-papers-tests/results/karaos_friends.json`
- `published-papers-tests/results/karaos_ami.json`

---

## Folder layout under `published-papers-tests/bridge/`

```
bridge/
├── __init__.py
├── run.py                       # main runner — handles Friends + AMI in one invocation
├── adapters/
│   ├── __init__.py
│   ├── input_adapter.py         # source row → classifier inputs
│   ├── output_mapper.py         # classifier dict → SPEAK/SILENT
│   └── prediction_writer.py     # build prediction-JSON shape, matches paper
├── shared/
│   ├── __init__.py
│   ├── budget_tracker.py        # track cumulative cost, abort at $5
│   └── config.py                # paths, INPUT_PRICE_PER_M, OUTPUT_PRICE_PER_M, BUDGET_USD=5.00
└── README.md                    # how to run, expected runtime, costs
```

**Imports allowed in bridge code:**
- `core.brain._classify_intent` — read-only
- Standard lib + `httpx` (already in dog-ai venv)
- `json`, `pathlib`, `time`, `asyncio`

**Imports forbidden:**
- `pipeline.*`
- `core.audio.*`
- `core.vision.*`
- `core.brain_agent.*`
- `core.db.*`
- Anything that touches FAISS, Kuzu, SQLite, or audio/vision hardware

---

## Running the test (developer workflow)

```bash
# from C:\Users\jagan\dog-ai\published-papers-tests\
cd bridge

# Smoke test FIRST — mandatory. 10 rows from each domain.
python run.py --datasets friends ami --split test --limit 10

# Read the smoke output. If anything looks wrong (parse errors, weird ground_truth values,
# null predictions on samples that obviously have an answer), STOP and debug.
# Do not run the full pass until smoke is clean.

# Full run on both domains
python run.py --datasets friends ami --split test

# Compute metrics using the paper's own metric code
cd ../code
python -c "
from benchmarking.metrics import compute_metrics
import json
for domain in ['friends', 'ami']:
    data = json.load(open(f'../results/karaos_{domain}.json'))
    print(f'{domain.upper()}:', compute_metrics(data['predictions']))
"
```

---

## Acceptance checklist

Mark each as done in `published-papers-tests/results/RESULTS.md`:

- [ ] `bridge/` folder created with the structure above. No file in `dog-ai/` outside `published-papers-tests/` was modified
- [ ] Smoke test (`--limit 10`, both domains) ran with zero exceptions and produced valid prediction JSON files
- [ ] Friends full run completed; balanced accuracy reported
- [ ] AMI full run completed; balanced accuracy reported
- [ ] Total spend recorded in `RESULTS.md` and is **under $5.00**
- [ ] Per-category accuracy reported (SPEAK_explicit, SPEAK_implicit, SILENT_no_ref, SILENT_ref) for both domains
- [ ] Both prediction JSONs are loadable by `code/benchmarking/metrics.py:compute_metrics`
- [ ] `RESULTS.md` includes the verbatim caveat block from the bottom of this spec
- [ ] `RESULTS.md` cites the paper's baseline numbers for context (read them from the paper's tables)
- [ ] dog-ai test count `1273 passing` is unchanged (run `pytest` in `dog-ai/` to confirm — the bridge must NOT have broken anything)

---

## Failure modes — required handling

| Situation | Required behavior |
|---|---|
| Together.ai returns 429 or 503 | Retry up to 4 times with 2/4/8/16s exponential backoff. After that, mark prediction as null and continue |
| `_classify_intent` returns `None` on a row | Mark prediction as null, count separately as "exclusions" in RESULTS.md, do NOT count as wrong |
| Cumulative cost crosses $5 | Stop immediately, write whatever rows are done, exit code 1 |
| `decision_point_id` collides between rows (shouldn't happen) | Last-write-wins is fine, log a warning |
| User Ctrl+C mid-run | Save partial state to `*.partial.json`, exit gracefully |

---

## What NOT to do (real failure modes I want to prevent)

- **Don't run vanilla Llama as a baseline.** The paper publishes baselines; cite them. Spending money on a vanilla-LLM number when the paper already has them is wasted budget.
- **Don't read the whole 1,287-row file into memory just to filter.** Stream line-by-line.
- **Don't run Friends and AMI in parallel** — easier to track budget sequentially.
- **Don't add a `--force` flag to override the budget cap.** The cap is the point.
- **Don't add temperature > 0** — non-determinism kills reproducibility.
- **Don't import anything from `pipeline.py`** — the bridge is stateless.
- **Don't write any files outside `published-papers-tests/`.** No log files, no caches, no debug dumps in `dog-ai/`.
- **Don't change the classifier prompt** to "improve" results. The whole point is to test the classifier as it ships in production.

---

## RESULTS.md — required structure

The developer must produce `published-papers-tests/results/RESULTS.md` with these sections:

1. **Run metadata** — date, dog-ai git SHA (or session number from CLAUDE.md), classifier prompt hash (`_INTENT_CLASSIFIER_SYSTEM` sha256 first 12 chars), backbone model, total cost, total runtime, total rows attempted, total rows excluded (null predictions)
2. **Friends results** — overall balanced accuracy, F1, FPR, FNR, per-category accuracy table
3. **AMI results** — same shape
4. **Paper baselines (cited)** — pull the relevant rows from the paper's Table 2 / Table 3 (Llama 3.1-8B, GPT-5.2, Gemini-3.1-pro fine-tuned and zero-shot). Show side-by-side with our numbers
5. **Honest caveats** — verbatim block below
6. **Reproducibility** — exact command run, total rows seen, exit code

### Caveat block (verbatim, no paraphrase)

> *Kara-OS's production task is "should the AI speak in this conversation?" The benchmark's task is "will the named human target speaker take the next turn?" These are related but not identical. The bridge tests Kara-OS by treating the target speaker as the AI for each sample. The mapping from classifier intent labels to SPEAK/SILENT is documented in `bridge/adapters/output_mapper.py`.*
>
> *Kara-OS scores on `SPEAK_explicit` (target named directly) should be strong; scores on `SPEAK_implicit` (target takes turn without being addressed) will likely be weaker — Kara-OS's classifier doesn't claim to predict implicit turn-taking.*
>
> *Kara-OS is model-agnostic. The current backbone is Llama-3.3-70B-Instruct-Turbo via Together.ai. The same classifier prompt, intent labels, and heuristic layer would plug into any frontier LLM with no changes. The score reported here is for Kara-OS-as-a-system, not for the underlying model.*

---

## Decisions deferred — do not act without confirmation

- Running SPGI (~$11.50, exceeds budget) — separate session
- Running Kara-OS with a different backbone (GPT-5, Gemini) to demonstrate model-agnosticism empirically — separate session, costs more
- Publishing the numbers to the GitHub README — only after Jagan reviews
- Adding a Pass C (heuristic-only path, no LLM call) — could be cheap signal on what fraction of correct answers come from the regex shortcut alone vs the classifier; out of scope here
