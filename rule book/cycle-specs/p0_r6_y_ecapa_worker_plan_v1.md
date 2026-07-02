# P0.R6.Y — ECAPA voice ID migration to ProcessPoolExecutor worker (Plan v1)

**Date**: 2026-05-24
**Author**: architect (Claude)
**Phase 0 verdict**: ACCEPTED with 0 BLOCKING PIs + 0 non-blocking observations + 1 ratified banking event (SURFACE-CASCADE-AXIS 7th instance) + 1 ratified sub-pattern-A non-firing (architect honest framing on correct pre-audit premise)
**Cycle shape**: MEDIUM band, 3-artifact OPTIONAL-Plan-v2 path candidate (11th proof case if cycle clears Plan v1 cleanly)

---

## §1 Pass-2 grep verification (architect-side, per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval`)

### §1.1 ECAPA inference enumeration (Phase 0 §1.1 LOCKED; re-verified at Plan v1 draft time)

| # | Surface | File:Line | Sync/Async | Wrapped? | Migrate? |
|---|---|---|---|---|---|
| 1 | `load_speaker_embedder()` model loader | `core/voice.py:69` | sync (boot) | n/a | n/a (subprocess inherits its own loader) |
| 2 | `_embedder` module-level singleton | `core/voice.py:39` | n/a | n/a | n/a (subprocess holds its own singleton) |
| 3 | **`_embedder.encode_batch(signal)` LOAD-BEARING inference** | **`core/voice.py:141`** | **sync** | **n/a** | **YES — D3 migration target inside `embed()` body** |
| 4 | `embed()` public API | `core/voice.py:121` (def) | sync → async | n/a | YES — D3 signature change |
| 5 | `identify()` public API | `core/voice.py:459` (def) | sync → async | n/a (calls embed internally) | YES — D3 signature cascade |
| 6 | `_diarize_ecapa_valley()` legacy backend | `core/voice.py:152` (def) | sync → async | n/a (calls embed in window loop + identify per segment) | YES — D3 signature cascade |
| 7 | `_diarize_pyannote()` pyannote backend | `core/voice.py:312` (def) | sync → async | n/a (calls identify per segment at line 395) | YES — D3 signature cascade |
| 8 | `diarize()` public dispatcher | `core/voice.py:406` (def) | sync → async | n/a (dispatches to _diarize_pyannote OR _diarize_ecapa_valley) | YES — D3 signature cascade |
| 9 | `get_diarize_executor()` dedicated thread pool | `core/voice.py:50` | n/a | n/a | n/a (pyannote-backend isolation stays at P0.R6.Y; retired at P0.R6.Z) |

**Pass-2 verification status**: identical to Phase 0 §1.1; auditor's independent re-grep at Phase 0 verdict confirmed lines 121/141/152/459/69 exact + lines ~289/~404 approximate (architect's `~` prefix correctly signaled approximation). Plan v1 hardens approximations: `_diarize_pyannote` at `core/voice.py:312` + `diarize` at `core/voice.py:406` per auditor's independent re-grep.

### §1.2 Pipeline.py caller enumeration (Phase 0 §1.2 LOCKED; re-verified at Plan v1 draft time)

| # | Caller | File:Line | Current shape | Post-D3 shape | Asyncio-blocking? |
|---|---|---|---|---|---|
| 1 | voice ID for known-voice match | `pipeline.py:2274` | `await loop.run_in_executor(None, voice_mod.identify, ...)` | `await voice_mod.identify(...)` | NO (already async-wrapped) |
| 2 | embedding for voice gallery write | `pipeline.py:2304` | `emb = await loop.run_in_executor(None, voice_mod.embed, audio)` | `emb = await voice_mod.embed(audio)` | NO (already async-wrapped) |
| 3 | **voice-first ambient identify** | **`pipeline.py:7148`** | **`v_pid, v_score = voice_mod.identify(...)` SYNC DIRECT CALL** | **`v_pid, v_score = await voice_mod.identify(...)`** | **YES — LOAD-BEARING ASYNCIO FIX** |
| 4 | conversation-turn voice identify | `pipeline.py:7414` | `await loop.run_in_executor(None, voice_mod.identify, ...)` | `await voice_mod.identify(...)` | NO (already async-wrapped) |
| 5 | multi-speaker diarize dispatch | `pipeline.py:7450` | `await _ev_loop.run_in_executor(voice_mod.get_diarize_executor(), voice_mod.diarize, ...)` | `await voice_mod.diarize(...)` (now async; pyannote pipeline INSIDE diarize still uses get_diarize_executor) | NO (already async-wrapped; signature ripple) |

**Pipeline.py caller migration count**: 5 production sites.
- Site 7148 is the LOAD-BEARING asyncio-release fix
- Sites 2274/2304/7414/7450 are signature-cascade migrations (wrapper elimination)

### §1.3 Voice_channel.py + test surfaces enumeration

