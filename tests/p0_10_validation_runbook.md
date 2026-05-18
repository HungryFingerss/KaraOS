# P0.10 Validation Runbook

**Status:** Ships with Phase 2 deletion PR.
**Audience:** Jagan, during the post-deletion validation window.
**Owner:** Architect + auditor sign off the gate closure; developer reverts on failure.

---

## Goal

Detect any divergence between the new reconciler's behavior and the user-visible
intent of the legacy router that was deleted in Phase 2. Specifically:

- The new `_p0_short_utterance_gap_hold_current` rule must fire on EVERY
  0.3-0.5s utterance with `cur_pid` set. Anything else fires → Bug-W
  regression.
- The Block B (B2) fail-safe (`[Reconciler] WARN: no rule fired`) must
  NEVER fire in normal use. It's a Bug-W-class structural-coverage gap
  signal.
- The Reconciler-Shadow log emits a divergence line ONLY when a
  watched-band turn (`utt_band=gap` or `utt_band=short_hard`) is handled
  by a rule OTHER than the band's expected rule(s).

If validation passes → follow-up PR deletes the shadow infrastructure +
`ROUTING_USE_RECONCILER` flag (see "Follow-up PR scope" below). If
validation fails → revert the Phase 2 PR (single-commit rollback) and
file a follow-up bug.

---

## Gate criteria (ALL must hold simultaneously)

1. **Traffic** — at least **100 routing decisions** during the window
   **OR 14 calendar days, whichever later** (p2 lock; locks the
   wall-clock floor to discourage premature closure).
2. **Zero `[Reconciler-Shadow]` divergence lines tagged `utt_band=gap`.**
   Gap-band turns MUST fire the gap rule every time. A `gap` line in the
   shadow log indicates the rule did NOT fire — Bug-W regression.
3. **Zero `[Reconciler-Shadow]` divergence lines tagged `utt_band=short_hard`.**
   The 0.5-1.0s band is D7-watch — `_p0_short_utterance_hard_mismatch`
   or `_p0_short_utterance_ambiguous_multi_session` (or the boundary
   pure-noise / gap variants) must fire. Any other rule firing is a
   coverage regression.
4. **Zero `[Reconciler] WARN: no rule fired` lines.** This is the B2
   fail-safe; should never fire in a fully-covered cascade. A WARN line
   is structurally equivalent to a Bug-W-class regression.
5. **Zero `[Reconciler-Shadow] error:` lines.** The try/except wrapper
   around the reconciler catches all exceptions; a recurring exception
   indicates a real bug in the cascade rules.
6. **No new regression complaints from Jagan during normal use.**
   Subjective gate but load-bearing — the user-experience regression
   class is what auditor's R3 mandated.

---

## Daily checklist (for Jagan)

Each day, after a normal session ends:

1. **Boot system normally.** `python pipeline.py` from the project root.
   Use the system end-to-end (multi-person sessions are most valuable —
   they exercise more of the cascade than solo sessions).

2. **At end of day, archive the terminal log.** The pipeline already
   does this on startup (renames `terminal_output.md` to
   `terminal_output_YYYY-MM-DD_HHMMSS.md`). All you need to do is shut
   the system down cleanly (Ctrl+C once); next boot triggers the
   archive.

3. **Grep the archives for divergence markers.** From the project root:

   ```bash
   # Count gap-band divergences (must be 0).
   grep -c "utt_band=gap" terminal_output_*.md

   # Count short_hard-band divergences (must be 0).
   grep -c "utt_band=short_hard" terminal_output_*.md

   # Count B2 fail-safe firings (must be 0).
   grep -c "no rule fired" terminal_output_*.md

   # Count reconciler exceptions (must be 0).
   grep -c "\[Reconciler-Shadow\] error:" terminal_output_*.md

   # Count routing-decision firings (track toward the 100-decision floor).
   grep -c "\[Voice\] .* Routing:" terminal_output_*.md
   ```

   **Divergence-log field reference (P0.10.1 F1):** each
   `[Reconciler-Shadow] ... divergence | ...` line carries 14 pipe-separated
   fields. The first correlation field is `turn_in_session=<int>` (per-session
   ordinal — the count of user messages within the current session;
   `n/a` when no session is open). Use this with `cur_pid` to locate the
   exact turn within a session when triaging a divergence; use `ts` (the
   leading `HH:MM:SS.mmm` timestamp on each log line) for cross-session
   correlation.

