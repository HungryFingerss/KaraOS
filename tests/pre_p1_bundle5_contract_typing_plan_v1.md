# Pre-P1 Bundle 5 — Contract Typing (MF7 + MF8) Plan v1 (2026-05-29)

**Cycle**: Pre-P1 must-fix Bundle 5 (Contract Typing) — FINAL Pre-P1 bundle
**Predecessor**: `tests/pre_p1_bundle5_contract_typing_audit.md` (Phase 0 NOT CLEAN — 1 BLOCKING PI on Q3 + Q1/Q2 ratified + 2 scope refinements; auditor verdict in `info.md` 2026-05-29)
**Discipline**: Strict-mode; Q3 BLOCKING PI absorbed → cycle escalates beyond OPTIONAL-Plan-v2 candidacy (adjudicated at this Plan v1 review)
**Architect**: Claude
**Auditor**: External

---

## §0 Procedural commitments + Q3 BLOCKING PI absorption

All Phase 0 §0 commitments PRESERVED. NEW for Plan v1:

### §0 NEW absorption event — Q3 BLOCKING PI (sole-construction-site premise FALSE)

**Phase 0 §1.2 + Q3 rested on a grep-falsified premise**: "IdentityClaim is CONSTRUCTED at `core/reconciler.py:112`" as the single chokepoint. The auditor's independent `IdentityClaim\(` grep across all production `.py` files (which the architect's Phase 0 failed to run — it grepped `IdentityClaim(` only within `reconciler.py`) found **3 production construction paths, not 1**.

**Architect BIDIRECTIONAL re-verification at Plan v1 drafting** (`IdentityClaim\(` grep across all `*.py`, 2026-05-29) — confirms the auditor exactly:

