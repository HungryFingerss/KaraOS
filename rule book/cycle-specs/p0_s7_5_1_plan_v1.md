# P0.S7.5.1 — Visitor alert marker/metadata asymmetry fix — Plan v1

**Date:** 2026-05-19
**Author:** architect
**Status:** Plan v1 — locked at D1 Option 2 (regex-replace) per Phase 0 verdict 2026-05-19. **First artifact under strict-industry-standard mode** (per `feedback_strict_industry_standard_mode.md` locked 2026-05-19).

**Companion documents:**
- `tests/p0_s7_5_1_audit.md` — Phase 0 audit (APPROVED 2026-05-19 with all 7 adjudications matching architect's lean)
- `tests/p0_s7_5_1_plan_v2.md` — forthcoming if precision items surface (likely 1-2 small items at this scope)

**Strict-mode disciplines applied at drafting (visible-by-default per the locked operating mode):**

| Discipline | Where applied |
|---|---|
| Pre-mortem (5-10 failure modes) | §6 |
| Multi-direction invariant trace (forward/backward/sideways/lifecycle) | §4 |
| Invariant contract explicit-by-default (preserved/new/not-touched) | §5 |
| 11-gate quality checklist | §7 |
| Cross-spec impact analysis at Phase 0/v1 | §3 |
| Two-pass grep-verification (Pass 1 at drafting) | §2 |
| Honest scope at this cycle | §8 |
| Production-canary diff tracking | §10 (closure step) |
| Long-arc discipline tracking | §11 |

---

## 1. Auditor-locked scope (per Phase 0 verdict 2026-05-19)

| ID | D-decision | Severity | Source |
|---|---|---|---|
| D1 | `update_visitor_alert_for_promoted_person` regex-replace at `core/brain_agent.py:3043-3047` | LOAD-BEARING | Canary 2 failure (line 1187 of `terminal_output.md`) |

**No belt-and-braces upstream fix** (auditor adjudication Q2): if Option 2 is robust, fixing upstream would imply Option 2 isn't — contradicting the rationale. Upstream `[visitor_name:unknown]` marker stays as intentional placeholder semantics; D1 reconciles at promotion time.

**No D2-D5** at this scope. Single-D-decision mini-spec.

---

## 2. Pass 1 grep verification (2026-05-19 at Plan v1 drafting)

### 2.1 Direct edit site (D1 PRIMARY)

| File | Line | Class | Surface |
|---|---|---|---|
| `core/brain_agent.py` | 3043-3047 | `BrainDB` | Literal-substring check + replace — **D1 EDIT SITE** |
| `core/brain_agent.py` | 3035 | `BrainDB.update_visitor_alert_for_promoted_person` | `old_name = meta.get("visitor_name") or ""` (read, retained, but result becomes unused at line 3043) |

**Class-containment verified** (per `feedback_spec_time_grep_verification.md` instance 5 sub-observation): `update_visitor_alert_for_promoted_person` is method on `BrainDB` class (class defined at `core/brain_agent.py` near line 2270 — verified by grep at drafting).

### 2.2 Producers (backward trace)

| File | Line | Surface | Role |
|---|---|---|---|
| `core/brain_agent.py` | 7139-7144 | `_run_visitor_alert` content-marker write — stranger branch | Writes `[visitor_name:unknown]` marker |
| `core/brain_agent.py` | 7142-7144 | `_run_visitor_alert` content-marker write — known branch | Writes `[visitor_name:{person_name}]` marker |
| `core/brain_agent.py` | 7179 | `_run_visitor_alert` metadata write | Writes `meta["visitor_name"] = person_name` (always) |
| `core/brain_agent.py` | 7174 | `BrainDB.store_nudge` call | Persists content + metadata atomically |

**Producers UNCHANGED by D1**. The asymmetry between content marker (`unknown`) and metadata field (`visitor`) stays intentional.

### 2.3 Consumers (forward trace)

| File | Line | Surface | Role |
|---|---|---|---|
| `core/brain_agent.py` | 8342-8390 | `BrainOrchestrator.get_prompt_addendum` | Reads `nudges[0]['content']` → injects into prompt_addendum |
| `core/brain.py` | 2569-2570 | `_build_system_prompt` VISITOR CONTEXT block reader | `re.search(r"\[visitor_name:([^\]]+)\]", prompt_addendum)` extracts visitor name |
| `core/brain.py` | 2583 | VISITOR CONTEXT block gate | `if _visitor_name and _visitor_name.lower() not in ("unknown", "")` — D1 result flips this from False (broken) to True (fixed) |
| `core/brain.py` | 2593-2610 | VISITOR CONTEXT block name-known branch | Fires after D1 fix; directs brain to call `search_memory(person_name='Lexi', ...)` |

**Consumers UNCHANGED by D1**. The reader regex shape (`[^\]]+`) matches the writer regex shape D1 introduces (symmetric pattern).

### 2.4 Sideways (concurrent writers to nudges table)

| File | Line | Surface | Column touched |
|---|---|---|---|
| `core/brain_agent.py` | 3063-3068 | `mark_nudge_injected` | `injected_at` (different column) |
| `core/brain_agent.py` | 3070-3074 | `dismiss_nudge` | `dismissed_at` (different column) |
| `core/brain_agent.py` | 3077-3098 | `nudge_exists` | Read-only |

**No concurrent writer to `content` column.** SQLite row-level atomicity covers the concurrent-`injected_at`/`content` UPDATE case. No race.

### 2.5 Test surface — pre-emptive estimate confirmed

Per auditor Q5 verdict + Phase 0 granularity self-test: **5 tests** locked.

| # | Test | Phase | Type |
|---|---|---|---|
| 1 | `test_regex_swaps_existing_marker` | 1 | Unit |
| 2 | `test_regex_noop_when_marker_absent` | 1 | Unit |
| 3 | `test_regex_idempotent_when_already_renamed` | 1 | Unit |
| 4 | `test_update_alert_uses_regex_not_literal_substring` | 1 | AST forward-property |
| 5 | `test_visitor_alert_marker_swap_e2e` | 2 | Behavioral E2E |

**Suite delta forecast: 2421 → 2426 (+5).** Auditor-Q5 5th instance prediction: ON-TARGET (self-test of Phase 0 granularity sub-observation).

---

## 3. Cross-spec impact analysis (strict-mode discipline)

### 3.1 Specs touching `update_visitor_alert_for_promoted_person` (the D1 edit site)

| Spec | Disposition |
|---|---|
| **Session 114 Part 5** (2026-04-25) | Created the method with the literal-substring check. D1 fixes its shipped behavior. NOT a regression of S114; it's a correctness improvement on top. |
| **Session 100 Bug G** | Established `[visitor_name:X]` marker convention in `_run_visitor_alert`. D1 preserves the marker shape; only changes how it's swapped. |
| **Session 96 Bug 2** | Established VISITOR CONTEXT block reader. D1 preserves the reader contract; only fixes the writer's swap semantic. |
| **P0.S7.5 D1** (P0.S7.5 main) | Established persistent nudge re-injection via `ONE_SHOT_NUDGE_TYPES` exemption. D1 of P0.S7.5.1 is downstream: persistent injection means the broken marker re-injects every turn (worse than one-shot would have been). D1 fix is necessary downstream of P0.S7.5's persistence change. |

**No cross-spec conflicts.** D1 is the natural next step in the visitor-alert correctness arc. No upstream spec assumes the literal-substring check works; no downstream spec depends on the broken behavior.

### 3.2 Specs that would be affected if D1 introduces regression

If D1's regex pattern misfires (false-positive on LLM-generated content containing literal `[visitor_name:X]`):
- **Session 113 P3B.3** ADDRESS DECISION marker (`[addressing:X]`) — different marker name; not affected.
- **Session 96 Bug G** safety flags marker (`[safety_flags:X]`) — different marker name; not affected.
- **No other `[*:X]` markers** in the codebase per grep at drafting (verified `\[[a-z_]+:` against `core/` — only visitor_name, visitor_id, safety_flags, addressing).

**Regression risk: LOW.** D1's regex pattern is `\[visitor_name:[^\]]+\]` specifically; collision with other marker namespaces is impossible.

### 3.3 Specs anticipated downstream of D1

| Spec | Relationship |
|---|---|
| **Bundled Stage 2 PR** (D-C Stage 2 + D-D Stage 2) | RE-CANARY 3 gates this PR. D1 must pass canary 3 first. |
| **Future OBS C resolution** (multi-pid visitor split) | Different bug (pre-existing); not blocked by D1. May surface during canary 3 but is out-of-scope. |
| **P1.A16 event sourcing** (complete-plan.md) | Future event log will record nudge state mutations. D1's correctness is a precondition for honest replay. |

---

## 4. Multi-direction invariant trace (strict-mode discipline)

### 4.1 Forward (consumers downstream of D1's mutation)

```
update_visitor_alert_for_promoted_person (D1 PRIMARY)
    ↓ writes nudges.content with corrected [visitor_name:X] marker
BrainOrchestrator.get_prompt_addendum (PromptPrefAgent class)
    ↓ reads nudge content (persistent re-injection per P0.S7.5 D1)
    ↓ injects content into prompt_addendum
_build_system_prompt
    ↓ regex-extracts [visitor_name:X] marker (core/brain.py:2570)
    ↓ branch decision at line 2583 (name-known vs unknown)
LLM (Together.ai Llama-3.3-70B)
    ↓ receives VISITOR CONTEXT block with explicit search_memory(person_name='X', ...) directive
    ↓ calls search_memory tool with correct entity
search_memory tool handler
    ↓ returns Lexi's facts (entity='Lexi' matches brain.db rows)
LLM response
    ↓ surfaces Lexi by name + discussion content
TTS
    ↓ user hears "I was talking to Lexi about..."
```

**All forward consumers preserve their existing contracts.** D1 changes WHAT the marker says, not HOW it's consumed.

### 4.2 Backward (producers upstream of D1's input)

```
_run_visitor_alert (session-end hook)
    ↓ stranger branch: name_marker = "[visitor_name:unknown]" (line 7141)
    ↓ known branch:    name_marker = f"[visitor_name:{person_name}]" (line 7144)
    ↓ writes content + metadata atomically via store_nudge
BrainDB.store_nudge
    ↓ INSERT into proactive_nudges
[time passes; visitor named Lexi via update_person_name]
update_person_name handler (pipeline.py)
    ↓ on stranger promotion → calls _brain_orchestrator.on_identity_confirmed
BrainOrchestrator.on_identity_confirmed
    ↓ calls update_visitor_alert_for_promoted_person(person_id, new_name='Lexi')
update_visitor_alert_for_promoted_person (D1 PRIMARY)
    ↓ INPUTS: person_id, new_name (from caller); meta + content (from DB)
```

**Two upstream writers** to the nudge content lifecycle:
1. **`_run_visitor_alert`** (birth) — writes initial content with `[visitor_name:unknown]` or `[visitor_name:{name}]`
2. **`update_visitor_alert_for_promoted_person`** (mutation) — D1 PRIMARY EDIT SITE

D1 trusts the producer marker format but doesn't constrain it. Robust to:
- `[visitor_name:unknown]` (stranger placeholder)
- `[visitor_name:visitor]` (hypothetical alternative placeholder — not currently produced but D1 handles it)
- `[visitor_name:Lexi]` (already-named visitor — idempotent re-rename works)
- `[visitor_name:Anne-Marie]` (multi-word with hyphen)
- `[visitor_name:José]` (Unicode)

### 4.3 Sideways (parallel writers to same state)

`nudges` row identified by `id`. Three concurrent writers exist:

| Writer | Column | Conflict with D1's `content` write |
|---|---|---|
| `update_visitor_alert_for_promoted_person` (D1) | `content`, `metadata` | Self — runs atomically within transaction |
| `mark_nudge_injected` (P0.S7.5 D1) | `injected_at` | None — different column; SQLite row-level UPDATE atomicity |
| `dismiss_nudge` | `dismissed_at` | None — different column |

**No `content`-column race**. SQLite's row-level atomicity covers concurrent column UPDATEs.

### 4.4 Lifecycle (birth → mutation → consumption → death)

```
BIRTH:    _run_visitor_alert queues nudge at session-end
          content = "{display_name} stopped by while you were away... [visitor_name:unknown] [visitor_id:Y] [safety_flags:...]"
          metadata = {visitor_id, visitor_name=person_name, visitor_type='stranger', turn_count, safety_flags}
          injected_at = NULL
          dismissed_at = NULL
          expires_at = now + 86400 (24h)

MUTATION 1 (D1 PRIMARY):
          update_visitor_alert_for_promoted_person fires when stranger promoted to known via update_person_name
          AFTER D1: content's [visitor_name:X] swapped to [visitor_name:Lexi] via regex
          metadata.visitor_name = 'Lexi', metadata.visitor_type = 'known'

CONSUMPTION:
          Every turn (per P0.S7.5 D1 persistent re-injection):
              BrainOrchestrator.get_prompt_addendum reads pending nudges
              VISITOR_ALERT type is NOT in ONE_SHOT_NUDGE_TYPES → stays pending
              content injected into prompt_addendum every turn until expired/dismissed
          Every turn while nudge active:
              _build_system_prompt re-extracts [visitor_name:Lexi] marker
              VISITOR CONTEXT block fires name-known branch
              LLM sees explicit directive to query search_memory(person_name='Lexi', ...)

DEATH:    expires_at past (24h after birth) → get_pending_nudges filter excludes
          OR dismissed_nudge called → dismissed_at set → excluded
```

**D1 only touches MUTATION 1**. Birth, Consumption, Death unchanged.

---

## 5. Invariant contract (strict-mode discipline)

### 5.1 Invariants D1 PRESERVES

- **Single-string nudge content** with embedded markers (`[visitor_name:X]`, `[visitor_id:Y]`, `[safety_flags:...]`)
- **JSON metadata** remains canonical typed source for `visitor_id`, `visitor_name`, `visitor_type`, `turn_count`, `safety_flags`
- **Atomic single-row UPDATE** within existing transaction context (preserves `_in_outer_tx` gate at line 3055)
- **Backward compat** with pre-existing nudges: regex-replace handles ANY marker placeholder, including legacy `[visitor_name:visitor]` if any production data was written that way
- **Method signature**: `update_visitor_alert_for_promoted_person(self, person_id: str, new_name: str) -> int` unchanged
- **Return semantic**: `int` count of updated alerts unchanged
- **Existing observability log** at line 3057-3060 unchanged
- **Persistent re-injection** (P0.S7.5 D1 contract) — VISITOR_ALERT stays out of `ONE_SHOT_NUDGE_TYPES`; D1 only fixes the corruption of content during persistence

### 5.2 Invariants D1 ESTABLISHES (new)

- **Marker-metadata reconciliation invariant**: after `update_visitor_alert_for_promoted_person` returns successfully, the `[visitor_name:X]` marker in `content` and the `visitor_name` field in `metadata` MUST agree (X = new_name parameter).
  - **Formal**: ∀ nudge n where `update_visitor_alert_for_promoted_person(pid, new_name)` returns truthy → `re.search(r"\[visitor_name:([^\]]+)\]", n.content).group(1) == n.metadata['visitor_name'] == new_name`
- **Placeholder-robust swap**: regex-replace works for ANY current marker value (`unknown`, `visitor`, `Lexi`, hypothetical future placeholders).
  - **Formal**: ∀ content c containing `[visitor_name:X]` for any X ≠ `]` → `update_visitor_alert_for_promoted_person(pid, Y)` produces content with `[visitor_name:Y]` substituted at the original position.
- **Idempotency**: re-running with the same `new_name` is byte-identical no-op.
  - **Formal**: ∀ content c → `update_alert(pid, Y); update_alert(pid, Y)` produces same c as single call

### 5.3 Invariants D1 explicitly does NOT touch (out-of-scope, declared)

- **`_run_visitor_alert` marker-vs-metadata asymmetry at queue time** (`name_marker = "[visitor_name:unknown]"` + `meta["visitor_name"] = "visitor"` for stranger sessions): intentionally retained. Option 2 makes this asymmetry harmless. Fixing it would contradict the Option 2 rationale per auditor Q2.
- **VISITOR CONTEXT block reader regex** (`core/brain.py:2570`): unchanged.
- **Marker shape `[visitor_name:X]`**: unchanged.
- **`ONE_SHOT_NUDGE_TYPES` membership** (P0.S7.5 D1): unchanged.
- **Multi-pid visitor split** (canary 2 OBS C: `stranger_visitor_5a1594` alongside `stranger_visitor_511257`): out-of-scope per auditor Q6. Different root cause; future spec.
- **Existing broken nudges in production from canary 2 era**: stay broken until they expire (24h). Factory reset before canary 3 wipes them. No migration shipped. Documented as known limitation in closure narrative.

---

## 6. Pre-mortem (strict-mode discipline)

10 most-likely failure modes for D1, with mitigation status:

| # | Failure mode | Mitigation | Severity |
|---|---|---|---|
| 1 | Regex false-positive on LLM-generated content containing literal `[visitor_name:X]` shape | Bounded: visitor_alert content is system-generated (from `_run_visitor_alert`), NOT LLM-generated. The only LLM-touched field is the brain's prose response, which is never written into nudge content. Risk = effectively zero. | Low |
| 2 | Multi-marker content (two `[visitor_name:X]` markers in same content) | `re.sub` default replaces ALL occurrences. After D1: all markers identical. Downstream `re.search` returns FIRST (matches). No regression even on hypothetical multi-marker content. | Low |
| 3 | Empty `new_name` parameter | Marker becomes `[visitor_name:]` (regex's `[^\]]+` requires ≥1 char). Reader's regex would NOT match → falls back to unknown branch. Caller-side guard: `BrainOrchestrator.on_identity_confirmed` only calls when `new_name` is non-empty per its existing contract. Defensive guard at the writer is unnecessary. | Low |
| 4 | Concurrent calls to D1 for the same nudge_id | Single async path: `_brain_orchestrator.on_identity_confirmed` is the sole caller. No concurrent invocation possible. SQLite row-level atomicity is the floor anyway. | Low |
| 5 | Idempotency under repeated calls | Verified: regex pattern matches `[visitor_name:Lexi]`, replaces with `[visitor_name:Lexi]`, byte-identical. Test 3 explicitly covers. | Low |
| 6 | In-transaction safety with existing `_in_outer_tx` gate | D1 change is purely in the value being written (`new_content`), not the UPDATE structure. Existing transaction semantic preserved. | Low |
| 7 | Existing broken nudges in production (canary 2 era) stay broken | Factory reset before canary 3 wipes them. In production, broken nudges expire after 24h naturally. NO MIGRATION SHIPPED. Documented as known limitation in closure narrative. Acceptable; matches the canary discipline of factory-reset-between-canaries. | Medium (documented) |
| 8 | Visitor name containing `]` character (e.g., `[visitor_name:Le]xi]`) | `re.sub` pattern `[^\]]+` is greedy-until-first-`]`. A name with `]` would produce nested-bracket marker. Reader's regex same shape. Symmetric handling. Visitor names don't contain `]` in practice (no enrollment path accepts it). | Low |
| 9 | Visitor name with Unicode chars (e.g., `Lexi García`) | `re.sub` pattern `[^\]]+` matches all non-`]` chars including Unicode. No encoding issue. | Low |
| 10 | Test isolation: in-memory test DBs leak between tests | Existing pattern in `tests/conftest.py` uses `tmp_path` fixture per-test. Memory-DB isolation by default. No interaction. | Low |

**11 — bonus, banked from auditor Q7 observations:**

| # | Failure mode | Mitigation | Severity |
|---|---|---|---|
| 11 | Concurrent `mark_nudge_injected` (P0.S7.5 D1) + `update_visitor_alert_for_promoted_person` (D1) for same nudge_id | Different columns (`injected_at` vs `content`). SQLite row-level atomicity covers. Auditor Q7 confirmed no race. | Low |

**Pre-mortem result**: 10 modes Low risk; 1 (broken nudges in production) documented Medium with accepted limitation; 0 blocking. **Ship cleared.**

---

## 7. 11-gate quality checklist (strict-mode discipline)

Each gate either: ✓ (passes), N/A (not applicable, with rationale), or ⚠️ (needs attention).

| # | Gate | Status | Rationale |
|---|---|---|---|
| 1 | **Correctness** | ✓ | 4-axis trace complete (§4); invariants explicit (§5); pre-mortem clean (§6) |
| 2 | **Security** | N/A | No new attack surface. Visitor_alert is internal context; regex pattern bounded to bracket-delimited marker namespace; no user-controlled input. Auditor Q7 confirmed. |
| 3 | **Privacy** | ✓ | No change to audience filtering or tier classification. Nudge content already privacy-scoped (system_only by default per existing design). Marker swap is metadata-correctness, not privacy mechanism. |
| 4 | **Performance** | ✓ | Regex on <1KB string per nudge per promotion event (rare event). Negligible overhead vs current `str.replace`. Promotion fires at most N times per session (N = number of stranger-promotions). Cost: <1ms per call. |
| 5 | **Observability** | ✓ | Existing log `[BrainDB] update_visitor_alert_for_promoted_person: updated N alert(s)` retained. Implicit observability via canary log: when D1 works, no more `Tool: search_memory('Jagan', 'visitor')` queries (asker-name fallback gone). No new log line needed; existing line surfaces the success path correctly. |
| 6 | **Test pyramid** | ✓ | 3 unit (regex) + 1 AST (forward-property) + 1 behavioral E2E. Pyramid shape correct for single-D-decision mini-spec. |
| 7 | **Regression guards** | ✓ | Test 5 (E2E) directly defends against the canary 2 failure mode: queue with `[visitor_name:unknown]` → promote to Lexi → assert marker becomes `[visitor_name:Lexi]` AND reader extracts `_visitor_name = 'Lexi'`. |
| 8 | **Pre-mortem** | ✓ | 10 + 1 bonus failure modes listed (§6); all Low risk or documented Medium with accepted limitation. |
| 9 | **Multi-direction trace** | ✓ | Forward (§4.1) + Backward (§4.2) + Sideways (§4.3) + Lifecycle (§4.4) all named. |
| 10 | **Backward compat** | ⚠️ | Existing broken nudges in production (canary 2 era) stay broken — documented as known limitation. New nudges work correctly. Factory-reset between canaries wipes production state for fresh testing. No migration script. |
| 11 | **Doc updates queued** | ✓ | CLAUDE.md header narrative entry; complete-plan.md P0.S7.5.1 entry; memory file updates (`feedback_auditor_q5_estimates_trail_grep.md` 5th instance with Phase 0 granularity confirmation). |

**Gates result**: 9 ✓ + 1 N/A + 1 ⚠️ (accepted limitation documented). **Sign-off threshold met.**

---

## 8. D1 implementation contract

### 8.1 Specifies WHAT, not HOW

Replace literal-substring marker swap at `core/brain_agent.py:3043-3047` with regex-based swap. Developer chooses exact code shape within these constraints.

### 8.2 Reference implementation (template)

```python
# P0.S7.5.1 D1 — regex-replace the [visitor_name:...] marker regardless
# of what placeholder is currently in content. The previous literal-
# substring check (Session 114 Part 5) only fired when the old_name
# from metadata matched the marker — but _run_visitor_alert writes
# ASYMMETRIC content (marker="[visitor_name:unknown]") and metadata
# (visitor_name="visitor") for stranger sessions, so the old check
# silently no-op'd on every stranger promotion. Regex-replace is
# robust to the asymmetry (and to any future placeholder drift).
# Canary 2 evidence: 2026-05-19 terminal_output.md:857 + :1187.
new_content = content
if content:
    new_content = re.sub(
        r"\[visitor_name:[^\]]+\]",
        f"[visitor_name:{new_name}]",
        content,
    )
```

### 8.3 Required changes

1. **At line 3043-3047**: replace literal-substring check + `content.replace(...)` with `re.sub` per §8.2 template.
2. **At top of file**: verify `import re` is already present (Plan v1 Pass 1 grep confirms it is — `core/brain_agent.py` uses `re` in multiple places).
3. **NO change** to:
   - Method signature
   - Return semantic
   - Observability log (line 3057-3060)
   - Transaction context (line 3055)
   - Metadata write (line 3036)

### 8.4 Invariants enforced by the contract

Per §5.2:
- Marker-metadata reconciliation
- Placeholder-robust swap
- Idempotency

---

## 9. Test surface (detailed)

### 9.1 Test 1 — `test_regex_swaps_existing_marker` (Phase 1, unit)

**Purpose**: D1's primary happy path.

**Setup**: in-memory `BrainDB`. Direct INSERT into `proactive_nudges` with `content = '... [visitor_name:unknown] ...'` + `metadata = {"visitor_id": "p1", "visitor_name": "visitor"}` + `nudge_type='VISITOR_ALERT'` + `injected_at=NULL`.

**Action**: call `update_visitor_alert_for_promoted_person(person_id='p1', new_name='Lexi')`.

**Assert**:
- Return value == 1
- `nudges.content` LIKE `%[visitor_name:Lexi]%`
- `nudges.content` NOT LIKE `%[visitor_name:unknown]%`
- `nudges.metadata` parsed as JSON has `visitor_name == 'Lexi'` AND `visitor_type == 'known'`

### 9.2 Test 2 — `test_regex_noop_when_marker_absent` (Phase 1, unit)

**Purpose**: D1 defensive — if content somehow lacks the marker (legacy data, schema change), no error + no spurious write.

**Setup**: same as Test 1 but `content = 'plain text with no markers'`.

**Action**: call `update_visitor_alert_for_promoted_person(person_id='p1', new_name='Lexi')`.

**Assert**:
- Return value == 1 (metadata still updated)
- `nudges.content == 'plain text with no markers'` (unchanged — no marker to swap)
- `nudges.metadata` has `visitor_name == 'Lexi'`

### 9.3 Test 3 — `test_regex_idempotent_when_already_renamed` (Phase 1, unit)

**Purpose**: D1 idempotency invariant.

**Setup**: same as Test 1 but `content` already has `[visitor_name:Lexi]`.

**Action**: call `update_visitor_alert_for_promoted_person(person_id='p1', new_name='Lexi')`.

**Assert**:
- Return value == 1
- `nudges.content` byte-identical to setup state (no spurious modification)

### 9.4 Test 4 — `test_update_alert_uses_regex_not_literal_substring` (Phase 1, AST forward-property)

**Purpose**: D1 structural invariant — AST asserts the method body uses `re.sub` (or `re.compile + .sub`) and does NOT use the literal-substring pattern.

**Implementation**: parse `core/brain_agent.py` AST; locate `update_visitor_alert_for_promoted_person` function; walk body; assert:
- A `Call` node referencing `re.sub` exists
- No `Call` node referencing `.replace(` with first argument being an f-string literal `f"[visitor_name:{old_name}]"` exists
- The visitor_name substitution is done via regex pattern

**Why AST not source-inspection**: avoids the adjacent-string-literal false-positive pattern (per `feedback_adjacent_string_literal_normalizer.md`); AST sees structure, not text.

### 9.5 Test 5 — `test_visitor_alert_marker_swap_e2e` (Phase 2, behavioral E2E)

**Purpose**: D1 full lifecycle — defends against the exact canary 2 failure mode.

**Setup**:
1. Tmp-path `BrainDB` + `FaceDB` via fixture
2. Open stranger session via SessionStore
3. Add a conversation_log row to give the stranger turn_count >= 1
4. Call `BrainOrchestrator._run_visitor_alert(stranger_pid)` — queues VISITOR_ALERT with `[visitor_name:unknown]` marker (stranger branch)
5. Verify nudge in DB has `content` containing `[visitor_name:unknown]`
6. Update person name via `db.update_person_name(stranger_pid, 'Lexi')`
7. Call `BrainOrchestrator.on_identity_confirmed(stranger_pid, old_name='visitor', new_name='Lexi')` — triggers `update_visitor_alert_for_promoted_person`

**Assert**:
- Nudge content's marker is now `[visitor_name:Lexi]` (NOT `[visitor_name:unknown]`)
- Nudge metadata has `visitor_name == 'Lexi'`
- Simulating the VISITOR CONTEXT block reader: `re.search(r"\[visitor_name:([^\]]+)\]", content)` extracts `'Lexi'`
- Result NOT in `('unknown', '')` → name-known branch would fire downstream

**Test name follows existing convention**: file at `tests/test_p0_s7_5_1.py` (per auditor Q7 observation on naming).

---

## 10. Phase decomposition

### 10.1 Phase 1 — D1 implementation + 4 tests (~2 hours)

**Surfaces shipped:**
- Edit `update_visitor_alert_for_promoted_person` at `core/brain_agent.py:3043-3047`: replace literal-substring with `re.sub` per §8.2 template
- New test file `tests/test_p0_s7_5_1.py` with tests 1, 2, 3 (unit) + test 4 (AST forward-property)

**Verification step**: full-suite run; expected delta 2421 → 2425 (+4 from Phase 1).

### 10.2 Phase 2 — Behavioral E2E + closure narrative (~0.5-1 hour)

**Surfaces shipped:**
- Test 5 (E2E) added to `tests/test_p0_s7_5_1.py`
- Closure narrative drafted in `CLAUDE.md` header + `complete-plan.md` P0.S7.5.1 entry
- Memory file updates queued (architect-side: `feedback_auditor_q5_estimates_trail_grep.md` 5th instance with Phase 0 granularity confirmation)

**Verification step**: full-suite run; expected delta 2425 → 2426 (+1 from Phase 2). Total cumulative: +5.

### 10.3 Phase 3 — Deliberate-regression confirmation + memory file finalization (~0.25 hours)

**Confirmation (a)**: revert `re.sub` → literal-substring at the edit site → run test 5 → expect test 5 FAILS with assertion error (marker stays `[visitor_name:unknown]`).

Revert the regression; run test 5 → expect PASS.

**Production-canary diff tracking step**: closure narrative MUST diff canary 2 vs (predicted) canary 3:
- Canary 2 failure: `Tool: search_memory('Jagan', 'visitor')` + TTS "Someone stopped by but didn't tell me their name"
- Canary 3 expected: `Tool: search_memory(person_name='Lexi', ...)` + TTS includes Lexi by name

**Memory updates at closure (Phase 3 step):**
- `feedback_auditor_q5_estimates_trail_grep.md`: 5th instance. Pre-emptive estimate 4-5; Plan v1 locked at 5; closure delta = 5 actual. Phase 0 granularity sub-observation CONFIRMED: high-granularity Phase 0 (1 D-decision, 1 edit site) → on-target estimate even at mini-spec scale.
- `MEMORY.md` index: refresh auditor-Q5 line to 5 instances.

### 10.4 Total effort

**~3 hours = half-day.** Matches "mini follow-up spec" framing.

---

## 11. Discipline-count predictions (strict-mode discipline)

| Discipline | Pre-P0.S7.5.1 | Post-closure |
|---|---|---|
| Spec-first review cycle | 15-for-15 | **16-for-16** ✓ |
| Sub-pattern A (`### Phase-0-catches-wrong-premise`) | 5 instances | stays at **5** (pre-audit hypothesis matched grep — not wrong-premise) |
| Tripwires-must-match-deferral-surface | 4-for-4 | stays **4-for-4** |
| Developer-improves-on-spec | 6-for-6 | stays **6-for-6** unless code phase surfaces a mechanism improvement |
| Induction-surfaces-invariant-gaps | 7-for-7 | stays **7-for-7** unless Phase 3 surfaces real gap |
| Canary-finding tracker | 3 instances | **4th instance** (P0.S7.5.1 canary-surfaced) — approaching 5+ doctrine threshold |
| Canary-gate override (informal) | 1 instance | stays at **1** |
| Scope-expansion-via-Phase-0 (informal) | 1 instance | stays at **1** |
| Deferral-rationale-expires-when-downstream-ships (informal) | 1 instance | stays at **1** |
| Two-stage-canary-gated-cleanup (informal) | 2 instances | stays at **2** (P0.S7.5.1 single-stage) |
| Auditor-Q5-estimates-trail-grep (architect-memory) | 4 instances (1 ON-TARGET) | **5th instance** — Phase 0 granularity self-test CONFIRMED |
| Partial-falsification-tentative (architect-memory only) | 2 instances | stays at **2** — re-evaluation pending at instance 3 |
| Spec-time grep-verification (architect-memory) | 5 instances + class-containment sub-observation | stays at **5** unless Plan v1/closure surfaces drift (Pass 1 applied; Pass 2 at closure) |
| **NEW: Strict-industry-standard mode** (auto-memory, 0 instances pre-P0.S7.5.1) | — | **1st instance APPLIED** at Plan v1 — operational test: pre-mortem + multi-direction trace + 11-gate checklist all visible in this Plan v1 |

---

## 12. Plan v1 → Plan v2 anticipated precision items

Per auditor's Phase 0 verdict: "likely 1-2 small items" at this scope.

1. **§9.5 E2E test fixture standardization** — Plan v1 sketches E2E setup inline. Auditor may want fixture builder reused from `tests/fixtures/event_log_fixtures.py` per P0.0.7 pattern. Minor refactor.

2. **§8.3 import re grep verification at Plan v2** — Plan v1 §8.3 claims `import re` is already present in `core/brain_agent.py`. Auditor may want explicit grep evidence in Plan v2. (Plan v1 drafting confirmed via grep at §2 surface map, but a Plan v2 grep-verification annotation would be tighter.)

3. **§7 backward compat gate (⚠️)** — Plan v1 documents the existing-broken-nudges-stay-broken limitation. Auditor may want this surfaced more prominently in the closure narrative (e.g., a dedicated "Known Limitations" subsection).

None of these are blockers. Plan v2 anticipated to be ~1 page refinement.

---

## 13. Reference documents

- `tests/p0_s7_5_1_audit.md` — Phase 0 audit (APPROVED 2026-05-19 with all 7 adjudications matching architect's lean)
- `tests/p0_s7_5_audit.md` + closure + canary-2 result — preceding P0.S7.5 reference
- `tests/p0_s7_5_plan_v1.md` + `plan_v2.md` — P0.S7.5 plans (architect's lean on Option 2 confirmed there)
- `CLAUDE.md` `### Phase-0-catches-wrong-premise` doctrine — applied at audit §1.2
- **Canary 2 evidence (terminal_output.md, 2026-05-19)**:
  - Line 790: initial visitor_alert queued
  - Line 857: `update_visitor_alert_for_promoted_person: updated 1 alert(s)` — metadata updated, content marker stayed broken
  - Line 1170: persistent nudge re-injection (P0.S7.5 D1 working)
  - Line 1179: `Tool: search_memory('Jagan', 'visitor')` — entity defaulted to asker (canary failure)
  - Line 1187: TTS "Someone stopped by but didn't tell me their name..." — unknown-branch template
  - Line 1242: subsequent turn `Tool: search_memory('unknown', 'conversation')` — symptom of upstream bug
- `core/brain_agent.py:3043-3047` — D1 PRIMARY EDIT SITE (literal-substring → regex)
- `core/brain_agent.py:7139-7144` — `_run_visitor_alert` stranger marker (upstream, unchanged)
- `core/brain_agent.py:7179` — `_run_visitor_alert` metadata write (upstream, unchanged)
- `core/brain.py:2569-2570` — VISITOR CONTEXT block reader (downstream, unchanged)
- `core/brain.py:2611-2618` — unknown-branch template (will NOT fire after D1 fix)
- Memory: `feedback_strict_industry_standard_mode.md` (locked 2026-05-19) — **FIRST APPLICATION** at Plan v1
- Memory: `feedback_spec_time_grep_verification.md` (5 instances + class-containment sub-observation) — Pass 1 applied at §2; Pass 2 at closure
- Memory: `feedback_auditor_q5_estimates_trail_grep.md` (4 → 5 instances at closure with Phase 0 granularity confirmation)
- Memory: `feedback_partial_falsification_tentative.md` (2 instances; not bumping per §11)

---

## 14. Closure narrative banking targets (Phase 3 final step)

1. **1 deliberate-regression confirmation** (revert regex → literal-substring) — expected passing
2. **Sub-pattern A stays at 5** (not a wrong-premise instance)
3. **Canary-finding tracker bumps to 4th instance** in CLAUDE.md informal observations — track toward 5+ doctrine elevation as `### Canary-surfaces-real-gaps`
4. **`feedback_auditor_q5_estimates_trail_grep.md` 5th instance** with Phase 0 granularity confirmation: high-granularity Phase 0 (1 D-decision + 1 edit site) → on-target estimate at mini-spec scale → sub-observation has predictive power even at smallest scope
5. **Strict-industry-standard mode 1st application** banked in closure narrative — this Plan v1 is the canonical reference for future strict-mode Plan v1 drafts
6. **CLAUDE.md "Pending Work" updates**: re-canary 3 trigger AFTER P0.S7.5.1 closure → on PASS fire combined Stage 2 PR (D-C Stage 2 + D-D Stage 2)
7. **Production-canary diff**: canary 2 failure markers (asker-name search, unknown-branch template) vs canary 3 expected (Lexi-name search, name-known branch). Bank the diff explicitly.

---

**Standing by for auditor review of Plan v1. Anticipated precision items per §12.**

Plan v1 forecast: 5 tests (Phase 1: 3 unit + 1 AST; Phase 2: 1 E2E). Suite delta: **2421 → 2426 (+5)**. Total effort: ~3 hours. Phase 4 confirmations: 1 (one per D-decision). Bundled-queue RE-CANARY 3 trigger: IMMEDIATELY on closure.

**Strict-mode discipline self-audit (operational test)**:
- ✓ Pre-mortem section exists (§6 — 11 failure modes)
- ✓ Multi-direction trace exists (§4 — all 4 axes named)
- ✓ Quality-gate checklist named (§7 — 9 ✓ / 1 N/A / 1 ⚠️)
- ✓ Cross-spec impact analysis exists (§3)
- ✓ Closure-audit step scheduled (§10.3)
- **Discipline status: APPLIED**. First artifact under the locked operating mode (2026-05-19).
