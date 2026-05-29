"""
P0.B5 — Resilience Hygiene Bundle (Bugs 7+8+9+10).

9 logical anchors across 4 D-decisions per Plan v1 §3.6:
  D1 (2): _safe_emit_failure_count reset-list inclusion + behavioral isolation
  D2 (2): stop_writer() asyncio.wait_for wrap + slow-tier dead-writer behavioral
  D3 (3): _save_faiss_unlocked exists + _save_faiss thin-wraps + AST forward-property
          (no _save_faiss() calls inside `with self._index_lock:` blocks)
  D4 (2): _persistent_lock is threading.Lock (NOT RLock per Q2 lock) + concurrent-writer
          behavioral (4 threads × 250 calls = 1000 keys, zero lost updates)
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import ast
import asyncio
import inspect
import threading
import time
from pathlib import Path

import pytest


# ────────────────────────────────────────────────────────────────────────────────
# D1 anchors (2) — _safe_emit_failure_count reset hygiene
# ────────────────────────────────────────────────────────────────────────────────


def test_d1_reset_for_tests_clears_safe_emit_failure_count():
    """P0.B5 D1 (Bug 7): _reset_for_tests must reset _safe_emit_failure_count.

    Pre-fix: _reset_for_tests declared `global` for 6 counters but NOT
    _safe_emit_failure_count + didn't reset it. Test isolation broken —
    a test that simulates a swallowed exception (bumping the counter)
    leaked the bumped value into the next test in the same process.
    """
    from core.event_log import producer

    src = inspect.getsource(producer._reset_for_tests)
    # Reset must include the counter in the global declaration AND the reset assignment.
    assert "_safe_emit_failure_count" in src, (
        "P0.B5 D1: _safe_emit_failure_count missing from _reset_for_tests"
    )
    assert "_safe_emit_failure_count = 0" in src, (
        "P0.B5 D1: _safe_emit_failure_count must be reset to 0 in _reset_for_tests"
    )


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


# ────────────────────────────────────────────────────────────────────────────────
# D2 anchors (2) — stop_writer() bounded-wait + early-exit
# ────────────────────────────────────────────────────────────────────────────────


def test_d2_stop_writer_wraps_queue_join_in_wait_for():
    """P0.B5 D2 (Bug 8): _queue.join() in stop_writer must be wrapped in asyncio.wait_for.

    Pre-fix: `await _queue.join()` blocked forever when _writer_task died
    before stop_writer was called (no consumer to call task_done()).
    Post-fix: bounded wait_for with 5s timeout + early-exit on dead writer.
    """
    from core.event_log import producer

    src = inspect.getsource(producer.stop_writer)
    assert "_queue.join()" in src, "must call _queue.join()"
    assert "asyncio.wait_for(" in src, "must wrap with asyncio.wait_for"
    # The wait_for(_queue.join(), ...) substring is the critical D2 fix.
    # Accept either single-line or multi-line formatting.
    has_wrapped = (
        "wait_for(_queue.join()" in src
        or "wait_for(\n            _queue.join()" in src
        or "wait_for(\n        _queue.join()" in src
    )
    assert has_wrapped, (
        "P0.B5 D2: _queue.join() must be wrapped in asyncio.wait_for "
        "to prevent unbounded hang when _writer_task is dead"
    )
    # Early-exit on dead writer task: presence of the `done()` check.
    assert "_writer_task.done()" in src, (
        "P0.B5 D2: stop_writer must early-exit on _writer_task.done() — "
        "don't put sentinel into queue with no consumer"
    )


@pytest.mark.slow
async def test_d2_stop_writer_completes_when_writer_task_dead(tmp_path):
    """P0.B5 D2 (Bug 8): stop_writer must complete within reasonable time
    even when _writer_task has died before stop_writer is called.

    Without the bounded wait_for, this would hang forever (the bug).
    With the fix: early-exit on `.done()` skips the queue drain entirely
    when writer is already dead → completes within ~ms.
    """
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
        "early-exit on _writer_task.done() (the dead-task case bypasses "
        "the timeout entirely)"
    )


# ────────────────────────────────────────────────────────────────────────────────
# D3 anchors (3) — _save_faiss_unlocked lock-context split + AST forward-property
# ────────────────────────────────────────────────────────────────────────────────


def test_d3_save_faiss_unlocked_exists_without_lock_acquisition():
    """P0.B5 D3 (Bug 9): _save_faiss_unlocked must exist AND must NOT acquire _index_lock.

    Extracted from _save_faiss() to make the lock-held precondition explicit
    at every internal call site. Pre-fix: line 715 inside add_embedding's
    `with self._index_lock:` block called `self._save_faiss()` (re-entrant
    RLock acquisition — works under RLock, would deadlock under Lock).
    """
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


def test_d3_save_faiss_thin_wraps_unlocked_variant():
    """P0.B5 D3 (Bug 9): _save_faiss must acquire _index_lock and delegate to _save_faiss_unlocked.

    External callers (no lock context) use _save_faiss(); internal callers
    that already hold the lock use _save_faiss_unlocked() directly.
    """
    from core.db import FaceDB

    src = inspect.getsource(FaceDB._save_faiss)
    assert "with self._index_lock" in src, (
        "P0.B5 D3: _save_faiss must acquire _index_lock"
    )
    assert "self._save_faiss_unlocked()" in src, (
        "P0.B5 D3: _save_faiss must delegate to _save_faiss_unlocked"
    )


def test_d3_no_save_faiss_call_inside_index_lock_block():
    """P0.B5 D3 (Bug 9) AST forward-property: scan core/db.py for
    `with self._index_lock:` AST nodes; their descendants must NOT contain
    `self._save_faiss()` calls (must use `self._save_faiss_unlocked()` instead).

    Pre-fix: line 715 inside add_embedding's `with self._index_lock:` block
    called `self._save_faiss()` (re-entrant RLock acquisition — works under
    RLock, would deadlock under Lock). Post-fix: every locked-context caller
    uses the _unlocked variant; the lock-acquiring `_save_faiss` is reserved
    for external (standalone) callers only.

    This test prevents future-refactor that adds a new lock-context call site
    without migrating to _save_faiss_unlocked.
    """
    src = (Path(__file__).resolve().parent.parent / "core" / "db.py").read_text(
        encoding="utf-8"
    )
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


# ────────────────────────────────────────────────────────────────────────────────
# D4 anchors (2) — _persistent_lock GIL-free safety
# ────────────────────────────────────────────────────────────────────────────────


def test_d4_set_persistent_uses_threading_lock():
    """P0.B5 D4 (Bug 10): set_persistent must wrap mutation in _persistent_lock.

    Q2 LOCK at Plan v1: `threading.Lock` (NOT `threading.RLock`) — sole
    production writer is `pipeline.py:6310` (startup-only); no re-entrant
    call chains; non-re-entrant Lock is the correct primitive.
    """
    from core import state

    # Module has the lock declaration.
    assert hasattr(state, "_persistent_lock"), (
        "P0.B5 D4: state._persistent_lock must exist (threading.Lock())"
    )
    # threading.Lock() and threading.RLock() return different types; assert the
    # Lock variant per Q2 LOCK.
    assert isinstance(state._persistent_lock, type(threading.Lock())), (
        "P0.B5 D4: _persistent_lock must be a threading.Lock (Q2 LOCK — not RLock)"
    )
    # Belt-and-braces: ensure it's NOT an RLock.
    assert not isinstance(state._persistent_lock, type(threading.RLock())), (
        "P0.B5 D4: _persistent_lock must NOT be an RLock (Q2 LOCK)"
    )

    src = inspect.getsource(state.set_persistent)
    assert "with _persistent_lock" in src, (
        "P0.B5 D4: set_persistent body must wrap mutation in `with _persistent_lock:`"
    )
    assert "_persistent = {**_persistent" in src, (
        "P0.B5 D4: atomic-replace pattern preserved (rebind, not mutate in place)"
    )


def test_d4_concurrent_writers_no_lost_updates():
    """P0.B5 D4 (Bug 10): N threads × M set_persistent calls produce N*M keys in final dict.

    Pre-fix: GIL-atomicity backed the no-lost-update guarantee on CPython but
    breaks on GIL-free builds (Python 3.13+ --disable-gil). Post-fix: explicit
    threading.Lock makes the no-lost-update guarantee load-bearing on BOTH
    standard and GIL-free CPython.
    """
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
