# P0.S5 — Prompt-injection hardening across all agents — Plan v2

**Predecessor:** `tests/p0_s5_plan_v1.md`
**Status:** Plan v2 — auditor's 1 Plan v1 precision item + (c)+(b) §10 disposition addressed
**Mode:** Strict industry-standard + deferred-canary (5th application)

Plan v2 is a refinement over Plan v1. Sections below address only the deltas.

---

## §1. Auditor Plan v1 precision item (1 — addressed)

### D2 direct-consumer enumeration math reconciled (Plan v1 §1.P1 headline-vs-enumeration drift)

**Auditor's catch:** Plan v1 §1.P1 said "8 sites (brain.py:1068 + 7 in brain_agent.py: Extraction ×2 + Contradiction + PromptPref ×2 + FrictionDetection ×2 + Household + SocialGraph)" — counted ROWS (logical agent boundaries) but enumerated 9 line-level sites within brain_agent.py. Off by 2 in the headline.

**Grep-verified at Plan v2 drafting (Pass-1 catch becomes Pass-2 refresh):**

```
grep -nE '"role":\s*"user"' core/brain_agent.py
  458 / 4507 / 4543 / 4588 / 4708 / 4753 / 4895 / 4912 /
  5024 / 5047 / 5128 / 5640 / 5663 / 5720 / 5942 / 6010 / 7108
```

**17 line-level sites in `core/brain_agent.py` + 1 in `core/brain.py` = 18 total LLM-call boundaries.**

**Corrected D2 enumeration (Plan v2 LOCKED):**

**DIRECT (need wrap) — 12 line-level sites across 7 logical agent boundaries:**

| # | File:Line | Function | Logical boundary |
|---|---|---|---|
| 1 | `core/brain.py:1068` | `_classify_intent` | classifier (1 logical) |
| 2 | `core/brain_agent.py:4543` | `ExtractionAgent.extract` (Together) | Extraction (2 paths) |
| 3 | `core/brain_agent.py:4588` | `ExtractionAgent.extract` (Ollama fallback) | same |
| 4 | `core/brain_agent.py:4708` | `ContradictionAgent._call_together` | Contradiction (2 paths) |
| 5 | `core/brain_agent.py:4753` | `ContradictionAgent._call_ollama` (Plan v1 MISSED) | same |
| 6 | `core/brain_agent.py:4895` | `PromptPrefAgent._call_together` | PromptPref (2 paths) |
| 7 | `core/brain_agent.py:4912` | `PromptPrefAgent._call_ollama` | same |
| 8 | `core/brain_agent.py:5024` | `FrictionDetectionAgent` (Together) | FrictionDetection (2 paths) |
| 9 | `core/brain_agent.py:5047` | `FrictionDetectionAgent` (Ollama) | same |
| 10 | `core/brain_agent.py:5128` | `HouseholdExtractionAgent._call_api` | Household (1 path) |
| 11 | `core/brain_agent.py:5942` | `SocialGraphAgent.extract` | SocialGraph (1 path) |
| 12 | `core/brain_agent.py:7108` | `synthesize_room` (RoomSynth narrative — Plan v1 MISSED) | RoomSynth (1 path) |

**Plan v1 missed 2 sites:**

- **Line 4753** — `ContradictionAgent._call_ollama` (Ollama fallback path, parallel to 4708 Together). Same logical boundary as 4708; same risk class. Plan v1's table row 4 said "ContradictionAgent.check" with single line — missed the parallel-path discipline.
- **Line 7108** — `synthesize_room` narrative LLM call (multi-speaker transcript). Plan v1 didn't enumerate this site at all — entire logical agent boundary missed.

**INDIRECT (allowlist) — 6 line-level sites with per-entry rationale:**

| # | File:Line | Function | Rationale |
|---|---|---|---|
| 1 | `core/brain_agent.py:458` | `_ask_privacy_llm` | entity/attribute/value triples |
| 2 | `core/brain_agent.py:4507` | `extract_assistant_room_turn` | Assistant's own prior output |
| 3 | `core/brain_agent.py:5640` | `PatternAnalysisAgent` (Together) | Structured sighting patterns + stats |
| 4 | `core/brain_agent.py:5663` | `PatternAnalysisAgent` (Ollama) | Same as 5640 |
| 5 | `core/brain_agent.py:5720` | `SchemaNormAgent` | Extracted attribute strings (derived from wrapped extraction) |
| 6 | `core/brain_agent.py:6010` | `InsightAgent._call` | Conversation summary, not raw turns |

**Plan v1 §1.P1 indirect headline said "5 entries" but enumerated 6** (row 3 mentioned `5640/5663` = 2 lines). Same headline-vs-enumeration drift class. Plan v2 corrects to 6.

