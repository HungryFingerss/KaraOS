# P0.R9 — Cumulative VRAM budget guard + graceful pool-degradation (Phase 0 audit)

**Date**: 2026-05-25
**Author**: architect (Claude)
**Cycle shape**: SMALL-MEDIUM band; orthogonal failure mode from P0.R8 (detection AFTER crash) and P0.R11 (forensics AFTER crash) — P0.R9 predicts/prevents BEFORE crash
**Estimated effort**: ~3h MEDIUM-band cycle
**Companion specs**: P0.R6.* arc (the 4 pools whose VRAM this cycle budgets), P0.R8 (auto-respawn on crash; complementary), P0.R11 (forensics on crash; complementary), Wave 5 Item 20 disk-monitor (threshold pattern precedent), P0.R1 (None-return fallback contract)

---

## §0 Pre-audit framing (LOCKED 2026-05-25 by architect BEFORE grep verification)

> "P0.R9 adds cumulative VRAM budget guard + graceful pool-degradation. At startup, predicts cumulative VRAM across 4 heavy-worker pools via static `ESTIMATED_VRAM_MB` config values. Compares to available CUDA memory × `VRAM_CEILING_PCT` (default 80%). If cumulative would exceed ceiling, refuses lower-priority pool spawns per `VRAM_POOL_PRIORITY` config ordering. Refused pools return None from `get_or_create_pool`; callers fall through to P0.R1 D1 None-return fallback contracts uniformly. HealthSnapshot exposes per-pool estimate + cumulative + degraded list. WatchdogAgent alert on VRAM-budget-refusal. ~3h MEDIUM cycle."

Phase 0 grep verifies framing. Findings below.

