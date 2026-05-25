# P0.R3 — Vision-loop watchdog (heartbeat + supervised restart + degraded fallback) — Phase 0 audit

**Status:** Phase 0 audit drafted 2026-05-23. APPROVED-AT-AUDITOR-REVIEW pending.

**Pre-audit framing (verbatim from parent `c:\Users\jagan\dog-ai\complete-plan.md::P0.R3`):**

> ### P0.R3 — No watchdog on `_background_vision_loop`
>
> **Fix:** heartbeat (`time.time()` to `_vision_heartbeat`). Watchdog checks every 5 s; if older than 30 s: log; restart; mark `vision_degraded` if restart fails (keep audio alive).

---

## §1 — Grep-verified findings (DILIGENT Pass-2 per operational-rule extension banked at P0.R1 closure 2026-05-23)

**§1.1 Vision loop existence + entry point:**

`pipeline.py:2384` — `async def _background_vision_loop(camera, detector, embedder=None, temporal_buffer=None, db=None) -> None:`. Body is `while True:` infinite loop with `await loop.run_in_executor(None, camera.read)` + `detector.detect(frame)` + downstream face recognition / temporal buffer / FAISS dispatch. No exception handlers wrap the loop body. No heartbeat update at iteration start.

Spawn site (grep-verified at pipeline.py): the loop is spawned via `loop.create_task(_background_vision_loop(...))` in `pipeline.run()` startup; cancelled in the shutdown finally block.

**§1.2 Existing `_vision_last_heartbeat` (NAME-COLLISION RISK — distinct concern):**

`pipeline.py:287` — `_vision_last_heartbeat: float = 0.0  # epoch time of last [Vision] status print`. This is a module-level PRINT-throttle variable for the "Vision: persons=N face=Y" heartbeat log line (fires every 30s). It is updated at lines 2754 + 6922 when the PRINT fires — NOT when the loop iterates.

Companion: `_vision_last_heartbeat_state: str = ""` at line 288 (dedup state for the print).

**Disambiguation discipline (locked at this audit drafting):** the existing `_vision_last_heartbeat` serves PRINT-throttle, not watchdog liveness. The new watchdog heartbeat MUST use a distinct name to avoid collision. Architect lean: new field `vision_heartbeat_at: float` on `PipelineStateStore` (different namespace from the module-level print-throttle). Existing `_vision_last_heartbeat` stays untouched. See Q1 for adjudication.

**§1.3 `vision_degraded` flag — does not exist:**

Project-wide grep for `vision_degraded` (case-sensitive) returns ZERO matches across `core/*.py` + `pipeline.py` + `tests/*.py`. Completely new field; no twin-filename collision.

**§1.4 Other background loops (out-of-scope but worth surfacing for transparency):**

| Loop | Definition site | Watchdog status |
|---|---|---|
| `_background_vision_loop` | `pipeline.py:2384` | **NO watchdog (P0.R3 IN-SCOPE)** |
| `_lip_tracking_loop` | `pipeline.py:302` | NO watchdog (P0.R3.X follow-up candidate) |
| `_health_log_loop` | `pipeline.py` (via `_emit_health` background) | NO watchdog; self-supervising for health emission (watchdog-of-watchdog is design rabbit hole) |
| `_dream_loop` | `pipeline.py` | NO watchdog (lower-priority follow-up) |
| `_cloud_monitor_task` | `pipeline.py` | Self-supervising for cloud retry (no separate watchdog) |

Pre-audit framing quantifier check: pre-audit says "No watchdog on `_background_vision_loop`" — scoped to the vision loop. Grep verifies the framing is precise + scoped; quantifier is NOT overstated. NO `Pre-audit-quantifier-precision-refined-by-grep` instance to bank at this Phase 0.

**§1.5 Cross-spec interactions (grep-verified):**

