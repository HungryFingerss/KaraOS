# Built with AI

How KaraOS was actually built. Not a methodology essay — a record of one solo developer collaborating with Claude (Anthropic's frontier model) under explicit discipline, demonstrated against a real codebase.

---

## Premise

Most "I build with AI" stories fall into two failure modes. The first is *AI as code generator*: "Claude wrote this for me." The output is plausible but brittle, the developer has no model of why the code is shaped the way it is, and every bug is an exercise in re-prompting until something passes. The second is *AI as chat assistant*: useful for asking questions, but the actual code is still written line by line by the human, and AI is just an autocomplete with a personality.

Neither describes how this project was built.

KaraOS is built by Claude in three distinct roles — **architect**, **auditor**, and **developer** — coordinated by one human (me). The roles correspond to actual conversations in different contexts, with different prompts, different focus, and explicit hand-offs between them. The disciplines that make this work are reusable and documented. The codebase is the artifact that proves they work.

This document covers the workflow, the four banked architectural disciplines that have emerged, and a worked example tracing one sub-PR — the deletion of a 270-line legacy voice-routing function and its replacement with a rule-cascade-based reconciler — from initial spec through implementation. It is intentionally not exhaustive; the goal is to demonstrate that the discipline produces reliable outcomes, not to teach every variant.

---

## The three-role discipline

### Architect

Writes phase specs. Defines invariants that must hold (the contract). Does not prescribe implementation details (the code shape). Each multi-day sub-PR starts with a **Phase 0 audit**: pure documentation, grep-verified findings, zero production-code changes. Surfaces decisions before any test is written.

The architect's outputs:
- `tests/p0_X_inventory.md` (or audit equivalent) — what's currently there, what's affected
- `complete-plan.md` entries — the high-level work breakdown
- Phase specs with locked D1-Dn architectural decisions
- Plan v1 → v2 documents incorporating auditor feedback

The architect *never* writes test code or production code directly during a Phase 0 audit. Holding this discipline is what makes Phase 0 surface decisions cleanly — the moment you start coding, you commit to mechanism, and mechanism leaks back into the spec.

### Auditor

Independent review pass before sign-off. Reads the architect's Plan v1, asks questions the architect would not ask of their own work, locks decisions explicitly. The architect-auditor distinction matters because the same person playing both roles tends to defend their own assumptions; an auditor in a separate conversation context, reading the plan cold, is more likely to catch wrong premises.

The auditor's outputs:
- D1-Dn decision sheets with options and recommendations
- Plan v1 review with explicit concerns and approvals
- Plan v2 review with refinement requirements
- Joint sign-off (or rejection) before code starts

In practice, auditor and architect are sometimes the same Claude conversation, but always with explicit framing: "Now switching to auditor role. Read this Plan v1 as if you didn't write it." The discipline of role-switching is what catches issues; the human (me) enforces the boundary.

### Developer

Implements against the contract. Surfaces better mechanisms when careful reading reveals them. Flags every deviation from spec in the closure report so the architect/auditor can review whether the deviation is principled or scope creep.

The developer's outputs:
- Code (production + tests)
- Closure reports per sub-PR with explicit "what shipped vs what was spec'd" sections
- Documented mid-flight improvements (the "developer improves on spec" pattern)

The developer is given **the contract, not the code shape**. When the spec says "every paired write must have a sentinel and SQL-first ordering," the developer chooses the sentinel pattern, the function name, the call sites. When the developer reads the spec carefully and finds a better mechanism (4 instances documented below), they implement the better mechanism and flag it in the closure.

---

## The four banked patterns

Each pattern below has a multi-cycle empirical track record. Patterns are "banked" — elevated from recurring practice into named architectural discipline in the project's working-memory file — once they reach a track record of at least 4 instances and produce demonstrably better code than not having them.

### 1. Induction-surfaces-invariant-gaps

**The discipline:** every structural invariant ships with an induction protocol that deliberately exercises the failure mode it is meant to prevent. The induction is the test of the invariant, not the test of the production code. When induction surfaces a gap (either in the invariant's coverage or in production code), the gap is closed in the same cycle, not deferred.

**Track record (7×):**

- **Store-pattern migration closure** — 8 deliberate-regression checks induced field-drift, unenumerated-writer, paired-write-atomicity, producer-copy, peek-not-mutate, ratchet-bypass, autouse-fixture-coverage, and prior-state-guard violations across 8 typed Store classes. All 8 fired correctly with useful error messages.
- **Tool-timeout structural invariants** — induced a synchronous `.execute()` loop without `await asyncio.sleep(0)` checkpoint (would break transaction rollback on `wait_for` cancellation) and flipped `include_tools=False` → `True` on the retry path (would re-enable tools recursively). Both AST-based invariants fired correctly.
- **Atomic-replace for shared dict (`_persistent`)** — three deliberate-regression checks; the third surfaced a detector gap (attribute-form access from external modules wasn't caught alongside bare-name access in the owning module). Detector strengthened in the same cycle to scan both shapes.
- **Brain LLM JSON parser hardening** — Hypothesis property-based tests (1000 examples per test) induced two real production bugs: `_parse_json` returned non-dict types on valid scalar JSON (contract violation), and `_parse_intent_sidecar` didn't catch Python 3.11+ `ValueError` on oversized integer strings (DoS vector). Both fixed in the same sub-PR with regression tests pinned to the falsifying inputs.
- **Caller-audit downstream regression catch** — auditing every caller of the parser hardening above surfaced one real downstream regression (a list-shape branch became unreachable after the parser's contract was narrowed). Fix landed in the same cycle via a sibling `_parse_json_array` parser preserving the old contract for that one call site.
- **Event-log fixture coverage gate** — a round-trip test asserting every event_type in the closed registry deserializes correctly surfaced one event_type (`presence_state`) missing from the canonical scenario fixtures. Added to the relevant scenario builder in the same cycle. The induction was an exhaustive-set coverage check, not a behavior probe — and it caught a real omission before the fixtures shipped as reusable test infrastructure.
- **Full-suite verification catches subset-blind regression** — Steps 4-5 of the event-log work claimed "no regressions" based on a subset run that excluded the silent-except invariant test. Full-suite verification surfaced 12 P0.4 silent-except violations at the producer-hook surface. Fix consolidated into a single annotated swallow helper (see developer-improves-on-spec instance below) in the same cycle. Process lesson banked: subset verification is necessary but not sufficient.

**Operational rule:** mid-flight production fixes from induction findings are NOT scope creep — they are the protocol working. The whole point of inducing a violation is to find out whether the test catches it; if the test catches a real bug while you're at it, that's the discipline paying its rent.

### 2. Spec-first review cycle

**The discipline:** for sub-PRs estimated > 1 day, the workflow is: Phase 0 audit → D1-Dn decisions surfaced → Plan v1 → architect/auditor review → Plan v2 → code. Phase 0 is grep-verified findings reported BEFORE any test code is written; Plan v1 is the first complete spec; architect/auditor feedback drives a Plan v2 revision before any code lands.

**Track record (6-for-6 across multi-day sub-PRs):**

- **Store-pattern migration** — retired 28 module-level mutable globals in pipeline.py and replaced them with 8 typed Store classes (`asyncio.Lock`-guarded async mutators, sync `peek_*` reads, atomic snapshots). +362 tests across the arc.
- **Typed session state foundation** — replaced the pre-existing `_active_sessions: dict` with a typed `SessionStore` + frozen `SessionSnapshot` immutable views, with structural invariants enforcing single-writer discipline and no-raw-dict-leak across the entire pipeline.
- **Per-tool timeout protection** — every LLM-callable tool handler wrapped in `asyncio.wait_for` with per-tool wall-clock budgets and cancellation-safe partial SQL rollback; covers dispatch-routed tools AND inline tools (Tavily web search).
- **Schema-migrations versioning** — versioned migration ledger across all 3 SQLite databases (faces.db, brain.db, classifier_scenarios.db); 19 historical schema mutations retrofitted into the ledger; bootstrap routine handles fresh / legacy-fully-migrated / partially-migrated DB shapes; live-production-DB validation gate before legacy idempotency paths deleted.
- **Reconciler legacy-router deletion** — deleted a 270-line legacy voice-routing function and its 54 direct-call tests, replaced with a rule-cascade reconciler under structural invariants. Phase 0 audit caught the wrong premise before code was written (see worked example below).
- **Event log + replay harness** — full event-sourcing foundation across 9 staged steps. Phase 0 boundary audit → Plan v1 with locked D1-D8 decisions → Plan v2 with R1-R5 mid-spec refinements → code phase. 12 typed payload dataclasses, exactly-one-producer-per-event-type AST invariant, 11 producer hooks at 12 sites, read-only replay CLI, reusable scenario fixtures consumed by the next sub-PR's regression tests, health-log integration via observability counters.

**Spec-time investment pays back 2-4× in mid-flight rework avoided.** Every cycle that skipped the Phase 0 audit hit larger surprises. The reconciler refactor specifically saved an entire spec-cycle of rework — see the worked example below.

### 3. Spec-contracts-not-implementations

**The discipline:** architect specs describe **what invariants must hold** (the contract), not how to satisfy them (the implementation). When a spec prescribes implementation details, it forecloses the developer's mechanism-discovery loop and reliably produces worse code than necessary.

**Why this works:** the developer has full visibility into the actual code, runtime state, surrounding patterns, and adjacent constraints the spec author cannot pre-load. Specs that lock contracts let the developer's local knowledge improve the mechanism; specs that lock mechanisms turn the developer into a transcription typist.

**Concrete examples:**
- Contract: *"every paired-write site must use a `_mark_X_dirty()` sentinel before the cross-storage write"*. Implementation: which file, which exact name, which line — developer's call.
- Contract: *"the divergence-logging trigger fires when the firing rule isn't in the expected-rule set for the utterance's duration band."* Implementation: where the expected-rule mapping lives, what data type it is, what the data flow looks like — developer's call. In this case the mapping ended up colocated with the rules it describes (in the reconciler module), not inline in the consumer pipeline.

### 4. Developer-improves-on-spec-by-reading-carefully

**The discipline:** when implementation reveals a better path that preserves the spec's architectural intent, bank the improvement explicitly in the closure report so the architect/auditor sees the deviation + rationale.

**Track record (5-for-5):**

- **Internal-contract recognition in retry-path invariant** — spec named external call sites as the invariant target ("every caller of the retry function must pass `include_tools=False`"). Developer's caller audit found the actual contract was internal — the retry function doesn't accept `include_tools` as a parameter by design; the override happens inside the function body when it calls a deeper LLM helper. Developer rewrote the invariant to verify the internal contract directly. Strictly stronger guarantee.

- **Self-evolving schema-migration ledger initializer** — spec sketched a fresh `init_ledger()` function for the new versioned-migration table. Developer made it self-evolving: idempotent `ALTER TABLE` adding the `is_initial` column to pre-existing ledger tables. This way one DB that already had an older ledger from a prior single-DB experiment got upgraded automatically on first boot rather than requiring a separate meta-migration. Avoided a chicken-and-egg recursion the spec didn't anticipate (a migration that fixes the migration system).

- **Split verification function for data-backfill migrations** — spec defined migrations as 4-tuples `(version, description, apply, verify)`. Developer split `verify` into `verify_post` (runner uses after the migration applies, asserts the post-condition) and `verify_present` (bootstrap uses to detect "is this already done on a legacy DB?"). For schema-only migrations these collapse to the same predicate; for data backfills they diverge sharply — conflating them would let bootstrap stamp `is_initial=1` on a partially-backfilled DB, and the runner would never finish the data migration. Real correctness issue, developer-caught.

- **Band-divergence retargeting in reconciler shadow-log** — spec said *"extend the existing divergence-log block with more fields, don't change the trigger condition."* The reconciler-deletion plan would remove the legacy variable that the existing trigger compared against, so the original trigger becomes unworkable. Developer retargeted to band-divergence detection (firing rule not in expected-rule set for the utterance-duration band), preserving the gate criteria semantically while making the check independent of the legacy code being deleted. Architecturally cleaner than the spec.

- **Swallow-helper consolidation across producer-hook surface** — auditor's structural-invariant remediation prescribed annotating each of 12 per-call-site try/except blocks at the producer-hook surface with the `# OPTIONAL:` annotation that satisfies the silent-except invariant. Developer instead consolidated to a single `safe_emit_sync(...)` helper carrying one annotated except, with all 12 hook sites delegating to it. 12 violations collapsed into 1 annotated except + 12 unannotated call sites; future hooks automatically inherit the swallow-discipline without an annotation step. Same shape as a prior `_TOOL_HANDLERS` consolidation in the per-tool timeout work — strictly better than the patch the auditor proposed.

This pattern emerges *because* of the spec-contracts-not-implementations discipline. If the spec locked mechanism, the developer couldn't propose better mechanism without violating the spec. Pairing the two disciplines is what makes the developer's careful-reading useful instead of insubordinate.

---

## A worked example: deleting a 270-line legacy voice-routing function

This is the single largest spec-cycle save in the project's history. The premise of the entire phase turned out to be wrong, and the Phase 0 audit caught it before any code was written. The trace below is the actual workflow, slightly compressed.

### Phase 0 audit (the save)

**The premise going in:** the codebase had two voice-routing implementations running side-by-side. The old one was a 270-line function with a multi-priority decision tree, written incrementally over months of live-canary feedback. The new one was a rule-cascade where each rule was small, named, and independently testable. The codebase had already migrated to the new one via a feature flag; the old one was still around as a fallback. The plan: validate that the new reconciler covered every decision the legacy function used to make, delete the legacy function, declare victory.

**The audit ask:** enumerate every code path that can dispatch a routing action, trace "Bug-W" (a recent live-canary failure where the user saying "Thank you." in a 0.45-second utterance caused the system to incorrectly open a phantom new-stranger session), classify every legacy decision branch as KEEP (carry forward), DROP (pre-existing bug, don't preserve), or REVISE (intent correct, implementation needs work), and surface architectural decisions for joint review.

**What the audit found:**

The premise was wrong. Bug-W was not a residual legacy-function bug. Bug-W was in the **new reconciler** — specifically a coverage gap in the 0.3-0.5 second utterance-duration band that the legacy function had been incidentally papering over.

Concretely: the new reconciler's Priority-0 rules collectively gate the "hold current speaker session on a short utterance" behavior behind one of two preconditions:

- `utterance_duration < 0.3s` (pure-noise floor) — fires a "hold current" rule
- `utterance_duration ≥ 0.5s` (minimum-audio-for-scoring) — fires a "short-utterance mismatch" rule

The 0.3 – 0.5 second band had no Priority-0 rule. The legacy function's catch-all return-current default at the bottom of its decision tree had been covering this gap. When the previous cutover to the new reconciler removed the legacy function's broader 1.0-second floor, the gap got exposed.

If the original simple-deletion plan had been written without the Phase 0 audit, here's what would have happened:

1. Delete the legacy function
2. Ship against the new reconciler
3. Re-introduce Bug-W in production (since the new reconciler is its source)
4. Require a Plan v1.5 rework to add the gap-fill rule retroactively
5. Re-validate against live traffic

The audit prevented all of that. The plan that actually shipped includes a new gap-fill rule covering `0.3 ≤ utterance_duration < 0.5` as a **prerequisite** before the deletion, plus a Bug-W regression test pinned to the exact canary failure signature.

### Decision locking

After the audit landed, eight architectural decisions were surfaced for joint architect + auditor review. The most consequential ones:

- **Deletion scope**: AST scan confirmed only one code path produced the routing action variable, so simple deletion of the legacy function would work cleanly once the prerequisite gap-fill rule was in place.
- **Bug-W disposition**: ship the gap-fill rule + a Bug-W regression test in the same pull request as the legacy deletion (not as a follow-up). The bug is the divergence the shadow-window validation was supposed to catch; shipping the fix together makes the legacy deletion safe.
- **Gap-fill rule scope**: cover the precise 0.3 – 0.5 second band (minimal behavior change), not the wider 0.3 – 1.0 second band the developer initially proposed. The wider band would have overlapped with existing rules in 0.5 – 1.0 s and suppressed them, creating order-dependence the codebase didn't need.
- **Rollback plan**: keep the feature flag alive for a 7-day live-traffic validation window before fully deleting the shadow infrastructure in a follow-up PR.

Each decision had 2-4 explicit options with trade-off rationale. The auditor's pushback on the gap-fill scope (refining from 0.3-1.0s to 0.3-0.5s) is an example of the auditor role catching an over-broad mechanism choice before code starts.

### Plan v1 → Plan v2

Plan v1 covered the work in five blocks: the new gap-fill rule, a structural fail-safe for the case where the cascade returns nothing (defense in depth against future refactors), the extended divergence-log block in shadow mode, test-count reconciliation, and a separate validation-runbook file.

Auditor review surfaced five precision items — most notably that the ordering invariant test catches mis-order but not coverage gaps (the discipline of "catch mis-order in CI, catch coverage gaps in human review") — and two sub-decisions on mechanism choice. Plan v2 incorporated all five, plus the sub-decisions. Joint sign-off followed.

### Implementation

Two phases of code work:

- **Phase 1** (+35 tests): the new gap-fill rule, the Bug-W regression test, lower-bound attributes on every Priority-0 rule, the rules-ordering structural invariant test, the fail-safe behavior when the cascade returns nothing, the extended shadow-log format.
- **Phase 2** (+4 tests, -54 deleted legacy tests): the 270-line legacy function deleted, the 54 direct-call tests deleted with it, replaced with the structured rule-cascade behavioral suite already shipped in Phase 1.

Net result: -15 tests in raw count but +40 architectural-coverage tests added. Coverage shifted from "legacy 270-line function tests" to "rule cascade + contract invariants + per-rule behavioral tests." A raw test count alone is a misleading metric for a legacy-deletion phase.

### Mid-flight improvement

Plan v2 said *"extend the existing divergence-log block with more fields; don't change the trigger condition."* But the deletion plan would remove the legacy variable that the existing trigger compared against, so the trigger would have nothing to compare against post-deletion.

The developer caught this mid-implementation and retargeted to band-divergence detection: each critical utterance band (gap, short-hard) has an expected-rule set; if a different rule fires in that band, the divergence is logged. This is the 4th instance of the developer-improves-on-spec pattern. Architecturally cleaner — the band-divergence check is a *positive* contract (encoding expected coverage per band), not a *negative* comparison (disagreement with legacy code that's about to be deleted anyway).

The architect's Plan v2 had an internal inconsistency. The developer's careful reading caught what the spec-cycle review missed. The architect's review of Plan v2 didn't catch it. The auditor's review of Plan v2 didn't catch it. The developer caught it during implementation and resolved it correctly.

**This is the discipline's load-bearing claim:** the spec-first cycle isn't about producing a perfect spec; it's about producing a spec good enough that the developer's careful reading catches the residual issues. Specs that lock contract rather than mechanism are the format that makes this work.

### Validation window

After Phase 2 closed, a 7-day validation window opened with the feature flag still alive and the shadow infrastructure still logging. Gate criteria, locked in a separate runbook file: at least 100 routing decisions OR at least 14 calendar days (whichever is later), zero divergence in the gap band, zero divergence in the short-hard band, zero firings of the structural fail-safe. Closure of the validation window unlocks a follow-up PR that deletes the shadow infrastructure, the feature flag, and the fail-safe along with their tests.

This is the **live-validation gate discipline** — pytest-green is necessary but not sufficient for schema migrations or router refactors. Real production data running against the new path is the actual evidence.

---

## What this isn't

A few honest limitations worth naming explicitly:

- **Not autonomous AI development.** Every spec, every decision lock, every closure review is done by me reading carefully and pushing back. Claude doesn't decide what to build next; Claude decides how to build what I've decided to build next. The architect/auditor/developer roles are mechanisms for forcing me to think clearly, not for delegating thinking.
- **Not robotic embodiment today.** KaraOS is a working cognitive layer running on consumer hardware in a household. Robot integration is the roadmap. The two-layer architecture in [`ARCHITECTURE.md`](ARCHITECTURE.md) is accurate about what's done and what's planned.
- **Not deployed at scale.** The 4,237-test suite, the live multi-person canary sessions, and the published-benchmark validation are all in a single-household development context. Scale validation is future work.
- **Not production-deployed-to-strangers.** The privacy-tier model is designed for one's own household; deployment to homes I don't control would require additional security work I haven't done.

The strength of this project is not its scale or its claim to physical embodiment. The strength is the engineering discipline that produced it and the verifiability of every architectural claim.

---

## Links and deeper material

- [`README.md`](README.md) — system overview + external benchmark validation
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — two-layer view, component-level walkthrough, engineering discipline, deployment notes
- [`terminal-logs/`](terminal-logs/) — live session captures; paste any one into an LLM and ask "how does this work?" — modern frontier models can reconstruct the architecture from these alone
- [`published-papers-tests/results/RESULTS.md`](published-papers-tests/results/RESULTS.md) — three-run benchmark journey on the *Speak or Stay Silent* paper (Bhagtani et al. 2026), full methodology and honest caveats

For selected Claude transcripts demonstrating the workflow in action (Phase 0 audits, decision locking, joint sign-off cycles, mid-flight improvements), contact me directly — see `README.md` for contact info.
