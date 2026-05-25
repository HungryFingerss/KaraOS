# P0.R6.X — Whisper migration to ProcessPoolExecutor worker (Plan v1)

**Date**: 2026-05-24
**Author**: architect (Claude)
**Phase 0 verdict**: ACCEPTED with 0 BLOCKING PIs + 1 non-blocking observation (auditor Phase 0 verdict 2026-05-24); 8/8 Q-questions ratified per architect leans
**Cycle shape**: SMALL-MEDIUM band, 3-artifact OPTIONAL-Plan-v2 path candidate (10th proof case if cycle clears Plan v1 cleanly)

---

## §1 Pass-2 grep verification (architect-side, per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval`)

### §1.1 Whisper inference enumeration (Phase 0 §1.1 LOCKED; re-verified at Plan v1 draft time)

| # | Surface | File:Line | Sync/Async | Wrapped? | Migrate? |
|---|---|---|---|---|---|
| 1 | `_load_whisper()` lazy loader | `core/audio.py:186` | sync (lazy) | n/a | n/a (subprocess inherits its own loader) |
| 2 | `_load_whisper()` preload site | `core/audio.py:327` | sync | n/a | n/a (boot warmup; not migration target) |
| 3 | `_load_whisper()` in transcribe() body | `core/audio.py:506` | sync | n/a | n/a (inside transcribe; covered transitively — REMOVED at D3) |
| 4 | **`model.transcribe(...)` LOAD-BEARING inference** | **`core/audio.py:507`** | **sync** | **n/a** | **YES — D3 migration target** |
| 5 | `transcribe` definition | `core/audio.py:493` (def) | sync → async | n/a | YES — D3 signature change (`def` → `async def`) |
| 6 | `transcribe` caller inside `listen_and_transcribe` | `core/audio.py:620` | async | `run_in_executor` | YES — D3 caller migration (`await loop.run_in_executor(None, transcribe, audio)` → `await transcribe(audio)`) |
| 7 | `transcribe` direct caller (multi-speaker diarize) | `pipeline.py:7482` | async | `run_in_executor` | YES — D3 caller migration (same shape) |

**Pass-2 verification status**: identical to Phase 0 §1.1; auditor's independent re-grep at Phase 0 verdict confirmed all 6 architect-claimed rows match production code exactly. Plan v1 ratifies 7-row enumeration (added `transcribe` definition row at #5 + caller migration rows at #6+#7 with explicit migration shape).

### §1.2 Cross-spec interactions (Phase 0 §1.2 LOCKED; re-verified at Plan v1 draft time)

