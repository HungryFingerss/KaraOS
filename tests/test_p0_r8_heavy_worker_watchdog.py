"""P0.R8 — Heavy-worker pool watchdog + restart-burst limit + crash
observability (9 logical anchors, anchor LOCK 9 per Plan v1 §3).

Validates the ``core/heavy_worker.py`` crash-history infrastructure (D1 —
``_HEAVY_WORKER_CRASH_HISTORY`` + 3 accessors) + ``run_heavy`` body wrapper
(D2 — try/except catching ``BrokenProcessPool`` + record + BARE re-raise
preserving traceback), the ``pipeline.py`` watchdog loop (D3 — bare
``while True:`` body per PI #1 absorption mirroring P0.R3 actual at
pipeline.py:2411), the ``core/config.py`` constants (D7), the
``HealthSnapshot.heavy_worker_crash_counts`` field (D5), the
``WatchdogAgent.report_heavy_worker_burst`` method (D4), and the startup
ordering invariant (D6 — heavy_worker_watchdog spawned AFTER
vision_watchdog; cancelled FIRST at shutdown).

Per Plan v1 §3 LOCK: 9 anchors at exact mid 9 INCLUSIVE ±15% band
[7.65, 10.35].

Hybrid surface:
- A1, A6, A7, A9: source-inspection (module-level FunctionDef + dataclass
  field + config constant + WatchdogAgent method presence)
- A2: AST positive + inverse (try/except + record + BARE raise; NO `pass`,
  NO `raise SomethingElse(...)`)
- A3: source-inspection (bare `while True:` body) + AST function exists
- A4: behavioral (watchdog sleeps `HEAVY_WORKER_WATCHDOG_INTERVAL_SECS`)
- A5: behavioral (burst-detection logic with crafted timestamps)
- A8: AST line-order (heavy_worker_watchdog spawn AFTER vision_watchdog
  AND AFTER all 4 pool warm-ups)

Anchor-to-deliberate-regression mapping (per Plan v1 §2.8):
- (a) Delete `_HEAVY_WORKER_CRASH_HISTORY` + accessors → A1
- (b) Remove try/except from `run_heavy` body → A2
- (c) Delete `_heavy_worker_watchdog_loop` async function → A3
- (d) Replace `HEAVY_WORKER_WATCHDOG_INTERVAL_SECS` with hardcoded 1.0 → A4
- (e) Replace burst-threshold check `>= THRESHOLD` with `>= 999` → A5
- (f) Delete `report_heavy_worker_burst` method from `WatchdogAgent` → A6
- (g) Remove `heavy_worker_crash_counts` field from `HealthSnapshot` → A7
- (h) Reverse startup ordering — spawn BEFORE vision_watchdog → A8
- (i) Delete the 3 new config constants → A9
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_HEAVY_WORKER = _REPO_ROOT / "core" / "heavy_worker.py"
_HEALTH = _REPO_ROOT / "core" / "health.py"
_CONFIG = _REPO_ROOT / "core" / "config.py"
_BRAIN_AGENT = _REPO_ROOT / "core" / "brain_agent" / "agents" / "watchdog.py"
_PIPELINE = _REPO_ROOT / "pipeline.py"


# ---------------------------------------------------------------------------
# A1 (D1) — crash history infrastructure
# ---------------------------------------------------------------------------


def test_p0_r8_d1_anchor_1_crash_history_infrastructure_present() -> None:
    """A1 — ``_HEAVY_WORKER_CRASH_HISTORY`` module-level dict +
    ``_HEAVY_WORKER_CRASH_LOCK`` + ``_record_pool_crash`` +
    ``count_recent_crashes`` + ``peek_crash_history`` accessors all
    present at module scope in ``core/heavy_worker.py``.

    Per Plan v1 §2.8 (a) deliberate-regression: deleting any of the 5
    surfaces fires this anchor.
    """
    source = _HEAVY_WORKER.read_text(encoding="utf-8")

    # Module-level assigns/declarations.
    for name in ("_HEAVY_WORKER_CRASH_HISTORY", "_HEAVY_WORKER_CRASH_LOCK"):
        assert name in source, (
            f"D1 regression: {name} module-level declaration missing from "
            f"core/heavy_worker.py."
        )

    # Module-level function defs.
    tree = ast.parse(source)
    module_level_funcs = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    for fn in ("_record_pool_crash", "count_recent_crashes", "peek_crash_history"):
        assert fn in module_level_funcs, (
            f"D1 regression: {fn}() accessor missing from module scope. "
            f"Current module-level functions: {sorted(module_level_funcs)}."
        )

    # Importable + callable.
    import core.heavy_worker as hw  # noqa: PLC0415

    for fn in ("_record_pool_crash", "count_recent_crashes", "peek_crash_history"):
        assert callable(getattr(hw, fn, None)), (
            f"D1 regression: hw.{fn} not callable after import."
        )


# ---------------------------------------------------------------------------
# A2 (D2) — run_heavy body has try/except + record + BARE raise
# ---------------------------------------------------------------------------


def test_p0_r8_d2_anchor_1_run_heavy_wraps_with_record_and_raise() -> None:
    """A2 — ``run_heavy()`` body contains:
    - a ``try`` block wrapping ``await loop.run_in_executor(pool, bound)``
    - an ``except concurrent.futures.process.BrokenProcessPool:`` handler
    - a call to ``_record_pool_crash(task_name)`` inside the handler
    - a BARE ``raise`` statement (NOT ``pass``, NOT ``raise SomethingElse``)
      so the original traceback is preserved + caller fallback fires

    Per Plan v1 §2.8 (b) deliberate-regression: removing the try/except
    OR swallowing via ``pass`` OR wrapping/re-raising a different
    exception type fires this anchor. The BARE ``raise`` is LOAD-BEARING
    — the 4 callers (AdaFace/Whisper/ECAPA/Pyannote) rely on the
    exception propagating to trigger their fallback paths.
    """
    source = _HEAVY_WORKER.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found_try_except = False
    found_record_call = False
    found_bare_raise = False
    no_pass_in_handler = True

    for fn_node in tree.body:
        if not (isinstance(fn_node, ast.AsyncFunctionDef) and fn_node.name == "run_heavy"):
            continue
        for node in ast.walk(fn_node):
            if not isinstance(node, ast.Try):
                continue
            for handler in node.handlers:
                exc = handler.type
                # Match `concurrent.futures.process.BrokenProcessPool` (Attribute chain).
                if not isinstance(exc, ast.Attribute):
                    continue
                if exc.attr != "BrokenProcessPool":
                    continue
                found_try_except = True
                # Scan handler body for _record_pool_crash(task_name) call +
                # BARE raise + absence of swallowing pass.
                #
                # `_record_pool_crash` + bare `raise` checks walk the FULL
                # handler subtree — both can land at any depth via refactor.
                #
                # `Pass` check walks ONLY the OUTER handler body, skipping
                # nested `Try` blocks. P0.R11 D2 added a nested
                # `try: ... except Exception: pass` inside this handler for
                # the OPTIONAL annotated `persist_crash_diagnostic` call
                # (P0.4 silent-except policy: persist failure must NOT mask
                # the original BrokenProcessPool). A nested swallow there is
                # legitimate; a top-level `Pass` instead of `raise` is the
                # actual regression this anchor catches.
                for sub in ast.walk(handler):
                    if (
                        isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Name)
                        and sub.func.id == "_record_pool_crash"
                    ):
                        found_record_call = True
                    if isinstance(sub, ast.Raise):
                        # Bare raise has exc=None and cause=None.
                        if sub.exc is None and sub.cause is None:
                            found_bare_raise = True

                def _outer_pass_scan(body):
                    """Iterate handler body, skipping into nested Try blocks
                    (whose own except handlers may contain legitimate annotated
                    swallows per P0.4). Returns True if any top-level statement
                    OR any statement inside non-Try compound (If/For/etc.) is
                    `ast.Pass`."""
                    for stmt in body:
                        if isinstance(stmt, ast.Pass):
                            return True
                        if isinstance(stmt, ast.Try):
                            # Skip nested Try entirely — its except: pass shape
                            # is legitimate P0.4-annotated silent failure.
                            continue
                        # Recurse into other compounds (If/For/While/With) — a
                        # `Pass` hiding under `if x: pass` would still be a
                        # swallow path that this anchor must catch.
                        for child in ast.iter_child_nodes(stmt):
                            if hasattr(child, "body") and isinstance(child.body, list):
                                if _outer_pass_scan(child.body):
                                    return True
                            if hasattr(child, "orelse") and isinstance(child.orelse, list):
                                if _outer_pass_scan(child.orelse):
                                    return True
                    return False

                if _outer_pass_scan(handler.body):
                    no_pass_in_handler = False
        break

    assert found_try_except, (
        "D2 regression (positive — try/except): run_heavy body missing "
        "`except concurrent.futures.process.BrokenProcessPool:` handler."
    )
    assert found_record_call, (
        "D2 regression (positive — record call): handler missing "
        "`_record_pool_crash(...)` call. Watchdog burst-detection breaks "
        "without the record-side effect."
    )
    assert found_bare_raise, (
        "D2 regression (LOAD-BEARING — bare raise): handler missing BARE "
        "`raise` statement (must NOT be `raise SomethingElse(...)`). "
        "BARE raise preserves original traceback AND the 4 callers "
        "(AdaFace/Whisper/ECAPA/Pyannote) rely on the exception "
        "propagating to trigger their fallback paths."
    )
    assert no_pass_in_handler, (
        "D2 regression (inverse — no swallow): handler contains `pass` "
        "statement, which would swallow the BrokenProcessPool and break "
        "every caller's fallback chain."
    )


# ---------------------------------------------------------------------------
# A3 (D3) — _heavy_worker_watchdog_loop async function with bare while True
# ---------------------------------------------------------------------------


def test_p0_r8_d3_anchor_1_watchdog_loop_exists_with_bare_while_true() -> None:
    """A3 — ``pipeline.py`` defines ``async def _heavy_worker_watchdog_loop()``
    at module scope with a bare ``while True:`` body per Plan v1 §2.3
    (PI #1 absorption — mirrors P0.R3 actual at pipeline.py:2411).

    Per Plan v1 §2.8 (c) deliberate-regression: deleting the function
    fires this anchor.
    """
    tree = ast.parse(_PIPELINE.read_text(encoding="utf-8"))
    module_level_asyncs = {
        node.name for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
    }
    assert "_heavy_worker_watchdog_loop" in module_level_asyncs, (
        f"D3 regression: _heavy_worker_watchdog_loop async function "
        f"missing from pipeline.py module scope. Current module-level "
        f"async functions: {sorted(module_level_asyncs)}."
    )

    # Verify bare `while True:` body inside the function (PI #1 absorption).
    for node in tree.body:
        if not (isinstance(node, ast.AsyncFunctionDef) and node.name == "_heavy_worker_watchdog_loop"):
            continue
        has_bare_while_true = False
        for sub in ast.walk(node):
            if not isinstance(sub, ast.While):
                continue
            # Bare `while True:` means test is `ast.Constant(value=True)`.
            if isinstance(sub.test, ast.Constant) and sub.test.value is True:
                has_bare_while_true = True
                break
        assert has_bare_while_true, (
            "D3 regression (PI #1 absorption): _heavy_worker_watchdog_loop "
            "body MUST use bare `while True:` per Plan v1 §2.3 (mirrors "
            "P0.R3 actual at pipeline.py:2411). Predicate-driven loops "
            "(like `while _state.peek_persistent(...)`) were the PI #1 "
            "absorption shape — corrected to bare while True."
        )
        break


# ---------------------------------------------------------------------------
# A4 (D3) — watchdog sleeps HEAVY_WORKER_WATCHDOG_INTERVAL_SECS per iter
# ---------------------------------------------------------------------------


def test_p0_r8_d3_anchor_2_watchdog_sleeps_config_interval() -> None:
    """A4 — ``_heavy_worker_watchdog_loop`` body calls ``await
    asyncio.sleep(HEAVY_WORKER_WATCHDOG_INTERVAL_SECS)`` (NOT a hardcoded
    literal). The config constant is the single source of truth for the
    poll cadence.

    Per Plan v1 §2.8 (d) deliberate-regression: replacing the constant
    with hardcoded ``1.0`` fires this anchor.

    AST scan for `asyncio.sleep(...)` Call inside the function body —
    the arg must be a Name node referencing `HEAVY_WORKER_WATCHDOG_INTERVAL_SECS`,
    NOT a numeric Constant.
    """
    tree = ast.parse(_PIPELINE.read_text(encoding="utf-8"))
    found_correct_sleep = False
    found_hardcoded_sleep = False
    for fn_node in tree.body:
        if not (isinstance(fn_node, ast.AsyncFunctionDef) and fn_node.name == "_heavy_worker_watchdog_loop"):
            continue
        for node in ast.walk(fn_node):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "asyncio"
                and func.attr == "sleep"
            ):
                continue
            if not node.args:
                continue
            arg = node.args[0]
            if isinstance(arg, ast.Name) and arg.id == "HEAVY_WORKER_WATCHDOG_INTERVAL_SECS":
                found_correct_sleep = True
            elif isinstance(arg, ast.Constant) and isinstance(arg.value, (int, float)):
                found_hardcoded_sleep = True
        break

    assert found_correct_sleep, (
        "D3 regression: _heavy_worker_watchdog_loop must sleep "
        "`HEAVY_WORKER_WATCHDOG_INTERVAL_SECS` (config constant), NOT a "
        "hardcoded numeric literal. Config-driven cadence allows operator "
        "tuning without code changes."
    )
    assert not found_hardcoded_sleep, (
        "D3 regression: _heavy_worker_watchdog_loop contains hardcoded "
        "numeric asyncio.sleep(N) — must use HEAVY_WORKER_WATCHDOG_INTERVAL_SECS "
        "config constant."
    )


# ---------------------------------------------------------------------------
# A5 (D3) — burst-detection logic (behavioral with crafted timestamps)
# ---------------------------------------------------------------------------


def test_p0_r8_d3_anchor_3_burst_detection_threshold_logic() -> None:
    """A5 — burst-detection logic: the watchdog loop's threshold comparison
    must use ``crash_count >= HEAVY_WORKER_RESTART_BURST_THRESHOLD`` (the
    config constant), NOT a hardcoded numeric literal. Plus behavioral
    verification that ``count_recent_crashes`` correctly counts at
    threshold + prunes outside the window.

    Hybrid AST + behavioral check:
    1. AST scan inside ``_heavy_worker_watchdog_loop`` for the Compare
       node with `>=` op + right side is `Name("HEAVY_WORKER_RESTART_BURST_THRESHOLD")`,
       NOT a numeric Constant. Catches Plan v1 §2.8 (e) regression
       (`>= 999` hardcode would replace the Name with a Constant).
    2. Behavioral count_recent_crashes verification (rolling-window
       pruning correctness).

    Per Plan v1 §2.8 (e) deliberate-regression: replacing the threshold
    check with hardcoded `>= 999` (or any numeric Constant) fires the
    AST half. Breaking window pruning fires the behavioral half.
    """
    import core.heavy_worker as hw  # noqa: PLC0415
    from core.config import (  # noqa: PLC0415
        HEAVY_WORKER_RESTART_BURST_THRESHOLD,
        HEAVY_WORKER_RESTART_BURST_WINDOW_SECS,
    )

    # Part 1: AST check — threshold comparison uses Name (config constant)
    # NOT a numeric Constant.
    tree = ast.parse(_PIPELINE.read_text(encoding="utf-8"))
    found_correct_threshold_compare = False
    found_hardcoded_threshold_compare = False
    for fn_node in tree.body:
        if not (isinstance(fn_node, ast.AsyncFunctionDef) and fn_node.name == "_heavy_worker_watchdog_loop"):
            continue
        for node in ast.walk(fn_node):
            if not isinstance(node, ast.Compare):
                continue
            # Match `crash_count >= <something>` shape — left is Name("crash_count"),
            # ops[0] is GtE.
            if not (isinstance(node.left, ast.Name) and node.left.id == "crash_count"):
                continue
            if not (len(node.ops) == 1 and isinstance(node.ops[0], ast.GtE)):
                continue
            right = node.comparators[0]
            if isinstance(right, ast.Name) and right.id == "HEAVY_WORKER_RESTART_BURST_THRESHOLD":
                found_correct_threshold_compare = True
            elif isinstance(right, ast.Constant) and isinstance(right.value, (int, float)):
                found_hardcoded_threshold_compare = True
        break

    assert found_correct_threshold_compare, (
        "A5 regression (AST positive): _heavy_worker_watchdog_loop body "
        "missing `crash_count >= HEAVY_WORKER_RESTART_BURST_THRESHOLD` "
        "compare. Config-driven threshold is the single source of truth; "
        "operator tuning must work without code changes."
    )
    assert not found_hardcoded_threshold_compare, (
        "A5 regression (AST inverse): _heavy_worker_watchdog_loop body "
        "contains hardcoded numeric threshold compare. The comparison "
        "must use HEAVY_WORKER_RESTART_BURST_THRESHOLD config constant; "
        "hardcoding (e.g. `>= 999`) breaks the watchdog (never fires)."
    )

    # Part 2: behavioral count_recent_crashes verification.
    test_task = "p0_r8_a5_test_task"
    with hw._HEAVY_WORKER_CRASH_LOCK:
        hw._HEAVY_WORKER_CRASH_HISTORY.pop(test_task, None)

    try:
        now = 10000.0
        for i in range(HEAVY_WORKER_RESTART_BURST_THRESHOLD):
            hw._record_pool_crash(test_task, now=now - 10.0 * i)
        count_at_threshold = hw.count_recent_crashes(
            test_task, HEAVY_WORKER_RESTART_BURST_WINDOW_SECS, now=now
        )
        assert count_at_threshold == HEAVY_WORKER_RESTART_BURST_THRESHOLD, (
            f"A5 regression: count at threshold = {count_at_threshold}, "
            f"expected {HEAVY_WORKER_RESTART_BURST_THRESHOLD}."
        )

        with hw._HEAVY_WORKER_CRASH_LOCK:
            hw._HEAVY_WORKER_CRASH_HISTORY.pop(test_task, None)
        for i in range(HEAVY_WORKER_RESTART_BURST_THRESHOLD):
            hw._record_pool_crash(
                test_task,
                now=now - HEAVY_WORKER_RESTART_BURST_WINDOW_SECS - 10.0 - i,
            )
        count_outside_window = hw.count_recent_crashes(
            test_task, HEAVY_WORKER_RESTART_BURST_WINDOW_SECS, now=now
        )
        assert count_outside_window == 0, (
            f"A5 regression: count outside window = {count_outside_window}, "
            f"expected 0 (pruning broken)."
        )
    finally:
        with hw._HEAVY_WORKER_CRASH_LOCK:
            hw._HEAVY_WORKER_CRASH_HISTORY.pop(test_task, None)


# ---------------------------------------------------------------------------
# A6 (D4) — WatchdogAgent.report_heavy_worker_burst method
# ---------------------------------------------------------------------------


def test_p0_r8_d4_anchor_1_watchdog_agent_method_exists() -> None:
    """A6 — ``WatchdogAgent.report_heavy_worker_burst`` method exists +
    stores alert via ``self._db.store_alert(...)``. Source-inspection
    AST scan locates the method def inside the WatchdogAgent class
    body + verifies a `store_alert` Call inside the method body.

    Per Plan v1 §2.8 (f) deliberate-regression: deleting the method
    fires this anchor.
    """
    tree = ast.parse(_BRAIN_AGENT.read_text(encoding="utf-8"))
    watchdog_class = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "WatchdogAgent":
            watchdog_class = node
            break
    assert watchdog_class is not None, (
        "D4 sanity: WatchdogAgent class not found in core/brain_agent.py."
    )

    method_def = None
    for sub in watchdog_class.body:
        if isinstance(sub, ast.FunctionDef) and sub.name == "report_heavy_worker_burst":
            method_def = sub
            break
    assert method_def is not None, (
        "D4 regression: WatchdogAgent.report_heavy_worker_burst method "
        "missing. Per Plan v1 §2.4, this method stores a burst-crash "
        "alert via self._db.store_alert(...) called from "
        "pipeline._heavy_worker_watchdog_loop."
    )

    # Verify store_alert call inside the method body.
    has_store_alert = False
    for n in ast.walk(method_def):
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "store_alert"
        ):
            has_store_alert = True
            break
    assert has_store_alert, (
        "D4 regression: report_heavy_worker_burst body missing "
        "store_alert(...) call. The method must persist the alert via "
        "the BrainDB alert store for dashboard/operator visibility."
    )


# ---------------------------------------------------------------------------
# A7 (D5) — HealthSnapshot.heavy_worker_crash_counts field
# ---------------------------------------------------------------------------


def test_p0_r8_d5_anchor_1_health_snapshot_crash_counts_field() -> None:
    """A7 — ``HealthSnapshot.heavy_worker_crash_counts: dict[str, int]``
    field present + ``gather_health_snapshot`` populates it from
    ``hw.count_recent_crashes`` per pool.

    Per Plan v1 §2.8 (g) deliberate-regression: removing the field
    fires this anchor.
    """
    import dataclasses  # noqa: PLC0415
    from core.health import HealthSnapshot  # noqa: PLC0415

    field_names = {f.name for f in dataclasses.fields(HealthSnapshot)}
    assert "heavy_worker_crash_counts" in field_names, (
        f"D5 regression: HealthSnapshot.heavy_worker_crash_counts field "
        f"missing. Present fields: {sorted(field_names)}. Per Plan v1 "
        f"§2.5, this field surfaces per-pool crash counts to the "
        f"observability layer."
    )

    # Verify gather_health_snapshot references count_recent_crashes.
    source = _HEALTH.read_text(encoding="utf-8")
    assert "count_recent_crashes" in source, (
        "D5 regression: core/health.py does not call "
        "hw.count_recent_crashes — gather_health_snapshot must populate "
        "heavy_worker_crash_counts from the heavy_worker crash history."
    )


# ---------------------------------------------------------------------------
# A8 (D6) — Startup ordering invariant
# ---------------------------------------------------------------------------


def test_p0_r8_d6_anchor_1_startup_ordering_invariant() -> None:
    """A8 — ``pipeline.run()`` startup spawns:
    - all 4 pool warm-ups FIRST
    - then ``_vision_task = asyncio.create_task(...)`` (P0.R3 D5 ordering)
    - then ``_vision_watchdog_task = asyncio.create_task(_vision_watchdog_loop())``
    - then ``_heavy_worker_watchdog_task = asyncio.create_task(_heavy_worker_watchdog_loop())``
      (P0.R8 D6 — LAST, AFTER vision_watchdog)

    ORDERING INVARIANT at shutdown (mirror): heavy_worker_watchdog cancel
    FIRST, then vision_watchdog, then vision_task, then
    hw.shutdown_all_pools. This anchor enforces the STARTUP order via
    AST line-order check; the shutdown order is enforced by the existing
    P0.R3 D5 + new P0.R8 D6 wiring.

    Per Plan v1 §2.8 (h) deliberate-regression: reversing the startup
    order (spawning heavy_worker_watchdog BEFORE vision_watchdog) fires
    this anchor.
    """
    source = _PIPELINE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # AST scan for the actual Call sites (not docstring/comment substrings).
    pool_lines: dict[str, int] = {}
    vision_task_line = None
    vision_watchdog_line = None
    heavy_watchdog_line = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # Pool warm-up: hw.get_or_create_pool("...")
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "hw"
                and func.attr == "get_or_create_pool"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value in (
                    "adaface_embed", "whisper_transcribe",
                    "ecapa_embed", "pyannote_diarize",
                )
            ):
                if node.args[0].value not in pool_lines:
                    pool_lines[node.args[0].value] = node.lineno
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id == "_vision_task" and vision_task_line is None:
                    # Only first assignment within run() body (multiple
                    # restart-helper assignments may follow).
                    if isinstance(node.value, ast.Call):
                        vision_task_line = node.lineno
                if target.id == "_vision_watchdog_task" and vision_watchdog_line is None:
                    if isinstance(node.value, ast.Call):
                        vision_watchdog_line = node.lineno
                if target.id == "_heavy_worker_watchdog_task" and heavy_watchdog_line is None:
                    if isinstance(node.value, ast.Call):
                        heavy_watchdog_line = node.lineno

    expected_pools = ("adaface_embed", "whisper_transcribe", "ecapa_embed", "pyannote_diarize")
    missing_pools = [p for p in expected_pools if p not in pool_lines]
    assert not missing_pools, (
        f"D6 sanity: pool(s) missing from pipeline.run() startup: {missing_pools}."
    )
    assert vision_task_line is not None, "D6 sanity: _vision_task assign not found."
    assert vision_watchdog_line is not None, "D6 sanity: _vision_watchdog_task assign not found."
    assert heavy_watchdog_line is not None, (
        "D6 regression: _heavy_worker_watchdog_task assign not found in "
        "pipeline.run() — startup spawn missing."
    )

    # Ordering: all 4 pools < vision_task < vision_watchdog < heavy_worker_watchdog.
    pool_max = max(pool_lines.values())
    assert pool_max < vision_task_line, (
        f"D6 regression: vision_task spawn at line {vision_task_line} "
        f"comes BEFORE last pool warm-up at line {pool_max}. Pools must "
        f"be ready before vision task spawns."
    )
    assert vision_task_line < vision_watchdog_line, (
        f"D6 regression: vision_watchdog spawn at line {vision_watchdog_line} "
        f"comes BEFORE vision_task at line {vision_task_line}."
    )
    assert vision_watchdog_line < heavy_watchdog_line, (
        f"D6 regression (ORDERING INVARIANT): heavy_worker_watchdog "
        f"spawn at line {heavy_watchdog_line} comes BEFORE vision_watchdog "
        f"at line {vision_watchdog_line}. Per Plan v1 §2.6, "
        f"heavy_worker_watchdog must spawn AFTER vision_watchdog (so "
        f"shutdown ORDERING INVARIANT — heavy_worker_watchdog cancel "
        f"FIRST — is preserved)."
    )


# ---------------------------------------------------------------------------
# A9 (D7) — 3 config constants
# ---------------------------------------------------------------------------


def test_p0_r8_d7_anchor_1_config_constants_present() -> None:
    """A9 — 3 new config constants present in ``core/config.py``:
    ``HEAVY_WORKER_WATCHDOG_INTERVAL_SECS`` +
    ``HEAVY_WORKER_RESTART_BURST_THRESHOLD`` +
    ``HEAVY_WORKER_RESTART_BURST_WINDOW_SECS``.

    Per Plan v1 §2.8 (i) deliberate-regression: deleting any of the 3
    constants fires this anchor.
    """
    from core import config  # noqa: PLC0415

    REQUIRED = (
        "HEAVY_WORKER_WATCHDOG_INTERVAL_SECS",
        "HEAVY_WORKER_RESTART_BURST_THRESHOLD",
        "HEAVY_WORKER_RESTART_BURST_WINDOW_SECS",
    )
    missing = [c for c in REQUIRED if not hasattr(config, c)]
    assert not missing, (
        f"D7 regression: config constants missing: {missing}. Per "
        f"Plan v1 §2.7, the watchdog reads all 3 — deleting any breaks "
        f"the watchdog loop."
    )

    # Sanity values — non-zero, sensible defaults.
    assert config.HEAVY_WORKER_WATCHDOG_INTERVAL_SECS > 0, (
        "D7 regression: HEAVY_WORKER_WATCHDOG_INTERVAL_SECS must be > 0."
    )
    assert config.HEAVY_WORKER_RESTART_BURST_THRESHOLD >= 1, (
        "D7 regression: HEAVY_WORKER_RESTART_BURST_THRESHOLD must be >= 1."
    )
    assert config.HEAVY_WORKER_RESTART_BURST_WINDOW_SECS > 0, (
        "D7 regression: HEAVY_WORKER_RESTART_BURST_WINDOW_SECS must be > 0."
    )
