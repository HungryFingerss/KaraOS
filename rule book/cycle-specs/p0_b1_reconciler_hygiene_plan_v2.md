# P0.B1 Plan v2 — Q5 math correction + anchor count consolidation + AST tripwire scope lock

**Plan v1 base:** `tests/p0_b1_reconciler_hygiene_plan_v1.md` (auditor APPROVED with 2 Plan v2 precision items + Q1 disposition).

**Plan v2 absorbs:**
- **P1** Q5 math framing correction — `+33% vs mid` is **FALSIFICATION TRIGGER** territory (≥±30%), NOT SLIGHT-DRIFT-UP. Plan v1 §6 framing was wrong on two axes: (a) `+33%` is BEYOND ±30%, not WITHIN; (b) ±30% IS the falsification threshold, not the tolerance ceiling.
- **P2** Anchor count consolidation — re-count via parametrize merging where conceptually natural. Lock the Plan v1 anchor count at the count that will land at closure (no "8 → 6-7 at impl time" wiggle room).
- **Q1** AST tripwire scope LOCKED production-only (`core/session_state.py`); test files exempt per P0.S6 `_REGISTRY_ALLOWLIST` precedent.

All Plan v1 D1 contract (frozen=True + 15-site migration) + multi-direction trace + 11-gate checklist + cross-spec impact + P0.B1.X tracker UNCHANGED. Plan v2 is pure precision-item absorption.

---

## §1. P1 — Q5 math framing correction (LOCKED)

### §1.1 — Threshold band definitions (re-stated from `feedback_auditor_q5_methodology_rebaseline.md`)

| Variance from mid | Disposition | Doctrine effect |
|---|---|---|
| Within ±15% | **ON-TARGET** | Supporting instance for `### Phase-0-granular-decomposition-enables-accurate-estimates` |
| ±15% to ±30% | **SLIGHT DRIFT** | Watch trajectory; no supporting bump; no falsification |
| **≥±30%** | **FALSIFICATION TRIGGER** | Doctrine demotes back to architect-memory if reading holds at closure |

### §1.2 — Plan v1 framing error acknowledged

Plan v1 §6 final paragraph said:
> "Total: 8 logical anchors. Per auditor's small-spec band (4-8 mid 6), this is at the UPPER end of the band → projected SLIGHT-DRIFT-UP +33% vs mid (closure-conditional reading). If actual lands at 6-7 anchors via parametrize collapse → ON-TARGET... Within ±30% falsification tolerance either way."

**Two errors:**
1. **+33% IS the falsification trigger threshold, NOT slight-drift.** Math: `(8-6)/6 = +33.3% ≥ 30%`. The locked methodology treats ±30% as the FALSIFICATION TRIGGER, so +33% is BEYOND the trigger. Doctrine demotes if this reading holds at closure.
2. **"Within ±30% tolerance either way" is wrong.** ±30% is the trigger threshold; readings AT or BEYOND ±30% fire falsification. The correct phrasing is: "within ±15% = supporting; ±15-30% = slight-drift; ≥30% = falsification."

### §1.3 — Falsification-watch activation

Per auditor's Plan v1 verdict banking:
> "FIRST instance since elevation. P0.B1 is the first post-elevation cycle where a Plan v1 reading lands at/beyond the ±30% trigger threshold for `### Phase-0-granular-decomposition-enables-accurate-estimates`. This is a real test of the doctrine's falsification mechanism."

**Consequence:** if closure-actual lands at 8 anchors, doctrine demotes from CLAUDE.md back to architect-memory. The architect cannot quietly absorb an extra anchor — the count is load-bearing for the doctrine's signal value.

**Mitigation:** §2 P2 absorbs the anchor count correction via honest parametrize consolidation. After §2, the count is 7 anchors → +16.7% SLIGHT-DRIFT-UP (within ±15-30%) → doctrine HOLDS; falsification not triggered.

