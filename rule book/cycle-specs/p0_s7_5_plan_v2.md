# P0.S7.5 — Plan v2 (architect's response to Plan v1 review)

**Date:** 2026-05-19
**Author:** architect
**Status:** Plan v2 — 3 auditor precision items locked + 2 banking observations adopted + Q5 sub-observation banked. Standing by for joint sign-off.

**Preceding documents:**
- `tests/p0_s7_5_audit.md` — Phase 0 audit (APPROVED 2026-05-19 with 6 adjudications)
- `tests/p0_s7_5_plan_v1.md` — Plan v1 (APPROVED 2026-05-19 with 3 precision items)
- This document — Plan v2 (locks precision items; final spec before developer handoff)

---

## Summary — auditor's 3 precision items + 2 banking observations

| Item | Severity | Disposition |
|---|---|---|
| MEDIUM 1 — Phase 4 5th deliberate-regression confirmation for D4 | MEDIUM | LOCKED — Phase 4 confirmation set grows to 5 |
| LOW 1 — `_ONE_SHOT_NUDGE_TYPES` naming convention | LOW | LOCKED — option (a) drop `_` prefix → `ONE_SHOT_NUDGE_TYPES` |
| LOW 2 — Re-injection observability | LOW | LOCKED — ~3 LOC per-turn re-injection log added to `get_prompt_addendum` |
| OBS A — D3 rename-failure stale-name ack | non-blocking | ADOPTED — closure-narrative documents as known limitation; no code change |
| OBS B — D4 same-name (person_name == system_name) edge case | non-blocking | ADOPTED — defer to actual occurrence |
| Q5 sub-observation — Phase 0 granularity correlation | banking | LOCKED — refinement note added to `feedback_auditor_q5_estimates_trail_grep.md` at closure |

**Architect's 4 anticipated items from Plan v1 §11**: 3 of 4 explicitly approved-as-deferred by auditor (D2 query batching, D3 exception class, D4 block content). Item 4 (E2E fixture standardization) also deferred. None became blocking precision items. Discipline-system in sync.

---

## 1. MEDIUM 1 — Phase 4 5th deliberate-regression confirmation for D4

### 1.1 Plan v1 §8.4 said (insufficient — 4 confirmations for 5 D-decisions)

Plan v1 listed 4 deliberate-regression confirmations: (a) revert D1, (b) revert D2, (c) revert D3, (d) drop D5 bullet. **Missing: explicit confirmation for D4.**

### 1.2 Plan v2 locks (5 confirmations — one per D-decision)

Add confirmation (e) targeting D4's load-bearing structural change:

**(e) Drop `format_known_speaker_identity_block` invocation in `_build_system_prompt`** → test 10 (AST gating) fails (block absent for known-speaker session).

### 1.3 Updated Phase 4 confirmation set

| # | Confirmation | Target | Test that fails |
|---|---|---|---|
| (a) | Drop `VISITOR_ALERT` from `_ONE_SHOT_NUDGE_TYPES` exemption (revert D1) | D1 | Test 2 (nudge=no after first) + Test 14 (persistence broken) |
| (b) | Revert D2 fallback branch in `build_shared_context_block` | D2 | Test 4 (gate widening) + Test 15 (cross-session retrieval) |
| (c) | Revert D3 `await` → `create_task` | D3 | Test 6 (AST) + Test 7 (canonical ack reads stale name) |
| **(d)** | **Drop `format_known_speaker_identity_block` invocation in `_build_system_prompt`** | **D4** | **Test 10 (AST gating)** |
| (e) | Drop FABRICATED ABSENCE bullet from HONESTY POLICY | D5 | Test 12 (anti-pattern content) |

Note: Plan v1's lettering reshuffled. Plan v2 LOCKS the order as (a/b/c/d/e) aligned with D1/D2/D3/D4/D5 — easier auditor-side cross-reference at closure.

### 1.4 Rationale (auditor verdict adopted)

Discipline pattern across D-C/D-B/D-D/D-E closures has been "one deliberate-regression confirmation per D-decision." With 5 D-decisions in P0.S7.5, 5 confirmations are correct. Auditor's specific choice between targeting the block invocation vs the description text — locked at block invocation (auditor's lean): "the block insertion is more load-bearing than the description text." The description extension is auxiliary protection; the block is the primary structural change.

