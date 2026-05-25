# P0.S4 — `_visibility_clause` privacy-level not whitelisted — Plan v2

**Predecessor:** `tests/p0_s4_plan_v1.md`
**Status:** Plan v2 — auditor's 1 Plan v1 precision item addressed inline
**Mode:** Strict industry-standard + deferred-canary (4th application)

Plan v2 is a refinement over Plan v1, not a rewrite. Sections below address only the deltas; everything else in Plan v1 stands.

---

## §1. Auditor Plan v1 precision item (1 — addressed)

### Site enumeration line-number drift + missing `<>` site

**Auditor's catch:** Plan v1 §1.P2's enumeration listed 5 sites but actual grep returns 7 SQL/Cypher comparison sites. Two distinct issues:

1. **Line 3694 (`<>` operator) MISSING** — Plan v1 listed `3696/3804` for Cypher `find_shared_entities` but skipped 3694, the `r.privacy_level <> 'system_only'` site that uses the `<>` operator (regex covers it; enumeration didn't list it).
2. **Line 8064 → 6156 line drift** — Plan v1 listed `run_cross_person_inference` at line 8064 (stale grep from earlier in the conversation referencing a comment mention of `_visibility_clause` at that line); actual SQL comparison site is at line 6156.

**Grep-verified at Plan v2 drafting time (2026-05-20):**

```
$ grep -nE "privacy_level\s*(=|!=|<>|IN|NOT\s+IN)\s*\(?\s*['\"][^'\"]+" core/brain_agent.py
```

Returns 16 matches. Filtered for actual SQL/Cypher comparison sites (excluding docstring + comment mentions):

**7 actual code sites (the test's real coverage):**

| Line | Function | Operator | Tier captured |
|---|---|---|---|
| 538 | `_visibility_clause` (best_friend branch) | `!=` | `system_only` |
| 543 | `_visibility_clause` (non-bf branch, public clause) | `=` | `public` |
| 544 | `_visibility_clause` (non-bf branch, personal clause) | `=` | `personal` |
| **3694** | `find_shared_entities` (Cypher, best_friend) | **`<>`** | `system_only` |
| 3696 | `find_shared_entities` (Cypher, non-bf) | `=` | `public` |
| 3804 | `find_shared_entities` (Cypher, non-bf — second site) | `=` | `public` |
| **6156** | `run_cross_person_inference` (Plan v1 §1.P2 line-drift fix) | `!=` | `system_only` |

**5 documentation mentions (regex matches but harmless — tier values cited in docstrings are all valid PRIVACY_LEVELS members; D2 test passes naturally):**

| Line | Context |
|---|---|
| 525 | `_visibility_clause` docstring — "best_friend: ``privacy_level != 'system_only'``" |
| 3538 | Kuzu schema comment — "find_shared_entities filters at `r.privacy_level = 'public'`" |
| 3772 | `find_shared_entities` docstring — "Cypher WHERE filter `r.privacy_level = 'public'` applied" |
| 3795 | `find_shared_entities` docstring — "P0.S7.D-B: Cypher WHERE adds `r.privacy_level = 'public'`" |
| **4443** | **`extract_assistant_room_turn` docstring — "all with `privacy_level='personal'` (D6)" (added per auditor Plan v2 verdict informational note 2026-05-20; pattern matches regex via `\s*` zero-width match around `=`)** |

**Test behavior on documentation matches:** the regex captures the tier value (`public` / `system_only` / `personal`), the test checks `tier in PRIVACY_LEVELS`, the test passes. **Documentation matches are expected-but-harmless** — they don't trigger false-positives because docstrings naturally cite valid tier names. The test scans for INVALID tiers; valid mentions in docs don't fail it. If a future docstring contains an invalid tier name (e.g., the developer pastes legacy `privacy_level = 'private'` as a counter-example without quoting it as comment-only), the test would FAIL — that's actually the correct behavior, because such a docstring would also be a code-readability hazard.

**Test implementation correctness:** Plan v1's locked code at §1.P1 is structurally correct — module-wide AST scan catches all 7 code sites + 4 doc mentions, all PRIVACY_LEVELS members are valid, test passes. The defect was documentation-only (Plan v1's enumeration mismatched the regex's actual coverage). Locked code stays as-is.

**Bank as 6th instance of spec-time grep-verification discipline** (`feedback_spec_time_grep_verification.md`). Pass 1 caught at Plan v1 auditor review; Pass 2 will be at closure when the developer re-greps for final enumeration accuracy. This is the discipline's intended two-pass shape — same as P0.S7.D-B closure narrative line-number drift precedent.

### Known-limitation added (Plan v2 §6 closure narrative update)

```markdown
**Line-number drift over time:** the site enumeration in Plan v2 §1
captures the state of `core/brain_agent.py` as of 2026-05-20 Plan v2
drafting. As the file evolves, line numbers will drift. The module-wide
AST scan in test 6 (`test_brain_agent_sql_tier_literals_are_all_valid`)
is the structural guard — it doesn't rely on line numbers, so the test
keeps working under refactors. Re-grep at closure (Pass 2 verification
per the spec-time grep-verification discipline) to update the
enumeration ONLY IF the enumeration is referenced for operator
guidance; the test itself is line-number-agnostic by design.
```

---

## §2. Updated test surface — locked counts (Plan v2)

**Plan v1 lock:** 8 logical anchors → ~32 collected.
**Plan v2 lock:** **8 logical anchors → ~32 collected** (UNCHANGED — site enumeration fix is documentation-only; test count unchanged).

**Q5-B trigger math at Plan v2 lock:**
- Auditor upper bound: 10
- Plan v2: 8 logical anchors
- **Overage: −20% UNDER upper bound** ✓
- Trigger does NOT activate
- Trajectory continues UNDER: 20% → 7% → 18% → −10% → **−20%** (2nd consecutive UNDER)
- Phase 0 granular-decomposition doctrine's possible attribution (per auditor's Plan v1 review): elevated doctrine is causing tighter Phase 0 decomposition, which produces tighter estimates. Working hypothesis — confirms at closure ON-TARGET.

---

## §3. Updated edit-site enumeration (Plan v2 §1 fix propagated)

### Production code

Same as Plan v1 §3 — no change to production edits.

### Tests

Same as Plan v1 §3 — `tests/test_p0_s4_privacy_level_invariants.py` NEW (8 logical anchors / ~32 collected).

### Documentation

| File | Change |
|---|---|
| `tests/p0_s4_plan_v2.md` (THIS file) | Corrected site enumeration + line-number-drift known-limitation |

---

## §4. Pre-mortem updated count

Plan v1 had 9 failure modes. Plan v2 adds 1 new mode:

### §3.10 — Site enumeration drifts from grep over time (NEW per Plan v2 §1)

**Failure:** Plan v2 §1's site enumeration table captures `core/brain_agent.py` state as of 2026-05-20. As the file evolves (new specs add functions; existing functions get refactored; line numbers shift), the enumeration becomes stale. Future maintainers reading the closure narrative may be confused by line numbers that don't point at SQL comparison sites anymore.

**Mitigation:**

1. **Test implementation is line-number-agnostic** — the AST scan walks every string constant in the module; doesn't reference line numbers in its logic. Even when enumeration drifts, the test keeps working.
2. **Closure narrative documents the drift expectation** — Plan v2 §6 closure paste-template includes the known-limitation about line-number drift over time.
3. **Pass 2 grep at closure** — per `feedback_spec_time_grep_verification.md`, the architect re-greps at closure to refresh the enumeration if it's used for operator guidance. The closure narrative becomes the most-recent-snapshot of the site map.

**Banking as accepted-with-rationale:** site enumeration is operator-facing documentation; line-number drift is expected; the structural test is the actual guard. Worse-case future-failure: stale enumeration → operator confusion when reading the closure narrative → developer re-greps + updates docs. No data-correctness risk; only documentation-clarity risk.

**Total pre-mortem at Plan v2: 10 failure modes** (8 from Phase 0 + Plan v1 + 1 new in Plan v2). Above strict-mode floor.

---

## §5. 11-gate quality checklist (re-affirmed for Plan v2)

No gate changes from Plan v1. The §1 site enumeration fix strengthens Gates 1 (Correctness — corrected enumeration matches actual code), 9 (Multi-direction trace — sideways scope coverage validated), 11 (Doc updates — closure paste-template uses correct line numbers).

All 11 gates remain APPLIES.

---

## §6. Deferred-canary `to_be_checked.md` entry (locked verbatim — Plan v2 final)

Plan v1 §6 entry is canonical-shape. Plan v2 §1 fix propagates to the `Surfaces shipped` section + `Test scenario` section + adds the line-number-drift known-limitation.

**REPLACE Plan v1 §6 "Test scenario" step 6 with:**

```
6. Simulated tier rename in config.PRIVACY_LEVELS (replace "personal" with
   "private" in PRIVACY_LEVELS at config.py) → D2 test fails with the 3
   _visibility_clause SQL literal lines (538/543/544) + the 4
   find_shared_entities Cypher literal lines (3694/3696/3804 plus the
   r.privacy_level <> 'system_only' at 3694 specifically) + the
   run_cross_person_inference site (line 6156) — total 7 code sites
   surfaced + 4 docstring mentions (all 4 are valid tier names; only the
   code sites would fire on the simulated rename)
```

**REPLACE Plan v1 §6 "Known limitations" with the new line-number-drift addition:**

```
Known limitations (banked accepted-with-rationale):
- Existing rows with legacy privacy_level="private" (pre-Session 95 3A.4.5)
  survive P0.S4. They're already invisible via _visibility_clause (which
  doesn't match "private"); P0.S4 prevents NEW invalid rows. Data
  archaeology is a separate spec (S4.X follow-up if it surfaces).
- D2 regex misses `LIKE` / `NOT LIKE` comparisons (no such sites currently
  exist; banking known-limitation).
- D2 regex captures only the FIRST tier in a `privacy_level IN ('public',
  'household')` quoted-list shape (no such sites currently exist; banking
  known-limitation).
- Kuzu graph RELATES_TO edges added pre-P0.S7.D-B (before privacy_level
  column existed) have no privacy_level; current readers handle this via
  `COALESCE(privacy_level, PRIVACY_LEVEL_DEFAULT)` per S95 P3A.6. P0.S4
  doesn't change this.
- Site enumeration in this entry (538/543/544/3694/3696/3804/6156) captures
  brain_agent.py state at closure. Line numbers drift over time as the
  file evolves; the AST scan is line-number-agnostic so the test keeps
  working regardless. Re-grep at any future closure that updates the
  closure narrative.
```

Auditor cross-check at closure: verify entry lands verbatim. Drift in wording = discipline failure flag.

---

## §7. Strict-mode operational test (Plan v2)

- [x] Pre-mortem extended (§4 — 10 failure modes; was 9 at Plan v1)
- [x] Multi-direction trace held from Plan v1 §4 (no new surfaces; §1 fix is documentation)
- [x] Quality-gate checklist re-affirmed (§5 — 11/11 APPLIES)
- [x] Cross-spec impact analysis re-verified (Plan v1 §1 holds)
- [x] Closure-audit scheduled (implicit — executes per discipline)

**Strict-mode 15th consecutive application** (Phase 0 + Plan v1 + Plan v2 = 3 cycles for P0.S4 alone; 12 prior + 3 = 15).

---

## §8. Auditor-Q5 banking (Plan v2 final)

- Phase 0 forecast: 7 logical anchors
- Plan v1 lock: 8 logical anchors (+1 from P3 verification step locked at developer Phase 1)
- Plan v2 lock: **8 logical anchors** (unchanged; §1 fix is documentation-only)
- Auditor upper bound: 10
- **Overage at Plan v2: −20% UNDER upper bound**
- Trigger does NOT activate

**Spec-time grep-verification discipline bumps to 6 instances** (per auditor verdict): P0.S4 Plan v1 §1.P2 enumeration drift (line 8064 → 6156) + missed `<>` site (3694) caught at Pass 1 (Plan v1 auditor review). Pass 2 verification at closure (developer re-greps before pushing the closure narrative).

**Memory file update at closure:** add this 6th instance to `feedback_spec_time_grep_verification.md` track record.

---

## §9. Discipline counts at Plan v2 close

- **Spec-first review cycle:** 24-for-24 → **25-for-25** at Plan v2 land
- **`### Phase-0-catches-wrong-premise`:** stays at **6** (Phase 0 was the wrong-premise catch; Plan v1+v2 didn't surface new)
- **Strict-industry-standard mode:** **15th consecutive application**
- **Spec-time grep-verification discipline:** 5 → **6 instances** (Plan v1 §1.P2 line-drift caught at auditor review)
- **Auditor-Q5:** 8 banked + 1 in-flight (Plan v2 at −20% UNDER upper bound; 2nd consecutive UNDER reading)
- **Auditor-precision-item-misframe (auditor-side):** stays at **2** (no misframe at Plan v1 → v2 transition; auditor's grep was correct)
- **Phase 0 granular-decomposition (CLAUDE.md doctrine):** 6 supporting candidate (closure-conditional per the doctrine's falsification clause)
- **Deferred-canary strategy:** 4th application in flight

---

## §10. Working hypothesis update (strict-mode §8 sub-rule)

P0.S4 confirms the architect's prediction — outcome (2) (Plan v2 needed) is the floor for 3-D-decision medium-specs. The auditor's 1 Plan v1 precision item (site enumeration drift) was a real precision-item-worth iteration, not a documentation nitpick — the closure narrative paste-template would have shipped with stale line numbers if not fixed at Plan v2.

**Updated working hypothesis (post-P0.S4):**

| Scope shape | Floor cadence | Track record |
|---|---|---|
| 1-2 D-decisions, single subsystem, no cross-spec entanglement | v1 only | **P0.S3** (1 instance confirms; OPTIONAL-Plan-v2 path proof case) |
| 3-5 D-decisions, single subsystem, 1-2 cross-spec interactions | **v1 → v2 (likely)** | **P0.S4** (confirms — Plan v2 needed for site enumeration fix + closure narrative paste-template correction) |
| 5+ D-decisions OR multi-subsystem OR cross-language OR canary-derived | v1 → v2 → ... → vN | P0.S7.5.1, P0.S7.5.2, P0.S2 all 3 |

P0.S4 is the **1st 3-D-decision medium-spec data point**. Track record is 1 instance — needs 2-3 more medium-spec cycles before claiming the cadence rule operationalizes. Per the locked operational rule, the hypothesis stays "correlation candidate; needs 5+ instances per band to elevate."

---

## §11. Developer handoff (cleared on Plan v2 auditor sign-off)

Developer reads:
- `tests/p0_s4_audit.md` — Phase 0 audit (premise-falsification context)
- `tests/p0_s4_plan_v1.md` — Plan v1 (4 Phase 0 precision items absorbed)
- `tests/p0_s4_plan_v2.md` — Plan v2 (THIS file; site enumeration fix + line-number-drift known-limitation)

Implementation phases unchanged from Plan v1 §9:
- **Phase 1 (~20 min):** `_process_turn` broad-except grep-verification (per P3 lock)
- **Phase 2 (~30 min):** D1 store_knowledge + _create_edge validation
- **Phase 3 (~30 min):** D2 + D3 invariant tests
- **Phase 4 (~30 min):** D1 behavioral tests
- **Phase 5 (~30 min):** closure (5 surfaces per twin-filename pitfall checklist + Pass 2 site re-grep for closure narrative accuracy)

**Phase 5 closure-narrative update (Plan v2 §1 fix carries forward):** the developer re-greps for SQL/Cypher comparison sites at closure (Pass 2 grep-verification per the discipline) and updates the closure narrative line numbers if drift has occurred between Plan v2 drafting and closure (likely zero drift since developer work is ~2-3 hours; banking the discipline anchor regardless).

**Phase 5 Pass-2 expectation (auditor informational note 2026-05-20):** expect to find **5 doc mentions, not 4**, at the Pass-2 re-grep. Line 4443 (`extract_assistant_room_turn` docstring citing `privacy_level='personal'` (D6)) was caught at the auditor's Plan v2 review and pre-banked in §1's enumeration. If Pass-2 surfaces additional doc mentions beyond the 5 enumerated, update the to_be_checked.md paste-template before closure-narrative finalization. AST scan catches them regardless — line numbers are operator-facing documentation, not test logic.

**Total estimated effort:** ~2-3 hours.

---

**End of Plan v2.**

Ready to share with auditor for v2 review. Per the strict-mode §8 sub-rule:
- If auditor returns "APPROVED 0 precision items" → ship to developer with Plan v2 as the contract (P0.S4 confirms 3-D-decision v1 → v2 cadence).
- If auditor surfaces real items at v2 → Plan v3 absorbs them; iterate until clean.

Architect-side prediction: outcome (1) at v2 is highly likely — the §1 fix was the ONLY Plan v1 item; Plan v2 absorbs it cleanly with grep-verified enumeration + line-number-drift known-limitation; no other surfaces touched. Plan v3 unlikely.
