# P0.R6.Z — Pyannote diarization migration + `get_diarize_executor()` retirement (Plan v1)

**Date**: 2026-05-24
**Author**: architect (Claude)
**Phase 0 verdict**: ACCEPTED with 0 BLOCKING PIs + 0 non-blocking observations + 4 ratified banking events (Zero-precision-items-at-auditor-review 23 → 24 / RETIREMENT-SURFACE-AXIS 8th sub-shape ratified / Pass-2-grep doctrine 8th consecutive cycle / feedback_pass_2_grep_deferral_pattern.md preventive application honored)
**Cycle shape**: HEAVY band (RETIREMENT-HEAVY), 3-artifact OPTIONAL-Plan-v2 path candidate (11th proof case if cycle clears Plan v1 cleanly)
**Final cycle**: 4-task heavy-worker migration arc COMPLETES at P0.R6.Z

---

## §1 Pass-2 grep verification (architect-side, per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval`)

Per auditor's Phase 0 verdict preventive observation: Pass-2 re-grep at Plan v1 drafting specifically verifies (a) the 14 test sites have not drifted between Phase 0 and Plan v1; (b) Q2 worker-side serialization handles edge cases; (c) A11 regex extension is preventive-only. All three points addressed below.

### §1.1 Pyannote-related production surfaces in `core/voice.py` (Phase 0 §1.1 LOCKED; re-verified at Plan v1 draft)

| # | Surface | File:Line | Action |
|---|---|---|---|
| 1 | `_voice_diarize_executor` module-level var | `core/voice.py:48` | **RETIRE** (D3.a) |
| 2 | `get_diarize_executor()` function | `core/voice.py:51-59` | **RETIRE** (D3.a) |
| 3 | `shutdown_diarize_executor()` function | `core/voice.py:62-67` | **RETIRE** (D3.a) |
| 4 | `_pyannote_pipeline = None` module-level singleton | `core/voice.py:247` | **RETIRE** (D3.a) |
| 5 | `_load_pyannote_pipeline()` function | `core/voice.py:264-314` | **RETIRE** (D3.a; replicated subprocess-side at heavy_worker.py per D2) |
| 6 | `_diarize_pyannote()` body | `core/voice.py:317-403` | **MIGRATE** (D3.b; preserves `async def` from P0.R6.Y) |
| 7 | Line 345 `pipeline = _load_pyannote_pipeline()` | `core/voice.py:345` | **REMOVE** (worker handles model load) |
| 8 | Lines 371-375 `annotation = await loop.run_in_executor(get_diarize_executor(), pipeline, audio_dict)` | `core/voice.py:371-375` | **REPLACE** with `hw.run_heavy("pyannote_diarize", ...)` |
| 9 | Line 386 `for segment, _, label in annotation.itertracks(yield_label=True):` | `core/voice.py:386` | **ADAPT** to iterate `list[tuple[float, float, str]]` from worker |

**Pass-2 verification status**: identical to Phase 0 §1.1; auditor's independent re-grep at Phase 0 verdict confirmed all 6 line refs (48 / 51 / 62 / 247 / 264 / 317). Plan v1 line-refs MATCH Phase 0.

### §1.2 Pyannote-related production surfaces in `pipeline.py` (Phase 0 §1.2 LOCKED; re-verified at Plan v1 draft)

| # | Surface | File:Line | Action |
|---|---|---|---|
| 1 | `_warm_pyannote_via_dedicated_executor()` function | `pipeline.py:6183-6217` | **RETIRE** (D3.c) |
| 2 | Line 6193 `await loop.run_in_executor(voice_mod.get_diarize_executor(), loader)` | `pipeline.py:6193` | **REMOVE** (covered by D3.c retirement) |
| 3 | Line 6219 `_warm_pyannote_via_dedicated_executor(loop, voice_mod._load_pyannote_pipeline)` | `pipeline.py:6219` | **REPLACE** with `hw.get_or_create_pool("pyannote_diarize")` + `set_heavy_worker_status("pyannote_diarize", "healthy")` per D4 |
| 4 | Line 8383 `voice_mod.shutdown_diarize_executor()` | `pipeline.py:8383` | **REMOVE** (subprocess pool handled via `hw.shutdown_all_pools(wait=True)`) |

**Pass-2 verification status**: identical to Phase 0 §1.2; auditor-verified.

### §1.3 Test infrastructure enumeration (auditor's preventive observation (a) — re-verified for drift)

Auditor flagged: "verify (a) the 14 test sites have not drifted between Phase 0 and Plan v1 drafting." Architect Pass-2 re-grep at Plan v1 drafting:

**§1.3.A — `patch.object(_voice_mod, "_load_pyannote_pipeline", ...)` sites** (6 sites in `test_pipeline.py`; line refs preserved):

| # | Line | Patch target | Migration |
|---|---|---|---|
| 1 | 6614 | `_load_pyannote_pipeline` | RETIRE — patch target replaced with `hw.pyannote_diarize_worker` OR `_get_subprocess_pyannote` |
| 2 | 6650 | `_load_pyannote_pipeline` | same |
| 3 | 6693 | `_load_pyannote_pipeline` | same |
| 4 | 6732 | `_load_pyannote_pipeline` | same |
| 5 | 6773 | `_load_pyannote_pipeline` | same |
| 6 | 6867 | `_load_pyannote_pipeline` (`_FailingPipeline`) | same — test failure-fallback path post-migration |

