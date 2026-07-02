# P0.S7.1 — SHARED CONTEXT observability micro-PR

**Date:** 2026-05-18
**Author:** architect
**Status:** Spec direct-to-developer (micro-PR; full spec-first cycle relaxed per user call 2026-05-18). Single-phase, pure additive logging, no architectural surface change. Standing by for developer implementation → user runs canary → architect verifies from logs.

**Surfaced by:** P0.S7 live canary 2026-05-18 (`terminal_output.md` archive). The canary surfaced that `_build_shared_context_block` has zero observability — no log signal indicates whether the block rendered, was gated, or returned empty. Brain behavior subjectively suggested it worked (line 244: `room=yes`, line 369: Jagan named Lexi explicitly) but the legacy `_build_cross_person_excerpts` block was also firing (line 243 `[Brain] Room context: 2 people active`) so we couldn't distinguish which block carried the load.

**Why this blocks D-C:** D-C deletes `_build_cross_person_excerpts` — the legacy safety net. Without observability for SHARED CONTEXT, a subtle bug in the new block would only surface AFTER the legacy is gone. Add observability first; then re-canary; then ship D-C with confidence.

---

## 1. Scope

**In scope (Phase 1 only, ~1-2 hours):**
- Add per-call log emit inside `_build_shared_context_block` (`pipeline.py:1305`) covering all 5 outcome paths (4 gates + render path).
- Extend the `[Brain] Context:` summary log line in `conversation_turn` (and `_kairos_tick` if applicable) to include `shared_context=<N>` field where N is the rendered row count (0 if None returned).
- 2 tests for the log emit shape (parametrized over outcome paths) + 1 test for the summary-line extension.

