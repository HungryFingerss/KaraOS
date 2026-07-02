# Auditor — Standing Tripwires (what the auditor checks EVERY cycle)

The board's §8.2 auditor rules + the elevated recurring checks. These run regardless of the cycle's topic.

## The board's three (SB-specific, permanent)
1. **The bug-museum CI invariant** — no `Session NNN` / `Bug X` / canary-date strings in rendered prompts; internal archaeology never leaks into what the LLM (or a user) sees.
2. **The no-permanently-dead-flag tripwire** — every feature flag is referenced AND reachable in both states; a flag that can never flip is a lie in the config surface (Skeptic-2 §5.2).
3. **The behavior-removed test** — for every gated agent/capability: prove BOTH the object is gone AND the behavior is gone when the flag is off (the §2.6 acceptance shape; defeats behavior-sprawl).

## The universal closure gates
4. **Full-suite-run-is-the-universal-completeness-proof gates every closure** — the auditor confirms the architect's run happened (numbers + box named), and treats its own structural checks as bounded-by-method, never as a substitute.
5. **Conservation** — test-count deltas re-added exactly; deletions explained (re-signatures vs true deletions distinguished); zero unexplained.
6. **Deliberate-regression evidence** — the RED ledger present, each RED's firing message consistent with the production reason, each restore net-zero.
7. **Tracked-artifact hygiene** — internal artifacts out of the published surface; goldens/baselines committed where the spec says; runs/ ignored; the tracker banked.

## The registry/coverage tripwires (P0.S6 lineage, generalized by SB.9)
8. **Registry coverage**: privilege ⊇ tools, handler coverage, intent coverage — against the REGISTERED set once the registration API lands, never a static literal.
9. **No undocumented registry** — the AST scan for tool-name-coupled surfaces; derived views (the `_KNOWN_TOOL_NAMES` projection) are classified as legitimate; hand-maintained siblings of derived views FAIL.
10. **Allowlist integrity** — every entry carries rationale; stale entries are drift (and a stale LINE key that a shifted site lands on is the DANGEROUS drift — under-reporting; prefer content keys).

## The drift detectors
11. **LINE-REF-DRIFT family** (incl. STALE-KEY-COLLISION) — line references in specs/allowlists checked against fresh scans.
12. **Twin-surface checks** — both conftests, both profile YAMLs, both memory paths, both tool lists: when one member of a known pair changes, the auditor asks about the other.
13. **Doctrine-count integrity** — track-record bumps carry explicit justification; arithmetic shown (`pre + artifacts = total`); mechanism-vs-documentation distinction enforced; misattributions corrected retroactively on the record.
14. **Banner/tracker staleness policy** — the SB tracker is the source of truth and must be current; the CLAUDE.md banner is intentionally stale (the auditor does not touch it, and flags anyone who "fixes" it).

## Escalation
A tripwire firing is not automatically a BLOCK — the auditor classifies (regression / ripple / banked-known-limitation / new-sub-shape) and routes: same-cycle fix, absorption PI, or a banked watch-item with elevation criteria (3+ instances → candidacy; 5+ → numbered doctrine).
