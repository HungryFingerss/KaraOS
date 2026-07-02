# P0.S7.5.1 — Plan v2 (architect's response to Plan v1 review)

**Date:** 2026-05-19
**Author:** architect
**Status:** Plan v2 — 2 auditor precision items addressed (one with honest clarification of a misread + adoption of the defense-in-depth spirit at the correct surface). Standing by for joint sign-off.

**Preceding documents:**
- `tests/p0_s7_5_1_audit.md` — Phase 0 audit (APPROVED 2026-05-19)
- `tests/p0_s7_5_1_plan_v1.md` — Plan v1 (APPROVED 2026-05-19 with 2 precision items)
- This document — Plan v2 (locks precision items + clarifications)

**Strict-industry-standard mode**: 2nd application (Plan v1 was the 1st). Discipline self-audit at §6.

---

## 1. Summary — auditor's 2 precision items + 1 architect clarification

| Item | Severity | Disposition |
|---|---|---|
| MEDIUM 1 — `re.escape(old_name)` defense-in-depth (as auditor framed it) | MEDIUM | **CLARIFIED + RE-FRAMED**: Plan v1's regex pattern does NOT use `old_name`; the real defense-in-depth concern is on the REPLACEMENT-STRING side (new_name special-char interpretation). LOCKED at lambda-replacement implementation. |
| LOW 1 — Explicit "Known Limitations" subsection in closure narrative | LOW | LOCKED — Phase 3 closure narrative MUST contain a dedicated "Known Limitations" subsection per §3 |

**Auditor declined 2 of architect's anticipated Plan v2 items** (Plan v1 §12):
- E2E fixture standardization: defer to developer at implementation
- `import re` grep annotation: §2 surface map already confirms; noise without contract change

Plan v1 §12 anticipated 3 items; auditor took 2 + 1 was already covered. Discipline-system in sync — architect's anticipation accuracy was reasonable.

---

## 2. MEDIUM 1 — Regex-replace defense-in-depth (clarified + re-framed)

### 2.1 Auditor's precision item as stated

> "§8.2 regex pattern formation — reference implementation must explicitly call `re.escape(old_name)` when building the pattern. `old_name = 'visitor'` is benign, but future callers could pass names with regex special chars (`.`, `[`, etc.). Defense-in-depth, prevents silent pattern-corruption regressions."

### 2.2 Honest clarification: Plan v1 §8.2 doesn't use `old_name` in the pattern

Plan v1's reference implementation at §8.2:

```python
new_content = re.sub(
    r"\[visitor_name:[^\]]+\]",   # FIXED pattern — no old_name interpolation
    f"[visitor_name:{new_name}]", # replacement uses new_name
    content,
)
```

The regex pattern `r"\[visitor_name:[^\]]+\]"` is **fixed** — a raw string literal with no `old_name` interpolation. `re.escape(old_name)` has no surface to apply.

This is the intentional shape of Option 2 (vs Option 1 which WOULD have used `old_name` in the pattern and required escaping):

**Option 1 (rejected at Phase 0)**:
```python
re.sub(rf"\[visitor_name:{re.escape(old_name)}\]", ...)
# Would need re.escape per auditor's framing; but also still vulnerable to
# the asymmetry bug (old_name='visitor' wouldn't match marker 'unknown').
```

**Option 2 (Plan v1 locked)**:
```python
re.sub(r"\[visitor_name:[^\]]+\]", ...)
# Fixed wildcard pattern; matches ANY current marker placeholder.
# No old_name interpolation hazard at all.
```

So the auditor's precision item as literally stated does NOT apply to Plan v1's pattern. **But the defense-in-depth spirit is real and applies to a different surface — the REPLACEMENT STRING.**

### 2.3 The real defense-in-depth concern: replacement-string special-char interpretation

`re.sub(pattern, replacement, string)` interprets the **replacement** argument as a template that supports:
- `\1`, `\2`, ... — numeric backreferences
- `\g<name>` — named backreferences
- `\\` — literal backslash

