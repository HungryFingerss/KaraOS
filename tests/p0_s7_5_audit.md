# P0.S7.5 — Bundled-queue canary follow-up — Phase 0 Audit

**Date:** 2026-05-19
**Author:** architect
**Status:** Phase 0 — grep-verified findings, zero production-code changes. **Bundled-queue canary FAILED 2026-05-19 with γ-related root cause cluster — this spec addresses the cluster, NOT just the γ surface.** Standing by for auditor review.

**Companion documents (forthcoming):**
- `tests/p0_s7_5_plan_v1.md` — after Phase 0 sign-off + D-decision lock
- `tests/p0_s7_5_plan_v2.md` — after Plan v1 review

**Disciplines applied at audit drafting:**
- **Two-pass grep-verification (Pass 1)**: all function/line/symbol references grep-verified 2026-05-19 against production code. Pass 2 fires at closure.
- **AST + behavioral workhorse pair** (3 instances, architect-memory): §6 test design preserves the discipline.
- **`### Phase-0-catches-wrong-premise` doctrine** (CLAUDE.md, elevated 2026-05-19 at D-D closure): explicit hypothesis-testing framing applied at §1.
- **Spec-time grep-verification** (4 instances, architect-memory): function/line refs grep-verified before lock.
- **Canary-finding tracker** (CLAUDE.md informal, 2 → 3 instances): P0.S7.2, P0.S7.3, **P0.S7.5 (new)**.

---

## 1. Canary failure summary + root-cause decomposition

### 1.1 Live canary 2026-05-19 (3 archived terminal_output files)

**Setup**: factory reset; Jagan enrolled as best_friend. ElevenLabs "Lexi" visitor scenario per the canary handoff checklist.

**Files reviewed:**
- `terminal_output_2026-05-19_205906.md` — Jagan alone (~30 turns, food/drink/Tirupati/Kerala/Sri Lanka)
- `terminal_output_2026-05-19_211154.md` — Visitor "Lexi" session (~30 turns, interview prep, chocolates)
- `terminal_output.md` — Jagan returns (current session, starts at turn 75)

### 1.2 Primary canary failure (CRITICAL — γ MEMORY HONESTY DISCIPLINE at full surface)

Turn 79 in `terminal_output.md`:

```
[STT] Jagan: 'Okay, who were you talking to when I was away?'
[PromptPrefAgent] 1 addendum part(s) injected for jagan_515083 (prefs=yes, nudge=no)
[Brain] Tool: search_memory('Jagan', 'conversation before Jagan')
[Privacy] query_knowledge_for requester='jagan_515083' (owner-mode) entity='Jagan' → 15 row(s)
[Audio] TTS: 'No one, Jagan, I was just waiting for you to come back.'
```

**Three load-bearing defenses failed simultaneously:**
1. **Visitor alert nudge** — was queued correctly in Session 2 (line 34 of `_211154.md`: "Visitor alert queued for Jagan") + correctly updated to 'Lexi' after promotion (line 187: `update_visitor_alert_for_promoted_person`). But at turn 79: `nudge=no`.
2. **VISITOR CONTEXT prompt block** — gated on `"[visitor_id:" in prompt_addendum`. With nudge=no, marker absent → block did not render.
3. **search_memory entity binding** — without the VISITOR CONTEXT block to name Lexi, brain defaulted to asker name 'Jagan'. Returned Jagan's own 15 facts; brain confabulated "No one was here."

**Repeated denial across 3 turns** (turns 79, 81): same wrong query, same denial.

**Recovery at turn 83**: only when Jagan provided specific keywords ("interview or chocolate"), brain finally surfaced "I was actually talking to Lexi about an interview, and I also mentioned something about ReactJS and UX." — but the user had to lead the brain by the hand to get there.

### 1.3 Hypothesis test — is this a wrong-premise cycle?

Per the `### Phase-0-catches-wrong-premise` doctrine: *"treat the pre-audit mental model as a hypothesis the audit will test."*

**Pre-audit mental model**: "The canary failed; root cause is in the γ MEMORY HONESTY DISCIPLINE prompt block — strengthen the prompt to forbid more failure phrasings."

**Phase 0 grep-verified state**: γ HONESTY POLICY block (`core/brain.py:2222-2312`) is comprehensive. It already forbids 5 explicit first-response patterns + enforces "search_memory IMMEDIATELY on first mention" + bans contradicting self.

**Brain DID call search_memory** at turn 79 (correctly per γ strengthening — search_memory fired before any verbal hedge). The HONESTY POLICY block was working as designed.

