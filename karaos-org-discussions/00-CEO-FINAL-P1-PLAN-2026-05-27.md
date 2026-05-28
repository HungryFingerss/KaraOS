# KaraOS — CEO Final P1 Prep Plan & Industry Standard Directive (Discipline-Aligned) — 2026-05-27

**Author:** KaraOS-CEO
**Issue:** KAR-126
**Status:** Synthesis of 7 Wave-1 analyst reports + 15-doctrine discipline framework + strategic goal lock-in.
**Strategic goal (locked, non-negotiable):** "KaraOS should be a universal system that enables users to control ROS 2 robots. Every ROS 2 robot should use only our system. This system should be that capable."
**Reading order:** Sections 1 → 11 in order. Section 11 (CEO Final Directive) is the bottom-line.

---

## SECTION 1: EXECUTIVE SUMMARY

**The state of KaraOS at end of P0.R15.** KaraOS is a production-grade, single-user social-AI cognitive runtime with extraordinary engineering discipline at the correctness layer: 2810 passing tests, 15 elevated architectural doctrines, the 14-cycle P0.R resilience-track arc CLOSED, 28+ AST-enforced structural invariants, P0.S10 (the 6-artifact deepest-absorption cycle in project history) shipped clean. Five persistent memory surfaces (FAISS, brain.db, Kuzu, voice gallery, classifier-graph DB) have cross-storage atomicity sealed by sentinel + boot reconciliation. The 4-tier privacy model with `_visibility_clause` SQL composer is end-to-end isolated. The pure-graph intent classifier with Wilson lower-bound aggregation runs LLM-free in the hot path. This is the best household-companion cognition layer that exists in 2026 open-source.

**The gap between current state and the strategic goal.** "Every ROS 2 robot should use only our system" requires the system to BE a Layer D middleware (cognition above motor control), to PUBLISH the Adapter SDK as a separable package, to HOLD an Apache 2.0 license, to PASS a conformance suite, to RUN on a real robot (TurtleBot4 reference, Unitree G1 later), to EXPOSE an MCP server endpoint, and to GOVERN through a charter with multi-org legitimacy. Today: zero ROS 2 integration, zero adapter, zero external users, zero partners, zero published license, zero foundation. The cognitive substrate is real and disciplined. The robotics product is not yet code. Pipeline.py is 8000 lines but that is NOT the gating constraint — the gating constraint is that there is no embodied runtime, no commitment store, no scheduler, no verifier registry, no published contract.

**The P1 cycle's role in closing that gap.** P1's job is NOT to refactor pipeline.py. P1's job is to LAND THE STANDARD-FORMATION PREREQUISITES while pipeline.py stays mostly intact. The strategic clock is 8-10 weeks before ROSClaw v0.2, NVIDIA Isaac Orchestrate, or an MCP-for-robots wave forecloses our Layer D position. Build the embodied runtime (commitment store + scheduler + policy + verifier + mock adapter + TurtleBot4 reference + MCP server endpoint) in P1. Decompose pipeline.py as P2 hygiene running in parallel slices, NOT as a blocking prerequisite. Per Elon's first-principles read (Attack 3) and `future-execution.md` §4.3, the embodied runtime touches `pipeline.py` at exactly ONE line: `maybe_handle_embodied_command()`. The 483 KB pipeline.py is real debt but does not gate the universal-robot claim.

**How the existing discipline framework shaped this synthesis.** Every Wave-1 recommendation was cross-checked against the 15 elevated doctrines + 14-gate checklist + 3-part Pass-2 grep + spec-first review cycle. Where Wave-1 reports proposed mechanism changes, the discipline framework was treated as authoritative. The 7 analysts wrote without the discipline framework in context; my synthesis enforces it. Specifically: (a) Elon's "defer pipeline.py decomposition" was cross-checked against doctrine #6 (Phase-0 granular decomposition) and doctrine #14 (Spec-contracts-not-implementations) — no conflict, the doctrines prescribe HOW to decompose, not WHEN. (b) TechAnalyst-1's MF4 (Phase-0 audit before P1.A1-A3 code) is doctrine #4 (Phase-0-catches-wrong-premise) applied — but P1 is reframed so P1.A1-A3 lands AFTER Phase 4 demo. (c) Skeptic-1's BUG-2 (assert-under-O) becomes doctrine-#1-induction-protocol-enforced AST invariant. (d) Skeptic-2's governance gaps map to a brand-new operational discipline (License + Charter as Pre-P1 deliverable) that the existing 15 doctrines did NOT cover.

**Top 5 highest-impact recommendations (one line each, ordered by urgency).**
1. **Ship Pre-P1 must-fix MF1 (CI scaffold) + MF6 (Apache 2.0 license + GOVERNANCE.md charter) in the next 7 days.** Without these, every P1 deliverable is invisible to partners and every elevated doctrine is dead weight on the social layer.
2. **Reframe P1 around embodied runtime, NOT pipeline.py decomposition.** Build `core/embodied/` (commitment store + scheduler + policy + verifier + mock adapter + TurtleBot4 reference + MCP server) in 8-10 weeks. Pipeline.py decomposition becomes P2.
3. **Publish `karaos-adapter-sdk` v0.1 + Capability Ontology v1.0 at END of P1, NOT Phase 7.** Spec-first sequencing per Sundar §2.5; Decision 3.9 in `future-execution.md` ships the SDK 6 months late.
4. **Land Pre-P1 bug census fixes (BUG-1 time.monotonic, BUG-2 assert→raise, BUG-3 _log_drain observability) before any P1 code.** Skeptic-1's catalog cleans up 14 latent CRITICAL+HIGH issues in 1 week.
5. **Adopt agent consolidation under `KARAOS_PROFILE = {companion, robotics, both}` config gate before adding any new embodied agent.** TechAnalyst-2's §2.3 prevents companion-agent overhead from dragging every P1 cycle.

---

## SECTION 2: DISCIPLINE-FRAMEWORK CROSS-REFERENCE

For each of the 15 elevated CLAUDE.md doctrines, I state how it governs P1 and which Wave-1 reports respected vs missed it.

### Doctrine 1: Induction-surfaces-invariant-gaps (7-for-7)
- **Applies to P1 because:** every new embodied invariant (commitment store atomicity, verifier abstention contract, adapter conformance) MUST ship with a deliberate-regression check before sign-off.
- **P1 enforcement:** every new `core/embodied/*` invariant test (e.g. `test_no_llm_can_invoke_adapter_without_policy_check`, `test_durable_commitment_survives_restart`, `test_verifier_disagreement_yields_failed_verification`) ships with a 3+ regression-confirmation cycle. The Phase 4 closure narrative MUST document each induced regression + revert.
- **Wave 1 alignment:** Sam §3 explicitly extends this to embodied eval ("the bench is the contract"). Skeptic-1 BUG-1/BUG-2 caught by this discipline if applied. TechAnalyst-1's B-H1 IdentityClaim.confidence_is_no_signal needs the AST invariant `test_reconciler_no_exact_equality_against_claim_confidence` to satisfy the doctrine. No conflicts.

### Doctrine 2: Architect-reads-production-code-before-sign-off (27 instances)
- **Applies to P1 because:** P1 will introduce ≥30 new files across `core/embodied/`, `karaos-adapter-sdk/`, `cognition/specs/v0/`. Closure-narrative drift is structurally guaranteed at this scale.
- **P1 enforcement:** Path C grep-verify at every embodied-spec closure-audit. Cross-path memory-file discipline (MEMORY.md at both paths) applies. STALE-CACHED-VERIFICATION bidirectional discipline (PowerShell fresh-disk read for `to_be_checked.md`) applies to every canary commitment.
- **Wave 1 alignment:** All 7 analysts implicitly assume this; TechAnalyst-2 §7.3 (memory event-sourcing) and Sam §3.4 (`intent_divergences` extension for actions) both rely on architect grep-verify at closure. No conflicts.

### Doctrine 3: Twin-filename-pitfall-prevention (6 instances)
- **Applies to P1 because:** `karaos-adapter-sdk/` lives outside `core/` (separately published package per Decision 3.3). Same filename across packages is a real risk (e.g. `core/embodied/commitment.py` vs `karaos-adapter-sdk/karaos_adapter_sdk/commitment_stub.py`).
- **P1 enforcement:** every P1 sub-PR creating files in BOTH packages must use distinguishing suffix at creation time. Closure pre-flight checklist extended to cross-package status flips.
- **Wave 1 alignment:** No analyst flagged this — they each scoped to one layer. Doctrine extension is mine.

