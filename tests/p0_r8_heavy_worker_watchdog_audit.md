# P0.R8 — Heavy-worker pool watchdog + restart-burst limit + crash observability (Phase 0 audit)

**Date**: 2026-05-25
**Author**: architect (Claude)
**Cycle shape**: SMALL-MEDIUM band, mirror of P0.R3 vision-loop watchdog pattern, applied to the 4 heavy-worker pools (AdaFace + Whisper + ECAPA + Pyannote) created across the P0.R6.* arc that closed 2026-05-24
**Estimated effort**: ~3-4h MEDIUM-band cycle
**Companion specs**: P0.R3 (vision-loop watchdog precedent for pattern), P0.R6 D4 (existing `_heavy_worker_status` dict foundation), `### Phase-0-granular-decomposition-enables-accurate-estimates` (Q5 framework)

---

## §0 Pre-audit framing (LOCKED 2026-05-25 by architect BEFORE grep verification)

> "P0.R8 adds heavy-worker pool watchdog + restart-burst limit + crash observability. Mirror of P0.R3 vision-loop watchdog pattern, applied to the 4 heavy-worker pools. Detects subprocess crashes via `BrokenProcessPool` exception. Per-pool restart counter + burst-limit (e.g. 3 crashes in 5 min → degraded). Watchdog poll loop (~5s). Health snapshot reports per-pool restart count + last-crash timestamp + degraded flag. WatchdogAgent alert on burst-limit breach. Crash diagnostic capture DEFERRED to P0.R11 scope. ~3-4h MEDIUM cycle."

Phase 0 grep verifies framing against production. Findings below.

---

## §1 Grep findings (Pass-1 baseline)

### §1.1 Heavy-worker pool current state (post-P0.R6.* arc)

| # | Surface | File:Line | Current behavior |
|---|---|---|---|
| 1 | `_HEAVY_WORKER_POOLS: dict[str, ProcessPoolExecutor]` | `core/heavy_worker.py:33` | Singleton pool registry keyed by task_name. 4 task classes registered post-P0.R6.*: `adaface_embed` + `whisper_transcribe` + `ecapa_embed` + `pyannote_diarize` |
| 2 | `get_or_create_pool(task_name, max_workers=1)` | `core/heavy_worker.py:66` | Returns existing OR creates new ProcessPoolExecutor with `mp.get_context("spawn")` |
| 3 | `run_heavy(task_name, fn, *args, **kwargs)` | `core/heavy_worker.py:92-109` | Async wrapper around `loop.run_in_executor(pool, partial(fn, ...))`. **NO try/except wrapping the dispatch** — `BrokenProcessPool` exceptions propagate up to caller-site |
| 4 | `shutdown_all_pools(wait=True)` | `core/heavy_worker.py:112-122` | Clean shutdown of all pools at pipeline exit |
| 5 | `_heavy_worker_status: dict[str, str]` at PipelineStateStore | `core/pipeline_state_store.py:90` | Status values currently: "healthy" (set at startup per P0.R6 D4); no other values used yet |
| 6 | `peek_heavy_worker_status()` accessor | `core/pipeline_state_store.py:150` | Returns COPY of dict |
| 7 | `set_heavy_worker_status(task_name, status)` async setter | `core/pipeline_state_store.py:156` | Scalar setter |
| 8 | `HealthSnapshot.heavy_worker_status: dict[str, str]` field | `core/health.py:70` | Surfaces dict; `format_health_line` conditional `heavy_workers=degraded` emit when any pool != healthy |

**Key finding**: `run_heavy` body has NO crash detection. `BrokenProcessPool` exceptions propagate to caller-site try/except (each P0.R6.* spec implemented its own fallback). For P0.R8 centralized crash observability, detection must land in `run_heavy` wrapper + counter recording.

### §1.2 Per-caller crash fallback semantics (post-P0.R6.* arc — preserved by P0.R8)

