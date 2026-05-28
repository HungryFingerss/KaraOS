# P0.S10 Plan v2 — Brain + classifier identity-mismatch precision tightening (PI #1 absorption)

**References:** `tests/p0_s10_s11_s12_canary_day1_bundle_audit.md` §1 (Phase 0) + `tests/p0_s10_identity_mismatch_precision_plan_v1.md` (Plan v1, BLOCKED by auditor PI #1).

**Plan v2 trigger:** auditor's Plan v1 verdict surfaced PI #1 (BLOCKING) — `IDENTITY_DENIAL_PATTERNS` is NOT a new constant; it ALREADY exists in production at `core/config.py:418-425` (banked Session 73 Bug G3 lineage) + is consumed by `pipeline.py:4382` regex-fallback gate + has 3 existing tests in `test_pipeline.py`. Plan v1 §1.3 framed it as a NEW addition; this is structurally incorrect.

**Caught-real-gap mode:** `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine fires its **2nd caught-real-gap instance** (after P0.R4 PI #1 ENUMERATION-DRIFT). The doctrine's track record extends: 8 clean cycles + 2 caught-real-gap cycles = 10 applications. **Both validation modes proven** structurally.

---

## §1 PI #1 absorption — full surface re-audit

### §1.1 Auditor's grep findings, independently re-verified

Architect-side fresh grep on `IDENTITY_DENIAL_PATTERNS` returns 4 production references:

1. **`core/config.py:418-425`** — constant defined with 6 existing patterns (Session 73 Bug G3 banking; comment block at lines 415-417 documents Jagan's live-run "who are you talking to?" question as the motivating-failure case):
   ```python
   IDENTITY_DENIAL_PATTERNS: tuple[str, ...] = (
       r"\bi(?:'m|\s+am)\s+not\s+\w",                              # "I'm not Jagan" — PERMISSIVE: also matches "I'm not in office"
       r"\bthat(?:'s|\s+is)\s+not\s+me\b",
       r"\byou(?:'ve|\s+have)\s+got\s+the\s+wrong\s+person\b",
       r"\byou(?:'re|\s+are)\s+confusing\s+me\s+(?:with|for)\s+\w",
       r"\bi(?:'m|\s+am)\s+not\s+(?:the\s+person\s+you\s+think|who\s+you\s+think)\b",
       r"\bstop\s+calling\s+me\s+\w",
   )
   ```

2. **`pipeline.py:4382`** — consumed in the regex-fallback branch (`elif INTENT_FALLBACK_TO_REGEX:`) at lines 4381-4395 of the `report_identity_mismatch` handler:
   ```python
   elif INTENT_FALLBACK_TO_REGEX:
       if not _user_text_gate_passes(user_text, None, IDENTITY_DENIAL_PATTERNS):
           # ... log + return "rejected"
   ```

3. **`test_pipeline.py:2330+2340`** — `_user_text_gate_passes` behavioral tests assert positive ("I'm not Jagan, I told you" passes) + negative ("Hey, who are you talking to?" blocks).

4. **`test_pipeline.py:2420-2448`** — `test_identity_denial_patterns_cover_live_run_evidence`:
   - DENIALS list (6 shapes) — all must match at least one pattern
   - BENIGN list (3 shapes; only "who are you talking to?" actively asserted as non-matching)
   - **Comment at lines 2442-2444** explicitly acknowledges the over-permissive pattern #1 as "acceptable false-positive class":
     > `# "I'm not sure" legitimately starts with the same prefix as "I'm not X" — acceptable false-positive class if X=sure is treated as a name denial, but "who are you talking to?" MUST remain benign.`

### §1.2 Architectural implication clarified

**Plan v1 §1.3 framing was wrong.** Corrected:

- ✅ Regex-fallback branch at `pipeline.py:4382` ALREADY uses `IDENTITY_DENIAL_PATTERNS` as a gate.
- ❌ Classifier-driven branch at `pipeline.py:4373-4380` does NOT route through this gate — it just emits `_log_intent_divergence("allow")` based on intent-sidecar verdict alone.
- 🎯 **The canary turn took the classifier-driven branch** (intent_sidecar present with `deny_identity@0.95`) → bypassed the existing regex-fallback gate entirely → no structural gating fired.

So the gap isn't "missing gate" — it's "missing gate on the CLASSIFIER-DRIVEN branch." `_intent_allows` (which the classifier-driven branch routes through) has no `report_identity_mismatch`-specific structural validation.

### §1.3 Procedural lesson — Pass-2 grep extension banked

**Architect-side procedural failure:** Plan v1 §1 Pass-2 grep verified Phase 0's CITED line refs but did NOT grep for whether the PROPOSED new symbol name was already in production. A single command — `grep -n "IDENTITY_DENIAL_PATTERNS" core/ pipeline.py tests/` — would have surfaced PI #1 at draft time.

**Plan v2 commits to formalize this as an architect-side discipline extension:**

> **Pass-2 grep operational rule extension** (architect-memory, candidate for elevation): "For every NEW symbol / constant / function / class proposed in a spec, grep-verify the name is NOT already in production. If it exists, identify the existing surface in spec §1, classify the proposed change as REPLACE / EXTEND / SUPERSEDE, and audit downstream test impact."

This generalizes beyond P0.S10. Sub-shape candidate under `### Pass-2-grep-auditor-verified-before-Plan-v1-approval`: **PRE-EXISTING-SURFACE-MISIDENTIFICATION** — distinct from the existing CODE-TEMPLATE-MISIDENTIFICATION (template/code-shape mismatch) and ENUMERATION-DRIFT (count drift) sub-shapes. First instance at P0.S10 Plan v1; 3+ instances would warrant sub-shape formal banking.

---

## §2 D3 design lock — option (a) REPLACE

### §2.1 Option analysis (auditor's framing ratified)

| Option | Behavior | Downstream impact | Architect's verdict |
|---|---|---|---|
| **(a) REPLACE** | Tighten existing 6 patterns in-place to drop pattern #1's over-permissive shape | 3 test_pipeline.py tests need data-side migration; BOTH gate-firing paths benefit uniformly; cleanest semantic | **LOCKED** |
| (b) EXTEND | Union new + existing patterns | Over-permissive pattern #1 stays active → defeats D3's purpose for the canary's exact phrasing class | REJECTED |
| (c) SUPERSEDE | Add `IDENTITY_DENIAL_PATTERNS_STRICT` as new constant alongside existing | Dual-list maintenance; existing permissive behavior on regex-fallback path stays; no real benefit | REJECTED |

**Lock rationale:** (a) is the cleanest fix. Existing pattern #1 (`\bi(?:'m|\s+am)\s+not\s+\w`) was an artifact of incomplete Session 73 work — the comment at `test_pipeline.py:2442-2444` explicitly acknowledges it as a "false-positive class." Tightening it benefits BOTH gate paths AND eliminates the documented over-permissive shape. Existing test data migration is small (verified §3 below).

### §2.2 Final 6-pattern set (MERGED from Plan v1 §2 D3 proposal + existing)

The MERGE preserves all existing test denials while tightening pattern #1 + broadening coverage on shapes the existing set missed (like bare "wrong person" without "you've got the" prefix):

```python
IDENTITY_DENIAL_PATTERNS: tuple[str, ...] = (
    # 1. Tightened "I'm not X" — requires capital-letter name OR specific
    #    identity referent (that/who/the right/correct/same/person, him/her/them).
    #    Plan v2 §2.2 REPLACES Session 73's over-permissive `\bi(?:'m|\s+am)\s+not\s+\w`
    #    which would match "I'm not in office" / "I'm not sure" — exactly the canary
    #    failure shape (2026-05-27).
    r"\b(?:i'?m|i\s+am)\s+not\s+(?:[A-Z][a-z]+|that|who|the\s+(?:right|correct|same|person)|him|her|them|that\s+person)\b",

    # 2. That's-not-X family (existing #2 broadened with Plan v1 #5's "my name"/"who i am" referents)
    r"\bthat(?:'s|\s+is)\s+not\s+(?:me|my\s+name|who\s+i\s+am)\b",

    # 3. Wrong person — Plan v1 #2 (broader than existing #3 which required "you've got the" prefix)
    r"\bwrong\s+person\b",

    # 4. Confused/confusing/mistaken (existing #4 + Plan v1 #3 merged; covers
    #    "you're confusing me with X" AND "you confused me with X" AND
    #    "you mistook me for X" AND "you've mixed me up with X")
    r"\b(?:confused|confusing|mistaken|mistook|mixed\s+up)\s+me\s+(?:with|for)\s+\w",

    # 5. Not the person you think (existing #5 unchanged — covers
    #    "I'm not the person you think I am" / "I'm not who you think")
    r"\bi(?:'m|\s+am)\s+not\s+(?:the\s+person\s+you\s+think|who\s+you\s+think)\b",

    # 6. Stop calling me X (existing #6 unchanged — covers exhausted/frustrated user
    #    who wants the AI to stop using a wrong name)
    r"\bstop\s+calling\s+me\s+\w",
)
```

**Pattern-by-pattern verification against canary phrasing** "who said I'm in office I don't have any job and I don't go to office":
- #1 `\b(?:i'?m|i\s+am)\s+not\s+(?:[A-Z]...)` — "I'm in" has no "not" → no match ✓
- #2 `\bthat(?:'s|\s+is)\s+not\s+` — no "that's not" → no match ✓
- #3 `\bwrong\s+person\b` — no "wrong person" → no match ✓
- #4 `\b(?:confused|confusing|...)\s+me\s+` — no confusion verbs → no match ✓
- #5 `\bi(?:'m|\s+am)\s+not\s+(?:the\s+person|who\s+you)` — no "I'm not the person you think" → no match ✓
- #6 `\bstop\s+calling\s+me\s+` — no "stop calling me" → no match ✓

**RESULT:** all 6 patterns correctly REJECT the canary's exact phrasing class. ✓

**Pattern-by-pattern verification against `test_identity_denial_patterns_cover_live_run_evidence` denials (test_pipeline.py:2426-2433):**
- "I'm not Jagan" → #1 matches (Jagan ∈ [A-Z][a-z]+) ✓
- "that's not me" → #2 matches (me) ✓
- "you've got the wrong person" → #3 matches (wrong person) ✓
- "you're confusing me with someone" → #4 matches (confusing me with X) ✓
- "I'm not the person you think I am" → #5 matches ✓
- "stop calling me Jagan" → #6 matches ✓

**RESULT:** all 6 existing test denials still match at least one pattern. ✓

**Pattern verification against existing benign cases (`test_pipeline.py:2438-2444`):**
- "who are you talking to?" → no pattern matches (preserved existing benign assertion) ✓
- "I'm not sure what you meant" → #1: `not\s+sure` — "sure" is lowercase, not [A-Z][a-z]+, not in identity-referent list → no match. **Improvement: previously this WAS a documented false-positive; now it's correctly benign.** ✓
- "that's not a problem" → #2: `not\s+a problem` — "a problem" not in (me|my name|who i am) → no match. **Improvement.** ✓

**RESULT:** existing benign cases preserved AND 2 documented false-positives eliminated. ✓

### §2.3 Edit site adjusted

**D3 Edit Site 1 (Plan v1) — SUPERSEDED:**

OLD framing: "NEW constant `IDENTITY_DENIAL_PATTERNS` after `TOOL_INTENT_MAP`"

NEW framing: **MODIFY** existing constant at `core/config.py:418-425`. Replace pattern set with the 6 patterns from §2.2 above. Update inline comment to reference Plan v2 §2.2 + Session 73 lineage preservation.

**D3 Edit Site 2 (Plan v1) — UNCHANGED:**

`pipeline.py::_intent_allows` adds the tool-specific gate AFTER the existing extracted_value/arg_key block. The gate imports + uses the SAME constant — no rename, no shadow.

```python
    # P0.S10 D3 — Identity-denial structural gate for report_identity_mismatch.
    # The tool has arg_key=None, so neither extracted_value grounding nor arg_key
    # cross-check fires above. This adds the missing third gate on the CLASSIFIER-
    # DRIVEN branch: user_text MUST contain an identity-claim-rejection phrase.
    # Canary 2026-05-27 dual-gate failed because classifier said deny_identity@0.95
    # for "I don't have a job" (topic-denial); LLM + classifier both wrong; this
    # structural gate is the safety net. Reuses IDENTITY_DENIAL_PATTERNS (Session 73
    # banking; tightened in Plan v2 §2.2) so BOTH gate-firing paths (classifier-driven
    # via _intent_allows AND regex-fallback via _user_text_gate_passes at pipeline.py:4382)
    # use the SAME pattern set.
    if tool_name == "report_identity_mismatch":
        import re  # noqa: PLC0415
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

---

## §3 Test surface audit (existing tests preserve semantics under REPLACE)

Per auditor's Plan v2 requirement #4, audit of 5 existing references at `test_pipeline.py`:

| Line | Test | Existing assertion | Under REPLACE |
|---|---|---|---|
| 2332 | `test_report_identity_mismatch_user_text_gate_jagan` (approx) | `_user_text_gate_passes("I'm not Jagan, I told you", None, IDENTITY_DENIAL_PATTERNS)` returns True | **Preserved** — pattern #1 matches "I'm not Jagan" |
| 2342 | `test_report_identity_mismatch_user_text_gate_question` (approx) | `_user_text_gate_passes("Hey, who are you talking to?", None, IDENTITY_DENIAL_PATTERNS)` returns False | **Preserved** — no pattern matches a question |
| 2426-2436 | `test_identity_denial_patterns_cover_live_run_evidence` DENIALS loop | All 6 denials must match ≥1 pattern | **Preserved** — §2.2 verification shows all 6 still covered |
| 2445-2448 | Same test, benign assertion | "who are you talking to?" matches NO pattern | **Preserved** — §2.2 verification |
| 2438-2441 | Same test, BENIGN list (documented but not asserted) | Comment acknowledges "I'm not sure" + "that's not a problem" as false-positive class | **Improvement** — both now correctly benign; comment can be deleted or updated |

**Test ripple count: 0 BREAKING changes.** Optional improvement: delete the comment at lines 2442-2444 acknowledging the false-positive class, since the false positives are eliminated under REPLACE. Bank as A4-adjacent ripple at Phase 4.

---

## §4 Anchor count LOCK — STAYS at 8

Per auditor Plan v2 requirement #5 + #6: anchor count under (a) REPLACE = 8 (LOCK unchanged from Plan v1).

| Anchor | D-decision | Updated coverage (under REPLACE) |
|---|---|---|
| **A1** | D1 | `_INTENT_CLASSIFIER_SYSTEM` contains `ASSERTION-DOMAIN RULE` block + canary date anchor — UNCHANGED from Plan v1 |
| **A2** | D1 | Prompt contains ≥3 verbatim counter-examples — UNCHANGED from Plan v1 |
| **A3** | D2 | `report_identity_mismatch` tool description contains `Topic corrections` bullet — UNCHANGED from Plan v1 |
| **A4** | D3 | **REVISED:** `core/config.py:418-425` `IDENTITY_DENIAL_PATTERNS` tuple contains the 6 patterns from §2.2 (FINAL post-REPLACE state, NOT "constant exists" — the constant ALREADY exists per PI #1). Test asserts the EXACT pattern strings per the §2.2 LOCK so future drift fires. |
| **A5** | D3 | **UNCHANGED:** `_intent_allows("report_identity_mismatch", "deny_identity", 0.95, None, "I don't have any job and I don't go to office", {})` returns `(False, ...)` — canary's exact failure mode |
| **A6** | D3 | **UNCHANGED:** `_intent_allows(..., "I'm not Jagan", ...)` returns `(True, "intent match")` — regression guard |
| **A7** | D3 | **REVISED:** parametrized pattern coverage — 6 patterns × (positive case matching + counter-example NOT matching). Updated counter-example list to include: (a) canary's exact "I don't have a job" / "I don't go to office" (Pattern #1 tightening), (b) the 2 newly-eliminated false-positives "I'm not sure" + "that's not a problem" (Pattern #1 + #2 tightening). ~14 parametrize cases. Logical anchor = 1. |
| **A8** | golden_intent.jsonl | UNCHANGED from Plan v1 |

**Q5 closure projection unchanged:**
- Closure-actual = 8 → 0% drift vs Plan v2 LOCK → ON-TARGET exact-mid; extends `Doctrine-prediction-precision-improving-over-arc` to **9 consecutive 0%-streak rebuild** (assuming P0.S12 also closed 0%)
- Closure-actual = 7 or 9 → ±12.5% within ±15% band; ON-TARGET edge; doctrine HOLDS; streak BREAKS

---

## §5 Pre-mortem (refined — 3 ways this fix could fail under REPLACE)

1. **REPLACE introduces a regression in the regex-fallback branch (`pipeline.py:4382`) that wasn't anticipated.**
   - Risk: a phrasing that the existing permissive pattern #1 matched (legitimately, not false-positive) now fails to match. E.g., "I'm not jagan" (lowercase j) — existing #1 matched on `\w`; new #1 requires `[A-Z][a-z]+`.
   - Mitigation: STT normalizes proper nouns to title-case in practice (Whisper). If a real user types/says lowercase variant, the system COULD miss it. Acceptable trade-off — pattern #1 explicitly requires capital name to defend against TOPIC denial ("I'm not in office" — lowercase, plausible). Bank as known limitation; revisit if a canary surfaces lowercase-name-denial.

2. **Test_pipeline.py existing test ordering matters — if A4/A7 anchor tests run BEFORE existing tests, the existing pattern set is no longer in memory at the time existing tests check it.**
   - Risk: stale-module-cache issue if D3 mutates the constant via monkeypatch.
   - Mitigation: D3 does NOT mutate at runtime — it modifies the file source. Test ordering is irrelevant; all tests see the same source state. **No regression expected.**

3. **D3 tool-specific gate fires for the regex-fallback branch too (double-gating).**
   - Risk: regex-fallback branch at `pipeline.py:4382` and `_intent_allows` D3 BOTH check the same patterns. If a phrasing passes the regex-fallback check but fails the D3 gate (or vice-versa), behavior diverges.
   - Mitigation: they use the SAME constant per Plan v2 §2.3. Same pattern set, same matching semantic. Double-gating is idempotent — if regex-fallback allows, D3 also allows (or D3 doesn't fire because the classifier-driven branch took over). Architecturally: the two gates live on DIFFERENT branches of the `if intent_sidecar else if INTENT_FALLBACK_TO_REGEX` conditional; they're mutually exclusive in execution. **No double-gating risk.**

---

## §6 Multi-direction invariant trace (updated)

**Forward (canary's exact failure shape, post-Plan v2):**
```
User: "who said I'm in office I don't have any job and I don't go to office"
  → brain LLM judgment: emits `report_identity_mismatch({'reason': '...'})`
  → intent classifier (post-D1): re-evaluates with ASSERTION-DOMAIN RULE
      → classifier sees "I don't have any job" → matches TOPIC denial counter-example
      → classifies `personal_statement` (NOT `deny_identity`) at high conf
  → _intent_allows (post-D3): even IF classifier still said `deny_identity`,
      → tool_name == "report_identity_mismatch" branch fires
      → IDENTITY_DENIAL_PATTERNS (§2.2 tightened) check:
        Pattern #1: no "I'm not [Capital]" → no match
        Patterns #2-#6: no match (see §2.2 verification)
      → returns (False, "report_identity_mismatch requires explicit identity-rejection...")
  → tool BLOCKED on classifier-driven branch
  → session NOT entered into disputed state
  → user can correct the fact naturally
```

**Reverse (real identity-denial still works):**
```
User: "I'm not Jagan"
  → classifier: deny_identity @ high-conf (D1 ASSERTION-DOMAIN RULE confirms identity-domain)
  → _intent_allows: D3 gate checks IDENTITY_DENIAL_PATTERNS
      → Pattern #1: "i'm not Jagan" matches (Jagan ∈ [A-Z][a-z]+)
      → returns (True, "intent match")
  → tool FIRES; session enters disputed state correctly
```

**Reverse (regex-fallback branch with intent_sidecar=None):**
```
User: "I'm not Jagan" (classifier unavailable, intent_sidecar=None)
  → _intent_allows skips the classifier-driven branch (sidecar None)
  → pipeline.py:4381 elif INTENT_FALLBACK_TO_REGEX path fires
  → _user_text_gate_passes(user_text, None, IDENTITY_DENIAL_PATTERNS)
      → Pattern #1: matches "I'm not Jagan"
      → returns True (gate passes)
  → tool fires; session enters disputed state correctly
```

**Cross-spec (UNCHANGED from Plan v1 §5):** P0.S2 + P0.S7.5.2 + P0.S11 + P0.S12 + Session 50+ all independent or complementary. No new cross-spec interactions introduced by Plan v2.

---

## §7 11-gate quality checklist (Plan v2)

Per `feedback_strict_industry_standard_mode.md` §1:

| # | Gate | Status |
|---|---|---|
| 1 | Pre-mortem written (3 failure modes) | ✅ §5 |
| 2 | Multi-direction invariant trace (forward + reverse + cross-spec + reverse-regex-fallback) | ✅ §6 |
| 3 | Pass-1 grep verified (Phase 0) | ✅ |
| 4 | Pass-2 grep verified (architect-side + auditor-side; PI #1 caught by auditor, absorbed) | ✅ §1 |
| 5 | Honest Q5 closure projection (§4 LOCK 8 unchanged) | ✅ §4 |
| 6 | Cross-spec impact analyzed (P0.S2 + P0.S7.5.2 + P0.S11 + P0.S12 + Session 50+) | ✅ §6 |
| 7 | Closure-audit scheduled (§8 commitment) | ✅ §8 |
| 8 | Doctrine firings catalogued (§9) | ✅ §9 |
| 9 | Open questions surface with architect's leans (§10) | ✅ §10 |
| 10 | 11-gate self-audit documented (this section) | ✅ §7 |
| 11 | Architect closure-audit verdict forwarding committed (§8) | ✅ §8 |
| 12 (NEW) | Pass-2 grep operational rule extension banked (§1.3) | ✅ §1.3 — PRE-EXISTING-SURFACE-MISIDENTIFICATION sub-shape candidate |

---

## §8 Closure-audit commitment

5th cycle routinization at closure (P0.R10 + P0.R12-R15 + P0.S11 + P0.S12 + P0.S10). Same shape as Plan v1 §7 but with one addition:

**NEW step 6.5** — Pass-2 grep on the EXACT shape of `IDENTITY_DENIAL_PATTERNS` post-REPLACE. Verify the 6 patterns match the §2.2 LOCK character-for-character. A4 anchor tests the FINAL state, NOT "constant exists" (which would tautologically pass since the constant already exists).

---

## §9 Doctrine firings at Plan v2 review

| Doctrine | Pre-Plan-v2 | Post-Plan-v2 |
|---|---|---|
| `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` | 9 | **10** ✅ (caught-real-gap mode; 2nd caught-real-gap in track record after P0.R4) |
| `### Pre-audit-quantifier-precision-refined-by-grep` | 10 | **STAYS at 10** ✅ (auditor's read RATIFIED: this is NOT a quantifier-precision refinement — it's SURFACE-IDENTIFICATION axis catching, a different doctrine's territory) |
| **NEW informal observation banked** | — | `PRE-EXISTING-SURFACE-MISIDENTIFICATION` sub-shape candidate under `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` (1st instance at P0.S10 Plan v1 PI #1) |
| **NEW Bidirectional-validation pattern 2nd instance** | — | P0.R9 (architect catches auditor STALE-CACHED-VERIFICATION) + **P0.S10 (auditor catches architect PRE-EXISTING-SURFACE-MISIDENTIFICATION)**. Cross-actor symmetry now 2-instance with both directions represented. Per CLAUDE.md P0.R9 entry "Watch criteria: 3+ bidirectional-validation instances may elevate the cross-actor symmetry framing to its own sub-rule" — next bidirectional event (either direction) triggers `### Bidirectional-validation` sub-rule elevation candidacy. |
| OPTIONAL-Plan-v2 sub-rule track record | 18 proof cases | **STAYS at 18** (P0.S10 does NOT bank as 19th since cycle escalated to 4-artifact via Plan v2 absorption; pattern-broken streak interrupts at P0.S10 Plan v1) |
| Plan-v1-Pass-2-grep-undercount sibling banking | — | Under PRE-EXISTING-SURFACE-MISIDENTIFICATION shape rather than ENUMERATION-DRIFT shape — distinct sub-shape; bank under same doctrine but as new failure-mode dimension |

**Plan v1 §3.1 commitment HONORED:** "the count will be reported HONESTLY regardless of streak implications." This Plan v2 absorbs PI #1 honestly; streak interruption banked transparently.

---

## §10 Open questions for auditor (3 questions; architect's lean per each)

### Q1 — Pattern #1 character class extension: include lowercase pronouns?

§2.2 pattern #1 includes `him|her|them|that\s+person` for pronoun denial. But pronouns are LOWERCASE, while `[A-Z][a-z]+` is the primary name-shape requirement. Is the regex correctly handling both?

Re-reading the regex: `\b(?:i'?m|i\s+am)\s+not\s+(?:[A-Z][a-z]+|that|who|the\s+(?:right|correct|same|person)|him|her|them|that\s+person)\b`

The alternation list is: `[A-Z][a-z]+` (capital name) OR `that` OR `who` OR `the\s+(?:right|correct|same|person)` OR `him|her|them|that\s+person`. The pronouns are explicit literals (no character class), so case-sensitivity depends on the `re.IGNORECASE` flag passed at call time.

**Architect's lean: ship as-listed.** `re.IGNORECASE` is used at both call sites (line 4382 via `_user_text_gate_passes` and new D3 gate). The pronouns match case-insensitively; the capital-letter-name requirement still enforces tighter shape via `[A-Z][a-z]+` (which IS case-sensitive). The mixed semantic is intentional: capital name pattern is TIGHTER than lowercase referents.

### Q2 — Should A4 anchor verify the EXACT 6-tuple character-for-character?

- **(a)** Exact: A4 reads `IDENTITY_DENIAL_PATTERNS` and asserts `list(IDENTITY_DENIAL_PATTERNS) == [pattern1_str, pattern2_str, ..., pattern6_str]` with the FULL pattern strings.
- **(b)** Shape-only: A4 asserts `len(IDENTITY_DENIAL_PATTERNS) == 6` + each is a valid regex.
- **(c)** Hybrid: A4 asserts (b) shape + spot-checks that pattern #1 contains `[A-Z][a-z]+` (the canary-killer signature) but doesn't pin every character.

**Architect's lean: (c) hybrid.** Exact (a) is brittle to refactors that whitespace-shift the patterns without changing semantics; shape-only (b) misses the tightening invariant (pattern #1's `[A-Z][a-z]+` IS the load-bearing change). Hybrid catches the load-bearing semantic shift while tolerating cosmetic edits.

### Q3 — Should Plan v2 §1.3 procedural extension be formalized at this closure?

The Pass-2 grep rule extension ("for every NEW symbol proposed, grep-verify name uniqueness") could either:
- **(a)** Bank as architect-memory observation, defer formal banking to next 3+ instance accumulation
- **(b)** Formalize NOW under `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` as PRE-EXISTING-SURFACE-MISIDENTIFICATION sub-shape (parallel to existing CODE-TEMPLATE-MISIDENTIFICATION + ENUMERATION-DRIFT sub-shapes)
- **(c)** Wait until 2nd instance surfaces before sub-shape banking

**Architect's lean: (b) formalize now.** 1st instance + 4-criteria check passes: instance enumeration ✓ (1 distinct cycle, clear procedural failure), discipline-stability ✓ (canonical example), cross-reference integrity ✓ (parallel to existing sub-shapes), falsification clause ✓ (a future cycle where architect's Pass-2 includes symbol-name-uniqueness grep but auditor STILL catches a pre-existing-surface gap would falsify). Banking now establishes the operational rule for future cycles to follow.

---

## §11 Cycle shape impact

**OPTIONAL-Plan-v2 BLOCKED at this cycle** — P0.S10 escalates to 4-artifact (Phase 0 + Plan v1 + Plan v2 + closure). OPTIONAL-Plan-v2 sub-rule track record stays at 18 proof cases.

**Pattern-broken streak interruption:** Plan v1 review surfaced PI #1; this is the FIRST PI surface in the canary-Day-1 bundle (P0.S11 + P0.S12 both cleared 0 PIs at Plan v1). Architect's closure-audit will compute exact streak break point + bank under `### Zero-precision-items-at-auditor-review` pattern-broken streak tracking.

---

## §12 Ready for auditor (Plan v2 absorption)

Plan v2 forwarded for:
1. PI #1 absorption ratification (REPLACE option locked; pattern set §2.2 verified against canary + existing test denials)
2. Q1-Q3 open question adjudication
3. PRE-EXISTING-SURFACE-MISIDENTIFICATION sub-shape banking decision (§10 Q3)
4. Bidirectional-validation 2nd instance ratification (§9)
5. Doctrine firings ratification at Plan v2 review

Architect commits to Plan v3 within ~2 hours of auditor's verdict if any new precision items surface (unlikely — Plan v2 absorption is targeted). Otherwise: hand off to developer Phase 4 implementation.

**Procedural commitment for future cycles:** architect-side Pass-2 grep will INCLUDE symbol-name-uniqueness verification for every NEW proposed symbol going forward. This Plan v2 §1.3 banking is the trigger event for the rule's enforcement starting at P0.S10 Phase 4 and beyond.