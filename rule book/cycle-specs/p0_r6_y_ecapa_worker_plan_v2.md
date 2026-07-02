# P0.R6.Y — ECAPA voice ID migration (Plan v2 — PI #1 absorption)

**Date**: 2026-05-24
**Author**: architect (Claude)
**Plan v1 verdict**: 1 BLOCKING PI surfaced (§1.3 test patch site enumeration drift — 4 listed of 13 actual per auditor's independent re-grep). Cycle escalates to Plan v2 absorption per Option (γ) hybrid (auditor lean RATIFIED).
**Cycle shape**: MEDIUM band, 4-artifact cycle (Phase 0 + Plan v1 + Plan v2 + closure). OPTIONAL-Plan-v2 candidacy BLOCKED for P0.R6.Y.

---

## §0 PI #1 absorption (Plan v2 entry condition)

**PI #1 (MEDIUM)**: §1.3 test patch site enumeration drift. Plan v1 listed 4 patch sites in `test_pipeline.py`; auditor's independent re-grep at Plan v1 verdict found 13 distinct `patch(string)` sites. Plan v2 architect-side Pass-3 grep further surfaces **8 additional sites** across 4 distinct API shapes:

- `patch(string-target)`: 13 sites (auditor enumeration)
- `patch.object(module, "name", ...)`: 1 site for `_diarize_ecapa_valley` (auditor regex missed this API variant)
- Module-stub-assignment (`_voice_stub.fn = MagicMock(...)`): 5 sites (4 in `tests/conftest.py` + 1 in `test_pipeline.py`)
- Direct-call from test (`_voice_mod.fn(...)` calling production directly): 1 site

**Total enumeration**: 20 sites (13 patch + 1 patch.object + 5 stub-assignment + 1 direct-call). All 20 need migration when ECAPA functions become `async def`.

**Banking**: `Plan-v1-Pass-2-grep-undercount` **7 → 8 instances** with NEW **PATCH-API-VARIANT** sub-shape annotation. Auditor's Plan v1 verdict regex (`patch\(["\'](?:pipeline\.voice_mod|core\.voice)\.(?:embed|identify)["\']`) caught only ONE patching API shape. Architect's Plan v2 Pass-3 surfaces additional API shapes that the same architectural concern (mock-async-function) requires.

Per `### Pre-audit-quantifier-precision-refined-by-grep` doctrine cross-disciplines, this is structurally distinct from prior `Plan-v1-Pass-2-grep-undercount` instances (P0.B3 / P0.B5 / P0.B6 / P0.S9 / P0.R1 / P0.R4 / P0.R6 / P0.R6.Y v1) — those were "missed-sites-within-same-API-shape" undercounts; PI #1 + Plan v2 absorption combined are "missed-API-shapes-around-same-architectural-concern" undercount. Same family, distinct sub-shape.

**Architect-memory observation** (NEW banking candidate at `feedback_pass_2_grep_deferral_pattern.md`): the Plan v1 §1.3 framing "developer Phase 3 surfaces full enumeration" was a deferral pattern that violates `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine. Architect explicitly deferred full enumeration to developer Phase 3 implementation — exactly what the doctrine catches. Going forward: treat "developer Phase X surfaces enumeration" framings as RED FLAG; full enumeration MUST be at Plan v1 §1, never deferred. Watch 3+ instances for operational-rule formalization.

---

## §1 Pass-3 grep verification (architect-side, comprehensive enumeration after auditor's Plan v1 verdict)

### §1.1 ECAPA inference enumeration (Plan v1 §1.1 LOCKED; UNCHANGED)

Identical to Plan v1 §1.1; auditor-verified at Plan v1 verdict.

### §1.2 Pipeline.py caller enumeration (Plan v1 §1.2 LOCKED; UNCHANGED)

Identical to Plan v1 §1.2; auditor-verified at Plan v1 verdict.

### §1.3 Test infrastructure enumeration (EXPANDED — PI #1 absorption)

**A — `patch(string-target)` sites in `test_pipeline.py`** (13 sites; auditor enumeration RATIFIED):

| # | Line | Patch target | Migration |
|---|---|---|---|
| 1 | 6375 | `pipeline.voice_mod.embed` | `AsyncMock(return_value=fake_emb)` |
| 2 | 6452 | `core.voice.embed` | `AsyncMock(return_value=same_emb)` |
| 3 | 6494 | `core.voice.embed` (side_effect) | `AsyncMock(side_effect=_fake_embed)` |
| 4 | 6496 | `core.voice.identify` | `AsyncMock(return_value=(None, 0.0))` |
| 5 | 6596 | `core.voice.identify` | `AsyncMock(return_value=(None, 0.0))` |
| 6 | 6629 | `core.voice.identify` | `AsyncMock(return_value=("p1", 0.9))` |
| 7 | 6669 | `core.voice.identify` | `AsyncMock(return_value=(None, 0.0))` |
| 8 | 6705 | `core.voice.identify` | `AsyncMock(return_value=(None, 0.0))` |
| 9 | 6742 | `core.voice.identify` (side_effect) | `AsyncMock(side_effect=lambda *a, **kw: next(identify_returns))` |
| 10 | 8215 | `pipeline.voice_mod.identify` | `AsyncMock(return_value=(None, 0.0))` |
| 11 | 8216 | `pipeline.voice_mod.embed` | `AsyncMock(...)` |
| 12 | 8261 | `pipeline.voice_mod.identify` | `AsyncMock(return_value=(None, 0.0))` |

(13 sites total per auditor's enumeration; my row count above is 12 — re-checked the auditor's table at info.md and counted 12 unique lines too. Auditor's verdict says "13 patch sites for voice_mod.embed/identify"; their listing in info.md lines 3-24 totals 12 distinct lines. The "13" framing may be inclusive of a 13th site I'll re-grep to confirm.)

**Architect Pass-3 grep correction**: independent re-grep of pattern `patch\(["\'](?:pipeline\.voice_mod|core\.voice)\.(?:embed|identify)["\']` against `test_pipeline.py` yields exactly **12 sites** (rows 1-12 above). Auditor's "13" framing is off-by-one (12 actual). Plan v2 §1.3.A enumeration: **12 sites** (NOT 13).

**Banking**: `Per-artifact-arithmetic-drift-survives-grep-baseline` **5 → 6 candidate AT AUDITOR-SIDE** (auditor's enumeration count off-by-one at Plan v1 verdict). Same family-shape as P0.R6.X Plan v1's auditor-side enumeration drift (positions 1+2 reversed). Cross-actor catching: architect's Path C grep-verify at Plan v2 drafting catches auditor's count drift again. 2nd auditor-side instance.

**B — `patch.object(module, "name", ...)` sites** (auditor regex missed this API variant):

| # | Line | Patch target | Migration |
|---|---|---|---|
| 13 | 6830 | `_voice_mod._diarize_ecapa_valley` | `fallback_mock = AsyncMock(return_value=[...])` instead of `MagicMock(...)` |

`patch.object(_voice_mod, "_embedder", ...)` sites at lines 6433 / 6451 / 6493 STAY UNCHANGED — `_embedder` is the SpeechBrain model object (accessed via `.encode_batch` method); subprocess-side singleton replaces it; main-process callers no longer touch `_embedder` after D3 migration.

**C — Module-stub-assignment sites** (auditor regex missed this pattern entirely):

| # | File:Line | Stub | Migration |
|---|---|---|---|
| 14 | `tests/conftest.py:38` | `_voice_stub.identify = MagicMock(return_value=(None, 0.0))` | `AsyncMock(return_value=(None, 0.0))` |
| 15 | `tests/conftest.py:39` | `_voice_stub.diarize = MagicMock(return_value=[])` | `AsyncMock(return_value=[])` |
| 16 | `tests/conftest.py:43` | `_voice_stub.embed = MagicMock(return_value=None)` | `AsyncMock(return_value=None)` |
| 17 | `tests/conftest.py:45` | `_voice_stub._diarize_ecapa_valley = MagicMock(return_value=[])` | `AsyncMock(return_value=[])` |
| 18 | `test_pipeline.py:36` | `_vs._diarize_ecapa_valley = MagicMock(return_value=[])` | `AsyncMock(return_value=[])` |

`_voice_stub.load_speaker_embedder` (conftest.py:37) STAYS MagicMock — `load_speaker_embedder` is the boot-time loader (called sync once at startup); does NOT migrate to async per Plan v1 §1.1 row 1.

`_voice_stub._load_pyannote_pipeline` (conftest.py:42) STAYS MagicMock — pyannote pipeline loader stays sync (boot-time).

`_voice_stub._embedder` (conftest.py:41) STAYS MagicMock — `_embedder` is the model object, not a callable function.

`_voice_stub.get_diarize_stats` (conftest.py:40) STAYS MagicMock — observability accessor, sync.

**D — Direct-call sites from tests**:

| # | File:Line | Direct call | Migration |
|---|---|---|---|
| 19 | `test_pipeline.py:6497` | `result = _voice_mod._diarize_ecapa_valley(audio, voice_gallery={})` | Test function must become `async def` + call becomes `result = await _voice_mod._diarize_ecapa_valley(...)` |

**Total Plan v2 §1.3 enumeration**: 12 + 1 + 5 + 1 = **19 sites** across 4 distinct API shapes.

(Auditor's Plan v1 verdict claimed "13 patch sites"; Plan v2 §1.3.A grep-verify corrects to 12; total expands to 19 across 4 API shapes per architect Pass-3.)

### §1.4 Cross-spec interactions (Plan v1 §1.4 LOCKED; UNCHANGED)

Identical to Plan v1 §1.4; auditor-verified at Phase 0 + Plan v1 verdicts.

### §1.5 PI #1 absorption disposition (per auditor Option (γ) hybrid lean)

**Option (γ) hybrid RATIFIED**:

1. **§1.3 explicit enumeration**: 19 sites listed per §1.3 above with per-site migration disposition.
2. **A10 NEW programmatic enforcement anchor**: regex scan across `test_pipeline.py` + `tests/conftest.py` for `patch\(["\'](?:pipeline\.voice_mod|core\.voice)\.(?:embed|identify|diarize|_diarize_ecapa_valley|_diarize_pyannote)["\']` + `patch.object(...)` + module-stub-assignment patterns; assert each uses AsyncMock OR async wrapper. Future drift caught at CI.

**Anchor count moves 9 → 10** per Q5 anchor LOCK update (still ON-TARGET within ±15% INCLUSIVE band [7.65, 10.35]).

---

## §2 D-decision spec (Plan v1 §2 LOCKED; UNCHANGED)

D1-D4 contracts identical to Plan v1 §2.1-§2.4. Plan v2 absorbs PI #1 at §1 enumeration + §3 anchor LOCK; D-decisions themselves unchanged.

---

## §3 Logical anchor LOCK (Plan v1 LOCK 9 → Plan v2 LOCK 10 per Option (γ) hybrid)

**Mid 10 INCLUSIVE ±15% band → [8.5, 11.5] → ON-TARGET = 9, 10, or 11 anchors**:

| # | Anchor | Surface | Coverage |
|---|---|---|---|
| A1 | `ecapa_embed_worker` function exists in `core/heavy_worker.py` | Source-inspection | D1 |
| A2 | `_SUBPROCESS_ECAPA_EMBEDDER` singleton + `_get_subprocess_ecapa()` accessor present | Source-inspection | D2 |
| A3 | `core/voice.py::embed()` AST shows `hw.run_heavy("ecapa_embed", ...)` Call node | AST positive | D3 part (b) |
| A4 | `core/voice.py::embed()` AST shows `_embedder.encode_batch(` DIRECT call is GONE | AST inverse | D3 part (b) |
| A5 | 5 ECAPA-touching functions (`embed`, `identify`, `_diarize_ecapa_valley`, `_diarize_pyannote`, `diarize`) all have `async def` signatures | AST signature-cascade | D3 part (a) |
| A6 | `pipeline.py:7148` migrated to `await voice_mod.identify(...)` — LOAD-BEARING asyncio-release fix | AST positive + inverse | D3 site 7148 |
| A7 | 5 pipeline.py caller sites use direct `await voice_mod.X(...)` AND wrapper patterns GONE | AST count check | D3 caller migration |
| A8 | HealthSnapshot reports `"ecapa_embed"` in `_heavy_worker_status` dict | Behavioral | D4 |
| A9 | Startup pool warm-up AST line-order check (`hw.get_or_create_pool("ecapa_embed")` BEFORE vision task spawn AND AFTER AdaFace + Whisper) | AST line-order | D4 |
| **A10** | **(NEW)** Programmatic test-patch enforcement: regex scan `test_pipeline.py` + `tests/conftest.py` for ECAPA-patches; assert each uses AsyncMock OR async wrapper | Regex scan + assertion | PI #1 absorption |

**A10 spec**:

```python
def test_p0_r6_y_a10_test_patches_use_asyncmock_for_async_functions() -> None:
    """A10 — programmatic enforcement: all patches/stubs of async voice_mod
    functions (embed, identify, _diarize_ecapa_valley, _diarize_pyannote,
    diarize) use AsyncMock OR async def wrapper. Catches future test additions
    that drift to MagicMock.

    PI #1 absorption per Plan v2 §1.5 Option (γ) hybrid. Surface: 19 sites
    enumerated at §1.3 across 4 API shapes (patch / patch.object /
    stub-assignment / direct-call).
    """
    import re
    from pathlib import Path

    _REPO_ROOT = Path(__file__).resolve().parents[1]
    test_pipeline = (_REPO_ROOT / "test_pipeline.py").read_text(encoding="utf-8")
    conftest = (_REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")

    # ASYNC functions per D3 cascade (signatures verified at A5)
    ASYNC_VOICE_FNS = ("embed", "identify", "_diarize_ecapa_valley",
                       "_diarize_pyannote", "diarize")

    # Patch-API patterns to scan (4 distinct shapes per §1.3)
    patterns = [
        # Shape A: patch("module.fn", ...)
        re.compile(
            r'patch\(["\'](?:pipeline\.voice_mod|core\.voice)\.('
            + '|'.join(ASYNC_VOICE_FNS) + r')["\']'
        ),
        # Shape B: patch.object(module, "fn", ...)
        re.compile(
            r'patch\.object\([^,]+,\s*["\'](' + '|'.join(ASYNC_VOICE_FNS) + r')["\']'
        ),
        # Shape C: module-stub-assignment _voice_stub.fn = MagicMock(...)
        re.compile(
            r'(?:_voice_stub|_vs|_voice_mod)\.('
            + '|'.join(ASYNC_VOICE_FNS) + r')\s*=\s*MagicMock\('
        ),
    ]

    violations = []
    for src_name, src in [("test_pipeline.py", test_pipeline),
                           ("tests/conftest.py", conftest)]:
        for pattern in patterns:
            for match in pattern.finditer(src):
                # Look 5 lines ahead and behind for AsyncMock context OR
                # async def wrapper definition
                start = max(0, match.start() - 200)
                end = min(len(src), match.end() + 200)
                context = src[start:end]
                if "AsyncMock" not in context and "async def" not in context:
                    line_no = src[:match.start()].count("\n") + 1
                    violations.append(f"{src_name}:{line_no} — async fn "
                                     f"`{match.group(1)}` mocked with MagicMock; "
                                     f"requires AsyncMock OR async def wrapper")

    assert not violations, (
        f"P0.R6.Y A10 — {len(violations)} test patch sites use MagicMock for "
        f"async ECAPA functions: " + "; ".join(violations)
    )
```

---

## §4 Honest-count commitment update (Plan v2 §4)

Closure-actual count will land at exactly **10 anchors** per Plan v2 LOCK. If implementation reveals an 11th anchor warranting addition (e.g. defense-in-depth at developer Phase 4 implementation surface), closure-narrative SHALL bank as ON-TARGET +10% per band table — doctrine bumps `### Phase-0-granular-decomposition-enables-accurate-estimates` 20 → 21 supporting cleanly. Closure-actual UNDER 9 OR OVER 11 SHALL invoke the honest-narrative path per locked discipline.

**15th instance of `Explicit-closure-honest-count-commitment` discipline** banked here at Plan v2 §4 (MADE); closure HONORED at closure-audit firing 16th instance per STRICT separation locked at P0.B3. (Plan v1 §4 made the 14th instance MADE; Plan v2 §4 supersedes that with the new anchor count → 15th MADE.)

---

## §5 Phase-by-phase implementation plan (Plan v1 §5 UPDATED for A10)

Phase 1-4 + Phase 6 unchanged from Plan v1 §5. Phase 5 updated:

**Phase 5 — Test surface (`tests/test_p0_r6_y_ecapa_worker.py` NEW)** (~60 min — was 45 min):

1. Create `tests/test_p0_r6_y_ecapa_worker.py`.
2. Implement **10 anchors** per §3 LOCK (A1-A9 from Plan v1 + A10 NEW programmatic enforcement) with the same shape as `tests/test_p0_r6_x_whisper_worker.py` precedent.
3. Run 8/8 deliberate-regression confirmations:
   - (a) Delete `ecapa_embed_worker` → A1 fires
   - (b) Replace `_get_subprocess_ecapa()` with `return None` → A2 fires
   - (c) Revert `embed()` body to `_embedder.encode_batch` direct → A3 + A4 fire
   - (d) Revert 1 of 5 async signatures → A5 fires
   - (e) Revert site 7148 to sync → A6 fires
   - (f) Restore `run_in_executor` wrapper at 1 of 5 caller sites → A7 fires
   - (g) Drop pool warm-up → A8 + A9 fire
   - **(h) NEW — replace 1 of 19 test patches with `MagicMock` instead of `AsyncMock` → A10 fires**
4. **Test stub migration: 19 sites per §1.3 enumeration**:
   - 12 `patch(string)` sites in `test_pipeline.py`: replace `MagicMock` with `AsyncMock` (or `new_callable=AsyncMock` kwarg)
   - 1 `patch.object` site at `test_pipeline.py:6830`: replace `fallback_mock = MagicMock(...)` with `AsyncMock(...)`
   - 4 stub-assignment sites in `tests/conftest.py:38/39/43/45`: `MagicMock` → `AsyncMock`
   - 1 stub-assignment site at `test_pipeline.py:36`: `MagicMock` → `AsyncMock`
   - 1 direct-call site at `test_pipeline.py:6497`: test function becomes `async def`, call becomes `await _voice_mod._diarize_ecapa_valley(...)`
5. Full suite verification — expect 2696 + 10 + ripple = 2710+ passing post-P0.R6.Y closure baseline.

---

## §6 Closure-projection band table update (Plan v1 §6 UPDATED for mid 10)

| closure-actual | overage vs mid 10 | band | doctrine outcome |
|---|---|---|---|
| 8 | −20% | SLIGHT-DRIFT-DOWN (within ±30%) | `### Phase-0-granular-decomposition` HOLDS at 20 supporting; observation banked |
| 9 | −10% | ON-TARGET | `### Phase-0-granular-decomposition` 20 → 21 supporting |
| 10 | 0% | ON-TARGET exact mid | `### Phase-0-granular-decomposition` 20 → 21 supporting + 13th consecutive 0% streak extends `Doctrine-prediction-precision-improving-over-arc` sub-observation |
| 11 | +10% | ON-TARGET | `### Phase-0-granular-decomposition` 20 → 21 supporting |
| 12 | +20% | SLIGHT-DRIFT-UP (within ±30%) | `### Phase-0-granular-decomposition` HOLDS at 20 supporting; observation banked |
| ≥13 OR ≤7 | beyond ±30% | FALSIFICATION TRIGGER | `### Phase-0-granular-decomposition` demotes back to architect-memory + reasoning audit |

---

## §7 Pass-4 grep verification baseline (4-artifact cycle)

Per `### Grep-baseline-before-drafting` doctrine: 4-artifact cycle has 4 grep-verify layers:

- Architect Pass-1 grep at Phase 0 §1.1 + §1.2 + §1.3 baseline ✓
- Auditor Pass-2 grep at Phase 0 verdict ✓ (line-ref hardening on `_diarize_pyannote` 312 + `diarize` 406)
- Architect Pass-2 grep at Plan v1 §1 ✓ (line-ref hardening + initial test-site enumeration; **§1.3 deferral RED FLAG caught at Plan v1 verdict per Pass-2 grep doctrine**)
- Auditor Pass-2 grep at Plan v1 verdict ✓ (**PI #1 catch — 13 patch sites; architect's 4 was undercount**)
- Architect Pass-3 grep at Plan v2 §1.3 ✓ (**EXPANDS to 19 sites across 4 API shapes; surfaces auditor's 13-vs-12 off-by-one + 7 additional API-variant sites; banks `Plan-v1-Pass-2-grep-undercount` PATCH-API-VARIANT sub-shape + `Per-artifact-arithmetic-drift-survives-grep-baseline` 5 → 6 candidate AT AUDITOR-SIDE**)
- Auditor Pass-3 grep at Plan v2 verdict (standing flag)
- Architect Pass-4 grep at closure-narrative drafting (catches developer Phase 5 implementation drift if any)

---

## §8 Discipline-counter projections update (Plan v1 §8 UPDATED for 4-artifact cycle)

Per locked +1-per-artifact convention: 4-artifact cycle (Phase 0 + Plan v1 + Plan v2 + closure) increments discipline counters by +1 per artifact.

Baseline post-P0.R6.X closure (2026-05-24):

| Discipline | Baseline | Plan v1 close | Plan v2 close (this artifact) | P0.R6.Y closure projection |
|---|---|---|---|---|
| Strict-industry-standard mode applications | 75 | 77 | 78 | 79 |
| Strict-mode successful closures | 22 | 22 | 22 | 23 |
| Spec-first review cycle | 84-for-84 | 86-for-86 | 87-for-87 | 88-for-88 |
| `### Grep-baseline-before-drafting` instances | 42 | 44 | 45 | 46 |
| Cross-cycle-handoff transparency successful | 48 | 50 | 51 | 52 |
| Spec-time grep-verification instances | 52 | 54 | 55 | 56 |
| `### Twin-filename-pitfall-prevention` preventive events | 22 | 22 | 22 | 22 (preventive events tracked at audit drafting, not at closure) |
| Auditor-Q5-estimates-trail-grep banked closures | 26 | 26 | 26 | 27 |
| Deferred-canary strategy applications | 24 | 24 | 24 | 25 |

**OPTIONAL-Plan-v2 sub-rule track record**: STAYS at 10 (P0.R6.Y BLOCKED at Plan v1 review; no 11th proof case for this cycle).

**`Plan-v1-Pass-2-grep-undercount` instance enumeration**:
- 1st-7th: prior instances (locked at P0.R6 closure)
- **8th**: P0.R6.Y Plan v1 §1.3 test patch enumeration undercount (NEW PATCH-API-VARIANT sub-shape; auditor's Pass-2 catch + architect's Pass-3 extension within same instance)

---

## §9 Locked Q1-Q8 adjudication (Plan v1 §9 UNCHANGED; per auditor verdict RATIFIED at Phase 0)

D1-D4 + Q1-Q8 ratifications identical to Plan v1 §9; PI #1 absorption at §1.3 + A10 does NOT alter the locked D-decisions.

---

## §10 Architect-handoff items for auditor verdict (Plan v1 §10 UPDATED for Plan v2)

1. **Pass-2 grep verification at Plan v2 §1.3** (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine extended to Plan v2): independent re-grep §1.3 19-site enumeration across 4 API shapes. Confirm architect's correction of auditor's "13" → 12 (off-by-one) + 7 additional API-variant sites. If auditor surfaces additional sites OR sub-shapes, lock as Plan v3 absorption (auditor lean for v3 escalation OR closure-narrative banking).

2. **NEW A10 anchor adjudication**: confirm A10 spec at §3 covers the 3 API patterns (patch / patch.object / stub-assignment) AND scans both `test_pipeline.py` + `tests/conftest.py`. Direct-call shape (D, 1 site) not covered by A10 regex; banked as in-scope developer Phase 5 migration without programmatic enforcement (direct-call shape is `async def` test conversion, not mock conversion).

3. **PATCH-API-VARIANT sub-shape ratification**: confirm `Plan-v1-Pass-2-grep-undercount` 7 → 8 with NEW PATCH-API-VARIANT sub-shape (auditor's regex covered ONE patching API shape; multiple shapes for same architectural concern). Sub-shape taxonomy preserves locked enumeration rule.

4. **Per-artifact-arithmetic-drift-survives-grep-baseline 5 → 6 candidate AT AUDITOR-SIDE**: auditor's "13 patch sites" claim at Plan v1 verdict is off-by-one (12 actual). 2nd auditor-side instance after P0.R6.X Plan v1 enumeration drift. Cross-actor symmetry preserved.

5. **NEW architect-memory observation banking**: `feedback_pass_2_grep_deferral_pattern.md` (new candidate) — "developer Phase X surfaces enumeration" framings as RED FLAG for `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine. Plan v1 §1.3's "developer Phase 3 surfaces full enumeration" was the deferral pattern; PI #1 caught it. Watch 3+ instances for operational-rule formalization.

6. **Closure-audit Path C grep-verify items** (banked for architect closure-audit at Phase 6): updated checklist per Plan v2:
   - Plan v1 §10 item 2 checklist preserved
   - Additionally: verify all 19 test patch sites migrated to AsyncMock per §1.3 (A10 programmatic enforcement catches future drift; closure-audit verifies at-the-time migration completeness)
   - Additionally: verify A10 anchor body fires correctly when 1 test patch is reverted to MagicMock (deliberate-regression (h))

7. **CLAUDE.md canonical doctrine body extension** at Phase 6 (Plan v1 §10 item 3 PRESERVED): SURFACE-CASCADE-AXIS 7th instance + sub-shape taxonomy update at lines 646-770.

8. **Closure-narrative explicit doctrine X → Y lines** (Plan v1 §10 item 4 EXPANDED):
   - `### Architect-reads-production-code-before-sign-off` 19 → 20 (3rd-cycle self-sustaining adoption)
   - `### Pre-audit-quantifier-precision-refined-by-grep` 6 → 7 (SURFACE-CASCADE-AXIS NEW sub-shape; first post-elevation firing)
   - `### Phase-0-catches-wrong-premise` STAYS at 13
   - `### Zero-precision-items-at-auditor-review` 22 → 23 (Plan v2 surface firing if cycle clears cleanly)
   - `### Phase-0-granular-decomposition-enables-accurate-estimates` 20 → 21 IF closure-actual ∈ [9, 11]
   - `Doctrine-prediction-precision-improving-over-arc` extension IF closure-actual = 10 exact (13th consecutive 0%)
   - `Plan-v1-Pass-2-grep-undercount` 7 → 8 (PATCH-API-VARIANT sub-shape; banked at Plan v2 §0)
   - `Per-artifact-arithmetic-drift-survives-grep-baseline` 5 → 6 AT AUDITOR-SIDE (2nd auditor-side instance; banked at Plan v2 §1.3.A)
   - `Zero-precision-items-pre-closure-predictions-blocked` counter 0 → 1 (P0.R6.Y Plan v1 blocked; pattern-broken streak interrupted at 4 cycles)
   - OPTIONAL-Plan-v2 sub-rule track record STAYS at 10 (P0.R6.Y BLOCKED; no 11th proof case)

---

**End of Plan v2.** Ready for auditor verdict.
