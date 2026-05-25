# P0.R8 — Heavy-worker pool watchdog + restart-burst limit + crash observability (Plan v1)

**Date**: 2026-05-25
**Author**: architect (Claude)
**Phase 0 verdict**: ACCEPTED with 1 BLOCKING PI (Q9 D3 loop predicate misidentification; absorbed in Plan v1 §2.3 + §2.6 + §9). 8/9 Q-questions RATIFIED per architect leans. Pass-2 grep doctrine catching mechanism validated in 2nd validation mode (1st caught-real-gap cycle since elevation).
**Cycle shape**: SMALL-MEDIUM band, 3-artifact OPTIONAL-Plan-v2 path candidate (12th proof case if Plan v1 clears cleanly post-absorption)

---

## §0 PI #1 absorption (Plan v1 entry condition)

**PI #1 (MEDIUM)**: §3 D3 code template referenced `_state.peek_persistent("pipeline_running")` predicate that **does NOT exist** in production. P0.R3 `_vision_watchdog_loop` actual at `pipeline.py:2411` uses bare `while True:` + explicit `.cancel()` at shutdown via `asyncio.wait_for(..., timeout=1.0)` (per shutdown finally at `pipeline.py:8341-8344`).

**Auditor's catching event**: independent Pass-2 grep verified zero matches for `peek_persistent` in `core/state.py` + zero matches for `pipeline_running` literal in `pipeline.py` or `core/state.py`. The architect's Q9 framing was mis-grounded — both Q9 (a) and Q9 (b) referenced infrastructure that doesn't exist.

**Absorption per auditor's recommendation**:

1. **§2.3 D3 substitution**: bare `while True:` loop body (mirror P0.R3 actual at `pipeline.py:2411`)
2. **§2.6 D6 shutdown wiring**: explicit `.cancel()` + `await asyncio.wait_for(_heavy_worker_watchdog_task, timeout=1.0)` + suppress `(CancelledError, TimeoutError, Exception)` (mirror P0.R3 actual at `pipeline.py:8341-8346`)
3. **§9 Q9 re-framing**: re-cast Q9 as "bare `while True:` with explicit `.cancel()` at shutdown (matches P0.R3 actual implementation)". Spirit of "same pattern as P0.R3" preserved; only the misidentification of what the pattern IS gets corrected.

**Banking event**: `Plan-v1-Pass-2-grep-undercount` STAYS at 11 if PI #1 absorbed cleanly at Plan v1 (no NEW instance fires); converts to 11 → 12 candidate AT AUDITOR-SIDE if PI absorption surfaces additional drift at Plan v1 verdict.

**Catching credit (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine)**: This is the **1st caught-real-gap cycle for the doctrine since elevation at P0.R4 closure-audit**. Prior 5 cycles (P0.R5 + P0.R6 + P0.R6.X + P0.R6.Y + P0.R6.Z) all cleared at Plan v1 verdict cleanly. P0.R8 demonstrates the doctrine's catching mechanism in its 2nd validation mode (clean-pass + caught-real-gap = both validation modes proven). Doctrine maturation evidence: catching mechanism active across 9 consecutive cycles in BOTH modes.

---

## §1 Pass-2 grep verification (architect-side, per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval`)

### §1.1 Heavy-worker pool current state (Phase 0 §1.1 LOCKED; re-verified at Plan v1 draft)

| # | Surface | File:Line | Verified |
|---|---|---|---|
| 1 | `_HEAVY_WORKER_POOLS: dict[str, ProcessPoolExecutor]` | `core/heavy_worker.py:33` | ✓ |
| 2 | `get_or_create_pool(task_name, max_workers=1)` | `core/heavy_worker.py:66` | ✓ |
| 3 | `run_heavy(task_name, fn, *args, **kwargs)` body (NO try/except) | `core/heavy_worker.py:92-109` | ✓ — auditor Pass-2 confirmed zero try/except wrap |
| 4 | `shutdown_all_pools(wait=True)` | `core/heavy_worker.py:112-122` | ✓ |
| 5 | `_heavy_worker_status: dict[str, str]` at PipelineStateStore | `core/pipeline_state_store.py:90` | ✓ |
| 6 | `peek_heavy_worker_status()` accessor | `core/pipeline_state_store.py:150` | ✓ |
| 7 | `set_heavy_worker_status(task_name, status)` async setter | `core/pipeline_state_store.py:156` | ✓ |
| 8 | `HealthSnapshot.heavy_worker_status: dict[str, str]` field | `core/health.py:70` | ✓ |

