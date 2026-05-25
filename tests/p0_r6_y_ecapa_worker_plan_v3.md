# P0.R6.Y — ECAPA voice ID migration (Plan v3 — PI #2 absorption + convergent enumeration)

**Date**: 2026-05-24
**Author**: architect (Claude)
**Plan v2 verdict**: 1 BLOCKING PI surfaced (§1.3 Shape C + Shape D enumeration drift; ~33 sites per auditor re-grep vs 19 listed). Cycle escalates to Plan v3 absorption per Option (γ) hybrid (auditor lean RATIFIED).
**Cycle shape**: HEAVY-band, 5-artifact cycle (Phase 0 + Plan v1 + Plan v2 + Plan v3 + closure). OPTIONAL-Plan-v2 candidacy BLOCKED for P0.R6.Y. **Highest-artifact cycle since P0.S5** (architect's locked v1→v2→v3 cadence for HEAVY-band cycles).

---

## §0 PI #2 absorption + iterative bidirectional convergence banking

**PI #2 (MEDIUM)**: Plan v2 §1.3 Shape C + Shape D enumeration drift. Architect's Plan v2 grep verified 19 sites (4 → 19 = 4.75× improvement); auditor's Plan v2 verdict re-grep verified ~33 sites (12 + 1 + 12 + 8). Plan v3 architect-side Pass-4 grep further surfaces **5 additional sites** beyond auditor's count, yielding **38 sites convergent enumeration**:

**Bidirectional iteration timeline**:

| Round | Actor | Plan v? | Total enumeration | Catching event |
|---|---|---|---|---|
| 1 | Architect Pass-1 | Phase 0 | 4 sites (1 shape) | baseline |
| 2 | Auditor Pass-2 | Plan v1 verdict | 13 sites (1 shape; off-by-one to 12) | architect-side undercount catch (PI #1) |
| 3 | Architect Pass-3 | Plan v2 | 19 sites (4 shapes) | auditor-side off-by-one catch + 3 NEW API shapes |
| 4 | Auditor Pass-4 | Plan v2 verdict | 33 sites (4 shapes; broader) | architect-side undercount catch on Shape C (4 missing test files) + Shape D (7 missing diarize calls) |
| 5 | **Architect Pass-5 (this Plan v3)** | **Plan v3** | **38 sites (4 shapes; convergent)** | **auditor-side undercount catch on Shape C (4 sites in test_pipeline.py root) + Shape D (1 site _diarize_ecapa_valley at 6497)** |

**Convergence properties**: each round narrows the enumeration gap. Round 5 (this Plan v3) catches 5 additional sites the auditor's Pass-4 grep missed:
- Shape C: auditor's regex `_voice_stub\.fn = MagicMock` covered tests/ subdirectory but missed test_pipeline.py root which uses `_vs` alias (lines 29, 30, 34, 36 — 4 sites)
- Shape D: auditor's regex `_voice_mod\.diarize\(` covered `diarize` cascade function but missed `_diarize_ecapa_valley` direct call at test_pipeline.py:6497 (1 site; architect's Plan v2 §1.3.D originally listed this site — auditor's verdict said "doesn't appear in my grep")

**Banking events at Plan v3 §0**:

1. **`Plan-v1-Pass-2-grep-undercount` 8 → 9 → 10 instances** with NEW **ITERATIVE-BIDIRECTIONAL-CONVERGENCE** sub-shape annotation:
   - 8 → 9: architect-side Plan v2 §1.3 Shape C/D undercount (auditor Pass-4 catches; banked at auditor's Plan v2 verdict)
   - 9 → 10: auditor-side Plan v2 verdict Shape C/D undercount (architect Pass-5 catches; banked HERE at Plan v3 §0)
   - The doctrine-pair operates as ITERATIVE refinement rather than single-round catching — multi-round bidirectional convergence is the maturation shape.

2. **`Per-artifact-arithmetic-drift-survives-grep-baseline` 6 → 7 candidate AT AUDITOR-SIDE** (3rd consecutive auditor-side instance after P0.R6.X Plan v1 + P0.R6.Y Plan v1 verdict):
   - 5 → 6: auditor's "13" → 12 off-by-one at Plan v1 verdict (banked at Plan v2 §1.3.A)
   - 6 → 7: auditor's "~33 sites" claim at Plan v2 verdict undercount by 5 (actual 38) (banked HERE at Plan v3 §0)
   - **3-instance pattern at auditor-side warrants `### Convention-drift-on-discipline-counts` sub-rule extension** — auditor's enumeration count at verdict surfaces drifts when working memory holds large enumerations. Banking shape suggests auditor should adopt explicit grep-verify-count-before-asserting discipline per `feedback_pass_2_grep_deferral_pattern.md` parallel.

3. **NEW architect-memory observation** at `feedback_iterative_bidirectional_catching_convergence.md` (banked candidate per auditor's standing observation #5 + meta-observation): P0.R6.Y is the FIRST cycle demonstrating multi-round (3+) bidirectional iteration on the SAME enumeration drift. Prior cycles converged at 1 or 2 rounds; this is the first 5-round convergence. Future cycles' Pass-N discipline should aim for first-round completeness; architect-handoff item #8 commits to creating this memory file at closure-audit.

**Auditor-handoff continuation observation** at `feedback_pass_2_grep_deferral_pattern.md`: my Plan v2 §1.3 Shape D row 19's "covered by Phase 5 manual migration" framing was the DEFERRAL RED FLAG that the auditor caught at Plan v2 verdict (per their standing observation #3). Plan v3 §1.3.D explicitly enumerates all 9 Shape D sites with per-site disposition; NO deferral framing. The architect-memory observation matures: ALL deferral-to-Phase-N framings (not just explicit "Phase 3 surfaces") are RED FLAGS per the doctrine.

---

## §1 Pass-4 grep verification (architect-side, convergent enumeration)

### §1.1 ECAPA inference enumeration (Plan v1/v2 §1.1 LOCKED; UNCHANGED)

Identical to Plan v1/v2 §1.1.

### §1.2 Pipeline.py caller enumeration (Plan v1/v2 §1.2 LOCKED; UNCHANGED)

Identical to Plan v1/v2 §1.2.

### §1.3 Test infrastructure CONVERGENT enumeration (38 sites across 4 API shapes)

**§1.3.A — `patch(string-target)` sites in `test_pipeline.py`** (12 sites; auditor-verified RATIFIED):

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

**§1.3.B — `patch.object(module, "fn", ...)` sites** (1 site; auditor-verified RATIFIED):

| # | Line | Patch target | Migration |
|---|---|---|---|
| 13 | 6830 | `_voice_mod._diarize_ecapa_valley` (fallback_mock) | `fallback_mock = AsyncMock(return_value=[...])` instead of `MagicMock(...)` |

**§1.3.C — Module-stub-assignment sites** (16 sites across 6 test files; architect Pass-5 expanded auditor's 12 → 16):

| # | File:Line | Stub | Migration |
|---|---|---|---|
| 14 | `tests/conftest.py:38` | `_voice_stub.identify = MagicMock(return_value=(None, 0.0))` | `AsyncMock(return_value=(None, 0.0))` |
| 15 | `tests/conftest.py:39` | `_voice_stub.diarize = MagicMock(return_value=[])` | `AsyncMock(return_value=[])` |
| 16 | `tests/conftest.py:43` | `_voice_stub.embed = MagicMock(return_value=None)` | `AsyncMock(return_value=None)` |
| 17 | `tests/conftest.py:45` | `_voice_stub._diarize_ecapa_valley = MagicMock(return_value=[])` | `AsyncMock(return_value=[])` |
| 18 | `tests/test_dispute_auto_clear.py:24` | `_voice_stub.identify = MagicMock(return_value=(None, 0.0))` | `AsyncMock(return_value=(None, 0.0))` |
| 19 | `tests/test_dispute_auto_clear.py:25` | `_voice_stub.diarize = MagicMock(return_value=[])` | `AsyncMock(return_value=[])` |
| 20 | `tests/test_multispeaker_integration.py:34` | `_voice_stub.identify = MagicMock(return_value=(None, 0.0))` | `AsyncMock(return_value=(None, 0.0))` |
| 21 | `tests/test_multispeaker_integration.py:35` | `_voice_stub.diarize = MagicMock(return_value=[])` | `AsyncMock(return_value=[])` |
| 22 | `tests/test_user_text_gate_invariants.py:90` | `_voice_stub.identify = MagicMock(return_value=(None, 0.0))` | `AsyncMock(return_value=(None, 0.0))` |
| 23 | `tests/test_user_text_gate_invariants.py:91` | `_voice_stub.diarize = MagicMock(return_value=[])` | `AsyncMock(return_value=[])` |
| 24 | `tests/test_user_text_gate_multiword.py:27` | `_voice_stub.identify = MagicMock(return_value=(None, 0.0))` | `AsyncMock(return_value=(None, 0.0))` |
| 25 | `tests/test_user_text_gate_multiword.py:28` | `_voice_stub.diarize = MagicMock(return_value=[])` | `AsyncMock(return_value=[])` |
| 26 | `test_pipeline.py:29` (NEW — architect Pass-5 catch) | `_vs.identify = MagicMock(return_value=(None, 0.0))` | `AsyncMock(return_value=(None, 0.0))` |
| 27 | `test_pipeline.py:30` (NEW — architect Pass-5 catch) | `_vs.diarize = MagicMock(return_value=[])` | `AsyncMock(return_value=[])` |
| 28 | `test_pipeline.py:34` (NEW — architect Pass-5 catch) | `_vs.embed = MagicMock(return_value=None)` | `AsyncMock(return_value=None)` |
| 29 | `test_pipeline.py:36` | `_vs._diarize_ecapa_valley = MagicMock(return_value=[])` | `AsyncMock(return_value=[])` |

`_voice_stub.load_speaker_embedder` (conftest.py:37) STAYS MagicMock (boot-time loader, sync). `_voice_stub._load_pyannote_pipeline` (conftest.py:42) STAYS MagicMock (pyannote loader, sync). `_voice_stub._embedder` (conftest.py:41) STAYS MagicMock (model object, not callable function).

**§1.3.D — Direct-call sites from test functions** (9 sites in `test_pipeline.py`; architect Pass-5 caught auditor's missed `_diarize_ecapa_valley` at 6497):

| # | Line | Direct call | Migration |
|---|---|---|---|
| 30 | `test_pipeline.py:6434` | `result = _voice_mod.diarize(audio, voice_gallery={})` | Test function becomes `async def` + `result = await _voice_mod.diarize(...)` |
| 31 | `test_pipeline.py:6453` | `result = _voice_mod.diarize(audio, voice_gallery={})` | same |
| 32 | `test_pipeline.py:6497` (NEW vs auditor Pass-4) | `result = _voice_mod._diarize_ecapa_valley(audio, voice_gallery={})` | same |
| 33 | `test_pipeline.py:6597` | `segs = _voice_mod.diarize(audio, voice_gallery={})` | same |
| 34 | `test_pipeline.py:6630` | `segs = _voice_mod.diarize(audio, voice_gallery={"p1": ...})` | same |
| 35 | `test_pipeline.py:6670` | `segs = _voice_mod.diarize(audio, voice_gallery={})` | same |
| 36 | `test_pipeline.py:6706` | `segs = _voice_mod.diarize(audio, voice_gallery={})` | same |
| 37 | `test_pipeline.py:6743` | `segs = _voice_mod.diarize(audio, voice_gallery={"jagan_abc": ...})` | same |
| 38 | `test_pipeline.py:6831` | `segs = _voice_mod.diarize(audio, voice_gallery={"p1": ...})` | same |

**Total Plan v3 §1.3 convergent enumeration**: 12 + 1 + 16 + 9 = **38 sites** across 4 distinct API shapes.

(Auditor's Plan v2 verdict counted ~33 sites; architect Pass-5 adds 4 Shape C sites in test_pipeline.py root (NEW; auditor regex used `_voice_stub` alias which didn't match `_vs` alias) + 1 Shape D `_diarize_ecapa_valley` site at 6497 (NEW vs auditor's grep; auditor used `diarize\(` regex which matched short name but not the cascade function name `_diarize_ecapa_valley`).)

### §1.4 Cross-spec interactions (Plan v1/v2 §1.4 LOCKED; UNCHANGED)

Identical to Plan v1/v2 §1.4.

### §1.5 PI #2 absorption disposition (per auditor Option (γ) hybrid lean)

**Option (γ) hybrid RATIFIED**:

1. **§1.3 explicit enumeration**: 38 sites listed per §1.3.A-D above with per-site migration disposition.
2. **A10 EXTENDED programmatic enforcement anchor**: regex scan extended to `tests/**/*.py` (all test files in subdirectory) + `test_pipeline.py` root + `tests/conftest.py`. Covers Shape A + B + C across all test files.
3. **A11 NEW programmatic enforcement anchor for Shape D**: regex scan for `_voice_mod\.(embed|identify|diarize|_diarize_ecapa_valley)\(` direct calls in test files; assert each is preceded by `await` keyword.

**Anchor count moves 10 → 11** per Q5 anchor LOCK update (still ON-TARGET within ±15% INCLUSIVE band [8.5, 11.5] on mid 10; 11 = +10% well within band).

---

## §2 D-decision spec (Plan v1/v2 §2 LOCKED; UNCHANGED)

D1-D4 contracts identical to Plan v1/v2 §2.1-§2.4.

---

## §3 Logical anchor LOCK (Plan v2 LOCK 10 → Plan v3 LOCK 11 per Option (γ) hybrid)

**Mid 10 INCLUSIVE ±15% band → [8.5, 11.5] → ON-TARGET = 9, 10, or 11 anchors**:

| # | Anchor | Surface | Coverage |
|---|---|---|---|
| A1 | `ecapa_embed_worker` function exists in `core/heavy_worker.py` | Source-inspection | D1 |
| A2 | `_SUBPROCESS_ECAPA_EMBEDDER` singleton + `_get_subprocess_ecapa()` accessor present | Source-inspection | D2 |
| A3 | `core/voice.py::embed()` AST shows `hw.run_heavy("ecapa_embed", ...)` Call node | AST positive | D3 part (b) |
| A4 | `core/voice.py::embed()` AST shows `_embedder.encode_batch(` DIRECT call is GONE | AST inverse | D3 part (b) |
| A5 | 5 ECAPA-touching functions all have `async def` signatures | AST signature-cascade | D3 part (a) |
| A6 | `pipeline.py:7148` migrated to `await voice_mod.identify(...)` — LOAD-BEARING asyncio-release fix | AST positive + inverse | D3 site 7148 |
| A7 | 5 pipeline.py caller sites use direct `await voice_mod.X(...)` AND wrapper patterns GONE | AST count check | D3 caller migration |
| A8 | HealthSnapshot reports `"ecapa_embed"` in `_heavy_worker_status` dict | Behavioral | D4 |
| A9 | Startup pool warm-up AST line-order check | AST line-order | D4 |
| **A10** | (EXTENDED) Programmatic test-patch enforcement: regex scan `tests/**/*.py` + `test_pipeline.py` + `tests/conftest.py` for Shape A/B/C patterns; assert each uses AsyncMock | Regex scan + assertion | PI #1/#2 absorption (Shape A/B/C) |
| **A11** | (NEW) Programmatic direct-call enforcement: regex scan `tests/**/*.py` + `test_pipeline.py` for `_voice_mod\.(embed\|identify\|diarize\|_diarize_ecapa_valley)\(` calls; assert each is preceded by `await` keyword | Regex scan + assertion | PI #2 absorption (Shape D) |

**A10 EXTENDED spec**:

```python
def test_p0_r6_y_a10_test_patches_use_asyncmock_for_async_functions() -> None:
    """A10 — programmatic enforcement: all patches/stubs of async voice_mod
    functions (embed, identify, _diarize_ecapa_valley, _diarize_pyannote,
    diarize) use AsyncMock OR async def wrapper. Catches future test additions
    that drift to MagicMock.

    PI #1 + PI #2 absorption per Plan v3 §1.5 Option (γ) hybrid. Surface: 29
    sites (Shape A/B/C) per Plan v3 §1.3.A-C across 6 test files.
    """
    import re
    from pathlib import Path

    _REPO_ROOT = Path(__file__).resolve().parents[1]
    # Scan all test files (including subdirectory)
    test_files = [
        _REPO_ROOT / "test_pipeline.py",
        _REPO_ROOT / "tests" / "conftest.py",
        _REPO_ROOT / "tests" / "test_dispute_auto_clear.py",
        _REPO_ROOT / "tests" / "test_multispeaker_integration.py",
        _REPO_ROOT / "tests" / "test_user_text_gate_invariants.py",
        _REPO_ROOT / "tests" / "test_user_text_gate_multiword.py",
    ]
    # Additionally walk tests/ for any NEW files added in the future
    for test_file in (_REPO_ROOT / "tests").rglob("test_*.py"):
        if test_file not in test_files:
            test_files.append(test_file)

    ASYNC_VOICE_FNS = ("embed", "identify", "_diarize_ecapa_valley",
                       "_diarize_pyannote", "diarize")

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
        # Shape C: module-stub-assignment (covers _voice_stub, _vs, _voice_mod aliases)
        re.compile(
            r'(?:_voice_stub|_vs|_voice_mod)\.('
            + '|'.join(ASYNC_VOICE_FNS) + r')\s*=\s*MagicMock\('
        ),
    ]

    violations = []
    for test_file in test_files:
        if not test_file.exists():
            continue
        src = test_file.read_text(encoding="utf-8")
        for pattern in patterns:
            for match in pattern.finditer(src):
                start = max(0, match.start() - 200)
                end = min(len(src), match.end() + 200)
                context = src[start:end]
                if "AsyncMock" not in context and "async def" not in context:
                    line_no = src[:match.start()].count("\n") + 1
                    rel_path = test_file.relative_to(_REPO_ROOT)
                    violations.append(f"{rel_path}:{line_no} — async fn "
                                     f"`{match.group(1)}` mocked with MagicMock; "
                                     f"requires AsyncMock OR async def wrapper")

    assert not violations, (
        f"P0.R6.Y A10 — {len(violations)} test patch sites use MagicMock for "
        f"async ECAPA functions: " + "; ".join(violations)
    )
```

**A11 NEW spec** (Shape D direct-call enforcement):

```python
def test_p0_r6_y_a11_test_direct_calls_use_await_for_async_functions() -> None:
    """A11 — programmatic enforcement: all direct calls to async voice_mod
    functions (embed, identify, _diarize_ecapa_valley, _diarize_pyannote,
    diarize) in tests must be preceded by `await` keyword. Catches future
    test additions that forget async migration.

    PI #2 absorption per Plan v3 §1.5 Option (γ) hybrid. Surface: 9 sites
    (Shape D) per Plan v3 §1.3.D in test_pipeline.py.
    """
    import re
    from pathlib import Path

    _REPO_ROOT = Path(__file__).resolve().parents[1]
    test_files = [_REPO_ROOT / "test_pipeline.py"]
    for test_file in (_REPO_ROOT / "tests").rglob("test_*.py"):
        if test_file not in test_files:
            test_files.append(test_file)

    ASYNC_VOICE_FNS = ("embed", "identify", "_diarize_ecapa_valley",
                       "_diarize_pyannote", "diarize")

    # Regex: _voice_mod.fn(...) NOT preceded by `await ` keyword
    # Use lookbehind to assert that "await " does NOT precede the call site
    pattern = re.compile(
        r'(?<!await )_voice_mod\.('
        + '|'.join(ASYNC_VOICE_FNS) + r')\('
    )

    violations = []
    for test_file in test_files:
        if not test_file.exists():
            continue
        src = test_file.read_text(encoding="utf-8")
        for match in pattern.finditer(src):
            line_no = src[:match.start()].count("\n") + 1
            rel_path = test_file.relative_to(_REPO_ROOT)
            violations.append(f"{rel_path}:{line_no} — direct call to async "
                             f"`_voice_mod.{match.group(1)}(...)` missing "
                             f"`await` keyword; test function must be `async def`")

    assert not violations, (
        f"P0.R6.Y A11 — {len(violations)} direct calls to async ECAPA "
        f"functions missing `await`: " + "; ".join(violations)
    )
```

---

## §4 Honest-count commitment update (Plan v3 §4)

Closure-actual count will land at exactly **11 anchors** per Plan v3 LOCK. Per band table at §6, ON-TARGET range is 9-11. If implementation reveals a 12th anchor warranting addition, closure-narrative SHALL bank as SLIGHT-DRIFT-UP +20% per band table (within ±30% falsification tolerance; doctrine HOLDS without bumping). Closure-actual UNDER 9 OR OVER 12 (≥13) SHALL invoke the honest-narrative path per locked discipline.

**16th instance of `Explicit-closure-honest-count-commitment` discipline** banked here at Plan v3 §4 (MADE supersedes Plan v2 §4's 15th MADE per the 5-artifact cycle); closure HONORED at closure-audit firing 17th instance per STRICT separation.

---

## §5 Phase-by-phase implementation plan (Plan v2 §5 UPDATED for 38-site migration)

Phase 1-4 + Phase 6 unchanged from Plan v1/v2 §5. Phase 5 updated:

**Phase 5 — Test surface (`tests/test_p0_r6_y_ecapa_worker.py` NEW + 38-site migration)** (~90 min — was 60 min):

1. Create `tests/test_p0_r6_y_ecapa_worker.py`.
2. Implement **11 anchors** per §3 LOCK (A1-A9 from Plan v1 + A10 EXTENDED from Plan v2 + A11 NEW from Plan v3) with the same shape as `tests/test_p0_r6_x_whisper_worker.py` precedent.
3. Run 9/9 deliberate-regression confirmations (Plan v2 §2.5 8 scenarios + Plan v3 new scenario (i)):
   - (a)-(h) per Plan v2 §2.5
   - **(i) NEW — convert 1 of 9 Shape D direct calls back to non-await form (e.g. `result = _voice_mod.diarize(...)` without `await`) → A11 fires**
4. **Test surface migration: 38 sites per §1.3 convergent enumeration**:
   - **Shape A**: 12 `patch(string)` sites in `test_pipeline.py` → `AsyncMock` (or `new_callable=AsyncMock`)
   - **Shape B**: 1 `patch.object` site at `test_pipeline.py:6830` → `fallback_mock = AsyncMock(...)`
   - **Shape C**: 16 stub-assignment sites across 6 test files → `MagicMock` → `AsyncMock`
     - tests/conftest.py: 4 sites (38, 39, 43, 45)
     - tests/test_dispute_auto_clear.py: 2 sites (24, 25)
     - tests/test_multispeaker_integration.py: 2 sites (34, 35)
     - tests/test_user_text_gate_invariants.py: 2 sites (90, 91)
     - tests/test_user_text_gate_multiword.py: 2 sites (27, 28)
     - test_pipeline.py: 4 sites (29, 30, 34, 36)
   - **Shape D**: 9 direct-call sites in `test_pipeline.py` → test function `async def` + `await _voice_mod.X(...)`
     - 6434, 6453, 6497, 6597, 6630, 6670, 6706, 6743, 6831
5. Full suite verification — expect 2696 + 11 + ripple = 2712+ passing post-P0.R6.Y closure baseline.

---

## §6 Closure-projection band table (Plan v2 §6 UPDATED for mid 10 anchor LOCK 11)

| closure-actual | overage vs mid 10 | band | doctrine outcome |
|---|---|---|---|
| 8 | −20% | SLIGHT-DRIFT-DOWN (within ±30%) | `### Phase-0-granular-decomposition` HOLDS at 20 supporting |
| 9 | −10% | ON-TARGET | `### Phase-0-granular-decomposition` 20 → 21 supporting |
| 10 | 0% | ON-TARGET exact mid | `### Phase-0-granular-decomposition` 20 → 21 supporting + 13th consecutive 0% streak |
| 11 | +10% | ON-TARGET | `### Phase-0-granular-decomposition` 20 → 21 supporting (anchor LOCK target) |
| 12 | +20% | SLIGHT-DRIFT-UP (within ±30%) | `### Phase-0-granular-decomposition` HOLDS at 20 supporting |
| ≥13 OR ≤7 | beyond ±30% | FALSIFICATION TRIGGER | `### Phase-0-granular-decomposition` demotes back to architect-memory + reasoning audit |

---

## §7 Pass-5 grep verification baseline (5-artifact cycle)

5-artifact cycle now has 5 grep-verify layers:

- Architect Pass-1 grep at Phase 0 §1.1 + §1.2 + §1.3 baseline ✓
- Auditor Pass-2 grep at Phase 0 verdict ✓ (line-ref hardening)
- Architect Pass-2 grep at Plan v1 §1 ✓ (4 sites; deferral RED FLAG)
- Auditor Pass-3 grep at Plan v1 verdict ✓ (12-13 sites; PI #1)
- Architect Pass-3 grep at Plan v2 §1.3 ✓ (19 sites across 4 shapes)
- Auditor Pass-4 grep at Plan v2 verdict ✓ (33 sites; PI #2 catches Shape C/D undercount)
- **Architect Pass-5 grep at Plan v3 §1.3 (THIS) ✓ (38 sites convergent; catches auditor Pass-4 undercount on 4 Shape C + 1 Shape D)**
- Auditor Pass-5 grep at Plan v3 verdict (standing flag)
- Architect Pass-6 grep at closure-narrative drafting (catches developer Phase 5 implementation drift if any)

---

## §8 Discipline-counter projections update (Plan v2 §8 UPDATED for 5-artifact cycle)

Per locked +1-per-artifact convention: 5-artifact cycle (Phase 0 + Plan v1 + Plan v2 + Plan v3 + closure) increments discipline counters by +1 per artifact.

Baseline post-P0.R6.X closure (2026-05-24):

| Discipline | Baseline | Plan v1 close | Plan v2 close | Plan v3 close (this artifact) | P0.R6.Y closure projection |
|---|---|---|---|---|---|
| Strict-industry-standard mode applications | 75 | 77 | 78 | 79 | 80 |
| Strict-mode successful closures | 22 | 22 | 22 | 22 | 23 |
| Spec-first review cycle | 84-for-84 | 86-for-86 | 87-for-87 | 88-for-88 | 89-for-89 |
| `### Grep-baseline-before-drafting` instances | 42 | 44 | 45 | 46 | 47 |
| Cross-cycle-handoff transparency successful | 48 | 50 | 51 | 52 | 53 |
| Spec-time grep-verification instances | 52 | 54 | 55 | 56 | 57 |
| `### Twin-filename-pitfall-prevention` preventive events | 22 | 22 | 22 | 22 | 22 |
| Auditor-Q5-estimates-trail-grep banked closures | 26 | 26 | 26 | 26 | 27 |
| Deferred-canary strategy applications | 24 | 24 | 24 | 24 | 25 |

**OPTIONAL-Plan-v2 sub-rule track record**: STAYS at 10 (P0.R6.Y BLOCKED at Plan v1 + Plan v2 + Plan v3 absorption cycles; no proof case).

**`Plan-v1-Pass-2-grep-undercount` instance enumeration**:
- 1st-7th: prior instances (locked at P0.R6 closure)
- 8th: P0.R6.Y Plan v1 §1.3 (PATCH-API-VARIANT sub-shape; auditor Pass-2 catch at Plan v1 verdict)
- 9th: P0.R6.Y Plan v2 §1.3 (architect-side Shape C/D undercount; auditor Pass-4 catch at Plan v2 verdict)
- **10th**: P0.R6.Y Plan v3 §1.3 (auditor-side Shape C/D undercount; architect Pass-5 catch at Plan v3 drafting — ITERATIVE-BIDIRECTIONAL-CONVERGENCE sub-shape)

**`Per-artifact-arithmetic-drift-survives-grep-baseline` AT AUDITOR-SIDE pattern**:
- 5 → 6: P0.R6.Y Plan v1 verdict "13" → 12 off-by-one
- **6 → 7**: P0.R6.Y Plan v2 verdict "~33" undercount by 5 (38 actual)
- **3-instance auditor-side pattern**: warrants `### Convention-drift-on-discipline-counts` sub-rule extension — auditor's enumeration count at verdict drifts when working memory holds large enumerations

---

## §9 Locked Q1-Q8 adjudication (Plan v1/v2 §9 UNCHANGED; per auditor verdict RATIFIED at Phase 0)

D1-D4 + Q1-Q8 ratifications identical to Plan v1/v2 §9; PI #2 absorption at §1.3 + A11 does NOT alter the locked D-decisions.

---

## §10 Architect-handoff items for auditor verdict (Plan v2 §10 UPDATED for Plan v3)

1. **Pass-5 grep verification at Plan v3 §1.3** (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine extended to Plan v3): independent re-grep §1.3 38-site convergent enumeration across 4 API shapes across 6 test files (5 in tests/ subdirectory + test_pipeline.py + tests/conftest.py). Confirm architect Pass-5's catches: 4 Shape C in test_pipeline.py root (`_vs` alias) + 1 Shape D `_diarize_ecapa_valley` at 6497.

2. **A10 EXTENDED + A11 NEW adjudication**: confirm A10 EXTENDED covers Shape A/B/C across all test files (`tests/**/*.py` + `test_pipeline.py` + `tests/conftest.py`) AND A11 NEW covers Shape D direct-call detection via lookbehind regex `(?<!await )_voice_mod\.fn\(`. If auditor surfaces additional Shape OR additional file scope, lock as Plan v4 absorption (if needed) OR closure-narrative banking.

3. **ITERATIVE-BIDIRECTIONAL-CONVERGENCE sub-shape ratification**: confirm `Plan-v1-Pass-2-grep-undercount` 9 → 10 with NEW ITERATIVE-BIDIRECTIONAL-CONVERGENCE sub-shape (architect Pass-5 catches auditor Pass-4 undercount within the SAME architectural concern; 3rd round of bidirectional iteration). Same family, NEW sub-shape captures multi-round convergence dynamic.

4. **Per-artifact-arithmetic-drift-survives-grep-baseline 6 → 7 AT AUDITOR-SIDE**: 3rd consecutive auditor-side instance. Banking shape suggests auditor-side grep-verify-count-before-asserting discipline maturation candidate.

5. **NEW architect-memory observation banking** at closure-audit:
   - `feedback_pass_2_grep_deferral_pattern.md`: deferred to closure-audit per Plan v2 §0 banking; matures at Plan v3 §0 (Shape D's "covered by Phase 5 manual migration" framing was the 2nd deferral RED FLAG; auditor caught both rounds)
   - `feedback_iterative_bidirectional_catching_convergence.md`: NEW candidate per auditor's Plan v2 verdict meta-observation #5 + Plan v3 §0 banking; documents the 5-round iteration pattern; watch for additional multi-round catching cycles

6. **Closure-audit Path C grep-verify items** (Plan v2 §10 item 6 EXPANDED for 38-site migration):
   - All Plan v2 closure-audit items preserved
   - Additionally: verify all 38 test patch/stub/direct-call sites migrated per §1.3 (A10 EXTENDED + A11 NEW programmatic enforcement catches future drift; closure-audit verifies at-the-time migration completeness across all 6 test files)
   - Additionally: verify A10 EXTENDED + A11 NEW anchor bodies fire correctly via deliberate-regression scenarios (h) + (i)

7. **CLAUDE.md canonical doctrine body extension** at Phase 6 (Plan v1/v2 §10 item PRESERVED): SURFACE-CASCADE-AXIS 7th instance + sub-shape taxonomy update at lines 646-770.

8. **Closure-narrative explicit doctrine X → Y lines** (Plan v2 §10 item 8 EXPANDED for 5-artifact cycle):
   - `### Architect-reads-production-code-before-sign-off` 19 → 20 (3rd-cycle self-sustaining adoption)
   - `### Pre-audit-quantifier-precision-refined-by-grep` 6 → 7 (SURFACE-CASCADE-AXIS NEW sub-shape; first post-elevation firing)
   - `### Phase-0-catches-wrong-premise` STAYS at 13
   - `### Zero-precision-items-at-auditor-review` 22 → 23 (Plan v3 surface firing if cycle clears cleanly per Plan-vN enumeration rule precedent from P0.S9 + P0.R1 + P0.R4 + auditor's verdict §190)
   - `### Phase-0-granular-decomposition-enables-accurate-estimates` 20 → 21 IF closure-actual ∈ [9, 11]
   - `Doctrine-prediction-precision-improving-over-arc` extension IF closure-actual = 10 exact (13th consecutive 0%; OR =11 = +10% ON-TARGET but no exact-mid streak)
   - `Plan-v1-Pass-2-grep-undercount` 7 → 10 (3 instances banked at this cycle: PATCH-API-VARIANT + auditor-Pass-4 + ITERATIVE-BIDIRECTIONAL-CONVERGENCE)
   - `Per-artifact-arithmetic-drift-survives-grep-baseline` 5 → 7 AT AUDITOR-SIDE (2 instances: P0.R6.Y Plan v1 verdict + Plan v2 verdict)
   - `Zero-precision-items-pre-closure-predictions-blocked` counter STAYS at 1 (P0.R6.Y Plan v1 was 1st block; Plan v2/v3 escalations don't increment counter per its enumeration rule)
   - OPTIONAL-Plan-v2 sub-rule track record STAYS at 10 (P0.R6.Y BLOCKED; no 11th proof case)
   - NEW memory file landings: `feedback_pass_2_grep_deferral_pattern.md` + `feedback_iterative_bidirectional_catching_convergence.md` (both architect-memory candidates)

---

**End of Plan v3.** Ready for auditor verdict.
