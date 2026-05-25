# P0.B5 Plan v1 — Resilience Hygiene Bundle (D1+D2+D3+D4 contract lock + 4 precision items absorbed)

**Phase 0 base:** `tests/p0_b5_resilience_hygiene_audit.md` (auditor APPROVED 2026-05-21 with all 4 open questions adjudicated to architect leans + Q5 band locked at 6-12 mid 9 + 0 open precision items at Phase 0 review — `Phase-0-zero-precision-items-at-auditor-review` 2nd instance banked; 1 away from 3+ sub-rule threshold).

**Plan v1 absorbs (proactively, all 4 anticipated precision items from auditor verdict):**

- **P1** §1 Pass-2 grep enumeration across 4 subsystems per `Plan-v1-Pass-2-grep-undercount` informal observation (1 instance banked at P0.B3 closure). Multi-pattern grep covers test files + production call sites for each D-decision.
- **P2** §5 closure-narrative paste-template (5-surface landing format per P0.B2/P0.B3 precedent) + §6 closure-actual projection per `Explicit-closure-honest-count-commitment` discipline (commitment MADE here = 7th instance at Plan v1; HONORED at closure = 8th).
- **P3** §2.3 D3 AST tripwire (forward-property): NO `self._save_faiss()` call site appears inside `with self._index_lock:` AST block. Every locked-context caller must use `_save_faiss_unlocked()`.
- **P4** §5.6 + §7 — closure narrative lands the 10-bug enumeration as PERMANENT REFERENCE DOC per Q4 architect lean (auditor LOCKED ACCEPT). P0.B5 is the LAST bug-fix cycle in the original board-meeting 10-bug scope; closure narrative becomes the master reference.

Cadence prediction: **v1 → v2 floor likely** per auditor verdict ("Realistically, MEDIUM-band cycles have historically required Plan v2 except for the 2 anomalous short-spec proof cases"). Plan v2 escalation likely for explicit closure-template lock + AST tripwire shape verification + 10-bug reference doc structure. OPTIONAL-Plan-v2 path POSSIBLE if Plan v1 absorbs cleanly (would be 3rd proof case after P0.S3 + P0.B3).

---

## §1. P1 — Pass-2 grep enumeration across 4 subsystems

Per the `Plan-v1-Pass-2-grep-undercount` informal observation (1 instance banked at P0.B3 closure; multi-pattern Pass-2 grep is the preventive operational rule), the 4-subsystem fan-out raises undercount risk. Each D-decision's grep below uses MULTIPLE search patterns + cross-references the production code + test code.

### §1.1 D1 (Bug 7) — `_safe_emit_failure_count` reset scope

**Production sites** (`core/event_log/producer.py`):
- **Line 464** — `_safe_emit_failure_count: int = 0` (module-level declaration). The single counter declaration.
- **Lines 453-459** — `_safe_emit_failure_count += 1` increment inside `safe_emit_sync` exception handler (only writer).
- **Line 467-470** — `get_safe_emit_failure_count() -> int` (read-side observability surface used by `core/health.py:128`).
- **Line 585** — `__all__` export list (`get_safe_emit_failure_count` exported).
- **Lines 527-541** — `_reset_for_tests()` (the bug surface: counter NOT in reset list).

**Sibling module-level counters (already reset)**:
- Line 69: `_drop_count: int = 0` — in reset ✓
- Line 70: `_last_drop_log_ts: float = 0.0` — in reset ✓
- Line 464: `_safe_emit_failure_count: int = 0` — **MISSING from reset ✗**

**Test sites** (multi-pattern grep `tests/test_*event_log*.py` + `tests/test_event_log_*.py`):
- `tests/test_event_log_contract.py` — grep for `_safe_emit_failure_count` / `get_safe_emit_failure_count`.
- `tests/test_event_log_invariants.py` — same.
- `tests/test_event_log_producer_coverage.py` — same.
- `tests/test_event_log_replay*` — same.

**Pass-2 verification needed at Phase 4:** developer re-greps all 4 test files for `_safe_emit_failure_count` / `get_safe_emit_failure_count` references. Any test that asserts the counter equals 0 after `_reset_for_tests` is the regression guard; any test that asserts >0 after seeded failures + tracks the count is the behavioral guard.

### §1.2 D2 (Bug 8) — `_queue.join()` unbounded-await surface

**Production sites** (`core/event_log/producer.py`):
- **Line 510** — `await _queue.join()` inside `stop_writer()` (the bug surface; unbounded await).
- Other `_queue.join()` call sites: ZERO (grep confirmed). Only `stop_writer()` calls it.
- **Line 513** — `await asyncio.wait_for(_writer_task, timeout=5.0)` (canonical mirror pattern for D2 fix).
- **Lines 504-521** — `stop_writer()` function body (the migration target).

**Test sites** (multi-pattern grep `tests/test_*event_log*.py` + `tests/*event_log_replay*` + `tests/conftest.py`):
- `tests/test_event_log_contract.py` — grep for `stop_writer` calls.
- `tests/test_event_log_invariants.py` — same.
- Any pipeline-shutdown integration test — grep for `stop_writer` + `pipeline.run` cleanup.

