# P0.S7.5.1 — Visitor alert marker/metadata asymmetry fix — Phase 0 Audit

**Date:** 2026-05-19
**Author:** architect
**Status:** Phase 0 — grep-verified findings, zero production-code changes. **Bundled-queue RE-CANARY 2026-05-19 (canary 2) revealed a single subtle bug downstream of P0.S7.5's wins. Mini follow-up spec — single D-decision, ~half-day.** Standing by for auditor review.

**Companion documents (forthcoming):**
- `tests/p0_s7_5_1_plan_v1.md` — after Phase 0 sign-off
- `tests/p0_s7_5_1_plan_v2.md` — if precision items surface

**Disciplines applied at audit drafting:**
- **Two-pass grep-verification (Pass 1)**: all function/line/symbol references grep-verified 2026-05-19 against current production code. Class containment + line range BOTH verified (sub-observation from `feedback_spec_time_grep_verification.md` instance 5).
- **`### Phase-0-catches-wrong-premise` doctrine** (CLAUDE.md): hypothesis-testing framing applied at §1.
- **Canary-finding tracker** (informal observation, 3 → 4 instances): P0.S7.2, P0.S7.3, P0.S7.5, **P0.S7.5.1**. Approaching 5+ doctrine elevation threshold.

---

## 1. Canary 2 result + root-cause decomposition

### 1.1 Bundled-queue RE-CANARY 2026-05-19 (canary 2) — partial pass

Per the closure-cleared scenario: factory reset → Jagan enrolled → ElevenLabs Lexi visitor session → Jagan returns → "who were you talking to when I was away?"

**5 of 6 P0.S7.5 surfaces validated successfully:**

| # | Surface | Canary 2 result |
|---|---|---|
| 1 | Visitor alert persistence (D1) | ✓ `[PromptPrefAgent] persistent nudge re-injected (type=VISITOR_ALERT, id=1)` fires every Jagan turn |
| 2 | VISITOR CONTEXT block render | ✓ Block renders; marker IS in prompt_addendum (`nudge=yes` at lines 1120, 1171, 1235, 1286) |
| 3 | SHARED CONTEXT widening (D2) | ✓ `[SharedContext] gate=recent_audience (rooms=2, rows=10) → rendered (D2 widening)` |
| 4 | Canonical ack on rename (D3) | ✓ `[Audio] TTS 23:02:56.305: 'Got it, Lexi.'` |
| 5 | LOW 2 re-injection log | ✓ log line fires per turn as designed |

**1 surface FAILED with a new, subtle root cause:**

Turn 39 (terminal_output.md:1159): Jagan asks **"Yeah, and who were you talking to when I was away?"**
- Line 1179: `[Brain] Tool: search_memory('Jagan', 'visitor')` — **STILL queries entity='Jagan' (asker)**
- Line 1187: `[Audio] TTS stream 23:06:48.732: 'Someone stopped by but didn't tell me their name, do you know who it might have been?'` — **Brain doesn't name Lexi**

**Strict improvement vs canary 1**: brain no longer confabulates "No one was here" denial. Now uses an HONEST hedge from the VISITOR CONTEXT block's unknown-branch template. But still fails to surface Lexi by name.

### 1.2 Pre-audit hypothesis test (Phase-0-catches-wrong-premise applied)

Per the elevated `### Phase-0-catches-wrong-premise` doctrine: *"treat the pre-audit mental model as a hypothesis the audit will test."*

**Pre-audit mental model**: "VISITOR CONTEXT block is firing in the WRONG branch — `_visitor_name = 'unknown'` instead of `'Lexi'`. Either marker isn't being updated on promotion, or block reader has a bug."

**Phase 0 grep-verified state**: the bug IS in `update_visitor_alert_for_promoted_person` — confirmed via code read at `core/brain_agent.py:3035-3047`. Pre-audit hypothesis matches grep evidence. **NOT a wrong-premise instance.** Sub-pattern A stays at 5; this spec is canary-finding-tracker territory.

