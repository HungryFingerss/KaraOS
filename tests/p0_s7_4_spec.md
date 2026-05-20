# P0.S7.4 — γ strengthening: autonomous search_memory on first mention

**Date:** 2026-05-19
**Author:** architect
**Status:** Direct-to-developer micro-PR (parallel to P0.S7.D-C). No Phase 0 audit needed — prompt-engineering, not architectural. Standing by for developer implementation → ships into the bundled-queue canary alongside D-C / D-B / D-D / D-E.

**Surfaced by:** P0.S7.2 partial-validation canary 2026-05-19 (`terminal_output.md`). The γ MEMORY HONESTY DISCIPLINE bullet (P0.S7.2 Phase 1) shifted brain's behavior from "confident denial" → "hedge until user explicitly asks." Better than the prior canary's confident-denial pattern, but NOT the locked γ target — "autonomously call search_memory BEFORE denying or hedging on first mention."

---

## 1. Bug

Live canary observation (`terminal_output.md` lines 96-237):

- **Turn 1** (line 96): Jagan says *"yeah Lexi just now called me and she was she asked me what you said about the burger that she she told you"*
- **Brain response** (line 115): *"I'm not sure what you're referring to, could you clarify what Lexi asked you about and what I supposedly said about a burger?"* — hedge, NO search_memory call
- **Turn 2** (line 156): Jagan says *"She said something like she asked you about the recipe of the classic burger or something..."*
- **Brain response** (line 174): *"I don't recall having a conversation with Lexi about a burger recipe or a milkshake..."* — hedge-adjacent-to-denial, NO search_memory call
- **Turn 3** (line 216): Jagan EXPLICITLY says *"Can you check the lexi personal context and just tell me what all you discussed with lexi last time"*
- **Brain response** (line 237): finally calls `search_memory('Lexi', 'last conversation')` → 15 facts retrieved → correct response (line 242)

**Gap**: γ shifted brain's tone (no confident denial) but didn't trigger autonomous tool calling. Brain waited for explicit user permission before checking memory. The γ target was "call search_memory BEFORE denying" — currently observed: "hedge politely until user permits memory access."

---

## 2. Fix

Strengthen the γ MEMORY HONESTY DISCIPLINE bullet in `<<<HONESTY POLICY>>>` block (core/brain.py:2283-2293) to:

(a) Demand autonomous tool call on FIRST mention of an unrecognized reference, not after user prompting.
(b) Explicitly reject hedge phrasings as a substitute for retrieval.

### 2.1 Current bullet (P0.S7.2 Phase 1 — too weak)

```
- MEMORY HONESTY DISCIPLINE (P0.S7.2 γ, 2026-05-18): If the user
  references something you said or did that you don't currently see
  in your context, you MUST call search_memory BEFORE denying.
  NEVER respond with "I didn't actually..." or "I don't think
  I..." or similar self-denial phrasings for a user's reference
  to a past exchange WITHOUT first attempting retrieval via
  search_memory. False denial of your own prior actions is a hard
  correctness failure — it makes the system untrustworthy. When
  search_memory returns nothing matching, you may hedge ("I don't
  have clear notes on that — can you remind me?") but you MUST
  NOT confidently deny.
```

### 2.2 Strengthened bullet (P0.S7.4 — locked)

```
- MEMORY HONESTY DISCIPLINE (P0.S7.2 γ + P0.S7.4 strengthening,
  2026-05-19): If the user references something you said or did
  that you don't currently see in your context, you MUST call
  search_memory IMMEDIATELY — on the FIRST mention, BEFORE
  responding. Do NOT hedge first. Do NOT ask the user to clarify
  first. Do NOT wait for the user to explicitly tell you to check
  memory. The first response to an unrecognized self-reference
  MUST be a search_memory tool call, not a verbal hedge.

  Forbidden first-response patterns (call search_memory instead):
  - "I'm not sure what you're referring to, could you clarify..."
  - "I don't recall having a conversation about..."
  - "I don't think I said..."
  - "I didn't actually..."
  - "Can you remind me what we discussed?"

  Required first-response pattern: call search_memory with the
  speaker_name and topic keyword from the user's reference.
  AFTER retrieval:
  - If search_memory returns matching facts → respond with what
    you found ("I remember — we discussed X...").
  - If search_memory returns nothing → THEN you may hedge
    ("I checked my notes and don't have clear records on that
    — can you remind me?"). The hedge MUST acknowledge the
    retrieval attempt.

  False denial OR pre-retrieval hedging of your own prior actions
  is a hard correctness failure — it makes the system untrustworthy.
```