Phase 4 effort estimate adjusts: 4 → 5 confirmations adds ~5-10 min total (each confirmation is ~1-2 min: induce → run test → revert). Phase 4 time bumps from ~0.5h → ~0.5h (still under budget; trivial addition).

---

## 2. LOW 1 — `_ONE_SHOT_NUDGE_TYPES` naming convention

### 2.1 Plan v1 §3.2 said (inconsistent with config.py convention)

```python
_ONE_SHOT_NUDGE_TYPES: frozenset[str] = frozenset({...})
```

Leading underscore implies module-private, but `core/config.py` constants (MAX_EMBEDDINGS, SCHEMA_NORM_THRESHOLD, RECOGNITION_THRESHOLD, etc.) do NOT use the `_` prefix — config.py's role is cross-module public configuration.

### 2.2 Plan v2 locks (option (a) — drop `_` prefix)

```python
# P0.S7.5 D1 — nudge types that are ONE-SHOT proactive reminders.
# These get mark_nudge_injected on first delivery (legacy behavior).
# Nudge types NOT in this set default to PERSISTENT context — they
# stay pending and re-inject every turn until expires_at or dismissed.
# VISITOR_ALERT is INTENTIONALLY excluded: owner needs persistent
# context about visitor presence whenever they ask, not just first turn.
# When adding a new nudge type, default behavior is PERSISTENT — opt
# into one-shot only when the type is a proactive reminder that
# should not repeat.
ONE_SHOT_NUDGE_TYPES: frozenset[str] = frozenset({
    "CROSS_PERSON_HYPOTHESIS",
    "INTENTION_FOLLOWUP",
    "MEMORY_PROMPT",
})
```

### 2.3 Rationale (auditor verdict adopted)

Option (a) selected over option (b) because:
- `core/config.py` is the architecturally correct home for cross-module constants
- The constant IS used by `core/brain_agent.py` (`PromptPrefAgent.get_prompt_addendum`) — confirms cross-module usage
- Future consumers (test files, possible future nudge consumers) benefit from a public config import path
- Option (b) would force `from core.brain_agent import _ONE_SHOT_NUDGE_TYPES` patterns elsewhere — leaky abstraction

### 2.4 Import statement update

In `core/brain_agent.py` `PromptPrefAgent.get_prompt_addendum`:

```python
# Plan v1 had:
from core.config import _ONE_SHOT_NUDGE_TYPES

# Plan v2 lock:
from core.config import ONE_SHOT_NUDGE_TYPES
```

Test files referencing the constant use the same import (no leading underscore).

### 2.5 No semantic change

Pure naming convention fix. Behavior unchanged. Cost: 2 search-replaces in config.py + brain_agent.py + test files referencing the constant.

---

## 3. LOW 2 — Re-injection observability

### 3.1 Plan v1 §3.6 said (validation deferred to re-canary; observability minimal)

Plan v1 noted "ship simple re-injection now; defer auto-dismiss to follow-up if re-canary surfaces cost concern." But Plan v1 did not add explicit re-injection observability beyond the existing `[PromptPrefAgent] ... (nudge=yes/no)` log. Re-canary review would have to infer re-injection rate from raw log counts.

### 3.2 Plan v2 locks (~3 LOC per-turn re-injection log)

Add a per-turn log line in `get_prompt_addendum` when a persistent nudge re-injects:

