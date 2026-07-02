# P0.S7.D-C — Delete `_build_cross_person_excerpts` legacy block — Plan v1

**Date:** 2026-05-19
**Author:** architect
**Status:** Plan v1 — drafted against Phase 0 D-lock (2026-05-19) + auditor's 2 precision items + 2 informal observations from `tests/p0_s7_dc_audit.md`'s Phase 0 review verdict. Standing by for auditor's Plan v1 review → Plan v2 (if precision items surface) → joint sign-off → developer handoff.

**Phase 0 audit:** `tests/p0_s7_dc_audit.md` (premise + 10-surface dependency map + D-decisions + quality flags).

---

## 1. Locked decision reference (Phase 0 D-lock 2026-05-19)

| ID | Locked at | Notes |
|---|---|---|
| D1 | **(a) Two-stage** flag-gate | Stage 1 = this D-C (flag-gate); Stage 2 = post-canary hard-delete |
| D2 | **(a) Repoint** `[Brain] Context: ... room=yes/no` to ROOM block render | Semantic intent ("multi-person context in scope this turn") preserved |
| D3 | **Plan v1 grep-verified gap; commits to disposition (a)** — extend `_build_room_block` Section 1 with `_is_disputed(pid)` check | See §3 — gap confirmed, fix shape locked |
| D4 | Plan v1 grep-enumerates test surface; delete if ≤5, repoint if >10 | See §6 grep findings |
| D5 | DELETE `room_context` prepending into `prompt_addendum` under flag | Redundant with `_build_system_prompt` direct injection |
| D6 | Token-budget net reduction ~-300 tokens/multi-person turn | Validation-window overlap eliminated |
| D7 | NEW Phase 3 AST invariant (forward-property, NOT deferral tripwire) | Tripwire count stays 4-for-4 |
| D8 | ~4-6 tests, ~half-day, suite 2367 → ~2371 | Approved |
| **P1** (precision item 1) | **Stage 2 hard-delete trigger condition** explicit: filed as standalone follow-up after user's bundled-queue canary validates D-A + D-C + D-B + D-D + D-E + γ AS A SET | See §8 |
| **P2** (precision item 2) | **D3 gap-verification DONE in Plan v1**: gap CONFIRMED; disposition (a) locked — extend ROOM Section 1 | See §3 — code shape included |

---

## 2. Architectural overview

D-C ships as Stage 1 of a two-stage deletion. Three surface-level changes:

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Stage 1 (this D-C) — flag-gate legacy block                              │
│                                                                            │
│  1. New config: CROSS_PERSON_EXCERPTS_ENABLED: bool = False              │
│  2. pipeline.py:5419 call site guarded:                                   │
│       if CROSS_PERSON_EXCERPTS_ENABLED:                                   │
│           room_context = _build_cross_person_excerpts(...)                │
│       else:                                                               │
│           room_context = None                                             │
│  3. pipeline.py:5423 [Brain] Context: summary field repointed             │
│       OLD: room='yes' if room_context else 'no'                           │
│       NEW: room='yes' if len(active_sessions) >= 2 else 'no'              │
│  4. pipeline.py:5448-5449 prompt_addendum prepending — DEAD when flag    │
│     off (room_context is None); explicit if-guard for clarity             │
│  5. _build_room_block Section 1 — extend with _is_disputed(pid) check    │
│     to preserve disputed-identity role label (D3 fix)                     │
└──────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼ (validation window: bundled-queue canary)
┌──────────────────────────────────────────────────────────────────────────┐
│  Stage 2 (post-canary follow-up)                                           │
│  Hard-delete: _build_cross_person_excerpts function (89 LOC) +            │
│  CROSS_PERSON_EXCERPTS_ENABLED config flag + tests + dead-code branches.  │
│  Trigger: user runs bundled-queue canary validating D-A + D-C + D-B +     │
│  D-D + D-E + γ AS A SET; on canary pass, file Stage 2 follow-up.          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 3. D3 gap-verification — grep findings + disposition