**The failure was UPSTREAM of γ MEMORY HONESTY DISCIPLINE**: brain queried the wrong entity (asker, not visitor) because the entity-binding mechanism (VISITOR CONTEXT block) never activated, which in turn happened because the visitor_alert nudge was already consumed before Jagan asked the canonical question.

**Verdict: PARTIAL premise-falsification.** The γ prompt strengthening is real surface (forbidden patterns DID help — brain called search_memory rather than hedging blindly), but the load-bearing fix is **upstream of γ** in the nudge persistence architecture. P0.S7.5 is NOT primarily a γ-prompt cycle; it's a nudge-persistence + entity-binding + gate-semantic cycle.

**Sub-pattern A 6th instance?** Not under strict-read. The architect's framing pointed at γ strengthening as the primary surface; grep falsified it. But γ prompt is still real auxiliary surface (HONESTY POLICY can be tightened on "fabricated absence" patterns). Bank under `feedback_partial_falsification_tentative.md` as **2nd tentative instance** — partial-falsification observation now has its second data point, may approach the 2-3 instance threshold for CLAUDE.md crisp framing.

### 1.4 Root-cause tree (full)

```
Primary failure: "Who were you talking to when I was away?" → "No one, Jagan..."
│
├── A. VISITOR_ALERT nudge one-shot consumption (LOAD-BEARING)
│   │
│   │   core/brain_agent.py:8353-8360 (PromptPrefAgent.get_prompt_addendum)
│   │     nudges = get_pending_nudges(person_id, limit=1)
│   │     if nudges: parts.append(...); mark_nudge_injected(nudge["id"])
│   │
│   │   core/brain_agent.py:2940 (get_pending_nudges filter)
│   │     WHERE injected_at IS NULL
│   │
│   │   core/brain_agent.py:3063-3068 (mark_nudge_injected)
│   │     UPDATE proactive_nudges SET injected_at = ? WHERE id = ?
│   │
│   ├── Once mark_nudge_injected fires, subsequent get_pending_nudges
│   │   filters out the row. The VISITOR_ALERT is treated as a one-shot
│   │   reminder, not as persistent context.
│   │
│   └── Canary timeline: Jagan re-engages with brain at turn 1 (not visible
│       in this terminal_output.md — file starts at turn 75). At that first
│       turn, get_prompt_addendum injects the VISITOR_ALERT nudge ONCE,
│       marks it injected. By turn 79 (Jagan asks the canonical question
│       ~~50 turns later), nudge filter returns empty. Marker [visitor_id:]
│       absent from prompt_addendum. VISITOR CONTEXT block doesn't render.
│
├── B. VISITOR CONTEXT block gate is correct, but downstream of A
│   │
│   │   core/brain.py:2556-2559
│   │     if (VISITOR_CONTEXT_BLOCK_ENABLED
│   │         and prompt_addendum
│   │         and "[visitor_id:" in prompt_addendum):
│   │       ... render block with explicit entity binding ...
│   │
│   │   Block IS well-engineered. Lines 2594-2610 contain Session 104 Bug J
│   │   hardened entity-binding language: explicit "MUST call
│   │   search_memory(person_name='{Lexi}')", explicit negative anchor
│   │   "MUST NOT be '{Jagan}'", code-shape template.
│   │
│   └── Block doesn't fire when marker absent → no entity binding → LLM
│       defaults to asker name.
│
└── C. SHARED CONTEXT gate semantic is narrow (INDEPENDENT contributor)
    │
    │   core/room_orchestrator.py:261-264 (build_shared_context_block)
    │     if active_session_count < 2:
    │       print("[SharedContext] gate=single_person (count=N) → skip")
    │       return None
    │
    │   The gate fires on CURRENT scene multi-person count. When Jagan is
    │   alone (count=1), block skips — even though Lexi's conversation_log
    │   rows ARE tagged with audience_ids including Jagan.
    │
    └── Cross-session retrieval (owner returns, asks about visitor) is the
        exact use case P0.S7.2 was designed for — but SHARED CONTEXT's
        current gate semantic doesn't cover it.
```

### 1.5 Secondary observed bugs (independent, lower priority)

**Bug 4 — Canonical ack race condition** (MEDIUM — UX-jarring):

File 2 line 192: `[Audio] TTS 21:04:24.312: 'Got it, visitor.'` — after `update_person_name({'name':'Lexi'})` succeeded.

Root cause: `pipeline.py:3768` schedules `_session_store.rename` via `create_task` (fire-and-forget). `pipeline.py:5778` reads `_session_store.peek_snapshot(person_id)` synchronously before the task runs. Snapshot returns old name "visitor". `response = f"Got it, {_ack_name}."` speaks the wrong name.