| Caller | Fallback on `BrokenProcessPool` |
|---|---|
| `core/vision.py::FaceEmbedder.embed()` (AdaFace) | None return → P0.R1 D1 fallback to recognize-miss |
| `core/audio.py::transcribe()` (Whisper) | None text → empty STT → main process filter chain |
| `core/voice.py::embed()` (ECAPA) | None embedding → P0.R1 D1 fallback to identify-miss |
| `core/voice.py::_diarize_pyannote()` (Pyannote) | None segments → ECAPA-valley fallback per Q9 (a) lock at P0.R6.Z |

**LOAD-BEARING**: P0.R8 detection MUST preserve these existing fallback semantics. The crash-detection wrapper records the crash + re-raises the exception so each caller's fallback path fires unchanged.

### §1.3 P0.R3 vision-loop watchdog pattern (precedent for P0.R8)

| Surface | File:Line | Pattern |
|---|---|---|
| `VISION_WATCHDOG_INTERVAL_SECS=5.0` | `core/config.py:1399` | Watchdog poll cadence |
| `VISION_WATCHDOG_STALE_THRESHOLD_SECS=30.0` | `core/config.py:1400` | Heartbeat staleness threshold |
| `VISION_WATCHDOG_RESTART_TIMEOUT_SECS=30.0` | `core/config.py:1401` | Restart-success deadline |
| `_vision_watchdog_loop()` async function | `pipeline.py:2402` | Polls every interval; checks staleness; invokes restart helper |
| `_restart_vision_task()` async helper | `pipeline.py:2429` | Explicit restart of vision task with timeout |
| Spawn ordering | `pipeline.py:6562-6565` | Watchdog spawned AFTER vision task (P0.R3 D5 ordering invariant) |
| Shutdown ordering | `pipeline.py` finally block | Watchdog cancelled BEFORE vision task |

P0.R8 mirrors this pattern for the 4 heavy-worker pools (centralized watchdog loop polling per-pool state instead of per-pool heartbeat).

### §1.4 WatchdogAgent alert dispatch precedents

| Method | Severity | Pattern |
|---|---|---|
| `report_dispute_rename_burst` | `warning`/`critical` | Counter-based threshold; severity escalation by victim type |
| `report_anti_spoof_burst` | `warning` | Fires at exact equality (3 rejections) to prevent spam |
| `report_disk_threshold` | `warning`/`critical` | Level-based (80/90/95%); idempotency managed by caller |

P0.R8 follows the burst pattern: `WatchdogAgent.report_heavy_worker_burst(task_name, crash_count, window_secs)` fires at burst-threshold breach. Severity `warning` (heavy-worker degraded is recoverable; operator-actionable but not session-blocking).

### §1.5 Cross-spec interactions (Pass-2 grep)