| Spec | Interaction | Status |
|---|---|---|
| P0.R1 | ONNX session.run() wrap for AdaFace — different model class | NO conflict (independent path) |
| P0.R2 | Provider state machine for AdaFace/buffalo_l CPU fallback | NO conflict (independent path) |
| P0.R5 | Pyannote/speechbrain vendoring — torchaudio compat patches | LOAD-BEARING (subprocess must inherit `from faster_whisper import WhisperModel` cleanly; torchaudio compat patches apply uniformly at install-time per `requirements.txt` git URL; no subprocess-side action needed; verified at P0.R5 closure 2026-05-23) |
| P0.R6 | AdaFace migration to heavy_worker — SAME infrastructure | EXTENDS (`whisper_transcribe_worker` lands in same `core/heavy_worker.py` module; `_heavy_worker_status` dict already designed for multi-task scaling per D4) |
| P0.S7.5.2 D4 | 1-word STT artifact filter in `transcribe()` | LOAD-BEARING (filter chain stays in main process per Q2 (b) lock) |
| P0.S7.5.2 D5 | Smart-Turn debounce widening in `record_until_silence` | NO conflict (record path unchanged; only transcribe migrated) |
| P0.0.7 H1 | `audio_in` event emission via `safe_emit_sync` in `listen_and_transcribe` | NO conflict (emission happens in main process AFTER transcribe; `text` argument changes from sync-return to async-await but content unchanged) |
| P0.R6 D5 | Startup pool warm-up BEFORE vision task spawn | EXTENDS (whisper_transcribe pool warm-up must land BEFORE `preload_models()` body's `_load_whisper()` call — see D4 ordering invariant below) |

**Pass-2 verification status**: identical to Phase 0 §1.2; cross-spec orthogonality verified clean.

### §1.3 Caller migration enumeration (LOAD-BEARING — production + test surfaces)

| # | Caller | File:Line | Current shape | Post-D3 shape | Scope |
|---|---|---|---|---|---|
| 1 | `listen_and_transcribe` body | `core/audio.py:620` | `text, lang = await loop.run_in_executor(None, transcribe, audio)` | `text, lang = await transcribe(audio)` | PRODUCTION (in-scope) |
| 2 | multi-speaker diarize transcription | `pipeline.py:7482` | `_t, _ = await _ev_loop.run_in_executor(None, transcribe, _a)` | `_t, _ = await transcribe(_a)` | PRODUCTION (in-scope) |
| 3 | conftest stub fixture | `tests/conftest.py:80-81` | `model = _audio_stub._load_whisper(); segments, _ = model.transcribe(audio)` | unchanged (stub uses its own MagicMock model) | TEST (test-only; stub doesn't need migration since it doesn't call production `transcribe()`) |
| 4 | executor unit test | `test_executor.py:259-279` | `result = await loop.run_in_executor(None, audio_mod.transcribe, fake_audio)` | `result = await audio_mod.transcribe(fake_audio)` | TEST (in-scope migration — must adapt to async signature) |
| 5 | test_pipeline stub | `test_pipeline.py:68-69` | `model = _as._load_whisper(); segments, _ = model.transcribe(audio)` | unchanged (stub uses its own MagicMock model) | TEST (test-only; stub doesn't migrate) |

**Production caller migration count**: 2 sites (`core/audio.py:620` + `pipeline.py:7482`).

**Test surface migration count**: 1 site (`test_executor.py:259-279` — must adapt to async). Stubs at `tests/conftest.py` + `test_pipeline.py` use their own MagicMock model (independent of production `transcribe()`); no migration needed.

### §1.4 Doctrine enumeration reconciliation (Path C grep-verify per auditor's non-blocking observation #1)

Auditor's Phase 0 verdict flagged a doctrine enumeration discrepancy for `### Pre-audit-quantifier-precision-refined-by-grep`. Path C grep-verify against CLAUDE.md doctrine body at lines 646-770 (LOCKED at P0.R6 closure-audit per the in-line banking note at lines 763-770):

| Position | CLAUDE.md canonical (auditor-sourced at P0.R6 closure) | Architect's §6 in P0.R6.X Phase 0 | Auditor's P0.R6.X verdict working-memory |
|---|---|---|---|
| 1st | **P0.B3 D-D Phase 0 (2026-05-21)** — COUNT-axis | P0.B3 D-D COUNT-axis ✓ | P0.R1 COUNT-AXIS ✗ (drift) |
| 2nd | **P0.R2 §2.6(b) Phase 0 (2026-05-23)** — MECHANISM-AXIS | P0.R2 MECHANISM-AXIS ✓ | P0.R2 SCOPE-AXIS ✗ (axis label drift) |
| 3rd | **P0.R4 Q3 Phase 0 (2026-05-23)** — MECHANISM-GENERALITY-AXIS | matches ✓ | matches ✓ |
| 4th | **P0.R5 Phase 0 (2026-05-23)** — LAYERED-AXIS 3-axis | matches ✓ | matches ✓ |
| 5th | **P0.R6 Phase 0 (2026-05-24)** — LAYERED-AXIS continuation 2-axis | matches ✓ | matches ✓ |

**Disposition: (β) per auditor's option-list, with actor-side reversed** — auditor's P0.R6.X verdict working-memory has enumeration drift; CLAUDE.md canonical text (locked verbatim at P0.R6 closure-audit per the auditor's own Phase 0 verdict text) is authoritative. The drift occurred between P0.R6 closure-audit (canonical text locked) and P0.R6.X Phase 0 verdict (auditor's working memory referenced an earlier draft that didn't include P0.B3 D-D).

**Banking: `Per-artifact-arithmetic-drift-survives-grep-baseline` 4 → 5 instance AT AUDITOR-SIDE.** Same family-shape as prior 4 architect-side instances (P0.B2 + P0.S9 v1+v2 + P0.R1 v2) but the catching actor is reversed — architect's Path C grep-verify at Plan v1 drafting catches auditor's drift. 5-instance candidacy for elevation candidacy unchanged (cross-actor banking; family-shape continuity preserved); future closure-audit may elevate to numbered observation under `### Convention-drift-on-discipline-counts` parent doctrine.

**Resolution at Plan v1**: 6th instance of `### Pre-audit-quantifier-precision-refined-by-grep` for P0.R6.X locks correctly as TASK-COMPLETENESS-AXIS continuation. Doctrine track record stays at canonical 5 prior + 1 P0.R6.X = 6 instances; no off-by-one inflation.

---

## §2 D-decision spec (4 D-decisions, locked from Phase 0; Q1-Q8 LOCKED per auditor verdict)

### §2.1 D1 — `whisper_transcribe_worker` in `core/heavy_worker.py`

**LOCKED**. New worker entry point at module-scope. Mirror of P0.R6 D2 `adaface_embed_worker` shape (per `### Spec-contracts-not-implementations` discipline — contract is "Whisper inference in worker subprocess returning (raw_text, language)").

Signature:

```python
def whisper_transcribe_worker(
    audio_bytes: bytes,
    shape: "tuple[int, ...]",
    dtype_name: str,
    language: str,
) -> "tuple[str, str]":
    """Worker entry point: deserializes audio buffer + transcribes via
    subprocess-singleton WhisperModel + returns (raw_text, language).

    Filter chain (non-ASCII, char-run, word-repetition, phrase-repetition,
    1-word artifact) stays in main process per Plan v1 Q2 (b) lock.

    Q3 (a) lock: explicit tuple (bytes, shape, dtype_name) for IPC payload
    shape — matches P0.R6 D2 adaface_embed_worker pattern.

    Q4 (b) lock: returns (raw_text, language) — main process applies
    filter chain AFTER worker returns.

    Q5 (b) lock: lazy-load WhisperModel on first call via
    _get_subprocess_whisper() accessor.
    """
    import numpy as np
    audio_array = np.frombuffer(audio_bytes, dtype=dtype_name).reshape(shape)
    model = _get_subprocess_whisper()
    if model is None:
        return ("", language)
    segments, _ = model.transcribe(
        audio_array,
        language=language,
        beam_size=5,
        vad_filter=False,
        vad_parameters={"min_silence_duration_ms": 200},
        condition_on_previous_text=False,
        no_speech_threshold=0.7,
        compression_ratio_threshold=2.4,
        log_prob_threshold=-1.5,
        temperature=0.0,
        task="transcribe",
    )
    segments_list = list(segments)
    good = [s for s in segments_list if s.no_speech_prob < 0.6 and s.avg_logprob > -1.5]
    if not good:
        candidates = [s for s in segments_list if s.no_speech_prob < 0.4]
        if candidates:
            good = [min(candidates, key=lambda s: s.no_speech_prob)]
        else:
            return ("", language)
    raw_text = " ".join(s.text for s in good).strip()
    return (raw_text, language)
```

**Subprocess-side segment-filtering (no_speech_prob + avg_logprob thresholds + "filtered" empty-return)** is part of the worker because it operates on Whisper's segment objects (which contain numpy arrays + complex metadata). Pickling segments across subprocess boundary would be more expensive than running thresholds subprocess-side. **Main-process-side filter chain** (non-ASCII / char-run / word-repetition / phrase-repetition / 1-word artifact) operates on already-joined `str` text — pure-Python regex, cheap to run main-side, dodges import cost of `core.config` (STT_KNOWN_IMPERATIVES) in every worker subprocess.

### §2.2 D2 — `_SUBPROCESS_WHISPER_MODEL` singleton + `_get_subprocess_whisper()` accessor in `core/heavy_worker.py`

**LOCKED**. Mirror of P0.R6 D2 `_SUBPROCESS_EMBEDDER` + `_get_subprocess_embedder()` accessor pattern (developer-improves-on-spec absorbed at P0.R6 D2 implementation: module-level singleton preserves contract via spirit-preserving alternative when API surface doesn't expose `get_global()` accessor).

Signature:

```python
_SUBPROCESS_WHISPER_MODEL: "Any | None" = None


def _get_subprocess_whisper():
    """Returns subprocess-scoped WhisperModel singleton.

    Lazy-loads on first call via faster_whisper.WhisperModel(...).
    First-call latency ~3-5s (model load from disk + CUDA context init);
    subsequent calls are O(1) lookup.

    Q5 (b) lock: lazy-load on first call matches main-process pattern
    (core/audio.py:_load_whisper); first-call latency only affects first
    transcribe call after subprocess spawn (acceptable cost).

    P0.R1 D1 None-return fallback contract preserved: returns None on
    cascading CUDA + CPU EP failure → callers (worker entry point) treat
    as transcribe-failure (empty string return).
    """
    global _SUBPROCESS_WHISPER_MODEL
    if _SUBPROCESS_WHISPER_MODEL is None:
        try:
            from faster_whisper import WhisperModel
            _SUBPROCESS_WHISPER_MODEL = WhisperModel(
                "large-v3-turbo",
                device="cuda",
                compute_type="float16",
            )
        except Exception:  # OPTIONAL: load failure → None propagates
            return None
    return _SUBPROCESS_WHISPER_MODEL
```

Subprocess-scoped (each subprocess maintains its own singleton; main process never holds this reference). Cleanup happens via `shutdown_all_pools(wait=True)` which terminates worker subprocesses cleanly.

### §2.3 D3 — `core/audio.py::transcribe()` body migration + signature change

**LOCKED — sync → async signature change per Q1 (a)**. Two parts: (a) signature change from `def` to `async def`; (b) body inference block replacement.

**Part (a) — signature change**:

```python
# BEFORE
def transcribe(audio: np.ndarray) -> tuple[str, str]:
    """Transcribe audio using faster-whisper. English only. ..."""

# AFTER
async def transcribe(audio: np.ndarray) -> tuple[str, str]:
    """Transcribe audio using faster-whisper via worker subprocess. ..."""
```

**Part (b) — body migration** (replaces lines 504-519):

```python
# BEFORE (lines 504-519)
import time as _time
_t0 = _time.perf_counter()
model = _load_whisper()
segments, _ = model.transcribe(
    audio,
    language=SPEAKER_LANGUAGES[0],
    beam_size=5,
    # ... other Whisper params ...
)
segments_list = list(segments)

good = [s for s in segments_list if s.no_speech_prob < 0.6 and s.avg_logprob > -1.5]
if not good:
    candidates = [s for s in segments_list if s.no_speech_prob < 0.4]
    if candidates:
        good = [min(candidates, key=lambda s: s.no_speech_prob)]
    else:
        print("[Audio] STT: (filtered)")
        return "", "en"

text = " ".join(s.text for s in good).strip()

# AFTER (replaces lines 504-519)
import time as _time
import core.heavy_worker as hw
_t0 = _time.perf_counter()
text, _ = await hw.run_heavy(
    "whisper_transcribe",
    hw.whisper_transcribe_worker,
    audio.tobytes(),
    audio.shape,
    audio.dtype.name,
    language=SPEAKER_LANGUAGES[0],
)
if not text:
    print("[Audio] STT: (filtered)")
    return "", "en"
```

Filter chain at lines 533-588 (non-ASCII / char-run / word-repetition / phrase-repetition / 1-word artifact) STAYS unchanged — runs AFTER worker returns text.

**Caller migration (2 production + 1 test sites per §1.3)**:

```python
# core/audio.py:620 (inside listen_and_transcribe body)
# BEFORE
text, lang = await loop.run_in_executor(None, transcribe, audio)
# AFTER
text, lang = await transcribe(audio)

# pipeline.py:7482 (multi-speaker diarize path)
# BEFORE
_t, _ = await _ev_loop.run_in_executor(None, transcribe, _a)
# AFTER
_t, _ = await transcribe(_a)

# test_executor.py:259-279 (async unit test)
# BEFORE
result = await loop.run_in_executor(None, audio_mod.transcribe, fake_audio)
# AFTER
result = await audio_mod.transcribe(fake_audio)
```

### §2.4 D4 — health observability + startup wiring extension

**LOCKED**. Reuses P0.R6 D4 `_heavy_worker_status: dict[str, str]` infrastructure. P0.R6 D4 already designed for multi-task scaling (key per task_name); P0.R6.X just adds a new key.

**Health snapshot extension**: `_heavy_worker_status` dict at startup gains `"whisper_transcribe": "healthy"` entry. `format_health_line` conditional `heavy_workers=degraded` emit already covers multi-task case (fires when ANY pool != healthy). No new format-line code needed.

**Startup wiring extension** in `pipeline.py::run()`:

```python
# BEFORE (post-P0.R6 closure shape)
import core.heavy_worker as hw
hw.get_or_create_pool("adaface_embed")
_pipeline_state_store.set_heavy_worker_status("adaface_embed", "healthy")
# vision task spawn...
_vision_task = asyncio.create_task(_background_vision_loop(...))

# AFTER (P0.R6.X)
import core.heavy_worker as hw
hw.get_or_create_pool("adaface_embed")
_pipeline_state_store.set_heavy_worker_status("adaface_embed", "healthy")
hw.get_or_create_pool("whisper_transcribe")
_pipeline_state_store.set_heavy_worker_status("whisper_transcribe", "healthy")
# vision task spawn (unchanged)...
_vision_task = asyncio.create_task(_background_vision_loop(...))
```

**ORDERING INVARIANT**: whisper_transcribe pool warm-up MUST land BEFORE `preload_models()` body's `_load_whisper()` call AND BEFORE pipeline's first conversation cycle. Specifically: BEFORE the vision task spawn line (which kicks off background vision + KAIROS loops that may indirectly trigger STT). AdaFace pool warm-up at the existing P0.R6 site is the natural anchor; whisper_transcribe warm-up immediately follows.

**Shutdown unchanged**: P0.R6 D5 `hw.shutdown_all_pools(wait=True)` already terminates ALL pools (including whisper_transcribe) cleanly.

### §2.5 Deliberate-regression scenarios (per `### Induction-surfaces-invariant-gaps` doctrine)

5 scenarios proving each anchor catches its targeted regression:

| Revert | Expected anchor fire | Anchor catches |
|---|---|---|
| (a) Delete `whisper_transcribe_worker` from `core/heavy_worker.py` | A1 (function-existence source-inspection) | Worker function gone |
| (b) Replace `_get_subprocess_whisper()` body with `return None` unconditionally | A2 (subprocess singleton accessor + lazy-init shape) | Singleton accessor broken |
| (c) Revert `transcribe()` body to `model.transcribe(audio, ...)` direct call (skip worker dispatch) | A3 + A4 (AST positive `hw.run_heavy` Call node + inverse missing-`model.transcribe` check) | Migration regressed; old sync code path restored |
| (d) Remove filter chain (lines 533-588) from `transcribe()` | A5 (filter chain regression — hallucination text passes through unfiltered) | Filter chain location regression (Q2 (b) violation) |
| (e) Drop `hw.get_or_create_pool("whisper_transcribe")` from `pipeline.py::run()` startup | A6 + A7 (health snapshot missing whisper_transcribe key + AST line-order regression) | Pool warm-up regressed |

5/5 deliberate-regression coverage of the 7 logical anchors. A4 + A7 also serve as inverse / line-order regression guards (mirror of P0.R6 A4 4-site enforcement + AST line-order pattern).

---

## §3 Logical anchor lock (Q5 LOCK = 7 anchors at EXACT MID)

Per auditor Phase 0 verdict §4 Q5 ratification: **7 anchors at exact mid 7 INCLUSIVE ±15% band [5.95, 8.05]**.

| # | Anchor | Surface | Coverage |
|---|---|---|---|
| A1 | `whisper_transcribe_worker` function exists in `core/heavy_worker.py` | Source-inspection (function definition) | D1 |
| A2 | `_SUBPROCESS_WHISPER_MODEL` singleton + `_get_subprocess_whisper()` accessor present | Source-inspection (module-level var + accessor) | D2 |
| A3 | `core/audio.py::transcribe()` AST shows `hw.run_heavy("whisper_transcribe", ...)` Call node | AST positive check | D3 part (b) |
| A4 | `core/audio.py::transcribe()` AST shows `model.transcribe(audio, ...)` DIRECT call is GONE | AST inverse check (old sync inference must NOT remain) | D3 part (b) |
| A5 | Whisper transcribe filter chain still applies AFTER worker returns text | Behavioral test with mocked worker returning hallucination shapes | D3 part (b) filter-chain location regression guard |
| A6 | HealthSnapshot reports `"whisper_transcribe"` in `_heavy_worker_status` dict | Behavioral test (gather snapshot post-init) | D4 |
| A7 | Startup pool warm-up AST line-order check (`hw.get_or_create_pool("whisper_transcribe")` BEFORE vision task spawn) | AST line-order positive check | D4 |

**Q8 disposition**: CUDA-gated A8 behavioral smoke anchor DEFERRED per auditor verdict Q8 disposition. Plan v1 ships 7 always-run anchors (mid 7 exact). Future cycle may add A8 if test surface gap surfaces.

---

## §4 Honest-count commitment (per `Explicit-closure-honest-count-commitment` discipline)

Closure-actual count will land at exactly 7 anchors per current spec. If implementation reveals an 8th anchor warranting addition (e.g. defense-in-depth at developer Phase 4 implementation surface), closure-narrative SHALL bank as ON-TARGET +14.3% per band table — doctrine bumps `### Phase-0-granular-decomposition-enables-accurate-estimates` 19 → 20 supporting cleanly. Closure-actual UNDER 6 OR OVER 8 SHALL invoke the honest-narrative path per locked discipline; will NOT silently over-count or under-count to claim ON-TARGET. Closure-projection band table at §6 enumerates all 7 outcomes (5/6/7/8/9/≤4/≥10) with explicit doctrine consequences for each.

**12th instance of `Explicit-closure-honest-count-commitment` discipline** banked here at Plan v1 §4 (MADE); closure HONORED at closure-audit firing 13th instance per STRICT separation locked at P0.B3.

---

## §5 Phase-by-phase implementation plan

**Phase 1 — Worker + subprocess singleton (D1 + D2)** (~30 min):

1. Open `core/heavy_worker.py`.
2. After `adaface_embed_worker` function block, add `_SUBPROCESS_WHISPER_MODEL: "Any | None" = None` module-level var.
3. After `_SUBPROCESS_WHISPER_MODEL` declaration, add `_get_subprocess_whisper()` accessor function per §2.2 signature.
4. After `_get_subprocess_whisper()`, add `whisper_transcribe_worker` function per §2.1 signature.
5. Verify file imports already include `numpy as np` (yes, via P0.R6 D2 worker — confirmed at heavy_worker.py imports). If not, add.
6. Verify `from typing import Any` import exists or add.

**Phase 2 — `core/audio.py::transcribe()` body migration + signature change (D3 part (a) + (b))** (~30 min):

1. Open `core/audio.py`.
2. Change `def transcribe(audio: np.ndarray) -> tuple[str, str]:` (line 493) to `async def transcribe(audio: np.ndarray) -> tuple[str, str]:`.
3. Replace lines 504-519 (inference block + segment-filtering) with the migrated body per §2.3 Part (b).
4. Update docstring (line 494-499) to reflect worker subprocess delegation.
5. Verify `import core.heavy_worker as hw` lands at top of body OR top of file. Banking observation: developer may choose to lift `import core.heavy_worker as hw` to module-top imports if not already there (similar to pipeline.py which already does so post-P0.R6 D5).

**Phase 3 — Caller migration (D3 part (b) continued)** (~15 min):

1. `core/audio.py:620`: replace `text, lang = await loop.run_in_executor(None, transcribe, audio)` with `text, lang = await transcribe(audio)`.
2. `pipeline.py:7482`: replace `_t, _ = await _ev_loop.run_in_executor(None, transcribe, _a)` with `_t, _ = await transcribe(_a)`.
3. `test_executor.py:259-279`: replace `result = await loop.run_in_executor(None, audio_mod.transcribe, fake_audio)` with `result = await audio_mod.transcribe(fake_audio)`.

**Phase 4 — Health observability + startup wiring (D4)** (~15 min):

1. `pipeline.py::run()`: locate the P0.R6 D5 site where `hw.get_or_create_pool("adaface_embed")` + `_pipeline_state_store.set_heavy_worker_status("adaface_embed", "healthy")` lands. Add immediately AFTER (or alongside): `hw.get_or_create_pool("whisper_transcribe")` + `_pipeline_state_store.set_heavy_worker_status("whisper_transcribe", "healthy")`.
2. Verify ORDERING INVARIANT preserved: BOTH pool warm-ups MUST land BEFORE vision task spawn (`_vision_task = asyncio.create_task(_background_vision_loop(...))`).

**Phase 5 — Test surface (`tests/test_p0_r6_x_whisper_worker.py` NEW)** (~30 min):

1. Create `tests/test_p0_r6_x_whisper_worker.py`.
2. Implement 7 anchors per §3 lock with the same shape as `tests/test_p0_r6_heavy_worker_foundation.py` (developer reference precedent).
3. Run 5/5 deliberate-regression confirmations per §2.5 table.
4. Full suite verification — expect 2657 + 7 = 2664 passing post-P0.R6.X.

**Phase 6 — Closure narrative + audit (~20 min)**:

1. Update CLAUDE.md header with P0.R6.X closure entry.
2. Bank doctrine firings per §6 closure-projection band table outcome.
3. Update test count line at CLAUDE.md top.
4. Architect closure-audit Path C grep-verify against production code.

---

## §6 Closure-projection band table + doctrine outcomes

| closure-actual | overage vs mid 7 | band | doctrine outcome |
|---|---|---|---|
| 5 | −28.6% | SLIGHT-DRIFT-DOWN (within ±30%) | `### Phase-0-granular-decomposition` HOLDS at 19 supporting (no bump); observation banked |
| 6 | −14.3% | ON-TARGET | `### Phase-0-granular-decomposition` 19 → 20 supporting |
| 7 | 0% | ON-TARGET exact mid | `### Phase-0-granular-decomposition` 19 → 20 supporting + 12th consecutive 0% streak extends `Doctrine-prediction-precision-improving-over-arc` sub-observation |
| 8 | +14.3% | ON-TARGET | `### Phase-0-granular-decomposition` 19 → 20 supporting |
| 9 | +28.6% | SLIGHT-DRIFT-UP (within ±30%) | `### Phase-0-granular-decomposition` HOLDS at 19 supporting; observation banked |
| ≥10 OR ≤4 | beyond ±30% | FALSIFICATION TRIGGER | `### Phase-0-granular-decomposition` demotes back to architect-memory + reasoning audit |

---

## §7 Pass-3 grep verification baseline (architect-side at closure-narrative drafting)

Per `### Grep-baseline-before-drafting` doctrine (elevated at P0.B3 closure 2026-05-21): closure-narrative drafting at Phase 6 grep-verifies §1.1 + §1.2 + §1.3 enumeration tables against post-implementation production code. Catching layer:

- Architect Pass-1 grep at Phase 0 §1.1 + §1.2 + §1.3 baseline ✓ (this Plan v1 covers Pass-2)
- Auditor Pass-2 grep at Plan v1 §1 verdict (standing flag per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval`)
- Architect Pass-3 grep at closure-narrative drafting (catches developer Phase 5 implementation drift if any)

If Pass-3 surfaces enumeration drift (e.g., Phase 4 implementation accidentally added a new transcribe call site), Plan-v1-Pass-2-grep-undercount 7 → 8 candidate.

---

## §8 Discipline-counter projections (locked +1-per-artifact)

Per locked convention (P0.S6 closure adjudication 2026-05-21): every artifact in cycle (Phase 0 + Plan v1 + closure) increments discipline counters by +1.

Baseline at P0.R6 closure (2026-05-24):

| Discipline | P0.R6 closure baseline | Plan v1 close (this artifact) | P0.R6.X closure projection |
|---|---|---|---|
| Strict-industry-standard mode applications | 72 | 74 | 75 |
| Strict-mode successful closures | 21 | 21 | 22 |
| Spec-first review cycle | 81-for-81 | 83-for-83 | 84-for-84 |
| `### Grep-baseline-before-drafting` instances | 39 | 41 | 42 |
| Cross-cycle-handoff transparency successful | 45 | 47 | 48 |
| Spec-time grep-verification instances | 49 | 51 | 52 |
| `### Twin-filename-pitfall-prevention` preventive events | 21 | 22 | stays 22 (already honored at Phase 0 + Plan v1 drafting) |
| Auditor-Q5-estimates-trail-grep banked closures | 25 | 25 | 26 |
| Deferred-canary strategy applications | 23 | 23 | 24 |

**OPTIONAL-Plan-v2 path candidacy**: if auditor returns 0 precision items at this Plan v1 review, cycle ships as 3-artifact (Phase 0 + Plan v1 + closure). **10th OPTIONAL-Plan-v2 proof case candidate post-closure**.

**`### Pre-audit-quantifier-precision-refined-by-grep` instance enumeration** (post-P0.R6 closure, locked at CLAUDE.md doctrine body lines 659-689):

- 1st: P0.B3 D-D Phase 0 (COUNT-axis)
- 2nd: P0.R2 §2.6(b) Phase 0 (MECHANISM-AXIS)
- 3rd: P0.R4 Q3 Phase 0 (MECHANISM-GENERALITY-AXIS)
- 4th: P0.R5 Phase 0 (LAYERED-AXIS 3-axis)
- 5th: P0.R6 Phase 0 (LAYERED-AXIS continuation 2-axis)
- **6th**: P0.R6.X Phase 0 (TASK-COMPLETENESS-AXIS — pre-audit "~2-3 sites" refined to "1 inference site")

Path C reconciliation banking at §1.4: `Per-artifact-arithmetic-drift-survives-grep-baseline` 4 → 5 candidate AT AUDITOR-SIDE.

---

## §9 Locked Q1-Q8 adjudication (per auditor verdict RATIFIED)

| Q | Locked | Implementation effect |
|---|---|---|
| Q1 (LOAD-BEARING) | (a) sync → async signature | `def transcribe(audio)` → `async def transcribe(audio)`; 2 production callers + 1 test caller migrate from `await loop.run_in_executor(None, transcribe, ...)` to `await transcribe(...)` |
| Q2 (LOAD-BEARING) | (b) filters in main process | Worker returns `(raw_text, language)`; filter chain (non-ASCII / char-run / repetition / 1-word artifact) stays in `transcribe()` body AFTER worker returns |
| Q3 | (a) explicit tuple `(bytes, shape, dtype_name)` | IPC payload shape matches P0.R6 D2 `adaface_embed_worker` pattern |
| Q4 | (b) raw_text + language from worker | Per Q2 (b) — filters apply in main process AFTER worker returns |
| Q5 | (b) lazy load on first call | Matches main-process pattern; ~3-5s first-call latency only on cold start |
| Q6 | Reuses P0.R6 Q6 (a) explicit `mp.get_context("spawn")` | No new decision; existing infrastructure |
| Q7 | max_workers=1 | Whisper inference sequential within session; matches P0.R6 default |
| Q8 | DEFER CUDA-gated A8 to follow-up | Phase 0 mid 7 covers source-inspection floor; future cycle may add A8 |

---

## §10 Architect-handoff items for auditor verdict

1. **Pass-2 grep verification** (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine): independent re-grep §1.1 7-row enumeration + §1.2 8-row cross-spec table + §1.3 5-row caller migration table. If auditor surfaces additional Whisper-touching sites OR cross-spec interactions, lock as Plan v1 PI #1 absorption per Option α pattern. Architect's Pass-2 at this draft confirms identical to Phase 0 §1.1 + §1.2 (re-verified); §1.3 caller migration is new explicit enumeration not in Phase 0.

2. **§1.4 doctrine enumeration reconciliation**: Path C grep-verify against CLAUDE.md canonical text (lines 646-770) confirms architect's §6 enumeration in Phase 0 matches canonical. Auditor's P0.R6.X verdict working-memory has 2-position enumeration drift (P0.R1 vs P0.B3 D-D as 1st; SCOPE-AXIS vs MECHANISM-AXIS at 2nd). Disposition (β) per auditor's option list with actor-side reversed. Banking: `Per-artifact-arithmetic-drift-survives-grep-baseline` 4 → 5 instance AT AUDITOR-SIDE.

3. **Closure-audit Path C grep-verify items** (banked for architect closure-audit at Phase 6):
   - Verify `whisper_transcribe_worker` lands at `core/heavy_worker.py` with exact signature per §2.1
   - Verify `_SUBPROCESS_WHISPER_MODEL` + `_get_subprocess_whisper()` land per §2.2
   - Verify `core/audio.py::transcribe()` has `async def` signature + body uses `hw.run_heavy("whisper_transcribe", ...)`
   - Verify 2 caller sites migrated: `core/audio.py:620` + `pipeline.py:7482` (line numbers may shift post-edit)
   - Verify A4 inverse check fires correctly (no `model.transcribe(audio, ...)` direct call remains in `transcribe()` body)
   - Verify health snapshot reports `"whisper_transcribe"` key
   - Verify startup ordering invariant preserved (whisper_transcribe pool warm-up BEFORE vision task spawn)

4. **Closure-narrative explicit doctrine X → Y lines** (per `Implicit-doctrine-firings-not-narrative-tracked` 5-instance threshold reached at P0.R5 closure-audit — 3rd-cycle self-sustaining adoption):
   - `### Architect-reads-production-code-before-sign-off` 18 → 19 firing at closure-audit (explicit X → Y narrative line required)
   - `### Phase-0-catches-wrong-premise` 12 → 13 firing (sub-pattern A opposite-direction MOTIVATION-REFRAMING variant)
   - `### Pre-audit-quantifier-precision-refined-by-grep` 5 → 6 firing (TASK-COMPLETENESS-AXIS continuation, first post-elevation firing)
   - `### Zero-precision-items-at-auditor-review` 19 → 21 (Phase 0 + Plan v1, IF cycle clears cleanly at Plan v1)
   - `### Phase-0-granular-decomposition-enables-accurate-estimates` 19 → 20 IF closure-actual ∈ [6, 8]
   - `Doctrine-prediction-precision-improving-over-arc` sub-observation streak extension IF closure-actual = 7 exact

---

**End of Plan v1.** Ready for auditor verdict.