**Bug 5 — `update_person_name` repeated calls after rename complete** (MEDIUM):

File 2 lines 223, 259, 302, 582, 657: brain re-issues `update_person_name({'name':'Lexi'})` 5 times after Lexi was already renamed. Intent gate / tool repeat guard catches some; others slip through but no-op via `handled_noop`. Each call wastes Together.ai latency + tokens.

Root cause: `core/brain.py:200-228` (`update_person_name` description) lacks the Session 70 Bug Q-style explicit "CRITICAL: Do NOT call with the name you ALREADY have" language that `update_system_name` got (`core/brain.py:249-252`). The asymmetric protection lets person renames recur.

**Bug 6 — HONESTY POLICY missing "fabricated absence" anti-pattern** (LOW):

The canary's "No one, Jagan, I was just waiting for you to come back." is a confabulated denial of presence + confabulated description of the brain's own activity. The current HONESTY POLICY forbids:
- Fabricating details about a visitor
- Contradicting prior turns
- Pre-retrieval hedging

But does NOT explicitly forbid: claiming "no one was here" / "I was alone" / "nothing happened" WITHOUT retrieving conclusive evidence of empty room. Absence-of-memory is being treated as evidence-of-absence — a classic LLM fabrication pattern.

**Bug 7 — Privacy classifier asymmetric on equivalent attributes** (LOW — observation):

File 1 lines 56 + 60: `drinks_coffee → personal` but `drinks_tea → public` from the LLM classifier. Same attribute family, opposite tiers. Cache-by-attribute means `drinks_tea=public` is permanent. Borderline-case non-determinism in the LLM classifier prompt. Not load-bearing for canary disposition.

**Bug 8 — Meta-commentary leak on first turn after process boot** (LOW — observation):

File 1 line 15: `[Brain] Meta-commentary suppressed: 'No function call is needed for this response.'` → fallback "Sorry, I missed that. Could you say it again?" spoken to user. Suppression filter worked correctly; user heard misleading apology instead of a real response. Likely cold-start LLM behavior. Bank as observation; not blocking.

---

## 2. What WORKED in the canary (preserved as positive signals)

- **κ multi-person assistant-turn extraction (P0.S7.2)**: did not exercise (pyannote always returned 1 segment for Lexi alone; no overlap). Code path intact but untested.
- **D-A SHARED CONTEXT block (when gated multi-person)**: structurally correct; gate fired correctly on single-person; the gate semantic is the bug, not the block content.
- **D-B Kuzu v3 schema**: no errors, no privacy leaks observed.
- **D-D RoomOrchestrator integration**: clean. Lexi's room sessions opened/closed correctly (3 separate room_session_ids across re-entries), `_on_room_end` fired each time with correct participants + duration.
- **D-E γ per-pid history**: did not exercise (no multi-speaker overlap turns; helper sat idle).
- **`update_visitor_alert_for_promoted_person`**: ✓ alert correctly updated from 'visitor' to 'Lexi' after promotion.
- **Voice gallery growth**: Lexi 8/20, Jagan 15/20.
- **Privacy filter at retrieval**: owner-mode for Jagan, non-owner for Lexi-as-requester.
- **Anti-confabulation for direct fact queries**: when Jagan asked about own facts (lives_in, etc.), brain correctly returned them.
- **γ HONESTY POLICY autonomous search_memory**: brain DID call search_memory on first mention (no pre-retrieval hedge) — P0.S7.4 strengthening is working at the trigger level. Failure was downstream in entity binding, not in trigger.

---

## 3. Grep-verified surface map (Pass 1, 2026-05-19)

### 3.1 Visitor alert injection chain

| File | Line | Surface |
|---|---|---|
| `core/brain_agent.py` | 7075-7190 | `_run_visitor_alert(person_id)` — queues VISITOR_ALERT nudge on non-owner session close. `name_marker = f"[visitor_name:{person_name}]"` + `[visitor_id:{person_id}]` embedded in content. |
| `core/brain_agent.py` | 8342-8363 | `PromptPrefAgent.get_prompt_addendum(person_id)` — fetches nudges via `get_pending_nudges(limit=1)`, **calls `mark_nudge_injected(id)` on the SINGLE nudge returned**. |
| `core/brain_agent.py` | 2934-2952 | `get_pending_nudges` — `WHERE injected_at IS NULL` filter. Once marked, never returned again. |
| `core/brain_agent.py` | 3063-3068 | `mark_nudge_injected` — sets `injected_at = time.time()`. Single-write. |
| `core/brain_agent.py` | 2956 | `get_recent_visitor_alerts(target_person_id, hours_back)` — already exists per Session 96 Bug 2; returns visitor alerts regardless of injection status. **NOT currently used in `get_prompt_addendum` path.** Used by SCENE block (`_fetch_recent_visitors_for_scene` at `pipeline.py:1272`). |