4. **If ANY gap/short_hard divergence OR WARN line OR Shadow error
   appears → STOP.** Do not continue using until the architect + auditor
   review the failing case. The shadow line itself logs all 14 fields
   for diagnosis (utt_dur, v_score, cur_pid, persons_in_frame_count,
   etc.) — no extra triage data needed.

5. **Record daily counts in a simple log** (text file is fine):
   ```
   YYYY-MM-DD: routing=N, gap_div=0, short_hard_div=0, warn=0, error=0
   ```

---

## Closure procedure

When all six gate criteria hold:

1. **Capture the validation artifact:** the running daily-count log +
   the most-recent archive file (proof the system was booting and
   running through the window).
2. **Hand off to the follow-up PR.** Closure unlocks the follow-up PR
   (DELETES/KEEPS list below).
3. **Update CLAUDE.md** Pending Work section to remove "P0.10
   validation window open"; mark the milestone closed.

---

## Failure procedure

If ANY criterion fails:

1. **Stop daily use.** Switch off pipeline until triaged.
2. **Capture the failing log line + the surrounding 10 lines of
   `terminal_output` for context.**
3. **File a follow-up bug** with the captured log + the daily-count log.
4. **Revert Phase 2 PR.** Single-commit rollback (the legacy function
   returns, the override conditional restores `ROUTING_USE_RECONCILER`,
   the shadow block restores its legacy-comparison trigger).
5. Architect + auditor review the failure, decide next steps.
   Common outcomes:
   - Cascade-coverage fix → Plan v3 → re-execute Phase 2 with the fix.
   - New rule needed → audit deliverable amended → Plan v3.

---

## Follow-up PR scope (R3 DELETES/KEEPS — locked in this runbook)

### DELETES (when validation closes)

- Entire Reconciler-Shadow block at the original `pipeline.py:7400-7408`
  shape — includes the 14-field rich-logging code added in Phase 1 (Block C)
  AND the band-divergence-detection trigger added in Phase 2. Both go
  together; the rich-logging code is dead the moment the shadow concept
  is gone.
- `ROUTING_USE_RECONCILER` flag in `core/config.py`.
- Any test references to the flag (none currently in test_pipeline.py
  per P0.10 audit, but check before deletion).
- The B2 fail-safe `else:` branch + WARN log emission in the override
  conditional. The cascade's `_last_resort_ambiguous` makes
  `_rc_decision is None` structurally impossible — the fail-safe was
  insurance against a future refactor that drops the last-resort rule.
  Once validation proves zero WARN-fires over the gate window, the
  fail-safe + its source-inspection tests can retire.

### KEEPS (forbidden from deletion)

- New reconciler (`core/reconciler.py`) + `_p0_short_utterance_gap_hold_current`
  rule + `LOWER_BOUND` attributes on every P0 rule.
- Bug-W regression test (`tests/test_p10_routing_invariants.py::test_bug_w_short_utterance_gap_holds_current_session`).
- RULES-ordering invariant test (`test_p0_cascade_ordered_by_ascending_utterance_band`).
- All other invariants in `tests/test_p10_routing_invariants.py` —
  these encode load-bearing structural locks.
- N2-N6 contracts in `tests/test_p10_reconciler_contract.py`.
- AST single-write-site test (`test_routing_action_has_single_logical_write_site`)
  — preserves the architectural invariant post-shadow-cleanup.
- Rich-logging FIELD set knowledge — even though the shadow block is
  deleted, the 14-field structured observability shape (utt_band tag,
  last_face_age_s, persons_in_frame_count) is a reusable template for
  any future telemetry work. Don't tear out the field shape's
  documentation in CLAUDE.md.

### Listing keeps explicitly prevents accidental scope creep

Without the explicit KEEPS list, "while we're cleaning up the shadow,
let me also remove the gap rule's LOWER_BOUND attribute since the
ordering test will never re-fail" becomes tempting and breaks the
invariant when the next P0 rule lands.

---

## Validation timeline expectation

Per Plan v2 estimate:

| Phase | Time |
|---|---|
| Phase 1 PR merge | (done) |
| Phase 2 PR merge | (this PR) |
| Validation window opens | immediately after Phase 2 merge |
| Validation window closes | ≥ 14 calendar days AND ≥ 100 routing decisions |
| Follow-up PR (DELETES) | 0.5 dev day, after closure |

Wall-clock floor is 14 days from PR merge. Traffic floor scales with
how often Jagan uses the system — 100 routing decisions ≈ 30-50
normal-use sessions.

---

## Pointer

CLAUDE.md milestone for P0.10 carries a 1-2 line pointer to this
runbook; the full procedure lives here so future P0.X items with
similar windows can copy the pattern.