**Out of scope:**
- ANY change to `_build_shared_context_block`'s gate logic / SQL query / render shape.
- ANY change to `FaceDB.get_recent_room_conversation`.
- ANY change to the existing `[Brain] Context:` field order (only EXTEND the format; don't reorder existing fields).
- Adding observability to `_build_room_block` or `_build_cross_person_excerpts` (separate concern; not part of P0.S7.1).

---

## 2. Log emit specification

### 2.1 `_build_shared_context_block` per-call log

Emit ONE log line per call, capturing the outcome. Five mutually-exclusive outcomes:

| Path | Condition | Log line format |
|---|---|---|
| A | `SHARED_CONTEXT_BLOCK_ENABLED=False` | `[SharedContext] gate=flag_off → skip` |
| B | `active_session_count < 2` | `[SharedContext] gate=single_person (count={N}) → skip` |
| C | `room_session_id` falsy (None/empty) | `[SharedContext] gate=no_room_session_id → skip` |
| D | `is_disputed_fn(requester_pid)` True | `[SharedContext] gate=disputed (requester={pid}) → skip` |
| E | DB returned 0 rows | `[SharedContext] room={room_id} requester={pid} rows=0 → skip` |
| F | DB returned N rows | `[SharedContext] room={room_id} requester={pid} rows={N} → rendered` |

Emit BEFORE returning from the helper (so the log is paired with each return statement). The 5 mutually-exclusive prefixes (`gate=flag_off` / `gate=single_person` / `gate=no_room_session_id` / `gate=disputed` / `rows=0 → skip` / `rows={N} → rendered`) make canary grep trivially unambiguous.

**Stylistic guidance (consistent with existing pipeline log style):**
- Always `[SharedContext]` prefix (mirrors `[Brain]` / `[Room]` / `[Voice]` patterns).
- No timestamp prefix on the helper-level log — `conversation_turn`'s outer logging context already carries timing for the turn.
- Quote pid values in the gate=disputed branch since they may have special chars; raw is fine for room_id (uuid-shape).

### 2.2 `[Brain] Context:` summary extension

Current format (pipeline.py:5220):
```python
print(f"[Brain] Context: history={len(history)} turns, memory={'yes' if memory_context else 'no'}, emotion={'yes' if emotion_context else 'no'}, room={'yes' if room_context else 'no'}, scene={'yes' if SCENE_BLOCK_ENABLED else 'no'}")
```

**Extend to add `shared_context=<N>` field at the end** (preserve existing field order):
```python
print(f"[Brain] Context: history={len(history)} turns, memory={'yes' if memory_context else 'no'}, emotion={'yes' if emotion_context else 'no'}, room={'yes' if room_context else 'no'}, scene={'yes' if SCENE_BLOCK_ENABLED else 'no'}, shared_context={_shared_ctx_row_count}")
```

Where `_shared_ctx_row_count` is the row count rendered (or 0 if None returned). Caller must capture the row count when building vision_state.

**Implementation hint:** `_build_shared_context_block` currently returns `str | None`. Change to ALSO return the row count, OR add a sibling helper / module-level last-render-count. Simplest: have `_build_shared_context_block` set a module-level `_last_shared_context_row_count: int = 0` on every call (0 on any skip path, N on render). Caller reads the module attr after the call.

Apply the same extension at the `_kairos_tick` Brain Context log site if one exists (search for `[Brain] Context:` in `_kairos_tick` — may or may not exist).

---

## 3. Test specification

**File:** `tests/test_p0_s7_1_observability.py` (new)

**Test 1 — `test_shared_context_log_emit_per_outcome`** (parametrized over 6 outcome paths):

For each outcome path A-F:
- Set up the gate-firing condition (mock flag, mock active_session_count, mock disputed_fn, mock DB to return 0/N rows).
- Call `_build_shared_context_block(...)` once.
- Capture stdout (pytest `capsys` fixture).
- Assert the captured stdout contains EXACTLY ONE line matching the expected format string for that outcome.

**Test 2 — `test_brain_context_summary_includes_shared_context_field`**:

- Behavioral test: call into `conversation_turn` path (or use existing test scaffolding) with vision_state["shared_context"] set to render path.
- Capture stdout; assert `[Brain] Context:` line contains `shared_context=<integer>`.
- Parametrize over (a) shared_context renders 3 rows → field reads `shared_context=3`; (b) shared_context None → field reads `shared_context=0`.

**Test 3 — `test_last_shared_context_row_count_module_attr`** (if option chosen):

- Source-inspection test: `_build_shared_context_block` writes to module-level `_last_shared_context_row_count` exactly once per call.
- AST scan asserts the variable is assigned in every return path.

**Net new tests: 3 logical (parametrize fan-out per Test 1 yields ~6 collected).** Suite delta forecast: 2337 → ~2343.

---

## 4. Phase plan

Single phase. ~1-2 hours total.

1. Add per-call log emit inside `_build_shared_context_block` (5 outcome paths covered).
2. Track row count via module-level attr `_last_shared_context_row_count` (set in every code path).
3. Extend `[Brain] Context:` summary line at conversation_turn site to include `shared_context=<count>`.
4. Apply same extension at `_kairos_tick` Brain Context log site if it exists.
5. Add 3 tests per §3.
6. Run full suite; verify green.
7. Closure report: confirm all 6 outcome paths exercised by Test 1, confirm summary extension in conversation_turn + _kairos_tick paths.

---

## 5. Validation gate

- All 3 new tests green; full suite green at ~2343.
- Manual sanity: invoke `_build_shared_context_block` with each of the 6 outcome paths in a REPL or quick script; visually confirm each log line format.
- No regression in existing `[Brain] Context:` line format (existing tests asserting that line should still pass — preserved by appending the new field rather than reordering).

---

## 6. Discipline-count predictions

- **Spec-first review cycle: stays 9-for-9.** Micro-PRs that bypass the full spec-first cycle (per user call) don't bump the count; only multi-day specs with Phase 0 → Plan v1 → Plan v2 → 4-phase implementation count for that track record.
- **Induction-surfaces-invariant-gaps: 7-for-7 → 8-for-8 candidate.** The canary surfaced a real observability gap that neither the Phase 0 audit, Plan v1, nor Plan v2 considered. Closure of P0.S7.1 fills the gap in the same cycle the canary exposed it — strict-read interpretation of the discipline. Auditor adjudicates at closure.
- **Sub-pattern A: stays at 4 instances banked.** P0.S7.1 isn't a wrong-premise catch on its own — it's the FOLLOW-UP to P0.S7's wrong-premise (which already banked the 4th instance).
- **Tripwires-must-match-deferral-surface: stays 4-for-4.**
- **Developer-improves-on-spec: stays 6-for-6** unless the implementation surfaces a mechanism improvement (possible at the module-attr design choice).

---

## 7. Reference documents

- `tests/p0_s7_audit.md` — Phase 0 audit (D-A first slice)
- `tests/p0_s7_plan_v2.md` — Plan v2 (D-A code contract)
- `pipeline.py:1305` — `_build_shared_context_block` implementation target
- `pipeline.py:5220` — `[Brain] Context:` summary log site (extend at this location)
- `terminal_output.md` (current archive) — canary log that surfaced the gap