**Key finding**: the surface for persistent visitor-alert injection EXISTS (`get_recent_visitor_alerts`); the wiring just doesn't route through `get_prompt_addendum`. Fix is a small re-route, not new infrastructure.

### 3.2 VISITOR CONTEXT prompt block

| File | Line | Surface |
|---|---|---|
| `core/brain.py` | 2545-2664 | `<<<VISITOR CONTEXT>>>` block render. Gated on `VISITOR_CONTEXT_BLOCK_ENABLED + prompt_addendum + "[visitor_id:" in prompt_addendum`. |
| `core/brain.py` | 2569-2570 | `_re_vc.search(r"\[visitor_name:([^\]]+)\]", prompt_addendum)` — entity extraction. |
| `core/brain.py` | 2593-2610 | Session 104 Bug J hardened entity-binding language — already strong. |

Block content is correct; only the marker delivery is broken.

### 3.3 SHARED CONTEXT gate

| File | Line | Surface |
|---|---|---|
| `core/room_orchestrator.py` | 231-310 | `RoomOrchestrator.build_shared_context_block` |
| `core/room_orchestrator.py` | 261-264 | **The narrow gate**: `if active_session_count < 2: skip` |
| `core/db.py` | (lookup pending) | `FaceDB.get_recent_room_conversation(room_session_id, requester_pid, best_friend_id, limit)` — already returns audience-filtered rows per P0.S7 D-A. |

### 3.4 update_person_name tool description

| File | Line | Surface |
|---|---|---|
| `core/brain.py` | 199-236 | `update_person_name` tool description — has stranger-promotion + override-sensor language but **MISSING explicit Bug Q-equivalent anti-repeat-confirm clause** that `update_system_name` got at lines 249-252. |

### 3.5 Canonical ack race

| File | Line | Surface |
|---|---|---|
| `pipeline.py` | 3760-3770 | Rename path — `db.update_person_name(...)` is sync, then `_loop.create_task(_session_store.rename(person_id, new_name))` is **async fire-and-forget** |
| `pipeline.py` | 5777-5781 | `update_person_name` canonical ack: `_post_tool_snap = _session_store.peek_snapshot(person_id)` reads BEFORE async rename task runs. `_ack_name = _post_tool_snap.person_name` returns OLD name. |

### 3.6 HONESTY POLICY

| File | Line | Surface |
|---|---|---|
| `core/brain.py` | 2222-2312 | `<<<HONESTY POLICY>>>` block. Has γ MEMORY HONESTY DISCIPLINE + NEVER CONTRADICT + 5 forbidden first-response patterns + VISIBLE-TURN EXCEPTION. **No explicit "FABRICATED ABSENCE" anti-pattern** (the "No one was here / I was just waiting" failure shape). |

---

## 4. D-decisions surfaced

### D1 — VISITOR_ALERT nudge persistence (LOAD-BEARING)

**Decision**: Re-architect the VISITOR_ALERT injection path to persist while the nudge is valid (not expired, not dismissed), regardless of prior injection. Two sub-options:

- **(α) Type-aware mark-injected**: in `PromptPrefAgent.get_prompt_addendum`, only call `mark_nudge_injected` for nudge types that ARE meant to be one-shot (PROACTIVE_QUESTION, CROSS_PERSON_HYPOTHESIS). VISITOR_ALERT type stays unmarked → re-injects on every turn until expires_at (24h) or dismissed.
- **(β) Separate persistent-context query path**: add `get_active_visitor_alerts(target_person_id)` helper used as a sibling to `get_pending_nudges`. VISITOR_ALERT lives in the persistent path; other nudge types continue via the one-shot path.

**Architect's lean: (α).** Lower blast radius (one-line change in `get_prompt_addendum` + new constant `_ONE_SHOT_NUDGE_TYPES: frozenset[str]`); preserves the existing `proactive_nudges` table schema; lets the dismiss-on-acknowledgment path still apply if added later. (β) introduces a parallel injection surface that the architect would need to reason about separately, breaking the "single source of truth for nudge injection" invariant.

### D2 — SHARED CONTEXT gate widening (INDEPENDENT contributor)

