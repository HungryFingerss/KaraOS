# P0.S7.D-E — Multi-speaker `conversation_turn` redesign — Phase 0 Audit

**Date:** 2026-05-19
**Author:** architect
**Status:** Phase 0 — grep-verified findings, zero production-code changes. **Partial premise-falsification finding — auditor adjudication on scope-reduction needed before D-decision lock.** Standing by for auditor review.

**Companion document trail (forthcoming):**
- `tests/p0_s7_de_plan_v1.md` — after Phase 0 sign-off + D-decision lock
- `tests/p0_s7_de_plan_v2.md` — after Plan v1 review

**Disciplines applied at audit drafting:**
- **Two-pass grep-verification (Pass 1)**: all function/line/symbol references grep-verified 2026-05-19. Pass 2 fires at closure.
- **AST + behavioral workhorse pair** (3 instances, architect-memory): §6 test design preserves the discipline.
- **`### Phase-0-catches-wrong-premise` doctrine** (CLAUDE.md, just elevated 2026-05-19): explicit hypothesis-testing framing applied at §1.

---

## 1. Sub-pattern A hypothesis-test — PARTIAL falsification (not 6th instance)

Per the newly-elevated `### Phase-0-catches-wrong-premise` doctrine: *"treat the pre-audit mental model as a hypothesis the audit will test — not as the locked scope."*

### 1.1 Original D-E framing (P0.S7 Phase 0 audit + CLAUDE.md "Features pending")

```
D-E — Multi-speaker conversation_turn redesign. Remove _cur_pid
singular primary speaker model from conversation_turn, multi-speaker
signature, interleaved history with speaker tags. 3-5 days,
deferred until D-D establishes the access-site pattern.
```

Three components:
1. Remove `_cur_pid` singular primary model
2. `conversation_turn()` multi-speaker signature
3. Interleaved history with speaker tags

### 1.2 Grep-verified state of each component (2026-05-19)

| Component | Grep finding | Status |
|---|---|---|
| **1: Remove `_cur_pid` singular primary** | 68 `_cur_pid` references in pipeline.py — all LOCAL to `run()`'s inner loop. Set at line 6851 via `_primary_person_id()`; updated at routing decision points (line 7371-7459); passed to `conversation_turn(_cur_pid, _cur_name, ...)` at line 7781. | **Real surface, but conceptually it's a TURN-DISPATCH VARIABLE, not a global "singular primary" architectural model.** |
| **2: Multi-speaker conversation_turn signature** | `async def conversation_turn(text, person_id, person_name, db=None, vision_state=None, voice_state=None, prompt_addendum_override=None)` at pipeline.py:4741-4748. Still singular-signature. | **Real — singular signature persists.** |
| **3: Interleaved history with speaker tags** | `_build_room_block` Section 3 (pipeline.py:1524-1546 area, now moved into RoomOrchestrator per D-D) interleaves all `_session_store.peek_all_snapshots()` × each pid's `_conversation_store.peek_history(pid)`, sorted chronologically, capped at `ROOM_BLOCK_TURN_CAP=10`, with `[Xm ago] Speaker → Addressee: "content"` format. | **ALREADY DONE** in S113 P3B.1 (2026-04-24). Component 3 is COMPLETE under different naming (`<<<ROOM>>>` block). |

### 1.3 Premise-falsification verdict

