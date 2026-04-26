# Session 119 Spec — Path 1: Implicit-Addressing Detection (Prompt-Only)

**Goal:** Lift Kara-OS's AMI score from ~20% (vocative-only classifier) toward 50–65% by teaching the classifier to recognize **implicit addressing patterns** — without fine-tuning, without architecture changes, without breaking explicit-addressing cases (Friends).

**Implementation: in `dog-ai/`. Validation: in `published-papers-tests/`.**

---

## What Path 1 actually changes

One file in `core/brain.py`. One file in `core/config.py`. One file in `published-papers-tests/bridge/adapters/`.

That's it. **No architectural changes. No new code paths. No state-tracking. Pure prompt + label expansion.**

If the developer finds themselves modifying `pipeline.py`, `core/brain_agent.py`, or anything in the orchestrator — stop. That's not Path 1.

---

## Hard rules

1. **Production behavior must stay the same.** No existing pipeline gate may route on the new label. The new label is purely an emit option for the classifier; downstream production code should treat it as a no-op (i.e., it falls through to the existing default-allow path). Only the bridge consumes it as SPEAK.

2. **Golden corpus must not regress.** Every existing test case that currently passes must continue to pass. New cases must be added for the new label.

3. **Classifier prompt hash will change.** This is expected. Update Phase 5 drift baseline accordingly (mention in the session ship note).

4. **Friends score must not drop.** If the new prompt causes Friends to fall below the smoke's 90% by more than ~5 points, prompt expansion went too far. Roll back and revise.

---

## The change — three files

### File 1: `core/config.py`

Add ONE new intent label to the `INTENT_LABELS` frozenset:

```python
"topical_participant_response"
```

Position: alphabetical or grouped with similar response intents — developer's discretion. Update whatever invariant test in `test_pipeline.py` enforces the exhaustive label set.

**Do NOT add this label to `TOOL_INTENT_MAP`.** The new label is not gating any tool. It's purely a classification observability output.

### File 2: `core/brain.py` — `_INTENT_CLASSIFIER_SYSTEM`

The expansion has two parts: a new section explaining implicit addressing, and a few-shot example block. Land them after the existing CRITICAL `unclear` directive but before the existing INJECTION DEFENSE block.

#### Part A: Add a new section

```
IMPLICIT ADDRESSING — recognize when YOU (the AI) are conversationally expected to respond
even without being named:

A turn that asks for a response from "the room" or continues a thread you have been actively
participating in counts as implicit addressing. Use the label `topical_participant_response`
for these cases.

The two-step test:
  1. Have YOU been an ACTIVE PARTICIPANT in the recent conversation thread (last 3-5 turns)?
     - Active = you spoke, were addressed by name, or directly engaged with the topic.
     - Bystander = you have not spoken or been addressed; the topic does not involve you.

  2. Does the most recent utterance INVITE a response?
     - YES — group-directed question ("right?", "what do we think?", "you know?", "anyone?")
     - YES — substantive contribution that ends with a thought waiting for acknowledgment
     - YES — direct continuation of a thread you and the speaker were just discussing
     - NO  — speaker is making a self-contained statement to the group with no question
     - NO  — speaker is addressing someone else specifically by name

If YES to both → label `topical_participant_response`, conf ≥ 0.70.
If NO to step 1 → you are a bystander → casual_conversation, SILENT by default.
If YES to step 1 but NO to step 2 → casual_conversation, SILENT.

When uncertain → casual_conversation. Never invent reasons to speak.
```

#### Part B: Add few-shot examples

Add these AT THE END of the existing examples section. Mark the speaker IDs naturally so the classifier can generalize.

