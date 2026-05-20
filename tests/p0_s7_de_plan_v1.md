# P0.S7.D-E — Multi-speaker per-speaker history append (option γ targeted fix) — Plan v1

**Date:** 2026-05-19
**Author:** architect
**Status:** Plan v1 — locked at option (γ) per auditor verdict 2026-05-19. Standing by for auditor review.

**Companion documents:**
- `tests/p0_s7_de_audit.md` — Phase 0 audit (sub-pattern A NOT bumped; option γ locked)
- `tests/p0_s7_de_plan_v2.md` — forthcoming if precision items surface

**Disciplines applied:**
- **Two-pass grep-verification (Pass 1)**: all function/line references grep-verified 2026-05-19 at drafting. Pass 2 fires at closure.
- **AST forward-property + behavioral workhorse pair**: §6 test design preserves the discipline.
- **Spec-contracts-not-implementations**: D-decisions specify contracts; developer chooses implementation mechanism within them where applicable.
- **`### Phase-0-catches-wrong-premise` doctrine** (CLAUDE.md, just elevated 2026-05-19): sub-pattern A stays at 5 instances; D-E is partial falsification, not a 6th instance.
- **`feedback_partial_falsification_tentative.md`** (architect-memory, 1 instance): banking for D-E only; not promoted to CLAUDE.md doctrine.

---

## 1. Auditor-locked scope (γ targeted fix)

**Auditor verdict 2026-05-19**: LOCK option (γ) targeted fix. HOLD sub-pattern A at 5 instances. DEFER partial-falsification banking to architect-memory only.

**γ scope contract**: close the in-memory `_conversation_store._history[secondary_pid]` gap for overlapping-speech turns. Smallest possible addition that closes the identified gap.

**NOT in scope (deferred to potential future α follow-up post-canary):**
- `conversation_turn` signature change to multi-speaker
- 68-site `_cur_pid` refactor in `run()`'s inner loop
- conversation_log row schema or audience_ids handling changes (P0.S7.2 + S107 already correct)
- Per-speaker conversation_log row writes for non-primaries

**Architectural intent of γ**: each pid's in-memory `_history` row contains content THEY actually spoke (or — for the primary speaker — the combined transcript that conversation_turn emits). After γ ships, every active pid in a multi-speaker turn has at least one row in their per-pid history. The ROOM block Section 3 iteration (per S113 P3B.1) gains complete per-pid coverage.

---

## 2. Pre-Plan grep verification (Pass 1, 2026-05-19)

### 2.1 Multi-speaker emit path shape (production code 2026-05-19)

```python
# pipeline.py:7020-7083 — multi-speaker emit block inside run() inner loop

# Span merging (consecutive same-label spans coalesced)
_spans: list[dict] = []
for _seg in _diar: ...

# Per-span transcription + name resolution
_named_pairs: list[tuple[str | None, str]] = []
for _span in _spans:
    _a = audio_buf[_span["start_sample"]:_span["end_sample"]]
    _t, _ = await _ev_loop.run_in_executor(None, transcribe, _a)
    _t = _t.strip()
    if not _t:
        continue
    _pid_span = _span.get("speaker_id")
    _span_name: "str | None" = None
    if _pid_span is not None:
        _r = db.get_person(_pid_span)
        _span_name = _r["name"] if _r else _pid_span
    _named_pairs.append((_span_name, _t))      # pid NOT preserved in this list

# Multi-speaker text emission
if len(_named_pairs) >= 2:
    text, _preview, _labels = _format_multispeaker_transcript(_named_pairs)
    _multi_speaker_detected = True
    _multi_speaker_labels   = _labels
    print(f"[STT] [{len(_named_pairs)} voices] {_preview}")
    # ... N≥3 guardrail log
```

**Key finding**: `_named_pairs` is `list[tuple[str | None, str]]` — **name + content only**, the pid is dropped on line 7055. γ needs the pid preserved in a parallel structure.

### 2.2 Routing → conversation_turn dispatch (lines 7204-7785)

`_cur_pid` is finalized by the reconciler dispatch block at pipeline.py:7370-7461. After routing, ALL drop-actions (ambiguous / no_action / short_utterance_skip / short_utterance_voice_mismatch / multi_segment_voice_mismatch) `continue` past the turn — `conversation_turn` is NOT invoked. After all `continue` branches, `conversation_turn(text, _cur_pid, _cur_name, db, ...)` fires at pipeline.py:7780-7785.