**§1.3.B — Module-stub-assignment sites** (6 stub retirements across 2 files):

| # | File:Line | Stub | Migration |
|---|---|---|---|
| 7 | `tests/conftest.py:47` | `_voice_stub._load_pyannote_pipeline = MagicMock(return_value=None)` | RETIRE |
| 8 | `tests/conftest.py:49` | `_voice_stub._voice_diarize_executor = None` | RETIRE |
| 9 | `tests/conftest.py:51-65` | `_get_diarize_executor_cf` + `_shutdown_diarize_executor_cf` stub functions | RETIRE (function-block deletion) |
| 10 | `test_pipeline.py:34` | `_vs._load_pyannote_pipeline = MagicMock(return_value=None)` | RETIRE |
| 11 | `test_pipeline.py:36` | `_vs._voice_diarize_executor = None` | RETIRE |
| 12 | `test_pipeline.py:38-52` | `_get_diarize_executor_tp` + `_shutdown_diarize_executor_tp` stub functions | RETIRE (function-block deletion) |

**§1.3.C — Dedicated test files** (2 files):

| # | File | Action |
|---|---|---|
| 13 | `tests/test_voice.py` | Auditor verified 3 test methods (including `test_pipeline_uses_dedicated_executor_for_diarize` at line 44 that source-inspects the migrating pattern) — RETIRE/REPURPOSE |
| 14 | `tests/test_warmup.py` | Auditor verified 4 test methods (including `test_warmup_uses_dedicated_executor_for_pyannote` at line 87) — RETIRE/REPURPOSE |

**§1.3.D — Direct-call sites** (zero verified):
Auditor confirmed independent grep shows zero direct `_diarize_pyannote(` test calls. All routes go through public `diarize()` dispatcher. **A11 regex extension is preventive-only** per auditor's preventive observation (c).

**Total test infrastructure migration count**: **14 test sites** (Phase 0 = Plan v1; zero drift between artifacts).

### §1.4 Cross-spec interactions (Phase 0 §1.4 LOCKED; re-verified at Plan v1 draft)

Identical to Phase 0 §1.4 (8 rows; auditor-verified). Cross-spec orthogonality clean.

### §1.5 Pre-audit refinement banking (Phase 0 §1.5 RATIFIED; Plan v1 records the lock)

**RETIREMENT-SURFACE-AXIS** as 8th sub-shape of `### Pre-audit-quantifier-precision-refined-by-grep` doctrine RATIFIED at Phase 0 verdict. Pre-audit framing "2 surfaces" (pipeline migrate + executor retire) refined by Phase 0 grep to 23 distinct retirement events (5 production + 4 pipeline.py + 14 test). Structurally distinct from prior 7 axes — captures orthogonal RETIREMENT SCOPE dimension under-weighted by "retire X + add Y" pre-audit framing.

**Banking at closure-audit**: `### Pre-audit-quantifier-precision-refined-by-grep` 7 → 8 instances with RETIREMENT-SURFACE-AXIS sub-shape. CLAUDE.md canonical doctrine body at lines 646-770 EXTENDED with 8th instance entry + sub-shape taxonomy update at lines ~700 (COUNT-axis → MECHANISM-AXIS → MECHANISM-GENERALITY-AXIS → LAYERED-AXIS → LAYERED-AXIS-continuation → TASK-COMPLETENESS-AXIS → SURFACE-CASCADE-AXIS → **RETIREMENT-SURFACE-AXIS**). Banking note at lines 798-805 preserved verbatim.

---

## §2 D-decision spec (5 D-decisions, locked from Phase 0; Q1-Q9 LOCKED per auditor verdict)

### §2.1 D1 — `pyannote_diarize_worker` in `core/heavy_worker.py`

**LOCKED**. New worker entry point with Q2 (a) lock subprocess-side serialization.

Signature:

```python
def pyannote_diarize_worker(
    audio_bytes: bytes,
    shape: "tuple[int, ...]",
    dtype_name: str,
    sample_rate: int,
) -> "list[tuple[float, float, str]] | None":
    """Worker entry point: deserializes audio buffer + calls subprocess-singleton
    pyannote Pipeline + serializes returned Annotation to list[tuple] via
    annotation.itertracks(yield_label=True) iteration subprocess-side + returns
    serializable list of (start_secs, end_secs, label) triples.

    Q2 (a) lock: subprocess serializes pyannote `Annotation` to list[tuple]
    BEFORE returning — avoids pickle compatibility issues + version-skew risk +
    keeps main process free of pyannote imports.

    Q3 (a) lock: explicit tuple (bytes, shape, dtype_name, sample_rate) for
    IPC payload shape — matches P0.R6 D2 + P0.R6.X D1 + P0.R6.Y D1 precedent.

    Q5 (b) lock: lazy-load pyannote Pipeline on first call via
    _get_subprocess_pyannote() accessor.

    **Edge cases** (per auditor's Phase 0 preventive observation (b)):
    - Empty Annotation (no segments detected) → return empty list []
    - Single-segment Annotation → return single-tuple list [(start, end, label)]
    - len(audio_array) == 0 → return [] (matches main-process pre-D3 semantic)

    Returns None on cascading failure (pyannote pipeline load fails OR sync
    C-extension raises). Preserves P0.R1 D1 None-return fallback contract —
    main-process `_diarize_pyannote` falls through to ECAPA-valley fallback
    per existing `DIARIZATION_FALLBACK_ON_ERROR` logic.
    """
    import numpy as np
    audio_array = np.frombuffer(audio_bytes, dtype=dtype_name).reshape(shape)
    if len(audio_array) == 0:
        return []
    pipeline = _get_subprocess_pyannote()
    if pipeline is None:
        return None
    import torch
    waveform = torch.from_numpy(audio_array.astype(np.float32)).unsqueeze(0)
    if torch.cuda.is_available():
        waveform = waveform.to(torch.device("cuda"))
    try:
        annotation = pipeline({"waveform": waveform, "sample_rate": sample_rate})
    except Exception:  # OPTIONAL: pyannote runtime failure → None propagates
        return None
    # Q2 (a) lock: serialize Annotation → list[tuple] subprocess-side
    result: "list[tuple[float, float, str]]" = []
    for segment, _, label in annotation.itertracks(yield_label=True):
        result.append((float(segment.start), float(segment.end), str(label)))
    return result
```

### §2.2 D2 — `_SUBPROCESS_PYANNOTE_PIPELINE` singleton + `_get_subprocess_pyannote()` accessor in `core/heavy_worker.py`

**LOCKED**. Mirror of P0.R6 D2 + P0.R6.X D2 + P0.R6.Y D2 pattern.

Signature:

```python
_SUBPROCESS_PYANNOTE_PIPELINE: "Any | None" = None


def _get_subprocess_pyannote() -> "Any | None":
    """Returns subprocess-scoped pyannote Pipeline singleton. Lazy-loads on
    first call via Pipeline.from_pretrained(...) + .to(cuda).

    Q5 (b) lock: lazy-load on first call. First-call latency ~30-60s if cold
    HF cache (model download); ~2-3s if cached (model load + CUDA context
    init). Acceptable for infrequent multi-speaker scenarios.

    Q6 (a) lock: HF_TOKEN env var inherits at subprocess spawn time per Python
    multiprocessing semantics. P0.R5 vendored fork (HungryFingerss/pyannote-audio
    @ 2cee8f3e) inherits via requirements.txt git URL.

    P0.R1 D1 None-return fallback contract preserved: returns None on load
    failure → worker returns None → main-process falls through to ECAPA-valley
    fallback.
    """
    global _SUBPROCESS_PYANNOTE_PIPELINE
    if _SUBPROCESS_PYANNOTE_PIPELINE is None:
        try:
            import os
            import torch
            from pyannote.audio import Pipeline
            hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
            _SUBPROCESS_PYANNOTE_PIPELINE = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=hf_token,
            )
            if torch.cuda.is_available():
                _SUBPROCESS_PYANNOTE_PIPELINE.to(torch.device("cuda"))
        except Exception:  # OPTIONAL: load failure → None propagates
            return None
    return _SUBPROCESS_PYANNOTE_PIPELINE
```

### §2.3 D3 — `core/voice.py` retirements + `_diarize_pyannote()` body migration + `pipeline.py` retirements

**LOCKED — 3 sub-decisions**:

**D3.a — `core/voice.py` retirements** (5 surfaces deleted; hard-delete per Q1 (a) lock):

```python
# Lines to DELETE:
# Line 48: _voice_diarize_executor: "ThreadPoolExecutor | None" = None
# Lines 51-59: def get_diarize_executor() -> ThreadPoolExecutor: ...
# Lines 62-67: def shutdown_diarize_executor() -> None: ...
# Line 247: _pyannote_pipeline = None
# Lines 264-314: def _load_pyannote_pipeline(): ...
```

Plus remove the `from concurrent.futures import ThreadPoolExecutor` import at top of `core/voice.py` if it's no longer used after D3.a (Phase 5 verify via grep).

**D3.b — `_diarize_pyannote()` body migration** (lines 344-403):

