# Pre-P1 Bundle 5 — Contract Typing (MF7 + MF8) Phase 0 Audit (2026-05-29)

**Cycle**: Pre-P1 must-fix Bundle 5 (Contract Typing) — FINAL Pre-P1 bundle
**Scope**: MF7 (`IdentityClaim.confidence_is_no_signal` field — decouple reconciler from ECAPA's exact-0.0 no-signal convention) + MF8 (`SessionSnapshot.recent_voice_confs`/`core_memory`/`recent_attributions` `list`→`tuple` frozen-by-construction)
**Source**: CEO-FINAL-P1-PLAN MF7 (§255-258) + MF8 (§266-270) = TechAnalyst-1 B-H1 + B-H2
**Sequencing**: Pre-P1 must-fix sequence position 5 of 5 (CEO synthesis Path A locked) — sequential after Bundle 4 close 2026-05-28
**Discipline**: Strict-mode; Bundle 1-4 carry-forward (Developer-Pass-3-grep numbered doctrine + 4-part Pass-2 grep rule + Multi-discipline-preventive-convergence + BIDIRECTIONAL-VALIDATION 4-way matrix + Multi-axis-precision-pattern watch at 2 instances)
**Architect**: Claude
**Auditor**: External

---

## §0 Procedural commitments (Bundle 1-4 carry-forward)

All Bundle 4 §0 commitments PRESERVED. Bundle 5 carries forward the now-locked numbered doctrines:

1. **Path C grep-verify at closure surface** (production + memory + `to_be_checked.md` fresh-disk Python read)
2. **Cross-path memory-file discipline** if new memory files land
3. **DEFERRED-CANARY-ENTRY-OMISSION preventive** via fresh-disk Python read at closure
4. **Closure-audit verdict forwarding** to auditor (10th-cycle routinization)
5. **CODE-TEMPLATE-MISIDENTIFICATION preventive** — `IdentityClaim` field-add template verified against the actual frozen-dataclass shape (P0.B1 VoiceEvidence frozen precedent); `SessionSnapshot` tuple migration verified against P0.7.1 frozen+slots shape
6. **§0 NEW commitment EXTENSION dual-axis verification** at developer Pass-3 (file-count + semantic-correctness) — MANDATORY per `### Developer-Pass-3-grep-at-Phase-4-pre-implementation` numbered doctrine (Bundle 3 elevation)
7. **4-part Pass-2 grep operational rule** applied at Plan v1+ (symbol-name uniqueness + behavioral-semantic + symmetric verification + **ARITHMETIC SUM-AGAINST-TOTAL** — Bundle 3 lesson; 2 instances banked, Bundle 5 = candidate 3rd for formalization)
8. **Multi-discipline preventive convergence enumeration** at Plan v1 §5.4 + preserved at closure (`### Multi-discipline-preventive-convergence` numbered doctrine; trajectory Bundle 1 [7] → Bundle 2 [9] → Bundle 3 [11] → Bundle 4 [11])
9. **BIDIRECTIONAL-VALIDATION sub-rule active** — Bundle 4 completed the 4-way actor matrix; sub-rule live for Bundle 5
10. **Phase 0 explicit-per-bucket grep enumeration** — applied at §1 (no globbed-pattern approximation; Bundle 2 lesson)
11. **`Multi-axis-precision-pattern-confirmed-by-3-consecutive-blocked-bundles` at 2 instances** — Bundle 5 outcome adjudicates the 3rd-instance ELEVATION EVENT (if Plan v1 blocks) vs observation-matures-without-elevation (if Plan v1 clean)

---

## §1 Grep-verified scope baseline (2026-05-29)

Per `### Grep-baseline-before-drafting` + `Phase-0-globbed-pattern-estimates-imprecise-explicit-enumeration-precise` (Bundle 2 lesson) + 4-part Pass-2 grep arithmetic (Bundle 3 lesson): explicit per-bucket grep enumeration locked at Phase 0 drafting.

### §1.1 MF7 — `IdentityClaim` location + the confidence-vs-0.0 site inventory

**WRONG-FILE PREMISE CAUGHT (`### Phase-0-catches-wrong-premise` candidate)**: CEO MF7 §257 + TechAnalyst-1 B-H1 §165 say `IdentityClaim` is in `core/reconciler_state.py`. **Grep-verified: `IdentityClaim` is defined in `core/voice_channel.py:56-81`** (`@dataclass(frozen=True)`, 6 fields: pid, confidence, n_diarize_segments, utterance_duration, reasoning, raw_segment_scores). `core/reconciler_state.py` has NO `IdentityClaim` class. The MF7 field-add lands in `core/voice_channel.py`, NOT `core/reconciler_state.py`.

**SCOPE QUANTIFIER REFINEMENT (`Pre-audit-quantifier-precision-refined-by-grep` candidate)**: CEO MF7 §257 says "3 `claim.confidence == 0.0` checks at `core/reconciler.py:715, 739, 794`". Grep-verified the ACTUAL confidence-vs-0.0 surface is **6 sites across 3 comparison shapes**:

| Shape | Lines (current) | Semantic | MF7 disposition |
|---|---|---|---|
| `claim.confidence == 0.0` | 719, 743, 798 | "embedding computation failed = no signal" | → `claim.confidence_is_no_signal` (the CEO's 3 named targets) |
| `claim.confidence != 0.0` | 660, 776 | "has real signal (positive OR negative)" — logical INVERSE | → `not claim.confidence_is_no_signal` (Q1 — see §5) |
| `claim.confidence <= 0.0` | 628 | "no signal OR anti-correlated" — documented at reconciler.py:614-619 | → `claim.confidence_is_no_signal or claim.confidence < 0.0` OR stay (Q2 — see §5) |

**LINE-REF-DRIFT sub-shape**: CEO line numbers 715/739/794 → actual 719/743/798 (+4 each from Bundle 3's time.monotonic migration adding ~4 lines to reconciler.py). Same LINE-REF-DRIFT sub-shape as Bundle 3/4. Plan v1 re-greps fresh.

**The 628 `<= 0.0` site is LOAD-BEARING and DOCUMENTED**: reconciler.py:614-619 explicitly explains "`confidence <= 0.0` (not `== 0.0`): ECAPA cosine similarity between two very different speakers' L2-normalized embeddings is often NEGATIVE (anti-correlated). voice.identify() returns the actual best cosine score even on gallery miss — it only returns exactly 0.0 when the embedding computation itself failed." This IS the exact semantic `confidence_is_no_signal` encodes: exactly-0.0 = embedding-failed = no-signal; negative = real-but-anti-correlated signal. The 628 fix is the subtle one (Q2).

### §1.2 MF7 — flag-propagation chain

`IdentityClaim` is CONSTRUCTED at `core/reconciler.py:112` inside `_build_routing_inputs(*, v_pid, v_score, n_diarize_segments, ...)` (keyword-only, line 81) via `confidence=v_score`.

`v_score` originates from `core/voice.py::identify` (line 414), which returns `tuple[str | None, float]`:
- `return None, 0.0` (line 430) — when `emb is None` (embedding computation failed) OR `not voice_gallery` (empty gallery). **THE no-signal sentinel.**
- `return None, best_score` (line 441) — gallery miss; best_score is a real cosine (can be negative). NOT no-signal.
- `return best_id, best_score` (line 440) — real match. NOT no-signal.

**Propagation chain**: `voice.identify` (returns score, 0.0=no-signal) → pipeline.py call site (captures v_score) → `_build_routing_inputs(v_score=...)` → `IdentityClaim(confidence=v_score)` at reconciler.py:112.

**The flag-setting architecture is a genuine decision (Q3 — see §5)**:
- **(a) Backend-sets**: `voice.identify` return signature `(pid, score)` → `(pid, score, is_no_signal)` (3-tuple OR dataclass), threaded through pipeline.py → `_build_routing_inputs` new kwarg → `IdentityClaim(confidence_is_no_signal=...)`. **True decoupling** (a future pyannote-only / cloud backend sets its own no-signal flag), but touches voice.identify return + `_IdentifyFn` type alias (voice_channel.py:88) + all `voice.identify` callers + tests. More than the CEO's 0.5d.
- **(b) Construction-site chokepoint**: `_build_routing_inputs` sets `confidence_is_no_signal=(v_score == 0.0)` at reconciler.py:112. The "0.0 = no-signal" convention lives in EXACTLY ONE place (construction) instead of 6 rule predicates. 0.5d. But re-couples to the ECAPA exact-0.0 convention at the construction site (a future backend returning 0.01 for failure still breaks — just at one place instead of six).
- **(c) Hybrid**: construction-site chokepoint NOW (Bundle 5, 0.5d) + a banked follow-up (Bundle 5.X / P1.B1) to push the flag into the backend return when multi-platform adapters land.

### §1.3 MF8 — `SessionSnapshot` tuple-migration surface (grep-verified clean)

| Surface | Line(s) | Current | MF8 disposition |
|---|---|---|---|
| `Session` (mutable owner) fields | `core/session_state.py:76` recent_voice_confs / `:78` core_memory / `:81` recent_attributions | `list` (default_factory=list) | STAY `list` (owner keeps mutable) |
| `SessionSnapshot` (frozen consumer) fields | `:110` recent_voice_confs / `:112` core_memory / `:115` recent_attributions | `list` | → **`tuple`** (frozen-by-construction) |
| `_to_snapshot` conversions | `:144` list(s.recent_voice_confs) / `:146` list(s.core_memory) / `:149` list(s.recent_attributions) | `list(...)` | → **`tuple(...)`** |
| Session mutations (owner-side, unchanged) | `:298` s.recent_voice_confs.append / `:409` s.recent_attributions.append / `:429` s.core_memory = memory | `.append()` / rebind on owner list | UNCHANGED (owner stays mutable list) |

### §1.4 MF8 — consumer impact (all production-safe; 5 test updates)

**Production consumers of the snapshot fields** (which become tuple) — grep-verified ALL safe:
- `pipeline.py:2247` `_recent_vc = _snap.recent_voice_confs` → READ-ONLY: `len(_recent_vc)` (2249) + `list(_recent_vc)[-N:]` (2252, explicit list() conversion). Tuple-safe ✓
- `pipeline.py:8331` `_drift_attrs = list(_drift_snap.recent_attributions)` → already `list(...)`. Tuple-safe ✓
- `pipeline.py:3481` `core_memory=_kairos_snap.core_memory` → passed as kwarg to a brain context-builder (read-only render). Plan v1 grep-verifies the consumer treats it read-only. Low risk.
- `pipeline.py:5859` `core_memory=_snap_conv.core_memory` → same pattern. Plan v1 verifies.

**Test consumers needing updates** (5 sites):
- `test_pipeline.py:8138` `assert isinstance(snap.recent_attributions, list)` → BREAKS (now tuple). Update to `isinstance(..., tuple)`.
- `tests/test_session_store.py:260` `snap.recent_voice_confs == [0.9, 0.85]` → BREAKS (tuple != list). Update to `== (0.9, 0.85)` (or `list(...) == [...]`).
- `tests/test_session_store.py:403` `snap.recent_attributions == ["face", "voice"]` → BREAKS. Update.
- `tests/test_session_store.py:435` `snap.core_memory == mem` (mem is list) → BREAKS. Update.
- `tests/test_session_store.py:532` `snap1.recent_voice_confs == [0.9]` → BREAKS. Update.

**Test consumers ALREADY safe** (no change):
- `test_pipeline.py:8158` `list(snap.recent_attributions) == ["current"]` → list() conversion ✓
- `tests/test_session_store.py:69/71/74` → these are on the OWNER `s` (Session), which STAYS list ✓
- `tests/test_session_state_invariants.py:277-283` → owner `s.X = [...]` sets + `snap.X is not s.X` identity checks (tuple(...) creates a distinct object, so `is not` holds) ✓

### §1.5 Phase 0 baseline counts (per `### Grep-baseline-before-drafting`)

Pre-Bundle-5 baseline (post-Bundle-4 closure-audit ratification 2026-05-28):
- Strict-industry-standard mode applications: 126
- Strict-industry-standard mode closures: 36
- Spec-first review cycle: 135
- `### Grep-baseline-before-drafting`: 93
- Cross-cycle-handoff transparency: 96
- Spec-time grep-verification: 103
- `### Twin-filename-pitfall-prevention`: 35
- `### Architect-reads-production-code-before-sign-off`: 34 (BIDIRECTIONAL-VALIDATION sub-rule at 4 instances, 4-way matrix complete)
- `### Multi-discipline-preventive-convergence`: 11 instances (Bundle 4 = 11th)
- `### Developer-Pass-3-grep-at-Phase-4-pre-implementation`: 4 instances (Bundle 4 = 4th, 1st preventive-mode)
- `### Pass-2-grep-auditor-verified-before-Plan-v1-approval`: 12 instances
- Auditor-Q5-estimates-trail-grep: 40
- `### Phase-0-granular-decomposition-enables-accurate-estimates`: 34 supporting
- `Doctrine-prediction-precision-improving-over-arc`: 13 consecutive 0%-streak
- OPTIONAL-Plan-v2 sub-rule track record: 20 (Bundle 4 LOCKED the 20th proof case)
- `Per-artifact-arithmetic-drift-survives-grep-baseline`: 19
- `Plan-v2-collection-estimate-omits-AST-invariant-fan-out`: 2
- `Multi-axis-precision-pattern-confirmed-by-3-consecutive-blocked-bundles`: 2 (Bundle 5 adjudicates 3rd-instance elevation vs maturation)
- `Plan-v1-Pass-2-grep-undercount`: 16
- `Zero-precision-items-pre-closure-predictions-blocked`: 6
- `### Zero-precision-items-at-auditor-review`: 42

---

## §2 D-decisions (initial; Plan v1 refines per Q1-Q6 adjudications)

### D1 — MF7: add `IdentityClaim.confidence_is_no_signal: bool` field

`core/voice_channel.py:56-81` IdentityClaim (frozen dataclass) gains a 7th field `confidence_is_no_signal: bool = False` (default False so existing constructions + tests don't break; the flag is opt-in set at the no-signal sentinel). Preserves `frozen=True`. Docstring updated to document the field's contract: "True iff the voice-ID backend reported no usable signal (embedding computation failed OR empty gallery). Distinct from a negative confidence (anti-correlated real signal). Decouples rule predicates from the ECAPA exact-0.0 convention."

### D2 — MF7: set the flag at construction + migrate reconciler predicates

Per Q3 adjudication (§5): set `confidence_is_no_signal` at the IdentityClaim construction (reconciler.py:112) — either backend-propagated (Q3a) or construction-chokepoint (Q3b).

Migrate reconciler.py confidence-vs-0.0 predicates:
- 3 `== 0.0` (719/743/798) → `claim.confidence_is_no_signal`
- 2 `!= 0.0` (660/776) → `not claim.confidence_is_no_signal` (Q1)
- 1 `<= 0.0` (628) → `claim.confidence_is_no_signal or claim.confidence < 0.0` OR stay (Q2)

### D3 — MF7: AST invariant `test_no_exact_equality_against_claim_confidence`

New `tests/test_no_exact_equality_against_claim_confidence.py` — AST-walks `core/reconciler.py`; rejects any `ast.Compare` with `claim.confidence` (or `.confidence` on an IdentityClaim-typed name) against a `0.0` literal using `Eq` OR `NotEq` ops (both couple to the exact-0.0 convention). The `<= 0.0` (LtE) at 628 — Q2 adjudicates whether it's allowlisted (documented "no-signal OR anti-correlated" threshold) or also migrated. Self-tests: forward (synthetic `== 0.0` fires) + inverse (flag-based predicate passes).

### D4 — MF8: `SessionSnapshot` 3 fields `list` → `tuple` + `_to_snapshot` conversions

`core/session_state.py` SessionSnapshot fields (110/112/115) typed `tuple`; `_to_snapshot` (144/146/149) converts via `tuple(...)`. Owner `Session` (76/78/81) keeps `list`. Mirrors P0.B1 VoiceEvidence frozen discipline one layer up.

### D5 — MF8: AST invariant `test_session_snapshot_collection_fields_are_immutable`

New `tests/test_session_snapshot_collection_fields_are_immutable.py` — AST-walks `core/session_state.py`; asserts the 3 SessionSnapshot fields (recent_voice_confs, core_memory, recent_attributions) are annotated `tuple`. Behavioral companion: construct a SessionSnapshot, assert `.recent_voice_confs` has no `.append` (is tuple). Self-tests: forward (synthetic `list` annotation fires) + inverse (tuple passes).

### D6 — consumer migration + closure-narrative + CI integration

5 test-site updates (§1.4); production consumers verified safe (Plan v1 confirms 3481/5859). New AST invariant tests auto-included in `fast.yml` default-marker filter. Closure-narrative banked.

---

## §3 Q5 LOCK projection — anchor count estimate

**Initial estimate (Phase 0): 6 anchors** at mid; NARROW band ±15% = [5.1, 6.9]; SLIGHT-DRIFT ±30%; FALSIFICATION ≤4 OR ≥9.

| # | Anchor | Type |
|---|---|---|
| A1 | D1 IdentityClaim field added + frozen preserved | source-inspection on voice_channel.py |
| A2 | D2 flag-setting at construction (reconciler.py:112) per Q3 | source + behavioral (no-signal → flag True; real negative → flag False) |
| A3 | D2 reconciler predicate migration (3 `==` + 2 `!=` + 1 `<=` per Q1/Q2) | source-inspection + behavioral (the canary-2026-04-29 negative-cosine regression guard still fires) |
| A4 | D3 AST invariant `test_no_exact_equality_against_claim_confidence` | structural AST + self-tests |
| A5 | D4 SessionSnapshot tuple + `_to_snapshot` | source + behavioral immutability (snapshot field has no .append) |
| A6 | D5 AST invariant `test_session_snapshot_collection_fields_are_immutable` | structural AST + self-tests |

**Total = 6 logical anchors. NARROW band [5.1, 6.9]. Q5 LOCK = 6** (subject to Q5 auditor adjudication — A2+A3 could merge into a single MF7-migration anchor → 5; or A3 could split by comparison-shape → 7).

**Collection fan-out projection (per Bundle 3 Q4 + Bundle 4 lesson — explicitly account for AST detector parametrize)**: A3 + A4 + A5 + A6 self-tests + the reconciler-migration parametrize ≈ 15-20 collections (single-file scope invariants; not STANDARD-scope like Bundle 3's 67-file fan-out).

**Phase 4 strengthening caveat** (Bundle 1-4 pattern): if Phase 4 surfaces a detector gap requiring same-cycle strengthening → 11th `### Induction-surfaces-invariant-gaps` family event.

---

## §4 Cross-spec impact

### §4.1 File-impact table (Phase 0 estimate; Plan v1 refines via Pass-2 grep + ARITHMETIC SUM-AGAINST-TOTAL)

| D | New files | Modified files | Approx scope |
|---|---|---|---|
| D1 | — | `core/voice_channel.py` (1 field + docstring) | ~8 line edits |
| D2 | — | `core/reconciler.py` (1 construction-site flag + 6 predicate migrations) + possibly `core/voice.py` + pipeline.py (Q3a backend-propagation path) | ~10-20 line edits (Q3-dependent) |
| D3 | `tests/test_no_exact_equality_against_claim_confidence.py` (NEW) | — | 1 test file + AST detector + self-tests |
| D4 | — | `core/session_state.py` (3 SessionSnapshot field types + 3 `_to_snapshot` conversions) | ~6 line edits |
| D5 | `tests/test_session_snapshot_collection_fields_are_immutable.py` (NEW) | — | 1 test file + AST detector + self-tests |
| D6 | — | 5 test-site updates (test_pipeline.py:8138 + test_session_store.py:260/403/435/532) | ~5 line edits |

**Total scope estimate**: 2 new test files + ~35-45 line-level edits across 3-5 production files (voice_channel.py + reconciler.py + session_state.py, plus voice.py + pipeline.py if Q3a) + 5 test-site updates. Q3 adjudication materially affects the production-file count (Q3a = 5 files; Q3b = 3 files).

### §4.2 No Bundle-6 dependency — Bundle 5 is the FINAL Pre-P1 must-fix bundle

Per CEO synthesis, Bundle 5 closes the Pre-P1 must-fix arc. After Bundle 5, the next major work is the **P1 cycle** (8-10 week strategic clock; 5 parallel tracks: P1.A architecture + P1.E embodied runtime + P1.S SDK + P1.M MCP server + P1.R TurtleBot4 reference). MF7's IdentityClaim contract tightening is itself the Pre-P1 form of P1.B1 (IdentityClaim contract tightening per techanalyst1 §332); MF8 is the Pre-P1 form of P1.B2 (SessionSnapshot tuple migration §333).

### §4.3 Bundle 5.X candidates filed at Phase 0

- **Bundle 5.X — backend-sets-the-flag** (if Q3b construction-chokepoint chosen for Bundle 5): push `confidence_is_no_signal` into `voice.identify`'s return when P1 multi-platform adapters land (the TRUE decoupling). Folds into P1.B1 / the adapter SDK work. Filed; user-trigger / P1-gated.
- **Bundle 5.Y — debug-field pruning** (B-L2): `voice_reasoning` + `voice_raw_segment_scores` are debug fields written into IdentityClaim but never consumed by any rule (techanalyst1 B-L2 §224). Out of MF7 scope; file separately.

---

## §5 Auditor pre-emption + RATIFICATION QUESTIONS

### Q1 — MF7 scope: do the 2 `!= 0.0` sites (660, 776) migrate too?

**Finding**: CEO MF7 §257 named only the 3 `== 0.0` sites. Grep found 2 `!= 0.0` sites (660 `_p4_new_stranger_low_match`, 776 `ambient first entry`) that are the LOGICAL INVERSE — "has real signal (positive OR negative)". A future backend returning 0.01 for embedding-failure would make `!= 0.0` treat failure as signal — the SAME backend-coupling MF7 fixes for `== 0.0`. For the AST invariant `test_no_exact_equality_against_claim_confidence` to be coherent (it bans exact-equality against claim.confidence), it should ban BOTH `==` and `!=`.

**Options**: (a) IN-SCOPE — migrate `!= 0.0` (660/776) → `not claim.confidence_is_no_signal`; AST invariant bans both `Eq` and `NotEq`. (b) Narrow — only `== 0.0` (3 sites); AST invariant bans only `Eq`; `!= 0.0` stays backend-coupled (Bundle 5.Z follow-up).

**Architect lean: (a).** A backend-decoupling that leaves the logical inverse coupled is incomplete; the `!= 0.0` sites have identical failure mode. The AST invariant banning both `==` and `!=` is the coherent contract.

### Q2 — MF7: the `<= 0.0` site (628) — migrate or allowlist?

**Finding**: reconciler.py:628 `claim.confidence <= 0.0` is the 2026-04-29 Lexi-misattribution fix (documented at 614-619). Its semantic is "no-signal (exactly 0.0) OR anti-correlated (negative)" — DELIBERATELY broader than `== 0.0`. Migrating to just `confidence_is_no_signal` would BREAK it (miss the negative case that the comment + canary regression specifically guard).

**Options**: (a) Migrate to `claim.confidence_is_no_signal or claim.confidence < 0.0` — decouples the no-signal half from the exact-0.0 convention while preserving the anti-correlated half. AST invariant allows `< 0.0` (a genuine threshold, not exact-equality). (b) Allowlist 628 as-is (`<= 0.0` is a threshold comparison, not exact-equality; the AST invariant only bans `== 0.0`/`!= 0.0`) + keep the existing 614-619 comment. (c) Migrate to a richer predicate the IdentityClaim exposes (e.g., a `confidence_is_anti_correlated` companion flag) — over-engineering for Pre-P1.

**Architect lean: (a).** Decoupling the no-signal half (`confidence_is_no_signal`) while keeping the explicit `< 0.0` for anti-correlation preserves the documented semantic AND advances the decoupling. The AST invariant treats `< 0.0` (LtE/Lt threshold) as allowed, banning only exact `== 0.0`/`!= 0.0`.

### Q3 — MF7 flag-setting architecture: backend-sets vs construction-chokepoint

**Finding**: `voice.identify` returns `(pid, score)` 2-tuple; the no-signal sentinel is `return None, 0.0` (line 430). IdentityClaim is constructed at reconciler.py:112 from `v_score`. The flag must be set somewhere on the chain voice.identify → pipeline.py → `_build_routing_inputs` → construction.

**Options**:
- **(a) Backend-sets (TRUE decoupling, CEO's stated intent)**: `voice.identify` returns `(pid, score, is_no_signal)`; thread through `_IdentifyFn` alias + all callers + pipeline.py + `_build_routing_inputs` new kwarg. Achieves genuine backend-independence but exceeds the CEO's 0.5d (return-signature change + all callers + tests).
- **(b) Construction-chokepoint (0.5d)**: `_build_routing_inputs` sets `confidence_is_no_signal=(v_score == 0.0)` at reconciler.py:112. The convention lives in ONE place; the 6 rule predicates stop referencing 0.0. A future backend swap changes ONE line (construction) instead of six. But the exact-0.0 convention is still assumed at that one line.
- **(c) Hybrid**: (b) now (Bundle 5) + Bundle 5.X / P1.B1 follow-up to push the flag into the backend when multi-platform adapters land.

**Architect lean: (c).** (b)'s construction-chokepoint achieves the PRIMARY MF7 goal (rules no longer reference 0.0; the convention is no longer scattered across 6 predicates) at 0.5d. The full backend-sets decoupling (a) is genuinely valuable but is naturally P1.B1 / adapter-SDK work (when the SECOND backend actually exists). Bundle 5 ships (b) + files Bundle 5.X for (a). This matches the CEO's 0.5d estimate AND the "decouple the rules from the convention" intent, deferring the backend-return-signature change to when it's load-bearing (a 2nd backend).

### Q4 — MF8: production consumers 3481/5859 (`core_memory=` kwarg) — read-only confirmed?

**Finding**: pipeline.py:3481 + 5859 pass `core_memory=snap.core_memory` (now tuple) to a brain context-builder. Grep-verified 2247 (read-only) + 8331 (already list()) are safe. 3481/5859 pass the tuple to a consumer that almost certainly renders it read-only into a prompt.

**Architect lean**: low risk; Plan v1 grep-verifies the consumer signatures (render_session_stable_prefix / get_context) treat `core_memory` read-only. If any consumer does list-specific mutation, Plan v1 adds an explicit `list(...)` at the call site. **Auditor: ratify deferring this to Plan v1 §1 Pass-2 grep verification.**

### Q5 — anchor count: 6 mid? OR auditor sees different decomposition?

Per `### Phase-0-granular-decomposition-enables-accurate-estimates`: auditor independent enumeration may merge A2+A3 (MF7 flag-set + predicate-migration = one contract) → 5, or split A3 by comparison-shape → 7. Auditor's lean requested.

### Q6 — OPTIONAL-Plan-v2 path eligibility

Bundle 4 broke the 3-consecutive-blocked-bundle streak (clean Plan v1, OPTIONAL-Plan-v2 activated, 20th proof case LOCKED). **Bundle 5 has a RICHER Phase 0 finding surface than Bundle 4**: a wrong-FILE premise (IdentityClaim location), a 3→6 scope refinement (3 comparison shapes), LINE-REF-DRIFT, AND a genuine flag-propagation architecture decision (Q3). These are Phase-0-caught (resolved at Phase 0 / Plan v1), not Plan-v1-review surprises — so OPTIONAL-Plan-v2 is still POSSIBLE if Plan v1 absorbs them cleanly. But the Q1/Q2/Q3 architectural decisions are more substantive than Bundle 4's, raising Plan-v2-escalation probability.

**Architect's read**: if Plan v1 clears 0 PIs → OPTIONAL-Plan-v2 holds (2nd consecutive clean Pre-P1 bundle; `Multi-axis-precision-pattern` STAYS at 2 + matures-without-elevation). If Plan v1 surfaces PIs → 4-artifact cycle + `Multi-axis-precision-pattern` 3rd instance CONFIRMS → SUB-RULE ELEVATION EVENT LOCKS at Bundle 5 closure. **Auditor: conditional approval subject to Plan v1 outcome.** Either outcome is a locked architectural narrative event (mirrors Bundle 4's framing).

---

## §6 Procedural commitments (Phase 0 → Plan v1 transition)

1. **Plan v1 §1 locks exhaustive per-site classification** of all 6 confidence-vs-0.0 reconciler sites (3 `==` + 2 `!=` + 1 `<=`) with per-site disposition per Q1/Q2, + the IdentityClaim construction site flag-setting per Q3, + the 6 SessionSnapshot/`_to_snapshot` MF8 sites + 4 production consumers + 5 test-site updates.
2. **Plan v1 §0 NEW commitment**: developer Pass-3 grep at Phase 4 pre-implementation verifies both file-count consistency AND semantic-correctness (the `!=`/`<=` migrations preserve rule behavior; the canary-2026-04-29 negative-cosine regression still fires; SessionSnapshot consumers don't mutate the now-tuple fields).
3. **Plan v1 §5.4 Multi-discipline preventive convergence enumeration** preserved per `### Multi-discipline-preventive-convergence` numbered doctrine (trajectory at 11-floor; Bundle 5 target ≥11).
4. **4-part Pass-2 grep operational rule** applied at Plan v1 §1 (symbol-name + behavioral-semantic + symmetric + ARITHMETIC SUM-AGAINST-TOTAL — Bundle 5 = candidate 3rd instance for formalization).
5. **Closure-audit verdict forwarding** to auditor before declaring Bundle 5 CLOSED (10th-cycle routinization).

---

## §7 Standing by for auditor Phase 0 verdict

Phase 0 grep-baseline locked. **MF7 surface: IdentityClaim in `core/voice_channel.py:56-81` (NOT reconciler_state.py — wrong-file premise) + 6 confidence-vs-0.0 sites across 3 shapes (NOT 3 — scope refinement) at lines 628/660/719/743/776/798 (NOT 715/739/794 — LINE-REF-DRIFT +4) + flag-propagation architecture decision (Q3). MF8 surface: 3 SessionSnapshot fields + 3 `_to_snapshot` conversions + 4 production consumers (all safe) + 5 test-site updates.** All independently grep-verified at architect Pass-1 2026-05-29.

6 RATIFICATION QUESTIONS surfaced (Q1-Q6) with architect leans. Three are genuine architectural decisions (Q1 `!=` scope, Q2 `<=` disposition, Q3 flag-propagation) that materially affect the migration shape + file count.

If auditor returns CLEAN (0 PIs) → proceed to Plan v1 with locked Q1-Q6 ratifications. OPTIONAL-Plan-v2 candidacy gated at Plan v1 review.

If auditor returns with PIs → Plan v1 absorbs at architect-side.

**Doctrine instances this verdict may bank** (auditor adjudicates):
- `### Phase-0-catches-wrong-premise` 13 → 14 (IdentityClaim wrong-file premise — sub-pattern A: pre-audit mental model named wrong surface `core/reconciler_state.py`)
- `Pre-audit-quantifier-precision-refined-by-grep` SURFACE-CASCADE-AXIS 11 → 12 (3-sites → 6-sites scope refinement)
- LINE-REF-DRIFT sub-shape (715/739/794 → 719/743/798)

---

**Filed**: 2026-05-29
**Architect**: Claude
**Forwarded to**: Auditor (external)
**Predecessor**: Pre-P1 Bundle 4 CLOSED 2026-05-28 (3-artifact OPTIONAL-Plan-v2 cycle; 20th proof case LOCKED; BIDIRECTIONAL-VALIDATION 4-way matrix completed; 11 numbered doctrines)
