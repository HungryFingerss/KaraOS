# P0.S7.D-E — Plan v2 (final, joint sign-off cleared 2026-05-19)

**Date:** 2026-05-19
**Author:** architect
**Status:** Plan v2 — APPROVED by auditor 2026-05-19. Joint sign-off cleared. Code phase ready. Developer handoff package.

**Preceding documents:**
- `tests/p0_s7_de_audit.md` — Phase 0 audit (sub-pattern A held at 5; option γ locked)
- `tests/p0_s7_de_plan_v1.md` — Plan v1 (APPROVED 2026-05-19 with 4 precision items)
- This document — Plan v2 (locks all 4 precision items + OBS A; final spec for developer)

---

## Summary — auditor's 4 precision items + 1 observation

| Item | Severity | Disposition |
|---|---|---|
| MEDIUM 1 — Dedup MANDATORY in helper contract | MEDIUM | LOCKED as mandatory in D5 contract |
| MEDIUM 2 — try/except wrapper at helper call site | MEDIUM | LOCKED at call site per D4 |
| MEDIUM 3 — Test 6 parametrize over N ∈ {2, 3} | MEDIUM | LOCKED — Phase 3 test surface = tests 7a + 7b |
| LOW 1 — Test 1 explicit primary-no-double-write delta assertion | LOW | LOCKED in D6 test 1 spec |
| OBS A — `_spans_with_pids` scope hazard | non-blocking | ADOPTED — Phase 2 AST invariant added |

**All 4 precision items match the architect's §9 anticipation in Plan v1 — discipline-system in sync.**

---

## 1. MEDIUM 1 — Dedup MANDATORY (D5 contract precision)

### 1.1 Plan v1 §5.2 said (rejected)

> "Developer may simplify to no dedup if they verify the merger invariant, but the contract permits dedup."

### 1.2 Plan v2 locks (MANDATORY)

**Dedup is MANDATORY in the helper contract.** The helper MUST maintain a `seen_pids: set[str]` across the single invocation and SKIP any pid already appended in this call.

### 1.3 Rationale (auditor verdict adopted)

1. **Inverse-check discipline (P0.5 precedent)**: if a future refactor changes the span-merger at pipeline.py:7020-7036 and breaks the consecutive-same-label invariant, the helper's dedup catches the silent regression. Without it, the merger regression silently produces duplicate per-speaker history rows.
2. **Local invariant > upstream dependency**: "each speaker gets ONE history row per multi-speaker turn" is cleaner as a helper-enforced invariant than a property contingent on upstream behavior. The helper's `seen_pids: set[str]` is ~3 lines of Python; architectural cleanliness is worth it.

