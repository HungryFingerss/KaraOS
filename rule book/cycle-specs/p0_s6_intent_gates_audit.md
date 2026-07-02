# P0.S6 Phase 0 audit — Tools without intent gates

**Spec ID disambiguation:** P0.S6 in the **parent** `c:\Users\jagan\dog-ai\complete-plan.md` enumeration line 623 — "Tools without intent gates" `[OPEN]`. **NOT** the earlier "Secrets Management" cycle closed 2026-05-18 (whose artifacts live at `tests/p0_s6_audit.md` + `tests/p0_s6_plan_v1.md` + `tests/p0_s6_plan_v2.md` — a different P0.S6 from a prior P0.S* enumeration). Filename `p0_s6_intent_gates_audit.md` is intentionally distinct to avoid the twin-filename pitfall per strict-mode §9.

**Pre-audit premise (verbatim from parent complete-plan.md):**
> **Fix:** define `TOOL_INTENT_REQUIRED` map + `TOOL_INTENT_OPTIONAL` allowlist. Startup assertion: every tool in `brain.TOOLS` is in one set.

**Cadence prediction:** 3 D-decisions (medium D-count band) + ~21 grep-relevant cells (3 registries × 7 tools, LOW fan-out per `feedback_plan_version_cadence_multi_axis.md`) → predicted v1 → v2 floor. NOT predicted v3 (low fan-out doesn't trigger 4-layer review need).

---

## §1. Grep-verified architectural surface (Pass-1)

**3 tool registries identified across `core/config.py`, `core/brain.py`, `pipeline.py`:**

### Registry A — `TOOL_PRIVILEGES: dict[str, frozenset[str]]` (config.py:258-268)
- **Purpose:** maps each tool to the set of `person_type` values allowed to call it. Fail-closed: tools not in table are blocked.
- **Coverage:** 7/7 ✓ — all `brain.TOOLS` entries (update_person_name, update_system_name, search_web, shutdown, search_memory, search_room_memory, report_identity_mismatch) have a privilege row.
- **Startup assertion:** `pipeline.py:6099-6106` — `_missing = _tool_names - set(TOOL_PRIVILEGES); assert not _missing`. Fires at pipeline.run() entry. **CLOSED** (Session 61 Step 2).
- **Test mirror:** `test_pipeline.py:11559-11567`.

### Registry B — `TOOL_INTENT_MAP: dict[str, tuple[str, str|None]]` (config.py:500-519)
- **Purpose:** maps mutation tools to `(required_intent, arg_key)` for classifier-gate verification. The gate (`_intent_allows`) prevents Detroit-class hallucinations.
- **Coverage:** **4/7 — INTENTIONAL** ✓ (update_system_name / update_person_name / report_identity_mismatch / shutdown). The 3 search tools (search_web, search_memory, search_room_memory) are intentionally omitted because:
  - `search_web` — consumed inline inside `core.brain._ask_stream` BEFORE the tool_call reaches `conversation_turn`'s gate; tool_call never bubbles to the classifier code path. Deferred to Phase 1.5 per Session 79's audit (verbatim 15-line rationale comment at config.py:505-519).
  - `search_memory` — read-only query path with no privilege escalation; gate adds latency without security benefit.
  - `search_room_memory` — same shape as search_memory; gate would be cosmetic.
- **Startup assertion:** **MISSING** ✗ — no exhaustive check that `set(brain.TOOLS) == set(TOOL_INTENT_MAP) | INTENT_OPTIONAL_TOOLS` at pipeline.run() entry.
- **Test coverage:** `test_pipeline.py:1838-1858` asserts the 4 mutation tools ARE in the map AND search_web is NOT — but the 4-tool expected set is hardcoded. Adding a 5th mutation tool to brain.TOOLS without updating the test AND TOOL_INTENT_MAP would silently slip through (the subset check stays green).

### Registry C — `_TOOL_FALLBACKS: dict[str, str]` (pipeline.py:376-382)
- **Purpose:** spoken text emitted when LLM calls a tool but returns empty content. Comment line 375 says "Every tool MUST have a non-empty fallback to prevent silent turns."
- **Coverage:** **5/7 ✗** — `report_identity_mismatch` AND `search_room_memory` are MISSING. Their tool calls today would hit `_TOOL_FALLBACKS.get(name, "")` → empty string → silent turn (the exact anti-pattern the comment warns against).
- **Startup assertion:** **MISSING** ✗ — no exhaustive check.
- **Test coverage:** **NONE** ✗ — no test asserts coverage.
- **Blast radius:** silent turns when these two tools fire. `report_identity_mismatch` is uncommon (only fires on dispute-flip path); `search_room_memory` is Phase 3B.5-recent. The gap surfaced via Pass-1 grep at Phase 0 — exactly the kind of registry-drift the P0.S6 fix is meant to close.

---

## §2. Pre-audit premise check

**Parent complete-plan.md premise:** "define `TOOL_INTENT_REQUIRED` map + `TOOL_INTENT_OPTIONAL` allowlist. Startup assertion: every tool in `brain.TOOLS` is in one set."

**Grep-verified verdict: PARTIAL-TRUTH ON-TARGET** for the intent-half of the premise. The privilege-half is already closed (Session 61). The intent-half gap is real and matches the premise's framing precisely.

**Premise refinements adopted:**
- **R1:** `TOOL_INTENT_REQUIRED` is an unnecessary rename — the existing `TOOL_INTENT_MAP` already plays this role. Keep the name; introduce `TOOL_INTENT_OPTIONAL` as the companion frozenset.
- **R2:** P0.S6 scope EXTENDS to `_TOOL_FALLBACKS` registry (surfaced during Phase 0). Closing the intent-gate registry gap while leaving the fallback registry gap open would be silent under-scoping. Same-cycle close per strict-mode §1.
- **R3:** Sub-pattern A (`### Phase-0-catches-wrong-premise`) does NOT apply. The premise's CORE — intent-gate gap — was correct. The half-truth ("Tools without intent gates" implies BOTH privilege + intent gates lack registry coverage when only intent + fallback do) is a framing imprecision, not a wrong-premise catch. Doctrine count stays at 7.

---

## §3. Pre-mortem (12 failure modes — strict-mode floor 5-10)

### §3.1 — D1 `TOOL_INTENT_OPTIONAL` naming collision with `TOOL_INTENT_MAP`
**Risk:** introducing a `TOOL_INTENT_OPTIONAL` frozenset adjacent to `TOOL_INTENT_MAP` could read as "the optional half of TOOL_INTENT_MAP" rather than "the complement set." Future readers might add `(intent, arg_key)` tuples to TOOL_INTENT_OPTIONAL by analogy.
**Mitigation:** name it `INTENT_OPTIONAL_TOOLS: frozenset[str]` (subject-noun-first, plural) so the shape signals "set of tool names" not "map of tool→intent." Docstring naming both the contrast AND the rationale comment template.

### §3.2 — D2 startup assertion timing
**Risk:** the existing TOOL_PRIVILEGES assertion at `pipeline.py:6099-6106` runs at `pipeline.run()` entry. Adding the intent assertion adjacent is the natural position — but if it fires in the wrong order (before privilege check, before env validation) and an env var or config import side-effect makes config.py raise, the user sees the intent assertion's stack trace instead of the env-var error.
**Mitigation:** lock ordering invariant at the call site (per P0.S3 §1.P3 precedent). Intent assertion goes AFTER privilege assertion. Comment block names BOTH ordering rules: AFTER env_validation + AFTER privilege assertion (so privilege misconfig surfaces first; intent assertion is the secondary check).

### §3.3 — D3 fallback assertion vs cosmetic-string surface
**Risk:** `_TOOL_FALLBACKS` values are user-facing SPOKEN TEXT. Enforcing non-empty assertion at startup catches missing rows, but doesn't catch DEGENERATE rows (e.g., `"."` or `" "` or `"\n"`). A test could enforce min-length floor (>= 3 chars or matches `[A-Za-z]`).
**Mitigation:** D3 implementation = non-empty + non-whitespace assertion: `assert v.strip()`. Don't over-engineer (no semantic check). Closure test covers structural correctness, NOT prose quality.

### §3.4 — D3 cross-registry symmetry: TOOL_PRIVILEGES has assertion, TOOL_INTENT_MAP gets one, _TOOL_FALLBACKS gets one — but is there a 4th registry I'm missing?
**Risk:** if a future code path adds a 4th tool registry (e.g., `_TOOL_CONCURRENCY_TIMEOUTS: dict[str, float]` or per-tool retry counts), the same coverage-gap class re-emerges. P0.S6 closes 3 registries; the 4th would slip through.
**Mitigation:** Phase 0 §1 exhaustively grepped for tool-registry dicts (`grep -E "(?:_TOOL|TOOL)_[A-Z]+:?\s*(dict|frozenset|set)"`). The 3 registries enumerated are exhaustive at Pass-1. Plan v1 §4 will add a structural test `test_no_undocumented_tool_registries_in_repo` that AST-walks `core/config.py` + `pipeline.py` for module-level `dict[str, ...]`/`frozenset[str]` annotations whose keys overlap with brain.TOOLS — a forward tripwire against future drift.

### §3.5 — D2 startup assertion message clarity
**Risk:** the existing TOOL_PRIVILEGES assertion message names ONE gap ("missing from TOOL_PRIVILEGES"). The intent-assertion needs to distinguish TWO gap shapes: (a) tool in TOOLS but not in TOOL_INTENT_MAP ∪ INTENT_OPTIONAL_TOOLS, (b) tool in TOOL_INTENT_MAP but no longer in TOOLS (orphan).
**Mitigation:** assertion message enumerates BOTH shapes verbatim per failure mode. P0.S2 D5 hard-error precedent for naming the threat + the fix.

### §3.6 — D1+D2 backward-compat: existing code paths read TOOL_INTENT_MAP
**Risk:** there are 2 known consumers of TOOL_INTENT_MAP — `pipeline._execute_tool` at line ~4380 (intent_sidecar gate dispatch) and `test_pipeline.py:1847` (existing structural test). Introducing INTENT_OPTIONAL_TOOLS adjacent SHOULDN'T touch these consumers; the assertion is additive.
**Mitigation:** Pass-2 grep at Plan v1 will enumerate ALL consumers of TOOL_INTENT_MAP to confirm no rename collision. If a consumer needs both sets, expose a `TOOL_INTENT_KNOWN_NAMES: frozenset[str] = set(TOOL_INTENT_MAP) | INTENT_OPTIONAL_TOOLS` computed constant.

### §3.7 — D3 fallback registry membership: should search tools have fallbacks?
**Risk:** search_memory / search_room_memory return data, not actions. Their tool result is what the LLM uses to compose its response. If the LLM emits zero text BUT successfully called search_memory, what's the "fallback"? "Let me think about that" (current search_memory fallback) is fine — but for search_room_memory, the same fallback applies. report_identity_mismatch's correct fallback is something like "Got it." or empty (the dispute-handler logs + UI shows the dispute state).
**Mitigation:** D3 fallback strings — pick at Plan v1 drafting. search_room_memory → "Let me think about that." (same as search_memory). report_identity_mismatch → "Understood." (matches the dispute-acknowledgment shape). Plan v1 §3 documents both rationales.

### §3.8 — Coverage of LLM-hallucinated tool names
**Risk:** the existing `_execute_tool` Layer 0 filter at `pipeline.py:4257` blocks unknown tool names BEFORE dispatch (Bug P fix, Session 70). So if a future tool name appears in brain.TOOLS but NOT TOOL_INTENT_MAP ∪ INTENT_OPTIONAL_TOOLS, the startup assertion catches it. If the LLM hallucinates a tool name that's nowhere, Layer 0 catches it at runtime. Both gates work in tandem.
**Mitigation:** no action needed; this is correct behavior. Document the dual-gate at Plan v1 §1 closure narrative.

### §3.9 — Test-only enforcement vs production-only enforcement
**Risk:** the TOOL_PRIVILEGES assertion is BOTH a pytest test (test_pipeline.py:11559) AND a startup runtime check (pipeline.py:6099). Asymmetric coverage (test-only) would let production launch with a missing entry until CI catches it. P0.S6 must keep symmetric coverage.
**Mitigation:** D2 assertion goes in BOTH surfaces: production runtime at pipeline.run() entry + pytest test in test_pipeline.py. D3 same shape (runtime + pytest).

### §3.10 — Plan v3-floor risk (4-layer review)
**Risk:** P0.S5 (high fan-out, 29 sites) needed Plan v3 with Pass-3 + Pass-4 catches. P0.S6 has LOW fan-out (~21 cells). Per `feedback_plan_version_cadence_multi_axis.md`, this predicts v2 floor.
**Mitigation:** explicit prediction at Phase 0 audit; if Pass-2 (auditor review) surfaces residual scope or Pass-3 (developer Phase 2 entry) surfaces missing sites, plan absorbs into v3. The 4-layer discipline holds even if low-fan-out predicts v2.

### §3.11 — Cross-spec impact analysis
**Risk:** P0.S6's changes touch (a) `core/config.py` — additive new constant + verbatim rationale comment, (b) `pipeline.py:6099-6106` — additive new assertion block, (c) `pipeline.py:376-382` — additive 2 new fallback rows. No invariant tests in `test_p10_*` / `test_p0_s*_*` should be affected. No P1.A* layering implications (this is core/config + pipeline, both already permitted boundary surfaces).
**Mitigation:** Plan v1 §6 cross-spec impact analysis enumerates the 3 surfaces touched + confirms no cross-spec invariant impacts.

### §3.12 — Pass-N grep-verification fatigue (P0.S5 precedent)
**Risk:** even at LOW fan-out, multi-pass grep at each layer can still surface residual cases. P0.S5 Plan v3's "convergence point" claim was falsified by Pass-4 classification swap. P0.S6 should NOT make the same claim prematurely.
**Mitigation:** Plan v1 §1 will commit to Pass-1 enumeration as architect's BEST-EFFORT exhaustive at drafting time. Auditor Pass-2 + developer Pass-3 + developer Pass-4 are EXPECTED. Convergence is claimed only at closure, not at Plan v1.

---

## §4. D-decisions (3 decisions, all single-file surfaces)

### D1 — `INTENT_OPTIONAL_TOOLS` companion set in `core/config.py`
**Surface:** `core/config.py:498-519` (immediately adjacent to TOOL_INTENT_MAP).
**Contract:** new module-level `INTENT_OPTIONAL_TOOLS: frozenset[str]` containing 3 search-family tool names. Verbatim rationale comment naming WHY each is intent-optional (search_web inline-consumed, search_memory read-only, search_room_memory same shape). The existing 15-line search_web deferral comment becomes the canonical text for the search_web entry.

### D2 — Exhaustive intent-gate registry startup assertion in `pipeline.py`
**Surface:** `pipeline.py:6107-6113` (immediately after TOOL_PRIVILEGES assertion).
**Contract:** `assert set(brain.TOOLS_names) == set(TOOL_INTENT_MAP) | INTENT_OPTIONAL_TOOLS`. ORDERING INVARIANT comment block: AFTER env_validation + AFTER privilege assertion. Hard-error message names BOTH gap shapes (missing + orphan).

### D3 — `_TOOL_FALLBACKS` registry coverage + startup assertion
**Surface:** `pipeline.py:376-382` (registry entries) + `pipeline.py:~6114-6120` (assertion adjacent to D2).
**Contract:** add `report_identity_mismatch: "Understood."` + `search_room_memory: "Let me think about that."` rows. Exhaustive startup assertion: every brain.TOOLS name has a non-empty stripped fallback string. Hard-error message names tool missing AND ordering invariant (AFTER D2).

---

## §5. Forecast: Plan v1 test count

**~13 logical anchors** (mid-range estimate, ±3 acceptable):

- D1 (3): INTENT_OPTIONAL_TOOLS exists with locked content (3-entry assertion) + structural type-check (frozenset) + rationale comment present.
- D2 (4): startup assertion present at correct ordering position + hard-error message names both gap shapes + asserts equality of brain.TOOLS to union set + pytest mirror.
- D3 (4): both new fallback rows present + non-empty assertion + ordering invariant comment + pytest mirror.
- Cross-cutting (2): no-undocumented-registries AST scan (§3.4 forward tripwire) + Phase 4 closure: 3 deliberate-regression confirmations (remove D1 entry / drop D2 / strip D3 row) all fire correctly.

Predicted total collected: ~15-18 (light parametrize on fallback row coverage). Q5 forecast band: 12-15 mid-range, 9-18 outer range.

---

## §6. Out of scope (banked for follow-up specs if triggered)

- **search_web intent-gate re-evaluation** — deferred to Phase 1.5 per the existing 15-line comment in config.py:505-519. P0.S6 does NOT touch this deferral; it merely enumerates search_web in INTENT_OPTIONAL_TOOLS with the same deferral rationale visible at the consumer registry instead of buried in config.py.
- **Tool-deprecation lifecycle** — set_language was removed in Session 61 Step 2 with a comment marker. Similar future removals (e.g., search_web if Phase 1.5 retires it) would need a banked migration path; out of P0.S6 scope.
- **Cross-spec tool-state observability** — Phase 5 evals + intent_divergences telemetry already cover this; P0.S6 closes the structural registry gap, NOT the telemetry surface.

---

## §7. Banked dispositions for Plan v1 review

- **Sub-pattern A (`### Phase-0-catches-wrong-premise`) doctrine: STAYS at 7 instances.** Premise was partial-truth (privilege half closed, intent half open) — not a wrong-premise catch.
- **`### Phase-0-granular-decomposition-enables-accurate-estimates` doctrine: 7 supporting + 3 contrary instances.** P0.S6 decomposed at Phase 0 into 3 D-decisions with named edit sites at `core/X.py:LINE` granularity. Continued supporting evidence (candidate 8th supporting instance at closure if Q5 within ±15% of mid-range under re-baselined methodology).
- **`### Spec-first review cycle` doctrine: 29 → 30-for-30 at Phase 0 close.** Routine application.
- **Strict-industry-standard mode: 19 → 20th consecutive application.**
- **Deferred-canary 5 → 6th in-flight application.**
- **Q5-B trajectory: P0.S3 +12.5% → P0.S4 0% → P0.S5 +22.2% — watch P0.S6 evidence.** Symmetric-over-estimate watch tentative rename stays in abeyance.
- **Twin-filename pitfall: 3rd preventive instance** — audit filename disambiguated upfront at the audit header to prevent future maintainer confusion with the earlier closed P0.S6 (Secrets Management).

---

## §8. Banked open question for auditor

**Q1.** D3 expanded scope: the pre-audit premise framed P0.S6 narrowly as "intent gates." Expanding to `_TOOL_FALLBACKS` is justified under strict-mode §1 (same-cycle close of surfaced gap), but it grows the spec. Architect's lean: KEEP D3 in scope — the registry-drift class is identical to D2; closing 2 of 3 registries while the 3rd silently keeps drifting would be the exact anti-pattern P0.S6 is meant to prevent. If auditor disagrees on scope expansion, D3 splits to a P0.S6.1 follow-up with same trigger conditions as the rest of the security track.

---

**End of Phase 0 audit.** Ready to forward to auditor for Phase 0 review → Plan v1.
