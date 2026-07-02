# P0.R9 — Cumulative VRAM budget guard + graceful pool-degradation (Plan v1)

**Date**: 2026-05-25
**Author**: architect (Claude)
**Cycle shape**: SMALL-MEDIUM band, 3-artifact OPTIONAL-Plan-v2 path projected
**Phase 0 verdict**: ACCEPTED with 0 BLOCKING PIs + 1 non-blocking observation (LINE-REF-DRIFT) + carry-forward withdrawn after architect's fresh grep-verify caught auditor's stale-cached verification
**Q1-Q9**: all 9 RATIFIED at Phase 0 verdict
**Anchor count**: 9 RATIFIED at exact mid INCLUSIVE band [7.65, 10.35]

---

## §0 Phase 0 absorption + bidirectional discipline validation

Phase 0 audit ACCEPTED 2026-05-25. Three absorption events fold into Plan v1:

**(1) LINE-REF-DRIFT non-blocking observation absorbed at §1.1 refresh** — auditor's independent Pass-2 grep surfaced architect's §1.1 row 4 cited stale line refs (261, 363) from older P0.R6.* audit docs. Independent re-grep confirms auditor is correct: subprocess singletons at lines 111 / 276 / 358 / 456. Plan v1 §1.1 row 4 refreshed against current production state.

**(2) NEW LINE-REF-DRIFT caught-real-gap sub-shape banking** under `feedback_pass_2_grep_caught_real_gap_subshape.md` — 3rd sub-shape (after ENUMERATION-DRIFT + CODE-TEMPLATE-MISIDENTIFICATION). 1st caught instance. Distinct failure-mode: surfaces EXIST + names are correct + line refs are stale documentation. Different prevention mechanism than the prior 2 sub-shapes (which target count drift + structural shape drift). Cross-path discipline preventive application: extend at BOTH memory paths at P0.R9 closure.

**(3) NEW STALE-CACHED-VERIFICATION caught-real-gap sub-variant banking** under `feedback_auditor_precision_item_misframe.md` — 2nd sub-variant (after SURFACE-MISFRAME). 1st instance: P0.R9 Phase 0 verdict 2026-05-25; auditor's verdict claimed pending CROSS-PATH-SYNC-OMISSION carry-forward from P0.R11 was UNRESOLVED, but architect's fresh Read at verdict-receipt time grep-verified that the P0.R11 closure-audit corrections HAD landed at the auditor-facing path (line 15 + line 16 of auditor-facing MEMORY.md both reflect post-P0.R11 state). Auditor's verification was against session-start cached snapshot, NOT fresh Read at verdict time. Auditor withdrew carry-forward claim. **This is a bidirectional discipline-firing instance**: architect's `### Architect-reads-production-code-before-sign-off` doctrine caught auditor's analog stale-cache error. The discipline's "grep-verify code-shape at named surface" property holds bidirectionally regardless of which actor performs it. Cross-path discipline preventive application: extend at BOTH memory paths at P0.R9 closure.

**Q1-Q9 ratifications applied to §2 D-decisions**: all 9 architect leans RATIFIED at Phase 0 verdict. §2 D-decision specifications LOCKED at architect's lean shapes; D-decision text unchanged from Phase 0.

**Cross-path discipline preventive commitment** (per `feedback_architect_reads_catches_phase_7_memory_file_omission.md` 4th sub-variant CROSS-PATH-SYNC-OMISSION operational rule, locked at P0.R11 closure-audit): P0.R9 closure introduces 2 NEW memory-file edits (LINE-REF-DRIFT + STALE-CACHED-VERIFICATION sub-shape extensions). Architect MUST verify updates land at BOTH the architect-memory path (`C--Users-jagan-dog-ai-dog-ai/memory/`) AND the auditor-facing memory path (`C--Users-jagan-dog-ai/memory/`) at closure. §6 below enumerates the cross-path verification steps explicitly.

---

## §1 Grep findings (Pass-2 — Plan v1 refresh)

### §1.1 Heavy-worker pool spawn surfaces (REFRESHED line refs per Phase 0 LINE-REF-DRIFT absorption)

| # | Surface | File:Line | Current behavior |
|---|---|---|---|
| 1 | `_HEAVY_WORKER_POOLS: dict` | `core/heavy_worker.py:33` | 4 task_name keys after startup: adaface_embed / whisper_transcribe / ecapa_embed / pyannote_diarize |
| 2 | `get_or_create_pool(task_name, max_workers=1)` | `core/heavy_worker.py:128-151` | Always creates ProcessPoolExecutor on first call; **no budget check** |
| 3 | `run_heavy(task_name, fn, ...)` | `core/heavy_worker.py:154-202` | Calls `get_or_create_pool` + dispatches via `loop.run_in_executor(pool, ...)` + P0.R8 D2 BrokenProcessPool catch + P0.R11 forensics + bare `raise` |
| 4 | Subprocess singletons | `core/heavy_worker.py:111 / 276 / 358 / 456` | Lazy-loaded per subprocess; total ~6.3GB cumulative VRAM when all loaded (refreshed line refs: `_SUBPROCESS_EMBEDDER` at 111, `_SUBPROCESS_WHISPER_MODEL` at 276, `_SUBPROCESS_ECAPA_EMBEDDER` at 358, `_SUBPROCESS_PYANNOTE_PIPELINE` at 456) |

**LINE-REF-DRIFT absorption**: refreshed against current production state via independent grep-verify at Plan v1 drafting time. Auditor's Pass-2 grep at Plan v1 review will independently confirm.

### §1.2-§1.5 unchanged from Phase 0 audit