### 1.3 Root-cause tree (full chain)

```
Primary failure: Jagan asks "who were you talking to when I was away?"
  ↓ Brain says: "Someone stopped by but didn't tell me their name"
  ↓ VISITOR CONTEXT block fires unknown-name branch at core/brain.py:2611-2618
  ↓ Block reader at core/brain.py:2569-2570 extracts: _visitor_name = "unknown"
  ↓ prompt_addendum content contains: [visitor_name:unknown] [visitor_id:stranger_visitor_511257]
  ↓
  ↓ ROOT CAUSE: marker/metadata asymmetry in _run_visitor_alert + update_visitor_alert_for_promoted_person
  │
  ├── _run_visitor_alert (core/brain_agent.py:7139-7179) writes ASYMMETRIC marker vs metadata
  │   when person is stranger named "visitor":
  │     Line 7141: name_marker = "[visitor_name:unknown]"  ← placeholder in content
  │     Line 7179: meta["visitor_name"] = person_name = "visitor"  ← different placeholder
  │
  └── update_visitor_alert_for_promoted_person (core/brain_agent.py:3035-3047)
      reads old_name FROM METADATA (= "visitor"), tries to replace in CONTENT:
        Line 3043: if old_name and f"[visitor_name:{old_name}]" in (content or ""):
                   #            literal "[visitor_name:visitor]" — NOT found in content
        Line 3044-3047: content.replace(...)  ← never fires
      Result:
        - metadata: visitor_name="Lexi" ✓ (updated)
        - content: [visitor_name:unknown] ← STAYS BROKEN (replace silently no-op'd)
```

**Canary log evidence**:
- Line 790: `[Brain] Visitor alert queued for Jagan — an unidentified visitor stopped by (1 turns, type=stranger)` — initial queue, person_name="visitor"
- Line 857: `[BrainDB] update_visitor_alert_for_promoted_person: updated 1 alert(s) for stranger_visitor_511257 → 'Lexi'` — metadata updated, BUT content marker did NOT swap (silent no-op due to literal-substring mismatch)
- Line 1170: `[PromptPrefAgent] persistent nudge re-injected (type=VISITOR_ALERT, id=1)` — broken content gets re-injected every turn
- Line 1187: brain dutifully follows the unknown-branch template

### 1.4 Downstream observed effect: brain queries literal "unknown"

Line 1242 of canary 2: `[Brain] Tool: search_memory('unknown', 'conversation')` — the SECOND turn of Jagan asking, brain literally calls `search_memory(person_name='unknown', ...)`.

This is the unknown-branch directive ("You cannot retrieve their specific facts via search_memory") being misread by the LLM. The block told the brain NOT to search; brain interpreted "use 'unknown' as the placeholder entity" instead. **Symptom of the upstream bug; resolves automatically when D1 fixes the marker.**

---

## 2. Grep-verified surface map (Pass 1, 2026-05-19)

### 2.1 The bug site (D1 EDIT SITE)

| File | Line | Surface |
|---|---|---|
| `core/brain_agent.py` | 3003 | `def update_visitor_alert_for_promoted_person(self, person_id, new_name) -> int:` — method on `BrainDB` class |
| `core/brain_agent.py` | 3035 | `old_name = meta.get("visitor_name") or ""` — reads from metadata |
| `core/brain_agent.py` | 3043 | `if old_name and f"[visitor_name:{old_name}]" in (content or ""):` — **THE BUG: literal-substring check** |
| `core/brain_agent.py` | 3044-3047 | `content.replace(f"[visitor_name:{old_name}]", f"[visitor_name:{new_name}]")` — silent no-op when old_name doesn't match marker |

### 2.2 Upstream — where the asymmetry originates

