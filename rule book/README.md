# The KaraOS Rule Book

**What this is.** The operating system of this project, extracted from where it actually lives: the CLAUDE.md doctrine library (15+ elevated numbered doctrines with multi-cycle track records), the Solidify-Base board's section 8.2 role rules, the banked memory directives, and the lessons individual cycles paid for. Every rule here was **earned**, it exists because skipping it once cost something, and the cost is usually named in the provenance line.

**PUBLISHED.** Originally local-only; published to the repo on Jagan's 2026-07-03 directive, the disciplines and the cycle-spec archive are part of the project's public record. (The board discussions and internal knowledge dumps remain local-only, outside the repo.)

**How it's organized.**

```
rule book/
├── cycle-specs/ ← the published per-cycle spec archive (audits, plans, runbooks)
└── disciplines/
    ├── README.md ← the SHARED operating system (roles, the cycle, the universal proofs)
    ├── architect/ ← planning, auditing, Layer-3 verification, closure
    ├── developer/ ← coding standards, testing disciplines, pass-grep verification
    └── auditor/ ← gate verdicts, verification methods, standing tripwires
```

**The three enforcement tiers** (weakest to strongest):
1. **Written rule**, lives here + in CLAUDE.md; enforced by the actor reading it.
2. **Protocol**, a repeatable procedure with a named trigger (deliberate-regression REDs, Pass-N greps, the closure battery).
3. **CI invariant**, a structural test that fails the build when the rule is violated. The project's standing goal: promote rules up this ladder. ~25+ invariant/tripwire test files exist (`tests/test_*_invariant*.py`, `test_*_tripwire*.py`, `test_silent_except_invariant.py`, `test_layering_invariants.py`, `test_no_walltime_deadline_math.py`, `test_secrets_invariants.py`, …). Where a discipline has a CI enforcement, its entry names the test file.

**The one-sentence philosophy:** *reactive patching surfaces ~30% of an invariant's violations; structured audits surface ~100%, so when a rule is worth having, audit for it, test for it, and make the test fire before a human ever has to remember it.*