### 1.4 Updated helper contract (D5 final)

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

    Invariants (MANDATORY, helper-enforced):
      - Skip rows where pid is None (voice ID failed).
      - Skip rows where content is empty/whitespace-only.
      - Skip rows where pid == primary_pid (conversation_turn covers primary).
      - DEDUP same-pid spans within the call via seen_pids: set[str]
        (each speaker gets at most ONE history append per multi-speaker turn).
    """
```

### 1.5 Test 2 reframed

Test 2 (`test_append_per_speaker_history_dedups_same_pid`) is no longer "belt-and-braces" — it is the **structural guarantee of the helper contract**. Test surface unchanged; semantic upgraded.

---

## 2. MEDIUM 2 — try/except wrapper at helper call site (D4 precision)

### 2.1 Plan v1 §9 anticipated; Plan v2 locks

**The helper call MUST be wrapped in try/except at the call site.** Helper failures log + continue. `conversation_turn` dispatch is NEVER interrupted by helper bugs.

### 2.2 Rationale (auditor verdict adopted)

1. `conversation_turn` is the critical user-facing dispatch path. Helper bugs (e.g., pid not recognized by conversation_store, unanticipated exception in `create_task` wrapping) MUST NOT cascade into "user's turn crashes."
2. Helper is best-effort observability/UX-improvement. Per-speaker history append is not load-bearing for the user's turn to complete — combined transcript path (existing `conversation_turn`) carries the actual content the brain responds to. If the helper fails on one turn, that turn just misses the in-memory append; canary catches degraded behavior.
3. Consistent with `safe_emit_sync` pattern from P0.0.7 Step 5 (developer-improves-on-spec instance from CLAUDE.md). Same shape: best-effort side-effect helper wrapped at the call site with a single annotated except.

### 2.3 Updated call site (D4 final)

At pipeline.py:7779 (immediately before `await conversation_turn(...)`):

```python
if _multi_speaker_detected:
    try:
        _append_per_speaker_history(
            _spans_with_pids,
            primary_pid=_cur_pid,
            now_ts=time.time(),
        )
    except Exception as _aps_e:
        print(
            f"[Pipeline] _append_per_speaker_history failed: "
            f"{type(_aps_e).__name__}: {_aps_e!r}"
        )  # OPTIONAL: best-effort observability

result, extra = await conversation_turn(
    text, _cur_pid, _cur_name, db,
    vision_state=_vision_state,
    voice_state=_voice_state,
    prompt_addendum_override=_addendum_override,
)
```

### 2.4 Note on wrapper scope

The try/except catches SYNCHRONOUS errors raised by the helper (e.g., helper raises before any `create_task` dispatch, or `create_task` itself raises). ASYNC task failures inside `_conversation_store.append_turns(...)` are isolated by `create_task` itself (fire-and-forget; failure surfaces in the asyncio task exception log, not the caller). This is the same isolation contract as the KAIROS pattern at pipeline.py:2974.

Log line `[Pipeline] _append_per_speaker_history failed: {Type}: {repr}` is annotated `# OPTIONAL` per the P0.4 silent-except policy — failure path is best-effort observability, not load-bearing.

---

## 3. MEDIUM 3 — Phase 3 test parametrize over N ∈ {2, 3} (D6 precision)

### 3.1 Plan v1 §5.6 D6 said (insufficient)

Phase 3 behavioral integration: 2-speaker diarization fixture. Single case.

### 3.2 Plan v2 locks (parametrize)

**Phase 3 test parametrizes over N ∈ {2, 3}** (final test numbering per §6.3 = tests 7a + 7b after Phase 2 added tests 5 + 6):

- **7a (N=2)**: Jagan primary + Lexi secondary → Lexi gains 1 row, Jagan's row count unchanged (delta == 0). Validates the 2-speaker case (S113 P3B.4 legacy `[Name]: text\n[Name]: text` format path).
- **7b (N=3)**: Jagan primary + Lexi secondary + Priya secondary → BOTH Lexi AND Priya gain 1 row each, Jagan's row count unchanged. Validates the N≥3 case (S113 P3B.4 `[N voices simultaneously]` block path) and confirms the helper handles `len(spans_with_pids) > 2` correctly.

### 3.3 Rationale (auditor verdict adopted)

N=2 and N≥3 take structurally distinct paths through `_format_multispeaker_transcript` per S113 P3B.4 (different header formats). γ's helper iterates `_spans_with_pids` independently of the transcript format, but the test surface should explicitly cover both N=2 and N≥3 to lock the invariant "each non-primary gets their own row regardless of N."

Cost: ~30 LOC test addition (parametrize fixture). Worth it for N-speaker coverage assurance.

### 3.4 Plan v2 test count update

Plan v1 estimate: 5-7 tests (auditor estimate 3-5).
Plan v2 lock: **8 tests** (Phase 1 +4, Phase 2 +2, Phase 3 +2).

Auditor-Q5-estimates-trail-grep 3rd instance updated: original estimate 3-5; Plan v2 actual 8. Low-by-~60%. Banked at architect-memory.

---

## 4. LOW 1 — Test 1 explicit primary-no-double-write delta assertion (D6 precision)

### 4.1 Plan v1 §6.4 Phase 4 confirmation (b) said (deferred)

> "Confirmation (b) requires a refined version of test #1 that asserts primary's history row count BEFORE and AFTER helper call (delta == 0). Will surface in Phase 1 implementation if not already implicit."

### 4.2 Plan v2 locks (explicit)

**Test 1 explicitly asserts before/after row-count deltas for BOTH primary and secondary.** No deferral to implementation.

### 4.3 Updated test 1 spec (D6 final)

```python
async def test_append_per_speaker_history_basic():
    # Setup: 2 active sessions with seeded history
    primary_pid = 'jagan_001'
    secondary_pid = 'lexi_001'
    await _conversation_store.init_empty(primary_pid)
    await _conversation_store.init_empty(secondary_pid)
    # Seed primary with N existing rows (turn history exists)
    await _conversation_store.append_turns(primary_pid, [
        {"role": "user", "content": "hi", "ts": time.time()},
    ])
    primary_count_before = len(_conversation_store.peek_history(primary_pid))
    secondary_count_before = len(_conversation_store.peek_history(secondary_pid))

    spans_with_pids = [
        (primary_pid, 'Jagan', 'hi'),
        (secondary_pid, 'Lexi', 'hello'),
    ]
    _append_per_speaker_history(spans_with_pids, primary_pid=primary_pid, now_ts=time.time())

    # Wait for fire-and-forget create_task to complete
    await asyncio.sleep(0)

    # Primary's row count UNCHANGED (helper skipped primary)
    assert len(_conversation_store.peek_history(primary_pid)) == primary_count_before, (
        "Helper must NOT append to primary_pid's history; conversation_turn covers primary"
    )
    # Secondary's row count INCREASED by exactly 1
    assert len(_conversation_store.peek_history(secondary_pid)) == secondary_count_before + 1
    # Secondary's appended row has the correct content
    secondary_history = _conversation_store.peek_history(secondary_pid)
    assert secondary_history[-1]["content"] == "hello"
    assert secondary_history[-1]["role"] == "user"
```

### 4.4 Rationale

The before/after delta assertion is the **structural guarantee** for primary-no-double-write. Locking it into test 1 explicitly (rather than deferring to "will surface in implementation") prevents the helper's primary-skip invariant from drifting under future refactors.

---

## 5. OBS A — `_spans_with_pids` scope hazard (Phase 2 AST invariant)

### 5.1 Auditor's observation (non-blocking)

> "`_spans_with_pids` is built inside the per-span loop and consumed ~700 lines later at the helper call site. Both are within the SAME `while True:` iteration of `run()`'s inner loop, so the variable is reachable. But the lexical distance is large. If a future refactor introduces a new `continue` branch BETWEEN the collection (line 7044-7055) and the helper call (line 7779), the helper might fire with stale or empty `_spans_with_pids`."

### 5.2 Architect's adoption (YES, add Phase 2 AST invariant)

**Add the forward-property AST invariant in Phase 2.** Cheap (~1 test), closes a real future-refactor hazard, fits the AST-forward-property-as-workhorse discipline (3 instances banked).

### 5.3 New Phase 2 AST invariant test spec

```python
def test_spans_with_pids_lifetime_within_multispeaker_iteration():
    """AST forward-property: in run()'s inner loop, _spans_with_pids is
    initialized inside the multi-speaker emit block AND consumed at the
    _append_per_speaker_history call site WITHOUT any reset/reassignment
    in between (which would silently break the helper's contract).

    Forward-property: scan run()'s body. Find every Name(id='_spans_with_pids')
    assignment + every _append_per_speaker_history(_spans_with_pids, ...) call.
    Assert each call's _spans_with_pids reference has a prior assignment in
    the SAME iteration scope without an intervening reset.
    """
```

Implementation: AST walk `run()`'s body; collect line numbers of `_spans_with_pids = ...` assignments and `_append_per_speaker_history(_spans_with_pids, ...)` calls; assert the most recent assignment before each call is the inline initialization at the multi-speaker emit block (lineno ~7043) and there's no intervening reset (assignment of `_spans_with_pids` to something else) between them.

### 5.4 Discipline framing

This is preventive hardening, not catching a current bug. Same shape as P0.0's S2 dashboard tripwire (closes a future-refactor surface) and P0.11's `_persistent` AST tripwires (closes a future-refactor hazard). The fact that current code is safe is the right time to ship the invariant — locks the property BEFORE it can drift.

---

## 6. Updated D-decisions (Plan v2 final, supersedes Plan v1 §5)

| ID | Plan v1 disposition | Plan v2 lock |
|---|---|---|
| D1 | Module-level helper colocated with `_format_multispeaker_transcript` | UNCHANGED |
| D2 | Helper signature contract | UNCHANGED (positional + kwargs mix is conventional) |
| D3 | `_spans_with_pids` collected inline in per-span loop | UNCHANGED |
| D4 | Helper call site at pipeline.py:7779 | **UPDATED — try/except wrapper REQUIRED** (MEDIUM 2) |
| D5 | Idempotency + edge cases (dedup optional) | **UPDATED — dedup MANDATORY** (MEDIUM 1) |
| D6 | 5-7 tests | **UPDATED — 8 tests; Phase 3 test parametrized + test 1 delta assertion explicit** (MEDIUM 3 + LOW 1) |
| D7 | 4 phases, ~half-day | UNCHANGED (small additions absorb into existing phases) |
| D8 | No Stage 2 | UNCHANGED |
| D9 | Closure narrative banking | UNCHANGED with auditor-Q5 3rd-instance estimate update (3-5 → 8 actual; ~60% low-by) |
| **D10 (NEW)** | — | **NEW — Phase 2 AST invariant test for `_spans_with_pids` scope hazard** (OBS A) |

### 6.1 Phase decomposition (Plan v2 final)

**Phase 1** — Helper definition + `_spans_with_pids` collection + try/except call-site wiring + 4 tests (test 1 with explicit delta + test 2 mandatory dedup + test 3 edge cases + test 4 collection AST). ~3.5 hours.
**Phase 2** — 2 AST invariants (test 5 helper-call-site + test 6/D10 spans-with-pids-scope-lifetime). ~0.5 hours.
**Phase 3** — Behavioral integration parametrized over N ∈ {2, 3} (tests 7a + 7b). ~1 hour.
**Phase 4** — Deliberate-regression confirmations (4 confirmations: gate, primary-skip, collection, dedup) + closure narrative. ~0.5 hours.

**Total Plan v2: ~5.5 hours** (still half-day; small additions absorb).

### 6.2 Phase 4 deliberate-regression confirmations updated

Plan v1 had 3 confirmations. Plan v2 locks **4**:

- **(a)** Drop `if _multi_speaker_detected:` gate at call site → singlespeaker test fails (helper fires when it shouldn't).
- **(b)** Drop `if pid == primary_pid: continue` skip in helper → test 1 fails on `delta(primary) == 0` assertion.
- **(c)** Drop `_spans_with_pids.append(...)` line in collection → Phase 2 AST invariant fails.
- **(d) NEW** — Drop `seen_pids.add(pid) / if pid in seen_pids: continue` from helper → test 2 fails (dedup invariant violation).

### 6.3 Test surface forecast (Plan v2 final)

| Phase | Tests | Cumulative |
|---|---|---|
| Phase 1 | 4 (test 1 + test 2 + test 3 + test 4) | 4 |
| Phase 2 | 2 (test 5 helper-call-site AST + test 6 spans-with-pids-scope-lifetime AST) | 6 |
| Phase 3 | 2 (tests 7a + 7b — behavioral N ∈ {2, 3}) | 8 |
| Phase 4 | 0 new tests; 4 deliberate-regression confirmations against existing tests | 8 |

**Plan v2 forecast: +8 tests (2396 → 2404).** Auditor's §10 forecast was ~2403 (+7); Plan v2 lands at +8 because of OBS A's added AST invariant (D10). Difference is +1, within acceptable forecast bounds.

### 6.4 Test name reference (canonical numbering for developer)

| # | Phase | Test name |
|---|---|---|
| 1 | Phase 1 | `test_append_per_speaker_history_basic` (with primary + secondary delta assertions per §4.3) |
| 2 | Phase 1 | `test_append_per_speaker_history_dedups_same_pid` (structural guarantee per §1.5) |
| 3 | Phase 1 | `test_append_per_speaker_history_skips_empty_and_none_pid` (edge cases) |
| 4 | Phase 1 | `test_spans_with_pids_collected_in_multispeaker_emit` (AST forward-property on collection) |
| 5 | Phase 2 | `test_append_per_speaker_history_called_from_multispeaker_emit_path` (AST forward-property on call site, gated, exactly-once, located-before-conversation_turn) |
| 6 | Phase 2 | `test_spans_with_pids_lifetime_within_multispeaker_iteration` (D10 — AST scope-lifetime invariant per §5.3) |
| 7a | Phase 3 | `test_multispeaker_turn_appends_each_speaker_to_own_history[N=2]` (Jagan + Lexi) |
| 7b | Phase 3 | `test_multispeaker_turn_appends_each_speaker_to_own_history[N=3]` (Jagan + Lexi + Priya) |

Developer may rename tests within reason if a more descriptive shape surfaces during implementation; the **invariants each test guards are the contract**, names are guidance.

---

## 7. Architect's response to auditor's three non-precision observations

### 7.1 OBS A — `_spans_with_pids` scope hazard

**Adopted.** Plan v2 §5 adds the AST invariant in Phase 2 (D10). Auditor said "architect's call whether to add now or defer" — architect's call: add now. Cheap and closes a real future-refactor surface.

### 7.2 OBS B — Auditor-Q5-estimates-trail-grep 3rd instance

**Acknowledged.** §3.4 updates the 3rd instance numbers: original estimate 3-5; Plan v2 actual 8. Low-by ~60%. Memory file `feedback_auditor_q5_estimates_trail_grep.md` updates at closure (Phase 4).

Pattern across 3 instances: D-B HIGH by ~40% (21 → 15), D-D LOW by ~4× (40 → 130), D-E LOW by ~60%. Bidirectional + variable-magnitude. Toward potential `### Auditor-estimates-trail-grep` doctrine if 2+ more instances accumulate. Currently architect-memory; correct level for 3 instances.

### 7.3 OBS C — Two-stage pattern NOT bumped (strict-read preservation)

**Acknowledged with appreciation.** γ is single-stage; two-stage observation stays at 2 instances (D-C + D-D). Architect resisted the temptation to artificially fit γ into the two-stage pattern just to bump the count. Strict-read preservation is the discipline working.

---

## 8. Discipline-count predictions (Plan v2 final)

All counts match Phase 0 verdict locks. No changes from Plan v1 §8:

| Discipline | Status |
|---|---|
| Spec-first review cycle | 13-for-13 → **14-for-14** on closure |
| Sub-pattern A (`### Phase-0-catches-wrong-premise`) | **stays at 5 instances** (D-E partial; not wholesale) |
| Tripwires-must-match-deferral-surface | stays **4-for-4** (γ has no deferral tripwire; OBS A's AST invariant is forward-property, not deferral-guarding) |
| Developer-improves-on-spec | stays **6-for-6** unless code phase surfaces a mechanism improvement |
| Induction-surfaces-invariant-gaps | stays **7-for-7** unless Phase 4 surfaces a real gap |
| Canary-finding tracker | stays at **2 instances** |
| Canary-gate override (informal) | stays at **1 instance** |
| Scope-expansion-via-Phase-0 (informal) | stays at **1 instance** |
| Deferral-rationale-expires-when-downstream-ships (informal) | stays at **1 instance** |
| Two-stage-canary-gated-cleanup (informal) | stays at **2 instances** (γ is single-stage) |
| Auditor-Q5-estimates-trail-grep (architect-memory) | **3rd instance** (~60% low bias on D-E) |
| Partial-falsification-tentative (architect-memory only, NOT CLAUDE.md) | **1st instance** banked tentatively |

---

## 9. Developer handoff package

**Joint sign-off cleared 2026-05-19. Code phase ready.**

Developer should consume:

1. **`tests/p0_s7_de_audit.md`** — Phase 0 audit. Sub-pattern A held at 5; partial-falsification noted. Option γ scope locked.
2. **`tests/p0_s7_de_plan_v1.md`** — Plan v1 (APPROVED 2026-05-19 with 4 precision items + 1 non-blocking observation).
3. **`tests/p0_s7_de_plan_v2.md`** (this document) — Plan v2 final. Locks all 4 precision items + OBS A as D10.
4. **`CLAUDE.md`** — project rules + Architectural Disciplines section (especially `### Phase-0-catches-wrong-premise`).
5. **`complete-plan.md`** — P0.S7 narrative anchor.

**Implementation phases (~5.5h total):**
- **Phase 1** (~3.5h): helper definition + `_spans_with_pids` collection + try/except call-site wiring + 4 tests (test 1 with explicit delta + test 2 mandatory dedup + test 3 edge cases + test 4 collection AST). Full-suite verification → green.
- **Phase 2** (~0.5h): 2 AST invariants (test 5 helper-call-site + test 6 `_spans_with_pids` scope-lifetime). Full-suite verification → green.
- **Phase 3** (~1h): behavioral integration parametrized over N ∈ {2, 3} (tests 7a + 7b). Full-suite verification → green.
- **Phase 4** (~0.5h): 4 deliberate-regression confirmations (each one: induce regression → corresponding test fails as predicted → revert → full-suite green) + closure narrative + memory file updates.

**Phase 4 closure banks:**
- 4 deliberate-regression confirmations (gate, primary-skip, collection, dedup) — all PASSING expected
- Sub-pattern A STAYS at 5 instances (D-E partial falsification, not wholesale)
- Two-stage STAYS at 2 instances (γ is single-stage)
- `feedback_partial_falsification_tentative.md` 1st instance banked at architect-memory ONLY (NOT CLAUDE.md)
- `feedback_auditor_q5_estimates_trail_grep.md` 3rd instance update (~60% low bias on D-E)
- Scope reduction documented (3-5 day original → ~5.5h actual via Phase 0 + Plan v2 grep)

---

## 10. Plan v2 deltas from Plan v1 — summary

| Section | Plan v1 | Plan v2 |
|---|---|---|
| D4 (call site) | Helper called unwrapped | **try/except wrapper REQUIRED + log line + `# OPTIONAL` annotation** |
| D5 (dedup) | Optional, dev's choice | **MANDATORY in helper contract** |
| D6 (test surface) | 5-7 tests; Phase 3 test single 2-speaker case | **8 tests; Phase 3 test parametrized over N ∈ {2, 3}** |
| D6 test 1 | Delta assertion deferred to implementation | **Delta assertion locked explicit (before/after row counts for both primary AND secondary)** |
| D10 (NEW) | Did not exist | **Phase 2 AST invariant for `_spans_with_pids` scope-lifetime** |
| Phase 1 time | ~3h | ~3.5h (try/except wrapper + delta assertion + mandatory dedup test refinement) |
| Phase 2 time | ~0.5h | ~0.5h (now 2 AST invariants instead of 1; same time budget; tests are small) |
| Phase 4 confirmations | 3 (gate, primary-skip, collection) | **4 (gate, primary-skip, collection, dedup)** |
| Test count forecast | 5-7 | **8** (Phase 1 +4 + Phase 2 +2 + Phase 3 +2) |
| Auditor-Q5 3rd instance | 3-5 → 5-7 (low-by-30-40%) | **3-5 → 8 (low-by-~60%)** — updated at closure |

All deltas are tightenings or additions. Nothing in Plan v1 is reversed; all locks are strictly stronger.

---

## 11. Bundled-queue canary trigger (post-D-E closure)

Once D-E closes, the bundled queue is COMPLETE: **D-A + D-C Stage 1 + D-B + D-D Stage 1 + γ (P0.S7.4) + D-E.** All architectural items shipped; live multi-person canary validates the set.

**Stage 2 trigger banking (on canary PASS):**
- D-C Stage 2 (hard-delete `_build_cross_person_excerpts` + flag) fires as follow-up
- D-D Stage 2 (hard-delete RoomOrchestrator shim layer + migrate 130 test sites) fires as follow-up
- α full-D-E refactor (NOT scheduled unless canary reveals evidence γ insufficient)

**Combined PR candidate**: D-C Stage 2 + D-D Stage 2 (shared trigger; same canary validates both).

**On canary FAIL with γ-related root cause**: file full α refactor as separate post-canary spec. γ stays in place (additive; doesn't need rollback). No flag flip needed.

---

## 12. Reference documents

- `tests/p0_s7_de_audit.md` — Phase 0 audit (sub-pattern A held at 5; option γ locked)
- `tests/p0_s7_de_plan_v1.md` — Plan v1 (APPROVED 2026-05-19 with 4 precision items + 1 non-blocking observation)
- `tests/p0_s7_dd_audit.md` + closure — D-D shipped 2026-05-19 (sub-pattern A 5th instance + doctrine elevation reference)
- `tests/p0_s7_db_audit.md` + closure — D-B shipped (Kuzu v3 schema bump)
- `tests/p0_s7_dc_audit.md` + closure — D-C Stage 1 shipped (two-stage pattern 1st instance)
- `CLAUDE.md` `### Phase-0-catches-wrong-premise` doctrine
- `pipeline.py:1077-1170` — `_format_multispeaker_transcript` helper (unchanged)
- `pipeline.py:7020-7083` — multi-speaker emit block (γ adds `_spans_with_pids` collection inline)
- `pipeline.py:7370-7461` — routing dispatch (γ does not touch)
- `pipeline.py:7779-7785` — `conversation_turn` invocation (γ adds try/except-wrapped helper call immediately before)
- `pipeline.py:2974` — KAIROS `append_turns` reference (γ helper matches this fire-and-forget pattern)
- `core/conversation_store.py` — P0.6.3 ConversationStore (lock-protected append_turns)
- Memory: `feedback_spec_time_grep_verification.md` (two-pass) — Pass 1 at Plan v1; Pass 2 at closure
- Memory: `feedback_ast_forward_property_tests.md` (3 instances) — applied at D6 + D10
- Memory: `feedback_auditor_q5_estimates_trail_grep.md` (2 → 3 instances at closure)
- Memory: `feedback_partial_falsification_tentative.md` (1 instance, tentative; banked at D-E closure)
- P0.0.7 Step 5 `safe_emit_sync` — D4 try/except pattern precedent (CLAUDE.md developer-improves-on-spec instance)

---

**Joint sign-off cleared 2026-05-19. Developer handoff package complete.**

Plan v2 strictly tightens Plan v1; nothing reversed. All 4 precision items adopted verbatim; OBS A adopted at architect's discretion. Suite delta forecast: **2396 → 2404** (+8 collected: Phase 1 +4, Phase 2 +2, Phase 3 +2). Total effort: ~5.5h (~half-day).