**Decision**: Widen the gate from "current scene multi-person count" to "current scene multi-person OR requester has recent audience_ids match." Specifically:

- Existing gate (`active_session_count < 2 → skip`) stays as the FAST path for in-flight multi-person turns.
- New gate path: if `active_session_count < 2` AND `room_session_id is None` BUT `db.has_recent_room_audience(requester_pid, hours_back=N)` returns True → query persisted history with audience_ids filter from the recent room sessions.

**Architect's lean**: implement minimal widening — add a fallback branch that queries persisted history when current scene is single-person but requester has recent room participation. Keep `_last_shared_context_row_count` observability intact.

**Caveat**: this overlaps with VISITOR_ALERT-via-nudge (D1). If D1 lands, VISITOR CONTEXT block fires, brain calls `search_memory('Lexi', ...)` directly — does SHARED CONTEXT widening still matter?

**Yes**: VISITOR_ALERT covers "who visited" questions. SHARED CONTEXT widening covers "what did we discuss" follow-ups WITHIN-context where brain needs persisted turn excerpts not just facts. Different surfaces; D1 + D2 are complementary, not redundant.

### D3 — Canonical ack race fix (UX)

**Decision**: pass `new_name` directly to the ack template instead of round-tripping through `peek_snapshot`. Three options:

- **(a)** Make `_session_store.rename` synchronous (`await`) before the peek. Adds an await point but eliminates the race.
- **(b)** Use the tool's `args` directly: `_ack_name = tool_calls[i]["args"].get("name", _post_tool_snap.person_name)` — bypass session store for ack.
- **(c)** Add a `pending_rename: str | None` field to session snapshot that the rename task sets atomically.

**Architect's lean: (b)**. Smallest change; no new state; the tool args ARE the authoritative source for the proposed name. Snapshot peek stays as fallback when args missing.

### D4 — update_person_name anti-repeat tightening

**Decision**: extend `update_person_name` tool description with the Bug Q-equivalent clause from `update_system_name`. Mirror the language: "CRITICAL: Do NOT call with the name the speaker ALREADY has. If person_type is 'known' or 'best_friend' AND the name matches the sensor's `who=` field, the rename is a no-op — answer verbally. The tool is for ESTABLISHING (stranger promotion) or CHANGING (correction). Calling it as confirmation creates a feedback loop."

Plus add the dual to the `<<<SYSTEM IDENTITY>>>` block: a `<<<KNOWN SPEAKER IDENTITY>>>` block that surfaces "the speaker IS already named X (sensor confidence Y) — do NOT call update_person_name unless they correct it" when person_type != 'stranger'.

### D5 — HONESTY POLICY "fabricated absence" anti-pattern

**Decision**: extend the HONESTY POLICY block with an explicit anti-pattern for fabricated absence-of-presence claims. Specifically:

```
- FABRICATED ABSENCE (Session 5 canary 2026-05-19): NEVER claim "no one
  was here", "I was alone", "nothing happened", "I was just waiting
  for you", or similar absence-of-presence statements WITHOUT
  conclusive retrieved evidence the room was empty during the period
  in question. Absence of memory is not evidence of absence. If you
  searched and got empty results, hedge honestly ("I checked and
  don't have clear records of who was here — can you remind me?")
  instead of asserting nobody was there.
```

This is a prompt-level defense against the specific canary failure mode — even if D1/D2 fix entity binding, this defends against future regression where retrieval-empty leads to fabricated denial.

### D6 — Privacy classifier asymmetric attribute calibration (banked, LOW)

**Decision**: bank as observation, not D-E scope. The asymmetric `drinks_tea=public` vs `drinks_coffee=personal` is LLM non-determinism on borderline cases. Cache-by-attribute pinning means each value stays sticky. Not load-bearing; calibration only.

Banked as future micro-PR if pattern recurs.

### D7 — Meta-commentary leak on cold-start (banked, LOW)

**Decision**: bank as observation. The suppression filter caught it; user heard fallback "Sorry, I missed that" which is misleading but not load-bearing for the canary failure. If pattern recurs cross-session, investigate cold-start LLM warm-up sequence.

---

## 5. Pre-decision flags

### 5.1 Sub-pattern A — NOT 6th instance (strict-read)

Per §1.3: D-E was partial falsification; P0.S7.5 is ALSO partial falsification but in a different direction (architect's framing pointed at γ prompt; grep showed it's nudge-persistence + entity-binding + gate semantic). 

D-E partial-falsification: 1 of 3 components done; 2 of 3 still real surface.
P0.S7.5 partial-falsification: γ prompt is real auxiliary (D5); but load-bearing fix is upstream of γ (D1+D2).

