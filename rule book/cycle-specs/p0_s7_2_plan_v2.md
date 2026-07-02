# P0.S7.2 — Cross-Session Memory Retrieval Gap — Plan v2

**Date:** 2026-05-18
**Author:** architect
**Status:** Plan v2 — drafted against locked D1-D8 + L1-L3 (Plan v1) + auditor's 5 precision items from Plan v1 review (4 MEDIUM + 1 LOW). Plan v1 retained at `tests/p0_s7_2_plan_v1.md` for delta visibility. Standing by for auditor's Plan v2 verdict → joint sign-off → developer handoff.

**Phase 0 spec:** `tests/p0_s7_2_spec.md` (premise, audit verdict).
**Phase 0 D-lock:** auditor verdict on `tests/p0_s7_2_spec.md` (D1-D8 + 4 precision items).
**Plan v1:** `tests/p0_s7_2_plan_v1.md` (D-lock + 4 precision items incorporated).

**Delta from Plan v1 (5 precision items):**
- **Precision 1 (MEDIUM)** — action_type enum gap: add `asked_question` as 5th type. Brain-asks-question turns are common; previously fell into `engaged_general_discussion` and lost semantic precision.
- **Precision 2 (MEDIUM)** — `primary_subject_name` semantic ambiguity locked at **(ii) addressee** with explicit counter-example added to extraction prompt.
- **Precision 3 (MEDIUM)** — disputed-skip code shown explicitly in fan-out helper (`§4.2`); test 6 gains a parametrize case for `disputed_pid_present`.
- **Precision 4 (MEDIUM)** — Phase 3 fixture: dedicated NEW builder `build_multi_person_assistant_extraction(...)` in `tests/fixtures/event_log_fixtures.py` (auditor's option (a)) rather than reusing chain 3.
- **Precision 5 (LOW)** — Phase 3 test scope clarification: WIRING verification only; real-LLM compliance via re-canary post-closure. Documented in §9 validation gate.

Locked D-decisions and Plan v1 contract clauses unchanged except where explicit revision noted below.

---

## 1. Locked decision reference (Plan v1 unchanged unless noted)

| ID | Locked at | Plan v2 delta |
|---|---|---|
| D1 | γ.1 — extend `<<<HONESTY POLICY>>>` block | — |
| D2 | κ.1 — multi-person assistant-turn extraction with per-participant attribution | — |
| D3 | Multi-person rooms only; assistant role; content ≥ 80 chars | — |
| D4 | Per-participant fact emission; no JSON-array participant lists | — |
| D5 | `ASSISTANT_TURN_EXTRACT_MIN_CHARS = 80` | — |
| D6 | personal tier for BOTH subject-of-fact + witness-of-fact | — |
| D7 | TriageAgent single-person assistant-turn skip preserved | — |
| D8 | 7 logical tests across γ + κ + integration | Plan v2 §6 + 1 parametrize case = 8 logical (still ~11-12 collected) |
| L1 | (c) — one LLM call + mechanical fan-out | **Action_type enum expanded** (precision item 1); semantic of `primary_subject_name` clarified (precision item 2) |
| L2 | Phase 3 PRIMARY + MECHANISM dual assertion | — |
| L3 | γ ⇄ κ phase-ordering dependency documented | — |
| **P1** (precision item 1) | Action_type enum = 5 types | NEW: `{shared_information, answered_question, asked_question, made_suggestion, engaged_general_discussion}` |
| **P2** (precision item 2) | `primary_subject_name` = addressee (not topic-subject) | NEW: explicit counter-example added to extraction prompt; topic-subjects who are participants get `witnessed_*` facts |
| **P3** (precision item 3) | Disputed-skip code shown explicitly in fan-out helper | NEW: §4.2 helper code + test 6 parametrize case |
| **P4** (precision item 4) | Phase 3 fixture = dedicated NEW builder | NEW: `build_multi_person_assistant_extraction()` in `tests/fixtures/event_log_fixtures.py` |
| **P5** (precision item 5) | Phase 3 verifies WIRING only | Validation gate §9 + closure-narrative requirement: bank post-closure re-canary results as the real-LLM behavior signal |

---

## 2. Architectural overview (unchanged from Plan v1 §2; included for context)

Two-part fix; both load-bearing. Neither part alone closes the canary failure.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Part γ — Prompt-side honesty discipline (Phase 1)                         │
│  Extend <<<HONESTY POLICY>>> block with: "If user references something     │
│  you don't remember, call search_memory BEFORE denying. Self-referential   │
│  denial without retrieval is a hard correctness failure."                  │
└──────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Part κ — Multi-person assistant-turn extraction (Phase 2)                 │
│  TriageAgent: new branch for multi-person + ≥80-char assistant turns       │
│  ExtractionAgent: ONE LLM call (5 action types per P1)                     │
│    + mechanical fan-out per participant (P2 addressee semantic)            │
│    + disputed-skip gate (P3)                                               │
│    + privacy_level='personal' (D6)                                         │
└──────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Phase 3 — Integration WIRING test (canary as regression)                  │
│  Replay Session A → Session B via NEW fixture builder (P4)                 │
│  Dual assertion: PRIMARY denial-regex + MECHANISM search_memory spy (L2)   │
│  WIRING ONLY; real-LLM behavior verified via post-closure re-canary (P5)   │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Part γ — Prompt-side honesty discipline (Phase 1)

§3 unchanged from Plan v1. Bullet text + landing site + gating identical.

---

## 4. Part κ — Multi-person assistant-turn extraction (Phase 2)

### 4.1 TriageAgent extension

Unchanged from Plan v1 §4.1. New kwarg `room_participant_count: int = 1` on `should_process`; multi-person + ≥80-char branch returns `(True, "multi_person_assistant_turn")`.

### 4.2 ExtractionAgent extension — REVISED for P1 + P2 + P3

**System prompt (`_ASSISTANT_ROOM_EXTRACT_SYSTEM`) — Plan v2 locked text:**

```
You analyze a single assistant turn that occurred during a multi-person
conversation. Extract structured information about what was discussed.

Output STRICT JSON:
{
  "topic": "<concise topic phrase, ≤60 chars, e.g., 'cheese cookies recipe'>",
  "action_type": "<one of: shared_information | answered_question |
                   asked_question | made_suggestion |
                   engaged_general_discussion>",
  "primary_subject_name": "<participant name the assistant ADDRESSED (NOT
                            the topic-subject); see counter-example below>",
  "key_details": "<≤80 chars of distinctive content; null if action_type is
                   engaged_general_discussion or content is non-substantive>"
}

PRIMARY_SUBJECT_NAME SEMANTIC: the participant the assistant SPOKE TO, not
the participant they spoke ABOUT.

Counter-example: assistant says "Jagan, Lexi mentioned earlier she likes
cooking" — primary_subject_name = "Jagan" (addressee), NOT "Lexi" (topic).
Lexi appears in topic content; she's covered separately by the system as
a witness in the room.

ACTION_TYPE GUIDANCE:
- shared_information: assistant offers facts/recipe/instructions/explanation
- answered_question: assistant directly responds to a participant's question
- asked_question: assistant probes for info (e.g., "Lexi, what's the deadline?")
- made_suggestion: assistant proposes an action/option
- engaged_general_discussion: catch-all for substantive turns that don't fit
  the 4 above; topic + key_details should still be extracted

If the assistant turn is non-substantive (acknowledgment, filler, KAIROS
check-in), output {"topic": null}. Do NOT extract anything.

Participants in the room: [list of names]
```

User message: the assistant turn content (truncated to 1500 chars if longer).

LLM call via existing `_call_llm_chat` helper (S69); JSON-response-format mode; 5s timeout; max_tokens 250.

**Mechanical fan-out helper (Plan v2 locked code with P3 disputed-skip):**

```python
def _fan_out_to_participants(
    extracted: dict,
    participant_names: list[str],
    participant_pids: list[str],
    disputed_pids: "set[str]",  # P3 — set from orchestrator._disputed_persons
) -> list[Extraction]:
    """P0.S7.2 Plan v2 — fan-out helper.

    Emits per-participant Extraction objects from the topic-level LLM extraction.
    Skips disputed pids (P3) — pollution into a disputed-id knowledge graph
    would be a correctness failure (S91 / S73).

    primary_subject_name semantic = ADDRESSEE (P2). Topic-subjects who happen
    to be participants get witnessed_* facts. Topic-subjects who are NOT
    participants do not appear in the fan-out at all (their data isn't being
    written to anyone's graph by this path).
    """
    if not extracted or not extracted.get("topic"):
        return []  # non-substantive turn — no facts

    topic = extracted["topic"]
    action_type = extracted.get("action_type") or "engaged_general_discussion"
    primary_subject_name = extracted.get("primary_subject_name")  # ADDRESSEE per P2
    key_details = extracted.get("key_details") or ""

    # Compose value strings
    if primary_subject_name and primary_subject_name in participant_names:
        primary_value = f"{topic}" if not key_details else f"{topic}: {key_details}"
        witness_value = f"{topic} to_{primary_subject_name}"
    else:
        # Primary subject not a participant (or null) — all participants are witnesses
        primary_subject_name = None
        primary_value = None
        witness_value = topic if not key_details else f"{topic}: {key_details}"

    facts: list[Extraction] = []
    for name, pid in zip(participant_names, participant_pids):
        # P3 — disputed-skip gate. Don't pollute disputed-id knowledge graph.
        if pid in disputed_pids:
            continue
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
            privacy_level="personal",  # D6
        ))
    return facts
```

**ExtractionAgent method signature (Plan v2 locked):**

```python
async def extract_assistant_room_turn(
    self,
    assistant_content: str,
    participant_names: list[str],
    participant_pids: list[str],
    disputed_pids: "set[str] | None" = None,  # P3 — default empty if not supplied
) -> list[Extraction]:
    """P0.S7.2 Plan v2 — multi-person assistant-turn extraction.

    ONE LLM call (L1.c) returning topic-level structured data + mechanical
    fan-out per participant (§4.2).

    Returns a list of Extraction objects, one per non-disputed participant,
    all with privacy_level='personal' (D6).
    """
    # 1. LLM call (one) — topic-level structured extraction
    response = await _call_llm_chat(
        self._http,
        messages=[
            {"role": "system", "content": _ASSISTANT_ROOM_EXTRACT_SYSTEM.format(
                participants=", ".join(participant_names)
            )},
            {"role": "user", "content": assistant_content[:1500]},
        ],
        agent_name="ExtractAssistantRoomTurn",
        response_format={"type": "json_object"},
        timeout=5.0,
        max_tokens=250,
    )
    if response is None:
        return []  # LLM failure — fail safe; no extractions
    extracted = _parse_json(response) or {}

    # 2. Mechanical fan-out per participant (P3 disputed-skip gated)
    return _fan_out_to_participants(
        extracted,
        participant_names,
        participant_pids,
        disputed_pids or set(),
    )
```

### 4.3 Wiring into `_process_turn`

Unchanged from Plan v1 §4.3, with one addition: caller passes `disputed_pids=self._disputed_persons` (the BrainOrchestrator's existing S91 set):

```python
extractions = await self._extraction_agent.extract_assistant_room_turn(
    assistant_content=content,
    participant_names=participants["names"],
    participant_pids=participants["pids"],
    disputed_pids=self._disputed_persons,  # P3
)
```

### 4.4 What κ does NOT do (unchanged from Plan v1 §4.4)

Identical non-claims preserved. P3 disputed-skip is now an explicit code gate (not just a non-claim).

---

## 5. Privacy tier (unchanged from Plan v1 §5)

D6 locked at `personal` for BOTH subject-of-fact AND witness-of-fact. Visitor returns later, retrieves own facts. Best_friend retrieves via cross-person owner override (P0.S7 P1). `household` reserved for true household-shared facts.

---

## 6. Test specification (Plan v2 — 8 logical tests with P3 + P4 + P5 revisions)

### Phase 1 tests (γ — prompt-side discipline) — unchanged

1. **`test_honesty_policy_block_contains_memory_denial_bullet`** — source-inspection
2. **`test_honesty_policy_block_present_for_known_speakers`** — behavioral

### Phase 2 tests (κ — extraction extension)

3. **`test_triage_admits_multi_person_assistant_turn`** — parametrize over participant_count ∈ {2, 3, 4}
4. **`test_triage_skips_single_person_assistant_turn`** — existing behavior preserved
5. **`test_triage_skips_short_multi_person_assistant_turn`** — D5 min-chars guard
6. **`test_extract_assistant_room_turn_fan_out_per_participant`** — REVISED parametrize per P1 + P3:
   - **6a**: action_type=`shared_information`, primary_subject_name set + is participant → 1 `received_*` + N-1 `witnessed_*` facts. Existing scenario.
   - **6b**: action_type=`asked_question` (P1 new enum), primary_subject_name="Lexi" → `Lexi.received_asked_question=...` + `Jagan.witnessed_asked_question=... to_Lexi`. Tests the new enum value.
   - **6c**: primary_subject_name=null (room-general) → ALL participants get `witnessed_*` facts; NO `received_*` fact.
   - **6d**: primary_subject_name="Jagan" but topic mentions Lexi (`"Jagan, Lexi mentioned earlier she likes cooking"`) — P2 addressee semantic test. Jagan.received_=..., Lexi.witnessed_=.... Lexi the topic-subject correctly gets witness fact (she's a participant), NOT received fact.
   - **6e** (NEW per P3): one of the participants is in `disputed_pids` set → that pid's Extraction is NOT emitted; remaining N-1 participants get their facts as normal.
   - **6f** (NEW per P1 enum coverage): action_type=`engaged_general_discussion` with no primary_subject → all participants get `witnessed_engaged_general_discussion=<topic>` facts.

### Phase 3 test (integration WIRING) — REVISED per P4 + P5

7. **`test_session_a_then_b_recipe_retrieval`** — uses NEW dedicated fixture builder (P4):

   **Fixture builder spec** (`tests/fixtures/event_log_fixtures.py`):

   ```python
   def build_multi_person_assistant_extraction(
       brain_orchestrator: "BrainOrchestrator",
       owner_name: str = "Jagan",
       owner_pid: str = "j_001",
       visitor_name: str = "Lexi",
       visitor_pid: str = "l_002",
       assistant_turn_content: str = (
           "To make cheese cookies, you'll need butter, sugar, eggs, "
           "flour, and cheese — I can try to walk you through a basic "
           "recipe if you'd like."
       ),
       extracted_facts_stub: "list[Extraction] | None" = None,
   ) -> dict:
       """P0.S7.2 Plan v2 P4 — fixture for Session A → Session B replay.

       Session A: opens a multi-person room with owner + visitor, fires
       a multi_person_assistant_turn extraction (real if extracted_facts_stub
       is None; else seeded directly into brain.db), ends session.

       Session B: opens fresh owner-only session; returns the
       conversation_turn flow's primed state ready for owner's "thanks for
       your recipe" turn.

       Returns: {
           'session_a_room_session_id': str,
           'extractions_stored': list[Extraction],
           'session_b_ready': bool,
       }
       """
   ```

   Test 7 calls this fixture; primes Session B; mocks brain's LLM streaming response to issue a `search_memory` tool call (the WIRING focus per P5).

   **Dual assertion (L2-tightened, unchanged from Plan v1):**

   - **Primary**: brain response does NOT match `r"(?i)I (?:didn't|do not have|don't (?:think I )?(?:give|share|suggest)|did not (?:give|share|suggest))"` denial regex.
   - **Mechanism**: `search_memory` tool was called via mock spy `assert_called()`.

   Both must pass — no 3-way OR.

   **P5 scope clarification (test docstring + Plan v2 §9):** this test verifies WIRING — given a mocked brain that issues a `search_memory` call AND the κ facts in place, the dispatch + retrieval path works end-to-end. Real-LLM compliance with the new γ bullet is validated via post-closure re-canary (out of CI scope).

### Phase 4 (deliberate-regression confirmations — closure items)

Unchanged from Plan v1; 3 induction probes confirmed during closure narrative.

**Net new tests: 8 logical** (Plan v1: 7; Plan v2 splits test 6 across 6 parametrize cases for P1 + P2 + P3 coverage). **~14 collected** (test 3 ×3 + test 6 ×6 + others ×1).

**Suite delta forecast: 2350 → ~2364** (assumes P0.S7.3 already shipped at 2350; reflects parametrize fan-out).

---

## 7. Implementation phases (Plan v2 — revised counts)

### Phase 1 — Part γ landing (+2 tests, ~quarter-day)

Unchanged from Plan v1 §7 Phase 1. Suite checkpoint: 2350 → 2352.

### Phase 2 — Part κ extraction extension (+4 logical / ~9 collected, ~full day)

Plan v2 deltas vs v1:
- `_ASSISTANT_ROOM_EXTRACT_SYSTEM` prompt locks 5-action-type enum (P1) + counter-example for `primary_subject_name` (P2).
- `_fan_out_to_participants` adds `disputed_pids` param + skip gate (P3).
- `extract_assistant_room_turn` method adds `disputed_pids` kwarg.
- Wiring in `_process_turn` passes `self._disputed_persons` as `disputed_pids`.
- Tests 3-6 from §6 (with 6 expanding to 6a-6f parametrize).

Suite checkpoint: 2352 → ~2361 (Plan v1 +4 logical, ~+9 collected reflecting test 6's 6-way parametrize).

### Phase 3 — Integration WIRING test (+1 test, ~quarter-day)

Plan v2 deltas vs v1:
- NEW fixture builder `build_multi_person_assistant_extraction` in `tests/fixtures/event_log_fixtures.py` (P4).
- Test 7 docstring includes P5 scope-framing language.
- Suite checkpoint: 2361 → 2362.

### Phase 4 — Deliberate-regression confirmations + closure (+0 tests, ~quarter-day)

3 induction probes + closure narrative.

**Additional closure narrative requirement (P5)**: bank the post-closure re-canary results (Session A → Session B real-LLM replay) as the empirical validation signal. If the re-canary shows brain still denies, file a follow-up to strengthen γ's prompt bullet.

**Total effort: ~2 dev-days.** Suite delta: 2350 → ~2362.

---

## 8. Configuration additions (unchanged from Plan v1 §8)

```python
ASSISTANT_TURN_EXTRACT_MIN_CHARS: int = 80
```

No new flag.

---

## 9. Validation gate (Plan v2 — P5 explicit)

1. All 8 new tests green (~14 collected); full-suite green at ~2362.
2. 3/3 deliberate-regression confirmations pass (induction protocol).
3. **Phase 3 verifies WIRING only** (per P5): given a mocked brain emitting `search_memory` call AND fan-out facts in place, the dispatch + retrieval path works end-to-end. **Real-LLM compliance with the new γ bullet is validated via post-closure re-canary.** Post-canary results bank into closure narrative — if brain still denies in real-LLM canary, file follow-up.
4. Closure narrative banks: 2 informational observations from Plan v1 auditor verdict (γ ⇄ κ dependency + P0.S7.3 sibling); 5 Plan v2 precision items resolved; D6 revision rationale.

---

## 10. Discipline-count predictions (strict-read confirmed by Plan v1 auditor verdict)

- **Spec-first review cycle: 9-for-9 → 10-for-10** on closure.
- **Sub-pattern A: stays at 4 instances** (predicted follow-up, not new wrong-premise).
- **Induction-surfaces-invariant-gaps: stays 7-for-7** (canary findings are a separate production-observation mechanism; auditor strict-read locked).
- **Tripwires-must-match-deferral-surface: stays 4-for-4.**
- **Developer-improves-on-spec: stays 6-for-6** unless code phase surfaces a mechanism improvement.

Canary-finding instances banked so far: **2** (P0.S7.2 cross-session retrieval + P0.S7.3 KAIROS timing). If accumulates to 5+, may surface as separate `### Canary-surfaces-real-gaps` doctrine in the future.

---

## 11. Open items / risks (Plan v2 additions)

Plan v1 §11 risks 1-6 preserved. Plan v2 additions:

7. **Action_type enum saturation** — 5 types covers most multi-person assistant turns but may miss edge cases (e.g., assistant offering a meta-comment about the room state). `engaged_general_discussion` catch-all absorbs these; if production shows >20% catch-all rate, Plan v3 may add a 6th type.

8. **P2 addressee semantic edge case — addressee not in participants list** — if assistant says "Jagan, ..." but Jagan's pid is not currently in `participant_pids` (e.g., he left the room mid-turn), the fan-out treats him as null primary_subject (per §4.2 `if primary_subject_name in participant_names` check). Resolves to all-witnesses semantic. Acceptable degradation.

9. **P4 fixture stability** — new fixture builder is the third pattern in `event_log_fixtures.py` (chain 1: greeting, chain 2: stranger first-encounter, chain 3: multi-person room, chain 4: dispute, chain 5 NEW: multi_person_assistant_extraction). Existing tests using chains 1-4 are unaffected; ensure chain 5 doesn't introduce shared-fixture state pollution into other test files.

10. **Post-closure re-canary discipline** — P5 frames this as the empirical signal but doesn't specify when it runs. **Plan v2 lock**: re-canary fires within 1 week of Phase 4 closure; results bank into the P0.S7.2 closure narrative as a closure-attestation gate (mirrors P0.S6's rotation-timestamp banking pattern). If re-canary fails (brain still denies), closure stays provisional pending γ prompt strengthening.

---

## 12. References (Plan v1 §12 preserved + P4 fixture additions)

- `tests/p0_s7_2_spec.md` — Phase 0 spec
- `tests/p0_s7_2_plan_v1.md` — Plan v1 (retained for delta visibility)
- `tests/p0_s7_audit.md` — Phase 0 audit of P0.S7
- `tests/p0_s7_plan_v2.md` — P0.S7 D-A Plan v2
- `tests/p0_s7_3_spec.md` — P0.S7.3 KAIROS sibling fix
- **`c:\Users\jagan\dog-ai\dog-ai\terminal_output_2026-05-18_205920.md`** — Session A log
- **`c:\Users\jagan\dog-ai\dog-ai\terminal_output.md`** — Session B log
- `core/brain.py::_build_system_prompt` — Part γ landing site
- `core/brain_agent.py:3812-3820` — TriageAgent.should_process (κ entry)
- `core/brain_agent.py:4078` — ExtractionAgent.extract (κ sibling)
- `core/brain_agent.py:7063` — BrainOrchestrator._process_turn (wiring)
- **`tests/fixtures/event_log_fixtures.py`** — P4 NEW `build_multi_person_assistant_extraction` builder target
- `tests/p0_s7_plan_v2.md` §1 — P0.S7 owner-override privacy rule (P1) — basis for D6's best_friend cross-person access

---

## 13. Next steps

1. **Auditor reviews Plan v2.** Specifically: (a) `asked_question` enum addition complete?; (b) P2 counter-example sufficient to disambiguate?; (c) P3 disputed-skip code shape clean?; (d) P4 fixture builder signature/contract; (e) P5 re-canary discipline within 1-week window — reasonable?
2. **Joint sign-off** on Plan v2 → user forwards to developer.
3. **Developer executes Phase 1-4** with full-suite verification between phases.
4. **Closure report** with 3/3 deliberate-regression confirmations + 5 Plan v2 precision items resolution + post-closure re-canary scheduled.
5. **Post-closure re-canary** (within 1 week per §11.10) — Session A → Session B real-LLM replay. Banks into closure narrative as empirical signal.