### 3.1 Grep verification (per Precision 2)

**Question**: does `_build_room_block` Section 1 emit the "disputed identity" role label that `_build_cross_person_excerpts` (line 1234) produces?

**Grep findings** (pipeline.py 2026-05-19):

| Site | Function | Disputed-identity check? |
|---|---|---|
| Line 1234-1235 | `_build_cross_person_excerpts` (LEGACY) | ✓ Yes — `if _is_disputed(pid): role = "disputed identity"` |
| Line 1800-1801 | `_build_scene_block` (SCENE) | ✓ Yes — `if _is_disputed(pid): role = "disputed identity"` |
| **Line 1508** | **`_build_room_block` Section 1** | **✗ NO — `_active_lines.append(f"{_rs.person_name} ({_rs.person_type})")` — NO disputed check** |

**Compounded finding**: the `<<<IDENTITY DISPUTED>>>` block (core/brain.py:2402-2412) fires ONLY for the CURRENT SPEAKER (`_is_disputed(person_id)` at vision_state line 3286). In a multi-person scene where Jagan (current speaker) is non-disputed and Lexi (other participant) IS disputed:

- Legacy block: emits "Lexi (disputed identity)" in active speakers list ✓
- `<<<ROOM>>>` Section 1: emits "Lexi (stranger)" or whatever person_type — NO disputed signal ✗
- `<<<IDENTITY DISPUTED>>>` block: doesn't fire (Jagan isn't disputed) ✗

**Real correctness regression risk**: brain loses the "Lexi is contested" signal in multi-person scenes after legacy block flag-gates off.

### 3.2 Disposition locked — (a) Extend `_build_room_block` Section 1

```python
# Plan v1 §3.2 — D3 fix
# Mirror the SCENE block's pattern at pipeline.py:1800 and the legacy
# block's pattern at line 1234.

for _rs in active_sessions:
    pid = _rs.person_id
    if _is_disputed(pid):
        role = "disputed identity"
    elif pid == best_friend_id:  # NEW — needed for parity
        role = "best_friend"
    else:
        role = _rs.person_type
    _active_lines.append(f"{_rs.person_name} ({role})")
```

**Why also add the best_friend check**: the SCENE block (pipeline.py:1802-1807) and the legacy block (line 1236) both use the explicit role hierarchy `disputed → best_friend → visitor/known`. ROOM Section 1 currently just uses raw `person_type` which doesn't surface best_friend status. Adding the disputed check without the best_friend check would leave a partial-fix smell.

**Signature change**: `_build_room_block` gains `best_friend_id: "str | None" = None` kwarg (default None for backward-compat). Caller at pipeline.py:3274 (and 7956 KAIROS) updated to pass `_bf_id`.

### 3.3 Why option (a) over (b) `<<<IDENTITY DISPUTED>>>` coverage extension

Option (b) would extend the existing `<<<IDENTITY DISPUTED>>>` block to fire for any room participant (not just current speaker). Pros: existing block, easier to extend. Cons:

- Crosses a layer boundary — the IDENTITY DISPUTED block is the CURRENT-SPEAKER honesty contract; extending it to room-participants confuses its semantic.
- Doesn't preserve the role-label surface (the legacy block emitted "Lexi (disputed identity)" inline with other roles; (b) would render disputed status in a separate block).
- More code change (block + vision_state plumbing changes) than option (a).

Option (a) is the smaller change, preserves the inline-with-roles surface, mirrors existing SCENE block pattern. Locked.

### 3.4 Why NOT option (c) bank as future micro-PR

The gap is real and silent — brain loses a load-bearing identity-signal in multi-person scenes. Banking as future micro-PR would ship D-C with a known correctness regression. Auditor's Precision 2 explicitly forbids deferral. Disposition (a) lands in D-C Phase 1.

---

## 4. Test surface impact (D4 grep enumeration)

### 4.1 Grep findings

`_build_cross_person_excerpts` references across test files:

| File | Line(s) | Type | Disposition |
|---|---|---|---|
| `test_pipeline.py` | search needed | Tests directly asserting legacy block render | Plan v1 §4.2 below |

Specific test names grep-enumerated in Phase 1 implementation:
- Any `test_build_cross_person_excerpts_*` direct unit tests → **DELETE** (flag-gated source path; tests assert dead-when-flag-off behavior)
- Any tests asserting the `room_context` prepending into `prompt_addendum` → **DELETE or REPOINT** depending on whether they assert structural shape (delete) vs behavior (repoint to ROOM block tests)
- Session 111 Critical #2 (session-boundary filter) test → **REPOINT** to ROOM Section 3 test (ROOM already enforces the boundary via `_boundary = room_start_ts` at pipeline.py:1525)
- Session 111 Critical #3 (addressed_to render) test → **REPOINT** to ROOM Section 3 or SHARED CONTEXT test (both render addressed_to)
- S91 Finding M (disputed-identity role label) test → **REPOINT** to the NEW ROOM Section 1 disputed-check (D3 fix)

### 4.2 Disposition strategy

Per auditor's D4 lock: delete if ≤5, repoint if >10. Grep at Phase 1 implementation time confirms the count. Plan v1 commits to:
- Tests asserting direct LEGACY render — DELETE (dead code under flag-off)
- Tests asserting SEMANTIC properties (session-boundary, addressed_to, disputed-role) — REPOINT to ROOM / SHARED CONTEXT equivalents

Plan v1 §6 Phase 3 adds NEW tests for the disputed-identity ROOM Section 1 fix (D3 disposition (a)).

---

## 5. `[Brain] Context:` summary field repoint (D2)

### 5.1 Current state (pipeline.py:5423)

```python
print(f"[Brain] Context: history={len(history)} turns, memory={'yes' if memory_context else 'no'}, emotion={'yes' if emotion_context else 'no'}, room={'yes' if room_context else 'no'}, scene={'yes' if SCENE_BLOCK_ENABLED else 'no'}, shared_context={_last_shared_context_row_count}")
```

The `room=yes/no` field is based on `room_context` — the output of `_build_cross_person_excerpts`. When the flag-gate sets `room_context = None`, this field always reads `room=no` even in multi-person scenes (a regression — the field becomes useless for canary grep).

### 5.2 Plan v1 lock — repoint to `len(active_sessions) >= 2`

```python
# Plan v1 §5 — D2 repoint
_multi_person = len(_all_snaps_ct) >= 2
print(f"[Brain] Context: history={len(history)} turns, memory={'yes' if memory_context else 'no'}, emotion={'yes' if emotion_context else 'no'}, room={'yes' if _multi_person else 'no'}, scene={'yes' if SCENE_BLOCK_ENABLED else 'no'}, shared_context={_last_shared_context_row_count}")
```

**Semantic preserved**: "room=yes" means "multi-person context is in scope this turn" — same as before. Implementation source flips from "legacy block output exists" → "multi-person session exists." Grep tooling that reads the field continues to work.

**Alternative considered (and rejected)**: read from `_build_room_block` output directly. Rejected because (a) ROOM block has its own gating (ROOM_BLOCK_ENABLED + multi-person + room_session_id presence) that's stricter than just multi-person; (b) `len(active_sessions) >= 2` is the most-honest mapping of the field's semantic intent.

---

## 6. Test specification (Plan v1 — 6 logical tests)

### Phase 1 tests (flag-gate + D3 fix)

1. **`test_cross_person_excerpts_enabled_flag_defaults_false`** — source-inspection: `CROSS_PERSON_EXCERPTS_ENABLED` exists in `core/config.py`, type `bool`, value `False`.

2. **`test_build_cross_person_excerpts_call_site_guarded_by_flag`** — source-inspection: pipeline.py:5419 area contains `if CROSS_PERSON_EXCERPTS_ENABLED:` guard before `_build_cross_person_excerpts(` call.