| # | Surface | File:Line | Current | Post-D3 |
|---|---|---|---|---|
| 1 | `identify_speaker` body | `core/voice_channel.py:175, 192` | `await _maybe_run_in_executor(diarize_fn, ...)` + `await _maybe_run_in_executor(identify_fn, ...)` | Helper at line 87-95 auto-detects `iscoroutinefunction(fn)` and routes accordingly; NO CHANGE to helper, signature change in voice.py propagates transparently |
| 2 | `test_pipeline.py:6375` patch | `with patch("pipeline.voice_mod.embed", return_value=fake_emb)` | becomes `AsyncMock(return_value=fake_emb)` OR `async def` wrapper | TEST in-scope (4 patch sites total) |
| 3 | `test_pipeline.py:6452` patch | `with patch("core.voice.embed", return_value=same_emb)` | same as #2 | TEST in-scope |
| 4 | `test_pipeline.py:6494` patch | `with patch("core.voice.embed", side_effect=_fake_embed)` | same as #2; side_effect requires async-compatible callable | TEST in-scope (side_effect path) |
| 5 | `test_pipeline.py:6496` patch | `with patch("core.voice.identify", return_value=(None, 0.0))` | same as #2 | TEST in-scope |
| 6 | `tests/conftest.py` voice stub | stub functions may be sync | `async def` wrapper if stubs are called directly from production code paths | TEST observation (banking for developer Phase 5) |
| 7 | reconciler docstring refs | `core/reconciler.py:612/649` | docstring references "voice.identify() returns" | unchanged (commentary only) |

**Voice_channel.py auto-coroutine-detection**: `_maybe_run_in_executor` helper at `core/voice_channel.py:87-95` already handles BOTH sync and async via `inspect.iscoroutinefunction(fn)` check. No helper changes needed; signature change in voice.py propagates transparently per existing infrastructure.

**Test stub migration count**: 4 patch sites in `test_pipeline.py` (~6375, ~6452, ~6494, ~6496) need `AsyncMock` instead of `MagicMock` patches when patching async functions. Plus potential `tests/conftest.py` stub adaptation (similar to P0.R6.X stub-signature ripple per `Plan-v1-Pass-2-grep-undercount` 8th instance). Banked as in-scope migration; developer Phase 3 surfaces full enumeration.

### §1.4 Cross-spec interactions (Phase 0 §1.4 LOCKED; re-verified at Plan v1 draft time)

| Spec | Interaction | Status |
|---|---|---|
| P0.R5 | Vendored speechbrain fork (`HungryFingerss/speechbrain @ a9b05847`) | LOAD-BEARING (subprocess inherits `from speechbrain.inference.speaker import EncoderClassifier` cleanly; vendored torch_audio_backend patches apply uniformly at install-time per `requirements.txt` git URL; HF_TOKEN auth unchanged) |
| P0.R6 | AdaFace migration to heavy_worker — SAME infrastructure | EXTENDS (`ecapa_embed_worker` lands in same `core/heavy_worker.py` module; `_heavy_worker_status` dict extends for `ecapa_embed` key) |
| P0.R6.X | Whisper migration — SAME infrastructure pattern | EXTENDS (3rd task class joining heavy_worker pool; sync→async cascade discipline established at P0.R6.X) |
| P0.R6.Z | Pyannote migration (FUTURE — NOT P0.R6.Y scope) | INTERACTS — pyannote's internal speechbrain ECAPA usage stays in main process at P0.R6.Y via `get_diarize_executor()`; P0.R6.Z migrates pyannote pipeline + retires `get_diarize_executor()` |
| P0.S7.5.2 D4 | 1-word STT artifact filter (Whisper-side) | NO conflict (different model class) |
| P0.0.7 H3 | `identity_claim` event emission | NO conflict (emission happens in main process AFTER voice ID; signature change ripple at boundary) |
| Session 119 / P5 | reconciler negative-cosine fix — `voice.identify()` returns actual cosine including negatives | NO conflict (return shape preserved through subprocess boundary; only signature changes async, not semantic) |
| Session 88 / P2 | `_diarize_pyannote` + `_diarize_ecapa_valley` dispatch logic | LOAD-BEARING (dispatch stays in `diarize()` body; signature cascade preserves return-shape contract `[{start_sample, end_sample, speaker_id, speaker_score, speaker_label}]`) |

**Pass-2 verification status**: identical to Phase 0 §1.4; cross-spec orthogonality verified clean.

---

## §2 D-decision spec (4 D-decisions, locked from Phase 0; Q1-Q8 LOCKED per auditor verdict)

### §2.1 D1 — `ecapa_embed_worker` in `core/heavy_worker.py`

**LOCKED**. New worker entry point at module-scope. Mirror of P0.R6 D2 `adaface_embed_worker` + P0.R6.X D1 `whisper_transcribe_worker` shape.

Signature:

```python
def ecapa_embed_worker(
    audio_bytes: bytes,
    shape: "tuple[int, ...]",
    dtype_name: str,
    sample_rate: int,
) -> "bytes | None":
    """Worker entry point: deserializes audio buffer + extracts ECAPA-TDNN
    speaker embedding via subprocess-singleton SpeechBrain model + returns
    L2-normalized 192-dim float32 embedding as bytes (768 bytes).

    Q3 (a) lock: explicit tuple (bytes, shape, dtype_name, sample_rate) for
    IPC payload shape — matches P0.R6 D2 + P0.R6.X D1 pattern.

    Q4 (b) lock: subprocess performs L2-normalization (numpy work, cheap);
    returns embedding ready for downstream cosine computation.

    Q5 (b) lock: lazy-load EncoderClassifier on first call via
    _get_subprocess_ecapa() accessor.

    Returns None on cascading failure (preserves P0.R1 D1 None-return
    fallback contract — callers handle as identify-miss).
    """
    import numpy as np
    audio_array = np.frombuffer(audio_bytes, dtype=dtype_name).reshape(shape)
    embedder = _get_subprocess_ecapa()
    if embedder is None:
        return None
    # Minimum reliable length: 1.5 seconds (matches main-process embed() invariant)
    if len(audio_array) < sample_rate * 1.5:
        return None
    # Resample to 16 kHz if needed (matches main-process behavior)
    if sample_rate != 16000:
        import torchaudio
        import torch
        audio_t = torch.from_numpy(audio_array.astype(np.float32))
        audio_array = torchaudio.functional.resample(audio_t, sample_rate, 16000).numpy()
    import torch
    signal = torch.from_numpy(audio_array.astype(np.float32)).unsqueeze(0)
    try:
        with torch.no_grad():
            emb = embedder.encode_batch(signal)
        emb = emb.squeeze().cpu().numpy()
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        return emb.astype(np.float32).tobytes()
    except Exception:  # OPTIONAL: inference failure → None propagates
        return None
```

Worker body preserves main-process `embed()` invariants verbatim (1.5s minimum length, 16kHz resampling, torch.no_grad, L2-normalize) — keeps subprocess semantically identical to current main-process code.

### §2.2 D2 — `_SUBPROCESS_ECAPA_EMBEDDER` singleton + `_get_subprocess_ecapa()` accessor in `core/heavy_worker.py`

**LOCKED**. Mirror of P0.R6 D2 `_SUBPROCESS_EMBEDDER` + P0.R6.X D2 `_SUBPROCESS_WHISPER_MODEL` accessor pattern.

Signature:

```python
_SUBPROCESS_ECAPA_EMBEDDER: "Any | None" = None


def _get_subprocess_ecapa() -> "Any | None":
    """Returns subprocess-scoped SpeechBrain ECAPA-TDNN EncoderClassifier
    singleton. Lazy-loads on first call.

    Q5 (b) lock: lazy-load on first call matches main-process pattern
    (core/voice.py:load_speaker_embedder); first-call latency ~1-2s only
    affects first voice-ID after subprocess spawn (acceptable cost).

    P0.R1 D1 None-return fallback contract preserved: returns None on
    load failure → callers treat as identify-miss.
    """
    global _SUBPROCESS_ECAPA_EMBEDDER
    if _SUBPROCESS_ECAPA_EMBEDDER is None:
        try:
            from speechbrain.inference.speaker import EncoderClassifier
            _SUBPROCESS_ECAPA_EMBEDDER = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir="pretrained_models/spkrec-ecapa-voxceleb",
                run_opts={"device": "cuda"},
            )
        except Exception:  # OPTIONAL: load failure → None propagates
            return None
    return _SUBPROCESS_ECAPA_EMBEDDER
```

Subprocess-scoped (each subprocess maintains its own singleton; main process never holds this reference). Cleanup via `shutdown_all_pools(wait=True)` terminates worker subprocesses cleanly. Inherits P0.R5 vendored speechbrain fork via `requirements.txt` git URL — no special install steps needed.

### §2.3 D3 — `core/voice.py` 5-function async cascade + `embed()` body migration

**LOCKED — sync→async cascade per Q1 (a)**. Five functions become `async def`; body migration in `embed()` only:

**Part (a) — signature cascade**:

```python
# core/voice.py:121
# BEFORE
def embed(audio: np.ndarray, sample_rate: int = MIC_SAMPLE_RATE) -> "np.ndarray | None":
# AFTER
async def embed(audio: np.ndarray, sample_rate: int = MIC_SAMPLE_RATE) -> "np.ndarray | None":

# core/voice.py:152
# BEFORE
def _diarize_ecapa_valley(...) -> list[dict]:
# AFTER
async def _diarize_ecapa_valley(...) -> list[dict]:

# core/voice.py:312
# BEFORE
def _diarize_pyannote(...) -> list[dict]:
# AFTER
async def _diarize_pyannote(...) -> list[dict]:

# core/voice.py:406
# BEFORE
def diarize(...) -> list[dict]:
# AFTER
async def diarize(...) -> list[dict]:

# core/voice.py:459
# BEFORE
def identify(audio, voice_gallery, threshold, sample_rate=MIC_SAMPLE_RATE) -> tuple[str | None, float]:
# AFTER
async def identify(audio, voice_gallery, threshold, sample_rate=MIC_SAMPLE_RATE) -> tuple[str | None, float]:
```

Internal calls between these wrappers change from `func(...)` to `await func(...)`:
- `identify()` body at line 470: `emb = await embed(audio, sample_rate)`
- `_diarize_ecapa_valley()` body at line 195: `emb = await embed(audio[pos : pos + window_samples], sample_rate)` (inside loop)
- `_diarize_ecapa_valley()` body at line 225: `pid, score = await identify(seg_audio, voice_gallery, threshold, sample_rate)`
- `_diarize_pyannote()` body at line 395: `pid, score = await identify(seg_audio, voice_gallery, threshold, sample_rate)`
- `_diarize_pyannote()` body's pyannote pipeline call retains thread dispatch: `annotation = await loop.run_in_executor(get_diarize_executor(), self._pipeline, audio_dict)` per Q2 (a) lock
- `diarize()` dispatcher body: `return await _diarize_pyannote(...)` or `return await _diarize_ecapa_valley(...)`