§1.2 (pool VRAM cost estimates) + §1.3 (disk monitor threshold-crossing pattern precedent) + §1.4 (CUDA-availability check sites) + §1.5 (P0.R1 D1 None-return fallback contracts) all stay as locked in Phase 0 audit; auditor's Phase 0 Pass-2 grep confirmed these tables convergent.

### §1.6 Cross-spec interactions (unchanged from Phase 0)

All 9 cross-spec rows confirmed convergent at auditor Phase 0 Pass-2 grep.

### §1.7 NEW — Current `get_or_create_pool` signature + `run_heavy` body (verified at Plan v1 drafting)

**`get_or_create_pool` current shape (`core/heavy_worker.py:128-151`):**

```python
def get_or_create_pool(
    task_name: str, max_workers: int = 1
) -> concurrent.futures.ProcessPoolExecutor:
    """..."""
    if task_name in _HEAVY_WORKER_POOLS:
        return _HEAVY_WORKER_POOLS[task_name]
    ctx = mp.get_context("spawn")
    pool = concurrent.futures.ProcessPoolExecutor(
        max_workers=max_workers,
        mp_context=ctx,
        initializer=_adaface_worker_init if task_name == "adaface_embed" else None,
    )
    _HEAVY_WORKER_POOLS[task_name] = pool
    return pool
```

**`run_heavy` current shape (`core/heavy_worker.py:154-202`):**

```python
async def run_heavy(
    task_name: str, fn: Callable, *args: Any, **kwargs: Any
) -> Any:
    """..."""
    pool = get_or_create_pool(task_name)
    loop = asyncio.get_running_loop()
    bound = functools.partial(fn, *args, **kwargs)
    try:
        return await loop.run_in_executor(pool, bound)
    except concurrent.futures.process.BrokenProcessPool as e:
        _record_pool_crash(task_name)
        try:
            from core.crash_logs import persist_crash_diagnostic
            crash_count = len(_HEAVY_WORKER_CRASH_HISTORY.get(task_name, []))
            persist_crash_diagnostic(task_name, e, traceback.format_exc(), crash_count)
        except Exception:  # OPTIONAL: P0.R11 import/call failure
            pass
        raise  # bare — preserves traceback + caller fallback
```

**Phase 1 mutation surface confirmed**: D3 (`get_or_create_pool` extension) inserts budget check + None-return BEFORE `mp.get_context("spawn")` call. D4 (`run_heavy` None-pool handling) inserts None-pool check BEFORE `loop.run_in_executor`. Both line ranges grep-verified at Plan v1 drafting.

---

## §2 D-decisions LOCKED (per Q1-Q9 ratifications)

### D1 — Config constants (Q1 + Q2 + Q5 RATIFIED)

`core/config.py` near HEAVY_WORKER constants, after P0.R8 constants:

```python
# P0.R9 — heavy-worker pool VRAM budget guard. Static estimates per pool;
# cumulative cap at VRAM_CEILING_PCT of available CUDA memory; pool priority
# determines which pools refuse spawn on budget exhaustion. Tune estimates +
# ceiling + priority order based on production canary signal; restart to
# re-evaluate. Q5 (a) RATIFIED: skip enforcement on non-CUDA (CI / dev laptop
# without GPU); see core/heavy_worker.py::check_vram_budget for skip logic.
HEAVY_WORKER_VRAM_ESTIMATES_MB = {
    "adaface_embed":      100,
    "ecapa_embed":        200,
    "whisper_transcribe": 3000,
    "pyannote_diarize":   3000,
}
VRAM_CEILING_PCT = 80.0  # cap at 80% of available CUDA memory
VRAM_POOL_PRIORITY = [
    "adaface_embed",      # highest priority — face recognition is core
    "ecapa_embed",        # voice ID for greeting
    "whisper_transcribe", # STT (could degrade to other STT)
    "pyannote_diarize",   # lowest — has ECAPA-valley fallback
]
```

### D2 — `check_vram_budget` helper + `_REFUSED_POOLS` set + `peek_refused_pools` accessor (Q4 + Q5 + Q6 + Q7 RATIFIED)

`core/heavy_worker.py` near `_HEAVY_WORKER_POOLS` declaration (after line 33):

```python
# P0.R9 — VRAM budget guard module state.
_REFUSED_POOLS: "set[str]" = set()
_VRAM_CHECK_LOCK = threading.Lock()


def check_vram_budget(task_name: str) -> bool:
    """Return True if `task_name` can spawn within VRAM budget; False if refused.

    Q5 (a) RATIFIED: skip enforcement on non-CUDA (torch.cuda.is_available()
    False); returns True so non-CUDA dev/CI environments proceed as today.

    Q4 (a) RATIFIED: refused pools cached in _REFUSED_POOLS module set;
    subsequent calls return False without re-computing.

    Q6 (a) RATIFIED: first-call lazy check (called from get_or_create_pool
    BEFORE pool creation; matches existing pool warm-up ordering).

    Q7 (a) RATIFIED: torch.cuda.mem_get_info() — no subprocess overhead.

    Computes cumulative VRAM = sum(ESTIMATES_MB[p] for p in _HEAVY_WORKER_POOLS) +
    ESTIMATES_MB[task_name]; compares to (available_cuda_mb * VRAM_CEILING_PCT / 100).
    """
    with _VRAM_CHECK_LOCK:
        if task_name in _REFUSED_POOLS:
            return False
        try:
            import torch  # noqa: PLC0415
            if not torch.cuda.is_available():
                return True  # Q5 (a) — skip on non-CUDA
            free_mb, total_mb = (
                b // (1024 * 1024) for b in torch.cuda.mem_get_info()
            )
        except Exception:  # OPTIONAL: torch import / CUDA probe failure → skip
            return True
        from core.config import (  # noqa: PLC0415
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

### D3 — `get_or_create_pool` extension (Q3 LOCK + Q8 RATIFIED)

`core/heavy_worker.py:128-151` — extend with budget check BEFORE pool creation:

```python
def get_or_create_pool(
    task_name: str, max_workers: int = 1
) -> "concurrent.futures.ProcessPoolExecutor | None":
    """Get-or-create singleton ProcessPoolExecutor per task_name.

    P0.R9 D3 RATIFIED Q3 (a): budget check BEFORE pool creation. If
    check_vram_budget returns False (cumulative would exceed VRAM_CEILING_PCT),
    return None and dispatch WatchdogAgent.report_vram_budget_refusal alert
    per Q8 (a) RATIFIED (per-pool alert granularity). The None return
    propagates through run_heavy (D4) to caller's existing P0.R1 D1
    None-return fallback contract uniformly.

    Foundation cycle (P0.R6 Plan v1 §2.1 Q4 (a) lock): max_workers=1 per task.
    mp.get_context("spawn") explicit (P0.R6 Q6 (a) lock) for cross-platform.
    """
    if task_name in _HEAVY_WORKER_POOLS:
        return _HEAVY_WORKER_POOLS[task_name]
    # P0.R9 D3 — VRAM budget check (Q3 (a) RATIFIED)
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