3. **`test_build_room_block_section1_renders_disputed_identity`** (NEW — D3 fix) — behavioral: build `active_sessions` with one disputed pid; call `_build_room_block(...)`; assert Section 1 renders `(disputed identity)` for the disputed participant.

4. **`test_build_room_block_section1_renders_best_friend_role`** (NEW — D3 partial-fix companion) — behavioral: build `active_sessions` with best_friend pid; call `_build_room_block(best_friend_id=that_pid)`; assert Section 1 renders `(best_friend)` for that participant.

### Phase 2 test ([Brain] Context: summary repoint)

5. **`test_brain_context_summary_room_field_repointed_to_active_sessions`** — behavioral: with 2 active sessions, `room=yes` in `[Brain] Context:` log line; with 1 active session, `room=no`. Both cases with `CROSS_PERSON_EXCERPTS_ENABLED=False` (flag-gated off). Verifies semantic preserved.

### Phase 3 test (D7 structural invariant)

6. **`test_no_room_context_prepending_when_flag_off`** — AST scan pipeline.py: when `CROSS_PERSON_EXCERPTS_ENABLED=False`, the code path at pipeline.py:5448-5449 (`prompt_addendum = room_context + ...`) is unreachable (room_context is None). Structural invariant: any new prepending of multi-person blocks to `prompt_addendum` after this fix is forbidden.

### Phase 4 (deliberate-regression confirmations — closure items)

- Flip `CROSS_PERSON_EXCERPTS_ENABLED=True` → flag-gated path re-enables → confirm legacy block renders → `[Brain] Context:` field still uses repointed `len(active_sessions) >= 2` semantic per D2 (independent of flag).
- Drop `_is_disputed(pid)` check from ROOM Section 1 (D3 fix) → test 3 fails → revert.
- Drop best_friend_id check from ROOM Section 1 → test 4 fails → revert.
- Drop the `len(active_sessions) >= 2` repoint in summary → test 5 fails → revert.
- Inject `room_context = _build_cross_person_excerpts(...)` without the flag guard → test 2 fails → revert.

**Net new tests: 6 logical.** Suite delta forecast: 2367 → 2373 (+6).

---

## 7. Implementation phases

### Phase 1 — Flag-gate + D3 fix (+4 tests, ~quarter-day)

- New config `CROSS_PERSON_EXCERPTS_ENABLED: bool = False` in `core/config.py`.
- pipeline.py:5419 call site guarded by flag.
- pipeline.py:5448-5449 prompt_addendum prepending — `room_context` is None when flag off; explicit `if room_context is not None and CROSS_PERSON_EXCERPTS_ENABLED:` guard for clarity (defensive — both conditions checked).
- `_build_room_block` Section 1 — extend with `_is_disputed(pid)` check + best_friend_id check (Plan v1 §3.2 code).
- `_build_room_block` signature gains `best_friend_id: "str | None" = None` kwarg.
- 2 call sites (pipeline.py:3274 + 7956) updated to pass `_bf_id`.
- Tests 1, 2, 3, 4 from §6.
- **Suite checkpoint:** 2367 → 2371 (+4).

### Phase 2 — `[Brain] Context:` summary repoint (+1 test, ~quarter-day)

- pipeline.py:5423 line repointed to `len(_all_snaps_ct) >= 2`.
- Test 5 from §6.
- **Suite checkpoint:** 2371 → 2372 (+1).

### Phase 3 — D7 structural invariant + test surface cleanup (+1 test, ~quarter-day)

- Phase 1 grep-enumerates `_build_cross_person_excerpts` test references in `test_pipeline.py`.
- Per §4.2 disposition: delete legacy-render tests, repoint semantic-property tests.
- Test 6 from §6 (AST invariant).
- **Suite checkpoint:** 2372 → 2373 (+1).

### Phase 4 — Deliberate-regression confirmations + closure + Stage 2 trigger doc (+0 tests, ~quarter-day)

