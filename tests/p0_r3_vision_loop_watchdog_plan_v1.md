# P0.R3 — Vision-loop watchdog (heartbeat + supervised restart + degraded fallback) — Plan v1

**Status:** Plan v1 drafted 2026-05-23 with Q1-Q7 locked per P0.R3 Phase 0 verdict + Q7 non-blocking refinement absorbed. APPROVED-AT-AUDITOR-REVIEW pending.

**Parent audit:** `tests/p0_r3_vision_loop_watchdog_audit.md` (Phase 0 ACCEPTED with 0 BLOCKING PIs + 1 non-blocking Q7 refinement on stale-persists log).

---

## §1 — Phase 0 reconciliation

**§1.1 Q1-Q7 lock summary per auditor verdict 2026-05-23:**

| Q | Decision | Lock |
|---|---|---|
| Q1 | Heartbeat storage location | **(a) PipelineStateStore** — new `vision_heartbeat_at: float = 0.0` field + async setter `set_vision_heartbeat` + sync peeker `peek_vision_heartbeat_at`. P0.6 ratchet aligned; cloud_state precedent supports. |
| Q2 | Watchdog implementation location | **(a) NEW dedicated `_vision_watchdog_loop` async function in pipeline.py** — positioned near `_health_log_loop`; 5s polling cadence distinct from 300s health log; module-level new file overkill for ~30 LOC. |
| Q3 | `vision_degraded` flag storage location | **(a) PipelineStateStore** — new `vision_degraded: bool = False` field + async setter `set_vision_degraded` + sync peeker `peek_vision_degraded`. Consistent with Q1; ratchet-aligned. |
| Q4 | Restart-failure criterion | **(c) combined** — exception OR heartbeat-timeout. Defensive-specification convention (matches P0.5 sentinel + try/except + boot reconciliation defensive pattern). Heartbeat-timeout-only (b) is functionally equivalent but combined (c) makes the contract explicit for future maintenance. |
| Q5 | Anchor count | **10 anchors at exact mid 10; inclusive ±15% band [8.5, 11.5]** — 9/10/11 all qualify ON-TARGET per locked methodology from P0.S5/B5/R2. |
| Q6 | WatchdogAgent integration | **(b) health.py only** — operator-actionable; no best_friend alert escalation. P0.R3.X if empirical evidence shows it adds value. |
| Q7 | Restart endless-loop protection + stale-persists logging | **CONFIRMED semantic + non-blocking refinement absorbed at Plan v1** — restart fires ONCE per stale-detection cycle; if it fails → mark degraded + STOP respawning. **NEW per Q7 refinement**: subsequent stale-detection cycles while `vision_degraded` already set emit log `[Vision] stale persists (vision_degraded set; awaiting heartbeat recovery)` (operator-visible signal that issue persists). Architect absorbed at Plan v1 §2.2 (D2 spec extension) + A2 source-inspection (persists log substring required) + A3 behavioral parametrize fan-out (degraded=false: restart fires; degraded=true: restart skipped + persists log fires). |

**§1.2 Diligent Pass-2 grep enumeration (per operational-rule extension banked at P0.R1 closure 2026-05-23; auditor verification target):**