**Return type annotation update LOAD-BEARING**: `-> concurrent.futures.ProcessPoolExecutor` → `-> "concurrent.futures.ProcessPoolExecutor | None"` (Q3 (a) lock).

### D4 — `run_heavy` None-pool handling (Q3 LOAD-BEARING + D3 interaction)

`core/heavy_worker.py:154-202` — extend with None-pool check BEFORE `loop.run_in_executor`:

```python
async def run_heavy(
    task_name: str, fn: Callable, *args: Any, **kwargs: Any
) -> Any:
    """... P0.R9 D4 RATIFIED Q3 (a): if get_or_create_pool returns None (VRAM
    budget refusal), return None immediately (preserves caller's P0.R1 D1
    None-return fallback contract; skips the run_in_executor dispatch). The
    None propagates through `await hw.run_heavy(...)` to caller's existing
    None-handling path (AdaFace recognize-miss / Whisper empty-STT /
    ECAPA identify-miss / Pyannote ECAPA-valley fallback).

    P0.R8 D2 (2026-05-25): BrokenProcessPool catch + bare raise (unchanged).
    P0.R11 D2 (2026-05-25): forensic capture (unchanged).
    """
    pool = get_or_create_pool(task_name)
    if pool is None:
        return None  # P0.R9 D4 — preserve P0.R1 D1 fallback contract
    loop = asyncio.get_running_loop()
    bound = functools.partial(fn, *args, **kwargs)
    try:
        return await loop.run_in_executor(pool, bound)
    except concurrent.futures.process.BrokenProcessPool as e:
        # P0.R8 D2 + P0.R11 D2 — unchanged
        _record_pool_crash(task_name)
        try:
            from core.crash_logs import persist_crash_diagnostic
            crash_count = len(_HEAVY_WORKER_CRASH_HISTORY.get(task_name, []))
            persist_crash_diagnostic(
                task_name, e, traceback.format_exc(), crash_count
            )
        except Exception:  # OPTIONAL: P0.R11 import/call failure
            pass
        raise  # bare — preserves traceback + caller fallback
```

### D5 — `WatchdogAgent.report_vram_budget_refusal` method (Q8 RATIFIED)

`core/brain_agent.py` `WatchdogAgent` class after `report_heavy_worker_burst`:

```python
def report_vram_budget_refusal(
    self,
    task_name: str,
    cumulative_mb: int,
    ceiling_mb: int,
    estimate_mb: int,
) -> None:
    """Store a VRAM budget refusal alert. Severity: warning (graceful
    degradation — caller's fallback fires; system continues running). Called
    from core.heavy_worker.get_or_create_pool on first refusal per task_name.

    Q8 (a) RATIFIED: per-pool alert granularity (operator wants to know WHICH
    pool degraded). Alert metadata captures pool name + cumulative MB +
    ceiling MB + estimate MB for operator triage.
    """
    self._db.store_alert(
        f"vram_budget_refusal_{task_name}",
        "warning",
        f"Pool '{task_name}' refused spawn (estimate {estimate_mb}MB + "
        f"cumulative {cumulative_mb}MB > ceiling {ceiling_mb}MB). "
        f"Fallback path active. Tune VRAM_POOL_PRIORITY / VRAM_CEILING_PCT / "
        f"HEAVY_WORKER_VRAM_ESTIMATES_MB at core/config.py + restart to recover.",
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

Plus `BrainOrchestrator.report_vram_budget_refusal` passthrough mirroring `report_heavy_worker_burst` shape.

### D6 — `HealthSnapshot.vram_budget` field + format extensions

`core/health.py` — `HealthSnapshot` dataclass extension:

```python
# P0.R9 — VRAM budget observability
vram_budget: "dict[str, list[str]]" = field(default_factory=dict)
```

`gather_health_snapshot` addition (after existing heavy_worker observability):

```python
# P0.R9 — VRAM budget observability
try:
    import core.heavy_worker as hw  # noqa: PLC0415
    vram_budget = {
        "refused_pools": sorted(hw.peek_refused_pools()),
        "active_pools": sorted(hw._HEAVY_WORKER_POOLS.keys()),
    }
except Exception:  # OPTIONAL: import/probe failure → empty
    vram_budget = {}