**Part (b) — `embed()` body migration** (replaces lines 132-149):

```python
# BEFORE (lines 132-149)
if sample_rate != 16000:
    import torchaudio
    audio_t = torch.from_numpy(audio.astype(np.float32))
    audio   = torchaudio.functional.resample(audio_t, sample_rate, 16000).numpy()

signal = torch.from_numpy(audio.astype(np.float32)).unsqueeze(0)
try:
    with torch.no_grad():
        emb = _embedder.encode_batch(signal)
    emb  = emb.squeeze().cpu().numpy()
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    return emb.astype(np.float32)
except Exception as e:
    print(f"[Voice] Embedding failed: {e}")
    return None

# AFTER (replaces lines 132-149)
import core.heavy_worker as hw
emb_bytes = await hw.run_heavy(
    "ecapa_embed",
    hw.ecapa_embed_worker,
    audio.tobytes(),
    audio.shape,
    audio.dtype.name,
    sample_rate,
)
if emb_bytes is None:
    return None
emb = np.frombuffer(emb_bytes, dtype=np.float32)
return emb.copy()  # detach from buffer (mutable downstream)
```

Worker performs L2-normalization subprocess-side (Q4 (b)). Main-process body just deserializes + detaches buffer for downstream mutation safety.

**Caller migration (5 production sites per §1.2)**:

```python
# pipeline.py:2274
# BEFORE
None, voice_mod.identify, audio, _voice_gallery_store.peek_all_gallery(), VOICE_RECOGNITION_THRESHOLD
# AFTER (call site simplifies; full migration drops run_in_executor wrap)
await voice_mod.identify(audio, _voice_gallery_store.peek_all_gallery(), VOICE_RECOGNITION_THRESHOLD)

# pipeline.py:2304
# BEFORE
emb = await loop.run_in_executor(None, voice_mod.embed, audio)
# AFTER
emb = await voice_mod.embed(audio)

# pipeline.py:7148 (LOAD-BEARING asyncio fix)
# BEFORE
v_pid, v_score = voice_mod.identify(
    _ambient_audio, _voice_gallery_store.peek_all_gallery(), VOICE_RECOGNITION_THRESHOLD
)
# AFTER
v_pid, v_score = await voice_mod.identify(
    _ambient_audio, _voice_gallery_store.peek_all_gallery(), VOICE_RECOGNITION_THRESHOLD
)

# pipeline.py:7414
# BEFORE (inside run_in_executor wrap context)
None, voice_mod.identify, audio_buf, _voice_gallery_store.peek_all_gallery(), VOICE_RECOGNITION_THRESHOLD
# AFTER
await voice_mod.identify(audio_buf, _voice_gallery_store.peek_all_gallery(), VOICE_RECOGNITION_THRESHOLD)

# pipeline.py:7450
# BEFORE
_diar = await _ev_loop.run_in_executor(
    voice_mod.get_diarize_executor(), voice_mod.diarize,
    audio_buf, _voice_gallery_store.peek_all_gallery(), VOICE_RECOGNITION_THRESHOLD
)
# AFTER
_diar = await voice_mod.diarize(
    audio_buf, _voice_gallery_store.peek_all_gallery(), VOICE_RECOGNITION_THRESHOLD
)
```

### §2.4 D4 — health observability + startup wiring extension

**LOCKED**. Reuses P0.R6 D4 + P0.R6.X D4 `_heavy_worker_status` dict. Add `"ecapa_embed"` key with initial "healthy" status.

**Health snapshot extension**: `_heavy_worker_status` dict at startup gains `"ecapa_embed": "healthy"` entry. `format_health_line` conditional `heavy_workers=degraded` emit already covers multi-task case. No new format-line code needed.

**Startup wiring extension** in `pipeline.py::run()`:

```python
# BEFORE (post-P0.R6.X closure shape)
import core.heavy_worker as hw
hw.get_or_create_pool("adaface_embed")
asyncio.create_task(_pipeline_state_store.set_heavy_worker_status("adaface_embed", "healthy"))
hw.get_or_create_pool("whisper_transcribe")
asyncio.create_task(_pipeline_state_store.set_heavy_worker_status("whisper_transcribe", "healthy"))
# vision task spawn...

# AFTER (P0.R6.Y)
import core.heavy_worker as hw
hw.get_or_create_pool("adaface_embed")
asyncio.create_task(_pipeline_state_store.set_heavy_worker_status("adaface_embed", "healthy"))
hw.get_or_create_pool("whisper_transcribe")
asyncio.create_task(_pipeline_state_store.set_heavy_worker_status("whisper_transcribe", "healthy"))
hw.get_or_create_pool("ecapa_embed")
asyncio.create_task(_pipeline_state_store.set_heavy_worker_status("ecapa_embed", "healthy"))
# vision task spawn (unchanged)...
```

**ORDERING INVARIANT**: ALL 3 heavy-worker pools warm-up BEFORE vision task spawn AND before pipeline's first conversation cycle. AdaFace + Whisper + ECAPA in order; vision task spawn follows.

**Shutdown unchanged**: P0.R6 D5 `hw.shutdown_all_pools(wait=True)` already terminates ALL pools (including ecapa_embed) cleanly.

### §2.5 Deliberate-regression scenarios (per `### Induction-surfaces-invariant-gaps` doctrine)

