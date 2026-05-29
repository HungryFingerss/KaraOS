# Pre-P1 Bundle 5 — Contract Typing (MF7 + MF8) — DEVELOPER HANDOFF (2026-05-29)

**Status**: Plan v3 RATIFIED CLEAN (auditor verdict `info.md` 2026-05-29). Ships to Phase 4 implementation.
**Cycle**: 5-artifact (Phase 0 + Plan v1 + Plan v2 + Plan v3 + closure). FINAL Pre-P1 must-fix bundle.
**Authoritative artifacts**: Phase 0 audit + Plan v1 + Plan v2 + Plan v3 (this handoff consolidates the RATIFIED contract; where any detail conflicts, Plan v3 §2 "RATIFIED carries forward" + Plan v2 §1-§2 govern).
**Q5 LOCK = 7 anchors (A1-A7)**. NARROW band [5.95, 8.05].

---

## 0. The two surface classes (READ FIRST — this is the bundle's core discipline)

| Surface | Discipline | Why |
|---|---|---|
| **HARD-BREAK** — the 3 production `voice.identify` callers | **Exhaustively enumerated below; implement ALL 3 exactly.** A missed caller ships silent `ValueError` to users. | Closure-audit confirms all 3 landed. |
| **SELF-CORRECTING** — the ≥17 test-fakes | **Run the Pass-3 grep sweep + let the green suite be the proof.** A missed 2-tuple stub fails LOUD at test time. | Closure-audit confirms green suite — NOT a re-counted enumeration. |