4 pools registered at startup confirmed: `adaface_embed` (line 6516) / `whisper_transcribe` (line 6530) / `ecapa_embed` (line 6541) / `pyannote_diarize` (line 6557).

### §1.2 P0.R3 actual watchdog pattern (LOAD-BEARING reference for Plan v1 absorption)

| Surface | File:Line | Pattern |
|---|---|---|
| `_vision_watchdog_loop` async function definition | `pipeline.py:2402` | Watchdog body starts at 2410 |
| **Loop predicate** | `pipeline.py:2411` | **`while True:`** (bare; NOT predicate-driven) |
| Sleep dispatch | `pipeline.py:2412` | `await asyncio.sleep(VISION_WATCHDOG_INTERVAL_SECS)` |
| Watchdog spawn | `pipeline.py:6565` | `_vision_watchdog_task = asyncio.create_task(_vision_watchdog_loop())` |
| **Shutdown cancel pattern** | `pipeline.py:8341-8346` | Explicit `.cancel()` + `asyncio.wait_for(..., timeout=1.0)` + `except (CancelledError, TimeoutError, Exception): pass` |

**LOAD-BEARING**: P0.R8 watchdog mirrors P0.R3 shape — bare `while True:` body + explicit shutdown cancel via `.cancel()` + `wait_for(timeout=1.0)`. Cancellation propagates via `CancelledError` to break the bare-while-True loop cleanly.

### §1.3 P0.R3 shutdown ordering (LOAD-BEARING reference)

```python
# pipeline.py:8341-8346 (verbatim)
if _vision_watchdog_task and not _vision_watchdog_task.done():
    _vision_watchdog_task.cancel()
    try:
        await asyncio.wait_for(_vision_watchdog_task, timeout=1.0)
    except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
        pass
```

P0.R8 wiring lands IMMEDIATELY ABOVE this block (so heavy_worker_watchdog cancels FIRST, then vision_watchdog, then vision_task — preserves P0.R3 D5 ordering invariant).

### §1.4 Cross-spec interactions (Phase 0 §1.5 LOCKED; re-verified at Plan v1 draft)

| Spec | Interaction | Status |
|---|---|---|
| P0.R1 | None-return fallback contracts | LOAD-BEARING (preserved via re-raise in D2) |
| P0.R3 | Vision-loop watchdog | EXTENDS pattern (bare while True + explicit .cancel() shutdown) |
| P0.R4 | Process supervisor | COMPLEMENTARY |
| P0.R6 D4 | `_heavy_worker_status` dict | EXTENDS (adds "degraded" status value) |
| P0.R6 D5 | Pool warm-up ordering | NO conflict (watchdog spawns AFTER pool warm-ups + vision watchdog) |
| WatchdogAgent | Burst-alert pattern | EXTENDS (new `report_heavy_worker_burst` method) |
| Session 42 / Wave 5 Items 19+20 | Health log + disk monitor | COMPLEMENTARY |

### §1.5 Pre-audit refinement banking (Phase 0 §6 LOCKED — clean-confirmation per operational rule 3)

Phase 0 grep CONFIRMS pre-audit framing — no quantifier refinement event fires. `### Pre-audit-quantifier-precision-refined-by-grep` STAYS at 8 instances. This is the **1st clean-confirmation since elevation at P0.R6 closure-audit** — meaningful negative-evidence validation of doctrine operational rule 3.

PI #1 surfaced at Phase 0 is **NOT a quantifier refinement** — it's a code-template predicate misidentification (separate orthogonal failure mode). Banked under `Plan-v1-Pass-2-grep-undercount` family (deferred to verdict).

---

## §2 D-decision spec (6 D-decisions, locked from Phase 0; Q1-Q8 RATIFIED; Q9 absorbed via PI #1)

### §2.1 D1 — `core/heavy_worker.py` crash history + burst detection

**LOCKED**. Module-level crash history with thread-safe accessors (since `run_heavy` is async + executor threads may race on the same task_name).