| Spec | Interaction | Status |
|---|---|---|
| P0.R1 | None-return fallback contracts | LOAD-BEARING (P0.R8 preserves; crash wrapper re-raises so caller's None-return path fires) |
| P0.R3 | Vision-loop watchdog | EXTENDS pattern; no conflict |
| P0.R4 | Process supervisor (systemd/supervisord) | COMPLEMENTARY — supervisor restarts pipeline; P0.R8 watchdog handles intra-process pool crashes |
| P0.R6 D4 | `_heavy_worker_status` dict + health.py integration | EXTENDS — adds "degraded" status value + restart_count field to HealthSnapshot |
| P0.R6 D5 | Pool warm-up ordering | NO conflict (watchdog spawns AFTER pool warm-ups + vision task) |
| WatchdogAgent | Existing burst-alert pattern | EXTENDS — new `report_heavy_worker_burst` method |
| Session 42 / Wave 5 Items 19+20 | Health log + disk monitor | COMPLEMENTARY (operator dashboard reads same `_heavy_worker_status` dict) |

---

## §2 Architectural justification refresh

Pre-audit framing was structurally CORRECT. Phase 0 grep ADDS:

1. **Crash-detection location**: `run_heavy` wrapper is the natural choke-point. Centralized try/except records the crash event + re-raises so caller-side fallback semantics stay intact. Alternative (separate observability hook called by each caller) would require touching 4 callers — more surface, more drift risk.

2. **Restart counter mechanism**: `ProcessPoolExecutor` auto-respawns subprocesses on next `submit()` after `BrokenProcessPool`. P0.R8 doesn't need explicit restart logic — the auto-respawn IS the restart. P0.R8 detects + tracks + alerts; the respawn happens implicitly. **Materially simpler than P0.R3** which needed explicit `_restart_vision_task()` helper for vision-task lifecycle management.

3. **Crash diagnostic capture deferred to P0.R11** per the resilience-track roadmap I proposed earlier. P0.R8 records `(task_name, timestamp, exception_type)` tuples in module-level history; P0.R11 will extend to capture stack traces + write to `faces/crash_logs/`.

4. **Burst-limit semantic**: `HEAVY_WORKER_RESTART_BURST_THRESHOLD=3` + `HEAVY_WORKER_RESTART_BURST_WINDOW_SECS=300` (5 min). On breach: pool status → "degraded"; watchdog alert fires once; auto-respawn STILL works (operator-actionable, not auto-disabled). Mirrors P0.R4 systemd `StartLimitBurst=5` semantic but with degraded-flag rather than pipeline-shutdown.

---

## §3 D-decision proposal (6 D-decisions)

**D1 (`core/heavy_worker.py` crash history + burst detection)**:

```python
# Module-level crash history (main process state; subprocesses don't see it)
_HEAVY_WORKER_CRASH_HISTORY: dict[str, list[float]] = {}
# Lock to protect concurrent reads/writes across asyncio + thread executors
_HEAVY_WORKER_CRASH_LOCK = threading.Lock()


def _record_pool_crash(task_name: str, now: float | None = None) -> None:
    """Record a pool-crash event for burst detection. Called from
    run_heavy()'s BrokenProcessPool catch block.

    Thread-safe via _HEAVY_WORKER_CRASH_LOCK — concurrent run_heavy() calls
    from multiple coroutines can race on the same task_name's history list.

    Crash events stay in history indefinitely; burst detection at watchdog
    poll-time filters by HEAVY_WORKER_RESTART_BURST_WINDOW_SECS. Memory
    bounded by event-rate × window-size; degenerate case (constant-crashing
    pool) is bounded by watchdog alert + operator intervention.
    """
    if now is None:
        now = time.time()
    with _HEAVY_WORKER_CRASH_LOCK:
        _HEAVY_WORKER_CRASH_HISTORY.setdefault(task_name, []).append(now)


def count_recent_crashes(task_name: str, window_secs: float, now: float | None = None) -> int:
    """Return number of crashes for task_name within the rolling
    `window_secs` window ending at `now`.

    Public accessor for watchdog loop. Implicitly prunes events older
    than window_secs (writes back filtered list) to bound memory.
    """
    if now is None:
        now = time.time()
    cutoff = now - window_secs
    with _HEAVY_WORKER_CRASH_LOCK:
        events = _HEAVY_WORKER_CRASH_HISTORY.get(task_name, [])
        # Prune events older than cutoff
        events = [t for t in events if t >= cutoff]
        _HEAVY_WORKER_CRASH_HISTORY[task_name] = events
        return len(events)


def peek_crash_history(task_name: str) -> list[float]:
    """Return COPY of crash history for task_name. Read-only accessor."""
    with _HEAVY_WORKER_CRASH_LOCK:
        return list(_HEAVY_WORKER_CRASH_HISTORY.get(task_name, []))
```

**D2 (`run_heavy` body — crash detection wrapper)**:

```python
async def run_heavy(
    task_name: str, fn: Callable, *args: Any, **kwargs: Any
) -> Any:
    """Async wrapper for ProcessPoolExecutor.submit; preserves asyncio integration.

    P0.R8 (2026-05-25): wraps dispatch in try/except to detect subprocess
    crashes via BrokenProcessPool. On crash: records event via
    _record_pool_crash() for watchdog burst-detection + RE-RAISES so caller's
    existing fallback semantic fires unchanged (P0.R1 None-return contracts +
    P0.R6.Z Q9 BrokenProcessPool → ECAPA-valley fallback all preserved).
    """
    pool = get_or_create_pool(task_name)
    loop = asyncio.get_running_loop()
    bound = functools.partial(fn, *args, **kwargs)
    try:
        return await loop.run_in_executor(pool, bound)
    except concurrent.futures.process.BrokenProcessPool:
        # P0.R8: record + re-raise (preserves caller-side fallback)
        _record_pool_crash(task_name)
        raise
```

**D3 (`_heavy_worker_watchdog_loop` in `pipeline.py`)**:

```python
async def _heavy_worker_watchdog_loop() -> None:
    """Watchdog for the 4 heavy-worker pools (AdaFace + Whisper + ECAPA +
    Pyannote). Polls every HEAVY_WORKER_WATCHDOG_INTERVAL_SECS; for each
    pool, checks crash count within HEAVY_WORKER_RESTART_BURST_WINDOW_SECS
    rolling window; on burst-threshold breach, sets pool status to
    "degraded" + dispatches WatchdogAgent.report_heavy_worker_burst alert
    once per pool per breach (re-arms when crash count drops below threshold).

    Mirror of P0.R3 _vision_watchdog_loop pattern. ProcessPoolExecutor
    auto-respawns subprocesses on next submit() after BrokenProcessPool;
    no explicit restart helper needed (materially simpler than P0.R3).
    """
    import core.heavy_worker as hw
    from core.config import (
        HEAVY_WORKER_WATCHDOG_INTERVAL_SECS,
        HEAVY_WORKER_RESTART_BURST_THRESHOLD,
        HEAVY_WORKER_RESTART_BURST_WINDOW_SECS,
    )
    _alert_armed: dict[str, bool] = {}  # per-pool armed flag; re-arms on healthy
    while _state.peek_persistent("pipeline_running"):
        await asyncio.sleep(HEAVY_WORKER_WATCHDOG_INTERVAL_SECS)
        for task_name in list(hw._HEAVY_WORKER_POOLS):
            crash_count = hw.count_recent_crashes(
                task_name, HEAVY_WORKER_RESTART_BURST_WINDOW_SECS
            )
            armed = _alert_armed.get(task_name, True)
            if crash_count >= HEAVY_WORKER_RESTART_BURST_THRESHOLD:
                if armed:
                    await _pipeline_state_store.set_heavy_worker_status(
                        task_name, "degraded"
                    )
                    if _brain_orchestrator is not None:
                        _brain_orchestrator.report_heavy_worker_burst(
                            task_name=task_name,
                            crash_count=crash_count,
                            window_secs=HEAVY_WORKER_RESTART_BURST_WINDOW_SECS,
                        )
                    print(
                        f"[HeavyWorker] WATCHDOG: pool '{task_name}' degraded — "
                        f"{crash_count} crashes in last {HEAVY_WORKER_RESTART_BURST_WINDOW_SECS:.0f}s"
                    )
                    _alert_armed[task_name] = False  # disarm until recovery
            else:
                # Crash count dropped below threshold; re-arm + clear degraded
                if not armed:
                    await _pipeline_state_store.set_heavy_worker_status(
                        task_name, "healthy"
                    )
                    print(
                        f"[HeavyWorker] WATCHDOG: pool '{task_name}' recovered — "
                        f"crash count {crash_count} < threshold "
                        f"{HEAVY_WORKER_RESTART_BURST_THRESHOLD}"
                    )
                    _alert_armed[task_name] = True
```

**D4 (`WatchdogAgent.report_heavy_worker_burst` method in `core/brain_agent.py`)**:

```python
def report_heavy_worker_burst(
    self,
    task_name: str,
    crash_count: int,
    window_secs: float,
) -> None:
    """Store a heavy-worker pool burst-crash alert.

    Called from pipeline._heavy_worker_watchdog_loop when crash count
    within HEAVY_WORKER_RESTART_BURST_WINDOW_SECS exceeds threshold.

    Severity is `warning` — heavy-worker degraded is recoverable;
    operator-actionable but not session-blocking. ProcessPoolExecutor
    auto-respawns subprocesses on next submit; recovery happens implicitly
    when crash rate drops below threshold within the window.
    """
    self._db.store_alert(
        f"heavy_worker_burst_{task_name}",
        "warning",
        f"Heavy-worker pool '{task_name}' crashed {crash_count} times in "
        f"the last {window_secs:.0f}s. Pool will auto-respawn but is marked "
        f"degraded. Check logs for crash root cause (CUDA OOM, model file "
        f"corruption, etc.).",
        {
            "task_name": task_name,
            "crash_count": crash_count,
            "window_secs": window_secs,
        },
    )
    print(
        f"[WatchdogAgent] heavy_worker_burst_{task_name} alert stored "
        f"({crash_count} crashes / {window_secs:.0f}s)"
    )
```

**D5 (`HealthSnapshot` extension + `format_health_line` + `format_health_alerts`)**:

Extend `HealthSnapshot` with `heavy_worker_crash_counts: dict[str, int] = field(default_factory=dict)`. Gather function reads via `hw.count_recent_crashes(task_name, HEAVY_WORKER_RESTART_BURST_WINDOW_SECS)` for each pool.

`format_health_line` extended: when ANY pool's recent crash count > 0, conditionally emit `heavy_worker_crashes=N` field (mirrors P0.R6 D4 `heavy_workers=degraded` pattern).

`format_health_alerts` extended: on degraded pool, emit actionable recovery alert with verbatim substrings: `"Heavy-worker pool"`, `"degraded"`, `"auto-respawn"`, `"check logs"`, `"clears when crash rate drops"`. Mirrors P0.R3 D3 actionable recovery alert pattern.

**D6 (`pipeline.run()` startup wiring + shutdown ordering)**:

```python
# AFTER the 4 pool warm-ups + vision task spawn + vision watchdog spawn
# (P0.R6.* D5 ordering + P0.R3 D5 ordering preserved)
_heavy_worker_watchdog_task = asyncio.create_task(_heavy_worker_watchdog_loop())

# Shutdown ordering (finally block):
# (a) cancel heavy_worker_watchdog FIRST (before pool shutdown so it doesn't
#     observe shutdown-in-progress crashes as bursts)
# (b) cancel vision_watchdog
# (c) cancel vision_task
# (d) hw.shutdown_all_pools(wait=True) (existing P0.R6 D5 shutdown)
```

ORDERING INVARIANT: heavy_worker_watchdog spawned AFTER vision_watchdog (which depends on vision_task). Watchdog cancellation at shutdown happens FIRST so the watchdog doesn't observe pool shutdown as crash events.

---

## §4 Anchor count proposal (Q5)

**Mid 9 INCLUSIVE ±15% band → [7.65, 10.35] → ON-TARGET = 8, 9, or 10 anchors**:

- **A1**: `_HEAVY_WORKER_CRASH_HISTORY` dict + `_record_pool_crash` + `count_recent_crashes` + `peek_crash_history` accessors present in `core/heavy_worker.py` (source-inspection)
- **A2**: `run_heavy` body catches `BrokenProcessPool` + records + re-raises (AST positive + inverse: try/except is wrapping the dispatch, NOT bare; exception is RAISED not swallowed)
- **A3**: `_heavy_worker_watchdog_loop` async function exists in `pipeline.py` (source-inspection)
- **A4**: Watchdog polls every `HEAVY_WORKER_WATCHDOG_INTERVAL_SECS` (behavioral test with mocked sleep)
- **A5**: Burst detection logic — N crashes in M-sec window triggers degraded; below threshold re-arms (behavioral test with crafted crash timestamps)
- **A6**: `WatchdogAgent.report_heavy_worker_burst` method exists + stores alert via `_db.store_alert(...)` (source-inspection + behavioral)
- **A7**: `HealthSnapshot.heavy_worker_crash_counts: dict[str, int]` field present + `format_health_line` conditionally emits `heavy_worker_crashes=N` (source-inspection + behavioral)
- **A8**: Startup ordering — heavy_worker_watchdog spawn lands AFTER vision_watchdog spawn AND AFTER 4 pool warm-ups (AST line-order check)
- **A9**: 3 config constants present (`HEAVY_WORKER_WATCHDOG_INTERVAL_SECS` + `HEAVY_WORKER_RESTART_BURST_THRESHOLD` + `HEAVY_WORKER_RESTART_BURST_WINDOW_SECS`)

**Closure-projection band table**:

| closure-actual | overage vs mid 9 | band | doctrine outcome |
|---|---|---|---|
| 7 | −22.2% | SLIGHT-DRIFT-DOWN (within ±30%) | `### Phase-0-granular-decomposition` HOLDS at 22 supporting |
| 8 | −11.1% | ON-TARGET | `### Phase-0-granular-decomposition` 22 → 23 supporting |
| 9 | 0% | ON-TARGET exact mid | `### Phase-0-granular-decomposition` 22 → 23 supporting + 2nd consecutive 0%-streak rebuild instance |
| 10 | +11.1% | ON-TARGET | `### Phase-0-granular-decomposition` 22 → 23 supporting |
| 11 | +22.2% | SLIGHT-DRIFT-UP (within ±30%) | `### Phase-0-granular-decomposition` HOLDS at 22 supporting |
| ≥12 OR ≤6 | beyond ±30% | FALSIFICATION TRIGGER | doctrine demotes back to architect-memory + reasoning audit |

---

## §5 OUT-OF-SCOPE classification

1. **Crash diagnostic capture** — DEFERRED to P0.R11 (stack traces + write to `faces/crash_logs/` + dashboard exposure). P0.R8 captures only `(task_name, timestamp)` tuples for burst detection.
2. **Explicit pool restart logic** — `ProcessPoolExecutor` auto-respawns on next `submit()`; P0.R8 doesn't need explicit restart helper (materially simpler than P0.R3 vision-loop restart).
3. **Stuck task detection** — subprocess hangs (doesn't crash but blocks longer than expected). Separate failure mode + adds complexity (timeout per task class); banked for future cycle.
4. **Pool-level permanent disable** — burst-limit sets pool status to "degraded" but auto-respawn STILL works. Operator-actionable, not auto-disabled. Permanent disable would require config flag + manual recovery + risk of cascading inability-to-recover; defer.
5. **Cross-pool crash correlation** — if multiple pools crash simultaneously (e.g. CUDA driver crash affects all 4 pools), watchdog still treats each pool independently. Cross-pool correlation analysis is observability/dashboard concern, not P0.R8 scope.
6. **VRAM exhaustion prediction** — P0.R9 candidate (cumulative VRAM budget guard); P0.R8 detects crashes that may be caused by VRAM exhaustion but doesn't predict or prevent.

---

## §6 Locked-down discipline counters

Per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine: auditor DILIGENT Pass-2 grep at Plan v1 §1 will independently verify §1.1 8-row + §1.2 4-row + §1.3 7-row + §1.4 3-row + §1.5 7-row cross-spec table.

Per `feedback_pass_2_grep_deferral_pattern.md` (banked at P0.R6.Y closure-audit): NO "developer Phase N surfaces enumeration" framings in this Phase 0 — all surfaces enumerated upfront with explicit per-surface disposition.

**`### Pre-audit-quantifier-precision-refined-by-grep` instance enumeration** (post-P0.R6.Z closure baseline; CLAUDE.md canonical at lines 646-770 with 8-axis sub-shape taxonomy locked at P0.R6.Z closure-audit):

Phase 0 grep CONFIRMS pre-audit framing — no quantifier refinement event fires. Pre-audit said "4 heavy-worker pools" + "P0.R3 watchdog pattern" + "5s poll cadence" + "WatchdogAgent burst alert"; grep verified all 4 surfaces match (4 pools registered, P0.R3 pattern at expected line refs, P0.R6 D4 dict foundation, WatchdogAgent burst alert precedents). **Per operational rule 3 of `### Pre-audit-quantifier-precision-refined-by-grep`**: "If Phase 0 grep CONFIRMS the pre-audit framing (no refinement needed), no instance bank fires." Doctrine STAYS at 8 instances; this Phase 0 is a clean-confirmation cycle.

---

## §7 Q-questions for adjudication

**Q1 (Crash detection location)**:
Where does `BrokenProcessPool` detection happen?
- Option (a): `run_heavy` wrapper catches + records + re-raises (centralized, 1 surface)
- Option (b): Each of 4 callers catches + reports via observability hook (decentralized, 4 surfaces)

**Architect lean: (a)** — centralized; preserves existing caller-side fallback semantics (re-raise propagates `BrokenProcessPool` exception to caller's existing try/except).

**Q2 (Restart-counter location)**:
Where does crash history live?
- Option (a): Module-level dict in `core/heavy_worker.py` (`_HEAVY_WORKER_CRASH_HISTORY`)
- Option (b): Extended `_heavy_worker_status` dict at PipelineStateStore with status string encoding count

**Architect lean: (a)** — keeps crash-detection state co-located with pool registry; PipelineStateStore stays scalar status-only ("healthy" / "degraded") for clean separation. Watchdog reads both: status from PipelineStateStore, crash count from `core/heavy_worker.py`.

**Q3 (Burst window mechanism)**:
- Option (a): Rolling time window (`now - WINDOW_SECS`); event list pruned at watchdog poll
- Option (b): Fixed N-of-last-M event count (no time component)

**Architect lean: (a)** — rolling time window matches P0.R4 systemd `StartLimitIntervalSec=60s` pattern + naturally bounds memory growth (events older than window pruned).

**Q4 (Watchdog poll cadence)**:
- Option (a): 5s (mirror P0.R3)
- Option (b): 1s (faster detection, more CPU)
- Option (c): 10s (slower detection, less CPU)

**Architect lean: (a)** — 5s mirrors P0.R3. Burst-detection latency ≤5s is acceptable for operator alert (the crashes themselves already happened; watchdog is reporting, not preventing).

**Q5 (Burst-limit semantic)**:
- Option (a): Set pool status to "degraded" + alert; auto-respawn STILL works
- Option (b): Set pool status to "degraded" + actively prevent further `run_heavy` dispatch (refuse with cached None response)
- Option (c): Permanent-disable pool (`shutdown(wait=False)` + don't recreate); requires manual recovery

**Architect lean: (a)** — soft degradation. Pool stays available; auto-respawn lets it recover. Operator sees alert + can intervene if needed. Option (b)/(c) risk cascading failure cascade-prevention vs auto-recovery; (a) is the more graceful default.

**Q6 (Restart-burst reset semantic)**:
- Option (a): Auto re-arm when crash count drops below threshold (rolling-window-based; events age out)
- Option (b): Manual reset only (operator clears via dashboard or restart)
- Option (c): Time-based reset (e.g. 1 hour without crash → re-arm)

**Architect lean: (a)** — automatic recovery via rolling window. Events age out; once crash count drops below threshold for ≥1 watchdog cycle, pool flips back to "healthy" + watchdog alert re-arms.

**Q7 (HealthSnapshot extension)**:
Add `heavy_worker_crash_counts: dict[str, int]` to HealthSnapshot? OR keep crash count internal to watchdog?
- Option (a): Add field to HealthSnapshot (dashboard visibility)
- Option (b): Status string-only (no count exposed)

**Architect lean: (a)** — dashboard visibility is valuable for canary observation. Adding the field is ~1 LOC; surfaces structured data instead of operators parsing log lines.

**Q8 (Crash diagnostic capture P0.R8 vs P0.R11 split)**:
P0.R8 captures `(task_name, timestamp)` tuples — minimal. P0.R11 will add exception_type + stack_trace + write to `faces/crash_logs/`.
- Option (a): Confirm split; P0.R8 minimal, P0.R11 full diagnostics
- Option (b): Include exception_type in P0.R8 (light extension)
- Option (c): Include full diagnostics in P0.R8 (collapse P0.R11 into P0.R8)

**Architect lean: (a)** — preserves cycle scope. P0.R11 has standalone value (extends beyond heavy-worker crashes to ALL unhandled exceptions in worker threads). Don't merge.

**Q9 (`pipeline_running` shutdown signal)**:
P0.R3 vision watchdog uses `_state.peek_persistent("pipeline_running")` as loop continuation predicate. Does P0.R8 use the same OR introduce a separate flag?
- Option (a): Same predicate (`_state.peek_persistent("pipeline_running")`)
- Option (b): Separate flag (`heavy_worker_watchdog_running`)

**Architect lean: (a)** — same shutdown signal as P0.R3. Single source of truth for pipeline running state; both watchdogs cancel uniformly at shutdown.

---

## §8 Doctrine-firing projections at closure

If P0.R8 closes cleanly with closure-actual = 9 anchors at exact mid:

- `### Phase-0-granular-decomposition-enables-accurate-estimates` 22 → 23 supporting
- `Doctrine-prediction-precision-improving-over-arc` 2nd consecutive 0%-streak rebuild instance (was 1 after P0.R6.Z; P0.R8 exact-mid = 2 consecutive)
- `### Pre-audit-quantifier-precision-refined-by-grep` STAYS at 8 instances (Phase 0 grep CONFIRMS pre-audit; no refinement)
- `### Phase-0-catches-wrong-premise` STAYS at 13 (premise correct)
- `### Zero-precision-items-at-auditor-review` 25 → 27 (Phase 0 + Plan v1 if cycle clears cleanly; 27th instance = 3rd consecutive zero-PI surface in resilience track)
- OPTIONAL-Plan-v2 sub-rule track record 11 → 12 proof cases (if 3-artifact cycle ships)
- `### Architect-reads-production-code-before-sign-off` 21 → 22 at closure-audit (5th-cycle self-sustaining adoption per `Implicit-doctrine-firings-not-narrative-tracked` operational rule)
- Strict-industry-standard mode 83 → 86 applications + 24 → 25 closures
- Spec-first review cycle 92 → 95-for-95 at closure
- `### Grep-baseline-before-drafting` 50 → 53 instances
- Cross-cycle-handoff transparency 56 → 59 successful
- Spec-time grep-verification 60 → 63 instances
- `### Twin-filename-pitfall-prevention` 23 → 24 preventive events
- Auditor-Q5-estimates-trail-grep 28 → 29 banked closures
- Deferred-canary strategy 26 → 27 applications

---

## §9 Architect-handoff items for auditor verdict

1. **Pass-2 grep verification** (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine): independent re-grep §1.1 8-row + §1.2 4-row + §1.3 7-row + §1.4 3-row + §1.5 7-row cross-spec table. **Per `feedback_pass_2_grep_deferral_pattern.md` LOCKED at P0.R6.Y closure-audit**: NO deferral framings in this Phase 0. If auditor surfaces additional sites OR cross-spec interactions, lock as Plan v1 PI #1 absorption per Option α pattern.

2. **Q1-Q9 adjudication**: confirm architect leans OR substitute. Q1 (centralized detection) + Q5 (soft degradation) are LOAD-BEARING; Q2-Q4 + Q6-Q9 are implementation refinements per P0.R3/P0.R4/P0.R6 precedent.

3. **Anchor count adjudication**: confirm mid 9 INCLUSIVE ±15% band [7.65, 10.35] OR substitute. P0.R8 is materially simpler than P0.R3 (no explicit restart helper; ProcessPoolExecutor auto-respawns) so 9 anchors covers detection + tracking + alert + observability cleanly.

4. **Clean-confirmation cycle for `### Pre-audit-quantifier-precision-refined-by-grep`**: per §6 banking, Phase 0 grep CONFIRMS pre-audit framing — no refinement event fires. Doctrine STAYS at 8 instances. Confirm this is correct application of operational rule 3 (no instance bank when grep confirms pre-audit).

5. **P0.R8 scope vs P0.R11 split**: Q8 banks crash-diagnostic capture in P0.R11. Confirm this split holds OR merge if auditor judgment is otherwise.

---

**End of Phase 0 audit.** Ready for auditor verdict.