If `new_name` contains any of these patterns, the replacement gets MIS-INTERPRETED:

| `new_name` value | What `f"[visitor_name:{new_name}]"` becomes | What `re.sub` interprets |
|---|---|---|
| `"Lexi"` | `"[visitor_name:Lexi]"` | Correct — no special chars |
| `"Lex\1i"` (hypothetical Unicode-source attack or LLM glitch) | `"[visitor_name:Lex\1i]"` | `\1` interpreted as backref to capture group 1 — but pattern has no groups → raises `re.error` |
| `"Lex\\g<x>i"` | `"[visitor_name:Lex\g<x>i]"` | `\g<x>` interpreted as named backref — raises `re.error` (no such group) |
| `"\\new_value"` | `"[visitor_name:\new_value]"` | `\n` becomes literal newline; rest treated as backref attempt → unexpected output |

**Realistic risk assessment**: visitor names today come from STT transcription (`update_person_name` tool with `name` argument from LLM tool call) AND from enrollment. Neither path produces backslashes in practice. But under strict-industry-standard mode, defense-in-depth is mandatory — name-injection vectors could open if:
- Future enrollment accepts file-paths or pasted names
- An LLM hallucinates a name containing escape sequences
- A future locale/encoding change interprets non-ASCII as backslash

### 2.4 Plan v2 lock: use lambda-replacement to bypass `re.sub`'s replacement interpretation

The clean fix: pass a **callable** as the replacement argument. `re.sub` invokes the callable per match; the callable's return is used VERBATIM (no backreference interpretation).

**Locked reference implementation (Plan v2 §8.2 final, supersedes Plan v1)**:

```python
# P0.S7.5.1 D1 — regex-replace the [visitor_name:...] marker regardless
# of what placeholder is currently in content. The previous literal-
# substring check (Session 114 Part 5) only fired when the old_name
# from metadata matched the marker — but _run_visitor_alert writes
# ASYMMETRIC content (marker="[visitor_name:unknown]") and metadata
# (visitor_name="visitor") for stranger sessions, so the old check
# silently no-op'd on every stranger promotion. Regex-replace is
# robust to the asymmetry (and to any future placeholder drift).
#
# Plan v2 refinement: use a LAMBDA replacement (callable) so the
# replacement string is used verbatim — no interpretation of regex
# backreferences (\1, \g<name>, \\). Defense-in-depth against future
# visitor names containing regex special chars in replacement-string
# context (e.g., LLM-hallucinated names, future locale changes).
#
# Canary 2 evidence: 2026-05-19 terminal_output.md:857 + :1187.
new_content = content
if content:
    new_marker = f"[visitor_name:{new_name}]"
    new_content = re.sub(
        r"\[visitor_name:[^\]]+\]",
        lambda _m: new_marker,
        content,
    )
```

**What the lambda gives us**:
- Replacement string `new_marker` is computed ONCE (closure capture), used VERBATIM per match
- `re.sub` does NOT interpret backreferences in lambda return values
- Same byte-output as Plan v1's f-string-replacement for ASCII-only names (backward-compat)
- Robust to backslash + `\1` + `\g<name>` + any future replacement-string special chars

**Why not `re.escape(new_name)`**: `re.escape` is for escaping PATTERNS (it doubles special chars so they match literally in regex syntax). For replacement strings, the correct primitive is either a lambda (cleanest) or manual `.replace('\\', '\\\\')` (uglier). Lambda is idiomatic Python.

### 2.5 Test surface impact

New test required for the defense-in-depth invariant:

