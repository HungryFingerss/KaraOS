# P0.10 Plan v2 — legacy routing deletion + Bug-W fix

**Status:** v2 draft incorporating architect's Block A-E sign-off feedback. Pure documentation; zero production code changes.
**Date:** 2026-05-17.
**Supersedes:** `tests/p0_10_plan_v1.md` (kept for delta visibility).
**Prerequisites unchanged from v1.**

---

## Delta from v1

| Block | v1 stance | v2 resolution |
|---|---|---|
| **A** | Rule shape was sketched but inexact | Verbatim spec locked + **new** RULES-ordering invariant test |
| **B** | Open question: drop with `"no_action"` vs hold with `"current"` | Locked: **(B2)** hold-current + WARN log. **N7 added** to negative contract; companion test mandatory |
| **C** | Rich logging "12 fields" sketched | Locked: **extend the existing Reconciler-Shadow log** (not new infrastructure); 14-field shape pinned |
| **D** | Test count math discrepancy (27 vs 33) | **Explicit breakdown table** below. Total = 33 with v2 additions |
| **E** | Validation procedure inline in CLAUDE.md milestone | Locked: **separate runbook** at `tests/p0_10_validation_runbook.md`; CLAUDE.md gets a 1-2 line pointer |

---

## Block A — `_p0_short_utterance_gap_hold_current` (verbatim spec)

**File:** `core/reconciler.py`. Insert between `_p0_pure_noise_hold_current` (handles `< 0.3s`) and `_p0_short_utterance_hard_mismatch` (handles `>= 0.5s`).

**Architect-approved code shape (verbatim per Block A):**

```python
def _p0_short_utterance_gap_hold_current(
    claim: IdentityClaim, presence: PresenceState, session: SessionState
) -> Optional[RoutingDecision]:
    """Gap-fill rule covering the 0.3-0.5s utterance band where neither
    _p0_pure_noise_hold_current (< 0.3s) nor _p0_short_utterance_*_mismatch
    (>= 0.5s) fires.  Without this, Bug-W falls through every P0/P1/P2/P3
    rule and lands on _p4_new_stranger_low_match → phantom stranger.

    Same shape as legacy router's P0c catch-all (pipeline.py:1233) but
    narrowed to the actual coverage gap (not legacy's 1.0s blanket floor —
    existing P0 rules at >= 0.5s were designed correctly per Phase 4 cutover).
    """
    if (claim.utterance_duration >= VOICE_ROUTING_NOISE_FLOOR_SECS       # 0.3
            and claim.utterance_duration < VOICE_ROUTING_MIN_AUDIO_FOR_SCORE  # 0.5
            and session.cur_pid is not None):
        return RoutingDecision(
            pid=session.cur_pid,
            action="current",
            rule="_p0_short_utterance_gap_hold_current",
            reasoning=(
                f"utterance {claim.utterance_duration:.2f}s in 0.3-0.5s gap band — "
                f"hold current session ({session.cur_pid}); audio too short for "
                f"voice-ID decision but above pure-noise floor"
            ),
        )
    return None
```

**Gate semantic:** unconditional hold-current for `0.3 ≤ utt < 0.5` AND `cur_pid is not None`. No voice-score / n_active / face check. The band itself IS the rationale ("audio too short for any decision").

**Position in RULES list:**

```python
RULES: list = [
    _p0_pure_noise_hold_current,               # utt < 0.3
    _p0_short_utterance_gap_hold_current,      # ★ NEW: 0.3 ≤ utt < 0.5
    _p0_short_utterance_hard_mismatch,         # 0.5 ≤ utt < 1.0, score < FLOOR
    _p0_short_utterance_ambiguous_multi_session,  # 0.5 ≤ utt < 1.0, ambiguous + multi-session
    _p0_short_utterance_no_session,            # utt < 0.3 + no cur_pid
    # P1-P5 unchanged
]
```

**Note on v1 → v2 ordering revision:** v1 placed the new rule between `_p0_short_utterance_ambiguous_multi_session` and `_p0_pure_noise_hold_current`. Architect's Block A locked the ordering BY DURATION BAND — ascending lower bound. The correct position is between `_p0_pure_noise_hold_current` (`< 0.3`) and `_p0_short_utterance_hard_mismatch` (`>= 0.5`). v2 fixes this.

### New RULES-ordering invariant test (Block A structural lock)

**Purpose:** Enforce the duration-band ordering structurally so a future refactor that re-orders the P0 cascade can't silently put rules out of band-order. Same shape as P0.5 inverse-check, P0.6.7v2 writer enumeration, P0.8.2 F1/F2.

