# P0.S7.2 — Cross-Session Memory Retrieval Gap (Phase 3B D-A follow-up)

**Date:** 2026-05-18
**Author:** architect
**Status:** Spec for auditor review. Two-part fix surfacing a real architectural gap exposed by the 2026-05-18 P0.S7.1 canary. Standing by for auditor verdict → joint sign-off → developer handoff.

**Surfaced by:** Live canary 2026-05-18 (Jagan + Lexi multi-person session followed by Jagan-only return session next day). The bug demonstrates that P0.S7 D-A (SHARED CONTEXT block) closed the gap for CURRENT multi-person scenes but left the cross-session retrieval gap open for returning solo speakers.

---

## 1. Bug — concrete evidence from the two live canary sessions

### 1.1 Session A — 2026-05-18 evening (multi-person, recipe shared)

**Log:** `c:\Users\jagan\dog-ai\dog-ai\terminal_output_2026-05-18_205920.md`

In this session:
- Jagan booted system, was greeted, had a few solo turns about his day, green tea, etc.
- Lexi joined the camera frame + spoke (line 179: `[Room] Participant joined: Lexi (stranger_c760fc6e) → room_1779117653_ff5736 (now 2 participant(s))`)
- Lexi asked at line 173: *"Hi guys, can anyone one tell me how to make cheese cookies?"*
- Brain (responding to Lexi but Jagan was present) at line 197: *"To make cheese cookies, you'll need ingredients like butter, sugar, eggs, flour, and cheese - I can try to walk you through a basic recipe if you'd like."*
- Lexi at line 228: *"I have bread and butter and some florey."*
- Brain at line 250: *"It sounds like you might have some of the basics, but 'florey' isn't typically an ingredient in cheese cookies - I think you might mean flour..."* and at line 253: *"Would you like me to guide you through a simple recipe using bread, butter, and flour..."*
- Jagan at line 369: *"yeah the swimming class you reminded me ... so that's the reason I'm discussing with Lexi to make some beautiful cheese cookies"* — explicit acknowledgment that he was discussing cheese cookies with Lexi in his presence.
- Lexi's session expired at line 291; visitor alert queued for Jagan at line 296.

**The brain SHARED a recipe with Lexi while Jagan was present, in a multi-person room scope. Conversation persisted to `conversation_log` under `room_session_id=room_1779117653_ff5736` with audience tagging.**

### 1.2 Session B — 2026-05-18 night (Jagan returns alone, brain denies the recipe)

**Log:** `c:\Users\jagan\dog-ai\dog-ai\terminal_output.md`

In this session:
- Jagan booted system, was greeted (new room `room_1779119405_0efc7d`).
- Jagan at line 76: *"the cookies came out so good and thanks for your recipe"*
- Brain at line 93: ***"I'm glad to hear that the cookies turned out well, but I think there might be some confusion - I didn't actually give you a recipe, I was just chatting with you about your conversation with Lexi."***
- Jagan tried again at line 122: *"Yeah, Lexi told that you suggested her some recipes and you can use it."*
- Brain at line 143: ***"I didn't actually suggest any recipes to Lexi, I was just chatting with you about your conversation."***
- Jagan tried a third time at line 179: *"but you let's see ask you to give her some suggestions about making cookies right like she asked you and you said the recipe"*
- Brain at line 195: ***"I think I see what's going on here - I didn't actually give Lexi a recipe or suggest any specific cookie recipes to her, I was just responding to your conversation and trying to be helpful."***

**Brain confidently DENIED having given the recipe — three separate denials despite Jagan's repeated attempts.** This is a hard correctness failure. The brain DID give the recipe; the brain's response is fabricating a denial about its own prior action.

The `[SharedContext]` observability line at log line 82: `[SharedContext] gate=single_person (count=1) → skip` — confirms SHARED CONTEXT block correctly did NOT render (Jagan was alone). So the retrieval path that WOULD have surfaced the prior recipe-sharing turns was structurally gated off.

The brain DID see SOMETHING about Lexi (line 93 mentions "your conversation with Lexi") — likely from `<<<RECENT ROOMS>>>` block (room SUMMARY) or from `search_memory` on the Lexi entity. But the SUMMARY didn't include the specific recipe content.