**Test 4b (NEW in Plan v2) — `test_regex_replacement_handles_backslash_in_new_name`** (Phase 1, unit):
- **Purpose**: Defense-in-depth — verify replacement-string special chars in `new_name` are handled verbatim, not interpreted.
- **Setup**: Same as Test 1 but use a `new_name` with a backslash: `new_name="Test\\name"`.
- **Action**: call `update_visitor_alert_for_promoted_person(person_id='p1', new_name='Test\\name')`.
- **Assert**: `nudges.content` contains literal `[visitor_name:Test\\name]` (backslash preserved as-is, not interpreted).

**Total tests: 5 → 6** (added test 4b). Auditor-Q5 5th instance updated: 5 → 6 (+1 from Plan v2 defense-in-depth addition).

### 2.6 Update to invariant contract (§5.2 of Plan v1)

Add to §5.2 New invariants:

- **Replacement-string-verbatim invariant**: after `update_visitor_alert_for_promoted_person` returns successfully, the `[visitor_name:X]` marker in `content` contains `X` verbatim — no regex backreference interpretation of `new_name`.

---

## 3. LOW 1 — Explicit "Known Limitations" subsection in closure narrative

### 3.1 Plan v1 §7 ⚠️ flagged backward-compat as documented limitation

Plan v1 §7 gate 10 (Backward compat) was marked ⚠️ with accepted-with-rationale: existing broken nudges in production (from canary 2 era) stay broken; only post-fix nudges benefit from regex swap. Auditor accepted but asked for more prominence in closure narrative.

### 3.2 Plan v2 locks (closure narrative MUST contain dedicated subsection)

At Phase 3 closure, the closure narrative MUST contain a subsection titled exactly:

```markdown
### Known Limitations (P0.S7.5.1)

**Canary-2-era broken nudges stay broken until natural expiry.** P0.S7.5.1 D1 fixes the marker-update path going forward; it does NOT migrate existing broken nudges in production databases. Specifically:

- Nudges queued BEFORE D1 deployment with `[visitor_name:unknown]` content where the visitor was later promoted to a real name (Lexi etc.) will retain the broken `[visitor_name:unknown]` marker until their natural `expires_at` (24h after queue) OR manual dismissal.
- Brain will continue surfacing the unknown-branch VISITOR CONTEXT template ("Someone stopped by but didn't tell me their name...") for these specific nudges.
- New nudges queued AFTER D1 deployment work correctly: regex swap fires at promotion time, marker reconciles with metadata, brain surfaces the visitor by name.

**Rationale for no migration**: factory-reset between canaries is the project's canary discipline; canary 3 starts with clean state. In production, broken nudges expire naturally within 24h. Migration script would add complexity for a transient liability with a known TTL.

**When to revisit**: if production runs without factory-reset between canaries become normal practice, OR if the 24h expiry proves too long for stale-nudge user experience, file a follow-up spec to add a one-shot migration. Until then, accepted-with-rationale.
```

### 3.3 Where the subsection lives

In `CLAUDE.md` header narrative section for P0.S7.5.1 entry (alongside other closure-banked items). Also referenced from `complete-plan.md` P0.S7.5.1 entry.

---

## 4. Updated D1 implementation contract (Plan v2 final, supersedes Plan v1 §8)

| Element | Plan v1 | Plan v2 |
|---|---|---|
| Regex pattern | `r"\[visitor_name:[^\]]+\]"` | UNCHANGED |
| Replacement | f-string: `f"[visitor_name:{new_name}]"` | **UPDATED — lambda: `lambda _m: new_marker` where `new_marker = f"[visitor_name:{new_name}]"`** |
| Defense-in-depth | Implicit (no special chars in current names) | **Explicit — replacement-string special chars handled verbatim via lambda** |
| Test surface | 5 tests (3 unit + 1 AST + 1 E2E) | **6 tests (4 unit + 1 AST + 1 E2E)** |

---

## 5. Updated phase decomposition + test surface forecast

### 5.1 Phase decomposition (Plan v2 final)