6 scenarios proving each anchor catches its targeted regression:

| Revert | Expected anchor fire | Anchor catches |
|---|---|---|
| (a) Delete `ecapa_embed_worker` from `core/heavy_worker.py` | A1 (function-existence source-inspection) | Worker function gone |
| (b) Replace `_get_subprocess_ecapa()` body with `return None` unconditionally | A2 (subprocess singleton accessor + lazy-init shape) | Singleton accessor broken |
| (c) Revert `embed()` body to `_embedder.encode_batch(signal)` direct call (skip worker dispatch) | A3 + A4 (AST positive `hw.run_heavy` Call node + inverse missing-`_embedder.encode_batch` check) | Body migration regressed; old sync code path restored |
| (d) Revert any one of the 5 `async def` signatures back to `def` | A5 (5-function async-def AST cascade check) | Signature cascade regressed |
| (e) Revert `pipeline.py:7148` from `await voice_mod.identify(...)` to sync `voice_mod.identify(...)` | A6 (LOAD-BEARING asyncio fix; AST positive `await` + inverse no-sync-direct-call check at site 7148) | Site 7148 asyncio-block reintroduced |
| (f) Restore `run_in_executor(None, voice_mod.embed/identify, ...)` wrapper at any of sites 2274/2304/7414 OR `run_in_executor(get_diarize_executor(), voice_mod.diarize, ...)` at 7450 | A7 (caller migration count check; inverse no-run_in_executor-wrap for voice_mod) | Caller migration regressed |
| (g) Drop `hw.get_or_create_pool("ecapa_embed")` from `pipeline.py::run()` startup | A8 + A9 (health snapshot missing ecapa_embed key + AST line-order regression) | Pool warm-up regressed |

7/9 deliberate-regression scenarios cover the 9 anchors. A4 + A6 + A9 also serve as inverse / line-order regression guards (mirror of P0.R6 + P0.R6.X precedent).

---

## §3 Logical anchor lock (Q5 LOCK = 9 anchors at EXACT MID)

Per auditor Phase 0 verdict §4 Q5 ratification: **9 anchors at exact mid 9 INCLUSIVE ±15% band [7.65, 10.35]**.

| # | Anchor | Surface | Coverage |
|---|---|---|---|
| A1 | `ecapa_embed_worker` function exists in `core/heavy_worker.py` | Source-inspection (function definition) | D1 |
| A2 | `_SUBPROCESS_ECAPA_EMBEDDER` singleton + `_get_subprocess_ecapa()` accessor present | Source-inspection (module-level var + accessor) | D2 |
| A3 | `core/voice.py::embed()` AST shows `hw.run_heavy("ecapa_embed", ...)` Call node | AST positive check | D3 part (b) |
| A4 | `core/voice.py::embed()` AST shows `_embedder.encode_batch(` DIRECT call is GONE | AST inverse check (old sync inference must NOT remain) | D3 part (b) |
| A5 | 5 ECAPA-touching functions (`embed`, `identify`, `_diarize_ecapa_valley`, `_diarize_pyannote`, `diarize`) all have `async def` signatures | AST signature-cascade check (5-function enumeration; all 5 must be async) | D3 part (a) |
| A6 | `pipeline.py:7148` migrated to `await voice_mod.identify(...)` — LOAD-BEARING asyncio-release fix | AST positive `await voice_mod.identify` + inverse no-sync-direct-call at site 7148 | D3 site 7148 |
| A7 | 5 pipeline.py caller sites (2274, 2304, 7148, 7414, 7450) use direct `await voice_mod.X(...)` AND wrapper patterns `run_in_executor(None, voice_mod.embed/identify, ...)` + `run_in_executor(get_diarize_executor(), voice_mod.diarize, ...)` GONE | AST count check (positive + inverse) | D3 caller migration |
| A8 | HealthSnapshot reports `"ecapa_embed"` in `_heavy_worker_status` dict | Behavioral test (gather snapshot post-init) | D4 |
| A9 | Startup pool warm-up AST line-order check (`hw.get_or_create_pool("ecapa_embed")` BEFORE vision task spawn AND AFTER `"adaface_embed"` + `"whisper_transcribe"` warm-ups) | AST line-order positive check | D4 |

---

## §4 Honest-count commitment (per `Explicit-closure-honest-count-commitment` discipline)

Closure-actual count will land at exactly 9 anchors per current spec. If implementation reveals an 10th anchor warranting addition (e.g. defense-in-depth at developer Phase 4 implementation surface), closure-narrative SHALL bank as ON-TARGET +11.1% per band table — doctrine bumps `### Phase-0-granular-decomposition-enables-accurate-estimates` 20 → 21 supporting cleanly. Closure-actual UNDER 8 OR OVER 10 SHALL invoke the honest-narrative path per locked discipline; will NOT silently over-count or under-count to claim ON-TARGET. Closure-projection band table at §6 enumerates all outcomes (7/8/9/10/11/≤6/≥12) with explicit doctrine consequences for each.

**14th instance of `Explicit-closure-honest-count-commitment` discipline** banked here at Plan v1 §4 (MADE); closure HONORED at closure-audit firing 15th instance per STRICT separation locked at P0.B3.

---

## §5 Phase-by-phase implementation plan

**Phase 1 — Worker + subprocess singleton (D1 + D2)** (~30 min):