**Component 3 is wholesale falsified** (already done; same shape as D-D's wholesale-falsification by P0.7/P0.6.6).

**Components 1+2 are PARTIALLY load-bearing** — the surface exists, but is it architectural cleanup or load-bearing user-visible work?

This is NOT a sub-pattern A 6th instance under strict-read interpretation. D-D's premise was 100% falsified (0 access sites). D-E's premise is ~33% falsified (1 of 3 components done; 2 of 3 still real surface). Under the now-doctrine `### Phase-0-catches-wrong-premise` strict-read, partial falsification doesn't count as a wrong-premise instance — the architect was partially correct.

**However, the partial falsification surfaces a scope question**: what do Components 1+2 actually deliver in user-visible value, given that the current architecture (D-A through D-D + S113 P3B.1) already covers most multi-speaker semantics?

---

## 2. Grep-verified surface map (2026-05-19)

### 2.1 `_cur_pid` access surface in pipeline.py

68 references. Breakdown by purpose (sampled):

| Site type | Approx count | Purpose |
|---|---|---|
| `_cur_pid = ...` assignments | 8 | Routing-decision updates |
| `_cur_pid` reads for dispatch | ~20 | Pass to conversation_turn, KAIROS, state labels |
| `_cur_pid == comparisons` | ~15 | Face-loss-exit guards, speaker-switch detection |
| `_cur_pid is None / not None` | ~10 | Defensive checks |
| Other (parameter to helpers, log lines, etc.) | ~15 | Miscellaneous |

**All 68 references are inside `run()`'s inner loop scope** (lines 6845-7799 roughly). NOT module-level state; NOT class state. Just local turn-dispatch variable.

### 2.2 `conversation_turn` definition + caller

- **Definition**: `pipeline.py:4741-4748` — singular `person_id` + `person_name` signature
- **Caller (one)**: `pipeline.py:7780-7785` — `await conversation_turn(text, _cur_pid, _cur_name, db, ...)`

### 2.3 In-memory `_conversation_store._history[pid]` write path

- `_conversation_store.append_turns(person_id, [...])` at pipeline.py:2974 — per-pid append
- Inside `conversation_turn`, history is appended under the singular `person_id` parameter

### 2.4 Multi-speaker INPUT handling (already in place)

- `_format_multispeaker_transcript` exists in pipeline.py (per S113 P3B.4)
- pyannote diarization wired via `core/voice.py::diarize()` (per S88)
- Multi-speaker emit path: `if len(_diar) >= 2:` at pipeline.py (S113 retargeting)
- Combined transcript format: `[Name1]: text\n[Name2]: text` (N=2 legacy) OR `[N voices simultaneously]\n{Name}: text\n...` (N≥3)

### 2.5 Components NOT under D-E (out-of-scope reference)

- ROOM block (Component 3 — done)
- κ multi-person assistant-turn extraction (P0.S7.2 — done)
- SHARED CONTEXT block (P0.S7 D-A — done)
- ADDRESS DECISION marker parsing (S113 P3B.3 — done)
- audience_ids per-turn tagging (P0.S7.2 + S107 — done)

---

## 3. The actual D-E question — what gap remains after D-A through D-D ship?

### 3.1 The current multi-speaker semantic (end-to-end as built)

When 2+ people speak in the same audio buffer:

1. Pyannote diarizes → returns N segments
2. For each segment: voice ID attributes to a pid (or opens new stranger session)
3. Combined transcript: `[A]: hello / [B]: hi`
4. Primary speaker resolved via voice-routing reconciler (`_cur_pid` set to primary)
5. `conversation_turn(text=combined_transcript, person_id=A_pid, ...)` fires ONCE
6. Brain prompt includes:
   - System prompt + `<<<ROOM>>>` block (interleaved per-pid history)
   - `<<<SHARED CONTEXT>>>` block (persistent room scope)
   - The combined transcript itself
7. Brain responds with `[addressing:X]` marker
8. Pipeline parses marker, records `addressed_to=X` in conversation_log
9. κ extraction (if multi-person room): per-participant facts emitted to brain.db
10. Conversation_log row: `person_id=A`, `text=combined_transcript`, `audience_ids=[all_participants]`, `addressed_to=resolved_pid`
11. `_conversation_store._history[A_pid]` gains the turn

### 3.2 The remaining gap (bounded, not wholesale)

**The in-memory `_conversation_store._history[B_pid]` does NOT gain the turn.** B's utterance appears in A's history as part of the combined transcript, NOT in B's own history as a standalone turn.

**Downstream effects of this gap:**
- `<<<ROOM>>>` block Section 3 iterates each active pid's history → B's row shows no entry for the overlapping-speech utterance
- B's per-pid history queries (`search_memory` by Lexi for "what did Lexi say earlier?") miss the overlapping utterance (still surfaces via conversation_log though — that's audience-tagged correctly)
- Cross-session retrieval via SHARED CONTEXT correctly surfaces B's content (audience_ids includes B)

**The gap is bounded to:**
- In-memory `_conversation_store._history[B_pid]` per-pid history (ROOM block Section 3 iteration)
- Overlapping-speech scenarios specifically (natural turn-taking is per-segment, unaffected)

### 3.3 Is this gap load-bearing?