```python
# AFTER (replaces lines 344-403)
global _diarize_fallback_count
if len(audio) == 0:
    return []
import core.heavy_worker as hw
try:
    segments_raw = await hw.run_heavy(
        "pyannote_diarize",
        hw.pyannote_diarize_worker,
        audio.tobytes(),
        audio.shape,
        audio.dtype.name,
        sample_rate,
    )
except Exception as e:
    print(f"[Voice] pyannote diarize runtime error: {type(e).__name__}: {e}")
    if DIARIZATION_FALLBACK_ON_ERROR:
        _diarize_fallback_count += 1
        print(f"[Voice] WARN diarize fallback (runtime) — ecapa_valley "
              f"for this call (fallback #{_diarize_fallback_count})")
        return await _diarize_ecapa_valley(audio, voice_gallery, threshold, sample_rate)
    return []

if segments_raw is None:
    # Worker returned None — pyannote pipeline load failure (cold cache fail
    # OR vendored fork import broken). Preserves P0.R1 D1 None-return contract.
    if DIARIZATION_FALLBACK_ON_ERROR:
        _diarize_fallback_count += 1
        print(f"[Voice] WARN diarize fallback (load-fail) — "
              f"pyannote unavailable, using ecapa_valley "
              f"(fallback #{_diarize_fallback_count})")
        return await _diarize_ecapa_valley(audio, voice_gallery, threshold, sample_rate)
    return []

# Q9 (a) lock: BrokenProcessPool exceptions land in the outer `except Exception`
# above (concurrent.futures.process.BrokenProcessPool inherits Exception). Pool
# auto-restarts on next `hw.run_heavy("pyannote_diarize", ...)` call (new
# subprocess spawns).

segments: list[dict] = []
for start_secs, end_secs, label in segments_raw:
    dur = end_secs - start_secs
    if dur < DIARIZE_MIN_SEGMENT_SECS:
        continue
    start_s = int(start_secs * sample_rate)
    end_s   = min(int(end_secs * sample_rate), len(audio))
    if dur < DIARIZE_MIN_EMBED_SECS:
        segments.append({
            "start_sample":  start_s,
            "end_sample":    end_s,
            "speaker_id":    None,
            "speaker_score": 0.0,
            "speaker_label": label,
        })
        continue
    seg_audio  = audio[start_s:end_s]
    pid, score = await identify(seg_audio, voice_gallery, threshold, sample_rate)
    segments.append({
        "start_sample":  start_s,
        "end_sample":    end_s,
        "speaker_id":    pid,
        "speaker_score": score,
        "speaker_label": label,
    })
return segments
```

**D3.c — `pipeline.py` retirements + new pool warm-up**:

```python
# DELETE pipeline.py:6183-6217: async def _warm_pyannote_via_dedicated_executor(...)
# DELETE pipeline.py:8383: voice_mod.shutdown_diarize_executor()

# REPLACE pipeline.py:~6219 call site:
# BEFORE
asyncio.create_task(
    _warm_pyannote_via_dedicated_executor(loop, voice_mod._load_pyannote_pipeline),
)
# AFTER (matches P0.R6 D5 + R6.X D4 + R6.Y D4 pool warm-up pattern)
hw.get_or_create_pool("pyannote_diarize")
asyncio.create_task(_pipeline_state_store.set_heavy_worker_status("pyannote_diarize", "healthy"))
```

### §2.4 D4 — health observability + 4-pool ORDERING INVARIANT

**LOCKED**. Reuses P0.R6 D4 + P0.R6.X D4 + P0.R6.Y D4 `_heavy_worker_status` dict pattern. Adds `"pyannote_diarize"` key with initial "healthy" status.

**4-pool ORDERING INVARIANT** at startup:

```python
# pipeline.py::run() — POST-P0.R6.Z shape
hw.get_or_create_pool("adaface_embed")           # 1st (P0.R6)
asyncio.create_task(_pipeline_state_store.set_heavy_worker_status("adaface_embed", "healthy"))
hw.get_or_create_pool("whisper_transcribe")      # 2nd (P0.R6.X)
asyncio.create_task(_pipeline_state_store.set_heavy_worker_status("whisper_transcribe", "healthy"))
hw.get_or_create_pool("ecapa_embed")             # 3rd (P0.R6.Y)
asyncio.create_task(_pipeline_state_store.set_heavy_worker_status("ecapa_embed", "healthy"))
hw.get_or_create_pool("pyannote_diarize")        # 4th (P0.R6.Z) — NEW
asyncio.create_task(_pipeline_state_store.set_heavy_worker_status("pyannote_diarize", "healthy"))
_vision_task = asyncio.create_task(_background_vision_loop(...))  # AFTER all 4 pool warm-ups
```

**Shutdown unchanged**: P0.R6 D5 `hw.shutdown_all_pools(wait=True)` already terminates ALL pools (including pyannote_diarize) cleanly. The line 8383 `voice_mod.shutdown_diarize_executor()` deleted at D3.c is fully covered by `hw.shutdown_all_pools`.

### §2.5 D5 — test surface retirement/repurpose (14 sites)

**LOCKED**. Per Q8 (a) hard-delete + new anchors in `tests/test_p0_r6_z_pyannote_worker.py`:

**Retire**:
- 6 Shape B `patch.object(_voice_mod, "_load_pyannote_pipeline", ...)` sites: rewrite to mock `hw.pyannote_diarize_worker` OR `hw._get_subprocess_pyannote` OR via pool-level patching
- 6 Shape C stub-assignment sites in `conftest.py` + `test_pipeline.py`: delete `_voice_stub._load_pyannote_pipeline` + `_voice_stub._voice_diarize_executor` + `_get_diarize_executor_cf/_tp` + `_shutdown_diarize_executor_cf/_tp` function blocks
- `tests/test_voice.py` get_diarize_executor tests: DELETE 3 test methods (preserve any non-pyannote-pool tests in same file if any)
- `tests/test_warmup.py` _warm_pyannote_via_dedicated_executor tests: DELETE 4 test methods (preserve any non-pyannote-warmup tests if any)

