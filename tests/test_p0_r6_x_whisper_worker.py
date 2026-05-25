"""P0.R6.X — Whisper migration to ProcessPoolExecutor worker (7 logical anchors).

Validates the ``core/heavy_worker.py`` Whisper section (D1 + D2), the
``core/audio.py::transcribe()`` async migration + worker dispatch (D3), and
the ``pipeline.py::run()`` startup wiring extension (D4).

Per Plan v1 §3 LOCK: 7 anchors at exact mid 7 INCLUSIVE ±15% band [5.95, 8.05].
Q2 (b) LOCK: filter chain (non-ASCII / char-run / word-repetition / phrase-
repetition / 1-word artifact) stays in main process AFTER worker returns —
A5 is the behavioral regression guard.

Hybrid surface:
- A1-A2, A6: source-inspection (substring + module-level FunctionDef)
- A3-A4: AST positive + inverse checks on ``transcribe()`` body
- A5: behavioral test with mocked ``hw.run_heavy`` returning hallucination shapes
- A7: AST line-order positive check (pool spawn BEFORE vision task)

Anchor-to-deliberate-regression mapping (per Plan v1 §2.5):
- (a) Delete ``whisper_transcribe_worker`` from ``core/heavy_worker.py`` → A1
- (b) Replace ``_get_subprocess_whisper()`` body with unconditional None → A2
- (c) Revert ``transcribe()`` to direct ``model.transcribe(...)`` call → A3 + A4
- (d) Remove filter chain from ``transcribe()`` (Q2 (b) violation) → A5
- (e) Drop ``hw.get_or_create_pool("whisper_transcribe")`` from startup → A6 + A7
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_HEAVY_WORKER = _REPO_ROOT / "core" / "heavy_worker.py"
_AUDIO = _REPO_ROOT / "core" / "audio.py"
_PIPELINE = _REPO_ROOT / "pipeline.py"


# ---------------------------------------------------------------------------
# A1 (D1) — whisper_transcribe_worker module-level function
# ---------------------------------------------------------------------------


def test_p0_r6_x_d1_anchor_1_whisper_worker_function_exists() -> None:
    """A1 — ``whisper_transcribe_worker`` is defined at MODULE SCOPE in
    ``core/heavy_worker.py`` (NOT nested inside another function).
    Module-level definition is required for pickleability — ProcessPoolExecutor's
    spawn-based IPC pickles the function reference; nested functions can't
    be pickled.

    Per Plan v1 §2.5 (a) deliberate-regression: deleting the function from
    the module fires this anchor (file-existence + module-level check).
    """
    tree = ast.parse(_HEAVY_WORKER.read_text(encoding="utf-8"))
    module_level_funcs = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    assert "whisper_transcribe_worker" in module_level_funcs, (
        f"D1 regression: whisper_transcribe_worker must be defined at module "
        f"scope in core/heavy_worker.py (pickleability requirement). "
        f"Current module-level functions: {sorted(module_level_funcs)}."
    )
    # Also verify it's importable + callable.
    import core.heavy_worker as hw  # noqa: PLC0415

    assert callable(getattr(hw, "whisper_transcribe_worker", None)), (
        "D1 regression: whisper_transcribe_worker not callable after import."
    )


# ---------------------------------------------------------------------------
# A2 (D2) — _SUBPROCESS_WHISPER_MODEL singleton + _get_subprocess_whisper accessor
# ---------------------------------------------------------------------------


def test_p0_r6_x_d2_anchor_1_subprocess_whisper_singleton_and_accessor() -> None:
    """A2 — ``_SUBPROCESS_WHISPER_MODEL`` module-level singleton + lazy-init
    accessor ``_get_subprocess_whisper()`` present in ``core/heavy_worker.py``.

    The singleton enforces "model loads ONCE per subprocess lifetime" — the
    persistent-worker invariant from Plan v1 §2.2. Without the accessor, every
    worker call would pay the ~1-2s WhisperModel load cost.

    Per Plan v1 §2.5 (b) deliberate-regression: replacing the accessor body
    with unconditional ``return None`` fires this anchor (lazy-init shape check
    requires both the global declaration AND the load attempt).
    """
    source = _HEAVY_WORKER.read_text(encoding="utf-8")

    # Module-level singleton declaration.
    assert "_SUBPROCESS_WHISPER_MODEL" in source, (
        "D2 regression: _SUBPROCESS_WHISPER_MODEL module-level singleton "
        "missing from core/heavy_worker.py. Per Plan v1 §2.2, the singleton "
        "is the persistent-worker contract anchor (load-once per subprocess)."
    )

    # Accessor function present at module scope.
    tree = ast.parse(source)
    module_level_funcs = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    assert "_get_subprocess_whisper" in module_level_funcs, (
        f"D2 regression: _get_subprocess_whisper() accessor missing. "
        f"Current module-level functions: {sorted(module_level_funcs)}."
    )

    # Lazy-init shape check — accessor body must (a) declare global AND
    # (b) attempt a WhisperModel construction. Unconditional-None body would
    # pass module-level checks but break the load contract.
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_get_subprocess_whisper":
            globals_declared = any(
                isinstance(s, ast.Global)
                and "_SUBPROCESS_WHISPER_MODEL" in s.names
                for s in ast.walk(node)
            )
            assert globals_declared, (
                "D2 regression: _get_subprocess_whisper() body missing "
                "`global _SUBPROCESS_WHISPER_MODEL` declaration. Without "
                "the global, the lazy-init assignment creates a function-"
                "local instead of populating the module singleton."
            )
            whisper_model_calls = [
                n for n in ast.walk(node)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "WhisperModel"
            ]
            assert whisper_model_calls, (
                "D2 regression: _get_subprocess_whisper() body missing "
                "WhisperModel(...) construction. The lazy-init contract "
                "requires constructing the model on first call; an "
                "unconditional `return None` body bypasses this."
            )
            break


# ---------------------------------------------------------------------------
# A3 (D3 part b) — transcribe() body dispatches to hw.run_heavy("whisper_transcribe", ...)
# ---------------------------------------------------------------------------


def test_p0_r6_x_d3_anchor_1_transcribe_body_uses_hw_run_heavy() -> None:
    """A3 — ``core/audio.py::transcribe()`` body contains a positive
    ``hw.run_heavy("whisper_transcribe", ...)`` Call node (AST scan, not
    substring — docstring mentions of the task name would pass a substring
    check even after the actual Call was reverted).

    Per Plan v1 §2.5 (c) deliberate-regression: reverting the body to a
    direct ``model.transcribe(...)`` sync call fires this anchor (the
    ``hw.run_heavy`` Call disappears).
    """
    source = _AUDIO.read_text(encoding="utf-8")
    tree = ast.parse(source)
    found = False
    for fn_node in tree.body:
        if not (isinstance(fn_node, ast.AsyncFunctionDef) and fn_node.name == "transcribe"):
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
                and node.args[0].value == "whisper_transcribe"
            ):
                found = True
                break
        break

    assert found, (
        "D3 regression (positive check): core/audio.py::transcribe() body "
        "does not call hw.run_heavy(\"whisper_transcribe\", ...). Per Plan v1 "
        "§2.3, the migrated body must offload inference to the heavy-worker "
        "subprocess; reverting to direct model.transcribe(...) call would "
        "block the asyncio event loop for the duration of inference."
    )


# ---------------------------------------------------------------------------
# A4 (D3 part b) — transcribe() body does NOT contain model.transcribe(audio, ...) sync call
# ---------------------------------------------------------------------------


def test_p0_r6_x_d3_anchor_2_transcribe_body_no_direct_model_call() -> None:
    """A4 — ``core/audio.py::transcribe()`` body must NOT contain a direct
    ``model.transcribe(...)`` Call node (inverse check; the worker
    subprocess now owns the inference call).

    Per Plan v1 §2.5 (c) deliberate-regression: reverting the body to a
    direct ``model.transcribe(audio, ...)`` call fires this inverse anchor.
    The worker module ``core/heavy_worker.py::whisper_transcribe_worker``
    legitimately calls ``model.transcribe(...)``; that's expected and OUT
    OF SCOPE for this anchor (which scans ``core/audio.py`` only).
    """
    source = _AUDIO.read_text(encoding="utf-8")
    tree = ast.parse(source)
    direct_model_calls = []
    for fn_node in tree.body:
        if not (isinstance(fn_node, ast.AsyncFunctionDef) and fn_node.name == "transcribe"):
            continue
        for node in ast.walk(fn_node):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # Match `model.transcribe(...)` Call (Attribute on a Name "model").
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "model"
                and func.attr == "transcribe"
            ):
                direct_model_calls.append(node.lineno)
        break

    assert not direct_model_calls, (
        f"D3 regression (inverse check): core/audio.py::transcribe() body "
        f"contains direct model.transcribe(...) Call nodes at lines "
        f"{direct_model_calls}. Per Plan v1 §2.3 post-migration, the body "
        f"must NOT do the inference inline; offload via hw.run_heavy("
        f"\"whisper_transcribe\", ...) and let the worker subprocess hold "
        f"the model singleton. Direct sync inference blocks the asyncio loop."
    )


# ---------------------------------------------------------------------------
# A5 (D3 part b) — filter chain still applies AFTER worker returns (Q2 (b) lock)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_p0_r6_x_d3_anchor_3_filter_chain_applies_after_worker() -> None:
    """A5 — the filter chain (non-ASCII / char-run / word-repetition / phrase-
    repetition / 1-word artifact) still runs AFTER the worker returns text,
    in the MAIN process per Q2 (b) lock.

    Per Plan v1 §2.5 (d) deliberate-regression: removing the filter chain
    from ``transcribe()`` body lets a hallucination text shape pass through
    unfiltered; this behavioral anchor fires by feeding the worker stub a
    char-run hallucination and asserting the main-process filter catches it.

    Bypasses the conftest ``core.audio`` stub by loading ``core/audio.py``
    directly via importlib (the stub replaces the module at sys.modules
    level for tests that don't care about audio internals; this test
    requires the REAL filter chain). Stubs ``core.heavy_worker.run_heavy``
    to return ``("Mmmmmmmmmmmmmmmmmmmm", "en")`` — a 20-char run that
    triggers the Session 105 Obs A regex ``(.)\\1{15,}``. Assertion:
    ``transcribe()`` returns ``("", "en")`` — the filter chain caught
    the hallucination in the main process AFTER the worker returned it.
    """
    import importlib.util  # noqa: PLC0415
    import sys  # noqa: PLC0415
    import types  # noqa: PLC0415
    from unittest.mock import MagicMock  # noqa: PLC0415

    import numpy as np  # noqa: PLC0415

    # The real core/audio.py imports sounddevice at module-top; on this
    # Windows dev machine the package isn't installed (conftest stubs it
    # for the conftest-loaded core.audio path). Pre-register a sounddevice
    # MagicMock stub in sys.modules so the force-load below succeeds.
    if "sounddevice" not in sys.modules:
        _sd_stub = types.ModuleType("sounddevice")
        _sd_stub.play = MagicMock()
        _sd_stub.wait = MagicMock()
        _sd_stub.stop = MagicMock()
        _sd_stub.InputStream = MagicMock()
        _sd_stub.OutputStream = MagicMock()
        sys.modules["sounddevice"] = _sd_stub

    # Load the REAL core/audio.py from disk (bypassing the conftest stub
    # at sys.modules["core.audio"]). The loaded module gets a distinct
    # name to avoid polluting sys.modules — other tests continue using
    # the stub.
    spec = importlib.util.spec_from_file_location(
        "_p0_r6_x_real_audio", str(_AUDIO)
    )
    assert spec is not None and spec.loader is not None
    real_audio = importlib.util.module_from_spec(spec)
    # Real audio expects `from core.audio import ...` patterns to resolve;
    # the inline `import core.heavy_worker as hw` inside transcribe()
    # re-fetches from sys.modules each call so monkeypatching works at
    # the heavy_worker module level.
    spec.loader.exec_module(real_audio)

    fake_audio = np.zeros(16000, dtype=np.float32)

    async def _stub_run_heavy(task_name, fn, *args, **kwargs):
        # Worker returns a char-run hallucination. The main process filter
        # chain (Session 105 Obs A) catches the 16+ char repeat and discards.
        return ("Mmmmmmmmmmmmmmmmmmmm", kwargs.get("language", "en"))

    # Patch the heavy_worker module's run_heavy at the source — transcribe()
    # uses inline `import core.heavy_worker as hw` so the patched binding
    # is picked up at call time.
    import core.heavy_worker as hw  # noqa: PLC0415
    original_run_heavy = hw.run_heavy
    hw.run_heavy = _stub_run_heavy
    try:
        text, lang = await real_audio.transcribe(fake_audio)
    finally:
        hw.run_heavy = original_run_heavy

    assert text == "" and lang == "en", (
        f"D3 regression (Q2 (b) filter-chain location): char-run hallucination "
        f"'Mmmmmmmmmmmmmmmmmmmm' passed through transcribe() unfiltered. Got "
        f"({text!r}, {lang!r}). Per Plan v1 §2.3 Q2 (b) lock, the filter "
        f"chain (non-ASCII / char-run / repetition / 1-word artifact) MUST "
        f"stay in the main process AFTER the worker returns text. Dropping "
        f"the filter chain or moving it into the worker would let this "
        f"hallucination shape pass through."
    )


# ---------------------------------------------------------------------------
# A6 (D4) — pipeline.run() startup includes whisper_transcribe pool warm-up
# ---------------------------------------------------------------------------


def test_p0_r6_x_d4_anchor_1_startup_warms_whisper_pool() -> None:
    """A6 — ``pipeline.py::run()`` startup calls
    ``hw.get_or_create_pool("whisper_transcribe")`` AND
    ``set_heavy_worker_status("whisper_transcribe", "healthy")``.

    Source-inspection (substring on the source — both invocations are
    distinctive enough that docstring collisions are not a concern; the
    rendered call shape doesn't appear elsewhere).

    Per Plan v1 §2.5 (e) deliberate-regression: dropping the pool warm-up
    fires this anchor.
    """
    source = _PIPELINE.read_text(encoding="utf-8")

    assert 'hw.get_or_create_pool("whisper_transcribe")' in source, (
        "D4 regression: pipeline.run() startup missing "
        'hw.get_or_create_pool("whisper_transcribe") call. Per Plan v1 §2.4, '
        "the Whisper worker pool MUST be warmed up before the vision task "
        "spawns so the first await transcribe(...) call doesn't pay the "
        "subprocess startup + model-load cost on the awaiting coroutine."
    )
    assert 'set_heavy_worker_status("whisper_transcribe", "healthy")' in source, (
        "D4 regression: pipeline.run() startup missing "
        'set_heavy_worker_status("whisper_transcribe", "healthy") call. '
        "Per Plan v1 §2.4, the initial state must mark the pool as healthy "
        "in the observability surface alongside adaface_embed."
    )


# ---------------------------------------------------------------------------
# A7 (D4) — startup AST line-order: whisper pool BEFORE vision task spawn
# ---------------------------------------------------------------------------


def test_p0_r6_x_d4_anchor_2_whisper_pool_spawn_before_vision_task() -> None:
    """A7 — ``pipeline.run()`` startup spawns the whisper_transcribe heavy-
    worker pool BEFORE the vision task (D4 ordering invariant; worker must
    be ready when the first ``await transcribe(...)`` call fires, which can
    happen via the multi-speaker diarize path inside
    ``_background_vision_loop`` indirectly or via ``listen_and_transcribe``
    directly).

    Source-inspection line-order check (same pattern as P0.R6 A7): locate
    the ``hw.get_or_create_pool("whisper_transcribe")`` line + the
    ``_vision_task = asyncio.create_task(_background_vision_loop(...))``
    line, assert the pool spawn comes FIRST.

    Per Plan v1 §2.5 (e) deliberate-regression: reversing the order fires
    this anchor (the inverse of A6 — A6 catches "pool spawn line missing"
    while A7 catches "pool spawn lands AFTER vision task spawn").
    """
    source = _PIPELINE.read_text(encoding="utf-8")
    lines = source.splitlines()

    whisper_pool_line = None
    vision_task_line = None
    for i, line in enumerate(lines, start=1):
        if whisper_pool_line is None and 'hw.get_or_create_pool("whisper_transcribe")' in line:
            whisper_pool_line = i
        if vision_task_line is None and "_vision_task = asyncio.create_task(" in line:
            vision_task_line = i
        if whisper_pool_line is not None and vision_task_line is not None:
            break

    assert whisper_pool_line is not None, (
        "D4 regression: pipeline.run() does not call "
        'hw.get_or_create_pool("whisper_transcribe") at startup. Per Plan v1 '
        "§2.4, the whisper worker pool must be warmed up before the vision "
        "task spawns (which can indirectly trigger STT via multi-speaker "
        "diarize)."
    )
    assert vision_task_line is not None, (
        "D4 sanity: _vision_task = asyncio.create_task(...) not found in "
        "pipeline.py — has the P0.R3 D5 + P0.R6 D5 wiring been removed?"
    )
    assert whisper_pool_line < vision_task_line, (
        f"D4 regression (ordering invariant): whisper heavy-worker pool spawn "
        f"at line {whisper_pool_line} comes AFTER vision task spawn at line "
        f"{vision_task_line}. Per Plan v1 §2.4, pool MUST be ready before "
        f"the first await transcribe(...) call fires."
    )