**Pass-2 verification needed at Phase 4:** developer re-greps for any test that exercises `stop_writer()` with a dead `_writer_task`. None expected today (the bug means this scenario isn't tested); new test added by D2 anchor 2 (slow-tier behavioral).

### §1.3 D3 (Bug 9) — `_save_faiss()` call site enumeration (3 sites verified at Plan v1)

**Production call sites in `core/db.py` (Pass-2 grep result):**

| Line | Context | Lock state at call site | Migration disposition |
|---|---|---|---|
| 715 | `add_embedding` body | Inside `with self._index_lock:` block at line 694 | **MIGRATE to `_save_faiss_unlocked()`** ✓ |
| 1165 | `_rebuild_faiss` body | OUTSIDE lock — lock block at 1149-1156 already released | **KEEP `self._save_faiss()`** (lock-acquiring path) |
| 1894 | `wipe_all` body | Standalone, no lock context | **KEEP `self._save_faiss()`** (lock-acquiring path) |

**Pass-2 verification:** all 3 call sites enumerated; migration target is line 715 only. Lines 1165 and 1894 stay on `self._save_faiss()` (the lock-acquiring variant) per the discipline ("callers that DO NOT hold the lock keep using `self._save_faiss()`").

**Sibling lock-acquiring methods (already inside `_index_lock` blocks)** — Pass-2 grep for `with self._index_lock:` blocks:
- Line 694: `add_embedding` — calls `_save_faiss()` at line 715 (MIGRATES).
- Line 730: needs Pass-2 verification of body — does it call `_save_faiss()`?
- Line 789: needs Pass-2 verification of body.
- Line 870: needs Pass-2 verification of body.
- Line 921: needs Pass-2 verification of body.
- Line 1013: needs Pass-2 verification of body (this is `rebuild_faiss_async` Phase 3).
- Line 1149: inside `_rebuild_faiss` (verified — doesn't call `_save_faiss` inside the lock block).

**Pass-2 verification needed at Phase 4:** developer greps each `with self._index_lock:` block body for `_save_faiss(` substring. If any contain it → migrate per D3 discipline. If none beyond line 715 contain it → 3-site enumeration is exhaustive.

**Defense-in-depth (D3 anchor 4 — AST forward-property):** structural test scans ALL `with self._index_lock:` blocks for descendants matching `Call(Attribute(self, "_save_faiss"))`. FAILS if any exist. Prevents future-refactor that adds a new lock-context call site without migrating.

### §1.4 D4 (Bug 10) — `set_persistent` writer enumeration

**Production sites:**
- `core/state.py:16` — `set_persistent` declaration (the function body to wrap with lock).
- `pipeline.py:6310` — `state.set_persistent("anti_spoof_enabled", _as_enabled)` — sole production writer (startup-only).

**Test sites (multi-pattern grep `tests/test_state*.py` + `tests/test_*persistent*.py` + `tests/test_state_race.py`):**
- `tests/test_state_race.py:91, 154, 158, 159` — concurrent-writer stress test (already exists per P0.11). 1000 sequential calls × 1000 reader threads. **D4 strengthens this test's guarantees** — pre-D4 the test passes by GIL-atomicity; post-D4 it passes by explicit `Lock`.
- `tests/test_state_race.py:263` — docstring text referencing `set_persistent(key, value)` (atomic-replace).
- `test_pipeline.py:7859` — `st.set_persistent("anti_spoof_enabled", False)` test setup.

**Pass-2 verification:** sole production writer is `pipeline.py:6310` (startup-only). No re-entrant call chains (verified — `set_persistent` doesn't call itself or any function that might call back). `threading.Lock` (non-re-entrant) is safe per Q2 architect lean (auditor LOCKED ACCEPT).

**Existing `tests/test_state_race.py` test compatibility:** D4 adds the explicit lock; existing tests should pass UNCHANGED (the GIL-atomic guarantee still holds + the new lock adds explicit safety). If any test asserts the ABSENCE of locking primitives, Plan v1 needs to update — but Pass-1 grep showed no such assertions. Architect lean: existing tests stay; D4's new concurrent-writer test (D4 anchor 3) supplements.

---

## §2. D-decisions — full contract lock

### §2.1 D1 LOCK — `_reset_for_tests` extension

**File:** `core/event_log/producer.py:527-541`.

**Edit (1-line global declaration + 1-line reset addition):**

```python
def _reset_for_tests() -> None:
    """Test-mode reset. Closes DB + clears module state."""
    global _queue, _writer_task, _conn, _drop_count, _recent_parent, _last_drop_log_ts, _safe_emit_failure_count
    #                                                                                   ^^^^^^^^^^^^^^^^^^^^^^^^
    #                                                                                   P0.B5 D1 — Bug 7 fix
    if _conn is not None:
        try:
            _conn.close()
        except Exception:                          # pragma: no cover
            # CLEANUP: best-effort close.
            pass
    _queue = None
    _writer_task = None
    _conn = None
    _drop_count = 0
    _recent_parent = {}
    _last_drop_log_ts = 0.0
    _safe_emit_failure_count = 0  # P0.B5 D1 — Bug 7 fix (test isolation)
```

**Discipline anchor:** the reset-completeness invariant (§4.1 D1 anchor) scans for every `^_[a-zA-Z_]+: int = 0` / `^_[a-zA-Z_]+: float = 0\.0` module-level counter declaration + verifies each is in the reset list. Any future counter addition that misses the reset will fail this test immediately.

### §2.2 D2 LOCK — `stop_writer` timeout

**File:** `core/event_log/producer.py:504-521`.

**Edit (early-exit + wrap `_queue.join()`):**

```python
async def stop_writer() -> None:
    """Drain the queue + shutdown. Called during graceful pipeline exit.

    P0.B5 D2 (Bug 8) fix: wrap `_queue.join()` with `asyncio.wait_for` to
    bound the wait when `_writer_task` has died before sentinel put. Pre-fix:
    `await _queue.join()` blocked forever because no consumer was calling
    `task_done()`. Post-fix: timeout proceeds to cleanup; subsequent
    `wait_for(_writer_task, ...)` surfaces the dead task via cancel path.
    """
    global _queue, _writer_task, _conn, _recent_parent

    # P0.B5 D2: early-exit if writer task is already done. Don't put sentinel
    # into a queue with no consumer (would just inflate the queue size + lose
    # envelopes anyway on cleanup).
    if _writer_task is not None and _writer_task.done():
        if _queue is not None:
            _q_size = _queue.qsize()
            print(
                f"[EventLog] WARN: stop_writer found writer task already done — "
                f"skipping queue drain ({_q_size} envelopes lost)"
            )
        # Fall through to cleanup below
    elif _queue is not None:
        # Sentinel: None envelope tells _writer_loop to exit.
        await _queue.put(None)
        # P0.B5 D2: bounded wait — protects against writer-task-died-mid-shutdown.
        try:
            await asyncio.wait_for(_queue.join(), timeout=5.0)
        except asyncio.TimeoutError:
            print(
                f"[EventLog] WARN: stop_writer queue.join() timed out — "
                f"writer task likely dead, proceeding to cleanup"
            )

    if _writer_task is not None:
        try:
            await asyncio.wait_for(_writer_task, timeout=5.0)
        except asyncio.TimeoutError:                       # pragma: no cover
            _writer_task.cancel()
    if _conn is not None:
        _conn.close()
    _queue = None
    _writer_task = None
    _conn = None
    _recent_parent = {}
```

**Note:** `_writer_task.done()` check is the architect's hardening beyond bare wrap. Without it, sentinel goes into dead queue + cleanup still proceeds via timeout, but the 5s wait is wasted. With it, dead-task case bypasses the timeout entirely.

### §2.3 D3 LOCK — `_save_faiss_unlocked` extraction + line 715 migration

**File:** `core/db.py:429-431` (extraction) + `core/db.py:715` (migration site).

**Extraction (new helper above `_save_faiss`):**

```python
def _save_faiss_unlocked(self) -> None:
    """Write FAISS index to disk. MUST be called WITH _index_lock already held.

    Extracted from _save_faiss() to make the lock-held precondition explicit
    at every internal call site (P0.B5 D3 / ceo-morning Finding 3 — was
    implicitly relying on RLock re-entrancy; explicit naming prevents future
    refactor from breaking the contract if _index_lock is ever changed from
    threading.RLock to threading.Lock).
    """
    faiss.write_index(self.index, str(self._faiss_path))

def _save_faiss(self) -> None:
    """Public-facing save. Acquires _index_lock + calls _save_faiss_unlocked.

    External callers (callers that do NOT already hold _index_lock) use this
    method. Internal callers that already hold _index_lock (inside a
    `with self._index_lock:` block) MUST use _save_faiss_unlocked() directly
    to make the lock-held precondition visible at the call site.
    """
    with self._index_lock:
        self._save_faiss_unlocked()
```

**Migration of line 715 (inside `add_embedding`, inside `with self._index_lock:` block):**

```python
# Before:
self._save_faiss()
# After:
self._save_faiss_unlocked()  # P0.B5 D3 — lock already held at line 694
```

**Lines 1165 + 1894 stay UNCHANGED** (standalone callers, no lock context — keep `self._save_faiss()`).

**AST tripwire (D3 anchor 4 — forward-property):** structural test scans `core/db.py` for `with self._index_lock:` AST nodes + walks descendants for any `Call(Attribute(self, "_save_faiss"))` matches. FAILS if found.

### §2.4 D4 LOCK — `_persistent_lock` addition

**File:** `core/state.py:1-32`.

**Edit (3 changes — import + lock declaration + wrap):**

```python
"""
core/state.py — Shared state between pipeline and dashboard
Pipeline writes → dashboard reads via /api/status
"""
import json
import os
import tempfile
import threading                                          # P0.B5 D4 — Bug 10 fix
import time
from typing import Optional
from core.config import STATE_FILE


_persistent: dict = {}  # fields merged into every write() — set once at startup
_persistent_lock = threading.Lock()  # P0.B5 D4 — Bug 10 fix (V5 GIL-free safety)


def set_persistent(key: str, value) -> None:
    """Set a field that survives every subsequent write() call.

    Atomic-replace pattern: rebinds `_persistent` to a new dict rather
    than mutating in place. CPython STORE_NAME is GIL-atomic, so a
    concurrent reader iterating the OLD dict reference sees a
    consistent snapshot.

    P0.B5 D4 (Bug 10 / V5) — added explicit `threading.Lock` wrapping
    the rebind preemptively for GIL-free Python forward-compatibility
    (Python 3.13+ --disable-gil builds break the STORE_NAME-atomicity
    assumption that backed the original design). Lock acquisition ~100ns;
    negligible overhead for the current single-startup-writer use case.

    NOTE: This protects readers from torn iteration (via GIL-atomic
    STORE_NAME on CPython) AND protects against concurrent writers
    losing updates (via the new lock). On GIL-free Python builds, the
    lock is the load-bearing safety mechanism.
    """
    global _persistent
    with _persistent_lock:
        _persistent = {**_persistent, key: value}
```

**Docstring change rationale:** the P0.11 disclaimer ("If runtime writers are added, add `threading.Lock`") is REPLACED with the affirmative "Lock added preemptively..." statement. P0.11's deferral is closed by D4.

---

## §3. Test surface — 9 anchors (D1×2 + D2×2 + D3×3 + D4×2)

### §3.1 D1 anchors (2 logical) — `tests/test_p0_b5_resilience_hygiene.py` NEW file

**D1 Anchor 1 — Source-inspection: `_safe_emit_failure_count` in reset list:**

```python
def test_d1_reset_for_tests_clears_safe_emit_failure_count():
    """P0.B5 D1 (Bug 7): _reset_for_tests must reset _safe_emit_failure_count."""
    import inspect
    from core.event_log import producer

    src = inspect.getsource(producer._reset_for_tests)
    # Reset must include the counter in the global declaration AND the reset assignment.
    assert "_safe_emit_failure_count" in src, (
        "P0.B5 D1: _safe_emit_failure_count missing from _reset_for_tests"
    )
    assert "_safe_emit_failure_count = 0" in src, (
        "P0.B5 D1: _safe_emit_failure_count must be reset to 0 in _reset_for_tests"
    )
```

**D1 Anchor 2 — Behavioral: counter survives reset (test isolation regression):**

```python
def test_d1_safe_emit_failure_count_isolated_across_reset():
    """P0.B5 D1 (Bug 7): two consecutive _reset_for_tests cycles each start
    with _safe_emit_failure_count == 0, regardless of intermediate increments."""
    from core.event_log import producer

    producer._reset_for_tests()
    assert producer.get_safe_emit_failure_count() == 0

    # Simulate a swallowed exception that bumps the counter.
    producer._safe_emit_failure_count = 5
    assert producer.get_safe_emit_failure_count() == 5

    producer._reset_for_tests()
    assert producer.get_safe_emit_failure_count() == 0, (
        "P0.B5 D1: counter must be 0 after _reset_for_tests, even if "
        "previously incremented (test isolation guarantee)"
    )
```

### §3.2 D2 anchors (2 logical) — same NEW file

**D2 Anchor 1 — Source-inspection: `_queue.join()` is wrapped:**

```python
def test_d2_stop_writer_wraps_queue_join_in_wait_for():
    """P0.B5 D2 (Bug 8): _queue.join() in stop_writer must be wrapped in asyncio.wait_for."""
    import inspect
    from core.event_log import producer

    src = inspect.getsource(producer.stop_writer)
    # Both wait_for calls must exist: one for _queue.join(), one for _writer_task.
    assert "_queue.join()" in src, "must call _queue.join()"
    assert "asyncio.wait_for(" in src, "must wrap with asyncio.wait_for"
    # The wait_for(_queue.join(), ...) substring is the critical D2 fix.
    assert "wait_for(_queue.join()" in src or "wait_for(\n            _queue.join()" in src, (
        "P0.B5 D2: _queue.join() must be wrapped in asyncio.wait_for "
        "to prevent unbounded hang when _writer_task is dead"
    )
```

**D2 Anchor 2 — Behavioral (slow-tier): `stop_writer` with dead writer doesn't hang:**

```python
@pytest.mark.slow
async def test_d2_stop_writer_completes_when_writer_task_dead(tmp_path):
    """P0.B5 D2 (Bug 8): stop_writer must complete within reasonable time
    even when _writer_task has died before stop_writer is called."""
    from core.event_log import producer
    producer._reset_for_tests()
    db_path = tmp_path / "test_event_log.db"

    await producer.start_writer(db_path)
    # Kill the writer task to simulate the bug scenario.
    producer._writer_task.cancel()
    try:
        await producer._writer_task
    except asyncio.CancelledError:
        pass

    # stop_writer must NOT hang. 10s upper bound (the bug's hang is unbounded).
    t0 = time.time()
    await asyncio.wait_for(producer.stop_writer(), timeout=10.0)
    elapsed = time.time() - t0
    assert elapsed < 10.0, (
        f"P0.B5 D2: stop_writer took {elapsed:.1f}s — should complete via "
        "the new _queue.join() timeout (5s) + _writer_task timeout (5s) + early-exit"
    )
```

### §3.3 D3 anchors (3 logical) — same NEW file

**D3 Anchor 1 — Source-inspection: `_save_faiss_unlocked` exists + lock-free body:**

```python
def test_d3_save_faiss_unlocked_exists_without_lock_acquisition():
    """P0.B5 D3 (Bug 9): _save_faiss_unlocked must exist AND must NOT acquire _index_lock."""
    import inspect
    from core.db import FaceDB

    assert hasattr(FaceDB, "_save_faiss_unlocked"), (
        "P0.B5 D3: FaceDB._save_faiss_unlocked method must exist"
    )
    src = inspect.getsource(FaceDB._save_faiss_unlocked)
    assert "with self._index_lock" not in src, (
        "P0.B5 D3: _save_faiss_unlocked must NOT acquire _index_lock "
        "(it's the lock-not-acquiring variant; caller must already hold the lock)"
    )
    # Body must still write the index.
    assert "faiss.write_index" in src, (
        "P0.B5 D3: _save_faiss_unlocked must still call faiss.write_index"
    )
```

**D3 Anchor 2 — Source-inspection: `_save_faiss` is a thin wrapper:**

```python
def test_d3_save_faiss_thin_wraps_unlocked_variant():
    """P0.B5 D3 (Bug 9): _save_faiss must acquire _index_lock and delegate to _save_faiss_unlocked."""
    import inspect
    from core.db import FaceDB

    src = inspect.getsource(FaceDB._save_faiss)
    assert "with self._index_lock" in src, (
        "P0.B5 D3: _save_faiss must acquire _index_lock"
    )
    assert "self._save_faiss_unlocked()" in src, (
        "P0.B5 D3: _save_faiss must delegate to _save_faiss_unlocked"
    )
```

**D3 Anchor 3 — AST forward-property (P3 absorbed): no `_save_faiss()` inside locked context:**

```python
def test_d3_no_save_faiss_call_inside_index_lock_block():
    """P0.B5 D3 (Bug 9) AST forward-property: scan core/db.py for
    `with self._index_lock:` AST nodes; their descendants must NOT contain
    `self._save_faiss()` calls (must use `self._save_faiss_unlocked()` instead).

    Pre-fix: line 715 inside add_embedding's `with self._index_lock:` block
    called `self._save_faiss()` (re-entrant RLock acquisition — works under
    RLock, would deadlock under Lock). Post-fix: every locked-context caller
    uses the _unlocked variant; the lock-acquiring `_save_faiss` is reserved
    for external (standalone) callers only.
    """
    import ast
    from pathlib import Path

    src = Path("core/db.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            # Check if any context manager is `self._index_lock`.
            is_index_lock_block = any(
                isinstance(item.context_expr, ast.Attribute)
                and isinstance(item.context_expr.value, ast.Name)
                and item.context_expr.value.id == "self"
                and item.context_expr.attr == "_index_lock"
                for item in node.items
            )
            if not is_index_lock_block:
                continue
            # Walk descendants looking for self._save_faiss() calls.
            for descendant in ast.walk(node):
                if not isinstance(descendant, ast.Call):
                    continue
                func = descendant.func
                if (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "self"
                    and func.attr == "_save_faiss"
                ):
                    violations.append(descendant.lineno)

    assert not violations, (
        f"P0.B5 D3 AST forward-property violation: "
        f"self._save_faiss() called inside `with self._index_lock:` block at line(s) "
        f"{violations}. Must use self._save_faiss_unlocked() instead — the "
        "lock is already held. Pre-fix: line 715 had this pattern (re-entrant "
        "RLock acquisition); post-P0.B5 D3 every locked-context caller uses "
        "the _unlocked variant to make the lock-held precondition explicit."
    )
```

### §3.4 D4 anchors (2 logical) — same NEW file

**D4 Anchor 1 — Source-inspection: lock declaration + wrap:**

```python
def test_d4_set_persistent_uses_threading_lock():
    """P0.B5 D4 (Bug 10): set_persistent must wrap mutation in _persistent_lock."""
    import inspect
    from core import state

    # Module has the lock declaration.
    assert hasattr(state, "_persistent_lock"), (
        "P0.B5 D4: state._persistent_lock must exist (threading.Lock())"
    )
    import threading
    assert isinstance(state._persistent_lock, type(threading.Lock())), (
        "P0.B5 D4: _persistent_lock must be a threading.Lock (Q2 LOCK — not RLock)"
    )

    src = inspect.getsource(state.set_persistent)
    assert "with _persistent_lock" in src, (
        "P0.B5 D4: set_persistent body must wrap mutation in `with _persistent_lock:`"
    )
    assert "_persistent = {**_persistent" in src, (
        "P0.B5 D4: atomic-replace pattern preserved (rebind, not mutate in place)"
    )
```

**D4 Anchor 2 — Behavioral (concurrent writers, GIL-free safety):**

```python
def test_d4_concurrent_writers_no_lost_updates():
    """P0.B5 D4 (Bug 10): N threads × M set_persistent calls produce N*M keys in final dict."""
    import threading
    from core import state

    # Reset persistent state.
    state._persistent = {}

    N_THREADS = 4
    N_CALLS_PER_THREAD = 250

    def writer(thread_id: int) -> None:
        for i in range(N_CALLS_PER_THREAD):
            state.set_persistent(f"t{thread_id}_k{i}", i)

    threads = [threading.Thread(target=writer, args=(t,)) for t in range(N_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    expected_keys = N_THREADS * N_CALLS_PER_THREAD
    actual_keys = len(state._persistent)
    assert actual_keys == expected_keys, (
        f"P0.B5 D4 lost-update violation: expected {expected_keys} keys in "
        f"_persistent after {N_THREADS} threads × {N_CALLS_PER_THREAD} calls, "
        f"got {actual_keys}. The new _persistent_lock should prevent RMW races; "
        "lost updates indicate the lock is not wrapping the atomic-replace correctly."
    )
```

### §3.5 Deliberate-regression checks (induction-surfaces-invariant-gaps protocol)

Phase 4 must execute (and document in closure narrative):
- (a) Remove `_safe_emit_failure_count` from `_reset_for_tests` global declaration → D1 Anchor 1 fails.
- (b) Replace `await asyncio.wait_for(_queue.join(), timeout=5.0)` with `await _queue.join()` (revert to unbounded) → D2 Anchor 2 (slow-tier) hangs at 10s timeout + fails.
- (c) Move `self._save_faiss_unlocked()` call at line 715 back to `self._save_faiss()` → D3 Anchor 3 (AST forward-property) catches the violation + fails.
- (d) Drop `_persistent_lock` from `set_persistent` body → D4 Anchor 2 (concurrent writers) MAY produce lost updates on GIL-free Python (Anchor 2 is calibrated to detect lost updates; the test would fail intermittently on CPython but consistently on GIL-free).

All 4 deliberate-regression confirmations follow the established protocol.

### §3.6 Total Plan v1 anchor count

| Anchor source | Count | Location |
|---|---|---|
| D1 anchors (new file) | 2 | `tests/test_p0_b5_resilience_hygiene.py` |
| D2 anchors (new file) | 2 | same |
| D3 anchors (new file) | 3 | same |
| D4 anchors (new file) | 2 | same |
| **TOTAL** | **9 logical anchors** | |

**Q5 LOCK: 9 anchors.** Auditor Q5 band 6-12 mid 9. Locked-actual 9 = 0% (exact mid) = **ON-TARGET** per Plan v3 §1.1 corrected band table.

Architect commitment to honest closure-actual count per `Explicit-closure-honest-count-commitment` discipline (7th instance MADE at this Plan v1; HONORED at closure = 8th):

| Closure-actual | Math (vs mid 9) | Disposition | Doctrine effect |
|---|---|---|---|
| ≤6 anchors | `≤−33.3%` | **FALSIFICATION TRIGGER** | **DEMOTES 9 → 8 supporting** |
| 7 anchors | `−22.2%` | **SLIGHT-DRIFT-DOWN** | HOLDS at 9 (no bump, no demote) |
| 8 anchors | `−11.1%` | **ON-TARGET** | **BUMPS 9 → 10 supporting** |
| **9 anchors (Plan v1 LOCK)** | `0%` | **ON-TARGET** | **BUMPS 9 → 10 supporting** |
| 10 anchors | `+11.1%` | **ON-TARGET** | **BUMPS 9 → 10 supporting** |
| 11 anchors | `+22.2%` | **SLIGHT-DRIFT-UP** | HOLDS at 9 (no bump, no demote) |
| 12 anchors | `+33.3%` | **FALSIFICATION TRIGGER** | **DEMOTES 9 → 8 supporting** |
| ≥13 anchors | `≥+44.4%` | **FALSIFICATION TRIGGER** | **DEMOTES 9 → 8 supporting** |

Honest acknowledgment: Plan v1 LOCK lands at the exact mid (9 anchors = 0% drift). This is the cleanest forecast in the bug-fix arc to date — if closure-actual matches, the doctrine bumps cleanly to 10 supporting. ON-TARGET band is wide (8/9/10) so consolidation/expansion ±1 still lands ON-TARGET.

---

## §4. Test surface — full anchor specifications

See §3.1-§3.4 for verbatim test bodies.

---

## §5. P2 + P4 — Closure-narrative paste-template + 10-bug reference doc

When P0.B5 closes, the closure narrative MUST land verbatim across these 5 surfaces:

### §5.1 CLAUDE.md line ~3 (Last-updated line + suite count + entry summary)

Per P0.B2/P0.B3 closure precedent: single-line summary appended. Format:

```
| **P0.B5 (Resilience Hygiene Bundle — Bugs 7+8+9+10) CLOSED 2026-05-XX** — Closes the LAST 4 of the original 10-bug board-meeting enumeration (P0.B1=Bug 4, P0.B2=Bugs 1+2, P0.B3=Bug 3, P0.B5=Bugs 7-10; Bug 5 deferred to P0.B1.X, Bug 6 deferred to P0.B4 user-trigger). D1: _reset_for_tests resets _safe_emit_failure_count. D2: stop_writer wraps _queue.join() with asyncio.wait_for + early-exit on dead writer task. D3: _save_faiss split into _save_faiss + _save_faiss_unlocked with AST forward-property test guarding the locked-context migration. D4: state._persistent_lock added preemptively for GIL-free Python forward-compat. 9 logical anchors = Plan v1 §3.6 LOCK exact match. Q5 closure 0% ON-TARGET → doctrine bumps 9 → 10 supporting per Plan v3 §1.1 corrected band table. Plan v1 §6 honest-count commitment HONORED — 7th instance MADE + 8th HONORED. NEW informal observations: [none new]. Doctrine track-record after P0.B5: ### Phase-0-granular-decomposition-enables-accurate-estimates 10 supporting; ### Grep-baseline-before-drafting 8 instances; Explicit-closure-honest-count-commitment 8 instances; Phase-0-zero-precision-items-at-auditor-review 3 instances (sub-rule threshold reached if Plan v1 audit also clears 0 precision items). Original 10-bug board-meeting scope: 100% addressed at spec level (P0.B1-B5 closed + P0.B1.X deferred + P0.B4 user-trigger gated).
```

### §5.2-§5.4 parent + subdir `complete-plan.md` + `to_be_checked.md`

Per P0.B2/P0.B3 precedent. Twin-filename pitfall discipline applied at status flip (verify both parent + subdir surfaces).

### §5.5 Memory files (3 entries minimum + 10-bug reference doc structure)

- `feedback_explicit_closure_honest_count_commitment.md`: bump 6 → 8 instances (Plan v1 §6 MADE + closure HONORED).
- `feedback_strict_industry_standard_mode.md` track-record entry.
- `feedback_auditor_q5_estimates_trail_grep.md`: +1 banked closure at 0% ON-TARGET (the cleanest band-table reading in the bug-fix arc).

### §5.6 P4 — 10-bug enumeration as PERMANENT REFERENCE DOC

Per Q4 architect lean (auditor LOCKED ACCEPT): P0.B5 closure narrative is the FINAL bug-fix cycle in the original board-meeting scope. The 10-bug enumeration table (from Phase 0 audit §"Pre-audit premise") lands in BOTH:

1. **CLAUDE.md** — appended below the closure narrative's one-line summary. Cross-referenced from the Architectural Disciplines section.
2. **`complete-plan.md`** (parent) — full table with hyperlinks to each spec's closure narrative for traceability.

Format (verbatim per §"Pre-audit premise"):

```markdown
### Board-bug remediation track — original 10-bug scope (CLOSED 2026-05-XX at P0.B5 closure)

| # | Name | Spec | Status | Closure date |
|---|---|---|---|---|
| 1 | FAISS async rebuild (Finding 1) | P0.B2 | CLOSED | 2026-05-21 |
| 2 | Documentation-vs-reality drift at `test_faiss_atomicity_invariants.py:29-32` | P0.B2 | CLOSED | 2026-05-21 |
| 3 | Kuzu schema upgrade ordering (Finding 2) | P0.B3 | CLOSED | 2026-05-21 |
| 4 | VoiceEvidence not frozen (BUG-SS-1) | P0.B1 | CLOSED | 2026-05-21 |
| 5 | Reconciler `_p4_single_segment_mismatch` "dead" (BUG-REC-1) | P0.B1.X | DEFERRED (design dialogue pending Jagan + reviewer) | — |
| 6 | Together.ai SPOF across knowledge pipeline (Attack 6) | P0.B4 | SKIPPED per Jagan 2026-05-21 (deferred to user-defined trigger; architect-flagged design dialogue required) | — |
| 7 | BUG-EL-1 — test isolation `_safe_emit_failure_count` not reset | P0.B5 | CLOSED | 2026-05-XX |
| 8 | BUG-EL-2 — `stop_writer()` hangs on writer-task death | P0.B5 | CLOSED | 2026-05-XX |
| 9 | Finding 3 — `_save_faiss()` RLock re-entrancy implicit | P0.B5 | CLOSED | 2026-05-XX |
| 10 | V5 — `state.json` GIL-dependent race | P0.B5 | CLOSED | 2026-05-XX |
```

Future maintainers see the full bug-fix arc + status of each in one place.

---

## §6. Closure-actual projection per Explicit-closure-honest-count-commitment (7th instance MADE here)

**Architect commits BEFORE closure** per `Explicit-closure-honest-count-commitment` discipline (7th instance candidate, to be HONORED at closure-audit as 8th instance per STRICT separation locked at P0.B3 closure):

Honest closure-actual count is the binding number. No silent over-bumping to ON-TARGET if closure lands at 11 anchors (SLIGHT-DRIFT-UP). No silent under-counting to 8 to dodge the falsification edge. §3.6 band table governs.

**Plan v1 LOCK: 9 anchors.** Architect prediction lands at exact mid 9 → 0% drift → ON-TARGET → doctrine bumps 9 → 10 supporting.

**Honest acknowledgment**: 9 anchors is the cleanest forecast in the bug-fix arc — exact mid-band placement. If developer at Phase 4 consolidates D2 or D3 anchors (e.g. D3 anchor 2 + D3 anchor 3 merge into a parametrized AST test), closure-actual could drop to 8 → STILL ON-TARGET. If developer surfaces an additional fixture-level test (e.g. the §3.5 deliberate-regression check graduates to a logical anchor for one of the 4 D-decisions), closure-actual could rise to 10 → STILL ON-TARGET. The ±15% band at mid 9 is [7.65, 10.35] = anchors 8, 9, 10 all qualify ON-TARGET. Forecast is robust.

---

## §7. Q5 closure projection table (LOCKED at Plan v1)

See §3.6 — band table above.

Band definitions per Plan v3 §1.1 corrected band table (locked at P0.B2 closure):
- ±15% ON-TARGET = [7.65, 10.35] → 8/9/10 anchors all qualify.
- ±15% to ±30% SLIGHT-DRIFT = 7 or 11 anchors.
- ≥±30% FALSIFICATION = ≤6 or ≥12 anchors.

---

## §8. Quality gate checklist (10 APPLIES + 1 N/A privacy)

Per strict-mode 11-gate floor:

1. ✅ **Phase 0 audit completed + auditor-approved** with 0 open precision items at review (2nd instance of `Phase-0-zero-precision-items-at-auditor-review`).
2. ✅ **Plan v1 absorbs all 4 anticipated precision items proactively** (P1 Pass-2 grep + P2 closure-template + P3 AST tripwire + P4 10-bug reference doc structure).
3. ✅ **D-decisions have unambiguous contracts** — D1 at §2.1 + D2 at §2.2 + D3 at §2.3 + D4 at §2.4.
4. ✅ **Pre-mortem coverage** — 10 failure modes documented at Phase 0 §3 with mitigation per mode.
5. ✅ **Multi-direction invariant trace per D-decision** — Phase 0 §4.
6. ✅ **Cross-spec impact analysis** — Phase 0 §5 explicitly names P0.0.7 + P0.5 + P0.11 + future P1.A naming-convention bookmark.
7. ✅ **Spec-time grep-verification (Pass-1 + Pass-2)** — Phase 0 §1 (Pass-1) + Plan v1 §1 (Pass-2). 18th instance of the discipline at Plan v1 close.
8. ✅ **Honest-closure-actual-count commitment made at Plan v1 §6** — 7th instance to be banked.
9. ✅ **Deliberate-regression check protocol** — §3.5 enumerates 4 induced reverts that MUST fire correctly at Phase 4 closure.
10. ✅ **Closure-narrative paste-template + 10-bug reference doc structure ready** — §5 5-surface template + §5.6 reference doc verbatim + §6 band-table + §7 band definitions.
11. N/A **Privacy** — no PII or sensitive-data path touched by D1-D4.

---

## §9. Discipline counts at Plan v1 close

**Per auditor's Post-P0.B5 Phase 0 ratified baseline + Plan v1 artifact (+1):**

| Discipline | Phase 0 close | Plan v1 close |
|---|---|---|
| Spec-first review cycle | 50 | **51** ✓ (Plan v1 artifact +1) |
| Strict-industry-standard mode | 40 applications + 11 closures | **41 applications + 11 closures** |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 9 supporting | stays 9 (closure pending; closure-conditional candidate for 10 if ON-TARGET) |
| `### Phase-0-catches-wrong-premise` | 7 | stays 7 |
| `### Twin-filename-pitfall-prevention` | 7 + 4 op rules | stays 7 (no filename event) |
| `### Grep-baseline-before-drafting` | 7 instances | **8 instances** ✓ (Plan v1 §1 Pass-2 grep applied baseline-citation discipline; preventive application) |
| Deferred-canary | 12th in-flight | stays 12 (closure event pending) |
| Auditor-Q5-estimates-trail-grep | 15 banked + 1 in-flight | stays 15 + 1 in-flight (Plan v1 LOCK 9 anchors; 0% mid-band; closure pending) |
| Cross-cycle-handoff transparency precedent | 13 successful | **14 successful** ✓ (architect honored Phase 0 verdict's ratified counts at Plan v1 baseline grep) |
| Architect-reads-production-code-before-sign-off | 8 banked | stays 8 (closure-audit pending) |
| Sub-pattern A (Phase-0-catches-wrong-premise) | 7 | stays 7 |
| Spec-time grep-verification | 17 instances | **18 instances** ✓ (Plan v1 §1 Pass-2 grep enumerated 3 `_save_faiss()` call sites in D3 + 1 + 1 + 1 sites across other 3 D-decisions + 4 test-file groupings) |
| Discipline-count-bump-needs-explicit-justification | 10 preventive | stays 10 |
| Convention-drift-on-discipline-counts (parent) | 4 | stays 4 |
| Per-artifact-arithmetic-drift-survives-grep-baseline (child) | 1 | stays 1 |
| Explicit-closure-honest-count-commitment | 6 | **7** ✓ (Plan v1 §6 commitment MADE; closure-audit will determine honor at 8th instance closure) |
| Auditor-catches-Q5-math-at-plan-review | 2 | stays 2 (no Q5 math error in Plan v1 — band table at §7 is straightforward 0% mid-band placement, double-verified) |
| Phase-0-zero-precision-items-at-auditor-review (informal) | 2 instances | stays 2 (Plan v1 audit pending; if auditor returns 0 precision items at Plan v1 → 3rd instance → sub-rule threshold reached) |
| Plan-v1-Pass-2-grep-undercount (informal) | 1 | stays 1 (Plan v1 §1 multi-pattern Pass-2 grep applied per the observation's operational rule; Phase 4 re-grep is the backstop) |
| Bug-fix-cycles-surface-discipline-edges (informal) | 1 | stays 1 |
| OPTIONAL-Plan-v2 proof case | 2 (P0.S3 + P0.B3) | stays 2 (would bump to 3 if auditor APPROVED 0 items at Plan v1 + closure event ratifies as MEDIUM-band proof) |

---

## §10. Open questions for auditor (0)

No new open questions. Plan v1 absorbs all 4 anticipated precision items from auditor Phase 0 verdict proactively. Architect prediction: **APPROVED 0 items → ship straight to developer per OPTIONAL-Plan-v2 path (3rd proof case candidate)**.

Realistically, MEDIUM-band cycles have required Plan v2 in 100% of prior cases (P0.B1 + P0.B2 + P0.S6 + P0.S7 etc.). The 2 OPTIONAL-Plan-v2 precedents (P0.S3 + P0.B3) were both SMALL-band. If auditor surfaces ≥1 unresolved item (e.g. closure-template paste-template needs further refinement, or AST tripwire scope needs broadening to other `with self._index_lock:` blocks), escalate to Plan v2.

---

## §11. Implementation handoff readiness

**Developer contract:**
- **Scope:** D1 + D2 + D3 + D4 per §2.1-§2.4.
- **Estimated effort:** 3-4 hours (MEDIUM-band cycle).
- **Files touched:** `core/event_log/producer.py` (D1 + D2, ~10 lines additive each) + `core/db.py` (D3 helper extraction + 1 migration site, ~15 lines) + `core/state.py` (D4 lock + wrap, ~5 lines) + `tests/test_p0_b5_resilience_hygiene.py` (NEW, 9 anchors).
- **Phase 1 (~30 min):** D1 `_reset_for_tests` extension + D4 `_persistent_lock` addition (both small additive).
- **Phase 2 (~1 hour):** D2 `stop_writer` refactor (early-exit + bounded wait_for) + D3 `_save_faiss_unlocked` extraction + line 715 migration.
- **Phase 3 (~30 min):** Pass-2 grep re-verification at production code AND test code per Plan v1 §1 (each D-decision). Honestly bank any Pass-2-grep-undercount instances found.
- **Phase 4 (~1.5 hours):** 9 anchors (D1 ×2 + D2 ×2 + D3 ×3 + D4 ×2). Plus §3.5 deliberate-regression confirmations.
- **Phase 5 (~30 min):** closure narrative + 5-surface landing per §5 + 10-bug reference doc landing per §5.6 + memory file updates + discipline-count integrity check + architect closure-audit per `Architect-reads-production-code-before-sign-off` discipline (9th instance candidate).

**Plan v1 → developer:** ship at auditor Plan v1 sign-off (assuming APPROVED 0 items → 3rd OPTIONAL-Plan-v2 proof case).

**Plan v1 → Plan v2:** ship Plan v2 if auditor surfaces ≥1 unresolved item (MEDIUM-band historical pattern).

---

**End of Plan v1.** Ready to forward to auditor.

**Architect prediction:** **APPROVED 0 items → ship to developer per OPTIONAL-Plan-v2 path** (P0.S3 + P0.B3 = 2 prior proof cases; this would be 3rd). Realistic alternative: 1-2 precision items at Plan v1 review forcing Plan v2 escalation per MEDIUM-band precedent.