### 2.3 In-memory history-write semantics

Two paths:
- **KAIROS path** (`_kairos_tick`, pipeline.py:2974): `_conversation_store.append_turns(person_id, [...])` — direct append.
- **`conversation_turn` path** (pipeline.py:4815 → 5776-5794): `history = list(_conversation_store.peek_history(person_id))` (load) → mutate locally → `history.append({"role": "user", "content": text, "ts": now_ts})` and `history.append({"role": "assistant", "content": response, "ts": now_ts, "addressed_to": addressed_to})` → `_conversation_store.set_history(person_id, history)` (write-back).

**`conversation_turn` ALWAYS appends the COMBINED transcript text to `_cur_pid`'s history.** No per-speaker split currently exists.

### 2.4 conversation_log row (persistent, P0.S7.2 + S107)

`db.log_turn(person_id=_cur_pid, role="user", content=text, room_session_id=_room_sid, audience_ids=_audience_ids, ...)` at pipeline.py:5807+ writes ONE row per turn for the primary speaker, with the combined transcript and audience_ids covering all room participants. Secondary speakers retrieve via audience filtering in SHARED CONTEXT (P0.S7 D-A). **γ does NOT modify this path.** Already correct per P0.S7.2 (audience_ids = all room participants) + P0.S7 D-A (cross-session retrieval surfaces via audience filter).

### 2.5 Test surface estimate (auditor's Q5 grep ask)

Grep-verified at Plan v1 drafting:
- `_format_multispeaker_transcript` references in test files: 6 in `test_pipeline.py` (lines 6735, 13322-13454) + 6 in `tests/test_multispeaker_integration.py`
- `conversation_turn` references in `test_pipeline.py`: 111 sites total — vast majority are existing single-speaker behavioral tests; γ does NOT change `conversation_turn` signature so they remain unmodified
- `_append_per_speaker_history`: 0 hits (new helper)
- New tests required for γ: 5-7 (helper unit + AST forward-property + behavioral 2-speaker integration + multi-speaker source-inspection)

**Pre-Plan estimate held within reasonable bounds.** Auditor's Q5 estimate of 3-5 tests was on the low end; actual is 5-7. Banked toward `feedback_auditor_q5_estimates_trail_grep.md` track record (3rd instance, low-by-~30-40%).

---

## 3. Ordering commitment (auditor's specific ask)

**Auditor question**: does `_append_per_speaker_history` run BEFORE or AFTER `_format_multispeaker_transcript`?

**Architect commitment**: helper fires **AFTER** routing's `_cur_pid` finalization AND **AFTER** all routing-action drop-branches (`continue` paths) AND **BEFORE** `conversation_turn` invocation.

**Specifically**:
1. **Collection** (pipeline.py:7044-7055 area): build `_spans_with_pids: list[tuple[str, str, str]]` INLINE alongside `_named_pairs` during the per-span loop. Only include spans where `_pid_span is not None`.
2. **`_format_multispeaker_transcript` invocation** stays at pipeline.py:7060-7061 unchanged — produces combined `text` for primary's conversation_turn.
3. **Routing/reconciler** runs at pipeline.py:7204-7461 — finalizes `_cur_pid` OR drops the turn via `continue`.
4. **`_append_per_speaker_history` helper** fires at NEW location around pipeline.py:7779 (immediately before `conversation_turn` invocation at 7780). Gated on `if _multi_speaker_detected:`.
5. **`conversation_turn` invocation** at pipeline.py:7780-7785 unchanged — appends combined `text` to `_cur_pid`'s history as before.

**Rationale for AFTER-routing ordering**:
- Routing decides which pid is primary for this turn. Helper needs to KNOW primary to skip them (avoids double-write since conversation_turn covers primary with combined transcript).
- Routing also decides whether to drop the turn (`continue` branches). Helper must NOT fire on dropped turns (no-op turn shouldn't write per-speaker history).
- Putting helper AFTER routing also means `_spans_with_pids` is referenced ~7 lines after build; small lexical distance, no scope hazard.

**Rationale for BEFORE conversation_turn**:
- conversation_turn does its own write to `_cur_pid`'s history (combined transcript). Helper for non-primaries fires independently — no ordering dependency in either direction (they touch DIFFERENT pids' histories).
- Putting helper BEFORE conversation_turn gives clean attribution if anything goes wrong in either path.

