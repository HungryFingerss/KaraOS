# P0.R6.X — Whisper migration to ProcessPoolExecutor worker (Phase 0 audit)

**Date**: 2026-05-24
**Author**: architect (Claude)
**Cycle shape**: SMALL-MEDIUM band, foundation reused from P0.R6 `core/heavy_worker.py` infrastructure (Q1 (a) decomposition follow-up #1)
**Estimated effort**: ~2-3h SMALL-MEDIUM-band cycle

---

## §0 Pre-audit framing (LOCKED 2026-05-24 by architect BEFORE grep verification)

> "P0.R6.X migrates the Whisper STT call sites in pipeline.py to use `hw.run_heavy("whisper_transcribe", hw.whisper_transcribe_worker, ...)` like P0.R6 did for AdaFace. Closes the C-extension-blocking-asyncio-loop failure class for the Whisper path. Estimated ~2-3 STT call sites in pipeline.py + maybe 1 in core/audio.py."

Phase 0 grep verifies this framing against production code. Findings below.

---

## §1 Grep findings (Pass-1 baseline)

### §1.1 Whisper inference enumeration

Independent grep across `core/audio.py` + `pipeline.py`:

| # | Surface | File:Line | Sync/Async | Wrapped? | Migrate? |
|---|---|---|---|---|---|
| 1 | `_load_whisper()` lazy loader | core/audio.py:186 | sync (lazy) | n/a | n/a (subprocess inherits its own loader) |
| 2 | `_load_whisper()` preload site | core/audio.py:327 | sync | n/a | n/a (boot warmup; not migration target) |
| 3 | `_load_whisper()` in transcribe() body | core/audio.py:506 | sync | n/a | n/a (inside transcribe; covered transitively) |
| 4 | **`model.transcribe(...)` LOAD-BEARING inference** | **core/audio.py:507** | **sync** | **n/a** | **YES (THE migration target)** |
| 5 | `transcribe` call inside listen_and_transcribe | core/audio.py:620 | async | `run_in_executor` | n/a (caller-side; covered transitively) |
| 6 | `transcribe` direct call (multi-speaker diarize) | pipeline.py:7482 | async | `run_in_executor` | n/a (caller-side; covered transitively) |

**Refinement #1 (KEY) — `### Pre-audit-quantifier-precision-refined-by-grep` TASK-COMPLETENESS-AXIS firing**: pre-audit framing said "~2-3 STT call sites in pipeline.py + maybe 1 in core/audio.py" but grep verified **ONE production inference site** (`core/audio.py:507`). All pipeline.py "call sites" are wrappers around the single `transcribe()` public API → migration is at the `transcribe()` body level, not at the call sites.

**Refinement #2 (KEY) — sub-pattern A `### Phase-0-catches-wrong-premise` opposite-direction subspecies**: pre-audit assumed Whisper has SYNC DIRECT CALLS blocking asyncio loop (mirroring P0.R6 sites 6716 + 7112). Grep verified ALL transcribe entry points already use `run_in_executor(None, transcribe, ...)` — `core/audio.py:620` + `pipeline.py:7482`. Whisper integration is ALREADY async-loop-safe.

**Architectural consequence**: P0.R6.X migration is **NOT load-bearing for asyncio-loop-release** (release already achieved via `run_in_executor`). Migration is load-bearing for:

1. **Process isolation** — Whisper crashes/segfaults contained in worker subprocess (Whisper's ~3GB CUDA work has non-trivial segfault risk, e.g. torchaudio compat issues post-P0.R5; segfault in subprocess doesn't kill pipeline)
2. **VRAM budget tracking** — Whisper held in dedicated worker subprocess; main process VRAM remains free for other CUDA models + future multi-model parallel inference
3. **Future parallel inference** — `max_workers > 1` enables concurrent transcription for future multi-microphone or multi-speaker simultaneous-utterance scenarios
4. **Foundation reuse** — same pattern propagates to P0.R6.Y (ECAPA) + P0.R6.Z (pyannote) without further infrastructure work

This refined architectural justification matches P0.R6's sites 2569 + 2663 case (those were also already-async-wrapped at P0.R6 entry; got migrated for the same isolation reasons).

### §1.2 Cross-spec interactions (Pass-2 grep)

| Spec | Interaction | Status |
|---|---|---|
| P0.R1 | ONNX session.run() wrap for AdaFace — different model class | NO conflict (independent path) |
| P0.R2 | Provider state machine for AdaFace/buffalo_l CPU fallback | NO conflict (independent path) |
| P0.R5 | Pyannote/speechbrain vendoring — torchaudio compat patches | LOAD-BEARING (subprocess must inherit `from faster_whisper import WhisperModel` cleanly; torchaudio compat patches from fork apply uniformly at install-time per `requirements.txt` git URL; no subprocess-side action needed) |
| P0.R6 | AdaFace migration to heavy_worker — SAME infrastructure | EXTENDS (`whisper_transcribe_worker` lands in same `core/heavy_worker.py` module; `_heavy_worker_status` dict already designed for multi-task scaling per D4) |
| P0.S7.5.2 D4 | 1-word STT artifact filter in `transcribe()` | LOAD-BEARING (filter chain MUST run somewhere; Q2 adjudication: subprocess-side OR main-process-side) |
| P0.S7.5.2 D5 | Smart-Turn debounce widening in `record_until_silence` | NO conflict (record path unchanged; only transcribe migrated) |
| P0.0.7 H1 | `audio_in` event emission via `safe_emit_sync` in `listen_and_transcribe` | NO conflict (emission happens in main process AFTER transcribe; `text` argument changes from sync-return to async-await but content unchanged) |
| P0.R6 D5 | Startup pool warm-up BEFORE vision task spawn | EXTENDS (whisper_transcribe pool warm-up must land BEFORE preload_models completion gate so first Whisper call sees ready pool) |

---

## §2 Architectural justification refresh

Pre-audit framing assumed P0.R6.X = P0.R6 shape (sync sites blocking asyncio loop). Phase 0 grep verified ALL-async shape — migration justified on process-isolation + VRAM-isolation grounds, NOT on asyncio-loop-release.

This refines the spec's risk/benefit:

- **Risk**: pickle IPC overhead per call ~0.5-1ms (Q3 lock from P0.R6) for ~32-64KB audio buffers (~500-1000ms of audio at 16kHz mono float32) — acceptable for ~200-500ms Whisper inference (<1% overhead)
- **Risk**: subprocess holds Whisper model in VRAM persistently (~3GB on Jetson) → ~3GB additional VRAM committed at boot
- **Benefit**: process isolation contains Whisper crashes (high-risk class given Whisper's torchaudio + CUDA C-extension dependencies)
- **Benefit**: VRAM budget tracking enables future Jetson VRAM ceiling enforcement (cumulative cost after P0.R6.X + P0.R6.Y + P0.R6.Z: ~6.3GB across 3 worker subprocesses, fits comfortably on AGX Orin 32GB and 8-12GB dev laptops)
- **Benefit**: foundation reuse for P0.R6.Y (ECAPA) + P0.R6.Z (pyannote) without further infrastructure work

---

## §3 D-decision proposal (4 D-decisions)

**D1 (NEW worker function in `core/heavy_worker.py`)**: `whisper_transcribe_worker(audio_bytes: bytes, shape: tuple[int, ...], dtype_name: str, language: str) -> tuple[str, str]` worker entry point. Deserializes audio buffer + calls subprocess-singleton `model.transcribe(...)` + returns (raw_text, language). Filter chain (non-ASCII / char-run / word-repetition / phrase-repetition / 1-word artifact) stays in main process per Q2 (b) lean. Mirror of P0.R6 D2 `adaface_embed_worker` shape.

**D2 (subprocess singleton accessor in `core/heavy_worker.py`)**: `_SUBPROCESS_WHISPER_MODEL: Any | None = None` module-level singleton + `_get_subprocess_whisper()` accessor with lazy-load on first call (~3-5s acceptable; matches main-process behavior per Q5 (b) lean). Same pattern as P0.R6 D2 `_SUBPROCESS_EMBEDDER` + `_get_subprocess_embedder()` accessor.

**D3 (`core/audio.py::transcribe()` body migration + signature change)**: Per Q1 (a) lean, `def transcribe(audio)` → `async def transcribe(audio)`. Body inference block `model = _load_whisper(); segments, _ = model.transcribe(audio, ...)` (lines 506-519) replaced with:

```python
import core.heavy_worker as hw
raw_text, lang = await hw.run_heavy(
    "whisper_transcribe",
    hw.whisper_transcribe_worker,
    audio.tobytes(),
    audio.shape,
    audio.dtype.name,
    language=SPEAKER_LANGUAGES[0],
)
```

Filter chain (non-ASCII / char-run / repetition / 1-word artifact) STAYS in main process — runs AFTER worker returns text. Caller migration: 2 callers (`core/audio.py:620` inside `listen_and_transcribe` async wrapper + `pipeline.py:7482` in multi-speaker diarize path) — both already-async via `loop.run_in_executor`; migrate from `await loop.run_in_executor(None, transcribe, audio)` → `await transcribe(audio)` directly.

**D4 (health observability + startup wiring extension)**: Reuses P0.R6 D4 `_heavy_worker_status` dict. `set_heavy_worker_status("whisper_transcribe", "healthy")` called at startup after `hw.get_or_create_pool("whisper_transcribe")` warm-up. Ordering invariant: pool warm-up MUST land BEFORE first Whisper-using code path — specifically before `preload_models()` completion gate at `core/audio.py:327` AND before pipeline's `run()` enters first conversation cycle.

---

## §4 Anchor count proposal (Q5)

**Mid 7 INCLUSIVE ±15% band → [5.95, 8.05] → ON-TARGET = 6, 7, or 8 anchors**:

- **A1**: `whisper_transcribe_worker` function exists in `core/heavy_worker.py` (source-inspection: function definition + signature shape)
- **A2**: `_SUBPROCESS_WHISPER_MODEL` singleton + `_get_subprocess_whisper()` accessor present (source-inspection)
- **A3**: `core/audio.py::transcribe()` AST scan shows `hw.run_heavy("whisper_transcribe", ...)` Call node (positive check — migration applied)
- **A4**: `core/audio.py::transcribe()` AST scan shows `model.transcribe(audio, ...)` DIRECT call is GONE (inverse check — old sync inference must NOT remain alongside new worker call; mirrors P0.R6 A4 4-site enforcement + inverse pattern)
- **A5**: Whisper transcribe filter chain still applies AFTER worker returns text (behavioral test with mocked worker returning hallucination shapes — char-run "Mmmmm" 500×, repetition pattern, 1-word artifact)
- **A6**: HealthSnapshot reports `"whisper_transcribe"` in `_heavy_worker_status` dict (extension of P0.R6 D4 pattern; behavioral test gathers snapshot post-init)
- **A7**: Startup pool warm-up AST line-order check (`hw.get_or_create_pool("whisper_transcribe")` BEFORE `preload_models()` body OR before pipeline's vision task spawn — TBD by Plan v1 §1 line-order grep)

**Closure-projection band table** (per `### Phase-0-granular-decomposition-enables-accurate-estimates` doctrine — strict ±15% ON-TARGET bar locked at P0.S7 closure adjudication 2026-05-21):

| closure-actual | overage vs mid 7 | band classification | doctrine outcome |
|---|---|---|---|
| 5 | −28.6% | SLIGHT-DRIFT-DOWN (within ±30% falsification tolerance) | doctrine holds; observation banked |
| 6 | −14.3% | ON-TARGET | doctrine bumps 19 → 20 supporting |
| 7 | 0% | ON-TARGET exact mid | doctrine bumps 19 → 20 supporting; 12th consecutive 0% streak extends `Doctrine-prediction-precision-improving-over-arc` sub-observation |
| 8 | +14.3% | ON-TARGET | doctrine bumps 19 → 20 supporting |
| 9 | +28.6% | SLIGHT-DRIFT-UP (within ±30% falsification tolerance) | doctrine holds; observation banked |
| ≥10 OR ≤4 | beyond ±30% | FALSIFICATION TRIGGER | doctrine demotes back to architect-memory + reasoning audit |

If A5 collapses (filter chain stays in `transcribe()` body and the AST scan in A3+A4 already catches the missing model.transcribe call), drop to 6 anchors. If Plan v1 absorbs an additional concern (e.g. CUDA-gated behavioral smoke test as A8), bump to 8.

---

## §5 OUT-OF-SCOPE classification

1. **`record_until_silence` migration** — separate concern (audio capture is sounddevice not torch/CUDA; sync sounddevice calls in `record_until_silence` are blocking but covered by existing `run_in_executor` wrapper at `listen_and_transcribe`). Not P0.R6.X scope.
2. **Whisper model parameter tuning** — `beam_size=5`, `no_speech_threshold=0.7`, `compression_ratio_threshold=2.4`, etc. stay as-is. P0.R6.X is migration-only.
3. **Smart-Turn end-of-turn detection migration** — separate ONNX model running on CPU (~50ms). Not heavyweight enough for ProcessPoolExecutor migration. Stays in main process.
4. **TTS migration (Kokoro / Piper)** — separate concern, separate spec if needed (TTS is heavyweight but currently uses `asyncio.run_in_executor` correctly in `_play_worker`).
5. **Multi-microphone parallel transcription** — `max_workers=1` per Q7 lean (single-utterance-at-a-time semantics). If multi-microphone scenarios land, revisit with separate spec.
6. **Whisper model version bump** — `large-v3-turbo` stays. Migration-only spec; behavior preservation invariant.
7. **Filter chain refactor** — non-ASCII / char-run / repetition / 1-word artifact filters stay as-is in main process per Q2 (b) lean. P0.R6.X is migration-only.

---

## §6 Discipline-counter projections (per locked +1-per-artifact convention)

Baselines from P0.R6 closure (2026-05-24, line 3 of CLAUDE.md):

| Discipline | P0.R6 closure baseline | P0.R6.X projected at closure |
|---|---|---|
| Strict-industry-standard mode applications | 72 | 75 (Phase 0 + Plan v1 + closure) |
| Strict-mode successful closures | 21 | 22 |
| Spec-first review cycle | 81-for-81 | 84-for-84 |
| `### Grep-baseline-before-drafting` instances | 39 | 42 |
| Cross-cycle-handoff transparency successful | 45 | 48 |
| Spec-time grep-verification instances | 49 | 52 |
| `### Twin-filename-pitfall-prevention` preventive events | 21 | 22 |
| Auditor-Q5-estimates-trail-grep banked closures | 25 | 26 |
| Deferred-canary strategy applications | 23 | 24 |

OPTIONAL-Plan-v2 path candidacy: if auditor returns 0 precision items at Plan v1 review, cycle ships as 3-artifact (Phase 0 + Plan v1 + closure). 10th OPTIONAL-Plan-v2 proof case candidate post-closure.

**`### Pre-audit-quantifier-precision-refined-by-grep` doctrine instance enumeration** (post-P0.R6 elevation, doctrine library 8 doctrines):
- 1st: P0.B3 D-D Phase 0 (COUNT-axis)
- 2nd: P0.R2 §2.6(b) Phase 0 (MECHANISM-AXIS)
- 3rd: P0.R4 Q3 Phase 0 (MECHANISM-GENERALITY-AXIS)
- 4th: P0.R5 Phase 0 (LAYERED-AXIS 3-axis)
- 5th: P0.R6 Phase 0 (LAYERED-AXIS continuation 2-axis)
- **6th**: P0.R6.X Phase 0 (TASK-COMPLETENESS-AXIS — pre-audit "~2-3 sites" refined to "1 inference site")

---

## §7 Q-questions for adjudication

**Q1 (sync→async signature change in `transcribe()`)**:
`core/audio.py::transcribe()` currently has signature `def transcribe(audio: np.ndarray) -> tuple[str, str]:` (sync). Migration to `hw.run_heavy(...)` requires async signature.

- Option (a): change to `async def transcribe(audio)` + update 2 callers (both already in async contexts via `run_in_executor`).
- Option (b): keep sync signature; do `asyncio.run(hw.run_heavy(...))` inside transcribe() body.

**Architect lean: (a)** — clean async signature; both callers already-async via executor wrapping so they can `await` directly. (b) introduces nested event loop anti-pattern (`asyncio.run` inside running loop → RuntimeError).

**Caller migration scope**: 2 sites need `await loop.run_in_executor(None, transcribe, ...)` → `await transcribe(...)`:
- `core/audio.py:620` (inside `listen_and_transcribe` body)
- `pipeline.py:7482` (multi-speaker diarize path)

Plus 3 test surfaces (`tests/conftest.py:80-81`, `test_executor.py:259-279`, `test_pipeline.py:68-69`) that may need test-side adaptation — banked observation, NOT scope creep.

**Q2 (filter chain location — load-bearing per §1.2)**:
Whisper post-transcribe filters (non-ASCII / char-run / repetition / 1-word artifact) MUST run somewhere.

- Option (a): all filters in worker subprocess, worker returns final filtered text.
- Option (b): worker returns raw text, filters run in main process.

**Architect lean: (b)** — filters are pure-Python regex with no CUDA work; running them in main process keeps subprocess code surface minimal + dodges the cost of importing `core.config` (STT_KNOWN_IMPERATIVES) in every worker subprocess.

**Q3 (IPC payload shape)**:
Audio buffer pickling across subprocess boundary.

- Option (a): explicit tuple `(bytes, shape, dtype_name)` matching P0.R6 D2 `adaface_embed_worker` pattern.
- Option (b): pickle ndarray directly (lets numpy handle wire format).

**Architect lean: (a)** — explicit shape carries semantic intent + dodges numpy version skew across subprocess boundary + matches P0.R6 precedent for cross-pattern consistency.

**Q4 (return shape from worker)**:
`whisper_transcribe_worker` return value.

- Option (a): `tuple[str, str]` (filtered_text, language) — matches `transcribe()` public API.
- Option (b): `tuple[str, str]` (raw_text, language) — main process applies filters AFTER.

**Architect lean: (b)** — per Q2 (b) lean.

**Q5 (eager vs lazy model load in subprocess)**:
Whisper model load ~3-5s first call.

- Option (a): eager load at subprocess startup (foreground 3-5s startup latency, no first-call penalty).
- Option (b): lazy load on first call (no startup penalty; ~3-5s first-call latency only on cold start).

**Architect lean: (b)** — matches main-process pattern; first-call latency only affects first conversation turn after process restart (acceptable cost). Eager load would push 3-5s into the boot sequence which already takes ~5-10s for other model preloads; users would notice.

**Q6 (CUDA spawn requirement)**:
Same as P0.R6 Q6 (a) lock — explicit `mp.get_context("spawn")` cross-platform. P0.R6.X reuses P0.R6's `get_or_create_pool` which already enforces `"spawn"`. No new decision.

**Q7 (worker max_workers)**:
Single worker per task class. Whisper inference is sequential within a session (1 utterance at a time). Multi-microphone scenarios not in scope.

**Architect lean: max_workers=1** (matches P0.R6 default).

**Q8 (CUDA-gated behavioral smoke anchor)**:
A1-A7 source-inspection / behavioral-mocked anchors always-run. Optional CUDA-gated A8 behavioral test would construct real WhisperModel in subprocess + transcribe a fixture audio. SKIP gracefully on Windows dev / Linux CI without GPU.

**Architect lean: defer to Plan v1** — Phase 0 mid 7 covers source-inspection floor; Plan v1 absorbs A8 if auditor surfaces test surface gap. If accepted, anchor count bumps to 8 (still ON-TARGET within ±15% INCLUSIVE band).

---

## §8 Doctrine-firing events at closure (projection)

If P0.R6.X closes cleanly with closure-actual = 7 anchors at exact mid:

- `### Phase-0-granular-decomposition-enables-accurate-estimates` 19 → 20 supporting (12th consecutive 0% exact-mid → `Doctrine-prediction-precision-improving-over-arc` sub-observation streak extends)
- `### Phase-0-catches-wrong-premise` 12 → 13 instances (sub-pattern A opposite-direction subspecies — Whisper pre-audit "asyncio-loop blocking" refined to "process-isolation justification")
- `### Pre-audit-quantifier-precision-refined-by-grep` 5 → 6 instances (TASK-COMPLETENESS-AXIS — pre-audit "~2-3 sites" refined to "1 inference site")
- `### Zero-precision-items-at-auditor-review` 19 → 21 instances (Phase 0 verdict + Plan v1 verdict = 2 surfaces if cycle clears cleanly)
- OPTIONAL-Plan-v2 sub-rule track record 9 → 10 proof cases (if 3-artifact cycle ships)
- `### Architect-reads-production-code-before-sign-off` 18 → 19 at closure-audit (per `Implicit-doctrine-firings-not-narrative-tracked` 3rd-cycle self-sustaining adoption — explicit X → Y narrative line)
- Strict-industry-standard mode 72 → 75 applications + 21 → 22 closures
- Spec-first review cycle 81 → 84-for-84 at closure
- `### Grep-baseline-before-drafting` 39 → 42 instances
- Cross-cycle-handoff transparency 45 → 48 successful
- Spec-time grep-verification 49 → 52 instances
- `### Twin-filename-pitfall-prevention` 21 → 22 preventive events (P0.R6.X artifacts at `tests/p0_r6_x_*.md` cleanly disambiguated against P0.R6 + future P0.R6.Y/Z artifacts)
- Auditor-Q5-estimates-trail-grep 25 → 26 banked closures
- Deferred-canary strategy 23 → 24 applications

---

## §9 Architect-handoff items for auditor verdict

1. **Pass-2 grep verification** (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine): independent re-grep §1.1 6-row enumeration + §1.2 8-row cross-spec table. If auditor surfaces additional Whisper-touching sites OR cross-spec interactions, lock as Plan v1 PI #1 absorption per Option α pattern.

2. **Q1-Q8 adjudication**: confirm architect leans OR substitute. Q1 (sync→async) + Q2 (filter chain location) are LOAD-BEARING; Q3-Q8 are implementation refinements.

3. **Anchor count adjudication**: confirm mid 7 INCLUSIVE ±15% band [5.95, 8.05] OR substitute. Plan v1 lock follows auditor verdict.

4. **OUT-OF-SCOPE classification**: confirm §5 enumeration OR flag items that warrant in-scope inclusion. Test-side migration (3 surfaces in `tests/conftest.py` + `test_executor.py` + `test_pipeline.py`) is currently banked as observation; Plan v1 will explicitly classify as in-scope OR follow-up cycle.

5. **Doctrine-firing projections**: confirm §8 enumeration matches discipline track records. Specifically: `### Pre-audit-quantifier-precision-refined-by-grep` 5 → 6 instance (P0.R6.X is the 6th TASK-COMPLETENESS-AXIS instance after P0.B3 + P0.R2 + P0.R4 + P0.R5 + P0.R6).

---

**End of Phase 0 audit.** Ready for auditor verdict.
