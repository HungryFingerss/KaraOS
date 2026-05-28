# P0.S10 Plan v4 — Brain + classifier identity-mismatch precision tightening (PI #3 absorption)

**References:** Phase 0 + Plan v1 (BLOCKED by PI #1) + Plan v2 (BLOCKED by PI #2) + Plan v3 (BLOCKED by PI #3) + this Plan v4.

**Plan v4 trigger:** auditor's Plan v3 verdict surfaced PI #3 (BLOCKING) — adding "that" to lookahead #4 (adverb-modifier category) was a grammatical-category mistake. "that" is predominantly determiner/pronoun in English; adding it to the adverb-exclusion list caused "I'm not that person" (legitimate high-frequency identity-denial) to no longer match pattern #1. Plan v3 §2.3 empirical verification was ASYMMETRIC — rejection-class verified rigorously, preserve-class not re-verified after lookahead #4 extension.

**Empirically confirmed at Plan v4 drafting:** independent hand-trace + Python REPL verified — "I'm not that person" / "I'm not that guy" / "I'm not that one" all FAIL Plan v3 pattern #1 due to lookahead #4's "that\b" assertion firing on the determiner sense.

**Pattern recap (3 PIs across 3 verification axes):**
1. PI #1 (Plan v1): symbol-name-uniqueness grep failure — `PRE-EXISTING-SURFACE-MISIDENTIFICATION`
2. PI #2 (Plan v2): regex-flag-interaction verification failure — `Plan-v2-behavioral-verification-undercount`
3. **PI #3 (Plan v3):** asymmetric empirical verification failure — **`Asymmetric-empirical-verification-undercount` (NEW)**

**3-part Pass-2 grep extension banked at Plan v4** (was 2-part at Plan v3, now 3-part).

---

## §1 PI #3 absorption — own the asymmetric verification gap

### §1.1 Verification-rigor lesson banked (Plan v4)

**Procedural lesson (NEW Plan v4 extension):**

> **Symmetric verification clause:** every change to rejection-class lookaheads MUST re-verify preserve-class doesn't regress, and every change to preserve-class allowlist MUST re-verify rejection-class doesn't false-allow. Same Python REPL run, both tables refreshed. Asymmetric verification (rejection-class only OR preserve-class only) is INSUFFICIENT.

This generalizes from Plan v3's mistake: I added "that" to lookahead #4 to catch "I'm not that important" (rejection-class extension), but didn't re-run preserve-class to check whether legitimate "that person" identity-denials regressed. Both tables must refresh on every change to either class.

### §1.2 Pass-2 grep operational rule extension — NOW 3-part

For every NEW spec element proposed:

1. **Symbol-name-uniqueness grep** (Plan v1 lesson — `PRE-EXISTING-SURFACE-MISIDENTIFICATION`). Run `grep -n "SYMBOL_NAME" core/ pipeline.py tests/` for every proposed constant, function, class, or module-level name.

2. **Behavioral semantic verification under call-site context** (Plan v2 lesson — `Plan-v2-behavioral-verification-undercount`). For every regex/pattern/conditional gate, run via Python REPL against actual call-site context (normalization wrappers, regex flags, surrounding code path) and verify behavioral outcome via `re.search()` results — NOT via character-presence analysis.

3. **Symmetric verification** (Plan v3 lesson — `Asymmetric-empirical-verification-undercount` — NEW). When a pattern serves BOTH rejection-class and preserve-class assertions, every patch to either class MUST re-run BOTH tables fresh. Asymmetric checks miss regressions introduced by the same patch that fixed the other class.

**Effective from P0.S10 Phase 4 onward.** All 3 parts mandatory at Plan v1 drafting for any future spec involving regex/pattern/gate work.

### §1.3 Architect-memory meta-pattern banked (premature to formalize)

Per auditor's Plan v3 verdict closing observation:

> "P0.S10 is now the deepest absorption cycle in project history... each absorption introduces a new gap in adjacent verification axes. This is itself a banking-worthy meta-pattern — `Verification-rigor-spiral` or `Successive-absorption-introduces-new-verification-axes` — but premature to formalize at 1 cycle's worth of evidence."

Architect's lean: bank as architect-memory observation with 1 instance (P0.S10). Watch criteria: if a future spec sees ≥3 consecutive Plan-iteration absorptions surface NEW verification-axis failures, elevate to formal sub-shape. For now, document the meta-pattern's existence; don't elevate.

---

## §2 D3 design — path (A) drop "that" from lookahead #4

### §2.1 Path analysis ratification

Auditor's Plan v3 verdict offered 3 paths:
- **(A) Remove "that" from lookahead #4** — accept "I'm not that important" as known false-positive; D1+D2 upstream gates still catch the LLM misroute. Lowest invasiveness.
- (B) Context-aware "that" handling with adverb-specific lookahead — precise but requires enumerating adverb-that follow-on words.
- (C) Explicit identity-referent allowlist after lookahead — biggest pattern rewrite.

**Architect's lean: (A) — RATIFIED per auditor's Plan v3 lean.** Rationale (auditor's analysis adopted verbatim):

1. "that" is predominantly determiner/pronoun in English, not adverb. The original adverb-modifier categorization at Plan v3 was wrong.
2. Trade-off favors identity-denial preserve: false-NEGATIVES on identity-denial silently fail-open → user disputes identity, system ignores → trust erosion. Topic-denial false-POSITIVES under D3 leak less severely because D1 ASSERTION-DOMAIN RULE + D2 tool description guidance reduce upstream LLM misroute probability. D3 is the LAST gate; D1+D2 are the FIRST.
3. Lowest implementation cost.

### §2.2 Final 6-pattern set (Plan v4)

```python
IDENTITY_DENIAL_PATTERNS: tuple[str, ...] = (
    # 1. "I'm not X" with negative lookahead for topic-denial heads.
    #    Plan v4 path (A) — DROPPED "that" from lookahead #4 (adverb modifiers)
    #    per PI #3 absorption. "that" is predominantly determiner/pronoun in
    #    English (e.g., "I'm not that person" = identity-denial); grouping
    #    it as adverb-modifier broke high-frequency identity-denials.
    #
    #    Lookahead categories (all empirically verified at Plan v4 drafting
    #    via Python REPL — SYMMETRIC verification: both reject + preserve
    #    classes checked; Pass-2 grep part 3 applied):
    #
    #    - Spatial prepositions (16 entries, INCL. compound forms into/onto/upon)
    #    - Epistemic states (6 entries, INCL. interested per Plan v3 §2.2)
    #    - Progressive verbs (9 entries)
    #    - Adverb modifiers (9 entries — "that" REMOVED per PI #3; only
    #      unambiguous adverbs that don't double as determiners/pronouns)
    r"\b(?:i'?m|i\s+am)\s+not\s+"
    r"(?!(?:in|into|at|on|onto|from|with|under|over|against|near|around|for|of|to|upon)\b)"
    r"(?!(?:sure|certain|positive|confident|aware|interested)\b)"
    r"(?!(?:feeling|going|doing|having|getting|making|saying|trying|looking)\b)"
    r"(?!(?:really|very|quite|extremely|just|already|even|too|so)\b)"
    r"\w+",

    # 2. That's-not-X family (Plan v2 §2.2 unchanged)
    r"\bthat(?:'s|\s+is)\s+not\s+(?:me|my\s+name|who\s+i\s+am)\b",

    # 3. Wrong person (Plan v2 §2.2 unchanged)
    r"\bwrong\s+person\b",

    # 4. Confused/confusing/mistaken (Plan v2 §2.2 unchanged)
    r"\b(?:confused|confusing|mistaken|mistook|mixed\s+up)\s+me\s+(?:with|for)\s+\w",

    # 5. Not the person you think (Plan v2 §2.2 unchanged)
    r"\bi(?:'m|\s+am)\s+not\s+(?:the\s+person\s+you\s+think|who\s+you\s+think)\b",

    # 6. Stop calling me X (Plan v2 §2.2 unchanged)
    r"\bstop\s+calling\s+me\s+\w",
)
```

### §2.3 Symmetric empirical verification (Plan v4 — REFRESHED per auditor's requirement)

Both tables run fresh via Python REPL at Plan v4 drafting. Pass-2 grep part 3 (symmetric verification) applied.

**PRESERVE-CLASS (identity-denials — MUST MATCH):**

| Input | Pattern matches | Expected | Verdict |
|---|---|---|---|
| `i'm not jagan` | #1 ("jagan" ∉ any lookahead) | True | ✅ |
| `i'm not him` | #1 ("him" ∉ any lookahead) | True | ✅ |
| `i'm not her` | #1 ("her" ∉ any lookahead) | True | ✅ |
| `i'm not them` | #1 ("them" ∉ any lookahead) | True | ✅ |
| `i'm not the right person` | #1 ("the" ∉ lookaheads) + #5 | True | ✅ |
| `i'm not who you think i am` | #1 ("who" ∉ lookaheads) + #5 | True | ✅ |
| **`i'm not that person`** | **#1 ("that" REMOVED from #4 — now passes)** | **True** | **✅ (PI #3 fix)** |
| **`i'm not that guy`** | **#1 (same)** | **True** | **✅ (PI #3 fix)** |
| **`i'm not that one`** | **#1 (same)** | **True** | **✅ (PI #3 fix)** |

**REJECT-CLASS (topic-denials — MUST NOT match):**

| Input | Pattern #1 match? | Expected | Verdict |
|---|---|---|---|
| `i'm not in school anymore` | False | False | ✅ |
| `i'm not at work today` | False | False | ✅ |
| `i'm not feeling well` | False | False | ✅ |
| `i'm not sure what you meant` | False | False | ✅ |
| `i'm not in office` | False | False | ✅ (canary's EXACT failure class) |
| `i'm not into music` | False | False | ✅ |
| `i'm not interested` | False | False | ✅ |
| `i'm not really sure` | False | False | ✅ |
| `i'm not very happy` | False | False | ✅ |
| `i'm not quite ready` | False | False | ✅ |
| **`i'm not that important`** | **True** | **False ideally** | **⚠️ ACCEPTED LEAK** (path A trade-off; D1+D2 upstream catch) |

**EXISTING TEST DENIALS (`test_pipeline.py:2426-2433`) — UNCHANGED:**

All 6 match at least one pattern (verified Plan v2 §2.2 + Plan v3 §2.3; no change in Plan v4).

**EXISTING BENIGN (`test_pipeline.py:2438-2444`) — UNCHANGED:**

All 3 don't match (preserved Session 73 + improved per Plan v2 §2.2 false-positive elimination).

### §2.4 Known limitations (revised per PI #3 absorption)

Plan v4 ships with the following ACCEPTED edge cases:

1. **"I'm not that important" leaks through D3 as false-positive** (path A trade-off). Pattern #1 matches; D3 gate would allow `report_identity_mismatch`. **Mitigation:** D1 ASSERTION-DOMAIN RULE + D2 tool description guidance reduce upstream LLM misroute probability. D1+D2 are the FIRST gates; D3 is the LAST gate. Empirically: LLM rarely fires `report_identity_mismatch` on adverb-headed topic-denials like "that important" — D1+D2 catch most cases before they reach D3.

2. **Residual adverb edge cases (lower-frequency, NOT in lookahead #4):** "I'm not always X" / "I'm not necessarily X" / "I'm not usually X". Same architecture: extend lookahead #4 by 1-line config addition when canary surfaces. Plan v4 doesn't pre-emptively enumerate these (no canary evidence yet).

3. **Lookahead #4 contains "just" and "even" — flagged by auditor for architect's discretion.** 
   - "just" → could match "I'm not just anyone" (identity-claim of uniqueness). Lower frequency than "that person"; auditor flagged as notable.
   - "even" → could match "I'm not even me anymore" (depressed-register self-doubt). Edge case.
   - **Architect's call: KEEP both in lookahead #4 for Plan v4.** Rationale: "I'm not just anyone" / "I'm not even me anymore" are LOW-frequency compared to common topic-denials ("I'm not just kidding", "I'm not even close"). Re-evaluate if canary surfaces an identity-denial of these shapes.

Bank as §7 closure narrative.

---

## §3 Anchor count LOCK — STAYS at 8

Path (A) doesn't change logical anchor count. A7 parametrize fan-out grows slightly to add 3 "that-person/guy/one" identity-denial preserve cases.

| Anchor | Plan v4 updated coverage |
|---|---|
| A1-A3 | UNCHANGED from Plan v3 (D1 prompt + D2 tool description) |
| **A4** | **STRENGTHENED per auditor's Q2 + Plan v4 symmetric-verification clause.** Hybrid: (1) `core/config.py` `IDENTITY_DENIAL_PATTERNS` tuple exists with 6 patterns; (2) pattern #1 contains 4 lookahead categories with the exact term lists from §2.2 (validates "that" REMOVED + "into/interested" PRESENT); (3) 3-5 behavioral counter-example assertions per auditor's strengthening lean. |
| A5-A6 | UNCHANGED — canary failure mode + identity-denial regression guard |
| **A7** | **EXPANDED — adds preserve-class regression guards.** Parametrized pattern coverage now covers ~27 cases: 9 identity-denials (added "that person/guy/one") + 10 topic-denials reject + 6 existing test denials + 3 existing benign. Logical anchor = 1. |
| A8 | UNCHANGED — golden_intent.jsonl regression row |

**Q5 closure projection unchanged:**
- Closure-actual = 8 → 0% drift → 9-consecutive-0%-streak rebuild (post-P0.S12 baseline)
- Closure-actual = 7 or 9 → ±12.5% within band; ON-TARGET edge; streak BREAKS

---

## §4 Pre-mortem (Plan v4 — refined per auditor's symmetric-verification lesson)

1. **Lookahead #4 still contains "just"/"even"; future canary surfaces an identity-denial shape using these.**
   - Risk: "I'm not just anyone" / "I'm not even me anymore" fail to match → identity-denial silently rejected.
   - Mitigation: §2.4 Known Limitations #3 documents the architect's accepted trade-off; canary-driven extension path is 1-line config (drop the offending word from lookahead #4). Watch criteria documented.

2. **Symmetric verification rule itself has gaps — what about preserve-class regressions from changes to OTHER patterns (not #1)?**
   - Risk: future patch to patterns #2-#6 (e.g., narrow #3 from `\bwrong\s+person\b` to `\bwrong\s+person\b\s+\w+`) could regress preserve-class.
   - Mitigation: Plan v4 §1.2 part 3 generalizes — "every patch to either class MUST re-run BOTH tables." Applies to ALL pattern changes, not just #1.

3. **The 3-part Pass-2 grep extension might still miss a 4th verification axis we haven't surfaced yet.**
   - Risk: cumulative-cascading meta-pattern (Verification-rigor-spiral) suggests future cycles might surface PI #4 from a different axis (e.g., test-fixture interaction, multi-pattern conflict, etc.).
   - Mitigation: §1.3 architect-memory bank with watch criteria; if a 4th axis surfaces in P0.S10 OR a future cycle, formalize as `### Verification-rigor-spiral` doctrine candidate.

---

## §5 11-gate quality checklist — EXTENDED to 14-gate

| # | Gate | Status |
|---|---|---|
| 1 | Pre-mortem written (3 failure modes) | ✅ §4 |
| 2 | Multi-direction invariant trace | ✅ (UNCHANGED from Plan v3 §5) |
| 3 | Pass-1 grep verified (Phase 0) | ✅ |
| 4 | Pass-2 grep verified — Part 1 (symbol-name-uniqueness) | ✅ (PI #1 absorbed at Plan v2) |
| 5 | Pass-2 grep verified — Part 2 (behavioral semantic under call-site context) | ✅ (PI #2 absorbed at Plan v3 §2.3) |
| 6 | **Pass-2 grep verified — Part 3 (SYMMETRIC verification of reject + preserve classes)** | ✅ (NEW gate; PI #3 absorbed at Plan v4 §2.3) |
| 7 | Honest Q5 closure projection (§3 LOCK 8 unchanged across all 4 Plans) | ✅ §3 |
| 8 | Cross-spec impact analyzed | ✅ (UNCHANGED) |
| 9 | Closure-audit scheduled (§7 commitment) | ✅ §7 |
| 10 | Doctrine firings catalogued (§8) | ✅ §8 |
| 11 | Open questions surface with architect's leans (§9) | ✅ §9 |
| 12 | 14-gate self-audit documented (this section) | ✅ §5 |
| 13 | Closure-audit verdict forwarding committed | ✅ §7 |
| **14 (NEW)** | **Symmetric behavioral verification: every rejection-class change re-verifies preserve-class; every preserve-class change re-verifies rejection-class. SAME Python REPL run, BOTH tables refreshed.** | ✅ §2.3 — both tables refreshed at Plan v4 drafting; PI #3 path A verified |

---

## §6 Multi-direction invariant trace (UNCHANGED from Plan v3 §5)

Substituting Plan v4 §2.2 pattern set for Plan v3's. Forward + reverse + reverse-regex-fallback all hold per §2.3 symmetric verification. No re-trace needed.

---

## §7 Closure-audit commitment (7th cycle routinization)

Per `feedback_closure_audit_verdict_cycle_elision.md` 7th cycle (P0.R10 + P0.R12-R15 + P0.S11 + P0.S12 + P0.S10):

**Closure narrative MUST document ALL 3 PI absorptions** (PI #1 + PI #2 + PI #3) transparently — including the architect's procedural failures, the lessons banked, and the 3-part Pass-2 grep extension.

**Closure-audit run:**
1. Grep-verify D1 + D2 + D3 contracts (unchanged from Plan v2/v3)
2. Re-run §2.3 symmetric empirical verification via Python REPL against final production code state of `IDENTITY_DENIAL_PATTERNS`
3. A4 anchor verifies hybrid character-presence + 3-5 behavioral counter-example assertions
4. A7 anchor parametrize fan-out includes 3 "that person/guy/one" preserve cases
5. Deliberate-regression cycle: temporarily ADD "that" back to lookahead #4 → confirm preserve-class tests (A7 "that person/guy/one") fire → revert → confirm green
6. Cumulative suite green (2775 + 8 = 2783)
7. PowerShell fresh-disk verify on to_be_checked.md
8. Forward closure-audit verdict to auditor for ratification — 7th cycle routinization

---

## §8 Doctrine firings (Plan v4 verdict — updated)

| Doctrine | Pre-Plan-v4 | Post-Plan-v4 |
|---|---|---|
| `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` | 10 | **STAYS at 10** — PI #3 is a DIFFERENT discipline's catching event |
| `Plan-v2-behavioral-verification-undercount` (informal) | 1 instance | **STAYS at 1** — PI #3 is NEW shape, not same as PI #2 |
| **NEW informal observation: `Asymmetric-empirical-verification-undercount`** | — | **1st instance at P0.S10 Plan v3 PI #3** |
| **NEW architect-memory observation: `Verification-rigor-spiral`** | — | **1st instance at P0.S10 (3 consecutive Plan iterations × 3 distinct verification-axis failures)** — premature to formalize; watch criteria documented |
| Pass-2 grep operational rule extension | 2-part | **NOW 3-part** (symbol-name-uniqueness + behavioral-semantic + symmetric) |
| 11-gate quality checklist | 13-gate (Plan v3) | **14-gate** (Plan v4 adds gate 14: symmetric verification) |
| `Bidirectional-validation pattern` | 2 instances | **STAYS at 2** — PI #3 same-cycle multi-PI |
| OPTIONAL-Plan-v2 sub-rule track record | 18 | **STAYS at 18** — P0.S10 escalates to 6-artifact cycle |
| `Explicit-closure-honest-count-commitment` | 27 | **31 if Plan v4 closes** at LOCK 8 (Plan v2 + v3 + v4 §3 commitments MADE; closure HONORED — 4 instance increments across the 6-artifact cycle) |

**Cycle shape: 6-artifact** (Phase 0 + Plan v1 BLOCKED + Plan v2 BLOCKED + Plan v3 BLOCKED + Plan v4 + closure). Deepest absorption cycle in project history (matching/exceeding P0.R6.Y's 5-artifact + 6-round bidirectional grep iteration).

---

## §9 Open questions for auditor (3 questions; architect's lean per each)

### Q1 — Lookahead #4 "just" + "even" — keep or audit further?

§2.4 known limitation #3 flagged these per auditor's Plan v3 verdict. Architect's lean: KEEP both in lookahead #4.

- **(a)** Keep both. "I'm not just anyone" / "I'm not even me anymore" are low-frequency identity claims; D1+D2 upstream catch them via LLM judgment. Accept low-frequency identity-denial false-negatives as cost.
- **(b)** Drop "just". "I'm not just anyone" is more common than "I'm not even me anymore"; tighten path-A trade-off further.
- **(c)** Drop both. Most permissive lookahead #4 (7 entries: really/very/quite/extremely/already/too/so).

**Architect's lean: (a) keep both.** Same logic as path-A trade-off — "I'm not that important" is accepted leak; "I'm not just kidding" is the higher-frequency adverb-modifier topic-denial. Re-evaluate if canary surfaces actual identity-denial misroute.

### Q2 — Symmetric verification rule formalization timing

§1.2 part 3 (symmetric verification) is currently architect-side procedural commitment. Should it be elevated to a CLAUDE.md doctrine sub-rule at this closure-audit?

- **(a)** Bank as informal observation (1st instance at P0.S10 PI #3); formalize after 3+ instances per locked precedent.
- **(b)** Elevate to formal sub-shape NOW at closure-audit per 4-criteria check.

**Architect's lean: (a) bank as informal observation.** Mirrors auditor's Q3 adjudication for Plan-v2-behavioral-verification-undercount — defer to 3+ instance threshold. 1-instance elevation would be premature.

### Q3 — Verification-rigor-spiral meta-pattern banking timing

§1.3 architect-memory meta-pattern (Verification-rigor-spiral) is at 1 cycle's worth of evidence. Auditor's Plan v3 verdict explicitly noted "premature to formalize."

**Architect's lean: bank as architect-memory observation, defer formal banking to 3+ cycle threshold.** Watch criteria: if another deep-absorption cycle surfaces ≥3 consecutive Plan-iteration absorptions across distinct verification axes, elevate to formal `### Verification-rigor-spiral` doctrine candidate. For now, document existence; don't elevate.

---

## §10 Procedural commitment summary (Plan v4)

**Pass-2 grep extension NOW 3-part** (cumulative from Plans v1/v2/v3 lessons):

1. Symbol-name-uniqueness grep (every NEW proposed symbol)
2. Behavioral-semantic verification under call-site context (every regex/pattern/gate)
3. SYMMETRIC verification of reject + preserve classes (every pattern serving both class assertions)

**14-gate quality checklist:** all 14 gates ✅ at this Plan v4.

**Effective from P0.S10 Phase 4 onward.** Future spec architects MUST apply all 3 Pass-2 grep parts + all 14 quality gates at Plan v1 drafting time.

---

## §11 Ready for auditor

Plan v4 forwarded for:
1. PI #3 absorption ratification (path A locked; symmetric verification table §2.3 refreshed)
2. Q1-Q3 open question adjudication
3. Pass-2 grep operational rule 3-part extension banking
4. 14-gate quality checklist banking
5. NEW informal observation `Asymmetric-empirical-verification-undercount` acknowledgment (1st instance)
6. NEW architect-memory observation `Verification-rigor-spiral` acknowledgment (1st instance, premature to formalize)
7. 6-artifact cycle shape confirmation

**Architect's expectation:** Plan v4 is the absorption-completion plan. §2.3 symmetric verification ran fresh; both tables verified; no asymmetric coverage gap. Auditor's Pass-2 hand-trace should converge.

**Procedural acknowledgment:** P0.S10 is the deepest absorption cycle in project history — 6 artifacts, 3 distinct verification-axis failures, 3-part Pass-2 grep extension evolved across the cycle. The cumulative architect-side learning is real:

- **Plan v1 lesson:** grep proposed-symbol-name uniqueness, not just cited line refs
- **Plan v2 lesson:** behavioral verification under call-site flags + normalization, not character analysis
- **Plan v3 lesson:** symmetric verification across reject + preserve classes, not asymmetric
- **Plan v4 acknowledgment:** the 3 lessons together form a 3-part discipline; each axis is independent; missing any one re-opens the verification-rigor gap

These are now structurally banked into the architect-side discipline going forward.