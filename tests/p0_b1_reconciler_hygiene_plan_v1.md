# P0.B1 Plan v1 — frozen VoiceEvidence + mutation-site migration (Bug 4 only)

**Phase 0 base:** `tests/p0_b1_reconciler_hygiene_audit.md` (auditor APPROVED with Option A Narrow scope + sub-pattern A 7th instance ratified + P0.B prefix doctrine extension banked).

**Plan v1 absorbs:**
- **Auditor Option A Narrow** — P0.B1 ships Bug 4 only. Bug 5 → P0.B1.X follow-up.
- **Auditor §3.1-§3.4 pre-mortem prescriptions** (Pass-2 grep for VoiceEvidence constructors, fixture compatibility, mutation-site enumeration, P0.B1.X tracker filing).
- **Pass-2 grep results** — 15 mutation sites total (14 production at `core/session_state.py` + 1 test fixture at `tests/test_session_state_invariants.py:289`).
- **Pass-2 construction-site enumeration** — 15 construction sites across 4 test files, all zero-arg defaults (compatible with frozen migration).

---

## §1. D-decision (single — Option A Narrow scope)

### D1 — `VoiceEvidence` is `@dataclass(frozen=True, slots=True)` + 15 mutation sites migrate to `dataclasses.replace()`

**Surface 1 (decorator):** `core/session_state.py:18` — change `@dataclasses.dataclass(slots=True)` → `@dataclasses.dataclass(frozen=True, slots=True)`.

**Surface 2 (14 production mutation sites in `core/session_state.py`):**

| Line | Current code | Migrated code |
|---|---|---|
| 175-176 | `s.evidence.bootstrap_credits = bootstrap_credits` + `s.evidence.voice_sample_count = voice_sample_count` | Single `s.evidence = dataclasses.replace(s.evidence, bootstrap_credits=bootstrap_credits, voice_sample_count=voice_sample_count)` |
| 202-209 | 5 conditional field updates in `update_face_seen()` | Conditional-kwargs pattern per audit §3.3:<br>```python<br>_updates = {"face_match_conf": conf, "face_last_seen_ts": ts}<br>if anti_spoof_live is not None:<br>    _updates["anti_spoof_live"] = anti_spoof_live<br>if anti_spoof_score is not None:<br>    _updates["anti_spoof_score"] = anti_spoof_score<br>if anti_spoof_live is not None or anti_spoof_score is not None:<br>    _updates["anti_spoof_last_ts"] = ts<br>s.evidence = dataclasses.replace(s.evidence, **_updates)``` |
| 216-217 | 2 field updates in `update_voice_heard()` | Single `s.evidence = dataclasses.replace(s.evidence, voice_match_conf=conf, voice_last_heard_ts=ts)` |
| 223 | `s.evidence.voice_sample_count += 1` | `s.evidence = dataclasses.replace(s.evidence, voice_sample_count=s.evidence.voice_sample_count + 1)` |
| 229 | `s.evidence.bootstrap_credits = max(0, s.evidence.bootstrap_credits - 1)` | `s.evidence = dataclasses.replace(s.evidence, bootstrap_credits=max(0, s.evidence.bootstrap_credits - 1))` |
| 235 | `s.evidence.voice_sample_count = count` | `s.evidence = dataclasses.replace(s.evidence, voice_sample_count=count)` |
| 241 | `s.evidence.bootstrap_credits = n` | `s.evidence = dataclasses.replace(s.evidence, bootstrap_credits=n)` |
| 247 | `s.evidence.bootstrap_credits = min(s.evidence.bootstrap_credits + 1, cap)` | `s.evidence = dataclasses.replace(s.evidence, bootstrap_credits=min(s.evidence.bootstrap_credits + 1, cap))` |

**Surface 3 (1 test fixture mutation in `tests/test_session_state_invariants.py:289`):**

```python
# BEFORE (will raise FrozenInstanceError post-migration):
s.evidence.face_match_conf = 0.95

# AFTER:
s.evidence = dataclasses.replace(s.evidence, face_match_conf=0.95)
```

**Surface 4 (15 construction sites — NO CHANGE NEEDED):**

Pass-2 grep enumerated 15 construction sites of `VoiceEvidence(...)`:
- 13 in test files use default constructor `VoiceEvidence()` (no kwargs)
- 2 in `tests/test_session_store.py:74, 81` use default constructor

All construction sites use the zero-arg default constructor. The frozen migration does NOT change the constructor signature; default construction continues to work. No construction-site migration needed.

