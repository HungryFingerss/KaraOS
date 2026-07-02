# Sanitize Spec — `karaos_friends_test.json` for GitHub

**Goal:** Produce a license-safe, publishable version of the Friends prediction file. Strip copyrighted Friends dialogue, keep everything that proves the score.

**Scope:** ~1 hour of dev work. One new script, one new output file, one RESULTS.md update.

---

## What changes

| File | Action |
|---|---|
| `published-papers-tests/bridge/scripts/sanitize_predictions.py` | NEW — small script, ~30 lines |
| `published-papers-tests/results/karaos_friends_test.json` | NEW — sanitized predictions, safe to commit |
| `published-papers-tests/results/karaos_friends.json` | LEAVE ALONE — keep locally as the full record. Add to `.gitignore` |
| `published-papers-tests/results/RESULTS.md` | UPDATE — point readers at the sanitized file + explain how to re-verify |

---

## Why we can't ship the existing JSON as-is

The current `karaos_friends.json` contains 1,287 verbatim Friends TV show dialogue snippets in the `current_turn.text` and `context_turns[].text` fields. That's copyrighted Warner Bros content. The HuggingFace dataset re-publishes it under research licensing; we re-publishing it on a public GitHub repo is a different legal posture.

**Solution:** strip the dialogue text. Keep the verification path intact.

---

## Field-level decisions

### KEEP (these prove the score, no copyright issue)

| Field | Why |
|---|---|
| `sample_id` | Join key — reader can match against HuggingFace dataset to reconstruct the full record |
| `ground_truth` | The dataset's SPEAK/SILENT label — needed for accuracy verification. This is a single-word label, not dialogue |
| `prediction` | Our classifier's output — our own data |
| `category` | The dataset's category label (SPEAK_explicit, etc.) — single-word label, not dialogue |
| `output_text` | Our classifier's reasoning — our own generation |
| `latency` | Our timing measurement |
| `target_speaker` | First name only ("ross", "monica") — name strings, not dialogue |
| `all_speakers` | List of first names — same |
| `context_turns_total` | Integer count — not content |
| `confidence` | Annotator's confidence label ("high"/"medium"/"low") — not dialogue |

### STRIP (these are the copyright concern)

| Field | Why |
|---|---|
| `current_turn` (entire object) | Contains `.text` with verbatim Friends dialogue |
| `context_turns` (entire array) | Each item contains `.text` with verbatim Friends dialogue |

Drop these fields entirely. Don't try to keep `current_turn.speaker` separately — cleaner to just remove the whole object.

### CHECK BEFORE SHIPPING (one residual risk)

The `output_text` field contains the classifier's reasoning. In theory, the LLM's reasoning could quote the source dialogue verbatim ("The user said 'Hi, it's me'..."). In practice, LLM reasoning paraphrases.

**Mandatory spot-check before shipping:**
- Sample 20 random rows from `output_text`
- Look for direct verbatim quotes from `current_turn.text` (≥6 consecutive words copied)
- If 0–1 cases found → ship as-is (residual risk acceptable)
- If 2+ cases found → escalate. We'll need a regex scrub that redacts quoted spans before publishing. Don't ship the file until that's resolved.

---

## Run metadata to keep at the top of the file

The existing run-metadata wrapper has these — keep them all:

```json
{
  "dataset": "friends",
  "model_key": "karaos",
  "model_id": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
  "system_prompt_repeat": 1,
  "predictions": [ ... sanitized rows ... ]
}
```

Add ONE new field to the top of the file (sibling of `dataset`):

```json
"_license_note": "Source dialogue stripped to comply with Friends-MMC redistribution terms. To verify these predictions: download the source dataset from huggingface.co/datasets/ishiki-labs/multi-party-dialogue, join on sample_id, and recompute metrics with the paper's metrics.py. See RESULTS.md for full instructions."
```

This makes the licensing decision visible, not hidden, and gives the verifier the exact path to reconstitute the full record.

---

## The script — `bridge/scripts/sanitize_predictions.py`

Spec, not code. Developer writes it.

**Inputs:**
- `--input`: path to full prediction JSON (default: `results/karaos_friends.json`)
- `--output`: path to sanitized JSON (default: `results/karaos_friends_test.json`)

**Behavior:**
1. Load input JSON
2. For each item in `predictions`:
   - Drop `current_turn` (entire object)
   - Drop `context_turns` (entire array)
   - Keep all other fields
3. Add `_license_note` field (verbatim text above) to the top-level wrapper
4. Print summary:
   - Rows processed
   - Average row size before/after
   - Total file size before/after
5. Run the spot-check pass:
   - Sample 20 random rows
   - For each: load the corresponding raw row from the input file
   - Substring-match check: does `output_text` contain ≥6-consecutive-word strings from `current_turn.text`?
   - Print pass count and any flagged samples

**Acceptance:** spot-check finds ≤1 quote leak; otherwise abort and report.

**Idempotent:** running twice produces the same output file.

---

## RESULTS.md update

Add a new section (after the existing reproducibility section) with this exact structure:

```markdown
## Verifying these results

The sanitized predictions are at `karaos_friends_test.json` (Friends dialogue stripped per
license terms). To verify our reported accuracy:

1. Download the source dataset:
   ```bash
   git clone https://huggingface.co/datasets/ishiki-labs/multi-party-dialogue
   ```
2. Join our predictions to the source data on `sample_id`
3. Run the paper's metrics on the joined data:
   ```bash
   python -c "
   from benchmarking.metrics import compute_metrics
   import json
   data = json.load(open('karaos_friends_test.json'))
   print(compute_metrics(data['predictions']))
   "
   ```

You should see the same balanced accuracy reported in this file (58.66%).
```

---

## Acceptance checklist

- [ ] `bridge/scripts/sanitize_predictions.py` written, idempotent, runs clean
- [ ] `results/karaos_friends_test.json` produced; significantly smaller than original (likely 200–400 KB vs 1.4 MB)
- [ ] Spot-check pass on `output_text` quotes — 0 or 1 cases found, documented in commit message
- [ ] `_license_note` field present at top of sanitized JSON
- [ ] All `current_turn` and `context_turns` fields dropped
- [ ] All other fields preserved exactly
- [ ] `results/karaos_friends.json` added to `.gitignore` (full file kept locally, never committed)
- [ ] `results/RESULTS.md` updated with the verification section
- [ ] Sanity test: load sanitized file, run paper's `metrics.py`, confirm number matches the original 58.66%

---

## What NOT to do

- **Don't generalize across the Friends dialogue values into "anonymized speakers" or paraphrases.** That risks claiming to have replaced source content with our own — confusing for verifiers. Just drop the fields cleanly.
- **Don't strip `output_text`.** That's our own generation. Keeping it lets readers see how the classifier reasoned.
- **Don't ship `karaos_friends.json`** (the unsanitized version). Even in a private branch.
- **Don't auto-publish to GitHub from this script.** The script produces the file; Jagan reviews it; Jagan commits it. Manual control.

---

## Cost: $0. No API calls. Pure data sanitization.