`### Developer-Pass-3-grep-at-Phase-4-pre-implementation` is **load-bearing for Bundle 5** (first catching-layer assignment after Bundle 4's preventive-mode instance). Run the grep sweep BEFORE editing; it IS the test-fake migration mechanism.

---

## 1. MF7 — `IdentityClaim.confidence_is_no_signal` (backend-sets decoupling)

### D1 — Add the field (`core/voice_channel.py:56-81`)

Add as the 7th field (trailing default — positionally safe in all existing constructions):
```python
confidence_is_no_signal: bool = False
```
Preserve `@dataclass(frozen=True)`. Docstring: *"True iff the voice-ID backend reported NO usable signal (embedding computation failed OR empty gallery — `core/voice.py::identify` returns exactly 0.0 only in these cases). Distinct from a negative `confidence` (anti-correlated real signal) or a sub-threshold positive (gallery miss with real signal). Decouples reconciler rule predicates from the ECAPA exact-0.0 convention."*

### D2a — `voice.identify` 3-tuple return (`core/voice.py`) + alias (`core/voice_channel.py:88`)

Return signature `tuple[str | None, float]` → `tuple[str | None, float, bool]`:
- Line 430 `return None, 0.0` → `return None, 0.0, True` (embedding failed OR empty gallery = no-signal)
- Line 440 `return best_id, best_score` → `return best_id, best_score, False` (real match)
- Line 441 `return None, best_score` → `return None, best_score, False` (gallery miss, real cosine — has signal)

`core/voice_channel.py:88`: `_IdentifyFn = Callable[..., tuple[Optional[str], float]]` → `Callable[..., tuple[Optional[str], float, bool]]`.

Update `identify`'s docstring: *"Returns `(person_id, cosine_score, is_no_signal)`. `is_no_signal=True` ONLY when the embedding failed or the gallery was empty (score forced to 0.0); `False` for both real matches and gallery-misses (score is a genuine cosine, possibly negative)."*

### D2b — `identify_speaker` 5-site flag-setting (`core/voice_channel.py`)

- **162** (audio None), **171** (empty gallery), **183** (diarize-fail), **200** (identify-fail): add `confidence_is_no_signal=True` to each `IdentityClaim(...)` (no-signal by construction)
- **196-198**: `pid, score = await _maybe_run_in_executor(identify_fn, ...)` → `pid, score, is_no_signal = await _maybe_run_in_executor(identify_fn, ...)` (unpack the 3-tuple)
- **217** (success path): add `confidence_is_no_signal=is_no_signal` (from the unpacked 3-tuple)

### D2c — reconciler kwarg + **3-caller** propagation (HARD-BREAK — all 3 mandatory)

`core/reconciler.py:112` `_build_routing_inputs`: add keyword-only param `v_score_is_no_signal: bool = False`; set `confidence_is_no_signal=v_score_is_no_signal` at the IdentityClaim construction.

The 3 production callers (grep-verified exhaustive — implement ALL):
- **`pipeline.py:2439`** (`_accumulate_voice`): `v_pid, v_score = await voice_mod.identify(` → `v_pid, v_score, _ = await voice_mod.identify(` (standalone; no flag needed)
- **`pipeline.py:7539`** (voice-first ambient): `v_pid, v_score = await voice_mod.identify(` → `v_pid, v_score, _ = await voice_mod.identify(` (standalone)
- **`pipeline.py:7804`** (per-turn → reconciler): `_v_pid, _v_score = await voice_mod.identify(` → `_v_pid, _v_score, _v_is_no_signal = await voice_mod.identify(` + pass `v_score_is_no_signal=_v_is_no_signal` to the `_build_routing_inputs(...)` call

### D2d — event-log decoder one-liner (`core/event_log/types.py:124`)

`_identity_claim_from_dict`: add `confidence_is_no_signal=bool(d.get("confidence_is_no_signal", False))`. **Encoder needs NO change** — `core/event_log/producer.py::_event_log_default` uses `dataclasses.asdict` (lines 100/117), so the new field serializes automatically.

### D2e — reconciler 6-predicate migration (`core/reconciler.py`)

| Line | From | To |
|---|---|---|
| 719 | `claim.confidence == 0.0` | `claim.confidence_is_no_signal` |
| 743 | `claim.confidence == 0.0` | `claim.confidence_is_no_signal` |
| 798 | `claim.confidence == 0.0` | `claim.confidence_is_no_signal` |
| 660 | `claim.confidence != 0.0` | `not claim.confidence_is_no_signal` |
| 776 | `claim.confidence != 0.0` | `not claim.confidence_is_no_signal` |
| 628 | `claim.confidence <= 0.0` | `claim.confidence_is_no_signal or claim.confidence < 0.0` |

**628 is load-bearing** — the `or claim.confidence < 0.0` half preserves the Session-119 anti-correlation fix (canary-2026-04-29 negative-cosine regression). Do NOT drop it. The comment block at reconciler.py:614-619 stays (update it to reference the flag).

### D3 — MF7 AST invariant (NEW `tests/test_no_exact_equality_against_claim_confidence.py`)

AST-walk `core/reconciler.py`; reject any `ast.Compare` against a `0.0` literal where the operand is `claim.confidence` (`.confidence` attribute access) using `ast.Eq` **OR** `ast.NotEq` (both couple to the exact-0.0 convention). **ALLOW** `ast.Lt`/`ast.LtE`/`ast.Gt`/`ast.GtE` (the 628 `< 0.0` + the many `< threshold` rule predicates are genuine thresholds). Self-tests: forward (synthetic `== 0.0` AND synthetic `!= 0.0` both fire) + inverse (flag-based predicate + `< 0.0` threshold both pass).

---

## 2. MF8 — `SessionSnapshot` list → tuple

### D4 — SessionSnapshot tuple + `_to_snapshot` (`core/session_state.py`)

- SessionSnapshot fields **110** (recent_voice_confs) / **112** (core_memory) / **115** (recent_attributions): `list` → `tuple`
- `_to_snapshot` conversions **144/146/149**: `list(s.X)` → `tuple(s.X)`
- Owner `Session` fields **76/78/81**: STAY `list` (owner keeps mutable; only the frozen snapshot becomes tuple)

### D5 — MF8 AST invariant (NEW `tests/test_session_snapshot_collection_fields_are_immutable.py`)

AST-assert the 3 SessionSnapshot fields annotated `tuple` + behavioral (constructed snapshot field has no `.append`). Self-tests: forward (synthetic `list` annotation fires) + inverse (tuple passes).

---

## 3. D6 — test-fake migration (SELF-CORRECTING — grep sweep + ValueError backstop)

**Mechanism (NOT exhaustive Plan-stage enumeration — run the sweep yourself):**
1. **Pass-3 grep sweep** at Phase 4 pre-implementation: `\.identify\s*=` + `patch\([^)]*identify` + `identify_fn=` across `test_pipeline.py` (root) + `tests/` + any root `test_*.py`. Inspect each for a non-3-tuple return; convert to 3-tuple (`(None, 0.0, True)` for no-signal stubs; `(pid, score, False)` for match/gallery-miss).
2. **Green full-suite run** = the completeness proof. Any invoked-but-unmigrated 2-tuple stub raises `ValueError: too many values to unpack` — fix it.

**≥17 known floor** (seed your sweep; an 18th surfacing is the mechanism working, not a miss):
- *test_pipeline.py (9)*: 35, 6500, 6604, 6640, 6683, 6722, 6763, 8246, 8295
- *global `_voice_stub`/`_vs` stubs (6)*: conftest.py:57, test_dispute_auto_clear.py:29, test_multispeaker_integration.py:39, test_user_text_gate_multiword.py:32, test_brain_agent.py:6993, tests/test_user_text_gate_invariants.py:96
- *`identify_fn`-injected (2)*: test_event_log_producer_coverage.py:160 (lambda — add `, False`), test_voice_channel.py:56 (`_fake_identify_factory` — add optional `is_no_signal: bool = False` param; inner `_f` returns `(pid, score, is_no_signal)`)

**MF8 test updates (5 — bounded, do all):**
- test_pipeline.py:8138 `isinstance(snap.recent_attributions, list)` → `tuple`
- test_session_store.py:260 `snap.recent_voice_confs == [0.9, 0.85]` → `== (0.9, 0.85)`
- test_session_store.py:403 `snap.recent_attributions == ["face", "voice"]` → tuple
- test_session_store.py:435 `snap.core_memory == mem` → tuple
- test_session_store.py:532 `snap.recent_voice_confs == [0.9]` → `== (0.9,)`

**Ripple verify (1):** test_p0_r6_y_ecapa_worker.py:311 (`test_p0_r6_y_d3_anchor_4_site_7148_uses_await_voice_mod_identify`) — source-inspection asserting `await voice_mod.identify(` is present. The await pattern survives D2a (only arity changes). Verify it doesn't assert a 2-tuple unpack shape; if it does, update.

---

## 4. Anchors (Q5 = 7) + deliberate-regression confirmations

Per `### Induction-surfaces-invariant-gaps`: ship each anchor with a deliberate-regression check — induce the violation, confirm the test fires, revert, document the outcome. If induction surfaces a detector gap, strengthen the detector in the same cycle (would be the 11th in-cycle `### Induction-surfaces-invariant-gaps` family event).

| # | Anchor | Verifies | Regression check |
|---|---|---|---|
| A1 | D1 field added + frozen preserved | voice_channel.py source | remove field → A1 fires |
| A2 | D2a 3-tuple return + alias | voice.py 430/440/441 return True/False/False; alias is 3-tuple | revert 430 to 2-tuple → A2 fires |
| A3 | D2b identify_speaker 5-site + success-path flag | 4 no-signal-by-construction → flag True; success-path → flag from unpack; **test_voice_channel.py:187 no-signal case asserts flag** | drop `confidence_is_no_signal=True` at 162 → A3 fires |
| A4 | D2c+D2e reconciler construction kwarg + 6-predicate migration + **Session-119 canary regression** | 6 predicates use flag/`< 0.0`; 628 still fires on negative cosine | revert one predicate to `== 0.0` → A4 (or A6) fires; revert 628 to drop `< 0.0` → Session-119 canary fires |
| A5 | D2d event-log round-trip | serialize IdentityClaim(confidence_is_no_signal=True) → JSON → `_identity_claim_from_dict` → flag preserved | drop decoder line → A5 fires (flag lost on round-trip) |
| A6 | D3 MF7 AST invariant + self-tests | bans `==`/`!=` against claim.confidence, allows `<`/`<=` | (self-tests are the regression checks) |
| A7 | D4+D5 MF8 tuple + AST invariant + self-tests | SessionSnapshot 3 fields tuple + immutable; _to_snapshot tuple() | revert a field to `list` → A7 fires |

---

## 5. Closure gates (binding — auditor §3)

Closure-audit (architect) + ratification (auditor) require:
1. **Green full suite** — the completeness proof for the SELF-CORRECTING test-fake surface (NOT a re-counted enumeration)
2. **All 3 production callers landed** (2439 `, _=` / 7539 `, _=` / 7804 unpack+propagate) — the HARD-BREAK surface
3. **6-predicate migration** (3 `==`→flag, 2 `!=`→`not flag`, 1 `<=`→`flag or <0`)
4. **Session-119 canary** (negative-cosine regression still fires at 628)
5. **MF8 tuple** (SessionSnapshot 3 fields + _to_snapshot + 5 test updates)
6. **7/7 anchors A1-A7 GREEN** + 7/7 deliberate-regression confirmations passed
7. **§0 NEW dual-axis Pass-3 grep report** (file-count + semantic-correctness) at Phase 4 pre-implementation

---

## 6. Scope guards (do NOT do)

- Do NOT chase an exhaustive test-fake count beyond running the grep sweep + green suite (the 8→15→17 recursion proved that's the wrong goal for this surface).
- Do NOT change the encoder (`_event_log_default` is asdict-automatic).
- Do NOT touch owner `Session` fields (76/78/81 stay `list`).
- Do NOT drop the `< 0.0` half of the 628 migration (Session-119 load-bearing).
- Do NOT add a 2nd backend / multi-platform adapter (that's P1.B1; Bundle 5.X was withdrawn — Q3(a) ships the backend-sets decoupling here).
- Bundle 5.Y (debug-field pruning of `voice_reasoning`/`voice_raw_segment_scores`) is OUT OF SCOPE — file separately if pursued.

---

## 7. Doctrine bumps to bank at closure (architect closure-audit applies to CLAUDE.md)

- `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` 12 → **13** CAUGHT-REAL-GAP (fired 3× in-bundle; reinforcing within the 13th, no inflation)
- `Plan-v1-Pass-2-grep-undercount` 16 → **17**
- `Multi-axis-precision-pattern-across-Pre-P1-bundles` 2 → **3** ELEVATION + RENAME (drop falsified "3-consecutive"; finalize rename in CLAUDE.md)
- NEW `Self-correcting-surface-resists-exhaustive-pre-enumeration` observation → both memory paths (cross-path discipline)
- `### Phase-0-catches-wrong-premise` STAYS 13 · `Pre-audit-quantifier` STAYS 12 · OPTIONAL-Plan-v2 STAYS 20 · BIDIRECTIONAL STAYS 5 · Q5 = 7
- Per-artifact counts at closure: strict-mode 131, spec-first 140, grep-baseline 98, cross-cycle 101, spec-time 108
- `### Multi-discipline-preventive-convergence` 11-floor preserved (12th surface-class-delegation flagged as lesson-from-PI, not preventive-applied)
- `### Architect-reads-production-code-before-sign-off` 34 → 35 (closure-audit Path C grep-verify)
- `### Twin-filename-pitfall-prevention` 35 → 36 · Auditor-Q5-estimates-trail-grep 40 → 41 (if Q5 in band) · Deferred-canary 37 → 38
- **FINAL Pre-P1 must-fix bundle** — on closure, all 5 bundles complete; project moves to P1 cycle.

---

**Standing by**: developer implements Phase 4 → reports → architect closure-audit (Path C grep-verify: green suite + 3 callers + 6-predicate + Session-119 canary + MF8 tuple + 7 anchors) → forward closure-audit to auditor for ratification → CLOSED.

**Architect**: Claude · **Filed**: 2026-05-29
