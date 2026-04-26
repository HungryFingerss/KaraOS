# Published-Paper Benchmarks for Kara-OS

This folder holds external academic benchmarks we plan to run Kara-OS against, to validate its capabilities with reproducible numbers.

---

## Test 1 — "Speak or Stay Silent: Context-Aware Turn-Taking in Multi-Party Dialogue"

**Paper:** arxiv.org/abs/2603.11409 (submitted to Interspeech 2026)
**Authors:** Bhagtani, Anand, Xu, Yadav (Ishiki Labs)
**Dataset license:** Apache 2.0
**Code license:** in repo
**Downloaded:** 2026-04-26

### What the paper claims
Multi-party turn-taking (knowing when to speak vs stay silent in a 3+ person conversation) is **not** an emergent LLM ability. Zero-shot LLMs fail. Their fix: supervised fine-tuning on 120K labeled conversations gives up to +23 percentage points balanced accuracy.

### Why we care
Kara-OS is built around exactly this problem (Phase 3B: ROOM block, direct-address detection, TURN ARBITRATION rules, user-to-user heuristic). Running this benchmark is the difference between "works in our living room" and "validated against the same test the paper used."

---

## Folder layout

```
published-papers-tests/
├── README.md                  ← you are here
├── code/                      ← cloned from github.com/ishikilabsinc/context_aware_modeling (main branch)
│   ├── benchmarking/          ← evaluation pipeline
│   │   ├── evaluate_baseline.py
│   │   ├── run_benchmark.py
│   │   ├── metrics.py
│   │   ├── prepare_data.py
│   │   └── validate_data.py
│   ├── data_pipelines/        ← how the dataset was built (we don't need)
│   ├── evaluation/            ← fine-tuned model eval (we don't need)
│   ├── fine_tuning/           ← LoRA training (we don't need)
│   ├── utils/                 ← shared constants, prompt templates
│   ├── README.md              ← upstream README (read this for the eval pipeline)
│   └── requirements.txt
└── dataset/                   ← cloned from huggingface.co/datasets/ishiki-labs/multi-party-dialogue
    ├── ami/
    │   ├── test/test_samples.jsonl       (1,410 rows — verified)
    │   ├── val/val_samples.jsonl         (1,408 rows — verified)
    │   └── train/                         (CoT variant only — we don't need train)
    ├── friends/
    │   ├── test/test_samples.jsonl       (1,287 rows — verified)
    │   └── val/val_samples.jsonl         (1,286 rows — verified)
    ├── spgi/
    │   ├── test/test_samples.jsonl       (9,929 rows — verified)
    │   └── val/val_samples.jsonl         (9,929 rows — verified)
    └── README.md                          (upstream dataset card)
```

**Test split totals (what we evaluate against):**
- AMI: 1,410
- Friends: 1,287
- SPGI: 9,929
- **Total test rows: 12,626**

(Paper headline "120K" is the full dataset including train+val+test; the test set we'll actually score against is 12,626.)

---

## Sample structure

Each row in the JSONL is a "decision point" — a moment in a conversation where we ask: should `target_speaker` speak next, or stay silent?

```json
{
  "decision_point_id": "test_5turns_1414_turn0_targetross",
  "target_speaker": "ross",
  "all_speakers": ["rachel", "ross"],
  "context_turns": [...],
  "current_turn": {
    "speaker": "rachel",
    "text": "Ross, you gotta know there is nothing between me and Mark."
  },
  "addressees_in_current": ["ross"],
  "target_is_addressed": true,
  "decision": "SPEAK",
  "category": "SPEAK_explicit",
  "reason": "ross was addressed by rachel and spoke (ground truth)"
}
```

Categories:
- `SPEAK_explicit` — target was directly addressed and replied
- `SPEAK_implicit` — target took the turn without being addressed by name
- `SILENT_no_ref` — conversation moved on, target not relevant
- `SILENT_ref` — target was mentioned but didn't take the turn

---

## What's NOT here yet (next decisions)

The dataset and code are ready. What we still need to decide before running:

1. **Which Kara-OS path to evaluate.**
   - **Option A — vanilla Llama-3.3-70B (our base model):** baseline number. Should match the paper's "untrained 70B" numbers (~50–60% balanced accuracy). Establishes that we're not cheating.
   - **Option B — Kara-OS classifier prompt + heuristics path:** the real thing. This is what we want to compare against the paper's fine-tuned models (~75–85%).
   - **Option C — both, side-by-side.** Slightly more API cost, vastly more credible result.

2. **Adapter design.** The paper's `target_speaker` is a human; Kara-OS's "should I speak?" is the AI's decision. They're not 1:1. Need a clean mapping rule (likely: treat AI as target_speaker, map our intent labels to SPEAK/SILENT).

3. **API budget.** 12,626 test rows × (Together.ai cost per call). Rough estimate: $30–80 for a single full test pass on the 70B baseline; classifier-path adds another $30–80. Budget for 2–3 runs total.

4. **Whether to evaluate on all 3 domains or start with one.** Friends (1,287 rows, ~$5) is the cheapest first run to debug the adapter end-to-end before spending on AMI + SPGI.

---

## Reproducibility notes

- All clones used `git clone` (no manual file edits)
- Dataset commit hash and code commit hash should be recorded in any results file we publish
- Their `requirements.txt` pins Python 3.9 / 3.10 — we may not need their full env if we wire Kara-OS's classifier in directly via our own code

---

## When this is done

If Kara-OS's score on this benchmark lands close to or above the paper's fine-tuned model numbers, it's a defensible external validation. The README in the main repo can cite this run with the actual number, the test count, and a link to the prediction JSONs.
