# P0.S6 Plan v1 — Tools without intent gates (intent + fallback + handler registry coverage)

**Spec ID:** parent `complete-plan.md:623` — P0.S6 "Tools without intent gates" `[OPEN]`. Distinct from earlier closed P0.S6 (Secrets Management, 2026-05-18). All P0.S6 artifacts for this cycle land at `tests/p0_s6_intent_gates_*.md`.

**Phase 0 base:** `tests/p0_s6_intent_gates_audit.md`. This Plan v1 absorbs:
- Auditor's 3 Phase 0 precision items (P1 ORDERING INVARIANT inline, P2 fallback content adjudication, P3 4th-registry tripwire AST shape).
- Architect's own Pass-2 grep finding: **4th tool registry** (`_TOOL_HANDLERS` at `pipeline.py:4191`) surfaced during Plan v1 drafting. Same coverage-drift class as `TOOL_INTENT_MAP` and `_TOOL_FALLBACKS` — included as **D4**.
- Cross-cycle bookkeeping reconciliation: sub-pattern A count corrected from "stays at 7" (audit §2.R3) to **stays at 6**.

---

## §0. Cross-cycle bookkeeping reconciliation (auditor's bookkeeping flag)

**Auditor's catch:** Phase 0 audit §2.R3 said "Doctrine count stays at 7." Auditor-side tracking shows `### Phase-0-catches-wrong-premise` at **6 instances** after P0.S4 closure (P0.10 + P0.S1 + P0.S6-secrets + P0.S7 + P0.S7.D-D + P0.S4). P0.S5 was ON-TARGET premise; no bump.

