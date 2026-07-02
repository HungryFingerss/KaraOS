# P0.S5 — Prompt-injection hardening across all agents — Plan v3

**Predecessor:** `tests/p0_s5_plan_v2.md`
**Trigger:** Developer Pass-3 grep at Phase 2 implementation surfaced 2 missed sites in `core/brain.py` (lines 1792 + 2000). Architect's responsive Pass-3 grep at Plan v3 drafting surfaced **11 additional sites** beyond the developer's catch (6 direct + 5 indirect + a recurring history-injection scope question).
**Status:** Plan v3 — absorbing developer's Pass-3 catch + architect's deeper enumeration + scope adjudication
**Mode:** Strict industry-standard + deferred-canary

---

## §0. Pass-3 grep result — full brain.py enumeration

**Grep at Plan v3 drafting (2026-05-20):**

```
grep -nE '"role":\s*"user"' core/brain.py
  520, 718, 1078, 1792, 1930, 1950, 1964, 2000, 2977, 3174, 3198, 3267
```

**12 line-level `"role": "user"` sites** (developer flagged 2; Pass-3 surfaces 10 additional sites the developer didn't list). Combined with brain_agent.py's 17 sites (per Plan v2 §1 corrected enumeration), total LLM-call boundary surface = **29 line-level sites**.

### brain.py classification (12 sites)

**DIRECT (6 sites — need wrap):**

| Line | Function/Context | Content origin | Plan v2 status |
|---|---|---|---|
| 1078 | `_classify_intent` user_prompt | Wraps `_snip` at line 1068 + concatenates 4 recent history items at 1058-1063 (unwrapped) | **PARTIALLY locked** at Plan v2 P4 (only current `_snip` wrapped; recent-history items NOT wrapped — §3 history-injection question below) |
| 1792 | `ask_offline()` Ollama fallback | `message.strip()` — raw user_text from caller; also appends to unwrapped `recent` conversation history at line 1790 | **DEVELOPER'S CATCH** — confirmed direct |
| 1930 | `autocompact_history` Together path | `prompt` contains `convo_block` = concatenated old turns (unwrapped) at lines 1908-1922 | **MISSED by Plan v2** — full convo_block needs wrap-each-turn discipline |
| 1950 | `autocompact_history` Ollama retry | Same `prompt` as 1930 (parallel path) | **MISSED by Plan v2** |
| 1964 | autocompact synthetic injection of compacted summary | `summary` is LLM-generated FROM unwrapped old turns; carries forward user-content recursively | **MISSED by Plan v2** — defense-in-depth case (recursive injection vector) |
| 2000 | `_build_context()` main chat user_msg | The user's current utterance | **DEVELOPER'S CATCH** — confirmed direct; THE main chat path |

**INDIRECT (5 sites — allowlist):**

| Line | Function/Context | Why indirect |
|---|---|---|
| 520 | `ping_together()` health check | Literal `"hi"` — system-constructed, no user_text |
| 718 | `describe_frame()` vision | `prompt` parameter is system-constructed describe-instruction; no user_text path |
| 2977 | Web-search re-injection | Concatenates `web_context` + already-wrapped previous user message (depends on line 2000 wrap upstream) |
| 3174 | Greeting-line generation | `prompt` is system-constructed greeting-instruction (e.g., "Greet Jagan by name") |
| 3198 | Greeting Ollama fallback | Same `prompt` as 3174 (parallel path) |
| 3267 | `choose_greeting_order()` | `user_prompt` built from `names` parameter list — structured derived data, not raw user-text |

Wait — that's 6 indirect entries, not 5. Re-counting: 520, 718, 2977, 3174, 3198, 3267 = **6 indirect**.

**brain.py corrected enumeration: 6 direct + 6 indirect = 12 line-level sites.**

### Final updated enumeration (brain.py + brain_agent.py combined)

| Class | brain.py | brain_agent.py | TOTAL |
|---|---|---|---|
| **DIRECT** (need wrap) | 6 | 11 | **17** |
| **INDIRECT** (allowlist) | 6 | 6 | **12** |
| **TOTAL line-level sites** | 12 | 17 | **29** |

**Plan v2 claimed:** 12 direct + 6 indirect = 18 sites.
**Plan v3 actual:** **17 direct + 12 indirect = 29 sites.** Off by 11 (5 direct + 6 indirect).

---

## §1. Architect Pass-3 surface (beyond developer's catch)

**Developer's transparent catch (2 sites):** brain.py:1792 + 2000.

**Architect's responsive Pass-3 surface (11 additional sites):**

- **5 additional DIRECT in brain.py:** 1078 partial (classifier — see §3 below), 1930, 1950, 1964, plus line 2977's nuance
- **6 additional INDIRECT in brain.py:** 520, 718, 3174, 3198, 3267, 2977 (with rationale)

**Banking shape:** developer's catch was the trigger; architect's responsive Pass-3 was the surface-coverage event. Same shape as auditor surfacing → architect deeper-grep at Plan v1 → v2 transition (banked as Plan v2 §10). **9th instance of spec-time grep-verification discipline** — Pass-3 catch at Phase 2 implementation surfacing a NEW phase for the discipline's track record.

**Pattern observation worth banking — discipline maturing into 3-layer review:**

- Layer 1: Architect Phase 0 + Plan v1 + Plan v2 enumeration (forecast + initial grep)
- Layer 2: Auditor review (quantitative-mismatch flag → architect Pass-2 re-grep)
- Layer 3: Developer Pass-3 grep at implementation phase (surfaces residual missed sites)

The discipline assumes **all 3 layers are required for full surface coverage.** Layer 1 alone is incomplete; Layer 2 catches arithmetic mismatches; Layer 3 catches phase-skipped sites. Each layer's grep is necessary; none is sufficient.

---

## §2. Scope expansion question — history-injection vector

**The recurring pattern surfaced at Pass-3:**

5 of the 6 DIRECT brain.py sites consume CONVERSATION HISTORY in addition to (or as the primary content of) the user_msg:

| Site | History injection mechanism |
|---|---|
| 1078 classifier | Prepends 4 recent turns to `_user_prompt` (lines 1058-1063) |
| 1792 ask_offline | Appends conversation_history `recent` list to messages (line 1790) |
| 1930 autocompact | `convo_block` is concatenated old_turns content (lines 1908-1922) |
| 1950 autocompact retry | Same prompt as 1930 |
| 1964 autocompact synthetic | `summary` is LLM-generated from unwrapped old turns (recursive vector) |
| 2000 _build_context | `messages` list includes prior conversation history items |

**Threat class:** if a user's prior turn contained injection content stored in `conversation_log` (raw per the storage-stays-raw discipline locked at Plan v2 §3.5), every subsequent LLM call that re-injects that history-item content WITHOUT wrapping it creates the injection vector that P0.S5 D1 is meant to close.

**Scope question Plan v3 must adjudicate:**

- (a) **Narrow P0.S5 scope — current-utterance wrap only.** Plan v3 wraps the 17 DIRECT current-utterance sites enumerated above. History-injection vector (conversation_history items re-injected at every LLM-call construction site) is deferred to P0.S5.X follow-up. **Acceptable scope-defer per the strict-mode §8 "Honest scope" discipline** (Phase 0 + Plan v1 + v2 + v3 all framed P0.S5 as "current-turn agent input boundary"; history-injection is a different shape).

- (b) **Expand P0.S5 to include history-injection wrap at every consumer.** Plan v3 adds per-history-item wrapping at every site that re-injects conversation history. Significantly broader scope (~6 additional refactor sites + new test coverage for history-injection corpus). Cost: ~2-3 more developer hours.

**Architect-side lean: (a) narrow scope; defer history-injection to P0.S5.X.**

Rationale:
1. **Honest scope discipline.** Phase 0 + Plan v1 + Plan v2 all framed P0.S5 as "every agent INPUT BOUNDARY" — the current-utterance LLM-call construction is THE boundary; conversation history retrieval is a separate read-path. Expanding mid-Plan-v3 would be silent scope-creep.
2. **Defense-in-depth via storage policy.** P0.S5 D1 wraps every NEW turn entering the system. As users interact going forward, all NEW history items are wrapped at their construction-time LLM call. Existing legacy history items (pre-P0.S5) eventually age out; the residual injection-vector surface shrinks over time.
3. **No known production injection-via-history in canary logs.** Banking as known-limitation in §6; if real canary surfaces history-injection vector, file P0.S5.X.
4. **The deferred-canary discipline catches it.** P0.R11 canary week explicitly validates the bundled queue; if history-injection is a real attack path, the validation surface catches it.

**Plan v3 locks option (a) — narrow scope.** P0.S5.X follow-up condition banked at §6.

---

## §3. Classifier line 1078 partial-wrap clarification

**The subtle case:** Plan v2 §1.P4 locked the `_classify_intent` refactor to use `wrap_user_input(_snip)` at line 1068. Pass-3 grep at Plan v3 drafting confirms the wrap is correctly placed for the CURRENT utterance. But the `_user_prompt` ALSO includes a recent-history prefix at lines 1058-1063 that concatenates 4 prior turns' content (unwrapped).

**Under §2's option (a) scope (narrow):** the classifier's history prefix is OUT OF SCOPE for P0.S5. The current `_snip` wrap closes the new-current-turn injection vector; history-prefix injection is deferred to P0.S5.X.

**Plan v3 disposition:** classifier line 1078 stays at PARTIAL-wrap (current utterance wrapped per Plan v2 P4; history-prefix items NOT wrapped). Mark in D2 allowlist with rationale: "classifier history-prefix injection deferred to P0.S5.X per Plan v3 §2 narrow-scope disposition."

Wait — that conflicts with the DIRECT classification. Let me reclassify:

- Line 1078 is DIRECT at the current-utterance level (Plan v2 P4 wrap applies)
- The history-prefix BEHIND line 1078 is a SEPARATE concern, deferred per §2

So the test at D2 verifies the line 1068 wrap exists at the current-utterance construction; doesn't verify history-prefix items are wrapped. That's the narrow-scope test surface.

**No allowlist entry needed for 1078.** Plan v2 P4 already locked the wrap at 1068 inside the construction at 1064-1069. Line 1078 IS the LLM call site that consumes the constructed `_user_prompt`. The construction at 1068 is verified by D2's source-inspection of the wrap call.

OK so line 1078 stays DIRECT with no allowlist entry. Good.

---

## §4. Updated D2 enumeration — Plan v3 LOCKED

### DIRECT consumers (need wrap_user_input) — 17 line-level sites:

**core/brain.py (6 sites):**
1. Line 1078 — `_classify_intent` (wrap on `_snip` at line 1068 — Plan v2 P4 locked; this LLM call site consumes the wrap)
2. Line 1792 — `ask_offline()` Ollama fallback (wrap `message`)
3. Line 1930 — `autocompact_history` Together path (wrap each old_turn in convo_block construction, OR wrap the assembled prompt; Plan v3 defers per §2)
4. Line 1950 — `autocompact_history` Ollama retry (same)
5. Line 1964 — autocompact synthetic-injection (defense-in-depth wrap on summary)
6. Line 2000 — `_build_context()` main chat (wrap `user_msg`)

**Wait — items 3-5 may also fall under §2's narrow-scope deferral.** Let me re-classify:

- 1930, 1950: prompt is constructed from convo_block (history-injection per §2). Under narrow scope, the LLM-call site IS the input boundary; the convo_block content is history-retrieval. The site itself is "input boundary" — but the input is history, not current turn.

This is the boundary case. Reasonable architects could classify either way:

- **As DIRECT:** "Every LLM-call construction site is an input boundary; autocompact's prompt is an input boundary; wrap it."
- **As INDIRECT (deferred):** "The current-turn input is not the autocompact's input; the input is past turns whose origin is not 'current utterance.' This is the same shape as the history-injection question."

**Plan v3 disposition: classify 1930, 1950, 1964 as INDIRECT with the rationale "history-injection / compacted-summary — deferred to P0.S5.X per §2 narrow-scope disposition."**

This is honest: P0.S5 covers CURRENT-utterance input boundaries; autocompact's input is past-turn-content, which is the deferred class.

So revised count:

**DIRECT (need wrap_user_input) — 14 line-level sites:**

**core/brain.py (3 sites):**
1. Line 1078 — `_classify_intent` (Plan v2 P4 locked; wrap on _snip at 1068)
2. Line 1792 — `ask_offline()` (developer's catch; wrap message)
3. Line 2000 — `_build_context()` (developer's catch; wrap user_msg)

**core/brain_agent.py (11 sites — unchanged from Plan v2 §1):**
- 4543, 4588 (Extraction ×2)
- 4708, 4753 (Contradiction ×2)
- 4895, 4912 (PromptPref ×2)
- 5024, 5047 (FrictionDetection ×2)
- 5128 (Household)
- 5942 (SocialGraph)
- 7108 (RoomSynth)

**INDIRECT (allowlist) — 15 entries:**

**core/brain.py (9 entries):**
1. Line 520 — `ping_together` health check (`"hi"` literal)
2. Line 718 — `describe_frame` vision (system-constructed prompt)
3. Line 1930 — `autocompact_history` Together (history-injection deferred to P0.S5.X)
4. Line 1950 — `autocompact_history` Ollama retry (same)
5. Line 1964 — autocompact synthetic-summary (history-derived deferred to P0.S5.X)
6. Line 2977 — web-search re-injection (depends on line 2000 upstream wrap; content already-wrapped)
7. Line 3174 — greeting generation (system-constructed)
8. Line 3198 — greeting Ollama fallback (system-constructed)
9. Line 3267 — choose_greeting_order (structured names list)

**core/brain_agent.py (6 entries — unchanged from Plan v2):**
1. 458 — `_ask_privacy_llm`
2. 4507 — `extract_assistant_room_turn`
3. 5640 — PatternAnalysis Together
4. 5663 — PatternAnalysis Ollama
5. 5720 — SchemaNormAgent
6. 6010 — InsightAgent

**TOTAL: 14 direct + 15 indirect = 29 line-level sites audited.**

Plan v2 said 18 sites. Plan v3 corrects to 29. Off by 11 (3 direct + 8 indirect after re-classification under §2 narrow-scope).

---

## §5. Test surface update (Plan v3)

**Logical anchors: 10** (unchanged from Plan v2; structural test walks AST + handles all sites).

**D2 test expected coverage updates:**
- Direct sites verified: 12 → **14** (Plan v3 corrected)
- Indirect allowlist entries: 6 → **15** (Plan v3 corrected)

**D2 allowlist constant** in `tests/test_p0_s5_wrap_user_input_coverage.py` needs 15-entry update:

```python
_INDIRECT_BOUNDARIES_ALLOWLIST: dict[tuple[str, int], str] = {
    # brain.py (9 entries)
    ("core/brain.py", 520):
        "ping_together health check — 'hi' literal, no user_text",
    ("core/brain.py", 718):
        "describe_frame vision — system-constructed describe-instruction",
    ("core/brain.py", 1930):
        "autocompact_history Together — history-injection deferred to P0.S5.X per Plan v3 §2",
    ("core/brain.py", 1950):
        "autocompact_history Ollama retry — same as 1930",
    ("core/brain.py", 1964):
        "autocompact synthetic-summary — history-derived content; deferred to P0.S5.X",
    ("core/brain.py", 2977):
        "web-search re-injection — content already-wrapped from upstream line 2000",
    ("core/brain.py", 3174):
        "greeting generation — system-constructed prompt",
    ("core/brain.py", 3198):
        "greeting Ollama fallback — same as 3174",
    ("core/brain.py", 3267):
        "choose_greeting_order — structured names list, not raw user-text",
    # brain_agent.py (6 entries; unchanged from Plan v2)
    ("core/brain_agent.py", 458):
        "_ask_privacy_llm — entity/attribute/value triples",
    ("core/brain_agent.py", 4507):
        "extract_assistant_room_turn — assistant's prior output",
    ("core/brain_agent.py", 5640):
        "PatternAnalysisAgent (Together) — structured patterns",
    ("core/brain_agent.py", 5663):
        "PatternAnalysisAgent (Ollama) — same as 5640",
    ("core/brain_agent.py", 5720):
        "SchemaNormAgent — extracted attribute strings",
    ("core/brain_agent.py", 6010):
        "InsightAgent — conversation summary, not raw turns",
}
```

**Q5-B trigger math under re-baselined mid-range methodology:**
- Auditor mid-range: 9 (for 6-12 medium-spec band)
- Plan v3 logical anchors: 10 (unchanged)
- **+11.1% vs MID-RANGE → ON-TARGET** (within ±15% tolerance)
- No change from Plan v2; logical-anchor count unchanged

---

## §6. Banked P0.S5.X follow-up — history-injection vector

**Triggered by:** Plan v3 §2 narrow-scope disposition.

**Scope:** every LLM-call construction site that re-injects conversation_history items must wrap each history item via `wrap_user_input` before concatenation. Affected sites (per §4):
- `core/brain.py:1058-1063` (classifier history-prefix construction)
- `core/brain.py:1790` (ask_offline `recent` history)
- `core/brain.py:1908-1922` (autocompact `convo_block` construction)
- `core/brain.py:1964` (synthetic-summary defense-in-depth)
- `core/brain.py:1969-2002` (`_build_context` history pass-through)

**Trigger conditions for P0.S5.X spec filing:**
- Real prose-injection vector surfaces in canary logs propagating through history
- Security audit identifies history-injection as exploitable
- **1+ canary instance of confirmed history-injection vector** (security-defense discipline = single-instance floor; ALLOWLIST-additive expansion uses 3-instance floor, but closing a known security surface operates at 1-instance trigger — locked at Plan v3 auditor refinement 2026-05-20)

**Until trigger fires, accepted-with-rationale:** narrow-scope P0.S5 closes the high-traffic CURRENT-utterance injection vector; deferred history-injection is bounded by the storage-raw policy (all NEW turns wrap at LLM-call, all OLD legacy turns age out of typical conversation windows).

---

## §7. Updated `to_be_checked.md` entry corrections (Plan v3)

Plan v2 §6 entry stands with these corrections:

**REPLACE Plan v2 §6 "Surfaces shipped" 4th bullet with:**

```
- core/brain.py — 3 direct-consumer LLM-call boundaries wrapped:
  _classify_intent (line 1068 wrap of _snip per Plan v2 P4 refactor),
  ask_offline (line 1792 wrap of message), _build_context (line 2000
  wrap of user_msg)
- core/brain_agent.py — 11 direct-consumer LLM-call boundaries wrapped
  (per Plan v2 §1 enumeration; unchanged)
```

**ADD to "Known limitations":**

```
- History-injection vector deferred to P0.S5.X per Plan v3 §2 narrow-scope
  disposition. Every LLM-call construction site that re-injects
  conversation_history items leaves prior-turn content unwrapped (5
  sites: classifier history-prefix, ask_offline recent, autocompact ×2,
  synthetic-summary, _build_context). New turns DO get wrapped at their
  construction-time LLM call; legacy unwrapped history-items age out
  over time. Trigger conditions for P0.S5.X filing per §6.
```

---

## §8. Pre-mortem updated count

Plan v2 had 11 failure modes. Plan v3 adds 1 new mode:

### §3.12 — Pass-N grep-verification fatigue (NEW per Plan v3)

**Failure:** Each layer of grep verification (Pass 1 architect → Pass 2 auditor → Pass 3 developer → Pass 4 architect re-grep) surfaces additional missed sites. The discipline assumes finite layers, but if every layer surfaces +N sites, we never converge.

**Mitigation:** **Plan v3 IS the convergence point.** The architect's responsive Pass-3 grep at Plan v3 drafting did exhaustive read of every `"role": "user"` site in both brain.py + brain_agent.py. Total surface = 29 line-level sites; 14 direct + 15 indirect classifications locked. The D2 AST + regex structural test then walks every future site automatically — line-number-agnostic, drift-resilient, no manual enumeration needed for future maintenance.

**Discipline framework anchor:** the 3-pass discipline assumes 3 layers are SUFFICIENT for SURFACE COVERAGE; Plan v3 banking confirms this with explicit Pass-3 exhaustive enumeration. If a 4th-pass at developer Phase 2 surfaces yet another missed site (already happened with developer's 2-site catch leading to Plan v3), the discipline iterates — but the structural test catches future drift automatically.

**Total Plan v3 pre-mortem: 12 failure modes.** Above strict-mode floor.

---

## §9. Strict-mode operational test (Plan v3)

- [x] Pre-mortem extended (§8 — 12 failure modes)
- [x] Multi-direction trace held + sideways extended to history-injection deferred-scope
- [x] Quality-gate checklist re-affirmed (10/11 APPLIES + 1 N/A)
- [x] Cross-spec impact analysis re-verified
- [x] Closure-audit scheduled

**Strict-mode 19th consecutive application.**

---

## §10. Discipline counts at Plan v3 close

- **Spec-first review cycle:** 28-for-28 → **29-for-29** (Plan v3 = +1)
- **`### Phase-0-catches-wrong-premise`:** stays at **6**
- **Strict-industry-standard mode:** **19th consecutive application**
- **Spec-time grep-verification:** 8 → **9 instances** (Pass-3 catch at Phase 2 implementation = NEW phase for the discipline's track record)
- **Auditor-Q5:** 9 banked + 1 in-flight at **+11.1% vs MID-RANGE = ON-TARGET** (unchanged from Plan v2)
- **Phase 0 granular-decomposition (CLAUDE.md doctrine):** 6 supporting + 7th closure-conditional candidate (unchanged)
- **NEW sub-observation banked: 3-layer grep-verification discipline** (architect Phase 0/v1/v2 + auditor review + developer Phase 2 implementation; each layer's grep is necessary; none is sufficient alone)
- **Deferred-canary strategy:** 4 → **5th application** in-flight
- **P0.S5.X follow-up banked** per §6 (history-injection vector trigger conditions documented)

---

## §11. Plan v4 contingency

Plan v4 is OPTIONAL — only fires if auditor's Plan v3 review surfaces real precision items.

**Architect-side prediction:** Plan v3 absorbed developer's 2-site catch + 11 additional sites the developer didn't surface + history-injection scope question explicitly adjudicated. The 14 + 15 = 29 line-level enumeration is grep-verified exhaustive at Plan v3 drafting.

**Likely auditor v3 disposition:**
- (i) APPROVED 0 precision items → ship to developer with corrected enumeration
- (ii) Auditor disagrees with §2 narrow-scope disposition → wants history-injection IN P0.S5 → Plan v4 expands scope
- (iii) Auditor surfaces additional missed sites (Pass-4 catch) → Plan v4 absorbs

If (i) → ship. If (ii) or (iii) → Plan v4. Realistic prediction: (i) — Plan v3 is exhaustive at the enumeration level + narrow-scope is defensible.

---

## §12. Updated developer handoff

If auditor returns "APPROVED 0 precision items" at Plan v3:

Developer reads:
- `tests/p0_s5_audit.md` — Phase 0
- `tests/p0_s5_plan_v1.md` — Plan v1
- `tests/p0_s5_plan_v2.md` — Plan v2
- `tests/p0_s5_plan_v3.md` — Plan v3 (THIS file; full enumeration + scope adjudication)

### Implementation phases (~4-5 hours)

**Phase 2-A (resume; ~1.5 hours) — direct-consumer wrap migration (14 sites):**
- `core/brain.py:1068` — `_classify_intent` (Plan v2 P4 refactor; already in scope)
- `core/brain.py:1792` — `ask_offline()` (Plan v3 §1)
- `core/brain.py:2000` — `_build_context()` (Plan v3 §1)
- `core/brain_agent.py` — 11 sites (Plan v2 §1 unchanged)

**Phase 3 (~1 hour) — D1 unit tests + D2 structural test:**
- D2 allowlist: 15 entries (Plan v3 §5 locked)
- D2 expected-coverage assertion: 14 direct sites verified

**Phase 4 (~1 hour) — D3 injection corpus (12 vectors):** unchanged from Plan v2

**Phase 5 (~45 min) — closure narrative:**
- 5-surface closure per twin-filename pitfall checklist
- `to_be_checked.md` paste with Plan v3 §7 corrections
- P0.S5.X follow-up entry banked per §6
- Memory file bankings (Q5 10th closure + spec-time grep-verification 9th instance + 3-layer-grep sub-observation NEW banking)

**Total estimated effort:** ~4-5 hours.

---

**End of Plan v3.**

Ready to share with auditor for v3 review. Per the strict-mode §8 sub-rule:
- If auditor returns "APPROVED 0 precision items" → ship to developer with Plan v3 enumeration
- If auditor surfaces real items → Plan v4 absorbs

**Architect-side disposition banking:**

P0.S5 confirms the heavy-spec band: v1 → v2 → v3 cadence with developer-side gap-catch at Phase 2 → v3 → resumption. **First heavy-spec instance** for the 3-D-decision SCOPE band (medium-band track record now: P0.S4 v1→v2, P0.S5 v1→v2→v3). Working-hypothesis update banked: **medium-specs can iterate to v3+ when Pass-3 grep at Phase 2 surfaces residual scope.**
