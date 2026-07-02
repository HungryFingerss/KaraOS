# Pre-P1 Bundle 5 — CORRECTED CLOSURE NARRATIVE → forwarded for auditor final bank confirm (2026-05-29)

**Status**: All 4 auditor-required corrections (verdict `info.md` §5) resolved. Forwarding the exact ready-to-bank content for the auditor's final confirm per "Forward the corrected closure narrative and I'll confirm the bank." On confirm, applied to CLAUDE.md banner + doctrine bodies + both memory paths + `to_be_checked.md`.
**Architect**: Claude · **Auditor**: External

---

## §1 — Correction 1 RESOLVED: 13-vs-19 reconciliation (developer-reconciled, architect grep-grounded)

The "19" conflated two distinct failure populations + carried a +1 assert→raise overcount. Banking-accurate breakdown:

### Population B — 13 distinct PRE-EXISTING failures (predate Bundle 5; 10 fix-actions, 1-to-many)

| Pre-existing failure(s) | Count | Root cause | Fix-action(s) |
|---|---|---|---|
| test_cache_store: entry_expired_after_ttl / expired_entry_removed_lazily / ttl_miss_increments_miss_counter | 3 | Bundle-3 cache TTL paired-clock bug | 1 prod fix (cache_store.set → monotonic) |
| test_pipeline::enrollment_mishear_escape_hatch_skips_when_session_stale | 1 | Bundle-3 monotonic-vs-wallclock | 1 prod fix (pipeline.py:628 → time.time() + WALLCLOCK) |
| test_pipeline::add_embedding_rejects_unknown_source / open_session_rejects_invalid_person_type + test_p09 verify_post ×3 | 5 | Bundle-3 assert→raise; tests expected AssertionError | 5 test-expectation edits (1:1) |
| test_p0_s5::every_user_role_content_passes_through_wrap_user_input / indirect_boundaries_allowlist_entries_are_real_sites | 2 | P0.S5 allowlist LINE-REF-DRIFT | 1 allowlist line-key refresh (17 keys, fixes both) |
| test_p0_r5: d1_pyannote / d2_speechbrain | 2 | vendored fork absent on Windows dev | 2 importorskip edits (1:1) |
| **Total** | **13** | | **10 fix-actions** (2 prod + 5 test-edit + 1 allowlist + 2 importorskip) |

**Two corrections to the developer's initial failure-breakdown (run-log-verified by the developer; architect grep-grounded — all 5 named tests confirmed to exist)**: assert→raise is **5, not 6** (5 distinct test functions); the **2 P0.S5 failures share ONE allowlist-refresh fix**, not two. Attribution (per auditor final-confirm touch-up): the "6" was the developer's initial breakdown component, which the **auditor flagged for reconciliation in closure-audit §5** ("6+8+1+2=17, needs reconciliation"); the **developer then reconciled** to the run-verified "5". The "5" supersedes the "6" — the §3 synthesis in action (the run is the proof; the initial static breakdown was bounded by its method). This is the bundle's last bidirectional catch, fittingly an attribution correction in a record whose theme is honest attribution.

### Population A — 8 distinct Bundle-5-CAUSED D2e-ripple failures (NOT pre-existing)

The auditor's "8 reconciler no-signal fixtures" belong HERE. D2e correctly migrated reconciler predicates `== 0.0` → flag-based, so fixtures building no-signal claims with `confidence=0.0` (no flag) needed `confidence_is_no_signal=True`. Expected ripple from a correct production change:
- 5 in test_reconciler.py (surfaced in targeted runs, fixed before the first full-suite run)
- 3 in test_p10_reconciler_contract.py (c17/c18/c20 — surfaced in the first full-suite run, fixed before the second)

The negative-cosine canary `test_p4_pyannote_vouched_stranger_negative_confidence` (−0.05) **passed throughout** (grep-confirmed at reconciler.py:469 + the `< 0.0` half preserved at :634) — confirming the anti-correlation half is independent + load-bearing (Session-119 intact).