**Corrected D2 surface: 12 direct + 6 indirect = 18 line-level sites audited** (vs Plan v1's claimed "13 LLM-call boundaries audited" which mismatched the actual count).

### Architectural observation on line 7108 (RoomSynth)

The `synthesize_room` narrative path concatenates user_text from multiple speakers into a `transcript` string with speaker labels (e.g., `"[Jagan]: hello\n[Lexi]: hi"`). The transcript IS raw user-typed content; injection vectors in any speaker's utterance reach the LLM via this site.

**Plan v2 disposition:**

D1's `wrap_user_input(text)` applied to the `transcript` works structurally — the speaker labels are formatting added by `synthesize_room`, not part of any user's typed input. Wrapping the assembled transcript in `<user_said>...</user_said>` preserves the multi-speaker context semantically (the LLM sees the speaker labels inside the wrap; treats them as part of the data).

**Alternative:** wrap each per-speaker utterance individually BEFORE concatenation (`<user_said>[Jagan]: hello</user_said>\n<user_said>[Lexi]: hi</user_said>`). More fine-grained but adds wrap-noise. Plan v2 lock: **wrap the assembled transcript once** at the LLM-call boundary; the speaker labels stay inside the wrap as documentation.

If a future canary surfaces multi-speaker injection that the single-wrap doesn't defend, file P0.S5.X. Banking accepted-with-rationale.

---

## §2. §10 Symmetric-over-estimate watch disposition — auditor's (c)+(b) combined applied

**Auditor disposition LOCKED:** (c) methodology re-baseline first + (b) tentative rename held in abeyance pending re-baselined-methodology evidence.

**Methodology re-baseline banked at `feedback_auditor_q5_estimates_trail_grep.md`:**

Operational rule extension landed 2026-05-20: Q5-B trigger math compares actual to **MID-RANGE** of the auditor's estimate band, NOT to upper bound.

**Trigger thresholds applied to MID-RANGE comparison (locked):**

| Result | Disposition |
|---|---|
| UNDER −30% vs mid | Trigger; potential rename to `Auditor-Q5-systematic-over-estimate` |
| OVER +30% vs mid | Trigger; potential rename to `Auditor-Q5-systematic-under-estimate` |
| Within ±15% of mid | ON-TARGET (supporting instance for granular-decomposition doctrine) |
| Between ±15% and ±30% | SLIGHT DRIFT; watch trajectory |

**P0.S5 Plan v1 re-evaluated under re-baselined methodology:**

| Cycle | Estimate band | Mid | Actual | vs UPPER bound | vs MID-RANGE |
|---|---|---|---|---|---|
| P0.S3 | 6-10 | 8 | 9 | −10% | **+12.5%** |
| P0.S4 | 6-10 | 8 | 8 | −20% | **0%** (ON-TARGET) |
| P0.S5 Plan v1 | 6-12 | 9 | 10 | −16.7% | **+11.1%** |
| **P0.S5 Plan v2 (with +2 sites added)** | **6-12** | **9** | **10** | **−16.7%** | **+11.1%** |

**P0.S5 Plan v2 stays at the same logical-anchor count.** The Plan v1 enumeration drift was documentation-only (line-level sites under-counted by 2); the test surface (logical anchors) is unchanged. Plan v2 stays at 10 logical anchors.

**Architect-side observation banked:** all 3 post-elevation cycles land within ±15% of mid-range → ON-TARGET band per the locked methodology. Pattern shift was upper-bound-comparison artifact. The `### Phase-0-granular-decomposition-enables-accurate-estimates` doctrine holds; falsification clause unactivated.

**Tentative rename (b) held in abeyance.** If P0.S6 lands UNDER mid-range (≤ −15%), the rename activates — real systematic bias survived methodology re-baseline. If P0.S6 lands ON or OVER mid-range, the discipline name `Auditor-Q5-estimates-trail-grep` holds.

---

## §3. Updated test surface (Plan v2)

Plan v1 locked 10 logical anchors → ~32 collected. **Plan v2 stays at 10 logical anchors** (the enumeration correction is documentation-only; test count unchanged because the structural test walks AST and catches all sites regardless).

**D2 test allowlist size:** Plan v1 said "5-entry"; **Plan v2 lock: 6-entry** (corrected per §1).

**D2 test expected-coverage assertion:** ~~Plan v1 forecast 13 audited boundaries~~ → **Plan v2 lock: 18 line-level boundaries** (12 direct route through `wrap_user_input` + 6 in allowlist). Total: 18 line-level sites verified.

**Q5-B trigger math (re-baselined per §2):**

- Auditor mid-range: 9 (for 6-12 medium-spec band)
- Plan v2 locked logical anchors: 10
- **Overage vs MID-RANGE: (10 - 9) / 9 = +11.1%** ✓
- Within ±15% tolerance → **ON-TARGET**
- Trigger does NOT activate under re-baselined methodology
- 3rd consecutive ON-TARGET reading under MID-RANGE comparison (P0.S3 +12.5% / P0.S4 0% / P0.S5 +11.1%)

---

## §4. Edit-site enumeration update (Plan v2)

### Production code

Same as Plan v1 §3 with 2 ADDITIONAL call sites in `core/brain_agent.py`:

| File:Line | Action |
|---|---|
| `core/brain_agent.py:4753` | NEW WRAP — `ContradictionAgent._call_ollama` (added per Plan v2 §1) |
| `core/brain_agent.py:7108` | NEW WRAP — `synthesize_room` narrative call. **Wrap the assembled `transcript`** before passing to the LLM call (single-wrap per multi-speaker disposition above) |

**Total direct-consumer wrap sites: 12** (Plan v1 said 10; Plan v2 corrects to 12).

### Tests

Plan v1's test file structure unchanged. D2 test's `_INDIRECT_BOUNDARIES_ALLOWLIST` constant updates to **6 entries** (vs Plan v1's "5"); D2 test's positive expected-coverage assertion updates to scan and verify all **12 direct sites** route through `wrap_user_input`.

---

## §5. Pre-mortem updated count

Plan v1 had 10 failure modes. Plan v2 adds 1 new mode:

### §3.11 — RoomSynth multi-speaker transcript wrap (NEW per Plan v2 §1)

**Failure:** `synthesize_room` concatenates raw user_text from multiple speakers into `transcript` with speaker labels. Plan v2 wraps the assembled transcript once. A malicious speaker could embed `</user_said>...<user_said>injection` inside their utterance → after assembly + wrap → the LLM sees nested `<user_said>` shape.

**Mitigation:** D1's `_XML_TAG_INJECTION_RE` includes `user_said` in the strip pattern (per Phase 0 §3.6 mitigation). The malicious closing tag inside a single speaker's utterance gets stripped BEFORE assembly via per-speaker `wrap_user_input` calls — but Plan v2 disposes single-wrap-on-assembly, not per-speaker pre-wrap.

**Plan v2 refinement:** apply `wrap_user_input` to each speaker's utterance BEFORE assembly into the transcript, THEN apply `wrap_user_input` to the entire transcript. Double-wrap is structurally redundant but defends against the assembly-bypass vector. **OR** keep single-wrap and accept the residual risk per the §1 disposition (banked accepted-with-rationale).

**Locked Plan v2 disposition:** keep single-wrap on assembled transcript (per §1 disposition); accept the residual risk that a speaker embedding `</user_said>` inside their utterance creates a nested wrap shape. The LLM still sees `<user_said>` as outermost data marker; nested tags inside are data per the canonical interpretation. If a real canary surfaces multi-speaker injection, file P0.S5.X to switch to per-speaker pre-wrap.

**Total Plan v2 pre-mortem: 11 failure modes.** Above strict-mode floor.

---

## §6. 11-gate quality checklist (re-affirmed for Plan v2)

No gate changes. The §1 enumeration correction strengthens Gates 1 (Correctness — true site count surfaced) and 9 (Multi-direction trace — RoomSynth side path covered). All 10 APPLIES + 1 N/A justified holds.

---

## §7. Deferred-canary `to_be_checked.md` entry (locked verbatim with Plan v2 corrections)

Plan v1 §6 entry stands with the following corrections per §1:

**REPLACE Plan v1 §6 "Surfaces shipped" 4th bullet with:**

```
- core/brain_agent.py — 12 direct-consumer LLM-call boundaries wrapped
  (per Plan v2 §1 corrected enumeration): Extraction ×2 paths + Contradiction
  ×2 paths + PromptPref ×2 paths + FrictionDetection ×2 paths + Household
  + SocialGraph + RoomSynth (synthesize_room narrative)
```

**ADD to "Test scenario" step 6:**

```
6. Add a new agent with LLM call boundary without wrap_user_input — verify
   D2 structural test fails with line number. Also verify the 6-entry
   allowlist correctly skips structured-data consumers (e/a/v triples,
   assistant-output, pattern stats, schema attributes, conversation summary)
```

**ADD to "Known limitations":**

```
- RoomSynth multi-speaker transcript single-wrap residual risk per Plan v2
  §3.11: a malicious speaker embedding </user_said> inside their utterance
  creates a nested-wrap shape; LLM still sees outermost wrap as data marker
  per canonical interpretation. If multi-speaker injection surfaces in
  canary, file P0.S5.X to switch to per-speaker pre-wrap.
```

---

## §8. Strict-mode operational test (Plan v2)

- [x] Pre-mortem extended (§5 — 11 failure modes; was 10 at Plan v1)
- [x] Multi-direction trace held from Plan v1 §4 + extends to RoomSynth side path
- [x] Quality-gate checklist re-affirmed (§6 — 10/11 APPLIES + 1 N/A)
- [x] Cross-spec impact analysis re-verified (Plan v1 §1 holds)
- [x] Closure-audit scheduled (implicit — discipline floor)

**Strict-mode 18th consecutive application.**

---

## §9. Discipline counts at Plan v2 close

- **Spec-first review cycle:** 27-for-27 → **28-for-28** at Plan v2 land
- **`### Phase-0-catches-wrong-premise`:** stays at **6** (no wrong-premise at Plan v2)
- **Strict-industry-standard mode:** **18th consecutive application**
- **Spec-time grep-verification:** 7 → **8 instances** (D2 enumeration math drift caught at auditor Plan v1 review; Pass-2 refresh applied at Plan v2)
- **Auditor-Q5:** 9 banked + 1 in-flight (Plan v2 at **+11.1% vs MID-RANGE** under re-baselined methodology — **ON-TARGET**)
- **Auditor-precision-item-misframe:** stays at **2**
- **Phase 0 granular-decomposition (CLAUDE.md doctrine):** **6 supporting + 3 closure-conditional candidates** (P0.S3/S4 confirmed; P0.S5 candidate ON-TARGET under re-baselined methodology)
- **Deferred-canary strategy:** 4 → **5th application** in-flight
- **Symmetric-over-estimate watch (banked at P0.S4 closure):** **DISPOSITION APPLIED** — (c)+(b) combined: methodology re-baselined to mid-range comparison; tentative rename held in abeyance pending P0.S6 evidence under re-baselined methodology
- **NEW operational rule banked at memory: Mid-range comparison methodology** (replaces upper-bound comparison for Q5-B trigger math)

---

## §10. Developer handoff (cleared on Plan v2 auditor sign-off)

If auditor returns "APPROVED 0 precision items" at Plan v2:

Developer reads:
- `tests/p0_s5_audit.md` — Phase 0
- `tests/p0_s5_plan_v1.md` — Plan v1 (4 Phase 0 items + 2 informational notes)
- `tests/p0_s5_plan_v2.md` — Plan v2 (THIS file; enumeration reconciliation + methodology re-baseline)

### Implementation phases (~5 hours)

**Phase 1 (~45 min) — `core/sanitize.py` NEW + helper extraction:** unchanged from Plan v1 §11 Phase 1

**Phase 2 (~1.5 hours) — 12 direct-consumer call-site migrations (Plan v2 §4 corrected):**
- `core/brain.py:1068::_classify_intent`
- `core/brain_agent.py` — 11 sites (Extraction ×2, Contradiction ×2 [includes the Plan v1-missed line 4753 Ollama path], PromptPref ×2, FrictionDetection ×2, Household, SocialGraph, RoomSynth)
- Run golden-intent benchmark before + after classifier refactor (P4 byte-identical verification)

**Phase 3 (~1 hour) — D1 unit tests + D2 structural test:** D2 allowlist constant = 6 entries (Plan v2 corrected); expected-coverage assertion = 12 direct sites

**Phase 4 (~1 hour) — D3 injection corpus:** unchanged

**Phase 5 (~45 min) — closure narrative:** unchanged + Pass-2 re-grep for allowlist line numbers + verbatim paste of Plan v2 §7 corrections to `to_be_checked.md`

**Total estimated effort:** ~5 hours.

---

## §11. Plan v3 contingency

Plan v3 is OPTIONAL — only fires if auditor's Plan v2 review surfaces real precision items.

**Architect-side prediction:** Plan v2 absorbed the auditor's 1 Plan v1 precision item cleanly (D2 enumeration math reconciled at line level + RoomSynth surface added + methodology re-baseline applied). Quality-gate checklist is full APPLIES with no borderline items. Working hypothesis predicts auditor returns "APPROVED 0 precision items" at v2.

If auditor surfaces real items at v2 → Plan v3 absorbs them. If clean → ship to developer.

---

**End of Plan v2.**

Ready to share with auditor for v2 review.

**Symmetric-over-estimate watch DISPOSITION applied per (c)+(b) combined:**
- Methodology re-baselined: actuals now compared vs MID-RANGE (locked at memory file)
- Under re-baselined methodology, all 3 post-elevation cycles are ON-TARGET (+12.5% / 0% / +11.1% vs mid)
- Tentative rename held in abeyance pending P0.S6 evidence
- `### Phase-0-granular-decomposition-enables-accurate-estimates` doctrine holds; falsification clause unactivated
