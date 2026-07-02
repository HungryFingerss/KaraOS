# Architect — Layer-3 Verification (run-is-authoritative)

The architect's independent verification layer. The developer verified; the auditor gate-checked structurally; Layer-3 is the actually-run proof on the real box. The Canary-#3 lesson founded it: a "validated GREEN" claim was unsubstantiated and the golden test was vacuous — since then, **the architect runs the suite and the REDs himself before any sign-off.**

## The battery (per checkpoint / closure)
1. **Full suite, personally run** — `python -m pytest --ignore=tests/test_brain_json_parser_hypothesis.py -q` from repo root (collects tests/ + root files), 0 failed, with the count arithmetic reconciled against the previous gate (conservation: every ± explained; cross-box deltas are a known banked phenomenon — both boxes must be 0-failed).
2. **REDs, personally run** — a chosen subset re-run independently even when the developer already ran them (the mispoint, the floor-strip, the channel probe…), each firing FOR THE PRODUCTION REASON with the failure message quoted, each restored by exact-reverse Edit, net-zero verified (`git diff` clean / byte-identity re-checked).
3. **REDs-before-suite sequencing** — all probes complete before the authoritative suite launches; a probe window overlapping a running suite contaminates it (learned twice in SB.7: one dodged, one hit + briefly misattributed).
4. **Byte-identity where the contract is bytes** — goldens compared by the architect's own comparison (SB.8: recomposed == pre-cut golden, 13,640 bytes), not by trusting the anchor.
5. **Behavioral spot-verification** — env-boots, determinism re-runs (n4b: 10× in-process + fresh processes), end-to-end CLI runs (`python -m bench.perception`), leak-checks (the ENROLLMENT_MODE restore).
6. **Structural reads** — the load-bearing code regions read in source (the two-slot template, the gather, the safety guards), not summarized.

## Probe discipline
- Probes are temporary Edits with a visible marker (`ARCHITECT RED (temporary)`), restored exact-reverse; **never `git checkout`** on an uncommitted tree (it destroys the developer's unstaged work).
- `if False:` dead-code probes isolate SOURCE-scanner REDs from runtime noise when the detector reads source at test time.
- When a RED doesn't fire, that's a detector gap: strengthen the detector in the same cycle (the `### Induction-surfaces-invariant-gaps` operational rule), don't shrug.
- When a suite fails during/after probes: **root-cause before verdict** (the Iron Law). Same count on a clean tree disproved my own contamination hypothesis once — re-run clean, identify the test, classify (flake vs regression vs vacuity) with evidence. SB.7's "flake" was a 20-session vacuity; the gate-hold that refused to bump the timeout is what surfaced it.

## Verdict discipline
- Checkpoint verdicts are explicit: PASS / HOLD / FAIL with the gate table (what was checked, what was found). HOLDs name the exact unblock conditions.
- The final Layer-3 consolidates the cycle's full RED ledger + suite history into the closure record.
- **The two halves rule** (auditor boundary): the auditor ratifies structure from fresh reads; the full-suite-green on the real box is ALWAYS the architect's half — forwarded to him, never claimed by him.
