# Pre-P1 Bundle 5 — Contract Typing (MF7 + MF8) Plan v2 (2026-05-29)

**Cycle**: Pre-P1 must-fix Bundle 5 (Contract Typing) — FINAL Pre-P1 bundle — 4-artifact cycle (Phase 0 + Plan v1 + Plan v2 + closure)
**Predecessor**: `tests/pre_p1_bundle5_contract_typing_plan_v1.md` (Plan v1 NOT CLEAN — 1 BLOCKING PI: D2a's 3-tuple return has 3 production callers, not 1; auditor verdict in `info.md` 2026-05-29)
**Discipline**: Strict-mode; BLOCKING PI absorbed → 4-artifact cycle; `Multi-axis-precision-pattern` 3rd instance RATIFIED (with rename — see §5)
**Architect**: Claude
**Auditor**: External

---

## §0 BLOCKING PI absorption + doctrine adjudications

### §0.1 The BLOCKING PI (auditor §1) — absorbed

Plan v1 D2a changes `voice.identify` return signature `(pid, score)` → `(pid, score, is_no_signal)`. This is a BREAKING return-signature change. Plan v1 §2 D2c + §4.1 + §11.1 used SINGULAR framing ("the caller" / "~6 line edits / the caller") and accounted for ONE caller (reconciler.py:112's upstream). **Reality: 3 production callers, two entirely unmapped, both HARD-BREAK with `ValueError: too many values to unpack` at runtime.**

**Root cause — deferral-pattern (the exact anti-discipline this bundle has been teaching)**: Plan v1 §11.1 wrote "[Architect commits to running this grep; result appended before forwarding]" for the D2c caller grep — then forwarded WITHOUT running it. Per the auditor's banked `feedback_pass_2_grep_deferral_pattern.md`, every "I'll grep before handoff" framing is an undercount red-flag. The architect's own Plan v1 §8 named "a missed `voice.identify` caller in the legacy pipeline path" as the Plan-v2 escalation trigger. The auditor's Pass-2 grep found two. **Architect accepts the catch fully — this is `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` firing exactly as designed.**

### §0.2 Architect BIDIRECTIONAL re-verification at Plan v2 drafting (no deferral — grep RUN + appended)

`identify\(` grep on `pipeline.py` (architect, 2026-05-29) — confirms the auditor's 3-caller finding EXACTLY:

| Site | Context | Current unpack | Disposition |
|---|---|---|---|
| `pipeline.py:2439` | `_accumulate_voice` (checks `v_score > 0.0` / `>= min_self_match`) | `v_pid, v_score = await voice_mod.identify(` | **Standalone** → `v_pid, v_score, _ = ...` (no flag needed; this caller doesn't construct an IdentityClaim) |
| `pipeline.py:7539` | voice-first ambient (opens session on `if v_pid:`) | `v_pid, v_score = await voice_mod.identify(` | **Standalone** → `v_pid, v_score, _ = ...` |
| `pipeline.py:7804` | per-turn voice ID (feeds reconciler routing) | `_v_pid, _v_score = await voice_mod.identify(` | **D2c target** → `_v_pid, _v_score, _v_is_no_signal = ...` + propagate to `_build_routing_inputs(..., v_score_is_no_signal=_v_is_no_signal)` |

Non-callers grep-confirmed as comments/logs only (3608/3609, 6892/6893, 11224) + the NEW-path `identify_speaker` at 8032/8033 (`_vc_identify`, the voice_channel function — constructs IdentityClaim directly via D2b, NOT a `voice.identify` 2-tuple caller). **Caller count = exactly 3; no hidden 4th** (auditor §2 confirms).

### §0.3 Architect Pass-2 grep CATCHES the auditor's test-fake undercount (architect-catches-auditor)

The auditor's §3 item 3 enumerated "~8 test-fake sites" (6 in test_pipeline.py @ 6500/6604/6640/6683/6722/6763 + test_voice_channel.py factory + test_event_log_producer_coverage.py:169). **Architect Pass-2 grep (`identify` across `test_pipeline.py` + `tests/`, 2026-05-29) finds the real count is 15** — the auditor's ~8 missed 7 sites:

- **test_pipeline.py is 9, not 6** — the auditor missed line 35 (`_vs.identify = AsyncMock` module stub) + 8246 + 8295 (`patch("pipeline.voice_mod.identify", ...)`).
- **4 global `_voice_stub.identify` stubs the auditor didn't enumerate** — conftest.py:57, test_dispute_auto_clear.py:29, test_multispeaker_integration.py:39, test_user_text_gate_multiword.py:32.

**This is BIDIRECTIONAL-VALIDATION working a 3rd way this bundle**: the auditor caught the architect's caller undercount (1→3); the architect's Plan-v2 Pass-2 grep catches the auditor's test-fake undercount (8→15). The whole bundle is a grep-completeness lesson; banking the symmetry honestly. Per the auditor's own restraint (`info.md` §4 "I leave it to closure rather than inflate"), the architect does NOT unilaterally bump BIDIRECTIONAL to a 6th instance — flags the architect-catches-auditor test-fake catch for closure adjudication and banks it under the completeness/Pass-2-grep framing (mirroring the auditor's choice).

### §0.4 Doctrine adjudications (auditor §4 locked + architect additions)

- `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` **12 → 13** — CAUGHT-REAL-GAP (ENUMERATION-DRIFT sub-shape). The doctrine's load-bearing property fired as designed.
- `Plan-v1-Pass-2-grep-undercount` **16 → 17** — the 2 unmapped callers (child failure-mode tracker). **Architect note**: the test-fake undercount (8→15, §0.3) is a SECOND undercount this bundle, but architect banks it under the same 17th-instance umbrella (one bundle, one enumeration-drift event with two halves) rather than inflating to 18 — leaves the discrete-second-half question to closure.
- `Multi-axis-precision-pattern` **2 → 3 RATIFIED, WITH RENAME** — see §5. The auditor's methodology-honesty flag is ACCEPTED: "3-consecutive-blocked-bundles" is literally false (Bundle 4 cleared between Bundle 3 + Bundle 5). Adopting the honest name **`Multi-axis-precision-pattern-across-Pre-P1-bundles`** (4 of 5 Pre-P1 bundles blocked; only Bundle 4 cleared). Architect finalizes the rename at closure per auditor's direction.
- **BIDIRECTIONAL-VALIDATION STAYS at 5** (4-way matrix complete) — the Phase-0 construction-surface catch already banked this bundle's auditor↔architect dynamic as the 5th. The Plan-v1 caller-fanout catch banks under Pass-2-grep CAUGHT-REAL-GAP (auditor §4); the architect-catches-auditor test-fake catch (§0.3) flagged for closure, not unilaterally bumped. Per auditor + architect mutual restraint.
- `### Phase-0-catches-wrong-premise` **STAYS 13** ✓ (accepted).
- `Pre-audit-quantifier-precision-refined-by-grep` **STAYS 12** ✓ (the caller-fanout is a Plan-v1 Pass-2 catch, NOT a Phase-0 pre-audit refinement).
- OPTIONAL-Plan-v2 **STAYS 20** ✓ (Bundle 5 ships ≥4-artifact).
- Q5 = **7 HOLDS** ✓ (the PI adds edits WITHIN anchors A2 [voice.identify] + A4 [reconciler/pipeline wiring]; no new anchor).

---

## §1 Exhaustive enumeration (auditor §3 absorptions, all grep-verified — zero deferral)

### §1.1 The 3 `voice.identify` production callers (auditor §3 item 1)

Per-caller disposition (§0.2): 2439 → `v_pid, v_score, _ = ...`; 7539 → `v_pid, v_score, _ = ...`; 7804 → `_v_pid, _v_score, _v_is_no_signal = ...` + `_build_routing_inputs(..., v_score_is_no_signal=_v_is_no_signal)`.

### §1.2 The 15 test-fake sites (auditor §3 item 3, CORRECTED 8→15 per §0.3)

Every fake/stub/patch of `core.voice.identify` (by ANY reference) MUST return a 3-tuple after D2a, because the function's contract changed AND both consumers (the 3 production callers' 3-target unpacks + `identify_speaker`'s `pid, score, is_no_signal = await identify_fn(...)` at voice_channel.py:196-198) now expect 3 values. A 2-tuple fake → `ValueError`.

**test_pipeline.py (9):**
| Line | Current | → |
|---|---|---|
| 35 | `_vs.identify = AsyncMock(return_value=(None, 0.0))` | `(None, 0.0, True)` |
| 6500 | `patch("core.voice.identify", new=AsyncMock(return_value=(None, 0.0)))` | `(None, 0.0, True)` |
| 6604 | `patch("core.voice.identify", new=AsyncMock(return_value=(None, 0.0)))` | `(None, 0.0, True)` |
| 6640 | `patch("core.voice.identify", new=AsyncMock(return_value=("p1", 0.9)))` | `("p1", 0.9, False)` |
| 6683 | `patch("core.voice.identify", new=AsyncMock(return_value=(None, 0.0)))` | `(None, 0.0, True)` |
| 6722 | `patch("core.voice.identify", new=AsyncMock(return_value=(None, 0.0)))` | `(None, 0.0, True)` |
| 6763 | `side_effect=lambda: next(iter([("jagan_abc", 0.85), ("wasim_def", 0.78)]))` | `iter([("jagan_abc", 0.85, False), ("wasim_def", 0.78, False)])` |
| 8246 | `patch("pipeline.voice_mod.identify", new=_AsyncMock(return_value=(None, 0.0)))` | `(None, 0.0, True)` |
| 8295 | `patch("pipeline.voice_mod.identify", new=AsyncMock(return_value=(None, 0.0)))` | `(None, 0.0, True)` |

**Global `_voice_stub.identify` stubs (4 — auditor missed):**
| File:Line | Current | → |
|---|---|---|
| tests/conftest.py:57 | `_voice_stub.identify = AsyncMock(return_value=(None, 0.0))` | `(None, 0.0, True)` |
| tests/test_dispute_auto_clear.py:29 | `_voice_stub.identify = AsyncMock(return_value=(None, 0.0))` | `(None, 0.0, True)` |
| tests/test_multispeaker_integration.py:39 | `_voice_stub.identify = AsyncMock(return_value=(None, 0.0))` | `(None, 0.0, True)` |
| tests/test_user_text_gate_multiword.py:32 | `_voice_stub.identify = AsyncMock(return_value=(None, 0.0))` | `(None, 0.0, True)` |

**`identify_fn`-injected fakes (2):**
| File:Line | Current | → |
|---|---|---|
| tests/test_event_log_producer_coverage.py:160 | `fake_identify = lambda audio, gallery, thresh, sr: ("jagan_001", 0.85)` (used as `identify_fn=` at 169) | `("jagan_001", 0.85, False)` |
| tests/test_voice_channel.py:56 | `_fake_identify_factory(pid, score)` returns `(pid, score)` (used at 110/130/150/168/187/226) | add optional `is_no_signal: bool = False` param; inner `_f` returns `(pid, score, is_no_signal)`. The no-signal-case test (187 `(None, 0.0)`) MAY pass `is_no_signal=True` to verify flag propagation through `identify_speaker`'s success path. |

**Total = 15 test-fake sites** (9 + 4 + 2; voice_channel factory counted as 1 fix). A 2-tuple stub feeding any 3-target unpack → ValueError; all 15 must be 3-tuples.

**Ripple flag (1 — verify at Phase 4, low risk)**: `tests/test_p0_r6_y_ecapa_worker.py:311` `test_p0_r6_y_d3_anchor_4_site_7148_uses_await_voice_mod_identify` is a source-inspection test asserting pipeline.py contains `await voice_mod.identify(`. The await PATTERN survives D2a (only the unpack arity changes), so it should pass — but it carries a STALE line ref in its name (7148; the call is now at 7804). Developer Pass-3 verifies it doesn't assert tuple arity; if it greps for an exact 2-tuple unpack shape, update.

### §1.3 D2d encoder — RESOLVED (auditor §3 item 4 + §2; architect's deferred §11.1 grep APPENDED)

`core/event_log/producer.py::_event_log_default` (line 87) uses `dataclasses.asdict(obj)` (lines 100 + 117) → the new `confidence_is_no_signal` field serializes to JSON automatically. **NO encoder edit needed.** Only the explicit decoder `core/event_log/types.py::_identity_claim_from_dict` (line 124) needs the planned one-liner `confidence_is_no_signal=bool(d.get("confidence_is_no_signal", False))`. D2d shrinks from Plan v1's "~3 line edits" to **1 line edit** (decoder only). This resolves the architect's other Plan v1 §11.1 deferred grep cleanly (auditor §2 confirmed).

### §1.4 Completeness (auditor §3 item 5 + architect verification)

Auditor §3 item 5: "no other at-risk surfaces — no positional IdentityClaim construction breaks, no field-count assertions, no `embed()` conflation." Architect Plan-v2 verification confirms:
- The 7th trailing-default field (`confidence_is_no_signal: bool = False`) is positionally safe in all `IdentityClaim(...)` constructions (5 fixture sites in event_log_fixtures.py + ~28 in test_reconciler.py + the 7 production sites) — they use keyword args OR the first 6 positional fields; a trailing default breaks nothing. No `dataclasses.fields(IdentityClaim)` field-count assertion anywhere (auditor §2 ✓).
- The PI is bounded to: 3 production callers + 15 test-fakes + 1 decoder one-liner + 1 ripple flag. No other surfaces.

---

## §2 D-decisions (refined — D2c 3-caller, D2d resolved, D6 exhaustive test-fakes)

D1, D2a, D2b, D2e, D3, D4, D5 UNCHANGED from Plan v1 §2 (auditor §2 cleared all). Refinements:

### D2c (REVISED) — reconciler kwarg + **3-caller** propagation

`core/reconciler.py:112` `_build_routing_inputs` gains keyword-only `v_score_is_no_signal: bool = False`; construction sets `confidence_is_no_signal=v_score_is_no_signal`. **3 production callers updated** (§1.1): 2439 + 7539 standalone (`, _ =`); 7804 unpacks `_v_is_no_signal` + propagates to `_build_routing_inputs`. (Was: "the caller" singular.)

### D2d (RESOLVED) — decoder one-liner only

`core/event_log/types.py:124` `_identity_claim_from_dict`: add `confidence_is_no_signal=bool(d.get("confidence_is_no_signal", False))`. Encoder needs NO change (asdict-automatic, §1.3). A6 event-log round-trip anchor verifies serialize→JSON→reconstruct preserves the flag.

### D6 (REVISED) — exhaustive test-fake fan-out

15 test-fake sites (§1.2) updated to 3-tuples + 5 MF8 test updates (Plan v1 §1.3, unchanged) + 1 ripple flag verified. Production consumers 3481/5859 read-only (Plan v1 §1.4, unchanged).

---

## §3 Cross-spec impact (re-done §4.1 arithmetic — auditor §3 item 2)

| D | New files | Modified files | Production line edits |
|---|---|---|---|
| D1 | — | `core/voice_channel.py` (field + docstring) | 8 |
| D2a | — | `core/voice.py` (3 returns + docstring) + `core/voice_channel.py:88` (_IdentifyFn alias) | 6 |
| D2b | — | `core/voice_channel.py` (5 identify_speaker sites + 1 unpack) | 7 |
| **D2c (REVISED)** | — | `core/reconciler.py:112` (kwarg + construction = 2) + `pipeline.py` (**3 callers**: 2439 + 7539 + 7804-with-propagate = ~5) | **7** |
| **D2d (RESOLVED)** | — | `core/event_log/types.py:124` (decoder one-liner; encoder auto) | **1** |
| D2e | — | `core/reconciler.py` (6 predicate migrations) | 6 |
| D4 | — | `core/session_state.py` (3 fields + 3 conversions) | 6 |
| D3 | `tests/test_no_exact_equality_against_claim_confidence.py` (NEW) | — | — |
| D5 | `tests/test_session_snapshot_collection_fields_are_immutable.py` (NEW) | — | — |

**ARITHMETIC SUM-AGAINST-TOTAL** (4-part Pass-2 grep rule — Bundle 5 = candidate 3rd instance):
- New files: **2** (test files)
- Modified production files: **6** (`core/voice.py`, `core/voice_channel.py`, `core/reconciler.py`, `core/event_log/types.py`, `pipeline.py`, `core/session_state.py`)
- Production line edits: 8 + 6 + 7 + 7 + 1 + 6 + 6 = **41** (Plan v1 said 42; D2d shrank 3→1 [encoder auto], D2c grew 6→7 [1→3 callers]; net −1)
- Test surface: 2 new files + **15 test-fake updates** + 5 MF8 test updates + 1 ripple verify = ~22 test edits

**Arithmetic verified**: 8+6+7+7+1+6+6 = 41 production line edits across 6 modified files; 2 new test files; 15+5+1 = ~21 test edits. The D2c SITE count corrected from 1→4 (3 callers + reconciler); the test-fake count corrected from ~8→15. ✓

---

## §4 Q5 LOCK — 7 HOLDS (auditor §2 + §4)

The BLOCKING PI adds edits WITHIN existing anchors, no new anchor:
- A2 (voice.identify 3-tuple) absorbs D2a (unchanged scope)
- A4 (reconciler/pipeline wiring) absorbs the 3-caller D2c fan-out (was 1 caller)
- A5 (event-log round-trip) absorbs the D2d decoder-only resolution
- A7 (MF8) absorbs the 15-test-fake fan-out within D6

**Q5 LOCK = 7. NARROW band [5.95, 8.05]. Falsification ≤4 OR ≥10.** Collection fan-out ~21-25 (single-file-scope invariants). Closure-projection: 7 exact = 0% ON-TARGET → `Doctrine-prediction-precision-improving-over-arc` 13→14 streak.

---

## §5 Discipline counts + `Multi-axis-precision-pattern` RENAME

### §5.1 Per-artifact-driven (4-artifact cycle)

| Discipline | Pre-Bundle-5 | Phase 0 | Plan v1 | **Plan v2** | Closure |
|---|---|---|---|---|---|
| Strict-industry-standard mode applications | 126 | 127 | 128 | **129** | 130 |
| Spec-first review cycle | 135 | 136 | 137 | **138** | 139 |
| `### Grep-baseline-before-drafting` | 93 | 94 | 95 | **96** | 97 |
| Cross-cycle-handoff transparency | 96 | 97 | 98 | **99** | 100 |
| Spec-time grep-verification | 103 | 104 | 105 | **106** | 107 |

### §5.2 NEW doctrine instances (auditor §4)

| Discipline | Pre | After closure | Event |
|---|---|---|---|
| `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` | 12 | **13** | CAUGHT-REAL-GAP (ENUMERATION-DRIFT — the 2 unmapped callers) |
| `Plan-v1-Pass-2-grep-undercount` | 16 | **17** | the 2 unmapped callers (+ test-fake 8→15 banked under same umbrella) |
| `Multi-axis-precision-pattern-across-Pre-P1-bundles` (RENAMED) | 2 | **3 — SUB-RULE ELEVATION EVENT** | 4 of 5 Pre-P1 bundles blocked (B1✗ B2✗ B3✗ B4✓ B5✗); only Bundle 4 cleared OPTIONAL-Plan-v2 |
| `### Phase-0-catches-wrong-premise` | 13 | **STAYS 13** | wrong-FILE = LINE-REF-DRIFT family |
| `Pre-audit-quantifier-precision-refined-by-grep` | 12 | **STAYS 12** | caller-fanout is Plan-v1 Pass-2, not Phase-0 |
| BIDIRECTIONAL-VALIDATION sub-rule | 5 | **STAYS 5** (closure may adjudicate a discrete 6th for the Plan-v1-stage catch + the architect-catches-auditor test-fake catch) | per auditor + architect mutual restraint |
| OPTIONAL-Plan-v2 sub-rule | 20 | **STAYS 20** | Bundle 5 ships ≥4-artifact |

### §5.3 `Multi-axis-precision-pattern` RENAME (auditor §4 methodology-honesty flag — ACCEPTED)

The sub-rule's prior name `Multi-axis-precision-pattern-confirmed-by-3-consecutive-blocked-bundles` is **literally false**: Bundle 4 cleared OPTIONAL-Plan-v2 between Bundle 3 (blocked) and Bundle 5 (blocked) — they are NOT consecutive. The auditor will NOT bless a "3-consecutive" elevation. **Architect ACCEPTS the rebaseline** (mirrors the auditor's banked `feedback_auditor_q5_methodology_rebaseline.md`: when accumulated artifacts reveal the original framing was an artifact, rebaseline rather than force-fit). 

**New name: `Multi-axis-precision-pattern-across-Pre-P1-bundles`.** Underlying observation REINFORCED (not weakened): Pre-P1 doc/config/contract work has multi-axis precision surfaces (Bundle 1 measurement-axis; Bundle 2 file-count + license-axis; Bundle 3 arithmetic + AST-scope-axis; Bundle 5 caller-fanout + construction-surface-axis) that benefit from staged Plan-vN absorption. 4 of 5 bundles blocked; only Bundle 4 (the leanest — 3-decision observability) cleared at Plan v1. **Architect finalizes the rename in CLAUDE.md at closure** per auditor direction. Sub-rule ELEVATION EVENT LOCKS at Bundle 5 closure under the honest name.

### §5.4 Multi-discipline preventive convergence (Bundle 5 — 11-floor preserved)

Per `### Multi-discipline-preventive-convergence` numbered doctrine (Bundle 3 [11] → Bundle 4 [11] → Bundle 5 [11]):
1. LINE-REF-DRIFT preventive (Phase 0 715/739/794 → 719/743/798)
2. CROSS-PATH-SYNC-OMISSION preventive commitment
3. DEFERRED-CANARY-ENTRY-OMISSION grep-verify
4. Closure-audit verdict forwarding 10th-cycle routinization
5. CODE-TEMPLATE-MISIDENTIFICATION preventive (IdentityClaim frozen-field-add + SessionSnapshot tuple vs P0.7.1 shape)
6. Developer Pass-3 grep at Phase 4 (numbered doctrine carry-forward)
7. §0 NEW commitment EXTENSION dual-axis (file-count + semantic-correctness)
8. BIDIRECTIONAL-VALIDATION active (5th instance Phase 0; architect-catches-auditor test-fake catch flagged for closure)
9. Phase 0 + Plan v2 explicit-per-bucket grep enumeration (caller fan-out + test-fake fan-out both exhaustively grep-verified — the bundle's own lesson applied)
10. Cross-bundle architectural-coherence preventive (D3 AST invariant scope)
11. 4-part Pass-2 grep ARITHMETIC SUM-AGAINST-TOTAL (§3 verified; Bundle 5 = candidate 3rd instance for formalization)

**11 preventives at Bundle 5 Plan v2** — sustained 11-floor.

---

## §6 Closure-narrative paste template

```markdown
| **Pre-P1 Bundle 5 (Contract Typing MF7+MF8 — FINAL Pre-P1 bundle — `IdentityClaim.confidence_is_no_signal` BACKEND-SETS decoupling [voice.identify 3-tuple return → 3 production callers + identify_speaker 5-site + reconciler construction kwarg + event-log decoder + 6-predicate migration] + `SessionSnapshot` 3-field list→tuple — 4-artifact cycle [Phase 0 BLOCKING Q3 sole-construction-site PI → Plan v1 re-baseline → Plan v2 BLOCKING caller-fanout PI [1→3 callers] absorbed → closure]) CLOSED 2026-05-2X** — [SUMMARY: MF7 decouples reconciler from ECAPA exact-0.0 via `confidence_is_no_signal` SET AT THE BACKEND (`voice.identify` returns `(pid, score, is_no_signal)` — 3 production callers updated [2439/7539 standalone `, _ =`; 7804 unpack+propagate]; identify_speaker 4 no-signal-by-construction + success-path unpack; reconciler.py:112 kwarg; event-log decoder round-trip [encoder asdict-automatic]); 6 reconciler predicates migrated [3 `==`→flag, 2 `!=`→`not flag`, 1 `<=`→`flag or <0` preserving Session-119]; 15 test-fakes → 3-tuples; MF8 SessionSnapshot 3 fields list→tuple + _to_snapshot]. **7/7 anchors A1-A7 GREEN** ~21-25 collections. **N/N deliberate-regression confirmations passed**. **Doctrine bumps**: `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` 12→13 (CAUGHT-REAL-GAP — auditor caught architect's 1→3 caller undercount; deferral-pattern realized). `Plan-v1-Pass-2-grep-undercount` 16→17. `Multi-axis-precision-pattern-across-Pre-P1-bundles` 2→3 SUB-RULE ELEVATION + RENAME (dropped false "3-consecutive"; 4 of 5 bundles blocked, only B4 cleared). BIDIRECTIONAL-VALIDATION STAYS 5 (architect-catches-auditor test-fake undercount 8→15 flagged, not inflated). `### Phase-0-catches-wrong-premise` STAYS 13. `Pre-audit-quantifier` STAYS 12. OPTIONAL-Plan-v2 STAYS 20. `Doctrine-prediction-precision-improving-over-arc` 14th 0%-streak (if closure-actual=7). 4-part Pass-2 grep ARITHMETIC rule 3rd instance. **FINAL Pre-P1 must-fix bundle CLOSED** — all 5 bundles (Docs+CI / Governance / Critical-bugs / Observability+Concurrency / Contract-typing) shipped. Next: P1 cycle (8-10 week clock, 5 parallel tracks). **No CI evidence event required**.
```

---

## §7 Honest-count commitment

Per `Explicit-closure-honest-count-commitment`: Plan v2 §7 MADE → closure §7 HONORED = 2 instances. IF closure-actual = 7 exact → `Doctrine-prediction-precision-improving-over-arc` 14th-streak. {6,8} → ON-TARGET, doctrine bumps, streak interrupted. {5,9} → SLIGHT-DRIFT, doctrine HOLDS, streak interrupted. ≤4 OR ≥10 → FALSIFICATION-WATCH.

---

## §8 Completeness statement (auditor §3 item 5 — architect-confirmed, zero deferral)

Bundle 5 PI surface is BOUNDED and EXHAUSTIVELY enumerated:
- **3 production callers** (grep-verified, no hidden 4th)
- **15 test-fake sites** (grep-verified across 7 test files; corrects auditor's ~8)
- **1 decoder one-liner** (encoder asdict-automatic)
- **1 ripple flag** (test_p0_r6_y_ecapa_worker.py:311 source-inspection — verify at Phase 4)
- No positional IdentityClaim construction breaks (7th field trailing-default safe)
- No field-count assertions
- No `embed()` conflation
- MF8 break-set = exactly 5 (test_pipeline.py:8138 + test_session_store.py:260/403/435/532); owner-side reads 69/71/74 safe

**No deferred greps remain.** Every count in this Plan v2 is grep-verified at drafting (the bundle's own lesson: the D2c deferral was the PI; Plan v2 carries zero deferrals).

---

## §9 Standing by for auditor Plan v2 verdict

If CLEAN → Plan v2 ships to developer for Phase 4 (4-artifact cycle: Phase 0 + Plan v1 + Plan v2 + closure). `Multi-axis-precision-pattern-across-Pre-P1-bundles` 3rd-instance elevation + rename LOCKS at closure.

If NEW PIs → Plan v3 (would be unusual given the exhaustive §1 enumeration + §8 completeness statement; architect's confidence is HIGH and the residual-risk deferrals that produced the v1→v2 PI are now zero).

**Architect's Plan v2 confidence: HIGH.** The Q3 backend-sets architecture is ratified (auditor §5); the BLOCKING caller-fanout PI is absorbed with all 3 callers + 15 test-fakes grep-verified and appended (no deferral); the encoder is resolved; the completeness statement bounds the surface. The deferral-pattern that caused the v1→v2 escalation is structurally eliminated from this artifact.

---

**Filed**: 2026-05-29
**Architect**: Claude
**Forwarded to**: Auditor (external)
**Prior artifact**: `tests/pre_p1_bundle5_contract_typing_plan_v1.md` (Plan v1 NOT CLEAN — D2a 3-tuple return had 3 production callers not 1; deferral-pattern realized; absorbed at Plan v2 with exhaustive caller [3] + test-fake [15] enumeration + encoder-resolved + completeness statement)