```

`format_health_line` conditional emit:

```python
if snapshot.vram_budget.get("refused_pools"):
    parts.append(f"vram_refused={len(snapshot.vram_budget['refused_pools'])}")
```

`format_health_alerts` actionable alert with verbatim substrings:

```python
if snapshot.vram_budget.get("refused_pools"):
    alerts.append(
        f"VRAM budget refusal — pools refused: "
        f"{', '.join(snapshot.vram_budget['refused_pools'])}. "
        f"Caller fallback active. Tune VRAM_POOL_PRIORITY / VRAM_CEILING_PCT / "
        f"HEAVY_WORKER_VRAM_ESTIMATES_MB at core/config.py + restart to recover."
    )
```

Verbatim alert substrings (anchored by A8):
- `"VRAM budget refusal"`
- `"pools refused:"`
- `"VRAM_POOL_PRIORITY"`
- `"VRAM_CEILING_PCT"`
- `"HEAVY_WORKER_VRAM_ESTIMATES_MB"`

---

## §3 Anchor enumeration (Q5 LOCKED = 9 anchors)

NEW `tests/test_p0_r9_vram_budget_guard.py` with 9 anchors:

| # | Anchor name | Surface | Behavioral / Source |
|---|---|---|---|
| A1 | `test_p0_r9_d1_config_constants_present` | `core/config.py` | Source — verify `HEAVY_WORKER_VRAM_ESTIMATES_MB` dict has 4 pool keys + `VRAM_CEILING_PCT == 80.0` + `VRAM_POOL_PRIORITY` is 4-item list with all 4 pool names |
| A2 | `test_p0_r9_d2_check_vram_budget_helper_exists` | `core/heavy_worker.py` | Source — AST scan for `check_vram_budget` + `peek_refused_pools` + `_REFUSED_POOLS` + `_VRAM_CHECK_LOCK` module-level definitions |
| A3 | `test_p0_r9_d3_get_or_create_pool_returns_none_when_budget_exceeded` | `core/heavy_worker.py` + monkeypatched torch | **BEHAVIORAL** — monkeypatch `torch.cuda.is_available` to True + `torch.cuda.mem_get_info` to return tiny total (e.g. 100MB) → call `get_or_create_pool("whisper_transcribe")` → assert returns None + WatchdogAgent.store_alert called with `vram_budget_refusal_whisper_transcribe` |
| A4 | `test_p0_r9_d3_high_priority_pool_spawns_when_low_priority_refused` | `core/heavy_worker.py` + monkeypatched torch | **BEHAVIORAL** — monkeypatch ceiling so AdaFace fits but Whisper doesn't → `get_or_create_pool("adaface_embed")` returns real pool + `get_or_create_pool("whisper_transcribe")` returns None |
| A5 | `test_p0_r9_d4_run_heavy_returns_none_when_pool_none` | `core/heavy_worker.py` + monkeypatched | **BEHAVIORAL** — monkeypatch `get_or_create_pool` to return None → `await run_heavy("test_task", lambda: 1)` returns None (NOT AttributeError) |
| A6 | `test_p0_r9_d2_refused_pools_cached` | `core/heavy_worker.py` + monkeypatched torch | **BEHAVIORAL** — first `check_vram_budget("whisper_transcribe")` returns False + adds to `_REFUSED_POOLS`; second call returns False from cache (verify via `_REFUSED_POOLS.__contains__` count or mocked `torch.cuda.mem_get_info` call count = 1) |
| A7 | `test_p0_r9_d5_watchdog_report_vram_budget_refusal` | `core/brain_agent.py` | Source + behavioral — verify `WatchdogAgent.report_vram_budget_refusal` method exists + calls `store_alert` with `vram_budget_refusal_{task_name}` key |
| A8 | `test_p0_r9_d6_health_snapshot_vram_budget_field_and_alerts` | `core/health.py` | Source + behavioral — verify `HealthSnapshot.vram_budget` field exists + `format_health_line` emits `vram_refused=N` conditionally + `format_health_alerts` emits 5 verbatim substrings when refused_pools non-empty |
| A9 | `test_p0_r9_non_cuda_skip_budget_enforcement` | `core/heavy_worker.py` + monkeypatched torch | **BEHAVIORAL** — monkeypatch `torch.cuda.is_available` to return False → `check_vram_budget("whisper_transcribe")` returns True (skip enforcement) without calling `torch.cuda.mem_get_info` |

---

## §4 Phase 4 deliberate-regression confirmation matrix

9 reverts (one per anchor) per `### Induction-surfaces-invariant-gaps` discipline:

| # | Revert action | Expected anchor failure |
|---|---|---|
| (a) | Delete `HEAVY_WORKER_VRAM_ESTIMATES_MB` from `core/config.py` | A1 fires (config constants missing) |
| (b) | Replace `check_vram_budget` body with `return True` unconditionally | A3 fires (returns real pool when should return None) + A4 fires (no refusal) |
| (c) | Drop `_REFUSED_POOLS.add(task_name)` from `check_vram_budget` body | A6 fires (refusal not cached; second call re-computes) |
| (d) | Drop None-pool check from `run_heavy` (`if pool is None: return None`) | A5 fires (AttributeError on `pool.submit` when pool is None) |
| (e) | Remove `WatchdogAgent.report_vram_budget_refusal` method | A7 fires (method missing) |
| (f) | Remove `vram_budget` field from `HealthSnapshot` | A8 fires (field missing) |
| (g) | Remove `if not torch.cuda.is_available(): return True` skip from `check_vram_budget` | A9 fires (non-CUDA env hits the mem_get_info call and either errors or applies enforcement) |
| (h) | Reorder `VRAM_POOL_PRIORITY` so `pyannote_diarize` is first | A1 still passes (constants present + 4-item list) BUT semantic test on order — verify `VRAM_POOL_PRIORITY[0] == "adaface_embed"` |
| (i) | Drop budget-check call from `get_or_create_pool` (skip directly to ProcessPoolExecutor construction) | A3 fires (pool created instead of None returned) |