Cross-path discipline (per `feedback_architect_reads_catches_phase_7_memory_file_omission.md` 4th sub-variant CROSS-PATH-SYNC-OMISSION + auditor's recommendation #3 at P0.R11 closure-verdict): if P0.R9 introduces NEW memory files at closure, architect MUST verify updates at BOTH the architect-memory path (`C--Users-jagan-dog-ai-dog-ai/memory/`) AND the auditor-facing memory path (`C--Users-jagan-dog-ai/memory/`).

---

## §1 Grep findings (Pass-1 baseline) — COMPREHENSIVE upfront

### §1.1 Heavy-worker pool spawn surfaces (extension point)

| # | Surface | File:Line | Current behavior |
|---|---|---|---|
| 1 | `_HEAVY_WORKER_POOLS: dict` | `core/heavy_worker.py:33` | 4 task_name keys after startup: adaface_embed / whisper_transcribe / ecapa_embed / pyannote_diarize |
| 2 | `get_or_create_pool(task_name, max_workers=1)` | `core/heavy_worker.py:128-151` | Always creates ProcessPoolExecutor on first call; **no budget check** |
| 3 | `run_heavy(task_name, fn, ...)` | `core/heavy_worker.py:154+` | Calls `get_or_create_pool` + dispatches via `loop.run_in_executor(pool, ...)` |
| 4 | Subprocess singletons (`_SUBPROCESS_EMBEDDER` / `_WHISPER_MODEL` / `_ECAPA_EMBEDDER` / `_PYANNOTE_PIPELINE`) | `core/heavy_worker.py:111/261/363` etc. | Lazy-loaded per subprocess; total ~6.3GB cumulative VRAM when all loaded |

**Extension surface**: `get_or_create_pool` is the natural choke-point for budget enforcement. Before creating the ProcessPoolExecutor, check if cumulative VRAM (existing pools + this pool's estimate) would exceed ceiling. If so, return None per Q3 (a) lock.

### §1.2 Current pool VRAM cost estimates (from P0.R6.* audit docs)

| Pool | Model | Estimate (banked from P0.R6.X / R6.Y / R6.Z audit docs) |
|---|---|---|
| `adaface_embed` | AdaFace IR101 ONNX | ~100 MB (P0.R6 audit §3.5) |
| `whisper_transcribe` | faster-whisper large-v3-turbo | ~3000 MB (P0.R6.X audit §2 risk) |
| `ecapa_embed` | SpeechBrain ECAPA-TDNN | ~200 MB (P0.R6.Y audit §2 refinement) |
| `pyannote_diarize` | pyannote/speaker-diarization-3.1 | ~3000 MB (P0.R6.Z audit §2 risk) |
| **Cumulative** | | **~6300 MB committed at full warm-up** |

**Static estimate strategy LOAD-BEARING decision (Q1)**: pre-audit assumed static config estimates. Phase 0 grep confirms estimates are well-documented across prior cycles. Probe-and-record would add subprocess-side measurement + IPC complexity for marginal benefit (estimates already documented + operator-tunable).

### §1.3 Disk monitor threshold-crossing pattern (closest precedent for P0.R9)

| # | Surface | File:Line | Pattern |
|---|---|---|---|
| 1 | `_last_disk_alert_level: int = 0` | `core/disk_monitor.py:20` | Module state for idempotency |
| 2 | `check_disk_thresholds()` | `core/disk_monitor.py:100-148` | 3-level idempotent threshold pattern (warning/critical/blocker) |
| 3 | `reset_alert_level()` | `core/disk_monitor.py:152-154` | Test/recovery helper |
| 4 | `DISK_ALERT_WARNING_PCT` / `_CRITICAL_PCT` / `_BLOCKER_PCT` | `core/config.py` | 3 threshold constants |
| 5 | `_db.store_alert(...)` via WatchdogAgent | `core/brain_agent.py:6573` | Alert dispatch pattern |

P0.R9 reuses the **idempotency + threshold + WatchdogAgent dispatch** patterns from disk-monitor. Different threshold (VRAM ceiling) + different alert type (VRAM-budget-refusal vs disk-warning) + simpler semantic (no 3-level escalation; either pool spawns or refuses).

### §1.4 Existing CUDA-availability check sites

| # | Surface | File:Line | Notes |
|---|---|---|---|
| 1 | `torch.cuda.is_available()` | `core/heavy_worker.py:488 / 553` | Used inside worker subprocess for device decision |
| 2 | `torch.cuda.is_available()` | `core/vision.py:600` | Used in `FaceEmbedder.__init__` device selection |
| 3 | `torch.cuda.is_available()` | `core/classifier_graph.py:126` | Used for classifier-graph CUDA path |

**P0.R9 budget check requires CUDA available** to call `torch.cuda.mem_get_info()`. On non-CUDA environments (Windows dev without GPU / CI runners), Q5 (a) lock: **skip budget enforcement entirely** — non-CUDA systems don't have VRAM budget concerns; `get_or_create_pool` proceeds without refusal. This matches Q5 (a) architect lean.

### §1.5 P0.R1 D1 None-return fallback contracts (LOAD-BEARING for Q3 absorption)

P0.R9 refused-pool semantic must preserve existing fallback contracts uniformly. Each pool's caller-side fallback:

| Caller | Fallback on `BrokenProcessPool` (P0.R8) / pool None (P0.R9) |
|---|---|
| `core/vision.py::FaceEmbedder.embed()` (AdaFace) | None embedding → recognize-miss (P0.R1 D1) |
| `core/audio.py::transcribe()` (Whisper) | None text → empty STT |
| `core/voice.py::embed()` (ECAPA) | None embedding → identify-miss (P0.R1 D1) |
| `core/voice.py::_diarize_pyannote()` (Pyannote) | None segments → ECAPA-valley fallback (P0.R6.Z Q9 lock) |

**Critical observation**: existing fallbacks fire on **`BrokenProcessPool` exception caught at `run_heavy`** (P0.R8 D2) — they catch a thrown exception via the bare `raise` at heavy_worker.py:202. If `get_or_create_pool` returns None (P0.R9 refusal), `run_heavy` would crash with `AttributeError: 'NoneType' object has no attribute 'submit'` UNLESS `run_heavy` is also updated to handle None pool.

**D4 LOAD-BEARING**: `run_heavy` must detect None pool + return None directly (skip `loop.run_in_executor`) to preserve caller-side fallback semantics uniformly. Returning None propagates through `await hw.run_heavy(...)` to caller's None-handling path.

### §1.6 Cross-spec interactions (Pass-2 grep)

| Spec | Interaction | Status |
|---|---|---|
| P0.R6.* arc | 4 pools whose VRAM this cycle budgets | INSTRUMENTS — budget check at `get_or_create_pool`; no changes to subprocess code |
| P0.R8 | Crash detection + burst limit | COMPLEMENTARY — P0.R8 detects crashes; P0.R9 prevents some (VRAM-exhaustion class) |
| P0.R11 | Forensic capture | COMPLEMENTARY — both observability; different surfaces |
| P0.R1 D1 | None-return fallback contracts | LOAD-BEARING — D4 preserves contract via `run_heavy` None-pool handling |
| P0.R6.Z Q9 | BrokenProcessPool → ECAPA-valley fallback | EXTENDS — P0.R9 None-pool refusal fires same fallback path |
| Wave 5 Item 20 | Disk monitor threshold pattern | EXTENDS — P0.R9 reuses idempotency + WatchdogAgent dispatch shape |
| HealthSnapshot | Already extended for heavy_worker_status (P0.R6 D4) + heavy_worker_crash_counts (P0.R8 D5) + recent_crash_logs (P0.R11 D3) | EXTENDS — P0.R9 adds `vram_budget` field |
| WatchdogAgent | Existing burst-alert pattern | EXTENDS — new `report_vram_budget_refusal` method |
| Non-CUDA environments (Windows dev / CI) | `torch.cuda.is_available() == False` | LOAD-BEARING SKIP — Q5 (a) lock: budget enforcement off on non-CUDA |

---

## §2 Architectural justification refresh

Pre-audit framing was structurally CORRECT. Phase 0 grep ADDS:

1. **`run_heavy` None-pool handling LOAD-BEARING** (Q3 + D4 interaction): the obvious "return None from get_or_create_pool" semantic requires a non-obvious second change — `run_heavy` body must also detect None pool + skip `loop.run_in_executor`. Without it, refused pool causes `AttributeError`, NOT the clean None propagation P0.R1 D1 contracts depend on.

2. **CUDA-availability prerequisite**: `torch.cuda.mem_get_info()` requires CUDA available. Q5 (a) skip-on-non-CUDA preserves dev-laptop + CI behavior. Banking shape: P0.R9 budget enforcement is CUDA-only feature; production target (Jetson) always has CUDA; dev-laptop fallback is acceptable.

3. **Static estimates vs probe-and-record**: pre-audit chose static. Phase 0 grep confirms estimates are well-documented across P0.R6 audit docs. Static is simpler + sufficient for current scope. Probe-and-record deferred to follow-up if estimates drift across model versions.

Risk/benefit:

- **Risk**: static estimates drift over time. Banking shape: documented in `core/config.py` near constants; operator updates if model versions change.
- **Risk**: VRAM_CEILING_PCT default 80% may be too conservative or too aggressive. Operator-tunable.
- **Risk**: pool priority ordering may not match deployment priorities. Operator-tunable via `VRAM_POOL_PRIORITY` config.
- **Benefit**: predicts/prevents VRAM-exhaustion crashes BEFORE they fire — complement to P0.R8/R11 which observe AFTER.
- **Benefit**: graceful degradation on memory-constrained systems (dev laptops, Jetson under heavy load) — keeps higher-priority pools functional + degrades lower-priority pools cleanly.
- **Benefit**: existing P0.R1 D1 None-return contracts fire uniformly — no new fallback semantic to design.

---

## §3 D-decision proposal (6 D-decisions)

**D1 (`core/config.py` constants)**:

```python
# P0.R9 — heavy-worker pool VRAM budget guard. Static estimates per pool;
# cumulative cap at VRAM_CEILING_PCT of available CUDA memory; pool
# priority determines which pools refuse spawn on budget exhaustion.
HEAVY_WORKER_VRAM_ESTIMATES_MB = {
    "adaface_embed":     100,
    "ecapa_embed":       200,
    "whisper_transcribe": 3000,
    "pyannote_diarize":  3000,
}
VRAM_CEILING_PCT       = 80.0  # cap at 80% of available CUDA memory
VRAM_POOL_PRIORITY     = [
    "adaface_embed",      # highest — face recognition is core
    "ecapa_embed",        # voice ID for greeting
    "whisper_transcribe", # STT (could degrade to other STT)
    "pyannote_diarize",   # lowest — has ECAPA-valley fallback
]
```

**D2 (`check_vram_budget` helper + `_REFUSED_POOLS` set in `core/heavy_worker.py`)**:

```python
# Module-level: track refused pools so subsequent calls return None
# consistently without re-computing the budget check.
_REFUSED_POOLS: "set[str]" = set()
_VRAM_CHECK_LOCK = threading.Lock()


def check_vram_budget(task_name: str) -> bool:
    """Return True if `task_name` can spawn within VRAM budget; False if refused.

    Q5 (a) lock: skip enforcement on non-CUDA (torch.cuda.is_available() == False);
    returns True so non-CUDA dev/CI environments proceed as today.

    Q4 (a) lock: refused pools cached in _REFUSED_POOLS module set; subsequent
    calls return False without re-computing.

    Computes cumulative VRAM = sum(ESTIMATES_MB[p] for p in _HEAVY_WORKER_POOLS) +
    ESTIMATES_MB[task_name]; compares to (available_cuda_mb * VRAM_CEILING_PCT / 100).
    """
    with _VRAM_CHECK_LOCK:
        if task_name in _REFUSED_POOLS:
            return False
        try:
            import torch
            if not torch.cuda.is_available():
                return True  # Q5 (a) — skip on non-CUDA
            free_mb, total_mb = (b // (1024 * 1024) for b in torch.cuda.mem_get_info())
        except Exception:  # OPTIONAL: torch import / CUDA probe failure → skip
            return True
        from core.config import (
            HEAVY_WORKER_VRAM_ESTIMATES_MB,
            VRAM_CEILING_PCT,
        )
        ceiling_mb = total_mb * (VRAM_CEILING_PCT / 100.0)
        cumulative_committed_mb = sum(
            HEAVY_WORKER_VRAM_ESTIMATES_MB.get(p, 0)
            for p in _HEAVY_WORKER_POOLS
        )
        this_pool_mb = HEAVY_WORKER_VRAM_ESTIMATES_MB.get(task_name, 0)
        if cumulative_committed_mb + this_pool_mb > ceiling_mb:
            _REFUSED_POOLS.add(task_name)
            return False
        return True


def peek_refused_pools() -> "set[str]":
    """Read-only accessor for refused pools (test + health observability)."""
    with _VRAM_CHECK_LOCK:
        return set(_REFUSED_POOLS)
```

**D3 (`get_or_create_pool` extension)**:

```python
def get_or_create_pool(
    task_name: str, max_workers: int = 1
) -> "concurrent.futures.ProcessPoolExecutor | None":
    """Get-or-create singleton ProcessPoolExecutor per task_name.

    P0.R9 D3: budget check BEFORE pool creation. If check_vram_budget returns
    False (cumulative would exceed VRAM_CEILING_PCT), return None and log
    refusal + dispatch WatchdogAgent.report_vram_budget_refusal alert. The
    None return propagates through run_heavy to caller's existing P0.R1 D1
    None-return fallback contract.
    """
    if task_name in _HEAVY_WORKER_POOLS:
        return _HEAVY_WORKER_POOLS[task_name]
    # P0.R9 D3 — VRAM budget check
    if not check_vram_budget(task_name):
        print(
            f"[HeavyWorker] WARN VRAM budget refusal — pool '{task_name}' "
            f"not spawned (cumulative + estimate would exceed "
            f"VRAM_CEILING_PCT). Fallback path will fire via caller's "
            f"None-return handling."
        )
        return None
    ctx = mp.get_context("spawn")
    pool = concurrent.futures.ProcessPoolExecutor(
        max_workers=max_workers,
        mp_context=ctx,
        initializer=_adaface_worker_init if task_name == "adaface_embed" else None,
    )
    _HEAVY_WORKER_POOLS[task_name] = pool
    return pool
```

**D4 (`run_heavy` None-pool handling)**:

```python
async def run_heavy(
    task_name: str, fn: "Callable", *args: "Any", **kwargs: "Any"
) -> "Any":
    """... P0.R9 D4: if get_or_create_pool returns None (VRAM budget refusal),
    return None immediately (preserves caller's P0.R1 D1 None-return fallback
    contract; skips the run_in_executor dispatch).
    """
    pool = get_or_create_pool(task_name)
    if pool is None:
        return None  # P0.R9 D4 — preserve P0.R1 D1 fallback contract
    loop = asyncio.get_running_loop()
    bound = functools.partial(fn, *args, **kwargs)
    try:
        return await loop.run_in_executor(pool, bound)
    except concurrent.futures.process.BrokenProcessPool as e:
        # P0.R8 + P0.R11 (existing) — unchanged
        ...
```

**D5 (`WatchdogAgent.report_vram_budget_refusal` method)**:

```python
def report_vram_budget_refusal(
    self,
    task_name: str,
    cumulative_mb: int,
    ceiling_mb: int,
    estimate_mb: int,
) -> None:
    """Store a VRAM budget refusal alert. Severity: warning (graceful
    degradation; caller's fallback fires). Called from
    pipeline._heavy_worker_watchdog_loop OR core.heavy_worker.check_vram_budget
    on first refusal per task_name.
    """
    self._db.store_alert(
        f"vram_budget_refusal_{task_name}",
        "warning",
        f"Pool '{task_name}' refused spawn (estimate {estimate_mb}MB + "
        f"cumulative {cumulative_mb}MB > ceiling {ceiling_mb}MB). "
        f"Fallback path active. Reduce estimates / raise ceiling / change "
        f"priority order to recover.",
        {
            "task_name": task_name,
            "cumulative_mb": cumulative_mb,
            "ceiling_mb": ceiling_mb,
            "estimate_mb": estimate_mb,
        },
    )
    print(
        f"[WatchdogAgent] vram_budget_refusal_{task_name} alert stored "
        f"(estimate={estimate_mb}MB, cumulative={cumulative_mb}MB, "
        f"ceiling={ceiling_mb}MB)"
    )
```

**D6 (`HealthSnapshot.vram_budget` field + format extensions)**:

```python
# HealthSnapshot dataclass field
vram_budget: "dict" = field(default_factory=dict)

# gather_health_snapshot addition
import core.heavy_worker as hw
vram_budget: dict = {
    "refused_pools": sorted(hw.peek_refused_pools()),
    "active_pools": sorted(hw._HEAVY_WORKER_POOLS.keys()),
}

# format_health_line conditional emit
if snapshot.vram_budget.get("refused_pools"):
    parts.append(f"vram_refused={len(snapshot.vram_budget['refused_pools'])}")

# format_health_alerts on degraded pools
if snapshot.vram_budget.get("refused_pools"):
    alerts.append(
        f"VRAM budget refusal — pools refused: "
        f"{', '.join(snapshot.vram_budget['refused_pools'])}. "
        f"Caller fallback active. Tune VRAM_POOL_PRIORITY / VRAM_CEILING_PCT / "
        f"HEAVY_WORKER_VRAM_ESTIMATES_MB at core/config.py + restart to recover."
    )
```

---

## §4 Anchor count proposal (Q5)

**Mid 9 INCLUSIVE ±15% band → [7.65, 10.35] → ON-TARGET = 8, 9, or 10 anchors**:

- **A1**: 3 config constants present (`HEAVY_WORKER_VRAM_ESTIMATES_MB` + `VRAM_CEILING_PCT` + `VRAM_POOL_PRIORITY`)
- **A2**: `check_vram_budget(task_name)` helper + `_REFUSED_POOLS` set + `peek_refused_pools()` accessor in `core/heavy_worker.py`
- **A3**: `get_or_create_pool` returns None when budget would be exceeded (behavioral test with monkeypatched `torch.cuda.mem_get_info` returning small total)
- **A4**: `get_or_create_pool` STILL spawns high-priority pool when budget tight; refuses low-priority pool (behavioral with crafted estimates)
- **A5**: `run_heavy` returns None when `get_or_create_pool` returns None (D4 graceful degradation; behavioral test)
- **A6**: `_REFUSED_POOLS` caches refusal (second call returns False without re-computing; behavioral test with `_REFUSED_POOLS` inspection)
- **A7**: `WatchdogAgent.report_vram_budget_refusal` method exists + stores alert
- **A8**: `HealthSnapshot.vram_budget` field + `format_health_line` `vram_refused=N` conditional emit + `format_health_alerts` actionable alert
- **A9**: Non-CUDA environment skips budget enforcement (`torch.cuda.is_available()` returns False → `check_vram_budget` returns True; behavioral test with monkeypatched `torch.cuda.is_available`)

**Closure-projection band table**:

| closure-actual | overage vs mid 9 | band | doctrine outcome |
|---|---|---|---|
| 7 | −22.2% | SLIGHT-DRIFT-DOWN | `### Phase-0-granular-decomposition` HOLDS at 24 |
| 8 | −11.1% | ON-TARGET | 24 → 25 supporting |
| 9 | 0% | ON-TARGET exact mid | 24 → 25 supporting + **4th consecutive 0%-streak rebuild instance** (P0.R6.Z + P0.R8 + P0.R11 + P0.R9; nearing 5+ sub-observation threshold) |
| 10 | +11.1% | ON-TARGET | 24 → 25 supporting |
| 11 | +22.2% | SLIGHT-DRIFT-UP | HOLDS at 24 |
| ≥12 OR ≤6 | beyond ±30% | FALSIFICATION TRIGGER | demotes back to architect-memory |

---

## §5 OUT-OF-SCOPE classification

1. **Probe-and-record VRAM measurement** — Q1 (a) static-estimate lock. If estimates drift, follow-up cycle adds subprocess-side measurement + IPC. Banked as Known Limitation.
2. **Dynamic budget re-evaluation** — `check_vram_budget` runs at first `get_or_create_pool` call per task_name + caches; no runtime re-check. If main-process CUDA usage grows post-startup (rare), no automatic adjustment. Operator restart triggers re-evaluation.
3. **Force-override semantic** — Q9 (a) lock: no operator-force flag to spawn refused pool. Tune config + restart to recover.
4. **Per-process VRAM accounting** — P0.R9 uses cumulative total from `torch.cuda.mem_get_info()` (system-wide CUDA available). Doesn't distinguish main-process VRAM vs subprocess VRAM. Acceptable for current scope; cross-process VRAM tracking is a future concern if multi-tenant CUDA usage becomes relevant.
5. **Estimate adaptive calibration** — if subprocess actually uses less/more VRAM than estimate, no auto-tune. Operator updates estimates manually per `core/config.py` constants. Adaptive calibration is follow-up cycle.
6. **VRAM monitor loop** — no periodic VRAM check during runtime. Disk monitor has periodic check; VRAM ceiling is enforced at pool-spawn-time only. Sufficient for current scope.

---

## §6 Locked-down discipline counters

Per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine: auditor DILIGENT Pass-2 grep at Plan v1 §1 will independently verify §1.1-§1.6 surface tables.

Per `feedback_pass_2_grep_deferral_pattern.md` (locked at P0.R6.Y closure-audit): NO "developer Phase N surfaces enumeration" framings — all surfaces enumerated upfront with explicit per-surface disposition.

Per `feedback_pass_2_grep_caught_real_gap_subshape.md` CODE-TEMPLATE-MISIDENTIFICATION sub-shape (validated in BOTH modes at P0.R11): architect proactive grep-verify of §2 D-decision code template references upfront. References:
- `_HEAVY_WORKER_POOLS` at `core/heavy_worker.py:33` ✓
- `torch.cuda.is_available()` + `torch.cuda.mem_get_info()` — stdlib torch API ✓
- P0.R6 D4 `_heavy_worker_status` dict precedent ✓
- WatchdogAgent burst-alert precedents (P0.R8 D4) ✓
- HealthSnapshot dataclass extension pattern (P0.R8 D5 + P0.R11 D3 precedents) ✓

CODE-TEMPLATE-MISIDENTIFICATION risk: LOW.

**`### Pre-audit-quantifier-precision-refined-by-grep` instance enumeration** (post-P0.R11 closure baseline; CLAUDE.md canonical at lines 656-745 with 8-axis sub-shape taxonomy):

Phase 0 grep CONFIRMS pre-audit framing — no quantifier refinement event fires. Pre-audit said "4 pools" + "~6.3GB cumulative" + "static estimates" + "P0.R1 D1 fallback contract"; grep verified all 4 claims match production. Per operational rule 3, no instance bank fires. Doctrine STAYS at 8 instances. **3rd consecutive clean-confirmation since elevation** (P0.R8 + P0.R11 + P0.R9) — sustained negative-evidence validation of operational rule 3.

---

## §7 Q-questions for adjudication

**Q1 (VRAM measurement strategy)**:
- Option (a): Static estimates in config (4 ESTIMATED_VRAM_MB values per pool)
- Option (b): Runtime probe — subprocess reports VRAM after model load + cached
- Option (c): Hybrid — static defaults + per-pool runtime adjustment

**Architect lean: (a)** — simpler; estimates documented + tunable; probe-and-record adds subprocess-side measurement + IPC. Banking shape: P0.R9 ships static; if estimates drift, follow-up cycle adds probe.

**Q2 (Pool priority ordering)**:
- Option (a): Config-driven (`VRAM_POOL_PRIORITY` list)
- Option (b): Hardcoded in heavy_worker.py

**Architect lean: (a)** — operator-tunable.

**Q3 (Refusal semantic — LOAD-BEARING)**:
- Option (a): `get_or_create_pool` returns None; `run_heavy` returns None; callers see P0.R1 D1 fallback (uniform with existing crash semantic)
- Option (b): `get_or_create_pool` returns degraded-pool sentinel that raises on `submit()` (callers catch via existing except branches)
- Option (c): `get_or_create_pool` raises `VRAMBudgetExceeded`; callers catch new exception

**Architect lean: (a)** — uniform with existing P0.R1 D1 None-return contract. Requires D4 `run_heavy` extension (handle None pool) — flagged as LOAD-BEARING in §1.5 + §2 D4.

**Q4 (Refused-pool caching)**:
- Option (a): Refuse once + cache in `_REFUSED_POOLS` set
- Option (b): Re-check on every `get_or_create_pool` call

**Architect lean: (a)** — caches refusal decision so subsequent calls return None deterministically; restart re-evaluates with updated estimates.

**Q5 (Non-CUDA fallback)**:
- Option (a): Skip budget enforcement when `torch.cuda.is_available() == False`
- Option (b): Use heuristic (e.g., RAM-based budget)

**Architect lean: (a)** — non-CUDA environments don't have VRAM concerns; CUDA-only feature.

**Q6 (Budget check timing)**:
- Option (a): First `get_or_create_pool` call per task_name (lazy at pool-spawn)
- Option (b): Startup batch check (all 4 pools checked upfront before any spawn)

**Architect lean: (a)** — lazy check; matches existing pool warm-up ordering at startup; first call to each pool's `get_or_create_pool` triggers check.

**Q7 (Available VRAM source)**:
- Option (a): `torch.cuda.mem_get_info()` — returns (free_bytes, total_bytes)
- Option (b): `nvidia-smi` subprocess call

**Architect lean: (a)** — no subprocess overhead; tied to torch already-loaded; cross-platform consistent.

**Q8 (Alert dispatch granularity)**:
- Option (a): Per-pool refusal (fire alert per refused task_name)
- Option (b): Cumulative-only (fire alert when ANY refusal happens)

**Architect lean: (a)** — operator wants to know WHICH pool degraded; per-pool alert via `report_vram_budget_refusal(task_name, ...)`.

**Q9 (Force-override semantic)**:
- Option (a): No override; operator tunes config + restarts
- Option (b): Config flag `VRAM_BUDGET_DISABLED=False` for emergency override
- Option (c): Per-pool override list

**Architect lean: (a)** — defer override semantics to follow-up if needed; restart-based recovery is the simplest contract.

---

## §8 Doctrine-firing projections at closure

If P0.R9 closes cleanly with closure-actual = 9 anchors at exact mid:

- `### Phase-0-granular-decomposition-enables-accurate-estimates` 24 → 25 supporting
- `Doctrine-prediction-precision-improving-over-arc` **4th consecutive 0%-streak rebuild instance** (P0.R6.Z + P0.R8 + P0.R11 + P0.R9; 5+ watch criteria approaching → sub-observation extension at 5th instance)
- `### Pre-audit-quantifier-precision-refined-by-grep` STAYS at 8 instances (3rd consecutive clean-confirmation per operational rule 3 — sustained empirical validation of negative-evidence semantic)
- `### Phase-0-catches-wrong-premise` STAYS at 13 (premise correct)
- `### Zero-precision-items-at-auditor-review` 27 → 29 (Phase 0 + Plan v1 if cycle clears cleanly)
- OPTIONAL-Plan-v2 sub-rule track record 13 → 14 proof cases (if 3-artifact cycle ships)
- `### Architect-reads-production-code-before-sign-off` 23 → 24 at closure-audit (7th-cycle self-sustaining adoption; the P0.R11 cross-path catch already pushed to 23 at next-cycle; THIS cycle is that next)
- Strict-industry-standard mode 89 → 92 applications + 26 → 27 closures
- Spec-first review cycle 98 → 101-for-101 at closure
- `### Grep-baseline-before-drafting` 56 → 59 instances
- Cross-cycle-handoff transparency 59 → 62 successful
- Spec-time grep-verification 66 → 69 instances
- `### Twin-filename-pitfall-prevention` 25 → 26 preventive events
- Auditor-Q5-estimates-trail-grep 30 → 31 banked closures
- Deferred-canary strategy 28 → 29 applications
- CODE-TEMPLATE-MISIDENTIFICATION sub-shape: 2nd preventive-application instance (P0.R8 caught + P0.R11 preventive + P0.R9 preventive = 1 caught + 2 preventive)
- MEMORY-FILE INDEX GAP family: track-record stays at 4 if no new instance fires at this cycle; cross-path discipline applied preventively per locked operational rule

---

## §9 Architect-handoff items for auditor verdict

1. **Pass-2 grep verification** (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine): independent re-grep §1.1 4-row + §1.2 4-row VRAM estimate table + §1.3 5-row disk-monitor precedent + §1.4 3-row CUDA-check sites + §1.5 4-row fallback contracts + §1.6 9-row cross-spec table. **CODE-TEMPLATE-MISIDENTIFICATION risk-check**: §2 D1-D6 code templates reference `_HEAVY_WORKER_POOLS` (heavy_worker.py:33 ✓) + `torch.cuda.is_available()` + `torch.cuda.mem_get_info()` (torch stdlib ✓) + `HEAVY_WORKER_VRAM_ESTIMATES_MB` + `VRAM_CEILING_PCT` + `VRAM_POOL_PRIORITY` (NEW config — verified absent before P0.R9; would be added at Phase 1) + WatchdogAgent burst-alert pattern (brain_agent.py precedents ✓) + HealthSnapshot extension pattern ✓. All references grep-verifiable.

2. **Q1-Q9 adjudication**: confirm architect leans. Q3 (refusal semantic) + Q5 (non-CUDA fallback) are LOAD-BEARING; Q1-Q2 + Q4 + Q6-Q9 are implementation refinements.

3. **Anchor count adjudication**: confirm mid 9 INCLUSIVE ±15% band [7.65, 10.35].

4. **3rd clean-confirmation for `### Pre-audit-quantifier-precision-refined-by-grep`**: per §6, Phase 0 grep CONFIRMS pre-audit framing — doctrine STAYS at 8 instances. 3rd consecutive clean-confirmation since elevation. Sustained empirical validation.

5. **Cross-path discipline preventive application**: per `feedback_architect_reads_catches_phase_7_memory_file_omission.md` 4th sub-variant CROSS-PATH-SYNC-OMISSION + auditor's recommendation at P0.R11 closure-verdict: if P0.R9 closure introduces NEW memory files OR updates existing memory files, architect MUST verify updates at BOTH paths. P0.R9 does not currently project NEW memory files (clean cycle if no observations surface); if any are banked at closure, cross-path verification is mandatory.

---

**End of Phase 0 audit.** Ready for auditor verdict.