Files affected by P0.R3 implementation (5 files total; exhaustive per architect's diligent enumeration):

| File | Edit type | D-decision | Lines/scope |
|---|---|---|---|
| `core/config.py` | NEW constants (3 lines added in vision-related section) | D2 | `VISION_WATCHDOG_INTERVAL_SECS=5.0`, `VISION_WATCHDOG_STALE_THRESHOLD_SECS=30.0`, `VISION_WATCHDOG_RESTART_TIMEOUT_SECS=30.0` |
| `core/pipeline_state_store.py` | NEW fields + setters/peekers (~25 LOC) | D1+D3 | `vision_heartbeat_at: float = 0.0` + `vision_degraded: bool = False` + `set_vision_heartbeat`, `peek_vision_heartbeat_at`, `set_vision_degraded`, `peek_vision_degraded` |
| `core/health.py` | NEW HealthSnapshot field (~1 LOC) + format_health_line conditional emit (~3 LOC) + format_health_alerts emit (~6 LOC) | D3 | `vision_degraded: bool = False` field on HealthSnapshot dataclass; `format_health_line` adds `vision=degraded` field when set (mirrors evlog_parts/kuzu_parts pattern); `format_health_alerts` emits `Vision subsystem degraded — restart attempts failing; check camera/driver state.` actionable alert |
| `pipeline.py` | D1 heartbeat update (1 LOC inside `_background_vision_loop`) + D2 NEW `_vision_watchdog_loop` body (~35 LOC) + D4 restart helper (~30 LOC) + D5 startup spawn (1 line) + D5 shutdown cancel (1 line in finally) | D1+D2+D4+D5 | `_background_vision_loop` body at line 2401 gains heartbeat-update line; NEW `_vision_watchdog_loop` async function near `_health_log_loop`; `run()` startup gains watchdog task spawn after vision task spawn; `run()` shutdown finally gains watchdog cancel before vision cancel |
| `tests/test_p0_r3_vision_loop_watchdog.py` | NEW test file (10 anchors per §3) | All | 10 logical anchors; 1:1 pytest-function-to-anchor mapping; A3 uses parametrize fan-out for Q7 absorption (degraded=false vs degraded=true branches) |

**Cross-checked against auditor's independent re-grep target:** 5 files total. NO twin filename collision (`vision_watchdog` keyword grep yields zero hits before this Plan v1; new test file lands at `tests/test_p0_r3_vision_loop_watchdog.py`).

**§1.3 P0.R3 D-decisions vs P0.R2 vision_provider_state orthogonality (cross-spec impact verified clean):**

- `vision_provider_state.py` (P0.R2) tracks CUDA/CPU provider state via `get_active_provider()` / `record_cuda_failure()` / `maybe_retry_cuda(now)` — separate concern.
- `vision_heartbeat_at` + `vision_degraded` (P0.R3 on PipelineStateStore) track VISION SUBSYSTEM liveness via watchdog supervision.
- Both fire INDEPENDENTLY in `format_health_line`: `vision_provider=cpu` AND `vision=degraded` can BOTH emit in same line (CUDA fallback to CPU AND subsystem hard-failed). Operator distinguishes "soft degradation" (CPU OK, recognition works) vs "hard fail" (vision loop crashed; recognition unavailable).
- D4 restart helper does NOT touch `vision_provider_state` — task respawn is at the asyncio task layer; provider state is at the inference layer; no interaction.

**§1.4 Twin-filename pitfall 17th preventive event ALREADY honored at Phase 0 audit drafting (no doctrine count bump per locked enumeration rule).**

---

## §2 — D-decision contracts (LOCKED per Q1-Q7 verdicts)

### §2.1 D1 — Heartbeat update in `_background_vision_loop`

**Edit site:** `pipeline.py:2401` (start of `while True:` body in `_background_vision_loop`, BEFORE `frame = await loop.run_in_executor(None, camera.read)`).

**Spec:**

```python
async def _background_vision_loop(camera, detector, embedder=None, temporal_buffer=None, db=None) -> None:
    """..."""
    loop = asyncio.get_running_loop()
    while True:
        # P0.R3 D1 — heartbeat update at iteration start (BEFORE camera.read).
        # Fire-and-forget via loop.create_task per existing sync-mutator pattern.
        # Race-safe: write fires from main loop, never from executor thread.
        loop.create_task(_pipeline_state_store.set_vision_heartbeat(time.time()))
        
        frame = await loop.run_in_executor(None, camera.read)
        if frame is None:
            await asyncio.sleep(0.05)
            continue
        # ... rest of body unchanged
```

**Contract:** every iteration of the loop emits a heartbeat update marking the loop is alive AT the iteration boundary. Heartbeat write is non-blocking via `loop.create_task`. Heartbeat reflects "loop is ALIVE", not "loop completed previous iteration".

### §2.2 D2 — NEW `_vision_watchdog_loop` async function

**Edit site:** NEW function in `pipeline.py` at module level, positioned BEFORE `_background_vision_loop` (so it's visible at module load).

**Spec (Q7 refinement ABSORBED — persists log + degraded-set branch):**

```python
# Module-level state for D4 restart helper to manipulate.
_vision_task: "asyncio.Task | None" = None

async def _vision_watchdog_loop() -> None:
    """P0.R3 D2 — supervises _background_vision_loop liveness via heartbeat.
    
    Polls every VISION_WATCHDOG_INTERVAL_SECS=5.0; if heartbeat staleness exceeds
    VISION_WATCHDOG_STALE_THRESHOLD_SECS=30.0, restart the vision task once.
    On restart failure → set vision_degraded; subsequent stale detections log
    [Vision] stale persists + no respawn (next successful heartbeat clears).
    """
    while True:
        await asyncio.sleep(VISION_WATCHDOG_INTERVAL_SECS)
        _now = time.time()
        _heartbeat_at = _pipeline_state_store.peek_vision_heartbeat_at()
        _staleness = _now - _heartbeat_at
        if _staleness < VISION_WATCHDOG_STALE_THRESHOLD_SECS:
            continue
        # Staleness detected. Two branches per Q7 lock.
        if _pipeline_state_store.peek_vision_degraded():
            # Subsequent stale-detection while degraded already set (Q7 refinement).
            # Log + no-op for restart. Next successful heartbeat naturally clears degraded.
            print(f"[Vision] stale persists (vision_degraded set; awaiting heartbeat recovery; staleness={_staleness:.1f}s)")
            continue
        # First stale detection (degraded not yet set). Invoke restart helper.
        print(f"[Vision] stale detected (staleness={_staleness:.1f}s; restarting vision task)")
        await _restart_vision_task()


async def _restart_vision_task() -> None:
    """P0.R3 D4 — supervised restart of _background_vision_loop.
    
    Cancels current task, spawns new task, waits for first heartbeat advance.
    On restart success (heartbeat advances past pre-restart value within
    VISION_WATCHDOG_RESTART_TIMEOUT_SECS) → clear vision_degraded.
    On restart fail (exception during spawn OR heartbeat unchanged after timeout)
    → set vision_degraded + log fail-loud line. Q4 (c) combined criterion.
    """
    global _vision_task
    _prev_heartbeat = _pipeline_state_store.peek_vision_heartbeat_at()
    
    # Cancel current task gracefully.
    try:
        if _vision_task is not None and not _vision_task.done():
            _vision_task.cancel()
            await asyncio.gather(_vision_task, return_exceptions=True)
    except Exception as e:
        print(f"[Vision] watchdog: existing task cancellation error: {e!r}")
    
    # Respawn new task. Q4 (c): catch exception path explicitly.
    try:
        _vision_task = asyncio.get_running_loop().create_task(
            _background_vision_loop(_vision_camera_ref, _vision_detector_ref, _vision_embedder_ref, _vision_temporal_buffer_ref, _vision_db_ref)
        )
    except Exception as e:
        print(f"[Vision] watchdog: respawn raised: {e!r}; marking vision_degraded")
        loop = asyncio.get_running_loop()
        loop.create_task(_pipeline_state_store.set_vision_degraded(True))
        return
    
    # Wait for heartbeat advance (Q4 (c) heartbeat-timeout criterion).
    _deadline = time.time() + VISION_WATCHDOG_RESTART_TIMEOUT_SECS
    while time.time() < _deadline:
        await asyncio.sleep(1.0)
        if _pipeline_state_store.peek_vision_heartbeat_at() > _prev_heartbeat:
            # Restart succeeded. Clear degraded if previously set.
            if _pipeline_state_store.peek_vision_degraded():
                loop = asyncio.get_running_loop()
                loop.create_task(_pipeline_state_store.set_vision_degraded(False))
                print(f"[Vision] watchdog: restart success; vision_degraded cleared")
            else:
                print(f"[Vision] watchdog: restart success")
            return
    
    # Heartbeat did not advance within timeout. Set degraded.
    print(f"[Vision] watchdog: restart timeout (heartbeat unchanged after {VISION_WATCHDOG_RESTART_TIMEOUT_SECS:.0f}s); marking vision_degraded")
    loop = asyncio.get_running_loop()
    loop.create_task(_pipeline_state_store.set_vision_degraded(True))
```

**Contract:** watchdog runs every 5s. Stale detection threshold 30s. Restart fires ONCE per stale detection. Subsequent stale detections while degraded set emit log + skip restart. Restart-fail (exception OR heartbeat timeout) sets `vision_degraded`. Restart-success clears `vision_degraded`.

### §2.3 D3 — `vision_degraded` flag + health alert

**Edit sites:**

- `core/pipeline_state_store.py`: add 2 new fields + 4 new methods.
- `core/health.py`: add 1 new HealthSnapshot field + 1 new conditional in `format_health_line` + 1 new conditional in `format_health_alerts`.

**Spec for PipelineStateStore (`core/pipeline_state_store.py`):**

```python
# New fields on PipelineStateStore __init__ (additive; backward-compat preserved).
self._vision_heartbeat_at: float = 0.0
self._vision_degraded: bool = False

async def set_vision_heartbeat(self, ts: float) -> None:
    """P0.R3 D1 — scalar setter for vision-loop heartbeat. No lock (CPython GIL sufficient)."""
    self._vision_heartbeat_at = ts

def peek_vision_heartbeat_at(self) -> float:
    """P0.R3 D2 — sync peeker for watchdog stale-detection."""
    return self._vision_heartbeat_at

async def set_vision_degraded(self, degraded: bool) -> None:
    """P0.R3 D3 — scalar setter for vision-subsystem degraded flag."""
    self._vision_degraded = degraded

def peek_vision_degraded(self) -> bool:
    """P0.R3 D3 — sync peeker for health.py + watchdog persists-branch."""
    return self._vision_degraded
```

**Spec for HealthSnapshot + format_health_line (`core/health.py`):**

```python
@dataclass(frozen=True)
class HealthSnapshot:
    # ... existing fields ...
    vision_degraded: bool = False  # P0.R3 D3 — set True when watchdog restart fails

def format_health_line(snap: HealthSnapshot) -> str:
    # ... existing logic ...
    if snap.vision_degraded:
        _parts.append("vision=degraded")
    # ... rest unchanged
```

**Spec for format_health_alerts (`core/health.py`):**

```python
def format_health_alerts(snap: HealthSnapshot) -> list[str]:
    alerts: list[str] = []
    # ... existing alerts ...
    if snap.vision_degraded:
        alerts.append(
            "Vision subsystem degraded — restart attempts failing; "
            "check camera/driver state. "
            "Recovery: verify USB camera connection + driver; "
            "vision_degraded clears automatically on next successful heartbeat."
        )
    return alerts
```

**Contract:** `vision_degraded` is operator-actionable observability. Cleared automatically by D4 on restart success; set automatically by D4 on restart failure. Health log + health alerts surface to operator.

### §2.4 D4 — Supervised restart helper

**Edit site:** `_restart_vision_task` body inside pipeline.py (per §2.2 spec verbatim above).

**Contract (LOCKED per Q4 (c) combined criterion):**

1. **Cancel current task** gracefully via `_vision_task.cancel()` + `await asyncio.gather(_vision_task, return_exceptions=True)`.
2. **Respawn** new task; if `create_task` raises → log + set degraded → return (exception path of Q4 (c)).
3. **Wait** up to `VISION_WATCHDOG_RESTART_TIMEOUT_SECS=30.0` for heartbeat advance.
4. **Heartbeat advanced** → restart success → clear degraded (if was set).
5. **Heartbeat NOT advanced after timeout** → restart fail → log + set degraded (timeout path of Q4 (c)).

**Critical invariant — "keep audio alive"**: restart helper cancels ONLY `_vision_task` (vision loop's asyncio task). Audio loop runs as a separate task; never touched by D4. Watchdog has no reference to audio task.

### §2.5 D5 — Startup + shutdown wiring

**Edit sites in `pipeline.py::run()`:**

**Startup (after vision task spawn):**

```python
# Existing line (already present):
_vision_task = loop.create_task(_background_vision_loop(camera, detector, embedder, temporal_buffer, db))

# NEW per P0.R3 D5 — spawn watchdog after vision task.
_vision_watchdog_task = loop.create_task(_vision_watchdog_loop())
```

**Shutdown (finally block; ordering invariant — watchdog cancel BEFORE vision cancel):**

```python
finally:
    # Existing audio task cancel ...
    
    # NEW per P0.R3 D5 — cancel watchdog FIRST so it doesn't respawn vision during shutdown.
    if _vision_watchdog_task and not _vision_watchdog_task.done():
        _vision_watchdog_task.cancel()
        try:
            await _vision_watchdog_task
        except (asyncio.CancelledError, Exception):
            pass
    
    # Existing vision task cancel (now cancelled AFTER watchdog).
    if _vision_task and not _vision_task.done():
        _vision_task.cancel()
        try:
            await _vision_task
        except (asyncio.CancelledError, Exception):
            pass
```

**Contract:** watchdog spawned AFTER vision task (D2 needs vision task to exist before supervising). Watchdog cancelled BEFORE vision task (D5 ordering invariant — prevents watchdog respawning vision during shutdown).

### §2.6 Deliberate-regression protocol (induction-surfaces-invariant-gaps; 6 reverts per D-decision coverage)

Before declaring closure, developer runs the following 6 deliberate-regression checks. Each fires the named anchor when reverted. If any check fails to fire, anchor needs strengthening (per `### Induction-surfaces-invariant-gaps` operational rule).

| Revert | Removed contract | Expected fire |
|---|---|---|
| **(a)** Remove `loop.create_task(_pipeline_state_store.set_vision_heartbeat(time.time()))` from `_background_vision_loop:2401` | D1 heartbeat update gone | A1 source-inspection fires (heartbeat update substring missing) |
| **(b)** Stub `_vision_watchdog_loop` to `while True: await asyncio.sleep(VISION_WATCHDOG_INTERVAL_SECS)` (no stale detection) | D2 watchdog stale-check gone | A2 source-inspection fires (stale-check + persists log substrings missing) |
| **(c)** Replace D4 `set_vision_degraded(True)` on exception path with no-op | D4 restart-fail set-degraded gone | A8 behavioral fires (vision_degraded stays False post-fail) |
| **(d)** Replace D4 `set_vision_degraded(False)` on success path with no-op | D4 restart-success clear-degraded gone | A7 behavioral fires (vision_degraded stays True post-recovery) |
| **(e)** Remove `vision_degraded: bool = False` field from HealthSnapshot dataclass | D3 HealthSnapshot field gone | A5 source-inspection fires (field missing on dataclass) |
| **(f)** Reverse shutdown cancel order (vision cancelled before watchdog) | D5 ordering invariant violated | A10 source-inspection fires (AST line-order check) |

Phase 5 closure narrative includes deliberate-regression confirmation outcomes per locked discipline. Any FAIL surfaces detector gap → strengthen in same cycle per `### Induction-surfaces-invariant-gaps` operational rule 3.

---

## §3 — Anchor decomposition LOCK (10 anchors at exact mid 10 inclusive ±15%)

| # | D | Anchor name | Type | Coverage |
|---|---|---|---|---|
| A1 | D1 | `test_p0_r3_d1_anchor_1_heartbeat_update_in_loop` | source-inspection | `_background_vision_loop` body contains `set_vision_heartbeat` call BEFORE `camera.read` |
| A2 | D2 | `test_p0_r3_d2_anchor_1_watchdog_loop_source` | source-inspection | `_vision_watchdog_loop` exists + `asyncio.sleep(VISION_WATCHDOG_INTERVAL_SECS)` cadence + stale check `> VISION_WATCHDOG_STALE_THRESHOLD_SECS` + `peek_vision_degraded` persists-branch + `stale persists` log substring |
| A3 | D2 | `test_p0_r3_d2_anchor_2_stale_triggers_restart_OR_persists` | behavioral (parametrize 2 cases) | Case (degraded=False): stale heartbeat → restart-helper invoked + restart log fires. Case (degraded=True): stale heartbeat → restart-helper NOT invoked + `stale persists` log fires. **Q7 absorption** |
| A4 | D3 | `test_p0_r3_d3_anchor_1_store_has_vision_fields` | source-inspection | PipelineStateStore has `_vision_heartbeat_at: float = 0.0` + `_vision_degraded: bool = False` + 4 methods (`set_vision_heartbeat`, `peek_vision_heartbeat_at`, `set_vision_degraded`, `peek_vision_degraded`) |
| A5 | D3 | `test_p0_r3_d3_anchor_2_health_snapshot_field` | source-inspection | `HealthSnapshot` dataclass has `vision_degraded: bool = False` field |
| A6 | D3 | `test_p0_r3_d3_anchor_3_format_alerts_emits_degraded` | source-inspection | `format_health_alerts` body emits actionable `Vision subsystem degraded` substring + recovery-instruction substrings (`check camera/driver state` + `clears automatically`) when `snap.vision_degraded == True` |
| A7 | D4 | `test_p0_r3_d4_anchor_1_restart_success_clears_degraded` | behavioral | Simulate: pre-restart heartbeat=T1, vision_degraded=True; respawn → new task fires heartbeat=T2 (T2 > T1); D4 detects + clears `vision_degraded → False` |
| A8 | D4 | `test_p0_r3_d4_anchor_2_restart_fail_sets_degraded` | behavioral | Simulate: respawn raises OR heartbeat doesn't advance within VISION_WATCHDOG_RESTART_TIMEOUT_SECS; D4 sets `vision_degraded → True`. Critical sub-assertion: audio task NOT cancelled (keep-audio-alive invariant) |
| A9 | D5 | `test_p0_r3_d5_anchor_1_watchdog_spawn_after_vision_AND_cancel_before_vision` | source-inspection (AST line-order) | `pipeline.py::run()` startup: `_vision_watchdog_task = ...` line appears AFTER `_vision_task = ...` line. Shutdown finally: `_vision_watchdog_task.cancel()` line appears BEFORE `_vision_task.cancel()` line |
| A10 | D2 | `test_p0_r3_d2_anchor_3_config_constants_present` | source-inspection | `core/config.py` contains `VISION_WATCHDOG_INTERVAL_SECS=5.0` + `VISION_WATCHDOG_STALE_THRESHOLD_SECS=30.0` + `VISION_WATCHDOG_RESTART_TIMEOUT_SECS=30.0` constants |

**Total: 10 logical anchors. 1:1 pytest-function-to-anchor mapping; A3 uses parametrize fan-out for Q7 absorption (1 logical anchor, 2 parametrize cases). Mid 10 exact match to Phase 0 §6 lock.**

---

## §4 — Honest-count commitment table (inclusive ±15% per locked methodology)

| Closure-actual | Overage | Band | Doctrine impact + commitment |
|---|---|---|---|
| 7 | −30.0% | ≥30% FALSIFICATION | Doctrine demotes; architect commits to honoring this outcome at closure-audit |
| 8 | −20.0% | ±15-30% SLIGHT-DRIFT-DOWN | Doctrine holds (watch trajectory); architect commits to honoring |
| **9** | **−10.0%** | **±15% ON-TARGET** | **Doctrine bumps 15 → 16**; architect commits |
| **10** | **0.0%** | **±15% ON-TARGET (exact mid)** | **Doctrine bumps 15 → 16; 8+ consecutive 0% exact-mid streak extends per `Doctrine-prediction-precision-improving-over-arc`**; architect commits |
| **11** | **+10.0%** | **±15% ON-TARGET** | **Doctrine bumps 15 → 16**; architect commits |
| 12 | +20.0% | ±15-30% SLIGHT-DRIFT-UP | Doctrine holds (watch trajectory); architect commits to honoring |
| ≥13 | ≥+30% | FALSIFICATION | Doctrine demotes; architect commits to honoring this outcome at closure-audit |

**`Explicit-closure-honest-count-commitment` 18 → 20 (19th MADE at Plan v1 §4 + 20th HONORED at closure per STRICT separation). 8+ consecutive 0% exact-mid streak only extends if closure-actual = 10 exact.**

---

## §5 — Closure-narrative paste-template

(Architect's pre-draft for closure narrative subject to closure-actual reconciliation + Path C grep-verify of doctrine counts.)

**P0.R3 closure note (parent + subdir complete-plan.md surfaces, plus CLAUDE.md header prepended):**

> ## P0.R3 — Vision-loop watchdog (heartbeat + supervised restart + degraded fallback) — D1+D2+D3+D4+D5 + 10 anchors + 6 deliberate-regression checks; OPTIONAL-Plan-v2 path TAKEN; 7th proof case under absorbed sub-rule  [CLOSED 2026-05-23]
> 
> **Sub-PR sequence:** Phase 0 audit (`tests/p0_r3_vision_loop_watchdog_audit.md`, APPROVED with 0 BLOCKING PIs + 1 non-blocking Q7 refinement absorbed at Plan v1 — **13th instance of `### Zero-precision-items-at-auditor-review` at Phase 0 surface**; 2nd consecutive clean review in pattern-broken streak) → Plan v1 (`tests/p0_r3_vision_loop_watchdog_plan_v1.md`, RATIFIED with 0 PIs at Plan v1 surface — **14th instance of `### Zero-precision-items-at-auditor-review` doctrine** firing at Plan v1 review; pattern-broken streak extends to 3 cycles; **7th OPTIONAL-Plan-v2 path proof case** under absorbed sub-rule track record P0.S3 + P0.B3 + P0.B5 + P0.B6 + P0.S8 + P0.R2 + P0.R3) → Phase 1-4 implementation.
> 
> **OPTIONAL-Plan-v2 path SUCCESS** — 2nd consecutive clean Phase 0 + Plan v1 cycle (P0.R2 was 1st; P0.R3 is 2nd). Pattern-broken streak extends. Architect's diligent Pass-2 grep enumeration (per operational-rule extension banked at P0.R1 closure handoff) empirically validated across 3 cycles now (P0.R2 Plan v1 + P0.R3 Phase 0 + P0.R3 Plan v1) → operational-rule extension promotion candidate.
> 
> **What shipped:** 5 D-decisions across `core/config.py` (D2 constants) + `core/pipeline_state_store.py` (D1+D3 fields) + `core/health.py` (D3 health field + alert) + `pipeline.py` (D1 heartbeat + D2 watchdog + D4 restart helper + D5 wiring).
> 
> **D1 (heartbeat update)**: `_background_vision_loop` body at `pipeline.py:2401` fires `loop.create_task(_pipeline_state_store.set_vision_heartbeat(time.time()))` at iteration start BEFORE camera.read; race-safe via main-loop write.
> 
> **D2 (watchdog loop)**: NEW `_vision_watchdog_loop` async function in `pipeline.py` polls every 5s (`VISION_WATCHDOG_INTERVAL_SECS`); stale detection threshold 30s (`VISION_WATCHDOG_STALE_THRESHOLD_SECS`); Q7 stale-persists log fires while degraded set (operator-visible continued staleness signal).
> 
> **D3 (vision_degraded flag + health alert)**: PipelineStateStore gains `vision_heartbeat_at: float` + `vision_degraded: bool` fields + 4 methods. HealthSnapshot extended with `vision_degraded: bool = False` field; `format_health_line` conditional emit `vision=degraded`; `format_health_alerts` actionable alert with recovery instructions.
> 
> **D4 (supervised restart)**: `_restart_vision_task` helper applies Q4 (c) combined criterion — exception path catches `create_task` raise; heartbeat-timeout path waits up to 30s (`VISION_WATCHDOG_RESTART_TIMEOUT_SECS`) for heartbeat advance. Restart success clears `vision_degraded`; restart fail sets `vision_degraded`. Critical invariant: keep audio alive — D4 cancels ONLY `_vision_task`; audio loop runs independently.
> 
> **D5 (startup + shutdown wiring)**: `pipeline.run()` spawns `_vision_watchdog_task` AFTER `_vision_task`; shutdown finally cancels `_vision_watchdog_task` BEFORE `_vision_task` (ordering invariant prevents respawn-during-shutdown).
> 
> **Total P0.R3 LOGICAL ANCHORS: 10** (Plan v1 §3 LOCK EXACT MATCH at exact mid 10 inclusive ±15% band [8.5, 11.5]; 1:1 pytest-function-to-anchor mapping; A3 parametrize fan-out for Q7 absorption).
> 
> **Q5 closure under MID-RANGE methodology**: auditor mid 10, Plan v1 lock 10, **closure actual {{N}}** ({{0%|−10%|+10%}}; {{exact mid|ON-TARGET}}). Doctrine `### Phase-0-granular-decomposition-enables-accurate-estimates` **BUMPS 15 → 16 SUPPORTING INSTANCES** per inclusive ±15% band table.
> 
> **Plan v1 §4 honest-count commitment HONORED — 20th instance of `Explicit-closure-honest-count-commitment` discipline** (19th MADE at Plan v1 §4, 20th HONORED at closure per STRICT separation).
> 
> **6/6 deliberate-regression confirmations PASSED** (a/b/c/d/e/f per §2.6 — heartbeat update revert + watchdog stale-check revert + restart-fail set-degraded revert + restart-success clear-degraded revert + HealthSnapshot field revert + shutdown cancel-order revert). All reverts restored cleanly.
> 
> **`### Zero-precision-items-at-auditor-review` doctrine 13 → 14 instances** (Phase 0 13th + Plan v1 14th). **OPTIONAL-Plan-v2 path TAKEN — 7th proof case** banked under absorbed sub-rule track record (P0.S3 + P0.B3 + P0.B5 + P0.B6 + P0.S8 + P0.R2 + P0.R3). Pattern-broken streak extends from 2 → 3 cycles (P0.R2 Plan v1 + P0.R3 Phase 0 + P0.R3 Plan v1).
> 
> **Strict-mode 59 → 62 applications + 17 → 18 closures** (3-artifact OPTIONAL-Plan-v2 cycle: Phase 0 + Plan v1 + closure). **Discipline counts (3-artifact cycle)**: spec-first review cycle 69 → 72-for-72 at closure. **`### Grep-baseline-before-drafting` 26 → 29 instances** (3 artifacts). **Cross-cycle-handoff transparency precedent 32 → 35 successful** (3 artifacts). **Spec-time grep-verification 36 → 39 instances** (3 artifacts; Phase 0 §1 Pass-1 + Plan v1 §1.2 DILIGENT Pass-2 + closure-narrative drafting Pass-3 baseline). **Twin-filename-pitfall-prevention** 17th preventive event already honored at Phase 0 + 18th at closure (no doctrine count bump per locked enumeration rule).
> 
> **Auditor-Q5-estimates-trail-grep 21 → 22 banked closures** at {{0%|N%}} reading. Trajectory across 14 cycles under MID-RANGE methodology: P0.S3 +12.5% → ... → P0.R2 0% → **P0.R3 {{0%|N%}}** ({{8th consecutive 0% reading; `Doctrine-prediction-precision-improving-over-arc` sub-observation continues extending|N%}}).
> 
> **Deferred-canary strategy 20th application** — entry pasted verbatim into `c:\Users\jagan\dog-ai\to_be_checked.md`.
> 
> **Known Limitations (P0.R3 closure)**:
> 
> 1. **Watchdog-of-watchdog excluded by design** — if `_vision_watchdog_loop` itself dies, vision restart-supervision is gone but vision loop keeps running. Process supervisor (P0.R4) catches the worst case.
> 2. **Restart endless-loop protection** — restart fires ONCE per stale-detection cycle; subsequent stale detections while degraded set are no-ops (log + skip respawn). Mitigates "thrash respawning permanently-dead camera" failure mode. Q7 stale-persists log keeps operator informed.
> 3. **False-positive cost on legitimate slow iteration** — 30s threshold is conservative; legitimate vision iterations complete in <50ms typical. False-positive rate expected ~0. 1 restart costs ~100ms; acceptable if it ever fires.
> 4. **`vision_degraded` is observability-only, not self-healing** — operator sees the alert + can intervene (reconnect camera, restart pipeline). If camera permanently dead, flag stays set until process restart.
> 5. **D2 vs D3 CUDA-unavailable asymmetry (P0.R2.X)** — separate concern from P0.R3; pre-existing as P0.R2.X follow-up.
> 
> **Cumulative suite**: {{N}} passed + {{M}} skipped = {{N+M}} total collected (+10 new anchors from `tests/test_p0_r3_vision_loop_watchdog.py`).

**§5.1 5-surface landing checklist (developer Phase 5 closure):**

1. ✓ `c:\Users\jagan\dog-ai\dog-ai\CLAUDE.md` — header P0.R3 entry prepended above P0.R2
2. ✓ `c:\Users\jagan\dog-ai\complete-plan.md::P0.R3` (parent) — status (no status pre-existed) → `[CLOSED]` + closure note
3. ✓ `c:\Users\jagan\dog-ai\dog-ai\complete-plan.md::P0.R3` (subdir) — full closure narrative
4. ✓ `c:\Users\jagan\dog-ai\to_be_checked.md` — 20th deferred-canary entry + coverage matrix row
5. ✓ Architect memory files via post-closure handoff (`feedback_phase_0_zero_precision_items_at_auditor_review.md` 13 → 14; `MEMORY.md` index refresh)

---

## §6 — Architect's diligent Pass-2 grep enumeration (auditor verification target per operational-rule extension)

**Verification-target query patterns + expected file:line outcomes:**

| Grep pattern | Expected matches | Verification |
|---|---|---|
| `_background_vision_loop` (existing) | `pipeline.py:2384` definition + line ~2403 spawn site in `run()` | Existing function; D1 mutation at line 2401 (heartbeat update insert) |
| `_vision_watchdog_loop` (NEW) | `pipeline.py` definition near `_health_log_loop` + `pipeline.py::run()` spawn line | NEW function per D2; D5 spawns in `run()` |
| `_restart_vision_task` (NEW) | `pipeline.py` definition near `_vision_watchdog_loop` | NEW helper per D4 |
| `set_vision_heartbeat` (NEW) | `core/pipeline_state_store.py` method definition + `pipeline.py:~2401` call site (D1) | NEW method per Q1 |
| `peek_vision_heartbeat_at` (NEW) | `core/pipeline_state_store.py` method definition + `pipeline.py::_vision_watchdog_loop` + `_restart_vision_task` call sites | NEW peeker per Q1 |
| `set_vision_degraded` (NEW) | `core/pipeline_state_store.py` method definition + `pipeline.py::_restart_vision_task` call sites (2: set True + set False) | NEW method per Q3 |
| `peek_vision_degraded` (NEW) | `core/pipeline_state_store.py` method definition + `pipeline.py::_vision_watchdog_loop` + `core/health.py::format_health_line` + `format_health_alerts` call sites | NEW peeker per Q3 |
| `vision_degraded` field grep across `core/health.py` | HealthSnapshot dataclass field + format_health_line conditional + format_health_alerts conditional | NEW per D3 |
| `VISION_WATCHDOG_INTERVAL_SECS` | `core/config.py` definition + `pipeline.py::_vision_watchdog_loop` usage | NEW per D2 |
| `VISION_WATCHDOG_STALE_THRESHOLD_SECS` | `core/config.py` definition + `pipeline.py::_vision_watchdog_loop` usage | NEW per D2 |
| `VISION_WATCHDOG_RESTART_TIMEOUT_SECS` | `core/config.py` definition + `pipeline.py::_restart_vision_task` usage | NEW per D4 |
| `stale persists` log substring | `pipeline.py::_vision_watchdog_loop` body | NEW per Q7 absorption |

**Auditor's independent re-grep target:** all 12 patterns above + cross-check NO twin filename collision (`vision_watchdog`, `vision_heartbeat_at`, `vision_degraded` keywords yield only the P0.R3 NEW surfaces).

**Architect prediction (probabilistic per `Zero-precision-items-pre-closure-predictions-blocked` operational rule):** Plan v1 §1.2 + §6 enumeration is diligent; expecting clean auditor independent re-grep verification per the operational-rule extension banked at P0.R1 closure. If clean (3rd consecutive clean review including P0.R2 Plan v1 + P0.R3 Phase 0), pattern-broken streak extends to 3 cycles → operational-rule extension promotion candidate.

---

## §7 — Doctrine bump projection at closure (closure-conditional per inclusive ±15% band)

| Doctrine | Pre-P0.R3 baseline | Closure projection |
|---|---|---|
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 15 (post-P0.R2 closure) | 16 IF closure-actual ∈ {9, 10, 11} |
| `### Zero-precision-items-at-auditor-review` | 13 (post-P0.R3 Phase 0) | 14 IF Plan v1 fires clean (0 PIs) |
| `### Induction-surfaces-invariant-gaps` | 10 (post-P0.R2 closure) | 10 (stays unless in-flight detector-strengthening event) |
| `### Architect-reads-production-code-before-sign-off` | 14 (post-P0.R2 closure-audit reconciliation per Path C lean) | 15 IF architect closure-audit fires at P0.R3 closure |
| OPTIONAL-Plan-v2 sub-rule proof cases | 6 (post-P0.R2 closure) | 7 IF closure-actual ∈ {9, 10, 11} |
| `Explicit-closure-honest-count-commitment` | 18 (post-P0.R2 closure) | 20 (19 MADE at Plan v1 §4 + 20 HONORED at closure) |
| Strict-mode applications | 59 (post-P0.R2 closure) | 62 (3-artifact cycle: Phase 0 + Plan v1 + closure) |
| Strict-mode closures | 17 (post-P0.R2 closure) | 18 |
| Spec-first review cycle | 69 (post-P0.R2 closure) | 72 (3 artifacts × +1) |
| `### Grep-baseline-before-drafting` | 26 (post-P0.R2 closure) | 29 (3 artifacts) |
| Cross-cycle-handoff transparency | 32 (post-P0.R2 closure) | 35 (3 artifacts) |
| Spec-time grep-verification | 36 (post-P0.R2 closure) | 39 (3 artifacts) |
| `Doctrine-prediction-precision-improving-over-arc` | 7+ cycle 0% streak | 8+ cycle 0% streak ONLY IF closure-actual = 10 exact |
| `Auditor-Q5-estimates-trail-grep` | 21 banked (post-P0.R2 closure) | 22 banked |

**Closure-conditional banks pending; locked at architect closure-audit per `Convention-drift-on-discipline-counts` + Path C grep-verify reconciliation discipline.**

---

## §8 — §8 row paste-template (for parent complete-plan.md + subdir complete-plan.md + CLAUDE.md header)

(Architect's pre-draft; subject to closure-actual reconciliation.)

```
| P0.R3 | Vision-loop watchdog (heartbeat + supervised restart + degraded fallback) | CLOSED 2026-05-23 | D1+D2+D3+D4+D5 + 10 anchors at exact mid 10 inclusive ±15% band; OPTIONAL-Plan-v2 7th proof case; 8+ consecutive 0% exact-mid streak {{extends|breaks at N%}}; `### Phase-0-granular-decomposition` 15 → 16; `### Zero-precision-items-at-auditor-review` 13 → 14 |
```

---

## §9 — Open questions for auditor at Plan v1: **0** (per OPTIONAL-Plan-v2 path candidacy)

All Q1-Q7 LOCKED per Phase 0 verdict 2026-05-23. Q7 non-blocking refinement absorbed at Plan v1 §1.1 + §2.2 (D2 stale-persists log) + §3 (A2 source-inspection extension + A3 parametrize fan-out). Plan v1 introduces ZERO new open questions. Plan v1 is RATIFIED-PENDING per auditor independent re-grep verification.

If auditor returns 0 PIs at Plan v1 review → 14th instance of `### Zero-precision-items-at-auditor-review` doctrine fires at Plan v1 surface + 7th OPTIONAL-Plan-v2 proof case unlocked + pattern-broken streak extends to 3 cycles + operational-rule extension empirically validated 3+ times → promotion candidate.

---

## §10 — 5-phase implementation plan (developer handoff; ~3-4 hours MEDIUM-band cycle)

**Phase 1 (~30 min) — Foundation (PipelineStateStore fields + config constants):**
- Edit `core/config.py`: add 3 NEW constants per §1.2 + §2.2 (`VISION_WATCHDOG_INTERVAL_SECS=5.0`, `VISION_WATCHDOG_STALE_THRESHOLD_SECS=30.0`, `VISION_WATCHDOG_RESTART_TIMEOUT_SECS=30.0`)
- Edit `core/pipeline_state_store.py`: add 2 NEW fields + 4 NEW methods per §2.3
- Run `tests/test_pipeline_state_store.py` to confirm existing tests still pass (additive change; no regression)

**Phase 2 (~45 min) — D1 heartbeat update + D2 watchdog loop:**
- Edit `pipeline.py:2401` to insert D1 heartbeat-update line per §2.1
- Add NEW `_vision_watchdog_loop` async function per §2.2 (above `_background_vision_loop` or near `_health_log_loop`)
- Add NEW `_restart_vision_task` helper per §2.4
- Add module-level `_vision_task: asyncio.Task | None = None` if not already present

**Phase 3 (~30 min) — D3 health.py extension:**
- Edit `core/health.py::HealthSnapshot` dataclass: add `vision_degraded: bool = False` field
- Edit `format_health_line`: add conditional `vision=degraded` emit when `snap.vision_degraded`
- Edit `format_health_alerts`: add actionable alert per §2.3 spec

**Phase 4 (~45 min) — D5 wiring + Phase 5 testing:**
- Edit `pipeline.py::run()` startup: add `_vision_watchdog_task = loop.create_task(_vision_watchdog_loop())` AFTER existing `_vision_task` spawn
- Edit `pipeline.py::run()` shutdown finally: add `_vision_watchdog_task` cancel BEFORE existing `_vision_task` cancel (ordering invariant per §2.5)
- Create NEW test file `tests/test_p0_r3_vision_loop_watchdog.py` with 10 anchors per §3 (A1-A10)
- Run anchor tests in isolation; confirm all 10 PASS
- Run 6 deliberate-regression checks per §2.6; confirm each fires the expected anchor
- Full suite test: confirm no regressions in `tests/test_pipeline_state_store.py` / `tests/test_health.py` / `tests/test_pipeline.py`

**Phase 5 (~30 min) — Closure narrative + 5-surface landing per §5.1:**
- Honor closure-actual count per §4 honest-count commitment table
- Apply Path C grep-verify reconciliation per `Convention-drift-on-discipline-counts` discipline before bumping doctrine counts
- Land closure narrative per §5 paste-template across CLAUDE.md header + parent + subdir complete-plan.md
- Update `to_be_checked.md` with 20th deferred-canary entry + coverage matrix row
- Architect closure-audit handoff: §8 row grep-verify reconciliation + memory file updates per locked discipline

**Expected total: ~3.0 hours** (matches MEDIUM-band cycle precedent from P0.R2 / P0.S8).

---

End of P0.R3 Plan v1.