**Add (in `tests/test_p0_r6_z_pyannote_worker.py`)**:
- 11 anchors per §3 LOCK below

### §2.6 Deliberate-regression scenarios (per `### Induction-surfaces-invariant-gaps` doctrine)

9 scenarios for the 11 anchors:

| Revert | Expected anchor fire | Catches |
|---|---|---|
| (a) Delete `pyannote_diarize_worker` from `core/heavy_worker.py` | A1 | Worker function gone |
| (b) Replace `_get_subprocess_pyannote()` body with `return None` | A2 | Singleton accessor broken |
| (c) Revert `_diarize_pyannote()` body to old `_load_pyannote_pipeline()` + `run_in_executor(get_diarize_executor(), ...)` direct call | A3 + A4 | Body migration regressed |
| (d) Restore any 1 of 5 retired symbols in `core/voice.py` | A5 | 5-prong retirement inverse fires |
| (e) Restore `_warm_pyannote_via_dedicated_executor` function OR `shutdown_diarize_executor` call in `pipeline.py` | A6 | pipeline.py retirement inverse fires |
| (f) Modify worker to return pyannote `Annotation` directly instead of list[tuple] | A7 | Return-shape behavioral fires (worker raises pickle error OR main process iteration fails) |
| (g) Drop `hw.get_or_create_pool("pyannote_diarize")` from startup wiring | A8 + A9 | Health snapshot missing key + ordering invariant fires |
| (h) Replace 1 of test patch sites with `MagicMock` instead of `AsyncMock` OR direct-import pyannote types | A10 | Programmatic test-patch enforcement fires |
| (i) Add `_voice_mod._diarize_pyannote(...)` direct call WITHOUT await in any test file | A11 | Programmatic direct-call enforcement fires (preventive scenario — currently zero call sites) |

9/9 deliberate-regression scenarios for 11 anchors. A4 + A5 + A6 collectively cover the retirement-inverse surface.

---

## §3 Logical anchor LOCK (Q5 LOCK = 11 anchors at EXACT MID)

Per auditor Phase 0 verdict §4 Q5 ratification: **11 anchors at exact mid 11 INCLUSIVE ±15% band [9.35, 12.65]**.

| # | Anchor | Surface | Coverage |
|---|---|---|---|
| A1 | `pyannote_diarize_worker` function exists in `core/heavy_worker.py` | Source-inspection | D1 |
| A2 | `_SUBPROCESS_PYANNOTE_PIPELINE` singleton + `_get_subprocess_pyannote()` accessor present | Source-inspection | D2 |
| A3 | `core/voice.py::_diarize_pyannote()` body AST shows `hw.run_heavy("pyannote_diarize", ...)` Call node | AST positive | D3.b |
| A4 | `core/voice.py::_diarize_pyannote()` body AST shows `_load_pyannote_pipeline()` call AND `run_in_executor(get_diarize_executor(), ...)` pattern are BOTH GONE | AST inverse | D3.b |
| A5 | `core/voice.py` source shows `get_diarize_executor` + `shutdown_diarize_executor` + `_voice_diarize_executor` + `_pyannote_pipeline` + `_load_pyannote_pipeline` are ALL GONE (5-prong retirement inverse) | Source-inspection inverse | D3.a |
| A6 | `pipeline.py` source shows `_warm_pyannote_via_dedicated_executor` function def + `shutdown_diarize_executor` call + `voice_mod.get_diarize_executor` references are ALL GONE | Source-inspection inverse | D3.c |
| A7 | Worker return shape is `list[tuple[float, float, str]]` per Q2 (a) lock — behavioral test verifies edge cases (empty Annotation → empty list; single-segment → single-tuple list) | Behavioral | D1 |
| A8 | HealthSnapshot reports `"pyannote_diarize"` in `_heavy_worker_status` dict | Behavioral | D4 |
| A9 | Startup pool warm-up AST line-order: `hw.get_or_create_pool("pyannote_diarize")` lands BEFORE vision task spawn AND AFTER AdaFace + Whisper + ECAPA pool warm-ups (4-pool ordering invariant) | AST line-order | D4 |
| A10 | (EXTENDED from P0.R6.Y A10) Programmatic test-patch enforcement: regex scan extended to cover `pyannote_diarize_worker` + `_get_subprocess_pyannote` patches; Shape A/B/C across `tests/**/*.py` + `test_pipeline.py` + `tests/conftest.py` | Regex scan + assertion | D5 / PI prevention |
| A11 | (EXTENDED from P0.R6.Y A11) Programmatic direct-call enforcement: regex includes `_diarize_pyannote` direct calls (preventive — zero current sites per auditor verification) | Regex scan + assertion | D5 / PI prevention |

---

## §4 Honest-count commitment (per `Explicit-closure-honest-count-commitment` discipline)