---

## 2. Root cause analysis

The brain has 4 retrieval paths for context:

| Path | What it provides | Did it fire in Session B? |
|---|---|---|
| `_conversation_store._history[jagan_pid]` | In-memory turns from Jagan's perspective | Yes — but it's per-pid; doesn't include Lexi's turns or brain's responses TO Lexi |
| `<<<SHARED CONTEXT>>>` block (P0.S7) | Persistent room-scoped turns from conversation_log | No — gated on `active_session_count >= 2`, Jagan was alone |
| `<<<RECENT ROOMS>>>` block (S117) | LLM-synthesized SUMMARY of recent rooms | Yes — but summary, not turn-level detail |
| `search_memory` tool | Brain-initiated SQL lookup on knowledge / conversation_log | No — brain didn't call it (didn't think to) |

**Two architectural gaps stacked:**

### 2.1 Gap A — Assistant turns are NEVER extracted as facts

`TriageAgent.should_process` in `core/brain_agent.py:3820` returns `(False, "assistant turn")` for any turn where `role == "assistant"`. So when the brain says *"To make cheese cookies, you'll need butter, sugar, eggs, flour, and cheese..."* — this content is NEVER processed by the extraction pipeline. No facts are stored about what the brain said.

Verified from the prior session log (line 197 was an assistant turn, no `[BrainAgent] Extracted ...` line follows). Verified from current canary: line 143 `Triage: SKIP turn 179 — assistant turn`.

**Consequence:** the brain's own actions (what it said, what it shared, what it suggested) are invisible to its own future retrieval paths. The brain literally cannot remember things it itself said.

### 2.2 Gap B — Cross-speaker context doesn't propagate to each speaker's knowledge graph

When 3 people (P1, P2, P3) are in a room and brain says something, the current architecture stores:
- P1's user turns → extracted to brain.db under entity=P1
- P2's user turns → extracted to brain.db under entity=P2
- P3's user turns → extracted to brain.db under entity=P3
- Brain's assistant turns → SKIPPED (per Gap A)
- Kuzu graph: entity nodes connected via RELATES_TO edges built from brain.db extractions

There is **no mechanism** for "P1 witnessed brain telling P2 about cheese cookies" to land in P1's knowledge graph. The room-level context lives in `conversation_log` but the per-speaker knowledge graphs / fact tables don't ingest it.

