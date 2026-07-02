# P0.B1 Phase 0 audit — Reconciler Hygiene (Bug 4 + Bug 5)

**Spec ID:** P0.B1 — first cycle in the "Board-bug remediation" track (the 10 bugs surfaced by skeptic1/skeptic2/ceo-evening board meetings 2026-05-20/21). Naming convention `p0_b{N}_*` for board-bug specs, distinct from P0.S* (security track) + P0.R* (resilience track).

**Twin-filename pitfall check:** no existing `p0_b1_*` files in `tests/`. Clean disambiguation. **6th preventive instance** of `### Twin-filename-pitfall-prevention` doctrine.

**Pre-audit premise (from board-meeting consolidation 2026-05-21):**
- **Bug 4 (BUG-SS-1):** `core/session_state.py::VoiceEvidence` is not `frozen=True`. Anti-spoof reads via `snapshot.evidence.anti_spoof_live` can race with background updates because the dataclass is mutable.
- **Bug 5 (BUG-REC-1):** `_p4_single_segment_mismatch` is "dead" in the reconciler cascade. Multi-person rooms: single-segment low-confidence voice turns spawn phantom strangers via `_p4_new_stranger_low_match` instead of dropping via `_p4_single_segment_mismatch`. Simple reorder fixes.

**Cadence prediction (initial):** 2 D-decisions / single subsystem / low fan-out → **v1 only OPTIONAL-Plan-v2 path**.

**REVISED CADENCE AFTER PHASE 0 (see §2):** Bug 5's pre-audit premise is partially-WRONG. The rule is NOT dead and the proposed reorder would break locked contract tests. Phase 0 surfaces a design-decision question that requires reviewer adjudication. P0.B1 narrows to Bug 4 only. Bug 5 splits.

---

## §1. Grep-verified surface (Pass-1)

### §1.1 Bug 4 — VoiceEvidence is mutable (CONFIRMED, clean fix)

**Production surface:** `core/session_state.py:18-28`

```python
@dataclasses.dataclass(slots=True)         # ← MISSING frozen=True
class VoiceEvidence:
    face_match_conf:     float = 0.0
    face_last_seen_ts:   float = 0.0
    anti_spoof_live:     bool  = False
    anti_spoof_score:    float = 0.0
    anti_spoof_last_ts:  float = 0.0
    voice_match_conf:    float = 0.0
    voice_sample_count:  int   = 0
    voice_last_heard_ts: float = 0.0
    bootstrap_credits:   int   = 0
```

**Snapshot defense already in place** (`_to_snapshot()` at line 100, 111):
```python
evidence=dataclasses.replace(s.evidence),  # copy VoiceEvidence
```

So the snapshot HAS an isolated `VoiceEvidence` instance — but the copy is still mutable. Defensive correctness gap: a consumer could mutate `snap.evidence.anti_spoof_live = True` accidentally and corrupt the snapshot's "immutable invariant" claim.

**Mutation sites enumerated (Pass-2 grep candidates):**

| File | Line | Pattern |
|---|---|---|
| `core/session_state.py` | 175 | `s.evidence.bootstrap_credits = bootstrap_credits` |
| `core/session_state.py` | 176 | `s.evidence.voice_sample_count = voice_sample_count` |
| `core/session_state.py` | 202 | `s.evidence.face_match_conf = conf` |
| `core/session_state.py` | 203 | `s.evidence.face_last_seen_ts = ts` |
| `core/session_state.py` | 205 | `s.evidence.anti_spoof_live = anti_spoof_live` |
| `core/session_state.py` | 207 | `s.evidence.anti_spoof_score = anti_spoof_score` |
| `core/session_state.py` | 209 | `s.evidence.anti_spoof_last_ts = ts` |
| `core/session_state.py` | 216 | `s.evidence.voice_match_conf = conf` |
| `core/session_state.py` | 217 | `s.evidence.voice_last_heard_ts = ts` |
| `core/session_state.py` | 223 | `s.evidence.voice_sample_count += 1` |
| `core/session_state.py` | 229 | `s.evidence.bootstrap_credits = max(0, s.evidence.bootstrap_credits - 1)` |
| `core/session_state.py` | 235 | `s.evidence.voice_sample_count = count` |
| `core/session_state.py` | 241 | `s.evidence.bootstrap_credits = n` |
| `core/session_state.py` | 247 | `s.evidence.bootstrap_credits = min(s.evidence.bootstrap_credits + 1, cap)` |