**Key strengthening deltas:**
- "MUST call search_memory BEFORE denying" → "MUST call search_memory IMMEDIATELY — on the FIRST mention, BEFORE responding"
- Explicit forbidden-first-response list (5 patterns including the canary's exact hedges)
- Explicit required-first-response pattern (tool call, not verbal response)
- Hedge fallback ONLY allowed AFTER retrieval attempt + must acknowledge the retrieval
- "False denial OR pre-retrieval hedging" — extends the failure-mode definition to include hedging

---

## 3. Test

`tests/test_p0_s7_4_gamma_strengthening.py` (new) — 1 source-inspection test:

**`test_honesty_policy_block_contains_strengthened_memory_discipline`**

Asserts the strengthened bullet text is present in `core/brain.py::_build_system_prompt`'s `<<<HONESTY POLICY>>>` block. Specifically:

- Marker label `MEMORY HONESTY DISCIPLINE` + P0.S7.4 strengthening tag (`P0.S7.4 strengthening`) — source-inspection
- Required phrasings (single-line literal substrings):
  - `"IMMEDIATELY"` (the strengthening keyword)
  - `"on the FIRST mention"`
  - `"BEFORE responding"`
  - `"Do NOT hedge first"`
  - `"call search_memory"` (multiple references)
- Forbidden-first-response pattern list includes at least 3 of the 5 patterns
- Hedge fallback gating language: `"AFTER retrieval"` AND `"acknowledge the retrieval attempt"`
- Failure-mode definition extended: `"False denial OR pre-retrieval hedging"`

Single test, no parametrize. Estimated effort: ~10 min implementation + ~10 min test = ~20 min total.

---

## 4. Validation

- Test green; full-suite green at 2374 (assuming D-C ships first at 2373).
- Manual sanity: build a prompt for a known speaker; visually confirm the strengthened bullet renders. Verify P0.S7.2's hedge fallback ("I don't have clear notes on that") is now gated on "AFTER retrieval."

**Real-LLM validation** — deferred to the bundled-queue canary that fires after D-A + D-C + D-B + D-D + D-E + P0.S7.4 all ship. Per P0.S7.2 §11.10 re-canary discipline.

---

## 5. Suite delta

Forecast: 2373 → 2374 (+1). Assumes D-C lands first.

---

## 6. Estimated effort

~30 min total (10 min prompt edit + 10 min test write + 10 min full-suite verification).

---

## 7. Closure-report banking

Phase 4 closure narrative for the bundled-queue work should bank P0.S7.4 alongside D-C / D-B / D-D / D-E:

- **P0.S7.4** — γ strengthening shipped (1 test). Real-LLM validation gated on the bundled-queue canary.
- **Re-canary expectations** for the bundled-queue canary (post-D-E ship):
  - Brain calls `search_memory` IMMEDIATELY on first mention of an unrecognized reference (target: 0 forbidden-first-response hedges in the canary log).
  - Brain's first response after the user references a prior exchange is the tool call, not a verbal hedge.
  - Hedge appears only AFTER retrieval and acknowledges the retrieval attempt.
- **If canary FAILS** (brain still hedges or denies pre-retrieval): file a P0.S7.5 follow-up to further strengthen the prompt OR investigate whether the LLM's tool-calling compliance has hit a ceiling.

---

## 8. Discipline-count predictions

- **Spec-first review cycle: stays 11-for-11** (P0.S7.4 is a micro-PR direct-to-developer; not a full spec-first cycle).
- **Canary-finding tracker: stays at 2 instances** (no new canary-finding banked by THIS spec; the canary observation that motivated P0.S7.4 is the same one banked under P0.S7.2's tracker entry).
- **Other disciplines unchanged.**

---

## 9. Reference

- `core/brain.py:2283-2293` — current γ bullet (P0.S7.2 Phase 1 landing site; strengthening target)
- `tests/p0_s7_2_plan_v2.md` §11.10 — re-canary discipline
- `terminal_output.md` lines 96-237 — canary evidence that motivated P0.S7.4
- `tests/p0_s7_2_phase1` — original γ Phase 1 test (regression-guard pattern reference)
