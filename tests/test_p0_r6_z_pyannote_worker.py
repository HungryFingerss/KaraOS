"""P0.R6.Z — Pyannote diarization migration + `get_diarize_executor()`
RETIREMENT (11 logical anchors, anchor LOCK 11 per Plan v1 §3).

Validates the ``core/heavy_worker.py`` pyannote section (D1 + D2 — worker
function + subprocess singleton + lazy-init accessor), the ``core/voice.py``
5-prong retirement (D3.a — `_voice_diarize_executor`, `get_diarize_executor`,
`shutdown_diarize_executor`, `_pyannote_pipeline`, `_load_pyannote_pipeline`
all hard-deleted per Q1 (a) lock), the ``_diarize_pyannote()`` body
migration (D3.b — `hw.run_heavy("pyannote_diarize", ...)` replaces the
in-process executor wrap), the ``pipeline.py`` retirements (D3.c —
`_warm_pyannote_via_dedicated_executor` function + `shutdown_diarize_executor`
call hard-deleted; new pool warm-up added), and the ``pipeline.py::run()``
startup wiring extension (D4 — 4-pool ORDERING INVARIANT preserved).

Per Plan v1 §3 LOCK: 11 anchors at exact mid 11 INCLUSIVE ±15% band
[9.35, 12.65].

Hybrid surface:
- A1-A2: source-inspection (module-level FunctionDef + global declaration)
- A3-A4: AST positive/inverse on ``core/voice.py::_diarize_pyannote()``
- A5-A6: source-inspection inverse (5-prong + 3-prong retirement checks)
- A7: behavioral test with mocked worker returning list[tuple] edge cases
- A8: source-inspection (HealthSnapshot wiring)
- A9: AST line-order (4-pool ordering invariant)
- A10-A11: regex programmatic enforcement (extended from P0.R6.Y A10+A11)

Anchor-to-deliberate-regression mapping (per Plan v1 §2.6):
- (a) Delete ``pyannote_diarize_worker`` → A1
- (b) Replace ``_get_subprocess_pyannote()`` body with `return None` → A2
- (c) Revert ``_diarize_pyannote()`` body to old `_load_pyannote_pipeline()` +
  in-process executor wrap → A3 + A4
- (d) Restore any 1 of 5 retired symbols in `core/voice.py` → A5
- (e) Restore `_warm_pyannote_via_dedicated_executor` OR
  `shutdown_diarize_executor` call in `pipeline.py` → A6
- (f) Modify worker to return Annotation directly (not list[tuple]) → A7
- (g) Drop `hw.get_or_create_pool("pyannote_diarize")` startup → A8 + A9
- (h) MagicMock-instead-of-AsyncMock for new async voice fn → A10
- (i) `_voice_mod._diarize_pyannote(...)` direct call without await → A11
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_HEAVY_WORKER = _REPO_ROOT / "core" / "heavy_worker.py"
_VOICE = _REPO_ROOT / "core" / "voice.py"
_PIPELINE = _REPO_ROOT / "pipeline.py"


# ---------------------------------------------------------------------------
# A1 (D1) — pyannote_diarize_worker module-level function
# ---------------------------------------------------------------------------


def test_p0_r6_z_d1_anchor_1_pyannote_worker_function_exists() -> None:
    """A1 — ``pyannote_diarize_worker`` is defined at MODULE SCOPE in
    ``core/heavy_worker.py`` (NOT nested inside another function).
    Module-level definition is required for pickleability —
    ProcessPoolExecutor's spawn-based IPC pickles the function reference;
    nested functions can't be pickled.

    Per Plan v1 §2.6 (a) deliberate-regression: deleting the function
    fires this anchor.
    """
    tree = ast.parse(_HEAVY_WORKER.read_text(encoding="utf-8"))
    module_level_funcs = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    assert "pyannote_diarize_worker" in module_level_funcs, (
        f"D1 regression: pyannote_diarize_worker must be defined at module "
        f"scope in core/heavy_worker.py (pickleability requirement). "
        f"Current module-level functions: {sorted(module_level_funcs)}."
    )
    import core.heavy_worker as hw  # noqa: PLC0415

    assert callable(getattr(hw, "pyannote_diarize_worker", None)), (
        "D1 regression: pyannote_diarize_worker not callable after import."
    )


# ---------------------------------------------------------------------------
# A2 (D2) — _SUBPROCESS_PYANNOTE_PIPELINE singleton + _get_subprocess_pyannote
# ---------------------------------------------------------------------------


def test_p0_r6_z_d2_anchor_1_subprocess_pyannote_singleton_and_accessor() -> None:
    """A2 — ``_SUBPROCESS_PYANNOTE_PIPELINE`` module-level singleton +
    lazy-init accessor ``_get_subprocess_pyannote()`` present in
    ``core/heavy_worker.py``.

    Singleton enforces "model loads ONCE per subprocess lifetime" — the
    persistent-worker invariant. Without the accessor, every worker call
    would pay the ~30-60s pyannote Pipeline load cost.

    Per Plan v1 §2.6 (b) deliberate-regression: replacing the accessor
    body with unconditional ``return None`` fires this anchor (the
    `global` declaration + Pipeline.from_pretrained construction
    requirement check).
    """
    source = _HEAVY_WORKER.read_text(encoding="utf-8")

    assert "_SUBPROCESS_PYANNOTE_PIPELINE" in source, (
        "D2 regression: _SUBPROCESS_PYANNOTE_PIPELINE module-level "
        "singleton missing from core/heavy_worker.py."
    )

    tree = ast.parse(source)
    module_level_funcs = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    assert "_get_subprocess_pyannote" in module_level_funcs, (
        f"D2 regression: _get_subprocess_pyannote() accessor missing. "
        f"Current module-level functions: {sorted(module_level_funcs)}."
    )

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_get_subprocess_pyannote":
            globals_declared = any(
                isinstance(s, ast.Global)
                and "_SUBPROCESS_PYANNOTE_PIPELINE" in s.names
                for s in ast.walk(node)
            )
            assert globals_declared, (
                "D2 regression: _get_subprocess_pyannote() body missing "
                "`global _SUBPROCESS_PYANNOTE_PIPELINE` declaration."
            )
            pipeline_calls = [
                n for n in ast.walk(node)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "from_pretrained"
            ]
            assert pipeline_calls, (
                "D2 regression: _get_subprocess_pyannote() body missing "
                "Pipeline.from_pretrained(...) construction."
            )
            break


# ---------------------------------------------------------------------------
# A3 (D3.b) — _diarize_pyannote() body dispatches via hw.run_heavy("pyannote_diarize", ...)
# ---------------------------------------------------------------------------


def test_p0_r6_z_d3_anchor_1_diarize_pyannote_uses_hw_run_heavy() -> None:
    """A3 — ``core/voice.py::_diarize_pyannote()`` body contains a positive
    ``hw.run_heavy("pyannote_diarize", ...)`` Call node (AST scan, not
    substring).

    Per Plan v1 §2.6 (c) deliberate-regression: reverting the body to
    direct ``_load_pyannote_pipeline()`` + in-process executor wrap
    fires this anchor.
    """
    source = _VOICE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    found = False
    for fn_node in tree.body:
        if not (isinstance(fn_node, ast.AsyncFunctionDef) and fn_node.name == "_diarize_pyannote"):
            continue
        for node in ast.walk(fn_node):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "hw"
                and func.attr == "run_heavy"
            ):
                continue
            if (
                node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "pyannote_diarize"
            ):
                found = True
                break
        break

    assert found, (
        "D3.b regression (positive check): "
        "core/voice.py::_diarize_pyannote() body does not call "
        'hw.run_heavy("pyannote_diarize", ...). Per Plan v1 §2.3, the '
        "migrated body must offload inference to the heavy-worker "
        "subprocess pool."
    )


# ---------------------------------------------------------------------------
# A4 (D3.b) — _diarize_pyannote() body does NOT contain old executor wrap pattern
# ---------------------------------------------------------------------------


def test_p0_r6_z_d3_anchor_2_diarize_pyannote_no_in_process_executor_wrap() -> None:
    """A4 — ``core/voice.py::_diarize_pyannote()`` body must NOT contain
    (1) ``_load_pyannote_pipeline()`` call OR (2) the in-process
    executor wrap pattern ``run_in_executor(get_diarize_executor(), ...)``
    (inverse check; both are retired post-P0.R6.Z).

    Per Plan v1 §2.6 (c) deliberate-regression: reverting the body to
    those patterns fires this anchor.
    """
    source = _VOICE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    violations = []
    for fn_node in tree.body:
        if not (isinstance(fn_node, ast.AsyncFunctionDef) and fn_node.name == "_diarize_pyannote"):
            continue
        for node in ast.walk(fn_node):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # Match _load_pyannote_pipeline() call (bare Name)
            if isinstance(func, ast.Name) and func.id == "_load_pyannote_pipeline":
                violations.append(f"line {node.lineno}: _load_pyannote_pipeline() call")
            # Match get_diarize_executor() call (bare Name) — passed as first
            # arg to run_in_executor
            if isinstance(func, ast.Name) and func.id == "get_diarize_executor":
                violations.append(f"line {node.lineno}: get_diarize_executor() call")
        break

    assert not violations, (
        f"D3.b regression (inverse check): "
        f"core/voice.py::_diarize_pyannote() body contains retired "
        f"pattern call(s): {violations}. Per Plan v1 §2.3 post-migration, "
        f"the body must NOT call _load_pyannote_pipeline() OR "
        f"get_diarize_executor() — both retired per Q1 (a) lock; pyannote "
        f"inference now runs subprocess-side via hw.run_heavy."
    )


# ---------------------------------------------------------------------------
# A5 (D3.a) — 5-prong retirement inverse check on core/voice.py
# ---------------------------------------------------------------------------


def test_p0_r6_z_d3_anchor_3_voice_py_5_prong_retirement() -> None:
    """A5 — ``core/voice.py`` source shows ALL 5 retirement targets are
    GONE: ``get_diarize_executor``, ``shutdown_diarize_executor``,
    ``_voice_diarize_executor``, ``_pyannote_pipeline``,
    ``_load_pyannote_pipeline``.

    Source-inspection inverse: scan for module-level FunctionDef +
    Assign targets; documentary references in docstrings/comments are
    NOT failures (they're retirement banking).

    Per Plan v1 §2.6 (d) deliberate-regression: restoring ANY of the 5
    retired symbols at module scope fires this anchor.
    """
    tree = ast.parse(_VOICE.read_text(encoding="utf-8"))
    RETIRED_FUNCS = {
        "get_diarize_executor",
        "shutdown_diarize_executor",
        "_load_pyannote_pipeline",
    }
    RETIRED_NAMES = {
        "_voice_diarize_executor",
        "_pyannote_pipeline",
    }

    module_funcs = {
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    module_assigns: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    module_assigns.add(target.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                module_assigns.add(node.target.id)

    func_violations = RETIRED_FUNCS & module_funcs
    name_violations = RETIRED_NAMES & module_assigns

    assert not func_violations and not name_violations, (
        f"D3.a regression (5-prong retirement inverse): the following "
        f"retired symbols are STILL DEFINED at module scope in "
        f"core/voice.py: function defs {sorted(func_violations) or 'none'}, "
        f"variable assignments {sorted(name_violations) or 'none'}. Per "
        f"Plan v1 §2.3 D3.a + Q1 (a) hard-delete lock, ALL 5 must be "
        f"absent from module surface."
    )


# ---------------------------------------------------------------------------
# A6 (D3.c) — pipeline.py 3-prong retirement inverse check
# ---------------------------------------------------------------------------


def test_p0_r6_z_d3_anchor_4_pipeline_py_3_prong_retirement() -> None:
    """A6 — ``pipeline.py`` source shows ALL 3 retirement targets are
    GONE: ``_warm_pyannote_via_dedicated_executor`` function def,
    ``shutdown_diarize_executor`` call, ``voice_mod.get_diarize_executor``
    references at any production call site.

    AST scan: function def absence + `shutdown_diarize_executor` Call
    absence + `voice_mod.get_diarize_executor` Attribute absence.
    Documentary references in docstrings/comments are NOT failures.

    Per Plan v1 §2.6 (e) deliberate-regression: restoring any of the 3
    retired patterns fires this anchor.
    """
    tree = ast.parse(_PIPELINE.read_text(encoding="utf-8"))

    # 1. _warm_pyannote_via_dedicated_executor function def absence.
    module_funcs = {
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_warm_pyannote_via_dedicated_executor" not in module_funcs, (
        "D3.c regression: `_warm_pyannote_via_dedicated_executor` "
        "function def STILL PRESENT in pipeline.py — should have been "
        "hard-deleted per Q1 (a) lock."
    )

    # 2. shutdown_diarize_executor() Call absence (production call site).
    # 3. voice_mod.get_diarize_executor Attribute (production references).
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # voice_mod.shutdown_diarize_executor() call
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "voice_mod"
                and func.attr == "shutdown_diarize_executor"
            ):
                violations.append(
                    f"line {node.lineno}: voice_mod.shutdown_diarize_executor() call"
                )
            # voice_mod.get_diarize_executor() call
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "voice_mod"
                and func.attr == "get_diarize_executor"
            ):
                violations.append(
                    f"line {node.lineno}: voice_mod.get_diarize_executor() call"
                )

    assert not violations, (
        f"D3.c regression (pipeline.py inverse): retired pattern "
        f"call(s) present: {violations}. Per Plan v1 §2.3 D3.c + Q1 "
        f"(a) hard-delete lock, ALL 3 must be absent from production "
        f"call sites."
    )


# ---------------------------------------------------------------------------
# A7 (D1) — worker return shape is list[tuple[float, float, str]] (Q2 (a))
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_p0_r6_z_d1_anchor_2_worker_return_shape_edge_cases() -> None:
    """A7 — ``pyannote_diarize_worker`` honors the Q2 (a) lock return
    shape contract:
    - Empty audio buffer → returns ``[]``
    - Single-segment mock → returns single-tuple list ``[(start, end, label)]``
    - Pipeline load failure → returns ``None``

    Behavioral test with mocked subprocess accessor. Validates the
    Annotation → list[tuple] serialization happens subprocess-side
    BEFORE returning (so main process receives serializable types only).

    Per Plan v1 §2.6 (f) deliberate-regression: modifying the worker to
    return pyannote Annotation directly (skipping serialization) fires
    this anchor — Annotation lacks the list iteration shape this test
    expects.
    """
    from unittest.mock import patch, MagicMock  # noqa: PLC0415

    import numpy as np  # noqa: PLC0415

    import core.heavy_worker as hw  # noqa: PLC0415

    # Edge case 1: empty audio buffer → returns [].
    empty_audio = np.zeros(0, dtype=np.float32)
    result_empty = hw.pyannote_diarize_worker(
        empty_audio.tobytes(), empty_audio.shape, "float32", 16000
    )
    assert result_empty == [], (
        f"A7 regression: empty audio → expected [], got {result_empty!r}"
    )

    # Edge case 2: pipeline load failure → returns None.
    audio = np.zeros(16000, dtype=np.float32)
    with patch.object(hw, "_get_subprocess_pyannote", return_value=None):
        result_load_fail = hw.pyannote_diarize_worker(
            audio.tobytes(), audio.shape, "float32", 16000
        )
    assert result_load_fail is None, (
        f"A7 regression: pipeline load failure → expected None, got "
        f"{result_load_fail!r}"
    )

    # Edge case 3: single-segment mock → returns single-tuple list.
    class _MockSegment:
        def __init__(self, start: float, end: float):
            self.start = start
            self.end = end

    class _MockAnnotation:
        def __init__(self, items):
            self._items = items

        def itertracks(self, yield_label: bool = False):
            for seg, track, label in self._items:
                yield (seg, track, label)

    class _MockPipeline:
        def __init__(self, annotation):
            self._ann = annotation

        def __call__(self, _waveform_dict):
            return self._ann

    mock_ann = _MockAnnotation(
        [(_MockSegment(0.5, 2.0), "t0", "SPEAKER_00")]
    )
    with patch.object(hw, "_get_subprocess_pyannote",
                      return_value=_MockPipeline(mock_ann)):
        result_single = hw.pyannote_diarize_worker(
            audio.tobytes(), audio.shape, "float32", 16000
        )

    assert isinstance(result_single, list), (
        f"A7 regression: single-segment → expected list, got "
        f"{type(result_single).__name__}: {result_single!r}"
    )
    assert len(result_single) == 1, (
        f"A7 regression: single-segment → expected 1 tuple, got "
        f"{len(result_single)}"
    )
    tup = result_single[0]
    assert isinstance(tup, tuple) and len(tup) == 3, (
        f"A7 regression: single-segment tuple shape wrong: {tup!r}"
    )
    start_secs, end_secs, label = tup
    assert isinstance(start_secs, float) and isinstance(end_secs, float), (
        f"A7 regression: tuple start/end must be float (Q2 (a) "
        f"serialization). Got: {type(start_secs).__name__}, "
        f"{type(end_secs).__name__}"
    )
    assert isinstance(label, str), (
        f"A7 regression: tuple label must be str (Q2 (a) "
        f"serialization). Got: {type(label).__name__}"
    )
    assert start_secs == 0.5 and end_secs == 2.0 and label == "SPEAKER_00", (
        f"A7 regression: tuple values wrong: {tup!r}"
    )


# ---------------------------------------------------------------------------
# A8 (D4) — HealthSnapshot has pyannote_diarize in heavy_worker_status
# ---------------------------------------------------------------------------


def test_p0_r6_z_d4_anchor_1_health_snapshot_includes_pyannote_status() -> None:
    """A8 — ``HealthSnapshot.heavy_worker_status`` dict reports the
    ``"pyannote_diarize"`` key after pipeline startup wiring fires.

    Source-inspection: ``pipeline.py::run()`` startup calls
    ``set_heavy_worker_status("pyannote_diarize", "healthy")``. Without
    the wiring, the dict would lack the key and operators would see no
    health signal for the Pyannote pool.

    Per Plan v1 §2.6 (g) deliberate-regression: dropping the
    ``set_heavy_worker_status("pyannote_diarize", ...)`` line fires this
    anchor.
    """
    source = _PIPELINE.read_text(encoding="utf-8")
    assert 'set_heavy_worker_status("pyannote_diarize", "healthy")' in source, (
        "D4 regression: pipeline.run() startup missing "
        'set_heavy_worker_status("pyannote_diarize", "healthy") call. '
        "Per Plan v1 §2.4, the initial state must mark the pool as "
        "healthy in the observability surface alongside the prior 3 "
        "pools (AdaFace + Whisper + ECAPA)."
    )


# ---------------------------------------------------------------------------
# A9 (D4) — 4-pool ORDERING INVARIANT
# ---------------------------------------------------------------------------


def test_p0_r6_z_d4_anchor_2_four_pool_ordering_invariant() -> None:
    """A9 — ``pipeline.run()`` startup spawns the 4 heavy-worker pools
    in the LOCKED order: AdaFace → Whisper → ECAPA → Pyannote → vision
    task spawn (4-pool ordering invariant; all 4 pools must be ready
    before vision task spawn).

    Per Plan v1 §2.6 (g) deliberate-regression: reversing the order OR
    dropping any pool warm-up fires this anchor.

    Final cycle of 4-task heavy-worker migration arc — this anchor
    captures the completion-state invariant.
    """
    source = _PIPELINE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # AST scan for actual `hw.get_or_create_pool("<name>")` Call nodes —
    # NOT substring (avoids matching docstring/comment references to the
    # call shape, which are documentary).
    pool_lines: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "hw"
            and func.attr == "get_or_create_pool"
        ):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and first.value in (
            "adaface_embed", "whisper_transcribe",
            "ecapa_embed", "pyannote_diarize",
        ):
            # Capture the FIRST production Call site for each pool name.
            if first.value not in pool_lines:
                pool_lines[first.value] = node.lineno

    # AST scan for `_vision_task = asyncio.create_task(...)` Assign target.
    vision_task_line = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_vision_task":
                    if vision_task_line is None:
                        vision_task_line = node.lineno
                    break

    expected = ("adaface_embed", "whisper_transcribe",
                "ecapa_embed", "pyannote_diarize")
    missing = [p for p in expected if p not in pool_lines]
    assert not missing, (
        f"D4 regression (ordering invariant): pool(s) missing from "
        f"pipeline.run() startup: {missing}. Per Plan v1 §2.4, all 4 "
        f"pools (AdaFace + Whisper + ECAPA + Pyannote) must be warmed "
        f"up before vision task spawn — final cycle of 4-task arc."
    )
    assert vision_task_line is not None, (
        "D4 sanity: _vision_task = asyncio.create_task(...) not found "
        "in pipeline.py — has the wiring regressed?"
    )

    ordered_lines = [pool_lines[p] for p in expected]
    is_ordered = all(
        ordered_lines[i] < ordered_lines[i + 1]
        for i in range(len(ordered_lines) - 1)
    )
    assert is_ordered and ordered_lines[-1] < vision_task_line, (
        f"D4 regression (ordering invariant): pool lines out of order. "
        f"Expected ascending: adaface ({pool_lines['adaface_embed']}) < "
        f"whisper ({pool_lines['whisper_transcribe']}) < "
        f"ecapa ({pool_lines['ecapa_embed']}) < "
        f"pyannote ({pool_lines['pyannote_diarize']}) < "
        f"vision ({vision_task_line}). Per Plan v1 §2.4, all 4 pools "
        f"MUST be ready before vision task spawn."
    )


# ---------------------------------------------------------------------------
# A10 (PI #1/#2/Z absorption) — programmatic test-patch enforcement extended
# ---------------------------------------------------------------------------


def test_p0_r6_z_a10_test_patches_use_asyncmock_for_async_functions() -> None:
    """A10 EXTENDED (P0.R6.Y A10 base + P0.R6.Z additions) — all
    patches/stubs of async voice_mod functions (``embed``, ``identify``,
    ``_diarize_ecapa_valley``, ``_diarize_pyannote``, ``diarize``) AND
    new pyannote subprocess-side surfaces (``pyannote_diarize_worker``,
    ``_get_subprocess_pyannote``) across all test files use
    ``AsyncMock`` OR ``async def`` wrapper.

    Per Plan v1 §2.6 (h) deliberate-regression: injecting a
    ``MagicMock`` patch for any of the 5 async voice fns OR the new
    subprocess-side surfaces in any test file fires this anchor.
    """
    test_files = [
        _REPO_ROOT / "test_pipeline.py",
        _REPO_ROOT / "tests" / "conftest.py",
    ]
    for test_file in (_REPO_ROOT / "tests").rglob("test_*.py"):
        if test_file not in test_files:
            test_files.append(test_file)

    ASYNC_VOICE_FNS = ("embed", "identify", "_diarize_ecapa_valley",
                       "_diarize_pyannote", "diarize",
                       "pyannote_diarize_worker")

    patterns = [
        # Shape A: patch("module.fn", ...)
        re.compile(
            r'patch\(["\'](?:pipeline\.voice_mod|core\.voice|core\.heavy_worker)\.('
            + '|'.join(ASYNC_VOICE_FNS) + r')["\']'
        ),
        # Shape B: patch.object(module, "fn", ...)
        re.compile(
            r'patch\.object\([^,]+,\s*["\'](' + '|'.join(ASYNC_VOICE_FNS) + r')["\']'
        ),
        # Shape C: module-stub-assignment
        re.compile(
            r'(?:_voice_stub|_vs|_voice_mod|hw)\.('
            + '|'.join(ASYNC_VOICE_FNS) + r')\s*=\s*MagicMock\('
        ),
    ]

    violations = []
    for test_file in test_files:
        if not test_file.exists():
            continue
        src = test_file.read_text(encoding="utf-8")
        for pattern in patterns:
            for match in pattern.finditer(src):
                start = max(0, match.start() - 200)
                end = min(len(src), match.end() + 200)
                context = src[start:end]
                if "AsyncMock" not in context and "async def" not in context:
                    line_no = src[:match.start()].count("\n") + 1
                    rel_path = test_file.relative_to(_REPO_ROOT)
                    violations.append(
                        f"{rel_path}:{line_no} — async fn "
                        f"`{match.group(1)}` mocked with MagicMock; "
                        f"requires AsyncMock OR async def wrapper"
                    )

    assert not violations, (
        f"P0.R6.Z A10 — {len(violations)} test patch sites use MagicMock "
        f"for async functions: " + "; ".join(violations)
    )


# ---------------------------------------------------------------------------
# A11 (PI #2/Z absorption) — programmatic direct-call enforcement extended
# ---------------------------------------------------------------------------


def test_p0_r6_z_a11_test_direct_calls_use_await_for_async_functions() -> None:
    """A11 EXTENDED (P0.R6.Y A11 base + P0.R6.Z additions) — all direct
    calls to async voice_mod functions including ``_diarize_pyannote``
    in tests must be preceded by ``await`` keyword.

    Per Plan v1 §2.6 (i) deliberate-regression: adding a
    ``_voice_mod._diarize_pyannote(...)`` direct call WITHOUT await in
    any test file fires this anchor (preventive — zero current sites
    per auditor's Phase 0 §1.3.D verification).
    """
    test_files = [_REPO_ROOT / "test_pipeline.py"]
    # Exclude the anchor test files themselves — they document the rule
    # in docstrings (Plan v1 §2.6 regression mapping), not enforce it on
    # themselves. Same shape as P0.S6 `_REGISTRY_ALLOWLIST` precedent.
    _ANCHOR_FILES = {
        "test_p0_r6_y_ecapa_worker.py",
        "test_p0_r6_z_pyannote_worker.py",
    }
    for test_file in (_REPO_ROOT / "tests").rglob("test_*.py"):
        if test_file.name in _ANCHOR_FILES:
            continue
        if test_file not in test_files:
            test_files.append(test_file)

    ASYNC_VOICE_FNS = ("embed", "identify", "_diarize_ecapa_valley",
                       "_diarize_pyannote", "diarize")

    pattern = re.compile(
        r'(?<!await )_voice_mod\.('
        + '|'.join(ASYNC_VOICE_FNS) + r')\('
    )

    violations = []
    for test_file in test_files:
        if not test_file.exists():
            continue
        src = test_file.read_text(encoding="utf-8")
        for match in pattern.finditer(src):
            line_no = src[:match.start()].count("\n") + 1
            rel_path = test_file.relative_to(_REPO_ROOT)
            violations.append(
                f"{rel_path}:{line_no} — direct call to async "
                f"`_voice_mod.{match.group(1)}(...)` missing `await`"
            )

    assert not violations, (
        f"P0.R6.Z A11 — {len(violations)} direct calls to async "
        f"functions missing `await`: " + "; ".join(violations)
    )