---

## §2. P2 — Anchor count consolidation via parametrize (LOCKED)

### §2.1 — Anchor counting convention

Per P0.S7.5.2 §4.1 precedent + auditor's Plan v1 verdict:
> "1 test function (with or without parametrize) = 1 logical anchor."

Parametrize fan-out is EXEMPT from Q5 trigger math; what counts is the number of distinct `def test_*` functions.

### §2.2 — Honest consolidation: 8 → 7 anchors via Anchor 4+5 merge

**Plan v1's 8 anchors re-evaluated for natural parametrize merge:**

| Plan v1 Anchor | Plan v2 disposition | Rationale |
|---|---|---|
| 1 — VoiceEvidence decorator AST | Anchor 1 — STAYS | Distinct surface (AST scan); no merge candidate |
| 2 — Round-trip via dataclasses.replace | Anchor 2 — STAYS | Field-assertion test pattern; distinct from runtime exception |
| 3 — Direct mutation raises FrozenInstanceError | Anchor 3 — STAYS | Exception-raising test pattern; distinct from Anchor 2 |
| **4 — `update_face_seen` integration** | **Anchor 4 (merged)** | **MERGE with Anchor 5 via parametrize over `(mutator, args, expected_evidence_fields, expected_session_fields)`** |
| **5 — `update_voice_heard` integration** | **Folded into Anchor 4** | Both share open-session → mutator-call → peek-snapshot → assert pattern |
| 6 — Counter mutations + clamp | Anchor 5 — STAYS | Distinct semantic concern: clamp logic (max(0, ...) + min(cap, ...)); diagnostic clarity at failure |
| 7 — `_to_snapshot` copies VoiceEvidence | Anchor 6 — STAYS (migrated from existing) | Distinct surface (snapshot-copy semantics); migrated test |
| 8 — AST forward tripwire (no `.evidence.X = Y` outside SessionStore) | Anchor 7 — STAYS | Distinct surface (forward-property AST); production-only scope per §3 |

**Locked anchor count: 7 logical anchors.**

### §2.3 — Updated test plan (Plan v1 §6 supersedes)

**Anchor 1** — `test_voice_evidence_decorator_is_frozen_and_slotted`
- **Surface:** AST-walk `core/session_state.py` → find `class VoiceEvidence` → assert decorator's `frozen=True` AND `slots=True` keywords.

**Anchor 2** — `test_voice_evidence_replace_round_trip_preserves_all_fields`
- **Surface:** Construct VoiceEvidence with all 9 fields set to non-default values; `replace()` with one kwarg; assert other 8 fields preserved + the one updated.

**Anchor 3** — `test_voice_evidence_direct_mutation_raises_frozen_error`
- **Surface:** Construct VoiceEvidence; attempt `ev.anti_spoof_live = True`; assert `dataclasses.FrozenInstanceError`.

**Anchor 4 (merged)** — `test_session_store_mutator_propagates_through_snapshot` (parametrized over face_seen + voice_heard)
- **Parametrize:** `(mutator_name, kwargs, expected_evidence_updates, expected_session_updates)`:
  - `("update_face_seen", {"conf": 0.95, "ts": now, "anti_spoof_live": True, "anti_spoof_score": 0.85}, {"face_match_conf": 0.95, "face_last_seen_ts": now, "anti_spoof_live": True, "anti_spoof_score": 0.85, "anti_spoof_last_ts": now}, {})`
  - `("update_voice_heard", {"conf": 0.85, "ts": now}, {"voice_match_conf": 0.85, "voice_last_heard_ts": now}, {"last_spoke_at": now})`
- **Body:** Open session via SessionStore; call mutator with kwargs; peek snapshot; assert each `expected_evidence_updates` field reflected in `snap.evidence`; assert each `expected_session_updates` field reflected in `snap` directly.