1. Open `core/heavy_worker.py`.
2. After `whisper_transcribe_worker` function block (P0.R6.X foundation), add `_SUBPROCESS_ECAPA_EMBEDDER: "Any | None" = None` module-level var.
3. After `_SUBPROCESS_ECAPA_EMBEDDER` declaration, add `_get_subprocess_ecapa()` accessor function per §2.2 signature.
4. After `_get_subprocess_ecapa()`, add `ecapa_embed_worker` function per §2.1 signature.
5. Imports already include `numpy as np` (verified at P0.R6 + P0.R6.X); `from typing import Any` available.

**Phase 2 — `core/voice.py` signature cascade + `embed()` body migration (D3 part (a) + (b))** (~45 min):

1. Open `core/voice.py`.
2. Change 5 function signatures from `def` to `async def`:
   - Line 121 `embed`
   - Line 152 `_diarize_ecapa_valley`
   - Line 312 `_diarize_pyannote`
   - Line 406 `diarize`
   - Line 459 `identify`
3. Update internal calls between wrappers to `await`:
   - Line ~195 in `_diarize_ecapa_valley`: `emb = await embed(...)`
   - Line ~225 in `_diarize_ecapa_valley`: `pid, score = await identify(...)`
   - Line ~370 in `_diarize_pyannote` body (where pyannote pipeline runs): wrap as `annotation = await loop.run_in_executor(get_diarize_executor(), self._pipeline, audio_dict)` per Q2 (a) lock
   - Line ~395 in `_diarize_pyannote`: `pid, score = await identify(...)`
   - Line 470 in `identify`: `emb = await embed(...)`
   - Public `diarize()` dispatcher body: `return await _diarize_pyannote(...)` / `return await _diarize_ecapa_valley(...)`
4. Replace `embed()` body lines 132-149 per §2.3 Part (b).

**Phase 3 — Pipeline.py caller migration (D3 caller migration)** (~30 min):

1. `pipeline.py:2274`: replace `loop.run_in_executor(None, voice_mod.identify, ...)` with direct `await voice_mod.identify(...)`.
2. `pipeline.py:2304`: replace `await loop.run_in_executor(None, voice_mod.embed, audio)` with `await voice_mod.embed(audio)`.
3. **`pipeline.py:7148` LOAD-BEARING**: replace `v_pid, v_score = voice_mod.identify(...)` with `v_pid, v_score = await voice_mod.identify(...)`.
4. `pipeline.py:7414`: replace `loop.run_in_executor(None, voice_mod.identify, ...)` with `await voice_mod.identify(...)`.
5. `pipeline.py:7450`: replace `_ev_loop.run_in_executor(voice_mod.get_diarize_executor(), voice_mod.diarize, ...)` with `await voice_mod.diarize(...)`.

**Phase 4 — Health observability + startup wiring (D4)** (~15 min):

1. `pipeline.py::run()`: locate P0.R6.X D4 site where `hw.get_or_create_pool("whisper_transcribe")` + healthy-status setter land. Add immediately AFTER: `hw.get_or_create_pool("ecapa_embed")` + `asyncio.create_task(_pipeline_state_store.set_heavy_worker_status("ecapa_embed", "healthy"))`.
2. Verify ORDERING INVARIANT preserved: ALL 3 pool warm-ups BEFORE vision task spawn (`_vision_task = asyncio.create_task(_background_vision_loop(...))`).

**Phase 5 — Test surface (`tests/test_p0_r6_y_ecapa_worker.py` NEW)** (~45 min):

1. Create `tests/test_p0_r6_y_ecapa_worker.py`.
2. Implement 9 anchors per §3 lock with the same shape as `tests/test_p0_r6_x_whisper_worker.py` (developer reference precedent).
3. Run 7/7 deliberate-regression confirmations per §2.5 table.
4. Test stub adaptation: 4 patch sites in `test_pipeline.py` (~6375, ~6452, ~6494, ~6496) need `AsyncMock` instead of `MagicMock` patches. Plus `tests/conftest.py` voice stub adaptation if voice stubs are async-called.
5. Full suite verification — expect 2696 + 9 = 2705 passing post-P0.R6.Y baseline; actual delta may include ripple test additions per `Plan-v1-Pass-2-grep-undercount` discipline.

**Phase 6 — Closure narrative + audit (~30 min)**:

1. Update CLAUDE.md line 3 test count.
2. Bank P0.R6.Y closure entry with all doctrine bumps + explicit X → Y narrative lines.
3. **Extend CLAUDE.md canonical doctrine body at lines 646-770** per auditor Phase 0 architect-handoff item 1:
   - Add P0.R6.Y as 7th instance entry (SURFACE-CASCADE-AXIS sub-shape) after the P0.R6 entry at line 680-689
   - Update "5 applications + 4-axis sub-shape taxonomy" framing at line 656 to "7 applications + 6-axis sub-shape taxonomy"
   - Update sub-shape taxonomy enumeration at line 700 to: "COUNT-axis → MECHANISM-AXIS → MECHANISM-GENERALITY-AXIS → LAYERED-AXIS → LAYERED-AXIS-continuation → TASK-COMPLETENESS-AXIS → SURFACE-CASCADE-AXIS"
   - Preserve banking note + operational rules + falsification clause anchors per the in-line lock at 763-770