**14 mutation sites total, ALL within SessionStore async methods (lock-protected).** Outside the lock, no other production code mutates `.evidence.X`. Test files read `.evidence.X` (test_pipeline.py + test_session_store.py + test_session_state_invariants.py) but don't mutate.

**Multi-direction trace (per strict-mode §2):**
- **Forward:** every consumer reading `snapshot.evidence.X` benefits from frozen guarantee. Production readers: pipeline.py routing path + anti_spoof gate (P0.S1 closed). Test readers: 6 grep-confirmed read sites.
- **Backward:** SessionStore async methods (the 14 mutation sites above) are the producers. All write via direct attribute assignment today; need migration to `dataclasses.replace()`.
- **Sideways:** Session dataclass (line 31) is NOT frozen (correctly — it's the live mutable state). Only `VoiceEvidence` (inner) and `SessionSnapshot` (outer) are candidates for frozen.
- **Lifecycle:** Session.__init__ creates default VoiceEvidence → async mutator updates fields → `_to_snapshot()` copies via `dataclasses.replace()` → snapshot returned to peek caller → eventually GC'd.

**Verdict:** Bug 4 is a **clean defensive structural fix**. No design change. Pure migration: 14 mutation sites → `dataclasses.replace()` calls + `frozen=True` flag. Same shape as P0.7.1 SessionSnapshot frozen migration.

### §1.2 Bug 5 — `_p4_single_segment_mismatch` is NOT dead (PHASE 0 PREMISE FALSIFIED)

**Pre-audit premise (verbatim from skeptic1-2026-05-21 ATTACK + ceo-evening-2026-05-21):**
> "BUG-REC-1: when a real household has 2+ people, single-segment low-confidence voice turns open phantom stranger sessions instead of being dropped... Fix: reorder _p4_single_segment_mismatch before _p4_new_stranger_low_match in the cascade."

**Phase 0 grep verdict: PARTIALLY FALSIFIED.** The pre-audit framing has THREE distinct errors:

#### Error 1 — Rule is NOT dead

**Production code at `core/reconciler.py:668-698`:**

```python
def _p4_single_segment_mismatch(...) -> Optional[RoutingDecision]:
    if (claim.pid is None
            and session.cur_pid is not None
            and VOICE_ROUTING_SINGLE_SEGMENT_MISMATCH_ENABLED      # True per config.py:891
            and claim.n_diarize_segments == 1
            and claim.confidence < VOICE_ROUTING_STRANGER_FLOOR    # 0.30 per config.py:882
            and claim.utterance_duration >= VOICE_ROUTING_MIN_AUDIO_FOR_SCORE
            and session.cur_holder_voice_n >= VOICE_ACCUM_MATURE_SAMPLE_COUNT
            and session.n_active_sessions >= 2):
```

**Production code at `core/reconciler.py:653-665`:**

```python
def _p4_new_stranger_low_match(...) -> Optional[RoutingDecision]:
    if (claim.pid is None
            and session.cur_pid is not None
            and claim.confidence < VOICE_RECOGNITION_THRESHOLD     # 0.25 per config.py:28
            and claim.confidence != 0.0):
```

**Config values verified (Pass-1 grep):**
- `VOICE_RECOGNITION_THRESHOLD = 0.25` (`core/config.py:28`)
- `VOICE_ROUTING_STRANGER_FLOOR = 0.30` (`core/config.py:882`)
- **0.25 < 0.30** — STRANGER_FLOOR is STRICTLY HIGHER than RECOGNITION_THRESHOLD

**Confidence-band analysis:**
- `confidence ∈ (0.0, 0.25)`: `_p4_new_stranger_low_match` fires first → `new_stranger` action. `_p4_single_segment_mismatch` unreachable.
- `confidence ∈ [0.25, 0.30)`: `_p4_new_stranger_low_match` does NOT fire (predicate requires `< 0.25`). Cascade continues. `_p4_single_segment_mismatch` fires if other gates pass.
- `confidence == 0.0`: `_p4_new_stranger_low_match` does NOT fire (`!= 0.0` guard). Cascade continues. `_p4_single_segment_mismatch` could fire (`0.0 < 0.30`) but typically `_p4_voice_ambiguous_no_candidates` (which I haven't fully traced yet) is the canonical zero-confidence handler.
- `confidence >= 0.30`: neither fires.

**Existing test `test_p4_single_segment_mismatch_drops_in_multi_known` at `tests/test_reconciler.py:1097-1141`:**

```python
claim = IdentityClaim(
    pid=None, confidence=0.27,                    # ← in [0.25, 0.30) band
    n_diarize_segments=1, utterance_duration=1.5, reasoning="test",
)
# ...
assert decision.action == "single_segment_voice_mismatch"
assert decision.rule_fired == _p4_single_segment_mismatch.__name__
```

The test EXERCISES the rule SUCCESSFULLY with `confidence=0.27`. **The rule fires in production today** in the [0.25, 0.30) band. NOT dead.

#### Error 2 — Proposed reorder breaks locked contract tests

**Contract test `test_c15_new_stranger_low_match_opens_stranger` at `tests/test_p10_reconciler_contract.py:245-260`:**

```python
def test_c15_new_stranger_low_match_opens_stranger():
    claim = _claim(pid=None, confidence=0.15,             # ← in (0, 0.25) band
                   utterance_duration=2.0, n_diarize_segments=1)
    session = _session()                                   # default: n_active=1, cur_holder=20 (MATURE)
    decision = reconcile(claim, _presence(), session)
    assert decision.action == "new_stranger"
```

**The next contract test `test_c16_single_segment_mature_low_score_drops` at line 263-283 explicitly documents the design intent:**

```python
"""C16 (P4c): n_diarize==1 + v_score < STRANGER_FLOOR + mature holder
+ audio >= 0.5 + n_active >= 2 → single_segment_voice_mismatch.

Uses confidence=0.27 to land in [VOICE_RECOGNITION_THRESHOLD=0.25,
STRANGER_FLOOR=0.30) — outside _p4_new_stranger_low_match's
`confidence < 0.25` range so the cascade reaches P4c. For
confidence in (0.0, 0.25) the new-stranger rule wins (audited
behavior preserved from legacy P4b/P4c ordering)."""
```

The contract test docstring **EXPLICITLY locks the current ordering as intentional design**: confidence in (0.0, 0.25) → new_stranger; confidence in [0.25, 0.30) → single_segment drop. The proposed reorder collapses this distinction.

**Negative contract `test_n5_drop_skipped_for_bootstrapping_holder` at line 420-439:**

```python
"""N5: drop on n_diarize==1 + low score must NOT fire when holder
is bootstrapping (immature gallery). Drop is only safe for mature
holders — bootstrapping strangers expect their own voice to score
poorly against the thin profile.
"""
claim = _claim(pid=None, confidence=0.10, ...)            # ← (0, 0.25) band
session = _session(cur_pid="stranger_x", cur_holder_voice_n=2, ...)  # bootstrapping
decision = reconcile(claim, _presence(), session)
assert decision.action != "single_segment_voice_mismatch"  # NOT dropped
```

This test passes TODAY because `_p4_new_stranger_low_match` fires first (single_segment never reached due to cur_holder bootstrap). After reorder: still passes because `cur_holder_voice_n=2 < MATURE` keeps single_segment from firing. But the test's reasoning ("drop is only safe for mature holders") would no longer be naturally enforced by cascade order — it would be enforced solely by the mature-holder gate inside `_p4_single_segment_mismatch`.

**Existing test `test_p4_new_stranger_low_match_negative_confidence` at `tests/test_reconciler.py:512-551`:**

```python
claim = IdentityClaim(pid=None, confidence=-0.08, n_diarize_segments=1, utterance_duration=1.5, ...)
session = SessionState(cur_pid="jagan_abc", cur_person_type="best_friend",
                       n_active_sessions=1,           # ← SOLO ROOM
                       cur_holder_voice_n=10, ...)
decision = reconcile(claim, presence, session)
assert decision.action == "new_stranger"
assert decision.rule_fired == _p4_new_stranger_low_match.__name__
```

After reorder: this test STILL passes because `n_active_sessions=1` keeps single_segment from firing (it requires `>= 2`). ✓ Reorder doesn't break this test.

#### Error 3 — Cascade docstring explicitly locks the order against reordering

**Production code at `core/reconciler.py:560-567`:**

```python
# ⚠ Inner ordering is load-bearing:
#   _p4_multi_segment_mismatch
#   _p4_pyannote_vouched_stranger     ← MUST fire before _p4_voice_ambiguous_no_candidates
#   _p4_new_stranger_low_match
#   _p4_single_segment_mismatch
#   _p4_voice_ambiguous_no_candidates
#   _p4_voice_ambiguous_with_candidates
# Reordering re-introduces the 2026-04-28 Lexi misattribution.
```

The comment EXPLICITLY warns against the reorder + names a regression scenario ("2026-04-28 Lexi misattribution"). This is a load-bearing convention.

**Verdict on Bug 5 pre-audit premise:**

The skeptic-1 / ceo-evening framing — "dead rule, simple cascade reorder fix" — is **PARTIALLY WRONG**:
1. ❌ Rule is NOT dead — fires in [0.25, 0.30) band per existing test.
2. ❌ Reorder is NOT simple — collapses INTENTIONAL design distinction (low-conf below 0.25 = open new_stranger; mid-conf [0.25, 0.30) = drop).
3. ⚠️ Underlying concern IS valid — multi-known mature-holder rooms DO open new_stranger for confidence in (0.0, 0.25) single-segment turns. Whether that's "phantom stranger" or "legitimate stranger entry" is a DESIGN DECISION not a bug.

**`### Phase-0-catches-wrong-premise` doctrine — 7th instance candidate.** This is a textbook wrong-premise catch via grep verification. (Sub-pattern A goes from 6 → 7 at closure if Jagan adjudicates that Phase 0 surfaced the gap.)

---

## §2. Scope adjudication — P0.B1 narrows

**Honest scope discipline (strict-mode §1):** Phase 0 reveals Bug 5 is not what was framed. Re-scope explicitly.

**Three options for Jagan:**

### Option A — Narrow scope (RECOMMENDED)
- **P0.B1** ships **Bug 4 ONLY** (frozen VoiceEvidence + 14 mutation site migration). Clean defensive structural fix, no design change.
- **P0.B1.X (NEW follow-up spec)** opens the design question for Bug 5 with reviewer/architect dialogue:
  - "Should mature multi-known single-segment low-score (confidence < 0.25) → drop instead of new_stranger?"
  - Pre-design conversation with Jagan + reviewer required before Phase 0 audit can lock D-decisions.
  - Requires updating C15 contract test docstring + cascade comment + N5 negative test reasoning + new regression coverage for the 2026-04-28 Lexi case under the new behavior.

### Option B — Wide scope (design change adopted)
- P0.B1 ships Bug 4 + Bug 5 with Bug 5 framed as a DESIGN CHANGE:
  - Reorder cascade.
  - Update C15 contract test + N5 narrative.
  - Replace cascade comment with new "load-bearing ordering" rationale.
  - Add deliberate-regression test for 2026-04-28 Lexi scenario under new behavior.
- Cadence pushes from "v1 only" → "v1 → v2 floor" (4-5 D-decisions; multi-test ripple).

### Option C — Narrow scope, defer Bug 5 entirely
- P0.B1 ships Bug 4 ONLY.
- Bug 5 is "WONTFIX — current behavior is intentional design; phantom-stranger concern is acknowledged but accepted-with-rationale (real-stranger-entry is the more common case; bootstrap-credit gates and dream-loop pruning handle phantom cleanup)."
- Update the board-meeting consolidation memo with the WONTFIX adjudication.

**Architect lean:** **Option A.** The audit's underlying concern (phantom strangers in mature multi-known rooms) is real even if framed wrong. Deferring it to a follow-up spec with proper design dialogue preserves quality without delaying the clean Bug 4 fix.

---

## §3. Pre-mortem (10 failure modes — strict-mode floor 5-10)

### §3.1 — VoiceEvidence frozen=True breaks an undiscovered mutation site
**Risk:** Pass-2 grep at Plan v1 may surface additional `.evidence.X = Y` mutations in production code I didn't find at Pass-1.
**Mitigation:** Plan v1 Pass-2 grep + AST scan for `Attribute` targets matching `s.evidence.*` or `evidence.*` (skip docstrings). If new sites surface, absorb into D1 mutation-migration count.

### §3.2 — `dataclasses.replace()` semantics on slots
**Risk:** Combining `slots=True` + `frozen=True` works in Python 3.10+, but `dataclasses.replace()` on a slotted frozen dataclass has subtle behavior — assigns via `__init__`, not attribute. Defensive verify with a unit test.
**Mitigation:** Plan v1 §X includes a unit test that round-trips `VoiceEvidence` through `dataclasses.replace()` + asserts every field preserved.

### §3.3 — Multi-field replace efficiency
**Risk:** Lines 202-209 update 5 evidence fields conditionally in one method. Naive migration: 5 sequential `dataclasses.replace()` calls = 5 new VoiceEvidence instances allocated. Performance gnat.
**Mitigation:** Migrate to single `dataclasses.replace()` with conditional kwargs:
```python
_updates = {"face_match_conf": conf, "face_last_seen_ts": ts}
if anti_spoof_live is not None:
    _updates["anti_spoof_live"] = anti_spoof_live
if anti_spoof_score is not None:
    _updates["anti_spoof_score"] = anti_spoof_score
if anti_spoof_live is not None or anti_spoof_score is not None:
    _updates["anti_spoof_last_ts"] = ts
s.evidence = dataclasses.replace(s.evidence, **_updates)
```
Lock the kwargs-dict pattern in Plan v1.

### §3.4 — `s.evidence = ...` reassignment of mutable Session field
**Risk:** Session itself is `@dataclass(slots=True)` (not frozen). Assigning `s.evidence = dataclasses.replace(s.evidence, ...)` rebinds the field. Session's slots include `evidence` — this works, but slot dataclasses raise on reassignment of NEW attribute names. Verify slot includes `evidence` (it does per line 43).
**Mitigation:** Plan v1 unit test that exercises a full evidence-mutation cycle via `update_face_seen()` and asserts the field is rebindable.

### §3.5 — Concurrent peek_snapshot during in-progress evidence rebind
**Risk:** Async lock held during evidence rebind, but peek_snapshot is SYNC (per session_state.py docstring contract: "peek_snapshot() is sync-safe under single-threaded asyncio + no-sync-mutators + frozen-snapshot assumptions"). What happens if peek_snapshot fires DURING an evidence rebind?
**Mitigation:** Single-threaded asyncio guarantee: no other coroutine can run while the async mutator's evidence rebind is executing synchronously. The rebind is one Python statement (`s.evidence = replace(...)`) — atomic under GIL. peek_snapshot called immediately before or after sees consistent state (either old `s.evidence` reference or new one — both are valid frozen VoiceEvidence instances).

### §3.6 — Test discovery: `s.evidence` in test seeding code
**Risk:** Tests may construct Sessions directly and assign `s.evidence.X = Y` for seeding (bypassing SessionStore). Pass-2 grep didn't find any production callers but might miss test-side patterns.
**Mitigation:** Pass-2 grep at Plan v1 includes test files. Tests that seed via direct mutation get migrated to `Session(..., evidence=VoiceEvidence(...))` constructor pattern.

### §3.7 — Bug 5 scope creep contamination
**Risk:** If Bug 5 split into P0.B1.X (Option A), there's a temptation to "while I'm here, just add the reorder safely." Pure scope creep.
**Mitigation:** Hard discipline. P0.B1 = Bug 4 ONLY. No reconciler edits. No cascade comment touches. Confirmed at closure.

### §3.8 — Cascade comment becomes stale on Bug 4 closure
**Risk:** If Bug 4 closes and someone reads the cascade comment at line 560-567, they might think "2026-04-28 Lexi misattribution" is unresolved. The comment is correct — it warns AGAINST reordering — but readers seeing P0.B1 (frozen VoiceEvidence) might conflate.
**Mitigation:** No cascade comment touch in P0.B1. P0.B1.X (when filed) revisits the comment as part of the design adjudication.

### §3.9 — Snapshot's `evidence` field type annotation
**Risk:** `SessionSnapshot.evidence: VoiceEvidence` (line 77) — after frozen migration, the type annotation is unchanged but the semantic strengthens. Consumers reading `snap.evidence.X` get the same fields back; no change there. But type checkers might flag if any code assigns to `snap.evidence.X = Y` post-migration — desirable (catches accidental mutation).
**Mitigation:** No annotation change needed. Plan v1 §X notes that mypy will catch any `snap.evidence.X = Y` post-migration; document this as an emergent invariant.

### §3.10 — Test infrastructure coverage
**Risk:** `tests/test_session_state_invariants.py` may have AST scans that check VoiceEvidence dataclass shape. If those don't account for frozen=True, they could fail or false-positive.
**Mitigation:** Pass-2 grep at Plan v1 reads `tests/test_session_state_invariants.py` to find any structural assertions on VoiceEvidence. Update tests in lockstep.

---

## §4. D-decisions (under Option A — Bug 4 only)

### D1 — `VoiceEvidence` frozen + migration of 14 mutation sites in `core/session_state.py`
- **Surface:** `core/session_state.py:18-19` (add `frozen=True` to decorator) + lines 175-247 (14 mutation sites → `dataclasses.replace()` per the §3.3 multi-field-update pattern).
- **Contract:** `VoiceEvidence` is `@dataclass(frozen=True, slots=True)` after migration. All field updates rebind via `s.evidence = dataclasses.replace(s.evidence, ...)`.
- **Test:** unit-level round-trip through `dataclasses.replace()` + full integration via `SessionStore.update_face_seen()` exercise + AST invariant test that `VoiceEvidence` carries both `frozen=True` and `slots=True` decorators.

---

## §5. Quality gate checklist (11 gates per strict-mode §4)

- **[APPLIES] Correctness** — invariants traced 4-axis at §1.1.
- **[APPLIES] Security** — frozen VoiceEvidence eliminates accidental snapshot mutation; tightens P0.S1 anti-spoof read contract (snapshot.evidence.anti_spoof_live now structurally immutable from consumer side).
- **[N/A] Privacy** — no new facts/state; structural dataclass change is not user-visible.
- **[APPLIES] Performance** — minor allocation overhead from `dataclasses.replace()` per mutation. ~14 sites; each fires <10 times/second in worst case. Negligible.
- **[APPLIES] Observability** — no new log lines; existing SessionStore logs unchanged. Mypy + tests are the observability surface.
- **[APPLIES] Test pyramid** — unit (round-trip) + AST invariant + behavioral (existing SessionStore test suite stays green).
- **[APPLIES] Regression guards** — deliberate-regression: revert frozen=True → AST invariant test fires.
- **[APPLIES] Pre-mortem** — 10 failure modes in §3.
- **[APPLIES] Multi-direction trace** — §1.1 (forward/backward/sideways/lifecycle).
- **[APPLIES] Backward compat** — additive: frozen=True + migration to `dataclasses.replace()`. Existing reader code unchanged.
- **[APPLIES] Doc updates** — closure narrative to CLAUDE.md + parent + subdir complete-plan.md + to_be_checked.md + 1 memory entry (Phase 0 wrong-premise catch).

**Total: 10 APPLIES + 1 N/A (privacy).** Matches canonical shape.

---

## §6. Cross-spec impact analysis

- **P0.S1 (CLOSED 2026-05-20):** anti-spoof every face match. P0.B1 D1 strengthens the read contract on `snapshot.evidence.anti_spoof_live` — supports P0.S1 invariants without changing them. No regression.
- **P0.7.1 (CLOSED earlier):** SessionStore + SessionSnapshot. P0.B1 D1 extends the frozen-snapshot discipline to VoiceEvidence inner field. Same pattern.
- **P0.S7 (CLOSED 2026-05-21):** privacy_critical marker + AST tripwires. None of the 14 mutation sites touch privacy invariants.
- **P0.S5 (CLOSED 2026-05-21):** wrap_user_input. Distinct subsystem.
- **All other P0.S* closed cycles:** no surface overlap.
- **P0.B1.X (deferred Bug 5):** decoupled from D1 by Option A. No invariant interaction.

---

## §7. Banked dispositions for Plan v1 review

- **`### Phase-0-catches-wrong-premise` doctrine:** **7th instance candidate** (P0.B1 §1.2). Premise reset from "dead rule simple reorder" → "rule reachable + design decision required." Bumps 6 → 7 at closure conditional on Jagan adjudicating Option A.
- **`### Phase-0-granular-decomposition` doctrine:** STAYS at 7 supporting (closure-conditional bump to 8 if P0.B1 lands ON-TARGET under re-baselined methodology).
- **`### Spec-first review cycle`:** 37 → 38 at Phase 0 close per locked +1-per-artifact convention.
- **Strict-industry-standard mode:** 27 → 28 consecutive applications + 8 closures (in-flight to 9 at P0.B1 close).
- **`### Twin-filename-pitfall-prevention`:** **6th preventive instance** (filename `p0_b1_reconciler_hygiene_audit.md` disambiguates against zero existing p0_b1_*).
- **`### Phase-0-catches-scope-expansion` informal:** STAYS at 2 (P0.B1 NARROWS scope, not expands — distinct from scope-expansion pattern).
- **NEW informal observation candidate — `Phase-0-catches-scope-narrowing`:** P0.B1 Phase 0 NARROWS pre-audit framing from 2 bugs → 1 bug + 1 design-question follow-up. Distinct from scope-expansion (Phase 0 finds MORE work needed) — this is Phase 0 finds LESS but DIFFERENT work needed. 1 instance candidate; watch future cycles for recurrence.

---

## §8. Open questions for auditor (3)

**Q1.** Adjudication on Option A vs B vs C for Bug 5 scope. Architect lean: Option A (narrow + defer). If auditor agrees, Plan v1 locks Bug 4 only + files P0.B1.X follow-up. If auditor leans B (wide scope adopted), Plan v1 expands to 4-5 D-decisions + v1 → v2 cadence.

**Q2.** Sub-pattern A 7th instance — does the Phase 0 finding qualify as a wrong-premise catch? The pre-audit framing was "dead rule simple reorder"; Phase 0 grep reveals "reachable rule + design decision." Architect reads this as wrong-premise. If auditor reads as "wrong-mechanism-correct-direction" (the underlying concern IS valid even if framing is off), the bump might be marginal.

**Q3.** New informal observation — `Phase-0-catches-scope-narrowing` — is this a legitimate distinct pattern from scope-expansion, or just "scope refinement" without doctrine signal? Banked observation only if auditor agrees it's distinct.

---

**End of Phase 0 audit.** Ready to forward to auditor for Phase 0 review.

**Architect prediction:** auditor approves Option A. P0.B1 narrows to Bug 4 only. Plan v1 forecasts ~6-8 test anchors (D1 unit + AST + behavioral + regression). Cadence stays **v1 only OPTIONAL-Plan-v2 path**.