### Banking-accurate numbers
- **13 distinct pre-existing failures** (Population B)
- **8 distinct Bundle-5-D2e-ripple failures** (Population A)
- **21 distinct test failures touched this cycle** (13 + 8) + 1 transient A2-invariant (developer's own enrollment-fix annotation placement, self-caught + fixed)
- 2 production bugs are within Population B (cache TTL + enrollment-mishear)
- The "19" = 11 Population-B fix-categories (auditor framing, +1 assert→raise overcount → 10) + 8 Population-A ripple, summed across buckets without distinguishing them.

**Architect note on verification boundary** (honoring the bundle's own lesson): the 5-vs-6 and 13-vs-8-split are run-log facts from the developer's execution — I grep-grounded that the named tests exist + the canary holds, but "which tests failed in the run" is not a static-code fact I can grep-settle. I take the failure-counts from the developer's run (they ran it; the run is the proof) and state that boundary plainly rather than overclaim a grep I cannot perform.

---

## §2 — CORRECTED CLOSURE NARRATIVE (proposed CLAUDE.md banner entry — ready to bank)

> **Pre-P1 Bundle 5 (Contract Typing MF7+MF8 — FINAL Pre-P1 bundle — `IdentityClaim.confidence_is_no_signal` BACKEND-SETS decoupling [voice.identify 3-tuple return → **5 production callers** (3 pipeline.py: 2444/7544 standalone + 7809 unpack+propagate@8081; **2 voice.py intra-module: _diarize_ecapa_valley:219 + _diarize_pyannote:352** — caught at Phase 4, corrects the handoff's "3 grep-verified exhaustive" undercount) + identify_speaker 5-site flag-set + reconciler.py:120 construction kwarg + event-log decoder (encoder asdict-automatic) + 6-predicate migration] + `SessionSnapshot` 3-field list→tuple frozen-by-construction — 5-artifact cycle [Phase 0 BLOCKING sole-construction-site PI → Plan v1 re-baseline → Plan v2 BLOCKING caller-fanout PI (1→3) → Plan v3 test-fake surface-class re-scope → closure-audit caller-undercount (3→5) + arc-level green-suite finding]) CLOSED 2026-05-29** — MF7 decouples reconciler from ECAPA exact-0.0 via `confidence_is_no_signal` SET AT THE BACKEND (`core/voice.py::identify` returns `(pid, score, is_no_signal)` — line 434 `None,0.0,True` / match `False` / gallery-miss `False`); identify_speaker 4 no-signal-by-construction sentinels (162/171/183/200) + success-path 3-tuple unpack (217); 5 production callers; reconciler.py:120 construction kwarg + 6-predicate migration (3 `==`→flag @725/749/804, 2 `!=`→`not flag` @666/782, 1 `<=`→`flag or confidence<0.0` @634 **preserving Session-119 anti-correlation** — canary `test_p4_pyannote_vouched_stranger_negative_confidence` −0.05 passed throughout); event-log decoder `_identity_claim_from_dict` one-liner (encoder `_event_log_default` asdict-automatic). MF8: `SessionSnapshot` recent_voice_confs/core_memory/recent_attributions (110/112/115) list→tuple + `_to_snapshot` (144/146/149) `tuple(...)`; owner `Session` (76/78/81) stays list. **2 NEW AST invariants** (test_no_exact_equality_against_claim_confidence bans Eq+NotEq allows Lt/LtE; test_session_snapshot_collection_fields_are_immutable). **7/7 anchors A1-A7 GREEN** + 7/7 deliberate-regression confirmations passed (incl. the <0.0-drop Session-119 canary). **Full suite GENUINELY GREEN — 3795 passed / 16 skipped / 9 xfailed / 0 failed (289s)** — the first independent end-to-end full-suite run of the Pre-P1 arc (the new closure-gate; see arc-level finding). **Cycle remediated 21 distinct failures: 13 pre-existing (Population B — incl. 2 latent Bundle-3 DEADLINE-MATH production bugs) + 8 Bundle-5-D2e-ripple (Population A).** **2 PRODUCTION BUGS shipped by Bundle 3, latent through Bundle 4, surfaced + fixed here**: (1) `cache_store.py` set/peek monotonic-vs-wallclock mismatch → entries never expired (P0.5/P0.X PAIRED-WRITE clock-mismatch class; fixed :125 monotonic both sides); (2) `pipeline.py:628` enrollment-rename grace-window reader monotonic-vs-wallclock → stale session read as "fresh", bypassing dispute-protection (security implication; fixed → time.time() + WALLCLOCK). **Doctrine bumps**: `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` 12→13 CAUGHT-REAL-GAP (fired 3× in-bundle: v1 caller catch + v2 test-fake-count catch + architect-catches-auditor test-fake direction; reinforcing within the 13th, no inflation). `Plan-v1-Pass-2-grep-undercount` 16→18 (17th = v1→v2 pipeline caller-fanout 1→3 auditor-caught; 18th = Phase-4 voice.py intra-module 3→5 developer-caught). `### Developer-Pass-3-grep-at-Phase-4-pre-implementation` 4→5 — **1st CATCHING-mode instance** (vindicates the auditor's Plan v3 prediction; caught the 2 voice.py callers architect+auditor both missed). `Multi-axis-precision-pattern-across-Pre-P1-bundles` 2→3 SUB-RULE ELEVATION + RENAME (dropped falsified "3-consecutive" — Bundle 4 cleared between B3+B5; 4 of 5 bundles blocked; 3 precision axes in B5: construction-surface@Phase0 / caller-fanout@PlanV1 / enumeration-recursion@PlanV2). `### Phase-0-granular-decomposition-enables-accurate-estimates` 34→35 (Q5=7 exact-mid; `Doctrine-prediction-precision-improving-over-arc` 14th consecutive 0%-streak). `### Multi-discipline-preventive-convergence` **STAYS 11** (developer's "10→11" was a DOCTRINE-ARITHMETIC-MISATTRIBUTION 2nd instance — baseline is 11 (B4=11th); banks under `Per-artifact-arithmetic-drift-survives-grep-baseline` architect↔developer track record; watch 3rd for sub-shape formalization). `### Architect-reads-production-code-before-sign-off` 34→35 (closure-audit caught the caller-undercount confirmation + 2 bug-fix verifications + Multi-discipline discrepancy + 13-vs-19 arithmetic). BIDIRECTIONAL-VALIDATION **STAYS 5** (increments at most once per bundle for the most architecturally-significant cross-actor catch — banked at Phase 0 auditor-catches-architect sole-construction-site; B5 had 6 cross-actor catches, bumping for any one would violate the anti-inflation discipline this bundle taught). Auditor-Q5-estimates-trail-grep 40→41. `### Twin-filename-pitfall-prevention` 35→36. Deferred-canary 37→38. `### Phase-0-catches-wrong-premise` STAYS 13 · `Pre-audit-quantifier-precision-refined-by-grep` STAYS 12 · OPTIONAL-Plan-v2 STAYS 20 · Q5=7. Strict-mode 131 / spec-first 140 / grep-baseline 98 / cross-cycle 101 / spec-time 108. **NEW**: `Self-correcting-surface-resists-exhaustive-pre-enumeration` (Plan v3) generalized to its mature form **`Full-suite-run-is-the-universal-completeness-proof`** (no static-verification claim — grep, anchor-subset — asserted exhaustive beyond its method's actual coverage; the deepest lesson of the 5-bundle arc) + `Full-suite-first-run-surfaces-prior-bundle-ripple` — all banked at both memory paths. **NEW closure-gate banked under `### Verification-before-completion`**: every closure runs the full suite with output shown; that run is the completeness proof. **FINAL Pre-P1 must-fix bundle CLOSED** — all 5 bundles (Docs+CI / Governance / Critical-bugs / Observability+Concurrency / Contract-typing) shipped; 5-bundle Pre-P1 arc COMPLETE (2nd arc-completion milestone, sibling to the P0.R resilience-track arc under `### Resilience-track-arc-completion` — advances that sub-rule's elevation candidacy). Next: P1 cycle (8-10 week clock; 5 parallel tracks). Cumulative suite: **3795 passed / 16 skipped / 9 xfailed / 0 failed**.

---

## §3 — Correction 2: Bundle 3 + Bundle 4 honesty annotations (auditor strengthened verbatim — ready to apply to both closure entries)

Appended to BOTH the Bundle 3 and Bundle 4 banner closure entries:

> *"[Honesty annotation appended at Bundle 5 closure 2026-05-29 per `### Verification-before-completion`]: The '~3734 / ~3755 passing' figure was derived from anchor-test + incremental-subset verification + `pytest --collect-only` counts, NOT from an independent end-to-end full-suite run. Bundle 5's green-suite gate (the first full-suite run of the Pre-P1 arc) surfaced 2 latent Bundle-3 DEADLINE-MATH production bugs the Bundle 3/4 verification method did not exercise: cache_store TTL clock-mismatch + pipeline.py:628 enrollment-rename WALLCLOCK. Both fixed at Bundle 5."*

Tie-in note: this is a violation of an **already-named** doctrine (`### Verification-before-completion` + the P0.0.7-banked "full-suite verification before 'no regressions' claim"), NOT a new doctrine — evidence the existing one wasn't enforced at the closure-gate. Role boundary stated plainly in the annotation context: neither the architect's role (grep-verify production surfaces) nor the auditor's role (same) included running pytest — that hole is the systemic finding, not a blame assignment; the auditor owns ratifying B4's "~3755" without an independent full-suite run behind it. The new closure-gate closes the hole for both roles.

---

## §4 — Correction 3: doctrine dispositions (as adjudicated, ready to bank)

| Doctrine | Disposition | Source |
|---|---|---|
| Pass-2-grep-auditor-verified | 12 → **13** CAUGHT-REAL-GAP (3× in-bundle, reinforcing within 13th) | auditor §4 |
| Plan-v1-Pass-2-grep-undercount | 16 → **18** (17th pipeline-caller + 18th voice.py intra-module) | auditor §4 |
| Developer-Pass-3-grep-at-Phase-4 | 4 → **5** (1st CATCHING mode) | auditor §4 |
| Multi-axis-precision-pattern-across-Pre-P1-bundles | 2 → **3** ELEVATION + RENAME (drop "3-consecutive") | auditor §4 |
| Phase-0-granular-decomposition | 34 → **35** (+ Doctrine-prediction-precision 13→**14**, Q5=7 exact-mid) | auditor §4 |
| Multi-discipline-preventive-convergence | **STAYS 11** (dev "10→11" = DOCTRINE-ARITHMETIC-MISATTRIBUTION 2nd instance → banks under Per-artifact-arithmetic-drift architect↔developer; watch 3rd) | auditor §4 |
| BIDIRECTIONAL-VALIDATION | **STAYS 5** (once-per-bundle; banked at Phase 0; anti-inflation) | auditor §4 |
| Architect-reads-production-code-before-sign-off | 34 → **35** | this closure-audit |
| Phase-0-catches-wrong-premise | STAYS **13** | auditor §4 |
| Pre-audit-quantifier-precision-refined-by-grep | STAYS **12** | auditor §4 |
| OPTIONAL-Plan-v2 sub-rule | STAYS **20** | auditor §4 |
| Auditor-Q5-estimates-trail-grep | 40 → **41** | this cycle |
| Twin-filename-pitfall-prevention | 35 → **36** | this cycle |
| Deferred-canary strategy | 37 → **38** | this cycle |
| Per-artifact (5-artifact) | strict-mode **131** / spec-first **140** / grep-baseline **98** / cross-cycle **101** / spec-time **108** | this cycle |

---

## §5 — Correction 3 (cont.): NEW observations + closure-gate + arc-completion (banking targets)

1. **`Full-suite-run-is-the-universal-completeness-proof`** (the §3-synthesis mature form of Plan v3's `Self-correcting-surface-resists-exhaustive-pre-enumeration`): *no static-verification claim — grep bounded by pattern+scope, anchor-subset bounded by not-full-run — should be asserted as exhaustive beyond its method's actual coverage; the full-suite run, actually run, is the universal completeness/correctness proof.* Deepest lesson of the 5-bundle arc; lands on the final bundle. → both memory paths (architect-memory + auditor-facing), alongside the Plan v3 observation.
2. **`Full-suite-first-run-surfaces-prior-bundle-ripple`** (1st instance — Bundle 5's first full-suite run surfaced 2 latent Bundle-3 production bugs + the Population-B pre-existing hole). → both memory paths.
3. **NEW closure-gate under `### Verification-before-completion`**: every closure runs the full suite with output shown; that run is the completeness proof (operationalizes the already-named doctrine that wasn't enforced at the B3/B4 closure-gates). → CLAUDE.md doctrine body.
4. **Arc-completion under `### Resilience-track-arc-completion` sibling framing**: the 5-bundle Pre-P1 must-fix arc completes — a 2nd arc-completion milestone across a distinct track (P0.R resilience arc was the 1st). Advances that sub-rule's elevation candidacy. → CLAUDE.md doctrine body.
5. **`DOCTRINE-ARITHMETIC-MISATTRIBUTION` sub-variant 2nd instance** (B4 "9→10" dropped B3's 10th; B5 "10→11" dropped B4's 11th) under `Per-artifact-arithmetic-drift-survives-grep-baseline` / architect↔developer track record. Watch 3rd for sub-shape formalization.

---

## §6 — Standing

All 4 corrections resolved + ready to bank. **Forwarding for the auditor's final bank confirm.** On confirm, the architect applies, in one coherent pass:
- CLAUDE.md banner: prepend the §2 corrected closure entry + append the §3 honesty annotations to the Bundle 3 + Bundle 4 entries
- CLAUDE.md doctrine bodies: the §4 dispositions + the Multi-axis RENAME + the §5 closure-gate (under Verification-before-completion) + arc-completion (under Resilience-track-arc-completion)
- Both memory paths: the 2 NEW observations + the DOCTRINE-ARITHMETIC-MISATTRIBUTION 2nd instance
- `to_be_checked.md`: Bundle 5 deferred-canary entry (fresh-disk Python read verify)

On bank, **Bundle 5 — the FINAL Pre-P1 must-fix bundle — CLOSES**, completing the full 5-bundle Pre-P1 arc. Project moves to the P1 cycle.

The final bundle earned its keep: its green-suite gate caught 2 production bugs that shipped through two prior "green" closures, and its caller-enumeration recursion (auditor ~8 → architect 15 → auditor 17; pipeline 1→3→ + voice.py 3→5) taught the arc's deepest lesson — **the run is the proof; static claims are bounded by their method.**

---

**Architect**: Claude · **Filed**: 2026-05-29 · **Forwarded to**: Auditor (external) for final bank confirm