**Architect-side verification:**
- CLAUDE.md header narrative (P0.S4 closure block) explicitly states "5 → 6 INSTANCES (P0.10 + P0.S1 + P0.S6 + P0.S7 + P0.S7.D-D + P0.S4). 6th instance crosses the canonical track-record threshold; doctrine matures rather than re-elevating."
- P0.S5 closure narrative (per developer's closure message + `feedback_strict_industry_standard_mode.md` track record entry 11) bumped **`### Phase-0-granular-decomposition-enables-accurate-estimates` 6 → 7**, NOT sub-pattern A. The granular-decomposition doctrine is the one at 7; sub-pattern A is at 6.

**Reconciliation:** my §2.R3 line "Doctrine count stays at 7" was an off-by-one error confusing the two doctrines. The correct count is **`### Phase-0-catches-wrong-premise` STAYS at 6 instances** at P0.S6 Phase 0 (premise was correct-in-spirit; no bump). The `### Phase-0-granular-decomposition-enables-accurate-estimates` doctrine is at 7 supporting instances post-P0.S5.

**Banked as:** **Discipline-count-bump-needs-explicit-justification sub-rule applied PREVENTIVELY ×1 at Plan v1 drafting** (4th preventive instance after P0.S4's two preventive applications + P0.S5's one). The catch was architect-self-detected post-auditor-flag (silent-rollback-by-next-cycle precedent would have triggered otherwise; explicit naming under §9 cross-cycle-handoff transparency precedent is cleaner).

---

## §1. D-decisions (4 decisions; Pass-2 grep surfaced D4)

### D1 — `INTENT_OPTIONAL_TOOLS: frozenset[str]` companion set in `core/config.py`
- **Surface:** `core/config.py:519` (immediately after `TOOL_INTENT_MAP` closing brace).
- **Contract:** new module-level `INTENT_OPTIONAL_TOOLS: frozenset[str] = frozenset({"search_web", "search_memory", "search_room_memory"})`. Verbatim rationale block above the constant naming WHY each is intent-optional:
  - `search_web` — consumed inline inside `core.brain._ask_stream`; tool_call never bubbles to `conversation_turn` classifier gate. Phase 1.5 deferral preserved (15-line existing comment block in config.py:505-519 moves to the new constant's docstring).
  - `search_memory` — read-only query path with no privilege escalation; classifier gate would add latency without security benefit.
  - `search_room_memory` — same shape as search_memory; gate would be cosmetic.
- **Naming choice (per audit §3.1):** plural-subject-noun `INTENT_OPTIONAL_TOOLS` signals "set of tool names," NOT a map shape. Prevents future readers from adding `(intent, arg_key)` tuples by analogy to TOOL_INTENT_MAP.

### D2 — Exhaustive intent-gate startup assertion in `pipeline.py`
- **Surface:** `pipeline.py:6107-6125` (new block, immediately after the existing TOOL_PRIVILEGES assertion at lines 6099-6106).
- **Contract:** assertion that `set(brain.TOOLS_names) == set(TOOL_INTENT_MAP) | INTENT_OPTIONAL_TOOLS` at pipeline.run() entry. Two distinguishable gap shapes in the hard-error message:
  - **Missing:** tool in `brain.TOOLS` but absent from BOTH registries — `f"Tools missing from TOOL_INTENT_MAP ∪ INTENT_OPTIONAL_TOOLS: {sorted(missing)}. Add to TOOL_INTENT_MAP if it needs classifier-gate verification, OR to INTENT_OPTIONAL_TOOLS if intentionally exempt."`
  - **Orphan:** tool in registry but absent from `brain.TOOLS` — `f"Tools in registry but not in brain.TOOLS: {sorted(orphans)}. Remove the registry entry OR re-add to brain.TOOLS."`
- **ORDERING INVARIANT inline comment (P1 from auditor):** comment block IMMEDIATELY ABOVE the assertion mirrors P0.S3 §1.P3 shape — names the ordering rule + cites tests/p0_s6_intent_gates_plan_v1.md as the spec anchor. Future cloud-probe specs grepping `ORDERING INVARIANT` find this assertion at the surface. Verbatim shape:

  ```python
  # ── Intent-gate registry integrity check ─────────────────────────────────
  # ORDERING INVARIANT: this assertion MUST run AFTER the TOOL_PRIVILEGES
  # check above. Privilege misconfiguration is the more common shape (missing
  # row in TOOL_PRIVILEGES blocks ALL callers); surfacing it first gives the
  # operator the right error. Intent-gate misconfiguration is the secondary
  # check (a tool in TOOLS without a TOOL_INTENT_MAP entry would slip past
  # classifier gating but still dispatch privilege-correctly).
  #
  # ORDERING vs P0.S3: this assertion runs AFTER validate_required_env() so
  # env-var errors surface first (P0.S3 ordering anchor).
  #
  # Spec: tests/p0_s6_intent_gates_plan_v1.md §1.D2 (ordering convention
  # locked at the call site so future maintainers grepping "ORDERING
  # INVARIANT" find all three invariants — P0.S2 dashboard, P0.S3 env, P0.S6
  # intent-gate — at the surface they affect).
  ```

### D3 — `_TOOL_FALLBACKS` coverage + startup assertion
- **Surface 1 (registry rows):** `pipeline.py:376-382` — add two entries:
  - `"report_identity_mismatch": "Got it."` — matches Session 28 Issue A shutdown override pattern (acknowledge-then-stay-quiet for dispute-handler tools; the dispute state machine + UI surface the dispute, no spoken elaboration needed).
  - `"search_room_memory":       "Let me think about that."` — mirrors `search_memory`'s fallback (same architectural shape; both are read-only queries with callback-side result rendering).
- **Surface 2 (assertion):** `pipeline.py:~6127-6135` — assertion immediately after D2 assertion. `assert set(brain.TOOLS_names) == set(_TOOL_FALLBACKS) and all(v.strip() for v in _TOOL_FALLBACKS.values())`. Two distinguishable error shapes (missing entry + degenerate whitespace-only value).
- **Fallback content locks (P2 from auditor):**
  - **`report_identity_mismatch: "Got it."`** — RATIONALE: dispute-handler tools acknowledge-then-stay-quiet (Session 28 Issue A precedent). The brain's spoken response stream typically includes hedged language like "I see, let me reconsider" already; the FALLBACK fires only when the LLM emits zero content alongside the tool call. "Got it" matches the user's expectation of "you heard me" without committing to a position the dispute hasn't resolved yet.
  - **`search_room_memory: "Let me think about that."`** — RATIONALE: read-only query tool that returns data the LLM uses to compose follow-up. The fallback fires when the LLM calls the tool but emits no streaming content. Same fallback as `search_memory` (line 381) preserves UX symmetry — the user shouldn't be able to tell from the fallback whether it was per-person or per-room search.
- **ORDERING INVARIANT inline comment:** same shape as D2 — names the position (AFTER D2) + cites spec.

### D4 — `_TOOL_HANDLERS` coverage + `INLINE_DISPATCHED_TOOLS` companion + startup assertion (Pass-2 surface)
- **Surface 1 (companion set):** `core/config.py:~520` — new `INLINE_DISPATCHED_TOOLS: frozenset[str] = frozenset({"search_web", "search_room_memory"})`. Rationale block names that these tools are consumed via inline ask_stream callbacks (`_make_memory_search_fn` / `_make_room_search_fn`), NOT through the `_execute_tool` dispatch table.
  - **Note:** `search_memory` is intentionally NOT in this set despite having a callback — it ALSO has a `_handle_search_memory` entry in `_TOOL_HANDLERS` (legacy dual-path from Session 56-58). Both paths are live; the registry assertion holds either way.
- **Surface 2 (assertion):** `pipeline.py:~6137-6145` — assertion immediately after D3. `assert set(brain.TOOLS_names) == set(_TOOL_HANDLERS) | INLINE_DISPATCHED_TOOLS`. Same two-shape error messaging as D2 (missing + orphan).
- **ORDERING INVARIANT inline comment:** same shape as D2/D3 — AFTER D3.
- **Why D4 isn't scope creep:** the auditor's §2.R2 precedent ("closing intent-gate gap while leaving fallback-gap open would be silent under-scoping") applies symmetrically. `_TOOL_HANDLERS` has the SAME coverage-drift class as `TOOL_INTENT_MAP` (intentional exclusions for callback-dispatched tools). Closing 3 of 4 registries while the 4th silently drifts would be the exact anti-pattern P0.S6 is meant to prevent. Phase 0 audit missed this surface because the audit's grep regex was tuned to dicts in `core/config.py`; `_TOOL_HANDLERS` lives in `pipeline.py` and Pass-2 grep surfaced it.

---

## §2. Auditor's 3 precision items — resolution

### P1 — D2 ORDERING INVARIANT inline comment (RESOLVED §1.D2)
The verbatim comment block at D2's call site mirrors P0.S3 §1.P3 shape + names BOTH ordering invariants (vs privilege assertion + vs env validation). D3 + D4 inline comments mirror the same shape with their respective ordering positions. Three new `ORDERING INVARIANT` anchors land in pipeline.py at adjacent positions; future grep for "ORDERING INVARIANT" finds all five (P0.S2 dashboard + P0.S3 env + P0.S6 intent-gate + P0.S6 fallback + P0.S6 handler).

### P2 — D3 fallback content adjudication (RESOLVED §1.D3)
Both fallback strings locked at Plan v1 with explicit rationale (Session 28 Issue A precedent for `report_identity_mismatch`; `search_memory` UX symmetry for `search_room_memory`). Developer does NOT make this call.

### P3 — D2 4th-registry tripwire AST shape lock
- **Test surface:** new `tests/test_p0_s6_intent_gates.py::test_no_undocumented_tool_registries_in_repo`.
- **AST-walk shape:**
  1. Parse `core/config.py` + `pipeline.py` modules.
  2. Walk for module-level `ast.AnnAssign` nodes where annotation is `dict[str, ...]` OR `frozenset[str]` OR `set[str]`.
  3. For each match, evaluate the RHS (if literal). If the keys / set members overlap with `brain.TOOLS` names by ≥1 entry → candidate registry.
  4. Apply **allowlist** for legitimate tool-name dicts that are NOT coverage registries (per auditor's P3 ask):
     - `_CONCURRENT_SAFE_TOOLS` at `pipeline.py:4387` — concurrency-dispatch allowlist (1 tool, intentionally narrow).
     - `HISTORY_OVERRIDE_TOOLS` at `core/config.py:1437` — history-rewrite allowlist (2 tools, intentionally narrow).
     - `_KNOWN_TOOL_NAMES` regex literal at `core/brain.py:20` — regex pattern string, NOT a set/dict; AST walk skips by type.
     - `TOOL_TIMEOUT_OVERRIDES` (if present) — per-tool budget map; rationale = "override-only allowlist, default = TOOL_TIMEOUT_SECS for any tool not in the override map."
  5. Any candidate registry NOT in the locked-registries list (`TOOL_PRIVILEGES`, `TOOL_INTENT_MAP`, `_TOOL_FALLBACKS`, `_TOOL_HANDLERS`) AND not in the allowlist → test fails with the registry name + suggested action (add coverage assertion OR add to allowlist with rationale).
- **Allowlist evolution discipline:** new entries to the allowlist require a rationale comment naming WHY the registry isn't a coverage surface (mirrors P0.S6-secrets `_ENV_VAR_ACCESS_ALLOWLIST` + P0.S5 D2 indirect-boundaries allowlist precedents).

---

## §3. Multi-direction invariant trace (per D-decision)

### D1
- **Forward:** consumers = D2 assertion (reads `INTENT_OPTIONAL_TOOLS`). No other consumers.
- **Backward:** none (this IS the producer of the new constant).
- **Sideways:** parallel writers — none. `TOOL_INTENT_MAP` is a sibling, not a competitor.
- **Lifecycle:** module import (load) → assertion check (verify) → reference at every `_execute_tool` call (but assertion already passed) → process exit (gone with module). No mutation; frozen-by-design.

### D2
- **Forward:** assertion failure aborts `pipeline.run()` BEFORE the event loop starts. Operator sees the hard-error message; no consumer downstream because the assertion is a launch-time gate.
- **Backward:** reads `brain.TOOLS` (producer = `core.brain` module) + `TOOL_INTENT_MAP` + `INTENT_OPTIONAL_TOOLS` (D1 product).
- **Sideways:** parallel writers to `brain.TOOLS` — none; `brain.TOOLS` is module-level frozen list. Parallel writers to `TOOL_INTENT_MAP` — none. Parallel writers to `INTENT_OPTIONAL_TOOLS` — none (frozenset).
- **Lifecycle:** runs ONCE at pipeline.run() entry, AFTER env validation + AFTER privilege assertion. Never mutates state.

### D3
- **Forward:** assertion failure aborts pipeline.run() before event loop. Runtime fallback consumer at `pipeline.py:5820` (`fb = _TOOL_FALLBACKS.get(tc["name"], "")`) gets a guaranteed non-empty entry for every tool the LLM might call.
- **Backward:** reads `brain.TOOLS` (`core.brain` producer) + `_TOOL_FALLBACKS` (pipeline.py:376 producer = this D3 row additions).
- **Sideways:** parallel writers — none. `_TOOL_FALLBACKS` is module-level dict; no mutation site exists in repo today (grep verified Pass-2).
- **Lifecycle:** assertion runs at pipeline.run() entry; consumer reads happen every tool dispatch.

### D4
- **Forward:** assertion failure aborts pipeline.run(). Runtime dispatch at `pipeline.py:4348` (`handler = _TOOL_HANDLERS.get(name)`) gets a guaranteed registered handler for non-inline-dispatched tools.
- **Backward:** reads `brain.TOOLS` + `_TOOL_HANDLERS` (pipeline.py:4191) + `INLINE_DISPATCHED_TOOLS` (new D4 product).
- **Sideways:** parallel writers — none. Module-level dict + frozenset.
- **Lifecycle:** assertion at pipeline.run() entry; consumer reads at every `_execute_tool` call.

---

## §4. Quality gate checklist (11 gates per strict-mode §4)

- **[APPLIES] Correctness** — invariants 4-axis-traced in §3 (above) for all 4 D-decisions.
- **[APPLIES] Security** — coverage-drift class IS the security surface. A tool dispatched without classifier gate verification IS the Detroit-class bug. P0.S6 is fundamentally a security spec. No new attack surface introduced; existing surface tightened.
- **[N/A — observability-only] Privacy** — tier classification for new facts/state? No new facts. `INTENT_OPTIONAL_TOOLS` + `INLINE_DISPATCHED_TOOLS` are config constants, not user-visible state.
- **[APPLIES] Performance** — all 3 new startup assertions run ONCE at pipeline.run() entry. Cost = 3 frozenset construction + 3 set-equality checks = ~microseconds. Worst-case latency = startup time + ~10ms. No hot-path impact.
- **[APPLIES] Observability** — assertion failures produce explicit hard-error messages naming BOTH gap shapes (missing + orphan) for each registry. Three new `ORDERING INVARIANT` comment anchors per P1. No log lines for pass case — silence is correct (mirrors TOOL_PRIVILEGES assertion).
- **[APPLIES] Test pyramid** —
  - Unit: D1 set-equality + frozen-type checks (3 tests).
  - AST: P3 forward-tripwire (1 test) + assertion-source-presence (3 tests).
  - Behavioral: induce missing-from-each-registry case + verify assertion fires (3-4 tests via monkeypatch on `brain.TOOLS_names`).
  - E2E: N/A (no integration scenario beyond pipeline.run() startup; covered structurally).
- **[APPLIES] Regression guards** — at least one deliberate-regression test per D-decision: (a) remove D1 entry → D2 assertion fires; (b) drop D2 assertion text → source-inspection fires; (c) remove D3 fallback row → D3 assertion fires; (d) remove D4 INLINE_DISPATCHED_TOOLS entry → D4 assertion fires. 4 regressions = 4 D-decisions.
- **[APPLIES] Pre-mortem** — 12 failure modes in Phase 0 §3 (above the 5-10 floor); §3.1-§3.4 specifically prevention-tuned at this Plan v1's surface.
- **[APPLIES] Multi-direction trace** — §3 above (forward/backward/sideways/lifecycle per D-decision).
- **[APPLIES] Backward compat** — no breaking changes. Additive: 2 new constants in config.py, 3 new assertion blocks in pipeline.py, 2 new fallback rows. Existing callers (`pipeline.py:6101` TOOL_PRIVILEGES assertion, `pipeline.py:5820` _TOOL_FALLBACKS reader, `pipeline.py:4348` _TOOL_HANDLERS reader) unchanged.
- **[APPLIES] Doc updates** — closure narrative goes to:
  - `CLAUDE.md` header — P0.S6 closure block + suite count update.
  - Parent `complete-plan.md:625` — status flip `[OPEN]` → `[CLOSED]` + closure note pointing to subdir.
  - Subdir `complete-plan.md` — full P0.S6 closure narrative entry.
  - `to_be_checked.md` — coverage matrix row + verbatim closure entry per deferred-canary discipline.
  - `feedback_auditor_q5_estimates_trail_grep.md` — 11th banked closure.
  - `feedback_strict_industry_standard_mode.md` — 20th-23rd consecutive application track-record entry (Phase 0 + v1 + closure + Phase 1-5 = 4 artifacts assuming v2 cycle).

---

## §5. Cross-spec impact analysis

- **P0.S3:** ORDERING INVARIANT anchor pattern reused (P1). P0.S3's env-validation block at `pipeline.py:6078-6093` stays unchanged; P0.S6's three assertion blocks add new anchors in adjacent positions. No P0.S3 invariant impacted.
- **P0.S2:** dashboard-token block at `pipeline.py:~6065-6077` is BEFORE env validation per P0.S2/P0.S3 ordering. P0.S6 assertions run AFTER env validation. No P0.S2 invariant impacted.
- **P0.S5:** wrap_user_input is in the LLM-call construction surface (`core/brain.py`); P0.S6 is in the registry/startup-assertion surface (`core/config.py` + `pipeline.py`). No code-line overlap.
- **P0.10 / P0.S7 family:** routing reconciler + cross-person privacy live in `pipeline.py` + `core/reconciler.py` + `core/brain_agent.py`. P0.S6's pipeline.py touches are at lines ~6107-6145 (new) and lines 376-382 (additive rows). No P0.10 invariant or P0.S7 invariant impacted.
- **P1.A* (future architectural):** layering invariant test at `tests/test_layering_invariants.py` doesn't flag config.py reads from pipeline.py (allowed boundary). D1 + D4 add new imports in pipeline.py from config.py; no new forbidden access introduced.

---

## §6. Forecast: test count + Plan-version cadence

### Test count (Q5 forecast band)
**~15-18 logical anchors mid-range, 12-21 outer range:**

- D1 (3): `INTENT_OPTIONAL_TOOLS` exists, content locked (3 entries), is frozenset type.
- D2 (5): assertion present at correct position, ORDERING INVARIANT comment present, fires on missing tool, fires on orphan tool, accepts valid union.
- D3 (5): both new fallback rows present, fallback content locked verbatim, assertion present, fires on missing entry, fires on whitespace-only value, ORDERING INVARIANT comment present.
- D4 (4): `INLINE_DISPATCHED_TOOLS` exists + locked content, assertion present + fires on missing handler, ORDERING INVARIANT comment present.
- Cross-cutting (2): P3 4th-registry AST tripwire (with allowlist enforcement) + Phase 4 closure-narrative bundle of 4 deliberate-regression confirmations.

Mid-range total = 19. Auditor original Phase 0 estimate was 13 mid-range; Plan v1 D4 addition pushes mid to 19 (auditor-flagged D4 emergence as Pass-2 finding; +6 anchors expected for the 4th D-decision). Under re-baselined mid-range methodology, ±15% = 16-22 ON-TARGET; trajectory at +46% vs Phase 0 mid-range = SLIGHT-DRIFT-toward-overshoot is the prediction, but this isn't the Q5 trajectory measurement (that's closure vs Plan v1 mid).

### Plan-version cadence prediction
- **Initial Phase 0 prediction:** medium-D + LOW fan-out (~21 cells) → v1 → v2 floor.
- **Plan v1 refinement:** 4 D-decisions + ~28 cells (4 registries × 7 tools) — still LOW fan-out per `feedback_plan_version_cadence_multi_axis.md` (≤20 cells threshold loosely defined; 28 is borderline). Sub-rule §8 governs by complexity, NOT by ritual.
- **Best estimate:** still v2 floor. D4 emergence is a clean addition, not architectural complexity bloom. If Plan v1 auditor review surfaces real precision items → Plan v2 absorbs. If 0 precision items → OPTIONAL-Plan-v2 path (per §8 sub-rule + P0.S3 precedent).

---

## §7. Banked dispositions for auditor v1 review

- **Sub-pattern A `### Phase-0-catches-wrong-premise`: STAYS at 6** (correction from audit §2.R3 off-by-one; reconciled in §0 above). P0.S6 is partial-truth premise (privilege half closed, intent+fallback+handler half open) — premise correct-in-spirit; no bump.
- **`### Phase-0-granular-decomposition-enables-accurate-estimates`: STAYS at 7 supporting** (closure-conditional bump to 8 if P0.S6 lands ON-TARGET under re-baselined mid-range methodology).
- **`### Spec-first review cycle for multi-day specs`: 29 → 30 at Phase 0 + 31 at Plan v1 close.**
- **Strict-industry-standard mode: 19 → 20 consecutive applications + 6 successful closures (in flight to 7 at P0.S6 close).**
- **Deferred-canary strategy: 5 → 6th application in-flight.**
- **Q5-B trajectory under re-baselined methodology:** P0.S3 +12.5% → P0.S4 0% → P0.S5 +22.2% → P0.S6 in-flight (currently Plan v1 forecast 19 mid vs Phase 0 13 mid = drift INTERNAL to spec scope from D4 emergence, NOT Q5 trajectory). **Symmetric-over-estimate watch:** stays in abeyance; P0.S6 closure-vs-Plan-v1-mid is the actual reading.
- **Twin-filename pitfall: 4th successful prevention** (audit filename `p0_s6_intent_gates_audit.md` + Plan v1 filename `p0_s6_intent_gates_plan_v1.md` disambiguate against the closed P0.S6-secrets artifacts).
- **Discipline-count-bump-needs-explicit-justification sub-rule: 4 banked instances at Plan v1 drafting** (P0.S1 + P0.S3 + P0.S4 ×2 + P0.S5 + P0.S6 §0 reconciliation). 4th preventive instance.
- **4-layer grep-verification review: 2nd in-flight instance** (P0.S6 Pass-2 architect grep surfaced D4; same shape as P0.S5 Pass-3 developer grep + Pass-4 classification swap).

---

## §8. Open questions for auditor (3)

**Q1.** D4 scope inclusion: Pass-2 grep at Plan v1 drafting surfaced `_TOOL_HANDLERS` registry. Architect's lean = INCLUDE under strict-mode §1 same-cycle-close discipline (same shape as Phase 0's D3 inclusion). If auditor disagrees, D4 splits to P0.S6.1 follow-up with the same trigger conditions as the security track.

**Q2.** D4 `INLINE_DISPATCHED_TOOLS` naming: chose this over alternatives like `CALLBACK_DISPATCHED_TOOLS` or `INLINE_TOOLS` to convey "dispatched inline in the ask_stream loop, NOT through _execute_tool." If auditor prefers different naming for clarity, lock at Plan v1 close.

**Q3.** P3 AST-walk allowlist completeness: §2.P3 lists 4 known allowlist entries (`_CONCURRENT_SAFE_TOOLS`, `HISTORY_OVERRIDE_TOOLS`, `_KNOWN_TOOL_NAMES`, `TOOL_TIMEOUT_OVERRIDES`). Pass-2 grep may have missed additional tool-name dicts in test files / harness scripts. Plan v2 (if needed) absorbs auditor's exhaustive sweep; OR developer Pass-3 catches at implementation entry.

---

**End of Plan v1.** Ready to forward to auditor for v1 review.
