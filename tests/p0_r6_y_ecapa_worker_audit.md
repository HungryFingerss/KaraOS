# P0.R6.Y — ECAPA voice ID migration to ProcessPoolExecutor worker (Phase 0 audit)

**Date**: 2026-05-24
**Author**: architect (Claude)
**Cycle shape**: MEDIUM band, foundation reused from P0.R6 `core/heavy_worker.py` infrastructure (Q1 (a) decomposition follow-up #2 — after P0.R6.X Whisper)
**Estimated effort**: ~3-4h MEDIUM-band cycle (larger surface than P0.R6.X — 5-function async cascade + 1 LOAD-BEARING sync-direct-call fix)

---

## §0 Pre-audit framing (LOCKED 2026-05-24 by architect BEFORE grep verification)

> "P0.R6.Y migrates the ECAPA-TDNN speaker identification calls in `core/voice.py` to use `hw.run_heavy("ecapa_embed", hw.ecapa_embed_worker, ...)` like P0.R6 + P0.R6.X did for AdaFace + Whisper. ECAPA voice ID inference also blocks asyncio loop. Slightly larger surface (more call sites in `core/voice.py` + diarize path). ~3-4h cycle. Smaller VRAM footprint (~200MB ECAPA model)."

Phase 0 grep verifies framing against production. Findings below.

---

## §1 Grep findings (Pass-1 baseline)

### §1.1 ECAPA inference enumeration

Independent grep across `core/voice.py` + `core/voice_channel.py` + `pipeline.py`:

| # | Surface | File:Line | Sync/Async | Wrapped? | Migrate? |
|---|---|---|---|---|---|
| 1 | `load_speaker_embedder()` model loader | core/voice.py:69 | sync (boot) | n/a | n/a (subprocess inherits its own loader) |
| 2 | `_embedder` module-level singleton | core/voice.py:39 | n/a | n/a | n/a (subprocess holds its own singleton) |
| 3 | **`_embedder.encode_batch(signal)` LOAD-BEARING inference** | **core/voice.py:141** | **sync** | **n/a** | **YES (THE D3 migration target — inside `embed()` body)** |
| 4 | `embed()` public API | core/voice.py:121 (def) | sync → async | n/a | YES — D3 signature change |
| 5 | `identify()` public API | core/voice.py:459 (def) | sync → async | n/a (calls embed internally) | YES — D3 signature cascade (embed→identify) |
| 6 | `_diarize_ecapa_valley()` legacy backend | core/voice.py:152 (def) | sync → async | n/a (calls embed in window loop + identify per segment) | YES — D3 signature cascade |
| 7 | `_diarize_pyannote()` pyannote backend | core/voice.py:~289 (def) | sync → async | n/a (calls identify per segment at line 395) | YES — D3 signature cascade |
| 8 | `diarize()` public dispatcher | core/voice.py:~404 (def) | sync → async | n/a (dispatches to _diarize_pyannote OR _diarize_ecapa_valley) | YES — D3 signature cascade |
| 9 | `get_diarize_executor()` dedicated thread pool | core/voice.py:50 | n/a | n/a | n/a (pyannote-backend isolation stays; pyannote pipeline itself OUT-OF-SCOPE for P0.R6.Y) |

**Refinement #1 — `### Pre-audit-quantifier-precision-refined-by-grep` SURFACE-CASCADE-AXIS firing** (NEW sub-shape candidate): pre-audit framing said "ECAPA inference calls in `core/voice.py`" implying single-primitive migration. Grep verified **5-function async cascade** (`embed → identify → _diarize_ecapa_valley → _diarize_pyannote → diarize`) — all callers transitively change signature when the primitive does. This is structurally distinct from prior axis sub-shapes:

- COUNT-axis (P0.B3 D-D): pre-audit overcounted; grep undercount-corrected
- MECHANISM-AXIS (P0.R2): pre-audit overstated; grep verified partial fix existed
- MECHANISM-GENERALITY-AXIS (P0.R4): pre-audit specific; grep showed contract uniform across implementations
- LAYERED-AXIS (P0.R5 + P0.R6): pre-audit multi-axis refined together
- TASK-COMPLETENESS-AXIS (P0.R6.X): pre-audit "~2-3 sites" refined to "1 inference site + N callers"
- **SURFACE-CASCADE-AXIS (P0.R6.Y candidate)**: pre-audit "ECAPA inference" refined to "5-function async cascade from `embed()` primitive through 4 transitively-affected wrappers"

The cascade depth is a property the pre-audit framing didn't capture; grep verification surfaces the structural cascade by enumerating all wrappers around the primitive.

**Refinement #2 (LOAD-BEARING) — sub-pattern A `### Phase-0-catches-wrong-premise` confirmation NOT applicable**: pre-audit framing was CORRECT this time. "ECAPA voice ID inference also blocks asyncio loop" — verified TRUE at site `pipeline.py:7148` (SYNC DIRECT CALL `v_pid, v_score = voice_mod.identify(...)` inside async function). This is materially different from P0.R6.X case where the pre-audit "blocks asyncio loop" was wrong.

P0.R6.Y has 1 NET-NEW asyncio-loop-release improvement at site 7148 (mirror of P0.R6 PI #1 sites 6716 + 7112). Migration justification is LOAD-BEARING for asyncio-loop-release AT THIS SITE in addition to process-isolation + VRAM-isolation.

### §1.2 Pipeline.py caller enumeration

| # | Caller | File:Line | Current shape | Post-D3 shape | Asyncio-blocking? |
|---|---|---|---|---|---|
| 1 | voice ID for known-voice match | `pipeline.py:2274` | `await loop.run_in_executor(None, voice_mod.identify, ...)` | `await voice_mod.identify(...)` | NO (already async-wrapped) |
| 2 | embedding for voice gallery write | `pipeline.py:2304` | `emb = await loop.run_in_executor(None, voice_mod.embed, audio)` | `emb = await voice_mod.embed(audio)` | NO (already async-wrapped) |
| 3 | **voice-first ambient identify** | **`pipeline.py:7148`** | **`v_pid, v_score = voice_mod.identify(...)` SYNC DIRECT CALL** | **`v_pid, v_score = await voice_mod.identify(...)`** | **YES — LOAD-BEARING ASYNCIO FIX** |
| 4 | conversation-turn voice identify | `pipeline.py:7414` | `await loop.run_in_executor(None, voice_mod.identify, ...)` | `await voice_mod.identify(...)` | NO (already async-wrapped) |
| 5 | multi-speaker diarize dispatch | `pipeline.py:7450` | `await _ev_loop.run_in_executor(voice_mod.get_diarize_executor(), voice_mod.diarize, ...)` | `await voice_mod.diarize(...)` (now async; pyannote pipeline INSIDE diarize still runs via get_diarize_executor) | NO (already async-wrapped; signature ripple) |

**Pipeline.py caller migration count**: 5 production sites. Site 7148 is the LOAD-BEARING asyncio-release fix; sites 2274/2304/7414/7450 are signature-cascade migrations.

### §1.3 Voice_channel.py + test enumeration

| # | Surface | File:Line | Current | Post-D3 |
|---|---|---|---|---|
| 1 | `identify_speaker` body | `core/voice_channel.py:175, 192` | `await _maybe_run_in_executor(diarize_fn, ...)` + `await _maybe_run_in_executor(identify_fn, ...)` | Helper detects `iscoroutinefunction` and `await fn(...)` direct (per line 92-93 logic; no changes needed to helper) |
| 2 | test stubs (`tests/conftest.py`, `test_pipeline.py:6375/6452/6494/6496`) | various | `with patch("core.voice.embed", return_value=...)` | Stubs become `async def` to match production signature (mirror of P0.R6.X stub-signature ripple per `Plan-v1-Pass-2-grep-undercount` 8th instance) |
| 3 | reconciler comments | `core/reconciler.py:612/649` | docstring references "voice.identify() returns" | unchanged (commentary only) |

**Voice_channel.py auto-detects coroutines**: the existing `_maybe_run_in_executor` helper (lines 87-95 of voice_channel.py) already handles both sync and async via `inspect.iscoroutinefunction(fn)` check. No changes needed to the helper itself; signature change in voice.py propagates transparently.

**Test stub migration count**: 4 patch sites in `test_pipeline.py` may need `AsyncMock` instead of `MagicMock` patches OR `async def` wrapper functions. Banked at §1.3 for Plan v1 detailed enumeration.

### §1.4 Cross-spec interactions (Pass-2 grep)

| Spec | Interaction | Status |
|---|---|---|
| P0.R5 | Vendored speechbrain fork (`HungryFingerss/speechbrain @ a9b05847`) | LOAD-BEARING (subprocess must inherit `from speechbrain.inference.speaker import EncoderClassifier` cleanly; vendored fork's torch_audio_backend patches apply uniformly at install-time per `requirements.txt` git URL; HF_TOKEN auth pattern unchanged) |
| P0.R6 | AdaFace migration to heavy_worker — SAME infrastructure | EXTENDS (`ecapa_embed_worker` lands in same `core/heavy_worker.py` module; `_heavy_worker_status` dict extends for ecapa_embed key) |
| P0.R6.X | Whisper migration — SAME infrastructure pattern | EXTENDS (3rd task class joining heavy_worker pool; sync→async cascade discipline established at P0.R6.X) |
| P0.R6.Z | Pyannote migration (FUTURE — NOT P0.R6.Y scope) | INTERACTS — pyannote's internal speechbrain ECAPA usage stays in main process at P0.R6.Y; P0.R6.Z migrates pyannote pipeline + retires `get_diarize_executor()` |
| P0.S7.5.2 D4 | 1-word STT artifact filter (Whisper-side) | NO conflict (different model class) |
| P0.0.7 H3 | `identity_claim` event emission | NO conflict (emission happens in main process AFTER voice ID; signature change ripple at boundary) |
| Session 119 / P5 | reconciler negative-cosine fix — `voice.identify()` returns actual cosine including negatives | NO conflict (return shape preserved through subprocess boundary; only signature changes async, not semantic) |
| Session 88 / P2 | `_diarize_pyannote` + `_diarize_ecapa_valley` dispatch logic | LOAD-BEARING (dispatch stays in `diarize()` body; signature cascade preserves return-shape contract `[{start_sample, end_sample, speaker_id, speaker_score, speaker_label}]`) |

---

## §2 Architectural justification refresh

Pre-audit framing was CORRECT on the LOAD-BEARING asyncio-blocking premise (site 7148 SYNC DIRECT CALL verified). Phase 0 grep ADDS:

1. **SURFACE-CASCADE-AXIS quantifier refinement**: 5-function async cascade (`embed → identify → _diarize_ecapa_valley → _diarize_pyannote → diarize`) per `### Pre-audit-quantifier-precision-refined-by-grep` 6 → 7 candidate (NEW sub-shape; first instance of cascade-aware quantifier discipline).

2. **VRAM budget refinement**: pre-audit said "~200MB ECAPA model"; grep + `load_speaker_embedder()` source confirms ECAPA-TDNN model ~80MB on disk + ~150-200MB CUDA context at runtime. Cumulative after P0.R6 + P0.R6.X + P0.R6.Y: ~100MB (AdaFace) + ~3GB (Whisper) + ~200MB (ECAPA) = ~3.3GB across 3 worker subprocesses. Document in Known Limitations.

3. **Pyannote interaction clarification (OUT-OF-SCOPE for P0.R6.Y)**: pyannote pipeline at `_load_pyannote_pipeline()` uses speechbrain ECAPA INTERNALLY (P0.R5 inherits speechbrain via pyannote's segmentation dependency). P0.R6.Y migrates the EXPLICIT `embed()` / `identify()` calls in `core/voice.py`; pyannote's internal ECAPA usage stays in main process via `get_diarize_executor()` dedicated thread. P0.R6.Z (pyannote migration) addresses pyannote-internal ECAPA + retires `get_diarize_executor()`.

This refines the risk/benefit:

- **Risk**: pickle IPC overhead per call ~0.5-1ms for ~24000-sample audio buffers (1.5s at 16kHz mono float32) — acceptable for ~30-50ms ECAPA inference (~1-2% overhead).
- **Risk**: `_diarize_ecapa_valley` sliding-window loop makes 10-20 `embed()` calls per diarize op → ~10-20ms cumulative IPC overhead per legacy-fallback diarize. Pyannote-backend primary path makes only 2-5 identify() calls (per segment) → ~2-5ms IPC overhead. Both acceptable.
- **Risk**: subprocess holds ECAPA model ~200MB VRAM persistently. After P0.R6+R6.X+R6.Y: ~3.3GB cumulative across 3 subprocess workers + ~1GB main process = ~4.3GB. Comfortably below Jetson 24GB CUDA budget and dev laptop 8-12GB.
- **Benefit**: site 7148 SYNC DIRECT CALL no longer blocks asyncio loop (~50-100ms per call) — LOAD-BEARING fix.
- **Benefit**: process isolation contains speechbrain crashes (speechbrain has had memory leak history per upstream issues; subprocess containment mitigates).
- **Benefit**: VRAM budget tracking continues across 3 task classes (foundation for P0.R6.Z).
- **Benefit**: foundation reuse for P0.R6.Z (pyannote) — clean separation of ECAPA-side speechbrain from pyannote-internal speechbrain prepares the migration boundary.

---

## §3 D-decision proposal (4 D-decisions)

**D1 (NEW worker function in `core/heavy_worker.py`)**: `ecapa_embed_worker(audio_bytes: bytes, shape: tuple[int, ...], dtype_name: str, sample_rate: int) -> "bytes | None"` worker entry point. Deserializes audio buffer + calls subprocess-singleton ECAPA model + serializes 192-dim float32 embedding bytes (192 × 4 = 768 bytes). Mirror of P0.R6 D2 `adaface_embed_worker` + P0.R6.X D1 `whisper_transcribe_worker` shape. Returns None on cascading failure (preserves P0.R1 D1 None-return fallback contract).

**D2 (subprocess singleton accessor in `core/heavy_worker.py`)**: `_SUBPROCESS_ECAPA_EMBEDDER: Any | None = None` module-level singleton + `_get_subprocess_ecapa()` accessor with lazy-load on first call (~1-2s acceptable). Same pattern as P0.R6 D2 + P0.R6.X D2.

**D3 (signature cascade across 5 functions in `core/voice.py` + body migration in `embed()`)**: Per Q1 (a) sync→async cascade lock from P0.R6.X precedent:

```python
# core/voice.py:121
# BEFORE
def embed(audio: np.ndarray, sample_rate: int = MIC_SAMPLE_RATE) -> "np.ndarray | None":
# AFTER
async def embed(audio: np.ndarray, sample_rate: int = MIC_SAMPLE_RATE) -> "np.ndarray | None":

# Body migration at line 139-149 (the encode_batch block)
# BEFORE
signal = torch.from_numpy(audio.astype(np.float32)).unsqueeze(0)
try:
    with torch.no_grad():
        emb = _embedder.encode_batch(signal)
    emb = emb.squeeze().cpu().numpy()
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    return emb.astype(np.float32)
except Exception as e:
    print(f"[Voice] Embedding failed: {e}")
    return None
# AFTER
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
return emb.copy()  # detach from buffer
```

Cascade signature change: `embed` + `identify` + `_diarize_ecapa_valley` + `_diarize_pyannote` + `diarize` all become `async def`. Internal calls between these wrappers change from `func(...)` to `await func(...)`. The pyannote `Pipeline.__call__(...)` inside `_diarize_pyannote` retains its dedicated thread pool dispatch via `await loop.run_in_executor(get_diarize_executor(), pipeline.__call__, ...)`.

**D4 (health observability + startup wiring extension)**: Reuses P0.R6 D4 `_heavy_worker_status` dict. Add `"ecapa_embed"` key with initial "healthy" status. Startup pool warm-up `hw.get_or_create_pool("ecapa_embed")` lands immediately after Whisper pool warm-up (and before vision task spawn) — ORDERING INVARIANT preserved.

---

## §4 Anchor count proposal (Q5)

**Mid 9 INCLUSIVE ±15% band → [7.65, 10.35] → ON-TARGET = 8, 9, or 10 anchors**:

- **A1**: `ecapa_embed_worker` function exists in `core/heavy_worker.py` (source-inspection)
- **A2**: `_SUBPROCESS_ECAPA_EMBEDDER` singleton + `_get_subprocess_ecapa()` accessor present (source-inspection)
- **A3**: `core/voice.py::embed()` body AST shows `hw.run_heavy("ecapa_embed", ...)` Call node (positive check — body migration applied)
- **A4**: `core/voice.py::embed()` body AST shows `_embedder.encode_batch(` DIRECT call is GONE (inverse check; old sync inference must NOT remain alongside new worker call)
- **A5**: 5 ECAPA-touching functions (`embed`, `identify`, `_diarize_ecapa_valley`, `_diarize_pyannote`, `diarize`) all have `async def` signatures (AST signature-cascade check)
- **A6**: `pipeline.py:7148` SYNC DIRECT CALL migrated to `await voice_mod.identify(...)` (LOAD-BEARING asyncio-release fix; AST positive `await` + inverse check that direct sync call is gone)
- **A7**: 5 pipeline.py caller sites (2274, 2304, 7148, 7414, 7450) all use direct `await voice_mod.X(...)` (positive); `run_in_executor(None, voice_mod.embed/identify, ...)` and `run_in_executor(get_diarize_executor(), voice_mod.diarize, ...)` patterns are GONE for these 5 sites (inverse; AST count check)
- **A8**: HealthSnapshot reports `"ecapa_embed"` in `_heavy_worker_status` dict (D4 extension; behavioral test)
- **A9**: Startup pool warm-up AST line-order check (`hw.get_or_create_pool("ecapa_embed")` BEFORE vision task spawn + AFTER AdaFace + Whisper pool warm-ups)

**Closure-projection band table** (per `### Phase-0-granular-decomposition-enables-accurate-estimates` doctrine):

| closure-actual | overage vs mid 9 | band | doctrine outcome |
|---|---|---|---|
| 7 | −22.2% | SLIGHT-DRIFT-DOWN (within ±30%) | doctrine HOLDS at 20 supporting; observation banked |
| 8 | −11.1% | ON-TARGET | doctrine bumps 20 → 21 supporting |
| 9 | 0% | ON-TARGET exact mid | doctrine bumps 20 → 21 supporting; 13th consecutive 0% streak extends `Doctrine-prediction-precision-improving-over-arc` sub-observation |
| 10 | +11.1% | ON-TARGET | doctrine bumps 20 → 21 supporting |
| 11 | +22.2% | SLIGHT-DRIFT-UP (within ±30%) | doctrine HOLDS at 20 supporting; observation banked |
| ≥12 OR ≤6 | beyond ±30% | FALSIFICATION TRIGGER | doctrine demotes back to architect-memory + reasoning audit |

---

## §5 OUT-OF-SCOPE classification

1. **Pyannote pipeline migration to subprocess** — P0.R6.Z scope. Pyannote pipeline at `_load_pyannote_pipeline()` + `_diarize_pyannote()` body's `self._pipeline(...)` call stays in main process via `get_diarize_executor()` dedicated thread. Pyannote-internal speechbrain ECAPA stays in main process.
2. **`get_diarize_executor()` retirement** — P0.R6.Z scope. P0.R6.Y preserves it for pyannote pipeline dispatch.
3. **`_load_speaker_embedder()` main-process retirement** — DEFERRED. Main-process embedder stays loaded for legacy code paths during transition. P0.R6.Z OR a separate cleanup cycle may retire it once all callers are subprocess-routed.
4. **Diarize cosine threshold tuning** — `VOICE_RECOGNITION_THRESHOLD`, `DIARIZE_CHANGE_THRESH`, etc. stay as-is. Migration-only spec.
5. **HF_TOKEN auth migration** — speechbrain ECAPA-TDNN model load uses HF_TOKEN per P0.R5 pattern. Subprocess inherits env vars at spawn time; no auth migration needed.
6. **Test stubs in `test_pipeline.py:6375/6452/6494/6496`** — IN-SCOPE for Plan v1 §1.3 enumeration; may require AsyncMock OR async wrapper. Banked observation; Plan v1 details.

---

## §6 Locked-down discipline counters

**`### Pre-audit-quantifier-precision-refined-by-grep` doctrine instance enumeration** (post-P0.R6.X closure baseline; CLAUDE.md canonical at lines 646-770):

- 1st: P0.B3 D-D Phase 0 (COUNT-axis)
- 2nd: P0.R2 §2.6(b) Phase 0 (MECHANISM-AXIS)
- 3rd: P0.R4 Q3 Phase 0 (MECHANISM-GENERALITY-AXIS)
- 4th: P0.R5 Phase 0 (LAYERED-AXIS 3-axis)
- 5th: P0.R6 Phase 0 (LAYERED-AXIS continuation 2-axis)
- 6th: P0.R6.X Phase 0 (TASK-COMPLETENESS-AXIS)
- **7th**: P0.R6.Y Phase 0 (SURFACE-CASCADE-AXIS — NEW sub-shape: pre-audit "ECAPA inference" refined to "5-function async cascade")

Per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine: auditor DILIGENT Pass-2 grep at Plan v1 §1 will independently verify §1.1 9-row enumeration + §1.2 5-row caller table + §1.3 voice_channel + test surfaces. Any drift → Plan v1 PI #1 absorption per Option α pattern.

---

## §7 Q-questions for adjudication

**Q1 (sync→async signature cascade across 5 functions in `core/voice.py`)**:
Per P0.R6.X precedent. Cascade `embed → identify → _diarize_ecapa_valley → _diarize_pyannote → diarize` all become `async def`.

- Option (a): cascade async signature (P0.R6.X precedent)
- Option (b): only `embed()` becomes async; wrappers use sync-bridge (`asyncio.run` OR `Future.result()`)

**Architect lean: (a)** — clean signature cascade matches P0.R6.X precedent. Option (b) introduces nested-event-loop anti-pattern OR thread-blocking sync-bridge that defeats the asyncio-release benefit.

**Q2 (`_diarize_pyannote` body — pyannote `Pipeline.__call__` dispatch)**:
Pyannote pipeline is sync C extension running on `get_diarize_executor()` dedicated thread.

- Option (a): inside async `_diarize_pyannote`, dispatch pyannote pipeline call via `await loop.run_in_executor(get_diarize_executor(), pipeline.__call__, ...)`
- Option (b): retire `get_diarize_executor()` and run pyannote on default executor

**Architect lean: (a)** — preserves dedicated thread isolation for pyannote (Session 88 P2 isolation reason: pyannote 100-500ms budget separated from default 12-worker executor). P0.R6.Z migrates pyannote to subprocess + retires `get_diarize_executor()` cleanly.

**Q3 (IPC payload shape)**:
Audio buffer pickling across subprocess boundary.

- Option (a): explicit tuple `(bytes, shape, dtype_name, sample_rate)` matching P0.R6.X precedent
- Option (b): pickle ndarray directly

**Architect lean: (a)** — explicit shape carries semantic intent + dodges numpy version skew + matches P0.R6 + P0.R6.X precedent for cross-pattern consistency.

**Q4 (return shape from worker)**:
ECAPA embedding is 192-dim float32 array (~768 bytes after L2-normalization).

- Option (a): return raw `bytes` (192 × 4 = 768 bytes); main process L2-normalizes
- Option (b): return raw `bytes` already-L2-normalized in subprocess

**Architect lean: (b)** — subprocess does L2-normalization (numpy work, cheap; keeps main-process body minimal). Mirror of P0.R6 D2 contract (subprocess returns embedding ready for downstream use).

**Q5 (eager vs lazy model load in subprocess)**:
ECAPA model load ~1-2s first call.

**Architect lean: (b) lazy load on first call** — matches P0.R6 + P0.R6.X precedent. First-call latency only affects first voice-ID after subprocess spawn.

**Q6 (CUDA spawn requirement)**:
Same as P0.R6 + P0.R6.X. Reuses `get_or_create_pool` which enforces `mp.get_context("spawn")`. No new decision.

**Q7 (worker max_workers)**:
Single worker per task class.

**Architect lean: max_workers=1** (matches P0.R6 + P0.R6.X default; ECAPA inference is sequential within a session).

**Q8 (`_diarize_ecapa_valley` N× IPC overhead)**:
Legacy fallback path calls `embed()` per window in sliding-window loop (10-20 calls per diarize op).

- Option (a): accept N× IPC overhead (~10-20ms per diarize call); legacy path is fallback only, primary is pyannote-backend
- Option (b): add batch-embed worker entry point `ecapa_embed_batch_worker(audio_chunks)` that processes the sliding window subprocess-side
- Option (c): keep `_diarize_ecapa_valley` body in main process via embed-sync-wrapper; degrades async benefit but preserves perf

**Architect lean: (a)** — accept overhead. Legacy path is rarely invoked (pyannote primary); 10-20ms additional per fallback call is acceptable. Option (b) adds API surface; option (c) defeats async benefit. Document in Known Limitations.

---

## §8 Doctrine-firing projections at closure

If P0.R6.Y closes cleanly with closure-actual = 9 anchors at exact mid:

- `### Phase-0-granular-decomposition-enables-accurate-estimates` 20 → 21 supporting
- 13th consecutive 0% exact-mid streak extends `Doctrine-prediction-precision-improving-over-arc` sub-observation
- `### Pre-audit-quantifier-precision-refined-by-grep` 6 → 7 instances (SURFACE-CASCADE-AXIS — NEW sub-shape; sub-shape taxonomy grows)
- `### Phase-0-catches-wrong-premise` STAYS at 13 (P0.R6.Y was ON-TARGET premise; no Phase 0 falsification)
- `### Zero-precision-items-at-auditor-review` 21 → 23 (Phase 0 + Plan v1 if cycle clears cleanly)
- OPTIONAL-Plan-v2 sub-rule track record 10 → 11 proof cases (if 3-artifact cycle ships)
- `### Architect-reads-production-code-before-sign-off` 19 → 20 at closure-audit (3rd-cycle self-sustaining adoption per `Implicit-doctrine-firings-not-narrative-tracked` operational rule)
- Strict-industry-standard mode 75 → 78 applications + 22 → 23 closures
- Spec-first review cycle 84 → 87-for-87 at closure
- `### Grep-baseline-before-drafting` 42 → 45 instances
- Cross-cycle-handoff transparency 48 → 51 successful
- Spec-time grep-verification 52 → 55 instances
- `### Twin-filename-pitfall-prevention` 22 → 23 preventive events
- Auditor-Q5-estimates-trail-grep 26 → 27 banked closures
- Deferred-canary strategy 24 → 25 applications

---

## §9 Architect-handoff items for auditor verdict

1. **Pass-2 grep verification** (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine): independent re-grep §1.1 9-row ECAPA inference enumeration + §1.2 5-row pipeline.py caller table + §1.3 voice_channel + test surfaces table + §1.4 8-row cross-spec table. If auditor surfaces additional ECAPA-touching sites OR cross-spec interactions, lock as Plan v1 PI #1 absorption per Option α pattern.

2. **Q1-Q8 adjudication**: confirm architect leans OR substitute. Q1 (sync→async cascade) + Q2 (pyannote dispatch retention) + Q8 (`_diarize_ecapa_valley` N× overhead) are LOAD-BEARING; Q3-Q7 are implementation refinements.

3. **Anchor count adjudication**: confirm mid 9 INCLUSIVE ±15% band [7.65, 10.35] OR substitute.

4. **SURFACE-CASCADE-AXIS NEW sub-shape**: confirm 7th instance of `### Pre-audit-quantifier-precision-refined-by-grep` qualifies as NEW sub-shape (cascade-depth quantifier) per the doctrine's operational-rule-4 ("Sub-shape taxonomy grows when a genuinely NEW failure-mode dimension surfaces"). OR substitute as TASK-COMPLETENESS-AXIS continuation if the auditor reads it as same-axis-different-magnitude.

5. **Doctrine-firing projections**: confirm §8 enumeration matches discipline track records (post-P0.R6.X closure baselines).

---

**End of Phase 0 audit.** Ready for auditor verdict.