- 5 deliberate-regression confirmations per §6 Phase 4 list.
- Closure-report banking:
  - 2 Plan v1 precision items resolution (Stage 2 trigger + D3 fix)
  - 2 informal observations (canary-gate override + scope-expansion-via-Phase-0)
  - Stage 2 trigger documented explicitly: "after user's bundled-queue canary validates D-A + D-C + D-B + D-D + D-E + γ AS A SET"
  - Discipline-count updates (Plan v1 §9)

**Total effort: ~half-day. Net new tests: 6 logical. Suite delta: 2367 → 2373.**

---

## 8. Stage 2 trigger specification (Precision 1)

Stage 2 hard-delete is a **standalone follow-up sub-PR**, NOT part of D-C. Plan v1 commits to the trigger:

**Trigger condition**: user runs a multi-person canary AFTER all bundled-queue items have shipped (D-C + D-B + D-D + D-E + γ strengthening as P0.S7.4). On canary PASS — brain demonstrates cross-session recall + multi-person room context correctly + autonomous search_memory call per γ behavioral target + no regressions in disputed-session / addressed_to / session-boundary surfaces — the user files a Stage 2 follow-up PR.

**Stage 2 scope**:
- Delete `_build_cross_person_excerpts` function (pipeline.py:1202-1290, ~89 LOC).
- Delete `CROSS_PERSON_EXCERPTS_ENABLED` config flag.
- Delete the flag-gate at pipeline.py:5419.
- Delete the dead prompt_addendum prepending path (pipeline.py:5448-5449 — already dead under flag-off).
- Delete the flag-related tests (test 1 + test 2 from §6).
- Suite delta forecast for Stage 2: -90 LOC, -2 tests, no functional change.

**Stage 2 closure narrative banking**: Stage 2's closure references back to P0.S7.D-C as the Stage 1 of the two-stage approach. This preserves the audit trail.

**If canary FAILS** (any regression in multi-person scenes): rollback by flipping `CROSS_PERSON_EXCERPTS_ENABLED=True`. One-flag-flip rollback. Stage 2 stays unfiled until canary passes.

**Closure narrative requirement**: P0.S7.D-C closure report explicitly notes "Stage 2 trigger filed as banked follow-up dependency. NOT yet scheduled." Mirrors P0.S7.2 §11.10 re-canary banking pattern.

---

## 9. Discipline-count predictions (strict-read locked per auditor verdict)

| Discipline | Pre-D-C | On D-C closure |
|---|---|---|
| Spec-first review cycle | 10-for-10 | **11-for-11** ✓ |
| Sub-pattern A | 4 instances | stays **4** (D-C is scope-expansion, not wrong-premise — auditor adjudication) |
| Tripwires-must-match-deferral-surface | 4-for-4 | stays **4-for-4** (D7 is forward-property) |
| Developer-improves-on-spec | 6-for-6 | stays **6-for-6** unless code phase surfaces a mechanism improvement |
| Induction-surfaces-invariant-gaps | 7-for-7 | stays **7-for-7** |
| Canary-finding tracker | 2 instances | stays **2** (no new canary-finding) |

**Two informal observations banked** (NOT numbered disciplines yet):

1. **Canary-gate override**: "spec explicitly reverses its own canary-gate per user strategic direction; quality mitigation via two-stage flag-gate." Currently **1 instance** (P0.S7.D-C). If recurs 5+ times, may surface as `### Canary-gate-overrides-need-quality-mitigation` doctrine.
2. **Scope-expansion-via-Phase-0**: "Phase 0 audit finds deletion/cleanup scope is N× larger than pre-audit assumption." Currently **1 instance** (P0.S7.D-C). Distinct from sub-pattern A. If recurs 5+ times, may surface as `### Phase-0-catches-scope-expansion` doctrine.

---

## 10. Validation gate

