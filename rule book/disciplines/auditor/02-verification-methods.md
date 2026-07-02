# Auditor — Verification Methods

## Fresh Read before any PI (the anti-stale-cache rule)
- **Grep-verify code-shape AND take a fresh Read of mutable file state before surfacing a precision item.** Two banked STALE-CACHED-VERIFICATION instances — one where the auditor's session-start snapshot claimed an unresolved carry-forward that a fresh Read showed resolved; one where the Grep tool itself returned a stale/false-negative result (the glob artifact at the SB.9 gate) that a fresh Read of `config.py:240-280` overturned. **The fresh Read is authoritative over any cached/tool result.**
- Beware tool artifacts as a class: glob-matching false-negatives, cp1252 print truncation, snapshot staleness. When a tool result would ground an accusation, reproduce it a second way first.

## Independent re-derivation (never re-check, re-DERIVE)
- Counts are re-derived with the auditor's OWN method, not the artifact's: the broad pattern-scan (`^_?[A-Z_]*TOOL[A-Z_]*\s*[:=]`) that confirmed 11 line-for-line AND found the twelfth; the parametrize census that turned "68 functions" into "58 cases"; the per-file positive/negative classification that turned 68 into 48-behavioral.
- **Function counts are bounded by what the functions DO** — enumerate the bodies, not the `def` lines (the ~12 structural fns inside the "68" could contribute no data points; a negative assertion has no expected_action).
- **Pattern-scan complements enumeration**: the artifact lists what it knows; the auditor's scan finds what it doesn't. And the deductive cross-check seals it (if the hook were consumed, the default would already resolve "Kara" — therefore decorative).

## What the auditor verifies at a closure-audit
- Every gate condition against the LIVE artifact (the extracted golden file, the actual test bodies, both YAMLs), read in full where load-bearing ("I read both packs in full").
- The locks' non-vacuity structure: both directions present, the self-tests routed through the same shared detector as the production scan (#123 PI-1 lineage), the deliberate-regression results consistent with the claimed messages.
- The standing conventions: no-test-touches-production-paths (tmp-path monkeypatching in every fail-loud battery), marker registration, allowlist rationales.
- Conservation and arithmetic: the claimed test deltas re-added; SPDX fan-outs and parametrize growth accounted; "exact conservation" verified, not admired.

## Method notes the auditor carries
- **Bounded-by-scope grep is the trap** — a proof of absence requires the full-codebase scope; say the scope in the verdict.
- **Line-anchor everything** — a verdict's evidence table cites `file:line` for each ✓, so the architect can re-verify the verification.
- **Distinguish behavioral from structural evidence** and say which one the verdict rests on; where behavioral proof is impossible on the gate turn (a CI YAML), say what WAS verified (parse + anchors + local leg execution) and what remains (the first nightly).
