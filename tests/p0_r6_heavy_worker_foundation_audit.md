# P0.R6 — Heavy-task worker foundation + AdaFace migration (P0.R6 cycle decomposition; full 4-task scope = P0.R6 + P0.R6.X + P0.R6.Y + P0.R6.Z) — Phase 0 audit

**Status:** Phase 0 audit drafted 2026-05-24. APPROVED-AT-AUDITOR-REVIEW pending.

**Pre-audit framing (verbatim from parent `c:\Users\jagan\dog-ai\complete-plan.md::P0.R6`):**

> ### P0.R6 — Single asyncio loop pinned by C-extensions
>
> **Fix:** move Whisper, ECAPA, pyannote, AdaFace inference to `ProcessPoolExecutor` with one worker per heavy task. Communicate via shared memory or pickle. Asyncio loop becomes pure I/O orchestration. **Largest robustness win without Rust rewrite.**

---

## §1 — Grep-verified findings (DILIGENT Pass-2 per now-elevated `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine)

**§1.1 Pre-audit framing scope verification (4-task list grep-confirmed + 2 layered quantifier-precision refinements surfaced):**

| Pre-audit task | Grep-verified call sites in pipeline.py | Verification |
|---|---|---|
| **Whisper** (STT via `faster-whisper`) | `transcribe` at line 7413 (multi-speaker span loop) + `core/audio.py::transcribe` is the primary entry | ✓ load-bearing single function |
| **ECAPA** (voice ID via `speechbrain`) | `voice_mod.identify` at lines 2272 + 7334; `voice_mod.embed` at line 2303 | ✓ 3 call sites; module-level ECAPA model |
| **pyannote** (diarization) | `_diarize_pyannote` via `voice_mod.get_diarize_executor()` at line 6165 + line 7370 | ✓ already uses ThreadPoolExecutor (`get_diarize_executor`); migration target is the existing executor wrapper |
| **AdaFace** (face embedding) | `embedder.embed` at lines 2569 + 2663 (background vision loop ambient + per-turn) | ✓ 2 call sites; module-level ONNX session |

**Quantifier-precision refinements surfaced (`Pre-audit-quantifier-precision-refined-by-grep` candidate 5th instance — multi-axis layered):**

| Axis | Pre-audit framing | Grep-verified reality | Refinement type |
|---|---|---|---|
| **TASK-COMPLETENESS** | "Whisper, ECAPA, pyannote, AdaFace" (4-task explicit) | Also heavy + GIL-contended: **RetinaFace `detector.detect`** (line 2522, buffalo_l), **YOLO `yolo_results`** (line 6653), **FAISS `db.recognize`** (lines 2594, 2688), **EmotionAgent transformers** (line 5188), **E5 embedder** (line 6415), **Smart-Turn ONNX** (in `core/audio.py`) | Pre-audit's 4-task quantifier is approximate; "Asyncio loop becomes pure I/O orchestration" outcome is APPROXIMATE — other heavy tasks remain in ThreadPoolExecutor post-cycle |
| **SCALE-OF-WORK** | "Largest robustness win without Rust rewrite" frames it as single cycle | Genuinely multi-week work: ProcessPoolExecutor wrapper + IPC + worker lifecycle + per-task migration + cross-platform considerations + GPU memory management + comprehensive testing per task | Pre-audit framing is precise about VALUE; APPROXIMATE about SCOPE — multi-day single cycle violates `feedback_break_large_implementations.md` discipline |

**§1.2 Architect's decomposition proposal (subject to Q1 auditor adjudication):**

Per `feedback_break_large_implementations.md` discipline ("Multi-day specs ship as a sequence of sub-PRs, decomposed at spec time, not as one all-or-nothing implementation"), architect proposes 4-cycle decomposition:

| Cycle | Scope | Estimated effort |
|---|---|---|
| **P0.R6 (THIS cycle)** | **Foundation: NEW `core/heavy_worker.py` ProcessPoolExecutor wrapper + AdaFace migration as first proof-of-concept** | ~3-4 hours (SMALL-MEDIUM-band) |
| **P0.R6.X** | Whisper STT migration (4 call sites including `core/audio.py::transcribe`) | ~2-3 hours |
| **P0.R6.Y** | ECAPA voice ID migration (3 call sites; `voice_mod.identify` + `embed`) | ~2-3 hours |
| **P0.R6.Z** | Pyannote diarization migration (`_diarize_pyannote`; existing `get_diarize_executor` wrapper migration) | ~2-3 hours |

