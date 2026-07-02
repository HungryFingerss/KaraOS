# P0.R6.Z — Pyannote diarization migration to ProcessPoolExecutor worker + `get_diarize_executor()` retirement (Phase 0 audit)

**Date**: 2026-05-24
**Author**: architect (Claude)
**Cycle shape**: HEAVY band (RETIREMENT-HEAVY), foundation reused from P0.R6 `core/heavy_worker.py` infrastructure (Q1 (a) decomposition follow-up #3 — final cycle of the 4-task heavy-worker migration)
**Estimated effort**: ~4-5h HEAVY-band cycle (largest of the 4 R6.* sub-cycles — retirement scope spans 5 production functions/vars + 2 dedicated test files)

---

## §0 Pre-audit framing (LOCKED 2026-05-24 by architect BEFORE grep verification)

> "P0.R6.Z migrates pyannote pipeline to ProcessPoolExecutor worker + retires `get_diarize_executor()` entirely per P0.R6.Y Plan v3 §1.4 commitment. Pyannote is the heaviest model (~3GB CUDA work). Cumulative VRAM after R6+R6.X+R6.Y+R6.Z: ~6.3GB across 4 subprocess workers. Final cycle of the 4-task heavy-worker migration."

Phase 0 grep verifies framing against production. Findings below.

---

## §1 Grep findings (Pass-1 baseline) — COMPREHENSIVE upfront (no deferral framings per `feedback_pass_2_grep_deferral_pattern.md` doctrine)

### §1.1 Pyannote-related production surfaces in `core/voice.py`

| # | Surface | File:Line | Action |
|---|---|---|---|
| 1 | `_voice_diarize_executor: ThreadPoolExecutor \| None = None` | `core/voice.py:48` | **RETIRE** (subprocess pool replaces) |
| 2 | `get_diarize_executor()` function | `core/voice.py:51-59` | **RETIRE** (callers migrate to `hw.run_heavy("pyannote_diarize", ...)`) |
| 3 | `shutdown_diarize_executor()` function | `core/voice.py:62-67` | **RETIRE** (subprocess pool shutdown via `hw.shutdown_all_pools(wait=True)`) |
| 4 | `_pyannote_pipeline = None` module-level singleton | `core/voice.py:247` | **RETIRE** (subprocess holds its own singleton) |
| 5 | `_load_pyannote_pipeline()` function | `core/voice.py:264-314` | **RETIRE** (replicate in `core/heavy_worker.py` as `_get_subprocess_pyannote()` accessor; main process no longer holds pyannote pipeline) |
| 6 | `_diarize_pyannote()` body | `core/voice.py:317-403` | **MIGRATE** body (preserve `async def` from P0.R6.Y; replace pipeline call with worker dispatch) |
| 7 | Line 345 `pipeline = _load_pyannote_pipeline()` | `core/voice.py:345` | **REMOVE** (worker handles model load) |
| 8 | Lines 371-375 `annotation = await loop.run_in_executor(get_diarize_executor(), pipeline, audio_dict)` | `core/voice.py:371-375` | **REPLACE** with `segments_raw = await hw.run_heavy("pyannote_diarize", hw.pyannote_diarize_worker, audio.tobytes(), audio.shape, audio.dtype.name, sample_rate)` |
| 9 | Line 386 `for segment, _, label in annotation.itertracks(yield_label=True):` | `core/voice.py:386` | **ADAPT** — worker returns serializable `list[tuple[start_secs, end_secs, label]]`; main-process iteration adapts to simple list |

### §1.2 Pyannote-related production surfaces in `pipeline.py`

| # | Surface | File:Line | Action |
|---|---|---|---|
| 1 | `_warm_pyannote_via_dedicated_executor()` function | `pipeline.py:6183-6217` | **RETIRE** (subprocess pool warm-up via `hw.get_or_create_pool("pyannote_diarize")` is the new pattern) |
| 2 | Line 6193 `await loop.run_in_executor(voice_mod.get_diarize_executor(), loader)` (warm-up dispatch) | `pipeline.py:6193` | **REMOVE** (covered by retirement above) |
| 3 | Line 6219 `_warm_pyannote_via_dedicated_executor(loop, voice_mod._load_pyannote_pipeline)` call site | `pipeline.py:6219` | **REPLACE** with `hw.get_or_create_pool("pyannote_diarize")` + `_pipeline_state_store.set_heavy_worker_status("pyannote_diarize", "healthy")` per D4 |
| 4 | Line 8383 `voice_mod.shutdown_diarize_executor()` shutdown call | `pipeline.py:8383` | **REMOVE** (subprocess pool handled via `hw.shutdown_all_pools(wait=True)` already in shutdown finally block) |

### §1.3 Test infrastructure enumeration — COMPREHENSIVE upfront per P0.R6.Y lessons (4 API shapes × multiple files)

**§1.3.A — `patch.object(module, "fn", ...)` sites for `_load_pyannote_pipeline`** (Shape B; 6 sites in `test_pipeline.py`):

| # | Line | Patch target | Migration |
|---|---|---|---|
| 1 | 6614 | `_load_pyannote_pipeline` | RETIRE — function gone post-D3; test migrates to mocking `hw.pyannote_diarize_worker` OR `_get_subprocess_pyannote` OR via worker-pool-level patching |
| 2 | 6650 | `_load_pyannote_pipeline` | same |
| 3 | 6693 | `_load_pyannote_pipeline` | same |
| 4 | 6732 | `_load_pyannote_pipeline` | same |
| 5 | 6773 | `_load_pyannote_pipeline` | same |
| 6 | 6867 | `_load_pyannote_pipeline` (`_FailingPipeline`) | same — test the failure-fallback path post-migration |

**§1.3.B — Module-stub-assignment sites for retiring pyannote-related symbols** (Shape C; 4 sites):

| # | File:Line | Stub | Migration |
|---|---|---|---|
| 7 | `tests/conftest.py:47` | `_voice_stub._load_pyannote_pipeline = MagicMock(return_value=None)` | RETIRE — function gone post-D3 |
| 8 | `tests/conftest.py:49` | `_voice_stub._voice_diarize_executor = None` | RETIRE — var gone post-D3 |
| 9 | `tests/conftest.py:51-65` | `_get_diarize_executor_cf` + `_shutdown_diarize_executor_cf` stub functions | RETIRE — functions gone post-D3 |
| 10 | `test_pipeline.py:34` | `_vs._load_pyannote_pipeline = MagicMock(return_value=None)` | RETIRE |
| 11 | `test_pipeline.py:36` | `_vs._voice_diarize_executor = None` | RETIRE |
| 12 | `test_pipeline.py:38-52` | `_get_diarize_executor_tp` + `_shutdown_diarize_executor_tp` stub functions | RETIRE |

(Note: §1.3.B rows 7-12 above represent grouped retirements; some are sub-blocks within a single function block. Counted as 6 distinct retirement events.)

**§1.3.C — Dedicated test files that need retirement/repurposing**:

| # | File | Lines | Action |
|---|---|---|---|
| 13 | `tests/test_voice.py:12-74` | full file | RETIRE/REPURPOSE — current tests assert `get_diarize_executor()` singleton + wrapping behavior. Post-D3: rewrite to assert `hw.pyannote_diarize_worker` exists + `_get_subprocess_pyannote` accessor works + pool warm-up at startup. |
| 14 | `tests/test_warmup.py:21-92` | warm-up tests | RETIRE/REPURPOSE — currently tests `_warm_pyannote_via_dedicated_executor`; replace with `hw.get_or_create_pool("pyannote_diarize")` invocation tests at startup. |

**§1.3.D — Direct-call sites from tests** (Shape D, scan for `_voice_mod\.(diarize|_diarize_pyannote)\(`):

Already covered by P0.R6.Y A11 programmatic enforcement (lookbehind regex `(?<!await )_voice_mod\.(embed|identify|diarize|_diarize_ecapa_valley)\(`). P0.R6.Z extends A11 regex to ALSO include `_diarize_pyannote` direct calls if any surface; grep currently shows zero direct `_diarize_pyannote(` test calls (all routes go through public `diarize()` dispatcher).

**Total test infrastructure migration count**: 12 stub/patch retirements + 2 dedicated test files = **14 test sites** for retirement/repurpose at Phase 5.

### §1.4 Cross-spec interactions (Pass-2 grep)

| Spec | Interaction | Status |
|---|---|---|
| P0.R5 | Vendored pyannote fork (`HungryFingerss/pyannote-audio @ 2cee8f3e`) | LOAD-BEARING (subprocess must inherit `from pyannote.audio import Pipeline` cleanly; vendored fork's torchaudio compat patches apply uniformly at install-time per `requirements.txt` git URL; HF_TOKEN auth carries via env var inheritance at subprocess spawn) |
| P0.R6 | AdaFace migration to heavy_worker — SAME infrastructure | EXTENDS (`pyannote_diarize_worker` lands in same `core/heavy_worker.py` module; `_heavy_worker_status` dict extends for `pyannote_diarize` key) |
| P0.R6.X | Whisper migration — SAME pattern | EXTENDS (4th task class joining heavy_worker pool) |
| P0.R6.Y | ECAPA migration | EXTENDS (`get_diarize_executor()` Q2 (a) lock retired; pyannote pipeline call inside `_diarize_pyannote` body migrates to subprocess; `identify()` per-segment calls already-migrated at P0.R6.Y preserve their subprocess dispatch) |
| Session 88 / P2 | `_diarize_pyannote` + `_diarize_ecapa_valley` dispatch logic | LOAD-BEARING (dispatch stays in async `diarize()` body; return-shape contract `[{start_sample, end_sample, speaker_id, speaker_score, speaker_label}]` preserved through subprocess boundary) |
| HF_TOKEN env var | Pyannote model download from HuggingFace | LOAD-BEARING (subprocess inherits env at spawn time per Python `multiprocessing` `spawn` context; verified via P0.R5 vendored speechbrain pattern) |
| pyannote `Annotation` object | Return shape from `pipeline(...)` | **PICKLE-FRAGILE** — pyannote's `Annotation` object is internal type; pickling across subprocess boundary may not work cleanly OR may carry version-skew risk. **Worker MUST serialize to simple `list[tuple[start_secs, end_secs, label]]` BEFORE returning** (LOAD-BEARING architectural decision; Q4 lock candidate) |

### §1.5 Pre-audit refinement banking

**Refinement #1 — `### Pre-audit-quantifier-precision-refined-by-grep` RETIREMENT-SURFACE-AXIS NEW sub-shape candidate**: pre-audit framing said "migrates pyannote pipeline + retires get_diarize_executor()" implying 2 surfaces. Grep verified **5 production surfaces retire** (`_voice_diarize_executor` + `get_diarize_executor` + `shutdown_diarize_executor` + `_pyannote_pipeline` + `_load_pyannote_pipeline`) + **4 pipeline.py call sites** affected (warmup function + 2 call sites + shutdown call) + **14 test sites** retire/repurpose. The "retire X + add Y" framing is structurally distinct from prior axis sub-shapes (COUNT, MECHANISM, MECHANISM-GENERALITY, LAYERED, TASK-COMPLETENESS, SURFACE-CASCADE) — captures the RETIREMENT SURFACE dimension where pre-audit captures the NEW addition but underweights the SCOPE OF WHAT'S BEING REMOVED.

Banking candidate: **RETIREMENT-SURFACE-AXIS** as 7th sub-shape of `### Pre-audit-quantifier-precision-refined-by-grep` doctrine. Auditor adjudication needed.

**Refinement #2 — sub-pattern A `### Phase-0-catches-wrong-premise` NOT applicable**: pre-audit framing was structurally CORRECT (pyannote is heaviest; `get_diarize_executor()` retires; subprocess pool added). Phase 0 confirms; only quantifier precision refined.

---

## §2 Architectural justification refresh

Pre-audit framing was CORRECT on structural premises. Phase 0 grep ADDS:

1. **Pyannote `Annotation` object pickle-fragility** (LOAD-BEARING Q4 candidate): pyannote's `Annotation` return type contains pyannote-internal structures (`Segment`, `Timeline`, label dictionaries). Pickling these across subprocess boundary may fail OR carry version-skew risk between fork commits. Worker MUST serialize to simple list before returning.

2. **HF_TOKEN env propagation across spawn**: pyannote model download requires HF_TOKEN. Python `multiprocessing.get_context("spawn")` inherits env at spawn time. Vendored pyannote fork (P0.R5) downloads from HuggingFace if not cached; first-call subprocess latency includes potential HF download (~30-60s on cold cache). Document in Known Limitations.

3. **RETIREMENT-HEAVY scope** (largest of 4 R6.* sub-cycles): 5 production surfaces retire + 14 test sites retire/repurpose. Largest single retirement event in the heavy-worker arc.

Risk/benefit:

- **Risk**: pickle IPC overhead per call ~0.5-1ms for ~24000-sample audio buffers + return-shape serialization overhead ~0.1-0.5ms for typical 2-5 segments. Acceptable for ~1-3s pyannote inference (<1% overhead).
- **Risk**: subprocess holds pyannote model ~3GB VRAM persistently. After P0.R6+R6.X+R6.Y+R6.Z: ~6.3GB cumulative across 4 worker subprocesses + ~1GB main process = ~7.3GB. Comfortable on Jetson AGX Orin 24GB CUDA budget; tight on dev laptops with 8GB VRAM (acceptable — dev laptop fallback path covered by `DIARIZATION_FALLBACK_ON_ERROR=True` → ECAPA-valley fallback if pyannote subprocess load fails).
- **Risk**: pyannote `Annotation` pickle-fragility (mitigated by Q4 worker-side serialization).
- **Benefit**: complete asyncio-loop-release across 4 heavy models (P0.R6 + R6.X + R6.Y + R6.Z arc closes).
- **Benefit**: `get_diarize_executor()` retirement removes dedicated thread pool — simpler architecture; all heavy CUDA work routes through unified subprocess pool infrastructure.
- **Benefit**: process isolation contains pyannote crashes (pyannote has high crash risk due to torch + CUDA + speechbrain-internal-dependency complexity; subprocess containment is the most-valuable isolation event in the R6.* arc).
- **Benefit**: closes the 4-task scope — heavy-worker arc complete.

---

## §3 D-decision proposal (5 D-decisions)

**D1 (NEW worker function in `core/heavy_worker.py`)**: `pyannote_diarize_worker(audio_bytes: bytes, shape: tuple[int, ...], dtype_name: str, sample_rate: int) -> "list[tuple[float, float, str]] | None"` worker entry point. Deserializes audio buffer + calls subprocess-singleton pyannote `Pipeline.__call__()` + serializes returned `Annotation` to `list[(start_secs, end_secs, label)]` triples via `annotation.itertracks(yield_label=True)` iteration **subprocess-side** + returns serializable list. Mirror of P0.R6 D2 + P0.R6.X D1 + P0.R6.Y D1 shape with the Q4 serialization difference. Returns None on cascading failure (preserves P0.R1 D1 None-return fallback contract; main-process `_diarize_pyannote` falls through to ECAPA-valley fallback per existing `DIARIZATION_FALLBACK_ON_ERROR` logic).

**D2 (subprocess singleton accessor in `core/heavy_worker.py`)**: `_SUBPROCESS_PYANNOTE_PIPELINE: Any | None = None` module-level singleton + `_get_subprocess_pyannote()` accessor with lazy-load on first call. Replicates `_load_pyannote_pipeline()` body (P0.R5 vendored fork) including HF_TOKEN auth + `Pipeline.to(torch.device("cuda"))`. ~30-60s first-call latency if cold cache (HF download); ~2-3s if cached (model load + CUDA context init). Same pattern as P0.R6 D2 + P0.R6.X D2 + P0.R6.Y D2.

**D3 (`core/voice.py` retirement + `_diarize_pyannote()` body migration)**:

Three sub-decisions:

**D3.a — Retirements** (5 surfaces deleted from `core/voice.py`):
- Delete `_voice_diarize_executor` module-level var (line 48)
- Delete `get_diarize_executor()` function (lines 51-59)
- Delete `shutdown_diarize_executor()` function (lines 62-67)
- Delete `_pyannote_pipeline` module-level var (line 247)
- Delete `_load_pyannote_pipeline()` function (lines 264-314)

**D3.b — `_diarize_pyannote()` body migration** (lines 345 + 371-375 + adapt 386 iteration):

```python
# BEFORE (lines 344-375)
global _diarize_fallback_count
pipeline = _load_pyannote_pipeline()
if pipeline is None:
    # ... fallback logic ...
    return await _diarize_ecapa_valley(...)
if len(audio) == 0:
    return []
waveform = torch.from_numpy(audio.astype(np.float32)).unsqueeze(0)
if torch.cuda.is_available():
    waveform = waveform.to(torch.device("cuda"))
loop = asyncio.get_running_loop()
try:
    annotation = await loop.run_in_executor(
        get_diarize_executor(),
        pipeline,
        {"waveform": waveform, "sample_rate": sample_rate},
    )
except Exception as e:
    # ... fallback logic ...
    return await _diarize_ecapa_valley(...)
# ... iterate annotation.itertracks ...

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
    # Worker returned None — pyannote pipeline load failure
    if DIARIZATION_FALLBACK_ON_ERROR:
        _diarize_fallback_count += 1
        print(f"[Voice] WARN diarize fallback (load-fail) — "
              f"pyannote unavailable, using ecapa_valley "
              f"(fallback #{_diarize_fallback_count})")
        return await _diarize_ecapa_valley(audio, voice_gallery, threshold, sample_rate)
    return []

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
- Delete `_warm_pyannote_via_dedicated_executor` function (lines 6183-6217)
- Replace line 6219 call site with `hw.get_or_create_pool("pyannote_diarize")` + `set_heavy_worker_status("pyannote_diarize", "healthy")`
- Delete line 8383 `voice_mod.shutdown_diarize_executor()` call (subprocess pool handled via `hw.shutdown_all_pools(wait=True)` already in shutdown finally)

**D4 (health observability + startup wiring extension)**: Reuses P0.R6 D4 `_heavy_worker_status` dict. Add `"pyannote_diarize"` key with initial "healthy" status. Startup pool warm-up lands immediately after ECAPA pool warm-up (preserves 4-pool ORDERING INVARIANT before vision task spawn).

**D5 (test surface retirement/repurpose)**: 14 test sites per §1.3:
- 6 Shape B patch.object sites in test_pipeline.py (lines 6614/6650/6693/6732/6773/6867): test target migrates from `_load_pyannote_pipeline` (gone) to `hw.pyannote_diarize_worker` OR `hw._get_subprocess_pyannote` OR a pool-level mock
- 6 Shape C stub-assignment sites in conftest.py + test_pipeline.py: delete `_load_pyannote_pipeline` + `_voice_diarize_executor` + `get_diarize_executor` + `shutdown_diarize_executor` stubs
- 2 dedicated test files (tests/test_voice.py + tests/test_warmup.py): retire/repurpose — `test_voice.py` rewrites singleton-behavior tests to subprocess-pool tests; `test_warmup.py` rewrites warmup tests to `hw.get_or_create_pool("pyannote_diarize")` warmup tests

---

## §4 Anchor count proposal (Q5)

**Mid 11 INCLUSIVE ±15% band → [9.35, 12.65] → ON-TARGET = 10, 11, or 12 anchors**:

- **A1**: `pyannote_diarize_worker` function exists in `core/heavy_worker.py` (source-inspection)
- **A2**: `_SUBPROCESS_PYANNOTE_PIPELINE` singleton + `_get_subprocess_pyannote()` accessor present
- **A3**: `core/voice.py::_diarize_pyannote()` body AST shows `hw.run_heavy("pyannote_diarize", ...)` Call node (positive)
- **A4**: `core/voice.py::_diarize_pyannote()` body AST shows `_load_pyannote_pipeline()` direct call is GONE AND `run_in_executor(get_diarize_executor(), ...)` pattern is GONE (inverse)
- **A5**: `core/voice.py` source AST shows `get_diarize_executor` + `shutdown_diarize_executor` + `_voice_diarize_executor` + `_pyannote_pipeline` + `_load_pyannote_pipeline` are ALL GONE (5-prong retirement inverse check)
- **A6**: `pipeline.py` source AST shows `_warm_pyannote_via_dedicated_executor` function definition + `shutdown_diarize_executor` call + `_voice_mod.get_diarize_executor` references are ALL GONE (retirement inverse check)
- **A7**: Worker returns serializable `list[tuple[float, float, str]]` shape (NOT pyannote `Annotation`); main-process iteration adapts (behavioral test with mocked worker returning fixture list)
- **A8**: HealthSnapshot reports `"pyannote_diarize"` in `_heavy_worker_status` dict (behavioral)
- **A9**: Startup pool warm-up AST line-order check — `hw.get_or_create_pool("pyannote_diarize")` lands BEFORE vision task spawn AND AFTER AdaFace + Whisper + ECAPA pool warm-ups (4-pool ordering invariant)
- **A10**: (EXTENDED from P0.R6.Y A10) Programmatic test-patch enforcement: regex scan extended to cover `pyannote_diarize_worker` + `_get_subprocess_pyannote` patches (Shape A/B/C across `tests/**/*.py` + `test_pipeline.py` + `tests/conftest.py`)
- **A11**: (EXTENDED from P0.R6.Y A11) Programmatic direct-call enforcement: regex `(?<!await )_voice_mod\.(embed|identify|diarize|_diarize_ecapa_valley|_diarize_pyannote)\(` includes `_diarize_pyannote` direct calls

**Closure-projection band table**:

| closure-actual | overage vs mid 11 | band | doctrine outcome |
|---|---|---|---|
| 9 | −18.2% | SLIGHT-DRIFT-DOWN (within ±30%) | `### Phase-0-granular-decomposition` HOLDS at 21 supporting |
| 10 | −9.1% | ON-TARGET | `### Phase-0-granular-decomposition` 21 → 22 supporting |
| 11 | 0% | ON-TARGET exact mid | `### Phase-0-granular-decomposition` 21 → 22 supporting + 13th consecutive 0% streak (per `Doctrine-prediction-precision-improving-over-arc`) |
| 12 | +9.1% | ON-TARGET | `### Phase-0-granular-decomposition` 21 → 22 supporting |
| 13 | +18.2% | SLIGHT-DRIFT-UP (within ±30%) | `### Phase-0-granular-decomposition` HOLDS at 21 supporting |
| ≥14 OR ≤8 | beyond ±30% | FALSIFICATION TRIGGER | doctrine demotes back to architect-memory + reasoning audit |

---

## §5 OUT-OF-SCOPE classification

1. **Whisper / ECAPA / AdaFace worker pool re-tuning** — prior cycles' patterns preserved; P0.R6.Z does NOT modify their behavior.
2. **Pyannote model version bump / parameter tuning** — `speaker-diarization-3.1` model stays; subprocess inherits via vendored fork.
3. **`DIARIZATION_FALLBACK_ON_ERROR=True` semantics** — preserved as-is. Pyannote worker failure → ECAPA-valley fallback at main process.
4. **`get_diarize_stats()` observability function in `core/voice.py`** — `_diarize_fallback_count` counter usage stays; only the dedicated thread pool retires.
5. **TTS worker migration** — separate concern; Kokoro / Piper TTS NOT in P0.R6.Z scope.
6. **Multi-process inference parallelism** — `max_workers=1` per Q7 lean (matches P0.R6 + R6.X + R6.Y default).

---

## §6 Locked-down discipline counters

**`### Pre-audit-quantifier-precision-refined-by-grep` doctrine instance enumeration** (post-P0.R6.Y closure baseline; CLAUDE.md canonical at lines 646-770):

- 1st: P0.B3 D-D Phase 0 (COUNT-axis)
- 2nd: P0.R2 §2.6(b) Phase 0 (MECHANISM-AXIS)
- 3rd: P0.R4 Q3 Phase 0 (MECHANISM-GENERALITY-AXIS)
- 4th: P0.R5 Phase 0 (LAYERED-AXIS 3-axis)
- 5th: P0.R6 Phase 0 (LAYERED-AXIS continuation 2-axis)
- 6th: P0.R6.X Phase 0 (TASK-COMPLETENESS-AXIS)
- 7th: P0.R6.Y Phase 0 (SURFACE-CASCADE-AXIS)
- **8th candidate**: P0.R6.Z Phase 0 (RETIREMENT-SURFACE-AXIS — NEW sub-shape; auditor adjudication needed at Phase 0 verdict)

Per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine: auditor DILIGENT Pass-2 grep at Plan v1 §1 will independently verify §1.1 9-row + §1.2 4-row + §1.3 14-site enumeration. Any drift → Plan v1 PI #1 absorption per Option α pattern.

Per `feedback_pass_2_grep_deferral_pattern.md` (banked at P0.R6.Y closure-audit): NO "developer Phase N surfaces enumeration" framings in this Phase 0 — all sites enumerated upfront with explicit per-site disposition.

---

## §7 Q-questions for adjudication

**Q1 (RETIREMENT-vs-DEPRECATION disposition for `core/voice.py` retired symbols)**:
After D3.a retirement, callers of `get_diarize_executor` / `shutdown_diarize_executor` / `_load_pyannote_pipeline` will get `AttributeError`.

- Option (a): Hard delete (cleanest). Callers MUST migrate at this cycle.
- Option (b): Stub functions left in place returning errors with explicit deprecation message.

**Architect lean: (a)** — Hard delete. P0.R6.Z is the final retirement cycle; deprecation stubs would carry technical debt. All 4 callers (pipeline.py + tests) are migrated in this cycle's Phase 5.

**Q2 (Pyannote `Annotation` return shape — pickle-fragility mitigation)**:
Pyannote's `Annotation` object contains internal `Segment` + `Timeline` + label dictionaries.

- Option (a): Worker serializes to `list[tuple[start_secs, end_secs, label]]` BEFORE returning; main process iterates simple list. (LOAD-BEARING — avoids pickle compatibility issues)
- Option (b): Worker pickles `Annotation` directly; main process imports pyannote types to iterate.

**Architect lean: (a)** — Option (b) requires main process to keep `from pyannote.audio import Pipeline` import alive (defeats some isolation benefit). Option (a) is cleaner + version-stable. LOAD-BEARING.

**Q3 (IPC payload shape — audio buffer)**:
Per P0.R6.X + P0.R6.Y precedent: explicit tuple `(bytes, shape, dtype_name, sample_rate)`.

**Architect lean: (a)** — matches precedent.

**Q4 (Worker return shape)**:
Per Q2 (a) lock: `list[tuple[float, float, str]]` of (start_secs, end_secs, label) triples.

**Architect lean: per Q2 (a) decision** — same locked choice.

**Q5 (Eager vs lazy model load in subprocess)**:
Pyannote model load ~30-60s on cold HF cache; ~2-3s if cached.

- Option (a): Eager load at subprocess startup (foreground ~3-60s latency, no first-call penalty)
- Option (b): Lazy load on first call (no startup penalty; ~3-60s first-call latency on cold cache)

**Architect lean: (b)** — matches P0.R6 + R6.X + R6.Y precedent. First-call latency only affects first diarize after subprocess spawn (acceptable; multi-speaker scenarios are infrequent).

**Q6 (CUDA spawn requirement + HF_TOKEN propagation)**:
Same as P0.R6 Q6 (a) — explicit `mp.get_context("spawn")`. HF_TOKEN env var inherits at spawn time per Python `multiprocessing` semantics. No special handling needed.

**Q7 (Worker max_workers)**:
Single worker per task class. Pyannote inference is sequential within a session.

**Architect lean: max_workers=1** (matches P0.R6 + R6.X + R6.Y).

**Q8 (`tests/test_voice.py` + `tests/test_warmup.py` retirement disposition)**:
Both files have substantial tests that ONLY exist to assert pre-P0.R6.Z dedicated-thread-pool behavior. After D3.a retirement, these tests become dead.

- Option (a): Delete the obsolete tests entirely + add subprocess-pool equivalents in `tests/test_p0_r6_z_pyannote_worker.py` (the new anchor test file).
- Option (b): Repurpose the obsolete tests to assert NEW subprocess-pool behavior.

**Architect lean: (a)** — Cleaner. Subprocess-pool tests belong with the new anchor file; obsolete tests can be deleted. Bank as Phase 5 task: delete `tests/test_voice.py` get_diarize_executor tests + delete `tests/test_warmup.py` _warm_pyannote_via_dedicated_executor tests (preserve non-pyannote-pool tests in same files if any).

**Q9 (Pyannote subprocess crash recovery semantic)**:
If pyannote worker subprocess crashes mid-session (CUDA OOM, segfault, etc.), `hw.run_heavy` returns from `concurrent.futures.ProcessPoolExecutor.submit().result()` with a `BrokenProcessPool` exception.

- Option (a): Catch `BrokenProcessPool` + return None → main-process `_diarize_pyannote` falls through to ECAPA-valley fallback (preserves existing `DIARIZATION_FALLBACK_ON_ERROR` contract)
- Option (b): Catch + restart pool + retry once.

**Architect lean: (a)** — matches P0.R1 D1 None-return fallback contract preserved through R6.* arc. Pool auto-restart adds complexity; restart on next call is the natural recovery (new subprocess spawns on next `hw.run_heavy("pyannote_diarize", ...)` invocation).

---

## §8 Doctrine-firing projections at closure

If P0.R6.Z closes cleanly with closure-actual = 11 anchors at exact mid:

- `### Phase-0-granular-decomposition-enables-accurate-estimates` 21 → 22 supporting
- 13th consecutive 0% exact-mid streak extends `Doctrine-prediction-precision-improving-over-arc` sub-observation (12 was streak-interrupted at P0.R6.Y +10%; P0.R6.Z exact-mid = streak rebuild from 1)
- `### Pre-audit-quantifier-precision-refined-by-grep` 7 → 8 instances (RETIREMENT-SURFACE-AXIS NEW sub-shape — pending auditor ratification)
- `### Phase-0-catches-wrong-premise` STAYS at 13 (premise correct this cycle)
- `### Zero-precision-items-at-auditor-review` 23 → 25 (Phase 0 + Plan v1 if cycle clears cleanly)
- OPTIONAL-Plan-v2 sub-rule track record 10 → 11 proof cases (if 3-artifact cycle ships)
- `### Architect-reads-production-code-before-sign-off` 20 → 21 at closure-audit (3rd-cycle self-sustaining adoption per `Implicit-doctrine-firings-not-narrative-tracked` operational rule)
- Strict-industry-standard mode 80 → 83 applications + 23 → 24 closures
- Spec-first review cycle 89 → 92-for-92 at closure
- `### Grep-baseline-before-drafting` 47 → 50 instances
- Cross-cycle-handoff transparency 53 → 56 successful
- Spec-time grep-verification 57 → 60 instances
- `### Twin-filename-pitfall-prevention` 22 → 23 preventive events
- Auditor-Q5-estimates-trail-grep 27 → 28 banked closures
- Deferred-canary strategy 25 → 26 applications

---

## §9 Architect-handoff items for auditor verdict

1. **Pass-2 grep verification** (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine): independent re-grep §1.1 9-row + §1.2 4-row + §1.3 14-site + §1.4 8-row cross-spec table. **Per `feedback_pass_2_grep_deferral_pattern.md` LOCKED at P0.R6.Y closure-audit**: NO deferral framings in this Phase 0; all sites enumerated upfront. If auditor surfaces additional sites OR cross-spec interactions, lock as Plan v1 PI #1 absorption per Option α pattern.

2. **Q1-Q9 adjudication**: confirm architect leans OR substitute. Q1 (hard-delete) + Q2 (worker serializes Annotation to list) + Q8 (delete obsolete test files cleanly) + Q9 (BrokenProcessPool → fallback) are LOAD-BEARING; Q3-Q7 are implementation refinements per prior R6.* precedent.

3. **Anchor count adjudication**: confirm mid 11 INCLUSIVE ±15% band [9.35, 12.65] OR substitute. P0.R6.Z is the most-retirement-heavy cycle; 11 anchors covers worker + singleton + body migration + 5-prong retirement inverse + return-shape behavioral + ordering + 2 programmatic enforcement extensions.

4. **RETIREMENT-SURFACE-AXIS NEW sub-shape adjudication**: confirm 8th instance of `### Pre-audit-quantifier-precision-refined-by-grep` qualifies as NEW sub-shape per the doctrine's operational-rule-4 ("Sub-shape taxonomy grows when a genuinely NEW failure-mode dimension surfaces") OR substitute as continuation of existing axis. The RETIREMENT-SURFACE dimension captures pre-audit's "retire X + add Y" framing under-weighting the SCOPE OF WHAT'S BEING REMOVED — structurally distinct from prior 7 sub-shapes.

5. **Doctrine-firing projections**: confirm §8 enumeration matches discipline track records.

---

**End of Phase 0 audit.** Ready for auditor verdict.