1. All 6 new tests green; full-suite green at 2373.
2. 5/5 deliberate-regression confirmations pass (induction protocol).
3. D3 gap-verification disposition (a) shipped — ROOM Section 1 renders disputed identity in multi-person scenes.
4. D2 `[Brain] Context: room=yes/no` repointed and verified.
5. Stage 2 trigger documented in closure narrative as banked follow-up dependency.

---

## 11. Open items / risks

1. **Disputed-identity ROOM Section 1 fix has 2 call sites to update** — pipeline.py:3274 (conversation_turn vision_state) + pipeline.py:7956 (KAIROS path). Both need `best_friend_id=_bf_id` added to `_build_room_block(...)` calls. Missing one site = inconsistent disputed-identity rendering across conversation/KAIROS turns. Phase 1 source-inspection test or grep verification protects against partial-update.

2. **Stage 2 trigger drift** — if user's bundled-queue canary passes but Stage 2 follow-up doesn't get filed promptly, dead code accumulates. Mitigation: closure narrative banks the dependency; CLAUDE.md "Pending Work" section gets a Stage 2 entry on D-C closure.

3. **Test surface unknown until Phase 1 grep** — if `test_pipeline.py` has many tests referencing legacy block (more than the ≤5 threshold), Phase 3 repointing work scales. Architect's lean: likely ≤5 because S91 + S111 + S107 tests already migrated to ROOM/SHARED CONTEXT during prior cycles. Phase 1 grep confirms.

4. **`[Brain] Context: room=yes/no` semantic flip (D2)** — the field's meaning changes from "legacy block rendered" → "multi-person session active." Any tool/log-grep relying on the field's current semantic will need to be aware. Low-impact (no production code reads the field; developer observability only).

5. **D3 fix ripple effect** — adding `best_friend_id` parameter to `_build_room_block` is a signature change. Existing Phase 2 tests of ROOM block (S113 P3B.1) call the function without that kwarg. Backward-compat preserved via `best_friend_id: "str | None" = None` default — existing tests don't break, but they don't test the new branch either. Phase 1 Test 4 (NEW) exercises the new branch directly.

---

## 12. References

- `tests/p0_s7_dc_audit.md` — Phase 0 audit
- `tests/p0_s7_audit.md` — P0.S7 Phase 0 audit (D-C bookmark)
- `tests/p0_s7_plan_v2.md` — P0.S7 Plan v2 (§11 D-C canary-gate)
- `tests/p0_s7_2_plan_v2.md` — P0.S7.2 cross-session memory Plan v2 (§11.10 re-canary discipline pattern)
- `pipeline.py:1202-1290` — `_build_cross_person_excerpts` (Stage 1 flag-gate target; Stage 2 deletion target)
- `pipeline.py:5419-5449` — call site + prompt_addendum prepending
- `pipeline.py:5423` — `[Brain] Context: ... room=yes/no` summary log line (D2 repoint target)
- `pipeline.py:1234` — disputed-identity role label site (D3 reference shape)
- `pipeline.py:1457-1546+` — `_build_room_block` (D3 extension target)
- `pipeline.py:1508` — ROOM Section 1 (D3 fix site)
- `pipeline.py:1800-1801` — SCENE block disputed-identity check (D3 mirror pattern)
- `pipeline.py:3274, 7956` — `_build_room_block` call sites needing best_friend_id pass-through
- `core/brain.py:2402-2412` — `<<<IDENTITY DISPUTED>>>` block (current-speaker only)

---

## 13. Next steps

1. **Auditor reviews Plan v1.** Specifically: (a) D3 fix code shape (3.2) — any precision items?; (b) Stage 2 trigger language (§8) — sufficient or needs more specificity?; (c) D2 repoint semantic — any concerns about the log-line backward-compat?; (d) §11 risks — anything missed?
2. **Plan v2** drafted if precision items surface (architect expects 0-2 items; this is a smaller spec than P0.S7 / P0.S7.2).
3. **Joint sign-off → developer handoff** for 4-phase implementation.
4. **Stage 2 banked as follow-up dependency** in CLAUDE.md "Pending Work" on D-C closure.