All 9 reverts MUST fire correctly + revert cleanly + suite green before closure narrative drafting.

---

## §5 Phase 5 implementation enumeration (explicit mutation steps per P0.R11 Observation 1 absorption pattern)

Per auditor's recommendation #4 at Phase 0 verdict + per P0.R11 Observation 1 absorption pattern (explicit mutation enumeration defends against missing-step silent-masking shape):

**Step 1 — `core/config.py` D1 constants (additive, no breakage)**:

- Step 1.1: Add `HEAVY_WORKER_VRAM_ESTIMATES_MB` dict (4 entries) after `HEAVY_WORKER_RESTART_BURST_WINDOW_SECS` constant
- Step 1.2: Add `VRAM_CEILING_PCT = 80.0` after `HEAVY_WORKER_VRAM_ESTIMATES_MB`
- Step 1.3: Add `VRAM_POOL_PRIORITY` list (4 entries in priority order) after `VRAM_CEILING_PCT`

**Step 2 — `core/heavy_worker.py` D2 + D3 + D4 (load-bearing mutations)**:

- Step 2.1: Add module-level `_REFUSED_POOLS: "set[str]" = set()` + `_VRAM_CHECK_LOCK = threading.Lock()` immediately after `_HEAVY_WORKER_POOLS` declaration (line 33)
- Step 2.2: Add `check_vram_budget(task_name) -> bool` function body + `peek_refused_pools() -> set[str]` accessor body. Place AFTER `_HEAVY_WORKER_POOLS` block + BEFORE `get_or_create_pool` (so D3 can reference)
- Step 2.3: Modify `get_or_create_pool` return type annotation: `-> concurrent.futures.ProcessPoolExecutor` → `-> "concurrent.futures.ProcessPoolExecutor | None"` (LOAD-BEARING — Q3 (a) lock)
- Step 2.4: Insert budget check + None return + WARN log + WatchdogAgent dispatch INSIDE `get_or_create_pool` body BEFORE `ctx = mp.get_context("spawn")` line
- Step 2.5: Insert `if pool is None: return None` INSIDE `run_heavy` body BEFORE `loop = asyncio.get_running_loop()` line

**Step 3 — `core/brain_agent.py` D5 (additive)**:

- Step 3.1: Add `WatchdogAgent.report_vram_budget_refusal(task_name, cumulative_mb, ceiling_mb, estimate_mb)` method after existing `report_heavy_worker_burst` method
- Step 3.2: Add `BrainOrchestrator.report_vram_budget_refusal` passthrough mirroring `report_heavy_worker_burst` shape

**Step 4 — `core/health.py` D6 (additive)**:

- Step 4.1: Add `vram_budget: "dict[str, list[str]]" = field(default_factory=dict)` field to `HealthSnapshot` dataclass
- Step 4.2: Add `vram_budget` dict population block in `gather_health_snapshot` (calls `hw.peek_refused_pools()` defensively via try/except)
- Step 4.3: Add `format_health_line` conditional emit `vram_refused=N` when refused_pools non-empty
- Step 4.4: Add `format_health_alerts` actionable alert with 5 verbatim substrings when refused_pools non-empty

**Step 5 — `tests/test_p0_r9_vram_budget_guard.py` NEW (9 anchors per §3)**:

- Step 5.1: Create file with A1-A9 test functions per §3 anchor enumeration
- Step 5.2: A3 + A4 + A5 + A6 + A9 require `torch.cuda.is_available` + `torch.cuda.mem_get_info` monkeypatching; use a shared `_mock_cuda_with_total_mb(monkeypatch, total_mb)` helper inside the test module
- Step 5.3: A5 (run_heavy None-pool) requires async test fixture (`@pytest.mark.asyncio`); pattern matches existing P0.R8 + P0.R11 async tests

**Step 6 — Phase 4 verify-on-revert pass (per §4 matrix)**:

- Step 6.1: Apply each of 9 reverts (a-i) in sequence via temporary Edit
- Step 6.2: After each revert, run the corresponding anchor test in isolation; verify it fires correctly
- Step 6.3: Revert the revert; verify suite green at end of each revert cycle
- Step 6.4: Bank reverts (a-i) in closure narrative `### Induction-surfaces-invariant-gaps` X → X+1 instance

**Step 7 — Closure narrative drafting** (post-implementation):

- Step 7.1: Draft `tests/p0_r9_vram_budget_guard_closure.md` with §5-style step enumeration
- Step 7.2: §6 cross-path memory-file updates per §6 below
- Step 7.3: Doctrine firings per §8 of Phase 0 audit (updated to current counts)
- Step 7.4: 4-criteria architect closure-audit verification (instance enumeration ✓ / discipline-stability ✓ / cross-reference integrity ✓ / falsification clause integrity ✓)
- Step 7.5: Deferred-canary entry to `to_be_checked.md`

**Mutation-step independence verification**: Steps 1-4 are independent and can land in any order. Step 5 must land last (depends on all prior implementation steps). Step 6 depends on Step 5. Step 7 depends on Step 6.

---

## §6 SCHEDULED memory-file work at closure (cross-path discipline preventive application)

Per `feedback_architect_reads_catches_phase_7_memory_file_omission.md` 4th sub-variant CROSS-PATH-SYNC-OMISSION operational rule (locked at P0.R11 closure-audit): when closure introduces memory-file edits, architect MUST verify updates at BOTH the architect-memory path (`C--Users-jagan-dog-ai-dog-ai/memory/`) AND the auditor-facing memory path (`C--Users-jagan-dog-ai/memory/`).