| File | Line | Surface |
|---|---|---|
| `core/brain_agent.py` | 7139-7144 | `_run_visitor_alert` stranger branch: `name_marker = "[visitor_name:unknown]"` + `meta["visitor_name"] = person_name = "visitor"` (line 7179) |

Pre-audit consideration: should we fix `_run_visitor_alert` to set `meta["visitor_name"] = "unknown"` (matching the marker)? That's "Option 1" from the canary handoff. **Architect's lean is Option 2 (regex replace) per Jagan's verdict 2026-05-19.** Option 2 is downstream-fix-only; doesn't touch the upstream asymmetry. Option 2 is robust to future drift (e.g., if marker placeholder changes again) where Option 1 introduces a brittle precondition.

### 2.3 Downstream consumer (no change needed)

| File | Line | Surface |
|---|---|---|
| `core/brain.py` | 2569-2570 | `_re_vc.search(r"\[visitor_name:([^\]]+)\]", prompt_addendum)` — reads marker from content |
| `core/brain.py` | 2583 | `if _visitor_name and _visitor_name.lower() not in ("unknown", ""):` — gate for name-known branch |
| `core/brain.py` | 2593-2610 | name-known branch (hardened entity-binding language) |
| `core/brain.py` | 2611-2618 | unknown-branch (fires today; will NOT fire after D1 fix) |

Block reader logic is correct. The bug is upstream — content marker isn't being updated. Block correctly fires unknown-branch given `[visitor_name:unknown]` in content.

### 2.4 Test surface estimate (auditor-Q5 pre-emptive)

Per `feedback_auditor_q5_estimates_trail_grep.md` (4 instances; 4th was ON-TARGET when Phase 0 was decomposed into concrete D-decisions with edit sites). P0.S7.5.1 has 1 D-decision + 1 concrete edit site:

- **D1 unit tests**: regex replaces existing marker (happy path); regex handles missing marker (no-op); regex handles already-renamed marker (idempotent)
- **D1 AST forward-property**: `update_visitor_alert_for_promoted_person` uses `re.sub` not `str.replace` for the marker swap
- **Behavioral integration**: full round-trip — `_run_visitor_alert` queues with `[visitor_name:unknown]` marker → `update_visitor_alert_for_promoted_person` swaps to `[visitor_name:Lexi]` → VISITOR CONTEXT block extracts `_visitor_name = "Lexi"` → name-known branch fires (regression guard against canary 2 failure mode)

**Pre-emptive estimate: 4-5 tests.** Phase 0 granularity is high (single edit site, named line range, named bug), so per the Phase 0 granularity sub-observation, this estimate should land on-target at Plan v1.

---

## 3. D-decision surfaced (single)

### D1 — Replace literal-substring check with regex replace in `update_visitor_alert_for_promoted_person`

**Contract**: `update_visitor_alert_for_promoted_person` MUST swap WHATEVER `[visitor_name:X]` marker exists in the nudge content (regardless of what X is), replacing it with `[visitor_name:{new_name}]`. The marker is the source of truth for the downstream VISITOR CONTEXT block reader; the metadata `visitor_name` field is canonical for queries.

**Implementation contract** (developer chooses exact code shape within these constraints):

Replace lines 3043-3047 with regex-based swap:

```python
# P0.S7.5.1 D1 — regex-replace the [visitor_name:...] marker regardless
# of what placeholder is currently in content. The previous literal-
# substring check (Plan v2 Session 114 Part 5) only fired when the
# old_name from metadata matched the marker — but _run_visitor_alert
# writes ASYMMETRIC content (marker="[visitor_name:unknown]") and
# metadata (visitor_name="visitor") for stranger sessions, so the
# old literal-substring check silently no-op'd on every stranger
# promotion. Regex-replace is robust to the asymmetry (and to any
# future placeholder drift).
new_content = content
if content:
    new_content = re.sub(
        r"\[visitor_name:[^\]]+\]",
        f"[visitor_name:{new_name}]",
        content,
    )
```