4. Architect closure-audit Path C grep-verify against production code.
5. Per `Implicit-doctrine-firings-not-narrative-tracked` 3rd-cycle self-sustaining adoption: explicit X → Y narrative line for `### Architect-reads-production-code-before-sign-off` 19 → 20.

---

## §6 Closure-projection band table + doctrine outcomes

| closure-actual | overage vs mid 9 | band | doctrine outcome |
|---|---|---|---|
| 7 | −22.2% | SLIGHT-DRIFT-DOWN (within ±30%) | `### Phase-0-granular-decomposition` HOLDS at 20 supporting (no bump); observation banked |
| 8 | −11.1% | ON-TARGET | `### Phase-0-granular-decomposition` 20 → 21 supporting |
| 9 | 0% | ON-TARGET exact mid | `### Phase-0-granular-decomposition` 20 → 21 supporting + 13th consecutive 0% streak extends `Doctrine-prediction-precision-improving-over-arc` sub-observation |
| 10 | +11.1% | ON-TARGET | `### Phase-0-granular-decomposition` 20 → 21 supporting |
| 11 | +22.2% | SLIGHT-DRIFT-UP (within ±30%) | `### Phase-0-granular-decomposition` HOLDS at 20 supporting; observation banked |
| ≥12 OR ≤6 | beyond ±30% | FALSIFICATION TRIGGER | `### Phase-0-granular-decomposition` demotes back to architect-memory + reasoning audit |

---

## §7 Pass-3 grep verification baseline (architect-side at closure-narrative drafting)

Per `### Grep-baseline-before-drafting` doctrine: closure-narrative drafting at Phase 6 grep-verifies §1.1 + §1.2 + §1.3 enumeration tables against post-implementation production code. Catching layer:

- Architect Pass-1 grep at Phase 0 §1.1 + §1.2 + §1.3 baseline ✓
- Auditor Pass-2 grep at Phase 0 verdict ✓ (independent re-grep with line-number corrections on `_diarize_pyannote` 312 + `diarize` 406)
- Architect Pass-2 grep at this Plan v1 §1 (refined `~289` → 312 + `~404` → 406 per auditor's independent verification)
- Auditor Pass-2 grep at Plan v1 §1 verdict (standing flag per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval`)
- Architect Pass-3 grep at closure-narrative drafting (catches developer Phase 5 implementation drift if any)

If Pass-3 surfaces enumeration drift (e.g. Phase 4 implementation accidentally added a new ECAPA call site), `Plan-v1-Pass-2-grep-undercount` 8 → 9 candidate.

---

## §8 Discipline-counter projections (locked +1-per-artifact)

Per locked convention (P0.S6 closure adjudication 2026-05-21): every artifact in cycle (Phase 0 + Plan v1 + closure) increments discipline counters by +1.

Baseline post-P0.R6.X closure (2026-05-24):

| Discipline | P0.R6.X closure baseline | Plan v1 close (this artifact) | P0.R6.Y closure projection |
|---|---|---|---|
| Strict-industry-standard mode applications | 75 | 77 | 78 |
| Strict-mode successful closures | 22 | 22 | 23 |
| Spec-first review cycle | 84-for-84 | 86-for-86 | 87-for-87 |
| `### Grep-baseline-before-drafting` instances | 42 | 44 | 45 |
| Cross-cycle-handoff transparency successful | 48 | 50 | 51 |
| Spec-time grep-verification instances | 52 | 54 | 55 |
| `### Twin-filename-pitfall-prevention` preventive events | 22 | stays 22 | stays 22 (Twin-filename count holds; preventive events tracked separately) |
| Auditor-Q5-estimates-trail-grep banked closures | 26 | 26 | 27 |
| Deferred-canary strategy applications | 24 | 24 | 25 |

**OPTIONAL-Plan-v2 path candidacy**: if auditor returns 0 precision items at this Plan v1 review, cycle ships as 3-artifact (Phase 0 + Plan v1 + closure). **11th OPTIONAL-Plan-v2 proof case candidate post-closure**.

**`### Pre-audit-quantifier-precision-refined-by-grep` instance enumeration** (post-P0.R6.X closure baseline; CLAUDE.md canonical at lines 646-770):

- 1st: P0.B3 D-D Phase 0 (COUNT-axis)
- 2nd: P0.R2 §2.6(b) Phase 0 (MECHANISM-AXIS)
- 3rd: P0.R4 Q3 Phase 0 (MECHANISM-GENERALITY-AXIS)
- 4th: P0.R5 Phase 0 (LAYERED-AXIS 3-axis)
- 5th: P0.R6 Phase 0 (LAYERED-AXIS continuation 2-axis)
- 6th: P0.R6.X Phase 0 (TASK-COMPLETENESS-AXIS)
- **7th**: P0.R6.Y Phase 0 (SURFACE-CASCADE-AXIS — NEW sub-shape; sub-shape taxonomy at 6 sub-shapes)

Sub-shape taxonomy after P0.R6.Y: COUNT-AXIS, MECHANISM-AXIS, MECHANISM-GENERALITY-AXIS, LAYERED-AXIS, TASK-COMPLETENESS-AXIS, **SURFACE-CASCADE-AXIS** (NEW).

---

## §9 Locked Q1-Q8 adjudication (per auditor verdict RATIFIED)

| Q | Locked | Implementation effect |
|---|---|---|
| Q1 (LOAD-BEARING) | (a) sync→async cascade across 5 functions | `embed` + `identify` + `_diarize_ecapa_valley` + `_diarize_pyannote` + `diarize` all become `async def`; internal calls `await func(...)` direct |
| Q2 (LOAD-BEARING) | (a) preserve `get_diarize_executor()` for pyannote at P0.R6.Y | `_diarize_pyannote` body dispatches pyannote `Pipeline.__call__` via `loop.run_in_executor(get_diarize_executor(), ...)` from INSIDE async function; full retirement deferred to P0.R6.Z |
| Q3 | (a) explicit tuple `(bytes, shape, dtype_name, sample_rate)` | IPC payload shape matches P0.R6 + P0.R6.X precedent |
| Q4 | (b) subprocess L2-normalizes | Worker returns ready embedding bytes; main process deserializes + detaches buffer copy |
| Q5 | (b) lazy load on first call | Matches main-process pattern; ~1-2s first-call latency only on cold start |
| Q6 | Reuses P0.R6 + P0.R6.X spawn infrastructure | No new decision |
| Q7 | max_workers=1 | ECAPA inference sequential within session; matches P0.R6 + P0.R6.X default |
| Q8 (LOAD-BEARING) | (a) accept N× IPC overhead per `_diarize_ecapa_valley` fallback call | Legacy path rarely invoked (pyannote primary); ~10-20ms acceptable per fallback call. Documented in Known Limitations |

---

## §10 Architect-handoff items for auditor verdict

1. **Pass-2 grep verification** (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine): independent re-grep §1.1 9-row ECAPA inference enumeration + §1.2 5-row pipeline.py caller table + §1.3 7-row voice_channel + test surfaces table + §1.4 8-row cross-spec table. Plan v1 hardened approximate line refs (~289 → 312 + ~404 → 406) per auditor's independent verification. If auditor surfaces additional ECAPA-touching sites OR cross-spec interactions, lock as Plan v1 PI #1 absorption per Option α pattern.

2. **Closure-audit Path C grep-verify items** (banked for architect closure-audit at Phase 6):
   - Verify `ecapa_embed_worker` lands at `core/heavy_worker.py` with exact signature per §2.1
   - Verify `_SUBPROCESS_ECAPA_EMBEDDER` + `_get_subprocess_ecapa()` land per §2.2
   - Verify 5 `core/voice.py` functions are all `async def` per §2.3 Part (a)
   - Verify `core/voice.py::embed()` body uses `hw.run_heavy("ecapa_embed", ...)` per §2.3 Part (b)
   - Verify 5 caller sites migrated: 2274 + 2304 + **7148 (LOAD-BEARING)** + 7414 + 7450 (line numbers may shift)
   - Verify A4 inverse check fires correctly (no `_embedder.encode_batch(` direct call remains in `embed()` body)
   - Verify A6 inverse check at site 7148 (no sync `voice_mod.identify(...)` direct call remains)
   - Verify A7 inverse check at all 5 caller sites (no `run_in_executor(None, voice_mod.embed/identify, ...)` OR `run_in_executor(get_diarize_executor(), voice_mod.diarize, ...)` patterns remain)
   - Verify health snapshot reports `"ecapa_embed"` key
   - Verify startup ordering invariant preserved (ECAPA pool warm-up BEFORE vision task spawn AND AFTER AdaFace + Whisper pool warm-ups)

3. **CLAUDE.md canonical doctrine body extension** at Phase 6 per auditor's Phase 0 architect-handoff item 1:
   - Add P0.R6.Y 7th instance entry with SURFACE-CASCADE-AXIS sub-shape at lines ~689 (after P0.R6 entry)
   - Update "5 applications + 4-axis sub-shape taxonomy" → "7 applications + 6-axis sub-shape taxonomy" at line 656
   - Update sub-shape taxonomy enumeration at line 700 to include SURFACE-CASCADE-AXIS
   - Preserve banking note + operational rules + falsification clause per in-line lock at 763-770

4. **Closure-narrative explicit doctrine X → Y lines** (per `Implicit-doctrine-firings-not-narrative-tracked` 3rd-cycle self-sustaining adoption):
   - `### Architect-reads-production-code-before-sign-off` 19 → 20 firing at closure-audit (explicit X → Y narrative line required)
   - `### Pre-audit-quantifier-precision-refined-by-grep` 6 → 7 firing (SURFACE-CASCADE-AXIS NEW sub-shape; first instance of cascade-aware quantifier discipline)
   - `### Phase-0-catches-wrong-premise` STAYS at 13 (pre-audit premise correct this cycle — first asyncio-blocking-correct cycle in P0.R-track)
   - `### Zero-precision-items-at-auditor-review` 22 → 23 (Plan v1 surface firing, IF cycle clears cleanly)
   - `### Phase-0-granular-decomposition-enables-accurate-estimates` 20 → 21 IF closure-actual ∈ [8, 10]
   - `Doctrine-prediction-precision-improving-over-arc` sub-observation streak extension IF closure-actual = 9 exact (13th consecutive 0%)
   - OPTIONAL-Plan-v2 sub-rule 10 → 11 proof cases at clean closure
   - `### Induction-surfaces-invariant-gaps` 12 → 13 IF deliberate-regression discovers a detector gap mid-cycle (banked observation; not committed at Plan v1)

---

**End of Plan v1.** Ready for auditor verdict.
