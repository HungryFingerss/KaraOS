# Developer — Pass-Grep Verification (the catching layers)

The multi-pass grep discipline is the project's most empirically validated catching machinery. Each layer is independent; drift caught at layer N never reaches layer N+1's cost.

## The passes
- **Pass-1 (at pickup / enumeration)** — the developer independently enumerates the spec's target surface before building: the exact case counts (the ~56-fns→51-flat-cases work), the parametrize expansions FLATTENED (a ×3 parametrize is 3 cases, not 1), the anchor positions, the verbatim fragments. Where the spec says "~N", Pass-1 produces the exact N and reports the arithmetic.
- **Pass-3 (at Phase-4 pre-implementation)** — `### Developer-Pass-3-grep-at-Phase-4-pre-implementation` (elevated doctrine, 3 founding instances): re-grep the locked enumeration against ACTUAL DISK STATE before any code mutation. Dual-axis: file-count AND semantic-correctness. Drift > ±10% or a semantic gap → STOP, re-engage architect+auditor; small subsumed drift → proceed with the extension documented. Founding catches: a 42% PowerShell line-count error, a mechanical-script scope undercount, an AST-scope omission — and in SB territory: **the SB.5 enrollment gate that would have crashed the robotics CI leg on the first nightly**, and the `.format`-KeyError on the greeting template's runtime keys.
- **Pass-4 (in-flight, at the edit site)** — per-site code-reads while migrating catch classification errors counts can't (the P0.S5 site-classification swaps; the −2 allowlist ripple from an import removal).

## Grep craft (the rules that make greps trustworthy)
- **Full-codebase scope or it isn't a proof** — "decorative = never consumed" is only provable with the repo-wide grep (apply/logging/display), not a directory-scoped one. Bounded-by-scope grep is the trap (auditor-banked, SB.8).
- **Pattern-scan over known-name enumeration** — listing the names you know finds the names you know; an alternation-pattern scan finds the twelfth registry (SB.9 PI-2).
- **The allowlists are enumeration INPUTS** — `_REGISTRY_ALLOWLIST`-class artifacts record what the project already knows; consult them FIRST, then pattern-scan for what no artifact records, and let the runtime tripwire be the completeness proof at build. Three complementary methods; exhaustive only through their union.
- **Grep both siblings, always** — every dual-list surface (`TOOLS`/`_API_TOOLS`, both conftest files, both profile YAMLs, both memory paths) is a place where fixing one and missing the other has already happened. The SB.5 lesson generalizes: when you find one, ask what its twin is.
- **Line-refs are perishable** — refresh from the detector's fresh scan, never arithmetic-shift by hand; prefer content keys where the artifact allows.

## Ripples
- In-flight ripples (line-shift allowlist refreshes, test re-points after intentional renames, LINE-REF-DRIFT fixes) are legitimate — land them WITH rationale per entry, banked in the report, classified honestly (ripple-of-my-change vs improvement vs pre-existing debt).
- A ripple that surfaces a NEW failure shape gets named and escalated (STALE-KEY-COLLISION came out of a routine allowlist refresh — the developer noticed the under-report and banked the sub-shape instead of just refreshing the keys).