Plus `import re` at top of file if not already imported (grep-verify at Plan v1).

**Invariants the contract enforces**:
- Robust to ANY existing marker value: `[visitor_name:visitor]`, `[visitor_name:unknown]`, `[visitor_name:Lexi]`, etc. — all swap correctly
- Idempotent: re-running with the same `new_name` is a no-op (regex matches but result is byte-identical)
- Defensive: `if content:` guard preserves the original None-check at line 3043
- No new metadata write needed: metadata's `visitor_name` field is already updated unconditionally at line 3036 (`meta["visitor_name"] = new_name`)

**What the contract does NOT do**:
- Does not fix the upstream `_run_visitor_alert` asymmetry. Marker/metadata can stay asymmetric at queue time; D1 handles the symmetry restoration at promotion time.
- Does not touch the VISITOR CONTEXT block reader. Block reader stays as-is.
- Does not address OBS C (multi-pid visitor split — out of scope; pre-existing bug).
- Does not address OBS D (brain queries literal "unknown" — auto-resolves once marker is correct).

---

## 4. Auditor adjudications requested

### Q1 — Option 2 vs Option 1 vs Option 3

Jagan approved Option 2 at canary 2 handoff. Architect locked Option 2. Auditor: confirm or push back?

**Option comparison reminder:**
- **Option 1** (upstream fix): change `_run_visitor_alert` to set `meta["visitor_name"] = "unknown"` when marker is `[visitor_name:unknown]`. Smallest change; restores symmetry at source.
- **Option 2** (downstream fix, architect's lean): regex-replace in `update_visitor_alert_for_promoted_person`. Robust to any current/future marker placeholder drift.
- **Option 3** (block reader fix): make VISITOR CONTEXT block reader prefer metadata-encoded visitor_name over content marker. Dual-source-of-truth complexity.

Auditor's call.

### Q2 — Should we ALSO fix the upstream asymmetry (defense in depth)?

Architect's read: NO. Option 2 is robust enough; fixing upstream too is belt-and-braces but adds churn for no marginal correctness gain. If the upstream asymmetry recurs in a future code path (e.g., a new caller writes `meta.visitor_name = "X"` but content has `[visitor_name:Y]`), Option 2 still handles it correctly.

But auditor may want both fixes for safety. Adjudicate.

### Q3 — Sub-pattern A — does P0.S7.5.1 bump?

Architect's lean: **stays at 5**. Pre-audit hypothesis (marker/metadata asymmetry) matched grep evidence. Not a wrong-premise instance. **Canary-finding tracker bumps to 4th instance** (P0.S7.2 + P0.S7.3 + P0.S7.5 + P0.S7.5.1).

### Q4 — `feedback_partial_falsification_tentative.md` — does P0.S7.5.1 bump?

Architect's lean: **stays at 2 instances**. P0.S7.5.1 is NOT a partial-falsification cycle — the pre-audit framing landed on the right surface (the metadata/marker asymmetry IS the load-bearing fix). Doesn't add a 3rd instance for the framing re-evaluation trigger. Re-evaluation pending at the NEXT partial-falsification instance.

### Q5 — Pre-emptive test count estimate (architect's Phase 0 granularity test)

Architect estimates 4-5 tests for D1. This is a self-test of the Phase 0 granularity sub-observation: with 1 D-decision + 1 edit site, did the architect land on-target at Plan v1 grep?

### Q6 — OBS C (multi-pid visitor split) — separate spec or banked observation?

Architect's lean: bank as observation; not P0.S7.5.1 scope. Pre-existing bug (line 824-828: `stranger_visitor_5a1594` opened alongside `stranger_visitor_511257` for what was likely the same physical person). Doesn't block re-canary. If multi-pid recurs in future sessions, file a separate `P0.S8.X` spec.

---

## 5. Phase decomposition forecast

### 5.1 Single D-decision, single edit site → minimal phases

**Phase 1** — D1 implementation + 4-5 tests. ~2 hours.
- Edit `update_visitor_alert_for_promoted_person` at `core/brain_agent.py:3043-3047`: replace literal-substring with `re.sub`
- 4-5 tests (per §2.4 estimate)

**Phase 2** — Behavioral integration + closure narrative. ~0.5-1 hour.
- End-to-end test: queue with `[visitor_name:unknown]` marker → promote to Lexi → assert marker becomes `[visitor_name:Lexi]` → assert brain reader extracts `_visitor_name = "Lexi"` → assert name-known branch fires
- Closure narrative + memory file updates

**Phase 3** — Deliberate-regression confirmation. ~0.25 hours.
- 1 confirmation: revert regex → literal-substring (Plan v1 §3 contract violation) → behavioral integration test fails (regression guard against future revert)

**Total: ~3 hours = ~half-day.** Matches "mini follow-up spec" framing from canary 2 handoff.

### 5.2 Phase 4 deliberate-regression confirmation (single)

(a) Replace `re.sub(...)` back to `content.replace(f"[visitor_name:{old_name}]", ...)` → behavioral integration test fails (marker stays at `[visitor_name:unknown]`).

Single D-decision → single confirmation. Maintains the discipline pattern (one confirmation per D-decision) at appropriate scale.

---

## 6. Test surface forecast

| Phase | Tests | Cumulative |
|---|---|---|
| Phase 1 unit | 3 (regex swaps existing marker / regex no-op when marker absent / regex idempotent) | 3 |
| Phase 1 AST | 1 (forward-property: `update_visitor_alert_for_promoted_person` body contains `re.sub` not literal `.replace`) | 4 |
| Phase 2 behavioral | 1 (E2E round-trip: queue → promote → block reader sees correct name) | 5 |
| **Total** | | **5 tests** |

Suite delta forecast: **2421 → 2426 (+5)**.

Banking for auditor-Q5 5th instance: architect estimate 4-5; locked at 5.

---

## 7. Risk + mitigation

### 7.1 Risk — regex pattern matches more than expected

The pattern `r"\[visitor_name:[^\]]+\]"` matches `[visitor_name:X]` where X is any non-`]` characters. What if a visitor's name contains `]` (e.g., `[visitor_name:Lexi (test)]`)? The regex would match incorrectly.

**Mitigation**: visitor names are constrained to alphanumeric + common name characters (no brackets). The `[^\]]+` character class is greedy but bounded by the closing `]` — same shape as the existing reader regex at `core/brain.py:2570`. The bug being fixed is exactly the same regex-shape mismatch in the OPPOSITE direction (literal-substring instead of regex). Symmetric handling: both writer and reader use the same pattern.

If a visitor name ever DOES contain `]`, fix in a follow-up; not a P0.S7.5.1 blocker.

### 7.2 Risk — multiple `[visitor_name:X]` markers in content

If content contains TWO markers (legacy artifact, or future format change), `re.sub` replaces ALL of them by default. The reader at `core/brain.py:2570` uses `re.search` which returns the FIRST match — so reader sees the first replacement, others are redundant.

**Mitigation**: not a realistic scenario today. `_run_visitor_alert` writes exactly one marker per nudge. If future code paths write multi-marker content, the regex's "replace all" behavior is the SAFE outcome (no orphan markers). No mitigation needed.

### 7.3 Risk — `import re` already present

`core/brain_agent.py` is likely to already have `import re` (it's a 8000+ line file). Plan v1 grep-verifies. If absent, add at top. If present, no change. Trivial.

### 7.4 Risk — running tests during canary 2 nudge state

The canary 2 ran with an in-database broken nudge (`[visitor_name:unknown]` content despite Lexi promotion). If the developer's local dev DB has that state when running tests, tests should still pass (tests use isolated tmp DBs via fixtures). But the broken nudge in the live DB persists until canary 3 wipes via factory reset.

**Mitigation**: re-canary 3 starts with factory reset → broken nudge state is wiped. Production code fix prevents new broken nudges. Tests use tmp_path DBs (standard pattern). No interaction.

---

## 8. Discipline-count predictions on P0.S7.5.1 closure

| Discipline | Pre-P0.S7.5.1 | Post-closure |
|---|---|---|
| Spec-first review cycle | 15-for-15 | **16-for-16** ✓ |
| Sub-pattern A (`### Phase-0-catches-wrong-premise`) | 5 instances | **stays at 5** (pre-audit hypothesis matched grep — not wrong-premise) |
| Tripwires-must-match-deferral-surface | 4-for-4 | stays **4-for-4** |
| Developer-improves-on-spec | 6-for-6 | stays **6-for-6** unless code phase surfaces a mechanism improvement |
| Induction-surfaces-invariant-gaps | 7-for-7 | stays **7-for-7** unless Phase 3 surfaces real gap |
| Canary-finding tracker | 3 instances | **4th instance** (toward 5+ doctrine elevation) |
| Canary-gate override (informal) | 1 instance | stays at **1** |
| Scope-expansion-via-Phase-0 (informal) | 1 instance | stays at **1** |
| Deferral-rationale-expires-when-downstream-ships (informal) | 1 instance | stays at **1** |
| Two-stage-canary-gated-cleanup (informal) | 2 instances | stays at **2** (P0.S7.5.1 single-stage) |
| Auditor-Q5-estimates-trail-grep (architect-memory) | 4 instances (1 ON-TARGET) | **5th instance** — self-test of Phase 0 granularity sub-observation |
| Partial-falsification-tentative (architect-memory only) | 2 instances | **stays at 2** (P0.S7.5.1 is single-D-decision; pre-audit hypothesis correct) |
| Spec-time grep-verification | 5 instances | stays at **5** unless Plan v1/closure surfaces drift (Pass 1 + Pass 2 both applied here) |
| Spec edit-site count under-estimation (architect-memory tentative) | 1 instance | stays at **1** (P0.S7.5.1 has 1 D-decision, 1 edit site — no count to under-estimate) |

---

## 9. Closure narrative banking targets (Phase 2 final step)

1. **1 deliberate-regression confirmation** (revert regex → literal-substring) — expected passing
2. **Sub-pattern A stays at 5** (not a wrong-premise instance)
3. **Canary-finding tracker bumps to 4th instance** in CLAUDE.md informal observations section — track toward potential 5+ doctrine elevation as `### Canary-surfaces-real-gaps`
4. **`feedback_auditor_q5_estimates_trail_grep.md` 5th instance** — self-test of Phase 0 granularity sub-observation (architect estimated 4-5 tests; Plan v1 locked at 5 — ON-TARGET would CONFIRM the sub-observation; OFF-TARGET would reveal limits)
5. **CLAUDE.md "Pending Work" updates**: re-canary 3 trigger AFTER P0.S7.5.1 closure → on PASS fire combined Stage 2 PR (D-C Stage 2 + D-D Stage 2)
6. **Memory file notes** — no new memory files created at P0.S7.5.1 closure (single D-decision; no new tentative observations expected)

---

## 10. Reference documents

- `tests/p0_s7_5_audit.md` + closure — P0.S7.5 reference (D1+D2+D3+D4+D5 + canary 2 partial-pass result)
- `tests/p0_s7_5_plan_v1.md` + `p0_s7_5_plan_v2.md` — P0.S7.5 plan reference (architect's lean = Option 2 confirmed by Jagan)
- `CLAUDE.md` `### Phase-0-catches-wrong-premise` doctrine — applied at §1.2
- **Canary 2 evidence (terminal_output.md, 2026-05-19)**:
  - Line 790: initial visitor_alert queued with stranger person_name="visitor"
  - Line 857: `update_visitor_alert_for_promoted_person: updated 1 alert(s)` — metadata updated, content marker stayed `[visitor_name:unknown]`
  - Line 1170: persistent nudge re-injected (P0.S7.5 D1 working)
  - Line 1179: `Tool: search_memory('Jagan', 'visitor')` — entity defaulted to asker
  - Line 1187: `TTS: 'Someone stopped by but didn't tell me their name...'` — unknown-branch template
- `core/brain_agent.py:3003-3061` — `update_visitor_alert_for_promoted_person` (D1 PRIMARY EDIT SITE)
- `core/brain_agent.py:3035` — `old_name` metadata read (D1 retains, but result no longer used in literal-substring check)
- `core/brain_agent.py:3043-3047` — literal-substring check + replace (D1 REPLACE with regex)
- `core/brain_agent.py:7139-7144` — `_run_visitor_alert` stranger marker `[visitor_name:unknown]` (upstream of asymmetry; unchanged)
- `core/brain_agent.py:7179` — `meta["visitor_name"] = person_name` (upstream of asymmetry; unchanged)
- `core/brain.py:2569-2570` — VISITOR CONTEXT block regex reader (downstream consumer; unchanged)
- `core/brain.py:2611-2618` — unknown-branch template (will NOT fire after D1 fix; preserved for genuinely-unknown cases)
- Memory: `feedback_spec_time_grep_verification.md` (5 instances + class-containment sub-observation) — Pass 1 applied at §2; Pass 2 at closure
- Memory: `feedback_auditor_q5_estimates_trail_grep.md` (4 instances + Phase 0 granularity sub-observation) — pre-emptive estimate at §6
- Memory: `feedback_partial_falsification_tentative.md` (2 instances) — explicitly NOT bumping per §4 Q4

---

## 11. Auditor verdict requested

1. **§3 D1 lock** — Option 2 regex-replace as drafted? Architect's lean: yes; Jagan confirmed Option 2 at canary 2 handoff.
2. **§4 Q2** — also fix upstream asymmetry in `_run_visitor_alert` (belt-and-braces) OR Option 2 alone?
3. **§4 Q3** — sub-pattern A stays at 5?
4. **§4 Q4** — partial-falsification stays at 2 (not bumping)?
5. **§4 Q5** — pre-emptive test count 4-5 reasonable for this scope?
6. **§4 Q6** — OBS C (multi-pid visitor split) deferred to future spec?
7. **§7 risk surface** — any unaddressed risks?

---

## 12. Next steps

1. **Auditor reviews this Phase 0 audit.** Adjudicates §11.
2. **D1 locked** at Phase 0 sign-off.
3. **Plan v1** drafted with D1 contract + test surface. Plan v1 grep-verifies test count (auditor-Q5 5th instance — Phase 0 granularity self-test).
4. **Plan v2** if precision items surface (anticipated: 1-2 small items at this scope).
5. **Joint sign-off** → developer handoff.
6. **Phase 1 (~2h)** + **Phase 2 (~0.5-1h)** + **Phase 3 (~0.25h)** ship.
7. **RE-CANARY 3** IMMEDIATELY on closure. Same scenario as canary 2. Expected: brain now says "I was talking to Lexi..." with explicit name + search_memory queries entity='Lexi'.
8. **On RE-CANARY 3 PASS**: combined Stage 2 PR fires (D-C Stage 2 + D-D Stage 2 hard-deletes + 130 test-site migrations). **P0.S7 family arc closes definitively.**
9. **On RE-CANARY 3 FAIL**: diagnose new root cause; file follow-up spec.

---

**Standing by for auditor verdict on §11 before drafting Plan v1.**

Mini-spec scope: 1 D-decision, ~3 hours total effort, +5 tests, single edit site at `core/brain_agent.py:3043-3047`. Phase 0 granularity is HIGH per the sub-observation — expect auditor-Q5 5th instance to land ON-TARGET as a confirmation of the granularity correlation.