**Honest framing**: this gap matters when B says something in overlapping speech AND a later turn queries B's per-pid history. In practice:
- ROOM block reads `_conversation_store.peek_history(pid)` per active pid — B's row would miss the utterance
- Brain's prompt context for the NEXT turn (when B is speaker) reads `_conversation_store.peek_history(B_pid)` — would miss B's earlier overlapping utterance

**However, downstream redundancy partially covers this:**
- SHARED CONTEXT block (persistent retrieval from conversation_log with audience_ids filter) surfaces B's utterance correctly because audience_ids includes B
- κ extraction wrote facts for both participants
- Brain has full context via the combined transcript that originally went to A

**Whether this matters in real multi-person sessions**: empirical question. Bundled-queue canary will reveal whether brain behavior degrades in overlapping-speech scenarios. If brain misses B's content in follow-up turns, the gap is load-bearing. If brain handles it correctly via SHARED CONTEXT / combined-transcript context, the gap is bounded and acceptable.

---

## 4. Three scope options for auditor adjudication

### 4.1 Option (α) — Full D-E: multi-speaker conversation_turn signature

Scope:
- `conversation_turn` signature gains `additional_speakers: list[tuple[pid, name, content]] = None` parameter
- `run()` collects all diarized speakers (primary + secondary) and passes both
- `conversation_turn` appends EACH speaker's content to their respective pid's `_conversation_store._history`
- `_cur_pid` reduced from "singular primary" to "addressed-by-default for this turn"
- 68-site refactor in `run()` for the dispatch loop restructuring