**Phase 1 (~2 hours)** — D1 implementation + 5 tests (was 4):
- Edit `update_visitor_alert_for_promoted_person` at `core/brain_agent.py:3043-3047`: replace literal-substring with lambda-replacement `re.sub` per Plan v2 §2.4 template
- New test file `tests/test_p0_s7_5_1.py` with:
  - Test 1: `test_regex_swaps_existing_marker` (unit)
  - Test 2: `test_regex_noop_when_marker_absent` (unit)
  - Test 3: `test_regex_idempotent_when_already_renamed` (unit)
  - Test 4: `test_update_alert_uses_regex_not_literal_substring` (AST forward-property)
  - **Test 4b (NEW)**: `test_regex_replacement_handles_backslash_in_new_name` (unit; Plan v2 §2.5)

**Phase 2 (~0.5-1 hour)** — Behavioral E2E + closure narrative:
- Test 5: `test_visitor_alert_marker_swap_e2e` (E2E)
- Closure narrative MUST contain the "Known Limitations" subsection per Plan v2 §3.2 verbatim
- Memory file updates queued: `feedback_auditor_q5_estimates_trail_grep.md` 5th instance with Phase 0 granularity confirmation (forecast 4-5; Plan v2 actual 6 — slight high-by-20%, still mid-range; sub-observation continues to hold)

**Phase 3 (~0.25 hours)** — Deliberate-regression + memory finalization:
- Confirmation (a): revert lambda → f-string replacement; verify test 4b fails (backslash interpreted as escape sequence); revert; all green
- Production-canary diff tracking step per Plan v1 §10.3

### 5.2 Test surface forecast (Plan v2 final)

| Phase | Tests |
|---|---|
| Phase 1 | 5 (3 unit + 1 AST + 1 defense-in-depth unit) |
| Phase 2 | 1 (E2E) |
| Phase 3 | 0 (1 deliberate-regression confirmation) |
| **Total** | **6 tests** |

**Plan v2 forecast: +6 tests (2421 → 2427).** Plan v1 was +5; Plan v2 adds 1 for defense-in-depth coverage.

### 5.3 Auditor-Q5 5th instance update

- Original auditor estimate: 4-5
- Plan v1 lock: 5 (ON-TARGET — mid-range)
- Plan v2 lock: 6 (slight HIGH-BY-20% from upper bound of estimate)

**Phase 0 granularity sub-observation status**: still CONFIRMED. Mini-spec with 1 D-decision + 1 named edit site forecast landed within 20% of mid-range estimate even after Plan v2 precision addition. Sub-observation has predictive power. The +1 test from Plan v2's defense-in-depth refinement is a small auditor-driven addition, not a structural under-estimate. Bank as: "Plan v1 ON-TARGET; Plan v2 +1 from defense-in-depth refinement — sub-observation holds."

---

## 6. Updated 11-gate quality checklist (Plan v2 deltas from Plan v1)