```python
def get_prompt_addendum(self, person_id: str) -> str | None:
    parts: list[str] = []
    pref_text = self._brain_db.get_prompt_addendum(person_id)
    if pref_text:
        parts.append(pref_text)
    nudges = self._brain_db.get_pending_nudges(person_id, limit=1)
    if nudges:
        nudge = nudges[0]
        parts.append(
            f"[Proactive — work naturally into conversation if the moment fits: "
            f"{nudge['content']}]"
        )
        # D1: only mark one-shot types as injected.
        from core.config import ONE_SHOT_NUDGE_TYPES
        _nudge_type = nudge.get("nudge_type") or ""
        if _nudge_type in ONE_SHOT_NUDGE_TYPES:
            self._brain_db.mark_nudge_injected(nudge["id"])
        else:
            # LOW 2 (P0.S7.5 Plan v2) — re-injection observability for
            # re-canary cost validation. Persistent nudge types
            # (VISITOR_ALERT) re-inject every turn until expires/
            # dismissed. Log surfaces whether re-injection is bounded
            # (~1-3 turns before owner asks) or excessive (~20+ turns
            # during long sessions). If excessive → file follow-up for
            # auto-dismiss heuristic.
            print(
                f"[PromptPrefAgent] persistent nudge re-injected "
                f"(type={_nudge_type}, id={nudge['id']})"
            )
    if parts:
        print(
            f"[PromptPrefAgent] {len(parts)} addendum part(s) injected for {person_id} "
            f"(prefs={'yes' if pref_text else 'no'}, nudge={'yes' if nudges else 'no'})"
        )
    return "\n\n".join(parts) if parts else None
```

### 3.3 Rationale (auditor verdict adopted)

- Re-canary diff against this log surfaces re-injection rate quantitatively (count log lines per session)
- Bounded re-injection (~1-3 turns) = healthy: owner asks early in re-engagement, nudge dismissed implicitly by query resolution
- Excessive re-injection (~20+ turns) = signal to file follow-up with `auto_dismiss_on_acknowledge` heuristic
- Observability discipline matches P0.S7.1's `[SharedContext]` log pattern

### 3.4 Implementation choice — log only (no persistence)

Per auditor: "Even simpler: just count without persisting. Just log existence of re-injection."

Plan v2 locks: **log without persisting**. The `re_inject_count` field is NOT added to the nudge metadata. Each turn's log line is independent. Re-canary review counts log occurrences across the session.