```
EXAMPLE — implicit topical participation:
History:
  Jagan: I've been thinking about getting a new car.
  AI: What kind are you considering?
  Jagan: Maybe an EV. Range anxiety is a thing though, right?
Classification: turn_intent=topical_participant_response, extracted_value=null, confidence=0.85
Reasoning: AI is an active participant in the topic; Jagan ends with a "right?" inviting response.

EXAMPLE — implicit group question, AI is active:
History:
  Lexi: I've never seen "The Office" actually.
  AI: It's worth watching.
  Lexi: So we should pick something for movie night?
Classification: turn_intent=topical_participant_response, extracted_value=null, confidence=0.80
Reasoning: AI was engaged in the thread; "we should pick something" invites group input.

EXAMPLE — bystander, do NOT speak:
History:
  Jagan: How was your day?
  Lexi: Long. Ran into Sarah at the market.
  Jagan: What did she say?
Classification: turn_intent=casual_conversation, extracted_value=null, confidence=0.90
Reasoning: AI has not been part of this exchange; Jagan is asking Lexi specifically. AI is a bystander.

EXAMPLE — group-directed question, AI is active:
History:
  AI: We could try the new restaurant on 5th.
  Jagan: Sounds good.
  Lexi: Anyone allergic to anything?
Classification: turn_intent=topical_participant_response, extracted_value=null, confidence=0.75
Reasoning: "Anyone" is group-directed; AI is part of the active group.

EXAMPLE — substantive close, no question, no group invite:
History:
  Lexi: I had pasta for dinner.
  Jagan: Nice.
  Lexi: Yeah it was pretty good.
Classification: turn_intent=casual_conversation, extracted_value=null, confidence=0.85
Reasoning: No question, no invitation, just a self-contained statement. AI should not chime in.
```

The negative examples (bystander, substantive-close) are **load-bearing** — they prevent the classifier from over-predicting `topical_participant_response` and chiming in unnecessarily. Don't drop them to "tighten" the prompt.

### File 3: `published-papers-tests/bridge/adapters/output_mapper.py`

Add ONE branch to `map_to_decision()`:

```python
if intent == "topical_participant_response":
    return "SPEAK"
```

Place it before the `direct_address_to_person` branch. Order doesn't strictly matter since these are mutually exclusive intents, but proximity to `addressing_ai` is most readable.

---

## Test impact in `dog-ai/`

The classifier prompt change WILL break some tests. Each break must be triaged honestly: is it (a) a regression we caused, or (b) a calibration update because the new prompt correctly handles a previously-mislabeled case?

### Tests that will likely need updates

| Test | Why | Action |
|---|---|---|
| Classifier prompt hash assertion (e.g. `test_intent_classifier_system_hash`) | Hash changes by design | Update to new hash. Note in commit: "Path 1 baseline reset" |
| Golden corpus invariant test that checks INTENT_LABELS exhaustively | New label added | Update expected set |
| Golden corpus rows that classified as `casual_conversation` for cases that are actually implicit addressing | Some rows may flip to `topical_participant_response` | Re-label only if the new label is correct. Tag with `regression_session_119_relabel` per the Session 81 taxonomy |
| Any test asserting Friends-style explicit addressing still works | Should NOT break | If it does, the prompt expansion went too far — revise |

### Tests that MUST NOT break

- Every `assign_own_name` / `assign_system_name` / `request_shutdown` / `deny_identity` test — Path 1 doesn't touch the mutation-tool gates. If any of these break, the prompt expansion is interfering with mutation detection. Revise.
- Every existing `addressing_ai` test — Friends-style direct addressing must still classify as `addressing_ai`, not `topical_participant_response`. The few-shot examples in Part B should make this obvious.
- Every existing `direct_address_to_person` test (3B.2 silent-skip) — implicit addressing should not bleed into "addressing another person."

### How to triage breaks

1. Run `pytest` after the prompt change. Count failures.
2. For each failure: read the failing case. Decide:
   - **Regression** — new prompt mishandles a case the old prompt handled correctly → revise prompt
   - **Calibration** — old prompt mislabeled the case; new prompt is more accurate → update test
3. Document each calibration in the commit message.
4. If more than ~10 tests need calibration, that's a smell — either the prompt expansion is too aggressive, or there were a lot of edge cases the old prompt was getting wrong. Pause and discuss before plowing through updates.

### New tests to add

Add 5–8 golden corpus rows to `tests/golden_intent.jsonl` covering:

| Source tag | Coverage |
|---|---|
| `regression_session_119` | 2 positive examples — clear `topical_participant_response` cases |
| `regression_session_119` | 2 negative examples — bystander cases that must classify as `casual_conversation` |
| `regression_session_119` | 1 "edge" — a substantive close with no question, must NOT trigger SPEAK |
| `regression_session_119` | 1 explicit-addressing regression guard — Friends-style "Hey Lexi" must still classify as `direct_address_to_person`, not `topical_participant_response` |

These guard against the failure mode where future prompt edits accidentally collapse the distinction.

---

## Validation in `published-papers-tests/`

After dog-ai changes pass:

```bash
# Confirm dog-ai is clean
cd C:\Users\jagan\dog-ai\dog-ai
pytest

# Smoke the bridge with new classifier
cd ..\published-papers-tests\bridge
python run.py --datasets friends ami --split test --limit 10

# Read smoke output:
#  - Friends accuracy should still be ~80–95% (no regression)
#  - AMI accuracy should lift from ~20% baseline toward 40–65%
#  - Look for `topical_participant_response` appearing in AMI predictions

# If smoke is clean, full run on both
python run.py --datasets friends ami --split test
```

Cost: ~$3.20 for the full run (same as the original spec). Within the $5 cap with ~$1.80 headroom remaining.

---

## Acceptance criteria

- [ ] `INTENT_LABELS` updated; invariant test passes
- [ ] `_INTENT_CLASSIFIER_SYSTEM` updated; classifier prompt hash recorded in commit
- [ ] Bridge `output_mapper.py` maps new label to SPEAK
- [ ] All existing dog-ai tests pass (after triage and any necessary calibration updates)
- [ ] 5–8 new golden corpus rows added with `regression_session_119` source tag
- [ ] Smoke run completes without exceptions
- [ ] Full Friends + AMI run completes
- [ ] **Friends balanced accuracy is within 5 points of pre-Path 1 number** (no regression on what works)
- [ ] **AMI balanced accuracy lifts from ~20% to at least 40%** (signal that Path 1 is doing something)
- [ ] `RESULTS.md` updated with: pre-Path-1 vs post-Path-1 numbers, classifier prompt hash before/after, total cost, examples of `topical_participant_response` firing correctly and any cases where it misfires

---

## Decision gates

After the test, three branches:

| AMI lift | Friends regression | Decision |
|---|---|---|
| AMI ≥ 50% | Friends ≤ 5pt drop | **Path 1 is a clear win.** Ship the prompt change. AMI is now in respectable range without architectural work |
| AMI 30–50% | Friends ≤ 5pt drop | **Partial win.** Worth shipping. Discuss whether Path 2 (two-stage classifier) earns the next spend |
| AMI < 30% OR Friends drop > 5pt | — | **Roll back.** The prompt approach hit a ceiling. The original $1.65 experiment (paper's prompt on 70B) becomes the next data point — it would tell us whether ANY prompt-only approach can clear the bar |

Do not ship Path 1 if Friends regresses more than 5 points. The home use case is the priority — better to leave AMI weak than break what works.

---

## What this spec deliberately does NOT do

- **Does not add multi-turn state tracking** — that's Path 3 territory
- **Does not add a second classifier call** — that's Path 2 territory
- **Does not change pipeline.py** — production gate logic stays exactly as-is
- **Does not add the `topical_participant_response` label to any TOOL_INTENT_MAP entry** — it's not a mutation tool intent, it's a behavioral hint
- **Does not modify the bridge's input adapter** — the bridge passes the same 4 fields it always did

If the developer finds Path 1 isn't enough to lift AMI to 40%+ without breaking Friends, **don't escalate to Path 2 in the same session**. Land what you have, document the ceiling, and let Jagan decide whether to invest further.

---

## Rollback plan

If Path 1 ships and Jagan reports unexpected production behavior:

1. Revert `_INTENT_CLASSIFIER_SYSTEM` to its pre-119 state (git revert the prompt changes)
2. Keep `topical_participant_response` in `INTENT_LABELS` — the label being defined doesn't hurt anything when the prompt no longer emits it
3. Bridge mapper change is harmless to leave in — it'll just never fire
4. Note the rollback in CLAUDE.md as Session 120