| # | Gate | Plan v1 | Plan v2 |
|---|---|---|---|
| 1 | Correctness | ✓ | ✓ (4-axis trace unchanged; lambda implementation more robust) |
| 2 | Security | N/A | **✓ (UPGRADED from N/A)** — lambda-replacement removes the regex-backreference-injection-via-name vector; explicit defense-in-depth |
| 3 | Privacy | ✓ | ✓ (unchanged) |
| 4 | Performance | ✓ | ✓ (lambda call per match adds <1μs; negligible) |
| 5 | Observability | ✓ | ✓ (unchanged) |
| 6 | Test pyramid | ✓ | ✓ (4 unit + 1 AST + 1 E2E = 6 total; pyramid shape preserved) |
| 7 | Regression guards | ✓ | ✓ (test 4b adds defense-in-depth regression guard) |
| 8 | Pre-mortem | ✓ | ✓ (failure mode #2 from Plan v1 §6 "multi-marker content" already covered backslash case implicitly via "no backreference interpretation"; explicit test 4b operationalizes this) |
| 9 | Multi-direction trace | ✓ | ✓ (unchanged) |
| 10 | Backward compat | ⚠️ | ⚠️ (UNCHANGED — same accepted limitation; Plan v2 §3 adds dedicated closure-narrative subsection per LOW 1) |
| 11 | Doc updates | ✓ | ✓ (UPDATED — "Known Limitations" subsection added to closure narrative template) |

**Gate 2 upgrade**: defense-in-depth against replacement-string special-char interpretation moves Gate 2 from N/A to ✓. This is the substantive correctness benefit of MEDIUM 1's clarification + lambda implementation. The risk surface was real (just on a different axis than the auditor framed); Plan v2 closes it cleanly.

---

## 7. Strict-industry-standard mode discipline self-audit (operational test)

Per `feedback_strict_industry_standard_mode.md` operational test — am I applying the rule?

| Check | Plan v2 status |
|---|---|
| Pre-mortem section exists | ✓ (Plan v1 §6 stands; Plan v2 §2.3 expands one failure mode with explicit handling) |
| Multi-direction invariant trace exists | ✓ (Plan v1 §4 stands; Plan v2 unchanged) |
| Quality-gate checklist named | ✓ (Plan v2 §6 — Gate 2 upgraded N/A → ✓) |
| Cross-spec impact analysis exists | ✓ (Plan v1 §3 stands; no new cross-spec impact from Plan v2 changes) |
| Closure-audit step scheduled | ✓ (Plan v2 §3 adds explicit "Known Limitations" subsection requirement) |
| **Honest engineering on auditor framing** | ✓ (Plan v2 §2.2 honestly clarifies that auditor's literal framing didn't apply to Plan v1 §8.2 — but adopted the defense-in-depth spirit at the correct surface. Did NOT silently fold to Option 1.) |

**Discipline status: APPLIED**. 2nd consecutive Plan under strict mode. Plan v2 specifically demonstrates the discipline by HONESTLY clarifying the auditor's precision item rather than silently misinterpreting it — strict mode rejects "fix what auditor said even if their framing doesn't fit" in favor of "name the misalignment + fix the real risk."

---

## 8. Discipline-count predictions (Plan v2 final)

Unchanged from Plan v1 §11 except for the auditor-Q5 5th instance note:

| Discipline | Pre-P0.S7.5.1 | Post-closure |
|---|---|---|
| Spec-first review cycle | 15-for-15 | **16-for-16** ✓ |
| Sub-pattern A | 5 instances | stays at **5** ✓ |
| Tripwires-must-match-deferral-surface | 4-for-4 | stays **4-for-4** ✓ |
| Developer-improves-on-spec | 6-for-6 | stays **6-for-6** |
| Induction-surfaces-invariant-gaps | 7-for-7 | stays **7-for-7** |
| Canary-finding tracker | 3 instances | **4th instance** |
| Canary-gate override (informal) | 1 instance | stays at **1** |
| Scope-expansion-via-Phase-0 (informal) | 1 instance | stays at **1** |
| Deferral-rationale-expires-when-downstream-ships (informal) | 1 instance | stays at **1** |
| Two-stage-canary-gated-cleanup (informal) | 2 instances | stays at **2** |
| Auditor-Q5-estimates-trail-grep (architect-memory) | 4 instances (1 ON-TARGET) | **5th instance** — Plan v1 ON-TARGET; Plan v2 +1 defense-in-depth → mid-range estimate held (20% from upper bound) — sub-observation CONFIRMED |
| Partial-falsification-tentative (architect-memory only) | 2 instances | stays at **2** |
| Spec-time grep-verification (architect-memory) | 5 instances + class-containment sub-observation | stays at **5** |
| **Strict-industry-standard mode (auto-memory)** | 0 instances pre-locked | **2nd application** at Plan v2 — discipline holds across consecutive Plans |

---

## 9. Plan v2 deltas from Plan v1 — summary

| Section | Plan v1 | Plan v2 |
|---|---|---|
| §8.2 reference implementation | f-string replacement | **Lambda replacement** (defense-in-depth against regex special chars in `new_name`) |
| §5.2 invariants | 3 new invariants | **4 new invariants** (+ replacement-string-verbatim invariant) |
| Test surface | 5 tests | **6 tests** (+1 defense-in-depth unit test 4b) |
| §7 Gate 2 (Security) | N/A | **✓ (upgraded)** — lambda removes backref-injection vector |
| Closure narrative | No "Known Limitations" subsection | **Dedicated "Known Limitations" subsection** required per Plan v2 §3.2 verbatim |
| Suite delta forecast | 2421 → 2426 (+5) | 2421 → 2427 (+6) |
| Phase 1 time | ~2h | ~2h (1 extra unit test = ~10 min add) |
| Phase 4 confirmations | 1 | 1 (unchanged) |
| Auditor-Q5 alignment | ON-TARGET (5 vs 4-5) | Slight high (6 vs 4-5 upper bound) — defense-in-depth-driven addition |

All deltas are tightenings, additions, or documentation. Nothing reversed.

---

## 10. Next steps

1. **Auditor reviews Plan v2.** If approved → joint sign-off cleared.
2. **No Plan v3 anticipated.** Both precision items locked.
3. **Developer handoff** with:
   - `tests/p0_s7_5_1_audit.md` (Phase 0 — APPROVED)
   - `tests/p0_s7_5_1_plan_v1.md` (Plan v1 — APPROVED with 2 precision items)
   - This document → `tests/p0_s7_5_1_plan_v2.md` (Plan v2 final)
   - `CLAUDE.md` + `complete-plan.md`
4. **Phase 1 ships** (~2h): lambda replacement + 5 tests (3 unit + 1 AST + 1 defense-in-depth unit).
5. **Phase 2 ships** (~0.5-1h): E2E test + closure narrative with mandatory "Known Limitations" subsection.
6. **Phase 3 ships** (~0.25h): 1 deliberate-regression confirmation + memory file updates.
7. **RE-CANARY 3 IMMEDIATELY** on closure. Same scenario as canary 2. Expected: brain says "I was talking to Lexi about..." with explicit name + search_memory queries entity='Lexi'.
8. **On PASS**: combined Stage 2 PR fires (D-C Stage 2 + D-D Stage 2 hard-deletes + 130 test-site migrations). P0.S7 family arc closes definitively.
9. **On FAIL**: diagnose new root cause; another follow-up spec.

---

## 11. Reference documents

- `tests/p0_s7_5_1_audit.md` — Phase 0 (APPROVED)
- `tests/p0_s7_5_1_plan_v1.md` — Plan v1 (APPROVED with 2 precision items)
- `CLAUDE.md` `### Phase-0-catches-wrong-premise` doctrine
- **Canary 2 evidence**: terminal_output.md:790, 857, 1170, 1179, 1187, 1242
- `core/brain_agent.py:3043-3047` — D1 PRIMARY EDIT SITE
- Memory: `feedback_strict_industry_standard_mode.md` — locked 2026-05-19; **2nd application** at this Plan v2
- Memory: `feedback_auditor_q5_estimates_trail_grep.md` (4 → 5 instances at closure; Plan v1 ON-TARGET; Plan v2 +1 defense-in-depth held within mid-range)
- Memory: `feedback_spec_time_grep_verification.md` (5 instances + class-containment sub-observation)

---

**Standing by for auditor sign-off on Plan v2 → developer handoff → RE-CANARY 3 IMMEDIATELY on closure.**

Plan v2 strictly tightens Plan v1 + honestly clarifies the auditor's precision item misalignment (§2.2) + adopts defense-in-depth spirit at the correct surface (replacement-string special chars via lambda). Suite delta: **2421 → 2427 (+6)**. Total effort: ~3 hours. **Strict-mode discipline self-audit: APPLIED (2nd consecutive Plan).**