| # | Path | Sites | Role |
|---|---|---|---|
| 1 | `core/voice_channel.py::identify_speaker` | 162, 171, 183, 200, 217 (5 sites) | The pure voice channel (Phase-3 shadow today @ pipeline.py:8032, Phase-4 primary at cutover). 4 sites (162/171/183/200) are no-signal-by-construction; 217 success path takes the flag from `identify_fn`'s return. |
| 2 | `core/reconciler.py:112::_build_routing_inputs` | 112 (1 site) | Assembles a claim from raw `v_pid`/`v_score` kwargs (the architect's claimed sole site — the LEGACY pipeline path). |
| 3 | `core/event_log/types.py:124::_identity_claim_from_dict` | 124 (1 site) | Replay reconstruction. Enumerates fields explicitly (NOT `dataclasses.asdict`) → MUST be updated for the new field. `IdentityClaimPayload` (237) wraps it — P0.0.7-class serialize→JSON→reconstruct round-trip. |

= **7 production construction sites across 3 files** (+ 5 test-fixture sites in `tests/fixtures/event_log_fixtures.py` + ~28 in `tests/test_reconciler.py` — test-side, mostly default-`False`-safe; the few constructing no-signal cases get the flag).

**Why the Q3(b)/(c) construction-chokepoint CANNOT work** (auditor §2, architect-confirmed): setting `confidence_is_no_signal=(v_score == 0.0)` at reconciler.py:112 (a) misses the 5 voice_channel.py sites entirely (their claims would carry the `=False` default while being genuinely no-signal), (b) misses the event-log payload, (c) even at one site, `== 0.0` inference re-couples to the exact convention MF7 exists to remove. **The no-signal-vs-coincidental-0.0 distinction is knowable ONLY at `voice.identify`** (its 3 distinct returns: `None,0.0`=no-signal @430; `None,best_score`=gallery-miss @441; `best_id,best_score`=match @440). Any downstream `== 0.0` cannot distinguish a coincidental-0.0 gallery-miss from a true no-signal embedding failure.

**Q3 RE-BASELINE → (a) backend-sets** (the only option that actually decouples; auditor-demonstrated CHEAP because `voice.identify` already branches): see §2 D2a-D2d.

### §0 doctrine bankings locked at Phase 0 verdict (auditor §4)

- `### Phase-0-catches-wrong-premise` **STAYS at 13** — architect's 13→14 candidate REJECTED. The wrong-FILE catch (reconciler_state.py → voice_channel.py) is LINE-REF-DRIFT family (locational drift), NOT a substantive-mental-model falsification. The substantive premise ("add a flag to decouple from exact-0.0") was intact; only the file pointer was wrong. Architect accepts the rejection.
- `Pre-audit-quantifier-precision-refined-by-grep` SURFACE-CASCADE-AXIS **11 → 12** (3-sites → 6-sites comparison-shape refinement; architect-side Phase 0 grep, grep-verified). RATIFIED.
- LINE-REF-DRIFT sub-shape — banked (715/739/794 → 719/743/798, +4 verified).
- **NEW `### Architect-reads-production-code-before-sign-off` Sub-rule 4 BIDIRECTIONAL-VALIDATION 5th instance** — auditor-catches-architect, **SOLE-CONSTRUCTION-SITE-PREMISE-FALSE sub-variant**. The auditor's fresh `IdentityClaim\(` grep falsified the architect's Phase-0 construction-surface premise (1 site claimed → 3 production paths actual). Distinct from the architect-side `Pre-audit-quantifier` refinement (that was the COMPARISON-site axis; this is the CONSTRUCTION-surface axis, caught by the auditor). The 4-way matrix completed at Bundle 4; this is a 2nd auditor↔architect instance (the matrix counts pairs, not totals — this reinforces the auditor↔architect pair as the 5th instance overall).
- `Multi-axis-precision-pattern-confirmed-by-3-consecutive-blocked-bundles` STAYS at 2; **3rd-instance elevation now LIKELY** — the Q3 BLOCKING PI forces Plan v1 absorption, raising Plan-v2-escalation probability. Adjudicated at Plan v1 review.

### §0 architect "HIGH with strengthened reservation" confidence framing

Per Bundle 2-4 carry-forward: Plan v1 confidence is HIGH on the re-baselined surface (the 7 construction sites + voice.identify 3-tuple are now grep-verified), but explicitly acknowledges the Bundle 1-4 prior-prediction-blocked history AND this cycle's own Phase-0 construction-surface miss. If Plan v1 review surfaces further drift (e.g., a missed `voice.identify` caller, or an event-log encoder gap), cycle escalates to Plan v2 + `Multi-axis-precision-pattern` 3rd instance LOCKS.

---

## §1 Re-baselined MF7 surface + Q1/Q2/Q4 ratifications + Pass-2 grep

### §1.1 `voice.identify` return points (Pass-2 grep per auditor §5 item 2 — architect personally read 2026-05-29)

`core/voice.py::identify` (line 414, returns `tuple[str | None, float]`):
- **Line 430** `return None, 0.0` — `emb is None` (embedding computation failed) OR `not voice_gallery` (empty gallery) → **no-signal = True**
- **Line 440** `return best_id, best_score` — `best_score >= threshold` (real match) → **no-signal = False**
- **Line 441** `return None, best_score` — gallery miss; `best_score` is a real cosine (can be negative) → **no-signal = False**

The auditor took these from the audit's quote + the `_IdentifyFn` 2-tuple alias; architect has now personally read lines 414-442 to confirm. The 3 one-token additions are: `True` / `False` / `False` respectively.

### §1.2 The 6 reconciler confidence-vs-0.0 sites (Q1 + Q2 ratified dispositions)

| Site | Shape | Rule | Disposition (RATIFIED) |
|---|---|---|---|
| 719 | `claim.confidence == 0.0` | (no-signal check) | → `claim.confidence_is_no_signal` |
| 743 | `claim.confidence == 0.0` | (no-signal check) | → `claim.confidence_is_no_signal` |
| 798 | `claim.confidence == 0.0` | (no-signal check) | → `claim.confidence_is_no_signal` |
| 660 | `claim.confidence != 0.0` | `_p4_new_stranger_low_match` ("weak-positive OR negative, NOT no-signal") | → `not claim.confidence_is_no_signal` (Q1 (a) RATIFIED — logical inverse; forward-compatible under a future 0.01-failure backend where `!= 0.0` would wrongly admit failure) |
| 776 | `claim.confidence != 0.0` | `_p5_no_session_new_stranger` ("any real cosine signal") | → `not claim.confidence_is_no_signal` (Q1 (a) RATIFIED) |
| 628 | `claim.confidence <= 0.0` | `_p4_pyannote_vouched_stranger` (Session-119 anti-correlation; documented 614-619) | → `claim.confidence_is_no_signal or claim.confidence < 0.0` (Q2 (a) RATIFIED — algebraic identity holds today [is_no_signal ⟺ ==0.0 ⟹ (==0.0) or (<0.0) = <=0.0]; strictly improves correctness under a decoupled backend; preserves the load-bearing Session-119 negative-cosine half) |

### §1.3 MF8 surface (Q4 ratified + nuance)

UNCHANGED from Phase 0 §1.3-§1.4. Q4 nuance banked: `_to_snapshot` (144/146/149) **currently does `list(s.X)` copies** — the "list→tuple conversions" is the MIGRATION TARGET, not current state. Count (3 fields + 3 conversions) + the 4 production consumers (all safe) + 5 test-site updates all confirmed.

### §1.4 Phase 0 baseline counts grep-verified at Plan v1 drafting

Per `### Grep-baseline-before-drafting` + +1 per artifact (the cycle is now 4-artifact-minimum given the Plan v1 PI absorption):
- Strict-industry-standard mode applications: 126 (Phase 0 baseline) → 127 (Phase 0 artifact) → **128** (Plan v1)
- Spec-first review cycle: 135 → 136 → **137**
- `### Grep-baseline-before-drafting`: 93 → 94 → **95**
- Cross-cycle-handoff transparency: 96 → 97 → **98**
- Spec-time grep-verification: 103 → 104 → **105**

---

## §2 D-decisions (re-baselined per Q3(a) backend-sets + Q1/Q2 ratifications)

### D1 — MF7: add `IdentityClaim.confidence_is_no_signal: bool` field

`core/voice_channel.py:56-81` IdentityClaim (frozen) gains a 7th field:
```python
confidence_is_no_signal: bool = False
```
Default `False` so existing test constructions + the event-log default-path don't break. Docstring documents the contract: "True iff the voice-ID backend reported NO usable signal (embedding computation failed OR empty gallery — `core/voice.py::identify` returns exactly 0.0 only in these cases). Distinct from a negative `confidence` (anti-correlated real signal) or a sub-threshold positive (gallery miss with real signal). Decouples reconciler rule predicates from the ECAPA exact-0.0 convention so a future voice-ID backend (pyannote-only, cloud) can signal no-signal explicitly without breaking the cascade." `frozen=True` preserved.

### D2a — MF7: `voice.identify` 3-tuple return + `_IdentifyFn` alias

`core/voice.py::identify` return signature `tuple[str | None, float]` → `tuple[str | None, float, bool]`:
- Line 430 `return None, 0.0` → `return None, 0.0, True`
- Line 440 `return best_id, best_score` → `return best_id, best_score, False`
- Line 441 `return None, best_score` → `return None, best_score, False`

`core/voice_channel.py:88` `_IdentifyFn = Callable[..., tuple[Optional[str], float]]` → `Callable[..., tuple[Optional[str], float, bool]]`.

Docstring on `identify` updated: "Returns `(person_id, cosine_score, is_no_signal)`. `is_no_signal=True` ONLY when the embedding failed or the gallery was empty (score forced to 0.0); `False` for both real matches and gallery-misses (where score is a genuine cosine, possibly negative)."

### D2b — MF7: `identify_speaker` 5-site flag-setting

`core/voice_channel.py::identify_speaker`:
- 162 (audio None), 171 (empty gallery), 183 (diarize-fail), 200 (identify-fail): add `confidence_is_no_signal=True` (no-signal by construction)
- 196-198: `pid, score = await _maybe_run_in_executor(identify_fn, ...)` → `pid, score, is_no_signal = await _maybe_run_in_executor(identify_fn, ...)` (unpack the 3-tuple)
- 217 (success path): add `confidence_is_no_signal=is_no_signal` (from the unpacked 3-tuple — the backend's explicit signal)

**Note**: `_maybe_run_in_executor` returns whatever `identify_fn` returns; the 3-tuple flows through transparently. Test fakes for `identify_fn` must also return 3-tuples (Plan v1 §1 flags the test-fake updates).

### D2c — MF7: `reconciler.py:112` construction kwarg + legacy pipeline propagation

`core/reconciler.py:112` `_build_routing_inputs` constructs IdentityClaim from `v_pid`/`v_score`. Add a keyword-only param `v_score_is_no_signal: bool = False` (after the existing kwargs) and pass `confidence_is_no_signal=v_score_is_no_signal` at construction (112).

The LEGACY pipeline path (pre-cutover) that calls `_build_routing_inputs` must pass `v_score_is_no_signal` from `voice.identify`'s 3-tuple. Plan v1 §1 Pass-2 greps the pipeline.py call site of `_build_routing_inputs` + the `voice.identify` call that produces `v_score` to wire the flag through. (Default `False` keeps existing tests + shadow-path callers that don't yet pass it safe; the production legacy path is updated to pass it.)

### D2d — MF7: event-log serialization round-trip (P0.0.7-class)

`core/event_log/types.py`:
- `_identity_claim_from_dict` (124-131): add `confidence_is_no_signal=bool(d.get("confidence_is_no_signal", False))` to the reconstruction.
- Verify the serialization encoder (`_event_log_default` in `producer.py`) includes the new field. If it uses `dataclasses.asdict`/field iteration → automatic. If it enumerates fields explicitly → add the field. Plan v1 §1 Pass-2 greps the encoder.
- `IdentityClaimPayload` (237) wraps IdentityClaim; no signature change (it holds the dataclass), but the round-trip (`from_json_dict` → `_identity_claim_from_dict`) now preserves the flag.

### D2e — MF7: reconciler predicate migrations (6 sites per Q1/Q2)

Per §1.2: 3 `== 0.0` → `confidence_is_no_signal`; 2 `!= 0.0` → `not confidence_is_no_signal`; 1 `<= 0.0` → `confidence_is_no_signal or claim.confidence < 0.0`. The 628 migration preserves the Session-119 anti-correlation regression (canary-2026-04-29).

### D3 — MF7: AST invariant `test_no_exact_equality_against_claim_confidence`

New `tests/test_no_exact_equality_against_claim_confidence.py` — AST-walks `core/reconciler.py`; rejects any `ast.Compare` against a `0.0` literal where the comparator operand is `claim.confidence` (`.confidence` attribute access) using `ast.Eq` OR `ast.NotEq` (both couple to the exact-0.0 convention per Q1). ALLOWS `ast.Lt` / `ast.LtE` / `ast.Gt` / `ast.GtE` threshold comparisons (the 628 `< 0.0` anti-correlation check + the many `< threshold` rule predicates are genuine thresholds, not exact-equality). Self-tests: forward (synthetic `== 0.0` AND synthetic `!= 0.0` both fire) + inverse (flag-based predicate + `< 0.0` threshold both pass).

### D4 — MF8: `SessionSnapshot` 3 fields `list` → `tuple` + `_to_snapshot` conversions

UNCHANGED from Phase 0 §2 D4. `core/session_state.py` SessionSnapshot (110/112/115) → `tuple`; `_to_snapshot` (144/146/149) `list(...)` → `tuple(...)`. Owner `Session` (76/78/81) keeps `list`.

### D5 — MF8: AST invariant `test_session_snapshot_collection_fields_are_immutable`

UNCHANGED from Phase 0 §2 D5. AST-asserts the 3 SessionSnapshot fields annotated `tuple` + behavioral (snapshot field has no `.append`). Self-tests forward (synthetic `list` fires) + inverse (tuple passes).

### D6 — consumer migration + closure-narrative + CI

5 test-site updates (§1.3 MF8) + test-fake `identify_fn` 3-tuple updates (D2b) + the test_reconciler.py / event_log_fixtures.py IdentityClaim constructions (default `False` mostly safe; no-signal-case fixtures get the flag). Production consumers 3481/5859 verified read-only at Plan v1 Pass-2. New AST invariants auto-included in `fast.yml` default-marker filter. Closure-narrative banked.

---

## §3 Q5 LOCK — re-locked at mid 7 per auditor §3 Q5 provisional (Q3 re-frame absorbed)

**Q5 LOCK = 7 anchors**. NARROW band ±15% = **[5.95, 8.05]**. Falsification: ≤4 OR ≥10.

| # | Anchor | Type |
|---|---|---|
| A1 | D1 IdentityClaim `confidence_is_no_signal` field + frozen preserved | source-inspection (voice_channel.py) |
| A2 | D2a backend flag-set at semantic source — `voice.identify` 3-tuple (430/440/441) + `_IdentifyFn` alias (88) | source + behavioral (no-signal returns True; match/gallery-miss return False) |
| A3 | D2b `identify_speaker` 5-site flag-setting (4 True-by-construction + success-path 3-tuple unpack) | source + behavioral (audio-None/empty-gallery/diarize-fail/identify-fail → flag True; real match → flag False) |
| A4 | D2c+D2e reconciler — construction kwarg (112) + 6-predicate migration (3 == / 2 != / 1 <=) + Session-119 canary regression guard | source + behavioral |
| A5 | D2d event-log round-trip (NEW per auditor) — `_identity_claim_from_dict` + encoder + serialize→JSON→reconstruct preserves the flag | behavioral round-trip + source |
| A6 | D3 MF7 AST invariant (bans Eq+NotEq, allows Lt/LtE) + self-tests | structural AST + 2 self-tests |
| A7 | D4+D5 MF8 SessionSnapshot tuple + `_to_snapshot` + AST invariant + self-tests | source + behavioral immutability + AST |

**Total = 7 logical anchors. NARROW band [5.95, 8.05]. Q5 LOCK = 7.**

**Collection fan-out projection** (per Bundle 3 Q4 + Bundle 4 lesson — explicitly account for AST detector parametrize): A4 6-predicate parametrize (~6) + A6 self-tests (~3) + A7 AST + self-tests (~4) + A2/A3/A5 behavioral (~6) + A1 source (~2) ≈ **~21-25 collections** (single-file-scope invariants; not STANDARD-scope).

**Phase 4 strengthening caveat** (Bundle 1-4 pattern): if Phase 4 surfaces a detector gap → 11th `### Induction-surfaces-invariant-gaps` family event.

**Closure-projection band**: 7 exact = 0% ON-TARGET → `Doctrine-prediction-precision-improving-over-arc` 13 → 14 consecutive (if closure-actual = 7); 6 or 8 = ON-TARGET within NARROW; 5 or 9 = SLIGHT-DRIFT within ±30%; ≤4 OR ≥10 = FALSIFICATION.

---

## §4 Cross-spec impact (re-baselined; 4-part Pass-2 grep arithmetic)

### §4.1 File-impact table

| D | New files | Modified files | Approx scope |
|---|---|---|---|
| D1 | — | `core/voice_channel.py` (1 field + docstring) | ~8 line edits |
| D2a | — | `core/voice.py` (3 one-token return additions + docstring) + `core/voice_channel.py:88` (_IdentifyFn alias) | ~6 line edits |
| D2b | — | `core/voice_channel.py` (5 identify_speaker sites + 1 unpack) | ~7 line edits |
| D2c | — | `core/reconciler.py:112` (kwarg + construction) + `pipeline.py` (legacy caller propagation) | ~6 line edits |
| D2d | — | `core/event_log/types.py` (_identity_claim_from_dict + encoder verify) | ~3 line edits |
| D2e | — | `core/reconciler.py` (6 predicate migrations: 719/743/798/660/776/628) | ~6 line edits |
| D3 | `tests/test_no_exact_equality_against_claim_confidence.py` (NEW) | — | 1 test file + AST detector + self-tests |
| D4 | — | `core/session_state.py` (3 SessionSnapshot fields + 3 `_to_snapshot`) | ~6 line edits |
| D5 | `tests/test_session_snapshot_collection_fields_are_immutable.py` (NEW) | — | 1 test file + AST detector + self-tests |
| D6 | — | 5 MF8 test updates + test-fake `identify_fn` 3-tuple updates + no-signal-case fixture flag adds | ~15-20 line edits |

**Total scope (4-part Pass-2 grep ARITHMETIC SUM-AGAINST-TOTAL — Bundle 5 candidate 3rd instance)**:
- New files: 2 (test files)
- Modified production files: **6** (`core/voice.py` + `core/voice_channel.py` + `core/reconciler.py` + `core/event_log/types.py` + `pipeline.py` + `core/session_state.py`)
- Production line-level edits: 8 (D1) + 6 (D2a) + 7 (D2b) + 6 (D2c) + 3 (D2d) + 6 (D2e) + 6 (D4) = **42 production edits**
- Test edits: 2 new files + ~15-20 consumer/fixture updates

**Arithmetic verified**: 2 new + 6 modified production + test surface; 42 production line-edits sum across D1-D6 production rows (8+6+7+6+3+6+6=42). ✓

### §4.2 Bundle 5 is the FINAL Pre-P1 must-fix bundle

After Bundle 5: P1 cycle (8-10 week clock; 5 parallel tracks). MF7 = Pre-P1 form of P1.B1 (IdentityClaim contract tightening); MF8 = Pre-P1 form of P1.B2 (SessionSnapshot tuple). The Q3(a) backend-sets architecture lands the IdentityClaim contract at the semantic source NOW — when P1's multi-platform adapters arrive, each adapter's voice-ID backend sets its own `is_no_signal` flag, and the cascade stays correct.

### §4.3 Bundle 5.X / 5.Y candidates

- Bundle 5.Y — debug-field pruning (`voice_reasoning` + `voice_raw_segment_scores` written into IdentityClaim but unused by rules; B-L2). Out of MF7 scope; file separately.
- Bundle 5.X — NO LONGER NEEDED as a "backend-sets follow-up" (Q3(a) ships the backend-sets decoupling IN Bundle 5 per the auditor's re-baseline). The Phase 0 §4.3 Bundle 5.X framing (deferred backend-sets) is withdrawn.

---

## §5 Discipline counts + Multi-discipline preventive convergence

### §5.1 Per-artifact-driven (cycle escalated to ≥4-artifact via Plan v1 PI absorption)

| Discipline | Pre-Bundle-5 | Phase 0 | **Plan v1** | Plan v2? | Closure |
|---|---|---|---|---|---|
| Strict-industry-standard mode applications | 126 | 127 | **128** | (129) | 129/130 |
| Spec-first review cycle | 135 | 136 | **137** | (138) | 138/139 |
| `### Grep-baseline-before-drafting` | 93 | 94 | **95** | (96) | 96/97 |
| Cross-cycle-handoff transparency | 96 | 97 | **98** | (99) | 99/100 |
| Spec-time grep-verification | 103 | 104 | **105** | (106) | 106/107 |

(Final counts depend on whether Plan v1 clears or escalates to Plan v2.)

### §5.2 Closure-event disciplines

| Discipline | Pre-Bundle-5 | After closure |
|---|---|---|
| Strict-industry-standard mode closures | 36 | 37 |
| `### Twin-filename-pitfall-prevention` | 35 | 36 (preventive — `tests/pre_p1_bundle5_*.md` cleanly disambiguated) |
| `### Architect-reads-production-code-before-sign-off` | 34 | 35 (closure-audit event) |
| Auditor-Q5-estimates-trail-grep | 40 | 41 (if Q5 within band) |
| Deferred-canary strategy | 37 | 38 |

### §5.3 NEW doctrine instances

| Discipline | Pre-Bundle-5 | After Plan v1 | After closure | Event |
|---|---|---|---|---|
| `Pre-audit-quantifier-precision-refined-by-grep` SURFACE-CASCADE-AXIS | 11 | **12** | 12 | 3→6 comparison-shape refinement (RATIFIED Phase 0) |
| `### Phase-0-catches-wrong-premise` | 13 | **STAYS 13** | 13 | Wrong-FILE catch is LINE-REF-DRIFT family, not substantive premise (auditor REJECTED 13→14) |
| `### Architect-reads-production-code-before-sign-off` BIDIRECTIONAL-VALIDATION sub-rule | 4 | **5** | 5 | NEW auditor-catches-architect SOLE-CONSTRUCTION-SITE-PREMISE-FALSE sub-variant |
| `Multi-axis-precision-pattern-confirmed-by-3-consecutive-blocked-bundles` | 2 | TBD | **3 (LIKELY — sub-rule ELEVATION EVENT)** if Bundle 5 ships ≥4-artifact | Q3 BLOCKING PI forced Plan v1 absorption |
| OPTIONAL-Plan-v2 sub-rule track record | 20 | 20 | **STAYS 20** | Bundle 5 escalates beyond OPTIONAL-Plan-v2 (Phase 0 surfaced BLOCKING PI) |
| `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` | 12 | TBD | **13** (if Plan v1 review clean) OR catching-event (if Plan v1 surfaces PI) | — |
| 4-part Pass-2 grep operational rule extension | 2 instances | TBD | **3 (FORMALIZATION threshold)** if Bundle 5 §4.1 arithmetic verification holds at closure | Bundle 5 = candidate 3rd instance |
| `Doctrine-prediction-precision-improving-over-arc` | 13 | TBD | **14 (if closure-actual = 7 exact)** | Conditional |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 34 | TBD | **35 (if within NARROW band [5.95, 8.05])** | Conditional |

### §5.4 Multi-discipline preventive convergence enumeration (Bundle 5)

Per `### Multi-discipline-preventive-convergence` numbered doctrine (trajectory Bundle 1 [7] → Bundle 2 [9] → Bundle 3 [11] → Bundle 4 [11]):

1. LINE-REF-DRIFT preventive (Phase 0 §1.1 caught 715/739/794 → 719/743/798 +4)
2. CROSS-PATH-SYNC-OMISSION preventive commitment (no new memory files expected)
3. DEFERRED-CANARY-ENTRY-OMISSION grep-verify
4. Closure-audit verdict forwarding 10th-cycle routinization
5. CODE-TEMPLATE-MISIDENTIFICATION preventive (IdentityClaim frozen-field-add verified against actual shape; SessionSnapshot tuple verified against P0.7.1 frozen+slots)
6. Developer Pass-3 grep at Phase 4 pre-implementation (numbered doctrine carry-forward)
7. §0 NEW commitment EXTENSION dual-axis (file-count + semantic-correctness)
8. BIDIRECTIONAL-VALIDATION sub-rule active (5th instance banked THIS Phase 0 — auditor-catches-architect)
9. Phase 0 explicit-per-bucket grep enumeration
10. Cross-bundle architectural-coherence preventive (D3 AST invariant scope = Bundle 2/3 STANDARD-scope discipline)
11. 4-part Pass-2 grep ARITHMETIC SUM-AGAINST-TOTAL (Bundle 3 lesson; §4.1 verified)

**11 preventives at Bundle 5 Plan v1** — sustained 11-floor (Bundle 3 [11] → Bundle 4 [11] → Bundle 5 [11]).

---

## §6 Closure-narrative paste template (Plan v1-aware)

```markdown
| **Pre-P1 Bundle 5 (Contract Typing MF7+MF8 — FINAL Pre-P1 bundle — `IdentityClaim.confidence_is_no_signal` backend-sets decoupling [voice.identify 3-tuple return + identify_speaker 5-site + reconciler construction + event-log round-trip + 6-predicate migration] + `SessionSnapshot` 3-field tuple migration — N-artifact cycle [Phase 0 BLOCKING Q3 PI → Plan v1 re-baseline ...]) CLOSED 2026-05-2X** — [SUMMARY: MF7 decouples reconciler from ECAPA exact-0.0 convention via `confidence_is_no_signal` flag SET AT THE BACKEND (`voice.identify` returns `(pid, score, is_no_signal)`; `identify_speaker` 4 no-signal-by-construction sentinels + success-path 3-tuple unpack; reconciler.py:112 construction kwarg; event-log serialize→reconstruct round-trip) — 7 construction sites across 3 files re-baselined from the architect's Phase-0 sole-site premise (auditor-caught, BIDIRECTIONAL-VALIDATION 5th instance); 6 reconciler predicates migrated (3 `==`→flag, 2 `!=`→`not flag`, 1 `<=`→`flag or <0` preserving Session-119 anti-correlation); MF8 SessionSnapshot recent_voice_confs/core_memory/recent_attributions list→tuple frozen-by-construction + _to_snapshot tuple() conversions]. **N/N anchor tests A1-A7 GREEN** with ~21-25 collections. **N/N deliberate-regression confirmations passed cleanly**. **Doctrine bumps**: `Pre-audit-quantifier-precision-refined-by-grep` 11→12 (3→6 comparison-shape). `### Architect-reads-production-code-before-sign-off` BIDIRECTIONAL-VALIDATION 4→5 (auditor-catches-architect SOLE-CONSTRUCTION-SITE-PREMISE-FALSE). `### Phase-0-catches-wrong-premise` STAYS 13 (wrong-FILE = LINE-REF-DRIFT family). `Multi-axis-precision-pattern` 2→3 (sub-rule ELEVATION EVENT — Bundle 5 escalated past OPTIONAL-Plan-v2). OPTIONAL-Plan-v2 STAYS at 20. 4-part Pass-2 grep rule 3rd instance (FORMALIZATION). `### Phase-0-granular-decomposition` 34→35. `Doctrine-prediction-precision-improving-over-arc` 14th 0%-streak (if closure-actual=7). **FINAL Pre-P1 must-fix bundle CLOSED** — all 5 bundles (Docs+CI / Governance / Critical-bugs / Observability+Concurrency / Contract-typing) shipped. Next: P1 cycle (8-10 week clock, 5 parallel tracks). **No CI evidence event required** (new AST invariants auto-run in fast.yml).
```

---

## §7 Honest-count commitment

Per `Explicit-closure-honest-count-commitment`:
- Plan v1 §7 MADE → closure §7 HONORED = 2 separate instances
- IF closure-actual = 7 exact → `Doctrine-prediction-precision-improving-over-arc` 14th-streak
- IF closure-actual ∈ {6, 8} → ON-TARGET within NARROW; doctrine bumps; streak interrupted
- IF closure-actual ∈ {5, 9} → SLIGHT-DRIFT within ±30%; doctrine HOLDS at 34; streak interrupted
- IF closure-actual ≤4 OR ≥10 → FALSIFICATION-WATCH

---

## §8 Plan v2 path adjudication

Per auditor §6 Q6: OPTIONAL-Plan-v2 candidacy MATERIALLY LOWERED — Phase 0 surfaced a BLOCKING PI absorbed at Plan v1. The cycle is already ≥4-artifact (Phase 0 + Plan v1 + closure minimum, with the BLOCKING PI absorbed at Plan v1 rather than a separate Plan v2). **Adjudication**: this Plan v1 IS the absorption of the Q3 BLOCKING PI. If the auditor's Plan v1 review clears 0 NEW PIs → Bundle 5 ships as 3-artifact-with-blocking-Phase-0 (Phase 0 + Plan v1 + closure), and `Multi-axis-precision-pattern` 3rd instance is adjudicated (the Phase-0 BLOCKING PI counts as the multi-axis-precision event even without a separate Plan v2). If the auditor's Plan v1 review surfaces NEW PIs (e.g., a missed `voice.identify` caller in the legacy pipeline path, or an event-log encoder gap) → Plan v2 absorbs; cycle becomes 4-artifact; `Multi-axis-precision-pattern` 3rd instance LOCKS unambiguously.

**Architect's read**: the Q3 re-baseline is substantial (7 construction sites + 3-tuple propagation + event-log round-trip) but now fully grep-verified. The highest residual risk is the legacy-pipeline `_build_routing_inputs` caller wiring (D2c) — Plan v1 §1 commits to Pass-2 grepping the pipeline.py call site at drafting. If that surfaces an unmapped caller, Plan v2. Confidence: HIGH with strengthened reservation (the Phase-0 construction-surface miss is a live reminder that grep-completeness is the load-bearing discipline).

**`Multi-axis-precision-pattern` 3rd-instance disposition**: Bundle 5's Phase 0 BLOCKING PI (construction-surface miss) is a genuine multi-axis precision event distinct from Bundle 1-4's axes (Bundle 1 measurement, Bundle 2 file-count + license, Bundle 3 arithmetic + AST-scope, Bundle 4 doctrine-arithmetic). The construction-surface axis is NEW. Whether this LOCKS the sub-rule elevation at 3 instances is the auditor's call at Plan v1 review.

---

## §9 Procedural commitments (closure-audit)

All Phase 0 §0 commitments preserved. Plan v1 NEW: §1 Pass-2 grep of (a) the `pipeline.py` legacy `_build_routing_inputs` caller + the `voice.identify` call producing `v_score` (D2c wiring); (b) the `_event_log_default` encoder in `producer.py` (D2d serialization). Both grep-verified at Plan v1 drafting; results below at §11.

---

## §10 Known Limitations

1. **Test-fake `identify_fn` 3-tuple migration** — D2b changes `identify_fn`'s contract to a 3-tuple. All test fakes that stub `identify_fn`/`voice.identify` must return 3-tuples. Plan v1 §1 enumerates these; Phase 4 developer Pass-3 grep confirms none missed (a missed 2-tuple fake → ValueError on unpack at 196-198, caught fast).
2. **Legacy vs shadow path** — `identify_speaker` (new, voice_channel.py) is Phase-3 shadow (pipeline.py:8032); `_build_routing_inputs` (reconciler.py:112) is the legacy production path. Both construct IdentityClaim; both get the flag. At the eventual Phase-4 cutover (post-P1), the legacy path retires; the flag-setting at identify_speaker becomes the sole path. Bundle 5 wires both for correctness during the shadow period.
3. **Event-log encoder** — if `_event_log_default` enumerates IdentityClaim fields explicitly (not `asdict`), D2d must add `confidence_is_no_signal` to the encoder too. Plan v1 §11 greps it.
4. **Bundle 5.Y debug-field pruning** deferred (B-L2). Bundle 5.X (backend-sets follow-up) WITHDRAWN — Q3(a) ships it in Bundle 5.

---

## §11 Architect Pass-2 grep clearance (4-part rule) + D2c/D2d wiring verification

1. **Symbol-name-uniqueness** ✓ — `IdentityClaim` / `confidence_is_no_signal` / `_build_routing_inputs` / `_identity_claim_from_dict` / `_IdentifyFn` / `identify_speaker` all unambiguous.
2. **Behavioral-semantic** ✓ — §1.1 voice.identify 3 returns personally read; §1.2 6 predicate dispositions verified against rule comments; D2b 5 construction sites read (162/171/183/200 no-signal-by-construction; 217 success).
3. **Symmetric verification** ✓ — MF7 adds a field (default False; existing constructions safe) + migrates 6 predicates (reject class: `== 0.0`/`!= 0.0` banned by AST invariant; preserve class: `< 0.0` threshold + flag-based predicates pass). MF8 list→tuple (reject: snapshot `.append` now fails; preserve: read-only consumers + `list(...)` conversions unaffected).
4. **ARITHMETIC SUM-AGAINST-TOTAL** ✓ (Bundle 5 = candidate 3rd instance of the 4-part rule) — §4.1: 8+6+7+6+3+6+6 = 42 production edits; 2 new + 6 modified production files; sums verified.

### §11.1 D2c + D2d wiring Pass-2 grep (committed at §9 — to execute at Plan v1 drafting)

- D2c: grep `pipeline.py` for the `_build_routing_inputs(` call site + the `voice.identify`/`identify(` call producing `v_score` → wire `v_score_is_no_signal` through. **[Architect commits to running this grep; result appended before forwarding. If an unmapped caller surfaces → Plan v2.]**
- D2d: grep `core/event_log/producer.py` for `_event_log_default` → confirm IdentityClaim serialization includes the new field (asdict = automatic; explicit = add). **[Architect commits to running this grep; result appended.]**

---

## §12 Standing by for auditor Plan v1 verdict

If CLEAN (0 NEW PIs) → Plan v1 ships to developer for Phase 4; `Multi-axis-precision-pattern` 3rd-instance adjudicated; cycle closes as 3-artifact-with-Phase-0-BLOCKING.

If NEW PIs surface → Plan v2 absorbs; `Multi-axis-precision-pattern` 3rd instance LOCKS sub-rule elevation at Bundle 5 closure.

**Architect's Plan v1 confidence: HIGH (with strengthened reservation)** — the Q3 re-baseline is grep-verified across all 7 construction sites + voice.identify returns + event-log payload; the residual risk is the D2c legacy-caller + D2d encoder wiring (§11.1 greps committed). The Phase-0 construction-surface miss is acknowledged as a live grep-completeness lesson.

---

**Filed**: 2026-05-29
**Architect**: Claude
**Forwarded to**: Auditor (external)
**Prior artifact**: `tests/pre_p1_bundle5_contract_typing_audit.md` (Phase 0 NOT CLEAN — Q3 BLOCKING sole-construction-site-premise-false; Q1/Q2 ratified; absorbed at Plan v1 via Q3(a) backend-sets re-baseline to 7 construction sites across 3 files)