```python
# Add near top of core/heavy_worker.py (after _HEAVY_WORKER_POOLS declaration)
import threading

# P0.R8 module-level crash history (main process state; subprocesses don't see it)
_HEAVY_WORKER_CRASH_HISTORY: "dict[str, list[float]]" = {}
_HEAVY_WORKER_CRASH_LOCK = threading.Lock()


def _record_pool_crash(task_name: str, now: "float | None" = None) -> None:
    """Record a pool-crash event for burst detection. Called from
    run_heavy()'s BrokenProcessPool catch block.

    Thread-safe via _HEAVY_WORKER_CRASH_LOCK — concurrent run_heavy() calls
    from multiple coroutines can race on the same task_name's history list.

    Crash events stay in history indefinitely between calls; count_recent_crashes
    filters + prunes by HEAVY_WORKER_RESTART_BURST_WINDOW_SECS at watchdog
    poll time, bounding memory growth.
    """
    if now is None:
        now = time.time()
    with _HEAVY_WORKER_CRASH_LOCK:
        _HEAVY_WORKER_CRASH_HISTORY.setdefault(task_name, []).append(now)


def count_recent_crashes(
    task_name: str, window_secs: float, now: "float | None" = None
) -> int:
    """Return number of crashes for task_name within the rolling
    `window_secs` window ending at `now`. Implicitly prunes events older
    than window_secs (writes back filtered list).
    """
    if now is None:
        now = time.time()
    cutoff = now - window_secs
    with _HEAVY_WORKER_CRASH_LOCK:
        events = _HEAVY_WORKER_CRASH_HISTORY.get(task_name, [])
        events = [t for t in events if t >= cutoff]
        _HEAVY_WORKER_CRASH_HISTORY[task_name] = events
        return len(events)


def peek_crash_history(task_name: str) -> "list[float]":
    """Return COPY of crash history for task_name. Read-only accessor for
    tests + health observability."""
    with _HEAVY_WORKER_CRASH_LOCK:
        return list(_HEAVY_WORKER_CRASH_HISTORY.get(task_name, []))
```

### §2.2 D2 — `run_heavy` body crash detection wrapper

**LOCKED**. Try/except around `loop.run_in_executor(pool, bound)` catches `BrokenProcessPool` + records + re-raises:

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

### §2.3 D3 — `_heavy_worker_watchdog_loop` in `pipeline.py` (PI #1 ABSORBED)

**LOCKED with PI #1 absorption — bare `while True:` per P0.R3 actual at line 2411**:

```python
async def _heavy_worker_watchdog_loop() -> None:
    """Watchdog for the 4 heavy-worker pools (AdaFace + Whisper + ECAPA +
    Pyannote). Polls every HEAVY_WORKER_WATCHDOG_INTERVAL_SECS; for each
    pool, checks crash count within HEAVY_WORKER_RESTART_BURST_WINDOW_SECS
    rolling window; on burst-threshold breach, sets pool status to
    "degraded" + dispatches WatchdogAgent.report_heavy_worker_burst alert
    once per pool per breach (re-arms when crash count drops below threshold).

    Mirror of P0.R3 _vision_watchdog_loop pattern (pipeline.py:2402-2510):
    bare ``while True:`` body + cancellation propagates via CancelledError
    at shutdown via explicit .cancel() + asyncio.wait_for(..., timeout=1.0)
    in the pipeline.run() finally block.

    ProcessPoolExecutor auto-respawns subprocesses on next submit() after
    BrokenProcessPool; no explicit restart helper needed (materially simpler
    than P0.R3 which needed _restart_vision_task helper for vision-task
    lifecycle management).
    """
    import core.heavy_worker as hw
    from core.config import (
        HEAVY_WORKER_WATCHDOG_INTERVAL_SECS,
        HEAVY_WORKER_RESTART_BURST_THRESHOLD,
        HEAVY_WORKER_RESTART_BURST_WINDOW_SECS,
    )
    # Per-pool alert-armed flag; re-arms when crash count drops below threshold.
    # Initialized lazily as we encounter each pool name.
    _alert_armed: "dict[str, bool]" = {}
    while True:
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
                        f"{crash_count} crashes in last "
                        f"{HEAVY_WORKER_RESTART_BURST_WINDOW_SECS:.0f}s"
                    )
                    _alert_armed[task_name] = False  # disarm until recovery
            else:
                # Crash count dropped below threshold → re-arm + clear degraded
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

### §2.4 D4 — `WatchdogAgent.report_heavy_worker_burst` method

**LOCKED**. New method in `core/brain_agent.py::WatchdogAgent` class (mirrors `report_dispute_rename_burst` + `report_anti_spoof_burst` + `report_disk_threshold` precedents):

```python
def report_heavy_worker_burst(
    self,
    task_name: str,
    crash_count: int,
    window_secs: float,
) -> None:
    """Store a heavy-worker pool burst-crash alert.

    Called from pipeline._heavy_worker_watchdog_loop when crash count within
    HEAVY_WORKER_RESTART_BURST_WINDOW_SECS exceeds threshold.

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

### §2.5 D5 — `HealthSnapshot` extension + `format_health_line` + `format_health_alerts`

**LOCKED**. Three sub-changes in `core/health.py`:

1. **`HealthSnapshot` dataclass field addition**:
   ```python
   heavy_worker_crash_counts: "dict[str, int]" = field(default_factory=dict)
   ```

2. **Gather function** (in `gather_health_snapshot`):
   ```python
   # P0.R8 — per-pool crash count within burst window
   import core.heavy_worker as hw
   from core.config import HEAVY_WORKER_RESTART_BURST_WINDOW_SECS
   heavy_worker_crash_counts: "dict[str, int]" = {}
   for task_name in list(hw._HEAVY_WORKER_POOLS):
       heavy_worker_crash_counts[task_name] = hw.count_recent_crashes(
           task_name, HEAVY_WORKER_RESTART_BURST_WINDOW_SECS
       )
   ```

3. **`format_health_line` conditional emit**: when ANY pool has crash count > 0, emit `heavy_worker_crashes=N` field where N is the total across all pools. Mirrors P0.R6 D4 `heavy_workers=degraded` conditional pattern.

4. **`format_health_alerts` actionable recovery alert**: on any pool with status="degraded", emit alert with verbatim substrings:
   - `"Heavy-worker pool"` (alert prefix)
   - `"degraded"` (state name)
   - `"auto-respawn"` (recovery mechanism)
   - `"check logs"` (operator action)
   - `"clears when crash rate drops"` (recovery semantic)

### §2.6 D6 — `pipeline.run()` startup wiring + shutdown ordering (PI #1 ABSORBED)

**LOCKED with PI #1 absorption — explicit `.cancel()` + `wait_for(timeout=1.0)` shutdown per P0.R3 actual at pipeline.py:8341-8346**:

**Startup wiring** (after vision_watchdog spawn at pipeline.py:6565, BEFORE the `await asyncio.sleep(0.1)` at line 6566):

```python
# P0.R8 D6 — spawn heavy-worker watchdog AFTER vision_watchdog (mirrors
# P0.R3 D5 spawn ordering). Watches the 4 heavy-worker pools created by
# P0.R6.* arc; detects subprocess crashes via BrokenProcessPool +
# burst-limit + degraded-state observability.
_heavy_worker_watchdog_task = asyncio.create_task(_heavy_worker_watchdog_loop())
```

Note: `_heavy_worker_watchdog_task` is declared at module scope (alongside `_vision_watchdog_task` at ~pipeline.py:2386-2387 — see ORDERING INVARIANT below).

**Shutdown wiring** (in pipeline.run() finally block, IMMEDIATELY ABOVE the existing P0.R3 D5 vision_watchdog cancel at pipeline.py:8341):

```python
# P0.R8 D6 ORDERING INVARIANT — cancel heavy_worker_watchdog FIRST so it
# doesn't observe pool shutdown as crash events. Order: heavy_worker_watchdog
# → vision_watchdog → vision_task → hw.shutdown_all_pools (existing P0.R6 D5).
if _heavy_worker_watchdog_task and not _heavy_worker_watchdog_task.done():
    _heavy_worker_watchdog_task.cancel()
    try:
        await asyncio.wait_for(_heavy_worker_watchdog_task, timeout=1.0)
    except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
        pass
```

**Module-scope declaration** (mirror `_vision_watchdog_task` at pipeline.py:2386-2387):

```python
# P0.R8 D6 — heavy-worker watchdog supervises the 4 pools (AdaFace + Whisper
# + ECAPA + Pyannote). Spawned in run() AFTER vision_watchdog; cancelled
# FIRST at shutdown per ORDERING INVARIANT.
_heavy_worker_watchdog_task: "asyncio.Task | None" = None
```

### §2.7 D7 — `core/config.py` constants

**LOCKED** (3 new constants):

```python
# P0.R8 — heavy-worker pool watchdog + burst-limit constants. The watchdog
# at pipeline._heavy_worker_watchdog_loop polls every WATCHDOG_INTERVAL_SECS;
# for each pool, if BURST_THRESHOLD crashes occur within BURST_WINDOW_SECS,
# the pool is marked "degraded" + a WatchdogAgent alert fires (recoverable;
# auto-respawn keeps working).
HEAVY_WORKER_WATCHDOG_INTERVAL_SECS    = 5.0    # poll cadence (matches P0.R3)
HEAVY_WORKER_RESTART_BURST_THRESHOLD   = 3      # N crashes in window → degraded
HEAVY_WORKER_RESTART_BURST_WINDOW_SECS = 300.0  # 5 minute rolling window
```

### §2.8 Deliberate-regression scenarios (per `### Induction-surfaces-invariant-gaps` doctrine)

9 scenarios for the 9 anchors:

| Revert | Expected anchor fire | Catches |
|---|---|---|
| (a) Delete `_HEAVY_WORKER_CRASH_HISTORY` + accessors from heavy_worker.py | A1 | Crash history infrastructure gone |
| (b) Remove try/except from `run_heavy` body | A2 | Crash detection wrapper gone (re-raise inverse check: no `_record_pool_crash` call) |
| (c) Delete `_heavy_worker_watchdog_loop` async function | A3 | Watchdog loop gone |
| (d) Replace `HEAVY_WORKER_WATCHDOG_INTERVAL_SECS` with hardcoded `1.0` in sleep call | A4 | Poll cadence regression |
| (e) Replace burst-threshold check `>= HEAVY_WORKER_RESTART_BURST_THRESHOLD` with `>= 999` | A5 | Burst detection logic broken (never fires) |
| (f) Delete `report_heavy_worker_burst` method from `WatchdogAgent` | A6 | Alert method gone |
| (g) Remove `heavy_worker_crash_counts` field from `HealthSnapshot` | A7 | Health snapshot field gone |
| (h) Reverse startup ordering — heavy_worker_watchdog spawn BEFORE vision_watchdog | A8 | Ordering invariant broken |
| (i) Delete the 3 new config constants | A9 | Config constants gone |

9/9 1:1 with anchors.

---

## §3 Logical anchor LOCK (Q5 LOCK = 9 anchors at EXACT MID)

Per auditor Phase 0 verdict §4 Q5 ratification: **9 anchors at exact mid 9 INCLUSIVE ±15% band [7.65, 10.35]**.

| # | Anchor | Surface | Coverage |
|---|---|---|---|
| A1 | `_HEAVY_WORKER_CRASH_HISTORY` dict + `_record_pool_crash` + `count_recent_crashes` + `peek_crash_history` present in `core/heavy_worker.py` | Source-inspection | D1 |
| A2 | `run_heavy` body AST shows `try` + `except concurrent.futures.process.BrokenProcessPool:` + call to `_record_pool_crash(task_name)` + bare `raise` (positive + inverse: no bare `except: pass`; exception is RE-RAISED) | AST positive + inverse | D2 |
| A3 | `_heavy_worker_watchdog_loop` async function exists in `pipeline.py` with bare `while True:` body | Source-inspection + AST | D3 |
| A4 | Watchdog sleeps `HEAVY_WORKER_WATCHDOG_INTERVAL_SECS` per iteration (behavioral test with mocked sleep) | Behavioral | D3 |
| A5 | Burst detection: ≥ `HEAVY_WORKER_RESTART_BURST_THRESHOLD` crashes in `HEAVY_WORKER_RESTART_BURST_WINDOW_SECS` window triggers degraded; below threshold re-arms (behavioral test with crafted timestamps) | Behavioral | D3 |
| A6 | `WatchdogAgent.report_heavy_worker_burst` method exists + stores alert via `_db.store_alert(...)` (source-inspection + behavioral) | Source + behavioral | D4 |
| A7 | `HealthSnapshot.heavy_worker_crash_counts: dict[str, int]` field present + gather function populates from `hw.count_recent_crashes` | Source-inspection + behavioral | D5 |
| A8 | Startup ordering AST line-order: `_heavy_worker_watchdog_task = asyncio.create_task(_heavy_worker_watchdog_loop())` lands AFTER `_vision_watchdog_task` spawn AND AFTER all 4 pool warm-ups | AST line-order | D6 |
| A9 | 3 config constants present: `HEAVY_WORKER_WATCHDOG_INTERVAL_SECS` + `HEAVY_WORKER_RESTART_BURST_THRESHOLD` + `HEAVY_WORKER_RESTART_BURST_WINDOW_SECS` | Source-inspection | D7 |

---

## §4 Honest-count commitment (per `Explicit-closure-honest-count-commitment` discipline)

Closure-actual count will land at exactly **9 anchors** per Plan v1 LOCK. ON-TARGET range is 8-10. If implementation reveals a 10th anchor warranting addition (e.g. defense-in-depth at developer Phase 4), closure-narrative SHALL bank as ON-TARGET +11.1% per band table. Closure-actual UNDER 8 OR OVER 10 SHALL invoke the honest-narrative path.

**20th instance of `Explicit-closure-honest-count-commitment` discipline** banked here at Plan v1 §4 (MADE); closure HONORED at closure-audit firing 21st instance per STRICT separation locked at P0.B3.

---

## §5 Phase-by-phase implementation plan

**Phase 1 — `core/heavy_worker.py` crash history + accessors (D1) + `run_heavy` wrapper (D2)** (~30 min):

1. Open `core/heavy_worker.py`.
2. Add `import threading` at top if not already present.
3. After `_HEAVY_WORKER_POOLS` declaration (line 33), add `_HEAVY_WORKER_CRASH_HISTORY` + `_HEAVY_WORKER_CRASH_LOCK`.
4. After `shutdown_all_pools` (line 122), add `_record_pool_crash` + `count_recent_crashes` + `peek_crash_history` accessors per §2.1.
5. Wrap `run_heavy` body per §2.2: try/except around `loop.run_in_executor` catches `BrokenProcessPool` + records + re-raises.
6. Verify `import concurrent.futures` is already at top of file (it is per existing imports; no change needed).

**Phase 2 — `core/config.py` constants (D7)** (~5 min):

1. Add 3 constants per §2.7 at end of `core/config.py` (or appropriate section near other watchdog constants).

**Phase 3 — `core/health.py` extension (D5)** (~20 min):

1. Add `heavy_worker_crash_counts: dict[str, int] = field(default_factory=dict)` field to `HealthSnapshot` dataclass.
2. Update `gather_health_snapshot` to populate `heavy_worker_crash_counts` per §2.5.
3. Extend `format_health_line` conditional emit when any crash count > 0.
4. Extend `format_health_alerts` with degraded-pool actionable recovery alert.

**Phase 4 — `core/brain_agent.py` WatchdogAgent method (D4)** (~15 min):

1. Add `report_heavy_worker_burst` method to `WatchdogAgent` class per §2.4 (placement: after `report_disk_threshold` at line ~6580).

**Phase 5 — `pipeline.py` watchdog loop + startup wiring + shutdown ordering (D3 + D6)** (~30 min):

1. Add `_heavy_worker_watchdog_task: "asyncio.Task | None" = None` at module scope (near `_vision_watchdog_task` at ~line 2386-2387).
2. Add `_heavy_worker_watchdog_loop` async function per §2.3 (placement: AFTER `_vision_watchdog_loop` definition).
3. Add startup spawn after vision_watchdog spawn (after line 6565) per §2.6.
4. Add shutdown cancel IMMEDIATELY ABOVE existing P0.R3 D5 vision_watchdog cancel at pipeline.py:8341 per §2.6 shutdown wiring.
5. Verify ORDERING INVARIANT: heavy_worker_watchdog → vision_watchdog → vision_task → hw.shutdown_all_pools (existing).

**Phase 6 — Test surface (`tests/test_p0_r8_heavy_worker_watchdog.py` NEW)** (~60 min):

1. Create `tests/test_p0_r8_heavy_worker_watchdog.py`.
2. Implement 9 anchors per §3 LOCK using same shape as `tests/test_p0_r6_z_pyannote_worker.py` precedent.
3. Run 9/9 deliberate-regression confirmations per §2.8 table.
4. Full suite verification — expect 2713 + 9 = 2722 passing post-P0.R8 closure.

**Phase 7 — Closure narrative + audit (~25 min)**:

1. Update `CLAUDE.md` line 3 test count.
2. Bank P0.R8 closure entry with all explicit X → Y narrative lines per Plan v1 §10 item 4.
3. Architect closure-audit Path C grep-verify against production code.

---

## §6 Closure-projection band table + doctrine outcomes

| closure-actual | overage vs mid 9 | band | doctrine outcome |
|---|---|---|---|
| 7 | −22.2% | SLIGHT-DRIFT-DOWN (within ±30%) | `### Phase-0-granular-decomposition` HOLDS at 22 supporting |
| 8 | −11.1% | ON-TARGET | `### Phase-0-granular-decomposition` 22 → 23 supporting |
| 9 | 0% | ON-TARGET exact mid | `### Phase-0-granular-decomposition` 22 → 23 supporting + 2nd consecutive 0%-streak rebuild instance |
| 10 | +11.1% | ON-TARGET | `### Phase-0-granular-decomposition` 22 → 23 supporting |
| 11 | +22.2% | SLIGHT-DRIFT-UP (within ±30%) | `### Phase-0-granular-decomposition` HOLDS at 22 supporting |
| ≥12 OR ≤6 | beyond ±30% | FALSIFICATION TRIGGER | doctrine demotes back to architect-memory + reasoning audit |

---

## §7 Pass-3 grep verification baseline (architect-side at closure-narrative drafting)

3-artifact OPTIONAL-Plan-v2 cycle has 4 grep-verify checkpoints (3 architect-side passes + 1 auditor cross-check):

- Architect Pass-1 grep at Phase 0 baseline ✓
- Auditor Pass-2 grep at Phase 0 verdict ✓ (PI #1 caught — predicate misidentification)
- Architect Pass-2 grep at Plan v1 §1 (this artifact) ✓ (P0.R3 actual patterns at lines 2411 + 8341-8346 verified; PI #1 absorption sound)
- Auditor Pass-2 grep at Plan v1 verdict (standing flag per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval`)
- Architect Pass-3 grep at closure-narrative drafting (catches developer Phase 6 implementation drift if any)

If Pass-3 surfaces enumeration drift, `Plan-v1-Pass-2-grep-undercount` 11 → 12 candidate AT ARCHITECT-SIDE.

---

## §8 Discipline-counter projections (locked +1-per-artifact)

Per locked convention: 3-artifact OPTIONAL-Plan-v2 cycle (Phase 0 + Plan v1 + closure) increments discipline counters by +1 per artifact.

Baseline post-P0.R6.Z closure (2026-05-24):

| Discipline | Baseline | Plan v1 close (this artifact) | P0.R8 closure projection |
|---|---|---|---|
| Strict-industry-standard mode applications | 83 | 85 | 86 |
| Strict-mode successful closures | 24 | 24 | 25 |
| Spec-first review cycle | 92-for-92 | 94-for-94 | 95-for-95 |
| `### Grep-baseline-before-drafting` instances | 50 | 52 | 53 |
| Cross-cycle-handoff transparency successful | 56 | 58 | 59 |
| Spec-time grep-verification instances | 60 | 62 | 63 |
| `### Twin-filename-pitfall-prevention` preventive events | 23 | stays 23 | 24 |
| Auditor-Q5-estimates-trail-grep banked closures | 28 | 28 | 29 |
| Deferred-canary strategy applications | 26 | 26 | 27 |

**OPTIONAL-Plan-v2 path candidacy**: if auditor returns 0 precision items at this Plan v1 review (PI #1 already absorbed cleanly), cycle ships as 3-artifact. **12th OPTIONAL-Plan-v2 proof case candidate post-closure** (P0.S3 + P0.B3 + P0.B5 + P0.B6 + P0.S8 + P0.R2 + P0.R3 + P0.R5 + P0.R6 + P0.R6.X + P0.R6.Z + **P0.R8**). P0.R6.Y was BLOCKED at 5-artifact; P0.R6.Z reclaimed at 11; P0.R8 candidate at 12.

**`### Pre-audit-quantifier-precision-refined-by-grep`**: STAYS at 8 instances per operational rule 3 (Phase 0 grep CONFIRMED pre-audit framing; no refinement event).

---

## §9 Locked Q1-Q9 adjudication (per auditor Phase 0 verdict; Q9 ABSORBED via PI #1)

| Q | Locked | Implementation effect |
|---|---|---|
| Q1 (LOAD-BEARING) | (a) centralized in `run_heavy` | Single chokepoint; preserves 4 callers' None-return fallback contracts intact via re-raise |
| Q2 | (a) module-level dict in `heavy_worker.py` | Co-located with pool registry; PipelineStateStore stays scalar status-only |
| Q3 | (a) rolling time window | Matches P0.R4 systemd `StartLimitIntervalSec` pattern + bounds memory growth |
| Q4 | (a) 5s poll cadence | Mirrors P0.R3 `VISION_WATCHDOG_INTERVAL_SECS` |
| Q5 (LOAD-BEARING) | (a) soft degradation | Pool stays available; auto-respawn STILL works; operator-actionable |
| Q6 | (a) auto re-arm on rolling window | Automatic recovery; no manual reset needed |
| Q7 | (a) add `HealthSnapshot.heavy_worker_crash_counts` field | Dashboard visibility ~1 LOC |
| Q8 | (a) P0.R8 minimal (`(task_name, timestamp)` tuples only); P0.R11 full diagnostics | Preserves cycle scope; P0.R11 has standalone value |
| Q9 | **ABSORBED via PI #1**: bare `while True:` + explicit `.cancel()` + `wait_for(timeout=1.0)` at shutdown (matches P0.R3 actual at pipeline.py:2411 + 8341-8346) | Mirrors P0.R3 actual implementation; predicate misidentification corrected |

---

## §10 Architect-handoff items for auditor verdict

1. **Pass-2 grep verification** (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine): independent re-grep §1.1 8-row + §1.2 5-row + §1.3 shutdown pattern + §1.4 7-row cross-spec table. Confirm PI #1 absorption is clean (no residual `peek_persistent`/`pipeline_running` references in Plan v1 §2.3 or §2.6).

2. **PI #1 absorption verification**: Plan v1 §2.3 D3 uses bare `while True:` (matches P0.R3 actual at pipeline.py:2411). Plan v1 §2.6 shutdown wiring uses explicit `.cancel()` + `wait_for(timeout=1.0)` + `except (CancelledError, TimeoutError, Exception): pass` (mirrors P0.R3 actual at pipeline.py:8341-8346). Q9 re-framed in §9.

3. **Closure-audit Path C grep-verify items** (banked for architect closure-audit at Phase 7):
   - Verify `_HEAVY_WORKER_CRASH_HISTORY` + 3 accessors land in `core/heavy_worker.py`
   - Verify `run_heavy` body has try/except around `loop.run_in_executor` catching `BrokenProcessPool` + calling `_record_pool_crash(task_name)` + bare `raise`
   - Verify `_heavy_worker_watchdog_loop` async function with bare `while True:` body
   - Verify 3 config constants in `core/config.py`
   - Verify `HealthSnapshot.heavy_worker_crash_counts` field
   - Verify `WatchdogAgent.report_heavy_worker_burst` method
   - Verify startup spawn AFTER vision_watchdog spawn
   - Verify shutdown cancel BEFORE vision_watchdog cancel (ORDERING INVARIANT)
   - Verify 9 anchors in `tests/test_p0_r8_heavy_worker_watchdog.py`

4. **Closure-narrative explicit doctrine X → Y lines** (per `Implicit-doctrine-firings-not-narrative-tracked` 5th-cycle self-sustaining adoption):
   - `### Architect-reads-production-code-before-sign-off` 21 → 22 with explicit narrative line (5th-cycle self-sustaining adoption)
   - `### Pre-audit-quantifier-precision-refined-by-grep` STAYS at 8 instances (clean-confirmation per operational rule 3; first negative-evidence validation since elevation)
   - `### Phase-0-catches-wrong-premise` STAYS at 13 (premise correct; Q9 was code-template misidentification not substantive-problem wrong-premise)
   - `### Zero-precision-items-at-auditor-review` 24 → 25 (Plan v1 surface CLEAN if PI #1 absorbed cleanly; Phase 0 was NOT clean per PI #1)
   - `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` validated 9th consecutive cycle — **catching mechanism validated in 2nd validation mode** (5 prior clean + P0.R8 caught-real-gap = both modes proven)
   - `### Phase-0-granular-decomposition-enables-accurate-estimates` 22 → 23 IF closure-actual ∈ [8, 10]
   - `Doctrine-prediction-precision-improving-over-arc` 2nd consecutive 0%-streak rebuild instance IF closure-actual = 9 exact
   - `Plan-v1-Pass-2-grep-undercount` STAYS at 11 if PI #1 absorbed cleanly at Plan v1; 11 → 12 candidate AT AUDITOR-SIDE if absorption surfaces additional drift
   - OPTIONAL-Plan-v2 sub-rule track record 11 → 12 proof cases (if 3-artifact cycle ships)
   - `### Twin-filename-pitfall-prevention` 23 → 24 preventive events at closure
   - Strict-industry-standard mode 83 → 86 + 24 → 25 closures

---

**End of Plan v1.** Ready for auditor verdict.