**Architect lean Q1 (a)**: decompose into 4 sub-cycles per discipline. **Architect lean Q1 (b)**: single multi-day P0.R6 cycle covering all 4 tasks (rejected by architect per discipline; auditor adjudicates).

**Rationale for AdaFace as first migration target (architect lean Q2):**
- Smallest scope: pure ONNX call (no faster-whisper feature extraction; no SpeechBrain HF pipeline; no pyannote Pipeline state)
- Smallest blast radius: 2 call sites in pipeline.py (lines 2569 + 2663); both in `_background_vision_loop`
- Smallest model: ~100MB ONNX (vs Whisper ~3GB, ECAPA ~50MB, pyannote ~150MB)
- Easiest verification: face_quality_score + recognition behavioral tests already exist
- Reference for subsequent migrations: foundation `core/heavy_worker.py` pattern validated on simplest task first

**§1.3 Cross-spec interactions:**

- **P0.R3 vision watchdog**: `_background_vision_loop` is supervised by P0.R3 watchdog; ProcessPoolExecutor for AdaFace must NOT interfere with vision_heartbeat update semantics. Worker failure → asyncio task gets exception → vision loop continues (existing P0.R1 D1 `embed()` try/except fallback handles None return).
- **P0.R1 ONNX session.run() wrap**: P0.R1 wrapped `embed()` with try/except + lazy CPU-EP fallback. ProcessPoolExecutor migration must preserve this fallback semantic — worker-side embed() includes the try/except + CPU fallback already present in `core/vision.py::FaceEmbedder.embed()`.
- **P0.R2 vision_provider_state**: CUDA/CPU provider state machine; each subprocess gets own CUDA context; subprocess-side provider state is independent. Cross-process coordination NOT needed for foundation cycle (single AdaFace worker; state-machine effectively single-process from worker's POV).
- **P0.R5 vendored pyannote**: P0.R6.Z (subsequent sub-cycle) will benefit from P0.R5's fork stability; ProcessPoolExecutor migration is orthogonal to vendoring.
- **Wave 5 health log**: NEW `heavy_worker_status` field on HealthSnapshot per D4; conditional emit when worker is degraded (similar pattern to `vision_provider=cpu` + `vision=degraded`).

**§1.4 Twin-filename pitfall 20th preventive event (greenfield-verified):**

Zero pre-existing P0.R6 artifacts (Glob `tests/p0_r6*` returned 0 matches). NEW artifacts at `tests/p0_r6_heavy_worker_foundation_*.md` + `core/heavy_worker.py` + `tests/test_p0_r6_heavy_worker_foundation.py` cleanly disambiguate. 20th preventive event candidate honored at audit drafting.

---

## §2 — Decomposed D-decisions (architect leans; auditor adjudication via Q1-Q8)

### D1 — NEW `core/heavy_worker.py` module

**Architect lean spec:**

```python
"""ProcessPoolExecutor wrapper for heavy C-extension tasks (P0.R6 foundation).

Architecture per P0.R6 Phase 0 §2.1:
- 1 ProcessPoolExecutor per heavy-task type (one worker pool per task class)
- Workers persistent (warm; loaded model state preserved across calls)
- IPC via pickle (default) for foundation cycle
- Restart-on-crash semantic via worker lifecycle management
- multiprocessing.set_start_method("spawn") for Windows + Linux cross-platform
"""
from __future__ import annotations
import asyncio
import concurrent.futures
import multiprocessing as mp
from typing import Any, Callable, Optional

_HEAVY_WORKER_POOLS: dict[str, concurrent.futures.ProcessPoolExecutor] = {}

def get_or_create_pool(task_name: str, max_workers: int = 1) -> concurrent.futures.ProcessPoolExecutor:
    """Get-or-create singleton pool per task_name. Foundation cycle: max_workers=1 per task."""
    if task_name in _HEAVY_WORKER_POOLS:
        return _HEAVY_WORKER_POOLS[task_name]
    ctx = mp.get_context("spawn")
    pool = concurrent.futures.ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx)
    _HEAVY_WORKER_POOLS[task_name] = pool
    return pool

async def run_heavy(task_name: str, fn: Callable, *args, **kwargs) -> Any:
    """Async wrapper for ProcessPoolExecutor.submit; preserves asyncio integration."""
    pool = get_or_create_pool(task_name)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(pool, lambda: fn(*args, **kwargs))

def shutdown_all_pools(wait: bool = True) -> None:
    """Shutdown all heavy-worker pools cleanly at process exit."""
    for name, pool in _HEAVY_WORKER_POOLS.items():
        pool.shutdown(wait=wait)
    _HEAVY_WORKER_POOLS.clear()
```

**Edit site:** NEW file `core/heavy_worker.py` (~80-120 LOC).

### D2 — Worker bootstrap (AdaFace model loading at subprocess startup)

**Architect lean spec:**

```python
# Inside core/heavy_worker.py
def _adaface_worker_init() -> None:
    """Called once per subprocess at startup. Loads AdaFace ONNX session.
    
    Subprocess inherits parent's filesystem state but NOT memory state;
    model must be reloaded per subprocess. Lifecycle: persistent worker
    means model loads ONCE per subprocess lifetime (typically: process lifetime).
    """
    import core.vision as vision_mod
    # Forces FaceEmbedder ONNX session construction in subprocess
    # P0.R2 D1 proactive CPU-EP fallback contract preserved
    _ = vision_mod.FaceEmbedder.get_global()

def adaface_embed_worker(face_crop_bytes: bytes, shape: tuple[int, int, int]) -> "bytes | None":
    """Worker entry point: deserialize ndarray, call embed, serialize result.
    
    IPC via pickle (default ProcessPoolExecutor mechanism) but ndarray
    serialization is bytes+shape for explicit control.
    
    Returns serialized embedding bytes (1024-dim float32 = 4096 bytes) or None
    on cascading failure (per P0.R1 D1 contract).
    """
    import numpy as np
    import core.vision as vision_mod
    face_crop = np.frombuffer(face_crop_bytes, dtype=np.uint8).reshape(shape)
    embedder = vision_mod.FaceEmbedder.get_global()
    embedding = embedder.embed(face_crop)
    if embedding is None:
        return None
    return embedding.tobytes()
```

**Edit site:** continuation of `core/heavy_worker.py`.

**Contract:**
- Worker subprocess loads AdaFace model ONCE at startup via initializer
- Subsequent calls re-use loaded model (persistent worker semantic)
- Pickle overhead: serialize face_crop (uint8 ndarray, ~12-50KB per crop) + deserialize embedding (4096 bytes)
- P0.R1 + P0.R2 fallback semantics preserved inside worker subprocess

### D3 — Migrate AdaFace call sites in pipeline.py

**Edit sites:** `pipeline.py:2569` + `pipeline.py:2663` (both in `_background_vision_loop`).

**Current pattern:**
```python
_raw_emb = await loop.run_in_executor(None, embedder.embed, _crop)
```

**Plan v1 LOCKED migration:**
```python
import core.heavy_worker as hw
# _raw_emb_bytes returned per D2 worker contract
_raw_emb_bytes = await hw.run_heavy("adaface_embed", hw.adaface_embed_worker, _crop.tobytes(), _crop.shape)
_raw_emb = np.frombuffer(_raw_emb_bytes, dtype=np.float32) if _raw_emb_bytes is not None else None
```

**Contract:** behavioral equivalence — `embed()` returns same shape + value; only the dispatch mechanism changes from ThreadPoolExecutor (default executor) to ProcessPoolExecutor (heavy_worker pool).

### D4 — Health observability

**Edit sites:** `core/pipeline_state_store.py` (NEW field `heavy_worker_status: dict[str, str] = field(default_factory=dict)`) + `core/health.py` (HealthSnapshot field + format_health_line conditional + format_health_alerts).

**Contract:** worker status states: `"healthy"` | `"degraded"` | `"unknown"`. Updated on worker crash detection. Health line emits `heavy_workers=degraded` when any worker is non-healthy. Health alerts emit actionable recovery line when persistent.

### D5 — Startup + shutdown wiring

**Edit sites:** `pipeline.py::run()` startup (warm-up AdaFace worker pool at boot) + shutdown finally block (cancel pool with timeout).

**Contract:** worker pool spawned BEFORE vision task spawn at startup (worker must be ready when `_background_vision_loop` first iteration calls `embed()`); shutdown finally cancels pool with `wait=True` + 30s timeout per worker.

### D6 — Test surface

**Architect lean:** NEW `tests/test_p0_r6_heavy_worker_foundation.py` with 10 anchors (per §3).

---

## §3 — Cross-spec impact analysis (OUT-OF-SCOPE explicit)

**IN-SCOPE (P0.R6 foundation cycle):**
- `core/heavy_worker.py` foundation per D1+D2
- AdaFace migration per D3 (2 call sites)
- Health observability per D4
- Startup/shutdown wiring per D5
- Test surface per D6

**OUT-OF-SCOPE (deferred to subsequent sub-cycles or rejected):**

| Concern | Disposition |
|---|---|
| Whisper STT migration | **P0.R6.X** subsequent cycle (4 call sites including `core/audio.py::transcribe`) |
| ECAPA voice ID migration | **P0.R6.Y** subsequent cycle (`voice_mod.identify` + `embed` 3 sites) |
| Pyannote diarization migration | **P0.R6.Z** subsequent cycle (`_diarize_pyannote` via `get_diarize_executor`) |
| RetinaFace `detector.detect` migration | **P0.R6.W** (or later) — not in pre-audit's 4-task list but heavy + GIL-contended |
| YOLO detection migration | **OUT-OF-SCOPE** (currently disabled per `VISION_YOLO_ENABLED=False`) |
| FAISS `recognize` migration | **REJECTED** — sub-millisecond cosine search; not GIL-contended at production scale |
| EmotionAgent transformers migration | **OUT-OF-SCOPE** — separate spec if profiling shows GIL contention |
| E5 embedder migration | **OUT-OF-SCOPE** — async network calls, not local C-extension |
| Smart-Turn ONNX migration | **OUT-OF-SCOPE** — sub-millisecond local inference |
| Shared memory IPC (vs pickle) | **DEFERRED** to subsequent cycle if pickle overhead becomes load-bearing (architect lean Q3 (a) pickle for foundation) |
| Multi-worker pool per task | **DEFERRED** — foundation cycle uses `max_workers=1` per task (architect lean Q4 (a) persistent single-worker) |
| Auto-restart on worker crash | **DEFERRED** — manual operator intervention per D4 health alert; auto-restart is subsequent sub-cycle |
| GPU memory pooling across workers | **REJECTED** — each subprocess gets own CUDA context by design |

---

## §4 — Pre-mortem (10 failure modes + mitigation per mode)

| # | Failure mode | Mitigation |
|---|---|---|
| 1 | Subprocess startup time blocks first `embed()` call by ~1-2s | Spawn worker pool at pipeline.py startup BEFORE vision task spawns (D5 ordering invariant); model load completes before first `embed()` dispatched |
| 2 | Pickle overhead on face_crop (~12-50KB uint8 + 4096 bytes float32) | Acceptable per back-of-envelope: ~0.5-1ms per IPC round trip; AdaFace inference is ~10-50ms; overhead is <10% per call |
| 3 | GPU memory fragmentation across subprocesses (foundation cycle: only AdaFace worker, but P0.R6.X-Z multiply the fragmentation) | Foundation cycle: 1 worker × ~100MB ONNX session = ~100MB additional VRAM; acceptable on Jetson 32GB / dev RTX. Future P0.R6.X-Z must consider total VRAM budget |
| 4 | Worker subprocess crashes (segfault in ONNX runtime; CUDA OOM) | `concurrent.futures.process.BrokenProcessPool` exception propagates to asyncio task; P0.R1 D1 `embed()` returns None on cascading failure; existing None-handling at caller sites preserves behavior |
| 5 | Windows `spawn` start method requires `if __name__ == "__main__":` guard in entry point | `pipeline.py` already has `if __name__ == "__main__":` guard at end; verify guard wraps all imports cleanly |
| 6 | Persistent worker holds model in memory indefinitely; potential VRAM leak over long-running process | Worker lifecycle: process restart on health degradation; documented as Known Limitation; future operational P0.R6.Z follow-up if leaks observed |
| 7 | Cross-platform behavior divergence (Windows spawn vs Linux fork) | `multiprocessing.set_start_method("spawn")` explicit per D1; tested on both Windows dev + Jetson Linux per A8-A9 CUDA-gated smoke tests |
| 8 | ProcessPoolExecutor cleanup on SIGINT may leave zombie subprocesses | Shutdown finally block (D5) cancels pool with `wait=True` + timeout; SIGINT propagates via Python signal handler |
| 9 | Worker function pickling fails (non-pickleable lambda or closure) | D2 `adaface_embed_worker` is module-level function (pickleable); D1 `run_heavy` uses lambda but lambda is local to caller (not pickled — only `fn(*args, **kwargs)` is) |
| 10 | Existing P0.R3 vision watchdog may misinterpret worker startup delay as vision loop staleness | Foundation cycle: warm-up worker BEFORE first `embed()` call (D5 startup ordering) — vision loop never blocks waiting for worker startup |

---

## §5 — Multi-direction invariant trace per D-decision

**D1 invariants:**
- ↑ Upstream: Python 3.10+ multiprocessing.spawn + ProcessPoolExecutor (available in stdlib)
- → Same-level: pool singleton per task_name; one worker per task in foundation cycle
- ↓ Downstream: callers use `run_heavy(task_name, fn, *args)` async wrapper

**D2 invariants:**
- ↑ Upstream: D1 pool exists at subprocess spawn time
- → Same-level: worker init loads model once; subsequent calls re-use
- ↓ Downstream: `adaface_embed_worker` returns serialized bytes; caller deserializes

**D3 invariants:**
- ↑ Upstream: D1 + D2 ship before D3 migration
- → Same-level: 2 call sites in `_background_vision_loop` migrate together (no partial migration)
- ↓ Downstream: P0.R1 D1 None-return fallback semantic preserved; caller `if embedding is None:` guards unchanged

**D4 invariants:**
- ↑ Upstream: D1 + D2 worker lifecycle in place
- → Same-level: HealthSnapshot conditional emit pattern (matches Wave 5 + P0.R2 + P0.R3 precedent)
- ↓ Downstream: operator-actionable health alert; no auto-restart in foundation cycle

**D5 invariants:**
- ↑ Upstream: `core/heavy_worker.py` import succeeds at `pipeline.py` module load
- → Same-level: worker pool spawn at startup BEFORE vision task spawn (D5 ordering invariant)
- ↓ Downstream: shutdown finally cancels pool cleanly; no zombie subprocesses

**D6 invariants:**
- ↑ Upstream: pytest collects new test file
- → Same-level: 10 anchors cover D1-D5
- ↓ Downstream: CI catches regression if foundation breaks

---

## §6 — Q5 baseline estimation (architect lean: 10 anchors at exact mid; inclusive ±15% band per locked methodology)

**Architect lean: 10 anchors at exact mid 10; inclusive ±15% band [8.5, 11.5] → 9/10/11 all qualify ON-TARGET per locked methodology from P0.S5/B5/R2/R3/R4/R5.**

| # | D | Anchor name | Type |
|---|---|---|---|
| A1 | D1 | `test_p0_r6_d1_anchor_1_heavy_worker_module_exists` | source-inspection: `core/heavy_worker.py` exists + has `get_or_create_pool` + `run_heavy` + `shutdown_all_pools` |
| A2 | D1 | `test_p0_r6_d1_anchor_2_uses_spawn_start_method` | source-inspection: `core/heavy_worker.py` body contains `mp.get_context("spawn")` (cross-platform compat) |
| A3 | D2 | `test_p0_r6_d2_anchor_1_adaface_worker_function` | source-inspection: `adaface_embed_worker` is module-level (pickleable) + accepts bytes + shape args |
| A4 | D3 | `test_p0_r6_d3_anchor_1_pipeline_uses_heavy_worker_for_adaface` | source-inspection (AST): `pipeline.py` `_background_vision_loop` body contains `hw.run_heavy("adaface_embed"` calls; does NOT contain `loop.run_in_executor(None, embedder.embed` |
| A5 | D4 | `test_p0_r6_d4_anchor_1_health_snapshot_has_worker_status` | source-inspection: HealthSnapshot has `heavy_worker_status: dict[str, str]` field |
| A6 | D4 | `test_p0_r6_d4_anchor_2_format_health_emits_worker_degraded` | source-inspection: format_health_line conditional emits `heavy_workers=degraded` substring |
| A7 | D5 | `test_p0_r6_d5_anchor_1_startup_spawns_pool_before_vision_task` | source-inspection (AST line-order): pipeline.py::run() spawns `adaface_embed` pool BEFORE `_background_vision_loop` task |
| A8 | D5 | `test_p0_r6_d5_anchor_2_shutdown_cancels_pools` | source-inspection: pipeline.py::run() shutdown finally calls `hw.shutdown_all_pools(wait=True)` with timeout |
| A9 | D2/D3 | `test_p0_r6_d3_anchor_2_adaface_embed_via_worker_returns_correct_shape` | behavioral (CUDA-gated smoke): `run_heavy("adaface_embed", adaface_embed_worker, ...)` round-trips a 224×224×3 uint8 face_crop and returns 1024-dim float32 embedding |
| A10 | D2 | `test_p0_r6_d2_anchor_2_worker_handles_none_return_from_embed` | behavioral (mocked): worker entry point handles `embed() → None` cascading failure path (P0.R1 D1 contract preserved) |

---

## §7 — Q5 LOCK (per inclusive ±15% locked methodology)

`### Phase-0-granular-decomposition-enables-accurate-estimates` bump expected at closure for closure-actual ∈ {9, 10, 11}; falsification clause active if closure-actual ∉ [8, 12].

---

## §8 — Open questions for auditor (8 Q-questions; architect leans explicit)

**Q1 — Spec decomposition: single multi-day vs sub-cycles:**
- **(a) Decompose into 4 sub-cycles** (P0.R6 foundation + AdaFace; P0.R6.X Whisper; P0.R6.Y ECAPA; P0.R6.Z pyannote)
- **(b) Single multi-day P0.R6 cycle** covering all 4 tasks per pre-audit framing
- **Architect lean: (a) decompose.** Per `feedback_break_large_implementations.md` discipline (locked); accumulates closure narratives in deferred-canary mode; smaller blast radius per cycle. Pre-audit's "Largest robustness win" is a VALUE framing, not a SINGLE-CYCLE-MANDATE.

**Q2 — First migration target (if Q1 decomposes):**
- **(a) AdaFace** — smallest scope, smallest model, smallest blast radius
- **(b) Pyannote** — already uses ThreadPoolExecutor wrapper; migration is wrapper-replacement
- **(c) Whisper** — largest direct value (longest-running call per turn)
- **Architect lean: (a) AdaFace** for foundation cycle. Reasoning per §1.2.

**Q3 — IPC mechanism:**
- **(a) Pickle** (ProcessPoolExecutor default; simple; ~0.5-1ms overhead per call)
- **(b) Shared memory** (faster; more complex; requires `multiprocessing.shared_memory.SharedMemory` allocation lifecycle)
- **Architect lean: (a) pickle** for foundation cycle. Revisit at P0.R6.X if Whisper's audio buffer IPC becomes load-bearing (16kHz × N seconds × float32 = up to 1MB per turn).

**Q4 — Worker lifecycle (persistent vs ephemeral):**
- **(a) Persistent** — workers warm; model loaded once per process lifetime; restart-on-crash
- **(b) Ephemeral** — spawn worker per call; ~1-2s startup cost per call
- **Architect lean: (a) persistent.** Matches pre-audit's "one worker per heavy task" framing. Foundation cycle: max_workers=1 per task; workers stay warm; model load cost amortized.

**Q5 — Anchor count (Q5 baseline estimation):**
- **Architect lean: 10 anchors at exact mid 10; inclusive ±15% band [8.5, 11.5]** per locked methodology.

**Q6 — Cross-platform start method:**
- **(a) Explicit `spawn`** for both Windows + Linux (slower startup than `fork` but cross-platform consistent)
- **(b) Default per-platform** (`fork` on Linux, `spawn` on Windows — divergent behavior across dev + production)
- **Architect lean: (a) explicit spawn.** Cross-platform consistency outweighs Linux fork() speed advantage.

**Q7 — GPU memory budget concerns:**
- **Architect lean — DOCUMENT but DEFER**: foundation cycle (1 AdaFace worker) adds ~100MB VRAM; acceptable on Jetson 32GB + dev RTX. P0.R6.X-Z multiply VRAM usage (~3GB Whisper + ~50MB ECAPA + ~150MB pyannote = ~3.3GB additional total). Document as Known Limitation in §5.1 closure narrative; future operational spec if VRAM ceiling hit. NOT a blocking concern for foundation cycle.

**Q8 — Test surface scope:**
- **(a) Hybrid** source-inspection + CUDA-gated behavioral (per Q6 P0.R4 precedent — runs on Windows dev + Linux CI; CUDA-gated tests SKIP without GPU)
- **(b) Source-inspection only** (cross-platform always-run; doesn't catch worker-runtime issues)
- **(c) Behavioral-heavy** (catches runtime; SKIPs frequently in dev)
- **Architect lean: (a) hybrid.** A1-A8 source-inspection + A9-A10 CUDA-gated behavioral. Same precedent as P0.R3/R4/R5 test surfaces.

---

## §9 — `### Zero-precision-items-at-auditor-review` doctrine forecast

Architect's pre-emption budget: 8 Q-leans (Q1-Q8) + Q5 anchor-count lock + 1 quantifier-precision-refined-by-grep multi-axis instance candidate (Q1 + §1.1 TASK-COMPLETENESS + SCALE-OF-WORK).

Q1 carries HIGHEST risk: auditor may push back on decomposition + require full 4-task scope in single cycle (would invalidate the foundation-only Phase 0). Honest forecast: 0-2 PIs possible at Q1/Q4/Q7 surfaces.

**Architect's probabilistic prediction (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine):** "Phase 0 + Plan v1 SUBMITTED for auditor cross-check; expecting 0-2 PI surface on Q1 (decomposition) specifically. If Q1 ratified (a) decompose: cycle proceeds with foundation + AdaFace scope; subsequent P0.R6.X-Z file as follow-up specs. If Q1 ratified (b) single-cycle full-scope: cycle re-scoped to all 4 tasks; significantly larger spec; would escalate to multi-week effort + violate break-large-implementations discipline. Architect's strong recommendation: (a) decompose."

---

## §10 — Files this audit touches (Phase 0 zero-production-code rule)

**Pure documentation; ZERO production code changes at Phase 0:**

- `c:\Users\jagan\dog-ai\dog-ai\tests\p0_r6_heavy_worker_foundation_audit.md` — THIS FILE (NEW)

**Phase 1+ shipping (PER PLAN v1 LOCK; NOT in Phase 0 scope):**

- `core/heavy_worker.py` — D1+D2 NEW module
- `core/pipeline_state_store.py` — D4 NEW field (`heavy_worker_status`)
- `core/health.py` — D4 conditional emit + alert
- `pipeline.py` — D3 migration (2 sites) + D5 startup/shutdown wiring
- `tests/test_p0_r6_heavy_worker_foundation.py` — NEW file with 10 anchors

**SUBSEQUENT cycles (NOT in P0.R6 scope; file as P0.R6.X-Z follow-up specs):**

- `core/audio.py::transcribe` — P0.R6.X Whisper migration
- `core/voice.py::identify` + `embed` — P0.R6.Y ECAPA migration
- `core/voice.py::_diarize_pyannote` + `get_diarize_executor` replacement — P0.R6.Z

---

## §11 — Verdict request

Forwarding to auditor for Phase 0 verdict. Expected verdict items:
1. **Q1 adjudication (HIGHEST risk)** — decomposition (architect lean (a)) vs single multi-day (b)
2. Q2 adjudication (first migration target)
3. Q3 adjudication (IPC mechanism)
4. Q4 adjudication (worker lifecycle)
5. Q5 anchor count lock (architect lean: 10 inclusive ±15%)
6. Q6 adjudication (cross-platform start method)
7. Q7 adjudication (GPU memory budget — document + defer)
8. Q8 adjudication (test surface scope)
9. PI surfacing + non-blocking observations

**Banking events expected at Phase 0 verdict (closure-conditional):**
- `### Zero-precision-items-at-auditor-review` 18 → 19 IF auditor returns 0 BLOCKING PIs
- `Pre-audit-quantifier-precision-refined-by-grep` 4 → 5 IF auditor ratifies §1.1 multi-axis refinements as a NEW instance — would reach 5-instance threshold for potential elevation
- Twin-filename pitfall 20th preventive event ALREADY honored at audit drafting
- `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` continues empirical track record (Phase 0 surface = 8th application post-elevation)

**Architect's honest scope flag**: this is a HEAVY-band foundational architectural cycle. Even with Q1 (a) decomposition, P0.R6 foundation + AdaFace is meaningful work. Subsequent P0.R6.X-Z follow-ups complete the pre-audit's 4-task scope across ~2-3 more cycles (each ~2-3h). Total P0.R6-track effort ≈ 8-12 hours across 4 cycles vs ~12-15h as single cycle — decomposition adds some coordination overhead but reduces per-cycle blast radius.

---

End of P0.R6 Phase 0 audit.
