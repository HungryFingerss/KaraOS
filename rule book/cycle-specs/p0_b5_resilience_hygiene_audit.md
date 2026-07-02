# P0.B5 Phase 0 audit — Resilience Hygiene Bundle (Bug 7 + Bug 8 + Bug 9 + Bug 10)

**Spec ID:** P0.B5 — fifth cycle in the "Board-bug remediation" track (P0.B1 + P0.B2 + P0.B3 closed; P0.B4 SKIPPED per Jagan; P0.B1.X Bug 5 deferred to design dialogue). Per `### Twin-filename-pitfall-prevention` operational rule 4: bug-fix specs use `P0.B` prefix; sub-name disambiguates within the track.

**Twin-filename pitfall check:** no existing `p0_b5_*` files in `tests/`. Clean disambiguation. **9th preventive instance** of `### Twin-filename-pitfall-prevention` doctrine.

**Pre-audit premise (grounded in board-meeting source-of-truth `ceo-evening-2026-05-21.md` TOPIC 4 + `ceo-morning-2026-05-21.md` §2.2 + `skeptic1-2026-05-20.md` §"Architecture Vulnerabilities Found"):**

The "Resilience Hygiene Bundle" framing covers 4 LOW/MEDIUM-severity defensive-correctness bugs that share an architectural theme: **tighten existing infrastructure invariants without changing user-facing behavior.** All 4 have specific code coordinates AND board-named fix prescriptions:

- **Bug 7 (BUG-EL-1, HIGH per ceo-evening) — Test isolation failure for emit-failure counts.** `core/event_log/producer.py:527-541` — `_reset_for_tests()` resets `_queue`, `_writer_task`, `_conn`, `_drop_count`, `_recent_parent`, `_last_drop_log_ts` but NOT `_safe_emit_failure_count` (declared at line 464). Test ordering can produce false-positive failures when one test's emit-failure increment carries over to a subsequent test's assertion. Elon's defense at ceo-evening: "BUG-EL-1 is a one-liner reset."

- **Bug 8 (BUG-EL-2, HIGH per ceo-evening) — `stop_writer()` hangs on writer-task death.** `core/event_log/producer.py:504-521` — `stop_writer()` does `await _queue.join()` at line 510 WITHOUT a timeout. If the `_writer_task` has died (raised exception, exited unexpectedly) before the sentinel is put, `_queue.join()` blocks FOREVER because no consumer is calling `task_done()`. The `asyncio.wait_for(_writer_task, timeout=5.0)` at line 513 is unreachable. Elon's defense: "BUG-EL-2 is wrapping queue.join() with asyncio.wait_for."

- **Bug 9 (Finding 3, LOW per ceo-morning §2.2) — `_save_faiss()` RLock re-entrancy implicit dependency.** `core/db.py:429-431, 694-715` — `_save_faiss()` acquires `self._index_lock`; `add_embedding` (line 694) acquires `_index_lock` THEN calls `self._save_faiss()` (line 715). Correctness depends on `_index_lock = threading.RLock()` at line 101. If ever changed to `threading.Lock()`, system deadlocks under write load. Not documented at call sites. Fix direction: extract `_save_faiss_unlocked()` to make invariant explicit.

- **Bug 10 (V5, JETSON-FORWARD per skeptic1-2026-05-20 §"Architecture Vulnerabilities") — `state.json` race relies on CPython GIL-atomic `STORE_NAME`.** `core/state.py:30-31` — `_persistent = {**_persistent, key: value}` atomic-replace assumes CPython STORE_NAME atomicity. Docstring at lines 24-28 explicitly acknowledges: "If runtime writers are added, add `threading.Lock`." On Jetson with a GIL-free Python 3.13 build (a production scenario per skeptic1-2026-05-20 V5), this assumption breaks. P0.11 acknowledged the CPython dependency; P0.B5 closes it pre-emptively.

**10-bug enumeration (locked at P0.B5 Phase 0 baseline grep 2026-05-21):**

| # | Name | Spec | Status |
|---|---|---|---|
| 1 | FAISS async rebuild (Finding 1) | P0.B2 | CLOSED |
| 2 | Documentation-vs-reality drift at `test_faiss_atomicity_invariants.py:29-32` | P0.B2 | CLOSED |
| 3 | Kuzu schema upgrade ordering (Finding 2) | P0.B3 | CLOSED |
| 4 | VoiceEvidence not frozen (BUG-SS-1) | P0.B1 | CLOSED |
| 5 | Reconciler `_p4_single_segment_mismatch` "dead" (BUG-REC-1) | P0.B1.X | DEFERRED (design dialogue pending Jagan + reviewer) |
| 6 | Together.ai SPOF across knowledge pipeline (Attack 6) | P0.B4 | SKIPPED per Jagan 2026-05-21 (deferred to user-defined trigger) |
| **7** | **BUG-EL-1 — test isolation `_safe_emit_failure_count` not reset** | **P0.B5** | **OPEN — THIS SPEC** |
| **8** | **BUG-EL-2 — `stop_writer()` hangs on writer-task death** | **P0.B5** | **OPEN — THIS SPEC** |
| **9** | **Finding 3 — `_save_faiss()` RLock re-entrancy implicit** | **P0.B5** | **OPEN — THIS SPEC** |
| **10** | **V5 — `state.json` GIL-dependent race** | **P0.B5** | **OPEN — THIS SPEC** |