- **P0.6.6 PipelineStateStore** (`core/pipeline_state_store.py`): existing home for cloud_state / pipeline_state / room lifecycle / scalar timestamps. NEW fields `vision_heartbeat_at: float` + `vision_degraded: bool` fit the existing Store-pattern + scalar-setter convention (no lock needed for single-attr writes; CPython GIL sufficient).
- **P0.R2 vision_provider_state** (`core/vision_provider_state.py`): separate concern (CUDA provider state machine). NO overlap with watchdog or degraded state. `vision_provider=cpu` health field + new `vision_degraded` health field can BOTH fire independently (CPU graceful-fallback vs hard subsystem fail).
- **Wave 5 health log** (`core/health.py`): existing `HealthSnapshot` dataclass + `format_health_alerts()` emit pattern. NEW `vision_degraded: bool = False` field on `HealthSnapshot` + conditional emit in `format_health_alerts()` when set.
- **P0.5 FAISS + faces.db atomicity**: unrelated. Restart of vision loop does NOT touch FAISS index (FAISS writes route through `add_embedding` on the main loop; watchdog only restarts the loop's task).
- **P0.X brain.db ↔ Kuzu**: unrelated.

**§1.6 Twin-filename pitfall preventive event (16th → 17th):**

Zero pre-existing P0.R3 artifacts. Phase 0 audit lands cleanly at `tests/p0_r3_vision_loop_watchdog_audit.md`. 17th preventive event honored at audit drafting (no doctrine count bump per locked enumeration rule).

---

## §2 — Decomposed D-decisions (architect leans; auditor adjudication via Q1-Q4)

### D1 — Heartbeat update in `_background_vision_loop`

**Surface:** `pipeline.py::_background_vision_loop` body. Architect lean: insert `_pipeline_state_store.set_vision_heartbeat(time.time())` (or sync-mutator equivalent) at the TOP of each `while True:` iteration, BEFORE the `camera.read` blocking call (so heartbeat reflects "loop is alive AT THE iteration boundary", not "loop completed previous iteration").

**Mechanism:** scalar-setter on PipelineStateStore (no lock per existing scalar-setter convention). Sync vs async: `set_vision_heartbeat` is a fire-and-forget `loop.create_task(...)` call per existing P0.6.6 sync-mutator-allowlist pattern. Camera.read latency is ~33ms typical; heartbeat update overhead is negligible.

**Edit site:** `pipeline.py:2401` (start of `while True:` body, before `frame = await loop.run_in_executor(None, camera.read)`).

### D2 — NEW `_vision_watchdog_loop` async function

**Surface:** NEW async function in `pipeline.py` (positioned near `_health_log_loop`; consistent layout per existing convention).

**Mechanism:** `while True: await asyncio.sleep(VISION_WATCHDOG_INTERVAL_SECS=5.0)` polling loop. Each iteration: peek `_pipeline_state_store.vision_heartbeat_at`; compare to `time.time()`; if delta > `VISION_WATCHDOG_STALE_THRESHOLD_SECS=30.0` → log stale-detection line + invoke restart helper.

**Edit sites:** NEW function body at `pipeline.py` (module-level, after `_health_log_loop`); NEW constants `VISION_WATCHDOG_INTERVAL_SECS=5.0` + `VISION_WATCHDOG_STALE_THRESHOLD_SECS=30.0` in `core/config.py`.

### D3 — `vision_degraded` flag + health alert

**Surface:** `core/pipeline_state_store.py` (NEW field + setter/peeker) + `core/health.py` (NEW `HealthSnapshot` field + conditional `format_health_alerts` emit).

**Mechanism:** `vision_degraded: bool = False` field on PipelineStateStore. Set True when restart fails (sentinel: arm by setter; clear by first successful new heartbeat). HealthSnapshot field surfaces in `format_health_line` conditional + `format_health_alerts` actionable alert with recovery instructions (similar shape to `### Architect-reads-production-code-before-sign-off` P0.B3 doctrine + P0.R2 vision_provider precedent — verbatim recovery substrings locked).

**Edit sites:** `core/pipeline_state_store.py::PipelineStateStore` (new field, setter `set_vision_degraded`, peeker `peek_vision_degraded`); `core/health.py::HealthSnapshot` (new field); `core/health.py::format_health_alerts` (new conditional emit).

### D4 — Supervised restart logic

**Surface:** restart helper INSIDE `_vision_watchdog_loop`'s stale-detection branch.

**Mechanism:**
1. Capture reference to current vision task via module-level `_vision_task: asyncio.Task | None`
2. On stale detection: `_vision_task.cancel()` + `await asyncio.gather(_vision_task, return_exceptions=True)`
3. Spawn new task: `_vision_task = asyncio.get_running_loop().create_task(_background_vision_loop(...))`
4. Capture pre-respawn heartbeat: `_prev_heartbeat = _pipeline_state_store.peek_vision_heartbeat_at()`
5. Wait up to `VISION_WATCHDOG_RESTART_TIMEOUT_SECS=30.0` for heartbeat to advance past `_prev_heartbeat`
6. If heartbeat advanced → restart succeeded → clear `vision_degraded` (if set)
7. If heartbeat did NOT advance → restart failed → set `vision_degraded = True` + log fail-loud line + continue polling (do NOT endlessly respawn — `vision_degraded` is the off-ramp; next successful heartbeat (e.g., camera reconnects) clears it naturally)

**Critical invariant — "keep audio alive":** restart-fail path MUST NOT cascade to audio/conversation loop. Audio loop runs independently; `vision_degraded` is observability + health-alert only; pipeline continues without vision recognition (falls back to voice-only routing per existing `_resolve_actual_speaker` Priority 4/5).

**Edit site:** new restart helper body in `pipeline.py::_vision_watchdog_loop`.

### D5 — Startup + shutdown wiring

**Surface:** `pipeline.py::run()` startup + shutdown finally block.

**Mechanism:** spawn `_vision_watchdog_task = loop.create_task(_vision_watchdog_loop(...))` AFTER `_vision_task` spawn (vision task must exist for watchdog to supervise). Cancel both in finally block: `_vision_watchdog_task.cancel()` BEFORE `_vision_task.cancel()` (so watchdog doesn't try to respawn vision task during shutdown).

**Edit sites:** 2 separate locations in `pipeline.py::run()` — startup spawn site + shutdown finally cancellation order.

---

## §3 — Cross-spec impact analysis (OUT-OF-SCOPE explicit)

**IN-SCOPE (P0.R3):**
- `_background_vision_loop` watchdog supervision (D1+D2+D3+D4+D5)
- `vision_degraded` health-alert observable
- Restart-failure off-ramp (no endless respawn)

**OUT-OF-SCOPE (deferred to follow-up specs or rejected):**

| Concern | Disposition |
|---|---|
| `_lip_tracking_loop` watchdog | **P0.R3.X** follow-up candidate IF lip-tracking dies silently in production |
| `_dream_loop` watchdog | **P0.R3.Y** follow-up candidate (lower priority; dream loop failure has reduced blast radius — just no memory pruning until restart) |
| `_health_log_loop` watchdog (watchdog-of-watchdog) | **REJECTED** — design rabbit hole; health log is self-supervising via its own observability |
| Audio loop watchdog | **SEPARATE SPEC** — audio loop architecture is different (sync record_until_silence + STT executor); needs distinct supervision model |
| Camera disconnect recovery beyond restart | **OUT-OF-SCOPE** — `camera.read()` already returns None on disconnect; loop continues via `await asyncio.sleep(0.05); continue`. P0.R3 watchdog catches the case where camera read HANGS indefinitely (not just returns None). |
| `vision_degraded` → brain prompt notification | **P0.R7** deferred — state-blind Ollama fallback spec covers this. Out of P0.R3 scope. |
| Forensic logging of restart event count + frequency | **P0.R3.Z** follow-up if restart-burst patterns surface in production |
| WatchdogAgent integration (`report_vision_degraded`) | **Architect lean: NOT in P0.R3** — health.py format_health_alerts is sufficient observability surface. WatchdogAgent integration is for "best-friend alert escalation"; vision_degraded is operator-actionable, not user-actionable. See Q6 if auditor disagrees. |

---

## §4 — Pre-mortem (10 failure modes + mitigation per mode)

| # | Failure mode | Mitigation |
|---|---|---|
| 1 | Camera read hangs indefinitely (USB disconnect, driver lockup) | Watchdog detects via heartbeat staleness >30s; restart cancels the hung executor task + respawns vision loop |
| 2 | `detector.detect()` raises uncaught exception → vision loop terminates | Loop exit means no more heartbeat updates → watchdog detects staleness → restart fires |
| 3 | `loop.run_in_executor(None, camera.read)` blocks on dead camera; await never resolves | Same as #1; watchdog timeout-based detection works regardless of WHERE the loop is stuck |
| 4 | Restart respawn raises immediately (e.g., camera no longer accessible) | Restart helper catches `_prev_heartbeat == new_heartbeat` after `VISION_WATCHDOG_RESTART_TIMEOUT_SECS` → marks vision_degraded + stops respawning (off-ramp) |
| 5 | Heartbeat update fires from inside executor thread (race condition) | Architect lean: heartbeat update fires on MAIN loop via `loop.create_task(...)` per existing sync-mutator-allowlist pattern. Executor thread never writes the heartbeat. Race-free. |
| 6 | Watchdog's own polling loop dies | **By design** — no watchdog-of-watchdog (rabbit hole). If watchdog dies, vision restart-supervision is gone but vision loop itself keeps running. Process supervisor (P0.R4) catches the worst case. |
| 7 | Pipeline shutdown during restart-in-progress | Shutdown finally cancels watchdog FIRST (so it doesn't try to respawn during shutdown) then vision task (D5 ordering invariant). |
| 8 | Watchdog detects staleness during a legitimate slow iteration (e.g., GPU under temporary load) | False positive cost: 1 restart (~100ms). 30s threshold is conservative; legitimate iterations complete in <50ms typical. Acceptable rate. |
| 9 | Heartbeat update overhead too frequent | Vision loop iterates ~30Hz (every ~33ms); 30Hz heartbeat updates via `loop.create_task` is fine (matches existing `set_last_face_seen` write pattern in same loop body). |
| 10 | `vision_degraded` flag stays True forever after a single restart-fail (camera permanently dead) | **By design** — the next successful heartbeat clears the flag automatically. If camera permanently dead, operator sees the health alert + can intervene. The flag is an observability signal, not a self-healing mechanism. |

---

## §5 — Multi-direction invariant trace per D-decision

**D1 invariants:**
- ↑ Upstream: `_pipeline_state_store` initialized at module-load BEFORE vision task spawns (existing P0.6.6 contract; verified by current ordering at `pipeline.py:814` instantiation).
- → Same-level: heartbeat update is fire-and-forget via `loop.create_task`; no blocking dependency on the store mutation completing before camera.read.
- ↓ Downstream: D2 watchdog reads `peek_vision_heartbeat_at()` (sync); needs the field initialized to 0.0 at store construction so first-iteration check doesn't false-positive as stale (watchdog must wait for first real heartbeat).

**D2 invariants:**
- ↑ Upstream: D1 must fire BEFORE D2's first check (otherwise watchdog sees heartbeat=0.0 → triggers restart on every boot). Mitigation: D2 polling loop sleeps `VISION_WATCHDOG_INTERVAL_SECS=5.0` BEFORE first check (gives vision loop time to fire first heartbeat).
- → Same-level: stale detection uses `time.time() - heartbeat > 30.0`; both side of comparison are monotonic-ish epoch time; no clock-jump concern.
- ↓ Downstream: stale detection triggers D4 restart helper.

**D3 invariants:**
- ↑ Upstream: `vision_degraded = False` at store construction (default).
- → Same-level: HealthSnapshot.vision_degraded reads from PipelineStateStore peeker (read-only; no mutation).
- ↓ Downstream: `format_health_alerts` emits alert ONLY when set; clear-state operators see no spurious noise.

**D4 invariants:**
- ↑ Upstream: D2 detects staleness → invokes D4 restart helper.
- → Same-level: restart respects "keep audio alive" — audio loop runs INDEPENDENTLY in `pipeline.run()` (separate task); D4 only cancels/respawns the VISION task.
- ↓ Downstream: restart success clears `vision_degraded` via first new heartbeat; restart failure sets `vision_degraded = True`.

**D5 invariants:**
- ↑ Upstream: PipelineStateStore + camera + detector must be initialized BEFORE watchdog spawn (already guaranteed by existing pipeline.run() ordering).
- → Same-level: watchdog task spawn order (after vision task) is load-bearing; shutdown cancel order (watchdog BEFORE vision) is load-bearing.
- ↓ Downstream: existing pipeline.run() shutdown handler catches all tasks via finally block.

---

## §6 — Q5 baseline estimation (architect lean: 10 anchors at exact mid; inclusive ±15% band per locked methodology)

**Architect lean: 10 anchors at exact mid 10; inclusive ±15% band [8.5, 11.5] → 9/10/11 all qualify ON-TARGET per locked methodology from P0.S5 Plan v2 §2 + P0.B5 closure narrative + P0.R2 Phase 0 auditor adjudication ratified at P0.R2 closure-audit.**

**Decomposed anchor table:**

| # | D | Anchor | Type |
|---|---|---|---|
| A1 | D1 | `_background_vision_loop` body contains heartbeat-update call (source-inspection: `set_vision_heartbeat` substring + located at iteration start before camera.read) | source |
| A2 | D2 | `_vision_watchdog_loop` exists + asyncio.sleep with VISION_WATCHDOG_INTERVAL_SECS cadence + stale check >VISION_WATCHDOG_STALE_THRESHOLD_SECS (source-inspection) | source |
| A3 | D2 | Behavioral: synthetic heartbeat staleness (heartbeat=0.0, time.time()=current) triggers restart-helper invocation | behavioral |
| A4 | D3 | PipelineStateStore has `vision_degraded` field + `set_vision_degraded` async setter + `peek_vision_degraded` sync peeker (source-inspection) | source |
| A5 | D3 | HealthSnapshot has `vision_degraded: bool = False` field (source-inspection of `core/health.py::HealthSnapshot`) | source |
| A6 | D3 | `format_health_alerts` emits actionable `Vision subsystem degraded` substring with recovery instructions when `vision_degraded == True` (source-inspection) | source |
| A7 | D4 | Behavioral: restart success — new task's first heartbeat clears `vision_degraded` (was-true → false) | behavioral |
| A8 | D4 | Behavioral: restart fail — pre/post heartbeat unchanged after VISION_WATCHDOG_RESTART_TIMEOUT_SECS → `vision_degraded` set True; audio loop intact | behavioral |
| A9 | D5 | `pipeline.py::run()` spawns watchdog task AFTER vision task (source-inspection AST line-order) | source |
| A10 | D5 | `pipeline.py::run()` shutdown finally cancels watchdog BEFORE vision task (source-inspection AST line-order) | source |

**Total: 10 logical anchors. 1:1 pytest-function-to-anchor mapping (no parametrize fan-out expected).**

**Inclusive ±15% band table (per locked methodology):**

| Closure-actual | Overage | Band | Doctrine impact |
|---|---|---|---|
| 7 | −30.0% | ≥30% FALSIFICATION | Doctrine demotes |
| 8 | −20.0% | ±15-30% SLIGHT-DRIFT-DOWN | Doctrine holds (watch trajectory) |
| **9** | **−10.0%** | **±15% ON-TARGET** | **Doctrine bumps 15 → 16** |
| **10** | **0.0%** | **±15% ON-TARGET (exact mid)** | **Doctrine bumps 15 → 16; 8+ consecutive 0% streak extends** |
| **11** | **+10.0%** | **±15% ON-TARGET** | **Doctrine bumps 15 → 16** |
| 12 | +20.0% | ±15-30% SLIGHT-DRIFT-UP | Doctrine holds (watch trajectory) |
| ≥13 | ≥+30% | FALSIFICATION | Doctrine demotes |

**Honest closure projection: closure-actual ∈ {9, 10, 11} ON-TARGET expected; 10 most likely if Plan v1 mirrors architect's anchor decomposition without consolidation.**

---

## §7 — Q5 LOCK (per inclusive ±15% locked methodology)

`### Phase-0-granular-decomposition-enables-accurate-estimates` bump expected at closure for closure-actual ∈ {9, 10, 11}; falsification clause active if closure-actual ∉ [7, 13].

---

## §8 — Open questions for auditor (architect leans explicit per locked discipline)

**Q1 — Heartbeat storage location:**
- **(a)** Add `vision_heartbeat_at: float = 0.0` field on `PipelineStateStore` with async setter `set_vision_heartbeat` + sync peeker `peek_vision_heartbeat_at` (consistent with cloud_state / pipeline_state Store-pattern precedent; satisfies P0.6 ratchet for new state)
- **(b)** Add module-level `_vision_heartbeat_at: float = 0.0` in pipeline.py (matches existing grandfathered pattern at `_vision_last_heartbeat` line 287 but violates P0.6 ratchet for new state)
- **Architect lean: (a) PipelineStateStore.** Reasoning: P0.6 ratchet forbids new module-level globals; existing module-level vision globals are grandfathered but new ones should use the Store pattern.

**Q2 — Watchdog implementation location:**
- **(a)** NEW dedicated `_vision_watchdog_loop` async function in pipeline.py (positioned next to `_health_log_loop`; consistent with existing background-loop pattern)
- **(b)** Piggyback supervision on `_health_log_loop` (already running; would need tighter polling sub-loop since `HEALTH_LOG_INTERVAL_SECS=300` > 5s watchdog interval)
- **(c)** NEW dedicated module `core/vision_watchdog.py` (parallel to `core/vision_provider_state.py` P0.R2 precedent)
- **Architect lean: (a) dedicated function in pipeline.py.** Reasoning: 5s polling cadence differs from 300s health log; coupling concerns is anti-pattern; new module is overkill for ~30 LOC.

**Q3 — `vision_degraded` flag storage location:**
- **(a)** PipelineStateStore (consistent with Q1 lean)
- **(b)** Module-level (mirrors existing `_faiss_degraded` + `_kuzu_degraded` precedent in db.py / brain_agent.py — note: those are class instance attrs, not module-level)
- **Architect lean: (a) PipelineStateStore.** Reasoning: Consistent with Q1; ratchet-aligned.

**Q4 — Restart-failure criterion:**
- **(a)** Exception-only — restart marked failed if `asyncio.create_task(...)` raises immediately
- **(b)** Heartbeat-timeout-only — restart marked failed if heartbeat doesn't advance within `VISION_WATCHDOG_RESTART_TIMEOUT_SECS=30.0` of respawn
- **(c)** Combined — exception OR timeout
- **Architect lean: (c) combined.** Reasoning: (a) misses "respawn succeeded but immediately died" cases; (b) catches both since exception → no heartbeat update either. Practical equivalent of (b) alone since exception case naturally produces zero heartbeat advance. Implementation-wise (b) is simpler.

**Q5 — Anchor count (Q5 baseline estimation):**
- **Architect lean: 10 anchors at exact mid 10; inclusive ±15% band [8.5, 11.5] → 9/10/11 all qualify ON-TARGET per locked methodology.** No precedent inconsistency to surface; locked methodology from P0.R2 closure-audit applies directly.

**Q6 — WatchdogAgent integration:**
- **(a)** Add `report_vision_degraded` method on WatchdogAgent for best-friend alerting
- **(b)** Health.py `format_health_alerts` only — operator-actionable; no best-friend alerting
- **Architect lean: (b) health.py only.** Reasoning: vision_degraded is operator-actionable (camera/driver issue); best-friend ("Jagan, your robot's camera is broken") doesn't add value vs operator-only signal. If empirical evidence shows it would help, add later.

**Q7 — Restart endless-loop protection:**
- Confirm: on restart-failure (vision_degraded set), watchdog STOPS attempting respawn. Next successful heartbeat (e.g., USB reconnects → next iteration succeeds) automatically clears vision_degraded.
- **Architect lean: confirmed semantic — restart fires ONCE per stale detection; if it fails, mark degraded + stop. Next stale-detection cycle (after vision_degraded already set) is a no-op (architect lean: log + skip respawn while degraded set; auditor adjudicate).** Mitigates the "thrash respawning a permanently-dead camera" failure mode.

---

## §9 — `### Zero-precision-items-at-auditor-review` doctrine forecast

Architect's pre-emption budget at Phase 0: 4 Q-leans (Q1-Q4) + 2 secondary Q-leans (Q6-Q7) + Q5 anchor-count lock. Auditor may ratify all leans (returns 0 PIs → doctrine fires at Phase 0 → 12 → 13) OR may surface a precision item on any of Q1-Q7. Honest forecast: Q4's combined criterion (c) might prompt auditor to pick (b) alone for simplicity → SLIGHT precision-item surface. Architect prediction: 12 → 13 at Phase 0 if all leans ratified; if Q4 simplification surfaces, cycle proceeds with corrected lean (still 0 BLOCKING PIs).

`Zero-precision-items-pre-closure-predictions-blocked` candidate stays at 1 candidate / 2 sub-events historical (P0.R2 broke the 2-consecutive-blocked pattern). Counter is at 0; P0.R3 is the FIRST cycle since the pattern broke. If P0.R3 Plan v1 also fires clean (broken pattern continues to break), discipline-stability evidence accumulates further.

---

## §10 — Architect's pre-Plan-v1 prediction (probabilistic per `Zero-precision-items-pre-closure-predictions-blocked` candidate)

Per the operational rule banked at P0.R1 closure handoff: architect's pre-Plan-v1-review prediction should be PROBABILISTIC, not CONFIDENT. Auditor's independent Pass-2 verification may surface PI architect missed at proactive Pass-2 enumeration.

**Architect prediction (probabilistic):** "Phase 0 + Plan v1 SUBMITTED for auditor cross-check; expecting clean review per operational-rule validation at P0.R2 but acknowledging non-zero PI surface possibility on any of Q1-Q7. If cycle clears clean → 7th OPTIONAL-Plan-v2 proof case + extends pattern-broken streak to 2 cycles."

---

## §11 — Files this audit touches (Phase 0 zero-production-code rule)

**Pure documentation; ZERO production code changes at Phase 0:**

- `c:\Users\jagan\dog-ai\dog-ai\tests\p0_r3_vision_loop_watchdog_audit.md` — THIS FILE (NEW)

**Phase 1+ shipping (PER PLAN v1 LOCK; NOT in Phase 0 scope):**

- `core/config.py` — D2 constants (`VISION_WATCHDOG_INTERVAL_SECS=5.0`, `VISION_WATCHDOG_STALE_THRESHOLD_SECS=30.0`, `VISION_WATCHDOG_RESTART_TIMEOUT_SECS=30.0`)
- `core/pipeline_state_store.py` — D1+D3 fields + setters/peekers (`vision_heartbeat_at`, `vision_degraded`)
- `core/health.py` — D3 HealthSnapshot field + format_health_alerts conditional emit
- `pipeline.py` — D1 heartbeat update in `_background_vision_loop` + D2 NEW `_vision_watchdog_loop` + D5 wiring in `run()` + D4 restart helper
- `tests/test_p0_r3_vision_loop_watchdog.py` — NEW file with 10 anchors (per §6 decomposed table)

---

## §12 — Verdict request

Forwarding to auditor for Phase 0 verdict. Expected verdict items:
1. Q1 adjudication (heartbeat storage location)
2. Q2 adjudication (watchdog impl location)
3. Q3 adjudication (vision_degraded storage location)
4. Q4 adjudication (restart-failure criterion)
5. Q5 anchor count lock (architect lean: 10 inclusive ±15%)
6. Q6 adjudication (WatchdogAgent integration)
7. Q7 confirmation (restart endless-loop protection semantic)
8. PI surfacing (if any) + non-blocking observations (if any)

**Banking events expected at Phase 0 verdict (closure-conditional):**
- `### Zero-precision-items-at-auditor-review` 12 → 13 IF auditor returns 0 PIs
- Twin-filename pitfall 17th preventive event ALREADY honored at audit drafting
- `Pre-audit-quantifier-precision-refined-by-grep` stays at 2 instances (pre-audit framing scoped + precise; no refinement)
- `Zero-precision-items-pre-closure-predictions-blocked` counter stays at 0 (P0.R2 broke the pattern); architect's probabilistic prediction per operational-rule extension

Architect closure commitment per `Explicit-closure-honest-count-commitment` discipline (already at 18 instances post-P0.R2): closure narrative will honor closure-actual count at closure-audit regardless of whether it lands at 10 exact mid, 9 ON-TARGET, 11 ON-TARGET, or any falsification reading. Doctrine integrity preserved across all 7 possible closure outcomes (see §6 band table).

---

End of P0.R3 Phase 0 audit.