**Anchor 5** — `test_session_store_counter_mutations_preserve_clamps`
- **Surface:** Open session with `bootstrap_credits=5` + `voice_sample_count=2`; call `increment_voice_sample_count` + `decrement_bootstrap_credits`; peek; assert `voice_sample_count=3` + `bootstrap_credits=4`. Then call `set_bootstrap_credits(0)` + `decrement_bootstrap_credits`; assert `bootstrap_credits=0` (max(0, -1) clamp). Then `increment_bootstrap_credits(cap=10)` × 12 times; assert `bootstrap_credits=10` (min(+1, cap) clamp).

**Anchor 6** — `test_to_snapshot_copies_voice_evidence` (MIGRATED — Plan v1 §1 Surface 3)
- **Surface:** Seed Session via `s.evidence = dataclasses.replace(s.evidence, face_match_conf=0.95)`; call `_to_snapshot(s)`; assert `snap.evidence is not s.evidence` + `snap.evidence.face_match_conf == 0.95`.

**Anchor 7** — `test_no_direct_voice_evidence_mutation_outside_sessionstore` (forward tripwire, production-only)
- **Surface:** AST-walk **`core/session_state.py` ONLY** (production scope per §3 Q1 lock) → find every `Attribute` assignment target matching pattern `<base>.evidence.<field>`; assert all sites are inside `SessionStore` async methods. After P0.B1 closes, only `s.evidence = ...` rebinding is permitted in `SessionStore`; direct field assignment is forbidden by frozen=True at runtime + by this AST tripwire at CI time.
- **Test files exempt:** Tests legitimately construct VoiceEvidence variants for fixture seeding (e.g., `test_session_state_invariants.py:289` post-migration uses `s.evidence = dataclasses.replace(s.evidence, ...)`). The tripwire scans production only per Q1 lock.

### §2.4 — Re-baselined Q5 reading

**Plan v2 anchor count: 7.**
- vs auditor's small-spec mid 6 = `(7-6)/6 = +16.7%`
- **+16.7% is within ±15-30% → SLIGHT-DRIFT-UP** (NOT falsification trigger)
- Doctrine HOLDS; falsification not activated.

### §2.5 — Closure-actual reading projection

If closure lands at exactly 7 anchors (mechanical implementation of the 7-anchor plan) → +16.7% SLIGHT-DRIFT-UP. Doctrine holds; banked under `Auditor-Q5-estimates-trail-grep` trajectory.

If closure lands at 6 anchors (further consolidation discovered at impl time, e.g., Anchor 5 folds into Anchor 4) → 0% ON-TARGET. Doctrine bumps 7 → 8 supporting.

If closure lands at 8 anchors (parametrize fails / new test added during impl) → +33.3% FALSIFICATION TRIGGER. Doctrine demotes 7 → 6 supporting + memory file demotion. Architect must surface this honestly at closure-audit.

**Architect prediction:** 7 anchors at closure (matches Plan v2 lock; no further consolidation expected because Anchors 2+3 + Anchor 5 + Anchor 6 are conceptually distinct).

---

## §3. Q1 — AST tripwire scope LOCKED production-only

### §3.1 — Decision

Anchor 7's AST tripwire (`test_no_direct_voice_evidence_mutation_outside_sessionstore`) scans **`core/session_state.py` ONLY**. Test files + harness scripts + pipeline.py are NOT scanned.

### §3.2 — Rationale (per auditor's Q1 disposition)

- **Production drift surface only.** The bug we're preventing is "future `@dataclass` on VoiceEvidence missing frozen=True" or "future direct `.evidence.X = Y` mutation in SessionStore methods." Both surfaces live in production.
- **Tests legitimately construct/seed VoiceEvidence.** Test fixtures may use `replace()` pattern (which DOES require evidence rebinding) OR construct with explicit kwargs OR seed via the migrated `s.evidence = dataclasses.replace(s.evidence, ...)` pattern (the Anchor 6 migration). Scanning tests would false-positive on legitimate test patterns.
- **Same shape as P0.S6 D2/D3/D4 startup assertions** — production code surface only.
- **Mirrors `_REGISTRY_ALLOWLIST` precedent** at P0.S6: when scope is clear, narrow the surface.

