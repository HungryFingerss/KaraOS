# Auditor — Gates & Precision Items

## The gate ladder
- **Phase-0 gate** — verifies the audit's grep-verified findings against disk; tests the premise, the scope, the decision surface. Outcome: GREENLIGHT to Plan v1 (with rulings on auditor-owned D-items + PIs for the plan to absorb).
- **Plan-vN gate** — the independent Pass-2 grep (`### Pass-2-grep-auditor-verified-before-Plan-v1-approval`, elevated doctrine): re-grep the plan's enumeration; convergence = no PI (clean cycles validate ABSENCE of drift); divergence = a PI (caught cycles validate PRESENCE of the catching layer). Both modes are the doctrine working. Zero-PI v1 → OPTIONAL-Plan-v2 (ship straight to the developer); PIs → vN+1 REQUIRED, absorption-scoped ("nothing else in the design moves").
- **Closure-audit** — every stated gate condition re-verified from fresh reads; the verdict names what is RATIFIED vs FORWARDED (the architect's run-half). GREENLIGHT releases the commit; the explicit verdict keeps the 4-step cycle intact.

## Precision-item discipline
- **A PI is grep-verified before it ships** — a PI is an accusation with evidence: the site, the line, the failure mode it causes, the doctrine lineage, and the exact absorption required. The SB.9 PI-2 is the model (the site, why it's load-bearing for §7.4, why it can't move to flow-ownership, the three-part fix).
- **Classify PIs honestly**: load-bearing (blocks banking — the twelfth registry) vs non-blocking absorptions (the denominator refinement) vs watch-items (the n4b flattening note) vs banked observations (no action, taxonomy only). Architect-surfaced questions WITH leans are NOT PIs.
- **Sequencing rulings**: some deliverables cannot precede their inputs — bands are computed FROM the committed baseline, not set at Phase 0; the ruling names the ordering, not just the value.
- **Granularity rulings**: thresholds respect the quantum of the thing measured (the ≥2pp floor because one case ≈ 1.8pp — a band below one-case granularity fires on legitimate rebaselines).
- **Gate the RULE, not the integer** — closure criteria are self-defining rules verified at audit time against the actual artifact; a pre-blessed magic number drifts and then either false-fails or silently blesses.

## Non-vacuity rulings (the auditor's signature move)
- **The distinguishing-cell condition**: a two-reference/two-pack proof where both references trace IDENTICALLY proves nothing — each contract's walkthrough must exercise the cell that separates the references (on-demand vs streaming; informational vs physical; two flows, one hook), PAIRED with the uniformity half (the floors identical across both). The SB.8 A2/A4 pairing, generalized.
- **Two-axis gates never collapse to the easy cell**; a second pack differing on ONE axis fails the differential by design.
- **A vacuity guard is itself proven non-vacuous** (#128 RED-B lineage): flip a real guard, not just inject a synthetic one; a guard never proven to fire is the cousin of the bug it guards.
- **Determinism conditions on pinned values**: observed-deterministic from the extraction run (fresh processes), or the value stays an invariant rather than a forced-brittle positive row.

## Standing rulings that recur
- Fail-closed over fail-open, always, at every new surface (registration, packs, gates, renderers).
- Positive-only denominators for accuracy metrics (dividing over negative invariants is a category error).
- History is not rewritten in docs (D4: historical records stay AS-IS, locked in both directions).
- Set-equality over byte-identity where order is legitimately free — byte-neutrality can be the WRONG contract (a false-failure trap).
