# P0.S10 Plan v1 — Brain + classifier identity-mismatch precision tightening

**References:** `tests/p0_s10_s11_s12_canary_day1_bundle_audit.md` §1 (Phase 0).

**Canary source-of-truth:** `terminal_output_2026-05-27_115642.md` lines 114-166. User said `"who said I'm in office I don't have any job and I don't go to office"` → brain fired `report_identity_mismatch` → intent classifier ratified `deny_identity@0.95` → validator passed (no grounding signal for tools without arg_key) → session entered disputed state. **Both LLM judgment AND classifier judgment failed; dual-gate didn't catch.**

**Sibling spec context:** Last spec in canary-Day-1 bundle. P0.S11 + P0.S12 both CLOSED (2026-05-27). §4.2 shipping-order debt fully cleared upon P0.S10 close.

**Cycle shape proposal:** OPTIONAL-Plan-v2 path (architect's lean — Pass-2 grep confirmed Phase 0 scope; multi-layer defense-in-depth fix shape borrowed from P0.S7.5.2 + Session 51 anti-poisoning precedents). If auditor returns ≥1 PI on the D3 regex patterns OR Q1 disposition, cycle escalates to 4-artifact.

---

## §1 Architect-side Pass-2 grep (surface re-verification)

**Phase 0 framing:** 3 D-decisions across 3 distinct layers: D1 classifier prompt + D2 tool description + D3 server-side validator gate. Estimated 8 anchors.

**Pass-2 grep findings (architect, this Plan v1):**

### §1.1 `_INTENT_CLASSIFIER_SYSTEM` surface (D1 target)

Re-verified at `core/brain.py:792-890+`:

- Line 792: `_INTENT_CLASSIFIER_SYSTEM = (` — opens classifier prompt
- Line 803-822: 12 INTENT_LABELS enumerated with brief descriptions
  - Line 809-810: `deny_identity            — user denies the sensor-matched identity ('I'm not Jagan', 'wrong person')`
  - Line 815: `personal_statement       — user shares their own facts/preferences` ✓ **label exists; classifier knows about it**
- Line 823-827: GROUNDING RULE block
- Line 828-842: QUESTION vs ASSERTION RULE block (Session 83 + 94 lineage) — covers question-shaped non-assertions but NOT topic-assertion-vs-identity-assertion distinction
- Line 838: `Never pick deny_identity, confirm_identity, request_shutdown, ...` defensive line
- Line 843+: GREETING-vs-ASSIGN RULE block (Session 94)
- Line 864+: DIRECT-ADDRESS RULE block (Phase 3B.2)

**Pass-2 insight:** the classifier's `personal_statement` label EXISTS and has Session 71 Bug T regression coverage in golden_intent.jsonl (lines 52-54). The bug is NOT a missing label — it's the LLM picking `deny_identity` over `personal_statement` when the user denies a TOPIC vs an IDENTITY. D1 adds an ASSERTION-DOMAIN RULE that disambiguates between these two assertion classes.

### §1.2 `report_identity_mismatch` tool description (D2 target)

Re-verified at `core/brain.py:455-498`:

Current description (verified verbatim in Phase 0 §1.1):
- TRIGGER CHECKLIST (4 items)
- DO-NOT-call list (5 items)
- Question-detection hint at lines 481-486 ("If the user is asking a question... it is almost certainly NOT an identity mismatch")

**Pass-2 insight:** the description is already rich. The LLM IGNORED the existing guidance in the canary turn. Adding MORE guidance has diminishing returns BUT the D2 addition gives the LLM a concrete counter-example from the canary's exact phrasing class — closer to the failure mode than the existing abstract rules.

### §1.3 `_intent_allows` validator surface (D3 target)

Re-verified at `pipeline.py:727-816`:

- Line 762-764: pass-through for tools not in `TOOL_INTENT_MAP`
- Line 765-766: intent match check
- Line 767-772: confidence floor (shutdown special case at 768-769)
- Line 773-794: grounding via `extracted_value`
- Line 795-815: grounding via `tool_args[arg_key]` (Session 87 elif branch)
- Line 816: return `(True, "intent match")`

For `report_identity_mismatch`:
- `TOOL_INTENT_MAP["report_identity_mismatch"] = ("deny_identity", None)` (`core/config.py:503`)
- `arg_key = None` → extracted_value grounding block at 773-794 SKIPPED (when extracted_value is None for `deny_identity` because the classifier doesn't extract a name)
- Line 795 elif → `arg_key is None` → SKIPPED
- Returns `(True, "intent match")` — **NO STRUCTURAL GROUNDING for `report_identity_mismatch`**

**Pass-2 insight:** the validator's existing grounding logic depends on EITHER `extracted_value` OR `arg_key`. `report_identity_mismatch` has neither (its `reason` arg is free-text rationale, not a structured identity field). D3 adds a tool-specific structural gate that requires the user_text to contain an identity-denial phrase — the dual-gate's missing third gate.

### §1.4 Existing test surface (preservation invariant)

Pass-2 found **15 test files** touching `deny_identity` / `report_identity_mismatch` / `personal_statement`:

- `tests/test_dispute_auto_clear.py` — dispute state machine tests
- `tests/test_p0_s5_*.py` — prompt injection tests (no overlap with D1/D2/D3)
- `tests/test_p0_s6_intent_gates.py` — TOOL_INTENT_MAP coverage invariants
- `tests/test_p0_s7_5_2.py` — canary 3 cluster fixes (STRANGER IDENTITY block)
- `tests/test_tool_timeout.py` — tool timeout protection
- `tests/test_prefix_cache.py` — system prompt cache
- 9 audit + plan markdown files (not executable)

**Critical preservation:** `tests/test_p0_s6_intent_gates.py` asserts `TOOL_INTENT_MAP` covers `report_identity_mismatch`. D3 doesn't change the map entry — it adds a tool-specific gate INSIDE `_intent_allows`. The structural invariant test stays green.

**No regression expected** across the 15 test files. Phase 4 spot-check at closure-audit will verify (cumulative suite still green post-D1+D2+D3).

### §1.5 golden_intent.jsonl coverage audit

Pass-2 grep on `tests/golden_intent.jsonl`:

- **26 `deny_identity` rows** — verified explicit identity-denial phrasings (`I'm not Jagan` / `wrong person` / `that's not me` / etc.)
- **`personal_statement` rows present** — Session 71 Bug T lineage at lines 52-54 (`I have a favorite team` / `I'm tired` / `My favorite team is Mumbai Indians`)

**Gap surfaced by canary:** NO `personal_statement` row matching the canary's exact phrasing class — "I don't have [an X that the system asserted I have]" pattern. The canary added one new failure-mode shape: TOPIC-DENIAL where the system's assertion (greeting referenced "office") is what the user denies (not their identity).

A8 anchor adds this regression row tagged `regression_session_canary_day1`.

---

## §2 D-decisions (LOCKED)

### D1 — Intent classifier prompt: ASSERTION-DOMAIN RULE block

**Edit site:** `core/brain.py::_INTENT_CLASSIFIER_SYSTEM` — insert ASSERTION-DOMAIN RULE block IMMEDIATELY AFTER the existing QUESTION-vs-ASSERTION RULE block (currently ending ~line 842 with the `Never pick deny_identity...` defensive line).

**Block content (LOCKED):**

```
"ASSERTION-DOMAIN RULE (Session 10 canary fix — 2026-05-27): when a user "
"ASSERTS something about themselves, distinguish what they're asserting:\n"
"  - IDENTITY denial: user rejects the SENSOR'S NAME for them. They claim "
"    to be someone ELSE OR to NOT BE the named identity. This is deny_identity.\n"
"    Examples: 'I'm not Jagan' / 'You have the wrong person' / 'I'm not who "
"    you think' / 'I'm not him'.\n"
"  - TOPIC denial: user rejects a FACT, ACTIVITY, or TOPIC the system "
"    asserted about them. They are CORRECTING a fact, NOT claiming a "
"    different identity. This is personal_statement (NOT deny_identity).\n"
"    Examples (each line: utterance → correct label):\n"
"    'I don't have a job' → personal_statement (denies activity, not identity)\n"
"    'I don't go to office' → personal_statement (denies activity)\n"
"    'I'm not in school anymore' → personal_statement (denies topic, not name)\n"
"    'That's wrong, I never said that' → personal_statement (correction, not denial)\n"
"    'I don't live there anymore' → personal_statement (fact update)\n"
"DISTINGUISHING TEST: identity-denial REQUIRES the user to reject their "
"NAME or claim to be SOMEONE ELSE. Topic-denial rejects a FACT the system "
"asserted (work, location, school, preferences). When uncertain, prefer "
"personal_statement — a missed deny_identity that should have fired is "
"recoverable on the next turn; a false deny_identity disputes the session "
"and pauses fact extraction (high blast radius).\n\n"
```

**Why this works:** the LLM's failure mode in the canary was lumping "I don't have a job" with "I'm not Jagan" as the same class (rejection-of-something-the-system-asserted). D1 explicitly partitions ASSERTIONS into two domains — IDENTITY (name-claim rejection) vs TOPIC (fact-claim rejection) — with 5 concrete counter-examples + a distinguishing test + a bias toward `personal_statement` on uncertainty.

### D2 — Tool description: topic-correction anti-example

**Edit site:** `core/brain.py:465-480` — extend the existing DO-NOT-call list with topic-correction anti-example as a new bullet.

**Insertion content (LOCKED):**

Add to the existing DO-NOT-call list (after the current 5 bullets at lines 466-474, before the TRIGGER CHECKLIST at line 475):

```
"  - Topic corrections — e.g. 'I don't have a job', 'I don't go to office', "
"'I'm not in school'. These deny FACTS the system asserted about the speaker "
"(work, location, school, activities), NOT the speaker's IDENTITY. Call "
"NOTHING here — let the brain respond conversationally to clarify the fact. "
"Identity-denial requires the speaker to reject their NAME ('I'm not "
"Jagan'), not their activities or topics. Session 10 canary 2026-05-27 fired "
"this tool on 'I don't have any job' — that's a fact update, not an "
"identity claim.\n"
```

**Why this works:** the existing tool description has abstract rules ("denying the sensor's identification of them"). D2 adds a CONCRETE canary-derived counter-example with the exact phrasing class that triggered the failure. Counter-examples are the teeth; abstract rules drift under LLM judgment pressure.

### D3 — `_intent_allows` validator: tool-specific identity-claim grounding gate

**Edit site 1:** `core/config.py` — new constant after `TOOL_INTENT_MAP`:

```python
# P0.S10 D3 — Identity-denial structural gate patterns for report_identity_mismatch.
# Defense-in-depth gate for the third layer of identity-mismatch dual-gate.
# When report_identity_mismatch fires AND classifier says deny_identity@high-conf,
# the validator additionally requires user_text to contain an explicit identity-
# rejection phrase. Without this, "I don't have a job" (topic denial) could
# pass both LLM judgment AND classifier label as deny_identity (canary 2026-05-27).
# Patterns matched case-insensitively against NFKC-casefolded user_text.
IDENTITY_DENIAL_PATTERNS: tuple = (
    # Direct name denial: "I'm not Jagan" / "I am not the person you think"
    r"\b(?:i'?m|i am)\s+not\s+(?:[A-Z][a-z]+|that|who|the\s+(?:right|correct|same))",
    # Wrong-person claim: "you have the wrong person" / "wrong person"
    r"\bwrong\s+person\b",
    # Confusion claim: "you confused me with someone"
    r"\b(?:confused|mistaken|mixed\s+up)\s+(?:me|us)\b",
    # Pronoun denial: "I'm not him" / "I'm not her" / "I'm not them"
    r"\b(?:i'?m|i am)\s+not\s+(?:him|her|them|that\s+person)\b",
    # Direct identity rejection: "that's not me" / "that's not my name"
    r"\bthat'?s\s+not\s+(?:me|my\s+name|who\s+i\s+am)\b",
    # Self-correction with replacement: "my name is X" / "I'm X" / "call me X"
    # (this lets denial-with-replacement pass — caller may use update_person_name
    # instead, but the gate doesn't reject the denial signal itself)
    r"\b(?:my\s+name\s+is|i'?m\s+called|call\s+me)\s+\w+\b",
)
```

**Edit site 2:** `pipeline.py::_intent_allows` — add tool-specific gate AFTER the existing extracted_value/arg_key block (after line 815, before `return (True, "intent match")` at line 816):

```python
    # P0.S10 D3 — Identity-denial structural gate for report_identity_mismatch.
    # The tool has arg_key=None (only arg is free-text `reason`), so neither
    # extracted_value grounding nor arg_key cross-check fires above. This
    # adds the missing third gate: user_text MUST contain an identity-claim-
    # rejection phrase. Canary 2026-05-27 dual-gate failed because
    # classifier said deny_identity@0.95 for "I don't have a job" (topic-
    # denial, NOT identity-denial). LLM judgment + classifier judgment both
    # wrong; this structural gate is the safety net.
    if tool_name == "report_identity_mismatch":
        import re  # noqa: PLC0415 — local import; pattern matching is hot-path
        from core.config import IDENTITY_DENIAL_PATTERNS  # noqa: PLC0415
        _ut = _nfkc_lower(user_text)
        if not any(re.search(p, _ut, re.IGNORECASE) for p in IDENTITY_DENIAL_PATTERNS):
            return (
                False,
                "report_identity_mismatch requires explicit identity-rejection "
                "phrase in user_text (P0.S10 D3 — topic-denial does not warrant "
                "identity-mismatch tool firing)",
            )
```

**Why this works:** the validator's existing dual-gate (intent match + confidence floor + grounding) has a structural blind spot for `report_identity_mismatch` because the tool has no arg_key. D3 adds a third gate that explicitly requires the user_text to contain an identity-claim-rejection phrase. **6 regex patterns** cover the canonical denial shapes; a future canary surfacing a missed phrasing class can extend `IDENTITY_DENIAL_PATTERNS` via a 1-line config addition (NOT a code change).

### D4 — Test surface: `tests/test_p0_s10_identity_mismatch_precision.py` NEW

8 anchors covering D1 + D2 + D3 + regression row:

| # | Type | Coverage |
|---|---|---|
| **A1** | Source-inspection | `_INTENT_CLASSIFIER_SYSTEM` contains `ASSERTION-DOMAIN RULE` block + canary date anchor `Session 10 canary fix — 2026-05-27` |
| **A2** | Source-inspection | Prompt contains ≥3 verbatim counter-examples: `"I don't have a job"`, `"I don't go to office"`, `"I'm not in school anymore"` |
| **A3** | Source-inspection | `report_identity_mismatch` tool description contains `Topic corrections` bullet with canary phrasing `"I don't have any job"` referenced |
| **A4** | Source-inspection | `core/config.py` defines `IDENTITY_DENIAL_PATTERNS` tuple with ≥5 regex patterns; tuple type (immutable) |
| **A5** | Behavioral | `_intent_allows("report_identity_mismatch", "deny_identity", 0.95, None, "I don't have any job and I don't go to office", {})` returns `(False, ...)` with reason containing `P0.S10 D3`; **the canary's exact failure mode** |
| **A6** | Behavioral | `_intent_allows("report_identity_mismatch", "deny_identity", 0.95, None, "I'm not Jagan", {})` returns `(True, "intent match")`; **regression guard — real identity-denial still passes** |
| **A7** | Behavioral parametrized | Pattern coverage across all 6 `IDENTITY_DENIAL_PATTERNS` shapes — each pattern's canonical phrasing passes the gate; each Phase 0 §1.2 counter-example fails the gate (~12 parametrize cases total) |
| **A8** | golden_intent.jsonl row | New row tagged `source="regression_session_canary_day1"` with `user_text="who said I'm in office I don't have any job and I don't go to office"` + `expected_intent="personal_statement"` + canary-date note |

---

## §3 Anchor count LOCK

**Plan v1 LOCK: 8 anchors** at exact mid 8, inclusive ±15% band [6.8, 9.2].

**Pass-2 grep result:** ZERO scope widening from Phase 0. Phase 0 mid was 8; Plan v1 locks 8. Clean confirmation under `### Pre-audit-quantifier-precision-refined-by-grep` operational rule 3 — sustained empirical validation of negative-evidence semantic. Doctrine STAYS at 10 instances (no refinement event).

**Q5 closure projection:**
- Closure-actual = 8 → 0% drift vs Plan v1 LOCK → ON-TARGET exact-mid; extends `Doctrine-prediction-precision-improving-over-arc` sub-rule streak (post-P0.S12: 8 consecutive) to **9 consecutive 0%-streak**
- Closure-actual = 7 → −12.5% vs Plan v1 LOCK → ON-TARGET edge (within ±15%); doctrine HOLDS; streak BREAKS
- Closure-actual = 9 → +12.5% vs Plan v1 LOCK → ON-TARGET edge; doctrine HOLDS; streak BREAKS
- A7 parametrize fan-out: ~12 pytest collections, but logical anchor = 1 (count by spec contract, not by pytest function fan-out — same convention as P0.S11 A3+A4 split)

**§3.1 Honest commitment per `Explicit-closure-honest-count-commitment`:** at closure, the count will be reported HONESTLY regardless of streak implications. If A2/A4/A7 split into multiple test functions via parametrize, logical anchor count stays 8 (matches LOCK). If a Phase 4 ripple necessitates an additional D-decision (e.g. `_strip_im_contraction` interaction with the new patterns), closure-actual may shift to 9 — banked honestly.

---

## §4 Pre-mortem (3 ways this fix could fail)

1. **D1+D2 prompt tightening doesn't prevent LLM judgment failure (recurrence).**
   - Risk: the LLM ignored existing tool-description guidance in the canary; adding more text to prompts may not deterministically prevent recurrence.
   - Mitigation: D3 is the LOAD-BEARING structural safety net. D1+D2 reduce the LLM's probability of bad calls; D3 prevents bad calls from reaching the dispute state regardless of LLM judgment.

2. **D3 regex patterns reject a legitimate identity-denial phrasing we didn't anticipate.**
   - Risk: a future user says e.g. "Who do you think I am? I'm not that guy" — colloquial denial that our patterns might miss.
   - Mitigation: 6 patterns cover the canonical shapes (direct name denial + wrong-person + confusion + pronoun + that's-not-me + name-with-replacement). Extension is a 1-line config addition (NOT a code change), matching `SYSTEM_NAME_ASSIGN_PATTERNS` / `PERSON_NAME_ASSIGN_PATTERNS` precedent from S73. If a canary surfaces a missed phrasing, file P0.S10.X follow-up.

3. **D3 pattern (regex #6) for "name-with-replacement" is too permissive — passes denial-with-replacement that should route to `update_person_name` instead.**
   - Risk: user says "I'm not Jagan, I'm Lexi" — both patterns match. The validator passes `report_identity_mismatch`, but the brain SHOULD have called `update_person_name(Lexi)` per the existing tool description's DO-NOT-call clause #4.
   - Mitigation: D3 is the gate, NOT the routing decision. The brain's tool-choice (between `report_identity_mismatch` and `update_person_name`) is upstream of D3. If the brain chose `report_identity_mismatch` over `update_person_name` here, D3 doesn't override — it just verifies the denial signal exists. This is acceptable: the user explicitly denied + provided a replacement; D3 lets the explicit denial signal through, and the brain's choice of tool is what's evaluated. Closure-audit will verify this via A6 + A7 behavioral tests on the "I'm not Jagan, I'm Lexi" case.

---

## §5 Multi-direction invariant trace

**Forward (canary's exact failure shape):**
```
User: "who said I'm in office I don't have any job and I don't go to office"
  → brain LLM judgment: emits `report_identity_mismatch({'reason': 'speaker insists they are not working'})`
  → intent classifier (post-D1): re-evaluates with ASSERTION-DOMAIN RULE
      → classifier sees "I don't have any job" → matches TOPIC denial counter-example
      → classifies `personal_statement` (NOT `deny_identity`) at high conf
  → _intent_allows (post-D3): even IF classifier somehow still said `deny_identity`,
      → tool_name == "report_identity_mismatch" branch fires
      → IDENTITY_DENIAL_PATTERNS check: "I don't have any job" doesn't match ANY pattern
      → returns (False, "report_identity_mismatch requires explicit identity-rejection phrase...")
  → tool BLOCKED; brain falls through to conversational response
  → session NOT entered into disputed state
  → user can continue correcting the fact naturally
```

**Reverse (real identity-denial still works):**
```
User: "I'm not Jagan"
  → brain LLM judgment: emits `report_identity_mismatch({'reason': 'speaker says not Jagan'})`
  → intent classifier (post-D1): ASSERTION-DOMAIN RULE matches IDENTITY denial counter-example
      → classifies `deny_identity` at high conf
  → _intent_allows (post-D3):
      → tool_name == "report_identity_mismatch" branch fires
      → IDENTITY_DENIAL_PATTERNS pattern #1 matches "i'?m not Jagan"
      → returns (True, "intent match")
  → tool FIRES; session enters disputed state correctly
  → Session 50+ anti-poisoning behavior unchanged
```

**Cross-spec:**
- **P0.S2 dashboard auth invariant** — independent; no overlap.
- **P0.S7.5.2 D4 (KNOWN SPEAKER IDENTITY block):** the canary fix locks-in known-speaker context; D1+D2 add ASSERTION-DOMAIN rule which is orthogonal — known speakers can have topic corrections (Jagan denying he has a job) without triggering identity disputes. **Complementary, not overlapping.**
- **P0.S7.5.2 D5 (FABRICATED ABSENCE bullet):** narrative-honesty discipline; D1+D2 are structural intent disambiguation. **Independent layers.**
- **P0.S11 (factory reset CLI):** independent; no overlap.
- **P0.S12 (terminal_output guard):** independent; no overlap.
- **Session 50+ anti-poisoning fixes (uncle-false-match incident):** D3 PRESERVES the anti-poisoning semantic — real identity-denials still fire the dispute path. **Belt-and-braces extension, not replacement.**

---

## §6 11-gate quality checklist

Per `feedback_strict_industry_standard_mode.md` §1:

| # | Gate | Status |
|---|---|---|
| 1 | Pre-mortem written (3 failure modes) | ✅ §4 |
| 2 | Multi-direction invariant trace (forward + reverse + cross-spec) | ✅ §5 |
| 3 | Pass-1 grep verified (Phase 0 §1.1) | ✅ |
| 4 | Pass-2 grep verified (architect-side; auditor-side pending) | ✅ §1 |
| 5 | Honest Q5 closure projection (§3 LOCK = Phase 0 mid; no widening) | ✅ §3 |
| 6 | Cross-spec impact analyzed (P0.S2 + P0.S7.5.2 + P0.S11 + P0.S12 + Session 50+) | ✅ §5 |
| 7 | Closure-audit scheduled (§7 commitment) | ✅ §7 |
| 8 | Doctrine firings catalogued (§9) | ✅ §9 |
| 9 | Open questions surface with architect's leans (§8 — 4 questions) | ✅ §8 |
| 10 | 11-gate self-audit documented (this section) | ✅ §6 |
| 11 | Architect closure-audit verdict forwarding committed (§7) | ✅ §7 |

---

## §7 Closure-audit commitment

Per `### Architect-reads-production-code-before-sign-off` + `feedback_closure_audit_verdict_cycle_elision.md` (**5th cycle routinization** at this closure, following P0.R10 + P0.R12-R15 + P0.S11 + P0.S12):

**At Phase 4 completion (developer side), architect performs closure-audit:**

1. **Grep-verify D1 contract** — `_INTENT_CLASSIFIER_SYSTEM` contains `ASSERTION-DOMAIN RULE` block with canary date anchor + ≥3 verbatim counter-examples; AST verifies block lives between existing QUESTION-vs-ASSERTION RULE and GREETING-vs-ASSIGN RULE
2. **Grep-verify D2 contract** — `report_identity_mismatch` description contains `Topic corrections` bullet + canary phrasing reference
3. **Grep-verify D3 contract** — `core/config.py` defines `IDENTITY_DENIAL_PATTERNS` tuple; `pipeline.py::_intent_allows` contains the tool-specific gate block
4. **Run D4 test suite** — `pytest tests/test_p0_s10_identity_mismatch_precision.py -v` reports all 8 anchors passing (~12 pytest collections with A7 parametrize)
5. **Run deliberate-regression cycle** — temporarily REMOVE one IDENTITY_DENIAL_PATTERN OR strip D1's ASSERTION-DOMAIN RULE block → confirm A5/A6/A7 fire → revert → confirm tests pass again
6. **Run cumulative suite** — `pytest --tb=no -q` reports 2775 (post-P0.S12) + 8 P0.S10 = 2783 passed + 14 skipped + 9 xfailed; verify the 15 existing tests that touch `deny_identity`/`report_identity_mismatch`/`personal_statement` still pass
7. **golden_intent.jsonl** — A8 anchor verifies the regression row is added with `source="regression_session_canary_day1"`
8. **Real-LLM validation (optional, deferred to canary-re-run):** run the canary's exact phrasing through the live classifier — verify it now labels `personal_statement` instead of `deny_identity`. NOT in the test surface (LLM behavior is non-deterministic); banked as Phase 4-adjacent validation
9. **PowerShell fresh-disk verify** on `to_be_checked.md` deferred-canary entry per locked §6.4 mechanism
10. **Forward closure-audit verdict to auditor** for ratification BEFORE declaring P0.S10 CLOSED — 5th cycle routinization

---

## §8 Open questions for auditor (4 questions; architect's lean per each)

### Q1 — D3 regex pattern #6 (name-with-replacement): ship or refine?

The pattern `r"\b(?:my\s+name\s+is|i'?m\s+called|call\s+me)\s+\w+\b"` matches "my name is Lexi" which is technically a self-introduction (should route to `update_person_name`, not `report_identity_mismatch`). But it ALSO matches "I'm not Jagan, my name is Lexi" — denial-with-replacement.

- **(a)** Ship as-listed (current). Pattern #6 lets denial-with-replacement signal through D3; tool choice (mismatch vs rename) is the brain's call upstream.
- **(b)** Drop pattern #6. Denial-with-replacement utterances would fail D3 if patterns #1-5 don't match. Risk: user says "I'm Lexi, not Jagan" (replacement-with-denial) — pattern #5 matches "I'm Lexi" alone but not the denial structure.
- **(c)** Refine pattern #6 to require denial-context (preceded by a negation within N tokens).

**Architect's lean: (a) ship as-listed.** D3 is the gate, not the routing decision. Tool choice is upstream; D3's job is to verify the denial SIGNAL exists in user_text. Pattern #6 covers the corner case where a user provides a replacement name AS the denial mechanism. Pre-mortem #3 covers the residual risk.

### Q2 — A8 golden_intent.jsonl row tag: `regression_session_canary_day1` vs `regression_session_canary_2026_05_27`?

- **(a)** `regression_session_canary_day1` — semantic (which canary phase surfaced the bug).
- **(b)** `regression_session_canary_2026_05_27` — date-based (matches existing `regression_session_<N>` numeric convention but uses date instead of session number).
- **(c)** `regression_session_p0_s10` — spec-based (matches spec ID).

**Architect's lean: (a) `regression_session_canary_day1`.** Canary day-1 is the unique semantic anchor for this 3-bug bundle. If future canary days surface bugs, they'd be `_day2`, `_day3` etc. Date-based would mix with the existing `regression_session_<N>` numbering and confuse the harvest script. Spec-based loses the canary lineage.

### Q3 — D1 prompt extension placement: after QUESTION-vs-ASSERTION RULE OR after GREETING-vs-ASSIGN RULE?

- **(a)** After QUESTION-vs-ASSERTION RULE (current Plan v1 §2 D1). Topical grouping: QUESTION-vs-ASSERTION distinguishes question shape; ASSERTION-DOMAIN distinguishes assertion content.
- **(b)** After GREETING-vs-ASSIGN RULE (later in the prompt). Closer to the `Never pick deny_identity, ...` defensive line.

**Architect's lean: (a).** Topical grouping reads more naturally — QUESTION vs ASSERTION shape rule, then ASSERTION-DOMAIN content rule. Reader's mental model flows. (b) would scatter the assertion-handling guidance.

### Q4 — Doctrine firings to bank at Plan v1 review?

- **`### Architect-reads-production-code-before-sign-off`** 29 → 30 — Plan v1 Pass-2 grep verified Phase 0 scope held cleanly. Architect's lean: bank.
- **`### Pass-2-grep-auditor-verified-before-Plan-v1-approval`** 9 → 10 — **10th application of the doctrine.** Auditor's standing-offer Pass-2 will determine if it's clean-convergence (architect's lean expects yes) OR caught-real-gap (would be 2nd in track record after P0.R4).
- **`### Pre-audit-quantifier-precision-refined-by-grep`** STAYS at 10 — clean confirmation (Pass-2 didn't widen Phase 0 scope). 5th consecutive clean-confirmation per operational rule 3 — sustained empirical validation continues.
- **`### Phase-0-granular-decomposition-enables-accurate-estimates`** 29 → 30 supporting (closure-conditional, fires only if Q5 closure-actual = 8 exact-mid). 9-consecutive 0%-streak rebuild also closure-conditional.
- **Multi-discipline preventive convergence** — STRONGLY WARRANTED for sub-rule elevation candidacy at next CLAUDE.md update; 5-instance threshold already REACHED at P0.S12 closure. P0.S10 closure may add 6th instance. Architect's lean: elevate to numbered doctrine at canary-week closure narrative OR P0.S10 closure-audit (architect's choice on timing).

---

## §9 Doctrine track-record update commitments (at P0.S10 closure)

If/when P0.S10 closes:

| Doctrine | Pre-P0.S10 | Post-P0.S10 (projected) |
|---|---|---|
| `### Architect-reads-production-code-before-sign-off` | 29 (post-P0.S12) | **30** |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` (if 0% Q5) | 29 supporting | **30 supporting** |
| `Doctrine-prediction-precision-improving-over-arc` sub-rule (if 0% Q5) | 8 consecutive 0%-streak | **9 consecutive 0%-streak rebuild** |
| `### Pre-audit-quantifier-precision-refined-by-grep` | 10 | **STAYS at 10** (clean confirmation; sustained negative-evidence streak) |
| `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` | 9 | **10** |
| `### Zero-precision-items-at-auditor-review` | 24 (post-P0.S12) | **26** if Phase 0 + Plan v1 both clear cleanly |
| OPTIONAL-Plan-v2 sub-rule track record | 18 proof cases | **19** if Plan v1 clears cleanly |
| Closure-audit verdict forwarding routinization | 4 cycles | **5 cycles** |
| `### Induction-surfaces-invariant-gaps` | 13 instances | 14 ONLY IF an in-cycle strengthening fires at Phase 5 (architect's expectation: NO strengthening needed; D3 patterns are explicit + AST-immune. STAYS at 13.) |
| `Explicit-closure-honest-count-commitment` | 27 (post-P0.S12) | **29** (Plan v1 §3 MADE + closure §3 HONORED) |
| Multi-discipline preventive convergence | 5 instances | **6 instances** (sub-rule elevation candidacy STRONGLY WARRANTED at elevation event) |

**Notable:** if P0.S10 closes 0% ON-TARGET → 9-consecutive-0%-streak. This would be the longest 0%-streak in the project's track record. Worth banking as `Doctrine-prediction-precision-improving-over-arc` reaching steady-state for the canary-Day-1 bundle.

---

## §10 Cumulative suite impact

- **Baseline (post-P0.S12):** 2775 passed + 14 skipped + 9 xfailed
- **Post-P0.S10 (projected):** 2783 passed (+8 anchors)
- **No retirements expected** — D1 + D2 + D3 add new test surface; D4 anchors are NEW. Pass-2 §1.4 audit verified the 15 existing tests touching these surfaces preserve their semantics.

---

## §11 Cycle shape recommendation

**Architect's lean: OPTIONAL-Plan-v2 path** (3-artifact cycle: Phase 0 + Plan v1 + closure).

Rationale: Plan v1 is comprehensive (Pass-2 grep verified Phase 0 scope held; pre-mortem covers known risks; cross-spec impact analyzed; D-decisions locked precisely with regex patterns explicit). No precision items anticipated.

If auditor returns ≥1 PI on D3 regex patterns (Q1 disposition) OR D1 prompt placement (Q3 disposition): cycle escalates to 4-artifact (Phase 0 + v1 + v2 + closure).

---

## §12 Ready for auditor

Plan v1 forwarded for:
1. Pass-2 grep convergence check (auditor's standing offer — 10th application of `### Pass-2-grep-auditor-verified-before-Plan-v1-approval`)
2. Q5 estimate calibration (auditor's mid vs architect's LOCK 8)
3. Q1-Q4 open question adjudication
4. Doctrine firings ratification at this Plan v1 review

Architect commits to Plan v2 within ~2 hours of auditor's verdict if any precision items surface. Otherwise: hand off to developer Phase 4 implementation — last spec in canary-Day-1 bundle, closes §4.2 shipping-order debt at the bundle level.

After P0.S10 closes: canary-week closure narrative + decision point (resume canary Days 2-5 OR pivot to P1.A1).