---

## 4. audience_ids handling commitment (auditor's specific ask)

**Auditor question**: does the targeted fix need to update `audience_ids` handling? §1.2 of the audit said "audience_ids is already correct via P0.S7.2 + S107 — verify this holds for the per-speaker in-memory append path."

**Architect commitment**: NO change to audience_ids handling. Verified:

- `_conversation_store._history` is a `dict[str, list[dict]]` (pid → message list). Messages have `role`, `content`, `ts`, `addressed_to` keys. **No `audience_ids` field.** In-memory per-pid history is INHERENTLY scoped to that pid by the dict key — there's no audience filtering at retrieval (callers `peek_history(pid)` get only that pid's messages).
- The persistent `conversation_log` table HAS `audience_ids` (S107 Phase 3A.6) and HAS `room_session_id` (S107 Phase 3A.6). The row is written at pipeline.py:5807+ inside `conversation_turn`, ONCE per turn for the primary speaker, with the combined transcript and audience_ids covering all room participants.
- Secondary speakers retrieve content via `db.get_recent_room_conversation(room_session_id, requester_pid, best_friend_id)` (P0.S7 D-A) — this query filters conversation_log rows by `audience_ids` JSON containment. Secondary speakers ALREADY surface the combined-transcript content via SHARED CONTEXT block.
- γ helper writes to in-memory store ONLY. No conversation_log row writes. No audience_ids touched.