**Surface 5 (NO `dataclasses` import needed — already imported):**

`core/session_state.py:14` already has `import dataclasses`. No new import.

**Contract invariants after D1:**
- `VoiceEvidence` instances are immutable. Direct field assignment raises `FrozenInstanceError`.
- All field updates rebind `Session.evidence` to a new `VoiceEvidence` instance via `dataclasses.replace()`.
- `_to_snapshot()` at line 111 already does `evidence=dataclasses.replace(s.evidence)` — produces a frozen copy.
- `SessionSnapshot.evidence` is now structurally immutable (no longer reliant on caller-doesn't-mutate convention).

---

## §2. Pass-2 grep verification (auditor §3.1)

### §2.1 — VoiceEvidence constructor compatibility (15 sites)

All 15 construction sites verified zero-arg defaults:

```
test_pipeline.py:8237, 8261, 8303, 8327, 8463, 8496, 8520, 8565, 8577, 12281
tests/test_multispeaker_integration.py:151
tests/test_p0_s7_dd.py:310, 322
tests/test_session_store.py:74, 81
```

Frozen migration preserves zero-arg default constructor. No construction-site updates required.

### §2.2 — Production mutation sites (14, all in `core/session_state.py`)

Lines 175, 176, 202, 203, 205, 207, 209, 216, 217, 223, 229, 235, 241, 247 — all inside SessionStore async methods (lock-protected). All migrate per §1 D1 table.

### §2.3 — Test mutation sites (1 — `tests/test_session_state_invariants.py:289`)

Single seeding-line in `test_to_snapshot_copies_voice_evidence` (line 281-292). Migrates to `dataclasses.replace()`. Behavior unchanged: test still verifies `_to_snapshot` copies VoiceEvidence (not alias).

### §2.4 — Total mutation surface: 15 sites (14 production + 1 test). Pass-2 confirms 14→15 vs Phase 0 §1.1 estimate.

---

## §3. Multi-direction invariant trace (D1)

### D1 — `VoiceEvidence` frozen=True + 15-site migration

- **Forward (consumers of frozen invariant):**
  - `SessionStore.peek_snapshot()` callers — production at `pipeline.py` (routing path, anti-spoof gate, scene block) + tests. Frozen guarantee strengthens the snapshot contract; readers cannot accidentally mutate.
  - Type checkers (mypy) — frozen=True provides static guarantee against future mutation attempts.
  - P0.S1 anti-spoof read path — `snapshot.evidence.anti_spoof_live` now structurally immutable.
- **Backward (producers, the 15 sites):**
  - SessionStore async methods (14 production sites) — all migrate to `dataclasses.replace()`.
  - Direct test seeding (1 site in invariants test) — migrates per §1.
  - Default constructions (15 sites) — no change.
- **Sideways (parallel writers / mutation paths):**
  - No external code mutates `.evidence.X` (Pass-2 grep verified — only sites listed above).
  - `Session` dataclass field reassignment (`s.evidence = ...`) is the new mutation pattern; works because Session is NOT frozen and `evidence` is in Session's `__slots__` per line 43.
- **Lifecycle:**
  - `Session.__init__` constructs default `VoiceEvidence()` via `field(default_factory=VoiceEvidence)` at line 43 — works under frozen.
  - Async mutator updates rebind `s.evidence` to new frozen instance via `dataclasses.replace()`.
  - `_to_snapshot()` copies via `dataclasses.replace()` at line 111 — same pattern, produces fresh frozen instance for snapshot.
  - Snapshot consumed by peek caller, returned by value — frozen guarantee held across the lifetime.

---

## §4. Pre-mortem (10 failure modes — strict-mode floor + auditor's §3.1-§3.4)

### §4.1 — VoiceEvidence kwargs constructions in test fixtures (auditor §3.1) — RESOLVED
Pass-2 grep confirmed all 15 construction sites use zero-arg default. No kwargs migration needed. ✓

### §4.2 — frozen=True breaks existing tests (auditor §3.2) — RESOLVED
Pass-2 grep surfaced exactly 1 mutation site outside SessionStore (test_session_state_invariants.py:289). Migrated per §1 Surface 3. All other tests read `.evidence.X` but don't mutate. ✓

### §4.3 — 14-site SessionStore migration cleanliness (auditor §3.3) — VERIFIED
All 14 sites are inside async methods with lock held; sequential migration is mechanically clean. Multi-field-update sites (175-176, 202-209, 216-217) use conditional-kwargs pattern per §1 to minimize allocation count. ✓

### §4.4 — P0.B1.X tracker filed (auditor §3.4) — RESOLVED at §8 of this Plan
P0.B1.X (Bug 5 design dialogue) tracker filed at this Plan v1 §8 + cross-referenced in `to_be_checked.md` at closure.

### §4.5 — `dataclasses.replace()` on slotted-frozen dataclass
**Risk:** `dataclasses.replace()` on `@dataclass(frozen=True, slots=True)` works in Python 3.10+ but creates new instance via `__init__`. Defensive verify: round-trip test that every field survives the replace.
**Mitigation:** Plan v1 §6 test #2 is a deterministic round-trip exercising all 9 VoiceEvidence fields.

### §4.6 — `s.evidence = dataclasses.replace(...)` rebinding via slot
**Risk:** Session.evidence is in Session's `__slots__` per line 43. Reassignment via `s.evidence = ...` is permitted on slotted (non-frozen) classes. Verify by integration test.
**Mitigation:** Plan v1 §6 test #4 exercises `SessionStore.update_face_seen()` end-to-end + asserts `snapshot.evidence.face_match_conf` reflects the update.

### §4.7 — Concurrent peek_snapshot during evidence rebind
**Risk:** peek_snapshot is sync; if it fires DURING an async mutator's evidence rebind, what happens?
**Mitigation:** Single-threaded asyncio guarantee per session_state.py:5-9 docstring. The rebind `s.evidence = replace(...)` is one bytecode (STORE_ATTR) — GIL-atomic. peek_snapshot called immediately before or after sees consistent state (old or new instance — both frozen, both valid).

### §4.8 — Snapshot's evidence field annotation stays `VoiceEvidence`
**Risk:** `SessionSnapshot.evidence: VoiceEvidence` (line 77) — after frozen migration, annotation is unchanged. Mypy / static analyzers correctly infer frozen instance.
**Mitigation:** No annotation update needed.

### §4.9 — `test_session_state_invariants.py` AST scans (auditor §3.10)
**Risk:** The invariants test file may have AST scans that check VoiceEvidence dataclass shape. If those check for absence of `frozen=True` (anti-frozen expectation), they'd fail.
**Mitigation:** Reviewed file at Pass-2 — no anti-frozen AST checks found. The only relevant test (line 281) is the seed-and-snapshot copy test, which migrates per §1.

### §4.10 — Pre-existing tests' Session construction
**Risk:** Direct Session construction in tests (e.g., `Session(person_id="p1", ...)`) creates default VoiceEvidence via `field(default_factory=VoiceEvidence)`. After frozen, this still works because Session is NOT frozen; only VoiceEvidence is. The default_factory pattern is compatible.
**Mitigation:** Pass-2 grep found 0 instances of `Session(evidence=...)` with non-default kwargs — all use the default_factory.

---

## §5. Quality gate checklist (11 gates — all explicit)

- **[APPLIES] Correctness** — invariants traced 4-axis at §3.
- **[APPLIES] Security** — frozen VoiceEvidence eliminates accidental snapshot mutation; tightens P0.S1 anti-spoof read contract. `snapshot.evidence.anti_spoof_live` becomes structurally immutable from any consumer.
- **[N/A] Privacy** — no new facts or user-visible state. Structural dataclass change is internal-only.
- **[APPLIES] Performance** — `dataclasses.replace()` adds ~1µs per mutation site for frozen-instance allocation. 14 sites × <10 calls/second worst case = <140µs/s overhead. Negligible.
- **[APPLIES] Observability** — no new log lines. Mypy + AST invariant test are the observability surface. AssertionError on frozen mutation would surface immediately at runtime.
- **[APPLIES] Test pyramid** — unit (round-trip + invariant test) + AST invariant + behavioral (existing SessionStore test suite + new integration test).
- **[APPLIES] Regression guards** — deliberate-regression: revert `frozen=True` → AST invariant test fires. Deliberate-regression: keep one `.evidence.X = Y` mutation in SessionStore (revert one site) → FrozenInstanceError at runtime → test failure.
- **[APPLIES] Pre-mortem** — 10 failure modes at §4 (above 5-10 floor).
- **[APPLIES] Multi-direction trace** — §3.
- **[APPLIES] Backward compat** — fully additive at the contract level. Default constructors unchanged. Snapshot consumers see same API. Only mutation API changes (and only inside SessionStore + 1 test).
- **[APPLIES] Doc updates** — closure narrative to CLAUDE.md + parent + subdir complete-plan.md + to_be_checked.md + 1 memory entry (Phase 0 wrong-premise catch for sub-pattern A 7th instance).

**Total: 10 APPLIES + 1 N/A (privacy, with rationale).** Matches canonical shape.

---

## §6. Test plan (~6-8 logical anchors)

### Anchor 1 — VoiceEvidence decorator carries frozen=True + slots=True (AST invariant)
**Test:** `test_voice_evidence_decorator_is_frozen_and_slotted`
**Surface:** AST-walk `core/session_state.py` → find `class VoiceEvidence` → assert decorator's `frozen=True` AND `slots=True` keywords present.

### Anchor 2 — Round-trip preservation through dataclasses.replace
**Test:** `test_voice_evidence_replace_round_trip`
**Surface:** Construct VoiceEvidence with all 9 fields set to non-default values; `replace()` with one kwarg; assert other 8 fields preserved + that one field updated.

### Anchor 3 — Direct mutation raises FrozenInstanceError (defensive)
**Test:** `test_voice_evidence_direct_mutation_raises`
**Surface:** Construct VoiceEvidence; attempt `ev.anti_spoof_live = True`; assert `dataclasses.FrozenInstanceError`.

### Anchor 4 — SessionStore.update_face_seen integration (end-to-end)
**Test:** `test_session_store_update_face_seen_through_snapshot`
**Surface:** Open session via SessionStore; call `update_face_seen(conf=0.95, ts=now, anti_spoof_live=True, anti_spoof_score=0.85)`; peek snapshot; assert all 4 fields reflect the update + that `anti_spoof_last_ts` = ts.

### Anchor 5 — SessionStore.update_voice_heard integration
**Test:** `test_session_store_update_voice_heard_through_snapshot`
**Surface:** Open session; `update_voice_heard(conf=0.85, ts=now)`; peek snapshot; assert `voice_match_conf=0.85` + `voice_last_heard_ts=now` + `last_spoke_at=now` (Session field also updates).

### Anchor 6 — Bootstrap credits / voice sample count counter mutations
**Test:** `test_session_store_counter_mutations_preserve_invariants`
**Surface:** Open session with bootstrap_credits=5 + voice_sample_count=2; call `increment_voice_sample_count` + `decrement_bootstrap_credits`; peek; assert voice_sample_count=3 + bootstrap_credits=4. Then call `set_bootstrap_credits(0)` + `decrement_bootstrap_credits`; assert bootstrap_credits=0 (max(0, -1) clamp).

### Anchor 7 — `_to_snapshot` produces frozen evidence copy
**Test:** `test_to_snapshot_copies_voice_evidence` (MIGRATED from existing — line 281 of test_session_state_invariants.py)
**Surface:** Seed Session via `s.evidence = dataclasses.replace(s.evidence, face_match_conf=0.95)` (the test mutation site migration per §1 Surface 3); `_to_snapshot(s)`; assert `snap.evidence is not s.evidence` + `snap.evidence.face_match_conf == 0.95`.

### Anchor 8 — AST invariant: no `.evidence.X = Y` mutations outside SessionStore async methods (forward tripwire)
**Test:** `test_no_direct_voice_evidence_field_mutation_outside_sessionstore`
**Surface:** AST-walk `core/*.py` + `pipeline.py` → find every `Attribute` assignment target matching pattern `<base>.evidence.<field>`; assert all sites are inside `core/session_state.py` (SessionStore methods). After P0.B1 closes, only `s.evidence = ...` (rebinding) is permitted; direct field assignment is forbidden by frozen=True at runtime + by this AST tripwire at CI time.

**Total: 8 logical anchors.** Per auditor's small-spec band (4-8 mid 6), this is at the UPPER end of the band → projected SLIGHT-DRIFT-UP +33% vs mid (closure-conditional reading). If actual lands at 6-7 anchors via parametrize collapse → ON-TARGET.

---

## §7. Cross-spec impact analysis

- **P0.S1 (CLOSED 2026-05-20):** anti-spoof every face match. P0.B1 strengthens the read contract on `snapshot.evidence.anti_spoof_live` — supports P0.S1 invariants without changing them. No regression.
- **P0.7.1 (CLOSED):** SessionStore + SessionSnapshot foundation. P0.B1 extends the frozen-snapshot discipline to the VoiceEvidence inner field. Pattern continuation, no conflict.
- **P0.S7 (CLOSED 2026-05-21):** privacy_critical marker discipline. P0.B1 doesn't touch privacy-tagged code paths. No regression.
- **P0.B2 (PENDING — FAISS async rebuild):** independent subsystem (`core/db.py`). No interaction with VoiceEvidence.
- **P0.B1.X (DEFERRED — Bug 5 design dialogue):** independent decision. Filed per §8.

**No invariant impact on any closed spec.** P0.B1 is pure additive structural hardening.

---

## §8. P0.B1.X follow-up tracker — Bug 5 design dialogue (FILED per auditor §3.4)

**Status:** DEFERRED to follow-up cycle. Filed at Plan v1 to honor auditor's §3.4 mitigation.

**Design question (locked at Plan v1 for P0.B1.X Phase 0):**

> "In a multi-known room (n_active_sessions >= 2) with a mature holder (cur_holder_voice_n >= MATURE_SAMPLE_COUNT), a single-segment voice claim with confidence in (0.0, VOICE_RECOGNITION_THRESHOLD=0.25) currently opens a new_stranger session via `_p4_new_stranger_low_match`. Skeptic-1's audit (2026-05-21) argues this opens phantom strangers from background noise / cross-talk. The current cascade comment at `core/reconciler.py:560-567` warns against reordering due to 2026-04-28 Lexi misattribution prevention. Should this case (a) drop via `_p4_single_segment_mismatch` reorder, OR (b) preserve current behavior with strengthened bootstrap-cleanup, OR (c) split based on additional context (face presence, scene candidates, etc.)?"

**Pre-Phase-0 dialogue required with Jagan:**
1. Review the 2026-04-28 Lexi misattribution scenario — what was the actual failure mode that the current ordering prevents?
2. Review the audit's "phantom stranger" claim — name a specific real scenario where the current behavior opens an unwanted session.
3. Evaluate the 3 design options (drop / preserve / context-split) against both scenarios.
4. Lock the design decision before P0.B1.X Phase 0 audit.

**P0.B1.X cadence prediction (after design lock):** 1-2 D-decisions (depending on chosen option) + low fan-out (cascade-only + test updates) → v1 only OPTIONAL-Plan-v2 path.

**Cross-reference at closure:** `to_be_checked.md` row + parent `complete-plan.md` P0.B1.X entry.

---

## §9. Banked dispositions for auditor v1 review

- **`### Phase-0-catches-wrong-premise` doctrine:** 6 → 7 ratified at auditor Phase 0 verdict. Closure entry will reflect.
- **`### Phase-0-granular-decomposition` doctrine:** STAYS at 7 supporting (closure-conditional bump to 8 if P0.B1 closes ON-TARGET vs mid 6, band 4-8).
- **`### Spec-first review cycle`:** 38 → 39 at Plan v1 close per locked +1-per-artifact convention.
- **Strict-industry-standard mode:** 28 → 29 consecutive applications + 8 closures (in-flight to 9 at P0.B1 close).
- **`### Twin-filename-pitfall-prevention`:** 6 instances + NEW operational rule 4 (P0.B prefix) banked at CLAUDE.md doctrine site.
- **Auditor-Q5 prediction:** 8 anchors vs mid 6 = +33% SLIGHT-DRIFT-UP under re-baselined methodology. If closure absorbs parametrize collapse to 6-7 anchors → ON-TARGET. If 8 holds → SLIGHT-DRIFT but within ±30% falsification tolerance.
- **`Phase-0-catches-scope-narrowing` informal observation:** 1 instance banked (P0.B1 Phase 0 narrowed pre-audit framing from 2 bugs → 1 bug + 1 follow-up). NOT elevated — auditor disposition holds until 3+ pure-narrowing instances accumulate without sub-pattern-A confounding.
- **OPTIONAL-Plan-v2 path candidate:** P0.B1 = 2nd OPTIONAL-Plan-v2 proof case after P0.S3 if Plan v1 absorbs 0 precision items at auditor review.

---

## §10. Open questions for auditor (1)

**Q1.** Anchor 8 forward-tripwire — should it scan `tests/*.py` too, or only production code (`core/*.py` + `pipeline.py`)? Architect lean: production code only (tests are allowed to have direct mutation patterns for fixture seeding, though they SHOULD also use `dataclasses.replace()` for consistency). If auditor wants exhaustive scan, expand Anchor 8 scope at Plan v2.

---

**End of Plan v1.** Ready to forward to auditor.

**Architect prediction:** APPROVED 0 items → ship to developer per OPTIONAL-Plan-v2 path. Developer contract: ~3-4 hours (15 mutation-site migration is mechanical; tests stay green by design).