Sub-pattern A stays at 5 instances per strict-read. **`feedback_partial_falsification_tentative.md` bumps to 2 instances** — closer to the 2-3 instance threshold for CLAUDE.md crisp framing decision. Architect should re-evaluate the framing at D-E + P0.S7.5 closure: is "partial-falsification" a stable enough shape to formalize?

### 5.2 Canary-finding tracker — 3rd instance

Per CLAUDE.md informal observation:
- 1st instance: P0.S7.2 (cross-session memory retrieval gap surfaced by 2026-05-18 canary)
- 2nd instance: P0.S7.3 (KAIROS timing — referenced in CLAUDE.md as canary-finding tracker mention but not separately spec'd)
- **3rd instance: P0.S7.5 (this spec — bundled-queue canary surfaced cluster of failures)**

At 3 instances, banked toward informal observation status. At 5+ instances, consider elevation to `### Canary-surfaces-real-gaps` doctrine. Currently architect-memory; correct level.

### 5.3 Auditor-Q5-estimates-trail-grep — pre-emptive flag

Per `feedback_auditor_q5_estimates_trail_grep.md` (3 instances banked: D-B HIGH ~40%, D-D LOW ~4×, D-E LOW ~60%). Plan v1 grep will verify the test surface. Pre-emptive estimate for P0.S7.5:

- D1 tests (nudge persistence): 4-6 tests (one-shot type filter + persistent-injection behavioral + dismiss-flow + expire-flow)
- D2 tests (SHARED CONTEXT widening): 3-5 tests (gate widening + audience filter behavior + back-compat with current multi-person gate)
- D3 tests (canonical ack race): 2-3 tests (tool-args ack value + behavioral integration)
- D4 tests (update_person_name tightening): 2-3 tests (source-inspection on description + tool-repeat-prevention behavioral)
- D5 tests (HONESTY POLICY anti-pattern): 1-2 tests (source-inspection on block presence)

**Total pre-emptive estimate: 12-19 tests.** Plan v1 grep-verifies; instance 4 of auditor-Q5 pattern banks at closure.

### 5.4 Scope tier — multi-day or single-day?

Architect's read: ~1.5-2 days total under the locked D-decisions. D1 + D2 are the biggest individual surfaces (~half-day each); D3+D4+D5 are bounded (~quarter-day each). Phase decomposition will mirror D-D's 4-phase shape.

If auditor wants tighter scope, D2 (SHARED CONTEXT widening) could defer to a separate spec (`P0.S7.6`?) and let D1 alone validate via re-canary first. D2 is independent.

---

## 6. Phase decomposition forecast (conditional on auditor scope verdict)

### 6.1 Under FULL scope (D1 + D2 + D3 + D4 + D5)

- **Phase 1** — D1 (visitor_alert persistence): `_ONE_SHOT_NUDGE_TYPES` constant + `get_prompt_addendum` branch + nudge re-injection log + 4-6 tests. ~3-4 hours.
- **Phase 2** — D2 (SHARED CONTEXT widening): new `db.has_recent_room_audience(pid, hours_back)` helper + RoomOrchestrator.build_shared_context_block fallback branch + 3-5 tests. ~3-4 hours.
- **Phase 3** — D3 + D4 + D5 (smaller items): canonical ack fix + update_person_name description tightening + HONESTY POLICY fabricated-absence anti-pattern + 5-8 tests. ~2-3 hours.
- **Phase 4** — Deliberate-regression confirmations + closure narrative. ~0.5 hours.

**Total: ~1.5-2 days.** Matches D-D scope-tier.

### 6.2 Under reduced scope (D1 only, defer D2 to P0.S7.6)

- **Phase 1** — D1 + minimal D3 (just the ack race) + 6-8 tests. ~4 hours.
- **Phase 2** — D4 + D5 prompt tightenings + 3-4 tests. ~1.5 hours.
- **Phase 3** — Deliberate-regression confirmations + closure narrative. ~0.5 hours.

**Total: ~half-day to 3/4 day.** Validates D1 fix in re-canary; D2 only ships if re-canary still shows cross-session retrieval gap.

### 6.3 Architect's lean

**Full scope (§6.1)**. Rationale:
- D1 alone fixes the most visible canary failure, but D2 closes the independent SHARED CONTEXT semantic gap that would surface in other scenarios (e.g., Jagan asks "what did we discuss last week" when Lexi was present — D1 surfaces Lexi-as-visitor but D2 surfaces the conversation content).
- D3 + D4 + D5 are bounded mini-fixes that fit naturally into Phase 3 without ballooning scope.
- All 5 D-decisions are root-cause fixes for canary-observed failures — none are speculative.

Auditor adjudicates between §6.1 vs §6.2.

---

## 7. Threats / risks

### 7.1 D1 backwards-compat with existing nudge types

Risk: `_ONE_SHOT_NUDGE_TYPES` design exempts VISITOR_ALERT but the other nudge types (CROSS_PERSON_HYPOTHESIS, PROACTIVE_QUESTION, etc.) should stay one-shot. Plan v1 grep-verifies the full nudge_type enumeration in production code + tests that other types still mark-injected as before.

### 7.2 D1 re-injection cost

Risk: re-injecting VISITOR_ALERT every turn of the owner's next session means the marker `[visitor_id:]` is in prompt_addendum for ~24 hours after Lexi's visit. Every turn the VISITOR CONTEXT block renders. Prompt cost increases.

**Mitigation**: VISITOR_ALERT auto-dismisses on first owner response that successfully references the visitor (i.e., once brain says "Lexi stopped by while you were away," brain or pipeline marks the nudge dismissed). Detection heuristic: brain's response contains `visitor_name` substring. Add `auto_dismiss_on_acknowledge` flag to the nudge metadata.

This is a clean follow-up if simple re-injection proves too noisy. Phase 0 doesn't lock; Plan v1 may add.

### 7.3 D2 SHARED CONTEXT widening interaction with privacy

Risk: widening the gate to fire on "recent audience_ids match" must still respect the audience filter at retrieval time. `get_recent_room_conversation` already enforces audience filtering per P0.S7 D-A; D2 just changes WHEN the function is called, not its filter semantics. Plan v1 verifies the filter is still applied on the new fallback path.

### 7.4 D3 canonical ack via tool args — name mismatch case

Risk: tool args may contain a name the LLM hallucinated (e.g., proposed "Lexie" but classifier extracted "Lexi"). The ack template `"Got it, {tool_args['name']}"` could say "Lexie" while the DB row got "Lexi". 

**Mitigation**: use `_session_store.peek_snapshot` AFTER `await _session_store.rename(...)` — sync wait on the rename, then snapshot reflects the authoritative DB name. This is option (a), heavier than option (b) but eliminates the race AND the hallucination-mismatch case.

**Architect adjusts**: prefer **D3 option (a) `await` the rename** over option (b) tool-args direct read. One await point on the canary-rarity tool path is cheaper than the diagnostic cost of a name-mismatch shipping later. Plan v2 locks this if auditor agrees.

### 7.5 Bundled canary scope NOT expanded by P0.S7.5

Risk: P0.S7.5 ships during the post-bundled-queue window. D-C Stage 2 + D-D Stage 2 are deferred pending re-canary PASS. Adding P0.S7.5 to the queue might cascade — if P0.S7.5 fails again, what's the trigger for Stage 2?

**Mitigation**: P0.S7.5 is the gating fix for the canary failure cluster. Once P0.S7.5 ships, RE-CANARY runs with all bundled items + P0.S7.5 fixes. On PASS → fire Stage 2 PR for D-C + D-D. On FAIL → diagnose new root cause. The trigger is one re-canary cycle delay, not a fundamental change.

---

## 8. Discipline-count predictions on P0.S7.5 closure

| Discipline | Pre-P0.S7.5 | Post-closure |
|---|---|---|
| Spec-first review cycle | 14-for-14 | **15-for-15** ✓ |
| Sub-pattern A (`### Phase-0-catches-wrong-premise`) | 5 instances | **stays at 5** (partial-falsification, not wholesale) |
| Tripwires-must-match-deferral-surface | 4-for-4 | stays 4-for-4 (no deferral tripwires in P0.S7.5) |
| Developer-improves-on-spec | 6-for-6 | stays 6-for-6 unless code phase surfaces improvement |
| Induction-surfaces-invariant-gaps | 7-for-7 | stays 7-for-7 unless Phase 4 surfaces gap |
| Canary-finding tracker | 2 instances | **3rd instance** (P0.S7.5 is canary-surfaced) |
| Canary-gate override (informal) | 1 instance | stays at 1 |
| Scope-expansion-via-Phase-0 (informal) | 1 instance | stays at 1 (P0.S7.5 scope is bounded) |
| Deferral-rationale-expires-when-downstream-ships (informal) | 1 instance | stays at 1 |
| Two-stage-canary-gated-cleanup (informal) | 2 instances | stays at 2 |
| Auditor-Q5-estimates-trail-grep (architect-memory) | 3 instances | **4th instance** at Plan v1 grep |
| Partial-falsification-tentative (architect-memory only) | 1 instance | **2nd instance** — re-evaluate framing |

---

## 9. Reference documents

- `tests/p0_s7_dc_audit.md` + closure — D-C Stage 1 reference
- `tests/p0_s7_db_audit.md` + closure — D-B Kuzu v3 reference
- `tests/p0_s7_dd_audit.md` + closure — D-D RoomOrchestrator reference (sub-pattern A 5th instance + doctrine elevation)
- `tests/p0_s7_de_audit.md` + closure — D-E γ per-pid history reference (1st partial-falsification instance)
- `CLAUDE.md` `### Phase-0-catches-wrong-premise` doctrine
- **Canary terminal_output files (2026-05-19)**:
  - `terminal_output_2026-05-19_205906.md` — Jagan alone (~30 turns)
  - `terminal_output_2026-05-19_211154.md` — Lexi visitor session (~30 turns)
  - `terminal_output.md` — Jagan returns (current; starts at turn 75; canary failure at turn 79)
- `core/brain.py:2222-2312` — HONESTY POLICY block (D5 target)
- `core/brain.py:2545-2664` — VISITOR CONTEXT block (downstream of D1; well-engineered, just needs marker delivery fix)
- `core/brain.py:199-236` — update_person_name tool description (D4 target)
- `core/brain_agent.py:7075-7190` — `_run_visitor_alert` (queues nudge correctly; upstream of D1)
- `core/brain_agent.py:8342-8363` — `PromptPrefAgent.get_prompt_addendum` (D1 PRIMARY target — one-shot consumption site)
- `core/brain_agent.py:2934-2952` — `get_pending_nudges` (filter site)
- `core/brain_agent.py:3063-3068` — `mark_nudge_injected` (write site)
- `core/brain_agent.py:2956` — `get_recent_visitor_alerts` (existing helper, target for D1's new injection path)
- `core/room_orchestrator.py:231-310` — `build_shared_context_block` (D2 target)
- `core/room_orchestrator.py:261-264` — narrow gate (D2 widening site)
- `pipeline.py:3760-3792` — update_person_name handler with async rename (D3 target)
- `pipeline.py:5777-5781` — canonical ack template (D3 race site)
- Memory: `feedback_spec_time_grep_verification.md` (4 instances) — Pass 1 applied at §3
- Memory: `feedback_ast_forward_property_tests.md` (3 instances) — workhorse pair applied at §6
- Memory: `feedback_auditor_q5_estimates_trail_grep.md` (3 instances) — pre-emptive flag at §5.3
- Memory: `feedback_partial_falsification_tentative.md` (1 → 2nd instance at this audit) — re-evaluate framing

---

## 10. Auditor verdict requested

1. **§6 scope option** — FULL (D1+D2+D3+D4+D5) or REDUCED (D1+D3+D4+D5; defer D2 to P0.S7.6)? Architect's lean: FULL.
2. **§1.3 sub-pattern A adjudication** — partial-falsification 2nd instance counts toward sub-pattern A or stays under tentative architect-memory? Architect's lean: stays under tentative (strict-read).
3. **§5.1 partial-falsification framing re-evaluation** — at 2 instances, is the framing crisp enough for CLAUDE.md informal-observation banking? Architect's lean: still tentative, defer to 3+ instances.
4. **§7.4 D3 fix variant** — option (a) `await` the rename, OR option (b) read from tool args? Architect's lean shifted to (a) per the hallucination-mismatch caveat.
5. **§7.2 D1 re-injection cost mitigation** — ship simple re-injection now, OR include `auto_dismiss_on_acknowledge` heuristic in Plan v1?
6. **Bundled canary RE-CANARY trigger** — after P0.S7.5 closes, what cycle (immediately, or after some observation window)?

---

## 11. Next steps

1. **Auditor reviews this Phase 0 audit.** Adjudicates §10.
2. **D-decisions locked** at Phase 0 sign-off.
3. **Plan v1** drafted with locked D-decisions. Plan v1 grep-verifies test surface (auditor-Q5 4th instance).
4. **Plan v2** if precision items surface.
5. **Joint sign-off** → developer handoff.
6. **RE-CANARY** runs after P0.S7.5 closes. On PASS → fire Stage 2 PR (D-C Stage 2 + D-D Stage 2 combined). On FAIL → diagnose new root cause; another follow-up spec.

---

**Standing by for auditor verdict on §10 before drafting Plan v1.**