**Invariant preserved**: persistent retrieval is unchanged. In-memory `_conversation_store._history` gains per-speaker rows for non-primaries (in addition to primary's combined-transcript row that conversation_turn writes).

---

## 5. D-decisions (option γ branch)

### 5.1 D1 — Helper module location + naming

**Decision**: new module-level helper `_append_per_speaker_history` in `pipeline.py`. Place near existing helpers like `_resolve_addressed_to` (pipeline.py:1077 area, alongside `_format_multispeaker_transcript`). Pure Python; no class membership.

**Rationale**: keeps multi-speaker concerns colocated. `_format_multispeaker_transcript` is the INPUT-side helper; `_append_per_speaker_history` is the OUTPUT-side helper for the same path.

### 5.2 D2 — Helper signature contract

**Contract (developer chooses precise signature within these constraints)**:

```python
def _append_per_speaker_history(
    spans_with_pids: "list[tuple[str, str, str]]",
    primary_pid: "str | None",
    now_ts: float,
) -> None:
    """γ targeted fix — append each non-primary speaker's segment text to
    their own _conversation_store._history.

    Primary speaker's history is appended by conversation_turn with the
    combined transcript (existing behavior unchanged). This helper covers
    SECONDARY speakers whose in-memory history would otherwise miss the
    overlapping-speech utterance.

    Called only when _multi_speaker_detected=True. Dedups same-pid spans
    (consecutive merged spans may share the same pid). Skips entries with
    None pid or empty content.
    """
```

**Invariants the contract enforces**:
- Skip rows where `pid is None` (voice ID failed for that span; can't append to unknown pid's history)
- Skip rows where `content` is empty/whitespace (defensive — `_named_pairs` already filters empty, but helper guards against future regressions)
- Skip rows where `pid == primary_pid` (conversation_turn covers primary)
- Dedup within the call (`seen_pids: set[str]`) — if a single pid has multiple non-merged spans (rare; span-merger at pipeline.py:7020-7036 normally coalesces them), append only ONCE with the first non-empty content
- Use `_conversation_store.append_turns` (the existing P0.6.3 async API) — fire-and-forget via `asyncio.get_running_loop().create_task(...)` matching the existing pattern at pipeline.py:2974

**Note on dedup choice**: spans for the same pid are already merged by the span-merger loop at pipeline.py:7020-7036 (consecutive same-label spans coalesce into one span entry). So `seen_pids` dedup is belt-and-braces against a future regression in the merger or a non-consecutive-same-pid scenario (which doesn't occur in current code shape). Developer may simplify to no dedup if they verify the merger invariant, but the contract permits dedup.

### 5.3 D3 — Collection point + plumbing

**Decision**: build `_spans_with_pids: list[tuple[str, str, str]]` INLINE inside the per-span loop at pipeline.py:7044-7055. Add the entry only when `_pid_span is not None`:

```python
_spans_with_pids: list[tuple[str, str, str]] = []  # NEW

for _span in _spans:
    _a = audio_buf[_span["start_sample"]:_span["end_sample"]]
    _t, _ = await _ev_loop.run_in_executor(None, transcribe, _a)
    _t = _t.strip()
    if not _t:
        continue
    _pid_span = _span.get("speaker_id")
    _span_name: "str | None" = None
    if _pid_span is not None:
        _r = db.get_person(_pid_span)
        _span_name = _r["name"] if _r else _pid_span
        _spans_with_pids.append((_pid_span, _span_name, _t))   # NEW
    _named_pairs.append((_span_name, _t))
```

**Rationale**: the per-span loop already iterates `_spans` with all relevant data in scope. Adding a parallel append is ~2 lines; no separate iteration needed. `_spans_with_pids` lives in the inner-loop iteration scope; consumed at the helper call site ~700 lines later but within the same `while True:` iteration.

### 5.4 D4 — Helper call site

**Decision**: at pipeline.py:7779 (immediately before `await conversation_turn(...)`), add:

```python
if _multi_speaker_detected:
    _append_per_speaker_history(
        _spans_with_pids,
        primary_pid=_cur_pid,
        now_ts=time.time(),
    )

result, extra = await conversation_turn(
    text, _cur_pid, _cur_name, db,
    ...
)
```

**Rationale**:
- Gated on `_multi_speaker_detected` so single-speaker turns pay zero cost (no extra helper call, no zero-length list iteration).
- After all routing-action drop branches (the `continue` paths at pipeline.py:7461-7494): helper only fires for turns that actually reach `conversation_turn`.
- Before `conversation_turn`: clean attribution if anything in either path raises.
- `now_ts = time.time()` matches the convention at pipeline.py:5775 (`_now_ts = time.time()` inside `conversation_turn` for primary's history rows).

### 5.5 D5 — Idempotency + edge cases

**Contract (developer enforces in helper body)**:
- Empty `spans_with_pids` → no-op. Helper returns immediately.
- `primary_pid is None` → all spans treated as non-primary (no skip). Edge case: primary pid is None when `_cur_pid` was unresolved at routing time. Possible but rare. Helper writes all entries to their respective histories.
- All spans match `primary_pid` → no writes (helper iterates and skips all). No-op.
- `_conversation_store` mutations are fire-and-forget via `create_task` (matches existing pattern at pipeline.py:2974). Helper does NOT `await` the writes — keeps it sync-callable from the inner loop's sync code.

**Concurrency note**: `_conversation_store.append_turns(pid, ...)` is async + thread-safe per P0.6.3 (lock-protected). Fire-and-forget tasks complete asynchronously; the next turn's `peek_history(pid)` will see the appended rows even if the task hasn't completed by the time `conversation_turn` returns. No ordering hazard.

### 5.6 D6 — Test surface (AST forward-property + behavioral workhorse pair)

**Total tests: 5-7. Phase breakdown:**

**Phase 1 — helper + collection + call site (3-4 tests)**:
1. `test_append_per_speaker_history_basic` — calls helper with 2 spans (primary + secondary), asserts `_conversation_store.peek_history(secondary_pid)` gains the secondary's content + `peek_history(primary_pid)` is unchanged.
2. `test_append_per_speaker_history_dedups_same_pid` — calls helper with 3 spans where 2 share the same pid (non-primary), asserts the secondary's history gains exactly ONE row (dedup).
3. `test_append_per_speaker_history_skips_empty_and_none_pid` — helper handles edge cases: `pid=None`, `content=""`, `content="   "` — none produce writes.
4. `test_spans_with_pids_collected_in_multispeaker_emit` — AST forward-property: scan pipeline.py inner-loop multi-speaker block, assert `_spans_with_pids` variable is initialized + appended-to inside the per-span loop.

**Phase 2 — AST invariant (1 test)**:
5. `test_append_per_speaker_history_called_from_multispeaker_emit_path` — AST forward-property: scan `run()` for `_append_per_speaker_history(` call, assert exactly ONE invocation site, gated on `_multi_speaker_detected`, located BEFORE the `conversation_turn(` invocation.

**Phase 3 — behavioral integration (1-2 tests)**:
6. `test_multispeaker_turn_appends_each_speaker_to_own_history` — seed 2-speaker diarization fixture (Jagan primary + Lexi secondary), exercise the full multi-speaker emit path + helper + conversation_turn, assert Jagan's history has the combined transcript row AND Lexi's history has Lexi's segment-text-only row.
7. `test_singlespeaker_turn_does_not_invoke_helper` — single-speaker turn (`_multi_speaker_detected=False`) does NOT call `_append_per_speaker_history`. Source-inspection or behavioral.

**Phase 4 — deliberate-regression confirmations (NOT new tests; verification step)**:
- (a) Drop the `if _multi_speaker_detected:` gate → singlespeaker test fails (regression: helper fires on solo turns).
- (b) Drop the `if pid == primary_pid: continue` skip in helper → primary-history double-write test (new assertion in test #1: primary's row count unchanged after helper call).
- (c) Drop the `_spans_with_pids.append(...)` line in collection → Phase 2 AST invariant fails.

Confirmation (b) requires a refined version of test #1 that asserts primary's history row count BEFORE and AFTER helper call (delta == 0). Will surface in Phase 1 implementation if not already implicit.

### 5.7 D7 — Phase decomposition

**Phase 1** — Helper definition + `_spans_with_pids` collection + call site wiring + 4 tests (helper unit + AST collection). ~3 hours.
**Phase 2** — AST invariant for helper call site (1 test). ~0.5 hours.
**Phase 3** — Behavioral integration (1-2 tests). ~1 hour.
**Phase 4** — Deliberate-regression confirmations (3 confirmations: gate, primary-skip, collection). ~0.5 hours.

**Total: ~half-day** (4-5 hours). Matches §7 audit estimate.

### 5.8 D8 — Stage 2 follow-up disposition

**Decision**: NONE scheduled. γ is complete in one stage.

**Rationale**:
- Targeted fix closes the identified in-memory history gap fully.
- No flag-gate or shim layer needed (helper is additive, not replacing existing logic).
- Bundled-queue canary validates whether the targeted fix is sufficient.
- If canary reveals deeper gaps (e.g., brain confabulates secondary content because conversation_log primary-speaker attribution mistreats overlap), full D-E (option α) ships as a separate post-canary follow-up. Not bundled with γ; clean attribution preserved.

**Not a Stage 1**: γ does NOT use the two-stage canary-gated cleanup pattern (D-C + D-D). γ is a single-stage targeted fix. Two-stage pattern stays at 2 instances (D-C + D-D); γ does not bump it.

### 5.9 D9 — Closure narrative banking

**Banking targets for closure (Phase 4 step)**:
- Scope reduction documented: D-E framed 3-5 days → grep-verified to ~half-day under γ scope after Phase 0 identified Component 3 already done (S113 P3B.1) + Components 1+2 partially bounded.
- Partial-falsification observation: bank 1st instance in `feedback_partial_falsification_tentative.md` (architect-memory only; NOT CLAUDE.md per auditor verdict).
- Sub-pattern A: STAYS at 5 instances (D-E does NOT bump — partial ≠ wholesale).
- Two-stage pattern: STAYS at 2 instances (γ is single-stage).
- Auditor-Q5-estimates-trail-grep: 3rd instance (architect-memory) — auditor's Q5 was 3-5 tests, actual is 5-7. Low-by-30-40%, banked toward potential 5+ doctrine.
- Bundled canary scope expanded: D-A + D-C + D-B + D-D + D-E + γ (P0.S7.4) all-together validation per the existing trigger.
- Pending Work line in CLAUDE.md: add D-E Stage 2 follow-up (potential full α refactor IF canary reveals deeper gap; NOT scheduled unless evidence).

---

## 6. Stage Stage 1 only (no Stage 2)

γ is a single-stage targeted fix. Bundled-queue canary validates. On PASS: D-E closes; no follow-up. On FAIL with γ-related root cause: file full α refactor as separate post-canary spec.

Combined PR candidates already scheduled:
- D-C Stage 2 (hard-delete `_build_cross_person_excerpts` + flag)
- D-D Stage 2 (hard-delete RoomOrchestrator shim layer + migrate 130 test sites)
- D-E does NOT add a Stage 2 to this combined PR.

---

## 7. Risk + mitigation

### 7.1 Risk — γ might not close the gap fully

**Hypothesis**: in-memory per-pid history append is the right level. SHARED CONTEXT block + κ extraction handle persistence + cross-session retrieval. Combined transcript on primary's row preserves context for brain.

**Mitigation**: bundled canary observes brain behavior on overlapping-speech turns. If brain still confabulates secondary content (e.g., gets attribution wrong because primary's row has combined text), the gap is deeper than γ scope and full α refactor ships as follow-up.

**Acceptance criterion (canary observation)**: in a 2-speaker overlap scenario, on follow-up turns brain correctly recalls who said what without confabulation. ROOM block Section 3 shows each speaker's content under their own name.

### 7.2 Risk — bundled canary attribution complexity

**Concern**: 6+ items bundled (D-A + D-C Stage 1 + D-B + D-D Stage 1 + γ + D-E). If overlapping-speech turn produces a bug, attribution is muddled.

**Mitigation**: γ's helper is named `_append_per_speaker_history` and lives on a clean attribution path. If bug stack trace includes the helper → attribute to D-E. If bug is in `_format_multispeaker_transcript` (S113 P3B.4 unchanged) or κ extraction (P0.S7.2 unchanged) or SHARED CONTEXT (D-A) → attribute elsewhere. γ's ~20 LOC has the smallest attribution footprint of any bundled item.

### 7.3 Risk — primary speaker's history row contains content they didn't say

**Concern**: `conversation_turn`'s history.append uses the COMBINED transcript text for `_cur_pid`'s row. In a 2-speaker turn where Jagan says "hi" and Lexi says "hello", Jagan's history row contains `[Jagan]: hi / [Lexi]: hello` not just "hi".

**Disposition**: this is EXISTING behavior, NOT a γ regression. γ adds Lexi-only content to Lexi's history; γ does NOT modify primary's row content. The "primary's row has combined text" property predates γ (Session 3B.4 + P0.S7.2). Acceptable per the architectural model that primary is the addressed speaker for the turn — combined transcript IS what brain answered.

**Future consideration (NOT γ scope)**: option α would split primary's row to primary-only content + secondary rows. Larger refactor; not in γ.

### 7.4 Risk — concurrent writes via fire-and-forget tasks

**Concern**: helper calls `_conversation_store.append_turns(pid, ...)` via `create_task` (fire-and-forget). Could a subsequent `peek_history(pid)` see the partial state?

**Disposition**: `_conversation_store` is P0.6.3 lock-protected. `append_turns` is atomic. Next turn's `peek_history(pid)` sees the appended row in full (or sees the pre-append state — never partial). The fire-and-forget pattern matches existing usage at pipeline.py:2974 (KAIROS path) which has the same atomicity guarantee.

---

## 8. Discipline-count predictions on D-E closure

| Discipline | Status |
|---|---|
| Spec-first review cycle | 13-for-13 → **14-for-14** on closure |
| Sub-pattern A (`### Phase-0-catches-wrong-premise`) | **stays at 5 instances** (D-E partial; not wholesale) |
| Tripwires-must-match-deferral-surface | stays **4-for-4** (γ has no deferral tripwire) |
| Developer-improves-on-spec | stays **6-for-6** unless code phase surfaces a mechanism improvement |
| Induction-surfaces-invariant-gaps | stays **7-for-7** unless Phase 4 surfaces a real gap |
| Canary-finding tracker | stays at **2 instances** (D-E not canary-surfaced) |
| Canary-gate override (informal) | stays at **1 instance** |
| Scope-expansion-via-Phase-0 (informal) | stays at **1 instance** (D-E scope SHRUNK, didn't expand) |
| Deferral-rationale-expires-when-downstream-ships (informal) | stays at **1 instance** (D-E's Component 3 overtake happened outside bundled-queue window) |
| Two-stage-canary-gated-cleanup (informal) | stays at **2 instances** (γ is single-stage) |
| Auditor-Q5-estimates-trail-grep (architect-memory) | **3rd instance** (test count low-by-~30-40%) |
| Partial-falsification-tentative (architect-memory only, NOT CLAUDE.md) | **1st instance** banked at architect-memory |

---

## 9. Plan v1 → Plan v2 anticipated precision items

Reviewer may surface:
1. **D2 / D5 contract precision** — exact helper signature shape: should `now_ts` be a kwarg or required positional? Should `spans_with_pids` be the only positional or also keyword? Plan v2 commits to the developer-facing signature.
2. **D6 test surface refinement** — auditor may want additional behavioral coverage (e.g., 3-speaker turn with primary + 2 secondaries, asserting each gets their own row). Plan v2 expands test #6 to N-speaker if requested.
3. **D5 dedup precision** — Plan v2 may commit to "dedup is mandatory" or "dedup is optional belt-and-braces" based on auditor's read of span-merger invariant.
4. **D4 call-site granularity** — Plan v2 may specify the helper call should fire INSIDE a try/except (defensive: helper bug shouldn't crash conversation_turn dispatch). Or may rule that the helper is reliable enough to fire without a wrapper.

None of these are blockers; Plan v2 anticipated to be 1-2 page refinement.

---

## 10. Next steps

1. **Auditor reviews Plan v1**. Adjudicates D2 / D5 / D6 / D4 precision items (if any).
2. **Plan v2** drafted if precision items surface (likely 1-2 small items).
3. **Joint sign-off** on Plan v2 → developer handoff.
4. **Developer ships** Phase 1 (helper + collection + call site + 4 tests) → Phase 2 (AST invariant) → Phase 3 (behavioral integration) → Phase 4 (deliberate-regression confirmations + closure narrative).
5. **Closure** banked with discipline counts per §8.
6. **Bundled-queue canary** runs with γ included. D-E observation = brain handles overlapping-speech turns correctly per §7.1 acceptance criterion.

---

## 11. Reference documents

- `tests/p0_s7_de_audit.md` — Phase 0 audit (sub-pattern A NOT bumped; partial falsification noted)
- `tests/p0_s7_dd_audit.md` + closure — D-D shipped 2026-05-19 (RoomOrchestrator; sub-pattern A 5th instance + doctrine elevation)
- `tests/p0_s7_db_audit.md` + closure — D-B shipped (Kuzu v3 schema bump)
- `tests/p0_s7_dc_audit.md` + closure — D-C Stage 1 shipped (flag-gate, two-stage pattern 1st instance)
- `CLAUDE.md` `### Phase-0-catches-wrong-premise` doctrine (just elevated 2026-05-19) — applied at §1
- `pipeline.py:1077-1170` — `_format_multispeaker_transcript` helper (S113 P3B.4, unchanged by γ)
- `pipeline.py:7020-7083` — multi-speaker emit block (γ adds `_spans_with_pids` collection inline)
- `pipeline.py:7370-7461` — routing/reconciler dispatch (γ does not touch)
- `pipeline.py:7779-7785` — `conversation_turn` invocation (γ adds helper call immediately before)
- `pipeline.py:2974` — KAIROS `append_turns` reference (γ helper matches this fire-and-forget pattern)
- `pipeline.py:5775-5794` — `conversation_turn`'s history-append (primary's combined-transcript row; unchanged)
- `core/conversation_store.py` — P0.6.3 ConversationStore with async append_turns + lock protection
- S107 Phase 3A.6 conversation_log schema — `room_session_id`, `audience_ids` columns (γ does not touch persistence path)
- P0.S7.2 κ extraction — per-participant facts (already delivers multi-speaker semantic at brain.db level)
- P0.S7 D-A SHARED CONTEXT block — cross-session retrieval via audience_ids (already correct)
- S113 P3B.1 ROOM block — Component 3 of original D-E framing (already done; γ's per-pid append closes the in-memory feeder gap)
- S113 P3B.3 ADDRESS DECISION marker — `addressed_to` field handling (unchanged)
- S113 P3B.4 N-speaker transcript — multi-speaker INPUT format (γ does not touch)
- Memory: `feedback_spec_time_grep_verification.md` (two-pass) — Pass 1 applied at §2; Pass 2 at closure
- Memory: `feedback_ast_forward_property_tests.md` (3 instances) — applied at §5.6 D6
- Memory: `feedback_auditor_q5_estimates_trail_grep.md` (2 instances; D-E will be 3rd)
- Memory: `feedback_partial_falsification_tentative.md` (1 instance, tentative; banked at D-E closure)

---

**Standing by for auditor review of Plan v1. Anticipated precision items per §9.**