Closure-actual count will land at exactly **11 anchors** per Plan v1 LOCK. Per band table at §6, ON-TARGET range is 10-12. If implementation reveals a 12th anchor warranting addition (e.g. defense-in-depth at developer Phase 4), closure-narrative SHALL bank as ON-TARGET +9.1% per band table. Closure-actual UNDER 10 OR OVER 12 SHALL invoke the honest-narrative path.

**19th instance of `Explicit-closure-honest-count-commitment` discipline** banked here at Plan v1 §4 (MADE); closure HONORED at closure-audit firing 20th instance per STRICT separation locked at P0.B3.

---

## §5 Phase-by-phase implementation plan

**Phase 1 — Worker + subprocess singleton (D1 + D2)** (~40 min):

1. Open `core/heavy_worker.py`.
2. After `ecapa_embed_worker` block (P0.R6.Y), add `_SUBPROCESS_PYANNOTE_PIPELINE: "Any | None" = None` module-level var.
3. After `_SUBPROCESS_PYANNOTE_PIPELINE`, add `_get_subprocess_pyannote()` accessor per §2.2 signature.
4. After `_get_subprocess_pyannote()`, add `pyannote_diarize_worker` per §2.1 signature.
5. Imports already include `numpy as np` (verified P0.R6+R6.X+R6.Y); add `import os` if not already at module-top (HF_TOKEN access).

**Phase 2 — `core/voice.py` retirements + body migration (D3.a + D3.b)** (~45 min):

1. Open `core/voice.py`.
2. Delete 5 retirement targets per D3.a (lines 48 / 51-59 / 62-67 / 247 / 264-314).
3. Replace `_diarize_pyannote()` body lines 344-403 per §2.3 D3.b code block.
4. Verify `from concurrent.futures import ThreadPoolExecutor` import at top of file is unused post-D3.a; remove if so.
5. Verify ALL retirement-affected references in same file are gone (grep `_voice_diarize_executor` + `get_diarize_executor` + `shutdown_diarize_executor` + `_pyannote_pipeline` + `_load_pyannote_pipeline` post-edit; expect zero matches except docstrings/comments).

**Phase 3 — `pipeline.py` retirements + pool warm-up (D3.c)** (~25 min):

1. Open `pipeline.py`.
2. Delete `_warm_pyannote_via_dedicated_executor` function (lines 6183-6217).
3. Replace warmup call at line ~6219 per §2.3 D3.c code (add `pyannote_diarize` pool warm-up + healthy-status setter immediately after ECAPA pool warm-up).
4. Delete `voice_mod.shutdown_diarize_executor()` call at line 8383.
5. Verify ORDERING INVARIANT: 4 pool warm-ups (AdaFace + Whisper + ECAPA + Pyannote) BEFORE vision task spawn.

**Phase 4 — Test surface retirement/repurpose (D5)** (~75 min):

1. **Retire conftest.py + test_pipeline.py stubs** (Shape C, 6 stub events):
   - Delete `tests/conftest.py:47, 49, 51-65` (stub assignments + helper functions)
   - Delete `test_pipeline.py:34, 36, 38-52` (same shape)
2. **Migrate Shape B patch.object sites** (6 sites in test_pipeline.py: 6614/6650/6693/6732/6773/6867):
   - Each currently patches `_load_pyannote_pipeline`; replace with `patch.object(hw, "_get_subprocess_pyannote", return_value=fake)` OR `patch("core.heavy_worker.pyannote_diarize_worker", new_callable=AsyncMock)` depending on test intent
   - Test at line 6867 specifically tests failure-fallback path — preserve `_FailingPipeline` semantic by mocking worker to return None
3. **Delete obsolete test methods**:
   - `tests/test_voice.py`: delete 3 test methods asserting `get_diarize_executor()` singleton/wrapping behavior
   - `tests/test_warmup.py`: delete 4 test methods asserting `_warm_pyannote_via_dedicated_executor` behavior
4. **Create `tests/test_p0_r6_z_pyannote_worker.py`** with 11 anchors per §3 LOCK using same shape as `tests/test_p0_r6_y_ecapa_worker.py` precedent.
5. **Run 9/9 deliberate-regression confirmations** per §2.6 table.
6. Full suite verification — expect 2707 + 11 + ripple = 2720+ passing post-P0.R6.Z closure.

**Phase 5 — Closure narrative + audit (~40 min)**:

1. Update `CLAUDE.md` line 3 test count.
2. Bank P0.R6.Z closure entry with all explicit X → Y narrative lines per Plan v1 §10 item 4.
3. **Extend CLAUDE.md canonical doctrine body at lines 646-770** per Phase 0 architect-handoff:
   - Add P0.R6.Z 8th instance entry (RETIREMENT-SURFACE-AXIS) after the P0.R6.Y entry
   - Update "5 applications + 4-axis sub-shape taxonomy" → "8 applications + 7-axis sub-shape taxonomy" or note sub-shape progression at lines ~656 + ~700
   - Preserve banking note at lines 798-805 verbatim
4. Architect closure-audit Path C grep-verify against production code.
5. Verify 4-pool ORDERING INVARIANT preserved at `pipeline.py::run()`.

