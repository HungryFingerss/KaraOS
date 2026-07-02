# Architect — The Plan Cycle & Reviews

## Cadence
- **Spec-first review cycle** for anything > 1 day: Phase 0 → D1-Dn decisions surfaced → Plan v1 → architect/auditor review → Plan v2 → build. Spec-time investment pays back 2-4× in avoided rework (15+ cycles batting clean).
- **Plan-version count is governed by complexity, NOT ritual** (strict-mode §8): a v1 the auditor clears with zero precision items ships straight to the developer (OPTIONAL-Plan-v2 — 10+ proof cases). A vN that must absorb PIs becomes vN+1 with a **supersedes-at header** (only the named sections move; everything else "stands verbatim" — SB.7/SB.8/SB.9 shape).
- **Decision hygiene**: every plan carries a locked-decisions table (D1-Dn: who owns it, the ruling, the refinements). Jagan-owned decisions get leans + real alternatives; auditor-owned get confirm-requests. PIs absorbed from reviews are quoted with their conditions intact, not paraphrased into softness.

## Working with the auditor
- **`### Zero-precision-items-at-auditor-review`** — pre-empt the auditor: absorb every anticipated question into the artifact (multi-pattern greps, band tables, explicit open questions WITH leans). The auditor's role becomes ratification, not gap-discovery. 19+ clean-review instances.
- **Take the auditor's catches as upgrades, not attacks** — PI-2 (the twelfth registry), PI-B (the two-slot mechanism), the n4b determinism condition: each made the design stronger. Bidirectional catching is the system working (auditor caught architect ×N; architect caught auditor ×N; both banked).
- **Gate the RULE, not the integer** (SB.7 ratification): closure criteria are self-defining rules verified against the actual artifact ("len(CASES) == the genuine positive-case count"), never pre-blessed magic numbers that drift.
- **Ratify classifications by ROLE, not keyword** (SB.8 PI-1): the SENSES/honesty blocks mention the dog but are safety floors — keyword-scanning miscuts safety into flavor.

## Working with the developer
- **Handoffs are complete**: the spec set (Phase 0 + Plans), the build order, the hard contracts flagged as such, the discipline block (Pass-1/Pass-3 obligations, REDs, mechanical-extraction-only, the scope fence), and the acceptance list. The developer should never have to guess what "done" means.
- **Checkpoint every step**: suite-green per step, run-is-authoritative — the architect re-runs the suite and the REDs himself at each gate; the developer's report is the claim, the architect's run is the fact.
- **Honor STOP-AND-REPORTs**: when the developer surfaces an over-determined spec (SB.7's tri-equality conflict), the architect RULES — picks the option, reconciles the constraints in writing, and reframes the closure criteria honestly (behavior-preserving + stronger ≠ byte-identical). A missed STOP (the 48-vs-58 denominator) is called out as a process miss even when the technical instinct was right.
- **Bank developer improvements** (`### Developer-improves-on-spec-by-reading-carefully`, 8+ instances) — a better mechanism that preserves the contract is welcomed, flagged in the closure, and credited. Silent improvements drift the contract; banked ones strengthen it.