**Consequence (the canary's exact failure mode):** when Jagan returns alone the next day and references something brain said to Lexi in his presence, Jagan's knowledge graph has no record of that exchange. The brain has no fact to retrieve via `search_memory`; the `<<<RECENT ROOMS>>>` summary captures the topic but not the specific recipe shared.

### 2.3 Why P0.S7 D-A didn't fix this

P0.S7 D-A's `<<<SHARED CONTEXT>>>` block is gated on `active_session_count >= 2`. By design, it only renders when the CURRENT scene is multi-person. The Phase 0 audit's framing was "wire S107's deferred retrieval for current multi-person scenes" — explicitly NOT cross-session continuity for returning solo speakers.

The canary just falsified that simplifying assumption: returning solo speakers DO need cross-session memory of what happened in prior multi-person scenes they were part of.

---

## 3. Fix scope — two coordinated parts

The user's direction (2026-05-18):

> "for bug 1, we have to do this (γ) Add prompt-side instruction: 'if user references something you don't remember, call search_memory BEFORE denying' and also improve the kuzu knowledge graph, like, in multi convo, lets say, person 1, 2 and 3 are there.. all the context should go to each person knowledge graph.. so its easy for brain to understand what happened when these 3 people talked."

Two sub-fixes, both load-bearing:

### 3.1 Part γ — Prompt-side honesty discipline

Add an instruction to the main chat system prompt (`_build_system_prompt` in `core/brain.py`):

> **MEMORY HONESTY DISCIPLINE:** If the user references something you said or did that you don't currently see in your context, you MUST call `search_memory` BEFORE denying. NEVER respond with "I didn't actually..." or "I don't think I..." for a user's reference to a past exchange WITHOUT first attempting retrieval via search_memory. False denial of your own actions is a hard correctness failure.

This is the same shape as the existing `<<<HONESTY POLICY>>>` block (S68 Bug N) but specialized for self-referential denials. Could either:
- (γ.1) Extend the existing `<<<HONESTY POLICY>>>` block with a new bullet
- (γ.2) Ship a new dedicated `<<<MEMORY HONESTY>>>` block

Architect's lean: (γ.1) — single source of honesty rules avoids fragmenting the prompt surface.

### 3.2 Part κ — Kuzu/extraction extension for multi-person context

Currently assistant turns are skipped entirely. The user wants every participant in a multi-person room to have the room's context reflected in their knowledge graph.

Three implementation shapes worth surfacing for auditor adjudication:

**(κ.1) Multi-person assistant-turn extraction with per-participant attribution**

When an assistant turn happens in a multi-person room (`active_session_count >= 2`), the extraction agent runs on the assistant content and produces facts attributed to EACH participant. E.g., brain says *"to make cookies you need butter, sugar, eggs, flour, cheese"* to Lexi while Jagan is present →

```
Lexi.received_recipe='cheese_cookies'
Lexi.recipe_ingredients='butter, sugar, eggs, flour, cheese'
Jagan.witnessed_recipe_share='cheese_cookies_to_Lexi'
Jagan.witnessed_topic='cheese_cookies'
```

Pros: clean, fits existing extraction surface, each participant's `search_memory` returns the fact.
Cons: requires extension to `ExtractionAgent.extract()` to handle multi-target attribution; possibly 2-3x extraction cost for multi-person turns.

**(κ.2) New Kuzu node types — Conversation/Room**

Add new node types to the graph schema:
- `Conversation` node (one per turn or one per topic)
- `Room` node (one per room_session_id)
- New REL types: `PARTICIPATED_IN`, `DISCUSSED`, `WITNESSED`

Each participant's graph traversal would surface `(Participant) -[PARTICIPATED_IN]-> (Conversation) -[DISCUSSED]-> (Topic)`.

Pros: rich semantic model, queryable via existing Kuzu traversal.
Cons: schema bump (GRAPH_SCHEMA_VERSION 2 → 3 — explicitly deferred at S107 audit per `everything_about_system.md` §338); larger change.

**(κ.3) Lightweight: room-scoped audience-tagged knowledge entries**

Extend `BrainDB.store_knowledge` to optionally write room-context-derived facts with explicit audience tagging. Reuses existing brain.db schema, no Kuzu changes. Format: when assistant turn in multi-person room, extract one or two summary facts (topic + role) and write under entity=brain, attribute=`shared_with_room`, value=`{topic} (audience: {pid_list})`, privacy_level=`household`.

Pros: minimal schema change, fast to implement.
Cons: less semantically rich; brain has to query "what did I share?" explicitly rather than getting it via entity traversal.

**Architect's lean: (κ.1)** with caveats. It's the cleanest extension of existing surface. The Kuzu schema-bump (κ.2) is real architectural work that should be its own spec (D-B's lane); (κ.3) is a stopgap that doesn't really solve the "knowledge graph reflects multi-convo context" semantic the user described.

---

## 4. D-decisions (architect's leans; auditor to lock or revise)

| ID | Topic | Architect's lean |
|---|---|---|
| D1 | Part γ landing site | γ.1 — extend `<<<HONESTY POLICY>>>` block (S68) with new bullet, not a new dedicated block |
| D2 | Part κ implementation shape | κ.1 — multi-target attribution in assistant-turn extraction |
| D3 | Trigger for κ extraction | Assistant turns ONLY in multi-person rooms (`len(_active_room_participants) >= 2`). Single-person assistant turns continue to be skipped per existing TriageAgent behavior — no value adding facts about brain self-talk. |
| D4 | Multi-target attribution shape | Per-participant fact emission. E.g., for `n` participants, emit `n` facts (one per pid) with appropriate attribute. Avoid "participant list as JSON" since that violates the existing entity-attribute-value schema. |
| D5 | Token-budget guard for assistant-turn extraction | Skip extraction if assistant turn < `ASSISTANT_TURN_EXTRACT_MIN_CHARS=80`. Short brain acknowledgments ("Got it", "OK") don't carry topic content; avoid wasteful LLM calls. |
| D6 | Privacy tier for extracted assistant-turn facts | Default `household` — multi-person room context is inherently household-tier (everyone present knows about it). Owner override applies via P0.S7 P1. |
| D7 | Existing tests impact | TriageAgent's `should_process` doesn't change for single-person assistant turns. Need new code path for multi-person assistant turns. Existing tests verifying assistant-turn-skipped behavior must be scoped to single-person context. |
| D8 | Test coverage | (a) prompt-side unit (γ): assert `<<<HONESTY POLICY>>>` block contains the new memory-denial bullet; (b) extraction behavioral (κ): multi-person assistant turn → 2+ facts emitted, one per participant; (c) integration: end-to-end replay of Session A → Session B scenario; brain calls `search_memory` and retrieves the cheese-cookies fact for Jagan. |

---

## 5. Test specification

### Phase 1 — Prompt-side discipline (γ)

1. **test_honesty_policy_block_contains_memory_denial_bullet** — source-inspection: assert `<<<HONESTY POLICY>>>` block in `core/brain.py::_build_system_prompt` contains a bullet matching `r"NEVER.*denying.*search_memory"` or equivalent verbatim text.
2. **test_honesty_policy_block_present_for_known_speakers** — behavioral: build a prompt for a `best_friend` speaker; assert the block is in the rendered prompt.

### Phase 2 — Extraction extension (κ)

3. **test_assistant_turn_extracted_in_multi_person_room** — TriageAgent (or new path) emits `should_process=True` for assistant turns when room has 2+ participants AND turn length ≥ `ASSISTANT_TURN_EXTRACT_MIN_CHARS`.
4. **test_assistant_turn_skipped_in_single_person_room** — preserves existing behavior; single-person room assistant turns still SKIPPED.
5. **test_assistant_turn_emits_per_participant_facts** — multi-person room of {Jagan, Lexi}, assistant turn "to make cookies you need flour, butter, cheese" → extraction produces ≥1 fact for Jagan AND ≥1 fact for Lexi (parametrize over participant count 2 and 3).
6. **test_assistant_turn_below_min_chars_skipped** — D5 guard; short assistant turn ("Got it!" — 7 chars) in multi-person room → skipped.

### Phase 3 — Cross-session integration (the canary scenario as a test)

7. **test_session_a_then_b_recipe_retrieval** — fixture replay:
   - Session A: simulate Jagan + Lexi multi-person room; assistant turn shares cheese-cookies recipe; end session.
   - Session B: simulate Jagan-only return; Jagan says "thanks for your recipe"; assert `_classify_intent` OR brain extraction path produces a `search_memory` call OR the brain's response does NOT contain a denial pattern (regex on `r"I didn't (actually )?give"`).
   - This is the canary's failure mode as a regression test.

### Phase 4 — Deliberate-regression confirmations

- Inject `(False, "assistant turn")` at the multi-person-room branch → test 3 fails → revert
- Drop the per-participant loop in extraction → test 5 fails → revert
- Strip the new bullet from `<<<HONESTY POLICY>>>` → test 1 fails → revert

---

## 6. Phase plan

| Phase | Scope | Tests | Effort |
|---|---|---|---|
| 1 | Part γ — `<<<HONESTY POLICY>>>` block extension + 2 tests | +2 | ~quarter-day |
| 2 | Part κ — TriageAgent multi-person assistant-turn branch + ExtractionAgent multi-target attribution + 4 tests | +4 | ~full day |
| 3 | Cross-session integration test (canary-as-regression) + 1 test | +1 | ~quarter-day |
| 4 | 3 deliberate-regression confirmations + closure | +0 | ~quarter-day |

**Net new tests: 7.** Suite delta forecast: ~2349 → ~2356 (depends on whether P0.S7.3 lands first).

---

## 7. Open items / risks

1. **Token-budget impact** — multi-person rooms now extract MORE per turn (user turn + assistant turn). Roughly doubles extraction cost in multi-person scenarios. The D5 min-chars guard reduces noise but doesn't eliminate the cost. Worth measuring in canary.
2. **Brain's own assistant turns might be attributed wrongly** — if brain says "Lexi loves cheese" (3rd party fact about Lexi), the extraction must attribute this to Lexi the SUBJECT, not just to participants who witnessed it. Existing extraction prompt (S94, S104) already handles subject vs. speaker distinction; verify it still works on assistant turns.
3. **Privacy semantic for κ** — D6 defaults extracted assistant-turn facts to `household` tier. If a participant later disputes their identity, do they retain visibility into facts attributed to them while disputed? Same P0.7 + S91 dispute-skip logic applies; verify.
4. **Cross-session fact retrieval still requires `search_memory` call** — Part γ tells the brain to call it; if the brain doesn't follow the instruction, the gap re-opens. Phase 3 integration test guards this but can't fully eliminate the LLM-compliance risk.
5. **Existing Kuzu schema (GRAPH_SCHEMA_VERSION=2) is unchanged in this spec.** Per κ.1 choice. If real production canary shows the entity-attribute-value model is insufficient for "what happened in the room," D-B (Kuzu v3) would address it as a separate spec.

---

## 8. Discipline-count predictions

- **Spec-first review cycle: 9-for-9 → 10-for-10** on closure (P0.S7.2 added — Phase 0 framing surfaced from canary evidence, multi-decision-surface spec).
- **Sub-pattern A: stays at 4 instances.** P0.S7.2 isn't a new wrong-premise catch; it's the natural follow-up to P0.S7's spec which explicitly scoped out cross-session retrieval. The canary surfaced the consequence of that scope; that's a separate discipline (induction-surfaces, below) NOT another sub-pattern A.
- **Induction-surfaces-invariant-gaps: 8-for-8 candidate** if P0.S7.1 closure already banked the 7→8 bump from the observability gap. If P0.S7.1 stays at 7-for-7 (auditor strict-read), P0.S7.2 becomes the 7→8 candidate independently — the canary surfaced TWO genuinely new architectural gaps (cross-session retrieval + KAIROS timing). Auditor adjudicates which closure carries the bump.
- **Tripwires-must-match-deferral-surface: stays 4-for-4.**
- **Developer-improves-on-spec: stays 6-for-6** unless code phase surfaces a mechanism improvement.

---

## 9. Reference documents

- `tests/p0_s7_audit.md` — Phase 0 audit (D-A first slice)
- `tests/p0_s7_plan_v2.md` — Plan v2 (D-A code contract; explicitly scoped out cross-session)
- `tests/p0_s7_1_spec.md` — P0.S7.1 observability micro-PR (what made this bug visible)
- `tests/p0_s7_3_spec.md` — P0.S7.3 KAIROS fix (sibling follow-up; ship first per architect's queue)
- **`c:\Users\jagan\dog-ai\dog-ai\terminal_output_2026-05-18_205920.md`** — Session A log (multi-person, recipe shared). Lines 173, 197, 228, 250, 253 carry the recipe-sharing turns.
- **`c:\Users\jagan\dog-ai\dog-ai\terminal_output.md`** — Session B log (Jagan returns alone, brain denies). Lines 76-200 carry the three denial responses.
- `core/brain.py::_build_system_prompt` — landing site for Part γ
- `core/brain_agent.py::TriageAgent.should_process` (line 3820) — Part κ entry point
- `core/brain_agent.py::ExtractionAgent.extract` (line 4078) — Part κ extension target
- `everything_about_system.md` §338 — Kuzu v3 deferral context

---

## 10. Next steps

1. **Auditor reviews this spec.** Specifically: (a) Part γ choice (γ.1 vs γ.2); (b) Part κ implementation shape (κ.1 vs κ.2 vs κ.3); (c) D5 min-chars threshold reasonable?; (d) D6 privacy tier default; (e) anything missed in the threat model.
2. **D-decisions locked** at audit sign-off.
3. **Plan v2** if precision items surface (likely; this is a substantive architectural extension).
4. **Joint sign-off → developer handoff** for 4-phase implementation.
5. **After ship: re-canary** with the same Session A → Session B scenario; expect brain to call `search_memory` and surface the cheese-cookies recipe correctly.
