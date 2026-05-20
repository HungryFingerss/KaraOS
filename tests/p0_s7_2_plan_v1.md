# P0.S7.2 — Cross-Session Memory Retrieval Gap — Plan v1

**Date:** 2026-05-18
**Author:** architect
**Status:** Plan v1 — drafted against Phase 0 D-lock (2026-05-18) + auditor's 4 precision items + 2 informational observations from `tests/p0_s7_2_spec.md`'s Phase 0 review verdict. Standing by for auditor's Plan v1 review → Plan v2 → joint sign-off → developer handoff.

**Phase 0 spec:** `tests/p0_s7_2_spec.md` (premise: Session A → Session B canary surfaced confident-denial behavior; two-part fix γ + κ).

---

## 1. Locked decision reference (Phase 0 D-lock 2026-05-18)

| ID | Topic | Locked at | Notes |
|---|---|---|---|
| D1 | Part γ landing site | γ.1 — extend existing `<<<HONESTY POLICY>>>` block, no new block | Single source of honesty rules |
| D2 | Part κ implementation shape | κ.1 — multi-person assistant-turn extraction with per-participant attribution | Kuzu schema unchanged (κ.2 is D-B's lane); κ.3 is stopgap, rejected |
| D3 | Trigger for κ extraction | Multi-person rooms only (`len(_active_room_participants) >= 2`) AND assistant turn AND content length ≥ 80 chars | Single-person assistant turns continue to be skipped per existing TriageAgent |
| D4 | Multi-target attribution shape | Per-participant fact emission; one fact per pid; no JSON-array participant lists | Preserves entity-attribute-value schema |
| D5 | Min-chars threshold | `ASSISTANT_TURN_EXTRACT_MIN_CHARS = 80` | Auditor approved; ~15-20 words; filters acknowledgments + KAIROS check-ins |
| D6 | Privacy tier per fact-shape | **REVISED per auditor precision item 1**: BOTH subject-of-fact AND witness-of-fact default to `personal`. Best_friend retrieves via cross-person owner override (P0.S7 P1). Visitor retrieves own facts on return. `household` reserved for true household-shared facts (S95 3A.4.6 simplified model). |
| D7 | Existing test impact | TriageAgent's single-person assistant-turn skip behavior unchanged; new code path for multi-person | Existing test must be scoped explicitly to single-person context |
| D8 | Test coverage | 7 logical tests across γ + κ + integration | See §6 |
| **L1** (precision item 2) | LLM call shape | **(c) — one LLM call returns topic-level structured data + mechanical fan-out per participant**. Avoids N× cost multiplier AND prompt-complexity risk of multi-target output. |
| **L2** (precision item 3) | Phase 3 integration test assertion | **Tightened to ONE primary + ONE mechanism assertion (both must pass)**: primary = response does NOT match denial regex; mechanism = `search_memory` tool was called via mock spy. No 3-way OR. |
| **L3** (precision item 4) | Phase ordering dependency | **Documented explicitly**: γ alone (Phase 1 closure) does NOT fix the canary failure mode — brain calls search_memory but gets nothing useful because κ (Phase 2) hasn't landed yet. Phase 3 integration test gates on BOTH parts landing. |

---

## 2. Architectural overview

Two-part fix; both load-bearing. Neither part alone closes the canary failure.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Part γ — Prompt-side honesty discipline (Phase 1)                         │
│  Extend <<<HONESTY POLICY>>> block in core/brain.py::_build_system_prompt  │
│  with a new bullet: "If user references something you don't remember,      │
│  call search_memory BEFORE denying. Self-referential denial without        │
│  retrieval is a hard correctness failure."                                 │
└──────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼ (brain's RESPONSE behavior shifts)
┌──────────────────────────────────────────────────────────────────────────┐
│  Part κ — Multi-person assistant-turn extraction (Phase 2)                 │
│                                                                            │
│  TriageAgent (core/brain_agent.py:3812)                                    │
│    New branch: role=='assistant' AND multi_person_room AND len≥80         │
│      → return (True, "multi_person_assistant_turn")                        │
│                                                                            │
│  ExtractionAgent (core/brain_agent.py:4078)                                │
│    New method extract_assistant_room_turn(content, participants)           │
│      → ONE LLM call returns:                                               │
│         { topic, action_type, primary_subject_name|null, key_details }    │
│      → mechanical fan-out per participant:                                 │
│         primary_subject: `<name>.received_<action_type>='<topic+details>'`│
│         witnesses:        `<name>.witnessed_<action_type>='<topic to_<subj>>'`│
│      → all facts privacy_level='personal' (D6 revised)                    │
│                                                                            │
│  Result: each participant's brain.db carries a fact about what            │
│  happened in the room. `search_memory` retrieval surfaces it on next      │
│  session.                                                                  │
└──────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Phase 3 — Integration test (canary as regression)                         │
│  Replay Session A (multi-person, recipe shared) → Session B (Jagan alone,  │
│  asks about recipe). Assert: (a) brain did NOT match denial regex;        │
│  (b) search_memory tool was called (mock spy).                             │
└──────────────────────────────────────────────────────────────────────────┘
```

**Critical dependency (L3)**: Part γ tells brain to call `search_memory`, but Part κ creates the facts that make `search_memory` return useful results. Phase 1 alone gets brain into the right behavioral mode but doesn't fix the underlying gap. Phase 3 integration test must run AFTER Phase 2.

---

## 3. Part γ — Prompt-side honesty discipline (Phase 1)

### 3.1 Landing site

`core/brain.py::_build_system_prompt` — within the existing `<<<HONESTY POLICY>>>` block (added in S68 Bug N).

### 3.2 Bullet text (locked)

Append the following bullet to the existing block:

```
- MEMORY HONESTY DISCIPLINE: If the user references something you said or did
  that you don't currently see in your context, you MUST call search_memory
  BEFORE denying. NEVER respond with "I didn't actually..." or "I don't think
  I..." or similar self-denial phrasings for a user's reference to a past
  exchange WITHOUT first attempting retrieval via search_memory. False denial
  of your own prior actions is a hard correctness failure — it makes the
  system untrustworthy. When search_memory returns nothing matching, you may
  hedge ("I don't have clear notes on that — can you remind me?") but you MUST
  NOT confidently deny.
```

### 3.3 Gating

The block already has `HONESTY_POLICY_BLOCK_ENABLED` flag (S68 Bug N). New bullet inherits this gating. No new config flag.

### 3.4 What γ does NOT fix

- Brain's training-default behavior on self-denial may still partially leak; the prompt instruction is mitigation, not elimination.
- If search_memory returns nothing useful (because Part κ hasn't run yet), brain may still hedge into denial after the retrieval attempt. Phase 1 closure is the prompt-discipline lock-in; canary failure mode is fully fixed only after Phase 2.

---

## 4. Part κ — Multi-person assistant-turn extraction (Phase 2)

### 4.1 TriageAgent extension

`core/brain_agent.py::TriageAgent.should_process` currently returns `(False, "assistant turn")` unconditionally for any `role=='assistant'` (line 3820).

**Plan v1 lock:** add a multi-person branch BEFORE the existing assistant-skip:

```python
def should_process(
    self,
    role: str,
    content: str,
    prior_assistant_turn: str | None = None,
    *,
    room_participant_count: int = 1,  # NEW kwarg
) -> tuple[bool, str]:
    if role == "assistant":
        # P0.S7.2 — multi-person room assistant turns carry topic-bearing
        # content that participants need in their knowledge graphs for
        # cross-session retrieval. Skip threshold via min-chars guard (D5).
        if (
            room_participant_count >= 2
            and len(content or "") >= ASSISTANT_TURN_EXTRACT_MIN_CHARS
        ):
            return True, "multi_person_assistant_turn"
        return False, "assistant turn"
    # ... rest of existing logic ...
```

Backward-compat: existing callers passing `role`, `content`, `prior_assistant_turn` continue to work (kwarg default = 1, single-person semantics preserved).

**Caller update:** `BrainOrchestrator._process_turn` (`core/brain_agent.py:7063`) passes the new kwarg:

```python
# Resolve room participant count at turn time
room_participant_count = self._get_room_participant_count(ts)
ok, reason = self._triage.should_process(
    role, content,
    prior_assistant_turn=prior_assistant,
    room_participant_count=room_participant_count,
)
```

New helper `BrainOrchestrator._get_room_participant_count(turn_ts) -> int` queries the room snapshot at turn time. Implementation: read `_pipeline_state_store.peek_active_room_participants()` if turn happened within the current room window; else fall back to `conversation_log` audience_ids JSON parse for the historical turn's room.

### 4.2 ExtractionAgent extension (the L1 LLM-call shape)

New method on `ExtractionAgent`:

```python
async def extract_assistant_room_turn(
    self,
    assistant_content: str,
    participant_names: list[str],
    participant_pids: list[str],
) -> list[Extraction]:
    """P0.S7.2 — multi-person assistant-turn extraction via ONE LLM call
    + mechanical fan-out per participant (L1 option c).

    Returns a list of Extraction objects, one per participant, all with
    privacy_level='personal' (D6 revised per auditor precision item 1).
    """
```

**LLM call shape (locked L1.c):** one LLM call returning topic-level structured data; code does the per-participant fan-out.

System prompt (new constant `_ASSISTANT_ROOM_EXTRACT_SYSTEM` in `core/brain_agent.py`):

```
You analyze a single assistant turn that occurred during a multi-person
conversation. Extract structured information about what was discussed.

Output STRICT JSON:
{
  "topic": "<concise topic phrase, ≤60 chars, e.g., 'cheese cookies recipe'>",
  "action_type": "<one of: shared_information | answered_question |
                   made_suggestion | engaged_general_discussion>",
  "primary_subject_name": "<participant name the assistant primarily
                            addressed, or null if room-general>",
  "key_details": "<≤80 chars of distinctive content; null if action_type is
                   engaged_general_discussion or content is non-substantive>"
}

If the assistant turn is non-substantive (acknowledgment, filler, KAIROS
check-in), output {"topic": null}. Do NOT extract anything.

Participants in the room: [list of names]
```

User message: the assistant turn content (truncated to 1500 chars if longer).

LLM call uses the existing `_call_llm_chat` helper (S69) — JSON-response-format mode, 5s timeout, max_tokens 250.

**Mechanical fan-out** (deterministic post-LLM code):

```python
def _fan_out_to_participants(
    extracted: dict,
    participant_names: list[str],
    participant_pids: list[str],
) -> list[Extraction]:
    if not extracted or not extracted.get("topic"):
        return []  # non-substantive turn, no facts

    topic = extracted["topic"]
    action_type = extracted.get("action_type") or "engaged_general_discussion"
    primary_subject_name = extracted.get("primary_subject_name")
    key_details = extracted.get("key_details") or ""

    # Compose fact-value strings
    if primary_subject_name and primary_subject_name in participant_names:
        primary_value = f"{topic}" if not key_details else f"{topic}: {key_details}"
        witness_value = f"{topic} to_{primary_subject_name}"
    else:
        primary_subject_name = None
        primary_value = None
        witness_value = topic if not key_details else f"{topic}: {key_details}"

    facts: list[Extraction] = []
    for name, pid in zip(participant_names, participant_pids):
        if name == primary_subject_name:
            attr = f"received_{action_type}"
            value = primary_value
        else:
            attr = f"witnessed_{action_type}"
            value = witness_value
        facts.append(Extraction(
            entity=name,
            attribute=attr,
            value=value,
            confidence=0.85,
            person_id=pid,
            privacy_level="personal",  # D6 revised
        ))
    return facts
```

**Why option (c) wins** (per auditor precision item 2 + architect implementation reading):
- Single LLM call regardless of participant count (no N× cost multiplier)
- Mechanical fan-out is deterministic + cheap (~microseconds)
- LLM output schema is bounded + simple (4 fields, no nested arrays)
- Easy to test in isolation: stub the LLM call's JSON output, verify fan-out produces the right Extraction objects

### 4.3 Wiring into `_process_turn`

`BrainOrchestrator._process_turn` currently flows: triage → extraction → contradiction-check → storage. Phase 2 adds the multi-person assistant-turn path:

```python
# After triage returns (True, "multi_person_assistant_turn")
participants = self._get_room_participants(ts)  # returns (names, pids)
extractions = await self._extraction_agent.extract_assistant_room_turn(
    assistant_content=content,
    participant_names=participants["names"],
    participant_pids=participants["pids"],
)
# Existing storage path handles the rest (contradiction check, brain.db
# write, Kuzu rebuild via existing add_to_graph hook).
```

No new storage code path. Existing `store_knowledge` accepts the per-participant Extraction list. Kuzu graph rebuild via existing `_persist_extraction_to_kuzu` flow (SWALLOW pattern per P0.X).

### 4.4 What κ does NOT do (explicit non-claims)

- **Does NOT add new Kuzu node/edge types.** Kuzu schema unchanged (κ.2 was rejected in Phase 0). Per-participant facts land as standard `<Entity>-[RELATES_TO {attribute, value}]->...` edges via existing Kuzu rebuild path.
- **Does NOT change extraction for single-person assistant turns.** Brain self-talk to a single user still skipped per existing triage. (Why: single-person assistant turns are typically the brain's response to the user; the response content carries facts about the user that are already extracted from the user's preceding turn. Re-extracting from the assistant turn would double-count.)
- **Does NOT extract facts about the brain itself.** Entity is always a participant (real person). Brain's own role in the conversation is implicit in the `received_*` / `witnessed_*` attribute names.
- **Does NOT handle disputed-session callers.** If a participant has identity disputed (S91 + S73), they're skipped from the fan-out (gate at the per-participant emission loop).

---

## 5. Privacy tier — D6 revised (auditor precision item 1)

Both subject-of-fact (`received_*`) AND witness-of-fact (`witnessed_*`) default to **`personal`** tier.

**Why personal (auditor's (α) lean, locked):**

| Tier | Visibility | Outcome for canary scenario |
|---|---|---|
| **personal** (LOCKED) | Owner of the entity sees their own; best_friend sees all via owner override (P0.S7 P1) | Jagan retrieves `Jagan.witnessed_shared_information='cheese cookies to_Lexi'` via owner override + retrieves own `witnessed_*` facts ✓. Lexi on return retrieves `Lexi.received_shared_information='cheese cookies: butter, sugar...'` via owner-of-own-facts ✓. |
| household (rejected) | Best_friend only (per S95 3A.4.6) | Lexi locked OUT of her own received_* fact on return ✗. Asymmetric. |
| public (rejected) | Universal | Over-discloses — random visitor could see Jagan/Lexi's multi-person room facts. |
| system_only (rejected) | Never disclosed | Defeats the purpose. |

**Implementation:** Extraction object's `privacy_level="personal"` hard-coded in the fan-out helper (§4.2). Phase 2 unit test verifies all emitted facts carry personal.

---

## 6. Test specification (Plan v1 — 7 logical tests, with auditor's L2 tightening)

### Phase 1 tests (γ — prompt-side discipline)

1. **`test_honesty_policy_block_contains_memory_denial_bullet`** — source-inspection: assert `<<<HONESTY POLICY>>>` block in `core/brain.py::_build_system_prompt` contains a bullet matching `r"MEMORY HONESTY DISCIPLINE"` AND `r"search_memory.*BEFORE.*denying"`. Pure structural check.
2. **`test_honesty_policy_block_present_for_known_speakers`** — behavioral: build a prompt for a `best_friend` speaker; assert the block (including new bullet) is in the rendered prompt. Mirrors existing S68 test shape.

### Phase 2 tests (κ — extraction extension)

3. **`test_triage_admits_multi_person_assistant_turn`** — `TriageAgent.should_process(role='assistant', content=<≥80 chars>, room_participant_count=2)` → `(True, 'multi_person_assistant_turn')`. Parametrize over participant_count ∈ {2, 3, 4}.
4. **`test_triage_skips_single_person_assistant_turn`** — `room_participant_count=1` → `(False, 'assistant turn')`. Existing behavior preserved.
5. **`test_triage_skips_short_multi_person_assistant_turn`** — `room_participant_count=2`, content=`"Got it!"` (7 chars) → `(False, 'assistant turn')`. D5 min-chars guard verified.
6. **`test_extract_assistant_room_turn_fan_out_per_participant`** — stub `_call_llm_chat` to return:
   ```json
   {"topic": "cheese cookies recipe",
    "action_type": "shared_information",
    "primary_subject_name": "Lexi",
    "key_details": "butter, sugar, eggs, flour"}
   ```
   Call `extract_assistant_room_turn(content="<assistant turn>", participant_names=["Jagan", "Lexi"], participant_pids=["j_001", "l_002"])`.
   Assert 2 Extraction objects emitted:
   - `Extraction(entity="Lexi", attribute="received_shared_information", value="cheese cookies recipe: butter, sugar, eggs, flour", privacy_level="personal", person_id="l_002")`
   - `Extraction(entity="Jagan", attribute="witnessed_shared_information", value="cheese cookies recipe to_Lexi", privacy_level="personal", person_id="j_001")`
   Parametrize over (a) primary_subject_name set, (b) primary_subject_name null (all witness fan-out), (c) participant count 3.

### Phase 3 test (integration — canary as regression)

7. **`test_session_a_then_b_recipe_retrieval`** (with L2-tightened assertions) — fixture replay:
   - **Session A setup**: simulate multi-person room (Jagan + Lexi); use scenario fixture from `tests/fixtures/event_log_fixtures.py` (S107 D7.4 reusable). Inject a real Session A assistant turn `"To make cheese cookies, you'll need butter, sugar, eggs, flour, and cheese - I can try to walk you through a basic recipe if you'd like."` (the exact Session A line 197 content from `terminal_output_2026-05-18_205920.md`). Run through `BrainOrchestrator._process_turn` with multi-person branch. Verify 2 facts written to brain.db.
   - **Session B replay**: Jagan-only session opens. Jagan turn: `"the cookies came out so good and thanks for your recipe"` (Session B line 76). Drive the conversation_turn flow up to the brain's response generation. Mock the LLM streaming response.
   - **Primary assertion (L2)**: brain response does NOT match `r"(?i)I (?:didn't|do not have|don't (?:think I )?(?:give|share|suggest)|did not (?:give|share|suggest))"` denial regex.
   - **Mechanism assertion (L2)**: `search_memory` tool was called via spy (MagicMock.assert_called()).
   - **Both must pass** — no 3-way OR.

### Phase 4 (deliberate-regression confirmations — closure-report items)

- Inject `(False, "assistant turn")` short-circuit in the multi-person branch → test 3 fails → revert.
- Drop the per-participant loop in fan-out → test 6 fails → revert.
- Strip the new bullet from `<<<HONESTY POLICY>>>` → test 1 fails → revert.

**Net new tests: 7 logical.** Parametrize fan-out increases collected count: test 3 ×3 + test 6 ×3 + others ×1 = ~11 collected. Suite delta forecast: 2349 → ~2360 (assuming P0.S7.3 ships first delivering +3).

---

## 7. Implementation phases (with L3 dependency note)

### Phase 1 — Part γ landing (+2 tests, ~quarter-day)

- Extend `<<<HONESTY POLICY>>>` block in `core/brain.py::_build_system_prompt` with the new bullet (§3.2 exact text).
- Tests 1 + 2 from §6.
- **Suite checkpoint:** 2349 → 2351 (+2).

**Closure expectation (L3 dependency note):** Phase 1 closure delivers the brain's behavioral intent ("call search_memory before denying") but does NOT fix the canary failure mode. Without Phase 2's per-participant facts in the DB, search_memory returns nothing useful and brain still hedges or denies. **This is intentional intermediate state.** The full canary fix is gated on Phase 2 + Phase 3.

### Phase 2 — Part κ extraction extension (+4 tests, ~full day)

- TriageAgent kwarg + multi-person branch (§4.1).
- BrainOrchestrator `_get_room_participant_count` helper + `_get_room_participants` helper.
- ExtractionAgent `extract_assistant_room_turn` method (§4.2).
- Mechanical fan-out helper `_fan_out_to_participants`.
- `_ASSISTANT_ROOM_EXTRACT_SYSTEM` prompt constant + new config `ASSISTANT_TURN_EXTRACT_MIN_CHARS=80`.
- Wiring in `_process_turn` (§4.3).
- Tests 3, 4, 5, 6 from §6.
- **Suite checkpoint:** 2351 → 2355 (+4).

### Phase 3 — Integration test (+1 test, ~quarter-day)

- Fixture builder for Session A → Session B replay (reuse `event_log_fixtures.py` shape).
- Test 7 with L2-tightened dual-assertion shape.
- **Suite checkpoint:** 2355 → 2356 (+1).

### Phase 4 — Deliberate-regression confirmations + closure (+0 tests, ~quarter-day)

- 3 deliberate-regression confirmations per §6 Phase 4 list.
- Closure-report banking (see §10).

**Total effort:** ~2 dev-days. **Net new tests: 7 logical / ~11 collected. Suite delta: 2349 → ~2356.**

---

## 8. Configuration additions (`core/config.py`)

```python
# P0.S7.2 — Multi-person assistant-turn extraction (Plan v1 §4)
# Minimum content length for assistant turn to enter extraction in multi-person
# rooms. Filters acknowledgments + KAIROS check-ins. ~15-20 words.
ASSISTANT_TURN_EXTRACT_MIN_CHARS: int = 80
```

No new flag; the multi-person assistant-turn extraction is unconditional once triage admits it (D3 + L3). If a future rollback need emerges, add `MULTI_PERSON_ASSISTANT_EXTRACTION_ENABLED` flag in Plan v2 — flag-gating not in scope for Plan v1.

---

## 9. Validation gate

1. All 7 new tests green; full-suite green at ~2356 (assumes P0.S7.3 already shipped at ~2349).
2. 3/3 deliberate-regression confirmations pass (induction protocol).
3. Phase 3 integration test fires both assertions (primary + mechanism) on the canary scenario.
4. Closure narrative banks: 2 informational observations from auditor (A + B), Phase 1 → Phase 2 dependency explicit, D6 revision rationale.

---

## 10. Discipline-count predictions (auditor's strict-read locked)

- **Spec-first review cycle: 9-for-9 → 10-for-10** on closure (P0.S7.2 added).
- **Sub-pattern A: stays at 4 instances.** P0.S7.2 is the predicted follow-up to P0.S7's explicit scope deferral, NOT a new wrong-premise catch.
- **Induction-surfaces-invariant-gaps: stays 7-for-7** per auditor's strict-read adjudication. Canary findings are a production-observation mechanism, distinct from deliberate-regression-of-structural-invariant. If canary discipline accumulates 5+ instances, may surface as a separate `### Canary-surfaces-real-gaps` doctrine in the future (currently 2 instances banked: P0.S7.2 cross-session retrieval + P0.S7.3 KAIROS timing).
- **Tripwires-must-match-deferral-surface: stays 4-for-4.**
- **Developer-improves-on-spec: stays 6-for-6** unless code phase surfaces a mechanism improvement (the L1.c option (one LLM call + mechanical fan-out) is auditor-prescribed, not developer-discovered; doesn't count unless implementation reveals additional refinement).

---

## 11. Open items / risks

1. **Token-budget impact** — multi-person rooms now extract for BOTH the user turn AND the assistant turn. Roughly 2× extraction LLM-call cost in multi-person scenarios. The D5 min-chars guard (80 chars) filters short turns; expect ~80% of multi-person assistant turns to qualify (substantive responses). Estimate: ~10-20 extra extractions per hour of multi-person conversation. Tolerable; revisit if production shows >50% cost increase.

2. **Cross-session fact retrieval still requires search_memory call from brain** — γ tells brain to call it; if LLM compliance is weaker than expected, gap re-opens. Phase 3 mechanism assertion catches this structurally in CI; real-production behavior measured via re-canary.

3. **Disputed-session interaction** — if a participant is identity-disputed at turn time, their `received_*` / `witnessed_*` fact must NOT be emitted (would pollute the disputed-id's knowledge graph). Fan-out helper queries `BrainOrchestrator._disputed_persons` (S91) and skips disputed pids. Test 6 sub-case may add this if Plan v2 surfaces it; defer to Phase 2 implementation.

4. **`_get_room_participants` for historical turns** — Phase 2 BrainOrchestrator helper needs to resolve participant names+pids at the time of the turn. For current-turn extraction, use `_pipeline_state_store.peek_active_room_participants()`. For replay/historical extraction, parse `audience_ids` JSON from `conversation_log`. Implementation surfaces a Plan v2 precision item if architectural surface differs from current expectation.

5. **Attribute-namespace collision** — `received_*` and `witnessed_*` are new attribute prefixes. Verify no existing brain.db rows use these patterns. Grep at Phase 2 implementation; if collisions exist, append `_room_` prefix (e.g., `received_room_shared_information`) for disambiguation. Low risk per current attribute conventions.

6. **Plan v1 → Plan v2 likely needs revision** — this is a multi-architectural-decision spec; auditor precision items will likely surface for the LLM-output schema details, the disputed-skip integration, and possibly the attribute-namespace question. Plan v2 incorporates auditor feedback before code phase.

---

## 12. References

- `tests/p0_s7_2_spec.md` — Phase 0 spec (premise + audit verdict + 4 precision items + 2 informational observations)
- `tests/p0_s7_audit.md` — Phase 0 audit of P0.S7 itself (D-A first-slice framing; explicitly scoped out cross-session)
- `tests/p0_s7_plan_v2.md` — P0.S7 D-A Plan v2 (the parent spec; cross-session scope deferred)
- `tests/p0_s7_3_spec.md` — P0.S7.3 KAIROS sibling fix (auditor observation B: bank both fixes against same canary observation)
- **`c:\Users\jagan\dog-ai\dog-ai\terminal_output_2026-05-18_205920.md`** — Session A log (multi-person, recipe shared). Key lines: 173 (Lexi's question), 197 (brain's recipe share), 228 + 250 + 253 (follow-up turns), 296 (visitor alert).
- **`c:\Users\jagan\dog-ai\dog-ai\terminal_output.md`** — Session B log (Jagan returns alone, brain denies). Key lines: 76 (Jagan's recipe reference), 93 + 143 + 195 (three denial responses), 82 (SharedContext gate=single_person confirming P0.S7 didn't render).
- `core/brain.py::_build_system_prompt` — Part γ landing site
- `core/brain_agent.py:3812-3820` — TriageAgent.should_process (Part κ entry)
- `core/brain_agent.py:4078` — ExtractionAgent.extract (Part κ sibling)
- `core/brain_agent.py:7063` — BrainOrchestrator._process_turn (wiring)
- `tests/fixtures/event_log_fixtures.py` — Phase 3 integration fixture reuse target (S107 D7.4)
- `tests/p0_s7_plan_v2.md` §1 — P0.S7 owner-override privacy rule (P1) — basis for D6's "best_friend sees everything via cross-person override" claim

---

## 13. Next steps

1. **Auditor reviews Plan v1.** Specifically: (a) `_ASSISTANT_ROOM_EXTRACT_SYSTEM` prompt design — anything missing?; (b) LLM-output JSON schema 4 fields — sufficient?; (c) attribute-name composition (`received_<action_type>` / `witnessed_<action_type>`) — convention-aligned?; (d) §11 risks — anything missed?
2. **Plan v2** drafted if precision items surface (likely 3-5 items given architectural-extension scope).
3. **Joint sign-off → developer handoff** for 4-phase implementation.
4. **After Phase 4 closure**: re-canary with same Session A → Session B scenario. Expected: brain calls search_memory and surfaces cheese-cookies recipe correctly without denial.