**Location:** `tests/test_p10_routing_invariants.py` (Step 1's file).

**Test shape:**

```python
def test_p0_cascade_ordered_by_ascending_utterance_band():
    """P0.10 Block A invariant: P0 cascade rules MUST be ordered by their
    utterance_duration lower-bound, ascending.  Putting a rule later
    than its band would let an earlier rule fire on inputs the later
    rule was supposed to cover — exactly the failure shape Bug-W
    exhibited (gap rule landing late wouldn't help).

    Each P0 rule has an inspectable lower-bound — extracted from its
    documented band in the rule's __doc__ or via an explicit
    LOWER_BOUND class attribute (TBD during implementation — pick
    whichever is more maintainable).
    """
    from core.reconciler import RULES
    p0_rules = [r for r in RULES if r.__name__.startswith("_p0_")]
    bounds = []
    for rule in p0_rules:
        # Convention: each P0 rule documents its lower bound in __doc__
        # via a structured "Band: [lower_bound, upper_bound]" comment
        # parsed by the test.  Alternative: explicit LOWER_BOUND attr
        # set by the rule definition.  Both options reviewable; pick
        # one during implementation.
        bound = _extract_lower_bound(rule)
        bounds.append((rule.__name__, bound))
    actual_order = [name for name, _ in bounds]
    expected_order = [name for name, _ in sorted(bounds, key=lambda x: x[1])]
    assert actual_order == expected_order, (
        f"P0 cascade out of duration-band order.\n"
        f"  expected: {expected_order}\n"
        f"  actual:   {actual_order}\n"
        "Reorder per ascending lower bound — putting a rule out of order "
        "lets an earlier rule fire on inputs the later rule was meant to cover."
    )
```

**Sign-off block A.1 (carried forward to architect for v2 review):** the lower-bound extraction approach — `__doc__`-parse via structured comment vs explicit `LOWER_BOUND` attribute on the rule function. Recommend the attribute — `__doc__`-parsing is fragile across refactors. Locks into implementation phase.

---

## Block B — Step 9 error path: (B2) hold-current + WARN log

**Locked:** when `_rc_decision is None` post-deletion (reconciler returned None — no rule fired — OR raised and was caught by try/except), the dispatch holds the current session AND emits a loud WARN log.

**Reasoning (per architect's Block B):**
- User-visible silence from (B1) is a worse failure mode than a transient missed-routing-update
- (B2) preserves the user's experience while making the gap loud in operator logs
- A `[Reconciler] WARN: no rule fired` log is a structural signal — should NEVER fire in a fully-covered rule set. Any appearance post-deployment = new Bug-W to investigate
- (B1)'s no-response failure mode would itself be a Bug-W class regression

**Code shape:** `pipeline.py:7417-7419` becomes:

```python
# P0.10: reconciler is the only routing source. ROUTING_USE_RECONCILER flag
# kept alive for the 7-day validation window (follow-up PR deletes the flag
# + Reconciler-Shadow infra together — D5).
if _rc_decision is not None:
    _resolved_pid = _rc_decision.pid
    _routing_action = _rc_decision.action
else:
    # P0.10 Block B (B2): no-rule-fired fail-safe.  Either reconciler
    # raised (caught by the try/except above) or returned None (no rule
    # in the RULES cascade matched — coverage gap, equivalent to a
    # Bug-W-class regression).  Hold the current session and emit a
    # loud WARN log so the gap is INSTANTLY visible in operator logs.
    # This log should NEVER fire in a fully-covered rule set.
    _resolved_pid = _cur_pid
    _routing_action = "current"
    print(
        f"[Reconciler] WARN {_now_log_ts()}: no rule fired — falling back "
        f"to hold-current; claim=(v_pid={_v_pid!r}, v_score={_v_score:.3f}, "
        f"utt={(_utterance_secs or 0.0):.2f}s, n_diarize={_diar_seg_count}) "
        f"session=(cur_pid={_cur_pid!r}, cur_type={_cur_person_type!r})"
    )
```

### N7 added to negative contract

| # | Forbidden behavior | Source |
|---|---|---|
| **N7** | **Silently drop a turn when `_rc_decision is None` (reconciler returned None or raised). Must hold current session AND emit `[Reconciler] WARN: no rule fired` log line** | **Block B (B2) lock** |

### N7 companion test

**Location:** `tests/test_p10_routing_invariants.py`.

**Test shape (behavioral):**

```python
def test_n7_no_rule_fired_holds_current_and_warns(monkeypatch, capsys):
    """P0.10 Block B / N7: when the reconciler returns None (no rule
    fired in the cascade), the dispatch MUST hold the current session
    AND emit a loud [Reconciler] WARN log so the coverage gap is
    visible to operators.  This branch should NEVER fire in a fully-
    covered rule set — a WARN line in prod logs is a Bug-W-class
    regression signal."""

    # Force reconcile() to return None by patching RULES to an empty list.
    import core.reconciler as _r
    monkeypatch.setattr(_r, "RULES", [])

    # Drive a single conversation_turn iteration with a known cur_pid.
    # (Implementation detail: use the same test harness shape as Step 3's
    # Bug-W regression test, but verify the dispatch-side branch rather
    # than the reconciler-side rule selection.)
    # ... harness setup ...

    # Assertions:
    #   1. _routing_action == "current" (hold)
    #   2. _resolved_pid == cur_pid
    #   3. capsys captures "[Reconciler] WARN" line
    #   4. WARN line includes claim + session fields per the spec above

    captured = capsys.readouterr().out
    assert "[Reconciler] WARN" in captured
    assert "no rule fired" in captured
    assert "falling back to hold-current" in captured
    # ... plus the routing assertions ...
```

Plus a **second test** verifying the exception path (reconciler raises, caught by try/except, falls through to the None branch — same end-state):

```python
def test_n7_reconciler_exception_holds_current_and_warns(monkeypatch, capsys):
    """Companion to test_n7: when reconcile() raises, the try/except
    swallows it (per existing pattern) and _rc_decision stays None,
    triggering the same (B2) fail-safe."""
    import core.reconciler as _r
    def _boom(*a, **kw):
        raise RuntimeError("forced reconciler bug")
    monkeypatch.setattr(_r, "reconcile", _boom)
    # ... harness setup ...
    # Assert same end-state: _routing_action == "current", WARN logged.
```

**Both tests count toward N7 coverage** (separate failure modes share the same fail-safe).

---

## Block C — Rich logging: extend Reconciler-Shadow, don't build new infra

**Locked:** extend the existing divergence-log block at `pipeline.py:7400-7408` (the one that stays alive through the validation window per D5/Step 11). No parallel logging path; the rich format is just the existing format with more fields + utterance-band tagging.

**Field set (architect's 14-field proposal, pinned verbatim):**

| Field | Type | Purpose |
|---|---|---|
| `ts` | timestamp | Always present (existing format already has this) |
| `turn_id` | int / "n/a" | Recoverable from ts but cheap; keep for ergonomics |
| `legacy_action` | str | Existing field |
| `legacy_pid` | str / None | New — pairs with legacy_action |
| `new_action` | str | Existing field |
| `new_pid` | str / None | Existing field |
| `new_rule` | str | Existing field (rule name that fired) |
| `utt_dur` | float | Utterance duration in seconds |
| `utt_band` | str | **Auditor's D7-watch tag**: `noise` (<0.3) / `gap` (0.3-0.5) / `short_hard` (0.5-1.0) / `normal` (≥1.0) |
| `v_score` | float | Voice-ID confidence |
| `pyannote_segments` | int | n_diarize_segments |
| `cur_pid` | str / None | Session holder |
| `persons_in_frame_count` | int | len(persons_in_frame) |
| `last_face_age_s` | float / None | now - last_face_seen (presence freshness) |

**Format:** structured log line (TSV / pipe-separated for grep-ability, **not** JSON — readability matters; same shape as the existing `[Vision]` and `[Voice]` log conventions).

**Implementation site (single edit at pipeline.py:7400-7408):**

```python
if _rc_decision.action != _routing_action:
    # P0.10 Block C: rich divergence logging extends the existing
    # Reconciler-Shadow block.  Stays alive through the 7-day
    # validation window; deleted in the follow-up PR alongside the
    # shadow infrastructure.  Tagged utt_band per D7-watch.
    _utt = _utterance_secs or 0.0
    if _utt < VOICE_ROUTING_NOISE_FLOOR_SECS:
        _band = "noise"
    elif _utt < VOICE_ROUTING_MIN_AUDIO_FOR_SCORE:
        _band = "gap"        # 0.3 ≤ utt < 0.5 — Bug-W's signature
    elif _utt < VOICE_ROUTING_MIN_UTTERANCE_SECS:
        _band = "short_hard" # 0.5 ≤ utt < 1.0 — D7 watch
    else:
        _band = "normal"
    _last_face_age = (
        time.time() - max((s.last_seen for s in _presence_store.peek_all_snapshots()), default=0.0)
        if _rs_pif_view else None
    )
    print(
        f"[Reconciler-Shadow] {_now_log_ts()} divergence | "
        f"turn_id={_turn_id} | legacy={_routing_action!r} | "
        f"legacy_pid={_resolved_pid!r} | new={_rc_decision.action!r} | "
        f"new_pid={_rc_decision.pid!r} | new_rule={_rc_decision.rule_fired!r} | "
        f"utt_dur={_utt:.2f}s | utt_band={_band} | v_score={_v_score:.3f} | "
        f"pyannote_segments={_diar_seg_count} | cur_pid={_cur_pid!r} | "
        f"persons_in_frame_count={len(_rs_pif_view)} | "
        f"last_face_age_s={(f'{_last_face_age:.2f}' if _last_face_age is not None else 'n/a')}"
    )
```

**Follow-up PR removes** this entire block (D5) once validation closes.

**Sign-off block C.1 (carried to v2 review):** `_turn_id` extraction site — pipeline.py uses turn-id-like values in a few places (`conversation_log.id`, the `turn_count` session field, etc.). Pick the most appropriate handle during implementation; not a load-bearing decision.

---

## Block D — Test count breakdown (explicit reconciliation)

v1's count was self-inconsistent. v2 reconciles with an enumeration table that maps every test to its source step:

| Source | Test name | Count | Counts toward |
|---|---|---|---|
| Step 1 | `test_routing_action_has_exactly_one_write_site` | 1 | AST verification |
| Step 1 (v2 NEW) | `test_p0_cascade_ordered_by_ascending_utterance_band` | 1 | Block A RULES-ordering invariant |
| Step 3 | `test_bug_w_short_utterance_gap_holds_current_session` | 1 | **Same test as C3 and N1** (counted once below; not double-counted here) |
| Step 3 | `test_gap_rule_does_not_fire_at_audio_gate_boundary` | 1 | Bug-W boundary |
| Step 3 | `test_gap_rule_does_not_fire_at_noise_floor_boundary` | 1 | Bug-W boundary |
| Step 3 | `test_gap_rule_does_not_fire_when_no_cur_pid` | 1 | Bug-W boundary |
| Step 3 | `test_gap_rule_fires_at_top_of_range` | 1 | Bug-W boundary |
| Step 5 | `test_c1_*` through `test_c21_*` (excluding C3 — same as Bug-W regression) | 20 | C1-C21 positive contract (C3 counted via Step 3) |
| Step 5 | `test_c3_gap_rule_holds_current` ← **same as Bug-W regression test** | 1 | C3 / N1 / Bug-W regression — one test, three roles |
| Step 5 | `test_n2_*` through `test_n6_*` (N1 is same as C3 above; N7 is new) | 5 | N2-N6 negative contract |
| **v2 NEW (Block B)** | `test_n7_no_rule_fired_holds_current_and_warns` | 1 | N7 forbidden behavior |
| **v2 NEW (Block B)** | `test_n7_reconciler_exception_holds_current_and_warns` | 1 | N7 exception-path companion |
| **Total unique tests** | | **34** | |

**v1 → v2 delta:**
- v1 said 33; my arithmetic was off (I double-counted N1=C3 once but missed the same overlap elsewhere).
- v2 adds 1 RULES-ordering invariant (Block A) + 2 N7 tests (Block B) = +3.
- v2 total = 34.

**Suite projection update:** 2189 → **~2223** passing after Plan v2's code lands (up from v1's "~2222"). Infra debt stays at 8.

---

## Block E — Validation runbook (separate file)

**Locked:** validation procedure moves to `tests/p0_10_validation_runbook.md`. CLAUDE.md milestone gets a 1-2 line pointer only.

**Why separate:**
- Validation is a one-time wall-clock procedure; CLAUDE.md is for permanent project state
- Future P0.X items with similar windows can copy the runbook pattern
- Operator-facing checklist (Jagan reads during validation) is structurally different from architect-facing milestone

**Runbook contents** (drafted during implementation, NOT in this v2):

1. **Goal**: detect any divergence during validation window before proceeding to flag-deletion follow-up PR.
2. **Gate criteria**:
   - 100 routing decisions during validation window **OR** 14 calendar days, whichever LATER (p2 lock)
   - Zero `[Reconciler-Shadow]` lines tagged `utt_band=short_hard` (D7-watch)
   - Zero `[Reconciler-Shadow]` lines tagged `utt_band=gap` (gap rule must fire every time)
   - Zero `[Reconciler] WARN: no rule fired` lines (N7)
3. **Daily checklist for Jagan**:
   - Boot system normally
   - At end of day, grep `terminal_output*.md` for `[Reconciler-Shadow]` and `[Reconciler] WARN` lines
   - Count `[Voice] Routing:` lines for the routing-decision counter
   - If any divergence in the gap or short_hard band → STOP. File follow-up bug. Do not proceed to follow-up PR.
4. **Closure**: when criteria met, capture the validation artifact + hand off to follow-up PR.

The runbook itself ships **at implementation time**, not Plan v2.

---

## Revised step sequence (v2)

Per Block A-E feedback, the sequence is structurally the same as v1, but the test counts and a few details revise:

1. AST verification (Step 1) — **+1 test** (RULES-ordering invariant per Block A)
2. Add `_p0_short_utterance_gap_hold_current` (Block A verbatim spec; position fixed)
3. Bug-W regression + 4 boundary tests (Step 3)
4. D7-watch telemetry as extension to Reconciler-Shadow (Block C — single edit, 14 fields)
5. C1-C21 + N1-N7 contract tests (Step 5; **N7 added** per Block B)
6. Delete `_resolve_actual_speaker`
7. Delete legacy call site
8. (Reconciler-Shadow stays alive; deleted in follow-up PR)
9. Collapse override conditional → Block B (B2) hold-current + WARN log
10. Retarget/delete test-side source-inspection refs
11. Keep `ROUTING_USE_RECONCILER` flag for validation window
12. CLAUDE.md milestone with 3 non-claims **+ 1-2 line pointer to validation runbook (Block E)**

**Implementation deliverable adds:**
- `tests/p0_10_validation_runbook.md` (lands during implementation, not Plan v2)

---

## Files touched (v2, unchanged from v1 + validation runbook addition)

**New files (planned, land during implementation):**
- `tests/test_p10_routing_invariants.py` — AST verification + RULES-ordering + Bug-W regression + N7 tests
- `tests/test_p10_reconciler_contract.py` — C1-C21 + N2-N6 contract tests (C3/N1 shared with regression test)
- `tests/p0_10_validation_runbook.md` — operator-facing validation procedure (Block E)

**Modified files (planned):**
- `core/reconciler.py` — add `_p0_short_utterance_gap_hold_current` (Block A) + optional `LOWER_BOUND` attribute on each P0 rule (Block A.1 decision pending)
- `pipeline.py` — Steps 6 + 7 + 9 (delete legacy function, delete call site, collapse override with Block B (B2) fail-safe). Step 4 (rich telemetry) modifies the existing Reconciler-Shadow block in place per Block C.
- `test_pipeline.py` — Step 10 (test-side source-inspection refs, inline decision during implementation)
- `CLAUDE.md` — Step 12 milestone + 1-2 line runbook pointer

**Untouched files (per D5/D6):**
- `core/config.py::ROUTING_USE_RECONCILER` flag — deletion deferred
- pipeline.py Reconciler-Shadow block stays alive (gets the Block C rich format in v2; the block itself is deleted in the follow-up PR)

---

## v1 → v2 sign-off blocks still open

**v2 introduces two minor sign-off requests** (architectural choices that need explicit approval before implementation, but neither blocks Plan v2's structure):

- **A.1** — lower-bound extraction approach for the RULES-ordering invariant. Recommended: explicit `LOWER_BOUND` attribute on each P0 rule function. Alternative: parse from `__doc__` structured comment. Attribute is more robust to refactors; docstring parsing is fragile.
- **C.1** — `_turn_id` extraction site for the rich log. Recommended: the existing `conversation_log.id` insertion point (most stable handle). Alternative: session-side `turn_count`. Either works; surface the choice during implementation.

Both can land either way. Architect can lock at v2 review or defer to implementation.

---

## Estimate (v2, unchanged from v1)

| Phase | Time |
|---|---|
| Plan v2 → architect+auditor sign-off | 0.5-1 day |
| Implementation (Steps 1-12, code + tests + runbook) | 1.5-2 dev days |
| Validation window (7-day wall-clock + 100 routing decisions, whichever later) | 7-14+ days wall-clock |
| Follow-up PR (shadow + flag deletion) | 0.5 dev days |
| **Total P0.10 closure** | **~2.5-3.5 dev days + traffic-gated validation** |

Awaiting architect + auditor v2 sign-off.