### Doctrine 4: Phase-0-catches-wrong-premise (13 instances, threshold-crossed at P0.S7.D-D)
- **Applies to P1 because:** the strategic premise that "we need to decompose pipeline.py first" is itself a wrong premise that Phase 0 of P1 must test.
- **P1 enforcement:** P1's Phase 0 audit MUST grep-verify the dependency direction (does `core/embodied/` truly only touch pipeline.py at ONE line?). Per Elon Attack 3, yes — but the audit MUST confirm via grep, not assumption.
- **Wave 1 alignment:** TechAnalyst-1 §4.4 (MF4 — Phase-0 audit on decomposition shape) is the doctrine applied. Elon §3 reframes the premise itself (decomposition is real but not THIS-quarter's work). I rule Elon's reframing as the correct application of doctrine #4 — the wrong-premise IS "decomposition gates embodied," not "decomposition is needed."

### Doctrine 5: Verification-before-completion
- **Applies to P1 because:** P1's deliverables include external-facing artifacts (Apache 2.0 LICENSE, GOVERNANCE.md, `karaos-adapter-sdk/` PyPI release). Each ships only after explicit grep + manual review + external test.
- **P1 enforcement:** `karaos-adapter-sdk` v0.1 publishes only after `pip install karaos-adapter-sdk` works in a fresh venv from a colleague's machine. No "I tested it locally" claims.
- **Wave 1 alignment:** Sam §3.3 (embodied eval bench) is verification-before-completion applied to P1's action layer. No conflicts.

### Doctrine 6: Phase-0-granular-decomposition-enables-accurate-estimates (9 supporting + 6-consecutive-0%-streak sub-rule RATIFIED)
- **Applies to P1 because:** P1 has 8+ sub-deliverables. Each MUST decompose to `core/embodied/X.py:LINE` granularity at Phase 0, not aggregate "embodied runtime."
- **P1 enforcement:** Phase 0 audit for each P1.* sub-PR lists D-decisions with named edit sites. Auditor Q5 estimate MUST be ON-TARGET (within ±15%) on at least 70% of P1 sub-cycles to preserve the 6-consecutive-0% streak.
- **Wave 1 alignment:** Sam §8 (embodied eval bench specifics) and TechAnalyst-2 §7 (5 Pre-P1 items with file:line) both demonstrate granular Phase 0. Sundar's §3 (license + DCO) lacks file granularity but is non-code (decision artifacts).

### Doctrine 7: Grep-baseline-before-drafting (6 instances)
- **Applies to P1 because:** every P1 closure narrative grep-verifies prior discipline counts against the source-of-truth files. Stale-copy drift compounds fast.
- **P1 enforcement:** unchanged from P0.B3+. Every closure-narrative draft starts with a fresh grep on `CLAUDE.md`, parent `complete-plan.md`, and the relevant memory files.
- **Wave 1 alignment:** All 7 analysts cite this through their existence (they grep-verified each claim against file:line). No conflicts.

### Doctrine 8: Zero-precision-items-at-auditor-review (38 instances + OPTIONAL-Plan-v2 sub-rule with 18 proof cases)
- **Applies to P1 because:** P1 sub-PRs with clean Plan v1 (0 PIs) ship at v1 directly (OPTIONAL-Plan-v2 path); only the absorbed sub-PRs escalate to Plan v2+. Saves 30-50% of cycle time vs P0 cycles.
- **P1 enforcement:** every P1 sub-PR's architect drafts Plan v1 with pre-emptive precision-item absorption (multi-pattern Pass-2 grep + closure-template lock + AST tripwire shape + cross-spec impact + Q5 band-table + explicit open questions with architect leans). Target: ≥70% of P1 sub-PRs hit OPTIONAL-Plan-v2.
- **Wave 1 alignment:** No direct conflict; this is internal discipline. Skeptic-2's "Pass-2 deferral pattern is RED FLAG" memory observation reinforces it.

### Doctrine 9: Canary-surfaces-real-gaps (5 instances + ratified)
- **Applies to P1 because:** P1 introduces embodied actions on real robot hardware (TurtleBot4 in sim at end of P1; Unitree G1 in P3). Canary findings will be REAL architectural findings, not noise.
- **P1 enforcement:** every P1 sub-PR adds a canary entry to `to_be_checked.md` per the Plan v1 §6 template. Post-P1 canary week (1 week dedicated, no live canaries during P1 itself) validates the full bundle.
- **Wave 1 alignment:** Skeptic-1 §8 (canary week extensions for memory-leak, NTP correction, GPU OOM, thread pool exhaustion, python -O) is the doctrine extended. Sam §3.3 (embodied eval bench) is canary discipline elevated to eval discipline.

### Doctrine 10: Pass-2-grep-auditor-verified-before-Plan-v1-approval (5 applications)
- **Applies to P1 because:** P1 sub-PRs introduce typed contracts (`cognition/specs/v0/`). Auditor's Pass-2 grep at Plan v1 review MUST enumerate every new file inventory + every new dataclass + every new schema reference.
- **P1 enforcement:** 3-part Pass-2 grep extension (symbol-name-uniqueness + behavioral-semantic + symmetric-reject-preserve-class) applies to every P1 Plan v1 and every absorption Plan v2+. Locked at P0.S10 Phase 4 onward.
- **Wave 1 alignment:** TechAnalyst-1 §6.3 #9 explicitly cites this discipline. No conflicts.

### Doctrine 11: Pre-audit-quantifier-precision-refined-by-grep (10 instances + 8-axis sub-shape taxonomy)
- **Applies to P1 because:** every P1 pre-audit framing (e.g. "ship commitment store + scheduler in 3 weeks") will be quantifier-precision-approximate. Phase 0 grep refines to precise per-file edit-site counts.
- **P1 enforcement:** sub-shape taxonomy may grow (e.g. new ROBOT-ADAPTER-INTEGRATION-AXIS) as P1 cycles surface novel quantifier failure modes.
- **Wave 1 alignment:** Sam §3.2's "9 capability needed" enumeration is a quantifier-precision-refinement event in waiting. No conflicts.

### Doctrine 12: Resilience-track-arc-completion (1 instance at elevation candidacy)
- **Applies to P1 because:** P1.E (embodied) may become a NEW arc candidate. Watch for arc-completion at the milestone where commitment store + scheduler + policy + verifier + mock adapter all CLOSE together.
- **P1 enforcement:** at P1's end-of-arc closure, evaluate per the 3 criteria + document the milestone in BOTH CLAUDE.md and a dedicated memory file.
- **Wave 1 alignment:** No analyst noted this; arc-completion is a meta-doctrine. Elon §4 ("reusable rocket") aligns with arc-completion thinking.

### Doctrine 13: Spec-first review cycle for multi-day specs (15-for-15)
- **Applies to P1 because:** every P1.* sub-PR > 1 day MUST run Phase 0 → Plan v1 → review → Plan v2 → code. No "obvious refactor" exceptions.
- **P1 enforcement:** the 5-artifact cadence is the binding process. OPTIONAL-Plan-v2 path (per doctrine #8) reduces this to 3-artifact when clean. Strict-industry-standard mode applies (110 applications + 32 closures already).
- **Wave 1 alignment:** All 7 analysts implicitly produced Phase 0 audits in their reports (they're Wave 1). The handoff to Architect/Developer/Auditor agents is the Plan v1 stage. No conflicts.

### Doctrine 14: Spec-contracts-not-implementations (3+ instances)
- **Applies to P1 because:** `cognition/specs/v0/` IS the contract layer (per Decision 3.6). The developer implements the contract; architect spec MUST NOT prescribe implementation details (e.g. "use sqlite3").
- **P1 enforcement:** every P1 plan v1 frames specs at invariant level (`commitment row MUST survive process restart with full payload + due_ts + verifier_id`), NOT at function-signature level. Adapter SDK is the canonical instance.
- **Wave 1 alignment:** TechAnalyst-1 §3.2 B-H1 fix (`IdentityClaim.confidence_is_no_signal` field, not `== 0.0` callers) is the doctrine applied. Sam §7 (adapter contract for robot foundation models) is the doctrine extended.

### Doctrine 15: Developer-improves-on-spec-by-reading-carefully (6-for-6)
- **Applies to P1 because:** P1 introduces new contracts with novel surface areas. Implementation will reveal better paths than spec imagined.
- **P1 enforcement:** developer flags improvement at closure narrative; architect audits as "preserves architectural intent yes/no." Track record continues.
- **Wave 1 alignment:** No conflicts.

### Load-bearing architect-memory feedback files

Each shapes a P1 decision; not yet elevated to numbered doctrine.

- **`feedback_strict_industry_standard_mode.md`** — Effect on P1 plan: every P1 cycle runs under strict mode (pre-mortem + multi-direction invariant trace + 14-gate checklist + cross-spec impact + production-canary diff). The 14-gate checklist (locked at P0.S10) governs every D-decision. The OPTIONAL-Plan-v2 sub-rule (§8) decides whether v2 ships.
- **`feedback_role_architect_not_developer.md`** — Effect on P1 plan: I (CEO) write THIS plan; Architect translates to Phase 0 + Plan v1 per spec; Developer implements; Auditor ratifies. P1 cycles preserve role separation. CEO does NOT write code.
- **`feedback_developer_agent_capability.md`** — Effect on P1 plan: Developer is empowered to improve mechanism within contract. Spec-contracts-not-implementations doctrine binds Architect; this binds Developer to discover better paths.
- **`feedback_communication_style.md`** — Effect on P1 plan: structured artifacts for handoffs (Plan v1/v2 templates); conversational style for review discussion + closure narrative drafting.
- **`feedback_discuss_first.md`** — Effect on P1 plan: every P1.* sub-PR begins with discussion in CLAUDE.md "Pending Work" before any code touches keyboard.
- **`feedback_deferred_canary_strategy.md`** — Effect on P1 plan: P0.R11+ canary strategy continues. P1 sub-PRs add entries to `to_be_checked.md`; one canary week at end of P1.A (architecture phase) before P1.E (embodied phase) begins. NO live canaries during P1 development. Strict-mode tightens under this mode.

### Conflicts between Wave 1 recommendations and existing doctrines

**Conflict 1 (resolved):** TechAnalyst-1's MF4 prescribes P1.A1-A3 pipeline.py decomposition as a CRITICAL pre-requirement. Elon's first-principles read defers it. Doctrine #6 (granular decomposition) is silent on order-of-operations. **Resolution: defer to Elon's framing.** Pipeline.py decomposition becomes P2 hygiene running in parallel with P1.E. The wrong-premise here is "decomposition gates embodied," not "decomposition is needed." Doctrine #4 (Phase-0 wrong-premise) ratifies the reframing.

**Conflict 2 (resolved):** Skeptic-2 declares "KaraOS will NOT become THE universal ROS 2 standard." Strategic goal says it must. **Resolution: hold the goal, adopt the prerequisites Skeptic-2 names.** Apache 2.0 + GOVERNANCE.md + Adapter SDK at END of P1 + 30-minute onboarding tutorial + TurtleBot4 reference robot. Skeptic-2 calls these out as ABSENT today; P1 ships them all.

**Conflict 3 (resolved):** Sundar §1 recommends "Reference robot pick = TurtleBot4 (Unitree G1 deferred to P3)." `future-execution.md` Decision (implicit in §2.4.4 mandatory differentiator #4) names Unitree G1 in Phase 4. **Resolution: defer to Sundar.** TurtleBot4 in Gazebo at end of P1 is the right call — OSRF reference, ROS 2 LTS supported, $200 dev-affordable, ecosystem-recognized. Unitree G1 stays for P3 when humanoid form factor matters. `future-execution.md` Decision 4.3 amended per §8 below.

**Conflict 4 (resolved):** TechAnalyst-2's agent consolidation prescribes a profile gate (`KARAOS_PROFILE`). No existing doctrine covers config-gated layered architecture. **Resolution: adopt as a new pattern but DO NOT elevate to doctrine yet.** 1 instance is below the 3+ elevation threshold. Profile gate becomes a P1 mechanism; doctrine elevation candidacy after 3+ similar patterns appear.

**Conflict 5 (no conflict, alignment):** Skeptic-1's BUG-2 (assert→raise under python -O) aligns with `feedback_strict_industry_standard_mode.md` fail-loud discipline. Not a conflict; a Pre-P1 hardening item.

**Conflict 6 (no conflict, alignment):** Sam §3 (embodied eval bench) extends `### Canary-surfaces-real-gaps` doctrine. Not a conflict; an extension.

---

## SECTION 3: AGREEMENTS & CONFLICTS ACROSS THE 7 WAVE 1 REPORTS

### Where the 7 agreed (high-confidence findings)

1. **CI scaffold is the single highest-leverage Pre-P1 fix** (TechAnalyst-1 MF1, Skeptic-1 §4, Sundar §3.5, Elon §2 concede). Without CI, all 28+ structural invariants are architect-advisory. Confidence: 7/7 unanimous.
2. **The Adapter SDK package boundary must ship before P7** (Skeptic-2 §4, Elon §3 Move 1, Sundar §1 priority 2, Sam §7). Decision 3.9 in `future-execution.md` scheduling at Phase 7 is wrong-by-precedent (OCI/CNCF pattern is spec-first). Confidence: 4/4 strategists agree (the 3 internal reports don't address sequencing).
3. **License must be Apache 2.0, locked NOW** (Sundar §3.1, Skeptic-2 §4 prerequisite 1). Confidence: 2/2 strategists; not addressed by internal reports but no conflict.
4. **Memory pollution from misattribution is a schema-shape problem, not a prompt-engineering problem** (TechAnalyst-2 §1 #3, Skeptic-1 §3 bug census on misattribution). Implication: P1 needs memory event-sourcing (H12 hook) per TechAnalyst-2 §7.3. Confidence: 2/2 deep-code reviewers.
5. **The 18-agent count is over-engineered for robotics, under-engineered for it** (TechAnalyst-2 §2.2, Sam §1, Elon §5 concession #2). Implication: profile-gated agent layers. Confidence: 3/3 agents who reviewed the agent layer.
6. **Pipeline.py decomposition is real debt but not THIS-quarter's work** (Elon §3 Move 3 explicitly, TechAnalyst-1 §4.4 "Decide P1.A1-A3 shape BEFORE any code lands" implicitly defers via Phase 0 discipline). Confidence: 2/2 architects; Skeptic-1 § doesn't address scope ordering.
7. **Per-skill verifier registry with abstention IS the moat** (Elon §4 "reusable rocket move", Sam §7 adapter contract for foundation models, Skeptic-2 §6 ecosystem-extension factor). Confidence: 3/3 strategic agents.

### Where the 7 conflicted

**Conflict A — Pipeline.py decomposition timing.**
- **TechAnalyst-1 (MF4 CRITICAL):** "decide P1.A1-A3 decomposition shape before any code lands."
- **Elon (Move 3 + Attack 3):** "defer until after Phase 4 demo."
- **My judgment:** Elon wins. Per `future-execution.md` §3.7 + §4.3, embodied runtime touches `pipeline.py` at exactly one function call. Pipeline.py being 8000 lines does not gate embodied work. The 8-10 week strategic clock to claim Layer D forecloses if we decompose first.
- **Doctrine check:** Doctrine #4 (Phase-0-catches-wrong-premise) backs Elon — the premise "decomposition gates embodied" is wrong-by-grep. Doctrine #6 (granular decomposition) is silent on order.
- **Resolution: defer pipeline.py decomposition to P2. P1 ships embodied first.**

**Conflict B — Reference robot pick.**
- **Sundar §1:** TurtleBot4 (OSRF reference, ROS 2 LTS, $200 dev kit, ecosystem-recognized).
- **`future-execution.md` §2.4.4:** Unitree G1 (humanoid, $16K, partner-channel signal).
- **My judgment:** Sundar wins for P1. TurtleBot4 is the right "first reference" — proves portability without humanoid complexity. Unitree G1 stays for P3 when humanoid differentiation matters.
- **Doctrine check:** Doctrine #14 (spec-contracts-not-implementations) is satisfied either way — the SDK contract is body-agnostic.
- **Resolution: TurtleBot4 reference adapter ships end of P1; Unitree G1 deferred to P3.**

**Conflict C — Embodied eval harness urgency.**
- **Sam §3:** "If KaraOS ships P1 without an embodied-eval harness, P1 has failed regardless of how good the code is." Eval is the #1 differentiator.
- **TechAnalyst-1, TechAnalyst-2, Skeptic-1:** No explicit eval-bench advocacy.
- **My judgment:** Sam wins. The conversation eval bench (`tests/eval_intent_bench.py`) is the architectural template. P1 ships `tests/embodied_eval_bench.py` as a P1.* sub-PR.
- **Doctrine check:** Doctrine #9 (Canary-surfaces-real-gaps) is satisfied via the bench acting as continuous eval signal.
- **Resolution: P1.E.0 (Embodied eval bench) ships before any embodied code, as part of Phase 0 of P1.E.**

**Conflict D — Defense-in-depth on `core/robot.py` hardware abstraction layer.**
- **Skeptic-1 §1 #4:** "There is currently no `core/robot.py` hardware abstraction." Implies P1 should have one.
- **Elon §3 Move 1:** "The Adapter SDK is the contract layer; robot-stack-specific code lives behind the SDK boundary." Implies no `core/robot.py` is needed; the SDK is the abstraction.
- **My judgment:** Elon wins by spec-contracts-not-implementations doctrine (#14). The contract IS the abstraction. `core/robot.py` would be wrong-layer (cognitive process should not import robot specifics).
- **Resolution: no `core/robot.py`. Adapter SDK + capability contract is the abstraction.**

**Conflict E — Governance timing.**
- **Skeptic-2 §4 prerequisite 1:** GOVERNANCE.md + TSC charter aspirational by end of P1.
- **Sundar §3:** Apache 2.0 LICENSE + DCO + minimal GOVERNANCE.md within P1, foundation deferred to "after first 3 adopters."
- **My judgment:** Sundar wins. License + charter NOW (P1 must-fix); foundation donation AFTER traction. CNCF/LF donations require traction signal.
- **Resolution: Apache 2.0 + GOVERNANCE.md (aspirational, 1-page) lands in Pre-P1 must-fix list. Foundation discussion deferred to P3.**

---

## SECTION 4: PRE-P1 MUST-FIX LIST

Ordered by criticality. Every item must close BEFORE P1 starts.

### MF1 (CRITICAL) — Ship CI scaffold

- **What:** Land `.github/workflows/{fast,slow,security}.yml` per `complete-plan.md` P0.0. Status `[CLOSED]` per `complete-plan.md` line 85 — but the closure narrative says it shipped, yet the actual `.github/workflows/` does not exist (per Pending Work block in CLAUDE.md: "P1.P1 — No CI config"). **Re-verify and remediate.**
- **Why now:** every elevated doctrine + every structural invariant is architect-advisory without CI. The first P1 sub-PR that violates `test_silent_except_invariant` or `test_layering_invariants` will silently merge.
- **How to fix:** (a) grep-verify `.github/workflows/` actually contains the 3 yml files. (b) If missing, create them per the `complete-plan.md` P0.0 spec. (c) Run a deliberate-regression check (push a PR with an `except Exception: pass` and watch CI fail). (d) Update CLAUDE.md to reflect actual state.
- **Doctrine governing the fix:** Doctrine #5 (Verification-before-completion). Closure narrative claimed CLOSED; grep MUST verify.
- **Validation:** `git push` to any branch triggers `fast.yml` within 5 minutes. A test PR with a deliberate silent-except triggers red CI.
- **Owner:** Developer (mechanical) + Auditor (verify).
- **Estimated time:** 0.5 day if files already exist (just verify); 0.5 day if missing (create from `complete-plan.md` P0.0 spec).
- **Phase 0 → Plan vN required?:** No. Already specified in `complete-plan.md` P0.0; this is verification + remediation.

### MF2 (CRITICAL) — Apache 2.0 LICENSE + GOVERNANCE.md aspirational charter

- **What:** Add `LICENSE` (Apache 2.0 full text), `NOTICE` (Copyright 2026 Jagan Nivas), `CONTRIBUTING.md` (DCO sign-off), `GOVERNANCE.md` (1-page aspirational: accept external contributors, create TSC when contributor count ≥5 from 2+ orgs, intent to donate to foundation when adoption justifies). Add SPDX headers (`# SPDX-License-Identifier: Apache-2.0`) to every Python file in `core/`, `pipeline.py`, `tests/`, `tools/`.
- **Why now:** every PR landed without a license has uncertain IP status. Relicensing later requires every contributor's sign-off (currently just Jagan, so still tractable — but every day this delays compounds). Per Sundar §3.1 (canonical cautionary tale: GCC GPLv3 → LLVM BSD = standard reversal). Per Skeptic-2 §4 prerequisite 1.
- **How to fix:** mechanical file creation. Apache 2.0 text from `https://www.apache.org/licenses/LICENSE-2.0.txt`. GOVERNANCE.md drafts from CNCF templates. SPDX headers via single sed pass.
- **Doctrine governing the fix:** None directly; this is a Pre-P1 architectural decision NOT covered by existing 15 doctrines. Becomes a new "License + Governance" discipline if Sundar §3 patterns recur in P2/P3.
- **Validation:** `LICENSE` present in repo root, `find . -name "*.py" -exec head -1 {} \; | grep -c SPDX | wc -l` matches Python file count. Publish to public GitHub (or at minimum, internal staging).
- **Owner:** Jagan (decision) + Developer (mechanical sed) + Auditor (verify SPDX coverage).
- **Estimated time:** 1 day.
- **Phase 0 → Plan vN required?:** No. Non-code decision artifacts. Plan v1 optional (single-author SPDX sweep is mechanical).

### MF3 (CRITICAL) — Strategic alignment decision in CLAUDE.md "Project Overview"

- **What:** Per TechAnalyst-1 MF6, resolve the ambiguity between (A) consumer social-AI runtime where ROS 2 is an extension and (B) universal ROS 2 cognitive middleware where current code is the FIRST reference adapter. The strategic goal locks (B). CLAUDE.md "Project Overview" line 113 currently says "AI robot dog" — out of date.
- **Why now:** every P1 sub-PR architect/developer/auditor reads CLAUDE.md first. Ambiguous overview = ambiguous scope = wasted cycles.
- **How to fix:** rewrite CLAUDE.md "Project Overview" section to: "KaraOS — durable cognitive middleware for ROS 2 robots. Layer D in the 2026 embodied-AI stack. Current `dog-ai/` codebase is the first reference adapter (social-AI cognitive runtime that consumes the v0 contracts). P1 adds the embodied runtime + Adapter SDK + TurtleBot4 reference adapter + MCP server endpoint."
- **Doctrine governing the fix:** Doctrine #4 (Phase-0-catches-wrong-premise) implicitly — the wrong-premise about what KaraOS IS will surface at every P1 Phase 0 if not fixed here.
- **Validation:** every P1 sub-PR's Phase 0 audit can quote CLAUDE.md overview without ambiguity.
- **Owner:** Jagan + CEO (decision) + Architect (rewrite).
- **Estimated time:** 2 hours.
- **Phase 0 → Plan vN required?:** No. Decision artifact only.

### MF4 (CRITICAL) — Skeptic-1 BUG-1 (`time.time()` for deadlines)

- **What:** Replace every `time.time() + N` or `while time.time() < deadline:` pattern in `core/*.py` + `pipeline.py` with `time.monotonic()`. Keep `time.time()` only for absolute timestamps logged to disk or DB.
- **Why now:** NTP correction on Jetson boot silently breaks watchdog deadlines + log retention. Universal embedded-systems concern (NASA SWE, MISRA C++ 17-3-1). Will surface as production bug the first time the Jetson is deployed.
- **How to fix:** AST scan + replacement. New AST invariant test: ban `time.time()` inside `while` / `for` loop conditions in production code (allowlist explicit DB-timestamp sites with `# WALLCLOCK:` annotation).
- **Doctrine governing the fix:** Doctrine #1 (Induction-surfaces-invariant-gaps). AST invariant + deliberate-regression check (inject `time.time()` in a while-loop → invariant fires → revert → green).
- **Validation:** `tests/test_no_time_time_in_deadlines.py` passes. Production canary on Jetson (when hardware arrives) survives NTP correction.
- **Owner:** Architect (Plan v1 with named edit sites — Skeptic-1 cites 5 specific sites including `pipeline.py:2769-2772`) + Developer (mechanical replacement) + Auditor (Pass-2 grep).
- **Estimated time:** 1 day.
- **Phase 0 → Plan vN required?:** Yes — multi-site refactor. Phase 0 + Plan v1 + closure (3-artifact OPTIONAL-Plan-v2 cycle).

### MF5 (CRITICAL) — Skeptic-1 BUG-2 (assert under `python -O`)

- **What:** Replace every `assert condition, msg` in `core/*.py` + `pipeline.py` with `if not condition: raise RuntimeError(msg)`. Skeptic-1 enumerates 14 sites including `pipeline.py:1742, 2016-2028, 6611, 6635, 6641, 6661, 6667, 6672, 6692, 6698`.
- **Why now:** all 14 asserts enforce LOAD-BEARING invariants (invalid person_type, room orchestrator init without deps, brain tool missing from privilege table = fail-closed contract). `python -O` strips every assert. Production deployments commonly use `-O`.
- **How to fix:** sed-able replacement. New AST invariant test: ban `assert` in production code (allowlist `tests/*.py`).
- **Doctrine governing the fix:** Doctrine #1 (Induction-surfaces-invariant-gaps) — invariant ships with deliberate-regression check.
- **Validation:** `tests/test_no_assert_in_production_code.py` passes. Run pipeline with `python -O pipeline.py` and confirm fail-closed invariants still fire as RuntimeError.
- **Owner:** Architect + Developer + Auditor.
- **Estimated time:** 1 day.
- **Phase 0 → Plan vN required?:** Yes. Phase 0 + Plan v1 + closure.

### MF6 (HIGH) — Skeptic-1 BUG-3/BUG-4 (`_log_drain` + `_log_q` observability)

- **What:** Add `_drain_failure_count` to `_log_drain`; emit one `sys.__stderr__.write` warning every Nth failure (bypass the Tee with the raw fd). Switch `_log_q` from unbounded `SimpleQueue` to bounded `queue.Queue(maxsize=10000)` with drop-oldest semantics.
- **Why now:** drain-thread crash = total log loss with no operator signal. Unbounded queue = OOM under multi-day uptime + drain stall.
- **How to fix:** localized changes in `pipeline.py:165, 167-180`. New AST invariant: `deque(maxlen=N)` requires explicit `maxlen` kwarg in `core/*.py`.
- **Doctrine governing the fix:** Doctrine #1 + Doctrine #5.
- **Validation:** simulate disk-full (chmod faces/terminal_output.md to read-only); confirm stderr warning fires; confirm queue does not grow unboundedly.
- **Owner:** Developer + Auditor.
- **Estimated time:** 0.5 day.
- **Phase 0 → Plan vN required?:** No (small localized change). Direct Plan v1 + closure.

### MF7 (HIGH) — TechAnalyst-1 B-H1 (IdentityClaim.confidence_is_no_signal field)

- **What:** Add `IdentityClaim.confidence_is_no_signal: bool` field to `core/reconciler_state.py`. Migrate 3 `claim.confidence == 0.0` checks in `core/reconciler.py:715, 739, 794` to `claim.confidence_is_no_signal`. Backend callers (`core/voice.py::identify`) set the flag explicitly.
- **Why now:** the semantic "0.0 = embedding failed; <0 = anti-correlated" is encoded in the ECAPA backend's return convention, not in the IdentityClaim type. Swapping backends silently breaks the cascade. P1 will introduce multi-robot-platform adapters with different voice-ID backends; the cascade WILL break.
- **How to fix:** field addition + 3-site migration + AST invariant `test_reconciler_no_exact_equality_against_claim_confidence`.
- **Doctrine governing the fix:** Doctrine #14 (Spec-contracts-not-implementations). The contract — "this claim represents a no-signal embedding-failure case" — becomes part of the type, not part of a backend convention.
- **Validation:** AST invariant + Session 119 closure narrative regression guard.
- **Owner:** Architect + Developer + Auditor.
- **Estimated time:** 0.5 day.
- **Phase 0 → Plan vN required?:** Yes. Phase 0 + Plan v1 + closure (mechanical extraction discipline).

### MF8 (HIGH) — TechAnalyst-1 B-H2 (SessionSnapshot mutable lists → tuple)

- **What:** Change `SessionSnapshot.recent_voice_confs`, `core_memory`, `recent_attributions` from `list` to `tuple` (frozen-by-construction). Owner `Session` keeps list. `_to_snapshot` converts via `tuple(...)`.
- **Why now:** P0.R6 heavy-worker pools added; P1.E will extend cross-process consumers. Each one is a potential silent-mutation bug source.
- **How to fix:** field type change + 1 AST invariant + 1 round of typing fixups in consumers.
- **Doctrine governing the fix:** Doctrine #14 + Doctrine #1 (induction check via deliberate `snap.recent_voice_confs.append(x)` regression).
- **Validation:** AST invariant + consumers compile without warning + induction passes.
- **Owner:** Architect + Developer + Auditor.
- **Estimated time:** 0.5 day.
- **Phase 0 → Plan vN required?:** Yes. Phase 0 + Plan v1 + closure.

### MF9 (MEDIUM) — TechAnalyst-1 B-H3 (`state.py:60` `**_persistent` spread under lock)

- **What:** Acquire `_persistent_lock` (already exists from P0.B5 D4) for the snapshot read inside `write()`: `with _persistent_lock: persistent_snapshot = dict(_persistent)` and spread the snapshot, not the live global. Lock held for one `dict(...)` call (microseconds).
- **Why now:** P0.B5 locked the writer but not the reader. Latent activation: future runtime writers, GIL-free CPython 3.13+, executor-thread `write()` calls.
- **How to fix:** 2-line change in `core/state.py:60`. New AST invariant: every `**_persistent` spread must be inside `with _persistent_lock:` block.
- **Doctrine governing the fix:** Doctrine #1.
- **Validation:** existing test `test_persistent_dict_under_concurrent_writers` extended.
- **Owner:** Developer + Auditor.
- **Estimated time:** 1 hour.
- **Phase 0 → Plan vN required?:** No. Direct Plan v1 + closure.

### MF10 (MEDIUM) — TechAnalyst-1 B-M5 (split `everything_about_system.md`)

- **What:** Split `everything_about_system.md` (608 KB, 10000+ lines) into `everything_about_system/{00-toc.md, 01-foundations.md, 02-lifecycle.md, ...}` mirroring the part structure. Each part stays under 200KB.
- **Why now:** future contributors / agents can't reliably consume it. The TOC + Part references inside the file are intra-document and cannot survive a partial Read tool call (the 256KB limit blocks). Every P1 cycle's `### Architect-reads-production-code-before-sign-off` audit needs to read the system doc.
- **How to fix:** mechanical split + cross-reference updates.
- **Doctrine governing the fix:** Doctrine #2.
- **Validation:** every part file < 200KB. Cross-references via explicit file links resolve.
- **Owner:** Architect (decide split boundaries) + Developer (mechanical).
- **Estimated time:** 0.5 day.
- **Phase 0 → Plan vN required?:** No. Plan v1 + closure (mechanical extraction).

### Pre-P1 must-fix summary

| # | Item | Sev | Time | Owner | Spec cycle |
|---|---|---|---|---|---|
| MF1 | CI scaffold verify + remediate | CRITICAL | 0.5d | Dev+Auditor | None (verify) |
| MF2 | Apache 2.0 LICENSE + GOVERNANCE.md | CRITICAL | 1d | Jagan+Dev+Auditor | None (decision) |
| MF3 | Strategic alignment in CLAUDE.md | CRITICAL | 2h | Jagan+CEO+Arch | None (decision) |
| MF4 | BUG-1 time.monotonic | CRITICAL | 1d | Arch+Dev+Auditor | Phase 0 + Plan v1 + closure |
| MF5 | BUG-2 assert→raise | CRITICAL | 1d | Arch+Dev+Auditor | Phase 0 + Plan v1 + closure |
| MF6 | BUG-3/4 log drain observability | HIGH | 0.5d | Dev+Auditor | Plan v1 + closure |
| MF7 | B-H1 IdentityClaim contract | HIGH | 0.5d | Arch+Dev+Auditor | Phase 0 + Plan v1 + closure |
| MF8 | B-H2 SessionSnapshot tuple | HIGH | 0.5d | Arch+Dev+Auditor | Phase 0 + Plan v1 + closure |
| MF9 | B-H3 `**_persistent` under lock | MEDIUM | 1h | Dev+Auditor | Plan v1 + closure |
| MF10 | Split everything_about_system.md | MEDIUM | 0.5d | Arch+Dev | Plan v1 + closure |

**Total Pre-P1 effort: ~6 days serial (parallelizable to ~3-4 days with Architect+Developer+Auditor working in parallel).** Pre-P1 must close before P1 starts.

---

## SECTION 5: THE COMPLETE P1 CYCLE PLAN

P1 splits into 5 tracks: P1.A (architecture pre-work, parallel to others), P1.E (embodied runtime — the load-bearing track), P1.S (SDK + spec), P1.M (MCP server), P1.R (reference robot). All tracks run in parallel; the canary week closes after all tracks finish.

### Phase 0 of P1 (week 0, 1 week)

**Task P1.Phase0** — full Phase 0 audit on EACH track. Decompose into D-decisions with named edit sites. Auditor Q5 estimates per doctrine #6.

- **What:** 5 Phase 0 audits (one per track) lock the scope.
- **Why:** doctrine #4 (Phase-0-catches-wrong-premise) requires this BEFORE any code. doctrine #13 (Spec-first review cycle) requires this for multi-day specs.
- **How:** Architect runs grep-verified Phase 0 audit per track per the spec-first cycle template.
- **Real-world precedent:** every spec cycle since P0.S7.D-D follows this (15-for-15 track record).
- **Spec cycle path:** Phase 0 only (no implementation).
- **D-decisions:** N/A — this IS the decomposition.
- **Pass-2 grep requirements:** 3-part Pass-2 grep at architect drafting time (symbol-name + behavioral-semantic + symmetric-reject-preserve).
- **14-gate checklist:** all 14 gates apply at Phase 0 surface.
- **Success criteria:** 5 Phase 0 audit documents in `tests/` for the 5 tracks; each names D-decisions with file:line refs; auditor Q5 estimates ON-TARGET.
- **Risks:** Phase 0 surfaces unexpected scope expansion → re-plan track ordering. Mitigation: budget 30% slack.
- **Dependencies:** Pre-P1 must-fix (MF1-MF10) closed.
- **Estimated time:** 1 week.

### P1.A — Architecture pre-work (running in parallel, NOT blocking)

**P1.A1 — Pipeline.py decomposition Phase 0 audit (DEFERRED to P2)**

Per Elon §3 Move 3 + Conflict A resolution: pipeline.py decomposition is real debt but NOT P1 scope. Phase 0 audit at end of P1 ratifies the deferral.

**P1.A2 — Agent consolidation under KARAOS_PROFILE config gate**

- **What:** New `core/agents/` directory tree. Move 11 companion-only agents to `core/agents/companion/`. New `core/agents/robotics/` (initially empty, populated by P1.E tracks). `KARAOS_PROFILE: str = "both"` in `core/config.py` with values `{"companion", "robotics", "both"}`. Mechanical-extraction discipline (no `while-I'm-here` cleanups).
- **Why:** companion-agent overhead drags every P1 cycle (TechAnalyst-2 §1 thesis). Adding new robotics agents to the existing 411 KB `brain_agent.py` worsens the monolith.
- **How:** mechanical move + import updates + profile gate at orchestrator init.
- **Real-world precedent:** Linux kernel menuconfig; ROS 2 apt-package selectors (`ros-humble-desktop` vs `ros-humble-ros-base`).
- **Spec cycle path:** Phase 0 → Plan v1 → Plan v2 → code (5-artifact HEAVY band — multi-subsystem mechanical move + profile gate is risky at this scale).
- **D-decisions:** D1 directory structure + mv operations; D2 import updates; D3 profile config + assertion; D4 BrainOrchestrator gating; D5 AST invariant `test_kara_os_profile_gates_agent_load`.
- **Pass-2 grep requirements:** symbol-name (every moved agent class name still findable by import) + behavioral-semantic (orchestrator routes through profile gate) + symmetric-reject-preserve (companion class never loads under robotics profile; robotics class never loads under companion profile).
- **14-gate checklist:** all 14 gates apply.
- **Success criteria:** profile = "companion" loads 11 companion agents; profile = "robotics" loads 0 (P1.A2 lands before P1.E adds robotics agents); profile = "both" loads all. Zero behavior change to existing canary scenarios.
- **Risks:** circular imports surface during the move. Mitigation: Phase 0 maps every cross-class dependency.
- **Dependencies:** Pre-P1 must-fix.
- **Estimated time:** 1 week.

### P1.E — Embodied runtime (the load-bearing track, 6-8 weeks)

**P1.E.0 — Embodied evaluation harness (FIRST)**

- **What:** `tests/embodied_eval_bench.py` parallel to `tests/eval_intent_bench.py`. Compute action-grounding eval, safety-gate latency eval, sim-to-real parity eval. Pure functions + CLI invocation + persisted runs in `tests/embodied_eval_runs/`.
- **Why:** Sam §3 — if P1 ships without embodied eval, P1 has failed regardless of code quality. The eval bench is the CONTRACT for every subsequent embodied PR.
- **How:** mirror `tests/eval_intent_bench.py` shape exactly. Mock world + Gazebo backends.
- **Real-world precedent:** Physical Intelligence π0 internal eval methodology; NVIDIA GR00T Isaac Sim closed-loop tasks; Google DeepMind Gemini Robotics Apollo testbed.
- **Spec cycle path:** Phase 0 → Plan v1 → Plan v2 → code (5-artifact HEAVY band — net-new eval infrastructure).
- **D-decisions:** D1 fixture scenarios (10 canonical); D2 `compute_metrics()` per-action-class + per-skill; D3 latency-budget gate; D4 `save_run` schema; D5 CLI; D6 weekly eval extension in `tests/eval_weekly.py`.
- **Pass-2 grep requirements:** 3-part Pass-2 grep on every D.
- **14-gate checklist:** all 14 gates.
- **Success criteria:** bench produces metrics for 10 mock-world scenarios. Any PR touching `core/embodied/` dispatch surfaces a delta report.
- **Risks:** Phase 0 budget at 2-3 weeks; bench may need 4 weeks if sim integration is harder than expected. Mitigation: ship mock-world bench first (week 1), Gazebo integration in week 2 if budget allows.
- **Dependencies:** Pre-P1 must-fix; P1.Phase0 complete.
- **Estimated time:** 2-3 weeks.

**P1.E.1 — Durable commitment store**

- **What:** New `core/embodied/commitment_db.py` + `commitment.db` SQLite schema. Fields: `commitment_id` (UUID), `created_at`, `due_ts`, `payload` (BLOB JSON), `status` (`pending`/`scheduled`/`fired`/`completed`/`failed_verification`/`cancelled`), `verifier_id`, `audit_chain` (parent_event_id from event_log). WAL mode + `isolation_level=IMMEDIATE` per P0.9.1 Imp-1. Migration shape per P0.9.2 (5-tuple).
- **Why:** the #1 defensible-gap differentiator (`future-execution.md` §2.4.2 #1). Without durable commitments, KaraOS is "another chatbot."
- **How:** schema + 5-tuple migration + `BrainOrchestrator.notify()` extension for commitment events.
- **Real-world precedent:** LangGraph Postgres checkpointer; AutoGen state save/resume.
- **Spec cycle path:** Phase 0 → Plan v1 → code (3-artifact OPTIONAL-Plan-v2 cycle; net-new schema is mechanical).
- **D-decisions:** D1 schema (file:line in new file); D2 migration; D3 CommitmentStore class with paired-write to event_log H12 hook; D4 `BrainOrchestrator.commit_pending()`; D5 AST invariant `test_commitment_schema_versioned`.
- **Pass-2 grep requirements:** symbol-name + symmetric paired-write enumeration.
- **14-gate checklist:** all 14 gates.
- **Success criteria:** commitment row written + persisted across process restart + audit chain intact via event_log. `tests/test_p1_e1_commitment_durable_survive_restart.py` passes.
- **Risks:** event_log H12 hook implies extending the existing event_log table. Mitigation: additive migration.
- **Dependencies:** Pre-P1, P1.Phase0, P1.A2 (agents/robotics/ exists), P1.E.0 (eval bench captures commitment-creation latency).
- **Estimated time:** 1 week.

**P1.E.2 — Scheduler service**

- **What:** New `core/embodied/scheduler.py`. Asyncio scheduler fires commitments at `due_ts` per Q3 (a) bounded-burst-limit policy. Late-fire policy per Decision 3.x (lookup in `future-execution.md`). Recovery-from-restart: scheduler resumes pending commitments via `commitment_db.list_pending()`.
- **Why:** scheduler IS the durable layer. `future-execution.md` §2.4.2 #1 names this.
- **How:** asyncio task started in `BrainOrchestrator.__init__` (gated by `KARAOS_PROFILE in ("robotics","both")`).
- **Real-world precedent:** Cloudflare Durable Objects alarms; LangGraph scheduled checkpoint resume.
- **Spec cycle path:** Phase 0 → Plan v1 → Plan v2 → code (HEAVY band).
- **D-decisions:** D1 scheduler class; D2 due_ts polling loop; D3 late-fire policy enum; D4 process-restart resume; D5 `tests/test_p1_e2_scheduler.py` 6 anchors.
- **Pass-2 grep requirements:** behavioral-semantic verification of late-fire branches.
- **14-gate checklist:** all 14 gates.
- **Success criteria:** kill process mid-pending; restart; scheduler fires pending commitments at due_ts. Latency < 1 second from due_ts.
- **Risks:** missed-fire on long downtime. Late-fire policy must distinguish "fire immediately on restart" vs "skip if too stale."
- **Dependencies:** P1.E.1.
- **Estimated time:** 1.5 weeks.

**P1.E.3 — Per-skill verifier registry**

- **What:** New `core/embodied/verifier_registry.py`. Per-skill verifier classes (initially: `MockWorldVerifier` for Phase 1, `SimGroundTruthVerifier` for Phase 4). Verifier returns `{passed: bool, evidence: dict, abstained: bool, abstain_reason: str}`. The abstention protocol IS the moat (Elon §4 reusable-rocket).
- **Why:** Decision 3.4 + 3.10 + Elon §4. Verifier-adapter disagreement protocol is the load-bearing differentiator.
- **How:** registry mapping `skill_name → verifier_class`. AST invariant `test_verifier_registry_covers_every_skill` (per skill in `cognition/specs/v0/skills/`, a registered verifier exists OR an explicit `# UNVERIFIED:` annotation).
- **Real-world precedent:** ROSClaw's verifier abstention pattern (closest competitor); Physical Intelligence π0 evaluation methodology.
- **Spec cycle path:** Phase 0 → Plan v1 → Plan v2 → code (HEAVY band — net-new abstraction).
- **D-decisions:** D1 verifier ABC; D2 registry + skill enumeration; D3 mock + sim verifier impls; D4 abstention protocol; D5 disagreement → `failed_verification` transition; D6 AST invariant.
- **Pass-2 grep requirements:** all 3 parts.
- **14-gate checklist:** all 14 gates.
- **Success criteria:** test scenario where verifier abstains AND verifier disagrees with adapter, both transition state correctly. `tests/test_p1_e3_verifier_disagreement.py`.
- **Risks:** abstention protocol design has no production precedent. Mitigation: prototype against MockWorld; iterate before Gazebo.
- **Dependencies:** P1.E.1, P1.E.2, P1.E.0 (eval bench measures abstention rate).
- **Estimated time:** 2 weeks.

**P1.E.4 — Policy engine**

- **What:** New `core/embodied/policy_engine.py`. YAML/JSON-described rules ("don't shutdown without owner confirmation," "don't navigate to no-speak zones during quiet hours," "rate-limit proposals to 1/sec"). Engine evaluates each commitment + skill proposal against active rules. Rejection → `rejected_by_policy` outcome.
- **Why:** Decision 3.6 — LLM never calls adapter directly; policy gate is structural.
- **How:** rule schema in `cognition/specs/v0/policies/`. Engine evaluation in `_execute_skill` chain BEFORE adapter dispatch.
- **Real-world precedent:** OPA (Open Policy Agent), Kubernetes admission controllers.
- **Spec cycle path:** Phase 0 → Plan v1 → Plan v2 → code (HEAVY band).
- **D-decisions:** D1 rule schema; D2 engine; D3 dispatch chain integration; D4 rejection metadata in audit log; D5 AST invariant `test_no_skill_execution_bypasses_policy_engine`.
- **Pass-2 grep requirements:** all 3 parts; symmetric reject-preserve class is load-bearing.
- **14-gate checklist:** all 14 gates.
- **Success criteria:** test scenario where commitment proposes an unsafe action → policy rejects before dispatch → audit log records `rejected_by_policy` with rationale.
- **Risks:** rule expressiveness vs simplicity tradeoff. Mitigation: ship 3 hand-curated rules at v0.1, expand.
- **Dependencies:** P1.E.3.
- **Estimated time:** 1.5 weeks.

**P1.E.5 — Mock adapter + first end-to-end embodied scenario**

- **What:** New `core/embodied/mock_adapter.py`. Implements RobotCapability interface from `cognition/specs/v0/`. Returns deterministic outcomes for testing. End-to-end scenario: user says "shut off the oven in 45 minutes," KaraOS parses → commitment created → scheduler fires at +45 min → policy passes → mock adapter ack → verifier confirms → audit log shows full chain.
- **Why:** the canonical demo of the full P1.E stack. Validates the architecture end-to-end before real-robot work.
- **How:** mock adapter + end-to-end test harness + canary entry.
- **Real-world precedent:** Kubernetes `kubectl run` end-to-end deployment.
- **Spec cycle path:** Phase 0 → Plan v1 → code (3-artifact OPTIONAL-Plan-v2 cycle).
- **D-decisions:** D1 MockAdapter class; D2 RobotCapability impl; D3 end-to-end test scenario; D4 `tests/test_p1_e5_oven_commitment_e2e.py`.
- **Pass-2 grep requirements:** all 3 parts.
- **14-gate checklist:** all 14 gates.
- **Success criteria:** test passes end-to-end. Latency from "shut off oven" utterance → commitment row created < 2 seconds. Latency from due_ts → mock adapter dispatch < 1 second.
- **Risks:** `maybe_handle_embodied_command()` integration into `pipeline.py` may surface conflicts with existing tool dispatch. Mitigation: structural invariant test `test_pipeline_does_not_import_any_core_embodied_module_except_entry_point` ratifies the single-seam.
- **Dependencies:** P1.E.1, P1.E.2, P1.E.3, P1.E.4.
- **Estimated time:** 1 week.

### P1.S — SDK + Capability Ontology v1.0

**P1.S.1 — `karaos-adapter-sdk` v0.1 published as separable package**

- **What:** New `karaos-adapter-sdk/` directory at repo root. `setup.py` + `pyproject.toml` for `pip install karaos-adapter-sdk`. Contents: capability protocol classes (RobotObservation, RobotCapability, ActionProposal, ActionResult, SafetyConstraint, TaskContext) imported from `cognition/specs/v0/python/`. MockAdapter as reference. Conformance harness stub (`karaos-adapter-sdk/conformance/runner.py`) ships in v0.1; tests added in v0.2.
- **Why:** Skeptic-2 §4 + Elon §3 Move 1 + Sundar §4. Spec-first sequencing per OCI/CNCF pattern. By end of P1, partners can `pip install karaos-adapter-sdk` and see the contract.
- **How:** standard Python package boundary. Apache 2.0 license file. `examples/` with mock adapter + reference adapter.
- **Real-world precedent:** OCI Runtime Spec v1.0.0 published before conformance suite GA. Kubernetes CRI/CSI/CNI published before runtime adoption.
- **Spec cycle path:** Phase 0 → Plan v1 → Plan v2 → code (HEAVY band — net-new package).
- **D-decisions:** D1 package structure; D2 v0.1 contract API; D3 mock adapter; D4 conformance runner stub; D5 README; D6 SemVer policy.
- **Pass-2 grep requirements:** all 3 parts; cross-package boundary enforcement.
- **14-gate checklist:** all 14 gates.
- **Success criteria:** `pip install karaos-adapter-sdk` works in fresh venv WITHOUT installing dog-ai core. MockAdapter implements every RobotCapability method per v0 spec.
- **Risks:** cross-package import boundary violations. Mitigation: AST invariant `test_adapter_sdk_does_not_import_core_dog_ai_internals`.
- **Dependencies:** P1.E.5 (RobotCapability spec stable).
- **Estimated time:** 1.5 weeks.

### P1.M — MCP server endpoint

**P1.M.1 — KaraOS MCP server (Decision 3.13)**

- **What:** New `core/embodied/mcp_server/` module. Exposes commit/list/cancel commitments + get_world_state + query_audit_log as MCP tools. Runs in interactive process (Decision 3.11) at well-known port. Apache 2.0 licensed.
- **Why:** Elon §3 Move 2 — MCP server is the GTM channel, ship in P1 not P4. Every MCP-aware client becomes a KaraOS frontend the day this ships.
- **How:** mcp-python library; tool surface mirrors commitment_db public API.
- **Real-world precedent:** Anthropic MCP protocol spec; ros-mcp-server family (complementary, not duplicative).
- **Spec cycle path:** Phase 0 → Plan v1 → code (3-artifact OPTIONAL-Plan-v2 cycle).
- **D-decisions:** D1 MCP server module; D2 tool surface; D3 protocol versioning; D4 conformance test against MCP spec.
- **Pass-2 grep requirements:** all 3 parts.
- **14-gate checklist:** all 14 gates.
- **Success criteria:** Claude Desktop / Claude Code / Cursor can call KaraOS commit_pending via MCP. Verifier_unavailable status code surfaces honestly when verifier not ready.
- **Risks:** tool surface ships before verifier registry is complete. Mitigation: explicit `verifier_unavailable` status code — honest stub > absent surface (Elon §3 Move 2 risk-if-we-do).
- **Dependencies:** P1.E.1 (commitment_db exists).
- **Estimated time:** 1 week.

### P1.R — TurtleBot4 reference adapter

**P1.R.1 — TurtleBot4 in Gazebo (ROS 2 LTS Humble/Jazzy)**

- **What:** New `karaos-adapter-sdk/examples/turtlebot4_adapter.py`. Maps RobotCapability → ROS 2 publish/subscribe via the local bridge process (Decision 3.8). Demo scenario: TurtleBot4 in Gazebo executes `walk_forward(1.0m)` commitment.
- **Why:** Sundar §1 + Conflict B resolution. TurtleBot4 is OSRF reference, $200 dev kit, ROS 2 LTS, ecosystem-recognized. Unitree G1 deferred to P3.
- **How:** ROS 2 setup in WSL2; `rclpy` in bridge process; gRPC IPC to KaraOS interactive process.
- **Real-world precedent:** TurtleBot 1/2/3/4 reference robots for ROS since 2007. Every ROS tutorial uses TurtleBot.
- **Spec cycle path:** Phase 0 → Plan v1 → Plan v2 → code (HEAVY band — first real ROS 2 integration).
- **D-decisions:** D1 ROS 2 setup; D2 bridge process; D3 gRPC contract; D4 TurtleBot4 adapter impl; D5 Gazebo scenario.
- **Pass-2 grep requirements:** all 3 parts.
- **14-gate checklist:** all 14 gates.
- **Success criteria:** end-to-end: user says "move forward 1 meter" → KaraOS commitment → policy passes → TurtleBot4 in Gazebo moves 1m → verifier confirms via Gazebo ground-truth → audit chain intact.
- **Risks:** WSL2 ROS 2 setup is unfamiliar territory. Mitigation: Phase 0 includes 1 day "spike" to validate `rclpy` install works in WSL2.
- **Dependencies:** P1.S.1, P1.M.1, P1.E.5.
- **Estimated time:** 2 weeks.

### P1 timeline (parallel tracks)

Week 0: P1.Phase0 (1 week)
Week 1-2: P1.A2 (agent consolidation) + P1.E.0 (eval bench) parallel
Week 3-4: P1.E.1 (commitment store) + P1.E.2 (scheduler) parallel
Week 5-6: P1.E.3 (verifier registry) + P1.E.4 (policy engine) + P1.S.1 (SDK) parallel
Week 7: P1.E.5 (mock adapter e2e) + P1.M.1 (MCP server) parallel
Week 8-9: P1.R.1 (TurtleBot4 in Gazebo)
Week 10: P1 canary week (validate everything against `to_be_checked.md`)

**Total P1: ~10 weeks (~2.5 months) with parallel tracks. Single-developer serial: ~16-20 weeks (~5 months).**

---

## SECTION 6: DEVELOPER / ARCHITECT / AUDITOR DISCIPLINE FOR P1

These rules ADD to the existing 15 doctrines + 14-gate checklist + architect-memory files. P1-specific only.

### For the Developer

1. **Mechanical-extraction discipline for P1.A2 agent consolidation.** No "while I'm here" cleanups during the mv operations. Every agent moves verbatim. P0.8 / P0.9.2 precedent applies.
2. **`maybe_handle_embodied_command()` is the ONLY seam.** No `core/embodied/*` module imports from `pipeline.py` directly. AST invariant `test_pipeline_does_not_import_any_core_embodied_module_except_entry_point` enforces.
3. **Every embodied action emits an `event_log` row.** Memory-write H12 hook applies. Audit chain MUST be reconstructible from event_log alone.
4. **Verifier disagreement is `failed_verification`, never silent retry.** Decision 3.10. AST invariant `test_no_silent_retry_on_verifier_disagreement`.
5. **AST invariants to add during P1:**

| Invariant | Scope | Catches |
|---|---|---|
| `test_no_module_level_side_effects_in_core_embodied` | `core/embodied/*.py` | Subprocess-spawn re-import side-effect leak (P0.S12 lesson applied to embodied) |
| `test_no_exact_equality_against_claim_confidence` | `core/reconciler.py` | MF7 regression |
| `test_session_snapshot_collection_fields_are_immutable` | `core/session_state.py` | MF8 regression |
| `test_cognition_specs_v0_files_marked_draft` | `cognition/specs/v0/*.py` | Premature v0 spec standardization |
| `test_robot_adapter_protocol_implements_capability_contract` | `karaos-adapter-sdk/*.py` | P1.R adapter regression |
| `test_no_motor_command_emission_from_cognition_layer` | `core/*.py` + `pipeline.py` | Cross-boundary scope creep |
| `test_durable_commitment_schema_versioned` | `commitment.db` schema | P1.E.1 migration |
| `test_verifier_registry_covers_every_skill` | verifier registry | P1.E.3 inverse-check |
| `test_no_silent_retry_on_verifier_disagreement` | dispatch chain | Decision 3.10 enforcement |
| `test_adapter_sdk_does_not_import_core_dog_ai_internals` | `karaos-adapter-sdk/*.py` | Cross-package boundary |
| `test_no_time_time_in_deadlines` | `core/*.py` + `pipeline.py` | MF4 (BUG-1) regression |
| `test_no_assert_in_production_code` | `core/*.py` + `pipeline.py` | MF5 (BUG-2) regression |
| `test_kara_os_profile_gates_agent_load` | `core/agents/` | P1.A2 regression |

6. **Forbidden patterns introduced in P1:**
- `time.time()` inside loop conditions or deadline computations (use `time.monotonic()`).
- `assert` in `core/*.py` / `pipeline.py` (use `if not cond: raise RuntimeError(...)`).
- `_log_q.put(...)` without bounded-queue overflow handling.
- `core/embodied/*` importing from `pipeline.py`.
- `cognition/specs/v0/*.py` without DRAFT header.

### For the Architect

1. **Every P1 sub-PR's Phase 0 audit cites the strategic alignment.** Per MF3 — CLAUDE.md "Project Overview" is the canonical scope reference.
2. **Every Phase 0 audit names D-decisions with `core/embodied/X.py:LINE` granularity (or `karaos-adapter-sdk/X.py:LINE`).** Doctrine #6 binds.
3. **New design review checkpoints specific to P1:**
- **C1 — Boundary check:** does this PR cross the cognition/embodied/adapter boundary? If yes, structural invariant must enforce the boundary.
- **C2 — Eval bench delta:** does this PR change action-class behavior? If yes, the PR includes an embodied_eval_bench delta report.
- **C3 — Verifier registry impact:** does this PR add or change a skill? If yes, the verifier registry adds an entry.
- **C4 — MCP tool surface impact:** does this PR change commit/list/cancel semantics? If yes, MCP server tool definitions are updated synchronously.
4. **ADR requirements specific to P1:** every P1.* track produces an Architectural Decision Record in `docs/adr/P1-<track>-<decision>.md`. Format per Michael Nygard ADR template. Each ADR cites the elevated doctrine that backs the decision (or the gap that motivated a new pattern).
5. **New approval gates:**
- **G1 — Spec lock approval:** `cognition/specs/v0/<dataclass>.py` requires architect sign-off before any consumer ships. Spec drafts can iterate; lock requires evidence of 1 reference adapter.
- **G2 — Adapter SDK release approval:** `karaos-adapter-sdk` v0.x release requires architect sign-off on (a) Apache 2.0 LICENSE present, (b) DRAFT headers in v0 specs, (c) SemVer policy documented, (d) no `core/dog_ai/` imports.
- **G3 — MCP tool surface approval:** every new MCP tool definition requires architect sign-off on (a) tool name follows convention `commit_*` / `list_*` / `cancel_*` / `get_*` / `query_*`, (b) parameters match capability schema, (c) `verifier_unavailable` status path tested.

### For the Auditor

1. **Pass-2 grep at every Plan v1 cycle.** 3-part (symbol-name + behavioral-semantic + symmetric-reject-preserve). The 5-application track record under doctrine #10 continues.
2. **Cross-package grep for `karaos-adapter-sdk`.** AST scan that no file in the SDK imports `dog_ai` or `core.*` (except via the published v0 specs).
3. **New audit checklist items for P1:**
- **A1 — Strategic alignment check:** every P1 sub-PR cites CLAUDE.md "Project Overview" and explains how this PR advances the strategic goal.
- **A2 — Apache 2.0 SPDX header:** every new Python file has the SPDX header. Auditor's Pass-2 grep flags missing headers.
- **A3 — Embodied eval bench delta:** every P1 sub-PR touching action surface emits a bench delta. Auditor's Pass-2 confirms the delta is non-zero on PR description.
- **A4 — Conformance impact:** every P1.S sub-PR documents whether it changes the SDK contract surface. SemVer bumps audited.
- **A5 — Decision 3.10 enforcement:** every P1.E.3+ sub-PR's verifier-disagreement path is tested with `tests/test_verifier_disagreement_yields_failed_verification`.
4. **P1-specific sign-off criteria:**
- **S1 — All Pre-P1 must-fix items closed** (MF1-MF10).
- **S2 — `KARAOS_PROFILE` config gate verified** (companion mode loads same agents as before P1.A2; robotics mode loads empty until P1.E adds; both mode loads union).
- **S3 — `pip install karaos-adapter-sdk` succeeds in fresh venv** (P1.S.1 acceptance).
- **S4 — End-to-end oven scenario passes** (P1.E.5 + P1.R.1 acceptance).
- **S5 — Embodied eval bench produces metrics for 10 mock + 5 Gazebo scenarios** (P1.E.0 acceptance).
- **S6 — Apache 2.0 LICENSE + GOVERNANCE.md + SPDX headers verified** (MF2 acceptance via grep).

---

## SECTION 7: CANARY CHECKLIST (TO BE APPENDED TO to_be_checked.md)

Per doctrine #9 (Canary-surfaces-real-gaps). Each entry matches the locked `tests/canary_week_2026-05-26.md` runbook format (Days 1-5 + triage Days 6-7).

### Post-Pre-P1 must-fix canary (Day 1 of P1 canary week)

```
## MF1-MF10 — Pre-P1 must-fix bundle (10 items)

Surfaces shipped:
- .github/workflows/{fast,slow,security}.yml — CI scaffold verified
- LICENSE (Apache 2.0) + NOTICE + CONTRIBUTING.md + GOVERNANCE.md at repo root
- SPDX headers in every Python file (`# SPDX-License-Identifier: Apache-2.0`)
- CLAUDE.md "Project Overview" rewritten to Layer D framing
- time.monotonic() in deadline computations (no time.time() in loop conditions)
- if not cond: raise pattern (no assert in production)
- _log_drain with _drain_failure_count + stderr fallback; _log_q bounded
- IdentityClaim.confidence_is_no_signal field + 3 site migrations
- SessionSnapshot.recent_voice_confs / core_memory / recent_attributions = tuple
- state.py:60 `**_persistent` wrapped in _persistent_lock
- everything_about_system/ split into part files

PASS signals:
- pytest tests/test_no_time_time_in_deadlines.py passes
- pytest tests/test_no_assert_in_production_code.py passes
- pytest tests/test_reconciler_no_exact_equality_against_claim_confidence.py passes
- pytest tests/test_session_snapshot_collection_fields_are_immutable.py passes
- python -O pipeline.py boots and fail-closed invariants still fire as RuntimeError
- Production canary day 1: zero "PermissionError 13" or "OSError: NTP" cascades in pipeline boot.

FAIL signals:
- Any AST invariant fires (regression on Pre-P1 fix).
- `python -O pipeline.py` allows invalid person_type through (assert was stripped, raise missing).
- Production canary: NTP correction during 30-second restart window produces premature vision degradation (BUG-1 regression).

Test scenario (canary-week observable):
1. Run pytest tests/test_pre_p1_hardening_invariants.py — all 13 invariants pass.
2. Run python -O pipeline.py + force a fail-closed invariant — confirm RuntimeError fires.
3. Day 1 solo Jagan session: zero regressions on existing P0.* canary entries.

Dependencies:
- All Pre-P1 must-fix items closed in single sub-PR sequence (MF1 → MF2 → MF3 → MF4-MF10).
```

### Post-P1.A2 canary (Day 1)

```
## P1.A2 — Agent consolidation under KARAOS_PROFILE config gate

Surfaces shipped:
- core/agents/companion/{prompt_pref,friction_detection,...11 files}.py
- core/agents/robotics/ (initially empty)
- core/config.py: KARAOS_PROFILE = "both"
- BrainOrchestrator gates agent registration by profile

PASS signals:
- KARAOS_PROFILE="companion" boots identically to pre-P1.A2 (11 agents loaded).
- KARAOS_PROFILE="robotics" boots with 0 companion agents loaded.
- KARAOS_PROFILE="both" boots with all 18 agents.
- Test suite at parity with pre-P1.A2.
- Canary: solo Jagan session behaves identically in "both" mode.

FAIL signals:
- Any import failure / circular import surfaces.
- Profile gate misses an agent (some companion agent loads under robotics profile).
- Test count drops by more than 5 (mechanical-extraction discipline violated).

Test scenario:
1. pytest --tb=no -q with KARAOS_PROFILE=companion — expect prior test count ± 5.
2. pytest --tb=no -q with KARAOS_PROFILE=robotics — expect tests that depend on companion agents to skip/error cleanly.
3. Day 1 solo Jagan session in companion mode: identical to pre-P1.A2 behavior.

Dependencies:
- Pre-P1 must-fix (MF1-MF10) closed.
- P1.Phase0 audit identifies every cross-class dependency.
```

### Post-P1.E.0 canary (Day 1-2)

```
## P1.E.0 — Embodied evaluation harness

Surfaces shipped:
- tests/embodied_eval_bench.py
- tests/embodied_eval_runs/ (gitignored)
- tests/eval_weekly.py extended for embodied bench
- tests/fixtures/embodied_scenarios/ (10 canonical mock-world scenarios)

PASS signals:
- python tests/embodied_eval_bench.py — produces metrics JSON for 10 scenarios.
- Metrics include action_grounding_accuracy, safety_gate_latency_p99, abstention_rate per scenario.
- tests/test_embodied_eval_bench_unit.py passes (pure-functions deterministic).
- Weekly eval extends to embodied bench; cron alert at ≥5pp drop.

FAIL signals:
- Bench takes > 30 minutes for 10 scenarios (latency budget exceeded).
- Metrics schema drift (action_grounding_accuracy missing from JSON).
- Mock-world non-determinism (run twice, get different metrics on identical scenarios).

Test scenario:
1. Run python tests/embodied_eval_bench.py — confirm metrics produced.
2. Run python tests/embodied_eval_bench.py again — confirm identical metrics (determinism).
3. Inject a regression in dispatch chain — confirm bench delta surfaces.

Dependencies:
- Pre-P1 must-fix.
- P1.Phase0 + P1.A2 closed.
```

### Post-P1.E.5 canary (Day 3-4)

```
## P1.E.5 — Mock adapter + first end-to-end embodied scenario

Surfaces shipped:
- core/embodied/mock_adapter.py
- maybe_handle_embodied_command() entry point in pipeline.py (single seam)
- tests/test_p1_e5_oven_commitment_e2e.py

PASS signals:
- E2E test: utterance → commitment_db row created → scheduler fires at due_ts → policy passes → mock adapter ack → verifier confirms → audit log shows full chain.
- Latency: utterance → commitment row < 2 seconds.
- Latency: due_ts → adapter dispatch < 1 second.
- Restart mid-pending → commitment recovers + fires at next opportunity.

FAIL signals:
- Any link in chain fails silently (no audit log entry).
- Verifier abstains when adapter ack arrives (disagreement protocol not wired).
- Mock adapter dispatched without policy engine consultation.

Test scenario (multi-person Day 3-4):
1. Jagan says "Shut off the oven in 45 minutes" — confirm commitment created (commitment_db.list_pending shows 1 row).
2. Fast-forward time (test mode) — confirm scheduler fires at due_ts.
3. Verify mock adapter receives ActionProposal + returns ActionResult.
4. Verify verifier reads MockWorld state + confirms.
5. Audit log query: events from utterance → commitment → policy → adapter → verifier → completed.

Dependencies:
- P1.E.0, P1.E.1, P1.E.2, P1.E.3, P1.E.4 all closed.
```

### Post-P1.S.1 canary (Day 4)

```
## P1.S.1 — karaos-adapter-sdk v0.1 published

Surfaces shipped:
- karaos-adapter-sdk/ (separate package boundary)
- karaos-adapter-sdk/setup.py, pyproject.toml, LICENSE, NOTICE, README.md
- karaos-adapter-sdk/karaos_adapter_sdk/__init__.py with v0 capability protocol classes
- karaos-adapter-sdk/examples/mock_adapter.py
- karaos-adapter-sdk/conformance/runner.py (stub)

PASS signals:
- Fresh venv: pip install ./karaos-adapter-sdk works without installing dog-ai.
- python -c "from karaos_adapter_sdk import RobotCapability, MockAdapter; m = MockAdapter(); print(m.list_skills())" works.
- conformance/runner.py --adapter karaos_adapter_sdk.examples.mock_adapter passes (stub returns 'no tests yet').
- AST invariant: no core/dog_ai/ imports in karaos-adapter-sdk/.
- LICENSE = Apache 2.0; SemVer policy documented.

FAIL signals:
- Cross-package import (karaos-adapter-sdk imports dog_ai core).
- v0 spec file missing DRAFT header.
- Conformance runner doesn't exit 0 cleanly.

Test scenario:
1. Fresh venv: pip install ./karaos-adapter-sdk — works.
2. Run conformance --adapter mock_adapter — exits 0.
3. From a separate Python process (not dog-ai), import + invoke MockAdapter — works.

Dependencies:
- P1.E.5 (RobotCapability v0 spec stable).
```

### Post-P1.M.1 canary (Day 4-5)

```
## P1.M.1 — KaraOS MCP server endpoint

Surfaces shipped:
- core/embodied/mcp_server/server.py
- core/embodied/mcp_server/tools/{commit,list,cancel,get_world_state,query_audit_log}.py
- MCP server starts in interactive process when KARAOS_PROFILE in {robotics, both}

PASS signals:
- MCP server starts on well-known port at boot.
- Claude Desktop with MCP client config can call commit_pending tool.
- Tool surface returns verifier_unavailable status code honestly when verifier not ready.
- AST invariant: tools advertised match implemented capabilities.

FAIL signals:
- MCP server fails to start.
- Tool returns malformed JSON.
- verifier_unavailable status code missing (would silently route to "completed").

Test scenario (stress + edge Day 5):
1. Boot pipeline with KARAOS_PROFILE=both.
2. MCP client lists tools — confirms commit_pending, list_commitments, cancel_commitment, get_world_state, query_audit_log all advertised.
3. MCP client calls commit_pending(skill="speak", payload={...}) — confirms 200 OK + commitment_id returned.
4. MCP client calls cancel_commitment(commitment_id) — confirms cancelled status.

Dependencies:
- P1.E.1 (commitment_db exists).
```

### Post-P1.R.1 canary (Day 5)

```
## P1.R.1 — TurtleBot4 in Gazebo (ROS 2 LTS)

Surfaces shipped:
- karaos-adapter-sdk/examples/turtlebot4_adapter.py
- WSL2 ROS 2 setup documented in karaos-adapter-sdk/examples/README.md
- Bridge process (rclpy ↔ gRPC) — `tools/karaos_ros_bridge.py`
- Gazebo world + TurtleBot4 model file

PASS signals:
- End-to-end: user says "move forward 1 meter" → commitment → policy → adapter → TurtleBot4 in Gazebo moves 1m → verifier confirms via Gazebo ground-truth → audit chain intact.
- Latency from utterance to motion onset < 5 seconds.
- Verifier abstains gracefully when Gazebo not running.

FAIL signals:
- ROS 2 bridge process crashes.
- Verifier silently passes when Gazebo reports incomplete motion.
- TurtleBot4 receives motor commands directly from KaraOS (boundary violation — adapter SDK contract should be the only path).

Test scenario (stress + edge Day 5, requires WSL2 + ROS 2 setup):
1. Boot KaraOS + Gazebo + TurtleBot4 model.
2. User says "move TurtleBot forward 1 meter" — commitment created.
3. Watch Gazebo: TurtleBot moves.
4. Audit log: confirms full chain.

Dependencies:
- P1.S.1, P1.M.1, P1.E.5.
```

### Day 6-7 — Regression diagnosis + bug-fix sub-specs

Per the locked `tests/canary_week_2026-05-26.md` runbook structure. Any FAIL signals trigger Phase 0 audit on a new follow-up spec under strict mode.

---

## SECTION 8: RECOMMENDED CHANGES TO future-execution.md

### 8.1 Add §4.5 "Lift required from current dog-ai/ codebase to v1"

**Section to change:** §4 (Existing System Context — Carry-Forward).
**Current:** Lists pieces to preserve and engineering disciplines to extend. Implies current code can be incrementally extended.
**Proposed:** Add §4.5 paragraph explicitly naming the 8 lifts (typed boundary, adapter SDK package, pipeline.py decomposition deferred to P2, durable commitment store, verifier registry, digital twin pre-validator, MCP server, two-process split). Each lift maps to a P1.* milestone or explicitly deferred to P2/P3.
**Reasoning:** TechAnalyst-1 §8.1 + Conflict 4 resolution. Implicit carry-forward narrative understates the lift; making it explicit prevents scope-creep mid-P1.
**Doctrine compatibility:** doctrine #6 (granular decomposition) supports — making the lift explicit is doctrine-aligned.

### 8.2 Strengthen §2.3 Brutal Scope Rule with hardware-test gates

**Section to change:** §2.3 (Brutal Scope Rule).
**Current:** Lists allowed and forbidden claims; transition between sim and physical is implicit.
**Proposed:** Add §2.3.1 "What constitutes 'physical-robot tested'" with explicit minimums: N=8 hours supervised operation across ≥3 distinct skills; M=50 skill executions; K=3+ verifier disagreements resolved; zero safety incidents.
**Reasoning:** TechAnalyst-1 §8.2 + Skeptic-1 §1 #4. Without explicit gates, the temptation to claim "works on a real robot" after one Gazebo demo is real.
**Doctrine compatibility:** doctrine #5 (Verification-before-completion) supports.

### 8.3 Tighten Decision 3.13 (MCP server interface) deployment shape

**Section to change:** Decision 3.13.
**Current:** Locks MCP server as first-class integration surface; doesn't specify which process hosts it.
**Proposed:** Clarify that MCP server lives in interactive process (Decision 3.11), runs on configurable port (default 8080), uses Apache 2.0-licensed `mcp-python` library. Communication with durable process via existing gRPC IPC.
**Reasoning:** TechAnalyst-1 §8.3. Without this, the "complementary not duplicative" framing vs ros-mcp-server collapses.
**Doctrine compatibility:** doctrine #14 (Spec-contracts-not-implementations) supports — MCP tool surface IS the contract.

### 8.4 Add Decision 3.15 — "Existing dog-ai code IS the first reference adapter"

**Section to change:** New Decision 3.15 in §3.
**Current:** §4 implies but doesn't state.
**Proposed:** Explicit decision: "The consumer-social-AI behaviors in current `core/brain.py` + `pipeline.py` are re-classified as ONE specific instantiation of the v1 cognitive runtime — a configuration that includes a face-vision sensor (RetinaFace), a Whisper STT sensor, an ECAPA voice sensor, an LLM-driven conversation skill, etc. Future ROS 2 robot adapters consume the SAME v1 surface with different sensor/skill bindings. The current code is an asset, not a constraint."
**Reasoning:** TechAnalyst-1 §8.4. MF3 strategic alignment decision.
**Doctrine compatibility:** doctrine #14 supports.

### 8.5 Update §6 reference-robot choice from Unitree G1 to TurtleBot4

**Section to change:** §6 (or wherever the reference robot is specified).
**Current:** Implicit Unitree G1 in Phase 4 per §2.4.4 mandatory differentiator #4.
**Proposed:** TurtleBot4 in Gazebo at end of P1 is the PRIMARY reference adapter. Unitree G1 in Gazebo deferred to P3 (when humanoid form factor matters for partner-channel signal).
**Reasoning:** Sundar §1 + Conflict B resolution. TurtleBot4 is OSRF reference, ROS 2 LTS, $200 dev kit.
**Doctrine compatibility:** No conflict.

### 8.6 Add Pre-P1 must-fix gate before Phase 0 starts

**Section to change:** §5 (or wherever phase plan lives).
**Current:** Phase 0 starts assuming current codebase state.
**Proposed:** Add explicit pre-condition: "P1 Phase 0 cannot start until Pre-P1 must-fix items MF1-MF10 are closed per `00-CEO-FINAL-P1-PLAN-2026-05-27.md` Section 4. The spec-first review cycle (Phase 0 → Plan v1 → Plan v2 → code) per CLAUDE.md doctrine #13 is the binding process protocol for P1."
**Reasoning:** TechAnalyst-1 §8.5. Spec-first discipline cited explicitly as a protocol, not a recommendation.
**Doctrine compatibility:** doctrine #13 (Spec-first review cycle) ratifies.

---

## SECTION 9: REAL-WORLD PRECEDENT SYNTHESIS

What the 7 analysts found about how other systems became standards. Cross-referenced against existing doctrines.

### 9.1 Architectural decisions

- **ROS 2 (cited by TechAnalyst-1, Sundar):** Typed messages + DDS transport + standard message packages + lifecycle nodes. Locked in 2017 at v0; iterated to multiple LTS versions. **Lesson for KaraOS:** publish the typed contracts (`cognition/specs/v0/`) BEFORE the runtime adoption window closes. Decision 3.6 + 3.9 supported.
- **MoveIt 2 (cited by TechAnalyst-1):** Planner-plugin API + MoveGroupInterface clients + configurable RViz + URDF/SRDF integration. Plugin architecture enables ecosystem. **Lesson for KaraOS:** the capability ontology v1.0 in `future-execution.md` §5 must be the framework contract; specific implementations (planner, verifier, adapter) are plugins.
- **LangGraph / AutoGen / CrewAI (cited by TechAnalyst-1, Sam):** State checkpointing via Postgres; explicit agent role typing. **Lesson for KaraOS:** durable commitment store IS the state checkpoint; per-skill verifier registry IS the role typing.
- **OCI / CNCF pattern (cited by Skeptic-2, Elon, Sundar):** Donate the spec to neutral foundation; standardize the image format BEFORE competitors can fork. Spec-first sequencing. **Lesson for KaraOS:** publish Adapter SDK + Capability Ontology v1.0 at END of P1, NOT Phase 7. Decision 3.9 sequencing is wrong-by-precedent.
- **Linux kernel CI (cited by TechAnalyst-1):** Every patch tested by 0day test bot + kbuild + kunit + syzkaller. **Lesson for KaraOS:** MF1 (CI scaffold) converts 28+ architect-advisory invariants into CI-enforced. Without this, every doctrine is dead weight.

### 9.2 Governance decisions

- **Kubernetes CNCF donation (Sundar §2.4):** Google donated K8s to CNCF in 2015 at v1.0. Removed Google control; made every cloud vendor safe to invest. **Lesson for KaraOS:** GOVERNANCE.md aspirational charter NOW. Foundation donation AFTER traction.
- **Docker → OCI (Sundar §2.3):** Docker Inc the company struggled; Docker the spec won. Foundation neutrality preserved the standard. **Lesson for KaraOS:** the Apache 2.0 LICENSE + DCO contributor model is the load-bearing decision.
- **React Patents Clause reversal (Sundar §2.5):** Facebook had to relicense React from BSD+PATENTS to MIT under public pressure. **Lesson for KaraOS:** pick Apache 2.0 BEFORE first partner conversation, not after.

### 9.3 Performance / quality bars

- **Production agentic eval (Sam §2.8):** Anthropic publishes SWE-bench; OpenAI ships system cards with per-task eval suites; Scale's business IS eval infrastructure. **Lesson for KaraOS:** P1.E.0 embodied eval bench is the table-stakes deliverable.
- **Physical Intelligence π0 (Sam §2.1):** 50Hz action chunks + flow-matching head + cross-embodiment training. Action chunks are the dual-rate split (System 2 cognitive at 1-5Hz, System 1 motor at 50-200Hz). **Lesson for KaraOS:** the adapter SDK must support chunked action sequences, not single actions.
- **Helix dual-system (Sam §2.4):** System 2 VLM at 7-9Hz + System 1 visuomotor at 200Hz. **Lesson for KaraOS:** KaraOS owns System 2; the adapter SDK delegates System 1 to the robot platform.

### 9.4 Ecosystem strategies

- **Kubernetes CRDs + Operators (Sundar §2.4):** Core stayed small; ecosystem extended via operators. Core = 1.5M lines; ecosystem = 30M lines. **Lesson for KaraOS:** the verifier registry, policy engine, MCP tool surface are the extension primitives. Capability ontology v1.0 expansion process must be community-friendly.
- **ROS 2 apt-package selectors (TechAnalyst-2):** `ros-humble-desktop` vs `ros-humble-ros-base` — same source, different artifacts. **Lesson for KaraOS:** `KARAOS_PROFILE` config gate per P1.A2.
- **30-minute onboarding (Sundar §2.7):** `docker run hello-world` in 60 seconds; `minikube start` in 5 minutes. **Lesson for KaraOS:** P1 must include "external developer first-run" tutorial. If a new developer can't install + run + see first commitment fire in 30 minutes, KaraOS is filtered out at first evaluation step.

### 9.5 Anti-patterns to avoid

- **PyTorch vs TensorFlow reversal (Sundar §2.5):** TensorFlow lost a 3x lead in 4 years due to (a) breaking changes betraying API stability, (b) worse developer experience, (c) closed governance. **Anti-pattern:** breaking changes in v0 specs without explicit DRAFT marker (mitigated by doctrine — DRAFT files explicitly named).
- **GCC GPLv3 → LLVM (Sundar §3.1):** GCC chose GPLv3 in 2007; commercial integrators chose LLVM BSD. **Anti-pattern:** AGPL/GPL licensing for middleware (mitigated by Apache 2.0 choice).
- **`ros-mcp-server` family (Elon §3 Move 2):** Layer C one-shot bridges with no state, no scheduling, no policy. **Anti-pattern:** competing at Layer C; KaraOS owns Layer D as durable orchestration.
- **AutoGen group-chat vs RoomOrchestrator (TechAnalyst-1):** AutoGen has peer-to-peer agent messaging; KaraOS's RoomOrchestrator is single-LLM-instance. **Anti-pattern:** assuming single-LLM-instance scales to multi-robot coordination. P1 must respect this constraint in adapter SDK design.

### New doctrines candidates (do NOT propose lightly — 3+ instance threshold)

- **License-and-governance discipline:** 1 instance (P1 MF2). NOT yet doctrine-elevation candidate. If subsequent strategic decisions (foundation donation in P3, governance amendments in P4) follow the same pattern of "decision artifact in repo + cross-doc consistency check," may elevate.
- **Spec-first sequencing for partner-facing contracts:** 1 instance (P1.S.1 Adapter SDK at end of P1). NOT yet doctrine-elevation candidate. If subsequent partner-facing contracts (MCP server in P1.M.1, conformance suite in P3) follow the same "publish at the right sequence not the easy sequence" pattern, may elevate.

---

## SECTION 10: STRATEGIC RISKS

Top 10 risks to KaraOS becoming the universal ROS 2 standard. Ordered by likelihood × impact.

### Risk 1: ROSClaw v0.2 ships with commitment storage before KaraOS Phase 1

- **Likelihood:** H
- **Impact:** H
- **Mitigation:** Ship P1 MVP in 8-10 weeks. Announce publicly (GitHub repo + Twitter + Hacker News post) at end of P1 to claim "durable cognitive middleware" framing first.
- **When to address:** During P1 (announce at P1 canary week close).
- **Doctrine cover:** doctrine #4 (Phase-0-catches-wrong-premise) — if ROSClaw ships first, Phase 0 of P2 surfaces the premise reset.

### Risk 2: 1X / NVIDIA / Figure ship vertical-lock cognitive stacks

- **Likelihood:** M
- **Impact:** H
- **Mitigation:** Position as OPEN partner middleware. 1X/Figure/NVIDIA are closed by design; robot makers wanting alternative come to KaraOS. Apache 2.0 + neutral governance is the signal.
- **When to address:** Pre-P1 (LICENSE + GOVERNANCE.md ship at MF2).
- **Doctrine cover:** None directly (governance is new discipline).

### Risk 3: MCP-for-robots standardization wave overtakes KaraOS

- **Likelihood:** M
- **Impact:** M-H
- **Mitigation:** Expose KaraOS itself as an MCP server (P1.M.1). Ride the protocol; don't fight it.
- **When to address:** During P1 (P1.M.1 ships in P1).
- **Doctrine cover:** None directly.

### Risk 4: NVIDIA adds Isaac Orchestrate layer above GR00T

- **Likelihood:** M
- **Impact:** H
- **Mitigation:** Be the open ROS-2-native alternative to NVIDIA's vertical-lock pattern. Apache 2.0 + multi-vendor TSC aspiration in GOVERNANCE.md.
- **When to address:** Continuous (monitor monthly per `future-execution.md` §2.4.3).
- **Doctrine cover:** None directly.

### Risk 5: Boston Dynamics + Google ship cognitive layer with Atlas

- **Likelihood:** L (industrial focus)
- **Impact:** M
- **Mitigation:** Stay consumer/multi-robot-maker focused; their lane is industrial.
- **When to address:** Continuous monitoring; no immediate action.
- **Doctrine cover:** None directly.

### Risk 6: Pipeline.py decomposition becomes a P1 distraction

- **Likelihood:** M (psychological pull from "tidy first" thinking)
- **Impact:** H (8-10 week strategic clock vanishes)
- **Mitigation:** Conflict A resolution: pipeline.py decomposition is P2. CEO + Architect enforce.
- **When to address:** Pre-P1 (MF3 strategic alignment update locks the framing).
- **Doctrine cover:** doctrine #4 (Phase-0 catches the wrong premise).

### Risk 7: Embodied eval bench is under-budgeted

- **Likelihood:** M
- **Impact:** H (without bench, every embodied PR ships on hope per Sam §3)
- **Mitigation:** P1.E.0 ships FIRST in P1.E track. Architect Phase 0 audit budgets 2-3 weeks.
- **When to address:** Week 0-2 of P1.
- **Doctrine cover:** doctrine #9 (Canary-surfaces-real-gaps).

### Risk 8: Verifier registry abstention protocol has no production precedent

- **Likelihood:** M
- **Impact:** M
- **Mitigation:** Prototype against MockWorld in P1.E.3; iterate before Gazebo in P1.R.1.
- **When to address:** Week 5-6 of P1.
- **Doctrine cover:** doctrine #14 (Spec-contracts-not-implementations).

### Risk 9: WSL2 ROS 2 setup is unfamiliar territory; P1.R.1 slips

- **Likelihood:** M
- **Impact:** M
- **Mitigation:** Phase 0 of P1.R.1 includes 1 day spike to validate `rclpy` install works in WSL2.
- **When to address:** Week 7-8 of P1.
- **Doctrine cover:** doctrine #4 (Phase-0-catches-wrong-premise).

### Risk 10: Canary week surfaces multi-track regression

- **Likelihood:** H (multi-track parallel landings always surface regressions)
- **Impact:** M
- **Mitigation:** 1-week canary week at end of P1 with Day 6-7 dedicated to regression triage. Each PR's structural-invariant tests are in CI per MF1.
- **When to address:** Week 10 of P1.
- **Doctrine cover:** doctrine #9.

---

## SECTION 11: CEO FINAL DIRECTIVE

Jagan,

**Where KaraOS stands today.** You have built the best household-companion cognition layer in 2026 open-source. 2810 passing tests, 15 elevated doctrines, the 14-cycle P0.R resilience-track arc closed clean, P0.S10 (the 6-artifact deepest-absorption cycle in project history) shipped without regressions. The discipline is real. The doctrines are load-bearing. The fact that you applied 15 distinct doctrines + 14 quality gates + 3-part Pass-2 grep across 110 strict-mode applications and 32 successful closures is structurally remarkable for a single-developer codebase. You should be proud.

But the strategic goal — "every ROS 2 robot should use only our system" — is a Layer D claim, and the system you built is currently a Layer F sample (consumer humanoid UX). The gap is real. Eight of nine standard-making criteria score ABSENT (per Skeptic-2's rubric in Section 1 of this plan). Zero ROS 2 integration. Zero adapter. Zero partners. Zero published license. Zero foundation. The cognitive substrate is real and disciplined; the robotics product is not yet code. Reaching the strategic goal from where you stand requires LANDING THE STANDARD-FORMATION PREREQUISITES, not refactoring pipeline.py.

**What the next 60-90 days demand.** Ship Pre-P1 must-fix in the next 7 days (CI scaffold + Apache 2.0 + strategic alignment + 7 bug-census fixes). Run the P1 cycle for 8-10 weeks landing the embodied runtime (commitment store + scheduler + policy + verifier + mock adapter + TurtleBot4 reference in Gazebo + MCP server endpoint + Adapter SDK v0.1 published at end of P1). Defer pipeline.py decomposition to P2 (it is real debt but it does not gate the Layer D claim per Elon's §3 Move 3 read of the integration seam). Run a 1-week canary at the end of P1. The strategic clock is 8-10 weeks before ROSClaw v0.2, NVIDIA Isaac Orchestrate, or an MCP-for-robots wave forecloses our Layer D position.

**Non-negotiables for this phase.** (1) The 15 elevated doctrines + 14-gate checklist + 3-part Pass-2 grep + spec-first review cycle bind every P1 sub-PR. No exceptions for "obvious refactors." (2) Apache 2.0 license + GOVERNANCE.md aspirational charter + SPDX headers ship in Pre-P1 must-fix. No "license decision later." (3) `maybe_handle_embodied_command()` is the ONLY seam between embodied and pipeline.py. AST invariant enforces. (4) Every embodied action ships through policy engine + verifier registry + audit log. No silent retries on verifier disagreement. (5) Embodied eval bench ships FIRST in the P1.E track, before any embodied code lands.

**Honest feasibility assessment for the strategic goal.** The goal is achievable but NOT in the form Jagan currently imagines. "Every ROS 2 robot should use only our system" requires 3-5 years of community-and-ecosystem work, not 8-10 weeks of P1. What P1 CAN deliver is the architectural prerequisites: Apache 2.0 license + Adapter SDK boundary + reference robot working in Gazebo + MCP server endpoint + per-skill verifier registry with abstention protocol. P1's job is to NOT FORECLOSE the standard path. The standard ITSELF gets won by adoption, partner integrations, governance maturity, and ecosystem extension over multiple years. Per Skeptic-2's brutal honesty in this plan's Section 3 — KaraOS as currently planned will not become THE universal ROS 2 standard; it will become a USEFUL Layer D middleware that one or two robot OEMs license. That is still a category-winning outcome IF the prerequisites are landed correctly. Reaching it requires accepting the honest framing: the goal is the direction, not the deliverable. P1 ships the prerequisites.

**The single most important thing to hold firm on.** The Adapter SDK must publish at end of P1, NOT at Phase 7. This is the load-bearing strategic decision. `future-execution.md` Decision 3.9 has it 6 months late. Every successful infrastructure standard in the cited precedent set — OCI, Kubernetes CRI/CSI/CNI, ROS 2 RMW, React JSX, LLVM, MCP — published the integration contract BEFORE the runtime adoption window closed. Partners begin work against the spec while v1 is being written. If KaraOS publishes the SDK at month 9-12, OpenMind OM1, ROSClaw, NVIDIA Isaac, and the MCP-for-robots wave will have eaten the partner channel. The 8-10 week mitigation window in `future-execution.md` §2.4.3 does NOT survive an architecture-debt cycle first. Spec-first sequencing IS the discipline that turns the technical thesis into a standard. Hold firm on this. Everything else can adjust.

— KaraOS-CEO
2026-05-27

---

*This plan was synthesized from 7 Wave-1 analyst reports (TechAnalyst-1, TechAnalyst-2, Skeptic-1, Skeptic-2, Elon, Sundar, Sam), grep-verified against the 15 elevated architectural doctrines in CLAUDE.md, the 14-gate quality checklist, the 3-part Pass-2 grep operational rule, the per-spec process artifacts at `tests/p0_s10_*` and `tests/canary_week_2026-05-26.md`, the strategic context in complete-plan.md / future-execution.md / to_be_checked.md / everything_about_system.md, and the operational discipline files at `C:\Users\jagan\.claude\projects\C--Users-jagan-dog-ai-dog-ai\memory\`. Every claim about KaraOS state was verified against the actual codebase at `C:\Users\jagan\dog-ai\dog-ai\` per the GROUND TRUTH RULE.*