### §3.3 — Future-proofing

If a future production code path (NOT in `core/session_state.py`) ever needs to mutate `VoiceEvidence`, the tripwire fires at CI. The maintainer must then either (a) add the new file to the tripwire's production-scope list with rationale (mirrors `_REGISTRY_ALLOWLIST` discipline), OR (b) refactor to use SessionStore's API. Forward-defense against drift.

---

## §4. Discipline counts at Plan v2 close

- **Spec-first review cycle:** 39 → 40 at Plan v2 close (per locked +1-per-artifact convention).
- **`### Phase-0-catches-wrong-premise`:** STAYS at 7 (Phase 0 ratification holds; closure entry reflects).
- **`### Phase-0-granular-decomposition-enables-accurate-estimates`:** STAYS at 7 supporting. **Falsification-watch DOWNGRADED** — Plan v2 anchor count at 7 lands at +16.7% SLIGHT-DRIFT-UP, NOT ≥30% trigger. Doctrine no longer at imminent demotion risk. Closure-conditional bump to 8 if closure lands at 6 anchors; HOLDS at 7 if closure lands at 7; demotes to 6 if closure lands at 8.
- **Strict-industry-standard mode:** 29 → 30 consecutive applications + 8 closures (in-flight to 9 at P0.B1 close).
- **`### Twin-filename-pitfall-prevention`:** STAYS at 6 instances + operational rule 4 banked.
- **Auditor-Q5:** 12 banked + 1 in-flight at +16.7% projection (SLIGHT-DRIFT-UP).
- **Spec-time grep-verification:** STAYS at 11 instances.
- **OPTIONAL-Plan-v2 path:** NOT achieved this cycle (Plan v2 needed for P1 + P2 + Q1). Stays at 1 proof case (P0.S3). Working hypothesis refined: OPTIONAL-v2 requires (a) clean Plan v1 absorption AND (b) clean Q5 math AND (c) clean cross-spec interactions; P0.B1 failed (b).
- **Discipline-count-bump-needs-explicit-justification:** stays at 7 (no preventive event at Plan v2).
- **Cross-cycle-handoff transparency precedent:** stays at 5 (no in-flight items at Plan v2 → closure handoff).
- **NEW operational rule 4 extension (Twin-filename-pitfall-prevention):** banked at CLAUDE.md:55 in Plan v1 close.

---

## §5. Open questions for auditor (0)

No new open questions at Plan v2. P1 + P2 + Q1 from Plan v1 verdict all locked per §1-§3.

**Architect prediction:** APPROVED 0 items → ship to developer per **medium-spec v1 → v2 floor cadence**. NOT OPTIONAL-Plan-v2 (auditor adjudication on P1 + P2 required this Plan v2 cycle, by design).

---

## §6. Banked dispositions for auditor v2 sign-off

**Quality bar:** Plan v2 absorbs both precision items + Q1 disposition with explicit math + locked anchor count. Clean re-baseline of the falsification-watch trajectory.

**Expected auditor verdict shape:**
- (i) APPROVED with 0 precision items → ship to developer (medium-spec v1 → v2 floor).
- (ii) APPROVED with 1 minor item — possible: auditor may surface anchor counting nuance (e.g., "Anchor 5 clamp test could also fold into parametrized Anchor 4"). Architect lean: 7 anchors is the honest minimum; further consolidation would obscure clamp-logic semantics. If auditor insists, Plan v3 absorbs.

**Falsification-watch consequence locked:** doctrine demotion will fire if closure lands at 8 anchors. Architect commits to honest count at closure — no silent over-bumping.

---

**End of Plan v2.** Ready to forward to auditor.