Rationale: log-only is sufficient for the cost-validation use case. Persisting `re_inject_count` would require an UPDATE on every turn (added DB write cost — exactly what we're trying to measure). Log-only adds zero DB cost.

### 3.5 No test impact

The log line is observability only; tests don't assert on log content. Test surface unchanged at 16 (no new tests for LOW 2).

---

## 4. OBS A — D3 rename-failure stale-name ack (banking observation)

### 4.1 Auditor's banking observation

> "In Python 3.8+, `asyncio.CancelledError` inherits from `BaseException`, NOT `Exception` — so `except Exception` correctly does NOT catch `CancelledError`, preserving task cancellation semantics. Plan v1's framing is correct.
>
> However, one DOC precision worth banking: when `_session_store.rename` actually fails (DB lock, etc.), the swallow-and-log path means downstream `peek_snapshot` sees OLD name → canonical ack says 'Got it, visitor.' (the original bug case). D3 fixes the RACE (common); the RARE rename-failure case still has the bug."

### 4.2 Plan v2 banking (closure narrative documents as known limitation)

D3 closes the **race condition** (frequent) by replacing `create_task` with `await`. D3 does NOT close the **rename-failure** edge case (rare — DB lock, IO error, programming bug). In that edge case:

- `await _session_store.rename(...)` raises
- `except Exception as _rn_e: print(...)` swallows + logs
- Downstream `_post_tool_snap.person_name` reads OLD name (rename didn't succeed)
- Canonical ack says "Got it, {old_name}." — same bug shape as the race condition

**This is a known limitation**, not a new code change. Closure narrative explicitly documents:

> "D3 closes the canonical ack race condition (the common case observed in 2026-05-19 canary). When `_session_store.rename` itself fails (DB lock, IO error, programming bug — rare), the swallow-and-log path means downstream `peek_snapshot` reads the pre-rename name and the canonical ack speaks the wrong name. Acceptable trade-off: don't propagate the rename failure into a turn crash; one wrong ack in a rare failure scenario is better than ending the user's turn. If the rename-failure case becomes more common in production, file follow-up to propagate the failure into a user-facing hedge."

### 4.3 No code change

OBS A is **documentation-only at closure**. No Plan v2 code addition.

---

## 5. OBS B — D4 same-name (person_name == system_name) edge case

### 5.1 Auditor's banking observation

> "If `person_name == system_name` (user named the AI 'Lexi' and a person named 'Lexi' is in the household), both KNOWN SPEAKER IDENTITY and SYSTEM IDENTITY blocks reference the same name. Brain could conflate. Rare edge case; defer to actual occurrence."

### 5.2 Plan v2 disposition — defer

Two blocks render in `_build_system_prompt`:
- `<<<SYSTEM IDENTITY>>>` — gated on `system_name is not None`, renders AI's name
- `<<<KNOWN SPEAKER IDENTITY>>>` (D4 NEW) — gated on `session_person_type in ("known", "best_friend")`, renders person's name

When `system_name == person_name` (rare in practice; user would need to deliberately name the AI after a household member), both blocks render with the same name. Brain could conflate "your name is Lexi" + "your conversation partner's name is Lexi" semantically.

**Mitigation considered but rejected for P0.S7.5 scope:**
- Auto-disambiguation prefix ("[YOUR NAME] is Lexi" vs "[PARTNER'S NAME] is Lexi") — adds complexity for a rare case
- Renaming-on-conflict — heavy-handed UX
- Block-level mutex (suppress one block when names match) — loses information

**Plan v2 disposition**: defer. If the edge case actually surfaces in production (brain misattributes person ↔ system identity due to same-name conflict), file follow-up. Until then, the two block headers (`<<<SYSTEM IDENTITY>>>` vs `<<<KNOWN SPEAKER IDENTITY>>>`) provide sufficient semantic separation for the brain.

### 5.3 No code change

OBS B is **defer-to-actual-occurrence**. No Plan v2 code addition.

---

## 6. Q5 sub-observation banking — Phase 0 granularity correlation

### 6.1 Auditor's recognition

> "Architect's §2.7 observation is sharp: 'estimate accuracy correlates with Phase 0 D-decision granularity. Decomposed Phase 0 → accurate estimate; aggregated framing → wide miss.' The sub-observation has predictive power."

Track record matrix from auditor:

| Instance | Phase 0 granularity | Estimate accuracy |
|---|---|---|
| D-B | "8 surfaces" (decomposed) | High by 40% (21 vs 15 actual) |
| D-D | "7 helpers" (aggregated framing) | Low by 4× (40 vs 130 actual) |
| D-E | Single targeted helper | Low by 60% (3-5 vs 8 actual) |
| **P0.S7.5** | **5 D-decisions with explicit edit sites** | **On-target (12-19 vs 16 actual)** |

### 6.2 Plan v2 banking (memory file refinement at closure)

At Phase 4 closure, the architect MUST update `feedback_auditor_q5_estimates_trail_grep.md` to add the sub-observation:

> **Sub-observation (banked 2026-05-19 at P0.S7.5 closure):** estimate accuracy correlates with Phase 0 D-decision granularity. When Phase 0 decomposes into concrete D-decisions with named edit sites (P0.S7.5: 5 D-decisions each with explicit `core/X.py:LINE` references → on-target estimate), auditor Q5 estimates are accurate. When Phase 0 aggregates ("7 helpers," "3 components," "8 surfaces"), estimates drift wildly in either direction (D-B HIGH ~40%, D-D LOW ~4×, D-E LOW ~60%).
>
> Predictive implication for future Phase 0 audits: surface concrete D-decisions with named edit sites in audits to improve auditor Q5 accuracy as a side effect. The improvement is incidental — the primary benefit of granular Phase 0 is for the developer, but downstream estimate accuracy is a bonus.
>
> Not yet a separate discipline (1 sub-observation isn't a pattern). Track forward — if 2+ more cycles show the granularity correlation holds, consider elevating to a Phase 0 audit-drafting checklist item ("name explicit edit sites per D-decision").

### 6.3 No code change

Q5 banking is **memory file refinement only**. Updates `feedback_auditor_q5_estimates_trail_grep.md` at closure (Phase 4 step).

---

## 7. Updated D-decisions (Plan v2 final, supersedes Plan v1 §3-§7)

| ID | Plan v1 disposition | Plan v2 lock |
|---|---|---|
| D1 | `_ONE_SHOT_NUDGE_TYPES` frozenset; mark_injected gated by membership | **UPDATED — drop `_` prefix → `ONE_SHOT_NUDGE_TYPES`; add re-injection observability log** (LOW 1 + LOW 2) |
| D2 | New `get_recent_audience_rooms` helper + fallback branch in `build_shared_context_block` | UNCHANGED |
| D3 | `await _session_store.rename` (option a) | UNCHANGED; closure narrative documents rename-failure as known limitation (OBS A) |
| D4 | Tool description extension + `format_known_speaker_identity_block` helper + new flag + insertion gate | UNCHANGED; closure defers same-name edge case (OBS B) |
| D5 | HONESTY POLICY fabricated-absence bullet | UNCHANGED |

### 7.1 Phase decomposition (Plan v2 final — Phase 4 grows by 1 confirmation)

**Phase 1** — D1 + D2 unit tests. **+1 LOC re-injection log in D1.** ~4 hours (unchanged).
**Phase 2** — D3 + D4 + D5. ~3 hours (unchanged).
**Phase 3** — Behavioral integration. ~1.5 hours (unchanged).
**Phase 4** — **5 deliberate-regression confirmations** (was 4) + closure narrative + memory file updates. ~0.5 hours (negligible bump).

**Total: ~9 hours = 1.5 days.** Matches Plan v1 forecast.

### 7.2 Test surface forecast (Plan v2 final — unchanged from Plan v1)

| Phase | Tests |
|---|---|
| Phase 1 | 5 |
| Phase 2 | 8 |
| Phase 3 | 3 |
| Phase 4 | 0 new tests; **5 deliberate-regression confirmations** against existing tests |

**Plan v2 forecast: +16 tests (2404 → 2420).** Unchanged from Plan v1. Auditor-Q5 ON-TARGET confirmed: 12-19 estimate → 16 actual.

### 7.3 Closure narrative banking targets (Phase 4 final)

Phase 4 closure MUST bank:

1. **5 deliberate-regression confirmations** (a/b/c/d/e per §1.3 table) — all passing expected
2. **Sub-pattern A stays at 5 instances** (P0.S7.5 partial-falsification, NOT wholesale)
3. **Two-stage stays at 2 instances** (P0.S7.5 is single-stage targeted fix)
4. **`feedback_partial_falsification_tentative.md` 2nd instance banked** at architect-memory + framing re-evaluation note (§5.1 of audit)
5. **`feedback_auditor_q5_estimates_trail_grep.md` 4th instance update** + Phase 0 granularity sub-observation per §6.2 of Plan v2
6. **Canary-finding tracker bumps to 3rd instance** (toward potential `### Canary-surfaces-real-gaps` doctrine at 5+)
7. **OBS A (D3 rename-failure limitation)** + **OBS B (D4 same-name edge case)** documented in closure narrative
8. **CLAUDE.md "Pending Work" updates**: bundled-queue RE-CANARY trigger IMMEDIATELY (per auditor Q6) → on PASS fire combined Stage 2 PR (D-C Stage 2 + D-D Stage 2)

---

## 8. Risk + mitigation (Plan v2 deltas from Plan v1)

### 8.1 LOW 2 re-injection log noise

**Risk**: per-turn re-injection log fires every turn for the duration of a persistent nudge (~24h ceiling). In a busy session with VISITOR_ALERT pending, this could log ~50-100 lines per session.

**Mitigation**: log line is small (~60 chars per occurrence). Re-canary diff against the log is straightforward: `grep "persistent nudge re-injected" terminal_output.md | wc -l` counts re-injection rate. If noise proves excessive, follow-up converts to a counter (log once per session at start + once at end with delta).

**Trade-off accepted**: short-term log noise is fine for one re-canary cycle; LOW 2's goal is exactly to surface this data.

### 8.2 LOW 1 naming-convention search-replace blast radius

**Risk**: dropping `_` prefix means search-replace across `core/config.py` (definition) + `core/brain_agent.py` (import + usage) + any new tests referencing the constant.

**Mitigation**: Plan v1 had not yet shipped; Plan v2 locks the no-prefix naming from the start. Developer ships with `ONE_SHOT_NUDGE_TYPES` directly — no later search-replace needed. Plan v2 §2 explicitly notes this is the locked name.

---

## 9. Discipline-count predictions (Plan v2 final)

All counts unchanged from Plan v1 §10. No changes from auditor's Plan v1 verdict.

| Discipline | Status |
|---|---|
| Spec-first review cycle | 14-for-14 → **15-for-15** on closure ✓ |
| Sub-pattern A (`### Phase-0-catches-wrong-premise`) | **stays at 5 instances** (partial-falsification, not wholesale) ✓ |
| Tripwires-must-match-deferral-surface | stays **4-for-4** ✓ |
| Developer-improves-on-spec | stays **6-for-6** unless code phase surfaces mechanism improvement |
| Induction-surfaces-invariant-gaps | stays **7-for-7** unless Phase 4 surfaces real gap |
| Canary-finding tracker | **3rd instance** (P0.S7.5 canary-surfaced) ✓ |
| Canary-gate override (informal) | stays at **1** |
| Scope-expansion-via-Phase-0 (informal) | stays at **1** |
| Deferral-rationale-expires-when-downstream-ships (informal) | stays at **1** |
| Two-stage-canary-gated-cleanup (informal) | stays at **2** (P0.S7.5 single-stage) |
| Auditor-Q5-estimates-trail-grep (architect-memory) | **4th instance — first ON-TARGET** + Phase 0 granularity sub-observation banked |
| Partial-falsification-tentative (architect-memory only) | **2nd instance** — re-evaluate framing at closure |

---

## 10. Plan v2 deltas from Plan v1 — summary for auditor's review

| Section | Plan v1 | Plan v2 |
|---|---|---|
| Constant name (D1) | `_ONE_SHOT_NUDGE_TYPES` | **`ONE_SHOT_NUDGE_TYPES` (no underscore)** — LOW 1 |
| `get_prompt_addendum` (D1) | Mark-injected conditional only | **+ per-turn re-injection log line for persistent types** — LOW 2 (~3 LOC) |
| Phase 4 confirmations | 4 (D1/D2/D3/D5) | **5 (D1/D2/D3/D4/D5)** — MEDIUM 1 |
| D3 rename-failure | Implicit (caught by try/except) | **Explicit closure-narrative documentation of known limitation** — OBS A |
| D4 same-name (person == system) | Not addressed | **Explicit closure-narrative documentation; defer to actual occurrence** — OBS B |
| Q5 instance count | 4th instance noted | **+ Phase 0 granularity sub-observation banked in memory file** |
| Phase 1 time | ~4h | ~4h (LOW 2 adds ~3 LOC, negligible) |
| Phase 4 time | ~0.5h | ~0.5h (1 extra confirmation, ~5-10 min add) |
| Test count forecast | 16 | 16 (unchanged) |
| Suite delta forecast | 2404 → 2420 | 2404 → 2420 (unchanged) |

All deltas are tightenings, additions, or documentation. Nothing reversed.

---

## 11. Next steps

1. **Auditor reviews Plan v2.** If approved → joint sign-off cleared.
2. **No Plan v3 anticipated.** All 3 precision items locked verbatim from auditor's verdict. OBS A + OBS B adopted as closure-narrative entries. Q5 sub-observation banked at Phase 4.
3. **Developer handoff** with:
   - `tests/p0_s7_5_audit.md` (Phase 0 — APPROVED)
   - `tests/p0_s7_5_plan_v1.md` (Plan v1 — APPROVED with 3 precision items)
   - This document → `tests/p0_s7_5_plan_v2.md` (Plan v2 final — locks precision items + 2 banking observations)
   - `CLAUDE.md` for project rules + disciplines
   - `complete-plan.md` for P0.S7 narrative anchor
4. **Phase 1 ships** (~4h): D1 + D2 unit + 5 tests + `ONE_SHOT_NUDGE_TYPES` (no `_`) + re-injection log.
5. **Phase 2 ships** (~3h): D3 + D4 + D5 + 8 tests.
6. **Phase 3 ships** (~1.5h): 3 behavioral integration tests.
7. **Phase 4 ships** (~0.5h): **5 deliberate-regression confirmations** + closure narrative + memory file updates.
8. **Bundled-queue RE-CANARY runs IMMEDIATELY on P0.S7.5 closure.** Same scenario re-run: Jagan + ElevenLabs Lexi visitor + Jagan returns + canonical "who were you talking to" question. Expected post-P0.S7.5:
   - Turn 1 of Jagan's return: VISITOR_ALERT nudge injects (persistent; stays pending)
   - Marker `[visitor_id:lexi_xxx]` in prompt_addendum
   - VISITOR CONTEXT block renders with explicit "MUST call search_memory(person_name='Lexi')"
   - Brain calls `search_memory('Lexi', ...)` → returns Lexi's facts
   - Brain answers correctly with Lexi-specific content
   - On PASS: fire combined Stage 2 PR (D-C Stage 2 + D-D Stage 2 hard-deletes + 130 test-site migrations)
   - On FAIL with new root cause: diagnose; file another follow-up spec

---

## 12. Reference documents

- `tests/p0_s7_5_audit.md` — Phase 0 audit (APPROVED 2026-05-19 with 6 adjudications)
- `tests/p0_s7_5_plan_v1.md` — Plan v1 (APPROVED 2026-05-19 with 3 precision items + 2 banking observations + Q5 sub-observation)
- `tests/p0_s7_de_audit.md` + closure — D-E reference (1st partial-falsification instance)
- `tests/p0_s7_dd_audit.md` + closure — D-D reference (sub-pattern A 5th instance + doctrine elevation)
- `CLAUDE.md` `### Phase-0-catches-wrong-premise` doctrine
- **Canary terminal_output files (2026-05-19)**:
  - `terminal_output_2026-05-19_205906.md`
  - `terminal_output_2026-05-19_211154.md`
  - `terminal_output.md` (canary failure at turn 79)
- `core/brain_agent.py:8342-8363` — `PromptPrefAgent.get_prompt_addendum` (D1 + LOW 2 EDIT SITE)
- `core/config.py` — `ONE_SHOT_NUDGE_TYPES` constant (LOW 1 locked name)
- `core/brain.py:199-236` — `update_person_name` description (D4 EDIT SITE 1)
- `core/brain.py:2013-2049` — `format_system_identity_block` (D4 TEMPLATE)
- `core/brain.py:2222-2311` — HONESTY POLICY block (D5 EDIT SITE)
- `core/db.py:1296-1371` — `get_recent_room_conversation` (D-A; D2 reuses)
- `core/db.py` (new) — `get_recent_audience_rooms` (D2 NEW HELPER)
- `core/room_orchestrator.py:231-310` — `build_shared_context_block` (D2 EDIT SITE)
- `core/session_state.py:317-321` — `SessionStore.rename` async (D3 awaitable)
- `pipeline.py:3439` — `_handle_update_person_name` async def
- `pipeline.py:3766-3770` — D3 PRIMARY EDIT SITE (await rename)
- `pipeline.py:5777-5781` — canonical ack template (D3 BENEFICIARY)
- Memory: `feedback_spec_time_grep_verification.md` (4 instances; two-pass discipline) — Pass 1 applied at Plan v1
- Memory: `feedback_ast_forward_property_tests.md` (3 instances) — workhorse pair applied
- Memory: `feedback_auditor_q5_estimates_trail_grep.md` (3 → 4 instances at closure; **first ON-TARGET + Phase 0 granularity sub-observation banked**)
- Memory: `feedback_partial_falsification_tentative.md` (1 → 2 instances at closure; framing re-evaluation note)

---

**Standing by for auditor sign-off on Plan v2 → developer handoff → RE-CANARY immediately on closure.**

Plan v2 strictly tightens Plan v1; nothing reversed. All 3 precision items adopted verbatim; OBS A + OBS B adopted as closure-narrative-only; Q5 sub-observation banked at memory level. Suite delta forecast: **2404 → 2420 (+16 collected)**. Phase 4 confirmations: 4 → **5** (one per D-decision). Total effort: ~9 hours = 1.5 days. RE-CANARY trigger: IMMEDIATELY on closure.