Effort: ~1-2 days (smaller than auditor's original 3-5 day estimate because Component 3 is already done).

**Architectural value:**
- Closes the in-memory history gap for overlapping speech
- Per-pid history queries always reflect all utterances by that pid
- ROOM block Section 3 shows each participant's true utterance history

**Cost:**
- 68 `_cur_pid` sites in `run()` need contextual review (most are routing decisions that still need a "primary addressed speaker" concept; few need wholesale removal)
- conversation_turn signature change — adds optional param, doesn't break existing callers
- Test impact moderate (conversation_turn has ~50 test sites, but the optional new param doesn't break them)

### 4.2 Option (β) — Defer D-E entirely

Scope: no code change. Recognize that the multi-speaker semantic is delivered via:
- κ extraction (per-participant facts)
- SHARED CONTEXT block (persistent audience-filtered retrieval)
- ROOM block (interleaved per-pid history)
- ADDRESS DECISION marker (brain-side addressee selection)
- N-speaker transcript (combined input)

The remaining gap (in-memory `_conversation_store._history[B_pid]` for overlapping speech) is BOUNDED and OBSERVED via canary. If the bundled-queue canary passes cleanly without surfacing the gap, D-E was correctly absorbed by adjacent migrations.

Effort: ~quarter-day documentation. Same shape as D-D's option (β) had been (which we ultimately rejected in favor of option α consolidation).

**Architectural value:**
- Honest disclosure: most of D-E's value was delivered via D-A through D-D
- Bundled canary stays the test of whether the remaining gap matters
- Frees the 3-5 day budget for other work

**Risk:**
- If bundled canary reveals brain confabulates or misses cross-speaker context in overlapping-speech scenarios, we file D-E as a follow-up (one-cycle delay vs shipping now)

### 4.3 Option (γ) — Targeted fix: per-speaker history append in multi-speaker transcript path

Scope:
- Keep `conversation_turn` singular signature
- Keep `_cur_pid` as turn-dispatch variable
- ADD: in `run()`'s multi-speaker transcript path (the `if len(_diar) >= 2:` branch), after voice-ID per segment, append each speaker's content to their own `_conversation_store._history[their_pid]` BEFORE the singular conversation_turn call fires for the primary
- conversation_turn proceeds unchanged with the combined transcript

Effort: ~half-day. Smallest scope.

**Architectural value:**
- Closes the in-memory history gap (each speaker's per-pid history reflects their own utterances)
- Preserves existing dispatch architecture (no `_cur_pid` removal; no signature change)
- ROOM block Section 3 shows each participant's true history
- Bundled canary tests whether the targeted fix is sufficient

**Cost:**
- One new helper or inline block (~20 LOC) in `run()`'s multi-speaker emit path
- 1-2 tests for the new behavior

**Architect's lean: (γ) targeted fix.** Reasons:
1. Closes the actual identified gap (overlapping-speech per-pid history) at minimum cost
2. Preserves the dispatch architecture (no `_cur_pid` restructuring; lower regression risk)
3. Lets the bundled canary validate whether deeper restructuring is needed
4. If canary reveals deeper gap → full D-E (option α) ships as a follow-up
5. If canary clean → D-E was rightly scoped down; targeted fix was sufficient

(α) is defensible but pays a 1-2 day refactor cost when the gap may already be covered downstream. (β) ships nothing — risky if canary reveals the gap is load-bearing.

---

## 5. Pre-decision flags

### 5.1 Sub-pattern A — NOT 6th instance

Per §1.3: D-E is PARTIAL falsification (1 of 3 components done). Not the wholesale-falsification shape sub-pattern A's strict-read requires. Stays at 5 instances + numbered doctrine.

But the partial-falsification observation IS worth banking. Suggested informal observation:

> *"Partial-falsification finding: D-E's Component 3 was done (ROOM block); Components 1+2 are real but bounded. Multi-component specs where one component is overtaken by adjacent work — banked as candidate informal observation. If 5+ instances accumulate, may surface as `### Multi-component-specs-need-per-component-grep` doctrine. Currently 1 instance (D-E)."*

Architect's lean: don't bank as numbered observation yet. ONE instance is too thin. Auditor adjudicates.

### 5.2 Scope reduction — same pattern as D-D

D-D's actual scope reduced from "5-7 days" to "~1-1.5 days" via Phase 0 grep. D-E's actual scope reduces from "3-5 days" to:
- Option (α): ~1-2 days
- Option (γ): ~half-day
- Option (β): ~quarter-day docs

Pre-audit estimates routinely over-state effort when scope hasn't been grep-verified against current state. **This is the SAME shape as D-D's premise-reset** but stops short of wholesale falsification. Worth noting in §5.1 banking consideration.

### 5.3 Auditor-Q5-estimates-trail-grep — pre-emptive flag

Per architect-memory `feedback_auditor_q5_estimates_trail_grep.md` (2 instances banked), Plan v1's grep should verify the test surface. Pre-emptive estimate for D-E test surface:

- `conversation_turn` test references in test_pipeline.py — ~50-70 sites (high estimate; will grep at Plan v1)
- `_cur_pid` references in test files — uncertain (will grep)
- Multi-speaker transcript tests — exist per S113 P3B.4

Plan v1 grep-verifies and commits to disposition.

---

## 6. D-decisions surfaced (conditional on auditor's scope verdict)

### 6.1 Under option (γ) — targeted fix [architect's lean]

| ID | Topic | Architect's lean |
|---|---|---|
| D1 | Where to add the per-speaker history append | Inside `run()`'s multi-speaker emit path (the `if len(_diar) >= 2:` branch). After voice-ID per segment + BEFORE the singular conversation_turn call. |
| D2 | Helper extraction | NEW module-level helper `_append_per_speaker_history(segments_with_pids)` in pipeline.py. Receives list of (pid, name, segment_text) tuples; calls `_conversation_store.append_turns(pid, [{"role": "user", "content": text, "ts": now, ...}])` per speaker. |
| D3 | Idempotency / dedup | Each segment-text appends ONCE per pid. If primary speaker's text overlaps with their segment (which it does — primary is among the diarized speakers), do NOT double-append; conversation_turn's existing append covers the primary. Per-speaker append fires only for SECONDARY speakers (non-`_cur_pid`). |
| D4 | Test surface (AST + behavioral pair) | AST forward-property: `_append_per_speaker_history` exists at module scope; multi-speaker branch in `run()` calls it. Behavioral: integration test seeds 2-speaker diarization fixture, exercises the path, asserts both pids' histories contain their respective utterances. |
| D5 | Phase decomposition | Phase 1 = helper + run() call site + 2 tests. Phase 2 = AST invariant. Phase 3 = 3 deliberate-regression confirmations. Phase 4 = closure narrative. Smaller phase count than D-D since scope is smaller. |
| D6 | Effort | ~half-day total. |
| D7 | Stage 2 follow-up | None scheduled. Targeted fix is complete in one stage. If bundled canary reveals deeper gap, full D-E (option α) ships as separate follow-up. |
| D8 | Closure narrative banking | Bank that D-E was scoped down from original 3-5 day framing to ~half-day targeted fix based on grep-verified state (Component 3 done; Components 1+2 partially load-bearing). |

### 6.2 Under option (α) — full D-E

(Conditional D-decisions, drafted only if auditor picks α over γ)

| ID | Topic | Architect's lean |
|---|---|---|
| D1' | conversation_turn signature change | Add `additional_speakers: list[tuple[str, str, str]] \| None = None` kwarg (list of (pid, name, segment_text) tuples). Backward-compat: existing callers don't pass it. |
| D2' | Per-pid history append for additional_speakers | Inside conversation_turn, after appending primary speaker's turn, iterate additional_speakers and append each to their own pid's history. |
| D3' | `_cur_pid` semantic rename | Keep variable; rename conceptually from "singular primary" to "addressed-by-default speaker." All 68 reference sites stay; semantic doc clarifies. |
| D4'-D8' | Test surface + phase decomposition + Stage 2 | Similar shape to D-D's two-stage; ~1-2 days. |

### 6.3 Under option (β) — defer entirely

| ID | Topic | Architect's lean |
|---|---|---|
| D1'' | Closure narrative banking | Document: "D-E's Component 3 done via S113 ROOM block; Components 1+2 partially load-bearing. Multi-speaker semantic delivered via D-A through D-D + adjacent components. Bundled canary tests whether remaining gap matters." |
| D2'' | CLAUDE.md "Pending Work" update | Mark D-E "completed-under-different-names" (Component 3) + "partial deferral" (Components 1+2 deferred pending canary observation). |

---

## 7. Effort estimate

| Option | Effort | Phases |
|---|---|---|
| (α) Full D-E | ~1-2 days | 4 phases (similar to D-D) |
| (γ) Targeted fix | ~half-day | 3 phases (smaller than D-D) |
| (β) Defer | ~quarter-day | Documentation only |

**All three options invalidate the original 3-5 day estimate.**

---

## 8. Discipline-count predictions (depends on auditor's scope verdict)

### 8.1 Under option (γ) — closure on D-E

- Spec-first review cycle: 13-for-13 → **14-for-14** on closure
- **Sub-pattern A**: stays at 5 instances (D-E is PARTIAL falsification, not wholesale — doesn't bump the now-numbered doctrine)
- Tripwires-must-match-deferral-surface: stays **4-for-4**
- Developer-improves-on-spec: stays **6-for-6** unless code phase surfaces mechanism improvement
- Induction-surfaces-invariant-gaps: stays **7-for-7**
- Canary-finding tracker: stays at **2 instances**
- Canary-gate override (informal): stays at **1 instance**
- Scope-expansion-via-Phase-0 (informal): stays at **1 instance**
- Deferral-rationale-expires-when-downstream-ships (informal): **stays at 1 instance** OR could bump to **2 instances** if auditor reads D-E's "Component 3 done by S113" as a downstream-ship falsification. Architect's lean: stays at 1 — D-E's Component 3 was overtaken BEFORE the bundled-queue window opened; not strictly "downstream-ship" timing.
- Two-stage-canary-gated-cleanup (informal): stays at **2 instances** (D-E doesn't use two-stage under option γ)
- Auditor-Q5-estimates-trail-grep (informal, architect-memory): TBD on Plan v1 grep

### 8.2 Under option (α) — closure on D-E (full refactor)

Similar to §8.1 but Two-stage-canary-gated-cleanup may bump to **3 instances** if option (α) uses Stage 1 = backward-compat signature + Stage 2 = `_cur_pid` removal post-canary.

### 8.3 Under option (β) — defer

Spec-first review cycle: stays at **13-for-13** (D-E closes as no-code; no spec-first cycle counted). Other counts unchanged.

---

## 9. Threats / risks

1. **Targeted fix (option γ) might be incomplete coverage**: closes in-memory per-pid history gap, but if bundled canary reveals deeper issues (e.g., brain confabulating because conversation_log primary-speaker attribution mistreats overlapping speech), full D-E (option α) ships as follow-up. Bounded risk.

2. **D-E NOT being a sub-pattern A 6th instance** depends on auditor adjudication. If auditor reads "1 of 3 components done" as a wrong-premise pattern, count bumps to 6 in the new doctrine. Strict-read says no; auditor adjudicates.

3. **Bundled canary scope expands** as more architectural items deliver to it. Currently D-A + D-C + D-B + D-D + γ are bundled; D-E adds another item. Risk of "too many variables changed at once for clean attribution if canary fails." Mitigation: targeted fix (option γ) is smallest-blast-radius addition.

4. **Multi-speaker INPUT path (`_format_multispeaker_transcript`) unchanged by D-E** under all 3 options. Pyannote + voice ID + combined transcript stay as-is. D-E only touches what HAPPENS to each segment's pid downstream.

5. **`_conversation_store` is an existing P0.6.3 class** with async mutators + sync peeks. Targeted fix (γ) just calls existing `append_turns` API per pid. No new class machinery.

---

## 10. Auditor verdict requested

1. **§4 scope option** — (α) full, (γ) targeted, (β) defer? Architect's lean: (γ).
2. **§1.3 sub-pattern A adjudication** — partial-falsification counts as 6th instance, or stays at 5 (architect's lean: stays at 5; partial ≠ wholesale)?
3. **§5.1 partial-falsification observation banking** — defer until 5+ instances accumulate, or bank now at 1 instance? Architect's lean: defer.
4. **§9 risk 3 — bundled canary scope expansion** — concern, or acceptable for the small-scope (γ) option?
5. **§5.3 D-E test surface pre-emptive estimate** — anything specific to grep-verify in Plan v1 beyond what's named?

---

## 11. Next steps

1. **Auditor reviews this Phase 0 audit.** Specifically: scope option (α/γ/β); sub-pattern A adjudication; informal-observation banking choice.
2. **D-decisions locked** at Phase 0 sign-off (different D-decision sets for α/γ/β paths).
3. **Plan v1** drafted with locked D-decisions. Plan v1 grep-verifies test surface for chosen option.
4. **Plan v2** if precision items surface.
5. **Joint sign-off** → developer handoff (option α or γ) OR documentation-only close (option β).
6. **Bundled-queue canary** ships after D-E closes (Stage 1 hard-delete for D-C Stage 2 + D-D Stage 2 + γ real-LLM + P0.S7.2 re-canary + D-B + D-D + D-E all-together validation).

---

## 12. Reference documents

- `tests/p0_s7_audit.md` — P0.S7 Phase 0 audit (original D-E scope reference)
- `tests/p0_s7_dd_audit.md` + closure — preceding sibling spec (sub-pattern A 5th instance + doctrine elevation reference)
- `tests/p0_s7_db_audit.md` + closure — preceding sibling spec
- `tests/p0_s7_dc_audit.md` + closure — preceding sibling spec (two-stage pattern reference)
- `CLAUDE.md` `### Phase-0-catches-wrong-premise` doctrine (just elevated 2026-05-19) — applied at §1 hypothesis-testing
- `core/session_state.py:135` — SessionStore (composed dep, unchanged by D-E)
- `core/pipeline_state_store.py:21` — PipelineStateStore (composed dep, unchanged by D-E)
- `core/room_orchestrator.py` — RoomOrchestrator (just shipped via D-D, unchanged by D-E)
- `pipeline.py:4741-4748` — `conversation_turn` signature (D-E target — option α changes; γ leaves intact)
- `pipeline.py:6845-7799` — `run()`'s inner loop with 68 `_cur_pid` references (D-E target — option α restructures; γ leaves intact)
- `pipeline.py:7780-7785` — single `conversation_turn` call site (D-E target under option α)
- `pipeline.py:2974` — `_conversation_store.append_turns` write site (option γ adds a sibling write for additional speakers)
- S113 P3B.1 ROOM block — Component 3 (already done; reference)
- S113 P3B.4 multi-speaker transcript — INPUT path (unchanged)
- P0.S7.2 κ extraction — multi-speaker fact emission (already done)
- P0.S7 D-A SHARED CONTEXT — multi-speaker persistent retrieval (already done)
- Memory: `feedback_spec_time_grep_verification.md` (two-pass) — Pass 1 applied
- Memory: `feedback_ast_forward_property_tests.md` (3 instances) — applied at §6
- Memory: `feedback_auditor_q5_estimates_trail_grep.md` (2 instances) — pre-emptive flag at §5.3

---

**Standing by for auditor verdict on §4 scope + §1.3 adjudication before drafting Plan v1.**