P0.R9 closure introduces **2 memory-file extensions**:

### §6.1 LINE-REF-DRIFT sub-shape extension (Phase 0 absorption #2)

**File**: `feedback_pass_2_grep_caught_real_gap_subshape.md`
**Action**: Extend with 3rd sub-shape LINE-REF-DRIFT (after ENUMERATION-DRIFT + CODE-TEMPLATE-MISIDENTIFICATION). 1st caught instance.

**Cross-path verification at closure** (CRITICAL — failure to honor is CROSS-PATH-SYNC-OMISSION 5th instance):

- Step 6.1.a: Update at architect-memory path: `C:\Users\jagan\.claude\projects\C--Users-jagan-dog-ai-dog-ai\memory\feedback_pass_2_grep_caught_real_gap_subshape.md`
- Step 6.1.b: Update at auditor-facing path: `C:\Users\jagan\.claude\projects\C--Users-jagan-dog-ai\memory\feedback_pass_2_grep_caught_real_gap_subshape.md`
- Step 6.1.c: Update MEMORY.md index entry at BOTH paths (reflect 3rd sub-shape: LINE-REF-DRIFT added at P0.R9 Phase 0 verdict 2026-05-25)
- Step 6.1.d: Verify both paths landed via fresh Read at closure-audit time

**Sub-shape body to add**:

```markdown
3. **LINE-REF-DRIFT** (NEW sub-shape, 1st instance P0.R9 Phase 0 verdict 2026-05-25) — architect's
   Pass-2 grep cites stale LINE REFS for named surfaces. The drift is DOCUMENTATION-CURRENCY —
   surfaces EXIST + names are correct + line numbers are stale (reused from older audit docs
   without re-verification against current production state). Canonical instance: P0.R9 Phase 0
   §1.1 row 4 cited `_SUBPROCESS_WHISPER_MODEL at 261` + `_SUBPROCESS_ECAPA_EMBEDDER at 363`;
   auditor's independent Pass-2 grep at Plan v1 verdict-time surfaced actual line refs 276 +
   358 (drift of +15 / -5). Names + surfaces correct; line numbers stale (architect's audit
   doc reused refs from older P0.R6.X / P0.R6.Y audit docs).

**Why this matters:**

LINE-REF-DRIFT has a distinct prevention mechanism from ENUMERATION-DRIFT + CODE-TEMPLATE-MISIDENTIFICATION:
- **LINE-REF-DRIFT prevention**: at Pass-2 grep, re-verify line refs against CURRENT production
  state via fresh Grep tool invocation; do NOT rely on cached refs from prior audit documents.
  Documentation-currency check at Plan v1 §1.* refresh step.
- **ENUMERATION-DRIFT prevention** (existing): programmatic enumeration enforcement at test surface.
- **CODE-TEMPLATE-MISIDENTIFICATION prevention** (existing): byte-for-byte canonical reference
  verification + AST-anchor enforcement.

**Validation modes**: 1st caught instance at P0.R9 Phase 0 verdict — auditor's independent
Pass-2 grep at Plan v1-prep surface caught architect's stale line refs. Distinct from prior
sub-shapes' caught/preventive validation modes (LINE-REF-DRIFT can only be caught — there is
no "preventive grep-verify of line refs" semantic because architect's preventive verification
WOULD itself be the prevention; the caught-mode IS the absence of architect-side preventive
re-verification).

**Watch criteria**: 3+ caught instances may extend sub-shape elevation candidacy.
```

### §6.2 STALE-CACHED-VERIFICATION sub-variant extension (Phase 0 absorption #3)

**File**: `feedback_auditor_precision_item_misframe.md`
**Action**: Extend with sub-variant taxonomy. 1st sub-variant retroactively named SURFACE-MISFRAME (existing 2 instances: P0.S7.5.1 + P0.S2); 2nd sub-variant NEW STALE-CACHED-VERIFICATION (1st instance: P0.R9 Phase 0 verdict 2026-05-25).

**Cross-path verification at closure**:

- Step 6.2.a: Update at architect-memory path
- Step 6.2.b: Update at auditor-facing path
- Step 6.2.c: Update MEMORY.md index entry at BOTH paths (reflect 2-sub-variant taxonomy + 3rd total instance)
- Step 6.2.d: Verify both paths landed via fresh Read at closure-audit time

**Sub-variant taxonomy to add (extends existing instance enumeration)**:

```markdown
**Sub-variant taxonomy (banked at P0.R9 Phase 0 verdict 2026-05-25):**

The parent doctrine's caught-real-gap instances have multiple sub-variants:

**Sub-variant A — SURFACE-MISFRAME** (existing 2 instances):
- Auditor surfaces a precision item that names a specific code surface that doesn't exist
  in current code (or names a hypothetical pattern shape rather than current shape).
- 1st instance: P0.S7.5.1 Plan v1 — MEDIUM 1 misframe (`re.escape(old_name)` on pattern
  that doesn't interpolate `old_name`).
- 2nd instance: P0.S2 Plan v1 — Q5-C misframe (function-scope import behavioral framing
  that doesn't match production semantic).

**Sub-variant B — STALE-CACHED-VERIFICATION** (NEW, 1st instance P0.R9 Phase 0 verdict
2026-05-25):
- Auditor performs grep-verification at verdict time, but against a stale cached snapshot
  of a mutable file (e.g., session-start auto-memory cache) rather than fresh Read at
  verdict-receipt time.
- Distinct from SURFACE-MISFRAME — the auditor's claim is internally consistent against
  the cached state; the gap is between cached state and current state of a mutable file.
- 1st instance: P0.R9 Phase 0 verdict — auditor claimed cross-path corrections from
  P0.R11 closure-audit were "STILL PENDING" at auditor-facing MEMORY.md; architect's
  fresh Read at verdict-receipt time grep-verified the corrections HAD landed (line 15
  + line 16 both reflect post-P0.R11 state). Auditor's verification was against
  session-start cached snapshot, not fresh Read.

**Prevention mechanism**: at every verdict that depends on mutable file state, perform
FRESH Read at verdict time. Never rely on session-start auto-memory cache for active
files. Same shape as the parent doctrine's "grep-verify code-shape at named surface
BEFORE the verdict goes out" framing — extended to "fresh Read for mutable file state
BEFORE the verdict goes out".

**Bidirectional discipline-firing**: STALE-CACHED-VERIFICATION sub-variant's 1st instance
was caught by ARCHITECT's `### Architect-reads-production-code-before-sign-off` doctrine
firing against AUDITOR's verdict. The discipline's "grep-verify code-shape at named
surface" property holds bidirectionally — works regardless of which actor performs the
verification. This is meaningful cross-actor symmetry evidence; bank as 1st
bidirectional-validation instance of the cross-actor grep-verify discipline family.

**Watch criteria**: 3+ STALE-CACHED-VERIFICATION instances may elevate to operational
rule under parent doctrine; 3+ bidirectional-validation instances (architect catching
auditor + auditor catching architect) may elevate the cross-actor symmetry framing to
its own sub-rule.
```

### §6.3 MEMORY.md index updates at BOTH paths

Both MEMORY.md files need index-entry refreshes reflecting the extensions:

- `feedback_pass_2_grep_caught_real_gap_subshape.md` — entry expanded to mention LINE-REF-DRIFT as 3rd sub-shape
- `feedback_auditor_precision_item_misframe.md` — entry expanded to mention sub-variant taxonomy (SURFACE-MISFRAME + STALE-CACHED-VERIFICATION)

**Closure-audit cross-path verification protocol** (per locked operational rule):

1. Apply all 4 file edits (2 memory files × 2 paths)
2. Apply MEMORY.md index updates at BOTH paths
3. Fresh Read both MEMORY.md files post-edit; verify entries land
4. Fresh Read both memory files post-edit; verify sub-shape/sub-variant bodies land
5. Bank cross-path discipline 2nd preventive-application instance under
   `feedback_architect_reads_catches_phase_7_memory_file_omission.md` (1st preventive
   was at P0.R9 Phase 0 §0 commitment; 2nd preventive is at P0.R9 closure successful
   application)

---

## §7 Closure-projection band table (Q5 LOCKED at 9)

| closure-actual | overage vs mid 9 | band | doctrine outcome |
|---|---|---|---|
| 7 | −22.2% | SLIGHT-DRIFT-DOWN | `### Phase-0-granular-decomposition` HOLDS at 24 |
| 8 | −11.1% | ON-TARGET | 24 → 25 supporting |
| 9 | 0% | ON-TARGET exact mid | 24 → 25 supporting + **4th consecutive 0%-streak rebuild instance** (P0.R6.Z + P0.R8 + P0.R11 + P0.R9; **5+ watch criteria approaching** — sub-observation extension candidacy at next 0%-streak instance if P0.R10 also exact-mid) |
| 10 | +11.1% | ON-TARGET | 24 → 25 supporting |
| 11 | +22.2% | SLIGHT-DRIFT-UP | HOLDS at 24 |
| ≥12 OR ≤6 | beyond ±30% | FALSIFICATION TRIGGER | demotes back to architect-memory |

**Architect closure-actual projection (Plan v1 §7 honest-count commitment)**: 9 anchors at exact mid (per Q5 RATIFIED at Phase 0 verdict).

---

## §8 Doctrine-firing projections at closure (updated to current counts)

If P0.R9 closes cleanly with closure-actual = 9 anchors at exact mid:

- `### Phase-0-granular-decomposition-enables-accurate-estimates` 24 → 25 supporting
- `Doctrine-prediction-precision-improving-over-arc` **4th consecutive 0%-streak rebuild instance** (P0.R6.Z + P0.R8 + P0.R11 + P0.R9; 5+ watch criteria approaching → sub-observation extension at 5th instance)
- `### Pre-audit-quantifier-precision-refined-by-grep` STAYS at 8 instances (3rd consecutive clean-confirmation per operational rule 3 — sustained empirical validation of negative-evidence semantic; LINE-REF-DRIFT non-blocking observation is documentation-currency, NOT quantifier-refinement)
- `### Phase-0-catches-wrong-premise` STAYS at 13 (premise correct)
- `### Zero-precision-items-at-auditor-review` 27 → 29 (Phase 0 + Plan v1 if cycle clears cleanly with 0 BLOCKING PIs at both surfaces)
- `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` 12 → 13 consecutive cycle (clean-pass mode)
- OPTIONAL-Plan-v2 sub-rule track record 13 → 14 proof cases (if 3-artifact cycle ships)
- `### Architect-reads-production-code-before-sign-off` 23 → 24 at closure-audit (7th-cycle self-sustaining adoption — bidirectional grep-verify validation pattern banked)
- Strict-industry-standard mode 89 → 92 applications + 26 → 27 closures
- Spec-first review cycle 98 → 101-for-101 at closure
- `### Grep-baseline-before-drafting` 56 → 59 instances
- Cross-cycle-handoff transparency 59 → 62 successful
- Spec-time grep-verification 66 → 69 instances
- `### Twin-filename-pitfall-prevention` 25 → 26 preventive events
- Auditor-Q5-estimates-trail-grep 30 → 31 banked closures
- Deferred-canary strategy 28 → 29 applications