---

## §6 Closure-projection band table + doctrine outcomes

| closure-actual | overage vs mid 11 | band | doctrine outcome |
|---|---|---|---|
| 9 | −18.2% | SLIGHT-DRIFT-DOWN (within ±30%) | `### Phase-0-granular-decomposition` HOLDS at 21 supporting |
| 10 | −9.1% | ON-TARGET | `### Phase-0-granular-decomposition` 21 → 22 supporting |
| 11 | 0% | ON-TARGET exact mid | `### Phase-0-granular-decomposition` 21 → 22 supporting + 13th consecutive 0% streak rebuild (12 was interrupted at P0.R6.Y +10%; P0.R6.Z exact-mid = streak rebuild from 1) per `Doctrine-prediction-precision-improving-over-arc` |
| 12 | +9.1% | ON-TARGET | `### Phase-0-granular-decomposition` 21 → 22 supporting |
| 13 | +18.2% | SLIGHT-DRIFT-UP (within ±30%) | `### Phase-0-granular-decomposition` HOLDS at 21 supporting |
| ≥14 OR ≤8 | beyond ±30% | FALSIFICATION TRIGGER | doctrine demotes back to architect-memory + reasoning audit |

---

## §7 Pass-3 grep verification baseline (architect-side at closure-narrative drafting)

3-artifact OPTIONAL-Plan-v2 cycle has 3 grep-verify layers:

- Architect Pass-1 grep at Phase 0 §1.1 + §1.2 + §1.3 + §1.4 baseline ✓
- Auditor Pass-2 grep at Phase 0 verdict ✓ (line-refs CONFIRMED)
- Architect Pass-2 grep at Plan v1 §1 (this artifact) ✓ (zero drift from Phase 0; auditor preventive observation (a) honored)
- Auditor Pass-2 grep at Plan v1 verdict (standing flag per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval`)
- Architect Pass-3 grep at closure-narrative drafting (catches developer Phase 4 implementation drift if any)

If Pass-3 surfaces enumeration drift, `Plan-v1-Pass-2-grep-undercount` 11 → 12 candidate.

---

## §8 Discipline-counter projections (locked +1-per-artifact)

Per locked convention: 3-artifact OPTIONAL-Plan-v2 cycle (Phase 0 + Plan v1 + closure) increments discipline counters by +1 per artifact.

Baseline post-P0.R6.Y closure (2026-05-24):

| Discipline | Baseline | Plan v1 close (this artifact) | P0.R6.Z closure projection |
|---|---|---|---|
| Strict-industry-standard mode applications | 80 | 82 | 83 |
| Strict-mode successful closures | 23 | 23 | 24 |
| Spec-first review cycle | 89-for-89 | 91-for-91 | 92-for-92 |
| `### Grep-baseline-before-drafting` instances | 47 | 49 | 50 |
| Cross-cycle-handoff transparency successful | 53 | 55 | 56 |
| Spec-time grep-verification instances | 57 | 59 | 60 |
| `### Twin-filename-pitfall-prevention` preventive events | 22 | stays 22 (preventive event honored at audit drafting) | 23 (at closure) |
| Auditor-Q5-estimates-trail-grep banked closures | 27 | 27 | 28 |
| Deferred-canary strategy applications | 25 | 25 | 26 |

**OPTIONAL-Plan-v2 path candidacy**: if auditor returns 0 precision items at this Plan v1 review, cycle ships as 3-artifact (Phase 0 + Plan v1 + closure). **11th OPTIONAL-Plan-v2 proof case candidate post-closure** (P0.S3 + P0.B3 + P0.B5 + P0.B6 + P0.S8 + P0.R2 + P0.R3 + P0.R5 + P0.R6 + P0.R6.X + **P0.R6.Z**). P0.R6.Y BLOCKED (5-artifact); P0.R6.Z reclaims.

**`### Pre-audit-quantifier-precision-refined-by-grep` instance enumeration** (post-P0.R6.Y closure baseline):

- 1st-7th: prior instances per CLAUDE.md canonical (lines 659-720)
- **8th**: P0.R6.Z Phase 0 (RETIREMENT-SURFACE-AXIS NEW sub-shape — pre-audit "2 surfaces" refined to 23 retirement events)

Sub-shape taxonomy after P0.R6.Z: COUNT-AXIS, MECHANISM-AXIS, MECHANISM-GENERALITY-AXIS, LAYERED-AXIS, TASK-COMPLETENESS-AXIS, SURFACE-CASCADE-AXIS, **RETIREMENT-SURFACE-AXIS** (NEW).

---

## §9 Locked Q1-Q9 adjudication (per auditor Phase 0 verdict RATIFIED)

| Q | Locked | Implementation effect |
|---|---|---|
| Q1 (LOAD-BEARING) | (a) hard delete | 5 production surfaces in `core/voice.py` deleted entirely; no deprecation stubs |
| Q2 (LOAD-BEARING) | (a) worker serializes Annotation → list[tuple] | `pyannote_diarize_worker` returns `list[tuple[float, float, str]]` of (start_secs, end_secs, label); main process iterates simple list |
| Q3 | (a) explicit tuple `(bytes, shape, dtype_name, sample_rate)` | IPC payload shape matches P0.R6 + R6.X + R6.Y precedent |
| Q4 | (a) per Q2 | Inherits Q2 decision |
| Q5 | (b) lazy load on first call | Matches R6+R6.X+R6.Y precedent; ~30-60s first-call latency on cold HF cache acceptable |
| Q6 | (a) explicit `mp.get_context("spawn")` + HF_TOKEN env inherit | Cross-platform requirement inherited from P0.R6 |
| Q7 | max_workers=1 | Pyannote inference sequential per session |
| Q8 (LOAD-BEARING) | (a) delete obsolete test methods; new anchors in `tests/test_p0_r6_z_pyannote_worker.py` | Cleaner separation; subprocess-pool tests belong with the new anchor file |
| Q9 (LOAD-BEARING) | (a) BrokenProcessPool → None → ECAPA-valley fallback | Preserves P0.R1 D1 None-return + `DIARIZATION_FALLBACK_ON_ERROR` contracts; pool auto-restarts on next call |

---

## §10 Architect-handoff items for auditor verdict

1. **Pass-2 grep verification** (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine): independent re-grep §1.1 9-row + §1.2 4-row + §1.3 14-site + §1.4 8-row cross-spec table. Plan v1 line refs MATCH Phase 0; zero drift per auditor's preventive observation (a). If auditor surfaces additional sites OR cross-spec interactions, lock as Plan v2 PI #1 absorption per Option α pattern.

2. **Q2 edge-case verification** (per auditor's Phase 0 preventive observation (b)): confirm `pyannote_diarize_worker` handles 3 edge cases:
   - Empty audio buffer (`len(audio_array) == 0`) → returns `[]`
   - Empty Annotation (pyannote returns 0 segments) → returns `[]`
   - Single-segment Annotation → returns single-tuple list `[(start, end, label)]`
   - Pipeline load failure → returns `None`
   §2.1 D1 worker body covers all 4 cases explicitly.

3. **A11 regex extension** (per auditor's Phase 0 preventive observation (c)): confirm A11 regex preventively covers `_diarize_pyannote` direct calls. Current grep shows ZERO `_voice_mod._diarize_pyannote(` test sites; A11 regex extension is preventive-only (future test additions that introduce direct calls without await would fire the anchor).

4. **Closure-audit Path C grep-verify items** (banked for architect closure-audit at Phase 5):
   - Verify `pyannote_diarize_worker` lands at `core/heavy_worker.py` with exact signature per §2.1
   - Verify `_SUBPROCESS_PYANNOTE_PIPELINE` + `_get_subprocess_pyannote()` land per §2.2
   - Verify 5 retirements applied in `core/voice.py` (zero remaining references per inverse grep)
   - Verify `_diarize_pyannote()` body uses `hw.run_heavy("pyannote_diarize", ...)`
   - Verify 4 pipeline.py retirements applied (function deletion + 2 call site changes + shutdown call deletion)
   - Verify A4 + A5 + A6 inverse checks fire correctly
   - Verify health snapshot reports `"pyannote_diarize"` key
   - Verify 4-pool ORDERING INVARIANT preserved
   - Verify 14 test sites migrated/retired per §1.3

5. **CLAUDE.md canonical doctrine body extension** at Phase 5: RETIREMENT-SURFACE-AXIS 8th instance + sub-shape taxonomy update at lines 646-770. Preserve banking note at 798-805 verbatim.

6. **Closure-narrative explicit doctrine X → Y lines** (per `Implicit-doctrine-firings-not-narrative-tracked` 4th-cycle self-sustaining adoption):
   - `### Architect-reads-production-code-before-sign-off` 20 → 21 with explicit narrative line
   - `### Pre-audit-quantifier-precision-refined-by-grep` 7 → 8 (RETIREMENT-SURFACE-AXIS NEW sub-shape; 2nd post-elevation firing)
   - `### Phase-0-catches-wrong-premise` STAYS at 13 (premise correct this cycle)
   - `### Zero-precision-items-at-auditor-review` 24 → 25 (Plan v1 surface firing if cycle clears cleanly)
   - `### Phase-0-granular-decomposition-enables-accurate-estimates` 21 → 22 IF closure-actual ∈ [10, 12]
   - `Doctrine-prediction-precision-improving-over-arc` 13th consecutive 0% streak rebuild IF closure-actual = 11 exact
   - OPTIONAL-Plan-v2 sub-rule track record 10 → 11 proof cases (P0.R6.Z reclaims after P0.R6.Y BLOCKED)
   - `### Twin-filename-pitfall-prevention` 22 → 23 preventive events at closure
   - Strict-industry-standard mode 80 → 83 + 23 → 24 closures
   - Spec-first review cycle 89 → 92-for-92 at closure
   - 4-task heavy-worker arc COMPLETES — banked at CLAUDE.md as arc-closure milestone

---

**End of Plan v1.** Ready for auditor verdict. Final cycle of 4-task heavy-worker migration arc.