**Cadence prediction (initial):** 4 D-decisions / 4 subsystems / LOW per-D fan-out → **v1 → v2 floor** (closure-template lock often justifies v2 even for clean v1 absorption per P0.B1 / P0.B2 precedent). OPTIONAL-Plan-v2 path possible (3rd proof case after P0.S3 + P0.B3) if Plan v1 absorbs cleanly.

---

## §1. Grep-verified surface (Pass-1)

### §1.1 Bug 7 — BUG-EL-1 test isolation `_safe_emit_failure_count` not reset

**Production surface:** `core/event_log/producer.py:527-541`.

```python
527:def _reset_for_tests() -> None:
528:    """Test-mode reset. Closes DB + clears module state."""
529:    global _queue, _writer_task, _conn, _drop_count, _recent_parent, _last_drop_log_ts
530:    if _conn is not None:
531:        try:
532:            _conn.close()
533:        except Exception:                          # pragma: no cover
534:            # CLEANUP: best-effort close.
535:            pass
536:    _queue = None
537:    _writer_task = None
538:    _conn = None
539:    _drop_count = 0
540:    _recent_parent = {}
541:    _last_drop_log_ts = 0.0
```

**The bug:** `_safe_emit_failure_count` is declared at line 464 as a module-level counter. `_reset_for_tests()` resets 6 other module-level globals but MISSES `_safe_emit_failure_count`. Test ordering hazard: Test A triggers a safe_emit failure → counter goes `0 → 1`. Test B runs `_reset_for_tests()` (which doesn't reset the counter) → counter stays at 1. Test B asserts `get_safe_emit_failure_count() == 0` → FALSE-POSITIVE failure.

**Fix:** add `_safe_emit_failure_count` to the `global` declaration on line 529 + add `_safe_emit_failure_count = 0` reset line at the bottom. One-line addition + one-word `global` extension.

### §1.2 Bug 8 — BUG-EL-2 `stop_writer()` hangs on writer-task death

**Production surface:** `core/event_log/producer.py:504-521`.

```python
504:async def stop_writer() -> None:
505:    """Drain the queue + shutdown. Called during graceful pipeline exit."""
506:    global _queue, _writer_task, _conn, _recent_parent
507:    if _queue is not None:
508:        # Sentinel: None envelope tells _writer_loop to exit.
509:        await _queue.put(None)
510:        await _queue.join()                                   # ← UNBOUNDED await; HANGS if writer dead
511:    if _writer_task is not None:
512:        try:
513:            await asyncio.wait_for(_writer_task, timeout=5.0)
514:        except asyncio.TimeoutError:                       # pragma: no cover
515:            _writer_task.cancel()
516:    if _conn is not None:
517:        _conn.close()
518:    _queue = None
519:    _writer_task = None
520:    _conn = None
521:    _recent_parent = {}
```

**The bug:** `_queue.join()` at line 510 blocks until ALL items in the queue (including the sentinel) have `task_done()` called on them by a consumer. The sole consumer is `_writer_task`. If `_writer_task` has DIED (raised exception, exited unexpectedly) BEFORE we put the sentinel at line 509, then:
- Step 1 puts the sentinel into the queue.
- Step 2 `await _queue.join()` HANGS FOREVER because nobody is calling `task_done()`.
- Step 3 (`wait_for` at line 513) is unreachable.

**Fix:** wrap `_queue.join()` with `asyncio.wait_for` + timeout (mirror line 513 shape):

```python
try:
    await asyncio.wait_for(_queue.join(), timeout=5.0)
except asyncio.TimeoutError:
    # writer task likely dead; proceed to cleanup; the wait_for(_writer_task, ...)
    # at line 513 will surface the dead task via its own timeout/cancel path.
    print(f"[EventLog] WARN: stop_writer queue.join() timed out — writer task likely dead, proceeding to cleanup")
```

Plus defense-in-depth: ALSO check `_writer_task.done()` BEFORE the queue.join() — if the task is already done before we put the sentinel, skip the join entirely.

### §1.3 Bug 9 — Finding 3 `_save_faiss()` RLock re-entrancy implicit

**Production surface:** `core/db.py:101` (lock declaration) + `core/db.py:429-431` (`_save_faiss`) + `core/db.py:694-715` (`add_embedding`, the canonical re-entrant caller).

```python
101: self._index_lock = threading.RLock()                       # ← RLock (re-entrant) — load-bearing
429: def _save_faiss(self):
430:     with self._index_lock:                                  # ← acquires _index_lock
431:         faiss.write_index(self.index, str(self._faiss_path))

694: with self._index_lock:                                     # ← acquires _index_lock at add_embedding outer
695:     faiss_idx = self.index.ntotal
...
715:     self._save_faiss()                                      # ← RE-ENTRANT acquisition (only OK because RLock)
```

**The bug:** Correctness of `add_embedding` (and 6+ other call sites at lines 694/730/789/870/921/1013 per grep) depends on `_index_lock` being `threading.RLock()` instead of `threading.Lock()`. If a future refactor changes this to `Lock()` (e.g. "performance optimization — `Lock` is faster than `RLock`"), the system deadlocks on every `add_embedding` call. Nothing at the call sites documents this dependency.

**Fix (per ceo-morning §2.2 prescription):** extract `_save_faiss_unlocked()` to make the invariant explicit:

```python
def _save_faiss_unlocked(self) -> None:
    """Write FAISS index to disk. MUST be called WITH _index_lock already held.

    Extracted from _save_faiss() to make the lock-held precondition explicit
    at every internal call site (P0.B5 Bug 9 / ceo-morning Finding 3 — was
    implicitly relying on RLock re-entrancy; explicit naming prevents future
    refactor from breaking the contract).
    """
    faiss.write_index(self.index, str(self._faiss_path))

def _save_faiss(self) -> None:
    """Public-facing save. Acquires _index_lock + calls _save_faiss_unlocked."""
    with self._index_lock:
        self._save_faiss_unlocked()
```

Internal callers that ALREADY hold `_index_lock` (e.g. line 715) switch to `self._save_faiss_unlocked()`. Callers that DO NOT hold the lock keep using `self._save_faiss()`. The invariant is now explicit at every call site.

**Pass-2 grep needed at Plan v1:** enumerate every `self._save_faiss()` call site in `core/db.py` + determine which are inside `with self._index_lock:` blocks vs which are standalone. Migrate the former to `_save_faiss_unlocked()`.

### §1.4 Bug 10 — V5 `state.json` GIL-dependent race

**Production surface:** `core/state.py:13-31`.

```python
13: _persistent: dict = {}  # fields merged into every write() — set once at startup

16: def set_persistent(key: str, value) -> None:
...
24:     NOTE: This protects readers from torn iteration. It does NOT protect
25:     against concurrent writers losing updates (RMW race — multiple
26:     writers can both load the old dict, both build new dicts, and the
27:     second STORE wins). Production has 1 writer at startup, so RMW is
28:     not a concern. If runtime writers are added, add `threading.Lock`.
29:     """
30:     global _persistent
31:     _persistent = {**_persistent, key: value}
```

**The bug:** The atomic-replace pattern at line 31 relies on CPython's `STORE_NAME` being atomic via the Global Interpreter Lock. This holds on standard CPython 3.x. **On free-threaded Python 3.13+ builds (`--disable-gil`), the assumption breaks.** Jetson production deployment targets a Linux build; the Jetson NX/Orin Python build may eventually be GIL-free as the broader ecosystem migrates.

The docstring acknowledges the limitation AND prescribes the fix: "If runtime writers are added, add `threading.Lock`."

**Fix:** add explicit `threading.Lock` to `set_persistent` (pre-emptive defensive hardening). One module-level lock; one `with` block around the atomic-replace. Production behavior unchanged on CPython (lock adds ~100ns); Jetson GIL-free safe.

```python
_persistent: dict = {}
_persistent_lock = threading.Lock()  # P0.B5 Bug 10 / V5 — explicit lock for GIL-free Python forward-compat

def set_persistent(key: str, value) -> None:
    """[docstring updated to remove the "If runtime writers are added" disclaimer]"""
    global _persistent
    with _persistent_lock:
        _persistent = {**_persistent, key: value}
```

The docstring also needs an update: remove the "If runtime writers are added, add `threading.Lock`" line (closed by this fix) + replace with "Lock added preemptively for GIL-free Python forward-compatibility (P0.B5 Bug 10)."

---

## §2. Phase 0 verdict + D-decisions to lock

### §2.1 Phase 0 verdict: PRE-AUDIT PREMISE FULLY ON-TARGET

All 4 bugs verified at exact code coordinates against board-meeting source-of-truth + production-code grep:
- Bug 7 → `core/event_log/producer.py:527-541` ✓
- Bug 8 → `core/event_log/producer.py:504-521` ✓
- Bug 9 → `core/db.py:101, 429-431, 694-715` (+ 6 other RLock-dependent call sites) ✓
- Bug 10 → `core/state.py:13-31` ✓

No wrong-premise refinement needed. `### Phase-0-catches-wrong-premise` NOT activated this cycle (stays at 7 instances). Per `### Phase-0-granular-decomposition-enables-accurate-estimates` doctrine — 4 D-decisions with named edit sites at file:line granularity, estimate range should be narrow.

### §2.2 D-decisions to lock at Plan v1

**D1 (Bug 7, LOW — test infrastructure):** `_reset_for_tests()` at `core/event_log/producer.py:527-541` extended to reset `_safe_emit_failure_count` to 0. Add to `global` declaration (line 529) + add reset line near other counter resets (after line 539).

**D2 (Bug 8, MEDIUM — graceful shutdown correctness):** `stop_writer()` at `core/event_log/producer.py:504-521`:
- Add early-exit if `_writer_task` is already done before putting sentinel (don't put sentinel into queue that no one will consume).
- Wrap `await _queue.join()` (line 510) with `asyncio.wait_for(..., timeout=5.0)` + `except asyncio.TimeoutError:` log + proceed to cleanup.
- The existing `asyncio.wait_for(_writer_task, timeout=5.0)` at line 513 stays (handles the cancel-the-task case).

**D3 (Bug 9, LOW — structural-invariant documentation):** `core/db.py:429-431` `_save_faiss()` split into:
- `_save_faiss_unlocked()` (NEW) — pure write, no lock acquisition, docstring names "MUST be called WITH _index_lock already held."
- `_save_faiss()` (refactored) — thin wrapper that acquires `_index_lock` + calls `_save_faiss_unlocked()`.
- Internal callers ALREADY inside `with self._index_lock:` blocks switch to `self._save_faiss_unlocked()`. Pass-2 grep at Plan v1 enumerates them.

**D4 (Bug 10, JETSON-FORWARD — GIL-free safety):** `core/state.py`:
- Add `import threading` at top.
- Add `_persistent_lock = threading.Lock()` at module scope after `_persistent: dict = {}`.
- Wrap `_persistent = {**_persistent, key: value}` (line 31) with `with _persistent_lock:`.
- Update docstring to remove the "If runtime writers are added" disclaimer; replace with "Lock added preemptively for GIL-free Python forward-compatibility (P0.B5 Bug 10)."

### §2.3 D-decisions deliberately NOT in scope

- **NOT in scope:** Refactoring `_index_lock` from RLock to Lock. Bug 9 is about making the RLock dependency explicit, NOT about changing it.
- **NOT in scope:** Adding new event_log emit-failure observability surfaces. Bug 7 is test-infrastructure-only.
- **NOT in scope:** P0.0.7 event log writer-task health observable in HealthSnapshot. The `event_log_emit_failures` counter is already exposed at HealthSnapshot per P0.0.7 D8.1; Bug 8's fix doesn't expand this surface.
- **NOT in scope:** Stress-testing the GIL-free Python 3.13 path under load. Bug 10's fix is defensive hardening for forward-compat; actual Jetson canary stress-testing waits for hardware deployment.
- **NOT in scope:** Adjacent V5-like races (`_disputed_persons` set mutation in BrainOrchestrator, etc.). Scope limited to `state.py::_persistent` which the board explicitly named.

---

## §3. Pre-mortem (10 failure modes — strict-mode floor 5-10)

### §3.1 — D1 reset addition introduces test-ordering side effect

**Risk:** Adding `_safe_emit_failure_count = 0` to `_reset_for_tests()` could expose previously-passing-by-accident tests that depended on the carry-over.

**Mitigation:** Plan v1 §1 Pass-2 grep enumerates every test that reads `get_safe_emit_failure_count()` (or `_safe_emit_failure_count` directly). Each is reviewed for "was this passing on purpose or by accident?" Convert any false-passing tests to explicit-seed pattern (test sets counter to a known value before assertion).

### §3.2 — D2 timeout in `stop_writer` could swallow real bugs

**Risk:** Adding `asyncio.wait_for(_queue.join(), timeout=5.0)` could hide real issues (e.g. writer task is slow but not dead — legitimately processing a backlog). Forcing cleanup at 5s might lose envelopes that would have flushed at 6s.

**Mitigation:** 5s is the same timeout already used at line 513 for `_writer_task` shutdown. Mirroring the existing budget keeps the discipline consistent. The TimeoutError path emits a `[EventLog] WARN: stop_writer queue.join() timed out` log line so the deviation is operator-visible. Cleanup still proceeds. Alternative: configurable via `EVENT_LOG_STOP_TIMEOUT_SECS` in `core/config.py` if production canary shows 5s is too tight.

### §3.3 — D3 `_save_faiss_unlocked()` extraction misses a call site

**Risk:** Pass-1 grep showed 7+ `with self._index_lock:` blocks across `core/db.py`. Pass-2 grep at Plan v1 might miss one. If a call site that already holds the lock still uses `self._save_faiss()` (the lock-acquiring version), it re-enters the lock (correct under RLock) — no immediate bug, but it defeats the discipline.

**Mitigation:** Plan v1 enumerates every `self._save_faiss()` call site + classifies each as (a) inside `with self._index_lock:` block — must migrate to `_save_faiss_unlocked()`, or (b) standalone — keeps `self._save_faiss()`. Defense-in-depth: AST forward-property test that scans for `self._save_faiss()` inside `with self._index_lock:` AST blocks and FAILS if any are found (every call site inside a lock block must use the unlocked variant). Same shape as P0.B2 D4 AST forward-property test.

### §3.4 — D4 `_persistent_lock` introduces re-entrant lock-acquisition risk

**Risk:** If `set_persistent()` is ever called from inside another `_persistent_lock`-holding code path (e.g. a hook that fires during the atomic-replace), the new lock causes deadlock under `threading.Lock` (not re-entrant).

**Mitigation:** Pass-2 grep enumerates every `set_persistent` call site to verify no re-entrant call chains exist. Today's production has 1 caller (`pipeline.py:6264` at startup). If Plan v1 finds re-entrant risk → use `threading.RLock` instead. Architect lean: `threading.Lock` is sufficient given current single-caller; document the assumption.

### §3.5 — D4 docstring update could cause CI regression

**Risk:** Existing tests may grep the docstring text "If runtime writers are added, add `threading.Lock`" as a structural assertion (testing the documented limitation). Removing the disclaimer breaks the assertion.

**Mitigation:** Pass-2 grep at Plan v1 enumerates every test that reads `set_persistent` docstring or sources `core/state.py`. None expected based on Pass-1 sample, but verify.

### §3.6 — D2 writer-task-already-done check could mask intermittent failures

**Risk:** If `_writer_task.done()` returns True before we put the sentinel, the early-exit skips queue draining. Any envelopes already in the queue are lost on shutdown.

**Mitigation:** This is correct behavior — if the writer is dead, the queue's contents are unreachable regardless; draining is impossible. The fix doesn't make things worse than the existing 5s `wait_for` already does. Log line surfaces the case for operator triage: `[EventLog] WARN: stop_writer found writer task already done — skipping queue drain (N envelopes lost)`.

### §3.7 — D3 introduces signature confusion between `_save_faiss` and `_save_faiss_unlocked`

**Risk:** Future maintainers may not understand which to call. The naming convention (`_unlocked` suffix) is the discipline, but it's the developer's first encounter with the pattern in this codebase.

**Mitigation:** Both functions get explicit docstrings naming the lock-precondition contract. The AST forward-property test from §3.3 mitigation is the structural backstop — wrong-call-site detection is automated. Future P1.A pipeline.py decomposition spec could establish a project-wide `_unlocked` naming convention if this pattern repeats.

### §3.8 — D4 lock acquisition adds latency to every `set_persistent` call

**Risk:** `threading.Lock` acquisition is ~100ns on CPython. Current production has 1 caller at startup; no hot path. If runtime writers are added later (e.g. dashboard-trigger refresh), the lock adds per-call overhead.

**Mitigation:** Negligible at 100ns. Future profiling can re-evaluate if `set_persistent` becomes a hot path. Document the acceptance: "Lock overhead ~100ns is acceptable given the alternative (GIL-free Python correctness)."

### §3.9 — Plan v1 Pass-2 grep undercount (`Plan-v1-Pass-2-grep-undercount` informal observation, 1 instance at P0.B3)

**Risk:** Per `feedback_plan_v1_pass2_grep_undercount.md` (banked at P0.B3 closure 2026-05-21), architect Pass-2 grep can undercount affected files. P0.B5 has 4 distinct subsystems; the risk is higher than single-subsystem cycles.

**Mitigation:** Plan v1 §1 uses multi-pattern Pass-2 grep per the observation's operational rule (tests/test_*event_log*.py + tests/test_event_log_*.py + tests/*event*.py for D1/D2; tests/test_*faiss*.py + tests/test_*db*.py + tests/test_*atomicity*.py for D3; tests/test_state*.py + tests/test_*persistent*.py for D4). Phase 4 developer re-grep is the natural backstop.

### §3.10 — Multi-subsystem cadence ambiguity (SMALL vs MEDIUM band)

**Risk:** 4 D-decisions across 4 subsystems could be SMALL-band (each D is 1-line / ~10-line fix) OR MEDIUM-band (cumulative test+source surface is larger than P0.B1 / P0.B3 SMALL-band precedents). The cadence band determines Plan v2 expectations.

**Mitigation:** Q5 estimate at §7 anchors the band. If Plan v1 anchor forecast lands at 6-8 → SMALL-band; if at 10-12 → MEDIUM-band. Cadence is band-conditional. Architect lean at Phase 0: MEDIUM-band (8-10 anchors) — 4 D-decisions × 1-2 anchors per D + 1-2 cross-cutting AST forward-property tests.

---

## §4. Multi-direction invariant trace per D-decision

### §4.1 D1 (BUG-EL-1 reset addition)

- **Forward:** test suite consumers of `get_safe_emit_failure_count()` — Pass-2 grep at Plan v1. Each consumer now sees clean state at test start; previously may have seen carry-over.
- **Backward:** sole writer is `safe_emit_sync()` at `core/event_log/producer.py:453-454` (`_safe_emit_failure_count += 1` on swallowed exception). No other writers.
- **Sideways:** other module-level counters that follow the same pattern: `_drop_count` (already reset), `_last_drop_log_ts` (already reset). D1 brings `_safe_emit_failure_count` into compliance with the documented reset convention.
- **Lifecycle:** counter is process-lifetime cumulative; production never resets it (production health uses it as observability signal at HealthSnapshot). `_reset_for_tests` is test-only. D1 changes nothing in production semantics.

### §4.2 D2 (BUG-EL-2 stop_writer timeout)

- **Forward:** sole caller is graceful pipeline shutdown path (`pipeline.py`). D2 fix means shutdown can no longer hang on writer-task death; cleanup proceeds.
- **Backward:** the queue + writer-task lifecycle is owned by `start_writer()` + `stop_writer()` at lines 477-521. No external state machinery.
- **Sideways:** other async-shutdown paths in the codebase (e.g. dream-loop shutdown, cloud-monitor shutdown). Pattern is independent; D2 doesn't generalize to those.
- **Lifecycle:** event_log subsystem startup-shutdown cycle. D2 hardens the SHUTDOWN side; startup is unchanged.

### §4.3 D3 (Finding 3 `_save_faiss_unlocked` extraction)

- **Forward:** all 7+ existing `self._save_faiss()` call sites in `core/db.py`. Pass-2 grep classifies each as locked-context or standalone. Locked-context callers migrate; standalone callers unchanged.
- **Backward:** `_index_lock` declaration at line 101. D3 doesn't touch the lock itself; only documents the contract at the call sites.
- **Sideways:** other re-entrant-lock-dependent functions in `core/db.py`. Pass-2 grep enumerates. If similar implicit-RLock-dependency patterns exist elsewhere, document via comment or follow-up spec (NOT in P0.B5 scope).
- **Lifecycle:** FAISS index persistence layer. D3 strengthens structural correctness; no user-facing behavior change.

### §4.4 D4 (V5 `_persistent_lock`)

- **Forward:** consumers of `_persistent` dict (read sites): `write()` at line 52 spreads `**_persistent` into the state JSON. Reads are unaffected by D4 (no lock acquisition on reads — that would defeat the GIL-atomic-snapshot pattern that already works).
- **Backward:** sole writer is `set_persistent()` at line 16. D4 wraps its mutation with the new lock.
- **Sideways:** other module-level dicts with similar atomic-replace patterns. Grep `_persistent` and `STORE_NAME` in `core/*.py` to enumerate analog cases. P0.B5 scope is `core/state.py::_persistent` only; analog cases bookmark for future spec if surfaced.
- **Lifecycle:** dashboard-pipeline IPC. D4 strengthens cross-thread / cross-GIL-mode correctness. Production CPython unchanged in behavior; Jetson GIL-free build correctness restored.

---

## §5. Cross-spec impact analysis

- **P0.0.7 (event log subsystem):** D1 + D2 touch event_log producer module. D1 closes a test-isolation bug surfaced during P0.0.7 dev or later. D2 strengthens the shutdown path P0.0.7 established. P0.0.7's HealthSnapshot integration (`event_log_drops` + `event_log_emit_failures`) is UNCHANGED by D1+D2.
- **P0.5 (FAISS atomicity):** D3 strengthens the structural invariants P0.5 established for FAISS+SQLite atomicity. Pre-D3, the RLock dependency was implicit; post-D3, it's explicit at every call site. P0.5's sentinel discipline is unchanged.
- **P0.11 (`_persistent` dict race):** P0.11 acknowledged the CPython-GIL-atomic dependency at the same line. D4 closes the gap P0.11 explicitly deferred ("If runtime writers are added, add threading.Lock"). D4 is the upgrade P0.11 anticipated.
- **P0.B1 + P0.B2 + P0.B3 (prior Board-bug cycles):** no interaction. Different subsystems.
- **P0.B4 (Pluggable Fallback, SKIPPED per Jagan):** no interaction with P0.B5.
- **P0.S1 (anti-spoof on every face match, in-flight):** no interaction with P0.B5.
- **P1.A (pipeline.py decomposition, future):** D3's `_unlocked` suffix convention COULD inform a future project-wide naming convention if P1.A surfaces similar implicit-lock-dependency patterns in pipeline.py. Bookmark only; NOT in P0.B5 scope.

---

## §6. Cadence prediction

**MEDIUM-band (4 D-decisions, low per-D fan-out, 4 subsystems, 8-10 logical anchors)** → **v1 → v2 floor likely; OPTIONAL-Plan-v2 path possible if Plan v1 absorbs cleanly** (3rd proof case after P0.S3 + P0.B3).

Rationale: 4 D-decisions is more than P0.B1's 1 and P0.B3's 2. But each D-decision is structurally simple (1-line / ~10-line fix). Cumulative anchor count is the discriminator — if Plan v1 lands at 6-8 anchors, treat as SMALL-band v1-only (3rd OPTIONAL-Plan-v2 proof case); if at 10-12 anchors, treat as MEDIUM-band v1 → v2 floor for explicit closure-template lock per P0.B1 / P0.B2 precedent.

If Plan v1 surfaces ≥1 unresolved precision item (e.g. Pass-2 grep enumerates more `self._save_faiss()` call sites than anticipated, or D4 lock-acquisition strategy needs refinement) → escalate to Plan v2.

---

## §7. Q5 baseline estimation

**Per `### Phase-0-granular-decomposition-enables-accurate-estimates` doctrine (9 supporting instances at P0.B3 closure):**

Estimate range: **6-12 logical anchors**, mid-range **8-9**.

Breakdown:
- **D1 (1-2 anchors):** source-inspection that `_safe_emit_failure_count` is in `_reset_for_tests` globals + behavioral test that 2 consecutive `safe_emit_sync` failures across `_reset_for_tests` boundary observe correct counter.
- **D2 (2-3 anchors):** source-inspection that `_queue.join()` is wrapped in `asyncio.wait_for` + behavioral test that `stop_writer` with dead `_writer_task` completes within timeout + log-line substring check.
- **D3 (3-4 anchors):** source-inspection that `_save_faiss_unlocked` exists with NO `with self._index_lock:` in body + source-inspection that `_save_faiss` thin-wraps with lock + AST forward-property test that no `self._save_faiss()` call site sits inside `with self._index_lock:` block (Pass-2-grep-enumerated migration verification) + behavioral test that nested-RLock semantics still work for legacy `_save_faiss()` callers.
- **D4 (2-3 anchors):** source-inspection that `_persistent_lock = threading.Lock()` exists + source-inspection that `set_persistent` body wraps mutation in `with _persistent_lock:` + concurrent-writer behavioral test (2 threads × 100 `set_persistent` calls; final dict has all 200 keys correctly).

Plan v1 will lock anchor count + auditor confirms / refines mid-range estimate. ON-TARGET band per Plan v3 §1.1 corrected band table (locked at P0.B2 closure) = ±15% of mid-range → ON-TARGET if closure lands in [7, 8, 9] (using mid 8) or [8, 9, 10] (using mid 9).

---

## §8. Open questions for auditor (4 items)

**Q1 — Should D3's `_save_faiss_unlocked()` extraction also cover other re-entrant-RLock patterns in `core/db.py`?**

Architect lean: NO. Pass-1 grep showed 7+ `with self._index_lock:` blocks in `core/db.py`. Some may have analogous implicit-RLock-dependency patterns (e.g. an `_index_lock`-holding method calls another `_index_lock`-acquiring method). Refactoring all of them is broader scope than Bug 9's specific named coordinates. Plan v1 limits to `_save_faiss()` + `_save_faiss_unlocked()`; analog cases bookmark for future P0.B5.X follow-up if pattern accumulates.

**Q2 — Should D4 use `threading.Lock` or `threading.RLock`?**

Architect lean: `threading.Lock`. Pass-2 grep at Plan v1 verifies no re-entrant call chains exist; today's single startup-time caller is non-re-entrant. `Lock` is cheaper (slightly faster acquisition, smaller object) and signals "no re-entrancy expected." If Plan v1 surfaces ANY re-entrant call chain, escalate to `RLock`. P0.B5 ships with `Lock`; future runtime-writer additions (if introduced) must re-verify.

**Q3 — Should D2's TimeoutError log be a `[Health-Alert]` (per the `kuzu_degraded` precedent at P0.B3 D2) or just a stderr WARN line?**

Architect lean: just WARN. Bug 8 is a SHUTDOWN-path bug — by definition, the pipeline is exiting when this fires. HealthSnapshot infrastructure is no longer being emitted at that point. The WARN line is the right operator-visibility surface for the shutdown context.

**Q4 — Should P0.B5 closure narrative explicitly enumerate the 10-bug list from §"Pre-audit premise" + status of each as a permanent reference doc?**

Architect lean: YES. The 10-bug enumeration in §"Pre-audit premise" is the first time the full list has been written down in a single place (it was implicit in prior cycle narratives). Landing it in the P0.B5 closure narrative + parent complete-plan.md gives future maintainers a single source-of-truth for the Board-bug remediation track. Plus: P0.B6 closure (Cycle 6) will reference the same list to verify 100% completion.

---

## §9. Discipline counts at Phase 0 close

**Per auditor's Post-P0.B3 ratified baseline + Phase 0 artifact (+1):**

| Discipline | Post-P0.B3 baseline | Post-P0.B5 Phase 0 |
|---|---|---|
| Spec-first review cycle | 49 | **50** ✓ (Phase 0 artifact +1) |
| Strict-industry-standard mode | 39 + 11 closures | **40 applications + 11 closures** ✓ |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 9 supporting | stays 9 (closure pending) |
| `### Phase-0-catches-wrong-premise` | 7 | stays 7 (premise fully on-target this cycle — board-meeting source-of-truth grep-verified 4-bug surface) |
| `### Twin-filename-pitfall-prevention` (elevated doctrine) | 7 + 4 op rules | stays 7 (preventive at audit drafting; clean disambiguation against zero pre-existing P0.B5 artifacts; 9th preventive instance counted at architect-side but doctrine instance count holds per the instance-enumeration rule) |
| `### Grep-baseline-before-drafting` (elevated doctrine, P0.B3) | 6 instances | **7 instances** ✓ (Phase 0 drafted from Post-P0.B3 ratified counts; preventive application) |
| Deferred-canary | 11th application | **12th application** ✓ (P0.B5 Phase 0 banks at to_be_checked.md eventually) |
| Auditor-Q5-estimates-trail-grep | 15 banked closures | stays 15 (closure pending) |
| Cross-cycle-handoff transparency precedent | 12 successful | **13 successful** ✓ (architect honored P0.B3 closure verdict's ratified counts at P0.B5 baseline grep) |
| Architect-reads-production-code-before-sign-off | 8 banked | stays 8 (closure-audit pending) |
| Sub-pattern A (Phase-0-catches-wrong-premise) | 7 | stays 7 |
| Spec-time grep-verification | 16 | **17** ✓ (Phase 0 §1 Pass-1 grep enumerated 4 production sites + 6 helper-site callers for D3) |
| Discipline-count-bump-needs-explicit-justification | 10 preventive | stays 10 |
| Convention-drift-on-discipline-counts (parent) | 4 | stays 4 |
| Per-artifact-arithmetic-drift-survives-grep-baseline (child) | 1 | stays 1 |
| Explicit-closure-honest-count-commitment | 6 | stays 6 (commitment-making pending Plan v1 §6) |
| Auditor-catches-Q5-math-at-plan-review | 2 | stays 2 |
| Phase-0-zero-precision-items-at-auditor-review (informal) | 1 | stays 1 (Plan v1 audit pending; if auditor returns 0 precision items at Phase 0 → 2nd instance bumps to candidacy) |
| Plan-v1-Pass-2-grep-undercount (informal) | 1 | stays 1 (Plan v1 §1 Pass-2 grep at next artifact; risk of recurrence flagged per §3.9 pre-mortem) |
| Bug-fix-cycles-surface-discipline-edges (informal) | 1 | stays 1 (cycle still in flight) |
| HEAVY-band cadence (working hypothesis) | 2 (P0.S5 + P0.B2) | stays 2 (P0.B5 is MEDIUM-band; does NOT add evidence either way) |
| OPTIONAL-Plan-v2 proof case | 2 (P0.S3 + P0.B3) | stays 2 (would bump to 3 if Plan v1 absorbs cleanly + closure event ratifies) |

**Phase 0 commitments banked for closure-audit:**

1. Spec-first review cycle expected at closure: 50 (Phase 0) + 1 (Plan v1) + (+1 if Plan v2) + 1 (closure) per +1-per-artifact convention.
2. Q5 estimate range LOCKED at 6-12 anchors, mid 8-9. Closure-actual reading triggers band-table disposition per P0.B2 / P0.B3 precedent.
3. `### Phase-0-catches-wrong-premise` NOT activated this cycle (premise verified ON-TARGET via board-meeting + grep cross-reference at §1).
4. Cadence: MEDIUM-band; v1 → v2 floor likely; OPTIONAL-Plan-v2 path possible (3rd proof case candidate).
5. 10-bug enumeration locked at §"Pre-audit premise" — to be landed in closure narrative per Q4 architect lean.

---

## §10. Open invariants for Plan v1 to enumerate

1. **D1 reset-completeness invariant** — `_reset_for_tests` resets ALL `_*_count` / `_*_log_ts` / `_recent_*` module-level globals declared in the file. Source-inspection test enumerates module globals + verifies each appears in the reset function.

2. **D2 timeout invariant** — `stop_writer()` body contains exactly TWO `asyncio.wait_for` calls (one for `_queue.join()`, one for `_writer_task`). Source-inspection test verifies both timeout values are bounded (NOT unbounded `await`).

3. **D3 ordering invariant (AST forward-property)** — NO `self._save_faiss()` call site appears inside `with self._index_lock:` block. Every call site inside a lock block must use `self._save_faiss_unlocked()`. AST walk identifies all `with self._index_lock:` `With` nodes + checks descendants for `Call(Attribute(self, "_save_faiss"))`.

4. **D3 unlocked-helper contract invariant** — `_save_faiss_unlocked()` body MUST NOT contain `with self._index_lock:` (it's the lock-not-acquiring variant). Source-inspection test.

5. **D4 lock-acquisition invariant** — `set_persistent()` body wraps the `_persistent = {**_persistent, key: value}` line in `with _persistent_lock:`. Source-inspection test.

6. **D4 concurrent-writer invariant (behavioral)** — 2 threads × N `set_persistent` calls produce a final dict containing all 2N keys (no lost updates).

7. **No-side-effect-in-Phase-0 invariant** (closure-narrative discipline) — this Phase 0 audit landed with zero production code changes. All §1 grep results are read-only.

---

**End of Phase 0 audit.** Ready to forward to auditor.

**Architect's request to auditor:** confirm pre-audit premise (10-bug enumeration + 4-bug P0.B5 scope) + Phase 0 scope decomposition + D1-D4 are the right shape + cadence prediction (MEDIUM-band v1 → v2 floor likely) is defensible. 4 open questions at §8 await adjudication.