**Sub-shape banking events** (locked per Phase 0 absorptions):

- `feedback_pass_2_grep_caught_real_gap_subshape.md`: 3rd sub-shape LINE-REF-DRIFT banked at P0.R9 Phase 0 verdict 2026-05-25; 1st caught instance. Sub-shape track record grows from 2-sub-shape × (1 caught + 1 preventive) to 3-sub-shape × (1 caught LINE-REF-DRIFT + 1 caught/2 preventive CODE-TEMPLATE + 1 caught ENUMERATION-DRIFT).
- `feedback_auditor_precision_item_misframe.md`: sub-variant taxonomy formalized at P0.R9 Phase 0 verdict 2026-05-25; SURFACE-MISFRAME named retroactively (2 existing instances P0.S7.5.1 + P0.S2); STALE-CACHED-VERIFICATION NEW (1st instance P0.R9 Phase 0 verdict).
- CODE-TEMPLATE-MISIDENTIFICATION sub-shape: 2nd preventive-application instance (P0.R8 caught + P0.R11 preventive + P0.R9 preventive = 1 caught + 2 preventive).
- CROSS-PATH-SYNC-OMISSION sub-variant: 1st preventive-application at Phase 0 §0 commitment + 2nd preventive-application at closure successful cross-path verification (if §6 protocol honored).
- MEMORY-FILE INDEX GAP family: 4 instances banked at P0.R11 closure-audit; sub-rule elevation candidacy WARRANTED. P0.R9 cycle: NO new instances (cross-path preventive discipline applied successfully = no MISSING-INDEX-ENTRY / MISSING-FILE / INDEX-CONTENT-STALE / CROSS-PATH-SYNC-OMISSION sub-variant firings). Track-record stays at 4 if §6 closure protocol honored cleanly.
- NEW bidirectional-validation pattern (architect catches auditor + auditor catches architect): 1st instance P0.R9 Phase 0 verdict. Watch criteria 3+ for sub-rule elevation under cross-actor grep-verify discipline family.

---

## §9 Architect-handoff items for auditor Plan v1 verdict

1. **Pass-2 grep verification** (per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine — 12th consecutive cycle at this Plan v1 surface):

   - §1.1 row 4 line refs REFRESHED at Plan v1 drafting per Phase 0 LINE-REF-DRIFT absorption (verified 111 / 276 / 358 / 456 at current production state). Auditor's independent Pass-2 grep should confirm.
   - §1.2-§1.5 + §1.6 unchanged from Phase 0 (auditor already confirmed convergent at Phase 0 verdict).
   - §1.7 NEW sub-table: `get_or_create_pool` current shape (heavy_worker.py:128-151) + `run_heavy` current shape (heavy_worker.py:154-202) at Plan v1 drafting; auditor's Pass-2 grep should confirm signatures match production.
   - CODE-TEMPLATE-MISIDENTIFICATION sub-shape risk-check: §2 D-decision code templates reference `_HEAVY_WORKER_POOLS` + `torch.cuda.is_available()` + `torch.cuda.mem_get_info()` (all grep-verified at Phase 0); `_HEAVY_WORKER_CRASH_HISTORY` reference in `run_heavy` D4 unchanged from P0.R8 + P0.R11 surfaces. All references grep-verifiable.

2. **Anchor count adjudication**: 9 anchors LOCKED at Q5 mid INCLUSIVE band [7.65, 10.35]; A1-A9 enumeration per §3 with 4 source-inspection (A1 + A2 + A7 + A8) + 5 behavioral (A3 + A4 + A5 + A6 + A9). Architect closure-projection: exact mid 9.

3. **Phase 0 absorption verification**:

   - **LINE-REF-DRIFT absorption at §1.1 row 4**: line refs refreshed 111 / 276 / 358 / 456 (auditor's Phase 0 verdict line refs).
   - **NEW LINE-REF-DRIFT sub-shape banking at §6.1**: closure protocol enumerated for both memory paths.
   - **NEW STALE-CACHED-VERIFICATION sub-variant banking at §6.2**: closure protocol enumerated for both memory paths.
   - **Implementation enumeration at §5**: explicit 5-step mutation enumeration per P0.R11 Observation 1 absorption pattern; defends against missing-step silent-masking shape.
   - **A3+A4+A5+A6+A9 behavioral refinement at §3**: explicit `torch.cuda.is_available` + `torch.cuda.mem_get_info` monkeypatch + None-return verification at both call sites.

4. **Cross-path discipline preventive commitment** (per `feedback_architect_reads_catches_phase_7_memory_file_omission.md` 4th sub-variant CROSS-PATH-SYNC-OMISSION operational rule, locked at P0.R11 closure-audit): §6 enumerates cross-path verification steps EXPLICITLY for both memory-file extensions. Architect commits to fresh Read both paths post-edit at closure to verify landing.

5. **Bidirectional grep-verify discipline-firing** (NEW pattern at P0.R9 Phase 0): architect's fresh Read at verdict-receipt time caught auditor's stale-cached verification claim. Distinct from prior cycles' architect-catches-architect patterns. Bank as 1st bidirectional-validation instance. Watch criteria 3+ instances for sub-rule elevation under cross-actor grep-verify discipline family.

6. **Q1-Q9 already RATIFIED at Phase 0 verdict** — no Plan v1 adjudication needed. Plan v1 §2 D-decisions are LOCKED at Phase 0 architect leans.

---

**End of Plan v1.** Ready for auditor verdict.
